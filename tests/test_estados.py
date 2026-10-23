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


def emenda(autor, local, pago, tipo="Emenda Individual - Transferências Especiais", resto=0):
    return dict(nomeAutor=autor, tipoEmenda=tipo, localidadeDoGasto=local, funcao="Saúde",
                valorPago=f"{pago:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."), valorRestoPago=resto)


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
    assert estados.dca(b, "35", "DCA-Anexo I-E", 2025, cache) == (2024, DESPESA)
    n = len(b.urls)
    assert estados.dca(b, "35", "DCA-Anexo I-E", 2025, cache) == (2024, DESPESA)
    assert len(b.urls) == n + 1  # 2025 vazio continua sendo perguntado; 2024 veio do cache
    assert estados.dca(BuscarFalso({}, falha=[("dca", "35", "2025", "DCA-Anexo I-E")]), "35", "DCA-Anexo I-E", 2025) \
        == (None, None)


def test_financas_marca_falha_por_secao():
    b = BuscarFalso({("dca", "35", "2025", "DCA-Anexo I-C"): RECEITA}, falha=[("dca", "35", "2025", "DCA-Anexo I-E")])
    f = estados.financas(b, "35", 2025)
    assert f["despesa"] == "falha" and f["ano_receita"] == 2025 and len(f["receita"]) == 3


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
    assert set(cache.d) == {("emendas", 2023)}  # 2024 falhou; 2025/2026 ainda recebem pagamentos
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


# ---------------------------------------------------------------- integracao
def _respostas():
    r = {("entes", None, None, None): [dict(cod_ibge=3509502, ente="Campinas", uf="SP", esfera="M", cnpj="00000000000191"),
                                       dict(cod_ibge=35, ente="São Paulo", uf="SP", esfera="E")]}
    r[("dca", "35", "2025", "DCA-Anexo I-E")] = DESPESA
    r[("dca", "35", "2025", "DCA-Anexo I-C")] = RECEITA
    r[("dca", "3509502", "2025", "DCA-Anexo I-C")] = RECEITA
    return r


def test_coletar_e_gerar_ponta_a_ponta(tmp_path):
    api = ApiFalsa({2026: [emenda("FULANA DEP", "CAMPINAS - SP", 50), emenda("FULANA DEP", "SÃO PAULO (UF)", 25)]})
    parl = [dict(nome="Fulana Dep", cargo="DEPUTADO FEDERAL", partido="PX", uf="SP", dossie="pessoa/p0001.html")]
    cache = CacheMem()
    pag, extra = estados.coletar(BuscarFalso(_respostas(), falha=[("dca", "33", "2025", "DCA-Anexo I-E")]), api, parl,
                                 cache=cache, hoje=HOJE, checar=lambda url: "al.sp" in url)
    assert cache.salvo and len(pag) == 27
    assert extra["SP"]["municipios"][0][:4] == ["Campinas", 50.0, 1, 830.0]
    assert estados.gerar(tmp_path, pag, extra, "2026-10-23 04:00") == 28
    sp = (tmp_path / "estado" / "SP.html").read_text(encoding="utf-8")
    assert "R$ 1,4 mil" in sp and "Saúde" in sp and "Cota-Parte do FPE" in sp
    assert 'href="../pessoa/p0001.html"' in sp and "Assembleia Legislativa de São Paulo" in sp
    assert 'data-json="SP.json"' in sp
    rj = (tmp_path / "estado" / "RJ.html").read_text(encoding="utf-8")
    assert "Fonte não encontrada" in rj  # despesa do RJ falhou e o link da Alerj nao abriu
    assert "envolvido" not in sp.lower()
    tudo = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "estado").iterdir())
    assert "00000000000191" not in tudo and not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", tudo)
    assert json.loads((tmp_path / "estado" / "SP.json").read_text(encoding="utf-8"))["siconfi_municipios"] is True
    idx = (tmp_path / "estado" / "index.html").read_text(encoding="utf-8")
    assert idx.count('class="card uf"') == 27


def test_sem_chave_do_portal_emendas_saem_fonte_nao_encontrada(tmp_path):
    pag, extra = estados.coletar(BuscarFalso(_respostas()), None, [], hoje=HOJE)
    estados.gerar(tmp_path, pag, extra, "agora")
    sp = (tmp_path / "estado" / "SP.html").read_text(encoding="utf-8")
    assert sp.count("Fonte não encontrada") >= 2 and "R$ 1,4 mil" in sp


def test_demo_gera_todas_as_ufs(tmp_path):
    pag, extra = estados.demo()
    assert estados.gerar(tmp_path, pag, extra, "demo") == 28
    assert all(extra[uf]["municipios"] and extra[uf]["estaduais"] for uf in estados.UFS)
    assert "Fonte não encontrada" in (tmp_path / "estado" / "AC.html").read_text(encoding="utf-8")


def test_pipeline_demo_publica_os_estados(tmp_path, monkeypatch):
    from test_fase0 import rodar
    rodar(tmp_path, monkeypatch, ID_SEGREDO="teste")
    pasta = tmp_path / "docs" / "estado"
    assert len(list(pasta.glob("*.html"))) == 28 and len(list(pasta.glob("*.json"))) == 27
    assert "Parlamentares autores de emendas" in (pasta / "MG.html").read_text(encoding="utf-8")
