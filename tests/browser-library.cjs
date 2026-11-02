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
  // Agrupar por artista (sem diferenciar maiúsculas) e filtrar pelo seletor.
  await page.getByLabel('Ordenar').selectOption('artist');
  await page.getByRole('heading',{level:3,name:/banda beta/i}).waitFor();
  assert.equal(await page.getByRole('heading',{level:3,name:/banda beta/i}).count(),1);
  // Campo de artista: nada antes do 3º caractere; depois sugere e filtra; Escape/× limpa.
  const picker=page.getByRole('combobox',{name:'Filtrar por artista'});
  await picker.fill('ba');
  const suggestions=page.getByRole('listbox',{name:'Artistas encontrados'});
  assert.equal(await suggestions.count(),0);
  await page.getByText('Digite pelo menos 3 letras.').waitFor();
  await picker.fill('BAN');
  await suggestions.getByRole('option',{name:/beta \(2\)/i}).waitFor();
  await picker.press('ArrowDown');await picker.press('Enter');
  await page.getByRole('button',{name:'Limpar filtro de artista'}).waitFor();
  await page.getByRole('button',{name:'Tocar Faixa Beta Um',exact:true}).waitFor();
  await page.getByRole('button',{name:'Tocar Áudio de teste local',exact:true}).waitFor({state:'detached'});
  await page.getByRole('button',{name:'Limpar filtro de artista'}).click();
  await page.getByRole('button',{name:'Tocar Áudio de teste local',exact:true}).waitFor();
  await page.getByLabel('Ordenar').selectOption('newest');
  // Miniatura local (capa) e enriquecimento individual.
  const cover=page.locator('img.cover').first();await cover.waitFor();
  await page.waitForFunction(()=>{const i=document.querySelector('img.cover');return i&&i.complete&&i.naturalWidth>0});
  assert.match(await page.locator('article',{has:cover}).innerText(),/Cantor Capa · 2017/);
  // Enriquecimento individual (endpoint simulado: sem rede). Não há botão em lote.
  assert.equal(await page.getByRole('button',{name:'Enriquecer biblioteca'}).count(),0);
  const requests=[];
  await page.route('**/api/library/*/enrich',async route=>{requests.push({method:route.request().method(),header:route.request().headers()['x-seletor-client']});await route.fulfill({json:{status:'ok'}})});
  await page.getByRole('button',{name:/Atualizar dados de Faixa Com Capa|Enriquecer Faixa Com Capa/}).click();
  await page.getByText(/Dados e capa de .*Faixa Com Capa.* atualizados/).waitFor();
  assert.deepEqual(requests,[{method:'POST',header:'1'}]);
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
