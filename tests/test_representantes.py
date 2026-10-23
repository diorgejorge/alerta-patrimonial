"""#59 Meus representantes: arquivos por estado (unitario) e o bloco do painel no navegador (integracao).
O site de demonstracao vem das fixtures de test_painel (pipeline --demo, dados mockados, sem rede)."""
import datetime as dt
import json, sys
from pathlib import Path
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import representantes as rp
from test_painel import site, servidor  # noqa: F401 (fixtures)

CPF = "52998224725"


def dep(**kw):
    base = dict(nome="Ana Souza", casa="camara", cargo="DEPUTADO FEDERAL", partido="PT", uf="sp", _id="204554",
                _cpf=CPF, _chave="cpf:" + CPF, _nomes={"ANA SOUZA"}, perfil="https://www.camara.leg.br/deputados/204554",
                cota=300000.0, cota_media=250000.0, apresentados=40, aprovados=3, selo=True, exemplar=False,
                dossie="dossie/p0001.html", patrimonio_ok=True)
    return {**base, **kw}


# ---------- unitario ----------

def test_parlamentar_so_campos_publicos():
    p = rp.parlamentar(dep())
    assert p["foto"] == "https://www.camara.leg.br/internet/deputado/bandep/204554.jpg"
    assert p["marcas"] == ["selo"] and p["cota"] == 300000.0 and p["dossie"] == "dossie/p0001.html"
    assert not any(k.startswith("_") for k in p) and CPF not in json.dumps(p) and "patrimonio_ok" not in p


def test_senador_tem_foto_do_senado_e_vazios_somem():
    p = rp.parlamentar(dep(casa="senado", _id="5012", cota=None, dossie="javascript:alert(1)", selo=False))
    assert p["foto"].endswith("/senador5012.jpg") and "cota" not in p and "dossie" not in p and "marcas" not in p


def test_presenca_e_votos_resumidos():
    p = rp.parlamentar(dep(presenca=dict(pct=91.5, media_casa=88.2, plenario=[100, 110], link="https://x.leg.br/p"),
                           votos=[dict(voto="Sim"), dict(voto="Não"), dict(voto="Não votou")]))
    assert p["presenca"] == dict(pct=91.5, media_casa=88.2, link="https://x.leg.br/p") and p["votos"] == [2, 3]
    assert "presenca" not in rp.parlamentar(dep(presenca="erro")) and "votos" not in rp.parlamentar(dep(votos=[]))


def test_eleitos_da_ultima_eleicao_estadual_empossada():
    linhas = [dict(ano=2022, cargo="GOVERNADOR", eleito=True, uf="SP", nome="FULANO", nome_urna="FULANO GOV", partido="A"),
              dict(ano=2022, cargo="DEPUTADO ESTADUAL", eleito=True, uf="SP", nome="BELTRANA", nome_urna="", partido="B",
                   chave="cpf:1"),
              dict(ano=2022, cargo="DEPUTADO ESTADUAL", eleito=False, uf="SP", nome="NAO ELEITO", nome_urna="", partido="C"),
              dict(ano=2022, cargo="DEPUTADO DISTRITAL", eleito=True, uf="DF", nome="DISTRITAL", nome_urna="", partido="D"),
              dict(ano=2026, cargo="GOVERNADOR", eleito=True, uf="SP", nome="AINDA NAO", nome_urna="", partido="E"),
              dict(ano=2022, cargo="VEREADOR", eleito=True, uf="SP", nome="OUTRO", nome_urna="", partido="F")]
    tse, ano = rp.eleitos(pd.DataFrame(linhas), link=lambda r: "https://tse/x", foto=lambda r: None,
                          paginas={"cpf:1": "pessoa/p0002.html"}, hoje=dt.date(2026, 10, 23))
    assert ano == 2022
    assert tse["SP"]["governador"] == [dict(nome="Fulano Gov", partido="A", perfil="https://tse/x")]
    assert [d["nome"] for d in tse["SP"]["estaduais"]] == ["Beltrana"] and tse["SP"]["estaduais"][0]["dossie"] == "pessoa/p0002.html"
    assert [d["nome"] for d in tse["DF"]["estaduais"]] == ["Distrital"]
    assert rp.eleitos(None) == ({}, None)


def test_montar_27_estados_grupos_em_ordem_e_nomes_ordenados():
    out = rp.montar([dep(nome="Zeca"), dep(nome="Ana", _id="1"), dep(casa="senado", nome="Sen"), dep(uf="XX")],
                    {"SP": {"governador": [dict(nome="Gov")]}}, "2026-10-23", 2022)
    assert len(out) == 27 and out["SP"]["estado"] == "São Paulo" and out["SP"]["eleicao_estadual"] == 2022
    g = {x["id"]: x["pessoas"] for x in out["SP"]["grupos"]}
    assert [x["id"] for x in out["SP"]["grupos"]] == ["governador", "senadores", "federais", "estaduais"]
    assert [p["nome"] for p in g["federais"]] == ["Ana", "Zeca"] and len(g["senadores"]) == 1 and g["governador"]
    assert all(not x["pessoas"] for x in out["AC"]["grupos"])


def test_gravar_um_arquivo_por_estado_sem_cpf(tmp_path):
    parl, tse, ano = rp.demo()
    n = rp.gravar(tmp_path, parl, tse, "2026-10-23", ano)
    arqs = sorted((tmp_path / rp.PASTA).glob("*.json"))
    assert len(arqs) == 27 and n == 27 * (5 + 1 + 8)
    for a in arqs:
        t = a.read_text(encoding="utf-8")
        assert "00000000000" not in t and '"_' not in t


# ---------- navegador ----------

@pytest.fixture
def pagina(servidor):  # noqa: F811
    nav, url = servidor
    pg = nav.new_page(viewport={"width": 1280, "height": 900})
    pg.erros = []
    pg.on("pageerror", lambda e: pg.erros.append(str(e)))
    pg.url_base = url
    yield pg
    assert not pg.erros, pg.erros
    pg.close()


def test_escolher_estado_mostra_grupos_e_lembra(pagina):
    pagina.goto(pagina.url_base)
    assert pagina.locator("#meus").is_visible() and pagina.locator("#meus-corpo .rep").count() == 0
    pagina.select_option("#meu-uf", "SP")
    pagina.wait_for_selector("#meus-corpo .rep")
    txt = pagina.locator("#meus-corpo").inner_text()
    assert "1 governador, 2 senadores, 3 deputados federais e 8 deputados estaduais" in txt
    assert "Parlamentar exemplar" in txt and "Mão na massa" in txt and "abaixo da média" in txt
    assert pagina.locator('a[href="estado/SP.html"]').count() == 1
    pagina.reload()
    pagina.wait_for_selector("#meus-corpo .rep")
    assert pagina.input_value("#meu-uf") == "SP"


def test_ver_todos_e_filtrar_destaques(pagina):
    pagina.goto(pagina.url_base)
    pagina.select_option("#meu-uf", "PA")
    pagina.wait_for_selector("#meus-corpo .rep")
    grupo = pagina.locator('.rep-grupo[data-g="estaduais"]')
    assert grupo.locator(".rep:visible").count() == 6
    grupo.locator(".rep-mais").click()
    assert grupo.locator(".rep:visible").count() == 8
    pagina.click("#meus-filtrar")
    assert "estado PA" in pagina.locator("#contagem").inner_text()


def test_link_externo_escolhe_estado_e_df_tem_distritais(pagina):
    pagina.goto(pagina.url_base + "#meus=DF")
    pagina.wait_for_selector("#meus-corpo .rep")
    assert pagina.input_value("#meu-uf") == "DF" and "deputados distritais" in pagina.locator("#meus-corpo").inner_text()


def test_sem_arquivo_mostra_fonte_nao_encontrada(pagina):
    pagina.route("**/representantes/*.json", lambda r: r.fulfill(status=404, body=""))
    pagina.goto(pagina.url_base)
    pagina.select_option("#meu-uf", "BA")
    pagina.wait_for_function("document.getElementById('meus-corpo').textContent.includes('Fonte não encontrada')")
