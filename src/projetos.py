"""Projetos apresentados e aprovados por deputados federais e senadores nos ultimos 4 anos (PL, PLP e PEC, como
autor ou coautor). Aprovado = transformado em norma juridica. Selo "Mao na massa": os 10% de cada casa com mais
projetos aprovados. Fontes oficiais e gratuitas:
  Camara: arquivos abertos anuais https://dadosabertos.camara.leg.br/arquivos/proposicoes(Autores)/csv/
          (o id do deputado liga com o CPF pela cota parlamentar, so aqui dentro)
  Senado: API de Dados Abertos https://legis.senado.leg.br/dadosabertos/processo (uma consulta por senador)
O CPF nunca vai para o site; so contagens e links para conferir na fonte."""
import datetime as dt, html, io, json, math, sys, time, urllib.parse, urllib.request
from pathlib import Path
import pandas as pd
import cifra, cota
from cache import resultados, resumo_fechado, resumo_log
from collections import Counter

VERSAO_PROJETOS = 1  # mude ao alterar a leitura: invalida as listas guardadas dos anos fechados

CAMARA_PROP = "https://dadosabertos.camara.leg.br/arquivos/proposicoes/csv/proposicoes-{ano}.csv"
CAMARA_AUT = "https://dadosabertos.camara.leg.br/arquivos/proposicoesAutores/csv/proposicoesAutores-{ano}.csv"
SENADO_LISTA = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual"
SENADO_PROC = "https://legis.senado.leg.br/dadosabertos/processo?codigoParlamentarAutor={cod}&sigla=PL,PLP,PEC&dataInicioApresentacao={ini}"
LINK_CAMARA = "https://www.camara.leg.br/busca-portal?"
LINK_SENADO = "https://www25.senado.leg.br/web/atividade/materias/-/materia/autor/{cod}/p/1"
TIPOS = {"PL", "PLP", "PEC"}
FATIA = 0.10  # selo: os 10% de cada casa com mais projetos aprovados (desempate: mais apresentados)
SELO = "Pata na massa"
UA = "alerta-patrimonial/1.0"
e = html.escape


def baixar(url, dest):
    return cifra.baixar(url, dest, cab={"User-Agent": UA})


def _json(url, timeout=60, tentativas=3):
    """JSON da URL; None se falhar. O Senado responde 503 ou corta a resposta de vez em quando: tenta de novo."""
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as ex:
            if n == tentativas - 1:
                print(f"[aviso] {url} indisponivel: {ex}", file=sys.stderr)
                return None
            time.sleep(2 + 4 * n)


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
    """{id do deputado: (apresentados, aprovados)} de todos os deputados autores nos anos pedidos; None se nao veio.
    Ano fechado (#48): a lista (deputado, projeto, aprovado) fica guardada cifrada com o sha256 dos dois CSVs; os CSVs
    daquele ano nao sao guardados e so sao baixados de novo a cada 30 dias (cache.CONFERIR_S: um projeto antigo pode
    virar lei), e relidos so se o conteudo mudou. O ano atual e sempre relido."""
    partes, atual = [], dt.date.today().year
    guardados = resultados(cache, "projetos_camara", 400 * 86400)
    origens = Counter()
    for ano in anos:
        fechado = guardados is not None and int(ano) < atual
        arqs = [Path(cache) / f"camara_proposicoes_{ano}.csv", Path(cache) / f"camara_proposicoes_autores_{ano}.csv"]
        try:
            if fechado:
                def brutos():  # so a memoria: o bruto do ano fechado nao vai para o actions/cache
                    prop = baixar(CAMARA_PROP.format(ano=ano), None)
                    return prop and (prop, baixar(CAMARA_AUT.format(ano=ano), None))
                d, origem = resumo_fechado(guardados, (VERSAO_PROJETOS, "camara", int(ano)), brutos,
                                           lambda prop, aut: ler_camara(prop, aut).to_dict("list"))
                for a in arqs:  # CSVs brutos antigos: ~77 MB por ano a menos no actions/cache
                    for p in (a, Path(str(a) + ".modificado")):
                        p.unlink(missing_ok=True)
                if d is None:
                    continue
                origens[origem] += 1
                partes.append(pd.DataFrame(d))
            else:
                prop, aut = baixar(CAMARA_PROP.format(ano=ano), arqs[0]), baixar(CAMARA_AUT.format(ano=ano), arqs[1])
                if prop and aut:
                    partes.append(ler_camara(prop, aut))
        except Exception as ex:
            print(f"[aviso] projetos: Camara {ano} ilegivel ({ex!r})", file=sys.stderr)
    resumo_log("Projetos da Camara", origens)
    if not partes:
        return None
    df = pd.concat(partes, ignore_index=True).drop_duplicates(["dep", "prop"])
    g = df.groupby("dep")["aprovada"].agg(["size", "sum"])
    return {d: (int(r["size"]), int(r["sum"])) for d, r in g.iterrows()}


_LISTA_SENADO = []


def lista_senado():
    """[dict(cod, nome, nome_completo, partido, uf, nomes)] dos senadores em exercicio, lida uma vez por execucao;
    None se a API nao respondeu."""
    if _LISTA_SENADO:
        return _LISTA_SENADO[0]
    d = _json(SENADO_LISTA)
    try:
        lista = d["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
    except (TypeError, KeyError):
        return None
    out = []
    for p in lista if isinstance(lista, list) else [lista]:
        i = p.get("IdentificacaoParlamentar") or {}
        if i.get("CodigoParlamentar"):
            out.append(dict(cod=str(i["CodigoParlamentar"]), nome=i.get("NomeParlamentar") or "",
                            nome_completo=i.get("NomeCompletoParlamentar") or "",
                            partido=i.get("SiglaPartidoParlamentar") or "", uf=i.get("UfParlamentar") or "",
                            nomes={cota.norm(i.get("NomeParlamentar")), cota.norm(i.get("NomeCompletoParlamentar"))} - {""}))
    _LISTA_SENADO.append(out)
    return out


def senadores():
    """[(codigo, {nomes normalizados})] dos senadores em exercicio; None se a API nao respondeu."""
    lista = lista_senado()
    return None if lista is None else [(s["cod"], s["nomes"]) for s in lista]


def _processos_senado(cod, ini, fim=None):
    """(ids, ids aprovados) dos projetos do senador apresentados de `ini` a `fim`; None se a API nao respondeu."""
    d = _json(SENADO_PROC.format(cod=cod, ini=ini) + (f"&dataFimApresentacao={fim}" if fim else ""))
    if not isinstance(d, list):
        return None
    return sorted({str(x.get("id")) for x in d}), sorted({str(x.get("id")) for x in d if _norma(x.get("situacaoAtual"))})


def contar_senado(ini, pausa=0.3, cache=None):
    """{codigo: (apresentados, aprovados, {nomes})} dos senadores em exercicio desde `ini` (AAAA-MM-DD).
    Com `cache` (#48): os anos fechados de cada senador ficam guardados cifrados por 30 dias e so o ano atual e
    consultado a cada execucao; se a API falhar, vale a ultima resposta guardada (30 dias)."""
    lista = senadores()
    if lista is None:
        return None
    atual = dt.date.today().year
    guardados = resultados(cache, "projetos_senado", 30 * 86400) if cache else None
    out, falhas = {}, 0
    for cod, nomes in lista:
        partes, ok = [], True
        periodos = ([(ini, f"{atual - 1}-12-31", "passado")] if int(ini[:4]) < atual else []) + [(f"{atual}-01-01", None, "atual")]
        for de, ate, rot in periodos:
            k = (VERSAO_PROJETOS, "senado", cod, de, rot)
            g = guardados.get(k) if guardados and rot == "passado" else None
            if g is None:
                g = _processos_senado(cod, de, ate)
                time.sleep(pausa)
                if g is not None and guardados:
                    guardados.set(k, g)
                elif g is None and guardados:  # API fora: a ultima resposta guardada (ate 30 dias)
                    g = guardados.get(k)
            if g is None:
                ok = False
                break
            partes.append(g)
        if not ok:
            falhas += 1
            continue
        ids = set().union(*(set(p[0]) for p in partes))  # a API pode ignorar a data final: a uniao nao duplica
        aprov = set().union(*(set(p[1]) for p in partes))
        out[cod] = (len(ids), len(aprov), nomes)
    if falhas:
        print(f"[aviso] projetos: {falhas} senador(es) sem resposta do Senado nem copia guardada", file=sys.stderr)
    return out or None


def corte(valores):
    """Menor valor que entra nos 10% de cima da casa (empates entram); sem nenhum aprovado ninguem entra.
    Valor = aprovados ou (aprovados, apresentados): com a tupla, o empate nos aprovados e desfeito por quem apresentou
    mais (sem isso, um corte em 1 aprovado dava o selo a ~26% da Camara, pelas PECs com muitos coautores)."""
    v = sorted(valores, reverse=True)
    if not v:
        return math.inf
    c = v[max(math.ceil(len(v) * FATIA), 1) - 1]
    if isinstance(c, tuple):
        return c if c[0] >= 1 else (1, 0)
    return max(c, 1)


def tem_selo(aprovados, apresentados, c):
    """True se (aprovados, apresentados) alcanca o corte da casa (corte)."""
    if c == math.inf or not aprovados:
        return False
    return (aprovados, apresentados or 0) >= c if isinstance(c, tuple) else aprovados >= c


def link_camara(dep, ini, fim):
    q = f"autores.ideCadastro: {dep} AND dataApresentacao:[{ini} TO {fim}]"
    return LINK_CAMARA + urllib.parse.urlencode(dict(contextoBusca="BuscaProposicoes", pagina=1, order="data",
                                                     abaEspecifica="true", q=q))


def cortes(camara, senado, membros=None):
    """Corte do selo em cada casa. Com `membros` ({"camara": ids, "senado": codigos} de quem esta em exercicio), so
    eles entram na conta dos 10%; quem esta em exercicio sem projeto conta como zero."""
    def aprov(cont, casa):  # (aprovados, apresentados) de cada um
        if not cont:
            return []
        if membros and membros.get(casa):
            return [(cont.get(m, (0, 0))[1], cont.get(m, (0, 0))[0]) for m in membros[casa]]
        return [(v[1], v[0]) for v in cont.values()]
    return dict(camara=corte(aprov(camara, "camara")), senado=corte(aprov(senado, "senado")))


def coletar(pessoas, anos, cache, camara=None, senado=None, membros=None):
    """pessoas: {chave: dict(nome, nome_urna, cargo, cpf)}. Devolve {chave: dict(casa, apresentados, aprovados, selo,
    link, de, ate)} e {"_fontes": {"camara": bool, "senado": bool}}. `camara`/`senado`: contagens prontas (as mesmas
    da lista de parlamentares, ou de testes); `membros`: quem esta em exercicio, para o corte do selo."""
    anos = list(anos)
    ini, fim = f"{anos[0]}-01-01", f"{anos[-1]}-12-31"
    alvo_dep = {k: p for k, p in pessoas.items() if "DEPUTADO FEDERAL" in cota.norm(p.get("cargo")) and p.get("cpf")}
    alvo_sen = {k: p for k, p in pessoas.items() if "SENADOR" in cota.norm(p.get("cargo"))}
    out = {}
    if alvo_dep and camara is None:
        camara = contar_camara(anos, cache)
    if alvo_sen and senado is None:
        senado = contar_senado(ini, cache=cache)
    cs = cortes(camara, senado, membros)
    if alvo_dep and camara:
        dep_cota = cota.bases(anos, cache)[0]  # cpf -> id do deputado (so aqui dentro)
        c = cs["camara"]
        for k, p in alvo_dep.items():
            ids = [i for i in dep_cota["id"][dep_cota["cpf"] == p["cpf"]] if i]
            if ids:
                ap, ok = camara.get(ids[-1], (0, 0))
                out[k] = dict(casa="camara", apresentados=ap, aprovados=ok, selo=tem_selo(ok, ap, c),
                              link=link_camara(ids[-1], ini, fim), de=anos[0], ate=anos[-1])
    if alvo_sen and senado:
        c = cs["senado"]
        for k, p in alvo_sen.items():
            nomes = {cota.norm(p.get("nome_urna")), cota.norm(p.get("nome"))} - {""}
            cod = next((cd for cd, v in senado.items() if v[2] & nomes), None)
            if cod:
                ap, ok, _ = senado[cod]
                out[k] = dict(casa="senado", apresentados=ap, aprovados=ok, selo=tem_selo(ok, ap, c),
                              link=LINK_SENADO.format(cod=cod), de=anos[0], ate=anos[-1])
    out["_fontes"] = dict(camara=bool(camara), senado=bool(senado))
    n = len(out) - 1
    print(f"Projetos de lei: {len(alvo_dep)} deputados federais e {len(alvo_sen)} senadores procurados, {n} encontrados, "
          f"{sum(1 for k, v in out.items() if k != '_fontes' and v['selo'])} com o selo {SELO}.")
    return out


def secao(r, cargo, fontes):
    """HTML da secao 'Projetos de lei' do dossie."""
    c = cota.norm(cargo)  # com dado, vale a casa onde a pessoa esta em exercicio (o cargo do TSE pode ser outro)
    casa = r["casa"] if r else "camara" if "DEPUTADO FEDERAL" in c else "senado" if "SENADOR" in c else None
    if casa is None:
        return ('<p class="vazio"><b>Não informado</b>: a contagem de projetos é feita só para deputados federais e '
                'senadores.</p>')
    if not r:
        if not (fontes or {}).get(casa):
            onde = "da Câmara" if casa == "camara" else "do Senado"
            return f'<p class="vazio"><b>Fonte não encontrada</b>: os dados abertos {onde} não responderam nesta execução.</p>'
        return '<p class="vazio"><b>Não informado</b>: a pessoa não está entre os parlamentares em exercício ou não foi encontrada nos dados abertos da casa.</p>'
    nome_casa = "Câmara dos Deputados" if r["casa"] == "camara" else "Senado Federal"
    selo = (f'<p><span class="tag selo">🐾 {SELO}</span> entre os 10% da casa com mais projetos aprovados.</p>'
            if r["selo"] else "")
    return (f'{selo}<p><b>{r["apresentados"]}</b> {"projeto apresentado" if r["apresentados"] == 1 else "projetos apresentados"}'
            f' e <b>{r["aprovados"]}</b> {"aprovado" if r["aprovados"] == 1 else "aprovados"} (transformados em norma '
            f'jurídica) de {r["de"]} a {r["ate"]}. <a href="{e(r["link"])}" target="_blank" rel="noopener">Ver a lista '
            f'no site da {nome_casa}</a></p>')
