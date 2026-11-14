// Confere a tela do assistente (D-219) no navegador, em 390 e 1280 px: abre "O que você quer fazer?", percorre o
// exemplo de aceitação (dois contêineres no canteiro → Locação → sanitário por um mês → na verdade, foram três), confere
// o rascunho e grava pelo toque. Uso: node conferir_tela.cjs http://127.0.0.1:8791 [pasta das capturas]
// O servidor precisa estar de pé sobre um banco descartável (ferramentas/assistente/cenario.py) e com a chave da Groq.
const { chromium } = require('playwright');
const base = process.argv[2] || 'http://127.0.0.1:8791', pasta = process.argv[3] || '.';
const espera = ms => new Promise(ok => setTimeout(ok, ms));

async function sessao(navegador, largura, login) {
  const ctx = await navegador.newContext({ viewport: { width: largura, height: largura < 500 ? 844 : 900 } });
  const pg = await ctx.newPage(), erros = [];
  pg.on('pageerror', e => erros.push(String(e)));
  pg.on('console', m => { if (m.type() === 'error' && !/favicon|fonts\.g|ERR_|Failed to load resource/.test(m.text())) erros.push(m.text()); });
  await pg.goto(base + '/');
  await pg.fill('#login input[name=login]', login);
  await pg.fill('#login input[name=senha]', 'demo-morro-123');
  await pg.press('#login input[name=senha]', 'Enter');
  await pg.waitForSelector('#menuLista .menu-item');
  return { pg, erros, ctx };
}
async function semRolagemLateral(pg, onde) {
  const sobra = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (sobra > 1) throw new Error(`rolagem lateral de ${sobra}px em ${onde}`);
}
// manda a mensagem e espera a resposta; se a cota por minuto apertar, a própria tela conta e tenta de novo
async function dizer(pg, texto) {
  const antes = await pg.locator('#iaConversa .ia-msg.a:not(.ia-pensando)').count();
  await pg.fill('#iaTexto', texto);
  await pg.click('#iaEnviar');
  await pg.waitForFunction(n => document.querySelectorAll('#iaConversa .ia-msg.a:not(.ia-pensando)').length > n, antes, { timeout: 150000 });
}

(async () => {
  const navegador = await chromium.launch();
  const saida = [];
  for (const largura of [390, 1280]) {
    const { pg, erros, ctx } = await sessao(navegador, largura, 'eng.demo');
    await pg.click('.inicio-assistente');
    await pg.waitForSelector('#aba-assistente.ativa');
    const titulo = await pg.textContent('#aba-assistente h1');
    if (titulo.trim() !== 'O que você quer fazer?') throw new Error('título: ' + titulo);
    const atalhos = await pg.locator('#iaBotoes button').allTextContents();
    await semRolagemLateral(pg, `abertura ${largura}`);
    await pg.screenshot({ path: `${pasta}/assistente_${largura}_1_abertura.png`, fullPage: true });
    if (largura === 390) {
      await dizer(pg, 'Lança dois contêineres no canteiro');
      const opcoes = await pg.locator('#iaBotoes button').allTextContents();
      if (!opcoes.includes('Instalação') || !opcoes.includes('Locação')) throw new Error('opções: ' + opcoes.join(' | '));
      await pg.screenshot({ path: `${pasta}/assistente_${largura}_2_opcoes.png`, fullPage: true });
      await pg.click('#iaBotoes button:has-text("Locação")');
      const tipos = await pg.locator('#iaBotoes button').allTextContents();
      if (tipos.length !== 3) throw new Error('tipos de locação: ' + tipos.join(' | '));
      await dizer(pg, 'sanitário por um mês');
      await dizer(pg, 'na verdade, foram três');
      await pg.waitForSelector('#iaGravar:not([disabled])');
      const rascunho = await pg.textContent('#iaRascunho');
      for (const t of ['6.1.3', 'Canteiro', '3 contêineres × 1 mês = 3 MES']) if (!rascunho.includes(t)) throw new Error(`rascunho sem "${t}": ${rascunho}`);
      await semRolagemLateral(pg, `rascunho ${largura}`);
      await pg.screenshot({ path: `${pasta}/assistente_${largura}_3_rascunho.png`, fullPage: true });
      await pg.reload();                                 // o rascunho e a conversa sobrevivem a recarregar a página
      await pg.waitForSelector('#iaGravar:not([disabled])');
      await pg.click('#iaGravar');
      await pg.waitForFunction(() => /Gravado\. Apropriação nº \d+/.test(document.querySelector('#iaConversa').textContent), null, { timeout: 20000 });
      const fim = await pg.locator('#iaConversa .ia-msg.a').last().textContent();
      saida.push(`390 px: atalhos [${atalhos.join(' | ')}]; opções [${opcoes.join(' | ')}]; ${fim}`);
      await pg.screenshot({ path: `${pasta}/assistente_${largura}_4_gravado.png`, fullPage: true });
    } else {
      await pg.click('#iaBotoes button:has-text("Choveu")');          // atalho: começa o rascunho sem gastar a IA
      await pg.waitForSelector('#iaRascunho:not([hidden])');
      await pg.click('#iaBotoes button:has-text("Ankara")');             // para qual equipe
      await pg.click('#iaBotoes button:has-text("Tarde")');
      await pg.click('#iaBotoes button:has-text("Paralisou")');
      await pg.waitForSelector('#iaGravar:not([disabled])');
      await semRolagemLateral(pg, `rascunho ${largura}`);
      await pg.screenshot({ path: `${pasta}/assistente_${largura}_2_chuva.png`, fullPage: true });
      saida.push(`1280 px: atalhos [${atalhos.join(' | ')}]; rascunho de chuva montado só com toques`);
    }
    if (erros.length) throw new Error(`erros de JS em ${largura}px: ${erros.join(' ; ')}`);
    await ctx.close();
  }
  await navegador.close();
  console.log(saida.join('\n'));
  console.log('OK: tela do assistente conferida em 390 e 1280 px, sem erro de JS e sem rolagem lateral.');
})().catch(e => { console.error('FALHOU:', e.message); process.exit(1); });
