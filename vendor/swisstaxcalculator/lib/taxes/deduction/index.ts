import { greaterThan } from 'dinero.js';
import { sortArray } from '~/lib/utils/array';
import {
  dineroChf,
  dineroRound,
  dineroToNumber,
  dineroSubtractMany,
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
    input: (taxInput) => [
      {
        amount: taxInput.persons[0].deductions?.insurancePremiums ?? 4560
      }
    ]
  },
  {
    id: 'KKSparzVerhMitBVGS3a_EK',
    rule: (taxInput) => ['m', 'rp'].includes(taxInput.relationship),
    input: (taxInput) => [
      {
        amount: taxInput.persons.reduce(
          (sum, person) => sum + (person.deductions?.insurancePremiums ?? 4560),
          0
        )
      }
    ]
  },
  {
    id: 'KKSparProKind_EK',
    rule: (taxInput) => taxInput.children > 0,
    input: (taxInput) =>
      Array.from(Array(taxInput.children).keys()).map((_, index) => ({
        target: `K${index + 1}`,
        amount:
          taxInput.deductions?.insurancePremiumsKids !== undefined
            ? (taxInput.deductions?.insurancePremiumsKids ?? 0) / taxInput.children
            : 1400
      }))
  },
  {
    id: 'SozVerheiratet_EK',
    rule: (taxInput) => ['m', 'rp'].includes(taxInput.relationship),
    input: () => [{}]
  },
  {
    id: 'ZweitVerdiener_EK',
    rule: (taxInput) => ['m', 'rp'].includes(taxInput.relationship),
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
  {
    id: 'EigenBetr_EK',
    rule: (taxInput) => taxInput.children > 0,
    input: () => [{}]
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
    const ahvIvEoDeduction = dineroRound(multiplyDineroPercent(grossIncome, 5.3, 1));
    const alvDeduction = dineroRound(
      multiplyDineroPercent(dineroMin(grossIncome, maxSalaryNbuAlvDinero), 1.1, 1)
    );
    const nbuDeduction = dineroRound(
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
    deductionDefinition.input(taxInput, grossDeductions).forEach((deductionInput) => {
      const amountOverride = deductionDefinition.applyAlways ? deductionInput.amount ?? 0 : 0;

      const amountCanton = deductionCanton
        ? calculateDeductionByFormat(deductionCanton, deductionInput.amount)
        : dineroChf(amountOverride);
      const amountBund = deductionBund
        ? calculateDeductionByFormat(deductionBund, deductionInput.amount)
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
        amountBund: getAmount(amountBund, deductionInput)
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
      return dineroRound(multiplyDineroPercent(amountDinero, deduction.percent, 5));
    case 'PERCENT,MINIMUM,MAXIMUM':
      return dineroMin(
        dineroMax(
          dineroRound(multiplyDineroPercent(amountDinero, deduction.percent, 5)),
          dineroChf(deduction.minimum)
        ),
        dineroChf(deduction.maximum)
      );
    case 'STANDARDIZED':
      return dineroChf(deduction.amount);
    default:
      return dineroChf(0);
  }
};
