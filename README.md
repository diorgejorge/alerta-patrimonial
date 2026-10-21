# Alerta patrimonial

Compara, para cada pessoa, o patrimônio declarado ao TSE entre duas eleições consecutivas com:
1. a **capacidade de acumulação estimada** (subsídio como eleito × taxa de poupança + renda extra informada), e
2. o **grupo de pares** (mesmo cargo e período), via percentil.

Gera alertas (forte / atenção / informativo), um painel estático e um resumo opcional no Telegram.
**Resultado é indício para acompanhamento, nunca prova.**

## Status
O código foi testado apenas com dados sintéticos (`python src/pipeline.py --demo`).
Na primeira execução real, confira as colunas dos CSVs do TSE (`bem_candidato_*` e `consulta_cand_*`):
- se `NR_CPF_CANDIDATO` vier mascarado, a chave cai para nome + data de nascimento (ver `chave_pessoa`);
- se o arquivo `_BRASIL.csv` não existir no zip, o código concatena os CSVs por UF.

## Uso local
```
pip install -r requirements.txt
python src/pipeline.py --demo     # teste sem internet
python src/pipeline.py            # dados reais do TSE
```
Abra `docs/index.html` no navegador.

## Configuração (`config/`)
- `parametros.json`: anos analisados, taxa de poupança, limiares de alerta, e `publicar_somente_monitorados`.
- `renda_publica.csv`: subsídio mensal por cargo e ano de vigência. **Confira os valores** antes de confiar na razão.
- `monitorados.csv`: lista de pessoas a acompanhar (`nome`, `cpf`, `renda_extra_mensal`). Com a lista preenchida, o painel mostra só esses nomes, mas o cálculo roda para todo o universo, então o percentil é comparável.

## Automação (GitHub Actions)
1. Crie um repositório **privado** e envie estes arquivos.
2. (Opcional) Em Settings → Secrets, crie `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`.
3. O workflow `atualizar.yml` roda sozinho toda segunda-feira às 06:00 (Brasília): baixa os dados do TSE, refaz alertas, notícias e consultas ao Portal da Transparência, grava `docs/` e `data/estado.json` (memória para marcar alertas "novos") e o `pages.yml` publica o site em seguida. Leva cerca de 1 hora; uma execução manual (Actions → Atualizar alertas → Run workflow) espera a anterior terminar. O GitHub desativa agendamentos de repositórios sem nenhum commit por 60 dias; como cada execução grava um commit, isso não deve acontecer, mas se acontecer basta reativar em Actions.
4. Painel no GitHub Pages: em Settings → Pages, escolha **Source: GitHub Actions**. O workflow `pages.yml` publica `docs/` depois de cada atualização (ou manualmente em Actions → Publicar painel). Lembre que o site do Pages é **público**, mesmo com repositório privado.

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
- Não inclui ainda vínculos societários, contratos e sanções (Portal da Transparência, CNPJ): próximo passo natural.
- Cuidado com LGPD e difamação: ao divulgar, descreva o fato e cite a fonte, sem concluir irregularidade.
