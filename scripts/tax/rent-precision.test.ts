import { expect, test } from 'vitest';
import { calculateGrossNetDetails } from '../../vendor/swisstaxcalculator/lib/taxes/deduction';
import { calculateTaxesIncomeAndFortune } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { buildGemeinden, loadSources, makeInput, type TaxRow } from './build';
import { loadArtifacts } from './selftest';
import { compilePrecision } from './precision';
import { reconstructPrecision } from './reconstruct';
import { calculateTax, preciseBase, TaxRepository, type TaxProfile } from '../../src/tax';

async function zugFixture(income:number) {
 const sources=await loadSources();
 const loc=sources.locations.find(x=>x.Canton==='ZG')!;
 const input=makeInput(loc,'s',0,income,'none');
 const precision=await compilePrecision(input);
 const g=buildGemeinden(sources).gemeinden[loc.BfsID];
 return {input,precision,g};
}

function profile(precision:Awaited<ReturnType<typeof compilePrecision>>,rows:TaxRow[]):TaxProfile {
 return {meta:{year:2026,schemaVersion:2,pensionDefault:'ESTV2026Age35',budgetDefault:'ESTV2026Age35',incomes:{from:40000,step:1000,count:461}},cantons:{ZG:rows},precision:{ZG:precision}};
}

function repository(payload:unknown) {
 return new TaxRepository(async()=>new Response(JSON.stringify(payload),{headers:{'content-type':'application/json'}}));
}

test('captured ZG CHF 120000 input derives CHF 26900 rent from actual post-BVG net salary',async()=>{
 const {input}=await zugFixture(120000);
 const net=calculateGrossNetDetails(input)[0].netIncome;
 expect(net).toBe(107602);
 expect(input.deductions?.rentExpenses).toBe(26900);
 const result=await calculateTaxesIncomeAndFortune(input);
 expect(result.details.deductionsIncome.find(x=>x.id==='MaxAbzMiete_EK')?.amountCanton).toBe(8070);
});

test('ZG compiler emits dynamic rent30 instead of frozen seed-income rent',async()=>{
 const {precision}=await zugFixture(120000);
 const op=precision.canton.deductions.find(x=>x.source==='rent30');
 expect(op).toMatchObject({source:'rent30',value:0,format:'MAXIMUM',maximum:10800});
});

test.each([[120345,8094],[300345,10800]])('browser and independent reconstruction match full ZG engine off-grid at CHF %i',async (income,rentDeduction)=>{
 const {input,precision,g}=await zugFixture(income);
 const expected=await calculateTaxesIncomeAndFortune(input);
 const rows=Array.from({length:461},()=>[0,0,0] as TaxRow);
 const p=profile(precision,rows);
 expect(calculateTax(p,g,income,'none').total).toBe(expected.taxesTotal);
 expect(reconstructPrecision(precision,income,[g[2],g[3],0],p.meta.pensionDefault,p.meta.budgetDefault)).toBe(expected.taxesTotal);
 const rentOp=precision.canton.deductions.find(x=>x.source==='rent30')!;
 const base=preciseBase(precision,income,p.meta.pensionDefault,p.meta.budgetDefault);
 expect(rentOp.maximum===10800).toBe(true);
 expect(expected.details.deductionsIncome.find(x=>x.id==='MaxAbzMiete_EK')?.amountCanton).toBe(rentDeduction);
 expect(base[1]).toBeGreaterThanOrEqual(0);
});

test('exact grid rows remain authoritative with rent30 precision present',async()=>{
 const {precision,g}=await zugFixture(120000);
 const rows=Array.from({length:461},()=>[0,0,0] as TaxRow);
 rows[80]=[101,202,303]; rows[81]=[999,999,999];
 const actual=calculateTax(profile(precision,rows),g,120000,'none');
 expect([actual.bund,actual.personal]).toEqual([101,303]);
 expect(actual.kanton).toBe(Math.round(202*g[2]/100));
});

test('legacy/no-op is accepted while invalid budget and rent30 marker combinations reject',async()=>{
 const rows=Array.from({length:461},()=>[0,0,0] as number[]);
 const legacy={meta:{year:2026,incomes:{from:40000,step:1000,count:461}},cantons:{ZG:rows}};
 await expect(repository(legacy).loadProfile('s',0)).resolves.toBeTruthy();
 await expect(repository({...legacy,meta:{...legacy.meta,budgetDefault:'SURPRISE'}}).loadProfile('s',0)).rejects.toThrow(/budget/i);
 await expect(repository({...legacy,meta:{...legacy.meta,budgetDefault:'ESTV2026Age35'}}).loadProfile('s',0)).rejects.toThrow(/pension/i);
 const artifacts=await loadArtifacts();
 const invalid=structuredClone(artifacts.profiles['s-0']) as TaxProfile;
 const existing=invalid.precision!.ZG.canton.deductions[0];
 invalid.precision!.ZG.canton.deductions[0]={...existing,source:'rent30',value:0};
 delete invalid.meta.budgetDefault;
 await expect(repository(invalid).loadProfile('s',0)).rejects.toThrow(/rent30|budget/i);
});
