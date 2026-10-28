import { useEffect, useRef, useState, type FormEvent } from 'react';
import { chatStream, newChatSession, prefillNearby, type ChatOrigin, type ChatMessage } from '../../api/client';
import Icon from '../../components/Icon';
import AssistantAnswer from './AssistantAnswer';
import { useLanguage } from '../../language';

const suggestions = [
  {label:'搵狗友善餐廳',question:'我想帶狗去九龍城飲咖啡，幫我搵有資料來源嘅餐廳。'},
  {label:'周末狗狗訓練',question:'幫我睇吓有咩狗隻訓練班，列出日期、地點、費用同報名連結。'},
  {label:'帶狗點樣搭車',question:'我星期日想帶狗出街，有咩攜寵交通服務？有咩條件要留意？'},
];

export default function AssistantPanel({ open, onOpen, onClose, onShowPlace }: { open: boolean; onOpen: () => void; onClose: () => void; onShowPlace: (id: string) => void }) {
  const { language, tx, errorText } = useLanguage();
  const [message, setMessage] = useState('');
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState('');
  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState<{question:string;answer:string;sourceUrls:string[];places:{id:string;name:string}[]}[]>([]);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const [origin,setOrigin]=useState<ChatOrigin|null>(null);
  const [locating,setLocating]=useState(false);
  const locationRequest=useRef(0);
  function shareLocation(){
    if(!navigator.geolocation){setError(tx('瀏覽器唔支援定位，請提供地圖上嘅起點。'));return;}
    const request=++locationRequest.current;setLocating(true);setError('');
    navigator.geolocation.getCurrentPosition(({coords})=>{
      if(request!==locationRequest.current)return;
      const here={latitude:coords.latitude,longitude:coords.longitude};setOrigin(here);setLocating(false);void prefillNearby(here,language);
    },()=>{if(request!==locationRequest.current)return;setLocating(false);setError(tx('定位失敗，請提供起點或稍後再試。'));},{enableHighAccuracy:false,timeout:10000,maximumAge:60000});
  }
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bubbleRef = useRef<HTMLButtonElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  function close() {
    onClose();
    requestAnimationFrame(() => bubbleRef.current?.focus());
  }

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus({ preventScroll: true });
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') close(); };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [open]);

  useEffect(() => {
    if (open) resultRef.current?.scrollIntoView({ block: 'nearest' });
  }, [turns, question, draft, pending, error, open]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!message.trim() || pending) return;
    const text = message.trim();
    setQuestion(text); setMessage(''); setPending(true); setError(''); setDraft('');
    try {
      let streamed='';
      const response=await chatStream(text, history, language, origin, delta=>{streamed+=delta;setDraft(streamed);});
      const reply=response.answer;
      setTurns(previous => [...previous, { question: text, answer: reply, sourceUrls: (response.sources||[]).map(s=>s.url), places: response.places||[] }].slice(-50));
      if(response.places?.length)onShowPlace(response.places[0].id);
      setQuestion('');setDraft('');
      setHistory(previous => [...previous, { role: 'user' as const, content: text }, { role: 'assistant' as const, content: reply.slice(0, 8000) }].slice(-8));
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : tx('暫時連唔到助手，請再試。')); }
    finally { setPending(false);setDraft(''); }
  }

  return <div className="assistant-widget">
    <section id="assistant-window" className="assistant-window" role="dialog" aria-label={tx('毛孩助手')} aria-modal="false" hidden={!open}>
      <div className="assistant-header"><span className="assistant-avatar"><Icon name="paw" size={22} /></span><div><h2>{tx('毛孩助手')}</h2><p>{tx('一齊諗吓，今次去邊好')}</p></div><button className="icon-button" onClick={close} aria-label={tx('閂埋對話')}><Icon name="close" size={19} /></button></div>
      <div className="assistant-body">
        <div className="assistant-welcome"><span className="eyebrow">{tx('一齊帶毛孩出街')}</span><h3>{tx('今日想帶毛孩去邊？')}</h3><p>{tx('話我知地區、日期同毛孩需要，幫你搵餐廳、設施同課程。')}</p></div>
        {!question && turns.length===0 && <div className="suggestion-list">{suggestions.map(item => <button key={item.label} onClick={() => { setMessage(tx(item.question)); inputRef.current?.focus(); }}>{tx(item.label)}<span>↗</span></button>)}</div>}
        {turns.map((turn,index) => <div key={index}><div className="user-message">{turn.question}</div><div className="assistant-message"><AssistantAnswer text={turn.answer} sourceUrls={turn.sourceUrls} />{turn.places.length>0 && <div className="assistant-places">{turn.places.map(place=><button type="button" key={place.id} onClick={()=>onShowPlace(place.id)}><Icon name="pin" size={13}/>{place.name}</button>)}</div>}</div></div>)}
        {question && <div className="user-message">{question}</div>}
        {pending && !draft && <div className="assistant-message thinking" role="status"><span /><span /><span /><span className="sr-only">{tx('助手諗緊')}</span></div>}
        {pending && draft && <div className="assistant-message" role="status">{draft}</div>}
        {error && <><p className="inline-error" role="alert">{errorText(error)}</p></>}
        <div ref={resultRef} />
      </div>
      <div className="assistant-composer"><div className="assistant-location"><button type="button" disabled={pending||locating} onClick={shareLocation}><Icon name="pin" size={14}/>{locating?tx('定位中…'):origin?tx('已分享位置'):tx('分享位置')}</button>{origin&&<button type="button" disabled={pending} onClick={()=>{locationRequest.current++;setOrigin(null);}}>{tx('移除位置')}</button>}</div><form ref={formRef} onSubmit={submit}><label className="sr-only" htmlFor="question">{tx('你嘅毛孩出街計劃')}</label><textarea ref={inputRef} id="question" value={message} onChange={event => setMessage(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); formRef.current?.requestSubmit(); } }} placeholder={tx('輸入你嘅毛孩出街計劃…')} maxLength={8000} rows={2} /><button type="submit" className="send-button" disabled={pending || !message.trim()} aria-label={tx('傳送訊息')}><Icon name="send" size={18} /></button></form><p>{tx("可繼續補充條件・入場同報名請向主辦方核實")}<button type="button" disabled={pending} className="assistant-reset" onClick={() => { locationRequest.current++;setOrigin(null);setLocating(false);newChatSession(); setHistory([]); setTurns([]); setQuestion(''); setError(''); setMessage(''); }}>{tx("新對話")}</button></p></div>
    </section>
    <button ref={bubbleRef} className={`assistant-bubble ${open ? 'is-open' : ''}`} aria-label={open ? tx('收起毛孩助手') : tx('打開毛孩助手')} aria-controls="assistant-window" aria-expanded={open} onClick={() => { if (open) close(); else onOpen(); }}>{open ? <Icon name="close" size={23} /> : <><Icon name="chat" size={23} /><span>{tx('問吓 AI')}</span></>}</button>
  </div>;
}
