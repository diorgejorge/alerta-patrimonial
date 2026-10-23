"""Economia no periodo (#55): o estado e o Brasil estavam em crescimento, declinio ou recessao entre as declaracoes
de bens da pessoa? So sinaliza o contexto: nao compara com o patrimonio (pedido do usuario em 23/10/2026).
Fonte oficial e gratuita: IBGE/SIDRA (apisidra.ibge.gov.br, sem chave), 2 consultas por execucao:
  6784 (Brasil): v9810 variacao real do PIB (%), v9811 deflator do PIB (%)
  5938 (UF):     v37 PIB a precos correntes (mil reais); o IBGE publica com ~2 anos de atraso
O PIB real por UF nao esta no SIDRA: e estimado pelo PIB nominal da UF descontado o deflator do PIB nacional (o texto
da pagina avisa). Dado publico agregado, sem dado pessoal: fica em data/economia.json e vale como reserva quando o
IBGE esta fora do ar."""
import datetime as dt, html, json, math, sys
from pathlib import Path
import estados

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
ARQUIVO = ROOT / "data" / "economia.json"
SIDRA = "https://apisidra.ibge.gov.br/values"
LINK = dict(brasil="https://sidra.ibge.gov.br/tabela/6784", uf="https://sidra.ibge.gov.br/tabela/5938")
ESTAVEL = 0.005  # variacao real abaixo de 0,5% (para mais ou para menos): "Estável"
NAO_ACHOU, NAO_INFORMADO = "Fonte não encontrada", "Não informado"
e = html.escape


# ---------------------------------------------------------------- coleta
def urls():
    return dict(brasil=f"{SIDRA}/t/6784/n1/all/v/9810,9811/p/all", uf=f"{SIDRA}/t/5938/n3/all/v/37/p/all")


def _numero(v):
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):  # "..", "-", "X": sem dado
        return None
    return x if math.isfinite(x) else None


def ler_sidra(resposta):
    """Linhas do apisidra como dicts {territorio, variavel, periodo, valor}. A primeira linha e o cabecalho: as
    dimensoes sao achadas pelo rotulo dele (a ordem D1..D4 muda conforme a consulta). Valor sem numero sai."""
    if not isinstance(resposta, list) or len(resposta) < 2 or not isinstance(resposta[0], dict):
        return []
    cab = resposta[0]
    achar = lambda *rots: next((k for k, v in cab.items() if k.endswith("C") and str(v).startswith(rots)), None)
    k_var, k_per, k_ter = achar("Variável"), achar("Ano"), achar("Brasil", "Unidade da Federação")
    if not (k_var and k_per and k_ter):
        return []
    out = []
    for r in resposta[1:]:
        valor = _numero(r.get("V"))
        if valor is not None:
            out.append(dict(territorio=str(r.get(k_ter)), variavel=str(r.get(k_var)), periodo=str(r.get(k_per)),
                            valor=valor))
    return out


def montar(brasil, uf, siglas):
    """{brasil: {volume, deflator}, uf: {sigla: {ano: pib}}} com anos em texto. `siglas`: {codigo IBGE: sigla}."""
    vol, defl = {}, {}
    for r in ler_sidra(brasil):
        {"9810": vol, "9811": defl}.get(r["variavel"], {})[r["periodo"]] = r["valor"]
    por_uf = {}
    for r in ler_sidra(uf):
        if r["variavel"] == "37" and r["territorio"] in siglas:
            por_uf.setdefault(siglas[r["territorio"]], {})[r["periodo"]] = r["valor"]
    return dict(brasil=dict(volume=vol, deflator=defl), uf=por_uf)


def completo(econ):
    return bool(econ and econ.get("brasil", {}).get("volume") and econ.get("uf"))


def coletar(buscar, siglas, arquivo=ARQUIVO, hoje=None):
    """Baixa as 2 tabelas e grava `arquivo`. Falhou alguma: devolve o ultimo salvo (ou {} sem nada salvo).
    `buscar(url)` devolve o JSON ou None (estados.Buscador: espaca as consultas e espera no 429)."""
    u = urls()
    econ = montar(buscar(u["brasil"]), buscar(u["uf"]), siglas)
    arquivo = Path(arquivo)
    if completo(econ):
        econ["atualizado"] = (hoje or dt.date.today()).isoformat()
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(econ, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        print(f"IBGE: PIB do Brasil até {ultimo(econ['brasil']['volume'])}, dos estados até "
              f"{max(ultimo(v) or 0 for v in econ['uf'].values())}.")
        return econ
    print("[aviso] IBGE/SIDRA indisponível: economia no período usa o último dado salvo", file=sys.stderr)
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def demo():
    """Dados mockados para o --demo e os testes (sem rede)."""
    vol = {"2019": 1.2, "2020": -3.3, "2021": 4.8, "2022": 3.0, "2023": 3.2, "2024": 3.4}
    defl = {"2019": 4.1, "2020": 5.0, "2021": 11.1, "2022": 8.3, "2023": 4.7, "2024": 4.0}
    base = dict(PA=1.6e8, SP=2.3e9, MG=6.5e8, BA=2.9e8)
    cresc = {"2019": 0.05, "2020": 0.01, "2021": 0.16, "2022": 0.12}
    uf = {}
    for sigla, v in base.items():
        uf[sigla] = {"2018": v}
        for ano, c in cresc.items():
            v *= 1 + c + (0.04 if sigla == "PA" else 0)
            uf[sigla][ano] = round(v)
    return dict(brasil=dict(volume=vol, deflator=defl), uf=uf, atualizado="demo")


# ---------------------------------------------------------------- contas
def ultimo(serie):
    return max((int(a) for a in serie or ()), default=None)


def _acumulado(pcts, anos):
    """Produto de (1 + pct/100) nos anos; None se faltar algum."""
    f = 1.0
    for a in anos:
        p = (pcts or {}).get(str(a))
        if p is None:
            return None
        f *= 1 + p / 100
    return f


def real_brasil(econ, ini, fim):
    """Crescimento real do PIB do Brasil de `ini` a `fim` (fracao: 0.05 = +5%); None sem dado."""
    f = _acumulado(econ["brasil"]["volume"], range(ini + 1, fim + 1))
    return None if f is None else f - 1


def real_uf(econ, sigla, ini, fim):
    """Crescimento real estimado do PIB da UF: nominal descontado o deflator do PIB nacional."""
    pib = econ["uf"].get(sigla) or {}
    p0, p1 = pib.get(str(ini)), pib.get(str(fim))
    d = _acumulado(econ["brasil"]["deflator"], range(ini + 1, fim + 1))
    return (p1 / p0) / d - 1 if p0 and p1 and d else None


def _anos_brasil(econ, ini, fim):
    vol = econ["brasil"]["volume"]
    return [(a, vol[str(a)] / 100) for a in range(ini + 1, fim + 1) if str(a) in vol]


def _anos_uf(econ, sigla, ini, fim):
    return [(a, r) for a in range(ini + 1, fim + 1) if (r := real_uf(econ, sigla, a - 1, a)) is not None]


def _economia(real, anos, fim):
    return dict(fim=fim, real=real, quedas=[a for a, v in anos if v < 0])


def periodo(econ, linha):
    """Economia do estado e do Brasil entre as declaracoes de um periodo (linha do alerta). Cada uma vai ate o ultimo
    ano que o IBGE ja publicou; sem nenhum ano depois do inicio, fica None."""
    ini, fim = int(linha.get("ano_ini") or 0), int(linha.get("ano_fim") or 0)
    sigla = str(linha.get("uf") or "").upper()
    out = dict(ini=ini, fim=fim, uf=sigla if sigla in econ.get("uf", {}) else None, estado=None, brasil=None)
    fim_br = min(fim, ultimo(econ["brasil"]["volume"]) or 0)
    if fim_br > ini:
        out["brasil"] = _economia(real_brasil(econ, ini, fim_br), _anos_brasil(econ, ini, fim_br), fim_br)
    fim_uf = min(fim, ultimo(econ["uf"].get(out["uf"])) or 0) if out["uf"] else 0
    if fim_uf > ini:
        out["estado"] = _economia(real_uf(econ, out["uf"], ini, fim_uf), _anos_uf(econ, out["uf"], ini, fim_uf), fim_uf)
    return out


def sinal(v):
    """('sobe'|'cai'|'igual', rotulo) para a variacao real."""
    if v is None:
        return "igual", NAO_INFORMADO
    if v >= ESTAVEL:
        return "sobe", "Em crescimento"
    return ("cai", "Em declínio") if v <= -ESTAVEL else ("igual", "Estável")


# ---------------------------------------------------------------- html
SETA = dict(sobe="▲", cai="▼", igual="●")  # forma alem da cor


def pct(v, sinal_=True):
    """0.056 -> '+5,6%'; 1.85 -> '+185%'; -0.033 -> '−3,3%'."""
    if v is None:
        return NAO_INFORMADO
    p = v * 100
    txt = f"{abs(p):.0f}" if abs(p) >= 100 else f"{abs(p):.1f}".replace(".", ",")
    txt = txt[:-2] if txt.endswith(",0") else txt
    return (("+" if p > 0 else "−" if p < 0 else "") if sinal_ else "") + txt + "%"


def _verbo(v):
    tipo = sinal(v)[0]
    return "ficou estável" if tipo == "igual" else ("cresceu " if tipo == "sobe" else "encolheu ") + pct(abs(v), False)


ARTIGO = dict(AC="o", AP="o", AM="o", BA="a", CE="o", DF="o", ES="o", MA="o", PA="o", PB="a", PR="o", PI="o", RJ="o",
              RN="o", RS="o", TO="o")  # sem artigo: Alagoas, Goias, Minas Gerais, Sao Paulo...


def _nome_uf(sigla, prep=""):
    """'BA' -> 'a Bahia' / 'da Bahia' (prep='de'); 'SP' -> 'São Paulo' / 'de São Paulo'."""
    nome, art = estados.UFS.get(sigla, ("", sigla))[1], ARTIGO.get(sigla, "")
    if prep:
        return f"{'d' + art if art else 'de'} {nome}"
    return f"{art} {nome}".strip()


def _ate(eco, fim):
    return f" (dados até {eco['fim']})" if eco["fim"] < fim else ""


def frase(p):
    """Frase em linguagem simples para um periodo (tambem serve ao texto de cobranca)."""
    eco = []
    if p["estado"] and p["estado"]["real"] is not None:
        eco.append(f"a economia {_nome_uf(p['uf'], 'de')} {_verbo(p['estado']['real'])}{_ate(p['estado'], p['fim'])}")
    if p["brasil"] and p["brasil"]["real"] is not None:
        eco.append(f"{'a do' if eco else 'a economia do'} Brasil {_verbo(p['brasil']['real'])}"
                   f"{_ate(p['brasil'], p['fim'])}")
    if not eco:
        return ""
    return (f"Entre as declarações de {p['ini']} e {p['fim']}, descontada a inflação, " + " e ".join(eco) + ". "
            + texto_recessao(p))


def texto_recessao(p):
    qb = p["brasil"]["quedas"] if p["brasil"] else []
    qu = p["estado"]["quedas"] if p["estado"] else []
    if not (qb or qu):
        return "Não houve ano de recessão no período."
    lados = ([f"o Brasil em {_lista(qb)}"] if qb else []) + ([f"{_nome_uf(p['uf'])} em {_lista(qu)}"] if qu else [])
    return "Houve recessão (queda real do PIB): " + "; ".join(lados) + "."


def _lista(anos):
    return ", ".join(map(str, anos[:-1])) + (" e " if len(anos) > 1 else "") + str(anos[-1])


def _chip(tipo, texto):
    return f'<span class="chip eco-{tipo}">{SETA[tipo]} {e(texto)}</span>'


def _chip_eco(lugar, eco, fim):
    tipo, rot = sinal(eco["real"])
    return _chip(tipo, f"{lugar} {rot.lower()} ({pct(eco['real'])}{', dados até ' + str(eco['fim']) if eco['fim'] < fim else ''})")


def _chips(p):
    chips = ([_chip_eco(estados.UFS[p["uf"]][1], p["estado"], p["fim"])] if p["estado"] else []) \
        + ([_chip_eco("Brasil", p["brasil"], p["fim"])] if p["brasil"] else [])
    quedas = sorted(set((p["estado"] or {}).get("quedas", [])) | set((p["brasil"] or {}).get("quedas", [])))
    if quedas:
        chips.append(_chip("cai", f"Recessão em {_lista(quedas)}"))
    return "".join(chips)


NOTA = ('<p class="mut"><small>O PIB mede a riqueza produzida, já sem a inflação, e não depende de um político: '
        "serve para lembrar como estava a vida de todo mundo enquanto o patrimônio mudava. Recessão é um ano em que a "
        "economia encolheu. No estado o número é estimado e o IBGE publica com cerca de 2 anos de atraso. Fonte: IBGE ("
        f'<a href="{LINK["brasil"]}" target="_blank" rel="noopener">Brasil</a>, '
        f'<a href="{LINK["uf"]}" target="_blank" rel="noopener">estados</a>).</small></p>')


def secao(econ, linhas):
    """Linha "Economia no período" da aba Patrimônio: selos de crescimento, declinio e recessao do estado e do Brasil
    entre as duas ultimas declaracoes com PIB publicado. `econ` None: omitida; {}: fonte fora do ar."""
    if econ is None:
        return ""
    titulo = "<h3>Economia no período</h3>"
    if not completo(econ):
        return titulo + f'<p class="vazio">{NAO_ACHOU}: IBGE fora do ar nesta execução.</p>'
    pers = [periodo(econ, a) for a in sorted(linhas, key=lambda a: (a.get("ano_ini") or 0, a.get("ano_fim") or 0))]
    com_eco = [p for p in pers if p["brasil"] or p["estado"]]
    if not com_eco:
        return titulo + f'<p class="vazio">{NAO_INFORMADO}: o IBGE ainda não publicou o PIB desse período.</p>'
    p = com_eco[-1]
    return (titulo + f'<p class="eco-linha"><span>Como ia a economia entre as declarações de {p["ini"]} e {p["fim"]}:</span> '
            f"{_chips(p)}</p>" + NOTA)
