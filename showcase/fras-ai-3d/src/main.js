import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';

const ICONS = window.__ICONS || {};
const ASSETS = window.__ASSETS || {};
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const coarse = matchMedia('(pointer: coarse)').matches;
const isWide = () => innerWidth >= 768;

/* =====================================================================
   Page UI: smooth scroll, nav state, reveal, counters, marquee, magnetic
   ===================================================================== */
gsap.registerPlugin(ScrollTrigger);
let lenis = null;
if (!reduce) {
  lenis = new Lenis({ lerp: .085, wheelMultiplier: .9 });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add(t => lenis.raf(t * 1000));
  gsap.ticker.lagSmoothing(0);
  document.querySelectorAll('a[href^="#"]').forEach(a => a.addEventListener('click', e => {
    const id = a.getAttribute('href');
    if (id.length > 1 && document.querySelector(id)) { e.preventDefault(); lenis.scrollTo(id, { duration: 1.6 }); }
  }));
}

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
  // bento photos drift slightly under the cursor
  document.querySelectorAll('.cell.photo').forEach(c => {
    c.addEventListener('pointermove', e => {
      const r = c.getBoundingClientRect();
      c.style.backgroundPosition = `center, center, ${50 + ((e.clientX - r.left) / r.width - .5) * 6}% ${50 + ((e.clientY - r.top) / r.height - .5) * 6}%`;
    });
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
   WebGL: a real night photograph turned into a 2.5D scene.
   A depth map drives parallax, a shader performs the x-ray scan.
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
renderer.setPixelRatio(Math.min(devicePixelRatio, LOW ? 1.5 : 1.75));
renderer.outputColorSpace = THREE.SRGBColorSpace;

const IMG_ASPECT = 1165 / 864;
const loader = new THREE.TextureLoader();
const tex = (url, srgb) => new Promise(res => loader.load(url, t => {
  t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  t.minFilter = THREE.LinearFilter; t.generateMipmaps = false;
  t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
  res(t);
}));

const scene = new THREE.Scene();
const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

/* view state, animated by scroll */
const V = {
  zoom: 1.14, cx: .62, cy: .5,          // camera framing in image uv
  par: 0,                                // scroll-driven parallax push
  scan: -.05, seen: -.05, xr: 0,         // scan line (screen y, 0 bottom to 1 top)
  classify: 0, fixed: 0, ember: 1, boot: 0, grade: 0
};
const U = {
  tColor: { value: null }, tDepth: { value: null },
  uRes: { value: new THREE.Vector2(1, 1) }, uAspect: { value: IMG_ASPECT },
  uZoom: { value: V.zoom }, uCenter: { value: new THREE.Vector2(V.cx, V.cy) },
  uMouse: { value: new THREE.Vector2() }, uPar: { value: 0 },
  uScan: { value: 0 }, uXr: { value: 0 }, uTime: { value: 0 },
  uDanger: { value: 1 }, uFixed: { value: 0 }, uBoot: { value: 0 },
  uTexel: { value: new THREE.Vector2(1 / 1748, 1 / 1296) }
};

const COMMON = /* glsl */`
  uniform vec2 uRes; uniform float uAspect; uniform float uZoom; uniform vec2 uCenter;
  vec2 visible(){ float sa = uRes.x / uRes.y; return sa > uAspect ? vec2(1.0, uAspect / sa) : vec2(sa / uAspect, 1.0); }
  vec2 screenToImg(vec2 s){ return (s - .5) * visible() / uZoom + uCenter; }
  vec2 imgToScreen(vec2 u){ return (u - uCenter) * uZoom / visible() + .5; }
`;

const photoMat = new THREE.ShaderMaterial({
  uniforms: U, depthTest: false, depthWrite: false,
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
  fragmentShader: /* glsl */`
    ${COMMON}
    uniform sampler2D tColor; uniform sampler2D tDepth;
    uniform vec2 uMouse; uniform float uPar; uniform float uScan; uniform float uXr;
    uniform float uTime; uniform float uDanger; uniform float uFixed; uniform float uBoot; uniform vec2 uTexel;
    varying vec2 vUv;

    float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    float lum(vec3 c){ return dot(c, vec3(.299, .587, .114)); }

    vec2 parallax(vec2 uv){
      vec2 dir = uMouse * .014 + vec2(0.0, uPar);
      vec2 p = uv;
      for (int i = 0; i < 3; i++) {
        float d = texture2D(tDepth, p).r;
        p = uv + dir * (d - .55);
      }
      return clamp(p, vec2(.001), vec2(.999));
    }

    void main(){
      vec2 s = vUv;
      vec2 uv = parallax(screenToImg(s));
      float depth = texture2D(tDepth, uv).r;
      vec3 col = texture2D(tColor, uv).rgb;

      // night grade: lift warm windows, cool shadows
      float l = lum(col);
      col = mix(col * vec3(.86, .93, 1.08), col * vec3(1.06, .98, .9), smoothstep(.35, .8, l));
      col *= mix(1.0, 1.08, uFixed);

      // fire danger: flickering red glow from the meter box on the pole
      float flick = .6 + .4 * sin(uTime * 13.0) * sin(uTime * 5.3 + 1.7);
      float dz = length((uv - vec2(.437, .262)) * vec2(uAspect, 1.0));
      col += vec3(1.0, .28, .12) * exp(-dz * 22.0) * 1.15 * flick * uDanger;
      col += vec3(.9, .2, .1) * exp(-dz * 6.0) * .12 * uDanger;

      // x-ray: edge-detected hologram of the same photograph
      vec2 tx = uTexel * 1.4;
      float a = lum(texture2D(tColor, uv + vec2(-tx.x,  tx.y)).rgb), b = lum(texture2D(tColor, uv + vec2(0.0, tx.y)).rgb), c = lum(texture2D(tColor, uv + tx).rgb);
      float d0 = lum(texture2D(tColor, uv + vec2(-tx.x, 0.0)).rgb), f = lum(texture2D(tColor, uv + vec2(tx.x, 0.0)).rgb);
      float g = lum(texture2D(tColor, uv - tx).rgb), h = lum(texture2D(tColor, uv - vec2(0.0, tx.y)).rgb), k = lum(texture2D(tColor, uv + vec2(tx.x, -tx.y)).rgb);
      float gx = -a - 2.0 * d0 - g + c + 2.0 * f + k;
      float gy = -a - 2.0 * b - c + g + 2.0 * h + k;
      float edge = smoothstep(.08, .55, length(vec2(gx, gy)));
      vec2 gridUv = uv * vec2(uAspect, 1.0) * 46.0;
      vec2 gl = abs(fract(gridUv) - .5);
      float grid = smoothstep(.47, .5, max(gl.x, gl.y)) * .18;
      float scanlines = .5 + .5 * sin(s.y * uRes.y * 1.1 - uTime * 6.0);
      vec3 xray = vec3(.22, .62, 1.0) * (edge * 1.7 + l * .32 + grid) * (.75 + .25 * scanlines);
      xray += vec3(.1, .3, .6) * pow(depth, 3.0) * .25;
      xray = mix(xray, xray * vec3(.7, 1.1, .9), uFixed);

      float below = smoothstep(uScan + .004, uScan - .004, s.y);
      col = mix(col, xray, below * uXr);
      float band = exp(-abs(s.y - uScan) * 140.0) * step(.001, uXr);
      col += vec3(.45, .85, 1.0) * band * 1.6 + vec3(.2, .5, 1.0) * exp(-abs(s.y - uScan) * 22.0) * .25 * step(.001, uXr);

      // boot-in: black, then a fast scan reveals the photograph
      col *= smoothstep(0.0, .35, uBoot);

      // lens: vignette, grain
      vec2 q = s - .5;
      col *= mix(.38, 1.0, smoothstep(.9, .22, length(q * vec2(1.25, 1.0))));
      col += (hash(s * uRes + fract(uTime) * 100.0) - .5) * .035;
      gl_FragColor = vec4(col, 1.0);
    }`
});
const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), photoMat);
quad.frustumCulled = false;
scene.add(quad);

/* embers rising from the meter box, positioned in image space */
const EN = LOW ? 120 : 260;
const eSeed = new Float32Array(EN), ePos = new Float32Array(EN * 3);
for (let i = 0; i < EN; i++) eSeed[i] = Math.random();
const eGeo = new THREE.BufferGeometry();
eGeo.setAttribute('position', new THREE.BufferAttribute(ePos, 3));
eGeo.setAttribute('aSeed', new THREE.BufferAttribute(eSeed, 1));
const emberMat = new THREE.ShaderMaterial({
  uniforms: { ...U, uOpacity: { value: 1 }, uPixel: { value: renderer.getPixelRatio() } },
  transparent: true, depthTest: false, depthWrite: false, blending: THREE.AdditiveBlending,
  vertexShader: /* glsl */`
    ${COMMON}
    attribute float aSeed; uniform float uTime; uniform float uPixel; varying float vA; varying float vS;
    void main(){
      float life = fract(uTime * (.045 + aSeed * .06) + aSeed * 7.31);
      vec2 o = vec2(.437 + (fract(aSeed * 91.7) - .5) * .05, .262);
      o.y += life * (.35 + aSeed * .45);
      o.x += sin(uTime * .8 + aSeed * 40.0) * .03 * life + life * .05 * (aSeed - .3);
      vec2 sc = imgToScreen(o);
      gl_Position = vec4(sc * 2.0 - 1.0, 0.0, 1.0);
      gl_PointSize = (1.5 + aSeed * 3.5) * uPixel * uZoom * (1.0 - life * .6);
      vA = (1.0 - life) * smoothstep(0.0, .05, life) * (.55 + .45 * sin(uTime * 14.0 + aSeed * 50.0));
      vS = aSeed;
    }`,
  fragmentShader: /* glsl */`
    uniform float uOpacity; varying float vA; varying float vS;
    void main(){
      float d = length(gl_PointCoord - .5);
      float a = smoothstep(.5, .0, d);
      vec3 c = mix(vec3(2.4, .7, .2), vec3(2.6, 1.5, .5), vS);
      gl_FragColor = vec4(c * a * vA * uOpacity, 1.0);
    }`
});
const embers = new THREE.Points(eGeo, emberMat);
embers.frustumCulled = false;
scene.add(embers);

/* post: bloom on lamps, windows, scan band and embers */
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, cam));
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), .55, .6, .72);
composer.addPass(bloom);
composer.addPass(new OutputPass());

/* hotspots in image uv (y up) */
const HS = [
  { uv: [.47, .5], name: 'Dây điện chằng chịt, lão hóa', sev: 'high', icon: 'lightning' },
  { uv: [.65, .56], name: 'Bình chữa cháy hết hạn', sev: 'mid', icon: 'fire-extinguisher' },
  { uv: [.553, .418], name: 'Thiết bị điện quá tải', sev: 'mid', icon: 'circuitry' },
  { uv: [.86, .25], name: 'Ổ cắm quá tải trong kho', sev: 'high', icon: 'plugs' },
  { uv: [.63, .2], name: 'Lối thoát duy nhất bị khóa', sev: 'high', icon: 'door-open' }
];
const labelsEl = document.getElementById('labels');
HS.forEach(h => {
  h.el = document.createElement('div'); h.el.className = 'hs-label hs-pin'; labelsEl.appendChild(h.el);
  h.state = '';
});

/* ---------------- scroll choreography ---------------- */
let sceneActive = true;
if (reduce) {
  Object.assign(V, { zoom: 1.2, scan: 1.1, seen: 1.1, xr: 1, classify: 1, ember: .4, boot: 1 });
  steps.forEach(s => s.classList.add('on'));
} else {
  const tl = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: '#journey', start: 'top top', end: 'bottom bottom', scrub: true } });
  tl.to(V, { zoom: 1.3, cx: .66, cy: .5, par: .02, duration: 2, ease: 'power1.inOut' }, 0)
    .to(V, { zoom: 1.52, cx: .64, cy: .44, par: .035, duration: 2, ease: 'power1.inOut' }, 2)
    .to(V, { scan: 1.08, seen: 1.08, xr: 1, zoom: 1.3, cx: .64, cy: .46, par: .015, duration: 2 }, 4)
    .to(V, { classify: 1, zoom: 1.36, cx: .66, cy: .44, duration: 1.4 }, 6)
    .to(V, { fixed: 1, ember: 0, scan: -.06, zoom: 1.16, cx: .62, cy: .5, par: 0, duration: 2 }, 8);
  tl.eventCallback('onUpdate', () => setStep(tl.progress()));
  setStep(0);
  ScrollTrigger.create({ trigger: '#journey', start: 'top top', end: 'bottom top',
    onLeave: () => { sceneActive = false; }, onEnterBack: () => { sceneActive = true; } });
}

/* pointer parallax */
const ptr = { x: 0, y: 0, sx: 0, sy: 0 };
if (!reduce && !coarse) addEventListener('pointermove', e => { ptr.x = e.clientX / innerWidth - .5; ptr.y = .5 - e.clientY / innerHeight; });

let vw = innerWidth, vh = innerHeight;
function resize() {
  vw = innerWidth; vh = innerHeight;
  renderer.setSize(vw, vh, false);
  composer.setSize(vw, vh);
  U.uRes.value.set(vw, vh);
  emberMat.uniforms.uPixel.value = renderer.getPixelRatio();
}
addEventListener('resize', resize);

const clamp01 = v => Math.max(0, Math.min(1, v));
function visible() { const sa = vw / vh; return sa > IMG_ASPECT ? [1, IMG_ASPECT / sa] : [sa / IMG_ASPECT, 1]; }

function frame(t) {
  ptr.sx += (ptr.x - ptr.sx) * .05; ptr.sy += (ptr.y - ptr.sy) * .05;
  const wide = isWide();
  // framing: keep the house right of centre on desktop, centred and high on phones
  const vis = visible();
  const breathe = reduce ? 0 : Math.sin(t * .18) * .012;
  const z = V.zoom * (wide ? 1 : 1.05) + breathe;
  let cx = wide ? V.cx - .16 * vis[0] / z : V.cx + .04;
  let cy = wide ? V.cy : V.cy - .14 * vis[1] / z;
  const hx = vis[0] / (2 * z) + .012, hy = vis[1] / (2 * z) + .012;
  cx = Math.min(Math.max(cx, hx), 1 - hx); cy = Math.min(Math.max(cy, hy), 1 - hy);
  U.uZoom.value = z; U.uCenter.value.set(cx, cy);
  U.uMouse.value.set(ptr.sx, ptr.sy);
  U.uPar.value = V.par;
  U.uScan.value = V.scan; U.uXr.value = V.xr; U.uTime.value = t;
  U.uDanger.value = V.ember * (1 - V.fixed); U.uFixed.value = V.fixed; U.uBoot.value = V.boot;
  emberMat.uniforms.uOpacity.value = V.ember;
  embers.visible = V.ember > .01;

  HS.forEach((h, i) => {
    const sx = (h.uv[0] - cx) * z / vis[0] + .5, sy = (h.uv[1] - cy) * z / vis[1] + .5;
    const seen = clamp01((V.seen - sy) * 25);
    const fix = clamp01(V.fixed * HS.length - i);
    const show = Math.max(clamp01(V.classify * 2 - .4), clamp01(V.xr * 1.5 - .5) * .999) * seen;
    const st = fix > .5 ? 'ok' : (V.classify < .3 ? 'scan' : h.sev);
    if (st !== h.state) {
      h.state = st;
      const color = st === 'ok' ? 'var(--ok)' : st === 'mid' ? 'var(--warn)' : st === 'scan' ? '#8fd3ff' : '#ff5a52';
      const tag = st === 'ok' ? 'Đã khắc phục' : st === 'mid' ? 'Cần chú ý' : st === 'scan' ? 'Đang phân tích' : 'Nguy cơ cao';
      h.el.style.setProperty('--c', color);
      h.el.innerHTML = `<span class="ic-wrap" style="color:${color}">${ICONS[st === 'ok' ? 'check-circle' : h.icon] || ''}</span>${h.name}<small>${tag}</small>`;
    }
    const x = sx * vw, y = (1 - sy) * vh;
    const flip = wide ? x > vw - 300 : x > vw * .5;
    const onScreen = x > 12 && x < vw - 12 && y > 60 && y < vh - 12;
    h.el.style.transform = `translate(${(x).toFixed(1)}px, ${(y).toFixed(1)}px)`;
    h.el.classList.toggle('flip', flip);
    h.el.style.opacity = (onScreen ? show : 0).toFixed(3);
  });

  composer.render();
}

resize();
Promise.all([tex(ASSETS.hero, true), tex(ASSETS.depth, false)]).then(([c, d]) => {
  U.tColor.value = c; U.tDepth.value = d;
  canvas.classList.add('ready');
  if (reduce) { frame(0); addEventListener('resize', () => frame(0)); return; }
  gsap.fromTo(V, { boot: 0, zoom: 1.45 }, { boot: 1, zoom: 1.14, duration: 2.8, ease: 'expo.out' });
  const clock = new THREE.Clock();
  let first = true;
  (function loop() {
    requestAnimationFrame(loop);
    if ((!sceneActive || document.hidden) && !first) return;
    first = false;
    frame(clock.getElapsedTime());
  })();
});
