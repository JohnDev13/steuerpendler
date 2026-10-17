import type { Church, CivilStatus, Gemeinde } from './tax';
export interface AppState {workplace:number;maxTime:number;maxWalk:number;countWalk:boolean;income:number;civ:CivilStatus;kids:number;church:Church;selected:number|null}
export const initialState: AppState={workplace:261,maxTime:25,maxWalk:10,countWalk:false,income:120000,civ:'s',kids:0,church:'none',selected:null};
export function foldName(text:string):string {return text.normalize('NFD').replace(/\p{M}/gu,'').toLocaleLowerCase('de-CH').trim();}
export function searchGemeinden(gemeinden:Record<string,Gemeinde>,query:string):number[] {
 const q=foldName(query);
 return Object.keys(gemeinden).map(Number).filter(id=>foldName(gemeinden[id][0]).includes(q)).sort((a,b)=>Number(foldName(gemeinden[b][0])===q)-Number(foldName(gemeinden[a][0])===q)||gemeinden[a][0].localeCompare(gemeinden[b][0],'de-CH')).slice(0,12);
}
