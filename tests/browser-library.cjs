// Usar com: PYTHONPATH=. .venv/bin/python tests/serve_library_fixture.py
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});
 try{
  const context=await browser.newContext();const page=await context.newPage();const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const base='http://localhost:8767';await page.goto(base);
  await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
  await page.getByRole('button',{name:'Tocar Áudio de teste local',exact:true}).waitFor();
  await page.getByLabel('Buscar na biblioteca').fill('ARTISTA DE TESTE');
  await page.getByRole('button',{name:'Tocar Áudio de teste local',exact:true}).waitFor();
  await page.getByRole('button',{name:'Tocar Áudio de teste local',exact:true}).click();
  await page.waitForFunction(()=>{const a=document.querySelector('audio');return a&&!a.paused&&a.currentTime>.2});
  await page.evaluate(()=>{document.querySelector('audio').currentTime=6;document.querySelector('audio').volume=.4});
  await page.waitForFunction(()=>document.querySelector('audio').currentTime>=6);
  await page.getByRole('button',{name:'Selecionar',exact:true}).click();
  const position=await page.locator('audio').evaluate(a=>a.currentTime);
  await page.waitForTimeout(350);
  assert.equal(await page.locator('audio').evaluate(a=>!a.paused&&a.currentTime>6),true);
  assert.ok(await page.locator('audio').evaluate(a=>a.currentTime)>position);
  await page.getByRole('button',{name:'Downloads',exact:true}).click();
  assert.equal(await page.locator('audio').evaluate(a=>a.volume),.4);
  // Áudio já servido localmente não exige acesso a domínios externos.
  await context.route('**/*',route=>new URL(route.request().url()).hostname==='localhost'?route.continue():route.abort());
  await page.locator('audio').evaluate(a=>a.pause());
  await page.locator('audio').evaluate(a=>a.play());
  await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
  await page.getByRole('button',{name:'Atualizar biblioteca',exact:true}).click();
  await page.getByRole('button',{name:'Tocar Áudio de teste local',exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:'/tmp/seletor-library.png',fullPage:true});
  await page.route('**/api/library/*/audio',route=>route.fulfill({status:404,json:{detail:'Arquivo ausente'}}));
  await page.getByRole('button',{name:'Tocar Áudio de teste local',exact:true}).click();
  await page.locator('.player .error').filter({hasText:'Não foi possível'}).waitFor();
  assert.deepEqual(errors,[]);
  console.log('Biblioteca: áudio real, busca, seek, volume, navegação sem interrupção, atualização, falha e tela pequena OK.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
