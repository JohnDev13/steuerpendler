import { test, expect } from '@playwright/test';
test('static scaffold shows the project and an honest preview status', async ({ page }) => {
 await page.goto('./');
 await expect(page.getByRole('heading', {name:'Steuerpendler',exact:true})).toBeVisible();
 await expect(page.getByTestId('release-status')).toContainText('Vorschau');
 await expect(page.getByTestId('release-status')).not.toContainText('kein produktiver');
});

test('Aarau overview uses the timetable matrix and states its model', async ({ page }) => {
 await page.goto('./');
 await page.getByRole('combobox', {name:'Arbeitsort'}).fill('Aarau');
 await page.getByRole('option', {name:'Aarau (AG)'}).click();
 await expect(page.locator('#summary')).toContainText('Gemeinden mit Verbindung nach Aarau bis 25 Min.');
 await expect(page.locator('#result-notice')).toContainText('Fahrplan vom 27.10.2026');
 await expect(page.locator('#result-notice')).toContainText('nicht gemessen');
});
