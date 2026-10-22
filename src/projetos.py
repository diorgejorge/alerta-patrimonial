"""Projetos apresentados e aprovados por deputados federais e senadores nos ultimos 4 anos (PL, PLP e PEC, como
autor ou coautor). Aprovado = transformado em norma juridica. Selo "Mao na massa": os 10% de cada casa com mais
projetos aprovados. Fontes oficiais e gratuitas:
  Camara: arquivos abertos anuais https://dadosabertos.camara.leg.br/arquivos/proposicoes(Autores)/csv/
          (o id do deputado liga com o CPF pela cota parlamentar, so aqui dentro)
  Senado: API de Dados Abertos https://legis.senado.leg.br/dadosabertos/processo (uma consulta por senador)
O CPF nunca vai para o site; so contagens e links para conferir na fonte."""
import html, io, json, math, sys, time, urllib.parse, urllib.request
from pathlib import Path
import pandas as pd
import cifra, cota

CAMARA_PROP = "https://dadosabertos.camara.leg.br/arquivos/proposicoes/csv/proposicoes-{ano}.csv"
CAMARA_AUT = "https://dadosabertos.camara.leg.br/arquivos/proposicoesAutores/csv/proposicoesAutores-{ano}.csv"
SENADO_LISTA = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual"
SENADO_PROC = "https://legis.senado.leg.br/dadosabertos/processo?codigoParlamentarAutor={cod}&sigla=PL,PLP,PEC&dataInicioApresentacao={ini}"
LINK_CAMARA = "https://www.camara.leg.br/busca-portal?"
LINK_SENADO = "https://www25.senado.leg.br/web/atividade/materias/-/materia/autor/{cod}/p/1"
TIPOS = {"PL", "PLP", "PEC"}
FATIA = 0.10  # selo: os 10% de cada casa com mais projetos aprovados
SELO = "Mão na massa"
UA = "alerta-patrimonial/1.0"
e = html.escape


def baixar(url, dest):
    return cifra.baixar(url, dest, cab={"User-Agent": UA})


def _json(url, timeout=60):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as ex:
        print(f"[aviso] {url} indisponivel: {ex}", file=sys.stderr)
        return None


def _csv(b, cols):
    return pd.read_csv(io.BytesIO(bytes(b) if isinstance(b, (bytes, bytearray)) else Path(b).read_bytes()), sep=";",
                       dtype=str, encoding="utf-8-sig", keep_default_na=False, usecols=cols)


def ler_camara(prop, aut):
    """Uma linha por (deputado, projeto) de PL/PLP/PEC: id do deputado, id do projeto e se virou norma juridica."""
    p = _csv(prop, ["id", "siglaTipo", "ultimoStatus_descricaoSituacao"])
    p = p[p["siglaTipo"].isin(TIPOS)]
    a = _csv(aut, ["idProposicao", "idDeputadoAutor"])
    a = a[a["idDeputadoAutor"] != ""]
    m = a.merge(p, left_on="idProposicao", right_on="id")
    return pd.DataFrame(dict(dep=m["idDeputadoAutor"], prop=m["idProposicao"],
                             aprovada=m["ultimoStatus_descricaoSituacao"].map(_norma)))


def _norma(situacao):
    s = cota.norm(situacao)
    return s.startswith("TRANSFORMAD") and "NORMA JURIDICA" in s


def contar_camara(anos, cache):
    """{id do deputado: (apresentados, aprovados)} de todos os deputados autores nos anos pedidos; None se nao veio."""
    partes = []
    for ano in anos:
        prop = baixar(CAMARA_PROP.format(ano=ano), Path(cache) / f"camara_proposicoes_{ano}.csv")
        aut = baixar(CAMARA_AUT.format(ano=ano), Path(cache) / f"camara_proposicoes_autores_{ano}.csv")
        if prop and aut:
            try:
                partes.append(ler_camara(prop, aut))
            except Exception as ex:
                print(f"[aviso] projetos: Camara {ano} ilegivel ({ex!r})", file=sys.stderr)
    if not partes:
        return None
    df = pd.concat(partes, ignore_index=True).drop_duplicates(["dep", "prop"])
    g = df.groupby("dep")["aprovada"].agg(["size", "sum"])
    return {d: (int(r["size"]), int(r["sum"])) for d, r in g.iterrows()}


def senadores():
    """[(codigo, {nomes normalizados})] dos senadores em exercicio; None se a API nao respondeu."""
    d = _json(SENADO_LISTA)
    try:
        lista = d["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
    except (TypeError, KeyError):
        return None
    out = []
    for p in lista if isinstance(lista, list) else [lista]:
        i = p.get("IdentificacaoParlamentar") or {}
        if i.get("CodigoParlamentar"):
            out.append((str(i["CodigoParlamentar"]),
                        {cota.norm(i.get("NomeParlamentar")), cota.norm(i.get("NomeCompletoParlamentar"))} - {""}))
    return out


def contar_senado(ini, pausa=0.3):
    """{codigo: (apresentados, aprovados, {nomes})} dos senadores em exercicio desde `ini` (AAAA-MM-DD)."""
    lista = senadores()
    if lista is None:
        return None
    out = {}
    for cod, nomes in lista:
        d = _json(SENADO_PROC.format(cod=cod, ini=ini))
        if isinstance(d, list):
            ids = {x.get("id") for x in d}
            aprov = {x.get("id") for x in d if _norma(x.get("situacaoAtual"))}
            out[cod] = (len(ids), len(aprov), nomes)
        time.sleep(pausa)
    return out or None


def corte(aprovados):
    """Menor numero de aprovados que entra nos 10% de cima da casa (empates entram); nunca menos de 1."""
    v = sorted(aprovados, reverse=True)
    if not v:
        return math.inf
    return max(v[max(math.ceil(len(v) * FATIA), 1) - 1], 1)


def link_camara(dep, ini, fim):
    q = f"autores.ideCadastro: {dep} AND dataApresentacao:[{ini} TO {fim}]"
    return LINK_CAMARA + urllib.parse.urlencode(dict(contextoBusca="BuscaProposicoes", pagina=1, order="data",
                                                     abaEspecifica="true", q=q))


def coletar(pessoas, anos, cache, camara=None, senado=None):
    """pessoas: {chave: dict(nome, nome_urna, cargo, cpf)}. Devolve {chave: dict(casa, apresentados, aprovados, selo,
    link, de, ate)} e {"_fontes": {"camara": bool, "senado": bool}}. `camara`/`senado`: contagens prontas (testes)."""
    anos = list(anos)
    ini, fim = f"{anos[0]}-01-01", f"{anos[-1]}-12-31"
    alvo_dep = {k: p for k, p in pessoas.items() if "DEPUTADO FEDERAL" in cota.norm(p.get("cargo")) and p.get("cpf")}
    alvo_sen = {k: p for k, p in pessoas.items() if "SENADOR" in cota.norm(p.get("cargo"))}
    out = {}
    if alvo_dep and camara is None:
        camara = contar_camara(anos, cache)
    if alvo_sen and senado is None:
        senado = contar_senado(ini)
    if alvo_dep and camara:
        dep_cota = cota.bases(anos, cache)[0]  # cpf -> id do deputado (so aqui dentro)
        c = corte(v[1] for v in camara.values())
        for k, p in alvo_dep.items():
            ids = [i for i in dep_cota["id"][dep_cota["cpf"] == p["cpf"]] if i]
            if ids:
                ap, ok = camara.get(ids[-1], (0, 0))
                out[k] = dict(casa="camara", apresentados=ap, aprovados=ok, selo=ok >= c,
                              link=link_camara(ids[-1], ini, fim), de=anos[0], ate=anos[-1])
    if alvo_sen and senado:
        c = corte(v[1] for v in senado.values())
        for k, p in alvo_sen.items():
            nomes = {cota.norm(p.get("nome_urna")), cota.norm(p.get("nome"))} - {""}
            cod = next((cd for cd, v in senado.items() if v[2] & nomes), None)
            if cod:
                ap, ok, _ = senado[cod]
                out[k] = dict(casa="senado", apresentados=ap, aprovados=ok, selo=ok >= c,
                              link=LINK_SENADO.format(cod=cod), de=anos[0], ate=anos[-1])
    out["_fontes"] = dict(camara=bool(camara), senado=bool(senado))
    n = len(out) - 1
    print(f"Projetos de lei: {len(alvo_dep)} deputados federais e {len(alvo_sen)} senadores procurados, {n} encontrados, "
          f"{sum(1 for k, v in out.items() if k != '_fontes' and v['selo'])} com o selo {SELO}.")
    return out


def secao(r, cargo, fontes):
    """HTML da secao 'Projetos de lei' do dossie."""
    c = cota.norm(cargo)
    casa = "camara" if "DEPUTADO FEDERAL" in c else "senado" if "SENADOR" in c else None
    if casa is None:
        return ('<p class="vazio"><b>Não informado</b>: a contagem de projetos é feita só para deputados federais e '
                'senadores.</p>')
    if not r:
        if not (fontes or {}).get(casa):
            onde = "da Câmara" if casa == "camara" else "do Senado"
            return f'<p class="vazio"><b>Fonte não encontrada</b>: os dados abertos {onde} não responderam nesta execução.</p>'
        return '<p class="vazio"><b>Não informado</b>: parlamentar não encontrado nos dados abertos da casa.</p>'
    nome_casa = "Câmara dos Deputados" if r["casa"] == "camara" else "Senado Federal"
    selo = (f'<p><span class="tag selo">🐾 {SELO}</span> entre os 10% da casa com mais projetos aprovados.</p>'
            if r["selo"] else "")
    return (f'{selo}<p><b>{r["apresentados"]}</b> {"projeto apresentado" if r["apresentados"] == 1 else "projetos apresentados"}'
            f' e <b>{r["aprovados"]}</b> {"aprovado" if r["aprovados"] == 1 else "aprovados"} (transformados em norma '
            f'jurídica) de {r["de"]} a {r["ate"]}. <a href="{e(r["link"])}" target="_blank" rel="noopener">Ver a lista '
            f'no site da {nome_casa}</a></p>')
