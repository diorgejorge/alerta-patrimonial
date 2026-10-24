"""Links de estilo e scripts com ?v=<hash do conteudo>, para o navegador nao usar copia velha apos publicar (#72)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import paginas  # noqa: E402


def test_versionar_poe_hash_e_troca_quando_muda(tmp_path):
    (tmp_path / "estilo.css").write_text("a{}")
    (tmp_path / "selo.js").write_text("1")
    (tmp_path / "pessoa").mkdir()
    (tmp_path / "index.html").write_text('<link rel="stylesheet" href="estilo.css"><script src="selo.js"></script>')
    (tmp_path / "pessoa" / "p1.html").write_text('<link href="../estilo.css"><a href="estilo.css.html">x</a>')
    assert paginas.versionar(tmp_path) == 2
    idx = (tmp_path / "index.html").read_text()
    assert 'href="estilo.css?v=' in idx and 'src="selo.js?v=' in idx
    p1 = (tmp_path / "pessoa" / "p1.html").read_text()
    assert 'href="../estilo.css?v=' in p1 and 'href="estilo.css.html"' in p1
    assert paginas.versionar(tmp_path) == 0  # idempotente
    (tmp_path / "estilo.css").write_text("b{}")
    assert paginas.versionar(tmp_path) == 2 and (tmp_path / "index.html").read_text() != idx


def test_versionar_sem_arquivos_nao_mexe(tmp_path):
    (tmp_path / "index.html").write_text('<link href="estilo.css">')
    assert paginas.versionar(tmp_path) == 0


def test_painel_js_tambem_versionado(tmp_path):
    # #73: o JS do painel saiu do HTML; sem versao, um index novo poderia rodar com o painel.js velho do cache
    (tmp_path / "painel.js").write_text("1")
    (tmp_path / "index.html").write_text('<script src="painel.js"></script>')
    assert paginas.versionar(tmp_path) == 1 and 'src="painel.js?v=' in (tmp_path / "index.html").read_text()
