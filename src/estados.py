"""Dossie por estado (#53): gasto do governo estadual, verbas recebidas da Uniao e parlamentares autores de emendas
com gasto no estado. Fontes oficiais e gratuitas:
  SICONFI (Tesouro Nacional, sem chave): DCA Anexo I-E (despesa por funcao) e I-C (receitas vindas da Uniao)
  Portal da Transparencia (so pela API oficial, chave-api-dados): emendas com o local do gasto, ultimos 4 anos
  Camara/Senado (parlamentares.py): quem esta em exercicio, para ligar o autor da emenda a pagina dele
  TSE (pipeline.py): deputados estaduais e distritais eleitos em exercicio
O unico elo oficial entre parlamentar e gasto e a autoria da emenda: o texto diz "autor da emenda", nunca "envolvido".
Pagina leve por UF (docs/estado/UF.html); municipios e deputados estaduais vao em docs/estado/UF.json, baixado so
quando o leitor abre a secao. Sem CPF/CNPJ em nenhum arquivo."""
import csv, datetime as dt, html, json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from pathlib import Path
import transparencia

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
LINK_SICONFI = "https://siconfi.tesouro.gov.br/siconfi/pages/public/consulta_finbra/finbra_list.jsf"
LINK_EMENDAS = "https://portaldatransparencia.gov.br/emendas"
ANOS_EMENDAS = 4
TEMPO_EMENDAS, TEMPO_MUNICIPIOS = 50 * 60, 40 * 60  # o Action roda 1x por semana: pode demorar
TOP_FUNCOES, TOP_RECEITAS, TOP_AUTORES, TOP_AUTORES_MUN, TOP_CARIMBOS = 5, 6, 10, 3, 5
MAX_FALHAS_SEGUIDAS = 10  # SICONFI fora do ar ou bloqueando: para de consultar municipios nesta execucao
NAO_ACHOU = "Fonte não encontrada"
e = html.escape

UFS = {"AC": ("12", "Acre"), "AL": ("27", "Alagoas"), "AP": ("16", "Amapá"), "AM": ("13", "Amazonas"),
       "BA": ("29", "Bahia"), "CE": ("23", "Ceará"), "DF": ("53", "Distrito Federal"), "ES": ("32", "Espírito Santo"),
       "GO": ("52", "Goiás"), "MA": ("21", "Maranhão"), "MT": ("51", "Mato Grosso"), "MS": ("50", "Mato Grosso do Sul"),
       "MG": ("31", "Minas Gerais"), "PA": ("15", "Pará"), "PB": ("25", "Paraíba"), "PR": ("41", "Paraná"),
       "PE": ("26", "Pernambuco"), "PI": ("22", "Piauí"), "RJ": ("33", "Rio de Janeiro"),
       "RN": ("24", "Rio Grande do Norte"), "RS": ("43", "Rio Grande do Sul"), "RO": ("11", "Rondônia"),
       "RR": ("14", "Roraima"), "SC": ("42", "Santa Catarina"), "SP": ("35", "São Paulo"), "SE": ("28", "Sergipe"),
       "TO": ("17", "Tocantins")}
TIPOS_RECEITA = {"legais": "Obrigatório por lei", "voluntarias": "Convênios (negociados)",
                 "especiais": "Emendas Pix"}
EMENDAS_LEIGO = {"Emenda Individual - Transferências Especiais": "Individual, tipo Pix (sem destino definido)",
                 "Emenda Individual - Transferências com Finalidade Definida": "Individual, com destino definido",
                 "Emenda de Bancada": "Da bancada do estado", "Emenda de Comissão": "De comissão da Câmara ou do Senado",
                 "Emenda de Relator": "Do relator (orçamento secreto)"}
# nome da funcao no balanco -> como qualquer pessoa entende (o nome oficial fica entre parenteses)
FUNCOES_LEIGO = {"Encargos Especiais": "Dívidas, juros e repasses", "Judiciária": "Tribunais de Justiça",
                 "Essencial à Justiça": "Ministério Público e Defensoria", "Legislativa": "Assembleia e Tribunal de Contas",
                 "Previdência Social": "Aposentadorias e pensões", "Administração": "Máquina pública",
                 "Urbanismo": "Cidades (ruas, praças, iluminação)", "Gestão Ambiental": "Meio ambiente",
                 "Desporto e Lazer": "Esporte e lazer", "Organização Agrária": "Reforma agrária"}
CARGOS_ESTADUAIS = {"DEPUTADO ESTADUAL", "DEPUTADO DISTRITAL"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


UF_POR_NOME = {norm(nome): uf for uf, (_, nome) in UFS.items()}
_num = transparencia._num


def brl_curto(v):
    """R$ 1,2 bi / R$ 350,4 mi / R$ 12 mil / R$ 950; None = Não informado."""
    if v is None:
        return "Não informado"
    for lim, suf in ((1e9, " bi"), (1e6, " mi"), (1e3, " mil")):
        if abs(v) >= lim:
            n = f"{v / lim:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")
            return "R$ " + n.removesuffix(",0") + suf
    return f"R$ {v:,.0f}".replace(",", ".")


def relativo(u):
    """Link do site (pessoa/p0001.html) visto de docs/estado/; link externo fica como esta."""
    if not u or not isinstance(u, str):
        return None
    return u if re.match(r"[a-z][a-z0-9+.-]*:", u, re.I) else "../" + u.lstrip("/")


def ano_dca(hoje=None):
    """Ultimo ano com DCA entregue por todos: o prazo e 30/abr do ano seguinte; folga ate junho."""
    hoje = hoje or dt.date.today()
    return hoje.year - (1 if hoje.month >= 7 else 2)


def mandato_estadual(anos, hoje=None):
    """Ano da eleicao dos deputados estaduais em exercicio (posse em 1/fev do ano seguinte)."""
    hoje = hoje or dt.date.today()
    validos = [a for a in anos if dt.date(int(a) + 1, 2, 1) <= hoje]
    return max(validos) if validos else None


# ---------------------------------------------------------------- SICONFI
def duracao(seg):
    """Segundos -> "1h 05min", "12min 30s" ou "8s"."""
    seg = int(seg)
    if seg >= 3600:
        return f"{seg // 3600}h {seg % 3600 // 60:02d}min"
    return f"{seg // 60}min {seg % 60:02d}s" if seg >= 60 else f"{seg}s"


class Andamento:
    """Andamento no log do Actions: etapa, contador, %, tempo decorrido e estimativa do que falta (no maximo uma
    linha a cada `intervalo` segundos por etapa), e um resumo em tabela no GITHUB_STEP_SUMMARY. So contagens e
    nomes de UF/municipio: nada de CPF/CNPJ."""
    ETAPAS = ("Estados no SICONFI", "Emendas no Portal", "Municípios no SICONFI", "Páginas")

    def __init__(self, intervalo=30, relogio=time.monotonic, saida=print):
        self.intervalo, self.relogio, self.saida = intervalo, relogio, saida
        self.inicio = relogio()
        self.feitas = []  # (nome, segundos, detalhe)
        self._atual = None

    def etapa(self, nome):
        self._fechar()
        self._atual = dict(nome=nome, ini=self.relogio(), ultimo=float("-inf"), detalhe="")
        n = self.ETAPAS.index(nome) + 1 if nome in self.ETAPAS else len(self.feitas) + 1
        self.saida(f"[{n}/{len(self.ETAPAS)}] {nome} · {duracao(self.relogio() - self.inicio)} desde o início", flush=True)

    def passo(self, i, total, rotulo=""):
        """Mostra i/total da etapa atual, com % e estimativa; total None = so contagem."""
        a, agora = self._atual, self.relogio()
        if a is None or (i != total and agora - a["ultimo"] < self.intervalo):
            return
        a["ultimo"] = agora
        gasto = agora - a["ini"]
        if total:
            pct = i / total
            falta = f" · faltam ~{duracao(gasto / pct * (1 - pct))}" if 0 < pct < 1 else ""
            conta = f"{i:,}/{total:,} · {pct:.0%}".replace(",", ".")
        else:
            conta, falta = f"{i:,}".replace(",", "."), ""
        self.saida(f"    {a['nome']}: {rotulo + ' · ' if rotulo else ''}{conta} · {duracao(gasto)}{falta}", flush=True)

    def fim(self, detalhe):
        """Resultado da etapa atual (vai para o resumo)."""
        if self._atual:
            self._atual["detalhe"] = detalhe

    def _fechar(self):
        if self._atual:
            a = self._atual
            self.feitas.append((a["nome"], self.relogio() - a["ini"], a["detalhe"]))
            self._atual = None

    def resumo(self, arquivo=None):
        """Fecha a etapa atual, imprime o total e grava a tabela no GITHUB_STEP_SUMMARY (se houver)."""
        self._fechar()
        total = duracao(self.relogio() - self.inicio)
        self.saida(f"Dossiê por estado: concluído em {total}.", flush=True)
        arquivo = arquivo or os.getenv("GITHUB_STEP_SUMMARY")
        if not arquivo:
            return
        linhas = ["## Dossiê por estado", "", "| Etapa | Tempo | Resultado |", "|---|---|---|"]
        linhas += [f"| {n} | {duracao(s)} | {d or '-'} |" for n, s, d in self.feitas]
        linhas += [f"| **Total** | **{total}** | |", ""]
        with open(arquivo, "a", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")


class Buscador:
    """GET de JSON com ritmo controlado. O SICONFI responde 429 (Too Many Requests) se receber consultas seguidas:
    espera `intervalo` entre consultas e, no 429, o Retry-After ou um recuo crescente (10s, 30s, 60s)."""
    RECUOS = (10, 30, 60)

    def __init__(self, intervalo=1.0, timeout=60, abrir=urllib.request.urlopen, dormir=time.sleep):
        self.intervalo, self.timeout, self.abrir, self.dormir = intervalo, timeout, abrir, dormir
        self.ultimo, self.req, self.falhas = 0.0, 0, 0

    def __call__(self, url):
        for recuo in self.RECUOS + (None,):
            espera = self.intervalo - (time.monotonic() - self.ultimo)
            if espera > 0:
                self.dormir(espera)
            self.ultimo = time.monotonic()
            self.req += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": transparencia.UA, "Accept": "application/json"})
                with self.abrir(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as ex:
                if ex.code != 429 and ex.code < 500 or recuo is None:
                    break
                pedido = str((ex.headers or {}).get("Retry-After") or "")
                self.dormir(int(pedido) if pedido.isdigit() else recuo)
            except Exception:
                if recuo is None:
                    break
                self.dormir(recuo)
        self.falhas += 1
        return None


def siconfi(buscar, recurso, **params):
    """Itens de um recurso do SICONFI, juntando as paginas (offset); None se a fonte falhar."""
    itens, offset = [], 0
    while True:
        d = buscar(f"{SICONFI}/{recurso}?" + urllib.parse.urlencode(dict(params, offset=offset)))
        if not isinstance(d, dict):
            return None
        lote = d.get("items") or []
        itens += lote
        if not (d.get("hasMore") and lote):
            return itens
        offset += len(lote)


RE_FUNCAO = re.compile(r"^(\d{2})\s*-\s*(.+)$")
RE_RECEITA = re.compile(r"^((?:1\.7\.1|2\.4\.1)\.(\d)\.(\d{2}))\.0\.0\s*-\s*(.+)$")


def despesa_por_funcao(itens):
    """[(funcao, valor liquidado)] do DCA Anexo I-E, maior primeiro. A mesma funcao reaparece no bloco
    intraorcamentario com valor menor: fica o maior."""
    por = {}
    for it in itens or ():
        if norm(it.get("coluna")) != "DESPESAS LIQUIDADAS":
            continue
        m = RE_FUNCAO.match(str(it.get("conta") or "").strip())
        v = _num(it.get("valor"))
        if m and v > por.get(m[1], ("", 0.0))[1]:
            por[m[1]] = (m[2].strip(), v)
    return sorted(por.values(), key=lambda x: -x[1])


def tipo_receita(rotulo):
    r = norm(rotulo)
    if "CONVENIO" in r:
        return "voluntarias"
    if "ESPECIA" in r and "TRANSFERENCIA" in r:
        return "especiais"
    return "legais"


def receitas_uniao(itens):
    """[(rotulo, valor, tipo)] das receitas brutas vindas da Uniao (1.7.1 correntes, 2.4.1 capital) no DCA Anexo I-C,
    maior primeiro. Usa o nivel mais detalhado com valor (ex.: 1.7.1.1.51 Cota-Parte do FPE); o rotulo e o da fonte."""
    detalhe, grupo = {}, {}
    for it in itens or ():
        if norm(it.get("coluna")) != "RECEITAS BRUTAS REALIZADAS":
            continue
        m = RE_RECEITA.match(str(it.get("conta") or "").strip())
        v = _num(it.get("valor"))
        if not m or v <= 0 or m[2] == "0":
            continue
        alvo = grupo if m[3] == "00" else detalhe
        alvo.setdefault(m[1], (m[4].strip(), v))
    # grupo sem nenhum detalhe com valor entra inteiro (nao soma duas vezes o mesmo dinheiro)
    com_detalhe = {c.rsplit(".", 1)[0] for c in detalhe}
    linhas = list(detalhe.values()) + [v for c, v in grupo.items() if c.rsplit(".", 1)[0] not in com_detalhe]
    somadas = {}
    for r, v in linhas:  # a fonte repete o mesmo rotulo em contas diferentes: vira uma linha so
        r = rotulo_limpo(r)
        somadas[r] = somadas.get(r, 0.0) + v
    return sorted(((r, round(v, 2), tipo_receita(r)) for r, v in somadas.items()), key=lambda x: -x[1])


def rotulo_limpo(r):
    """O SICONFI troca o travessao por "¿" (erro de codificacao na origem)."""
    return re.sub(r"\s+", " ", str(r).replace("\u00bf", "–")).strip()


VERSAO_DCA = 1  # mude ao mudar despesa_por_funcao/receitas_uniao: invalida os resumos guardados


def dca(buscar, id_ente, anexo, ano, ler, cache=None):
    """Resumo `ler(itens)` de um anexo do DCA; tenta o ano anterior se o ano ainda nao foi entregue.
    Guarda so o resumo (poucas linhas), inclusive o vazio, para a execucao seguinte continuar de onde esta parou.
    (ano, resumo) ou (None, None) se a fonte falhar."""
    for a in (ano, ano - 1):
        chave = ("dca", VERSAO_DCA, str(id_ente), anexo, a)
        resumo = cache.get(chave) if cache else None
        if resumo is None:
            itens = siconfi(buscar, "dca", an_exercicio=a, no_anexo=anexo, id_ente=id_ente)
            if itens is None:
                return None, None
            resumo = ler(itens)
            if cache:
                cache.set(chave, resumo)
        if resumo:
            return a, resumo
    return None, []


def financas(buscar, id_ente, ano, cache=None):
    """Gasto por funcao e verbas da Uniao de um ente. Falha da fonte = "falha"; ano sem entrega = dados vazios."""
    a_desp, desp = dca(buscar, id_ente, "DCA-Anexo I-E", ano, despesa_por_funcao, cache)
    a_rec, rec = dca(buscar, id_ente, "DCA-Anexo I-C", ano, receitas_uniao, cache)
    return dict(ano_despesa=a_desp, despesa="falha" if desp is None else desp,
                ano_receita=a_rec, receita="falha" if rec is None else rec)


def municipios(buscar, entes, ano, cache=None, tempo_max=TEMPO_MUNICIPIOS, prog=None):
    """{cod_ibge: dict(total, tipos)} das verbas da Uniao a cada municipio (DCA I-C), em partes: cada municipio lido
    fica no cache, e a execucao seguinte so consulta quem falta. Com prazo e parada apos falhas seguidas: quem fica
    de fora sai sem valor ("Não informado") nesta semana."""
    fim, out, seguidas, consultados = time.monotonic() + tempo_max, {}, 0, 0
    for n, ent in enumerate(entes, 1):
        cod = str(ent["cod"])
        if time.monotonic() >= fim or seguidas >= MAX_FALHAS_SEGUIDAS:
            motivo = "prazo esgotado" if seguidas < MAX_FALHAS_SEGUIDAS else f"{seguidas} falhas seguidas"
            print(f"[aviso] SICONFI municipios: {motivo} em {n - 1}/{len(entes)}; o resto entra pelo cache nas "
                  f"proximas execucoes", file=sys.stderr)
            break
        antes = getattr(buscar, "req", 0)
        _, rec = dca(buscar, cod, "DCA-Anexo I-C", ano, receitas_uniao, cache)
        if getattr(buscar, "req", 0) > antes:
            consultados += 1
            if cache and consultados % 200 == 0:  # se o job cair, o que ja foi lido nao se perde
                cache.salvar()
        seguidas = seguidas + 1 if rec is None else 0
        if rec:
            tipos = {}
            for _, v, t in rec:
                tipos[t] = tipos.get(t, 0.0) + v
            out[cod] = dict(total=round(sum(tipos.values()), 2), tipos={k: round(v, 2) for k, v in tipos.items()})
        if prog:
            prog.passo(n, len(entes), f"{ent['nome']} ({ent['uf']}), {consultados} consultados agora")
    print(f"SICONFI municipios: {len(out)}/{len(entes)} com verbas da Uniao, {consultados} consultados nesta execucao.")
    return out


def entes_municipais(buscar):
    """[dict(cod, nome, uf)] dos municipios no SICONFI (o CNPJ do ente nao e guardado); None se falhar."""
    itens = siconfi(buscar, "entes")
    if itens is None:
        return None
    return [dict(cod=str(it.get("cod_ibge")), nome=str(it.get("ente") or "").strip(), uf=str(it.get("uf") or "").upper())
            for it in itens if str(it.get("esfera") or "").upper() == "M" and it.get("cod_ibge")]


# ---------------------------------------------------------------- emendas (Portal da Transparencia)
def local(s):
    """Local do gasto da emenda -> (UF, None) para o estado, (UF, MUNICIPIO) para municipio; None se nacional etc."""
    s = str(s or "").strip()
    m = re.match(r"^(.+?)\s*-\s*([A-Z]{2})$", s)
    if m and m[2] in UFS:
        return m[2], norm(m[1])
    m = re.match(r"^(.+?)\s*\(UF\)$", s, re.I)
    uf = UF_POR_NOME.get(norm(m[1])) if m else None
    return (uf, None) if uf else None


def enxuta(d):
    """So o que a pagina usa (cabe no cache e nao carrega dado pessoal)."""
    return dict(autor=str(d.get("nomeAutor") or d.get("autor") or "").strip(), tipo=str(d.get("tipoEmenda") or "").strip(),
                local=str(d.get("localidadeDoGasto") or "").strip(), funcao=str(d.get("funcao") or "").strip(),
                subfuncao=str(d.get("subfuncao") or "").strip(), ano=int(_num(d.get("ano"))) or None,
                codigo=str(d.get("codigoEmenda") or "").strip(), empenhado=round(_num(d.get("valorEmpenhado")), 2),
                pago=round(_num(d.get("valorPago")) + _num(d.get("valorRestoPago")), 2))


VERSAO_EMENDAS = 2  # mude ao mudar enxuta(): invalida os anos guardados


def emendas(api, anos, cache=None, hoje=None, prog=None):
    """Emendas dos `anos` (lista enxuta) e os anos que faltaram. O ano so vai para o cache se veio inteiro; anos
    recentes sao sempre relidos (restos a pagar continuam sendo pagos)."""
    hoje = hoje or dt.date.today()
    out, faltou = [], []
    for ano in anos:
        guardavel = cache is not None and ano < hoje.year - 1
        lista = cache.get(("emendas", VERSAO_EMENDAS, ano)) if guardavel else None
        if lista is None:
            antes = api.falhas
            ler = (lambda pg, n, ano=ano: prog.passo(n, None, f"ano {ano}, página {pg}")) if prog else None
            bruto = api.paginas("/emendas", max_paginas=5000, ao_ler=ler, ano=ano) if api.ativa() else None
            if bruto is None or api.falhas != antes:
                faltou.append(ano)
            lista = [enxuta(d) for d in bruto or ()]
            if guardavel and ano not in faltou:
                cache.set(("emendas", VERSAO_EMENDAS, ano), lista)
        out += lista
        if prog:
            prog.saida(f"    ano {ano}: {len(lista):,} emendas{' (faltou)' if ano in faltou else ''}".replace(",", "."), flush=True)
    return out, faltou


ANOS_PARADA = 2  # emenda empenhada ha 2 anos ou mais sem nenhum pagamento
CARIMBO_PARADA = "Emenda parada"


def paradas(lista, hoje=None):
    """{uf: [emendas empenhadas ha ANOS_PARADA anos ou mais sem nenhum pagamento]}, maior empenho primeiro."""
    corte = (hoje or dt.date.today()).year - ANOS_PARADA
    out = {}
    for d in lista:
        lc = local(d["local"])
        if lc and d.get("ano") and d["ano"] <= corte and (d.get("empenhado") or 0) > 0 and d["pago"] <= 0:
            out.setdefault(lc[0], []).append(dict(d, municipio=lc[1]))
    for l in out.values():
        l.sort(key=lambda d: -d["empenhado"])
    return out


def execucao(pago, empenhado):
    """Parte do empenhado que ja foi paga, em %; None sem empenho. Pago inclui restos de anos anteriores: limite 100."""
    return min(round(pago / empenhado * 100), 100) if empenhado else None


def coletivo(autor):
    """Bancada, comissao ou relator: nao e uma pessoa."""
    a = norm(autor)
    return a.startswith(("BANCADA", "COMISSAO", "RELATOR", "COM. ")) or "COMISSAO" in a


def agregar(lista):
    """{uf: dict(pago, n, empenhado, tipos{tipo: valor}, autores{autor: [pago, n, empenhado]},
    municipios{MUN: dict(pago, n, autores)})}. n conta as emendas com pagamento; empenhado soma todas (execucao)."""
    por = {}
    for d in lista:
        lc = local(d["local"])
        emp = d.get("empenhado") or 0.0
        if not lc or (d["pago"] <= 0 and emp <= 0):
            continue
        uf, mun = lc
        u = por.setdefault(uf, dict(pago=0.0, n=0, estado=0.0, empenhado=0.0, tipos={}, autores={}, municipios={}))
        a = u["autores"].setdefault(d["autor"] or "Não informado", [0.0, 0, 0.0])
        u["empenhado"] += emp; a[2] += emp
        if d["pago"] <= 0:
            continue
        u["pago"] += d["pago"]; u["n"] += 1
        u["tipos"][d["tipo"] or "Não informado"] = u["tipos"].get(d["tipo"] or "Não informado", 0.0) + d["pago"]
        a[0] += d["pago"]; a[1] += 1
        if mun is None:
            u["estado"] += d["pago"]
            continue
        m = u["municipios"].setdefault(mun, dict(pago=0.0, n=0, autores={}))
        m["pago"] += d["pago"]; m["n"] += 1
        m["autores"][d["autor"]] = m["autores"].get(d["autor"], 0.0) + d["pago"]
    return por


def ligar_autores(autores, uf, parl):
    """Autores ordenados por valor, com cargo e link quando o autor esta em exercicio (parlamentares.py).
    Os parlamentares da UF sem emenda paga no estado entram no fim com zero (tambem e informacao)."""
    por_nome = {}
    for p in parl:
        for n in {norm(p.get("nome"))} | set(p.get("_nomes") or ()):
            por_nome.setdefault((n, p["uf"]), p)
            por_nome.setdefault((n, None), p)
    out, vistos = [], set()
    for autor, (pago, n, emp) in sorted(autores.items(), key=lambda kv: (-kv[1][0], -kv[1][2])):
        p = None if coletivo(autor) else por_nome.get((norm(autor), uf)) or por_nome.get((norm(autor), None))
        if p:
            vistos.add(id(p))
        out.append(dict(autor=autor, nome=p["nome"] if p else autor.title(), pago=round(pago, 2), n=n,
                        empenhado=round(emp, 2),
                        coletivo=coletivo(autor), cargo=p["cargo"] if p else "", partido=p["partido"] if p else "",
                        uf=p["uf"] if p else "", link=relativo(p.get("dossie") or p.get("perfil")) if p else None))
    for p in parl:
        if p["uf"] == uf and id(p) not in vistos:
            out.append(dict(autor=p["nome"], nome=p["nome"], pago=0.0, n=0, empenhado=0.0, coletivo=False, cargo=p["cargo"], partido=p["partido"],
                            uf=uf, link=relativo(p.get("dossie") or p.get("perfil"))))
    return out


# ---------------------------------------------------------------- deputados estaduais (TSE) e Assembleias
def deputados_estaduais(serie, paginas=None, link=None, hoje=None):
    """{uf: [dict(nome, partido, tse, pagina)]} dos eleitos em exercicio. `paginas`: {chave: pagina}; a chave
    (CPF) so liga as bases aqui dentro."""
    if serie is None or not len(serie):
        return {}, None
    est = serie[serie["cargo"].map(norm).isin(CARGOS_ESTADUAIS) & serie["eleito"].astype(bool)]
    ano = mandato_estadual(sorted(set(est["ano"].astype(int))), hoje)
    if ano is None:
        return {}, None
    out = {}
    for r in est[est["ano"].astype(int) == ano].to_dict("records"):
        uf = str(r.get("uf") or "").upper()
        if uf in UFS:
            out.setdefault(uf, []).append(dict(nome=(str(r.get("nome_urna") or "").strip() or str(r["nome"])).title(),
                                               partido=r.get("partido") or "Não informado",
                                               tse=link(r) if link else None,
                                               pagina=relativo((paginas or {}).get(r.get("chave")))))
    for l in out.values():
        l.sort(key=lambda d: norm(d["nome"]))
    return out, ano


def carregar_assembleias(caminho=ROOT / "config" / "assembleias.csv"):
    """{uf: dict(nome, site)} das Assembleias Legislativas (emendas estaduais nao tem base nacional)."""
    try:
        with open(caminho, encoding="utf-8", newline="") as f:
            return {r["uf"].strip().upper(): dict(nome=r["nome"].strip(), site=r["site"].strip()) for r in csv.DictReader(f)}
    except (OSError, KeyError):
        return {}


# ---------------------------------------------------------------- coleta completa
def cliente_portal(chave_api, tempo_max=TEMPO_EMENDAS):
    """Cliente da API do Portal com prazo proprio para as emendas; None sem chave."""
    return transparencia.Api(chave_api, time.monotonic() + tempo_max) if chave_api else None


def abre(url, timeout=20):
    """O link abre (status < 400)? Alguns sites recusam HEAD: tenta GET."""
    for metodo in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=metodo, headers={"User-Agent": transparencia.UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status < 400
        except Exception:
            continue
    return False


def coletar(buscar, api, parl, estaduais=None, ano_est=None, cache=None, hoje=None, checar=None,
            prog=None):
    """Dados de todas as UFs para gerar(). Cada fonte que falha vira NAO_ACHOU na sua secao, sem derrubar o resto.
    parl/estaduais/ano_est: da base gravada pelo pipeline (base())."""
    hoje = hoje or dt.date.today()
    prog = prog or Andamento()
    ano = ano_dca(hoje)
    prog.etapa("Estados no SICONFI")
    fin = {}
    for i, (uf, (cod, _)) in enumerate(UFS.items(), 1):
        fin[uf] = financas(buscar, cod, ano, cache)
        prog.passo(i, len(UFS), uf)
    prog.fim(f"{sum(f['despesa'] != 'falha' for f in fin.values())}/{len(UFS)} com balanço de {ano}")
    prog.etapa("Emendas no Portal")
    anos = list(range(hoje.year - ANOS_EMENDAS + 1, hoje.year + 1))
    lista, faltou = emendas(api, anos, cache, hoje, prog) if api else ([], anos)
    prog.fim(f"{len(lista):,} emendas de {anos[0]} a {anos[-1]}".replace(",", ".")
             + (f"; faltou {', '.join(map(str, faltou))}" if faltou else ""))
    prog.etapa("Municípios no SICONFI")
    entes = entes_municipais(buscar) or []
    mun = municipios(buscar, entes, ano, cache, prog=prog) if entes else {}
    prog.fim(f"{len(mun):,}/{len(entes):,} com verbas da União".replace(",", "."))
    if hasattr(buscar, "req"):
        print(f"SICONFI: {buscar.req} consultas, {buscar.falhas} sem resposta.")
    prog.etapa("Páginas")
    if cache:
        cache.salvar()
    assembleias = carregar_assembleias()
    for a in assembleias.values():  # link que nao abre no Actions vira "Fonte nao encontrada"
        a["ok"] = bool(a["site"]) and (checar(a["site"]) if checar else True)
    return montar(fin, agregar(lista), parl, entes, mun, estaduais or {}, assembleias,
                  dict(anos=anos, faltou=faltou, hoje=hoje.isoformat(), ano_estadual=ano, eleicao_estadual=ano_est,
                       falhou_emendas=len(faltou) == len(anos)), paradas(lista, hoje))


BASE = ROOT / "data" / "estados_base.json"


def base(parl, serie=None, paginas=None, link=None, hoje=None):
    """O que o dossie por estado precisa do pipeline principal, gravado em data/estados_base.json para o workflow
    proprio (estados.yml) rodar depois, sem segurar o painel: parlamentares em exercicio e deputados estaduais.
    So dados publicos (nome, cargo, partido, UF, links); CPF e chave ficam de fora."""
    estaduais, ano_est = deputados_estaduais(serie, paginas, link, hoje)
    pub = [dict(nome=p["nome"], cargo=p["cargo"], partido=p["partido"], uf=p["uf"], dossie=p.get("dossie"),
                perfil=p.get("perfil"), _nomes=sorted(p.get("_nomes") or ())) for p in parl]
    return dict(parlamentares=pub, estaduais=estaduais, eleicao_estadual=ano_est)


def main(raiz=ROOT):
    """Workflow "2 · Dossiê por estado" (estados.yml): le a base do pipeline, consulta SICONFI, Portal e S2iD e grava docs/estado."""
    from cache import Cache
    from ids import varrer
    arq = Path(raiz) / "data" / BASE.name
    try:
        b = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        sys.exit(f"Sem {arq.name} ({ex!r}): rode antes o workflow '1 · Dados dos políticos'.")
    seg = os.getenv("ID_SEGREDO")
    cache = Cache(Path(raiz) / "data" / "cache" / "estados.cache", 90 * 86400, seg) if seg else None
    prog = Andamento()
    pag, extra = coletar(Buscador(), cliente_portal(os.getenv("TRANSPARENCIA_TOKEN")), b["parlamentares"],
                         b["estaduais"], b["eleicao_estadual"], cache, checar=abre, prog=prog)
    docs = Path(raiz) / "docs"
    n = gerar(docs, pag, extra, dt.datetime.now().strftime('%Y-%m-%d %H:%M'))
    prog.fim(f"{n} páginas geradas")
    prog.resumo()
    if varrer(docs / "estado"):
        print("[aviso] CPF/CNPJ removido de paginas do dossie por estado", file=sys.stderr)


def _contar(lista, campo):
    """{valor normalizado do campo: quantas} (municipio None = o estado como um todo)."""
    out = {}
    for d in lista:
        k = norm(d[campo]) if d[campo] else None
        out[k] = out.get(k, 0) + 1
    return out


def montar(fin, emd, parl, entes, mun, estaduais, assembleias, meta, parad=None):
    """{uf: dados da pagina} + {uf: dados sob demanda (municipios e deputados estaduais)}.
    parad: {uf: [emendas paradas]} (paradas())."""
    paginas, extras, por_uf = {}, {}, {}
    for ent in entes:
        por_uf.setdefault(ent["uf"], {})[norm(ent["nome"])] = ent
    for uf, (_, nome) in UFS.items():
        u = emd.get(uf) or dict(pago=0.0, n=0, estado=0.0, empenhado=0.0, tipos={}, autores={}, municipios={})
        f = fin.get(uf) or {}
        paginas[uf] = dict(uf=uf, nome=nome, financas=f, emendas=dict(pago=round(u["pago"], 2), n=u["n"],
                           empenhado=round(u["empenhado"], 2),
                           estado=round(u["estado"], 2), tipos=sorted(u["tipos"].items(), key=lambda kv: -kv[1])),
                           autores=ligar_autores(u["autores"], uf, parl), assembleia=assembleias.get(uf), meta=meta,
                           paradas=(parad or {}).get(uf, []))
        conta = lambda chave, campo: _contar(paginas[uf][chave], campo)
        par_autor, par_mun = conta("paradas", "autor"), conta("paradas", "municipio")
        quem = {}
        for a in paginas[uf]["autores"]:
            a["paradas"] = par_autor.get(norm(a["autor"]), 0)
            quem.setdefault(norm(a["autor"]), a)
        for d in paginas[uf]["paradas"]:  # nome e link do autor como na lista
            a = quem.get(norm(d["autor"])) or {}
            d.update(autor_nome=a.get("nome") or d["autor"].title(), autor_link=a.get("link"))
        lm = []
        nomes_mun = por_uf.get(uf, {})
        for ent in nomes_mun.values():
            em = u["municipios"].get(norm(ent["nome"])) or {}
            uniao = mun.get(ent["cod"])
            if not em and not uniao and not par_mun.get(norm(ent["nome"])):
                continue
            top = sorted((em.get("autores") or {}).items(), key=lambda kv: -kv[1])[:TOP_AUTORES_MUN]
            lm.append([ent["nome"], round(em.get("pago", 0.0), 2), em.get("n", 0),
                       uniao["total"] if uniao else None, [[a.title(), round(v, 2)] for a, v in top],
                       par_mun.get(norm(ent["nome"]), 0)])
        for nm, em in u["municipios"].items():  # municipio da emenda que nao bateu com o SICONFI: entra assim mesmo
            if nm not in nomes_mun:
                top = sorted(em["autores"].items(), key=lambda kv: -kv[1])[:TOP_AUTORES_MUN]
                lm.append([nm.title(), round(em["pago"], 2), em["n"], None, [[a.title(), round(v, 2)] for a, v in top],
                           par_mun.get(nm, 0)])
        lm.sort(key=lambda m: -(m[1] + (m[3] or 0)))
        extras[uf] = dict(municipios=lm, ano_uniao=meta.get("ano_estadual"), siconfi_municipios=bool(mun),
                          estaduais=estaduais.get(uf, []), eleicao=meta.get("eleicao_estadual"))
    return paginas, extras


# ---------------------------------------------------------------- html
def _barras(linhas, total):
    """Lista de barras horizontais: [(rotulo, valor, extra_html)]."""
    if not linhas:
        return ""
    topo = max(v for _, v, _ in linhas) or 1
    itens = "".join(
        f'<li><span class="rot">{e(r)}{x}</span><span class="val">{brl_curto(v)}'
        f'<small>{_pct(v, total)}</small></span>'
        f'<span class="barra" aria-hidden="true"><i style="width:{max(v / topo * 100, 1):.1f}%"></i></span></li>'
        for r, v, x in linhas) if total else ""
    return f'<ul class="barras">{itens}</ul>'


def _pct(v, total):
    p = v / total * 100
    return "menos de 1%" if 0 < p < 0.5 else f"{p:.0f}%"


def _mais(linhas, total, rotulo):
    return (f'<details class="mais"><summary>{e(rotulo)}</summary>{_barras(linhas, total)}</details>'
            if linhas else "")


def secao_despesa(f):
    d = f.get("despesa")
    if d == "falha" or d is None:
        return f'<p class="vazio"><b>{NAO_ACHOU}</b>.</p>'
    if not d:
        return '<p class="vazio"><b>Não informado</b>: o estado ainda não entregou o balanço do ano ao Tesouro.</p>'
    total = sum(v for _, v in d)
    linhas = [(FUNCOES_LEIGO.get(r, r), v, f"<small>{e(r)}</small>" if r in FUNCOES_LEIGO else "") for r, v in d]
    return (f'<p class="destaque">Em {f["ano_despesa"]}, o estado gastou <b>{brl_curto(total)}</b>. '
            f'As áreas que mais levaram dinheiro:</p>{_barras(linhas[:TOP_FUNCOES], total)}'
            + _mais(linhas[TOP_FUNCOES:], total, f"Ver as outras {len(linhas) - TOP_FUNCOES} áreas"))


def _execucao(emd):
    """Quanto do empenhado (dinheiro reservado) ja virou pagamento."""
    pct = execucao(emd["pago"], emd.get("empenhado"))
    if pct is None:
        return ""
    return (f'<p class="exec-total">Do que foi prometido ({brl_curto(emd["empenhado"])} empenhados), <b>{pct}%</b> já '
            f'foi pago.<span class="barra" aria-hidden="true"><i style="width:{max(pct, 1)}%"></i></span></p>')


def secao_receita(f, emd):
    r = f.get("receita")
    if r == "falha" or r is None:
        corpo = f'<p class="vazio"><b>{NAO_ACHOU}</b>.</p>'
    elif not r:
        corpo = '<p class="vazio"><b>Não informado</b>: o estado ainda não entregou o balanço do ano ao Tesouro.</p>'
    else:
        total = sum(v for _, v, _ in r)
        tipos = {}
        for _, v, t in r:
            tipos[t] = tipos.get(t, 0.0) + v
        resumo = [(TIPOS_RECEITA[t], v, "") for t, v in sorted(tipos.items(), key=lambda kv: -kv[1])]
        corpo = (f'<p class="destaque">Em {f["ano_receita"]}, chegaram <b>{brl_curto(total)}</b> do governo federal, '
                 f'segundo o próprio estado. A maior parte é obrigatória por lei; convênios e emendas dependem de '
                 f'negociação política.</p>{_barras(resumo, total)}'
                 + _mais([(rot, v, f' <span class="tag">{e(TIPOS_RECEITA[t])}</span>') for rot, v, t in r], total,
                         f"Ver os {len(r)} repasses um a um"))
    pago = emd["pago"]
    if emd.get("falhou"):
        corpo += f'<h3>Emendas de deputados e senadores</h3><p class="vazio"><b>{NAO_ACHOU}</b>.</p>'
    elif pago:
        tipos = [(EMENDAS_LEIGO.get(t, t), v, f"<small>{e(t)}</small>" if t in EMENDAS_LEIGO else "") for t, v in emd["tipos"]]
        corpo += (f'<h3>Emendas de deputados e senadores</h3><p class="destaque"><b>{brl_curto(pago)}</b> pagos em '
                  f'{emd["n"]} emendas de {emd["de"]} a {emd["ate"]}: {brl_curto(emd["estado"])} para o estado e o '
                  f'resto para os municípios.</p>{_execucao(emd)}{_barras(tipos, pago)}')
    else:
        corpo += '<h3>Emendas de deputados e senadores</h3><p class="vazio"><b>Não informado</b>.</p>'
    return corpo


def carimbo(texto=CARIMBO_PARADA, pequeno=False, cor="parada-cera"):
    """Selo de cera comum do site (estilo.css + selo.js) com o texto ao lado."""
    return (f'<span class="selo-cera {cor}{" p" if pequeno else ""}"><span class="cera" aria-hidden="true">'
            f'<span>!</span></span><span class="rot">{e(texto)}</span></span>')


def _parada(d):
    lugar = (d["municipio"] or UFS.get(local(d["local"])[0], ("", ""))[1]).title()
    nome = e(d.get("autor_nome") or d["autor"].title())
    autor = f'<a href="{e(d["autor_link"])}">{nome}</a>' if d.get("autor_link") else nome
    return (f'<li>{carimbo(CARIMBO_PARADA, cor="parada-cera")}<span class="rot">{e(lugar)} · {brl_curto(d["empenhado"])} '
            f'reservados em {d["ano"]}, nada pago<small>Autor: {autor} · {e(d.get("funcao") or "Não informado")}</small>'
            f'<small><a href="{transparencia._link("/emendas/consulta", codigoEmenda=d["codigo"])}" target="_blank" '
            f'rel="noopener">Ver a emenda</a></small></span></li>')


def _lista_conferir(itens, fazer):
    corpo = f'<ul class="carimbadas">{"".join(fazer(d) for d in itens[:TOP_CARIMBOS])}</ul>'
    if len(itens) > TOP_CARIMBOS:
        corpo += (f'<details class="mais"><summary>Ver as outras {len(itens) - TOP_CARIMBOS}</summary>'
                  f'<ul class="carimbadas">{"".join(fazer(d) for d in itens[TOP_CARIMBOS:])}</ul></details>')
    return corpo


def secao_paradas(itens, meta):
    intro = (f'<p class="fonte">Dinheiro reservado há {ANOS_PARADA} anos ou mais e nada pago até hoje. Pode ser obra '
             f'atrasada ou projeto travado. Não prova irregularidade, mas vale perguntar ao autor o que aconteceu.</p>')
    if meta.get("falhou_emendas"):
        return intro + f'<p class="vazio"><b>{NAO_ACHOU}</b>.</p>'
    if not itens:
        return intro + '<p class="vazio">Nenhuma emenda parada.</p>'
    return intro + _lista_conferir(itens, _parada)


def _autor(a):
    nome = f'<a href="{e(a["link"])}">{e(a["nome"])}</a>' if a.get("link") else e(a["nome"])
    info = " · ".join(x for x in (a["cargo"].title() if a["cargo"] else "", a["partido"], a["uf"]) if x)
    if a["coletivo"]:
        info = "bancada ou comissão"
    elif not a["cargo"]:
        info = "fora do mandato atual ou sem cadastro"
    valor = (f'{brl_curto(a["pago"])} <small>em {a["n"]} emenda{"s" if a["n"] != 1 else ""}</small>'
             if a["n"] else '<small>nenhuma emenda paga aqui</small>')
    pct = execucao(a["pago"], a.get("empenhado"))
    if pct is not None:
        valor += f'<small class="exec">{pct}% do prometido já pago</small>'
    par = a.get("paradas")
    marca = (f'<small>{carimbo(f"{par} parada" + ("s" if par > 1 else ""), pequeno=True, cor="parada-cera")}</small>'
             if par else "")
    return f'<li><span class="rot">{nome}<small>{e(info)}</small>{marca}</span><span class="val">{valor}</span></li>'


def secao_autores(autores, uf, falhou):
    if falhou:
        return f'<p class="vazio"><b>{NAO_ACHOU}</b>.</p>'
    do_estado = [a for a in autores if a["uf"] == uf and not a["coletivo"]]
    outros = [a for a in autores if a not in do_estado and a["n"]]
    if not do_estado and not outros:
        return '<p class="vazio"><b>Não informado</b>.</p>'
    corpo = f'<ol class="autores">{"".join(_autor(a) for a in do_estado[:TOP_AUTORES])}</ol>'
    if len(do_estado) > TOP_AUTORES:
        corpo += (f'<details class="mais"><summary>Ver os outros {len(do_estado) - TOP_AUTORES} parlamentares do '
                  f'estado</summary><ol class="autores" start="{TOP_AUTORES + 1}">'
                  f'{"".join(_autor(a) for a in do_estado[TOP_AUTORES:])}</ol></details>')
    if outros:
        corpo += (f'<details class="mais"><summary>Bancadas, comissões e autores de outros estados ({len(outros)})'
                  f'</summary><ul class="autores">{"".join(_autor(a) for a in outros)}</ul></details>')
    return corpo


def secao_estaduais(assembleia, uf):
    """Deputados estaduais: lista sob demanda (UF.json) + link da Assembleia para as emendas estaduais."""
    if assembleia and assembleia.get("ok"):
        link = (f'<p class="fonte">As emendas dos deputados estaduais não estão numa base nacional aberta. Confira no '
                f'site da <a href="{e(assembleia["site"])}" target="_blank" rel="noopener">{e(assembleia["nome"])}</a>.</p>')
    else:
        link = f'<p class="fonte">Emendas estaduais: <b>{NAO_ACHOU}</b>.</p>'
    return (f'<details class="sob-demanda" data-json="{e(uf)}.json" data-parte="estaduais">'
            f'<summary>Deputados estaduais</summary><div class="conteudo" aria-live="polite"></div>'
            f'</details>{link}')


def secao_municipios(uf):
    return (f'<details class="sob-demanda" data-json="{e(uf)}.json" data-parte="municipios">'
            f'<summary>Cidade por cidade: emendas e dinheiro federal</summary><div class="conteudo" aria-live="polite"></div>'
            f'</details>')


def kpis(p):
    f, emd = p["financas"], p["emendas"]
    desp = f.get("despesa") if isinstance(f.get("despesa"), list) else None
    rec = f.get("receita") if isinstance(f.get("receita"), list) else None
    val = lambda l, i: brl_curto(sum(x[i] for x in l)) if l else ("Não informado" if l == [] else NAO_ACHOU)
    return (f'<div class="kpis"><div class="kpi card"><b>{val(desp, 1)}</b><span>gastos pelo estado'
            f'{" em " + str(f["ano_despesa"]) if desp else ""}</span></div>'
            f'<div class="kpi card"><b>{val(rec, 1)}</b><span>recebidos do governo federal'
            f'{" em " + str(f["ano_receita"]) if rec else ""}</span></div>'
            f'<div class="kpi card"><b>{NAO_ACHOU if emd.get("falhou") else brl_curto(emd["pago"])}</b>'
            f'<span>em emendas pagas, {emd["de"]}–{emd["ate"]}</span></div></div>')


def _data(iso):
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "Não informado"


def aviso_periodo(m, f=None):
    """Aviso no topo: de quando sao os dados (ultimos 4 anos)."""
    partes = [f'emendas de {m["anos"][0]} a {m["anos"][-1]} (até {_data(m.get("hoje"))})']
    anos_dca = sorted({a for a in ((f or {}).get("ano_despesa"), (f or {}).get("ano_receita")) if a})
    if f is not None:
        partes.append(f'balanço do estado de {" e ".join(map(str, anos_dca))}' if anos_dca
                      else "balanço do estado: Não informado")
    if m.get("ano_estadual"):
        partes.append(f'verbas da União aos municípios de {m["ano_estadual"]}')
    if m.get("eleicao_estadual"):
        partes.append(f'deputados estaduais eleitos em {m["eleicao_estadual"]}')
    return (f'<p class="aviso periodo"><b>Período dos dados:</b> {"; ".join(partes)}. O balanço é o último que o '
            f'estado entregou ao Tesouro.</p>')


def pagina_uf(p):
    m = p["meta"]
    emd = dict(p["emendas"], de=m["anos"][0], ate=m["anos"][-1], falhou=m.get("falhou_emendas"))
    p = dict(p, emendas=emd)
    faltou = (f'<p class="fonte">Emendas de {", ".join(map(str, m["faltou"]))}: <b>{NAO_ACHOU}</b> nesta '
              f'atualização; os totais desses anos podem estar incompletos.</p>') if m.get("faltou") and not emd["falhou"] else ""
    corpo = f"""<h1>{e(p["nome"])}</h1>
<p class="lead">Quanto o estado gastou, quanto veio do governo federal e quais parlamentares mandaram emendas para cá. Confira e cobre quem você elegeu. <a href="../index.html#meus={e(p["uf"])}">Ver meus representantes</a>.</p>
{aviso_periodo(m, p["financas"])}
{kpis(p)}
<section class="card"><h2>Para onde vai o dinheiro do estado</h2>
{secao_despesa(p["financas"])}
<p class="fonte">Fonte: balanço anual do estado no <a href="{LINK_SICONFI}" target="_blank" rel="noopener">Tesouro Nacional (SICONFI)</a>.</p></section>
<section class="card"><h2>O que veio do governo federal</h2>
{secao_receita(p["financas"], emd)}{faltou}
<p class="fonte">Fontes: balanço do estado no Tesouro e emendas no <a href="{LINK_EMENDAS}" target="_blank" rel="noopener">Portal da Transparência</a>, pelo lugar onde o dinheiro foi gasto.</p></section>
<section class="card"><h2>Quem mandou emendas para {e(p["nome"])}</h2>
<p class="fonte">Deputados federais e senadores do estado, por quanto já foi pago das emendas de cada um aqui. Mandar emenda é parte do trabalho deles. O que vale cobrar é se o dinheiro chegou e virou obra ou serviço.</p>
{secao_autores(p["autores"], p["uf"], emd["falhou"])}</section>
<section class="card" id="paradas"><h2>Emendas paradas</h2>
{secao_paradas(p.get("paradas") or [], m)}</section>
<section class="card"><h2>Cidades e deputados estaduais</h2>
{secao_municipios(p["uf"])}
{secao_estaduais(p.get("assembleia"), p["uf"])}</section>"""
    return corpo


def pagina_indice(paginas):
    itens = []
    for uf, p in sorted(paginas.items(), key=lambda kv: norm(kv[1]["nome"])):
        rec = p["financas"].get("receita")
        valor = brl_curto(sum(x[1] for x in rec)) if isinstance(rec, list) and rec else "Não informado"
        itens.append(f'<li><a class="card uf" href="{e(uf)}.html"><b>{e(p["nome"])}</b>'
                     f'<small>{valor} do governo federal · {brl_curto(p["emendas"]["pago"])} em emendas</small></a></li>')
    m = next(iter(paginas.values()))["meta"] if paginas else None
    return (f'<h1>Gastos por estado</h1><p class="lead">Escolha um estado e descubra para onde vai o dinheiro, quanto '
            f'veio do governo federal e quem mandou emendas.</p>{aviso_periodo(m) if m else ""}'
            f'<ul class="ufs">{"".join(itens)}</ul>')


def gerar(docs, paginas, extras, gerado):
    """Grava docs/estado/index.html, UF.html e UF.json (sob demanda). Devolve quantas paginas."""
    pasta = Path(docs) / "estado"
    pasta.mkdir(parents=True, exist_ok=True)
    tpl = (SRC / "estado.html").read_text(encoding="utf-8")
    preencher = lambda titulo, corpo: (tpl.replace("__TITULO__", e(titulo)).replace("__CORPO__", corpo)
                                       .replace("__GERADO__", e(gerado)))
    for uf, p in paginas.items():
        (pasta / f"{uf}.html").write_text(preencher(p["nome"], pagina_uf(p)), encoding="utf-8")
        (pasta / f"{uf}.json").write_text(json.dumps(extras.get(uf, {}), ensure_ascii=False, separators=(",", ":")),
                                          encoding="utf-8")
    (pasta / "index.html").write_text(preencher("Gastos por estado", pagina_indice(paginas)), encoding="utf-8")
    return len(paginas) + 1


# ---------------------------------------------------------------- dados mockados (--demo e testes)
def demo(parl=(), serie=None, paginas=None):
    """Mesmo formato de coletar(), com numeros sinteticos e deterministicos, sem rede."""
    import random
    rnd = random.Random(53)
    hoje = dt.date(2026, 10, 23)
    funcoes = ["Saúde", "Educação", "Segurança Pública", "Previdência Social", "Transporte", "Administração",
               "Assistência Social", "Urbanismo"]
    rotulos = [("Cota-Parte do Fundo de Participação dos Estados", "legais"),
               ("Transferências de Recursos do Sistema Único de Saúde", "legais"),
               ("Transferências do FNDE - Salário-Educação", "legais"),
               ("Transferências de Convênios da União", "voluntarias"),
               ("Transferências Especiais da União", "especiais")]
    fin, lista, entes, mun, siglas = {}, [], [], {}, list(UFS)
    parl = list(parl) or [dict(nome=f"Deputada Demo {uf} {j}", cargo="DEPUTADO FEDERAL" if j < 4 else "SENADOR",
                               partido="XX", uf=uf, perfil=None) for uf in UFS for j in range(1, 6)]
    for i, (uf, (cod, nome)) in enumerate(UFS.items()):
        if uf == "AC":  # um estado com a fonte fora do ar, para a pagina mostrar "Fonte nao encontrada"
            fin[uf] = dict(ano_despesa=None, despesa="falha", ano_receita=None, receita="falha")
        else:
            esc = rnd.uniform(5e9, 2e11)
            fin[uf] = dict(ano_despesa=2025, despesa=sorted(((f, esc * rnd.uniform(.02, .3)) for f in funcoes),
                                                            key=lambda x: -x[1]),
                           ano_receita=2025, receita=sorted(((r, esc * rnd.uniform(.005, .08), t) for r, t in rotulos),
                                                            key=lambda x: -x[1]))
        for j in range(3):
            entes.append(dict(cod=f"{cod}{j:05d}", nome=f"Cidade Demo {j + 1}", uf=uf))
            mun[f"{cod}{j:05d}"] = dict(total=round(rnd.uniform(1e6, 5e8), 2), tipos={})
        for k in range(8):
            lc = f"{nome.upper()} (UF)" if k % 3 == 0 else f"CIDADE DEMO {k % 3 + 1} - {uf}"
            de = siglas[(i + 1) % len(siglas)] if k == 6 else uf  # um autor de outra UF
            autor = "BANCADA DE DEMO" if k == 7 else f"DEPUTADA DEMO {de} {k % 4 + 1}"
            lista.append(dict(autor=autor, tipo=rnd.choice(
                ["Emenda Individual - Transferências com Finalidade Definida", "Emenda Individual - Transferências Especiais",
                 "Emenda de Bancada"]), local=lc, funcao=rnd.choice(funcoes),
                subfuncao="", ano=2025, codigo=f"2025{i:02d}{k:04d}",
                pago=round(rnd.uniform(1e5, 2e7), 2), empenhado=round(rnd.uniform(2e7, 3e7), 2)))
        lista.append(dict(autor=f"DEPUTADA DEMO {uf} 2", tipo="Emenda Individual - Transferências com Finalidade Definida",
                          local=f"CIDADE DEMO 1 - {uf}", funcao="Urbanismo", subfuncao="", ano=2023,
                          codigo=f"2023{i:02d}9999", pago=0.0, empenhado=round(rnd.uniform(1e6, 5e6), 2)))  # parada
    estaduais, ano_est = deputados_estaduais(serie, paginas, None, hoje)
    if not estaduais:
        estaduais = {uf: [dict(nome=f"Deputada Estadual Demo {k}", partido="XX", tse=None, pagina=None)
                          for k in range(1, 4)] for uf in UFS}
        ano_est = 2022
    assembleias = {uf: dict(a, ok=True) for uf, a in carregar_assembleias().items()}
    return montar(fin, agregar(lista), parl, entes, mun, estaduais, assembleias,
                  dict(anos=[2023, 2024, 2025, 2026], faltou=[], ano_estadual=2025, eleicao_estadual=ano_est,
                       hoje=hoje.isoformat(),
                       falhou_emendas=False), paradas(lista, hoje))


if __name__ == "__main__":
    main()
