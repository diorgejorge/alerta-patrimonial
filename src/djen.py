"""Processos em que a pessoa e re (polo passivo), contados nas publicacoes do Diario de Justica Eletronico Nacional
(DJEN), API publica e gratuita do CNJ - a mesma base de diarios que agregadores como o Escavador usam:
  GET https://comunicaapi.pje.jus.br/api/v1/comunicacao?nomeParte=<nome>&pagina=N&itensPorPagina=100
  -> items[] = {numero_processo, siglaTribunal, destinatarios: [{nome, polo: "A"|"P"}]}
O DJEN nao traz CPF/CNPJ das partes. Para evitar homonimos: busca pelo nome civil completo, exige o nome igual
(sem acento/caixa) no polo passivo e so aceita tribunais do estado da pessoa (TJ, TRE, TRT, TRF da regiao) ou
superiores (STF, STJ, TST, TSE, STM). A contagem cobre so processos com publicacao no DJEN, nao todos."""
import datetime as dt, json, re, sys, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path

API = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
UA = "alerta-patrimonial/1.0"
POR_PAGINA, MAX_PAGINAS, PAUSA = 100, 10, 3.2  # o DJEN aceita 20 consultas por minuto (X-RateLimit-Limit)
SUPERIORES = {"STF", "STJ", "TST", "TSE", "STM"}
TRF = {**dict.fromkeys("AC AM AP BA DF GO MA MT PA PI RO RR TO".split(), "TRF1"), "RJ": "TRF2", "ES": "TRF2",
       "SP": "TRF3", "MS": "TRF3", "RS": "TRF4", "SC": "TRF4", "PR": "TRF4",
       **dict.fromkeys("AL CE PB PE RN SE".split(), "TRF5"), "MG": "TRF6"}
TRT = {"RJ": ["TRT1"], "SP": ["TRT2", "TRT15"], "MG": ["TRT3"], "RS": ["TRT4"], "BA": ["TRT5"], "PE": ["TRT6"],
       "CE": ["TRT7"], "PA": ["TRT8"], "AP": ["TRT8"], "PR": ["TRT9"], "DF": ["TRT10"], "TO": ["TRT10"],
       "AM": ["TRT11"], "RR": ["TRT11"], "SC": ["TRT12"], "PB": ["TRT13"], "RO": ["TRT14"], "AC": ["TRT14"],
       "MA": ["TRT16"], "ES": ["TRT17"], "GO": ["TRT18"], "AL": ["TRT19"], "SE": ["TRT20"], "RN": ["TRT21"],
       "PI": ["TRT22"], "MT": ["TRT23"], "MS": ["TRT24"]}
LINK = "https://comunica.pje.jus.br/consulta"


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"^\s*\d+\s*[.)-]\s*", "", s)   # "2. FULANO" -> "FULANO"
    s = re.sub(r"\s*\(.*?\)\s*$", "", s)        # "FULANO (AGRAVADO)" -> "FULANO"
    return " ".join(re.sub(r"[^A-Z ]+", " ", s).split())


def tribunais(uf):
    """Siglas aceitas para a pessoa daquele estado (UF 'BR' = cargo nacional: so os superiores)."""
    uf = (uf or "").upper()
    if uf not in TRF:
        return set(SUPERIORES)
    tj = "TJDFT" if uf == "DF" else f"TJ{uf}"
    return SUPERIORES | {tj, f"TRE-{uf}", f"TRE{uf}", TRF[uf], *TRT.get(uf, [])}


def _pagina(nome, pagina, timeout=60):
    url = API + "?" + urllib.parse.urlencode({"nomeParte": nome, "pagina": pagina, "itensPorPagina": POR_PAGINA})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"}),
                                timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def processos_reu(nome, uf, buscar=_pagina):
    """Numeros (distintos) dos processos em que `nome` aparece no polo passivo, em tribunais aceitos; None se falhou."""
    alvo, aceitos, achados = norm(nome), tribunais(uf), set()
    if len(alvo.split()) < 2:
        return None  # nome de uma palavra so: homonimos demais
    for pagina in range(1, MAX_PAGINAS + 1):
        try:
            j = buscar(nome, pagina)
        except Exception as ex:
            print(f"[aviso] DJEN: consulta falhou ({ex!r})", file=sys.stderr)
            return None
        itens = j.get("items") or []
        for it in itens:
            if str(it.get("siglaTribunal") or "").upper().replace(" ", "") not in aceitos:
                continue
            if any(d.get("polo") == "P" and norm(d.get("nome")) == alvo for d in it.get("destinatarios") or []):
                achados.add(re.sub(r"\D", "", str(it.get("numero_processo") or "")))
        if len(itens) < POR_PAGINA or pagina * POR_PAGINA >= int(j.get("count") or 0):
            break
        time.sleep(PAUSA)
    achados.discard("")
    return achados


def contar(pessoas, cache, tempo_max=15 * 60):
    """pessoas: {chave: dict(nome, uf)}. Devolve {chave: n} (processos como re) e "_fonte" (False se o DJEN falhou
    em todas as consultas). Cache mensal em data/cache/djen.json, por nome+UF (sem CPF)."""
    arq = Path(cache) / "djen.json"
    try:
        guardado = json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        guardado = {}
    mes, fim = dt.date.today().strftime("%Y-%m"), time.monotonic() + tempo_max
    out, consultas, falhas = {}, 0, 0
    for chave, p in pessoas.items():
        k = f"{norm(p.get('nome'))}|{(p.get('uf') or '').upper()}"
        g = guardado.get(k)
        if g and g.get("mes") == mes:
            out[chave] = g["n"]
            continue
        if time.monotonic() > fim or falhas >= 5:
            continue
        r = processos_reu(p.get("nome"), p.get("uf"))
        consultas += 1
        if r is None:
            falhas += 1
            continue
        out[chave] = len(r)
        guardado[k] = dict(mes=mes, n=len(r))
        time.sleep(PAUSA)
    if consultas:
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(guardado, ensure_ascii=False), encoding="utf-8")
    print(f"DJEN: {len(out)} pessoas com contagem ({consultas} consultas, {falhas} falhas).")
    out["_fonte"] = bool(out) or consultas == 0
    return out
