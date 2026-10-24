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
    assert a["Ciclano RJ"]["link"] is None and a["Ciclano RJ"]["perfil"]  # sem dossie: nome sem link


def test_autor_liga_ao_dossie_e_mostra_carimbos():
    com = dict(nome="Fulana", cargo="SENADOR", partido="PX", uf="SP", n=1, pago=10.0, empenhado=10.0, coletivo=False,
               link="../pessoa/p0001.html", perfil="https://senado/1", marcas=("eleito", "selo"))
    html = estados._autor(com)
    assert '<a href="../pessoa/p0001.html">Fulana</a>' in html and "perfil oficial" not in html
    assert "selo-cera verde p" in html and "selo-cera caramelo p" in html and "Mão na massa" in html
    assert "Exemplar" not in html  # carimbo sem dado fica escondido
    sem = estados._autor(dict(com, link=None, marcas=()))
    assert "<a href=\"https://senado/1\"" in sem and "perfil oficial" in sem and "selo-cera" not in sem
    assert sem.startswith('<li><span class="rot">Fulana<small>')  # nome puro, sem link
    assert 'class="rot"' not in html.split("<small>")[0].split("</a>", 1)[1]  # so o selo: sem texto ao lado
    assert '<span class="sr">Eleito</span>' in html  # o significado continua para leitor de tela


def test_legenda_so_com_os_selos_que_aparecem():
    autores = [dict(marcas=("eleito:2022",), paradas=0), dict(marcas=(), paradas=2)]
    leg = estados.legenda_autores(autores)
    assert "legenda-selos" in leg and "<b>Eleito</b>" in leg and "<b>Emendas paradas</b>" in leg
    assert "Exemplar" not in leg and "Mão na massa" not in leg
    assert estados.legenda_autores([dict(marcas=(), paradas=0)]) == ""


def test_base_leva_pagina_e_carimbos():
    parl = [dict(nome="Fulana", cargo="SENADOR", partido="PX", uf="SP", perfil=None, _chave="cpf:1", exemplar=True),
            dict(nome="Beltrano", cargo="SENADOR", partido="PX", uf="SP", perfil=None, _chave="cpf:2", selo=True)]
    b = estados.base(parl, None, {"cpf:1": "pessoa/p0009.html"}, None, HOJE, eleitos={"cpf:2": 2022})["parlamentares"]
    assert b[0]["pagina"] == "pessoa/p0009.html" and b[0]["exemplar"] and not b[0]["eleito"]
    assert b[1]["pagina"] is None and b[1]["selo"] and b[1]["eleito"]
    assert estados.marcas_de(b[0]) == ("exemplar",) and estados.marcas_de(b[1]) == ("eleito:2022", "selo")
    assert "Eleito em 2022" in estados.carimbos(estados.marcas_de(b[1]))


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


def test_paradas_e_execucao():
    lista = [estados.enxuta(emenda("A", "SANTOS - SP", 0, ano=2023, empenhado=100)),  # parada
             estados.enxuta(emenda("B", "SANTOS - SP", 0, ano=2025, empenhado=100)),  # recente: ainda nao
             estados.enxuta(emenda("C", "SANTOS - SP", 5, ano=2023, empenhado=100)),  # teve pagamento
             estados.enxuta(emenda("D", "SÃO PAULO (UF)", 0, ano=2024, empenhado=300))]  # parada (2 anos)
    assert [d["autor"] for d in estados.paradas(lista, HOJE)["SP"]] == ["D", "A"]
    assert estados.execucao(50, 200) == 25 and estados.execucao(300, 200) == 100 and estados.execucao(5, 0) is None
    sp = estados.agregar(lista)["SP"]
    assert sp["empenhado"] == 600 and sp["pago"] == 5 and sp["n"] == 1 and sp["autores"]["A"] == [0.0, 0, 100.0]


# ---------------------------------------------------------------- integracao
def _respostas():
    r = {("entes", None, None, None): [dict(cod_ibge=3509502, ente="Campinas", uf="SP", esfera="M", cnpj="00000000000191"),
                                       dict(cod_ibge=35, ente="São Paulo", uf="SP", esfera="E")]}
    r[("dca", "35", "2025", "DCA-Anexo I-E")] = DESPESA
    r[("dca", "35", "2025", "DCA-Anexo I-C")] = RECEITA
    r[("dca", "3509502", "2025", "DCA-Anexo I-C")] = RECEITA
    return r


def test_coletar_e_gerar_ponta_a_ponta(tmp_path):
    api = ApiFalsa({2026: [emenda("FULANA DEP", "CAMPINAS - SP", 50), emenda("FULANA DEP", "SÃO PAULO (UF)", 25),
                           emenda("FULANA DEP", "SANTOS - SP", 7, ano=2026, empenhado=100)],
                    2024: [emenda("FULANA DEP", "SANTOS - SP", 0, ano=2024, empenhado=40)]})
    parl = [dict(nome="Fulana Dep", cargo="DEPUTADO FEDERAL", partido="PX", uf="SP", dossie="pessoa/p0001.html")]
    cache = CacheMem()
    pag, extra = estados.coletar(BuscarFalso(_respostas(), falha=[("dca", "33", "2025", "DCA-Anexo I-E")]), api, parl,
                                 cache=cache, hoje=HOJE, checar=lambda url: "al.sp" in url)
    assert cache.salvo and len(pag) == 27
    assert extra["SP"]["municipios"][0][:4] == ["Campinas", 50.0, 1, 830.0]
    assert [m[0] for m in extra["SP"]["municipios"] if m[5]] == ["Santos"]  # emenda parada
    assert estados.gerar(tmp_path, pag, extra, "2026-10-23 04:00") == 28
    sp = (tmp_path / "estado" / "SP.html").read_text(encoding="utf-8")
    assert "R$ 1,4 mil" in sp and "Saúde" in sp and "Cota-Parte do FPE" in sp
    assert "Período dos dados:</b> emendas de 2023 a 2026 (até 23/10/2026); balanço do estado de 2025" in sp
    assert 'href="../pessoa/p0001.html"' in sp and "Assembleia Legislativa de São Paulo" in sp
    assert 'data-json="SP.json"' in sp
    assert "Emergência" not in sp and "S2iD" not in sp
    assert "Santos · R$ 40 reservados em 2024, nada pago" in sp and "1 emenda parada" in sp
    assert "59% do prometido já pago" in sp and "<b>59%</b> já " in sp  # 82 pagos de 140 empenhados
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
    pag, extra = estados.coletar(BuscarFalso(_respostas()), None, [], hoje=HOJE)
    estados.gerar(tmp_path, pag, extra, "agora")
    sp = (tmp_path / "estado" / "SP.html").read_text(encoding="utf-8")
    assert sp.count("Fonte não encontrada") >= 3 and "R$ 1,4 mil" in sp
    assert 'class="selo-cera' not in sp  # sem emendas, nada e carimbado


def test_demo_gera_todas_as_ufs(tmp_path):
    pag, extra = estados.demo()
    assert estados.gerar(tmp_path, pag, extra, "demo") == 28
    assert all(extra[uf]["municipios"] and extra[uf]["estaduais"] for uf in estados.UFS)
    ac = (tmp_path / "estado" / "AC.html").read_text(encoding="utf-8")
    assert "Emenda parada" in ac and "Fonte não encontrada" in ac
    for nome in ("AC.html", "index.html"):
        html = (tmp_path / "estado" / nome).read_text(encoding="utf-8")
        assert 'class="vidro"' in html and 'class="topo-site"' in html and 'class="marca-link"' in html


def test_pipeline_demo_publica_os_estados(tmp_path, monkeypatch):
    from test_fase0 import rodar
    rodar(tmp_path, monkeypatch, ID_SEGREDO="teste")
    pasta = tmp_path / "docs" / "estado"
    assert len(list(pasta.glob("*.html"))) == 28 and len(list(pasta.glob("*.json"))) == 27
    assert "Quem mandou emendas para Minas Gerais" in (pasta / "MG.html").read_text(encoding="utf-8")


def test_base_do_pipeline_sem_cpf():
    parl = [dict(nome="Fulana", cargo="SENADOR", partido="PX", uf="SP", perfil="https://senado/1", dossie=None,
                 _cpf="12345678901", _chave="cpf:12345678901", _nomes={"FULANA", "FULANA DE TAL"})]
    serie = pd.DataFrame([dict(chave="cpf:12345678901", nome="ANA", nome_urna="ANA", cargo="DEPUTADO ESTADUAL",
                               uf="SP", partido="PZ", eleito=True, ano=2022)])
    b = estados.base(parl, serie, {}, None, HOJE)
    texto = json.dumps(b, ensure_ascii=False)
    assert "12345678901" not in texto and b["eleicao_estadual"] == 2022
    assert b["parlamentares"][0]["_nomes"] == ["FULANA", "FULANA DE TAL"] and b["estaduais"]["SP"][0]["nome"] == "Ana"


def test_main_do_workflow_le_a_base_e_grava_as_paginas(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    base = estados.base([dict(nome="Fulana Dep", cargo="DEPUTADO FEDERAL", partido="PX", uf="SP",
                              dossie="pessoa/p0001.html")])
    (tmp_path / "data" / "estados_base.json").write_text(json.dumps(base), encoding="utf-8")
    monkeypatch.delenv("ID_SEGREDO", raising=False)
    monkeypatch.setattr(estados, "Buscador", lambda: BuscarFalso(_respostas()))
    monkeypatch.setattr(estados, "cliente_portal", lambda chave: ApiFalsa({2026: [emenda("FULANA DEP", "CAMPINAS - SP", 9)]}))
    monkeypatch.setattr(estados, "abre", lambda url: True)
    resumo = tmp_path / "resumo.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(resumo))
    estados.main(tmp_path)
    tabela = resumo.read_text(encoding="utf-8")
    assert "| Estados no SICONFI |" in tabela and "| **Total** |" in tabela and "páginas geradas" in tabela
    sp = (tmp_path / "docs" / "estado" / "SP.html").read_text(encoding="utf-8")
    assert 'href="../pessoa/p0001.html">Fulana Dep' in sp and "Período dos dados:" in sp
    assert "Período dos dados:" in (tmp_path / "docs" / "estado" / "index.html").read_text(encoding="utf-8")


def test_main_sem_base_avisa(tmp_path):
    with pytest.raises(SystemExit):
        estados.main(tmp_path)


class Relogio:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_andamento_mostra_contagem_percentual_e_estimativa(tmp_path):
    rel, linhas = Relogio(), []
    prog = estados.Andamento(intervalo=30, relogio=rel, saida=lambda txt, **k: linhas.append(txt))
    prog.etapa("Municípios no SICONFI")
    assert linhas[-1].startswith("[3/4] Municípios no SICONFI")
    rel.t = 60
    prog.passo(1000, 4000, "Campinas (SP)")
    assert "1.000/4.000 · 25%" in linhas[-1] and "1min 00s" in linhas[-1] and "faltam ~3min 00s" in linhas[-1]
    rel.t = 70
    prog.passo(1100, 4000)  # menos de 30 s depois: nao repete a linha
    assert "1.000/4.000" in linhas[-1]
    prog.passo(4000, 4000)  # o ultimo sempre aparece
    assert "100%" in linhas[-1] and "faltam" not in linhas[-1]
    prog.fim("3.900/4.000 com verbas")
    rel.t = 3725
    arq = tmp_path / "resumo.md"
    prog.resumo(arq)
    assert "concluído em 1h 02min" in linhas[-1]
    assert "| Municípios no SICONFI | 1h 02min | 3.900/4.000 com verbas |" in arq.read_text(encoding="utf-8")


def test_andamento_das_emendas_por_pagina():
    linhas = []
    prog = estados.Andamento(intervalo=0, saida=lambda txt, **k: linhas.append(txt))

    class Api(ApiFalsa):
        def paginas(self, caminho, max_paginas=20, ao_ler=None, **params):
            ao_ler(1, 100)
            return super().paginas(caminho, max_paginas, **params)

    prog.etapa("Emendas no Portal")
    estados.emendas(Api({2026: [emenda("A", "CAMPINAS - SP", 1)]}), [2026], None, dt.date(2026, 10, 23), prog)
    assert any("ano 2026, página 1 · 100" in l for l in linhas) and any("ano 2026: 1 emendas" in l for l in linhas)


def test_receitas_com_rotulo_limpo_e_linhas_iguais_somadas():
    itens = [dict(coluna="Receitas Brutas Realizadas", conta=f"1.7.1.{c}.0.0 - {r}", valor=v) for c, r, v in (
        ("5.11", "Transferências do SUS \u00bf Bloco de Manutenção", 300),
        ("9.21", "Outras Transferências de Convênios da União", 20),
        ("9.22", "Outras Transferências de Convênios da União", 30))]
    r = estados.receitas_uniao(itens)
    assert ("Transferências do SUS – Bloco de Manutenção", 300.0, "legais") in r
    assert [x for x in r if x[0].startswith("Outras")] == [("Outras Transferências de Convênios da União", 50.0, "voluntarias")]


def test_texto_para_leigo():
    assert estados._pct(1, 1000) == "menos de 1%" and estados._pct(300, 1000) == "30%"
    html = estados.secao_despesa(dict(ano_despesa=2025, despesa=[("Encargos Especiais", 800.0), ("Saúde", 200.0)]))
    assert "Dívidas, juros e repasses<small>Encargos Especiais</small>" in html and "Em 2025, o estado gastou" in html
    pag, extra = estados.demo()
    sp = estados.pagina_uf(pag["SP"])
    assert "Individual, tipo Pix (sem destino definido)<small>Emenda Individual - Transferências Especiais</small>" in sp
    assert 'href="../index.html#meus=SP">Ver meus representantes' in sp and "do prometido já pago" in sp


def test_exemplar_e_mao_na_massa_primeiro_no_estado():
    base = dict(cargo="DEPUTADO FEDERAL", partido="PX", uf="SP", n=1, empenhado=1.0, coletivo=False, link=None, perfil=None)
    autores = [dict(base, nome="Rica", pago=900.0, marcas=("eleito:2022",)),
               dict(base, nome="Massa", pago=500.0, marcas=("selo",)),
               dict(base, nome="Media", pago=400.0, marcas=()),
               dict(base, nome="Exemplo", pago=100.0, marcas=("exemplar",)),
               dict(base, nome="Ambos", pago=50.0, marcas=("eleito:2022", "exemplar", "selo"))]
    html = estados.secao_autores(autores, "SP", falhou=False)
    ordem = [html.index(f"{n}<") for n in ("Ambos", "Exemplo", "Massa", "Rica", "Media")]
    assert ordem == sorted(ordem)  # o resto continua pelo valor pago


def test_eleito_um_carimbo_por_eleicao_com_o_ano_dentro():
    assert estados.ano_eleito({"cpf:1": 2022}, "cpf:1", {"cpf:1": [2022, 2018]}) == [2018, 2022]
    assert estados.ano_eleito({"cpf:1": 2022}, "cpf:1") == [2022] and estados.ano_eleito({}, "cpf:1") is False
    marcas = estados.marcas_de(dict(eleito=[2018, 2022], selo=True))
    assert marcas == ("eleito:2018", "eleito:2022", "selo")
    html = estados.carimbos(marcas)
    assert html.count("selo-cera verde p com-ano") == 2 and '<b class="ano">2018</b>' in html and "Eleito em 2022" in html
