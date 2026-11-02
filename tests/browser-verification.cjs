// Usa Playwright instalado separadamente, como browser-smoke.cjs.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage();let jobs=[],attempts=0,downloads=0;
  const url='https://www.youtube.com/watch?v=ClU3fctbGls';
  await page.route('**/api/downloads',route=>{
   if(route.request().method()==='POST'){downloads++;jobs=[];return route.fulfill({status:202,json:{accepted:['new'],skipped:[]}})}
   return route.fulfill({json:{jobs,dependencies:{ready:true,problems:[]},history_limit:200}});
  });
  await page.route('**/api/query',route=>{
   attempts++;
   return attempts===1?route.fulfill({status:502,json:{detail:{code:'youtube_verification',message:'Verificação necessária.',url}}}):route.fulfill({json:{items:[]}});
  });
  await page.goto('http://localhost:8766');
  await page.getByLabel('URL de vídeo, playlist ou Mix').fill(url);
  await page.getByRole('button',{name:'Consultar músicas',exact:true}).click();
  const dialog=page.getByRole('dialog');await dialog.waitFor();
  assert.equal(await dialog.getByRole('link',{name:'Abrir no YouTube ↗'}).getAttribute('href'),url);
  assert.equal(await dialog.getByRole('link').getAttribute('target'),'_blank');
  await dialog.getByRole('button',{name:'Tentar novamente',exact:true}).click();
  await dialog.waitFor({state:'hidden'});assert.equal(attempts,2);
  jobs=[{id:'a'.repeat(32),url,video_id:'ClU3fctbGls',title:'Teste',status:'failed',message:'O YouTube solicitou confirmação de que você não é um robô.'}];
  await dialog.waitFor();await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
  await page.waitForTimeout(1500);assert.equal(await dialog.isVisible(),false);
  await page.getByRole('button',{name:'Downloads',exact:true}).click();
  await page.getByRole('button',{name:'Verificação no YouTube',exact:true}).click();
  await dialog.waitFor();await dialog.getByRole('button',{name:'Tentar novamente',exact:true}).click();
  await dialog.waitFor({state:'hidden'});assert.equal(downloads,1);
  console.log('Janela de verificação: consulta, download, link externo, Escape, não reabrir a cada poll e nova tentativa OK.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
