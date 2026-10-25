import './styles.css';
import { strings as s } from './strings';
import { initialState } from './state';
import { installMunicipalitySearch } from './municipality-search';
import { workplaceGemeinden } from './destinations';
import { TaxRepository, calculateTax, type Gemeinde, type TaxBreakdown } from './tax';
import { sitePath } from './paths';
import { withheldCantons } from './policy';
import { filterAndRank, type Access, type TravelRows, type RankedResult } from './filter';
import { DATA_RELEASE, QUARANTINED_CANTONS, COLOURS } from './config';
import { formatCHF } from './format';
import { createMap } from './map';
import { renderList } from './list';
import { renderDetail } from './detail';
import { loadAarauPreview, type AarauPreview, type AdaptedAarauPreview } from './preview';
import { adaptObservedAarau, loadTransferWitness, type TransferWitness } from './transfer-preview';
import { adaptObservedRoutes, loadObservedRoutes, type ObservedRoutes } from './observed-routes';
const app=document.querySelector<HTMLDivElement>('#app')!;
app.innerHTML=`<header class="site-header"><a class="brand" href="${sitePath('')}">↗ ${s.appName}</a><button id="theme" type="button" aria-label="${s.theme}">◐</button></header>
<section class="hero"><p class="eyebrow">${s.eyebrow}</p><h1>${s.appName}</h1><p class="hero-copy">${s.intro}</p><p class="release-status" data-testid="release-status">${s.preview}</p></section>
<main class="workspace"><aside class="controls panel"><h2>${s.filters}</h2>
<div class="field search-field"><label for="workplace">${s.workplace}</label><input id="workplace" value="Aarau" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="workplace-options" autocomplete="off"><div id="workplace-options" role="listbox" hidden></div><small>${s.workplaceHint}</small></div>
<div class="field"><div class="label-row"><label for="max-time">${s.maxTime}</label><output id="time-value">25 ${s.minutes}</output></div><input id="max-time" type="range" min="5" max="30" step="1" value="25"></div>
<div class="field"><div class="label-row"><label for="max-walk">${s.maxWalk}</label><output id="walk-value">10 ${s.minutes}</output></div><input id="max-walk" type="range" min="0" max="15" step="1" value="10"></div>
<label class="toggle"><input id="count-walk" type="checkbox"><span>${s.countWalk}</span></label><label class="toggle"><input id="direct-only" type="checkbox"><span>${s.directOnly}</span></label><hr>
<div class="field"><label for="income">${s.income}</label><input id="income" type="number" inputmode="numeric" min="40000" max="500000" step="1000" value="120000"><input id="income-slider" type="range" aria-label="${s.incomeSlider}" min="40000" max="500000" step="1000" value="120000"><small id="clamp-note" hidden>${s.clamped}</small></div>
<div class="field"><label for="civil">${s.civil}</label><select id="civil"><option value="s">${s.single}</option><option value="m">${s.married}</option></select></div>
<div class="paired"><div class="field"><label for="kids">${s.children}</label><select id="kids"><option>0</option><option>1</option><option>2</option><option value="3">3+</option></select></div><div class="field"><label for="church">${s.church}</label><select id="church"><option value="none">${s.none}</option><option value="reformed">${s.reformed}</option><option value="catholic">${s.catholic}</option></select></div></div></aside>
<section class="results"><div class="summary"><p class="eyebrow">${s.results}</p><h2 id="summary">${s.loading}</h2><p id="cheapest"></p></div><p class="assumptions">${s.assumptions} <strong>${s.disclaimer}</strong></p><p id="result-notice" class="notice">${s.unverified}</p><p id="profile-status" class="assumptions" aria-live="polite"></p><p id="data-status" class="data-status" role="status" aria-live="polite"></p>
<section class="map-panel panel" aria-label="${s.map}"><div class="field search-field"><label for="residence">${s.residenceSearch}</label><input id="residence" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="residence-options" autocomplete="off"><div id="residence-options" role="listbox" hidden></div><small>${s.residenceHint}</small></div><div id="map"><p>${s.mapPending}</p></div><div class="legend"><span>${s.cheap}</span>${COLOURS.map(c=>`<i style="background:${c}"></i>`).join('')}<span>${s.expensive}</span><span class="legend-muted">◻ ${s.noData}</span></div><small>${s.mapHelp}</small></section>
<section class="list-panel panel" aria-label="${s.results}"><table><thead><tr>${[s.rank,s.municipality,s.canton,s.travel,s.walk,s.tax,s.difference].map(label=>`<th scope="col">${label}</th>`).join('')}</tr></thead><tbody id="ranked-list"></tbody></table><p id="empty-state" hidden>${s.empty}</p></section>
<section id="detail" class="detail-panel panel" aria-label="${s.detail}" tabindex="-1"><p>${s.selectDetail}</p></section></section></main>
<footer><p>${s.credits}</p><p>${s.mapSource} — <a href="https://data.geo.admin.ch/api/stac/v0.9/collections/ch.bfs.historisierte-administrative_grenzen_g1">${s.mapSourceTitle}</a>; ${s.mapAdaptation} <a href="https://opendata.swiss/en/terms-of-use#terms_by_ask">${s.mapTerms}</a> · <a href="${sitePath('credits/NOTICE.txt')}">${s.notices}</a></p><p>${s.licencePending}</p><nav><a href="${sitePath('')}pages/impressum.html">${s.impressum}</a><a href="${sitePath('')}pages/datenschutz.html">${s.privacy}</a><a href="${sitePath('')}pages/methode.html">${s.method}</a></nav></footer>`;
const $=<T extends HTMLElement=HTMLElement>(id:string)=>document.getElementById(id) as T;
const state={...initialState},repository=new TaxRepository(fetch,sitePath('data'),DATA_RELEASE.release,DATA_RELEASE.files);
let gemeinden:Record<string,Gemeinde>={},access:Access={},verifiedAccess:Access={},rows:TravelRows=[],results:RankedResult[]=[],breakdowns:Record<string,TaxBreakdown>={};
let map:ReturnType<typeof createMap>|null=null,revision=0,travelReady=false;
let preview:AarauPreview|null=null,previewData:AdaptedAarauPreview|null=null,transferWitness:TransferWitness|null=null,directOnly=false;
let observedRoutes:ObservedRoutes|null=null;
let workplaces:Record<string,Gemeinde>={};
let reviewCantons:ReadonlySet<string>=QUARANTINED_CANTONS;
const travelCache=new Map<number,Promise<TravelRows>>();
function clearPresentedResults(){
 rows=[];results=[];breakdowns={};access={};
 renderList($<HTMLTableSectionElement>('ranked-list'),[],null,selectGemeinde);
 $('cheapest').textContent='';$('summary').textContent=s.loading;$('profile-status').textContent=s.loading;
 $('data-status').textContent='';$('data-status').classList.remove('error');$('empty-state').hidden=true;
 $('detail').textContent=s.selectDetail;
 map?.update([],state.workplace,state.selected,observedRoutes||state.workplace===preview?.destinationBfs?QUARANTINED_CANTONS:reviewCantons);
}
function showError(error:unknown){$('summary').textContent=s.loadFailureSummary;$('data-status').textContent=s.loadError(error instanceof Error?error.message:String(error));$('data-status').classList.add('error');}
function selectGemeinde(id:number){
 if(!gemeinden[id]){$('detail').textContent=s.noData;return;}
 state.selected=id;
 $<HTMLInputElement>('residence').value=gemeinden[id][0];
 const indicative=!!observedRoutes||preview?.destinationBfs===state.workplace,activeReview=indicative?QUARANTINED_CANTONS:reviewCantons,witnessed=!!rows.find(row=>row[0]===id);
 const notice=observedRoutes?(directOnly?s.observedDirectWarning:s.observedWarning):(directOnly?s.indicativeDirectWarning:s.indicativeWarning);
 renderDetail($('detail'),gemeinden[id],id,witnessed||!indicative?breakdowns[id]??null:null,access[id],results.find(r=>r.id===id),rows.find(r=>r[0]===id)?.[1],travelReady,activeReview.has(gemeinden[id][1]),indicative,notice);
 map?.update(results,state.workplace,state.selected,activeReview);
 for(const row of $('ranked-list').querySelectorAll('tr'))row.classList.toggle('selected',row.getAttribute('data-bfs')===String(id));
}
async function loadRows(workplace:number):Promise<TravelRows>{
 if(verifiedAccess[workplace]==null)return [];
 if(!travelCache.has(workplace))travelCache.set(workplace,repository.json<{to:number;rows:TravelRows}>(`travel/to/${workplace}.json`).then(data=>{
  if(data.to!==workplace||!Array.isArray(data.rows)||!data.rows.some(row=>row[0]===workplace&&row[1]===0))throw new Error(s.invalidTravel);
  const seen=new Set<number>();let previous=-1;
  for(const row of data.rows){if(!Array.isArray(row)||row.length!==2||!Number.isInteger(row[0])||!gemeinden[row[0]]||!Number.isFinite(row[1])||row[1]<0||row[1]>60||row[1]<previous||seen.has(row[0]))throw new Error(s.invalidTravel);previous=row[1];seen.add(row[0]);}
  return data.rows;
 }).catch(error=>{travelCache.delete(workplace);throw error;}));
 return travelCache.get(workplace)!;
}
async function update(){
 const current=++revision,snapshot={...state};
 const all19=!!observedRoutes,legacyAarau=!all19&&preview?.destinationBfs===snapshot.workplace;
 const indicative=all19||legacyAarau,available=travelReady||indicative,activeReview=indicative?QUARANTINED_CANTONS:reviewCantons;
 $('time-value').textContent=`${state.maxTime} ${s.minutes}`;$('walk-value').textContent=`${state.maxWalk} ${s.minutes}`;
 if(!DATA_RELEASE.availability.tax){$('summary').textContent=s.taxPending;$('data-status').textContent=s.pending;return;}
 try{
  $('profile-status').textContent=s.loading;
  const adapted=all19?adaptObservedRoutes(observedRoutes!,snapshot.workplace,directOnly):legacyAarau?previewData!:null;
  const [profile,newRows]=await Promise.all([repository.loadProfile(snapshot.civ,snapshot.kids),adapted?Promise.resolve(adapted.rows):travelReady?loadRows(snapshot.workplace):Promise.resolve([] as TravelRows)]);
  if(current!==revision)return;
  $('profile-status').textContent=(indicative?s.profileLoadedIndicative:s.profileLoaded)(snapshot.civ==='m'?s.married:s.single,snapshot.kids===3?'3+':String(snapshot.kids),formatCHF(snapshot.income),s[snapshot.church]);
  rows=newRows;breakdowns={};const totals:Record<string,number>={};
  for(const [id,g] of Object.entries(gemeinden)){if(activeReview.has(g[1]))continue;const tax=calculateTax(profile,g,snapshot.income,snapshot.church);breakdowns[id]=tax;totals[id]=tax.total;}
  access=adapted?adapted.access:verifiedAccess;results=filterAndRank(gemeinden,access,rows,snapshot,totals,activeReview);
  const workplaceName=workplaces[snapshot.workplace]?.[0]??s.workplace;
  $('summary').textContent=all19?(directOnly?s.directObservedOverview:s.observedOverview)(results.length,workplaceName,snapshot.maxTime):legacyAarau?(directOnly?s.directPreviewOverview:s.previewOverview)(results.length,snapshot.maxTime):s.reachabilityOverview(available,results.length,workplaceName,snapshot.maxTime,snapshot.maxWalk,Object.keys(gemeinden).length);$('cheapest').textContent=results[0]?(indicative?s.cheapestPreview:s.cheapest)(results[0].name,formatCHF(results[0].total)):'';
  $('result-notice').textContent=all19?(directOnly?s.observedDirectWarning:s.observedWarning):legacyAarau?(directOnly?s.indicativeDirectWarning:s.indicativeWarning):s.unverified;
  $('data-status').classList.remove('error');$('data-status').textContent=!available?s.travelPending:!indicative&&access[snapshot.workplace]==null?s.noStop:'';
  $('empty-state').textContent=indicative?s.observedEmpty:s.empty;$('empty-state').hidden=!available||results.length>0;
  renderList($<HTMLTableSectionElement>('ranked-list'),results,state.selected,selectGemeinde);
  map?.update(results,state.workplace,state.selected,activeReview);
  if(state.selected!==null)selectGemeinde(state.selected);
 }catch(error){if(current===revision){clearPresentedResults();showError(error);}}
}
function chooseWorkplace(id:number){if(!workplaces[id])return;state.workplace=id;state.selected=id;clearPresentedResults();void update();}
installMunicipalitySearch($<HTMLInputElement>('workplace'),$('workplace-options'),()=>workplaces,()=>workplaces[state.workplace]?.[0]??'',chooseWorkplace);
installMunicipalitySearch($<HTMLInputElement>('residence'),$('residence-options'),()=>gemeinden,()=>gemeinden[state.selected??state.workplace]?.[0]??'',selectGemeinde);
for(const [id,key] of [['max-time','maxTime'],['max-walk','maxWalk']] as const)$<HTMLInputElement>(id).addEventListener('input',e=>{state[key]=Number((e.target as HTMLInputElement).value);void update();});
$('count-walk').addEventListener('change',e=>{state.countWalk=(e.target as HTMLInputElement).checked;void update();});
$<HTMLInputElement>('direct-only').addEventListener('change',e=>{directOnly=(e.target as HTMLInputElement).checked;if(!observedRoutes&&preview&&transferWitness)previewData=adaptObservedAarau(preview,transferWitness,directOnly);void update();});
function setIncome(raw:number){if(!Number.isFinite(raw)){showError(new Error(s.invalidIncome));return;}const income=Math.min(500000,Math.max(40000,raw));state.income=income;$<HTMLInputElement>('income').value=String(income);$<HTMLInputElement>('income-slider').value=String(income);$('clamp-note').hidden=income===raw;void update();}
$('income').addEventListener('change',e=>setIncome(Number((e.target as HTMLInputElement).value)));$('income-slider').addEventListener('input',e=>setIncome(Number((e.target as HTMLInputElement).value)));
$('civil').addEventListener('change',e=>{state.civ=(e.target as HTMLSelectElement).value as 's'|'m';void update();});$('kids').addEventListener('change',e=>{state.kids=Number((e.target as HTMLSelectElement).value);void update();});$('church').addEventListener('change',e=>{state.church=(e.target as HTMLSelectElement).value as typeof state.church;void update();});
$('theme').onclick=()=>{const dark=document.documentElement.dataset.theme==='dark'||(!document.documentElement.dataset.theme&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.dataset.theme=dark?'light':'dark';};
async function init(){
 if(!DATA_RELEASE.availability.tax){void update();return;}
 try{
  gemeinden=await repository.loadGemeinden();
  workplaces=workplaceGemeinden(gemeinden);
  const coverage=document.createElement('p');coverage.dataset.testid='candidate-coverage';coverage.className='assumptions';coverage.textContent=s.coverage(Object.keys(gemeinden).length,Object.keys(workplaces).length);coverage.dataset.residences=String(Object.keys(gemeinden).length);coverage.dataset.workplaces=String(Object.keys(workplaces).length);$('profile-status').after(coverage);
  reviewCantons=withheldCantons(Object.values(gemeinden).map(g=>g[1]),!!DATA_RELEASE.approvals.estv,QUARANTINED_CANTONS);
  if(DATA_RELEASE.availability.map){const topology=await repository.json<any>('map/switzerland-2026.json');map=createMap($('map'),topology,gemeinden,selectGemeinde);}
  observedRoutes=await loadObservedRoutes(repository,DATA_RELEASE,gemeinden);
  if(!observedRoutes){preview=await loadAarauPreview(repository,DATA_RELEASE,gemeinden);if(preview){transferWitness=await loadTransferWitness(repository,DATA_RELEASE,gemeinden);previewData=adaptObservedAarau(preview,transferWitness,directOnly);}}
  if(DATA_RELEASE.availability.travel){const [a,meta]=await Promise.all([repository.json<{gemeinden:Access}>('travel/access.json'),repository.json<{fixture?:boolean}>('travel/meta.json')]);
   if(!a.gemeinden)throw new Error(s.invalidTravel);
   for(const id of Object.keys(gemeinden)){const stop=a.gemeinden[id];if(stop!==null&&(!Array.isArray(stop)||stop.length!==3||typeof stop[0]!=='string'||typeof stop[1]!=='string'||!Number.isFinite(stop[2])||stop[2]<0||stop[2]>60))throw new Error(s.invalidTravel);}
   verifiedAccess=a.gemeinden;access=verifiedAccess;travelReady=true;if(meta.fixture)document.querySelector('[data-testid=release-status]')!.textContent=s.fixture;
  }
  state.selected=state.workplace;await update();
 }catch(error){clearPresentedResults();showError(error);}
}
void init();
