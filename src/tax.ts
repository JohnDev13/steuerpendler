export type CivilStatus = 's' | 'm';
export type Church = 'none' | 'reformed' | 'catholic';
export type Gemeinde = readonly [name:string,canton:string,rateCanton:number,rateGemeinde:number,rateReformed:number,rateCatholic:number];
export interface TaxProfile {meta:{year:number;incomes:{from:number;step:number;count:number};[key:string]:unknown};cantons:Record<string,number[][]>}
export interface TaxBreakdown {bund:number;kanton:number;gemeinde:number;kirche:number;personal:number;total:number;income:number;clamped:boolean}
export function calculateTax(profile:TaxProfile,g:Gemeinde,income:number,church:Church):TaxBreakdown {
 if (!Number.isFinite(income)) throw new Error('Ungültiges Einkommen.');
 const clampedIncome=Math.min(500000,Math.max(40000,income));
 const x=(clampedIncome-40000)/1000;
 const i=Math.min(Math.floor(x),459),t=x-i;
 const table=profile.cantons[g[1]];
 if (!table || !table[i] || !table[i+1]) throw new Error('Steuertabelle für diesen Kanton fehlt.');
 const row=table[i].map((v,k)=>v+(table[i+1][k]-v)*t);
 const rate=church==='reformed'?g[4]:church==='catholic'?g[5]:0;
 const bund=row[0],kanton=row[1]*g[2]/100,gemeinde=row[1]*g[3]/100,kirche=row[1]*rate/100,personal=row[2];
 const total=bund+kanton+gemeinde+kirche+personal;
 if(!Number.isFinite(total)) throw new Error('Steuerdaten sind unvollständig.');
 return {bund,kanton,gemeinde,kirche,personal,total,income:clampedIncome,clamped:income!==clampedIncome};
}
export type Fetcher = (url:string)=>Promise<Response>;
export interface FileDigest {sha256:string;bytes?:number}
export async function fetchJSON<T>(url:string,fetcher:Fetcher=fetch,expected?:FileDigest):Promise<T> {
 const response=await fetcher(url);
 if(!response.ok) throw new Error(`Daten nicht verfügbar (HTTP ${response.status}).`);
 if(!response.headers.get('content-type')?.includes('application/json')) throw new Error('Die angeforderte Datei enthält keine JSON-Daten.');
 const bytes=await response.arrayBuffer();
 if(expected){
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
  if(digest!==expected.sha256||(expected.bytes!==undefined&&bytes.byteLength!==expected.bytes))throw new Error('Die Datenversion stimmt nicht überein. Bitte lade die Seite neu.');
 }
 try {return JSON.parse(new TextDecoder().decode(bytes)) as T;} catch {throw new Error('Die Datendatei ist beschädigt.');}
}
export class TaxRepository {
 private pending=new Map<string,Promise<unknown>>();
 constructor(private fetcher:Fetcher=fetch,private base='/data',private release='',private files?:Record<string,FileDigest>){}
 url(path:string):string {return `${this.base}/${path}${this.release?`?v=${encodeURIComponent(this.release)}`:''}`;}
 async json<T>(path:string):Promise<T> {
  if(this.files&&!this.files[path])throw new Error('Diese Datendatei gehört nicht zur geladenen Datenversion.');
  return fetchJSON<T>(this.url(path),this.fetcher,this.files?.[path]);
 }
 private once<T>(path:string,validate:(data:unknown)=>T):Promise<T> {
  if(!this.pending.has(path)) {
   const result=this.json<unknown>(path).then(validate).catch(error=>{this.pending.delete(path);throw error;});
   this.pending.set(path,result);
  }
  return this.pending.get(path) as Promise<T>;
 }
 loadGemeinden():Promise<Record<string,Gemeinde>> {
  return this.once('gemeinden-2026.json',data=>{
   const values=(data as {gemeinden?:Record<string,unknown>})?.gemeinden;
   if(!values||!Object.keys(values).length) throw new Error('Gemeindedaten fehlen.');
   for(const [id,row] of Object.entries(values)) if(!/^\d+$/.test(id)||!Array.isArray(row)||row.length!==6||typeof row[0]!=='string'||typeof row[1]!=='string'||!row.slice(2).every(Number.isFinite)) throw new Error('Ungültiges Gemeindeformat.');
   return values as Record<string,Gemeinde>;
  });
 }
 loadProfile(civ:CivilStatus,kids:number):Promise<TaxProfile> {
  if(!['s','m'].includes(civ)||!Number.isInteger(kids)||kids<0||kids>3) return Promise.reject(new Error('Ungültiges Steuerprofil.'));
  return this.once(`tax-2026-${civ}-${kids}.json`,data=>{
   const p=data as TaxProfile;
   if(p?.meta?.year!==2026||p.meta.incomes?.from!==40000||p.meta.incomes.step!==1000||p.meta.incomes.count!==461||!p.cantons||!Object.keys(p.cantons).length) throw new Error('Ungültige Steuertabelle.');
   for(const rows of Object.values(p.cantons)) if(!Array.isArray(rows)||rows.length!==461||rows.some(row=>!Array.isArray(row)||row.length!==3||!row.every(Number.isFinite))) throw new Error('Steuerdaten sind unvollständig.');
   return p;
  });
 }
}
