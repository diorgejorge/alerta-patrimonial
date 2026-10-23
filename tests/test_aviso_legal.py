"""Resguardo legal (#62): aviso legal, canal de correcao e fonte oficial nas paginas, sem rede."""
import json, re, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
import paginas  # noqa: E402

LINK_OFICIAL = re.compile(r'href="https://[^"]*(tse\.jus\.br|gov\.br|camara\.leg\.br|senado\.leg\.br)')


def site(tmp_path):
    s = tmp_path / "_site"
    (s / "pessoa").mkdir(parents=True)
    (s / "index.html").write_text("<html><body><p>x</p></body></html>", encoding="utf-8")
    (s / "pessoa" / "p0001.html").write_text("<html><body></body></html>", encoding="utf-8")
    (s / "parcial.html").write_text("<p>sem body</p>", encoding="utf-8")
    return s


def test_rodape_em_todas_as_paginas_com_caminho_relativo(tmp_path):
    s = site(tmp_path)
    assert paginas.rodape_legal(s) == 2
    raiz, pessoa = (s / "index.html").read_text(encoding="utf-8"), (s / "pessoa" / "p0001.html").read_text(encoding="utf-8")
    assert 'href="funcionamento.html"' in raiz and 'href="../funcionamento.html"' in pessoa
    assert 'href="../privacidade.html"' in pessoa
    assert "Ferramenta independente de agregação de dados públicos" in raiz and "respondem por eles" in raiz and "Nenhum destaque afirma irregularidade" in raiz
    assert raiz.index("rodape-legal") < raiz.index("</body>")
    assert "rodape-legal" not in (s / "parcial.html").read_text(encoding="utf-8")


def test_rodape_idempotente(tmp_path):
    s = site(tmp_path)
    paginas.rodape_legal(s)
    assert paginas.rodape_legal(s) == 0
    assert (s / "index.html").read_text(encoding="utf-8").count("data-rodape-legal") == 1


def test_link_contato():
    assert paginas.link_contato("") == ""
    assert 'target="_blank"' in paginas.link_contato("https://github.com/x/y/issues/new?template=correcao.yml")
    assert 'mailto:a@b.com' in paginas.link_contato(" a@b.com ")
    assert "&lt;script&gt;" in paginas.link_contato("<script>")


def test_aviso_legal_publicado_com_canal(tmp_path, monkeypatch):
    raiz = tmp_path / "raiz"
    (raiz / "config").mkdir(parents=True)
    (raiz / "config" / "privacidade.json").write_text(json.dumps(
        {"controlador": "Mantenedor", "contato": "https://github.com/x/y/issues/new?template=correcao.yml",
         "atualizado_em": "23/10/2026"}), encoding="utf-8")
    monkeypatch.setattr(paginas, "ROOT", raiz)
    docs = tmp_path / "docs"
    docs.mkdir()
    paginas.copiar_estilo(docs)
    aviso = (docs / "funcionamento.html").read_text(encoding="utf-8")
    assert "__" not in re.sub(r"<[^>]+>", "", aviso)
    assert "issues/new?template=correcao.yml" in aviso and "23/10/2026" in aviso
    for rotulo in ("De onde vêm os dados", "Como funcionam as contas", "Faixas de cor", "÷ patrimônio do começo × 100", "Emenda parada"):
        assert rotulo in aviso
    assert len(LINK_OFICIAL.findall(aviso)) >= 4
    assert "Não quer dizer" not in aviso  # so as contas e as fontes, sem se explicar
    assert "issues/new?template=correcao.yml" in (docs / "privacidade.html").read_text(encoding="utf-8")


def test_config_publica_tem_canal_de_correcao():
    cfg = json.loads((RAIZ / "config" / "privacidade.json").read_text(encoding="utf-8"))
    assert cfg["controlador"].strip() and cfg["contato"].startswith("https://")
    assert (RAIZ / ".github" / "ISSUE_TEMPLATE" / "correcao.yml").exists()


def test_textos_de_dados_citam_fonte_com_link():
    """Cada paragrafo de explicacao de dado (class="fonte") no painel e no dossie aponta para a fonte oficial."""
    for nome in ("template.html", "dossie.html"):
        html = (RAIZ / "src" / nome).read_text(encoding="utf-8")
        for p in re.findall(r'<p class="fonte">(.*?)</p>', html, re.S):
            if "Fonte" in p or "Consultado" in p:
                assert LINK_OFICIAL.search(p) or "matéria original" in p, (nome, p[:80])


def test_patrimonio_da_pessoa_cita_tse():
    assert LINK_OFICIAL.search(paginas._patrimonio([], [], "u"))


def test_dossie_mostra_patrimonio_inicial_e_final_com_link_do_tse():
    """O dossie e a unica pagina com o patrimonio em reais: comeco e fim, cada um com a declaracao do TSE do ano."""
    t = paginas._tabela_periodos([dict(ano_ini=2018, ano_fim=2022, cargo="SENADOR", pat_ini=100_000, pat_fim=300_000,
                                       link_tse_ini="https://tse/2018", link_tse="https://tse/2022")])
    assert '<a href="https://tse/2018" target="_blank" rel="noopener">R$ 100.000</a>' in t
    assert '<a href="https://tse/2022" target="_blank" rel="noopener">R$ 300.000</a>' in t and "+200%" in t
    sem_link = paginas._tabela_periodos([dict(ano_ini=2018, ano_fim=2022, pat_ini=100_000, pat_fim=300_000)])
    assert "R$ 100.000" in sem_link and "<a href" not in sem_link.split("R$ 100.000")[0][-30:]
