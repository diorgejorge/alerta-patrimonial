"""Sonda temporaria (#66): verifica fontes oficiais da equipe de gabinete. Apagar depois."""
import json, re, urllib.request
from collections import Counter
UA = {"User-Agent": "alerta-patrimonial/1.0", "Accept": "application/json, text/html, */*"}


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
            b = r.read()
            print(f"\n=== {r.status} {url} ({len(b)} bytes)")
            return b.decode("utf-8", "replace")
    except Exception as ex:
        print(f"\n=== ERRO {url}: {ex}")
        return ""


for dep in (204554, 220593, 178957):
    for q in ("", "?ano=2024"):
        h = get(f"https://www.camara.leg.br/deputados/{dep}/pessoal-gabinete{q}")
        cel = re.findall(r'<td class="col-md-2">\s*(De [^<]*)</td>', h)
        grp = re.findall(r'<td class="alinhar-esquerda col-md-2">\s*([^<]*)</td>', h)
        print(len(cel), Counter(grp), [c for c in cel if not re.search(r" a \d", c)][:5], cel[-3:])
        print(re.findall(r'<select[^>]*ano[^>]*>.*?</select>', h, re.S)[:1])
        i = h.find("pessoal-gabinete")
        print(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h[h.find("<main"):h.find("<table")]))[-800:])
sen = json.loads(get("https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores") or "[]")
print(type(sen), len(sen), json.dumps(sen[:2] if isinstance(sen, list) else sen, ensure_ascii=False)[:1500])
lot = json.loads(get("https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/lotacoes") or "[]")
print(len(lot), json.dumps(lot[:3], ensure_ascii=False)[:1500])
at = json.loads(get("https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/servidores/ativos") or "[]")
print(len(at), sorted({k for x in at for k in x}), Counter(x.get("situacao") for x in at), Counter(x.get("vinculo") for x in at))
g = Counter((x.get("lotacao") or {}).get("nome") for x in at)
print([(k, v) for k, v in g.most_common() if k and re.search("Senador", k)][:60])
print("total em gabinete/escritorio de senador:", sum(v for k, v in g.items() if k and re.search("Senador", k)))
