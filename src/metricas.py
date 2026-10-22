#!/usr/bin/env python3
"""Contagem de acessos ao site com o Google Analytics 4, so com consentimento (LGPD): cada pagina mostra um aviso com
"Aceitar" e "Recusar"; o Google Analytics so carrega (e so grava cookies) depois do "Aceitar". Sinais de anuncios e
Google Signals ficam desligados. A escolha fica no navegador (localStorage) e pode ser mudada na pagina de privacidade.
Ligada pela variavel GOOGLE_ANALYTICS do repositorio (ID de medicao, ex.: G-ABC123XYZ9); vazia, nada muda.
Aplicada na publicacao (pages.yml) sobre a pasta pronta do site: poe o aviso e o script em todas as paginas e a secao
"Contagem de acessos" na pagina de privacidade.
Uso: python src/metricas.py <pasta do site>"""
import os, re, sys
from pathlib import Path

MARCA = "<!--metricas-->"  # ja aplicado: nao duplica
SECAO = "<!--METRICAS-->"  # lugar da secao em privacidade.html
BOTAO = ("background:#fff;color:#111;border:2px solid #fff;border-radius:6px;padding:6px 16px;font:inherit;"
         "font-weight:600;cursor:pointer;margin:4px 8px 0 0")  # mesmo destaque para aceitar e recusar


def id_medicao(valor):
    """ID de medicao do GA4 (G-...) em maiusculas; None se vazio ou invalido."""
    v = (valor or "").strip().upper()
    return v if re.fullmatch(r"G-[A-Z0-9]{4,15}", v) else None


def trecho(ga, raiz=""):
    """Aviso de consentimento + carregamento do GA4 so depois do "Aceitar". `raiz`: caminho ate a raiz do site."""
    return f"""{MARCA}<div id="ga-aviso" role="region" aria-label="Aviso de contagem de acessos" hidden style="position:fixed;left:0;right:0;bottom:0;z-index:9999;background:#1b1b1b;color:#fff;padding:12px 16px;font-size:15px;line-height:1.4;box-shadow:0 -2px 8px rgba(0,0,0,.3)">
<p style="margin:0 0 4px">Este site usa o Google Analytics para contar visitas, só se você aceitar. <a href="{raiz}privacidade.html#acessos" style="color:#fff;text-decoration:underline">Saiba mais</a>.</p>
<button type="button" data-ga="sim" style="{BOTAO}">Aceitar</button><button type="button" data-ga="nao" style="{BOTAO}">Recusar</button>
</div>
<script>
(function(){{var ID="{ga}",K="ga-consentimento",av=document.getElementById("ga-aviso");
function ler(){{try{{return localStorage.getItem(K)}}catch(e){{return null}}}}
function gravar(v){{try{{localStorage.setItem(K,v)}}catch(e){{}}}}
function ligar(){{if(window.gtag)return;window.dataLayer=window.dataLayer||[];window.gtag=function(){{dataLayer.push(arguments)}};
gtag("consent","default",{{ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied",analytics_storage:"granted"}});
gtag("js",new Date());gtag("config",ID,{{allow_google_signals:false,allow_ad_personalization_signals:false}});
var s=document.createElement("script");s.async=true;s.src="https://www.googletagmanager.com/gtag/js?id="+ID;document.head.appendChild(s)}}
var v=ler();if(v==="sim")ligar();else if(v!=="nao")av.hidden=false;
av.addEventListener("click",function(ev){{var b=ev.target.closest("[data-ga]");if(!b)return;gravar(b.getAttribute("data-ga"));av.hidden=true;if(b.getAttribute("data-ga")==="sim")ligar()}});
window.gaMudarEscolha=function(){{try{{localStorage.removeItem(K)}}catch(e){{}}
document.cookie.split(";").forEach(function(c){{var n=c.split("=")[0].trim();if(n.indexOf("_ga")===0)["",location.hostname,"."+location.hostname].forEach(function(d){{document.cookie=n+"=; Max-Age=0; path=/"+(d?"; domain="+d:"")}})}});
location.reload()}};
}})();
</script>"""


TEXTO = """<h2 id="acessos">Contagem de acessos</h2>
<p>Para saber quantas pessoas usam o site e quais páginas são mais vistas, usamos o <a href="https://policies.google.com/technologies/partner-sites?hl=pt-BR">Google Analytics</a>, do Google, <strong>só se você aceitar</strong> no aviso que aparece na primeira visita (art. 7º, I, e art. 8º). Sem o aceite, nada é enviado ao Google e nenhum cookie é gravado.</p>
<ul>
<li><strong>O que é coletado:</strong> página aberta, site de origem, navegador, sistema, tamanho da tela, cidade ou país aproximados e um identificador aleatório guardado em cookie (<code>_ga</code>). O endereço IP não é guardado pelo Google Analytics.</li>
<li><strong>O que não é feito:</strong> não há anúncios, personalização de anúncios nem cruzamento com contas do Google (Google Signals desligado).</li>
<li><strong>Transferência internacional (art. 33):</strong> o Google pode processar esses dados fora do Brasil.</li>
<li><strong>Prazo:</strong> os dados de cada visitante são apagados pelo Google depois do prazo de retenção configurado na conta.</li>
</ul>
<p><button type="button" onclick="window.gaMudarEscolha&&gaMudarEscolha()">Mudar minha escolha sobre a contagem</button> (apaga os cookies do Google Analytics e mostra o aviso de novo).</p>"""


def aplicar(pasta, valor):
    """Poe o aviso e o GA4 antes de </body> em cada .html da pasta e a secao na pagina de privacidade.
    Devolve quantas paginas receberam o contador (0 quando GOOGLE_ANALYTICS esta vazio ou invalido)."""
    ga = id_medicao(valor)
    pasta = Path(pasta)
    n = 0
    for f in sorted(pasta.rglob("*.html")):
        html = f.read_text(encoding="utf-8")
        novo = html.replace(SECAO, TEXTO if ga else "")
        if ga and MARCA not in novo and "</body>" in novo:
            raiz = "../" * (len(f.relative_to(pasta).parts) - 1)  # pessoa/ e dossie/ ficam um nivel abaixo
            i = novo.rindex("</body>")
            novo = novo[:i] + trecho(ga, raiz) + "\n" + novo[i:]
            n += 1
        if novo != html:
            f.write_text(novo, encoding="utf-8")
    return n


if __name__ == "__main__":
    valor = os.getenv("GOOGLE_ANALYTICS", "")
    if valor.strip() and not id_medicao(valor):
        print("[aviso] GOOGLE_ANALYTICS invalido (use o ID de medicao G-...): contagem desligada", file=sys.stderr)
    print(f"Contagem de acessos: {aplicar(sys.argv[1], valor)} pagina(s).")
