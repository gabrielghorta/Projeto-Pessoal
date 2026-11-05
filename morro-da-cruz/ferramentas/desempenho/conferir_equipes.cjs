// D-212: somente servidor de demonstração local. Cria pessoas/equipes sintéticas e as exclui ao terminar.
// URL=http://127.0.0.1:8765 CHANNEL=msedge PASTA=/tmp/equipes node ferramentas/desempenho/conferir_equipes.cjs
const {chromium}=require('playwright'),assert=require('assert'),fs=require('fs'),path=require('path'),os=require('os');
const pasta=process.env.PASTA||path.join(os.tmpdir(),'morro-equipes');fs.mkdirSync(pasta,{recursive:true});
(async()=>{
 const url=process.env.URL||'http://127.0.0.1:8765';assert(['127.0.0.1','localhost'].includes(new URL(url).hostname),'Use somente demonstração local');
 const browser=await chromium.launch({headless:true,...(process.env.CHANNEL?{channel:process.env.CHANNEL}:{})});
 const resultados=[];
 for(const width of [1280,390]){
  const context=await browser.newContext({viewport:{width,height:950},reducedMotion:'reduce'});
  await context.route('https://tile.openstreetmap.org/**',r=>r.fulfill({status:200,contentType:'image/svg+xml',headers:{'Access-Control-Allow-Origin':'*'},body:'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e8e5de"/><path d="M0 50H256 M50 0V256" stroke="white" stroke-width="15"/></svg>'}));
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url+'/#equipes');
  await page.locator('#fLogin input[name=login]').fill('eng.demo');await page.locator('#fLogin input[name=senha]').fill('demo-morro-123');
  await page.locator('#fLogin button:not([type])').click();
  await page.waitForSelector('#fNovaEquipe');
  await page.evaluate(async()=>{
   for(const e of EQUIPES_UI.dados.equipes.filter(e=>e.nome.startsWith('Equipe sintética '))) await api('/api/equipes/excluir',{equipe_id:e.id});
   await atualizarEquipes();await carregarEquipes();
  });
  assert.equal(await page.evaluate(()=>EQUIPES_UI.dados.equipes.length),0,'cadastro precisa começar vazio');
  await page.screenshot({path:path.join(pasta,`vazio_${width}.png`),fullPage:true});
  const criadas=[];
  for(const empresa of ['ANKARA','ANKARA','E1','E1','E2','E2']){
   await page.locator('#fNovaEquipe select[name=empresa]').selectOption(empresa);
   await page.locator('#fNovaEquipe input[name=nome]').fill('Equipe sintética '+(criadas.length+1));
   await page.locator('#fNovaEquipe button').click();
   await page.waitForFunction(n=>EQUIPES_UI.dados.equipes.length===n&&document.querySelector('#fEquipeMembro'),criadas.length+1);
   criadas.push(await page.evaluate(()=>EQUIPES_UI.id));
  }
  assert(criadas.every(id=>/^(A\d+|E[12]\.\d+)$/.test(id)));
  assert.equal(await page.evaluate(()=>RESUMO.equipes.filter(e=>e.integrantes).length),0);
  await page.evaluate(()=>abrirAba('mapa'));
  await page.waitForFunction(()=>PLN.pronto&&PLN.est);
  const escolha=await page.evaluate(()=>{
   const t=GERAL.trechos.findIndex(t=>zonaDoTrecho(t)==='Zona08');cliquePln(document.querySelector('#plnLinhas path'),{},t);
   cliquePln(document.querySelector('#plnLinhas path'),{},t);return PLN.equipe;
  });assert.equal(escolha,null,'zona não pode escolher uma equipe nova pelo código');
  await page.evaluate(()=>abrirAba('equipes'));await page.waitForSelector('#fNovaEquipe');
  for(let i=0;i<criadas.length;i++){
   await page.locator(`[data-eq-abrir="${criadas[i]}"]`).click();
   await page.waitForFunction(id=>EQUIPES_UI.id===id&&document.querySelector('#eqIntegrantes')?.dataset.equipe===id&&document.querySelector('#fEquipeMembro'),criadas[i]);
   await page.locator('#fEquipeMembro input[name=nome]').fill('Integrante sintético '+(i+1));
   await page.locator('#fEquipeMembro input[name=funcao]').fill(i?'Encanador':'Encarregado');
   await page.locator('#fEquipeMembro button').click();
   await page.waitForFunction(id=>EQUIPES_UI.dados.equipes.find(e=>e.id===id)?.integrantes===1,criadas[i]);
  }
  await page.screenshot({path:path.join(pasta,`compostas_${width}.png`),fullPage:true});
  assert.equal(await page.evaluate(()=>RESUMO.equipes.filter(e=>e.integrantes===1).length),6);
  const rotulos=await page.evaluate(ids=>ids.map(id=>rotuloEquipe(id)),criadas);assert.deepEqual(rotulos,criadas);
  await page.locator(`[data-eq-abrir="${criadas[0]}"]`).click();
  await page.waitForSelector('[data-eq-retirar]');await page.locator('[data-eq-retirar]').click();
  await page.waitForFunction(id=>EQUIPES_UI.dados.equipes.find(e=>e.id===id)?.integrantes===0,criadas[0]);
  await page.waitForFunction(()=>document.querySelector('#fEquipeMembro select[name=funcionario_id]')?.options.length>1);
  assert(await page.locator('#fEquipeMembro select[name=funcionario_id] option').count()>1);
  page.once('dialog',d=>d.accept());await page.locator('[data-eq-excluir]').click();
  await page.waitForFunction(()=>EQUIPES_UI.dados.equipes.length===5);
  assert(await page.evaluate(id=>!RESUMO.equipes.some(e=>e.id===id),criadas[0]));
  const semRolagem=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);assert(semRolagem);
  assert.deepEqual(errors,[]);
  // Limpeza apenas das equipes sintéticas deste teste; a exclusão conserva os históricos da cópia de QA.
  await page.evaluate(async ids=>{for(const id of ids)await api('/api/equipes/excluir',{equipe_id:id});},criadas.slice(1));
  resultados.push({width,criadas,rotulos,semRolagem,errors});await context.close();
 }
 await browser.close();fs.writeFileSync(path.join(pasta,'resultado_navegador.json'),JSON.stringify(resultados,null,2));console.log(JSON.stringify(resultados));
})().catch(e=>{console.error(e);process.exit(1)});
