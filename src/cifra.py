"""Todo arquivo que o pipeline salva (data/ versionado e data/cache) fica cifrado e assinado com chave derivada do
ID_SEGREDO: fluxo SHAKE-256(chave, nonce) com XOR + HMAC-SHA256 sobre o conteudo cifrado (cifra-e-depois-assina).
Formato: MAGIA(4) + HMAC(32) + nonce(16) + dados cifrados. Arquivo de outro segredo ou alterado: ValueError.
Arquivos antigos em texto puro (de antes da cifra) sao lidos uma vez (`aceitar_puro`) e regravados cifrados.
Sem ID_SEGREDO nada e gravado: o pipeline usa so o que baixou nesta execucao."""
import hashlib, hmac, os, sys, urllib.error, urllib.request
from pathlib import Path

MAGIA = b"APC1"


def segredo():
    return os.environ.get("ID_SEGREDO") or None


def _chave(seg, uso):
    return hmac.new(str(seg).encode(), f"cifra:{uso}".encode(), hashlib.sha256).digest()


def _xor(dados, chave, nonce):
    n = len(dados)
    fluxo = hashlib.shake_256(chave + nonce).digest(n)
    return (int.from_bytes(dados, "big") ^ int.from_bytes(fluxo, "big")).to_bytes(n, "big")


def cifrar(dados, seg):
    nonce = os.urandom(16)
    corpo = _xor(bytes(dados), _chave(seg, "fluxo"), nonce)
    mac = hmac.new(_chave(seg, "mac"), MAGIA + nonce + corpo, hashlib.sha256).digest()
    return MAGIA + mac + nonce + corpo


def decifrar(b, seg):
    if b[:4] != MAGIA:
        raise ValueError("arquivo nao cifrado")
    mac, nonce, corpo = b[4:36], b[36:52], b[52:]
    if not hmac.compare_digest(mac, hmac.new(_chave(seg, "mac"), MAGIA + nonce + corpo, hashlib.sha256).digest()):
        raise ValueError("assinatura nao confere (outro segredo ou arquivo alterado)")
    return _xor(corpo, _chave(seg, "fluxo"), nonce)


def gravar(arq, dados, seg=None):
    """Grava `dados` (bytes) cifrados; sem segredo nao grava nada. Devolve True se gravou."""
    seg = seg or segredo()
    if not seg:
        return False
    arq = Path(arq)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_name(arq.name + ".parcial")
    tmp.write_bytes(cifrar(dados, seg))
    tmp.replace(arq)
    return True


def ler(arq, seg=None, aceitar_puro=False):
    """Bytes decifrados; None se nao existe, se nao ha segredo ou se nao confere. `aceitar_puro`: arquivo antigo em
    texto puro (sem MAGIA) e devolvido como esta, para ser regravado cifrado por quem chamou."""
    seg = seg or segredo()
    try:
        b = Path(arq).read_bytes()
    except OSError:
        return None
    if b[:4] != MAGIA:
        return b if aceitar_puro else None
    if not seg:
        return None
    try:
        return decifrar(b, seg)
    except ValueError as ex:
        print(f"[aviso] {Path(arq).name} descartado ({ex})", file=sys.stderr)
        return None


def baixar(url, dest, cab=None, timeout=300, perguntar=True, seg=None):
    """Conteudo de `url`, guardado cifrado em `dest`. Com copia guardada: `perguntar=False` usa a copia sem acessar a
    rede; senao pergunta ao servidor se mudou (If-Modified-Since, data guardada em dest.modificado, que nao e dado
    pessoal). `dest=None`: so baixa, sem guardar o bruto (ano fechado ja resumido, #48). Devolve bytes, ou None se
    nao baixou e nao ha copia."""
    if dest is None:
        dest = marca = guardado = None
    else:
        dest, marca = Path(dest), Path(str(dest) + ".modificado")
        guardado = ler(dest, seg)
    if guardado is not None and not perguntar:
        return guardado
    h = {"User-Agent": "alerta-patrimonial/1.0", **(cab or {})}
    if guardado is not None and marca.exists():
        h["If-Modified-Since"] = marca.read_text().strip()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
            partes = []
            while bloco := r.read(1 << 20):
                partes.append(bloco)
            dados = b"".join(partes)
            if dest is not None and gravar(dest, dados, seg) and r.headers.get("Last-Modified"):
                marca.write_text(r.headers["Last-Modified"])
            return dados
    except urllib.error.HTTPError as ex:
        if ex.code == 304 and guardado is not None:  # nao mudou desde a copia guardada
            return guardado
        print(f"[aviso] {url} indisponivel: {ex}", file=sys.stderr)
    except Exception as ex:
        print(f"[aviso] {url} indisponivel: {ex}", file=sys.stderr)
    return guardado


def limpar_puros(pasta):
    """Apaga do cache os arquivos antigos em texto puro (de antes da cifra); ficam so os cifrados e as datas
    (.modificado). Devolve quantos apagou."""
    n = 0
    for p in Path(pasta).rglob("*"):
        if not p.is_file() or p.name.endswith(".modificado"):
            continue
        with open(p, "rb") as f:
            if f.read(4) == MAGIA:
                continue
        p.unlink(missing_ok=True)
        n += 1
    if n:
        print(f"Cache: {n} arquivo(s) antigo(s) em texto puro apagado(s); serao baixados de novo e guardados cifrados.")
    return n
