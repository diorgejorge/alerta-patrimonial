"""Graficos estaticos (SVG inline + tabela HTML alternativa) para as paginas geradas pelo pipeline.
So biblioteca padrao, sem JS nem servico externo. Nenhuma cor fixa: so classes CSS e currentColor,
o tema claro/escuro vem do CSS da pagina. Todo texto passa por html.escape.
Classes: nv-forte/nv-atencao/nv-informativo e tag-<tema> nas marcas; g-txt/g-mut nos textos;
g-eixo nas linhas de grade/base; g-padrao na camada de hachura; g-hachura nos <pattern>;
g-barra/g-coluna nas marcas; g-tabela nas tabelas alternativas."""
import html, math, re
from texto import cap as _cap

e = html.escape
# so a cor da faixa (#62): o significado e a formula ficam na legenda, sem rotulo que soe como julgamento
ROTULO_NIVEL = {"forte": "Faixa vermelha", "atencao": "Faixa laranja", "informativo": "Faixa azul"}
# regua dos colegas (#64): mesma marcacao do painel (RG/COL em template.html)
P_ALTO = 90  # ponto dourado: cresceu mais que 90 de cada 100 colegas
PARTE = ("a dos que menos cresceram", "a segunda", "a do meio", "a quarta", "a dos que mais cresceram")


def regua_colegas(a):
    """Em qual das 5 partes iguais de colegas (do menor ao maior crescimento) a pessoa esta, com o valor ao lado
    (para conferir a faixa) e a legenda do grupo comparado. Sem percentil: 'Não informado'."""
    p = a.get("percentil")
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "Não informado"
    q, alto = min(4, int(p // 20)), p >= P_ALTO
    rotulo = (f"Posição do crescimento entre os colegas: parte {q + 1} de 5, {PARTE[q]}"
              + (f"; cresceu mais que {P_ALTO} de cada 100" if alto else ""))
    valor = "o maior do grupo" if p >= 99.5 else f"acima de {p:.0f}% dos colegas"
    n, cargo = int(a.get("n_pares") or 0), a.get("cargo_pares")
    n_txt = f"{n:,}".replace(",", ".")
    depois = _cap(a.get("cargo")) or _cap(cargo)  # cargo do fim do periodo: se mudou, a legenda explica o grupo
    grupo = ("" if not n
             else f"Entre {n_txt} candidatos a {e(_cap(cargo))} em {a.get('ano_ini')}" if cargo and depois == _cap(cargo)
             else f"Entre {n_txt} que disputaram {e(_cap(cargo))} em {a.get('ano_ini')}, como esta pessoa "
                  f"(depois ela disputou {e(depois)})" if cargo
             else f"Entre {n_txt} pessoas de todos os cargos em {a.get('ano_ini')} (poucos colegas de cargo)")
    return ('<span class="colegas"><span class="regua-linha"><small aria-hidden="true">menos</small>'
            f'<span class="regua{" alto" if alto else ""}" role="img" aria-label="{e(rotulo)}">' + "<i></i>" * 5
            + f'<b style="left:{q * 20 + 10}%"></b></span><small aria-hidden="true">mais</small></span>'
            f' {valor}<small>{grupo}</small></span>')


ROTULO_TAG = {"politico": "Político", "eleitoral": "Eleitoral", "legislativo": "Legislativo",
              "gestao": "Gestão", "patrimonial": "Patrimonial", "judicial": "Judicial",
              "criminal": "Segurança", "outros": "Outros"}
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
VAZIO_PATRIMONIO = '<p class="vazio">Sem declarações para exibir.</p>'
VAZIO_NOTICIAS = '<p class="vazio">Ainda não há notícias classificadas.</p>'
RE_MES = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


# ---------------------------------------------------------------- numeros (pt-BR)
def _nulo(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def _num(v, casas=0):
    """12345.6 -> '12.346' (casas=0) / '12.345,6' (casas=1)."""
    return f"{v:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def inteiro(n):
    return _num(round(n))


def brl(v):
    """Valor completo: R$ 1.234.567 (sem centavos)."""
    if _nulo(v):
        return "Não informado"
    return ("-" if round(v) < 0 else "") + "R$ " + _num(abs(v))


def brl_compacto(v):
    """R$ 950 / R$ 12,3 mil / R$ 1,2 mi / R$ 3,4 bi (uma casa abaixo de 100, nenhuma acima)."""
    if _nulo(v):
        return "Não informado"
    a = abs(float(v))
    sinal = "-" if v < 0 else ""
    for base, suf in ((1e9, "bi"), (1e6, "mi"), (1e3, "mil")):
        q = a / base
        casas = 1 if q < 99.95 else 0
        r = round(q, casas)
        if r >= 1:
            txt = _num(r, casas)
            return f"{sinal}R$ {txt[:-2] if txt.endswith(',0') else txt} {suf}"
    return (sinal if round(a) else "") + "R$ " + _num(a)


def _qtd(v):
    try:
        return max(int(v or 0), 0)
    except (TypeError, ValueError):  # None/NaN/texto
        return 0


def _n(v):
    """Coordenada curta para o SVG: 12.0 -> '12', 3.25 -> '3.2'."""
    return f"{v:.1f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------- pecas comuns
def _id(uid, tipo):
    """Prefixo de id seguro: g-<uid>-<tipo>, entao o mesmo uid serve para todos os graficos da pagina
    (comeca com letra, nunca com digito hex apos o #)."""
    return "g-" + (re.sub(r"[^A-Za-z0-9_-]+", "-", str(uid)) or "x") + "-" + tipo


def _abre(p, w, h, titulo, desc, cls):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="grafico {cls}" viewBox="0 0 {_n(w)} {_n(h)}" '
            f'width="100%" font-size="12" role="img" aria-labelledby="{p}-t" aria-describedby="{p}-d">'
            f'<title id="{p}-t">{e(titulo)}</title><desc id="{p}-d">{e(desc)}</desc>')


def _padroes(p):
    """Hachuras por nivel (forte 45 graus, atencao 135 graus, informativo pontos) em currentColor."""
    lin = '<line x1="3" y1="0" x2="3" y2="6" stroke="currentColor" stroke-width="1.5"/>'
    return ("<defs>"
            f'<pattern id="{p}-forte" class="g-hachura" width="6" height="6" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate(45)">{lin}</pattern>'
            f'<pattern id="{p}-atencao" class="g-hachura" width="6" height="6" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate(135)">{lin}</pattern>'
            f'<pattern id="{p}-informativo" class="g-hachura" width="5" height="5" patternUnits="userSpaceOnUse">'
            '<circle cx="2.5" cy="2.5" r="1.1" fill="currentColor" stroke="currentColor" stroke-width=".3"/>'
            "</pattern></defs>")


def _ponta_dir(x, y, w, h, r=4):
    """Barra horizontal com a ponta direita arredondada."""
    r = min(r, w / 2, h / 2)
    if r < .5:
        return f"M{_n(x)},{_n(y)}h{_n(w)}v{_n(h)}h{_n(-w)}z"
    return (f"M{_n(x)},{_n(y)}h{_n(w - r)}a{_n(r)},{_n(r)} 0 0 1 {_n(r)},{_n(r)}v{_n(h - 2 * r)}"
            f"a{_n(r)},{_n(r)} 0 0 1 {_n(-r)},{_n(r)}h{_n(-(w - r))}z")


def _ponta_topo(x, y, w, h, r=4):
    """Coluna com os cantos de cima arredondados (y = topo)."""
    r = min(r, w / 2, h)
    if r < .5:
        return f"M{_n(x)},{_n(y)}h{_n(w)}v{_n(h)}h{_n(-w)}z"
    return (f"M{_n(x)},{_n(y + h)}v{_n(-(h - r))}a{_n(r)},{_n(r)} 0 0 1 {_n(r)},{_n(-r)}h{_n(w - 2 * r)}"
            f"a{_n(r)},{_n(r)} 0 0 1 {_n(r)},{_n(r)}v{_n(h - r)}z")


def _texto(x, y, s, cls="g-txt", ancora="start", extra=""):
    return (f'<text x="{_n(x)}" y="{_n(y)}" dy=".35em" text-anchor="{ancora}" class="{cls}" '
            f'fill="currentColor"{extra}>{e(s)}</text>')


def _tabela(titulo, cab, linhas, rodape=None):
    """Tabela simples: primeira coluna e cabecalho de linha."""
    def tr(l):
        return f'<tr><th scope="row">{e(l[0])}</th>' + "".join(f"<td>{e(c)}</td>" for c in l[1:]) + "</tr>"
    th = "".join(f'<th scope="col">{e(c)}</th>' for c in cab)
    pe = f"<tfoot>{tr(rodape)}</tfoot>" if rodape else ""
    return (f'<table class="g-tabela"><caption>{e(titulo)}</caption><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(tr(l) for l in linhas)}</tbody>{pe}</table>')


# ---------------------------------------------------------------- 1. alertas por nivel
def _niveis(contagens):
    return [(k, rot, _qtd((contagens or {}).get(k))) for k, rot in ROTULO_NIVEL.items()]


def barras_niveis(contagens: dict, uid: str, titulo: str = "Destaques por nível") -> str:
    p, vals = _id(uid, "niv"), _niveis(contagens)
    W, X0, LIN, ESP, TOPO = 440, 176, 32, 20, 6
    area = W - X0 - 56  # sobra espaco para o rotulo de valor na ponta
    m = max(v for _, _, v in vals) or 1
    desc = "Barras horizontais. " + "; ".join(f"{rot}: {inteiro(v)}" for _, rot, v in vals) + "."
    partes = [_abre(p, W, TOPO * 2 + LIN * len(vals), titulo, desc, "g-niveis"), _padroes(p)]
    for i, (k, rot, v) in enumerate(vals):
        y = TOPO + i * LIN + (LIN - ESP) / 2
        w = max(2.0, v / m * area)  # zero: barra minima de 2 px
        d, meio = _ponta_dir(X0, y, w, ESP), y + ESP / 2
        partes += [_texto(X0 - 8, meio, rot, ancora="end"),
                   f'<path d="{d}" class="g-barra nv-{k}"/>',
                   f'<path d="{d}" class="g-padrao" fill="url(#{p}-{k})"/>',
                   _texto(X0 + w + 6, meio, inteiro(v))]
    return "".join(partes) + "</svg>"


def tabela_niveis(contagens: dict, titulo: str = "Destaques por nível") -> str:
    vals = _niveis(contagens)
    return _tabela(titulo, ("Faixa", "Destaques"), [(rot, inteiro(v)) for _, rot, v in vals],
                   ("Total", inteiro(sum(v for _, _, v in vals))))


# ---------------------------------------------------------------- 2. patrimonio por eleicao
def _pontos(pontos):
    """[(ano, valor)] valido, ordenado por ano; ano repetido fica com o ultimo valor."""
    out = {}
    for ano, v in pontos or []:
        if _nulo(v):
            continue
        try:
            out[int(ano)] = float(v)
        except (TypeError, ValueError):
            continue
    return sorted(out.items())


def _escala(m):
    """Passo 'redondo' (1/2/2,5/5 x 10^k) e numero de linhas (3 ou 4) acima do zero."""
    m = max(m, 1000.0)
    bruto = m / 4
    mag = 10 ** math.floor(math.log10(bruto))
    for f in (1, 2, 2.5, 5, 10):
        passo = f * mag
        if passo >= bruto * (1 - 1e-9):
            break
    return passo, max(1, math.ceil(m / passo - 1e-9))


def aumento_percentual(v, base):
    """Quanto o patrimonio aumentou sobre o valor original: (v - base) / base x 100, ex. '+200%' ou 'diminuiu 40%'."""
    if _nulo(v) or _nulo(base):
        return "Não informado"
    if base <= 0:
        return "começou do zero" if v > 0 else "Não informado"
    pct = (v - base) / base * 100
    return f"+{_num(pct)}%" if pct >= 0 else f"diminuiu {_num(-pct)}%"


def patrimonio(pontos: list[tuple[int, float]], uid: str,
               titulo: str = "Patrimônio declarado por eleição") -> str:
    """Colunas na proporcao do patrimonio, rotuladas por quantas vezes aumentou desde a primeira eleicao, sem reais."""
    pts = _pontos(pontos)
    if not pts:
        return VAZIO_PATRIMONIO
    p, n = _id(uid, "pat"), len(pts)
    W, H, ESQ, DIR, BAIXO = 360, 200, 62, 8, 22
    slot = (W - ESQ - DIR) / n
    escalona = slot < 44           # colunas estreitas: rotulos alternam de altura
    TOPO = 34 if escalona else 20
    alt = H - TOPO - BAIXO
    passo, k = _escala(max(v for _, v in pts))
    topo = passo * k
    base = pts[0][1]
    rotulos = ["início"] + [aumento_percentual(v, base) for _, v in pts[1:]]
    if n == 1:
        desc = f"Só há a declaração da eleição de {pts[0][0]}."
    else:
        desc = (f"Colunas por eleição, de {pts[0][0]} a {pts[-1][0]}, com quanto o patrimônio aumentou desde {pts[0][0]}. "
                + "; ".join(f"{a}: {rot}" for (a, _), rot in zip(pts, rotulos)) + ".")
    partes = [_abre(p, W, H, titulo, desc, "g-patrimonio")]
    for i in range(k + 1):  # grade
        y = TOPO + alt - passo * i / topo * alt
        partes.append(f'<line x1="{ESQ}" y1="{_n(y)}" x2="{W - DIR}" y2="{_n(y)}" class="g-eixo" '
                      'stroke="currentColor" stroke-width="1"/>')
    cw = min(40, slot * .6)
    fs = "11" if slot >= 60 else "10"
    for i, (ano, v) in enumerate(pts):
        cx = ESQ + slot * (i + .5)
        hv = max(2.0, max(v, 0) / topo * alt)
        y = TOPO + alt - hv
        rot = rotulos[i]
        partes += [f'<path d="{_ponta_topo(cx - cw / 2, y, cw, hv)}" class="g-coluna" fill="currentColor"/>',
                   _texto(cx, y - 7 - (12 if escalona and i % 2 else 0), rot, ancora="middle",
                          extra=f' font-size="{fs}"'),
                   _texto(cx, H - 9, str(ano), "g-mut", "middle", ' font-size="10"')]
    return "".join(partes) + "</svg>"


def tabela_patrimonio(pontos: list[tuple[int, float]],
                      titulo: str = "Patrimônio declarado por eleição") -> str:
    pts = _pontos(pontos)
    if not pts:
        return ""
    base = pts[0][1]
    linhas = [(str(ano), "—" if i == 0 else aumento_percentual(v, pts[i - 1][1]), "início" if i == 0 else aumento_percentual(v, base))
              for i, (ano, v) in enumerate(pts)]
    return _tabela(titulo, ("Eleição", "Aumento sobre a eleição anterior", f"Aumento desde {pts[0][0]}"), linhas)


# ---------------------------------------------------------------- 3. mini grafico de patrimonio
def mini_patrimonio(pontos: list[tuple[int, float]], uid: str) -> str:
    pts = _pontos(pontos)
    if len(pts) < 2:
        return ""
    W, H, M = 96, 28, 4
    (a0, v0), (a1, v1) = pts[0], pts[-1]
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)

    def xy(a, v):  # x proporcional ao ano; serie constante fica no meio
        y = H / 2 if hi == lo else M + (hi - v) / (hi - lo) * (H - 2 * M)
        return M + (a - a0) / (a1 - a0) * (W - 2 * M), y

    coords = [xy(a, v) for a, v in pts]
    rot = f"Aumento do patrimônio de {a0} a {a1}: {aumento_percentual(v1, v0)}"
    linha = " ".join(f"{_n(x)},{_n(y)}" for x, y in coords)
    x, y = coords[-1]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="grafico g-mini" viewBox="0 0 {W} {H}" '
            f'width="{W}" height="{H}" role="img" aria-label="{e(rot)}">'
            f'<title id="{_id(uid, "mini")}-t">{e(rot)}</title>'
            f'<polyline points="{linha}" class="g-txt" stroke="currentColor" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round" style="fill:none"/>'
            f'<circle cx="{_n(x)}" cy="{_n(y)}" r="3" class="g-txt" fill="currentColor"/></svg>')


# ---------------------------------------------------------------- 4. noticias por tema
def _temas(series):
    """[(tag, {mes: qtd}, total)] so com total > 0, na ordem de ROTULO_TAG (desconhecidas no fim)."""
    ordem, out = list(ROTULO_TAG), []
    for tag, s in (series or {}).items():
        cont = {str(m): _qtd(q) for m, q in (s or {}).items() if RE_MES.match(str(m))}
        tot = sum(cont.values())
        if tot:
            out.append((str(tag), cont, tot))
    out.sort(key=lambda t: (ordem.index(t[0]) if t[0] in ordem else len(ordem), t[0]))
    return out


def _meses(temas):
    """Faixa continua AAAA-MM do primeiro ao ultimo mes presente."""
    ms = sorted({m for _, c, _ in temas for m in c})
    a, m = int(ms[0][:4]), int(ms[0][5:])
    out = []
    while True:
        k = f"{a:04d}-{m:02d}"
        out.append(k)
        if k >= ms[-1]:
            return out
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def _mes_rot(k):
    return f"{MESES[int(k[5:]) - 1]}/{k[:4]}"


def _rot_tag(tag):
    return ROTULO_TAG.get(tag, tag)


def _qtd_noticias(n):
    return f"{inteiro(n)} notícia" + ("" if n == 1 else "s")


def noticias_por_tema(series: dict[str, dict[str, int]], uid: str,
                      titulo: str = "Notícias por tema ao longo do tempo") -> str:
    temas = _temas(series)
    if not temas:
        return VAZIO_NOTICIAS
    p, meses = _id(uid, "tem"), _meses(temas)
    W, ESQ, DIR, TOPO, LIN, BARRA, BAIXO = 360, 104, 8, 22, 40, 26, 20
    nm = len(meses)
    slot = (W - ESQ - DIR) / nm
    bw = slot * .7 if slot >= 4 else slot
    mx = max(max(c.values()) for _, c, _ in temas)
    H = TOPO + LIN * len(temas) + BAIXO
    picos = []
    for tag, c, tot in temas:
        pm = max(meses, key=lambda m: c.get(m, 0))
        picos.append(f"{_rot_tag(tag)}: {_qtd_noticias(tot)}, pico de {inteiro(c[pm])} em {_mes_rot(pm)}")
    desc = (f"Pequenos múltiplos, um por tema, de {_mes_rot(meses[0])} a {_mes_rot(meses[-1])}, "
            f"na mesma escala (máximo de {inteiro(mx)} por mês). " + "; ".join(picos) + ".")
    partes = [_abre(p, W, H, titulo, desc, "g-temas"),
              _texto(W - DIR, 10, f"Escala comum: até {inteiro(mx)} por mês", "g-mut", "end", ' font-size="10"')]
    for i, (tag, c, tot) in enumerate(temas):
        y0 = TOPO + i * LIN
        base = y0 + BARRA + 4
        cls = tag if tag in ROTULO_TAG else "outros"
        rot = _rot_tag(tag)
        rot = rot if len(rot) <= 16 else rot[:15] + "…"
        partes += [_texto(ESQ - 8, y0 + 10, rot, ancora="end"),
                   _texto(ESQ - 8, y0 + 24, _qtd_noticias(tot), "g-mut", "end", ' font-size="10"'),
                   f'<line x1="{ESQ}" y1="{_n(base)}" x2="{W - DIR}" y2="{_n(base)}" class="g-eixo" '
                   'stroke="currentColor" stroke-width="1"/>']
        for j, m in enumerate(meses):
            q = c.get(m, 0)
            if q:
                h = max(1.5, q / mx * BARRA)
                partes.append(f'<rect x="{_n(ESQ + j * slot + (slot - bw) / 2)}" y="{_n(base - h)}" '
                              f'width="{_n(bw)}" height="{_n(h)}" class="g-barra tag-{cls}"/>')
    yx = H - 8  # eixo de meses: primeiro, (meio) e ultimo
    partes.append(_texto(ESQ, yx, _mes_rot(meses[0]), "g-mut", "start", ' font-size="10"'))
    if nm >= 5:
        meio = nm // 2
        partes.append(_texto(ESQ + slot * (meio + .5), yx, _mes_rot(meses[meio]), "g-mut", "middle",
                             ' font-size="10"'))
    if nm >= 2:
        partes.append(_texto(W - DIR, yx, _mes_rot(meses[-1]), "g-mut", "end", ' font-size="10"'))
    return "".join(partes) + "</svg>"


def tabela_noticias_por_tema(series: dict[str, dict[str, int]],
                             titulo: str = "Notícias por tema ao longo do tempo") -> str:
    temas = _temas(series)
    if not temas:
        return ""
    linhas = []
    for m in _meses(temas):  # meses sem nenhuma noticia ficam de fora da tabela
        qs = [c.get(m, 0) for _, c, _ in temas]
        if sum(qs):
            linhas.append([_mes_rot(m)] + [inteiro(q) for q in qs] + [inteiro(sum(qs))])
    cab = ["Mês"] + [_rot_tag(t) for t, _, _ in temas] + ["Total"]
    rodape = ["Total"] + [inteiro(t) for _, _, t in temas] + [inteiro(sum(t for _, _, t in temas))]
    return _tabela(titulo, cab, linhas, rodape)


# ---------------------------------------------------------------- 5. noticias da pessoa: % por tema (#54)
def _fatias(contagens):
    """[(tag, qtd, %)] so com qtd > 0, da maior para a menor (empate: ordem de ROTULO_TAG)."""
    ordem = list(ROTULO_TAG)
    vals = [(str(t), _qtd(q)) for t, q in (contagens or {}).items() if _qtd(q)]
    tot = sum(q for _, q in vals)
    vals.sort(key=lambda v: (-v[1], ordem.index(v[0]) if v[0] in ordem else len(ordem), v[0]))
    return [(t, q, q * 100 / tot) for t, q in vals]


def _pct(v):
    return f"{_num(v)}%" if v >= 1 or v == 0 else "<1%"


def percentual_por_tema(contagens: dict[str, int], uid: str, titulo: str = "Notícias por tema") -> str:
    fatias = _fatias(contagens)
    if not fatias:
        return VAZIO_NOTICIAS
    p = _id(uid, "pct")
    W, X0, LIN, ESP, TOPO = 340, 88, 28, 18, 6
    area = W - X0 - 76  # espaco para "100% (999)" na ponta
    desc = "Barras horizontais, porcentagem das notícias por tema principal. " + "; ".join(
        f"{_rot_tag(t)}: {_pct(v)} ({_qtd_noticias(q)})" for t, q, v in fatias) + "."
    partes = [_abre(p, W, TOPO * 2 + LIN * len(fatias), titulo, desc, "g-pct")]
    for i, (t, q, v) in enumerate(fatias):
        y = TOPO + i * LIN + (LIN - ESP) / 2
        w, meio = max(2.0, v / 100 * area), y + ESP / 2
        cls = t if t in ROTULO_TAG else "outros"
        partes += [_texto(X0 - 8, meio, _rot_tag(t), ancora="end"),
                   f'<path d="{_ponta_dir(X0, y, w, ESP)}" class="g-barra tag-{cls}"/>',
                   _texto(X0 + w + 6, meio, f"{_pct(v)} ({inteiro(q)})")]
    return "".join(partes) + "</svg>"


def tabela_percentual_por_tema(contagens: dict[str, int], titulo: str = "Notícias por tema") -> str:
    fatias = _fatias(contagens)
    if not fatias:
        return ""
    return _tabela(titulo, ("Tema", "Notícias", "%"), [(_rot_tag(t), inteiro(q), _pct(v)) for t, q, v in fatias],
                   ("Total", inteiro(sum(q for _, q, _ in fatias)), "100%"))
