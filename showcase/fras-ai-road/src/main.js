import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { FontLoader } from 'three/examples/jsm/loaders/FontLoader.js';
import { TextGeometry } from 'three/examples/jsm/geometries/TextGeometry.js';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import fontJson from 'three/examples/fonts/helvetiker_bold.typeface.json';
import { gsap } from 'gsap';
import Lenis from 'lenis';

const ICONS = window.__ICONS || {};
const ASSETS = window.__ASSETS || {};
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const coarse = matchMedia('(pointer: coarse)').matches;
const $ = s => document.querySelector(s);

/* =====================================================================
   Content: four chapters along one road
   ===================================================================== */
const CH = [
  { name: 'FRAS·AI', a: '#f4f5f9', b: '#9db6ff', fog: '#e9edf9', toy: ['#8fa8ff', '#c9d6ff', '#ffffff', '#ff8a8a'] },
  { name: 'Nguy cơ', a: '#f8f1ee', b: '#f5a08c', fog: '#f5e6e0', toy: ['#ff8f7a', '#ffc2b3', '#ffffff', '#ffb36b'] },
  { name: 'AI phân tích', a: '#eef3fb', b: '#86a9ff', fog: '#e4ebfa', toy: ['#7d9dff', '#b9c9ff', '#ffffff', '#9be3ff'] },
  { name: 'An toàn', a: '#f0f7f1', b: '#83dba0', fog: '#e3f3e7', toy: ['#6fd99a', '#bff0cf', '#ffffff', '#ffe08a'] }
];
const SURVEY = 'https://fras-ai.com/survey.html';

const STATIONS = [
  { ch: 0, img: 'hero', tag: 'Sáng kiến cấp tỉnh 2026', title: 'Hệ thống AI đánh giá nguy cơ cháy nổ', sub: 'Công an tỉnh Bắc Ninh',
    body: 'AI đối chiếu hơn 14.000 vụ cháy thực tế, chỉ ra điểm nguy hiểm trong nhà bạn sau 5 phút. Hoàn toàn miễn phí và ẩn danh.',
    list: ['Trả lời 20-25 câu hỏi trắc nghiệm đơn giản', 'Nhận báo cáo màu sắc kèm giải pháp', 'Không ai biết kết quả của bạn, kể cả quản trị viên'] },
  { ch: 0, poster: { big: 'Hỏi Chi', label: 'Trợ lý AI 24/7 về Luật PCCC', icon: 'chat-circle-text' }, tag: 'Trợ lý ảo', title: 'Hỏi đáp pháp luật và an toàn PCCC', sub: 'Phản hồi tức thì',
    body: 'Trợ lý Chi giải đáp mọi thắc mắc về Luật PCCC số 55/2024/QH15, tiêu chuẩn trang thiết bị và kỹ năng thoát nạn an toàn.',
    list: ['Thoát nạn khi cháy chung cư mini', 'Kiểm tra hạn bình chữa cháy', 'An toàn khi sạc pin xe điện'] },

  { ch: 1, img: 'c_wires', tag: 'Nguy cơ cao', title: 'Dây điện chằng chịt, lão hóa', sub: 'Vỏ bọc nứt, bị chuột gặm',
    body: 'Dây điện cũ dùng nhiều năm, đấu nối chắp vá và bị chuột gặm là nguyên nhân hàng đầu gây chập cháy trong nhà ống và nhà trọ.',
    list: ['Kiểm tra vỏ dây ở trần, góc tường', 'Thay dây đã cứng, nứt hoặc đổi màu', 'Gọi thợ điện có chuyên môn'] },
  { ch: 1, img: 'c_shop', tag: 'Nguy cơ cao', title: 'Ổ cắm quá tải', sub: 'Cắm chồng, dùng liên tục',
    body: 'Một ổ cắm gánh nhiều thiết bị công suất lớn sẽ nóng dần, chảy nhựa và phát lửa. Nhiều vụ cháy bắt đầu từ góc bếp hoặc kho hàng.',
    list: ['Không cắm nối tiếp nhiều ổ', 'Rút phích khi không sử dụng', 'Thay ổ cắm đã dùng trên 10 năm'] },
  { ch: 1, img: 'c_shutter', tag: 'Nguy cơ cao', title: 'Lối thoát duy nhất bị khóa', sub: 'Cửa cuốn, cầu thang chất đồ',
    body: 'Nhà ống thường chỉ có một lối ra là cửa cuốn. Khi cửa khóa kín và cầu thang chất đầy hàng hóa, người bên trong không thể thoát.',
    list: ['Luôn để chìa khóa cửa ở vị trí dễ lấy', 'Dọn trống cầu thang và hành lang', 'Mở lối thoát thứ hai ra ban công hoặc mái'] },
  { ch: 1, poster: { big: 'Hết hạn', label: 'Bình chữa cháy không còn tác dụng', icon: 'fire-extinguisher' }, tag: 'Cần chú ý', title: 'Bình chữa cháy hết hạn', sub: 'Hoặc đặt ở góc khuất',
    body: 'Bình chữa cháy quá hạn hoặc bị giấu trong góc khuất sẽ vô dụng đúng lúc cần nhất.',
    list: ['Xem đồng hồ áp suất mỗi tháng', 'Đặt bình ở nơi dễ thấy, gần lối ra', 'Cả nhà đều biết cách sử dụng'] },
  { ch: 1, poster: { big: '95%', label: 'cơ sở tự cho là an toàn', icon: 'eye-slash' }, tag: 'Sự thật', title: '95% cơ sở cho rằng mình an toàn', sub: 'cho đến khi kiểm tra',
    body: 'Phần lớn vụ cháy có dấu hiệu cảnh báo trước 3-6 tháng nhưng không được chú ý. Nguy hiểm nhất là điều bạn đã quen thấy đến mức bỏ qua.' },

  { ch: 2, poster: { big: 'Khai báo', label: '20-25 câu hỏi, 2-5 phút', icon: 'list-checks' }, tag: 'Bước 1', title: 'Khai báo tình trạng cơ sở', sub: 'Không cần kiến thức chuyên môn',
    body: 'Trả lời trung thực các câu hỏi trắc nghiệm đơn giản về nhà ở, cơ sở kinh doanh hoặc xưởng sản xuất của bạn.' },
  { ch: 2, poster: { big: '14.000+', label: 'vụ cháy thực tế AI đã học', icon: 'brain' }, tag: 'Bước 2', title: 'AI phân tích trong 10 giây', sub: 'Hơn 60 yếu tố nguy cơ',
    body: 'Hệ thống đối chiếu câu trả lời với cơ sở dữ liệu hơn 14.000 vụ cháy thực tế và kết quả điều tra nguyên nhân.' },
  { ch: 2, poster: { big: 'Báo cáo', label: 'Màu sắc trực quan, giải pháp cụ thể', icon: 'chart-line-up' }, tag: 'Bước 3', title: 'Nhận báo cáo ngay lập tức', sub: 'Đỏ, vàng, xanh',
    body: 'Thấy ngay điểm nào nguy hiểm nhất, kèm giải pháp khắc phục theo thứ tự ưu tiên và chi phí. Khảo sát định kỳ để so sánh giữa các kỳ.' },
  { ch: 2, poster: { big: '14.689', label: 'vụ cháy toàn quốc, 2021-2025', icon: 'flame' }, tag: 'Thống kê', title: '14.689 vụ cháy trên toàn quốc', sub: 'Giai đoạn 2021-2025',
    body: '531 người tử vong, 512 người bị thương và hơn 3.330,7 tỷ đồng thiệt hại vật chất.' },
  { ch: 2, poster: { big: '3.330,7 tỷ', label: 'đồng thiệt hại tài sản', icon: 'house-line' }, tag: 'Thống kê', title: 'Hơn 3.330,7 tỷ đồng thiệt hại', sub: 'Giai đoạn 2021-2025',
    body: 'Khoảng cách giữa nguy cơ và thảm họa thường chỉ là một hành động nhỏ chưa được thực hiện.' },

  { ch: 3, poster: { big: 'Miễn phí', label: 'Không thu phí, không quảng cáo', icon: 'hand-heart' }, tag: 'Cam kết', title: '100% miễn phí', sub: 'Từ Công an tỉnh Bắc Ninh',
    body: 'Không thu bất kỳ khoản phí nào, không quảng cáo sản phẩm. Kết quả khảo sát là ẩn danh.' },
  { ch: 3, poster: { big: 'Bảo mật', label: 'Xử lý nội bộ bằng Local AI', icon: 'lock-key' }, tag: 'Cam kết', title: 'Bảo mật tuyệt đối', sub: 'Không chia sẻ ra bên ngoài',
    body: 'Dữ liệu được xử lý nội bộ bằng Local AI, không chia sẻ ra bên ngoài.' },
  { ch: 3, img: 'c_balcony', tag: 'Người dân nói', title: '“Lắp ngay, đi làm đỡ lo”', sub: 'Chị Ngọc, TP. Bắc Ninh',
    body: 'Hệ thống nhắc lắp đầu báo khói và đèn thoát hiểm cho nhà có ông bà. Lắp ngay, đi làm đỡ lo hơn hẳn.' },
  { ch: 3, poster: { big: '“12 năm”', label: 'Chị Lan, chủ nhà trọ, Từ Sơn', icon: 'quotes' }, tag: 'Người dân nói', title: '“Ổ cắm bếp 12 năm chưa thay”', sub: 'Chị Lan, chủ nhà trọ 5 tầng',
    body: 'Làm xong mới biết ổ cắm ở bếp dùng 12 năm rồi chưa thay. Hệ thống cảnh báo đỏ, tôi gọi thợ thay ngay hôm đó.' },
  { ch: 3, poster: { big: 'Bắt đầu', label: 'Khảo sát an toàn, 5 phút', icon: 'shield-check' }, tag: 'Hành động hôm nay', title: 'Thực hiện khảo sát ngay', sub: 'An tâm lâu dài',
    body: 'Cháy nổ không báo trước. Nhưng nguy cơ luôn có dấu hiệu. Hãy để AI giúp bạn phát hiện trước khi quá muộn.' }
];
// chapter start positions on the road (0..1)
const CH_START = [0, .2, .52, .76];

/* screen-reader version of the journey */
$('#sr').innerHTML = CH.map((c, ci) => `<section><h2>${c.name}</h2>${STATIONS.filter(s => s.ch === ci).map(s => `<article><h3>${s.title}</h3><p>${s.body}</p></article>`).join('')}</section>`).join('');

/* =====================================================================
   Renderer, world
   ===================================================================== */
const canvas = $('#scene');
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  if (!renderer.getContext()) throw new Error('no gl');
} catch (e) {
  document.body.classList.add('no-webgl');
  $('#intro').classList.add('gone');
  $('#list').classList.add('open');
  throw e;
}
const LOW = coarse || innerWidth < 768;
renderer.setPixelRatio(Math.min(devicePixelRatio, LOW ? 1.6 : 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.setClearColor(0x000000, 0);

const scene = new THREE.Scene();
const fog = new THREE.Fog(new THREE.Color(CH[0].fog), 30, 110);
scene.fog = fog;
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(renderer), .04).texture;
scene.add(new THREE.HemisphereLight(0xffffff, 0xc9d3ee, 1.2));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(-6, 12, 8);
scene.add(sun);

const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, .1, 260);

/* the road */
const pts = [];
for (let i = 0; i <= 36; i++) pts.push(new THREE.Vector3(Math.sin(i * .5) * 9 + Math.sin(i * .17) * 7, 0, -i * 15));
const road = new THREE.CatmullRomCurve3(pts, false, 'catmullrom', .5);
const up = new THREE.Vector3(0, 1, 0);
const tmpA = new THREE.Vector3(), tmpB = new THREE.Vector3(), tmpC = new THREE.Vector3();
function frameAt(u) {
  const p = road.getPointAt(THREE.MathUtils.clamp(u, 0, 1));
  const t = road.getTangentAt(THREE.MathUtils.clamp(u, 0, 1));
  const side = new THREE.Vector3().crossVectors(t, up).normalize();
  return { p, t, side };
}

/* dotted path, like dashes painted on the ground */
{
  const N = 2600, pos = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) {
    const u = i / N, { p, side } = frameAt(u);
    const off = (Math.random() - .5) * 3.2 * (Math.random() < .75 ? .35 : 1);
    pos.set([p.x + side.x * off, .02, p.z + side.z * off], i * 3);
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const dotTex = new THREE.CanvasTexture((() => { const c = document.createElement('canvas'); c.width = c.height = 32; const x = c.getContext('2d'); x.fillStyle = '#fff'; x.beginPath(); x.ellipse(16, 16, 14, 6, 0, 0, 7); x.fill(); return c; })());
  scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color: 0x2a3146, size: .16, map: dotTex, transparent: true, opacity: .55, depthWrite: false })));
}

/* =====================================================================
   Canvas helpers: posters, photo cards, labels, chapter titles
   ===================================================================== */
const FONT = '"Be Vietnam Pro", system-ui, sans-serif';
function canvas2d(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return [c, c.getContext('2d')]; }
function rr(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
function loadImg(src) { return new Promise(res => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; }); }
function iconImg(name, color) {
  const svg = (ICONS[name] || '').replace('fill="currentColor"', `fill="${color}"`).replace('<svg ', '<svg width="256" height="256" ');
  return svg ? loadImg('data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)) : Promise.resolve(null);
}
function fitText(g, text, maxW, size, weight = 800) {
  let s = size;
  do { g.font = `${weight} ${s}px ${FONT}`; s -= 4; } while (g.measureText(text).width > maxW && s > 20);
  return s + 4;
}
const POSTER_THEME = [
  { a: '#1A3A6B', b: '#4f7dff', ink: '#ffffff', sub: 'rgba(255,255,255,.78)', icon: '#ffffff' },
  { a: '#ff8d76', b: '#C0202A', ink: '#ffffff', sub: 'rgba(255,255,255,.82)', icon: '#ffffff' },
  { a: '#f3f6ff', b: '#9bb5ff', ink: '#13254d', sub: 'rgba(19,37,77,.7)', icon: '#2e57d6' },
  { a: '#effbf2', b: '#7fdca0', ink: '#0d3a22', sub: 'rgba(13,58,34,.72)', icon: '#13804a' }
];
async function posterCanvas(st) {
  const th = POSTER_THEME[st.ch], W = 1024, H = 768, [c, g] = canvas2d(W, H);
  rr(g, 0, 0, W, H, 56); g.save(); g.clip();
  const gr = g.createLinearGradient(0, 0, W, H); gr.addColorStop(0, th.a); gr.addColorStop(1, th.b);
  g.fillStyle = gr; g.fillRect(0, 0, W, H);
  // soft orbs
  for (let i = 0; i < 3; i++) {
    const x = W * (.65 + .3 * Math.random()), y = H * (.15 + .4 * Math.random()), r = 160 + 140 * Math.random();
    const o = g.createRadialGradient(x, y, 0, x, y, r); o.addColorStop(0, 'rgba(255,255,255,.28)'); o.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = o; g.fillRect(0, 0, W, H);
  }
  const ic = await iconImg(st.poster.icon, th.icon);
  if (ic) g.drawImage(ic, 72, 64, 112, 112);
  g.fillStyle = th.ink; g.textBaseline = 'alphabetic';
  fitText(g, st.poster.big, W - 144, 210);
  g.fillText(st.poster.big, 66, H - 170);
  g.fillStyle = th.sub; fitText(g, st.poster.label, W - 144, 46, 600);
  g.fillText(st.poster.label, 72, H - 92);
  g.restore();
  return c;
}
async function photoCanvas(key) {
  const W = 1024, H = 768, [c, g] = canvas2d(W, H), img = await loadImg(ASSETS[key]);
  rr(g, 0, 0, W, H, 56); g.save(); g.clip();
  if (img) {
    const s = Math.max(W / img.width, H / img.height);
    g.drawImage(img, (W - img.width * s) / 2, (H - img.height * s) / 2, img.width * s, img.height * s);
  }
  g.restore();
  return c;
}
function labelCanvas(title, sub) {
  const W = 900, H = 200, [c, g] = canvas2d(W, H);
  g.fillStyle = '#1c2233';
  g.beginPath(); g.arc(22, 62, 12, 0, 7); g.fill();
  g.lineWidth = 3; g.strokeStyle = '#1c2233'; g.beginPath(); g.arc(22, 62, 20, 0, 7); g.stroke();
  fitText(g, title, W - 70, 50, 700); g.fillText(title, 58, 78);
  g.fillStyle = 'rgba(28,34,51,.6)'; g.font = `italic 600 34px ${FONT}`; g.fillText(sub, 58, 132);
  return c;
}
function chapterTitleCanvas(text, color) {
  const W = 2048, H = 380, [c, g] = canvas2d(W, H);
  const s = fitText(g, text.toUpperCase(), W - 80, 300);
  g.font = `800 ${s}px ${FONT}`; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.lineJoin = 'round';
  g.lineWidth = 14; g.strokeStyle = color; g.strokeText(text.toUpperCase(), W / 2, H / 2 + 10);
  g.fillStyle = 'rgba(255,255,255,.92)'; g.fillText(text.toUpperCase(), W / 2, H / 2 + 10);
  g.lineWidth = 3; g.strokeStyle = color; g.strokeText(text.toUpperCase(), W / 2 + 10, H / 2 + 20);
  return c;
}
function texFrom(c) { const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; }

/* waving card material (flag-like, like the reference) */
function cardMaterial(map) {
  return new THREE.ShaderMaterial({
    uniforms: { map: { value: map }, uTime: { value: 0 }, uHover: { value: 0 }, uOpacity: { value: 0 }, uSeed: { value: Math.random() * 10 } },
    transparent: true, side: THREE.DoubleSide, depthWrite: false,
    vertexShader: `
      uniform float uTime; uniform float uHover; uniform float uSeed; varying vec2 vUv; varying float vShade;
      void main(){
        vUv = uv; vec3 p = position;
        float w = sin(p.x * 1.1 + uTime * 1.7 + uSeed) * .16 * uv.x + sin(p.y * 1.8 + uTime * 1.2 + uSeed) * .05;
        p.z += w + uHover * .35 * sin(uv.x * 3.14159);
        p.y += sin(uTime * .9 + uSeed) * .08;
        vShade = w;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
      }`,
    fragmentShader: `
      uniform sampler2D map; uniform float uOpacity; uniform float uHover; varying vec2 vUv; varying float vShade;
      void main(){
        vec4 c = texture2D(map, vUv);
        c.rgb *= 1.0 + vShade * 1.1 + uHover * .05;
        gl_FragColor = vec4(c.rgb, c.a * uOpacity);
        #include <colorspace_fragment>
      }`
  });
}

/* =====================================================================
   Toys: soft pastel 3D objects about fire safety
   ===================================================================== */
const soft = (color, extra = {}) => new THREE.MeshPhysicalMaterial({ color, roughness: .45, clearcoat: .6, clearcoatRoughness: .3, ...extra });
function extinguisher() {
  const g = new THREE.Group(), red = soft(0xff5f5f), dark = soft(0x2a2f3d), white = soft(0xffffff);
  const body = new THREE.Mesh(new THREE.CylinderGeometry(.34, .34, 1.2, 32), red); g.add(body);
  const dome = new THREE.Mesh(new THREE.SphereGeometry(.34, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), red); dome.position.y = .6; g.add(dome);
  const base = new THREE.Mesh(new THREE.SphereGeometry(.34, 32, 16, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), red); base.position.y = -.6; base.scale.y = .25; g.add(base);
  const band = new THREE.Mesh(new THREE.CylinderGeometry(.347, .347, .32, 32), white); band.position.y = .05; g.add(band);
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(.09, .11, .22, 16), dark); neck.position.y = .98; g.add(neck);
  const handle = new THREE.Mesh(new RoundedBoxGeometry(.6, .08, .12, 2, .03), dark); handle.position.set(.12, 1.1, 0); handle.rotation.z = -.15; g.add(handle);
  const hose = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([new THREE.Vector3(-.05, 1.0, 0), new THREE.Vector3(-.4, .9, .05), new THREE.Vector3(-.48, .3, .1), new THREE.Vector3(-.38, -.1, .12)]), 20, .045, 8), dark); g.add(hose);
  return g;
}
function plug() {
  const g = new THREE.Group(), w = soft(0xffffff), m = soft(0xd9dee8, { metalness: .8, roughness: .25 });
  g.add(new THREE.Mesh(new RoundedBoxGeometry(.8, .55, .45, 4, .14), w));
  for (const x of [-.16, .16]) { const p = new THREE.Mesh(new THREE.CylinderGeometry(.045, .045, .38, 12), m); p.rotation.x = Math.PI / 2; p.position.set(x, 0, .4); g.add(p); }
  const cable = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([new THREE.Vector3(0, 0, -.22), new THREE.Vector3(0, -.1, -.7), new THREE.Vector3(.4, -.5, -1.1), new THREE.Vector3(.2, -.9, -1.6)]), 24, .06, 8), soft(0x2a2f3d)); g.add(cable);
  return g;
}
function flame() {
  const g = new THREE.Group(), pts = [];
  for (let i = 0; i <= 20; i++) { const t = i / 20; pts.push(new THREE.Vector2(Math.sin(Math.PI * t) * (.55 - .35 * t) * (1 - t * .15), t * 1.6 - .5)); }
  const outer = new THREE.Mesh(new THREE.LatheGeometry(pts, 32), soft(0xff8a4c, { emissive: 0xff5a1f, emissiveIntensity: .45 }));
  const inner = new THREE.Mesh(new THREE.LatheGeometry(pts, 32), soft(0xffd36b, { emissive: 0xffb23a, emissiveIntensity: .6 }));
  inner.scale.setScalar(.55); inner.position.set(0, -.12, .18);
  g.add(outer, inner); g.userData.flicker = [outer, inner];
  return g;
}
function house() {
  const g = new THREE.Group();
  const body = new THREE.Mesh(new RoundedBoxGeometry(1, .85, 1, 3, .08), soft(0xffffff)); g.add(body);
  const roof = new THREE.Mesh(new THREE.ConeGeometry(.88, .62, 4), soft(0xff8f7a)); roof.position.y = .72; roof.rotation.y = Math.PI / 4; g.add(roof);
  const door = new THREE.Mesh(new RoundedBoxGeometry(.26, .42, .06, 2, .03), soft(0x4f7dff)); door.position.set(0, -.2, .5); g.add(door);
  const win = new THREE.Mesh(new RoundedBoxGeometry(.22, .2, .06, 2, .03), soft(0xffd36b, { emissive: 0xffc04a, emissiveIntensity: .5 })); win.position.set(.27, .12, .5); g.add(win);
  return g;
}
function smokeDetector() {
  const g = new THREE.Group();
  const b = new THREE.Mesh(new THREE.CylinderGeometry(.6, .66, .2, 40), soft(0xffffff)); g.add(b);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(.38, .03, 10, 40), soft(0xdfe4ee)); ring.rotation.x = Math.PI / 2; ring.position.y = .11; g.add(ring);
  const led = new THREE.Mesh(new THREE.SphereGeometry(.05, 12, 12), new THREE.MeshBasicMaterial({ color: 0xff3b3b })); led.position.set(.25, .12, .2); g.add(led);
  g.rotation.x = Math.PI / 2.4;
  return g;
}
function shield() {
  const s = new THREE.Shape();
  s.moveTo(0, .9); s.bezierCurveTo(.35, .82, .6, .72, .7, .62); s.bezierCurveTo(.72, .05, .45, -.5, 0, -.8);
  s.bezierCurveTo(-.45, -.5, -.72, .05, -.7, .62); s.bezierCurveTo(-.6, .72, -.35, .82, 0, .9);
  const geo = new THREE.ExtrudeGeometry(s, { depth: .22, bevelEnabled: true, bevelThickness: .08, bevelSize: .08, bevelSegments: 6, curveSegments: 24 });
  geo.center();
  const g = new THREE.Group(); g.add(new THREE.Mesh(geo, soft(0x4fd18b)));
  const tick = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([new THREE.Vector3(-.3, 0, .25), new THREE.Vector3(-.08, -.22, .25), new THREE.Vector3(.32, .25, .25)], false, 'catmullrom', 0), 20, .07, 10), soft(0xffffff));
  g.add(tick);
  return g;
}
function bolt() {
  const s = new THREE.Shape();
  s.moveTo(.1, .9); s.lineTo(-.45, -.05); s.lineTo(-.02, -.05); s.lineTo(-.15, -.9); s.lineTo(.45, .12); s.lineTo(.02, .12); s.closePath();
  const geo = new THREE.ExtrudeGeometry(s, { depth: .2, bevelEnabled: true, bevelThickness: .06, bevelSize: .05, bevelSegments: 4 }); geo.center();
  return new THREE.Group().add(new THREE.Mesh(geo, soft(0xffc23d, { emissive: 0xffa000, emissiveIntensity: .25 })));
}

const toys = [];
function placeToy(obj, u, side, height, scale) {
  const { p, side: sv } = frameAt(u);
  obj.position.set(p.x + sv.x * side, height, p.z + sv.z * side);
  obj.scale.setScalar(scale);
  obj.userData.base = obj.position.y; obj.userData.seed = Math.random() * 10;
  obj.userData.spin = (Math.random() - .5) * .6;
  obj.rotation.y = Math.random() * 6;
  scene.add(obj); toys.push(obj);
}
// hero toys per chapter
placeToy(house(), .045, -5.5, 2.4, 1.5);
placeToy(smokeDetector(), .1, 6.5, 4.6, 1.2);
placeToy(plug(), .24, -4.2, 2.8, 1.4);
placeToy(flame(), .29, 5.8, 3.4, 1.5);
placeToy(extinguisher(), .37, -5.2, 2.6, 1.5);
placeToy(bolt(), .45, 5, 4, 1.3);
placeToy(flame(), .5, -6, 2.4, 1.1);
placeToy(smokeDetector(), .6, 5.4, 4.2, 1.1);
placeToy(house(), .68, -5.8, 2.2, 1.3);
placeToy(bolt(), .72, 6.2, 3.5, 1.1);
placeToy(shield(), .8, 5.6, 3.4, 1.7);
placeToy(extinguisher(), .87, -5.6, 2.8, 1.4);
placeToy(house(), .93, 6, 2.4, 1.6);
placeToy(shield(), .965, -6.4, 4.4, 1.3);

/* confetti: spheres, pills and cubes scattered along the road */
const confetti = [];
{
  const geos = [new THREE.SphereGeometry(.24, 24, 16), new THREE.CapsuleGeometry(.14, .38, 8, 16), new RoundedBoxGeometry(.38, .38, .38, 3, .08)];
  for (let i = 0; i < 130; i++) {
    const u = Math.random(), chi = CH_START.findLastIndex(s => u >= s);
    const col = CH[chi].toy[Math.floor(Math.random() * 4)];
    const m = new THREE.Mesh(geos[i % 3], soft(col, { roughness: .35 }));
    const { p, side } = frameAt(u), off = (Math.random() < .5 ? -1 : 1) * (2.5 + Math.random() * 11);
    m.position.set(p.x + side.x * off, .4 + Math.random() * 6, p.z + side.z * off);
    m.rotation.set(Math.random() * 6, Math.random() * 6, 0);
    m.scale.setScalar(.6 + Math.random() * 1.1);
    m.userData = { base: m.position.y, seed: Math.random() * 10, spin: (Math.random() - .5) * 1.2 };
    scene.add(m); confetti.push(m);
  }
}

/* big extruded title at the start, 114 at the end */
const font = new FontLoader().parse(fontJson);
function text3d(str, size, color) {
  const geo = new TextGeometry(str, { font, size, height: size * .28, curveSegments: 10, bevelEnabled: true, bevelThickness: size * .05, bevelSize: size * .035, bevelSegments: 5 });
  geo.center();
  return new THREE.Mesh(geo, soft(color, { roughness: .3 }));
}
const title = new THREE.Group();
{
  const a = text3d('FRAS', 2.3, 0x7f9bff), b = text3d('AI', 2.3, 0xff5a5f);
  a.position.x = -1.6; b.position.x = 4.55;
  const dot = new THREE.Mesh(new THREE.SphereGeometry(.32, 24, 16), soft(0xff5a5f)); dot.position.set(2.75, -.2, 0);
  title.add(a, b, dot);
  const { p } = frameAt(.06); title.position.set(p.x, 4.4, p.z); title.scale.setScalar(.85); title.lookAt(frameAt(0).p.x, 3.6, frameAt(0).p.z + 10);
  scene.add(title);
}
const finale = text3d('114', 2.4, 0xff5a5f);
{ const { p } = frameAt(1); finale.position.set(p.x, 4, p.z - 2); const q = frameAt(.95).p; finale.lookAt(q.x, 3.4, q.z); scene.add(finale); }

/* =====================================================================
   Build cards (async: needs fonts and images)
   ===================================================================== */
const cards = [];        // {mesh, label, line, st, u}
const chapterTitles = [];
const enterBtn = $('#enter'), prog = $('#prog'), enterLabel = $('#enter-label');
let loaded = 0;
const totalLoad = STATIONS.length + CH.length + 1;
const bump = () => { loaded++; prog.style.strokeDashoffset = String(528 * (1 - loaded / totalLoad)); };

async function build() {
  await Promise.race([document.fonts.load(`800 120px ${FONT}`).then(() => document.fonts.load(`600 40px ${FONT}`)), new Promise(r => setTimeout(r, 3500))]);
  bump();
  // chapter titles stretched across the road
  CH.forEach((c, i) => {
    if (i === 0) { bump(); return; }
    const tex = texFrom(chapterTitleCanvas(c.name, ['#7f9bff', '#ff6f5e', '#5f86ff', '#3fbf74'][i]));
    const m = new THREE.Mesh(new THREE.PlaneGeometry(16, 16 * 380 / 2048), new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, side: THREE.DoubleSide }));
    const u = CH_START[i] + .012, { p } = frameAt(u);
    m.position.set(p.x, 3.4, p.z);
    const q = frameAt(u - .03).p; m.lookAt(q.x, 3.4, q.z);
    scene.add(m); chapterTitles.push(m); bump();
  });
  // stations spread inside their chapter
  const byCh = CH.map((_, ci) => STATIONS.filter(s => s.ch === ci));
  for (let ci = 0; ci < CH.length; ci++) {
    const list = byCh[ci], start = CH_START[ci] + (ci === 0 ? .06 : .045), end = (CH_START[ci + 1] ?? .97) - .02;
    for (let k = 0; k < list.length; k++) {
      const st = list[k];
      const u = start + (end - start) * (k + .5) / list.length;
      const c = st.poster ? await posterCanvas(st) : await photoCanvas(st.img);
      st.thumb = c.toDataURL('image/jpeg', .82);
      const sideSign = (k + ci) % 2 === 0 ? 1 : -1;
      const { p, side } = frameAt(u);
      const off = (LOW ? 3.1 : 5.8) * sideSign;
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(8, 6, 32, 20), cardMaterial(texFrom(c)));
      mesh.position.set(p.x + side.x * off, 3.7, p.z + side.z * off);
      const q = frameAt(u - .045).p; mesh.lookAt(q.x + side.x * off * .35, 3.0, q.z + side.z * off * .35);
      if (LOW) mesh.scale.setScalar(.62);
      mesh.userData.st = st;
      scene.add(mesh);
      // pin label on the road side of the card, with a thread down to the ground
      const lt = texFrom(labelCanvas(st.title, st.sub));
      const label = new THREE.Mesh(new THREE.PlaneGeometry(5.2, 5.2 * 200 / 900), new THREE.MeshBasicMaterial({ map: lt, transparent: true, depthWrite: false, side: THREE.DoubleSide }));
      label.quaternion.copy(mesh.quaternion);
      const right = new THREE.Vector3(1, 0, 0).applyQuaternion(mesh.quaternion);
      const toRoad = -Math.sign(right.dot(side) * sideSign) || 1;
      label.position.copy(mesh.position).addScaledVector(right, toRoad * (4 * mesh.scale.x + 2.75)).add(new THREE.Vector3(0, 1.6 * mesh.scale.x, 0));
      if (LOW) label.position.y -= 3.2;
      scene.add(label);
      const anchor = label.position.clone().addScaledVector(right, -2.6 + .1).add(new THREE.Vector3(0, .12, 0));
      const lineGeo = new THREE.BufferGeometry().setFromPoints([anchor.clone().add(new THREE.Vector3(0, .05, 0)), new THREE.Vector3(anchor.x, 0, anchor.z)]);
      const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: 0x1c2233, transparent: true, opacity: .35 }));
      scene.add(line);
      cards.push({ mesh, label, line, st, u });
      bump();
    }
  }
  buildList();
}

/* =====================================================================
   Navigation state
   ===================================================================== */
const track = $('#track');
track.style.height = `${Math.round(STATIONS.length * 55 + 160)}vh`;
let lenis = null;
let mode = 'road';
const S = { p: 0, intro: 1, over: 0 };
const ptr = { x: 0, y: 0, sx: 0, sy: 0 };
if (!coarse) addEventListener('pointermove', e => { ptr.x = e.clientX / innerWidth - .5; ptr.y = e.clientY / innerHeight - .5; });

function progress() {
  const max = document.documentElement.scrollHeight - innerHeight;
  return max > 0 ? scrollY / max : 0;
}
function scrollToU(u) {
  const max = document.documentElement.scrollHeight - innerHeight;
  const y = THREE.MathUtils.clamp((u - .02) / .95, 0, 1) * max;
  if (lenis) lenis.scrollTo(y, { duration: 2.2, easing: t => 1 - Math.pow(1 - t, 4) }); else scrollTo(0, y);
}

// chapter colours
const bgEl = $('#bg'), root = document.documentElement;
const col = { a: new THREE.Color(CH[0].a), b: new THREE.Color(CH[0].b), f: new THREE.Color(CH[0].fog) };
let chIdx = 0;
const dots = [...document.querySelectorAll('.dots span')];
function setChapter(i) {
  if (i === chIdx) return; chIdx = i;
  const rgb = h => { const c = new THREE.Color(h); return { r: c.r, g: c.g, b: c.b }; };
  gsap.to(col.a, { ...rgb(CH[i].a), duration: 1.2, ease: 'power2.out' });
  gsap.to(col.b, { ...rgb(CH[i].b), duration: 1.2, ease: 'power2.out' });
  gsap.to(col.f, { ...rgb(CH[i].fog), duration: 1.2, ease: 'power2.out' });
  dots.forEach((d, k) => d.classList.toggle('on', k === i));
  $('#chapter-name').textContent = CH[i].name;
}

/* modes: road, overview, list */
const modeBtns = [...document.querySelectorAll('[data-mode]')];
function setMode(m) {
  if (m === mode && m !== 'road') m = 'road';
  mode = m;
  modeBtns.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === m)));
  $('#list').classList.toggle('open', m === 'list');
  gsap.to(S, { over: m === 'overview' ? 1 : 0, duration: reduce ? .01 : 1.8, ease: 'power3.inOut' });
  if (lenis) (m === 'road' ? lenis.start() : lenis.stop());
}
modeBtns.forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));
$('#home').addEventListener('click', e => { e.preventDefault(); setMode('road'); scrollToU(0); });
addEventListener('keydown', e => { if (e.key === 'Escape') { closeModal(); if (mode !== 'road') setMode('road'); } });

function buildList() {
  $('#list-inner').innerHTML = CH.map((c, ci) => `
    <div class="list-chapter"><h3>${c.name}</h3><div class="list-items">
      ${cards.filter(k => k.st.ch === ci).map(k => `<button class="list-item" data-i="${cards.indexOf(k)}"><span class="th" style="background-image:url(${k.st.thumb})"></span><span><b>${k.st.title}</b><small>${k.st.sub}</small></span></button>`).join('')}
    </div></div>`).join('');
  document.querySelectorAll('.list-item').forEach(b => b.addEventListener('click', () => {
    const k = cards[+b.dataset.i]; setMode('road'); scrollToU(k.u - .02);
    setTimeout(() => openModal(k.st), reduce ? 0 : 1600);
  }));
}

/* modal */
const modal = $('#modal');
function openModal(st) {
  $('#m-img').style.backgroundImage = `url(${st.thumb})`;
  $('#m-tag').textContent = st.tag; $('#m-title').textContent = st.title; $('#m-body').textContent = st.body;
  $('#m-list').innerHTML = (st.list || []).map(t => `<li>${ICONS['check-circle'] || ''}<span>${t}</span></li>`).join('');
  modal.classList.add('open'); lenis?.stop();
  $('#m-close').focus();
}
function closeModal() { if (!modal.classList.contains('open')) return; modal.classList.remove('open'); if (mode === 'road') lenis?.start(); }
$('#m-close').addEventListener('click', closeModal);
modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });

/* picking */
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2(-9, -9);
let hovered = null;
const tip = $('#tip');
canvas.style.pointerEvents = 'auto';
addEventListener('pointermove', e => {
  mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  tip.style.left = e.clientX + 'px'; tip.style.top = e.clientY + 'px';
});
canvas.addEventListener('click', () => {
  if (!hovered) return;
  if (mode === 'overview') { setMode('road'); scrollToU(hovered.u - .02); return; }
  openModal(hovered.st);
});

/* =====================================================================
   Loop
   ===================================================================== */
const hint = $('#hint'), finalCta = $('#final-cta');
const camPos = new THREE.Vector3(), camLook = new THREE.Vector3();
const overPos = new THREE.Vector3(), overLook = new THREE.Vector3();
{
  const box = new THREE.Box3().setFromPoints(road.getSpacedPoints(60));
  const c = box.getCenter(new THREE.Vector3());
  overPos.set(c.x + 40, 150, c.z + 150); overLook.copy(c);
}
function resize() {
  renderer.setSize(innerWidth, innerHeight, false);
  camera.aspect = innerWidth / innerHeight;
  camera.fov = camera.aspect < .8 ? 66 : 50;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize); resize();

const clock = new THREE.Clock();
function frame() {
  const t = reduce ? 0 : clock.getElapsedTime();
  ptr.sx += (ptr.x - ptr.sx) * .05; ptr.sy += (ptr.y - ptr.sy) * .05;
  S.p += (progress() - S.p) * (lenis || reduce ? 1 : .12);
  const u = .012 + S.p * .94;

  // road camera with a little sway; intro drops in from above
  const { p, side } = frameAt(u);
  const ahead = road.getPointAt(Math.min(u + .016, 1));
  const sway = side.clone().multiplyScalar(ptr.sx * 1.4 + (reduce ? 0 : Math.sin(t * .25) * .3));
  camPos.set(p.x, (LOW ? 3.6 : 3.3) - ptr.sy * .8 + S.intro * 26, p.z + S.intro * 18).add(sway);
  camLook.set(ahead.x, 3.1 + S.intro * 4, ahead.z).addScaledVector(side, ptr.sx * .6);
  camera.position.lerpVectors(camPos, overPos, S.over);
  tmpA.lerpVectors(camLook, overLook, S.over);
  camera.lookAt(tmpA);

  // chapter by position
  setChapter(CH_START.findLastIndex(s => u >= s - .005));
  bgEl.style.background = `radial-gradient(80% 90% at 100% 100%, #${col.b.getHexString()} 0%, transparent 72%), radial-gradient(70% 70% at 0% 0%, #ffffff 0%, transparent 60%), #${col.a.getHexString()}`;
  fog.color.copy(col.f);
  fog.far = THREE.MathUtils.lerp(110, 420, S.over); fog.near = THREE.MathUtils.lerp(30, 200, S.over);

  // cards: fade in as you approach, wave, hover lift
  ray.setFromCamera(mouse, camera);
  const hits = modal.classList.contains('open') || mode === 'list' ? [] : ray.intersectObjects(cards.map(k => k.mesh), false);
  const h = hits.length ? cards.find(k => k.mesh === hits[0].object) : null;
  if (h !== hovered) {
    hovered = h; canvas.style.cursor = h ? 'pointer' : '';
    tip.textContent = h ? (mode === 'overview' ? 'Bay tới đây' : 'Xem chi tiết') : ''; tip.style.opacity = h ? '1' : '0';
  }
  for (const k of cards) {
    const d = camera.position.distanceTo(k.mesh.position);
    const vis = S.over > .5 ? 1 : (1 - THREE.MathUtils.smoothstep(d, 26, 48)) * THREE.MathUtils.smoothstep(d, 2.5, 6);
    const U = k.mesh.material.uniforms;
    U.uTime.value = t; U.uOpacity.value = vis;
    U.uHover.value += ((k === hovered ? 1 : 0) - U.uHover.value) * .12;
    k.label.material.opacity = vis; k.line.material.opacity = vis * .35;
    k.label.visible = k.line.visible = vis > .01;
  }

  // toys bob and spin
  for (const o of toys) {
    o.position.y = o.userData.base + Math.sin(t * .9 + o.userData.seed) * .25;
    o.rotation.y += o.userData.spin * .01;
    if (o.userData.flicker) o.userData.flicker.forEach((m, i) => m.scale.set(1 - i * .45 + Math.sin(t * 9 + i) * .03, 1 - i * .45 + Math.sin(t * 7) * .06, 1 - i * .45));
  }
  for (const o of confetti) {
    o.position.y = o.userData.base + Math.sin(t * .7 + o.userData.seed) * .35;
    o.rotation.x += o.userData.spin * .006; o.rotation.y += o.userData.spin * .008;
  }
  title.rotation.z = reduce ? 0 : Math.sin(t * .6) * .03;

  hint.style.opacity = S.p < .01 && S.intro < .1 && mode === 'road' ? '1' : '0';
  finalCta.classList.toggle('on', S.p > .93 && mode === 'road');
  renderer.render(scene, camera);
}

/* boot */
build().then(() => {
  enterBtn.disabled = false; enterLabel.textContent = 'Vào';
  prog.style.strokeDashoffset = '0';
});
renderer.setAnimationLoop(frame);
enterBtn.addEventListener('click', () => {
  $('#intro').classList.add('gone');
  if (!reduce) {
    lenis = new Lenis({ lerp: .075, wheelMultiplier: .8, touchMultiplier: 1.4 });
    gsap.ticker.add(tt => lenis.raf(tt * 1000)); gsap.ticker.lagSmoothing(0);
  }
  gsap.to(S, { intro: 0, duration: reduce ? .01 : 3.2, ease: 'power3.inOut' });
});
