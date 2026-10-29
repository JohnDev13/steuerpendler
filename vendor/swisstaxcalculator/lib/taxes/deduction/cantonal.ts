// Steuerpendler patch 22: cantonal deductions that depend on the income after the ordinary deductions
// (low-income deductions, income-dependent married/single-parent deductions). Upstream has no concept of them.
// Evidence: tests/reference/estv-2026-probes/deductions-grid.jsonl (ESTV line items TXT_461, TXT_497, TXT_57,
// TXT_61), cantonal law where cited. Each rule is declarative so the browser evaluates it identically.
import type { TaxDeductionTable } from './types';

// Rules apply in order. basis B = income after the ordinary and the earlier late deductions + the listed
// deductions (ordinary or earlier late) added back.
//  fixed:   D = amount
//  percent: D = min(max, floor(rate x B))
//  linear:  D = max(0, floor(rate x (threshold - B)))
//  step:    D = max(0, base - floor(max(0, B - threshold) / step) x reduction)
export type LateRule =
  | { kind: 'fixed'; id: string; amount: number; addBack: string[] }
  | { kind: 'percent'; id: string; rate: number; max: number; addBack: string[] }
  | { kind: 'linear'; id: string; rate: number; threshold: number; addBack: string[] }
  | { kind: 'step'; id: string; base: number; threshold: number; step: number; reduction: number; addBack: string[] };

export interface Household { cantonId: number; married: boolean; kids: number }
export interface CantonalRules { disable: string[]; late: LateRule[] }

const amount = (table: TaxDeductionTable, id: string) => {
  const row = table.itemsById.get(id);
  if (!row) throw new Error(`Cantonal rule needs deduction ${id}`);
  return row.amount;
};

export const cantonalRules = (h: Household, table: TaxDeductionTable): CantonalRules => {
  const singleParent = !h.married && h.kids > 0;
  switch (h.cantonId) {
    case 4: { // BE, StG Art. 40: married 5,300 per spouse (Abs. 1); single parents 1,300 per child (Abs. 3);
      // modest income (Abs. 6/7): 1,100 / 2,200 + 600 per child up to 16,700 / 22,300, then -150 / -300 per CHF 2,000
      const late: LateRule[] = [];
      if (h.married) late.push({ kind: 'fixed', id: 'SozVerheiratetZweit_EK', amount: amount(table, 'SozVerheiratet_EK'), addBack: [] });
      if (singleParent && h.kids > 1) late.push({ kind: 'fixed', id: 'SozKindAlleinerzieherWeitere_EK', amount: (h.kids - 1) * amount(table, 'SozKindAlleinerzieher_EK'), addBack: [] });
      return { disable: [], late: [...late, { kind: 'step', id: 'SozBeschEK_EK',
        base: amount(table, h.married ? 'SozBeschEKverheiratet_EK' : 'SozBeschEKledig_EK') + h.kids * amount(table, 'SozBeschEKKind_EK'),
        threshold: h.married ? 22300 : 16700, step: 2000, reduction: h.married ? 300 : 150, addBack: [] }] };
    }
    case 12: // LU: 14% of (threshold - net income before social deductions); single parents use the married threshold
      return { disable: [], late: [{ kind: 'linear', id: 'SozBeschEK_EK', rate: table.itemsById.get('SozBeschEK_EK')!.percent / 100,
        threshold: amount(table, h.married || singleParent ? 'EntlVerheirateteSchwellwert_EK' : 'EntlAlleinstehendeSchwellwert_EK'),
        addBack: ['SozKind_EK', 'EigenBetr_EK'] }] };
    case 19: // SZ relief deduction: 30% of (35,000 single / 70,000 married + 25,000 per child - net income before social deductions)
      return { disable: [], late: [{ kind: 'linear', id: 'EntlAbzug_EK', rate: 0.3,
        threshold: amount(table, h.married ? 'EntlVerheirateteSchwellwert_EK' : 'EntlAlleinstehendeSchwellwert_EK') + h.kids * amount(table, 'EntlKindSchwellwert_EK'),
        addBack: ['SozLedig_EK', 'SozVerheiratet_EK', 'SozAlleinerzieher_EK', 'SozminderjKinder_EK'] }] };
    case 15: { // OW: married / single-parent deduction 20% of net income (max 10,000); low-income deduction 10% below 50,000 / 75,000 / 100,000
      const addBack = ['SozZusAbzug_EK', 'SozKind_EK'];
      const late: LateRule[] = [];
      if (h.married || singleParent) late.push({ kind: 'percent', id: h.married ? 'SozVerheiratet_EK' : 'SozAlleinerzieher_EK', rate: 0.2, max: 10000, addBack });
      late.push({ kind: 'linear', id: 'SozBeschEK_EK', rate: 0.1, threshold: h.kids > 0 ? 100000 : h.married ? 75000 : 50000,
        addBack: [...addBack, 'SozVerheiratet_EK', 'SozAlleinerzieher_EK'] });
      return { disable: ['SozVerheiratet_EK', 'SozAlleinerzieher_EK'], late };
    }
    default:
      return { disable: [], late: [] };
  }
};

export const lateDeduction = (rule: LateRule, basis: number): number => {
  if (rule.kind === 'fixed') return rule.amount;
  if (rule.kind === 'percent') return Math.min(rule.max, Math.floor(rule.rate * basis + 1e-9));
  if (rule.kind === 'linear') return Math.max(0, Math.floor(rule.rate * (rule.threshold - basis) + 1e-9));
  return Math.max(0, rule.base - Math.floor(Math.max(0, basis - rule.threshold) / rule.step + 1e-9) * rule.reduction);
};

// Applies the late rules in order to the income after the ordinary deductions. `ordinary` holds the canton amounts
// of the ordinary deductions by id. Returns the late deductions by id (taxable income = max(0, income - sum)).
export const applyLateRules = (rules: LateRule[], income: number, ordinary: Map<string, number>): [string, number][] => {
  const done: [string, number][] = [];
  let remaining = income;
  for (const rule of rules) {
    const back = rule.addBack.reduce((sum, id) => sum + (ordinary.get(id) ?? 0) + done.filter(([d]) => d === id).reduce((a, [, v]) => a + v, 0), 0);
    const d = lateDeduction(rule, remaining + back);
    done.push([rule.id, d]);
    remaining -= d;
  }
  return done;
};
