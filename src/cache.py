"""Cache incremental entre execucoes em data/cache (guardado pelo actions/cache, fora do git). Cada item tem validade.
O arquivo inteiro vai cifrado e assinado (cifra.py, chave derivada do ID_SEGREDO), e as chaves dos itens sao HMAC
(sem nome nem CPF). Arquivo alterado, corrompido ou de outro segredo: cache vazio, nada quebra."""
import gzip, hashlib, hmac, pickle, sys, time
from pathlib import Path
import cifra


class Cache:
    def __init__(self, arq, validade_s, segredo, cifrar=True):  # `cifrar` mantido por compatibilidade: sempre cifra
        self.arq, self.validade, self.segredo = Path(arq), validade_s, segredo
        self.k_id = hmac.new(str(segredo).encode(), b"cache:id", hashlib.sha256).digest()
        self.itens, self.mudou = self._ler(), False

    def _id(self, k):
        return hmac.new(self.k_id, str(k).encode(), hashlib.sha256).hexdigest()[:32]

    def _ler(self):
        b = cifra.ler(self.arq, self.segredo)  # so desserializa depois de conferir a assinatura
        if b is None:
            return {}
        try:
            itens = pickle.loads(gzip.decompress(b))
            agora = time.time()
            return {k: v for k, v in itens.items() if agora - v[0] < self.validade}
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
            cifra.gravar(self.arq, gzip.compress(pickle.dumps(dict(self.itens))), self.segredo)
            self.mudou = False
        except Exception as ex:
            print(f"[aviso] cache {self.arq.name} nao gravado ({ex!r})", file=sys.stderr)
