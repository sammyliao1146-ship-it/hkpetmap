/** Read a completed chat result, including CRLF/multiline SSE and truncated streams. */
export async function readChatEvents<T extends {answer:string}>(body:ReadableStream<Uint8Array>,onDelta:(text:string)=>void,missingMessage:string):Promise<T> {
  const reader=body.getReader(),decoder=new TextDecoder();
  let buffer='',final:T|null=null;
  function handle(block:string){
    const data=block.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).replace(/^ /,'')).join('\n');
    if(!data)return;
    const event=JSON.parse(data);
    if(event.type==='error')throw new Error(typeof event.detail==='string'?event.detail:missingMessage);
    if(event.type==='delta'&&typeof event.text==='string')onDelta(event.text);
    if(event.type==='final'){
      if(typeof event.answer!=='string')throw new Error(missingMessage);
      final=event;
    }
  }
  try {
    while(!final){
      const {value,done}=await reader.read();
      buffer+=(value?decoder.decode(value,{stream:!done}):done?decoder.decode():'');
      buffer=buffer.replace(/\r\n/g,'\n');
      let boundary;
      while(!final&&(boundary=buffer.indexOf('\n\n'))>=0){handle(buffer.slice(0,boundary));buffer=buffer.slice(boundary+2);}
      if(done){if(!final&&buffer.trim())handle(buffer);break;}
    }
    if(!final)throw new Error(missingMessage);
    return final;
  } finally {
    void reader.cancel().catch(()=>{});
    reader.releaseLock();
  }
}
