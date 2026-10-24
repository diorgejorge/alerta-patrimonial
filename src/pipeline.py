#!/usr/bin/env python3
"""Alerta patrimonial: compara o crescimento do patrimonio declarado ao TSE entre
eleicoes com a capacidade de acumulacao estimada e com o grupo de pares.
Resultado = INDICIO para acompanhamento, nao prova."""
import argparse, hashlib, io, json, os, re, sys, unicodedata, urllib.request, urllib.parse, zipfile
import datetime as dt
from pathlib import Path
import pandas as pd
from dossie import gerar_dossies, empresas_do_bem, MAX_EMPRESAS, RE_CNPJ
import dossie
import transparencia
import cota
import projetos
import parlamentares
import votacoes, presenca, gabinete
from texto import cap
import empresas
import estados
import temas
from ids import Ids, varrer
from cache import Cache, salvar_resultados
import cifra
import contatos
import paginas
import representantes, shutil
import ibge
import ranking as ranking_uf  # "ranking" ja e variavel do main()
import acompanhar

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


FOTO = "https://divulgacandcontas.tse.jus.br/divulga/rest/arquivo/img"


def link_foto(r):
    """Foto oficial da candidatura no DivulgaCandContas ({FOTO}/{ID_ELEICAO}/{SQ_CANDIDATO}/{SG_UE}), ou None."""
    lk = link_tse(r)  # mesmas regras: sem id da eleicao, SQ ou UE, nao ha foto
    if not lk:
        return None
    eleicao, sq, _, ue = lk.rsplit("/", 4)[1:]
    return f"{FOTO}/{eleicao}/{sq}/{ue}"


# ---------------------------------------------------------------- coleta TSE
def baixar(tipo, ano):
    """Zip do TSE (bytes), guardado cifrado em data/cache (cifra.py). Anos passados nao mudam: usa a copia sem
    acessar a rede; o ano corrente pergunta ao TSE se o arquivo mudou (If-Modified-Since)."""
    return cifra.baixar(f"{BASE}/{tipo}/{tipo}_{ano}.zip", CACHE / f"{tipo}_{ano}.zip",
                        perguntar=ano >= dt.date.today().year)


def ler_zip(dados):
    """Le o CSV nacional (_BRASIL) ou, se nao houver, concatena os CSVs por UF. `dados`: bytes do zip ou caminho."""
    with zipfile.ZipFile(io.BytesIO(dados) if isinstance(dados, (bytes, bytearray)) else dados) as z:
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
            if nome not in lst:  # todas: o card mostra quantas sao; o painel publica so MAX_EMPRESAS nomes
                lst.append(nome)
        # CNPJ da empresa (dado publico) so para consultar o Portal da Transparencia; nao vai para o site
        achados = [c for c in dict.fromkeys(re.sub(r"\D", "", x) for x in RE_CNPJ.findall(d)) if transparencia.cnpj_ok(c)]
        if len(nomes) == 1 and achados:
            par = cnpjs.setdefault(sq, [])
            if all(c != achados[0] for _, c in par):
                par.append((nomes[0], achados[0]))
    return out, cnpjs


VERSAO_LEITURA_TSE = 2  # mude ao alterar a leitura abaixo: invalida o cache dos anos ja lidos


def serie_tse(anos, cache=None):
    """Uma linha por pessoa e eleicao: patrimonio total declarado.
    `cache` (cache.Cache cifrado): o ano ja lido so e lido de novo se o zip do TSE mudar (tamanho/data)."""
    partes, assinaturas = [], {}
    for ano in anos:
        zb, zc = baixar("bem_candidato", ano), baixar("consulta_cand", ano)
        if not zb or not zc:
            continue
        assinatura = (VERSAO_LEITURA_TSE, int(ano), *(hashlib.sha256(z).hexdigest()[:16] for z in (zb, zc)))
        assinaturas[int(ano)] = "-".join(map(str, assinatura))  # pares() reaproveita os periodos dos anos sem mudanca
        lido = cache.get(assinatura) if cache else None
        if lido is not None:
            print(f"TSE {ano}: declaracoes ja lidas (cache, arquivo do TSE sem mudanca).")
            partes.append(lido)
            continue
        print(f"TSE {ano}: lendo declaracoes...")
        partes.append(_ler_ano_tse(ano, zb, zc))
        if cache:
            cache.set(assinatura, partes[-1])
    if cache:
        cache.salvar()
    if not partes:
        sys.exit("Nenhum dado do TSE disponivel. Verifique a conexao e os anos em config/parametros.json.")
    serie = pd.concat(partes, ignore_index=True)
    serie.attrs["assinaturas"] = assinaturas
    return serie


def _ler_ano_tse(ano, zb, zc):
    """Declaracoes de bens + candidaturas de um ano -> uma linha por candidatura com o patrimonio total."""
    bens, cand = ler_zip(zb), ler_zip(zc)
    bens["VR"] = dinheiro(bens["VR_BEM_CANDIDATO"])
    pat = bens.groupby("SQ_CANDIDATO", as_index=False)["VR"].sum().rename(columns={"VR": "patrimonio"})
    emp, emp_cnpj = empresas_por_sq(bens)
    # 2o turno: a mesma candidatura vem uma vez por turno; fica a do ultimo turno, que traz o resultado final (#59)
    if "NR_TURNO" in cand:
        cand = cand.sort_values("NR_TURNO", ascending=False, key=lambda t: pd.to_numeric(t, errors="coerce"))
    cand = cand.drop_duplicates("SQ_CANDIDATO").copy()
    cand["chave"] = cand.apply(chave_pessoa, axis=1)
    m = cand.merge(pat, on="SQ_CANDIDATO", how="inner")
    m["ano"] = int(ano)
    sit = m["DS_SIT_TOT_TURNO"] if "DS_SIT_TOT_TURNO" in m else pd.Series("", index=m.index)
    m["eleito"] = sit.astype(str).str.upper().str.startswith("ELEITO")
    col = lambda c: m[c].astype(str).str.strip() if c in m else pd.Series("", index=m.index)
    m["sq_candidato"], m["cd_eleicao"] = col("SQ_CANDIDATO"), col("CD_ELEICAO")
    m["sg_ue"], m["nome_urna"], m["nm_ue"] = col("SG_UE"), col("NM_URNA_CANDIDATO"), col("NM_UE")
    m["suplementar"] = col("NM_TIPO_ELEICAO").map(norm).str.contains("SUPLEMENTAR")
    m["empresas"] = m["sq_candidato"].map(lambda s: list(emp.get(s, ())))
    m["empresas_cnpj"] = m["sq_candidato"].map(lambda s: list(emp_cnpj.get(s, ())))
    return (m.rename(columns={"NM_CANDIDATO": "nome", "DS_CARGO": "cargo", "SG_UF": "uf", "SG_PARTIDO": "partido"})
            [["chave", "ano", "nome", "cargo", "uf", "partido", "eleito", "patrimonio", "sq_candidato",
              "cd_eleicao", "sg_ue", "nm_ue", "nome_urna", "suplementar", "empresas", "empresas_cnpj"]])


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
        linhas.append(dict(linhas[-1], ano=2022, patrimonio=base * f, eleito=i % 3 == 0))  # 1 em 3 reeleito (#67)
    # presidente e vice eleitos em 2022 com crescimento pequeno (sem nivel): mesmo assim aparecem nos destaques (#63)
    linhas.append(dict(linhas[-1], chave="demo:presidente", ano=2018, nome="PRESIDENTE DEMO", nome_urna="PRESIDENTE DEMO",
                       cargo="PRESIDENTE", uf="BR", partido="XX", eleito=False, patrimonio=1_000_000.0))
    linhas.append(dict(linhas[-1], ano=2022, eleito=True, patrimonio=1_050_000.0))
    linhas.append(dict(linhas[-1], chave="demo:vice", ano=2018, nome="VICE DEMO", nome_urna="VICE DEMO",
                       cargo="VICE-PRESIDENTE", eleito=False, patrimonio=800_000.0))
    linhas.append(dict(linhas[-1], ano=2022, eleito=True, patrimonio=820_000.0))
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


VERSAO_PARES = 1  # mude ao alterar a montagem dos pares: invalida os periodos guardados


def _assinatura(df):
    """Assinatura curta do conteudo de uma tabela (para a chave do cache)."""
    h = pd.util.hash_pandas_object(df.astype(str), index=False).values.tobytes() if len(df) else b""
    return hashlib.sha256(h).hexdigest()[:16]


def pares(serie, regras, extras, p, cache=None, ano_atual=None):
    """Periodos (declaracao anterior -> seguinte) de cada pessoa, com crescimento, capacidade, percentil e nivel.
    Com `cache` (#48): os periodos que terminam antes do ano atual ficam guardados (cifrados) e so os que chegam ao ano
    atual sao montados de novo; percentil e nivel sao refeitos sobre todos (grupos por ano_ini, ano_fim e cargo)."""
    if cache is None:
        return _classifica(pd.DataFrame(_lista_pares(serie, regras, extras, p)), p)
    ano_atual = int(ano_atual or dt.date.today().year)
    passado = serie[serie["ano"] < ano_atual]
    tse = serie.attrs.get("assinaturas") or {}
    k = (VERSAO_PARES, ano_atual, tuple(sorted((a, s) for a, s in tse.items() if a < ano_atual)) or _assinatura(passado),
         _assinatura(regras), json.dumps(p, sort_keys=True, default=str),
         hashlib.sha256(json.dumps(sorted(extras.items()), default=str).encode()).hexdigest()[:16])
    antigos = cache.get(k)
    if antigos is None:
        antigos = _lista_pares(passado, regras, extras, p)
        cache.set(k, antigos)
        cache.salvar()
    else:
        print(f"Pares: {len(antigos)} periodos anteriores a {ano_atual} vindos do cache.")
    atuais = serie[serie["chave"].isin(set(serie.loc[serie["ano"] == ano_atual, "chave"]))]
    return _classifica(pd.DataFrame(antigos + _lista_pares(atuais, regras, extras, p, so_fim=ano_atual)), p)


def _lista_pares(serie, regras, extras, p, so_fim=None):
    out = []
    for chave, g in serie.sort_values("ano").groupby("chave"):
        g = g.to_dict("records")
        for a, b in zip(g, g[1:]):
            if b["ano"] - a["ano"] < 2 or a["patrimonio"] <= 0 or (so_fim is not None and b["ano"] != so_fim):
                continue
            anos = b["ano"] - a["ano"]
            renda = renda_publica(a["cargo"], a["ano"], b["ano"], regras) if a["eleito"] else None
            extra = extras.get(chave, 0.0) * 12 * anos
            cap = None if (renda is None and not extra) else (renda or 0.0) * p["taxa_poupanca"] + extra
            out.append(dict(chave=chave, nome=b["nome"], cargo=b["cargo"], uf=b["uf"], partido=b["partido"],
                            ano_ini=a["ano"], ano_fim=b["ano"], pat_ini=a["patrimonio"], pat_fim=b["patrimonio"],
                            cresc=b["patrimonio"] - a["patrimonio"], cap=cap, cargo_ini=a["cargo"],
                            nome_urna=txt(b.get("nome_urna")) or None, link_tse=link_tse(b), link_tse_ini=link_tse(a), link_foto=link_foto(b),
                            empresas=[str(x) for x in b["empresas"]][:MAX_EMPRESAS]
                            if isinstance(b.get("empresas"), (list, tuple)) else [],
                            # quantas empresas diferentes a pessoa declarou no inicio ou no fim do periodo (card)
                            qtd_empresas=len({str(n) for x in (a, b) if isinstance(x.get("empresas"), (list, tuple))
                                              for n in x["empresas"]}),
                            empresas_cnpj=list(b["empresas_cnpj"])
                            if isinstance(b.get("empresas_cnpj"), (list, tuple)) else [],
                            # participacao em empresas no inicio ou no fim do periodo: ha outra fonte de renda
                            outras_rendas=any(isinstance(x.get("empresas"), (list, tuple)) and len(x["empresas"]) > 0
                                              for x in (a, b))))
    return out


def _classifica(df, p):
    """Razao, percentil no grupo de pares e nivel de destaque (sobre todos os periodos juntos)."""
    if df.empty:
        return df
    # faixas (#62): quantas vezes o patrimonio aumentou sobre o valor original (pat_ini > 0 em _lista_pares); o salario nao entra
    df["razao"] = df.cresc / df.pat_ini
    # so para "parlamentar exemplar" (patrimonio compativel com o salario)
    df["razao_salario"] = df.apply(lambda r: r.cresc / r.cap if r.cap and r.cap > 0 else None, axis=1)
    # percentil dentro do grupo de pares (cargo + periodo); se o grupo for pequeno, so o periodo
    gk = ["ano_ini", "ano_fim", "cargo_ini"]
    pct_grupo = df.groupby(gk)["cresc"].rank(pct=True) * 100
    pct_periodo = df.groupby(["ano_ini", "ano_fim"])["cresc"].rank(pct=True) * 100
    n = df.groupby(gk)["cresc"].transform("size")
    n_periodo = df.groupby(["ano_ini", "ano_fim"])["cresc"].transform("size")
    do_cargo = n >= p["min_pares_grupo"]
    df["percentil"] = pct_grupo.where(do_cargo, pct_periodo)
    # regua dos colegas (#64): tamanho do grupo usado e o cargo dele (None = todos os cargos do periodo)
    df["n_pares"] = n.where(do_cargo, n_periodo).astype(int)
    df["cargo_pares"] = df["cargo_ini"].where(do_cargo, None)
    df["nivel_calculado"] = df.apply(lambda r: nivel(r, p), axis=1)
    # outras rendas (empresas declaradas): o salario nao e a unica fonte, entao o destaque desce um grau
    df["nivel"] = [REDUZ.get(n, n) if o else n for n, o in zip(df["nivel_calculado"], df["outras_rendas"])]
    return df


REDUZ = {"forte": "atencao", "atencao": "informativo", "informativo": "informativo"}


def nivel(r, p):
    if r.cresc < p["crescimento_minimo"]:
        return None
    rz = r.razao
    f, a, i = p["limiar_forte"], p["limiar_atencao"], p["limiar_informativo"]
    if rz >= f["razao"] and r.percentil >= f["percentil"]:
        return "forte"
    if (rz >= a["razao"] and r.percentil >= a["percentil"]) or r.percentil >= 98:
        return "atencao"
    if r.percentil >= i["percentil"]:
        return "informativo"
    return None


def em_exercicio(serie, cargo, hoje=None):
    """Chave de quem foi eleito para `cargo` na eleicao mais recente com posse ja ocorrida (1o de janeiro seguinte),
    ou None (#63: PRESIDENTE e VICE-PRESIDENTE)."""
    hoje = hoje or dt.date.today()
    eleitos = serie[serie["eleito"].astype(bool) & (serie["cargo"].map(norm) == cargo)
                    & (serie["ano"].astype(int) < hoje.year)]
    return None if eleitos.empty else eleitos.sort_values("ano").iloc[-1]["chave"]


def em_mandato(serie, hoje=None):
    """{chave: ano da eleicao} de quem o TSE registra como eleito com mandato em curso hoje (#67): posse ja
    ocorrida (1o de janeiro seguinte a eleicao) e mandato ainda nao terminado (4 anos; senador 8).
    Com dois mandatos em curso (senador eleito depois para outro cargo), fica a eleicao mais recente."""
    hoje = hoje or dt.date.today()
    eleitos = serie[serie["eleito"].astype(bool)]
    ano = eleitos["ano"].astype(int)
    dur = eleitos["cargo"].map(norm).eq("SENADOR").map({True: 8, False: 4})
    atuais = eleitos.loc[(ano < hoje.year) & (ano + dur >= hoje.year)]
    return atuais.assign(ano=atuais["ano"].astype(int)).groupby("chave")["ano"].max().to_dict()


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


HOSTS_PROCESSOS = {"jusbrasil.com.br", "www.jusbrasil.com.br", "escavador.com", "www.escavador.com",
                   "processorapido.com", "www.processorapido.com"}  # alem de *.jus.br


def carregar_processos():
    """Processos em que a pessoa e re, informados e aprovados por issue (config/processos.csv).
    Devolve {(nome normalizado, UF): [dict(tribunal, numero, link)]}; so links https de *.jus.br, Jusbrasil, Escavador ou Processo Rapido."""
    f = CFG / "processos.csv"
    df = pd.read_csv(f, dtype=str, keep_default_na=False) if f.exists() else pd.DataFrame()
    out = {}
    for _, r in df.iterrows():
        link = r.get("link", "").strip()
        host = urllib.parse.urlsplit(link).netloc.lower()
        if not (link.startswith("https://") and (host.endswith(".jus.br") or host in HOSTS_PROCESSOS)):
            continue
        out.setdefault((norm(r.get("nome")), r.get("uf", "").strip().upper()), []).append(
            dict(tribunal=r.get("tribunal", "").strip(), numero=r.get("numero", "").strip(), link=link))
    return out


def arredonda(v, casas=4):
    """Floats com no maximo `casas` decimais (dict/list recursivo): JSON menor e sem sequencias longas de digitos
    que a varredura de CPF/CNPJ poderia confundir com documento."""
    if isinstance(v, float):
        return round(v, casas)
    if isinstance(v, dict):
        return {k: arredonda(x, casas) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [arredonda(x, casas) for x in v]
    return v


def carregar_bens():
    """Bens de referencia (config/bens_referencia.json) para "daria para comprar N ..."; None se faltar."""
    try:
        cfg = json.loads((CFG / "bens_referencia.json").read_text(encoding="utf-8"))
        cfg["bens"] = [b for b in cfg.get("bens", []) if float(b.get("preco") or 0) > 0 and b.get("singular")]
        return cfg if cfg["bens"] else None
    except (OSError, ValueError, TypeError) as ex:
        print(f"[aviso] config/bens_referencia.json ignorado ({ex!r})", file=sys.stderr)
        return None


NIVEL_COD = {"forte": 3, "atencao": 2, "informativo": 1}  # lista completa: 0 = sem destaque
REL_OK = lambda u: isinstance(u, str) and bool(u) and not re.match(r"\s*[a-z][a-z0-9+.-]*:", u, re.I)


def lista_completa(df, paginas_pessoa, gerado, marcas=None):
    """Todas as pessoas com duas declaracoes comparaveis (#43), no formato leve de docs/todos.json: uma linha por
    pessoa com os periodos dentro (#47) e so campos minimos. A chave (CPF) so agrupa aqui dentro e nao sai.
    pessoa = [nome publico, nome civil (vazio se igual), pagina do dossie (destaques) ou "", marcas, [periodos]]
    marcas = "e" parlamentar exemplar, "s" selo Mao na massa (parlamentares.py), "" nenhuma
    periodo = [ano_ini, ano_fim, cargo, partido, uf, patrimonio no inicio, no fim, nivel, link do TSE sem o prefixo]"""
    cargos, partidos = {}, {}
    cod = lambda d, v: d.setdefault(txt(v) or "Não informado", len(d))
    pre = DIVULGA + "/"
    out = []
    for chave, g in df.sort_values(["ano_ini", "ano_fim"]).groupby("chave", sort=False):
        per = [[int(r.ano_ini), int(r.ano_fim), cod(cargos, r.cargo), cod(partidos, r.partido), txt(r.uf).upper(),
                round(float(r.pat_ini)), round(float(r.pat_fim)), NIVEL_COD.get(r.nivel, 0),
                r.link_tse[len(pre):] if isinstance(r.link_tse, str) and r.link_tse.startswith(pre) else ""]
               for r in g.itertuples()]
        ult = g.iloc[-1]
        nome = txt(ult.get("nome"))
        urna = txt(ult.get("nome_urna")) or nome
        out.append([urna, "" if norm(nome) == norm(urna) else nome, paginas_pessoa.get(chave) or "",
                    (marcas or {}).get(chave, ""), per])
    out.sort(key=lambda p: norm(p[0]))
    return dict(gerado_em=gerado, pessoas=len(out), comparacoes=int(len(df)), link_tse=pre,
                cargos=list(cargos), partidos=list(partidos), lista=out)


def gravar_todos(docs, df, paginas_pessoa, gerado, marcas=None):
    """docs/todos.json (lista completa leve, baixada so quando o leitor abre a lista); devolve o resumo do painel."""
    t = lista_completa(df, paginas_pessoa, gerado, marcas)
    b = json.dumps(t, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (docs / "todos.json").write_bytes(b)
    kb = round(len(b) / 1024)
    print(f"Lista completa: {t['comparacoes']} comparacoes de {t['pessoas']} pessoas "
          f"({t['comparacoes'] - t['pessoas']} repeticoes de periodo); docs/todos.json com {kb} KB.")
    conta = lambda m: sum(m in p[3] for p in t["lista"])
    return dict(pessoas=t["pessoas"], comparacoes=t["comparacoes"], kb=kb, exemplar=conta("e"), selo=conta("s"))


def so_paginas(df, chaves, pid=None):
    """Periodo mais recente de cada chave em `chaves` (parlamentares em exercicio fora dos destaques), no formato
    das linhas de alerta, marcado `so_pagina`: ganha pagina propria e dossie, mas nao vira card do painel."""
    if not chaves:
        return df.iloc[0:0]
    x = df[df.chave.isin(chaves)].sort_values(["ano_fim", "ano_ini"]).drop_duplicates("chave", keep="last").copy()
    x["pessoa"] = x.chave.map(pid) if pid else None
    x["id"] = x.pessoa.astype(str) + "|" + x.ano_ini.astype(str) + "-" + x.ano_fim.astype(str) if pid else None
    x["novo"], x["topo"], x["so_pagina"] = False, 0, True
    return x


def montar_cobranca(pessoas, parl, ceap, proj, cache=None, demo=False):
    """{indice da primeira linha: contexto da aba "Como cobrar"} (#60). "contato" so existe para parlamentar federal
    em exercicio (None = fonte fora do ar); os demais cargos recebem o site da Assembleia (estadual) ou o aviso."""
    em_exercicio = {x["_chave"] for x in parl if x["_chave"]}
    chaves = {q["chave"] for q in pessoas.values()} & em_exercicio
    contato = contatos.coletar(parl, chaves, cache) if chaves else {}
    alas = contatos.assembleias()
    out = {}
    for k, q in pessoas.items():
        r = ceap.get(k)
        ctx = dict(assembleia=alas.get(k[1]), projetos=proj.get(k),
                   cota=dict(total=r["total"], de=r["anos"][0][0], ate=r["anos"][-1][0], link=r["link"]) if r else None)
        if q["chave"] in em_exercicio:
            ctx["contato"] = contato.get(q["chave"])
        elif demo and "DEPUTADO FEDERAL" in q["cargo"]:
            ctx["contato"] = contatos.DEMO
        out[q["idx"][0]] = ctx
    return out


def montar_equipe(pessoas, parl, cache=None, demo=False):
    """{indice da primeira linha: dict(pessoas, link) ou None} da equipe do gabinete (#66). So entra parlamentar
    federal em exercicio com pagina; None = fonte fora do ar ("Fonte nao encontrada")."""
    em_exercicio = {x["_chave"] for x in parl if x["_chave"]}
    chaves = {q["chave"] for q in pessoas.values()} & em_exercicio
    equipe = gabinete.coletar(parl, chaves, cache) if chaves else {}
    out = {}
    for q in pessoas.values():
        if q["chave"] in em_exercicio:
            out[q["idx"][0]] = equipe.get(q["chave"])
        elif demo and "DEPUTADO FEDERAL" in q["cargo"]:
            out[q["idx"][0]] = gabinete.DEMO
    return out


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

    # cache incremental entre execucoes (data/cache, actions/cache): so com ID_SEGREDO, que assina e cifra
    seg_cache = None if args.demo else os.getenv("ID_SEGREDO")
    if seg_cache:  # tudo que fica salvo e cifrado (cifra.py): sobras em texto puro de execucoes antigas saem
        cifra.limpar_puros(CACHE)
    caches = dict(tse=Cache(CACHE / "tse_lido.cache", 400 * 86400, seg_cache, cifrar=True),
                  portal=Cache(CACHE / "portal.cache", 7 * 86400, seg_cache, cifrar=True),
                  portal_bom=Cache(CACHE / "portal_bom.cache", 400 * 86400, seg_cache),  # ultima resposta completa
                  noticias=Cache(CACHE / "noticias.cache", 3 * 86400, seg_cache),
                  pares=Cache(CACHE / "pares.cache", 400 * 86400, seg_cache),
                  contatos=Cache(CACHE / "contatos.cache", contatos.VALIDADE_S, seg_cache),
                  gabinete=Cache(CACHE / "gabinete.cache", gabinete.VALIDADE_S, seg_cache)) if seg_cache else {}
    serie = serie_demo() if args.demo else serie_tse(p["anos"], caches.get("tse"))
    extras = {r.chave: extras_cfg.get(r.chave, extras_cfg.get("nome:" + norm(r.nome), 0.0))
              for r in serie.drop_duplicates("chave").itertuples()}
    df = pares(serie, regras, extras, p, cache=caches.get("pares"))
    if df.empty:
        sys.exit("Nenhuma pessoa com duas declaracoes consecutivas.")
    df["monitorado"] = df.apply(lambda r: r.chave in cpfs or norm(r.nome) in nomes, axis=1)
    # presidente e vice em exercicio sempre entram nos destaques, mesmo sem nivel; topo ordena (2 presidente, 1 vice) (#63)
    for campo, cargo in (("presidente_atual", "PRESIDENTE"), ("vice_atual", "VICE-PRESIDENTE")):
        chave = em_exercicio(serie, cargo)
        df[campo] = df["chave"].eq(chave) if chave else False
    df["topo"] = df.presidente_atual * 2 + df.vice_atual
    mandato = em_mandato(serie)  # carimbo verde "Eleito <ano>" nos cards (#67)
    df["eleito_atual"] = df["chave"].isin(list(mandato))
    df["eleito_ano"] = df["chave"].map(mandato).astype("Int64")
    alertas = df[df.nivel.notna() | df.topo.gt(0)].copy()

    # memoria de alertas por id interno (versoes antigas usavam o CPF na chave: sao descartadas)
    try:  # cifrado (cifra.py); o arquivo antigo em texto puro e lido uma vez e regravado cifrado no fim
        bruto = cifra.ler(estado_arq, segredo, aceitar_puro=True) if segredo else None
        estado = {k: v for k, v in json.loads(bruto or b"{}").items() if re.match(r"p\d+\|", k)}
    except (OSError, ValueError):
        estado = {}
    alertas["pessoa"] = alertas.chave.map(pid) if pid else None
    alertas["id"] = (alertas.pessoa.astype(str) + "|" + alertas.ano_ini.astype(str) + "-" + alertas.ano_fim.astype(str)
                     if pid else None)
    alertas["novo"] = alertas.apply(lambda r: ORDEM.get(r.nivel, 0) > ORDEM.get(estado.get(r.id, ""), 0), axis=1)

    so_lista = bool(p["publicar_somente_monitorados"] and (cpfs or nomes))  # trava: so quem esta na lista
    if so_lista:
        vis = alertas[alertas.monitorado]
    else:
        vis = alertas.assign(o=alertas.nivel.map(ORDEM).fillna(0)).sort_values(["o", "percentil"], ascending=False) \
                     .head(p["max_linhas_sem_lista"]).drop(columns="o")
        # o limite de linhas nao tira presidente nem vice; a trava da lista de monitorados vale para todos
        vis = pd.concat([vis, alertas[alertas.topo.gt(0) & ~alertas.index.isin(vis.index)]])
    vis = vis.assign(o=vis.nivel.map(ORDEM).fillna(0)).sort_values(["topo", "novo", "o", "cresc"],
                                                                     ascending=False).drop(columns="o")

    # todos os deputados federais e senadores em exercicio: cota, projetos, selo e estrela de exemplar (#44, #45)
    hoje = dt.date.today().year
    try:
        parl, parl_ctx = ([], {}) if args.demo else parlamentares.montar(
            df, range(hoje - 3, hoje + 1), CACHE, os.getenv("TRANSPARENCIA_TOKEN"))
    except Exception as ex:
        print(f"[aviso] lista de parlamentares indisponivel ({ex!r})", file=sys.stderr)
        parl, parl_ctx = [], {}
    # pagina propria tambem para quem esta em exercicio e nao e destaque (mesmo tratamento para todos): entram
    # depois dos destaques, marcados `so_pagina`, e saem do painel antes de grava-lo
    extras = set() if so_lista else {x["_chave"] for x in parl if x["_chave"]} - set(vis.chave)  # trava vale aqui tambem
    todas = pd.concat([vis, so_paginas(df, extras, pid)])
    print(f"Paginas: {len(vis)} destaques + {len(todas) - len(vis)} parlamentares em exercicio fora dos destaques.")

    pub = todas.drop(columns=["chave", "id", "cargo_ini", "empresas_cnpj"])  # CPF/CNPJ nunca vao para o site
    pub = pub.astype(object).where(pub.notna(), None)
    dados = dict(gerado_em=dt.datetime.now().strftime("%Y-%m-%d %H:%M"), universo=int(len(df)),
                 alertas=json.loads(pub.to_json(orient="records")))
    docs.mkdir(parents=True, exist_ok=True)
    fontes = carregar_fontes()
    dados["repo"] = os.getenv("GITHUB_REPOSITORY")  # links "sugerir fonte" do painel
    dados["metodo"] = dict(taxa=p["taxa_poupanca"], minimo=p["crescimento_minimo"], forte=p["limiar_forte"],
                           atencao=p["limiar_atencao"], informativo=p["limiar_informativo"],
                           min_pares=p["min_pares_grupo"],
                           formula="vezes")  # texto "Como ler"; "vezes" (#62) avisa a tela que as faixas ja usam a conta nova
    dados["fontes"] = [dict(nome=f["nome"], uf=f["uf"]) for f in fontes]
    # Portal da Transparencia: uma consulta por pessoa (nome+UF), na ordem do painel; CPF/CNPJ ficam so aqui
    pessoas = {}
    for i, r in enumerate(todas.to_dict("records")):
        q = pessoas.setdefault((norm(r["nome"]), str(r["uf"]).upper()), dict(
            nome=r["nome"], nome_urna=txt(r.get("nome_urna")), cargo="", idx=[], chave=r["chave"],
            cpf=r["chave"][4:] if str(r["chave"]).startswith("cpf:") else "", empresas=r.get("empresas_cnpj") or []))
        q["cargo"] += " " + str(r["cargo"])
        q["idx"].append(i)
    try:  # o Portal nunca derruba a atualizacao: se falhar, a secao sai "Fonte nao encontrada"
        info = {} if args.demo else transparencia.coletar(pessoas, chave_api=os.getenv("TRANSPARENCIA_TOKEN"),
                                                          cache=caches.get("portal"), bom=caches.get("portal_bom"))
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
    # projetos apresentados e aprovados (Camara: arquivos abertos; Senado: API) e o selo "Mao na massa";
    # as contagens e o corte do selo sao os mesmos da lista de parlamentares
    try:
        proj = {} if args.demo else projetos.coletar(pessoas, range(hoje - 3, hoje + 1), CACHE,
                                                     camara=parl_ctx.get("camara"), senado=parl_ctx.get("senado"),
                                                     membros=parl_ctx.get("membros"))
    except Exception as ex:
        print(f"[aviso] projetos de lei indisponiveis ({ex!r})", file=sys.stderr)
        proj = {}
    # quem esta em exercicio (parlamentares.py, ligado pelo CPF ou por nome e UF) usa as contagens da sua casa, mesmo
    # que o cargo do periodo no TSE seja outro (deputado candidato a senador ou a prefeito): selo e projetos juntos
    parl_chave = {x["_chave"]: x for x in parl if x["_chave"] and x.get("apresentados") is not None}
    for k, q in pessoas.items():
        x = parl_chave.get(q["chave"])
        if x:
            proj[k] = dict(casa=x["casa"], apresentados=x["apresentados"], aprovados=x["aprovados"], selo=x["selo"],
                           link=x.get("proj_link"), de=x["proj_de"], ate=x["proj_ate"])
    n_proj = [v for k, v in proj.items() if k != "_fontes"]
    print(f"Projetos de lei nos destaques: {len(n_proj)} pessoas com contagem "
          f"({sum(q['chave'] in parl_chave for q in pessoas.values())} pela lista de parlamentares em exercicio), "
          f"{sum(bool(v['selo']) for v in n_proj)} com o selo {projetos.SELO}.")
    secoes_proj = {}
    for k, q in pessoas.items():
        try:
            html_proj = projetos.secao(proj.get(k), q["cargo"], proj.get("_fontes"))
        except Exception as ex:
            print(f"[aviso] secao de projetos falhou para {q['nome']} ({ex!r})", file=sys.stderr)
            html_proj = '<p class="vazio"><b>Não informado</b>.</p>'
        secoes_proj.update({i: html_proj for i in q["idx"]})
        r = proj.get(k)
        for i in q["idx"] if r else ():  # contagem no card: projetos apresentados e aprovados (deputado/senador)
            dados["alertas"][i]["projetos"] = dict(apresentados=r["apresentados"], aprovados=r["aprovados"],
                                                   de=r["de"], ate=r["ate"], link=r["link"])
            if r["selo"]:
                dados["alertas"][i]["selo"] = True
    # como votou (#56) e presenca (#58): todos os parlamentares em exercicio (a media da casa usa todos); nos
    # destaques, quem esta em exercicio e ligado pela chave (CPF ou nome e UF), como em projetos
    try:
        pres_ctx = presenca.anotar(parl, CACHE) if parl else {}
        vot_ctx = votacoes.anotar(parl, cache=CACHE, ativo=pres_ctx.get("ativo")) if parl else {}
    except Exception as ex:
        print(f"[aviso] votacoes ou presenca indisponiveis ({ex!r})", file=sys.stderr)
        pres_ctx, vot_ctx = {}, {}
    por_chave = {x["_chave"]: x for x in parl if x["_chave"]}
    secoes_votos = {}
    for k, q in pessoas.items():
        x = por_chave.get(q["chave"]) or (votacoes.demo(q["cargo"]) if args.demo else {})
        try:
            html_v = (votacoes.secao(x.get("votos"), q["cargo"], vot_ctx, nome=cap(q["nome_urna"] or q["nome"])),
                      presenca.secao(x.get("presenca"), q["cargo"], pres_ctx.get("fontes"), x.get("casa")))
        except Exception as ex:
            print(f"[aviso] secao de votacoes falhou para {q['nome']} ({ex!r})", file=sys.stderr)
            html_v = ('<p class="vazio"><b>Não informado</b>.</p>',) * 2
        secoes_votos.update({i: html_v for i in q["idx"]})
        for i in q["idx"]:  # card: so o resumo (presenca e quantos temas votou); o detalhe fica no dossie
            for campo in ("presenca", "votos"):
                if x.get(campo):
                    dados["alertas"][i][campo] = x[campo]
    # parlamentares exemplares (estrela): patrimonio compativel, cota abaixo da media e sem sancoes
    # entre todos os parlamentares em exercicio (parlamentares.py), nao so os destaques
    # None: lista de parlamentares indisponivel (secao escondida); []: ninguem cumpre os criterios (mensagem)
    dados["exemplares"] = parlamentares.lista_exemplares(parl) if parl else None
    estrelas = {p["_chave"] for p in parl if p.get("exemplar") and p["_chave"]}
    selos = {ch for ch, x in parl_chave.items() if x.get("selo")}  # selo so com os projetos no card
    for i, ch in enumerate(todas["chave"]):
        if ch in estrelas:
            dados["alertas"][i]["exemplar"] = True
        if ch in selos:
            dados["alertas"][i]["selo"] = True
    # empresas declaradas: atividade, fundacao, capital e situacao nos dados abertos do CNPJ (Receita);
    # o CNPJ so cruza as bases aqui dentro e nunca vai para o site
    cnpjs = {c for q in pessoas.values() for _, c in q["empresas"]}
    try:
        receita = {} if args.demo or not cnpjs else empresas.coletar(cnpjs, CACHE)
    except Exception as ex:
        print(f"[aviso] dados do CNPJ indisponiveis ({ex!r})", file=sys.stderr)
        receita = {}
    secoes_receita = {}
    for q in pessoas.values():
        if not q["empresas"]:
            continue
        ult = max((dados["alertas"][i] for i in q["idx"]), key=lambda a: a.get("ano_fim") or 0)
        try:
            html_rec = "<h3>Dados das empresas na Receita Federal</h3>" + empresas.secao(
                q["empresas"], receita, int(ult.get("ano_ini") or 0))
        except Exception as ex:
            print(f"[aviso] secao de empresas falhou para {q['nome']} ({ex!r})", file=sys.stderr)
            html_rec = ""
        secoes_receita.update({i: html_rec for i in q["idx"]})
    # processos em que a pessoa e re (lista curada por issue): casa pelo nome civil ou de urna + UF;
    # desligado (#51) ate haver base oficial e gratuita por CPF: nem le a lista nem publica
    dados["processos_ativo"] = dossie.PROCESSOS_ATIVO
    processos = carregar_processos() if dossie.PROCESSOS_ATIVO else {}
    for a in dados["alertas"] if processos else ():
        uf = str(a.get("uf") or "").upper()
        achou = processos.get((norm(a.get("nome")), uf)) or processos.get((norm(a.get("nome_urna")), uf))
        if achou:
            a["processos"] = achou
    bens = carregar_bens()
    noticias = {}  # {indice: noticias com tags} para a aba Noticias (#54); fora do JSON do painel
    for i, cam in gerar_dossies(dados["alertas"], docs, buscar=not args.demo, fontes_extra=fontes,
                                transparencia=secoes, bens=bens, cota=secoes_cota, receita=secoes_receita,
                                cache=caches.get("noticias"), projetos=secoes_proj, noticias=noticias,
                                votos=secoes_votos).items():
        dados["alertas"][i]["dossie"] = cam
    if args.demo:  # noticias ficticias para ver a aba sem internet
        noticias = {i: temas.demo(i) for i in noticias}
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
    # painel: quem mais apresentou e aprovou projetos (entre as pessoas em destaque)
    ranking = []
    for k, q in pessoas.items():
        r = proj.get(k)
        if r and r["apresentados"]:
            a = dados["alertas"][q["idx"][0]]
            ranking.append(dict(nome=q["nome_urna"] or q["nome"], cargo=a.get("cargo"), partido=a.get("partido"),
                                uf=k[1], apresentados=r["apresentados"], aprovados=r["aprovados"], selo=r["selo"],
                                de=r["de"], ate=r["ate"], link=r["link"], dossie=a.get("dossie")))
    dados["projetos"] = sorted(ranking, key=lambda x: (-x["aprovados"], -x["apresentados"]))[:10]
    if parl:  # com a lista de todos os parlamentares em exercicio, os rankings comparam a casa inteira
        dossies = {ch: dados["alertas"][i].get("dossie") for i, ch in enumerate(todas["chave"])}
        for p in parl:
            p["dossie"] = dossies.get(p["_chave"])
        dados["cota"] = parlamentares.ranking_cota(parl) or dados["cota"]
        dados["projetos"] = parlamentares.ranking_projetos(parl) or dados["projetos"]

    # como cobrar (#60): canais oficiais do gabinete (so de quem tem pagina), cota e projetos para o texto sugerido
    cobranca = {}
    try:
        cobranca = montar_cobranca(pessoas, parl, ceap, proj, caches.get("contatos"), args.demo)
    except Exception as ex:  # sem contatos a aba sai com "Fonte nao encontrada"; nunca derruba o painel
        print(f"[aviso] contatos de gabinete indisponiveis ({ex!r})", file=sys.stderr)
    # equipe do gabinete (#66): so o numero de pessoas; nomes e salarios ficam na fonte oficial
    equipe = {}
    try:
        equipe = montar_equipe(pessoas, parl, caches.get("gabinete"), args.demo)
    except Exception as ex:  # sem a contagem o bloco nao aparece; nunca derruba o painel
        print(f"[aviso] equipe de gabinete indisponivel ({ex!r})", file=sys.stderr)
    for q in pessoas.values():  # card: so o numero, em "Ver detalhes"
        r = equipe.get(q["idx"][0])
        for i in q["idx"] if r and r.get("pessoas") else ():
            dados["alertas"][i]["gabinete"] = r
    cartoes, graficos_painel = "", {}
    if pid:  # uma pagina por pessoa (docs/pessoa/<id>.html), so com o id interno
        hist = {c: sorted((int(a), float(v)) for a, v in zip(g.ano, g.patrimonio))
                for c, g in serie[serie.chave.isin(set(todas.chave))].groupby("chave")}
        try:
            cartoes, graficos_painel = paginas.gerar(dados["alertas"], pessoas, hist, secoes, docs,
                                                     gerado=dados["gerado_em"], noticias=noticias,
                                                     cobranca=cobranca, votos=secoes_votos, equipe=equipe)
        except Exception as ex:  # nunca derruba o painel
            print(f"[aviso] paginas por pessoa falharam ({ex!r})", file=sys.stderr)
        try:  # Acompanhar (#57): feed RSS por pessoa e geral, com um item quando um dado muda entre execucoes
            n_feeds, novos = acompanhar.publicar(docs, dados_dir / "acompanhar.json", segredo, dados["alertas"],
                                                 pessoas, ceap, noticias)
            print(f"Acompanhar: {n_feeds} feeds, {len(novos)} avisos novos.")
        except Exception as ex:
            print(f"[aviso] feeds de acompanhamento falharam ({ex!r})", file=sys.stderr)
    # lista completa leve (#43): todas as pessoas com duas declaracoes, em arquivo separado (docs/todos.json)
    pag = {}
    for i, ch in enumerate(todas["chave"]):
        a = dados["alertas"][i]
        v = a.get("pagina") if REL_OK(a.get("pagina")) else a.get("dossie") if REL_OK(a.get("dossie")) else None
        if v:
            pag.setdefault(ch, v)
    try:
        marcas = {p["_chave"]: ("e" if p.get("exemplar") else "") + ("s" if p.get("selo") else "") for p in parl if p["_chave"]}
        dados["todos"] = gravar_todos(docs, df[df.monitorado] if so_lista else df, pag, dados["gerado_em"], {k: v for k, v in marcas.items() if v})
    except Exception as ex:  # nunca derruba o painel: sem o arquivo, a secao da lista fica escondida
        print(f"[aviso] lista completa falhou ({ex!r})", file=sys.stderr)
    # dossie por estado (#53): roda no proprio workflow (estados.yml), depois deste; aqui so a base que ele usa
    # (parlamentares em exercicio e deputados estaduais, sem CPF). No --demo gera as paginas com dados mockados
    try:
        if args.demo:
            uf_pag, uf_extra = estados.demo(parl, serie, pag)
            print(f"Dossie por estado (demo): {estados.gerar(docs, uf_pag, uf_extra, dados['gerado_em'])} paginas.")
        else:
            dados_dir.mkdir(parents=True, exist_ok=True)
            (dados_dir / estados.BASE.name).write_text(json.dumps(estados.base(parl, serie, pag, link_tse,
                                                                              eleitos=em_mandato(serie)),
                                                                  ensure_ascii=False), encoding="utf-8")
    except Exception as ex:
        print(f"[aviso] base do dossie por estado falhou ({ex!r})", file=sys.stderr)
    # meus representantes (#59): um arquivo leve por estado, baixado so quando o visitante escolhe o estado
    try:
        extra = representantes.faixas(df, pag)  # faixa do patrimonio e "esta na lista completa", por chave
        parl_uf, tse_uf, ano_est = (representantes.demo() if args.demo else
                                    (parl, *representantes.eleitos(serie, link_tse, link_foto, pag, extra=extra)))
        contato = ({(p["casa"], p["_id"]): contatos.DEMO for p in parl_uf[::5]} if args.demo else
                   representantes.contatos_de(parl_uf, caches.get("contatos")))
        cid, ano_mun = (representantes.demo_cidades() if args.demo else
                        representantes.cidades(serie, link_tse, link_foto, pag, extra=extra))
        representantes.gravar_cidades(docs, cid, ano_mun)
        dados["representantes"] = representantes.gravar(docs, parl_uf, tse_uf, dados["gerado_em"], ano_est,
                                                         contato, contatos.assembleias(),
                                                         representantes.lista_cidades(cid), extra)
        shutil.copyfile(ROOT / "src" / "representantes.js", docs / "representantes.js")
    except Exception as ex:  # nunca derruba o painel: sem os arquivos, o bloco mostra "Fonte não encontrada"
        print(f"[aviso] meus representantes falhou ({ex!r})", file=sys.stderr)
    # aba Estados (#68): ranking dos estados pelos parlamentares em exercicio; sem lista, a aba fica em ordem alfabetica
    try:
        dados["estados_rank"] = ranking_uf.montar(representantes.demo()[0] if args.demo else parl,
                                                  ranking_uf.ultimo_periodo(df))
    except Exception as ex:
        print(f"[aviso] ranking dos estados falhou ({ex!r})", file=sys.stderr)
    # indicadores do IBGE na aba Estados (#68): Brasil e estados; sem dado, o bloco fica escondido
    try:
        dados["ibge"] = ibge.demo() if args.demo else ibge.coletar(
            Cache(CACHE / "ibge.cache", 400 * 86400, seg_cache) if seg_cache else None)
    except Exception as ex:
        print(f"[aviso] indicadores do IBGE falharam ({ex!r})", file=sys.stderr)
    paginas.copiar_estilo(docs)
    dados["alertas"] = [a for a in dados["alertas"] if not a.get("so_pagina")]  # extras: so a pagina propria
    # ordem do painel: mais mencoes atuais na imprensa (Brasil e exterior) primeiro, depois maior crescimento
    dados["alertas"].sort(key=lambda a: (-(a.get("topo") or 0), -(a.get("mencoes") or 0), -(a.get("cresc") or 0)))
    tpl = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
    html_painel = tpl.replace("/*DADOS*/null", json.dumps(arredonda(dados), ensure_ascii=False))
    html_painel = html_painel.replace("/*BENS*/null", json.dumps(bens, ensure_ascii=False))
    blocos = dict(CARTOES=cartoes, **graficos_painel)
    for marca, conteudo in blocos.items():
        html_painel = html_painel.replace(f"<!--{marca}-->", conteudo)
    # blocos gerados a parte: o workflow "3 · Publicar site" remonta o index com o template atual
    (docs / "blocos.json").write_text(json.dumps(blocos, ensure_ascii=False), encoding="utf-8")
    (docs / "index.html").write_text(html_painel, encoding="utf-8")
    if pid:
        dados_dir.mkdir(parents=True, exist_ok=True)
        cifra.gravar(estado_arq, json.dumps({r.id: r.nivel for r in alertas.itertuples()}, ensure_ascii=False).encode(), segredo)
        pid.salvar()
    salvar_resultados()  # resumos dos anos fechados (cota, projetos; #48), cifrados em data/cache

    novos = vis[vis.novo]
    resumo = f"Caramelo Vasculha {dados['gerado_em']}: {len(vis)} destaques, {len(novos)} novos."
    for r in novos.head(15).itertuples():
        resumo += f"\n- [{r.nivel}] {r.nome} ({r.cargo}/{r.uf}) {r.ano_ini}->{r.ano_fim}: +R$ {r.cresc:,.0f}"
    (docs / "digest.txt").write_text(resumo, encoding="utf-8")
    # ultima barreira: nenhum CPF/CNPJ sai no site, mesmo que venha dentro de um texto de fonte externa
    n = varrer(docs, cpfs=[q["cpf"] for q in pessoas.values() if q.get("cpf")] + [p["_cpf"] for p in parl if p["_cpf"]])
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
