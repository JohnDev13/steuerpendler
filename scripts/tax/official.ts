import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { calculateTax, type Church, type Gemeinde, type TaxProfile } from '../../src/tax';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const CASE_IDS = Array.from({ length: 29 }, (_, index) => `estv-2026-${String(index + 1).padStart(2, '0')}`);
const DIGEST = /^[0-9a-f]{64}$/;

type CsvRow = Record<string, string>;
type FrontendComponents = Pick<ReturnType<typeof calculateTax>, 'bund' | 'kanton' | 'gemeinde' | 'kirche' | 'personal'>;
type OfficialResponse = { IncomeTaxFed: number; IncomeTaxCanton: number; IncomeTaxCity: number; IncomeTaxChurch: number; PersonalTax: number };

function sha256(bytes: Buffer | string): string {
  return createHash('sha256').update(bytes).digest('hex');
}

export function officialTolerance(official: number): number {
  if (!Number.isFinite(official)) throw new Error('Official value must be finite');
  return Math.max(5, Math.abs(official) * 0.001);
}

export async function verifyResponseEvidence(path: string, expectedSha256: string): Promise<string> {
  if (!DIGEST.test(expectedSha256)) throw new Error(`Invalid response SHA-256: ${expectedSha256}`);
  const bytes = await readFile(path);
  try { JSON.parse(bytes.toString('utf8')); } catch { throw new Error(`Malformed response evidence JSON: ${path}`); }
  const actual = sha256(bytes);
  if (actual !== expectedSha256) throw new Error(`Response evidence hash mismatch: ${path}`);
  return actual;
}

export function compareComponents(frontend: FrontendComponents, official: OfficialResponse) {
  const pairs = {
    federal: [frontend.bund, official.IncomeTaxFed], canton: [frontend.kanton, official.IncomeTaxCanton],
    city: [frontend.gemeinde, official.IncomeTaxCity], church: [frontend.kirche, official.IncomeTaxChurch],
    personal: [frontend.personal, official.PersonalTax],
  } as const;
  const components = Object.fromEntries(Object.entries(pairs).map(([name, [frontendAmount, officialAmount]]) => {
    if (!Number.isFinite(officialAmount)) throw new Error(`Non-finite official ${name} component`);
    return [name, { frontend: frontendAmount, official: officialAmount, error: Math.abs(frontendAmount - officialAmount) }];
  })) as Record<keyof typeof pairs, { frontend: number; official: number; error: number }>;
  const federalMismatch = components.federal.error !== 0;
  const nonFederalMismatch = (['canton', 'city', 'church', 'personal'] as const).some(name => components[name].error !== 0);
  const mismatchGroup: 'federal-only' | 'non-federal-only' | 'mixed' | null = federalMismatch && nonFederalMismatch ? 'mixed' : federalMismatch ? 'federal-only' : nonFederalMismatch ? 'non-federal-only' : null;
  return { components, mismatchGroup };
}

function parseCsv(text: string): CsvRow[] {
  const records: string[][] = [];
  let record: string[] = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"') quoted = true;
    else if (char === ',') { record.push(field); field = ''; }
    else if (char === '\n') { record.push(field.replace(/\r$/, '')); records.push(record); record = []; field = ''; }
    else field += char;
  }
  if (quoted) throw new Error('Malformed CSV quoting');
  if (field || record.length) { record.push(field.replace(/\r$/, '')); records.push(record); }
  const header = records.shift();
  if (!header?.length) throw new Error('Official CSV has no header');
  return records.filter(row => row.some(Boolean)).map(row => {
    if (row.length !== header.length) throw new Error(`Official CSV row has ${row.length}/${header.length} columns`);
    return Object.fromEntries(header.map((name, index) => [name, row[index]]));
  });
}

function finite(row: CsvRow, key: string): number {
  const value = Number(row[key]);
  if (row[key] === '' || !Number.isFinite(value)) throw new Error(`${row.case_id}: non-finite ${key}`);
  return value;
}

export async function runOfficialComparison(root = ROOT) {
  const csvPath = resolve(root, 'tests/reference/estv-2026.csv');
  const csvBytes = await readFile(csvPath);
  const rows = parseCsv(csvBytes.toString('utf8'));
  const ids = rows.map(row => row.case_id);
  if (rows.length !== 29 || new Set(ids).size !== 29 || ids.some((id, index) => id !== CASE_IDS[index])) {
    throw new Error(`Official CSV must contain exactly ordered cases ${CASE_IDS[0]}..${CASE_IDS[28]}`);
  }

  const dataFiles = ['gemeinden-2026.json', ...['s', 'm'].flatMap(civil => [0, 1, 2, 3].map(kids => `tax-2026-${civil}-${kids}.json`))];
  const artifactSha256: Record<string, string> = {};
  const artifacts: Record<string, unknown> = {};
  for (const file of dataFiles) {
    const bytes = await readFile(resolve(root, 'site/data', file));
    artifactSha256[file] = sha256(bytes);
    artifacts[file] = JSON.parse(bytes.toString('utf8'));
  }
  const gemeinden = (artifacts['gemeinden-2026.json'] as { gemeinden: Record<string, Gemeinde> }).gemeinden;
  const results: (ReturnType<typeof compareComponents> & { caseId: string; numericPassed: boolean; error: number; [key: string]: unknown })[] = [];
  for (const row of rows) {
    if (row.capture_status !== 'captured' || row.comparability !== 'owner_pending' || row.official_gate !== 'pending') throw new Error(`${row.case_id}: invalid evidence state`);
    if (row.tax_year !== '2026' || row.age !== '35' || row.partner_income !== '0' || row.wealth !== '0' || row.income_basis !== 'gross_employment') throw new Error(`${row.case_id}: frozen official inputs changed`);
    const kids = finite(row, 'kids');
    const civil = row.civil === 'single' ? 's' : row.civil === 'married' ? 'm' : '';
    if (!civil || !Number.isInteger(kids) || kids < 0 || kids > 3) throw new Error(`${row.case_id}: unsupported profile`);
    if (!['none', 'reformed', 'catholic'].includes(row.church)) throw new Error(`${row.case_id}: unsupported church`);
    const bfs = finite(row, 'bfs');
    const municipality = gemeinden[String(bfs)];
    if (!municipality || municipality[0] !== row.city || municipality[1] !== row.canton) throw new Error(`${row.case_id}: municipality mismatch`);
    const profileFile = `tax-2026-${civil}-${kids}.json`;
    const profile = artifacts[profileFile] as TaxProfile;
    const official = finite(row, 'official_chf');
    const evidencePath = resolve(root, row.evidence);
    const evidenceSha256 = await verifyResponseEvidence(evidencePath, row.response_sha256);
    const evidence = JSON.parse(await readFile(evidencePath, 'utf8')) as { response: OfficialResponse };
    if (!evidence.response || typeof evidence.response !== 'object') throw new Error(`${row.case_id}: missing official response`);
    const frontend = calculateTax(profile, municipality, finite(row, 'income'), row.church as Church);
    const actual = frontend.total;
    if (!Number.isFinite(actual)) throw new Error(`${row.case_id}: non-finite shipped total`);
    const error = Math.abs(actual - official);
    const tolerance = officialTolerance(official);
    results.push({ caseId: row.case_id, city: row.city, canton: row.canton, bfs, civil: row.civil, kids, income: finite(row, 'income'), church: row.church, official, actual, error, tolerance, numericPassed: error <= tolerance, ...compareComponents(frontend, evidence.response), evidence: row.evidence, evidenceSha256 });
  }
  const numericFailureCount = results.filter(result => !result.numericPassed).length;
  const observedMismatchGroups = { 'federal-only': 0, 'non-federal-only': 0, mixed: 0 };
  for (const result of results) if (result.mismatchGroup) observedMismatchGroups[result.mismatchGroup]++;
  const largestComponentDiscrepancies = (Object.keys(results[0].components) as (keyof typeof results[0]['components'])[]).map(component => {
    const largest = results.reduce((best, result) => result.components[component].error > best.components[component].error ? result : best);
    return { component, caseId: largest.caseId, error: largest.components[component].error, frontend: largest.components[component].frontend, official: largest.components[component].official };
  }).sort((a, b) => b.error - a.error);
  return {
    sourceCsv: 'tests/reference/estv-2026.csv',
    sourceCsvSha256: sha256(csvBytes),
    artifactSha256,
    coverage: { expected: 29, compared: results.length, exact: results.length === 29 },
    threshold: 'max(5, abs(official) * 0.001)',
    comparability: 'owner_pending',
    officialApproval: 'pending',
    numericFailureCount,
    observedMismatchGroups,
    largestComponentDiscrepancies,
    maxAbsoluteError: Math.max(...results.map(result => result.error)),
    numericPassed: numericFailureCount === 0,
    passed: false,
    exitCode: 1,
    results,
  };
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  (async () => {
    const args = process.argv.slice(2);
    if (args.length > 2 || (args.length === 2 && args[0] !== '--report') || args.length === 1) throw new Error('Usage: official.ts [--report file]');
    const report = await runOfficialComparison();
    const reportPath = resolve(ROOT, args[1] ?? 'docs/tax/official-comparison-report.json');
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
    console.error(`Official comparison: ${report.numericFailureCount}/${report.coverage.compared} numeric failures; comparability ${report.comparability}`);
    console.error(`Observed mismatch groups: federal-only ${report.observedMismatchGroups['federal-only']}, non-federal-only ${report.observedMismatchGroups['non-federal-only']}, mixed ${report.observedMismatchGroups.mixed}`);
    console.error(`Largest component discrepancies: ${report.largestComponentDiscrepancies.map(item => `${item.component} CHF ${item.error} (${item.caseId})`).join('; ')}`);
    process.exitCode = report.exitCode;
  })().catch(error => { console.error(error); process.exitCode = 1; });
}
