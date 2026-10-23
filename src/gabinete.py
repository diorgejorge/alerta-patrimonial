"""Equipe do gabinete (#66): quantas pessoas trabalham no gabinete de cada parlamentar federal em exercicio. So o
numero sai daqui: nomes, cargos e salarios ficam na fonte oficial. Fontes oficiais e gratuitas:
  Camara: pagina oficial "Pessoal de gabinete" de cada deputado (https://www.camara.leg.br/deputados/{id}/pessoal-gabinete)
  Senado: Dados Abertos administrativos, servidores ativos (https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/
          servidores/ativos), lotados no gabinete ou nos escritorios de apoio do senador
Sem resposta da fonte: None (a pagina mostra "Fonte nao encontrada"); pessoa fora da lista: "Nao informado"."""
import datetime as dt, html, re, sys, time, urllib.request
import projetos
from cota import norm

CAMARA = "https://www.camara.leg.br/deputados/{id}/pessoal-gabinete"
SENADO = "https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/servidores/ativos"
SENADO_LINK = "https://www6g.senado.leg.br/transparencia/sen/{cod}/pessoal/?local=gabinete&vinculo=todos"
VALIDADE_S = 6 * 86400  # equipe muda com nomeacoes e exoneracoes: consulta de novo em toda carga semanal
UA = "alerta-patrimonial/1.0"
e = html.escape
# "Gabinete do Senador X", "Escritorio de Apoio n 1 da Senadora X", "Escritorio Apoio 1 do Senador X"
RE_LOTACAO_SEN = re.compile(r"^(?:GABINETE|ESCRITORIO)\b.*?\bSENADORA?\s+(.+)$")
# tabela "Em exercicio": "Desde 18/02/2026"; o historico usa "De 05/04/2021 a 31/01/2023" e fica fora
RE_EM_EXERCICIO = re.compile(r">\s*Desde (\d{2}/\d{2}/\d{4})\s*<")


def _html(url, timeout=60, tentativas=3):
    """Texto da pagina; None se falhar (com nova tentativa, pausa maior em 429)."""
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as ex:
            if n == tentativas - 1:
                print(f"[aviso] {url} indisponivel: {ex}", file=sys.stderr)
                return None
            time.sleep((30 if "429" in str(ex) else 2) + 4 * n)


def contar_camara(pagina, hoje=None):
    """Pessoas na tabela "Em exercicio" da pagina "Pessoal de gabinete" (inicio ate hoje)."""
    hoje = hoje or dt.date.today()
    return sum(1 for ini in RE_EM_EXERCICIO.findall(pagina or "") if dt.datetime.strptime(ini, "%d/%m/%Y").date() <= hoje)


def nome_lotacao_senado(lotacao):
    """Nome do senador na lotacao ('Gabinete do Senador Beto Faro' -> 'BETO FARO'); None se nao e gabinete."""
    m = RE_LOTACAO_SEN.match(norm(lotacao))
    return m.group(1).strip() if m else None


def contar_senado(servidores):
    """{nome normalizado do senador: pessoas ativas no gabinete e escritorios de apoio}, sem o proprio senador."""
    out = {}
    for s in servidores or ():
        if str(s.get("vinculo") or "").upper() == "PARLAMENTAR":
            continue
        nome = nome_lotacao_senado((s.get("lotacao") or {}).get("nome"))
        if nome:
            out[nome] = out.get(nome, 0) + 1
    return out


def _senador(p, por_nome):
    for n in (p.get("nome"), p.get("_nome_completo")):
        if norm(n) in por_nome:
            return por_nome[norm(n)]
    return None


def coletar(parl, chaves, cache=None, pausa=0.5, buscar_html=_html, buscar_json=projetos._json, hoje=None):
    """{chave TSE: dict(pessoas, link) ou None} dos parlamentares em exercicio que tem pagina (`chaves`).
    None = fonte nao respondeu; parlamentar sem registro fica fora (a pagina mostra "Nao informado")."""
    alvo = [p for p in parl if p.get("_chave") in chaves]
    out, senado = {}, None
    if any(p["casa"] == "senado" for p in alvo):
        d = buscar_json(SENADO)
        senado = contar_senado(d) if isinstance(d, list) else None
    for p in alvo:
        ch = p["_chave"]
        if ch in out:
            continue
        if p["casa"] == "senado":
            n = _senador(p, senado) if senado is not None else None
            out[ch] = (dict(pessoas=n, link=SENADO_LINK.format(cod=p["_id"])) if n
                       else None if senado is None else dict(pessoas=None, link=SENADO_LINK.format(cod=p["_id"])))
            continue
        link = CAMARA.format(id=p["_id"])
        guardado = cache.get(f"gabinete:camara:{p['_id']}") if cache is not None else None
        if guardado:
            out[ch] = guardado
            continue
        h = buscar_html(link)
        if h is None:
            out[ch] = None
        else:
            n = contar_camara(h, hoje)
            out[ch] = dict(pessoas=n or None, link=link)
            if cache is not None:
                cache.set(f"gabinete:camara:{p['_id']}", out[ch])
        if pausa:
            time.sleep(pausa)  # respeita o limite do site da Camara (429)
    if cache is not None:
        cache.salvar()
    achados = sum(1 for v in out.values() if v and v["pessoas"])
    print(f"Equipe do gabinete: {achados} de {len(out)} parlamentares com pagina.")
    return out


# equipe ficticia para o --demo (sem internet): so para ver o bloco preenchido
DEMO = dict(pessoas=23, link=CAMARA.format(id="000000"))



def secao(r, cargo, consultado=False):
    """HTML do bloco "Equipe do gabinete" da pagina da pessoa. r: dict(pessoas, link) ou None.
    `consultado`: a pessoa e parlamentar federal em exercicio e a fonte foi consultada (None = fonte fora do ar)."""
    if r is None:
        if consultado:
            return ('<p class="vazio"><b>Fonte não encontrada</b>: a página oficial da Câmara ou do Senado não respondeu '
                    "nesta execução.</p>")
        return '<p class="vazio"><b>Não informado</b>: a equipe só é publicada para deputados federais e senadores em exercício.</p>'
    link = str(r.get("link") or "")
    fonte = (f' <a href="{e(link)}" target="_blank" rel="noopener">Ver a lista oficial</a>'
             if link.startswith("https://") else "")
    n = r.get("pessoas")
    if not n:
        return f'<p class="vazio"><b>Não informado</b>: a fonte oficial não lista ninguém no gabinete hoje.{fonte}</p>'
    senado = "senado" in link
    onde = "no gabinete em Brasília e nos escritórios de apoio no estado" if senado else "no gabinete"
    quem = "servidores efetivos e comissionados" if senado else "secretários parlamentares e cargos de natureza especial"
    verbo = "pessoa trabalha" if n == 1 else "pessoas trabalham"
    return (f'<p><b>{n}</b> {verbo} {onde} hoje, pagas com dinheiro público.</p>'
            f'<p class="mut"><small>Contagem de {quem} em exercício, como publicado pela fonte oficial. Nomes e salários '
            f"ficam só na fonte.{fonte}</small></p>")
