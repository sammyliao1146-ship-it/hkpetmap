/** Render government-source Markdown links without interpreting arbitrary HTML. */
export default function AssistantAnswer({ text, sourceUrls=[] }: { text: string; sourceUrls?:string[] }) {
  const verifiedUrls=new Set(sourceUrls.flatMap(value=>{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password?[u.href]:[];}catch{return [];}}));
  const pattern = /\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g;
  const parts: React.ReactNode[] = [];
  let previous = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    parts.push(text.slice(previous, index));
    let safe = false;
    try {
      const url = new URL(match[2]);
      safe = url.protocol === 'https:' && (verifiedUrls.has(url.href) || ['gov.hk','spca.org.hk','mtr.com.hk','uber.com','sunferry.com.hk','kmb.hk','airside.com.hk','arabica.coffee','arabica.com','pret.hk','pizzamaru.com.hk','askforalonzo.com','pizzaexpress.com.hk','starbucks.com.hk','tonkichi.com.hk'].some(host => url.hostname === host || url.hostname.endsWith('.'+host))) && !url.username && !url.password;
    } catch { /* Keep invalid URLs as plain text. */ }
    parts.push(safe ? <a key={index} href={match[2]} target="_blank" rel="noopener noreferrer">{match[1]} ↗</a> : match[0]);
    previous = index + match[0].length;
  }
  parts.push(text.slice(previous));
  return <>{parts}</>;
}
