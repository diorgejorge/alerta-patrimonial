"""Outras rendas (empresas declaradas ao TSE): o destaque desce um grau. Sem rede."""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import pipeline  # noqa: E402

P = dict(taxa_poupanca=0.3, crescimento_minimo=100_000, min_pares_grupo=1,
         limiar_forte=dict(razao=3, percentil=95), limiar_atencao=dict(razao=2, percentil=90),
         limiar_informativo=dict(percentil=95))


REGRAS = pd.read_csv(Path(__file__).resolve().parent.parent / "config" / "renda_publica.csv")


def linha(chave, ano, pat, empresas, cargo, eleito=True):
    return dict(chave=chave, ano=ano, nome=chave.upper(), cargo=cargo, uf="MG", partido="PX",
                eleito=eleito, patrimonio=pat, sq_candidato="", cd_eleicao="", sg_ue="", nome_urna="",
                suplementar=False, empresas=empresas, empresas_cnpj=[])


def test_reduz_um_grau_com_empresas():
    # cada pessoa sozinha no proprio grupo (cargo): percentil 100 e crescimento muito acima do salario -> vermelha
    serie = pd.DataFrame([linha("a", 2018, 100_000, [], "DEPUTADO FEDERAL"), linha("a", 2022, 9_000_000, [], "DEPUTADO FEDERAL"),
                          linha("b", 2018, 100_000, [], "SENADOR"), linha("b", 2022, 9_000_000, ["AGRO BOA VISTA LTDA"], "SENADOR")])
    df = pipeline.pares(serie, REGRAS, {}, P).set_index("chave")
    assert df.loc["a", "nivel_calculado"] == "forte" and df.loc["a", "nivel"] == "forte"
    assert not df.loc["a", "outras_rendas"]
    assert df.loc["b", "outras_rendas"] and df.loc["b", "nivel_calculado"] == "forte"
    assert df.loc["b", "nivel"] == "atencao"  # desceu um grau
    assert pipeline.REDUZ["informativo"] == "informativo"  # o menor grau nao some do painel


def test_sem_salario_fica_sem_cor_mas_nos_destaques():
    """#62: quem nao recebia salario publico (nao eleito) nao ganha cor, so a marca; empresas nao mudam isso."""
    serie = pd.DataFrame([linha("c", 2018, 100_000, [], "PREFEITO", False), linha("c", 2022, 9_000_000, [], "PREFEITO", False),
                          linha("d", 2018, 100_000, ["X LTDA"], "GOVERNADOR", False),
                          linha("d", 2022, 9_000_000, ["X LTDA"], "GOVERNADOR", False)])
    df = pipeline.pares(serie, REGRAS, {}, P).set_index("chave")
    assert df.loc["c", "cap"] is None or pd.isna(df.loc["c", "cap"])
    assert list(df["nivel"]) == ["sem_salario", "sem_salario"]


def test_teto_para_cargos_sem_subsidio_oficial():
    """#62: deputado estadual, vereador e executivo usam o teto da Constituicao; todo cargo eleito tem salario."""
    for cargo in ("DEPUTADO ESTADUAL", "DEPUTADO DISTRITAL", "VEREADOR", "PREFEITO", "VICE-PREFEITO", "GOVERNADOR",
                  "VICE-GOVERNADOR", "PRESIDENTE", "VICE-PRESIDENTE", "DEPUTADO FEDERAL", "SENADOR"):
        assert pipeline.renda_publica(cargo, 2018, 2022, REGRAS) > 0, cargo
    federal = REGRAS[REGRAS.cargo == "DEPUTADO FEDERAL"].set_index("vigente_desde").mensal_bruto
    estadual = REGRAS[REGRAS.cargo == "DEPUTADO ESTADUAL"].set_index("vigente_desde").mensal_bruto
    vereador = REGRAS[REGRAS.cargo == "VEREADOR"].set_index("vigente_desde").mensal_bruto
    assert (abs(estadual - federal * .75) < .01).all() and (abs(vereador - estadual * .75) < .01).all()
