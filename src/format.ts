export function formatCHF(amount: number): string {
 const rounded = Math.round(Math.abs(amount) / 10) * 10;
 const sign = amount < 0 && rounded !== 0 ? '-' : '';
 return `CHF ${sign}${String(rounded).replace(/\B(?=(\d{3})+(?!\d))/g, "'")}`;
}
