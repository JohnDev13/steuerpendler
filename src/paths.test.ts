import {expect,it} from 'vitest';
import {sitePath} from './paths';
it('resolves static data and content links beneath a GitHub project base',()=>{
 expect(sitePath('data/gemeinden-2026.json','/steuerpendler/')).toBe('/steuerpendler/data/gemeinden-2026.json');
 expect(sitePath('/pages/methode.html','/steuerpendler/')).toBe('/steuerpendler/pages/methode.html');
 expect(sitePath('','/steuerpendler/')).toBe('/steuerpendler/');
 expect(sitePath('data/map.json','/')).toBe('/data/map.json');
});
