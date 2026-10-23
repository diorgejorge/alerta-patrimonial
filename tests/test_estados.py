"""Dossie por estado (#53): leitura do SICONFI e das emendas com respostas mockadas, montagem das paginas e
integracao com o pipeline (--demo), sem rede."""
import datetime as dt, json, re, sys, urllib.parse
from pathlib import Path
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import estados  # noqa: E402

HOJE = dt.date(2026, 10, 23)


def item(conta, valor, coluna):
    return dict(conta=conta, valor=valor, coluna=coluna)


DESPESA = [item("10 - Saúde", 900.0, "Despesas Liquidadas"), item("12 - Educação", 500.0, "Despesas Liquidadas"),
           item("10 - Saúde", 50.0, "Despesas Liquidadas"),  # bloco intraorcamentario: menor, ignorado
           item("10.301 - Atenção Básica", 300.0, "Despesas Liquidadas"),  # subfuncao: fora
           item("10 - Saúde", 999.0, "Despesas Empenhadas")]  # outra coluna: fora
RECEITA = [item("1.7.1.0.00.0.0 - Transferências da União e de suas Entidades", 1000.0, "Receitas Brutas Realizadas"),
           item("1.7.1.1.00.0.0 - Participação na Receita da União", 600.0, "Receitas Brutas Realizadas"),
           item("1.7.1.1.51.0.0 - Cota-Parte do FPE", 600.0, "Receitas Brutas Realizadas"),
           item("1.7.1.6.00.0.0 - Transferências de Convênios da União", 150.0, "Receitas Brutas Realizadas"),
           item("2.4.1.9.00.0.0 - Transferências Especiais da União", 80.0, "Receitas Brutas Realizadas"),
           item("1.7.1.1.51.0.0 - Cota-Parte do FPE", -10.0, "Deduções - FUNDEB")]


class BuscarFalso:
    """SICONFI de mentira: responde por (recurso, id_ente, ano, anexo) e anota as URLs pedidas."""

    def __init__(self, respostas, falha=()):
        self.respostas, self.falha, self.urls = respostas, set(falha), []

    def __call__(self, url):
        self.urls.append(url)
        u = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(u.query))
        k = (u.path.rsplit("/", 1)[-1], q.get("id_ente"), q.get("an_exercicio"), q.get("no_anexo"))
        if k in self.falha:
            return None
        return dict(items=self.respostas.get(k, []), hasMore=False)


class ApiFalsa:
    def __init__(self, por_ano, falha=()):
        self.por_ano, self.falha, self.falhas, self.pedidos = por_ano, set(falha), 0, []

    def ativa(self):
        return True

    def paginas(self, caminho, max_paginas=20, **params):
        self.pedidos.append(params["ano"])
        if params["ano"] in self.falha:
            self.falhas += 1
            return None
        return self.por_ano.get(params["ano"], [])


class CacheMem:
    def __init__(self):
        self.d, self.salvo = {}, False

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v

    def salvar(self):
        self.salvo = True


def emenda(autor, local, pago, tipo="Emenda Individual - Transferências Especiais", resto=0, subfuncao="Atenção Básica",
           ano=2025, empenhado=0):
    return dict(nomeAutor=autor, tipoEmenda=tipo, localidadeDoGasto=local, funcao="Saúde", subfuncao=subfuncao,
                ano=ano, codigoEmenda=f"{ano}{autor[:3]}", valorEmpenhado=empenhado,
                valorPago=f"{pago:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."), valorRestoPago=resto)


S2ID_CSV = ("UF;Município;Código IBGE;COBRADE;Data da Publicação\n"
            "SP;Campinas;3509502;Chuvas Intensas;15/01/2025\n"
            "RJ;Petrópolis;3303906;Chuvas Intensas;2024-02-20\n").encode("latin-1")
CKAN = {"result": {"resources": [dict(name="Reconhecimentos Realizados", url="https://mdr/rec.csv"),
                                 dict(name="Danos informados", url="https://mdr/danos.csv")]}}


# ---------------------------------------------------------------- unidades
@pytest.mark.parametrize("v,txt", [(1_234_000_000, "R$ 1,2 bi"), (350_000_000, "R$ 350 mi"), (12_300, "R$ 12,3 mil"),
                                   (950, "R$ 950"), (None, "Não informado")])
def test_brl_curto(v, txt):
    assert estados.brl_curto(v) == txt


@pytest.mark.parametrize("s,esperado", [("SÃO PAULO (UF)", ("SP", None)), ("CAMPINAS - SP", ("SP", "CAMPINAS")),
                                         ("EMBU-GUAÇU - SP", ("SP", "EMBU-GUACU")), ("Nacional", None),
                                         ("SUDESTE (REGIÃO)", None), ("CIDADE - XX", None), ("", None)])
def test_local_do_gasto(s, esperado):
    assert estados.local(s) == esperado


def test_relativo_e_anos():
    assert estados.relativo("pessoa/p0001.html") == "../pessoa/p0001.html"
    assert estados.relativo("https://www.camara.leg.br/deputados/1") == "https://www.camara.leg.br/deputados/1"
    assert estados.relativo(None) is None
    assert estados.ano_dca(dt.date(2026, 10, 1)) == 2025 and estados.ano_dca(dt.date(2026, 3, 1)) == 2024
    assert estados.mandato_estadual([2018, 2022, 2026], HOJE) == 2022  # eleitos de 2026 so tomam posse em 2027
    assert estados.mandato_estadual([2026], HOJE) is None


def test_despesa_por_funcao():
    assert estados.despesa_por_funcao(DESPESA) == [("Saúde", 900.0), ("Educação", 500.0)]


def test_receitas_uniao_usa_o_nivel_mais_detalhado_sem_somar_duas_vezes():
    r = estados.receitas_uniao(RECEITA)
    assert r == [("Cota-Parte do FPE", 600.0, "legais"), ("Transferências de Convênios da União", 150.0, "voluntarias"),
                 ("Transferências Especiais da União", 80.0, "especiais")]
    assert sum(v for _, v, _ in r) == 830.0


def test_siconfi_junta_paginas_e_falha_vira_none():
    lotes = iter([dict(items=[1, 2], hasMore=True), dict(items=[3], hasMore=False)])
    urls = []
    assert estados.siconfi(lambda u: urls.append(u) or next(lotes), "dca", id_ente=35) == [1, 2, 3]
    assert "offset=2" in urls[1]
    assert estados.siconfi(lambda u: None, "dca") is None


def test_dca_tenta_o_ano_anterior_e_usa_cache():
    b = BuscarFalso({("dca", "35", "2024", "DCA-Anexo I-E"): DESPESA})
    cache = CacheMem()
    ler = estados.despesa_por_funcao
    assert estados.dca(b, "35", "DCA-Anexo I-E", 2025, ler, cache) == (2024, [("Saúde", 900.0), ("Educação", 500.0)])
    n = len(b.urls)
    assert estados.dca(b, "35", "DCA-Anexo I-E", 2025, ler, cache)[0] == 2024
    assert len(b.urls) == n  # 2025 vazio e 2024 vieram do cache: a proxima execucao continua de onde parou
    assert estados.dca(BuscarFalso({}, falha=[("dca", "35", "2025", "DCA-Anexo I-E")]), "35", "DCA-Anexo I-E", 2025, ler) \
        == (None, None)


def test_financas_marca_falha_por_secao():
    b = BuscarFalso({("dca", "35", "2025", "DCA-Anexo I-C"): RECEITA}, falha=[("dca", "35", "2025", "DCA-Anexo I-E")])
    f = estados.financas(b, "35", 2025)
    assert f["despesa"] == "falha" and f["ano_receita"] == 2025 and len(f["receita"]) == 3


class Resposta:
    def __init__(self, corpo):
        self.corpo = corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.corpo


def erro_http(codigo, retry=None):
    import urllib.error
    return urllib.error.HTTPError("u", codigo, "x", {"Retry-After": retry} if retry else {}, None)


def buscador(*respostas):
    fila, esperas = list(respostas), []

    def abrir(req, timeout):
        r = fila.pop(0)
        if isinstance(r, Exception):
            raise r
        return Resposta(r)
    return estados.Buscador(intervalo=0, abrir=abrir, dormir=esperas.append), esperas, fila


def test_buscador_espera_no_429_e_tenta_de_novo():
    b, esperas, _ = buscador(erro_http(429, "7"), erro_http(429), b'{"items": [1]}')
    assert b("https://x") == {"items": [1]} and esperas == [7, 30] and b.falhas == 0


def test_buscador_desiste_no_404_e_depois_de_tres_recuos():
    b, esperas, fila = buscador(erro_http(404), b"{}")
    assert b("https://x") is None and esperas == [] and len(fila) == 1  # 404 nao adianta repetir
    b, esperas, _ = buscador(*[erro_http(503)] * 4)
    assert b("https://x") is None and esperas == [10, 30, 60] and b.falhas == 1


def test_municipios_para_depois_de_falhas_seguidas():
    entes = [dict(cod=str(i), nome=f"C{i}", uf="SP") for i in range(30)]
    pedidos = []
    assert estados.municipios(lambda url: pedidos.append(url), entes, 2025) == {}
    assert len(pedidos) == estados.MAX_FALHAS_SEGUIDAS


def test_municipios_continua_de_onde_parou():
    entes = [dict(cod=c, nome=c, uf="SP") for c in ("1", "2", "3")]
    b = BuscarFalso({("dca", c, "2025", "DCA-Anexo I-C"): RECEITA for c in ("1", "2", "3")})
    cache = CacheMem()
    cache.set(("dca", estados.VERSAO_DCA, "1", "DCA-Anexo I-C", 2025), estados.receitas_uniao(RECEITA))  # lido antes
    assert set(estados.municipios(b, entes, 2025, cache)) == {"1", "2", "3"}
    assert {dict(urllib.parse.parse_qsl(urllib.parse.urlparse(u).query))["id_ente"] for u in b.urls} == {"2", "3"}


def test_municipios_respeita_o_prazo():
    entes = [dict(cod="3550308", nome="São Paulo", uf="SP")]
    b = BuscarFalso({("dca", "3550308", "2025", "DCA-Anexo I-C"): RECEITA})
    assert estados.municipios(b, entes, 2025)["3550308"]["total"] == 830.0
    assert estados.municipios(b, entes, 2025, tempo_max=0) == {}


def test_emendas_cache_so_de_ano_antigo_e_completo():
    api = ApiFalsa({2023: [emenda("FULANA", "SÃO PAULO (UF)", 10)], 2026: [emenda("FULANA", "CAMPINAS - SP", 5)]},
                   falha=[2024])
    cache = CacheMem()
    lista, faltou = estados.emendas(api, [2023, 2024, 2025, 2026], cache, HOJE)
    assert faltou == [2024] and [d["pago"] for d in lista] == [10.0, 5.0]
    assert set(cache.d) == {("emendas", estados.VERSAO_EMENDAS, 2023)}  # 2024 falhou; 2025/2026 ainda recebem pagamentos
    api.pedidos.clear()
    estados.emendas(api, [2023], cache, HOJE)
    assert api.pedidos == []


def test_agregar_e_ligar_autores():
    lista = [estados.enxuta(d) for d in (
        emenda("FULANA DEP", "SÃO PAULO (UF)", 100, resto=20), emenda("FULANA DEP", "CAMPINAS - SP", 50),
        emenda("BANCADA DE SAO PAULO", "CAMPINAS - SP", 30, tipo="Emenda de Bancada"),
        emenda("CICLANO RJ", "CAMPINAS - SP", 10), emenda("EX DEPUTADO", "SANTOS - SP", 5),
        emenda("FULANA DEP", "Nacional", 999), emenda("FULANA DEP", "RIO DE JANEIRO (UF)", 0))]
    sp = estados.agregar(lista)["SP"]
    assert sp["pago"] == 215.0 and sp["estado"] == 120.0 and sp["municipios"]["CAMPINAS"]["n"] == 3
    parl = [dict(nome="Fulana Dep", cargo="DEPUTADO FEDERAL", partido="PX", uf="SP", dossie="pessoa/p0001.html"),
            dict(nome="Ciclano RJ", cargo="SENADOR", partido="PY", uf="RJ", perfil="https://www25.senado.leg.br/x"),
            dict(nome="Sem Emenda", cargo="DEPUTADO FEDERAL", partido="PZ", uf="SP", perfil="https://camara/1")]
    a = {x["nome"]: x for x in estados.ligar_autores(sp["autores"], "SP", parl)}
    assert a["Fulana Dep"]["link"] == "../pessoa/p0001.html" and a["Fulana Dep"]["pago"] == 170.0
    assert a["Bancada De Sao Paulo"]["coletivo"] and a["Bancada De Sao Paulo"]["link"] is None
    assert a["Ciclano RJ"]["uf"] == "RJ"  # autor de outra UF continua identificado
    assert a["Ex Deputado"]["cargo"] == ""
    assert a["Sem Emenda"]["n"] == 0  # parlamentar da UF sem emenda paga no estado tambem aparece


def test_deputados_estaduais_em_exercicio():
    serie = pd.DataFrame([
        dict(chave="cpf:1", nome="MARIA SILVA", nome_urna="MARIA", cargo="DEPUTADO ESTADUAL", uf="SP", partido="PX",
             eleito=True, ano=2022),
        dict(chave="cpf:2", nome="JOAO", nome_urna="", cargo="DEPUTADO ESTADUAL", uf="SP", partido="PY", eleito=False,
             ano=2022),
        dict(chave="cpf:3", nome="ANA", nome_urna="ANA", cargo="DEPUTADO DISTRITAL", uf="DF", partido="PZ", eleito=True,
             ano=2022),
        dict(chave="cpf:4", nome="NOVA", nome_urna="NOVA", cargo="DEPUTADO ESTADUAL", uf="SP", partido="PW", eleito=True,
             ano=2026)])
    out, ano = estados.deputados_estaduais(serie, {"cpf:1": "pessoa/p0009.html"}, lambda r: "https://tse/x", HOJE)
    assert ano == 2022 and set(out) == {"SP", "DF"}
    assert out["SP"] == [dict(nome="Maria", partido="PX", tse="https://tse/x", pagina="../pessoa/p0009.html")]
    assert "cpf" not in json.dumps(out)


def test_ler_reconhecimentos_acha_colunas_pelo_nome():
    df = estados._tabela(S2ID_CSV, "rec.csv")
    rec = estados.ler_reconhecimentos(df)
    assert rec["cod"] == {"3509502": {2025}, "3303906": {2024}}
    assert rec["nome"][("SP", "CAMPINAS")] == {2025} and rec["uf"] == {"SP": {2025}, "RJ": {2024}}
    so_ano = pd.DataFrame(dict(ibge=["3509502"], ano=["2023"]))  # sem UF nem data: UF pelo codigo, ano pela coluna
    assert estados.ler_reconhecimentos(so_ano)["uf"] == {"SP": {2023}}


def test_reconhecimentos_pelo_catalogo_ckan():
    baixados = []
    rec = estados.reconhecimentos(lambda url: CKAN, lambda url: baixados.append(url) or S2ID_CSV)
    assert baixados == ["https://mdr/rec.csv"] and rec["cod"]["3509502"] == {2025}
    assert estados.reconhecimentos(lambda url: None) is None
    assert estados.reconhecimentos(lambda url: CKAN, lambda url: None) is None  # arquivo fora do ar: nada carimba


def test_carimbos_so_emergencial_sem_reconhecimento():
    rec = estados.ler_reconhecimentos(estados._tabela(S2ID_CSV, "rec.csv"))
    civil = dict(subfuncao="Defesa civil")
    lista = [estados.enxuta(dict(emenda("A", "CAMPINAS - SP", 10, ano=2025), **civil)),  # reconhecido no ano
             estados.enxuta(dict(emenda("B", "PETRÓPOLIS - RJ", 10, ano=2025), **civil)),  # reconhecido no ano anterior
             estados.enxuta(dict(emenda("C", "SANTOS - SP", 10, ano=2025), **civil)),  # sem reconhecimento: carimbo
             estados.enxuta(dict(emenda("D", "MINAS GERAIS (UF)", 0, ano=2025, empenhado=50), **civil)),  # carimbo
             estados.enxuta(dict(emenda("E", "SÃO PAULO (UF)", 10, ano=2025), **civil)),  # alguma cidade de SP teve
             estados.enxuta(emenda("F", "SANTOS - SP", 10, ano=2025)),  # nao e emergencial
             estados.enxuta(dict(emenda("G", "Nacional", 10), **civil))]
    cars = estados.carimbos(lista, rec, [dict(cod="3548500", nome="Santos", uf="SP")])
    assert {uf: [d["autor"] for d in l] for uf, l in cars.items()} == {"SP": ["C"], "MG": ["D"]}
    assert estados.carimbos(lista, None) == {}


def test_noticias_so_apoiam_e_respeitam_o_limite():
    cars = {"SP": [dict(municipio="SANTOS", ano=2025), dict(municipio="SANTOS", ano=2024)],
            "MG": [dict(municipio=None, ano=2025)]}
    pedidos = []
    estados.noticias_apoio(cars, lambda url: pedidos.append(url) or "<item></item><item></item>", maximo=2)
    assert [d["noticias"] for d in cars["SP"] + cars["MG"]] == [2, 2, None]
    assert "Minas+Gerais" in cars["MG"][0]["busca"] and len(pedidos) == 2
    assert "after%3A2024-07-01" in pedidos[0]


# ---------------------------------------------------------------- integracao
def _respostas():
    r = {("entes", None, None, None): [dict(cod_ibge=3509502, ente="Campinas", uf="SP", esfera="M", cnpj="00000000000191"),
                                       dict(cod_ibge=35, ente="São Paulo", uf="SP", esfera="E")]}
    r[("dca", "35", "2025", "DCA-Anexo I-E")] = DESPESA
    r[("dca", "35", "2025", "DCA-Anexo I-C")] = RECEITA
    r[("dca", "3509502", "2025", "DCA-Anexo I-C")] = RECEITA
    return r


class BuscarComCkan(BuscarFalso):
    def __call__(self, url):
        return CKAN if "package_show" in url else super().__call__(url)


def test_coletar_e_gerar_ponta_a_ponta(tmp_path):
    api = ApiFalsa({2026: [emenda("FULANA DEP", "CAMPINAS - SP", 50), emenda("FULANA DEP", "SÃO PAULO (UF)", 25),
                           emenda("FULANA DEP", "SANTOS - SP", 7, subfuncao="Defesa civil", ano=2026)]})
    parl = [dict(nome="Fulana Dep", cargo="DEPUTADO FEDERAL", partido="PX", uf="SP", dossie="pessoa/p0001.html")]
    cache = CacheMem()
    pag, extra = estados.coletar(BuscarComCkan(_respostas(), falha=[("dca", "33", "2025", "DCA-Anexo I-E")]), api, parl,
                                 cache=cache, hoje=HOJE, checar=lambda url: "al.sp" in url,
                                 baixar_=lambda url: S2ID_CSV, buscar_txt=lambda url: "")
    assert cache.salvo and len(pag) == 27
    assert extra["SP"]["municipios"][0][:4] == ["Campinas", 50.0, 1, 830.0]
    assert [m[0] for m in extra["SP"]["municipios"] if m[5]] == ["Santos"]
    assert estados.gerar(tmp_path, pag, extra, "2026-10-23 04:00") == 28
    sp = (tmp_path / "estado" / "SP.html").read_text(encoding="utf-8")
    assert "R$ 1,4 mil" in sp and "Saúde" in sp and "Cota-Parte do FPE" in sp
    assert 'href="../pessoa/p0001.html"' in sp and "Assembleia Legislativa de São Paulo" in sp
    assert 'data-json="SP.json"' in sp
    assert sp.count('<span class="txt">Emergência sem reconhecimento oficial</span>') == 1 and "1 sem reconhecimento oficial" in sp
    assert "Santos, 2026" in sp and "nenhuma encontrada" in sp
    assert 'Autor: <a href="../pessoa/p0001.html">Fulana Dep</a>' in sp
    rj = (tmp_path / "estado" / "RJ.html").read_text(encoding="utf-8")
    assert "Fonte não encontrada" in rj  # despesa do RJ falhou e o link da Alerj nao abriu
    assert "envolvido" not in sp.lower()
    tudo = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "estado").iterdir())
    assert "00000000000191" not in tudo and not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", tudo)
    assert json.loads((tmp_path / "estado" / "SP.json").read_text(encoding="utf-8"))["siconfi_municipios"] is True
    idx = (tmp_path / "estado" / "index.html").read_text(encoding="utf-8")
    assert idx.count('class="card uf"') == 27


def test_sem_chave_do_portal_emendas_saem_fonte_nao_encontrada(tmp_path):
    pag, extra = estados.coletar(BuscarFalso(_respostas()), None, [], hoje=HOJE, baixar_=lambda url: None)
    estados.gerar(tmp_path, pag, extra, "agora")
    sp = (tmp_path / "estado" / "SP.html").read_text(encoding="utf-8")
    assert sp.count("Fonte não encontrada") >= 3 and "R$ 1,4 mil" in sp
    assert 'class="carimbo' not in sp  # sem emendas nem S2iD, nada e carimbado


def test_demo_gera_todas_as_ufs(tmp_path):
    pag, extra = estados.demo()
    assert estados.gerar(tmp_path, pag, extra, "demo") == 28
    assert all(extra[uf]["municipios"] and extra[uf]["estaduais"] for uf in estados.UFS)
    ac = (tmp_path / "estado" / "AC.html").read_text(encoding="utf-8")
    assert "Fonte não encontrada" in ac and '<span class="txt">Emergência sem reconhecimento oficial</span>' in ac


def test_pipeline_demo_publica_os_estados(tmp_path, monkeypatch):
    from test_fase0 import rodar
    rodar(tmp_path, monkeypatch, ID_SEGREDO="teste")
    pasta = tmp_path / "docs" / "estado"
    assert len(list(pasta.glob("*.html"))) == 28 and len(list(pasta.glob("*.json"))) == 27
    assert "Parlamentares autores de emendas" in (pasta / "MG.html").read_text(encoding="utf-8")
