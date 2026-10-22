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
    assert "Mão na massa" in h and "<b>30</b>" in h and "<b>6</b>" in h and CPF not in h
    assert "Não informado" in projetos.secao(None, " GOVERNADOR", r["_fontes"])
    assert "Fonte não encontrada" in projetos.secao(None, " SENADOR", {"camara": True, "senado": False})
