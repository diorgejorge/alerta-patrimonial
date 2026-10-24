"""Intervalo de recarga de cada fonte (config/recarga.json, #71): dentro do prazo, a carga usa o dado ja processado
e guardado e nem consulta a fonte."""
import json
import time
from functools import lru_cache
from pathlib import Path

ARQ = Path(__file__).resolve().parent.parent / "config" / "recarga.json"
DIA = 86400


@lru_cache(maxsize=None)
def _config(arq=ARQ):
    try:
        return json.loads(Path(arq).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def dias(chave, padrao):
    """Dias configurados para a fonte; o padrao quando o arquivo ou a chave faltam ou o valor e invalido."""
    v = _config().get(chave)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else padrao


def segundos(chave, padrao):
    return dias(chave, padrao) * DIA


def vencido(em, chave, padrao, agora=None):
    """A ultima carga (`em`, epoch) ja passou do prazo da fonte? Sem carga anterior, sim."""
    return not em or (agora or time.time()) - em >= segundos(chave, padrao)
