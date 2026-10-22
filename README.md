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
- `vinculos.csv` (fase 4) e `curadoria.csv` (fase 1): revisões manuais; só o que estiver aprovado aparece no site.

## Automação (GitHub Actions)
1. Crie um repositório **privado** e envie estes arquivos.
2. Em Settings → Secrets and variables → Actions, crie `ID_SEGREDO` (um texto aleatório longo; gera o id interno `p0001`... de cada pessoa sem expor CPF; sem ele não há páginas por pessoa) e `TRANSPARENCIA_TOKEN` com a chave gratuita da API do Portal da Transparência (cadastro em https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email). Todas as consultas ao Portal (emendas, benefícios, despesas e sanções) usam só essa API; sem a chave, a seção "Dinheiro público" do dossiê fica sem dados. (Opcional) Crie também `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`.
3. O workflow `atualizar.yml` roda sozinho toda segunda-feira às 04:00 (Brasília): baixa os dados do TSE, refaz alertas, notícias e consultas ao Portal da Transparência, grava `docs/` e `data/estado.json` (memória para marcar alertas "novos") e o `pages.yml` publica o site em seguida. Leva cerca de 1 hora; uma execução manual (Actions → Atualizar alertas → Run workflow) espera a anterior terminar. O GitHub desativa agendamentos de repositórios sem nenhum commit por 60 dias; como cada execução grava um commit, isso não deve acontecer, mas se acontecer basta reativar em Actions.
4. Painel no GitHub Pages: em Settings → Pages, escolha **Source: GitHub Actions**. O workflow `pages.yml` publica `docs/` depois de cada atualização (ou manualmente em Actions → Publicar painel). Lembre que o site do Pages é **público**, mesmo com repositório privado.

## Contagem de acessos
Desligada até ser configurada. Usa o [GoatCounter](https://www.goatcounter.com), gratuito para projetos sem fins comerciais, sem cookies e sem guardar IP (por isso não precisa de aviso de cookies):
1. Crie uma conta no GoatCounter e escolha um código (ex.: `caramelo`, que vira `caramelo.goatcounter.com`).
2. Em Settings → Secrets and variables → Actions → **Variables**, crie `GOATCOUNTER` com esse código (ou o endereço completo `https://.../count` de uma instalação própria). É variável, não segredo: o código aparece no site de qualquer jeito.
3. Rode Actions → Publicar painel. O `pages.yml` (via `src/metricas.py`) põe o contador em todas as páginas e a seção "Contagem de acessos" em `privacidade.html`. Para desligar, apague a variável e publique de novo.

Os números ficam no painel do GoatCounter (visitas por página, origem, navegador, tela e país). Para mostrá-los ao público, o GoatCounter permite tornar o painel público nas configurações da conta.

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
- **Visitantes:** com a contagem de acessos ligada, o GoatCounter recebe a página aberta, a origem, o navegador, o sistema, o tamanho da tela e o país; sem cookies, sem IP guardado e sem identificar quem visita.
- **Direitos do titular e correções:** pedidos de correção ou de marcação de homônimo entram pelas issues do repositório e são registrados na curadoria (`config/curadoria.csv`).
