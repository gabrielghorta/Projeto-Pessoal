// Confere no navegador o que a pessoa vê quando a cota gratuita da IA acaba (D-220), em 390 e 1280 px: o aviso, o texto
// que ela escreveu ainda na caixa, o rascunho guardado, os botões do formulário manual e a gravação pelo próprio
// rascunho, sem a IA. Uso: node conferir_cota.cjs http://127.0.0.1:8791 [pasta das capturas]
// Rode com a cota realmente esgotada (o 429 é o da Groq) ou com o servidor sem chave (a tela trata igual: avisa e segue).
const { chromium } = require('playwright');
const base = process.argv[2] || 'http://127.0.0.1:8791', pasta = process.argv[3] || '.';

(async () => {
  const navegador = await chromium.launch(), saida = [];
  for (const [largura, login] of [[390, 'eng.demo'], [1280, 'eng2.demo']]) {
    const ctx = await navegador.newContext({ viewport: { width: largura, height: largura < 500 ? 844 : 900 } });
    const pg = await ctx.newPage(), erros = [];
    pg.on('pageerror', e => erros.push(String(e)));
    await pg.goto(base + '/');
    await pg.fill('#login input[name=login]', login);
    await pg.fill('#login input[name=senha]', 'demo-morro-123');
    await pg.press('#login input[name=senha]', 'Enter');
    await pg.waitForSelector('#menuLista .menu-item');
    await pg.click('.rail-item[data-tela="assistente"], .inicio-assistente >> visible=true');
    await pg.waitForSelector('#aba-assistente.ativa');
    await pg.click('#iaBotoes button:has-text("Lançar um serviço")');       // atalho: abre o rascunho sem a IA
    await pg.waitForSelector('#iaRascunho:not([hidden])');
    const frase = 'foram dois contêineres instalados no canteiro';
    await pg.fill('#iaTexto', frase);
    await pg.click('#iaEnviar');
    await pg.waitForSelector('#iaAviso:not([hidden])', { timeout: 60000 });
    const aviso = (await pg.textContent('#iaAviso')).replace(/\s+/g, ' ').trim();
    if (!/gratuit|ainda não foi ligada/.test(aviso)) throw new Error('aviso inesperado: ' + aviso);
    if (/upgrade|billing/i.test(aviso)) throw new Error('o aviso repete a propaganda do serviço: ' + aviso);
    if ((await pg.inputValue('#iaTexto')) !== frase) throw new Error('o texto digitado não ficou na caixa');
    if (!(await pg.isVisible('#iaRascunho'))) throw new Error('o rascunho sumiu');
    const manuais = await pg.locator('#iaAviso [data-tela]').allTextContents();
    if (!manuais.includes('Abrir Apropriação direta')) throw new Error('faltou o botão do formulário manual: ' + manuais.join(' | '));
    await pg.screenshot({ path: `${pasta}/cota_${largura}_1_aviso.png`, fullPage: true });
    await pg.reload();                                                     // recarregar não perde o texto nem o rascunho
    await pg.waitForSelector('#iaRascunho:not([hidden])');
    if ((await pg.inputValue('#iaTexto')) !== frase) throw new Error('recarregar perdeu o texto');
    // sem a IA: o item e a quantidade entram pelos campos do rascunho, e o toque grava pela rota de sempre
    await pg.fill('[data-ia-campo="item"]', '5.1.1');
    await pg.press('[data-ia-campo="item"]', 'Tab');
    await pg.waitForSelector('[data-ia-campo="fator.CONTAGEM"]');
    await pg.fill('[data-ia-campo="fator.CONTAGEM"]', '2');
    await pg.press('[data-ia-campo="fator.CONTAGEM"]', 'Tab');
    await pg.waitForSelector('#iaGravar:not([disabled])');
    const sobra = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (sobra > 1) throw new Error(`rolagem lateral de ${sobra}px`);
    await pg.screenshot({ path: `${pasta}/cota_${largura}_2_rascunho_manual.png`, fullPage: true });
    await pg.click('#iaGravar');
    await pg.waitForFunction(() => /Gravado\. Apropriação nº \d+/.test(document.querySelector('#iaConversa').textContent), null, { timeout: 20000 });
    if (erros.length) throw new Error(`erros de JS em ${largura}px: ${erros.join(' ; ')}`);
    saida.push(`${largura} px: aviso “${aviso.slice(0, 150)}”; botões manuais [${manuais.join(' | ')}]; gravou pelo rascunho, sem a IA`);
    await ctx.close();
  }
  await navegador.close();
  console.log(saida.join('\n'));
  console.log('OK: sem cota, a tela avisa, guarda o texto e o rascunho e o formulário grava. Sem erro de JS e sem rolagem lateral.');
})().catch(e => { console.error('FALHOU:', e.message); process.exit(1); });
