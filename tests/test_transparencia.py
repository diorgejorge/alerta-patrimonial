"""Portal da Transparencia: cache so guarda resposta completa e falha mantem a ultima completa (sem rede)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import transparencia  # noqa: E402

PESSOA = {"k1": dict(nome="FULANO DE TAL", nome_urna="FULANO", cargo="SENADOR", cpf="11111111111", chave="cpf:1")}
BOA = {"api": True, "emendas": {}, "sem_cpf": False, "recursos_pf": [], "empresas": [],
       "pf": dict(beneficios=[], sancoes=[], despesas=False, servidor=False)}


class Guarda(dict):
    """Cache falso com a mesma interface de cache.Cache."""
    salvo = False

    def set(self, k, v):
        self[k] = v

    def salvar(self):
        self.salvo = True


def portal(monkeypatch, resposta):
    monkeypatch.setattr(transparencia, "_pessoa", lambda api, p: resposta)


def test_completo_reconhece_partes_que_faltaram():
    assert transparencia.completo(BOA)
    assert not transparencia.completo({**BOA, "pf": None})
    assert not transparencia.completo({**BOA, "recursos_pf": None})
    assert not transparencia.completo({**BOA, "emendas": None})
    assert not transparencia.completo({**BOA, "empresas": [("EMPRESA X", None)]})
    assert not transparencia.completo({**BOA, "pf": {**BOA["pf"], "beneficios": [dict(erro=True)]}})
    assert not transparencia.completo({"pendente": "tempo"})
    assert transparencia.completo({**BOA, "sem_cpf": True, "pf": None, "recursos_pf": None})


def test_falha_mantem_a_ultima_resposta_completa(monkeypatch):
    portal(monkeypatch, {**BOA, "pf": None, "recursos_pf": None})
    cache, bom = Guarda(), Guarda({"cpf:1": BOA})
    out = transparencia.coletar(PESSOA, chave_api="x", cache=cache, bom=bom)
    assert out["k1"] == BOA
    assert "cpf:1" not in cache  # resposta incompleta nao entra no cache: a proxima carga tenta de novo


def test_resposta_completa_vai_para_os_dois_caches(monkeypatch):
    portal(monkeypatch, BOA)
    cache, bom = Guarda(), Guarda()
    out = transparencia.coletar(PESSOA, chave_api="x", cache=cache, bom=bom)
    assert out["k1"] == cache["cpf:1"] == bom["cpf:1"] == BOA
    assert cache.salvo and bom.salvo


def test_cache_incompleto_de_cargas_antigas_e_consultado_de_novo(monkeypatch):
    portal(monkeypatch, BOA)
    cache = Guarda({"cpf:1": {**BOA, "pf": None}})
    assert transparencia.coletar(PESSOA, chave_api="x", cache=cache)["k1"] == BOA


def test_sem_resposta_anterior_fica_fonte_nao_encontrada(monkeypatch):
    portal(monkeypatch, {**BOA, "pf": None})
    out = transparencia.coletar(PESSOA, chave_api="x", cache=Guarda(), bom=Guarda())
    assert "Fonte não encontrada" in transparencia.secao(out["k1"], "FULANO")


class Resposta:
    def __init__(self, corpo):
        self.corpo = corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        return self.corpo


def test_corpo_vazio_e_sem_registro_nao_falha(monkeypatch):
    """O Portal responde vazio quando o CPF nao consta em nada: vira lista vazia, nao "Fonte nao encontrada"."""
    monkeypatch.setattr(transparencia.urllib.request, "urlopen", lambda req, timeout: Resposta(b""))
    monkeypatch.setattr(transparencia.time, "sleep", lambda s: None)
    api = transparencia.Api("x", transparencia.time.monotonic() + 60)
    pf = transparencia.pessoa_fisica(api, "11111111111", "FULANO")
    assert pf == dict(beneficios=[], sancoes=[], despesas=False, servidor=False)
    assert (api.falhas, api.vazias) == (0, 1)


def test_corpo_json_continua_igual(monkeypatch):
    monkeypatch.setattr(transparencia.urllib.request, "urlopen", lambda req, timeout: Resposta(b'[{"servidor": true}]'))
    monkeypatch.setattr(transparencia.time, "sleep", lambda s: None)
    api = transparencia.Api("x", transparencia.time.monotonic() + 60)
    assert transparencia.pessoa_fisica(api, "11111111111", "FULANO")["servidor"] is True
