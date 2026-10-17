import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import type { TaxLocation } from '../../vendor/swisstaxcalculator/lib/taxes/typesClient';
import { calculateTaxesIncomeAndFortune } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { reconstructPrecision } from './reconstruct';
import type { BudgetDefault, PensionDefault, PreciseCanton } from '../../src/tax';
import { ROOT, SOURCE, INCOMES, loadSources, makeInput, type Gemeinde, type TaxRow, type Sources, type Civil, type Church } from './build';

export interface Profile { meta: { year: number; incomes: typeof INCOMES; pensionDefault?: PensionDefault; budgetDefault?: BudgetDefault }; cantons: Record<string, TaxRow[]>; precision?:Record<string,PreciseCanton> }
export interface Artifacts { profiles: Record<string, Profile>; gemeinden: Record<string, Gemeinde>; sha256: Record<string, string> }

export async function loadArtifacts(directory = `${ROOT}site/data`): Promise<Artifacts> {
  const sha256: Record<string, string> = {};
  const read = async (name: string) => {
    const raw = await readFile(resolve(directory, name));
    sha256[name] = createHash('sha256').update(raw).digest('hex');
    return JSON.parse(raw.toString('utf8'));
  };
  const { gemeinden } = await read('gemeinden-2026.json');
  if (!gemeinden || Object.keys(gemeinden).length !== 2110) throw new Error('Expected 2110 generated Gemeinden');
  for (const [id, row] of Object.entries(gemeinden) as [string, Gemeinde][]) {
    if (!/^\d+$/.test(id) || !Array.isArray(row) || row.length !== 6 || typeof row[0] !== 'string' || typeof row[1] !== 'string' || !row.slice(2).every(Number.isFinite)) throw new Error(`Invalid Gemeinde ${id}`);
  }
  const profiles: Record<string, Profile> = {};
  for (const civil of ['s', 'm']) for (let kids = 0; kids <= 3; kids++) {
    const profile: Profile = await read(`tax-2026-${civil}-${kids}.json`);
    if (profile.meta?.pensionDefault !== undefined && profile.meta.pensionDefault !== 'ESTV2026Age35') throw new Error('Invalid pensionDefault marker');
    if (profile.meta?.budgetDefault !== undefined && profile.meta.budgetDefault !== 'ESTV2026Age35') throw new Error('Invalid budgetDefault marker');
    if (profile.meta?.budgetDefault !== undefined && profile.meta.pensionDefault !== 'ESTV2026Age35') throw new Error('budgetDefault requires matching pensionDefault');
    if (profile.meta?.year !== 2026 || profile.meta.incomes?.from !== 40000 || profile.meta.incomes.step !== 1000 || profile.meta.incomes.count !== 461 || Object.keys(profile.cantons ?? {}).length !== 26) throw new Error('Invalid profile metadata/cantons');
    for (const rows of Object.values(profile.cantons)) if (!Array.isArray(rows) || rows.length !== 461 || rows.some(row => !Array.isArray(row) || row.length !== 3 || !row.every(Number.isFinite))) throw new Error('Invalid profile rows');
    const hasRent30=Object.values(profile.precision??{}).some(p=>[p.bund,p.canton].some(part=>part.deductions.some(op=>op.source==='rent30')));
    if(hasRent30&&profile.meta.budgetDefault!=='ESTV2026Age35')throw new Error('rent30 requires matching budgetDefault');
    profiles[`${civil}-${kids}`] = profile;
  }
  return { profiles, gemeinden, sha256 };
}

// SPEC §7, evaluated from serialized files, without display rounding or engine-component inversion.
export function reconstruct(artifacts: Artifacts, sample: Sample): number {
  const g = artifacts.gemeinden[sample.loc.BfsID];
  if (!g || g[1] !== sample.loc.Canton) throw new Error(`Missing/mismatched BFS ${sample.loc.BfsID}`);
  const rows = artifacts.profiles[`${sample.civil}-${sample.kids}`]?.cantons[g[1]];
  const x = Math.min(460, Math.max(0, (sample.income - 40000) / 1000));
  const i = Math.min(Math.floor(x), 459), t = x - i;
  if (!rows?.[i] || !rows[i + 1]) throw new Error(`Missing profile ${sample.civil}-${sample.kids}/${g[1]}`);
  const row = rows[i].map((v, k) => v + (rows[i + 1][k] - v) * t);
  const rateChurch = sample.church === 'reformed' ? g[4] : sample.church === 'catholic' ? g[5] : 0;
  const precise=artifacts.profiles[`${sample.civil}-${sample.kids}`].precision?.[g[1]];
  if(precise&&t!==0&&t!==1){const meta=artifacts.profiles[`${sample.civil}-${sample.kids}`].meta;return reconstructPrecision(precise,sample.income,[g[2],g[3],rateChurch],meta.pensionDefault,meta.budgetDefault);}
  // Separate monetary rounding at each final component, ties to even.
  const round=(v:number)=>{const f=Math.floor(v);return Math.abs(v-f-.5)<1e-8?(f%2===0?f:f+1):Math.round(v);};
  const r=precise?round:(v:number)=>v;
  const churchRate=precise?Math.round(rateChurch/precise.persons*100)/100*precise.persons:rateChurch;
  const total = row[0] + r(row[1] * g[2] / 100) + r(row[1] * g[3] / 100) + r(row[1] * churchRate / 100) + row[2];
  if (!Number.isFinite(total)) throw new Error('Nonfinite reconstructed total');
  return total;
}

export interface Comparison { bfs: number; canton: string; civil: Civil; kids: number; income: number; church: Church; expected: number; actual: number; error: number; tolerance: number }
export async function runSelftest(directory = `${ROOT}site/data`) {
  const sources = await loadSources();
  const artifacts = await loadArtifacts(directory);
  const samples = sampleCases(sources);
  const evaluate = async (cases: Sample[], offGrid: boolean) => {
    const failures: Comparison[] = [];
    let worst: Comparison | null = null;
    for (const sample of cases) {
      const expected = (await calculateTaxesIncomeAndFortune(makeInput(sample.loc, sample.civil, sample.kids, sample.income, sample.church))).taxesTotal;
      const actual = reconstruct(artifacts, sample);
      if (!Number.isFinite(expected)) throw new Error('Nonfinite engine result');
      const error = Math.abs(actual - expected);
      const tolerance = offGrid ? 10 : Math.max(2, Math.abs(expected) * 0.0001);
      const result: Comparison = { bfs: sample.loc.BfsID, canton: sample.loc.Canton, civil: sample.civil, kids: sample.kids, income: sample.income, church: sample.church, expected, actual, error, tolerance };
      if (!worst || error > worst.error) worst = result;
      if (error > tolerance) failures.push(result);
    }
    return { count: cases.length, failureCount: failures.length, maxAbsoluteError: worst?.error ?? 0, worst, failures };
  };
  const onGrid = await evaluate(samples.onGrid, false), offGrid = await evaluate(samples.offGrid, true);
  const passed = onGrid.failureCount === 0 && offGrid.failureCount === 0;
  return { source: SOURCE, seed: SEED, prng: 'LCG uint32: 1664525*x+1013904223', officialVerification: 'pending', artifactSha256: artifacts.sha256,
    gates: { onGrid: 'max(2, abs(expected) * 0.0001)', offGrid: 10 }, onGrid, offGrid, passed, exitCode: passed ? 0 : 1 };
}

export async function emitReport(report: unknown, path?: string) {
  const text = `${JSON.stringify(report, null, 2)}\n`;
  if (path) { await mkdir(dirname(resolve(path)), { recursive: true }); await writeFile(path, text); }
  console.log(text);
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  (async () => {
    const args = process.argv.slice(2);
    if (args.length % 2 || args.some((x, i) => i % 2 === 0 && !['--data', '--report'].includes(x))) throw new Error('Usage: selftest.ts [--data directory] [--report file]');
    const options = Object.fromEntries(Array.from({ length: args.length / 2 }, (_, i) => [args[i * 2], args[i * 2 + 1]]));
    const report = await runSelftest(options['--data']);
    await emitReport(report, options['--report']);
    console.error(`Selftest ${report.passed ? 'PASS' : 'FAIL'}: on-grid ${report.onGrid.failureCount}/500 failures, max CHF ${report.onGrid.maxAbsoluteError}; off-grid ${report.offGrid.failureCount}/300 failures, max CHF ${report.offGrid.maxAbsoluteError}`);
    process.exitCode = report.exitCode;
  })().catch(error => { console.error(error); process.exitCode = 1; });
}

export interface Sample { loc: TaxLocation; civil: Civil; kids: number; income: number; church: Church }
export const SEED = 0x2026;

export function sampleCases(sources: Sources, seed = SEED) {
  let state = seed >>> 0;
  const random = () => { state = (Math.imul(1664525, state) + 1013904223) >>> 0; return state / 4294967296; };
  const byCanton = new Map<string, TaxLocation[]>();
  for (const loc of sources.locations) byCanton.set(loc.Canton, [...(byCanton.get(loc.Canton) ?? []), loc]);
  const cantons = [...byCanton.keys()].sort();
  const sample = (count: number, offGrid: boolean): Sample[] => Array.from({ length: count }, (_, i) => {
    const candidates = byCanton.get(cantons[i % cantons.length])!;
    return { loc: candidates[Math.floor(random() * candidates.length)], civil: i % 8 < 4 ? 's' : 'm', kids: i % 4,
      income: 40000 + 1000 * Math.floor(random() * (offGrid ? 460 : 461)) + (offGrid ? 1 + Math.floor(random() * 999) : 0),
      church: (['none', 'reformed', 'catholic'] as const)[Math.floor(i / 8) % 3] };
  });
  return { onGrid: sample(500, false), offGrid: sample(300, true) };
}
