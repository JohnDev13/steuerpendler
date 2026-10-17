import { searchGemeinden } from './state';
import type { Gemeinde } from './tax';
/** Separate candidate sources prevent the workplace subset from restricting homes. */
export function installMunicipalitySearch(input:HTMLInputElement,list:HTMLElement,candidates:()=>Readonly<Record<string,Gemeinde>>,selectedName:()=>string,onSelect:(id:number)=>void){
 let ids:number[]=[],active=-1;
 list.classList.add('municipality-options');
 const close=()=>{list.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');};
 const choose=(id:number)=>{const g=candidates()[id];if(!g)return;input.value=g[0];close();onSelect(id);};
 const show=()=>{
  ids=searchGemeinden(candidates(),input.value);active=-1;input.removeAttribute('aria-activedescendant');list.replaceChildren();
  for(const id of ids){
   const option=document.createElement('div');option.id=`${input.id}-option-${id}`;option.setAttribute('role','option');option.setAttribute('aria-selected','false');
   const g=candidates()[id];option.textContent=`${g[0]} (${g[1]})`;
   option.onpointerdown=e=>{if(e.pointerType==='mouse')e.preventDefault();};option.onmousedown=e=>e.preventDefault();option.onclick=()=>choose(id);list.append(option);
  }
  list.hidden=ids.length===0;input.setAttribute('aria-expanded',String(!list.hidden));
 };
 input.addEventListener('input',show);input.addEventListener('focus',show);
 input.addEventListener('blur',()=>{close();input.value=selectedName();});
 input.addEventListener('keydown',e=>{
  if(e.key==='Escape'){close();input.value=selectedName();return;}
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){
   e.preventDefault();if(list.hidden)show();if(!ids.length)return;
   active=active<0?(e.key==='ArrowDown'?0:ids.length-1):(active+(e.key==='ArrowDown'?1:-1)+ids.length)%ids.length;
   for(const el of list.children)el.setAttribute('aria-selected',String(el.id===`${input.id}-option-${ids[active]}`));
   input.setAttribute('aria-activedescendant',`${input.id}-option-${ids[active]}`);
  }
  if(e.key==='Enter'&&!list.hidden&&ids.length){e.preventDefault();choose(ids[Math.max(active,0)]);}
 });
}
