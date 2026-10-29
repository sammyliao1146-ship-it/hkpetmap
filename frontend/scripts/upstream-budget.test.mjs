import test from 'node:test';
import assert from 'node:assert/strict';
import {budgetedProxy} from '../src/upstream-budget.js';
const request=(path='/api/v1/assistant/chat/stream')=>new Request('https://hkpetmap.com'+path,{method:'POST',body:'{}'});

test('deadline includes a stalled SSE body after immediate headers; no partial draft escapes',async()=>{
  let cancelled=false;
  globalThis.fetch=async()=>new Response(new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('unapproved partial draft'));},cancel(){cancelled=true;}}),{headers:{'Content-Type':'text/event-stream'}});
  const started=performance.now();const r=await budgetedProxy(request(),'https://example.invalid',20);
  const text=await r.text();assert(performance.now()-started<300);assert(text.includes('edge-time-budget'));assert(!text.includes('unapproved'));assert(cancelled);
  assert.equal(r.headers.get('Cache-Control'),'private, no-store');
});

test('unresponsive origin is aborted and Plan returns a bounded explicit error',async()=>{
  let aborted=false;
  globalThis.fetch=async req=>new Promise((_,reject)=>{req.signal.addEventListener('abort',()=>{aborted=true;reject(new Error('aborted'));});});
  const r=await budgetedProxy(request('/api/v1/plans'),'https://example.invalid',20);
  assert.equal(r.status,504);assert(aborted);assert((await r.json()).detail.includes('time limit'));
});

test('successful complete body is preserved; oversized and failed origins disclose no diagnostics',async()=>{
  globalThis.fetch=async()=>Response.json({answer:'Complete',model:'saved-data'},{headers:{'Cache-Control':'private, no-store'}});
  const r=await budgetedProxy(request('/api/v1/assistant/chat'),'https://example.invalid',100);
  assert.equal((await r.json()).answer,'Complete');
  globalThis.fetch=async()=>{throw new Error('SECRET CONNECTION STRING')};
  const failed=await budgetedProxy(request(),'https://example.invalid',100);
  const text=await failed.text();assert(!text.includes('SECRET'));assert(text.includes('edge-unavailable'));
  globalThis.fetch=async()=>new Response(new Uint8Array(2*1024*1024+1));
  assert((await (await budgetedProxy(request(),'https://example.invalid',100)).text()).includes('edge-unavailable'));
});
