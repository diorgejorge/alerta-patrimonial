"""Equipe do gabinete (#66): so a contagem de pessoas, sem rede (paginas e respostas mockadas)."""
import datetime as dt, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import gabinete  # noqa: E402

HOJE = dt.date(2026, 10, 23)
LINHA = '<tr><td scope="row">NOME</td><td>SECRETÁRIO PARLAMENTAR</td><td>SP25</td><td class="col-md-2">\n  {p}\n</td></tr>'
CAMARA = ("<h2>Pessoal de gabinete - 2026</h2><p>Em exercício</p><table>"
          + "".join(LINHA.format(p=p) for p in ("Desde 18/02/2026", "Desde 09/07/2025", "Desde 01/12/2026"))
          + "</table><h2>Histórico de contratação</h2><table>"
          + "".join(LINHA.format(p=p) for p in ("De 05/04/2021 a 31/01/2023", "De 01/02/2023 a 30/12/2026")) + "</table>")
SENADO = [
    dict(vinculo="COMISSIONADO", lotacao=dict(nome="Gabinete do Senador Beto Faro")),
    dict(vinculo="EFETIVO", lotacao=dict(nome="Escritório de Apoio nº 1 do Senador Beto Faro")),
    dict(vinculo="PARLAMENTAR", lotacao=dict(nome="Gabinete do Senador Beto Faro")),
    dict(vinculo="COMISSIONADO", lotacao=dict(nome="Gabinete da Senadora Leany Lemos")),
    dict(vinculo="EFETIVO", lotacao=dict(nome="Primeira-Secretaria")),
    dict(vinculo="COMISSIONADO", lotacao=None),
]


class CacheFalso(dict):
    def set(self, k, v):
        self[k] = v

    def salvar(self):
        pass


def test_contar_camara_so_exercicio_em_andamento():
    assert gabinete.contar_camara(CAMARA, HOJE) == 2
    assert gabinete.contar_camara("", HOJE) == 0
    assert gabinete.contar_camara(None, HOJE) == 0


def test_nome_lotacao_senado():
    assert gabinete.nome_lotacao_senado("Gabinete do Senador Beto Faro") == "BETO FARO"
    assert gabinete.nome_lotacao_senado("Escritório Apoio 1 do Senador Randolfe Rodrigues") == "RANDOLFE RODRIGUES"
    assert gabinete.nome_lotacao_senado("Escritório de Apoio n 1 da Senadora Roberta Acioly") == "ROBERTA ACIOLY"
    assert gabinete.nome_lotacao_senado("Gabinete da Liderança do PT") is None
    assert gabinete.nome_lotacao_senado("Serviço de Proteção de Senadores e Servidores") is None


def test_contar_senado_soma_gabinete_e_escritorio_sem_o_senador():
    assert gabinete.contar_senado(SENADO) == {"BETO FARO": 2, "LEANY LEMOS": 1}


def _parl():
    return [dict(casa="camara", _id="10", _chave="cpf:a", nome="Dep A"),
            dict(casa="camara", _id="11", _chave="cpf:b", nome="Dep B"),
            dict(casa="senado", _id="5", _chave="cpf:c", nome="Beto Faro", _nome_completo="Jose Faro"),
            dict(casa="senado", _id="6", _chave="cpf:d", nome="Fulano Novo", _nome_completo=""),
            dict(casa="camara", _id="12", _chave="cpf:fora", nome="Sem pagina")]


def test_coletar_integra_casas_e_falhas():
    pedidos = []

    def html(url):
        pedidos.append(url)
        return None if "/11/" in url else CAMARA

    cache = CacheFalso()
    out = gabinete.coletar(_parl(), {"cpf:a", "cpf:b", "cpf:c", "cpf:d"}, cache, pausa=0,
                           buscar_html=html, buscar_json=lambda u: SENADO, hoje=HOJE)
    assert out["cpf:a"] == dict(pessoas=2, link=gabinete.CAMARA.format(id="10"))
    assert out["cpf:b"] is None  # Camara nao respondeu: "Fonte nao encontrada"
    assert out["cpf:c"] == dict(pessoas=2, link=gabinete.SENADO_LINK.format(cod="5"))
    assert out["cpf:d"] == dict(pessoas=None, link=gabinete.SENADO_LINK.format(cod="6"))  # "Nao informado"
    assert "cpf:fora" not in out and len(pedidos) == 2
    assert cache == {"gabinete:camara:10": out["cpf:a"]}  # falha nao vai para o cache
    # segunda execucao: a Camara sai do cache, sem nova consulta
    pedidos.clear()
    gabinete.coletar(_parl()[:1], {"cpf:a"}, cache, pausa=0, buscar_html=html, buscar_json=lambda u: None, hoje=HOJE)
    assert pedidos == []


def test_coletar_senado_fora_do_ar():
    out = gabinete.coletar(_parl(), {"cpf:c"}, pausa=0, buscar_html=lambda u: CAMARA, buscar_json=lambda u: None)
    assert out == {"cpf:c": None}


def test_secao_textos():
    assert "<b>12</b> pessoas trabalham" in gabinete.secao(dict(pessoas=12, link="https://www.camara.leg.br/x"), "DEPUTADO FEDERAL")
    assert 'href="https://www.camara.leg.br/x"' in gabinete.secao(dict(pessoas=1, link="https://www.camara.leg.br/x"),
                                                                    "DEPUTADO FEDERAL")
    assert "<b>1</b> pessoa trabalha" in gabinete.secao(dict(pessoas=1, link="https://x"), "SENADOR")
    assert "Fonte não encontrada" in gabinete.secao(None, "SENADOR", consultado=True)
    assert "Não informado" in gabinete.secao(dict(pessoas=None, link="https://x"), "SENADOR")
    assert "Não informado" in gabinete.secao(None, "PREFEITO")


def test_secao_sem_nomes_nem_salarios():
    h = gabinete.secao(dict(pessoas=7, link="https://www.camara.leg.br/x"), "DEPUTADO FEDERAL")
    assert "R$" not in h and "NOME" not in h


def test_bloco_da_pagina_some_sem_dado():
    import paginas
    assert paginas._equipe(None) == ""  # cargo sem gabinete ou dado ainda nao carregado: bloco escondido
    assert "Equipe do gabinete" in paginas._equipe((dict(pessoas=5, link="https://www.camara.leg.br/x"),))
    assert "Fonte não encontrada" in paginas._equipe((None,))

