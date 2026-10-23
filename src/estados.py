"""Dossie por estado (#53): gasto do governo estadual, verbas recebidas da Uniao e parlamentares autores de emendas
com gasto no estado. Fontes oficiais e gratuitas:
  SICONFI (Tesouro Nacional, sem chave): DCA Anexo I-E (despesa por funcao) e I-C (receitas vindas da Uniao)
  Portal da Transparencia (so pela API oficial, chave-api-dados): emendas com o local do gasto, ultimos 4 anos
  Camara/Senado (parlamentares.py): quem esta em exercicio, para ligar o autor da emenda a pagina dele
  TSE (pipeline.py): deputados estaduais e distritais eleitos em exercicio
O unico elo oficial entre parlamentar e gasto e a autoria da emenda: o texto diz "autor da emenda", nunca "envolvido".
Pagina leve por UF (docs/estado/UF.html); municipios e deputados estaduais vao em docs/estado/UF.json, baixado so
quando o leitor abre a secao. Sem CPF/CNPJ em nenhum arquivo."""
import csv, datetime as dt, html, json, re, sys, time, unicodedata, urllib.parse, urllib.request
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
TIPOS_RECEITA = {"legais": "Constitucionais e legais", "voluntarias": "Voluntárias (convênios)",
                 "especiais": "Transferências especiais (emendas Pix)"}
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
    return sorted(((r, v, tipo_receita(r)) for r, v in linhas), key=lambda x: -x[1])


def dca(buscar, id_ente, anexo, ano, cache=None):
    """Itens de um anexo do DCA; tenta o ano anterior se o ano ainda nao foi entregue. (ano, itens) ou (None, None)."""
    for a in (ano, ano - 1):
        chave = ("dca", str(id_ente), anexo, a)
        itens = cache.get(chave) if cache else None
        if itens is None:
            itens = siconfi(buscar, "dca", an_exercicio=a, no_anexo=anexo, id_ente=id_ente)
            if itens is None:
                return None, None
            if itens and cache:
                cache.set(chave, itens)
        if itens:
            return a, itens
    return None, []


def financas(buscar, id_ente, ano, cache=None):
    """Gasto por funcao e verbas da Uniao de um ente. Falha da fonte = "falha"; ano sem entrega = dados vazios."""
    a_desp, desp = dca(buscar, id_ente, "DCA-Anexo I-E", ano, cache)
    a_rec, rec = dca(buscar, id_ente, "DCA-Anexo I-C", ano, cache)
    return dict(ano_despesa=a_desp, despesa="falha" if desp is None else despesa_por_funcao(desp),
                ano_receita=a_rec, receita="falha" if rec is None else receitas_uniao(rec))


def municipios(buscar, entes, ano, cache=None, tempo_max=TEMPO_MUNICIPIOS):
    """{cod_ibge: dict(total, tipos)} das verbas da Uniao a cada municipio (DCA I-C). Com prazo: quem fica de fora
    sai sem valor ("Não informado") e entra nas semanas seguintes pelo cache."""
    fim, out = time.monotonic() + tempo_max, {}
    for n, ent in enumerate(entes, 1):
        cod = str(ent["cod"])
        if time.monotonic() >= fim:
            print(f"[aviso] SICONFI municipios: prazo esgotado em {n - 1}/{len(entes)}", file=sys.stderr)
            break
        _, itens = dca(buscar, cod, "DCA-Anexo I-C", ano, cache)
        if itens:
            rec = receitas_uniao(itens)
            tipos = {}
            for _, v, t in rec:
                tipos[t] = tipos.get(t, 0.0) + v
            out[cod] = dict(total=round(sum(tipos.values()), 2), tipos={k: round(v, 2) for k, v in tipos.items()})
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


def emendas(api, anos, cache=None, hoje=None):
    """Emendas dos `anos` (lista enxuta) e os anos que faltaram. O ano so vai para o cache se veio inteiro; anos
    recentes sao sempre relidos (restos a pagar continuam sendo pagos)."""
    hoje = hoje or dt.date.today()
    out, faltou = [], []
    for ano in anos:
        guardavel = cache is not None and ano < hoje.year - 1
        lista = cache.get(("emendas", VERSAO_EMENDAS, ano)) if guardavel else None
        if lista is None:
            antes = api.falhas
            bruto = api.paginas("/emendas", max_paginas=5000, ano=ano) if api.ativa() else None
            if bruto is None or api.falhas != antes:
                faltou.append(ano)
            lista = [enxuta(d) for d in bruto or ()]
            if guardavel and ano not in faltou:
                cache.set(("emendas", VERSAO_EMENDAS, ano), lista)
        out += lista
    return out, faltou


# ---------------------------------------------------------------- emendas emergenciais x reconhecimento federal (S2iD)
CKAN_S2ID = "https://dadosabertos.mdr.gov.br/api/3/action/package_show?id=s2id_sedec"
LINK_S2ID = "https://s2id.mi.gov.br/paginas/series/"
RSS_NOTICIAS, BUSCA_NOTICIAS = "https://news.google.com/rss/search?", "https://news.google.com/search?"
MAX_NOTICIAS = 40  # consultas de apoio por execucao
CARIMBO = "Emergência sem reconhecimento oficial"


def baixar(url, timeout=120, limite=200_000_000):
    """Bytes da URL; None se falhar."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": transparencia.UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(limite)
    except Exception as ex:
        print(f"[aviso] {url} indisponivel ({ex})", file=sys.stderr)
        return None


def emergencial(d):
    """Emenda de resposta a desastre: subfuncao Defesa Civil (182)."""
    return "DEFESA CIVIL" in norm(d.get("subfuncao"))


def _tabela(bruto, nome):
    """DataFrame de um CSV (separador e codificacao detectados) ou XLSX; None se nao der para ler."""
    import io
    import pandas as pd
    try:
        if bruto[:2] == b"PK" or norm(nome).endswith(("XLSX", "XLS")):
            return pd.read_excel(io.BytesIO(bruto), dtype=str)
        for cod in ("utf-8-sig", "latin-1"):
            try:
                return pd.read_csv(io.BytesIO(bruto), sep=None, engine="python", dtype=str, encoding=cod,
                                   keep_default_na=False)
            except UnicodeDecodeError:
                continue
    except Exception as ex:
        print(f"[aviso] S2iD: {nome} ilegivel ({ex!r})", file=sys.stderr)
    return None


def _coluna(df, *partes, evitar=()):
    """Primeira coluna cujo nome (normalizado) contem todas as `partes`."""
    for c in df.columns:
        n = norm(c)
        if all(p in n for p in partes) and not any(x in n for x in evitar):
            return c
    return None


def ler_reconhecimentos(df):
    """{"cod": {ibge7: anos}, "nome": {(uf, MUNICIPIO): anos}, "uf": {uf: anos}} das portarias de reconhecimento.
    As colunas variam entre arquivos: acha IBGE, UF, municipio e a data (ou o ano) pelo nome."""
    out = dict(cod={}, nome={}, uf={})
    c_ibge, c_uf = _coluna(df, "IBGE"), _coluna(df, "UF")
    c_mun = _coluna(df, "MUNICIP", evitar=("IBGE", "COD"))
    c_data = (_coluna(df, "DATA", "PUBLICA") or _coluna(df, "DATA", "RECONHEC") or _coluna(df, "DATA", "DOU")
              or _coluna(df, "DATA"))
    c_ano = _coluna(df, "ANO")
    print(f"S2iD: colunas usadas ibge={c_ibge!r} uf={c_uf!r} municipio={c_mun!r} data={c_data!r} ano={c_ano!r}")
    for r in df.to_dict("records"):
        m = re.search(r"(19|20)\d{2}", str(r.get(c_data) or "")) if c_data else None
        ano = int(m[0]) if m else int(_num(r.get(c_ano))) if c_ano else 0
        if not ano:
            continue
        uf = str(r.get(c_uf) or "").strip().upper()[:2] if c_uf else ""
        cod = re.sub(r"\D", "", str(r.get(c_ibge) or ""))[:7] if c_ibge else ""
        if len(cod) == 7:
            out["cod"].setdefault(cod, set()).add(ano)
            uf = uf or next((u for u, (c, _) in UFS.items() if c == cod[:2]), "")
        if uf in UFS:
            out["uf"].setdefault(uf, set()).add(ano)
            if c_mun and r.get(c_mun):
                out["nome"].setdefault((uf, norm(r[c_mun])), set()).add(ano)
    return out


def reconhecimentos(buscar, baixar_=baixar):
    """Reconhecimentos federais de situacao de emergencia ou calamidade (S2iD, dados abertos do MIDR, pelo catalogo
    CKAN). None se a fonte falhar: sem essa base nenhuma emenda e carimbada."""
    d = buscar(CKAN_S2ID)
    recursos = ((d or {}).get("result") or {}).get("resources") if isinstance(d, dict) else None
    alvos = [r for r in recursos or [] if "RECONHEC" in norm(f'{r.get("name")} {r.get("description")}')
             and r.get("url")]
    out, lidos = dict(cod={}, nome={}, uf={}), 0
    for r in alvos:
        bruto = baixar_(r["url"])
        df = _tabela(bruto, r.get("url") or "") if bruto else None
        if df is None or not len(df):
            continue
        lidos += 1
        for k, v in ler_reconhecimentos(df).items():
            for ch, anos in v.items():
                out[k].setdefault(ch, set()).update(anos)
    print(f"S2iD: {len(alvos)} arquivos de reconhecimento no catalogo, {lidos} lidos, "
          f"{len(out['cod']) or len(out['nome'])} municipios com reconhecimento.")
    return out if lidos else None


def reconhecido(rec, uf, mun, ano, cod=None):
    """Houve reconhecimento federal no ano da emenda ou no anterior? Emenda para o estado: qualquer municipio da UF."""
    janela = {ano - 1, ano}
    if mun is None:
        return bool(rec["uf"].get(uf, set()) & janela)
    return bool((rec["cod"].get(cod, set()) if cod else set()) & janela
                or rec["nome"].get((uf, mun), set()) & janela)


def carimbos(lista, rec, entes=()):
    """{uf: [emendas emergenciais sem reconhecimento federal]}, maior valor primeiro. Sem a base do S2iD: {}."""
    if rec is None:
        return {}
    cods = {(e_["uf"], norm(e_["nome"])): e_["cod"] for e_ in entes}
    out = {}
    for d in lista:
        lc = local(d["local"])
        if not (lc and d.get("ano") and emergencial(d) and (d["pago"] > 0 or d.get("empenhado", 0) > 0)):
            continue
        uf, mun = lc
        if not reconhecido(rec, uf, mun, d["ano"], cods.get((uf, mun))):
            out.setdefault(uf, []).append(dict(d, municipio=mun))
    for l in out.values():
        l.sort(key=lambda d: -(d["pago"] or d.get("empenhado", 0)))
    return out


def consulta_noticias(lugar, ano):
    return (f'"{lugar}" (enchente OR seca OR estiagem OR chuva OR desastre OR "defesa civil" OR emergência) '
            f"after:{ano - 1}-07-01 before:{ano + 1}-01-01")


def noticias_apoio(cars, buscar_txt, maximo=MAX_NOTICIAS):
    """Apoio ao leitor: quantas noticias de emergencia o Google Noticias acha no local e no periodo da emenda. Nao
    decide o carimbo (cidade pequena quase nao aparece na imprensa). Fica None quando nao foi consultado."""
    n = 0
    for uf, l in cars.items():
        for d in l:
            lugar = (d["municipio"] or UFS[uf][1]).title()
            q = consulta_noticias(lugar, d["ano"])
            d["busca"] = BUSCA_NOTICIAS + urllib.parse.urlencode(dict(q=q, hl="pt-BR", gl="BR", ceid="BR:pt-419"))
            d["noticias"] = None
            if buscar_txt and n < maximo:
                n += 1
                xml = buscar_txt(RSS_NOTICIAS + urllib.parse.urlencode(dict(q=q, hl="pt-BR", gl="BR", ceid="BR:pt-419")))
                d["noticias"] = None if xml is None else xml.count("<item>")
    return cars


def texto(url):
    b = baixar(url, timeout=30, limite=5_000_000)
    return None if b is None else b.decode("utf-8", "replace")


def coletivo(autor):
    """Bancada, comissao ou relator: nao e uma pessoa."""
    a = norm(autor)
    return a.startswith(("BANCADA", "COMISSAO", "RELATOR", "COM. ")) or "COMISSAO" in a


def agregar(lista):
    """{uf: dict(pago, n, tipos{tipo: valor}, autores{autor: [pago, n]}, municipios{MUN: dict(pago, n, autores)})}."""
    por = {}
    for d in lista:
        lc = local(d["local"])
        if not lc or d["pago"] <= 0:
            continue
        uf, mun = lc
        u = por.setdefault(uf, dict(pago=0.0, n=0, estado=0.0, tipos={}, autores={}, municipios={}))
        u["pago"] += d["pago"]; u["n"] += 1
        u["tipos"][d["tipo"] or "Não informado"] = u["tipos"].get(d["tipo"] or "Não informado", 0.0) + d["pago"]
        a = u["autores"].setdefault(d["autor"] or "Não informado", [0.0, 0])
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
    for autor, (pago, n) in sorted(autores.items(), key=lambda kv: -kv[1][0]):
        p = None if coletivo(autor) else por_nome.get((norm(autor), uf)) or por_nome.get((norm(autor), None))
        if p:
            vistos.add(id(p))
        out.append(dict(autor=autor, nome=p["nome"] if p else autor.title(), pago=round(pago, 2), n=n,
                        coletivo=coletivo(autor), cargo=p["cargo"] if p else "", partido=p["partido"] if p else "",
                        uf=p["uf"] if p else "", link=relativo(p.get("dossie") or p.get("perfil")) if p else None))
    for p in parl:
        if p["uf"] == uf and id(p) not in vistos:
            out.append(dict(autor=p["nome"], nome=p["nome"], pago=0.0, n=0, coletivo=False, cargo=p["cargo"], partido=p["partido"],
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


def coletar(buscar, api, parl, serie=None, paginas=None, link=None, cache=None, hoje=None, checar=None,
            baixar_=baixar, buscar_txt=None):
    """Dados de todas as UFs para gerar(). Cada fonte que falha vira NAO_ACHOU na sua secao, sem derrubar o resto."""
    hoje = hoje or dt.date.today()
    ano = ano_dca(hoje)
    fin = {uf: financas(buscar, cod, ano, cache) for uf, (cod, _) in UFS.items()}
    anos = list(range(hoje.year - ANOS_EMENDAS + 1, hoje.year + 1))
    lista, faltou = emendas(api, anos, cache, hoje) if api else ([], anos)
    entes = entes_municipais(buscar) or []
    mun = municipios(buscar, entes, ano, cache) if entes else {}
    estaduais, ano_est = deputados_estaduais(serie, paginas, link, hoje)
    rec = reconhecimentos(buscar, baixar_)
    cars = noticias_apoio(carimbos(lista, rec, entes), buscar_txt)
    if cache:
        cache.salvar()
    assembleias = carregar_assembleias()
    for a in assembleias.values():  # link que nao abre no Actions vira "Fonte nao encontrada"
        a["ok"] = bool(a["site"]) and (checar(a["site"]) if checar else True)
    return montar(fin, agregar(lista), parl, entes, mun, estaduais, assembleias,
                  dict(anos=anos, faltou=faltou, ano_estadual=ano, eleicao_estadual=ano_est,
                       falhou_emendas=len(faltou) == len(anos), s2id=rec is not None), cars)


def montar(fin, emd, parl, entes, mun, estaduais, assembleias, meta, cars=None):
    """{uf: dados da pagina} + {uf: dados sob demanda (municipios e deputados estaduais)}.
    cars: {uf: [emendas carimbadas]} (carimbos())."""
    paginas, extras, por_uf = {}, {}, {}
    for ent in entes:
        por_uf.setdefault(ent["uf"], {})[norm(ent["nome"])] = ent
    for uf, (_, nome) in UFS.items():
        u = emd.get(uf) or dict(pago=0.0, n=0, estado=0.0, tipos={}, autores={}, municipios={})
        f = fin.get(uf) or {}
        paginas[uf] = dict(uf=uf, nome=nome, financas=f, emendas=dict(pago=round(u["pago"], 2), n=u["n"],
                           estado=round(u["estado"], 2), tipos=sorted(u["tipos"].items(), key=lambda kv: -kv[1])),
                           autores=ligar_autores(u["autores"], uf, parl), assembleia=assembleias.get(uf), meta=meta,
                           carimbos=(cars or {}).get(uf, []))
        por_autor, por_mun = {}, {}
        for d in paginas[uf]["carimbos"]:
            por_autor[norm(d["autor"])] = por_autor.get(norm(d["autor"]), 0) + 1
            por_mun[d["municipio"]] = por_mun.get(d["municipio"], 0) + 1
        quem = {}
        for a in paginas[uf]["autores"]:
            a["carimbos"] = por_autor.get(norm(a["autor"]), 0)
            quem.setdefault(norm(a["autor"]), a)
        for d in paginas[uf]["carimbos"]:  # nome e link do autor como na lista de parlamentares
            a = quem.get(norm(d["autor"])) or {}
            d.update(autor_nome=a.get("nome") or d["autor"].title(), autor_link=a.get("link"))
        lm = []
        nomes_mun = por_uf.get(uf, {})
        for ent in nomes_mun.values():
            em = u["municipios"].get(norm(ent["nome"])) or {}
            uniao = mun.get(ent["cod"])
            if not em and not uniao:
                continue
            top = sorted((em.get("autores") or {}).items(), key=lambda kv: -kv[1])[:TOP_AUTORES_MUN]
            lm.append([ent["nome"], round(em.get("pago", 0.0), 2), em.get("n", 0),
                       uniao["total"] if uniao else None, [[a.title(), round(v, 2)] for a, v in top],
                       por_mun.get(norm(ent["nome"]), 0)])
        for nm, em in u["municipios"].items():  # municipio da emenda que nao bateu com o SICONFI: entra assim mesmo
            if nm not in nomes_mun:
                top = sorted(em["autores"].items(), key=lambda kv: -kv[1])[:TOP_AUTORES_MUN]
                lm.append([nm.title(), round(em["pago"], 2), em["n"], None, [[a.title(), round(v, 2)] for a, v in top],
                           por_mun.get(nm, 0)])
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
        f'<small>{v / total * 100:.0f}%</small></span>'
        f'<span class="barra" aria-hidden="true"><i style="width:{max(v / topo * 100, 1):.1f}%"></i></span></li>'
        for r, v, x in linhas) if total else ""
    return f'<ul class="barras">{itens}</ul>'


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
    linhas = [(r, v, "") for r, v in d]
    return (f'<p class="destaque"><b>{brl_curto(total)}</b> gastos (liquidados) em {f["ano_despesa"]}. '
            f'Onde mais foi o dinheiro:</p>{_barras(linhas[:TOP_FUNCOES], total)}'
            + _mais(linhas[TOP_FUNCOES:], total, f"Ver as outras {len(linhas) - TOP_FUNCOES} áreas"))


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
        corpo = (f'<p class="destaque"><b>{brl_curto(total)}</b> recebidos da União em {f["ano_receita"]}, '
                 f'segundo o balanço do próprio estado.</p>{_barras(resumo, total)}'
                 + _mais([(rot, v, f' <span class="tag">{e(TIPOS_RECEITA[t])}</span>') for rot, v, t in r], total,
                         f"Ver as {len(r)} receitas"))
    pago = emd["pago"]
    if emd.get("falhou"):
        corpo += f'<h3>Emendas parlamentares</h3><p class="vazio"><b>{NAO_ACHOU}</b>.</p>'
    elif pago:
        tipos = [(t, v, "") for t, v in emd["tipos"]]
        corpo += (f'<h3>Emendas parlamentares</h3><p class="destaque"><b>{brl_curto(pago)}</b> pagos em {emd["n"]} '
                  f'emendas com gasto no estado ({brl_curto(emd["estado"])} no estado como um todo e o resto em '
                  f'municípios), {emd["de"]}–{emd["ate"]}.</p>{_barras(tipos, pago)}')
    else:
        corpo += '<h3>Emendas parlamentares</h3><p class="vazio"><b>Não informado</b>.</p>'
    return corpo


def carimbo(texto=CARIMBO):
    return f'<span class="carimbo">⚠ {e(texto)}</span>'


def _carimbada(d):
    lugar = (d["municipio"] or UFS.get(local(d["local"])[0], ("", ""))[1]).title()
    noticias = ("não consultadas" if d.get("noticias") is None else
                f'{d["noticias"]} encontrada{"s" if d["noticias"] != 1 else ""}' if d["noticias"] else "nenhuma encontrada")
    valor = (f'{brl_curto(d["pago"])} pagos' if d["pago"] else f'{brl_curto(d.get("empenhado"))} empenhados')
    nome = e(d.get("autor_nome") or d["autor"].title())
    autor = f'<a href="{e(d["autor_link"])}">{nome}</a>' if d.get("autor_link") else nome
    return (f'<li>{carimbo()}<span class="rot">{e(lugar)}, {d["ano"]} · {valor}'
            f'<small>Autor: {autor} · {e(d["subfuncao"] or "Defesa civil")}</small>'
            f'<small><a href="{transparencia._link("/emendas/consulta", codigoEmenda=d["codigo"])}" target="_blank" '
            f'rel="noopener">Ver a emenda</a> · <a href="{e(d["busca"])}" target="_blank" rel="noopener">Notícias de '
            f'emergência no período</a>: {noticias}</small></span></li>')


def secao_carimbos(cars, meta):
    """Emendas de defesa civil sem reconhecimento federal de emergencia no local (S2iD) no ano ou no anterior."""
    intro = (f'<p class="fonte">Emendas de defesa civil (resposta a desastres) para um lugar sem reconhecimento federal '
             f'de situação de emergência ou calamidade no ano da emenda ou no anterior, segundo o '
             f'<a href="{LINK_S2ID}" target="_blank" rel="noopener">S2iD, do Ministério da Integração</a>. O carimbo '
             f'pede conferência, não prova irregularidade: a defesa civil também previne desastres. As notícias só '
             f'ajudam a conferir e não decidem o carimbo.</p>')
    if meta.get("falhou_emendas") or not meta.get("s2id"):
        return intro + f'<p class="vazio"><b>{NAO_ACHOU}</b>: sem essa base nenhuma emenda é carimbada.</p>'
    if not cars:
        return intro + '<p class="vazio">Nenhuma emenda de defesa civil sem reconhecimento oficial.</p>'
    corpo = f'<ul class="carimbadas">{"".join(_carimbada(d) for d in cars[:TOP_CARIMBOS])}</ul>'
    if len(cars) > TOP_CARIMBOS:
        corpo += (f'<details class="mais"><summary>Ver as outras {len(cars) - TOP_CARIMBOS}</summary>'
                  f'<ul class="carimbadas">{"".join(_carimbada(d) for d in cars[TOP_CARIMBOS:])}</ul></details>')
    return intro + corpo


def _autor(a):
    nome = f'<a href="{e(a["link"])}">{e(a["nome"])}</a>' if a.get("link") else e(a["nome"])
    info = " · ".join(x for x in (a["cargo"].title() if a["cargo"] else "", a["partido"], a["uf"]) if x)
    if a["coletivo"]:
        info = "bancada ou comissão"
    elif not a["cargo"]:
        info = "fora do mandato atual ou sem cadastro"
    valor = (f'{brl_curto(a["pago"])} <small>em {a["n"]} emenda{"s" if a["n"] != 1 else ""}</small>'
             if a["n"] else '<small>nenhuma emenda paga aqui</small>')
    n = a.get("carimbos")
    marca = f'<small>{carimbo(f"{n} sem reconhecimento oficial")}</small>' if n else ""
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
        link = (f'<p class="fonte">Emendas estaduais não têm base nacional aberta: confira no site da '
                f'<a href="{e(assembleia["site"])}" target="_blank" rel="noopener">{e(assembleia["nome"])}</a>.</p>')
    else:
        link = f'<p class="fonte">Emendas estaduais: <b>{NAO_ACHOU}</b>.</p>'
    return (f'<details class="sob-demanda" data-json="{e(uf)}.json" data-parte="estaduais">'
            f'<summary>Deputados estaduais em exercício</summary><div class="conteudo" aria-live="polite"></div>'
            f'</details>{link}')


def secao_municipios(uf):
    return (f'<details class="sob-demanda" data-json="{e(uf)}.json" data-parte="municipios">'
            f'<summary>Municípios: emendas e verbas da União</summary><div class="conteudo" aria-live="polite"></div>'
            f'</details>')


def kpis(p):
    f, emd = p["financas"], p["emendas"]
    desp = f.get("despesa") if isinstance(f.get("despesa"), list) else None
    rec = f.get("receita") if isinstance(f.get("receita"), list) else None
    val = lambda l, i: brl_curto(sum(x[i] for x in l)) if l else ("Não informado" if l == [] else NAO_ACHOU)
    return (f'<div class="kpis"><div class="kpi card"><b>{val(desp, 1)}</b><span>gasto do estado'
            f'{" em " + str(f["ano_despesa"]) if desp else ""}</span></div>'
            f'<div class="kpi card"><b>{val(rec, 1)}</b><span>recebido da União'
            f'{" em " + str(f["ano_receita"]) if rec else ""}</span></div>'
            f'<div class="kpi card"><b>{NAO_ACHOU if emd.get("falhou") else brl_curto(emd["pago"])}</b>'
            f'<span>em emendas pagas, {emd["de"]}–{emd["ate"]}</span></div></div>')


def pagina_uf(p):
    m = p["meta"]
    emd = dict(p["emendas"], de=m["anos"][0], ate=m["anos"][-1], falhou=m.get("falhou_emendas"))
    p = dict(p, emendas=emd)
    faltou = (f'<p class="fonte">Emendas de {", ".join(map(str, m["faltou"]))}: <b>{NAO_ACHOU}</b> nesta '
              f'atualização; os totais desses anos podem estar incompletos.</p>') if m.get("faltou") and not emd["falhou"] else ""
    corpo = f"""<h1>{e(p["nome"])}</h1>
<p class="lead">Gastos do governo estadual, dinheiro que veio da União e quem mandou emendas para o estado.</p>
{kpis(p)}
<section class="card"><h2>Para onde vai o dinheiro do estado</h2>
{secao_despesa(p["financas"])}
<p class="fonte">Balanço anual (DCA) entregue pelo estado ao <a href="{LINK_SICONFI}" target="_blank" rel="noopener">SICONFI, do Tesouro Nacional</a>. Despesa liquidada por área (função).</p></section>
<section class="card"><h2>O que veio da União</h2>
{secao_receita(p["financas"], emd)}{faltou}
<p class="fonte">Receitas da União declaradas pelo estado no SICONFI. Emendas: <a href="{LINK_EMENDAS}" target="_blank" rel="noopener">Portal da Transparência</a>, pelo local do gasto (inclui órgãos federais, prefeituras e entidades no estado, não só o governo estadual).</p></section>
<section class="card"><h2>Parlamentares autores de emendas</h2>
<p class="fonte">Deputados federais e senadores do estado em exercício, pelo valor pago em emendas de sua autoria com gasto em {e(p["nome"])}. Ser autor de emenda é parte do mandato e não é, por si, irregular.</p>
{secao_autores(p["autores"], p["uf"], emd["falhou"])}</section>
<section class="card" id="carimbos"><h2>Emendas emergenciais para conferir</h2>
{secao_carimbos(p.get("carimbos") or [], m)}</section>
<section class="card"><h2>Municípios e Assembleia</h2>
{secao_municipios(p["uf"])}
{secao_estaduais(p.get("assembleia"), p["uf"])}</section>"""
    return corpo


def pagina_indice(paginas):
    itens = []
    for uf, p in sorted(paginas.items(), key=lambda kv: norm(kv[1]["nome"])):
        rec = p["financas"].get("receita")
        valor = brl_curto(sum(x[1] for x in rec)) if isinstance(rec, list) and rec else "Não informado"
        itens.append(f'<li><a class="card uf" href="{e(uf)}.html"><b>{e(p["nome"])}</b>'
                     f'<small>{valor} da União · {brl_curto(p["emendas"]["pago"])} em emendas</small></a></li>')
    return (f'<h1>Gastos por estado</h1><p class="lead">Escolha um estado para ver o gasto do governo estadual, as '
            f'verbas recebidas da União e os parlamentares autores de emendas.</p><ul class="ufs">{"".join(itens)}</ul>')


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
    rec = dict(cod={}, nome={}, uf={})
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
            civil = k in (1, 2)  # duas de defesa civil por UF: a da Cidade Demo 3 fica sem reconhecimento
            lista.append(dict(autor=autor, tipo=rnd.choice(
                ["Emenda Individual - Transferências com Finalidade Definida", "Emenda Individual - Transferências Especiais",
                 "Emenda de Bancada"]), local=lc, funcao="Segurança Pública" if civil else rnd.choice(funcoes),
                subfuncao="Defesa civil" if civil else "", ano=2025, codigo=f"2025{i:02d}{k:04d}",
                pago=round(rnd.uniform(1e5, 2e7), 2), empenhado=0.0))
        rec["cod"][f"{cod}00001"] = {2025}  # Cidade Demo 2 teve reconhecimento federal
    estaduais, ano_est = deputados_estaduais(serie, paginas, None, hoje)
    if not estaduais:
        estaduais = {uf: [dict(nome=f"Deputada Estadual Demo {k}", partido="XX", tse=None, pagina=None)
                          for k in range(1, 4)] for uf in UFS}
        ano_est = 2022
    assembleias = {uf: dict(a, ok=True) for uf, a in carregar_assembleias().items()}
    cars = noticias_apoio(carimbos(lista, rec, entes), None)
    return montar(fin, agregar(lista), parl, entes, mun, estaduais, assembleias,
                  dict(anos=[2023, 2024, 2025, 2026], faltou=[], ano_estadual=2025, eleicao_estadual=ano_est,
                       falhou_emendas=False, s2id=True), cars)
