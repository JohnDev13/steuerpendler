import type { Gemeinde } from './tax';

export type ComparisonUnavailable = 'withheld'|'tax'|'premium'|'candidate';
export interface AnnualComparison {
  baselineId:number;
  candidateId:number;
  baselineCost:number|null;
  candidateCost:number|null;
  candidateDelta:number|null;
  savings:number|null;
  unavailable:ComparisonUnavailable|null;
}

/** Compare annual candidate cost with a committed residence, independent of commute filtering. */
export function compareAnnualCosts(
  baselineId:number,
  candidateId:number,
  gemeinden:Readonly<Record<string,Gemeinde>>,
  taxes:Readonly<Record<string,number>>,
  premiums:Readonly<Record<string,number|undefined>>|null,
  withheldCantons:ReadonlySet<string>,
):AnnualComparison {
  const baseline=gemeinden[baselineId],candidate=gemeinden[candidateId];
  const empty=(unavailable:ComparisonUnavailable):AnnualComparison=>({baselineId,candidateId,baselineCost:null,candidateCost:null,candidateDelta:null,savings:null,unavailable});
  if(!baseline||withheldCantons.has(baseline[1]))return empty('withheld');
  const baselineTax=taxes[baselineId];
  if(!Number.isFinite(baselineTax))return empty('tax');
  const baselinePremium=premiums?.[baselineId];
  if(premiums && !Number.isFinite(baselinePremium))return empty('premium');
  const baselineCost=baselineTax+(baselinePremium??0);
  const unavailableCandidate=():AnnualComparison=>({baselineId,candidateId,baselineCost,candidateCost:null,candidateDelta:null,savings:null,unavailable:'candidate'});
  if(!candidate||withheldCantons.has(candidate[1])||!Number.isFinite(taxes[candidateId]))return unavailableCandidate();
  const candidatePremium=premiums?.[candidateId];
  if(premiums && !Number.isFinite(candidatePremium))return unavailableCandidate();
  const candidateCost=taxes[candidateId]+(candidatePremium??0);
  return {baselineId,candidateId,baselineCost,candidateCost,candidateDelta:candidateCost-baselineCost,savings:baselineCost-candidateCost,unavailable:null};
}
