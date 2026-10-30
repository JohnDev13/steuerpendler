import { subtract, add } from 'dinero.js';
import {
  dineroAddMany,
  dineroToNumber,
  dineroRoundMin0,
  dineroChf,
  DineroChf,
  dineroRound
} from '~/lib/utils/dinero';
import {
  calculateGrossNetDetails,
  taxDeductionDefinitions,
  calculateDeductionByDefinition
} from '../deduction';
import { getTaxDecutionTable } from '../deduction/provider';
import { applyLateRules, cantonalReductions, cantonalRules } from '../deduction/cantonal';
import {
  calculateTaxesCantonAndCity,
  getChurchIncomeFactor,
  getChurchFortuneFactor
} from '../factor';
import { getTaxFactors } from '../factor/provider';
import { validateTaxInput } from '../helpers';
import { calculateTaxesPersonnel } from '../personnel';
import {
  getTaxTarifGroup,
  calculateTaxesForTarif,
  calculateProgressionForTarif,
  scaleProgression,
  combineOverallProgression
} from '../tarif';
import { TaxDeductionResultItem } from '../types';
import {
  TaxInput,
  TaxResult,
  TaxDeductionResultItemDisplay,
  TaxProgressionResult
} from '../typesClient';

export const calculateTaxesIncomeAndFortune = async (taxInput: TaxInput): Promise<TaxResult> => {
  validateTaxInput(taxInput);

  const {
    taxableIncomeBund,
    taxableIncomeCanton,
    taxableFortuneCanton,
    grossNetDetails,
    deductionsFortune,
    deductionsIncome
  } = await calculateTaxableAmount(taxInput);

  const { taxesIncomeBund } = await calculateTaxesBund(taxInput, taxableIncomeBund, true);

  const { taxesIncomeBase, taxesFortuneBase } = await calculateTaxesBase(
    taxInput,
    taxableIncomeCanton,
    taxableFortuneCanton
  );

  let {
    taxesIncomeCanton,
    taxesIncomeCity,
    taxesIncomeChurch,
    taxesFortuneCanton,
    taxesFortuneCity,
    taxesFortuneChurch
  } = await calculateTaxesCantonAndCity(
    taxInput,
    taxesIncomeBase,
    taxesIncomeBase,
    taxesFortuneBase,
    taxableIncomeCanton
  );

  const taxesPersonnel = calculateTaxesPersonnel(taxInput);
  // Steuerpendler patch 24: per-child reduction of the cantonal tax only (NE), and the tax credit below.
  const reductions = cantonalReductions(
    { cantonId: taxInput.cantonId, married: ['m', 'rp'].includes(taxInput.relationship), kids: taxInput.children },
    await getTaxDecutionTable(taxInput.cantonId, taxInput.year, 'EINKOMMENSSTEUER')
  );
  if (reductions.cantonReduction)
    taxesIncomeCanton = dineroChf(Math.max(0, dineroToNumber(taxesIncomeCanton) - reductions.cantonReduction));

  let progression: TaxProgressionResult | undefined;
  if (taxInput.includeProgression) {
    const tarifGroup = getTaxTarifGroup(taxInput.relationship, taxInput.children);
    const factors = await getTaxFactors(taxInput);

    // Average church factor across persons (mirrors calculateTaxesCantonAndCity)
    const avgChurchIncome =
      taxInput.persons.reduce(
        (acc, p) => acc + getChurchIncomeFactor(p.confession, factors),
        0
      ) / taxInput.persons.length;
    const avgChurchFortune =
      taxInput.persons.reduce(
        (acc, p) => acc + getChurchFortuneFactor(p.confession, factors),
        0
      ) / taxInput.persons.length;

    // Steuerfuss as a multiplier (factors are expressed as percent of base tarif)
    const cantonIncomeFactor =
      (factors.IncomeRateCanton + factors.IncomeRateCity + avgChurchIncome) / 100;
    const cantonFortuneFactor =
      (factors.FortuneRateCanton + factors.FortuneRateCity + avgChurchFortune) / 100;

    const [bund, cantonIncomeBase, cantonFortuneBase] = await Promise.all([
      calculateProgressionForTarif(
        0,
        taxInput.year,
        tarifGroup,
        'EINKOMMENSSTEUER',
        taxableIncomeBund
      ),
      calculateProgressionForTarif(
        taxInput.cantonId,
        taxInput.year,
        tarifGroup,
        'EINKOMMENSSTEUER',
        taxableIncomeCanton
      ),
      calculateProgressionForTarif(
        taxInput.cantonId,
        taxInput.year,
        tarifGroup,
        'VERMOEGENSSTEUER',
        taxableFortuneCanton
      )
    ]);

    const cantonIncome = scaleProgression(cantonIncomeBase, cantonIncomeFactor);
    const cantonFortune = scaleProgression(cantonFortuneBase, cantonFortuneFactor);
    const overall = combineOverallProgression(
      bund,
      cantonIncome,
      dineroToNumber(taxableIncomeBund),
      dineroToNumber(taxableIncomeCanton)
    );

    progression = { bund, cantonIncome, cantonFortune, overall };
  }

  const { credit } = reductions;
  const nonFederal = dineroToNumber(dineroAddMany(taxesIncomeCanton, taxesIncomeCity, taxesIncomeChurch, taxesFortuneCanton,
    taxesFortuneCity, taxesFortuneChurch, taxesPersonnel));
  const taxCredit = Math.min(credit, Math.max(0, nonFederal));
  const taxesTotal = subtract(dineroAddMany(
    taxesIncomeCanton,
    taxesIncomeCity,
    taxesIncomeChurch,
    taxesFortuneCanton,
    taxesFortuneCity,
    taxesFortuneChurch,
    taxesIncomeBund,
    taxesPersonnel
  ), dineroChf(taxCredit));

  const result: TaxResult = {
    input: taxInput,
    taxesIncomeCanton: dineroToNumber(taxesIncomeCanton),
    taxesIncomeCity: dineroToNumber(taxesIncomeCity),
    taxesIncomeChurch: dineroToNumber(taxesIncomeChurch),
    taxesFortuneCanton: dineroToNumber(taxesFortuneCanton),
    taxesFortuneCity: dineroToNumber(taxesFortuneCity),
    taxesFortuneChurch: dineroToNumber(taxesFortuneChurch),
    taxesIncomeBund: dineroToNumber(taxesIncomeBund),
    taxesPersonnel: dineroToNumber(taxesPersonnel),
    taxesTotal: dineroToNumber(taxesTotal),
    details: {
      netIncomeCanton: grossNetDetails.reduce((acc, item) => acc + item.netIncome, 0),
      netIncomeBund: grossNetDetails.reduce((acc, item) => acc + item.netIncome, 0),
      grossNetDetails,
      deductionsIncome,
      deductionsFortune,
      taxableFortuneCanton: dineroToNumber(taxableFortuneCanton),
      taxableIncomeCanton: dineroToNumber(taxableIncomeCanton),
      taxableIncomeBund: dineroToNumber(taxableIncomeBund)
    },
    progression
  };

  return result;
};

export const calculateTaxableAmount = async (taxInput: TaxInput) => {
  const deductionsIncomeCanton = await getTaxDecutionTable(
    taxInput.cantonId,
    taxInput.year,
    'EINKOMMENSSTEUER'
  );
  const deductionsFortuneCanton = await getTaxDecutionTable(
    taxInput.cantonId,
    taxInput.year,
    'VERMOEGENSSTEUER'
  );
  const deductionsIncomeBund = await getTaxDecutionTable(0, taxInput.year, 'EINKOMMENSSTEUER');

  const grossNetDetails = calculateGrossNetDetails(taxInput);

  const deductionsIncome: TaxDeductionResultItem[] = [];
  const deductionsFortune: TaxDeductionResultItem[] = [];

  if (!taxInput.persons.find((p) => p.incomeType === 'taxable')) {
    taxDeductionDefinitions.forEach((definition) => {
      const deductionResultIncome = calculateDeductionByDefinition(
        definition,
        taxInput,
        'EINKOMMENSSTEUER',
        grossNetDetails,
        deductionsIncomeCanton,
        deductionsIncomeBund
      );
      deductionsIncome.push(...deductionResultIncome);

      const deductionResultFortune = calculateDeductionByDefinition(
        definition,
        taxInput,
        'VERMOEGENSSTEUER',
        grossNetDetails,
        deductionsFortuneCanton
      );

      deductionsFortune.push(...deductionResultFortune);
    });
  }

  const taxableFortuneCanton = dineroRoundMin0(
    subtract(
      dineroChf(taxInput.fortune),
      deductionsFortune.reduce((acc, item) => add(acc, item.amountCanton), dineroChf(0))
    )
  );

  // Steuerpendler patch 22: cantonal rules disable some ordinary deductions and add deductions that depend on the
  // income after the ordinary ones (low-income, income-dependent married/single-parent deductions).
  const rules = cantonalRules(
    { cantonId: taxInput.cantonId, married: ['m', 'rp'].includes(taxInput.relationship), kids: taxInput.children },
    deductionsIncomeCanton
  );
  for (const item of deductionsIncome) if (rules.disable.includes(item.id)) item.amountCanton = dineroChf(0);
  if (rules.late.length) {
    const before = dineroToNumber(dineroRoundMin0(subtract(
      grossNetDetails.reduce((acc, item) => dineroAddMany(acc, dineroChf(item.netIncome)), dineroChf(0)),
      deductionsIncome.reduce((acc, item) => dineroAddMany(acc, item.amountCanton), dineroChf(0))
    )));
    const ordinary = new Map<string, number>();
    for (const item of deductionsIncome) ordinary.set(item.id, (ordinary.get(item.id) ?? 0) + dineroToNumber(item.amountCanton));
    const net = dineroToNumber(grossNetDetails.reduce((acc, item) => dineroAddMany(acc, dineroChf(item.netIncome)), dineroChf(0)));
    for (const [id, value] of applyLateRules(rules.late, before, ordinary, net))
      if (value > 0) deductionsIncome.push({ id, name: id, target: '', amountCanton: dineroChf(value), amountBund: dineroChf(0) });
  }

  const taxableIncomeCanton = dineroRoundMin0(
    subtract(
      grossNetDetails.reduce(
        (acc, item) => dineroAddMany(acc, dineroChf(item.netIncome)),
        dineroChf(0)
      ),
      deductionsIncome.reduce((acc, item) => dineroAddMany(acc, item.amountCanton), dineroChf(0))
    )
  );

  const taxableIncomeBund = dineroRoundMin0(
    subtract(
      grossNetDetails.reduce(
        (acc, item) => dineroAddMany(acc, dineroChf(item.netIncome)),
        dineroChf(0)
      ),
      deductionsIncome.reduce((acc, item) => dineroAddMany(acc, item.amountBund), dineroChf(0))
    )
  );
  return {
    grossNetDetails,
    deductionsIncome: deductionsIncome.map(
      (item): TaxDeductionResultItemDisplay => ({
        id: item.id,
        amountCanton: dineroToNumber(item.amountCanton),
        amountBund: dineroToNumber(item.amountBund),
        name: item.name,
        target: item.target
      })
    ),
    deductionsFortune: deductionsFortune.map(
      (item): TaxDeductionResultItemDisplay => ({
        id: item.id,
        amountCanton: dineroToNumber(item.amountCanton),
        amountBund: dineroToNumber(item.amountBund),
        name: item.name,
        target: item.target
      })
    ),
    taxableFortuneCanton,
    taxableIncomeCanton,
    taxableIncomeBund
  };
};

export const calculateTaxesBase = async (
  taxInput: TaxInput,
  taxableIncomeCanton: DineroChf,
  taxableFortuneCanton: DineroChf
) => {
  const tarifGroup = getTaxTarifGroup(taxInput.relationship, taxInput.children);
  const taxesIncomeBase = await calculateTaxesForTarif(
    taxInput.cantonId,
    taxInput.year,
    tarifGroup,
    'EINKOMMENSSTEUER',
    taxableIncomeCanton,
    { married: ['m', 'rp'].includes(taxInput.relationship), kids: taxInput.children }
  );
  const taxesFortuneBase = await calculateTaxesForTarif(
    taxInput.cantonId,
    taxInput.year,
    tarifGroup,
    'VERMOEGENSSTEUER',
    taxableFortuneCanton
  );

  // Steuerpendler patch 24: per-child reduction of the cantonal simple tax (BL).
  const { simpleReduction } = cantonalReductions(
    { cantonId: taxInput.cantonId, married: ['m', 'rp'].includes(taxInput.relationship), kids: taxInput.children },
    await getTaxDecutionTable(taxInput.cantonId, taxInput.year, 'EINKOMMENSSTEUER')
  );
  const reducedIncomeBase = simpleReduction
    ? dineroChf(Math.max(0, dineroToNumber(taxesIncomeBase) - simpleReduction), 5)
    : taxesIncomeBase;
  return { taxesIncomeBase: reducedIncomeBase, taxesFortuneBase };
};

export const calculateTaxesBund = async (
  taxInput: TaxInput,
  taxableIncomeBund: DineroChf,
  includeChildrenDeduction: boolean
) => {
  const tarifGroup = getTaxTarifGroup(taxInput.relationship, taxInput.children);
  let taxesIncomeBund = dineroRound(
    await calculateTaxesForTarif(
      0,
      taxInput.year,
      tarifGroup,
      'EINKOMMENSSTEUER',
      taxableIncomeBund
    )
  );

  if (includeChildrenDeduction) {
    // 2025/2026 federal tax credit: CHF 263 per child, never a refund.
    taxesIncomeBund = dineroRoundMin0(subtract(taxesIncomeBund, dineroChf(263 * taxInput.children)));
  }
  // Steuerpendler patch 23: DBG Art. 36 Abs. 3, federal tax amounts below CHF 25 are not levied.
  if (dineroToNumber(taxesIncomeBund) < 25) taxesIncomeBund = dineroChf(0);

  return { taxesIncomeBund };
};
