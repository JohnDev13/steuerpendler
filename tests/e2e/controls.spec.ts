import { test, expect } from '@playwright/test';
test('offers German labelled controls and remains usable at 400px',async({page})=>{
 await page.setViewportSize({width:400,height:850});
 await page.goto('/');
 await expect(page.getByLabel('Arbeitsort',{exact:true})).toHaveValue('Zürich');
 await expect(page.getByLabel('Maximale Fahrzeit',{exact:true})).toHaveValue('25');
 await expect(page.getByLabel('Maximaler Fussweg',{exact:true})).toHaveValue('10');
 await expect(page.getByLabel('Bruttoeinkommen in CHF',{exact:true})).toHaveValue('120000');
 await expect(page.getByLabel('Fussweg zur Fahrzeit zählen',{exact:true})).not.toBeChecked();
 await expect(page.getByLabel('Zivilstand',{exact:true})).toHaveValue('s');
 await expect(page.getByLabel('Kinder',{exact:true})).toHaveValue('0');
 await expect(page.getByLabel('Kirchensteuer',{exact:true})).toHaveValue('none');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByLabel('Maximale Fahrzeit',{exact:true}).focus();
 await page.keyboard.press('ArrowRight');
 await expect(page.getByLabel('Maximale Fahrzeit',{exact:true})).toHaveValue('26');
});
