# Globo voxel (protótipo)

Mundo em blocos dentro de um globo, com um personagem andando pela superfície.
Projeto independente do restante do repositório: não é publicado pelo GitHub Pages (que lê só `docs/`).

## Como rodar
Não precisa de build. Sirva a pasta com qualquer servidor estático e abra no navegador:
```
cd voxel-globo
python3 -m http.server 8000     # depois abra http://localhost:8000
```
O three.js (v0.160.0) é carregado do jsDelivr, então é preciso internet.

## Controles
- `W` / `S` ou `↑` / `↓`: andar para frente e para trás
- `A` / `D` ou `←` / `→`: virar
- roda do mouse: zoom da câmera

A água bloqueia o caminho. O personagem acompanha o relevo.

## Estado
Protótipo técnico. Paleta, escala, personagem e regras de jogo são provisórios; o conceito e a identidade visual ainda serão definidos.
Os valores ajustáveis estão no topo de `main.js` (`RAIO`, `RELEVO`, `VELOCIDADE`, `PALETA` em `COR_DO_TIPO`).
