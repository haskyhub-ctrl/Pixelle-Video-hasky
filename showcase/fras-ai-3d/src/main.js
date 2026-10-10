import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { Reflector } from 'three/examples/jsm/objects/Reflector.js';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

const ICONS = window.__ICONS || {};
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const coarse = matchMedia('(pointer: coarse)').matches;
const isWide = () => innerWidth >= 768;

/* =====================================================================
   Page UI: nav state, reveal, counters, marquee, magnetic buttons
   ===================================================================== */
const nav = document.getElementById('nav');
new IntersectionObserver(([e]) => nav.classList.toggle('solid', !e.isIntersecting), { rootMargin: '-80px 0px 0px 0px' })
  .observe(document.querySelector('.hero'));

const rvObs = new IntersectionObserver(es => es.forEach(e => {
  if (e.isIntersecting) { e.target.classList.add('in'); rvObs.unobserve(e.target); }
}), { threshold: .12 });
document.querySelectorAll('.rv').forEach(el => rvObs.observe(el));

const fmt = (v, dec) => v.toLocaleString('vi-VN', { minimumFractionDigits: dec, maximumFractionDigits: dec });
const cntObs = new IntersectionObserver(es => es.forEach(e => {
  if (!e.isIntersecting) return;
  cntObs.unobserve(e.target);
  const el = e.target, to = parseFloat(el.dataset.count), dec = +(el.dataset.dec || 0);
  const suffix = el.querySelector('small')?.outerHTML || '';
  if (reduce) { el.innerHTML = fmt(to, dec) + suffix; return; }
  const t0 = performance.now(), dur = 1800;
  const tick = now => {
    const k = Math.min(1, (now - t0) / dur), ease = 1 - Math.pow(1 - k, 4);
    el.innerHTML = fmt(to * ease, dec) + suffix;
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}), { threshold: .5 });
document.querySelectorAll('[data-count]').forEach(el => cntObs.observe(el));

const track = document.getElementById('track');
track.innerHTML += track.innerHTML.replaceAll('<figure class="quote"', '<figure class="quote" aria-hidden="true"');

if (!reduce && !coarse) {
  document.querySelectorAll('.magnetic').forEach(b => {
    b.addEventListener('pointermove', e => {
      const r = b.getBoundingClientRect();
      b.style.setProperty('--mx', ((e.clientX - r.left - r.width / 2) * .18).toFixed(1) + 'px');
      b.style.setProperty('--my', ((e.clientY - r.top - r.height / 2) * .28).toFixed(1) + 'px');
    });
    b.addEventListener('pointerleave', () => { b.style.setProperty('--mx', '0px'); b.style.setProperty('--my', '0px'); });
  });
}

const ticks = [...document.querySelectorAll('.ticks span')];
const steps = [...document.querySelectorAll('.step')];
let stepIdx = -2;
function setStep(p) {
  const idx = p < .2 ? -1 : p < .4 ? 0 : p < .6 ? 1 : p < .8 ? 2 : 3;
  if (idx === stepIdx) return;
  stepIdx = idx;
  steps.forEach((s, i) => s.classList.toggle('on', i === Math.max(0, idx)));
  ticks.forEach((t, i) => t.classList.toggle('on', i <= idx));
}

/* =====================================================================
   3D: a Vietnamese tube house on a wet street at night
   ===================================================================== */
const canvas = document.getElementById('scene');
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
  if (!renderer.getContext()) throw new Error('no gl');
} catch (err) {
  document.body.classList.add('no-webgl');
  steps.forEach(s => s.classList.add('on'));
  throw err;
}

const LOW = coarse || innerWidth < 768;
renderer.setPixelRatio(Math.min(devicePixelRatio, LOW ? 1.25 : 1.5));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.localClippingEnabled = true;

const scene = new THREE.Scene();
const BG = new THREE.Color(0x070c18);
scene.background = BG;
scene.fog = new THREE.FogExp2(0x0a1222, 0.0085);
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(renderer), 0.04).texture;

const camera = new THREE.PerspectiveCamera(32, innerWidth / innerHeight, 0.1, 400);

/* ---------- procedural textures ---------- */
function cnv(w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}
const rnd = (a, b) => a + Math.random() * (b - a);

function grime(g, w, h, base, streak = .28) {
  g.fillStyle = base; g.fillRect(0, 0, w, h);
  for (let i = 0; i < w * h / 90; i++) {
    g.fillStyle = `rgba(0,0,0,${rnd(0, .06)})`;
    g.fillRect(rnd(0, w), rnd(0, h), rnd(1, 3), rnd(1, 3));
  }
  for (let i = 0; i < w / 6; i++) {
    const x = rnd(0, w), len = rnd(h * .1, h * .6), y = rnd(0, h * .7);
    const gr = g.createLinearGradient(0, y, 0, y + len);
    gr.addColorStop(0, `rgba(30,24,16,${rnd(.05, streak)})`); gr.addColorStop(1, 'rgba(30,24,16,0)');
    g.fillStyle = gr; g.fillRect(x, y, rnd(2, 9), len);
  }
}
const facadeTex = cnv(512, 512, (g, w, h) => grime(g, w, h, '#cbbf98'));
facadeTex.wrapS = facadeTex.wrapT = THREE.RepeatWrapping;
const concreteTex = cnv(512, 512, (g, w, h) => {
  grime(g, w, h, '#8a8781', .35);
  for (let i = 0; i < 40; i++) {
    g.fillStyle = `rgba(${rnd(60, 120)},${rnd(60, 110)},${rnd(55, 100)},.18)`;
    g.beginPath(); g.ellipse(rnd(0, w), rnd(0, h), rnd(10, 60), rnd(8, 40), 0, 0, 6.3); g.fill();
  }
});
concreteTex.wrapS = concreteTex.wrapT = THREE.RepeatWrapping;
const shutterTex = cnv(64, 256, (g, w, h) => {
  for (let y = 0; y < h; y += 8) {
    const gr = g.createLinearGradient(0, y, 0, y + 8);
    gr.addColorStop(0, '#9aa1a8'); gr.addColorStop(.5, '#6c737a'); gr.addColorStop(1, '#41474d');
    g.fillStyle = gr; g.fillRect(0, y, w, 8);
  }
});
const signTex = cnv(1024, 160, (g, w, h) => {
  const gr = g.createLinearGradient(0, 0, 0, h);
  gr.addColorStop(0, '#b3161f'); gr.addColorStop(1, '#7c0d14');
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
  g.strokeStyle = '#f6d36b'; g.lineWidth = 6; g.strokeRect(10, 10, w - 20, h - 20);
  g.fillStyle = '#ffe9a6'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.font = '800 78px "Be Vietnam Pro", Arial, sans-serif';
  g.fillText('TẠP HOÁ MINH AN', w / 2, h / 2 + 4);
});
const tileTex = cnv(256, 256, (g, w, h) => {
  g.fillStyle = '#5b4a45'; g.fillRect(0, 0, w, h);
  g.strokeStyle = 'rgba(20,14,12,.7)'; g.lineWidth = 3;
  for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(i * 64, 0); g.lineTo(i * 64, h); g.stroke(); g.beginPath(); g.moveTo(0, i * 64); g.lineTo(w, i * 64); g.stroke(); }
});
tileTex.wrapS = tileTex.wrapT = THREE.RepeatWrapping; tileTex.repeat.set(40, 1.2);
const asphaltTex = cnv(512, 512, (g, w, h) => {
  g.fillStyle = '#1b1d22'; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 9000; i++) { const v = rnd(10, 60); g.fillStyle = `rgba(${v},${v},${v + 5},.5)`; g.fillRect(rnd(0, w), rnd(0, h), 1.5, 1.5); }
  for (let i = 0; i < 14; i++) { g.fillStyle = 'rgba(0,0,0,.25)'; g.beginPath(); g.ellipse(rnd(0, w), rnd(0, h), rnd(20, 90), rnd(10, 40), rnd(0, 3), 0, 6.3); g.fill(); }
});
asphaltTex.wrapS = asphaltTex.wrapT = THREE.RepeatWrapping; asphaltTex.repeat.set(12, 2);

/* neighbour facades: wall colour + lit/unlit windows, with matching emissive map */
const PASTEL = ['#b9c4b1', '#d0b7a5', '#a9b8c6', '#cdbf8e', '#c7c2bb', '#b7a9c4', '#d6c7a2'];
function neighbourTextures(floors, color) {
  const fpx = 128, W = 256, H = floors * fpx;
  const lit = [];
  const map = cnv(W, H, (g) => {
    grime(g, W, H, color, .32);
    for (let f = 0; f < floors; f++) {
      const y = H - (f + 1) * fpx;
      g.fillStyle = 'rgba(0,0,0,.22)'; g.fillRect(0, y + fpx - 10, W, 10);
      const on = Math.random() < .45;
      lit.push(on);
      if (f === 0) {
        g.fillStyle = on ? '#6b5a44' : '#2a2c31'; g.fillRect(24, y + 24, W - 48, fpx - 24);
      } else {
        g.fillStyle = on ? '#8a6c46' : '#1c2230'; g.fillRect(40, y + 26, W - 80, fpx - 56);
        g.strokeStyle = '#2b2b2b'; g.lineWidth = 4; g.strokeRect(40, y + 26, W - 80, fpx - 56);
        g.beginPath(); g.moveTo(W / 2, y + 26); g.lineTo(W / 2, y + fpx - 30); g.stroke();
      }
    }
  });
  const emi = cnv(W, H, (g) => {
    g.fillStyle = '#000'; g.fillRect(0, 0, W, H);
    for (let f = 0; f < floors; f++) {
      if (!lit[f]) continue;
      const y = H - (f + 1) * fpx;
      const warm = Math.random() < .75 ? '#ffb45e' : '#bfe0ff';
      g.fillStyle = warm;
      if (f === 0) g.fillRect(24, y + 24, W - 48, fpx - 24);
      else { g.fillRect(42, y + 28, W / 2 - 44, fpx - 60); g.fillRect(W / 2 + 2, y + 28, W / 2 - 44, fpx - 60); }
    }
  });
  return { map, emi };
}

/* ---------- materials ---------- */
const clipSolid = new THREE.Plane(new THREE.Vector3(0, 1, 0), 1);   // keeps y > s
const clipXray = new THREE.Plane(new THREE.Vector3(0, -1, 0), -1);  // keeps y < s
function std(o) {
  const m = new THREE.MeshStandardMaterial(o);
  m.envMapIntensity = o.envMapIntensity ?? .25;
  return m;
}
const M = {
  facade: std({ map: facadeTex, roughness: .92 }),
  trim: std({ color: 0xe6e0d2, roughness: .8 }),
  side: std({ map: concreteTex, roughness: .95 }),
  slab: std({ color: 0xb8b2a6, roughness: .9 }),
  glass: std({ color: 0x1b2433, emissive: 0xffb466, emissiveIntensity: 1.6, roughness: .12, metalness: .5, envMapIntensity: 1 }),
  glassDim: std({ color: 0x141b28, emissive: 0x9cc8ff, emissiveIntensity: .35, roughness: .1, metalness: .6, envMapIntensity: 1 }),
  frame: std({ color: 0x2a2d33, roughness: .5, metalness: .6 }),
  rail: std({ color: 0x23262b, roughness: .45, metalness: .8 }),
  shutter: std({ map: shutterTex, roughness: .5, metalness: .7 }),
  shop: std({ color: 0x2a1f16, emissive: 0xffa04a, emissiveIntensity: .9, roughness: .9 }),
  sign: std({ map: signTex, emissive: 0xffffff, emissiveMap: signTex, emissiveIntensity: 1.25, roughness: .6 }),
  steel: std({ color: 0xd9dde2, roughness: .22, metalness: 1, envMapIntensity: 1.6 }),
  ac: std({ color: 0xd4d6d8, roughness: .55 }),
  pole: std({ color: 0x8c8a84, roughness: .9 }),
  cable: std({ color: 0x0d0e10, roughness: .6 }),
  meter: std({ color: 0xa8aeb3, roughness: .6, metalness: .3 }),
  lamp: new THREE.MeshBasicMaterial({ color: new THREE.Color(2.2, 1.5, .8), toneMapped: false }),
  tile: std({ map: tileTex, roughness: .55 }),
  plant: std({ color: 0x2c4a2a, roughness: .9 }),
};
// street copies are made before the house materials get their clipping plane
const MS = { side: M.side.clone(), slab: M.slab.clone(), rail: M.rail.clone(), frame: M.frame.clone() };
const houseMats = [M.facade, M.trim, M.side, M.slab, M.glass, M.glassDim, M.frame, M.rail, M.shutter, M.shop, M.sign, M.steel, M.ac];
houseMats.forEach(m => { m.clippingPlanes = [clipSolid]; m.clipShadows = false; });

/* x-ray: fresnel hologram with scan lines, used for structure + interior */
const xrayUniforms = { uTime: { value: 0 }, uColor: { value: new THREE.Color(0x6fc3ff) }, uFade: { value: 1 } };
const xrayMat = new THREE.ShaderMaterial({
  uniforms: xrayUniforms, transparent: true, depthWrite: false, side: THREE.DoubleSide,
  blending: THREE.AdditiveBlending, clipping: true, clippingPlanes: [clipXray],
  vertexShader: `
    #include <clipping_planes_pars_vertex>
    varying vec3 vN; varying vec3 vV; varying vec3 vW;
    void main(){
      vec4 wp = modelMatrix * vec4(position,1.0); vW = wp.xyz;
      vec4 mvPosition = viewMatrix * wp;
      vN = normalize(normalMatrix * normal); vV = -mvPosition.xyz;
      gl_Position = projectionMatrix * mvPosition;
      #include <clipping_planes_vertex>
    }`,
  fragmentShader: `
    #include <clipping_planes_pars_fragment>
    uniform float uTime; uniform vec3 uColor; uniform float uFade;
    varying vec3 vN; varying vec3 vV; varying vec3 vW;
    void main(){
      #include <clipping_planes_fragment>
      float f = clamp(1.0 - abs(dot(normalize(vN), normalize(vV))), 0.0, 1.0);
      f = pow(f, 2.2);
      float lines = smoothstep(.92, 1.0, sin(vW.y * 18.0 - uTime * 3.0) * .5 + .5) * .25;
      vec3 c = uColor * (0.006 + f * 0.16 + lines * f * .5);
      gl_FragColor = vec4(c * uFade, 1.0);
    }`
});
const xrayLineMat = new THREE.LineBasicMaterial({
  color: new THREE.Color(0x8fd3ff), transparent: true, opacity: .32,
  blending: THREE.AdditiveBlending, depthWrite: false, clippingPlanes: [clipXray]
});
const interiorLineMat = xrayLineMat.clone();
interiorLineMat.color = new THREE.Color(0xc7e6ff).multiplyScalar(1.15);
interiorLineMat.opacity = .75;
interiorLineMat.clippingPlanes = [clipXray];

/* ---------- builders ---------- */
const W = 4.5, D = 12, FH = 3.3, FLOORS = 4, TOP = FH * FLOORS, FZ = D / 2;
const house = new THREE.Group(); scene.add(house);
const structGeos = [], interiorGeos = [];

function box(w, h, d, x, y, z, mat, { parent = house, shadow = true, xray = true, interior = false } = {}) {
  const geo = new THREE.BoxGeometry(w, h, d);
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  if (shadow) { m.castShadow = true; m.receiveShadow = true; }
  if (!interior) parent.add(m);
  if (xray || interior) (interior ? interiorGeos : structGeos).push({ geo, pos: new THREE.Vector3(x, y, z) });
  return m;
}
function cyl(rt, rb, h, x, y, z, mat, rot, opts = {}) {
  const geo = new THREE.CylinderGeometry(rt, rb, h, 24);
  if (rot) geo.rotateZ(rot);
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z); m.castShadow = m.receiveShadow = true;
  if (!opts.interior) (opts.parent || house).add(m);
  if (opts.xray !== false) (opts.interior ? interiorGeos : structGeos).push({ geo, pos: new THREE.Vector3(x, y, z) });
  return m;
}
function merged(list, mat, parent) {
  const geos = list.map(({ g, x, y, z }) => g.clone().translate(x, y, z));
  const m = new THREE.Mesh(mergeGeometries(geos), mat);
  m.castShadow = m.receiveShadow = true;
  parent.add(m);
  return geos;
}

/* structure */
box(.22, TOP, D, -W / 2 + .11, TOP / 2, 0, M.side);
box(.22, TOP, D, W / 2 - .11, TOP / 2, 0, M.side);
box(W, TOP, .22, 0, TOP / 2, -D / 2 + .11, M.side);
facadeTex.repeat.set(1, 1);
for (let i = 0; i <= FLOORS; i++) box(W, .25, D, 0, i * FH, 0, M.slab, { shadow: i === FLOORS });

const floorStrips = [];
for (let i = 0; i < FLOORS; i++) {
  const b = i * FH;
  // pillars and beam
  box(.36, FH, .36, -W / 2 + .18, b + FH / 2, FZ - .18, M.facade);
  box(.36, FH, .36, W / 2 - .18, b + FH / 2, FZ - .18, M.facade);
  box(W, .5, .4, 0, b + FH - .25, FZ - .2, M.trim);
  // cyan strip for the "declare" step
  const strip = new THREE.Mesh(new THREE.BoxGeometry(W + .02, .05, .05),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(0x6fc3ff), toneMapped: false, transparent: true, opacity: 0 }));
  strip.position.set(0, b + FH - .52, FZ + .02); house.add(strip); floorStrips.push(strip);

  if (i === 0) {
    box(W - .72, FH * .36, .08, 0, b + FH - .95 - FH * .18, FZ - .25, M.shutter);
    box(W - .72, FH - .5, .05, 0, b + (FH - .5) / 2, FZ - 3.2, M.shop, { xray: false });
    const sign = box(W + .2, .72, .14, 0, b + FH - .6, FZ + .12, M.sign, { xray: false });
    sign.material = [M.trim, M.trim, M.trim, M.trim, M.sign, M.trim];
  } else {
    box(W - .72, 1.0, .2, 0, b + .5 + .12, FZ - .3, M.facade);
    const gh = FH - 1.75;
    box(W - .8, gh, .06, 0, b + 1.12 + gh / 2, FZ - .32, i === 2 ? M.glassDim : M.glass, { shadow: false });
    // window mullions
    const mull = [];
    for (const x of [-(W - .8) / 2, -(W - .8) / 6, (W - .8) / 6, (W - .8) / 2]) mull.push({ g: new THREE.BoxGeometry(.06, gh, .1), x, y: b + 1.12 + gh / 2, z: FZ - .27 });
    mull.push({ g: new THREE.BoxGeometry(W - .8, .06, .1), x: 0, y: b + 1.12 + gh, z: FZ - .27 });
    mull.push({ g: new THREE.BoxGeometry(W - .8, .06, .1), x: 0, y: b + 1.12, z: FZ - .27 });
    merged(mull, M.frame, house);
    // balcony
    box(W, .16, 1.15, 0, b + .08, FZ + .57, M.trim);
    const rails = [{ g: new THREE.BoxGeometry(W, .06, .06), x: 0, y: b + 1.08, z: FZ + 1.1 }];
    for (let k = 0; k <= 17; k++) rails.push({ g: new THREE.BoxGeometry(.035, .95, .035), x: -W / 2 + .05 + k * (W - .1) / 17, y: b + .6, z: FZ + 1.1 });
    for (const sx of [-1, 1]) rails.push({ g: new THREE.BoxGeometry(.06, .06, 1.1), x: sx * (W / 2 - .03), y: b + 1.08, z: FZ + .57 });
    merged(rails, M.rail, house);
    // AC unit + plant pot on balconies
    box(.82, .56, .3, 1.45, b + .45, FZ + .35, M.ac);
    if (i !== 2) { cyl(.2, .15, .35, -1.6, b + .33, FZ + .8, M.facade, 0, { xray: false }); cyl(.3, .25, .55, -1.6, b + .75, FZ + .8, M.plant, 0, { xray: false }); }
  }
}
// roof: parapet, stair hut, stainless water tank (very Hanoi), antenna
const R = TOP;
box(W, .9, .18, 0, R + .45, FZ - .09, M.facade);
box(.18, .9, D, -W / 2 + .09, R + .45, 0, M.side);
box(.18, .9, D, W / 2 - .09, R + .45, 0, M.side);
box(W * .55, 2.4, 3.2, -W * .2, R + 1.2, -D / 2 + 1.8, M.side);
box(1.6, .5, 1.1, 1.2, R + .25, -.5, M.frame);
cyl(.62, .62, 1.9, 1.2, R + 1.15, -.5, M.steel, Math.PI / 2);
cyl(.012, .012, 2.6, -1.2, R + 1.3, 1.5, M.frame, 0, { xray: false });

/* interior (only visible in the x-ray) */
const I = { interior: true };
// staircase along the back-left wall
for (let f = 0; f < FLOORS; f++) for (let k = 0; k < 11; k++)
  box(1.0, .3, .3, -W / 2 + .7, f * FH + .15 + k * .3, -1 - k * .3, null, I);
// ground floor: motorbikes + shop shelves
for (const z of [3.2, 1.6]) {
  box(.32, .55, 1.5, 1.1, .75, z, null, I);
  for (const dz of [-.65, .65]) { const g = new THREE.TorusGeometry(.3, .07, 10, 24); g.rotateY(Math.PI / 2); interiorGeos.push({ geo: g, pos: new THREE.Vector3(1.1, .32, z + dz) }); }
}
box(.4, 2.2, 3.5, W / 2 - .45, 1.1, -2.5, null, I);
box(.25, .2, .14, 1.85, .5, 4.2, null, I); // charger
// floor 1: kitchen
const f1 = FH;
box(2.6, .9, .6, .6, f1 + .45, -3.6, null, I);
box(.7, 1.8, .7, -.2, f1 + .9, -4.6, null, I);
box(.5, .1, .4, 1.4, f1 + .95, -3.6, null, I);
box(.14, .1, .05, 1.95, f1 + 1.15, -3.32, null, I); // socket strip
box(2.2, .45, .9, .3, f1 + .3, 2.4, null, I); // dining table
// floor 2: living room + extinguisher
const f2 = FH * 2;
box(2.2, .45, .9, .6, f2 + .25, 2.8, null, I);
box(1.6, .9, .1, .6, f2 + 1.3, 4.9, null, I);
cyl(.12, .12, .55, -1.75, f2 + .3, 2.2, null, 0, I);
// floor 3: bedroom + boxes blocking the stairs
const f3 = FH * 3;
box(1.8, .5, 2.1, .9, f3 + .3, 1.8, null, I);
box(.6, 2.1, 1.6, 1.7, f3 + 1.05, -2.2, null, I);
for (let k = 0; k < 5; k++) box(.55, .45, .5, -W / 2 + .7 + (k % 2) * .1, f3 + .25 + Math.floor(k / 2) * .45, -1.4 - k * .25, null, I);

/* x-ray meshes (merged into two draw calls each) */
function buildXray(list, lineMat) {
  const geos = list.map(({ geo, pos }) => {
    const g = geo.clone().toNonIndexed(); g.translate(pos.x, pos.y, pos.z);
    g.deleteAttribute('uv'); return g;
  });
  const mesh = new THREE.Mesh(mergeGeometries(geos), xrayMat);
  const lines = new THREE.LineSegments(mergeGeometries(list.map(({ geo, pos }) => new THREE.EdgesGeometry(geo, 30).translate(pos.x, pos.y, pos.z))), lineMat);
  mesh.renderOrder = 2; lines.renderOrder = 3;
  house.add(mesh, lines);
}
buildXray(structGeos, xrayLineMat);
buildXray(interiorGeos, interiorLineMat);

/* lights inside the house */
const interiorLights = [];
for (let i = 0; i < FLOORS; i++) {
  const l = new THREE.PointLight(0xffb36b, i === 0 ? 22 : 14, 10, 2);
  l.position.set(0, i * FH + 2.3, FZ - 1.6);
  house.add(l); interiorLights.push(l);
}

/* ---------- street ---------- */
const street = new THREE.Group(); scene.add(street);
// neighbours, both sides, varied heights and colours
const NB = [[-4.6, 2], [-9.25, 3], [-13.9, 5], [-18.5, 3], [-23.2, 6], [4.6, 3], [9.25, 2], [13.9, 5], [18.5, 3], [23.2, 4]];
const neighbourFronts = [];
NB.forEach(([x, n], k) => {
  const w = 4.55, h = n * FH, d = 11 + (k % 3) * .6;
  const { map, emi } = neighbourTextures(n, PASTEL[k % PASTEL.length]);
  const front = std({ map, emissive: 0xffffff, emissiveMap: emi, emissiveIntensity: .55, roughness: .9 });
  neighbourFronts.push(front);
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), [MS.side, MS.side, MS.slab, MS.slab, front, MS.side]);
  m.position.set(x, h / 2, FZ - d / 2 - (k % 2) * .15);
  m.castShadow = m.receiveShadow = true; street.add(m);
  // balconies on upper floors
  for (let f = 1; f < n; f++) {
    const s = new THREE.Mesh(new THREE.BoxGeometry(w - .1, .14, .9), MS.slab);
    s.position.set(x, f * FH, FZ + .45 - (k % 2) * .15); s.castShadow = s.receiveShadow = true; street.add(s);
    const r = new THREE.Mesh(new THREE.BoxGeometry(w - .1, .05, .05), MS.rail);
    r.position.set(x, f * FH + .95, FZ + .88 - (k % 2) * .15); street.add(r);
  }
});
// distant city silhouettes
const farMat = std({ color: 0x10172a, emissive: 0x2a3550, emissiveIntensity: .25, roughness: 1 });
for (let i = 0; i < 46; i++) {
  const h = rnd(8, 34), w = rnd(4, 9);
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, rnd(4, 9)), farMat);
  m.position.set(rnd(-70, 70), h / 2, rnd(-30, -80)); street.add(m);
}
// sidewalk, kerb, road
const walk = new THREE.Mesh(new THREE.BoxGeometry(120, .16, 2.4), M.tile);
walk.position.set(0, .08, FZ + 1.2); walk.receiveShadow = true; street.add(walk);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), std({ color: 0x0c0f15, roughness: 1 }));
ground.rotation.x = -Math.PI / 2; ground.position.y = -.01; ground.receiveShadow = true; scene.add(ground);
const roadDepth = 9;
let mirror = null;
if (!LOW) {
  mirror = new Reflector(new THREE.PlaneGeometry(120, roadDepth), {
    textureWidth: Math.floor(innerWidth * .5), textureHeight: Math.floor(innerHeight * .5), color: 0x8a8f99, clipBias: .003
  });
  mirror.rotation.x = -Math.PI / 2; mirror.position.set(0, .005, FZ + 2.4 + roadDepth / 2); scene.add(mirror);
}
const road = new THREE.Mesh(new THREE.PlaneGeometry(120, roadDepth),
  std({ map: asphaltTex, roughness: .32, metalness: .1, transparent: !!mirror, opacity: mirror ? .78 : 1, envMapIntensity: .8 }));
road.rotation.x = -Math.PI / 2; road.position.set(0, .02, FZ + 2.4 + roadDepth / 2); road.receiveShadow = true; street.add(road);

// concrete electricity pole, tangle of cables, meter boxes: the classic Vietnamese street
const PX = -3.5, PZ = FZ + 1.9;
const pole = new THREE.Mesh(new THREE.CylinderGeometry(.13, .2, 10, 16), M.pole);
pole.position.set(PX, 5, PZ); pole.castShadow = true; street.add(pole);
const arm = new THREE.Mesh(new THREE.BoxGeometry(2.2, .14, .14), M.pole);
arm.position.set(PX, 8.6, PZ); street.add(arm);
const meterGroup = new THREE.Group(); meterGroup.position.set(PX, 4.6, PZ); street.add(meterGroup);
[[0, 0, .3], [.34, .2, .25], [-.34, .1, .25], [.05, -.55, .25], [.36, -.42, .22]].forEach(([x, y, s]) => {
  const b = new THREE.Mesh(new THREE.BoxGeometry(s * 1.1, s * 1.4, .18), M.meter);
  b.position.set(x, y, .2); b.castShadow = true; meterGroup.add(b);
});
const cableGeos = [];
function sag(a, b, drop, seg = 24) {
  const pts = [];
  for (let i = 0; i <= seg; i++) {
    const t = i / seg, p = new THREE.Vector3().lerpVectors(a, b, t);
    p.y -= Math.sin(Math.PI * t) * drop; pts.push(p);
  }
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), seg, .022, 5, false);
}
for (let k = 0; k < 9; k++) {
  const y = 8.2 + rnd(-.5, .4);
  cableGeos.push(sag(new THREE.Vector3(PX - .9, y, PZ), new THREE.Vector3(-40, y + rnd(-1, 1), PZ + rnd(-.4, .4)), rnd(.8, 1.6), 40));
  cableGeos.push(sag(new THREE.Vector3(PX + .9, y, PZ), new THREE.Vector3(40, y + rnd(-1, 1), PZ + rnd(-.4, .4)), rnd(.8, 1.6), 40));
}
for (let k = 0; k < 7; k++) {
  const tx = rnd(-1.8, 1.8), ty = rnd(3.6, 7.5);
  cableGeos.push(sag(new THREE.Vector3(PX + rnd(-.2, .2), 4.6 + rnd(-.3, .5), PZ + .1), new THREE.Vector3(tx, ty, FZ + .05), rnd(.2, .6)));
  cableGeos.push(sag(new THREE.Vector3(PX, 8.4, PZ), new THREE.Vector3(PX + rnd(-.1, .1), 4.9, PZ + .15), .05, 8));
}
const cables = new THREE.Mesh(mergeGeometries(cableGeos), M.cable);
cables.castShadow = true; street.add(cables);
// street lamp on the pole
const lampArm = new THREE.Mesh(new THREE.CylinderGeometry(.04, .04, 2.2, 8), MS.frame);
lampArm.rotation.z = Math.PI / 2 - .18; lampArm.position.set(PX + 1.05, 7.3, PZ + .1); street.add(lampArm);
const lampHead = new THREE.Mesh(new THREE.BoxGeometry(.55, .1, .26), M.lamp);
lampHead.position.set(PX + 2.1, 7.45, PZ + .1); street.add(lampHead);

/* ---------- lighting ---------- */
scene.add(new THREE.HemisphereLight(0x2b3f6e, 0x0b0a08, .55));
const moon = new THREE.DirectionalLight(0x9db4ff, .9);
moon.position.set(-18, 30, 14); moon.castShadow = true;
moon.shadow.mapSize.set(LOW ? 1024 : 2048, LOW ? 1024 : 2048);
Object.assign(moon.shadow.camera, { left: -22, right: 22, top: 22, bottom: -6, near: 1, far: 80 });
moon.shadow.bias = -.0004; moon.shadow.normalBias = .02;
scene.add(moon);
const spot = new THREE.SpotLight(0xffb36b, 260, 28, .75, .65, 2);
spot.position.set(PX + 2.1, 7.35, PZ + .1);
spot.target.position.set(PX + 2.6, 0, PZ + 2.5);
spot.castShadow = !LOW; spot.shadow.mapSize.set(1024, 1024); spot.shadow.bias = -.0005;
scene.add(spot, spot.target);
const danger = new THREE.PointLight(0xff3b2a, 0, 7, 2);
danger.position.set(PX + .2, 4.6, PZ + .6); scene.add(danger);
const rim = new THREE.DirectionalLight(0x5c7cff, .5);
rim.position.set(20, 12, -20); scene.add(rim);

/* ---------- glow sprite texture ---------- */
const GLOW = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'), grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(.2, 'rgba(255,255,255,.6)');
  grd.addColorStop(.55, 'rgba(255,255,255,.12)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd; g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
})();

/* ---------- scan rig ---------- */
const scan = new THREE.Group(); house.add(scan);
const scanCol = new THREE.Color(0x7fd0ff).multiplyScalar(3.2);
const ringMat = new THREE.MeshBasicMaterial({ color: scanCol, toneMapped: false, transparent: true });
const RW = W + 1.6, RD = D + 3.2;
const ring = [
  new THREE.Mesh(new THREE.BoxGeometry(RW, .05, .05), ringMat), new THREE.Mesh(new THREE.BoxGeometry(RW, .05, .05), ringMat),
  new THREE.Mesh(new THREE.BoxGeometry(.05, .05, RD), ringMat), new THREE.Mesh(new THREE.BoxGeometry(.05, .05, RD), ringMat)
];
ring[0].position.set(0, 0, .8 + RD / 2); ring[1].position.set(0, 0, .8 - RD / 2);
ring[2].position.set(-RW / 2, 0, .8); ring[3].position.set(RW / 2, 0, .8);
scan.add(...ring);
const sheetMat = new THREE.MeshBasicMaterial({ color: 0x5cb8ff, transparent: true, opacity: .07, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
const sheet = new THREE.Mesh(new THREE.PlaneGeometry(RW, RD), sheetMat);
sheet.rotation.x = -Math.PI / 2; sheet.position.z = .8; scan.add(sheet);
const scanLight = new THREE.PointLight(0x7fd0ff, 0, 9, 2); scan.add(scanLight);

/* ground pulse when the house is safe */
const safeRing = new THREE.Mesh(new THREE.RingGeometry(.96, 1, 128),
  new THREE.MeshBasicMaterial({ color: new THREE.Color(0x2fd27a).multiplyScalar(2.5), toneMapped: false, transparent: true, opacity: 0, depthWrite: false }));
safeRing.rotation.x = -Math.PI / 2; safeRing.position.set(0, .2, FZ + 1); scene.add(safeRing);

/* ---------- hotspots ---------- */
const C = { red: new THREE.Color(1, .22, .18), warn: new THREE.Color(1, .62, .12), ok: new THREE.Color(.18, .9, .45) };
const HS = [
  { p: [1.85, .55, 4.2], name: 'Sạc xe điện qua đêm', sev: 'high', icon: 'lightning' },
  { p: [1.95, FH + 1.15, -3.3], name: 'Ổ cắm quá tải', sev: 'high', icon: 'plugs' },
  { p: [-1.75, FH * 2 + .35, 2.2], name: 'Bình chữa cháy hết hạn', sev: 'mid', icon: 'fire-extinguisher' },
  { p: [-1.4, FH * 3 + .7, -1.8], name: 'Lối thoát bị chặn', sev: 'high', icon: 'door-open' },
  { p: [PX + .1, 4.65, PZ + .35], name: 'Dây điện lão hóa', sev: 'mid', icon: 'circuitry', outside: true }
];
const labelsEl = document.getElementById('labels');
HS.forEach(h => {
  h.v = new THREE.Vector3(...h.p);
  const parent = h.outside ? scene : house;
  h.core = new THREE.Mesh(new THREE.SphereGeometry(.09, 16, 16), new THREE.MeshBasicMaterial({ toneMapped: false, transparent: true, depthTest: false }));
  h.glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLOW, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false, toneMapped: false }));
  h.ring = new THREE.Mesh(new THREE.RingGeometry(.26, .3, 48), new THREE.MeshBasicMaterial({ transparent: true, side: THREE.DoubleSide, depthWrite: false, depthTest: false, toneMapped: false }));
  [h.core, h.glow, h.ring].forEach(o => { o.position.copy(h.v); o.renderOrder = 10; parent.add(o); });
  h.col = new THREE.Color();
  h.el = document.createElement('div'); h.el.className = 'hs-label'; labelsEl.appendChild(h.el);
  h.state = '';
});

/* ---------- embers & sparks ---------- */
const EN = LOW ? 260 : 700;
const ePos = new Float32Array(EN * 3), eSeed = new Float32Array(EN);
for (let i = 0; i < EN; i++) {
  const nearMeter = i < EN * .35;
  ePos[i * 3] = nearMeter ? PX + rnd(-.4, .6) : rnd(-9, 9);
  ePos[i * 3 + 1] = nearMeter ? 4.4 : rnd(0, 3);
  ePos[i * 3 + 2] = nearMeter ? PZ + .3 : rnd(FZ - 4, FZ + 9);
  eSeed[i] = Math.random();
}
const eGeo = new THREE.BufferGeometry();
eGeo.setAttribute('position', new THREE.BufferAttribute(ePos, 3));
eGeo.setAttribute('aSeed', new THREE.BufferAttribute(eSeed, 1));
const emberMat = new THREE.ShaderMaterial({
  uniforms: { uTime: { value: 0 }, uOpacity: { value: 1 }, uPixel: { value: renderer.getPixelRatio() } },
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  vertexShader: `
    attribute float aSeed; uniform float uTime; uniform float uPixel; varying float vA; varying float vS;
    void main(){
      float life = fract(uTime * (0.05 + aSeed * 0.07) + aSeed * 9.17);
      vec3 p = position;
      p.y += life * (8.0 + aSeed * 10.0);
      p.x += sin(uTime * 0.9 + aSeed * 40.0) * 0.7 * life + life * 1.2;
      p.z += cos(uTime * 0.7 + aSeed * 23.0) * 0.5 * life;
      vec4 mv = modelViewMatrix * vec4(p, 1.0);
      gl_Position = projectionMatrix * mv;
      gl_PointSize = min((2.0 + aSeed * 4.0) * uPixel * (1.0 - life * .7) * (60.0 / -mv.z), 7.0 * uPixel);
      vA = (1.0 - life) * smoothstep(0.0, 0.06, life) * (0.6 + 0.4 * sin(uTime * 12.0 + aSeed * 60.0));
      vS = aSeed;
    }`,
  fragmentShader: `
    uniform float uOpacity; varying float vA; varying float vS;
    void main(){
      float d = length(gl_PointCoord - .5);
      float a = smoothstep(.5, .0, d);
      vec3 c = mix(vec3(3.0, .9, .25), vec3(3.2, 1.8, .6), vS);
      gl_FragColor = vec4(c * a * vA * uOpacity, 1.0);
    }`
});
const embers = new THREE.Points(eGeo, emberMat); embers.frustumCulled = false; scene.add(embers);

/* ---------- post-processing ---------- */
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), .7, .5, .86);
composer.addPass(bloom);
const finish = new ShaderPass({
  uniforms: { tDiffuse: { value: null }, uTime: { value: 0 } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float uTime; varying vec2 vUv;
    void main(){
      vec2 o = (vUv - .5) * .0016;
      vec4 c = texture2D(tDiffuse, vUv);
      c.r = texture2D(tDiffuse, vUv + o).r; c.b = texture2D(tDiffuse, vUv - o).b;
      float v = smoothstep(1.05, .28, length((vUv - .5) * vec2(1.2, 1.0)));
      c.rgb *= mix(.42, 1.0, v);
      float n = fract(sin(dot(vUv * (uTime + 1.0), vec2(12.9898, 78.233))) * 43758.5453);
      c.rgb += (n - .5) * .018;
      gl_FragColor = c;
    }`
});
composer.addPass(finish);
composer.addPass(new OutputPass());

/* =====================================================================
   Scroll choreography
   ===================================================================== */
const S = { a: .38, d: 46, y: 2.4, ly: 8.2, q: 0, s: -.5, seen: -.5, classify: 0, fixed: 0, ember: 1, xr: 0 };
let sceneActive = true;
if (reduce) {
  Object.assign(S, { a: -.4, d: 36, y: 10, ly: 6.8, s: TOP + 2, seen: TOP + 2, classify: 1, ember: .3, xr: 1 });
  steps.forEach(s => s.classList.add('on'));
} else {
  gsap.registerPlugin(ScrollTrigger);
  const tl = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: '#journey', start: 'top top', end: 'bottom bottom', scrub: 1.2 } });
  tl.to(S, { a: .28, d: 42, y: 5, ly: 7.6, duration: 2, ease: 'power1.inOut' }, 0)
    .to(S, { q: 1, a: .12, d: 38, y: 6.5, duration: 2 }, 2)
    .to(S, { s: TOP + 2.2, seen: TOP + 2.2, xr: 1, a: -.4, y: 11, ly: 6.8, d: 38, duration: 2 }, 4)
    .to(S, { classify: 1, a: -.6, d: 31, y: 9, duration: 2 }, 6)
    .to(S, { fixed: 1, ember: 0, s: -.5, xr: 0, a: .3, d: 41, y: 5.5, ly: 7.4, duration: 2 }, 8);
  tl.eventCallback('onUpdate', () => setStep(tl.progress()));
  setStep(0);
  ScrollTrigger.create({ trigger: '#journey', start: 'top top', end: 'bottom top',
    onLeave: () => { sceneActive = false; }, onEnterBack: () => { sceneActive = true; } });
}

const ptr = { x: 0, y: 0, sx: 0, sy: 0 };
if (!reduce && !coarse) addEventListener('pointermove', e => { ptr.x = e.clientX / innerWidth - .5; ptr.y = e.clientY / innerHeight - .5; });

let vw = innerWidth, vh = innerHeight;
function resize() {
  vw = innerWidth; vh = innerHeight;
  renderer.setSize(vw, vh, false);
  composer.setSize(vw, vh);
  camera.aspect = vw / vh;
  emberMat.uniforms.uPixel.value = renderer.getPixelRatio();
  if (reduce) render(0, 0);
}
addEventListener('resize', resize);

const clamp01 = v => Math.max(0, Math.min(1, v));
const v3 = new THREE.Vector3();

function render(t, dt) {
  ptr.sx += (ptr.x - ptr.sx) * .04; ptr.sy += (ptr.y - ptr.sy) * .04;
  const wide = isWide();
  const a = S.a + (reduce ? 0 : Math.sin(t * .12) * .035) + ptr.sx * .1;
  const d = wide ? S.d : S.d * (1.12 + .5 * S.xr);
  camera.position.set(Math.sin(a) * d, S.y - ptr.sy * .9, FZ * .2 + Math.cos(a) * d);
  camera.lookAt(0, S.ly, FZ * .2);
  camera.setViewOffset(vw, vh, wide ? -vw * .19 : 0, wide ? 0 : vh * .2, vw, vh);

  // clipping height of the scan
  clipSolid.constant = -S.s; clipXray.constant = S.s;
  const sv = clamp01(Math.min(S.s + .5, TOP + 2.2 - S.s) / 1.2) * (S.s > -.4 ? 1 : 0);
  scan.position.y = S.s; scan.visible = sv > .01;
  ringMat.opacity = sv; sheetMat.opacity = .07 * sv; scanLight.intensity = 6 * sv;
  xrayUniforms.uTime.value = t;
  xrayUniforms.uFade.value = .6 + .4 * S.xr;

  // declare step: floor strips light in sequence
  floorStrips.forEach((st, i) => { st.material.opacity = clamp01(S.q * FLOORS - i) * (1 - S.xr); });

  // interior warmth and danger flicker
  const flick = reduce ? .6 : .55 + .45 * Math.abs(Math.sin(t * 7.3) * Math.sin(t * 3.1 + 1.7));
  danger.intensity = 9 * flick * S.ember * (1 - S.fixed);
  M.glass.emissiveIntensity = 1.6 + .4 * S.fixed;
  neighbourFronts.forEach(m => { m.emissiveIntensity = .55 - .35 * S.xr; });

  // hotspots
  HS.forEach((h, i) => {
    const seen = clamp01((S.seen - h.v.y) / .9);
    const fix = clamp01(S.fixed * HS.length - i);
    h.col.copy(C.red);
    if (h.sev === 'mid') h.col.lerp(C.warn, S.classify);
    h.col.lerp(C.ok, fix);
    const pulse = reduce ? .5 : (Math.sin(t * (fix > .5 ? 1.8 : 4.2) + i) + 1) / 2;
    h.core.material.color.copy(h.col).multiplyScalar(4); h.core.material.opacity = seen;
    h.glow.material.color.copy(h.col).multiplyScalar(2.2); h.glow.material.opacity = seen * (.5 + .4 * pulse);
    const gs = 1.1 + .6 * pulse; h.glow.scale.set(gs, gs, 1);
    h.ring.material.color.copy(h.col).multiplyScalar(3); h.ring.material.opacity = seen * (1 - pulse);
    const rs = 1 + pulse * 1.8; h.ring.scale.set(rs, rs, rs);
    h.ring.quaternion.copy(camera.quaternion);

    const lo = clamp01(S.classify * 2 - .6) * seen;
    if (lo > .01) {
      v3.copy(h.v); if (!h.outside) v3.applyMatrix4(house.matrixWorld);
      v3.project(camera);
      const x = (v3.x * .5 + .5) * vw, y = (-v3.y * .5 + .5) * vh;
      const flip = x > vw - (wide ? 290 : 170);
      h.el.style.transform = `translate(${flip ? x - 18 : x + 18}px, ${y - 15}px) translateX(${flip ? '-100%' : '0'})`;
      const st = fix > .5 ? 'ok' : (h.sev === 'mid' ? 'mid' : 'high');
      if (st !== h.state) {
        h.state = st;
        const color = st === 'ok' ? 'var(--ok)' : st === 'mid' ? 'var(--warn)' : '#ff5a52';
        const tag = st === 'ok' ? 'Đã khắc phục' : st === 'mid' ? 'Cần chú ý' : 'Nguy cơ cao';
        h.el.innerHTML = `<span style="color:${color};display:flex">${ICONS[st === 'ok' ? 'check-circle' : h.icon] || ''}</span>${h.name}<small>${tag}</small>`;
      }
    }
    h.el.style.opacity = lo.toFixed(3);
  });

  // safe pulse
  const sp = reduce ? .5 : (t * .35) % 1;
  safeRing.scale.setScalar(4 + sp * 14);
  safeRing.material.opacity = S.fixed * (1 - sp) * .9;

  emberMat.uniforms.uTime.value = t;
  emberMat.uniforms.uOpacity.value = S.ember;
  embers.visible = S.ember > .01;
  finish.uniforms.uTime.value = t % 10;

  composer.render(dt);
}

resize();
const clock = new THREE.Clock();
let first = true;
function loop() {
  requestAnimationFrame(loop);
  const dt = Math.min(clock.getDelta(), .05);
  if ((!sceneActive || document.hidden) && !first) return;
  render(clock.elapsedTime, dt);
  if (first) { first = false; canvas.classList.add('ready'); }
}
if (reduce) { render(0, 0); canvas.classList.add('ready'); } else loop();
