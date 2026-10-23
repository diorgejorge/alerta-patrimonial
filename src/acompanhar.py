"""Acompanhar (#57): feed RSS por pessoa (docs/feed/<id>.xml) e um geral (docs/feed.xml), com um item quando um dado
muda entre execucoes (patrimonio, nivel, cota, noticias, marcacoes). A foto anterior dos dados fica cifrada em
data/acompanhar.json (cifra.py). So o id interno (pNNNN) sai daqui: CPF/CNPJ nunca entram no feed nem na URL."""
import datetime as dt
import hashlib, html, json, os, re
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
import cifra, graficos
from texto import cap

ITENS_POR_PESSOA = 20  # guardados e publicados no feed de cada pessoa
ITENS_GERAL = 50
NOTICIAS_POR_VEZ = 5  # noticias novas que viram item em uma execucao (o resto fica na pagina)
NOTICIAS_GUARDADAS = 200  # links ja vistos, para nao repetir item
PRESENCA_QUEDA = 5  # pontos percentuais de queda na presenca registrada que viram aviso
VOTOS_POR_VEZ = 5
COTA_MINIMA = 1000  # variacao da cota (R$) que vira aviso; abaixo disso e so o gasto do mes andando
SITE_PADRAO = "https://diorgejorge.github.io/alerta-patrimonial/"
RE_PID = re.compile(r"p\d+")
RE_UF = re.compile(r"[A-Z]{2}")
ORDEM_NIVEL = {"forte": 3, "atencao": 2, "informativo": 1}
e = html.escape


def site():
    """Endereco publico do site (links absolutos no feed): o repositorio do Actions ou o padrao."""
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if re.fullmatch(r"[\w-]+/[\w.-]+", repo):
        dono, nome = repo.split("/")
        return f"https://{dono.lower()}.github.io/{nome}/"
    return SITE_PADRAO


def url_feed(pid):
    return f"{site()}feed/{pid}.xml"


def brl(v):
    return "Não informado" if v is None else "R$ " + f"{v:,.0f}".replace(",", ".")


ICONE = ('<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor">'
         '<circle cx="3" cy="13" r="2"/><path d="M1 7.5a7.5 7.5 0 0 1 7.5 7.5h-2A5.5 5.5 0 0 0 1 9.5z"/>'
         '<path d="M1 2a13 13 0 0 1 13 13h-2A11 11 0 0 0 1 4z"/></svg>')


APPS = (("Feedly", "https://feedly.com/i/subscription/feed%2F{}"),
        ("Inoreader", "https://www.inoreader.com/?add_feed={}"))


def links_app(url):
    """Um toque e o feed ja entra no leitor: link de inscricao de cada app e o feed: (app instalado no aparelho)."""
    q = quote(url, safe="")
    return [(nome, modelo.format(q)) for nome, modelo in APPS] + [("Outro app", "feed:" + url)]


def botao(pid, uf=""):
    """Botao discreto "Acompanhar" da pagina da pessoa: um toque no app de RSS e pronto, sem copiar endereco."""
    apps = links_app(url_feed(pid))
    extra = (f' · <a href="{e(site())}feed/uf-{uf}.xml">Todos de {uf}</a>' if RE_UF.fullmatch(uf) else "")
    return (f'<details class="acompanhar"><summary class="botao secundario">{ICONE}Acompanhar</summary>'
            '<div class="card"><p><b>Não perca nada.</b> Seja avisado quando o patrimônio crescer, a cota subir, '
            "sair um voto ou uma notícia nova. Toque no seu app:</p><p class=\"apps\">"
            + "".join(f'<a class="botao{"" if i == 0 else " secundario"}" href="{e(h)}" target="_blank" rel="noopener">'
                      f"{e(n)}</a>" for i, (n, h) in enumerate(apps))
            + f'</p><p class="mut"><small><a href="{e(url_feed(pid))}">Ver o feed</a>{extra} · '
            f'<a href="{e(site())}feed.xml">Todas as pessoas</a></small></p></div></details>')


def link_head(pid, nome):
    return f'<link rel="alternate" type="application/rss+xml" title="Acompanhar {e(nome)}" href="../feed/{e(pid)}.xml">'


# ---------------------------------------------------------------- foto dos dados e mudancas
def foto(linhas, cota_total=None, noticias=None):
    """O que se compara entre execucoes. `noticias`: lista (busca feita) ou texto/None (busca falhou: None)."""
    ult = max(linhas, key=lambda a: a.get("ano_fim") or 0)
    nv = max((a.get("nivel") for a in linhas if a.get("nivel")), key=ORDEM_NIVEL.get, default=None)
    links = ([n["link"] for n in noticias if str(n.get("link") or "").startswith("https://")]
             if isinstance(noticias, list) else None)
    tse = next((a["link_tse"] for a in linhas if str(a.get("link_tse") or "").startswith("https://")), None)
    return dict(nome=cap((ult.get("nome_urna") or ult.get("nome") or "").strip()), uf=str(ult.get("uf") or "").upper(),
                pat=ult.get("pat_fim"),
                ano=ult.get("ano_fim"), nivel=nv, cota=None if cota_total is None else round(cota_total),
                exemplar=any(a.get("exemplar") for a in linhas), selo=any(a.get("selo") for a in linhas),
                noticias=links, tse=tse, presenca=_presenca(linhas), votos=_votos(linhas))


def _presenca(linhas):
    """% de presenca registrada (thread Votacoes e presenca: alertas[i]["presenca"]["pct"]); None sem o dado."""
    pct = next((a["presenca"].get("pct") for a in linhas if isinstance(a.get("presenca"), dict)), None)
    return None if pct is None else round(float(pct), 1)


def _votos(linhas):
    """Votos nominais por id estavel (alertas[i]["votos"]); None quando a pessoa nao tem a lista."""
    vs = next((a["votos"] for a in linhas if isinstance(a.get("votos"), list)), None)
    return None if vs is None else {str(v["id"]): dict(tema=v.get("tema"), voto=v.get("voto"), link=v.get("link"))
                                    for v in vs if v.get("id")}


def _item(tipo, titulo, texto, link):
    return dict(tipo=tipo, titulo=titulo, texto=texto, link=link)


def _marca(nome, antes, agora):
    if antes == agora:
        return None
    return (f"Ganhou {nome}" if agora else f"Perdeu {nome}")


def mudancas(antes, agora, pagina, detalhes=None):
    """Itens novos comparando a foto anterior com a atual. Sem foto anterior: um item de boas-vindas.
    Dado que nao veio nesta execucao (None) nunca vira aviso. `detalhes`: {link: noticia} para o texto."""
    nome = agora["nome"]
    if not antes:
        return [_item("inicio", f"Começamos a acompanhar {nome}",
                      f"A partir de hoje você fica sabendo quando algo mudar. Patrimônio declarado agora: {brl(agora['pat'])}"
                      f"{' em ' + str(agora['ano']) if agora.get('ano') else ''}.", pagina)]
    itens = []
    if agora["ano"] != antes.get("ano") or agora["pat"] != antes.get("pat"):
        dif = (agora["pat"] or 0) - (antes.get("pat") or 0)
        itens.append(_item("patrimonio", f"Nova declaração de bens: {brl(agora['pat'])} em {agora['ano']}",
                           f"Antes: {brl(antes.get('pat'))} em {antes.get('ano') or 'Não informado'}. Diferença: "
                           f"{'+' if dif >= 0 else '−'}{brl(abs(dif))}. Confira no TSE.", agora.get("tse") or pagina))
    if agora["nivel"] != antes.get("nivel"):
        rot = lambda n: graficos.ROTULO_NIVEL.get(n, "sem destaque")
        itens.append(_item("nivel", f"Destaque do patrimônio mudou: de “{rot(antes.get('nivel'))}” para "
                                    f"“{rot(agora['nivel'])}”",
                           "Compara quanto o patrimônio cresceu com o que daria para juntar só com o salário.", pagina))
    if agora["cota"] is not None and antes.get("cota") is not None and abs(agora["cota"] - antes["cota"]) >= COTA_MINIMA:
        dif = agora["cota"] - antes["cota"]
        itens.append(_item("cota", f"Cota parlamentar: {'mais' if dif > 0 else 'menos'} {brl(abs(dif))} em gastos",
                           f"Total em 4 anos: {brl(agora['cota'])}. É dinheiro público para passagens, escritório e "
                           "divulgação do mandato.", pagina))
    for chave, rotulo in (("exemplar", "a estrela de Parlamentar exemplar"), ("selo", "o selo Mão na massa")):
        t = _marca(rotulo, bool(antes.get(chave)), agora[chave])
        if t:
            itens.append(_item(chave, t, "Mesmos critérios para todos. Veja o porquê na página.", pagina))
    if agora.get("presenca") is not None and antes.get("presenca") is not None \
            and antes["presenca"] - agora["presenca"] >= PRESENCA_QUEDA:
        itens.append(_item("presenca", f"Presença registrada caiu de {_pct(antes['presenca'])} para "
                                       f"{_pct(agora['presenca'])}",
                           "Sessões com presença registrada. Ausência pode ter justificativa, como licença.", pagina))
    if agora.get("votos") is not None and antes.get("votos") is not None:
        for vid in [v for v in agora["votos"] if v not in antes["votos"]][:VOTOS_POR_VEZ]:
            v = agora["votos"][vid]
            link = v["link"] if str(v.get("link") or "").startswith("https://") else pagina
            itens.append(_item("voto", f"Votou “{v.get('voto') or 'Não informado'}” em: {v.get('tema') or vid}",
                               "Voto registrado pela Câmara ou pelo Senado. Concorda?", link))
    if agora["noticias"] is not None and antes.get("noticias") is not None:
        vistas = set(antes["noticias"])
        for link in [x for x in agora["noticias"] if x not in vistas][:NOTICIAS_POR_VEZ]:
            n = (detalhes or {}).get(link, {})
            meta = " · ".join(x for x in (n.get("veiculo"), _dia(n.get("data"))) if x)
            itens.append(_item("noticia", f"Na imprensa: {n.get('titulo') or link}",
                               f"Notícia nova que cita {nome}{f' ({meta})' if meta else ''}.", link))
    return itens


def _pct(v):
    return f"{v:.0f}%".replace(".", ",")


def _dia(d):
    return d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else (str(d) if d else "")


def juntar(antes, agora):
    """Foto a guardar: dado que nao veio agora fica o anterior; noticias somam os links ja vistos."""
    novo = dict(agora)
    for k in ("cota", "noticias", "presenca", "votos"):
        if novo.get(k) is None:
            novo[k] = (antes or {}).get(k)
    if agora["noticias"] is not None and antes and antes.get("noticias"):
        novo["noticias"] = list(dict.fromkeys(agora["noticias"] + antes["noticias"]))[:NOTICIAS_GUARDADAS]
    return novo


def atualizar(estado, atuais, agora):
    """`estado`: {pid: {foto, itens}} anterior; `atuais`: {pid: (foto, pagina, detalhes)}. Devolve (estado, novos)."""
    quando = agora.isoformat(timespec="seconds")
    novos = []
    for pid, (f, pagina, det) in atuais.items():
        reg = estado.get(pid) or {}
        itens = mudancas(reg.get("foto"), f, pagina, det)
        for it in itens:
            base = f"{pid}|{it['tipo']}|{it['titulo']}|{quando}"
            it.update(id=hashlib.sha256(base.encode()).hexdigest()[:20], data=quando, pessoa=pid, nome=f["nome"])
        novos += itens
        estado[pid] = dict(foto=juntar(reg.get("foto"), f), itens=(itens + reg.get("itens", []))[:ITENS_POR_PESSOA])
    return estado, novos


# ---------------------------------------------------------------- RSS
def rss(titulo, descricao, link, auto, itens, com_nome=False):
    """RSS 2.0 (bytes). Itens ja na ordem (mais novo primeiro)."""
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    r = ET.Element("rss", version="2.0")
    c = ET.SubElement(r, "channel")
    for tag, val in (("title", titulo), ("link", link), ("description", descricao), ("language", "pt-BR")):
        ET.SubElement(c, tag).text = val
    ET.SubElement(c, "{http://www.w3.org/2005/Atom}link", href=auto, rel="self", type="application/rss+xml")
    if itens:
        ET.SubElement(c, "lastBuildDate").text = _rfc822(itens[0]["data"])
    for it in itens:
        i = ET.SubElement(c, "item")
        ET.SubElement(i, "title").text = f"{it['nome']}: {it['titulo']}" if com_nome else it["titulo"]
        ET.SubElement(i, "link").text = it["link"]
        ET.SubElement(i, "description").text = it["texto"]
        ET.SubElement(i, "guid", isPermaLink="false").text = f"cv-{it['id']}"
        ET.SubElement(i, "pubDate").text = _rfc822(it["data"])
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(r, encoding="utf-8")


def _rfc822(iso):
    return format_datetime(dt.datetime.fromisoformat(iso))


def _recentes(itens):
    """Itens de varias pessoas, mais novos primeiro, sem os de boas-vindas (ruido fora do feed da propria pessoa)."""
    return sorted((it for it in itens if it["tipo"] != "inicio"), key=lambda it: it["data"], reverse=True)[:ITENS_GERAL]


def escrever(docs, estado, ativos):
    """docs/feed/<id>.xml de quem tem pagina agora, docs/feed/uf-XX.xml por estado e docs/feed.xml geral.
    Feeds de quem saiu do site sao apagados."""
    pasta = Path(docs) / "feed"
    pasta.mkdir(parents=True, exist_ok=True)
    base = site()
    por_uf, escritos = {}, set()
    for pid in ativos:
        reg = estado[pid]
        nome = reg["foto"]["nome"]
        (pasta / f"{pid}.xml").write_bytes(rss(
            f"{nome} · Caramelo Vasculha", f"Avisos de mudança nos dados públicos de {nome}.",
            f"{base}pessoa/{pid}.html", url_feed(pid), reg["itens"]))
        escritos.add(pid)
        if RE_UF.fullmatch(reg["foto"].get("uf") or ""):
            por_uf.setdefault(reg["foto"]["uf"], []).extend(reg["itens"])
    for uf, itens in por_uf.items():
        (pasta / f"uf-{uf}.xml").write_bytes(rss(
            f"Políticos de {uf} · Caramelo Vasculha", f"Avisos de mudança nos dados públicos dos políticos de {uf}.",
            base, f"{base}feed/uf-{uf}.xml", _recentes(itens), com_nome=True))
        escritos.add(f"uf-{uf}")
    for f in pasta.glob("*.xml"):
        if f.stem not in escritos:
            f.unlink()
    (Path(docs) / "feed.xml").write_bytes(rss(
        "Caramelo Vasculha · todas as pessoas", "Avisos de mudança nos dados públicos dos políticos acompanhados.",
        base, f"{base}feed.xml", _recentes(it for pid in ativos for it in estado[pid]["itens"]), com_nome=True))
    return len(ativos)


def publicar(docs, arq, segredo, alertas, pessoas, cota_por_pessoa, noticias, agora=None):
    """Compara com a execucao anterior, grava a foto nova (cifrada) e escreve os feeds. Devolve (feeds, itens novos)."""
    agora = agora or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    bruto = cifra.ler(arq, segredo)
    try:
        estado = json.loads(bruto) if bruto else {}
    except ValueError:
        estado = {}
    atuais = {}
    for k, q in pessoas.items():
        linhas = [alertas[i] for i in q["idx"]]
        pid = linhas[0].get("pessoa")
        if not pid or not RE_PID.fullmatch(str(pid)):
            continue
        nts = noticias.get(q["idx"][0])
        det = {n["link"]: n for n in nts if n.get("link")} if isinstance(nts, list) else {}
        total = (cota_por_pessoa.get(k) or {}).get("total")
        atuais[pid] = (foto(linhas, total, nts), f"{site()}pessoa/{pid}.html", det)
    estado, novos = atualizar(estado, atuais, agora)
    cifra.gravar(arq, json.dumps(estado, ensure_ascii=False).encode(), segredo)
    return escrever(docs, estado, set(atuais)), novos
