// D-209: usa só a demonstração local, com tiles interceptados (nenhuma varredura no serviço público).
// Inicie python demo.py --porta 8765. Precisa do Node/Playwright/Chromium já usados pelas ferramentas de desempenho.
// URL=http://127.0.0.1:8765 CHROME=/caminho/do/chromium PASTA=/tmp/mapa node ferramentas/desempenho/conferir_mapa_ruas.cjs
const {chromium} = require('playwright');
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert');
const PASTA=process.env.PASTA || path.join(os.tmpdir(),'morro-mapa-ruas');fs.mkdirSync(PASTA,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME || undefined,headless:true});
 const out=[];
 for(const width of [390,1280]){
  const context=await browser.newContext({viewport:{width,height:900},reducedMotion:'reduce'});
  let offline=false; const pedidos=[];
  // Nenhum pedido ao servidor público do OSM durante testes automatizados de zoom/arrasto.
  await context.route('https://tile.openstreetmap.org/**',async route=>{
   pedidos.push(route.request().url());
   if(offline)return route.abort('internetdisconnected');
   return route.fulfill({status:200,headers:{'Access-Control-Allow-Origin':'*'},contentType:'image/svg+xml',
    body:'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e8e5de"/><path d="M0 55H256 M60 0V256 M0 175L256 70" stroke="#c9c6be" stroke-width="16"/><path d="M0 55H256 M60 0V256 M0 175L256 70" stroke="white" stroke-width="12"/><path d="M0 235Q120 200 256 240" stroke="#abc9df" stroke-width="8" fill="none"/></svg>'});
  });
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto((process.env.URL || 'http://127.0.0.1:8765') + '/#iluminado');
  await page.locator('#fLogin input[name=login]').fill('eng.demo');
  await page.locator('#fLogin input[name=senha]').fill('demo-morro-123');
  await page.locator('#fLogin button:not([type])').click();
  await page.waitForFunction(()=>ILU.pronto&&ILU.est);
  await page.locator('#iluRuas image').first().waitFor();
  await page.waitForTimeout(600);
  assert.equal(await page.evaluate(()=>ILU.fundo),'ruas');
  assert.equal(await page.locator('#ilu .mapa-credito').isVisible(),true);
  assert.equal(await page.locator('#iluRuas').getAttribute('clip-path'),null);
  await page.screenshot({path:path.join(PASTA,`iluminado_${width}.png`),fullPage:true});
  await page.locator('#iluSvg .mapa-canteiro').click();
  await page.waitForTimeout(300);
  assert.equal(await page.locator('#iluSvg .mapa-canteiro').evaluate(e=>e.classList.contains('destacado')),true);
  assert.equal(await page.evaluate(()=>ILU.vb[2]<(ILU.base[2]-ILU.base[0])*.2),true);
  await page.evaluate(()=>verTudo());
  await page.evaluate(()=>abrirAba('mapa'));
  await page.waitForFunction(()=>PLN.pronto&&PLN.est);
  await page.locator('#plnRuas image').first().waitFor();
  assert.equal(await page.evaluate(()=>PLN.corPor),'de');
  const selecao=await page.evaluate(async()=>{
   const i=GERAL.trechos.findIndex(t=>zonaDoTrecho(t)==='Zona08'),alvo=document.querySelector('#plnLinhas path');
   cliquePln(alvo,{},i);const aberto=[PLN.zona,PLN.sel.length];
   cliquePln(alvo,{},i);cliquePln(alvo,{},i);await new Promise(r=>setTimeout(r,600));
   return {aberto,selecionados:PLN.sel.length,equipe:PLN.equipe};
  });
  assert.deepEqual(selecao.aberto,['Zona08',0]); assert.equal(selecao.selecionados,1); assert.equal(selecao.equipe,'Zona08');
  await page.evaluate(()=>{PLN.corPor='plan';colorirPln();});
  assert.equal(await page.evaluate(()=>PLN.corPor),'plan');
  await page.evaluate(()=>{PLN.corPor='de';colorirPln();});
  await page.evaluate(()=>irPara(PLN.base,false,PLN));
  await page.locator('#plnSvg .mapa-canteiro').click();
  assert.equal(await page.evaluate(()=>PLN.sel.length),1);
  await page.evaluate(()=>{PLN.zona=null;zonasPln();colorirPln();irPara(PLN.base,false,PLN);});
  await page.waitForTimeout(800);
  await page.screenshot({path:path.join(PASTA,`programacao_${width}.png`),fullPage:true});
  const semRolagem=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);
  assert(semRolagem,'rolagem horizontal');
  // Sem internet em uma área/nível ainda não visitado: a rede fica interativa e a falha fica explícita.
  offline=true;
  await page.evaluate(()=>{const x=PLN.base[0]+700,y=PLN.base[1]+1400;irPara([x,y,x+100,y+100],false,PLN);});
  await page.locator('#plnMapa .mapa-fundo-aviso').waitFor({state:'visible'});
  assert(await page.locator('#plnLinhas path').count()>0);
  offline=false;await page.locator('#plnMapa .mapa-fundo-aviso button').click();
  await page.locator('#plnMapa .mapa-fundo-aviso').waitFor({state:'hidden'});
  const antes=pedidos.length; await page.waitForTimeout(800);assert.equal(pedidos.length,antes,'pedido repetido parado');
  assert.deepEqual(errors,[]);
  out.push({width,semRolagem,selecao,tiles:pedidos.length,errors});await context.close();
 }
 await browser.close();fs.writeFileSync(path.join(PASTA,'navegador_resultado.json'),JSON.stringify(out,null,2));console.log(JSON.stringify(out));
})().catch(e=>{console.error(e);process.exit(1)});
