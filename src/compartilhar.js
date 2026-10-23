/* Compartilhar (#61). Botao [data-compartilhar='{json}']: desenha o card numa imagem PNG 4:5 (canvas, no proprio
   navegador, sem biblioteca nem servico externo) e abre o compartilhamento do celular; sem ele, mostra a previa com
   "Baixar imagem", "Mandar no WhatsApp" e "Copiar link". [data-copiar-texto=id] copia o texto do campo. A imagem cita a fonte oficial dos dados, nunca o site como
   origem. Sem canvas ou sem JS, o botao fica escondido (estilo.css). */
(function () {
  var raiz = document.documentElement, W = 1080, H = 1350, M = 72;
  var FONTE = 'system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif';
  var lata = document.createElement("canvas");
  if (lata.getContext && lata.toBlob) raiz.classList.add("pode-compartilhar");
  if (navigator.clipboard || document.queryCommandSupported && document.queryCommandSupported("copy")) raiz.classList.add("pode-copiar");

  function iniciais(nome) {
    var ps = (nome.match(/[A-Za-zÀ-ÿ]+/g) || []).filter(function (w) { return w.length > 2; });
    if (!ps.length) return (nome.trim()[0] || "?").toUpperCase();
    return (ps[0][0] + (ps.length > 1 ? ps[ps.length - 1][0] : "")).toUpperCase();
  }

  // quebra o texto em linhas que cabem na largura; corta com reticencias depois de `max` linhas
  function linhas(ctx, txt, larg, max) {
    var out = [], atual = "";
    String(txt).split(/\s+/).forEach(function (p) {
      var t = atual ? atual + " " + p : p;
      if (ctx.measureText(t).width <= larg || !atual) atual = t; else { out.push(atual); atual = p; }
    });
    if (atual) out.push(atual);
    if (out.length > max) { out = out.slice(0, max); out[max - 1] = out[max - 1].replace(/\s*\S*$/, "") + "…"; }
    return out;
  }

  function escreve(ctx, txt, x, y, larg, tam, cor, peso, max) {
    ctx.font = (peso || "400") + " " + tam + "px " + FONTE;
    ctx.fillStyle = cor;
    var ls = linhas(ctx, txt, larg, max || 3);
    ls.forEach(function (l, i) { ctx.fillText(l, x, y + i * tam * 1.25); });
    return y + ls.length * tam * 1.25;
  }

  function caixa(ctx, x, y, w, h, r, fundo, borda) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
    if (fundo) { ctx.fillStyle = fundo; ctx.fill(); }
    if (borda) { ctx.strokeStyle = borda; ctx.lineWidth = 2; ctx.stroke(); }
  }

  // desenha o card: pessoa, numeros principais, aviso, fonte oficial e link para conferir
  function desenhar(d) {
    var c = document.createElement("canvas"), ctx = c.getContext("2d"), larg = W - 2 * M;
    c.width = W; c.height = H;
    var g = ctx.createLinearGradient(0, 0, W * 0.3, H);
    g.addColorStop(0, "#1f3a62"); g.addColorStop(0.45, "#1b2f4e"); g.addColorStop(1, "#111e34");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    var brilho = ctx.createRadialGradient(W * 0.9, H * 1.05, 0, W * 0.9, H * 1.05, W * 0.8);
    brilho.addColorStop(0, "rgba(196,122,53,.5)"); brilho.addColorStop(1, "rgba(196,122,53,0)");
    ctx.fillStyle = brilho; ctx.fillRect(0, 0, W, H);
    ctx.textBaseline = "alphabetic";

    escreve(ctx, "DADOS OFICIAIS", M, 120, larg, 32, "#f4b223", "800", 1);
    ctx.fillStyle = "#f4b223"; ctx.fillRect(M, 196, larg, 4);

    // pessoa: iniciais, nome, cargo · partido · UF
    ctx.fillStyle = "#c47a35"; ctx.beginPath(); ctx.arc(M + 66, 316, 66, 0, 2 * Math.PI); ctx.fill();
    ctx.font = "800 54px " + FONTE; ctx.fillStyle = "#fff"; ctx.textAlign = "center";
    ctx.fillText(iniciais(d.nome || "?"), M + 66, 335); ctx.textAlign = "left";
    var y = escreve(ctx, d.nome || "Não informado", M + 160, 300, larg - 160, 56, "#fff", "800", 2);
    y = escreve(ctx, d.ficha || "", M + 160, y + 4, larg - 160, 30, "rgba(245,236,220,.85)", "400", 2);
    y = Math.max(y, 400) + 24;

    // numeros: uma caixa de vidro por numero, valor em ouro
    (d.numeros || []).slice(0, 3).forEach(function (n) {
      caixa(ctx, M, y, larg, 160, 28, "rgba(255,255,255,.08)", "rgba(255,255,255,.18)");
      escreve(ctx, n[0], M + 36, y + 76, larg - 72, 60, "#f4b223", "800", 1);
      escreve(ctx, n[1], M + 36, y + 124, larg - 72, 30, "#fff", "400", 1);
      y += 184;
    });

    var pe = H - 196;
    escreve(ctx, "Não é acusação: é dado oficial. Confira na fonte.", M, Math.min(y + 30, pe - 60),
      larg, 28, "rgba(245,236,220,.85)", "400", 2);
    ctx.fillStyle = "rgba(255,255,255,.18)"; ctx.fillRect(M, pe, larg, 2);
    escreve(ctx, d.fontes || "", M, pe + 52, larg, 26, "rgba(245,236,220,.85)", "400", 1);
    escreve(ctx, "Confira em: " + (String(d.url || "").match(/^https?:\/\/([^/#?]+)/) || [, ""])[1], M, pe + 104, larg, 30, "#f4b223", "700", 1);
    return c;
  }

  function arquivo(d) {
    var nome = (d.nome || "card").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "card";
    return "card-" + nome + ".png";
  }

  function copiar(txt) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(txt);
    return new Promise(function (ok, erro) {
      var t = document.createElement("textarea");
      t.value = txt; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
      document.body.appendChild(t); t.select();
      var deu = document.execCommand("copy"); t.remove();
      deu ? ok() : erro(new Error("copia recusada"));
    });
  }

  // previa (computador ou navegador sem compartilhamento de arquivo): baixar, WhatsApp, copiar link
  function previa(d, blob) {
    var url = URL.createObjectURL(blob), msg = (d.nome || "") + ": " + d.url;
    var dlg = document.createElement("dialog");
    dlg.className = "compartilhar";
    dlg.setAttribute("aria-label", "Compartilhar o card de " + (d.nome || "pessoa"));
    dlg.innerHTML = '<img alt="">' +
      '<p class="compartilhar-acoes"><a class="botao" download></a> <a class="botao secundario" target="_blank" rel="noopener">Mandar no WhatsApp</a> ' +
      '<button type="button" class="botao secundario" data-link>Copiar link</button> ' +
      '<button type="button" class="botao secundario" data-fechar>Fechar</button></p><p class="compartilhar-aviso" role="status"></p>';
    var img = dlg.querySelector("img"), baixar = dlg.querySelector("a[download]"), zap = dlg.querySelector("a[target]");
    img.src = url;
    img.alt = "Prévia da imagem: " + (d.nome || "") + ", " + (d.numeros || []).map(function (n) { return n[0] + " " + n[1]; }).join("; ");
    baixar.href = url; baixar.download = arquivo(d); baixar.textContent = "Baixar imagem";
    zap.href = "https://wa.me/?text=" + encodeURIComponent(msg);
    dlg.addEventListener("click", function (ev) {
      if (ev.target === dlg || ev.target.closest("[data-fechar]")) dlg.close();
      if (ev.target.closest("[data-link]")) copiar(d.url).then(function () {
        dlg.querySelector("[role=status]").textContent = "Link copiado.";
      }, function () { dlg.querySelector("[role=status]").textContent = "Não deu para copiar: " + d.url; });
    });
    dlg.addEventListener("close", function () { URL.revokeObjectURL(url); dlg.remove(); });
    document.body.appendChild(dlg);
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
  }

  function compartilhar(bt) {
    var d;
    try { d = JSON.parse(bt.getAttribute("data-compartilhar")); } catch (e) { return; }
    bt.setAttribute("aria-busy", "true");
    desenhar(d).toBlob(function (blob) {
      bt.removeAttribute("aria-busy");
      if (!blob) return;
      var f = typeof File === "function" ? new File([blob], arquivo(d), { type: "image/png" }) : null;
      var dados = { files: [f], title: d.nome, text: (d.nome || "") + ": " + d.url };
      if (f && navigator.canShare && navigator.canShare({ files: [f] })) {
        navigator.share(dados).catch(function (e) { if (e && e.name !== "AbortError") previa(d, blob); });
      } else previa(d, blob);
    }, "image/png");
  }

  document.addEventListener("click", function (ev) {
    var bt = ev.target.closest("[data-compartilhar]");
    if (bt) { compartilhar(bt); return; }
    var cp = ev.target.closest("[data-copiar-texto]");  // texto sugerido da aba Como cobrar (#60)
    var campo = cp && document.getElementById(cp.getAttribute("data-copiar-texto"));
    if (!campo) return;
    var aviso = cp.parentNode.querySelector(".cobrar-aviso");
    copiar(campo.value).then(function () { if (aviso) aviso.textContent = "Texto copiado. É só colar no e-mail ou na mensagem."; },
      function () { campo.select(); if (aviso) aviso.textContent = "Não deu para copiar sozinho: o texto está selecionado, use Ctrl+C."; });
  });

  window.CarameloCompartilhar = { desenhar: desenhar, iniciais: iniciais };  // testes de interface
})();
