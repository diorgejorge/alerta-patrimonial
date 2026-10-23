"""Como cobrar (#60) e compartilhar (#61) na pagina da pessoa: canais oficiais do gabinete, texto sugerido so para
copiar (educado, sem acusacao) e os dados da imagem de compartilhar, que o compartilhar.js desenha no navegador.
Texto e imagem citam so as fontes oficiais (TSE, Camara, Senado), nunca o site como origem (pedido do usuario).
Nada aqui consulta a rede: os contatos chegam prontos (contatos.py)."""
import html, json, re, urllib.parse
from estados import UFS
from texto import cap, de_estado
import graficos

e = html.escape
TSE_DADOS = "https://dadosabertos.tse.jus.br/"
CASAS = {"camara": "Dados Abertos da Câmara dos Deputados", "senado": "Dados Abertos do Senado Federal"}
FONTE_TSE = "Fonte: declarações de bens entregues ao TSE"
FONTE_SALARIO = " e salário oficial do cargo"
MUNICIPAIS = {"PREFEITO", "VICE-PREFEITO", "VEREADOR"}
ESTADUAIS = {"DEPUTADO ESTADUAL", "DEPUTADO DISTRITAL"}


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
    ini = _num(per[0].get("pat_ini"))
    return dict(ano_ini=per[0].get("ano_ini"), ano_fim=per[-1].get("ano_fim"), cresc=total, cap=guardar,
                aumento=None if total is None or ini is None else graficos.variacao(ini + total, ini),  # #62: sem reais
                razao=total / guardar if guardar and total and total > 0 else None,
                tse=next((a["link_tse"] for a in reversed(per) if str(a.get("link_tse") or "").startswith("https://")),
                         None))


def _da_casa(camara):
    return "da Câmara dos Deputados" if camara else "do Senado Federal"


def _vi(onde, link):
    """'Vi no site do TSE (https://...)': o cidadao cita a fonte oficial com o link direto (nunca o nosso site)."""
    return f"Vi {onde}" + (f" ({link})" if str(link or "").startswith("https://") else "")


def texto(nome, uf, r, cota=None, projetos=None):
    """Texto sugerido de cobranca, na voz do cidadao ("Vi no site do TSE (link) que..."): cada numero com o link da
    fonte oficial e um pedido de explicacao publica. Nunca afirma irregularidade nem cita o nosso site."""
    pontos = []
    cresceu = r.get("cresc") is not None and r["cresc"] > 0
    if cresceu:
        p = _vi("no site do TSE", r.get("tse")) + " que seu patrimônio declarado aumentou" + (
            f" {r['aumento']}" if r.get("aumento") and r["aumento"][0] in "+−" else "") + f" de {r['ano_ini']} a {r['ano_fim']}."
        if r.get("razao") and r["razao"] >= 1.05:
            p += f" O aumento foi {vezes(r['razao'])} vezes o que daria para guardar somente com o salário do cargo."
        pontos.append(p)
    if cota and _num(cota.get("total")):
        pontos.append(_vi(f"nos dados abertos {_da_casa('camara.leg.br' in str(cota.get('link')))}", cota.get("link"))
                      + f" que sua cota parlamentar (verba do mandato) somou {brl(cota['total'])} de {cota.get('de')} "
                      f"a {cota.get('ate')}.")
    if projetos and projetos.get("apresentados"):
        camara = projetos.get("casa") == "camara" or "camara.leg.br" in str(projetos.get("link"))
        pontos.append(_vi(f"no site {_da_casa(camara)}", projetos.get("link"))
                      + f" que, de {projetos.get('de')} a {projetos.get('ate')}, você apresentou "
                      f"{projetos['apresentados']} projetos e {projetos.get('aprovados') or 0} foram aprovados.")
    pedido = ("Pode explicar, de forma pública, de onde veio esse crescimento? Por exemplo: herança, venda de bens, "
              "outra atividade ou renda da família." if cresceu else
              "Peço que continue prestando contas do mandato de forma clara e pública.")
    de = f" {de_estado(uf, UFS[uf][1])}" if uf in UFS else f" de {uf}" if uf else ""
    corpo = "\n\n" + "\n".join(f"- {p}" for p in pontos) if pontos else ""
    return (f"Prezado(a) {nome},\n\n"
            f"Sou eleitor(a){de} e acompanho os dados oficiais do seu mandato.{corpo}\n\n{pedido}\n\n"
            "Aguardo sua resposta. Obrigado(a)!\n[seu nome]")


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


def secao(linhas, ctx=None):
    """HTML da aba "Como cobrar": canais oficiais e texto sugerido para copiar. `ctx`: contato (dict, ou None quando a
    fonte falhou; ausente = nao e parlamentar federal), assembleia (nome, site), cota e projetos (como no pipeline)."""
    ctx = ctx or {}
    topo = max(linhas, key=lambda a: a.get("ano_fim") or 0)
    nome = cap((topo.get("nome_urna") or topo.get("nome") or "").strip())
    corpo = texto(nome, topo.get("uf"), resumo(linhas), ctx.get("cota"), ctx.get("projetos"))
    return ("<p><strong>Você paga o salário de quem foi eleito. Perguntar é seu direito.</strong></p>"
            f'<h3>Canais oficiais do gabinete</h3>{_contatos(topo.get("cargo"), topo.get("uf"), ctx)}'
            '<h3><label for="cobrar-texto">Sugestão de texto</label></h3>'
            f'<textarea id="cobrar-texto" class="cobrar-texto" rows="12" readonly>{e(corpo)}</textarea>'
            '<p class="cobrar-acoes"><button type="button" class="botao" data-copiar-texto="cobrar-texto">Copiar texto'
            '</button><span class="cobrar-aviso" role="status"></span></p>')


def imagem(linhas):
    """Dados do card para a imagem de compartilhar (JSON no atributo data-compartilhar do botao). O link e o da
    fonte oficial (candidatura no TSE), nunca o do nosso site."""
    topo = max(linhas, key=lambda a: a.get("ano_fim") or 0)
    r = resumo(linhas)
    numeros = []
    if r["aumento"]:
        numeros.append([r["aumento"], f"no patrimônio de {r['ano_ini']} a {r['ano_fim']}"])
    if r["razao"]:
        numeros.append([vezes(r["razao"]) + "×", "o que daria para guardar somente com o salário"])
    ficha = " · ".join(str(x) for x in (cap(topo.get("cargo")), topo.get("partido"), topo.get("uf")) if x)
    return dict(nome=cap((topo.get("nome_urna") or topo.get("nome") or "").strip()), ficha=ficha, numeros=numeros,
                url=r["tse"] or TSE_DADOS, fontes=FONTE_TSE + (FONTE_SALARIO if r["cap"] else "") + ".")


def botao(dados):
    """Botao "Compartilhar" (escondido ate o compartilhar.js confirmar que o navegador desenha a imagem)."""
    return (f'<button type="button" class="botao" data-compartilhar="{e(json.dumps(dados, ensure_ascii=False))}" '
            '>Compartilhar</button>')
