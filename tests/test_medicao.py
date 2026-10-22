"""Google Analytics 4: tag do Google em todas as paginas, cookies so com aceite (config/analytics.json, #40), sem rede."""
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
    assert "googletagmanager" not in (s / "index.html").read_text(encoding="utf-8")
    assert paginas.texto_medicao() == ""


def test_id_invalido_desliga(tmp_path, monkeypatch):
    s = site(tmp_path, monkeypatch, {"id_medicao": 'G-1"><script>alert(1)</script>'})
    assert paginas.medicao(s) == 0 and not (s / "medicao.js").exists()
    assert "googletagmanager" not in (s / "index.html").read_text(encoding="utf-8")


def test_com_id_liga_em_todas_as_paginas(tmp_path, monkeypatch):
    s = site(tmp_path, monkeypatch, {"id_medicao": "g-abc123xyz9", "retencao_meses": 2})
    assert paginas.medicao(s) == 2
    assert (s / "medicao.js").read_text(encoding="utf-8") == (RAIZ / "src" / "medicao.js").read_text(encoding="utf-8")
    for pag, pre in ((s / "index.html", ""), (s / "pessoa" / "p0001.html", "../")):
        h = pag.read_text(encoding="utf-8")
        assert h.startswith("<html><head>\n<!-- Google tag (gtag.js) -->\n")
        assert '<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABC123XYZ9"></script>' in h
        assert "gtag('config', 'G-ABC123XYZ9');" in h
        assert f'<script src="{pre}medicao.js" defer></script>\n</head>' in h
    assert paginas.medicao(s) == 0  # nao duplica
    assert (s / "index.html").read_text(encoding="utf-8").count("googletagmanager") == 1


def test_tag_nao_confunde_header(tmp_path, monkeypatch):
    s = site(tmp_path, monkeypatch, {"id_medicao": "G-ABC123XYZ9"})
    (s / "index.html").write_text('<html><head lang="pt"><title>x</title></head><body><header>y</header></body></html>',
                                  encoding="utf-8")
    paginas.medicao(s)
    h = (s / "index.html").read_text(encoding="utf-8")
    assert h.index("googletagmanager") < h.index("</head>") and "<header>y</header>" in h


def test_cookies_so_depois_do_aceite(tmp_path, monkeypatch):
    s = site(tmp_path, monkeypatch, {"id_medicao": "G-ABC123XYZ9"})
    paginas.medicao(s)
    h = (s / "index.html").read_text(encoding="utf-8")
    negado = h.index("'analytics_storage': 'denied'")
    assert "'ad_storage': 'denied'" in h
    assert negado < h.index("gtag('config'")  # o padrao negado vale antes da primeira medicao
    assert h.index("localStorage.getItem('cv-medicao') === 'aceito'") < h.index("gtag('config'")
    js = (RAIZ / "src" / "medicao.js").read_text(encoding="utf-8")
    assert 'CHAVE = "cv-medicao"' in js and 'analytics_storage: "granted"' in js
    assert "googletagmanager" not in js  # o aviso nao carrega o Google; so libera os cookies


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
    assert 'id="metricas"' in h and "14 meses" in h and "data-medicao-preferencias" in h and "só são gravados se você aceitar" in h
