/* Caramelo Vasculha: aviso de cookies do Google Analytics 4 (LGPD, art. 7o, I, e art. 8o).
   A tag do Google fica no <head> de cada pagina com o consentimento negado (modo de consentimento do Google):
   sem o "Aceitar", nenhum cookie e gravado. A escolha fica so neste navegador (localStorage), e a tag
   no <head> (paginas.medicao) le a mesma chave para liberar os cookies de quem ja aceitou. */
(function () {
  var CHAVE = "cv-medicao", eu = document.currentScript;
  var base = eu ? new URL(".", eu.src).href : "";

  function ler() { try { return localStorage.getItem(CHAVE); } catch (x) { return null; } }
  function gravar(v) { try { localStorage.setItem(CHAVE, v); } catch (x) { /* navegador sem armazenamento: vale so nesta pagina */ } }

  function permitir() {
    if (window.gtag) window.gtag("consent", "update", { analytics_storage: "granted" });
  }

  function apagarCookies() {  // _ga e _ga_<id>, em todos os dominios possiveis do endereco atual
    var partes = location.hostname.split(".");
    document.cookie.split(";").forEach(function (c) {
      var nome = c.split("=")[0].trim();
      if (!/^_ga/.test(nome)) return;
      document.cookie = nome + "=; Max-Age=0; path=/";
      for (var i = 0; i < partes.length; i++) {
        document.cookie = nome + "=; Max-Age=0; path=/; domain=." + partes.slice(i).join(".");
      }
    });
  }

  function aviso() {
    var velho = document.getElementById("consentimento");
    if (velho) velho.remove();
    var d = document.createElement("section");
    d.id = "consentimento";
    d.className = "consentimento";
    d.setAttribute("aria-label", "Cookies de métricas de acesso");
    d.innerHTML = '<p>🐾 O Caramelo quer contar quantas pessoas visitam o site, com o <strong>Google Analytics</strong>. '
      + 'Posso gravar os cookies de medição no seu navegador? Sem o seu aceite, nenhum cookie é gravado. '
      + 'Recusar não muda nada no site. <a href="' + base + 'privacidade.html#metricas">Saiba mais</a>.</p>'
      + '<div class="consentimento-acoes"><button type="button" class="botao" data-v="aceito">Aceitar</button>'
      + '<button type="button" class="botao secundario" data-v="recusado">Recusar</button></div>';
    d.addEventListener("click", function (ev) {
      var v = ev.target.getAttribute && ev.target.getAttribute("data-v");
      if (!v) return;
      var antes = ler();
      gravar(v);
      d.remove();
      if (v === "aceito") permitir();
      else if (antes === "aceito") { apagarCookies(); location.reload(); }  // recarrega para o GA voltar ao modo negado
    });
    document.body.appendChild(d);
  }

  function iniciar() {
    var v = ler();
    if (v !== "aceito" && v !== "recusado") aviso();
    // botao "Mudar minha escolha" da pagina de privacidade
    var bs = document.querySelectorAll("[data-medicao-preferencias]");
    for (var i = 0; i < bs.length; i++) {
      bs[i].hidden = false;
      bs[i].addEventListener("click", aviso);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
