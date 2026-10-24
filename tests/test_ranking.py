"""#68 Ranking dos estados da aba Estados (unitario, dados mockados)."""
import json, sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import ranking


def parl(uf, n, exemplares=0, prefixo=None):
    pre = prefixo or uf
    return [dict(uf=uf, _chave=f"{pre}{i}", exemplar=i < exemplares, _cpf="52998224725") for i in range(n)]


def test_fatia_de_exemplares_vem_primeiro():
    r = ranking.montar(parl("AC", 10, 1) + parl("SP", 70, 5))  # 10% contra 7,1%
    assert [x["uf"] for x in r[:2]] == ["AC", "SP"] and r[0]["pos"] == 1 and len(r) == 27


def test_exemplar_em_faixa_de_cor_nao_conta():
    faixa = {"SP0": ("forte", 300.0)}
    r = {x["uf"]: x for x in ranking.montar(parl("SP", 4, 1), faixa)}
    assert r["SP"]["exemplares"] == 0 and r["SP"]["sem_faixa"] == 3


def test_desempates_sem_faixa_e_mediana():
    faixa = {"RJ0": ("atencao", 500.0), "MG0": (None, 80.0), "MG1": (None, 90.0), "BA0": (None, 10.0), "BA1": (None, 20.0)}
    r = ranking.montar(parl("RJ", 2) + parl("MG", 2) + parl("BA", 2), faixa)
    ordem = [x["uf"] for x in r if x["total"]]
    assert ordem == ["BA", "MG", "RJ"]  # BA e MG empatam sem faixa; BA cresceu menos; RJ tem gente em faixa
    assert r[0]["mediana"] == 15.0


def test_sem_parlamentares_nao_ha_ranking_e_nada_pessoal_sai():
    assert ranking.montar([]) is None
    r = ranking.montar(parl("SP", 3, 1))
    assert "52998224725" not in json.dumps(r) and "SP0" not in json.dumps(r)
    vazio = next(x for x in r if x["uf"] == "AC")
    assert vazio["total"] == 0 and vazio["mediana"] is None


def test_ultimo_periodo_pega_o_mais_recente():
    df = pd.DataFrame([dict(chave="a", ano_ini=2014, ano_fim=2018, nivel="forte", razao=3.0),
                       dict(chave="a", ano_ini=2018, ano_fim=2022, nivel=None, razao=0.5)])
    assert ranking.ultimo_periodo(df) == {"a": (None, 50.0)}
