#!/usr/bin/env python3
"""Alerta patrimonial: compara o crescimento do patrimonio declarado ao TSE entre
eleicoes com a capacidade de acumulacao estimada e com o grupo de pares.
Resultado = INDICIO para acompanhamento, nao prova."""
import argparse, json, os, re, sys, unicodedata, urllib.request, urllib.parse, zipfile
import datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE, DOCS, CFG = ROOT / "data" / "cache", ROOT / "docs", ROOT / "config"
ESTADO = ROOT / "data" / "estado.json"
BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
ORDEM = {"forte": 3, "atencao": 2, "informativo": 1}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


# ---------------------------------------------------------------- coleta TSE
def baixar(tipo, ano):
    dest = CACHE / f"{tipo}_{ano}.zip"
    if dest.exists() and ano < dt.date.today().year:  # ano corrente muda: rebaixa
        return dest
    CACHE.mkdir(parents=True, exist_ok=True)
    url = f"{BASE}/{tipo}/{tipo}_{ano}.zip"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "alerta-patrimonial/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
            f.write(r.read())
        return dest
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


def serie_tse(anos):
    """Uma linha por pessoa e eleicao: patrimonio total declarado."""
    partes = []
    for ano in anos:
        zb, zc = baixar("bem_candidato", ano), baixar("consulta_cand", ano)
        if not zb or not zc:
            continue
        bens, cand = ler_zip(zb), ler_zip(zc)
        bens["VR"] = dinheiro(bens["VR_BEM_CANDIDATO"])
        pat = bens.groupby("SQ_CANDIDATO", as_index=False)["VR"].sum().rename(columns={"VR": "patrimonio"})
        cand = cand.drop_duplicates("SQ_CANDIDATO").copy()
        cand["chave"] = cand.apply(chave_pessoa, axis=1)
        m = cand.merge(pat, on="SQ_CANDIDATO", how="inner")
        m["ano"] = int(ano)
        sit = m["DS_SIT_TOT_TURNO"] if "DS_SIT_TOT_TURNO" in m else pd.Series("", index=m.index)
        m["eleito"] = sit.astype(str).str.upper().str.startswith("ELEITO")
        partes.append(m.rename(columns={"NM_CANDIDATO": "nome", "DS_CARGO": "cargo",
                                        "SG_UF": "uf", "SG_PARTIDO": "partido"})
                       [["chave", "ano", "nome", "cargo", "uf", "partido", "eleito", "patrimonio"]])
    if not partes:
        sys.exit("Nenhum dado do TSE disponivel. Verifique a conexao e os anos em config/parametros.json.")
    return pd.concat(partes, ignore_index=True)


def serie_demo(seed=7):
    import random
    random.seed(seed)
    linhas = []
    for i in range(400):
        base = random.lognormvariate(12.5, 1.0)
        f = random.lognormvariate(0.35, 0.35)
        if i == 1:
            f = 25.0  # caso extremo
        linhas.append(dict(chave=f"demo:{i}", ano=2018, nome=f"PESSOA DEMO {i:03d}", cargo="DEPUTADO FEDERAL",
                           uf=random.choice(["PA", "SP", "MG", "BA"]), partido="XX", eleito=True, patrimonio=base))
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
                            cresc=b["patrimonio"] - a["patrimonio"], cap=cap, cargo_ini=a["cargo"]))
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
    df["nivel"] = df.apply(lambda r: nivel(r, p), axis=1)
    return df


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
    f = CFG / "monitorados.csv"
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="dados sinteticos para testar sem internet")
    args = ap.parse_args()
    p = json.loads((CFG / "parametros.json").read_text())
    regras = pd.read_csv(CFG / "renda_publica.csv")
    cpfs, nomes, extras_cfg = carregar_monitorados()

    serie = serie_demo() if args.demo else serie_tse(p["anos"])
    extras = {r.chave: extras_cfg.get(r.chave, extras_cfg.get("nome:" + norm(r.nome), 0.0))
              for r in serie.drop_duplicates("chave").itertuples()}
    df = pares(serie, regras, extras, p)
    if df.empty:
        sys.exit("Nenhuma pessoa com duas declaracoes consecutivas.")
    df["monitorado"] = df.apply(lambda r: r.chave in cpfs or norm(r.nome) in nomes, axis=1)
    alertas = df[df.nivel.notna()].copy()

    estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    alertas["id"] = alertas.chave + "|" + alertas.ano_ini.astype(str) + "-" + alertas.ano_fim.astype(str)
    alertas["novo"] = alertas.apply(lambda r: ORDEM[r.nivel] > ORDEM.get(estado.get(r.id, ""), 0), axis=1)

    if p["publicar_somente_monitorados"] and (cpfs or nomes):
        vis = alertas[alertas.monitorado]
    else:
        vis = alertas.assign(o=alertas.nivel.map(ORDEM)).sort_values(["o", "percentil"], ascending=False) \
                     .head(p["max_linhas_sem_lista"]).drop(columns="o")
    vis = vis.assign(o=vis.nivel.map(ORDEM)).sort_values(["novo", "o", "cresc"], ascending=False).drop(columns="o")

    pub = vis.drop(columns=["chave", "id", "cargo_ini"])  # CPF nunca vai para o site
    pub = pub.astype(object).where(pub.notna(), None)
    dados = dict(gerado_em=dt.datetime.now().strftime("%Y-%m-%d %H:%M"), universo=int(len(df)),
                 alertas=json.loads(pub.to_json(orient="records")))
    DOCS.mkdir(exist_ok=True)
    tpl = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
    (DOCS / "index.html").write_text(tpl.replace("/*DADOS*/null", json.dumps(dados, ensure_ascii=False)),
                                      encoding="utf-8")
    ESTADO.write_text(json.dumps({r.id: r.nivel for r in alertas.itertuples()}, ensure_ascii=False))

    novos = vis[vis.novo]
    resumo = f"Alerta patrimonial {dados['gerado_em']}: {len(vis)} alertas visiveis, {len(novos)} novos."
    for r in novos.head(15).itertuples():
        resumo += f"\n- [{r.nivel}] {r.nome} ({r.cargo}/{r.uf}) {r.ano_ini}->{r.ano_fim}: +R$ {r.cresc:,.0f}"
    (DOCS / "digest.txt").write_text(resumo, encoding="utf-8")
    print(resumo)
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
