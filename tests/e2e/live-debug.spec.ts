import { test, expect } from '@playwright/test';

test('live Aarau preview includes Staufen transfer by default and excludes it in direct-only mode', async ({ page }) => {
  await page.goto('./');
  const workplace = page.getByRole('combobox', { name: 'Arbeitsort' });
  await workplace.fill('Aarau');
  await page.getByRole('option', { name: 'Aarau (AG)' }).click();
  const time = page.getByLabel('Maximale Fahrzeit', { exact: true });
  await time.evaluate((input: HTMLInputElement) => { input.value = '20'; input.dispatchEvent(new Event('input', { bubbles: true })); });
  const directOnly = page.getByLabel('Nur direkt (optional)', { exact: true });
  await expect(directOnly).not.toBeChecked();
  const row = page.locator('#ranked-list tr[data-bfs="4210"]');
  await expect(row).toBeVisible();
  await expect(row).toContainText('Staufen');
  await expect(row).toContainText('18');
  await expect(page.locator('#result-notice')).toContainText('keine vollständige Erreichbarkeitsmenge');
  await directOnly.check();
  await expect(row).toHaveCount(0);
  await expect(page.locator('#summary')).toContainText('direkter Verbindung');
  await directOnly.uncheck();
  await expect(row).toBeVisible();
  await row.locator('button').click();
  await expect(page.locator('#detail')).toContainText('Staufen');
  await expect(page.locator('#detail')).toContainText('18 Min.');
});
