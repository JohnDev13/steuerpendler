import { TaxDeductionPersonFieldConfigs, TaxDeductionGeneralFieldConfigs } from '../typesClient';

export const maxSalaryNbuAlv = 148200;

export const taxDeductionsPerson: TaxDeductionPersonFieldConfigs = {
  insurancePremiums: {
    label: { de: 'Versicherungsprämien und Zinsen von Sparkapitalien' },
    hint: {
      de: "Versicherungsprämien und Zinsen von Sparkapitalien, abzüglich individuelle Prämienverbilligung. Annahme: 4'560 CHF pro Erwachsenen (380 CHF monatlich)"
    },
    default: 4560
  },
  pillar3a: {
    label: { de: 'Beiträge an Säule 3a' }
  },
  mealCosts: {
    label: { de: 'Verpflegungskosten' },
    default: 1600,
    suggestion: 3200,
    dependsOnWorkloadFactor: true
  },
  travelExpenses: {
    label: { de: 'Fahrkosten' },
    default: 1000
  },
  otherProfessionalExpenses: {
    label: { de: 'Berufsauslagen' },
    defaultFlatRate: true
  },
  professionalExpensesSideline: {
    label: { de: 'Berufsauslagen Nebenerwerb' }
  },
  otherDeductions: {
    label: { de: 'Übrige Abzüge' }
  }
};

export const taxDeductionsGeneral: TaxDeductionGeneralFieldConfigs = {
  insurancePremiumsKids: {
    label: { de: 'Versicherungsprämien Kinder' },
    withChildrenOnly: true,
    defaultPerChild: 1200
  },
  childcareCosts: {
    label: { de: 'Kinder Drittbetreuungskosten' },
    withChildrenOnly: true
  },
  // rentExpenses: {
  //   label: { de: 'Mietausgaben' },
  //   hint: {
  //     de: 'Nur relevant für die Kantone ZG und VD.'
  //   }
  // },
  debtInterest: {
    label: { de: 'Schuldzinsen' }
  },
  maintenanceCostsRealEstate: {
    label: { de: 'Unterhaltskosten für Liegenschaften' }
  },
  otherDeductions: {
    label: { de: 'Übrige Abzüge' }
  }
};
