import * as THREE from 'three';

// ---------------------------------------------------------------------------
// Parâmetros. Valores provisórios: o conceito e a identidade visual ainda
// serão definidos, então paleta, escala e tamanho do personagem podem mudar.
// ---------------------------------------------------------------------------
const RAIO = 26;            // raio base do globo, em blocos
const RELEVO = 5;           // altura máxima do relevo acima e abaixo do raio base
const NIVEL_MAR = RAIO;     // a água preenche tudo até este raio
const SEMENTE = 1337;
const VELOCIDADE = 5;       // blocos por segundo, medidos sobre a superfície
const VELOC_GIRO = 2.4;     // radianos por segundo
const ZOOM_MIN = 3;
const ZOOM_MAX = 70;

// Paleta provisória
const TIPO = { agua: 1, fundo: 2, areia: 3, grama: 4, floresta: 5, rocha: 6, neve: 7 };
const COR_DO_TIPO = [
  null,
  0x2f6fb0, // agua
  0x5b4a3a, // fundo
  0xe8d28c, // areia
  0x6fae4a, // grama
  0x3d7a3c, // floresta
  0x8a8580, // rocha
  0xf4f8fb, // neve
];

// ---------------------------------------------------------------------------
// Ruído determinístico (valor 3D + fractal), sem dependências
// ---------------------------------------------------------------------------
function hash(x, y, z, s) {
  let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(z, 1442695041) ^ Math.imul(s, 2246822519);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

function mistura(a, b, t) {
  return a + (b - a) * t;
}

function ruido3(x, y, z, s) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = x - xi, yf = y - yi, zf = z - zi;
  const u = xf * xf * (3 - 2 * xf);
  const v = yf * yf * (3 - 2 * yf);
  const w = zf * zf * (3 - 2 * zf);
  const h = (dx, dy, dz) => hash(xi + dx, yi + dy, zi + dz, s);
  const base0 = mistura(mistura(h(0, 0, 0), h(1, 0, 0), u), mistura(h(0, 1, 0), h(1, 1, 0), u), v);
  const base1 = mistura(mistura(h(0, 0, 1), h(1, 0, 1), u), mistura(h(0, 1, 1), h(1, 1, 1), u), v);
  return mistura(base0, base1, w);
}

function fractal(x, y, z) {
  let soma = 0, amp = 0.5, freq = 1, norma = 0;
  for (let i = 0; i < 4; i++) {
    soma += amp * ruido3(x * freq, y * freq, z * freq, SEMENTE + i);
    norma += amp;
    amp *= 0.5;
    freq *= 2;
  }
  return soma / norma; // aproximadamente entre 0 e 1
}

// Altura inteira da coluna na direção unitária d (em blocos a partir do centro)
function alturaEm(d) {
  const e = (fractal(d.x * 2.3 + 17, d.y * 2.3 + 5, d.z * 2.3 + 11) - 0.5) * 2.4;
  const passo = Math.max(-RELEVO, Math.min(RELEVO, Math.round(e * RELEVO)));
  return RAIO + passo;
}

function classificar(h, dy) {
  const e = h - RAIO;
  if (e < 0) return TIPO.fundo;
  if (Math.abs(dy) > 0.8 && e >= 1) return TIPO.neve;
  if (e === 0) return TIPO.areia;
  if (e <= 2) return TIPO.grama;
  if (e <= 4) return TIPO.floresta;
  return TIPO.rocha;
}

// ---------------------------------------------------------------------------
// Cena
// ---------------------------------------------------------------------------
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

const cena = new THREE.Scene();
cena.background = new THREE.Color(0xbfe3ff);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 2000);

cena.add(new THREE.HemisphereLight(0xffffff, 0x445566, 0.9));
const sol = new THREE.DirectionalLight(0xffffff, 0.8);
sol.position.set(30, 50, 20);
cena.add(sol);

// ---------------------------------------------------------------------------
// Globo: grade de voxels, só as faces expostas viram instâncias
// ---------------------------------------------------------------------------
const N = RAIO + RELEVO + 3;
const L = 2 * N + 1;
const indice = (x, y, z) => ((x + N) * L + (y + N)) * L + (z + N);
const solido = new Uint8Array(L * L * L);
const tipo = new Uint8Array(L * L * L);
const dir = new THREE.Vector3();

for (let x = -N; x <= N; x++) {
  for (let y = -N; y <= N; y++) {
    for (let z = -N; z <= N; z++) {
      const i = indice(x, y, z);
      const r = Math.sqrt(x * x + y * y + z * z);
      if (r < RAIO - RELEVO - 1) { // núcleo sempre sólido
        solido[i] = 1;
        tipo[i] = TIPO.fundo;
        continue;
      }
      if (r > RAIO + RELEVO + 1) continue; // espaço vazio
      dir.set(x / r, y / r, z / r);
      const h = alturaEm(dir);
      const topo = Math.max(h, NIVEL_MAR);
      if (r >= topo + 0.5) continue;
      solido[i] = 1;
      tipo[i] = r < h + 0.5 ? classificar(h, dir.y) : TIPO.agua;
    }
  }
}

const exposto = [];
for (let x = -N + 1; x <= N - 1; x++) {
  for (let y = -N + 1; y <= N - 1; y++) {
    for (let z = -N + 1; z <= N - 1; z++) {
      const i = indice(x, y, z);
      if (!solido[i] || tipo[i] === TIPO.fundo) continue;
      const cercado =
        solido[indice(x + 1, y, z)] && solido[indice(x - 1, y, z)] &&
        solido[indice(x, y + 1, z)] && solido[indice(x, y - 1, z)] &&
        solido[indice(x, y, z + 1)] && solido[indice(x, y, z - 1)];
      if (!cercado) exposto.push({ x, y, z, t: tipo[i] });
    }
  }
}

const malhaGlobo = new THREE.InstancedMesh(
  new THREE.BoxGeometry(1, 1, 1),
  new THREE.MeshLambertMaterial(),
  exposto.length
);
const m4 = new THREE.Matrix4();
const cor = new THREE.Color();
exposto.forEach((b, k) => {
  m4.makeTranslation(b.x, b.y, b.z);
  malhaGlobo.setMatrixAt(k, m4);
  // pequena variação de tom por bloco, para a textura voxel ficar visível
  cor.setHex(COR_DO_TIPO[b.t]).multiplyScalar(0.93 + hash(b.x, b.y, b.z, 7) * 0.12);
  malhaGlobo.setColorAt(k, cor);
});
malhaGlobo.instanceMatrix.needsUpdate = true;
malhaGlobo.instanceColor.needsUpdate = true;
cena.add(malhaGlobo);

// ---------------------------------------------------------------------------
// Personagem: voxels simples, com a base dos pés no ponto de origem
// ---------------------------------------------------------------------------
function material(c) {
  return new THREE.MeshLambertMaterial({ color: c });
}

function caixa(l, a, p, c, x, y, z) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(l, a, p), material(c));
  m.position.set(x, y, z);
  return m;
}

const personagem = new THREE.Group();
const quadril = { x: 0.2 };
const pernaE = new THREE.Group(); pernaE.position.set(quadril.x, 0.7, 0);
const pernaD = new THREE.Group(); pernaD.position.set(-quadril.x, 0.7, 0);
pernaE.add(caixa(0.36, 0.7, 0.36, 0x34495e, 0, -0.35, 0));
pernaD.add(caixa(0.36, 0.7, 0.36, 0x34495e, 0, -0.35, 0));
const bracoE = new THREE.Group(); bracoE.position.set(0.5, 1.4, 0);
const bracoD = new THREE.Group(); bracoD.position.set(-0.5, 1.4, 0);
bracoE.add(caixa(0.28, 0.7, 0.28, 0xd9534f, 0, -0.35, 0));
bracoD.add(caixa(0.28, 0.7, 0.28, 0xd9534f, 0, -0.35, 0));
personagem.add(pernaE, pernaD, bracoE, bracoD);
personagem.add(caixa(0.7, 0.75, 0.4, 0xd9534f, 0, 1.075, 0));
const cabeca = caixa(0.6, 0.6, 0.6, 0xf1c27d, 0, 1.75, 0);
personagem.add(cabeca);
personagem.add(caixa(0.6, 0.18, 0.62, 0x4a2f1b, 0, 2.0, 0)); // cabelo
personagem.add(caixa(0.1, 0.1, 0.02, 0x111111, 0.15, 1.78, -0.31)); // olhos na frente (-Z)
personagem.add(caixa(0.1, 0.1, 0.02, 0x111111, -0.15, 1.78, -0.31));
cena.add(personagem);

// ---------------------------------------------------------------------------
// Posição do personagem na superfície: p é unitário, fwd é tangente a p
// ---------------------------------------------------------------------------
const Y = new THREE.Vector3(0, 1, 0);
const X = new THREE.Vector3(1, 0, 0);
const p = new THREE.Vector3();
const fwd = new THREE.Vector3();

function encontrarInicio() {
  // espiral de Fibonacci: primeiro ponto de terra firme com relevo acima do mar
  const n = 4000;
  const ouro = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (2 * (i + 0.5)) / n;
    const r = Math.sqrt(1 - y * y);
    const t = i * ouro;
    const d = new THREE.Vector3(Math.cos(t) * r, y, Math.sin(t) * r);
    if (Math.abs(y) < 0.6 && alturaEm(d) >= NIVEL_MAR + 2) return d;
  }
  return new THREE.Vector3(1, 0, 0);
}

function reprojetarFrente() {
  fwd.addScaledVector(p, -fwd.dot(p)).normalize();
}

p.copy(encontrarInicio());
const tmp = Math.abs(p.y) < 0.9 ? Y : X;
fwd.copy(tmp).addScaledVector(p, -tmp.dot(p)).normalize();

function girar(angulo) {
  // rotaciona fwd em torno de p; positivo gira para a esquerda
  const c = Math.cos(angulo), s = Math.sin(angulo);
  const perp = new THREE.Vector3().crossVectors(p, fwd);
  fwd.multiplyScalar(c).addScaledVector(perp, s).normalize();
}

function andar(sinal, passo) {
  const a = passo / RAIO;
  const d = fwd.clone().multiplyScalar(sinal);
  const novo = p.clone().multiplyScalar(Math.cos(a)).addScaledVector(d, Math.sin(a)).normalize();
  if (alturaEm(novo) < NIVEL_MAR) return false; // água bloqueia o caminho
  p.copy(novo);
  reprojetarFrente();
  return true;
}

// ---------------------------------------------------------------------------
// Entrada
// ---------------------------------------------------------------------------
const teclas = {};
const TECLAS_DE_JOGO = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space']);
addEventListener('keydown', (e) => {
  teclas[e.code] = true;
  if (TECLAS_DE_JOGO.has(e.code)) e.preventDefault();
});
addEventListener('keyup', (e) => { teclas[e.code] = false; });
addEventListener('blur', () => { for (const k in teclas) teclas[k] = false; });

let distancia = 9;
addEventListener('wheel', (e) => {
  e.preventDefault();
  distancia = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, distancia + e.deltaY * 0.02));
}, { passive: false });

addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ---------------------------------------------------------------------------
// Loop
// ---------------------------------------------------------------------------
const posCamera = new THREE.Vector3();
const alvo = new THREE.Vector3();
const basePersonagem = new THREE.Matrix4();
const zero = new THREE.Vector3();
const coord = document.getElementById('coord');
let primeiroFrame = true;
let ultimo = performance.now();
let tempo = 0;
let ultimoTextoCoord = 0;

function atualizar(agora) {
  const dt = Math.min((agora - ultimo) / 1000, 0.05);
  ultimo = agora;
  tempo += dt;

  const esquerda = teclas.KeyA || teclas.ArrowLeft;
  const direita = teclas.KeyD || teclas.ArrowRight;
  if (esquerda) girar(VELOC_GIRO * dt);
  if (direita) girar(-VELOC_GIRO * dt);

  let movendo = 0;
  if (teclas.KeyW || teclas.ArrowUp) movendo = 1;
  if (teclas.KeyS || teclas.ArrowDown) movendo = -1;
  if (movendo !== 0) andar(movendo, VELOCIDADE * dt);

  // posição: pés sobre o topo da coluna (o topo fica em h + 0.5)
  const h = alturaEm(p);
  const pes = p.clone().multiplyScalar(h + 0.5);
  personagem.position.copy(pes);
  basePersonagem.lookAt(zero, fwd, p);
  personagem.quaternion.setFromRotationMatrix(basePersonagem);

  // animação simples de caminhada
  const balanco = movendo !== 0 ? Math.sin(tempo * 9) * 0.8 : 0;
  pernaE.rotation.x = balanco;
  pernaD.rotation.x = -balanco;
  bracoE.rotation.x = -balanco;
  bracoD.rotation.x = balanco;

  // câmera: atrás do personagem, com "cima" = normal da superfície
  const altura = 0.6 * distancia + 2.5;
  const desejada = pes.clone().addScaledVector(p, altura).addScaledVector(fwd, -distancia);
  alvo.copy(pes).addScaledVector(p, 1.3);
  if (primeiroFrame) {
    posCamera.copy(desejada);
    primeiroFrame = false;
  } else {
    posCamera.lerp(desejada, 1 - Math.exp(-6 * dt));
  }
  camera.position.copy(posCamera);
  camera.up.copy(p);
  camera.lookAt(alvo);

  if (agora - ultimoTextoCoord > 150) {
    ultimoTextoCoord = agora;
    const lat = (Math.asin(p.y) * 180) / Math.PI;
    const lon = (Math.atan2(p.z, p.x) * 180) / Math.PI;
    coord.textContent = `Latitude ${lat.toFixed(1)}° · Longitude ${lon.toFixed(1)}°`;
  }
}

function quadro(agora) {
  atualizar(agora);
  renderer.render(cena, camera);
  requestAnimationFrame(quadro);
}

requestAnimationFrame(quadro);

// Expõe um pequeno diagnóstico para testes automatizados e depuração
window.__voxel = {
  blocosVisiveis: exposto.length,
  posicao: () => p.toArray(),
  alturaEm,
  NIVEL_MAR,
};
