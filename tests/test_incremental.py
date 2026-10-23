"""Dados incrementais (#48): anos fechados reaproveitados, ano atual sempre recalculado, sem rede."""
import datetime as dt, json, sys
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
import cache, pipeline  # noqa: E402

ATUAL = 2026


def serie():
    s = pipeline.serie_demo()
    s.loc[s["ano"] == 2022, "eleito"] = True
    s3 = s[s["ano"] == 2022].copy()
    s3["ano"], s3["patrimonio"], s3["eleito"] = ATUAL, s3["patrimonio"] * 1.7, False
    return pd.concat([s, s3], ignore_index=True)


def config():
    p = json.loads((RAIZ / "config" / "parametros.json").read_text())
    return pd.read_csv(RAIZ / "config" / "renda_publica.csv"), p


def ordenado(df):
    return df.sort_values(["chave", "ano_ini", "ano_fim"]).reset_index(drop=True)


def test_pares_com_cache_igual_ao_calculo_completo(tmp_path, monkeypatch):
    regras, p = config()
    s = serie()
    completo = ordenado(pipeline.pares(s, regras, {}, p))
    c = cache.Cache(tmp_path / "pares.cache", 400 * 86400, "segredo-de-teste")
    primeira = ordenado(pipeline.pares(s, regras, {}, p, cache=c, ano_atual=ATUAL))
    pd.testing.assert_frame_equal(primeira, completo)
    # segunda execucao: os periodos ate 2022 vem do cache; so os que chegam ao ano atual sao montados
    chamados = []
    original = pipeline._lista_pares
    monkeypatch.setattr(pipeline, "_lista_pares", lambda *a, **k: chamados.append(k.get("so_fim")) or original(*a, **k))
    c2 = cache.Cache(tmp_path / "pares.cache", 400 * 86400, "segredo-de-teste")
    segunda = ordenado(pipeline.pares(s, regras, {}, p, cache=c2, ano_atual=ATUAL))
    pd.testing.assert_frame_equal(segunda, completo)
    assert chamados == [ATUAL]
    # mudou um ano passado (outra assinatura): os periodos antigos sao montados de novo
    s2 = s.copy()
    s2.loc[s2["ano"] == 2018, "patrimonio"] *= 2
    chamados.clear()
    pipeline.pares(s2, regras, {}, p, cache=c2, ano_atual=ATUAL)
    assert chamados == [None, ATUAL]


def test_ano_fechado():
    assert cache.ano_fechado(2024, dt.date(2026, 1, 10))
    assert not cache.ano_fechado(2025, dt.date(2026, 3, 31))  # carencia: lancamentos de dezembro chegam ate marco
    assert cache.ano_fechado(2025, dt.date(2026, 4, 1))
    assert not cache.ano_fechado(2026, dt.date(2026, 10, 23))


def test_resultados_sem_segredo_nao_grava(tmp_path, monkeypatch):
    monkeypatch.delenv("ID_SEGREDO", raising=False)
    assert cache.resultados(tmp_path, "x", 60) is None
