"""Processos em que a pessoa e re: validacao da issue aprovada e leitura de config/processos.csv. Sem rede."""
import json, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / ".github" / "scripts"))
import aprovar_processo as ap  # noqa: E402
import pipeline  # noqa: E402

STF = "https://portal.stf.jus.br/processos/detalhe.asp?incidente=1"


def test_validacao():
    assert ap.validar("Fulano", "MG", "STF", "AP 1044", STF) == ""
    assert ap.validar("Fulano", "MG", "TJMG", "0000001-02.2024.8.13.0024", "https://www.jusbrasil.com.br/processos/1") == ""
    assert ap.validar("Fulano", "MG", "TJMG", "AP 1044", "https://www.escavador.com/processos/1") == ""
    assert "link" in ap.validar("Fulano", "MG", "TJMG", "AP 1044", "https://escavador.com.exemplo.net/x")  # dominio falso
    assert ap.validar("Fulano", "MG", "TJMG", "AP 1044", "https://processorapido.com/processos/x/y/") == ""
    assert "formato" in ap.validar("Fulano", "MG", "STF", "qualquer coisa", STF)
    assert "link" in ap.validar("Fulano", "MG", "STF", "AP 1044", "http://portal.stf.jus.br/x")        # sem https
    assert "link" in ap.validar("Fulano", "MG", "STF", "AP 1044", "https://exemplo.com/processo")      # outro site
    assert "link" in ap.validar("Fulano", "MG", "STF", "AP 1044", "https://jus.br.exemplo.com/x")      # dominio falso
    assert "CPF" in ap.validar("Fulano 123.456.789-09", "MG", "STF", "AP 1044", STF)
    assert "faltou" in ap.validar("", "MG", "STF", "AP 1044", STF)


def test_issue_aprovada_grava_csv(tmp_path, monkeypatch):
    corpo = ("### Nome da pessoa (como aparece no painel)\n\nFulano de Tal\n\n### Estado da pessoa no painel\n\nMG\n\n"
             "### Tribunal\n\nSTF\n\n### Número do processo\n\nAP 1044\n\n### Link da consulta\n\n" + STF + "\n")
    ev = tmp_path / "ev.json"
    ev.write_text(json.dumps({"issue": {"number": 7, "body": corpo}}), encoding="utf-8")
    saida = tmp_path / "out.txt"
    monkeypatch.setattr(ap, "CSV", tmp_path / "processos.csv")
    monkeypatch.setattr(ap, "ROOT", tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(ev))
    monkeypatch.setenv("GITHUB_OUTPUT", str(saida))
    ap.main()
    assert "ok=true" in saida.read_text()
    linhas = (tmp_path / "processos.csv").read_text(encoding="utf-8").splitlines()
    assert linhas[0] == "nome,uf,tribunal,numero,link,issue,incluido_em"
    assert linhas[1].startswith("Fulano de Tal,MG,STF,AP 1044,https://portal.stf.jus.br/")
    ap.main()  # repetido: nao duplica
    assert len((tmp_path / "processos.csv").read_text(encoding="utf-8").splitlines()) == 2


def test_pipeline_le_so_links_validos(tmp_path, monkeypatch):
    (tmp_path / "processos.csv").write_text(
        "nome,uf,tribunal,numero,link,issue,incluido_em\n"
        f"Fulano de Tal,MG,STF,AP 1044,{STF},7,2026-10-22\n"
        "Fulano de Tal,MG,X,1,javascript:alert(1),8,2026-10-22\n"
        "Beltrana,SP,TJSP,1,https://exemplo.com/x,9,2026-10-22\n", encoding="utf-8")
    monkeypatch.setattr(pipeline, "CFG", tmp_path)
    p = pipeline.carregar_processos()
    assert p == {("FULANO DE TAL", "MG"): [dict(tribunal="STF", numero="AP 1044", link=STF)]}
