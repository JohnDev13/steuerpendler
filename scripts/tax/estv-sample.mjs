// Captures a broad official ESTV 2026 sample (network; run in Actions) into
// tests/reference/estv-2026-sample.jsonl: one line per case with the exact request, the response body and its
// SHA-256. Cantonal capitals, single (0/2 children) and married one-income (0-3 children), four incomes, no church,
// plus one church variant per canton. Usage: node scripts/tax/estv-sample.mjs
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const URL = 'https://swisstaxcalculator.estv.admin.ch/delegate/ost-integration/v1/lg-proxy/operation/c3b67379_ESTV/API_calculateDetailedTaxes';
const CAPITALS = [261, 351, 1061, 1201, 1372, 1407, 1509, 1632, 1711, 2196, 2601, 2701, 2829, 2939, 3001, 3101, 3203,
  3901, 4001, 4566, 5002, 5586, 6266, 6458, 6621, 6711];
const CONFESSION = { none: 4, reformed: 1, catholic: 2 };
const locations = JSON.parse(readFileSync(join(ROOT, 'vendor/swisstaxcalculator/data/parsed/2026/locations.json'), 'utf8'));
const profiles = [['single', 0], ['single', 2], ['married', 0], ['married', 1], ['married', 2], ['married', 3]];
const incomes = [50000, 90000, 150000, 300000];

const cases = [];
for (const bfs of CAPITALS) {
  const loc = locations.find(l => l.BfsID === bfs);
  if (!loc) throw new Error(`no location ${bfs}`);
  for (const [civil, kids] of profiles) for (const income of incomes) cases.push({ loc, civil, kids, income, church: 'none' });
  cases.push({ loc, civil: 'married', kids: 2, income: 90000, church: loc.Canton === 'GE' || loc.Canton === 'NE' ? 'reformed' : 'catholic' });
}

function request({ loc, civil, kids, income, church }) {
  const married = civil === 'married';
  return JSON.stringify({ SimKey: null, TaxYear: 2026, TaxLocationID: loc.TaxLocationID, Relationship: married ? 2 : 1,
    Confession1: CONFESSION[church], Children: Array.from({ length: kids }, () => ({ Age: 10 })), Age1: 35, RevenueType1: 1,
    Revenue1: income, Fortune: 0, Confession2: married ? CONFESSION[church] : 0, Age2: married ? 35 : 0, RevenueType2: 0,
    Revenue2: 0, Budget: [] });
}

async function post(body) {
  for (let attempt = 1; ; attempt++) {
    try {
      const res = await fetch(URL, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body });
      const text = await res.text();
      if (res.status !== 200) throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
      JSON.parse(text);
      return text;
    } catch (error) {
      if (attempt >= 5) throw error;
      await new Promise(r => setTimeout(r, 3000 * attempt));
    }
  }
}

const lines = [];
const retrieved = new Date().toISOString();
for (const [index, c] of cases.entries()) {
  const body = request(c);
  const text = await post(body);
  lines.push(JSON.stringify({ id: `s${String(index + 1).padStart(3, '0')}`, bfs: c.loc.BfsID, city: c.loc.BfsName, canton: c.loc.Canton,
    civil: c.civil, kids: c.kids, income: c.income, church: c.church, url: URL, retrieved,
    request: JSON.parse(body), responseSha256: createHash('sha256').update(text).digest('hex'), response: JSON.parse(text).response }));
  await new Promise(r => setTimeout(r, 250));
}
writeFileSync(join(ROOT, 'tests/reference/estv-2026-sample.jsonl'), lines.join('\n') + '\n');
console.log(`captured ${lines.length} official cases`);
