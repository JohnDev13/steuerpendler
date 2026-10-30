import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';
import { premiumFor, validateKk } from './kk';
const data=validateKk(JSON.parse(readFileSync(resolve(import.meta.dirname,'../site/data/kk.json'),'utf8')));
it('looks up household premiums by profile, deductible and mode',()=>{
 const median=premiumFor(data,'2026',261,'s',0,300,'median')!,min=premiumFor(data,'2026',261,'s',0,300,'min')!;
 expect(median).toBeGreaterThan(5000);expect(min).toBeLessThan(median);
 expect(premiumFor(data,'2026',261,'s',0,2500,'median')!).toBeLessThan(median);
 expect(premiumFor(data,'2026',261,'m',2,300,'median')!).toBeGreaterThan(median);
 expect(premiumFor(data,'2026',261,'s',5,300,'median')).toBe(premiumFor(data,'2026',261,'s',3,300,'median'));
 expect(premiumFor(data,'2026',261,'s',0,300,'none')).toBeUndefined();
 expect(premiumFor(data,'2026',999999,'s',0,300,'median')).toBeUndefined();
 expect(premiumFor(data,'2026',261,'s',0,400,'median')).toBeUndefined();
});
it('rejects malformed premium files',()=>{
 expect(()=>validateKk({})).toThrow();
 expect(()=>validateKk({...data,years:{...data.years,'2026':{table:[[1,2]],gemeinden:{'1':0}}}})).toThrow();
});
