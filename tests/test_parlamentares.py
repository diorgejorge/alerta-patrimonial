"""Todos os deputados federais e senadores em exercicio (#44, #45): cota, projetos, selo e estrela, sem rede."""
import json, sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import cota, exemplares, parlamentares  # noqa: E402

CPF_A, CPF_B, CPF_S, CPF_EX = "11111111111", "22222222222", "33333333333", "44444444444"


def par(chave, nome, cargo, uf, cresc, cap):
    return dict(chave=chave, nome=nome, nome_urna=None, cargo=cargo, cargo_ini=cargo, uf=uf, partido="PX",
                ano_ini=2022, ano_fim=2026, cresc=cresc, cap=cap, razao_salario=cresc / cap)


DF = pd.DataFrame([par(f"cpf:{CPF_A}", "FULANO A", "DEPUTADO FEDERAL", "SP", 100_000, 500_000),
                   par(f"cpf:{CPF_B}", "FULANO B", "DEPUTADO FEDERAL", "RJ", 100_000, 500_000),
                   par(f"cpf:{CPF_S}", "BELTRANA SILVA", "SENADOR", "MG", 50_000, 800_000)])
DEP = pd.DataFrame(dict(cpf=[CPF_A, CPF_B, CPF_EX], id=["100", "200", "900"], nome="", ano=2025, tipo="X",
                        valor=[100_000.0, 100_000.0, 1_000_000.0]))  # o ex-deputado so entra na media
SEN = pd.DataFrame(dict(cpf="", id="", nome=["BELTRANA", "OUTRO"], ano=2025, tipo="Y", valor=[200_000.0, 1_000_000.0]))
DEPS = [dict(id="100", nome="Fulano A", partido="PX", uf="SP"), dict(id="200", nome="Fulano B", partido="PY", uf="RJ"),
        dict(id="300", nome="Novato", partido="PZ", uf="BA")]
SENS = [dict(cod="5012", nome="Beltrana", nome_completo="Beltrana Silva", partido="PW", uf="MG",
             nomes={"BELTRANA", "BELTRANA SILVA"})]
CAMARA = {"100": (30, 6), "200": (5, 0), "999": (50, 20)}  # 999 nao esta em exercicio: fica fora do corte
SENADO = {"5012": (40, 3, {"BELTRANA", "BELTRANA SILVA"})}


class ApiFalsa:
    req = falhas = 0

    def __init__(self, *a):
        pass

    def ativa(self):
        return True

    def get(self, caminho, cpf):
        return [{"sancionadoCEIS": cpf == CPF_B}]


def montar(monkeypatch):
    monkeypatch.setattr(cota, "bases", lambda anos, cache: (DEP, SEN, {"camara": True, "senado": True}))
    monkeypatch.setattr(exemplares.transparencia, "Api", ApiFalsa)
    return parlamentares.montar(DF, [2023, 2024, 2025, 2026], "x", "chave-teste", deps=DEPS, sens=SENS,
                                camara=CAMARA, senado=SENADO)


def test_todos_em_exercicio(monkeypatch):
    lista, ctx = montar(monkeypatch)
    r = {p["nome"]: p for p in lista}
    assert len(lista) == 4 and ctx["membros"] == dict(camara=["100", "200", "300"], senado=["5012"])
    # selo: o corte dos 10% conta so quem esta em exercicio (o 999 com 20 aprovados nao entra)
    assert r["Fulano A"]["selo"] and r["Fulano A"]["aprovados"] == 6 and not r["Fulano B"]["selo"]
    assert r["Novato"]["apresentados"] == 0 and not r["Novato"]["selo"]
    assert r["Beltrana"]["selo"] and r["Beltrana"]["perfil"].endswith("/perfil/5012")
    # estrela: patrimonio compativel, cota abaixo da media da casa e sem sancoes
    assert r["Fulano A"]["exemplar"] and r["Beltrana"]["exemplar"]
    assert not r["Fulano B"]["exemplar"] and r["Fulano B"]["criterios"]["sancoes"] is False
    assert r["Novato"]["cota"] is None and not r["Novato"]["exemplar"]
    assert r["Beltrana"]["cota"] == 200_000.0 and r["Beltrana"]["ano_ini"] == 2022


def test_publico_sem_documentos(monkeypatch):
    lista, _ = montar(monkeypatch)
    pub = json.dumps([parlamentares.publico(p) for p in lista] + parlamentares.lista_exemplares(lista)
                     + parlamentares.ranking_cota(lista) + parlamentares.ranking_projetos(lista), ensure_ascii=False)
    assert not any(c in pub for c in (CPF_A, CPF_B, CPF_S, CPF_EX)) and "cpf:" not in pub
    assert all(not k.startswith("_") for p in lista for k in parlamentares.publico(p))


def test_rankings_e_exemplares(monkeypatch):
    lista, _ = montar(monkeypatch)
    assert [x["nome"] for x in parlamentares.ranking_projetos(lista)][:2] == ["Fulano A", "Beltrana"]
    assert parlamentares.ranking_cota(lista)[0]["nome"] == "Beltrana"
    assert {x["nome"] for x in parlamentares.lista_exemplares(lista)} == {"Fulano A", "Beltrana"}


def test_sem_listas_oficiais(monkeypatch):
    monkeypatch.setattr(parlamentares, "deputados", lambda: None)
    monkeypatch.setattr(parlamentares.projetos, "lista_senado", lambda: None)
    assert parlamentares.montar(DF, [2026], "x", None) == ([], {})
