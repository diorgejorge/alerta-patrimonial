"""Parlamentares exemplares (estrela): deputados federais e senadores que, no periodo mais recente do mandato,
cumprem os tres criterios:
  1. patrimonio compativel: crescimento dentro do que o salario do cargo permitiria (ate 1x o possivel);
  2. cota parlamentar abaixo da media de quem tem o mesmo cargo (ultimos 4 anos);
  3. sem sancoes: nao consta no CEIS, CNEP nem CEAF (API do Portal da Transparencia).
Sem dado para algum criterio (API fora do ar, cota nao encontrada): nao ganha a estrela.
O CPF so liga as bases aqui dentro; o resultado leva nome, cargo, partido e UF."""
import sys, time
import pandas as pd
import cota
import transparencia

CARGOS = {"DEPUTADO FEDERAL": "camara", "SENADOR": "senado"}


def candidatos(df):
    """Linhas de pares (pipeline.pares) do periodo mais recente de cada parlamentar com patrimonio compativel."""
    if df.empty:
        return df
    c = df[df["cargo_ini"].map(cota.norm).isin(CARGOS) & df["cap"].notna() & (df["cap"] > 0)]
    c = c[(c["cresc"] <= 0) | (c["razao"] <= 1)]
    return c.sort_values("ano_fim").drop_duplicates("chave", keep="last")


def sancoes(api, cpf):
    """Lista de cadastros de sancao em que o CPF consta; None se a API nao respondeu."""
    pf = api.get("/pessoa-fisica", cpf=cpf)
    if isinstance(pf, list):
        pf = pf[0] if pf else {}
    if pf is None:
        return None
    return [rot for f, rot in transparencia.SANCOES_PF if pf.get(f)]


def calcular(df, anos, cache, chave_api, tempo_max=10 * 60, max_pessoas=600):
    """Lista de exemplares (dicts prontos para o painel) e o conjunto de chaves internas que ganharam a estrela."""
    cand = candidatos(df)
    if cand.empty or not chave_api:
        print(f"Exemplares: {len(cand)} com patrimonio compativel; "
              + ("sem TRANSPARENCIA_TOKEN, sancoes nao consultadas." if not chave_api else "nenhum candidato."))
        return [], set()
    media = cota.medias(anos, cache)
    pessoas = {r.chave: dict(nome=r.nome, nome_urna=r.nome_urna or "", cargo=r.cargo_ini,
                             cpf=r.chave[4:] if str(r.chave).startswith("cpf:") else "")
               for r in cand.itertuples()}
    gastos = cota.coletar(pessoas, anos, cache)
    api = transparencia.Api(chave_api, time.monotonic() + tempo_max)
    out, chaves = [], set()
    for r in cand.itertuples():
        if len(out) >= max_pessoas or not api.ativa():
            break
        casa = CARGOS[cota.norm(r.cargo_ini)]
        g, m = gastos.get(r.chave), media.get(casa)
        if not g or m is None or g["total"] >= m:
            continue
        cpf = pessoas[r.chave]["cpf"]
        if not cpf:
            continue  # sem CPF no TSE nao da para consultar sancoes com seguranca
        s = sancoes(api, cpf)
        if s is None or s:
            continue
        chaves.add(r.chave)
        out.append(dict(nome=r.nome_urna or r.nome, cargo=r.cargo_ini, partido=r.partido, uf=r.uf,
                        ano_ini=int(r.ano_ini), ano_fim=int(r.ano_fim), cresc=float(r.cresc), cap=float(r.cap),
                        razao=None if pd.isna(r.razao) else float(r.razao), cota=round(g["total"], 2),
                        cota_media=round(m, 2), link=g["link"]))
    out.sort(key=lambda x: (x["razao"] if x["razao"] is not None else -1, x["cota"] / x["cota_media"]))
    print(f"Exemplares: {len(cand)} com patrimonio compativel, {len(out)} com cota abaixo da media e sem sancoes "
          f"({api.req} consultas ao Portal, {api.falhas} falhas).", file=sys.stdout)
    return out, chaves
