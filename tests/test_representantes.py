"""#59 Meus representantes: arquivos por estado (unitario) e o bloco do painel no navegador (integracao).
O site de demonstracao vem das fixtures de test_painel (pipeline --demo, dados mockados, sem rede)."""
import datetime as dt
import json, re, sys
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


class CacheFalso(dict):
    salvo = False
    def set(self, k, v): self[k] = v
    def salvar(self): self.salvo = True


def test_contatos_de_consulta_cada_um_uma_vez_e_usa_cache():
    chamadas = []
    def buscar(casa, ident, cache):
        chamadas.append((casa, ident))
        return dict(email=f"{ident}@x.leg.br")
    cache = CacheFalso({"contato:senado:5012": dict(email="s@senado.leg.br")})
    out = rp.contatos_de([dep(), dep(), dep(casa="senado", _id="5012"), dep(_id="")], cache, pausa=0,
                         buscar=lambda c, i, k: k.get(f"contato:{c}:{i}") or buscar(c, i, k))
    assert chamadas == [("camara", "204554")] and cache.salvo
    assert out[("senado", "5012")]["email"] == "s@senado.leg.br" and len(out) == 2


def test_contato_so_email_e_telefone_e_assembleia_no_estado():
    c = dict(email="dep@camara.leg.br", telefone="(61) 3215-5000", endereco="Anexo 4", fonte="https://x")
    p = rp.parlamentar(dep(), c)
    assert p["contato"] == dict(email="dep@camara.leg.br", telefone="(61) 3215-5000")
    assert "contato" not in rp.parlamentar(dep(), None)
    out = rp.montar([dep()], assembleias={"SP": ("Alesp", "https://www.al.sp.gov.br"), "RJ": ("Alerj", "http://x")})
    assert out["SP"]["assembleia"] == dict(nome="Alesp", site="https://www.al.sp.gov.br") and out["RJ"]["assembleia"] is None


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

# numero com ponto no decimal (padrao americano): no Brasil e virgula, 43,5%
SEM_VIRGULA = re.compile(r"(?<![\d.,])\d+\.\d{1,2}(?![\d.])")


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
    assert "60% abaixo da média" in txt and "R$" not in txt
    # selos discretos no canto: todos eleitos; exemplar e Mao na massa so em quem tem
    assert pagina.locator("#meus-corpo .rep").count() == pagina.locator("#meus-corpo .rep-selos .selo-cera.verde").count()
    assert pagina.locator("#meus-corpo .selo-cera.ouro").count() == 1 and pagina.locator("#meus-corpo .selo-cera.caramelo").count() == 1
    gov = pagina.locator('.rep-grupo[data-g="governador"] .rep')
    assert "Faixa laranja" in gov.inner_text() and gov.locator(".rep-lista-bt").count() == 1
    assert not SEM_VIRGULA.search(txt), SEM_VIRGULA.findall(txt)  # 43,5%, nunca 43.5%
    assert pagina.locator('a[href="estado/SP.html"]').count() == 1
    assert pagina.locator('a[href="feed/uf-SP.xml"]').count() == 1
    assert pagina.locator('.rep a[href^="mailto:"]').count() == 1 and "Cobre direto" in txt
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


# ---------- cidade (prefeito, vice e vereadores) ----------

def _zip(nome, linhas):
    import io, zipfile
    cab = list(linhas[0])
    txt = "\n".join([";".join(cab)] + [";".join(str(l.get(c, "")) for c in cab) for l in linhas])
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(f"{nome}_BRASIL.csv", txt.encode("latin-1"))
    return b.getvalue()


def test_leitura_tse_guarda_municipio_e_resultado_do_segundo_turno():
    import pipeline
    cand = dict(NR_CPF_CANDIDATO="", NM_CANDIDATO="FULANA", DT_NASCIMENTO="01/01/1970", SQ_CANDIDATO="1", DS_CARGO="PREFEITO",
                SG_UF="SP", SG_PARTIDO="AA", SG_UE="71072", NM_UE="SÃO PAULO", NM_URNA_CANDIDATO="FULANA", CD_ELEICAO="619",
                NM_TIPO_ELEICAO="ORDINÁRIA", NR_TURNO="1", DS_SIT_TOT_TURNO="2º TURNO")
    zc = _zip("consulta_cand", [cand, dict(cand, NR_TURNO="2", DS_SIT_TOT_TURNO="ELEITO")])
    zb = _zip("bem_candidato", [dict(SQ_CANDIDATO="1", VR_BEM_CANDIDATO="100,00", DS_BEM_CANDIDATO="CASA",
                                     DS_TIPO_BEM_CANDIDATO="IMOVEL")])
    df = pipeline._ler_ano_tse(2024, zb, zc)
    assert len(df) == 1 and bool(df.iloc[0]["eleito"]) and df.iloc[0]["nm_ue"] == "SÃO PAULO"


def test_cidades_da_ultima_eleicao_municipal_empossada():
    base = dict(uf="SP", sg_ue="71072", nm_ue="SÃO PAULO", eleito=True, nome_urna="", partido="A")
    linhas = [dict(base, ano=2024, cargo="PREFEITO", nome="PREFEITA"),
              dict(base, ano=2024, cargo="VEREADOR", nome="VEREADOR B"), dict(base, ano=2024, cargo="VEREADOR", nome="VEREADOR A"),
              dict(base, ano=2024, cargo="VEREADOR", nome="NAO", eleito=False),
              dict(base, ano=2020, cargo="PREFEITO", nome="ANTIGO"),
              dict(base, ano=2024, cargo="DEPUTADO ESTADUAL", nome="OUTRO"),
              dict(base, ano=2024, cargo="PREFEITO", nome="SEM UE", sg_ue="", nm_ue="")]
    cid, ano = rp.cidades(pd.DataFrame(linhas), hoje=dt.date(2026, 10, 23))
    assert ano == 2024 and list(cid) == ["71072"] and cid["71072"]["cidade"] == "São Paulo"
    assert [p["nome"] for p in cid["71072"]["grupos"]["prefeito"]] == ["Prefeita"]
    assert rp.cidades(pd.DataFrame(linhas).drop(columns="nm_ue")) == ({}, None)
    assert rp.mandato_municipal([2020, 2024], dt.date(2024, 12, 31)) == 2020


def test_gravar_cidades_e_lista_no_arquivo_do_estado(tmp_path):
    cid, ano = rp.demo_cidades()
    assert rp.gravar_cidades(tmp_path, cid, ano) == len(cid) == 52
    um = json.loads(next((tmp_path / rp.PASTA / "cidades").glob("*.json")).read_text(encoding="utf-8"))
    assert [g["id"] for g in um["grupos"]] == ["prefeito", "vice", "vereadores"] and "gerado_em" not in um
    lista = rp.lista_cidades(cid)
    assert "DF" not in lista and [n for _, n in lista["SP"]] == ["Cidade Demo SP 1", "Cidade Demo SP 2"]
    assert rp.montar([], cidades_uf=lista)["SP"]["cidades"] == lista["SP"]


def test_escolher_cidade_mostra_prefeitura_e_lembra(pagina):
    pagina.goto(pagina.url_base)
    pagina.select_option("#meu-uf", "SP")
    pagina.wait_for_selector("#minha-cidade")
    pagina.select_option("#minha-cidade", label="Cidade Demo SP 2")
    pagina.wait_for_selector("#meus-cidade .rep")
    txt = pagina.locator("#meus-cidade").inner_text()
    assert "Prefeita Demo SP 2" in txt and "Vereadores (9)" in txt.replace("\n", " ")
    pagina.reload()
    pagina.wait_for_selector("#meus-cidade .rep")
    assert "Prefeita Demo SP 2" in pagina.locator("#meus-cidade").inner_text()
    pagina.select_option("#meu-uf", "DF")
    pagina.wait_for_selector("#meus-corpo .rep")
    assert pagina.locator("#minha-cidade").count() == 0


def test_faixas_pelo_periodo_mais_recente():
    df = pd.DataFrame([dict(chave="a", ano_ini=2018, ano_fim=2022, nivel="forte"),
                       dict(chave="a", ano_ini=2022, ano_fim=2026, nivel="informativo"),
                       dict(chave="b", ano_ini=2020, ano_fim=2024, nivel=None)])
    assert rp.faixas(df) == {"a": dict(faixa="informativo", lista=1), "b": dict(lista=1)}
    assert rp.faixas(df, {"b": "pessoa/p0009.html"})["b"] == dict(lista=1, dossie="pessoa/p0009.html")
    out = rp.montar([dep(_chave="a")], extra={"a": dict(faixa="forte", lista=1)})
    assert out["SP"]["grupos"][2]["pessoas"][0]["faixa"] == "forte"


def test_patrimonio_abre_a_lista_completa_pelo_nome(pagina):
    pagina.goto(pagina.url_base)
    pagina.select_option("#meu-uf", "SP")
    pagina.wait_for_selector("#meus-corpo .rep-lista-bt")
    pagina.locator(".rep-lista-bt").first.click()
    pagina.wait_for_function("document.getElementById('tq').value==='Governadora Demo SP'")
    assert pagina.locator("#todos").is_visible()
