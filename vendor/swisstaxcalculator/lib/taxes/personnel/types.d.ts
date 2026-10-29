export interface PersonnelTaxItem {
  amount: number;
  marriedBoth: boolean;
  // Steuerpendler patch 21: church personal tax, same per-person/household rule as amount.
  church?: { protestant: number; roman: number };
}
