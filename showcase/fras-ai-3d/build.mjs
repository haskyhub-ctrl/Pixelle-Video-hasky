// Builds a single self-contained index.html: bundles three.js + GSAP + scene code
// and inlines Phosphor icons as SVG, so the page runs with no CDN at all.
import { build } from 'esbuild';
import { readFileSync, writeFileSync } from 'node:fs';

const ICON_DIR = 'node_modules/@phosphor-icons/core/assets';
const svg = (name, weight = 'regular', cls = '') => {
  const file = weight === 'regular' ? `${ICON_DIR}/regular/${name}.svg` : `${ICON_DIR}/${weight}/${name}-${weight}.svg`;
  return readFileSync(file, 'utf8').trim()
    .replace('<svg ', `<svg class="ic${cls ? ' ' + cls : ''}" aria-hidden="true" focusable="false" fill="currentColor" `);
};

let html = readFileSync('src/template.html', 'utf8');
html = html.replace(/<i class="ph(?:-(fill|bold))? ph-([a-z-]+)((?: [a-z-]+)*)"([^>]*)><\/i>/g,
  (_, weight, name, extra, attrs) => svg(name, weight || 'regular', extra.trim()).replace('<svg ', `<svg${attrs} `));
if (/class="ph/.test(html)) throw new Error('unconverted icon left in template');

const labelIcons = Object.fromEntries(['lightning', 'plugs', 'fire-extinguisher', 'door-open', 'circuitry', 'check-circle']
  .map(n => [n, svg(n, 'fill')]));

const out = await build({ entryPoints: ['src/main.js'], bundle: true, minify: true, format: 'iife', write: false, target: 'es2020', legalComments: 'none' });
const js = `window.__ICONS=${JSON.stringify(labelIcons)};\n${out.outputFiles[0].text}`.replaceAll('</script', '<\\/script');
html = html.replace('<script>/*APP*/</script>', () => `<script>${js}</script>`);
writeFileSync('index.html', html);
console.log('index.html', (html.length / 1024).toFixed(0) + ' KB');
