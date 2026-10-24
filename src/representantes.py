"""Meus representantes (#59): quem representa cada estado hoje, num arquivo leve por UF (docs/representantes/UF.json)
que o painel so baixa quando o visitante escolhe o estado. Grupos: governador, senadores, deputados federais e
deputados estaduais em exercicio. Fontes oficiais e gratuitas:
  Camara (API de deputados) e Senado (lista atual), via parlamentares.py: cota, projetos, selo e estrela
  TSE (eleitos da ultima eleicao estadual ja empossada): governador e deputados estaduais, com a foto da candidatura
So dados publicos: nada de CPF, chave interna ou campos "_..."."""
import json
from pathlib import Path
import datetime as dt
import re, time
import contatos
from estados import UFS, mandato_estadual, norm

PASTA = "representantes"
FOTO_DEP = "https://www.camara.leg.br/internet/deputado/bandep/{id}.jpg"
FOTO_SEN = "https://www.senado.leg.br/senadores/img/fotos-oficiais/senador{id}.jpg"
CARGOS_TSE = {"GOVERNADOR": "governador", "DEPUTADO ESTADUAL": "estaduais", "DEPUTADO DISTRITAL": "estaduais"}
# ordem e titulos dos grupos no painel (o DF tem deputados distritais)
GRUPOS = (("governador", "Governador"), ("senadores", "Senadores"), ("federais", "Deputados federais"),
          ("estaduais", "Deputados estaduais"))
CAMPOS_PARL = ("cota", "cota_media", "cota_link", "apresentados", "aprovados", "proj_link")


def _https(u):
    return u if isinstance(u, str) and u.startswith("https://") else None


def _local(u):
    """Pagina do proprio site (dossie/p0001.html), vista da raiz como o painel; link externo ou esquisito: None."""
    return u if isinstance(u, str) and u and not re.match(r"\s*([a-z][a-z0-9+.-]*:|/)", u, re.I) else None


def _limpa(d):
    """Sem valores vazios: o painel mostra "Não informado" no que faltar."""
    return {k: v for k, v in d.items() if v not in (None, "", [])}


def _presenca(p):
    """So o resumo do card: % de presenca, media da casa e link (presenca.py, thread "Votacoes e presenca")."""
    pr = p.get("presenca")
    return _limpa(dict(pct=pr.get("pct"), media_casa=pr.get("media_casa"), link=_https(pr.get("link")))) or None \
        if isinstance(pr, dict) else None


def _votos(p):
    """[votou, temas]: em quantos temas acompanhados a pessoa votou (votacoes.py)."""
    v = p.get("votos")
    return [sum(x.get("voto") not in (None, "", "Não votou") for x in v), len(v)] if isinstance(v, list) and v else None


def parlamentar(p, contato=None):
    """Deputado federal ou senador de parlamentares.py, so com os campos publicos que o card usa.
    `contato`: gabinete (contatos.py); so e-mail e telefone, o resto ja esta no perfil oficial."""
    senado = p.get("casa") == "senado"
    foto = (FOTO_SEN if senado else FOTO_DEP).format(id=p["_id"]) if str(p.get("_id") or "").isdigit() else None
    marcas = [m for m in ("exemplar", "selo") if p.get(m)]
    return _limpa(dict(nome=p.get("nome") or "Não informado", partido=p.get("partido"), foto=foto,
                       perfil=_https(p.get("perfil")), dossie=_local(p.get("dossie")), marcas=marcas,
                       presenca=_presenca(p), votos=_votos(p),
                       contato=_limpa(dict(email=(contato or {}).get("email"), telefone=(contato or {}).get("telefone"))) or None, **{k: p.get(k) for k in CAMPOS_PARL}))


def contatos_de(parl, cache=None, pausa=0.3, buscar=contatos.buscar):
    """{(casa, id): contato} do gabinete de todos os parlamentares em exercicio (contatos.py, mesmo cache de 30 dias
    da aba "Como cobrar"). So pausa quando consultou a fonte, para respeitar o limite das APIs (429)."""
    out = {}
    for p in parl or ():
        k = (p.get("casa"), p.get("_id"))
        if not k[1] or k in out:
            continue
        novo = not (cache and cache.get(f"contato:{k[0]}:{k[1]}"))
        out[k] = buscar(k[0], k[1], cache)
        if novo and pausa:
            time.sleep(pausa)
    if cache:
        cache.salvar()
    print(f"Meus representantes: contato de gabinete de {sum(1 for c in out.values() if c)} de {len(out)} parlamentares.")
    return out


def eleitos(serie, link=None, foto=None, paginas=None, hoje=None, extra=None):
    """{uf: {"governador": [...], "estaduais": [...]}} dos eleitos da ultima eleicao estadual ja empossada (TSE).
    `link`/`foto`: funcoes do pipeline que montam o link e a foto do DivulgaCandContas a partir da linha."""
    if serie is None or not len(serie):
        return {}, None
    cargo = serie["cargo"].map(norm)
    est = serie[cargo.isin(CARGOS_TSE) & serie["eleito"].astype(bool)]
    ano = mandato_estadual(sorted(set(est["ano"].astype(int))), hoje)
    if ano is None:
        return {}, None
    out = {}
    for r in est[est["ano"].astype(int) == ano].to_dict("records"):
        uf = str(r.get("uf") or "").upper()
        if uf not in UFS:
            continue
        out.setdefault(uf, {}).setdefault(CARGOS_TSE[norm(r["cargo"])], []).append(_pessoa_tse(r, link, foto, paginas, extra))
    return out, ano


CARGOS_MUN = {"PREFEITO": "prefeito", "VICE-PREFEITO": "vice", "VEREADOR": "vereadores"}
GRUPOS_MUN = (("prefeito", "Prefeito"), ("vice", "Vice-prefeito"), ("vereadores", "Vereadores"))


FAIXAS = ("forte", "atencao", "informativo")


def faixas(df, paginas=None):
    """{chave: dict(faixa, lista)} de quem esta na lista completa (todos.json): faixa do patrimonio no periodo mais
    recente (so as tres faixas coloridas), lista=1 para o painel abrir a pessoa em "Todas as pessoas" e a pagina
    da pessoa (`paginas`: {chave: pessoa/pNNNN.html}), quando houver."""
    if df is None or not len(df):
        return {}
    ult = df.sort_values(["ano_fim", "ano_ini"]).groupby("chave").tail(1)
    pg = paginas or {}
    return {ch: _limpa(dict(faixa=nv if nv in FAIXAS else None, lista=1, dossie=_local(pg.get(ch))))
            for ch, nv in zip(ult["chave"], ult["nivel"])}


def mandato_municipal(anos, hoje=None):
    """Ano da eleicao municipal em exercicio (posse em 1/jan do ano seguinte)."""
    hoje = hoje or dt.date.today()
    validos = [a for a in anos if dt.date(int(a) + 1, 1, 1) <= hoje]
    return max(validos) if validos else None


def cidades(serie, link=None, foto=None, paginas=None, hoje=None, extra=None):
    """{codigo TSE do municipio: dict(cidade, uf, grupos)} dos eleitos da ultima eleicao municipal empossada e o ano.
    Precisa da coluna nm_ue (leitura do TSE versao 2); sem ela, nada."""
    if serie is None or not len(serie) or "nm_ue" not in serie:
        return {}, None
    mun = serie[serie["cargo"].map(norm).isin(CARGOS_MUN) & serie["eleito"].astype(bool)]
    ano = mandato_municipal(sorted(set(mun["ano"].astype(int))), hoje)
    if ano is None:
        return {}, None
    out = {}
    for r in mun[mun["ano"].astype(int) == ano].to_dict("records"):
        uf, cod, nome = str(r.get("uf") or "").upper(), str(r.get("sg_ue") or "").strip(), str(r.get("nm_ue") or "").strip()
        if uf not in UFS or not cod.isdigit() or not nome:
            continue
        c = out.setdefault(cod, dict(cidade=nome.title(), uf=uf, grupos={g: [] for g, _ in GRUPOS_MUN}))
        c["grupos"][CARGOS_MUN[norm(r["cargo"])]].append(_pessoa_tse(r, link, foto, paginas, extra))
    return out, ano


def _pessoa_tse(r, link, foto, paginas, extra=None):
    nome = (str(r.get("nome_urna") or "").strip() or str(r.get("nome") or "")).title()
    return _limpa(dict(nome=nome or "Não informado", partido=r.get("partido"), foto=_https(foto(r)) if foto else None,
                       perfil=_https(link(r)) if link else None, dossie=_local((paginas or {}).get(r.get("chave"))),
                       **(extra or {}).get(r.get("chave"), {})))


def gravar_cidades(docs, cid, ano):
    """docs/representantes/cidades/<codigo>.json, um por municipio, sem data de geracao (so muda quando o dado muda)."""
    pasta = Path(docs) / PASTA / "cidades"
    pasta.mkdir(parents=True, exist_ok=True)
    for cod, c in cid.items():
        for l in c["grupos"].values():
            l.sort(key=lambda d: norm(d["nome"]))
        d = dict(cidade=c["cidade"], uf=c["uf"], eleicao=ano,
                 grupos=[dict(id=g, titulo=t, pessoas=c["grupos"][g]) for g, t in GRUPOS_MUN])
        (pasta / f"{cod}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(cid)


def lista_cidades(cid):
    """{uf: [[codigo, nome], ...]} em ordem alfabetica, para o seletor de cidade (vai no arquivo do estado)."""
    out = {}
    for cod, c in cid.items():
        out.setdefault(c["uf"], []).append([cod, c["cidade"]])
    for l in out.values():
        l.sort(key=lambda x: norm(x[1]))
    return out


def montar(parl, tse=None, gerado=None, eleicao=None, contato=None, assembleias=None, cidades_uf=None, extra=None):
    """{uf: dict do arquivo} para os 27 estados; o estado sem ninguem tambem sai, com os grupos vazios."""
    por_uf = {uf: {g: [] for g, _ in GRUPOS} for uf in UFS}
    for p in parl or ():
        uf = str(p.get("uf") or "").upper()
        if uf in por_uf:
            por_uf[uf]["senadores" if p.get("casa") == "senado" else "federais"].append(
                dict(parlamentar(p, (contato or {}).get((p.get("casa"), p.get("_id")))),
                     **(extra or {}).get(p.get("_chave"), {})))
    for uf, grupos in (tse or {}).items():
        for g, l in grupos.items():
            if uf in por_uf and g in por_uf[uf]:
                por_uf[uf][g] += l
    # ano em que o senador foi eleito: o ultimo periodo do TSE, se for uma eleicao geral do mandato atual (8 anos)
    if eleicao:
        for p in parl or ():
            if p.get("casa") == "senado" and p.get("ano_fim") in (eleicao, eleicao - 4):
                uf = str(p.get("uf") or "").upper()
                for d in por_uf.get(uf, {}).get("senadores", ()):
                    if d["nome"] == p.get("nome"):
                        d["eleito_em"] = p["ano_fim"]
    out = {}
    for uf, grupos in por_uf.items():
        for l in grupos.values():
            l.sort(key=lambda d: norm(d["nome"]))
        ala = (assembleias or {}).get(uf)
        out[uf] = dict(uf=uf, estado=UFS[uf][1], gerado_em=gerado, eleicao_estadual=eleicao,
                       assembleia=dict(nome=ala[0], site=ala[1]) if ala and _https(ala[1]) else None,
                       cidades=(cidades_uf or {}).get(uf) or [],
                       grupos=[dict(id=g, titulo=t, pessoas=grupos[g]) for g, t in GRUPOS])
    return out


def gravar(docs, parl, tse=None, gerado=None, eleicao=None, contato=None, assembleias=None, cidades_uf=None, extra=None):
    """Grava docs/representantes/UF.json (um por estado) e devolve quantas pessoas sairam."""
    pasta = Path(docs) / PASTA
    pasta.mkdir(parents=True, exist_ok=True)
    total = 0
    for uf, d in montar(parl, tse, gerado, eleicao, contato, assembleias, cidades_uf, extra).items():
        (pasta / f"{uf}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        total += sum(len(g["pessoas"]) for g in d["grupos"])
    print(f"Meus representantes: {total} pessoas em {len(UFS)} arquivos (docs/{PASTA}).")
    return total


def demo():
    """(parlamentares, eleitos do TSE, ano) sinteticos e deterministicos (sem rede), para o --demo e os testes."""
    parl, tse = [], {}
    for i, uf in enumerate(UFS):
        for j in range(1, 6):
            sen, ident = j > 3, str(9000 + i * 10 + j)
            parl.append(dict(nome=f"{'Senadora' if sen else 'Deputada'} Demo {uf} {j}", casa="senado" if sen else "camara",
                             cargo="SENADOR" if sen else "DEPUTADO FEDERAL", partido="XX", uf=uf, _id=ident,
                             _cpf="00000000000", perfil=f"https://www.camara.leg.br/deputados/{ident}",
                             cota=100000.0 * j, cota_media=250000.0, apresentados=10 * j, aprovados=j - 1,
                             exemplar=j == 1, selo=j == 5))
        tse[uf] = dict(governador=[dict(nome=f"Governadora Demo {uf}", partido="YY", faixa="atencao", lista=1)],
                       estaduais=[dict(nome=f"Estadual Demo {uf} {k}", partido="ZZ") for k in range(1, 9)])
    return parl, tse, 2022


def demo_cidades():
    """Municipios sinteticos (dois por estado, menos o DF) no formato de cidades(), para o --demo e os testes."""
    out = {}
    for i, uf in enumerate(u for u in UFS if u != "DF"):
        for k in (1, 2):
            out[f"{i + 1:03d}{k:02d}"] = dict(cidade=f"Cidade Demo {uf} {k}", uf=uf, grupos=dict(
                prefeito=[dict(nome=f"Prefeita Demo {uf} {k}", partido="AA", faixa="forte", lista=1)],
                vice=[dict(nome=f"Vice Demo {uf} {k}", partido="BB")],
                vereadores=[dict(nome=f"Vereadora Demo {uf} {k} {j}", partido="CC") for j in range(1, 10)]))
    return out, 2024
