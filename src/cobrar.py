"""Como cobrar (#60) e compartilhar (#61) na pagina da pessoa: contatos oficiais do gabinete, texto pronto de cobranca
montado com os numeros do proprio card (educado e sem acusacoes) e os dados da imagem de compartilhar, que o
compartilhar.js desenha no navegador. Nada aqui consulta a rede: os contatos chegam prontos (contatos.py)."""
import html, json, os, re, urllib.parse
import estados
from texto import cap, de_estado

e = html.escape
SITE = "https://diorgejorge.github.io/alerta-patrimonial/"
ASSUNTO = "Pedido de esclarecimento sobre dados públicos do mandato"
CASAS = {"camara": "Dados Abertos da Câmara dos Deputados", "senado": "Dados Abertos do Senado Federal"}
NIVEL = {"forte": "Muito acima do esperado", "atencao": "Acima do esperado", "informativo": "Para conhecer"}
FONTES_IMAGEM = "Fontes oficiais: TSE, Portal da Transparência, Câmara e Senado"
MUNICIPAIS = {"PREFEITO", "VICE-PREFEITO", "VEREADOR"}
ESTADUAIS = {"DEPUTADO ESTADUAL", "DEPUTADO DISTRITAL"}


def site(repo=None):
    """Endereco publico do site: GitHub Pages do repositorio (GITHUB_REPOSITORY) ou o padrao."""
    repo = repo if repo is not None else os.getenv("GITHUB_REPOSITORY") or ""
    m = re.fullmatch(r"([\w.-]+)/([\w.-]+)", repo)
    return f"https://{m[1].lower()}.github.io/{m[2]}/" if m else SITE


def brl(v):
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def vezes(v):
    return f"{v:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _num(v):
    return v if isinstance(v, (int, float)) and v == v else None  # descarta None e NaN


def resumo(linhas):
    """Numeros do card (regra 8: crescimento somado entre os periodos): anos, crescimento, o que daria para guardar
    com o salario (so se todos os periodos tem) e quantas vezes isso."""
    per = sorted(linhas, key=lambda a: (a.get("ano_ini") or 0, a.get("ano_fim") or 0))
    cresc = [_num(a.get("cresc")) for a in per]
    caps = [_num(a.get("cap")) for a in per]
    total = sum(c for c in cresc if c is not None) if any(c is not None for c in cresc) else None
    guardar = sum(caps) if caps and all(c is not None and c > 0 for c in caps) else None
    return dict(ano_ini=per[0].get("ano_ini"), ano_fim=per[-1].get("ano_fim"), cresc=total, cap=guardar,
                razao=total / guardar if guardar and total and total > 0 else None,
                tse=next((a["link_tse"] for a in reversed(per) if str(a.get("link_tse") or "").startswith("https://")),
                         None))


def _fonte(link):
    return f" Fonte: {link}" if str(link or "").startswith("https://") else ""


def texto(nome, uf, r, cota=None, projetos=None, url=SITE, extra=None):
    """Texto pronto de cobranca: pede explicacao publica com base em dados oficiais, cada numero com a sua fonte.
    Nunca afirma irregularidade. `extra`: frase pronta de outro modulo ."""
    pontos = []
    cresceu = r.get("cresc") is not None and r["cresc"] > 0
    if cresceu:
        p = f"Seu patrimônio declarado ao TSE cresceu {brl(r['cresc'])} de {r['ano_ini']} a {r['ano_fim']}."
        if r.get("cap"):
            p += f" Só com o salário, daria para guardar {brl(r['cap'])}."
            if r.get("razao") and r["razao"] >= 1.05:
                p += f" Cresceu {vezes(r['razao'])} vezes isso."
        pontos.append(p + _fonte(r.get("tse")))
    if extra:
        pontos.append(extra.strip())
    if cota and _num(cota.get("total")):
        pontos.append(f"A cota parlamentar (verba do mandato) somou {brl(cota['total'])} de {cota.get('de')} a {cota.get('ate')}."
                      + _fonte(cota.get("link")))
    if projetos and projetos.get("apresentados"):
        pontos.append(f"De {projetos.get('de')} a {projetos.get('ate')}, foram {projetos['apresentados']} projetos "
                      f"apresentados e {projetos.get('aprovados') or 0} aprovados." + _fonte(projetos.get("link")))
    pedido = ("Pode explicar, de forma pública, de onde veio esse crescimento? Por exemplo: herança, venda de bens, "
              "outra atividade ou renda da família." if cresceu else
              "Peço que continue prestando contas do mandato de forma clara e pública.")
    de = f" {de_estado(uf, estados.UFS[uf][1])}" if uf in estados.UFS else f" de {uf}" if uf else ""
    corpo = "\n\n" + "\n".join(f"- {p}" for p in pontos) if pontos else ""
    return (f"Prezado(a) {nome},\n\n"
            f"Sou eleitor(a){de} e acompanho os dados oficiais do seu mandato.{corpo}\n\n{pedido}\n\n"
            "Aguardo sua resposta. Obrigado(a)!\n[seu nome]\n\n"
            f"Dados oficiais reunidos pelo Caramelo Vasculha: {url}")


def mailto(email, corpo):
    q = urllib.parse.urlencode(dict(subject=ASSUNTO, body=corpo), quote_via=urllib.parse.quote)
    return f"mailto:{email}?{q}"


def _tel(fone):
    return "tel:+55" + re.sub(r"\D", "", fone)


def _contatos(cargo, uf, ctx):
    """Lista de contatos oficiais, ou o aviso de quando nao ha (Fonte nao encontrada / Nao informado)."""
    if "contato" in ctx:  # parlamentar federal em exercicio
        c = ctx["contato"]
        if not c:
            return ('<p class="vazio"><b>Fonte não encontrada</b>: os dados abertos da Câmara e do Senado não '
                    "responderam nesta atualização. Tente a página oficial do mandato.</p>")
        itens = []
        if c.get("email"):
            itens.append(("E-mail", f'<a href="mailto:{e(c["email"])}">{e(c["email"])}</a>'))
        if c.get("telefone"):
            itens.append(("Telefone", f'<a href="{_tel(c["telefone"])}">{e(c["telefone"])}</a>'))
        if c.get("endereco"):
            itens.append(("Gabinete", e(c["endereco"])))
        if c.get("perfil"):
            itens.append(("Página oficial", f'<a href="{e(c["perfil"])}" target="_blank" rel="noopener">'
                                             "Ver o mandato no site oficial</a>"))
        redes = [u for u in c.get("redes") or [] if u.startswith("https://")]
        if redes:
            itens.append(("Redes sociais", " · ".join(
                f'<a href="{e(u)}" target="_blank" rel="noopener">{e(urllib.parse.urlsplit(u).hostname or u)}</a>'
                for u in redes)))
        lista = "".join(f"<li><span>{r}</span>{v}</li>" for r, v in itens) or '<li><span>Contato</span>Não informado</li>'
        fonte = (f'<p class="mut"><small>Fonte: <a href="{e(c["fonte"])}" target="_blank" rel="noopener">'
                 f'{CASAS.get(c.get("casa"), "Dados abertos oficiais")}</a>.</small></p>'
                 if str(c.get("fonte") or "").startswith("https://") else "")
        return f'<ul class="cobrar-contatos">{lista}</ul>{fonte}'
    cargo = str(cargo or "").upper()
    if cargo in ESTADUAIS and ctx.get("assembleia"):
        nome, url = ctx["assembleia"]
        return (f'<ul class="cobrar-contatos"><li><span>Onde procurar</span><a href="{e(url)}" target="_blank" '
                f'rel="noopener">{e(nome)}</a></li></ul><p class="mut"><small>Os dados abertos das Assembleias não '
                "seguem um padrão nacional; no site oficial há a página do gabinete com e-mail e telefone.</small></p>")
    onde = ("na câmara municipal ou na prefeitura da cidade" if cargo in MUNICIPAIS else
            "no site oficial do órgão em que a pessoa trabalha")
    return (f'<p class="vazio"><b>Não informado</b>: ainda não há fonte oficial e gratuita com o contato deste cargo. '
            f"Procure os canais {onde}.</p>")


def secao(linhas, ctx=None, url=SITE):  # url: endereco da pagina da pessoa (vai no fim do texto)
    """HTML da aba "Como cobrar". `ctx`: contato (dict, ou None quando a fonte falhou; ausente = nao e parlamentar
    federal), assembleia (nome, site), cota e projetos (como no pipeline) e extra (frase pronta)."""
    ctx = ctx or {}
    topo = max(linhas, key=lambda a: a.get("ano_fim") or 0)
    nome = cap((topo.get("nome_urna") or topo.get("nome") or "").strip())
    corpo = texto(nome, topo.get("uf"), resumo(linhas), ctx.get("cota"), ctx.get("projetos"), url, ctx.get("extra"))
    email = (ctx.get("contato") or {}).get("email")
    enviar = (f'<a class="botao secundario" data-mailto="cobrar-texto" href="{e(mailto(email, corpo))}">'
              "Enviar por e-mail</a>" if email else "")
    return ("<p><strong>Você paga o salário de quem foi eleito. Perguntar é seu direito.</strong> Use o contato "
            "oficial e o texto pronto abaixo; dá para editar antes de mandar.</p>"
            f'<h3>Fale com o gabinete</h3>{_contatos(topo.get("cargo"), topo.get("uf"), ctx)}'
            '<h3><label for="cobrar-texto">Texto pronto</label></h3>'
            f'<textarea id="cobrar-texto" class="cobrar-texto" rows="14" spellcheck="true">{e(corpo)}</textarea>'
            f'<p class="cobrar-acoes"><button type="button" class="botao" data-copiar-texto="cobrar-texto">'
            f'Copiar texto</button>{enviar}<span class="cobrar-aviso" role="status"></span></p>'
            '<p class="mut"><small>Dica: troque “[seu nome]” pelo seu nome e guarde a resposta. Quanto mais gente '
            "pergunta, mais difícil é ignorar.</small></p>")


def imagem(linhas, pagina, url=SITE):
    """Dados do card para a imagem de compartilhar (JSON no atributo data-compartilhar do botao)."""
    topo = max(linhas, key=lambda a: a.get("ano_fim") or 0)
    r = resumo(linhas)
    nivel = max((a.get("nivel") for a in linhas if a.get("nivel") in NIVEL),
                key=["informativo", "atencao", "forte"].index, default=None)
    numeros = []
    if r["cresc"] is not None:
        numeros.append([("+" if r["cresc"] > 0 else "−" if r["cresc"] < 0 else "") + brl(abs(r["cresc"])),
                        f"a mais no patrimônio de {r['ano_ini']} a {r['ano_fim']}"])
    if r["cap"]:
        numeros.append([brl(r["cap"]), "daria para guardar só com o salário"])
    if r["razao"]:
        numeros.append([vezes(r["razao"]) + "×", "o que daria para guardar com o salário"])
    ficha = " · ".join(str(x) for x in (cap(topo.get("cargo")), topo.get("partido"), topo.get("uf")) if x)
    return dict(nome=cap((topo.get("nome_urna") or topo.get("nome") or "").strip()), ficha=ficha, nivel=nivel,
                nivel_rotulo=NIVEL.get(nivel, ""), numeros=numeros, url=url + pagina, fontes=FONTES_IMAGEM)


def botao(dados):
    """Botao "Compartilhar" (escondido ate o compartilhar.js confirmar que o navegador desenha a imagem)."""
    return (f'<button type="button" class="botao" data-compartilhar="{e(json.dumps(dados, ensure_ascii=False))}" '
            '>Compartilhar</button>')
