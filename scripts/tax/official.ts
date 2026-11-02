import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { calculateTax, type Church, type Gemeinde, type TaxProfile } from '../../src/tax';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const CASE_IDS = Array.from({ length: 29 }, (_, index) => `estv-2026-${String(index + 1).padStart(2, '0')}`);
const DIGEST = /^[0-9a-f]{64}$/;
const ACCEPTANCE_PATH = 'docs/tax/owner-comparator-acceptance-2026-11-02.json';
const ACCEPTANCE_SHA256 = '6dfb8911b25e2f6c81682d72388f3257c6e5632520bd679e9445ebf9d6f679cd';
const DATA_FILES = ['gemeinden-2026.json', ...['s', 'm'].flatMap(civil => [0, 1, 2, 3].map(kids => `tax-2026-${civil}-${kids}.json`))];

type CsvRow = Record<string, string>;
type FrontendComponents = Pick<ReturnType<typeof calculateTax>, 'bund' | 'kanton' | 'gemeinde' | 'kirche' | 'personal'>;
type OfficialResponse = { IncomeTaxFed: number; IncomeTaxCanton: number; IncomeTaxCity: number; IncomeTaxChurch: number; PersonalTax: number };
type TaxCalculator = typeof calculateTax;
type AcceptanceCase = { caseId: string; evidence: string; request: string; requestSha256: string; responseSha256: string; officialChf: number };
type OwnerAcceptance = {
  schemaVersion: number;
  decisionId: string;
  decisionDate: string;
  ownerQuote: string;
  acceptanceKind: string;
  status: string;
  numericTolerance: string;
  sourceRevision: string;
  scope: { comparator: string; cases: number; boundedTo: string; estvEndorsement: boolean; estvCertification: boolean; productionRelease: boolean };
  adoptedInputsForThese29FrozenCasesOnly: { childAge: number; spouse: { age: string; confession: string; income: number }; budget: string };
  bindings: {
    referenceChecksums: { path: string; sha256: string };
    sourceCsv: { path: string; sha256: string };
    captureContract: { path: string; sha256: string };
    taxSource: { path: string; sha256: string };
    bvgSource: { path: string; sha256: string };
    siteDataArtifacts: Record<string, string>;
  };
  cases: AcceptanceCase[];
};

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

async function verifyRequestEvidence(path: string, expectedSha256: string): Promise<Record<string, unknown>> {
  if (!DIGEST.test(expectedSha256)) throw new Error(`Invalid request SHA-256: ${expectedSha256}`);
  const bytes = await readFile(path);
  let request: Record<string, unknown>;
  try { request = JSON.parse(bytes.toString('utf8')) as Record<string, unknown>; } catch { throw new Error(`Malformed request evidence JSON: ${path}`); }
  if (sha256(bytes) !== expectedSha256) throw new Error(`Request evidence hash mismatch: ${path}`);
  return request;
}

async function validateOwnerAcceptance(root: string, rows: CsvRow[], sourceCsvSha256: string, artifactSha256: Record<string, string>): Promise<OwnerAcceptance> {
  const bytes = await readFile(resolve(root, ACCEPTANCE_PATH));
  if (sha256(bytes) !== ACCEPTANCE_SHA256) throw new Error('Owner comparator acceptance manifest hash mismatch');
  let acceptance: OwnerAcceptance;
  try { acceptance = JSON.parse(bytes.toString('utf8')) as OwnerAcceptance; } catch { throw new Error('Malformed owner comparator acceptance manifest'); }
  const semanticFieldsAreExact = acceptance.schemaVersion === 1
    && acceptance.decisionId === 'owner-comparator-acceptance-2026-11-02'
    && acceptance.decisionDate === '2026-11-02'
    && acceptance.ownerQuote === 'Then change the contract as for me it Passes'
    && acceptance.acceptanceKind === 'ownerComparatorAcceptance'
    && acceptance.status === 'accepted'
    && acceptance.numericTolerance === 'max(5, abs(official) * 0.001)'
    && acceptance.sourceRevision === '2a5493c9ec111aaba52339f783bbf242f91fbeb2'
    && acceptance.scope?.comparator === 'frozen 2026 ESTV comparator'
    && acceptance.scope?.cases === 29
    && acceptance.scope?.boundedTo === 'the exact ordered, evidence-bound cases and file hashes in this manifest'
    && acceptance.scope?.estvEndorsement === false
    && acceptance.scope?.estvCertification === false
    && acceptance.scope?.productionRelease === false
    && acceptance.adoptedInputsForThese29FrozenCasesOnly?.childAge === 10
    && acceptance.adoptedInputsForThese29FrozenCasesOnly?.spouse?.age === 'same_as_primary'
    && acceptance.adoptedInputsForThese29FrozenCasesOnly?.spouse?.confession === 'same_as_primary'
    && acceptance.adoptedInputsForThese29FrozenCasesOnly?.spouse?.income === 0
    && acceptance.adoptedInputsForThese29FrozenCasesOnly?.budget === 'ESTV_native_defaults';
  if (!semanticFieldsAreExact) throw new Error('Owner comparator acceptance scope or decision changed');

  const checksumPath = 'tests/reference/SHA256SUMS';
  const checksumBytes = await readFile(resolve(root, checksumPath));
  if (acceptance.bindings?.referenceChecksums?.path !== checksumPath
      || acceptance.bindings.referenceChecksums.sha256 !== sha256(checksumBytes)) {
    throw new Error('Owner comparator acceptance reference checksum manifest mismatch');
  }
  // The historical manifest also contains unrelated probes; validate every frozen 2026
  // case sidecar, verification record, and CSV against its original digest.
  const evidenceLines = checksumBytes.toString('utf8').trimEnd().split('\n').map(line => {
    const match = /^([0-9a-f]{64})  (.+)$/.exec(line);
    if (!match) throw new Error('Malformed reference checksum entry');
    return { digest: match[1], path: match[2] };
  }).filter(entry => entry.path === 'estv-2026.csv' || entry.path.startsWith('estv-2026/'));
  if (evidenceLines.length < 29 * 9 || new Set(evidenceLines.map(entry => entry.path)).size !== evidenceLines.length) {
    throw new Error('Incomplete or duplicated frozen ESTV checksum coverage');
  }
  for (const { digest, path } of evidenceLines) {
    if (sha256(await readFile(resolve(root, 'tests/reference', path))) !== digest) {
      throw new Error(`Frozen ESTV evidence checksum mismatch: ${path}`);
    }
  }

  const fixedBindings = [
    ['sourceCsv', acceptance.bindings?.sourceCsv, 'tests/reference/estv-2026.csv', sourceCsvSha256],
    ['captureContract', acceptance.bindings?.captureContract, 'tests/reference/estv-2026/contract.json', sha256(await readFile(resolve(root, 'tests/reference/estv-2026/contract.json')))],
    ['taxSource', acceptance.bindings?.taxSource, 'src/tax.ts', sha256(await readFile(resolve(root, 'src/tax.ts')))],
    ['bvgSource', acceptance.bindings?.bvgSource, 'scripts/tax/bvg.ts', sha256(await readFile(resolve(root, 'scripts/tax/bvg.ts')))],
  ] as const;
  for (const [name, binding, path, actualSha256] of fixedBindings) {
    if (binding?.path !== path || binding?.sha256 !== actualSha256) throw new Error(`Owner comparator acceptance ${name} binding mismatch`);
  }
  if (Object.keys(acceptance.bindings.siteDataArtifacts ?? {}).join(',') !== DATA_FILES.join(',')) throw new Error('Owner comparator acceptance artifact list mismatch');
  for (const file of DATA_FILES) {
    if (acceptance.bindings.siteDataArtifacts[file] !== artifactSha256[file]) throw new Error(`Owner comparator acceptance artifact binding mismatch: ${file}`);
  }
  if (!Array.isArray(acceptance.cases) || acceptance.cases.length !== rows.length) throw new Error('Owner comparator acceptance case count mismatch');
  rows.forEach((row, index) => {
    const accepted = acceptance.cases[index];
    const request = `tests/reference/estv-2026/${row.case_id}-tax.request.json`;
    if (accepted?.caseId !== row.case_id || accepted.evidence !== row.evidence || accepted.request !== request
      || accepted.requestSha256 !== row.request_sha256 || accepted.responseSha256 !== row.response_sha256
      || accepted.officialChf !== finite(row, 'official_chf')) {
      throw new Error(`${row.case_id}: owner comparator acceptance case binding mismatch`);
    }
  });
  return acceptance;
}

export function compareComponents(frontend: FrontendComponents, official: OfficialResponse) {
  const pairs = {
    federal: [frontend.bund, official.IncomeTaxFed], canton: [frontend.kanton, official.IncomeTaxCanton],
    city: [frontend.gemeinde, official.IncomeTaxCity], church: [frontend.kirche, official.IncomeTaxChurch],
    personal: [frontend.personal, official.PersonalTax],
  } as const;
  const components = Object.fromEntries(Object.entries(pairs).map(([name, [frontendAmount, officialAmount]]) => {
    if (!Number.isFinite(frontendAmount)) throw new Error(`Non-finite frontend ${name} component`);
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

export async function runOfficialComparison(root = ROOT, taxCalculator: TaxCalculator = calculateTax) {
  const csvPath = resolve(root, 'tests/reference/estv-2026.csv');
  const csvBytes = await readFile(csvPath);
  const rows = parseCsv(csvBytes.toString('utf8'));
  const ids = rows.map(row => row.case_id);
  if (rows.length !== 29 || new Set(ids).size !== 29 || ids.some((id, index) => id !== CASE_IDS[index])) {
    throw new Error(`Official CSV must contain exactly ordered cases ${CASE_IDS[0]}..${CASE_IDS[28]}`);
  }

  const artifactSha256: Record<string, string> = {};
  const artifacts: Record<string, unknown> = {};
  for (const file of DATA_FILES) {
    const bytes = await readFile(resolve(root, 'site/data', file));
    artifactSha256[file] = sha256(bytes);
    artifacts[file] = JSON.parse(bytes.toString('utf8'));
  }
  const acceptance = await validateOwnerAcceptance(root, rows, sha256(csvBytes), artifactSha256);
  const gemeinden = (artifacts['gemeinden-2026.json'] as { gemeinden: Record<string, Gemeinde> }).gemeinden;
  const results: (ReturnType<typeof compareComponents> & { caseId: string; numericPassed: boolean; error: number; [key: string]: unknown })[] = [];
  for (const row of rows) {
    if (row.capture_status !== 'captured' || row.comparability !== 'owner_pending' || row.official_gate !== 'pending') throw new Error(`${row.case_id}: invalid evidence state`);
    if (row.tax_year !== '2026' || row.age !== '35' || row.partner_income !== '0' || row.wealth !== '0' || row.income_basis !== 'gross_employment' || row.budget !== 'ESTV_native_defaults') throw new Error(`${row.case_id}: frozen official inputs changed`);
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
    const evidence = JSON.parse(await readFile(evidencePath, 'utf8')) as { response: OfficialResponse & { TotalNetTax: number } };
    if (!evidence.response || typeof evidence.response !== 'object') throw new Error(`${row.case_id}: missing official response`);
    if (!Number.isFinite(evidence.response.TotalNetTax) || evidence.response.TotalNetTax !== official) {
      throw new Error(`${row.case_id}: frozen ESTV total differs from CSV`);
    }
    const requestPath = resolve(root, `tests/reference/estv-2026/${row.case_id}-tax.request.json`);
    const request = await verifyRequestEvidence(requestPath, row.request_sha256);
    const childAges = row.child_ages ? row.child_ages.split(';').map(Number) : [];
    const confession = row.church === 'none' ? 4 : row.church === 'reformed' ? 1 : 2;
    const requestInputsMatch = Array.isArray(request.Children)
      && request.Children.length === kids
      && request.Children.every(child => typeof child === 'object' && child !== null && (child as { Age?: unknown }).Age === 10)
      && childAges.length === kids && childAges.every(age => age === 10)
      && request.Age1 === 35 && request.Confession1 === confession && request.Revenue2 === 0
      && (civil === 's' ? request.Relationship === 1 && request.Age2 === 0 && request.Confession2 === 0 : request.Relationship === 2 && request.Age2 === 35 && request.Confession2 === confession)
      && Array.isArray(request.Budget) && request.Budget.length === 0;
    if (!requestInputsMatch || (civil === 'm' && row.partner_age !== '35') || (civil === 's' && row.partner_age !== '')) throw new Error(`${row.case_id}: accepted frozen request inputs changed`);
    const frontend = taxCalculator(profile, municipality, finite(row, 'income'), row.church as Church);
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
    comparability: 'owner_accepted_for_frozen_comparator',
    ownerComparatorAcceptance: acceptance.status,
    ownerComparatorAcceptanceManifest: ACCEPTANCE_PATH,
    ownerComparatorAcceptanceSha256: ACCEPTANCE_SHA256,
    estvEndorsement: false,
    estvCertification: false,
    productionRelease: false,
    numericFailureCount,
    observedMismatchGroups,
    largestComponentDiscrepancies,
    maxAbsoluteError: Math.max(...results.map(result => result.error)),
    numericPassed: numericFailureCount === 0,
    passed: results.length === 29 && numericFailureCount === 0,
    exitCode: results.length === 29 && numericFailureCount === 0 ? 0 : 1,
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
