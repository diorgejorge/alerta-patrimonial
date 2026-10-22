"""Empresas declaradas ao TSE: atividade principal (CNAE), inicio de atividade, capital social e situacao cadastral,
dos dados abertos oficiais do CNPJ da Receita Federal (arquivos mensais, CSV sem cabecalho, ';', latin-1):
  https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9 (pasta AAAA-MM com Empresas0..9.zip,
  Estabelecimentos0..9.zip e Cnaes.zip; acesso por WebDAV publico em /public.php/webdav/AAAA-MM/...)
Os arquivos grandes (~7 GB por mes) sao baixados um por vez em pasta temporaria (fora de data/cache, que vai para o
actions/cache), lidos em blocos e apagados; so fica guardado data/cache/cnpj_receita.json (cifrado, cifra.py) com as poucas empresas
procuradas. O CNPJ so serve para cruzar as bases aqui dentro: nunca vai para o site nem para o log.
Faturamento nao e publico: nada aqui diz se a renda e compativel; e ponto de partida para pesquisar."""
import base64, html, io, json, math, re, shutil, sys, tempfile, threading, time
import urllib.error, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
import cifra

COMPARTILHAMENTO = "YggdBLfdninEJX9"  # link publico da Receita (SERPRO+/Nextcloud)
WEBDAV = "https://arquivos.receitafederal.gov.br/public.php/webdav/"
LINK_FONTE = ("https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/cadastros/consultas/"
              "dados-publicos-cnpj")
EMPRESAS = [f"Empresas{i}.zip" for i in range(10)]
ESTABELECIMENTOS = [f"Estabelecimentos{i}.zip" for i in range(10)]
NECESSARIOS = ["Cnaes.zip"] + EMPRESAS + ESTABELECIMENTOS
SITUACAO = {"01": "nula", "1": "nula", "02": "ativa", "2": "ativa", "03": "suspensa", "3": "suspensa",
            "04": "inapta", "4": "inapta", "08": "baixada", "8": "baixada"}
RE_MES = re.compile(r"\d{4}-\d{2}")
UA = "alerta-patrimonial/1.0"
LOTE = 300_000          # linhas por bloco do read_csv (memoria ~ centenas de MB por bloco)
PARTES = 8              # conexoes em paralelo por arquivo grande (o servidor limita ~1,5 MB/s por conexao)
TENTATIVAS = 4
LIMITE_S = 75 * 60      # desiste da varredura se passar disso (o job inteiro tem 150 min)
e = html.escape
_PARAR = threading.Event()  # interrompe downloads em andamento quando a varredura desiste


def _cab(extra=None):
    tok = base64.b64encode(f"{COMPARTILHAMENTO}:".encode()).decode()
    return {"User-Agent": UA, "Authorization": "Basic " + tok, **(extra or {})}


def _aviso(msg):
    print(f"[aviso] empresas (Receita): {msg}", file=sys.stderr)


def limpa(c):
    """CNPJ so com digitos/letras maiusculas (CNPJ alfanumerico a partir de 07/2026); '' se nao tem 14 posicoes."""
    c = re.sub(r"[^0-9A-Z]", "", str(c or "").upper())
    if c.isdigit() and 12 <= len(c) < 14:  # zeros a esquerda perdidos em conversao numerica
        c = c.zfill(14)
    return c if len(c) == 14 else ""


# ---------- acesso a Receita ----------

def _listar(caminho):
    """[(nome, tamanho)] de uma pasta do compartilhamento (PROPFIND Depth 1)."""
    req = urllib.request.Request(WEBDAV + caminho, method="PROPFIND", headers=_cab({"Depth": "1"}))
    with urllib.request.urlopen(req, timeout=60) as r:
        raiz = ET.fromstring(r.read())
    out = []
    for resp in raiz.iter("{DAV:}response"):
        href = resp.findtext("{DAV:}href") or ""
        tam = resp.findtext(".//{DAV:}getcontentlength")
        out.append((urllib.parse.unquote(href.rstrip("/").rsplit("/", 1)[-1]), int(tam) if tam else None))
    return out


def _mes():
    """(ref 'AAAA-MM', {arquivo: tamanho}) do mes mais recente com todos os arquivos; None se a Receita nao respondeu."""
    try:
        meses = sorted((n for n, _ in _listar("") if RE_MES.fullmatch(n)), reverse=True)
        for m in meses[:3]:
            arqs = dict(_listar(m + "/"))
            if all(n in arqs for n in NECESSARIOS):
                return m, arqs
        _aviso("nenhum mes completo na listagem")
    except Exception as ex:
        _aviso(f"listagem indisponivel ({ex!r})")
    return None


def baixar(url, dest):
    """Arquivo pequeno (Cnaes.zip) em bytes, guardado cifrado em data/cache (cifra.py); so baixa de novo se o
    servidor disser que mudou."""
    return cifra.baixar(url, dest, cab=_cab(), timeout=120)


def _faixa(url, dest, ini, fim):
    """Baixa os bytes ini..fim para a mesma posicao de dest; retoma de onde parou se a conexao cair."""
    pos, erro = ini, None
    for t in range(TENTATIVAS):
        if _PARAR.is_set():
            return False
        try:
            req = urllib.request.Request(url, headers=_cab({"Range": f"bytes={pos}-{fim}"}))
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "r+b") as f:
                if r.status != 206:
                    raise OSError(f"HTTP {r.status} sem suporte a Range")
                f.seek(pos)
                while pos <= fim and not _PARAR.is_set() and (bloco := r.read(1 << 20)):
                    f.write(bloco)
                    pos += len(bloco)
            if pos > fim:
                return True
        except Exception as ex:
            erro = ex
        time.sleep(3 * (t + 1))
    _aviso(f"{url.rsplit('/', 1)[-1]} incompleto ({erro!r})")
    return False


def _baixar_grande(url, tamanho, dest):
    """Arquivo grande em pasta temporaria, em PARTES faixas paralelas. Devolve dest ou None."""
    with open(dest, "wb") as f:
        f.truncate(tamanho)
    passo = max(1, -(-tamanho // PARTES))
    faixas = [(i, min(i + passo, tamanho) - 1) for i in range(0, tamanho, passo)]
    with ThreadPoolExecutor(PARTES) as ex:
        ok = all(list(ex.map(lambda fx: _faixa(url, dest, *fx), faixas)))
    return dest if ok else None


# ---------- leitura dos CSV (layout oficial, sem cabecalho) ----------

def _ler(caminho, cols):
    """Blocos (DataFrame, colunas = posicoes) do CSV dentro do zip, lido em streaming."""
    with zipfile.ZipFile(io.BytesIO(caminho) if isinstance(caminho, (bytes, bytearray)) else caminho) as z:
        nome = next(n for n in z.namelist() if not n.endswith("/"))
        with z.open(nome) as f:
            try:
                leitor = pd.read_csv(f, sep=";", header=None, dtype=str, usecols=cols, encoding="latin-1",
                                     keep_default_na=False, chunksize=LOTE, on_bad_lines="skip")
            except pd.errors.EmptyDataError:  # arquivo sem linhas
                return
            with leitor:
                try:
                    yield from leitor
                except pd.errors.EmptyDataError:
                    return


def ler_cnaes(caminho):
    """{codigo 7 digitos: descricao}. Cnaes.zip: 0 codigo, 1 descricao."""
    out = {}
    for ch in _ler(caminho, [0, 1]):
        out.update(zip(ch[0].map(_cod), ch[1].str.strip()))
    return out


def _cod(c):
    c = str(c or "").strip()
    return c.zfill(7) if c.isdigit() else c


def ler_empresas(caminho, basicos):
    """{cnpj_basico: capital social} so dos pedidos. Empresas: 0 cnpj_basico, 1 razao social, 2 natureza,
    3 qualificacao do responsavel, 4 capital social ('1000,00'), 5 porte, 6 ente federativo."""
    out = {}
    for ch in _ler(caminho, [0, 4]):
        ch = ch[ch[0].isin(basicos)]
        out.update(zip(ch[0], ch[4].map(_num)))
    return out


def ler_estabelecimentos(caminho, alvo):
    """{cnpj 14: dict(situacao, inicio, cnae)} so dos pedidos. Estabelecimentos: 0 basico, 1 ordem, 2 dv,
    3 matriz/filial, 4 nome fantasia, 5 situacao cadastral, 6 data situacao, 7 motivo, 8 cidade exterior, 9 pais,
    10 inicio de atividade (AAAAMMDD), 11 CNAE principal, 12.. secundarios/endereco/contato (nunca lidos)."""
    basicos, out = {c[:8] for c in alvo}, {}
    for ch in _ler(caminho, [0, 1, 2, 5, 10, 11]):
        ch = ch[ch[0].isin(basicos)]
        if ch.empty:
            continue
        cnpj = ch[0] + ch[1] + ch[2]
        ch = ch[cnpj.isin(alvo)]
        for c, sit, ini, cnae in zip(cnpj.loc[ch.index], ch[5], ch[10], ch[11]):
            out[c] = dict(situacao=SITUACAO.get(sit.strip()), inicio=_data(ini), cnae=_cod(cnae) or None)
    return out


def _num(s):
    try:
        v = float(str(s).strip().replace(".", "").replace(",", "."))
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _data(s):
    s = str(s or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if re.fullmatch(r"(19|20)\d{6}", s) and s[4:6] != "00" else None


# ---------- coleta com cache mensal ----------

def _carregar(arq):
    try:
        j = json.loads(cifra.ler(arq) or b"{}")  # cifrado (cifra.py): tem CNPJs
        return dict(ref=j.get("ref"), procurados=set(j.get("procurados") or []), dados=j.get("dados") or {})
    except Exception:
        return dict(ref=None, procurados=set(), dados={})


def _salvar(arq, ref, procurados, dados):
    cifra.gravar(arq, json.dumps(dict(ref=ref, procurados=sorted(procurados), dados=dados),
                                 ensure_ascii=False).encode())  # cifrado: tem CNPJs


def _varrer(ref, arqs, alvo, cache):
    """Le Cnaes, Empresas0..9 e Estabelecimentos0..9 do mes ref. Devolve {cnpj: dados} ou None se algo falhou."""
    t0 = time.monotonic()
    base = WEBDAV + ref + "/"
    cn = baixar(base + "Cnaes.zip", cache / "cnpj_cnaes.zip")
    if not cn:
        return None
    cnaes = ler_cnaes(cn)
    basicos = {c[:8] for c in alvo}
    capital, estab = {}, {}
    tmp = Path(tempfile.mkdtemp(prefix="cnpj_receita_"))
    _PARAR.clear()

    def pega(n):
        try:
            return None if _PARAR.is_set() else _baixar_grande(base + n, int(arqs[n]), tmp / n)
        except Exception as exc:
            _aviso(f"{n} ({exc!r})")
            return None

    try:
        with ThreadPoolExecutor(1) as ex:  # baixa o proximo arquivo enquanto le o atual (no maximo 2 no disco)
            nomes = EMPRESAS + ESTABELECIMENTOS
            fut = ex.submit(pega, nomes[0])
            for i, n in enumerate(nomes):
                caminho = fut.result()
                if i + 1 < len(nomes):
                    if time.monotonic() - t0 > LIMITE_S:
                        _aviso(f"varredura passou de {LIMITE_S // 60} min; desisto neste mes")
                        return None
                    fut = ex.submit(pega, nomes[i + 1])
                if not caminho:
                    _PARAR.set()
                    return None
                try:
                    if n in EMPRESAS:
                        capital.update(ler_empresas(caminho, basicos))
                    else:
                        estab.update(ler_estabelecimentos(caminho, alvo))
                except Exception as exc:
                    _aviso(f"{n} ilegivel ({exc!r})")
                    _PARAR.set()
                    return None
                finally:
                    caminho.unlink(missing_ok=True)
                print(f"Empresas (Receita): {n} lido ({time.monotonic() - t0:.0f}s).")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = {}
    for c in alvo:
        es, cap = estab.get(c), capital.get(c[:8])
        if es is None and cap is None:
            continue
        es = es or {}
        out[c] = dict(cnae=es.get("cnae"), cnae_desc=cnaes.get(es.get("cnae") or ""), inicio=es.get("inicio"),
                      capital=cap, situacao=es.get("situacao"))
    return out


def coletar(cnpjs, cache):
    """cnpjs: CNPJs (14 posicoes) das empresas declaradas. Devolve {cnpj: dict(cnae, cnae_desc, inicio 'AAAA-MM-DD',
    capital float, situacao)} so dos encontrados (campos podem ser None), mais "_fonte": True se todos os pedidos
    foram consultados na Receita (agora ou neste/noutro mes, pelo cache) e "_ref": 'AAAA-MM' dos dados.
    So reprocessa os arquivos da Receita quando muda o mes de referencia ou aparece CNPJ ainda nao procurado."""
    cache = Path(cache)
    arq = cache / "cnpj_receita.json"
    alvo = {c for c in map(limpa, cnpjs or ()) if c}
    salvo = _carregar(arq)
    ref, procurados, dados = salvo["ref"], salvo["procurados"], salvo["dados"]
    if alvo:
        mes = _mes()
        if mes and (mes[0] != ref or not alvo <= procurados):
            print(f"Empresas (Receita): varrendo o mes {mes[0]} para {len(alvo)} empresas...")
            try:
                novos = _varrer(mes[0], mes[1], alvo, cache)
            except Exception as ex:
                _aviso(f"varredura falhou ({ex!r})")
                novos = None
            if novos is not None:
                ref, procurados, dados = mes[0], set(alvo), novos
                _salvar(arq, ref, procurados, dados)
        elif mes is None and not dados:
            _aviso("sem listagem e sem cache")
    out = {c: dados[c] for c in alvo if c in dados}
    out["_fonte"] = bool(alvo) and alvo <= procurados
    out["_ref"] = ref
    print(f"Empresas (Receita): {len(alvo)} procuradas, {len(out) - 2} encontradas (referencia {ref or '-'}).")
    return out


# ---------- HTML ----------

def _brl(v):
    if v == int(v):
        return "R$ " + f"{v:,.0f}".replace(",", ".")
    return "R$ " + f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _cnae(c):
    c = str(c or "")
    return f"{c[:4]}-{c[4]}/{c[5:]}" if re.fullmatch(r"\d{7}", c) else c


def _nome(n):
    """Nome para exibir, sem qualquer sequencia que pareca CPF/CNPJ (MEI costuma levar o CPF na razao social)."""
    n = re.sub(r"\s+", " ", re.sub(r"[\d./-]{11,}", " ", str(n or ""))).strip(" -")
    return n or "Empresa declarada"


def _atividade(d):
    desc = (d.get("cnae_desc") or "").strip()
    if desc[1:2].islower():
        desc = desc[0].lower() + desc[1:]
    if desc and d.get("cnae"):
        return f"{e(desc)} (CNAE {e(_cnae(d['cnae']))})"
    if d.get("cnae"):
        return f"CNAE {e(_cnae(d['cnae']))}"
    return "Não informado"


def _fundada(inicio, ano_ini):
    if not inicio:
        return "Fundada em: Não informado"
    a, m = int(inicio[:4]), inicio[5:7]
    if a < ano_ini:
        rel = f"antes do início do período de {ano_ini}"
    elif a > ano_ini:
        rel = f"depois do início do período de {ano_ini}"
    else:
        rel = f"no ano de início do período, {ano_ini}"
    return f"Fundada em {m}/{a} ({rel})"


def secao(lista_empresas, dados, ano_ini):
    """HTML da subsecao 'Empresas declaradas' do dossie. lista_empresas: [(nome, cnpj)]; dados: saida de coletar().
    O CNPJ so serve de chave: nunca entra no HTML."""
    dados = dados or {}
    vistos, itens = set(), []
    for nome, c in lista_empresas or ():
        c = limpa(c)
        if c and c not in vistos:
            vistos.add(c)
            itens.append((nome, c))
    if not itens:
        return '<p class="vazio"><b>Não informado</b>: nenhuma empresa com CNPJ entre os bens declarados ao TSE.</p>'
    lis = []
    for nome, c in itens:
        d = dados.get(c)
        t = f"<b>{e(_nome(nome))}</b>"
        if d:
            v = d.get("capital")
            cap = _brl(v) if isinstance(v, (int, float)) and math.isfinite(v) else "Não informado"
            t += (f"<br>Atividade: {_atividade(d)}<br>{_fundada(d.get('inicio'), int(ano_ini))}"
                  f"<br>Capital social: {cap} · Situação: {e(d.get('situacao') or 'Não informado')}")
        elif dados.get("_fonte"):
            t += "<br><b>Não informado</b>: empresa não localizada nos dados abertos do CNPJ."
        else:
            t += "<br><b>Fonte não encontrada</b>: os dados abertos do CNPJ não responderam nesta execução."
        lis.append(f"<li>{t}</li>")
    ref = dados.get("_ref") or ""
    ref = f" (referência {ref[5:7]}/{ref[:4]})" if RE_MES.fullmatch(ref) else ""
    return (f'<ul class="nt">{"".join(lis)}</ul>'
            f'<p><small>Fonte: <a href="{e(LINK_FONTE)}" target="_blank" rel="noopener">dados abertos do CNPJ da '
            f'Receita Federal</a>{ref}. O faturamento das empresas não é público: estas informações são um ponto de '
            'partida para pesquisar, não uma conclusão.</small></p>')
