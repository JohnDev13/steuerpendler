// Fetches current ESTV data for tax year 2026 (network; run in Actions):
//  1. the three raw tables the engine imports (tarifs, factors, deductions) into vendor/.../data/raw/2026,
//  2. today's official answers to the 29 frozen requests in tests/reference/estv-2026 into --out,
// and prints what differs from the committed copies. Usage: node scripts/tax/estv-fetch.mjs --out DIR
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const API = 'https://swisstaxcalculator.estv.admin.ch/delegate/ost-integration/v1/lg-proxy/operation/c3b67379_ESTV';
const RAW = join(ROOT, 'vendor/swisstaxcalculator/data/raw/2026');
const REF = join(ROOT, 'tests/reference/estv-2026');
const out = resolve(process.argv[process.argv.indexOf('--out') + 1] ?? 'estv-fresh');
mkdirSync(out, { recursive: true });
const sha = text => createHash('sha256').update(text).digest('hex');

async function post(path, body) {
  for (let attempt = 1; ; attempt++) {
    try {
      const res = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body });
      const text = await res.text();
      if (res.status !== 200) throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
      JSON.parse(text);
      return text;
    } catch (error) {
      if (attempt >= 4) throw error;
      await new Promise(r => setTimeout(r, 2000 * attempt));
    }
  }
}

const lines = [];
const tables = { tarifs: ['/API_exportManyTaxScales', 88], factors: ['/API_exportManySimpleRates', 99], deductions: ['/API_exportManyDeductions', 88] };
for (const [name, [path, group]] of Object.entries(tables)) {
  const fresh = await post(path, JSON.stringify({ TaxYear: 2026, TaxGroupID: group }));
  const file = join(RAW, `${name}.json`);
  const old = readFileSync(file, 'utf8');
  const count = JSON.parse(fresh).response.length;
  lines.push(`table ${name}: ${sha(old) === sha(fresh) ? 'unchanged' : 'CHANGED'} (${count} entries, sha256 ${sha(fresh).slice(0, 12)})`);
  if (sha(old) !== sha(fresh)) {
    // Which entries changed (by canonical JSON of each entry)
    const key = e => JSON.stringify(e);
    const before = new Set(JSON.parse(old).response.map(key));
    const after = new Set(JSON.parse(fresh).response.map(key));
    const added = [...after].filter(e => !before.has(e)), removed = [...before].filter(e => !after.has(e));
    lines.push(`  ${name}: ${added.length} entries new/changed, ${removed.length} old entries gone; e.g. ${added.slice(0, 2).map(s => s.slice(0, 300)).join(' ;; ')}`);
    writeFileSync(file, fresh);
  }
}

const FIELDS = ['IncomeTaxFed', 'IncomeTaxCanton', 'IncomeTaxCity', 'IncomeTaxChurch', 'PersonalTax', 'TaxCredit', 'TotalNetTax'];
let same = 0;
for (const name of readdirSync(REF).filter(n => /^estv-2026-\d\d-(tax|budget)\.request\.json$/.test(n)).sort()) {
  const kind = name.includes('-tax.') ? 'tax' : 'budget';
  const path = kind === 'tax' ? '/API_calculateDetailedTaxes' : '/API_calculateTaxBudget';
  const request = readFileSync(join(REF, name), 'utf8');
  const fresh = await post(path, request);
  const responseName = name.replace('.request.', '.response.');
  writeFileSync(join(out, responseName), fresh);
  const old = readFileSync(join(REF, responseName), 'utf8');
  if (sha(old) === sha(fresh)) { same++; continue; }
  const a = JSON.parse(old).response, b = JSON.parse(fresh).response;
  if (kind === 'tax') {
    const diff = FIELDS.filter(f => a[f] !== b[f]).map(f => `${f} ${a[f]}->${b[f]}`);
    lines.push(`${responseName}: ${diff.length ? diff.join(', ') : 'bytes differ, amounts equal'}`);
  } else {
    lines.push(`${responseName}: budget differs`);
  }
}
lines.push(`frozen responses byte-identical today: ${same}`);
writeFileSync(join(out, 'summary.txt'), lines.join('\n') + '\n');
console.log(lines.join('\n'));
