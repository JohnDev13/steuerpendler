import { calculateTaxesIncomeAndFortune } from './income';
import { calculatePensionCapitalTaxes } from './pensionCapital';
import { TaxInput, TaxResult } from './typesClient';

export const calculateTaxes = async (taxInput: TaxInput): Promise<TaxResult> => {
  switch (taxInput.calculationType) {
    case 'incomeAndWealth':
      return await calculateTaxesIncomeAndFortune(taxInput);
    case 'capital':
      return await calculatePensionCapitalTaxes(taxInput);
  }

  throw new Error('Tax type not supported');
};
