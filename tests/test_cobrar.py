"""#60 Como cobrar e #61 Compartilhar: contatos do gabinete (respostas mockadas da Camara e do Senado), texto de
cobranca, aba na pagina da pessoa (integracao com o --demo) e imagem do card no Chromium (interface)."""
import base64, functools, http.server, json, os, re, subprocess, sys, threading, urllib.parse
from pathlib import Path
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
import cobrar, contatos  # noqa: E402

CAMARA = {"dados": {"id": 204554, "cpf": "12345678909", "nomeCivil": "FULANA DE TAL",
                    "redeSocial": ["https://www.instagram.com/fulana", "http://inseguro.example"],
                    "ultimoStatus": {"email": "dep.fulana@camara.leg.br", "gabinete": {
                        "nome": "576", "predio": "4", "sala": "576", "andar": "5", "telefone": "3215-5576",
                        "email": "dep.fulana@camara.leg.br"}}}}
SENADO = {"DetalheParlamentar": {"Parlamentar": {
    "IdentificacaoParlamentar": {"CodigoParlamentar": "5012", "EmailParlamentar": "sen.fulano@senado.leg.br",
                                 "UrlPaginaParlamentar": "https://www25.senado.leg.br/web/senadores/senador/-/perfil/5012"},
    "DadosBasicosParlamentar": {"EnderecoParlamentar": "Senado Federal  Anexo 2  Ala Teotônio Vilela Gabinete 3"},
    "Telefones": {"Telefone": [{"NumeroTelefone": "33036100", "IndicadorFax": "Sim"},
                               {"NumeroTelefone": "33036200", "IndicadorFax": "Não"}]}}}}
LINHA = dict(nome="MARIA DA SILVA", nome_urna="MARIA", cargo="DEPUTADO FEDERAL", partido="XX", uf="BA",
             ano_ini=2018, ano_fim=2022, cresc=1_000_000.0, cap=200_000.0, nivel="forte",
             link_tse="https://divulgacandcontas.tse.jus.br/divulga/#/candidato/X")


class CacheFalso:
    def __init__(self):
        self.d, self.salvou = {}, False

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v

    def salvar(self):
        self.salvou = True


# ---------- contatos (unitario, sem rede) ----------

def test_camara_so_contato_e_sem_cpf():
    c = contatos.de_camara(CAMARA, "204554")
    assert c["email"] == "dep.fulana@camara.leg.br" and c["telefone"] == "(61) 3215-5576"
    assert c["endereco"] == "Câmara dos Deputados, Anexo 4, andar 5, sala 576, Brasília (DF)"
    assert c["redes"] == ["https://www.instagram.com/fulana"]  # so https
    assert "12345678909" not in json.dumps(c) and "cpf" not in json.dumps(c).lower()


def test_senado_pula_fax_e_limpa_endereco():
    c = contatos.de_senado(SENADO, "5012")
    assert c["email"] == "sen.fulano@senado.leg.br" and c["telefone"] == "(61) 3303-6200"
    assert c["endereco"] == "Senado Federal Anexo 2 Ala Teotônio Vilela Gabinete 3"
    assert c["perfil"].endswith("/perfil/5012")


@pytest.mark.parametrize("resp", [None, {}, {"dados": None}, "erro"])
def test_resposta_ruim_vira_none(resp):
    assert contatos.de_camara(resp, "1") is None and contatos.de_senado(resp, "1") is None


@pytest.mark.parametrize("bruto,esperado", [("3215-5576", "(61) 3215-5576"), ("61999998888", "(61) 99999-8888"),
                                            ("123", None), (None, None)])
def test_telefone(bruto, esperado):
    assert contatos._telefone(bruto) == esperado


def test_coletar_usa_cache_e_so_quem_tem_pagina():
    urls = []

    def falso(url):
        urls.append(url)
        return CAMARA if "camara" in url else SENADO
    parl = [dict(_chave="cpf:1", casa="camara", _id="204554"), dict(_chave="x", casa="senado", _id="5012"),
            dict(_chave="", casa="camara", _id="9")]
    cache = CacheFalso()
    out = contatos.coletar(parl, {"cpf:1"}, cache, pausa=0, buscar_json=falso)
    assert list(out) == ["cpf:1"] and out["cpf:1"]["casa"] == "camara" and len(urls) == 1 and cache.salvou
    contatos.coletar(parl, {"cpf:1"}, cache, pausa=0, buscar_json=falso)
    assert len(urls) == 1  # segunda vez veio do cache


def test_coletar_falha_vira_none():
    out = contatos.coletar([dict(_chave="k", casa="senado", _id="1")], {"k"}, None, pausa=0, buscar_json=lambda u: None)
    assert out == {"k": None}


def test_assembleias_do_config():
    a = contatos.assembleias()
    assert a["AC"][1].startswith("https://") and len(a) >= 26


# ---------- texto e secao (unitario) ----------

def test_texto_educado_com_fontes_e_sem_acusacao():
    t = cobrar.texto("Maria", "BA", cobrar.resumo([LINHA]),
                     cota=dict(total=1_234_567, de=2023, ate=2026, link="https://www.camara.leg.br/cota"),
                     projetos=dict(apresentados=10, aprovados=2, de=2023, ate=2026, link="https://x.leg.br/p"),
                     url="https://exemplo.github.io/r/pessoa/p0001.html")
    assert t.startswith("Prezado(a) Maria,") and "da Bahia" in t
    assert "R$ 1.000.000" in t and "R$ 200.000" in t and "5,0 vezes isso" in t and "R$ 1.234.567" in t
    assert "Fonte: https://divulgacandcontas" in t and "Fonte: https://www.camara.leg.br/cota" in t
    assert "10 projetos apresentados e 2 aprovados" in t and t.rstrip().endswith("pessoa/p0001.html")
    assert not re.search(r"\b(corrup|ladr|crime|roub|desvi|ilegal)", t, re.I)


def test_texto_sem_crescimento_nao_pede_explicacao_do_patrimonio():
    t = cobrar.texto("Maria", "", cobrar.resumo([dict(LINHA, cresc=-5.0)]))
    assert "patrimônio declarado" not in t and "continue prestando contas" in t


def test_resumo_soma_periodos_regra_8():
    r = cobrar.resumo([dict(LINHA, ano_ini=2014, ano_fim=2018, cresc=100.0, cap=50.0), LINHA])
    assert r["cresc"] == 1_000_100 and r["cap"] == 200_050 and (r["ano_ini"], r["ano_fim"]) == (2014, 2022)
    assert cobrar.resumo([LINHA, dict(LINHA, cap=None)])["cap"] is None  # sem salario em um periodo: sem conta


def test_secao_estados_do_contato():
    ok = cobrar.secao([LINHA], dict(contato=contatos.de_camara(CAMARA, "204554")))
    assert 'href="mailto:dep.fulana@camara.leg.br"' in ok and 'href="tel:+556132155576"' in ok
    assert 'data-mailto="cobrar-texto"' in ok and "Dados Abertos da Câmara" in ok
    assert "Fonte não encontrada" in cobrar.secao([LINHA], dict(contato=None))
    est = cobrar.secao([dict(LINHA, cargo="DEPUTADO ESTADUAL")], dict(assembleia=("Assembleia X", "https://al.x.leg.br/")))
    assert "https://al.x.leg.br/" in est and "Enviar por e-mail" not in est
    assert "câmara municipal" in cobrar.secao([dict(LINHA, cargo="VEREADOR")], {})


def test_secao_escapa_html():
    s = cobrar.secao([dict(LINHA, nome_urna='<script>x</script>')], {})
    assert "<script>x" not in s


def test_mailto_codifica_assunto_e_corpo():
    m = cobrar.mailto("a@b.leg.br", "Olá & tchau\nfim")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(m).query)
    assert m.startswith("mailto:a@b.leg.br?") and q["body"] == ["Olá & tchau\nfim"] and q["subject"] == [cobrar.ASSUNTO]


def test_imagem_numeros_do_card():
    d = cobrar.imagem([LINHA], "pessoa/p0001.html", "https://x.github.io/r/")
    assert d["url"] == "https://x.github.io/r/pessoa/p0001.html" and d["nivel_rotulo"] == "Muito acima do esperado"
    assert [n[0] for n in d["numeros"]] == ["+R$ 1.000.000", "R$ 200.000", "5,0×"]
    assert cobrar.imagem([dict(LINHA, cresc=-10.0, cap=None)], "p", "")["numeros"][0][0] == "−R$ 10"


def test_site_pelo_repositorio():
    assert cobrar.site("Dono/Repo") == "https://dono.github.io/Repo/" and cobrar.site("") == cobrar.SITE


# ---------- integracao: --demo ----------

@pytest.fixture(scope="module")
def site(tmp_path_factory):
    saida = tmp_path_factory.mktemp("cobrar")
    env = {**os.environ, "ID_SEGREDO": "segredo-de-teste"}
    for k in ("MONITORADOS_CSV", "TRANSPARENCIA_TOKEN", "TELEGRAM_TOKEN", "GITHUB_REPOSITORY"):
        env.pop(k, None)
    subprocess.run([sys.executable, str(RAIZ / "src" / "pipeline.py"), "--demo", "--saida", str(saida)],
                   check=True, env=env, capture_output=True)
    return saida / "docs"


def test_paginas_tem_aba_cobrar_e_botao(site):
    pags = sorted((site / "pessoa").glob("p*.html"))
    assert pags and (site / "compartilhar.js").exists()
    for pg in pags:
        h = pg.read_text(encoding="utf-8")
        assert 'id="aba-cobrar"' in h and 'id="cobrar"' in h and "__COBRAR__" not in h
        assert 'data-compartilhar="' in h and "compartilhar.js" in h and 'id="cobrar-texto"' in h
        assert not re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", h)  # nada com cara de CPF


def test_painel_carrega_o_script(site):
    h = (site / "index.html").read_text(encoding="utf-8")
    assert '<script src="compartilhar.js" defer>' in h and "data-compartilhar" in h


# ---------- interface: Chromium ----------

@pytest.fixture(scope="module")
def navegador(site):
    pw = pytest.importorskip("playwright.sync_api")
    handler = functools.partial(type("Quieto", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}),
                                directory=str(site))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with pw.sync_playwright() as p:
        nav = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
        yield nav, f"http://127.0.0.1:{srv.server_port}/"
        nav.close()
    srv.shutdown()


def _pagina(navegador, caminho, **kw):
    nav, base = navegador
    ctx = nav.new_context(viewport={"width": 1280, "height": 900}, **kw)
    pg = ctx.new_page()
    pg.erros = []
    pg.on("pageerror", lambda e: pg.erros.append(str(e)))
    pg.goto(base + caminho)
    return pg


def test_imagem_gerada_no_canvas(navegador):
    pg = _pagina(navegador, "pessoa/p0001.html")
    d = pg.get_attribute("[data-compartilhar]", "data-compartilhar")
    url = pg.evaluate("d=>window.CarameloCompartilhar.desenhar(JSON.parse(d),null).toDataURL('image/png')", d)
    png = base64.b64decode(url.split(",", 1)[1])
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and int.from_bytes(png[16:20], "big") == 1080
    assert int.from_bytes(png[20:24], "big") == 1350 and not pg.erros


def test_previa_com_baixar_whatsapp_e_link(navegador):
    pg = _pagina(navegador, "pessoa/p0001.html")
    pg.click("[data-compartilhar]")
    dlg = pg.wait_for_selector("dialog.compartilhar[open]")
    assert dlg.query_selector("a[download]").get_attribute("download").endswith(".png")
    assert dlg.query_selector("a[href^='https://wa.me/?text=']") and dlg.query_selector("img").get_attribute("alt")
    pg.keyboard.press("Escape")
    pg.wait_for_selector("dialog.compartilhar", state="detached")
    assert not pg.erros


def test_aba_cobrar_pelo_link_e_copiar(navegador):
    pg = _pagina(navegador, "pessoa/p0001.html#cobrar", permissions=["clipboard-read", "clipboard-write"])
    assert pg.is_visible("#cobrar-texto") and pg.get_attribute("#aba-cobrar", "aria-selected") == "true"
    pg.fill("#cobrar-texto", "Texto editado")
    pg.click("[data-copiar-texto]")
    pg.wait_for_function("document.querySelector('.cobrar-aviso').textContent.length>0")
    assert pg.evaluate("navigator.clipboard.readText()") == "Texto editado"
    if pg.query_selector("a[data-mailto]"):  # o e-mail leva o texto editado
        pg.evaluate("document.querySelector('a[data-mailto]').addEventListener('click',e=>e.preventDefault())")
        pg.click("a[data-mailto]")
        assert "body=Texto%20editado" in pg.get_attribute("a[data-mailto]", "href")
    assert not pg.erros


def test_card_do_painel_compartilha(navegador):
    pg = _pagina(navegador, "index.html")
    pg.wait_for_selector("#cards li [data-compartilhar]")
    assert pg.is_visible("#cards li [data-compartilhar]")
    assert pg.query_selector("#cards li a[href$='#cobrar']")
    pg.click("#cards li [data-compartilhar]")
    pg.wait_for_selector("dialog.compartilhar[open]")
    assert not pg.erros
