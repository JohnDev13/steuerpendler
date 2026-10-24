import {test,expect} from '@playwright/test';
test('public preview draws genuine geography, searches Gemeinden, and withholds unverified tax recommendations',async({page,context})=>{
 const errors:string[]=[],requests:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 page.on('request',r=>requests.push(r.url()));
 await page.goto('./');
 await expect(page.locator('#map path.municipality')).toHaveCount(2113);
 await expect(page.getByTestId('release-status')).toContainText('Vorschau');
 await expect(page.getByLabel('Arbeitsort',{exact:true})).toHaveValue('Aarau');
 await expect(page.locator('#ranked-list tr[data-bfs="4210"]')).toContainText('Staufen');
 await expect(page.locator('#summary')).toContainText('keine vollständige Erreichbarkeitsmenge');
 await page.getByLabel('Arbeitsort',{exact:true}).fill('bern');
 await page.getByLabel('Arbeitsort',{exact:true}).press('Enter');
 await expect(page.locator('#detail h2')).toContainText('Bern');
 await expect(page.locator('#map [data-bfs="351"]')).toHaveClass(/workplace/);
 await page.locator('#map [data-bfs="1711"]').click();
 await expect(page.locator('#detail h2')).toContainText('Zug');
 await expect(page.locator('#detail')).not.toContainText('CHF');
 await expect(page.locator('#detail')).toContainText('Daten werden geprüft');
 await page.getByLabel('Bruttoeinkommen in CHF',{exact:true}).fill('10000');
 await page.getByLabel('Bruttoeinkommen in CHF',{exact:true}).press('Tab');
 await expect(page.locator('#income')).toHaveValue('40000');await expect(page.locator('#clamp-note')).toBeVisible();
 await page.getByLabel('Farbschema wechseln').click();await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
 expect(await context.cookies()).toEqual([]);expect(errors).toEqual([]);
 expect(requests.every(url=>url.startsWith(new URL(page.url()).origin+'/'))).toBe(true);
});
test('built content pages work below the project prefix and absent JSON is a genuine 404',async({page,request})=>{
 await page.goto('./');
 for(const [label,title] of [['Impressum','Impressum'],['Datenschutz','Datenschutz'],['Methode','Methode']]){
  await page.getByRole('link',{name:label,exact:true}).click();
  await expect(page.getByRole('heading',{level:1})).toContainText(title);
  await page.getByRole('link',{name:'Zur Startseite',exact:true}).first().click();
 }
 const missing=await request.get('data/this-file-does-not-exist.json?v=test');expect(missing.status()).toBe(404);
});
test('missing municipality data produces a readable error rather than a blank page',async({page})=>{
 await page.route('**/data/gemeinden-2026.json?*',route=>route.fulfill({status:404,contentType:'text/plain',body:'Not found'}));
 await page.goto('./');await expect(page.locator('#data-status')).toContainText('HTTP 404');
 await expect(page.getByRole('heading',{name:'Steuerpendler',exact:true})).toBeVisible();
});
test('profile controls show the loaded local selection without exposing an unverified tax amount',async({page})=>{
 await page.goto('./');await expect(page.locator('#profile-status')).toContainText('CHF 120');
 await page.getByLabel('Arbeitsort',{exact:true}).fill('Bern');await page.getByLabel('Arbeitsort',{exact:true}).press('Enter');
 await page.getByLabel('Zivilstand',{exact:true}).selectOption('m');await page.getByLabel('Kinder',{exact:true}).selectOption('2');await page.getByLabel('Kirchensteuer',{exact:true}).selectOption('reformed');
 await expect(page.locator('#profile-status')).toContainText('Verheiratet');await expect(page.locator('#profile-status')).toContainText('2 Kinder');await expect(page.locator('#profile-status')).toContainText('Reformiert');
 await expect(page.locator('#detail')).not.toContainText('CHF');await expect(page.locator('#cheapest')).toBeEmpty();
});
test('a stale profile is rejected by its pinned served-byte digest',async({page})=>{
 await page.route('**/data/tax-2026-s-0.json?*',async route=>{const response=await route.fetch();await route.fulfill({response,body:(await response.text())+' '});});
 await page.goto('./');await expect(page.locator('#data-status')).toContainText('Datenversion stimmt nicht überein');
 await expect(page.locator('#ranked-list tr')).toHaveCount(0);
});
