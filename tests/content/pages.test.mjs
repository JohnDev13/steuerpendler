import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const filenames = ['impressum', 'datenschutz', 'methode'];
const root = fileURLToPath(new URL('../../', import.meta.url));
const page = name => readFileSync(resolve(root, 'pages', `${name}.html`), 'utf8');
const text = html => html.replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

function assertStatic(html, title) {
  assert.match(html, /^<!doctype html>/i);
  assert.match(html, /<html lang="de-CH">/);
  assert.match(html, new RegExp(`<title>${title} – Entwurf \\| Steuerpendler</title>`));
  assert.match(html, /<meta name="viewport" content="width=device-width, initial-scale=1">/);
  assert.equal((html.match(/<h1\b/g) || []).length, 1);
  assert.match(html, /<main id="inhalt">/);
  assert.match(html, /href="#inhalt"/);
  assert.match(html, /<nav aria-label="Seitennavigation">/);
  assert.match(html, /href="\.\.\/">Zur Startseite/);
  assert.match(html, /Entwurf/);
  assert.match(html, /2026-10-16/);
  assert.match(html, /SPEC\.md/);
  assert.match(html, /v1\.1/);
  assert.doesNotMatch(html, /<(?:script|iframe|frame|frameset|embed|object|img|picture|source|video|audio|svg|math|canvas|link|base|form|input|button)\b/i);
  assert.doesNotMatch(html, /\s(?:src|srcset|poster|data|on\w+)\s*=/i);
  assert.doesNotMatch(html, /(?:url\s*\(|@import|@font-face|http-equiv|javascript:|data:|<\?)/i);
  assert.match(html, /overflow-wrap:\s*anywhere/);
  assert.match(html, /:focus-visible/);
  assert.match(html, /prefers-color-scheme:\s*dark/);
  assert.match(html, /href="https:\/\//);
}

test('Impressum is a static German draft, with named O5 placeholders blocking launch', () => {
  const html = page('impressum');
  assertStatic(html, 'Impressum');
  const copy = text(html);
  for (const required of [/O5/, /nicht zur Veröffentlichung freigegeben/i, /Produktivstart gesperrt/, /\[BETREIBERNAME – AUSSTEHEND\]/, /\[POSTANSCHRIFT – AUSSTEHEND\]/, /\[KONTAKT-E-MAIL – AUSSTEHEND\]/, /rechtliche Prüfung.*ausstehend/i, /keine Rechtsberatung/i]) {
    assert.match(copy, required);
  }
  assert.doesNotMatch(html, /mailto:|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
  assert.doesNotMatch(copy, /\bJohn\b|Musterstrasse|Max Mustermann/);
});

test('Datenschutz distinguishes browser inputs from prospective hosting metadata and pending legal review', () => {
  const html = page('datenschutz');
  assertStatic(html, 'Datenschutz');
  const copy = text(html);
  for (const required of [/Schweizer Datenschutzgesetz.*DSG/, /Einkommen.*ausschliesslich.*Browser/, /nicht an.*Server.*übertragen/, /keine Benutzerkonten/i, /keine Cookies/i, /keine Analytics/i, /O6/, /Cloudflare Pages.*vorgesehen/, /kein Nachweis.*Live-Betrieb/, /IP-Adresse/, /Zeitpunkt/, /Browser/, /Protokoll/, /Speicherdauer.*ausstehend/, /Ausland/, /Auskunft/, /Berichtigung/, /Löschung/, /\[BETREIBERNAME – AUSSTEHEND\]/, /\[KONTAKT-E-MAIL – AUSSTEHEND\]/, /rechtliche Prüfung.*ausstehend/]) {
    assert.match(copy, required);
  }
  assert.doesNotMatch(copy, /keine personenbezogenen Daten|niemals Personendaten|DSG-konform|DSGVO-konform/i);
  assert.doesNotMatch(html, /mailto:/i);
});

test('Datenschutz names the GitHub Pages preview host and its documented IP logging',()=>{
 const copy=text(page('datenschutz'));
 assert.match(copy,/GitHub Pages/);assert.match(copy,/IP-Adresse.*Sicherheitszwecke/);
});

test('Methode documents the implemented formula, pending exact travel metric, real notices and lineage', () => {
  const html = page('methode');
  assertStatic(html, 'Methode');
  const copy = text(html);
  for (const required of [
    /40'000/, /500'000/, /461/, /1'000/, /linear/i,
    /x = clamp\(\(income − 40000\) \/ 1000, 0, 460\)/,
    /i = min\(floor\(x\), 459\); t = x − i/,
    /row = row\[i\] \+ \(row\[i\+1\] − row\[i\]\) × t/,
    /kanton = base × rateCanton \/ 100/,
    /gemeinde = base × rateGemeinde \/ 100/,
    /kirche = base × rateCh \/ 100/,
    /total = bund \+ kanton \+ gemeinde \+ kirche \+ personal/,
    /CHF 10/, /ungerundeten/, /35 Jahre/, /Standardabzüge/, /kein Vermögen/i, /ein Einkommen/i,
    /Haupthaltestelle/, /06:00–09:00/, /2'000/, /1,2 m\/s/, /06:30–08:30/, /Europe\/Zurich/,
    /exakte Minimum/, /ersten Einsteigen/, /Wartezeit vor dem ersten Einsteigen.*ausgeschlossen/,
    /Umsteige-Wartezeiten.*Umsteige-Fusswege.*enthalten/, /auf volle Minuten aufgerundet/,
    /keine Tür-zu-Tür/, /keine echten Reisedatensätze/i, /GTFS/, /r5py\/R5/, /kein Perzentil/,
    /2026/, /Fahrplanjahr.*Metadaten/, /29 ESTV.*ausstehend/, /30 SBB.*ausstehend/,
    /VS.*Daten in Prüfung/, /nicht.*bestätigter.*Fehler/, /Fribourg/,
    /Bundesamt für Statistik \(BFS\), GEOSTAT/, /swiss-maps@4\.7\.0/, /BSD-3-Clause/,
    /non-commercial/, /keine Freigabe.*Geodatenrechte/, /STATPOP/, /ODbL/, /MIT/,
    /43064402b1e52dbbc34dded6a305d7d536737c73/, /17\. Oktober 2026/, /Dokumentationsdrift/,
    /LV95/, /WGS84/, /2391, 5391, 5394/,
  ]) assert.match(copy, required);
  const notice = readFileSync(resolve(root, 'docs/map/swiss-maps-4.7.0-LICENSE.txt'), 'utf8').trim();
  assert.ok(html.includes(notice), 'retain the genuine BSD notice verbatim, not a made-up licence summary');
  for (const url of ['https://swisstaxcalculator.estv.admin.ch', 'https://www.sbb.ch', 'https://github.com/devbrains-com/swisstaxcalculator', 'https://opentransportdata.swiss', 'https://opendata.swiss', 'https://www.openstreetmap.org/copyright', 'https://www.bfs.admin.ch']) {
    assert.ok(html.includes(`href="${url}`), `missing source hyperlink: ${url}`);
  }
});

for (const name of filenames) {
  test(`${name}: every relative hyperlink and fragment exists, with current-page navigation`, () => {
    const html = page(name);
    const currentPath = resolve(root, 'pages', `${name}.html`);
    const anchors = [...html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)];
    assert.ok(anchors.length > 0);
    for (const [, attrs, label] of anchors) {
      assert.ok(text(label).trim(), 'links have descriptive visible text');
      const href = /\bhref="([^"]+)"/.exec(attrs)?.[1];
      assert.ok(href, `missing href on ${label}`);
      if (href.startsWith('https://')) {
        assert.equal(new URL(href).protocol, 'https:');
        continue; // source hyperlinks are not fetched by a content-page load
      }
      assert.doesNotMatch(href, /^(?:\/|[a-z]+:|\\\\)/i, 'local links must be relative');
      const [path, fragment] = href.split('#');
      const targetPath = path === '../' ? resolve(root, 'index.html') : path ? resolve(dirname(currentPath), path) : currentPath;
      assert.ok(existsSync(targetPath), `missing local link target: ${href}`);
      if (fragment) {
        assert.ok(readFileSync(targetPath, 'utf8').includes(`id="${fragment}"`), `missing fragment: ${href}`);
      }
    }
    assert.match(html, new RegExp(`href="${name}\\.html" aria-current="page"`));
    for (const sibling of filenames) assert.ok(html.includes(`href="${sibling}.html"`));
    const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
    assert.equal(new Set(ids).size, ids.length, 'no duplicate IDs');
  });
}
