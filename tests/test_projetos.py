"""Projetos de lei (Camara: arquivos abertos; Senado: API) e o selo "Mao na massa", com dados sinteticos, sem rede."""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import cota, projetos  # noqa: E402

CPF = "12345678909"
PROP = ('"id";"siglaTipo";"numero";"ultimoStatus_descricaoSituacao"\n'
        '"1";"PL";"10";"Transformado em Norma Jurídica"\n'
        '"2";"PLP";"11";"Aguardando Parecer"\n'
        '"3";"PEC";"12";"Transformado em Norma Jurídica com Veto Parcial"\n'
        '"4";"REQ";"13";"Transformado em Norma Jurídica"\n'
        '"5";"PL";"14";"Transformado em nova proposição"\n')
AUT = ('"idProposicao";"idDeputadoAutor";"nomeAutor"\n'
       '"1";"204554";"Fulano"\n"2";"204554";"Fulano"\n"3";"204554";"Fulano"\n"4";"204554";"Fulano"\n'
       '"3";"300";"Outro"\n"5";"300";"Outro"\n"1";"";"Senado Federal"\n')


def test_ler_camara():
    df = projetos.ler_camara(("﻿" + PROP).encode("utf-8"), AUT.encode("utf-8"))
    assert set(df["prop"]) == {"1", "2", "3", "5"}  # REQ fica de fora; autor sem id de deputado tambem
    ful = df[df["dep"] == "204554"]
    assert len(ful) == 3 and ful["aprovada"].sum() == 2  # PL e PEC viraram norma (com veto parcial conta)
    assert df[df["dep"] == "300"]["aprovada"].sum() == 1  # "nova proposicao" nao e norma juridica


def test_corte():
    assert projetos.corte([9, 5, 3, 0, 0, 0, 0, 0, 0, 0]) == 9  # 10% de 10 = 1 parlamentar
    assert projetos.corte([4, 4, 1, 0, 0, 0, 0, 0, 0, 0]) == 4  # empate no corte: os dois entram
    assert projetos.corte([0, 0, 0]) == 1  # sem nenhum aprovado ninguem ganha o selo
    assert projetos.corte([]) == float("inf")


def test_corte_desempate():
    # (aprovados, apresentados): empate em 1 aprovado nao da o selo a todos, vale quem apresentou mais (#44)
    v = [(1, 50), (1, 10), (1, 5)] + [(0, 3)] * 7
    c = projetos.corte(v)
    assert c == (1, 50) and projetos.tem_selo(1, 50, c) and not projetos.tem_selo(1, 10, c)
    assert projetos.corte([(0, 9)] * 3) == (1, 0) and not projetos.tem_selo(0, 9, (1, 0))
    assert not projetos.tem_selo(5, 5, float("inf"))
    assert projetos.cortes({"1": (50, 1), "2": (10, 1), "3": (5, 1)}, None)["camara"] == (1, 50)
    # deputado em exercicio cujo periodo no TSE e de prefeito: a contagem da casa aparece no dossie
    r = dict(casa="camara", apresentados=3, aprovados=1, selo=False, link="https://x", de=2023, ate=2026)
    assert "<b>3</b>" in projetos.secao(r, " PREFEITO", {})


def test_coleta_e_secao(tmp_path, monkeypatch):
    dep = pd.DataFrame(dict(cpf=[CPF, CPF], id=["", "204554"], nome="", ano=2025, tipo="X", valor=1.0))
    monkeypatch.setattr(cota, "bases", lambda anos, cache: (dep, pd.DataFrame(), {}))
    camara = {"204554": (30, 6), **{str(i): (5, 0) for i in range(9)}}
    senado = {"5012": (40, 3, {"BELTRANA", "BELTRANA SILVA"}), "1": (10, 1, {"OUTRA"})}
    pessoas = {"dep": dict(nome="Fulano de Tal", nome_urna="Fulano", cargo=" DEPUTADO FEDERAL", cpf=CPF),
               "sen": dict(nome="Beltrana Silva", nome_urna="Beltrana", cargo=" SENADOR", cpf=""),
               "gov": dict(nome="Ciclano", nome_urna="", cargo=" GOVERNADOR", cpf="11122233344")}
    r = projetos.coletar(pessoas, [2023, 2024, 2025, 2026], tmp_path, camara=camara, senado=senado)
    assert r["_fontes"] == {"camara": True, "senado": True}
    assert r["dep"]["apresentados"] == 30 and r["dep"]["aprovados"] == 6 and r["dep"]["selo"]
    assert "ideCadastro%3A+204554" in r["dep"]["link"] and "2023-01-01" in r["dep"]["link"]
    assert r["sen"]["selo"] and r["sen"]["link"].endswith("/autor/5012/p/1")
    assert "gov" not in r
    h = projetos.secao(r["dep"], pessoas["dep"]["cargo"], r["_fontes"])
    assert "Pata na massa" in h and "<b>30</b>" in h and "<b>6</b>" in h and CPF not in h
    assert "Não informado" in projetos.secao(None, " GOVERNADOR", r["_fontes"])
    assert "Fonte não encontrada" in projetos.secao(None, " SENADOR", {"camara": True, "senado": False})


def test_lista_do_senado_fora_do_ar_usa_a_ultima_boa(tmp_path, monkeypatch):
    arq = tmp_path / "senado_lista.json"
    resp = {"ListaParlamentarEmExercicio": {"Parlamentares": {"Parlamentar": [
        {"IdentificacaoParlamentar": {"CodigoParlamentar": 1, "NomeParlamentar": "Fulana", "NomeCompletoParlamentar": "Fulana de Tal",
                                      "SiglaPartidoParlamentar": "PX", "UfParlamentar": "SP"}}]}}}
    monkeypatch.setattr(projetos, "_LISTA_SENADO", [])
    monkeypatch.setattr(projetos, "_json", lambda url, **k: resp)
    boa = projetos.lista_senado(arq)
    assert [s["cod"] for s in boa] == ["1"] and arq.exists()
    monkeypatch.setattr(projetos, "_LISTA_SENADO", [])
    monkeypatch.setattr(projetos, "_json", lambda url, **k: None)
    fora = projetos.lista_senado(arq)
    assert fora == boa and fora[0]["nomes"] == {"FULANA", "FULANA DE TAL"}
    monkeypatch.setattr(projetos, "_LISTA_SENADO", [])
    assert projetos.lista_senado(tmp_path / "nada.json") is None
