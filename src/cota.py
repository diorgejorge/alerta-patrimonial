"""Cota parlamentar (CEAP/CEAPS): quanto deputados federais e senadores gastaram da cota para o exercicio
da atividade parlamentar, por ano e por tipo de despesa. Fontes oficiais, arquivos anuais abertos:
  Camara: https://www.camara.leg.br/cotas/Ano-AAAA.csv.zip (tem CPF: liga com a declaracao do TSE)
  Senado: https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_AAAA.csv (so o nome do senador)
O CPF so serve para ligar as bases aqui dentro; nunca vai para o site. Fornecedores tambem nao sao exibidos."""
import html, io, re, sys, unicodedata, urllib.error, urllib.request, zipfile
import cifra
from cache import ano_fechado, resultados, resumo_fechado, resumo_log
from collections import Counter
from pathlib import Path
import pandas as pd

VERSAO_COTA = 1  # mude ao alterar a leitura: invalida os resumos guardados dos anos fechados (#48)
CAMARA = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
SENADO = "https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv"
LINK_CAMARA = "https://www.camara.leg.br/deputados/{id}"
LINK_CAMARA_GERAL = "https://www.camara.leg.br/transparencia/gastos-parlamentares"
LINK_SENADO = "https://www12.senado.leg.br/transparencia/dados-abertos-transparencia/dados-abertos-ceaps"
UA = "alerta-patrimonial/1.0"
MAX_TIPOS = 5
e = html.escape


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def baixar(url, dest):
    """Conteudo (bytes) do arquivo anual, guardado cifrado em data/cache (cifra.py); so baixa de novo se o servidor
    disser que mudou (If-Modified-Since)."""
    return cifra.baixar(url, dest, cab={"User-Agent": UA})


def _bytes(x):
    """Bytes do arquivo: aceita o conteudo ja lido ou um caminho (testes)."""
    return bytes(x) if isinstance(x, (bytes, bytearray)) else Path(x).read_bytes()


def ler_camara(path):
    """Linhas de despesa da Camara: cpf (so digitos), id, ano, tipo, valor liquido."""
    with zipfile.ZipFile(io.BytesIO(_bytes(path))) as z:
        nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        df = pd.read_csv(z.open(nome), sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False,
                         usecols=["cpf", "ideCadastro", "nuDeputadoId", "numAno", "txtDescricao", "vlrLiquido"])
    df["cpf"] = df["cpf"].str.replace(r"\D", "", regex=True)
    df = df[df["cpf"].str.len() == 11]
    return pd.DataFrame(dict(cpf=df["cpf"], id=df["ideCadastro"].where(df["ideCadastro"] != "", df["nuDeputadoId"]),
                             ano=pd.to_numeric(df["numAno"], errors="coerce"), tipo=df["txtDescricao"].str.strip(),
                             valor=pd.to_numeric(df["vlrLiquido"].str.replace(",", ".", regex=False), errors="coerce")))


def ler_senado(path):
    """Linhas de despesa do Senado: nome do senador (normalizado), ano, tipo, valor reembolsado."""
    bruto = _bytes(path)
    txt = bruto.decode("utf-8") if bruto[:3] == b"\xef\xbb\xbf" or _utf8(bruto) else bruto.decode("latin-1")
    linhas = txt.splitlines()
    ini = next((i for i, l in enumerate(linhas[:5]) if l.startswith('"ANO"')), 0)
    # separa pelos delimitadores '";"' em vez de um leitor CSV: o arquivo tem aspas soltas dentro do detalhamento
    # (o pandas parava em "EOF inside string") e quebras de linha dentro de campos (juntadas ate fechar a linha)
    cab = linhas[ini].strip().strip('"').split('";"')
    regs, buf = [], ""
    for l in linhas[ini + 1:]:
        buf = f"{buf}\n{l}" if buf else l
        if buf.count('";"') >= len(cab) - 1 and buf.rstrip().endswith('"'):
            campos = buf.strip().strip('"').split('";"')
            if len(campos) == len(cab):
                regs.append(campos)
            buf = ""
    df = pd.DataFrame(regs, columns=cab)
    return pd.DataFrame(dict(nome=df["SENADOR"].map(norm), ano=pd.to_numeric(df["ANO"], errors="coerce"),
                             tipo=df["TIPO_DESPESA"].str.strip().str.replace(r",\s*compreendendo.*$", "", regex=True),
                             valor=pd.to_numeric(df["VALOR_REEMBOLSADO"].str.replace(".", "", regex=False)
                                                 .str.replace(",", ".", regex=False), errors="coerce")))


def _utf8(b):
    try:
        b.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _resumo(df):
    df = df.dropna(subset=["ano", "valor"])
    if df.empty:
        return None
    anos = df.groupby("ano")["valor"].sum().sort_index()
    tipos = df.groupby("tipo")["valor"].sum().sort_values(ascending=False).head(MAX_TIPOS)
    return dict(total=float(df["valor"].sum()), anos=[(int(a), float(v)) for a, v in anos.items()],
                tipos=[(str(t), float(v)) for t, v in tipos.items()])


_BASES = {}


def bases(anos, cache):
    """Despesas de todos os deputados (Camara) e senadores (Senado) nos anos pedidos, lidas uma vez por execucao.
    Devolve (camara, senado, fontes); camara/senado vazios se o arquivo nao veio."""
    chave = (tuple(anos), str(cache))
    if chave in _BASES:
        return _BASES[chave]
    cache = Path(cache)
    ok, dep, sen = {"camara": False, "senado": False}, [], []
    # ano fechado (#48): o resumo por pessoa, ano e tipo fica guardado (cifrado) com o sha256 do arquivo de origem;
    # o arquivo bruto nao e guardado e so e baixado de novo a cada cache.CONFERIR_S para ver se a fonte o corrigiu
    guardados = resultados(cache, "cota_anos", 400 * 86400)
    fontes = (("camara", dep, CAMARA, "ceap_camara_{ano}.zip", ler_camara, ["cpf", "id", "ano", "tipo"]),
              ("senado", sen, SENADO, "ceaps_senado_{ano}.csv", ler_senado, ["nome", "ano", "tipo"]))
    origens = Counter()
    for ano in anos:
        fechado = guardados is not None and ano_fechado(ano)
        for casa, partes, url, arq, ler, por in fontes:
            bruto = cache / arq.format(ano=ano)
            resumir = lambda b: ler(b).dropna(subset=["ano", "valor"]).groupby(por, as_index=False)["valor"].sum()
            try:
                if fechado:
                    d, origem = resumo_fechado(guardados, (VERSAO_COTA, casa, int(ano)),
                                               lambda: baixar(url.format(ano=ano), None),
                                               lambda b: resumir(b).to_dict("list"))
                    for p in (bruto, Path(str(bruto) + ".modificado")):  # bruto antigo: menos espaco no actions/cache
                        p.unlink(missing_ok=True)
                    if d is None:
                        continue
                    origens[origem] += 1
                    df = pd.DataFrame(d)
                else:  # ano atual (ou sem ID_SEGREDO): sempre relido
                    b = baixar(url.format(ano=ano), bruto)
                    if not b:
                        continue
                    df = resumir(b)
            except Exception as ex:
                print(f"[aviso] cota parlamentar: {casa} {ano} ilegivel ({ex!r})", file=sys.stderr)
                continue
            partes.append(df)
            ok[casa] = True
    resumo_log("Cota parlamentar", origens)
    vazio = pd.DataFrame(columns=["cpf", "id", "nome", "ano", "tipo", "valor"])
    _BASES[chave] = (pd.concat(dep, ignore_index=True) if dep else vazio,
                     pd.concat(sen, ignore_index=True) if sen else vazio, ok)
    return _BASES[chave]


def medias(anos, cache):
    """Gasto medio da cota por parlamentar no periodo: {"camara": R$, "senado": R$}; None se o arquivo nao veio."""
    dep, sen, ok = bases(anos, cache)
    m = lambda df, por: float(df.dropna(subset=["valor"]).groupby(por)["valor"].sum().mean())
    return {"camara": m(dep, "cpf") if ok["camara"] and len(dep) else None,
            "senado": m(sen, "nome") if ok["senado"] and len(sen) else None}


def coletar(pessoas, anos, cache):
    """pessoas: {chave: dict(nome, nome_urna, cargo, cpf)}. Devolve {chave: resumo} so para quem tem despesa,
    e {"_fontes": {"camara": bool, "senado": bool}} dizendo se cada arquivo foi lido."""
    alvo_dep = {k: p for k, p in pessoas.items() if "DEPUTADO FEDERAL" in norm(p.get("cargo")) and p.get("cpf")}
    alvo_sen = {k: p for k, p in pessoas.items() if "SENADOR" in norm(p.get("cargo"))}
    out, ok = {}, {"camara": False, "senado": False}
    if alvo_dep or alvo_sen:
        dep, sen, ok = bases(anos, cache)
        if alvo_dep and len(dep):
            dep = dep[dep["cpf"].isin({p["cpf"] for p in alvo_dep.values()})]
            for k, p in alvo_dep.items():
                d = dep[dep["cpf"] == p["cpf"]]
                r = _resumo(d)
                if r:
                    ids = d["id"][d["id"] != ""]
                    r.update(casa="camara", link=LINK_CAMARA.format(id=ids.iloc[-1]) if len(ids) else LINK_CAMARA_GERAL)
                    out[k] = r
        if alvo_sen and len(sen):
            for k, p in alvo_sen.items():
                nomes = {norm(p.get("nome_urna")), norm(p.get("nome"))} - {""}
                r = _resumo(sen[sen["nome"].isin(nomes)])
                if r:
                    r.update(casa="senado", link=LINK_SENADO)
                    out[k] = r
    out["_fontes"] = dict(ok)
    n = len(out) - 1
    print(f"Cota parlamentar: {len(alvo_dep)} deputados federais e {len(alvo_sen)} senadores procurados, {n} com despesas.")
    return out


def secao(r, cargo, fontes):
    """HTML da secao 'Cota parlamentar' do dossie."""
    c = norm(cargo)
    casa = "camara" if "DEPUTADO FEDERAL" in c else "senado" if "SENADOR" in c else None
    if casa is None:
        return ('<p class="vazio"><b>Não informado</b>: a cota parlamentar só existe para deputados federais e '
                'senadores.</p>')
    if not r:
        if not (fontes or {}).get(casa):
            onde = "da Câmara" if casa == "camara" else "do Senado"
            link = LINK_CAMARA_GERAL if casa == "camara" else LINK_SENADO
            return (f'<p class="vazio"><b>Fonte não encontrada</b>: os dados abertos {onde} não responderam nesta '
                    f'execução. <a href="{e(link)}" target="_blank" rel="noopener">Consultar no site oficial</a>.</p>')
        return '<p class="vazio"><b>Não informado</b>: nenhuma despesa da cota encontrada para esta pessoa no período.</p>'
    anos = "".join(f'<tr><td>{a}</td><td class="n" data-label="Valor">{brl(v)}</td></tr>' for a, v in r["anos"])
    tipos = "".join(f"<li>{e(t)}<br><small>{brl(v)}</small></li>" for t, v in r["tipos"])
    nome_casa = "Câmara dos Deputados" if r["casa"] == "camara" else "Senado Federal"
    return (f'<p>{brl(r["total"])} gastos de {r["anos"][0][0]} a {r["anos"][-1][0]}. '
            f'<a href="{e(r["link"])}" target="_blank" rel="noopener">Ver no site da {nome_casa}</a></p>'
            '<div class="tab"><table class="resp"><thead><tr><th>Ano</th><th class="n">Valor</th></tr></thead>'
            f'<tbody>{anos}</tbody></table></div><p><b>Maiores tipos de despesa</b></p><ul class="nt">{tipos}</ul>')
