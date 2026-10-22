"""Testes de src/graficos.py (sem rede): SVG bem formado, acessibilidade, sem cores fixas, ids, escape."""
import re, sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import graficos as g  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"
COR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(", re.I)
MAU = "<script>alert('x')</script>"
NIV = {"forte": 3, "atencao": 0, "informativo": 12}
PAT = [(2014, 250_000.0), (2018, 1_200_000.0), (2022, 3_400_000_000.0)]
NOT = {"criminal": {"2024-02": 4}, "politico": {"2024-01": 2, "2024-03": 1}, "gestao": {"2024-01": 0}}


def graficos(uid, titulo=None):
    kw = {"titulo": titulo} if titulo else {}
    return [g.barras_niveis(NIV, uid, **kw), g.patrimonio(PAT, uid, **kw), g.noticias_por_tema(NOT, uid, **kw)]


def svg(s):
    raiz = ET.fromstring(s)
    assert raiz.tag == NS + "svg"
    return raiz


def acessivel(s):
    raiz = svg(s)
    assert raiz.get("role") == "img"
    assert raiz.get("width") == "100%" and raiz.get("viewBox")
    t, d = raiz.find(NS + "title"), raiz.find(NS + "desc")
    assert t is not None and d is not None and t.text and d.text
    assert raiz.get("aria-labelledby") == t.get("id") and raiz.get("aria-describedby") == d.get("id")
    return raiz


def ids(raiz):
    return [el.get("id") for el in raiz.iter() if el.get("id")]


def textos(raiz):
    return [el.text for el in raiz.iter(NS + "text")]


def sem_cor_fixa(s):
    assert not COR.search(s)
    for el in svg(s).iter():
        for a in ("fill", "stroke", "color"):
            v = el.get(a)
            assert v is None or v in ("currentColor", "none") or v.startswith("url(#"), (el.tag, a, v)


# ---------------------------------------------------------------- comuns
def test_bem_formado_acessivel_sem_cor():
    for s in graficos("a"):
        acessivel(s)
        sem_cor_fixa(s)
    mini = g.mini_patrimonio(PAT, "a")
    sem_cor_fixa(mini)
    assert svg(mini).get("role") == "img"


def test_ids_unicos_entre_graficos():
    a = [i for s in graficos("pessoa-1") for i in ids(svg(s))]
    b = [i for s in graficos("pessoa-2") for i in ids(svg(s))]
    for lista in (a, b):
        assert len(lista) == len(set(lista))
    assert not set(a) & set(b)
    for lista in (a, b):  # referencias url(#...) apontam para ids do proprio grafico
        assert all(re.match(r"^g-pessoa-\d-", i) for i in lista)


def test_mesmo_tipo_com_uids_diferentes():
    a, b = svg(g.barras_niveis(NIV, "x")), svg(g.barras_niveis(NIV, "y"))
    assert not set(ids(a)) & set(ids(b))
    s = g.barras_niveis(NIV, "x")
    for ref in re.findall(r'url\(#([^)]+)\)', s):
        assert ref in ids(svg(s))


def test_escape_titulo():
    for s in graficos("a", MAU):
        assert "<script>" not in s
        assert acessivel(s).find(NS + "title").text == MAU
    for t in (g.tabela_niveis(NIV, MAU), g.tabela_patrimonio(PAT, MAU), g.tabela_noticias_por_tema(NOT, MAU)):
        assert "<script>" not in t and "&lt;script&gt;" in t
        assert ET.fromstring(t).find("caption").text == MAU


def test_escape_uid_e_tag():
    s = g.barras_niveis(NIV, '"><script>')
    assert "<script>" not in s
    svg(s)
    s = g.noticias_por_tema({"<b>x</b>": {"2024-01": 1}}, "u")
    assert "<b>" not in s
    raiz = svg(s)
    assert "<b>x</b>" in textos(raiz)
    assert 'class="g-barra tag-outros"' in s


# ---------------------------------------------------------------- numeros
def test_brl_compacto():
    assert g.brl_compacto(0) == "R$ 0"
    assert g.brl_compacto(950) == "R$ 950"
    assert g.brl_compacto(12_345) == "R$ 12,3 mil"
    assert g.brl_compacto(150_000) == "R$ 150 mil"
    assert g.brl_compacto(1_200_000) == "R$ 1,2 mi"
    assert g.brl_compacto(999_960) == "R$ 1 mi"
    assert g.brl_compacto(3_400_000_000) == "R$ 3,4 bi"
    assert g.brl_compacto(-2_500_000) == "-R$ 2,5 mi"
    assert g.brl_compacto(float("nan")) == "—"
    assert g.inteiro(12345) == "12.345"


# ---------------------------------------------------------------- 1. niveis
def test_barras_niveis():
    s = g.barras_niveis(NIV, "n")
    raiz = acessivel(s)
    tx = textos(raiz)
    assert tx == ["Forte", "3", "Atenção", "0", "Informativo", "12"]
    for k in ("forte", "atencao", "informativo"):
        assert f'class="g-barra nv-{k}"' in s
        assert f'fill="url(#g-n-niv-{k})"' in s
    assert s.count('class="g-padrao"') == 3
    zero = [el for el in raiz.iter(NS + "text") if el.text == "0"][0]
    assert zero.get("x") == "104"  # barra minima de 2 px + 6 de folga a partir de x=96
    assert "Atenção: 0" in raiz.find(NS + "desc").text


def test_barras_niveis_vazio_e_grande():
    raiz = acessivel(g.barras_niveis({}, "v"))
    assert textos(raiz) == ["Forte", "0", "Atenção", "0", "Informativo", "0"]
    raiz = acessivel(g.barras_niveis({"forte": 12345, "atencao": None}, "w"))
    assert "12.345" in textos(raiz)


def test_tabela_niveis():
    t = ET.fromstring(g.tabela_niveis(NIV))
    assert t.find("caption").text == "Alertas por nível"
    assert [th.text for th in t.iter("th")] == ["Nível", "Alertas", "Forte", "Atenção", "Informativo", "Total"]
    assert t.find("tfoot").find("tr").find("td").text == "15"


# ---------------------------------------------------------------- 2. patrimonio
def test_patrimonio_vazio():
    assert g.patrimonio([], "p") == '<p class="vazio">Sem declarações para exibir.</p>'
    assert g.patrimonio([(2022, None)], "p") == g.VAZIO_PATRIMONIO
    assert g.tabela_patrimonio([]) == ""


def test_patrimonio_um_ponto():
    s = g.patrimonio([(2022, 1_200_000.0)], "p")
    raiz = acessivel(s)
    assert s.count('class="g-coluna"') == 1
    tx = textos(raiz)
    assert "2022" in tx and "R$ 1,2 mi" in tx


def test_patrimonio_bilhoes():
    s = g.patrimonio(PAT, "p")
    raiz = acessivel(s)
    tx = textos(raiz)
    assert "R$ 4 bi" in tx and "R$ 0" in tx  # grade arredondada
    assert "R$ 3,4 bi" in tx
    assert 3 <= s.count('class="g-eixo"') - 1 <= 4  # linhas acima do zero
    assert s.count('class="g-coluna"') == 3


def test_patrimonio_zero():
    s = g.patrimonio([(2018, 0), (2022, 0)], "z")
    acessivel(s)
    assert s.count('class="g-coluna"') == 2


def test_patrimonio_muitas_eleicoes():
    pts = [(1994 + 2 * i, 100_000.0 * (i + 1)) for i in range(12)]
    acessivel(g.patrimonio(pts, "m"))


def test_tabela_patrimonio():
    t = g.tabela_patrimonio([(2022, 150_000), (2018, 100_000)])
    raiz = ET.fromstring(t)
    linhas = raiz.find("tbody").findall("tr")
    assert [l.find("th").text for l in linhas] == ["2018", "2022"]
    assert [td.text for td in linhas[0].findall("td")] == ["R$ 100.000", "—"]
    assert [td.text for td in linhas[1].findall("td")] == ["R$ 150.000", "+R$ 50.000 (+50,0%)"]
    t = g.tabela_patrimonio([(2018, 100_000), (2022, 0)])
    assert "-R$ 100.000 (-100,0%)" in t


# ---------------------------------------------------------------- 3. mini
def test_mini_patrimonio():
    s = g.mini_patrimonio([(2018, 100_000), (2022, 150_000)], "m")
    raiz = svg(s)
    assert raiz.get("viewBox") == "0 0 96 28"
    assert raiz.get("aria-label") == "Patrimônio de R$ 100 mil em 2018 para R$ 150 mil em 2022"
    c = raiz.find(NS + "circle")
    assert c.get("r") == "3"
    assert raiz.find(NS + "polyline").get("stroke-width") == "2"


def test_mini_patrimonio_poucos_pontos():
    assert g.mini_patrimonio([], "m") == ""
    assert g.mini_patrimonio([(2022, 1.0)], "m") == ""
    svg(g.mini_patrimonio([(2018, 0), (2022, 0)], "m"))  # serie constante


# ---------------------------------------------------------------- 4. noticias
def test_noticias_vazio():
    vazio = '<p class="vazio">Ainda não há notícias classificadas.</p>'
    assert g.noticias_por_tema({}, "t") == vazio
    assert g.noticias_por_tema({"politico": {"2024-01": 0}}, "t") == vazio
    assert g.tabela_noticias_por_tema({}) == ""


def test_noticias_por_tema():
    s = g.noticias_por_tema(NOT, "t")
    raiz = acessivel(s)
    tx = textos(raiz)
    assert tx.index("Político") < tx.index("Criminal")  # ordem de ROTULO_TAG
    assert "Gestão" not in tx  # tema zerado fica de fora
    assert "3 notícias" in tx and "4 notícias" in tx
    assert "jan/2024" in tx and "mar/2024" in tx
    assert s.count('class="g-barra tag-politico"') == 2 and s.count('class="g-barra tag-criminal"') == 1
    assert "pico de 4 em fev/2024" in raiz.find(NS + "desc").text


def test_noticias_um_mes_e_meses_invalidos():
    s = g.noticias_por_tema({"judicial": {"2024-05": 1, "2024-13": 9, "x": 3}}, "t")
    raiz = acessivel(s)
    assert "1 notícia" in textos(raiz)
    assert s.count("<rect") == 1


def test_tabela_noticias_por_tema():
    raiz = ET.fromstring(g.tabela_noticias_por_tema(NOT))
    assert [th.text for th in raiz.find("thead").iter("th")] == ["Mês", "Político", "Criminal", "Total"]
    linhas = raiz.find("tbody").findall("tr")
    assert [l.find("th").text for l in linhas] == ["jan/2024", "fev/2024", "mar/2024"]
    assert [td.text for td in raiz.find("tfoot").iter("td")] == ["3", "4", "7"]
