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


def test_legenda_usa_os_mesmos_carimbos(html):
    """#72: na legenda da principal, Eleito, Exemplar e Pata na massa mostram o mesmo carimbo (pegada de cera, pequeno);
    fora da legenda o HTML fixo nao tem carimbo (os dos cards vem do JS, #67)."""
    destaques = re.search(r'<section id="destaques".*?</section>', html, re.S).group(0)
    for v, cor in (("eleito", "verde"), ("exemplar", "ouro"), ("selo", "caramelo")):
        assert re.search(rf'data-v="{v}"><span class="selo-cera mini {cor}" aria-hidden="true">', destaques), v
    assert destaques.count("selo-cera") == 3


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
    valor = c.locator(".valor").text_content()
    assert "de 2018 a 2026" in valor and "+100%" in valor and "R$" not in valor  # #62: so o percentual
    assert "R$" not in c.locator(".fatos").text_content()
    assert c.locator(".tags").count() == 0  # nenhuma marcacao: nada de "Nenhuma empresa" na face
    det, ver = c.locator(".det"), c.locator("button.ver")
    assert ver.text_content().startswith("Detalhes") and ver.get_attribute("aria-expanded") == "false"
    assert "Nenhuma empresa declarada" in det.text_content() and "Aumento do patrimônio" in det.text_content()
    assert "R$" not in det.text_content() and "+100%" in det.text_content() and "salário" not in det.text_content()  # #62: nenhum valor do patrimonio em reais
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
    assert "Pata na massa" in face and "3 empresas" in face
    assert c.locator(".valor b").text_content() == "+300%"  # soma dos periodos sobre o patrimonio inicial (#62)
    assert "Notícias (3)" in c.locator(".links").text_content()


def test_cards_com_mesma_escala_tipografica(abrir):
    pg = abrir()
    tam = pg.evaluate("""()=>{const px=s=>[...document.querySelectorAll('#cards .alerta:not(.presidente):not(.vice) '+s)].map(e=>getComputedStyle(e).fontSize);
        return {nome:px('.nome'),valor:px('.valor b'),fatos:px('.fatos li')}}""")
    assert all(len(set(v)) == 1 for v in tam.values()), tam


def test_presidente_em_exercicio_primeiro_e_maior(abrir):
    """#63: o presidente em exercicio vem primeiro, largura toda, com faixa; sem nivel o card fica sem cor."""
    pg = abrir()
    c = pg.locator("#cards > li").first
    assert "presidente" in c.get_attribute("class")
    assert "Presidente da República em exercício" in c.locator(".faixa-pres").text_content()
    assert c.locator(".topo .chip").count() == 0  # sem nivel calculado: nenhuma faixa de cor
    largura = pg.evaluate("()=>[...document.querySelectorAll('#cards > li')].map(e=>e.getBoundingClientRect().width)")
    assert largura[0] > largura[2] * 1.5  # [1] e o vice, tambem na largura toda
    nome = pg.evaluate("()=>[...document.querySelectorAll('#cards .nome')].slice(0,3).map(e=>parseFloat(getComputedStyle(e).fontSize))")
    assert nome[0] > nome[1] > nome[2]
    assert pg.locator("#cards .presidente").count() == 1
    vice = pg.locator("#cards > li").nth(1)
    assert "vice" in vice.get_attribute("class")  # o vice vem logo depois, com destaque menor
    assert "Vice-presidente da República em exercício" in vice.locator(".faixa-pres").text_content()
    av = pg.evaluate("()=>[...document.querySelectorAll('#cards > li .faixa-pres .avatar')].map(e=>e.getBoundingClientRect().width)")
    assert av[0] > av[1]


def test_presidente_some_com_filtro_que_nao_o_inclui(abrir):
    pg = abrir()
    pg.fill("#q", "demo 0")
    pg.dispatch_event("#q", "input")
    assert pg.locator("#cards .presidente").count() == 0


def test_aumento_percentual(abrir):
    """#62: aumento sobre o patrimonio do inicio, sem salario; o presidente fica no topo e o resto pelo maior percentual."""
    pg = abrir()
    assert pg.evaluate("VO({cresc:2e6,pat_ini:1e6})") == "+200%"
    assert pg.evaluate("VO({cresc:-4e5,pat_ini:1e6})") == "diminuiu 40%"
    assert pg.evaluate("VO({cresc:2.3e7,pat_ini:1e6})") == "+2.300%"
    assert pg.evaluate("VO({cresc:5,pat_ini:0})") == "começou do zero"
    assert pg.evaluate("VO({cresc:null,pat_ini:1})") == "Não informado"
    vn = pg.evaluate("PES.filter(p=>!TOPO(p)).map(VN)")  # maior percentual primeiro, sempre
    assert vn == sorted(vn, reverse=True)


SEM_VIRGULA = re.compile(r"(?<![\d.,])\d+\.\d{1,2}(?![\d.])")  # 43.5 (ponto no decimal); 2.400 (milhar) passa


def test_numeros_com_virgula_no_decimal(abrir, site):
    """No Brasil o decimal e com virgula (43,5%) e o milhar com ponto (2.400): nada de 43.5 em nenhuma pagina."""
    pg = abrir()
    pg.evaluate("()=>document.querySelectorAll('details').forEach(d=>d.open=true)")
    txt = pg.evaluate("()=>document.body.innerText")
    assert not SEM_VIRGULA.search(txt), SEM_VIRGULA.findall(txt)[:5]
    for f in [*site.glob("*.html"), *(site / "pessoa").glob("*.html")]:
        corpo = re.sub(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", f.read_text(encoding="utf-8"), flags=re.S)
        assert not SEM_VIRGULA.search(corpo), (f.name, SEM_VIRGULA.findall(corpo)[:5])


def test_tabela_da_pessoa_nao_quebra_palavras_no_computador(servidor, site):
    """1280px: nada de "Perío do"; "R$ 26.961.420" e "3 pegadas" numa linha so; a tabela cabe sem rolar."""
    nav, url = servidor
    pg = nav.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(url.replace("index.html", f"pessoa/{next((site / 'pessoa').glob('*.html')).name}"))
    assert pg.evaluate("getComputedStyle(document.querySelector('table.resp')).overflowWrap") == "normal"  # quebra so entre palavras
    linhas = pg.evaluate("""()=>[...document.querySelectorAll('table.resp td.n, table.resp .chip')]
        .filter(e=>e.innerText.trim()&&!e.querySelector('br,small')).map(e=>{const r=document.createRange();r.selectNodeContents(e);
        return [e.innerText.trim(),new Set([...r.getClientRects()].map(x=>Math.round(x.bottom/12))).size]})""")
    assert linhas and all(n == 1 for _, n in linhas), [t for t, n in linhas if n != 1]
    assert pg.evaluate("(t=>t.scrollWidth<=t.clientWidth)(document.querySelector('.tab'))")
    pg.close()


def test_card_patrimonio_que_diminuiu(abrir):
    c = card(abrir(), [{**UM_PERIODO[0], "cresc": -400_000, "pat_ini": 1_000_000, "pat_fim": 600_000}])
    valor = c.locator(".valor").text_content()
    assert "diminuiu 40%" in valor and "de aumento" not in valor


def test_dados_antigos_nao_quebram_a_tela(abrir):
    """Tela publicada antes da carga: faixa antiga ("sem_salario") fica sem chip e o card mostra o percentual."""
    c = card(abrir(), [{**UM_PERIODO[0], "nivel": "sem_salario"}])
    assert c.locator(".topo .chip").count() == 0 and "undefined" not in c.inner_text()
    assert "+100%" in c.locator(".valor").text_content()


def test_faixas_da_conta_antiga_ficam_escondidas(abrir):
    """#62: antes da carga nova (sem metodo.formula = "vezes"), nenhuma faixa de cor aparece; o resto da tela segue."""
    pg = abrir()
    assert pg.evaluate("FAIXA_NOVA")  # o site de teste ja vem da conta nova
    assert pg.evaluate("""()=>{const d={metodo:{},alertas:[{nivel:'forte'}]};const nova=(d.metodo||{}).formula==="vezes";
        for(const a of d.alertas)if(!nova||!NIVEIS.includes(a.nivel))a.nivel=null;return d.alertas[0].nivel}""") is None


def test_legenda_explica_niveis_em_linguagem_simples(abrir):
    pg = abrir()
    assert pg.is_visible("#legenda")
    niveis = pg.locator("#leg-niveis li")
    assert niveis.count() == 3 and "300%" in niveis.first.inner_text()
    assert "salário" not in pg.locator("#leg-niveis").inner_text()  # #62: o salario nao entra na cor
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
    for aba in ("projetos", "exemplares"):  # abas desenhadas so quando abrem (#73)
        if pg.locator(f"#aba-{aba}").count():
            pg.click(f"#aba-{aba}")
    pg.click("#aba-destaques")
    assert pg.locator("#projetos-lista .selo-cera.caramelo").count() == com_selo
    if pg.evaluate("(D.exemplares||[]).length"):
        assert pg.locator("#exemplares-lista .selo-cera.ouro").count() == pg.locator("#exemplares-lista li").count()
    # na principal, so o carimbo verde de Eleito (#67)
    assert pg.locator("#cards .selo-cera").count() == pg.locator("#cards .selo-cera.verde").count()


def test_eleito_carimbo_verde_e_borda_verde(abrir):
    """#67: mandato em curso ganha o carimbo verde no canto e borda verde; candidato sem mandato, nada."""
    pg = abrir()
    c = card(pg, [{**UM_PERIODO[0], "eleito_atual": True, "eleito_ano": 2022}])
    assert "eleito" in c.get_attribute("class") and c.locator(".carimbos.canto .selo-cera.verde").count() == 1
    assert c.locator(".selo-cera .cera .ano").inner_text() == "2022"  # ano dentro do selo
    assert c.locator(".selo-cera .rot").count() == 0  # sem texto do significado ao lado (fica na legenda)
    assert "mandato está em curso" in c.locator(".selo-cera").get_attribute("title")
    borda, cor = pg.evaluate("""()=>{const e=document.querySelector('#teste .alerta'),s=getComputedStyle(e);
        return[s.borderTopColor,getComputedStyle(document.documentElement).getPropertyValue('--eleito')]}""")
    assert borda == pg.evaluate("c=>{const d=document.createElement('i');d.style.color=c;document.body.append(d);"
                                "const r=getComputedStyle(d).color;d.remove();return r}", cor.strip())
    canto = pg.evaluate("""()=>{const e=document.querySelector('#teste .alerta').getBoundingClientRect(),
        s=document.querySelector('#teste .selo-cera').getBoundingClientRect();return[s.left-e.left,s.top-e.top]}""")
    assert all(v < 0 for v in canto)  # canto superior esquerdo, por cima da borda
    pg.evaluate("document.getElementById('teste').remove()")
    assert card(pg, UM_PERIODO).locator(".selo-cera").count() == 0  # sem o campo (antes da carga), nada muda
    pg.evaluate("document.getElementById('teste').remove()")
    sem_ano = card(pg, [{**UM_PERIODO[0], "eleito_atual": True}])  # sem o ano: nenhum carimbo (selo sem ano nao diz nada)
    assert sem_ano.locator(".selo-cera").count() == 0 and "eleito" in sem_ano.get_attribute("class").split()


def test_presidente_eleito_mantem_ouro_e_ganha_carimbo(abrir):
    pg = abrir()
    c = pg.locator("#cards > li").first
    assert "presidente" in c.get_attribute("class") and c.locator(".selo-cera.verde").count() == 1
    ouro, borda = pg.evaluate("""()=>{const e=document.querySelector('#cards > li'),d=document.createElement('i');
        d.style.color='var(--ouro)';document.body.append(d);const o=getComputedStyle(d).color;d.remove();
        return[o,getComputedStyle(e).borderTopColor]}""")
    assert borda == ouro
    sc, ca = pg.evaluate("""()=>{const e=document.querySelector('#cards > li').getBoundingClientRect(),
        s=document.querySelector('#cards > li .selo-cera').getBoundingClientRect();return[s.left-e.left,s.top-e.top]}""")
    assert sc < 0 and ca < 0  # no card em grade o carimbo fica no canto do card, nao da coluna


def test_legenda_e_filtro_do_eleito(abrir):
    pg = abrir()
    b = pg.locator('#legenda button[data-v="eleito"]')
    assert b.is_visible()
    total = pg.locator("#cards .selo-cera.verde").count()
    assert total > 0
    assert pg.locator("#cards .selo-cera.verde .ano").first.inner_text() == "2022"  # ano gravado pelo pipeline
    b.click()
    assert pg.locator("#cards > li").count() == pg.locator("#cards .alerta.com-selo").count()
    pg.evaluate("$('como-ler').open=true")  # "Como ler os numeros" e montado ao abrir (#73)
    pg.wait_for_function("$('leitura').childElementCount>0")
    assert "Carimbo verde" in pg.inner_text("#leitura") or "Carimbo verde" in pg.evaluate("$('leitura').innerHTML")


def test_um_carimbo_por_eleicao_vencida(abrir):
    """Pedido do usuario (24/10): eleito em 2018 e 2022 ganha dois carimbos, em ordem; borda verde so com mandato em curso."""
    pg = abrir()
    c = card(pg, [{**UM_PERIODO[0], "eleito_atual": True, "eleito_ano": 2022, "eleito_anos": [2018, 2022]}])
    assert c.locator(".carimbos .selo-cera .ano").all_inner_texts() == ["2018", "2022"]
    assert c.locator(".carimbos .rot").count() == 0  # so o ano dentro do selo; o significado fica na legenda
    xs = pg.evaluate("()=>[...document.querySelectorAll('#teste .carimbos .selo-cera')].map(e=>e.getBoundingClientRect().left)")
    assert xs[1] > xs[0] + 30  # lado a lado, sem sobrepor
    pg.evaluate("document.getElementById('teste').remove()")
    c = card(pg, [{**UM_PERIODO[0], "eleito_atual": False, "eleito_anos": [2018]}])  # venceu, mas o mandato acabou
    assert "eleito" not in c.get_attribute("class").split() and c.locator(".carimbos .selo-cera").count() == 1


def test_demo_reeleito_tem_dois_carimbos(abrir):
    pg = abrir()
    assert pg.locator("#cards .alerta:has(.carimbos .selo-cera:nth-child(2))").count() > 0


def test_legenda_do_eleito_escondida_sem_o_campo(html):
    assert re.search(r'<li data-eleito hidden>', html)


def test_funcionamento_explica_o_eleito(site):
    f = (site / "funcionamento.html").read_text(encoding="utf-8")
    assert "Eleito (carimbo verde)" in f and "divulgacandcontas.tse.jus.br" in f


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


def test_celular_legenda_compacta_nao_tampa_os_filtros(abrir):
    # a legenda continua aberta, mas no celular so as marcacoes numa linha; o significado abre sob demanda
    pg = abrir(largura=360)
    assert pg.evaluate("document.documentElement.scrollWidth") <= 360
    assert pg.is_visible("#leg-niveis li:first-child .chip") and not pg.is_visible("#leg-niveis .expl")
    assert pg.locator("#legenda").bounding_box()["height"] < 260
    assert pg.locator("#filtros-bt").bounding_box()["y"] < 900  # filtros na primeira tela
    pg.click("#leg-mais")
    assert pg.is_visible("#leg-niveis .expl") and pg.get_attribute("#leg-mais", "aria-expanded") == "true"
    pg.click("#leg-mais")
    assert not pg.is_visible("#leg-niveis .expl")


def test_computador_legenda_explicada_sem_botao(abrir):
    pg = abrir()
    assert pg.is_visible("#leg-niveis .expl") and not pg.is_visible("#leg-mais")


def test_como_cobrar_e_dossie_levam_a_lugares_diferentes(abrir):
    # "Como cobrar" abre direto a aba #cobrar; sem a aba na pagina (dados antigos), o atalho nao aparece
    pg = abrir()
    links = card(pg, [{**UM_PERIODO[0], "cobrar": 1}]).locator("a.lk")
    hrefs = {a.text_content(): a.get_attribute("href") for a in links.all()}
    assert hrefs["Raio-X"] == "pessoa/p0001.html" and hrefs["Como cobrar"] == "pessoa/p0001.html#cobrar"
    pg.evaluate("document.getElementById('teste').remove()")
    assert "Como cobrar" not in card(pg, UM_PERIODO).text_content()


def test_pagina_da_pessoa_abre_como_cobrar_pela_ancora_no_celular(servidor, site):
    nav, url = servidor
    pes = next((site / "pessoa").glob("*.html"))
    pg = nav.new_page(viewport={"width": 360, "height": 740})
    pg.goto(url.replace("index.html", f"pessoa/{pes.name}#cobrar"))
    assert pg.get_attribute("#aba-cobrar", "aria-selected") == "true" and pg.is_visible("#cobrar")
    assert not pg.is_visible("#resumo")
    caixa = pg.locator("#aba-cobrar").bounding_box()
    assert 0 <= caixa["x"] and caixa["x"] + caixa["width"] <= 360 and 0 <= caixa["y"] < 740  # aba visivel na tela
    pg.close()


def test_pipeline_marca_quem_tem_a_aba_como_cobrar(html):
    assert '"cobrar": 1' in html or '"cobrar":1' in html


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


def test_link_para_contas_da_campanha_no_tse(abrir):
    """Prestação de contas: um só link oficial do TSE (candidatura, bens e contas), sem cálculo nem link duplicado."""
    pg = abrir()
    h = pg.evaluate("TSE({link_tse:'https://divulgacandcontas.tse.jus.br/divulga/#/candidato/X',ano_ini:2018,ano_fim:2022})")
    assert "Candidatura, bens e contas da campanha" in h and h.count("divulgacandcontas.tse.jus.br") == 1
    assert pg.evaluate("TSE({link_tse:'javascript:x'})") == ""


def test_regua_explica_troca_de_cargo(abrir):
    pg = abrir()
    t = pg.evaluate("GRUPO({n_pares:1604,cargo_pares:'DEPUTADO FEDERAL',cargo:'SENADOR',ano_ini:2022})")
    assert t == "Entre 1.604 que disputaram Deputado Federal em 2022, como esta pessoa (depois ela disputou Senador)"
    assert pg.evaluate("GRUPO({n_pares:81,cargo_pares:'SENADOR',cargo:'SENADOR',ano_ini:2018})") == "Entre 81 candidatos a Senador em 2018"


def test_abas_desenhadas_so_ao_abrir(abrir):
    # #73: na carga so Destaques e montado; as outras abas sao desenhadas quando abrem
    pg = abrir()
    assert pg.locator("#kpis > *").count() == 0 and pg.locator("#cota-lista > li").count() == 0
    assert pg.evaluate("$('leitura').childElementCount") == 0
    pg.click("#aba-numeros")
    assert pg.locator("#kpis .kpi").count() == 4
    if pg.locator("#aba-cota").count():
        pg.click("#aba-cota")
        assert pg.locator("#cota-lista > li").count() == pg.evaluate("D.cota.length")


def test_numeros_seguem_filtro_feito_fora_da_aba(abrir):
    pg = abrir()
    pg.click("#aba-numeros")
    antes = pg.inner_text("#kpis .kpi b >> nth=0")
    pg.click("#aba-destaques")
    pg.locator("#cards .resumo button[data-dim=uf]").first.click()
    pg.click("#aba-numeros")
    assert pg.inner_text("#kpis .kpi b >> nth=0") != antes


def test_reserva_some_depois_da_carga(abrir):
    # #73: os textos que reservam espaco durante a carga nunca ficam visiveis
    pg = abrir()
    assert pg.locator(".reserva").count() == 0 or not pg.locator(".reserva").first.is_visible()
    assert "abas-prontas" in pg.evaluate("document.documentElement.className")


def test_faixa_no_card_so_cor_e_pegadas(abrir):
    """#72: o chip de faixa mostra so a cor e 2 pegadas (atencao); o rotulo fica so para leitor de tela."""
    pg = abrir()
    chip = card(pg, UM_PERIODO).locator(".chip.nv-atencao")
    assert "2 pegadas" in chip.get_attribute("aria-label")
    estilo = chip.evaluate("""c=>{const s=getComputedStyle(c),p=getComputedStyle(c,'::before');
        return {fonte:s.fontSize,cor:s.color,pegadas:p.getPropertyValue('--n').trim(),largura:parseFloat(p.width)}}""")
    assert estilo["fonte"] == "0px" and estilo["cor"] == "rgb(255, 255, 255)"
    assert estilo["pegadas"] == "2" and estilo["largura"] > 0


def test_carimbo_pegada_de_cera_com_ano_em_texto(abrir):
    """#72: o carimbo Eleito e uma pegada de cera com o ano em texto branco vindo dos dados (2030 sem desenho novo)."""
    pg = abrir()
    pg.evaluate("document.querySelector('main').insertAdjacentHTML('afterbegin',`<div id='t-selo'>${CARIMBO_ELEITO(2030)}</div>`)")
    selo = pg.locator("#t-selo .selo-cera.verde")
    assert selo.locator(".ano").inner_text() == "2030"
    assert selo.locator(".ano").evaluate("e=>getComputedStyle(e).color") == "rgb(255, 255, 255)"
    mascara = selo.locator(".cera").evaluate("e=>getComputedStyle(e,'::before').maskImage||getComputedStyle(e,'::before').webkitMaskImage")
    assert "ellipse" in mascara  # pegada (almofada e dedos), nao o selo redondo recortado


@pytest.mark.parametrize("largura", [360, 1280])
def test_cada_filtro_da_pagina_inicial_filtra(abrir, largura):
    # #73: no celular e no computador, cada filtro (busca, selects, faixas e marcacoes da legenda) muda a lista
    pg = abrir(largura)
    total = pg.evaluate("PES.length")
    contagem = lambda: int(pg.inner_text("#contagem b").replace(".", ""))
    if largura < 600:
        pg.click("#filtros-bt")
        assert pg.is_visible("#cg")
    for sel in ("cg", "rg", "nv"):
        pg.select_option(f"#{sel}", index=1)
        assert contagem() < total or "filtro" in pg.inner_text("#contagem"), sel
        pg.select_option(f"#{sel}", index=0)
        assert contagem() == total, sel
    pg.fill("#q", "zzzz-ninguem")
    assert contagem() == 0 and pg.is_visible("#vz")
    pg.fill("#q", "")
    for b in pg.locator("#legenda button[data-nv]").all():  # faixas da legenda tambem filtram
        b.click()
        assert b.get_attribute("aria-pressed") == "true" and "faixa de" in pg.inner_text("#contagem")
        assert pg.locator("#cards > li").count() > 0 and contagem() <= total
        b.click()
        assert contagem() == total
    for b in pg.locator('#legenda button[data-f="flag"]:not([aria-disabled=true])').all():
        if not b.is_visible():  # marcacao desligada nesta atualizacao (li hidden)
            continue
        if b.get_attribute("data-todos"):  # ninguem entre os destaques: abre a lista completa ja filtrada
            b.click()
            assert pg.get_attribute("#aba-todos", "aria-selected") == "true"
            pg.click("#aba-destaques")
            continue
        b.click()
        assert "filtro:" in pg.inner_text("#contagem") and contagem() <= total
        pg.click("#limpar")
        assert contagem() == total


def test_aba_aberta_aparece_na_barra_do_celular(abrir):
    pg = abrir(360)
    pg.click("#aba-destaques")
    pg.evaluate("abrirAba('todos')")
    caixa, nav = pg.locator("#aba-todos").bounding_box(), pg.locator("#abas").bounding_box()
    assert caixa["x"] >= nav["x"] - 1 and caixa["x"] + caixa["width"] <= nav["x"] + nav["width"] + 1
