import React, {useEffect, useRef} from 'react';

export function needsVerification(job) {
 return job.status==='failed' && typeof job.message==='string' && job.message.includes('não é um robô');
}
export default function VerificationDialog({item,busy,onClose,onRetry}) {
 const dialog=useRef(null);
 useEffect(()=>{
  const element=dialog.current;
  if(item&&!element.open)element.showModal();
  if(!item&&element.open)element.close();
 },[item]);
 return <dialog ref={dialog} aria-labelledby="verification-title" aria-describedby="verification-help" onCancel={e=>{e.preventDefault();onClose()}}>
  <h2 id="verification-title">O YouTube pediu uma verificação</h2>
  <p id="verification-help">Abra o YouTube no seu navegador. Se ele apresentar uma confirmação, faça a verificação manualmente e depois volte para tentar novamente.</p>
  <p className="muted">A confirmação feita no navegador não é transferida automaticamente ao yt-dlp. Esta tentativa pode continuar bloqueada. A aplicação não acessa seus cookies ou sua conta.</p>
  <div className="row"><a className="button-link" href={item?.url} target="_blank" rel="noopener noreferrer">Abrir no YouTube ↗</a><button disabled={busy} onClick={onRetry}>Tentar novamente</button><button className="secondary" onClick={onClose}>Fechar</button></div>
 </dialog>;
}
