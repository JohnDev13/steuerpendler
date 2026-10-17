import { expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { workplaceGemeinden, DESTINATIONS } from './destinations';
import type { Gemeinde } from './tax';
const all:Record<string,Gemeinde>=JSON.parse(readFileSync('site/data/gemeinden-2026.json','utf8')).gemeinden;
it('limits workplaces to German-speaking cantonal capitals without narrowing residential coverage',()=>{
 const before=JSON.stringify(all),workplaces=workplaceGemeinden(all);
 expect(DESTINATIONS).toHaveLength(19);
 expect(Object.keys(workplaces)).toHaveLength(19);
 expect(workplaces[4001][0]).toBe('Aarau');
 expect(workplaces[230]).toBeUndefined(); // Winterthur is a residence, not a destination.
 expect(all[230][0]).toBe('Winterthur');
 expect(Object.keys(all)).toHaveLength(2110);
 expect(JSON.stringify(all)).toBe(before);
 expect(Object.values(all).some(g=>g[0]==='Lenzburg')).toBe(true);
 expect(Object.values(all).some(g=>g[0]==='Olten')).toBe(true);
});
