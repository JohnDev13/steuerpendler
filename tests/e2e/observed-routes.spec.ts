import { test, expect } from '@playwright/test';

const workplaces = [
  'Zürich (ZH)', 'Bern (BE)', 'Luzern (LU)', 'Altdorf (UR) (UR)', 'Schwyz (SZ)',
  'Sarnen (OW)', 'Stans (NW)', 'Glarus (GL)', 'Zug (ZG)', 'Solothurn (SO)',
  'Basel (BS)', 'Liestal (BL)', 'Schaffhausen (SH)', 'Herisau (AR)', 'Appenzell (AI)',
  'St. Gallen (SG)', 'Chur (GR)', 'Aarau (AG)', 'Frauenfeld (TG)',
];

test('all 19 workplaces expose source-backed provisional positives with all routes as the default', async ({ page }) => {
  await page.goto('./');
  const workplace = page.getByRole('combobox', { name: 'Arbeitsort' });
  const time = page.getByLabel('Maximale Fahrzeit', { exact: true });
  await time.evaluate((input: HTMLInputElement) => { input.value = '30'; input.dispatchEvent(new Event('input', { bubbles: true })); });
  await expect(page.getByLabel('Nur direkt (optional)', { exact: true })).not.toBeChecked();
  for (const label of workplaces) {
    await workplace.fill(label.replace(/ \([A-Z]{2}\)$/, ''));
    await page.getByRole('option', { name: label, exact: true }).click();
    await expect(page.locator('#summary')).toContainText('beobachteter Verbindung');
    await expect(page.locator('#summary')).toContainText('keine vollständige Erreichbarkeitsmenge');
    await expect(page.locator('#ranked-list tr')).not.toHaveCount(0);
  }
  await expect(page.locator('#ranked-list tr td:nth-child(3)', { hasText: 'VS' })).toHaveCount(0);
});

test('direct-only uses its independent subset and unknown origins never become unreachable', async ({ page }) => {
  await page.goto('./');
  const summary = page.locator('#summary');
  await expect(summary).toContainText('beobachteter Verbindung nach Aarau');
  const allCount = Number((await summary.textContent())?.match(/^(\d+)/)?.[1]);
  const direct = page.getByLabel('Nur direkt (optional)', { exact: true });
  await direct.check();
  await expect(summary).toContainText('unabhängig beobachteter direkter Verbindung');
  const directCount = Number((await summary.textContent())?.match(/^(\d+)/)?.[1]);
  expect(directCount).toBeLessThanOrEqual(allCount);

  const residence = page.getByRole('combobox', { name: 'Wohngemeinde suchen' });
  await residence.fill('Genève');
  await page.getByRole('option', { name: 'Genève (GE)', exact: true }).click();
  await expect(page.locator('#detail')).not.toContainText('Ausser Reichweite');
  await expect(page.locator('#detail')).toContainText(/Erreichbarkeit unbekannt|Rang/);
});

test('all-19 detail uses all-19 provenance, not the old Aarau-only witness copy', async ({ page }) => {
  await page.goto('./');
  await page.locator('#ranked-list tr[data-bfs="4210"] button').click();
  await expect(page.locator('#detail')).toContainText('All-19-Vorschau');
  await expect(page.locator('#detail')).not.toContainText('Aarau-Live-Debug');
});

test('an advertised all-19 asset with mismatched bytes fails closed without Aarau fallback', async ({ page }) => {
  await page.route('**/data/travel/all19-observed-routes-20261027.json?*', async route => {
    const response = await route.fetch();
    await route.fulfill({ response, body: `${await response.text()} ` });
  });
  await page.goto('./');
  await expect(page.locator('#data-status')).toContainText('Datenversion stimmt nicht überein');
  await expect(page.locator('#ranked-list tr')).toHaveCount(0);
});
