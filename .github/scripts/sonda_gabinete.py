"""Sonda temporaria (#66): verifica fontes oficiais da equipe de gabinete. Apagar depois."""
import re, urllib.request
UA = {"User-Agent": "alerta-patrimonial/1.0", "Accept": "text/html, */*"}


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


for dep in (220593, 204554):
    h = get(f"https://www.camara.leg.br/deputados/{dep}/pessoal-gabinete")
    i = h.find("Pessoal de gabinete")
    print(texto(h[i - 200:])[:2500])
    print("tabelas:", re.findall(r"<table[^>]*>", h), re.findall(r"<h[23][^>]*>.*?</h[23]>", h, re.S)[:10])
    print("links:", sorted(set(re.findall(r'href="([^"]*(?:gabinete|pessoal|secretar)[^"]*)"', h, re.I)))[:20])
for u in ("https://www6g.senado.leg.br/transparencia/sen/5672/pessoal/?local=gabinete&vinculo=todos",
          "https://www6g.senado.gov.br/transparencia/sen/5672/pessoal/?local=gabinete&vinculo=todos",
          "https://www25.senado.leg.br/web/transparencia/sen/5672/pessoal"):
    h = get(u)
    print(texto(h)[:1200])
