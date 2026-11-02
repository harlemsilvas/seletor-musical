// Interface real com respostas de download simuladas; não baixa mídia.
// NODE_PATH=/tmp/seletor-browser/node_modules CHROMIUM_PATH=/caminho/chrome node tests/browser-smoke.cjs
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let jobs=[], posted=[];
  const endpoint='http://localhost:8766';
  const snapshot=()=>({jobs,dependencies:{ready:true,problems:[]},download_dir:'~/Música/SeletorMusical',history_limit:200});
  await page.route('**/api/downloads**',async route=>{
   const req=route.request();
   if(req.method()==='GET')return route.fulfill({json:snapshot()});
   if(req.url().endsWith('/cancel')){
    const id=req.url().split('/').at(-2);jobs=jobs.map(j=>j.id===id?{...j,status:'cancelled',message:'Cancelado'}:j);
    return route.fulfill({json:{status:'cancelled'}});
   }
   posted=req.postDataJSON().items;
   jobs=posted.map((t,i)=>({id:String(i).padStart(32,'0'),video_id:new URL(t.url).searchParams.get('v'),title:t.title,url:t.url,status:i?'pending':'downloading',progress:i?null:50,downloaded:500,total:1000,speed:100,eta:5,message:'Fixture'}));
   return route.fulfill({status:202,json:{accepted:jobs.map(j=>j.id),skipped:[]}});
  });
  await page.goto(endpoint);
  await page.getByText('Ou importe JSONL / texto',{exact:true}).click();
  await page.getByLabel('Lista para importar').fill('{"id":"abcdefghijk","title":"Canção A","channel":"Canal Um"}\n{"id":"lmnopqrstuv","title":"Canção B","channel":"Canal Dois"}');
  await page.getByRole('button',{name:'Carregar lista',exact:true}).click();
  await page.getByLabel('Buscar por título ou canal').fill('Canal Um');
  assert.equal(await page.getByRole('checkbox').count(),1);
  await page.getByRole('button',{name:'Selecionar resultados filtrados (1)',exact:true}).click();
  await page.getByLabel('Buscar por título ou canal').fill('');
  assert.equal(await page.getByRole('checkbox').first().isChecked(),true);
  await page.getByRole('button',{name:'Copiar URLs selecionadas',exact:true}).click();
  assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),'https://www.youtube.com/watch?v=abcdefghijk');
  await page.getByRole('checkbox').nth(1).check();
  await page.getByRole('button',{name:'Baixar selecionadas em MP3',exact:true}).click();
  await page.getByRole('button',{name:'Cancelar download',exact:true}).waitFor();
  assert.equal(posted.length,2);assert.equal(posted[0].url.includes('list='),false);
  assert.equal(await page.getByRole('progressbar').getAttribute('value'),'50');
  // O resumo do topo acompanha a fila (não é um texto fixo do momento do envio).
  await page.getByText('Lote em andamento: 2 adicionadas à fila · 0 concluídas · 0 com falha ou canceladas · 2 restantes. 0 já concluídas e 0 já na fila foram ignoradas.').waitFor();
  await page.getByRole('button',{name:'Remover da fila',exact:true}).click();
  await page.getByRole('button',{name:'Remover da fila',exact:true}).waitFor({state:'hidden'});
  await page.getByText(/Lote em andamento: 2 adicionadas à fila · 0 concluídas · 1 com falha ou canceladas · 1 restantes/).waitFor();
  jobs=jobs.map(j=>j.status==='downloading'?{...j,status:'converting',progress:null}:j);
  await page.locator('.status-converting').waitFor();
  await page.getByRole('button',{name:'Cancelar download',exact:true}).click();
  await page.getByRole('button',{name:'Cancelar download',exact:true}).waitFor({state:'hidden'});
  assert.equal(jobs.every(j=>j.status==='cancelled'),true);
  await page.getByText(/Lote finalizado: 2 adicionadas à fila · 0 concluídas · 2 com falha ou canceladas · 0 restantes/).waitFor();
  assert.deepEqual(errors,[]);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  console.log('Browser: importação, busca, seleção, cópia real, envio, progresso, conversão, remoção e cancelamento OK.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
