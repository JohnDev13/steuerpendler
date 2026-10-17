import { test, expect } from '@playwright/test';

test('national map zoom controls preserve selection and reset, with bounded keyboard zoom', async ({ page }) => {
 await page.goto('./');
 const map=page.locator('svg[aria-label]').first();
 await expect(map.locator('.municipality')).toHaveCount(2113);
 const initial=await map.getAttribute('viewBox');
 const plus=page.getByRole('button',{name:'Karte vergrössern',exact:true});
 const minus=page.getByRole('button',{name:'Karte verkleinern',exact:true});
 await expect(plus).toBeVisible({timeout:2000});await expect(minus).toBeDisabled();await plus.click();
 await expect(map).not.toHaveAttribute('viewBox',initial!);const zoomed=await map.getAttribute('viewBox');
 await map.locator('.municipality[tabindex="0"]').press('Enter');await expect(map).toHaveAttribute('viewBox',zoomed!);
 await map.focus();for(let i=0;i<20;i++) await page.keyboard.press('+');await expect(plus).toBeDisabled();
 await page.keyboard.press('Home');await expect(map).toHaveAttribute('viewBox',initial!);await expect(minus).toBeDisabled();
});

test('wheel zoom, mouse pan, drag click suppression, reset and mobile width',async({page})=>{
 await page.setViewportSize({width:400,height:800});await page.goto('./');
 const map=page.locator('svg[aria-label]').first();await expect(map.locator('.municipality')).toHaveCount(2113);
 await map.scrollIntoViewIfNeeded();const initial=await map.getAttribute('viewBox');await map.hover();await page.mouse.wheel(0,-500);
 await expect(map).not.toHaveAttribute('viewBox',initial!);const zoomed=await map.getAttribute('viewBox');const box=(await map.boundingBox())!;
 const selected=await map.locator('.selected').getAttribute('data-bfs');
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+45,box.y+box.height/2+25,{steps:5});await page.mouse.up();
 await expect(map).not.toHaveAttribute('viewBox',zoomed!);expect(await map.locator('.selected').getAttribute('data-bfs')).toBe(selected);
 await page.getByRole('button',{name:'Schweiz anzeigen',exact:true}).click();await expect(map).toHaveAttribute('viewBox',initial!);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('drag held stationary before release preserves selection',async({page})=>{
 await page.goto('./');const map=page.locator('svg[aria-label]').first();await expect(map.locator('.municipality')).toHaveCount(2113);
 await page.getByRole('button',{name:'Karte vergrössern',exact:true}).click();await map.scrollIntoViewIfNeeded();
 const zoomed=await map.getAttribute('viewBox'),selected=await map.locator('.selected').getAttribute('data-bfs');
 const start=await map.evaluate(svg=>{const box=svg.getBoundingClientRect();for(let y=box.top+30;y<box.bottom-50;y+=10)for(let x=box.left+30;x<box.right-50;x+=10){const hit=document.elementFromPoint(x,y);if(hit?.matches('.municipality:not(.selected)'))return {x,y};}throw new Error('No unselected municipality hit point');});
 await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(start.x+35,start.y+20,{steps:5});await page.waitForTimeout(650);await page.mouse.up();
 await expect(map).not.toHaveAttribute('viewBox',zoomed!);expect(await map.locator('.selected').getAttribute('data-bfs')).toBe(selected);
});

test('real CDP two-finger pinch and touch pan',async({page,context})=>{
 await page.setViewportSize({width:400,height:800});await page.goto('./');const map=page.locator('svg[aria-label]').first();await expect(map.locator('.municipality')).toHaveCount(2113);await map.scrollIntoViewIfNeeded();
 const cdp=await context.newCDPSession(page);await cdp.send('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:2});
 const box=(await map.boundingBox())!,x=box.x+box.width/2,y=box.y+box.height/2;const initial=await map.getAttribute('viewBox');
 const touch=async(type:'touchStart'|'touchMove'|'touchEnd',points:{x:number;y:number;id:number}[])=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points});
 await touch('touchStart',[{x:x-25,y,id:1},{x:x+25,y,id:2}]);await touch('touchMove',[{x:x-65,y,id:1},{x:x+65,y,id:2}]);await touch('touchEnd',[]);
 await expect(map).not.toHaveAttribute('viewBox',initial!);const pinched=await map.getAttribute('viewBox');
 await touch('touchStart',[{x,y,id:1}]);await touch('touchMove',[{x:x+35,y:y+20,id:1}]);await touch('touchEnd',[]);await expect(map).not.toHaveAttribute('viewBox',pinched!);
});

test('ordinary municipality mouse click still selects after navigation is attached',async({page})=>{
 await page.goto('./');const bern=page.locator('.municipality[data-bfs="351"]');await expect(bern).toBeVisible();await bern.click({force:true});await expect(bern).toHaveClass(/selected/);
});
