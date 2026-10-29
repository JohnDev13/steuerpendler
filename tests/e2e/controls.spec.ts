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
 await expect(page.locator('#summary')).toContainText('109 Gemeinden mit Verbindung nach Aarau bis 30 Min. · 3 weitere erreichbare Gemeinden ohne Steuerangabe');
 await expect(page.locator('#result-notice')).toContainText('Der Weg zur Haltestelle ist nicht gemessen');
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

test('long result lists are paged and can be sorted by travel time',async({page})=>{
 await page.goto('./');
 const time=page.getByLabel('Maximale Fahrzeit',{exact:true});
 await time.evaluate((input:HTMLInputElement)=>{input.value='30';input.dispatchEvent(new Event('input',{bubbles:true}));});
 await expect(page.locator('#summary')).toContainText('109 Gemeinden');
 await expect(page.locator('#ranked-list tr')).toHaveCount(25);
 await page.getByRole('button',{name:'Alle 109 Gemeinden anzeigen'}).click();
 await expect(page.locator('#ranked-list tr')).toHaveCount(109);
 await page.getByLabel('Sortieren nach',{exact:true}).selectOption('time');
 const minutes=await page.locator('#ranked-list tr td:nth-child(4)').allTextContents();
 const values=minutes.map(text=>Number.parseInt(text,10));
 expect(values).toEqual([...values].sort((a,b)=>a-b));
});

test('differences use a real sign before the currency and the workplace label names its canton once',async({page})=>{
 await page.goto('./');
 await expect(page.locator('#ranked-list tr').first()).toBeVisible();
 const deltas=await page.locator('#ranked-list tr td:nth-child(7)').allTextContents();
 expect(deltas.every(text=>/^(\+CHF|−CHF|CHF 0|—)/.test(text))).toBe(true);
 await page.getByRole('combobox',{name:'Arbeitsort'}).fill('Altdorf');
 await expect(page.getByRole('option',{name:'Altdorf (UR)',exact:true})).toBeVisible();
});
