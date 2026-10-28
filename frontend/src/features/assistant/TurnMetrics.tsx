import type {ChatMetrics} from '../../api/client';
import {useLanguage} from '../../language';

export default function TurnMetrics({traceId,metrics}:{traceId?:string;metrics?:ChatMetrics}) {
  const {language}=useLanguage();
  const text=(en:string,zh:string)=>language==='en'?en:zh;
  if(!traceId)return null;
  const tokens=metrics?.total_tokens==null?text('Tokens unavailable','Token 用量未知'):
    `${metrics.total_tokens.toLocaleString()} tokens${metrics.usage_complete?'':text(' (partial)','（部分）')}`;
  return <details className="assistant-turn-metrics"><summary>{metrics?.duration_ms!=null&&<span>{(metrics.duration_ms/1000).toFixed(2)} s</span>}<span>{tokens}</span><span>{text('Trace details','追蹤詳情')}</span></summary>
    <dl><dt>Trace ID</dt><dd><code>{traceId}</code></dd>
      {metrics&&<><dt>{text('Model / tool calls','模型／工具調用')}</dt><dd>{metrics.model_calls} / {metrics.tool_calls}</dd>
      <dt>{text('Input / output tokens','輸入／輸出 Token')}</dt><dd>{metrics.input_tokens??'—'} / {metrics.output_tokens??'—'}</dd>
      <dt>{text('Cached / reasoning tokens','快取／推理 Token')}</dt><dd>{metrics.cached_tokens??'—'} / {metrics.reasoning_tokens??'—'}</dd>
      <dt>{text('First text received','首段文字時間')}</dt><dd>{metrics.first_token_ms==null?'—':`${(metrics.first_token_ms/1000).toFixed(2)} s`}</dd>
      <dt>{text('Conversation storage','對話儲存')}</dt><dd>{metrics.storage_status==='saved'?text('Saved to database','已存入資料庫'):metrics.storage_status==='unavailable'?text('Database write failed','資料庫寫入失敗'):text('Database not configured','尚未配置資料庫')}</dd></>}
    </dl>
  </details>;
}
