"""Google Analytics 4 com aviso de consentimento (config/analytics.json, #40), sem rede."""
import json, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
import paginas  # noqa: E402


def site(tmp_path, monkeypatch, cfg):
    raiz = tmp_path / "raiz"
    (raiz / "config").mkdir(parents=True)
    (raiz / "config" / "analytics.json").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(paginas, "ROOT", raiz)
    s = tmp_path / "_site"
    (s / "pessoa").mkdir(parents=True)
    (s / "index.html").write_text("<html><head><title>x</title></head><body></body></html>", encoding="utf-8")
    (s / "pessoa" / "p0001.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    (s / "blocos.json").write_text("{}", encoding="utf-8")
    return s


def test_config_publica_vazia_ou_valida():
    cfg = json.loads((RAIZ / "config" / "analytics.json").read_text(encoding="utf-8"))
    assert cfg["id_medicao"] == "" or cfg["id_medicao"].startswith("G-")
    assert cfg["retencao_meses"] in (2, 14)


def test_sem_id_nada_carrega(tmp_path, monkeypatch):
    s = site(tmp_path, monkeypatch, {"id_medicao": ""})
    (s / "medicao.js").write_text("velho", encoding="utf-8")
    assert paginas.medicao(s) == 0
    assert not (s / "medicao.js").exists()
    assert "medicao.js" not in (s / "index.html").read_text(encoding="utf-8")
    assert paginas.texto_medicao() == ""


def test_id_invalido_desliga(tmp_path, monkeypatch):
    s = site(tmp_path, monkeypatch, {"id_medicao": 'G-1"><script>alert(1)</script>'})
    assert paginas.medicao(s) == 0 and not (s / "medicao.js").exists()


def test_com_id_liga_em_todas_as_paginas(tmp_path, monkeypatch):
    s = site(tmp_path, monkeypatch, {"id_medicao": "g-abc123xyz9", "retencao_meses": 2})
    assert paginas.medicao(s) == 2
    js = (s / "medicao.js").read_text(encoding="utf-8")
    assert '"G-ABC123XYZ9"' in js and "__GA_ID__" not in js
    assert '<script src="medicao.js" defer></script>' in (s / "index.html").read_text(encoding="utf-8")
    assert '<script src="../medicao.js" defer></script>' in (s / "pessoa" / "p0001.html").read_text(encoding="utf-8")
    assert paginas.medicao(s) == 0  # nao duplica


def test_ga_so_depois_do_aceite():
    js = (RAIZ / "src" / "medicao.js").read_text(encoding="utf-8")
    assert js.count("googletagmanager.com") == 1
    corpo = js.split("function carregar()")[1].split("function apagarCookies()")[0]
    assert "googletagmanager.com" in corpo  # o script do Google so e criado dentro de carregar()
    assert 'ad_storage: "denied"' in js and "allow_google_signals: false" in js


def test_privacidade_com_e_sem_ga(tmp_path, monkeypatch):
    site(tmp_path, monkeypatch, {"id_medicao": ""})
    sem = tmp_path / "sem"
    sem.mkdir()
    paginas.copiar_estilo(sem)
    h = (sem / "privacidade.html").read_text(encoding="utf-8")
    assert "Google Analytics" not in h and "__MEDICAO__" not in h
    site(tmp_path / "b", monkeypatch, {"id_medicao": "G-ABC123XYZ9", "retencao_meses": 14})
    com = tmp_path / "com"
    com.mkdir()
    paginas.copiar_estilo(com)
    h = (com / "privacidade.html").read_text(encoding="utf-8")
    assert 'id="metricas"' in h and "14 meses" in h and "data-medicao-preferencias" in h
