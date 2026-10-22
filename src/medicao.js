/* Caramelo Vasculha: Google Analytics 4 so depois do "Aceitar" no aviso (LGPD, art. 7o, I, e art. 8o).
   Sem escolha ou com "Recusar", nada do Google e carregado. A escolha fica so neste navegador (localStorage).
   O id vem de config/analytics.json (paginas.medicao troca __GA_ID__ ao publicar). */
(function () {
  var ID = "__GA_ID__", CHAVE = "cv-medicao", eu = document.currentScript;
  var base = eu ? new URL(".", eu.src).href : "";

  function ler() { try { return localStorage.getItem(CHAVE); } catch (x) { return null; } }
  function gravar(v) { try { localStorage.setItem(CHAVE, v); } catch (x) { /* navegador sem armazenamento: vale so nesta pagina */ } }

  function carregar() {
    if (window.gtag) return;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    // so medicao de acesso: anuncios, personalizacao e sinais do Google ficam desligados
    window.gtag("consent", "default", { ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied",
                                        analytics_storage: "granted" });
    window.gtag("js", new Date());
    window.gtag("config", ID, { allow_google_signals: false, allow_ad_personalization_signals: false });
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(ID);
    document.head.appendChild(s);
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
      + 'Isso usa cookies e envia ao Google dados da sua navegação, sem anúncios. Recusar não muda nada no site. '
      + '<a href="' + base + 'privacidade.html#metricas">Saiba mais</a>.</p>'
      + '<div class="consentimento-acoes"><button type="button" class="botao" data-v="aceito">Aceitar</button>'
      + '<button type="button" class="botao secundario" data-v="recusado">Recusar</button></div>';
    d.addEventListener("click", function (ev) {
      var v = ev.target.getAttribute && ev.target.getAttribute("data-v");
      if (!v) return;
      var antes = ler();
      gravar(v);
      d.remove();
      if (v === "aceito") carregar();
      else if (antes === "aceito") { apagarCookies(); location.reload(); }  // recarrega para o GA parar de vez
    });
    document.body.appendChild(d);
  }

  function iniciar() {
    var v = ler();
    if (v === "aceito") carregar();
    else if (v !== "recusado") aviso();
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
