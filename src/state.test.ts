import { expect, it } from 'vitest';
import { searchGemeinden, foldName } from './state';
it('matches Gemeinde names without accents and prioritizes the exact name',()=>{
 const g={'261':['Zürich','ZH',0,0,0,0],'351':['Bern','BE',0,0,0,0],'352':['Bernex','GE',0,0,0,0]} as const;
 expect(searchGemeinden(g,'zurich')).toEqual([261]);
 expect(searchGemeinden(g,'BERN')).toEqual([351,352]);
 expect(foldName(' Genève ')).toBe('geneve');
});
