# Ponte DJEN (Vercel, São Paulo)

A API pública do DJEN (CNJ) só aceita acessos de dentro do Brasil. Esta função roda na Vercel na região
`gru1` (São Paulo) e repassa ao DJEN só a busca de comunicações por nome (`nomeParte`, `pagina`,
`itensPorPagina`). O pipeline usa a ponte quando a variável `DJEN_API` do repositório aponta para ela.

Configuração (uma vez, no navegador):

1. Em vercel.com, entrar com o GitHub (plano Hobby, gratuito, uso não comercial).
2. **Add New → Project → Import** o repositório `alerta-patrimonial`.
3. Em **Root Directory**, escolher `ponte-djen`. Framework: **Other**. Deploy.
4. Copiar o endereço do projeto (ex.: `https://ponte-djen.vercel.app`).
5. No GitHub, a variável de repositório `DJEN_API` recebe
   `https://<endereço>/api/comunicacao` (Settings → Secrets and variables → Actions → Variables).

A Vercel só refaz o deploy quando algo muda nesta pasta (`ignoreCommand`).
