'use strict';
/* Assistente (D-219): "O que você quer fazer?". A pessoa escreve ou fala; o servidor conversa com o modelo e devolve a
 * fala, os botões e o rascunho já conferido pelo código. O que está determinado (toque num botão, campo do rascunho) o
 * próprio sistema aplica, sem chamar o modelo. Nada é gravado até o toque no botão do rascunho, que envia o corpo à rota
 * de sempre (/api/solicitacao, /api/ocorrencia, /api/apropriacao). Sem cota da IA, o texto e o rascunho ficam guardados e
 * o formulário manual continua a um toque.
 * Histórico quase zero (D-226): a conversa fica só na tela (some ao recarregar) e NÃO vai ao servidor. Vão a mensagem,
 * o rascunho, os botões da tela e, se houver, só a última pergunta da IA ainda sem resposta. Ficam guardados no
 * navegador apenas o rascunho e o texto que está sendo digitado. */
const IA = { estado: null, conversa: [], rascunho: null, botoes: [], pergunta: null, ocupado: false, aviso: null, relogio: null, tentativas: 0, voz: null, falando: false };
const iaChave = () => 'mc-assistente-' + (USUARIO ? USUARIO.login : '');
const iaNorm = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const iaCru = () => IA.rascunho ? { tipo: IA.rascunho.tipo, campos: IA.rascunho.campos } : null;
const iaTela = id => podeAba(String(id).split('/')[0]);

function iaGuardar() {
  try {
    localStorage.setItem(iaChave(), JSON.stringify({ rascunho: iaCru(), texto: $('#iaTexto').value }));
  } catch (_) { /* sem storage: o rascunho vale só enquanto a tela está aberta */ }
}
function iaLer() {
  try { return JSON.parse(localStorage.getItem(iaChave()) || 'null'); } catch (_) { return null; }
}

// POST sem o aviso padrão: a tela do assistente mostra o próprio aviso (cota, IA desligada) e guarda o que a pessoa escreveu
async function iaPost(rota, corpo) {
  let r;
  try { r = await fetch(rota, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-MC': '1' }, body: JSON.stringify(corpo) }); }
  catch (_) { return { situacao: 'SEM_REDE', aviso: 'Sem conexão com o servidor. O que você escreveu continua aqui.' }; }
  const j = await r.json().catch(() => ({}));
  if (r.status === 401) { mostrarLogin(j.erro); return { situacao: 'SEM_REDE', aviso: j.erro || 'Entre de novo.' }; }
  if (!r.ok) return { situacao: 'ERRO', aviso: j.erro || `Erro ${r.status}` };
  return j;
}

async function carregarAssistente() {
  if (!IA.estado || IA.dono !== USUARIO.login) {
    IA.estado = await api('/api/assistente');
    IA.dono = USUARIO.login;
    const g = iaLer();
    IA.conversa = []; IA.botoes = []; IA.pergunta = null; IA.rascunho = null; IA.aviso = null;
    $('#iaTexto').value = (g && g.texto) || '';
    if (g && g.rascunho) {                               // o rascunho guardado volta conferido de novo pelo servidor,
      const r = await iaPost('/api/assistente/rascunho', { rascunho: g.rascunho, mudar: {} });     // com a pergunta do que falta
      if (r.situacao === 'OK') iaReceber(r);
    }
    iaMicrofone();
  }
  if (!IA.estado.disponivel) IA.aviso = { texto: IA.estado.motivo + ' Você pode seguir pelo formulário.', manual: true };
  iaDesenhar();
}

/* ---------------------------------------------------------------- desenho */
function iaDesenhar() {
  const vazio = !IA.conversa.length && !IA.rascunho;
  $('#iaConversa').innerHTML = IA.conversa.map(m => `<div class="ia-msg ${m.de === 'u' ? 'u' : 'a'}">${esc(m.texto)}</div>`).join('')
    + (IA.ocupado ? '<div class="ia-msg a ia-pensando" role="status">Pensando…</div>' : '');
  // conversa vazia: os atalhos do que este login lança (começam o rascunho sem gastar a IA)
  const atalhos = [];
  for (const u of IA.estado.usos) {
    if (u.tipo === 'PEDIDO') atalhos.push({ rotulo: 'Pedir material', iniciar: 'PEDIDO' });
    if (u.tipo === 'OCORRENCIA') atalhos.push({ rotulo: 'Choveu', iniciar: 'OCORRENCIA', chuva: true }, { rotulo: 'Relatar interferência', iniciar: 'OCORRENCIA' });
    if (u.tipo === 'APROPRIACAO') atalhos.push({ rotulo: 'Lançar um serviço', iniciar: 'APROPRIACAO' });
  }
  const botoes = vazio ? atalhos : IA.botoes;
  IA.naTela = botoes;
  $('#iaBotoes').innerHTML = botoes.map((b, i) => `<button type="button" class="btn grande" data-ia-botao="${i}">${esc(b.rotulo)}</button>`).join('');
  $('#iaBotoes').hidden = !botoes.length || IA.ocupado;
  iaDesenharAviso();
  iaDesenharRascunho();
  $('#iaEnviar').disabled = IA.ocupado;
  $('#iaNova').hidden = vazio;
  const c = $('#iaConversa'); c.scrollTop = c.scrollHeight;
  iaGuardar();
}
function iaDesenharAviso() {
  const a = IA.aviso, box = $('#iaAviso');
  box.hidden = !a; if (!a) return;
  const manuais = a.manual ? IA.estado.usos.filter(u => iaTela(u.tela)) : [];
  box.className = 'aviso ' + (a.tipo || 'info');
  box.innerHTML = `<b>${esc(a.texto)}</b>${a.conta ? ` <span id="iaConta">Tento de novo em ${a.conta} s.</span> <button type="button" class="btn" id="iaCancelarEspera">Não tentar</button>` : ''}
    ${IA.rascunho && a.manual ? '<div>O rascunho abaixo está guardado: você pode completar os campos e gravar por aqui mesmo.</div>' : ''}
    ${manuais.length ? `<div class="ia-manuais">${manuais.map(u => `<button type="button" class="btn" data-tela="${esc(u.tela)}">Abrir ${esc(u.pagina)}</button>`).join('')}</div>` : ''}`;
}
function iaCampo(f) {
  const id = `iaCampo-${f.id.replace(/[^a-zA-Z0-9]/g, '-')}`, v = f.valor == null ? '' : f.valor;
  let campo;
  if (f.tipo === 'opcoes') campo = `<select id="${id}" data-ia-campo="${esc(f.id)}"><option value="">Escolha</option>${f.opcoes.map(o => `<option value="${esc(o.v)}"${String(o.v) === String(v) ? ' selected' : ''}>${esc(o.r)}</option>`).join('')}</select>`;
  else if (f.tipo === 'area') campo = `<textarea id="${id}" data-ia-campo="${esc(f.id)}" rows="2" maxlength="${f.max || 600}">${esc(v)}</textarea>`;
  else if (f.tipo === 'data') campo = `<input id="${id}" type="date" data-ia-campo="${esc(f.id)}" value="${esc(v)}" max="${esc(f.max || '')}">`;
  else if (f.tipo === 'numero') campo = `<span class="ia-numero"><input id="${id}" inputmode="decimal" data-ia-campo="${esc(f.id)}" value="${esc(v === '' ? '' : String(v).replace('.', ','))}" autocomplete="off">${f.sufixo ? `<span>${esc(f.sufixo)}</span>` : ''}${f.remover ? `<button type="button" class="btn" data-ia-remover="${esc(f.remover)}">Tirar</button>` : ''}</span>`;
  else campo = `<input id="${id}" data-ia-campo="${esc(f.id)}" value="${esc(v)}" placeholder="${esc(f.dica || '')}" autocomplete="off">`;
  return `<label for="${id}">${esc(f.rotulo)}${campo}</label>`;
}
function iaDesenharRascunho() {
  const v = IA.rascunho, box = $('#iaRascunho');
  box.hidden = !v; $('.ia').classList.toggle('com-rascunho', !!v);
  if (!v) { box.innerHTML = ''; return; }
  box.innerHTML = `<div class="acoes ia-rascunho-topo"><h2>Rascunho · ${esc(v.titulo)}</h2>
      <span class="chip ${v.pronto ? 'verde' : 'amarelo'}">${v.pronto ? 'pronto para conferir' : 'incompleto'}</span></div>
    <dl class="ia-linhas">${v.linhas.map(([a, b]) => `<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join('')}</dl>
    ${v.avisos.map(a => `<div class="aviso info">${esc(a)}</div>`).join('')}
    <div class="ia-form">${v.form.map(iaCampo).join('')}
      ${v.tipo === 'APROPRIACAO' && v.campos.item_ref ? '<label for="iaEvidencias">Evidências (opcional: fotos ou PDF)<input id="iaEvidencias" type="file" multiple accept="image/jpeg,image/png,application/pdf"></label>' : ''}</div>
    ${v.faltam.length ? `<p class="ia-falta" role="status"><b>Falta:</b> ${v.faltam.map(f => esc(f.pergunta)).join(' ')}</p>` : ''}
    <p class="ia-status" id="iaStatus" role="status"></p>
    <button type="button" class="btn prim grande" id="iaGravar"${v.pronto ? '' : ' disabled'}>${esc(v.confirmar)}</button>
    <p class="vazio ia-nota">Nada é gravado antes deste toque. Fica registrado com o seu usuário, pela rotina de sempre.</p>
    <div class="acoes">${iaTela(v.manual.tela) ? `<button type="button" class="btn" data-tela="${esc(v.manual.tela)}">Abrir o formulário completo</button>` : ''}
      <button type="button" class="btn" id="iaDescartar">Descartar o rascunho</button></div>`;
}

/* ---------------------------------------------------------------- conversa */
function iaReceber(r, opcoes = {}) {
  if ('rascunho' in r) IA.rascunho = r.rascunho;
  if (r.situacao === 'OK') {
    IA.aviso = IA.estado.disponivel ? null : IA.aviso; IA.tentativas = 0;
    IA.botoes = r.botoes || [];
    IA.pergunta = r.pergunta || null;                    // só ela volta ao servidor na próxima mensagem
    if (r.resposta && !opcoes.calado) IA.conversa.push({ de: 'a', texto: r.resposta });
    return true;
  }
  return false;
}
async function iaEnviar(texto, automatico) {
  texto = String(texto || '').trim();
  if (IA.ocupado || !texto) return;
  const igual = (IA.naTela || []).find(b => iaNorm(b.rotulo) === iaNorm(texto));     // escreveu (ou falou) o nome de um botão: é o toque
  if (igual) { $('#iaTexto').value = ''; return iaTocar(igual); }
  if (!IA.estado.disponivel) { IA.aviso = { texto: IA.estado.motivo + ' Você pode seguir pelo formulário.', manual: true }; return iaDesenhar(); }
  iaPararEspera();
  IA.ocupado = true; IA.aviso = null; iaDesenhar();
  const r = await iaPost('/api/assistente/mensagem', { texto, pergunta: IA.pergunta, rascunho: iaCru(), opcoes: IA.botoes });
  IA.ocupado = false;
  if (r.situacao === 'OK') {
    IA.conversa.push({ de: 'u', texto });
    iaReceber(r);
    $('#iaTexto').value = '';
  } else {                                              // a mensagem não foi: o texto fica na caixa e o rascunho, guardado
    iaReceber(r);
    const espera = (r.cota || {}).espera_s;
    IA.aviso = { texto: r.aviso || 'A IA não respondeu agora.', manual: true, tipo: r.situacao === 'ERRO' ? 'problema' : 'info' };
    if (r.situacao === 'COTA' && espera && espera <= 45 && IA.tentativas < 2) iaEsperar(espera + 2, texto);
    else IA.tentativas = 0;
  }
  iaDesenhar();
  if (!automatico) $('#iaTexto').focus();
}
// limite por minuto do plano gratuito: espera curta com contagem e uma nova tentativa sozinha (no máximo duas)
function iaEsperar(segundos, texto) {
  IA.tentativas += 1; IA.aviso.conta = segundos;
  IA.relogio = setInterval(() => {
    IA.aviso.conta -= 1;
    const el = $('#iaConta'); if (el) el.textContent = `Tento de novo em ${IA.aviso.conta} s.`;
    if (IA.aviso.conta <= 0) { iaPararEspera(); iaEnviar(texto, true); }
  }, 1000);
}
function iaPararEspera() { clearInterval(IA.relogio); IA.relogio = null; if (IA.aviso) delete IA.aviso.conta; }

async function iaAplicar(corpo, fala) {
  if (IA.ocupado) return false;
  IA.ocupado = true;
  const r = await iaPost('/api/assistente/rascunho', { rascunho: iaCru(), ...corpo });
  IA.ocupado = false;
  if (r.situacao !== 'OK') { toast(r.aviso || 'Não consegui aplicar.', 'erro'); iaDesenhar(); return false; }
  if (fala) IA.conversa.push({ de: 'u', texto: fala });
  iaReceber(r, { calado: !fala });
  iaDesenhar();
  if (!fala && r.resposta) { const s = $('#iaStatus'); if (s) s.textContent = IA.rascunho && IA.rascunho.pronto ? '' : r.resposta; }
  return true;
}
async function iaTocar(b) {
  if (b.tela) return abrirAba(b.tela);
  if (b.sub) {                                          // grupo (ex.: Locação): abre os itens dele, sem chamar ninguém
    IA.conversa.push({ de: 'u', texto: b.rotulo }, { de: 'a', texto: b.pergunta });
    IA.botoes = b.sub; IA.pergunta = b.pergunta;
    return iaDesenhar();
  }
  if (b.iniciar) return iaAplicar({ iniciar: b.iniciar, chuva: !!b.chuva }, b.rotulo);
  if (b.aplicar) {
    const corpo = { mudar: b.aplicar };
    if (b.tipo && (!IA.rascunho || IA.rascunho.tipo !== b.tipo)) corpo.iniciar = b.tipo;
    return iaAplicar(corpo, b.rotulo);
  }
  if (b.texto) return iaEnviar(b.texto);
}

$('#iaForm').addEventListener('submit', ev => { ev.preventDefault(); iaEnviar($('#iaTexto').value); });
$('#iaTexto').addEventListener('keydown', ev => { if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); iaEnviar($('#iaTexto').value); } });
$('#iaTexto').addEventListener('input', iaGuardar);
$('#iaBotoes').addEventListener('click', ev => { const b = ev.target.closest('[data-ia-botao]'); if (b && IA.naTela[b.dataset.iaBotao]) iaTocar(IA.naTela[b.dataset.iaBotao]); });
$('#iaAviso').addEventListener('click', ev => { if (ev.target.closest('#iaCancelarEspera')) { iaPararEspera(); IA.tentativas = 0; iaDesenhar(); } });
$('#iaNova').addEventListener('click', () => {
  if (IA.rascunho && !confirm('Começar uma conversa nova apaga o rascunho. Continuar?')) return;
  iaPararEspera(); IA.conversa = []; IA.botoes = []; IA.pergunta = null; IA.rascunho = null; IA.tentativas = 0;
  IA.aviso = IA.estado.disponivel ? null : IA.aviso; $('#iaTexto').value = '';
  iaDesenhar();
});

/* ---------------------------------------------------------------- rascunho: os campos e o toque que grava */
$('#iaRascunho').addEventListener('change', ev => {
  const c = ev.target.closest('[data-ia-campo]'); if (!c) return;
  iaAplicar({ mudar: { [c.dataset.iaCampo]: c.value } });
});
$('#iaRascunho').addEventListener('click', async ev => {
  const tirar = ev.target.closest('[data-ia-remover]');
  if (tirar) return iaAplicar({ mudar: { [tirar.dataset.iaRemover]: true } });
  if (ev.target.closest('#iaDescartar')) return iaAplicar({ descartar: true }, 'Descartar o rascunho');
  const bt = ev.target.closest('#iaGravar'); if (!bt || !IA.rascunho || !IA.rascunho.pronto) return;
  const v = IA.rascunho, corpo = { ...v.corpo }, arqs = [...(($('#iaEvidencias') || {}).files || [])];
  bt.disabled = true;
  try {
    if (arqs.length) corpo.evidencias = await Promise.all(arqs.map(async a => ({ nome: a.name, conteudo_b64: await lerOriginal(a) })));
    const r = await acao(() => api(v.rota, corpo)).catch(() => null);   // a rota de sempre: permissão, autoria, reenvio e auditoria
    if (!r) return;
    const feito = v.tipo === 'PEDIDO' ? `Requisição nº ${r.id} enviada: ela entra aberta, sem aprovação.`
      : v.tipo === 'APROPRIACAO' ? (r.situacao === 'PROPOSTA' ? `Apropriação nº ${r.id} gravada e proposta na medição de teste (gaveta 5).`
        : `Apropriação nº ${r.id} gravada. Ela fica parada: a restrição aparece na Medição, em "Medível com restrição".`)
      : r.ids ? `Chuva registrada em ${r.ids.length} equipe(s).` : v.corpo.categoria === 'CHUVA' ? 'Chuva registrada.' : `Registro nº ${r.id} gravado.`;
    toast(feito, 'ok');
    IA.conversa.push({ de: 'a', texto: 'Gravado. ' + feito });
    IA.rascunho = null; IA.pergunta = null;
    IA.botoes = iaTela(v.manual.tela) ? [{ rotulo: 'Ver em ' + v.manual.rotulo, tela: v.manual.tela }] : [];
    iaDesenhar();
    if (arqs.length && typeof driveEmSegundoPlano === 'function') driveEmSegundoPlano();
  } finally { bt.disabled = false; }
});

/* ---------------------------------------------------------------- microfone: a transcrição do próprio navegador, onde existir */
function iaMicrofone() {
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition, bt = $('#iaMic');
  if (!Rec || IA.voz) { bt.hidden = !Rec; return; }
  bt.hidden = false;
  const rec = IA.voz = new Rec();
  rec.lang = 'pt-BR'; rec.interimResults = true; rec.continuous = false;
  let base = '';
  const parar = () => { IA.falando = false; bt.setAttribute('aria-pressed', 'false'); bt.title = bt.ariaLabel = 'Falar'; };
  rec.onstart = () => { IA.falando = true; base = $('#iaTexto').value.trim(); bt.setAttribute('aria-pressed', 'true'); bt.title = bt.ariaLabel = 'Parar de ouvir'; };
  rec.onresult = ev => {
    const dito = [...ev.results].map(r => r[0].transcript).join(' ').trim();
    $('#iaTexto').value = (base ? base + ' ' : '') + dito; iaGuardar();
  };
  rec.onerror = ev => { parar(); if (ev.error !== 'aborted' && ev.error !== 'no-speech') toast(ev.error === 'not-allowed' ? 'Permita o microfone no navegador para falar.' : 'Não consegui ouvir. Tente de novo ou escreva.', 'erro'); };
  rec.onend = () => { parar(); $('#iaTexto').focus(); };
  bt.addEventListener('click', () => { try { IA.falando ? rec.stop() : rec.start(); } catch (_) { parar(); } });
}
