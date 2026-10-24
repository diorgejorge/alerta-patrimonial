"""Comparacao do crescimento com bens de referencia (config/bens_referencia.json), sem rede."""
import json, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
import dossie  # noqa: E402

BENS = {"atualizado_em": "outubro de 2026", "bens": [
    {"singular": "carro", "plural": "carros", "preco": 80000, "referencia": "tabela", "link": "https://exemplo.com/carro"},
    {"singular": "casa", "plural": "casas", "preco": 400000, "referencia": "teto", "link": "javascript:alert(1)"}]}


def test_config_valida():
    cfg = json.loads((RAIZ / "config" / "bens_referencia.json").read_text(encoding="utf-8"))
    assert cfg["bens"]
    for b in cfg["bens"]:
        assert b["preco"] > 0 and b["singular"] and b["plural"]
        assert b["link"].startswith("https://")


def test_quantidades_e_links():
    h = dossie.compra(1_000_000, BENS)
    assert "<b>12</b> carros" in h and "<b>2</b> casas" in h
    assert 'href="https://exemplo.com/carro"' in h
    assert "javascript:" not in h  # so links https


def test_menos_de_um_e_vazio():
    h = dossie.compra(200_000, BENS)  # nao daria para uma casa: o item some ("0,5 casas" nao diz nada)
    assert "casa" not in h and "0," not in h and "<b>2</b> carros" in h
    assert dossie.compra(50_000, BENS) == ""  # nenhum bem inteiro: sem a lista
    assert "<b>1</b> carro<" in dossie.compra(90_000, BENS)
    assert dossie.compra(None, BENS) == "" and dossie.compra(-5, BENS) == "" and dossie.compra(10, None) == ""
