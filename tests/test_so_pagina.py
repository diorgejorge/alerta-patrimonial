"""Pagina propria para parlamentares em exercicio fora dos destaques (so_pagina): ganham pagina, nao viram card."""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import paginas, pipeline  # noqa: E402


def pares():
    return pd.DataFrame([dict(chave="cpf:1", nome="ANA", ano_ini=2014, ano_fim=2018, nivel="forte", cresc=1.0),
                         dict(chave="cpf:1", nome="ANA", ano_ini=2018, ano_fim=2022, nivel=None, cresc=2.0),
                         dict(chave="cpf:2", nome="BIA", ano_ini=2018, ano_fim=2022, nivel=None, cresc=3.0)])


def test_so_paginas_pega_o_periodo_mais_recente_de_cada_um():
    x = pipeline.so_paginas(pares(), {"cpf:1"}, pid={"cpf:1": "p0007"}.get)
    assert len(x) == 1 and x.iloc[0].ano_fim == 2022 and x.iloc[0].pessoa == "p0007"
    assert x.iloc[0].so_pagina and not x.iloc[0].novo and x.iloc[0].id == "p0007|2018-2022"


def test_so_paginas_sem_ninguem():
    assert pipeline.so_paginas(pares(), set()).empty


def test_extra_ganha_pagina_mas_nao_card(tmp_path, monkeypatch):
    monkeypatch.setattr(paginas, "pagina", lambda *a, **k: "<html></html>")
    monkeypatch.setattr(paginas, "cartao", lambda pid, linhas, h: f"<li>{pid}</li>")
    alertas = [dict(pessoa="p0001", nivel="forte", cresc=1.0), dict(pessoa="p0002", nivel="forte", cresc=1.0, so_pagina=True)]
    pessoas = {"a": dict(idx=[0], chave="cpf:1"), "b": dict(idx=[1], chave="cpf:2")}
    cartoes, graf = paginas.gerar(alertas, pessoas, {}, {}, tmp_path, gerado="hoje")
    assert (tmp_path / "pessoa" / "p0002.html").exists() and alertas[1]["pagina"] == "pessoa/p0002.html"
    assert "p0001" in cartoes and "p0002" not in cartoes


def test_link_do_raio_x():
    assert pipeline.pagina_ou_dossie(dict(dossie="dossie/ana-sp.html", pessoa="p0001")) == "dossie/ana-sp.html"
    assert pipeline.pagina_ou_dossie(dict(pessoa="p0002", so_pagina=True)) == "pessoa/p0002.html"
    assert pipeline.pagina_ou_dossie(dict(pessoa=None)) is None


def test_em_mandato_estadual_so_cargos_do_estado_com_mandato():
    import datetime as dt
    serie = pd.DataFrame([
        dict(chave="cpf:1", cargo="GOVERNADOR", eleito=True, ano=2022),
        dict(chave="cpf:2", cargo="DEPUTADO ESTADUAL", eleito=True, ano=2022),
        dict(chave="cpf:3", cargo="DEPUTADO ESTADUAL", eleito=False, ano=2022),
        dict(chave="cpf:4", cargo="DEPUTADO ESTADUAL", eleito=True, ano=2018),
        dict(chave="cpf:5", cargo="VEREADOR", eleito=True, ano=2024),
        dict(chave="cpf:6", cargo="DEPUTADO DISTRITAL", eleito=True, ano=2022)])
    assert pipeline.em_mandato_estadual(serie, dt.date(2026, 10, 24)) == {"cpf:1", "cpf:2", "cpf:6"}


def serie_unica():
    base = dict(cargo="1º SUPLENTE", partido="X", eleito=False, sq_candidato="", sg_ue="", suplementar=False,
                empresas=[], empresas_cnpj=["12345678000199"])
    return pd.DataFrame([dict(base, chave="cpf:9", nome="CARLA DIAS", nome_urna="CARLA", uf="SP", ano=2018, patrimonio=10.0),
                         dict(base, chave="cpf:9", nome="CARLA DIAS", nome_urna="CARLA", uf="SP", ano=2022, patrimonio=50.0),
                         dict(base, chave="cpf:8", nome="DORA", nome_urna="DORA", uf="RJ", ano=2022, patrimonio=5.0)])


def test_declaracao_unica_mostra_so_o_patrimonio_declarado():
    x = pipeline.declaracao_unica(serie_unica(), {"cpf:8"}, pid={"cpf:8": "p0009"}.get)
    r = x.iloc[0]
    assert len(x) == 1 and r.pat_fim == 5.0 and r.pat_ini is None and r.cresc is None and r.nivel is None
    assert r.unica and r.so_pagina and r.id == "p0009|2022" and r.ano_ini == r.ano_fim == 2022


def test_declaracao_unica_sem_ninguem():
    assert pipeline.declaracao_unica(serie_unica(), set()).empty


def test_ligar_ao_tse_pelo_nome_e_uf_so_quando_unico():
    parl = [dict(_chave="", _nomes={"CARLA DIAS"}, uf="SP"), dict(_chave="", _nomes={"DORA"}, uf="SP"),
            dict(_chave="cpf:1", _nomes={"DORA"}, uf="RJ")]
    pipeline.ligar_ao_tse(parl, serie_unica())
    assert [p["_chave"] for p in parl] == ["cpf:9", "", "cpf:1"]


def test_resumo_da_declaracao_unica_sem_percentual_nem_faixa():
    a = dict(unica=True, so_pagina=True, pat_fim=1500000.0, ano_fim=2022, cargo="SENADOR",
             link_tse="https://divulgacandcontas.tse.jus.br/x")
    html = paginas._resumo([a])
    assert "R$ 1.500.000" in html and "2022" in html and paginas.UNICA in html and "divulgacandcontas" in html
    assert "%" not in html and "Faixa" not in html


def test_painel_leva_so_os_campos_do_card():
    # #73: campos so das paginas e valores vazios nao vao para o index.html
    a = dict(nome="A", cresc=1.0, link_tse_ini="https://tse", monitorado=True, unica=False,
             partido=None, eleito_atual=None)
    assert pipeline.so_campos_do_card(a) == dict(nome="A", cresc=1.0, eleito_atual=None)
