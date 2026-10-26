import {test,expect} from '@playwright/test';

test('real touch swipe scrolls options without selecting; completed tap selects',async({browser})=>{
 const context=await browser.newContext({hasTouch:true,viewport:{width:900,height:900}});
 const page=await context.newPage();await page.goto('./');
 const input=page.getByLabel('Arbeitsort',{exact:true});await input.fill('');
 const list=page.locator('#workplace-options');await expect(list).toBeVisible();
 const box=(await list.boundingBox())!;
 await page.evaluate(()=>{(window as any).optionEvents=[];for(const type of ['pointerdown','pointercancel','click'])document.querySelector('#workplace-options')!.addEventListener(type,e=>(window as any).optionEvents.push({type:e.type,pointerType:(e as PointerEvent).pointerType}));});
 const cdp=await context.newCDPSession(page);const x=box.x+box.width/2,y=box.y+Math.min(box.height-15,130);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
 await expect(input).toHaveValue('');await expect(list).toBeVisible();
 for(let i=1;i<=6;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:y-i*15}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 await expect(input).toHaveValue('');await expect(list).toBeVisible();
 await expect.poll(()=>list.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);
 const events=await page.evaluate(()=>(window as any).optionEvents);
 expect(events).toContainEqual({type:'pointerdown',pointerType:'touch'});
 expect(events.some((e:{type:string})=>e.type==='click')).toBe(false);
 await input.fill('Aarau');await page.getByRole('option',{name:'Aarau (AG)',exact:true}).tap();
 await expect(input).toHaveValue('Aarau');await expect(list).toBeHidden();
 await expect(page.locator('#map [data-bfs="4001"]')).toHaveClass(/workplace/);
 expect(await page.evaluate(()=>(window as any).optionEvents.some((e:{type:string})=>e.type==='click'))).toBe(true);
 await context.close();
});

test('refreshing input clears stale active descendant and mouse selection works',async({page})=>{
 await page.goto('./');const input=page.getByLabel('Arbeitsort',{exact:true});
 await input.fill('');await input.press('ArrowDown');
 await expect(input).toHaveAttribute('aria-activedescendant',/.+/);
 await input.fill('Bern');
 expect(await input.getAttribute('aria-activedescendant')).toBeNull();
 await page.getByRole('option',{name:'Bern (BE)',exact:true}).click();
 await expect(input).toHaveValue('Bern');
 await expect(page.locator('#map [data-bfs="351"]')).toHaveClass(/workplace/);
});

test('workplaces are capitals while every municipality stays selectable as a residence',async({page})=>{
 await page.goto('./');
 await expect(page.locator('#map path.municipality')).toHaveCount(2113);
 const workplace=page.getByLabel('Arbeitsort',{exact:true});
 await workplace.fill('Winterthur');
 await expect(page.getByRole('option',{name:'Winterthur (ZH)',exact:true})).toHaveCount(0);
 await workplace.press('Tab');
 await expect(workplace).toHaveValue('Aarau');
 await workplace.fill('Aarau');await workplace.press('Enter');
 await expect(page.locator('#map [data-bfs="4001"]')).toHaveClass(/workplace/);
 await page.locator('#max-time').evaluate((el:HTMLInputElement)=>{el.value='20';el.dispatchEvent(new Event('input',{bubbles:true}));});
 await expect(page.locator('#time-value')).toHaveText('20 Min.');
 // Walking access is unmeasured in the preview, so the walk controls are disabled and explained.
 await expect(page.locator('#max-walk')).toBeDisabled();
 await expect(page.locator('#count-walk')).toBeDisabled();
 await expect(page.locator('#walk-hint')).toBeVisible();
 await expect(page.locator('#count-walk')).not.toBeChecked();
 await page.locator('#map [data-bfs="230"]').focus();await page.keyboard.press('Enter');
 await expect(page.locator('#detail h2')).toContainText('Winterthur');
 await expect(workplace).toHaveValue('Aarau');
 await expect(page.getByTestId('candidate-coverage')).toHaveAttribute('data-residences','2110');
 await expect(page.getByTestId('candidate-coverage')).toHaveAttribute('data-workplaces','19');
});

test('residential search finds non-capitals across canton borders without changing the workplace',async({page})=>{
 await page.goto('./');
 const workplace=page.getByLabel('Arbeitsort',{exact:true});
 await workplace.fill('Aarau');await workplace.press('Enter');
 const residence=page.getByLabel('Wohngemeinde suchen',{exact:true});
 for(const name of ['Lenzburg','Olten','Genève']){
  await residence.fill(name);await residence.press('Enter');
  await expect(page.locator('#detail h2')).toContainText(name);
  await expect(workplace).toHaveValue('Aarau');
  await expect(page.locator('#map [data-bfs="4001"]')).toHaveClass(/workplace/);
 }
});
