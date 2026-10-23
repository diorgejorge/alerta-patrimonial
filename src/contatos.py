"""Contatos oficiais do gabinete (#60), para o cidadao cobrar direto de quem o representa. Fontes oficiais e gratuitas:
  Camara: API https://dadosabertos.camara.leg.br/api/v2/deputados/{id} (ultimoStatus.gabinete, redes sociais)
  Senado: https://legis.senado.leg.br/dadosabertos/senador/{codigo}.json (e-mail, telefones e endereco)
  Deputado estadual: site oficial da Assembleia do estado (config/assembleias.csv)
So campos de contato saem daqui: a resposta da Camara traz o CPF, que e descartado na leitura."""
import csv, re, time
from pathlib import Path
import projetos
from parlamentares import PERFIL_DEP, PERFIL_SEN

CAMARA = "https://dadosabertos.camara.leg.br/api/v2/deputados/{id}"
SENADO = "https://legis.senado.leg.br/dadosabertos/senador/{cod}.json"
ASSEMBLEIAS = Path(__file__).resolve().parent.parent / "config" / "assembleias.csv"
VALIDADE_S = 30 * 86400  # contato de gabinete muda pouco: consulta de novo a cada 30 dias
RE_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.I)


def _email(v):
    v = str(v or "").strip()
    return v if RE_EMAIL.fullmatch(v) else None


def _telefone(v, ddd="61"):
    """Telefone legivel com DDD: '3215-5576' -> '(61) 3215-5576'; '33036100' -> '(61) 3303-6100'."""
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) in (8, 9):
        d = ddd + d
    if len(d) not in (10, 11):
        return None
    return f"({d[:2]}) {d[2:-4]}-{d[-4:]}"


def _https(v):
    v = str(v or "").strip()
    return v if v.startswith("https://") else None


def de_camara(d, ident):
    """Contato do deputado federal a partir da resposta da API da Camara; None se a resposta veio sem dados."""
    dados = (d or {}).get("dados") if isinstance(d, dict) else None
    if not isinstance(dados, dict):
        return None
    st = dados.get("ultimoStatus") or {}
    gab = st.get("gabinete") or {}
    local = ", ".join(f"{rot} {gab[k]}" for k, rot in (("predio", "Anexo"), ("andar", "andar"), ("sala", "sala"))
                      if str(gab.get(k) or "").strip())
    return dict(casa="camara", email=_email(gab.get("email")) or _email(st.get("email")),
                telefone=_telefone(gab.get("telefone")),
                endereco=f"Câmara dos Deputados, {local}, Brasília (DF)" if local else None,
                perfil=PERFIL_DEP.format(id=ident), redes=[u for u in map(_https, dados.get("redeSocial") or []) if u],
                fonte=CAMARA.format(id=ident))


def de_senado(d, cod):
    """Contato do senador a partir da resposta dos Dados Abertos do Senado; None se a resposta veio sem dados."""
    try:
        p = d["DetalheParlamentar"]["Parlamentar"]
    except (TypeError, KeyError):
        return None
    ident = p.get("IdentificacaoParlamentar") or {}
    basicos = p.get("DadosBasicosParlamentar") or {}
    tels = (p.get("Telefones") or {}).get("Telefone") or []
    tels = tels if isinstance(tels, list) else [tels]
    fones = [_telefone(t.get("NumeroTelefone")) for t in tels
             if isinstance(t, dict) and str(t.get("IndicadorFax") or "").lower() not in ("sim", "s")]
    endereco = " ".join(str(basicos.get("EnderecoParlamentar") or "").split()) or None
    return dict(casa="senado", email=_email(ident.get("EmailParlamentar")), telefone=next((f for f in fones if f), None),
                endereco=endereco, perfil=_https(ident.get("UrlPaginaParlamentar")) or PERFIL_SEN.format(cod=cod),
                redes=[], fonte=SENADO.format(cod=cod))


def buscar(casa, ident, cache=None, buscar_json=projetos._json):
    """Contato de um parlamentar ({'casa', 'email', 'telefone', 'endereco', 'perfil', 'redes', 'fonte'}) ou None se a
    fonte nao respondeu. Com `cache`, a resposta vale por 30 dias e uma falha usa a ultima guardada."""
    chave = f"contato:{casa}:{ident}"
    guardado = cache.get(chave) if cache else None
    if guardado:
        return guardado
    if casa == "camara":
        c = de_camara(buscar_json(CAMARA.format(id=ident)), ident)
    elif casa == "senado":
        c = de_senado(buscar_json(SENADO.format(cod=ident)), ident)
    else:
        return None
    if c and cache:
        cache.set(chave, c)
    return c


def coletar(parl, chaves, cache=None, pausa=0.3, buscar_json=projetos._json):
    """{chave TSE: contato} dos parlamentares em exercicio (lista de parlamentares.montar) que estao em `chaves`.
    Quem nao respondeu fica com None (a pagina mostra "Fonte nao encontrada"). Consulta so quem tem pagina."""
    out = {}
    for p in parl:
        ch = p.get("_chave")
        if not ch or ch not in chaves or ch in out:
            continue
        guardado = cache.get(f"contato:{p['casa']}:{p['_id']}") if cache else None
        out[ch] = guardado or buscar(p["casa"], p["_id"], cache, buscar_json)
        if not guardado and pausa:
            time.sleep(pausa)  # respeita o limite das APIs (429)
    if cache:
        cache.salvar()
    achados = sum(1 for c in out.values() if c)
    print(f"Contatos de gabinete: {achados} de {len(out)} parlamentares com pagina.")
    return out


# contato ficticio para o --demo (sem internet): so para ver a aba "Como cobrar" preenchida
DEMO = dict(casa="camara", email="dep.demo@camara.leg.br", telefone="(61) 3215-5000",
            endereco="Câmara dos Deputados, Anexo 4, andar 5, sala 500, Brasília (DF)",
            perfil="https://www.camara.leg.br/deputados/000000", redes=[], fonte=CAMARA.format(id="000000"))


def assembleias(caminho=ASSEMBLEIAS):
    """{UF: (nome, site oficial)} das Assembleias Legislativas."""
    try:
        with open(caminho, encoding="utf-8", newline="") as f:
            return {r["uf"].strip().upper(): (r["nome"].strip(), r["site"].strip()) for r in csv.DictReader(f)
                    if _https(r.get("site"))}
    except (OSError, KeyError):
        return {}
