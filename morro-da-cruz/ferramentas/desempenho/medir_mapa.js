// Mede a fluidez dos dois mapas (Mapa iluminado e Dados da obra) nos gestos de quem usa: arrastar, zoom com touchpad e
// com a roda do mouse, pinça no celular, focar zona e ver a obra inteira. Fora da suíte Python: precisa de Node, Playwright e
// Chromium. Uso, com o servidor de demonstração aberto (python demo.py ou server.py --demonstracao):
//
//   NODE_PATH=$(npm root -g) node ferramentas/desempenho/medir_mapa.js
//   CONDICAO=B NODE_PATH=$(npm root -g) node ferramentas/desempenho/medir_mapa.js
//
// Condições (seção 5.0 do prompt dos mapas fluidos):
//   A: computador do responsável: 1600×930, escala 1,25 (= 2000 px), CPU 4×, mouse e touchpad;
//   B: celular: 390×844, escala 3, CPU 6×, toque (arrastar com um dedo e pinça com dois).
// Variáveis: URL, CONDICAO (A|B), TELAS (iluminado,mapa), ROTULO, GPU=1 (liga window.__GPU do protótipo antigo),
// CHROME (caminho do Chromium), JSON (arquivo para gravar os números), USUARIO e SENHA.
// Cuidado: em tela pequena, sem escala e com CPU rápida a rasterização some da medição e tudo parece fluido.
const { chromium } = require('playwright');

const COND = (process.env.CONDICAO || 'A').toUpperCase();
const PADRAO = { A: { W: 1600, H: 930, DPR: 1.25, CPU: 4, toque: false }, B: { W: 390, H: 844, DPR: 3, CPU: 6, toque: true } }[COND];
const URL = process.env.URL || 'http://127.0.0.1:8791';
const W = +(process.env.W || PADRAO.W), H = +(process.env.H || PADRAO.H);
const DPR = +(process.env.DPR || PADRAO.DPR), CPU = +(process.env.CPU || PADRAO.CPU);
const TELAS = (process.env.TELAS || 'iluminado,mapa').split(',');
const ROTULO = process.env.ROTULO || URL;
const espera = ms => new Promise(ok => setTimeout(ok, ms));

// soma do trace por etapa do navegador (thread principal, rasterização, decodificação de imagem)
function resumoTrace(buf) {
  const ev = JSON.parse(buf.toString()).traceEvents || [];
  const nomes = {};
  ev.filter(e => e.ph === 'M' && e.name === 'thread_name').forEach(e => { nomes[`${e.pid}:${e.tid}`] = e.args.name; });
  const soma = {};
  const add = (k, d) => { soma[k] = (soma[k] || 0) + d / 1000; };
  for (const e of ev) {
    if (e.ph !== 'X' || !e.dur) continue;
    const th = nomes[`${e.pid}:${e.tid}`] || '';
    if (th === 'CrRendererMain') {
      if (e.name === 'UpdateLayoutTree') add('estilo', e.dur);
      else if (e.name === 'Layout') add('layout', e.dur);
      else if (e.name === 'PrePaint') add('pré-pintura', e.dur);
      else if (e.name === 'Paint') add('pintura', e.dur);
      else if (e.name === 'Layerize' || e.name === 'Commit') add('camadas', e.dur);
      else if (e.name === 'FunctionCall' || e.name === 'TimerFire' || e.name === 'FireAnimationFrame' || e.name === 'EventDispatch') add('script', e.dur);
    } else if (/CompositorTileWorker|ThreadPoolForegroundWorker/.test(th)) {
      if (/RasterTask|TileManager::RunRasterTask/.test(e.name)) add('rasterização', e.dur);
      if (/ImageDecode|Decode Image/.test(e.name)) add('decodificação', e.dur);
    }
  }
  // quadros apresentados pelo compositor (o que a pessoa vê): numa animação que roda no compositor, a thread principal
  // pode ficar parada e o requestAnimationFrame não conta os quadros
  const sw = ev.filter(e => e.name === 'Display::DrawAndSwap' && e.ph === 'X').map(e => e.ts).sort((a, b) => a - b);
  const ints = sw.slice(1).map((t, i) => (t - sw[i]) / 1000);
  soma.__tela = { n: sw.length, lentos: ints.filter(x => x > 50).length, max: Math.max(0, ...ints), p90: [...ints].sort((a, b) => a - b)[Math.floor(ints.length * 0.9)] || 0 };
  return soma;
}
const textoTrace = soma => Object.entries(soma).filter(([k]) => k !== '__tela').sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v.toFixed(0)}`).join(' · ') + ' ms';

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined, args: ['--headless=new'] });
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: DPR, hasTouch: PADRAO.toque, isMobile: PADRAO.toque });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  const erros = [], pedidos = [];
  page.on('pageerror', e => erros.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !/401/.test(m.text())) erros.push(m.text()); });
  page.on('request', r => pedidos.push(r.url()));
  await page.goto(URL);
  await page.fill('#fLogin input[name=login]', process.env.USUARIO || 'admin.demo');
  await page.fill('#fLogin input[name=senha]', process.env.SENHA || 'demo-morro-123');
  await page.click('#fLogin > .acoes > button.btn.prim');
  await page.waitForTimeout(1500);
  if (process.env.GPU) await page.evaluate(() => { window.__GPU = true; });
  const saida = { rotulo: ROTULO, condicao: COND, W, H, DPR, CPU, telas: {} };

  for (const tela of TELAS) {
    const svgSel = tela === 'iluminado' ? '#iluSvg' : '#plnSvg', p = tela === 'iluminado' ? 'ilu' : 'pln';
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });
    pedidos.length = 0;
    await page.evaluate(t => { location.hash = '#' + t; }, tela);
    await page.waitForSelector(svgSel, { state: 'visible' }); await page.waitForTimeout(5000);
    const pedidosSat = pedidos.filter(u => /\/mapa\/(pb\/|geral\.webp)/.test(u)).length;
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: CPU });
    const n = await page.evaluate(s => document.querySelectorAll(`${s} *`).length, svgSel);
    const b = await page.locator(svgSel).boundingBox(), cx = b.x + b.width / 2, cy = b.y + b.height / 2;
    const alvo = await page.evaluate(p => {             // aproxima sobre a Zona 03, que tem trechos
      const t = [...document.querySelectorAll(`#${p}Nomes text`)].find(x => x.textContent.includes('03'));
      const r = t.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2 + 30];
    }, p);

    // gestos de mouse e touchpad (condição A)
    const arrastarMouse = async () => {
      await page.mouse.move(cx, cy); await page.mouse.down();
      for (let i = 1; i <= 10; i++) await page.mouse.move(cx - i * 18, cy - i * 10);
      await page.mouse.up();
    };
    const touchpad = dy => page.evaluate(([sel, x, y, dy]) => new Promise(ok => {   // 4 eventos de roda por quadro
      const svg = document.querySelector(sel); let k = 0;
      const tic = () => {
        for (let j = 0; j < 4 && k < 80; j++, k++) svg.dispatchEvent(new WheelEvent('wheel', { deltaY: dy, clientX: x, clientY: y, bubbles: true, cancelable: true }));
        if (k < 80) setTimeout(tic, 16); else ok();
      };
      tic();
    }), [svgSel, alvo[0], alvo[1], dy]);
    const roda = dy => page.evaluate(([sel, x, y, dy]) => new Promise(ok => {       // mouse: um "clique" de roda a cada 60 ms
      const svg = document.querySelector(sel); let k = 0;
      const tic = () => {
        svg.dispatchEvent(new WheelEvent('wheel', { deltaY: dy, clientX: x, clientY: y, bubbles: true, cancelable: true }));
        if (++k < 12) setTimeout(tic, 60); else ok();
      };
      tic();
    }), [svgSel, alvo[0], alvo[1], dy]);
    // gestos de toque (condição B), pelo protocolo do DevTools: viram pointer events com pointerType "touch"
    const toque = (type, pts) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
    const arrastarDedo = async () => {
      await toque('touchStart', [[cx, cy]]);
      for (let i = 1; i <= 12; i++) { await toque('touchMove', [[cx - i * 8, cy - i * 12]]); await espera(16); }
      await toque('touchEnd', []);
    };
    const pinca = abrir => async () => {              // dois dedos em volta do alvo, abrindo (aproximar) ou fechando
      const [x, y] = alvo, d0 = abrir ? 30 : 150, d1 = abrir ? 150 : 30;
      await toque('touchStart', [[x - d0, y], [x + d0, y]]);
      for (let i = 1; i <= 20; i++) { const d = d0 + (d1 - d0) * i / 20; await toque('touchMove', [[x - d, y], [x + d, y]]); await espera(16); }
      await toque('touchEnd', []);
    };
    const chamar = js => () => page.evaluate(js);
    const fimAnimacao = () => page.waitForTimeout(700);
    const focar = tela === 'iluminado' ? "focarZona('Zona03')" : "focarZonaPln('Zona03')";
    const tudo = tela === 'iluminado' ? 'verTudo()' : 'verTudoPln()';
    const gestos = PADRAO.toque ? [
      ['arrastar de longe (dedo)', arrastarDedo], ['pinça (aproximar)', pinca(true)], ['arrastar de perto (dedo)', arrastarDedo],
      ['pinça (afastar)', pinca(false)], ['focar zona', async () => { await chamar(focar)(); await fimAnimacao(); }],
      ['ver a obra inteira', async () => { await chamar(tudo)(); await fimAnimacao(); }],
    ] : [
      ['arrastar de longe', arrastarMouse], ['zoom touchpad (aproximar)', () => touchpad(-14)], ['arrastar de perto', arrastarMouse],
      ['zoom touchpad (afastar)', () => touchpad(14)], ['zoom roda do mouse (aproximar)', () => roda(-100)],
      ['zoom roda do mouse (afastar)', () => roda(100)], ['focar zona', async () => { await chamar(focar)(); await fimAnimacao(); }],
      ['ver a obra inteira', async () => { await chamar(tudo)(); await fimAnimacao(); }],
    ];
    console.log(`\n== ${ROTULO} · ${tela} · ${n} elementos no SVG · ${pedidosSat} pedidos de satélite ao abrir · tela ${W}×${H} @${DPR}x · CPU ${CPU}× · condição ${COND}`);
    saida.telas[tela] = { elementos: n, pedidos_satelite: pedidosSat, gestos: {} };
    // marca o que causou cada quadro: o redesenho de verdade (desenharVista) e a foto da PB em resolução cheia entrando
    // ou saindo do satélite (depois que o mapa para)
    await page.evaluate(p => {
      window.__red = []; window.__foto = [];
      if (!window.__marcado) {
        window.__marcado = true;
        const orig = desenharVista;
        window.desenharVista = function () { window.__red.push(performance.now()); return orig.apply(this, arguments); };
      }
      const sat = document.querySelector(`#${p}Sat .sat-detalhe`);
      if (sat && !sat.__obs) { sat.__obs = new MutationObserver(() => window.__foto.push(performance.now())); sat.__obs.observe(sat, { childList: true }); }
    }, p);
    for (const [nome, acao] of gestos) {
      // quadros (requestAnimationFrame) e, a cada quadro, se a área visível está toda desenhada (o visor diz por
      // descoberto(ctx), quando existe)
      await page.evaluate(p => {
        window.__q = []; window.__on = true; window.__vazio = []; window.__red = []; window.__foto = []; let ult = performance.now();
        const ctx = p === 'ilu' ? ILU : PLN;
        const f = t => {
          if (!window.__on) return;
          window.__q.push([t, t - ult]); ult = t;
          if (typeof descoberto === 'function') window.__vazio.push([t, descoberto(ctx)]);
          requestAnimationFrame(f);
        };
        requestAnimationFrame(f);
      }, p);
      await browser.startTracing(page, { categories: ['devtools.timeline', 'disabled-by-default-devtools.timeline', 'cc', 'viz', 'toplevel'] });
      const t0 = await page.evaluate(() => performance.now());
      await acao();
      const tFim = await page.evaluate(() => performance.now());
      await page.waitForTimeout(600);                 // o redesenho ao soltar (150 ms depois do último evento) e a foto da PB
      const buf = await browser.stopTracing();
      const r = await page.evaluate(([t0, tFim]) => {
        window.__on = false;
        const q = window.__q.slice(2), dentro = (lista, t, d) => lista.some(x => x >= t - d - 1 && x <= t);
        const causa = ([t, d]) => dentro(window.__red, t, d) ? 'redesenho' : dentro(window.__foto, t, d) ? 'foto' : 'gesto';
        const dur = q.filter(([t]) => t <= tFim).map(x => x[1]);
        // o redesenho ao soltar: o quadro de redesenho depois do último evento do gesto
        const red = q.filter(([t, d]) => t > tFim && causa([t, d]) === 'redesenho').map(x => x[1]);
        let vazioMax = 0, ini = null;                  // maior trecho contínuo com área vazia à vista
        for (const [t, v] of window.__vazio) { if (v > 0.01) { if (ini == null) ini = t; vazioMax = Math.max(vazioMax, t - ini); } else ini = null; }
        const lentosEm = q.filter(([, d]) => d > 50).map(x => [Math.round(x[0] - t0), Math.round(x[1]), causa(x)]);
        const rel = l => l.map(x => Math.round(x - t0));
        return { dur, red, max: Math.max(0, ...q.map(x => x[1])), vazioMax, total: tFim - t0, lentosEm, redEm: rel(window.__red), fotoEm: rel(window.__foto) };
      }, [t0, tFim]);
      const ord = [...r.dur].sort((a, c) => a - c), pct = k => ord.length ? ord[Math.min(ord.length - 1, Math.floor(ord.length * k))] : 0;
      const conta = c => r.lentosEm.filter(x => x[2] === c).length;
      const lentos = { gesto: conta('gesto'), redesenho: conta('redesenho'), foto: conta('foto') };
      const redesenho = r.red.length ? Math.max(...r.red) : 0;
      const trace = resumoTrace(buf);
      saida.telas[tela].gestos[nome] = { lentos, p50: pct(0.5), p90: pct(0.9), max: r.max, redesenho, vazio_ms: r.vazioMax, total: r.total, lentos_em: r.lentosEm, trace };
      console.log(`  ${nome.padEnd(30)} quadros > 50 ms: ${lentos.gesto} no gesto, ${lentos.redesenho} de redesenho, ${lentos.foto} da foto da PB · p50 ${pct(0.5).toFixed(0)} · p90 ${pct(0.9).toFixed(0)} · máx ${r.max.toFixed(0)} · redesenho ao soltar ${redesenho.toFixed(0)} ms · área vazia ${r.vazioMax.toFixed(0)} ms`);
      const tl = trace.__tela; delete trace.__tela;
      saida.telas[tela].gestos[nome].tela = tl;
      console.log(`  ${''.padEnd(30)} na tela (compositor): ${tl.n} quadros apresentados · ${tl.lentos} intervalos > 50 ms · p90 ${tl.p90.toFixed(0)} · máx ${tl.max.toFixed(0)} ms`);
      console.log(`  ${''.padEnd(30)} ${textoTrace(trace)}`);
      if (process.env.DETALHE) console.log(`  ${''.padEnd(30)} quadros lentos [ms desde o começo, duração, causa]: ${JSON.stringify(r.lentosEm)} · gesto durou ${r.total.toFixed(0)} ms · desenhos em ${JSON.stringify(r.redEm)} · foto da PB em ${JSON.stringify(r.fotoEm)}`);
      await page.waitForTimeout(800);
    }
  }
  saida.erros = erros;
  console.log(`\nerros no console: ${erros.length ? erros.join(' | ') : 'nenhum'}`);
  if (process.env.JSON) require('fs').writeFileSync(process.env.JSON, JSON.stringify(saida, null, 1));
  await browser.close();
})();
