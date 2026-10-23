"""Economia no periodo (#55): leitura do SIDRA com respostas mockadas, crescimento real, atraso do PIB por UF,
selos e integracao com o pipeline (--demo), sem rede."""
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


def econ_teste():
    return dict(brasil=dict(volume={"2019": 1.0, "2020": -4.0, "2021": 5.0, "2022": 3.0},
                            deflator={"2019": 4.0, "2020": 5.0, "2021": 10.0, "2022": 8.0}),
                uf={"SP": {"2018": 100.0, "2019": 105.0, "2020": 103.0, "2021": 118.0}})


# ---------- leitura ----------

def test_ler_sidra_acha_dimensoes_pelo_cabecalho_e_pula_sem_numero():
    inv = sidra(["Variável", "Ano", "Brasil"], [("1.5", "9810", "2019", "1")])  # outra ordem de dimensoes
    assert economia.ler_sidra(inv) == [dict(territorio="1", variavel="9810", periodo="2019", valor=1.5)]
    assert len(economia.ler_sidra(BRASIL)) == 4  # "..." sai
    assert economia.ler_sidra(None) == [] and economia.ler_sidra([{"V": "x"}]) == []


def test_montar_separa_volume_deflator_e_uf():
    m = economia.montar(BRASIL, UF, SIGLAS)
    assert m["brasil"] == dict(volume={"2019": 1.3, "2020": -3.3}, deflator={"2019": 4.0, "2020": 5.0})
    assert m["uf"] == {"SP": {"2018": 100.0, "2019": 110.0}, "BA": {"2018": 50.0}}  # codigo 99 fora


def test_urls_oficiais_sem_chave():
    u = economia.urls()
    assert all(x.startswith("https://apisidra.ibge.gov.br/values/") for x in u.values()) and len(u) == 2
    assert "/t/6784/" in u["brasil"] and "/t/5938/n3/all/v/37/" in u["uf"]


# ---------- coleta ----------

def test_coletar_grava_e_usa_o_ultimo_salvo_quando_ibge_cai(tmp_path):
    arq = tmp_path / "economia.json"
    respostas = {"6784": BRASIL, "5938": UF}
    buscar = lambda url: next(v for k, v in respostas.items() if f"/t/{k}/" in url)
    ok = economia.coletar(buscar, SIGLAS, arq, hoje=dt.date(2026, 10, 23))
    assert ok["atualizado"] == "2026-10-23" and json.loads(arq.read_text())["uf"]["SP"]["2019"] == 110.0
    assert economia.coletar(lambda url: None, SIGLAS, arq) == ok  # fora do ar: ultimo salvo
    assert economia.coletar(lambda url: None, SIGLAS, tmp_path / "nada.json") == {}


# ---------- contas ----------

def test_brasil_acumula_variacao_real():
    assert economia.real_brasil(econ_teste(), 2018, 2022) == pytest.approx(1.01 * 0.96 * 1.05 * 1.03 - 1)
    assert economia.real_brasil(econ_teste(), 2018, 2025) is None


def test_estado_estimado_com_deflator_nacional():
    e = econ_teste()
    assert economia.real_uf(e, "SP", 2018, 2021) == pytest.approx(1.18 / (1.04 * 1.05 * 1.10) - 1)
    assert economia.real_uf(e, "SP", 2018, 2019) == pytest.approx(1.05 / 1.04 - 1)
    assert economia.real_uf(e, "RJ", 2018, 2019) is None


def test_periodo_respeita_o_atraso_e_aponta_recessao():
    p = economia.periodo(econ_teste(), dict(ano_ini=2018, ano_fim=2022, uf="SP"))
    assert p["brasil"]["fim"] == 2022 and p["estado"]["fim"] == 2021
    assert p["brasil"]["quedas"] == [2020] and p["estado"]["quedas"] == [2020]  # 2020: nominal -1,9%, deflator +5%
    assert economia.periodo(econ_teste(), dict(ano_ini=2022, ano_fim=2026, uf="SP"))["brasil"] is None
    br = economia.periodo(econ_teste(), dict(ano_ini=2018, ano_fim=2022, uf="BR"))
    assert br["uf"] is None and br["estado"] is None and br["brasil"]


def test_sinal_crescimento_declinio_estavel():
    assert [economia.sinal(v)[1] for v in (0.05, -0.02, 0.001, None)] == \
           ["Em crescimento", "Em declínio", "Estável", "Não informado"]


# ---------- textos ----------

def test_pct_em_portugues():
    assert [economia.pct(v) for v in (0.056, 1.85, -0.033, 0.0, None, 0.05)] == \
           ["+5,6%", "+185%", "−3,3%", "0%", "Não informado", "+5%"]


def test_nome_do_estado_com_artigo_certo():
    assert economia._nome_uf("BA", "de") == "da Bahia" and economia._nome_uf("PA", "de") == "do Pará"
    assert economia._nome_uf("SP", "de") == "de São Paulo" and economia._nome_uf("BA") == "a Bahia"


def test_frase_em_linguagem_simples_sem_falar_de_patrimonio():
    f = economia.frase(economia.periodo(econ_teste(), dict(ano_ini=2018, ano_fim=2022, uf="SP")))
    assert f.startswith("Entre as declarações de 2018 e 2022, descontada a inflação, a economia de São Paulo")
    assert "(dados até 2021)" in f and "recessão" in f and "2020" in f and "patrimônio" not in f


def test_secao_omitida_fora_do_ar_e_sem_periodo():
    linhas = [dict(ano_ini=2018, ano_fim=2022, uf="SP")]
    assert economia.secao(None, linhas) == ""
    assert "Fonte não encontrada" in economia.secao({}, linhas)
    tarde = economia.secao(econ_teste(), [dict(ano_ini=2022, ano_fim=2026, uf="SP")])
    assert "Não informado" in tarde and "ainda não publicou" in tarde


def test_secao_so_com_selos_do_ultimo_periodo_e_links_oficiais():
    linhas = [dict(ano_ini=2014, ano_fim=2018, uf="SP"), dict(ano_ini=2018, ano_fim=2022, uf="SP")]
    h = economia.secao(econ_teste(), linhas)
    assert "entre as declarações de 2018 e 2022" in h and "2014" not in h
    assert "▼ São Paulo em declínio" in h and "dados até 2021" in h and "▲ Brasil em crescimento" in h
    assert "▼ Recessão em 2020" in h
    assert "<table" not in h and "Patrimônio" not in h
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


def test_pipeline_demo_mostra_economia_no_periodo_na_aba_patrimonio(pagina_demo):
    aba = pagina_demo.split('id="patrimonio"', 1)[1].split("</section>", 1)[0]
    assert "Economia no período" in aba and 'class="eco-linha"' in aba and "Brasil em crescimento" in aba
    assert "sidra.ibge.gov.br" in aba
