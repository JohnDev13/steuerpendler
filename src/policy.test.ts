import {expect,it,vi} from 'vitest';
import {withheldCantons} from './policy';
it('withholds every unverified canton in a public preview, without marking suspicion as official failure',()=>{
 expect([...withheldCantons(['ZH','VS','ZH'],false,['VS'])].sort()).toEqual(['VS','ZH']);
 expect([...withheldCantons(['ZH','VS'],true,['VS'])]).toEqual(['VS']);
});
it('always quarantines both known-problem cantons even when global approval is true',async()=>{
 vi.stubGlobal('__DATA_RELEASE__',{});
 const {QUARANTINED_CANTONS}=await import('./config');
 expect([...withheldCantons(['ZH','JU','VS','VD','GE'],true,QUARANTINED_CANTONS)].sort()).toEqual(['GE','JU','VD','VS']);
 vi.unstubAllGlobals();
});
