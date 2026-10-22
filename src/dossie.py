"""Dossie por pessoa: periodos de alerta + noticias do Google Noticias e das fontes sugeridas (RSS, sem chave).
So entram noticias que citam a pessoa (nome de urna, nome civil ou primeiro+ultimo nome) ou uma
empresa ligada a ela (extraida da descricao dos bens declarados ao TSE) no titulo, no resumo do RSS
ou, para itens de fontes sugeridas com busca, no texto da materia. Ainda pode haver homonimos.
Guarda so titulo/veiculo/data/link, nunca o texto da materia."""
import html, math, re, sys, time, unicodedata, urllib.parse, urllib.request
import datetime as dt
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from pathlib import Path

TPL = Path(__file__).resolve().parent / "dossie.html"
RSS = "https://news.google.com/rss/search?"
BUSCA = "https://news.google.com/search?"
LOCAL = {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
UA = "Mozilla/5.0 (compatible; alerta-patrimonial/1.0)"
UA_NAV = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0 Safari/537.36")
MAX_ITENS = 15         # itens lidos por busca RSS
MAX_LISTA = 15         # noticias exibidas por secao
MAX_FALHAS = 5         # falhas seguidas numa fonte: para de buscar nela (provavel bloqueio/limite)
MAX_EMPRESAS = 5       # empresas exibidas por pessoa
MAX_BUSCA_EMP = 3      # empresas pesquisadas por pessoa
MAX_PAGINA = 2_000_000  # bytes lidos de cada materia
FALHA = "Fonte não encontrada: as fontes de notícias não responderam nesta execução."
SEM_TEMPO = "Não informado: busca não realizada nesta execução (limite de tempo)."
TEMAS = '(patrimônio OR investigação OR denúncia OR TCU OR "Polícia Federal" OR "Ministério Público")'
NV = {"forte": "Forte", "atencao": "Atenção", "informativo": "Informativo"}
ONDE = {"titulo": "no título", "resumo": "no resumo", "texto": "no texto"}
CARGOS = {"DEPUTADO": "deputado OR deputada", "SENADOR": "senador OR senadora",
          "GOVERNADOR": "governador OR governadora", "PREFEITO": "prefeito OR prefeita",
          "VEREADOR": "vereador OR vereadora", "PRESIDENTE": "presidente"}
UFS = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
       "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
       "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
       "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
       "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
       "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins"}
FINAIS = {"junior", "jr", "filho", "neto", "sobrinho", "segundo", "terceiro"}
e = html.escape


def ascii_(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()


def chave(s):
    """Minusculas, sem acento, so letras/digitos separados por um espaco (para comparar nomes)."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_(s).lower()).split())


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", ascii_(s).lower()).strip("-")[:80].strip("-") or "pessoa"


def nulo(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def brl(v):
    return "Não informado" if nulo(v) else "R$ " + f"{v:,.0f}".replace(",", ".")


def url_ok(u):
    return isinstance(u, str) and u.startswith(("https://", "http://"))


def sem_tags(s):
    s = re.sub(r"(?s)<[^>]+>", " ", s or "")
    s = re.sub(r"(?s)<[^>]+>", " ", html.unescape(s))  # descricoes com HTML escapado
    return " ".join(s.split())


# ---------------------------------------------------------------- empresas (bens do TSE)
RE_PART = re.compile(r"\b(?:QUOTAS?|COTAS?|ACOES|ACAO|PARTICIPACAO|PARTICIPACOES|QUINHOES|QUINHAO|CAPITAL)\b")
RE_SOCIET = re.compile(r"\b(?:QUOTAS?|COTAS?|PARTICIPACAO|PARTICIPACOES|QUINHOES|QUINHAO|CAPITAL SOCIAL)\b")
RE_EXCL = re.compile(r"\b(?:FUNDOS?|CONSORCIOS?|PREVIDENCIA|PREVIDENCIARI\w*|CAPITALIZACAO|POUPANCA|CDB|LCI|LCA"
                     r"|DEBENTURES?|TESOURO|CLUBE|CLUBES|LINHA TELEFONICA|LINHAS TELEFONICAS)\b")
RE_BOLSA = re.compile(r"\b(?:BOLSA|BOVESPA|B3|PN|ON|PNA|PNB|UNIT|UNITS|CORRETORA|CUSTODIA|ACOES ORDINARIAS"
                      r"|ACOES PREFERENCIAIS)\b")
RE_CNPJ = re.compile(r"\d{2}\.?\d{3}\.?\d{3}\s*/?\s*\d{4}\s*-?\s*\d{2}")
RE_SUF = re.compile(r"\b(LTDA|LIMITADA|SA|EIRELI|EPP|ME)\b")
RE_ANCORA = re.compile(r"\b(?:EMPRESAS?|DENOMINADAS?|DENOMINADOS?|FIRMA|RAZAO SOCIAL)\b")
RE_PARAR = re.compile(r"\b(?:CNPJ|CPF|INSCRITAS?|INSCRITOS?|SITUADAS?|SITUADOS?|SEDIADAS?|SEDIADOS?|LOCALIZADAS?"
                      r"|LOCALIZADOS?|COM SEDE|VALOR|CORRESPONDENTES?|REFERENTES?|EQUIVALENTES?|TOTALIZANDO"
                      r"|SENDO|CONFORME|INTEGRALIZAD\w*|SUBSCRIT\w*|ADQUIRID\w*|RECEBID\w*|DOAD\w*|HERDAD\w*)\b")
SUFIXOS = {"LTDA": "LTDA", "LIMITADA": "LTDA", "SA": "S.A.", "EIRELI": "EIRELI", "EPP": "EPP", "ME": "ME"}
RE_SUF_FIM = re.compile(r"(?:\s+(?:LTDA|S\.A\.|EIRELI|EPP|ME))+$")
CONECTIVOS = set("DE DA DO DAS DOS E EM NA NO NAS NOS A O AS OS &".split())
PREFIXO = CONECTIVOS | set("""QUOTA QUOTAS COTA COTAS ACAO ACOES ORDINARIA ORDINARIAS PREFERENCIAL PREFERENCIAIS
    NOMINATIVA NOMINATIVAS SOCIAL SOCIAIS CAPITAL PARTICIPACAO PARTICIPACOES SOCIETARIA SOCIETARIAS SOCIO SOCIA
    SOCIOS EMPRESA EMPRESAS FIRMA DENOMINADA DENOMINADO RAZAO SOCIEDADE UM UMA PERCENTUAL POR CENTO PCT PORCENTO
    TOTAL TOTALIDADE PARTE INTEGRALIZADAS INTEGRALIZADA INTEGRALIZADO INTEGRALIZADOS SUBSCRITAS NOMINAL REAIS
    CADA MIL QUINHOES QUINHAO OU REFERENTE REFERENTES CORRESPONDENTE CORRESPONDENTES EQUIVALENTE SEU SUA
    MINHA MEU""".split())
GENERICOS = set("""COMERCIO COMERCIAL SERVICOS SERVICO INDUSTRIA INDUSTRIAL INDUSTRIAS PARTICIPACOES EMPREENDIMENTOS
    EMPREENDIMENTO AGROPECUARIA AGROPECUARIO AGRICOLA PECUARIA CONSTRUTORA CONSTRUCOES CONSTRUCAO INCORPORADORA
    INCORPORACOES IMOBILIARIA IMOBILIARIO IMOVEIS HOLDING CIA COMPANHIA GRUPO TRANSPORTES TRANSPORTE
    DISTRIBUIDORA DISTRIBUICAO REPRESENTACOES REPRESENTACAO ADMINISTRACAO ADMINISTRADORA CONSULTORIA ASSESSORIA
    EMPRESA SOCIEDADE NEGOCIOS INVESTIMENTOS MINERACAO ENGENHARIA SOLUCOES TECNOLOGIA MATERIAIS PRODUTOS
    ALIMENTOS EVENTOS LOCACAO LOCACOES MARKETING PUBLICIDADE COMUNICACAO SAUDE MEDICOS MEDICA CLINICA
    ODONTOLOGIA ADVOGADOS ADVOCACIA EDUCACAO ENSINO BRASIL BRASILEIRA NACIONAL""".split())
BLOQ = set("""BANCO BANK SICREDI SICOOB UNIMED COOPERATIVA COOPERATIVAS COOP CRESOL UNICRED TELEFONICA TELEMAR
    TELEBRAS EMBRATEL TELESP TELERJ TELEMIG PETROBRAS ELETROBRAS ITAU ITAUSA BRADESCO BRADESPAR SANTANDER AMBEV
    CEMIG COPEL SABESP GERDAU USIMINAS CAIXA CONSORCIO FUNDO CLUBE ASSOCIACAO SINDICATO""".split())
BLOQ_FRASES = ("PETROLEO BRASILEIRO", "VALE DO RIO DOCE", "CENTRAIS ELETRICAS")


def _limpar(seg):
    ws = seg.split()
    while ws and ws[0] in PREFIXO:
        ws.pop(0)
    while ws and ws[-1] in CONECTIVOS:
        ws.pop()
    if not ws or len(ws) > 10:
        return None
    if sum(1 for w in ws if len(w) >= 2 and w not in CONECTIVOS and w not in GENERICOS) < 2:
        return None  # generico/curto demais ("COMERCIO E SERVICOS", "J R COMERCIO")
    nome = " ".join(ws)
    if any(w in BLOQ for w in ws) or any(f in nome for f in BLOQ_FRASES):
        return None  # bancos, cooperativas, grandes estatais/listadas: noticias sem relacao com a pessoa
    return nome


def empresas_do_bem(desc, tipo=""):
    """Nomes de empresas citados na descricao de um bem de participacao societaria (quotas, acoes,
    capital social). Heuristica: o nome fica antes do sufixo (LTDA, S.A., EIRELI, ME, EPP) e depois de
    palavras como EMPRESA/DENOMINADA; sem sufixo, so aceita depois de EMPRESA/DENOMINADA.
    CNPJ e numeros sao removidos. Ex.: 'QUOTAS DA EMPRESA AGROPECUARIA BOA VISTA LTDA' ->
    ['AGROPECUARIA BOA VISTA LTDA']."""
    s = ascii_(desc).upper()
    # tipo sem parenteses: "Acoes (inclusive as provenientes de linha telefonica)" -> "Acoes"
    tudo = re.sub(r"\(.*?\)", " ", ascii_(tipo).upper()) + " " + s
    tudo = " ".join(re.sub(r"[^A-Z]+", " ", tudo).split())
    if not RE_PART.search(tudo) or RE_EXCL.search(tudo):
        return []
    so_acoes = not RE_SOCIET.search(tudo)  # "acoes" soltas costumam ser papeis de bolsa
    s = RE_CNPJ.sub(" ", s)
    s = re.sub(r"\bS\s*[/.]\s*A\b\.?", " SA ", s)
    s = " ".join(re.sub(r"[^A-Z&]+", " ", s).split())
    if so_acoes and RE_BOLSA.search(s):
        return []
    nomes, ini = [], 0
    for m in RE_SUF.finditer(s):
        seg, ini = s[ini:m.start()], m.end()
        anc = list(RE_ANCORA.finditer(seg))
        cortes = anc + list(RE_PARAR.finditer(seg))
        if cortes:
            seg = seg[max(c.end() for c in cortes):]
        nome = _limpar(seg)
        if nome and (anc or not so_acoes):
            nomes.append(f"{nome} {SUFIXOS[m.group(1)]}")
    if not nomes:
        m = RE_ANCORA.search(s)  # sem sufixo: "QUOTAS DA EMPRESA BOA VISTA AGROPECUARIA"
        if m:
            seg = s[m.end():]
            p = RE_PARAR.search(seg)
            nome = _limpar(seg[:p.start()] if p else seg)
            if nome:
                nomes.append(nome)
    return list(dict.fromkeys(nomes))


def base_empresa(nome):
    """Nome sem o sufixo societario (para a busca e para a verificacao de mencao)."""
    return RE_SUF_FIM.sub("", str(nome or "").strip()).strip()


# ---------------------------------------------------------------- nomes / mencoes
def nomes_pessoa(p):
    """Variantes aceitas como mencao: nome de urna, nome civil completo, primeiro+ultimo nome civil."""
    civil, urna = chave(p.get("nome")), chave(p.get("nome_urna"))
    vs = [urna] if len(urna) >= 4 else []
    vs.append(civil)
    ws = civil.split()
    if len(ws) >= 3:
        fim = ws[-2:] if ws[-1] in FINAIS else ws[-1:]  # "Joao ... Silva Junior" -> "joao silva junior"
        vs.append(" ".join([ws[0], *fim]))
    return [v for v in dict.fromkeys(vs) if v]


def achados(texto, alvos):
    """Indices dos alvos citados no texto (sem acento/caixa, com limite de palavra)."""
    t = f" {chave(texto)} "
    return {i for i, a in enumerate(alvos) if f" {a[0]} " in t}


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


def verificavel(link):
    host = urllib.parse.urlsplit(link).netloc.lower() if url_ok(link) else ""
    return bool(host) and not host.endswith("news.google.com")


def itens_rss(xml, real, max_itens=MAX_ITENS):
    """`real`: link leva a materia (pode ser lida)."""
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError:  # prefixo de namespace sem declaracao: troca "News:Source" por "News_Source"
        raiz = ET.fromstring(re.sub(rb"<(/?)([A-Za-z]+):", rb"<\1\2_", xml))
    itens, vistos = [], set()
    for it in raiz.iter("item"):
        link = (it.findtext("link") or "").strip() or (it.findtext("guid") or "").strip()
        if not url_ok(link) or link in vistos:
            continue
        vistos.add(link)
        veiculo = ""
        for c in it:  # Google: <source>; outros feeds podem usar namespace (<x:source>)
            t = str(c.tag).rsplit("}", 1)[-1].lower()
            if t == "source" or t.endswith("_source"):
                veiculo = " ".join((c.text or "").split())
                break
        titulo = sem_tags(it.findtext("title"))
        if veiculo and titulo.endswith(" - " + veiculo):  # Google anexa " - Veiculo" ao titulo
            titulo = titulo[: -len(veiculo) - 3]
        itens.append(dict(titulo=titulo, resumo=sem_tags(it.findtext("description")), veiculo=veiculo,
                          data=data_pub(it.findtext("pubDate")), link=link, real=real))
        if len(itens) >= max_itens:  # RSS vem por relevancia: pega os mais relevantes
            break
    return itens


class Fonte:
    """Uma fonte RSS com fila propria (1 thread): pausa entre buscas, tolerancia a falhas e prazo."""

    def __init__(self, nome, base, params, ua, pausa, timeout, fim, modelo=None, uf="", max_itens=MAX_ITENS):
        """`modelo`: URL de fonte sugerida, com {q} no lugar da busca (sem {q} = feed geral do veiculo)."""
        self.nome, self.base, self.params, self.ua = nome, base, params, ua
        self.pausa, self.timeout, self.fim = pausa, timeout, fim
        self.modelo, self.uf, self.max_itens = modelo, uf, max_itens
        # Google: link e redirecionamento; feed geral traz de tudo: so mencao no titulo/resumo, sem abrir a materia
        self.real = modelo is not None and "{q}" in modelo
        self.ultimo, self.req, self.falhas, self.seguidas = None, 0, 0, 0
        self.pool = ThreadPoolExecutor(max_workers=1)

    def submeter(self, q):
        return self.pool.submit(self._buscar, q)

    def _buscar(self, q):
        if self.seguidas >= MAX_FALHAS:
            return FALHA
        if time.monotonic() > self.fim:
            return SEM_TEMPO
        if self.ultimo is not None:
            espera = self.pausa - (time.monotonic() - self.ultimo)
            if espera > 0:
                time.sleep(espera)
        self.ultimo = time.monotonic()
        self.req += 1
        if self.modelo is not None:
            url = self.modelo.replace("{q}", urllib.parse.quote_plus(q))
        else:
            url = self.base + urllib.parse.urlencode({"q": q, **self.params})
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept-Language": "pt-BR,pt;q=0.9"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                xml = r.read(5_000_000)
            itens = itens_rss(xml, self.real, self.max_itens)
            self.seguidas = 0
            return itens
        except Exception as ex:
            self.falhas += 1
            self.seguidas += 1
            print(f"[aviso] {self.nome} falhou ({ex})", file=sys.stderr)
            if self.seguidas == MAX_FALHAS:
                print(f"[aviso] {self.nome}: muitas falhas seguidas, buscas restantes nesta fonte canceladas",
                      file=sys.stderr)
            return FALHA


def texto_pagina(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA_NAV, "Accept-Language": "pt-BR,pt;q=0.9",
                                               "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        tipo = (r.headers.get("Content-Type") or "").lower()
        if tipo and "html" not in tipo and "text" not in tipo:
            return ""
        bruto = r.read(MAX_PAGINA)
        cs = r.headers.get_content_charset()
    if not cs:
        m = re.search(rb"""charset=["']?([A-Za-z0-9_.:-]+)""", bruto[:8192])
        cs = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    try:
        s = bruto.decode(cs, errors="replace")
    except LookupError:
        s = bruto.decode("utf-8", errors="replace")
    s = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1\s*>", " ", s)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return html.unescape(s)


def verificar(url, alvos, fim, timeout=10):
    """Alvos citados no texto da materia, ou None se nao deu para ler (ou acabou o prazo)."""
    if time.monotonic() > fim:
        return None
    try:
        return achados(texto_pagina(url, timeout), alvos)
    except Exception:
        return None


def esperar(fut, limite):
    if fut is None:
        return set()
    try:
        return fut.result(timeout=max(0.0, limite - time.monotonic())) or set()
    except Exception:
        return set()


def preparar(p, paginas, fim, max_verif):
    """Junta as fontes de cada secao, deduplica (URL real e titulo), marca mencoes no titulo/resumo e
    agenda a leitura da materia (so fontes sugeridas com busca) quando o nome nao aparece em nenhum dos dois."""
    alvos = p["alvos"]
    rel_emp = {i for i, a in enumerate(alvos) if a[1] == "empresa" and a[2] < MAX_BUSCA_EMP}
    rel_todos = set(range(len(alvos)))
    futs, vistos = {}, {"pes": set(), "emp": set()}
    p["cands"] = {}
    for s in ("pat", "rec", "emp"):
        if s not in p["fut"]:
            continue
        res = []
        for f in p["fut"][s]:
            try:
                res.append(f.result(timeout=max(0.0, fim - time.monotonic()) + 120))
            except Exception:
                res.append(FALHA)
        listas = [r for r in res if isinstance(r, list)]
        if not listas:
            p["cands"][s] = next((r for r in res if isinstance(r, str)), FALHA)
            continue
        rel = rel_emp if s == "emp" else rel_todos
        vis = vistos["emp" if s == "emp" else "pes"]
        cands = []
        for it in (x for lst in listas for x in lst):  # Google primeiro, depois as fontes sugeridas
            kt = chave(it["titulo"])
            if it["link"] in vis or (kt and kt in vis):
                continue
            vis.add(it["link"])
            if kt:
                vis.add(kt)
            c = dict(it, mt=achados(it["titulo"], alvos), md=achados(it["resumo"], alvos), fut=None)
            if not ((c["mt"] | c["md"]) & rel) and it["real"] and verificavel(it["link"]):
                if it["link"] in futs:
                    c["fut"] = futs[it["link"]]
                elif len(futs) < max_verif:
                    c["fut"] = futs[it["link"]] = paginas.submit(verificar, it["link"], alvos, fim)
            cands.append(c)
        p["cands"][s] = cands
    p["verif"] = len(futs)


def _saida(c, onde, quem):
    return dict(titulo=c["titulo"], veiculo=c["veiculo"], data=c["data"], link=c["link"], onde=onde, quem=quem)


def _ordenar(nts):
    return sorted(nts, key=lambda n: n["data"] or dt.date.min, reverse=True)[:MAX_LISTA]


def resolver(p, limite):
    """Aplica o filtro de mencao direta e devolve so titulo/veiculo/data/link + onde/quem."""
    alvos, out = p["alvos"], {}
    for s, cands in p["cands"].items():
        if isinstance(cands, str):
            out[s] = cands
            continue
        for c in cands:
            c["mx"] = esperar(c["fut"], limite)
        if s == "emp":
            por = {}
            for i, a in enumerate(alvos):
                if a[1] != "empresa" or a[2] >= MAX_BUSCA_EMP:
                    continue
                nts = []
                for c in cands:
                    onde = next((o for o, m in (("titulo", c["mt"]), ("resumo", c["md"]), ("texto", c["mx"]))
                                 if i in m), None)
                    if onde:
                        nts.append(_saida(c, onde, "cita a empresa"))
                por[a[2]] = _ordenar(nts)
            out[s] = por
        else:
            nts = []
            for c in cands:
                for onde, m in (("titulo", c["mt"]), ("resumo", c["md"]), ("texto", c["mx"])):
                    if m:
                        nts.append(_saida(c, onde, alvos[min(m)][3]))  # pessoa tem prioridade (vem primeiro)
                        break
            out[s] = _ordenar(nts)
    p["res"] = out


# ---------------------------------------------------------------- pagina
def lista(nts, vazio):
    if isinstance(nts, str):
        return f'<p class="vazio">{e(nts)}</p>'
    if not nts:
        return f'<p class="vazio">{e(vazio)}</p>'
    li = []
    for n in nts:
        meta = " · ".join(x for x in (e(n["veiculo"]), n["data"].strftime("%d/%m/%Y") if n["data"] else "") if x)
        tags = " ".join(f'<span class="tag">{e(t)}</span>' for t in (ONDE.get(n.get("onde"), ""), n.get("quem")) if t)
        rodape = " ".join(x for x in (f"<small>{meta}</small>" if meta else "", tags) if x)
        li.append(f'<li><a href="{e(n["link"])}" target="_blank" rel="noopener">{e(n["titulo"] or n["link"])}</a>'
                  f'{"<br>" + rodape if rodape else ""}</li>')
    return '<ul class="nt">' + "".join(li) + "</ul>"


def bloco_empresas(empresas):
    if not empresas:
        return '<p class="vazio">Nenhuma empresa identificada na descrição dos bens declarados ao TSE.</p>'
    return "".join(f"<h3>{e(nome)}</h3>" + lista(nts, "Nenhuma notícia que cite a empresa.")
                   for nome, nts in empresas)


def periodo(a):
    rz = "Não informado" if nulo(a.get("razao")) else f"{a['razao']:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".") + "×"
    p = a.get("percentil")
    pc = ("Não informado" if nulo(p) else "o maior<br><small>do grupo</small>" if p >= 99.5
          else f"acima de {p:.0f}%<br><small>dos colegas</small>")  # mesmo texto do painel
    nv = a.get("nivel") or ""
    novo = ' <span class="novo">novo</span>' if a.get("novo") else ""
    return (f"<tr><td>{a['ano_ini']}–{a['ano_fim']}{novo}<br><small>{e(a.get('cargo') or '')}</small></td>"
            f'<td class="n">{brl(a.get("pat_ini"))}</td><td class="n">{brl(a.get("pat_fim"))}</td>'
            f'<td class="n">{brl(a.get("cresc"))}</td><td class="n">{brl(a.get("cap"))}</td>'
            f'<td class="n">{rz}</td><td class="n">{pc}</td><td class="nivel {e(nv)}">{e(NV.get(nv, nv))}</td></tr>')


def pagina(tpl, linhas, q, recentes, patrimonio, empresas, gerado, transp=""):
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
    nome = urna or str(ult["nome"])
    vals = dict(TITULO=e(nome), NOME=e(nome), CABECALHO=cab, PERIODOS="".join(periodo(a) for a in linhas),
                RECENTES=lista(recentes, "Nenhuma notícia recente que cite a pessoa ou empresa ligada pelo nome."),
                PATRIMONIO=lista(patrimonio, "Nenhuma notícia sobre patrimônio ou investigações que cite a pessoa "
                                             "ou empresa ligada pelo nome."),
                EMPRESAS=bloco_empresas(empresas), QUERY=e(q), TRANSPARENCIA=transp,  # html ja escapado (transparencia.secao)
                BUSCA=e(BUSCA + urllib.parse.urlencode({"q": q, **LOCAL})), GERADO=e(gerado))
    # passada unica: texto externo ja inserido nunca e reprocessado
    return re.sub(r"__([A-Z]+)__", lambda m: vals.get(m.group(1), m.group(0)), tpl)


# ---------------------------------------------------------------- entrada
def gerar_dossies(alertas, destino, max_pessoas=200, buscar=True, pausa=0.5, timeout=20,
                  tempo_max=12 * 60, max_verif=20, workers=12, fontes_extra=(), transparencia=None):
    """Gera destino/dossie/<slug>.html por pessoa (nome+UF) e devolve {indice_da_linha: "dossie/<slug>.html"}.
    Noticias so para as primeiras max_pessoas (ordem de `alertas`); as demais saem sem busca automatica.
    As buscas RSS correm numa fila por fonte (Google e fontes sugeridas em paralelo, `pausa` s entre buscas na mesma
    fonte) e a leitura das materias num pool de `workers` threads; nada novo comeca apos `tempo_max` s."""
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

    pessoas = []
    for n, (k, idx) in enumerate(grupos.items()):
        linhas = sorted((alertas[i] for i in idx), key=lambda a: (a.get("ano_ini") or 0, a.get("ano_fim") or 0))
        ult = linhas[-1]
        v = ult.get("empresas")
        emps = [str(x).strip() for x in (v if isinstance(v, (list, tuple)) else []) if chave(base_empresa(x))]
        emps = list(dict.fromkeys(emps))[:MAX_EMPRESAS]
        alvos = [(x, "pessoa", None, "cita a pessoa") for x in nomes_pessoa(ult)]
        alvos += [(chave(base_empresa(x)), "empresa", j, f"cita {x}") for j, x in enumerate(emps)]
        pessoas.append(dict(n=n, k=k, idx=idx, linhas=linhas, q=query(ult), emps=emps, alvos=alvos))

    fontes, verif = [], 0
    if buscar:
        fim = time.monotonic() + tempo_max
        ativos = [p for p in pessoas if p["n"] < max_pessoas]
        fontes = [Fonte("Google Notícias", RSS, LOCAL, UA, pausa, timeout, fim)]
        # fontes sugeridas pelo site (config/fontes_noticias.csv): com {q} = busca no veiculo; sem = feed geral
        extras = [Fonte(x["nome"], None, None, UA_NAV, pausa, timeout, fim, modelo=x["feed"],
                        uf=(x.get("uf") or "").upper(), max_itens=MAX_ITENS if "{q}" in x["feed"] else 200)
                  for x in fontes_extra]
        gerais = {f: f.submeter("") for f in extras if "{q}" not in f.modelo}  # uma leitura por execucao
        fontes += extras
        paginas = ThreadPoolExecutor(max_workers=workers)
        try:
            for p in ativos:  # enfileira todas as buscas; cada fonte atende na ordem do painel
                cons = {"pat": f"{p['q']} {TEMAS}", "rec": p["q"]}
                if p["emps"]:
                    cons["emp"] = " OR ".join(f'"{base_empresa(x).title()}"' for x in p["emps"][:MAX_BUSCA_EMP])
                p["fut"] = {s: [f.submeter(q) for f in fontes] for s, q in cons.items()}
                uf = p["k"][1]
                termo = " ".join((p["linhas"][-1].get("nome_urna") or p["linhas"][-1]["nome"]).split())
                for f in extras:
                    if f.uf and f.uf != uf:
                        continue
                    p["fut"]["rec"].append(gerais[f] if f in gerais else f.submeter(termo))
            print(f"Noticias: buscando para {len(ativos)} pessoas...")
            for n, p in enumerate(ativos, 1):  # conforme as buscas chegam, agenda a leitura das materias
                if n % 20 == 0:
                    print(f"  {n}/{len(ativos)} pessoas")
                preparar(p, paginas, fim, max_verif)
                verif += p["verif"]
            for p in ativos:
                resolver(p, fim + 30)
        except Exception as ex:  # nunca derruba o painel por causa das noticias
            print(f"[aviso] busca de noticias interrompida ({ex!r})", file=sys.stderr)
        finally:
            paginas.shutdown(wait=False, cancel_futures=True)
            for f in fontes:
                f.pool.shutdown(wait=False, cancel_futures=True)

    usados, indice = set(), {}
    for p in pessoas:
        if not buscar:
            msg = "Busca de notícias desativada nesta execução."
        elif p["n"] >= max_pessoas:
            msg = "Busca automática não realizada nesta execução (limite de pessoas)."
        else:
            msg = None
        res = p.get("res") or {}
        rec = msg or res.get("rec", FALHA)
        pat = msg or res.get("pat", FALHA)
        emp_r = res.get("emp", FALHA)
        empresas = []
        for j, nome in enumerate(p["emps"]):
            if msg:
                nts = msg
            elif j >= MAX_BUSCA_EMP:
                nts = f"Busca não realizada para esta empresa (limite de {MAX_BUSCA_EMP} por pessoa)."
            elif isinstance(emp_r, dict):
                nts = emp_r.get(j, [])
            else:
                nts = emp_r if isinstance(emp_r, str) else FALHA
            empresas.append((nome, nts))
        k = p["k"]
        s = base = slug(f"{k[0]} {k[1]}")
        c = 2
        while s in usados:
            s, c = f"{base}-{c}", c + 1
        usados.add(s)
        transp = next((transparencia[i] for i in p["idx"] if i in (transparencia or {})),
                      '<p class="vazio">Consulta ao Portal da Transparência não realizada nesta execução.</p>')
        (pasta / f"{s}.html").write_text(pagina(tpl, p["linhas"], p["q"], rec, pat, empresas, gerado, transp),
                                         encoding="utf-8")
        for i in p["idx"]:
            indice[i] = f"dossie/{s}.html"
    st = ", ".join(f"{f.nome}: {f.req} buscas/{f.falhas} falhas" for f in fontes) or "sem buscas"
    print(f"Dossies: {len(pessoas)} pessoas; {st}; {verif} materias verificadas.")
    return indice
