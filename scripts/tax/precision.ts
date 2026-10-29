// Partial evaluation of authentic deductions for the frozen one-earner profile.
// No tax results, sampler cases or municipal scope constants are embedded here.
import { calculateDeductionByDefinition, calculateGrossNetDetails, taxDeductionDefinitions } from '../../vendor/swisstaxcalculator/lib/taxes/deduction';
import { cantonalRules } from '../../vendor/swisstaxcalculator/lib/taxes/deduction/cantonal';
import { getTaxDecutionTable } from '../../vendor/swisstaxcalculator/lib/taxes/deduction/provider';
import { getTaxTarifGroup, isGroupEligableForSplitting, tariffRounding } from '../../vendor/swisstaxcalculator/lib/taxes/tarif';
import { getTaxTarifTable } from '../../vendor/swisstaxcalculator/lib/taxes/tarif/provider';
import { calculateTaxesPersonnel } from '../../vendor/swisstaxcalculator/lib/taxes/personnel';
import { dineroToNumber } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import type { TaxInput } from '../../vendor/swisstaxcalculator/lib/taxes/typesClient';
import type { PreciseCanton, DeductionOp, PreciseLate } from '../../src/tax';
export async function compilePrecision(input:TaxInput):Promise<PreciseCanton> {
 const group=getTaxTarifGroup(input.relationship,input.children);
 const compile=async(id:number)=>{
  const deductions=await getTaxDecutionTable(id,2026,'EINKOMMENSSTEUER');
  const a={...input,persons:input.persons.map((p,i)=>({...p,income:i===0?100000:p.income}))};
  const b={...input,persons:input.persons.map((p,i)=>({...p,income:i===0?200000:p.income}))};
  const ga=calculateGrossNetDetails(a),gb=calculateGrossNetDetails(b);
  const ops:DeductionOp[]=[];
  const rules=id===0?{disable:[] as string[],late:[]}:cantonalRules({cantonId:id,married:['m','rp'].includes(input.relationship),kids:input.children},deductions);
  for(const def of taxDeductionDefinitions){
   const row=deductions.itemsById.get(def.id);
   if(!row||rules.disable.includes(def.id))continue;
   if(!def.rule(a,'EINKOMMENSSTEUER')){
    if(def.id==='ZweitVerdiener_EK')ops.push({source:'constant',value:0,format:'ZERO',amount:row.amount,percent:row.percent,minimum:row.minimum,maximum:row.maximum,multiplier:1});
    continue;
   }
   const ia=def.input(a,ga,deductions),ib=def.input(b,gb,deductions);
   for(let i=0;i<ia.length;i++){
    const x=ia[i],y=ib[i];
    const net=x.amount!==y.amount;
    if(net&&(x.amount!==ga[0].netIncome||y.amount!==gb[0].netIncome))throw Error(`Unrepresentable deduction ${def.id}`);
    const implemented = ['STANDARDIZED','MAXIMUM','PERCENT','PERCENT,MAXIMUM','PERCENT,MINIMUM,MAXIMUM','STANDARDIZED,PERCENT,MAXIMUM'].includes(row.format);
    // Upstream's default branch contributes zero for other authentic formats.
    // Serialize that explicitly so unknown browser payload formats are rejected.
    const source = def.id === 'MaxAbzMiete_EK' ? 'rent30' : net ? 'net' : 'constant';
    // rent30 is reconstructed from current net income; never freeze the seed input's rent.
    ops.push({source,value:source==='rent30'?0:x.amount??0,format:implemented?row.format as DeductionOp['format']:'ZERO',amount:row.amount,percent:row.percent,minimum:row.minimum,maximum:row.maximum,multiplier:x.multiplier??1});
   }
  }
  // Late rules: the ordinary deductions they add back must not depend on income (checked at two incomes).
  const ordinaryAmount=(target:typeof a,g:typeof ga,ruleId:string)=>{
   const def=taxDeductionDefinitions.find(d=>d.id===ruleId);
   if(!def||rules.disable.includes(ruleId))return 0;
   return calculateDeductionByDefinition(def,target,'EINKOMMENSSTEUER',g,deductions,undefined).reduce((sum,item)=>sum+dineroToNumber(item.amountCanton),0);
  };
  const late:PreciseLate[]=rules.late.map((rule,index)=>{
   const lateIds=rules.late.slice(0,index).map(r=>r.id);
   let addBack=0;
   for(const ruleId of rule.addBack.filter(x=>!lateIds.includes(x))){
    const va=ordinaryAmount(a,ga,ruleId),vb=ordinaryAmount(b,gb,ruleId);
    if(va!==vb)throw Error(`Income-dependent add-back ${ruleId}`);
    addBack+=va;
   }
   const addBackLate=rule.addBack.flatMap(x=>lateIds.flatMap((lid,i)=>lid===x?[i]:[]));
   return {kind:rule.kind,amount:rule.kind==='fixed'?rule.amount:0,rate:'rate' in rule?rule.rate:0,max:rule.kind==='percent'?rule.max:0,
    threshold:'threshold' in rule?rule.threshold:0,base:rule.kind==='step'?rule.base:0,step:rule.kind==='step'?rule.step:0,
    reduction:rule.kind==='step'?rule.reduction:0,addBack,addBackLate};
  });
  const [tariff,used]=await getTaxTarifTable(id,2026,'EINKOMMENSSTEUER',group);
  return {deductions:ops,...(late.length?{late}:{}),tariff:{type:tariff.tableType,split:tariff.splitting>0&&isGroupEligableForSplitting(used)?tariff.splitting:1,rounding:tariffRounding(id,tariff.tableType),table:tariff.table}};
 };
 const personal=(confession:'other'|'protestant'|'roman')=>dineroToNumber(calculateTaxesPersonnel({...input,persons:input.persons.map(p=>({...p,confession}))}));
 return {bund:await compile(0),canton:await compile(input.cantonId),personal:personal('other'),personalChurch:{reformed:personal('protestant')-personal('other'),catholic:personal('roman')-personal('other')},kids:input.children,persons:input.persons.length};
}
