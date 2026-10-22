# Alerta patrimonial: documento de referência

Base de consulta do projeto: o que existe, como funciona, o que foi decidido e o que falta.
Atualizado em 22/10/2026. Repositório: `github.com/diorgejorge/alerta-patrimonial`. Site: `diorgejorge.github.io/alerta-patrimonial`.

---

## 1. O que o projeto faz

Compara, para cada pessoa candidata ou eleita, o patrimônio declarado ao TSE entre duas eleições com:
1. o que ela **poderia juntar com o salário** do cargo (subsídio × 12 × anos × taxa de poupança de 30% + renda extra informada);
2. os **colegas** (mesmo cargo e período), pelo percentil do crescimento.

O resultado é um **indício para acompanhamento, nunca prova**. Ele é publicado como site estático no GitHub Pages:
- **painel**: indicadores, gráficos, cartões das pessoas e tabela filtrável;
- **página por pessoa** (`docs/pessoa/<id>.html`);
- **dossiê antigo de notícias** (`docs/dossie/<nome-uf>.html`);
- **página de privacidade**.

## 2. Arquivos

| Arquivo | Papel |
|---|---|
| `src/pipeline.py` | Orquestra tudo. Baixa TSE, calcula alertas, chama Portal, notícias e páginas, grava `docs/` e `data/`. |
| `src/ids.py` | Id interno `p0001…` (HMAC-SHA256 com `ID_SEGREDO`), `sem_documentos()` e `varrer()` (tiram CPF/CNPJ de tudo que é publicado). |
| `src/paginas.py` | Página por pessoa, cartões e gráficos do painel, página de privacidade e leitores das fases futuras (`propostas.jsonl`, `vinculos.csv`). |
| `src/graficos.py` | Gráficos SVG sem JS: níveis, patrimônio, minigráfico e notícias por tema, cada um com tabela alternativa. |
| `src/transparencia.py` | Portal da Transparência **só pela API oficial**: emendas, documentos de pagamento, pessoa física, pessoa jurídica e recursos recebidos. Gera a seção "Dinheiro público". |
| `src/dossie.py` | Notícias (Google Notícias RSS e fontes sugeridas), filtro de menção direta e empresas extraídas dos bens. Gera `docs/dossie/`. |
| `src/template.html` | Painel (JS: busca, filtros por nível, partido e UF, gráficos interativos de partido e UF, "Como ler a tabela"). |
| `src/pessoa.html` | Página da pessoa: abas Resumo, Patrimônio, Notícias, Dinheiro público e Propostas × PLs. |
| `src/privacidade.html` | Página da LGPD, preenchida com `config/privacidade.json`. |
| `src/estilo.css` | Estilo comum: celular primeiro, tema claro/escuro, impressão e classes dos gráficos. |
| `src/dossie.html` | Modelo do dossiê antigo de notícias. |
| `config/parametros.json` | Anos, taxa de poupança, limiares, `publicar_somente_monitorados`, `max_linhas_sem_lista` (200). |
| `config/renda_publica.csv` | Subsídio mensal por cargo e vigência. **Conferir os valores.** |
| `config/monitorados.csv` | Lista pública vazia. **Não pôr CPF aqui**; use o segredo `MONITORADOS_CSV`. |
| `config/fontes_noticias.csv` | Fontes de notícias aprovadas pelo site (`nome,feed,uf,issue`). |
| `config/privacidade.json` | Controlador, contato, encarregado e data. **Preencher antes de divulgar.** |
| `data/estado.json` | Memória de alertas "novos", com chave `p0001\|2018-2022`. |
| `data/ids.json` | HMAC → id interno. Não permite recuperar o CPF sem o segredo. |
| `tests/` | `test_fase0.py` (pipeline `--demo`, rede bloqueada) e `test_graficos.py`. |

## 3. Fluxo de uma atualização

1. **TSE**: baixa `consulta_cand_<ano>.zip` e `bem_candidato_<ano>.zip` (CDN `cdn.tse.jus.br/estatistica/sead/odsele`).
   - Chave da pessoa: `cpf:<CPF>`. Se o CPF vier mascarado, `nn:<NOME>|<NASCIMENTO>`.
2. **Pares de eleições**: calcula crescimento, capacidade, razão ("quantas vezes o possível"), percentil e nível.
   - **Forte**: razão ≥ 3 e percentil ≥ 95.
   - **Atenção**: razão ≥ 2 e percentil ≥ 90, ou percentil ≥ 98.
   - **Informativo**: percentil ≥ 95.
   - Só entram crescimentos de pelo menos R$ 100 mil.
3. **Quem aparece**: com `MONITORADOS_CSV`, só os monitorados. Sem ele, os 200 maiores alertas (modo atual, escolhido pelo usuário).
4. **Id interno** por pessoa (`ID_SEGREDO`). Sem o segredo não há páginas por pessoa nem memória de "novos".
5. **Portal da Transparência (API)**: no máximo 45 min. Uma falha vira "Indisponível" e não derruba nada.
6. **Notícias** (Google e fontes aprovadas): no máximo 12 min. Só entram itens que citam a pessoa ou empresa ligada no título, no resumo ou no texto.
7. **Páginas**: dossiê de notícias, página da pessoa, painel (`index.html` + `blocos.json`), `estilo.css` e `privacidade.html`.
8. **Varredura final** (`varrer`): troca qualquer CPF ou CNPJ, formatado, mascarado ou conhecido, por "[documento omitido]".
9. `digest.txt` e, opcionalmente, Telegram.

## 4. Segredos e configuração (GitHub → Settings → Secrets and variables → Actions)

| Segredo | Para quê | Situação |
|---|---|---|
| `ID_SEGREDO` | Gera o id interno sem expor CPF. Texto aleatório longo; **não trocar depois** (os ids mudariam). | **Falta criar.** |
| `TRANSPARENCIA_TOKEN` | Chave da API do Portal (cadastro em `portaldatransparencia.gov.br/api-de-dados/cadastrar-email`). | Criado. |
| `MONITORADOS_CSV` | Lista `nome,cpf,renda_extra_mensal`, lida só em memória. | Opcional. Vazio = modo atual. |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | Resumo semanal. | Opcional. |

## 5. Workflows (`.github/workflows/`)

| Workflow | Quando | O que faz |
|---|---|---|
| `atualizar.yml` | Segunda 07:00 UTC (04:00 Brasília) e manual | Pipeline completo (~1 h). `python -u` para o andamento aparecer no log. Uma execução por vez, limite de 150 min. Grava `docs/` e `data/`. |
| `pages.yml` | Após "Atualizar alertas", push em `docs/`, `src/template.html` ou `src/estilo.css`, e manual | Remonta o `index.html` com o template atual + dados + `blocos.json` e publica. |
| `fontes.yml` | Rótulo `aprovada` numa issue "[Fonte de notícias]" | Testa o feed, grava em `config/fontes_noticias.csv` e responde e fecha a issue. |
| `testes.yml` | Push em `src/`, `tests/` ou `config/`, PR e manual | `pytest` (sem rede) e Lighthouse no celular (360 px). Acessibilidade ≥ 90 bloqueia; desempenho ≥ 90 só avisa. |
| `versao.yml` | Todo push na `main` | Cria a tag `vX.Y.Z` (patch +1, começa em `v0.1.0`) e uma release com a mensagem do commit. Commits do bot (`GITHUB_TOKEN`) não disparam workflows, então não geram versão. |

**Fluxo de trabalho:** cada solicitação vira uma issue no GitHub; o commit que a resolve cita `Closes #N` (ou `Refs #N`) e gera uma versão nova.

Execução manual: **Actions → Atualizar alertas → Run workflow**. **Não usar "Re-run"** de uma execução antiga, porque ela roda o código antigo.

## 6. Fontes: o que foi descoberto na prática

- **DivulgaCandContas (link da candidatura)**:
  - Formato: `…/divulga/#/candidato/{REGIAO}/{UF}/{ID_ELEICAO}/{SQ}/{ANO}/{SG_UE}`.
  - Regiões: `NORTE`, `NORDESTE`, `CENTROOESTE` (sem hífen), `SUDESTE`, `SUL`; `BR` para Presidente.
  - O `ID_ELEICAO` é o id interno do site, não o `CD_ELEICAO` do CSV: 2018 = 2022802018, 2020 = 2030402020, 2022 = 2040602022, 2024 = 2045202024, **2026 = 20322002026**, Macapá 2020 = 2032002020.
  - Anos novos precisam entrar em `ID_DIVULGA`.
- **Portal da Transparência**:
  - O **site** tem proteção anti-robô (AWS WAF, `x-amzn-waf-action: challenge`). Não contornar.
  - Usar só a **API**: `https://api.portaldatransparencia.gov.br/api-de-dados/<consulta>`, cabeçalho `chave-api-dados`, parâmetro `pagina`.
  - Limites: 90 consultas/min das 6h às 24h e 300/min da 0h às 6h. O robô ajusta o ritmo e trata HTTP 429.
  - `despesas/recursos-recebidos` recusa (HTTP 400) períodos maiores que um ano, por isso a consulta é ano a ano.
  - `/pessoa-fisica` indica por flags quais benefícios e sanções existem; só esses são detalhados.
  - Respostas 4xx não suspendem a API inteira.
- **Bing Notícias RSS**: removido em 21/10/2026 (issue #2). Nas execuções do GitHub Actions falhava quase sempre (11 de 13 buscas: "not well-formed (invalid token): line 1, column 41"), embora respondesse RSS válido fora do Actions.
- **Google Notícias RSS**: o link não leva à matéria sem JS. Itens do Google só valem com menção no título ou no resumo.
- **TSE**: o CSV de 2026 traz CPF. As empresas ligadas são extraídas da descrição dos bens ("quotas da empresa X LTDA"); bancos, cooperativas e ações de bolsa ficam de fora.

## 7. LGPD: regras aplicadas (Lei 13.709/2018, texto compilado do Planalto lido em 22/10/2026)

| Regra | Artigo | Como está no projeto |
|---|---|---|
| Dado público tratado conforme finalidade, boa-fé e interesse público da divulgação | art. 7º, § 3º | Base principal: dados que a lei manda o TSE e o Portal publicarem. |
| Nova finalidade compatível, com direitos preservados | art. 7º, § 7º | Controle social da evolução patrimonial. |
| Interesse legítimo, só dados estritamente necessários e com transparência | art. 7º, IX; art. 10, §§ 1º e 2º | Minimização (sem CPF/CNPJ; só metadados de notícias) e página de privacidade. |
| Dispensa de consentimento não afasta princípios e direitos | art. 7º, § 6º | Página de direitos e canal de contato. |
| Princípios: finalidade, necessidade, qualidade, transparência, segurança, não discriminação etc. | art. 6º | Mesmos critérios para todos; fonte e data em cada página; curadoria de homônimos. |
| Informações ao titular: finalidade, forma, duração, controlador, contato, compartilhamento, direitos | art. 9º | `docs/privacidade.html`. **Faltam controlador e contato** em `config/privacidade.json`. |
| **Dado sensível** (saúde, filiação política…) não pode usar interesse legítimo | arts. 5º, II, e 11 | **BPC fora** (pode revelar deficiência). **PETI fora** (crianças, art. 14). Nem são consultados. |
| Direitos do titular | art. 18 | Listados na página de privacidade, com canal de pedido. |
| Registro das operações | art. 37 | Seção 8 deste documento. |
| Encarregado com identidade e contato públicos | art. 41, § 1º | Campo em `config/privacidade.json`. **Preencher** ou verificar dispensa para agente de pequeno porte em norma da ANPD. |
| Segurança | art. 46 | Segredos no cofre do Actions, varredura automática de CPF/CNPJ, testes. |
| Isenção jornalística | art. 4º, II, "a" | Vale só para fins **exclusivamente** jornalísticos. **Não** é a base principal aqui. |

Pontos para revisão jurídica:
- **Partido** é "filiação a organização de caráter político" (art. 5º, II). Aqui ele vem da candidatura pública, publicada pelo TSE por lei, mas o enquadramento precisa ser confirmado.
- **Benefícios** como Bolsa Família não são dado sensível pela definição legal, mas expõem situação social. Avaliar se a exibição é proporcional.
- O texto da página de privacidade é um **rascunho técnico**.

## 8. Registro das operações de tratamento (art. 37)

| Operação | Dados | Fonte | Onde fica | Retenção |
|---|---|---|---|---|
| Coleta de candidaturas e bens | nome, nome de urna, CPF, nascimento, cargo, partido, UF, bens | TSE (dados abertos) | Cache só no executor do Actions (`data/cache/`, não versionado) | Durante a execução |
| Cálculo de alertas | valores declarados, cargo, período | derivado | `docs/index.html` (sem CPF) | Até a próxima atualização |
| Id interno | HMAC da chave | derivado | `data/ids.json` | Enquanto houver acompanhamento |
| Consulta ao Portal | CPF/CNPJ (em memória), emendas, benefícios, sanções, recursos | API do Portal | `docs/pessoa/`, `docs/dossie/` (sem CPF/CNPJ) | Até a próxima atualização |
| Notícias | título, veículo, data, link | Google, fontes aprovadas | `docs/dossie/` (fase 1: `data/noticias.jsonl`) | Enquanto houver acompanhamento |
| Sugestões de fontes | nome do veículo, URL, usuário do GitHub | Issues do repositório | GitHub | Conforme o GitHub |

## 9. Decisões já tomadas pelo usuário

- **Trava**: manter o modo atual (200 maiores) até criar `MONITORADOS_CSV`.
- **Dossiê antigo** (`docs/dossie/`): **não** substituir. Continua sendo gerado, e o painel mostra os links "Dossiê" (página nova) e "Notícias" (antigo).
- **Dinheiro público**: aba própria na página da pessoa.
- **Dependências**: Pillow (quando entrarem as fotos) e Lighthouse com Node no Actions estão liberados.
- **Portal da Transparência**: só pela API oficial, nada pelo site.
- **Falha da API**: mostrar "Indisponível".
- **CPF e CNPJ**: nunca visíveis.
- **Atualização**: automática, semanal.

## 10. Fases

- **Fase 0 (feita, ainda não executada com dados reais)**: id interno, página por pessoa com abas, painel com SVG e cartões, estilo responsivo, testes, Lighthouse, privacidade.
- **Fase 1, notícias com tags**:
  - `src/noticias.py`: RSS incremental, uma consulta por pessoa, deduplicação por URL canônica e título parecido, só metadados em `data/noticias.jsonl`.
  - `src/classificador.py`: tags fixas por regras de `config/tags.json`. Tags: político, eleitoral, legislativo, gestão, patrimonial, judicial, criminal, outros.
  - `config/curadoria.csv` (`url,id_pessoa,decisao,data`): homônimo e irrelevante não voltam; "criminal" só com `aprova_criminal`.
  - Na aba Notícias: cartões, chips e filtros por tag e período. Gráfico "notícias por tema" no painel (a função já existe).
- **Fase 2**: desambiguação das tags por modelo de linguagem (JSON validado, teto de chamadas, cache e chave como segredo). Campos previstos: `tags_regra`, `tags_modelo`, `origem_tag`.
- **Fase 3**: propostas do plano de governo (PDF do TSE, cargos do Executivo) em `data/propostas.jsonl`, com trecho literal, página e se depende de lei.
- **Fase 4**: proposições da Câmara e do Senado, sugestão de vínculos e só os aprovados em `config/vinculos.csv` (`status=aprovado`). Tramitação e cobertura, sem nota.
- **Fase 5**: atualização semanal de status; assembleias estaduais e câmaras municipais.
- **Fotos**: só de fontes oficiais, depois de confirmados os termos. WebP em 2 tamanhos, `loading=lazy`, texto alternativo e crédito. Até lá, avatar com iniciais.

## 11. Pendências abertas

1. **CPFs no histórico do git**: versões antigas de `data/estado.json` (commit `e249e44` e outros do bot) têm cerca de 1.173 CPFs num repositório **público**. O arquivo atual foi zerado. Apagar do histórico exige reescrita e force push (ação destrutiva), **só com autorização do usuário**. Depois, pedir ao suporte do GitHub a limpeza de cache.
2. **`/pessoa-fisica` na API**: falhou para 144 de 189 pessoas na execução #8. O código do erro está no log (`[aviso] API do Portal… /pessoa-fisica (…)`); falta o print para corrigir. Suspeita: limite próprio dessa consulta.
3. **Criar `ID_SEGREDO`** e **preencher `config/privacidade.json`** (controlador, contato, encarregado).
4. **Rótulo `aprovada`** nas issues (para o `fontes.yml`).
5. **Fase 0 sem execução real**: rodar "Atualizar alertas" e conferir o resultado do workflow "Testes" (pytest e Lighthouse).
6. **Qualidade dos dados**: casos extremos (ex.: 1º suplente com +R$ 272 mi, 407× o possível) parecem erro de dados. Conferir antes de divulgar.
7. **`renda_publica.csv`**: conferir os valores dos subsídios.
8. **Não há Python nem Node na máquina local**: testes só no Actions.

## 12. Ambiente local

- Pasta: `C:\Users\diorg\Downloads\alerta-patrimonial\alerta-patrimonial`. A pasta `alerta-patrimonial/` interna é um repositório antigo ignorado.
- O `git push` às vezes pede login (Git Credential Manager) ou dá 403 passageiro; tentar de novo resolve.
- O navegador do Claude não está logado no GitHub: logs completos do Actions só por print do usuário.
