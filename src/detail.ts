import type { Gemeinde, TaxBreakdown } from './tax';
import type { Access, RankedResult } from './filter';
import { formatCHF } from './format';
import { strings as s } from './strings';
export function renderDetail(container:HTMLElement,g:Gemeinde,id:number,tax:TaxBreakdown|null,stop:Access[string]|undefined,result:RankedResult|undefined,minutes:number|undefined,travelAvailable:boolean,underReview:boolean,indicativePreview=false,indicativeNotice:string=s.indicativeWarning,matrix?:{maxTime:number;transfers:number|undefined},premium?:{amount:number;label:string}):void {
 const title=document.createElement('h2');title.textContent=`${g[0]} · ${g[1]}`;
 const status=document.createElement('p');status.className='detail-status';status.textContent=underReview?s.review:result?`${s.rank} ${result.rank}`:matrix?s.matrixNoRoute(matrix.maxTime):indicativePreview?s.previewUnknown:travelAvailable?s.outOfReach:s.travelUnknown;
 container.replaceChildren(title,status);
 if(!underReview&&tax){
  const dl=document.createElement('dl');
  for(const [label,value] of [[s.bund,tax.bund],[s.kanton,tax.kanton],[s.gemeinde,tax.gemeinde],[s.kirche,tax.kirche],[s.personal,tax.personal],...(tax.credit?[[s.credit,-tax.credit] as const]:[]),[s.total,tax.total],...(premium?[[premium.label,premium.amount] as const,[s.totalWithPremium,tax.total+premium.amount] as const]:[])] as const){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=formatCHF(value);dl.append(dt,dd);}
  container.append(dl);
 }
 const info=document.createElement('p');info.className='detail-meta';info.textContent=`${s.rate}: ${g[3]}% · BFS ${id}`;container.append(info);
 if(stop&&matrix){const p=document.createElement('p');p.textContent=`${s.matrixBoarding}: ${stop[1]}${minutes===undefined?'':` · ${s.travel}: ${minutes} ${s.minutes}`}${matrix.transfers===undefined?'':` · ${s.matrixTransfers(matrix.transfers)}`}`;container.append(p);}
 else if(stop){const p=document.createElement('p');p.textContent=indicativePreview?`${stop[1].startsWith('ch:')?s.boardingStopInGemeinde:`${s.boardingStop}: ${stop[1]}`} · ${s.unmeasuredAccess}${minutes===undefined?'':` · ${s.travel}: ${minutes} ${s.minutes}`}`:`${s.stop}: ${stop[1]} · ${s.walk}: ${stop[2]} ${s.minutes}${minutes===undefined?'':` · ${s.travel}: ${minutes} ${s.minutes}`}`;container.append(p);}
 const note=document.createElement('p');note.className='muted';note.textContent=indicativePreview?s.detailNote(indicativeNotice):s.disclaimer;container.append(note);
}
