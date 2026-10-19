import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
test('an incomplete destination matrix cannot advertise national travel availability',async()=>{
 const {buildRelease}=await import('./build.mjs');
 const root=mkdtempSync(join(tmpdir(),'steuer-partial-travel-fixture-'));
 try{
  const data=join(root,'site/data');mkdirSync(join(data,'travel/to'),{recursive:true});
  const municipalities=JSON.parse(readFileSync(new URL('../../site/data/gemeinden-2026.json',import.meta.url),'utf8'));
  writeFileSync(join(data,'gemeinden-2026.json'),JSON.stringify(municipalities));
  const access=Object.fromEntries(Object.keys(municipalities.gemeinden).map(id=>[id,[`fixture-${id}`,'Synthetic test stop',1]]));
  writeFileSync(join(data,'travel/access.json'),JSON.stringify({gemeinden:access}));
  writeFileSync(join(data,'travel/meta.json'),JSON.stringify({referenceDate:'2026-10-20',timetable:'2026',window:'06:30-08:30'}));
  writeFileSync(join(data,'travel/to/4001.json'),JSON.stringify({to:4001,rows:[[4001,0]]}));
  assert.throws(()=>buildRelease(root),/destination|capital/i);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('release entry point invokes travel validation before publishing manifests',async()=>{
 const {buildRelease}=await import('./build.mjs');
 const root=mkdtempSync(join(tmpdir(),'steuer-travel-validation-fixture-'));
 try{
  const data=join(root,'site/data');mkdirSync(join(data,'travel/to'),{recursive:true});
  const municipalities=JSON.parse(readFileSync(new URL('../../site/data/gemeinden-2026.json',import.meta.url),'utf8'));
  writeFileSync(join(data,'gemeinden-2026.json'),JSON.stringify(municipalities));
  const access=Object.fromEntries(Object.keys(municipalities.gemeinden).map(id=>[id,[`fixture-${id}`,'Synthetic test stop',1]]));
  writeFileSync(join(data,'travel/access.json'),JSON.stringify({gemeinden:access}));
  writeFileSync(join(data,'travel/meta.json'),JSON.stringify({fixture:true,referenceDate:'2026-10-20',timetable:'2026',window:'06:30-08:30'}));
  writeFileSync(join(data,'travel/to/4001.json'),JSON.stringify({to:4001,rows:[[4001,0]]}));
  assert.throws(()=>buildRelease(root),/synthetic|fixture/i);
  assert.equal(existsSync(join(data,'manifest.json')),false);
  assert.equal(existsSync(join(data,'release.json')),false);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('release provenance includes the travel validator source',async()=>{
 const {buildRelease}=await import('./build.mjs');
 const root=mkdtempSync(join(tmpdir(),'steuer-release-provenance-fixture-'));
 try{
  mkdirSync(join(root,'site/data'),{recursive:true});
  mkdirSync(join(root,'scripts/release'),{recursive:true});
  writeFileSync(join(root,'scripts/release/travel.mjs'),'export const validatorVersion = 1;\n');
  const first=buildRelease(root);
  assert.ok(first.inputs['scripts/release/travel.mjs']?.sha256);
  writeFileSync(join(root,'scripts/release/travel.mjs'),'export const validatorVersion = 2;\n');
  assert.notEqual(buildRelease(root).release,first.release);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('release inventory is deterministic, excludes itself and changes with actual bytes',async()=>{
 const module=await import('./build.mjs').catch(()=>({}));
 assert.equal(typeof module.buildRelease,'function');
 const root=mkdtempSync(join(tmpdir(),'steuer-release-fixture-'));
 try{
  mkdirSync(join(root,'site/data'),{recursive:true});
  writeFileSync(join(root,'site/data/synthetic.json'),'{"syntheticFixture":true}');
  const first=module.buildRelease(root),bytes=readFileSync(join(root,'site/data/manifest.json'),'utf8');
  const second=module.buildRelease(root);
  assert.equal(first.release,second.release);assert.equal(readFileSync(join(root,'site/data/manifest.json'),'utf8'),bytes);
  assert.equal(first.availability.tax,false);assert.equal(first.availability.travel,false);
  assert.ok(first.files['synthetic.json'].sha256);assert.equal(first.files['manifest.json'],undefined);assert.equal(first.files['release.json'],undefined);
  writeFileSync(join(root,'site/data/synthetic.json'),'{"syntheticFixture":"changed"}');
  assert.notEqual(module.buildRelease(root).release,first.release);
 }finally{rmSync(root,{recursive:true,force:true});}
});
