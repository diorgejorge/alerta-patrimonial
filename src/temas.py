"""Tags das noticias (#54): classificacao por palavras-chave no titulo e no resumo, sem servico externo.
Tags na ordem de graficos.ROTULO_TAG; "criminal" aparece no site como "Segurança". Sem nenhuma palavra = "outros".
Uma noticia pode ter ate MAX_TAGS tags; a primeira (mais palavras, titulo vale o dobro) e a principal."""
import datetime as dt
import re, unicodedata

MAX_TAGS = 3
OUTROS = "outros"
# radicais sem acento e em minusculas, com \b nos dois lados; "_" junta expressoes de mais de uma palavra.
# Inclui termos em ingles (Google News exterior) e siglas de partido
PALAVRAS = {
    "politico": r"partid\w* filiad\w* filiacao ministr\w* planalto oposicao alianca aliad\w* centrao lideranca"
                r" lider governista articulacao federacao bancada apoio governo pt pl mdb psdb psd pp psol pdt psb"
                r" pcdob republicanos podemos avante solidariedade cidadania uniao_brasil party",
    "eleitoral": r"eleic\w* eleit\w* reeleit\w* reeleic\w* candidat\w* campanha\w* votos? urnas? tse tre turno"
                 r" coligac\w* intencao pesquisa\w* debate\w* elect\w* vote\w* voters?",
    "legislativo": r"projetos?_de_lei pec plenario camara senado assembleia comissao\w* cpi cpmi emendas?"
                   r" relator\w* votac\w* aprov\w* veto\w* sancion\w* medida_provisoria tramitac\w* congress\w*"
                   r" lawmakers? senate",
    "gestao": r"prefeitura\w* secretari\w* obras? saude educacao orcamento\w* licitac\w* contrat\w* investiment\w*"
              r" gestao administracao programa\w* hospita\w* escolas? verbas? repass\w* recursos",
    "patrimonial": r"patrimoni\w* bens imove\w* imovel fazendas? enriquec\w* empresas? socios? socia heranca"
                   r" mansao fortuna milionari\w* declaracao_de_bens wealth assets",
    "judicial": r"justica juiz\w* tribuna\w* stf stj tcu processo\w* acao reu re denunci\w* conden\w* inelegiv\w*"
                r" julgament\w* sentenca liminar recurso\w* improbidade ministerio_publico mpf court judge\w*",
    "criminal": r"policia\w* pf operac\w* pris\w* pres[oa]s? crimes? criminos\w* corrupc\w* lavagem desvi\w*"
                r" propinas? fraude\w* homicidi\w* violencia seguranca trafic\w* milicia\w* investigad\w*"
                r" police arrest\w* corruption scandal\w*",
}
REGRAS = {t: re.compile(r"\b(?:" + "|".join(w.replace("_", " ") for w in p.split()) + r")\b")
          for t, p in PALAVRAS.items()}
ORDEM = (*PALAVRAS, OUTROS)


def _normal(s):
    """Minusculas, sem acento, so letras/digitos separados por espaco."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def classificar(titulo, resumo=None):
    """Tags da noticia, da mais forte para a mais fraca (empate: ordem de ORDEM); o titulo vale o dobro."""
    tit, res = _normal(titulo), _normal(resumo)
    placar = [(2 * len(r.findall(tit)) + len(r.findall(res)), i, t) for i, (t, r) in enumerate(REGRAS.items())]
    tags = [t for n, _, t in sorted(placar, key=lambda x: (-x[0], x[1])) if n][:MAX_TAGS]
    return tags or [OUTROS]


def principal(noticia):
    tags = noticia.get("tags") or [OUTROS]
    return tags[0] if tags[0] in ORDEM else OUTROS


def contar(noticias):
    """{tag principal: quantidade} (soma = numero de noticias)."""
    out = {}
    for n in noticias:
        t = principal(n)
        out[t] = out.get(t, 0) + 1
    return out


def juntar(*listas, limite=None):
    """Une listas de noticias sem repetir link, mais recentes primeiro; textos (avisos) sao ignorados."""
    vistas = {}
    for lst in listas:
        for n in lst if isinstance(lst, list) else ():
            vistas.setdefault(n.get("link"), n)
    out = sorted(vistas.values(), key=lambda n: n.get("data") or dt.date.min, reverse=True)
    return out[:limite] if limite else out


def por_mes(noticias):
    """{tag principal: {"AAAA-MM": qtd}} sem repetir link (grafico do painel)."""
    out = {}
    for n in juntar(list(noticias)):
        if n.get("data"):
            mes = out.setdefault(principal(n), {})
            k = n["data"].strftime("%Y-%m")
            mes[k] = mes.get(k, 0) + 1
    return out


def demo(i, hoje=None):
    """Noticias ficticias para o modo --demo (nunca publicado): links em exemplo.invalid."""
    hoje = hoje or dt.date.today()
    titulos = ("Deputado apresenta projeto de lei sobre saúde na Câmara",
               "Pesquisa eleitoral mostra candidato à frente na campanha",
               "Polícia Federal faz operação contra desvio de verbas",
               "Declaração de bens ao TSE mostra crescimento do patrimônio",
               "Tribunal de Contas julga recurso da prefeitura",
               "Partido anuncia nova liderança da bancada")
    out = []
    for j, t in enumerate(titulos[: 3 + i % 4]):
        out.append(dict(titulo=t, veiculo="Jornal Fictício", data=hoje - dt.timedelta(days=9 * j + i),
                        link=f"https://exemplo.invalid/demo/{i}/{j}", tags=classificar(t)))
    return out
