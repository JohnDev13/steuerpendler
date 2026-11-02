import { test, expect } from '@playwright/test';

test('current residence is committed separately, retained, recalculated and reset at 400px',async({page})=>{
  await page.setViewportSize({width:400,height:900});
  await page.goto('./');

  const toggle=page.getByRole('button',{name:'aktueller Wohnort abweichend',exact:true});
  await expect(toggle).toBeVisible();
  await toggle.click();
  const current=page.getByRole('combobox',{name:'Aktueller Wohnort',exact:true});
  await expect(current).toBeFocused();
  await expect(page.locator('#difference-heading')).toHaveText('Zum Arbeitsort');

  await current.fill('Genève');
  await expect(page.getByRole('option',{name:'Genève (GE)',exact:true})).toBeVisible();
  await expect(page.locator('#difference-heading')).toHaveText('Zum Arbeitsort');
  await current.press('Enter');
  await expect(page.locator('#difference-heading')).toHaveText('Zum aktuellen Wohnort: Genève');
  const comparison=page.getByRole('region',{name:'Jährlicher Vergleich zum aktuellen Wohnort'});
  await expect(comparison).toContainText('Genève');
  await expect(comparison).toContainText(/Kandidat gegenüber aktuellem Wohnort\s*[+−]?CHF/);
  await expect(comparison).toContainText(/Jährliches Sparpotenzial\s*[+−]?CHF/);
  await expect(comparison).toContainText('nicht offiziell freigegeben');
  const baseline2026=await comparison.locator('p').first().textContent();

  const workplace=page.getByRole('combobox',{name:'Arbeitsort'});
  await workplace.fill('Bern');
  await workplace.press('Enter');
  await expect(current).toHaveValue('Genève');
  await expect(comparison).toContainText('Genève');

  await page.getByLabel('Prämienjahr',{exact:true}).selectOption('2027');
  await expect.poll(async()=>comparison.locator('p').first().textContent()).not.toBe(baseline2026);
  await page.getByLabel('Krankenkasse (Grundversicherung)',{exact:true}).selectOption('none');
  await expect(comparison).toContainText('Jährliches Sparpotenzial');

  await page.getByRole('button',{name:'Aktuellen Wohnort zurücksetzen',exact:true}).click();
  await expect(page.locator('#difference-heading')).toHaveText('Zum Arbeitsort');
  await expect(comparison).toHaveCount(0);
  await expect(current).toHaveValue('Bern');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('equality is zero; a withheld current home never creates fictitious savings',async({page})=>{
  await page.goto('./');
  await page.getByRole('button',{name:'aktueller Wohnort abweichend',exact:true}).click();
  const current=page.getByRole('combobox',{name:'Aktueller Wohnort',exact:true});
  await current.fill('Aarau');
  await page.getByRole('option',{name:'Aarau (AG)',exact:true}).click();
  const comparison=page.getByRole('region',{name:'Jährlicher Vergleich zum aktuellen Wohnort'});
  await expect(comparison).toContainText('Keine Differenz');
  await expect(comparison).toContainText('CHF 0');
  await current.fill('Lausanne');
  await page.getByRole('option',{name:'Lausanne (VD)',exact:true}).click();
  await expect(comparison).toContainText('Steuerdaten für den aktuellen Wohnort werden geprüft');
  await expect(comparison).not.toContainText('Jährliches Sparpotenzial');
  await expect(page.locator('#ranked-list tr').first().locator('td:nth-child(8)')).toHaveText('—');
  await expect(page.locator('#ranked-list tr')).not.toHaveCount(0);
});
