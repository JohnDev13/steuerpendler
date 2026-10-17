// A separate serialized-program interpreter for table validation. Does not call
// the full engine, taxable-income calculator or the browser implementation.
import { add,subtract } from 'dinero.js';
import { dineroChf,dineroToNumber,dineroRound,dineroRoundMin0,dineroRound100Down,multiplyDineroPercent,multiplyDineroFactor,dineroMin,dineroMax } from '../../vendor/swisstaxcalculator/lib/utils/dinero';
import { calculateTaxesAmount } from '../../vendor/swisstaxcalculator/lib/taxes/tarif';
import type { PreciseCanton } from '../../src/tax';
export function reconstructPrecision(p:PreciseCanton,income:number,rates:number[]):number {
 const gross=dineroChf(income),capped=dineroMin(gross,dineroChf(148200));
 const net=subtract(subtract(subtract(gross,dineroRound(multiplyDineroPercent(gross,5.3,1))),dineroRound(multiplyDineroPercent(capped,1.1,1))),dineroRound(multiplyDineroPercent(capped,.4,1)));
 const base=(part:PreciseCanton['bund'])=>{
  let deductions=dineroChf(0);
  for(const op of part.deductions){const value=op.source==='net'?net:dineroChf(op.value);let d=dineroChf(0);
   switch(op.format){
    case 'ZERO':break;
    case 'STANDARDIZED':d=dineroChf(op.amount);break;
    case 'MAXIMUM':d=dineroMin(value,dineroChf(op.maximum));break;
    case 'PERCENT':d=dineroRound(multiplyDineroPercent(value,op.percent,5));break;
    case 'PERCENT,MINIMUM,MAXIMUM':d=dineroMin(dineroMax(dineroRound(multiplyDineroPercent(value,op.percent,5)),dineroChf(op.minimum)),dineroChf(op.maximum));break;
   }
   deductions=add(deductions,multiplyDineroFactor(d,op.multiplier,1));
  }
  const t=part.tariff;
  let amount=multiplyDineroFactor(dineroRoundMin0(subtract(net,deductions)),1/t.split,5);
  if(t.type!=='FORMEL')amount=dineroRound100Down(amount);
  return multiplyDineroFactor(calculateTaxesAmount(amount,{tableType:t.type,table:t.table} as any),t.split,5);
 };
 const bund=dineroRoundMin0(subtract(dineroRound(base(p.bund)),dineroChf(263*p.kids)));
 const canton=base(p.canton);
 const churchRate=Math.round(rates[2]/p.persons*100)/100*p.persons;
 return dineroToNumber([dineroRound(multiplyDineroPercent(canton,rates[0],5)),dineroRound(multiplyDineroPercent(canton,rates[1],5)),dineroRound(multiplyDineroPercent(canton,churchRate,5)),dineroChf(p.personal)].reduce(add,bund));
}
