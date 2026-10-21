#!/usr/bin/env python3
"""Grava em config/fontes_noticias.csv a fonte sugerida numa issue aprovada (rotulo "aprovada").
O texto da issue e de terceiros: so le campos conhecidos, valida a URL e testa o feed antes de gravar.
Escreve a resposta para a issue em resposta.md e ok=true/false em $GITHUB_OUTPUT."""
import csv, json, os, re, sys, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "config" / "fontes_noticias.csv"
CAMPOS = ["nome", "feed", "uf", "issue"]
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
UA = "Mozilla/5.0 (compatible; alerta-patrimonial/1.0)"


def secoes(corpo):
    """Corpo de issue form: '### Rotulo' seguido do valor; '_No response_' = vazio."""
    out, atual = {}, None
    for linha in (corpo or "").splitlines():
        m = re.match(r"^###\s+(.+?)\s*$", linha)
        if m:
            atual = m.group(1).lower()
            out[atual] = []
        elif atual is not None:
            out[atual].append(linha)
    return {k: ("" if "\n".join(v).strip() == "_No response_" else "\n".join(v).strip()) for k, v in out.items()}


def campo(s, inicio):
    return next((v for k, v in s.items() if k.startswith(inicio)), "")


def url_ok(u):
    p = urllib.parse.urlsplit(u)
    return p.scheme in ("http", "https") and bool(p.netloc) and not re.search(r"\s", u)


def testar(feed):
    url = feed.replace("{q}", urllib.parse.quote_plus("governo"))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        raiz = ET.fromstring(r.read(5_000_000))
    if raiz.find(".//item") is None and (raiz.tag != "rss" or raiz.find("channel") is None):
        raise ValueError("o endereço respondeu, mas não é um feed RSS")  # busca sem resultado ainda vale


def main():
    ev = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = ev["issue"]
    s = secoes(issue.get("body"))
    nome = " ".join(campo(s, "nome do ve").split())[:80]
    site = campo(s, "site do ve").strip()
    feed = campo(s, "feed rss").strip().strip("`<>")
    uf = campo(s, "abrang").strip().upper()
    uf = "" if uf == "NACIONAL" or uf not in UFS else uf
    if not feed and url_ok(site):
        feed = site.rstrip("/") + "/?s={q}&feed=rss2"
    ok, msg = False, ""
    if not nome or not url_ok(feed):
        msg = "Não consegui gravar: faltou o nome do veículo ou um endereço de feed válido (http/https)."
    else:
        try:
            testar(feed)
        except Exception as ex:
            msg = f"Não consegui gravar: o feed `{feed}` não funcionou ({ex}). Corrija o endereço na issue e aplique o rótulo de novo."
        else:
            linhas = list(csv.DictReader(CSV.open(encoding="utf-8"))) if CSV.exists() else []
            if any(l["feed"].strip().lower() == feed.lower() for l in linhas):
                msg = f"O feed `{feed}` já está na lista de fontes."
            else:
                novo = not CSV.exists()
                with CSV.open("a", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=CAMPOS)
                    if novo:
                        w.writeheader()
                    w.writerow(dict(nome=nome, feed=feed, uf=uf, issue=issue["number"]))
                ok = True
                onde = f"pessoas de {uf}" if uf else "todas as pessoas"
                msg = (f"Fonte **{nome}** adicionada (`{feed}`), usada para {onde}. "
                       "Ela entra nos dossiês na próxima atualização. Obrigado!")
    (ROOT / "resposta.md").write_text(msg, encoding="utf-8")
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
        f.write(f"ok={'true' if ok else 'false'}\n")
    print(msg)


if __name__ == "__main__":
    sys.exit(main())
