"""Pagina propria para parlamentares em exercicio fora dos destaques (so_pagina): ganham pagina, nao viram card."""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import paginas, pipeline  # noqa: E402


def pares():
    return pd.DataFrame([dict(chave="cpf:1", nome="ANA", ano_ini=2014, ano_fim=2018, nivel="forte", cresc=1.0),
                         dict(chave="cpf:1", nome="ANA", ano_ini=2018, ano_fim=2022, nivel=None, cresc=2.0),
                         dict(chave="cpf:2", nome="BIA", ano_ini=2018, ano_fim=2022, nivel=None, cresc=3.0)])


def test_so_paginas_pega_o_periodo_mais_recente_de_cada_um():
    x = pipeline.so_paginas(pares(), {"cpf:1"}, pid={"cpf:1": "p0007"}.get)
    assert len(x) == 1 and x.iloc[0].ano_fim == 2022 and x.iloc[0].pessoa == "p0007"
    assert x.iloc[0].so_pagina and not x.iloc[0].novo and x.iloc[0].id == "p0007|2018-2022"


def test_so_paginas_sem_ninguem():
    assert pipeline.so_paginas(pares(), set()).empty


def test_extra_ganha_pagina_mas_nao_card(tmp_path, monkeypatch):
    monkeypatch.setattr(paginas, "pagina", lambda *a, **k: "<html></html>")
    monkeypatch.setattr(paginas, "cartao", lambda pid, linhas, h: f"<li>{pid}</li>")
    alertas = [dict(pessoa="p0001", nivel="forte", cresc=1.0), dict(pessoa="p0002", nivel="forte", cresc=1.0, so_pagina=True)]
    pessoas = {"a": dict(idx=[0], chave="cpf:1"), "b": dict(idx=[1], chave="cpf:2")}
    cartoes, graf = paginas.gerar(alertas, pessoas, {}, {}, tmp_path, gerado="hoje")
    assert (tmp_path / "pessoa" / "p0002.html").exists() and alertas[1]["pagina"] == "pessoa/p0002.html"
    assert "p0001" in cartoes and "p0002" not in cartoes
