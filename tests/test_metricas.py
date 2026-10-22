"""Contagem de acessos (Google Analytics 4 com consentimento): so liga com ID valido, sem duplicar, so carrega o GA
depois do "Aceitar" e explica na privacidade. Sem rede."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
import metricas  # noqa: E402

PAGINA = "<!doctype html><html><head><title>x</title></head><body><p>oi</p></body></html>"
GA = "G-ABC123XYZ9"


def site(tmp_path):
    (tmp_path / "pessoa").mkdir()
    (tmp_path / "index.html").write_text(PAGINA, encoding="utf-8")
    (tmp_path / "pessoa" / "p0001.html").write_text(PAGINA, encoding="utf-8")
    (tmp_path / "privacidade.html").write_text((SRC / "privacidade.html").read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_id_medicao():
    assert metricas.id_medicao(GA) == GA
    assert metricas.id_medicao(" g-abc123xyz9 ") == GA
    for ruim in ("", None, "UA-12345-1", "G-", "G-ABC\"><script>", "GTM-ABCDEF", "javascript:alert(1)"):
        assert metricas.id_medicao(ruim) is None, ruim


def test_liga_em_todas_as_paginas_sem_duplicar(tmp_path):
    s = site(tmp_path)
    assert metricas.aplicar(s, GA) == 3
    assert metricas.aplicar(s, GA) == 0  # segunda publicacao sobre a mesma pasta
    for f in ("index.html", "pessoa/p0001.html", "privacidade.html"):
        html = (s / f).read_text(encoding="utf-8")
        assert html.count(metricas.MARCA) == 1 and f'var ID="{GA}"' in html
        assert html.index("ga-aviso") < html.index("</body>")
        # o GA so e carregado dentro de ligar(), chamada apos o aceite: nenhuma tag <script src> do Google
        assert '<script async src="https://www.googletagmanager.com' not in html
    assert 'href="../privacidade.html#acessos"' in (s / "pessoa" / "p0001.html").read_text(encoding="utf-8")
    assert 'href="privacidade.html#acessos"' in (s / "index.html").read_text(encoding="utf-8")
    priv = (s / "privacidade.html").read_text(encoding="utf-8")
    assert 'id="acessos"' in priv and "gaMudarEscolha" in priv and metricas.SECAO not in priv


def test_sem_anuncios(tmp_path):
    html = metricas.trecho(GA)
    for c in ("ad_storage", "ad_user_data", "ad_personalization"):
        assert f'{c}:"denied"' in html
    assert "allow_google_signals:false" in html and "allow_ad_personalization_signals:false" in html


def test_desligada_nao_muda_paginas(tmp_path):
    s = site(tmp_path)
    for valor in ("", "invalido!"):
        assert metricas.aplicar(s, valor) == 0
    assert (s / "index.html").read_text(encoding="utf-8") == PAGINA
    priv = (s / "privacidade.html").read_text(encoding="utf-8")
    assert "analytics" not in priv.lower() and metricas.SECAO not in priv
