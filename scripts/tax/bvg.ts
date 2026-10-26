const MIN_GROSS_2026_AGE_35 = 40_000;
const MAX_GROSS_2026_AGE_35 = 500_000;
const BVG_UPPER_SALARY_2026 = 90_720;
const BVG_COORDINATION_DEDUCTION_2026 = 26_460;

/** ESTV native-budget BVG default for the fixed 2026, employed, age-35 profile. */
export function calculateBvg2026Age35(grossAnnualIncome: number): number {
  if (!Number.isFinite(grossAnnualIncome)
      || grossAnnualIncome < MIN_GROSS_2026_AGE_35
      || grossAnnualIncome > MAX_GROSS_2026_AGE_35) {
    throw new RangeError('grossAnnualIncome must be finite and within CHF 40,000–500,000');
  }

  const coordinatedContribution = 0.05 * (
    Math.min(grossAnnualIncome, BVG_UPPER_SALARY_2026) - BVG_COORDINATION_DEDUCTION_2026
  );
  const extraMandatoryContribution = 0.035 * Math.max(
    grossAnnualIncome - BVG_UPPER_SALARY_2026,
    0,
  );

  // Values are positive in the supported domain, so floor(x + 0.5) is half-up.
  return Math.floor(coordinatedContribution + extraMandatoryContribution + 0.5);
}
