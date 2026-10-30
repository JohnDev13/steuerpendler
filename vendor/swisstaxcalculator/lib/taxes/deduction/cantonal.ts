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
//  step:    D = max(min, base - floor(max(0, B - threshold) / step) x reduction)  (ceil if roundUp; min default 0);
//           D = 0 when B > ceiling (if set)
//  bands:   D = amount of the first band with B <= upTo, else 0
//  rent:    D = max(0, min(max, floor(min(R, cap) - rate x B))), R = ESTV's default rent round(net x 0.25 / 10) x 10
//           (VD housing deduction, code 660; net = net salary income)
export type LateRule =
  | { kind: 'fixed'; id: string; amount: number; addBack: string[] }
  | { kind: 'percent'; id: string; rate: number; max: number; addBack: string[] }
  | { kind: 'linear'; id: string; rate: number; threshold: number; addBack: string[] }
  | { kind: 'step'; id: string; base: number; threshold: number; step: number; reduction: number; roundUp?: boolean; min?: number; ceiling?: number; addBack: string[] }
  | { kind: 'bands'; id: string; bands: [upTo: number, amount: number][]; addBack: string[] }
  | { kind: 'rent'; id: string; cap: number; rate: number; max: number; addBack: string[] };

export interface Household { cantonId: number; married: boolean; kids: number }
export interface CantonalRules { disable: string[]; late: LateRule[] }

const amount = (table: TaxDeductionTable, id: string) => {
  const row = table.itemsById.get(id);
  if (!row) throw new Error(`Cantonal rule needs deduction ${id}`);
  return row.amount;
};

// VD 2026 family deduction (art. 42a(3)), basis = declaration code 650 (X). Vendor patch 28 corrects patch 25: the
// official 2026 ESTV results (tests/reference/estv-2026-probes/vd-vs-grid.jsonl, all 280 Lausanne cases) reduce the
// amount by CHF 100 per completed CHF 2,000 above the first threshold and per CHF 1,000 above the second, the two
// fractions adding up before one floor: n = floor((min(X,T2) - T1) / 2000 + (X - T2) / 1000).
export const vdFamilyDeduction = (familyAmount: number, t1: number, t2: number, x: number): number => {
  const n = Math.floor((Math.max(0, Math.min(x, t2) - t1) + 2 * Math.max(0, x - t2)) / 2000);
  return Math.max(0, familyAmount - 100 * n);
};
// The same step function as bands over whole francs (taxable incomes are whole francs).
const vdFamilyBands = (familyAmount: number, t1: number, t2: number): [number, number][] => {
  const bands: [number, number][] = [];
  let value = familyAmount;
  for (let x = t1; value > 0; x++) {
    const next = vdFamilyDeduction(familyAmount, t1, t2, x);
    if (next !== value) { bands.push([x - 1, value]); value = next; }
  }
  return bands;
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
    case 1: // AG § 42 Abs. 1bis StG: additional social deduction on net income after the social deductions (ESTV canton sheet AG)
      return { disable: [], late: [{ kind: 'bands', id: 'SozZusAbzugTiefeEinkommen_EK', addBack: [],
        bands: [[14999, 12000], [19999, 7500], [24999, 3000], [29999, 2000], [34999, 1000]] }] };
    case 7: { // FR LICD art. 36 (ESTV canton sheet FR, Feb 2026). Child deduction 8,600 (9,600 from the 3rd child),
      // -100 per child for each started CHF 1,000 of net income above 62,700 + 10,100 per further child, min 7,100 / 8,100.
      // Modest income: 4,100 (single without children) / 5,100 up to 20,300 / 24,300, then -200 per started CHF 1,000.
      // Both on net income before social deductions.
      const late: LateRule[] = [];
      if (h.kids > 0) {
        const first = Math.min(h.kids, 2), further = Math.max(0, h.kids - 2);
        late.push({ kind: 'step', id: 'SozKind_EK', base: 8600 * first + 9600 * further, min: 7100 * first + 8100 * further,
          threshold: 62700 + 10100 * (h.kids - 1), step: 1000, reduction: 100 * h.kids, roundUp: true, addBack: [] });
      }
      const dependants = h.married || h.kids > 0;
      late.push({ kind: 'step', id: 'SozBeschEK_EK', base: dependants ? 5100 : 4100, threshold: dependants ? 24300 : 20300,
        step: 1000, reduction: 200, roundUp: true, addBack: ['SozKind_EK'] });
      return { disable: ['SozKinderAnzahl1Oder2_EK', 'SozKinderAnzahlUeber2_EK'], late };
    }
    case 13: // NE: 2,100 single (also single parents) / 3,800 married, -100 / -200 per started CHF 1,000 above 26,000 / 48,000
      // (ESTV Steuermäppchen 'bescheidenes Einkommen' 2025); basis net income after professional expenses only
      return { disable: [], late: [{ kind: 'step', id: 'SozBeschEK_EK', base: h.married ? 3800 : 2100, threshold: h.married ? 48000 : 26000,
        step: 1000, reduction: h.married ? 200 : 100, roundUp: true,
        addBack: ['KKSparLedigMitBVGS3a_EK', 'KKSparzVerhMitBVGS3a_EK', 'KKSparProKind_EK', 'SozKinderAlterUnter4_EK',
          'SozKinderAlterZwischen4und13_EK', 'SozKinderAlterUeber14_EK'] }] };
    case 17: // SH: 3,525 single / 7,050 married or single parent up to net income 16,800 / 25,200, then -150 per started CHF 800
      // (ESTV Steuermäppchen 'bescheidenes Einkommen' 2025; basis before the child deductions)
      return { disable: [], late: [{ kind: 'step', id: 'SozBeschEK_EK', base: h.married || singleParent ? 7050 : 3525,
        threshold: h.married || singleParent ? 25200 : 16800, step: 800, reduction: 150, roundUp: true, addBack: ['SozKind_EK'] }] };
    case 23: { // VD (vendor patches 25, 28): housing (code 660), modest income (695) and family (725), each on code 650
      // (the income after the ordinary deductions, X). Evidence: tests/reference/estv-2026-probes/vd-*.jsonl.
      const max = (id: string) => { const row = table.itemsById.get(id); if (!row) throw new Error(`VD rule needs ${id}`); return row.maximum; };
      const rentCap = (h.married || singleParent ? max('AbzMietePauschalVerheiratet_EK') : max('AbzMietePauschalLedig_EK'))
        + h.kids * max('AbzMietePauschalKind_EK');
      const modest = h.married ? amount(table, 'SozBeschEKverheiratet_EK') + h.kids * amount(table, 'SozBeschEKKind_EK')
        : singleParent ? amount(table, 'SozBeschEKAlleinerzMitK_EK') + (h.kids - 1) * amount(table, 'SozBeschEKKind_EK')
        : amount(table, 'SozBeschEKledig_EK');
      const familyAmount = h.married ? max('SozVerheiratet_EK') + max('SozminderjKinder_EK') * h.kids
        : singleParent ? max('SozKindAlleinerzieher_EK') + max('SozminderjKinder_EK') * h.kids : 0;
      const late: LateRule[] = [
        { kind: 'rent', id: 'VdLogement_EK', cap: rentCap, rate: 0.2, max: max('MaxAbzMiete_EK'), addBack: [] },
        // CHF 100 less per completed CHF 200 above (amount - 100); none above 3 x amount - 700 (single, single parent)
        // or - 1,000 (married). The ceiling is derived from the 2026 ESTV results: every profile's last granted and first
        // refused case brackets it within CHF 220 (tests/reference/estv-2026-probes/vd-modest.jsonl).
        { kind: 'step', id: 'VdModeste_EK', base: modest, threshold: modest - 100, step: 200, reduction: 100,
          ceiling: 3 * modest - (h.married ? 1000 : 700), addBack: ['VdLogement_EK'] },
      ];
      if (familyAmount > 0) late.push({ kind: 'bands', id: 'SozFamAbzug_EK', addBack: ['VdLogement_EK', 'VdModeste_EK'],
        bands: vdFamilyBands(familyAmount, amount(table, 'SozFamAbzugSchwellwertAus1_EK'), amount(table, 'SozFamAbzugSchwellwertAus2_EK')) });
      return { disable: ['SozVerheiratet_EK', 'SozKindAlleinerzieher_EK', 'SozKind_EK', 'SozminderjKinder_EK'], late };
    }
    case 6: case 11: case 22: case 25: // BS, JU, UR, ZG: single parents get the single-parent deduction instead of the single deduction
      return { disable: singleParent ? ['SozLedig_EK'] : [], late: [] };
    default:
      return { disable: [], late: [] };
  }
};

export const estvDefaultRent = (net: number) => Math.round((net * 0.25) / 10) * 10;
export const lateDeduction = (rule: LateRule, basis: number, net = 0): number => {
  if (rule.kind === 'fixed') return rule.amount;
  if (rule.kind === 'rent') return Math.max(0, Math.min(rule.max, Math.floor(Math.min(estvDefaultRent(net), rule.cap) - rule.rate * basis + 1e-9)));
  if (rule.kind === 'bands') return rule.bands.find(([upTo]) => basis <= upTo)?.[1] ?? 0;
  if (rule.kind === 'percent') return Math.min(rule.max, Math.floor(rule.rate * basis + 1e-9));
  if (rule.kind === 'linear') return Math.max(0, Math.floor(rule.rate * (rule.threshold - basis) + 1e-9));
  if (rule.ceiling && basis > rule.ceiling) return 0;
  const steps = Math.max(0, basis - rule.threshold) / rule.step;
  return Math.max(rule.min ?? 0, rule.base - (rule.roundUp ? Math.ceil(steps - 1e-9) : Math.floor(steps + 1e-9)) * rule.reduction);
};

// Applies the late rules in order to the income after the ordinary deductions. `ordinary` holds the canton amounts
// of the ordinary deductions by id. Returns the late deductions by id (taxable income = max(0, income - sum)).
export const applyLateRules = (rules: LateRule[], income: number, ordinary: Map<string, number>, net = 0): [string, number][] => {
  const done: [string, number][] = [];
  let remaining = income;
  for (const rule of rules) {
    const back = rule.addBack.reduce((sum, id) => sum + (ordinary.get(id) ?? 0) + done.filter(([d]) => d === id).reduce((a, [, v]) => a + v, 0), 0);
    const d = lateDeduction(rule, remaining + back, net);
    done.push([rule.id, d]);
    remaining -= d;
  }
  return done;
};

// Steuerpendler patch 24: per-child reductions after the tariff. Evidence: deductions-grid probe and broad sample.
//  simpleReduction: subtracted from the cantonal simple tax before the multipliers, not below 0 (BL 750 per child,
//                   table StErmässigungProKind_EK)
//  cantonReduction: subtracted from the cantonal tax (after the cantonal multiplier) only, not below 0 (NE 200 per child)
//  credit:          subtracted from the cantonal, communal, church and personal tax, not below 0 (ESTV TaxCredit:
//                   SH 320, TG 100 per child)
export interface Reductions { simpleReduction: number; cantonReduction: number; credit: number }
export const cantonalReductions = (h: Household, table: TaxDeductionTable): Reductions => {
  const none = { simpleReduction: 0, cantonReduction: 0, credit: 0 };
  if (h.cantonId === 5) return { ...none, simpleReduction: h.kids * amount(table, 'StErmässigungProKind_EK') };
  if (h.cantonId === 13) return { ...none, cantonReduction: 200 * h.kids };
  if (h.cantonId === 17) return { ...none, credit: 320 * h.kids };
  if (h.cantonId === 20) return { ...none, credit: 100 * h.kids };
  return none;
};
