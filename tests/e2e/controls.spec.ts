import { test, expect } from '@playwright/test';
test('caps the public-transport control at 30 minutes for Aarau while keeping walking separate',async({page})=>{
 await page.goto('./');
 const time=page.getByLabel('Maximale Fahrzeit',{exact:true});
 const walk=page.getByLabel('Maximaler Fussweg',{exact:true});
 await expect(time).toHaveAttribute('max','30');
 await expect(walk).toHaveAttribute('max','15');
 await page.getByRole('combobox',{name:'Arbeitsort'}).fill('Aarau');
 await page.getByRole('option',{name:'Aarau (AG)'}).click();
 await time.evaluate((input:HTMLInputElement)=>{input.value='30';input.dispatchEvent(new Event('input',{bubbles:true}));});
 await expect(page.locator('#summary')).toContainText('106 Gemeinden mit beobachteter Verbindung nach Aarau bis 30 Min.');
 await expect(page.locator('#summary')).toContainText('keine vollständige Erreichbarkeitsmenge');
 await expect(page.locator('#result-notice')).toContainText('Externer Zugang zur Einstiegshaltestelle ist ungemessen');
});

test('offers German labelled controls and remains usable at 400px',async({page})=>{
 await page.setViewportSize({width:400,height:850});
 await page.goto('./');
 await expect(page.getByLabel('Arbeitsort',{exact:true})).toHaveValue('Aarau');
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
