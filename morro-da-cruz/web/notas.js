'use strict';
/* Notas de serviço (NS) por upload: enviar, ler, conferir cada segmento contra os trechos da obra e registrar.
 * "Ler a nota" não grava nada; o PDF e o croqui abrem no próprio navegador antes de registrar (URL.createObjectURL) e,
 * depois de registrados, pela rota /api/ns/arquivo. Cada tipo é enviado na sua aba: a NS do dia e a de serviço de obra
 * em Notas de serviço; a de topografia e a de cadastro nas abas Topografia e Cadastro de campo (montarEnvioNs). */

const NS_TIPOS = { TOPOGRAFIA: 'Topografia', CADASTRO: 'Cadastro de campo', SERVICO: 'Serviço de obra', EXECUCAO: 'Do dia (execução)' };
const NS_DESC = {
  TOPOGRAFIA: 'Gera a liberação topográfica dos trechos da nota, só no que ainda não está liberado. É a primeira etapa: sem ela, a execução é recusada.',
  CADASTRO: 'Gera o cadastro de campo só sobre o que já foi executado (assentado) até a data da nota. O resto é recusado, com o que falta; '
    + 'se o assentamento até essa data for registrado depois, use "Aplicar de novo" na nota.',
  SERVICO: 'NS de serviço de obra é o plano da zona: a nota e o croqui ficam para a equipe abrir na página NS do dia, e nada acende no mapa. O que acende o executado é a NS do dia.',
};
const NS_ETAPA = { TOPOGRAFIA: 'liberação topográfica', CADASTRO: 'cadastro de campo' };
const NS_SITU = { AUTOMATICO: ['automático', 'azul'], CONFIRMAR: ['confirmar', 'amarelo'], ERRO: ['erro', 'vermelho'],
  SEM_CORRESPONDENCIA: ['sem correspondência', 'vermelho'], CONFIRMADO: ['confirmado', 'azul'], FORA: ['fora', 'cinza'] };
const NSV = { envio: null, leitura: null, decisoes: {}, marcado: {}, filtro: '', anuladas: false, fila: {}, cartao: null, lote: null };
const chipNs = s => `<span class="chip ${(NS_SITU[s] || ['', ''])[1]}">${esc((NS_SITU[s] || [s])[0])}</span>`;
const mNs = v => v == null ? '—' : nf(v) + ' m';
const linhaNs = n => String(n || '').split('_').pop();                       // Zona03_PB08_Rede_TR020 → TR020
const elNs = t => String(t || '').split(/\s+\(|\s+-\s+/)[0].trim() || '?';       // NÓ6.1 - TÊ 160x110 → NÓ6.1
const PERM_NS = { TOPOGRAFIA: 'topografia', CADASTRO: 'cadastro_campo' };     // registrar, aplicar e anular pedem também a do tipo
const podeNs = tipo => pode('notas_servico') && (!PERM_NS[tipo] || pode(PERM_NS[tipo]));
const linkNs = (id, qual, rot) => `<a class="btn" href="/api/ns/arquivo?id=${id}&qual=${qual}" target="_blank" rel="noopener">${rot}</a>`;

/* ---------------------------------------------------------------- a aba Notas de serviço (as do campo da obra) */
const NS_DA_OBRA = ['EXECUCAO', 'SERVICO'];
async function carregarNotas() {
  $$('#nsFiltro button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.nsFiltro === NSV.filtro)));
  $('#nsAnuladas').checked = NSV.anuladas;
  if (PAGINA.notas === 'dia') { carregarNotaDia(); nsCarregarFila(); }
  if (PAGINA.notas === 'servico') prepararEnvioNs('SERVICO');
  await nsCarregarLista(NSV.filtro, '#nsLista', { anuladas: NSV.anuladas, tipos: NS_DA_OBRA });
  if (pode('notas_servico')) nsForaDeOrdem();
}
// legado fora da ordem obrigatória (D-20): só a lista, para a engenharia tratar trecho a trecho
async function nsForaDeOrdem() {
  const l = await api('/api/ns/fora-de-ordem').catch(() => []);
  $('#nsForaPainel').hidden = !l.length; $('#nsForaN').textContent = l.length;
  $('#nsFora').innerHTML = l.map(x => `<div class="registro"><div><b>${esc(nomeCompleto(x.nome))}</b><span class="chip amarelo">${esc(x.o_que)}</span></div>
    <small>${x.faixas.map(([a, b]) => `${nf(a, 1)}–${nf(b, 1)} m`).join(', ')} · ${dataBR(x.data)} · ${esc(x.registro)}</small></div>`).join('');
}
// depois de registrar ou anular uma NS: a aba aberta se refaz, e os mapas também
function recarregarTelaNs() {
  if (TELA === 'notas') carregarNotas(); else if (TELA === 'topografia') carregarTopografia(); else if (TELA === 'cadastro_campo') carregarCadCampo();
  recarregarCamadaMapa(); driveEmSegundoPlano();
}
function nsLimpar() {
  if (NSV.envio) Object.values(NSV.envio.arquivos).forEach(a => a && URL.revokeObjectURL(a.url));
  NSV.envio = NSV.leitura = NSV.cartao = NSV.lote = null; NSV.decisoes = {}; NSV.marcado = {};
  $('#nsResultado').innerHTML = ''; $('#nsSegPainel').hidden = true; $('#nsConferencia').hidden = true;
}

/* ---------------------------------------------------------------- envio em lote (componente de qualquer tela)
 * criarFilaNs({ caixa, tipo, extra, conferir, depois }): a fila de NS de uma página.
 *  - tipo(): o tipo das NS que entram (o da página: EXECUCAO, SERVICO, TOPOGRAFIA ou CADASTRO);
 *  - extra(): os campos a mais de cada envio (zona e PB; na NS do dia, a equipe e o clima), ou lança o que falta;
 *  - conferir(cartao): abre a conferência que já existe (as NS lidas antes de registrar); depois(): o que recarregar.
 * Vários PDFs de uma vez (até 20 arquivos por lote), com croquis e planilhas também em lote: casam com cada NS pelo
 * número escrito no documento e, na falta dele, pelo nome do arquivo; o que não casar fica visível para ligar à mão.
 * Cada NS vira um cartão: lida, precisa conferir, recusada (com o motivo), registrada ou repetida (mesmo arquivo).
 * "Registrar todas" grava uma NS por pedido, em sequência, com o progresso (o servidor atende um pedido por vez); a
 * falha de uma não para as outras. A NS do dia não tem leitura antes: é registrada ao enviar e o servidor decide. */
const LIMITE_LOTE = 20;
const SIT_LOTE = { lendo: ['lendo…', 'cinza'], lida: ['lida, sem pendência', 'azul'], pronta: ['pronta para enviar', 'azul'],
  conferir: ['precisa conferir', 'amarelo'], recusada: ['recusada', 'vermelho'], registrada: ['registrada', 'verde'], repetida: ['repetida', 'cinza'] };
const numeroNoNome = nome => { const m = /(?:N\s*\.?\s*S|NOTA)[\s._-]*0*(\d{1,4})(?!\d)/i.exec(nome || ''); return m ? +m[1] : null; };
async function hashArquivo(arq) {          // sem https (rede local) não há crypto.subtle: nome, tamanho e data servem
  if (!(window.crypto && crypto.subtle)) return `${arq.name}|${arq.size}|${arq.lastModified}`;
  const d = await crypto.subtle.digest('SHA-256', await arq.arrayBuffer());
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('');
}
function criarFilaNs(op) {
  const F = { cartoes: [], soltos: [], seq: 0, ocupado: false };
  const dia = () => op.tipo() === 'EXECUCAO';
  const numeros = async arq => (await api('/api/ns/numero', { arquivo_b64: await lerOriginal(arq) }).catch(() => ({ numeros: [] }))).numeros;
  const b64 = async a => a ? { b64: await lerOriginal(a), nome: a.name } : {};
  const progresso = t => { const p = $('[data-lote-progresso]', op.caixa); if (p) p.textContent = t; };
  F.adicionar = async (pdfs, croquis = [], planilhas = []) => {
    if (F.ocupado) return toast('Espere terminar o lote em andamento.', 'erro');
    if (!pdfs.length) return toast('Escolha o PDF da nota de serviço.', 'erro');
    if (pdfs.length + croquis.length + planilhas.length > LIMITE_LOTE) return toast(`No máximo ${LIMITE_LOTE} arquivos por lote.`, 'erro');
    let extra; try { extra = op.extra(); } catch (e) { return toast(e.message, 'erro'); }
    F.ocupado = true; F.render();
    try {
      const novos = [];
      for (const [k, arq] of pdfs.entries()) {
        progresso(`Lendo o número da nota ${k + 1} de ${pdfs.length}…`);
        const hash = await hashArquivo(arq).catch(() => arq.name + arq.size);
        const c = { id: ++F.seq, pdf: arq, hash, tipo: op.tipo(), extra, numeros: await numeros(arq), estado: 'lendo', croqui: null, planilha: null };
        const rep = F.cartoes.concat(novos).find(x => x.hash === hash);
        if (rep) Object.assign(c, { estado: 'repetida', motivo: `o mesmo arquivo de ${rep.pdf.name}` });
        novos.push(c);
      }
      F.cartoes.push(...novos);
      const anexos = [...croquis.map(a => [a, 'croqui']), ...planilhas.map(a => [a, 'planilha'])];
      for (const [k, [arq, qual]] of anexos.entries()) {
        progresso(`Casando croquis e planilhas: ${k + 1} de ${anexos.length}…`);
        const ns = await numeros(arq), nome = numeroNoNome(arq.name), livre = novos.filter(x => !x[qual] && x.estado !== 'repetida');
        const c = livre.find(x => x.numeros.some(n => ns.includes(n))) || (nome != null && livre.find(x => x.numeros.includes(nome)))
          || (livre.length === 1 && novos.length === 1 ? livre[0] : null);            // uma nota só no lote: o anexo é dela
        if (c) c[qual] = arq; else F.soltos.push({ id: ++F.seq, arq, qual });
      }
      for (const [k, c] of novos.entries()) { if (c.estado !== 'repetida') { progresso(`Lendo a nota ${k + 1} de ${novos.length}…`); await F.ler(c); } }
    } finally { F.ocupado = false; progresso(''); F.render(); }
    if (dia()) await F.registrarTodas();                  // a NS do dia é registrada ao enviar
  };
  // classifica o cartão: lida (sem pendência), precisa conferir, recusada ou repetida
  F.ler = async c => {
    c.motivo = null; c.leitura = null;
    if (c.tipo === 'EXECUCAO') { Object.assign(c, c.croqui ? { estado: 'pronta' } : { estado: 'conferir', motivo: 'falta o croqui: ligue o croqui a esta nota' }); return; }
    c.estado = 'lendo'; F.render();
    const [pdf, cro, pla] = [await b64(c.pdf), await b64(c.croqui), await b64(c.planilha)];
    const r = await api('/api/ns/ler', { tipo: c.tipo, pdf_b64: pdf.b64, planilha_b64: pla.b64, croqui_b64: cro.b64, zona: c.extra.zona, pb: c.extra.pb })
      .catch(e => ({ erro: e.message }));
    if (r.erro) return Object.assign(c, { estado: 'recusada', motivo: r.erro });
    c.leitura = r; c.numero = r.leitura.numero;
    const res = r.leitura.resultado, falta = [];
    if (!r.contrato_ok) return Object.assign(c, { estado: 'recusada', motivo: `a nota é de outro contrato (${r.leitura.contrato || 'sem contrato'})` });
    if (!res.aceita) return Object.assign(c, { estado: 'recusada', motivo: res.motivos.join('; ') });
    if (r.ja_registrada) return Object.assign(c, { estado: 'repetida', motivo: `este arquivo já foi registrado (NS ${r.ja_registrada.numero})` });
    if (r.mesmo_numero && !r.mesmo_numero.mesma_impressao) falta.push(`a NS ${r.mesmo_numero.numero} já está registrada com outro conteúdo: anule a anterior`);
    if (c.tipo === 'SERVICO' && !c.croqui && !r.mesmo_numero) falta.push('o croqui (obrigatório no serviço de obra)');
    const seg = r.segmentos.filter(s => s.situacao !== 'AUTOMATICO').map(s => s.ordem);
    if (seg.length && !(r.mesmo_numero && r.mesmo_numero.mesma_impressao)) falta.push(`conferir o(s) segmento(s) ${seg.join(', ')}`);
    (r.avisos_croqui || []).forEach(t => falta.push('confira o croqui: ' + t));
    if (r.aviso_tipo) falta.push('confira o tipo: ' + r.aviso_tipo);
    if (!podeNs(c.tipo)) falta.push('seu perfil não registra notas de serviço deste tipo');
    Object.assign(c, falta.length ? { estado: 'conferir', motivo: falta.join('; ') } : { estado: 'lida' });
  };
  F.registrar = async c => {
    const [pdf, cro, pla] = [await b64(c.pdf), await b64(c.croqui), await b64(c.planilha)];
    const corpo = { pdf_b64: pdf.b64, pdf_nome: pdf.nome, croqui_b64: cro.b64, croqui_nome: cro.nome, planilha_b64: pla.b64, planilha_nome: pla.nome, ...c.extra };
    try {
      const r = c.tipo === 'EXECUCAO' ? await api('/api/ns/dia', corpo) : await api('/api/ns', { tipo: c.tipo, decisoes: c.decisoes || [], ...corpo });
      F.marcar(c, r);
    } catch (e) { Object.assign(c, { estado: 'recusada', motivo: e.message }); }
  };
  F.marcar = (c, r) => { Object.assign(c, { estado: 'registrada', resultado: r, motivo: null }); F.render(); };
  F.registrarTodas = async () => {
    const lista = F.cartoes.filter(c => c.estado === 'lida' || c.estado === 'pronta');
    if (!lista.length || F.ocupado) return;
    F.ocupado = true; F.render();
    try {
      for (const [k, c] of lista.entries()) { progresso(`Registrando ${k + 1} de ${lista.length}…`); await F.registrar(c); F.render(); }
    } finally { F.ocupado = false; progresso(''); F.render(); }
    const ok = lista.filter(c => c.estado === 'registrada').length;
    toast(`${ok} de ${lista.length} nota(s) registrada(s)${ok < lista.length ? '; veja o motivo das outras na fila' : ''}.`, ok < lista.length ? 'erro' : 'ok');
    if (ok && op.depois) op.depois();
  };
  const resumo = c => {
    const r = c.resultado; if (!r) return '';
    if (c.tipo === 'EXECUCAO') return htmlNdNota(r);
    const pend = (r.segmentos || []).flatMap(s => s.pendencias || []);
    return `<small>${r.arquivo_trocado ? 'Só o arquivo da NS já registrada foi trocado.' : NS_ETAPA[c.tipo] ? `${nf(r.gravado_m)} m de ${NS_ETAPA[c.tipo]} gravados` + (r.pendente_m > 0.001 ? `; ${nf(r.pendente_m)} m recusados` : '') : 'Registrada.'}</small>`
      + pend.slice(0, 3).map(t => `<div><small>${esc(t)}</small></div>`).join('');
  };
  const nomeCartao = c => c.numero ? `NS ${c.numero}` : c.numeros.length ? `NS ${String(c.numeros[0]).padStart(3, '0')}` : c.pdf.name;
  F.render = () => {
    const cx = op.caixa; cx.hidden = !F.cartoes.length && !F.soltos.length;
    const opcoes = F.cartoes.filter(c => c.estado !== 'registrada' && c.estado !== 'repetida');
    const prontas = F.cartoes.filter(c => c.estado === 'lida' || c.estado === 'pronta').length;
    cx.innerHTML = `<div class="acoes" style="justify-content:space-between"><h3 style="margin:0">Fila do envio (${F.cartoes.length})</h3>
        <span data-lote-progresso class="vazio"></span></div>
      ${F.soltos.length ? `<div class="aviso info"><b>Sem nota casada:</b> ligue cada arquivo à nota certa.
        ${F.soltos.map(x => `<div class="linha" data-solto="${x.id}"><span>${x.qual === 'croqui' ? 'Croqui' : 'Planilha'}: ${esc(x.arq.name)}</span>
          <select data-ligar><option value="">ligar à nota…</option>${opcoes.map(c => `<option value="${c.id}">${esc(nomeCartao(c))} · ${esc(c.pdf.name)}</option>`).join('')}</select></div>`).join('')}</div>` : ''}
      ${F.cartoes.map(c => `<div class="registro cartao-ns" data-cartao="${c.id}"><div><b>${esc(nomeCartao(c))}</b>
          <span class="chip ${SIT_LOTE[c.estado][1]}">${SIT_LOTE[c.estado][0]}</span></div>
        <small>${esc(c.pdf.name)} · croqui: ${c.croqui ? esc(c.croqui.name) : 'nenhum'} · planilha: ${c.planilha ? esc(c.planilha.name) : 'nenhuma'}</small>
        ${c.motivo ? `<div class="${c.estado === 'recusada' ? 'aviso problema' : 'aviso info'}">${esc(c.motivo)}</div>` : ''}${resumo(c)}
        <div class="acoes">${c.estado === 'conferir' && c.leitura && op.conferir ? '<button type="button" class="btn azul" data-conferir-cartao>Conferir</button>' : ''}
          ${['lida', 'pronta'].includes(c.estado) ? '<button type="button" class="btn" data-registrar-cartao>Registrar esta</button>' : ''}
          ${c.estado !== 'registrada' ? '<button type="button" class="btn" data-tirar-cartao>Tirar da fila</button>' : ''}</div></div>`).join('')}
      <div class="acoes"><button type="button" class="btn prim" data-registrar-todas ${prontas && !F.ocupado ? '' : 'disabled'}>Registrar todas as conferidas sem pendência (${prontas})</button>
        ${F.cartoes.some(c => c.estado === 'registrada') ? '<button type="button" class="btn" data-limpar-fila>Limpar as registradas</button>' : ''}</div>`;
    $$('button, select', cx).forEach(b => { if (F.ocupado) b.disabled = true; });
  };
  const cartao = el => F.cartoes.find(c => c.id === +(el.closest('[data-cartao]') || {}).dataset?.cartao);
  op.caixa.addEventListener('click', async ev => {
    const b = ev.target.closest('button'); if (!b || F.ocupado) return;
    const c = cartao(b);
    if (b.matches('[data-registrar-todas]')) return F.registrarTodas();
    if (b.matches('[data-limpar-fila]')) { F.cartoes = F.cartoes.filter(x => x.estado !== 'registrada'); return F.render(); }
    if (!c) return;
    if (b.matches('[data-tirar-cartao]')) { F.cartoes = F.cartoes.filter(x => x !== c); return F.render(); }
    if (b.matches('[data-conferir-cartao]')) return op.conferir(c);
    if (b.matches('[data-registrar-cartao]')) { F.ocupado = true; F.render(); try { await F.registrar(c); } finally { F.ocupado = false; F.render(); }
      if (c.estado === 'registrada' && op.depois) op.depois(); }
  });
  op.caixa.addEventListener('change', async ev => {
    const s = ev.target; if (F.ocupado) return;
    if (s.matches('[data-ligar]') && s.value) {
      const solto = F.soltos.find(x => x.id === +s.closest('[data-solto]').dataset.solto), c = F.cartoes.find(x => x.id === +s.value);
      c[solto.qual] = solto.arq; F.soltos = F.soltos.filter(x => x !== solto);
      await F.ler(c); F.render();
    }
  });
  return F;
}
// a conferência de um cartão da fila: os segmentos, o que fica de fora e "Registrar". É uma só, e vai para a página que
// está conferindo (Serviço de obra, Topografia ou Cadastro de campo)
async function nsConferirCartao(c, lote, lugar) {
  nsLimpar();
  const arq = async a => a ? { b64: await lerOriginal(a), nome: a.name, url: URL.createObjectURL(a) } : null;
  NSV.envio = { tipo: c.tipo, arquivos: { pdf: await arq(c.pdf), croqui: await arq(c.croqui), planilha: await arq(c.planilha) }, zona: c.extra.zona, pb: c.extra.pb };
  NSV.leitura = c.leitura; NSV.cartao = c; NSV.lote = lote;
  const conf = $('#nsConferencia'); lugar.appendChild(conf); conf.hidden = false;
  renderNsLeitura(); if (c.leitura.contrato_ok) renderNsSegmentos();
  $('#nsResultado').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
// o envio de um tipo de NS numa página: o formulário, a fila do lote e o lugar da conferência. Um só componente para
// Notas de serviço (Serviço de obra), Topografia e Cadastro de campo, com o tipo fixo
const ENVIO_NS = {};
function montarEnvioNs(caixa, tipo) {
  const servico = tipo === 'SERVICO';
  caixa.innerHTML = `<div class="grade-2">
      <div style="display:grid;gap:16px;min-width:0;align-content:start"><div class="painel" data-fila hidden></div><div data-conferencia></div></div>
      <form class="painel" data-perm="notas_servico">
        <h3 style="margin:0">Enviar notas de ${esc(NS_TIPOS[tipo].toLowerCase())}</h3>
        <p class="vazio" style="margin:0">${esc(NS_DESC[tipo])}</p>
        <label>Notas de serviço (PDF; várias de uma vez, até 20 arquivos por lote)<input type="file" name="pdf" accept="application/pdf,.pdf" multiple required></label>
        <label>Croquis (PDF, JPG ou PNG; ${servico ? 'obrigatório no serviço de obra' : 'opcional'})<input type="file" name="croqui" accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png" multiple></label>
        <label>Planilhas das notas (.xlsx ou .xls, opcional: leitura exata)<input type="file" name="planilha" accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel" multiple></label>
        <p class="vazio" style="margin:0">O croqui e a planilha casam com cada nota pelo número escrito neles e, na falta dele, pelo nome do arquivo. O que não casar aparece na fila para você ligar à nota certa.</p>
        <details><summary>A nota não diz a zona ou a PB</summary>
          <div class="linha"><label>Zona<select name="zona"><option value="">a da nota</option></select></label><label>PB<input name="pb" placeholder="ex.: PB08" autocomplete="off"></label></div>
        </details>
        <div class="acoes"><button class="btn prim">Ler as notas</button></div>
        <p class="vazio" style="margin:0">Ler não grava nada: cada nota entra na fila ao lado. As lidas sem pendência são registradas juntas, uma por vez; as outras você confere uma a uma.</p>
      </form></div>
    <p class="vazio" data-so-consulta hidden>Seu perfil só consulta as notas deste tipo.</p>`;
  const form = $('form', caixa);
  const lote = criarFilaNs({ caixa: $('[data-fila]', caixa), tipo: () => tipo, conferir: c => nsConferirCartao(c, lote, $('[data-conferencia]', caixa)),
    extra: () => { const o = formObj(form); return { zona: o.zona || null, pb: o.pb || null }; }, depois: recarregarTelaNs });
  form.addEventListener('submit', async ev => {
    ev.preventDefault();
    await lote.adicionar([...form.pdf.files], [...form.croqui.files], [...form.planilha.files]);
    form.pdf.value = form.croqui.value = form.planilha.value = '';
  });
  ENVIO_NS[tipo] = { caixa, form, lote };
}
// ao abrir a página de envio: as zonas no formulário e, para quem não registra o tipo, só o aviso
function prepararEnvioNs(tipo) {
  const e = ENVIO_NS[tipo], z = e.form.zona;
  if (z.options.length < 2) z.innerHTML += RESUMO.frentes.filter(f => /^(Zona\d\d|ADUTORA)$/.test(f)).map(f => `<option>${esc(f)}</option>`).join('');
  $('.grade-2', e.caixa).hidden = !podeNs(tipo); $('[data-so-consulta]', e.caixa).hidden = podeNs(tipo);
}
montarEnvioNs($('#nsEnvioServico'), 'SERVICO');
montarEnvioNs($('#topEnvio'), 'TOPOGRAFIA');
montarEnvioNs($('#cadEnvio'), 'CADASTRO');

function renderNsLeitura() {
  const r = NSV.leitura, l = r.leitura, a = NSV.envio.arquivos, res = l.resultado;
  const contas = l.verificacoes.filter(v => v.nivel !== 'INFO');
  const falhas = contas.filter(v => !v.ok), erros = falhas.filter(v => v.nivel === 'ERRO');
  const ctx = r.contexto, onde = [ctx.zona, ctx.pb].filter(Boolean).join(' ');
  const avisos = [];
  if (!r.contrato_ok) avisos.push(['problema', `<b>Recusada: a nota é de outro contrato (${esc(l.contrato || 'sem contrato')}).</b> Esta obra é o ${esc(RESUMO.contrato)}. Nada pode ser registrado.`]);
  else if (!res.aceita) avisos.push(['problema', `<b>Recusada:</b> ${res.motivos.map(esc).join('; ')}. Confira o PDF ou envie a planilha da nota (.xlsx ou .xls).`]);
  if (r.ja_registrada) avisos.push(['problema', `<b>Este arquivo já foi registrado</b> (NS ${esc(r.ja_registrada.numero)}, ${esc(NS_TIPOS[r.ja_registrada.tipo] || r.ja_registrada.tipo)}, em ${dataBR(String(r.ja_registrada.registrada_em).slice(0, 10))}).`]);
  if (r.mesmo_numero) avisos.push(r.mesmo_numero.mesma_impressao
    ? ['sugestao', `A NS ${esc(r.mesmo_numero.numero)} já está registrada com o mesmo conteúdo (por exemplo, a versão sem assinatura). Ao registrar, só o arquivo é trocado; a versão anterior fica guardada.`]
    : ['problema', `<b>A NS ${esc(r.mesmo_numero.numero)} já está registrada com outro conteúdo.</b> Anule a anterior (com o motivo) na lista "Notas recebidas" antes de registrar esta.`]);
  if (r.aviso_tipo) avisos.push(['info', `Confira o tipo: ${esc(r.aviso_tipo)}.`]);
  (r.avisos_croqui || []).forEach(t => avisos.push(['problema', `<b>Confira o croqui:</b> ${esc(t)}.`]));
  if (!onde) avisos.push(['info', 'A nota não diz a zona nem a PB: escolha em "A nota não diz a zona ou a PB" e leia de novo.']);
  const ass = (l.assinaturas || []).filter(s => s.nome || s.empresa);
  $('#nsResultado').innerHTML = `<div class="acoes" style="justify-content:space-between">
      <h3 style="margin:0">NS ${esc(l.numero || '?')} · folha ${esc(l.folha || '?')} de ${esc(l.folhas || '?')} · ${dataBR(l.data)}</h3>
      <span>${r.contrato_ok ? '<span class="chip verde">contrato confere com a obra</span>' : '<span class="chip vermelho">outro contrato</span>'}
        ${res.aceita ? '<span class="chip azul">contas conferidas</span>' : '<span class="chip vermelho">recusada</span>'}</span></div>
    <p style="margin:8px 0">${esc(l.titulo || '')}<br><small>${esc(l.localizacao || '')}${onde ? ` · <b>${esc(onde)}</b>${ctx.origem === 'FORMULARIO' ? ' (escolhida no formulário)' : ''}` : ''}
      · contrato ${esc(l.contrato || '—')} · total ${mNs(l.total_geral)} em ${l.grupos.length} grupo(s)</small></p>
    ${avisos.map(([c, t]) => `<div class="aviso ${c}">${t}</div>`).join('')}
    <div class="acoes"><a class="btn" href="${a.pdf.url}" target="_blank" rel="noopener">Abrir o PDF</a>
      ${a.croqui ? `<a class="btn" href="${a.croqui.url}" target="_blank" rel="noopener">Abrir o croqui</a>` : ''}
      ${a.planilha ? '<span class="chip azul">planilha conferida com o PDF</span>' : ''}</div>
    ${ass.length ? `<p style="margin:8px 0 0"><small>Assinaturas: ${ass.map(s => `${esc(String(s.empresa || s.rotulo || s.papel).replace(/:\s*$/, ''))}${s.nome ? ': ' + esc(s.nome) : ': sem nome'}`).join(' · ')}</small></p>` : ''}
    <details${erros.length && r.contrato_ok ? ' open' : ''}><summary>Contas da nota: ${contas.length - falhas.length} conferem${falhas.length ? `, ${falhas.length} com problema` : ''}</summary>
      <ul class="pend">${contas.map(v => `<li><span class="chip ${v.ok ? 'verde' : v.nivel === 'ERRO' ? 'vermelho' : 'amarelo'}">${v.ok ? 'confere' : v.nivel === 'ERRO' ? 'erro' : 'aviso'}</span> ${esc(v.msg)}</li>`).join('')}</ul>
      ${(l.avisos || []).length ? `<ul class="pend">${l.avisos.map(x => `<li><small>${esc(x)}</small></li>`).join('')}</ul>` : ''}</details>`;
}

/* ---------------------------------------------------------------- segmentos × trechos da obra */
function nsEscolhido(s) {          // o trecho que vale para o segmento: o do sistema ou o que a pessoa escolheu
  const d = NSV.decisoes[s.ordem];
  if (d && d.fisico_id) return s.candidatos.find(c => c.fisico_id === d.fisico_id) || null;
  return s.escolhido;
}
function nsSituacao(s) {
  const d = NSV.decisoes[s.ordem];
  if (d && d.acao === 'FORA') return 'FORA';
  if (d && d.acao === 'ACEITAR') return 'CONFIRMADO';
  return s.situacao;
}
function htmlNsTrecho(s) {
  const e = nsEscolhido(s), cs = s.candidatos || [];
  if (s.situacao === 'CONFIRMAR' && !s.escolhido && cs.length && !NSV.decisoes[s.ordem]) {   // vários trechos possíveis: a pessoa escolhe
    return cs.map(c => `<label class="check"${c.situacao === 'ERRO' ? ' style="opacity:.55"' : ''}><input type="radio" name="nsCand${s.ordem}" value="${esc(c.fisico_id)}" data-ns-cand="${s.ordem}"${NSV.marcado[s.ordem] === c.fisico_id ? ' checked' : ''}${c.situacao === 'ERRO' ? ' disabled' : ''}>
      <span>${esc((c.linhas || []).map(linhaNs).join(' + '))} · ${esc(lugarNs(c))} · ${mNs(c.extensao_m)}${c.situacao !== 'AUTOMATICO' ? ` <small>(${esc(c.motivo || '')})</small>` : ''}</span></label>`).join('');
  }
  if (!e) return '<small>nenhum</small>';
  return `${esc((e.linhas || []).map(linhaNs).join(' + '))}<br><small>${esc(e.texto || '')}</small>`;
}
const lugarNs = c => [...new Set((c.linhas || []).map(n => (/^(Zona\d\d|ADUTORA)_(PB\d\d)_/.exec(n) || []).slice(1, 3).join(' ')))].filter(Boolean).join(' e ');
function htmlNsAcao(s) {
  const d = NSV.decisoes[s.ordem];
  if (d) return `<button type="button" class="btn" data-ns-acao="desfazer" data-ordem="${s.ordem}">Desfazer</button>${d.acao === 'FORA' ? `<br><small>${esc(d.motivo)}</small>` : ''}`;
  const fora = `<button type="button" class="btn" data-ns-acao="fora" data-ordem="${s.ordem}">Deixar de fora</button>`;
  if (s.situacao === 'CONFIRMAR') return `<button type="button" class="btn azul" data-ns-acao="aceitar" data-ordem="${s.ordem}">${s.escolhido ? 'Aceitar a diferença' : 'Usar o trecho marcado'}</button> ${fora}`;
  return fora;
}
function renderNsSegmentos() {
  const r = NSV.leitura, segs = r.segmentos;
  $('#nsSegPainel').hidden = false;
  $('#nsSegmentos').innerHTML = segs.length ? tabelaHtml('<th>#</th><th>De → para</th><th>Tubo</th><th class="n">Na nota</th><th>Trecho da obra</th><th class="n">No projeto</th><th class="n">Diferença</th><th>Situação</th><th>O que fazer</th>',
    segs.map(s => { const e = nsEscolhido(s), avisos = [s.motivo, ...(s.avisos || [])].filter(Boolean);
      return `<tr><td>${s.ordem}</td><td title="${esc(s.de || '')} → ${esc(s.para || '')}">${esc(elNs(s.de))} → ${esc(elNs(s.para))}</td><td>${s.de_mm ? 'DE ' + nf(s.de_mm, 0) : '—'}${s.metodo ? ' · ' + esc(s.metodo) : ''}</td>
        <td class="n">${mNs(s.metros_ns)}</td><td>${htmlNsTrecho(s)}</td><td class="n">${e ? mNs(e.extensao_m) : '—'}</td>
        <td class="n">${e && e.diferenca_m != null ? nf(e.diferenca_m) + ' m' : '—'}</td>
        <td>${chipNs(nsSituacao(s))}${s.situacao === 'AUTOMATICO' && (s.avisos || []).length ? ' <span class="chip amarelo">aviso</span>' : ''}</td><td>${htmlNsAcao(s)}</td></tr>
        ${avisos.length ? `<tr><td></td><td colspan="8"><small>${avisos.map(esc).join('<br>')}</small></td></tr>` : ''}`; }))
    : '<p class="vazio">A nota não tem segmentos (linhas com dois elementos da rede).</p>';
  renderNsPrevia();
}
function renderNsPrevia() {
  const r = NSV.leitura, tipo = NSV.envio.tipo, faltas = nsFaltas();
  let html;
  if (r.mesmo_numero && r.mesmo_numero.mesma_impressao) html = '<p>Só o arquivo da NS já registrada é trocado. Os registros dela continuam como estão.</p>';
  else if (!NS_ETAPA[tipo]) html = '<p>Nada é gravado nos trechos: a nota e o croqui ficam para a equipe abrir em Notas de serviço, na página NS do dia.</p>';
  else {
    let total = 0, pend = 0, ja = 0;
    const linhas = r.segmentos.filter(s => !['FORA', 'ERRO', 'SEM_CORRESPONDENCIA'].includes(nsSituacao(s))).flatMap(s => {
      const e = nsEscolhido(s); if (!e) return [];
      return (e.plano || []).map(p => { const g = p.gravar.reduce((x, [a, b]) => x + b - a, 0), pe = p.pendente.reduce((x, [a, b]) => x + b - a, 0);
        total += g; pend += pe; ja += p.ja_m;
        return `<tr><td>${s.ordem}</td><td>${esc(linhaNs(p.ponto))}</td><td>${faixa(p.gravar)}</td><td class="n">${nf(g)} m</td>
          <td><small>${p.ja_m > 0.001 ? `já tinha ${nf(p.ja_m)} m` : ''}${pe > 0.001 ? `${p.ja_m > 0.001 ? ' · ' : ''}pendente ${faixa(p.pendente)} (ainda não assentado)` : ''}</small></td></tr>`; });
    });
    html = linhas.length ? `<p style="margin:4px 0">${esc(NS_ETAPA[tipo][0].toUpperCase() + NS_ETAPA[tipo].slice(1))} de <b>${nf(total)} m</b>${ja > 0.001 ? `; ${nf(ja)} m já estavam registrados` : ''}${pend > 0.001 ? `; <b>${nf(pend)} m ficam pendentes</b>` : ''}. Data: ${dataBR(r.leitura.data)}; referência: NS ${esc(r.leitura.numero)}.</p>
      ${tabelaHtml('<th>#</th><th>Linha da 06.1</th><th>Grava (m)</th><th class="n">Metros</th><th>Observação</th>', linhas)}` : '<p class="vazio">Nenhum trecho a gravar.</p>';
  }
  $('#nsPrevia').innerHTML = html;
  $('#nsRegistrar').disabled = faltas.length > 0;
  $('#nsFalta').textContent = faltas.length ? 'Falta: ' + faltas.join('; ') + '.' : '';
}
function nsFaltas() {
  const r = NSV.leitura, out = [];
  if (!r.contrato_ok || !r.leitura.resultado.aceita) out.push('a nota foi recusada');
  if (r.ja_registrada) out.push('este arquivo já foi registrado');
  if (r.mesmo_numero && !r.mesmo_numero.mesma_impressao) out.push('anular a NS anterior de mesmo número');
  if (NSV.envio.tipo === 'SERVICO' && !NSV.envio.arquivos.croqui && !r.mesmo_numero) out.push('o croqui (obrigatório no serviço de obra)');
  if (!podeNs(NSV.envio.tipo)) out.push('seu perfil não registra notas de serviço deste tipo');
  const conferir = r.segmentos.filter(s => s.situacao !== 'AUTOMATICO' && !NSV.decisoes[s.ordem]).map(s => s.ordem);
  if (conferir.length && !(r.mesmo_numero && r.mesmo_numero.mesma_impressao)) out.push(`conferir o(s) segmento(s) ${conferir.join(', ')}`);
  return out;
}
$('#nsSegmentos').addEventListener('change', ev => {
  const i = ev.target.closest('[data-ns-cand]'); if (!i) return;
  NSV.marcado = { ...NSV.marcado, [+i.dataset.nsCand]: i.value };
});
$('#nsSegmentos').addEventListener('click', ev => {
  const b = ev.target.closest('[data-ns-acao]'); if (!b) return;
  const o = +b.dataset.ordem, s = NSV.leitura.segmentos.find(x => x.ordem === o);
  if (b.dataset.nsAcao === 'desfazer') delete NSV.decisoes[o];
  else if (b.dataset.nsAcao === 'fora') {
    const motivo = prompt('Por que este segmento fica de fora? (fica registrado junto da nota)'); if (!motivo || !motivo.trim()) return;
    NSV.decisoes[o] = { ordem: o, acao: 'FORA', motivo: motivo.trim() };
  } else if (b.dataset.nsAcao === 'aceitar') {
    const marcado = NSV.marcado[o];
    if (!s.escolhido && !marcado) return toast('Marque um dos trechos possíveis.', 'erro');
    NSV.decisoes[o] = s.escolhido ? { ordem: o, acao: 'ACEITAR' } : { ordem: o, acao: 'ACEITAR', fisico_id: marcado };
  }
  renderNsSegmentos();
});
$('#nsRegistrar').addEventListener('click', async () => {
  const e = NSV.envio, a = e.arquivos;
  const r = await acao(() => api('/api/ns', { tipo: e.tipo, pdf_b64: a.pdf.b64, pdf_nome: a.pdf.nome, croqui_b64: a.croqui && a.croqui.b64,
    croqui_nome: a.croqui && a.croqui.nome, planilha_b64: a.planilha && a.planilha.b64, planilha_nome: a.planilha && a.planilha.nome,
    zona: e.zona, pb: e.pb, decisoes: Object.values(NSV.decisoes) })).catch(() => null);
  if (!r) return;
  toast(r.arquivo_trocado ? 'Arquivo da NS trocado (a versão anterior ficou guardada).'
    : `NS registrada${NS_ETAPA[e.tipo] ? `: ${nf(r.gravado_m)} m de ${NS_ETAPA[e.tipo]} gravados${r.pendente_m > 0.001 ? `, ${nf(r.pendente_m)} m recusados (o que falta está na nota)` : ''}` : ''}.`, 'ok');
  if (NSV.cartao && NSV.lote) NSV.lote.marcar(NSV.cartao, r);         // o cartão da fila que foi conferido
  nsLimpar(); recarregarTelaNs();
});

/* ---------------------------------------------------------------- notas recebidas (tela Notas e abas Topografia / Cadastro) */
// opcoes.tipos: sem tipo escolhido, só esses (a aba Notas de serviço mostra só as do campo da obra)
async function nsCarregarLista(tipo, alvo, opcoes = {}) {
  const q = new URLSearchParams({ vigentes: opcoes.anuladas ? '0' : '1' }); if (tipo) q.set('tipo', tipo);
  const lista = await acao(() => api('/api/ns?' + q)).catch(() => null); if (!lista) return;
  $(alvo).innerHTML = htmlNsLista(tipo || !opcoes.tipos ? lista : lista.filter(n => opcoes.tipos.includes(n.tipo)));
}
const situNs = n => n.segmentos.map(x => `${x.n} ${esc((NS_SITU[x.situacao] || [x.situacao])[0])}`).join(' · ');
const driveNs = d => !d ? '' : d.status === 'ENVIADO' ? `<a href="${esc(d.drive_link || '#')}" target="_blank" rel="noopener">no Drive</a>`
  : d.status === 'ERRO' ? `<span class="chip vermelho" title="${esc(d.ultimo_erro || '')}">erro</span>` : '<span class="chip cinza">na fila</span>';
function htmlNsLista(lista) {
  if (!lista.length) return '<p class="vazio">Nenhuma nota de serviço recebida.</p>';

  return tabelaHtml('<th>NS</th><th>Tipo</th><th>Onde</th><th>Data</th><th>Situação</th><th class="n">Gravou</th><th class="n">Pendente</th><th>Drive</th><th></th>',
    lista.map(n => `<tr${n.status === 'ANULADA' ? ' style="opacity:.6"' : ''}><td><b>${esc(n.referencia)}</b><br><small>${esc(n.titulo || '')}</small></td>
      <td>${esc(NS_TIPOS[n.tipo] || n.tipo)}</td><td>${esc([n.zona, n.pb, n.equipe_id && n.tipo === 'EXECUCAO' ? 'equipe ' + n.equipe_id : null].filter(Boolean).join(' · ') || '—')}</td>
      <td>${dataBR(n.data)}</td><td>${n.status === 'ANULADA' ? `<span class="chip cinza" title="${esc(n.anulada_motivo || '')}">anulada</span>` : `<small>${situNs(n)}</small>`}</td>
      <td class="n">${NS_ETAPA[n.tipo] || n.tipo === 'EXECUCAO' ? mNs(n.aplicado_m) : '—'}</td><td class="n">${n.pendente_m > 0.001 ? `<b>${mNs(n.pendente_m)}</b>` : '—'}</td>
      <td>${driveNs((n.drive || {}).pdf)}</td>
      <td><div class="acoes">${linkNs(n.id, 'pdf', 'PDF')}${n.croqui_id ? linkNs(n.id, 'croqui', 'Croqui') : ''}
        <button type="button" class="btn" data-ns-ver="${n.id}">Ver</button>
        ${podeNs(n.tipo) && n.status === 'REGISTRADA' && NS_ETAPA[n.tipo] && n.pendente_m > 0.001 ? `<button type="button" class="btn azul" data-ns-aplicar="${n.id}">Aplicar de novo</button>` : ''}
        ${podeNs(n.tipo) && n.status === 'REGISTRADA' && n.tipo !== 'EXECUCAO' ? `<button type="button" class="btn" data-ns-anular="${n.id}">Anular</button>` : ''}</div></td></tr>
      <tr hidden data-ns-detalhe="${n.id}"><td colspan="9"></td></tr>`));
}
async function nsVer(id, linha) {
  if (!linha.hidden) { linha.hidden = true; return; }
  const d = await acao(() => api('/api/ns/detalhe?id=' + id)).catch(() => null); if (!d) return;
  linha.hidden = false;
  $('td', linha).innerHTML = `${((d.leitura || {}).avisos_croqui || []).map(t => `<div class="aviso problema">Confira o croqui: ${esc(t)}.</div>`).join('')}
    ${d.status === 'ANULADA' ? `<div class="aviso problema">Anulada por ${esc(d.anulada_por)} em ${dataBR(String(d.anulada_em).slice(0, 10))}: ${esc(d.anulada_motivo)}</div>` : ''}
    ${d.segmentos.map(s => `<div class="registro"><div><b>${s.ordem}. ${esc(elNs(s.de))} → ${esc(elNs(s.para))} · ${mNs(s.metros_ns)} na nota</b> ${chipNs(s.situacao)}</div>
      <small>${s.linhas.length ? s.linhas.map(l => `${esc(linhaNs(l.ponto))} ${nf(l.ini_m)}–${nf(l.fim_m)} m`).join(' · ') : 'sem trecho da obra'}
        ${s.aplicado_m > 0.001 ? ` · gravado ${nf(s.aplicado_m)} m` : ''}${s.pendente_m > 0.001 ? ` · <b>pendente ${nf(s.pendente_m)} m</b>` : ''}${s.confirmado_por ? ` · conferido por ${esc(s.confirmado_por)}` : ''}</small>
      ${[s.motivo, s.pendente, ...(s.avisos || [])].filter(Boolean).map(t => `<div><small>${esc(t)}</small></div>`).join('')}</div>`).join('') || '<p class="vazio">Sem segmentos.</p>'}
    ${d.versoes.length ? `<p style="margin:6px 0 0"><small>Versões anteriores do arquivo: ${d.versoes.length} (guardadas, registradas em ${d.versoes.map(v => dataBR(String(v.registrada_em).slice(0, 10))).join(', ')})</small></p>` : ''}`;
}
document.addEventListener('click', async ev => {
  const ver = ev.target.closest('[data-ns-ver]'), apl = ev.target.closest('[data-ns-aplicar]'), anu = ev.target.closest('[data-ns-anular]');
  if (ver) return nsVer(ver.dataset.nsVer, ver.closest('table').querySelector(`[data-ns-detalhe="${ver.dataset.nsVer}"]`));
  let r = null;
  if (apl) r = await acao(() => api('/api/ns/aplicar', { ns_id: +apl.dataset.nsAplicar }), null).catch(() => null);
  if (apl && r) toast(r.gravado_m > 0.001 ? `Gravados mais ${nf(r.gravado_m)} m.${r.pendente_m > 0.001 ? ` Ainda pendentes: ${nf(r.pendente_m)} m.` : ''}`
    : 'Nada novo a gravar: o que falta ainda não foi assentado até a data da nota.', 'ok');
  if (anu) {
    const motivo = prompt('Motivo da anulação (os registros desta nota também são anulados; nada é apagado):'); if (!motivo || !motivo.trim()) return;
    r = await acao(() => api('/api/ns/anular', { ns_id: +anu.dataset.nsAnular, motivo: motivo.trim() }), 'Nota anulada com os registros dela.').catch(() => null);
  }
  if (r) recarregarTelaNs();
});
$('#nsFiltro').addEventListener('click', ev => {
  const b = ev.target.closest('[data-ns-filtro]'); if (!b) return;
  NSV.filtro = b.dataset.nsFiltro; carregarNotas();
});
$('#nsAnuladas').addEventListener('change', ev => { NSV.anuladas = ev.target.checked; carregarNotas(); });

/* ---------------------------------------------------------------- NS do dia: o resumo em linguagem simples */
const ETAPA_DIA = { ASSENTADO: 'assentado', REATERRADO: 'reaterrado', ESCAVADO: 'escavado' };
const juntarE = l => l.length < 2 ? l.join('') : l.slice(0, -1).join(', ') + ' e ' + l[l.length - 1];
function htmlLancado(n) {
  const regs = n.segmentos.flatMap(s => s.registros || []);
  return Object.keys(ETAPA_DIA).map(e => { const r = regs.filter(x => x.etapa === e);
    return r.length ? `<li><b>Lançado:</b> ${juntarE(r.map(x => `${esc(linhaNs(x.ponto))} ${nf(x.ini_m)}–${nf(x.fim_m)} m`))} (${ETAPA_DIA[e]})</li>` : ''; }).join('');
}
const podeAnularDia = n => n.status === 'REGISTRADA' && (pode('retificar_campo')
  || (pode('ns_dia') && !n.verificada && (!USUARIO.restrito_a_equipe || n.equipe_id === USUARIO.equipe_id)));
function htmlNdNota(n) {
  const fila = n.segmentos.filter(s => s.na_fila), ja = {};
  n.segmentos.forEach(s => Object.entries((s.agora || {}).ja || {}).forEach(([e, m]) => { ja[e] = (ja[e] || 0) + m; }));
  const pulado = [...new Set(n.segmentos.flatMap(s => (s.agora || {}).pulado || []))];
  const onde = [n.zona, n.pb].filter(Boolean).join(' ');
  return `<div class="registro"><div><b>${esc(n.referencia)} · ${dataBR(n.data)} · equipe ${esc(n.equipe_id)}${onde && onde !== n.equipe_id ? ' · ' + esc(onde) : ''}</b>
      ${fila.length ? `<span class="chip amarelo">${fila.length} aguardando a engenharia</span>` : '<span class="chip verde">lançada</span>'}</div>
    <ul class="pend">${htmlLancado(n) || '<li>Nada lançado ainda.</li>'}
      ${Object.entries(ja).map(([e, m]) => `<li>${nf(m)} m já estavam lançados (${ETAPA_DIA[e]}).</li>`).join('')}
      ${pulado.map(p => `<li>${esc(p)}.</li>`).join('')}
      ${fila.map(s => `<li><b>Aguardando a engenharia:</b> ${esc(elNs(s.de))} → ${esc(elNs(s.para))} (${esc(s.motivo || s.pendente || '')})</li>`).join('')}
      ${(n.avisos || []).map(a => `<li><small>${esc(a[0].toUpperCase() + a.slice(1))}.</small></li>`).join('')}</ul>
    <small>Enviada por ${esc(n.registrada_por)} em ${dataBR(String(n.registrada_em).slice(0, 10))}</small>
    <div class="acoes" style="margin-top:6px">${linkNs(n.id, 'pdf', 'Abrir a nota')}${n.croqui_id ? linkNs(n.id, 'croqui', 'Abrir o croqui') : ''}
      ${podeAnularDia(n) ? `<button type="button" class="btn" data-nd-anular="${n.id}">Anular este envio</button>` : ''}</div></div>`;
}

/* ---------------------------------------------------------------- NS do dia (Notas de serviço › NS do dia: o encarregado envia, sem digitar o que fez) */
const ND = { clima: {} };
const zonaDaEquipe = eq => /^(Zona\d\d|ADUTORA)$/.test(eq || '') ? eq : '';
async function carregarNotaDia() {
  const sel = $('#ndEquipe');
  if (sel.options.length < 2) sel.innerHTML = '<option value="">Escolha a equipe</option>' + RESUMO.equipes.map(e => `<option value="${esc(e.id)}">${esc(e.nome)}</option>`).join('');
  if (USUARIO.restrito_a_equipe) { sel.value = USUARIO.equipe_id; sel.disabled = true; }        // o encarregado envia só a dele
  chipsClima($('#fNd'));
  await ndListas();
}
// os dois toques do clima (manhã e tarde): na NS do dia e no Clima do dia do Lançamento do dia
function chipsClima(form) {
  $$('[data-turno]', form).forEach(box => { if (!box.children.length) box.innerHTML = Object.entries(RESUMO.clima)
    .map(([k, v]) => `<button type="button" data-clima="${esc(k)}" aria-pressed="false">${esc(v)}</button>`).join(''); });
}
function tocarClima(ev, guardar) {
  const b = ev.target.closest('[data-clima]'); if (!b) return;
  const box = b.closest('[data-turno]');
  guardar[box.dataset.turno] = b.dataset.clima;
  $$('button', box).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
}
// as notas do dia enviadas: a equipe escolhida (a do encarregado, para ele) e o dia; sem dia, os últimos 7
async function ndListas() {
  const eq = $('#ndEquipe').value, dia = $('#ndDia').value, z = zonaDaEquipe(eq);
  const q = new URLSearchParams(dia ? { data: dia } : { desde: somarDia(hoje(), -7) });
  if (eq) q.set('equipe', eq);
  const [env, serv] = await Promise.all([api('/api/ns/dia?' + q).catch(() => null), api('/api/ns?tipo=SERVICO' + (z ? '&zona=' + z : '')).catch(() => null)]);
  if (env) $('#ndEnviadas').innerHTML = env.slice(0, 10).map(htmlNdNota).join('') || `<p class="vazio">Nenhuma nota enviada ${dia ? 'em ' + dataBR(dia) : 'nos últimos 7 dias'}.</p>`;
  if (serv) $('#ndServico').innerHTML = serv.slice(0, 8).map(n => `<div class="registro"><div><b>${esc(n.referencia)} · ${dataBR(n.data)}</b>
      <span>${esc([n.zona, n.pb].filter(Boolean).join(' '))}</span></div><small>${esc(n.titulo || '')}</small>
      <div class="acoes" style="margin-top:6px">${linkNs(n.id, 'pdf', 'Abrir a nota')}${n.croqui_id ? linkNs(n.id, 'croqui', 'Abrir o croqui') : ''}</div></div>`).join('')
    || '<p class="vazio">Nenhuma nota de serviço da zona.</p>';
}
$('#ndEquipe').addEventListener('change', ndListas);
$('#ndDia').addEventListener('change', ndListas);
$('#fNd').addEventListener('click', ev => tocarClima(ev, ND.clima));
// a NS do dia usa a mesma fila do envio em lote: cada nota é registrada ao enviar, e o resultado fica no cartão dela
const ND_LOTE = criarFilaNs({ caixa: $('#ndLote'), tipo: () => 'EXECUCAO',
  extra: () => {
    const eq = $('#ndEquipe').value;
    if (!eq) throw new Error('Escolha a equipe.');
    return { equipe_id: eq, clima: { ...ND.clima } };      // sem toque, vale o já marcado em Clima do dia (D-131)
  },
  depois: () => { ndListas(); recarregarCamadaMapa(); driveEmSegundoPlano(); } });
$('#fNd').addEventListener('submit', async ev => {
  ev.preventDefault();
  const f = ev.target, bt = $('#ndEnviar'); bt.disabled = true; bt.textContent = 'Enviando…';
  try {
    await ND_LOTE.adicionar([...f.pdf.files], [...f.croqui.files], [...f.planilha.files]);
    f.pdf.value = f.croqui.value = f.planilha.value = '';
  } finally { bt.disabled = false; bt.textContent = 'Enviar a nota do dia'; }
});
ligarBusca($('#ndAlvo'), r => selecionarCampo(r.tipo, r.id));
// o trecho (ou nó) das soldas e fotos é um só no Lançamento do dia, venha da busca, do apontamento sem NS ou da ficha do mapa
function ndAlvoEscolhido(nome) {
  $('#ndAlvo').value = nomeCompleto(nome); $('#ndAlvoInfo').textContent = `Soldas e fotos de ${nomeCompleto(nome)}.`;
}
// escolher no mapa: a ficha do trecho volta para cá pelo botão "Lançar avanço"
$('#ndNoMapa').addEventListener('click', () => { abrirAba('iluminado'); toast('Toque no trecho e, na ficha, em "Lançar avanço".'); });

/* ---------------------------------------------------------------- Lançamento do dia › Clima do dia (para o diário dos dias sem NS do dia) */
const CLIMA_DIA = {};
function carregarClimaDia() {
  const f = $('#fClima'), sel = $('#climaEquipe');
  if (sel.options.length < 2) sel.innerHTML = '<option value="">Escolha a equipe</option>' + RESUMO.equipes.map(e => `<option value="${esc(e.id)}">${esc(e.nome)}</option>`).join('');
  if (USUARIO.restrito_a_equipe) { sel.value = USUARIO.equipe_id; sel.disabled = true; }
  if (!f.data.value) f.data.value = hoje();
  chipsClima(f);
}
$('#fClima').addEventListener('click', ev => tocarClima(ev, CLIMA_DIA));
$('#fClima').addEventListener('submit', async ev => {
  ev.preventDefault();
  const f = ev.target, eq = $('#climaEquipe').value;
  if (!eq) return toast('Escolha a equipe.', 'erro');
  if (!CLIMA_DIA.MANHA || !CLIMA_DIA.TARDE) return toast('Toque no clima da manhã e no da tarde.', 'erro');
  const r = await acao(() => api('/api/clima', { data: f.data.value, equipe_id: eq, ...CLIMA_DIA }), `Clima de ${dataBR(f.data.value)} gravado.`).catch(() => null);
  if (r) { delete CLIMA_DIA.MANHA; delete CLIMA_DIA.TARDE; $$('[data-clima]', f).forEach(b => b.setAttribute('aria-pressed', 'false')); }
});
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-nd-anular]'); if (!b) return;
  const motivo = prompt('Motivo da anulação (o que esta nota lançou também é anulado; nada é apagado):'); if (!motivo || !motivo.trim()) return;
  const r = await acao(() => api('/api/ns/dia/anular', { ns_id: +b.dataset.ndAnular, motivo: motivo.trim() }), 'Envio anulado.').catch(() => null);
  if (!r) return;
  if (TELA === 'notas') ndListas(); else if (TELA === 'diario') carregarDiario();
  recarregarCamadaMapa();
});

/* ---------------------------------------------------------------- Diário de obra: a NS do dia, o croqui enviado e o croqui do sistema */
function renderDiarioNs(lista) {
  $('#diaNs').innerHTML = lista.length ? lista.map(n => `${htmlNdNota(n)}
    <div class="croqui-par">
      <figure><figcaption>Croqui enviado</figcaption>${!n.croqui_id ? '<div class="vazio">Sem croqui.</div>'
        : String(n.croqui_mime || '').startsWith('image/') ? `<img src="/api/ns/arquivo?id=${n.id}&qual=croqui" alt="Croqui enviado com a ${esc(n.referencia)}" loading="lazy">`
          : `<div class="croqui-pdf">Croqui em PDF. ${linkNs(n.id, 'croqui', 'Abrir o croqui')}</div>`}</figure>
      <figure><figcaption>Croqui do sistema: os trechos que o sistema entendeu da nota</figcaption>
        <svg class="croqui-sistema" data-ns="${n.id}" role="img" aria-label="Trechos lançados a partir da ${esc(n.referencia)}"></svg></figure>
    </div>`).join('') : '<p class="vazio">Nenhuma nota do dia enviada neste dia.</p>';
  lista.forEach(n => desenharCroquiSistema($(`svg.croqui-sistema[data-ns="${n.id}"]`), n));
}
// mapa pequeno com as funções do iluminado.js (obterGeral, indexar, limites, encaixar, caminho): lançado aceso, fila tracejada
async function desenharCroquiSistema(svg, n) {
  let g; try { g = await obterGeral(); } catch (_) { return; }
  if (!svg || g.ausente) return;
  const ix = indexar(g), regs = n.segmentos.flatMap(s => s.registros || []);
  const feitos = new Map();
  regs.forEach(r => { const l = feitos.get(r.ponto) || []; l.push(`${ETAPA_DIA[r.etapa] || r.etapa} ${nf(r.ini_m)}–${nf(r.fim_m)} m`); feitos.set(r.ponto, l); });
  const fila = new Set(n.segmentos.filter(s => s.na_fila).flatMap(s => (s.linhas || []).map(l => l.ponto)).filter(p => !feitos.has(p)));
  const linhas = [...feitos.keys(), ...fila].map(p => ix.trecho.get(p)).filter(Boolean);
  if (!linhas.length) { svg.outerHTML = '<div class="vazio">Nenhum trecho desta nota no mapa.</div>'; return; }
  const r = svg.getBoundingClientRect(), [x, y, w, h] = encaixar(limites(linhas.flatMap(t => t.p), 0.6), (r.width || 320) / (r.height || 240));
  const px = w / (r.width || 320), dentro = p => { for (let i = 0; i < p.length; i += 2) if (p[i] >= x && p[i] <= x + w && p[i + 1] >= y && p[i + 1] <= y + h) return true; return false; };
  svg.setAttribute('viewBox', `${x} ${y} ${w} ${h}`);
  svg.innerHTML = `<path class="cs-fundo" stroke-width="${1.4 * px}" d="${caminho(g.trechos.filter(t => t.p.some(dentro)).flatMap(t => t.p))}"/>
    ${[...fila].map(p => ix.trecho.get(p)).filter(Boolean).map(t => `<path class="cs-fila" stroke-width="${3 * px}" stroke-dasharray="${6 * px} ${4 * px}" d="${caminho(t.p)}"><title>${esc(linhaNs(t.n))}: aguardando a engenharia</title></path>`).join('')}
    ${[...feitos].map(([p, l]) => [ix.trecho.get(p), l]).filter(([t]) => t).map(([t, l]) => `<path class="cs-lancado" stroke-width="${4 * px}" d="${caminho(t.p)}"><title>${esc(linhaNs(t.n))}: ${esc(l.join('; '))}</title></path>`).join('')}`;
}

/* ---------------------------------------------------------------- Notas de serviço: a fila "NS do dia a conferir" (engenharia) */
const candTexto = c => `${lugarNs({ linhas: [c.de] })} · ${linhaNs(c.de)} → ${linhaNs(c.para)} · ${nf(c.ini_m)}–${nf(c.fim_m)} m do trecho físico`;
function htmlFilaSeg(n, s) {
  const cands = s.situacao === 'CONFIRMAR' && !s.fisico_id ? (s.candidatos || []) : [];
  const d = (NSV.fila[n.id] || {})[s.ordem];
  return `<div class="registro" data-fila-ordem="${s.ordem}"><div><span>${s.ordem}. ${esc(elNs(s.de))} → ${esc(elNs(s.para))} · ${mNs(s.metros_ns)} na nota</span> ${chipNs(s.situacao)}</div>
    <small>${esc(s.motivo || s.pendente || '')}</small>
    ${cands.map((c, k) => `<label class="check"${c.situacao === 'ERRO' ? ' style="opacity:.55"' : ''}><input type="radio" name="fila${n.id}_${s.ordem}" value="${k}"${c.situacao === 'ERRO' ? ' disabled' : ''}${d && d.candidato === k ? ' checked' : ''}>
      <span>${esc(candTexto(c))}${c.motivo ? ` <small>(${esc(c.motivo)})</small>` : ''}</span></label>`).join('')}
    <div class="acoes" style="margin-top:6px">${s.situacao === 'CONFIRMAR' ? `<button type="button" class="btn azul" data-fila-acao="aceitar">${cands.length ? 'Usar o trecho marcado' : 'Aceitar a diferença'}</button>` : ''}
      ${s.aplicado_m ? '' : '<button type="button" class="btn" data-fila-acao="fora">Deixar de fora</button>'}
      ${['AUTOMATICO', 'CONFIRMADO'].includes(s.situacao) ? '<small>será tentado de novo ao registrar</small>' : ''}
      ${d ? `<span class="chip azul">${d.acao === 'FORA' ? 'fica de fora: ' + esc(d.motivo) : 'aceito'}</span> <button type="button" class="btn" data-fila-acao="desfazer">Desfazer</button>` : ''}</div></div>`;
}
async function nsCarregarFila() {
  const painel = $('#nsFilaPainel'); painel.hidden = !pode('retificar_campo'); if (painel.hidden) return;
  const lista = await api('/api/ns/dia?fila=1').catch(() => null); if (!lista) return;
  NSV.filaDados = lista;
  const vale = {};                                    // decisões antigas só valem para o que ainda está na fila
  lista.forEach(n => { const d = NSV.fila[n.id] || {}; n.segmentos.filter(s => s.na_fila).forEach(s => {
    const x = d[s.ordem]; if (x && (x.acao === 'FORA' || s.situacao === 'CONFIRMAR')) (vale[n.id] = vale[n.id] || {})[s.ordem] = x; }); });
  NSV.fila = vale;
  $('#nsFila').innerHTML = lista.length ? lista.map(n => `<div class="painel" style="margin:8px 0;padding:12px" data-fila-ns="${n.id}">
      <div class="acoes" style="justify-content:space-between"><b>${esc(n.referencia)} · ${dataBR(n.data)} · ${esc(n.equipe_id)}</b><small>enviada por ${esc(n.registrada_por)}</small></div>
      ${n.segmentos.filter(s => s.na_fila).map(s => htmlFilaSeg(n, s)).join('')}
      <div class="acoes" style="margin-top:8px">${linkNs(n.id, 'pdf', 'Abrir a nota')}${n.croqui_id ? linkNs(n.id, 'croqui', 'Abrir o croqui') : ''}
        <button type="button" class="btn prim" data-fila-registrar="${n.id}">Registrar o que foi conferido</button></div></div>`).join('')
    : '<p class="vazio">Nenhuma nota do dia esperando a engenharia.</p>';
}
$('#nsFila').addEventListener('click', async ev => {
  const b = ev.target.closest('[data-fila-acao]'), reg = ev.target.closest('[data-fila-registrar]');
  if (b) {
    const caixa = b.closest('[data-fila-ns]'), id = +caixa.dataset.filaNs, o = +b.closest('[data-fila-ordem]').dataset.filaOrdem;
    const dec = NSV.fila[id] = NSV.fila[id] || {};
    if (b.dataset.filaAcao === 'desfazer') delete dec[o];
    else if (b.dataset.filaAcao === 'fora') {
      const motivo = prompt('Por que este segmento fica de fora?'); if (!motivo || !motivo.trim()) return;
      dec[o] = { ordem: o, acao: 'FORA', motivo: motivo.trim() };
    } else {
      const radio = $(`input[name="fila${id}_${o}"]:checked`, caixa), temRadio = !!$(`input[name="fila${id}_${o}"]`, caixa);
      if (temRadio && !radio) return toast('Marque um dos trechos possíveis.', 'erro');
      dec[o] = radio ? { ordem: o, acao: 'ACEITAR', candidato: +radio.value } : { ordem: o, acao: 'ACEITAR' };
    }
    const n = NSV.filaDados.find(x => x.id === id), s = n.segmentos.find(x => x.ordem === o);
    b.closest('[data-fila-ordem]').outerHTML = htmlFilaSeg(n, s);
    return;
  }
  if (!reg) return;
  const id = +reg.dataset.filaRegistrar;
  const r = await acao(() => api('/api/ns/dia/conferir', { ns_id: id, decisoes: Object.values(NSV.fila[id] || {}) })).catch(() => null);
  if (!r) return;
  delete NSV.fila[id];
  toast(r.fila.length ? `Registrado. Ainda aguardando: ${r.fila.length} segmento(s).` : 'Registrado: a nota do dia não tem mais nada na fila.', 'ok');
  carregarNotas(); recarregarCamadaMapa();
});
