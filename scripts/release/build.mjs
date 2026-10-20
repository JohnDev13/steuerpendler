import {createHash} from 'node:crypto';
import {existsSync,readdirSync,readFileSync,writeFileSync,statSync} from 'node:fs';
import {resolve,join,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
function sorted(value){if(Array.isArray(value))return value.map(sorted);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,sorted(value[key])]));return value;}
function filesUnder(path){if(!existsSync(path))return [];return readdirSync(path).sort().flatMap(name=>{const p=join(path,name);return statSync(p).isDirectory()?filesUnder(p):[p];});}
export function buildRelease(root=process.cwd()){
 const data=join(root,'site/data'),files={};
 for(const path of filesUnder(data)){
  const name=relative(data,path).replaceAll('\\','/');
  if(!name.endsWith('.json')||['manifest.json','release.json'].includes(name))continue;
  const bytes=readFileSync(path);JSON.parse(bytes.toString('utf8'));
  files[name]={sha256:hash(bytes),bytes:bytes.length};
 }
 const inputs={};
 for(const name of ['SPEC.md','src/destinations.ts','package-lock.json','scripts/release/build.mjs','scripts/tax/build.ts','scripts/map/build.mjs','docs/map/source-manifest.json','vendor/swisstaxcalculator/STEUERPENDLER-PATCHES.md']){
  const path=join(root,name);if(existsSync(path))inputs[name]={sha256:hash(readFileSync(path)),bytes:statSync(path).size};
 }
 const release=hash(JSON.stringify(sorted({schemaVersion:1,files,inputs})));
 const taxAvailable=!!files['gemeinden-2026.json']&&['s','m'].every(civ=>[0,1,2,3].every(kids=>files[`tax-2026-${civ}-${kids}.json`]));
 // Fail closed until the frontend, schema-v2 validation and official travel checks migrate together.
 const travelAvailable=false;
 const result={schemaVersion:1,release,taxYear:2026,availability:{tax:taxAvailable,map:!!files['map/switzerland-2026.json'],travel:travelAvailable},approvals:{estv:false,sbb:false,content:false,golden:false,geodataLicense:false},status:'reconstruction',files,inputs};
 const output=JSON.stringify(sorted(result));
 writeFileSync(join(data,'manifest.json'),output);writeFileSync(join(data,'release.json'),output);
 return result;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){const result=buildRelease();console.log(JSON.stringify({release:result.release,availability:result.availability,files:Object.keys(result.files).length,approvals:result.approvals}));}
