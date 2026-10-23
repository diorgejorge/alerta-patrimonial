"""Texto para exibir: nomes e cargos que vem em MAIUSCULAS das fontes (TSE) ficam como no painel (CAP do template)."""
import re

_MIN = frozenset({"de", "da", "do", "das", "dos", "e"})


def cap(s):
    """'DEPUTADO ESTADUAL' -> 'Deputado Estadual'; 'MARIA DA SILVA E SOUZA' -> 'Maria da Silva e Souza'."""
    return re.sub(r"[^\W\d_]+", lambda m: m[0] if m[0] in _MIN else m[0][0].upper() + m[0][1:], str(s or "").lower())
