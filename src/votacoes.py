"""Como votou (#56): voto de cada deputado federal e senador em exercicio nas votacoes nominais de plenario de temas
importantes, escolhidas a mao em config/votacoes.json (tema, explicacao simples e o que significa votar Sim).
Fontes oficiais e gratuitas:
  Camara: arquivos abertos anuais https://dadosabertos.camara.leg.br/arquivos/votacoesVotos/csv/ (um por ano)
  Senado: API de Dados Abertos https://legis.senado.leg.br/dadosabertos/votacao (uma consulta por dia de votacao)
O texto so mostra o voto e o placar da casa, sem juizo de valor. "Nao votou" nao e falta: pode ser licenca ou missao."""
import datetime as dt, hashlib, html, io, json, sys
from collections import Counter
from pathlib import Path
import pandas as pd
import cifra
from cache import ano_fechado, resultados, resumo_fechado, resumo_log

VERSAO = 1  # mude ao alterar a leitura: invalida os resumos guardados
ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "votacoes.json"
CAMARA_VOTOS = "https://dadosabertos.camara.leg.br/arquivos/votacoesVotos/csv/votacoesVotos-{ano}.csv"
SENADO_DIA = "https://legis.senado.leg.br/dadosabertos/votacao?dataInicio={dia}&dataFim={dia}"
LINK_CAMARA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={prop}"
LINK_SENADO = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{materia}"
NAO_VOTOU = "Não votou"
VOTOS_CAMARA = {"Sim": "Sim", "Não": "Não", "Abstenção": "Abstenção", "Obstrução": "Obstrução",
                "Artigo 17": "Presidiu a sessão"}  # art. 17 do Regimento: quem preside nao vota
VOTOS_SENADO = {"Sim": "Sim", "Não": "Não", "Abstenção": "Abstenção", "Obstrução": "Obstrução",
                "P-NRV": "Presente, sem votar", "Presidente (art. 51 RISF)": "Presidiu a sessão"}
JUSTIFICADA = ("LICEN", "MISS", "ATIVIDADE", "REPRESENTA", "AFAST", "ART. 13", "ART 13")
e = html.escape


def carregar(arq=CONFIG):
    """Votacoes curadas (lista de dicts); arquivo ausente ou ruim = nenhuma."""
    try:
        return [v for v in json.loads(Path(arq).read_text(encoding="utf-8"))["votacoes"]
                if v.get("casa") in ("camara", "senado") and v.get("votacao") and v.get("id")]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _norm(s):
    import unicodedata
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()


def voto_senado(sigla, descricao=""):
    """(voto, motivo) a partir do codigo do Senado; ausencia com justificativa oficial leva o motivo."""
    if sigla in VOTOS_SENADO:
        return VOTOS_SENADO[sigla], None
    d = _norm(descricao)
    if sigla == "NCom" or "NAO COMPARECEU" in d:
        return NAO_VOTOU, None
    if any(j in d for j in JUSTIFICADA):
        return NAO_VOTOU, descricao.strip() or sigla
    return ("Presente, sem votar", None) if d.startswith("PRESENTE") else (NAO_VOTOU, descricao.strip() or None)


def ler_votos_camara(bruto, ids):
    """{idVotacao: {id do deputado: voto}} so das votacoes pedidas, lendo o CSV anual em pedacos."""
    out = {}
    b = bytes(bruto) if isinstance(bruto, (bytes, bytearray)) else Path(bruto).read_bytes()
    for parte in pd.read_csv(io.BytesIO(b), sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False,
                             usecols=["idVotacao", "voto", "deputado_id"], chunksize=200_000):
        parte = parte[parte["idVotacao"].isin(ids)]
        for v, dep, voto in zip(parte["idVotacao"], parte["deputado_id"], parte["voto"]):
            out.setdefault(v, {})[dep] = VOTOS_CAMARA.get(voto, voto or NAO_VOTOU)
    return out


def votos_camara(itens, cache, baixar=None):
    """{idVotacao: {dep: voto}} das votacoes da Camara pedidas; None se nenhum arquivo veio.
    Ano fechado: o resumo (so as votacoes curadas) fica guardado cifrado com o sha256 do CSV (cache.resumo_fechado);
    o CSV bruto (~60 MB por ano) nao e guardado. O ano atual e sempre baixado de novo."""
    baixar = baixar or (lambda url: cifra.baixar(url, None, cab={"User-Agent": "alerta-patrimonial/1.0"}))
    por_ano = {}
    for v in itens:
        por_ano.setdefault(int(v["data"][:4]), set()).add(v["votacao"])
    guardados = resultados(cache, "votacoes_camara", 400 * 86400) if cache else None
    out, veio, origens = {}, False, Counter()
    for ano, ids in sorted(por_ano.items()):
        url = CAMARA_VOTOS.format(ano=ano)
        try:
            if guardados is not None and ano_fechado(ano):
                assinatura = hashlib.sha256("|".join(sorted(ids)).encode()).hexdigest()[:16]
                d, origem = resumo_fechado(guardados, (VERSAO, "camara", ano, assinatura), lambda: baixar(url),
                                           lambda b: ler_votos_camara(b, ids))
                if origem:
                    origens[origem] += 1
            else:
                b = baixar(url)
                d = ler_votos_camara(b, ids) if b else None
        except Exception as ex:
            print(f"[aviso] votacoes: Camara {ano} ilegivel ({ex!r})", file=sys.stderr)
            d = None
        if d is not None:
            veio = True
            out.update(d)
    resumo_log("Votacoes da Camara", origens)
    return out if veio else None


def votos_senado(itens, buscar, cache):
    """{codigoSessaoVotacao: dict(votos={cod: (voto, motivo)}, materia)} das votacoes do Senado pedidas.
    Votacao encerrada nao muda: a resposta fica guardada (cifrada) e so e consultada de novo se o cache expirar."""
    guardados = resultados(cache, "votacoes_senado", 400 * 86400) if cache else None
    out, faltam = {}, {}
    for v in itens:
        g = guardados.get((VERSAO, "senado", v["votacao"])) if guardados else None
        if g:
            out[v["votacao"]] = g
        else:
            faltam.setdefault(v["data"], set()).add(v["votacao"])
    for dia, cods in sorted(faltam.items()):
        lista = buscar(SENADO_DIA.format(dia=dia))
        for x in lista if isinstance(lista, list) else ():
            cod = str(x.get("codigoSessaoVotacao"))
            if cod not in cods:
                continue
            r = dict(materia=x.get("codigoMateria"),
                     votos={str(p.get("codigoParlamentar")): voto_senado(p.get("siglaVotoParlamentar"),
                                                                         p.get("descricaoVotoParlamentar") or "")
                            for p in x.get("votos") or [] if p.get("codigoParlamentar")})
            out[cod] = r
            if guardados is not None and r["votos"]:
                guardados.set((VERSAO, "senado", cod), r)
    return out


def placar(votos):
    """'Sim 375 × Não 113' (com abstencoes, se houver) a partir dos votos individuais."""
    c = Counter(v[0] if isinstance(v, tuple) else v for v in votos.values())
    txt = f"Sim {c['Sim']} × Não {c['Não']}"
    return txt + (f" · {c['Abstenção']} abstenç{'ão' if c['Abstenção'] == 1 else 'ões'}" if c["Abstenção"] else "")


def link(v, meta):
    if v["casa"] == "camara":
        return LINK_CAMARA.format(prop=v["votacao"].split("-")[0])
    m = (meta or {}).get("materia")
    return LINK_SENADO.format(materia=m) if m else "https://www25.senado.leg.br/web/atividade/votacoes-nominais"


def anotar(parl, itens=None, cache=None, buscar=None, camara=None, senado=None, ativo=None):
    """Grava p["votos"] = [dict(id, tema, voto, data, link[, motivo])] em cada parlamentar em exercicio (parlamentares.py)
    e devolve {"placar": {votacao: texto}, "fontes": {"camara": bool, "senado": bool}}. camara/senado: votos prontos
    (testes); sem eles, busca nas fontes oficiais. ativo(dep, data): False se o deputado nao estava no mandato no dia
    (presenca.anotar); a Camara so lista quem votou, entao sem isso todo ausente vira "Nao votou"."""
    itens = carregar() if itens is None else itens
    cam = [v for v in itens if v["casa"] == "camara"]
    sen = [v for v in itens if v["casa"] == "senado"]
    if camara is None and cam:
        camara = votos_camara(cam, cache)
    if senado is None and sen:
        if buscar is None:
            import estados
            buscar = estados.Buscador(intervalo=1.0)
        senado = votos_senado(sen, buscar, cache)
    info = {}
    for v in cam:
        vs = (camara or {}).get(v["votacao"])
        if vs:
            info[v["votacao"]] = (vs, None)
    for v in sen:
        r = (senado or {}).get(v["votacao"])
        if r and r.get("votos"):
            info[v["votacao"]] = (r["votos"], r)
    for p in parl:
        lista = []
        for v in (cam if p["casa"] == "camara" else sen):
            if v["votacao"] not in info:
                continue
            vs, meta = info[v["votacao"]]
            if p["casa"] == "senado" and p["_id"] not in vs:
                continue  # nao estava em exercicio no dia (suplente ou mandato depois)
            if p["casa"] == "camara" and p["_id"] not in vs and ativo and ativo(p["_id"], v["data"]) is False:
                continue
            voto = vs.get(p["_id"], NAO_VOTOU)
            voto, motivo = voto if isinstance(voto, tuple) else (voto, None)
            item = dict(id=v["id"], tema=v["tema"], voto=voto, data=v["data"], link=link(v, meta))
            if motivo:
                item["motivo"] = motivo
            lista.append(item)
        p["votos"] = lista
    fontes = dict(camara=bool(camara) or not cam, senado=bool(senado) or not sen)
    print(f"Votacoes: {len(itens)} curadas, {len(info)} encontradas nas fontes; "
          f"{sum(bool(p.get('votos')) for p in parl)} parlamentares com algum voto.")
    return dict(placar={k: placar(vs) for k, (vs, _) in info.items()}, fontes=fontes)


def secao(votos, cargo, ctx, itens=None):
    """HTML de 'Como votou' (dossie e pagina da pessoa). votos: p["votos"] (ou None); ctx: retorno de anotar()."""
    itens = carregar() if itens is None else itens
    c = _norm(cargo)
    if votos is None:
        if "DEPUTADO FEDERAL" not in c and "SENADOR" not in c:
            return ('<p class="vazio"><b>Não informado</b>: só deputados federais e senadores em exercício votam '
                    'nestes temas.</p>')
        if ctx and not all((ctx.get("fontes") or {}).values()):
            return ('<p class="vazio"><b>Fonte não encontrada</b>: os dados abertos da Câmara ou do Senado não '
                    'responderam nesta execução.</p>')
        return '<p class="vazio"><b>Não informado</b>: a pessoa não está entre os parlamentares em exercício.</p>'
    if not votos:
        return ('<p class="vazio"><b>Não informado</b>: a pessoa não estava no mandato nas votações escolhidas.</p>')
    por_id = {(v["id"], v["data"]): v for v in itens}
    placar_ = (ctx or {}).get("placar") or {}
    linhas = []
    for x in votos:
        v = por_id.get((x["id"], x["data"]), {})
        data = dt.date.fromisoformat(x["data"]).strftime("%d/%m/%Y")
        cls = {"Sim": "sim", "Não": "nao", NAO_VOTOU: "ausente"}.get(x["voto"], "outro")
        motivo = f'<br><small>{e(x["motivo"])}</small>' if x.get("motivo") else ""
        pl = placar_.get(v.get("votacao"))
        linhas.append(
            f'<li><details><summary><span class="voto {cls}">{e(x["voto"])}</span> <b>{e(x["tema"])}</b> '
            f'<small>{data}</small></summary><p>{e(v.get("explicacao", ""))} <small>{e(v.get("sim", ""))}</small></p>'
            f'<p>{motivo.removeprefix("<br>")}{f"<small>Placar na casa: {e(pl)}.</small> " if pl else ""}'
            f'<a href="{e(x["link"])}" target="_blank" rel="noopener">Ver na fonte oficial</a></p></details></li>')
    votou = sum(x["voto"] != NAO_VOTOU for x in votos)
    return (f'<p>Votou em <b>{votou}</b> de <b>{len(votos)}</b> {"tema" if len(votos) == 1 else "temas"} que mexem '
            'com a vida de todo mundo. Abra um tema para ver o que estava em jogo. '
            '<b>Concorda com esses votos?</b> Cobre.</p>'
            '<ul class="nt votos">' + "".join(linhas) + "</ul>")


def demo(cargo):
    """Dados ficticios (pipeline --demo, testes de interface): votos e presenca de um parlamentar inventado."""
    c = _norm(cargo)
    casa = "camara" if "DEPUTADO FEDERAL" in c else "senado" if "SENADOR" in c else None
    if not casa:
        return {}
    votos = [dict(id=v["id"], tema=v["tema"], voto=("Sim", "Não", "Sim", NAO_VOTOU)[i % 4], data=v["data"],
                  link=link(v, {"materia": 1})) for i, v in enumerate(carregar()) if v["casa"] == casa]
    plen = [180, 200] if casa == "camara" else [610, 700]
    return dict(casa=casa, votos=votos, presenca=dict(
        pct=round(100 * plen[0] / plen[1], 1), media_casa=86.4, plenario=plen,
        comissoes=[40, 62] if casa == "camara" else None, comissoes_pct=64.5 if casa == "camara" else None,
        comissoes_media=71.2 if casa == "camara" else None, justificadas=None if casa == "camara" else 35,
        de="2023-02-01", ate="2026-10-15", link="https://www.camara.leg.br/deputados/quem-sao"))
