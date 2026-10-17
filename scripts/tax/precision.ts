// Partial evaluation of authentic deductions for the frozen one-earner profile.
// No tax results, sampler cases or municipal scope constants are embedded here.
import { calculateGrossNetDetails, taxDeductionDefinitions } from '../../vendor/swisstaxcalculator/lib/taxes/deduction';
import { getTaxDecutionTable } from '../../vendor/swisstaxcalculator/lib/taxes/deduction/provider';
import { getTaxTarifGroup, isGroupEligableForSplitting } from '../../vendor/swisstaxcalculator/lib/taxes/tarif';
import { getTaxTarifTable } from '../../vendor/swisstaxcalculator/lib/taxes/tarif/provider';
import { calculateTaxesPersonnel } from '../../vendor/swisstaxcalculator/lib/taxes/personnel';
import { dineroToNumber } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import type { TaxInput } from '../../vendor/swisstaxcalculator/lib/taxes/typesClient';
import type { PreciseCanton, DeductionOp } from '../../src/tax';
export async function compilePrecision(input:TaxInput):Promise<PreciseCanton> {
 const group=getTaxTarifGroup(input.relationship,input.children);
 const compile=async(id:number)=>{
  const deductions=await getTaxDecutionTable(id,2026,'EINKOMMENSSTEUER');
  const a={...input,persons:input.persons.map((p,i)=>({...p,income:i===0?100000:p.income}))};
  const b={...input,persons:input.persons.map((p,i)=>({...p,income:i===0?200000:p.income}))};
  const ga=calculateGrossNetDetails(a),gb=calculateGrossNetDetails(b);
  const ops:DeductionOp[]=[];
  for(const def of taxDeductionDefinitions){
   const row=deductions.itemsById.get(def.id);
   if(!row)continue;
   if(!def.rule(a,'EINKOMMENSSTEUER')){
    if(def.id==='ZweitVerdiener_EK')ops.push({source:'constant',value:0,format:'ZERO',amount:row.amount,percent:row.percent,minimum:row.minimum,maximum:row.maximum,multiplier:1});
    continue;
   }
   const ia=def.input(a,ga),ib=def.input(b,gb);
   for(let i=0;i<ia.length;i++){
    const x=ia[i],y=ib[i];
    const net=x.amount!==y.amount;
    if(net&&(x.amount!==ga[0].netIncome||y.amount!==gb[0].netIncome))throw Error(`Unrepresentable deduction ${def.id}`);
    const implemented = ['STANDARDIZED','MAXIMUM','PERCENT','PERCENT,MINIMUM,MAXIMUM'].includes(row.format);
    // Upstream's default branch contributes zero for other authentic formats.
    // Serialize that explicitly so unknown browser payload formats are rejected.
    ops.push({source:net?'net':'constant',value:x.amount??0,format:implemented?row.format as DeductionOp['format']:'ZERO',amount:row.amount,percent:row.percent,minimum:row.minimum,maximum:row.maximum,multiplier:x.multiplier??1});
   }
  }
  const [tariff,used]=await getTaxTarifTable(id,2026,'EINKOMMENSSTEUER',group);
  return {deductions:ops,tariff:{type:tariff.tableType,split:tariff.splitting>0&&isGroupEligableForSplitting(used)?tariff.splitting:1,table:tariff.table}};
 };
 return {bund:await compile(0),canton:await compile(input.cantonId),personal:dineroToNumber(calculateTaxesPersonnel(input)),kids:input.children,persons:input.persons.length};
}
