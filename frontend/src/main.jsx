import React, {useState, useEffect, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {parseTracks, filterTracks, selectedUrls} from './tracks';
import './style.css';
import {Library,Player} from './Library';
import Downloads, {downloadLabel} from './Downloads';
import VerificationDialog, {needsVerification} from './VerificationDialog';
// Resumo do último lote enviado, recalculado a cada atualização da fila.
function batchSummary(batch,downloads){
 if(!batch)return '';
 const byId=new Map((downloads?.jobs||[]).map(j=>[j.id,j]));
 let done=0,failed=0,remaining=0;
 for(const id of batch.ids){const status=byId.get(id)?.status;
  // Ativos sempre aparecem na lista; um item ausente já saiu do histórico recente (concluído).
  if(['pending','downloading','converting'].includes(status))remaining++;else if(['failed','cancelled','interrupted'].includes(status))failed++;else done++}
 const ignored=`${batch.done} já concluídas e ${batch.queued} já na fila foram ignoradas.`;
 return `${remaining?'Lote em andamento':'Lote finalizado'}: ${batch.ids.length} adicionadas à fila · ${done} concluídas · ${failed} com falha ou canceladas · ${remaining} restantes. ${ignored}`;
}
function App() {
 const [tab,setTab]=useState('select'),[playing,setPlaying]=useState(null);
 const [items,setItems]=useState(()=>{try{return parseTracks(localStorage.getItem('musicas-v1')||'[]')}catch{return []}});
 const [selected,setSelected]=useState(new Set()), [term,setTerm]=useState(''), [url,setUrl]=useState(''), [source,setSource]=useState('');
 const [max,setMax]=useState(50), [limit,setLimit]=useState(50), [busy,setBusy]=useState(false), [error,setError]=useState(''), [notice,setNotice]=useState(''), [batch,setBatch]=useState(null);
 useEffect(()=>{fetch('/api/config').then(r=>r.json()).then(c=>{setMax(c.max_items);setLimit(c.max_items)}).catch(()=>setError('Não foi possível conectar ao servidor.'))},[]);
 useEffect(()=>{try{localStorage.setItem('musicas-v1',JSON.stringify(items))}catch{setNotice('Não foi possível salvar a lista neste navegador.')}},[items]);
 const [downloads,setDownloads]=useState(null), [queueError,setQueueError]=useState(''), [sending,setSending]=useState(false);
 useEffect(()=>{
  // 1 s com download ativo e aba visível; 5 s caso contrário. Volta a consultar ao reexibir a aba.
  let stopped=false, timer, active=false;
  async function poll(){clearTimeout(timer);try{const response=await fetch('/api/downloads');if(!response.ok)throw new Error('Não foi possível carregar a fila. Verifique se o servidor foi atualizado e está em execução.');const data=await response.json();active=data.jobs.some(j=>['pending','downloading','converting'].includes(j.status));if(!stopped){setDownloads(data);setQueueError('')}}catch(e){if(!stopped)setQueueError(e.message)}finally{if(!stopped)timer=setTimeout(poll,active&&document.visibilityState==='visible'?1000:5000)}}
  const onVisible=()=>{if(document.visibilityState==='visible')poll()};
  document.addEventListener('visibilitychange',onVisible);
  poll();return ()=>{stopped=true;clearTimeout(timer);document.removeEventListener('visibilitychange',onVisible)};
 },[]);
 async function queueAction(path,body){
  setSending(true);setError('');
  try{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Seletor-Client':'1'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Não foi possível adicionar os itens. Confira os dados da seleção.');
   if(data.accepted){setTab('downloads');setNotice('');setBatch({ids:data.accepted,done:data.skipped.filter(i=>i.reason==='completed').length,queued:data.skipped.filter(i=>i.reason==='queued').length})}else{setNotice('Cancelamento solicitado. Arquivos concluídos são preservados.')}
   const status=await fetch('/api/downloads');if(status.ok)setDownloads(await status.json());
  }catch(e){setError(e.message)}finally{setSending(false)}
 }
 function enqueue(tracks){if(tracks.length>200){setError('Selecione até 200 músicas por envio à fila.');return}return queueAction('/api/downloads',{items:tracks.map(t=>({url:t.url,title:t.title.slice(0,500),channel:typeof t.channel==='string'?t.channel.slice(0,500):''}))})}
 const downloadStates=new Map();for(const job of downloads?.jobs||[]){if(!downloadStates.has(job.video_id))downloadStates.set(job.video_id,job)}
 const [verification,setVerification]=useState(null);
 const seenVerifications=useRef(new Set());
 useEffect(()=>{
  const blocked=(downloads?.jobs||[]).filter(needsVerification);
  if(verification)return;
  const next=blocked.find(job=>!seenVerifications.current.has(job.id));
  if(next){blocked.forEach(job=>seenVerifications.current.add(job.id));setVerification({...next,kind:'download'})}
 },[downloads,verification]);
 const visible=filterTracks(items,term);
 function load(list){setItems(list);setSelected(new Set());setTerm('');setNotice(`${list.length} músicas carregadas.`)}
 async function query(e){e.preventDefault();return consult(url,limit)}
 async function consult(targetUrl,targetLimit){setBusy(true);setError('');setNotice('');try{const r=await fetch('/api/query',{method:'POST',headers:{'Content-Type':'application/json','X-Seletor-Client':'1'},body:JSON.stringify({url:targetUrl,limit:Number(targetLimit)})});const data=await r.json();if(!r.ok){if(data.detail?.code==='youtube_verification'){setVerification({kind:'query',url:data.detail.url,limit:targetLimit});throw new Error(data.detail.message)}throw new Error(typeof data.detail==='string'?data.detail:'Confira a URL e o limite informado.')}load(data.items)}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function copy(text){setError('');try{await navigator.clipboard.writeText(text);setNotice('URLs copiadas.')}catch{setError('O navegador bloqueou a cópia. Copie os links exibidos abaixo.');window.prompt('Copie as URLs:',text)}}
 function toggle(id){setSelected(old=>{const next=new Set(old);next.has(id)?next.delete(id):next.add(id);return next})}
 function importText(text){setError('');const list=parseTracks(text);if(!list.length){setError('Nenhum vídeo válido encontrado. Cole URLs, texto ou JSONL do yt-dlp.');return}load(list)}
 return <main><header><span className="tag">SUA MÚSICA · SUA ESCOLHA</span><h1>Escolha o que vai tocar.</h1><p>Consulte uma lista do YouTube, selecione suas músicas e baixe em MP3.</p></header>
 <nav className="tabs" aria-label="Seções da aplicação">{[['select','Selecionar'],['downloads','Downloads'],['library','Biblioteca']].map(([key,label])=><button key={key} className={tab===key?'':'secondary'} aria-pressed={tab===key} onClick={()=>setTab(key)}>{label}</button>)}</nav>
 <div role="alert" className="error">{error}</div><div role="status" aria-live="polite">{busy?'Consultando metadados, aguarde…':notice}</div><div className="batch-summary" role="status" aria-live="polite">{batchSummary(batch,downloads)}</div>
 <div hidden={tab!=='select'}><section><h2>1. Consulte o YouTube</h2><form onSubmit={query}><label>URL de vídeo, playlist ou Mix<input type="url" required value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://www.youtube.com/playlist?list=…"/></label><div className="row"><label>Limite de itens<input type="number" min="1" max={max} required value={limit} onChange={e=>setLimit(e.target.value)}/></label><button disabled={busy}>{busy?'Consultando…':'Consultar músicas'}</button></div></form><p className="muted">Mixes são dinâmicos: a seleção pode variar em relação ao navegador. Até {max} itens por consulta.</p></section>
 <section><details><summary>Ou importe JSONL / texto</summary><p>Uma URL por linha, Nome | URL, JSON ou JSONL do yt-dlp. A importação substitui a lista atual.</p><textarea aria-label="Lista para importar" value={source} onChange={e=>setSource(e.target.value)}/><div className="row"><button disabled={busy} onClick={()=>importText(source)}>Carregar lista</button><label> Abrir arquivo<input type="file" accept=".txt,.json,.jsonl,.csv" disabled={busy} onChange={async e=>{const file=e.target.files[0];if(!file)return;if(file.size>5*1024*1024){setError('Arquivo excede 5 MB.');return}try{const text=await file.text();setSource(text);importText(text)}catch{setError('Não foi possível ler o arquivo.')}}}/></label></div></details></section>
 <section aria-busy={busy}><h2>2. Sua seleção <small>{items.length} músicas · {selected.size} selecionadas</small></h2><input type="search" aria-label="Buscar por título ou canal" placeholder="Buscar por título ou canal…" value={term} onChange={e=>setTerm(e.target.value)}/><div className="row"><button disabled={!visible.length} onClick={()=>setSelected(old=>new Set([...old,...visible.map(t=>t.id)]))}>Selecionar resultados filtrados ({visible.length})</button><button className="secondary" onClick={()=>setSelected(new Set())}>Desmarcar todas</button><button disabled={!selected.size} onClick={()=>copy(selectedUrls(items,selected))}>Copiar URLs selecionadas</button><button disabled={!selected.size||sending||!downloads?.dependencies?.ready} onClick={()=>enqueue(items.filter(t=>selected.has(t.id)))}>{sending?'Aguarde…':'Baixar selecionadas em MP3'}</button><button className="secondary" disabled={busy} onClick={()=>{load([]);setSource('')}}>Limpar lista</button></div>
 {!visible.length&&<p className="empty">{items.length?'Nenhuma música corresponde à busca.':'Consulte o YouTube ou importe uma lista para começar.'}</p>}
 {visible.map(t=><article key={t.id}><input type="checkbox" aria-label={`Selecionar ${t.title}`} checked={selected.has(t.id)} onChange={()=>toggle(t.id)}/>{/^https:\/\/(i\.ytimg\.com|img\.youtube\.com)\//.test(t.thumbnail||'')&&<img src={t.thumbnail} alt="" loading="lazy" referrerPolicy="no-referrer"/>}<div className="info"><strong>{t.title}</strong>{downloadStates.has(t.id)&&<small className="track-status">{downloadLabel(downloadStates.get(t.id).status)}</small>}<p>{t.channel||'Canal indisponível'} · {Number.isFinite(t.duration)?`${Math.floor(t.duration/60)}:${String(Math.floor(t.duration%60)).padStart(2,'0')}`:'Duração indisponível'}</p><a href={t.url} target="_blank" rel="noreferrer">{t.url}</a></div><button className="secondary" onClick={()=>copy(t.url)}>Copiar URL</button></article>)}
 </section></div><div hidden={tab!=='downloads'}><Downloads data={downloads} failure={queueError} sending={sending} onCancel={job=>queueAction(`/api/downloads/${job.id}/cancel`,{})} onRetry={job=>enqueue([job])} onVerification={job=>setVerification({...job,kind:'download'})}/></div><div hidden={tab!=='library'}><Library active={tab==='library'} currentId={playing?.id} onPlay={track=>setPlaying({...track})}/></div><Player track={playing}/><VerificationDialog item={verification} busy={sending||busy} onClose={()=>setVerification(null)} onRetry={()=>{const item=verification;setVerification(null);if(item.kind==='query')consult(item.url,item.limit);else enqueue([item])}}/><footer>A lista fica neste navegador. O histórico fica salvo neste computador. Baixe apenas músicas que você tem permissão para baixar.</footer></main>
}
createRoot(document.getElementById('root')).render(<App/>);
