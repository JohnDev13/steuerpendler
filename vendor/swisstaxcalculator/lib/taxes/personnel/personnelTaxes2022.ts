import { PersonnelTaxItem } from './types';

export const personnelTaxes: Record<number, PersonnelTaxItem> = {
  26: { amount: 24, marriedBoth: true }, // Zürich
  4: { amount: 0, marriedBoth: true }, // Bern
  12: { amount: 50, marriedBoth: false }, // Luzern
  22: { amount: 100, marriedBoth: true }, // Uri — Steuerpendler patch 16: 2026 CHF 100 (estv-2026-29)
  19: { amount: 0, marriedBoth: true }, // Schwyz
  15: { amount: 0, marriedBoth: true }, // Obwalden
  14: { amount: 50, marriedBoth: false }, // Nidwalden
  9: { amount: 0, marriedBoth: true }, // Glarus
  25: { amount: 0, marriedBoth: true }, // Zug
  7: { amount: 0, marriedBoth: true }, // Freiburg
  18: { amount: 60, marriedBoth: true }, // Solothurn — patch 16: married household CHF 120 (estv-2026-28)
  6: { amount: 0, marriedBoth: true }, // Basel-Stadt
  5: { amount: 0, marriedBoth: true }, // Basel-Landschaft
  17: { amount: 60, marriedBoth: false }, // Schaffhausen
  3: { amount: 0, marriedBoth: true }, // Appenzell Ausserrhoden
  2: { amount: 0, marriedBoth: true }, // Appenzell Innerrhoden
  16: { amount: 0, marriedBoth: true }, // St. Gallen
  10: { amount: 0, marriedBoth: true }, // Graubünden
  1: { amount: 0, marriedBoth: true }, // Aargau
  20: { amount: 0, marriedBoth: true }, // Thurgau
  21: { amount: 40, marriedBoth: false }, // Tessin — patch 16: married household CHF 40 (estv-2026-14)
  23: { amount: 0, marriedBoth: true }, // Waadt
  24: { amount: 24, marriedBoth: false }, // Wallis
  13: { amount: 0, marriedBoth: true }, // Neuenburg
  8: { amount: 25, marriedBoth: false }, // Genf
  11: { amount: 0, marriedBoth: true } // Jura
};
