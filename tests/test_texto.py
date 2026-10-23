import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from texto import cap


def test_cap_igual_ao_painel():
    assert cap("DEPUTADO ESTADUAL") == "Deputado Estadual"
    assert cap("MARIA DA SILVA E SOUZA") == "Maria da Silva e Souza"
    assert cap("ZÉ TEIXEIRA") == "Zé Teixeira"
    assert cap(None) == "" and cap("") == ""
