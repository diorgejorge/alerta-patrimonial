"""Identificador interno estavel por pessoa, sem CPF.
A chave da pessoa (cpf:... ou nn:NOME|NASCIMENTO) passa por HMAC-SHA256 com o segredo ID_SEGREDO;
so o HMAC e gravado (data/ids.json, cifrado com cifra.py), mapeado para um codigo curto sequencial (p0001, p0002...).
Sem o segredo nao ha como gerar ids seguros: hash simples de CPF e reversivel por forca bruta."""
import hashlib, hmac, json, re
import cifra
from pathlib import Path


def digest(chave, segredo):
    return hmac.new(segredo.encode(), str(chave).encode(), hashlib.sha256).hexdigest()[:24]


# CPF e CNPJ formatados ou mascarados ("***.123.456-**"), em qualquer texto que va para o site
# (?<!\.) no CNPJ sem pontuacao: 14 digitos logo apos um ponto sao casas decimais (ex.: -49.12345678901234)
RE_DOC = re.compile(r"(?<![\d*])(?:[\d*]{3}\.[\d*]{3}\.[\d*]{3}-[\d*]{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|(?<!\.)\d{14})(?![\d*])")
OMITIDO = "[documento omitido]"


def sem_documentos(texto):
    return RE_DOC.sub(OMITIDO, texto)


def varrer(pasta, cpfs=()):
    """Ultima barreira antes de publicar: troca CPF/CNPJ formatados (e os CPFs conhecidos, sem formato)
    em todos os .html/.json/.txt da pasta. Devolve quantos arquivos foram corrigidos."""
    # CPF conhecido sem formato: so como numero inteiro, nunca dentro de outro numero ou de casas decimais
    nus = (re.compile(r"(?<![\d.])(?:" + "|".join(sorted({re.escape(c) for c in cpfs if len(c) == 11})) + r")(?!\d)")
           if any(len(c) == 11 for c in cpfs) else None)
    n = 0
    for p in Path(pasta).rglob("*"):
        if p.suffix not in (".html", ".json", ".txt") or not p.is_file():
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        novo = sem_documentos(txt)
        if nus:
            novo = nus.sub(OMITIDO, novo)
        if novo != txt:
            p.write_text(novo, encoding="utf-8")
            n += 1
    return n


class Ids:
    def __init__(self, arquivo, segredo):
        self.arquivo, self.segredo = Path(arquivo), segredo
        try:  # cifrado (cifra.py); o arquivo antigo em texto puro e lido uma vez e regravado cifrado em salvar()
            self.mapa = json.loads(cifra.ler(self.arquivo, segredo, aceitar_puro=True) or b"{}")
        except ValueError:
            self.mapa = {}
        nums = [int(v[1:]) for v in self.mapa.values() if re.fullmatch(r"p\d+", v)]
        self.proximo = max(nums, default=0) + 1

    def __call__(self, chave):
        """Codigo da pessoa; cria um novo na primeira vez que ela aparece."""
        h = digest(chave, self.segredo)
        if h not in self.mapa:
            self.mapa[h] = f"p{self.proximo:04d}"
            self.proximo += 1
        return self.mapa[h]

    def salvar(self):
        cifra.gravar(self.arquivo, json.dumps(self.mapa, indent=0, sort_keys=True).encode(), self.segredo)
