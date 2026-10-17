import type { RankedResult } from './filter';
import { formatCHF } from './format';
import { strings as s } from './strings';
export function renderList(body:HTMLTableSectionElement,results:RankedResult[],selected:number|null,onSelect:(id:number)=>void):void {
 const fragment=document.createDocumentFragment();
 for(const result of results){
  const row=document.createElement('tr');row.dataset.bfs=String(result.id);row.classList.toggle('selected',selected===result.id);
  const rank=document.createElement('td');rank.dataset.label=s.rank;rank.textContent=String(result.rank);row.append(rank);
  const cell=document.createElement('td'),button=document.createElement('button');button.type='button';button.className='municipality-button';button.textContent=result.name;button.setAttribute('aria-label',s.resultButton(result.name));button.onclick=()=>onSelect(result.id);cell.append(button);row.append(cell);
  for(const text of [result.canton,`${result.minutes} ${s.minutes}`,`${result.walk} ${s.minutes}`,formatCHF(result.total),result.delta===null?'—':`${result.delta>0?'+':''}${formatCHF(result.delta)}`]){const td=document.createElement('td');td.textContent=text;row.append(td);}
  fragment.append(row);
 }
 body.replaceChildren(fragment);
}
