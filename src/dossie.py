"""Dossie por pessoa: periodos de alerta + noticias do Google Noticias (RSS, sem chave).
Noticias sao coletadas por busca de nome e podem se referir a homonimos.
Guarda so titulo/veiculo/data/link, nunca o texto da materia."""
import html, math, re, sys, time, unicodedata, urllib.parse, urllib.request
import datetime as dt
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

TPL = Path(__file__).resolve().parent / "dossie.html"
RSS = "https://news.google.com/rss/search?"
BUSCA = "https://news.google.com/search?"
LOCAL = {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
UA = "Mozilla/5.0 (compatible; alerta-patrimonial/1.0)"
MAX_ITENS = 15
MAX_FALHAS = 5  # falhas seguidas: para de buscar (provavel bloqueio/limite)
TEMAS = '(patrimônio OR investigação OR denúncia OR TCU OR "Polícia Federal" OR "Ministério Público")'
NV = {"forte": "Forte", "atencao": "Atenção", "informativo": "Informativo"}
CARGOS = {"DEPUTADO": "deputado OR deputada", "SENADOR": "senador OR senadora",
          "GOVERNADOR": "governador OR governadora", "PREFEITO": "prefeito OR prefeita",
          "VEREADOR": "vereador OR vereadora", "PRESIDENTE": "presidente"}
UFS = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
       "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
       "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
       "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
       "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
       "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins"}
e = html.escape


def ascii_(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", ascii_(s).lower()).strip("-")[:80].strip("-") or "pessoa"


def nulo(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def brl(v):
    return "—" if nulo(v) else "R$ " + f"{v:,.0f}".replace(",", ".")


def url_ok(u):
    return isinstance(u, str) and u.startswith(("https://", "http://"))


# ---------------------------------------------------------------- busca
def query(p):
    """Nome entre aspas + contexto (cargo e/ou estado) para reduzir homonimos.
    Nome de urna e como a imprensa cita; se for uma palavra so (muito ambiguo),
    exige cargo E estado; senao, cargo OU estado."""
    urna = (p.get("nome_urna") or "").strip()
    termo = " ".join((urna or p["nome"]).split()).title()
    ws = re.findall(r"[A-Z]+", ascii_(p.get("cargo")).upper())
    cargo = next((CARGOS[w] for w in ws if w in CARGOS), None)
    est = UFS.get((p.get("uf") or "").upper())
    est = f'"{est}"' if est else None
    if len(termo.split()) == 1:
        ctx = " ".join(f"({c})" if " OR " in c else c for c in (cargo, est) if c)
    else:
        ctx = " OR ".join(c for c in (cargo, est) if c)
        ctx = f"({ctx})" if ctx else ""
    return f'"{termo}" {ctx}'.strip()


def data_pub(s):
    try:
        return parsedate_to_datetime(s).date()
    except Exception:
        return None


def buscar_rss(q, timeout):
    url = RSS + urllib.parse.urlencode({"q": q, **LOCAL})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raiz = ET.fromstring(r.read(5_000_000))
    itens, vistos = [], set()
    for it in raiz.iter("item"):
        link = (it.findtext("link") or "").strip()
        if not url_ok(link) or link in vistos:
            continue
        vistos.add(link)
        src = it.find("source")
        veiculo = (src.text or "").strip() if src is not None else ""
        titulo = (it.findtext("title") or "").strip()
        if veiculo and titulo.endswith(" - " + veiculo):  # Google anexa " - Veiculo" ao titulo
            titulo = titulo[: -len(veiculo) - 3]
        itens.append(dict(titulo=titulo, veiculo=veiculo, data=data_pub(it.findtext("pubDate")), link=link))
        if len(itens) >= MAX_ITENS:  # RSS vem por relevancia: pega os mais relevantes
            break
    return sorted(itens, key=lambda n: n["data"] or dt.date.min, reverse=True)


# ---------------------------------------------------------------- pagina
def lista(nts):
    if isinstance(nts, str):
        return f'<p class="vazio">{e(nts)}</p>'
    if not nts:
        return '<p class="vazio">Nenhuma notícia encontrada para esta busca.</p>'
    li = []
    for n in nts:
        meta = " · ".join(x for x in (e(n["veiculo"]), n["data"].strftime("%d/%m/%Y") if n["data"] else "") if x)
        li.append(f'<li><a href="{e(n["link"])}" target="_blank" rel="noopener">{e(n["titulo"] or n["link"])}</a>'
                  f'{f"<br><small>{meta}</small>" if meta else ""}</li>')
    return '<ul class="nt">' + "".join(li) + "</ul>"


def periodo(a):
    rz = "—" if nulo(a.get("razao")) else f"{a['razao']:.1f}".replace(".", ",") + "×"
    pc = "—" if nulo(a.get("percentil")) else f"{a['percentil']:.0f}"
    nv = a.get("nivel") or ""
    novo = ' <span class="novo">novo</span>' if a.get("novo") else ""
    return (f"<tr><td>{a['ano_ini']}–{a['ano_fim']}{novo}<br><small>{e(a.get('cargo') or '')}</small></td>"
            f'<td class="n">{brl(a.get("pat_ini"))}</td><td class="n">{brl(a.get("pat_fim"))}</td>'
            f'<td class="n">{brl(a.get("cresc"))}</td><td class="n">{brl(a.get("cap"))}</td>'
            f'<td class="n">{rz}</td><td class="n">{pc}</td><td class="nivel {e(nv)}">{e(NV.get(nv, nv))}</td></tr>')


def pagina(tpl, linhas, q, recentes, patrimonio, gerado):
    ult = linhas[-1]  # periodo mais recente
    urna = (ult.get("nome_urna") or "").strip()
    tse = next((a["link_tse"] for a in reversed(linhas) if url_ok(a.get("link_tse"))), None)
    ficha = " · ".join(e(str(x)) for x in (ult.get("cargo"), ult.get("partido"), ult.get("uf")) if x)
    cab = f"<h1>{e(ult['nome'])}</h1>"
    if urna and urna.upper() != str(ult["nome"]).upper():
        cab += f'<p class="ficha">Nome de urna: <strong>{e(urna)}</strong></p>'
    cab += f'<p class="ficha">{ficha}</p>'
    if tse:
        cab += f'<p class="ficha"><a href="{e(tse)}" target="_blank" rel="noopener">Ver candidatura e bens no TSE</a></p>'
    vals = dict(TITULO=e(urna or ult["nome"]), CABECALHO=cab, PERIODOS="".join(periodo(a) for a in linhas),
                RECENTES=lista(recentes), PATRIMONIO=lista(patrimonio), QUERY=e(q),
                BUSCA=e(BUSCA + urllib.parse.urlencode({"q": q, **LOCAL})), GERADO=e(gerado))
    # passada unica: texto externo ja inserido nunca e reprocessado
    return re.sub(r"__([A-Z]+)__", lambda m: vals.get(m.group(1), m.group(0)), tpl)


# ---------------------------------------------------------------- entrada
def gerar_dossies(alertas, destino, max_pessoas=200, buscar=True, pausa=1.0, timeout=20):
    """Gera destino/dossie/<slug>.html por pessoa (nome+UF) e devolve {indice_da_linha: "dossie/<slug>.html"}.
    Noticias so para as primeiras max_pessoas (ordem de `alertas`); as demais saem sem busca automatica."""
    pasta = Path(destino) / "dossie"
    pasta.mkdir(parents=True, exist_ok=True)
    for f in pasta.glob("*.html"):
        f.unlink()
    tpl = TPL.read_text(encoding="utf-8")
    gerado = dt.datetime.now().strftime("%d/%m/%Y %H:%M")

    grupos = {}  # (nome, uf) -> [indices], na ordem do painel
    for i, a in enumerate(alertas):
        k = (" ".join(ascii_(a.get("nome")).upper().split()), (a.get("uf") or "").upper())
        grupos.setdefault(k, []).append(i)

    indice, usados, st = {}, set(), dict(req=0, falhas=0, seguidas=0)

    def rss(q):
        if st["seguidas"] >= MAX_FALHAS:
            return "Não foi possível buscar notícias agora."
        if st["req"]:
            time.sleep(pausa)
        st["req"] += 1
        try:
            r = buscar_rss(q, timeout)
            st["seguidas"] = 0
            return r
        except Exception as ex:
            st["falhas"] += 1; st["seguidas"] += 1
            print(f"[aviso] Google Noticias falhou ({ex})", file=sys.stderr)
            if st["seguidas"] == MAX_FALHAS:
                print("[aviso] muitas falhas seguidas: dossies restantes sem noticias", file=sys.stderr)
            return "Não foi possível buscar notícias agora."

    for n, (k, idx) in enumerate(grupos.items()):
        linhas = sorted((alertas[i] for i in idx), key=lambda a: (a.get("ano_ini") or 0, a.get("ano_fim") or 0))
        q = query(linhas[-1])
        if not buscar:
            rec = pat = "Busca de notícias desativada nesta execução."
        elif n >= max_pessoas:
            rec = pat = "Busca automática não realizada nesta execução (limite de pessoas)."
        else:
            pat = rss(f"{q} {TEMAS}")
            rec = rss(q)
            if isinstance(rec, list) and isinstance(pat, list):
                vistos = {x["link"] for x in pat}
                rec = [x for x in rec if x["link"] not in vistos]
        s = base = slug(f"{k[0]} {k[1]}")
        c = 2
        while s in usados:
            s, c = f"{base}-{c}", c + 1
        usados.add(s)
        (pasta / f"{s}.html").write_text(pagina(tpl, linhas, q, rec, pat, gerado), encoding="utf-8")
        for i in idx:
            indice[i] = f"dossie/{s}.html"
    print(f"Dossies: {len(grupos)} pessoas, {st['req']} buscas de noticias, {st['falhas']} falhas.")
    return indice
