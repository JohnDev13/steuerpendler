import { expect, test } from 'vitest';
import { buildProfile, loadSources, makeInput, buildGemeinden, buildRow, SOURCE } from './build';
import { loadArtifacts, sampleCases, SEED } from './selftest';
import { reconstructPrecision } from './reconstruct';
import { calculateTax, preciseBase, TaxRepository } from '../../src/tax';
import { writeFile } from 'node:fs/promises';
import { calculateTaxesIncomeAndFortune } from '../../vendor/swisstaxcalculator/lib/taxes/income';
import { compilePrecision } from './precision';

async function marriedSionInput() {
 const sources = await loadSources();
 const loc = sources.locations.find(x=>x.BfsID===6266)!;
 return makeInput(loc,'m',3,110000,'catholic');
}

test('zero-income spouse contributes no second-earner deduction in the real engine', async () => {
 const result = await calculateTaxesIncomeAndFortune(await marriedSionInput());
 expect(result.details.deductionsIncome.find(x=>x.id==='ZweitVerdiener_EK')).toBeUndefined();
});

test('positive-income spouse retains the real engine second-earner deduction', async () => {
 const input = await marriedSionInput();
 input.persons[1].income = 20000;
 const result = await calculateTaxesIncomeAndFortune(input);
 const deduction = result.details.deductionsIncome.find(x=>x.id==='ZweitVerdiener_EK');
 expect(deduction?.amountBund).toBeGreaterThan(0);
 expect(deduction?.amountCanton).toBeGreaterThan(0);
});

test('precision compiler explicitly serializes the zero-spouse second-earner branch', async () => {
 const zeroInput = await marriedSionInput();
 const positiveInput = structuredClone(zeroInput);
 positiveInput.persons[1].income = 20000;
 const zero = await compilePrecision(zeroInput);
 const positive = await compilePrecision(positiveInput);
 for (const key of ['bund','canton'] as const) {
  const positiveOp = positive[key].deductions.find(op=>op.format!=='ZERO' && op.source==='constant' && op.value===20000);
  expect(positiveOp).toBeDefined();
  const zeroOp = zero[key].deductions.find(op=>
   op.format==='ZERO' && op.amount===positiveOp?.amount && op.percent===positiveOp?.percent &&
   op.minimum===positiveOp?.minimum && op.maximum===positiveOp?.maximum);
  expect(zeroOp).toBeDefined();
  expect(zeroOp?.value).toBe(0);
 }
});

test('Freienbach precision preserves the authentic capped percentage professional expense', async () => {
 const sources=await loadSources();
 const loc=sources.locations.find(x=>x.BfsID===1322)!;
 const input=makeInput(loc,'s',0,120000,'none');
 const precision=await compilePrecision(input);
 const op=precision.canton.deductions.find(x=>x.format==='PERCENT,MAXIMUM');
 expect(op).toMatchObject({source:'net',percent:20,maximum:6900});
 expect(preciseBase(precision,120000,'ESTV2026Age35','ESTV2026Age35')).toEqual(await buildRow(input));
});

test('TG tracer: preserves taxable CHF100 steps rather than interpolating across them', async () => {
 const sources = await loadSources();
 const loc = sources.locations.find(x=>x.BfsID===4591)!;
 const profile = await buildProfile(sources,'s',1);
 const g = buildGemeinden(sources).gemeinden[loc.BfsID];
 const expected = await calculateTaxesIncomeAndFortune(makeInput(loc,'s',1,321976,'reformed'));
 const actual = calculateTax(profile,g,321976,'reformed');
 expect(Math.abs(actual.total-expected.taxesTotal)).toBeLessThanOrEqual(10);
});

test('marked off-grid Zurich profile includes the age-35 BVG default like the full engine', async () => {
 const sources = await loadSources();
 const loc = sources.locations.find(x=>x.BfsID===261)!;
 const profile = await buildProfile(sources,'s',0);
 const g = buildGemeinden(sources).gemeinden[loc.BfsID];
 const income = 120345;
 const expected = await calculateTaxesIncomeAndFortune(makeInput(loc,'s',0,income,'none'));
 expect(calculateTax(profile,g,income,'none').total).toBe(expected.taxesTotal);
 expect(reconstructPrecision(profile.precision.ZH,income,[g[2],g[3],0],profile.meta.pensionDefault)).toBe(expected.taxesTotal);
});

test('shipped browser independently meets original 500/300 gates against full engine',async()=>{
 const sources=await loadSources(),artifacts=await loadArtifacts();
 const cases=sampleCases(sources);
 const results:{kind:string;bfs:number;canton:string;civil:string;kids:number;church:string;income:number;expected:number;actual:number;error:number;tolerance:number}[]=[];
 for(const [kind,rows] of Object.entries(cases))for(const s of rows){
  const expected=await calculateTaxesIncomeAndFortune(makeInput(s.loc,s.civil,s.kids,s.income,s.church));
  const actual=calculateTax(artifacts.profiles[`${s.civil}-${s.kids}`],artifacts.gemeinden[s.loc.BfsID],s.income,s.church);
  const limit=kind==='offGrid'?10:Math.max(2,Math.abs(expected.taxesTotal)*.0001);
  results.push({kind,bfs:s.loc.BfsID,canton:s.loc.Canton,civil:s.civil,kids:s.kids,church:s.church,income:s.income,expected:expected.taxesTotal,actual:actual.total,error:Math.abs(actual.total-expected.taxesTotal),tolerance:limit});
 }
 const summarize=(kind:string)=>{
  const rows=results.filter(result=>result.kind===kind);
  const worst=rows.reduce((candidate,result)=>result.error>candidate.error?result:candidate);
  const failures=rows.filter(result=>result.error>result.tolerance);
  const {kind:_kind,...worstCase}=worst;
  return {count:rows.length,failureCount:failures.length,maxAbsoluteError:worst.error,worst:worstCase,
   failures:failures.map(({kind:_failureKind,...failure})=>failure),results:rows.map(({kind:_resultKind,...result})=>result)};
 };
 const onGrid=summarize('onGrid'),offGrid=summarize('offGrid');
 const report={source:SOURCE,implementation:'src/tax.ts calculateTax',seed:SEED,prng:'LCG uint32: 1664525*x+101****4223',officialVerification:'pending',artifactSha256:artifacts.sha256,
  gates:{onGrid:'max(2, abs(expected) * 0.0001)',offGrid:10},onGrid,offGrid,passed:onGrid.failureCount===0&&offGrid.failureCount===0};
 const reportPath=process.env.TAX_BROWSER_PARITY_REPORT??new URL('../../docs/tax/current-budget-browser-parity-report.json',import.meta.url);
 await writeFile(reportPath,JSON.stringify(report,null,2)+'\n');
 expect(onGrid.count).toBe(500);
 expect(offGrid.count).toBe(300);
 expect(onGrid.failures,'on-grid frontend comparisons').toEqual([]);
 expect(offGrid.failures,'off-grid frontend comparisons').toEqual([]);
});

test('schema v2 rejects missing precise programs instead of silently using inaccurate interpolation',async()=>{
 const artifacts=await loadArtifacts();
 const p=structuredClone(artifacts.profiles['s-0']);
 delete p.precision;
 const repository=new TaxRepository(async()=>new Response(JSON.stringify(p),{headers:{'content-type':'application/json'}}));
 await expect(repository.loadProfile('s',0)).rejects.toThrow();
});

test('pension marker is optional for genuine legacy profiles but invalid marker combinations are rejected',async()=>{
 const artifacts=await loadArtifacts();
 const generated=artifacts.profiles['s-0'];
 const legacy=structuredClone(generated);
 delete legacy.meta.pensionDefault;
 delete legacy.meta.budgetDefault;
 for(const precision of Object.values(legacy.precision!))for(const part of [precision.bund,precision.canton]){
  part.deductions=part.deductions.filter(op=>op.source!=='rent30');
 }
 expect(Object.values(legacy.precision!).flatMap(p=>[...p.bund.deductions,...p.canton.deductions])).not.toContainEqual(expect.objectContaining({source:'rent30'}));
 const accepted=new TaxRepository(async()=>new Response(JSON.stringify(legacy),{headers:{'content-type':'application/json'}}));
 await expect(accepted.loadProfile('s',0)).resolves.toBeTruthy();

 const unknownPension=structuredClone(generated);
 (unknownPension.meta as any).pensionDefault='SURPRISE';
 const rejectedUnknown=new TaxRepository(async()=>new Response(JSON.stringify(unknownPension),{headers:{'content-type':'application/json'}}));
 await expect(rejectedUnknown.loadProfile('s',0)).rejects.toThrow(/pension/i);

 const missingPension=structuredClone(generated);
 delete missingPension.meta.pensionDefault;
 const rejectedCombination=new TaxRepository(async()=>new Response(JSON.stringify(missingPension),{headers:{'content-type':'application/json'}}));
 await expect(rejectedCombination.loadProfile('s',0)).rejects.toThrow(/budgetDefault benötigt pensionDefault/);
});

test('browser preserves every serialized exact-grid component within 1e-9 CHF',async()=>{
 const artifacts=await loadArtifacts();
 for(const profile of Object.values(artifacts.profiles))for(const [canton,rows] of Object.entries(profile.cantons)){
  // A schema-v1 profile intentionally exercises the unchanged interpolation path.
  const legacy={meta:profile.meta,cantons:profile.cantons};
  const g=['grid probe',canton,100,100,100,100] as const;
  for(let i=0;i<rows.length;i++){
   const actual=calculateTax(legacy,g,40000+i*1000,'reformed');
   const components=[actual.bund,actual.kanton,actual.gemeinde,actual.kirche,actual.personal];
   const expected=[rows[i][0],rows[i][1],rows[i][1],rows[i][1],rows[i][2]];
   for(let k=0;k<components.length;k++)expect(Math.abs(components[k]-expected[k]),`${canton}/${i}/${k}`).toBeLessThanOrEqual(1e-9);
  }
 }
});
