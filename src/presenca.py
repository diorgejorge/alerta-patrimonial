"""Presenca (#58): presenca registrada de deputados federais e senadores em exercicio desde o inicio da legislatura
atual, comparada com a media da casa. Fontes oficiais e gratuitas:
  Camara: arquivos abertos anuais https://dadosabertos.camara.leg.br/arquivos/ (eventos, eventosOrgaos,
          eventosPresencaDeputados) e membros das comissoes (orgaosDeputados, por legislatura)
          plenario = sessoes deliberativas encerradas; comissoes = reunioes deliberativas das comissoes em que a
          pessoa era titular na data
  Senado: API de Dados Abertos https://legis.senado.leg.br/dadosabertos/votacao (votacoes nominais de plenario, uma
          consulta por mes); a API nao publica presenca em comissoes
Falta registrada nao e falta injustificada: licenca, missao oficial e saude contam como ausencia nos dados abertos da
Camara. No Senado, as ausencias com justificativa oficial sao contadas a parte.
Camara: periodos longos sem nenhum registro (licenca longa, cargo no governo) e antes da posse ou depois da saida
ficam fora da conta: uma sessao so e esperada se a pessoa tem algum registro ate JANELA dias antes ou depois."""
import bisect, calendar, csv, datetime as dt, html, io, sys
from collections import Counter
from pathlib import Path
import cifra
from cache import ano_fechado, resultados, resumo_fechado, resumo_log
import votacoes

VERSAO = 1  # mude ao alterar a leitura: invalida os resumos guardados
ARQ = "https://dadosabertos.camara.leg.br/arquivos/{n}/csv/{n}-{ano}.csv"
MEMBROS = "https://dadosabertos.camara.leg.br/arquivos/orgaosDeputados/csv/orgaosDeputados-L{leg}.csv"
SENADO_MES = "https://legis.senado.leg.br/dadosabertos/votacao?dataInicio={ini}&dataFim={fim}"
JANELA = 45  # dias: sem nenhum registro antes e depois de uma sessao, a pessoa nao estava no mandato
MINIMO = 20  # sessoes esperadas para entrar na media da casa (suplentes por poucos dias ficam fora da media)
PLENARIO = {"Sessão Deliberativa"}
COMISSAO = {"Reunião Deliberativa", "Audiência Pública e Deliberação"}
FORA = {"PLEN", "MESA"}
UA = {"User-Agent": "alerta-patrimonial/1.0"}
e = html.escape


def legislatura(hoje=None):
    """(numero, data de inicio) da legislatura atual: a 57a comecou em 1/fev/2023 e cada uma dura 4 anos."""
    hoje = hoje or dt.date.today()
    n = (hoje.year - 2023 - (hoje < dt.date(hoje.year, 2, 1))) // 4
    return 57 + n, dt.date(2023 + 4 * n, 2, 1)


def _linhas(bruto):
    b = bytes(bruto) if isinstance(bruto, (bytes, bytearray)) else Path(bruto).read_bytes()
    return csv.DictReader(io.StringIO(b.decode("utf-8-sig")), delimiter=";")


def _dia(s):
    try:
        return dt.date.fromisoformat(str(s)[:10]).toordinal()
    except ValueError:
        return None


def ler_ano_camara(eventos, orgaos, presencas, inicio):
    """Resumo de um ano da Camara: plen [(dia, evento)], com [(dia, evento, (orgaos))], pres {dep: [eventos]} e
    ativos {dep: [dias com algum registro]}. So eventos encerrados a partir de `inicio` (ordinal)."""
    org = {}
    for r in _linhas(orgaos):
        org.setdefault(r["idEvento"], []).append((r["idOrgao"], r["siglaOrgao"]))
    plen, com = [], []
    for r in _linhas(eventos):
        d = _dia(r.get("dataHoraInicio"))
        if d is None or d < inicio or not str(r.get("situacao")).startswith("Encerrada"):
            continue
        os_ = org.get(r["id"], [])
        if r.get("descricaoTipo") in PLENARIO and any(s == "PLEN" for _, s in os_):
            plen.append((d, r["id"]))
        elif r.get("descricaoTipo") in COMISSAO and os_ and not any(s in FORA for _, s in os_):
            com.append((d, r["id"], tuple(sorted(i for i, _ in os_))))
    contam = {x[1] for x in plen} | {x[1] for x in com}
    pres, ativos = {}, {}
    for r in _linhas(presencas):
        d = _dia(r.get("dataHoraInicio"))
        dep = r.get("idDeputado")
        if not dep or d is None or d < inicio:
            continue
        ativos.setdefault(dep, set()).add(d)
        if r["idEvento"] in contam:
            pres.setdefault(dep, set()).add(r["idEvento"])
    return dict(plen=sorted(plen), com=sorted(com), pres={k: sorted(v) for k, v in pres.items()},
                ativos={k: sorted(v) for k, v in ativos.items()})


def ler_membros(bruto):
    """{dep: [(orgao, dia inicio, dia fim)]} dos titulares (e presidentes) de comissao; suplente nao conta."""
    out = {}
    for r in _linhas(bruto):
        if "SUPLENTE" in votacoes._norm(r.get("cargo")) or r.get("siglaOrgao") in FORA:
            continue
        dep, orgao = r["uriDeputado"].rsplit("/", 1)[-1], r["uriOrgao"].rsplit("/", 1)[-1]
        out.setdefault(dep, []).append((orgao, _dia(r.get("dataInicio")) or 0, _dia(r.get("dataFim")) or 10 ** 7))
    return out


def anos_camara(cache, hoje=None, baixar=None):
    """Resumos de cada ano da legislatura atual; ano fechado fica guardado cifrado (cache.resumo_fechado)."""
    hoje = hoje or dt.date.today()
    baixar = baixar or (lambda url: cifra.baixar(url, None, cab=UA))
    _, ini = legislatura(hoje)
    guardados = resultados(cache, "presenca_camara", 400 * 86400) if cache else None
    out, origens = [], Counter()
    for ano in range(ini.year, hoje.year + 1):
        urls = [ARQ.format(n=n, ano=ano) for n in ("eventos", "eventosOrgaos", "eventosPresencaDeputados")]
        brutos = lambda: tuple(baixar(u) for u in urls)
        ler = lambda ev, og, pr: ler_ano_camara(ev, og, pr, ini.toordinal())
        try:
            if guardados is not None and ano_fechado(ano, hoje):
                d, origem = resumo_fechado(guardados, (VERSAO, "camara", ano, ini.toordinal()), brutos, ler)
                if origem:
                    origens[origem] += 1
            else:
                b = brutos()
                d = ler(*b) if all(b) else None
        except Exception as ex:
            print(f"[aviso] presenca: Camara {ano} ilegivel ({ex!r})", file=sys.stderr)
            d = None
        if d is None:
            print(f"[aviso] presenca: Camara {ano} sem dados", file=sys.stderr)
            continue
        out.append(d)
    resumo_log("Presenca da Camara", origens)
    return out


def juntar(anos):
    """Junta os resumos anuais num so."""
    j = dict(plen=[], com=[], pres={}, ativos={})
    for a in anos:
        j["plen"] += a["plen"]
        j["com"] += a["com"]
        for k in ("pres", "ativos"):
            for dep, v in a[k].items():
                j[k].setdefault(dep, []).extend(v)
    j["plen"].sort()
    j["com"].sort()
    j["pres"] = {k: set(v) for k, v in j["pres"].items()}
    j["ativos"] = {k: sorted(set(v)) for k, v in j["ativos"].items()}
    return j


def ativo(dias, d):
    """True se ha algum registro ate JANELA dias antes ou depois de `d` (ordinal)."""
    i = bisect.bisect_left(dias, d - JANELA)
    return i < len(dias) and dias[i] <= d + JANELA


def conta_camara(dep, base, membros):
    """(plenario [presentes, esperadas], comissoes [presentes, esperadas])."""
    dias, pres = base["ativos"].get(dep, []), base["pres"].get(dep, set())
    esp = [ev for d, ev in base["plen"] if ativo(dias, d)]
    plen = [sum(ev in pres for ev in esp), len(esp)]
    mem = membros.get(dep, [])
    esp_c = [ev for d, ev, orgs in base["com"] if any(o in orgs and a <= d <= b for o, a, b in mem)]
    return plen, [sum(ev in pres for ev in esp_c), len(esp_c)]


def ler_mes_senado(lista):
    """{codigo do senador: [presentes, esperadas, justificadas]} das votacoes nominais de um mes."""
    out = {}
    for x in lista or ():
        for p in x.get("votos") or ():
            cod = str(p.get("codigoParlamentar") or "")
            if not cod:
                continue
            voto, motivo = votacoes.voto_senado(p.get("siglaVotoParlamentar"), p.get("descricaoVotoParlamentar") or "")
            c = out.setdefault(cod, [0, 0, 0])
            c[1] += 1
            if voto != votacoes.NAO_VOTOU:
                c[0] += 1
            elif motivo:
                c[2] += 1
    return out


def meses_senado(buscar, cache, hoje=None):
    """Soma por senador desde o inicio da legislatura; mes encerrado fica guardado cifrado. None se nada veio."""
    hoje = hoje or dt.date.today()
    _, ini = legislatura(hoje)
    guardados = resultados(cache, "presenca_senado", 400 * 86400) if cache else None
    total, veio, falhas = {}, False, 0
    a, m = ini.year, ini.month
    while (a, m) <= (hoje.year, hoje.month):
        fim = dt.date(a, m, calendar.monthrange(a, m)[1])
        k = (VERSAO, "senado", f"{a}-{m:02d}")
        fechado = (fim - hoje).days < -10  # mes encerrado ha mais de 10 dias
        d = guardados.get(k) if guardados and fechado else None
        if d is None:
            lista = buscar(SENADO_MES.format(ini=f"{a}-{m:02d}-01", fim=fim.isoformat()))
            if isinstance(lista, list):
                d = ler_mes_senado(lista)
                if guardados is not None and fechado:
                    guardados.set(k, d)
            else:
                falhas += 1
        if d is not None:
            veio = True
            for cod, c in d.items():
                t = total.setdefault(cod, [0, 0, 0])
                for i in range(3):
                    t[i] += c[i]
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    if falhas:
        print(f"[aviso] presenca: {falhas} mes(es) sem resposta do Senado", file=sys.stderr)
    return total if veio else None


def _pct(c):
    return round(100 * c[0] / c[1], 1) if c and c[1] else None


def _media(valores):
    v = [_pct(c) for c in valores if c and c[1] >= MINIMO]
    return round(sum(v) / len(v), 1) if v else None


def anotar(parl, cache=None, buscar=None, hoje=None, camara=None, membros=None, senado=None):
    """Grava p["presenca"] em cada parlamentar em exercicio (parlamentares.py):
      dict(pct, media_casa, plenario=[presentes, esperadas], comissoes=[presentes, esperadas] ou None,
           comissoes_pct, comissoes_media, justificadas (Senado), de, ate, link)
    Devolve {"fontes": {...}, "ativo": funcao(dep, data ISO) -> bool} para votacoes.anotar saber quem estava no
    mandato no dia. camara (resumo juntado)/membros/senado: dados prontos (testes)."""
    hoje = hoje or dt.date.today()
    leg, ini = legislatura(hoje)
    deps = [p for p in parl if p["casa"] == "camara"]
    sens = [p for p in parl if p["casa"] == "senado"]
    if camara is None and deps:
        anos = anos_camara(cache, hoje)
        camara = juntar(anos) if anos else None
        b = cifra.baixar(MEMBROS.format(leg=leg), None, cab=UA) if camara else None
        membros = ler_membros(b) if b else None
    if senado is None and sens:
        if buscar is None:
            import estados
            buscar = estados.Buscador(intervalo=1.0)
        senado = meses_senado(buscar, cache, hoje)
    contas = {}
    if camara:
        ate = max([d for d, _ in camara["plen"]] or [ini.toordinal()])
        for p in deps:
            contas[id(p)] = conta_camara(p["_id"], camara, membros or {}) + (None, ate)
    if senado:
        for p in sens:
            c = senado.get(p["_id"])
            if c:
                contas[id(p)] = ([c[0], c[1]], None, c[2], hoje.toordinal())
    medias = {}
    for casa, grupo in (("camara", deps), ("senado", sens)):
        cs = [contas[id(p)] for p in grupo if id(p) in contas]
        medias[casa] = (_media(c[0] for c in cs), _media(c[1] for c in cs if c[1] is not None and membros))
    for p in parl:
        c = contas.get(id(p))
        if not c or not c[0][1]:
            continue
        plen, com, just, ate = c
        tem_com = com is not None and membros is not None and com[1] > 0
        p["presenca"] = dict(pct=_pct(plen), media_casa=medias[p["casa"]][0], plenario=plen,
                             comissoes=com if tem_com else None, comissoes_pct=_pct(com) if tem_com else None,
                             comissoes_media=medias[p["casa"]][1] if tem_com else None, justificadas=just,
                             de=ini.isoformat(), ate=dt.date.fromordinal(ate).isoformat(), link=p.get("perfil"))
    print(f"Presenca: {sum('presenca' in p for p in parl)} de {len(parl)} parlamentares com dado; media do plenario "
          f"Camara {medias['camara'][0]}%, Senado {medias['senado'][0]}%.")
    dias = (camara or {}).get("ativos", {})

    def no_mandato(dep, data):
        """Para a Camara: None sem dado de presenca (nao da para saber)."""
        if not camara:
            return None
        return ativo(dias.get(dep, []), dt.date.fromisoformat(data).toordinal())

    return dict(fontes=dict(camara=bool(camara) or not deps, senado=bool(senado) or not sens), ativo=no_mandato)


def _barra(rot, c, pct, media, oque):
    """'90% de presença no plenário' + barra com o traço da média da casa + '180 de 200 sessões'."""
    if pct is None:
        return ""
    m = f'<span class="media" style="left:{media:.0f}%"></span>' if media is not None else ""
    return (f'<div class="pres"><p><b class="grande">{_fmt(pct)}</b> de presença {rot}'
            f'{f" <small>· média da casa: {_fmt(media)}</small>" if media is not None else ""}</p>'
            f'<div class="barra" role="img" aria-label="Presença {rot}: {_fmt(pct)}; média da casa {_fmt(media)}">'
            f'<span style="width:{pct:.0f}%"></span>{m}</div><p><small>{c[0]} de {c[1]} {oque}</small></p></div>')


def _fmt(v):
    return "Não informado" if v is None else f"{v:.1f}%".replace(".", ",")


def secao(r, cargo, fontes, casa=None):
    """HTML de 'Presenca' (dossie e pagina da pessoa). r: p["presenca"] ou None."""
    c = votacoes._norm(cargo)
    if r is None:
        if "DEPUTADO FEDERAL" not in c and "SENADOR" not in c and not casa:
            return '<p class="vazio"><b>Não informado</b>: a presença é medida só para deputados federais e senadores.</p>'
        if fontes and not all(fontes.values()):
            return ('<p class="vazio"><b>Fonte não encontrada</b>: os dados abertos da Câmara ou do Senado não '
                    'responderam nesta execução.</p>')
        return '<p class="vazio"><b>Não informado</b>: a pessoa não está entre os parlamentares em exercício.</p>'
    de = dt.date.fromisoformat(r["de"]).strftime("%d/%m/%Y")
    senado = r.get("justificadas") is not None
    oque = "votações nominais" if senado else "sessões de votação"
    txt = _barra("no plenário", r["plenario"], r["pct"], r.get("media_casa"), f"{oque} desde {de}")
    if r.get("comissoes"):
        txt += _barra("nas comissões", r["comissoes"], r.get("comissoes_pct"), r.get("comissoes_media"),
                      "reuniões de votação das comissões de que é titular")
    elif senado:
        txt += '<p class="mut"><small>Comissões: Não informado (o Senado não publica essa presença).</small></p>'
    if senado and r["justificadas"]:
        txt += f'<p class="mut"><small>{r["justificadas"]} ausências têm justificativa oficial (licença ou missão).</small></p>'
    nota = ("Medida pelas votações nominais do plenário." if senado else
            "A Câmara não informa se a falta foi justificada (licença, missão, saúde). Afastamentos longos não contam.")
    link = (f' <a href="{e(r["link"])}" target="_blank" rel="noopener">Ver o perfil oficial</a>'
            if str(r.get("link") or "").startswith("https://") else "")
    return txt + f'<p class="mut"><small>{nota}{link}</small></p>'
