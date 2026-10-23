"""Dados incrementais (#48): anos fechados reaproveitados, ano atual sempre recalculado, sem rede."""
import datetime as dt, json, sys
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
import cache, pipeline  # noqa: E402

ATUAL = 2026


def serie():
    s = pipeline.serie_demo()
    s.loc[s["ano"] == 2022, "eleito"] = True
    s3 = s[s["ano"] == 2022].copy()
    s3["ano"], s3["patrimonio"], s3["eleito"] = ATUAL, s3["patrimonio"] * 1.7, False
    return pd.concat([s, s3], ignore_index=True)


def config():
    p = json.loads((RAIZ / "config" / "parametros.json").read_text())
    return pd.read_csv(RAIZ / "config" / "renda_publica.csv"), p


def ordenado(df):
    return df.sort_values(["chave", "ano_ini", "ano_fim"]).reset_index(drop=True)


def test_pares_com_cache_igual_ao_calculo_completo(tmp_path, monkeypatch):
    regras, p = config()
    s = serie()
    completo = ordenado(pipeline.pares(s, regras, {}, p))
    c = cache.Cache(tmp_path / "pares.cache", 400 * 86400, "segredo-de-teste")
    primeira = ordenado(pipeline.pares(s, regras, {}, p, cache=c, ano_atual=ATUAL))
    pd.testing.assert_frame_equal(primeira, completo)
    # segunda execucao: os periodos ate 2022 vem do cache; so os que chegam ao ano atual sao montados
    chamados = []
    original = pipeline._lista_pares
    monkeypatch.setattr(pipeline, "_lista_pares", lambda *a, **k: chamados.append(k.get("so_fim")) or original(*a, **k))
    c2 = cache.Cache(tmp_path / "pares.cache", 400 * 86400, "segredo-de-teste")
    segunda = ordenado(pipeline.pares(s, regras, {}, p, cache=c2, ano_atual=ATUAL))
    pd.testing.assert_frame_equal(segunda, completo)
    assert chamados == [ATUAL]
    # mudou um ano passado (outra assinatura): os periodos antigos sao montados de novo
    s2 = s.copy()
    s2.loc[s2["ano"] == 2018, "patrimonio"] *= 2
    chamados.clear()
    pipeline.pares(s2, regras, {}, p, cache=c2, ano_atual=ATUAL)
    assert chamados == [None, ATUAL]


def test_ano_fechado():
    assert cache.ano_fechado(2024, dt.date(2026, 1, 10))
    assert not cache.ano_fechado(2025, dt.date(2026, 3, 31))  # carencia: lancamentos de dezembro chegam ate marco
    assert cache.ano_fechado(2025, dt.date(2026, 4, 1))
    assert not cache.ano_fechado(2026, dt.date(2026, 10, 23))


def test_resultados_sem_segredo_nao_grava(tmp_path, monkeypatch):
    monkeypatch.delenv("ID_SEGREDO", raising=False)
    assert cache.resultados(tmp_path, "x", 60) is None


# ---------------------------------------------------------------- resumo por ano fechado (sha256 + versao da leitura)
import io, zipfile  # noqa: E402
import cifra, cota, projetos  # noqa: E402

CPF = "12345678909"
CAB_COTA = '"cpf";"ideCadastro";"nuDeputadoId";"numAno";"txtDescricao";"vlrLiquido"\n'


def zip_cota(ano, valor, data=(2026, 1, 1, 0, 0, 0)):
    """Zip da Camara com um lancamento; `data` muda so a data interna do zip (mesmo conteudo)."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(zipfile.ZipInfo(f"Ano-{ano}.csv", data),
                   CAB_COTA + f'"{CPF}";"204554";"1";"{ano}";"PASSAGEM";"{valor}"\n')
    return b.getvalue()


def test_sha_conteudo_ignora_data_do_zip_e_ve_mudanca():
    assert cache.sha_conteudo(zip_cota(2024, 10)) == cache.sha_conteudo(zip_cota(2024, 10, (2026, 10, 23, 7, 0, 0)))
    assert cache.sha_conteudo(zip_cota(2024, 10)) != cache.sha_conteudo(zip_cota(2024, 11))
    assert cache.sha_conteudo(b"a", b"b") != cache.sha_conteudo(b"b", b"a")


def test_resumo_fechado_cache_igual_relido_fora(tmp_path):
    g = cache.Cache(tmp_path / "r.cache", 400 * 86400, "segredo-de-teste")
    lidos, fonte = [], {"b": b"v1"}
    ler = lambda b: lidos.append(b) or b.decode()
    baixar = lambda: fonte["b"]
    assert cache.resumo_fechado(g, (1, "x", 2024), baixar, ler, agora=0) == ("v1", "relido")
    # dentro da janela: nem baixa
    assert cache.resumo_fechado(g, (1, "x", 2024), lambda: 1 / 0, ler, agora=10) == ("v1", "cache")
    # janela vencida, conteudo igual: reaproveitado sem reler
    assert cache.resumo_fechado(g, (1, "x", 2024), baixar, ler, conferir_s=5, agora=20) == ("v1", "igual")
    # fonte corrigiu o ano: relido e guardado de novo
    fonte["b"] = b"v2"
    assert cache.resumo_fechado(g, (1, "x", 2024), baixar, ler, conferir_s=5, agora=30) == ("v2", "relido")
    assert lidos == [b"v1", b"v2"]
    # fonte fora do ar: ultimo resumo guardado
    assert cache.resumo_fechado(g, (1, "x", 2024), lambda: None, ler, conferir_s=5, agora=40) == ("v2", "fora")
    # outra versao da leitura: o resumo antigo nao serve
    assert cache.resumo_fechado(g, (2, "x", 2024), lambda: None, ler, agora=40) == (None, None)
    # resumo no formato antigo (sem sha): lido de novo
    g.set((1, "y", 2024), {"cpf": [CPF]})
    assert cache.resumo_fechado(g, (1, "y", 2024), baixar, ler, agora=50) == ("v2", "relido")


def test_baixar_sem_destino_nao_guarda_bruto(tmp_path, monkeypatch):
    class Resp(io.BytesIO):
        headers = {"Last-Modified": "Fri, 23 Oct 2026 07:00:00 GMT"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(cifra.urllib.request, "urlopen", lambda *a, **k: Resp(b"dados"))
    monkeypatch.chdir(tmp_path)
    assert cifra.baixar("https://exemplo/x.csv", None, seg="seg") == b"dados"
    assert list(tmp_path.iterdir()) == []


def _execucao(monkeypatch):
    """Simula uma nova execucao do pipeline: le os resumos do disco de novo."""
    cache.salvar_resultados()
    monkeypatch.setattr(cache, "_POR_NOME", {})
    monkeypatch.setattr(cota, "_BASES", {})


def test_cota_ano_passado_reaproveitado_atual_relido_mudado_relido(tmp_path, monkeypatch):
    monkeypatch.setenv("ID_SEGREDO", "segredo-de-teste")
    monkeypatch.setattr(cache, "_POR_NOME", {})
    monkeypatch.setattr(cota, "_BASES", {})
    atual = dt.date.today().year
    passado, valores, pedidos, lidos = atual - 2, {atual - 2: 100, atual: 50}, [], []

    def baixar(url, dest):
        if "senado" in url:
            return None
        ano = int(url.split("-")[-1][:4])
        pedidos.append((ano, dest is None))
        return zip_cota(ano, valores[ano])
    ler_original = cota.ler_camara
    monkeypatch.setattr(cota, "baixar", baixar)
    monkeypatch.setattr(cota, "ler_camara", lambda b: lidos.append(1) or ler_original(b))
    anos = [passado, atual]
    total = lambda: float(cota.bases(anos, tmp_path)[0]["valor"].sum())

    assert total() == 150 and pedidos == [(passado, True), (atual, False)] and len(lidos) == 2
    assert not (tmp_path / f"ceap_camara_{passado}.zip").exists()  # bruto do ano fechado nao e guardado
    _execucao(monkeypatch)
    assert (tmp_path / "cota_anos.cache").read_bytes()[:4] == b"APC1"  # resumo cifrado
    assert CPF.encode() not in (tmp_path / "cota_anos.cache").read_bytes()

    # execucao seguinte: ano passado do resumo (sem baixar nem reler); ano atual sempre relido
    pedidos.clear(), lidos.clear()
    valores[atual] = 60
    assert total() == 160 and pedidos == [(atual, False)] and len(lidos) == 1
    _execucao(monkeypatch)

    # hora de conferir: mesmo conteudo -> nao rele; conteudo mudado (correcao da fonte) -> rele e atualiza
    monkeypatch.setattr(cache, "CONFERIR_S", -1)
    pedidos.clear(), lidos.clear()
    assert total() == 160 and pedidos == [(passado, True), (atual, False)] and len(lidos) == 1
    _execucao(monkeypatch)
    valores[passado] = 130
    lidos.clear()
    assert total() == 190 and len(lidos) == 2
    _execucao(monkeypatch)

    # mudou a leitura (versao): resumo antigo nao e reaproveitado
    monkeypatch.setattr(cache, "CONFERIR_S", 30 * 86400)
    monkeypatch.setattr(cota, "VERSAO_COTA", cota.VERSAO_COTA + 1)
    lidos.clear()
    assert total() == 190 and len(lidos) == 2


def test_projetos_camara_ano_passado_reaproveitado(tmp_path, monkeypatch):
    monkeypatch.setenv("ID_SEGREDO", "segredo-de-teste")
    monkeypatch.setattr(cache, "_POR_NOME", {})
    atual = dt.date.today().year
    passado = atual - 1
    sit = {passado: "Aguardando Parecer", atual: "Aguardando Parecer"}
    pedidos = []

    def baixar(url, dest):
        ano = int(url.rsplit("-", 1)[-1][:4])
        pedidos.append((ano, dest is None))
        if "Autores" in url:
            return f'"idProposicao";"idDeputadoAutor"\n"{ano}";"204554"\n'.encode()
        return f'"id";"siglaTipo";"ultimoStatus_descricaoSituacao"\n"{ano}";"PL";"{sit[ano]}"\n'.encode()
    monkeypatch.setattr(projetos, "baixar", baixar)
    anos = [passado, atual]

    assert projetos.contar_camara(anos, tmp_path) == {"204554": (2, 0)}
    assert sorted(pedidos) == [(passado, True), (passado, True), (atual, False), (atual, False)]
    cache.salvar_resultados()
    monkeypatch.setattr(cache, "_POR_NOME", {})
    pedidos.clear()
    assert projetos.contar_camara(anos, tmp_path) == {"204554": (2, 0)}
    assert all(a == atual for a, _ in pedidos)  # ano passado nao foi baixado de novo
    # 30 dias depois: o projeto antigo virou lei (CSV mudou) -> ano passado relido
    cache.salvar_resultados()
    monkeypatch.setattr(cache, "_POR_NOME", {})
    monkeypatch.setattr(cache, "CONFERIR_S", -1)
    sit[passado] = "Transformado em Norma Jurídica"
    assert projetos.contar_camara(anos, tmp_path) == {"204554": (2, 1)}
