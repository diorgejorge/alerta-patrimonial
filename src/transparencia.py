"""Dinheiro publico ligado a cada pessoa, no Portal da Transparencia (portaldatransparencia.gov.br).
Todas as consultas usam so a API oficial (api.portaldatransparencia.gov.br, chave em TRANSPARENCIA_TOKEN);
o site aparece apenas como link para leitura humana.
- Emendas parlamentares de que a pessoa e autora e quem recebeu os pagamentos.
- Beneficios pagos ao CPF da pessoa (Bolsa Familia, Auxilio Emergencial/Brasil, Garantia-Safra, Seguro-Defeso,
  Auxilio Reconstrucao). BPC e PETI ficam de fora (dado sensivel / criancas, LGPD arts. 11 e 14). So como titular: registros de representados/dependentes sao descartados.
- Sancoes (CEIS, CNEP, CEAF, CEPIM) da pessoa e das empresas.
- Recursos federais recebidos pelo CPF da pessoa e pelo CNPJ das empresas declaradas ao TSE.
CPF/CNPJ so vao na consulta ao Portal; nunca aparecem na pagina."""
import datetime as dt
import html, json, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request


SITE = "https://portaldatransparencia.gov.br"
UA = "Mozilla/5.0 (compatible; alerta-patrimonial/1.0; +https://github.com)"
CARGOS_EMENDA = ("DEPUTADO FEDERAL", "SENADOR", "SUPLENTE")  # autores de emendas
INTERMEDIARIOS = ("BANCO DO BRASIL", "CAIXA ECONOMICA")  # repassam fundo a fundo: nao sao o destino final
MAX_EMENDAS, MAX_DOCS_EMENDAS, MAX_FAV = 5, 2, 6
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


# ---------------------------------------------------------------- API oficial
API = "https://api.portaldatransparencia.gov.br/api-de-dados"


class Api:
    """API de dados do Portal (chave gratuita em portaldatransparencia.gov.br/api-de-dados/cadastrar-email).
    Limite do Portal: 90 consultas/min das 06h as 24h e 300/min da 0h as 6h (Brasilia)."""

    def __init__(self, chave_api, fim, timeout=30):
        self.chave, self.fim, self.timeout = chave_api, fim, timeout
        self.ultimo, self.req, self.falhas, self.seguidas = 0.0, 0, 0, 0

    def ativa(self):
        return bool(self.chave) and self.seguidas < 5 and time.monotonic() < self.fim

    def pausa(self):
        h = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).hour
        return 0.25 if h < 6 else 0.75  # com folga abaixo do limite de cada faixa

    def get(self, caminho, _de_novo=False, **params):
        """JSON de {API}{caminho}; None se falhar."""
        if not self.ativa():
            return None
        espera = self.pausa() - (time.monotonic() - self.ultimo)
        if espera > 0:
            time.sleep(espera)
        self.ultimo = time.monotonic()
        self.req += 1
        req = urllib.request.Request(f"{API}{caminho}?" + urllib.parse.urlencode(params),
                                     headers={"chave-api-dados": self.chave, "Accept": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                dados = json.loads(r.read(20_000_000).decode("utf-8", "replace") or "null")
            self.seguidas = 0
            return dados
        except urllib.error.HTTPError as ex:
            if ex.code == 429 and not _de_novo:  # passou do limite: espera um minuto e tenta uma vez
                time.sleep(60)
                return self.get(caminho, _de_novo=True, **params)
            self._falha(caminho, ex, conta=ex.code >= 500)  # 4xx: so esta consulta foi recusada, a API segue no ar
        except Exception as ex:
            self._falha(caminho, ex)
        return None

    def _falha(self, caminho, ex, conta=True):
        self.falhas += 1
        if conta:
            self.seguidas += 1
        print(f"[aviso] API do Portal da Transparencia falhou em {caminho} ({ex})", file=sys.stderr)

    def paginas(self, caminho, max_paginas=20, ao_ler=None, **params):
        """Junta as paginas (a API devolve listas; pagina vazia = fim). None se a primeira falhar.
        ao_ler(pagina, itens_ate_agora): opcional, para mostrar andamento."""
        out = []
        for pg in range(1, max_paginas + 1):
            d = self.get(caminho, pagina=pg, **params)
            if d is None:
                return out or None
            if not isinstance(d, list) or not d:
                break
            out += d
            if ao_ler:
                ao_ler(pg, len(out))
        return out

# flag de /pessoa-fisica -> (nome, caminho, parametro do CPF)
# LGPD art. 5o, II e art. 11: BPC (pode revelar deficiencia = dado de saude) e PETI (envolve criancas, art. 14)
# ficam de fora: dado sensivel nao pode ser tratado por legitimo interesse. Nem sao consultados.
BENEFICIOS = [
    ("favorecidoBolsaFamilia", "Bolsa Família", "/bolsa-familia-sacado-por-cpf-ou-nis", "codigo"),
    ("favorecidoNovoBolsaFamilia", "Novo Bolsa Família", "/novo-bolsa-familia-sacado-por-cpf-ou-nis", "codigo"),
    ("auxilioEmergencial", "Auxílio Emergencial", "/auxilio-emergencial-por-cpf-ou-nis", "codigoBeneficiario"),
    ("favorecidoAuxilioBrasil", "Auxílio Brasil", "/auxilio-brasil-sacado-por-cpf-ou-nis", "codigo"),
    ("favorecidoSafra", "Garantia-Safra", "/safra-codigo-por-cpf-ou-nis", "codigo"),
    ("favorecidoSeguroDefeso", "Seguro-Defeso", "/seguro-defeso-codigo", "codigo"),
    ("favorecidoAuxilioReconstrucao", "Auxílio Reconstrução", None, None),
]
SANCOES_PF = [("sancionadoCEIS", "CEIS (empresas/pessoas inidôneas e suspensas)"),
              ("sancionadoCNEP", "CNEP (empresas punidas)"), ("sancionadoCEAF", "CEAF (expulsões da administração federal)")]
SANCOES_PJ = SANCOES_PF + [("sancionadoCEPIM", "CEPIM (entidades sem fins lucrativos impedidas)")]
TITULARES = ("beneficiario", "beneficiarioBolsaFamilia", "beneficiarioNovoBolsaFamilia", "titularBolsaFamilia",
             "beneficiarioSafra", "beneficiarioPeti", "pessoaSeguroDefeso")


def _num(v):
    """Numero da API: pode vir como numero, '1234.56' ou '1.234,56'."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").strip()
    if "," in s:
        return valor(s)
    try:
        return float(s)
    except ValueError:
        return 0.0


def _mes(d):
    """Mes de referencia (AAAA-MM) de um registro de beneficio, nos varios formatos da API."""
    for k in ("dataMesReferencia", "mesDisponibilizacao", "dataMesCompetencia", "dataSaque"):
        s = str(d.get(k) or "")
        m = re.search(r"(\d{4})-(\d{2})", s) or re.search(r"(\d{2})/(\d{4})", s)
        if m:
            a, b = m.groups()
            return f"{a}-{b}" if len(a) == 4 else f"{b}-{a}"
        m = re.fullmatch(r"(\d{4})(\d{2})", s)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    return ""


def _titular(d, nome):
    """True se o registro e da propria pessoa (descarta casos em que ela so aparece como representante)."""
    for k in TITULARES:
        t = d.get(k)
        if isinstance(t, dict) and t.get("nome"):
            return chave(t["nome"]) == chave(nome)
    return True


def pessoa_fisica(api, cpf, nome):
    pf = api.get("/pessoa-fisica", cpf=cpf)
    if isinstance(pf, list):
        pf = pf[0] if pf else {}
    if pf is None:
        return None
    bens = []
    for flag, rotulo, caminho, param in BENEFICIOS:
        if not pf.get(flag):
            continue
        if caminho is None:
            bens.append(dict(nome=rotulo, meses=[], total=None, erro=False))
            continue
        dados = api.paginas(caminho, **{param: cpf})
        if dados is None:
            bens.append(dict(nome=rotulo, meses=[], total=None, erro=True))
            continue
        proprios = [d for d in dados if _titular(d, nome)]
        if not proprios and dados:
            continue  # so aparece como representante legal de outra pessoa: nao exibimos
        meses = sorted({m for m in map(_mes, proprios) if m})
        total = sum(_num(d.get("valor") if d.get("valor") is not None else d.get("valorSaque")) for d in proprios)
        bens.append(dict(nome=rotulo, meses=meses, total=total, erro=False))
    sancoes = [rot for f, rot in SANCOES_PF if pf.get(f)]
    return dict(beneficios=bens, sancoes=sancoes, despesas=bool(pf.get("favorecidoDespesas")),
                servidor=bool(pf.get("servidor")))


def recursos(api, codigo):
    """Recursos federais recebidos por um CPF/CNPJ desde 2019, por orgao (Despesas > Recursos recebidos)."""
    hoje = dt.date.today()
    dados, falhou = [], 0
    for ano in range(2019, hoje.year + 1):  # a API recusa (HTTP 400) periodos maiores que um ano
        fim = hoje.strftime("%m/%Y") if ano == hoje.year else f"12/{ano}"
        parte = api.paginas("/despesas/recursos-recebidos", max_paginas=10, mesAnoInicio=f"01/{ano}",
                            mesAnoFim=fim, codigoFavorecido=codigo)
        if parte is None:
            falhou += 1
        else:
            dados += parte
    if falhou and not dados:
        return None
    por = {}
    for d in dados:
        org = d.get("nomeOrgaoSuperior") or d.get("nomeOrgao") or "Não informado"
        por[org] = por.get(org, 0.0) + _num(d.get("valor"))
    return sorted(por.items(), key=lambda kv: kv[1], reverse=True)


def pessoa_juridica(api, cnpj):
    pj = api.get("/pessoa-juridica", cnpj=cnpj)
    if isinstance(pj, list):
        pj = pj[0] if pj else {}
    if pj is None:
        return None
    rec = recursos(api, cnpj) if pj.get("favorecidoDespesas") else []
    return dict(sancoes=[rot for f, rot in SANCOES_PJ if pj.get(f)], recursos=rec,
                contratos=bool(pj.get("possuiContratacao")), convenios=bool(pj.get("convenios")))


def _favorecido(doc):
    """Nome do favorecido num documento de despesa da API (os formatos variam entre endpoints)."""
    f = doc.get("favorecido")
    if isinstance(f, dict):
        f = f.get("nome") or f.get("razaoSocialReceita") or f.get("nomeFantasiaReceita")
    nome = doc.get("nomeFavorecido") or f or ""
    return re.sub(r"^[\d*./-]+\s*-\s*", "", str(nome)).strip()  # tira CPF/CNPJ do inicio (inclusive mascarado)


def emendas(api, nomes):
    """Emendas de autoria da pessoa (nome de urna = nome parlamentar no Portal) e quem recebeu os pagamentos."""
    lista = []
    for nome in nomes:
        if not nome:
            continue
        dados = api.paginas("/emendas", max_paginas=40, nomeAutor=nome)
        if dados is None:
            return None
        lista = [d for d in dados if chave(d.get("nomeAutor") or d.get("autor")) == chave(nome)]
        if lista:
            break
    if not lista:
        return {}
    por_ano = {}
    for d in lista:
        a = por_ano.setdefault(d.get("ano"), [0.0, 0.0, 0])
        a[0] += _num(d.get("valorEmpenhado")); a[1] += _num(d.get("valorPago")); a[2] += 1
    top = sorted(lista, key=lambda d: _num(d.get("valorPago")), reverse=True)[:MAX_EMENDAS]
    favs = {}
    for d in top[:MAX_DOCS_EMENDAS]:
        docs = api.paginas(f"/emendas/documentos/{urllib.parse.quote(str(d.get('codigoEmenda') or ''))}", max_paginas=2) or []
        pagos = [x for x in docs if "pagamento" in chave(x.get("fase")) and x.get("codigoDocumento")][:2]  # 2 pagamentos por emenda: poupa consultas
        for x in pagos:
            doc = api.get(f"/despesas/documentos/{urllib.parse.quote(str(x['codigoDocumento']))}")
            if isinstance(doc, list):
                doc = doc[0] if doc else None
            if not isinstance(doc, dict):
                continue
            nome = _favorecido(doc) or "Não informado"
            favs[nome] = favs.get(nome, 0.0) + _num(doc.get("valor") if doc.get("valor") is not None else doc.get("valorDocumento"))
    return dict(nome_autor=lista[0].get("nomeAutor") or "", anos=sorted(por_ano.items(), key=lambda kv: kv[0] or 0, reverse=True),
                top=top, favorecidos=sorted(favs.items(), key=lambda kv: kv[1], reverse=True)[:MAX_FAV],
                total_pago=sum(a[1] for a in por_ano.values()), n=len(lista))


def _pessoa(api, p):
    """Tudo o que o Portal tem sobre uma pessoa; cada parte que falha fica None (= indisponivel)."""
    r = {"api": True}
    if any(c in (p.get("cargo") or "").upper() for c in CARGOS_EMENDA):
        r["emendas"] = emendas(api, [p.get("nome_urna"), p.get("nome")])
    cpf = re.sub(r"\D", "", p.get("cpf") or "")
    r["sem_cpf"] = len(cpf) != 11
    if not r["sem_cpf"]:
        r["pf"] = pessoa_fisica(api, cpf, p.get("nome"))
        if r["pf"] and r["pf"]["despesas"]:
            r["recursos_pf"] = recursos(api, cpf)
        elif r["pf"]:
            r["recursos_pf"] = []
    r["empresas"] = [(nome, pessoa_juridica(api, cnpj))
                     for nome, cnpj in (p.get("empresas") or []) if cnpj_ok(cnpj)][:3]
    return r


def coletar(pessoas, tempo_max=45 * 60, chave_api=None, cache=None):
    """pessoas: {chave: dict(nome, nome_urna, cargo, cpf, empresas=[(nome, cnpj)])} na ordem do painel.
    Tudo pela API oficial (precisa de `chave_api`); sem chave nada e consultado.
    Devolve {chave: dados}; quem fica de fora do prazo recebe {"pendente": "tempo"}.
    `cache` (cache.Cache cifrado): pessoa consultada sem falhas nos ultimos dias nao e consultada de novo."""
    if not chave_api:
        print("Portal da Transparencia: sem TRANSPARENCIA_TOKEN, nada consultado.")
        return {k: {"api": False} for k in pessoas}
    api = Api(chave_api, time.monotonic() + tempo_max)
    out = {}
    print(f"Portal da Transparencia: consultando {len(pessoas)} pessoas pela API...")
    if api.pausa() > 0.5:
        print("[aviso] Portal da Transparencia: fora da faixa 0h-6h (Brasilia) a API aceita menos consultas por "
              "minuto; esta etapa leva cerca de 3x mais que na execucao agendada da madrugada.")
    for n, (k, p) in enumerate(pessoas.items(), 1):
        if n % 20 == 0:
            print(f"  {n}/{len(pessoas)} pessoas, {api.req} consultas, {api.falhas} falhas")
        guardado = cache.get(p.get("chave") or k) if cache else None
        if guardado is not None:  # incremental: so consulta quem e novo ou venceu no cache
            out[k] = guardado
            continue
        if not api.ativa():
            out[k] = {"pendente": "tempo" if time.monotonic() >= api.fim else "falha"}
            continue
        try:
            antes = api.falhas
            out[k] = _pessoa(api, p)
            if cache and api.falhas == antes:  # so respostas completas entram no cache
                cache.set(p.get("chave") or k, out[k])
        except Exception as ex:  # dado inesperado da API: so esta pessoa fica "indisponivel"
            print(f"[aviso] Portal da Transparencia: erro ao montar {p.get('nome')} ({ex!r})", file=sys.stderr)
            out[k] = {"pendente": "falha"}
    if cache:
        cache.salvar()
    print(f"Portal da Transparencia (API): {len(out)} pessoas, {api.req} consultas, {api.falhas} falhas.")
    return out


# ---------------------------------------------------------------- html (secao do dossie)
def _link(caminho, **params):
    return e(f"{SITE}{caminho}?" + urllib.parse.urlencode(params))


def secao(r, nome):
    """HTML da secao 'Dinheiro público' do dossie."""
    if r is None:
        return NAO_DEU
    if not r.get("api") and not r.get("pendente"):
        return ('<p class="vazio">Não consultado: falta configurar a chave da API do Portal da Transparência '
                '(TRANSPARENCIA_TOKEN).</p>')
    if r.get("pendente") == "tempo":
        return '<p class="vazio"><b>Não informado</b>: consulta ao Portal da Transparência não realizada nesta execução (limite de tempo).</p>'
    if r.get("pendente"):
        return NAO_DEU
    partes = []
    em = r.get("emendas", "nao-aplica")
    if em != "nao-aplica":
        partes.append("<h3>Emendas parlamentares de autoria</h3>")
        if em is None:
            partes.append(NAO_DEU)
        elif not em:
            partes.append(f'<p class="vazio">Nenhuma emenda encontrada com o autor “{e(nome)}”.</p>')
        else:
            link = _link("/emendas/consulta", palavraChave=em["nome_autor"] or nome, ordenarPor="valorPago", direcao="desc")
            partes.append(f'<p>{em["n"]} emendas, {brl(em["total_pago"])} pagos no total. '
                          f'<a href="{link}" target="_blank" rel="noopener">Ver todas no Portal</a></p>')
            partes.append('<div class="tab"><table><thead><tr><th>Ano</th><th class="n">Emendas</th>'
                          '<th class="n">Empenhado</th><th class="n">Pago</th></tr></thead><tbody>'
                          + "".join(f'<tr><td>{e(str(a))}</td><td class="n">{v[2]}</td><td class="n">{brl(v[0])}</td>'
                                    f'<td class="n">{brl(v[1])}</td></tr>' for a, v in em["anos"]) + "</tbody></table></div>")
            partes.append("<p><b>Maiores emendas</b></p><ul class=\"nt\">" + "".join(
                f'<li><a href="{_link("/emendas/consulta", codigoEmenda=d.get("codigoEmenda") or "")}"'
                f' target="_blank" rel="noopener">{e(str(d.get("ano")))} · {e(d.get("funcao") or "Não informado")} / {e(d.get("subfuncao") or "Não informado")}</a>'
                f'<br><small>{e(d.get("localidadeDoGasto") or "Não informado")} · pago {brl(_num(d.get("valorPago")))}</small></li>'
                for d in em["top"]) + "</ul>")
            if em["favorecidos"]:
                partes.append(f"<p><b>Quem recebeu os pagamentos</b> (das {min(len(em['top']), MAX_DOCS_EMENDAS)} maiores emendas)</p>"
                              '<ul class="nt">' + "".join(
                                  f'<li>{e(n)}<br><small>{brl(v)}'
                                  f'{" · banco que repassa a estados e municípios, não é o destino final" if any(i in chave(n).upper() for i in INTERMEDIARIOS) else ""}'
                                  f"</small></li>" for n, v in em["favorecidos"]) + "</ul>")
    if r.get("sem_cpf"):
        partes.append('<p class="vazio">O TSE não informa o CPF desta candidatura, então benefícios sociais, '
                      'recursos recebidos e sanções da pessoa não foram consultados.</p>')
    else:
        pf = r.get("pf")
        partes.append("<h3>Benefícios sociais pagos à própria pessoa</h3>")
        if pf is None:
            partes.append(NAO_DEU)
        elif not pf["beneficios"]:
            partes.append('<p class="vazio">Nenhum benefício registrado no CPF (Bolsa Família, Novo Bolsa Família, '
                          'Auxílio Emergencial, Auxílio Brasil, Garantia-Safra, Seguro-Defeso, Auxílio Reconstrução).</p>')
        else:
            partes.append('<ul class="nt">' + "".join(f"<li><b>{e(b['nome'])}</b><br><small>{_beneficio(b)}</small></li>"
                                                      for b in pf["beneficios"]) + "</ul>")
        if pf is not None:
            partes.append("<h3>Sanções</h3>" + (
                '<ul class="nt">' + "".join(f"<li>Consta no {e(s)}</li>" for s in pf["sancoes"]) + "</ul>"
                if pf["sancoes"] else '<p class="vazio">Não consta nos cadastros de sanções (CEIS, CNEP, CEAF).</p>'))
        partes.append("<h3>Recursos federais recebidos pelo CPF</h3>" + _recursos(r.get("recursos_pf")))
    emp = r.get("empresas") or []
    if emp:
        partes.append("<h3>Empresas declaradas: recursos federais e sanções</h3>")
        for nome_emp, pj in emp:
            partes.append(f"<p><b>{e(nome_emp)}</b></p>")
            if pj is None:
                partes.append(NAO_DEU)
                continue
            extra = [x for x, ok in (("tem contratos com o governo federal", pj["contratos"]),
                                     ("tem convênios", pj["convenios"])) if ok]
            if pj["sancoes"]:
                partes.append('<ul class="nt">' + "".join(f"<li>Consta no {e(s)}</li>" for s in pj["sancoes"]) + "</ul>")
            if extra:
                partes.append(f"<p><small>{e('; '.join(extra).capitalize())}.</small></p>")
            partes.append(_recursos(pj["recursos"]))
    return "".join(partes) or '<p class="vazio">Nada a consultar para esta pessoa.</p>'


NAO_DEU = ('<p class="vazio"><b>Fonte não encontrada</b>: a API do Portal da Transparência não respondeu nesta execução. '
           f'Consulte direto no <a href="{SITE}" target="_blank" rel="noopener">Portal da Transparência</a>.</p>')


def _beneficio(b):
    if b["erro"]:
        return "consta no CPF · detalhe: fonte não encontrada nesta execução"
    if b["total"] is None or not b["meses"]:
        return "consta no CPF · detalhe não informado pela API"
    return f'{len(b["meses"])} mês(es), de {e(b["meses"][0])} a {e(b["meses"][-1])} · {brl(b["total"])}'


def _recursos(rec):
    if rec is None:
        return NAO_DEU
    if not rec:
        return '<p class="vazio">Nada recebido do governo federal desde 2019.</p>'
    return '<ul class="nt">' + "".join(f"<li>{e(o)}<br><small>{brl(v)}</small></li>" for o, v in rec[:MAX_FAV]) + "</ul>"
