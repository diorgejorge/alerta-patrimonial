"""Empresas declaradas x dados abertos do CNPJ (Receita) com arquivos sinteticos no layout oficial, sem rede."""
import json, re, sys, zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import empresas  # noqa: E402
import cifra  # noqa: E402

A = "12345678000190"          # pedida, matriz
A_FILIAL = "12345678000270"   # mesma raiz, nao pedida
B = "98765432000155"          # existe na Receita, nao pedida
C = "11222333000181"          # pedida, nao existe na Receita
MEI = "55666777000199"        # pedida; razao social de MEI costuma trazer CPF


def _q(campos):
    return ";".join(f'"{c}"' for c in campos)


def _estab(cnpj, sit, ini, cnae):
    campos = [cnpj[:8], cnpj[8:12], cnpj[12:], "1", "FANTASIA", sit, "20200101", "00", "", "", ini, cnae,
              "4711301", "RUA", "DAS FLORES", "10", "", "CENTRO", "01001000", "SP", "7107", "11", "33334444",
              "", "", "", "", "contato@exemplo.com.br", "", ""]
    assert len(campos) == 30
    return _q(campos)


def _zip(dest, linhas, nome="K3241.K03200Y0.D61010.CSV"):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(nome, ("\n".join(linhas) + "\n").encode("latin-1"))
    return dest


ARQUIVOS = {
    "Cnaes.zip": [_q(["0151201", "Criação de bovinos para corte"]), _q(["4711301", "Comércio varejista de mercadorias"])],
    "Empresas0.zip": [_q([A[:8], "AGRO BOA VISTA LTDA", "2062", "49", "2000000,00", "05", ""]),
                      _q([B[:8], "OUTRA SA", "2054", "10", "5000,50", "03", ""])],
    "Empresas7.zip": [_q([MEI[:8], "FULANO DE TAL 12345678909", "2135", "50", "1234,56", "01", ""])],
    "Estabelecimentos3.zip": [_estab(A, "02", "20190315", "0151201"), _estab(A_FILIAL, "08", "20000101", "4711301"),
                              _estab(B, "02", "19990101", "4711301")],
    "Estabelecimentos8.zip": [_estab(MEI, "04", "20120610", "151201")],  # CNAE sem zero a esquerda
}


@pytest.fixture
def receita(monkeypatch):
    """Simula a Receita: listagem do mes e downloads geram os zips sinteticos; conta quantos grandes foram baixados."""
    chamadas = {"grandes": 0, "falhar": None}
    monkeypatch.setenv("ID_SEGREDO", "segredo-de-teste")  # o cache so e gravado cifrado (cifra.py)
    monkeypatch.setattr(empresas, "_mes", lambda: ("2026-10", {n: 1 for n in empresas.NECESSARIOS}))

    def baixar(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        return _zip(dest, ARQUIVOS["Cnaes.zip"], "F.K03200$Z.D61010.CNAECSV")

    def grande(url, tamanho, dest):
        n = url.rsplit("/", 1)[-1]
        assert "/2026-10/" in url and n in empresas.NECESSARIOS
        chamadas["grandes"] += 1
        if n == chamadas["falhar"]:
            return None
        enchimento = (_q(["00000001", "Y", "1", "1", "0,00", "01", ""]) if n.startswith("Empresas")
                      else _estab("00000001000100", "02", "20000101", "4711301"))
        return _zip(dest, ARQUIVOS.get(n, []) + [enchimento])
    monkeypatch.setattr(empresas, "baixar", baixar)
    monkeypatch.setattr(empresas, "_baixar_grande", grande)
    return chamadas


def test_coleta_filtra_e_usa_cache(tmp_path, receita, capsys):
    r = empresas.coletar({A, "11.222.333/0001-81", MEI}, tmp_path)
    assert r["_fonte"] is True and r["_ref"] == "2026-10"
    assert set(r) - {"_fonte", "_ref"} == {A, MEI}  # so os pedidos e existentes
    assert r[A] == dict(cnae="0151201", cnae_desc="Criação de bovinos para corte", inicio="2019-03-15",
                        capital=2000000.0, situacao="ativa")
    assert r[MEI]["cnae"] == "0151201" and r[MEI]["situacao"] == "inapta" and r[MEI]["capital"] == 1234.56
    assert receita["grandes"] == 20
    bruto = (tmp_path / "cnpj_receita.json").read_bytes()
    assert bruto[:4] == cifra.MAGIA and A.encode() not in bruto  # cifrado: nenhum CNPJ legivel no arquivo
    salvo = json.loads(cifra.ler(tmp_path / "cnpj_receita.json"))
    assert salvo["ref"] == "2026-10" and set(salvo["dados"]) == {A, MEI}
    assert B not in json.dumps(salvo) and A_FILIAL not in json.dumps(salvo)
    assert "contato@" not in json.dumps(salvo)  # contato/endereco nunca sao guardados
    # mesmo mes, mesmos CNPJs: nao baixa nada de novo
    r2 = empresas.coletar({A, C, MEI}, tmp_path)
    assert receita["grandes"] == 20 and r2[A] == r[A] and r2["_fonte"] is True
    # CNPJ novo no mesmo mes: varre de novo
    r3 = empresas.coletar({A, B}, tmp_path)
    assert receita["grandes"] == 40 and r3[B]["capital"] == 5000.5
    log = capsys.readouterr()
    for c in (A, B, C, MEI, A[:8], B[:8]):
        assert c not in log.out + log.err  # CNPJ nunca vai para o log


def test_secao_sem_cnpj(tmp_path, receita):
    r = empresas.coletar({A, C, MEI}, tmp_path)
    lista = [("AGRO BOA VISTA LTDA", A), ("EMPRESA SUMIDA LTDA", C), ("FULANO DE TAL 123.456.789-09", MEI), ("X", "abc")]
    h = empresas.secao(lista, r, 2018)
    assert h.startswith('<ul class="nt"><li>') and h.count("<li>") == 3
    assert "AGRO BOA VISTA LTDA" in h
    assert "Atividade: criação de bovinos para corte (CNAE 0151-2/01)" in h
    assert "Fundada em 03/2019 (depois do início do período de 2018)" in h
    assert "Capital social: R$ 2.000.000 · Situação: ativa" in h
    assert "Capital social: R$ 1.234,56 · Situação: inapta" in h
    assert "Fundada em 06/2012 (antes do início do período de 2018)" in h
    assert "Não informado" in h and "Fonte não encontrada" not in h
    assert empresas.LINK_FONTE in h and "referência 10/2026" in h
    assert "ponto de partida para pesquisar" in h
    digitos = re.sub(r"\D", "", re.sub(r"<[^>]+>", "", h))
    for c in (A, C, MEI, "12345678909"):
        assert c not in digitos  # nem CNPJ nem o CPF da razao social do MEI
    assert "12.345.678" not in h and "123.456.789" not in h
    assert "no ano de início do período, 2019" in empresas.secao([("AGRO", A)], r, 2019)


def test_fonte_fora_do_ar(tmp_path, monkeypatch):
    monkeypatch.setattr(empresas, "_mes", lambda: None)
    r = empresas.coletar({A}, tmp_path)
    assert r["_fonte"] is False and A not in r
    h = empresas.secao([("AGRO BOA VISTA LTDA", A)], r, 2018)
    assert "Fonte não encontrada" in h and A not in h


def test_falha_no_meio_nao_grava_cache(tmp_path, receita):
    receita["falhar"] = "Estabelecimentos5.zip"
    r = empresas.coletar({A}, tmp_path)
    assert r["_fonte"] is False and A not in r
    assert not (tmp_path / "cnpj_receita.json").exists()
    assert "Fonte não encontrada" in empresas.secao([("AGRO", A)], r, 2018)


def test_campos_faltando_e_vazio():
    d = {A: dict(cnae=None, cnae_desc=None, inicio=None, capital=None, situacao=None), "_fonte": True, "_ref": None}
    h = empresas.secao([("AGRO", A)], d, 2018)
    assert "Atividade: Não informado" in h and "Fundada em: Não informado" in h
    assert "Capital social: Não informado · Situação: Não informado" in h
    assert "Não informado" in empresas.secao([], d, 2018)


def test_limpa():
    assert empresas.limpa("12.345.678/0001-90") == A
    assert empresas.limpa(2345678000190) == "02345678000190"
    assert empresas.limpa("12ABC34501DE35") == "12ABC34501DE35"  # CNPJ alfanumerico
    assert empresas.limpa("123") == "" and empresas.limpa(None) == ""
