// D-211. Somente demonstração local. Não grava execução: as etapas são fixtures de renderização no navegador.
// URL=http://127.0.0.1:8765 PASTA=/tmp/contraste node ferramentas/desempenho/conferir_contraste_iluminado.cjs
// Precisa do Playwright/Chromium já usados nas ferramentas de desempenho. CHROME ou CHANNEL selecionam o navegador.
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),os=require('os'),assert=require('assert');
const pasta=process.env.PASTA||path.join(os.tmpdir(),'morro-contraste');fs.mkdirSync(pasta,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROME?{executablePath:process.env.CHROME}:{}),...(process.env.CHANNEL?{channel:process.env.CHANNEL}:{})});
 const resultados=[];
 for(const width of [390,1280]){
  const context=await browser.newContext({viewport:{width,height:900},reducedMotion:'reduce'});
  // Tiles de teste com ruas claras e construções: nenhum pedido automatizado ao OSM público.
  await context.route('https://tile.openstreetmap.org/**',r=>r.fulfill({status:200,contentType:'image/svg+xml',headers:{'Access-Control-Allow-Origin':'*'},
   body:'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e8e5de"/><path d="M0 55H256 M60 0V256 M0 175L256 70" stroke="#c9c6be" stroke-width="16"/><path d="M0 55H256 M60 0V256 M0 175L256 70" stroke="white" stroke-width="12"/><path d="M0 235Q120 200 256 240" stroke="#abc9df" stroke-width="8" fill="none"/></svg>'}));
  const page=await context.newPage(),erros=[];page.on('pageerror',e=>erros.push(e.message));
  await page.goto((process.env.URL||'http://127.0.0.1:8765')+'/#iluminado');
  await page.locator('#fLogin input[name=login]').fill('eng.demo');
  await page.locator('#fLogin input[name=senha]').fill('demo-morro-123');
  await page.locator('#fLogin button:not([type])').click();
  await page.waitForFunction(()=>ILU.pronto&&ILU.est);
  const info=await page.evaluate(()=>{
   ILU.est.camadas.etapas={};
   // Comparar topografia e não iniciado na mesma zona, com a geometria real do projeto.
   GERAL.trechos.filter(t=>zonaDoTrecho(t)==='Zona05').forEach((t,i)=>ILU.est.camadas.etapas[t.n]={s:i%4?'liberado':'nao'});
   colorirIluminado();focarZona('Zona05');
   const lum=hex=>{const a=hex.match(/\w\w/g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4));return .2126*a[0]+.7152*a[1]+.0722*a[2];};
   const cr=(a,b)=>(Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
   return {cores:SITU.map(s=>s.cor),ids:SITU.map(s=>s.id),contraste:cr(SITU_ID.liberado.cor,'D7E5E8'),contrasteAntigo:cr('9FD1F5','D7E5E8')};
  });
  assert.equal(new Set(info.cores).size,10);assert(info.contraste>=3&&info.contraste>2*info.contrasteAntigo,'topografia precisa contrastar com a zona clara');
  assert.deepEqual(info.ids,['nao','liberado','execucao','executado','verificado','campo','pronto','ok','cad_andamento','cadastrado']);
  await page.waitForTimeout(900);
  await page.locator('#ilu').screenshot({path:path.join(pasta,`topografia_${width}.png`)});
  const tracos=await page.evaluate(()=>{
   const p=s=>document.querySelector(`#iluLinhas [data-situ="${s}"]`),b=s=>document.querySelector(`#iluSvg .rede-contraste [data-situ="${s}"]`);
   return {ativo:parseFloat(getComputedStyle(p('liberado')).strokeWidth),inativo:parseFloat(getComputedStyle(p('nao')).strokeWidth),
    cor:getComputedStyle(p('liberado')).stroke,borda:parseFloat(getComputedStyle(b('liberado')).strokeWidth)};
  });
  assert(tracos.ativo>tracos.inativo&&tracos.borda>tracos.ativo);
  // O filtro precisa esconder também o contorno e a cópia do gesto.
  const filtro=await page.evaluate(()=>{
   ILU.vis.liberado=false;aplicarCamadas();desenharVista();
   const paths=[...document.querySelectorAll('#iluSvg [data-situ="liberado"]')];
   return paths.length>1&&paths.every(p=>getComputedStyle(p).display==='none');
  });assert(filtro,'contorno órfão ao esconder situação');
  await page.evaluate(()=>{ILU.vis.liberado=true;aplicarCamadas();desenharVista();});
  // Todas as etapas, a legenda e os quatro fundos usam a mesma paleta/contorno.
  await page.evaluate(()=>{
   GERAL.trechos.filter(t=>zonaDoTrecho(t)==='Zona05').forEach((t,i)=>ILU.est.camadas.etapas[t.n]={s:SITU[i%SITU.length].id});colorirIluminado();
  });
  for(const fundo of ['ruas','escura','clara','sem']){
   const linhas=await page.evaluate(fundo=>{
    ILU.fundo=fundo;aplicarCamadas();desenharVista();abrirPop('situacao',true);
    return SITU.map(s=>{const a=document.querySelector(`#iluLinhas [data-situ="${s.id}"]`),b=document.querySelector(`#iluSvg .rede-contraste [data-situ="${s.id}"]`),leg=document.querySelector(`[data-situ="${s.id}"] i`);
     return {id:s.id,linha:getComputedStyle(a).stroke,legenda:getComputedStyle(leg).borderTopColor,contorno:getComputedStyle(b.parentElement).display,borda:getComputedStyle(b).stroke};});
   },fundo);
   assert(linhas.every(l=>l.linha===l.legenda&&l.contorno!=='none'),'legenda ou contorno diferente no fundo '+fundo);
   assert.notEqual(linhas.find(l=>l.id==='pronto').borda,linhas.find(l=>l.id==='pronto').linha);
   if(fundo==='ruas')await page.locator('#ilu').screenshot({path:path.join(pasta,`etapas_${width}.png`)});
  }
  // A cópia leve pinta a faixa colorida e a borda em vez de apagar o destaque ao arrastar.
  const pixels=await page.evaluate(()=>{
   const cv=document.createElement('canvas');cv.width=120;cv.height=50;const g=cv.getContext('2d');
   g.fillStyle='#D7E5E8';g.fillRect(0,0,120,50);
   linhasCopia(g,1,[{cor:SITU_ID.liberado.cor,largura:larguraIlu(1,'liberado'),halo:'#FFFFFF',trechos:[{p:[[10,10.5,110,10.5]]}]}]);
   return {centro:[...g.getImageData(60,10,1,1).data],borda:[...g.getImageData(60,9,1,1).data],fundo:[...g.getImageData(60,5,1,1).data]};
  });assert.notDeepEqual(pixels.centro,pixels.fundo);assert.notDeepEqual(pixels.borda,pixels.fundo);
  await page.evaluate(()=>{ILU.pop=null;$('#popSituacao').hidden=true;ILU.fundo='ruas';aplicarCamadas();verTudo();});
  await page.waitForTimeout(500);await page.locator('#ilu').screenshot({path:path.join(pasta,`obra_inteira_${width}.png`)});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'rolagem horizontal');
  assert.deepEqual(erros,[]);
  resultados.push({width,contraste:info.contraste,contrasteAntigo:info.contrasteAntigo,tracos,filtro,pixels,erros});
  await context.close();
 }
 await browser.close();fs.writeFileSync(path.join(pasta,'resultado_contraste.json'),JSON.stringify(resultados,null,2));console.log(JSON.stringify(resultados));
})().catch(e=>{console.error(e);process.exit(1)});
