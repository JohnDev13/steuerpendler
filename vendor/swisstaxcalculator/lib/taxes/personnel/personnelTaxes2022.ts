import { PersonnelTaxItem } from './types';

export const personnelTaxes: Record<number, PersonnelTaxItem> = {
  26: { amount: 24, marriedBoth: true }, // Zürich
  4: { amount: 0, marriedBoth: true }, // Bern
  12: { amount: 50, marriedBoth: false }, // Luzern
  22: { amount: 70, marriedBoth: false, church: { protestant: 30, roman: 30 } }, // Uri — patch 21: 70 per household + 30 church
  19: { amount: 0, marriedBoth: true }, // Schwyz
  15: { amount: 0, marriedBoth: true }, // Obwalden
  14: { amount: 50, marriedBoth: false }, // Nidwalden
  9: { amount: 0, marriedBoth: true }, // Glarus
  25: { amount: 0, marriedBoth: true }, // Zug
  7: { amount: 0, marriedBoth: true }, // Freiburg
  18: { amount: 50, marriedBoth: true, church: { protestant: 10, roman: 20 } }, // Solothurn — patch 21: 50 per person + church
  6: { amount: 0, marriedBoth: true }, // Basel-Stadt
  5: { amount: 0, marriedBoth: true }, // Basel-Landschaft
  17: { amount: 60, marriedBoth: false }, // Schaffhausen
  3: { amount: 0, marriedBoth: true }, // Appenzell Ausserrhoden
  2: { amount: 0, marriedBoth: true }, // Appenzell Innerrhoden
  16: { amount: 0, marriedBoth: true }, // St. Gallen
  10: { amount: 0, marriedBoth: true }, // Graubünden
  1: { amount: 0, marriedBoth: true }, // Aargau
  20: { amount: 0, marriedBoth: true }, // Thurgau
  21: { amount: 20, marriedBoth: true }, // Tessin — patch 21: 20 per person (estv-2026-14: married 40)
  23: { amount: 0, marriedBoth: true }, // Waadt
  24: { amount: 24, marriedBoth: false }, // Wallis
  13: { amount: 0, marriedBoth: false, church: { protestant: 10, roman: 10 } }, // Neuenburg — patch 21: church 10 per household
  8: { amount: 25, marriedBoth: false, church: { protestant: 10, roman: 10 } }, // Genf — patch 21: + church 10 per household
  11: { amount: 0, marriedBoth: true } // Jura
};
