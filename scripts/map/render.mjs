#!/usr/bin/env node
/** Offline visual geometry evidence. Colours are NOT taxes or reachability. */
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { feature, mesh } from 'topojson-client';
import { geoIdentity, geoPath } from 'd3-geo';
import { createRequire } from 'node:module';
import { initWasm, Resvg } from '@resvg/resvg-wasm';
const require = createRequire(import.meta.url);

const root = fileURLToPath(new URL('../../', import.meta.url));
const output = path.join(root, 'docs/map');
const bytes = await readFile(path.join(root, 'site/data/map/switzerland-2026.json'));
const topology = JSON.parse(bytes);
const noDataIds = topology.meta.noDataIds;
const municipalities = feature(topology, topology.objects.gemeinden);
const lakes = feature(topology, topology.objects.lakes);
const all = { type: 'FeatureCollection', features: [...municipalities.features, ...lakes.features] };
const projection = geoIdentity().reflectY(true).fitExtent([[45, 110], [1355, 890]], all);
const draw = geoPath(projection);
const paths = municipalities.features.map(f => `<path class="municipality${noDataIds.includes(f.id) ? ' no-data' : ''}" data-id="${f.id}" fill="${noDataIds.includes(f.id) ? '#94a3b8' : '#97c2a5'}" d="${draw(f)}"><title>BFS ${f.id}${noDataIds.includes(f.id) ? ': no data' : ''}</title></path>`).join('');
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1000" viewBox="0 0 1400 1000">
<rect width="1400" height="1000" fill="#f8fafc"/>
<g font-family="Arial, sans-serif" fill="#1e293b"><text x="45" y="48" font-size="28" font-weight="bold">Switzerland · 2026 boundary geometry review</text><text x="45" y="80" font-size="17">2,110 tax municipalities + 3 no-data areas · LV95 (EPSG:2056) · not a tax/reachability map</text></g>
<g id="municipalities">${paths}</g>
<path d="${draw(mesh(topology, topology.objects.gemeinden, (a, b) => a !== b))}" fill="none" stroke="#f8fafc" stroke-width="0.55" stroke-linejoin="round"/>
<g id="lakes" fill="#a4d0e6" stroke="#6296ad" stroke-width="0.45">${lakes.features.map(f => `<path d="${draw(f)}"/>`).join('')}</g>
<path d="${draw(mesh(topology, topology.objects.cantons))}" fill="none" stroke="#334155" stroke-width="1.15" stroke-linejoin="round"/>
<g font-family="Arial, sans-serif" font-size="16" fill="#334155"><rect x="45" y="923" width="20" height="15" fill="#97c2a5"/><text x="75" y="936">Municipality geometry</text><rect x="325" y="923" width="20" height="15" fill="#94a3b8"/><text x="355" y="936">No data: 2391, 5391, 5394</text><rect x="690" y="923" width="20" height="15" fill="#a4d0e6"/><text x="720" y="936">Lakes</text><text x="45" y="973" font-size="14">Source: Bundesamt für Statistik (BFS), GEOSTAT · swiss-maps 4.7.0 · geodata non-commercial licence issue unresolved</text></g>
</svg>`;
assert(!/NaN|Infinity/.test(svg));
await mkdir(output, { recursive: true });
const resvgRoot = path.dirname(require.resolve('@resvg/resvg-wasm'));
await initWasm(await readFile(path.join(resvgRoot, 'index_bg.wasm')));
const fontDirectory = process.env.MAP_FONT_DIR || '/usr/share/fonts/truetype/dejavu';
const fonts = await Promise.all(['DejaVuSans.ttf', 'DejaVuSans-Bold.ttf'].map(name => readFile(path.join(fontDirectory, name))));
const renderer = new Resvg(svg, { font: { fontBuffers: fonts, defaultFontFamily: 'DejaVu Sans', sansSerifFamily: 'DejaVu Sans' } });
try {
  const image = renderer.render();
  try {
    assert.equal(image.width, 1400);
    assert.equal(image.height, 1000);
    const png = image.asPng();
    await writeFile(path.join(output, 'switzerland-2026.png'), png);
    const hash = b => createHash('sha256').update(b).digest('hex');
    const report = { mapSha256: hash(bytes), pngSha256: hash(png), renderer: '@resvg/resvg-wasm 2.6.2 (offline SVG to PNG)', width: image.width, height: image.height, municipalityPaths: municipalities.features.length, noDataIds, networkRequestsAllowed: false, scope: 'Geometry-only review; no tax values or official/legal approval' };
    await writeFile(path.join(output, 'render-report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report));
  } finally { image.free(); }
} finally { renderer.free(); }
