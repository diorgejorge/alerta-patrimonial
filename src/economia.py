"""Patrimonio x economia (#55): o patrimonio declarado cresceu mais ou menos que a economia do estado e do Brasil?
Fonte oficial e gratuita: IBGE/SIDRA (apisidra.ibge.gov.br, sem chave), 3 consultas por execucao:
  6784 (Brasil): v9810 variacao real do PIB (%), v9811 deflator do PIB (%)
  5938 (UF):     v37 PIB a precos correntes (mil reais); o IBGE publica com ~2 anos de atraso
  1737 (Brasil): v2266 IPCA numero-indice, julho de cada ano (a declaracao ao TSE e entregue em agosto)
Tudo e comparado descontada a inflacao. O PIB real por UF nao esta no SIDRA: e estimado pelo PIB nominal da UF
descontado o deflator do PIB nacional (o texto da pagina avisa). Dado publico agregado, sem dado pessoal: fica em
data/economia.json e vale como reserva quando o IBGE esta fora do ar."""
import datetime as dt, html, json, math, sys
from pathlib import Path
import estados

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
ARQUIVO = ROOT / "data" / "economia.json"
SIDRA = "https://apisidra.ibge.gov.br/values"
ANO_INICIAL = 2002  # inicio da serie do PIB por UF (referencia 2010)
MES_IPCA = "07"
LINK = dict(brasil="https://sidra.ibge.gov.br/tabela/6784", uf="https://sidra.ibge.gov.br/tabela/5938",
            ipca="https://sidra.ibge.gov.br/tabela/1737")
NAO_ACHOU, NAO_INFORMADO = "Fonte não encontrada", "Não informado"
NUM = ' class="n"'  # colunas numericas (alinhadas a direita)
e = html.escape


# ---------------------------------------------------------------- coleta
def urls(hoje=None):
    hoje = hoje or dt.date.today()
    meses = ",".join(f"{a}{MES_IPCA}" for a in range(ANO_INICIAL, hoje.year + 1))
    return dict(brasil=f"{SIDRA}/t/6784/n1/all/v/9810,9811/p/all",
                uf=f"{SIDRA}/t/5938/n3/all/v/37/p/all",
                ipca=f"{SIDRA}/t/1737/n1/all/v/2266/p/{meses}")


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
    k_var, k_per = achar("Variável"), achar("Ano", "Mês")
    k_ter = achar("Brasil", "Unidade da Federação")
    if not (k_var and k_per and k_ter):
        return []
    out = []
    for r in resposta[1:]:
        valor = _numero(r.get("V"))
        if valor is not None:
            out.append(dict(territorio=str(r.get(k_ter)), variavel=str(r.get(k_var)), periodo=str(r.get(k_per)),
                            valor=valor))
    return out


def montar(brasil, uf, ipca, siglas):
    """{brasil: {volume, deflator}, uf: {sigla: {ano: pib}}, ipca: {ano: indice de julho}} com anos em texto.
    `siglas`: {codigo IBGE da UF: sigla}."""
    vol, defl = {}, {}
    for r in ler_sidra(brasil):
        {"9810": vol, "9811": defl}.get(r["variavel"], {})[r["periodo"]] = r["valor"]
    por_uf = {}
    for r in ler_sidra(uf):
        if r["variavel"] == "37" and r["territorio"] in siglas:
            por_uf.setdefault(siglas[r["territorio"]], {})[r["periodo"]] = r["valor"]
    ind = {r["periodo"][:4]: r["valor"] for r in ler_sidra(ipca)
           if r["variavel"] == "2266" and r["periodo"].endswith(MES_IPCA)}
    return dict(brasil=dict(volume=vol, deflator=defl), uf=por_uf, ipca=ind)


def completo(econ):
    return bool(econ and econ.get("brasil", {}).get("volume") and econ.get("uf") and econ.get("ipca"))


def coletar(buscar, siglas, arquivo=ARQUIVO, hoje=None):
    """Baixa as 3 tabelas e grava `arquivo`. Falhou alguma: devolve o ultimo salvo (ou {} sem nada salvo).
    `buscar(url)` devolve o JSON ou None (estados.Buscador: espaca as consultas e espera no 429)."""
    u = urls(hoje)
    econ = montar(buscar(u["brasil"]), buscar(u["uf"]), buscar(u["ipca"]), siglas)
    arquivo = Path(arquivo)
    if completo(econ):
        econ["atualizado"] = (hoje or dt.date.today()).isoformat()
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(econ, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        print(f"IBGE: PIB do Brasil até {ultimo(econ['brasil']['volume'])}, dos estados até "
              f"{max(ultimo(v) or 0 for v in econ['uf'].values())}, IPCA até {ultimo(econ['ipca'])}.")
        return econ
    print("[aviso] IBGE/SIDRA indisponível: comparação com a economia usa o último dado salvo", file=sys.stderr)
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
    ipca = {"2018": 4952.4, "2019": 5114.7, "2020": 5248.0, "2021": 5729.5, "2022": 6297.8, "2023": 6551.3}
    return dict(brasil=dict(volume=vol, deflator=defl), uf=uf, ipca=ipca, atualizado="demo")


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


def real_patrimonio(econ, ini, fim, pat_ini, pat_fim):
    """Crescimento do patrimonio descontado o IPCA (fracao: 0.5 = +50%); None sem dado."""
    ipca = (econ or {}).get("ipca") or {}
    i0, i1 = ipca.get(str(ini)), ipca.get(str(fim))
    if not (i0 and i1 and pat_ini and pat_fim is not None and pat_ini > 0):
        return None
    return (pat_fim / pat_ini) / (i1 / i0) - 1


def real_brasil(econ, ini, fim):
    f = _acumulado(econ["brasil"]["volume"], range(ini + 1, fim + 1))
    return None if f is None else f - 1


def real_uf(econ, sigla, ini, fim):
    pib = econ["uf"].get(sigla) or {}
    p0, p1 = pib.get(str(ini)), pib.get(str(fim))
    d = _acumulado(econ["brasil"]["deflator"], range(ini + 1, fim + 1))
    return (p1 / p0) / d - 1 if p0 and p1 and d else None


def quedas_brasil(econ, ini, fim):
    vol = econ["brasil"]["volume"]
    return [(a, vol[str(a)]) for a in range(ini + 1, fim + 1) if (vol.get(str(a)) or 0) < 0]


def quedas_uf(econ, sigla, ini, fim):
    return [(a, r * 100) for a in range(ini + 1, fim + 1)
            if (r := real_uf(econ, sigla, a - 1, a)) is not None and r < 0]


def comparar(econ, linha):
    """Comparacao de um periodo de declaracoes (linha do alerta). Cada economia vai ate o ultimo ano que o IBGE ja
    publicou; sem nenhum ano depois do inicio, fica None."""
    ini, fim = int(linha.get("ano_ini") or 0), int(linha.get("ano_fim") or 0)
    sigla = str(linha.get("uf") or "").upper()
    out = dict(ini=ini, fim=fim, uf=sigla if sigla in econ.get("uf", {}) else None,
               patrimonio=real_patrimonio(econ, ini, fim, linha.get("pat_ini"), linha.get("pat_fim")))
    fim_br = min(fim, ultimo(econ["brasil"]["volume"]) or 0)
    out["brasil"] = dict(fim=fim_br, real=real_brasil(econ, ini, fim_br), quedas=quedas_brasil(econ, ini, fim_br)) \
        if fim_br > ini else None
    fim_uf = min(fim, ultimo(econ["uf"].get(out["uf"])) or 0) if out["uf"] else 0
    out["estado"] = dict(fim=fim_uf, real=real_uf(econ, out["uf"], ini, fim_uf),
                         quedas=quedas_uf(econ, out["uf"], ini, fim_uf)) if fim_uf > ini else None
    return out


# ---------------------------------------------------------------- html
def pct(v, sinal=True):
    """0.056 -> '+5,6%'; 1.85 -> '+185%'; -0.033 -> '−3,3%'."""
    if v is None:
        return NAO_INFORMADO
    p = v * 100
    txt = f"{abs(p):.0f}" if abs(p) >= 100 else f"{abs(p):.1f}".replace(".", ",")
    txt = txt[:-2] if txt.endswith(",0") else txt
    return (("+" if p > 0 else "−" if p < 0 else "") if sinal else "") + txt + "%"


def _verbo(v):
    return "ficou estável" if abs(v) < 0.0005 else ("cresceu " if v > 0 else "encolheu ") + pct(abs(v), sinal=False)


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


def frase(c):
    """Frase em linguagem simples para um periodo."""
    if c["patrimonio"] is None:
        partes = [f"De {c['ini']} a {c['fim']}, não dá para descontar a inflação do patrimônio declarado."]
    else:
        partes = [f"De {c['ini']} a {c['fim']}, descontada a inflação, o patrimônio declarado {_verbo(c['patrimonio'])}."]
    eco = []
    if c["estado"] and c["estado"]["real"] is not None:
        eco.append(f"a economia {_nome_uf(c['uf'], 'de')} {_verbo(c['estado']['real'])}{_ate(c['estado'], c['fim'])}")
    if c["brasil"] and c["brasil"]["real"] is not None:
        eco.append(f"a do Brasil {_verbo(c['brasil']['real'])}{_ate(c['brasil'], c['fim'])}")
    if eco:
        partes.append("No mesmo período, " + " e ".join(eco) + ".")
    partes.append(texto_recessao(c))
    return " ".join(p for p in partes if p)


def _anos(quedas):
    return ", ".join(f"{a} ({pct(v / 100)})" for a, v in quedas)


def texto_recessao(c):
    qb = c["brasil"]["quedas"] if c["brasil"] else []
    qu = c["estado"]["quedas"] if c["estado"] else []
    if not (c["brasil"] or c["estado"]):
        return ""
    if not (qb or qu):
        return "Não houve ano de recessão no período publicado pelo IBGE."
    lados = ([f"o Brasil em {_anos(qb)}"] if qb else []) + ([f"{_nome_uf(c['uf'])} em {_anos(qu)}"] if qu else [])
    return "Houve recessão (queda real do PIB): " + "; ".join(lados) + "."


def _barras(c):
    itens = [("Patrimônio declarado", c["patrimonio"], "eco-pat")]
    if c["estado"]:
        itens.append((f"PIB {_nome_uf(c['uf'], 'de')}{_ate(c['estado'], c['fim'])}", c["estado"]["real"], "eco-uf"))
    if c["brasil"]:
        itens.append((f"PIB do Brasil{_ate(c['brasil'], c['fim'])}", c["brasil"]["real"], "eco-br"))
    vals = [v for _, v, _ in itens if v is not None]
    if len(vals) < 2:
        return ""
    neg, pos = max(0.0, -min(vals)), max(0.0, max(vals))
    escala = (neg + pos) or 1.0
    zero = neg / escala * 100
    linhas = []
    for rot, v, cls in itens:
        if v is None:
            barra = ""
        else:
            larg = abs(v) / escala * 100
            esq = zero if v >= 0 else zero - larg
            barra = (f'<span class="eco-barra {cls}{" eco-neg" if v < 0 else ""}" '
                     f'style="left:{esq:.1f}%;width:{max(larg, 0.6):.1f}%"></span>')
        linhas.append(f'<li><span class="eco-rot">{e(rot)}</span><span class="eco-trilho">'
                      f'<span class="eco-zero" style="left:{zero:.1f}%"></span>{barra}</span>'
                      f'<b class="eco-val">{e(pct(v))}</b></li>')
    return (f'<ul class="eco-barras" aria-label="Crescimento de {c["ini"]} a {c["fim"]}, descontada a inflação">'
            + "".join(linhas) + "</ul>")


def _celula(eco, fim, chave="real"):
    if not eco:
        return NAO_INFORMADO
    return e(pct(eco[chave])) + (f" <small>(até {eco['fim']})</small>" if eco["fim"] < fim else "")


def _tabela(comps):
    cab = ["Período", "Patrimônio", "PIB do estado", "PIB do Brasil", "Anos de recessão"]
    corpo = []
    for c in comps:
        rec = sorted({a for a, _ in (c["brasil"] or {}).get("quedas", [])}
                     | {a for a, _ in (c["estado"] or {}).get("quedas", [])})
        cel = [f"{c['ini']}–{c['fim']}", e(pct(c["patrimonio"])), _celula(c["estado"], c["fim"]),
               _celula(c["brasil"], c["fim"]),
               ", ".join(map(str, rec)) or ("Nenhum" if c["brasil"] or c["estado"] else NAO_INFORMADO)]
        corpo.append("<tr>" + "".join(f'<td data-label="{e(h)}"{NUM if 1 <= i <= 3 else ""}>{v}</td>'
                                      for i, (h, v) in enumerate(zip(cab, cel))) + "</tr>")
    return ('<div class="tab"><table class="resp"><caption class="sr">Patrimônio e economia por período, descontada '
            "a inflação</caption><thead><tr>" + "".join(
                f'<th scope="col"{NUM if 1 <= i <= 3 else ""}>{e(h)}</th>' for i, h in enumerate(cab))
            + "</tr></thead><tbody>" + "".join(corpo) + "</tbody></table></div>")


NOTA = ('<p class="mut"><small>Tudo descontada a inflação pelo IPCA de julho a julho (a declaração ao TSE é entregue '
        'em agosto). PIB do Brasil: crescimento real calculado pelo IBGE. PIB do estado: estimativa, com o PIB do estado '
        'descontado o deflator do PIB do Brasil; o IBGE publica o PIB dos estados com cerca de 2 anos de atraso. '
        "Patrimônio é de uma pessoa e o PIB é da economia inteira: a comparação é só uma referência para fazer "
        "perguntas, não prova de nada. Fontes: IBGE, "
        f'<a href="{LINK["brasil"]}" target="_blank" rel="noopener">PIB do Brasil</a>, '
        f'<a href="{LINK["uf"]}" target="_blank" rel="noopener">PIB dos estados</a> e '
        f'<a href="{LINK["ipca"]}" target="_blank" rel="noopener">IPCA</a>.</small></p>')


def secao(econ, linhas):
    """Bloco "Patrimônio × economia" da aba Patrimônio. `econ` None: secao omitida; {}: fonte fora do ar."""
    if econ is None:
        return ""
    titulo = "<h3>Patrimônio × economia</h3>"
    if not completo(econ):
        return titulo + f'<p class="vazio">{NAO_ACHOU}: IBGE fora do ar nesta execução.</p>'
    comps = [comparar(econ, a) for a in sorted(linhas, key=lambda a: (a.get("ano_ini") or 0, a.get("ano_fim") or 0))]
    comps = [c for c in comps if c["fim"] > c["ini"]]
    com_eco = [c for c in comps if c["brasil"] or c["estado"]]
    if not com_eco:
        return titulo + (f'<p class="vazio">{NAO_INFORMADO}: o IBGE ainda não publicou o PIB desse período.</p>'
                         + NOTA)
    principal = com_eco[-1]
    return (titulo + f'<p class="eco-frase">{e(frase(principal))}</p>' + _barras(principal)
            + (_tabela(comps) if len(comps) > 1 else "") + NOTA)
