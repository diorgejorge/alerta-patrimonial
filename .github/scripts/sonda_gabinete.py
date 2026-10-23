"""Sonda temporaria (#66): verifica fontes oficiais da equipe de gabinete. Apagar depois."""
import json, re, sys, urllib.request
sys.path.insert(0, "src")
import gabinete
UA = {"User-Agent": "alerta-patrimonial/1.0", "Accept": "text/html, application/json, */*"}


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
            b = r.read()
            print(f"\n=== {r.status} {r.url} ({len(b)} bytes)")
            return b.decode("utf-8", "replace")
    except Exception as ex:
        print(f"\n=== ERRO {url}: {ex}")
        return ""


def texto(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))


deps = json.loads(get("https://dadosabertos.camara.leg.br/api/v2/deputados?itens=3&ordem=ASC&ordenarPor=nome"))["dados"]
for d in deps:
    h = get(gabinete.CAMARA.format(id=d["id"]))
    i, j = h.find("Pessoal de gabinete - "), h.find("Histórico de contratação")
    print(d["nome"], "| contagem:", gabinete.contar_camara(h), "| tabelas:", h.count("<table"))
    print("ATUAL:", re.sub(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?: [A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,})+", "NOME", texto(h[i:j if j > 0 else i + 6000]))[:1500])
    print("estrutura atual:", re.findall(r"<t[dh][^>]*>", h[i:j])[:12])
for local in ("gabinete", "escritorio"):
    h = get(f"https://www6g.senado.leg.br/transparencia/sen/5672/pessoal/?local={local}&vinculo=todos")
    t = texto(h)
    print(local, re.findall(r"(Efetivos|Comissionados|Terceirizados|Estagi\w+) \((\d+)\)", t)[:6],
          re.findall(r"Escrit\w+ de apoio[^.]{0,80}", t)[:3])
at = json.loads(get(gabinete.SENADO))
c = gabinete.contar_senado(at)
print("API Alan Rick:", c.get("ALAN RICK"), "| senadores na API:", len(c))
print(sorted(c.items(), key=lambda t: -t[1])[:5], sorted(c.items(), key=lambda t: t[1])[:5])
