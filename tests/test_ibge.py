"""#68 Indicadores do IBGE da aba Estados (unitario, API mockada, sem rede)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import ibge

IND = dict(id="desemprego", nome="Desemprego", unidade="%", casas=1, melhor="menor", tabelas=[4099],
           variavel="taxa de desocupacao")
ESG = dict(id="esgoto", nome="Casas com esgoto", unidade="%", casas=1, melhor="maior", tabelas=[9],
           variavel="percentual", categorias={"esgot": "rede geral"})


CAB = {"NC": "Nível Territorial (Código)", "NN": "Nível Territorial", "MN": "Unidade de Medida", "V": "Valor",
       "D1C": "Brasil e Unidade da Federação (Código)", "D1N": "Brasil e Unidade da Federação",
       "D2C": "Trimestre (Código)", "D2N": "Trimestre", "D3C": "Variável (Código)", "D3N": "Variável"}


def sidra(valores, var="Taxa de desocupação, na semana de referência", per="Trimestre"):
    """Resposta do apisidra: valores {(nivel '1'/'3', codigo): {periodo: valor}}; inclui o coeficiente de variacao."""
    cab = {**CAB, "D2C": f"{per} (Código)", "D2N": per}
    linhas = [cab]
    for (nc, cod), s in valores.items():
        for p, v in s.items():
            for nome, val in ((var + " - coeficiente de variação", "1.5"), (var, v)):
                linhas.append(dict(NC=nc, NN="x", MN="%", V=val, D1C=cod, D1N="x", D2C=p, D2N="x", D3C="1", D3N=nome))
    return linhas


def test_ler_sidra_acha_a_variavel_e_ignora_coeficiente_de_variacao():
    s, freq, var = ibge.ler_sidra(sidra({("1", "1"): {"202502": "6.9", "202602": "6.1"},
                                         ("3", "35"): {"202502": "6.0", "202602": "6.0"}, ("3", "11"): {"202602": "..."}}), IND)
    assert freq == "TRIMESTRAL" and var == "Taxa de desocupação, na semana de referência"
    assert s == {"BR": {"202502": 6.9, "202602": 6.1}, "SP": {"202502": 6.0, "202602": 6.0}}
    br = ibge.resumo(s["BR"], freq)
    assert br == [6.1, 6.9, "2º tri 2026", "2º tri 2025"]  # mesmo trimestre do ano anterior
    assert ibge.tendencia(br, IND) == "melhor" and ibge.tendencia(ibge.resumo(s["SP"], freq), IND) == "igual"
    assert ibge.tendencia([10.0, 9.0, "", ""], dict(melhor="maior", casas=0)) == "melhor"
    assert ibge.tendencia([10.0, None, "2025", None], IND) is None and ibge.resumo({}, "ANUAL") is None


def test_ler_sidra_sem_a_variavel_ou_resposta_esquisita_e_none():
    assert ibge.ler_sidra(sidra({("1", "1"): {"2024": "5"}}, var="Outra coisa", per="Ano"), IND) is None
    assert ibge.ler_sidra("Tabela nao encontrada", IND) is None and ibge.ler_sidra([CAB], IND) is None
    assert ibge.ler_sidra(sidra({("1", "1"): {"2024": "5"}}, per="Ano"), IND)[1] == "ANUAL"


def test_url_do_sidra_e_categoria_pela_descricao():
    assert ibge.url_sidra(4099) == "https://apisidra.ibge.gov.br/values/t/4099/n1/all/n3/all/v/all/p/last%206"
    html = ("<p><b>C1</b> Situação do domicílio (3): 1 Total, 2 Urbana</p>\n<p><b>C11558</b> Esgotamento sanitário (4):</p>"
            "\n<p>46289 Total</p>\n<p>46290 Rede geral, rede pluvial ou fossa ligada à rede</p>\n<p>46291 Fossa não ligada</p>")
    assert ibge.classif_desc(html, ESG["categorias"]) == "/c11558/46290"
    assert ibge.classif_desc(html, {"esgot": "poco artesiano"}) is None


def test_anual_compara_com_o_periodo_anterior():
    assert ibge.resumo({"2023": 5.4, "2024": 5.3}, "ANUAL") == [5.3, 5.4, "2024", "2023"]


class CacheFalso(dict):
    def set(self, k, v):
        self[k] = v

    def salvar(self):
        pass


def obter_falso(url):
    if "desctabapi" in url:
        return "<p>C11558 Esgotamento sanitário</p>\n<p>46290 Rede geral</p>"
    return sidra({("1", "1"): {"202502": "6.9", "202602": "6.1"}, ("3", "35"): {"202502": "6.0", "202602": "6.5"}})


CSV = "iso3,country,hdi_rank_2023,hdi_2022,hdi_2023\nBRA,Brazil,84,0.780,0.786\nARG,Argentina,47,0.84,0.85\n"


def test_coletar_monta_tudo_e_usa_cache():
    c = CacheFalso()
    d = ibge.coletar(c, dict(indicadores=[IND], idh=dict(urls=["https://x/a.csv"], link="https://hdr.undp.org/x")),
                     obter_falso, lambda u: CSV.encode(), agora=1000)
    assert d["indicadores"][0]["link"] == "https://sidra.ibge.gov.br/tabela/4099"
    assert d["valores"]["BR"]["desemprego"][-1] == "melhor" and d["valores"]["SP"]["desemprego"][-1] == "pior"
    assert d["idh"] == dict(valor=0.786, anterior=0.78, ano=2023, posicao=84, link="https://hdr.undp.org/x")
    falha = lambda u: (_ for _ in ()).throw(OSError("fora"))
    cfg1 = dict(indicadores=[IND], idh=dict(urls=["https://x/a.csv"]))
    assert ibge.coletar(c, cfg1, falha, falha, agora=2000) == d  # dentro da semana: cache
    assert ibge.coletar(c, cfg1, falha, falha, agora=1000 + 8 * 86400) == d  # fora: ultima boa


def test_cache_incompleto_tenta_de_novo_na_carga():
    c = CacheFalso({ibge.CHAVE: dict(em=1000, dados=dict(indicadores=[], valores={}, idh=dict(valor=0.786)))})
    d = ibge.coletar(c, dict(indicadores=[IND], idh=dict(urls=["https://x/a.csv"])), obter_falso, lambda u: CSV.encode(), agora=2000)
    assert [i["id"] for i in d["indicadores"]] == ["desemprego"] and c[ibge.CHAVE]["em"] == 2000


def test_tudo_fora_do_ar_e_none():
    falha = lambda u: (_ for _ in ()).throw(OSError("fora"))
    assert ibge.coletar(None, dict(indicadores=[IND], idh=dict(urls=["https://x"])), falha, falha) is None


def test_config_real_sem_pib_e_demo_no_formato():
    cfg = ibge.ler_config()
    assert not any("PIB" in ibge.norm(i["nome"]) or "pib" in i["id"] for i in cfg["indicadores"])  # #55
    d = ibge.demo()
    assert set(d["valores"]) == {"BR", *ibge.UFS} and all(len(v) == 5 for v in d["valores"]["BR"].values())


def test_fora_do_ar_para_na_primeira_falha():
    chamadas = []

    def lento(url):
        chamadas.append(url)
        raise TimeoutError("timed out")
    cfg = dict(indicadores=[IND, ESG, dict(IND, id="outro")])
    assert ibge.coletar(None, cfg, lento, lambda u: (_ for _ in ()).throw(OSError("fora")), sondar=lambda: chamadas.append("sonda")) is None
    assert len(chamadas) == 2 and chamadas[-1] == "sonda"  # a primeira falha de rede pula o resto e sonda os caminhos


def test_tabela_com_erro_http_nao_derruba_as_outras():
    import urllib.error

    def obter(url):
        if "/9/" in url:
            raise urllib.error.HTTPError(url, 500, "erro", None, None)
        return obter_falso(url)
    d = ibge.coletar(None, dict(indicadores=[dict(ESG, tabelas=[9]), IND]), obter, lambda u: b"")
    assert [i["id"] for i in d["indicadores"]] == ["desemprego"]


def test_dado_antigo_nao_entra_e_log_descreve_a_tabela(capsys):
    velho = lambda url: sidra({("1", "1"): {"2015": "13.8", "2016": "13.3"}}, var="Taxa de mortalidade infantil", per="Ano")
    ind = dict(IND, id="mortalidade", variavel="mortalidade infantil", tabelas=[3834])
    assert ibge.coletar(None, dict(indicadores=[ind]), velho, lambda u: b"", agora=1793000000) is None  # 2026
    assert "dado antigo (ultimo ano 2016)" in capsys.readouterr().out
    ibge.coletar(None, dict(indicadores=[dict(ind, variavel="analfabetismo")]), velho, lambda u: b"", agora=1793000000)
    assert "variaveis ['Taxa de mortalidade infantil - coeficiente de variação', 'Taxa de mortalidade infantil']" in capsys.readouterr().out


def test_classificacao_com_varias_categorias_fica_no_total_e_projecao_ate_o_ano_atual():
    cab = {**CAB, "D2C": "Ano (Código)", "D2N": "Ano", "D4C": "Sexo (Código)", "D4N": "Sexo", "D5C": "Ano (Código)", "D5N": "Ano"}
    linhas = [cab] + [dict(NC="1", V=v, D1C="1", D2C="2024", D3N="Taxa de mortalidade infantil", D4N=sexo, D5C=ano)
                      for sexo, base in (("Homens", 20.0), ("Total", 12.0)) for ano, v in
                      (("2025", str(base)), ("2026", str(base - 1)), ("2030", "1.0"))]
    s, freq, _ = ibge.ler_sidra(linhas, dict(variavel="mortalidade infantil"), ano_max=2026)
    assert freq == "ANUAL" and s == {"BR": {"2025": 12.0, "2026": 11.0}}  # Total; 2030 (projecao futura) fora
    cab7113 = {**CAB, "D2C": "Ano (Código)", "D2N": "Ano", "D4C": "Grupo de idade (Código)", "D4N": "Grupo de idade"}
    linhas = [cab7113] + [dict(NC="1", V=v, D1C="1", D2C="2024", D3N="Taxa de analfabetismo", D4N=g)
                          for g, v in (("15 a 19 anos", "1.0"), ("15 anos ou mais", "5.3"), ("60 anos ou mais", "15.0"))]
    assert ibge.ler_sidra(linhas, dict(variavel="analfabetismo", preferir=["15 anos ou mais"]))[0] == {"BR": {"2024": 5.3}}


def test_descricao_com_403_usa_os_metadados_do_site():
    import urllib.error
    meta = {"Id": 6805, "Classificacoes": [{"Id": 1, "Nome": "Situação", "Categorias": [{"Id": 6795, "Nome": "Total"}]},
                                           {"Id": 11558, "Nome": "Esgotamento sanitário",
                                            "Categorias": [{"Id": 46289, "Nome": "Total"}, {"Id": 46290, "Nome": "Rede geral ou fossa"}]}]}
    assert ibge.classif_json(meta, ESG["categorias"]) == "/c11558/46290"
    assert ibge.classif_json(meta, {"esgot": "poco"}) is None
    urls = []

    def obter(url):
        urls.append(url)
        if "desctabapi" in url:
            raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)
        return meta if "/Ajax/" in url else obter_falso(url)
    d = ibge.coletar(None, dict(indicadores=[dict(ESG, variavel="desocupacao")]), obter, lambda u: b"")
    assert [i["id"] for i in d["indicadores"]] == ["esgoto"] and urls[-1].endswith("/c11558/46290")
