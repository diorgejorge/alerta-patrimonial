# Alerta patrimonial: documento de referência

Base de consulta do projeto: o que existe, como funciona, o que foi decidido e o que falta.
Atualizado em 2026-10-22 (até a v0.1.42, issue #34). Repositório: `github.com/diorgejorge/alerta-patrimonial`. Site: `diorgejorge.github.io/alerta-patrimonial`, com o nome **"Patrimônio declarado em foco"** (desde 2026-10-22, #7).

---

## 1. O que o projeto faz

Compara, para cada pessoa candidata ou eleita, o patrimônio declarado ao TSE entre duas eleições com:
1. o que ela **poderia juntar com o salário** do cargo (subsídio × 12 × anos × taxa de poupança de 30% + renda extra informada);
2. os **colegas** (mesmo cargo e período), pelo percentil do crescimento.

O resultado é um **destaque para conhecer e pesquisar nas fontes oficiais, nunca prova nem acusação**. Ele é publicado como site estático no GitHub Pages:
- **painel**: indicadores, gráficos, cards das pessoas em destaque (24 por vez), tabela completa sob demanda, parlamentares exemplares e quem mais gastou da cota parlamentar;
- **página por pessoa** (`docs/pessoa/<id>.html`);
- **dossiê antigo de notícias** (`docs/dossie/<nome-uf>.html`), em cards;
- **página de privacidade**.

## 2. Arquivos

| Arquivo | Papel |
|---|---|
| `src/pipeline.py` | Orquestra tudo. Baixa TSE, calcula destaques, chama Portal, cota, Receita, notícias e páginas, grava `docs/` e `data/`. Números do painel saem com no máximo 4 casas decimais (`arredonda`, #27). |
| `src/ids.py` | Id interno `p0001…` (HMAC-SHA256 com `ID_SEGREDO`), `sem_documentos()` e `varrer()` (tiram CPF/CNPJ de tudo que é publicado). A varredura ignora dígitos logo depois de um ponto decimal (#27). |
| `src/paginas.py` | Página por pessoa, cartões e gráficos do painel, página de privacidade e leitores das fases futuras (`propostas.jsonl`, `vinculos.csv`). |
| `src/graficos.py` | Gráficos SVG sem JS: níveis, patrimônio, minigráfico e notícias por tema, cada um com tabela alternativa. |
| `src/transparencia.py` | Portal da Transparência **só pela API oficial**: emendas, documentos de pagamento, pessoa física, pessoa jurídica, recursos recebidos e sanções (CEIS, CNEP, CEAF). Gera a seção "Dinheiro público". |
| `src/dossie.py` | Notícias (Google Notícias RSS em português, Google News em inglês para a imprensa internacional e fontes sugeridas), filtro de menção direta, contagem de menções dos últimos 30 dias, empresas extraídas dos bens, processos da lista curada e link "Conferir processos". Gera `docs/dossie/`. |
| `src/cota.py` | Cota parlamentar (CEAP da Câmara e CEAPS do Senado, arquivos anuais abertos, últimos 4 anos), lida uma vez por execução. Deputado federal ligado pelo CPF do TSE (só internamente); senador pelo nome. Arquivos guardados em `data/cache` (If-Modified-Since). Leitor próprio para o CSV do Senado com aspas soltas (#31). |
| `src/exemplares.py` | Estrela de "parlamentar exemplar" (deputado federal e senador) no período mais recente, com os três critérios: crescimento dentro do que o salário permitiria, cota abaixo da média do cargo nos últimos 4 anos e nenhum registro no CEIS, CNEP ou CEAF. Sem dado para algum critério, não há estrela (#15). |
| `src/empresas.py` | Empresas declaradas: atividade (CNAE), início de atividade, capital social e situação nos dados abertos do CNPJ da Receita (WebDAV público do compartilhamento `YggdBLfdninEJX9`, ~7 GB por mês). Varre os arquivos só quando muda o mês de referência ou aparece CNPJ novo, em pasta temporária, e guarda só `data/cache/cnpj_receita.json`; limite de 75 min. O faturamento não é público, então o dossiê não afirma compatibilidade com o crescimento. O CNPJ nunca vai para o site (#13). |
| `src/cache.py` | Cache incremental entre execuções em `data/cache` (só com `ID_SEGREDO`, que assina e cifra): `tse_lido.cache` (cada ano já lido, até o zip do TSE mudar), `portal.cache` (cada pessoa por 7 dias, cifrado; só respostas sem falha) e `noticias.cache` (cada busca por 3 dias). Chaves são HMAC, sem nome nem CPF. Arquivo adulterado ou de outro segredo é descartado (#26). A cifra é a de `src/cifra.py` (#34). |
| `src/cifra.py` | **Tudo que o pipeline salva fica cifrado e assinado** (#34): fluxo SHAKE-256 com chave derivada do `ID_SEGREDO` (XOR) + HMAC-SHA256 sobre o cifrado; formato `APC1` (4) + HMAC (32) + nonce (16) + dados. Vale para `data/ids.json`, `data/estado.json` e todo o `data/cache` (zips do TSE, Câmara, Senado, Cnaes, `cnpj_receita.json`, caches portal/tse_lido/notícias). `baixar()` guarda a data do If-Modified-Since em `<arquivo>.modificado` (não é dado pessoal). Arquivo antigo em texto puro: ids e estado são lidos uma vez e regravados cifrados; os do cache são apagados (`limpar_puros`) e baixados de novo. Sem `ID_SEGREDO` nada é gravado. Outro segredo ou arquivo alterado: erro, o arquivo é descartado. |
| `src/template.html` | Painel (JS): busca; filtros por nível, cargo, partido, estado e região, todos como chip removível; cards com tags clicáveis (cargo, partido com bolinha da cor do partido, estado; escala do bege ao vermelho-escuro pela concentração de destaques), estrela de exemplar, "Tem empresas declaradas", "Responde a processo", menções na imprensa e link "Conferir processos"; legenda das tags como botões de filtro; gráfico de estados agrupado por região; tabela de exemplares; quem mais gastou da cota; tabela completa com coluna "Tags"; "Como ler a tabela". Blocos sem conteúdo ficam escondidos. |
| `src/pessoa.html` | Página da pessoa: abas Resumo, Patrimônio, Notícias, Dinheiro público e Propostas × PLs. |
| `src/privacidade.html` | Página da LGPD, preenchida com `config/privacidade.json`. |
| `src/estilo.css` | Estilo comum: celular primeiro, tema claro/escuro, impressão e classes dos gráficos. Paleta calma (índigo, verde-azulado, verde-sálvia; contraste AA nos dois temas). |
| `src/dossie.html` | Modelo do dossiê antigo de notícias (seções em cards; tabela de períodos vira lista no celular). |
| `config/parametros.json` | Anos, taxa de poupança, limiares, `publicar_somente_monitorados`, `max_linhas_sem_lista` (200). |
| `config/renda_publica.csv` | Subsídio mensal por cargo e vigência. **Conferir os valores.** |
| `config/monitorados.csv` | Lista pública vazia. **Não pôr CPF aqui**; use o segredo `MONITORADOS_CSV`. |
| `config/fontes_noticias.csv` | Fontes de notícias aprovadas pelo site (`nome,feed,uf,issue`). |
| `config/bens_referencia.json` | Bens de referência do "daria para comprar N …" (nome, preço, data, link oficial): carro popular, picape, casa do MCMV faixa 3, apartamento de 70 m² (FipeZAP) e bens fora do comum (ilha em Guaratuba, iate Azimut, Ilha dos Porcos Grandes). Atualizar os preços à mão; o painel republica sozinho ao mudar. |
| `config/processos.csv` | Processos em que a pessoa é ré (`nome,uf,tribunal,numero,link,issue,incluido_em`). Entram só por issue "[Processo]" aprovada (rótulo `aprovada`, workflow `processos.yml`); link só https de `*.jus.br`, Jusbrasil, Escavador ou Processo Rápido (o robô não abre o link). Remover a linha quando o processo terminar. **Não há contagem automática de processos** (#31). |
| `config/privacidade.json` | Controlador, contato, encarregado e data. **Preencher antes de divulgar.** |
| `data/estado.json` | Memória de destaques "novos", com chave `p0001\|2018-2022`. Cifrado (`src/cifra.py`, #34). |
| `data/ids.json` | HMAC → id interno. Não permite recuperar o CPF sem o segredo. Cifrado (`src/cifra.py`, #34). As cópias atuais no git ainda estão em texto puro até a próxima execução do pipeline regravá-las. |
| `.github/ISSUE_TEMPLATE/` | Formulários `fonte-noticias.yml`, `fonte-dados.yml` e `processo.yml` (pessoa, UF, tribunal, número e link, sem CPF). |
| `.github/scripts/` | `aprovar_fonte.py` e `aprovar_processo.py`: leem só campos conhecidos da issue e validam antes de gravar. |
| `.claude/agents/documentador.md` | Agente que atualiza este documento e a memória da sessão ao fim de cada ciclo (#33). |
| `tests/` | `test_fase0.py` (pipeline `--demo`, rede bloqueada, inclui o caso da varredura com casas decimais), `test_graficos.py`, `test_bens.py`, `test_cache.py`, `test_cifra.py`, `test_cota.py`, `test_empresas.py`, `test_exemplares.py`, `test_outras_rendas.py`, `test_processos.py`. |

## 3. Fluxo de uma atualização

1. **TSE**: baixa `consulta_cand_<ano>.zip` e `bem_candidato_<ano>.zip` (CDN `cdn.tse.jus.br/estatistica/sead/odsele`). Zips guardados cifrados em `data/cache`; só baixa de novo se o TSE disser que mudou (If-Modified-Since).
   - Chave da pessoa: `cpf:<CPF>`. Se o CPF vier mascarado, `nn:<NOME>|<NASCIMENTO>`.
2. **Pares de eleições**: calcula crescimento, capacidade, razão ("quantas vezes o possível"), percentil e nível. Nome interno → nome no site:
   - `forte` → **"Muito acima do esperado"**: razão ≥ 3 e percentil ≥ 95.
   - `atencao` → **"Acima do esperado"**: razão ≥ 2 e percentil ≥ 90, ou percentil ≥ 98.
   - `informativo` → **"Para conhecer"**: percentil ≥ 95.
   - Só entram crescimentos de pelo menos R$ 100 mil.
   - **Empresas declaradas** ao TSE no início ou no fim do período reduzem o nível um grau (o menor se mantém); o nível antes da redução fica em `nivel_calculado` e aparece na explicação (#10).
3. **Quem aparece**: com `MONITORADOS_CSV`, só os monitorados. Sem ele, os 200 maiores destaques (modo atual, escolhido pelo usuário).
4. **Id interno** por pessoa (`ID_SEGREDO`). Sem o segredo não há páginas por pessoa, cache incremental nem memória de "novos", e nada é gravado em `data/` (tudo que é salvo é cifrado com ele, #34).
5. **Portal da Transparência (API)**: no máximo 45 min. Uma falha vira "Fonte não encontrada" no site e não derruba nada.
6. **Cota parlamentar** (Câmara e Senado) e **exemplares** (estrela, com consulta de sanções ao Portal).
7. **Empresas (Receita)**: só para as empresas declaradas pelas pessoas em destaque.
8. **Notícias** (Google em português e em inglês, fontes aprovadas): no máximo 12 min. Só entram itens que citam a pessoa ou empresa ligada no título, no resumo ou no texto. As dos últimos 30 dias viram a contagem de menções.
9. **Ordem do painel**: primeiro quem tem mais menções na imprensa nos últimos 30 dias; depois, o maior crescimento (#11).
10. **Páginas**: dossiê de notícias, página da pessoa, painel (`index.html` + `blocos.json`), `estilo.css` e `privacidade.html`. Falha de conexão aparece como "Fonte não encontrada"; dado faltante, como "Não informado".
11. **Varredura final** (`varrer`): troca qualquer CPF ou CNPJ, formatado, mascarado ou conhecido, por "[documento omitido]".
12. `digest.txt` e, opcionalmente, Telegram.

## 4. Segredos e configuração (GitHub → Settings → Secrets and variables → Actions)

| Segredo | Para quê | Situação |
|---|---|---|
| `ID_SEGREDO` | Gera o id interno sem expor CPF e cifra/assina tudo que é salvo (`data/ids.json`, `data/estado.json`, `data/cache`, #34). Texto aleatório longo; **não trocar nem apagar** (ids, estado e cache ficariam ilegíveis e seriam perdidos). Sem ele nada é gravado. | Criado em 2026-10-22 (valor aleatório, não guardado fora do GitHub). |
| `TRANSPARENCIA_TOKEN` | Chave da API do Portal (cadastro em `portaldatransparencia.gov.br/api-de-dados/cadastrar-email`). | Criado (2026-10-21). |
| `MONITORADOS_CSV` | Lista `nome,cpf,renda_extra_mensal`, lida só em memória. | Opcional, não criado. Vazio = modo atual. |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | Resumo semanal. | Opcional, não criados. |

Não há variáveis de repositório (a `DJEN_API` da ponte na Vercel saiu junto com a ponte, #31).

**Rótulos de issue**: `aprovada` (revisão humana; dispara `fontes.yml` e `processos.yml`), `processo`, `fonte-noticias`, `fonte-dados`.

## 5. Workflows (`.github/workflows/`)

| Workflow | Quando | O que faz |
|---|---|---|
| `atualizar.yml` | Segunda 07:00 UTC (04:00 Brasília) e manual | Pipeline completo. `data/cache` guardado com `actions/cache` (chave `tse-<run_id>`, restaura a mais recente): zips do TSE, arquivos da cota, Receita e cache incremental. Notícias com 0,5 s entre buscas. `python -u` para o andamento aparecer no log. Uma execução por vez, limite de 150 min. Grava `docs/` e `data/`. A execução de 2026-10-22 04:26 UTC levou 31m48s, cerca de 16 min deles na primeira varredura da Receita. |
| `pages.yml` | Após "Atualizar alertas", push em `docs/`, `src/template.html`, `src/estilo.css` ou `config/bens_referencia.json`, e manual | Remonta o `index.html` com o template atual + dados + `blocos.json` e publica. |
| `fontes.yml` | Rótulo `aprovada` numa issue "[Fonte de notícias]" | Testa o feed, grava em `config/fontes_noticias.csv` e responde e fecha a issue. |
| `processos.yml` | Rótulo `aprovada` numa issue "[Processo]" | Valida número (padrão CNJ ou classe e número) e link, grava em `config/processos.csv`, responde e fecha a issue. |
| `testes.yml` | Push em `src/`, `tests/` ou `config/`, PR e manual | `pytest` (sem rede) e Lighthouse no celular (360 px). Acessibilidade ≥ 90 bloqueia; desempenho ≥ 90 só avisa. |
| `versao.yml` | Todo push na `main` | Cria a tag `vX.Y.Z` (patch +1, começou em `v0.1.0`) e uma release com a mensagem do commit. Vários commits num mesmo push geram uma versão só (no último). Commits do bot (`GITHUB_TOKEN`) não disparam workflows, então não geram versão. |

**Fluxo de trabalho** (desde 2026-10-22, #1 e #33): cada pedido do usuário vira uma issue no GitHub; o commit que a resolve cita `Closes #N` (ou `Refs #N`) e gera uma versão nova (tag e release pelo `versao.yml`). Ao fim de cada ciclo, o agente `documentador` atualiza este documento e a memória e faz um commit só de documentação.

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
  - Limites: 90 consultas/min das 6h às 24h e 300/min da 0h às 6h. O robô ajusta o ritmo, trata HTTP 429 e avisa no log quando roda fora da faixa 0h-6h.
  - `despesas/recursos-recebidos` recusa (HTTP 400) períodos maiores que um ano, por isso a consulta é ano a ano.
  - `/pessoa-fisica` indica por flags quais benefícios e sanções existem; só esses são detalhados.
  - Respostas 4xx não suspendem a API inteira.
  - Execução de 2026-10-22 04:26 UTC: 192 pessoas, 930 consultas, 1 falha; exemplares com 159 consultas e 0 falhas.
- **Bing Notícias RSS**: removido em 2026-10-22 (issue #2). Nas execuções do GitHub Actions falhava quase sempre (11 de 13 buscas: "not well-formed (invalid token): line 1, column 41"), embora respondesse RSS válido fora do Actions.
- **Google Notícias RSS**: o link não leva à matéria sem JS. Itens do Google só valem com menção no título ou no resumo. A busca em inglês (Google News) entra só na contagem de menções e no dossiê (#11).
- **TSE**: o CSV de 2026 traz CPF. As empresas ligadas são extraídas da descrição dos bens ("quotas da empresa X LTDA"); bancos, cooperativas e ações de bolsa ficam de fora. O CDN aceita If-Modified-Since.
- **Câmara (CEAP)**: arquivos anuais abertos; aceitam If-Modified-Since.
- **Senado (CEAPS)**: o CSV de 2025 tem aspas soltas dentro do detalhamento e o leitor padrão parava ("EOF inside string"). O leitor próprio separa pelo `;` entre aspas e junta linhas quebradas: 23.826 de 23.826 linhas lidas (#31).
- **Receita (dados abertos do CNPJ)**: WebDAV público, ~7 GB por mês (`Empresas0-9.zip` e `Estabelecimentos0-9.zip`). Na primeira execução (2026-10-22) a varredura levou ~16 min (938 s) para 3 empresas; depois, só refaz quando muda o mês ou aparece CNPJ novo.
- **DJEN (CNJ, Diário de Justiça Eletrônico Nacional)**: API pública e gratuita, mas responde **HTTP 403 a consultas de fora do Brasil**, como os servidores do GitHub Actions (execução de 2026-10-22: 5 consultas, 5 falhas; de um computador no Brasil funciona). Limite de 20 consultas/min (`X-RateLimit-Limit: 20`). Por isso a contagem automática de processos foi removida (#31).
- **Escavador, Jusbrasil e Processo Rápido**: restringem robôs; o `robots.txt` do Escavador bloqueia `/busca` e `/cpf`, o do Processo Rápido bloqueia `/consulta-processual/busca`. Só entram como **link aberto por pessoas** (lista curada e "Conferir processos"). A API do Escavador é paga.

## 7. LGPD: regras aplicadas (Lei 13.709/2018, texto compilado do Planalto lido em 2026-10-22)

| Regra | Artigo | Como está no projeto |
|---|---|---|
| Dado público tratado conforme finalidade, boa-fé e interesse público da divulgação | art. 7º, § 3º | Base principal: dados que a lei manda o TSE e o Portal publicarem. |
| Nova finalidade compatível, com direitos preservados | art. 7º, § 7º | Controle social da evolução patrimonial. |
| Interesse legítimo, só dados estritamente necessários e com transparência | art. 7º, IX; art. 10, §§ 1º e 2º | Minimização (sem CPF/CNPJ; só metadados de notícias) e página de privacidade. |
| Dispensa de consentimento não afasta princípios e direitos | art. 7º, § 6º | Página de direitos e canal de contato. |
| Princípios: finalidade, necessidade, qualidade, transparência, segurança, não discriminação etc. | art. 6º | Mesmos critérios para todos; fonte e data em cada página; curadoria de homônimos; linguagem não acusatória. |
| Informações ao titular: finalidade, forma, duração, controlador, contato, compartilhamento, direitos | art. 9º | `docs/privacidade.html`. **Faltam controlador e contato** em `config/privacidade.json`. |
| **Dado sensível** (saúde, filiação política…) não pode usar interesse legítimo | arts. 5º, II, e 11 | **BPC fora** (pode revelar deficiência). **PETI fora** (crianças, art. 14). Nem são consultados. |
| Direitos do titular | art. 18 | Listados na página de privacidade, com canal de pedido. |
| Registro das operações | art. 37 | Seção 8 deste documento. |
| Encarregado com identidade e contato públicos | art. 41, § 1º | Campo em `config/privacidade.json`. **Preencher** ou verificar dispensa para agente de pequeno porte em norma da ANPD. |
| Segurança | art. 46 | Segredos no cofre do Actions, varredura automática de CPF/CNPJ, **todos os dados salvos cifrados e assinados** (`src/cifra.py`, #34), testes. |
| Isenção jornalística | art. 4º, II, "a" | Vale só para fins **exclusivamente** jornalísticos. **Não** é a base principal aqui. |

Pontos para revisão jurídica:
- **Partido** é "filiação a organização de caráter político" (art. 5º, II). Aqui ele vem da candidatura pública, publicada pelo TSE por lei, mas o enquadramento precisa ser confirmado.
- **Benefícios** como Bolsa Família não são dado sensível pela definição legal, mas expõem situação social. Avaliar se a exibição é proporcional.
- **Processos**: a tag "Responde a processo" vem só de lista curada e lembra que ser réu não significa condenação; avaliar a proporcionalidade.
- O texto da página de privacidade é um **rascunho técnico**.

## 8. Registro das operações de tratamento (art. 37)

| Operação | Dados | Fonte | Onde fica | Retenção |
|---|---|---|---|---|
| Coleta de candidaturas e bens | nome, nome de urna, CPF, nascimento, cargo, partido, UF, bens | TSE (dados abertos) | Cache só no executor do Actions (`data/cache/`, não versionado, cifrado) | Durante a execução e no `actions/cache` |
| Cálculo de destaques | valores declarados, cargo, período | derivado | `docs/index.html` (sem CPF) | Até a próxima atualização |
| Id interno | HMAC da chave | derivado | `data/ids.json` (cifrado) | Enquanto houver acompanhamento |
| Consulta ao Portal | CPF/CNPJ (em memória), emendas, benefícios, sanções, recursos | API do Portal | `docs/pessoa/`, `docs/dossie/` (sem CPF/CNPJ); `portal.cache` cifrado | Até a próxima atualização; cache 7 dias |
| Cota parlamentar | total por ano e tipos de despesa (sem fornecedores) | Câmara e Senado (dados abertos) | `docs/dossie/`, painel; arquivos em `data/cache` (cifrados) | Até a próxima atualização |
| Empresas declaradas | CNPJ (só interno), atividade, início, capital, situação | Receita (dados abertos CNPJ) | `data/cache/cnpj_receita.json` (não versionado, cifrado); dossiê sem CNPJ | Até mudar o mês de referência |
| Processos informados | nome, UF, tribunal, número, link, issue | Issues "[Processo]" aprovadas | `config/processos.csv`, painel e dossiê | Até o processo terminar |
| Notícias | título, veículo, data, link | Google, fontes aprovadas | `docs/dossie/`, `noticias.cache` (3 dias) (fase 1: `data/noticias.jsonl`) | Enquanto houver acompanhamento |
| Sugestões de fontes | nome do veículo, URL, usuário do GitHub | Issues do repositório | GitHub | Conforme o GitHub |

## 9. Decisões já tomadas pelo usuário

- **Trava**: manter o modo atual (200 maiores) até criar `MONITORADOS_CSV`.
- **Dossiê antigo** (`docs/dossie/`): **não** substituir. Continua sendo gerado, e o painel mostra os links "Dossiê" (página nova) e "Notícias" (antigo).
- **Dinheiro público**: aba própria na página da pessoa.
- **Dependências**: Pillow (quando entrarem as fotos) e Lighthouse com Node no Actions estão liberados.
- **Portal da Transparência**: só pela API oficial, nada pelo site.
- **Falha de fonte**: mostrar "Fonte não encontrada"; dado faltante, "Não informado" (2026-10-22, #3; substitui o antigo "Indisponível").
- **CPF e CNPJ**: nunca visíveis.
- **Atualização**: automática, semanal.
- 2026-10-22 (#1, #33): **fluxo de trabalho**: cada pedido vira issue; cada commit vira versão (`versao.yml`, tag `vX.Y.Z` e release); agente `documentador` ao fim de cada ciclo.
- 2026-10-22 (#2): **Bing Notícias removido**.
- 2026-10-22 (#7): **linguagem não acusatória** e paleta calma; site renomeado **"Patrimônio declarado em foco"**; níveis "Muito acima do esperado", "Acima do esperado" e "Para conhecer".
- 2026-10-22 (#8): comparação com **bens fora do comum** (ilha, iate), em tom neutro.
- 2026-10-22 (#10): **empresas declaradas reduzem o destaque um grau**.
- 2026-10-22 (#11): **ordem do painel**: menções na imprensa (30 dias) e depois crescimento.
- 2026-10-22 (#14): tags do **bege ao vermelho-escuro** pela concentração de destaques; partido com bolinha da cor do partido.
- 2026-10-22 (#15): **estrela de exemplares** só com os três critérios (patrimônio compatível, cota abaixo da média, sem sanções); sem dado, sem estrela.
- 2026-10-22: **fontes gratuitas sempre**; perguntar ao usuário antes de usar qualquer fonte paga.
- 2026-10-22: **nada pode depender de rodar algo no PC do usuário**; tudo roda no GitHub.
- 2026-10-22 (#31): **processos**: só a lista curada por issue + o link "Conferir processos", **sem contagem automática**. Motivo: o DJEN recusa o GitHub fora do Brasil; o usuário recusou a ponte na Vercel e a API paga do Escavador.
- 2026-10-22 (#32): seção **"Pessoas" removida** do painel (repetia os cards; a página da pessoa segue pelo link "Dossiê").
- 2026-10-22 (#33): **depois que o documentador termina, a sessão principal limpa o contexto da conversa**; este documento e a memória precisam bastar para retomar do zero.
- 2026-10-22 (#34): **"os dados salvos devem ser criptografados"**: tudo que o pipeline grava (`data/ids.json`, `data/estado.json`, `data/cache`) passa por `src/cifra.py`.
- 2026-10-22 (#23, #24, #31): sites que proíbem robôs (Escavador, Jusbrasil, Processo Rápido) **só como link aberto por pessoas**; o robô nunca os consulta.

## 10. Fases

- **Fase 0 (feita; primeira execução com dados reais em 2026-10-22, 192 pessoas)**: id interno, página por pessoa com abas, painel com SVG e cartões, estilo responsivo, testes, Lighthouse, privacidade.
- **Fase 1, notícias com tags**:
  - `src/noticias.py`: RSS incremental, uma consulta por pessoa, deduplicação por URL canônica e título parecido, só metadados em `data/noticias.jsonl`.
  - `src/classificador.py`: tags fixas por regras de `config/tags.json`. Tags: político, eleitoral, legislativo, gestão, patrimonial, judicial, criminal, outros.
  - `config/curadoria.csv` (`url,id_pessoa,decisao,data`): homônimo e irrelevante não voltam; "criminal" só com `aprova_criminal`.
  - Na aba Notícias: cartões, chips e filtros por tag e período. Gráfico "notícias por tema" no painel (a função já existe; o bloco fica escondido enquanto vazio).
- **Fase 2**: desambiguação das tags por modelo de linguagem (JSON validado, teto de chamadas, cache e chave como segredo). Campos previstos: `tags_regra`, `tags_modelo`, `origem_tag`.
- **Fase 3**: propostas do plano de governo (PDF do TSE, cargos do Executivo) em `data/propostas.jsonl`, com trecho literal, página e se depende de lei.
- **Fase 4**: proposições da Câmara e do Senado, sugestão de vínculos e só os aprovados em `config/vinculos.csv` (`status=aprovado`). Tramitação e cobertura, sem nota.
- **Fase 5**: atualização semanal de status; assembleias estaduais e câmaras municipais.
- **Fotos**: só de fontes oficiais, depois de confirmados os termos. WebP em 2 tamanhos, `loading=lazy`, texto alternativo e crédito. Até lá, avatar com iniciais.

## 11. Pendências abertas

1. **Dados em texto puro no histórico do git**: versões antigas de `data/estado.json` (commit `e249e44` e outros do bot) têm cerca de 1.173 CPFs num repositório **público**; as versões antigas de `data/ids.json` e `data/estado.json` anteriores à cifra (#34) também estão em texto puro. O arquivo atual foi zerado e passa a ser gravado cifrado. Apagar do histórico exige reescrita e force push (ação destrutiva), **só com autorização do usuário**. Depois, pedir ao suporte do GitHub a limpeza de cache.
2. **Preencher `config/privacidade.json`** (controlador, contato, encarregado) antes de divulgar.
3. **Conferir na próxima execução de "Atualizar alertas"** (a de 2026-10-22 04:26 UTC foi a primeira com o cache, "0 do cache"):
   - a cifra (#34): o cache antigo em texto puro é apagado e tudo é baixado de novo (TSE, Câmara, Senado, varredura da Receita), então essa execução será mais lenta uma vez; `data/ids.json` e `data/estado.json` devem sair regravados cifrados (começam com `APC1`) e os ids `p0001…` devem se manter;
   - se o cache incremental (#26) é aproveitado a partir da execução seguinte (TSE, Portal, notícias com acertos no log) e se ela fica mais curta;
   - os cards, as tags, a estrela e a tabela de exemplares com dados reais depois das correções #27 a #32;
   - a razão do exemplar que foi corrigida à mão para `-49.0` em `docs/index.html` (e890a67) deve voltar recalculada;
   - a cota dos senadores de 2025 completa (leitor novo do CSV do Senado).
4. **`/pessoa-fisica` na API**: tinha falhado para 144 de 189 pessoas na execução #8; na execução de 2026-10-22 04:26 UTC houve só 1 falha em 930 consultas. Parece resolvido; confirmar na próxima execução.
5. **Qualidade dos dados**: casos extremos (ex.: 1º suplente com +R$ 272 mi, 407× o possível) parecem erro de dados. Conferir antes de divulgar.
6. **`renda_publica.csv`**: conferir os valores dos subsídios.
7. **Não há Python nem Node na máquina local**: testes só no Actions (e nada pode depender do PC do usuário, §9).

## 12. Ambiente local

- Pasta: `C:\Users\diorg\Downloads\alerta-patrimonial\alerta-patrimonial`. A pasta `alerta-patrimonial/` interna é um repositório antigo ignorado.
- GitHub CLI: `"/c/Program Files/GitHub CLI/gh.exe"` (logado). Logs do Actions: `gh run view <id> --log`.
- O `git push` às vezes pede login (Git Credential Manager) ou dá 403 passageiro; tentar de novo resolve.
- O navegador do Claude não está logado no GitHub.

## 13. Histórico de ciclos

- 2026-10-22 · v0.1.42 · #34 Dados salvos cifrados — `src/cifra.py` cifra e assina `data/ids.json`, `data/estado.json` e todo o `data/cache`; texto puro antigo é regravado ou apagado.
- 2026-10-22 · v0.1.41 · #1–#33 Documentação do ciclo — REFERENCIA.md e memória atualizados pelo documentador.
- 2026-10-22 · v0.1.40 · #33 Agente documentador — `.claude/agents/documentador.md` mantém este documento e a memória após cada ciclo.
- 2026-10-22 · v0.1.39 · #31 Processos sem contagem automática — saem `src/djen.py`, a ponte na Vercel e a tag "Réu em N processos"; ficam a lista curada e "Conferir processos".
- 2026-10-22 · v0.1.38 · #31 Ponte do DJEN na Vercel — tentativa de contornar o 403 do DJEN por São Paulo; desfeita na v0.1.39 por decisão do usuário.
- 2026-10-22 · v0.1.37 · #31 DJEN a 20 consultas/min — pausa entre consultas de 0,5 s para 3,2 s.
- 2026-10-22 · v0.1.36 · #31 CSV do Senado — leitor próprio para aspas soltas no arquivo de 2025.
- 2026-10-22 · v0.1.35 · #32 Remove "Pessoas" — seção do painel retirada por repetir os cards.
- 2026-10-22 · v0.1.34 · #30 Seção "Pessoas" com tags — cards com tags clicáveis e filtros (removida na v0.1.35).
- 2026-10-22 · v0.1.33 · #29 Tabelas no PC — nome e cargo não quebram mais letra por letra.
- 2026-10-22 · v0.1.32 · #28 Tags na tabela — coluna "Tags" clicável na tabela completa e na de exemplares.
- 2026-10-22 · v0.1.31 · #27 Painel quebrado pela varredura — `varrer` ignora casas decimais, números com até 4 casas e painel publicado restaurado.
- 2026-10-22 · v0.1.30 · #26 Cache incremental — TSE, Portal (7 dias) e notícias (3 dias) em `data/cache`, assinado e cifrado.
- 2026-10-22 · v0.1.29 · #25 Contagem pelo DJEN — tag "Réu em N processos" (removida na v0.1.39).
- 2026-10-22 · v0.1.28 · #13 Empresas pela Receita — atividade, início, capital e situação no dossiê, sem CNPJ.
- 2026-10-22 · v0.1.27 · #24 Processo Rápido — aceito como link na lista curada e em "Conferir processos".
- 2026-10-22 · v0.1.26 · #23 Escavador — aceito como link na lista curada e em "Conferir processos".
- 2026-10-22 · v0.1.25 · #21 #22 Conferir processos e legenda — link de busca pelo nome nos cards e legenda como filtro.
- 2026-10-22 · v0.1.24 · #20 Responde a processo — formulário "[Processo]", `processos.yml` e `config/processos.csv`.
- 2026-10-22 · v0.1.23 · ID_SEGREDO — registra a criação do segredo.
- 2026-10-22 · v0.1.22 · #19 Regiões — estados agrupados por região, com filtro.
- 2026-10-22 · v0.1.21 · #18 Blocos vazios — gráficos e seções sem conteúdo ficam escondidos.
- 2026-10-22 · v0.1.20 · #17 Tabela de exemplares — exemplares em tabela própria.
- 2026-10-22 · v0.1.19 · #15 Teste de exemplares — nome fictício não deriva do CPF.
- 2026-10-22 · v0.1.18 · #16 Legenda das tags — escala de cores, partido, estrela e empresas visíveis.
- 2026-10-22 · v0.1.17 · #15 Estrela de exemplares — `src/exemplares.py` com os três critérios.
- 2026-10-22 · v0.1.16 · #14 Cores das tags — cor do partido e bege ao vermelho-escuro pela concentração.
- 2026-10-22 · v0.1.15 · #7 Rótulo "Segurança" — corrige rótulo cortado no gráfico de notícias.
- 2026-10-22 · v0.1.14 · #12 Filtro por cargo — menu e tag de cargo clicável.
- 2026-10-22 · v0.1.13 · #11 Ordem por menções — Google News em inglês e ordem por menções e crescimento.
- 2026-10-22 · v0.1.12 · #10 Empresas declaradas — marcação e destaque um grau abaixo.
- 2026-10-22 · v0.1.11 · #8 Cota no painel e bens fora do comum — dez que mais gastaram e ilha/iate na comparação.
- 2026-10-22 · v0.1.10 · #7 Linguagem não acusatória — novo nome do site, novos níveis e paleta calma.
- 2026-10-22 · v0.1.9 · #9 Tags no card — cargo, partido e estado.
- 2026-10-22 · v0.1.8 · #6 Cota parlamentar — `src/cota.py` (CEAP e CEAPS) no dossiê.
- 2026-10-22 · v0.1.7 · #5 Daria para comprar — `config/bens_referencia.json`.
- 2026-10-22 · v0.1.6 · #4 Dossiê em cards — seções em cards e tabela legível no celular.
- 2026-10-22 · v0.1.5 · #4 Painel em cards — 24 por vez e tabela completa sob demanda.
- 2026-10-22 · v0.1.4 · #3 Mensagens de falta — "Fonte não encontrada" e "Não informado".
- 2026-10-22 · v0.1.3 · #3 Notícias mais rápidas — 0,5 s entre buscas e aviso do horário do Portal.
- 2026-10-22 · v0.1.2 · #3 Cache do TSE — zips guardados entre execuções.
- 2026-10-22 · v0.1.1 · #2 Remove o Bing — só Google Notícias e fontes sugeridas.
- 2026-10-22 · v0.1.0 · #1 Fluxo issue e versão — `versao.yml` cria tag e release a cada push na `main`.
