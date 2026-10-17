import { expect, it } from 'vitest';
const syntheticProfile = () => ({meta:{year:2026,incomes:{from:40000,step:1000,count:461}},cantons:{ZH:Array.from({length:461},(_,i)=>[100+i,200+i*10,5])}});
const syntheticGemeinde = ['Synthetic fixture', 'ZH', 95, 119, 10, 20] as const;
it('interpolates the documented tax components without rounding the result', async () => {
 const module = await import('./tax').catch(() => ({} as Record<string,unknown>));
 expect(typeof module.calculateTax).toBe('function');
 const calculate = module.calculateTax as any;
 const result = calculate(syntheticProfile(),syntheticGemeinde,40500,'reformed');
 expect(result.bund).toBe(100.5);
 expect(result.kanton).toBe(194.75);
 expect(result.gemeinde).toBe(243.95);
 expect(result.kirche).toBe(20.5);
 expect(result.personal).toBe(5);
 expect(result.total).toBeCloseTo(564.7,8);
});
it('matches exact grid rows, clamps range endpoints and selects church rates',async()=>{
 const {calculateTax}=await import('./tax');
 const p=syntheticProfile();
 for(let i=0;i<461;i++) expect(calculateTax(p,syntheticGemeinde,40000+i*1000,'none').bund).toBe(p.cantons.ZH[i][0]);
 expect(calculateTax(p,syntheticGemeinde,100,'none')).toMatchObject({income:40000,clamped:true,kirche:0});
 expect(calculateTax(p,syntheticGemeinde,999999,'none')).toMatchObject({income:500000,clamped:true});
 expect(calculateTax(p,syntheticGemeinde,40000,'catholic').kirche).toBe(40);
 expect(calculateTax(p,syntheticGemeinde,40000,'reformed').kirche).toBe(20);
 expect(()=>calculateTax(p,syntheticGemeinde,NaN,'none')).toThrow();
});
it('caches metadata and profiles and validates server responses', async()=>{
 const module=await import('./tax') as any;
 expect(typeof module.TaxRepository).toBe('function');
 const calls:string[]=[];
 const fetcher=async(url:string)=>{calls.push(url);return new Response(JSON.stringify(url.includes('gemeinden')?{gemeinden:{'261':syntheticGemeinde}}:syntheticProfile()),{headers:{'content-type':'application/json'}});};
 const repository=new module.TaxRepository(fetcher,'/data','fixture-release');
 await Promise.all([repository.loadGemeinden(),repository.loadGemeinden()]);
 await Promise.all([repository.loadProfile('s',0),repository.loadProfile('s',0)]);
 expect(calls).toHaveLength(2);
 expect(calls.every(url=>url.endsWith('?v=fixture-release'))).toBe(true);
 const invalid=new module.TaxRepository(async()=>new Response('<html>not json</html>',{headers:{'content-type':'text/html'}}));
 await expect(invalid.loadGemeinden()).rejects.toThrow();
});
it('rejects stale served bytes that do not match the pinned release hash',async()=>{
 const {fetchJSON}=await import('./tax');
 const fetcher=async()=>new Response('{"synthetic":true}',{headers:{'content-type':'application/json'}});
 await expect(fetchJSON('/data/synthetic.json?v=test',fetcher,{sha256:'0'.repeat(64)})).rejects.toThrow();
});
