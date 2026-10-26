// Steuerpendler patch 19: apply ESTV-evidenced corrections (data/corrections/<year>.json) at load time.
// Every entry names the value it expects to replace; a mismatch means the vendored data changed and the
// correction must be re-checked, so loading fails instead of silently double-correcting.
import { readFileSync, existsSync } from 'fs';
import path from 'path';
import { dataParsedBasePath } from './constants';
import type { TaxFactors } from './factor/types';
import type { TaxDeductionTable } from './deduction/types';

interface FactorCorrection { bfs?: number; canton?: number; field: keyof TaxFactors; from: number; to: number; evidence: string }
interface DeductionCorrection { canton: number; id: string; field: 'amount' | 'maximum' | 'minimum' | 'percent'; from: number; to: number; evidence: string }
interface Corrections { factors: FactorCorrection[]; deductions: DeductionCorrection[] }

const cache = new Map<number, Corrections>();
const load = (year: number): Corrections => {
  if (!cache.has(year)) {
    const file = path.resolve(`${dataParsedBasePath}../corrections/${year}.json`);
    cache.set(year, existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : { factors: [], deductions: [] });
  }
  return cache.get(year)!;
};

export const correctFactors = (year: number, cantonId: number, factors: TaxFactors[]): TaxFactors[] => {
  const corrections = load(year).factors;
  return factors.map((factor) => {
    let corrected = factor;
    for (const c of corrections) {
      if (c.bfs !== undefined ? c.bfs !== factor.Location.BfsID : c.canton !== cantonId) continue;
      if (corrected[c.field] !== c.from)
        throw new Error(`Stale correction ${c.field} for ${factor.Location.BfsID}: expected ${c.from}, found ${String(corrected[c.field])}`);
      corrected = { ...corrected, [c.field]: c.to };
    }
    return corrected;
  });
};

export const correctDeductions = (year: number, cantonId: number, tables: TaxDeductionTable[]): TaxDeductionTable[] => {
  const corrections = load(year).deductions.filter((c) => c.canton === cantonId);
  if (!corrections.length) return tables;
  return tables.map((table) =>
    table.type !== 'EINKOMMENSSTEUER' || table.target !== 'KANTON'
      ? table
      : {
          ...table,
          items: table.items.map((item) => {
            let corrected = item;
            for (const c of corrections.filter((c) => c.id === item.id)) {
              if (corrected[c.field] !== c.from)
                throw new Error(`Stale correction ${c.id}.${c.field} for canton ${cantonId}: expected ${c.from}, found ${corrected[c.field]}`);
              corrected = { ...corrected, [c.field]: c.to };
            }
            return corrected;
          })
        }
  );
};
