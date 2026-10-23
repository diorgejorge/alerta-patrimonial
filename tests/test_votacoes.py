"""Como votou (#56): leitura dos votos da Camara (CSV anual) e do Senado (API), com dados sinteticos, sem rede."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import votacoes  # noqa: E402

VOTOS = ('"idVotacao";"uriVotacao";"dataHoraVoto";"voto";"deputado_id";"deputado_nome"\n'
         '"10-1";"u";"t";"Sim";"100";"A"\n"10-1";"u";"t";"Não";"200";"B"\n"10-1";"u";"t";"Artigo 17";"300";"C"\n'
         '"10-1";"u";"t";"Abstenção";"400";"D"\n"99-9";"u";"t";"Sim";"100";"A"\n')
ITENS = [dict(id="tema-a", tema="Tema A", casa="camara", votacao="10-1", data="2025-03-10", explicacao="Explica A.",
              sim="Sim = a favor."),
         dict(id="tema-a", tema="Tema A", casa="senado", votacao="555", data="2025-04-02", explicacao="Explica A.",
              sim="Sim = a favor.")]
SENADO = [dict(codigoSessaoVotacao=555, codigoMateria=123, votos=[
    dict(codigoParlamentar=5012, siglaVotoParlamentar="Não"),
    dict(codigoParlamentar=6000, siglaVotoParlamentar="MIS", descricaoVotoParlamentar="Missão da Casa no País/exterior"),
    dict(codigoParlamentar=7000, siglaVotoParlamentar="NCom", descricaoVotoParlamentar="Não compareceu")]),
    dict(codigoSessaoVotacao=556, votos=[dict(codigoParlamentar=5012, siglaVotoParlamentar="Sim")])]


def parl():
    return [dict(casa="camara", _id=i) for i in ("100", "200", "300", "500", "600")] + \
           [dict(casa="senado", _id=c) for c in ("5012", "6000", "7000", "8000")]


def test_ler_votos_camara_filtra_as_votacoes_pedidas():
    d = votacoes.ler_votos_camara(("﻿" + VOTOS).encode(), {"10-1"})
    assert set(d) == {"10-1"}
    assert d["10-1"] == {"100": "Sim", "200": "Não", "300": "Presidiu a sessão", "400": "Abstenção"}


def test_voto_senado_separa_ausencia_justificada():
    assert votacoes.voto_senado("Sim") == ("Sim", None)
    assert votacoes.voto_senado("P-NRV") == ("Presente, sem votar", None)
    assert votacoes.voto_senado("NCom", "Não compareceu") == ("Não votou", None)
    assert votacoes.voto_senado("LS", "Licença saúde") == ("Não votou", "Licença saúde")
    assert votacoes.voto_senado("XYZ", "Presente – outro") == ("Presente, sem votar", None)


def test_carregar_config_real_e_valida():
    itens = votacoes.carregar()
    assert len(itens) >= 10 and all(v["explicacao"] and v["sim"].startswith("Sim =") for v in itens)
    assert all(len(v["data"]) == 10 and v["casa"] in ("camara", "senado") for v in itens)
    assert len({(v["casa"], v["votacao"]) for v in itens}) == len(itens)  # sem votacao repetida


def test_anotar_integra_camara_e_senado_sem_rede(tmp_path):
    baixados, buscas = [], []
    camara = votacoes.votos_camara([ITENS[0]], None, baixar=lambda url: baixados.append(url) or VOTOS.encode())
    senado = votacoes.votos_senado([ITENS[1]], lambda url: buscas.append(url) or SENADO, None)
    assert baixados == [votacoes.CAMARA_VOTOS.format(ano=2025)] and "2025-04-02" in buscas[0]
    ps = parl()
    fora = lambda dep, data: dep != "600"  # o 600 nao estava no mandato no dia
    ctx = votacoes.anotar(ps, ITENS, camara=camara, senado=senado, ativo=fora)
    por = {p["_id"]: p["votos"] for p in ps}
    assert por["100"][0]["voto"] == "Sim" and "idProposicao=10" in por["100"][0]["link"]
    assert por["500"][0]["voto"] == "Não votou" and por["600"] == []
    assert por["5012"][0]["voto"] == "Não" and por["5012"][0]["link"].endswith("/materia/123")
    assert por["6000"][0]["motivo"].startswith("Missão") and por["8000"] == []  # 8000 nao estava na sessao
    assert ctx["placar"]["10-1"].startswith("Sim 1 × Não 1") and ctx["fontes"] == {"camara": True, "senado": True}
    html = votacoes.secao(por["100"], "DEPUTADO FEDERAL", ctx, ITENS)
    assert "Votou em <b>1</b> de <b>1</b>" in html and "Explica A." in html and "Placar na casa" in html
    assert '<span class="voto sim">Sim</span>' in html and "<details>" in html


def test_secao_sem_dado():
    assert "Não informado" in votacoes.secao(None, "GOVERNADOR", {}, ITENS)
    assert "Fonte não encontrada" in votacoes.secao(None, "SENADOR", {"fontes": {"camara": True, "senado": False}}, ITENS)
    assert "não estava no mandato" in votacoes.secao([], "SENADOR", {}, ITENS)


def test_secao_escapa_texto_externo():
    v = [dict(id="tema-a", tema="<b>x</b>", voto="Sim", data="2025-03-10", link="https://x/?a=1&b=2", motivo="<i>")]
    html = votacoes.secao(v, "DEPUTADO FEDERAL", {}, ITENS)
    assert "<b>x</b>" not in html and "&lt;i&gt;" in html and "a=1&amp;b=2" in html


def test_demo_so_para_parlamentar():
    assert votacoes.demo("GOVERNADOR") == {}
    d = votacoes.demo("SENADOR")
    assert d["casa"] == "senado" and d["votos"] and d["presenca"]["justificadas"] is not None
    json.dumps(d)  # vai para o JSON do painel


def test_texto_cobranca_cita_a_fonte_oficial():
    x = dict(id="a", tema="Tema A", voto="Sim", data="2025-03-10", link="https://www.camara.leg.br/x")
    t = votacoes.texto_cobranca("Fulano", x)
    assert t.startswith("Prezado(a) Fulano,") and "site da Câmara dos Deputados (https://www.camara.leg.br/x)" in t
    assert 'votou "Sim" em "Tema A", em 10/03/2025' in t and "por que votou assim" in t and "[seu nome]" in t
    t2 = votacoes.texto_cobranca("", dict(x, voto="Não votou", link="https://www25.senado.leg.br/y"))
    assert "Prezado(a) parlamentar" in t2 and "do Senado Federal" in t2 and "não votou" in t2 and "o motivo" in t2
    html = votacoes.secao([x], "DEPUTADO FEDERAL", {}, ITENS, nome="Fulano")
    assert 'data-cobrar-voto="Prezado(a) Fulano' in html and "Cobrar sobre este voto" in html
