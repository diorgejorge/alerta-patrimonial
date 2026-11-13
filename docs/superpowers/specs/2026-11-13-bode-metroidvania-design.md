# Bode Mjolnir: design (título provisório)

Data: 2026-11-13
Status: v3. Inclui as folhas de referência enviadas pelo autor. Aguarda aprovação do autor.

Legenda: itens marcados **(proposta)** foram sugeridos por mim e o autor ainda não confirmou. Itens sem marca foram decididos pelo autor.

## Intenção e porquê

Jogo de plataforma metroidvania. Primeiro para PC, com teclado e mouse. Mobile fica para depois.

O herói é um bode montanhês cuja vila foi destruída pelo rei dragão. O dragão também roubou a lança de Odin, que a vila guardava.

O bode começa com um martelo. Aos poucos ele descobre que é o Mjolnir, e recupera as peças da arma até ela chegar ao potencial total. Ele sobe a montanha até o dragão, derrota o rei e devolve a lança à vila.

O jogo é feito para quem gosta de explorar um mapa conectado, com caminhos bloqueados até pegar habilidades, e de combate com peso.

## Inspirações

- Hollow Knight: referência principal. Quando houver conflito de design, Hollow Knight vence. Autor confirmou.
- Super Metroid e Castlevania: autor citou como inspiração de itens e habilidades.
- Souldiers: autor citou como inspiração.

## Metas

- Exploração metroidvania: mapa interligado, portões que só abrem com habilidade.
- Combate de martelo com peso.
- Três tipos de coleta com papéis claros (ver Progressão).
- Visual 3D em baixa resolução, com cara de pixel.

## Não-metas

- Multiplayer. **(proposta)**
- Mobile nesta fase. Autor disse PC primeiro.
- Diálogo longo. A história é contada por cenário e poucas falas. **(proposta)**

## Anti-metas (**proposta**, o autor não confirmou)

- Câmera livre que esconde o inimigo na luta.
- Grind sem fim: pegar item demais só pra avançar.
- Caminho bloqueado sem pista visual de onde ir.

## Restrições

- Plataforma: PC, teclado e mouse. Mobile depois. Fora de escopo agora.
- Engine: Godot 4. Já instalado no PC do autor. Projeto existente na pasta: não confirmado.
- Produção 3D: tudo no Blender, modelado do zero pelo autor. Sem conversão de sprite para voxel.
- Render 3D do bode: referência de vibe, não guia de modelagem.
- Sprites 2D existentes (bode, ovelha soldado, rei dragão): só conceito. Referência de silhueta e ação. Tudo será refeito em 3D no Blender; nenhum sprite entra no jogo. Autor confirmou. Arquivos em `refs-bode/`.

## Abordagens consideradas (estilo e câmera)

1. **Sprites 2D pixel:** sprite sheets já prontas, rápidas de usar. Mas cada animação é um desenho novo, e mapa grande fica caro de produzir.
2. **3D baixa resolução, câmera de lado (escolhida pelo autor):** modelo 3D pequeno, render com pouca resolução e filtro sem suavizar, câmera fixa de lado como em Hollow Knight. Tudo modelado no Blender.
3. **3D com câmera livre:** mais espaço de cenário, mas a luta fica difícil de ler. Rejeitada.

Escolhido: opção 2.

## Controles

- Teclado: anda, pula, ataca. Ataque sai na direção que o bode encara, como em Hollow Knight. Autor confirmou que não há mira com mouse.
- **(proposta)** Mouse: sem função de mira. Menus, se houver. A definir.
- Golpes do martelo, conforme a folha de conceito do bode: golpe pesado, ataque no pulo, bloqueio. Teclas exatas a definir.

## Mundo e cenário

- Biomas: gelo, neve, floresta, lago, montanha.
- Montanha aparece no fundo dos cenários. Autor pediu que ela apareça ao fundo, em todas as áreas.
- Caminho até a montanha é bloqueado até pegar habilidade. Autor confirmou.
- Topo da montanha: caverna com ouro e o trono do rei dragão.

## Habilidades e caminho

- Primeira habilidade: o martelo quebra pedra e gruda no gelo. O bode escala parede de gelo com ele. Essa habilidade libera o caminho até a montanha. Autor concordou.
- Demais habilidades: não definidas agora. Vão sendo decididas durante o jogo. Autor confirmou.

## Progressão

Três tipos de coleta, cada um com um papel:

- Peças do Mjolnir: aumentam o dano do martelo. Juntas, levam a arma ao potencial total.
- Runas: 5 runas juntas = +1 de vida máxima.
- Amuletos: itens equipáveis. O jogador escolhe a build dele.

Estátuas de Thor:
- Curam o bode e salvam o jogo (ponto de save).
- Cura vida total ao tocar.

Ferreiro com moeda: entra no jogo. Ele melhora o martelo. Detalhes (custo, origem da moeda, quantas melhorias): a definir.

## Inimigos

Ovelha soldado (inimiga fraca):
- Anda sozinha em mapa fácil. Em mapa difícil, anda em bando. Autor definiu.
- **(proposta)** Ataques da folha de conceito: estocada desajeitada, pancada de escudo, arremesso de lança. A ovelha usa lança e escudo; a espada que aparece em alguns quadros da folha fica de fora.
- **(proposta)** Reações: dano e queda.

Outros inimigos: a definir. Ovelha é só o mais fraco.

## Chefe: Rei Dragão

- Duas fases. Autor confirmou. Detalhes das fases ficam para depois, quando o autor ver na prática.
- Ataques de luta perto e de longe. Autor disse "os dois". **(proposta)** Estocada com a lança de Odin (perto), sopro de fogo (longe), investida aérea (mergulha do céu e bate no chão).
- **(proposta)** Movimento: anda, paira no ar, voa para frente.
- **(proposta)** Reações: dano e queda.

## Final

- Dragão cai. A lança volta para a vila.
- Vila reconstruída.
- Vídeo final e créditos.

## Ordem de construção

- Um mapa por vez. Cada mapa fica pronto e jogável antes do próximo. Autor pediu.
- **(proposta)** Primeiro mapa, a primeira entrega: uma sala. Bode anda, pula e ataca pelo teclado. Uma ovelha. Uma estátua de Thor que cura e salva. Câmera lateral com render em baixa resolução.
- Critério de pronto: jogador anda, bate na ovelha, leva dano, e salva na estátua.
- Fora do primeiro mapa: habilidades, chefe, ferreiro, amuletos, vídeo final.

## Referências (conceito, não arte final)

- `refs-bode/bode-render-3d.png`: vibe do bode (chifres longos, cicatriz no olho, correias de couro, martelo de pedra).
- `refs-bode/bode-sprites.jpg`: idle, andar, correr, golpe pesado, ataque no pulo, dano, bloqueio, queda.
- `refs-bode/ovelha-soldado-sprites.jpg`: andar, correr, 3 ataques, dano, queda.
- `refs-bode/rei-dragao-sprites.jpg`: parado, andar, pairar, voar, 3 ataques, dano, queda.

## Estilo visual e produção

- 3D baixa resolução, cor chapada, filtro sem suavizar.
- Bode modelado do zero no Blender, baixa poligonagem, textura pequena.
- Cenário e inimigos também no Blender.
- Exporta para Godot 4.
- **(proposta)** Tamanho do render e escala do pixel a definir pelo construtor.

## Deixado para quem constrói (minha escolha)

- Teclas exatas do teclado.
- Tamanho da tela de render e escala do pixel.
- Tempo de cada fase do chefe.

## Perguntas em aberto

Nenhuma pergunta de decisão pendente. Habilidades e detalhes do ferreiro ficam para decidir durante o jogo.
