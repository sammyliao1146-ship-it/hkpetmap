// Bound the complete upstream body, not just time until SSE response headers.
const LIMIT_BYTES = 2 * 1024 * 1024;
export const BUDGETED_PATHS = new Set(['/api/v1/assistant/chat', '/api/v1/assistant/chat/stream', '/api/v1/plans']);

function fallback(path, timeout) {
  const headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'};
  const detail=timeout?'Unable to verify within the response time limit. Please narrow your question or open the place’s saved details. 未能喺時限內完成核實，請縮窄問題或查看場地已儲存資料。':'The assistant is temporarily unavailable. Please try again.';
  if(path==='/api/v1/plans')return Response.json({detail},{status:timeout?504:502,headers});
  const data={answer:detail,model:timeout?'edge-time-budget':'edge-unavailable',degraded:true,sources:[],places:[]};
  if(path.endsWith('/stream'))return new Response('data: '+JSON.stringify({type:'final',...data})+'\n\n',{
    headers:{...headers,'Content-Type':'text/event-stream; charset=utf-8'}});
  return Response.json(data,{headers});
}

export async function budgetedProxy(request, upstream, timeoutMs=4200) {
  const path=new URL(request.url).pathname;
  const controller=new AbortController();
  let timedOut=false,timer,reader;
  const disconnected=()=>controller.abort();
  request.signal.addEventListener('abort',disconnected,{once:true});
  if(request.signal.aborted)controller.abort();
  const timeout=new Promise((_,reject)=>{timer=setTimeout(()=>{
    timedOut=true;controller.abort();reject(new Error('Upstream deadline'));
  },timeoutMs);});
  try {
    return await Promise.race([timeout,(async()=>{
      const outgoing=new Request(upstream,new Request(request,{signal:controller.signal}));
      // We inspect/buffer this small API body; avoid compressed passthrough ambiguity.
      outgoing.headers.set('Accept-Encoding','identity');
      const response=await fetch(outgoing);
      reader=response.body?.getReader();
      const chunks=[];let length=0;
      if(reader)for(;;){
        const {done,value}=await reader.read();if(done)break;
        length+=value.byteLength;if(length>LIMIT_BYTES)throw new Error('Response too large');
        chunks.push(value);
      }
      const body=new Uint8Array(length);let offset=0;
      for(const chunk of chunks){body.set(chunk,offset);offset+=chunk.byteLength;}
      const headers=new Headers(response.headers);headers.set('Cache-Control','private, no-store');
      headers.delete('Content-Length');headers.delete('Content-Encoding');
      return new Response(body,{status:response.status,statusText:response.statusText,headers});
    })()]);
  } catch {
    controller.abort();
    if(request.signal.aborted)return new Response(null,{status:499,headers:{'Cache-Control':'private, no-store'}});
    return fallback(path,timedOut);
  } finally {
    clearTimeout(timer);request.signal.removeEventListener('abort',disconnected);
    // Cancel unread data after a deadline; don't keep a stalled body alive.
    if(reader)reader.cancel().catch(()=>{});
  }
}
