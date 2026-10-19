const RENT_SHARE = 0.25;
const RENT_ROUNDING_CHF = 10;

/**
 * Evidence-based estimated annual rent for the fixed ESTV 2026 profile.
 *
 * This reproduces captured native-budget outputs; it is not source-published
 * backend code and does not represent a person's actual rent.
 */
export function estimateAnnualRent2026FixedProfile(
  netAnnualIncomeP1: number,
  netAnnualIncomeP2: number,
): number {
  if (!Number.isFinite(netAnnualIncomeP1)
      || !Number.isFinite(netAnnualIncomeP2)
      || netAnnualIncomeP1 < 0
      || netAnnualIncomeP2 < 0) {
    throw new RangeError('net annual incomes must be finite and non-negative');
  }

  const combinedNetIncome = netAnnualIncomeP1 + netAnnualIncomeP2;
  if (!Number.isFinite(combinedNetIncome)) {
    throw new RangeError('combined net annual income must be finite');
  }

  return Math.round(
    combinedNetIncome * RENT_SHARE / RENT_ROUNDING_CHF,
  ) * RENT_ROUNDING_CHF;
}
