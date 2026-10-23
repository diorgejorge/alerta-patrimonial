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


def ano_fechado(ano, hoje=None, carencia_mes=4):
    """Ano que nao muda mais na fonte: anterior ao atual. O ano anterior so fecha em `carencia_mes` (abril), porque
    lancamentos de dezembro (cota parlamentar) chegam ate marco (#48)."""
    import datetime as dt
    hoje = hoje or dt.date.today()
    return int(ano) < hoje.year - 1 or (int(ano) == hoje.year - 1 and hoje.month >= carencia_mes)


CONFERIR_S = 30 * 86400  # ano fechado: de quanto em quanto tempo baixa o arquivo para ver se a fonte o corrigiu


def sha_conteudo(*brutos):
    """sha256 do conteudo dos arquivos (bytes ou caminho), nunca da data do servidor (#48). Zip: dos arquivos de
    dentro (nome e dados), porque um zip regerado com os mesmos dados muda so as datas internas."""
    import io, zipfile
    h = hashlib.sha256()
    for b in brutos:
        b = bytes(b) if isinstance(b, (bytes, bytearray)) else Path(b).read_bytes()
        if b[:4] == b"PK\x03\x04":
            try:
                with zipfile.ZipFile(io.BytesIO(b)) as z:
                    for n in sorted(z.namelist()):
                        h.update(n.encode() + b"\0" + hashlib.sha256(z.read(n)).digest())
                continue
            except zipfile.BadZipFile:
                pass
        h.update(hashlib.sha256(b).digest())
    return h.hexdigest()


def resumo_fechado(guardados, chave, baixar, ler, conferir_s=None, agora=None):
    """Resumo de um ano fechado (#48), guardado cifrado em `guardados` (Cache). `chave` leva a versao da leitura (mudou
    a regra: resumo antigo nao serve). O resumo guarda o sha256 do conteudo de origem:
      - conferido ha menos de `conferir_s`: reaproveitado sem acessar a rede;
      - senao baixa (`baixar()` -> bytes ou tupla de bytes): conteudo igual -> reaproveitado sem reler; diferente
        (a fonte corrigiu o ano) -> relido com `ler(*brutos)` e guardado de novo;
      - fonte fora do ar: vale o ultimo resumo guardado.
    Devolve (resumo, origem) com origem em "cache", "igual", "relido" ou "fora"; (None, None) se nao ha nada."""
    conferir_s = CONFERIR_S if conferir_s is None else conferir_s
    agora = time.time() if agora is None else agora
    g = guardados.get(chave)
    if not (isinstance(g, dict) and {"sha", "conferido", "dados"} <= set(g)):
        g = None  # formato antigo ou ausente: le de novo
    if g and agora - g["conferido"] < conferir_s:
        return g["dados"], "cache"
    brutos = baixar()
    brutos = brutos if isinstance(brutos, tuple) else (brutos,)
    if not all(brutos):
        return (g["dados"], "fora") if g else (None, None)
    sha = sha_conteudo(*brutos)
    if g and g["sha"] == sha:
        guardados.set(chave, dict(g, conferido=agora))
        return g["dados"], "igual"
    dados = ler(*brutos)
    guardados.set(chave, dict(sha=sha, conferido=agora, dados=dados))
    return dados, "relido"


def resumo_log(fonte, origens):
    """Linha de log com a origem dos anos fechados (so contagens, sem dado pessoal)."""
    if origens:
        nomes = dict(cache="do cache sem baixar", igual="conferidos sem mudanca (nao relidos)",
                     relido="lidos e guardados", fora="do cache (fonte fora do ar)")
        print(f"{fonte}: anos fechados " + ", ".join(f"{n} {nomes[o]}" for o, n in sorted(origens.items())) + ".")


_POR_NOME = {}


def resultados(pasta, nome, validade_s):
    """Cache cifrado de resultados ja processados (ex.: resumo por ano fechado) em <pasta>/<nome>.cache, um por
    execucao; None sem ID_SEGREDO (nada e gravado). Gravado no fim por salvar_resultados()."""
    seg = cifra.segredo()
    if not seg:
        return None
    k = (str(Path(pasta).resolve()), nome)
    if k not in _POR_NOME:
        _POR_NOME[k] = Cache(Path(pasta) / f"{nome}.cache", validade_s, seg)
    return _POR_NOME[k]


def salvar_resultados():
    for c in _POR_NOME.values():
        c.salvar()
