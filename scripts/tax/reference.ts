import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { calculateTaxesIncomeAndFortune } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { ROOT, SOURCE, loadSources, makeInput, type Civil, type Church } from './build';
import { loadArtifacts, reconstruct, emitReport } from './selftest';

export interface OriginalScenario {
  name: string; canton: string; bfs: number; civil: Civil; kids: number;
  income: number; church: Church; historicalEngine: number;
}

// Only §11.1 is evidence for the historical engine column; it is not ESTV evidence.
export function parseOriginalScenarios(spec: string): OriginalScenario[] {
  const section = spec.match(/^### 11\.1[^\n]*\n([\s\S]*?)(?=^### |^## |$(?![\s\S]))/m)?.[1];
  if (!section) throw new Error('Missing SPEC §11.1');
  const rows = section.split('\n').filter(line => line.startsWith('|'));
  if (rows.length !== 31) throw new Error('Expected header, separator and 29 scenarios in SPEC §11.1');
  const number = (value: string) => {
    if (!/^(?:\d+|\d{1,3}(?:,\d{3})+)$/.test(value)) throw new Error(`Invalid scenario number: ${value}`);
    return Number(value.replaceAll(',', ''));
  };
  return rows.slice(2).map(line => {
    const cells = line.split('|').slice(1, -1).map(x => x.trim());
    if (cells.length !== 9) throw new Error('Invalid scenario columns');
    const [name, canton, bfsText, civilText, kidsText, incomeText, churchText, historicalText] = cells;
    if (!name || !/^[A-Z]{2}$/.test(canton) || !['single', 'married'].includes(civilText) || !['none', 'reformed', 'catholic'].includes(churchText)) throw new Error(`Invalid scenario: ${line}`);
    const bfs = number(bfsText), kids = number(kidsText), income = number(incomeText), historicalEngine = number(historicalText);
    if (bfs <= 0 || kids > 3 || income < 40000 || income > 500000) throw new Error(`Out-of-range scenario: ${line}`);
    return { name, canton, bfs, civil: civilText === 'single' ? 's' : 'm', kids, income, church: churchText as Church, historicalEngine };
  });
}

export async function runReference(directory = `${ROOT}site/data`) {
  const scenarios = parseOriginalScenarios(await readFile(`${ROOT}SPEC.md`, 'utf8'));
  const sources = await loadSources();
  const artifacts = await loadArtifacts(directory);
  const results = [];
  for (const scenario of scenarios) {
    const loc = sources.locations.find(x => x.BfsID === scenario.bfs);
    if (!loc || loc.Canton !== scenario.canton) throw new Error(`Missing/mismatched reference BFS ${scenario.bfs}`);
    const sample = { loc, civil: scenario.civil, kids: scenario.kids, income: scenario.income, church: scenario.church };
    const engine = (await calculateTaxesIncomeAndFortune(makeInput(loc, scenario.civil, scenario.kids, scenario.income, scenario.church))).taxesTotal;
    if (!Number.isFinite(engine)) throw new Error(`Nonfinite reference engine result: ${scenario.bfs}`);
    const reconstructed = reconstruct(artifacts, sample);
    const tableError = Math.abs(reconstructed - engine);
    results.push({ ...scenario, engine, historicalDrift: engine - scenario.historicalEngine, reconstructed, tableError, tablePassed: tableError <= 10, officialEstv: null });
  }
  const passed = results.every(x => x.tablePassed);
  return { source: SOURCE, officialVerification: 'pending', historicalComparison: 'Original SPEC rounded engine values, not official ESTV verification', artifactSha256: artifacts.sha256, tolerance: 10, results, passed, exitCode: passed ? 0 : 1 };
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  (async () => {
    const args = process.argv.slice(2);
    if (args.length % 2 || args.some((x, i) => i % 2 === 0 && !['--data', '--report'].includes(x))) throw new Error('Usage: reference.ts [--data directory] [--report file]');
    const options = Object.fromEntries(Array.from({ length: args.length / 2 }, (_, i) => [args[i * 2], args[i * 2 + 1]]));
    const report = await runReference(options['--data']);
    await emitReport(report, options['--report']);
    console.error(`Reference ${report.passed ? 'PASS' : 'FAIL'}: ${report.results.filter(x => !x.tablePassed).length}/${report.results.length} table failures; ESTV verification pending`);
    process.exitCode = report.exitCode;
  })().catch(error => { console.error(error); process.exitCode = 1; });
}
