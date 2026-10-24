"""#68 Indicadores do IBGE da aba Estados (unitario, API mockada, sem rede)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import ibge

IND = dict(id="desemprego", nome="Desemprego", unidade="%", casas=1, melhor="menor", tabelas=[4099],
           variavel="taxa de desocupacao")
ESG = dict(id="esgoto", nome="Casas com esgoto", unidade="%", casas=1, melhor="maior", tabelas=[9],
           variavel="percentual", categorias={"esgot": "rede geral"})


def meta(t, variaveis, classif=(), freq="trimestral", niveis=("N1", "N3")):
    return dict(id=t, periodicidade=dict(frequencia=freq), nivelTerritorial=dict(Administrativo=list(niveis)),
                variaveis=[dict(id=i, nome=n) for i, n in variaveis], classificacoes=list(classif))


def resp(valores):
    """valores: {(nivel, id): {periodo: valor}}"""
    return [dict(id="4099", resultados=[dict(series=[dict(localidade=dict(id=i, nivel=dict(id=n)), serie=s)
                                                      for (n, i), s in valores.items()])])]


def test_resolve_pela_tabela_e_ignora_coeficiente_de_variacao():
    m = meta(4099, [(1, "Taxa de desocupação - coeficiente de variação"), (4099, "Taxa de desocupação")])
    r = ibge.resolver(IND, lambda t: m)
    assert r["tabela"] == 4099 and r["variavel"] == 4099 and r["classificacao"] == ""


def test_tabela_sem_nivel_de_estado_passa_para_a_proxima_candidata():
    metas = {4099: meta(4099, [(4099, "Taxa de desocupação")], niveis=("N1",)),
             6381: meta(6381, [(4099, "Taxa de desocupação")])}
    assert ibge.resolver(dict(IND, tabelas=[4099, 6381]), metas.__getitem__)["tabela"] == 6381


def test_classificacao_no_total_e_categoria_pedida():
    m = meta(9, [(7, "Domicílios - percentual do total geral")], freq="anual", classif=[
        dict(id=2, nome="Sexo", categorias=[dict(id=4, nome="Homens"), dict(id=6794, nome="Total")]),
        dict(id=11558, nome="Esgotamento sanitário", categorias=[dict(id=1, nome="Total"), dict(id=46290, nome="Rede geral ou fossa ligada à rede")])])
    r = ibge.resolver(ESG, lambda t: m)
    assert r["classificacao"] == "C2[6794]|C11558[46290]"
    assert "classificacao=C2[6794]|C11558[46290]" in ibge.url_valores(r, 6)


def test_series_resumo_e_tendencia():
    s = ibge.series(resp({("N1", "1"): {"202502": "6.9", "202601": "7.0", "202602": "6.1"},
                          ("N3", "35"): {"202502": "6.0", "202602": "6.0"}, ("N3", "11"): {"202602": "..."}}))
    assert set(s) == {"BR", "SP", "RO"} and s["RO"] == {}
    br = ibge.resumo(s["BR"], "TRIMESTRAL")
    assert br == [6.1, 6.9, "2º tri 2026", "2º tri 2025"]  # mesmo trimestre do ano anterior
    assert ibge.tendencia(br, IND) == "melhor" and ibge.tendencia(ibge.resumo(s["SP"], "TRIMESTRAL"), IND) == "igual"
    assert ibge.tendencia([10.0, 9.0, "", ""], dict(melhor="maior", casas=0)) == "melhor"
    assert ibge.tendencia([10.0, None, "2025", None], IND) is None and ibge.resumo({}, "ANUAL") is None


def test_anual_compara_com_o_periodo_anterior():
    assert ibge.resumo({"2023": 5.4, "2024": 5.3}, "ANUAL") == [5.3, 5.4, "2024", "2023"]


class CacheFalso(dict):
    def set(self, k, v):
        self[k] = v

    def salvar(self):
        pass


def obter_falso(url):
    if url.endswith("/metadados"):
        return meta(4099, [(4099, "Taxa de desocupação")])
    return resp({("N1", "1"): {"202502": "6.9", "202602": "6.1"}, ("N3", "35"): {"202502": "6.0", "202602": "6.5"}})


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
