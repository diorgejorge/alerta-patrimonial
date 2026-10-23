# Caramelo Vasculha (alerta patrimonial)

Compara, para cada pessoa, o patrimônio declarado ao TSE entre duas eleições consecutivas com:
1. a **capacidade de acumulação estimada** (subsídio como eleito × taxa de poupança + renda extra informada), e
2. o **grupo de pares** (mesmo cargo e período), via percentil.

Gera alertas (forte / atenção / informativo), um painel estático com uma página por pessoa (`docs/pessoa/<id>.html`) e um resumo opcional no Telegram.
**Resultado é indício para acompanhamento, nunca prova.**

## Status
Testes automáticos com dados sintéticos e sem rede rodam no Actions (workflow `testes.yml`: `pytest` e Lighthouse no celular). Localmente: `python src/pipeline.py --demo --saida _demo` e `python -m pytest tests`.
Na primeira execução real, confira as colunas dos CSVs do TSE (`bem_candidato_*` e `consulta_cand_*`):
- se `NR_CPF_CANDIDATO` vier mascarado, a chave cai para nome + data de nascimento (ver `chave_pessoa`);
- se o arquivo `_BRASIL.csv` não existir no zip, o código concatena os CSVs por UF.

## Uso local
```
pip install -r requirements.txt
python src/pipeline.py --demo --saida _demo   # dados sinteticos, sem internet, fora de docs/
python src/pipeline.py            # dados reais do TSE
```
Abra `docs/index.html` (ou `_demo/docs/index.html`) no navegador.

## Configuração (`config/`)
- `parametros.json`: anos analisados, taxa de poupança, limiares de alerta, e `publicar_somente_monitorados`.
- `renda_publica.csv`: subsídio mensal por cargo e ano de vigência. **Confira os valores** antes de confiar na razão.
- Lista de monitorados: segredo `MONITORADOS_CSV` (conteúdo CSV com `nome,cpf,renda_extra_mensal`), lido só em memória. Sem ele, o painel segue o modo atual: os `max_linhas_sem_lista` maiores alertas. `config/monitorados.csv` continua aceito, mas **não ponha CPF nele**: o repositório é público.
- `analytics.json`: ID de medição do Google Analytics 4 (`G-XXXXXXXXXX`) e o prazo de retenção escolhido no GA (2 ou 14 meses). Vazio = GA desligado. Com ID, a tag do Google (gtag.js) entra logo depois do `<head>` de todas as páginas publicadas, com o consentimento negado: os cookies só são gravados depois do "Aceitar" no aviso (LGPD); a página de privacidade ganha a seção "Métricas de acesso".
- `vinculos.csv` (fase 4) e `curadoria.csv` (fase 1): revisões manuais; só o que estiver aprovado aparece no site.

## Automação (GitHub Actions)
1. Crie um repositório **privado** e envie estes arquivos.
2. Em Settings → Secrets and variables → Actions, crie `ID_SEGREDO` (um texto aleatório longo; gera o id interno `p0001`... de cada pessoa sem expor CPF; sem ele não há páginas por pessoa) e `TRANSPARENCIA_TOKEN` com a chave gratuita da API do Portal da Transparência (cadastro em https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email). Todas as consultas ao Portal (emendas, benefícios, despesas e sanções) usam só essa API; sem a chave, a seção "Dinheiro público" do dossiê fica sem dados. (Opcional) Crie também `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`.
3. Painel no GitHub Pages: em Settings → Pages, escolha **Source: GitHub Actions**. Lembre que o site do Pages é **público**, mesmo com repositório privado.

### Fluxos (aba Actions)
Os fluxos de dados são separados para o site atualizar rápido: o principal publica o painel em minutos, e o dossiê por estado, que é lento, roda depois, sozinho. Os números indicam a ordem.

| Fluxo | Arquivo | Quando roda | O que faz | Tempo |
|---|---|---|---|---|
| **1 · Dados dos políticos** | `atualizar.yml` | Toda segunda às 04:00 (Brasília) ou manual | TSE, alertas de patrimônio, Portal da Transparência por pessoa, cota, projetos, empresas e notícias. Grava `docs/` (painel e páginas por pessoa), `data/estado.json` e `data/estados_base.json` (base do fluxo 2, sem CPF). | minutos |
| **2 · Dossiê por estado** | `estados.yml` | Logo depois do fluxo 1, ou manual | Gasto do estado e verbas da União (SICONFI), emendas dos últimos 4 anos (API do Portal), carimbos de emergência (S2iD) e emenda parada, municípios e deputados estaduais. Grava `docs/estado/`. O SICONFI aceita cerca de 1 consulta por segundo: os municípios entram em partes, e cada execução continua de onde a anterior parou (cache cifrado). O log mostra a etapa, a contagem, o percentual e a estimativa do que falta; ao final, a página da execução traz uma tabela com o tempo de cada etapa. | até 3 h |
| **3 · Publicar site** | `pages.yml` | Depois dos fluxos 1 e 2, a cada mudança visual na `main`, ou manual | Monta o painel com o template atual e publica `docs/` no GitHub Pages. | 1 min |
| **Testes e acessibilidade** | `testes.yml` | A cada push em `src/`, `tests/` ou `config/` | Testes unitários e de integração (sem rede, dados mockados) e Lighthouse no celular. | minutos |
| **Versão automática** | `versao.yml` | A cada push na `main` | Cria a tag `vX.Y.Z` e a release com a mensagem do commit. | segundos |
| **Issue · aprovar fonte sugerida** | `fontes.yml` | Rótulo `aprovada` numa issue de fonte | Grava a fonte em `config/fontes_noticias.csv`. | segundos |
| **Issue · aprovar processo informado** | `processos.yml` | Rótulo `aprovada` numa issue de processo | Desligado no site (#51); guardado para quando houver base oficial. | segundos |

**Sem tempo perdido baixando coisas:** todos os fluxos com Python usam `.github/actions/python`, que guarda o ambiente pronto (Python e pacotes) em cache e só reinstala quando o `requirements.txt` muda. Medido no fluxo de testes em 23/10: antes, cada job gastava de 12 a 21 s preparando o Python (`setup-python` mais `pip install`) em toda execução; com o cache, de 3 a 7 s. Os testes de interface usam o Chrome que já vem no runner, e os fluxos de issue usam o Python do runner, sem instalar nada.

**Releitura única do TSE:** o fluxo 1 guarda cada ano do TSE já lido e só relê quando o arquivo muda ou quando a leitura muda (`VERSAO_LEITURA_TSE` em `src/pipeline.py`). Em 23/10 a leitura passou para a versão 2 (#59: cidade do eleito e resultado do 2º turno), então a próxima execução relê todos os anos uma vez e demora mais (perto dos 17 min de uma execução fria, dentro do limite de 150 min).

**Meus representantes (#59):** o fluxo 1 grava `docs/representantes/UF.json` (um por estado) e `docs/representantes/cidades/<código TSE>.json` (prefeito, vice e vereadores de cada cidade). O painel só baixa o arquivo escolhido.

Uma execução manual (Actions → nome do fluxo → Run workflow) espera a anterior do mesmo fluxo terminar. O GitHub desativa agendamentos de repositórios sem nenhum commit por 60 dias; como cada execução grava um commit, isso não deve acontecer, mas se acontecer basta reativar em Actions.

## Sugestões de fontes pelo site
O painel tem o bloco "Ajude a ampliar as fontes", que abre formulários de issue no GitHub (é preciso ter conta; a sugestão fica pública):
- **Fonte de notícias** (`.github/ISSUE_TEMPLATE/fonte-noticias.yml`): veículo, feed RSS ou endereço de busca com `{q}` e abrangência (nacional ou UF).
- **Fonte de dados** (`.github/ISSUE_TEMPLATE/fonte-dados.yml`): base pública para avaliar; precisa de código novo, então não entra sozinha.

Para aprovar uma fonte de notícias, aplique o rótulo **`aprovada`** na issue (crie o rótulo uma vez em Issues → Labels). O workflow `fontes.yml` testa o feed, grava em `config/fontes_noticias.csv`, responde e fecha a issue. Como só quem tem acesso de escrita aplica rótulos, nada entra sem revisão. A fonte passa a valer na próxima atualização:
- feed com `{q}` (ex.: `https://site.com.br/?s={q}&feed=rss2`): busca o nome de cada pessoa e pode abrir a matéria para confirmar a menção;
- feed geral (sem `{q}`): lido uma vez por execução; só entram itens que citam a pessoa no título ou no resumo.
Para remover uma fonte, apague a linha do CSV.

## Limitações
- Bens são declarados pelo custo histórico, não pelo valor de mercado.
- Herança, venda de bens, atividade rural/empresarial e renda do cônjuge não entram.
- Só renda como eleito em cargos listados em `renda_publica.csv`; demais casos ficam sem razão (só percentil).
- Empresas ligadas vêm só da descrição dos bens declarados ao TSE (pode faltar empresa ou haver erro de leitura).
- Notícias são coletadas por nome e podem se referir a homônimos; a curadoria manual corrige casos conhecidos.
- Partes da API do Portal da Transparência podem recusar consultas numa execução; o dossiê mostra "Indisponível".
- Cuidado com LGPD e difamação: ao divulgar, descreva o fato e cite a fonte, sem concluir irregularidade.

## Fontes
- **TSE, Portal de Dados Abertos:** candidaturas (`consulta_cand_*`) e declarações de bens (`bem_candidato_*`). Link para a página de cada candidatura no DivulgaCandContas.
- **Portal da Transparência (só pela API oficial):** emendas de autoria e documentos de pagamento, benefícios sociais pagos ao CPF da própria pessoa, sanções (CEIS, CNEP, CEAF, CEPIM), recursos federais recebidos pela pessoa e pelas empresas declaradas.
- **Câmara dos Deputados e Senado Federal (dados abertos):** cota parlamentar e projetos (PL, PLP e PEC) apresentados e aprovados nos últimos quatro anos, como autor ou coautor; selo **Mão na massa** para os 10% de cada casa com mais projetos aprovados. Link para a lista de cada parlamentar no site oficial.
- **Notícias:** RSS do Google Notícias e de veículos sugeridos e aprovados. Só metadados (título, veículo, data, link); nunca texto, imagem ou resumo das matérias.
- **Fotos:** ainda não usadas. Só entrarão de fontes oficiais (Câmara, Senado, TSE), depois de confirmados os termos de uso; até lá, avatar com iniciais.

## Privacidade, finalidade e base legal
O registro das operações de tratamento (art. 37) é mantido pelo responsável e fica disponível mediante solicitação.

**Rascunho, precisa de revisão jurídica antes de divulgar o site.**
- **Finalidade:** controle social e interesse público sobre a evolução patrimonial de pessoas que disputam ou exercem cargos eletivos, a partir de dados que a lei já obriga a tornar públicos. O site aponta **indícios para acompanhamento**, com os mesmos critérios para todas as pessoas, e não afirma irregularidade.
- **Base legal (LGPD, Lei 13.709/2018):** dados de acesso público tratados conforme a finalidade, a boa-fé e o interesse público de sua divulgação (art. 7º, § 3º), para finalidade nova e compatível (art. 7º, § 7º), e interesse legítimo de controle social com só os dados estritamente necessários e transparência (art. 7º, IX, e art. 10). A isenção do art. 4º, II, "a" exige fins *exclusivamente* jornalísticos e não é a base principal. Dados sensíveis (art. 5º, II, e art. 11) não são tratados: BPC (pode revelar deficiência) e PETI (crianças, art. 14) ficam de fora. A transparência ativa vem da Lei 12.527/2011 (LAI) e da Lei 9.504/1997.
- **Transparência ao titular (arts. 9º, 18 e 41):** página `docs/privacidade.html`, preenchida com `config/privacidade.json` (controlador, contato e encarregado; **preencher antes de divulgar**).
- **Minimização:** CPF e CNPJ só são usados em memória para consultar as fontes oficiais. O site, o JSON publicado, os nomes de arquivo, os logs e o histórico (`data/estado.json`, `data/ids.json`) usam apenas o id interno, um HMAC do identificador com o segredo `ID_SEGREDO`. Benefícios sociais só aparecem quando a pessoa é a titular; registros em que ela é representante legal de outra pessoa são descartados.
- **Direitos do titular e correções:** pedidos de correção ou de marcação de homônimo entram pelas issues do repositório e são registrados na curadoria (`config/curadoria.csv`).
