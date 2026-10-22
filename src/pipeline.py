#!/usr/bin/env python3
"""Alerta patrimonial: compara o crescimento do patrimonio declarado ao TSE entre
eleicoes com a capacidade de acumulacao estimada e com o grupo de pares.
Resultado = INDICIO para acompanhamento, nao prova."""
import argparse, io, json, os, re, sys, unicodedata, urllib.request, urllib.parse, zipfile
import datetime as dt
from pathlib import Path
import pandas as pd
from dossie import gerar_dossies, empresas_do_bem, MAX_EMPRESAS, RE_CNPJ
import transparencia
import cota
from ids import Ids, varrer
import paginas

ROOT = Path(__file__).resolve().parent.parent
CACHE, DOCS, CFG = ROOT / "data" / "cache", ROOT / "docs", ROOT / "config"
ESTADO = ROOT / "data" / "estado.json"
BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
ORDEM = {"forte": 3, "atencao": 2, "informativo": 1}

# DivulgaCandContas: pagina do candidato em
#   {DIVULGA}/{REGIAO}/{UF}/{ID_ELEICAO}/{SQ_CANDIDATO}/{ANO}/{SG_UE}
# REGIAO usa a grafia do proprio site (CENTROOESTE, sem hifen; "BR" para Presidente/Vice).
# ID_ELEICAO e o id interno do site (rest/v1/eleicao/ordinarias), NAO o CD_ELEICAO dos CSVs
# (ex.: 2022 -> 2040602022; o CD_ELEICAO 546 do CSV nao abre a pagina).
DIVULGA = "https://divulgacandcontas.tse.jus.br/divulga/#/candidato"
REGIAO = {**dict.fromkeys("AC AP AM PA RO RR TO".split(), "NORTE"),
          **dict.fromkeys("AL BA CE MA PB PE PI RN SE".split(), "NORDESTE"),
          **dict.fromkeys("DF GO MT MS".split(), "CENTROOESTE"),
          **dict.fromkeys("ES MG RJ SP".split(), "SUDESTE"),
          **dict.fromkeys("PR RS SC".split(), "SUL"), "BR": "BR"}
ID_DIVULGA = {2006: "14423", 2008: "14422", 2010: "14417", 2012: "1699", 2014: "680", 2016: "2",
              2018: "2022802018", 2020: "2030402020", 2022: "2040602022", 2024: "2045202024",
              2026: "20322002026"}
ID_DIVULGA_UE = {(2020, "06050"): "2032002020"}  # Macapa/AP 2020 (eleicao adiada, id proprio)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def txt(v):
    """Texto limpo; None/NaN viram ''."""
    return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()


def link_tse(r):
    """URL da pagina do candidato no DivulgaCandContas, ou None se faltar dado."""
    uf, ue, sq = txt(r.get("uf")).upper(), txt(r.get("sg_ue")), re.sub(r"\D", "", txt(r.get("sq_candidato")))
    try:
        ano = int(r.get("ano"))
    except (TypeError, ValueError):
        return None
    if r.get("suplementar") in (True, 1) or not (uf and ue and sq):
        return None  # eleicoes suplementares tem outro id no site
    eleicao = ID_DIVULGA_UE.get((ano, ue)) or ID_DIVULGA.get(ano)
    regiao = REGIAO.get(uf)
    if not (eleicao and regiao):
        return None
    return f"{DIVULGA}/{regiao}/{uf}/{eleicao}/{sq}/{ano}/{ue}"


# ---------------------------------------------------------------- coleta TSE
def baixar(tipo, ano):
    """Zip do TSE em data/cache (guardado entre execucoes pelo actions/cache). Ano corrente muda:
    pergunta ao TSE se o arquivo mudou (If-Modified-Since) e so baixa de novo se mudou."""
    dest = CACHE / f"{tipo}_{ano}.zip"
    if dest.exists() and ano < dt.date.today().year:
        return dest
    CACHE.mkdir(parents=True, exist_ok=True)
    url = f"{BASE}/{tipo}/{tipo}_{ano}.zip"
    marca = dest.with_suffix(".modificado")  # Last-Modified da ultima copia baixada
    cab = {"User-Agent": "alerta-patrimonial/1.0"}
    if dest.exists() and marca.exists():
        cab["If-Modified-Since"] = marca.read_text().strip()
    try:
        req = urllib.request.Request(url, headers=cab)
        with urllib.request.urlopen(req, timeout=300) as r:
            tmp = dest.with_suffix(".parcial")
            with open(tmp, "wb") as f:
                while bloco := r.read(1 << 20):
                    f.write(bloco)
            tmp.replace(dest)
            if r.headers.get("Last-Modified"):
                marca.write_text(r.headers["Last-Modified"])
        return dest
    except urllib.error.HTTPError as e:
        if e.code == 304:  # nao mudou desde a copia guardada
            return dest
        print(f"[aviso] {url} indisponivel: {e}", file=sys.stderr)
        return dest if dest.exists() else None
    except Exception as e:
        print(f"[aviso] {url} indisponivel: {e}", file=sys.stderr)
        return dest if dest.exists() else None


def ler_zip(path):
    """Le o CSV nacional (_BRASIL) ou, se nao houver, concatena os CSVs por UF."""
    with zipfile.ZipFile(path) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        alvo = [n for n in csvs if "_BRASIL" in n.upper()] or csvs
        dfs = [pd.read_csv(z.open(n), sep=";", encoding="latin-1", dtype=str,
                           keep_default_na=False) for n in alvo]
    return pd.concat(dfs, ignore_index=True)


def dinheiro(s):
    return pd.to_numeric(s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                         errors="coerce").fillna(0.0)


def chave_pessoa(r):
    cpf = re.sub(r"\D", "", r.get("NR_CPF_CANDIDATO", ""))
    if len(cpf) == 11 and len(set(cpf)) > 1:
        return "cpf:" + cpf
    return "nn:" + norm(r.get("NM_CANDIDATO")) + "|" + r.get("DT_NASCIMENTO", "")


def empresas_por_sq(bens):
    """{SQ_CANDIDATO: [empresas]} a partir da descricao dos bens de participacao societaria
    (quotas, acoes, capital social). So nomes: CNPJ/CPF e numeros sao descartados."""
    if "DS_BEM_CANDIDATO" not in bens:
        return {}
    desc = bens["DS_BEM_CANDIDATO"].astype(str)
    tipo = bens["DS_TIPO_BEM_CANDIDATO"].astype(str) if "DS_TIPO_BEM_CANDIDATO" in bens \
        else pd.Series("", index=bens.index)
    alvo = (tipo + " " + desc).str.contains(r"QUOT|COTA|A[CÇ][OÕÃA]|PARTICIPA|CAPITAL|QUINH",
                                            case=False, regex=True, na=False)  # pre-filtro rapido
    out, cnpjs = {}, {}
    for sq, d, t in zip(bens.loc[alvo, "SQ_CANDIDATO"].astype(str).str.strip(), desc[alvo], tipo[alvo]):
        lst = out.setdefault(sq, [])
        nomes = empresas_do_bem(d, t)
        for nome in nomes:
            if nome not in lst and len(lst) < MAX_EMPRESAS:
                lst.append(nome)
        # CNPJ da empresa (dado publico) so para consultar o Portal da Transparencia; nao vai para o site
        achados = [c for c in dict.fromkeys(re.sub(r"\D", "", x) for x in RE_CNPJ.findall(d)) if transparencia.cnpj_ok(c)]
        if len(nomes) == 1 and achados:
            par = cnpjs.setdefault(sq, [])
            if all(c != achados[0] for _, c in par):
                par.append((nomes[0], achados[0]))
    return out, cnpjs


def serie_tse(anos):
    """Uma linha por pessoa e eleicao: patrimonio total declarado."""
    partes = []
    for ano in anos:
        print(f"TSE {ano}: baixando e lendo declaracoes...")
        zb, zc = baixar("bem_candidato", ano), baixar("consulta_cand", ano)
        if not zb or not zc:
            continue
        bens, cand = ler_zip(zb), ler_zip(zc)
        bens["VR"] = dinheiro(bens["VR_BEM_CANDIDATO"])
        pat = bens.groupby("SQ_CANDIDATO", as_index=False)["VR"].sum().rename(columns={"VR": "patrimonio"})
        emp, emp_cnpj = empresas_por_sq(bens)
        cand = cand.drop_duplicates("SQ_CANDIDATO").copy()
        cand["chave"] = cand.apply(chave_pessoa, axis=1)
        m = cand.merge(pat, on="SQ_CANDIDATO", how="inner")
        m["ano"] = int(ano)
        sit = m["DS_SIT_TOT_TURNO"] if "DS_SIT_TOT_TURNO" in m else pd.Series("", index=m.index)
        m["eleito"] = sit.astype(str).str.upper().str.startswith("ELEITO")
        col = lambda c: m[c].astype(str).str.strip() if c in m else pd.Series("", index=m.index)
        m["sq_candidato"], m["cd_eleicao"] = col("SQ_CANDIDATO"), col("CD_ELEICAO")
        m["sg_ue"], m["nome_urna"] = col("SG_UE"), col("NM_URNA_CANDIDATO")
        m["suplementar"] = col("NM_TIPO_ELEICAO").map(norm).str.contains("SUPLEMENTAR")
        m["empresas"] = m["sq_candidato"].map(lambda s: list(emp.get(s, ())))
        m["empresas_cnpj"] = m["sq_candidato"].map(lambda s: list(emp_cnpj.get(s, ())))
        partes.append(m.rename(columns={"NM_CANDIDATO": "nome", "DS_CARGO": "cargo",
                                        "SG_UF": "uf", "SG_PARTIDO": "partido"})
                       [["chave", "ano", "nome", "cargo", "uf", "partido", "eleito", "patrimonio",
                         "sq_candidato", "cd_eleicao", "sg_ue", "nome_urna", "suplementar", "empresas",
                         "empresas_cnpj"]])
    if not partes:
        sys.exit("Nenhum dado do TSE disponivel. Verifique a conexao e os anos em config/parametros.json.")
    return pd.concat(partes, ignore_index=True)


def cpf_ficticio(i):
    """CPF com digitos verificadores validos, gerado a partir de i (so para o modo --demo)."""
    base = [int(c) for c in f"{(i * 7919 + 123456789) % 10**9:09d}"]
    for n in (9, 10):
        d = sum(a * b for a, b in zip(base, range(n + 1, 1, -1))) * 10 % 11
        base.append(0 if d == 10 else d)
    return "".join(map(str, base))


def serie_demo(seed=7):
    import random
    random.seed(seed)
    linhas = []
    for i in range(400):
        base = random.lognormvariate(12.5, 1.0)
        f = random.lognormvariate(0.35, 0.35)
        if i == 1:
            f = 25.0  # caso extremo
        # metade com CPF ficticio (digitos validos), para os testes provarem que CPF nunca vaza
        chave = f"cpf:{cpf_ficticio(i)}" if i % 2 == 0 else f"demo:{i}"
        linhas.append(dict(chave=chave, ano=2018, nome=f"PESSOA DEMO {i:03d}", cargo="DEPUTADO FEDERAL",
                           uf=random.choice(["PA", "SP", "MG", "BA"]), partido="XX", eleito=True, patrimonio=base,
                           sq_candidato=None, cd_eleicao=None, sg_ue=None, nome_urna=f"DEMO {i:03d}",
                           suplementar=False, empresas=[], empresas_cnpj=[]))  # sem SQ real: link_tse fica None no demo
        linhas.append(dict(linhas[-1], ano=2022, patrimonio=base * f, eleito=False))
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------- analise
def renda_publica(cargo, ano_a, ano_b, regras):
    r = regras[regras.cargo == cargo]
    if r.empty:
        return None
    total = 0.0
    for y in range(ano_a + 1, ano_b + 1):
        v = r[r.vigente_desde <= y].sort_values("vigente_desde")
        if v.empty:
            return None
        total += 12 * float(v.iloc[-1].mensal_bruto)
    return total


def pares(serie, regras, extras, p):
    out = []
    for chave, g in serie.sort_values("ano").groupby("chave"):
        g = g.to_dict("records")
        for a, b in zip(g, g[1:]):
            if b["ano"] - a["ano"] < 2 or a["patrimonio"] <= 0:
                continue
            anos = b["ano"] - a["ano"]
            renda = renda_publica(a["cargo"], a["ano"], b["ano"], regras) if a["eleito"] else None
            extra = extras.get(chave, 0.0) * 12 * anos
            cap = None if (renda is None and not extra) else (renda or 0.0) * p["taxa_poupanca"] + extra
            out.append(dict(chave=chave, nome=b["nome"], cargo=b["cargo"], uf=b["uf"], partido=b["partido"],
                            ano_ini=a["ano"], ano_fim=b["ano"], pat_ini=a["patrimonio"], pat_fim=b["patrimonio"],
                            cresc=b["patrimonio"] - a["patrimonio"], cap=cap, cargo_ini=a["cargo"],
                            nome_urna=txt(b.get("nome_urna")) or None, link_tse=link_tse(b),
                            empresas=[str(x) for x in b["empresas"]]
                            if isinstance(b.get("empresas"), (list, tuple)) else [],
                            empresas_cnpj=list(b["empresas_cnpj"])
                            if isinstance(b.get("empresas_cnpj"), (list, tuple)) else [],
                            # participacao em empresas no inicio ou no fim do periodo: ha outra fonte de renda
                            outras_rendas=any(isinstance(x.get("empresas"), (list, tuple)) and len(x["empresas"]) > 0
                                              for x in (a, b))))
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df["razao"] = df.apply(lambda r: r.cresc / r.cap if r.cap and r.cap > 0 else None, axis=1)
    # percentil dentro do grupo de pares (cargo + periodo); se o grupo for pequeno, so o periodo
    gk = ["ano_ini", "ano_fim", "cargo_ini"]
    pct_grupo = df.groupby(gk)["cresc"].rank(pct=True) * 100
    pct_periodo = df.groupby(["ano_ini", "ano_fim"])["cresc"].rank(pct=True) * 100
    n = df.groupby(gk)["cresc"].transform("size")
    df["percentil"] = pct_grupo.where(n >= p["min_pares_grupo"], pct_periodo)
    df["nivel_calculado"] = df.apply(lambda r: nivel(r, p), axis=1)
    # outras rendas (empresas declaradas): o salario nao e a unica fonte, entao o destaque desce um grau
    df["nivel"] = [REDUZ.get(n, n) if o else n for n, o in zip(df["nivel_calculado"], df["outras_rendas"])]
    return df


REDUZ = {"forte": "atencao", "atencao": "informativo", "informativo": "informativo"}


def nivel(r, p):
    if r.cresc < p["crescimento_minimo"]:
        return None
    rz = r.razao if pd.notna(r.razao) else None
    f, a, i = p["limiar_forte"], p["limiar_atencao"], p["limiar_informativo"]
    if rz is not None and rz >= f["razao"] and r.percentil >= f["percentil"]:
        return "forte"
    if (rz is not None and rz >= a["razao"] and r.percentil >= a["percentil"]) or r.percentil >= 98:
        return "atencao"
    if r.percentil >= i["percentil"]:
        return "informativo"
    return None


# ---------------------------------------------------------------- saida
def carregar_monitorados():
    """Lista de monitorados: segredo MONITORADOS_CSV (lido so em memoria) ou config/monitorados.csv."""
    texto = os.getenv("MONITORADOS_CSV", "").strip()
    f = CFG / "monitorados.csv"
    if texto:
        df = pd.read_csv(io.StringIO(texto), dtype=str, keep_default_na=False)
    else:
        df = pd.read_csv(f, dtype=str, keep_default_na=False) if f.exists() else pd.DataFrame()
    cpfs, nomes, extras = set(), set(), {}
    for _, r in df.iterrows():
        cpf = re.sub(r"\D", "", r.get("cpf", ""))
        extra = float(r.get("renda_extra_mensal") or 0)
        if cpf:
            cpfs.add("cpf:" + cpf); extras["cpf:" + cpf] = extra
        if r.get("nome"):
            nomes.add(norm(r["nome"])); extras["nome:" + norm(r["nome"])] = extra
    return cpfs, nomes, extras


def carregar_fontes():
    """Fontes de noticias aprovadas pelo site (issues com rotulo "aprovada"): nome, feed, uf."""
    f = CFG / "fontes_noticias.csv"
    df = pd.read_csv(f, dtype=str, keep_default_na=False) if f.exists() else pd.DataFrame()
    out = []
    for _, r in df.iterrows():
        feed = r.get("feed", "").strip()
        if feed.startswith(("https://", "http://")) and r.get("nome", "").strip():
            out.append(dict(nome=r["nome"].strip(), feed=feed, uf=r.get("uf", "").strip().upper()))
    return out


def carregar_bens():
    """Bens de referencia (config/bens_referencia.json) para "daria para comprar N ..."; None se faltar."""
    try:
        cfg = json.loads((CFG / "bens_referencia.json").read_text(encoding="utf-8"))
        cfg["bens"] = [b for b in cfg.get("bens", []) if float(b.get("preco") or 0) > 0 and b.get("singular")]
        return cfg if cfg["bens"] else None
    except (OSError, ValueError, TypeError) as ex:
        print(f"[aviso] config/bens_referencia.json ignorado ({ex!r})", file=sys.stderr)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="dados sinteticos para testar sem internet")
    ap.add_argument("--saida", help="pasta de saida (docs/ e data/ ficam dentro dela); padrao: o proprio repositorio")
    args = ap.parse_args()
    docs, dados_dir = (Path(args.saida) / "docs", Path(args.saida) / "data") if args.saida else (DOCS, ROOT / "data")
    estado_arq, ids_arq = dados_dir / "estado.json", dados_dir / "ids.json"
    p = json.loads((CFG / "parametros.json").read_text())
    regras = pd.read_csv(CFG / "renda_publica.csv")
    cpfs, nomes, extras_cfg = carregar_monitorados()
    # id interno estavel (HMAC com ID_SEGREDO): unico identificador de pessoa que sai do pipeline
    segredo = os.getenv("ID_SEGREDO") or ("demo" if args.demo else "")
    pid = Ids(ids_arq, segredo) if segredo else None
    if not pid:
        print("[aviso] sem ID_SEGREDO: paginas por pessoa e memoria de alertas novos desativadas", file=sys.stderr)

    serie = serie_demo() if args.demo else serie_tse(p["anos"])
    extras = {r.chave: extras_cfg.get(r.chave, extras_cfg.get("nome:" + norm(r.nome), 0.0))
              for r in serie.drop_duplicates("chave").itertuples()}
    df = pares(serie, regras, extras, p)
    if df.empty:
        sys.exit("Nenhuma pessoa com duas declaracoes consecutivas.")
    df["monitorado"] = df.apply(lambda r: r.chave in cpfs or norm(r.nome) in nomes, axis=1)
    alertas = df[df.nivel.notna()].copy()

    # memoria de alertas por id interno (versoes antigas usavam o CPF na chave: sao descartadas)
    try:
        estado = {k: v for k, v in json.loads(estado_arq.read_text()).items() if re.match(r"p\d+\|", k)}
    except (OSError, ValueError):
        estado = {}
    alertas["pessoa"] = alertas.chave.map(pid) if pid else None
    alertas["id"] = (alertas.pessoa.astype(str) + "|" + alertas.ano_ini.astype(str) + "-" + alertas.ano_fim.astype(str)
                     if pid else None)
    alertas["novo"] = alertas.apply(lambda r: ORDEM[r.nivel] > ORDEM.get(estado.get(r.id, ""), 0), axis=1)

    if p["publicar_somente_monitorados"] and (cpfs or nomes):
        vis = alertas[alertas.monitorado]
    else:
        vis = alertas.assign(o=alertas.nivel.map(ORDEM)).sort_values(["o", "percentil"], ascending=False) \
                     .head(p["max_linhas_sem_lista"]).drop(columns="o")
    vis = vis.assign(o=vis.nivel.map(ORDEM)).sort_values(["novo", "o", "cresc"], ascending=False).drop(columns="o")

    pub = vis.drop(columns=["chave", "id", "cargo_ini", "empresas_cnpj"])  # CPF/CNPJ nunca vao para o site
    pub = pub.astype(object).where(pub.notna(), None)
    dados = dict(gerado_em=dt.datetime.now().strftime("%Y-%m-%d %H:%M"), universo=int(len(df)),
                 alertas=json.loads(pub.to_json(orient="records")))
    docs.mkdir(parents=True, exist_ok=True)
    fontes = carregar_fontes()
    dados["repo"] = os.getenv("GITHUB_REPOSITORY")  # links "sugerir fonte" do painel
    dados["metodo"] = dict(taxa=p["taxa_poupanca"], minimo=p["crescimento_minimo"], forte=p["limiar_forte"],
                           atencao=p["limiar_atencao"], informativo=p["limiar_informativo"])  # texto "Como ler"
    dados["fontes"] = [dict(nome=f["nome"], uf=f["uf"]) for f in fontes]
    # Portal da Transparencia: uma consulta por pessoa (nome+UF), na ordem do painel; CPF/CNPJ ficam so aqui
    pessoas = {}
    for i, r in enumerate(vis.to_dict("records")):
        q = pessoas.setdefault((norm(r["nome"]), str(r["uf"]).upper()), dict(
            nome=r["nome"], nome_urna=txt(r.get("nome_urna")), cargo="", idx=[], chave=r["chave"],
            cpf=r["chave"][4:] if str(r["chave"]).startswith("cpf:") else "", empresas=r.get("empresas_cnpj") or []))
        q["cargo"] += " " + str(r["cargo"])
        q["idx"].append(i)
    try:  # o Portal nunca derruba a atualizacao: se falhar, a secao sai "Fonte nao encontrada"
        info = {} if args.demo else transparencia.coletar(pessoas, chave_api=os.getenv("TRANSPARENCIA_TOKEN"))
    except Exception as ex:
        print(f"[aviso] Portal da Transparencia indisponivel ({ex!r})", file=sys.stderr)
        info = {k: {"pendente": "falha"} for k in pessoas}
    secoes = {}
    for k, q in pessoas.items():
        try:
            html_sec = transparencia.secao(info.get(k), q["nome_urna"] or q["nome"])
        except Exception as ex:
            print(f"[aviso] secao do Portal falhou para {q['nome']} ({ex!r})", file=sys.stderr)
            html_sec = transparencia.NAO_DEU
        secoes.update({i: html_sec for i in q["idx"]})
    # cota parlamentar (Camara/Senado, arquivos abertos anuais); o CPF so liga as bases, nao sai daqui
    hoje = dt.date.today().year
    try:
        ceap = {} if args.demo else cota.coletar(pessoas, range(hoje - 3, hoje + 1), CACHE)
    except Exception as ex:
        print(f"[aviso] cota parlamentar indisponivel ({ex!r})", file=sys.stderr)
        ceap = {}
    secoes_cota = {}
    for k, q in pessoas.items():
        try:
            html_cota = cota.secao(ceap.get(k), q["cargo"], ceap.get("_fontes"))
        except Exception as ex:
            print(f"[aviso] secao da cota falhou para {q['nome']} ({ex!r})", file=sys.stderr)
            html_cota = '<p class="vazio"><b>Não informado</b>.</p>'
        secoes_cota.update({i: html_cota for i in q["idx"]})
    bens = carregar_bens()
    for i, cam in gerar_dossies(dados["alertas"], docs, buscar=not args.demo, fontes_extra=fontes,
                                transparencia=secoes, bens=bens, cota=secoes_cota).items():
        dados["alertas"][i]["dossie"] = cam
    # painel: quem mais gastou da cota parlamentar (entre as pessoas em destaque) e com o que
    ranking = []
    for k, q in pessoas.items():
        r = ceap.get(k)
        if r:
            a = dados["alertas"][q["idx"][0]]
            ranking.append(dict(nome=q["nome_urna"] or q["nome"], cargo=a.get("cargo"), partido=a.get("partido"),
                                uf=k[1], total=round(r["total"], 2), de=r["anos"][0][0], ate=r["anos"][-1][0],
                                tipos=[dict(tipo=t, valor=round(v, 2)) for t, v in r["tipos"][:3]],
                                link=r["link"], dossie=a.get("dossie")))
    dados["cota"] = sorted(ranking, key=lambda x: -x["total"])[:10]

    cartoes, graficos_painel = "", {}
    if pid:  # uma pagina por pessoa (docs/pessoa/<id>.html), so com o id interno
        hist = {c: sorted((int(a), float(v)) for a, v in zip(g.ano, g.patrimonio))
                for c, g in serie[serie.chave.isin(set(vis.chave))].groupby("chave")}
        try:
            cartoes, graficos_painel = paginas.gerar(dados["alertas"], pessoas, hist, secoes, docs,
                                                     gerado=dados["gerado_em"])
        except Exception as ex:  # nunca derruba o painel
            print(f"[aviso] paginas por pessoa falharam ({ex!r})", file=sys.stderr)
    paginas.copiar_estilo(docs)
    # ordem do painel: mais mencoes atuais na imprensa (Brasil e exterior) primeiro, depois maior crescimento
    dados["alertas"].sort(key=lambda a: (-(a.get("mencoes") or 0), -(a.get("cresc") or 0)))
    tpl = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
    html_painel = tpl.replace("/*DADOS*/null", json.dumps(dados, ensure_ascii=False))
    html_painel = html_painel.replace("/*BENS*/null", json.dumps(bens, ensure_ascii=False))
    blocos = dict(CARTOES=cartoes, **graficos_painel)
    for marca, conteudo in blocos.items():
        html_painel = html_painel.replace(f"<!--{marca}-->", conteudo)
    # blocos gerados a parte: o workflow "Publicar painel" remonta o index com o template atual
    (docs / "blocos.json").write_text(json.dumps(blocos, ensure_ascii=False), encoding="utf-8")
    (docs / "index.html").write_text(html_painel, encoding="utf-8")
    if pid:
        dados_dir.mkdir(parents=True, exist_ok=True)
        estado_arq.write_text(json.dumps({r.id: r.nivel for r in alertas.itertuples()}, ensure_ascii=False))
        pid.salvar()

    novos = vis[vis.novo]
    resumo = f"Patrimonio declarado em foco {dados['gerado_em']}: {len(vis)} destaques, {len(novos)} novos."
    for r in novos.head(15).itertuples():
        resumo += f"\n- [{r.nivel}] {r.nome} ({r.cargo}/{r.uf}) {r.ano_ini}->{r.ano_fim}: +R$ {r.cresc:,.0f}"
    (docs / "digest.txt").write_text(resumo, encoding="utf-8")
    # ultima barreira: nenhum CPF/CNPJ sai no site, mesmo que venha dentro de um texto de fonte externa
    n = varrer(docs, cpfs=[q["cpf"] for q in pessoas.values() if q.get("cpf")])
    if n:
        print(f"[aviso] CPF/CNPJ removido de {n} arquivo(s) antes de publicar", file=sys.stderr)
    print(resumo)
    if not args.demo:
        avisar(resumo if len(novos) else None)


def avisar(texto):
    tok, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (texto and tok and chat):
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": texto[:4000]}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data, timeout=30)
    except Exception as e:
        print(f"[aviso] Telegram falhou: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
