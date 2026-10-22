"""Arquivos salvos cifrados (cifra.py): ida e volta, assinatura, migracao do texto puro e limpeza. Sem rede."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import cifra  # noqa: E402

CPF = b"12345678909"


def test_ida_e_volta_sem_texto_legivel(tmp_path):
    dados = b'{"cpf": "12345678909", "nome": "FULANO DE TAL"}' * 100
    assert cifra.gravar(tmp_path / "a.json", dados, "seg")
    bruto = (tmp_path / "a.json").read_bytes()
    assert bruto[:4] == cifra.MAGIA and CPF not in bruto and b"FULANO" not in bruto
    assert cifra.ler(tmp_path / "a.json", "seg") == dados


def test_outro_segredo_ou_alterado_nao_le(tmp_path):
    cifra.gravar(tmp_path / "a", b"conteudo", "seg")
    assert cifra.ler(tmp_path / "a", "outro") is None
    b = bytearray((tmp_path / "a").read_bytes())
    b[-1] ^= 1
    (tmp_path / "a").write_bytes(bytes(b))
    assert cifra.ler(tmp_path / "a", "seg") is None


def test_sem_segredo_nao_grava(tmp_path, monkeypatch):
    monkeypatch.delenv("ID_SEGREDO", raising=False)
    assert not cifra.gravar(tmp_path / "a", b"x")
    assert not (tmp_path / "a").exists()


def test_texto_puro_antigo_so_com_aceitar_puro(tmp_path):
    (tmp_path / "ids.json").write_text('{"abc": "p0001"}', encoding="utf-8")
    assert cifra.ler(tmp_path / "ids.json", "seg") is None
    assert cifra.ler(tmp_path / "ids.json", "seg", aceitar_puro=True) == b'{"abc": "p0001"}'


def test_limpar_puros_mantem_cifrados_e_datas(tmp_path):
    cifra.gravar(tmp_path / "ok.zip", b"zip", "seg")
    (tmp_path / "ok.zip.modificado").write_text("Wed, 21 Oct 2026 22:33:23 GMT")
    (tmp_path / "antigo.zip").write_bytes(b"PK\x03\x04 texto puro")
    assert cifra.limpar_puros(tmp_path) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ok.zip", "ok.zip.modificado"]


def test_baixar_usa_copia_sem_rede(tmp_path, monkeypatch):
    cifra.gravar(tmp_path / "tse.zip", b"conteudo guardado", "seg")

    def sem_rede(*a, **k):
        raise AssertionError("nao devia acessar a rede")
    monkeypatch.setattr(cifra.urllib.request, "urlopen", sem_rede)
    assert cifra.baixar("https://exemplo/tse.zip", tmp_path / "tse.zip", perguntar=False, seg="seg") == b"conteudo guardado"
