"""Contagem de processos como re no DJEN (CNJ) com respostas sinteticas, sem rede."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import djen  # noqa: E402


def item(num, trib, *dest):
    return {"numero_processo": num, "siglaTribunal": trib,
            "destinatarios": [{"nome": n, "polo": p} for n, p in dest]}


PAG = {1: {"count": 6, "items": [
    item("0001", "TJAL", ("ARTHUR CÉSAR PEREIRA DE LIRA", "P"), ("OUTRO", "A")),
    item("0001", "TJAL", ("Arthur Cesar Pereira de Lira", "P")),                      # mesmo processo: conta 1
    item("0002", "STJ", ("2. ARTHUR CESAR PEREIRA DE LIRA (AGRAVADO)", "P")),
    item("0003", "TJAL", ("ARTHUR CESAR PEREIRA DE LIRA", "A")),                      # polo ativo: fora
    item("0004", "TJSP", ("ARTHUR CESAR PEREIRA DE LIRA", "P")),                      # outro estado: fora
    item("0005", "TRT19", ("ARTHUR CESAR PEREIRA DE LIRA JUNIOR", "P"))]}}            # outro nome: fora


def test_conta_so_polo_passivo_do_estado():
    r = djen.processos_reu("Arthur César Pereira de Lira", "AL", buscar=lambda nome, p: PAG[p])
    assert r == {"0001", "0002"}


def test_tribunais_por_estado():
    t = djen.tribunais("MG")
    assert {"TJMG", "TRF6", "TRT3", "STF"} <= t and "TJSP" not in t
    assert djen.tribunais("DF") >= {"TJDFT", "TRF1", "TRT10"}
    assert djen.tribunais("BR") == djen.SUPERIORES


def test_nome_curto_e_falha():
    assert djen.processos_reu("Tiririca", "SP", buscar=lambda n, p: PAG[1]) is None

    def erro(n, p):
        raise OSError("fora do ar")
    assert djen.processos_reu("Fulano de Tal", "SP", buscar=erro) is None


def test_contar_usa_cache(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(djen, "processos_reu", lambda nome, uf: chamadas.append(nome) or {"1", "2"})
    monkeypatch.setattr(djen, "PAUSA", 0)
    pessoas = {"k": dict(nome="Fulano de Tal", uf="MG")}
    assert djen.contar(pessoas, tmp_path)["k"] == 2
    assert djen.contar(pessoas, tmp_path)["k"] == 2
    assert chamadas == ["Fulano de Tal"]  # segunda vez veio do cache do mes
