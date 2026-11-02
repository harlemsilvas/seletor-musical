import React from 'react';
import {needsVerification} from './VerificationDialog';

const labels = {pending:'Na fila', downloading:'Baixando', converting:'Convertendo para MP3', completed:'Concluído', failed:'Falhou', cancelled:'Cancelado / removido', interrupted:'Interrompido'};
const active = new Set(['pending','downloading','converting']);
export function downloadLabel(status) { return labels[status] || status; }
function bytes(value) {
 if (!Number.isFinite(value)) return '';
 return value >= 1048576 ? `${(value/1048576).toFixed(1)} MB` : `${Math.round(value/1024)} KB`;
}
export default function Downloads({data, failure, sending, onCancel, onRetry, onVerification}) {
 const jobs = data?.jobs || [];
 const queued = jobs.filter(j=>active.has(j.status));
 const history = jobs.filter(j=>!active.has(j.status));
 function row(job) {
  const downloading=job.status==='downloading';
  return <article key={job.id} className="download-item">
   <div className="info"><strong>{job.title}</strong><p><span className={`status status-${job.status}`}>{downloadLabel(job.status)}</span>{downloading&&job.progress!==null&&` · ${job.progress.toFixed(1)}%`}</p>
   {downloading&&<><progress aria-label={`Progresso de ${job.title}`} max="100" {...(job.progress===null?{}:{value:job.progress})}/><p>{bytes(job.downloaded)}{job.total?` de ~${bytes(job.total)}`:''}{job.speed?` · ${bytes(job.speed)}/s`:''}{Number.isFinite(job.eta)?` · ~${Math.ceil(job.eta)} s restantes`:''}</p></>}
   <p>{job.message}</p>{job.filename&&<small>Arquivo: {job.filename}{job.file_exists===false?' · arquivo não encontrado na pasta':''}</small>}
   </div>
   {needsVerification(job)&&<button className="secondary" onClick={()=>onVerification(job)}>Verificação no YouTube</button>}
   {active.has(job.status)?<button disabled={sending} className="secondary" onClick={()=>onCancel(job)}>{job.status==='pending'?'Remover da fila':'Cancelar download'}</button>:job.status!=='completed'||job.file_exists===false?<button disabled={sending} className="secondary" onClick={()=>onRetry(job)}>Tentar novamente</button>:null}
  </article>;
 }
 return <section><h2>3. Downloads em MP3 <small>{queued.length} na fila ou em andamento</small></h2>
 <p className="muted">Um download por vez. Salvos em <strong>{data?.download_dir || '~/Música/SeletorMusical'}</strong>. Fechar esta página não interrompe a fila enquanto o servidor estiver aberto.</p>
 {failure&&<p role="alert" className="error">{failure}</p>}
 {data?.dependencies&&!data.dependencies.ready&&<p role="alert" className="error">Downloads indisponíveis: {data.dependencies.problems.join(' ')}</p>}
 {!data&&!failure&&<p role="status">Carregando fila…</p>}
 {data&&!queued.length&&<p className="empty">Nenhum download em andamento. Marque músicas e clique em Baixar selecionadas em MP3.</p>}
 {queued.slice().reverse().map(row)}
 <details open={history.length>0}><summary>Histórico ({history.length}{history.length===data?.history_limit?' mais recentes':''})</summary>{history.length?history.map(row):<p>Ainda não há downloads no histórico.</p>}</details>
 </section>;
}
