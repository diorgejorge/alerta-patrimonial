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
3. O workflow roda toda segunda-feira, atualiza `docs/` e `data/estado.json` (memória para marcar alertas "novos").
4. Para ver o painel, baixe `docs/index.html` do repositório. Não publique em GitHub Pages aberto se a lista contiver pessoas específicas.

## Limitações
- Bens são declarados pelo custo histórico, não pelo valor de mercado.
- Herança, venda de bens, atividade rural/empresarial e renda do cônjuge não entram.
- Só renda como eleito em cargos listados em `renda_publica.csv`; demais casos ficam sem razão (só percentil).
- Não inclui ainda vínculos societários, contratos e sanções (Portal da Transparência, CNPJ): próximo passo natural.
- Cuidado com LGPD e difamação: ao divulgar, descreva o fato e cite a fonte, sem concluir irregularidade.
