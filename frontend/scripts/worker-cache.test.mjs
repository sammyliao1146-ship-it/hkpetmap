import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/worker.js';

function harness(makeResponse=()=>Response.json({items:['public']},{headers:{'Cache-Control':'public, s-maxage=300','ETag':'"rev1"'}})) {
  const rows=new Map(),pending=[];let upstream=0;
  globalThis.caches={default:{async match(req){return rows.get(req.url)?.clone()},async put(req,res){rows.set(req.url,res)}}};
  globalThis.fetch=async()=>{upstream++;return makeResponse()};
  const ctx={waitUntil(p){pending.push(p)}};
  return {async get(path,init){const result=await worker.fetch(new Request('https://hkpetmap.com'+path,init),{},ctx);await Promise.all(pending);return result},count:()=>upstream,rows};
}

test('public GET is reused, query/language keys stay distinct and validators return 304',async()=>{
  const h=harness();await h.get('/api/v1/catalog');await h.get('/api/v1/catalog');assert.equal(h.count(),1);
  const r=await h.get('/api/v1/catalog',{headers:{'If-None-Match':'"rev1"'}});assert.equal(r.status,304);
  await h.get('/api/v1/catalog?v=new');assert.equal(h.count(),2);
  await h.get('/api/v1/parking?language=en');await h.get('/api/v1/parking?language=zh-Hant');assert.equal(h.count(),4);
});

test('authenticated, cookie, location, mixed-Google and personal endpoints always bypass',async()=>{
  const h=harness();
  for(const [path,init] of [
    ['/api/v1/catalog',{headers:{Authorization:'Bearer private'}}],
    ['/api/v1/catalog',{headers:{Cookie:'session=private'}}],
    ['/api/v1/parking?latitude=22.3&longitude=114.1',{}],
    ['/api/v1/place-summaries',{}],['/api/v1/places/restaurant:1',{}],
    ['/api/v1/assistant/conversations/session1',{}],
    ['/api/v1/plans',{method:'POST'}],['/api/v1/assistant/chat/stream',{method:'POST'}]]){
    const n=h.count();await h.get(path,init);await h.get(path,init);assert.equal(h.count(),n+2);
  }
  assert.equal(h.rows.size,0);
});

test('errors, private responses and cookies are never cached',async()=>{
  for(const make of [()=>new Response('bad',{status:502}),
    ()=>Response.json({secret:true},{headers:{'Cache-Control':'private, no-store'}}),
    ()=>Response.json({secret:true},{headers:{'Set-Cookie':'session=private'}})]){
    const h=harness(make);await h.get('/api/v1/catalog');await h.get('/api/v1/catalog');assert.equal(h.count(),2);assert.equal(h.rows.size,0);
  }
});
