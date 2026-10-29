import test from 'node:test';
import assert from 'node:assert/strict';
import {readChatEvents} from '../src/api/sse-reader.ts';

function stream(chunks,close=true){return new ReadableStream({start(c){for(const chunk of chunks)c.enqueue(new TextEncoder().encode(chunk));if(close)c.close();}});}
test('CRLF split across chunks and multiline JSON preserve the final answer',async()=>{
  const deltas=[];
  const result=await readChatEvents(stream(['data: {"type":"delta","text":"你好"}\r','\n\r\n','data: {"type":"final",\r\ndata: "answer":"完成"}\r\n\r\n']),t=>deltas.push(t),'Missing final');
  assert.deepEqual(deltas,['你好']);assert.equal(result.answer,'完成');
});
test('a final event returns without waiting for the connection to close',async()=>{
  const result=await readChatEvents(stream(['data: {"type":"final","answer":"Done"}\n\n'],false),()=>{},'Missing final');
  assert.equal(result.answer,'Done');
});
test('HTTP 200 with no final, invalid final and explicit error are failures',async()=>{
  for(const content of ['', 'data: {"type":"delta","text":"draft"}\n\n','data: {"type":"final"}\n\n']){
    await assert.rejects(readChatEvents(stream([content]),()=>{},'Connection interrupted'),/Connection interrupted/);
  }
  await assert.rejects(readChatEvents(stream(['data: {"type":"error","detail":"Unavailable"}\n\n']),()=>{},'Failed'),/Unavailable/);
});
