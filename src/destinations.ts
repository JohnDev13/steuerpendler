import type { Gemeinde } from './tax';
/** Workplace destinations only. Never use this subset as residential/tax coverage. */
export const DESTINATIONS = [
 {bfs:261,name:'Zürich',canton:'ZH'}, {bfs:351,name:'Bern',canton:'BE'},
 {bfs:1061,name:'Luzern',canton:'LU'}, {bfs:1201,name:'Altdorf (UR)',canton:'UR'},
 {bfs:1372,name:'Schwyz',canton:'SZ'}, {bfs:1407,name:'Sarnen',canton:'OW'},
 {bfs:1509,name:'Stans',canton:'NW'}, {bfs:1632,name:'Glarus',canton:'GL'},
 {bfs:1711,name:'Zug',canton:'ZG'}, {bfs:2601,name:'Solothurn',canton:'SO'},
 {bfs:2701,name:'Basel',canton:'BS'}, {bfs:2829,name:'Liestal',canton:'BL'},
 {bfs:2939,name:'Schaffhausen',canton:'SH'}, {bfs:3001,name:'Herisau',canton:'AR'},
 {bfs:3101,name:'Appenzell',canton:'AI'}, {bfs:3203,name:'St. Gallen',canton:'SG'},
 {bfs:3901,name:'Chur',canton:'GR'}, {bfs:4001,name:'Aarau',canton:'AG'},
 {bfs:4566,name:'Frauenfeld',canton:'TG'},
] as const;
export function workplaceGemeinden(all:Readonly<Record<string,Gemeinde>>):Record<string,Gemeinde>{
 const workplaces:Record<string,Gemeinde>={};
 for(const destination of DESTINATIONS){
  const g=all[destination.bfs];
  if(!g||g[0]!==destination.name||g[1]!==destination.canton)throw new Error(`Ungültiger Hauptort: BFS ${destination.bfs}.`);
  workplaces[destination.bfs]=g;
 }
 return workplaces;
}
