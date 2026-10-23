"""Patrimonio x economia (#55): leitura do SIDRA com respostas mockadas, contas descontada a inflacao, atraso do PIB
por UF, textos e integracao com o pipeline (--demo), sem rede."""
import datetime as dt, json, os, subprocess, sys
from pathlib import Path
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
import economia  # noqa: E402

SIGLAS = {"35": "SP", "29": "BA"}


def sidra(dims, linhas):
    """Resposta do apisidra: cabecalho + linhas. `dims`: rotulos de D1..Dn; `linhas`: (valor, codigos...)."""
    cab = {"V": "Valor", **{f"D{i}C": f"{r} (Código)" for i, r in enumerate(dims, 1)}}
    return [cab] + [{"V": v, **{f"D{i}C": c for i, c in enumerate(cods, 1)}} for v, *cods in linhas]


BRASIL = sidra(["Brasil", "Variável", "Ano"], [("1.3", "1", "9810", "2019"), ("-3.3", "1", "9810", "2020"),
                                               ("4.0", "1", "9811", "2019"), ("5.0", "1", "9811", "2020"),
                                               ("...", "1", "9810", "2021")])
UF = sidra(["Unidade da Federação", "Variável", "Ano"], [("100", "35", "37", "2018"), ("110", "35", "37", "2019"),
                                                         ("50", "29", "37", "2018"), ("99", "99", "37", "2018")])
IPCA = sidra(["Variável", "Mês", "Brasil"], [("1000", "2266", "201807", "1"), ("1100", "2266", "201907", "1"),
                                             ("1200", "2266", "202007", "1"), ("9", "2266", "202008", "1")])


def econ_teste():
    return dict(brasil=dict(volume={"2019": 1.0, "2020": -4.0, "2021": 5.0, "2022": 3.0},
                            deflator={"2019": 4.0, "2020": 5.0, "2021": 10.0, "2022": 8.0}),
                uf={"SP": {"2018": 100.0, "2019": 105.0, "2020": 103.0, "2021": 118.0}},
                ipca={"2018": 100.0, "2022": 125.0, "2020": 108.0})


# ---------- leitura ----------

def test_ler_sidra_acha_dimensoes_pelo_cabecalho_e_pula_sem_numero():
    linhas = economia.ler_sidra(IPCA)
    assert linhas[0] == dict(territorio="1", variavel="2266", periodo="201807", valor=1000.0)
    assert len(economia.ler_sidra(BRASIL)) == 4  # "..." sai
    assert economia.ler_sidra(None) == [] and economia.ler_sidra([{"V": "x"}]) == []


def test_montar_separa_volume_deflator_uf_e_ipca_de_julho():
    m = economia.montar(BRASIL, UF, IPCA, SIGLAS)
    assert m["brasil"] == dict(volume={"2019": 1.3, "2020": -3.3}, deflator={"2019": 4.0, "2020": 5.0})
    assert m["uf"] == {"SP": {"2018": 100.0, "2019": 110.0}, "BA": {"2018": 50.0}}  # codigo 99 fora
    assert m["ipca"] == {"2018": 1000.0, "2019": 1100.0, "2020": 1200.0}  # agosto fora


def test_urls_sem_chave_e_ipca_em_julho():
    u = economia.urls(dt.date(2026, 10, 23))
    assert all(x.startswith("https://apisidra.ibge.gov.br/values/") for x in u.values())
    assert "/t/6784/" in u["brasil"] and "/t/5938/n3/all/v/37/" in u["uf"]
    assert u["ipca"].endswith("/p/" + ",".join(f"{a}07" for a in range(2002, 2027)))
    assert "202607" in u["ipca"] and "202608" not in u["ipca"]


# ---------- coleta ----------

def test_coletar_grava_e_usa_o_ultimo_salvo_quando_ibge_cai(tmp_path):
    arq = tmp_path / "economia.json"
    respostas = {"6784": BRASIL, "5938": UF, "1737": IPCA}
    buscar = lambda url: next(v for k, v in respostas.items() if f"/t/{k}/" in url)
    ok = economia.coletar(buscar, SIGLAS, arq, hoje=dt.date(2026, 10, 23))
    assert ok["atualizado"] == "2026-10-23" and json.loads(arq.read_text())["uf"]["SP"]["2019"] == 110.0
    assert economia.coletar(lambda url: None, SIGLAS, arq) == ok  # fora do ar: ultimo salvo
    assert economia.coletar(lambda url: None, SIGLAS, tmp_path / "nada.json") == {}


# ---------- contas ----------

def test_patrimonio_descontado_o_ipca():
    e = econ_teste()
    assert economia.real_patrimonio(e, 2018, 2022, 100, 250) == pytest.approx(250 / 100 / 1.25 - 1)
    assert economia.real_patrimonio(e, 2018, 2026, 100, 250) is None  # sem IPCA do fim
    assert economia.real_patrimonio(e, 2018, 2022, 0, 250) is None


def test_brasil_acumula_variacao_real_e_aponta_recessao():
    e = econ_teste()
    assert economia.real_brasil(e, 2018, 2022) == pytest.approx(1.01 * 0.96 * 1.05 * 1.03 - 1)
    assert economia.quedas_brasil(e, 2018, 2022) == [(2020, -4.0)]


def test_estado_estimado_com_deflator_nacional():
    e = econ_teste()
    assert economia.real_uf(e, "SP", 2018, 2021) == pytest.approx(1.18 / (1.04 * 1.05 * 1.10) - 1)
    assert [a for a, _ in economia.quedas_uf(e, "SP", 2018, 2021)] == [2020]  # 2020: nominal -1,9% e deflator +5%
    assert economia.real_uf(e, "SP", 2018, 2019) == pytest.approx(1.05 / 1.04 - 1)


def test_comparar_respeita_o_atraso_de_cada_economia():
    c = economia.comparar(econ_teste(), dict(ano_ini=2018, ano_fim=2022, uf="SP", pat_ini=100, pat_fim=250))
    assert c["brasil"]["fim"] == 2022 and c["estado"]["fim"] == 2021
    sem = economia.comparar(econ_teste(), dict(ano_ini=2022, ano_fim=2026, uf="SP", pat_ini=1, pat_fim=2))
    assert sem["estado"] is None and sem["brasil"] is None and sem["patrimonio"] is None
    br = economia.comparar(econ_teste(), dict(ano_ini=2018, ano_fim=2022, uf="BR", pat_ini=1, pat_fim=2))
    assert br["uf"] is None and br["estado"] is None and br["brasil"]


# ---------- textos ----------

def test_pct_em_portugues():
    assert [economia.pct(v) for v in (0.056, 1.85, -0.033, 0.0, None, 0.05)] == \
           ["+5,6%", "+185%", "−3,3%", "0%", "Não informado", "+5%"]


def test_nome_do_estado_com_artigo_certo():
    assert economia._nome_uf("BA", "de") == "da Bahia" and economia._nome_uf("PA", "de") == "do Pará"
    assert economia._nome_uf("SP", "de") == "de São Paulo" and economia._nome_uf("BA") == "a Bahia"


def test_frase_em_linguagem_simples_com_atraso_e_recessao():
    c = economia.comparar(econ_teste(), dict(ano_ini=2018, ano_fim=2022, uf="SP", pat_ini=100, pat_fim=250))
    f = economia.frase(c)
    assert f.startswith("De 2018 a 2022, descontada a inflação, o patrimônio declarado cresceu 100%.")
    assert "a economia de São Paulo" in f and "(dados até 2021)" in f and "recessão" in f and "2020" in f


def test_secao_omitida_fora_do_ar_e_sem_periodo():
    linhas = [dict(ano_ini=2018, ano_fim=2022, uf="SP", pat_ini=100, pat_fim=250)]
    assert economia.secao(None, linhas) == ""
    assert "Fonte não encontrada" in economia.secao({}, linhas)
    tarde = economia.secao(econ_teste(), [dict(ano_ini=2022, ano_fim=2026, uf="SP", pat_ini=1, pat_fim=2)])
    assert "Não informado" in tarde and "ainda não publicou" in tarde


def test_secao_com_barras_tabela_e_links_oficiais():
    linhas = [dict(ano_ini=2014, ano_fim=2018, uf="SP", pat_ini=1, pat_fim=2),
              dict(ano_ini=2018, ano_fim=2022, uf="SP", pat_ini=100, pat_fim=80)]
    h = economia.secao(econ_teste(), linhas)
    assert h.count('class="eco-barra ') == 3 and "eco-neg" in h  # patrimonio caiu: barra para a esquerda
    assert "<table" in h and "2014–2018" in h and "Não informado" in h
    assert all(link in h for link in economia.LINK.values())


# ---------- integracao ----------

@pytest.fixture(scope="module")
def pagina_demo(tmp_path_factory):
    saida = tmp_path_factory.mktemp("eco")
    env = {**os.environ, "ID_SEGREDO": "segredo-de-teste"}
    for k in ("MONITORADOS_CSV", "TRANSPARENCIA_TOKEN", "TELEGRAM_TOKEN"):
        env.pop(k, None)
    subprocess.run([sys.executable, str(RAIZ / "src" / "pipeline.py"), "--demo", "--saida", str(saida)],
                   check=True, env=env, capture_output=True)
    return next((saida / "docs" / "pessoa").glob("*.html")).read_text(encoding="utf-8")


def test_pipeline_demo_mostra_patrimonio_x_economia_na_aba_patrimonio(pagina_demo):
    aba = pagina_demo.split('id="patrimonio"', 1)[1].split("</section>", 1)[0]
    assert "Patrimônio × economia" in aba and "descontada a inflação" in aba and "eco-barras" in aba
    assert "sidra.ibge.gov.br" in aba
