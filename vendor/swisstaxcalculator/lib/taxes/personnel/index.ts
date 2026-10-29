import { dineroChf, dineroRound, multiplyDineroFactor } from '~/lib/utils/dinero';
import { getPersonnelTax } from './provider';
import { TaxInput } from '../typesClient';

export const calculateTaxesPersonnel = (taxInput: TaxInput) => {
  const taxes = getPersonnelTax(taxInput.cantonId);
  // Steuerpendler patch 21: church personal tax (evidence: tests/reference/estv-2026-probes/personal-church.jsonl).
  const confession = taxInput.persons[0]?.confession;
  const church = confession === 'protestant' || confession === 'roman' ? (taxes.church?.[confession] ?? 0) : 0;
  const amount = dineroChf(taxes.amount + church);
  return dineroRound(
    multiplyDineroFactor(amount, taxes.marriedBoth ? taxInput.persons.length : 1, 0)
  );
};
