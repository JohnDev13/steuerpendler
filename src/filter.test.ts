import { expect, it } from 'vitest';
// Synthetic fixtures only: not Swiss commute or tax references.
it('distinguishes reachable homes with withheld tax from an empty commute result',async()=>{
 const module=await import('./filter') as any;
 expect(typeof module.summarizeReachability).toBe('function');
 const options={maxTime:20,maxWalk:15,countWalk:false,workplace:1};
 const gs={'1':['Work','AG',100,100,0,0],'2':['Neighbour','SO',100,100,0,0],'3':['Far','ZH',100,100,0,0]} as const;
 const acc={'1':['one','One',15],'2':['two','Two',10],'3':['three','Three',16]} as const;
 expect(module.summarizeReachability(gs,acc,[[1,0],[2,20],[3,10]],options,new Set(['AG','SO']))).toEqual({reachable:2,underReview:2});
 expect(module.summarizeReachability(gs,acc,[[1,0],[2,20],[3,10]],{...options,countWalk:true},new Set(['AG','SO']))).toEqual({reachable:1,underReview:1});
 expect(module.summarizeReachability(gs,acc,[],options,new Set(['AG','SO']))).toEqual({reachable:0,underReview:0});
});
it('provides distinct UI labels for partly and wholly withheld reachable Gemeinden',async()=>{
 const {strings}=await import('./strings');
 expect(strings.reviewReachable(1)).toBe('1 erreichbare Gemeinde: Daten werden geprüft.');
 expect(strings.reviewReachable(2)).toBe('2 erreichbare Gemeinden: Daten werden geprüft.');
 expect(strings.allReachableUnderReview(2)).toBe('Für alle 2 erreichbaren Gemeinden werden die Daten geprüft.');
});
const gemeinden={'1':['Alpha','ZH',100,100,0,0],'2':['Beta','ZH',100,100,0,0],'3':['Gamma','VS',100,100,0,0]} as const;
const access={'1':['one','One',10],'2':['two','Two',2],'3':null} as const;
it('applies the exact walk-toggle rule including the zero-time workplace',async()=>{
 const module=await import('./filter').catch(()=>({} as Record<string,unknown>));
 expect(typeof module.filterAndRank).toBe('function');
 const run=module.filterAndRank as any;
 const rows=[[1,0],[2,4],[3,1]];
 const options={maxTime:5,maxWalk:10,countWalk:false,workplace:1};
 expect(run(gemeinden,access,rows,options,{'1':200,'2':100,'3':50},new Set()).map((r:any)=>r.id)).toEqual([2,1]);
 expect(run(gemeinden,access,rows,{...options,countWalk:true},{'1':200,'2':100,'3':50},new Set())).toEqual([]);
});
it('sorts unrounded totals then minutes then name with deterministic ranks',async()=>{
 const {filterAndRank}=await import('./filter');
 const gs={...gemeinden,'4':['Aardvark','ZH',100,100,0,0] as const};
 const acc={...access,'3':['three','Three',0] as const,'4':['four','Four',0] as const};
 const result=filterAndRank(gs,acc,[[1,4],[2,3],[3,3],[4,3]],{maxTime:10,maxWalk:10,countWalk:false,workplace:1},{1:100,2:100,3:100.01,4:100});
 expect(result.map(r=>r.id)).toEqual([4,2,1,3]);
 expect(result.map(r=>r.rank)).toEqual([1,2,3,4]);
});
it('excludes quarantined cantons and suppresses a quarantined workplace baseline',async()=>{
 const {filterAndRank}=await import('./filter');
 const result=filterAndRank(gemeinden,{...access,'3':['three','Three',0]},[[1,0],[2,1],[3,2]],{maxTime:5,maxWalk:10,countWalk:false,workplace:3},{1:200,2:100,3:50},new Set(['VS']));
 expect(result.map(r=>r.id)).toEqual([2,1]);
 expect(result.every(r=>r.delta===null)).toBe(true);
});
it('forms five equal-count groups including small and empty result sets',async()=>{
 const {filterAndRank}=await import('./filter');
 for(const n of [0,1,2,4,5,6,23]){
  const gs:Record<string,any>={},acc:Record<string,any>={},totals:Record<string,number>={},rows:[number,number][]=[];
  for(let i=1;i<=n;i++){gs[i]=['Synthetic '+i,'ZH',100,100,0,0];acc[i]=['stop','Stop',0];totals[i]=i;rows.push([i,0]);}
  const result=filterAndRank(gs,acc,rows,{maxTime:5,maxWalk:0,countWalk:false,workplace:1},totals);
  const counts=Array.from({length:5},(_,i)=>result.filter(r=>r.colorGroup===i).length);
  expect(Math.max(...counts)-Math.min(...counts)).toBeLessThanOrEqual(1);
  expect(result).toHaveLength(n);
 }
});
it('places surplus quantile members in the first groups',async()=>{
 const {filterAndRank}=await import('./filter');
 const gs:Record<string,any>={},acc:Record<string,any>={},totals:Record<string,number>={},rows:[number,number][]=[];
 for(let i=1;i<=7;i++){gs[i]=['Synthetic '+i,'ZH',100,100,0,0];acc[i]=['stop','Stop',0];totals[i]=i;rows.push([i,0]);}
 expect(filterAndRank(gs,acc,rows,{maxTime:5,maxWalk:0,countWalk:false,workplace:1},totals).map(r=>r.colorGroup)).toEqual([0,0,1,1,2,3,4]);
});
