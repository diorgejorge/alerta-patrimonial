"""#57 Acompanhar: feed RSS por pessoa, por estado e geral, com um item quando um dado muda entre execucoes.
Unitarios (foto, mudancas, atualizar, rss, botao) e integracao (pipeline --demo duas vezes, sem rede)."""
import datetime as dt
import json, sys
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tests"))
import acompanhar, cifra  # noqa: E402

T1 = dt.datetime(2026, 10, 16, 12, tzinfo=dt.timezone.utc)
T2 = dt.datetime(2026, 10, 23, 12, tzinfo=dt.timezone.utc)
PAG = "https://x.github.io/r/pessoa/p0001.html"


def linha(**k):
    base = dict(pessoa="p0001", nome="FULANO DE TAL", nome_urna="Fulano", uf="sp", ano_ini=2018, ano_fim=2022,
                pat_fim=1_000_000, nivel="atencao", link_tse="https://divulgacandcontas.tse.jus.br/x")
    return {**base, **k}


def foto(cota=None, noticias=(), **k):
    return acompanhar.foto([linha(**k)], cota, list(noticias) if noticias is not None else None)


# ---------------------------------------------------------------- unitarios
def test_foto_pega_o_periodo_mais_recente_e_o_nivel_mais_alto():
    f = acompanhar.foto([linha(ano_fim=2018, pat_fim=10, nivel="forte"), linha(ano_fim=2022, pat_fim=20, nivel=None)],
                        1234.4, [dict(link="https://a/1"), dict(link="http://inseguro")])
    assert (f["pat"], f["ano"], f["nivel"], f["cota"], f["uf"]) == (20, 2022, "forte", 1234, "SP")
    assert f["noticias"] == ["https://a/1"] and f["nome"] == "Fulano"


def test_busca_de_noticias_que_falhou_vira_none():
    assert acompanhar.foto([linha()], None, "Fonte não encontrada")["noticias"] is None


def test_primeira_vez_gera_so_boas_vindas():
    itens = acompanhar.mudancas(None, foto(), PAG)
    assert [i["tipo"] for i in itens] == ["inicio"] and "R$" not in itens[0]["texto"]


def test_sem_mudanca_nao_gera_item():
    assert acompanhar.mudancas(foto(cota=5000), foto(cota=5500), PAG) == []


@pytest.mark.parametrize("antes, agora, tipo, trecho", [
    (dict(), dict(ano_fim=2026, pat_fim=1_500_000), "patrimonio", "Nova declaração de bens em 2026: patrimônio aumentou 50%"),
    (dict(), dict(nivel="forte"), "nivel", "“Faixa vermelha”"),
    (dict(cota=1000), dict(cota=9000), "cota", "subiu 800%"),
    (dict(), dict(exemplar=True), "exemplar", "Ganhou a estrela"),
    (dict(selo=True), dict(), "selo", "Perdeu o selo Mão na massa"),
])
def test_cada_mudanca_vira_um_item(antes, agora, tipo, trecho):
    a, b = dict(antes), dict(agora)
    fa = foto(cota=a.pop("cota", None), **a)
    fb = foto(cota=b.pop("cota", None), **b)
    itens = acompanhar.mudancas(fa, fb, PAG)
    assert [i["tipo"] for i in itens] == [tipo] and trecho in itens[0]["titulo"]


def test_patrimonio_aponta_para_o_tse():
    it = acompanhar.mudancas(foto(), foto(ano_fim=2026), PAG)[0]
    assert it["link"].startswith("https://divulgacandcontas.tse.jus.br")


def test_dado_ausente_agora_nao_vira_aviso():
    assert acompanhar.mudancas(foto(cota=9000), foto(cota=None), PAG) == []
    assert acompanhar.mudancas(foto(noticias=[dict(link="https://a/1")]), foto(noticias=None), PAG) == []


def test_noticias_novas_viram_itens_com_link_da_materia_e_limite():
    antes = foto(noticias=[dict(link="https://a/0")])
    novas = [dict(link=f"https://a/{i}") for i in range(10)]
    det = {"https://a/1": dict(titulo="Deputado vota", veiculo="Jornal", data=dt.date(2026, 10, 20))}
    itens = acompanhar.mudancas(antes, foto(noticias=novas), PAG, det)
    assert len(itens) == acompanhar.NOTICIAS_POR_VEZ and "https://a/0" not in [i["link"] for i in itens]
    assert itens[0]["titulo"] == "Na imprensa: Deputado vota" and "Jornal · 20/10/2026" in itens[0]["texto"]


def test_juntar_guarda_o_anterior_quando_falta_e_soma_noticias():
    antes = foto(cota=100, noticias=[dict(link="https://a/1")])
    novo = acompanhar.juntar(antes, foto(cota=None, noticias=[dict(link="https://a/2")]))
    assert novo["cota"] == 100 and novo["noticias"] == ["https://a/2", "https://a/1"]
    assert acompanhar.juntar(antes, foto(noticias=None))["noticias"] == ["https://a/1"]


def test_atualizar_acumula_e_limita_itens():
    est, novos = acompanhar.atualizar({}, {"p0001": (foto(), PAG, {})}, T1)
    assert len(novos) == 1 and novos[0]["data"] == T1.isoformat() and novos[0]["pessoa"] == "p0001"
    est, novos = acompanhar.atualizar(est, {"p0001": (foto(), PAG, {})}, T2)
    assert novos == [] and len(est["p0001"]["itens"]) == 1
    for d in range(30):
        est, _ = acompanhar.atualizar(est, {"p0001": (foto(pat_fim=d), PAG, {})}, T2 + dt.timedelta(days=d + 1))
    assert len(est["p0001"]["itens"]) == acompanhar.ITENS_POR_PESSOA
    assert len({i["id"] for i in est["p0001"]["itens"]}) == acompanhar.ITENS_POR_PESSOA


def test_rss_bem_formado_com_guid_e_data():
    est, _ = acompanhar.atualizar({}, {"p0001": (foto(), PAG, {})}, T1)
    est, _ = acompanhar.atualizar(est, {"p0001": (foto(nivel="forte"), PAG, {})}, T2)
    xml = acompanhar.rss("T", "D", PAG, "https://x/feed.xml", est["p0001"]["itens"], com_nome=True)
    c = ET.fromstring(xml).find("channel")
    itens = c.findall("item")
    assert len(itens) == 2 and itens[0].find("title").text.startswith("Fulano: Faixa")
    assert itens[0].find("pubDate").text.endswith("+0000") and itens[0].find("guid").text.startswith("cv-")


def test_site_usa_o_repositorio_do_actions(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "Dono/repo-x")
    assert acompanhar.url_feed("p0007") == "https://dono.github.io/repo-x/feed/p0007.xml"
    monkeypatch.setenv("GITHUB_REPOSITORY", "lixo")
    assert acompanhar.site() == acompanhar.SITE_PADRAO


def test_botao_abre_direto_no_app_de_rss():
    h = acompanhar.botao("p0001", "SP")
    url = acompanhar.url_feed("p0001")
    assert "<input" not in h and "Todos de SP" in h
    assert 'aria-label="Acompanhar por RSS"' in h and "</svg></summary>" in h  # so o icone, sem texto
    assert 'href="feed:' + url + '"' in h
    assert "feedly.com/i/subscription/feed%2Fhttps%3A%2F%2F" in h and "inoreader.com/?add_feed=https%3A%2F%2F" in h


def test_escrever_apaga_feed_de_quem_saiu(tmp_path):
    est, _ = acompanhar.atualizar({}, {"p0001": (foto(), PAG, {}), "p0002": (foto(pessoa="p0002"), PAG, {})}, T1)
    acompanhar.escrever(tmp_path, est, {"p0001", "p0002"})
    acompanhar.escrever(tmp_path, est, {"p0001"})
    assert sorted(f.name for f in (tmp_path / "feed").iterdir()) == ["p0001.xml", "uf-SP.xml"]
    geral = ET.parse(tmp_path / "feed.xml").getroot().find("channel")
    assert geral.findall("item") == []  # boas-vindas nao entram no geral


# ---------------------------------------------------------------- integracao
def test_pipeline_demo_gera_feeds_e_so_avisa_o_que_mudou(tmp_path, monkeypatch):
    from test_fase0 import rodar
    rodar(tmp_path, monkeypatch, ID_SEGREDO="segredo-de-teste")
    docs, arq = tmp_path / "docs", tmp_path / "data" / "acompanhar.json"
    feeds = sorted((docs / "feed").glob("p*.xml"))
    paginas = sorted((docs / "pessoa").glob("*.html"))
    assert feeds and [f.stem for f in feeds] == [p.stem for p in paginas]
    assert arq.read_bytes()[:4] == cifra.MAGIA  # foto guardada cifrada
    for f in [*feeds, *(docs / "feed").glob("uf-*.xml"), docs / "feed.xml"]:
        ET.parse(f)  # todos bem formados
    pag = paginas[0].read_text(encoding="utf-8")
    assert f'href="../feed/{paginas[0].stem}.xml"' in pag and 'class="acompanhar"' in pag and "__" not in pag
    estado = json.loads(cifra.ler(arq, "segredo-de-teste"))
    n1 = sum(len(r["itens"]) for r in estado.values())
    assert n1 == len(feeds)  # so as boas-vindas

    # segunda execucao: o mesmo patrimonio, so uma pessoa com nova declaracao
    pid = feeds[0].stem
    estado[pid]["foto"]["pat"] = 1
    cifra.gravar(arq, json.dumps(estado).encode(), "segredo-de-teste")
    rodar(tmp_path, monkeypatch, ID_SEGREDO="segredo-de-teste")
    estado = json.loads(cifra.ler(arq, "segredo-de-teste"))
    assert sum(len(r["itens"]) for r in estado.values()) == n1 + 1
    geral = ET.parse(docs / "feed.xml").getroot().find("channel").findall("item")
    assert len(geral) == 1 and "Nova declaração de bens" in geral[0].find("title").text


def test_presenca_so_avisa_queda_relevante():
    pr = lambda pct: dict(presenca=dict(pct=pct, media_casa=90))
    assert acompanhar.mudancas(foto(**pr(92)), foto(**pr(89)), PAG) == []
    it = acompanhar.mudancas(foto(**pr(92)), foto(**pr(80)), PAG)
    assert [i["tipo"] for i in it] == ["presenca"] and it[0]["titulo"] == "Presença registrada caiu de 92% para 80%"
    assert acompanhar.mudancas(foto(**pr(92)), foto(), PAG) == []  # sem dado agora: sem aviso


def test_voto_novo_vira_item_com_link_da_casa():
    v1 = dict(id="reforma", tema="Reforma tributária", voto="Sim", link="https://camara.leg.br/v/1")
    v2 = dict(id="arcabouco", tema="Arcabouço fiscal", voto="Não", link="https://camara.leg.br/v/2")
    it = acompanhar.mudancas(foto(votos=[v1]), foto(votos=[v1, v2]), PAG)
    assert len(it) == 1 and it[0]["titulo"] == "Votou “Não” em: Arcabouço fiscal" and it[0]["link"].endswith("/2")
    assert acompanhar.mudancas(foto(), foto(votos=[v1]), PAG) == []  # primeira vez com a lista: so guarda


def test_cada_item_cita_a_fonte_oficial_e_aponta_para_ela():
    pr = lambda pct: dict(link="https://camara.leg.br/presenca", pct=pct)
    a = acompanhar.foto([linha(presenca=pr(90))], 1000, [], "https://camara.leg.br/cota")
    b = acompanhar.foto([linha(ano_fim=2026, nivel="forte", exemplar=True, presenca=pr(70))], 9000,
                        [dict(link="https://jornal/1")], "https://camara.leg.br/cota")
    itens = acompanhar.mudancas(a, b, PAG, {"https://jornal/1": dict(titulo="T", veiculo="Jornal")})
    assert {i["tipo"] for i in itens} == {"patrimonio", "nivel", "cota", "exemplar", "presenca", "noticia"}
    for it in itens:
        assert "Fonte" in it["texto"], it
        assert "Caramelo" not in it["texto"]
    links = {i["tipo"]: i["link"] for i in itens}
    assert links["cota"].endswith("/cota") and links["presenca"].endswith("/presenca") and "tse" in links["patrimonio"]


def test_nunca_mostra_valor_em_reais():
    est, _ = acompanhar.atualizar({}, {"p0001": (foto(pat_ini=500_000), PAG, {})}, T1)
    assert "De 2018 a 2022, o patrimônio declarado aumentou 100%" in est["p0001"]["itens"][0]["texto"]
    itens = acompanhar.mudancas(foto(cota=10_000), foto(ano_fim=2026, pat_fim=900_000, cota=5_000), PAG)
    assert [i["titulo"] for i in itens] == ["Nova declaração de bens em 2026: patrimônio diminuiu 10%",
                                             "Gasto com a cota parlamentar caiu 50%"]
    assert not any("R$" in i["titulo"] + i["texto"] for i in itens)
