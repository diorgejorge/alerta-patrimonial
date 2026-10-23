"""Foto oficial da candidatura (DivulgaCandContas) e avatar com volta para as iniciais."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.setdefault("ID_SEGREDO", "segredo-de-teste")
from pipeline import link_foto
from paginas import avatar

LINHA = dict(uf="SP", sg_ue="SP", sq_candidato="250001607829", ano=2022, suplementar=False)


def test_link_foto_monta_url_do_tse():
    assert link_foto(LINHA) == "https://divulgacandcontas.tse.jus.br/divulga/rest/arquivo/img/2040602022/250001607829/SP"


def test_link_foto_sem_dados_ou_suplementar():
    assert link_foto({**LINHA, "sq_candidato": None}) is None
    assert link_foto({**LINHA, "suplementar": True}) is None
    assert link_foto({**LINHA, "ano": 1990}) is None


def test_avatar_com_foto_mantem_iniciais_por_baixo():
    h = avatar("MARIA DA SILVA", foto="https://divulgacandcontas.tse.jus.br/x.jpg")
    assert ">MS<img" in h and 'referrerpolicy="no-referrer"' in h and 'onerror="this.remove()"' in h


def test_avatar_ignora_foto_que_nao_e_https():
    assert "<img" not in avatar("MARIA", foto="javascript:alert(1)") and "<img" not in avatar("MARIA")
