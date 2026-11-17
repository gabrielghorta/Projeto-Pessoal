'use strict';

const FISCAL = { medicao: null, aberta: false, prontas: [], respostas: [], pedido: 0 };
const FISCAL_STATUS = {
  AGUARDANDO: 'Aguardando resposta', ACEITA: 'Aceita', REDUZIDA: 'Aceita em parte', RECUSADA: 'Recusada',
  ALTERADA: 'Em correção', CANCELADA: 'Envio cancelado', PENDENTE: 'Pendente', NAO_ENVIADA: 'Ainda não enviada',
};
const FISCAL_ACAO = {
  ENVIADA: 'Enviou', REENVIADA: 'Reenviou', ACEITA: 'Aceitou', REDUZIDA: 'Aceitou em parte',
  RECUSADA: 'Recusou', REABERTA: 'Reabriu a resposta', CANCELADA: 'Cancelou o envio',
};
const fiscalQuery = () => new URLSearchParams(FISCAL.medicao ? { medicao: FISCAL.medicao } : {});
const fiscalVazio = texto => `<p class="vazio">${esc(texto)}</p>`;
const fiscalQtd = (q, u) => `${nf(q, 6)} ${esc(u || '')}`;
const fiscalLink = (url, nome) => `<a class="btn" href="${esc(url)}" target="_blank" rel="noopener">${esc(nome)}</a>`;

function fiscalContador(qtd) {
  const el = $('#fiscalContador');
  el.hidden = !qtd;
  el.textContent = qtd > 99 ? '99+' : String(qtd);
}
async function atualizarContadorFiscal() {
  if (!podeTela('fiscalizacao')) return;
  const r = await api('/api/fiscalizacao/resumo?contador=1');
  fiscalContador(r.contador);
}

function fiscalPainel(painel, emails) {
  const titulos = { enviado: 'Enviado', aguardando: 'Aguardando', aceito: 'Aceito', reduzido: 'Redução',
    recusado: 'Recusado', nao_enviado: 'Ainda não enviado', pendente: 'Pendente', alterado: 'Em correção' };
  $('#fiscalKpis').innerHTML = Object.entries(titulos).filter(([id]) => painel.totais[id]).map(([id, nome]) => {
    const t = painel.totais[id];
    return `<div class="kpi"><span>${nome} · ${nf(t.linhas, 0)} linha(s)</span><b>${brl(t.valor)}</b></div>`;
  }).join('');
  $('#fiscalItens').innerHTML = painel.itens.map(i => `<div class="fiscal-item">
    <div><b>${esc(i.item)}</b> <span>${esc(i.descricao || '')}</span></div>
    <div><span>Enviado</span><b>${fiscalQtd(i.enviado, i.unidade)}</b><small>${brl(i.valor_enviado)}</small></div>
    <div><span>Aceito</span><b>${fiscalQtd(i.aceito, i.unidade)}</b><small>${brl(i.valor_aceito)} · ${nf(i.percentual * 100, 1)}%</small></div>
    </div>`).join('') || fiscalVazio('Ainda não há linhas nesta medição.');
  const estados = { ENVIADO: 'Enviado', PENDENTE: 'Na fila', SEM_CONFIGURACAO: 'E-mail sem configuração',
    SEM_DESTINATARIO: 'E-mail sem destinatário', FALHOU: 'E-mail com falha' };
  $('#fiscalEmails').innerHTML = emails.length ? `<details class="painel">
    <summary>Avisos por e-mail</summary>
    <ul>${emails.map(e => `<li>${esc(estados[e.situacao] || e.situacao)} · ${esc(e.criado_em.replace('T', ' ').slice(0, 16))}</li>`).join('')}</ul>
    </details>` : '';
}

function fiscalEvidencias(l) {
  const e = l.evidencias || {};
  return `<dl class="fiscal-evidencias">
    ${e.o_que_foi_feito ? `<dt>Serviço</dt><dd>${esc(e.o_que_foi_feito)}</dd>` : ''}
    ${e.memoria_calculo ? `<dt>Memória de cálculo</dt><dd>${esc(e.memoria_calculo)}</dd>` : ''}
    ${e.justificativa_tecnica ? `<dt>Justificativa</dt><dd>${esc(e.justificativa_tecnica)}</dd>` : ''}
    </dl><div class="acoes fiscal-anexos">${(e.documentos || []).map(d => fiscalLink(d.url, d.nome || 'Evidência')).join('')}
    ${e.ficha ? `<button type="button" class="btn" data-fiscal-ficha="${esc(l.id)}">Ficha e evidências${e.fotos ? ` (${e.fotos} foto(s))` : ''}</button>` : ''}</div>`;
}

function fiscalFormulario(l, acao, rotulo, quantidade = false, opcional = false) {
  return `<details class="fiscal-formulario"><summary class="btn">${rotulo}</summary>
    <form data-fiscal-acao="${acao}" data-linha="${esc(l.id)}">
      ${quantidade ? `<label>Quantidade aceita neste envio (${esc(l.unidade)})<input name="quantidade" type="number" min="0.000001" max="${esc(l.quantidade_lote)}" step="any" required></label>` : ''}
      <label>${opcional ? 'Observação (opcional)' : 'Motivo'}<textarea name="motivo" rows="2" maxlength="4000" ${opcional ? '' : 'required'}></textarea></label>
      <button class="btn prim">${acao === 'reenviar' ? rotulo : 'Confirmar'}</button>
    </form></details>`;
}

function fiscalLinha(l, modo) {
  const aprovar = FISCAL.aberta && pode('fiscalizacao_responder') && l.situacao === 'AGUARDANDO';
  const enviar = FISCAL.aberta && pode('fiscalizacao_enviar');
  const selecionavel = (modo === 'prontas' && enviar) || (modo === 'aguardando' && aprovar);
  const qtd = modo === 'aguardando' ? l.quantidade_lote : l.quantidade;
  const saldo = l.quantidade_aceita > 0 && l.saldo > 0;
  const st = modo === 'prontas' ? '' : `<span class="chip ${l.situacao === 'ACEITA' ? 'verde' : 'amarelo'}">${esc(FISCAL_STATUS[l.situacao] || l.situacao)}</span>`;
  const alvo = l.alvo_tipo === 'TRECHO' || l.alvo_tipo === 'ATIVIDADE' ? nomeCompleto(l.alvo_nome) : l.alvo_nome;
  let acoes = '';
  if (modo === 'aguardando' && aprovar) {
    acoes = `<button type="button" class="btn prim" data-fiscal-aceitar="${esc(l.id)}">Aceitar</button>
      ${fiscalFormulario(l, 'REDUZIR', 'Aceitar menos', true)}${fiscalFormulario(l, 'RECUSAR', 'Recusar')}`;
  } else if (modo === 'aguardando' && enviar) {
    acoes = fiscalFormulario(l, 'cancelar', 'Cancelar envio');
  } else if (modo === 'retornos' && enviar && l.saldo > 0) {
    acoes = fiscalFormulario(l, 'reenviar', saldo ? 'Reenviar saldo' : 'Reenviar', false, true);
  } else if (modo === 'retornos' && FISCAL.aberta && pode('fiscalizacao_responder')
             && ['ACEITA', 'REDUZIDA', 'RECUSADA'].includes(l.situacao)) {
    acoes = fiscalFormulario(l, 'reabrir', 'Reabrir resposta');
  }
  return `<article class="fiscal-linha">
    <div class="fiscal-linha-cab">
      ${selecionavel ? `<label class="fiscal-selecao"><input type="checkbox" data-fiscal-selecao="${modo}" value="${esc(l.id)}"> <b>${esc(alvo)}</b></label>` : `<b>${esc(alvo)}</b>`}
      ${st}<span class="fiscal-quantidade">${fiscalQtd(qtd, l.unidade)} · ${brl(modo === 'aguardando' ? l.valor_lote : l.valor)}</span>
    </div>${modo === 'prontas' ? `<p class="vazio">${esc(l.item_bm || l.item || '')} · ${esc(l.descricao || l.servico)}</p>` : ''}
    ${l.quantidade_aceita ? `<p>Aceito <b>${fiscalQtd(l.quantidade_aceita, l.unidade)}</b>${saldo ? ` · Saldo ${fiscalQtd(l.saldo, l.unidade)}` : ''}</p>` : ''}
    ${l.motivo_fiscal || l.motivo ? `<p>${esc(l.motivo_fiscal || l.motivo)}</p>` : ''}
    ${fiscalEvidencias(l)}
    ${acoes ? `<div class="acoes fiscal-acoes">${acoes}</div>` : ''}</article>`;
}

function fiscalAgrupar(ls, modo, vazio) {
  const grupos = new Map();
  for (const l of ls) {
    const k = l.item || 'Fora do BM';
    if (!grupos.has(k)) grupos.set(k, []);
    grupos.get(k).push(l);
  }
  return [...grupos].map(([item, linhas]) => `<div class="fiscal-grupo">
    <h4>${esc(linhas[0].item_bm || item)} · ${esc(linhas[0].servico)}</h4>
    ${linhas[0].descricao ? `<details class="fiscal-descricao"><summary>Descrição do item</summary><p>${esc(linhas[0].descricao)}</p></details>` : ''}
    ${linhas.map(l => fiscalLinha(l, modo)).join('')}</div>`).join('') || fiscalVazio(vazio);
}

function fiscalSelecao(modo) {
  return $$('[data-fiscal-selecao="' + modo + '"]:checked').map(i => Number(i.value));
}
function fiscalAtualizarSelecao() {
  for (const [modo, id] of [['prontas', 'fiscalSelecionarProntas'], ['aguardando', 'fiscalSelecionarPendentes']]) {
    const todos = $$('[data-fiscal-selecao="' + modo + '"]'), n = todos.filter(i => i.checked).length;
    const el = $('#' + id);
    el.disabled = !todos.length;
    el.checked = n > 0 && n === todos.length;
    el.indeterminate = n > 0 && n < todos.length;
  }
  const ids = new Set(fiscalSelecao('prontas'));
  const total = FISCAL.prontas.filter(l => ids.has(l.id)).reduce((v, l) => v + l.valor, 0);
  $('#fiscalTotalSelecionado').textContent = `${brl(total)} selecionados`;
  $('#fiscalEnviar').disabled = !ids.size || !FISCAL.aberta;
  $('#fiscalAceitarSelecionadas').disabled = !fiscalSelecao('aguardando').length || !FISCAL.aberta;
}

async function carregarFiscalizacao() {
  const pedido = ++FISCAL.pedido;
  const r = await api('/api/fiscalizacao/resumo?' + fiscalQuery());
  if (pedido !== FISCAL.pedido || TELA !== 'fiscalizacao') return;
  fiscalContador(r.contador);
  const med = r.painel?.medicao;
  $('#fiscalVazio').hidden = !!med;
  $('.paginas-aba', $('#aba-fiscalizacao')).hidden = !med;
  if (!med) {
    $('#fiscalVazio').textContent = 'Aguardando a abertura da medição pela Engenharia.';
    $$('[data-pagina]', $('#aba-fiscalizacao')).forEach(el => el.hidden = true);
    $('#fiscalMedicao').disabled = true;
    return;
  }
  FISCAL.medicao = med.id;
  FISCAL.aberta = med.status === 'ABERTA';
  $('#fiscalMedicao').disabled = false;
  $('#fiscalMedicao').innerHTML = r.medicoes.map(m => `<option value="${m.id}">
    ${m.numero}ª medição · ${dataBR(m.periodo_ini)} a ${dataBR(m.periodo_fim)}</option>`).join('');
  $('#fiscalMedicao').value = med.id;
  $('#fiscalEstado').className = 'chip ' + (FISCAL.aberta ? 'azul' : 'cinza');
  $('#fiscalEstado').textContent = FISCAL.aberta ? 'Aberta' : 'Fechada';
  const pagina = PAGINA.fiscalizacao;
  if (pagina === 'painel') return fiscalPainel(r.painel, r.emails || []);
  const q = fiscalQuery();
  if (pagina === 'pronto') {
    const lista = await api('/api/fiscalizacao/pronto?' + q);
    if (pedido !== FISCAL.pedido || TELA !== 'fiscalizacao') return;
    FISCAL.prontas = lista.prontas;
    $('#fiscalProntas').innerHTML = lista.prontas.map(l => fiscalLinha(l, 'prontas')).join('') || fiscalVazio('Nenhuma linha pronta para enviar.');
    $('#fiscalPendentes').innerHTML = lista.pendentes.map(l => `<div class="fiscal-linha"><b>${esc(l.alvo_nome)}</b><small>${esc(l.descricao || l.servico)}</small><p>${esc(l.motivo)}</p></div>`).join('') || fiscalVazio('Nenhuma pendência.');
  } else {
    q.set('situacao', pagina === 'aprovar' ? 'AGUARDANDO' : 'ACEITA,REDUZIDA,RECUSADA,ALTERADA,CANCELADA');
    const [ls, eventos] = await Promise.all([api('/api/fiscalizacao/linhas?' + q),
      pagina === 'historico' ? api('/api/fiscalizacao/historico?' + fiscalQuery()) : Promise.resolve([])]);
    if (pedido !== FISCAL.pedido || TELA !== 'fiscalizacao') return;
    FISCAL.respostas = ls;
    if (pagina === 'aprovar') {
      $('#fiscalAprovarDescricao').textContent = pode('fiscalizacao_responder') ? 'Confira cada linha do boletim.' : 'Linhas aguardando resposta da Caesb.';
      $('#fiscalAceiteLote').hidden = !FISCAL.aberta || !pode('fiscalizacao_responder') || !ls.length;
      $('#fiscalAprovar').innerHTML = fiscalAgrupar(ls, 'aguardando', 'Nenhuma linha aguardando resposta.');
    } else {
      $('#fiscalRetornos').innerHTML = fiscalAgrupar(ls, 'retornos', 'Nenhuma resposta ou correção nesta medição.');
      $('#fiscalHistorico').innerHTML = eventos.map(e => `<li><b>${esc(e.nome)}</b> · ${esc(FISCAL_ACAO[e.acao] || e.acao)} · linha ${e.lancamento_id}
        ${e.quantidade != null ? `· ${nf(e.quantidade, 6)}` : ''}<small>${esc(e.perfil)} · ${esc(e.em.replace('T', ' ').slice(0, 16))}</small>
        ${e.motivo ? `<p>${esc(e.motivo)}</p>` : ''}</li>`).join('') || '<li>Nenhum evento ainda.</li>';
    }
  }
  fiscalAtualizarSelecao();
}

async function fiscalGravar(rota, dados, mensagem, alvo) {
  if (!FISCAL.aberta || alvo.disabled) return;
  alvo.disabled = true;
  try {
    if (await acao(() => api('/api/fiscalizacao/' + rota, dados), mensagem).catch(() => null)) {
      if (rota === 'enviar') $('#fiscalObs').value = '';
      await carregarFiscalizacao();
    }
  } finally {
    if (alvo.isConnected) alvo.disabled = false;
    fiscalAtualizarSelecao();
  }
}

$('#fiscalMedicao').addEventListener('change', ev => {
  FISCAL.medicao = Number(ev.target.value);
  carregarFiscalizacao().catch(e => toast(e.message, 'erro'));
});
for (const [id, modo] of [['fiscalSelecionarProntas', 'prontas'], ['fiscalSelecionarPendentes', 'aguardando']]) {
  $('#' + id).addEventListener('change', ev => {
    $$('[data-fiscal-selecao="' + modo + '"]').forEach(i => { i.checked = ev.target.checked; });
    fiscalAtualizarSelecao();
  });
}
$('#aba-fiscalizacao').addEventListener('change', ev => {
  if (ev.target.matches('[data-fiscal-selecao]')) fiscalAtualizarSelecao();
});
$('#fiscalEnviar').addEventListener('click', ev => fiscalGravar('enviar', {
  medicao_id: FISCAL.medicao, ids: fiscalSelecao('prontas'), obs: $('#fiscalObs').value,
}, 'Lote enviado à fiscalização.', ev.currentTarget));
$('#fiscalAceitarSelecionadas').addEventListener('click', ev => fiscalGravar('responder', {
  itens: fiscalSelecao('aguardando').map(id => ({ lancamento_id: id, acao: 'ACEITAR' })),
}, 'Linhas aceitas.', ev.currentTarget));
$('#aba-fiscalizacao').addEventListener('submit', ev => {
  const form = ev.target.closest('[data-fiscal-acao]');
  if (!form) return;
  ev.preventDefault();
  const o = new FormData(form), id = Number(form.dataset.linha), tipo = form.dataset.fiscalAcao;
  const motivo = o.get('motivo');
  const btn = $('button', form);
  if (tipo === 'REDUZIR' || tipo === 'RECUSAR') {
    fiscalGravar('responder', { itens: [{ lancamento_id: id, acao: tipo, quantidade: Number(o.get('quantidade')), motivo }] },
      'Resposta registrada.', btn);
  } else {
    fiscalGravar(tipo, { lancamento_id: id, motivo, obs: motivo }, 'Alteração registrada.', btn);
  }
});
$('#aba-fiscalizacao').addEventListener('click', ev => {
  const botao = ev.target.closest('[data-fiscal-aceitar]');
  if (botao) fiscalGravar('responder', { itens: [{ lancamento_id: Number(botao.dataset.fiscalAceitar), acao: 'ACEITAR' }] }, 'Linha aceita.', botao);
  const btnFicha = ev.target.closest('[data-fiscal-ficha]');
  if (btnFicha) {
    const l = [...FISCAL.prontas, ...FISCAL.respostas].find(l => l.id === Number(btnFicha.dataset.fiscalFicha));
    if (l) abrirFichaFiscal(l.alvo_tipo, l.alvo_id).catch(e => toast(e.message, 'erro'));
  }
});

async function abrirFichaFiscal(tipo, id) {
  const d = await api('/api/fiscalizacao/ficha?' + new URLSearchParams({ tipo, id }));
  const n = d.nome || d.id;
  const intervalos = d.intervalos?.intervalos || [];
  const rotulosEtapa = { ASSENTADO: 'Assentamento', REATERRADO: 'Reaterro', CADASTRO_CAMPO: 'Cadastro de campo' };
  $('#fiscalFichaTitulo').textContent = nomeCompleto(n);
  $('#fiscalFichaConteudo').innerHTML = `<p>${esc([d.frente_id, d.pb, d.material, d.de_mm && `DE ${d.de_mm}`].filter(Boolean).join(' · '))}</p>
    <div class="acoes"><button class="btn" id="fiscalIrMapa" type="button">Ver no Mapa Iluminado</button></div>
    ${d.coordenadas ? `<details><summary>Coordenadas</summary><pre>${esc(JSON.stringify(d.coordenadas, null, 2))}</pre></details>` : ''}
    <h3>Verificação</h3>
    ${intervalos.map(i => `<p>${esc(rotulosEtapa[i.etapa] || i.etapa)} · ${nf(i.ini_m)} a ${nf(i.fim_m)} m · ${i.verificado_em ? 'Verificado' : 'Aguardando verificação'}</p>`).join('') || fiscalVazio('Nenhum intervalo de execução registrado.')}
    <h3>Notas de serviço</h3>
    ${(d.notas || []).map(nota => `<div class="fiscal-linha"><b>${esc(nota.referencia || nota.numero)} · ${dataBR(nota.data)}</b><div class="acoes">
      ${nota.arquivos.map(arq => fiscalLink(arq.url, arq.nome)).join('')}</div></div>`).join('') || fiscalVazio('Nenhuma nota vinculada.')}
    <h3>Fotos</h3><div class="fiscal-fotos">${(d.fotos || []).map(f => `<a href="/fotos/${encodeURIComponent(f.arquivo)}" target="_blank" rel="noopener">
      <img loading="lazy" src="/fotos/${encodeURIComponent(f.arquivo)}" alt="${esc(f.categoria || 'Foto da obra')}"><span>${esc(f.categoria || '')}</span></a>`).join('')}</div>`;
  $('#fiscalIrMapa').onclick = async () => {
    $('#fiscalFicha').close();
    await abrirAba('iluminado');
    await abrirFicha(d.alvo_tipo || tipo, n);
  };
  if (!$('#fiscalFicha').open) $('#fiscalFicha').showModal();
}
$('#fiscalFecharFicha').addEventListener('click', () => $('#fiscalFicha').close());
