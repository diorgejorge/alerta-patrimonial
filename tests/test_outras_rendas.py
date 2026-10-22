"""Outras rendas (empresas declaradas ao TSE): o destaque desce um grau. Sem rede."""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import pipeline  # noqa: E402

P = dict(taxa_poupanca=0.3, crescimento_minimo=100_000, min_pares_grupo=1,
         limiar_forte=dict(razao=3, percentil=95), limiar_atencao=dict(razao=2, percentil=90),
         limiar_informativo=dict(percentil=95))


def linha(chave, ano, pat, empresas, cargo):
    return dict(chave=chave, ano=ano, nome=chave.upper(), cargo=cargo, uf="MG", partido="PX",
                eleito=False, patrimonio=pat, sq_candidato="", cd_eleicao="", sg_ue="", nome_urna="",
                suplementar=False, empresas=empresas, empresas_cnpj=[])


def test_reduz_um_grau_com_empresas():
    # cada pessoa sozinha no proprio grupo (cargo): percentil 100 -> "atencao" mesmo sem salario de referencia
    serie = pd.DataFrame([linha("a", 2018, 100_000, [], "DEPUTADO FEDERAL"), linha("a", 2022, 9_000_000, [], "DEPUTADO FEDERAL"),
                          linha("b", 2018, 100_000, [], "SENADOR"), linha("b", 2022, 9_000_000, ["AGRO BOA VISTA LTDA"], "SENADOR")])
    df = pipeline.pares(serie, {}, {}, P).set_index("chave")
    assert df.loc["a", "nivel_calculado"] == "atencao" and df.loc["a", "nivel"] == "atencao"
    assert not df.loc["a", "outras_rendas"]
    assert df.loc["b", "outras_rendas"] and df.loc["b", "nivel_calculado"] == "atencao"
    assert df.loc["b", "nivel"] == "informativo"  # desceu um grau
    assert pipeline.REDUZ["informativo"] == "informativo"  # o menor grau nao some do painel
