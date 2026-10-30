// A separate serialized-program interpreter for table validation. Does not call
// the full engine, taxable-income calculator or the browser implementation.
import { add,subtract } from 'dinero.js';
import { dineroChf,dineroToNumber,dineroRound,dineroRoundHalfUp,dineroRoundMin0,dineroRoundDown,multiplyDineroPercent,multiplyDineroFactor,dineroMin,dineroMax } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import { applyTariffRounding, calculateTaxesAmount } from '../../vendor/swisstaxcalculator/lib/taxes/tarif';
import type { BudgetDefault, PensionDefault, PreciseCanton, PreciseLate } from '../../src/tax';
import { lateDeduction } from '../../vendor/swisstaxcalculator/lib/taxes/deduction/cantonal';
import { calculateBvg2026Age35 } from './bvg';
export function reconstructPrecision(p:PreciseCanton,income:number,rates:number[],pensionDefault?:PensionDefault,budgetDefault?:BudgetDefault,personalChurch=0,churchOnTaxable=false,personalOverride?:number):number {
 let cantonTaxable=0;
 const gross=dineroChf(income),capped=dineroMin(gross,dineroChf(148200));
 const social=subtract(subtract(subtract(gross,dineroRoundHalfUp(multiplyDineroPercent(gross,5.3,1))),dineroRoundHalfUp(multiplyDineroPercent(capped,1.1,1))),dineroRoundHalfUp(multiplyDineroPercent(capped,.4,1)));
 const net=pensionDefault==='ESTV2026Age35'?subtract(social,dineroChf(calculateBvg2026Age35(income))):social;
 const base=(part:PreciseCanton['bund'])=>{
  let deductions=dineroChf(0);
  for(const op of part.deductions){
   const estimatedRent=Math.round(dineroToNumber(net)*.25/10)*10;
   const value=op.source==='net'?net:op.source==='rent30'&&budgetDefault==='ESTV2026Age35'?dineroChf(estimatedRent*.3):dineroChf(op.value);let d=dineroChf(0);
   switch(op.format){
    case 'ZERO':break;
    case 'STANDARDIZED':d=dineroChf(op.amount);break;
    case 'MAXIMUM':d=dineroMin(value,dineroChf(op.maximum));break;
    case 'PERCENT':d=dineroRoundDown(multiplyDineroPercent(value,op.percent,5));break;
    case 'PERCENT,MAXIMUM':d=dineroMin(dineroRoundDown(multiplyDineroPercent(value,op.percent,5)),dineroChf(op.maximum));break;
    case 'PERCENT,MINIMUM,MAXIMUM':d=dineroMin(dineroMax(dineroRoundDown(multiplyDineroPercent(value,op.percent,5)),dineroChf(op.minimum)),dineroChf(op.maximum));break;
    case 'STANDARDIZED,PERCENT,MAXIMUM':d=dineroMin(add(dineroChf(op.amount),dineroRoundDown(multiplyDineroPercent(value,op.percent,5))),dineroChf(op.maximum));break;
   }
   deductions=add(deductions,multiplyDineroFactor(d,op.multiplier,1));
  }
  const t=part.tariff;
  let taxable=dineroToNumber(dineroRoundMin0(subtract(net,deductions)));
  const done:number[]=[];
  for(const l of (part.late??[]) as PreciseLate[]){
   const basis=taxable+l.addBack+l.addBackLate.reduce((s,i)=>s+done[i],0);
   const d=lateDeduction({...l,id:'',roundUp:l.roundUp===1,cap:l.threshold,addBack:[]} as any,basis,dineroToNumber(net));
   done.push(d);taxable-=d;
  }
  taxable=Math.max(0,taxable);
  if(part===p.canton)cantonTaxable=taxable;
  return dineroChf(applyTariffRounding(t.rounding,taxable,t.split,a=>dineroToNumber(calculateTaxesAmount(dineroChf(a,5),{tableType:t.type,table:t.table} as any)),t.rounding==='quotient'?{q0:t.q0??t.split,cap:t.cap??0}:undefined),5);
 };
 const bund=dineroRoundMin0(subtract(dineroRound(base(p.bund)),dineroChf(263*p.kids)));
 const bundLevied=dineroToNumber(bund)<25?dineroChf(0):bund;
 const unreduced=base(p.canton);
 const canton=p.canton.reduction?dineroChf(Math.max(0,dineroToNumber(unreduced)-p.canton.reduction),5):unreduced;
 const churchRate=Math.round(rates[2]/p.persons*100)/100*p.persons;
 const nonFederal=dineroToNumber([dineroChf(Math.max(0,dineroToNumber(dineroRound(multiplyDineroPercent(canton,rates[0],5)))-(p.cantonReduction??0))),dineroRound(multiplyDineroPercent(canton,rates[1],5)),dineroRound(multiplyDineroPercent(churchOnTaxable?dineroChf(cantonTaxable):canton,churchRate,5)),dineroChf(personalOverride??p.personal+personalChurch)].reduce(add,dineroChf(0)));
 return dineroToNumber(bundLevied)+nonFederal-Math.min(p.credit??0,Math.max(0,nonFederal));
}
