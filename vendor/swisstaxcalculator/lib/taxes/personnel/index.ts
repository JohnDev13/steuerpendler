import { readFileSync, existsSync } from 'fs';
import path from 'path';
import { dineroChf, dineroRound, multiplyDineroFactor } from '~/lib/utils/dinero';
import { dataParsedBasePath } from '../constants';
import { getPersonnelTax } from './provider';
import { TaxInput } from '../typesClient';

// Steuerpendler patch 27: personal tax per person by Gemeinde (SO), derived from official ESTV captures by
// scripts/tax/personal.ts. Overrides the cantonal constant for the listed Gemeinden only.
export interface GemeindePersonalTax { amount: number; protestant: number; roman: number }
const personalByYear = new Map<number, Record<string, GemeindePersonalTax>>();
export const getGemeindePersonalTax = (year: number, bfs: number): GemeindePersonalTax | undefined => {
  if (!personalByYear.has(year)) {
    const file = path.resolve(`${dataParsedBasePath}../personal/${year}.json`);
    personalByYear.set(year, existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')).gemeinden : {});
  }
  return personalByYear.get(year)![String(bfs)];
};

export const calculateTaxesPersonnel = (taxInput: TaxInput) => {
  const confession = taxInput.persons[0]?.confession;
  const local = getGemeindePersonalTax(taxInput.year, taxInput.locationId);
  if (local) {
    const church = confession === 'protestant' || confession === 'roman' ? local[confession] : 0;
    return dineroRound(multiplyDineroFactor(dineroChf(local.amount + church), taxInput.persons.length, 0));
  }
  const taxes = getPersonnelTax(taxInput.cantonId);
  // Steuerpendler patch 21: church personal tax (evidence: tests/reference/estv-2026-probes/personal-church.jsonl).
  const church = confession === 'protestant' || confession === 'roman' ? (taxes.church?.[confession] ?? 0) : 0;
  const amount = dineroChf(taxes.amount + church);
  return dineroRound(
    multiplyDineroFactor(amount, taxes.marriedBoth ? taxInput.persons.length : 1, 0)
  );
};
