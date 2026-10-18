import test from 'node:test';
import assert from 'node:assert/strict';
import {validateTravelDataset} from './travel.mjs';
test('publication rejects synthetic travel and invalid reference-day/window metadata',()=>{
 for(const change of [{fixture:true},{referenceDate:'2026-10-19'},{referenceDate:'2026-02-31'},{window:'06:00-09:00'},{timetable:''}]){
  const data=fixture();Object.assign(data.meta,change);assert.throws(()=>validateTravelDataset(data),/fixture|reference|window|timetable/i);
 }
});
// Synthetic in-memory structural fixtures only; never timetable evidence or site data.
const homes={'1':['Residential neighbour','SO',100,100,0,0],'2':['Capital A','AG',100,100,0,0],'3':['Capital B','ZH',100,100,0,0]};
function fixture(){return {gemeinden:homes,destinations:[2,3],meta:{referenceDate:'2026-10-20',timetable:'2026',window:'06:30-08:30'},access:{gemeinden:{1:['one','Fixture one',15],2:['two','Fixture two',1],3:['three','Fixture three',2]}},matrices:{2:{to:2,rows:[[2,0],[1,20]]},3:{to:3,rows:[[3,0],[1,60]]}}};}
test('travel release retains all residential origins and requires every usable capital file',async()=>{
 const module=await import('./travel.mjs').catch(()=>({}));
 assert.equal(typeof module.validateTravelDataset,'function');
 assert.equal(module.validateTravelDataset(fixture()),true);
 const incomplete=fixture();delete incomplete.access.gemeinden[1];
 assert.throws(()=>module.validateTravelDataset(incomplete),/residential|origin/i);
 const partial=fixture();delete partial.matrices[3];
 assert.throws(()=>module.validateTravelDataset(partial),/destination|capital/i);
});
test('travel matrices reject fractional, unknown, duplicate, unsorted and false-zero rows',async()=>{
 const {validateTravelDataset}=await import('./travel.mjs');
 for(const rows of [[[2,0],[1,20.1]],[[2,0],[99,5]],[[2,0],[1,20],[1,20]],[[2,0],[3,20],[1,20]],[[2,0],[1,0]],[[2,0],[1,61]]]){
  const data=fixture();data.matrices[2].rows=rows;
  assert.throws(()=>validateTravelDataset(data),/row|sort|zero/i);
 }
 const shared=fixture();shared.access.gemeinden[1][0]='two';shared.matrices[2].rows=[[1,0],[2,0]];
 assert.equal(validateTravelDataset(shared),true);
});
