import { DineroChf, dineroRound, multiplyDineroPercent, dineroAddMany } from '~/lib/utils/dinero';
import { getTaxFactors } from './provider';
import { TaxFactors } from './types';
import { TaxConfession, TaxInput } from '../typesClient';

export const getChurchIncomeFactor = (confession: TaxConfession, factors: TaxFactors) => {
  switch (confession) {
    case 'christ':
      return factors.IncomeRateChrist;
    case 'roman':
      return factors.IncomeRateRoman;
    case 'protestant':
      return factors.IncomeRateProtestant;
    default:
      return 0;
  }
};

// Steuerpendler patch 15: church-tax base differs by canton. The engine applies every church rate to the
// simple tax. ESTV applies JU rates to the cantonal tax (estv-2026-25: 6.4% x 5,809 = 372) and UR rates per
// 1% of taxable income on top of UR's 7.1% flat tariff (estv-2026-29: 0.82% x 48,349 = 396). Express both as
// an equivalent rate on the simple tax so every consumer keeps the single formula base x rate / 100.
export const UR_FLAT_TAX_PERCENT = 7.1;
export const churchIncomeRateOnSimpleTax = (cantonId: number, rate: number, factors: TaxFactors) => {
  if (cantonId === 11) return Math.round(rate * factors.IncomeRateCanton * 1e4) / 1e6;
  if (cantonId === 22) return Math.round((rate / UR_FLAT_TAX_PERCENT) * 1e6) / 1e6;
  return rate;
};

// Steuerpendler patch 26: the BL reformed church tax is a percentage of the cantonal taxable income, not of
// the simple tax (gemeinden-reachable probe: all 70 reachable BL Gemeinden, e.g. Liestal 0.55% x 78,182 = 430).
export const churchOnTaxableIncome = (cantonId: number, confession: TaxConfession | undefined) =>
  cantonId === 5 && confession === 'protestant';

export const getChurchFortuneFactor = (confession: TaxConfession, factors: TaxFactors) => {
  switch (confession) {
    case 'christ':
      return factors.FortuneRateChrist;
    case 'roman':
      return factors.FortuneRateRoman;
    case 'protestant':
      return factors.FortuneRateProtestant;
    default:
      return 0;
  }
};

export const calculateTaxesCantonAndCity = async (
  taxInput: TaxInput,
  taxesIncomeBase: DineroChf,
  taxesIncomeBaseChurch: DineroChf,
  taxesFortuneBase: DineroChf,
  taxableIncomeCanton?: DineroChf
) => {
  const factor = await getTaxFactors(taxInput);

  const taxesIncomeCanton = dineroRound(
    multiplyDineroPercent(taxesIncomeBase, factor.IncomeRateCanton, 5)
  );
  const taxesIncomeCity = dineroRound(
    multiplyDineroPercent(taxesIncomeBase, factor.IncomeRateCity, 5)
  );

  const taxesIncomeChurch = dineroRound(
    dineroAddMany(
      ...taxInput.persons.map((person) =>
        multiplyDineroPercent(
          churchOnTaxableIncome(taxInput.cantonId, person.confession) && taxableIncomeCanton
            ? taxableIncomeCanton
            : taxesIncomeBaseChurch,
          churchIncomeRateOnSimpleTax(taxInput.cantonId, getChurchIncomeFactor(person.confession, factor), factor) /
            taxInput.persons.length,
          2
        )
      )
    )
  );
  const taxesFortuneCanton = dineroRound(
    multiplyDineroPercent(taxesFortuneBase, factor.FortuneRateCanton, 5)
  );
  const taxesFortuneCity = dineroRound(
    multiplyDineroPercent(taxesFortuneBase, factor.FortuneRateCity, 5)
  );
  const taxesFortuneChurch = dineroRound(
    dineroAddMany(
      ...taxInput.persons.map((person) =>
        multiplyDineroPercent(
          taxesFortuneBase,
          getChurchFortuneFactor(person.confession, factor) / taxInput.persons.length,
          5
        )
      )
    )
  );
  return {
    taxesIncomeCanton,
    taxesIncomeCity,
    taxesIncomeChurch,
    taxesFortuneCanton,
    taxesFortuneCity,
    taxesFortuneChurch
  };
};
