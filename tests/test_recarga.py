"""Intervalo de recarga por fonte (config/recarga.json, #71)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import recarga  # noqa: E402


def test_config_do_repositorio_tem_os_prazos_pedidos():
    cfg = json.loads(recarga.ARQ.read_text(encoding="utf-8"))
    assert cfg["receita_dias"] == 7 and cfg["ano_atual_dias"] == 30 and cfg["emendas_anos_fechados_dias"] == 90


def test_dias_usa_o_padrao_quando_falta_ou_e_invalido(monkeypatch):
    monkeypatch.setattr(recarga, "_config", lambda: {"a": 3, "b": -1, "c": "x", "d": True})
    assert recarga.dias("a", 9) == 3
    assert [recarga.dias(k, 9) for k in ("b", "c", "d", "nenhum")] == [9, 9, 9, 9]


def test_vencido(monkeypatch):
    monkeypatch.setattr(recarga, "_config", lambda: {"x_dias": 7})
    agora = 1_000_000_000
    assert recarga.vencido(0, "x_dias", 1, agora) and recarga.vencido(None, "x_dias", 1, agora)
    assert not recarga.vencido(agora - 6 * recarga.DIA, "x_dias", 1, agora)
    assert recarga.vencido(agora - 7 * recarga.DIA, "x_dias", 1, agora)
