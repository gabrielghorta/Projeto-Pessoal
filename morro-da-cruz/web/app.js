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

/* ---------------------------------------------------------------- visão integrada (detalhe do trecho e campo) */
const faixa = l => l && l.length ? l.map(([a, b]) => `${nf(a)}–${nf(b)}`).join(', ') : '—';
const NIVEL = { BLOQUEIO: 'vermelho', ALERTA: 'amarelo', PENDENTE: '' };
// "verificado" = conferência interna Ankara (azul), nunca verde de aprovação
const VERIF = { INFORMADO: ['informado, sem verificação', 'amarelo'], PARCIAL: ['verificação parcial', 'amarelo'],
  VERIFICADO: ['verificado — conferência interna', 'azul'], LEGADO_SEM_POSICAO: ['avanço legado sem posição', 'vermelho'] };
const FASE_STATUS = {
  NAO_INICIADO: ['não iniciado', 'vermelho'], PARCIAL: ['parcial', 'amarelo'], COMPLETO: ['completo (informado)', 'azul'],
  AGUARDA_OK_INTERNO: ['aguarda OK interno', ''], PRONTO_PARA_ENVIO: ['pronto p/ envio', 'amarelo'], EM_PRODUCAO: ['em produção na empresa', 'amarelo'], RECEBIDO: ['recebido', 'azul'],
  AGUARDA_ARQUIVOS: ['aguarda arquivos', ''], SEM_CONFERENCIA: ['sem conferência', 'amarelo'], CONFORME: ['conforme (interno)', 'azul'],
  NAO_CONFORME: ['não conforme (interno)', 'vermelho'], PROTOCOLADO_SEM_CONFERENCIA: ['protocolado sem conferência', 'amarelo'],
  NAO_PROTOCOLADO: ['não protocolado', ''], EM_ANALISE_CAESB: ['em análise na Caesb', 'amarelo'], NEGADO_CAESB: ['negado pela Caesb', 'vermelho'],
  APROVACAO_CAESB_REGISTRADA: ['aprovação Caesb registrada (memorando ESET)', 'verde'],
};
const chipVerif = v => v ? `<span class="chip ${VERIF[v][1]}">${VERIF[v][0]}</span>` : '';
function htmlEtapas(iv) {
  return `<table><thead><tr><th>Etapa</th><th class="n">Informado (m)</th><th class="n">Verificado (m)</th><th>Feito (m)</th><th>Lacunas (m)</th></tr></thead><tbody>
    ${Object.entries(iv.etapas).map(([e, v]) => `<tr><td>${esc(e)}</td><td class="n">${nf(v.metros)}</td><td class="n">${nf(v.verificado_m)}</td><td>${faixa(v.cobertura)}</td><td>${faixa(v.lacunas)}</td></tr>`).join('')}</tbody></table>`;
}
function htmlRegistros(iv, editavel) {
  return iv.registros.map(g => `<div class="registro"><div><b>${g.ref_tipo === 'CONCILIACAO' ? 'Conciliação do legado' : 'Apontamento'} #${g.ref_id}</b>
      ${editavel ? `<button type="button" class="btn" data-retificar-ref="${g.ref_tipo}|${g.ref_id}">Retificar</button>` : ''}</div>
    ${g.intervalos.map(i => `<div><small>${esc(i.etapa)} ${nf(i.ini_m)}–${nf(i.fim_m)} m · ${esc(i.data)} · ${esc(i.origem)}${i.informado_por ? ' · ' + esc(i.informado_por) : ''}${i.referencia ? ' · registro: ' + esc(i.referencia) : ''}</small>
      ${i.verificado_em ? `<span class="chip azul">verificado · ${esc(i.verificado_por)}</span>` : editavel ? `<button type="button" class="btn" data-verificar-intervalo="${i.id}">Verificar</button>` : '<span class="chip amarelo">sem verificação</span>'}</div>`).join('')}</div>`).join('')
    || '<div class="vazio">Nenhum intervalo registrado.</div>';
}
function htmlHistorico(iv) {
  if (!iv.retificacoes.length && !iv.anulados.length && !iv.conciliacoes.length) return '';
  return `<details><summary>Histórico: ${iv.conciliacoes.length} conciliação(ões), ${iv.retificacoes.length} retificação(ões), ${iv.anulados.length} intervalo(s) anulado(s)</summary>
    ${iv.conciliacoes.map(c => `<div><small>Conciliação #${c.id} · ${esc(String(c.em).slice(0, 10))} · ${esc(c.responsavel)} · ${nf(c.metros_assentado)} m assentados / ${nf(c.metros_reaterrado)} m reaterrados — ${esc(c.motivo)}</small></div>`).join('')}
    ${iv.retificacoes.map(r => `<div><small>Retificação #${r.id} · ${esc(String(r.em).slice(0, 10))} · ${esc(r.responsavel)} · ${r.ref_tipo === 'CONCILIACAO' ? 'conciliação' : 'apontamento'} #${r.ref_id}${r.novo_apontamento_id ? ' → apontamento #' + r.novo_apontamento_id : ''} — ${esc(r.motivo)}</small></div>`).join('')}
    ${iv.anulados.map(i => `<div style="opacity:.6;text-decoration:line-through"><small>${esc(i.etapa)} ${nf(i.ini_m)}–${nf(i.fim_m)} m · ${esc(i.data)} · ${esc(i.origem)}${i.verificado_por ? ' · verificado por ' + esc(i.verificado_por) : ''} (anulado pela retificação #${i.anulado_por})</small></div>`).join('')}</details>`;
}
const htmlPendencias = ps => ps && ps.length ? `<ul class="pend">${ps.map(p => `<li><span class="chip ${NIVEL[p.nivel]}">${esc(p.nivel.toLowerCase())}</span> <b>${esc(p.area)}:</b> ${esc(p.texto)}</li>`).join('')}</ul>`
  : '<div class="vazio">Sem pendências registradas.</div>';
const htmlFases = fs => (fs || []).map(f => `<div class="fase"><b>${esc(f.nome)}</b> <span class="chip ${(FASE_STATUS[f.status] || ['', ''])[1]}">${esc((FASE_STATUS[f.status] || [f.status])[0])}</span>
    ${f.evidencias.length ? `<ul>${f.evidencias.map(e => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}
    ${f.pendencias.length ? `<ul class="pendencias">${f.pendencias.map(e => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}</div>`).join('');
const FOTO_OK = v => v && !['INVALIDA', 'ARQUIVO_AUSENTE'].includes(v);
const ROT_ETAPA = { LIBERACAO_TOPOGRAFICA: 'Liberação topográfica', ESCAVADO: 'Escavado (vala aberta)' };
function htmlComplementar(c, editavel) {
  if (!c) return '';
  return `<table style="margin-top:4px"><thead><tr><th>Etapa</th><th class="n">Metros</th><th>Feito (m)</th></tr></thead><tbody>
    ${Object.keys(ROT_ETAPA).map(e => `<tr><td>${ROT_ETAPA[e]}</td><td class="n">${nf(c[e].metros)}</td><td>${faixa(c[e].cobertura)}</td></tr>`).join('')}</tbody></table>
    ${Object.keys(ROT_ETAPA).flatMap(e => c[e].registros).map(r => `<div><small>${esc(ROT_ETAPA[r.etapa])} ${nf(r.ini_m)}–${nf(r.fim_m)} m · ${esc(r.data)} · ${esc(r.registrado_por)}${r.referencia ? ' · ' + esc(r.referencia) : ''}</small>
      ${editavel ? `<button type="button" class="btn" data-anular-etapa="${r.id}">Anular</button>` : ''}</div>`).join('')}
    ${c.anulados.length ? `<details><summary>${c.anulados.length} registro(s) anulado(s)</summary>${c.anulados.map(r => `<div style="opacity:.6;text-decoration:line-through"><small>${esc(ROT_ETAPA[r.etapa])} ${nf(r.ini_m)}–${nf(r.fim_m)} m · ${esc(r.data)} — ${esc(r.anulado_motivo)} (${esc(r.anulado_por)})</small></div>`).join('')}</details>` : ''}`;
}
function htmlOcorrencias(os_, editavel) {
  return (os_ || []).map(o => `<div class="registro"><div><b>${o.tipo === 'IMPEDIMENTO' ? 'Impedimento' : 'Não conformidade'} #${o.id} · ${esc(o.categoria)}</b>
      ${o.resolvida_em ? '<span class="chip azul">resolvida</span>' : `<span class="chip amarelo">aberta</span>${editavel ? ` <button type="button" class="btn" data-resolver-ocorrencia="${o.id}">Resolver</button>` : ''}`}</div>
    <small>${esc(o.data)} · ${esc(o.aberta_por)}${o.equipe_id ? ' · ' + esc(o.equipe_id) : ''} — ${esc(o.descricao)}</small>
    ${o.resolvida_em ? `<div><small>Resolução (${esc(o.resolvida_por)}, ${esc(o.resolvida_em.slice(0, 10))}): ${esc(o.resolucao)}</small></div>` : ''}</div>`).join('')
    || '<div class="vazio">Nenhuma ocorrência.</div>';
}

let USUARIO = null, DEMONSTRACAO = false;
const EM_CURSO = new Map();
async function tratar(r) {
  const j = await r.json().catch(() => ({}));
  if (r.status === 401) { mostrarLogin(j.erro); throw new Error(j.erro || 'Entre com seu usuário.'); }
  if (!r.ok) throw new Error(j.erro || `Erro ${r.status}`);
  return j;
}
// Gravação: cabeçalho da aplicação (X-MC) e chave de reenvio (X-Idem). Clique repetido devolve a mesma
// requisição em curso; falha de rede reenvia com a MESMA chave e o servidor não executa duas vezes.
async function api(url, body) {
  if (body === undefined) return tratar(await fetch(url));
  const k = url + '|' + JSON.stringify(body);
  if (EM_CURSO.has(k)) return EM_CURSO.get(k);
  const idem = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const p = (async () => {
    for (let t = 0; ; t++) {
      let r;
      try { r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-MC': '1', 'X-Idem': idem }, body: JSON.stringify(body) }); }
      catch (e) { if (t < 2) { await new Promise(ok => setTimeout(ok, 800)); continue; } throw new Error('Sem conexão com o servidor.'); }
      return tratar(r);
    }
  })().finally(() => EM_CURSO.delete(k));
  EM_CURSO.set(k, p);
  return p;
}
const pode = perm => !!(USUARIO && USUARIO.permissoes.includes(perm));
function toast(msg, tipo = '') {
  const t = $('#toast'); t.textContent = msg; t.className = tipo; t.style.display = 'block';
  clearTimeout(toast.h); toast.h = setTimeout(() => t.style.display = 'none', tipo === 'erro' ? 7000 : 3500);
}
async function acao(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(okMsg, 'ok'); return r; } catch (e) { toast(e.message, 'erro'); e.exibido = true; throw e; }
}
// recusa já mostrada no aviso interrompe o restante do clique, sem virar erro não tratado
window.addEventListener('unhandledrejection', ev => { if (ev.reason && ev.reason.exibido) ev.preventDefault(); });
const formObj = f => Object.fromEntries(new FormData(f).entries());

/* ---------------------------------------------------------------- tema (escuro por padrão; o mapa REV02 acompanha) */
function aplicarTema(t) {
  document.documentElement.dataset.tema = t;
  $('#temaBtn').textContent = t === 'claro' ? '🌙 Tema escuro' : '☀️ Tema claro';
  try { localStorage.setItem('mc-tema', t); } catch (_) { /* sem storage */ }
  try { $('#mapaFrame').contentWindow.postMessage({ tipo: 'mc-tema', tema: t }, location.origin); } catch (_) { /* mapa ausente */ }
}
$('#temaBtn').addEventListener('click', () => aplicarTema(document.documentElement.dataset.tema === 'claro' ? 'escuro' : 'claro'));
aplicarTema(document.documentElement.dataset.tema === 'claro' ? 'claro' : 'escuro');

/* ---------------------------------------------------------------- abas */
$$('nav.abas button').forEach(b => b.addEventListener('click', () => abrirAba(b.dataset.aba)));
function abrirAba(id) {
  $$('nav.abas button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.aba === id)));
  $$('section.aba').forEach(s => s.classList.toggle('ativa', s.id === 'aba-' + id));
  try { localStorage.setItem('aba', id); } catch (_) { /* sem storage */ }
  ({ mapa: carregarMapa, prog: carregarProg, almox: carregarAlmox, compras: carregarCompras, campo: () => {}, esteira: carregarEsteira, medicao: carregarMedicoes, admin: carregarAdmin, relatorios: carregarRelatorios })[id]();
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
  const frente = $('#selFrente').value;
  const r = await api('/api/resumo' + (frente ? '?frente=' + encodeURIComponent(frente) : ''));
  if (!frente) RESUMO = { ...RESUMO, ...r };
  if ($('#selFrente').options.length < 2) $('#selFrente').innerHTML += r.frentes.map(f => `<option>${esc(f)}</option>`).join('');
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
  const leg = est.legado_sem_posicao || [];
  $('#painelLegado').hidden = !leg.length;
  $('#legadoLista').innerHTML = leg.map(l => `<div style="margin-bottom:6px"><button class="btn" data-fisc="TRECHO|${esc(l.alvo_id)}">${esc(curto(l.nome))}</button>
    <small>${nf(l.assentado_m)} m assentados / ${nf(l.reaterrado_m)} m reaterrados sem posição</small></div>`).join('');
  const ret = est.retirados_com_historico || [];
  $('#painelRetirados').hidden = !ret.length;
  $('#retirados').innerHTML = ret.map(r => `<div style="margin-bottom:6px"><button class="btn" data-fisc="${esc(r.alvo_tipo)}|${esc(r.alvo_id)}">${esc(curto(r.nome))}</button><br><small>histórico: ${esc((r.historico || []).join(', '))}${(r.situacoes || []).length ? ' · ' + esc(r.situacoes.join('; ')) : ''}</small></div>`).join('');
}
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-fisc]'); if (!b) return;
  const [t, id] = b.dataset.fisc.split('|'); mostrarFiscal(t, id);
});
ligarBusca($('#fiscBusca'), r => mostrarFiscal(r.tipo, r.id));
$('#selFrente').addEventListener('change', carregarMapa);
let FISCAL_ATUAL = null;
window.addEventListener('message', ev => {   // seleção vinda do mapa REV02 (camada mapa_iluminado.js)
  if (ev.origin !== location.origin || !ev.data || ev.data.tipo !== 'mc-selecao') return;
  const a = FISCAL_ATUAL;                   // eco da própria seleção (painel → mapa → painel): não redesenha
  if (a && [a.nome, a.id].includes(ev.data.alvo_id) && Date.now() - a.t < 4000) return;
  mostrarFiscal(ev.data.alvo_tipo, ev.data.alvo_id);
});

async function mostrarFiscal(tipo, id) {
  const d = await acao(() => api(`/api/detalhe?tipo=${tipo}&id=${encodeURIComponent(id)}`));
  FISCAL_ATUAL = { id: d.id, nome: d.nome, t: Date.now() };
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
  const podeOk = ex && ex.concluido && !st.length && !ex.ok_fiscal_em;
  $('#fiscDetalhe').className = '';
  $('#fiscDetalhe').innerHTML = `<h2 style="word-break:break-all">${esc(curto(d.nome))}</h2>
    ${d.retirado ? '<div class="aviso problema"><b>Retirado da revisão vigente do projeto.</b> Consulta do histórico; novos lançamentos bloqueados.</div>' : ''}
    <table>${linhas.map(([k, v]) => `<tr><th style="position:static;width:40%">${k}</th><td>${v}</td></tr>`).join('')}</table>
    ${bloqueio}${avisos}
    <h4 style="margin:12px 0 4px">Pendências</h4>${htmlPendencias(d.pendencias)}
    ${tipo === 'TRECHO' ? `<h4 style="margin:12px 0 4px">Execução — informado × verificado ${chipVerif(d.intervalos.verificacao)}</h4>${htmlEtapas(d.intervalos)}
      <details><summary>Intervalos por registro (${d.intervalos.intervalos.length})</summary>${htmlRegistros(d.intervalos, false)}</details>${htmlHistorico(d.intervalos)}` : ''}
    <p style="margin:8px 0">Soldas: ${d.soldas.estimativa_barras_6m != null ? `estimativa ⌈L/6⌉ ${d.soldas.estimativa_barras_6m} (referência) · ` : ''}informadas ${d.soldas.informadas} · aprovadas ${d.soldas.aprovadas} · reprovadas ${d.soldas.reprovadas} · sem verificação ${d.soldas.sem_verificacao}</p>
    <p>Fotos: ${st.length ? st.map(c => `<span class="chip vermelho">falta ${c}</span>`).join(' ') : '<span class="chip verde">completas</span>'}
       ${d.fotos.map(f => `<span class="chip ${FOTO_OK(f.validacao) ? '' : 'vermelho'}" title="${esc(f.validacao || 'não validada')}">${esc(f.categoria)}${FOTO_OK(f.validacao) ? '' : ' · não conta: ' + esc(f.validacao || 'não validada')}</span>`).join(' ')}
       ${ex && ex.ok_fiscal_em ? `<span class="chip verde">OK em ${esc(ex.ok_fiscal_em)} por ${esc(ex.ok_fiscal_por)}</span>` : ''}</p>
    ${tipo === 'TRECHO' ? `<h4 style="margin:12px 0 4px">Liberação topográfica e escavação</h4>${htmlComplementar(d.complementar, false)}` : ''}
    <h4 style="margin:12px 0 4px">Ocorrências (impedimentos e não conformidades)</h4>${htmlOcorrencias(d.ocorrencias, false)}
    ${tipo === 'TRECHO' ? `<h4 style="margin:12px 0 4px">Cadastro — do levantamento de campo à entrega</h4>${htmlFases(d.fases_cadastro)}` : ''}
    <h4 style="margin:12px 0 4px">Programação</h4>${(d.programacoes || []).map(p => `<div><small>${esc(p.data)} · ${esc(p.equipe_id)} · ${esc((RESUMO.servicos_programacao || {})[p.servico] || p.servico)}${p.ini_m != null ? ` ${nf(p.ini_m)}–${nf(p.fim_m)} m` : ''}</small> <span class="chip ${p.status === 'REALIZADA' ? 'azul' : p.status === 'PLANEJADA' ? 'amarelo' : ''}">${esc(p.status.toLowerCase())}</span>${p.motivo ? ` <small>${esc(p.motivo)}</small>` : ''}</div>`).join('') || '<div class="vazio">Sem programação.</div>'}
    <details id="histObj"><summary>Histórico de alterações (quem fez o quê)</summary><div class="vazio">carregando…</div></details>
    <label class="check" style="margin:8px 0"><input type="checkbox" id="okFiscal" ${ex && ex.ok_fiscal_em ? 'checked disabled' : podeOk ? '' : 'disabled'}>
      <b>[✓] OK Fiscalização — Pronto p/ Medir</b></label>
    ${!podeOk && !(ex && ex.ok_fiscal_em) ? '<div class="vazio">Exige 100 % reaterrado e as fotos obrigatórias.</div>' : ''}
    ${ex && ex.ok_fiscal_em && !ex.recomposicao_ok ? `<div class="form" style="margin-top:10px"><b>Recomposição (equipe de pavimento)</b>
      <div class="linha"><select id="recTipo"><option>CALÇADA</option><option>ASFALTO</option></select><input id="recQtd" type="number" step="any" placeholder="quantidade"></div>
      <button class="btn" id="recBtn">Lançar recomposição</button></div>` : ''}`;
  $('#histObj').addEventListener('toggle', async ev => {
    if (!ev.target.open || ev.target.dataset.ok) return;
    const ls = await api(`/api/auditoria?alvo_tipo=${tipo}&alvo_id=${encodeURIComponent(d.id)}&limite=60`).catch(() => []);
    ev.target.dataset.ok = '1';
    ev.target.innerHTML = '<summary>Histórico de alterações (quem fez o quê)</summary>' + (ls.map(a => `<div><small>${esc(a.em.replace('T', ' '))} · ${esc(a.login || '—')} · ${esc(a.rota.replace('/api/', ''))} · ${a.status === 200 ? 'aceito' : 'recusado ' + a.status}${a.status !== 200 && a.resultado ? ': ' + esc(a.resultado.slice(0, 120)) : ''}</small></div>`).join('') || '<div class="vazio">Nada registrado.</div>');
  });
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
    const corpo = { movimento_id: e.dataset.estornar, motivo };
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
    await acao(() => api('/api/retificar', { movimento_id: rt.dataset.retificar, destino, motivo }), 'Fechamento retificado (o lançamento original fica no histórico).');
    carregarAlmox();
  }
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

/* ---------------------------------------------------------------- 1.1 programação */
const fProg = $('#fProg');
ligarBusca($('input[name=alvo_txt]', fProg));
const maisDias = (d, n) => { const x = new Date(d + 'T12:00:00'); x.setDate(x.getDate() + n); return x.toISOString().slice(0, 10); };
async function carregarProg() {
  if (!MATERIAIS.length) MATERIAIS = await api('/api/estoque');
  if (!carregarProg.feito) { carregarProg.feito = true; $('#pgIni').value = hoje(); $('#pgFim').value = maisDias(hoje(), 7); fProg.data.value = maisDias(hoje(), 1); }
  if ($('#pgFrente').options.length < 2) $('#pgFrente').innerHTML += (RESUMO.frentes || []).map(f => `<option>${esc(f)}</option>`).join('');
  if (!$('#selServProg').options.length) $('#selServProg').innerHTML = Object.entries(RESUMO.servicos_programacao || {}).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join('');
  const e = $('.editor-itens[data-itens=prog]'); if (!e.children.length) e.innerHTML = LINHA_ITEM.prog();
  const q = new URLSearchParams({ ini: $('#pgIni').value, fim: $('#pgFim').value });
  if ($('#pgFrente').value) q.set('frente', $('#pgFrente').value);
  if ($('#pgEquipe').value) q.set('equipe', $('#pgEquipe').value);
  const r = await api('/api/programacoes?' + q);
  const c = r.resumo.contagem;
  $('#pgResumo').innerHTML = `<span class="chip amarelo">planejadas ${c.PLANEJADA}</span> <span class="chip azul">realizadas ${c.REALIZADA}</span> <span class="chip vermelho">não realizadas ${c.NAO_REALIZADA}</span> <span class="chip">canceladas ${c.CANCELADA}</span>
    ${r.resumo.programadas_no_passado ? ` · programado × realizado (dias passados): <b>${r.resumo.realizadas_no_passado}/${r.resumo.programadas_no_passado}</b>` : ''}`;
  $('#pgLista').innerHTML = r.programacoes.length ? `<table><thead><tr><th>Data</th><th>Equipe</th><th>Alvo</th><th>Serviço</th><th>Materiais previstos</th><th>Situação</th></tr></thead><tbody>${r.programacoes.map(p => `<tr>
    <td>${esc(p.data)}</td><td>${esc(p.equipe_id)}</td><td><button class="btn" data-fisc="${esc(p.alvo_tipo)}|${esc(p.alvo_id)}">${esc(curto(p.alvo_nome))}</button></td>
    <td>${esc(p.servico_nome)}${p.ini_m != null ? `<br><small>${nf(p.ini_m)}–${nf(p.fim_m)} m</small>` : ''}</td>
    <td>${p.materiais.map(m => `${esc(m.material_id)}: ${nf(m.quantidade, 3)}`).join('<br>') || '—'}</td>
    <td><span class="chip ${p.status === 'REALIZADA' ? 'azul' : p.status === 'PLANEJADA' ? 'amarelo' : p.status === 'NAO_REALIZADA' ? 'vermelho' : ''}">${esc(p.status.toLowerCase().replace('_', ' '))}</span>
      ${p.motivo ? `<br><small>${esc(p.motivo)}</small>` : ''}${p.status === 'PLANEJADA' && pode('planejar') ? `<br><button type="button" class="btn" data-prog-enc="${p.id}" data-st="NAO_REALIZADA">Não realizada</button> <button type="button" class="btn" data-prog-enc="${p.id}" data-st="CANCELADA">Cancelar</button>` : ''}</td></tr>`).join('')}</tbody></table>`
    : '<div class="vazio" style="padding:8px">Nada programado no período.</div>';
  $('#pgFaltantes').innerHTML = r.faltantes.length ? `<table><thead><tr><th>Material</th><th class="n">Previsto</th><th class="n">Reservado p/ a programação</th><th class="n">Disponível</th><th class="n">A receber (pedidos)</th><th class="n">Faltante</th></tr></thead><tbody>${r.faltantes.map(f => `<tr>
    <td>${esc(f.material_id)}<br><small>${esc(f.descricao.slice(0, 60))} (${esc(f.unidade)})</small></td><td class="n">${nf(f.previsto, 3)}</td><td class="n">${nf(f.reservado, 3)}</td><td class="n">${nf(f.disponivel, 3)}</td><td class="n">${nf(f.a_receber, 3)}</td>
    <td class="n">${f.faltante > 0 ? `<span class="chip vermelho">${nf(f.faltante, 3)}</span>` : '<span class="chip azul">0</span>'}</td></tr>`).join('')}</tbody></table>`
    : '<div class="vazio" style="padding:8px">Nenhum material previsto nas programações do período.</div>';
}
['#pgIni', '#pgFim', '#pgFrente', '#pgEquipe'].forEach(x => $(x).addEventListener('change', carregarProg));
fProg.addEventListener('submit', async ev => {
  ev.preventDefault(); const o = formObj(fProg), alvo = $('input[name=alvo_txt]', fProg);
  if (!alvo.dataset.id) return toast('Escolha o trecho/nó na lista da busca.', 'erro');
  const r = await acao(() => api('/api/programacao', { data: o.data, equipe_id: o.equipe_id, alvo_tipo: alvo.dataset.tipo, alvo_id: alvo.dataset.id, servico: o.servico,
    ini_m: o.ini_m, fim_m: o.fim_m, obs: o.obs, materiais: lerItens(fProg, 'prog') }), 'Programação registrada.').catch(() => null);
  if (r) { alvo.value = ''; alvo.dataset.id = ''; $('.editor-itens[data-itens=prog]').innerHTML = ''; carregarProg(); recarregarCamadaMapa(); }
});
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-prog-enc]'); if (!b) return;
  const motivo = prompt(b.dataset.st === 'CANCELADA' ? 'Motivo do cancelamento:' : 'Por que não foi realizada?'); if (!motivo) return;
  const r = await acao(() => api('/api/programacao/encerrar', { programacao_id: b.dataset.progEnc, status: b.dataset.st, motivo }), 'Programação encerrada.').catch(() => null);
  if (r) carregarProg();
});

/* ---------------------------------------------------------------- 2.1 compras & recebimento */
let COMPRAS = null;
const opMat = f => MATERIAIS.filter(f).map(m => `<option value="${esc(m.id)}">${esc(m.id)} — ${esc(m.descricao.slice(0, 48))} (${esc(m.unidade)})</option>`).join('');
const LINHA_ITEM = {
  solic: () => `<div class="linha lin-iv lin-item"><select data-k="material_id">${opMat(m => m.propriedade !== 'CAESB')}</select><input data-k="quantidade" type="number" step="any" min="0" placeholder="quantidade"><button type="button" class="btn" data-remover-linha>×</button></div>`,
  nfdig: () => `<div class="linha lin-iv lin-item"><input data-k="descricao" placeholder="descrição na nota"><input data-k="unidade" placeholder="unid." style="max-width:80px"><input data-k="quantidade" type="number" step="any" min="0" placeholder="qtd."><input data-k="valor_unitario" type="number" step="any" min="0" placeholder="valor unit."><button type="button" class="btn" data-remover-linha>×</button></div>`,
  inv: () => `<div class="linha lin-iv lin-item"><select data-k="material_id">${opMat(() => true)}</select><input data-k="contado" type="number" step="any" min="0" placeholder="contado"><button type="button" class="btn" data-remover-linha>×</button></div>`,
  prog: () => `<div class="linha lin-iv lin-item"><select data-k="material_id">${opMat(m => m.propriedade !== 'CONSUMO')}</select><input data-k="quantidade" type="number" step="any" min="0" placeholder="quantidade prevista"><button type="button" class="btn" data-remover-linha>×</button></div>`,
};
const lerItens = (raiz, tipo) => $$(`.editor-itens[data-itens=${tipo}] .lin-item`, raiz).map(l => Object.fromEntries($$('[data-k]', l).map(i => [i.dataset.k, i.value])))
  .filter(o => Object.values(o).some(v => v !== '') && (o.quantidade !== '' || o.contado !== ''));
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-mais-item]'); if (!b) return;
  $(`.editor-itens[data-itens=${b.dataset.maisItem}]`).insertAdjacentHTML('beforeend', LINHA_ITEM[b.dataset.maisItem]());
});
const STATUS_NF = { A_CONFERIR: ['a conferir', 'amarelo'], CONFERIDA: ['conferida — recebendo', 'azul'], ENCERRADA: ['encerrada', ''], CANCELADA: ['cancelada', 'vermelho'], QUARENTENA: ['quarentena (registro direto)', 'amarelo'], ACEITO: ['aceita (registro direto)', ''] };
async function carregarCompras() {
  MATERIAIS = await api('/api/estoque');
  COMPRAS = await api('/api/compras');
  const fs = COMPRAS.fornecedores.map(f => `<option value="${f.id}">${esc(f.nome)} · ${esc(f.cnpj)}</option>`).join('');
  $('#selForn').innerHTML = fs; $$('.selForn').forEach(x => x.innerHTML = fs);
  $$('.selMaterialTodos').forEach(x => x.innerHTML = opMat(() => true));
  ['solic', 'nfdig', 'inv'].forEach(t => { const e = $(`.editor-itens[data-itens=${t}]`); if (!e.children.length) e.innerHTML = LINHA_ITEM[t](); });
  const aprov = COMPRAS.solicitacoes.filter(x => x.status === 'APROVADA');
  $('#selSolicAprov').innerHTML = '<option value="">—</option>' + aprov.map(x => `<option value="${x.id}">#${x.id} · ${esc(x.motivo.slice(0, 40))}</option>`).join('');
  renderItensPedido();
  $('#solicLista').innerHTML = COMPRAS.solicitacoes.length ? `<table><thead><tr><th>#</th><th>Solicitante</th><th>Itens</th><th>Situação</th></tr></thead><tbody>${COMPRAS.solicitacoes.map(x => `<tr>
    <td>${x.id}<br><small>${esc(x.data)}</small></td><td>${esc(x.solicitante)}<br><small>${esc(x.motivo)}</small></td><td>${x.itens.map(i => `${esc(i.material_id)}: ${nf(i.quantidade, 3)}`).join('<br>')}</td>
    <td><span class="chip ${x.status === 'APROVADA' ? 'azul' : x.status === 'ABERTA' ? 'amarelo' : x.status === 'RECUSADA' ? 'vermelho' : ''}">${esc(x.status.toLowerCase())}</span>${x.decidida_por ? `<br><small>${esc(x.decidida_por)}${x.decisao_motivo ? ': ' + esc(x.decisao_motivo) : ''}</small>` : ''}
      ${x.status === 'ABERTA' && pode('compras_aprovar') && x.solicitante !== USUARIO.login ? `<br><button type="button" class="btn" data-solic="${x.id}" data-ap="1">Aprovar</button> <button type="button" class="btn" data-solic="${x.id}" data-ap="0">Recusar</button>` : ''}</td></tr>`).join('')}</tbody></table>` : '<div class="vazio">Nenhuma solicitação.</div>';
  $('#pedidosLista').innerHTML = COMPRAS.pedidos.length ? `<table><thead><tr><th>Pedido</th><th>Material</th><th class="n">Pedido</th><th class="n">Faturado</th><th class="n">Entregue</th><th class="n">Quarentena</th><th class="n">Aceito</th><th class="n">Recusado</th><th class="n">Devolvido</th><th class="n">Pendente</th></tr></thead><tbody>
    ${COMPRAS.pedidos.flatMap(p => p.itens.map((i, k) => `<tr>${k ? '<td></td>' : `<td rowspan="1"><b>${esc(p.numero)}</b> · ${esc(p.fornecedor)}<br><span class="chip ${p.status === 'EMITIDO' ? (p.atendido ? '' : 'azul') : ''}">${esc(p.status.toLowerCase())}${p.status === 'EMITIDO' && p.atendido ? ' · atendido' : ''}</span>
      ${p.status === 'EMITIDO' && pode('compras_pedir') ? ` <button type="button" class="btn" data-pedido-enc="${p.id}">Encerrar saldo</button>` : ''}</td>`}
      <td>${esc(i.material_id)}</td><td class="n">${nf(i.quantidade, 3)}</td><td class="n">${nf(i.faturado, 3)}</td><td class="n">${nf(i.entregue, 3)}</td><td class="n">${nf(i.quarentena, 3)}</td><td class="n">${nf(i.aceito, 3)}</td><td class="n">${nf(i.recusado, 3)}</td><td class="n">${nf(i.devolvido, 3)}</td><td class="n"><b>${nf(i.pendente_entrega, 3)}</b></td></tr>`)).join('')}</tbody></table>` : '<div class="vazio" style="padding:8px">Nenhum pedido.</div>';
  renderNotas();
  const invs = await api('/api/inventarios');
  $('#invLista').innerHTML = invs.map(v => `<div class="registro"><div><b>Inventário #${v.id} · ${esc(v.data)} · ${esc(v.contado_por)}</b> <span class="chip ${v.status === 'AJUSTADO' ? 'azul' : v.status === 'CONTADO' ? 'amarelo' : ''}">${esc(v.status.toLowerCase())}</span></div>
    ${v.itens.map(i => `<div><small>${esc(i.material_id)}: sistema ${nf(i.saldo_sistema, 3)} · contado ${nf(i.contado, 3)} · diferença <b>${nf(i.diferenca, 3)}</b></small></div>`).join('')}
    ${v.status === 'CONTADO' && pode('inventario_ajustar') && v.contado_por !== USUARIO.login ? `<button type="button" class="btn" data-inv="${v.id}" data-ap="1">Aprovar ajuste</button> <button type="button" class="btn" data-inv="${v.id}" data-ap="0">Descartar</button>` : ''}
    ${v.decidido_por ? `<div><small>${esc(v.decidido_por)}: ${esc(v.decisao_motivo || '')}</small></div>` : ''}</div>`).join('');
  const venc = await api('/api/reservas-vencidas?hoje=' + hoje());
  $('#vencidasLista').innerHTML = venc.length ? `${venc.map(r => `<label class="check"><input type="checkbox" data-venc="${r.id}" checked> #${r.id} · ${esc(r.data)} · ${esc(r.equipe_id)} · ${esc(r.material_id)} ${nf(r.quantidade, 3)}</label>`).join('')}
    <div class="linha"><input id="vencMotivo" placeholder="motivo (ex.: equipe não compareceu)"><button type="button" class="btn" id="vencBtn">Liberar selecionadas</button></div>` : '<div class="vazio">Nenhuma reserva vencida.</div>';
}
function renderItensPedido() {
  const sid = +$('#selSolicAprov').value, so = COMPRAS && COMPRAS.solicitacoes.find(x => x.id === sid);
  if (!so) { $('#pedidoItens').innerHTML = '<div class="vazio">Escolha a solicitação aprovada.</div>'; return; }
  const ja = {}; COMPRAS.pedidos.filter(p => p.solicitacao_id === sid && p.status !== 'CANCELADO').forEach(p => p.itens.forEach(i => ja[i.material_id] = (ja[i.material_id] || 0) + i.quantidade));
  $('#pedidoItens').innerHTML = so.itens.map(i => `<div class="linha lin-ped" data-m="${esc(i.material_id)}"><span>${esc(i.material_id)}<br><small>aprovado ${nf(i.quantidade, 3)} · já pedido ${nf(ja[i.material_id] || 0, 3)}</small></span>
    <input data-k="quantidade" type="number" step="any" min="0" value="${Math.max(0, i.quantidade - (ja[i.material_id] || 0))}"><input data-k="valor_unitario" type="number" step="any" min="0" placeholder="valor unit."></div>`).join('');
}
$('#selSolicAprov').addEventListener('change', renderItensPedido);
function renderNotas() {
  const pedidosDe = f => COMPRAS.pedidos.filter(p => p.status === 'EMITIDO' && p.fornecedor_id === f);
  $('#notasLista').innerHTML = COMPRAS.notas.filter(n => n.origem !== 'DIRETA').map(n => {
    const st = STATUS_NF[n.status] || [n.status, ''];
    let corpo = '';
    if (n.status === 'A_CONFERIR' && pode('receber')) {
      const ps = pedidosDe(n.fornecedor_id);
      corpo = `<div class="conf-nf" data-nf="${n.id}"><label>Pedido<select data-c="pedido">${ps.map(p => `<option value="${p.id}">${esc(p.numero)}</option>`).join('') || '<option value="">nenhum pedido emitido deste fornecedor</option>'}</select></label>
        <table><thead><tr><th>Linha da nota</th><th>Material</th><th>Fator</th><th>Item do pedido</th></tr></thead><tbody>${n.linhas.map(l => `<tr data-l="${l.id}">
          <td>${l.n_item}. ${esc(l.descricao)}<br><small>${nf(l.quantidade, 4)} ${esc(l.unidade)} × ${nf(l.valor_unitario, 4)}</small></td>
          <td><select data-k="material_id"><option value="__fora">— fora do estoque (frete, serviço)</option>${opMat(m => m.propriedade !== 'CAESB')}</select></td>
          <td><input data-k="fator" type="number" step="any" min="0" placeholder="1" style="width:80px" title="quantidade no material = quantidade da nota × fator"></td>
          <td><select data-k="pedido_item_id"></select></td></tr>`).join('')}</tbody></table>
        <div class="acoes"><button type="button" class="btn prim" data-conferir-nf="${n.id}">Conferir nota</button>${n.origem === 'DIGITADA' && n.registrada_por === USUARIO.login ? ' <small>(você digitou esta nota: outra pessoa confere)</small>' : ''}</div></div>`;
    } else if (n.status !== 'A_CONFERIR') {
      corpo = `<table><thead><tr><th>Material</th><th class="n">Na nota</th><th class="n">Entregue</th><th class="n">Aceito</th><th class="n">Devolvido</th><th></th></tr></thead><tbody>${n.itens.map(i => `<tr data-ni="${i.id}">
        <td>${esc(i.material_id)}</td><td class="n">${nf(i.quantidade, 3)}</td><td class="n">${nf(i.recebido, 3)}</td><td class="n">${nf(i.aceito, 3)}</td><td class="n">${nf(i.devolvido, 3)}</td>
        <td>${n.status === 'CONFERIDA' && pode('receber') && i.quantidade - i.recebido > 1e-9 ? `<input data-entrega type="number" step="any" min="0" value="${+(i.quantidade - i.recebido).toFixed(6)}" style="width:90px">` : ''}
          ${pode('receber') && i.aceito - i.devolvido > 1e-9 ? `<button type="button" class="btn" data-devolver="${i.id}">Devolver</button>` : ''}</td></tr>`).join('')}</tbody></table>
        ${n.status === 'CONFERIDA' && pode('receber') && n.itens.some(i => i.quantidade - i.recebido > 1e-9) ? `<div class="linha"><input data-doc-entrega placeholder="canhoto / romaneio"><button type="button" class="btn prim" data-receber="${n.id}">Registrar entrega (entra em quarentena)</button></div>` : ''}
        ${n.a_inspecionar.length ? `<b>Em quarentena — inspeção</b>${n.a_inspecionar.map(r => `<div class="linha lin-insp" data-ri="${r.id}"><span>${esc(r.material_id)} · ${nf(r.quantidade, 3)} · entregue ${esc(r.data)}</span>
          <input data-k="aceito" type="number" step="any" min="0" value="${r.quantidade}" title="aceito"><input data-k="recusado" type="number" step="any" min="0" value="0" title="recusado">
          <input data-k="laudo" placeholder="laudo / inspeção"><input data-k="motivo_recusa" placeholder="motivo da recusa">${pode('receber') ? `<button type="button" class="btn" data-inspecionar="${r.id}">Inspecionar</button>` : ''}</div>`).join('')}` : ''}`;
    }
    return `<div class="registro"><div><b>NF ${esc(n.numero)}${n.serie ? '/' + esc(n.serie) : ''} · ${esc(n.fornecedor || '')}</b>
      <span><span class="chip ${st[1]}">${esc(st[0])}</span> <small>${esc(n.origem)} · emissão ${esc(n.data_emissao || '')} · ${brl(n.valor_total)} · reg. ${esc(n.registrada_por || '')}${n.conferida_por ? ' · conf. ' + esc(n.conferida_por) : ''}</small>
      ${['A_CONFERIR', 'CONFERIDA'].includes(n.status) && pode('receber') && !n.itens.some(i => i.recebido > 0) ? ` <button type="button" class="btn" data-cancelar-nf="${n.id}">Cancelar</button>` : ''}</span></div>${corpo}</div>`;
  }).join('') || '<div class="vazio">Nenhuma nota no fluxo novo.</div>';
  $$('.conf-nf').forEach(box => {
    const sel = $('[data-c=pedido]', box);
    const atual = () => { const p = COMPRAS.pedidos.find(x => x.id === +sel.value);
      $$('tr[data-l]', box).forEach(tr => { const m = $('[data-k=material_id]', tr).value;
        $('[data-k=pedido_item_id]', tr).innerHTML = (p ? p.itens.filter(i => i.material_id === m) : []).map(i => `<option value="${i.id}">${esc(i.material_id)} · a faturar ${nf(i.a_faturar, 3)}</option>`).join('') || '<option value="">—</option>'; }); };
    sel.addEventListener('change', atual); $$('[data-k=material_id]', box).forEach(x => x.addEventListener('change', atual)); atual();
  });
}
const recarregarCompras = r => { if (r) carregarCompras(); };
$('#fSolic').addEventListener('submit', async ev => {
  ev.preventDefault();
  const r = await acao(() => api('/api/solicitacao', { data: hoje(), motivo: ev.target.motivo.value, itens: lerItens(ev.target, 'solic') }), 'Solicitação aberta (aguarda aprovação de outra pessoa).').catch(() => null);
  if (r) { ev.target.reset(); $('.editor-itens[data-itens=solic]').innerHTML = ''; carregarCompras(); }
});
$('#fForn').addEventListener('submit', async ev => {
  ev.preventDefault(); recarregarCompras(await acao(() => api('/api/fornecedor', formObj(ev.target)), 'Fornecedor cadastrado.').catch(() => null));
});
$('#fPedido').addEventListener('submit', async ev => {
  ev.preventDefault(); const o = formObj(ev.target);
  const itens = $$('#pedidoItens .lin-ped').map(l => ({ material_id: l.dataset.m, quantidade: +$('[data-k=quantidade]', l).value, valor_unitario: +$('[data-k=valor_unitario]', l).value || 0 })).filter(i => i.quantidade > 0);
  const r = await acao(() => api('/api/pedido', { ...o, faturamento_etapas: !!o.faturamento_etapas, itens }), 'Pedido emitido (não altera o estoque).').catch(() => null);
  if (r) { ev.target.reset(); carregarCompras(); }
});
$('#fXml').addEventListener('submit', async ev => {
  ev.preventDefault(); const arq = ev.target.arquivo.files[0];
  const r = await acao(async () => api('/api/nf/importar-xml', { conteudo_b64: await lerOriginal(arq), nome: arq.name }), 'NF-e importada: confira as linhas antes de receber.').catch(() => null);
  if (r) { ev.target.reset(); carregarCompras(); }
});
$('#fNfDig').addEventListener('submit', async ev => {
  ev.preventDefault(); const o = formObj(ev.target), arq = ev.target.arquivo.files[0];
  const r = await acao(async () => api('/api/nf/digitar', { numero: o.numero, data_emissao: o.data_emissao, fornecedor_id: o.fornecedor_id, chave: o.chave,
    linhas: lerItens(ev.target, 'nfdig'), documento_b64: await lerOriginal(arq), documento_tipo: arq.type === 'application/pdf' ? 'NF_PDF' : 'NF_IMAGEM', documento_nome: arq.name }), 'Nota registrada: outra pessoa confere contra o anexo.').catch(() => null);
  if (r) { ev.target.reset(); $('.editor-itens[data-itens=nfdig]').innerHTML = ''; carregarCompras(); }
});
$('#fTransf').addEventListener('submit', async ev => {
  ev.preventDefault();
  const r = await acao(() => api('/api/transferencia', { ...formObj(ev.target), data: hoje() }), 'Transferência registrada (custódia da equipe de origem para a de destino).').catch(() => null);
  if (r) ev.target.reset();
});
$('#fInv').addEventListener('submit', async ev => {
  ev.preventDefault();
  recarregarCompras(await acao(() => api('/api/inventario/contagem', { data: hoje(), itens: lerItens(ev.target, 'inv') }), 'Contagem registrada (o ajuste precisa da aprovação de outra pessoa).').catch(() => null));
});
document.addEventListener('click', async ev => {
  const t = ev.target, q = s => t.closest(s);
  let r = null;
  if (q('[data-solic]')) { const b = q('[data-solic]'), ap = b.dataset.ap === '1', motivo = ap ? null : prompt('Motivo da recusa:'); if (!ap && !motivo) return;
    r = await acao(() => api('/api/solicitacao/decidir', { solicitacao_id: b.dataset.solic, aprovar: ap, motivo }), ap ? 'Solicitação aprovada.' : 'Solicitação recusada.').catch(() => null); }
  else if (q('[data-pedido-enc]')) { const motivo = prompt('Motivo do encerramento do saldo (o já recebido continua valendo):'); if (!motivo) return;
    r = await acao(() => api('/api/pedido/encerrar', { pedido_id: q('[data-pedido-enc]').dataset.pedidoEnc, motivo }), 'Pedido encerrado.').catch(() => null); }
  else if (q('[data-conferir-nf]')) { const box = q('.conf-nf');
    const linhas = $$('tr[data-l]', box).map(tr => { const m = $('[data-k=material_id]', tr).value; return m === '__fora' ? { linha_id: tr.dataset.l, fora_do_estoque: true }
      : { linha_id: tr.dataset.l, material_id: m, fator: $('[data-k=fator]', tr).value || null, pedido_item_id: $('[data-k=pedido_item_id]', tr).value }; });
    r = await acao(() => api('/api/nf/conferir', { nf_id: box.dataset.nf, pedido_id: $('[data-c=pedido]', box).value, linhas }), 'Nota conferida: pode receber as entregas.').catch(() => null); }
  else if (q('[data-receber]')) { const card = q('.registro');
    const itens = $$('tr[data-ni]', card).map(tr => ({ nf_item_id: tr.dataset.ni, quantidade: +($('[data-entrega]', tr) || { value: 0 }).value })).filter(i => i.quantidade > 0);
    r = await acao(() => api('/api/recebimento', { nf_id: q('[data-receber]').dataset.receber, data: hoje(), itens, documento: $('[data-doc-entrega]', card).value }), 'Entrega registrada em quarentena.').catch(() => null); }
  else if (q('[data-inspecionar]')) { const l = q('.lin-insp'), o = Object.fromEntries($$('[data-k]', l).map(i => [i.dataset.k, i.value]));
    r = await acao(() => api('/api/inspecao', { recebimento_item_id: l.dataset.ri, ...o, data: hoje() }), 'Inspeção registrada: o aceito entrou no estoque.').catch(() => null); }
  else if (q('[data-devolver]')) { const qt = prompt('Quantidade a devolver ao fornecedor:'); if (!qt) return; const motivo = prompt('Motivo:'); if (!motivo) return; const doc = prompt('Documento (NF de devolução):') || null;
    r = await acao(() => api('/api/devolucao-fornecedor', { nf_item_id: q('[data-devolver]').dataset.devolver, data: hoje(), quantidade: qt, motivo, documento: doc }), 'Devolução registrada (saiu do estoque).').catch(() => null); }
  else if (q('[data-cancelar-nf]')) { const motivo = prompt('Motivo do cancelamento da nota:'); if (!motivo) return;
    r = await acao(() => api('/api/nf/cancelar', { nf_id: q('[data-cancelar-nf]').dataset.cancelarNf, motivo }), 'Nota cancelada.').catch(() => null); }
  else if (q('[data-inv]')) { const b = q('[data-inv]'), motivo = prompt(b.dataset.ap === '1' ? 'Motivo do ajuste:' : 'Motivo do descarte:'); if (!motivo) return;
    r = await acao(() => api('/api/inventario/decidir', { inventario_id: b.dataset.inv, aprovar: b.dataset.ap === '1', motivo }), 'Inventário decidido.').catch(() => null); }
  else if (t.id === 'vencBtn') { const ids = $$('[data-venc]:checked').map(i => +i.dataset.venc);
    r = await acao(() => api('/api/reservas/liberar-vencidas', { ids, motivo: $('#vencMotivo').value, hoje: hoje() }), 'Reservas vencidas liberadas.').catch(() => null); }
  else return;
  recarregarCompras(r);
});

/* ---------------------------------------------------------------- 3. lançamento de campo & fotos */
const fAp = $('#fApont');
ligarBusca($('input[name=alvo_txt]', fAp), r => selecionarCampo(r.tipo, r.id));
let CAMPO = null;
async function selecionarCampo(tipo, id) {
  const d = await acao(() => api(`/api/detalhe?tipo=${tipo}&id=${encodeURIComponent(id)}`));
  CAMPO = { tipo, id, d };
  $('#apMetros').style.display = tipo === 'TRECHO' ? '' : 'none';
  const iv = d.intervalos;
  const editavel = tipo === 'TRECHO' && !(d.execucao && d.execucao.ok_fiscal_em);
  $('#apAlvo').innerHTML = tipo === 'TRECHO'
    ? `<div class="aviso info">${esc(curto(d.nome))}: ${nf(d.extensao_m)} m · DE${d.de_mm} · ${esc(d.metodologia)}${d.perfil_bloqueado ? ' · <b>perfil bloqueado (E06)</b>' : ''} ${chipVerif(iv.verificacao)}
        <div style="margin-top:6px">${htmlEtapas(iv)}</div></div>
      ${iv.alertas.map(a => `<div class="aviso problema">${esc(a)}</div>`).join('')}
      ${iv.legado ? `<div class="caixa-retif" id="fLegado">
        <b>Conciliar avanço anterior sem posição</b> — ${nf(iv.legado.ASSENTADO)} m assentados${d.mnd ? '' : ` e ${nf(iv.legado.REATERRADO)} m reaterrados`}
        (apontamentos de ${esc([...new Set(iv.legado.apontamentos.map(a => a.data))].join(', '))}). Informe onde esses metros estão (um ou mais intervalos por etapa); a soma por etapa precisa ser igual. Não gera quantidades novas.
        <div class="editor" data-etapas="${d.mnd ? 'ASSENTADO' : 'ASSENTADO,REATERRADO'}" data-com-data="1">${(d.mnd ? ['ASSENTADO'] : ['ASSENTADO', 'REATERRADO']).map((e, _, et) => linhaIntervalo(et, { etapa: e }, true, false)).join('')}</div>
        <button type="button" class="btn" data-mais-linha>+ intervalo</button>
        <label>Como a posição foi confirmada<input data-r="motivo"></label>
        <div class="acoes"><button type="button" class="btn prim" id="legadoBtn">Conciliar</button></div></div>` : ''}
      <h4 style="margin:10px 0 4px">Intervalos por registro</h4>
      ${htmlRegistros(iv, editavel)}
      ${editavel ? '<p class="vazio" style="margin:2px 0">Retificar substitui os intervalos daquele registro. O trecho inteiro é conferido antes de gravar (tudo ou nada); o original fica no histórico.</p>' : ''}
      <div id="retifBox"></div>${htmlHistorico(iv)}
      <h4 style="margin:10px 0 4px">Liberação topográfica e escavação <small>(não geram quantidade)</small></h4>
      ${htmlComplementar(d.complementar, pode('retificar_campo'))}${(d.complementar.alertas || []).map(a => `<div class="aviso info">${esc(a)}</div>`).join('')}
      ${editavel ? `<div class="linha lin-compl" id="fCompl" style="margin-top:6px"><select data-c="etapa">${Object.entries(ROT_ETAPA).filter(([e]) => !(d.mnd && e === 'ESCAVADO')).map(([e, r]) => `<option value="${e}">${r}</option>`).join('')}</select>
        <input data-c="ini_m" type="number" step="any" min="0" placeholder="de (m)"><input data-c="fim_m" type="number" step="any" min="0" placeholder="até (m)">
        <input data-c="referencia" placeholder="nota de serviço / locação"><button type="button" class="btn" id="complBtn">Registrar</button></div>` : ''}`
    : `<div class="aviso info">${esc(curto(d.nome))}: ${esc(d.texto)}</div>`;
  $('#apAlvo').insertAdjacentHTML('beforeend', `<h4 style="margin:10px 0 4px">Ocorrências</h4>${htmlOcorrencias(d.ocorrencias, pode('verificar'))}
    <div class="linha" id="fOcor" style="margin-top:6px"><select data-o="tipo"><option value="IMPEDIMENTO">Impedimento</option><option value="NAO_CONFORMIDADE">Não conformidade</option></select>
      <select data-o="categoria"></select><input data-o="descricao" placeholder="o que aconteceu"><button type="button" class="btn" id="ocorBtn">Abrir ocorrência</button></div>`);
  const cats = () => { $('#fOcor [data-o=categoria]').innerHTML = (RESUMO.categorias_ocorrencia[$('#fOcor [data-o=tipo]').value] || []).map(c => `<option>${c}</option>`).join(''); };
  cats(); $('#fOcor [data-o=tipo]').addEventListener('change', cats);
  $('#ocorBtn').addEventListener('click', async () => {
    const o = Object.fromEntries($$('#fOcor [data-o]').map(i => [i.dataset.o, i.value])), f = formObj(fAp);
    const ok = await acao(() => api('/api/ocorrencia', { alvo_tipo: tipo, alvo_id: id, ...o, data: f.data || hoje(), equipe_id: f.equipe_id || null }), 'Ocorrência aberta.').catch(() => null);
    if (ok) selecionarCampo(tipo, id);
  });
  const cb = $('#complBtn');
  if (cb) cb.addEventListener('click', async () => {
    const o = Object.fromEntries($$('#fCompl [data-c]').map(i => [i.dataset.c, i.value])), f = formObj(fAp);
    const rota = o.etapa === 'ESCAVADO' ? '/api/escavacao' : '/api/liberacao';
    const ok = await acao(() => api(rota, { trecho_id: id, ini_m: o.ini_m, fim_m: o.fim_m, referencia: o.referencia, data: f.data || hoje() }), 'Registrado.').catch(() => null);
    if (ok) selecionarCampo(tipo, id);
  });
  renderSoldas();
  $('#apQuant').innerHTML = '';
  renderFotos();
  const fl = $('#fLegado');   // bloco dentro do formulário de apontamento: não pode ser <form> aninhado
  if (fl) $('#legadoBtn').addEventListener('click', async () => {
    const r = Object.fromEntries($$('[data-r]', fl).map(i => [i.dataset.r, i.value]));
    const ok = await acao(() => api('/api/legado/conciliar', { trecho_id: CAMPO.id, intervalos: lerLinhas(fl), motivo: r.motivo }),
      'Avanço anterior conciliado (sem quantidades novas).').catch(() => null);
    if (ok) { selecionarCampo(CAMPO.tipo, CAMPO.id); recarregarCamadaMapa(); }   // recusa: mantém o que foi digitado
  });
}
// editor de intervalos (conciliação e retificação): uma linha por intervalo
function linhaIntervalo(etapas, l = {}, comData = false, comRef = true) {
  return `<div class="linha lin-iv"><select data-k="etapa">${etapas.map(e => `<option ${e === l.etapa ? 'selected' : ''}>${e}</option>`).join('')}</select>
    <input data-k="ini_m" type="number" step="any" min="0" placeholder="de (m)" value="${l.ini_m ?? ''}"><input data-k="fim_m" type="number" step="any" min="0" placeholder="até (m)" value="${l.fim_m ?? ''}">
    ${comData ? `<input data-k="data" type="date" value="${esc(l.data || '')}" title="data do serviço">` : ''}${comRef ? `<input data-k="referencia" placeholder="registro do levantamento" value="${esc(l.referencia || '')}" title="só para CADASTRO_CAMPO">` : ''}
    <button type="button" class="btn" data-remover-linha title="remover">×</button></div>`;
}
const lerLinhas = box => $$('.lin-iv', box).map(l => Object.fromEntries($$('[data-k]', l).map(i => [i.dataset.k, i.type === 'number' ? (i.value === '' ? null : +i.value) : i.value])))
  .filter(o => o.ini_m != null && o.fim_m != null).map(o => ({ ...o, data: o.data || undefined, referencia: o.etapa === 'CADASTRO_CAMPO' ? o.referencia : undefined }));
document.addEventListener('click', ev => {
  const mais = ev.target.closest('[data-mais-linha]');
  if (mais) {
    const ed = mais.parentElement.querySelector('.editor'), et = ed.dataset.etapas.split(',');
    ed.insertAdjacentHTML('beforeend', linhaIntervalo(et, { etapa: et[0] }, !!ed.dataset.comData, !ed.dataset.comData));
  }
  const rm = ev.target.closest('[data-remover-linha]');
  if (rm) rm.closest('.lin-iv').remove();
});
document.addEventListener('click', async ev => {
  const a = ev.target.closest('[data-anular-etapa]'), r = ev.target.closest('[data-resolver-ocorrencia]');
  if (a) { const motivo = prompt('Motivo da anulação (o registro fica no histórico):'); if (!motivo) return;
    const ok = await acao(() => api('/api/etapa-complementar/anular', { registro_id: a.dataset.anularEtapa, motivo }), 'Registro anulado.').catch(() => null);
    if (ok && CAMPO) selecionarCampo(CAMPO.tipo, CAMPO.id); }
  if (r) { const resolucao = prompt('Resolução / correção feita:'); if (!resolucao) return;
    const ok = await acao(() => api('/api/ocorrencia/resolver', { ocorrencia_id: r.dataset.resolverOcorrencia, resolucao }), 'Ocorrência resolvida.').catch(() => null);
    if (ok && CAMPO) selecionarCampo(CAMPO.tipo, CAMPO.id); }
});
// retificação de intervalos (aba Campo)
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-retificar-ref]'); if (!b || !CAMPO) return;
  const [ref_tipo, ref_id] = b.dataset.retificarRef.split('|');
  const iv = CAMPO.d.intervalos, g = iv.registros.find(x => x.ref_tipo === ref_tipo && String(x.ref_id) === ref_id);
  const conc = ref_tipo === 'CONCILIACAO', etapas = conc ? (CAMPO.d.mnd ? ['ASSENTADO'] : ['ASSENTADO', 'REATERRADO']) : Object.keys(iv.etapas);
  $('#retifBox').innerHTML = `<div class="caixa-retif" data-ref="${ref_tipo}|${ref_id}">
    <b>Retificar ${conc ? 'conciliação do legado' : 'apontamento'} #${ref_id}</b> — informe o conjunto CORRETO de intervalos deste registro (linha vazia ou removida = intervalo anulado).
    ${conc ? 'A soma por etapa continua igual à da conciliação; não há quantidades.' : 'As quantidades do apontamento são recalculadas sem dupla contagem (veja a prévia).'}
    <div class="editor" data-etapas="${etapas.join(',')}" ${conc ? 'data-com-data="1"' : ''}>${g.intervalos.map(i => linhaIntervalo(etapas, i, conc, !conc)).join('')}</div>
    <button type="button" class="btn" data-mais-linha>+ intervalo</button>
    <div class="linha">${conc ? '' : `<label>Data do apontamento<input type="date" data-r="data" value="${esc(g.intervalos[0].data)}"></label>`}
      <label>Motivo (o que estava errado e como foi confirmado)<input data-r="motivo"></label></div>
    <div class="acoes"><button type="button" class="btn azul" data-retif-acao="previa">Prévia</button><button type="button" class="btn prim" data-retif-acao="aplicar">Aplicar retificação</button><button type="button" class="btn" data-retif-acao="cancelar">Cancelar</button></div>
    <div class="retif-previa"></div></div>`;
});
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-retif-acao]'); if (!b) return;
  const box = b.closest('.caixa-retif');
  if (b.dataset.retifAcao === 'cancelar') { box.remove(); return; }
  const [ref_tipo, ref_id] = box.dataset.ref.split('|'), r = Object.fromEntries($$('[data-r]', box).map(i => [i.dataset.r, i.value]));
  const corpo = { ref_tipo, ref_id, intervalos: lerLinhas($('.editor', box)), motivo: r.motivo, data: r.data, simular: b.dataset.retifAcao === 'previa' };
  const p = await acao(() => api('/api/intervalos/retificar', corpo), corpo.simular ? null : 'Retificação aplicada — original preservado no histórico.').catch(() => null);
  if (!p) return;
  if (!corpo.simular) { selecionarCampo(CAMPO.tipo, CAMPO.id); recarregarCamadaMapa(); return; }
  const lin = l => l.map(i => `${esc(i.etapa)} ${nf(i.ini_m)}–${nf(i.fim_m)} m (${esc(i.data)})`).join('<br>') || '—';
  const qs = (p.quantidades_depois || []).map(q => [q, (p.quantidades_antes || []).find(a => a.servico === q.servico && a.unidade === q.unidade)])
    .filter(([q, a]) => !a || a.confirmado !== q.confirmado).concat((p.quantidades_antes || []).filter(a => p.quantidades_depois && !p.quantidades_depois.some(q => q.servico === a.servico && q.unidade === a.unidade)).map(a => [null, a]));
  $('.retif-previa', box).innerHTML = `<table style="margin-top:8px"><thead><tr><th>Antes (anulado)</th><th>Depois</th></tr></thead><tbody><tr><td>${lin(p.anulados)}</td><td>${lin(p.novos)}</td></tr></tbody></table>
    <p style="margin:4px 0">Trecho: ${Object.keys(p.resumo_depois).map(e => `${esc(e)} ${nf(p.resumo_antes[e])} → <b>${nf(p.resumo_depois[e])}</b> m`).join(' · ')}</p>
    ${p.quantidades_depois ? (qs.length ? `<p style="margin:4px 0">Quantidades confirmadas que mudam: ${qs.map(([q, a]) => `${esc((q || a).servico)} ${nf(a ? a.confirmado : 0, 3)} → <b>${nf(q ? q.confirmado : 0, 3)}</b> ${esc((q || a).unidade)}`).join(' · ')}</p>` : '<p style="margin:4px 0">Quantidades confirmadas: sem mudança.</p>') : ''}
    ${(p.alertas || []).map(a => `<div class="aviso info">${esc(a)}</div>`).join('')}
    <p class="vazio" style="margin:2px 0">Prévia: nada foi gravado. Confira e use "Aplicar retificação".</p>`;
});
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
    .map(([etapa, k]) => ({ etapa, ini_m: +o[k + '_ini'], fim_m: +o[k + '_fim'], ...(k === 'cad' && o.cad_ref ? { referencia: o.cad_ref } : {}) }));
  await acao(() => api('/api/apontamento', { data: o.data, equipe_id: o.equipe_id, alvo_tipo: CAMPO.tipo, alvo_id: CAMPO.id,
    concluido_100: !!o.concluido_100, intervalos: o.concluido_100 ? null : intervalos,
    estaca_ini: o.estaca_ini, estaca_fim: o.estaca_fim, quantidades }), 'Apontamento registrado.');
  $('#apQuant').innerHTML = ''; ['ass', 'cad', 'rea'].forEach(k => { $(`input[name=${k}_ini]`, fAp).value = ''; $(`input[name=${k}_fim]`, fAp).value = ''; });
  $('input[name=cad_ref]', fAp).value = '';
  $('input[name=concluido_100]', fAp).checked = false;
  selecionarCampo(CAMPO.tipo, CAMPO.id);
}

document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-verificar-intervalo]'); if (!b) return;
  if (!confirm(`Confirmar que você (${USUARIO.login}) conferiu este intervalo em campo? Quem informou não pode verificar.`)) return;
  const r = await acao(() => api('/api/intervalo/verificar', { intervalo_id: b.dataset.verificarIntervalo }), 'Intervalo verificado (conferência interna).').catch(() => null);
  if (r) { selecionarCampo(CAMPO.tipo, CAMPO.id); recarregarCamadaMapa(); }
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
  const r = await acao(() => api('/api/solda', { ...o, data: d.data || hoje(), equipe_id: d.equipe_id || null, alvo_tipo: CAMPO.tipo, alvo_id: CAMPO.id }), 'Soldas registradas (aguardam verificação).').catch(() => null);
  if (r) { ev.target.reset(); selecionarCampo(CAMPO.tipo, CAMPO.id); }
});
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-verificar-solda]'); if (!b) return;
  const ok = confirm(`Verificação por ${USUARIO.login} (não pode ser o soldador nem quem informou).\n\nSoldas APROVADAS? (Cancelar = reprovadas)`);
  const obs = ok ? null : prompt('Motivo da reprovação:');
  if (!ok && !obs) return;
  const r = await acao(() => api('/api/solda/verificar', { solda_id: b.dataset.verificarSolda, resultado: ok ? 'APROVADA' : 'REPROVADA', obs }), 'Verificação registrada.').catch(() => null);
  if (r) selecionarCampo(CAMPO.tipo, CAMPO.id);
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
  '3_RECEBIDO': [['4_GDOC_ANALISE', 'Catalogar no GDOC', [['protocolo_gdoc', 'Nº protocolo GDOC']]],
    ['2_ENVIADO', 'Devolver à empresa (conferência não conforme)', []]],
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
      <div><span class="chip ${c.levantamento_completo ? 'azul' : 'amarelo'}" title="intervalos CADASTRO_CAMPO registrados antes do reaterro">levantamento de campo ${c.levantamento_completo ? 'completo' : nf(c.levantamento_m) + ' m de ' + nf(c.extensao_m)}</span></div>
      ${c.conferencia ? `<div><span class="chip ${c.conferencia.resultado === 'CONFORME' ? 'azul' : 'vermelho'}" title="conferência interna Ankara — não é aprovação da Caesb">Rev. ${c.conferencia.revisao}: ${c.conferencia.resultado === 'CONFORME' ? 'conforme' : 'não conforme'} (interno) · ${esc(c.conferencia.revisor)}</span>${c.conferencia.obs ? `<div class="aviso problema">${esc(c.conferencia.obs)}</div>` : ''}</div>` : ''}
      ${k === '3_RECEBIDO' ? `<details class="conf" data-tr="${esc(c.trecho_id)}"><summary>Conferência interna Ankara (não é aprovação da Caesb)</summary>
        ${Object.entries(RESUMO.checklist_conferencia || {}).map(([ck, txt]) => `<label class="check"><input type="checkbox" data-ck="${ck}"> ${esc(txt)}</label>`).join('')}
        <input data-c="obs" placeholder="Divergência (obrigatória se não conforme)">
        <div class="acoes"><button type="button" class="btn" data-conf="CONFORME">Conforme</button><button type="button" class="btn" data-conf="NAO_CONFORME">Não conforme</button></div></details>` : ''}
      ${(CAMPOS_ETAPA[k] || []).filter(([dest]) => k !== '3_RECEBIDO' || (dest === '2_ENVIADO') === !!(c.conferencia && c.conferencia.resultado === 'NAO_CONFORME'))
        .map(([dest, rot, campos]) => `<form class="form" data-tr="${esc(c.trecho_id)}" data-dest="${dest}">
        ${campos.map(([n, l, t]) => `<input name="${n}" placeholder="${l}" ${t ? `type="${t}"` : ''} required>`).join('')}
        <button class="btn ${dest === '5A_NEGADO' || (k === '3_RECEBIDO' && dest === '2_ENVIADO') ? '' : 'prim'}">${rot}</button></form>`).join('')}</div>`).join('') || '<div class="vazio">—</div>'}</div>`;
  }).join('');
}
$('#kanban').addEventListener('click', async ev => {
  const b = ev.target.closest('[data-conf]'); if (!b) return;
  const box = b.closest('details.conf');
  const checklist = Object.fromEntries($$('[data-ck]', box).map(i => [i.dataset.ck, i.checked]));
  const ok = await acao(() => api('/api/cadastro/conferencia', { trecho_id: box.dataset.tr, resultado: b.dataset.conf, checklist,
    obs: $('[data-c=obs]', box).value }), 'Conferência interna registrada (não é aprovação da Caesb).').catch(() => null);
  if (ok) carregarEsteira();
});
$('#kanban').addEventListener('submit', async ev => {
  ev.preventDefault(); const f = ev.target, dados = formObj(f);
  if (dados.arquivos) dados.arquivos = dados.arquivos.split(/[;,]/).map(s => s.trim()).filter(Boolean);
  const ok = await acao(() => api('/api/cadastro', { trecho_id: f.dataset.tr, destino: f.dataset.dest, dados, data: hoje() }), 'Esteira atualizada.').catch(() => null);
  if (ok) carregarEsteira();
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
  renderMedComplementos(r);
  carregarElegibilidade(id);
  $('#medTetos').className = r.tetos.length ? '' : 'vazio';
  $('#medTetos').innerHTML = r.tetos.length ? `<table><thead><tr><th>Subgrupo</th><th class="n">Teto</th><th class="n">Anterior</th><th class="n">Atual</th><th class="n">Excedente</th></tr></thead><tbody>
    ${r.tetos.map(t => `<tr><td>${esc(t.subgrupo)} ${esc(t.nome || '')}</td><td class="n">${brl(t.teto)}</td><td class="n">${brl(t.anterior)}</td><td class="n">${brl(t.atual)}</td><td class="n">${t.excedente ? `<span class="chip vermelho">${brl(t.excedente)}</span>` : '—'}</td></tr>`).join('')}</tbody></table>` : 'Sem lançamentos com item de BM.';
}
const SIT_REGRA = { 'CONFIRMADA': 'verde', 'PROVISÓRIA': 'amarelo', 'HIPÓTESE': 'amarelo', 'BLOQUEADA': 'vermelho', 'VÍNCULO INCOMPLETO': 'vermelho' };
const SIT_ELEG = { PROPOSTO_NESTA: ['verde', 'proposto nesta'], APTO_SEM_OK: ['amarelo', 'completo, sem OK interno'],
  PARCIAL_NAO_ELEGIVEL: ['cinza', 'parcial — não elegível (D-30)'], MEDIDO_ANTES: ['azul', 'medido antes'] };
function renderMedComplementos(r) {
  const aberta = r.medicao.status === 'ABERTA', c = r.conferencia;
  $('#medConfItens').innerHTML = Object.entries(r.roteiro_conferencia).map(([k, t]) =>
    `<label class="check"><input type="checkbox" name="ck_${k}"> ${esc(t)}</label>`).join('');
  $('#fMedConf').hidden = !aberta || !pode('medicao');
  $('#medConfEstado').innerHTML = !c ? `<div class="aviso info">Sem conferência interna: o fechamento exige uma conferência <b>CONFORME</b> sobre os lançamentos atuais (D-59, provisório).</div>`
    : `<div class="aviso ${c.resultado === 'CONFORME' && c.vale ? 'ok' : 'problema'}"><b>Conferência #${c.id}: ${c.resultado === 'CONFORME' ? 'CONFORME' : 'NÃO CONFORME'}</b> por ${esc(c.por)} em ${esc(c.em)}.
       ${c.vale ? '' : ' <b>Não vale mais:</b> os lançamentos mudaram depois dela — confira de novo.'}${c.obs ? ' ' + esc(c.obs) : ''}</div>`;
  $('#medFechar').disabled = !aberta || !(c && c.vale && c.resultado === 'CONFORME');
  $('#medFechar').title = $('#medFechar').disabled && aberta ? 'Exige conferência interna CONFORME e vigente' : '';
  $('#medConfHist').innerHTML = r.conferencias.length > 1 ? `<details><summary>Histórico (${r.conferencias.length})</summary><ul>${r.conferencias.map(x =>
    `<li>#${x.id} ${x.resultado} — ${esc(x.por)}, ${esc(x.em)}${x.obs ? ': ' + esc(x.obs) : ''}</li>`).join('')}</ul></details>` : '';
  $('#medRegras').className = '';
  $('#medRegras').innerHTML = `<table><tbody>${r.regras.map(g => `<tr><td><span class="chip ${SIT_REGRA[g.situacao] || ''}">${esc(g.situacao.toLowerCase())}</span></td>
    <td>${esc(g.regra)}<br><small>${esc(g.efeito)}${g.decisao ? ' · <b>' + esc(g.decisao) + '</b>' : ''}</small></td></tr>`).join('')}</tbody></table>`;
  const dup = r.duplicidades.length ? `<div class="aviso problema"><b>Parcela em mais de uma medição:</b> ${r.duplicidades.map(d => `${esc(d.servico)} de ${esc(d.alvo_nome)} (medições ${d.medicoes.join(', ')})`).join('; ')}</div>` : '';
  $('#medParcelas').className = r.acumulado.length || dup ? '' : 'vazio';
  $('#medParcelas').innerHTML = dup + (r.acumulado.length ? `<div class="tabela"><table><thead><tr><th>Item</th><th>Unid.</th><th class="n">Contrato</th><th class="n">Anterior</th><th class="n">Nesta</th><th class="n">Acumulado</th><th class="n">Saldo</th></tr></thead><tbody>
    ${r.acumulado.map(i => `<tr><td title="${esc(i.descricao || '')}">${esc(i.item)}</td><td>${esc(i.unidade || '')}</td><td class="n">${nf(i.contrato, 3)}</td><td class="n">${nf(i.anterior, 3)}</td>
      <td class="n">${nf(i.nesta, 3)}</td><td class="n">${i.excede_contrato ? `<span class="chip vermelho">${nf(i.acumulado, 3)}</span>` : nf(i.acumulado, 3)}</td><td class="n">${nf(i.saldo, 3)}</td></tr>`).join('')}</tbody></table></div>` : 'Nenhuma parcela com item de BM proposta.');
}
async function carregarElegibilidade(id) {
  const el = await api('/api/medicao/elegibilidade?id=' + id);
  if (String(id) !== $('#medSel').value) return;
  const cont = Object.entries(SIT_ELEG).map(([k, [cor, rot]]) => `<span class="chip ${cor}">${el.contagem[k]} ${rot}</span>`).join(' ');
  $('#medEleg').className = '';
  $('#medEleg').innerHTML = `<p style="margin:0 0 6px">${cont}</p>
    <p class="vazio" style="margin:0 0 8px">${esc(el.regra)} No período: ${nf(el.resumo.assentado_periodo_m, 2)} m assentados (informado), ${nf(el.resumo.verificado_periodo_m, 2)} m verificados; ${nf(el.resumo.proposto_nesta_m, 2)} m de trechos propostos nesta medição.
      Cadastros medidos nesta: ${el.cadastro.medidos_nesta}. Recomposições ainda não lançadas: ${el.recomposicao_nao_lancada}.</p>
    ${el.linhas.length ? `<div class="tabela"><table><thead><tr><th>Situação</th><th>Trecho / nó</th><th class="n">Assent. período</th><th class="n">Verif. período</th><th>Impedimentos / alertas</th></tr></thead><tbody>
    ${el.linhas.map(l => `<tr><td><span class="chip ${SIT_ELEG[l.situacao][0]}">${SIT_ELEG[l.situacao][1]}${l.medido_na ? ' (' + l.medido_na + 'ª)' : ''}</span></td>
      <td><a href="#" data-abrir="${l.alvo_tipo}|${esc(l.alvo_id)}">${esc(curto(l.nome))}</a></td><td class="n">${l.assentado_periodo_m != null ? nf(l.assentado_periodo_m, 2) : '—'}</td>
      <td class="n">${l.verificado_periodo_m != null ? nf(l.verificado_periodo_m, 2) : '—'}</td><td><small>${esc([...l.impedimentos, ...l.alertas].join(' · ') || '—')}</small></td></tr>`).join('')}</tbody></table></div>` : ''}
    ${el.materiais.length ? `<div class="aviso info" style="margin-top:8px"><b>Material no período — bloqueado (D-53 · D-54):</b> regime de faturamento não aprovado; recebido não é faturável.
      <ul style="margin:4px 0 0 18px">${el.materiais.map(m => `<li>${esc(m.material_id)} (${esc(m.propriedade)}): recebido ${nf(m.recebido, 2)} · aplicado ${nf(m.aplicado, 2)} ${esc(m.unidade)}</li>`).join('')}</ul></div>` : ''}`;
}
$('#medEleg').addEventListener('click', ev => {
  const a = ev.target.closest('[data-abrir]'); if (!a) return;
  ev.preventDefault(); const [tipo, id] = a.dataset.abrir.split('|');
  abrirAba('mapa'); mostrarFiscal(tipo, id);
});
$('#fMedConf').addEventListener('submit', async ev => {
  ev.preventDefault();
  const f = ev.target, checklist = {};
  f.querySelectorAll('input[type=checkbox]').forEach(i => { checklist[i.name.slice(3)] = i.checked; });
  const ok = await acao(() => api('/api/medicao/conferir', { medicao_id: +$('#medSel').value, resultado: f.resultado.value, obs: f.obs.value, checklist }),
    'Conferência registrada.').catch(() => null);
  if (ok) { f.reset(); carregarMedicao(); }
});
$('#fMed').addEventListener('submit', async ev => {
  ev.preventDefault(); await acao(() => api('/api/medicao', formObj(ev.target)), 'Medição aberta.'); carregarMedicoes();
});
$('#medFechar').addEventListener('click', async () => {
  if (!confirm('Fechar a medição? Nenhum lançamento novo poderá entrar nela.')) return;
  const ok = await acao(() => api('/api/medicao/fechar', { medicao_id: +$('#medSel').value }), 'Medição fechada.').catch(() => null);
  if (ok) carregarMedicoes();
});

/* ---------------------------------------------------------------- 7. relatórios */
const ROT_PEND = { impedimentos: 'Impedimentos', nao_conformidades: 'Não conformidades', intervalos_sem_verificacao: 'Intervalos sem verificação',
  reaterro_sem_cadastro: 'Reaterro sem cadastro', legado_sem_posicao: 'Legado sem posição', aguardando_ok_interno: 'Aguardando OK interno',
  concluidos_sem_fotos: 'Concluídos sem fotos', cadastro_pronto: 'Cadastro não enviado', cadastro_recebido: 'Cadastro a conferir',
  cadastro_negado: 'Cadastro negado', programacao_vencida: 'Programação vencida' };
let RELATORIO = null;
async function carregarRelatorios() {
  if (!carregarRelatorios.feito) { carregarRelatorios.feito = true; $('#rlIni').value = hoje().slice(0, 8) + '01'; $('#rlFim').value = hoje(); }
  if ($('#rlFrente').options.length < 2) $('#rlFrente').innerHTML += (RESUMO.frentes || []).map(f => `<option>${esc(f)}</option>`).join('');
  const q = new URLSearchParams({ ini: $('#rlIni').value, fim: $('#rlFim').value });
  if ($('#rlFrente').value) q.set('frente', $('#rlFrente').value);
  $('#rlExport').href = '/api/relatorios/exportar?' + q;
  const r = RELATORIO = await api('/api/relatorios?' + q);
  const av = r.avanco, t = av.total_periodo;
  const dias = Object.entries(av.por_dia), maxd = Math.max(1, ...dias.map(d => d[1]));
  $('#rlAvanco').className = '';
  $('#rlAvanco').innerHTML = `<div class="kpis"><div class="kpi"><span>Assentado</span><b>${nf(t.ASSENTADO, 2)} m</b></div><div class="kpi"><span>Cadastro de campo</span><b>${nf(t.CADASTRO_CAMPO, 2)} m</b></div><div class="kpi"><span>Reaterrado</span><b>${nf(t.REATERRADO, 2)} m</b></div></div>
    ${av.por_equipe.length ? `<div class="tabela"><table><thead><tr><th>Frente</th><th>Equipe</th><th class="n">Assentado</th><th class="n">Cad. campo</th><th class="n">Reaterrado</th><th class="n">Trechos</th></tr></thead><tbody>
      ${av.por_equipe.map(l => `<tr><td>${esc(l.frente_id)}</td><td>${esc(l.equipe_id)}</td><td class="n">${nf(l.ASSENTADO, 2)}</td><td class="n">${nf(l.CADASTRO_CAMPO, 2)}</td><td class="n">${nf(l.REATERRADO, 2)}</td><td class="n">${l.trechos}</td></tr>`).join('')}</tbody></table></div>` : '<div class="vazio">Nenhum intervalo no período.</div>'}
    ${dias.length ? `<div class="barras" title="assentado por dia">${dias.map(([d, m]) => `<div><i style="height:${Math.max(3, 60 * m / maxd)}px"></i><small>${d.slice(8)}/${d.slice(5, 7)}</small><small>${nf(m, 1)}</small></div>`).join('')}</div>` : ''}`;
  $('#rlFrentes').innerHTML = `<table><thead><tr><th>Frente</th><th class="n">Extensão (m)</th><th class="n">Assentado</th><th class="n">%</th><th class="n">Reaterrado</th><th class="n">Legado s/ posição</th><th class="n">Nós concl.</th></tr></thead><tbody>
    ${av.frentes.map(f => `<tr><td>${esc(f.frente_id)}</td><td class="n">${nf(f.extensao_m, 2)}</td><td class="n">${nf(f.assentado_m, 2)}</td><td class="n">${f.assentado_pct != null ? nf(f.assentado_pct, 2) : '—'}</td>
      <td class="n">${nf(f.reaterrado_m, 2)}</td><td class="n">${f.legado_sem_posicao_m ? `<span class="chip amarelo">${nf(f.legado_sem_posicao_m, 2)}</span>` : '—'}</td><td class="n">${f.nos_concluidos}/${f.nos}</td></tr>`).join('')}</tbody></table>`;
  const pf = r.pendencias.frentes.filter(f => f.total), g = r.pendencias.gerais;
  $('#rlPend').className = '';
  $('#rlPend').innerHTML = (pf.length ? `<div class="tabela"><table><thead><tr><th>Frente</th><th>Pendências</th><th class="n">Total</th></tr></thead><tbody>
    ${pf.map(f => `<tr><td>${esc(f.frente_id)}</td><td>${Object.entries(ROT_PEND).filter(([k]) => f[k]).map(([k, rot]) => `<span class="chip ${['impedimentos', 'nao_conformidades', 'cadastro_negado'].includes(k) ? 'vermelho' : 'amarelo'}">${f[k]} ${esc(rot)}</span>`).join(' ')}</td><td class="n">${f.total}</td></tr>`).join('')}</tbody></table></div>`
    : '<div class="vazio">Nenhuma pendência nas frentes.</div>')
    + `<p style="margin:8px 0 0"><span class="chip ${g.reservas_vencidas ? 'amarelo' : ''}">${g.reservas_vencidas} reserva(s) vencida(s)</span> <span class="chip ${g.notas_a_conferir ? 'amarelo' : ''}">${g.notas_a_conferir} nota(s) a conferir</span> <span class="chip ${g.itens_em_quarentena ? 'amarelo' : ''}">${g.itens_em_quarentena} item(ns) em quarentena</span></p>`;
  $('#rlFalt').innerHTML = r.faltantes.length ? `<table><thead><tr><th>Material</th><th class="n">Previsto</th><th class="n">Reservado</th><th class="n">Disponível</th><th class="n">A receber</th><th class="n">Faltante</th></tr></thead><tbody>
    ${r.faltantes.map(f => `<tr><td>${esc(f.material_id)}</td><td class="n">${nf(f.previsto, 3)}</td><td class="n">${nf(f.reservado, 3)}</td><td class="n">${nf(f.disponivel, 3)}</td><td class="n">${nf(f.a_receber, 3)}</td>
      <td class="n">${f.faltante > 0 ? `<span class="chip vermelho">${nf(f.faltante, 3)}</span>` : '0'}</td></tr>`).join('')}</tbody></table>` : '<div class="vazio" style="padding:8px">Nenhum material previsto nas programações do período.</div>';
  renderMateriaisRel();
}
function renderMateriaisRel() {
  const ms = RELATORIO.materiais.filter(m => !$('#rlSoMov').checked || m.movimentado);
  $('#rlMat').innerHTML = ms.length ? `<table><thead><tr><th>Material</th><th>Prop.</th><th class="n">Previsto</th><th class="n">Solicitado</th><th class="n">Comprado</th><th class="n">A receber</th><th class="n">Quarentena</th><th class="n">Recebido</th>
    <th class="n">Saldo almox.</th><th class="n">Reservado</th><th class="n">Com equipes</th><th class="n">Aplicado</th><th class="n">Perda</th><th>Medido</th></tr></thead><tbody>
    ${ms.map(m => `<tr><td title="${esc(m.descricao)}">${esc(m.material_id)}<br><small>${esc(m.descricao.slice(0, 48))} (${esc(m.unidade)})</small></td><td>${esc(m.propriedade)}</td>
      ${['previsto', 'solicitado', 'comprado', 'a_receber', 'quarentena', 'recebido', 'saldo_almox', 'reservado', 'com_equipes', 'aplicado', 'perda'].map(k => `<td class="n">${m[k] == null ? '—' : nf(m[k], 3)}</td>`).join('')}
      <td><span class="chip vermelho" title="${esc(m.medido_situacao)}">bloqueado</span></td></tr>`).join('')}</tbody></table>
    <p class="vazio" style="margin:6px 0 0">Medido: material não entra na medição enquanto o regime estiver bloqueado (D-53 · D-54). Pedido não é estoque; recebido não é faturável.</p>`
    : '<div class="vazio" style="padding:8px">Nenhum material com movimento.</div>';
}
['#rlIni', '#rlFim', '#rlFrente'].forEach(x => $(x).addEventListener('change', carregarRelatorios));
$('#rlSoMov').addEventListener('change', () => RELATORIO && renderMateriaisRel());

/* ---------------------------------------------------------------- 6. usuários e histórico */
async function carregarLink() {
  const r = await api('/api/link').catch(() => null);
  LINK_ATUAL = r && r.situacao === 'NO_AR' ? r.url : null;
  $('#linkBtn').hidden = !LINK_ATUAL;
  $('#painelLink').hidden = !(r && r.ligado);
  if (r && r.ligado) $('#linkEstado').innerHTML = LINK_ATUAL
    ? `<p style="margin:0 0 6px">Envie este endereço para a equipe (cada pessoa entra com o próprio usuário):</p><p style="font-size:17px;font-weight:700;word-break:break-all;margin:0 0 6px">${esc(LINK_ATUAL)}</p><small class="vazio">Vale enquanto o programa estiver aberto no computador do escritório; muda quando ele reinicia.</small>`
    : `<p class="vazio" style="margin:0">${r.configurado ? esc(r.erro || 'Ligando o link…') : 'Crie o administrador no computador do programa (endereço /configurar).'}</p>`;
}
let LINK_ATUAL = null;
$('#linkBtn').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(LINK_ATUAL); toast('Link copiado: ' + LINK_ATUAL, 'ok'); } catch (_) { prompt('Copie o link:', LINK_ATUAL); }
});
async function carregarAdmin() {
  carregarLink();
  $('#painelUsuarios').hidden = !pode('usuarios');
  if (pode('usuarios')) {
    const us = await api('/api/usuarios');
    $('#selPerfil').innerHTML = Object.entries(RESUMO.perfis).map(([k, p]) => `<option value="${k}">${esc(p.nome)}</option>`).join('');
    $('#usuariosLista').innerHTML = `<table><thead><tr><th>Login</th><th>Nome</th><th>Perfil</th><th>Equipe</th><th></th></tr></thead><tbody>${us.map(u => `<tr${u.ativo ? '' : ' style="opacity:.5"'}>
      <td>${esc(u.login)}</td><td>${esc(u.nome)}</td><td>${esc(u.perfil_nome)}</td><td>${esc(u.equipe_id || '')}</td>
      <td>${u.login === USUARIO.login ? '' : `<button type="button" class="btn" data-usr-ativo="${esc(u.login)}" data-v="${u.ativo ? 0 : 1}">${u.ativo ? 'Desativar' : 'Reativar'}</button> <button type="button" class="btn" data-usr-senha="${esc(u.login)}">Nova senha</button>`}</td></tr>`).join('')}</tbody></table>`;
  }
  carregarAuditoria();
}
async function carregarAuditoria() {
  const q = new URLSearchParams({ limite: 200 });
  if ($('#audLogin').value) q.set('login', $('#audLogin').value.trim());
  if ($('#audAlvo').value) q.set('alvo_id', $('#audAlvo').value.trim());
  if (!q.get('alvo_id') && !pode('auditoria')) { $('#audLista').innerHTML = '<div class="vazio" style="padding:8px">Seu perfil consulta o histórico de um objeto: informe o objeto.</div>'; return; }
  const ls = await acao(() => api('/api/auditoria?' + q)).catch(() => []);
  $('#audLista').innerHTML = ls.length ? `<table><thead><tr><th>Quando</th><th>Usuário</th><th>Operação</th><th>Objeto</th><th>Resultado</th></tr></thead><tbody>${ls.map(a => `<tr>
    <td>${esc(a.em.replace('T', ' '))}</td><td>${esc(a.login || '—')} <small>${esc(a.perfil || '')}</small></td><td>${esc(a.rota.replace('/api/', ''))}</td>
    <td>${esc([a.alvo_tipo, a.alvo_id].filter(Boolean).join(' '))}</td>
    <td>${a.status === 200 ? '<span class="chip azul">aceito</span>' : `<span class="chip vermelho">${a.status}</span>`} <small>${esc((a.resultado || '').slice(0, 160))}</small></td></tr>`).join('')}</tbody></table>`
    : '<div class="vazio" style="padding:8px">Nada registrado.</div>';
}
$('#audBtn').addEventListener('click', carregarAuditoria);
$('#fUsuario').addEventListener('submit', async ev => {
  ev.preventDefault(); const o = formObj(ev.target);
  const r = await acao(() => api('/api/usuarios', { acao: 'criar', ...o }), 'Usuário criado.').catch(() => null);
  if (r) { ev.target.reset(); carregarAdmin(); }
});
document.addEventListener('click', async ev => {
  const a = ev.target.closest('[data-usr-ativo]'), s = ev.target.closest('[data-usr-senha]');
  if (a) { const r = await acao(() => api('/api/usuarios', { acao: 'alterar', login: a.dataset.usrAtivo, ativo: a.dataset.v === '1' }), 'Usuário atualizado.').catch(() => null); if (r) carregarAdmin(); }
  if (s) { const senha = prompt('Nova senha (mín. 10 caracteres) para ' + s.dataset.usrSenha + ':'); if (!senha) return;
    await acao(() => api('/api/usuarios', { acao: 'senha', login: s.dataset.usrSenha, senha }), 'Senha redefinida; as sessões dessa pessoa foram encerradas.').catch(() => null); }
});

/* ---------------------------------------------------------------- login e início */
function mostrarLogin(msg) {
  USUARIO = null; $('#login').hidden = false;
  const m = $('#loginMsg'); m.hidden = !msg || /Entre com seu usuário/.test(msg); m.textContent = msg || '';
  setTimeout(() => $('#fLogin input[name=login]').focus(), 50);
}
$('#fLogin').addEventListener('submit', async ev => {
  ev.preventDefault();
  try { const r = await api('/api/login', formObj(ev.target)); USUARIO = r.usuario; DEMONSTRACAO = !!r.demonstracao; ev.target.reset(); $('#login').hidden = true; iniciar(); }
  catch (e) { const m = $('#loginMsg'); m.hidden = false; m.textContent = e.message; }
});
$('#entrarLocal').addEventListener('click', async () => {
  try { const r = await api('/api/entrar-local', {}); USUARIO = r.usuario; DEMONSTRACAO = !!r.demonstracao; $('#login').hidden = true; iniciar(); }
  catch (e) { if (/administrador/.test(e.message)) location.href = '/configurar'; else { const m = $('#loginMsg'); m.hidden = false; m.textContent = e.message; } }
});
$('#sairBtn').addEventListener('click', async () => { await api('/api/logout', {}).catch(() => null); location.reload(); });
$('#senhaBtn').addEventListener('click', async () => {
  const atual = prompt('Senha atual:'); if (!atual) return;
  const nova = prompt('Nova senha (mín. 10 caracteres):'); if (!nova) return;
  await acao(() => api('/api/senha', { senha_atual: atual, nova_senha: nova }), 'Senha alterada.').catch(() => null);
});
function aplicarPermissoes() {
  $('#quem').innerHTML = `<b>${esc(USUARIO.nome)}</b><br>${esc(USUARIO.login)} · ${esc(USUARIO.perfil_nome)}${USUARIO.equipe_id ? ' · ' + esc(USUARIO.equipe_id) : ''}`;
  $('#sairBtn').hidden = $('#senhaBtn').hidden = false;
  $('#faixaDemo').hidden = !DEMONSTRACAO;
  // a tela só indica o que o perfil pode fazer; quem decide é o servidor (403)
  $$('[data-perm]').forEach(el => { const ok = el.dataset.perm.split(' ').some(pode); el.toggleAttribute('data-sem-permissao', !ok); el.title = ok ? '' : 'Seu perfil não tem esta permissão'; });
}

let INICIADO = false;
async function iniciar() {
  if (!USUARIO) {
    try { const r = await api('/api/sessao'); USUARIO = r.usuario; DEMONSTRACAO = !!r.demonstracao; } catch (_) { return; }   // sem sessão: tela de login
  }
  aplicarPermissoes();
  carregarLink();
  if (INICIADO) return;
  INICIADO = true;
  RESUMO = await api('/api/resumo');
  $$('.selEquipe').forEach(s => s.innerHTML = '<option value="">—</option>' + RESUMO.equipes.map(e => `<option value="${e.id}">${esc(e.nome)}</option>`).join(''));
  $$('.selClima').forEach(s => s.innerHTML = '<option value="">—</option>' + Object.entries(RESUMO.clima).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join(''));
  $('select[name=contingencia]').innerHTML += RESUMO.contingencias.map(c => `<option>${esc(c)}</option>`).join('');
  $$('input[type=date]').forEach(i => { if (!i.value && i.name !== 'periodo_ini' && i.name !== 'periodo_fim') i.value = hoje(); });
  const ms = await api('/api/medicoes'); const ab = ms.find(m => m.status === 'ABERTA'); if (ab) MEDICAO_ATUAL = ab.id;
  let aba = 'mapa'; try { aba = localStorage.getItem('aba') || 'mapa'; } catch (_) { /* sem storage */ }
  abrirAba(aba);
}
iniciar();
