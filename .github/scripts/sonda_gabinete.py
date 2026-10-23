"""Sonda temporaria (#gabinete): verifica fontes oficiais da equipe de gabinete. Apagar depois."""
import json, re, urllib.request
UA = {"User-Agent": "alerta-patrimonial/1.0", "Accept": "application/json, text/html, */*"}


def get(url, n=600):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            b = r.read()
            print(f"\n=== {r.status} {url} ({len(b)} bytes, {r.headers.get('Content-Type')})")
            return b.decode("utf-8", "replace")
    except Exception as ex:
        print(f"\n=== ERRO {url}: {ex}")
        return ""


doc = get("https://dadosabertos.camara.leg.br/api/v2/api-docs")
print(sorted(set(re.findall(r'"(/[a-zA-Z/{}]+)"\s*:', doc))))
arq = get("https://dadosabertos.camara.leg.br/arquivos/")
print(sorted(set(re.findall(r'arquivos/([A-Za-z]+)/', arq)))[:200])
for ano in (2025, 2026):
    h = get(f"https://www.camara.leg.br/deputados/204554/pessoal-gabinete?ano={ano}")
    i = h.find("<table")
    print(re.sub(r"\s+", " ", h[i:i + 3000]))
    print("linhas tbody:", h.count("<tr") - 1)
sen = get("https://adm.senado.gov.br/adm-dadosabertos/v3/api-docs")
print(sorted(set(re.findall(r'"(/api/[^"]+)"\s*:', sen))))
s = get("https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/servidores")
try:
    d = json.loads(s)
    print(type(d), len(d))
    print(json.dumps(d[:3], ensure_ascii=False)[:2000])
    lot = {}
    for x in d:
        k = json.dumps({c: v for c, v in x.items() if "lota" in c.lower()}, ensure_ascii=False)
        lot[k] = lot.get(k, 0) + 1
    for k, v in sorted(lot.items(), key=lambda t: -t[1])[:40]:
        print(v, k)
    print("com GABINETE/SENADOR:", sum(v for k, v in lot.items() if re.search("GABINETE|SENADOR", k, re.I)))
except Exception as ex:
    print("json:", ex, s[:500])
