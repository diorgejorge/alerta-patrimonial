"""Parlamentares exemplares (estrela): deputados federais e senadores em exercicio que, no periodo mais recente do
mandato, cumprem os tres criterios:
  1. patrimonio compativel: crescimento dentro do que o salario do cargo permitiria (ate 1x o possivel);
  2. cota parlamentar abaixo da media de quem tem o mesmo cargo (ultimos 4 anos);
  3. sem sancoes: nao consta no CEIS, CNEP nem CEAF (API do Portal da Transparencia).
Sem dado para algum criterio (API fora do ar, cota nao encontrada, sem declaracao no TSE): nao ganha a estrela.
A lista de parlamentares vem de parlamentares.py; o CPF so liga as bases aqui dentro."""
import sys, time
import pandas as pd
import cota
import transparencia

CARGOS = {"DEPUTADO FEDERAL": "camara", "SENADOR": "senado"}


def ultimos(df):
    """Linha de pares (pipeline.pares) do periodo mais recente de cada pessoa que comecou como deputado federal ou
    senador, com ou sem patrimonio compativel."""
    if df.empty:
        return df
    c = df[df["cargo_ini"].map(cota.norm).isin(CARGOS)]
    return c.sort_values("ano_fim").drop_duplicates("chave", keep="last")


def compativel(cresc, cap, razao):
    """True se o crescimento cabe no que o salario permitiria; False se passa; None sem salario de referencia."""
    if cap is None or pd.isna(cap) or cap <= 0 or cresc is None or pd.isna(cresc):
        return None
    return bool(cresc <= 0 or (razao is not None and not pd.isna(razao) and razao <= 1))


def sancoes(api, cpf):
    """Lista de cadastros de sancao em que o CPF consta; None se a API nao respondeu."""
    pf = api.get("/pessoa-fisica", cpf=cpf)
    if isinstance(pf, list):
        pf = pf[0] if pf else {}
    if pf is None:
        return None
    return [rot for f, rot in transparencia.SANCOES_PF if pf.get(f)]


def avaliar(lista, media, chave_api, tempo_max=10 * 60, max_consultas=600):
    """lista: dicts de parlamentares.py (com "_cpf", "patrimonio_ok", "cota" e "casa"). Preenche "criterios" e
    "exemplar" em cada um; as sancoes so sao consultadas para quem passou nos dois primeiros criterios."""
    api = transparencia.Api(chave_api, time.monotonic() + tempo_max) if chave_api else None
    for p in lista:
        m = (media or {}).get(p["casa"])
        c_cota = None if p.get("cota") is None or m is None else bool(p["cota"] < m)
        c_sanc = None
        if p.get("patrimonio_ok") and c_cota and p.get("_cpf") and api and api.ativa() and api.req < max_consultas:
            s = sancoes(api, p["_cpf"])
            c_sanc = None if s is None else not s
        p["cota_media"] = None if m is None else round(m, 2)
        p["criterios"] = dict(patrimonio=p.get("patrimonio_ok"), cota=c_cota, sancoes=c_sanc)
        p["exemplar"] = bool(p.get("patrimonio_ok") and c_cota and c_sanc)
    n = sum(p["exemplar"] for p in lista)
    print(f"Exemplares: {len(lista)} parlamentares, {sum(bool(p.get('patrimonio_ok')) for p in lista)} com patrimonio "
          f"compativel, {n} com os tres criterios"
          + (f" ({api.req} consultas ao Portal, {api.falhas} falhas)." if api else "; sem TRANSPARENCIA_TOKEN, sancoes nao consultadas."),
          file=sys.stdout)
    return n
