"""Contagem de acessos (GoatCounter): so liga com codigo valido, sem duplicar, e explica na privacidade. Sem rede."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
import metricas  # noqa: E402

PAGINA = "<!doctype html><html><head><title>x</title></head><body></body></html>"


def site(tmp_path):
    (tmp_path / "pessoa").mkdir()
    (tmp_path / "index.html").write_text(PAGINA, encoding="utf-8")
    (tmp_path / "pessoa" / "p0001.html").write_text(PAGINA, encoding="utf-8")
    (tmp_path / "privacidade.html").write_text((SRC / "privacidade.html").read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_endpoint():
    assert metricas.endpoint("caramelo") == "https://caramelo.goatcounter.com/count"
    assert metricas.endpoint(" caramelo-vasculha ") == "https://caramelo-vasculha.goatcounter.com/count"
    assert metricas.endpoint("https://stats.exemplo.org/count") == "https://stats.exemplo.org/count"
    for ruim in ("", None, "Caramelo", "a", "x\"><script>", "http://stats.exemplo.org/count",
                 "https://stats.exemplo.org/count?x=1", "javascript:alert(1)"):
        assert metricas.endpoint(ruim) is None, ruim


def test_liga_em_todas_as_paginas_sem_duplicar(tmp_path):
    s = site(tmp_path)
    assert metricas.aplicar(s, "caramelo") == 3
    assert metricas.aplicar(s, "caramelo") == 0  # segunda publicacao sobre a mesma pasta
    for f in ("index.html", "pessoa/p0001.html", "privacidade.html"):
        html = (s / f).read_text(encoding="utf-8")
        assert html.count('data-goatcounter="https://caramelo.goatcounter.com/count"') == 1
        assert html.index("gc.zgo.at/count.js") < html.index("</head>")
    priv = (s / "privacidade.html").read_text(encoding="utf-8")
    assert "Contagem de acessos" in priv and metricas.SECAO not in priv


def test_desligada_nao_muda_paginas(tmp_path):
    s = site(tmp_path)
    for valor in ("", "invalido!"):
        assert metricas.aplicar(s, valor) == 0
    assert (s / "index.html").read_text(encoding="utf-8") == PAGINA
    priv = (s / "privacidade.html").read_text(encoding="utf-8")
    assert "goatcounter" not in priv.lower() and metricas.SECAO not in priv
