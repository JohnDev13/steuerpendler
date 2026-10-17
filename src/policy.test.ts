import {expect,it} from 'vitest';
import {withheldCantons} from './policy';
it('withholds every unverified canton in a public preview, without marking suspicion as official failure',()=>{
 expect([...withheldCantons(['ZH','VS','ZH'],false,['VS'])].sort()).toEqual(['VS','ZH']);
 expect([...withheldCantons(['ZH','VS'],true,['VS'])]).toEqual(['VS']);
});
