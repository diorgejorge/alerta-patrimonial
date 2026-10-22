"""Google Analytics 4 com a tag do Google em todas as paginas (config/analytics.json, #40), sem rede."""
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
    assert paginas.medicao(s) == 0
    assert "googletagmanager" not in (s / "index.html").read_text(encoding="utf-8")


def test_com_id_liga_em_todas_as_paginas(tmp_path, monkeypatch):
    s = site(tmp_path, monkeypatch, {"id_medicao": "g-abc123xyz9", "retencao_meses": 2})
    (s / "medicao.js").write_text("velho", encoding="utf-8")
    assert paginas.medicao(s) == 2
    assert not (s / "medicao.js").exists()  # sem o aviso de consentimento antigo
    for pag in (s / "index.html", s / "pessoa" / "p0001.html"):
        h = pag.read_text(encoding="utf-8")
        assert h.startswith('<html><head>\n<!-- Google tag (gtag.js) -->\n'
                            '<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABC123XYZ9"></script>')
        assert "gtag('config', 'G-ABC123XYZ9');" in h
    assert paginas.medicao(s) == 0  # nao duplica
    assert (s / "index.html").read_text(encoding="utf-8").count("googletagmanager") == 1


def test_tag_nao_confunde_header(tmp_path, monkeypatch):
    s = site(tmp_path, monkeypatch, {"id_medicao": "G-ABC123XYZ9"})
    (s / "index.html").write_text('<html><head lang="pt"><title>x</title></head><body><header>y</header></body></html>',
                                  encoding="utf-8")
    paginas.medicao(s)
    h = (s / "index.html").read_text(encoding="utf-8")
    assert h.index("googletagmanager") < h.index("</head>") and "<header>y</header>" in h


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
    assert 'id="metricas"' in h and "14 meses" in h and "gaoptout" in h and "aceitar" not in h.lower()
