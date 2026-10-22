"""Parlamentares exemplares (estrela): os tres criterios, sem rede."""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import exemplares  # noqa: E402

CPF_OK, CPF_SANCAO, CPF_GASTAO = "11111111111", "22222222222", "33333333333"


def par(chave, cargo, cresc, cap, ano_fim=2026):
    return dict(chave=chave, nome=chave.upper(), nome_urna=None, cargo=cargo, cargo_ini=cargo, uf="MG", partido="PX",
                ano_ini=ano_fim - 4, ano_fim=ano_fim, cresc=cresc, cap=cap,
                razao=(cresc / cap) if cap else None)


DF = pd.DataFrame([par(f"cpf:{CPF_OK}", "DEPUTADO FEDERAL", 100_000, 500_000),
                   par(f"cpf:{CPF_SANCAO}", "DEPUTADO FEDERAL", 100_000, 500_000),
                   par(f"cpf:{CPF_GASTAO}", "DEPUTADO FEDERAL", -50_000, 500_000),
                   par("cpf:44444444444", "DEPUTADO FEDERAL", 2_000_000, 500_000),   # 4x o possivel
                   par("cpf:55555555555", "GOVERNADOR", 10_000, 500_000),             # cargo sem cota
                   par("cpf:66666666666", "DEPUTADO FEDERAL", 10_000, None)])          # sem salario de referencia


class ApiFalsa:
    req = falhas = 0

    def __init__(self, *a):
        pass

    def ativa(self):
        return True

    def get(self, caminho, cpf):
        return [{"sancionadoCEIS": cpf == CPF_SANCAO}]


def test_candidatos():
    assert set(exemplares.candidatos(DF)["chave"]) == {f"cpf:{CPF_OK}", f"cpf:{CPF_SANCAO}", f"cpf:{CPF_GASTAO}"}


def test_tres_criterios(monkeypatch):
    monkeypatch.setattr(exemplares.cota, "medias", lambda anos, cache: {"camara": 1_000_000.0, "senado": None})
    gastos = {f"cpf:{CPF_OK}": 400_000.0, f"cpf:{CPF_SANCAO}": 300_000.0, f"cpf:{CPF_GASTAO}": 1_500_000.0}
    monkeypatch.setattr(exemplares.cota, "coletar", lambda pessoas, anos, cache: {
        k: dict(total=v, link="https://www.camara.leg.br/deputados/1") for k, v in gastos.items() if k in pessoas})
    monkeypatch.setattr(exemplares.transparencia, "Api", ApiFalsa)
    lista, chaves = exemplares.calcular(DF, [2025, 2026], "x", "chave-teste")
    assert chaves == {f"cpf:{CPF_OK}"}  # sancao e cota acima da media ficam de fora
    assert lista[0]["cota"] == 400_000.0 and lista[0]["cota_media"] == 1_000_000.0
    assert not any(CPF_OK in str(v) for v in lista[0].values())  # CPF nunca sai do modulo


def test_sem_chave_da_api():
    assert exemplares.calcular(DF, [2026], "x", None) == ([], set())
