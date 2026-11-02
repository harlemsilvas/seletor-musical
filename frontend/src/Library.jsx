import React, {useEffect,useRef,useState} from 'react';
const time=value=>Number.isFinite(value)?`${Math.floor(value/60)}:${String(Math.floor(value%60)).padStart(2,'0')}`:'—';
export function Library({active,onPlay,currentId}) {
 const [data,setData]=useState(null),[search,setSearch]=useState(''),[sort,setSort]=useState('newest'),[offset,setOffset]=useState(0),[error,setError]=useState(''),[refresh,setRefresh]=useState(0),[syncing,setSyncing]=useState(false);
 useEffect(()=>{
  if(!active)return;
  let stopped=false,timer;const controller=new AbortController();
  async function poll(){try{const params=new URLSearchParams({search,sort,offset,limit:50});const r=await fetch(`/api/library?${params}`,{signal:controller.signal});if(!r.ok)throw new Error('Não foi possível carregar a biblioteca.');const result=await r.json();if(!stopped){setData(result);setError('')}}catch(e){if(!stopped)setError(e.message)}finally{if(!stopped)timer=setTimeout(poll,2000)}}
  timer=setTimeout(poll,180);return()=>{stopped=true;clearTimeout(timer);controller.abort()};
 },[active,search,sort,offset,refresh]);
 async function sync(){setSyncing(true);setError('');try{const r=await fetch('/api/library/sync',{method:'POST',headers:{'X-Seletor-Client':'1'}});if(!r.ok)throw new Error('Não foi possível iniciar a atualização.');setData(old=>old?{...old,sync:{...old.sync,running:true}}:old);setRefresh(v=>v+1)}catch(e){setError(e.message)}finally{setSyncing(false)}}
 return <section><h2>Biblioteca local <small>{data?.total||0} faixas</small></h2><p className="muted">MP3s salvos na pasta de downloads. Você pode ouvir sem internet enquanto o servidor local estiver aberto.</p>
 <div className="row"><label className="library-search">Buscar na biblioteca<input type="search" value={search} maxLength={200} onChange={e=>{setSearch(e.target.value);setOffset(0)}} placeholder="Título, canal ou artista…"/></label><label>Ordenar<select value={sort} onChange={e=>{setSort(e.target.value);setOffset(0)}}><option value="newest">Mais recentes</option><option value="title">Título</option></select></label><button disabled={syncing||data?.sync.running} onClick={sync}>Atualizar biblioteca</button></div>
 <p role="status">{!data&&!error?'Carregando biblioteca…':data?.sync.running?'Verificando os arquivos…':''}</p><p role="alert" className="error">{error||data?.sync.error}</p>
 {data&&!data.total&&<p className="empty">Ainda não há músicas na biblioteca. Conclua um download ou coloque seus MP3s em ~/Música/SeletorMusical e clique em Atualizar biblioteca.</p>}
 {data?.items.map(track=><article key={track.id}><span className="music-icon" aria-hidden="true">♫</span><div className="info"><strong>{track.title}</strong><p>{track.channel||track.artist||'Canal / artista indisponível'} · {time(track.duration)}</p>{!track.available&&<small className="error">{track.message}</small>}</div><button disabled={!track.available} onClick={()=>onPlay(track)} aria-label={`Tocar ${track.title}`}>{currentId===track.id?'Tocar novamente':'Tocar'}</button></article>)}
 {data&&data.total>50&&<div className="row"><button className="secondary" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-50))}>Página anterior</button><span>{offset+1}–{Math.min(offset+50,data.total)} de {data.total}</span><button className="secondary" disabled={offset+50>=data.total} onClick={()=>setOffset(offset+50)}>Próxima página</button></div>}
 </section>;
}
export function Player({track}) {
 const audio=useRef(null),[error,setError]=useState('');
 useEffect(()=>{
  if(!track)return;
  let stopped=false;setError('');
  const element=audio.current;element.load();
  element.play().catch(()=>{if(!stopped)setError('Não foi possível iniciar automaticamente. Use o botão de reprodução; se o arquivo estiver ausente, atualize a biblioteca.')});
  return()=>{stopped=true};
 },[track]);
 return <aside className="player" aria-label="Player local"><div className="player-title"><strong>{track?.title||'Selecione uma música na Biblioteca'}</strong>{track&&<small>{track.channel||track.artist||'Reprodução local'}</small>}<span role="alert" className="error">{error}</span></div><audio ref={audio} aria-label="Áudio da música atual" controls preload="metadata" src={track?`/api/library/${track.id}/audio`:undefined} onError={()=>{if(track)setError('Não foi possível reproduzir o arquivo. Atualize a biblioteca e verifique se o MP3 está disponível.')}}/></aside>;
}
