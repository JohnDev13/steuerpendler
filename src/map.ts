import { geoIdentity, geoMercator, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import type { Gemeinde } from './tax';
import type { RankedResult } from './filter';
import { COLOURS } from './config';
import { strings as s } from './strings';
import { createMapNavigation } from './map-navigation';
import './map-navigation.css';
const NS='http://www.w3.org/2000/svg';
export function createMap(container:HTMLElement,topology:any,gemeinden:Record<string,Gemeinde>,onSelect:(id:number)=>void){
 const municipalities=feature(topology,topology.objects.gemeinden) as any;
 const coordinates=municipalities.features[0]?.geometry.coordinates.flat(Infinity) as number[];
 const projected=coordinates?.some(n=>Math.abs(n)>180);
 const projection=projected?geoIdentity().reflectY(true).fitExtent([[15,15],[945,545]],municipalities):geoMercator().fitExtent([[15,15],[945,545]],municipalities);
 const path=geoPath(projection as any),svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox','0 0 960 560');svg.setAttribute('aria-label',s.map);svg.setAttribute('role','group');
 const shapes=new Map<number,SVGPathElement>(),features=new Map<number,any>();
 for(const f of municipalities.features){const id=Number(f.id),p=document.createElementNS(NS,'path');p.setAttribute('d',path(f)||'');p.dataset.bfs=String(id);p.classList.add('municipality');p.setAttribute('aria-label',gemeinden[id]?.[0]||s.noData);p.setAttribute('role','button');p.setAttribute('tabindex','-1');const title=document.createElementNS(NS,'title');title.textContent=gemeinden[id]?.[0]||s.noData;p.append(title);p.onclick=()=>onSelect(id);p.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(id);}else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();const ids=[...shapes.keys()].filter(key=>gemeinden[key]);const current=ids.indexOf(id),next=ids[(current+(e.key==='ArrowLeft'||e.key==='ArrowUp'?-1:1)+ids.length)%ids.length];shapes.get(next)?.focus();onSelect(next);}};svg.append(p);shapes.set(id,p);features.set(id,f);}
 for(const key of ['lakes','cantons']){const object=topology.objects[key];if(!object)continue;const p=document.createElementNS(NS,'path');p.setAttribute('d',path(feature(topology,object) as any)||'');p.classList.add(key);p.setAttribute('pointer-events','none');svg.append(p);}
 const labels=document.createElementNS(NS,'g');labels.classList.add('map-labels');svg.append(labels);container.replaceChildren(svg);
 const navigation=createMapNavigation(svg,container);
 return {reset:navigation.reset,update(results:RankedResult[],workplace:number,selected:number|null,review:ReadonlySet<string>){
  const byId=new Map(results.map(r=>[r.id,r]));
  for(const [id,p] of shapes){const row=byId.get(id),underReview=gemeinden[id]&&review.has(gemeinden[id][1]);p.style.fill=row?COLOURS[row.colorGroup]:'';p.classList.toggle('workplace',id===workplace);p.classList.toggle('selected',id===selected);p.classList.toggle('under-review',!!underReview);p.setAttribute('tabindex',id===(selected??workplace)?'0':'-1');}
  labels.replaceChildren();
  for(const row of results.slice(0,10)){const f=features.get(row.id);if(!f)continue;const [x,y]=path.centroid(f);if(!Number.isFinite(x)||!Number.isFinite(y))continue;const t=document.createElementNS(NS,'text');t.setAttribute('x',String(x));t.setAttribute('y',String(y));t.textContent=String(row.rank);labels.append(t);}
  // Data and selection updates never overwrite the user-controlled viewport.
 }};
}
