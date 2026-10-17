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
