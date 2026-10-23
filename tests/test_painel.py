"""#52: painel repaginado (abas, card compacto, detalhes sob demanda).
Estrutura do HTML sem navegador; funcoes do card (unitario) e navegacao (integracao) no Chromium via Playwright.
Sem Playwright instalado, so a parte estrutural roda (o job "interface" do Actions instala)."""
import functools, http.server, json, os, re, subprocess, sys, threading
from pathlib import Path
import pytest

RAIZ = Path(__file__).resolve().parent.parent
ABAS = ("destaques", "exemplares", "projetos", "cota", "numeros", "todos")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    saida = tmp_path_factory.mktemp("painel")
    env = {**os.environ, "ID_SEGREDO": "segredo-de-teste"}
    for k in ("MONITORADOS_CSV", "TRANSPARENCIA_TOKEN", "TELEGRAM_TOKEN"):
        env.pop(k, None)
    subprocess.run([sys.executable, str(RAIZ / "src" / "pipeline.py"), "--demo", "--saida", str(saida)],
                   check=True, env=env, capture_output=True)
    return saida / "docs"


@pytest.fixture(scope="module")
def html(site):
    return (site / "index.html").read_text(encoding="utf-8")


# ---------- estrutura (sem navegador) ----------

def test_secoes_das_abas_existem(html):
    for id_ in ABAS:
        assert re.search(rf'<section id="{id_}" class="painel-aba"', html), id_
    assert 'id="abas" role="tablist"' in html


def test_destaques_antes_das_outras_secoes(html):
    pos = [html.index(f'<section id="{id_}"') for id_ in ABAS]
    assert pos[0] == min(pos)


def test_avisos_recolhidos_em_como_funciona(html):
    sobre = re.search(r'<details class="sobre">(.*?)</details>', html, re.S).group(1)
    assert "apenas um agregador" in sobre and "custo histórico" in sobre and 'id="contrib"' in sobre


def test_legenda_sempre_aberta_e_filtros_recolhidos(html):
    leg = re.search(r'<section class="legenda" id="legenda".*?</section>', html, re.S).group(0)
    assert "<details" not in leg and all(f'data-v="{v}"' in leg for v in ("exemplar", "selo", "renda"))
    assert "concentram" not in html  # cores de concentracao sairam (#52)
    filtros = re.search(r'<div class="filtros" id="filtros">(.*?)</div>', html, re.S).group(1)
    assert all(f'id="{i}"' in filtros for i in ("cg", "rg", "nv"))


# ---------- navegador ----------

@pytest.fixture(scope="module")
def servidor(site):
    pw = pytest.importorskip("playwright.sync_api")
    handler = functools.partial(type("Quieto", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}),
                                directory=str(site))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with pw.sync_playwright() as p:
        nav = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
        yield nav, f"http://127.0.0.1:{srv.server_port}/index.html"
        nav.close()
    srv.shutdown()


@pytest.fixture
def abrir(servidor):
    nav, url = servidor
    paginas = []

    def _abrir(largura=1280, sufixo=""):
        pg = nav.new_page(viewport={"width": largura, "height": 900})
        pg.erros = []
        pg.on("pageerror", lambda e: pg.erros.append(str(e)))
        pg.goto(url + sufixo)
        pg.wait_for_selector("#cards li", state="attached")
        paginas.append(pg)
        return pg
    yield _abrir
    for pg in paginas:
        assert not pg.erros, pg.erros
        pg.close()


PERIODO = dict(nome="MARIA DA SILVA", uf="MS", pessoa="x1", nivel="atencao", cap=250000, razao=2.5, percentil=96,
               pagina="pessoa/p0001.html", dossie="dossie/p0001.html", mencoes=3)
DOIS_PERIODOS = [
    {**PERIODO, "cargo": "DEPUTADO ESTADUAL", "partido": "PSDB", "ano_ini": 2018, "ano_fim": 2022,
     "pat_ini": 1e6, "pat_fim": 3e6, "cresc": 2e6, "qtd_empresas": 3, "outras_rendas": True},
    {**PERIODO, "cargo": "DEPUTADO ESTADUAL", "partido": "PL", "ano_ini": 2022, "ano_fim": 2026,
     "pat_ini": 3e6, "pat_fim": 4e6, "cresc": 1e6, "qtd_empresas": 3, "outras_rendas": True, "selo": True},
]
UM_PERIODO = [{**PERIODO, "cargo": "SENADOR", "partido": "PT", "ano_ini": 2018, "ano_fim": 2026,
               "pat_ini": 1e6, "pat_fim": 2e6, "cresc": 1e6, "qtd_empresas": 0}]


def card(pg, periodos):
    """Monta o card de uma pessoa sintetica com as funcoes do proprio painel e devolve o elemento."""
    pg.evaluate("""l=>{const li=document.createElement('ul');li.id='teste';li.className='alertas';
        li.innerHTML=CARD(agrupaPessoas(l)[0]);document.querySelector('main').prepend(li);}""", periodos)
    return pg.locator("#teste .alerta")


def test_cap_nomes_e_cargos(abrir):
    pg = abrir()
    assert pg.evaluate("CAP('DEPUTADO ESTADUAL')") == "Deputado Estadual"
    assert pg.evaluate("CAP('MARIA DA SILVA E SOUZA')") == "Maria da Silva e Souza"
    assert pg.evaluate("CAP('ZÉ TEIXEIRA')") == "Zé Teixeira"


def test_card_um_periodo_esconde_zeros_e_detalha_sob_demanda(abrir):
    c = card(abrir(), UM_PERIODO)
    assert c.locator(".nome").text_content() == "Maria da Silva"
    assert c.locator(".resumo").text_content().split() == ["Senador", "·", "PT", "·", "MS", "·", "2018–2026"]
    assert c.locator(".tags").count() == 0  # nenhuma marcacao: nada de "Nenhuma empresa" na face
    det = c.locator("details.det")
    assert det.locator("summary").text_content() == "Ver detalhes" and not det.get_attribute("open")
    assert "Nenhuma empresa declarada" in det.text_content() and "Cresceu quantas vezes isso" in det.text_content()
    assert not det.locator(".contadores").is_visible()
    det.locator("summary").click()
    assert det.locator(".contadores").is_visible()


def test_card_dois_periodos(abrir):
    c = card(abrir(), DOIS_PERIODOS)
    assert "PSDB → PL" in c.locator(".resumo").text_content()
    assert c.locator("details.det summary").text_content() == "Ver detalhes dos 2 períodos"
    assert c.locator("details.det .periodo").count() == 2
    face = c.locator(".tags").text_content()
    assert "Mão na massa" in face and "3 empresas" in face
    assert "R$ 3.000.000" in c.locator(":scope > .cresc b").text_content()  # soma dos periodos
    assert "Notícias (3)" in c.locator(".links").text_content()


def test_vezes_o_salario(abrir):
    pg = abrir()
    assert "<b>4,0×</b>" in pg.evaluate("l=>VEZES(agrupaPessoas(l)[0])", UM_PERIODO[:1] and [{**UM_PERIODO[0], "cap": 250000}])
    assert "6,0×" in pg.evaluate("l=>VEZES(agrupaPessoas(l)[0])", DOIS_PERIODOS)  # 3 mi / (2 x 250 mil)
    assert pg.evaluate("l=>VEZES(agrupaPessoas(l)[0])", [{**UM_PERIODO[0], "cap": None}]) == ""


def test_legenda_explica_niveis_em_linguagem_simples(abrir):
    pg = abrir()
    assert pg.is_visible("#legenda")
    niveis = pg.locator("#leg-niveis li")
    assert niveis.count() == 3 and "salário" in niveis.first.inner_text()
    for b in pg.locator("#legenda button[data-f=flag]:visible").all():  # sem ninguem com a marcacao: desativado e explicado
        if b.get_attribute("aria-disabled") == "true":
            assert "nesta atualização" in b.locator("xpath=..").inner_text() or b.get_attribute("data-todos")
        else:
            b.click()
            assert "filtro:" in pg.inner_text("#contagem")
            break


def test_tabela_completa_abre_sem_erro(abrir):
    pg = abrir()
    pg.click("#tabela summary")
    assert pg.locator("#tb tr").count() == pg.locator("#cards li").count() or pg.locator("#tb tr").count() > 0


def test_abre_em_destaques_sem_rolar(abrir):
    pg = abrir()
    assert pg.evaluate("scrollY") == 0
    assert pg.get_attribute("#aba-destaques", "aria-selected") == "true"
    assert pg.is_visible("#cards") and not pg.is_visible("#numeros")


def test_troca_de_aba_e_teclado(abrir):
    pg = abrir()
    pg.click("#aba-numeros")
    assert pg.is_visible("#kpis") and not pg.is_visible("#cards")
    assert pg.evaluate("location.hash") == "#numeros"
    pg.keyboard.press("ArrowLeft")
    assert pg.evaluate("document.activeElement.id") != "aba-numeros"
    assert pg.locator("[role=tab][aria-selected=true]").count() == 1


def test_ancora_abre_a_aba(abrir):
    pg = abrir(sufixo="#numeros")
    assert pg.is_visible("#kpis") and not pg.is_visible("#cards")


def test_barra_do_grafico_filtra_e_volta_aos_destaques(abrir):
    pg = abrir()
    total = pg.locator("#cards li").count()
    pg.click("#aba-numeros")
    pg.locator("#gu .trilho").first.click()
    assert pg.is_visible("#cards") and pg.get_attribute("#aba-destaques", "aria-selected") == "true"
    assert "filtro: estado" in pg.inner_text("#contagem")
    assert pg.locator("#cards li").count() < total


def test_resumo_do_card_filtra(abrir):
    pg = abrir()
    pg.locator("#cards .resumo button[data-dim=uf]").first.click()
    assert "filtro: estado" in pg.inner_text("#contagem")


def test_todas_as_pessoas_carrega_ao_abrir_a_aba(abrir):
    pg = abrir()
    pg.click("#aba-todos")
    pg.wait_for_selector("#todos-lista li")
    assert pg.is_visible("#todos-box") and not pg.is_visible("#todos-abrir")


def test_celular_filtros_recolhidos_e_sem_rolagem_lateral(abrir):
    pg = abrir(largura=360)
    assert pg.evaluate("document.documentElement.scrollWidth") <= 360
    assert not pg.is_visible("#cg")
    pg.click("#filtros-bt")
    assert pg.is_visible("#cg") and pg.get_attribute("#filtros-bt", "aria-expanded") == "true"
    pg.select_option("#nv", "atencao")
    assert pg.inner_text("#filtros-bt") == "Filtros (1)"
