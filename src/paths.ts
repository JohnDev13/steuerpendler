export function sitePath(path:string,base:string=import.meta.env.BASE_URL):string {
 return `${base.endsWith('/')?base:base+'/'}${path.replace(/^\/+/, '')}`;
}
