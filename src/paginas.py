"""Pagina por pessoa (docs/pessoa/<id>.html) e blocos da visao geral (cartoes e graficos SVG).
So usa o id interno (p0001...): CPF, chave e CNPJ nunca entram no HTML."""
import csv, hashlib, html, json, re, shutil
from pathlib import Path
import acompanhar, cobrar, gabinete, graficos, temas
from texto import cap

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
ORDEM = {"forte": 3, "atencao": 2, "informativo": 1}
NUM = ' class="n"'  # colunas numericas (alinhadas a direita)
e = html.escape


def chip_nivel(nv):
    if not nv:
        return ""
    return f'<span class="chip nv-{e(nv)}">{e(graficos.ROTULO_NIVEL.get(nv, nv))}</span>'  # pegadas no CSS (#72)


def iniciais(nome):
    ps = [w for w in re.findall(r"[A-Za-zÀ-ÿ]+", nome or "") if len(w) > 2] or (nome or "?").split()
    return ((ps[0][0] + (ps[-1][0] if len(ps) > 1 else "")) if ps else "?").upper()


def avatar(nome, grande=False, foto=None):
    """Foto oficial da candidatura (TSE) sobre as iniciais; se a foto nao carregar, ficam as iniciais."""
    img = (f'<img src="{e(foto)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">'
           if str(foto or "").startswith("https://") else "")
    return f'<span class="avatar{" g" if grande else ""}" aria-hidden="true">{e(iniciais(nome))}{img}</span>'


FOTO_TSE = "https://divulgacandcontas.tse.jus.br/divulga/rest/arquivo/img"


def foto(linhas):
    """Foto oficial do periodo mais recente; linhas antigas do cache so tem link_tse, entao a foto sai dele."""
    for a in sorted(linhas, key=lambda x: x.get("ano_fim") or 0, reverse=True):
        if str(a.get("link_foto") or "").startswith("https://"):
            return a["link_foto"]
        m = re.search(r"/divulga/#/candidato/[A-Z]+/[A-Z]{2}/(\d+)/(\d+)/\d{4}/(\w+)$", str(a.get("link_tse") or ""))
        if m:
            return f"{FOTO_TSE}/{m[1]}/{m[2]}/{m[3]}"
    return None


def _alt(tabela):
    return f'<details class="alt"><summary>Ver dados em tabela</summary><div class="tab">{tabela}</div></details>'


# ---------------------------------------------------------------- dados das fases seguintes (leitores)
def ler_jsonl(caminho):
    """Linhas de um .jsonl (propostas, noticias...); arquivo ausente ou linha ruim = ignorado."""
    out = []
    try:
        for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(linha))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def ler_vinculos(caminho=ROOT / "config" / "vinculos.csv"):
    """Vinculos proposta x proposicao aprovados manualmente (fase 4): so status 'aprovado' e exibido."""
    try:
        with open(caminho, encoding="utf-8", newline="") as f:
            return [r for r in csv.DictReader(f) if (r.get("status") or "").strip().lower() == "aprovado"]
    except OSError:
        return []


# ---------------------------------------------------------------- pagina da pessoa
def _valor_tse(v, link):
    """Patrimonio declarado em reais, com o link da declaracao do TSE daquele ano quando houver (so no dossie, #62)."""
    txt = graficos.brl(v)
    return f'<a href="{e(link)}" target="_blank" rel="noopener">{txt}</a>' if str(link or "").startswith("https://") else txt


COLUNAS_NUM = {2, 3, 4}


def _tabela_periodos(linhas):
    # o dossie mostra o patrimonio em reais do comeco e do fim (pedido do usuario); no resto do site, so o percentual
    cab = ["Período", "Cargo", "Patrimônio no começo", "Patrimônio no fim", "Aumento do patrimônio",
           "Entre colegas do mesmo cargo", "Faixa"]
    corpo = []
    for a in sorted(linhas, key=lambda a: (a.get("ano_ini") or 0, a.get("ano_fim") or 0)):
        cel = [f'{a.get("ano_ini")}–{a.get("ano_fim")}', e(cap(a.get("cargo"))),
               _valor_tse(a.get("pat_ini"), a.get("link_tse_ini")), _valor_tse(a.get("pat_fim"), a.get("link_tse")),
               graficos.aumento_percentual(a.get("pat_fim"), a.get("pat_ini")),
               graficos.regua_colegas(a), chip_nivel(a.get("nivel"))]
        corpo.append("<tr>" + "".join(f'<td data-label="{e(c)}"{NUM if i in COLUNAS_NUM else ""}>{v}</td>'
                                      for i, (c, v) in enumerate(zip(cab, cel))) + "</tr>")
    return ('<div class="tab"><table class="resp"><caption class="sr">Períodos em destaque</caption><thead><tr>'
            + "".join(f'<th scope="col"{NUM if i in COLUNAS_NUM else ""}>{e(c)}</th>' for i, c in enumerate(cab))
            + "</tr></thead><tbody>" + "".join(corpo) + "</tbody></table></div>")


UNICA = "Só uma declaração no TSE nas eleições analisadas, sem comparação ainda."


def _resumo_unica(a):
    """Quem tem uma so declaracao no TSE: o patrimonio declarado em reais com o link do TSE, sem percentual nem faixa."""
    kpis = [(_valor_tse(a.get("pat_fim"), a.get("link_tse")), f"Patrimônio declarado em {a.get('ano_fim')}"),
            (e(cap(a.get("cargo"))), "Cargo disputado")]
    tse = a.get("link_tse") if str(a.get("link_tse") or "").startswith("https://") else None
    return ('<div class="kpis">' + "".join(f'<div class="card kpi"><b>{v}</b><span>{e(r)}</span></div>' for v, r in kpis)
            + f'</div><p class="mut">{e(UNICA)}</p>'
            + (f'<p><a class="botao" href="{e(tse)}" target="_blank" rel="noopener">Ver candidatura, bens e contas da campanha no TSE</a></p>'
               if tse else ""))


def _resumo(linhas):
    if all(a.get("unica") for a in linhas):
        return _resumo_unica(linhas[0])
    topo = max(linhas, key=lambda a: (ORDEM.get(a.get("nivel"), 0), a.get("cresc") or 0))
    so_pagina = bool(linhas[0].get("so_pagina"))  # fora dos destaques: sem faixa, e o periodo e so "analisado"
    kpis = ([(graficos.ROTULO_NIVEL[topo["nivel"]], "Faixa mais alta")] if topo.get("nivel") in graficos.ROTULO_NIVEL else [])
    kpis += [(graficos.aumento_percentual(topo.get("pat_fim"), topo.get("pat_ini")),
              f"{'Patrimônio' if (topo.get('cresc') or 0) < 0 else 'Aumento do patrimônio'} de {topo.get('ano_ini')} a {topo.get('ano_fim')}"),
             (str(len(linhas)), "Períodos analisados" if so_pagina else "Períodos em destaque")]
    html_kpis = '<div class="kpis">' + "".join(f'<div class="card kpi"><b>{e(v)}</b><span>{e(r)}</span></div>'
                                                for v, r in kpis) + "</div>"
    tse = next((a["link_tse"] for a in linhas if str(a.get("link_tse") or "").startswith("https://")), None)
    links = (f'<p><a class="botao" href="{e(tse)}" target="_blank" rel="noopener">Ver candidatura, bens e contas da campanha no TSE</a></p>'
             if tse else "")
    return (html_kpis + _tabela_periodos(linhas) + links +
            '<p class="mut"><small><a href="../index.html#como-ler">O que significam estas colunas?</a></small></p>')


FONTE_TSE = ('<p class="fonte">Fonte: declarações de bens do <a href="https://dadosabertos.tse.jus.br/" target="_blank" '
             'rel="noopener">TSE</a>. Confira a declaração de cada eleição no <a href="https://divulgacandcontas.tse.jus.br/" '
             'target="_blank" rel="noopener">DivulgaCandContas</a>.</p>')


def _patrimonio(hist, linhas, uid):
    graf = graficos.patrimonio(hist, uid=uid)
    alt = _alt(graficos.tabela_patrimonio(hist)) if hist else ""
    emps = next((a.get("empresas") for a in linhas if a.get("empresas")), []) or []
    bloco = ""
    if emps:
        bloco = ("<h3>Empresas citadas na declaração de bens</h3><ul class=\"nt\">"
                 + "".join(f"<li>{e(x)}</li>" for x in emps) + "</ul>"
                 "<p class=\"mut\"><small>Extraídas automaticamente da descrição dos bens declarados ao TSE; a lista pode "
                 "estar incompleta.</small></p>")
    return (graf + alt + bloco + '<p class="mut"><small>Valores declarados pelo custo histórico, não pelo valor de mercado. '
            "Herança, venda de bens, atividade própria e renda do cônjuge não entram na conta.</small></p>" + FONTE_TSE)


def _chips(tags):
    return "".join(f'<span class="chip tag-{e(t)}">{e(graficos.ROTULO_TAG[t])}</span>'
                   for t in tags or () if t in graficos.ROTULO_TAG)


def _item_noticia(n):
    meta = " · ".join(x for x in (e(n.get("veiculo") or ""), n["data"].strftime("%d/%m/%Y") if n.get("data") else "") if x)
    titulo = e(n.get("titulo") or n["link"])
    return (f'<li><a href="{e(n["link"])}" target="_blank" rel="noopener">{titulo}</a>'
            f'<br>{f"<small>{meta}</small> " if meta else ""}{_chips(n.get("tags"))}</li>')


def _noticias(noticias, uid):
    """Lista de noticias com link e tags (#54) + grafico da % por tema; texto = aviso da busca."""
    if isinstance(noticias, str):
        return f'<p class="vazio">{e(noticias)}</p>'
    if noticias is None:
        return '<p class="vazio">Não informado: busca de notícias não realizada para esta pessoa.</p>'
    itens = [n for n in noticias if str(n.get("link") or "").startswith("https://")]
    if not itens:
        return '<p class="vazio">Nenhuma notícia que cite a pessoa ou empresa ligada pelo nome.</p>'
    cont = temas.contar(itens)
    return (graficos.percentual_por_tema(cont, uid=uid) + _alt(graficos.tabela_percentual_por_tema(cont))
            + '<ul class="nt">' + "".join(_item_noticia(n) for n in itens) + "</ul>"
            '<p class="mut"><small>Tags automáticas, pelas palavras do título e do resumo; podem errar. O gráfico conta '
            "cada notícia uma vez, pela primeira tag.</small></p>"
            '<p class="fonte">Fonte: cada link leva à matéria original; o conteúdo é de responsabilidade do veículo.</p>')


def _propostas(pid):
    props = [x for x in ler_jsonl(ROOT / "data" / "propostas.jsonl") if x.get("pessoa") == pid]
    vinc = [v for v in ler_vinculos() if v.get("pessoa") == pid]
    if not props and not vinc:
        return ('<p class="vazio">Ainda não há propostas de plano de governo nem proposições vinculadas a esta pessoa. '
                "Os vínculos só aparecem depois de revisados manualmente.</p>")
    return f'<p class="mut">{len(props)} propostas registradas; {len(vinc)} vínculos aprovados.</p>'


def _votos(v):
    """Aba "Votos e presença" (#56, #58): html ja escapado (votacoes.secao e presenca.secao)."""
    if not v:
        return '<p class="vazio"><b>Não informado</b>: votos e presença só existem para deputados federais e senadores.</p>'
    return f"<h3>Como votou</h3>{v[0]}<h3>Presença</h3>{v[1]}"


def _cabecalho(a, nome, img=None, acoes=""):
    urna = (a.get("nome_urna") or "").strip()
    ficha = " · ".join(e(str(x)) for x in (cap(a.get("cargo")), a.get("partido"), a.get("uf")) if x)
    return (f'<header class="cab">{avatar(urna or nome, grande=True, foto=img)}<div><h1>{e(cap(nome))}</h1>'
            + (f'<p class="ficha">Nome de urna: <strong>{e(cap(urna))}</strong></p>' if urna and urna.upper() != nome.upper() else "")
            + f'<p class="ficha">{ficha}</p>{chip_nivel(a.get("nivel"))}</div>'
            + (f'<div class="acoes">{acoes}</div>' if acoes else "") + "</header>")


def _equipe(equipe):
    """Bloco "Equipe do gabinete" do Resumo (#66); vazio quando a contagem nao existe (cargo sem gabinete ou dado
    ainda nao carregado), para a pagina nunca mostrar um bloco quebrado."""
    if not equipe:
        return ""
    return f'<h3>Equipe do gabinete</h3>{gabinete.secao(equipe[0], None, consultado=True)}'


def pagina(tpl, pid, linhas, hist, dinheiro, gerado, noticias=None, cobranca=None, votos=None, equipe=None):
    """`cobranca`: contato do gabinete, cota e projetos da pessoa para a aba "Como cobrar" (#60, cobrar.secao).
    `equipe`: (contagem do gabinete ou None se a fonte falhou,) para parlamentar em exercicio; None fora disso (#66)."""
    topo = max(linhas, key=lambda a: (ORDEM.get(a.get("nivel"), 0), a.get("ano_fim") or 0))
    nome = str(topo.get("nome") or "")
    acoes = cobrar.botao(cobrar.imagem(linhas)) + acompanhar.botao(pid, str(topo.get("uf") or "").upper())
    vals = dict(TITULO=e(cap((topo.get("nome_urna") or nome).strip())),
                CABECALHO=_cabecalho(topo, nome, foto(linhas), acoes),
                RESUMO=_resumo(linhas) + _equipe(equipe), PATRIMONIO=_patrimonio(hist, linhas, f"pt-{pid}"),
                NOTICIAS=_noticias(noticias, f"nt-{pid}"),
                DINHEIRO=dinheiro or '<p class="vazio">Sem consulta nesta execução.</p>',
                PROPOSTAS=_propostas(pid), COBRAR=cobrar.secao(linhas, cobranca), VOTOS=_votos(votos), GERADO=e(gerado),
                FEED=acompanhar.link_head(pid, cap((topo.get("nome_urna") or nome).strip())))
    return re.sub(r"__([A-Z]+)__", lambda m: vals.get(m.group(1), m.group(0)), tpl)


# ---------------------------------------------------------------- visao geral
def cartao(pid, linhas, hist):
    topo = max(linhas, key=lambda a: (ORDEM.get(a.get("nivel"), 0), a.get("cresc") or 0))
    nome = (topo.get("nome_urna") or topo.get("nome") or "").strip()
    ficha = " · ".join(e(str(x)) for x in (topo.get("cargo"), topo.get("partido"), topo.get("uf")) if x)
    mini = graficos.mini_patrimonio(hist, uid=f"mn-{pid}")
    # so o nome e link: as tags (montadas no painel a partir de data-pagina) sao botoes de filtro
    return (f'<li class="card pessoa" data-pagina="pessoa/{e(pid)}.html">{avatar(nome, foto=foto(linhas))}'
            f'<span class="info"><a class="nome" href="pessoa/{e(pid)}.html">{e(nome)}</a>'
            f'<small class="ficha">{ficha}</small>{chip_nivel(topo.get("nivel"))}</span>'
            f'<span class="mini">{mini}</span></li>')


def gerar(alertas, pessoas, hist, secoes, docs, gerado, noticias=None, cobranca=None, votos=None, equipe=None):
    """Escreve docs/pessoa/<id>.html e devolve (html dos cartoes, {marca: html dos graficos do painel}).
    `noticias`: {indice_da_linha: lista de noticias com tags ou aviso em texto} (dossie.gerar_dossies).
    `cobranca`: {indice_da_linha: contato, cota e projetos} para a aba "Como cobrar" (#60).
    `votos`: {indice_da_linha: (html de "Como votou", html de "Presença")} (#56, #58).
    `equipe`: {indice_da_linha: contagem do gabinete ou None se a fonte falhou} (#66, pipeline.montar_equipe)."""
    noticias, cobranca, equipe = noticias or {}, cobranca or {}, equipe or {}
    pasta = Path(docs) / "pessoa"
    pasta.mkdir(parents=True, exist_ok=True)
    for f in pasta.glob("*.html"):
        f.unlink()
    tpl = (SRC / "pessoa.html").read_text(encoding="utf-8")
    itens = []
    for q in pessoas.values():
        linhas = [alertas[i] for i in q["idx"]]
        pid = linhas[0].get("pessoa")
        if not pid or not re.fullmatch(r"p\d+", str(pid)):
            continue
        h = hist.get(q["chave"], [])
        (pasta / f"{pid}.html").write_text(pagina(tpl, pid, linhas, h, secoes.get(q["idx"][0]), gerado,
                                                           noticias.get(q["idx"][0]),
                                                           cobranca.get(q["idx"][0]), (votos or {}).get(q["idx"][0]),
                                                           (equipe[q["idx"][0]],) if q["idx"][0] in equipe else None),
                                       encoding="utf-8")
        for i in q["idx"]:
            alertas[i]["pagina"] = f"pessoa/{pid}.html"
            alertas[i]["cobrar"] = 1  # a pagina ja tem a aba "Como cobrar": o card mostra o atalho (#60)
        if not linhas[0].get("so_pagina"):  # fora dos destaques: so a pagina, sem card no painel
            itens.append((max(ORDEM.get(a.get("nivel"), 0) for a in linhas), max(a.get("cresc") or 0 for a in linhas),
                          cartao(pid, linhas, h)))
    itens.sort(key=lambda t: (t[0], t[1]), reverse=True)
    cartoes = '<ul class="pessoas">' + "".join(t[2] for t in itens) + "</ul>" if itens else ""
    cont = {n: sum(1 for a in alertas if a.get("nivel") == n and not a.get("so_pagina")) for n in graficos.ROTULO_NIVEL}
    series = temas.por_mes(n for v in noticias.values() if isinstance(v, list) for n in v)
    graf = dict(GRAFICO_NIVEIS=graficos.barras_niveis(cont, uid="pn") + _alt(graficos.tabela_niveis(cont)),
                GRAFICO_TEMAS=graficos.noticias_por_tema(series, uid="pt")
                + (_alt(graficos.tabela_noticias_por_tema(series)) if series else ""))
    return cartoes, graf


def copiar_estilo(docs):
    """estilo.css, selo.js, logo, a pagina de privacidade (LGPD arts. 9, 18 e 41) e o aviso legal, com os dados de
    config/privacidade.json."""
    for f in ("estilo.css", "selo.js", "compartilhar.js", "representantes.js", "painel.js"):  # estilo, selo de cera, cobrar (#60, #61), estados (#68), painel (#73)
        shutil.copyfile(SRC / f, Path(docs) / f)
    shutil.copytree(SRC / "bandeiras", Path(docs) / "bandeiras", dirs_exist_ok=True)  # aba Estados (#68), sem link externo
    for img in ("logo.png", "icone.png"):  # marca do Caramelo Vasculha
        shutil.copyfile(SRC / img, Path(docs) / img)
    try:
        cfg = json.loads((ROOT / "config" / "privacidade.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    falta = "Ainda não informado. Preencha <code>config/privacidade.json</code> antes de divulgar o site."
    enc = cfg.get("encarregado", "").strip()
    vals = dict(CONTROLADOR=e(cfg.get("controlador", "").strip()) or falta,
                CONTATO=link_contato(cfg.get("contato", "")) or falta,
                ENCARREGADO=(e(enc) + (f' · {e(cfg.get("contato_encarregado", "").strip())}'
                                        if cfg.get("contato_encarregado", "").strip() else "")) or falta,
                ATUALIZADO=e(cfg.get("atualizado_em", "").strip() or "Não informado"),
                MEDICAO=texto_medicao())
    for nome in ("privacidade.html", "funcionamento.html"):  # funcionamento do site (#62): o que o site e e como pedir correcao
        tpl = (SRC / nome).read_text(encoding="utf-8")
        (Path(docs) / nome).write_text(re.sub(r"__([A-Z]+)__", lambda m: vals.get(m.group(1), m.group(0)), tpl),
                                       encoding="utf-8")


def link_contato(contato):
    """Canal de correcao e direito de resposta: formulario (URL), e-mail ou texto livre; vazio se nao configurado."""
    contato = (contato or "").strip()
    if contato.startswith("https://"):
        return f'<a href="{e(contato)}" target="_blank" rel="noopener">formulário de correção e resposta</a>'
    if "@" in contato:
        return f'<a href="mailto:{e(contato)}">{e(contato)}</a>'
    return e(contato)


RODAPE_LEGAL = "data-rodape-legal"


def rodape_legal(site):
    """Rodape legal (#62) no fim de todas as paginas publicadas: dados oficiais so reorganizados, nenhum indicador
    afirma irregularidade, e onde pedir correcao. Idempotente. Devolve quantas paginas receberam o rodape."""
    site = Path(site)
    n = 0
    for pag in sorted(site.rglob("*.html")):
        h = pag.read_text(encoding="utf-8")
        if RODAPE_LEGAL in h or "</body>" not in h:
            continue
        pre = "../" * (len(pag.relative_to(site).parts) - 1)
        rodape = (f'<footer class="rodape-legal" {RODAPE_LEGAL}>Ferramenta independente de agregação de dados '
                  f'públicos, sem vínculo com governo, partido ou empresa. Dados de fontes oficiais (TSE, '
                  f'Portal da Transparência, Câmara e Senado), que respondem por eles; aqui eles só são organizados. '
                  f'Confira sempre na fonte indicada. Nenhum destaque afirma irregularidade ou crime. '
                  f'<a href="{pre}funcionamento.html">Funcionamento do site e correções</a> · '
                  f'<a href="{pre}privacidade.html">Privacidade</a></footer>\n')
        pag.write_text(h.replace("</body>", rodape + "</body>", 1), encoding="utf-8")
        n += 1
    return n


ARQUIVOS_VERSIONADOS = ("estilo.css", "selo.js", "compartilhar.js", "representantes.js", "painel.js")


def versionar(site):
    """Poe ?v=<hash do conteudo> nos links de estilo e scripts comuns, para o navegador nao usar uma copia velha
    depois de uma publicacao (o GitHub Pages deixa em cache por 10 min). Idempotente. Devolve quantas paginas mudaram."""
    site = Path(site)
    versoes = {f: hashlib.sha256((site / f).read_bytes()).hexdigest()[:10]
               for f in ARQUIVOS_VERSIONADOS if (site / f).exists()}
    if not versoes:
        return 0
    link = re.compile(r'((?:href|src)="(?:\.\./)*)(' + "|".join(map(re.escape, versoes)) + r')(?:\?v=[0-9a-f]*)?"')
    n = 0
    for pag in site.rglob("*.html"):
        h = pag.read_text(encoding="utf-8")
        novo = link.sub(lambda m: f'{m[1]}{m[2]}?v={versoes[m[2]]}"', h)
        if novo != h:
            pag.write_text(novo, encoding="utf-8")
            n += 1
    return n


def config_medicao():
    """config/analytics.json: id do GA4 so se tiver o formato G-XXXXXXXXXX (senao, Google Analytics desligado)."""
    try:
        cfg = json.loads((ROOT / "config" / "analytics.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    ga = str(cfg.get("id_medicao", "")).strip().upper()
    meses = cfg.get("retencao_meses")
    return (ga if re.fullmatch(r"G-[A-Z0-9]{4,16}", ga) else ""), (meses if meses in (2, 14) else None)


def texto_medicao():
    """Secao da privacidade sobre o Google Analytics; vazia quando ele esta desligado."""
    ga, meses = config_medicao()
    if not ga:
        return ""
    prazo = f"{meses} meses" if meses else "o prazo configurado no Google Analytics"
    return f"""<h2 id="metricas">Métricas de acesso (Google Analytics)</h2>
<p>Para saber quantas pessoas visitam o site e quais páginas são mais lidas, usamos o Google Analytics 4, do Google. Os cookies de medição <strong>só são gravados se você aceitar</strong> no aviso de cookies (consentimento, art. 7º, I, e art. 8º). Sem o aceite, a tag do Google continua na página no modo de consentimento negado: não grava cookies e manda ao Google só avisos de visita sem identificador, que não ligam uma visita à outra. Recusar não muda nada no uso do site.</p>
<ul>
<li><strong>O que é coletado:</strong> páginas visitadas, tempo de visita, de onde veio o acesso, tipo de aparelho e de navegador, região aproximada e um código aleatório guardado nos cookies <code>_ga</code>. O Google recebe o endereço IP para fazer a medição e informa que não o guarda no Google Analytics 4.</li>
<li><strong>O que fica desligado:</strong> anúncios, personalização de anúncios e os sinais do Google (ligação com contas Google), nas configurações da propriedade. Nenhum dado das pessoas acompanhadas pelo site vai para o Google.</li>
<li><strong>Quem recebe:</strong> o Google, que pode tratar os dados fora do Brasil (transferência internacional, art. 33). Veja a <a href="https://policies.google.com/privacy" target="_blank" rel="noopener">política de privacidade do Google</a> e <a href="https://policies.google.com/technologies/partner-sites" target="_blank" rel="noopener">como ele usa dados de sites parceiros</a>.</li>
<li><strong>Por quanto tempo:</strong> os dados de navegação ficam {prazo} nos relatórios; os cookies <code>_ga</code> duram até 2 anos no seu navegador, ou até você recusar ou apagá-los.</li>
<li><strong>Como mudar de ideia:</strong> <button type="button" class="botao" data-medicao-preferencias hidden>Mudar minha escolha</button> Também dá para apagar os cookies e os dados deste site nas configurações do navegador, ou instalar o <a href="https://tools.google.com/dlpage/gaoptout" target="_blank" rel="noopener">complemento de desativação do Google Analytics</a>.</li>
</ul>"""


def medicao(site):
    """Google Analytics 4 no site publicado: poe a tag do Google (gtag.js) com o id de config/analytics.json logo
    depois do <head> de todas as paginas, com o consentimento negado ate o "Aceitar" do aviso (medicao.js, gravado
    junto). Sem id valido, nada e carregado. Devolve quantas paginas."""
    site = Path(site)
    alvo = site / "medicao.js"
    ga, _ = config_medicao()
    if not ga:
        alvo.unlink(missing_ok=True)
        return 0
    shutil.copyfile(SRC / "medicao.js", alvo)
    # sem cookie nenhum ate o aceite; anuncios sempre negados. cv-medicao e a escolha gravada pelo medicao.js
    tag = f"""<!-- Google tag (gtag.js) -->
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('consent', 'default', {{'ad_storage': 'denied', 'ad_user_data': 'denied', 'ad_personalization': 'denied',
                               'analytics_storage': 'denied'}});
  try {{ if (localStorage.getItem('cv-medicao') === 'aceito') gtag('consent', 'update', {{'analytics_storage': 'granted'}}); }} catch (e) {{}}
</script>
<script async src="https://www.googletagmanager.com/gtag/js?id={ga}"></script>
<script>
  gtag('js', new Date());

  gtag('config', '{ga}');
</script>"""
    n = 0
    for pag in sorted(site.rglob("*.html")):
        h = pag.read_text(encoding="utf-8")
        if "googletagmanager.com/gtag/js" in h:
            continue
        pre = "../" * (len(pag.relative_to(site).parts) - 1)
        h, achou = re.subn(r"<head(?:\s[^>]*)?>", lambda m: m.group(0) + "\n" + tag, h, count=1)
        if achou and "</head>" in h:
            h = h.replace("</head>", f'<script src="{pre}medicao.js" defer></script>\n</head>', 1)
            pag.write_text(h, encoding="utf-8")
            n += 1
    return n
