import {createServer} from 'node:http';
import {readFileSync,existsSync,statSync} from 'node:fs';
import {resolve,extname,sep} from 'node:path';
const root=resolve(process.env.STATIC_ROOT||'dist'),base=process.env.PAGES_BASE||'/';
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.txt':'text/plain; charset=utf-8'};
// Local verification only. GitHub Pages serves production files; this server is never deployed.
createServer((req,res)=>{
 try {
  const url=new URL(req.url,'http://localhost'),path=decodeURIComponent(url.pathname);
  if(!['GET','HEAD'].includes(req.method)){res.writeHead(405);res.end();return;}
  const target=path.startsWith(base)?resolve(root,path.slice(base.length)||'index.html'):'';
  let file=target;
  if(file&&existsSync(file)&&statSync(file).isDirectory())file=resolve(file,'index.html');
  const allowed=file&&(file===root||file.startsWith(root+sep))&&existsSync(file)&&statSync(file).isFile();
  if(!allowed){res.writeHead(404,{'Content-Type':'text/html; charset=utf-8'});res.end(req.method==='HEAD'?'':readFileSync(resolve(root,'404.html')));return;}
  const bytes=readFileSync(file);res.writeHead(200,{'Content-Type':types[extname(file)]||'application/octet-stream','Content-Length':bytes.length,'Cache-Control':'no-cache'});res.end(req.method==='HEAD'?'':bytes);
 }catch{res.writeHead(400);res.end('Bad request');}
}).listen(Number(process.env.PORT||4173),'127.0.0.1',()=>console.log(`Static build ready at http://127.0.0.1:${process.env.PORT||4173}${base}`));
