import { test, expect } from '@playwright/test';
test('static scaffold shows the project and an honest preview status', async ({ page }) => {
 await page.goto('/');
 await expect(page.getByRole('heading', {name:'Steuerpendler',exact:true})).toBeVisible();
 await expect(page.getByTestId('release-status')).toContainText('Vorschau');
});
