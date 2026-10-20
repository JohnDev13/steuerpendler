import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
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
test('travel assets stay inventoried but unavailable until the v2 release migration',async()=>{
 const {buildRelease}=await import('./build.mjs');
 for(const [label,assets] of [
  ['v1',{
   'meta.json':{schemaVersion:1},
   'access.json':{'261':['Zürich HB',4]},
   'to/4001.json':[[261,20]],
  }],
  ['v2',{
   'meta.json':{schemaVersion:2,targetGroups:{4001:['stop:aarau']}},
   'access.json':{'261':{placeLabel:'Zürich',referenceStop:['stop:zurich','Zürich HB'],centreLV95:[2683000,1247000,'statpop'],candidates:[['stop:zurich','Zürich HB',240]]}},
   'to/4001.json':{schemaVersion:2,to:4001,rows:[[261,[[240,1200,'stop:zurich','stop:aarau',23400,24600]]]]},
  }],
 ]){
  const root=mkdtempSync(join(tmpdir(),`steuer-release-${label}-`));
  try{
   for(const [name,value] of Object.entries(assets)){
    const path=join(root,'site/data/travel',name);
    mkdirSync(join(path,'..'),{recursive:true});
    writeFileSync(path,JSON.stringify(value));
   }
   const result=buildRelease(root);
   assert.equal(result.availability.travel,false,label);
   assert.equal(result.approvals.sbb,false,label);
   for(const name of Object.keys(assets)){
    assert.ok(result.files[`travel/${name}`]?.sha256,`${label} ${name} is inventoried`);
   }
  }finally{rmSync(root,{recursive:true,force:true});}
 }
});
