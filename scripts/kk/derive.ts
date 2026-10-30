// Derives household health-insurance premiums (mandatory basic insurance, OKP) per Gemeinde from the official BAG
// premium data (data/kk/raw/<year>-Praemien_CH.csv.gz) and the EDI premium regions (data/kk/regions-<year>.csv).
//
// Household of the site profile: one employed adult (age 26+, without accident cover: the employer insures accidents),
// for married couples a second adult without own income (with accident cover), children (with accident cover,
// deductible CHF 0). Adults use the selected deductible. Per insurer the whole household is priced with one tariff,
// including the insurer's child discounts. Per Gemeinde and profile:
//   median: median of the insurers' household premium in the standard model (TAR-BASE) offered there;
//   min:    the cheapest household premium over all insurers and models (HMO, family doctor, telmed, ...) offered there.
// Insurers flagged "eingeschränkt tätig" in a canton (Gemeinden not published) and tariffs limited to listed Gemeinden
// (Einzugsgebiete) are only counted where they are available.
// Usage: npx tsx scripts/kk/derive.ts [--write]
import { readFileSync, writeFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export const YEARS = [2026, 2027] as const;
export const DEDUCTIBLES = [300, 500, 1000, 1500, 2000, 2500] as const;
export const PROFILES = ['s0', 's1', 's2', 's3', 'm0', 'm1', 'm2', 'm3'] as const;
export const KK_FILE = resolve(ROOT, 'site/data/kk.json');

export function parseCsv(text: string): Record<string, string>[] {
  const t = text.replace(/^﻿/, '');
  const head = t.slice(0, t.indexOf('\n'));
  const sep = (head.match(/;/g)?.length ?? 0) > (head.match(/,/g)?.length ?? 0) ? ';' : ',';
  const rows: string[][] = [];
  let row: string[] = [], field = '', quoted = false;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (quoted) {
      if (c === '"' && t[i + 1] === '"') { field += '"'; i++; } else if (c === '"') quoted = false; else field += c;
    } else if (c === '"') quoted = true;
    else if (c === sep) { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && t[i + 1] === '\n') i++;
      row.push(field); field = ''; if (row.some(v => v !== '')) rows.push(row); row = [];
    } else field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [header, ...body] = rows;
  return body.map(r => Object.fromEntries(header.map((h, i) => [h.trim(), (r[i] ?? '').trim()])));
}

const readGz = (file: string) => gunzipSync(readFileSync(resolve(ROOT, 'data/kk/raw', file))).toString('utf8');
const readCsv = (file: string) => parseCsv(readFileSync(resolve(ROOT, file), 'utf8'));

// The 2027 files use a new coding (PR_REG_2, AKA_03_ERW, OHN_UNF, BASE, E1, FRA_02_E_0500); normalize both years to
// region number, KIN/JUG/ERW, MIT/OHN, base flag, child code ('' for adults) and the deductible in CHF.
export const regionNumber = (code: string) => Number(code.match(/(\d)\s*$/)![1]);
const ageClass = (code: string) => code.match(/KIN|JUG|ERW/)![0];
const accident = (code: string) => code.match(/MIT|OHN/)![0];
const childCode = (code: string) => (/^K\d$/.test(code) ? code : '');
const deductibleOf = (code: string) => Number(code.match(/(\d+)$/)![1]);

interface Tariff { insurer: string; canton: string; region: number; tarif: string; type: string; base: boolean;
  premium: Map<string, number> } // key `${klasse}|${unfall}|${untergruppe}|${franchise}`

function loadTariffs(year: number): Map<string, Tariff> {
  const tariffs = new Map<string, Tariff>();
  for (const r of parseCsv(readGz(`${year}-Praemien_CH.csv.gz`))) {
    if (r['Geschäftsjahr'] !== String(year)) throw new Error(`Premium year ${r['Geschäftsjahr']} in ${year} file`);
    const region = regionNumber(r.Region), insurer = String(Number(r.Versicherer));
    const key = `${insurer}|${r.Kanton}|${region}|${r.Tarif}`;
    let t = tariffs.get(key);
    if (!t) tariffs.set(key, t = { insurer, canton: r.Kanton, region, tarif: r.Tarif, type: r.Tariftyp, base: /(^|-)BASE$/.test(r.Tariftyp), premium: new Map() });
    t.premium.set(`${ageClass(r.Altersklasse)}|${accident(r.Unfalleinschluss)}|${childCode(r.Altersuntergruppe)}|${deductibleOf(r.Franchise)}`, Number(r['Prämie']));
  }
  return tariffs;
}

// Child premium codes: K1 ordinary; K3 from the 3rd child; K4 all children from 2 children; K5 all children from 3.
function childCodes(t: Tariff, kids: number): string[] | undefined {
  const has = (code: string) => t.premium.has(`KIN|MIT|${code}|0`);
  if (kids === 0) return [];
  if (has('K4') && kids >= 2) return Array(kids).fill('K4');
  if (has('K5') && kids >= 3) return Array(kids).fill('K5');
  if (!has('K1')) return undefined;
  return Array.from({ length: kids }, (_, i) => (i >= 2 && has('K3') ? 'K3' : 'K1'));
}

// Monthly household premium of one tariff, or undefined when the tariff lacks a needed row.
export function householdMonthly(t: Tariff, married: boolean, kids: number, deductible: number): number | undefined {
  const get = (k: string) => t.premium.get(k);
  const earner = get(`ERW|OHN||${deductible}`);
  const spouse = married ? get(`ERW|MIT||${deductible}`) : 0;
  const codes = childCodes(t, kids);
  if (earner === undefined || spouse === undefined || codes === undefined) return undefined;
  let sum = earner + spouse;
  for (const code of codes) { const p = get(`KIN|MIT|${code}|0`); if (p === undefined) return undefined; sum += p; }
  return Math.round(sum * 100) / 100;
}

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b), n = s.length;
  return n === 0 ? undefined : n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
};

export function derive(year: number, gemeinden: Record<string, readonly [string, string, ...unknown[]]>) {
  const tariffs = loadTariffs(year);
  // Gemeinde -> premium region, resolving Gemeinden that merge in or out between the ESTV and BAG lists.
  const regions = new Map(readCsv(`data/kk/regions-${year}.csv`).map(r => [Number(r.bfs), Number(r.region)]));
  const mergers = YEARS.flatMap(y => readCsv(`data/kk/mergers-${y}.csv`)).map(r => [Number(r.bfs), Number(r.into)] as const);
  const divided = new Set(readCsv(`data/kk/regions-${year}.csv`).map(r => r.canton));
  const regionOf = (bfs: number, canton: string): number => {
    if (!divided.has(canton)) return 0;
    if (regions.has(bfs)) return regions.get(bfs)!;
    const candidates = new Set([...mergers.filter(([, into]) => into === bfs).map(([from]) => regions.get(from)),
      ...mergers.filter(([from]) => from === bfs).map(([, into]) => regions.get(into))].filter((v): v is number => v !== undefined));
    if (candidates.size !== 1) throw new Error(`No unique premium region for ${bfs} (${canton}) in ${year}`);
    return [...candidates][0];
  };
  // Availability restrictions.
  const limited = new Map<string, Set<number>>(); // tariff key -> Gemeinden where it is offered
  for (const r of parseCsv(readGz(`${year}-Einzugsgebiete.csv.gz`)))
    if (r['Eingeschränkt'] === 'Y')
      limited.set(`${Number(r.Versicherer)}|${r.Kanton}|${regionNumber(r.Region)}|${r.Tarif}`,
        new Set(r['Gemeinden-BFS'].split(',').map(Number)));
  const activity = readGz(`${year}-Eingeschr.-Taet.gebiete.csv.gz`).replace(/^﻿/, '').split(/\r?\n/);
  const header = activity.find(l => l.startsWith('G_ID'))!.split(';');
  const restricted = new Set<string>();
  for (const line of activity.filter(l => /^\d/.test(l))) {
    const cells = line.split(';');
    cells.forEach((v, i) => { if (v === '1.1') restricted.add(`${Number(cells[0])}|${header[i]}`); });
  }
  const available = (t: Tariff, bfs: number) => !restricted.has(`${Number(t.insurer)}|${t.canton}`)
    && (limited.get(`${Number(t.insurer)}|${t.canton}|${t.region}|${t.tarif}`)?.has(bfs) ?? true);
  const byRegion = new Map<string, Tariff[]>();
  for (const t of tariffs.values()) { const k = `${t.canton}|${t.region}`; byRegion.set(k, [...(byRegion.get(k) ?? []), t]); }

  const values = new Map<string, number[]>(); // signature -> [median, min] x profiles x deductibles (annual CHF)
  const out: Record<string, number> = {};
  const table: number[][] = [];
  for (const [bfs, g] of Object.entries(gemeinden)) {
    const canton = g[1] as string, offer = (byRegion.get(`${canton}|${regionOf(Number(bfs), canton)}`) ?? []).filter(t => available(t, Number(bfs)));
    if (!offer.length) throw new Error(`No premiums for ${bfs} ${g[0]} (${canton}) in ${year}`);
    const row: number[] = [];
    for (const p of PROFILES) for (const d of DEDUCTIBLES) {
      const married = p[0] === 'm', kids = Number(p[1]);
      const perInsurer = new Map<string, number>();
      let min = Infinity;
      for (const t of offer) {
        const m = householdMonthly(t, married, kids, d);
        if (m === undefined) continue;
        min = Math.min(min, m);
        if (t.base) perInsurer.set(t.insurer, Math.min(perInsurer.get(t.insurer) ?? Infinity, m));
      }
      const med = median([...perInsurer.values()]);
      if (med === undefined || !Number.isFinite(min)) throw new Error(`No ${p} ${d} premium for ${bfs} in ${year}`);
      row.push(Math.round(med * 12), Math.round(min * 12));
    }
    const sig = row.join(',');
    if (!values.has(sig)) { values.set(sig, row); table.push(row); }
    out[bfs] = table.indexOf(values.get(sig)!);
  }
  return { table, gemeinden: out };
}

export function deriveAll() {
  const gemeinden = JSON.parse(readFileSync(resolve(ROOT, 'site/data/gemeinden-2026.json'), 'utf8')).gemeinden;
  const manifest = JSON.parse(readFileSync(resolve(ROOT, 'data/kk/raw/manifest.json'), 'utf8'));
  return {
    meta: {
      source: 'Bundesamt für Gesundheit (BAG), Prämien der obligatorischen Krankenpflegeversicherung, opendata.swiss "health-insurance-premiums"; Prämienregionen: Anhang der Verordnung des EDI über die Prämienregionen (SR 832.106)',
      licence: 'opendata.swiss terms_by (attribution required)',
      files: manifest.map((m: any) => ({ file: m.file, sha256: m.sha256 })),
      profiles: PROFILES, deductibles: DEDUCTIBLES,
      layout: 'years[y].table[i] = for each profile (s0..m3) and deductible: [median standard model, cheapest], CHF per year; years[y].gemeinden[bfs] = i',
      assumptions: 'Adults 26+; employed adult without accident cover, other adult and children with; children deductible 0; one insurer and tariff per household; no premium subsidies',
    },
    years: Object.fromEntries(YEARS.map(y => [y, derive(y, gemeinden)])),
  };
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const data = deriveAll();
  for (const y of YEARS) console.log(y, 'distinct premium rows', data.years[y].table.length, 'Gemeinden', Object.keys(data.years[y].gemeinden).length);
  if (process.argv.includes('--write')) { writeFileSync(KK_FILE, JSON.stringify(data) + '\n'); console.log('wrote', KK_FILE); }
}
