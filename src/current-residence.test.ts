import { describe, expect, it } from 'vitest';
import { compareAnnualCosts } from './current-residence';
import type { Gemeinde } from './tax';

const gemeinden:Record<string,Gemeinde>={
  '1':['Arbeitsort','ZH',100,100,0,0],
  '2':['Aktueller Wohnort','AG',100,100,0,0],
  '3':['Kandidat','BE',100,100,0,0],
  '4':['Gesperrt','JU',100,100,0,0],
};
const taxes={1:10000,2:12000,3:9000,4:8000};

describe('current-residence annual comparison',()=>{
  it('uses an off-filter residence as baseline and keeps both signs explicit',()=>{
    const comparison=compareAnnualCosts(2,3,gemeinden,taxes,{2:5000,3:5500},new Set());
    expect(comparison).toMatchObject({baselineCost:17000,candidateCost:14500,candidateDelta:-2500,savings:2500,unavailable:null});
  });

  it('returns exact zero when current residence equals the candidate',()=>{
    expect(compareAnnualCosts(2,2,gemeinden,taxes,null,new Set())).toMatchObject({candidateDelta:0,savings:0});
  });

  it('withholds numeric comparison for a withheld current canton',()=>{
    expect(compareAnnualCosts(4,3,gemeinden,taxes,null,new Set(['JU']))).toMatchObject({baselineCost:null,candidateDelta:null,savings:null,unavailable:'withheld'});
  });

  it('does not silently fall back to tax-only when the current premium is missing',()=>{
    expect(compareAnnualCosts(2,3,gemeinden,taxes,{3:5500},new Set())).toMatchObject({baselineCost:null,candidateDelta:null,savings:null,unavailable:'premium'});
  });
  it('still displays the valid current-residence cost when the selected candidate is withheld',()=>{
    expect(compareAnnualCosts(2,4,gemeinden,taxes,{2:5000},new Set(['JU']))).toMatchObject({baselineCost:17000,candidateCost:null,candidateDelta:null,savings:null,unavailable:'candidate'});
  });
});
