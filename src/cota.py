"""Cota parlamentar (CEAP/CEAPS): quanto deputados federais e senadores gastaram da cota para o exercicio
da atividade parlamentar, por ano e por tipo de despesa. Fontes oficiais, arquivos anuais abertos:
  Camara: https://www.camara.leg.br/cotas/Ano-AAAA.csv.zip (tem CPF: liga com a declaracao do TSE)
  Senado: https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_AAAA.csv (so o nome do senador)
O CPF so serve para ligar as bases aqui dentro; nunca vai para o site. Fornecedores tambem nao sao exibidos."""
import html, io, re, sys, unicodedata, urllib.error, urllib.request, zipfile
from pathlib import Path
import pandas as pd

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
    """Copia em data/cache; so baixa de novo se o servidor disser que mudou (If-Modified-Since)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    marca = dest.with_suffix(dest.suffix + ".modificado")
    cab = {"User-Agent": UA}
    if dest.exists() and marca.exists():
        cab["If-Modified-Since"] = marca.read_text().strip()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=300) as r:
            tmp = dest.with_suffix(".parcial")
            with open(tmp, "wb") as f:
                while bloco := r.read(1 << 20):
                    f.write(bloco)
            tmp.replace(dest)
            if r.headers.get("Last-Modified"):
                marca.write_text(r.headers["Last-Modified"])
    except urllib.error.HTTPError as ex:
        if ex.code != 304:
            print(f"[aviso] cota parlamentar: {url} ({ex})", file=sys.stderr)
    except Exception as ex:
        print(f"[aviso] cota parlamentar: {url} ({ex})", file=sys.stderr)
    return dest if dest.exists() else None


def ler_camara(path):
    """Linhas de despesa da Camara: cpf (so digitos), id, ano, tipo, valor liquido."""
    with zipfile.ZipFile(path) as z:
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
    bruto = path.read_bytes()
    txt = bruto.decode("utf-8") if bruto[:3] == b"\xef\xbb\xbf" or _utf8(bruto) else bruto.decode("latin-1")
    linhas = txt.splitlines()
    ini = next((i for i, l in enumerate(linhas[:5]) if l.startswith('"ANO"')), 0)
    df = pd.read_csv(io.StringIO("\n".join(linhas[ini:])), sep=";", dtype=str, keep_default_na=False)
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
    for ano in anos:
        z = baixar(CAMARA.format(ano=ano), cache / f"ceap_camara_{ano}.zip")
        if z:
            try:
                dep.append(ler_camara(z))
                ok["camara"] = True
            except Exception as ex:
                print(f"[aviso] cota parlamentar: Camara {ano} ilegivel ({ex!r})", file=sys.stderr)
        f = baixar(SENADO.format(ano=ano), cache / f"ceaps_senado_{ano}.csv")
        if f:
            try:
                sen.append(ler_senado(f))
                ok["senado"] = True
            except Exception as ex:
                print(f"[aviso] cota parlamentar: Senado {ano} ilegivel ({ex!r})", file=sys.stderr)
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
