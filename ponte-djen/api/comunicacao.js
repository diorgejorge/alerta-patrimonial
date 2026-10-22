// Ponte para a API publica do DJEN (Diario de Justica Eletronico Nacional, CNJ), executada em Sao Paulo (gru1).
// A API do CNJ recusa (403) acessos de fora do Brasil, e os servidores do GitHub Actions ficam nos EUA.
// So repassa GET para /api/v1/comunicacao com os parametros que o alerta-patrimonial usa; nada mais passa.
const API = "https://comunicaapi.pje.jus.br/api/v1/comunicacao";
const PERMITIDOS = ["nomeParte", "pagina", "itensPorPagina"];

module.exports = async (req, res) => {
  if (req.method !== "GET") {
    res.status(405).json({ erro: "só GET" });
    return;
  }
  const q = new URLSearchParams();
  for (const k of PERMITIDOS) {
    const v = req.query[k];
    if (v !== undefined) q.set(k, String(Array.isArray(v) ? v[0] : v).slice(0, 200));
  }
  if (!q.get("nomeParte")) {
    res.status(400).json({ erro: "nomeParte é obrigatório" });
    return;
  }
  try {
    const r = await fetch(`${API}?${q}`, {
      headers: { "User-Agent": "alerta-patrimonial/1.0 (ponte gru1)", Accept: "application/json" },
    });
    res.status(r.status);
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", r.ok ? "s-maxage=86400" : "no-store"); // mesma consulta no dia: cache da Vercel
    res.send(await r.text());
  } catch (e) {
    res.status(502).json({ erro: "DJEN não respondeu" });
  }
};
