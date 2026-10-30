// Health-insurance premiums per Gemeinde (site/data/kk.json) against the official BAG data.
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import { DEDUCTIBLES, deriveAll, KK_FILE, parseCsv, PROFILES } from './derive';

const ROOT = resolve(import.meta.dirname, '../..');
const shipped = JSON.parse(readFileSync(KK_FILE, 'utf8'));
const value = (year: string, bfs: number, profile: string, deductible: number, stat: 0 | 1) =>
  shipped.years[year].table[shipped.years[year].gemeinden[bfs]][(PROFILES.indexOf(profile as any) * DEDUCTIBLES.length + DEDUCTIBLES.indexOf(deductible as any)) * 2 + stat];

test('the shipped premium file is exactly what the BAG data gives', () => {
  expect(JSON.parse(JSON.stringify(deriveAll()))).toEqual(shipped);
}, 300000);

test('every Gemeinde has premiums; cheaper never exceeds median; higher deductibles cost less', () => {
  const gemeinden = Object.keys(JSON.parse(readFileSync(resolve(ROOT, 'site/data/gemeinden-2026.json'), 'utf8')).gemeinden);
  for (const year of ['2026', '2027']) {
    expect(Object.keys(shipped.years[year].gemeinden).sort()).toEqual([...gemeinden].sort());
    for (const row of shipped.years[year].table as number[][]) {
      for (let p = 0; p < PROFILES.length; p++) for (let d = 0; d < DEDUCTIBLES.length; d++) {
        const i = (p * DEDUCTIBLES.length + d) * 2;
        expect(row[i + 1]).toBeLessThanOrEqual(row[i]);
        expect(row[i + 1]).toBeGreaterThan(0);
        if (d > 0) expect(row[i]).toBeLessThan(row[i - 2]);
      }
    }
  }
});

test('independent recomputation from the raw CSV: Zürich (region 1) single adult, standard model, CHF 300', () => {
  const rows = parseCsv(gunzipSync(readFileSync(resolve(ROOT, 'data/kk/raw/2026-Praemien_CH.csv.gz'))).toString('utf8'))
    .filter(r => r.Kanton === 'ZH' && r.Region === 'PR-REG CH1' && r.Altersklasse === 'AKL-ERW' && r.Unfalleinschluss === 'OHN-UNF'
      && r.Tariftyp === 'TAR-BASE' && r.Franchise === 'FRA-300');
  const byInsurer = new Map<string, number>();
  for (const r of rows) byInsurer.set(r.Versicherer, Math.min(byInsurer.get(r.Versicherer) ?? Infinity, Number(r['Prämie'])));
  const sorted = [...byInsurer.values()].sort((a, b) => a - b), n = sorted.length;
  const median = n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
  expect(n).toBeGreaterThan(20);
  expect(value('2026', 261, 's0', 300, 0)).toBe(Math.round(median * 12));
});
