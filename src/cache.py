"""Cache entre execucoes em data/cache (guardado pelo actions/cache, fora do git). Cada item tem validade.
O arquivo inteiro e assinado (HMAC-SHA256) e, com `cifrar=True`, cifrado (fluxo SHA-256 em modo contador) com chave
derivada do ID_SEGREDO: respostas da API do Portal ligadas ao CPF nunca ficam legiveis no cache, e as chaves dos
itens sao HMAC (sem nome nem CPF). Arquivo alterado, corrompido ou de outro segredo: cache vazio, nada quebra."""
import gzip, hashlib, hmac, os, pickle, sys, time
from pathlib import Path


def _chave(segredo, uso):
    return hmac.new(str(segredo).encode(), f"cache:{uso}".encode(), hashlib.sha256).digest()


def _xor(dados, chave, nonce):
    n = len(dados)
    return (int.from_bytes(dados, "big") ^ int.from_bytes(_fluxo(chave, nonce, n), "big")).to_bytes(n, "big")


def _fluxo(chave, nonce, n):
    out, i = bytearray(), 0
    while len(out) < n:
        out += hashlib.sha256(chave + nonce + i.to_bytes(8, "big")).digest()
        i += 1
    return bytes(out[:n])


class Cache:
    def __init__(self, arq, validade_s, segredo, cifrar=False):
        self.arq, self.validade, self.cifrar = Path(arq), validade_s, cifrar
        self.k_mac, self.k_cif, self.k_id = (_chave(segredo, "mac"), _chave(segredo, "cifra"), _chave(segredo, "id"))
        self.itens, self.mudou = self._ler(), False

    def _id(self, k):
        return hmac.new(self.k_id, str(k).encode(), hashlib.sha256).hexdigest()[:32]

    def _ler(self):
        try:
            b = self.arq.read_bytes()
            mac, nonce, corpo = b[:32], b[32:48], b[48:]
            if not hmac.compare_digest(mac, hmac.new(self.k_mac, nonce + corpo, hashlib.sha256).digest()):
                raise ValueError("assinatura nao confere")
            if self.cifrar:
                corpo = _xor(corpo, self.k_cif, nonce)
            itens = pickle.loads(gzip.decompress(corpo))  # so depois de conferir a assinatura
            agora = time.time()
            return {k: v for k, v in itens.items() if agora - v[0] < self.validade}
        except FileNotFoundError:
            return {}
        except Exception as ex:
            print(f"[aviso] cache {self.arq.name} descartado ({ex.__class__.__name__})", file=sys.stderr)
            return {}

    def get(self, k):
        v = self.itens.get(self._id(k))
        return None if v is None else v[1]

    def set(self, k, valor):
        self.itens[self._id(k)] = (time.time(), valor)
        self.mudou = True

    def salvar(self):
        """Grava o cache; nunca levanta erro (cache e so atalho: falhar aqui nao pode derrubar o pipeline)."""
        if not self.mudou:
            return
        try:
            corpo, nonce = gzip.compress(pickle.dumps(dict(self.itens))), os.urandom(16)
            if self.cifrar:
                corpo = _xor(corpo, self.k_cif, nonce)
            self.arq.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.arq.with_suffix(".parcial")
            tmp.write_bytes(hmac.new(self.k_mac, nonce + corpo, hashlib.sha256).digest() + nonce + corpo)
            tmp.replace(self.arq)
            self.mudou = False
        except Exception as ex:
            print(f"[aviso] cache {self.arq.name} nao gravado ({ex!r})", file=sys.stderr)
