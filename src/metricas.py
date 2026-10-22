#!/usr/bin/env python3
"""Contagem de acessos ao site com o GoatCounter (https://www.goatcounter.com): sem cookies, sem guardar IP e sem
identificar quem visita. Ligada pela variavel GOATCOUNTER do repositorio (codigo da conta, ex.: "caramelo", ou o
endereco completo .../count de uma instalacao propria); vazia, nada muda.
Aplicada na publicacao (pages.yml) sobre a pasta pronta do site: poe o script em todas as paginas e a secao
"Contagem de acessos" na pagina de privacidade.
Uso: python src/metricas.py <pasta do site>"""
import os, re, sys
from pathlib import Path

SCRIPT = "https://gc.zgo.at/count.js"
MARCA = "<!--metricas-->"  # ja aplicado: nao duplica
SECAO = "<!--METRICAS-->"  # lugar da secao em privacidade.html


def endpoint(valor):
    """URL de contagem a partir do codigo da conta ou do endereco completo; None se vazio ou invalido."""
    v = (valor or "").strip()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,48}[a-z0-9]", v):
        return f"https://{v}.goatcounter.com/count"
    if re.fullmatch(r"https://[A-Za-z0-9.-]+(?::\d+)?/count", v):
        return v
    return None


def trecho(url):
    return f'{MARCA}<script data-goatcounter="{url}" async src="{SCRIPT}"></script>'


TEXTO = """<h2>Contagem de acessos</h2>
<p>Para saber quantas pessoas usam o site e quais páginas são mais vistas, cada visita é contada pelo <a href="https://www.goatcounter.com">GoatCounter</a>, serviço de estatística sem anúncios. Não há cookies nem identificação de quem visita: o endereço IP não é guardado e só servem para gerar totais a página aberta, o site de onde a visita veio, o navegador, o sistema, o tamanho da tela e o país (art. 7º, IX, e art. 10).</p>"""


def aplicar(pasta, valor):
    """Poe o contador antes de </head> em cada .html da pasta e a secao na pagina de privacidade.
    Devolve quantas paginas receberam o contador (0 quando GOATCOUNTER esta vazio ou invalido)."""
    url = endpoint(valor)
    n = 0
    for f in sorted(Path(pasta).rglob("*.html")):
        html = f.read_text(encoding="utf-8")
        novo = html.replace(SECAO, TEXTO if url else "")
        if url and MARCA not in novo and "</head>" in novo:
            novo = novo.replace("</head>", trecho(url) + "\n</head>", 1)
            n += 1
        if novo != html:
            f.write_text(novo, encoding="utf-8")
    return n


if __name__ == "__main__":
    valor = os.getenv("GOATCOUNTER", "")
    if valor.strip() and not endpoint(valor):
        print("[aviso] GOATCOUNTER invalido (use o codigo da conta ou https://.../count): contagem desligada",
              file=sys.stderr)
    print(f"Contagem de acessos: {aplicar(sys.argv[1], valor)} pagina(s).")
