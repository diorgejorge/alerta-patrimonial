"""#54: aba Noticias da pagina da pessoa (tags por palavra-chave, lista com link e grafico da % por tag).
Unitarios (temas, graficos, paginas, dossie) e integracao (pipeline --demo, sem rede, noticias mockadas)."""
import datetime as dt
import os, re, subprocess, sys
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
import dossie, graficos, paginas, temas  # noqa: E402

D = dt.date(2026, 10, 1)


def nt(titulo, link, data=D, tags=None):
    return dict(titulo=titulo, veiculo="Veículo", data=data, link=link,
                tags=tags if tags is not None else temas.classificar(titulo))


# ---------------------------------------------------------------- temas (unitario)
@pytest.mark.parametrize("titulo, tag", [
    ("Deputado apresenta projeto de lei na Câmara", "legislativo"),
    ("Pesquisa eleitoral: candidata lidera a campanha", "eleitoral"),
    ("Polícia Federal prende ex-prefeito em operação contra corrupção", "criminal"),
    ("Declaração de bens mostra patrimônio de R$ 5 milhões e imóveis", "patrimonial"),
    ("STF julga recurso e mantém condenação", "judicial"),
    ("Prefeitura abre licitação para obras no hospital", "gestao"),
    ("Partido anuncia que senador será líder da bancada", "politico"),
])
def test_classificar_tag_principal(titulo, tag):
    assert temas.classificar(titulo)[0] == tag


def test_classificar_sem_palavra_e_outros_e_vazio():
    assert temas.classificar("Fulano visita feira de livros") == ["outros"]
    assert temas.classificar(None, "") == ["outros"]


def test_classificar_varias_tags_no_maximo_tres_e_usa_resumo():
    tags = temas.classificar("Polícia faz operação na prefeitura", "STF analisa denúncia; projeto de lei; eleição")
    assert len(tags) == temas.MAX_TAGS and tags[0] == "criminal"
    assert set(tags) <= set(temas.ORDEM)


def test_classificar_palavra_inteira_sem_acento():
    assert temas.classificar("Operação da POLÍCIA")[0] == "criminal"
    assert temas.classificar("Repreensão")[0] == "outros"  # "re" so como palavra inteira


def test_contar_pela_tag_principal():
    ns = [nt("a", "https://x/1", tags=["eleitoral", "judicial"]), nt("b", "https://x/2", tags=["eleitoral"]),
          nt("c", "https://x/3", tags=[]), nt("d", "https://x/4", tags=["inventada"])]
    assert temas.contar(ns) == {"eleitoral": 2, "outros": 2}


def test_juntar_sem_repetir_link_recentes_primeiro_e_ignora_avisos():
    a = [nt("velha", "https://x/1", D), nt("sem data", "https://x/3", None)]
    b = [nt("repetida", "https://x/1", D), nt("nova", "https://x/2", D + dt.timedelta(days=5))]
    out = temas.juntar(a, "Fonte não encontrada", b)
    assert [n["titulo"] for n in out] == ["nova", "velha", "sem data"]
    assert len(temas.juntar(a, b, limite=2)) == 2


def test_por_mes_sem_repetir_link():
    ns = [nt("x", "https://x/1", dt.date(2026, 9, 3), ["gestao"]), nt("x", "https://x/1", dt.date(2026, 9, 3), ["gestao"]),
          nt("y", "https://x/2", dt.date(2026, 10, 1), ["gestao"]), nt("z", "https://x/3", None, ["judicial"])]
    assert temas.por_mes(iter(ns)) == {"gestao": {"2026-09": 1, "2026-10": 1}}


def test_demo_links_ficticios_e_classificados():
    ns = temas.demo(5, hoje=D)
    assert ns and all(n["link"].startswith("https://exemplo.invalid/") and n["tags"] for n in ns)


# ---------------------------------------------------------------- grafico (unitario)
def test_percentual_por_tema_acessivel_sem_cor_e_ordenado():
    s = graficos.percentual_por_tema({"gestao": 1, "eleitoral": 3, "judicial": 0}, uid="nt-p1")
    raiz = ET.fromstring(s)
    ns = "{http://www.w3.org/2000/svg}"
    assert raiz.get("role") == "img" and raiz.find(ns + "title").text == "Notícias por tema"
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", s)
    txt = [t.text for t in raiz.iter(ns + "text")]
    assert txt == ["Eleitoral", "75% (3)", "Gestão", "25% (1)"]
    assert "tag-eleitoral" in s and "tag-judicial" not in s


def test_percentual_por_tema_vazio_menos_de_um_e_desconhecida():
    assert graficos.percentual_por_tema({}, "x") == graficos.VAZIO_NOTICIAS
    assert graficos.tabela_percentual_por_tema({"x": 0}) == ""
    s = graficos.percentual_por_tema({"politico": 999, "<b>": 1}, "x")
    assert "&lt;1%" in s and "tag-outros" in s and "<b>" not in s


def test_tabela_percentual_por_tema():
    t = graficos.tabela_percentual_por_tema({"criminal": 1, "politico": 1})
    assert "<th scope=\"row\">Político</th><td>1</td><td>50%</td>" in t and "Segurança" in t
    assert "<tfoot><tr><th scope=\"row\">Total</th><td>2</td><td>100%</td>" in t


# ---------------------------------------------------------------- aba da pessoa (unitario)
def test_aba_noticias_lista_link_tags_e_grafico():
    ns = [nt("Projeto de lei <script>", "https://x/1", tags=["legislativo", "gestao"]),
          nt("Sem link seguro", "javascript:alert(1)")]
    h = paginas._noticias(ns, "nt-p1")
    assert "próxima fase" not in h and "botao" not in h
    assert '<a href="https://x/1" target="_blank" rel="noopener">Projeto de lei &lt;script&gt;</a>' in h
    assert '<span class="chip tag-legislativo">Legislativo</span><span class="chip tag-gestao">Gestão</span>' in h
    assert "javascript:" not in h and "01/10/2026" in h
    assert 'class="grafico g-pct"' in h and "Ver dados em tabela" in h and "100% (1)" in h


def test_aba_noticias_avisos():
    assert "Fonte não encontrada" in paginas._noticias(dossie.FALHA, "x")
    assert "Não informado" in paginas._noticias(None, "x")
    assert "Nenhuma notícia" in paginas._noticias([], "x")


# ---------------------------------------------------------------- dossie (unitario)
def test_saida_traz_tags():
    c = dict(titulo="Polícia prende vereador", resumo="operação contra fraude", veiculo="V", data=D, link="https://x")
    assert dossie._saida(c, "titulo", "cita a pessoa")["tags"][0] == "criminal"


def test_gerar_dossies_devolve_aviso_quando_busca_desligada(tmp_path):
    alertas = [dict(nome="FULANA DE TAL", uf="SP", ano_ini=2018, ano_fim=2022, cargo="DEPUTADO FEDERAL")]
    noticias = {}
    dossie.gerar_dossies(alertas, tmp_path, buscar=False, noticias=noticias)
    assert noticias == {0: "Busca de notícias desativada nesta execução."}


# ---------------------------------------------------------------- integracao (pipeline --demo)
@pytest.fixture(scope="module")
def docs(tmp_path_factory):
    saida = tmp_path_factory.mktemp("noticias")
    env = {**os.environ, "ID_SEGREDO": "segredo-de-teste"}
    for k in ("MONITORADOS_CSV", "TRANSPARENCIA_TOKEN", "TELEGRAM_TOKEN"):
        env.pop(k, None)
    subprocess.run([sys.executable, str(RAIZ / "src" / "pipeline.py"), "--demo", "--saida", str(saida)],
                   check=True, env=env, capture_output=True)
    return saida / "docs"


def test_paginas_da_pessoa_mostram_noticias_com_tags(docs):
    pags = sorted((docs / "pessoa").glob("*.html"))
    assert pags
    for p in pags:
        aba = re.search(r'<section role="tabpanel" id="noticias".*?</section>', p.read_text(encoding="utf-8"), re.S).group(0)
        assert "próxima fase" not in aba
        assert 'class="grafico g-pct"' in aba and 'href="https://exemplo.invalid/' in aba
        assert re.search(r'<span class="chip tag-[a-z]+">', aba)


def test_noticias_fora_do_json_e_grafico_do_painel_preenchido(docs):
    painel = (docs / "index.html").read_text(encoding="utf-8")
    assert "exemplo.invalid" not in painel  # so a contagem por mes entra no painel
    assert "Ainda não há notícias classificadas" not in painel and "g-temas" in painel
