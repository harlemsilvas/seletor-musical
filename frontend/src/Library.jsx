import React, {useEffect,useRef,useState} from 'react';
import {groupByArtist} from './tracks';
const time=value=>Number.isFinite(value)?`${Math.floor(value/60)}:${String(Math.floor(value%60)).padStart(2,'0')}`:'—';
export function Library({active,onPlay,currentId}) {
 const [data,setData]=useState(null),[search,setSearch]=useState(''),[sort,setSort]=useState('newest'),[artist,setArtist]=useState(''),[artists,setArtists]=useState([]),[offset,setOffset]=useState(0),[error,setError]=useState(''),[refresh,setRefresh]=useState(0),[syncing,setSyncing]=useState(false),[note,setNote]=useState(''),[enriching,setEnriching]=useState('');
 useEffect(()=>{
  if(!active)return;
  let stopped=false,timer;const controller=new AbortController();
  async function poll(){try{const params=new URLSearchParams({search,sort,artist,offset,limit:50});const r=await fetch(`/api/library?${params}`,{signal:controller.signal});if(!r.ok)throw new Error('Não foi possível carregar a biblioteca.');const result=await r.json();const a=await fetch('/api/library/artists',{signal:controller.signal});if(!stopped){setData(result);setError('');if(a.ok)setArtists((await a.json()).artists)}}catch(e){if(!stopped)setError(e.message)}finally{if(!stopped)timer=setTimeout(poll,2000)}}
  timer=setTimeout(poll,180);return()=>{stopped=true;clearTimeout(timer);controller.abort()};
 },[active,search,sort,artist,offset,refresh]);
 async function sync(){setSyncing(true);setError('');try{const r=await fetch('/api/library/sync',{method:'POST',headers:{'X-Seletor-Client':'1'}});if(!r.ok)throw new Error('Não foi possível iniciar a atualização.');setData(old=>old?{...old,sync:{...old.sync,running:true}}:old);setRefresh(v=>v+1)}catch(e){setError(e.message)}finally{setSyncing(false)}}
 async function enrichTrack(track){
  setError('');setNote('');setEnriching(track.id);
  try{const r=await fetch(`/api/library/${track.id}/enrich`,{method:'POST',headers:{'X-Seletor-Client':'1'}});const body=await r.json().catch(()=>({}));
   if(!r.ok)throw new Error(typeof body.detail==='string'?body.detail:'Não foi possível enriquecer esta faixa.');
   setNote(body.status==='ok'?`Dados e capa de “${track.title}” atualizados no MP3.`:body.status==='blocked'?'O YouTube pediu verificação anti-bot. Tente novamente mais tarde.':`Não foi possível obter os dados de “${track.title}”. Verifique a conexão e tente de novo.`);
   setRefresh(v=>v+1)}catch(e){setError(e.message)}finally{setEnriching('')}
 }
 return <section><h2>Biblioteca local <small>{data?.total||0} faixas</small></h2><p className="muted">MP3s salvos na pasta de downloads. Você pode ouvir sem internet enquanto o servidor local estiver aberto.</p>
 <div className="row"><label className="library-search">Buscar na biblioteca<input type="search" value={search} maxLength={200} onChange={e=>{setSearch(e.target.value);setOffset(0)}} placeholder="Título, canal ou artista…"/></label><label>Ordenar<select value={sort} onChange={e=>{setSort(e.target.value);setOffset(0)}}><option value="newest">Mais recentes</option><option value="title">Título</option><option value="artist">Artista</option></select></label><label>Artista<select aria-label="Filtrar por artista" value={artist} onChange={e=>{setArtist(e.target.value);setOffset(0)}}><option value="">Todos</option>{artists.map(a=><option key={a.artist} value={a.artist}>{a.artist} ({a.count})</option>)}</select></label><button disabled={syncing||data?.sync.running} onClick={sync}>Atualizar biblioteca</button></div>
 <p role="status">{!data&&!error?'Carregando biblioteca…':data?.sync.running?'Verificando os arquivos…':enriching?'Consultando o YouTube e gravando tags… pode levar alguns segundos.':note}</p><p role="alert" className="error">{error||data?.sync.error}</p>
 {data&&!data.total&&<p className="empty">Ainda não há músicas na biblioteca. Conclua um download ou coloque seus MP3s em ~/Música/SeletorMusical e clique em Atualizar biblioteca.</p>}
 {(sort==='artist'?groupByArtist(data?.items||[]):[{name:null,items:data?.items||[]}]).map(group=><div key={group.name||'all'} className="artist-group">{group.name&&<h3>{group.name} <small>{group.items.length}</small></h3>}{group.items.map(track=><article key={track.id}>{track.has_cover?<img className="cover" src={`/api/library/${track.id}/cover`} alt="" loading="lazy" width="48" height="48"/>:<span className="music-icon" aria-hidden="true">♫</span>}<div className="info"><strong>{track.track||track.title}</strong><p>{track.artist||track.channel||'Artista indisponível'}{track.album?` · ${track.album}`:''}{(track.release_date||track.upload_date)?` · ${(track.release_date||track.upload_date).slice(0,4)}`:''} · {time(track.duration)}</p>{!track.available&&<small className="error">{track.message}</small>}</div><button disabled={!track.available} onClick={()=>onPlay(track)} aria-label={`Tocar ${track.title}`}>{currentId===track.id?'Tocar novamente':'Tocar'}</button><button className="secondary" disabled={!track.available||!track.video_id||!!enriching} onClick={()=>enrichTrack(track)} aria-label={`${track.meta_status==='done'?'Atualizar dados de':'Enriquecer'} ${track.title}`} title="Busca título, artista, ano e capa no YouTube e grava no MP3">{enriching===track.id?'Enriquecendo…':track.meta_status==='done'?'Atualizar dados':'Enriquecer'}</button></article>)}</div>)}
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
 return <aside className="player" aria-label="Player local">{track?.has_cover&&<img className="cover" src={`/api/library/${track.id}/cover`} alt="" width="48" height="48"/>}<div className="player-title"><strong>{track?.title||'Selecione uma música na Biblioteca'}</strong>{track&&<small>{track.artist||track.channel||'Reprodução local'}</small>}<span role="alert" className="error">{error}</span></div><audio ref={audio} aria-label="Áudio da música atual" controls preload="metadata" src={track?`/api/library/${track.id}/audio`:undefined} onError={()=>{if(track)setError('Não foi possível reproduzir o arquivo. Atualize a biblioteca e verifique se o MP3 está disponível.')}}/></aside>;
}
