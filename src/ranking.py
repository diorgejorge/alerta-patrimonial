"""Ranking dos estados na aba Estados (#68). Base: deputados federais e senadores em exercicio de cada estado.
Ordem (formula publicada em funcionamento.html):
  1. maior fatia com o selo Exemplar e fora das faixas de cor
  2. maior fatia fora das faixas de cor
  3. menor mediana do crescimento do patrimonio (ultimo periodo de cada um no TSE)
  4. ordem alfabetica do estado
So contagens e percentuais: nada de nome, CPF ou chave sai daqui."""
from statistics import median
from estados import UFS, norm

FAIXAS = {"forte", "atencao", "informativo"}


def ultimo_periodo(df):
    """{chave: (nivel, crescimento em %)} do periodo mais recente de cada pessoa (df de pipeline._classifica)."""
    if df is None or df.empty:
        return {}
    ult = df.sort_values(["ano_fim", "ano_ini"]).groupby("chave").tail(1)
    return {r.chave: (r.nivel if isinstance(r.nivel, str) else None, float(r.razao) * 100 if r.razao == r.razao else None)
            for r in ult.itertuples()}


def _linha(uf, pessoas, faixa):
    total = len(pessoas)
    marcados = [faixa.get(p.get("_chave")) or (None, None) for p in pessoas]
    sem_faixa = [p for p, (nv, _) in zip(pessoas, marcados) if nv not in FAIXAS]
    exemplares = sum(bool(p.get("exemplar")) for p in sem_faixa)
    cresc = [c for _, c in marcados if c is not None]
    return dict(uf=uf, estado=UFS[uf][1], total=total, exemplares=exemplares, sem_faixa=len(sem_faixa),
                mediana=round(median(cresc), 1) if cresc else None)


def _ordem(r):
    t = r["total"] or 1
    med = r["mediana"]
    return (-r["exemplares"] / t, -r["sem_faixa"] / t, med is None, med or 0, norm(r["estado"]))


def montar(parl, faixa=None):
    """Lista dos 27 estados na ordem do ranking, com a posicao (1 = primeiro). Sem parlamentares: None (aba sem ranking)."""
    por_uf = {uf: [] for uf in UFS}
    for p in parl or ():
        uf = str(p.get("uf") or "").upper()
        if uf in por_uf:
            por_uf[uf].append(p)
    if not any(por_uf.values()):
        return None
    out = sorted((_linha(uf, l, faixa or {}) for uf, l in por_uf.items()), key=_ordem)
    for i, r in enumerate(out, 1):
        r["pos"] = i
    return out
