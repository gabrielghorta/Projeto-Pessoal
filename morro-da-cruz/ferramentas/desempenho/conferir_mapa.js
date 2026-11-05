// Confere que a otimização não mudou o mapa parado nem o clique: compara, pixel a pixel, o mapa de dois servidores
// (o código de partida e o novo) depois dos mesmos gestos, e confere que o clique num trecho conhecido abre a ficha
// (Mapa iluminado) ou escolhe o trecho (Dados da obra). Fora da suíte Python: precisa de Node, Playwright e Chromium.
//
//   ANTES=http://127.0.0.1:8790 DEPOIS=http://127.0.0.1:8791 NODE_PATH=$(npm root -g) node ferramentas/desempenho/conferir_mapa.js
//
// Variáveis: ANTES, DEPOIS, CHROME (caminho do Chromium), PASTA (onde gravar as capturas), TOLERANCIA (fração de pixels
// diferentes aceita; padrão 0,002), USUARIO e SENHA.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const ANTES = process.env.ANTES || 'http://127.0.0.1:8790', DEPOIS = process.env.DEPOIS || 'http://127.0.0.1:8791';
const PASTA = process.env.PASTA || '.', TOL = +(process.env.TOLERANCIA || 0.002);

async function abrir(browser, url) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 930 }, deviceScaleFactor: 1.25 });
  const page = await ctx.newPage();
  const erros = [];
  page.on('pageerror', e => erros.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !/401/.test(m.text())) erros.push(m.text()); });
  await page.goto(url);
  await page.fill('#fLogin input[name=login]', process.env.USUARIO || 'admin.demo');
  await page.fill('#fLogin input[name=senha]', process.env.SENHA || 'demo-morro-123');
  await page.click('#fLogin > .acoes > button.btn.prim');
  await page.waitForTimeout(1500);
  return { ctx, page, erros };
}
// os mesmos gestos nas duas versões: o visor faz a mesma conta, então a vista final é a mesma
const ROTEIRO = [
  ['obra inteira', null],
  ['zona 03', (p, mapa) => p.evaluate(m => (m === 'ILU' ? focarZona('Zona03') : focarZonaPln('Zona03')), mapa)],
  ['zoom touchpad de perto', (p, mapa) => p.evaluate(([m, n]) => new Promise(ok => {
    const svg = document.querySelector(m === 'ILU' ? '#iluSvg' : '#plnSvg'), r = svg.getBoundingClientRect(); let k = 0;
    const tic = () => { for (let j = 0; j < 4 && k < n; j++, k++) svg.dispatchEvent(new WheelEvent('wheel', { deltaY: -14, clientX: r.x + r.width * 0.45, clientY: r.y + r.height * 0.55, bubbles: true, cancelable: true }));
      if (k < n) setTimeout(tic, 16); else ok(); };
    tic();
  }), [mapa, 120])],
  ['arrastar de perto', async (p, mapa) => {
    const b = await p.locator(mapa === 'ILU' ? '#iluSvg' : '#plnSvg').boundingBox(), cx = b.x + b.width / 2, cy = b.y + b.height / 2;
    await p.mouse.move(cx, cy); await p.mouse.down();
    for (let i = 1; i <= 10; i++) await p.mouse.move(cx - i * 30, cy - i * 12);
    await p.mouse.up();
  }],
];
// fração de pixels que diferem mais que 24 níveis em algum canal
const comparar = (page, a, b) => page.evaluate(async ([a, b]) => {
  const ler = src => new Promise(ok => { const im = new Image(); im.onload = () => ok(im); im.src = 'data:image/png;base64,' + src; });
  const [ia, ib] = await Promise.all([ler(a), ler(b)]);
  const px = im => { const c = document.createElement('canvas'); c.width = im.width; c.height = im.height; const g = c.getContext('2d'); g.drawImage(im, 0, 0); return g.getImageData(0, 0, im.width, im.height).data; };
  const da = px(ia), db = px(ib); let dif = 0;
  for (let i = 0; i < da.length; i += 4) if (Math.abs(da[i] - db[i]) > 24 || Math.abs(da[i + 1] - db[i + 1]) > 24 || Math.abs(da[i + 2] - db[i + 2]) > 24) dif++;
  return dif / (da.length / 4);
}, [a.toString('base64'), b.toString('base64')]);

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined, args: ['--headless=new'] });
  const versoes = [await abrir(browser, ANTES), await abrir(browser, DEPOIS)];
  let falhas = 0;
  for (const [tela, mapa] of [['iluminado', 'ILU'], ['mapa', 'PLN']]) {
    for (const v of versoes) { await v.page.evaluate(t => { location.hash = '#' + t; }, tela); }
    await Promise.all(versoes.map(v => v.page.waitForTimeout(4000)));
    for (const [nome, gesto] of ROTEIRO) {
      const caps = [];
      for (const v of versoes) {
        if (gesto) await gesto(v.page, mapa);
        await v.page.waitForTimeout(3000);                 // redesenho ao soltar e fotos do satélite em resolução cheia
        // textos e tracejado na escala exata: o código de partida redesenhava a cada quadro e guardava a escala de um
        // quadro até 2 % antes do fim (escalaMudou); sem isso a comparação acusa diferença de subpixel
        await v.page.evaluate(m => { const c = m === 'ILU' ? ILU : PLN; c.ultPx = 0; desenharVista(c); }, mapa);
        await v.page.waitForTimeout(400);
        const caixa = await v.page.evaluate(m => { const r = (m === 'ILU' ? ILU : PLN).caixa().getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; }, mapa);
        caps.push(await v.page.screenshot({ clip: caixa }));
      }
      const dif = await comparar(versoes[1].page, caps[0], caps[1]);
      const ok = dif <= TOL; if (!ok) falhas++;
      const arq = nome.replace(/\W+/g, '_');
      fs.writeFileSync(path.join(PASTA, `${tela}_${arq}_antes.png`), caps[0]); fs.writeFileSync(path.join(PASTA, `${tela}_${arq}_depois.png`), caps[1]);
      console.log(`${ok ? 'igual    ' : 'DIFERENTE'} ${tela} · ${nome}: ${(dif * 100).toFixed(3)} % dos pixels`);
    }
    // clique num trecho conhecido, com a Zona 03 à vista: o do meio da lista de trechos visíveis, no ponto do meio da linha
    for (const v of versoes) { await ROTEIRO[1][1](v.page, mapa); await v.page.waitForTimeout(1500); }
    for (const v of versoes) {
      const alvo = await v.page.evaluate(m => {
        const c = m === 'ILU' ? ILU : PLN, r = c.caixa().getBoundingClientRect(), [x, y, w, h] = c.vb;
        const vis = GERAL.trechos.filter(t => { const p = t.p[0], mx = p[Math.floor(p.length / 4) * 2], my = p[Math.floor(p.length / 4) * 2 + 1];
          return mx > x + w * 0.2 && mx < x + w * 0.8 && my > y + h * 0.2 && my < y + h * 0.8 && (!t.s || m !== 'ILU' || ILU.vis[t.s]); });
        if (!vis.length) return null;
        const t = vis[Math.floor(vis.length / 2)], p = t.p[0], j = Math.floor(p.length / 4) * 2;
        const mx = (p[j] + p[j + 2 < p.length ? j + 2 : j]) / 2, my = (p[j + 1] + p[j + 3 < p.length ? j + 3 : j + 1]) / 2;
        return { nome: t.n, cx: r.x + (mx - x) / w * r.width, cy: r.y + (my - y) / h * r.height };
      }, mapa);
      if (!alvo) { falhas++; console.log(`SEM TRECHO ${tela}: nenhum trecho no meio da vista`); continue; }
      alvo.sob = await v.page.evaluate(([x, y]) => { const e = document.elementFromPoint(x, y); return e ? e.tagName + '.' + (e.getAttribute('class') || e.id) : '-'; }, [alvo.cx, alvo.cy]);
      await v.page.mouse.click(alvo.cx, alvo.cy);
      await v.page.waitForTimeout(1200);
      const res = await v.page.evaluate(m => m === 'ILU' ? (ILU.sel && ILU.sel.nome) || (document.querySelector('#iluFicha:not([hidden])') || {}).textContent || '' : PLN.sel.join(','), mapa);
      const ok = String(res).includes(alvo.nome); if (!ok) falhas++;
      console.log(`${ok ? 'certo    ' : 'ERRADO   '} ${tela} · clique em ${alvo.nome} (${v === versoes[0] ? 'antes' : 'depois'}; sob o cursor ${alvo.sob}): ${String(res).slice(0, 80).replace(/\s+/g, ' ')}`);
    }
  }
  versoes.forEach((v, i) => console.log(`erros no console (${i ? 'depois' : 'antes'}): ${v.erros.join(' | ') || 'nenhum'}`));
  console.log(falhas ? `${falhas} conferência(s) falharam` : 'tudo igual e todos os cliques certos');
  await browser.close();
  process.exit(falhas ? 1 : 0);
})();
