"""Meus representantes (#59): quem representa cada estado hoje, num arquivo leve por UF (docs/representantes/UF.json)
que o painel so baixa quando o visitante escolhe o estado. Grupos: governador, senadores, deputados federais e
deputados estaduais em exercicio. Fontes oficiais e gratuitas:
  Camara (API de deputados) e Senado (lista atual), via parlamentares.py: cota, projetos, selo e estrela
  TSE (eleitos da ultima eleicao estadual ja empossada): governador e deputados estaduais, com a foto da candidatura
So dados publicos: nada de CPF, chave interna ou campos "_..."."""
import json
from pathlib import Path
import re
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


def parlamentar(p):
    """Deputado federal ou senador de parlamentares.py, so com os campos publicos que o card usa."""
    senado = p.get("casa") == "senado"
    foto = (FOTO_SEN if senado else FOTO_DEP).format(id=p["_id"]) if str(p.get("_id") or "").isdigit() else None
    marcas = [m for m in ("exemplar", "selo") if p.get(m)]
    return _limpa(dict(nome=p.get("nome") or "Não informado", partido=p.get("partido"), foto=foto,
                       perfil=_https(p.get("perfil")), dossie=_local(p.get("dossie")), marcas=marcas,
                       presenca=_presenca(p), votos=_votos(p), **{k: p.get(k) for k in CAMPOS_PARL}))


def eleitos(serie, link=None, foto=None, paginas=None, hoje=None):
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
        nome = (str(r.get("nome_urna") or "").strip() or str(r.get("nome") or "")).title()
        out.setdefault(uf, {}).setdefault(CARGOS_TSE[norm(r["cargo"])], []).append(_limpa(dict(
            nome=nome or "Não informado", partido=r.get("partido"), foto=_https(foto(r)) if foto else None,
            perfil=_https(link(r)) if link else None, dossie=_local((paginas or {}).get(r.get("chave"))))))
    return out, ano


def montar(parl, tse=None, gerado=None, eleicao=None):
    """{uf: dict do arquivo} para os 27 estados; o estado sem ninguem tambem sai, com os grupos vazios."""
    por_uf = {uf: {g: [] for g, _ in GRUPOS} for uf in UFS}
    for p in parl or ():
        uf = str(p.get("uf") or "").upper()
        if uf in por_uf:
            por_uf[uf]["senadores" if p.get("casa") == "senado" else "federais"].append(parlamentar(p))
    for uf, grupos in (tse or {}).items():
        for g, l in grupos.items():
            if uf in por_uf and g in por_uf[uf]:
                por_uf[uf][g] += l
    out = {}
    for uf, grupos in por_uf.items():
        for l in grupos.values():
            l.sort(key=lambda d: norm(d["nome"]))
        out[uf] = dict(uf=uf, estado=UFS[uf][1], gerado_em=gerado, eleicao_estadual=eleicao,
                       grupos=[dict(id=g, titulo=t, pessoas=grupos[g]) for g, t in GRUPOS])
    return out


def gravar(docs, parl, tse=None, gerado=None, eleicao=None):
    """Grava docs/representantes/UF.json (um por estado) e devolve quantas pessoas sairam."""
    pasta = Path(docs) / PASTA
    pasta.mkdir(parents=True, exist_ok=True)
    total = 0
    for uf, d in montar(parl, tse, gerado, eleicao).items():
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
        tse[uf] = dict(governador=[dict(nome=f"Governadora Demo {uf}", partido="YY")],
                       estaduais=[dict(nome=f"Estadual Demo {uf} {k}", partido="ZZ") for k in range(1, 9)])
    return parl, tse, 2022
