/** Difference to the workplace: "+CHF 70", "−CHF 660", "CHF 0" (true minus sign, sign before the currency). */
export function formatDelta(delta: number): string {
 const text = formatCHF(Math.abs(delta));
 return text === 'CHF 0' ? text : `${delta > 0 ? '+' : '−'}${text}`;
}
export function formatCHF(amount: number): string {
 const rounded = Math.round(Math.abs(amount) / 10) * 10;
 const sign = amount < 0 && rounded !== 0 ? '-' : '';
 return `CHF ${sign}${String(rounded).replace(/\B(?=(\d{3})+(?!\d))/g, "'")}`;
}
