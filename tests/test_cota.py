"""Cota parlamentar (CEAP Camara / CEAPS Senado) com arquivos sinteticos, sem rede."""
import sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import cota  # noqa: E402

CPF = "12345678909"
CAB = ('"txNomeParlamentar";"cpf";"ideCadastro";"nuDeputadoId";"numAno";"txtDescricao";"vlrLiquido";"txtFornecedor";'
       '"txtCNPJCPF"\n')


def camara(pasta, ano):
    linhas = [f'"FULANO";"{CPF}";"204554";"3000";"{ano}";"PASSAGEM AÉREA - SIGEPA";"1500.50";"CIA X";"11.111.111/0001-11"',
              f'"FULANO";"{CPF}";"204554";"3000";"{ano}";"COMBUSTÍVEIS E LUBRIFICANTES.";"200";"POSTO Y";"22.222.222/0001-22"',
              f'"OUTRO";"98765432100";"1";"1";"{ano}";"PASSAGEM AÉREA - SIGEPA";"999";"CIA X";"11.111.111/0001-11"',
              f'"LID.GOV-CD";"";"";"2812";"{ano}";"MANUTENÇÃO";"10";"Z";"1"']
    z = pasta / f"ceap_camara_{ano}.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(f"Ano-{ano}.csv", ("﻿" + CAB + "\n".join(linhas) + "\n").encode("utf-8"))
    return z


def senado(pasta, ano):
    txt = ('"ULTIMA ATUALIZACAO";"20/10/2026 02:01"\n'
           '"ANO";"MES";"SENADOR";"TIPO_DESPESA";"CNPJ_CPF";"FORNECEDOR";"DOCUMENTO";"DATA";"DETALHAMENTO";'
           '"VALOR_REEMBOLSADO";"COD_DOCUMENTO"\n'
           f'"{ano}";"1";"BELTRANA";"Aluguel de imóveis para escritório político, compreendendo despesas concernentes a eles.";'
           '"1";"X";"1";"01/01/2025";"";"1.399,44";"1"\n')
    f = pasta / f"ceaps_senado_{ano}.csv"
    f.write_bytes(txt.encode("latin-1"))
    return f


def test_coleta_e_secao(tmp_path, monkeypatch):
    def baixar(url, dest):
        ano = int(url.split("-")[-1][:4]) if "camara" in url else int(url.rsplit("_", 1)[-1][:4])
        return camara(tmp_path, ano) if "camara" in url else senado(tmp_path, ano)
    monkeypatch.setattr(cota, "baixar", baixar)
    pessoas = {"dep": dict(nome="Fulano de Tal", nome_urna="Fulano", cargo=" DEPUTADO FEDERAL", cpf=CPF),
               "sen": dict(nome="Beltrana Silva", nome_urna="Beltrana", cargo=" SENADOR", cpf=""),
               "gov": dict(nome="Ciclano", nome_urna="", cargo=" GOVERNADOR", cpf="11122233344")}
    r = cota.coletar(pessoas, [2025, 2026], tmp_path)
    assert r["_fontes"] == {"camara": True, "senado": True}
    assert round(r["dep"]["total"], 2) == 2 * 1700.50 and r["dep"]["anos"] == [(2025, 1700.5), (2026, 1700.5)]
    assert r["dep"]["link"].endswith("/deputados/204554")
    assert r["sen"]["tipos"][0][0] == "Aluguel de imóveis para escritório político"
    assert round(r["sen"]["total"], 2) == 2 * 1399.44
    assert "gov" not in r
    h = cota.secao(r["dep"], pessoas["dep"]["cargo"], r["_fontes"])
    assert "R$ 3.401,00" in h and CPF not in h and "CIA X" not in h  # sem CPF e sem fornecedor
    assert "Não informado" in cota.secao(None, " GOVERNADOR", r["_fontes"])
    assert "Não informado" in cota.secao(None, " SENADOR", r["_fontes"])
    assert "Fonte não encontrada" in cota.secao(None, " SENADOR", {"camara": True, "senado": False})
