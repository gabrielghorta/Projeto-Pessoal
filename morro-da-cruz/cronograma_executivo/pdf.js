// Gantt em PDF A3 deitado: node pdf.js PASTA/ARQUIVO_GANTT.html ... (grava o .pdf ao lado de cada .html)
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1640, height: 1100 } });
  for (const f of process.argv.slice(2)) {
    await p.goto('file://' + require('path').resolve(f)); await p.waitForTimeout(300);
    await p.pdf({ path: f.replace(/\.html$/, '.pdf'), format: 'A3', landscape: true, printBackground: true });
  }
  await b.close();
})();
