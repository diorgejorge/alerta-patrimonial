"""Identificador interno estavel por pessoa, sem CPF.
A chave da pessoa (cpf:... ou nn:NOME|NASCIMENTO) passa por HMAC-SHA256 com o segredo ID_SEGREDO;
so o HMAC e gravado (data/ids.json), mapeado para um codigo curto sequencial (p0001, p0002...).
Sem o segredo nao ha como gerar ids seguros: hash simples de CPF e reversivel por forca bruta."""
import hashlib, hmac, json, re
from pathlib import Path


def digest(chave, segredo):
    return hmac.new(segredo.encode(), str(chave).encode(), hashlib.sha256).hexdigest()[:24]


class Ids:
    def __init__(self, arquivo, segredo):
        self.arquivo, self.segredo = Path(arquivo), segredo
        try:
            self.mapa = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
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
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps(self.mapa, indent=0, sort_keys=True), encoding="utf-8")
