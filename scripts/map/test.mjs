#!/usr/bin/env node
/** Real-data acceptance tests. Missing tax data is a failure unless explicitly skipped. */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import { gzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { feature, neighbors } from 'topojson-client';
import { geoIdentity, geoPath } from 'd3-geo';

const require = createRequire(import.meta.url);
const root = fileURLToPath(new URL('../../', import.meta.url));
const output = path.join(root, 'site/data/map/switzerland-2026.json');
const source = path.dirname(require.resolve('swiss-maps/package.json'));
const noDataIds = [2391, 5391, 5394];
const bytes = await readFile(output).catch(error => assert.fail(`Build the real map first: ${error.message}`));
const topology = JSON.parse(bytes);
const geometries = topology.objects.gemeinden.geometries;
const sorted = ids => [...ids].map(Number).sort((a, b) => a - b);
const sha256 = content => createHash('sha256').update(content).digest('hex');

test('pinned 4.7.0 input hashes and verbatim licence/README notices', async () => {
  const manifest = JSON.parse(await readFile(path.join(root, 'docs/map/source-manifest.json')));
  assert.equal(manifest.version, '4.7.0');
  for (const [name, digest] of Object.entries(manifest.files)) {
    assert.equal(sha256(await readFile(path.join(source, name))), digest, name);
  }
  for (const [name, copy] of [['LICENSE', 'swiss-maps-4.7.0-LICENSE.txt'], ['README.md', 'swiss-maps-4.7.0-README.md']]) {
    assert.deepEqual(await readFile(path.join(root, 'docs/map', copy)), await readFile(path.join(source, name)));
  }
});

test('real map has exactly the source BFS IDs, 2110 municipalities + 3 no-data areas', async () => {
  assert.equal(topology.type, 'Topology');
  assert.deepEqual(Object.keys(topology.objects).sort(), ['cantons', 'gemeinden', 'lakes']);
  assert.equal(geometries.length, 2113);
  assert.equal(new Set(geometries.map(g => g.id)).size, 2113, 'duplicate BFS IDs');
  assert.deepEqual(topology.meta.noDataIds, noDataIds);
  const mapshaper = require('mapshaper');
  // Read the real DBF records, not a fabricated range of BFS IDs.
  const records = await mapshaper.applyCommands(`-i "${path.join(source, '2026/municipalities.dbf')}" -o format=json ids.json`);
  assert.deepEqual(sorted(geometries.map(g => g.id)), sorted(JSON.parse(records['ids.json']).map(r => r.id)));
  for (const id of noDataIds) assert(geometries.some(g => g.id === id), `missing ${id}`);
  assert.equal(topology.objects.cantons.geometries.length, 26);
  assert.equal(topology.objects.lakes.geometries.length, 22);
});

test('map municipality ID set equals the actual 2026 tax ID set exactly', async context => {
  const taxFile = path.join(root, 'site/data/gemeinden-2026.json');
  let tax;
  try { tax = JSON.parse(await readFile(taxFile, 'utf8')); }
  catch (error) {
    if (error.code === 'ENOENT' && process.argv.includes('--allow-missing-tax')) {
      context.skip('BLOCKED: real gemeinden-2026.json not integrated; source checks are not tax acceptance');
      return;
    }
    throw error;
  }
  const taxIds = Object.keys(tax.gemeinden);
  assert.equal(taxIds.length, 2110, 'actual tax count');
  assert.deepEqual(sorted(geometries.filter(g => !noDataIds.includes(g.id)).map(g => g.id)), sorted(taxIds));
  for (const id of noDataIds) assert(!Object.hasOwn(tax.gemeinden, String(id)), `${id} is not a tax municipality`);
});

test('LV95 projection, quantization, metadata and compressed budgets are valid', () => {
  assert.equal(topology.meta.year, 2026);
  assert.equal(topology.meta.version, '4.7.0');
  assert.equal(topology.meta.projection, 'EPSG:2056');
  assert.match(topology.meta.source, /Bundesamt für Statistik/);
  assert.match(topology.meta.licenceStatus, /Unresolved/);
  assert.equal(topology.meta.simplification.jointTopology, true);
  assert.equal(topology.meta.quantization, 100000);
  assert(bytes.length <= 1500000, `${bytes.length} raw bytes`);
  assert(gzipSync(bytes).length <= 500000, `${gzipSync(bytes).length} gzip bytes`);
  for (const number of [...topology.bbox, ...topology.transform.scale, ...topology.transform.translate]) assert(Number.isFinite(number));
  assert(topology.transform.scale.every(s => s > 0 && s < 5));
  assert(topology.bbox[0] > 2400000 && topology.bbox[2] < 2900000);
  assert(topology.bbox[1] > 1000000 && topology.bbox[3] < 1400000);
  assert.equal(bytes.toString(), JSON.stringify(topology), 'minified, no incidental whitespace');
});

test('all arcs decode to finite LV95 vertices; polygon rings are closed and non-degenerate', () => {
  for (const arc of topology.arcs) {
    assert(arc.length >= 2);
    let x = 0, y = 0;
    for (const delta of arc) {
      assert.equal(delta.length, 2);
      assert(delta.every(Number.isSafeInteger));
      x += delta[0]; y += delta[1];
      assert(x >= 0 && x <= 99999 && y >= 0 && y <= 99999);
    }
  }
  for (const [name, object] of Object.entries(topology.objects)) {
    assert.equal(object.type, 'GeometryCollection');
    assert.equal(new Set(object.geometries.map(g => g.id)).size, object.geometries.length);
    for (const geometry of object.geometries) {
      const label = `${name}/${geometry.id}`;
      assert(Number.isSafeInteger(geometry.id), label);
      assert(!Object.hasOwn(geometry, 'properties'), label);
      assert(['Polygon', 'MultiPolygon'].includes(geometry.type), label);
      for (const index of geometry.arcs.flat(Infinity)) {
        assert(Number.isInteger(index) && (index < 0 ? ~index : index) < topology.arcs.length, label);
      }
      const decoded = feature(topology, geometry);
      const polygons = decoded.geometry.type === 'Polygon' ? [decoded.geometry.coordinates] : decoded.geometry.coordinates;
      assert(polygons.length > 0, label);
      for (const polygon of polygons) {
        assert(polygon.length > 0, label);
        for (const ring of polygon) {
          assert(ring.length >= 4, label);
          assert.deepEqual(ring[0], ring.at(-1), label);
          assert(new Set(ring.slice(0, -1).map(p => p.join(','))).size >= 3, label);
          let area2 = 0;
          const [ox, oy] = ring[0];
          for (let i = 1; i < ring.length; i++) {
            const [x, y] = ring[i], [px, py] = ring[i - 1];
            assert(Number.isFinite(x) && Number.isFinite(y), label);
            area2 += (px - ox) * (y - oy) - (x - ox) * (py - oy);
          }
          assert(Math.abs(area2) > 0, `zero-area ring: ${label}`);
          // Proper non-adjacent edge crossings are invalid polygon interiors.
          // Bounding-box rejection keeps this inexpensive on the real simplified rings.
          const cross = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
          for (let i = 0; i < ring.length - 1; i++) for (let j = i + 2; j < ring.length - 1; j++) {
            if (i === 0 && j === ring.length - 2) continue;
            const a = ring[i], b = ring[i + 1], c = ring[j], d = ring[j + 1];
            if (Math.max(a[0], b[0]) < Math.min(c[0], d[0]) || Math.max(c[0], d[0]) < Math.min(a[0], b[0]) ||
                Math.max(a[1], b[1]) < Math.min(c[1], d[1]) || Math.max(c[1], d[1]) < Math.min(a[1], b[1])) continue;
            assert(!(cross(a, b, c) * cross(a, b, d) < 0 && cross(c, d, a) * cross(c, d, b) < 0), `self-crossing ring: ${label}`);
          }
        }
      }
    }
  }
});

test('municipality neighbours and canton/lake shores share the same simplified arcs', () => {
  const sets = {};
  for (const [name, object] of Object.entries(topology.objects)) sets[name] = new Set(object.geometries.flatMap(g => g.arcs.flat(Infinity).map(i => i < 0 ? ~i : i)));
  const shared = (a, b) => [...sets[a]].filter(i => sets[b].has(i)).length;
  assert(shared('gemeinden', 'cantons') >= 900);
  assert(shared('gemeinden', 'lakes') >= 150);
  assert(shared('cantons', 'lakes') > 0);
  const adjacency = neighbors(geometries);
  assert(adjacency.filter(n => n.length).length >= 2100);
  const usages = new Map();
  for (const g of geometries) for (const ref of new Set(g.arcs.flat(Infinity))) {
    const index = ref < 0 ? ~ref : ref;
    if (!usages.has(index)) usages.set(index, []);
    usages.get(index).push(ref >= 0);
  }
  let borders = 0;
  for (const [index, directions] of usages) if (directions.length === 2) {
    assert.notEqual(directions[0], directions[1], `neighbour arc ${index} must have opposite orientation`);
    borders++;
  }
  assert(borders >= 5000);
  const collection = feature(topology, topology.objects.gemeinden);
  const projection = geoIdentity().reflectY(true).fitExtent([[20, 20], [1180, 820]], collection);
  const draw = geoPath(projection);
  for (const f of collection.features) {
    assert(draw.centroid(f).every(Number.isFinite));
    const d = draw(f);
    assert(d && !/NaN|Infinity/.test(d), `finite rendered path: ${f.id}`);
  }
  console.log(`Shared arcs: municipalities/cantons=${shared('gemeinden', 'cantons')}, municipalities/lakes=${shared('gemeinden', 'lakes')}; neighbour borders=${borders}`);
});

test('render evidence is a real full-size PNG of this exact topology', async () => {
  const image = await readFile(path.join(root, 'docs/map/switzerland-2026.png'));
  const { PNG } = require('pngjs');
  const decoded = PNG.sync.read(image);
  assert.equal(decoded.width, 1400);
  assert.equal(decoded.height, 1000);
  let land = 0, water = 0, grey = 0;
  for (let i = 0; i < decoded.data.length; i += 4) {
    const [r, g, b] = decoded.data.subarray(i, i + 3);
    if (r === 151 && g === 194 && b === 165) land++;
    if (r === 164 && g === 208 && b === 230) water++;
    if (r === 148 && g === 163 && b === 184) grey++;
  }
  assert(land > 200000 && water > 10000 && grey > 30, `real land/water/no-data pixels: ${land}/${water}/${grey}`);
  const report = JSON.parse(await readFile(path.join(root, 'docs/map/render-report.json')));
  assert.equal(report.mapSha256, sha256(bytes), 'screenshot must be regenerated after a map change');
  assert.equal(report.pngSha256, sha256(image));
  assert.equal(report.municipalityPaths, 2113);
  assert.deepEqual(report.noDataIds, noDataIds);
});

test('two real rebuilds produce byte-identical committed output', { skip: !process.argv.includes('--rebuild') }, async () => {
  const before = await readFile(output);
  execFileSync(process.execPath, ['scripts/map/build.mjs'], { cwd: root, stdio: 'pipe' });
  const first = await readFile(output);
  execFileSync(process.execPath, ['scripts/map/build.mjs'], { cwd: root, stdio: 'pipe' });
  const second = await readFile(output);
  assert.deepEqual(first, before, 'committed map must match a clean build');
  assert.deepEqual(second, first);
  console.log(`Reproducible SHA-256: ${sha256(first)}`);
});
