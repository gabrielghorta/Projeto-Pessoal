'use strict';
/* Sistema Morro da Cruz — interface (sem dependências externas). */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nf = (v, c = 2) => v == null ? '—' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: c });
const brl = v => v == null ? 'PENDENTE' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const hoje = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const curto = id => String(id ?? '').replace(/^Zona\d\d_PB\d\d_|^ADUTORA_PB\d\d_/, '');

const STATUS = {
  NAO_EXECUTADO: ['Não executado', ''], EM_EXECUCAO: ['Em execução', 'laranja'], CONCLUIDO_MES: ['Concluído — aguardando OK', 'vermelho'],
  OK_FISCAL: ['OK Fiscalização', 'verde'], MEDIDO_ANTERIOR: ['Medido anteriormente', 'amarelo'],
};
let RESUMO = null, MATERIAIS = [], MEDICAO_ATUAL = null;

async function api(url, body) {
  const r = await fetch(url, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.erro || `Erro ${r.status}`);
  return j;
}
function toast(msg, tipo = '') {
  const t = $('#toast'); t.textContent = msg; t.className = tipo; t.style.display = 'block';
  clearTimeout(toast.h); toast.h = setTimeout(() => t.style.display = 'none', tipo === 'erro' ? 7000 : 3500);
}
async function acao(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(okMsg, 'ok'); return r; } catch (e) { toast(e.message, 'erro'); throw e; }
}
const formObj = f => Object.fromEntries(new FormData(f).entries());

/* ---------------------------------------------------------------- abas */
$$('nav.abas button').forEach(b => b.addEventListener('click', () => abrirAba(b.dataset.aba)));
function abrirAba(id) {
  $$('nav.abas button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.aba === id)));
  $$('section.aba').forEach(s => s.classList.toggle('ativa', s.id === 'aba-' + id));
  try { localStorage.setItem('aba', id); } catch (_) { /* sem storage */ }
  ({ mapa: carregarMapa, almox: carregarAlmox, campo: () => {}, esteira: carregarEsteira, medicao: carregarMedicoes })[id]();
}

/* ---------------------------------------------------------------- busca de trecho/nó */
function ligarBusca(input, aoEscolher) {
  const ul = input.parentElement.querySelector('ul');
  let t;
  input.addEventListener('input', () => {
    clearTimeout(t); input.dataset.tipo = ''; input.dataset.id = '';
    t = setTimeout(async () => {
      const q = input.value.trim(); if (q.length < 2) { ul.hidden = true; return; }
      const res = await api('/api/buscar?q=' + encodeURIComponent(q));
      ul.innerHTML = res.map((r, i) => `<li data-i="${i}"><span>${esc(r.rotulo)}</span><small>${r.tipo === 'TRECHO' ? 'trecho' : 'nó/caixa'} · ${esc(r.extra || '')}</small></li>`).join('') || '<li><small>nada encontrado</small></li>';
      ul.hidden = false;
      ul.onclick = ev => { const li = ev.target.closest('li[data-i]'); if (!li) return; const r = res[+li.dataset.i];
        input.value = r.rotulo; input.dataset.tipo = r.tipo; input.dataset.id = r.id; ul.hidden = true; aoEscolher && aoEscolher(r); };
    }, 180);
  });
  input.addEventListener('blur', () => setTimeout(() => ul.hidden = true, 200));
}

/* ---------------------------------------------------------------- 1. mapa & fiscalização */
async function carregarMapa() {
  const r = RESUMO = await api('/api/resumo');
  $('#obraContrato').textContent = r.contrato;
  $('#kpis').innerHTML = [
    ['Rede de projeto', nf(r.extensao_m) + ' m'], ['Rede reaterrada', nf(r.executado_m) + ' m'],
    ['Trechos', nf(r.trechos)], ['Nós e caixas', nf(r.elementos)], ['Validados (OK interno)', nf(r.ok_fiscal)], ['Contrato (cl. 3.1)', brl(r.valor_contrato)],
  ].map(([k, v]) => `<div class="kpi"><span>${k}</span><b>${v}</b></div>`).join('') +
    (r.itens_pendentes ? `<div class="kpi" style="border-top-color:var(--vermelho)"><span>Itens 06.2 sem quantidade/unidade com fonte</span><b>${nf(r.itens_pendentes)}</b></div>` : '');
  const fr = $('#mapaFrame');
  if (fr.src.endsWith('about:blank')) fr.src = '/mapa/';
  const est = await api('/api/mapa/estado' + (MEDICAO_ATUAL ? '?medicao=' + MEDICAO_ATUAL : ''));
  $('#pins').innerHTML = est.pins.length ? est.pins.map(p => `<div class="acoes" style="margin-bottom:6px">📍 <b>${esc(p.equipe)}</b> <button class="btn" data-fisc="${esc(p.alvo_tipo)}|${esc(p.alvo_id)}">${esc(curto(p.alvo_id))}</button></div>`).join('')
    : '<span class="vazio">Nenhum check-in aberto hoje.</span>';
  $('#semPosicao').innerHTML = est.sem_posicao.map(e => `<div style="margin-bottom:6px"><b>${esc(e.numero)}</b> <span class="chip ${String(e.status_posicao || '').startsWith('PROV') ? 'amarelo' : 'vermelho'}">${esc(e.status_posicao || 'sem posição')}</span><br><small>${esc(e.nomenclaturas)}</small></div>`).join('');
  const ret = est.retirados_com_historico || [];
  $('#painelRetirados').hidden = !ret.length;
  $('#retirados').innerHTML = ret.map(r => `<div style="margin-bottom:6px"><button class="btn" data-fisc="${esc(r.alvo_tipo)}|${esc(r.alvo_id)}">${esc(curto(r.nome))}</button><br><small>histórico: ${esc((r.historico || []).join(', '))}${(r.situacoes || []).length ? ' · ' + esc(r.situacoes.join('; ')) : ''}</small></div>`).join('');
}
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-fisc]'); if (!b) return;
  const [t, id] = b.dataset.fisc.split('|'); mostrarFiscal(t, id);
});
ligarBusca($('#fiscBusca'), r => mostrarFiscal(r.tipo, r.id));
window.addEventListener('message', ev => {   // seleção vinda do mapa REV02 (camada mapa_iluminado.js)
  if (ev.origin !== location.origin || !ev.data || ev.data.tipo !== 'mc-selecao') return;
  mostrarFiscal(ev.data.alvo_tipo, ev.data.alvo_id);
});

async function mostrarFiscal(tipo, id) {
  const d = await acao(() => api(`/api/detalhe?tipo=${tipo}&id=${encodeURIComponent(id)}`));
  const ex = d.execucao, st = d.fotos_faltando;
  const linhas = tipo === 'TRECHO' ? [
    ['Frente / equipe', `${esc(d.frente_id)} · ${esc(d.equipe)}`], ['Extensão', nf(d.extensao_m) + ' m'], ['DE', `${d.de_mm} mm · ${esc(d.material)} · ${esc(d.metodologia)}`],
    ['Pontas', `${esc(curto(d.no_ini))} → ${esc(curto(d.no_fim))}`], ['Item BM', d.mnd ? `<span class="chip vermelho">MND — item a definir</span> <small>06.1 traz ${esc(d.codigo_bm)}</small>` : '2.2_' + esc(d.codigo_bm)],
    ['Executado / reaterrado', ex ? `${nf(ex.metros_executados)} m / ${nf(ex.metros_reaterrados)} m` : '—'],
  ] : [
    ['Elemento', `${esc(d.numero)} · ${esc(d.tipo_elemento)} · ${esc(d.pb)}`], ['Frente', esc(d.frente_id)],
    ['Itens (06.2)', esc(d.texto)], ['Outras frentes do elemento', (d.outras_atividades || []).map(o => esc(o.nomenclatura)).join(', ') || '—'], ['Trechos ligados', d.trechos_ligados.map(t => esc(curto(t.ponto))).join(', ') || '—'],
    ['Posição', d.lat ? `${d.lat}, ${d.lon}` : '<span class="chip vermelho">sem posição</span>'],
  ];
  const decs = Object.fromEntries([...(d.decisoes || []), ...(d.decisoes_sugeridas || [])].map(x => [x.id, x]));
  const avisos = (d.avisos || []).map(a => `<div class="aviso ${a.tipo === 'PROBLEMA' ? 'problema' : 'sugestao'}"><b>${a.tipo === 'PROBLEMA' ? 'Problema (AA)' : 'Sugestão (AB)'}</b>
      ${a.prioridade ? `<span class="chip">${esc(a.prioridade)}</span>` : ''} ${esc(a.texto)}
      ${a.decisoes.map(i => `<br><span class="chip verde">${esc(i)} · ${esc(decs[i] ? decs[i].status : '')}</span> <small>${esc(decs[i] ? decs[i].decisao : '')}</small>`).join('')}
      ${(a.sugestoes || []).map(i => `<br><span class="chip" title="Sugestão por semelhança de texto: a decisão NÃO foi aplicada a este aviso">possível relação com ${esc(i)} — revisar</span>`).join('')}</div>`).join('')
    + (d.avisos && d.avisos.length ? '<p class="vazio" style="margin:4px 0">Avisos = texto de origem da 06.2 (AA/AB/AW). Em verde, só decisões com vínculo explícito a este aviso (não reabertas pela reimportação). "Revisar" = semelhança de texto, sem decisão aplicada.</p>' : '')
    + ((d.decisoes || []).filter(x => !(d.avisos || []).some(a => a.decisoes.includes(x.id))).map(x => `<div class="aviso info"><span class="chip verde">${esc(x.id)} · ${esc(x.status)}</span> ${esc(x.assunto)} — <small>${esc(x.decisao)}</small></div>`).join(''));
  const bloqueio = d.perfil_bloqueado ? `<div class="aviso problema"><b>E06:</b> ${esc(d.perfil_bloqueado)} — cálculo bloqueado.</div>` : '';
  const pode = ex && ex.concluido && !st.length && !ex.ok_fiscal_em;
  $('#fiscDetalhe').className = '';
  $('#fiscDetalhe').innerHTML = `<h2 style="word-break:break-all">${esc(curto(d.nome))}</h2>
    ${d.retirado ? '<div class="aviso problema"><b>Retirado da revisão vigente do projeto.</b> Consulta do histórico; novos lançamentos bloqueados.</div>' : ''}
    <table>${linhas.map(([k, v]) => `<tr><th style="position:static;width:40%">${k}</th><td>${v}</td></tr>`).join('')}</table>
    ${bloqueio}${avisos}
    <p>Fotos: ${st.length ? st.map(c => `<span class="chip vermelho">falta ${c}</span>`).join(' ') : '<span class="chip verde">completas</span>'}
       ${ex && ex.ok_fiscal_em ? `<span class="chip verde">OK em ${esc(ex.ok_fiscal_em)} por ${esc(ex.ok_fiscal_por)}</span>` : ''}</p>
    <label class="check" style="margin:8px 0"><input type="checkbox" id="okFiscal" ${ex && ex.ok_fiscal_em ? 'checked disabled' : pode ? '' : 'disabled'}>
      <b>[✓] OK Fiscalização — Pronto p/ Medir</b></label>
    ${!pode && !(ex && ex.ok_fiscal_em) ? '<div class="vazio">Exige 100 % reaterrado e as fotos obrigatórias.</div>' : ''}
    ${ex && ex.ok_fiscal_em && !ex.recomposicao_ok ? `<div class="form" style="margin-top:10px"><b>Recomposição (equipe de pavimento)</b>
      <div class="linha"><select id="recTipo"><option>CALÇADA</option><option>ASFALTO</option></select><input id="recQtd" type="number" step="any" placeholder="quantidade"></div>
      <button class="btn" id="recBtn">Lançar recomposição</button></div>` : ''}`;
  const ok = $('#okFiscal');
  if (ok && !ok.disabled) ok.addEventListener('change', async () => {
    if (!ok.checked) return;
    if (!confirm('Confirmar o OK interno? Gera PROPOSTA de lançamentos na medição de TESTE e envia o trecho para a Esteira de Cadastro. Não é aprovação da Caesb.')) { ok.checked = false; return; }
    await acao(() => api('/api/ok-fiscal', { alvo_tipo: tipo, alvo_id: id, data: hoje() }), 'OK interno registrado — proposta lançada na medição de TESTE.').catch(() => ok.checked = false);
    mostrarFiscal(tipo, id); recarregarCamadaMapa(); carregarMapa();
  });
  const rb = $('#recBtn');
  if (rb) rb.addEventListener('click', async () => {
    await acao(() => api('/api/recomposicao', { alvo_tipo: tipo, alvo_id: id, tipo: $('#recTipo').value, quantidade: $('#recQtd').value, data: hoje() }), 'Recomposição lançada (gaveta 4).');
    mostrarFiscal(tipo, id);
  });
  try { $('#mapaFrame').contentWindow.postMessage({ tipo: 'mc-focar', alvo_tipo: tipo, alvo_id: d.nome }, location.origin); } catch (_) { /* mapa ausente */ }
}
function recarregarCamadaMapa() {
  try { $('#mapaFrame').contentWindow.postMessage({ tipo: 'mc-recarregar' }, location.origin); } catch (_) { /* mapa ausente */ }
}

/* ---------------------------------------------------------------- 2. almoxarifado & equipes */
async function carregarAlmox() {
  MATERIAIS = await api('/api/estoque');
  const opt = m => `<option value="${esc(m.id)}">${esc(m.id)} — ${esc(m.descricao.slice(0, 70))} (${esc(m.unidade)})</option>`;
  $$('.selMaterial').forEach(s => s.innerHTML = MATERIAIS.filter(m => m.propriedade !== 'ANKARA').map(opt).join(''));
  $$('.selMaterialAnkara').forEach(s => s.innerHTML = MATERIAIS.filter(m => m.propriedade === 'ANKARA').map(opt).join(''));
  $$('.selMaterialReserva').forEach(s => s.innerHTML = MATERIAIS.filter(m => m.propriedade !== 'CONSUMO' && m.disponivel > 0).map(m => `<option value="${esc(m.id)}">${esc(m.id)} (disponível ${nf(m.disponivel)} ${esc(m.unidade)})</option>`).join('') || '<option value="">nada disponível</option>');
  renderEstoque();
  const res = await api('/api/reservas');
  $('#reservasLista').innerHTML = res.length ? `<table><thead><tr><th>Dia</th><th>Equipe</th><th>Material</th><th class="n">Qtd.</th><th></th></tr></thead><tbody>${res.map(r => `<tr><td>${esc(r.data)}</td><td>${esc(r.equipe_id)}</td><td>${esc(r.material_id)}</td><td class="n">${nf(r.quantidade, 3)}</td><td><button class="btn" data-cancelar-reserva="${r.id}">Cancelar</button></td></tr>`).join('')}</tbody></table>` : '<span class="vazio">Nenhuma reserva ativa.</span>';
  const cons = await api('/api/consumo');
  $('#consumo').innerHTML = `<table><thead><tr><th>Tubo</th><th class="n">Previsto (metros apontados)</th><th class="n">Aplicado confirmado</th><th class="n">Diferença</th></tr></thead><tbody>${cons.map(c => `<tr><td>${esc(c.material_id)}</td><td class="n">${nf(c.previsto_apontado)}</td><td class="n">${nf(c.aplicado_confirmado)}</td><td class="n">${c.diferenca ? `<span class="chip amarelo">${nf(c.diferenca)}</span>` : '—'}</td></tr>`).join('')}</tbody></table><p class="vazio" style="margin:4px 0">O previsto é só referência: nunca baixa estoque.</p>`;
  const movs = await api('/api/movimentos?limite=40');
  $('#movimentos').innerHTML = movs.length ? `<table><thead><tr><th>#</th><th>Data</th><th>Tipo</th><th>Material</th><th class="n">Qtd.</th><th>Equipe</th><th>Documento / responsável</th><th></th></tr></thead><tbody>${movs.map(m => `<tr${m.estornado_em ? ' style="opacity:.55;text-decoration:line-through"' : ''}><td>${m.id}</td><td>${esc(m.data)}</td><td>${esc(m.tipo)}${m.tipo === 'BAIXA_TEORICA' ? ' <small>(legado, fora do saldo)</small>' : ''}</td><td>${esc(m.material_id)}</td><td class="n">${nf(m.quantidade, 3)}</td><td>${esc(m.equipe_id || '')}</td><td>${esc([m.documento, m.responsavel, m.autorizacao].filter(Boolean).join(' · '))}</td>
    <td>${m.estornado_em ? `<small style="text-decoration:none">estornado: ${esc(m.estorno_motivo)}</small>` : m.tipo === 'ENTRADA_NF' ? ''
      : ['APLICADO', 'SOBRA', 'PERDA'].includes(m.tipo) && m.checkin_encerrado ? `<button class="btn" data-retificar="${m.id}" data-q="${m.quantidade}">Retificar fechamento</button>`
      : `<button class="btn" data-estornar="${m.id}">Estornar</button>`}${m.retificacao_id ? ` <small>retificação #${m.retificacao_id}</small>` : ''}</td></tr>`).join('')}</tbody></table>` : '<div class="vazio" style="padding:10px">Nenhum movimento.</div>';
  const comp = await api('/api/compat-caesb');
  $('#compat').innerHTML = `<table><thead><tr><th>Tubo</th><th class="n">Projeto 06.1 (m)</th><th class="n">Estoque Caesb</th><th class="n">Emprestado p/ outras obras</th><th class="n">Retirado pela Ankara</th><th class="n">Aplicado em obra</th><th class="n">Perdido</th><th class="n">Saldo virtual a retirar</th><th class="n">Saldo físico</th></tr></thead><tbody>
    ${comp.map(c => `<tr><td>${esc(c.descricao)}</td><td class="n">${nf(c.projeto)}</td><td class="n">${nf(c.estoque_caesb)}</td><td class="n">${nf(c.emprestado)}</td><td class="n">${nf(c.retirado)}</td><td class="n">${nf(c.aplicado)}</td><td class="n">${nf(c.perdido)}</td><td class="n"><b>${nf(c.saldo_virtual)}</b></td><td class="n">${nf(c.saldo_fisico)}</td></tr>`).join('')}</tbody></table>`;
  const nfs = await api('/api/nfs');
  $('#nfLista').innerHTML = nfs.length ? `<table><thead><tr><th>NF</th><th>Entrega</th><th>Status</th><th></th></tr></thead><tbody>${nfs.map(n => `<tr><td>${esc(n.numero)}${n.faturamento_etapas ? ' <span class="chip azul">etapas</span>' : ''}</td><td>${esc(n.data_entrega)}</td>
    <td><span class="chip ${n.status === 'ACEITO' ? 'verde' : 'amarelo'}">${n.status}</span></td>
    <td>${n.status === 'QUARENTENA' ? `<input placeholder="laudo (arquivo)" data-laudo="${n.id}" style="width:120px"> <button class="btn" data-aceitar="${n.id}">Aceitar</button>` : ''}</td></tr>`).join('')}</tbody></table>` : '';
  await carregarCheckouts();
  if (!$('#hIni').value) { $('#hIni').value = hoje().slice(0, 8) + '01'; $('#hFim').value = hoje(); }
  carregarHistograma();
}
function renderEstoque() {
  const f = $('#estFiltro').value, so = $('#estSaldo').checked;
  const lst = MATERIAIS.filter(m => (!f || m.propriedade === f) && (!so || m.saldo_almox || m.custodia || m.quarentena || m.reservado));
  $('#estoque').innerHTML = lst.length ? `<table><thead><tr><th>Material</th><th>Propriedade</th><th>Unid.</th><th class="n">Saldo físico</th><th class="n">Reservado</th><th class="n">Disponível</th><th class="n">Quarentena</th><th class="n">Com as equipes</th><th class="n">Preço BM</th></tr></thead><tbody>
    ${lst.map(m => `<tr><td>${esc(m.id)} — ${esc(m.descricao.slice(0, 80))}</td><td><span class="chip ${m.propriedade === 'CAESB' ? 'azul' : m.propriedade === 'ANKARA' ? 'laranja' : ''}">${m.propriedade}</span></td><td>${esc(m.unidade)}</td>
      <td class="n">${nf(m.saldo_almox, 3)}</td><td class="n">${nf(m.reservado, 3)}</td><td class="n"><b>${nf(m.disponivel, 3)}</b></td><td class="n">${nf(m.quarentena, 3)}</td><td class="n">${nf(m.custodia, 3)}</td><td class="n">${m.propriedade === 'CAESB' ? 'R$ 0,00' : brl(m.preco_unitario)}</td></tr>`).join('')}</tbody></table>`
    : '<div class="vazio" style="padding:10px">Nenhum material com movimento.</div>';
}
$('#estFiltro').addEventListener('change', renderEstoque);
$('#estSaldo').addEventListener('change', renderEstoque);
$('#nfLista').addEventListener('click', async ev => {
  const b = ev.target.closest('[data-aceitar]'); if (!b) return;
  const laudo = $(`[data-laudo="${b.dataset.aceitar}"]`).value;
  await acao(() => api('/api/nf/aceitar', { nf_id: b.dataset.aceitar, laudo_arquivo: laudo }), 'NF aceita — fora da quarentena.');
  carregarAlmox();
});
$('#fMov').addEventListener('submit', async ev => {
  ev.preventDefault();
  await acao(() => api('/api/movimento', formObj(ev.target)), 'Movimento lançado.'); ev.target.reset(); carregarAlmox();
});
$('#fReserva').addEventListener('submit', async ev => {
  ev.preventDefault();
  await acao(() => api('/api/reserva', formObj(ev.target)), 'Reserva registrada — disponível reduzido para as outras equipes.'); ev.target.reset(); carregarAlmox();
});
document.addEventListener('click', async ev => {
  const c = ev.target.closest('[data-cancelar-reserva]');
  if (c) {
    const motivo = prompt('Motivo do cancelamento da reserva:'); if (!motivo) return;
    await acao(() => api('/api/reserva/cancelar', { reserva_id: c.dataset.cancelarReserva, motivo }), 'Reserva cancelada.'); carregarAlmox();
  }
  const e = ev.target.closest('[data-estornar]');
  if (e) {
    const motivo = prompt('Motivo do estorno (o movimento não é apagado):'); if (!motivo) return;
    const responsavel = prompt('Responsável pelo estorno:'); if (!responsavel) return;
    const corpo = { movimento_id: e.dataset.estornar, motivo, responsavel };
    try { await api('/api/estorno', corpo); toast('Movimento estornado.', 'ok'); }
    catch (err) {
      if (!/sem cobertura/.test(err.message) || !confirm(err.message + '\n\nReduzir/cancelar as reservas mais recentes (registrado com este estorno)?')) { toast(err.message, 'erro'); return; }
      await acao(() => api('/api/estorno', { ...corpo, ajustar_reservas: true }), 'Movimento estornado; reservas ajustadas e registradas.');
    }
    carregarAlmox();
  }
  const rt = ev.target.closest('[data-retificar]');
  if (rt) {
    const q = +rt.dataset.q, n = s => +(prompt(`${s} (total ${q}):`, '0') || 0);
    const destino = { aplicado: n('Aplicado'), sobra: n('Sobra devolvida'), perda: n('Perda'), fica_com_equipe: n('Fica com a equipe') };
    if (destino.perda) destino.motivo_perda = prompt('Motivo da perda:') || '';
    const motivo = prompt('Motivo da retificação:'); if (!motivo) return;
    const responsavel = prompt('Responsável:'); if (!responsavel) return;
    await acao(() => api('/api/retificar', { movimento_id: rt.dataset.retificar, destino, motivo, responsavel }), 'Fechamento retificado (o lançamento original fica no histórico).');
    carregarAlmox();
  }
});
$('#fNF').addEventListener('submit', async ev => {
  ev.preventDefault(); const o = formObj(ev.target);
  await acao(() => api('/api/nf', { numero: o.numero, data_entrega: o.data_entrega, fornecedor: o.fornecedor, chave_nfe: o.chave_nfe,
    faturamento_etapas: !!o.faturamento_etapas, itens: [{ material_id: o.material_id, quantidade: +o.quantidade, valor_unitario: +o.valor_unitario || 0 }] }), 'NF registrada (quarentena).');
  ev.target.reset(); carregarAlmox();
});
$('#fRecurso').addEventListener('submit', async ev => {
  ev.preventDefault(); const o = formObj(ev.target);
  if (o.nome) await acao(() => api('/api/funcionario', o));
  if (o.descricao) await acao(() => api('/api/maquina', o));
  toast('Equipe atualizada.', 'ok'); ev.target.reset();
});

// check-in
const fCk = $('#fCheckin');
ligarBusca($('input[name=alvo_txt]', fCk));
$('select[name=equipe_id]', fCk).addEventListener('change', async ev => {
  const eq = await api('/api/equipe?id=' + ev.target.value);
  const it = [...eq.funcionarios.map(f => ['f', f.id, `${f.nome}${f.funcao ? ' · ' + f.funcao : ''}`]), ...eq.maquinas.map(m => ['m', m.id, '🚜 ' + m.descricao])];
  $('#ckPresentes').innerHTML = it.length ? it.map(([t, id, n]) => `<label class="check"><input type="checkbox" data-t="${t}" value="${id}" checked> ${esc(n)}</label>`).join('')
    : '<span class="vazio">Cadastre funcionários e máquinas da equipe abaixo.</span>';
});
$('#ckAddMat').addEventListener('click', () => {
  const div = document.createElement('div'); div.className = 'linha';
  div.innerHTML = `<select data-mat>${MATERIAIS.filter(m => m.propriedade !== 'CONSUMO' && m.saldo_almox > 0).map(m => `<option value="${esc(m.id)}">${esc(m.id)} (disponível ${nf(m.disponivel)} + reserva da equipe · ${esc(m.unidade)})</option>`).join('') || '<option value="">sem saldo no almoxarifado</option>'}</select><input type="number" step="any" min="0" data-qtd placeholder="quantidade">`;
  $('#ckMateriais').append(div);
});
fCk.addEventListener('submit', async ev => {
  ev.preventDefault(); const o = formObj(fCk), alvo = $('input[name=alvo_txt]', fCk);
  const corpo = { data: o.data, equipe_id: o.equipe_id, contingencia: o.contingencia || null,
    alvo_tipo: alvo.dataset.tipo || null, alvo_id: alvo.dataset.id || null,
    funcionarios: $$('#ckPresentes input[data-t=f]:checked').map(i => +i.value), maquinas: $$('#ckPresentes input[data-t=m]:checked').map(i => +i.value),
    materiais: $$('#ckMateriais .linha').map(l => ({ material_id: $('[data-mat]', l).value, quantidade: +$('[data-qtd]', l).value || 0 })).filter(m => m.material_id && m.quantidade > 0) };
  await acao(() => api('/api/checkin', corpo), `Check-in registrado — pin de programação da ${o.equipe_id} no mapa.`);
  $('#ckMateriais').innerHTML = ''; alvo.value = ''; carregarAlmox();
});
async function carregarCheckouts() {
  const cks = await api('/api/checkins');
  $('#checkoutLista').className = cks.length ? '' : 'vazio';
  $('#checkoutLista').innerHTML = cks.length ? cks.map(c => `<form class="form" data-co="${c.id}" style="border-bottom:1px solid var(--borda);padding-bottom:10px;margin-bottom:10px">
    <div><b>${esc(c.equipe_id)}</b> · ${esc(c.data)} · ${c.alvo_id ? '📍 ' + esc(curto(c.alvo_nome)) : esc(c.contingencia || '')}</div>
    ${c.materiais.length ? `<table><thead><tr><th>Material</th><th class="n">Com a equipe</th><th>Aplicado</th><th>Sobra (devolve)</th><th>Perda</th><th>Fica com a equipe</th><th>Motivo da perda</th></tr></thead><tbody>
      ${c.materiais.map(m => `<tr data-m="${esc(m.material_id)}"><td>${esc(m.material_id)}</td><td class="n">${nf(m.quantidade, 3)}${m.trazido ? `<br><small>trazido ${nf(m.trazido, 3)}</small>` : ''}</td>
      <td><input type="number" step="any" min="0" name="aplicado" value="${m.quantidade}"></td><td><input type="number" step="any" min="0" name="sobra" value="0"></td>
      <td><input type="number" step="any" min="0" name="perda" value="0"></td><td><input type="number" step="any" min="0" name="fica_com_equipe" value="0"></td><td><input name="motivo"></td></tr>`).join('')}</tbody></table>
      <p class="vazio" style="margin:4px 0">Aplicado + sobra + perda + fica com a equipe = material com a equipe. O que fica volta no próximo check-in.</p>` : '<span class="vazio">Sem materiais em custódia.</span>'}
    <div class="acoes"><button class="btn ok">Confirmar check-out com o encarregado</button></div></form>`).join('') : 'Nenhum check-in aberto.';
}
$('#checkoutLista').addEventListener('submit', async ev => {
  ev.preventDefault(); const f = ev.target;
  const itens = $$('tr[data-m]', f).map(tr => ({ material_id: tr.dataset.m, aplicado: +$('[name=aplicado]', tr).value || 0, sobra: +$('[name=sobra]', tr).value || 0, perda: +$('[name=perda]', tr).value || 0, fica_com_equipe: +$('[name=fica_com_equipe]', tr).value || 0, motivo: $('[name=motivo]', tr).value }));
  await acao(() => api('/api/checkout', { checkin_id: f.dataset.co, itens }), 'Check-out confirmado.'); carregarAlmox();
});
async function carregarHistograma() {
  const h = await api(`/api/histograma?ini=${$('#hIni').value}&fim=${$('#hFim').value}`);
  const mx = Math.max(1, ...h.map(x => x.funcionarios + x.maquinas));
  $('#histograma').innerHTML = h.length ? `<table><thead><tr><th>Data</th><th>Equipe</th><th>Pessoas</th><th>Máquinas</th></tr></thead><tbody>${h.map(x => `<tr><td>${esc(x.data)}</td><td>${esc(x.equipe_id)}</td>
    <td>${x.funcionarios} <div class="barra" style="width:${x.funcionarios / mx * 100}%"></div></td><td>${x.maquinas} <div class="barra maq" style="width:${x.maquinas / mx * 100}%"></div></td></tr>`).join('')}</tbody></table>` : '<span class="vazio">Sem check-ins no período.</span>';
}
$('#hIni').addEventListener('change', carregarHistograma);
$('#hFim').addEventListener('change', carregarHistograma);

/* ---------------------------------------------------------------- 3. lançamento de campo & fotos */
const fAp = $('#fApont');
ligarBusca($('input[name=alvo_txt]', fAp), r => selecionarCampo(r.tipo, r.id));
let CAMPO = null;
async function selecionarCampo(tipo, id) {
  const d = await acao(() => api(`/api/detalhe?tipo=${tipo}&id=${encodeURIComponent(id)}`));
  CAMPO = { tipo, id, d };
  $('#apMetros').style.display = tipo === 'TRECHO' ? '' : 'none';
  const ex = d.execucao, iv = d.intervalos;
  const faixa = l => l.length ? l.map(([a, b]) => `${nf(a)}–${nf(b)}`).join(', ') : '—';
  $('#apAlvo').innerHTML = tipo === 'TRECHO'
    ? `<div class="aviso info">${esc(curto(d.nome))}: ${nf(d.extensao_m)} m · DE${d.de_mm} · ${esc(d.metodologia)}${d.perfil_bloqueado ? ' · <b>perfil bloqueado (E06)</b>' : ''}
        <table style="margin-top:6px"><thead><tr><th>Etapa</th><th class="n">Metros</th><th>Feito (m)</th><th>Lacunas (m)</th></tr></thead><tbody>
        ${Object.entries(iv.etapas).map(([e, v]) => `<tr><td>${esc(e)}</td><td class="n">${nf(v.metros)}</td><td>${faixa(v.cobertura)}</td><td>${faixa(v.lacunas)}</td></tr>`).join('')}</tbody></table>
        ${iv.intervalos.filter(i => !i.verificado_em).map(i => `<div style="margin-top:4px"><small>${esc(i.etapa)} ${nf(i.ini_m)}–${nf(i.fim_m)} m · ${esc(i.data)} · ${esc(i.origem)}${i.informado_por ? ' · ' + esc(i.informado_por) : ''}</small> <button type="button" class="btn" data-verificar-intervalo="${i.id}">Verificar</button></div>`).join('')}</div>
      ${iv.alertas.map(a => `<div class="aviso problema">${esc(a)}</div>`).join('')}
      ${iv.legado ? `<div class="form" id="fLegado" style="border:1px dashed var(--borda);padding:8px">
        <b>Conciliar avanço anterior sem posição</b> — ${nf(iv.legado.ASSENTADO)} m assentados${d.mnd ? '' : ` e ${nf(iv.legado.REATERRADO)} m reaterrados`}
        (apontamentos de ${esc([...new Set(iv.legado.apontamentos.map(a => a.data))].join(', '))}). Informe onde esses metros estão; a soma precisa ser igual. Não gera quantidades novas.
        <div class="linha"><label>Assentado de (m)<input name="la_ini" type="number" step="any" min="0"></label><label>até<input name="la_fim" type="number" step="any" min="0"></label></div>
        ${d.mnd ? '' : '<div class="linha"><label>Reaterrado de (m)<input name="lr_ini" type="number" step="any" min="0"></label><label>até<input name="lr_fim" type="number" step="any" min="0"></label></div>'}
        <div class="linha"><label>Como a posição foi confirmada<input name="motivo"></label><label>Responsável<input name="responsavel"></label></div>
        <div class="acoes"><button type="button" class="btn prim" id="legadoBtn">Conciliar</button></div></div>` : ''}`
    : `<div class="aviso info">${esc(curto(d.nome))}: ${esc(d.texto)}</div>`;
  renderSoldas();
  $('#apQuant').innerHTML = '';
  renderFotos();
  const fl = $('#fLegado');   // bloco dentro do formulário de apontamento: não pode ser <form> aninhado
  if (fl) $('#legadoBtn').addEventListener('click', async () => {
    const o = Object.fromEntries($$('input', fl).map(i => [i.name, i.value]));
    const intervalos = [['ASSENTADO', 'la'], ['REATERRADO', 'lr']].filter(([, k]) => o[k + '_ini'] && o[k + '_fim'])
      .map(([etapa, k]) => ({ etapa, ini_m: +o[k + '_ini'], fim_m: +o[k + '_fim'] }));
    await acao(() => api('/api/legado/conciliar', { trecho_id: CAMPO.id, intervalos, motivo: o.motivo, responsavel: o.responsavel }), 'Avanço anterior conciliado (sem quantidades novas).');
    selecionarCampo(CAMPO.tipo, CAMPO.id);
  });
}
function renderFotos() {
  if (!CAMPO) return;
  const { d } = CAMPO;
  $('#fotoPend').className = '';
  $('#fotoPend').innerHTML = d.fotos_faltando.length ? 'Faltam: ' + d.fotos_faltando.map(c => `<span class="chip vermelho">${c}</span>`).join(' ')
    + (CAMPO.tipo !== 'TRECHO' && !d.fotos_faltando.includes('SINALIZACAO') ? ' <small>(sinalização herdada do trecho da área)</small>' : '')
    : '<span class="chip verde">Fotos obrigatórias completas</span>';
  $('#fotoLista').innerHTML = d.fotos.map(f => `<figure class="foto-carimbo"><img src="/fotos/${encodeURIComponent(f.arquivo)}" alt="${esc(f.categoria)}"><span class="carimbo">${esc(f.carimbo)}</span>
    <figcaption>${esc(f.categoria)} · ${esc(f.data_hora)} <small>(data: ${esc(f.origem_data || '—')}${f.origem_gps ? ' · GPS: ' + esc(f.origem_gps) : ''}${f.sha256 ? ' · sha256 ' + esc(f.sha256.slice(0, 12)) + '…' : ''})</small></figcaption></figure>`).join('');
}
$('#apPrevisto').addEventListener('click', async () => {
  if (!CAMPO) return toast('Selecione o trecho/nó.', 'erro');
  const o = formObj(fAp);
  let metros = Math.max(0, (+o.ass_fim || 0) - (+o.ass_ini || 0));
  if (CAMPO.tipo === 'TRECHO' && o.concluido_100) metros = CAMPO.d.extensao_m - (CAMPO.d.execucao ? CAMPO.d.execucao.metros_executados : 0);
  const prev = await acao(() => api(`/api/previsto?tipo=${CAMPO.tipo}&id=${encodeURIComponent(CAMPO.id)}&metros=${metros}`));
  $('#apQuant').innerHTML = `<div class="tabela" style="max-height:340px"><table><thead><tr><th>Serviço / peça</th><th>Unid.</th><th class="n">Previsto</th><th style="width:120px">Confirmado</th></tr></thead><tbody>
    ${prev.map(q => q.estimativa ? `<tr><td>${esc(q.servico)}</td><td>${esc(q.unidade)}</td><td class="n">${nf(q.previsto, 3)}</td><td><small>estimativa — registre no controle de soldas</small></td></tr>`
      : `<tr><td>${esc(q.servico)}</td><td>${esc(q.unidade)}</td><td class="n">${nf(q.previsto, 3)}</td><td><input type="number" step="any" min="0" value="${q.previsto}" data-s="${esc(q.servico)}" data-u="${esc(q.unidade)}" data-p="${q.previsto}"></td></tr>`).join('') || '<tr><td colspan="4" class="vazio">Sem quantidades (apenas avanço).</td></tr>'}</tbody></table></div>
    <div class="acoes" style="margin-top:10px"><button type="button" class="btn ok" id="apOk">[✅ OK, Confirmar Previsto]</button><button type="button" class="btn" id="apEdit">Salvar com as quantidades editadas</button></div>`;
  $('#apOk').onclick = () => enviarApontamento(false).catch(() => null);      // recusa já exibida no aviso
  $('#apEdit').onclick = () => enviarApontamento(true).catch(() => null);
});
async function enviarApontamento(editado) {
  const o = formObj(fAp);
  await acao(() => api('/api/clima', { data: o.data, equipe_id: o.equipe_id, MANHA: o.MANHA, TARDE: o.TARDE }));
  const quantidades = editado ? $$('#apQuant input[data-s]').filter(i => +i.value !== +i.dataset.p).map(i => ({ servico: i.dataset.s, unidade: i.dataset.u, confirmado: +i.value })) : null;
  const intervalos = [['ASSENTADO', 'ass'], ['CADASTRO_CAMPO', 'cad'], ['REATERRADO', 'rea']]
    .filter(([, k]) => o[k + '_ini'] !== '' && o[k + '_fim'] !== '' && o[k + '_ini'] != null)
    .map(([etapa, k]) => ({ etapa, ini_m: +o[k + '_ini'], fim_m: +o[k + '_fim'] }));
  await acao(() => api('/api/apontamento', { data: o.data, equipe_id: o.equipe_id, alvo_tipo: CAMPO.tipo, alvo_id: CAMPO.id,
    concluido_100: !!o.concluido_100, intervalos: o.concluido_100 ? null : intervalos, informado_por: o.informado_por,
    estaca_ini: o.estaca_ini, estaca_fim: o.estaca_fim, quantidades }), 'Apontamento registrado.');
  $('#apQuant').innerHTML = ''; ['ass', 'cad', 'rea'].forEach(k => { $(`input[name=${k}_ini]`, fAp).value = ''; $(`input[name=${k}_fim]`, fAp).value = ''; });
  $('input[name=concluido_100]', fAp).checked = false;
  selecionarCampo(CAMPO.tipo, CAMPO.id);
}

document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-verificar-intervalo]'); if (!b) return;
  const quem = prompt('Verificado por (não pode ser quem informou):'); if (!quem) return;
  await acao(() => api('/api/intervalo/verificar', { intervalo_id: b.dataset.verificarIntervalo, verificado_por: quem }), 'Intervalo verificado.');
  selecionarCampo(CAMPO.tipo, CAMPO.id);
});
function renderSoldas() {
  if (!CAMPO || !$('#soldas')) return;
  const s = CAMPO.d.soldas;
  $('#soldas').innerHTML = `<p style="margin:4px 0">${s.estimativa_barras_6m != null ? `Estimativa ⌈L/6⌉: <b>${s.estimativa_barras_6m}</b> (só referência) · ` : ''}Informadas <b>${s.informadas}</b> · aprovadas ${s.aprovadas} · reprovadas ${s.reprovadas} · sem verificação ${s.sem_verificacao}</p>
    ${s.registros.map(r => `<div><small>${esc(r.data)} · ${r.quantidade} ${esc(r.tipo)}${r.posicao_m != null ? ' @ ' + nf(r.posicao_m) + ' m' : ''} · ${esc(r.soldador)} · inf. ${esc(r.informado_por)}</small>
      ${r.verificado_em ? `<span class="chip ${r.resultado === 'APROVADA' ? 'verde' : 'vermelho'}">${esc(r.resultado)} · ${esc(r.verificado_por)}</span>` : `<button type="button" class="btn" data-verificar-solda="${r.id}">Verificar</button>`}</div>`).join('')}`;
}
$('#fSolda').addEventListener('submit', async ev => {
  ev.preventDefault(); if (!CAMPO) return toast('Selecione o trecho/nó no apontamento.', 'erro');
  const o = formObj(ev.target), d = formObj(fAp);
  await acao(() => api('/api/solda', { ...o, data: d.data || hoje(), equipe_id: d.equipe_id || null, alvo_tipo: CAMPO.tipo, alvo_id: CAMPO.id }), 'Soldas registradas (aguardam verificação).');
  ev.target.reset(); selecionarCampo(CAMPO.tipo, CAMPO.id);
});
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-verificar-solda]'); if (!b) return;
  const quem = prompt('Verificado por (não pode ser o soldador nem quem informou):'); if (!quem) return;
  const ok = confirm('Soldas APROVADAS? (Cancelar = reprovadas)');
  const obs = ok ? null : prompt('Motivo da reprovação:');
  await acao(() => api('/api/solda/verificar', { solda_id: b.dataset.verificarSolda, verificado_por: quem, resultado: ok ? 'APROVADA' : 'REPROVADA', obs }), 'Verificação registrada.');
  selecionarCampo(CAMPO.tipo, CAMPO.id);
});

// fotos: arquivo ORIGINAL (sem recompressão nem carimbo gravado) + data do aparelho + GPS do navegador
function gps() {   // nunca bloqueia o envio: sem resposta em 10 s (inclusive permissão pendente) segue sem GPS
  return new Promise(res => { if (!navigator.geolocation) return res(null);
    const t = setTimeout(() => res(null), 10000);
    navigator.geolocation.getCurrentPosition(p => { clearTimeout(t); res({ lat: p.coords.latitude, lon: p.coords.longitude }); },
      () => { clearTimeout(t); res(null); }, { timeout: 8000, enableHighAccuracy: true }); });
}
function lerOriginal(arquivo) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(',')[1]);
    r.onerror = () => rej(new Error('Não foi possível ler o arquivo.'));
    r.readAsDataURL(arquivo);
  });
}
$('#fFoto').addEventListener('submit', async ev => {
  ev.preventDefault();
  if (!CAMPO) return toast('Selecione o trecho/nó no apontamento.', 'erro');
  const f = ev.target, arq = f.arquivo.files[0], cat = f.categoria.value;
  const pos = await gps(), quando = new Date(arq.lastModified || Date.now()), dh = new Date(quando - quando.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
  const b64 = await lerOriginal(arq);
  await acao(() => api('/api/foto', { alvo_tipo: CAMPO.tipo, alvo_id: CAMPO.id, categoria: cat, conteudo_b64: b64, data_hora: dh, lat: pos && pos.lat, lon: pos && pos.lon }), 'Foto original enviada (hash registrado).').catch(() => null);
  f.reset(); selecionarCampo(CAMPO.tipo, CAMPO.id);
});

/* ---------------------------------------------------------------- 4. esteira de cadastro */
const CAMPOS_ETAPA = {
  '1_PRONTO': [['2_ENVIADO', 'Enviar dados p/ empresa', [['empresa', 'Empresa'], ['data_envio', 'Data', 'date']]]],
  '2_ENVIADO': [['3_RECEBIDO', 'Cadastro recebido', [['arquivos', 'Arquivos DWG/PDF/BIM']]]],
  '3_RECEBIDO': [['4_GDOC_ANALISE', 'Catalogar no GDOC', [['protocolo_gdoc', 'Nº protocolo GDOC']]]],
  '4_GDOC_ANALISE': [['6_APROVADO', 'Aprovado', [['memorando_eset', 'Memorando ESET']]], ['5A_NEGADO', 'Negado', [['motivo_negativa', 'Motivo da negativa']]]],
  '5A_NEGADO': [['2_ENVIADO', 'Reenviar p/ empresa ajustar', []]],
};
async function carregarEsteira() {
  if (!RESUMO) RESUMO = await api('/api/resumo');
  const lst = await api('/api/esteira');
  $('#kanban').innerHTML = Object.entries(RESUMO.etapas).map(([k, nome]) => {
    const cs = lst.filter(c => c.etapa === k);
    return `<div class="coluna"><h4><span>${esc(nome)}</span><span class="chip">${cs.length}</span></h4>${cs.map(c => `<div class="cartao"><b>${esc(curto(c.ponto))}</b>
      ${esc(c.frente_id)} · ${nf(c.extensao_m)} m ${c.revisao ? `<span class="chip laranja">Rev. ${c.revisao}</span>` : ''}
      ${c.empresa ? `<div>Empresa: ${esc(c.empresa)}</div>` : ''}${c.protocolo_gdoc ? `<div>GDOC: ${esc(c.protocolo_gdoc)}</div>` : ''}
      ${c.motivo_negativa ? `<div class="aviso problema">${esc(c.motivo_negativa)}</div>` : ''}${c.memorando_eset ? `<div>ESET: ${esc(c.memorando_eset)}</div>` : ''}
      ${(CAMPOS_ETAPA[k] || []).map(([dest, rot, campos]) => `<form class="form" data-tr="${esc(c.trecho_id)}" data-dest="${dest}">
        ${campos.map(([n, l, t]) => `<input name="${n}" placeholder="${l}" ${t ? `type="${t}"` : ''} required>`).join('')}
        <button class="btn ${dest === '5A_NEGADO' ? '' : 'prim'}">${rot}</button></form>`).join('')}</div>`).join('') || '<div class="vazio">—</div>'}</div>`;
  }).join('');
}
$('#kanban').addEventListener('submit', async ev => {
  ev.preventDefault(); const f = ev.target, dados = formObj(f);
  if (dados.arquivos) dados.arquivos = dados.arquivos.split(/[;,]/).map(s => s.trim()).filter(Boolean);
  await acao(() => api('/api/cadastro', { trecho_id: f.dataset.tr, destino: f.dataset.dest, dados, data: hoje() }), 'Esteira atualizada.');
  carregarEsteira();
});

/* ---------------------------------------------------------------- 5. medição */
async function carregarMedicoes() {
  const ms = await api('/api/medicoes');
  const sel = $('#medSel'), atual = sel.value;
  sel.innerHTML = ms.map(m => `<option value="${m.id}">${m.numero}ª — ${m.periodo_ini} a ${m.periodo_fim} (${m.status})</option>`).join('');
  if (ms.length) {
    sel.value = atual && ms.some(m => String(m.id) === atual) ? atual : ms.find(m => m.status === 'ABERTA')?.id ?? ms[ms.length - 1].id;
    const f = $('#fMed'), ult = ms[ms.length - 1], ini = new Date(ult.periodo_fim + 'T12:00:00');
    ini.setDate(ini.getDate() + 1);
    const fim = new Date(ini.getFullYear(), ini.getMonth() + 1, 0, 12), iso = d => d.toISOString().slice(0, 10);
    f.numero.value = ult.numero + 1; f.periodo_ini.value = iso(ini); f.periodo_fim.value = iso(fim);
    carregarMedicao();
  }
}
$('#medSel').addEventListener('change', carregarMedicao);
async function carregarMedicao() {
  const id = $('#medSel').value; if (!id) return;
  MEDICAO_ATUAL = +id;
  const r = await api('/api/medicao?id=' + id);
  $('#medExport').href = '/api/medicao/exportar?id=' + id;
  $('#medFechar').disabled = r.medicao.status !== 'ABERTA';
  $('#medResumo').className = '';
  $('#medResumo').innerHTML = (r.teste ? `<div class="aviso problema"><b>MEDIÇÃO DE TESTE — NÃO OFICIAL.</b> Regras financeiras, controle de acesso e exportação no modelo oficial (01ª MC) ainda não validados.</div>` : '')
    + ((r.hipoteses || []).length ? `<div class="aviso info"><b>Simulação com hipóteses não validadas:</b><ul style="margin:4px 0 0 18px">${r.hipoteses.map(h => `<li>${esc(h)}</li>`).join('')}</ul></div>` : '')
    + (r.congelada ? `<div class="aviso info"><b>Medição fechada — valores congelados no fechamento.</b>${r.alerta_recalculo ? ' ' + esc(r.alerta_recalculo) : ''}</div>` : '') + `<div class="kpis">${Object.entries(r.gavetas).map(([g, d]) => `<div class="kpi"><span>Gaveta ${g} — ${esc(d.nome)}</span><b>${brl(d.valor)}</b></div>`).join('')}</div>
    <table style="max-width:560px;margin-bottom:12px">
      <tr><td>Σ material / Σ serviço (ROUND por item, s/ BDI)</td><td class="n">${brl(r.totalizacao.material)} / ${brl(r.totalizacao.servico)}</td></tr>
      <tr><td>Subtotal P0 = (Σ + BDI por classe) × (1 + K)</td><td class="n">${brl(r.valor_pi)}</td></tr>
      <tr><td>(−) Excedente sobre teto de subgrupo <small>(hipótese — controle proposto)</small></td><td class="n">${brl(-r.excedente_teto)}</td></tr>
      <tr><td>Reajuste ${r.indice_reajuste != null ? nf(r.indice_reajuste * 100) + ' %' : ''} <small>(simulado)</small></td><td class="n">${brl(r.valor_reajuste)}</td></tr>
      <tr class="destaque"><td><b>Total da medição</b></td><td class="n"><b>${brl(r.valor_total)}</b></td></tr></table>
    ${r.aviso_reajuste ? `<div class="aviso problema">${esc(r.aviso_reajuste)}</div>` : ''}
    ${r.pendentes ? `<div class="aviso info"><b>${r.pendentes}</b> lançamento(s) PENDENTE(S) — fora do valor até haver item/regra com fonte (não é R$ 0 contratual).</div>` : ''}
    <div class="tabela"><table><thead><tr><th>Gav.</th><th>Trecho / atividade / NF</th><th>Serviço</th><th>Item BM</th><th class="n">Quant.</th><th>Unid.</th><th>Status</th></tr></thead><tbody>
    ${Object.entries(r.gavetas).flatMap(([g, d]) => d.lancamentos.map(l => `<tr><td>${g}</td><td>${esc(curto(l.alvo_nome || ('NF ' + (l.nf_id || ''))))}</td><td>${esc(l.servico)}</td>
      <td>${l.item ? esc(l.item) : '<span class="chip vermelho">sem item</span>'}</td><td class="n">${nf(l.quantidade, 3)}</td><td>${esc(l.unidade)}</td><td>${l.status === 'PENDENTE' ? `<span class="chip vermelho" title="${esc(l.motivo || '')}">pendente</span> <small>${esc(l.motivo || '')}</small>` : '<span class="chip verde">proposto</span>'}</td></tr>`)).join('') || '<tr><td colspan="7" class="vazio">Nada lançado nesta medição.</td></tr>'}
    </tbody></table></div>`;
  $('#medTetos').className = r.tetos.length ? '' : 'vazio';
  $('#medTetos').innerHTML = r.tetos.length ? `<table><thead><tr><th>Subgrupo</th><th class="n">Teto</th><th class="n">Anterior</th><th class="n">Atual</th><th class="n">Excedente</th></tr></thead><tbody>
    ${r.tetos.map(t => `<tr><td>${esc(t.subgrupo)} ${esc(t.nome || '')}</td><td class="n">${brl(t.teto)}</td><td class="n">${brl(t.anterior)}</td><td class="n">${brl(t.atual)}</td><td class="n">${t.excedente ? `<span class="chip vermelho">${brl(t.excedente)}</span>` : '—'}</td></tr>`).join('')}</tbody></table>` : 'Sem lançamentos com item de BM.';
}
$('#fMed').addEventListener('submit', async ev => {
  ev.preventDefault(); await acao(() => api('/api/medicao', formObj(ev.target)), 'Medição aberta.'); carregarMedicoes();
});
$('#medFechar').addEventListener('click', async () => {
  if (!confirm('Fechar a medição? Nenhum lançamento novo poderá entrar nela.')) return;
  await acao(() => api('/api/medicao/fechar', { id: $('#medSel').value }), 'Medição fechada.'); carregarMedicoes();
});

/* ---------------------------------------------------------------- início */
(async function iniciar() {
  RESUMO = await api('/api/resumo');
  $$('.selEquipe').forEach(s => s.innerHTML = '<option value="">—</option>' + RESUMO.equipes.map(e => `<option value="${e.id}">${esc(e.nome)}</option>`).join(''));
  $$('.selClima').forEach(s => s.innerHTML = '<option value="">—</option>' + Object.entries(RESUMO.clima).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join(''));
  $('select[name=contingencia]').innerHTML += RESUMO.contingencias.map(c => `<option>${esc(c)}</option>`).join('');
  $$('input[type=date]').forEach(i => { if (!i.value && i.name !== 'periodo_ini' && i.name !== 'periodo_fim') i.value = hoje(); });
  const ms = await api('/api/medicoes'); const ab = ms.find(m => m.status === 'ABERTA'); if (ab) MEDICAO_ATUAL = ab.id;
  let aba = 'mapa'; try { aba = localStorage.getItem('aba') || 'mapa'; } catch (_) { /* sem storage */ }
  abrirAba(aba);
})();
