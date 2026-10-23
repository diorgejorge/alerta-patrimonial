"""Parlamentares exemplares (estrela): os tres criterios, sem rede."""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import exemplares  # noqa: E402

CPF_OK, CPF_SANCAO = "11111111111", "22222222222"


def par(chave, cargo, cresc, cap, ano_fim=2026):
    return dict(chave=chave, nome="PESSOA " + chave[-2:], nome_urna=None, cargo=cargo, cargo_ini=cargo, uf="MG",
                partido="PX", ano_ini=ano_fim - 4, ano_fim=ano_fim, cresc=cresc, cap=cap,
                razao=(cresc / cap) if cap else None)


class ApiFalsa:
    req = falhas = 0

    def __init__(self, *a):
        pass

    def ativa(self):
        return True

    def get(self, caminho, cpf):
        ApiFalsa.req += 1
        return [{"sancionadoCEIS": cpf == CPF_SANCAO}]


def test_ultimos_so_parlamentares_e_periodo_mais_recente():
    df = pd.DataFrame([par("cpf:1", "DEPUTADO FEDERAL", 1, 10, ano_fim=2022),
                       par("cpf:1", "DEPUTADO FEDERAL", 2, 10, ano_fim=2026),
                       par("cpf:2", "GOVERNADOR", 1, 10)])
    u = exemplares.ultimos(df)
    assert list(u["chave"]) == ["cpf:1"] and int(u["ano_fim"].iloc[0]) == 2026


def test_compativel():
    assert exemplares.compativel(100_000, 500_000, 0.2) is True
    assert exemplares.compativel(-50_000, 500_000, -0.1) is True
    assert exemplares.compativel(2_000_000, 500_000, 4.0) is False
    assert exemplares.compativel(10_000, None, None) is None  # sem salario de referencia: sem estrela


def test_tres_criterios(monkeypatch):
    monkeypatch.setattr(exemplares.transparencia, "Api", ApiFalsa)
    base = dict(casa="camara", patrimonio_ok=True)
    lista = [dict(base, nome="OK", cota=400_000.0, _cpf=CPF_OK),
             dict(base, nome="SANCAO", cota=300_000.0, _cpf=CPF_SANCAO),
             dict(base, nome="GASTAO", cota=1_500_000.0, _cpf="33333333333"),
             dict(base, nome="CRESCEU", cota=100_000.0, _cpf="44444444444", patrimonio_ok=False),
             dict(base, nome="SEM COTA", cota=None, _cpf="55555555555")]
    ApiFalsa.req = 0
    assert exemplares.avaliar(lista, {"camara": 1_000_000.0, "senado": None}, "chave-teste") == 1
    r = {p["nome"]: p for p in lista}
    assert r["OK"]["exemplar"] and r["OK"]["criterios"] == dict(patrimonio=True, cota=True, sancoes=True)
    assert not r["SANCAO"]["exemplar"] and r["SANCAO"]["criterios"]["sancoes"] is False
    assert not r["GASTAO"]["exemplar"] and r["GASTAO"]["criterios"]["cota"] is False
    assert r["SEM COTA"]["criterios"]["cota"] is None and not r["SEM COTA"]["exemplar"]
    assert ApiFalsa.req == 2  # sancoes so para quem passou nos dois primeiros criterios
    assert r["OK"]["cota_media"] == 1_000_000.0


def test_sem_chave_da_api():
    lista = [dict(casa="camara", patrimonio_ok=True, cota=1.0, _cpf=CPF_OK)]
    assert exemplares.avaliar(lista, {"camara": 10.0}, None) == 0
    assert lista[0]["criterios"]["sancoes"] is None and not lista[0]["exemplar"]
