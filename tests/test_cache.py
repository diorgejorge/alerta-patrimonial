"""Cache incremental entre execucoes: validade, cifra, assinatura. Sem rede."""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from cache import Cache  # noqa: E402

CPF = "12345678909"


def test_guarda_e_le_de_novo(tmp_path):
    c = Cache(tmp_path / "x.cache", 3600, "segredo", cifrar=True)
    c.set(f"cpf:{CPF}", {"pf": {"sancoes": []}, "nome": "FULANO"})
    c.salvar()
    d = Cache(tmp_path / "x.cache", 3600, "segredo", cifrar=True)
    assert d.get(f"cpf:{CPF}") == {"pf": {"sancoes": []}, "nome": "FULANO"}
    assert d.get("outra") is None


def test_cifrado_sem_cpf_nem_nome_no_arquivo(tmp_path):
    c = Cache(tmp_path / "x.cache", 3600, "segredo", cifrar=True)
    c.set(f"cpf:{CPF}", "FULANO DE TAL " * 50)
    c.salvar()
    bruto = (tmp_path / "x.cache").read_bytes()
    assert CPF.encode() not in bruto and b"FULANO" not in bruto


def test_validade_vencida(tmp_path, monkeypatch):
    c = Cache(tmp_path / "x.cache", 60, "segredo")
    c.set("k", 1)
    c.salvar()
    agora = time.time()
    monkeypatch.setattr(time, "time", lambda: agora + 120)
    assert Cache(tmp_path / "x.cache", 60, "segredo").get("k") is None


def test_adulterado_ou_outro_segredo_descarta(tmp_path):
    c = Cache(tmp_path / "x.cache", 3600, "segredo", cifrar=True)
    c.set("k", 1)
    c.salvar()
    assert Cache(tmp_path / "x.cache", 3600, "outro", cifrar=True).get("k") is None
    b = bytearray((tmp_path / "x.cache").read_bytes())
    b[-1] ^= 1
    (tmp_path / "x.cache").write_bytes(bytes(b))
    assert Cache(tmp_path / "x.cache", 3600, "segredo", cifrar=True).get("k") is None
