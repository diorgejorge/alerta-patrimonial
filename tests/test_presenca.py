"""Presenca (#58): plenario e comissoes da Camara (arquivos anuais) e votacoes nominais do Senado, sem rede."""
import datetime as dt, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import presenca  # noqa: E402

HOJE = dt.date(2025, 6, 30)
INI = dt.date(2023, 2, 1).toordinal()
EVENTOS = ('"id";"uri";"dataHoraInicio";"situacao";"descricaoTipo"\n'
           '"1";"u";"2025-03-04T14:00:00";"Encerrada";"Sessão Deliberativa"\n'
           '"2";"u";"2025-03-05T14:00:00";"Encerrada";"Sessão Deliberativa"\n'
           '"3";"u";"2025-03-06T14:00:00";"Cancelada";"Sessão Deliberativa"\n'
           '"4";"u";"2025-03-06T10:00:00";"Encerrada (Final)";"Reunião Deliberativa"\n'
           '"5";"u";"2025-03-07T10:00:00";"Encerrada (Final)";"Audiência Pública"\n'
           '"6";"u";"2025-06-10T14:00:00";"Encerrada";"Sessão Deliberativa"\n'
           '"7";"u";"2022-12-10T14:00:00";"Encerrada";"Sessão Deliberativa"\n')
ORGAOS = ('"idEvento";"uriEvento";"idOrgao";"uriOrgao";"siglaOrgao"\n'
          '"1";"u";"180";"u";"PLEN"\n"2";"u";"180";"u";"PLEN"\n"3";"u";"180";"u";"PLEN"\n'
          '"4";"u";"2003";"u";"CCJC"\n"5";"u";"2003";"u";"CCJC"\n"6";"u";"180";"u";"PLEN"\n"7";"u";"180";"u";"PLEN"\n')
PRES = ('"idEvento";"uriEvento";"dataHoraInicio";"idDeputado";"uriDeputado"\n'
        '"1";"u";"2025-03-04T14:00:00";"100";"u"\n"2";"u";"2025-03-05T14:00:00";"100";"u"\n'
        '"4";"u";"2025-03-06T10:00:00";"100";"u"\n"1";"u";"2025-03-04T14:00:00";"200";"u"\n'
        '"6";"u";"2025-06-10T14:00:00";"300";"u"\n')
MEMBROS = ('"uriOrgao";"siglaOrgao";"nomeOrgao";"nomePublicacaoOrgao";"uriDeputado";"nomeDeputado";"siglaPartido";'
           '"siglaUF";"cargo";"dataInicio";"dataFim"\n'
           '"x/orgaos/2003";"CCJC";"n";"n";"x/deputados/100";"A";"P";"SP";"Titular";"2025-03-01";""\n'
           '"x/orgaos/2003";"CCJC";"n";"n";"x/deputados/200";"B";"P";"RJ";"Titular";"2025-03-01";""\n'
           '"x/orgaos/2003";"CCJC";"n";"n";"x/deputados/300";"C";"P";"BA";"Suplente";"2025-03-01";""\n'
           '"x/orgaos/4";"MESA";"n";"n";"x/deputados/100";"A";"P";"SP";"Presidente";"2025-02-01";""\n')


def test_legislatura():
    assert presenca.legislatura(dt.date(2026, 10, 23)) == (57, dt.date(2023, 2, 1))
    assert presenca.legislatura(dt.date(2027, 1, 31)) == (57, dt.date(2023, 2, 1))
    assert presenca.legislatura(dt.date(2027, 2, 1)) == (58, dt.date(2027, 2, 1))


def test_ler_ano_camara():
    r = presenca.ler_ano_camara(EVENTOS.encode(), ORGAOS.encode(), PRES.encode(), INI)
    assert [e for _, e in r["plen"]] == ["1", "2", "6"]  # cancelada e de antes da legislatura ficam fora
    assert [(e, o) for _, e, o in r["com"]] == [("4", ("2003",))]  # audiencia publica sem deliberacao nao conta
    assert r["pres"]["100"] == ["1", "2", "4"] and r["pres"]["300"] == ["6"]


def test_membros_so_titulares_de_comissao():
    m = presenca.ler_membros(MEMBROS.encode())
    assert set(m) == {"100", "200"} and m["100"][0][0] == "2003"


def test_conta_camara_ignora_periodo_fora_do_mandato():
    base = presenca.juntar([presenca.ler_ano_camara(EVENTOS.encode(), ORGAOS.encode(), PRES.encode(), INI)])
    m = presenca.ler_membros(MEMBROS.encode())
    assert presenca.conta_camara("100", base, m) == ([2, 2], [1, 1])  # 10/jun: sem registro perto, fora do mandato
    assert presenca.conta_camara("200", base, m) == ([1, 2], [0, 1])
    assert presenca.conta_camara("300", base, m) == ([1, 1], [0, 0])  # suplente na comissao: nao e esperado


def test_ler_mes_senado():
    lista = [dict(votos=[dict(codigoParlamentar=1, siglaVotoParlamentar="Sim"),
                         dict(codigoParlamentar=2, siglaVotoParlamentar="NCom"),
                         dict(codigoParlamentar=3, siglaVotoParlamentar="LS", descricaoVotoParlamentar="Licença saúde")]),
             dict(votos=[dict(codigoParlamentar=1, siglaVotoParlamentar="P-NRV"),
                         dict(codigoParlamentar=2, siglaVotoParlamentar="Não")])]
    assert presenca.ler_mes_senado(lista) == {"1": [2, 2, 0], "2": [1, 2, 0], "3": [0, 1, 1]}


def test_meses_senado_consulta_um_mes_por_vez():
    urls = []
    total = presenca.meses_senado(lambda u: urls.append(u) or [dict(votos=[dict(codigoParlamentar=1,
                                                                                 siglaVotoParlamentar="Sim")])],
                                  None, dt.date(2023, 4, 15))
    assert len(urls) == 3 and "2023-02-01" in urls[0] and "2023-02-28" in urls[0] and total == {"1": [3, 3, 0]}
    assert presenca.meses_senado(lambda u: None, None, dt.date(2023, 3, 1)) is None


def test_anotar_integra_media_e_secao():
    base = presenca.juntar([presenca.ler_ano_camara(EVENTOS.encode(), ORGAOS.encode(), PRES.encode(), INI)])
    parl = [dict(casa="camara", _id="100", perfil="https://www.camara.leg.br/deputados/100"),
            dict(casa="camara", _id="200", perfil=""), dict(casa="senado", _id="5012", perfil=""),
            dict(casa="senado", _id="9", perfil="")]
    presenca.MINIMO, minimo = 1, presenca.MINIMO
    try:
        ctx = presenca.anotar(parl, hoje=HOJE, camara=base, membros=presenca.ler_membros(MEMBROS.encode()),
                              senado={"5012": [90, 100, 6]})
    finally:
        presenca.MINIMO = minimo
    a, b, s, sem = (p.get("presenca") for p in parl)
    assert a["pct"] == 100.0 and b["pct"] == 50.0 and a["media_casa"] == 75.0 and a["comissoes"] == [1, 1]
    assert s["pct"] == 90.0 and s["justificadas"] == 6 and s["comissoes"] is None and sem is None
    assert ctx["ativo"]("100", "2025-03-20") is True and ctx["ativo"]("100", "2025-09-01") is False
    h = presenca.secao(a, "DEPUTADO FEDERAL", ctx["fontes"])
    assert "100,0%" in h and "média da casa: 75,0%" in h and "nas comissões" in h and "perfil oficial" in h
    hs = presenca.secao(s, "SENADOR", ctx["fontes"])
    assert "votações nominais" in hs and "6 ausências" in hs and "Comissões: Não informado" in hs
    assert "Não informado" in presenca.secao(None, "GOVERNADOR", {})
    assert "Fonte não encontrada" in presenca.secao(None, "SENADOR", {"camara": True, "senado": False})
