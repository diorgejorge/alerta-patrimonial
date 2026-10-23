/* Selo de cera (#52): carimba cada .selo-cera uma vez, quando ele entra na tela, inclusive os criados depois
   (cards em lotes, listas sob demanda). Sem IntersectionObserver ou com "menos movimento", o selo aparece parado. */
(function () {
  var raiz = document.documentElement;
  if (!("IntersectionObserver" in window) || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  raiz.classList.add("js-carimbo");
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (!e.isIntersecting) return;
      e.target.classList.add("carimbado");
      io.unobserve(e.target);
    });
  }, { threshold: 0.6 });
  function olhar(n) {
    if (n.nodeType !== 1) return;
    if (n.matches(".selo-cera:not(.carimbado)")) io.observe(n);
    n.querySelectorAll(".selo-cera:not(.carimbado)").forEach(function (s) { io.observe(s); });
  }
  new MutationObserver(function (ms) {
    ms.forEach(function (m) { m.addedNodes.forEach(olhar); });
  }).observe(document.body, { childList: true, subtree: true });
  olhar(document.body);
})();
