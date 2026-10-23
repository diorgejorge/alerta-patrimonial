"""#64 Regua dos colegas: posicao do crescimento entre candidatos ao mesmo cargo, sem valor exato na face. Sem rede."""
import sys
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
import graficos, pipeline  # noqa: E402

P = dict(taxa_poupanca=0.3, crescimento_minimo=100_000, min_pares_grupo=3,
         limiar_forte=dict(razao=3, percentil=95), limiar_atencao=dict(razao=2, percentil=90),
         limiar_informativo=dict(percentil=95))


def periodo(chave, cargo, cresc):
    return dict(chave=chave, ano_ini=2018, ano_fim=2022, cargo_ini=cargo, cresc=cresc, cap=100_000.0,
                outras_rendas=False)


def test_grupo_do_cargo_e_fallback_para_o_periodo():
    df = pipeline._classifica(pd.DataFrame([periodo(f"s{i}", "SENADOR", i * 1e5) for i in range(1, 5)]
                                           + [periodo("g1", "GOVERNADOR", 5e5)]), P).set_index("chave")
    assert df.loc["s4", "n_pares"] == 4 and df.loc["s4", "cargo_pares"] == "SENADOR"
    assert df.loc["s4", "percentil"] == 100
    # governador sozinho (menos que min_pares_grupo): compara com todos do periodo e nao diz cargo
    assert df.loc["g1", "n_pares"] == 5 and pd.isna(df.loc["g1", "cargo_pares"])


def test_regua_posicao_sem_valor_exato_e_ponto_dourado():
    alto = graficos.regua_colegas(dict(percentil=96.0, n_pares=81, cargo_pares="SENADOR", ano_ini=2018))
    assert 'class="regua alto"' in alto and "left:90%" in alto and "parte 5 de 5" in alto
    assert "Entre 81 candidatos a Senador em 2018" in alto and "acima de 96% dos colegas" in alto
    meio = graficos.regua_colegas(dict(percentil=50.0, n_pares=1200, cargo_pares="DEPUTADO ESTADUAL", ano_ini=2022))
    assert 'class="regua"' in meio and "left:50%" in meio and "a do meio" in meio and "1.200" in meio
    assert "<i></i>" * 5 in meio


def test_regua_grupo_pequeno_e_sem_dado():
    r = graficos.regua_colegas(dict(percentil=10.0, n_pares=40, cargo_pares=None, ano_ini=2018))
    assert "todos os cargos" in r and "left:10%" in r and "a dos que menos cresceram" in r
    assert graficos.regua_colegas({}) == "Não informado"
    assert graficos.regua_colegas(dict(percentil=float("nan"))) == "Não informado"


def test_regua_escapa_o_cargo():
    r = graficos.regua_colegas(dict(percentil=60.0, n_pares=30, cargo_pares="<b>x</b>", ano_ini=2018))
    assert "<b>x</b>" not in r


def test_formula_no_aviso_legal_e_no_como_ler():
    aviso = (RAIZ / "src" / "funcionamento.html").read_text(encoding="utf-8")
    assert "Régua dos colegas" in aviso and "5 partes iguais" in aviso and "90 de cada 100" in aviso
    assert "menos de 20" in aviso and "inflação" in aviso
    tpl = (RAIZ / "src" / "template.html").read_text(encoding="utf-8")
    assert "régua dos colegas" in tpl and "5 partes iguais" in tpl
