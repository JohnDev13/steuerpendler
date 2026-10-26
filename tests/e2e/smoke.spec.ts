import { test, expect } from '@playwright/test';
test('static scaffold shows the project and an honest preview status', async ({ page }) => {
 await page.goto('./');
 await expect(page.getByRole('heading', {name:'Steuerpendler',exact:true})).toBeVisible();
 await expect(page.getByTestId('release-status')).toContainText('Vorschau');
 await expect(page.getByTestId('release-status')).not.toContainText('kein produktiver');
});

test('Aarau overview distinguishes unverified travel from zero reachable Gemeinden', async ({ page }) => {
 await page.goto('./');
 await page.getByRole('combobox', {name:'Arbeitsort'}).fill('Aarau');
 await page.getByRole('option', {name:'Aarau (AG)'}).click();
 await expect(page.locator('#summary')).toContainText('Gemeinden mit beobachteter Verbindung nach Aarau');
 await expect(page.locator('#result-notice')).toContainText('keine vollständige Erreichbarkeitsmenge');
 await expect(page.locator('#result-notice')).toContainText('Nicht aufgeführte Gemeinden bleiben unbekannt');
});
