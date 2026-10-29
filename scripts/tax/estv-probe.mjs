// Targeted official ESTV calculations (network; run in Actions by .github/workflows/estv-probe.yml).
// Each scripts/tax/probes/<name>.json lists {bfs, civil, kids, income, church} cases (or "grid" expansions);
// the answers are frozen in tests/reference/estv-2026-probes/<name>.jsonl like the broad sample.
// Usage: node scripts/tax/estv-probe.mjs scripts/tax/probes/<name>.json [...]
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { basename, join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const URL = 'https://swisstaxcalculator.estv.admin.ch/delegate/ost-integration/v1/lg-proxy/operation/c3b67379_ESTV/API_calculateDetailedTaxes';
const CONFESSION = { none: 4, reformed: 1, catholic: 2 };
const locations = JSON.parse(readFileSync(join(ROOT, 'vendor/swisstaxcalculator/data/parsed/2026/locations.json'), 'utf8'));

const expand = spec => {
  const out = [];
  for (const g of spec.cases) {
    const list = k => (Array.isArray(g[k]) ? g[k] : [g[k]]);
    const incomes = g.incomes ?? (g.from !== undefined ? Array.from({ length: Math.floor((g.to - g.from) / g.step) + 1 }, (_, i) => g.from + i * g.step) : list('income'));
    for (const bfs of list('bfs')) for (const civil of list('civil')) for (const kids of list('kids'))
      for (const church of list('church')) for (const income of incomes) out.push({ bfs, civil, kids, income, church });
  }
  return out;
};

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

for (const file of process.argv.slice(2)) {
  const name = basename(file, '.json');
  const target = join(ROOT, 'tests/reference/estv-2026-probes', `${name}.jsonl`);
  if (existsSync(target)) { console.log(`${name}: already captured`); continue; }
  const cases = expand(JSON.parse(readFileSync(file, 'utf8')));
  const retrieved = new Date().toISOString();
  const lines = [];
  for (const [index, c] of cases.entries()) {
    const loc = locations.find(l => l.BfsID === c.bfs);
    if (!loc) throw new Error(`no location ${c.bfs}`);
    const married = c.civil === 'married';
    const body = JSON.stringify({ SimKey: null, TaxYear: 2026, TaxLocationID: loc.TaxLocationID, Relationship: married ? 2 : 1,
      Confession1: CONFESSION[c.church], Children: Array.from({ length: c.kids }, () => ({ Age: 10 })), Age1: 35, RevenueType1: 1,
      Revenue1: c.income, Fortune: 0, Confession2: married ? CONFESSION[c.church] : 0, Age2: married ? 35 : 0, RevenueType2: 0,
      Revenue2: 0, Budget: [] });
    const text = await post(body);
    lines.push(JSON.stringify({ id: `${name}-${String(index + 1).padStart(4, '0')}`, bfs: c.bfs, city: loc.BfsName, canton: loc.Canton,
      civil: c.civil, kids: c.kids, income: c.income, church: c.church, url: URL, retrieved, request: JSON.parse(body),
      responseSha256: createHash('sha256').update(text).digest('hex'), response: JSON.parse(text).response }));
    await new Promise(r => setTimeout(r, 250));
  }
  writeFileSync(target, lines.join('\n') + '\n');
  console.log(`${name}: captured ${lines.length}`);
}
