"""Texto para exibir: nomes e cargos que vem em MAIUSCULAS das fontes (TSE) ficam como no painel (CAP do template)."""
import re

_MIN = frozenset({"de", "da", "do", "das", "dos", "e"})


def cap(s):
    """'DEPUTADO ESTADUAL' -> 'Deputado Estadual'; 'MARIA DA SILVA E SOUZA' -> 'Maria da Silva e Souza'."""
    return re.sub(r"[^\W\d_]+", lambda m: m[0] if m[0] in _MIN else m[0][0].upper() + m[0][1:], str(s or "").lower())


_ARTIGO_UF = dict(AC="o", AP="o", AM="o", BA="a", CE="o", DF="o", ES="o", MA="o", PA="o", PB="a", PR="o", PI="o",
                  RJ="o", RN="o", RS="o", TO="o")  # sem artigo: Alagoas, Goias, Minas Gerais, Sao Paulo...


def de_estado(sigla, nome):
    """('BA', 'Bahia') -> 'da Bahia'; ('PA', 'Pará') -> 'do Pará'; ('SP', 'São Paulo') -> 'de São Paulo'."""
    art = _ARTIGO_UF.get(str(sigla).upper(), "")
    return f"{'d' + art if art else 'de'} {nome}"
