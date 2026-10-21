"""Dinheiro publico ligado a cada pessoa, consultado nas paginas do Portal da Transparencia
(portaldatransparencia.gov.br, as mesmas consultas que o site faz ao montar as tabelas; sem API/chave).
- Emendas parlamentares de que a pessoa e autora e quem recebeu os pagamentos.
- Beneficios sociais pagos ao CPF da pessoa (BPC, Bolsa Familia, Auxilio Emergencial, Seguro-Defeso, PETI,
  Auxilio Reconstrucao). So como beneficiaria: dados de representados/dependentes nunca sao buscados.
- Recursos federais recebidos pelo CPF da pessoa e pelo CNPJ das empresas declaradas ao TSE.
CPF/CNPJ so vao na consulta ao Portal; nunca aparecem na pagina."""
import datetime as dt
import html, json, re, sys, time, unicodedata, urllib.parse, urllib.request

SITE = "https://portaldatransparencia.gov.br"
UA = "Mozilla/5.0 (compatible; alerta-patrimonial/1.0; +https://github.com)"
HDR = {"User-Agent": UA, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
CARGOS_EMENDA = ("DEPUTADO FEDERAL", "SENADOR", "SUPLENTE")  # autores de emendas
INTERMEDIARIOS = ("BANCO DO BRASIL", "CAIXA ECONOMICA")  # repassam fundo a fundo: nao sao o destino final
MAX_EMENDAS, MAX_DOCS_EMENDAS, MAX_FAV = 5, 3, 6
e = html.escape


def ascii_(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()


def chave(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_(s).lower()).split())


def valor(s):
    """'1.234,56' -> 1234.56"""
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def cnpj_ok(c):
    c = re.sub(r"\D", "", c or "")
    if len(c) != 14 or len(set(c)) == 1:
        return False
    for n in (12, 13):
        pesos = list(range(n - 7, 1, -1)) + list(range(9, 1, -1))
        d = sum(int(a) * b for a, b in zip(c[:n], pesos)) % 11
        if int(c[n]) != (0 if d < 2 else 11 - d):
            return False
    return True


class Portal:
    """Requisicoes ao site com pausa entre chamadas, prazo total e parada apos falhas seguidas."""

    def __init__(self, pausa, fim, timeout=30):
        self.pausa, self.fim, self.timeout = pausa, fim, timeout
        self.ultimo, self.req, self.falhas, self.seguidas = 0.0, 0, 0, 0

    def ativo(self):
        return self.seguidas < 5 and time.monotonic() < self.fim

    def get(self, caminho, **params):
        """JSON de {SITE}{caminho}/resultado?...; None se falhar."""
        if not self.ativo():
            return None
        espera = self.pausa - (time.monotonic() - self.ultimo)
        if espera > 0:
            time.sleep(espera)
        self.ultimo = time.monotonic()
        self.req += 1
        base = dict(paginacaoSimples="true", tamanhoPagina=100, offset=0)
        url = f"{SITE}{caminho}/resultado?" + urllib.parse.urlencode({**base, **params})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=self.timeout) as r:
                dados = json.loads(r.read(10_000_000).decode("utf-8", "replace"))
            self.seguidas = 0
            return dados.get("data") or []
        except Exception as ex:
            self.falhas += 1
            self.seguidas += 1
            print(f"[aviso] Portal da Transparencia falhou em {caminho} ({ex})", file=sys.stderr)
            return None


# ---------------------------------------------------------------- consultas
def emendas(portal, nomes):
    """Emendas de autoria da pessoa (nome de urna = nome parlamentar no Portal)."""
    codigos = set()
    for nome in nomes:
        if not nome:
            continue
        for d in portal.get("/emendas/consulta", palavraChave=nome, colunasSelecionadas="autor",
                            direcaoOrdenacao="asc", colunaOrdenacao="autor") or []:
            m = re.match(r"\s*(\d+)\s*-\s*(.+)", d.get("autor") or "")
            if m and chave(m.group(2)) == chave(nome):
                codigos.add(m.group(1))
        if codigos:
            break
    lista = []
    for cod in sorted(codigos):
        lista += portal.get("/emendas/consulta", autorEmenda=cod, direcaoOrdenacao="desc", colunaOrdenacao="valorPago",
                            colunasSelecionadas="codigoEmenda,ano,autor,localidadeDoGasto,funcao,subfuncao,"
                                                "valorEmpenhado,valorPago") or []
    if not lista:
        return None
    por_ano = {}
    for d in lista:
        a = por_ano.setdefault(d.get("ano"), [0.0, 0.0, 0])
        a[0] += valor(d.get("valorEmpenhado")); a[1] += valor(d.get("valorPago")); a[2] += 1
    top = sorted(lista, key=lambda d: valor(d.get("valorPago")), reverse=True)[:MAX_EMENDAS]
    favs = {}
    for d in top[:MAX_DOCS_EMENDAS]:
        docs = portal.get("/emendas/documentos-relacionados", codigo=d.get("codigoEmenda"), ano=d.get("ano"),
                          codigoFuncao=d.get("codigoFuncao") or "", codigoSubfuncao=d.get("codigoSubfuncao") or "",
                          localidadeDoGasto=d.get("localidadeDoGasto") or "", skTipoEmenda=d.get("skTipoEmenda") or "",
                          palavraChave="", direcaoOrdenacao="desc", colunaOrdenacao="valor",
                          colunasSelecionadas="data,fase,codigoDocumentoResumido,favorecido,valor") or []
        for x in docs:
            if (x.get("fase") or "").lower() != "pagamento":
                continue
            nome = re.sub(r"^[\d./-]+\s*-\s*", "", x.get("favorecido") or "").strip() or "—"
            favs[nome] = favs.get(nome, 0.0) + valor(x.get("valor"))
    return dict(autores=sorted(codigos), anos=sorted(por_ano.items(), key=lambda kv: kv[0] or 0, reverse=True),
                top=top, favorecidos=sorted(favs.items(), key=lambda kv: kv[1], reverse=True)[:MAX_FAV],
                total_pago=sum(a[1] for a in por_ano.values()), n=len(lista))


BENEFICIOS = [  # (nome, caminho, filtro do CPF, coluna de valor, janelas anuais ou None = sem periodo)
    ("BPC (Benefício de Prestação Continuada)", "/beneficios/bpc", "beneficiario", "valorTotalPeriodo", None),
    ("PETI", "/beneficios/peti", "beneficiario", "valorTotalParcela", None),
    ("Auxílio Reconstrução", "/beneficios/auxilio-reconstrucao", "cpfNisBeneficiario", "valorParcela", None),
    ("Bolsa Família (até 2021)", "/beneficios/bolsa-familia", "cpfNisBeneficiario", "valorTotalPeriodo", (2019, 2021)),
    ("Auxílio Emergencial", "/beneficios/auxilio-emergencial", "cpfNisBeneficiario", "valorTotalPeriodo", (2020, 2021)),
    ("Seguro-Defeso", "/beneficios/seguro-defeso", "cpfNisBeneficiario", "valor", (2019, None)),
]


def beneficios(portal, cpf):
    out = []
    hoje = dt.date.today()
    for nome, caminho, filtro, col, anos in BENEFICIOS:
        janelas = [None] if anos is None else range(anos[0], (anos[1] or hoje.year) + 1)
        meses, total, erro = set(), 0.0, False
        for a in janelas:
            per = {} if a is None else dict(de=f"01/01/{a}", ate=f"31/12/{a}" if a < hoje.year else hoje.strftime("%d/%m/%Y"))
            dados = portal.get(caminho, **{filtro: cpf}, **per, direcaoOrdenacao="desc", colunaOrdenacao="mesReferencia",
                               colunasSelecionadas=f"mesReferencia,uf,municipio,cpf,beneficiario,{col}")
            if dados is None:
                erro = True
                continue
            for d in dados:
                meses.add(d.get("mesReferencia") or "")
                total += valor(d.get(col))
        if meses or erro:
            out.append(dict(nome=nome, meses=sorted(m for m in meses if m), total=total, erro=erro and not meses))
    return out


def recursos(portal, codigo):
    """Recursos federais recebidos por um CPF/CNPJ (Despesas > Recursos recebidos), por orgao."""
    dados = portal.get("/despesas/recursos-recebidos", cpfCnpj=codigo, de="01/01/2019",
                       ate=dt.date.today().strftime("%d/%m/%Y"), direcaoOrdenacao="desc", colunaOrdenacao="valorRecebido",
                       colunasSelecionadas="mesAno,favorecido,tipoFavorecido,ufFavorecido,orgaoSuperior,valorRecebido")
    if dados is None:
        return None
    por = {}
    for d in dados:
        org = re.sub(r"^\d+\s*-\s*", "", d.get("orgaoSuperior") or "—")
        por[org] = por.get(org, 0.0) + valor(d.get("valorRecebido"))
    return sorted(por.items(), key=lambda kv: kv[1], reverse=True)


def coletar(pessoas, pausa=0.6, tempo_max=30 * 60):
    """pessoas: {chave: dict(nome, nome_urna, cargo, cpf, empresas=[(nome, cnpj)])} na ordem do painel.
    Devolve {chave: dados}; quem fica de fora do prazo recebe {"pendente": True}."""
    portal = Portal(pausa, time.monotonic() + tempo_max)
    out = {}
    for k, p in pessoas.items():
        if not portal.ativo():
            out[k] = {"pendente": True}
            continue
        r = {}
        if any(c in (p.get("cargo") or "").upper() for c in CARGOS_EMENDA):
            r["emendas"] = emendas(portal, [p.get("nome_urna"), p.get("nome")])
        cpf = re.sub(r"\D", "", p.get("cpf") or "")
        if len(cpf) == 11:
            r["beneficios"] = beneficios(portal, cpf)
            r["recursos_pf"] = recursos(portal, cpf)
        r["empresas"] = [(nome, recursos(portal, cnpj)) for nome, cnpj in (p.get("empresas") or []) if cnpj_ok(cnpj)][:3]
        r["sem_cpf"] = len(cpf) != 11
        out[k] = r
    print(f"Portal da Transparencia: {len(out)} pessoas, {portal.req} consultas, {portal.falhas} falhas.")
    return out


# ---------------------------------------------------------------- html (secao do dossie)
def _link(caminho, **params):
    return e(f"{SITE}{caminho}?" + urllib.parse.urlencode(params))


def secao(r, nome):
    """HTML da secao 'Dinheiro público' do dossie."""
    if r is None:
        return '<p class="vazio">Consulta ao Portal da Transparência não realizada nesta execução.</p>'
    if r.get("pendente"):
        return '<p class="vazio">Consulta ao Portal da Transparência não realizada nesta execução (limite de tempo).</p>'
    partes = []
    em = r.get("emendas", "nao-aplica")
    if em != "nao-aplica":
        partes.append("<h3>Emendas parlamentares de autoria</h3>")
        if not em:
            partes.append(f'<p class="vazio">Nenhuma emenda encontrada com o autor “{e(nome)}”.</p>')
        else:
            link = _link("/emendas/consulta", autorEmenda=",".join(em["autores"]), ordenarPor="valorPago", direcao="desc")
            partes.append(f'<p>{em["n"]} emendas, {brl(em["total_pago"])} pagos no total. '
                          f'<a href="{link}" target="_blank" rel="noopener">Ver todas no Portal</a></p>')
            partes.append('<div class="tab"><table><thead><tr><th>Ano</th><th class="n">Emendas</th>'
                          '<th class="n">Empenhado</th><th class="n">Pago</th></tr></thead><tbody>'
                          + "".join(f'<tr><td>{e(str(a))}</td><td class="n">{v[2]}</td><td class="n">{brl(v[0])}</td>'
                                    f'<td class="n">{brl(v[1])}</td></tr>' for a, v in em["anos"]) + "</tbody></table></div>")
            partes.append("<p><b>Maiores emendas</b></p><ul class=\"nt\">" + "".join(
                f'<li><a href="{_link("/emendas/detalhe", codigoEmenda=d.get("codigoEmenda"), codigoTipoEmenda=d.get("skTipoEmenda") or 1)}"'
                f' target="_blank" rel="noopener">{e(str(d.get("ano")))} · {e(d.get("funcao") or "—")} / {e(d.get("subfuncao") or "—")}</a>'
                f'<br><small>{e(d.get("localidadeDoGasto") or "—")} · pago {brl(valor(d.get("valorPago")))}</small></li>'
                for d in em["top"]) + "</ul>")
            if em["favorecidos"]:
                partes.append(f"<p><b>Quem recebeu os pagamentos</b> (das {min(len(em['top']), MAX_DOCS_EMENDAS)} maiores emendas)</p>"
                              '<ul class="nt">' + "".join(
                                  f'<li>{e(n)}<br><small>{brl(v)}'
                                  f'{" · banco que repassa a estados e municípios, não é o destino final" if any(i in chave(n).upper() for i in INTERMEDIARIOS) else ""}'
                                  f"</small></li>" for n, v in em["favorecidos"]) + "</ul>")
    if r.get("sem_cpf"):
        partes.append('<p class="vazio">O TSE não informa o CPF desta candidatura, então benefícios sociais e '
                      'recursos recebidos pela pessoa não foram consultados.</p>')
    else:
        partes.append("<h3>Benefícios sociais pagos ao CPF da pessoa</h3>")
        bs = r.get("beneficios") or []
        if not bs:
            partes.append('<p class="vazio">Nenhum benefício social encontrado (BPC, Bolsa Família, Auxílio Emergencial, '
                          'Seguro-Defeso, PETI, Auxílio Reconstrução).</p>')
        else:
            partes.append('<ul class="nt">' + "".join(
                f'<li><b>{e(b["nome"])}</b><br><small>'
                + ("não foi possível consultar agora" if b["erro"] else
                   f'{len(b["meses"])} mês(es) ({e(b["meses"][0])} a {e(b["meses"][-1])}) · {brl(b["total"])}')
                + "</small></li>" for b in bs) + "</ul>")
        rp = r.get("recursos_pf")
        partes.append("<h3>Recursos federais recebidos pelo CPF</h3>")
        partes.append('<p class="vazio">Não foi possível consultar agora.</p>' if rp is None else
                      '<p class="vazio">Nada encontrado desde 2019.</p>' if not rp else
                      '<ul class="nt">' + "".join(f"<li>{e(o)}<br><small>{brl(v)}</small></li>" for o, v in rp[:MAX_FAV]) + "</ul>")
    emp = r.get("empresas") or []
    if emp:
        partes.append("<h3>Recursos federais recebidos pelas empresas declaradas</h3>")
        for nome_emp, rec in emp:
            partes.append(f"<p><b>{e(nome_emp)}</b></p>" + (
                '<p class="vazio">Não foi possível consultar agora.</p>' if rec is None else
                '<p class="vazio">Nada encontrado desde 2019.</p>' if not rec else
                '<ul class="nt">' + "".join(f"<li>{e(o)}<br><small>{brl(v)}</small></li>" for o, v in rec[:MAX_FAV]) + "</ul>"))
    return "".join(partes) or '<p class="vazio">Nada a consultar para esta pessoa.</p>'
