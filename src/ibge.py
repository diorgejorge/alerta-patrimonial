"""Indicadores do IBGE na aba Estados (#68): como o Brasil e cada estado estao indo, sem relacao com patrimonio de
politicos. Fonte oficial e gratuita: API de agregados do IBGE (os mesmos dados do SIDRA), com o link da tabela.
Cada indicador (config/ibge.json) acha a tabela e a variavel pelo nome nos metadados, porque o numero da tabela
pode mudar entre edicoes da pesquisa. So no Brasil: IDH do PNUD (Relatorio de Desenvolvimento Humano).
Tendencia: ultimo periodo contra o mesmo trimestre do ano anterior (trimestral) ou o periodo anterior (anual)."""
import csv, io, json, re, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from estados import UFS, norm

CONFIG = Path(__file__).resolve().parent.parent / "config" / "ibge.json"
API = "https://servicodados.ibge.gov.br/api/v3/agregados"
SIDRA = "https://sidra.ibge.gov.br/tabela/{t}"
UA = {"User-Agent": "alerta-patrimonial/1.0"}
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
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return r.read()
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(pausa * (i + 1))


def _json(url):
    return json.loads(_baixar(url).decode("utf-8"))


def _tem(texto, trecho):
    return norm(trecho) in norm(texto)


def _variavel(meta, ind):
    for v in meta.get("variaveis") or ():
        if _tem(v.get("nome"), ind["variavel"]) and not NAO_E_VALOR.search(norm(v.get("nome"))):
            return v
    return None


def _classificacao(meta, ind):
    """'C2[6794]|C58[95253]': cada classificacao no Total, menos as de `categorias` (ex.: esgoto pela rede geral)."""
    partes = []
    for c in meta.get("classificacoes") or ():
        cats = c.get("categorias") or []
        alvo = next((v for k, v in (ind.get("categorias") or {}).items() if _tem(c.get("nome"), k)), None)
        cat = (next((x for x in cats if _tem(x.get("nome"), alvo)), None) if alvo else
               next((x for x in cats if norm(x.get("nome")) == "TOTAL"), None))
        if alvo and not cat:
            return None  # a categoria pedida nao existe nesta tabela
        if cat:
            partes.append(f"C{c['id']}[{cat['id']}]")
    return "|".join(partes)


def _serve(meta, ind):
    """dict(tabela, variavel, classificacao, freq) se a tabela tem a variavel e o nivel de estado (N3); senao None."""
    niveis = (meta.get("nivelTerritorial") or {}).get("Administrativo") or []
    v = _variavel(meta, ind)
    cl = _classificacao(meta, ind) if v else None
    if not v or "N3" not in niveis or cl is None:
        return None
    return dict(tabela=int(meta["id"]), variavel=int(v["id"]), classificacao=cl, nome_var=v.get("nome"),
                freq=norm((meta.get("periodicidade") or {}).get("frequencia")))


def resolver(ind, metadados):
    """Primeira das tabelas candidatas (config) que tem a variavel e o nivel de estado; loga por que cada uma nao serviu.
    (O catalogo completo de agregados nao e usado: tem varios MB e estourava o tempo da carga de 24/10.)"""
    for t in ind.get("tabelas") or ():
        try:
            meta = metadados(int(t))
        except Exception as ex:
            print(f"[aviso] IBGE: {ind['id']}, tabela {t}: metadados indisponiveis ({ex!r})")
            continue
        r = _serve(meta, ind)
        if r:
            return r
        print(f"[aviso] IBGE: {ind['id']}, tabela {t}: sem a variavel, a categoria ou o nivel de estado")
    return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None  # "-", "...", "X": sem dado


def series(resp):
    """{"BR" ou UF: {periodo: valor}} da resposta da API de agregados."""
    out = {}
    for var in resp or ():
        for res in var.get("resultados") or ():
            for s in res.get("series") or ():
                loc = s.get("localidade") or {}
                nivel = (loc.get("nivel") or {}).get("id")
                chave = "BR" if nivel == "N1" else UF_DO_COD.get(str(loc.get("id"))) if nivel == "N3" else None
                if chave:
                    vals = {p: _num(v) for p, v in (s.get("serie") or {}).items()}
                    out[chave] = {p: v for p, v in vals.items() if v is not None}
    return out


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


def url_valores(res, periodos):
    q = dict(localidades="N1[all]|N3[all]")
    if res["classificacao"]:
        q["classificacao"] = res["classificacao"]
    return f"{API}/{res['tabela']}/periodos/-{periodos}/variaveis/{res['variavel']}?" + urllib.parse.urlencode(q, safe="[]|")


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


def coletar(cache=None, cfg=None, obter=_json, baixar=_baixar, agora=None):
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
        try:
            res = resolver(ind, lambda t: seguro(f"{API}/{t}/metadados"))
            if not res:
                print(f"[aviso] IBGE: {ind['id']} " + ("pulado (fonte fora do ar)" if fora else "sem tabela que sirva"))
                continue
            sr = series(seguro(url_valores(res, 6)))
        except Exception as ex:
            print(f"[aviso] IBGE: {ind['id']} indisponivel ({ex!r})")
            continue
        if "BR" not in sr:
            print(f"[aviso] IBGE: {ind['id']} sem o valor do Brasil na tabela {res['tabela']}")
            continue
        print(f"IBGE: {ind['id']} = tabela {res['tabela']}, variavel {res['variavel']} ({res['nome_var']}), "
              f"{res['classificacao'] or 'sem classificacao'}, {len(sr)} localidades.")
        inds.append(dict(id=ind["id"], nome=ind["nome"], unidade=ind["unidade"], casas=ind.get("casas", 1),
                         melhor=ind["melhor"], fonte=ind.get("fonte") or "IBGE", link=SIDRA.format(t=res["tabela"])))
        for loc, s in sr.items():
            r = resumo(s, res["freq"])
            if r:
                valores.setdefault(loc, {})[ind["id"]] = r + [tendencia(r, ind)]
    try:
        h = idh(cfg.get("idh"), baixar)
    except Exception as ex:
        print(f"[aviso] IBGE: IDH indisponivel ({ex!r})")
        h = None
    dados = dict(indicadores=inds, valores=valores, idh=h) if inds or h else None
    antes = (guardado or {}).get("dados")
    if antes and (len(antes.get("indicadores") or ()) > len(inds) or (antes.get("idh") and not h)):
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
