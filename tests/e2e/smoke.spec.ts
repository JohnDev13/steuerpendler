import { test, expect } from '@playwright/test';

const estimateDisclaimer = /Unverbindliche Orientierungsschätzung.*ESTV-Rechner.*Alter 35.*Vorsorge.*geschätzte Wohnkosten.*Keine individuelle oder verbindliche Steuerberechnung.*Veranlagung der zuständigen Steuerbehörde/s;

test('comparison and methodology visibly qualify the unfinished estimate', async ({ page }) => {
 await page.goto('./');
 await expect(page.getByRole('heading', {name:'Steuerpendler',exact:true})).toBeVisible();
 await expect(page.getByTestId('release-status')).toContainText('Vorschau');
 await expect(page.locator('main .results > .assumptions').filter({hasText:estimateDisclaimer})).toBeVisible();
 await expect(page.locator('main')).toContainText('offizielle ESTV-Verifikation ausstehend');

 await page.getByRole('link',{name:'Methode',exact:true}).click();
 await expect(page.locator('main').getByText(estimateDisclaimer)).toBeVisible();
 await expect(page.locator('main')).toContainText('offiziell geprüfte Datenfreigabe');
});
