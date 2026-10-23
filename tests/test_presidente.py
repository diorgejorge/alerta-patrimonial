"""#63: presidente da Republica em exercicio (eleito na eleicao mais recente com posse ja ocorrida). Sem rede."""
import datetime as dt
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import pipeline  # noqa: E402


def linha(chave, ano, cargo="PRESIDENTE", eleito=True):
    return dict(chave=chave, ano=ano, cargo=cargo, eleito=eleito)


SERIE = pd.DataFrame([linha("a", 2018), linha("b", 2018, eleito=False), linha("b", 2022),
                      linha("c", 2022, eleito=False), linha("c", 2026), linha("d", 2022, cargo="SENADOR")])


def test_antes_da_posse_fica_o_eleito_anterior():
    assert pipeline.em_exercicio(SERIE, "PRESIDENTE", dt.date(2026, 10, 23)) == "b"
    assert pipeline.em_exercicio(SERIE, "PRESIDENTE", dt.date(2026, 12, 31)) == "b"


def test_depois_da_posse_troca_sozinho():
    assert pipeline.em_exercicio(SERIE, "PRESIDENTE", dt.date(2027, 1, 1)) == "c"


def test_cargo_com_grafia_diferente_e_sem_eleito():
    assert pipeline.em_exercicio(pd.DataFrame([linha("x", 2022, cargo="Presidente")]), "PRESIDENTE", dt.date(2024, 5, 1)) == "x"
    assert pipeline.em_exercicio(SERIE[SERIE.cargo == "SENADOR"], "PRESIDENTE", dt.date(2024, 5, 1)) is None
    assert pipeline.em_exercicio(SERIE, "PRESIDENTE", dt.date(2018, 6, 1)) is None


def test_vice_e_presidente_separados():
    serie = pd.DataFrame([linha("p", 2022), linha("v", 2022, cargo="VICE-PRESIDENTE")])
    assert pipeline.em_exercicio(serie, "PRESIDENTE", dt.date(2024, 5, 1)) == "p"
    assert pipeline.em_exercicio(serie, "VICE-PRESIDENTE", dt.date(2024, 5, 1)) == "v"
