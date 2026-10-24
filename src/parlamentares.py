"""Deputados federais e senadores em exercicio, todos e nao so quem esta entre os destaques (#44, #45): cota
parlamentar dos ultimos 4 anos, projetos apresentados e aprovados com o selo "Mao na massa" (os 10% de cada casa com
mais aprovados, entre quem esta em exercicio) e a estrela de exemplar (exemplares.py). Fontes oficiais e gratuitas:
  Camara: API https://dadosabertos.camara.leg.br/api/v2/deputados (em exercicio); o id liga ao CPF pela cota
  Senado: https://legis.senado.leg.br/dadosabertos/senador/lista/atual; liga ao TSE pelo nome e UF
O CPF so liga as bases aqui dentro (TSE, cota e sancoes) e fica nos campos "_...", que nunca vao para o site."""
import sys
import pandas as pd
import cota, exemplares, projetos

CAMARA_DEP = "https://dadosabertos.camara.leg.br/api/v2/deputados?itens=100&ordem=ASC&ordenarPor=nome&pagina={pag}"
PERFIL_DEP = "https://www.camara.leg.br/deputados/{id}"
PERFIL_SEN = "https://www25.senado.leg.br/web/senadores/senador/-/perfil/{cod}"


def deputados():
    """[dict(id, nome, partido, uf)] dos deputados em exercicio; None se a API nao respondeu."""
    out = []
    for pag in range(1, 21):
        d = projetos._json(CAMARA_DEP.format(pag=pag))
        if not isinstance(d, dict):
            if out:
                print(f"[aviso] lista de deputados incompleta: parou na pagina {pag}", file=sys.stderr)
            break
        out += [dict(id=str(x["id"]), nome=x.get("nome") or "", partido=x.get("siglaPartido") or "",
                     uf=x.get("siglaUf") or "") for x in d.get("dados") or [] if x.get("id")]
        if not any(l.get("rel") == "next" for l in d.get("links") or []):
            break
    return out or None


def _num(v):
    return None if v is None or pd.isna(v) else float(v)


def _tse(df):
    """Periodo mais recente de cada deputado federal ou senador no TSE: por chave e, para senadores, por (nome, UF)."""
    u = exemplares.ultimos(df).to_dict("records") if len(df) else []
    por_chave = {r["chave"]: r for r in u}
    por_nome = {}
    for r in u:
        if "SENADOR" in {cota.norm(r.get("cargo_ini")), cota.norm(r.get("cargo"))}:  # eleito senador no inicio ou no fim
            for n in (r.get("nome"), r.get("nome_urna")):
                if isinstance(n, str) and n.strip():
                    por_nome.setdefault((cota.norm(n), str(r["uf"]).upper()), r)
    return por_chave, por_nome


def _base(casa, cargo, nome, nome_completo, partido, uf, ident, perfil, cpf, r):
    p = dict(nome=nome, cargo=cargo, casa=casa, partido=partido, uf=uf, perfil=perfil,
             _id=ident, _cpf=cpf, _chave=(r or {}).get("chave") or ("cpf:" + cpf if cpf else ""),
             _nome_completo=nome_completo,
             _nomes={cota.norm(nome), cota.norm(nome_completo), cota.norm((r or {}).get("nome"))} - {""})
    if r:
        p.update(ano_ini=int(r["ano_ini"]), ano_fim=int(r["ano_fim"]), cresc=_num(r["cresc"]), cap=_num(r["cap"]),
                 razao=_num(r.get("razao_salario")))
    p["patrimonio_ok"] = exemplares.compativel(r["cresc"], r["cap"], r.get("razao_salario")) if r else None
    return p


def montar(df, anos, cache, chave_api, deps=None, sens=None, camara=None, senado=None):
    """Lista de todos os parlamentares em exercicio (dicts com campos internos "_...") e o contexto usado nos
    dossies: {"camara", "senado"} (contagens de projetos) e "membros" (para o corte do selo).
    deps/sens/camara/senado: dados prontos (testes); sem eles, busca nas fontes oficiais."""
    anos = list(anos)
    deps = deputados() if deps is None else deps
    sens = projetos.lista_senado() if sens is None else sens
    if not deps and not sens:
        print("Parlamentares: listas da Camara e do Senado indisponiveis.")
        return [], {}
    dep_base = cota.bases(anos, cache)[0]
    id_cpf = {i: c for i, c in zip(dep_base["id"], dep_base["cpf"]) if i} if len(dep_base) else {}
    por_chave, por_nome = _tse(df)
    lista = []
    for d in deps or []:
        cpf = id_cpf.get(d["id"], "")
        lista.append(_base("camara", "DEPUTADO FEDERAL", d["nome"], "", d["partido"], d["uf"], d["id"],
                           PERFIL_DEP.format(id=d["id"]), cpf, por_chave.get("cpf:" + cpf) if cpf else None))
    for s in sens or []:
        uf = str(s.get("uf") or "").upper()
        r = next((por_nome[(n, uf)] for n in sorted(s["nomes"]) if (n, uf) in por_nome), None)
        ch = (r or {}).get("chave") or ""
        lista.append(_base("senado", "SENADOR", s["nome"], s["nome_completo"], s["partido"], uf, s["cod"],
                           PERFIL_SEN.format(cod=s["cod"]), ch[4:] if ch.startswith("cpf:") else "", r))

    # cota parlamentar: deputado pelo CPF, senador pelo nome (cota.coletar)
    pessoas = {i: dict(nome=p["_nome_completo"] or p["nome"], nome_urna=p["nome"], cargo=p["cargo"], cpf=p["_cpf"])
               for i, p in enumerate(lista)}
    gastos = cota.coletar(pessoas, anos, cache)
    for i, p in enumerate(lista):
        g = gastos.get(i)
        p["cota"] = round(g["total"], 2) if g else None
        if g:
            p.update(cota_link=g["link"], cota_de=g["anos"][0][0], cota_ate=g["anos"][-1][0], _cota_tipos=g["tipos"])

    # projetos e selo: a casa inteira (so quem esta em exercicio) entra no corte dos 10%
    ini, fim = f"{anos[0]}-01-01", f"{anos[-1]}-12-31"
    if camara is None and deps:
        camara = projetos.contar_camara(anos, cache)
    if senado is None and sens:
        senado = projetos.contar_senado(ini, cache=cache)
    membros = dict(camara=[d["id"] for d in deps or []], senado=[s["cod"] for s in sens or []])
    cs = projetos.cortes(camara, senado, membros)
    for p in lista:
        cont = camara if p["casa"] == "camara" else senado
        v = None
        if cont is not None:
            v = cont.get(p["_id"], (0, 0)) if p["casa"] == "camara" else cont.get(p["_id"])
        p["apresentados"], p["aprovados"] = (v[0], v[1]) if v else (None, None)
        p["selo"] = bool(v) and projetos.tem_selo(v[1], v[0], cs[p["casa"]])
        if v:
            p["proj_link"] = (projetos.link_camara(p["_id"], ini, fim) if p["casa"] == "camara"
                              else projetos.LINK_SENADO.format(cod=p["_id"]))
        p["proj_de"], p["proj_ate"] = anos[0], anos[-1]

    exemplares.avaliar(lista, cota.medias(anos, cache), chave_api)
    print(f"Parlamentares: {sum(p['casa'] == 'camara' for p in lista)} deputados federais e "
          f"{sum(p['casa'] == 'senado' for p in lista)} senadores em exercicio; "
          f"{sum('ano_ini' in p for p in lista)} ligados ao TSE, {sum(p['cota'] is not None for p in lista)} com cota, "
          f"{sum(p['apresentados'] is not None for p in lista)} com projetos, {sum(p['selo'] for p in lista)} com o selo "
          f"{projetos.SELO}.")
    return lista, dict(camara=camara, senado=senado, membros=membros)


def publico(p):
    """O que vai para o painel: sem os campos internos (CPF, chave, ids) e sem valores vazios."""
    return {k: v for k, v in p.items() if not k.startswith("_") and k != "patrimonio_ok" and v is not None}


def lista_exemplares(lista):
    """Todos os exemplares (estrela), no formato dos cards do painel: patrimonio mais compativel primeiro."""
    l = [p for p in lista if p.get("exemplar")]
    l.sort(key=lambda p: (p["razao"] if p.get("razao") is not None else -1, p["cota"] / (p.get("cota_media") or 1)))
    return [dict(nome=p["nome"], cargo=p["cargo"], partido=p["partido"], uf=p["uf"], ano_ini=p.get("ano_ini"),
                 ano_fim=p.get("ano_fim"), cresc=p.get("cresc"), cap=p.get("cap"), razao=p.get("razao"),
                 cota=p["cota"], cota_media=p.get("cota_media"), link=p.get("cota_link") or p["perfil"],
                 dossie=p.get("dossie")) for p in l]


def ranking_cota(lista, n=10):
    """Quem mais gastou da cota entre todos os parlamentares em exercicio, com os maiores tipos de despesa."""
    l = sorted((p for p in lista if p.get("cota")), key=lambda p: -p["cota"])[:n]
    return [dict(nome=p["nome"], cargo=p["cargo"], partido=p["partido"], uf=p["uf"], total=p["cota"],
                 de=p["cota_de"], ate=p["cota_ate"], link=p["cota_link"], dossie=p.get("dossie"),
                 tipos=[dict(tipo=t, valor=round(v, 2)) for t, v in p["_cota_tipos"][:3]]) for p in l]


def ranking_projetos(lista, n=10):
    """Quem mais apresentou e aprovou projetos entre todos os parlamentares em exercicio."""
    l = sorted((p for p in lista if p.get("apresentados")), key=lambda p: (-p["aprovados"], -p["apresentados"]))[:n]
    return [dict(nome=p["nome"], cargo=p["cargo"], partido=p["partido"], uf=p["uf"], apresentados=p["apresentados"],
                 aprovados=p["aprovados"], selo=p["selo"], de=p["proj_de"], ate=p["proj_ate"], link=p.get("proj_link"),
                 dossie=p.get("dossie")) for p in l]
