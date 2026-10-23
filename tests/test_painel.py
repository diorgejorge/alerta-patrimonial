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


def test_icones_flat_sem_emoji(html):
    assert not re.search("[\U0001F300-\U0001FAFF\u2600-\u27BF]", html)  # emojis trocados por SVG (#52)


def test_selo_de_cera_so_nas_abas_proprias(html):
    destaques = re.search(r'<section id="destaques".*?</section>', html, re.S).group(0)
    assert "selo-cera" not in destaques  # na principal, Exemplar e Mao na massa sao tags coloridas


def test_selo_js_publicado_junto(site, html):
    assert '<script src="selo.js" defer>' in html and (site / "selo.js").exists()


def test_paginas_internas_com_a_identidade_do_painel(site):
    paginas = [site / "privacidade.html", next((site / "pessoa").glob("*.html")), next((site / "dossie").glob("*.html"))]
    for pg in paginas:
        h = pg.read_text(encoding="utf-8")
        assert 'class="vidro"' in h and 'class="topo-site"' in h and "logo.png" in h, pg.name


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
    assert c.locator(".resumo").text_content().split() == ["Senador", "·", "PT", "·", "MS"]
    assert "de 2018 a 2026" in c.locator(".valor").text_content()
    assert "Patrimônio foi de" in c.locator(".fatos").text_content() and "4,0×" in c.locator(".fatos").text_content()
    assert c.locator(".tags").count() == 0  # nenhuma marcacao: nada de "Nenhuma empresa" na face
    det, ver = c.locator(".det"), c.locator("button.ver")
    assert ver.text_content().startswith("Detalhes") and ver.get_attribute("aria-expanded") == "false"
    assert "Nenhuma empresa declarada" in det.text_content() and "Cresceu quantas vezes isso" in det.text_content()
    assert not det.is_visible()
    ver.click()
    assert det.is_visible() and ver.get_attribute("aria-expanded") == "true"
    assert ver.text_content().startswith("Fechar")
    ver.click()
    assert not det.is_visible() and ver.text_content().startswith("Detalhes")


def test_card_dois_periodos(abrir):
    c = card(abrir(), DOIS_PERIODOS)
    assert "PSDB → PL" in c.locator(".resumo").text_content()
    assert "2 períodos" in c.locator("button.ver").get_attribute("title")
    assert c.locator(".det .periodo").count() == 2
    assert c.locator(".tag.selo").count() == 1 and c.locator(".selo-cera").count() == 0  # selo de cera so na aba propria
    face = c.locator(".tags").text_content()
    assert "Mão na massa" in face and "3 empresas" in face
    assert "R$ 3.000.000" in c.locator(".valor b").text_content()  # soma dos periodos
    assert "Notícias (3)" in c.locator(".links").text_content()


def test_cards_com_mesma_escala_tipografica(abrir):
    pg = abrir()
    tam = pg.evaluate("""()=>{const px=s=>[...document.querySelectorAll('#cards .alerta:not(.presidente) '+s)].map(e=>getComputedStyle(e).fontSize);
        return {nome:px('.nome'),valor:px('.valor b'),fatos:px('.fatos li')}}""")
    assert all(len(set(v)) == 1 for v in tam.values()), tam


def test_presidente_em_exercicio_primeiro_e_maior(abrir):
    """#63: o presidente em exercicio vem primeiro, largura toda, com faixa; sem nivel o card fica sem cor."""
    pg = abrir()
    c = pg.locator("#cards > li").first
    assert "presidente" in c.get_attribute("class")
    assert "Presidente da República em exercício" in c.locator(".faixa-pres").text_content()
    assert c.locator(".topo .chip").count() == 0  # sem nivel calculado: nenhuma faixa de cor
    largura = pg.evaluate("()=>[...document.querySelectorAll('#cards > li')].slice(0,2).map(e=>e.getBoundingClientRect().width)")
    assert largura[0] > largura[1] * 1.5
    nome = pg.evaluate("()=>[...document.querySelectorAll('#cards .nome')].slice(0,2).map(e=>parseFloat(getComputedStyle(e).fontSize))")
    assert nome[0] > nome[1]
    assert pg.locator("#cards .presidente").count() == 1


def test_presidente_some_com_filtro_que_nao_o_inclui(abrir):
    pg = abrir()
    pg.fill("#q", "demo 0")
    pg.dispatch_event("#q", "input")
    assert pg.locator("#cards .presidente").count() == 0


def test_vezes_o_salario(abrir):
    pg = abrir()
    assert "<b>4,0×</b>" in pg.evaluate("l=>VEZES(agrupaPessoas(l)[0])", [{**UM_PERIODO[0], "cap": 250000}])
    assert "6,0×" in pg.evaluate("l=>VEZES(agrupaPessoas(l)[0])", DOIS_PERIODOS)  # 3 mi / (2 x 250 mil)
    assert pg.evaluate("l=>VEZES(agrupaPessoas(l)[0])", [{**UM_PERIODO[0], "cap": None}]) == ""


def test_legenda_explica_niveis_em_linguagem_simples(abrir):
    pg = abrir()
    assert pg.is_visible("#legenda")
    niveis = pg.locator("#leg-niveis li")
    assert niveis.count() == 4 and "salário" in niveis.first.inner_text()
    assert "sem cor" in niveis.last.inner_text()  # #62: sem salario publico fica fora das faixas
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
    pg.wait_for_selector("#tb tr", state="attached")  # a tabela e montada no evento toggle, que e assincrono
    assert pg.locator("#tb tr").count() > 0  # abrir nao gera erro de pagina (conferido no fixture)


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


def test_abas_proprias_mostram_selo_de_cera(abrir):
    pg = abrir()
    com_selo = pg.evaluate("(D.projetos||[]).filter(c=>c.selo).length")
    assert pg.locator("#projetos-lista .selo-cera.caramelo").count() == com_selo
    if pg.evaluate("(D.exemplares||[]).length"):
        assert pg.locator("#exemplares-lista .selo-cera.ouro").count() == pg.locator("#exemplares-lista li").count()
    assert pg.locator("#cards .selo-cera").count() == 0


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


def test_card_mostra_presenca_e_votos_so_nos_detalhes(abrir):
    # #56, #58: no card so o resumo curto; o detalhe fica no dossie (link #votos)
    votos = [dict(id="a", tema="A", voto="Sim", data="2025-01-01", link="https://x"),
             dict(id="b", tema="B", voto="Não votou", data="2025-02-01", link="https://x")]
    pres = dict(pct=91.5, media_casa=88.0, plenario=[183, 200])
    c = card(abrir(), [{**UM_PERIODO[0], "presenca": pres, "votos": votos}])
    det = c.locator(".det")
    assert "Presença" not in c.locator(".fatos").text_content()
    assert "Presença 91,5% (média da casa 88%)" in det.locator(".presenca").text_content()
    assert "Votou em 1 de 2 temas" in det.locator(".votos").text_content()
    assert det.locator(".votos a").get_attribute("href") == "dossie/p0001.html#votos"


def test_dossie_e_pagina_da_pessoa_com_votos_e_presenca(site):
    # no --demo, deputados federais e senadores recebem votos e presenca ficticios (votacoes.demo)
    doss = [p.read_text(encoding="utf-8") for p in (site / "dossie").glob("*.html")]
    com = [h for h in doss if '<ul class="nt votos">' in h]
    assert com and all('id="presenca"' in h and 'class="barra"' in h for h in com)
    pes = next((site / "pessoa").glob("*.html")).read_text(encoding="utf-8")
    assert 'id="aba-votos"' in pes and "<h3>Como votou</h3>" in pes


def test_cobrar_sobre_um_voto_leva_o_texto_para_como_cobrar(servidor, site):
    # #56: na pagina da pessoa o botao do voto preenche o texto da aba Como cobrar (com os canais do gabinete)
    nav, url = servidor
    pes = next(p for p in sorted((site / "pessoa").glob("*.html")) if "data-cobrar-voto" in p.read_text(encoding="utf-8"))
    pg = nav.new_page(viewport={"width": 1280, "height": 900})
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto(url.replace("index.html", f"pessoa/{pes.name}#votos"))
    pg.locator("#votos details").first.locator("summary").click()
    pg.locator("#votos [data-cobrar-voto]").first.click()
    assert pg.get_attribute("#aba-cobrar", "aria-selected") == "true" and pg.is_visible("#cobrar-texto")
    assert "Vi no site" in pg.input_value("#cobrar-texto") and "por que votou assim" in pg.input_value("#cobrar-texto") \
        or "o motivo" in pg.input_value("#cobrar-texto")
    assert not erros, erros
    pg.close()


def test_regua_dos_colegas_na_face_sem_valor_e_com_valor_nos_detalhes(abrir):
    """#64: na face, so a posicao (sem numero); nos detalhes, a regua com o valor para conferir a faixa."""
    c = card(abrir(), [{**UM_PERIODO[0], "n_pares": 81, "cargo_pares": "SENADOR"}])
    face = c.locator(".fatos")
    assert face.locator(".regua.alto").count() == 1
    assert "Entre 81 candidatos a Senador em 2018" in face.text_content() and "%" not in face.text_content()
    assert "parte 5 de 5" in face.locator(".regua").get_attribute("aria-label")
    assert "acima de 96% dos colegas" in c.locator(".det").text_content()


def test_regua_dos_colegas_cores_e_posicao(abrir):
    pg = abrir()
    assert 'left:50%' in pg.evaluate("RG({percentil:45})") and "alto" not in pg.evaluate("RG({percentil:45})")
    assert 'left:90%' in pg.evaluate("RG({percentil:100})")
    assert pg.evaluate("RG({percentil:null})") == ""
    assert "todos os cargos" in pg.evaluate("GRUPO({n_pares:40,cargo_pares:null,ano_ini:2018})")
