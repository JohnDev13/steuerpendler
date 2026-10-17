#!/usr/bin/env node
/** Build jointly noded LV95 TopoJSON from the pinned, real 2026 shapefiles. */
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { gzipSync } from 'node:zlib';

const require = createRequire(import.meta.url);
const mapshaper = require('mapshaper');
const root = fileURLToPath(new URL('../../', import.meta.url));
const sourceRoot = path.dirname(require.resolve('swiss-maps/package.json'));
const sourcePackage = JSON.parse(await readFile(path.join(sourceRoot, 'package.json'), 'utf8'));
if (sourcePackage.version !== '4.7.0') throw new Error('Expected swiss-maps@4.7.0');
if (require('mapshaper/package.json').version !== '0.7.87') throw new Error('Expected mapshaper@0.7.87 for reproducible output');
const manifest = JSON.parse(await readFile(path.join(root, 'docs/map/source-manifest.json'), 'utf8'));
for (const [name, expected] of Object.entries(manifest.files)) {
  const actual = createHash('sha256').update(await readFile(path.join(sourceRoot, name))).digest('hex');
  if (actual !== expected) throw new Error(`Pinned source hash mismatch: ${name}`);
}
const source = path.join(sourceRoot, '2026');
for (const name of ['municipalities', 'cantons', 'lakes']) {
  const prj = await readFile(path.join(source, `${name}.prj`), 'utf8');
  if (!prj.includes('"EPSG",2056')) throw new Error(`${name}: expected LV95 EPSG:2056`);
}
const quote = value => `"${value.replaceAll('"', '\\"')}"`;
// combine-files creates ONE arc topology before simplification. Never simplify layers separately.
const commands = `-i ${['municipalities', 'cantons', 'lakes'].map(n => quote(path.join(source, `${n}.shp`))).join(' ')} combine-files ` +
  '-rename-layers gemeinden,cantons,lakes ' +
  '-simplify weighted interval=100 planar keep-shapes ' +
  '-o format=topojson quantization=100000 id-field=id drop-table bbox map.json';
const result = await mapshaper.applyCommands(commands);
const topology = JSON.parse(result['map.json']);
for (const object of Object.values(topology.objects)) {
  for (const geometry of object.geometries) {
    geometry.id = Number(geometry.id);
    if (!Number.isSafeInteger(geometry.id)) throw new Error('Missing integer source ID');
    delete geometry.properties;
  }
  object.geometries.sort((a, b) => a.id - b.id);
}
topology.meta = {
  source: 'Bundesamt für Statistik (BFS), GEOSTAT; via swiss-maps',
  version: '4.7.0',
  projection: 'EPSG:2056',
  year: 2026,
  noDataIds: [2391, 5391, 5394],
  units: 'metres',
  coordinates: 'CH1903+ / LV95; use d3.geoIdentity().reflectY(true), not a spherical projection',
  simplification: { tool: 'mapshaper', version: require('mapshaper/package.json').version, method: 'weighted Visvalingam', intervalMetres: 100, keepShapes: true, jointTopology: true },
  quantization: 100000,
  licenceStatus: 'Unresolved: swiss-maps README states non-commercial geodata use; not legal clearance',
};
const bytes = Buffer.from(JSON.stringify(topology));
if (bytes.length > 1500000 || gzipSync(bytes).length > 500000) throw new Error('Map exceeds size budget');
const output = path.join(root, 'site/data/map/switzerland-2026.json');
await mkdir(path.dirname(output), { recursive: true });
await writeFile(output, bytes);
console.log(JSON.stringify({ output: path.relative(root, output), bytes: bytes.length, gzipBytes: gzipSync(bytes).length, sha256: createHash('sha256').update(bytes).digest('hex') }));
