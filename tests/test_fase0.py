"""Fase 0: paginas por pessoa com dados sinteticos (--demo), sem rede.
Roda o pipeline dentro do processo com o socket bloqueado e confere privacidade, ids e paginas."""
import html.parser, json, re, socket, sys
from pathlib import Path
import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))


class SemRede(socket.socket):
    def connect(self, *a, **k):
        raise OSError("rede bloqueada nos testes")


def rodar(saida, monkeypatch, **env):
    import pipeline
    monkeypatch.setattr(socket, "socket", SemRede)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError("sem rede")))
    for k in ("ID_SEGREDO", "MONITORADOS_CSV", "TRANSPARENCIA_TOKEN", "TELEGRAM_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "--demo", "--saida", str(saida)])
    pipeline.main()
    return pipeline


@pytest.fixture
def saida(tmp_path, monkeypatch):
    rodar(tmp_path, monkeypatch, ID_SEGREDO="segredo-de-teste")
    return tmp_path


def arquivos(raiz):
    return [p for p in Path(raiz).rglob("*") if p.is_file()]


def test_nenhum_cpf_publicado(saida):
    import pipeline
    cpfs = {pipeline.cpf_ficticio(i) for i in range(0, 400, 2)}
    formatos = set()
    for c in cpfs:
        formatos |= {c, f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"}
    for p in arquivos(saida):
        texto = p.read_text(encoding="utf-8", errors="ignore")
        achados = [f for f in formatos if f in texto]
        assert not achados, f"CPF em {p.relative_to(saida)}"
        assert "cpf:" not in texto, f"chave com CPF em {p.relative_to(saida)}"


def test_ids_internos(saida):
    import cifra
    assert all(p.read_bytes()[:4] == cifra.MAGIA for p in (saida / "data").glob("*.json"))  # salvos cifrados
    mapa = json.loads(cifra.ler(saida / "data" / "ids.json", "segredo-de-teste"))
    assert mapa and all(re.fullmatch(r"[0-9a-f]{24}", k) for k in mapa)
    assert all(re.fullmatch(r"p\d{4}", v) for v in mapa.values())
    assert len(set(mapa.values())) == len(mapa)
    paginas = sorted(p.name for p in (saida / "docs" / "pessoa").glob("*.html"))
    assert paginas and all(re.fullmatch(r"p\d{4}\.html", n) for n in paginas)
    estado = json.loads(cifra.ler(saida / "data" / "estado.json", "segredo-de-teste"))
    assert estado and all(re.match(r"p\d{4}\|\d{4}-\d{4}$", k) for k in estado)


def test_ids_estaveis(tmp_path, monkeypatch):
    rodar(tmp_path, monkeypatch, ID_SEGREDO="s1")
    import cifra
    antes = json.loads(cifra.ler(tmp_path / "data" / "ids.json", "s1"))
    rodar(tmp_path, monkeypatch, ID_SEGREDO="s1")
    assert json.loads(cifra.ler(tmp_path / "data" / "ids.json", "s1")) == antes


class Verificador(html.parser.HTMLParser):
    VAZIOS = {"meta", "link", "br", "img", "input", "hr", "source", "wbr", "path", "rect", "circle", "line",
              "polyline", "stop", "use"}

    def __init__(self):
        super().__init__()
        self.pilha, self.erros = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VAZIOS:
            self.pilha.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.VAZIOS:
            return
        if tag in self.pilha:
            while self.pilha and self.pilha.pop() != tag:
                pass
        else:
            self.erros.append(tag)


def test_paginas_da_pessoa(saida):
    paginas = list((saida / "docs" / "pessoa").glob("*.html"))
    for p in paginas:
        texto = p.read_text(encoding="utf-8")
        assert len(texto.encode()) < 500_000, f"{p.name} passa de 500 KB"
        assert not re.search(r"__[A-Z]+__", texto), f"marcador sem preencher em {p.name}"
        for aba in ("Resumo", "Patrimônio", "Notícias", "Dinheiro público", "Propostas × PLs"):
            assert aba in texto
        v = Verificador()
        v.feed(texto)
        assert not v.erros, f"tags fechadas sem abrir em {p.name}: {v.erros[:5]}"
        assert 'lang="pt-BR"' in texto and 'name="viewport"' in texto


def test_painel(saida):
    texto = (saida / "docs" / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<!--(CARTOES|GRAFICO_[A-Z]+)-->", texto)
    assert (saida / "docs" / "estilo.css").exists()
    dados = json.loads(re.search(r"^const D=(.*);$", texto, re.M).group(1))
    assert all(a.get("pagina", "").startswith("pessoa/p") for a in dados["alertas"])
    assert not any("chave" in a or "empresas_cnpj" in a for a in dados["alertas"])


def test_trava_com_lista(tmp_path, monkeypatch):
    rodar(tmp_path, monkeypatch, ID_SEGREDO="s1", MONITORADOS_CSV="nome,cpf,renda_extra_mensal\nPESSOA DEMO 001,,0\n")
    texto = (tmp_path / "docs" / "index.html").read_text(encoding="utf-8")
    dados = json.loads(re.search(r"^const D=(.*);$", texto, re.M).group(1))
    assert {a["nome"] for a in dados["alertas"]} <= {"PESSOA DEMO 001"}
    assert len(list((tmp_path / "docs" / "pessoa").glob("*.html"))) <= 1


def test_sem_documentos_formatados(saida):
    from ids import RE_DOC
    for p in arquivos(saida / "docs"):
        if p.suffix in (".html", ".json", ".txt"):
            assert not RE_DOC.search(p.read_text(encoding="utf-8", errors="ignore")), f"CPF/CNPJ em {p.name}"


def test_limpeza_de_documentos():
    from ids import sem_documentos, OMITIDO
    t = "CPF 123.456.789-09, mascarado ***.456.789-**, CNPJ 12.345.678/0001-95 e 12345678000195"
    assert sem_documentos(t).count(OMITIDO) == 4
    # casas decimais longas nao sao CNPJ (quebravam o JSON do painel: "razao": -49.[documento omitido])
    assert sem_documentos('{"razao": -49.12345678901234, "cap": 243093.59999999998}') == \
        '{"razao": -49.12345678901234, "cap": 243093.59999999998}'
    assert sem_documentos("ano 2022, eleicao 20322002026, valor R$ 1.234.567,89") == \
        "ano 2022, eleicao 20322002026, valor R$ 1.234.567,89"


def test_varrer_preserva_decimais_e_json(tmp_path):
    from ids import varrer, OMITIDO
    import pipeline
    cpf = "12345678909"
    dados = pipeline.arredonda({"razao": -49.123456789012345, "x": [1.0000000001234567], "cpf_solto": int(cpf)})
    assert dados["razao"] == -49.1235 and dados["x"] == [1.0]
    p = tmp_path / "index.html"
    p.write_text("const D=" + json.dumps({"razao": -49.12345678909123, "n": dados["cpf_solto"]}) + ";", encoding="utf-8")
    varrer(tmp_path, cpfs=[cpf])
    texto = p.read_text(encoding="utf-8")
    assert "-49.12345678909123" in texto  # CPF dentro das casas decimais: intocado
    assert texto.count(OMITIDO) == 1      # o CPF solto continua sendo removido
