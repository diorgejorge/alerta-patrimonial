#!/usr/bin/env python3
"""Grava em config/processos.csv o processo informado numa issue aprovada (rotulo "aprovada").
O texto da issue e de terceiros: so le campos conhecidos e valida numero e link (site de tribunal *.jus.br,
Jusbrasil ou Escavador) antes de gravar. Nao abre o link (esses sites restringem robos). Escreve a resposta em resposta.md e
ok=true/false em $GITHUB_OUTPUT."""
import csv, datetime as dt, json, os, re, sys, urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aprovar_fonte import campo, secoes  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "config" / "processos.csv"
CAMPOS = ["nome", "uf", "tribunal", "numero", "link", "issue", "incluido_em"]
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO BR".split())
RE_CNJ = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")
RE_CLASSE = re.compile(r"^[A-Za-zÀ-ú]{2,12}\.?\s?\d{1,7}$")  # ex.: AP 1044, Inq 4781
RE_DOC = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")  # CPF no texto: recusa
HOSTS = {"jusbrasil.com.br", "www.jusbrasil.com.br", "escavador.com", "www.escavador.com"}  # alem de *.jus.br


def link_ok(u):
    p = urllib.parse.urlsplit(u)
    host = p.netloc.lower().split(":")[0]
    return (p.scheme == "https" and not re.search(r"\s", u)
            and (host.endswith(".jus.br") or host in HOSTS))


def validar(nome, uf, tribunal, numero, link):
    """Mensagem de erro, ou '' se esta tudo certo."""
    if not nome or uf not in UFS or not tribunal:
        return "faltou o nome da pessoa, o estado ou o tribunal"
    if RE_DOC.search(" ".join((nome, tribunal, numero))):
        return "o texto parece conter um CPF; não informe CPF"
    if not (RE_CNJ.match(numero) or RE_CLASSE.match(numero)):
        return f"o número `{numero}` não está no formato do CNJ (0000000-00.0000.0.00.0000) nem como classe e número (ex.: AP 1044)"
    if not link_ok(link):
        return "o link precisa ser https e de um tribunal (*.jus.br), do Jusbrasil ou do Escavador"
    return ""


def main():
    ev = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = ev["issue"]
    s = secoes(issue.get("body"))
    nome = " ".join(campo(s, "nome da pessoa").split())[:120]
    uf = campo(s, "estado da pessoa").strip().upper()
    tribunal = " ".join(campo(s, "tribunal").split())[:40]
    numero = " ".join(campo(s, "número do processo").split())[:40]
    link = campo(s, "link da consulta").strip().strip("`<>")
    ok, erro = False, validar(nome, uf, tribunal, numero, link)
    if erro:
        msg = f"Não consegui gravar: {erro}. Corrija a issue e aplique o rótulo de novo."
    else:
        linhas = list(csv.DictReader(CSV.open(encoding="utf-8"))) if CSV.exists() else []
        if any(l["numero"] == numero and l["tribunal"].upper() == tribunal.upper() and l["nome"].upper() == nome.upper()
               for l in linhas):
            msg = f"O processo {numero} ({tribunal}) já está na lista para {nome}."
        else:
            novo = not CSV.exists()
            with CSV.open("a", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=CAMPOS)
                if novo:
                    w.writeheader()
                w.writerow(dict(nome=nome, uf=uf, tribunal=tribunal, numero=numero, link=link, issue=issue["number"],
                                incluido_em=dt.date.today().isoformat()))
            ok = True
            msg = (f"Processo **{numero}** ({tribunal}) adicionado para **{nome}** ({uf}). A tag aparece no painel e no "
                   "dossiê na próxima atualização. Quando o processo terminar, remova a linha de `config/processos.csv`.")
    (ROOT / "resposta.md").write_text(msg, encoding="utf-8")
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
        f.write(f"ok={'true' if ok else 'false'}\n")
    print(msg)


if __name__ == "__main__":
    sys.exit(main())
