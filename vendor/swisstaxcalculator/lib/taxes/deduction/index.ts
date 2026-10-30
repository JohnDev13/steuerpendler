import { greaterThan } from 'dinero.js';
import { sortArray } from '~/lib/utils/array';
import {
  dineroChf,
  dineroRound,
  dineroRoundHalfUp,
  dineroRoundDown,
  dineroToNumber,
  dineroSubtractMany,
  dineroAddMany,
  dineroMin,
  dineroMax,
  multiplyDineroPercent,
  multiplyDineroFactor,
  DineroChf
} from '~/lib/utils/dinero';
import { TaxInput, TaxGrossNetDetail } from './../typesClient.d';
import { maxSalaryNbuAlv, taxDeductionsGeneral, taxDeductionsPerson } from './constants';
import {
  TaxDeductionDefinition,
  TaxDeductionDefinitionInput,
  TaxDeductionTableExtended,
  TaxDeductionTableItem
} from './types';
import { TaxDeductionResultItem, TaxType } from '../types';

// Steuerpendler patch 8: ESTV 2026 native-budget defaults, evidenced by the frozen captures
// (KKPRAEMIEN = 4,560 per adult + 1,200 per child, e.g. estv-2026-12: 2 adults + 2 children = 11,520).
const DEFAULT_ADULT_PREMIUM = 4560;
const DEFAULT_CHILD_PREMIUM = 1200;
// SPEC 7.1: children are modelled at age 10 (the ESTV comparison catalogue uses the same age).
export const DEFAULT_CHILD_AGE = 10;

// Inclusive [min, max] child ages for the age-banded cantonal child deductions in the 2026 tables.
const childAgeBands: Record<string, [number, number]> = {
  SozminderjKinder_EK: [0, 17],
  SozKinderAlterUnter4_EK: [0, 3],
  SozKinderAlterUnter5_EK: [0, 4],
  SozKinderAlterUnter7_EK: [0, 6],
  SozKinderAlterUnter14_EK: [0, 13],
  SozKinderAlterUnter15_EK: [0, 14],
  SozKinderAlterZwischen4und13_EK: [4, 13],
  SozKinderAlterZwischen5und15_EK: [5, 15],
  SozKinderAlterZwischen7und16_EK: [7, 16],
  SozKinderAlterZwischen14und17_EK: [14, 17],
  SozKinderAlterUeber6_EK: [7, 99],
  SozKinderAlterUeber14_EK: [15, 99],
  SozKinderAlterUeber15_EK: [16, 99],
  SozKinderAltervon17Jahren_EK: [17, 17],
  SozKinderAlter18oder19_EK: [18, 19],
  SozKinderAlterUeber19_EK: [20, 99]
};
const inBand = (id: string) => DEFAULT_CHILD_AGE >= childAgeBands[id][0] && DEFAULT_CHILD_AGE <= childAgeBands[id][1];

const adultPremiums = (taxInput: TaxInput) =>
  taxInput.persons.reduce((sum, person) => sum + (person.deductions?.insurancePremiums ?? DEFAULT_ADULT_PREMIUM), 0);
// Child premium rows take their full cap when ESTV defaults apply (see patch 18).
const FLAT_MAXIMUM = 1e9;
const childPremium = (taxInput: TaxInput) =>
  taxInput.deductions?.insurancePremiumsKids !== undefined
    ? (taxInput.deductions?.insurancePremiumsKids ?? 0) / taxInput.children
    : DEFAULT_CHILD_PREMIUM;
const perChild = (taxInput: TaxInput) =>
  Array.from(Array(taxInput.children).keys()).map((_, index) => ({ target: `K${index + 1}`, amount: childPremium(taxInput) }));
// Steuerpendler patch 18: ESTV pools all premiums against the summed caps, i.e. the deduction is
// min(adult + child premiums, adult cap + children x child cap). Child rows take their full cap (flat);
// the adult row receives the remaining premiums. Evidence: ZH estv-2026-02 (8,400), GR estv-2026-16 (7,600),
// TI estv-2026-14 (9,120 below a 10,900 cap), VD estv-2026-12 (11,520), AG estv-2026-06 (3,800, no child row).
const CHILD_PREMIUM_ROWS = ['KKSparProKind_EK', 'KKSparProKindMitBVGS3a_EK', 'KKSparProminderjKind_EK', 'KKProMinderjKind_EK', 'KKPrivVersProKind_EK'];
const pooledAdultPremiums = (taxInput: TaxInput, table?: TaxDeductionTableExtended) => {
  const userPremiums = taxInput.persons.some((p) => p.deductions?.insurancePremiums !== undefined);
  const total = adultPremiums(taxInput) + (taxInput.children > 0 ? childPremium(taxInput) * taxInput.children : 0);
  if (userPremiums || !table) return adultPremiums(taxInput);
  const childCap = CHILD_PREMIUM_ROWS.map((id) => table.itemsById.get(id)).find((row) => row !== undefined)?.maximum ?? 0;
  return Math.max(0, total - childCap * taxInput.children);
};
const perChildFlat = (taxInput: TaxInput) =>
  Array.from(Array(taxInput.children).keys()).map((_, index) => ({
    target: `K${index + 1}`,
    amount: taxInput.deductions?.insurancePremiumsKids !== undefined ? childPremium(taxInput) : FLAT_MAXIMUM
  }));

export const taxDeductionDefinitions: TaxDeductionDefinition[] = [
  {
    id: 'HauptErw_EK',
    name: taxDeductionsPerson.otherProfessionalExpenses.label.de,
    rule: () => true,
    input: (_, grossDeductions) =>
      grossDeductions
        .filter((grossDeduction) => grossDeduction.netIncome > 0)
        .map((grossDeduction, index) => ({
          target: `P${index + 1}`,
          amount: grossDeduction.netIncome,
          min: grossDeduction.person.deductions?.otherProfessionalExpenses
        }))
  },
  {
    id: 'Fahrkosten_EK',
    rule: (taxInput) => taxInput.persons.some((p) => (p.deductions?.travelExpenses ?? 0) > 0),
    input: (_, grossDeductions) =>
      grossDeductions
        .filter((grossDeduction) => grossDeduction.netIncome > 0)
        .map((grossDeduction, index) => ({
          target: `P${index + 1}`,
          amount: grossDeduction.person.deductions?.travelExpenses
        }))
  },
  {
    id: 'NebenErw_EK',
    rule: (taxInput) =>
      taxInput.persons.some((p) => (p.deductions?.professionalExpensesSideline ?? 0) > 0),
    input: (_, grossDeductions) =>
      grossDeductions
        .filter((gd) => (gd.person.deductions?.professionalExpensesSideline ?? 0) > 0)
        .map((grossDeduction, index) => ({
          target: `P${index + 1}`,
          amount: 0, // Einkommen Nebenerwerb kann aktuell nicht erfasst werden
          min: grossDeduction.person.deductions?.professionalExpensesSideline
        }))
  },
  {
    id: 'S3a_EK',
    name: taxDeductionsPerson.pillar3a.label.de,
    rule: () => true,
    input: (taxInput, _) =>
      taxInput.persons.map((person, index) => ({
        target: `P${index + 1}`,
        amount: person.deductions?.pillar3a
      }))
  },
  {
    id: 'KKSparLedigMitBVGS3a_EK',
    rule: (taxInput) => taxInput.relationship === 's',
    input: (taxInput, _, table) => [{ amount: pooledAdultPremiums(taxInput, table) }]
  },
  {
    id: 'KKSparzVerhMitBVGS3a_EK',
    rule: (taxInput) => ['m', 'rp'].includes(taxInput.relationship),
    input: (taxInput, _, table) => [{ amount: pooledAdultPremiums(taxInput, table) }]
  },
  {
    id: 'KKSparProKind_EK',
    rule: (taxInput) => taxInput.children > 0,
    input: perChildFlat
  },
  // Steuerpendler patch 9: cantonal insurance-premium deductions published under canton-specific IDs.
  // FR estv-2026-15 (9,120 = 2 x 4,560), GE estv-2026-13 (4,560), VD estv-2026-12 (9,120 + 2 x 1,200),
  // SO estv-2026-28 (2 x 700 per child). Same default premiums as the generic rows above.
  { id: 'KKLedig_EK', rule: (t) => t.relationship === 's', input: (t, _, table) => [{ amount: pooledAdultPremiums(t, table) }] },
  { id: 'KKVerheiratet_EK', rule: (t) => ['m', 'rp'].includes(t.relationship), input: (t, _, table) => [{ amount: pooledAdultPremiums(t, table) }] },
  { id: 'KKProMinderjKind_EK', rule: (t) => t.children > 0, input: perChildFlat },
  // JU publishes married premium caps by pillar 2/3a status: a one-earner couple is "one person without
  // contributions" (deductions grid: 7,590 for every married JU case), a two-earner couple "both with".
  {
    id: 'KKSparzVerhEineOhneBVGS3a_EK',
    rule: (t) => ['m', 'rp'].includes(t.relationship) && t.persons.filter((p) => p.income > 0).length < 2,
    input: (t, _, table) => [{ amount: pooledAdultPremiums(t, table) }]
  },
  {
    id: 'KKSparzVerhBeideMitBVGS3a_EK',
    rule: (t) => ['m', 'rp'].includes(t.relationship) && t.persons.filter((p) => p.income > 0).length >= 2,
    input: (t, _, table) => [{ amount: pooledAdultPremiums(t, table) }]
  },
  { id: 'KKPrivVersLedig_EK', rule: (t) => t.relationship === 's', input: (t, _, table) => [{ amount: pooledAdultPremiums(t, table) }] },
  { id: 'KKPrivVersVerheiratet_EK', rule: (t) => ['m', 'rp'].includes(t.relationship), input: (t, _, table) => [{ amount: pooledAdultPremiums(t, table) }] },
  { id: 'KKPrivVersProKind_EK', rule: (t) => t.children > 0, input: perChildFlat },
  {
    id: 'KKDurchschnittsprämieErw_EK',
    rule: () => true,
    input: (t) => t.persons.map((person, index) => ({ target: `P${index + 1}`, amount: person.deductions?.insurancePremiums ?? DEFAULT_ADULT_PREMIUM }))
  },
  { id: 'KKDurchschnittsprämieMindjhrg_EK', rule: (t) => t.children > 0, input: perChild },
  { id: 'KKSparProKindMitBVGS3a_EK', rule: (t) => t.children > 0, input: perChildFlat },
  { id: 'KKSparProminderjKind_EK', rule: (t) => t.children > 0, input: perChildFlat },
  {
    id: 'SozVerheiratet_EK',
    rule: (taxInput) => ['m', 'rp'].includes(taxInput.relationship),
    input: () => [{}]
  },
  {
    id: 'ZweitVerdiener_EK',
    rule: (taxInput) =>
      ['m', 'rp'].includes(taxInput.relationship) &&
      taxInput.persons.filter((person) => person.income > 0).length >= 2,
    input: (taxInput) =>
      sortArray(taxInput.persons, (p) => p.income)
        .filter((_, index) => index === 0)
        .map((p) => ({ amount: p.income }))
  },
  {
    id: 'SozLedig_EK',
    rule: (taxInput) => taxInput.relationship === 's',
    input: (_, grossDeductions) => [{ amount: grossDeductions[0].netIncome }]
  },
  {
    id: 'SozAlleinerzieher_EK',
    rule: (taxInput) => taxInput.relationship === 's' && taxInput.children > 0,
    input: (_, grossDeductions) => [{ amount: grossDeductions[0].netIncome }]
  },
  {
    id: 'SozKindAlleinerzieher_EK',
    rule: (taxInput) => taxInput.relationship === 's' && taxInput.children > 0,
    input: (_, grossDeductions) => [{ amount: grossDeductions[0].netIncome }]
  },
  {
    id: 'SozKind_EK',
    rule: (taxInput) => taxInput.children > 0,
    input: (taxInput) => [{ multiplier: taxInput.children }]
  },
  // Steuerpendler patch 10: age-banded and count-based cantonal child deductions. Upstream only knew
  // SozKind_EK, so about 13 cantons silently got no child deduction (AG estv-2026-06: 9,300;
  // VS estv-2026-17: 3 x 8,940 + 1,240; TG estv-2026-20: 2 x 7,400; AR estv-2026-22: 2 x 7,400).
  ...Object.keys(childAgeBands).map((id): TaxDeductionDefinition => ({
    id,
    rule: (taxInput) => taxInput.children > 0 && inBand(id),
    input: (taxInput) => [{ multiplier: taxInput.children }]
  })),
  {
    id: 'SozKinderAnzahl1Oder2_EK',
    // JU: from three children on, every child gets the higher amount (deductions grid m3: 3 x 6,400).
    rule: (taxInput) => taxInput.children > 0 && !(taxInput.cantonId === 11 && taxInput.children > 2),
    input: (taxInput) => [{ multiplier: Math.min(taxInput.children, 2) }]
  },
  {
    id: 'SozKinderAnzahlUeber2_EK',
    rule: (taxInput) => taxInput.children > 2,
    input: (taxInput) => [{ multiplier: taxInput.cantonId === 11 ? taxInput.children : taxInput.children - 2 }]
  },
  {
    id: 'SozZusKinderabzugAbAnzahl3_EK',
    rule: (taxInput) => taxInput.children > 2,
    input: (taxInput) => [{ multiplier: taxInput.children - 2 }]
  },
  // Steuerpendler patch 11: BE deduction for single persons with their own household (estv-2026-07: 2,400).
  {
    id: 'SozAlleinEigenemHaushalt_EK',
    rule: (taxInput) => taxInput.relationship === 's',
    input: () => [{}]
  },
  // Steuerpendler patch 12: OW general additional social deduction (estv-2026-27: 10,000). Restricted to OW:
  // the BE row with the same ID is not applied by ESTV to a single person at CHF 90,000 (estv-2026-07).
  {
    id: 'SozZusAbzug_EK',
    rule: (taxInput) => taxInput.cantonId === 15,
    input: () => [{}]
  },
  {
    id: 'MaxAbzMiete_EK',
    rule: (taxInput) =>
      taxInput.cantonId === 25 && (taxInput.deductions?.rentExpenses ?? 0) > 0,
    input: (taxInput) => [{ amount: (taxInput.deductions?.rentExpenses ?? 0) * 0.3 }]
  },
  {
    // Steuerpendler patch 13: per child, not per household (VS estv-2026-17: 3 x 3,130 = 9,390).
    id: 'EigenBetr_EK',
    rule: (taxInput) => taxInput.children > 0,
    input: (taxInput) => [{ multiplier: taxInput.children }]
  },
  {
    id: 'SozKind_VM',
    rule: (taxInput) => taxInput.children > 0,
    input: (taxInput) => [{ multiplier: taxInput.children }]
  },
  {
    id: 'FremdBetr_EK',
    rule: (taxInput) => taxInput.children > 0,
    input: (taxInput) =>
      Array.from(Array(taxInput.children).keys()).map((_, index) => ({
        target: `K${index + 1}`,
        amount: (taxInput.deductions?.childcareCosts ?? 0) / taxInput.children
      }))
  },
  {
    id: 'SozLedigMitOhneKinder_VM',
    rule: (taxInput) => ['s', 'c'].includes(taxInput.relationship),
    input: () => [{}]
  },
  {
    id: 'SozVerheiratet_VM',
    rule: (taxInput) => ['m', 'rp'].includes(taxInput.relationship),
    input: () => [{}]
  },
  {
    id: 'SozLedigOhneKinder_VM',
    rule: (taxInput) => ['s', 'c'].includes(taxInput.relationship) && taxInput.children === 0,
    input: () => [{}]
  },
  {
    id: 'SozAlleinerzieher_VM',
    rule: (taxInput) => ['s', 'c'].includes(taxInput.relationship) && taxInput.children > 0,
    input: () => [{}]
  },
  {
    id: 'Custom_Meal_EK',
    applyAlways: true,
    name: taxDeductionsPerson.mealCosts.label.de,
    rule: (taxInput, taxType) =>
      taxType === 'EINKOMMENSSTEUER' &&
      taxInput.persons.some((p) => p.deductions?.mealCosts !== undefined),
    input: (_, grossDeductions) =>
      grossDeductions
        .filter((grossDeduction) => grossDeduction.netIncome > 0)
        .map((grossDeduction, index) => ({
          target: `P${index + 1}`,
          amount: grossDeduction.person.deductions?.mealCosts
        }))
  },
  {
    id: 'Custom_OtherDeductions_Person_EK',
    applyAlways: true,
    name: taxDeductionsPerson.otherDeductions.label.de,
    rule: (taxInput, taxType) =>
      taxType === 'EINKOMMENSSTEUER' &&
      taxInput.persons.some((p) => p.deductions?.otherDeductions !== undefined),
    input: (taxInput, _) =>
      taxInput.persons.map((person, index) => ({
        target: `P${index + 1}`,
        amount: person.deductions?.otherDeductions
      }))
  },
  {
    id: 'Custom_OtherDeductions_General_EK',
    applyAlways: true,
    name: taxDeductionsGeneral.otherDeductions.label.de,
    rule: (taxInput, taxType) =>
      taxType === 'EINKOMMENSSTEUER' && taxInput.deductions?.otherDeductions !== undefined,
    input: (taxInput, _) => [
      {
        amount: taxInput.deductions?.otherDeductions
      }
    ]
  },
  {
    id: 'Custom_DeptInterest_EK',
    applyAlways: true,
    name: taxDeductionsGeneral.debtInterest.label.de,
    rule: (taxInput, taxType) =>
      taxType === 'EINKOMMENSSTEUER' && taxInput.deductions?.debtInterest !== undefined,
    input: (taxInput, _) => [
      {
        amount: Math.min(taxInput.deductions?.debtInterest ?? 0, 50000) // Abkürzung. Normalerweise müssten noch Zinserträge dazugerechnet werden.
      }
    ]
  },
  {
    id: 'Custom_MaintenanceCostsRealEstate_EK',
    applyAlways: true,
    name: taxDeductionsGeneral.maintenanceCostsRealEstate.label.de,
    rule: (taxInput, taxType) =>
      taxType === 'EINKOMMENSSTEUER' &&
      taxInput.deductions?.maintenanceCostsRealEstate !== undefined,
    input: (taxInput, _) => [
      {
        amount: taxInput.deductions?.maintenanceCostsRealEstate
      }
    ]
  }
];

export const calculateGrossNetDetails = (taxInput: TaxInput): TaxGrossNetDetail[] => {
  return taxInput.persons.map((person) => {
    if (person.incomeType !== 'gross') {
      return {
        netIncome: person.income,
        grossIncome: person.income,
        person,
        ahvIvEo: 0,
        alv: 0,
        nbu: 0,
        pk: 0
      };
    }

    const maxSalaryNbuAlvDinero = dineroChf(maxSalaryNbuAlv);
    const grossIncome = dineroChf(person.income);
    // Steuerpendler patch 30: ESTV rounds the contributions half up.
    const ahvIvEoDeduction = dineroRoundHalfUp(multiplyDineroPercent(grossIncome, 5.3, 1));
    const alvDeduction = dineroRoundHalfUp(
      multiplyDineroPercent(dineroMin(grossIncome, maxSalaryNbuAlvDinero), 1.1, 1)
    );
    const nbuDeduction = dineroRoundHalfUp(
      multiplyDineroPercent(dineroMin(grossIncome, maxSalaryNbuAlvDinero), 0.4, 1)
    );
    const pkDeduction = dineroChf(person.pkDeduction ?? 0);

    const deducion: TaxGrossNetDetail = {
      person,
      grossIncome: person.income,
      ahvIvEo: dineroToNumber(ahvIvEoDeduction),
      alv: dineroToNumber(alvDeduction),
      nbu: dineroToNumber(nbuDeduction),
      pk: dineroToNumber(pkDeduction),
      netIncome: dineroToNumber(
        dineroSubtractMany(grossIncome, ahvIvEoDeduction, alvDeduction, nbuDeduction, pkDeduction)
      )
    };

    return deducion;
  });
};

export const calculateDeductionByDefinition = (
  deductionDefinition: TaxDeductionDefinition,
  taxInput: TaxInput,
  taxType: TaxType,
  grossDeductions: TaxGrossNetDetail[],
  deductionTableCanton?: TaxDeductionTableExtended,
  deductionTableBund?: TaxDeductionTableExtended
): TaxDeductionResultItem[] => {
  if (!deductionDefinition.rule(taxInput, taxType)) return [];

  const deductionCanton = deductionTableCanton?.itemsById.get(deductionDefinition.id);
  const deductionBund = deductionTableBund?.itemsById.get(deductionDefinition.id);

  const deductions: TaxDeductionResultItem[] = [];

  if (deductionCanton || deductionBund || deductionDefinition.applyAlways) {
    // Inputs may depend on the table's caps (patch 18), so evaluate them per table.
    const inputsBund = deductionDefinition.input(taxInput, grossDeductions, deductionTableBund);
    deductionDefinition.input(taxInput, grossDeductions, deductionTableCanton).forEach((deductionInput, inputIndex) => {
      const deductionInputBund = inputsBund[inputIndex] ?? deductionInput;
      const amountOverride = deductionDefinition.applyAlways ? deductionInput.amount ?? 0 : 0;

      const amountCanton = deductionCanton
        ? calculateDeductionByFormat(deductionCanton, deductionInput.amount)
        : dineroChf(amountOverride);
      const amountBund = deductionBund
        ? calculateDeductionByFormat(deductionBund, deductionInputBund.amount)
        : dineroChf(amountOverride);

      const deduction: TaxDeductionResultItem = {
        id: deductionDefinition.id,
        name:
          deductionDefinition.name ??
          deductionCanton?.name.de ??
          deductionBund?.name.de ??
          'Unbekannter Abzug',
        target: deductionInput.target ?? '',
        amountCanton: getAmount(amountCanton, deductionInput),
        amountBund: getAmount(amountBund, deductionInputBund)
      };

      if (
        greaterThan(deduction.amountCanton, dineroChf(0)) ||
        greaterThan(deduction.amountBund, dineroChf(0))
      ) {
        // console.log(deduction);
        deductions.push(deduction);
      }
    });
  }

  return deductions;
};

const getAmount = (amount: DineroChf, deductionInput: TaxDeductionDefinitionInput) => {
  if (deductionInput.multiplier !== undefined) {
    amount = multiplyDineroFactor(amount, deductionInput.multiplier, 1);
  }

  if (deductionInput.min !== undefined) {
    amount = dineroMax(amount, dineroChf(deductionInput.min));
  }

  return amount;
};

export const calculateDeductionByFormat = (deduction: TaxDeductionTableItem, amount = 0) => {
  const amountDinero = dineroChf(amount);
  switch (deduction.format) {
    case 'MAXIMUM':
      return dineroMin(amountDinero, dineroChf(deduction.maximum));
    case 'PERCENT':
      return dineroRoundDown(multiplyDineroPercent(amountDinero, deduction.percent, 5));
    case 'PERCENT,MAXIMUM':
      return dineroMin(
        dineroRoundDown(multiplyDineroPercent(amountDinero, deduction.percent, 5)),
        dineroChf(deduction.maximum)
      );
    case 'PERCENT,MINIMUM,MAXIMUM':
      return dineroMin(
        dineroMax(
          dineroRoundDown(multiplyDineroPercent(amountDinero, deduction.percent, 5)),
          dineroChf(deduction.minimum)
        ),
        dineroChf(deduction.maximum)
      );
    case 'STANDARDIZED':
      return dineroChf(deduction.amount);
    // Steuerpendler patch 14: flat amount plus a percentage, capped (SG estv-2026-11, AI estv-2026-21,
    // AR estv-2026-22: e.g. min(700 + 10% x net, 2,400)). Upstream fell through to zero.
    case 'STANDARDIZED,PERCENT,MAXIMUM':
      return dineroMin(
        dineroAddMany(dineroChf(deduction.amount), dineroRoundDown(multiplyDineroPercent(amountDinero, deduction.percent, 5))),
        dineroChf(deduction.maximum)
      );
    default:
      return dineroChf(0);
  }
};
