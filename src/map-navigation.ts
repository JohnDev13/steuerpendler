import { strings as s } from './strings';
export const navigationLabels={zoomIn:s.mapZoomIn,zoomOut:s.mapZoomOut,reset:s.mapReset,help:s.mapNavigationHelp};
export function createMapNavigation(svg:SVGSVGElement,container:HTMLElement){
 const width=960,height=560,maxZoom=16;
 let x=0,y=0,zoom=1;
 const controls=document.createElement('div');controls.className='map-navigation';controls.setAttribute('role','group');controls.setAttribute('aria-label',s.mapNavigation);
 const button=(text:string,label:string,action:()=>void)=>{const b=document.createElement('button');b.type='button';b.textContent=text;b.setAttribute('aria-label',label);b.onclick=action;controls.append(b);return b;};
 const render=()=>{x=Math.max(0,Math.min(width-width/zoom,x));y=Math.max(0,Math.min(height-height/zoom,y));svg.setAttribute('viewBox',`${x} ${y} ${width/zoom} ${height/zoom}`);plus.disabled=zoom>=maxZoom;minus.disabled=zoom<=1;reset.disabled=zoom===1;};
 const scale=(factor:number,ax=width/2,ay=height/2)=>{const next=Math.max(1,Math.min(maxZoom,zoom*factor));x+=ax/zoom-ax/next;y+=ay/zoom-ay/next;zoom=next;render();};
 const resetView=()=>{x=0;y=0;zoom=1;render();};
 const plus=button('+',navigationLabels.zoomIn,()=>scale(1.5));
 const minus=button('−',navigationLabels.zoomOut,()=>scale(1/1.5));
 const reset=button(s.mapResetButton,navigationLabels.reset,resetView);
 svg.setAttribute('tabindex','0');svg.setAttribute('aria-description',navigationLabels.help);
 svg.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){e.preventDefault();scale(1.5);}else if(e.key==='-'||e.key==='−'){e.preventDefault();scale(1/1.5);}else if(e.key==='0'||e.key==='Home'){e.preventDefault();resetView();}});
 // Translate client coordinates using the actual SVG CTM (including letterboxing).
 const point=(cx:number,cy:number)=>{const matrix=svg.getScreenCTM();if(!matrix)return {x:width/2,y:height/2};const p=new DOMPoint(cx,cy).matrixTransform(matrix.inverse());return {x:(p.x-x)*zoom,y:(p.y-y)*zoom};};
 svg.addEventListener('wheel',e=>{e.preventDefault();const p=point(e.clientX,e.clientY);scale(Math.exp(-Math.max(-600,Math.min(600,e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?560:1)))*.002),p.x,p.y);},{passive:false});
 const pointers=new Map<number,{x:number;y:number;startX:number;startY:number}>();
 let suppressUntil=0,gestureMoved=false;
 // Capture on the original hit path, not the parent SVG: otherwise a plain click
 // is retargeted to the SVG and municipality selection never receives it.
 svg.addEventListener('pointerdown',e=>{if(e.pointerType==='mouse'&&e.button!==0)return;if(!pointers.size){gestureMoved=false;suppressUntil=0;}pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY});(e.target as Element).setPointerCapture(e.pointerId);svg.classList.add('is-panning');if(pointers.size>1)gestureMoved=true;});
 svg.addEventListener('pointermove',e=>{const previous=pointers.get(e.pointerId);if(!previous)return;
  const before=[...pointers.values()];const mid=before.length>=2?{x:(before[0].x+before[1].x)/2,y:(before[0].y+before[1].y)/2}:previous;
  const anchor=point(mid.x,mid.y);const distance=before.length>=2?Math.hypot(before[0].x-before[1].x,before[0].y-before[1].y):0;
  if(Math.hypot(e.clientX-previous.startX,e.clientY-previous.startY)>4)gestureMoved=true;
  pointers.set(e.pointerId,{...previous,x:e.clientX,y:e.clientY});const after=[...pointers.values()];
  const nextMid=after.length>=2?{x:(after[0].x+after[1].x)/2,y:(after[0].y+after[1].y)/2}:after[0];
  if(distance>0)scale(Math.hypot(after[0].x-after[1].x,after[0].y-after[1].y)/distance,anchor.x,anchor.y);
  const shifted=point(nextMid.x,nextMid.y),old=point(mid.x,mid.y);x-=(shifted.x-old.x)/zoom;y-=(shifted.y-old.y)/zoom;render();
 });
 const release=(e:PointerEvent)=>{if(!pointers.delete(e.pointerId))return;if(!pointers.size){if(gestureMoved)suppressUntil=performance.now()+500;gestureMoved=false;svg.classList.remove('is-panning');}};
 svg.addEventListener('pointerup',release);svg.addEventListener('pointercancel',release);svg.addEventListener('lostpointercapture',release);
 svg.addEventListener('click',e=>{if(e.detail>0&&(gestureMoved||performance.now()<suppressUntil)){e.preventDefault();e.stopImmediatePropagation();}},true);
 container.append(controls);render();
 return {reset:resetView};
}
