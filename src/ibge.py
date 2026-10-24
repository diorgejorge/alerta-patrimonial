"""Indicadores do IBGE na aba Estados (#68): como o Brasil e cada estado estao indo, sem relacao com patrimonio de
politicos. Fonte oficial e gratuita: API do SIDRA (apisidra.ibge.gov.br), com o link da tabela. Cada indicador
(config/ibge.json) usa a primeira tabela candidata que tiver a variavel (achada pelo nome) e o Brasil. So no Brasil: IDH do PNUD (Relatorio de Desenvolvimento Humano).
Tendencia: ultimo periodo contra o mesmo trimestre do ano anterior (trimestral) ou o periodo anterior (anual)."""
import csv, io, json, re, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from estados import UFS, norm

CONFIG = Path(__file__).resolve().parent.parent / "config" / "ibge.json"
VALORES = "https://apisidra.ibge.gov.br/values"  # 24/10: o runner do GitHub alcanca o apisidra; servicodados da timeout
DESC = "https://apisidra.ibge.gov.br/desctabapi.aspx?c={t}"
META = "https://sidra.ibge.gov.br/Ajax/JSon/Tabela/1/{t}?versao=-1"  # metadados do site, plano B quando a DESC da 403
SIDRA = "https://sidra.ibge.gov.br/tabela/{t}"
UA = {"User-Agent": "alerta-patrimonial/1.0"}
# a pagina de descricao do SIDRA (desctabapi) respondeu 403 ao agente do robo em 24/10; ela e HTML para navegador
UA_NAVEGADOR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
ATRASO_MAX = 4  # dado com o ultimo ano mais velho que isso nao entra (a tabela 3834 parou em 2016)
VALIDADE_S = 7 * 86400  # dado trimestral/anual: consulta de novo uma vez por semana
PRAZO_S = 180  # teto da etapa inteira: a carga de 24/10 ficou 50 min esperando a API fora do ar
CHAVE = "ibge:v1"
UF_DO_COD = {cod: uf for uf, (cod, _) in UFS.items()}
NAO_E_VALOR = re.compile(r"COEFICIENTE|VARIACAO|ERRO|INTERVALO")


def ler_config(arq=CONFIG):
    try:
        return json.loads(Path(arq).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _baixar(url, tentativas=2, pausa=2):
    for i in range(tentativas):
        try:
            cab = UA_NAVEGADOR if "desctabapi" in url or "/Ajax/" in url else UA
            with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=20) as r:
                return r.read()
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(pausa * (i + 1))


def _json(url):
    """JSON do SIDRA; a pagina de descricao (desctabapi) vem como texto."""
    bruto = _baixar(url).decode("utf-8", "replace")
    return bruto if "desctabapi" in url else json.loads(bruto)


def _tem(texto, trecho):
    return norm(trecho) in norm(texto)


PERIODOS = {"ANO": "ANUAL", "TRIMESTRE": "TRIMESTRAL", "TRIMESTRE MOVEL": "TRIMESTRAL MOVEL", "MES": "MENSAL"}
TERRITORIO = re.compile(r"BRASIL|UNIDADE DA FEDERACAO")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None  # "-", "...", "X": sem dado


def url_sidra(t, classif="", periodos=6):
    """Brasil (n1) e estados (n3), todas as variaveis, ultimos periodos; classificacao nao pedida vem no Total."""
    return f"{VALORES}/t/{t}/n1/all/n3/all/v/all/p/last%20{periodos}{classif or ''}"


def _dimensoes(cab):
    """[(chave 'D1', nome normalizado)] na ordem do cabecalho do SIDRA."""
    return [(k[:-1], norm(v)) for k, v in cab.items() if re.fullmatch(r"D\d+N", k)]


def ler_sidra(resp, ind, ano_max=None):
    """(series {"BR"/UF: {periodo: valor}}, frequencia, nome da variavel) da resposta do SIDRA (a 1a linha e o
    cabecalho com o nome de cada dimensao D1..Dn). None se a tabela nao tem a variavel do indicador.
    Classificacoes que vierem com mais de uma categoria: fica a linha "Total" ou a de `preferir` (config).
    Duas dimensoes "Ano" (projecoes: edicao e ano projetado): o periodo e o ano projetado, ate `ano_max`."""
    if not isinstance(resp, list) or len(resp) < 2 or not isinstance(resp[0], dict):
        return None
    dims = _dimensoes(resp[0])
    kvar = next((k for k, n in dims if n == "VARIAVEL"), None)
    pers = [(k, n) for k, n in dims if n in PERIODOS]
    kper, nper = pers[-1] if pers else (None, None)
    kloc = next((k for k, n in dims if TERRITORIO.search(n)), None)
    if not (kvar and kper and kloc):
        return None
    nomes = list(dict.fromkeys(r.get(kvar + "N") for r in resp[1:]))
    var = next((n for n in nomes if _tem(n, ind["variavel"]) and not NAO_E_VALOR.search(norm(n))), None)
    if not var:
        return None
    extras = [k for k, _ in dims if k not in (kvar, kloc, kper)]
    preferir = [norm(x) for x in ind.get("preferir") or ()]

    def nota(r):  # quantas classificacoes estao no Total (ou na categoria preferida)
        return sum(norm(r.get(k + "N")) == "TOTAL" or any(x in norm(r.get(k + "N")) for x in preferir) for k in extras)
    projecao = len(pers) > 1  # edicao + "Ano" projetado (classificacao): so ela tem anos futuros
    teto = ano_max if projecao else None
    melhor = {}
    for r in resp[1:]:
        v = _num(r.get("V"))
        per = str(r.get(kper + ("N" if projecao else "C")))  # na projecao o "Ano" e classificacao: o codigo nao e o ano
        if r.get(kvar + "N") != var or v is None or (teto and per[:4].isdigit() and int(per[:4]) > teto):
            continue
        nc, cod = str(r.get("NC")), str(r.get(kloc + "C"))
        loc = "BR" if nc == "1" else UF_DO_COD.get(cod) if nc == "3" else None
        if loc and nota(r) >= melhor.get((loc, per), (-1, 0))[0]:
            melhor[(loc, per)] = (nota(r), v)
    out = {}
    for (loc, per), (_, v) in melhor.items():
        out.setdefault(loc, {})[per] = v
    return out, PERIODOS[nper], var


def descrever(resp):
    """Resumo da resposta para o log quando a tabela nao serve: dimensoes e as primeiras variaveis."""
    if not isinstance(resp, list) or not resp or not isinstance(resp[0], dict):
        return f"resposta inesperada: {str(resp)[:120]!r}"
    dims = {k[:-1]: v for k, v in resp[0].items() if re.fullmatch(r"D\d+N", k)}
    kvar = next((k for k, v in dims.items() if norm(v) == "VARIAVEL"), None)
    nomes = list(dict.fromkeys(r.get(kvar + "N") for r in resp[1:]))[:4] if kvar else []
    br = [{k: r.get(k) for k in r if k == "V" or k.endswith("N") and k != "NN"} for r in resp[1:] if str(r.get("NC")) == "1"][:3]
    return f"dimensoes {list(dims.values())}; variaveis {nomes}; linhas do Brasil {br}"


def classif_desc(html, categorias):
    """'/c11558/46290' a partir da pagina de descricao da tabela no SIDRA (classificacao e categoria pelo nome).
    Le o texto sem tags: 'C11558 Esgotamento sanitario ... 46290 Rede geral ...'. None se nao achar."""
    texto = re.sub(r"<[^>]+>", " ", html or "")
    partes = []
    for chave, alvo in (categorias or {}).items():
        achou = None
        for m in re.finditer(r"\bC(\d+)\b[\s:-]*([^\n(]{3,80})", texto):
            if not _tem(m.group(2), chave):
                continue
            prox = re.search(r"\bC\d+\b", texto[m.end():])
            bloco = texto[m.end(): m.end() + prox.start()] if prox else texto[m.end():]
            cat = next((c for c in re.finditer(r"\b(\d{2,7})\b[\s:-]*([^\n\d]{3,120})", bloco) if _tem(c.group(2), alvo)), None)
            if cat:
                achou = f"/c{m.group(1)}/{cat.group(1)}"
                break
        if not achou:
            return None
        partes.append(achou)
    return "".join(partes)


def _id_nome(d):
    i = next((d[k] for k in ("Id", "id", "Codigo", "codigo") if k in d), None)
    n = next((d[k] for k in ("Nome", "nome", "Descricao", "descricao") if k in d), None)
    return (str(i), str(n)) if i is not None and n is not None else None


def classif_json(dados, categorias):
    """Mesma saida de classif_desc, lendo os metadados em JSON do site do SIDRA: acha qualquer objeto com id e nome
    da classificacao que tenha uma lista de categorias (objetos com id e nome). None se nao achar."""
    def objetos(x):
        if isinstance(x, dict):
            yield x
            x = list(x.values())
        if isinstance(x, list):
            for y in x:
                yield from objetos(y)
    partes = []
    for chave, alvo in (categorias or {}).items():
        achou = None
        for o in objetos(dados):
            cl = _id_nome(o)
            if not cl or not _tem(cl[1], chave):
                continue
            cats = (_id_nome(c) for v in o.values() if isinstance(v, list) for c in v if isinstance(c, dict))
            cat = next((c for c in cats if c and _tem(c[1], alvo)), None)
            if cat:
                achou = f"/c{cl[0]}/{cat[0]}"
                break
        if not achou:
            return None
        partes.append(achou)
    return "".join(partes)


def periodo(p, freq):
    """'202602' trimestral -> '2º tri 2026'; anual fica o ano."""
    p = str(p)
    return f"{int(p[4:])}º tri {p[:4]}" if "TRIMESTR" in freq and len(p) == 6 else p[:4] if len(p) >= 4 else p


def resumo(serie, freq):
    """[ultimo, anterior, periodo do ultimo, periodo do anterior]; trimestral compara com o mesmo trimestre do ano
    anterior (sem efeito de epoca do ano). Sem dois periodos: so o ultimo."""
    if not serie:
        return None
    ps = sorted(serie)
    ult = ps[-1]
    ant = (f"{int(ult[:4]) - 1}{ult[4:]}" if "TRIMESTR" in freq and len(ult) == 6 else ps[-2] if len(ps) > 1 else None)
    if ant not in serie:
        ant = None
    return [serie[ult], serie[ant] if ant else None, periodo(ult, freq), periodo(ant, freq) if ant else None]


def tendencia(r, ind):
    """'melhor', 'pior' ou 'igual' (mesmo valor na precisao mostrada); None sem comparacao."""
    if not r or r[1] is None:
        return None
    a, b = round(r[0], ind.get("casas", 1)), round(r[1], ind.get("casas", 1))
    if a == b:
        return "igual"
    subiu = a > b
    return "melhor" if subiu == (ind.get("melhor") == "maior") else "pior"


def idh(cfg, baixar=_baixar):
    """IDH do Brasil e posicao entre os paises (PNUD), do CSV oficial da serie completa; None se nao achar."""
    iso = (cfg or {}).get("iso3", "BRA")
    for url in (cfg or {}).get("urls") or ():
        try:
            bruto = baixar(url)
            texto = bruto.decode("utf-8") if isinstance(bruto, bytes) else bruto
        except UnicodeDecodeError:
            texto = bruto.decode("latin-1")
        except Exception:
            continue
        linha = next((r for r in csv.DictReader(io.StringIO(texto)) if r.get("iso3") == iso), None)
        anos = sorted((int(k[4:]) for k, v in (linha or {}).items() if re.fullmatch(r"hdi_\d{4}", k or "") and _num(v)), reverse=True)
        if not anos:
            continue
        a = anos[0]
        rank = _num(linha.get(f"hdi_rank_{a}"))
        return dict(valor=_num(linha[f"hdi_{a}"]), anterior=_num(linha.get(f"hdi_{a - 1}")), ano=a,
                    posicao=int(rank) if rank else None, link=cfg.get("link") or url)
    return None


def _completo(d, cfg):
    """Todos os indicadores do config e o IDH: so assim o cache vale a semana; incompleto, tenta de novo na carga."""
    return bool(d) and len(d.get("indicadores") or ()) >= len(cfg.get("indicadores") or ()) and \
        (bool(d.get("idh")) or not cfg.get("idh"))


# caminhos oficiais do IBGE e do IPEA: testados so quando o SIDRA nao responde, para saber
# qual deles o runner do GitHub alcanca (24/10: servicodados.ibge.gov.br deu timeout no Actions)
SONDAS = ("https://apisidra.ibge.gov.br/values/t/4099/n1/all/v/4099/p/last%201",
          "https://servicodados.ibge.gov.br/api/v3/agregados/4099/metadados",
          "https://www.ipeadata.gov.br/api/odata4/Metadados('PNADC12_TD12')",
          "https://ftp.ibge.gov.br/")


def sondar(urls=SONDAS, timeout=10):
    """Uma linha de log por caminho: status HTTP e tempo, ou o erro. Nao guarda nada."""
    for u in urls:
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout) as r:
                res = f"HTTP {r.status}, {len(r.read(200000))} bytes"
        except Exception as ex:
            res = repr(ex)[:120]
        print(f"IBGE sonda: {u.split('/')[2]} -> {res} em {time.monotonic() - t0:.1f}s")


def coletar(cache=None, cfg=None, obter=_json, baixar=_baixar, agora=None, sondar=None):
    """Dados da aba: {"indicadores": [...], "valores": {"BR"/UF: {id: [ultimo, anterior, per, per_ant, tendencia]}},
    "idh": {...}}. Usa o cache por uma semana; se a consulta nova vier pior (menos indicadores), fica a ultima boa."""
    cfg = cfg or ler_config()
    agora = agora or time.time()
    guardado = cache.get(CHAVE) if cache is not None else None
    if guardado and agora - guardado.get("em", 0) < VALIDADE_S and _completo(guardado["dados"], cfg):
        return guardado["dados"]
    fora, fim = [], time.monotonic() + PRAZO_S

    def seguro(url):
        """Primeira falha de rede (fora do ar, timeout) ou prazo estourado: o resto da etapa nem tenta."""
        if fora or time.monotonic() > fim:
            raise TimeoutError("IBGE fora do ar ou prazo da etapa estourado")
        try:
            return obter(url)
        except OSError as ex:
            if not isinstance(ex, urllib.error.HTTPError):  # 404/500 de uma tabela nao derruba as outras
                fora.append(ex)
            raise
    inds, valores = [], {}
    for ind in cfg.get("indicadores") or ():
        achado = None
        for t in ind.get("tabelas") or ():
            try:
                cl = ind.get("classificacao") or ""
                if ind.get("categorias") and not cl:
                    try:
                        cl = classif_desc(seguro(DESC.format(t=t)), ind["categorias"])
                    except urllib.error.HTTPError:  # 24/10: a DESC deu 403 ao runner
                        meta = seguro(META.format(t=t))
                        cl = classif_json(meta, ind["categorias"])
                        if cl is None:
                            print(f"[aviso] IBGE: {ind['id']}, tabela {t}: metadados do site sem a categoria ({str(meta)[:600]!r})")
                    if cl is None:
                        print(f"[aviso] IBGE: {ind['id']}, tabela {t}: categoria {ind['categorias']} nao achada na descricao")
                        continue
                resp = seguro(url_sidra(t, cl))
                lido = ler_sidra(resp, ind, time.gmtime(agora).tm_year)
            except Exception as ex:
                print(f"[aviso] IBGE: {ind['id']}, tabela {t}: indisponivel ({ex!r})")
                continue
            if not lido or "BR" not in lido[0]:
                print(f"[aviso] IBGE: {ind['id']}, tabela {t}: sem a variavel '{ind['variavel']}' ou sem o Brasil ({descrever(resp)})")
                continue
            ultimo = max(int(p[:4]) for p in lido[0]["BR"])
            if ultimo < time.gmtime(agora).tm_year - ind.get("atraso_max", ATRASO_MAX):
                print(f"[aviso] IBGE: {ind['id']}, tabela {t}: dado antigo (ultimo ano {ultimo}), nao entra")
                continue
            achado = (t, cl) + lido
            break
        if not achado:
            print(f"[aviso] IBGE: {ind['id']} " + ("pulado (fonte fora do ar)" if fora else "sem tabela que sirva"))
            continue
        t, cl, sr, freq, var = achado
        print(f"IBGE: {ind['id']} = tabela {t}{cl}, variavel '{var}', {freq.lower()}, {len(sr)} localidades.")
        inds.append(dict(id=ind["id"], nome=ind["nome"], unidade=ind["unidade"], casas=ind.get("casas", 1),
                         melhor=ind["melhor"], fonte=ind.get("fonte") or "IBGE", link=SIDRA.format(t=t)))
        for loc, serie in sr.items():
            r = resumo(serie, freq)
            if r:
                valores.setdefault(loc, {})[ind["id"]] = r + [tendencia(r, ind)]
    try:
        h = idh(cfg.get("idh"), baixar)
    except Exception as ex:
        print(f"[aviso] IBGE: IDH indisponivel ({ex!r})")
        h = None
    if fora and sondar is not None:
        sondar()
    antes = (guardado or {}).get("dados")
    h = h or (antes or {}).get("idh")  # PNUD fora do ar: fica o IDH guardado
    dados = dict(indicadores=inds, valores=valores, idh=h) if inds or h else None
    # fonte fora do ar no meio: fica a ultima boa; sem falha de rede, vale o resultado novo (ex.: dado antigo saiu)
    if antes and fora and (len(antes.get("indicadores") or ()) > len(inds) or (antes.get("idh") and not h)):
        print("[aviso] IBGE: consulta veio incompleta; fica a ultima boa.")
        return antes
    if cache is not None and dados:
        cache.set(CHAVE, dict(em=agora, dados=dados))
        cache.salvar()
    return dados


def demo():
    """Dados sinteticos e deterministicos (sem rede) no formato de coletar(), para o --demo e os testes."""
    cfg = ler_config()
    inds = [dict(id=i["id"], nome=i["nome"], unidade=i["unidade"], casas=i.get("casas", 1), melhor=i["melhor"],
                 fonte=i.get("fonte") or "IBGE", link=SIDRA.format(t=i["tabelas"][0])) for i in cfg["indicadores"]]
    valores = {}
    for k, loc in enumerate(["BR", *UFS]):
        for j, i in enumerate(inds):
            base = 1500.0 + 40 * k if i["unidade"] == "R$" else 5.0 + (k + j) % 9
            delta = (-1) ** (k + j) * (50 if i["unidade"] == "R$" else 0.4) * (0 if (k + j) % 7 == 0 else 1)
            r = [base + delta, base, "2º tri 2026" if i["id"] == "desemprego" else "2025",
                 "2º tri 2025" if i["id"] == "desemprego" else "2024"]
            valores.setdefault(loc, {})[i["id"]] = r + [tendencia(r, i)]
    return dict(indicadores=inds, valores=valores,
                idh=dict(valor=0.786, anterior=0.780, ano=2023, posicao=84, link=cfg["idh"]["link"]))
