"""Equipe do gabinete (#66): quantas pessoas trabalham no gabinete de cada parlamentar federal em exercicio. So o
numero sai daqui: nomes, cargos e salarios ficam na fonte oficial. Fontes oficiais e gratuitas:
  Camara: pagina oficial "Pessoal de gabinete" de cada deputado (https://www.camara.leg.br/deputados/{id}/pessoal-gabinete)
  Senado: Dados Abertos administrativos, servidores ativos (https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/
          servidores/ativos), lotados no gabinete ou nos escritorios de apoio do senador
Sem resposta da fonte: None (a pagina mostra "Fonte nao encontrada"); pessoa fora da lista: "Nao informado"."""
import datetime as dt, re, sys, time, urllib.request
import projetos
from cota import norm

CAMARA = "https://www.camara.leg.br/deputados/{id}/pessoal-gabinete"
SENADO = "https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/servidores/ativos"
SENADO_LINK = "https://www6g.senado.leg.br/transparencia/sen/{cod}/pessoal/?local=gabinete&vinculo=todos"
VALIDADE_S = 7 * 86400  # equipe muda com nomeacoes e exoneracoes: consulta de novo a cada semana
UA = "alerta-patrimonial/1.0"
# "Gabinete do Senador X", "Escritorio de Apoio n 1 da Senadora X", "Escritorio Apoio 1 do Senador X"
RE_LOTACAO_SEN = re.compile(r"^(?:GABINETE|ESCRITORIO)\b.*?\bSENADORA?\s+(.+)$")
RE_PERIODO = re.compile(r"De (\d{2}/\d{2}/\d{4})(?: a (\d{2}/\d{2}/\d{4}))?")


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


def _data(s):
    return dt.datetime.strptime(s, "%d/%m/%Y").date()


def contar_camara(html, hoje=None):
    """Pessoas com exercicio em andamento na tabela "Pessoal de gabinete" (sem data de saida ou saida no futuro)."""
    hoje = hoje or dt.date.today()
    return sum(1 for ini, fim in RE_PERIODO.findall(html or "") if _data(ini) <= hoje and (not fim or _data(fim) >= hoje))


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


def coletar(parl, chaves, cache=None, pausa=0.5, buscar_html=_html, buscar_json=projetos._json):
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
        guardado = cache.get(f"gabinete:camara:{p['_id']}") if cache else None
        if guardado:
            out[ch] = guardado
            continue
        h = buscar_html(link)
        if h is None:
            out[ch] = None
        else:
            n = contar_camara(h)
            out[ch] = dict(pessoas=n or None, link=link)
            if cache:
                cache.set(f"gabinete:camara:{p['_id']}", out[ch])
        if pausa:
            time.sleep(pausa)  # respeita o limite do site da Camara (429)
    if cache:
        cache.salvar()
    achados = sum(1 for v in out.values() if v and v["pessoas"])
    print(f"Equipe do gabinete: {achados} de {len(out)} parlamentares com pagina.")
    return out
