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
const ROT_REGISTRO = { APONTAMENTO: 'Apontamento', CONCILIACAO: 'Conciliação do legado', CADASTRO_CAMPO: 'Cadastro de campo (terceirizada)' };
function htmlRegistros(iv, editavel) {
  return iv.registros.map(g => `<div class="registro"><div><b>${ROT_REGISTRO[g.ref_tipo] || esc(g.ref_tipo)} #${g.ref_id}</b>
      ${editavel ? `<button type="button" class="btn" data-retificar-ref="${g.ref_tipo}|${g.ref_id}">Retificar</button>` : ''}</div>
    ${g.intervalos.map(i => `<div><small>${esc(i.etapa)} ${nf(i.ini_m)}–${nf(i.fim_m)} m · ${esc(i.data)} · ${esc(i.origem)}${i.informado_por ? ' · ' + esc(i.informado_por) : ''}${i.referencia ? ' · registro: ' + esc(i.referencia) : ''}</small>
      ${i.verificado_em ? `<span class="chip azul">verificado · ${esc(i.verificado_por)}</span>` : editavel ? `<button type="button" class="btn" data-verificar-intervalo="${i.id}">Verificar</button>` : '<span class="chip amarelo">sem verificação</span>'}</div>`).join('')}</div>`).join('')
    || '<div class="vazio">Nenhum intervalo registrado.</div>';
}
function htmlHistorico(iv) {
  if (!iv.retificacoes.length && !iv.anulados.length && !iv.conciliacoes.length) return '';
  return `<details><summary>Histórico: ${iv.conciliacoes.length} conciliação(ões), ${iv.retificacoes.length} retificação(ões), ${iv.anulados.length} intervalo(s) anulado(s)</summary>
    ${iv.conciliacoes.map(c => `<div><small>Conciliação #${c.id} · ${esc(String(c.em).slice(0, 10))} · ${esc(c.responsavel)} · ${nf(c.metros_assentado)} m assentados / ${nf(c.metros_reaterrado)} m reaterrados — ${esc(c.motivo)}</small></div>`).join('')}
    ${iv.retificacoes.map(r => `<div><small>Retificação #${r.id} · ${esc(String(r.em).slice(0, 10))} · ${esc(r.responsavel)} · ${(ROT_REGISTRO[r.ref_tipo] || r.ref_tipo).toLowerCase()} #${r.ref_id}${r.novo_apontamento_id ? ' → apontamento #' + r.novo_apontamento_id : ''} — ${esc(r.motivo)}</small></div>`).join('')}
    ${iv.anulados.map(i => `<div style="opacity:.6;text-decoration:line-through"><small>${esc(i.etapa)} ${nf(i.ini_m)}–${nf(i.fim_m)} m · ${esc(i.data)} · ${esc(i.origem)}${i.verificado_por ? ' · verificado por ' + esc(i.verificado_por) : ''} (anulado pela retificação #${i.anulado_por})</small></div>`).join('')}</details>`;
}
const htmlPendencias = ps => ps && ps.length ? `<ul class="pend">${ps.map(p => `<li><span class="chip ${NIVEL[p.nivel]}">${esc(p.nivel.toLowerCase())}</span> <b>${esc(p.area)}:</b> ${esc(p.texto)}</li>`).join('')}</ul>`
  : '<div class="vazio">Sem pendências registradas.</div>';
const htmlFases = fs => (fs || []).map(f => `<div class="fase"><b>${esc(f.nome)}</b> <span class="chip ${(FASE_STATUS[f.status] || ['', ''])[1]}">${esc((FASE_STATUS[f.status] || [f.status])[0])}</span>
    ${f.evidencias.length ? `<ul>${f.evidencias.map(e => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}
    ${f.pendencias.length ? `<ul class="pendencias">${f.pendencias.map(e => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}</div>`).join('');
const FOTO_OK = v => v && !['INVALIDA', 'ARQUIVO_AUSENTE'].includes(v);
const ROT_ETAPA = { LIBERACAO_TOPOGRAFICA: 'Liberação topográfica', ESCAVADO: 'Escavado (vala aberta)' };
function htmlComplementar(c, editavel, etapas = Object.keys(ROT_ETAPA)) {
  if (!c) return '';
  return `<table style="margin-top:4px"><thead><tr><th>Etapa</th><th class="n">Metros</th><th>Feito (m)</th></tr></thead><tbody>
    ${etapas.map(e => `<tr><td>${ROT_ETAPA[e]}</td><td class="n">${nf(c[e].metros)}</td><td>${faixa(c[e].cobertura)}</td></tr>`).join('')}</tbody></table>
    ${etapas.flatMap(e => c[e].registros).map(r => `<div><small>${esc(ROT_ETAPA[r.etapa])} ${nf(r.ini_m)}–${nf(r.fim_m)} m · ${esc(r.data)} · ${esc(r.registrado_por)}${r.referencia ? ' · ' + esc(r.referencia) : ''}</small>
      ${editavel ? `<button type="button" class="btn" data-anular-etapa="${r.id}">Anular</button>` : ''}</div>`).join('')}
    ${c.anulados.filter(r => etapas.includes(r.etapa)).length ? `<details><summary>${c.anulados.filter(r => etapas.includes(r.etapa)).length} registro(s) anulado(s)</summary>${c.anulados.filter(r => etapas.includes(r.etapa)).map(r => `<div style="opacity:.6;text-decoration:line-through"><small>${esc(ROT_ETAPA[r.etapa])} ${nf(r.ini_m)}–${nf(r.fim_m)} m · ${esc(r.data)} — ${esc(r.anulado_motivo)} (${esc(r.anulado_por)})</small></div>`).join('')}</details>` : ''}`;
}
// lacunas de uma cobertura já unida e ordenada (como vem do servidor), de 0 à extensão
const lacunasDe = (cob, ext) => { const out = []; let pos = 0;
  for (const [a, b] of cob || []) { if (a > pos + 1e-3) out.push([pos, Math.min(a, ext)]); pos = Math.max(pos, b); }
  if (pos < ext - 1e-3) out.push([pos, ext]); return out; };
// o encarregado só consulta: liberação topográfica e levantamento de cadastro são registrados pela engenharia
function htmlTerceirizadas(d) {
  const lib = d.complementar && d.complementar.LIBERACAO_TOPOGRAFICA, ext = d.extensao_m;
  if (!lib) return '';
  const falta = lacunasDe(lib.cobertura, ext), lev = (d.fases_cadastro || [])[0];
  const cor = !falta.length ? 'azul' : lib.metros > 0 ? 'amarelo' : 'vermelho';
  return `<div class="registro"><div><b>Liberação topográfica</b> <span class="chip ${cor}">liberado ${nf(lib.metros)} de ${nf(ext)} m</span></div>
      <small>Liberado: ${faixa(lib.cobertura)}${falta.length ? ` · <b>falta liberar: ${faixa(falta)}</b>` : ''}</small></div>
    ${lev ? htmlFases([lev]) : ''}`;
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

/* ---------------------------------------------------------------- tema (escuro por padrão) */
function aplicarTema(t) {
  document.documentElement.dataset.tema = t;
  $('#temaBtn').textContent = t === 'claro' ? 'Tema escuro' : 'Tema claro';
  try { localStorage.setItem('mc-tema', t); } catch (_) { /* sem storage */ }
}
$('#temaBtn').addEventListener('click', () => aplicarTema(document.documentElement.dataset.tema === 'claro' ? 'escuro' : 'claro'));
aplicarTema(document.documentElement.dataset.tema === 'claro' ? 'claro' : 'escuro');

/* ---------------------------------------------------------------- navegação: tela inicial, menu lateral e telas */
// cada tela é uma <section id="aba-…">; as dos grupos (Campo, Almoxarifado, Administrativo) aparecem como subitens no menu lateral
const TELAS = {
  inicio: { titulo: 'Início', carregar: () => renderInicio() },
  iluminado: { titulo: 'Mapa iluminado', carregar: () => carregarIluminado() },
  campo: { titulo: 'Lançamento do dia', grupo: 'grupo-campo', carregar: () => carregarLancamentoDia() },
  notas: { titulo: 'Notas de serviço', grupo: 'grupo-campo', carregar: () => carregarNotas() },
  topografia: { titulo: 'Topografia', grupo: 'grupo-campo', carregar: () => carregarTopografia() },
  cadastro_campo: { titulo: 'Cadastro de campo', grupo: 'grupo-campo', carregar: () => carregarCadCampo() },
  interferencias: { titulo: 'Interferências e ocorrências', grupo: 'grupo-campo', carregar: () => carregarInterferencias() },
  diario: { titulo: 'Diário de obra', grupo: 'grupo-campo', carregar: () => carregarDiario() },
  mapa: { titulo: 'Dados da obra', grupo: 'planejamento', carregar: () => carregarDadosObra() },
  cronograma: { titulo: 'Cronograma da obra', grupo: 'planejamento', carregar: () => carregarCronograma() },
  almox: { titulo: 'Estoque e movimentos', grupo: 'planejamento', carregar: () => carregarAlmox() },
  compras: { titulo: 'Compras e notas', grupo: 'planejamento', carregar: () => carregarCompras() },
  equipes: { titulo: 'Equipes', grupo: 'administrativo', carregar: () => carregarAlmox() },
  relatorios: { titulo: 'Relatórios', grupo: 'administrativo', carregar: () => carregarRelatorios() },
  admin: { titulo: 'Usuários e histórico', grupo: 'administrativo', carregar: () => carregarAdmin() },
  lev: { titulo: 'LEV', grupo: 'administrativo', carregar: () => carregarLev() },
  medicao: { titulo: 'Medição', grupo: 'administrativo', carregar: () => carregarMedicoes() },
};
const GRUPOS = { 'grupo-campo': 'Execução', planejamento: 'Planejamento', administrativo: 'Administrativo' };
// telas que o perfil abre (config/perfis.json); o servidor confere de novo em cada consulta
const podeTela = id => id === 'inicio' || !!(USUARIO && USUARIO.telas.includes(id));
const telasDoGrupo = g => Object.keys(TELAS).filter(t => TELAS[t].grupo === g && podeTela(t));
let TELA = null;
// telas que saíram (link salvo): abrem a tela nova certa, com um aviso curto
const TELAS_ANTIGAS = {
  prog: ['mapa', 'A programação das equipes agora é feita no Dados da obra: o dia de cada equipe.'],
  ponto: ['mapa', 'O check-in e o check-out agora são a liberação e a devolução, no Dados da obra.'],
  esteira: ['iluminado', 'A esteira do cadastro agora fica na ficha do trecho, no Mapa iluminado.'],
};
// páginas dentro de uma aba (Execução): chips no topo, a página no endereço (#topografia/resumo), com voltar e avançar,
// e lembrada por aba na sessão. Cada página diz quem a usa; a aba abre na pedida, na lembrada ou na primeira que o perfil usa
const PAGINAS = {
  campo: [['apropriacao', 'Apropriação direta', () => pode('apropriacao')], ['apontamento', 'Apontamento sem NS', () => pode('lancar_sem_ns')],
    ['fotos', 'Fotos e soldas', () => pode('campo')], ['clima', 'Clima do dia', () => pode('campo')]],
  notas: [['dia', 'NS do dia', () => pode('campo')], ['servico', 'Serviço de obra', () => pode('notas_servico')]],
  topografia: [['enviar', 'Enviar NS de topografia', () => podeNs('TOPOGRAFIA')], ['resumo', 'Resumo', () => true]],
  cadastro_campo: [['enviar', 'Enviar NS de cadastro', () => podeNs('CADASTRO')], ['feito', 'O que foi feito', () => true]],
};
const PAGINA = {};                                     // a página aberta em cada aba
const paginasDe = tela => (PAGINAS[tela] || []).filter(([, , usa]) => usa());
function paginaDe(tela, pedida) {
  const ps = paginasDe(tela).map(p => p[0]); if (!ps.length) return null;
  let lembrada = null; try { lembrada = sessionStorage.getItem('mc-pagina-' + tela); } catch (_) { /* sem storage */ }
  return [pedida, lembrada].find(p => p && ps.includes(p)) || ps[0];
}
function mostrarPagina(tela, pag) {
  PAGINA[tela] = pag;
  try { sessionStorage.setItem('mc-pagina-' + tela, pag); } catch (_) { /* sem storage */ }
  const sec = $('#aba-' + tela), ps = paginasDe(tela), chips = $('.paginas-aba', sec);
  chips.innerHTML = ps.map(([id, rot]) => `<button type="button" data-pagina-ir="${id}" aria-pressed="${id === pag}">${esc(rot)}</button>`).join('');
  chips.hidden = ps.length < 2;
  $$('[data-pagina]', sec).forEach(el => { el.hidden = el.dataset.pagina !== pag; });
}
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-pagina-ir]'); if (!b || !PAGINAS[TELA]) return;
  abrirAba(`${TELA}/${b.dataset.paginaIr}`, { manterRolagem: true });
});
function abrirAba(id, opcoes = {}) {
  let [base, pedida] = String(id).split('/');
  id = base;
  if (TELAS_ANTIGAS[id]) { toast(TELAS_ANTIGAS[id][1]); id = TELAS_ANTIGAS[id][0]; opcoes = { ...opcoes, substituir: true }; }
  if (GRUPOS[id]) id = telasDoGrupo(id)[0];          // o grupo abre a primeira tela dele que o perfil usa
  if (!TELAS[id] || !podeTela(id)) id = 'inicio';
  TELA = id;
  document.body.classList.toggle('no-inicio', id === 'inicio');
  $$('section.aba').forEach(s => s.classList.toggle('ativa', s.id === 'aba-' + id));
  $$('.rail-item').forEach(b => b.dataset.tela === id || (b.dataset.grupo && b.dataset.grupo === TELAS[id].grupo)
    ? b.setAttribute('aria-current', 'page') : b.removeAttribute('aria-current'));
  $$('.rail-sub').forEach(s => s.classList.toggle('aberta', s.dataset.grupo === TELAS[id].grupo));
  $('#topoTitulo').textContent = id === 'inicio' ? 'Morro da Cruz' : TELAS[id].titulo;
  document.title = id === 'inicio' ? 'Morro da Cruz' : `${TELAS[id].titulo} · Morro da Cruz`;
  const pag = PAGINAS[id] ? paginaDe(id, pedida) : null;
  if (pag) mostrarPagina(id, pag);
  const endereco = '#' + id + (pag ? '/' + pag : '');
  if (location.hash !== endereco) history[opcoes.substituir || (pag && location.hash === '#' + id) ? 'replaceState' : 'pushState'](null, '', endereco);
  fecharMenuMovel();
  if (!opcoes.manterRolagem) window.scrollTo(0, 0);
  return TELAS[id].carregar();
}
window.addEventListener('popstate', () => USUARIO && abrirAba(location.hash.slice(1) || 'inicio', { substituir: true }));
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-tela]') || ev.target.closest('button[data-grupo]'); if (!b) return;
  ev.preventDefault(); abrirAba(b.dataset.tela || b.dataset.grupo);
});

// menu lateral: recolhido mostra só os ícones; passar o mouse (ou o foco do teclado) abre por cima; o botão fixa aberto
const RAIL = $('#rail');
const telaMovel = () => matchMedia('(max-width: 760px)').matches;
RAIL.addEventListener('mouseenter', () => { if (!telaMovel()) RAIL.classList.add('aberto'); });
RAIL.addEventListener('mouseleave', () => RAIL.classList.remove('aberto'));
RAIL.addEventListener('focusin', () => { if (!telaMovel()) RAIL.classList.add('aberto'); });
RAIL.addEventListener('focusout', ev => { if (!RAIL.contains(ev.relatedTarget)) RAIL.classList.remove('aberto'); });
function fixarRail(fixo) {
  RAIL.classList.toggle('fixo', fixo); document.body.classList.toggle('rail-fixo', fixo);
  const b = $('#railFixar'); b.setAttribute('aria-pressed', String(fixo));
  b.title = b.ariaLabel = fixo ? 'Soltar o menu' : 'Fixar o menu aberto';
  try { localStorage.setItem('mc-rail-fixo', fixo ? '1' : ''); } catch (_) { /* sem storage */ }
}
$('#railFixar').addEventListener('click', () => fixarRail(!RAIL.classList.contains('fixo')));
try { if (localStorage.getItem('mc-rail-fixo')) fixarRail(true); } catch (_) { /* sem storage */ }
function fecharMenuMovel() { document.body.classList.remove('menu-aberto'); $('#railFundo').hidden = true; $('#menuBtn').setAttribute('aria-expanded', 'false'); }
$('#menuBtn').addEventListener('click', () => {
  const abrir = !document.body.classList.contains('menu-aberto');
  if (!abrir) return fecharMenuMovel();
  document.body.classList.add('menu-aberto'); $('#railFundo').hidden = false; $('#menuBtn').setAttribute('aria-expanded', 'true');
});
$('#railFundo').addEventListener('click', fecharMenuMovel);
document.addEventListener('keydown', ev => { if (ev.key === 'Escape') fecharMenuMovel(); });

/* ---------------------------------------------------------------- tela inicial: o Menu de cada perfil */
const MODOS = {
  iluminado: { nome: 'Mapa iluminado', desc: 'A rede trecho a trecho e onde cada equipe está trabalhando: liberado, em execução, concluído e cadastrado.' },
  'grupo-campo': { nome: 'Execução', desc: 'O serviço em campo: o lançamento do dia sem nota, as notas de serviço da obra (a NS do dia e a de serviço), a topografia e o cadastro de campo (cada um com o envio das NS e o resumo), as interferências e o diário de obra.' },
  planejamento: { nome: 'Planejamento', desc: 'O dia de cada equipe no mapa do Dados da obra (programar, liberar o material e receber a devolução), o cronograma do Project (os 18 meses), o estoque com as notas a receber e o aceite do material, e compras.' },
  administrativo: { nome: 'Administrativo', desc: 'Equipes, cadastro, relatórios, usuários, LEV (cronograma, BM, redes e conexões) e medição de teste.' },
};
// a ordem do Menu segue o trabalho de cada perfil; o que o perfil não abre fica de fora
const MENU_PERFIL = {
  ENGENHARIA: ['iluminado', 'administrativo', 'planejamento', 'grupo-campo'],
  ADMINISTRACAO: ['iluminado', 'administrativo', 'planejamento', 'grupo-campo'],
  ALMOXARIFADO: ['planejamento', 'grupo-campo', 'iluminado'], CADASTRO: ['grupo-campo', 'administrativo', 'iluminado'],
  TOPOGRAFIA: ['grupo-campo', 'iluminado'],
};
const ORDEM_MENU = ['iluminado', 'administrativo', 'planejamento', 'grupo-campo'];
const abreModo = id => GRUPOS[id] ? telasDoGrupo(id).length > 0 : podeTela(id);
let MENU_FOCO = null;
const iniciais = n => (String(n || '').replace(/\(.*?\)/g, '').replace(/[^\p{L}\s]/gu, '').trim().split(/\s+/).filter(Boolean)
  .map(p => p[0]).filter((_, i, a) => i === 0 || i === a.length - 1).join('') || '?').toUpperCase();
function renderInicio() {
  if (!USUARIO) return;
  const itens = (MENU_PERFIL[USUARIO.perfil] || ORDEM_MENU).filter(abreModo);
  if (!itens.includes(MENU_FOCO)) MENU_FOCO = itens[0];
  const seta = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 12h15M13 5l7 7-7 7"/></svg>';
  $('#menuLista').innerHTML = itens.map(id => `<div class="menu-bloco" data-modo="${id}">
      <button type="button" class="menu-item" data-tela="${id}"><span>${esc(MODOS[id].nome)}</span>
        <span class="fim">${MODOS[id].teste ? '<span class="teste">teste</span>' : ''}${seta}</span></button></div>`).join('');
  focarMenu(MENU_FOCO);
  if (RESUMO) {
    const km = (RESUMO.extensao_m / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const lig = RESUMO.ligacoes ? ` e ${nf(RESUMO.ligacoes.quantidade, 0)} casas ligadas à rede` : '';
    $('#inicioDesc').textContent = `Rede de água em São Sebastião (DF) para a Caesb: ${km} km de tubulação${lig}.`;
    if (RESUMO.ligacoes) $('#inicioDesc').title = `Ligações: ${RESUMO.ligacoes.fonte}. Tubulação: soma dos trechos da 06.1.`;
    $('#inicioContrato').textContent = RESUMO.contrato;
  }
  desenharRede();
}
function focarMenu(id) {
  MENU_FOCO = id;
  $$('#menuLista .menu-bloco').forEach(b => {
    const ativo = b.dataset.modo === id;
    $('.menu-item', b).classList.toggle('ativo', ativo);
    const d = $('.menu-desc', b);
    if (ativo && !d) b.insertAdjacentHTML('beforeend', `<p class="menu-desc">${esc(MODOS[id].desc)}</p>`);
    if (!ativo && d) d.remove();
  });
  realcarRede(id === 'iluminado');
}
['mouseover', 'focusin'].forEach(t => $('#menuLista').addEventListener(t, ev => {
  const b = ev.target.closest('.menu-bloco'); if (b && b.dataset.modo !== MENU_FOCO) focarMenu(b.dataset.modo);
}));

/* ---------------------------------------------------------------- busca de trecho/nó */
function ligarBusca(input, aoEscolher) {
  const ul = input.parentElement.querySelector('ul');
  let t;
  input.addEventListener('input', () => {
    clearTimeout(t); input.dataset.tipo = ''; input.dataset.id = '';
    t = setTimeout(async () => {
      const q = input.value.trim(); if (q.length < 2) { ul.hidden = true; return; }
      const res = await api('/api/buscar?q=' + encodeURIComponent(q));
      // o nome completo (a numeração TR recomeça a cada PB), com a cor da zona quando o mapa já está carregado
      const cor = r => ((typeof GERAL !== 'undefined' && GERAL && GERAL.zonas.find(z => r.rotulo.startsWith(z.id + '_'))) || {}).cor;
      ul.innerHTML = res.map((r, i) => `<li data-i="${i}"><span>${cor(r) ? `<i class="zona-cor" style="background:${esc(cor(r))}"></i>` : ''}${esc(r.nome || r.rotulo)}</span><small>${r.tipo === 'TRECHO' ? 'trecho' : 'nó/caixa'} · ${esc(r.extra || '')}</small></li>`).join('') || '<li><small>nada encontrado</small></li>';
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
  $('#kpis').innerHTML = [
    ['Rede de projeto', nf(r.extensao_m) + ' m'], ['Rede reaterrada', nf(r.executado_m) + ' m'],
    ['Trechos', nf(r.trechos)], ['Nós e caixas', nf(r.elementos)], ['Validados (OK interno)', nf(r.ok_fiscal)], ['Contrato (cl. 3.1)', brl(r.valor_contrato)],
  ].map(([k, v]) => `<div class="kpi"><span>${k}</span><b>${v}</b></div>`).join('') +
    (r.itens_pendentes ? `<div class="kpi" style="border-top-color:var(--vermelho)"><span>Itens 06.2 sem quantidade/unidade com fonte</span><b>${nf(r.itens_pendentes)}</b></div>` : '');
  const est = await estadoMapa(true);
  $('#pins').innerHTML = est.pins.length ? est.pins.map(p => `<div class="acoes" style="margin-bottom:6px">📍 <b>${esc(p.equipe)}</b> <button class="btn" data-fisc="${esc(p.alvo_tipo)}|${esc(p.alvo_id)}">${esc(nomeCompleto(p.alvo_id))}</button></div>`).join('')
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
  const podeOk = ex && ex.concluido && !st.length && !ex.ok_fiscal_em;
  $('#fiscDetalhe').className = '';
  $('#fiscDetalhe').innerHTML = `<h2 style="word-break:break-word">${esc(nomeCompleto(d.nome))}</h2>
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
    ${tipo === 'TRECHO' ? (d.retirado ? '' : '<div class="caminho-box" id="fiscCaminho"><p class="vazio">Carregando o caminho até a medição…</p></div>') : `<label class="check" style="margin:8px 0"><input type="checkbox" id="okFiscal" ${ex && ex.ok_fiscal_em ? 'checked disabled' : podeOk ? '' : 'disabled'}>
      <b>[✓] OK interno — pronto para medir</b></label>
    ${!podeOk && !(ex && ex.ok_fiscal_em) ? '<div class="vazio">Exige 100 % executado e as fotos obrigatórias.</div>' : ''}`}
    ${ex && ex.ok_fiscal_em && !ex.recomposicao_ok ? `<div class="form" style="margin-top:10px"><b>Recomposição (equipe de pavimento)</b>
      <div class="linha"><select id="recTipo"><option>CALÇADA</option><option>ASFALTO</option></select><input id="recQtd" type="number" step="any" placeholder="quantidade"></div>
      <button class="btn" id="recBtn">Lançar recomposição</button></div>` : ''}`;
  $('#histObj').addEventListener('toggle', async ev => {
    if (!ev.target.open || ev.target.dataset.ok) return;
    const ls = await api(`/api/auditoria?alvo_tipo=${tipo}&alvo_id=${encodeURIComponent(d.id)}&limite=60`).catch(() => []);
    ev.target.dataset.ok = '1';
    ev.target.innerHTML = '<summary>Histórico de alterações (quem fez o quê)</summary>' + (ls.map(a => `<div><small>${esc(a.em.replace('T', ' '))} · ${esc(a.login || '—')} · ${esc(a.rota.replace('/api/', ''))} · ${a.status === 200 ? 'aceito' : 'recusado ' + a.status}${a.status !== 200 && a.resultado ? ': ' + esc(a.resultado.slice(0, 120)) : ''}</small></div>`).join('') || '<div class="vazio">Nada registrado.</div>');
  });
  if (tipo === 'TRECHO' && !d.retirado) montarCaminho($('#fiscCaminho'), d.nome, () => { mostrarFiscal(tipo, id); recarregarCamadaMapa(); carregarMapa(); });
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
  if (TELA === 'mapa') plnFocar(tipo, d.nome);                    // o mapa do Dados da obra vai até o trecho
}
// depois de um registro (OK interno, liberação, devolução, NS…) o mapa do Dados da obra, o Mapa iluminado e o mapa da tela
// Início relêem a situação na hora (sem esperar os 30 s da leitura guardada), e o mapa REV02 aberto noutra aba também
let CANAL_MAPA = null;
try { CANAL_MAPA = new BroadcastChannel('mc-mapa'); } catch (_) { /* navegador antigo: o REV02 relê a cada minuto */ }
function recarregarCamadaMapa() {
  plnRecarregar();
  if (TELA === 'iluminado' && ILU.pronto) carregarIluminado();
  if (CANAL_MAPA) CANAL_MAPA.postMessage('recarregar');
}

/* ---------------------------------------------------------------- 2. almoxarifado & equipes */
async function carregarAlmox() {
  MATERIAIS = await api('/api/estoque');
  const opt = m => `<option value="${esc(m.id)}">${esc(m.id)} — ${esc(m.descricao.slice(0, 70))} (${esc(m.unidade)})</option>`;
  $$('.selMaterial').forEach(s => s.innerHTML = MATERIAIS.filter(m => m.propriedade !== 'ANKARA').map(opt).join(''));
  $$('.selMaterialAnkara').forEach(s => s.innerHTML = MATERIAIS.filter(m => m.propriedade === 'ANKARA').map(opt).join(''));
  $$('.selMaterialReserva').forEach(s => s.innerHTML = MATERIAIS.filter(m => m.propriedade !== 'CONSUMO' && m.disponivel > 0).map(m => `<option value="${esc(m.id)}">${esc(m.id)} (disponível ${nf(m.disponivel)} ${esc(m.unidade)})</option>`).join('') || '<option value="">nada disponível</option>');
  renderEstoque();
  if (TELA === 'almox' && pode('almox') && podeTela('mapa')) almoxEquipesDoDia();
  if (podeTela('almox') || podeTela('compras')) renderNotasReceber(await api('/api/almox/notas'));
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
  if (!$('#hIni').value) { $('#hIni').value = hoje().slice(0, 8) + '01'; $('#hFim').value = hoje(); }
  carregarHistograma();
}
/* ---- Notas a receber (Estoque e movimentos): da importação do XML ao aceite, na tela do almoxarife */
const ST_NOTA = { A_CONFERIR: ['a conferir', 'amarelo'], CONFERIDA: ['a receber', 'azul'], ENCERRADA: ['recebida', 'verde'] };
function renderNotasReceber(notas) {
  const box = $('#notasReceber'), rec = pode('receber');
  $('#listaMateriais').innerHTML = MATERIAIS.map(m => `<option value="${esc(m.id)}">${esc(m.descricao.slice(0, 70))} (${esc(m.unidade)})</option>`).join('');
  box.className = notas.length ? '' : 'vazio';
  if (!notas.length) { box.textContent = 'Nenhuma nota a receber.'; return; }
  box.innerHTML = notas.map(n => {
    const st = ST_NOTA[n.status] || [n.status.toLowerCase(), ''], sug = Object.fromEntries((n.sugestoes || []).map(x => [x.linha_id, x]));
    const aprovar = n.sem_pedido && !n.aprovada_em;
    let corpo = '';
    if (n.status === 'A_CONFERIR' && rec) {
      corpo = `<div class="nota-conf"><label>Pedido<select data-c="pedido"><option value="">sem pedido (precisa de aprovação)</option>${n.pedidos.map(p => `<option value="${p.id}">${esc(p.numero)}</option>`).join('')}</select></label>
        ${n.linhas.map(l => { const s = sug[l.id] || {};
          return `<div class="nota-l" data-l="${l.id}"><div>${l.n_item}. ${esc(l.descricao)} <small>· ${nf(l.quantidade, 4)} ${esc(l.unidade)}${l.codigo ? ' · código ' + esc(l.codigo) : ''}</small></div>
            <div class="linha"><label>Material<input data-k="material_id" list="listaMateriais" value="${esc(s.material_id || '')}" placeholder="vazio = fora do estoque"></label>
              <label>Fator<input data-k="fator" type="number" step="any" min="0" value="${s.fator || ''}" placeholder="1" title="quantidade no material = quantidade da nota × fator"></label></div>
            <small>${s.material_id ? `sugerido (${esc(s.motivo)}): ${esc(((MATERIAIS.find(m => m.id === s.material_id) || {}).descricao || '').slice(0, 60))}${s.caesb ? ' · tubo da Caesb: entra como romaneio' : ''}` : 'sem sugestão: escolha o material ou deixe vazio (frete, serviço)'}</small></div>`; }).join('')}
        <div class="acoes"><button type="button" class="btn prim" data-nota-conferir="${n.id}">Conferir as linhas</button></div></div>`;
    } else if (n.status === 'CONFERIDA') {
      const falta = n.itens.filter(i => i.quantidade - i.recebido > 1e-9);
      corpo = (falta.length && rec ? `<div class="nota-chegou"><b>O que chegou</b>${falta.map(i => `<div class="linha" data-ni="${i.id}"><span>${esc(i.material_id)} <small>${esc((i.descricao || '').slice(0, 60))}${i.romaneio_caesb ? ' · romaneio Caesb' : ''}</small><br><small>na nota ${nf(i.quantidade, 3)} · já chegou ${nf(i.recebido, 3)} ${esc(i.unidade || '')}</small></span>
          <label>Chegou<input data-chegou type="number" step="any" min="0" value="${+(i.quantidade - i.recebido).toFixed(6)}"></label></div>`).join('')}
          <div class="linha"><input data-doc-entrega placeholder="canhoto / romaneio da entrega"><button type="button" class="btn prim" data-nota-receber="${n.id}">Registrar o que chegou</button></div></div>` : '')
        + n.entregas.map(e => `<div class="nota-insp" data-rec="${e.id}"><b>Em quarentena · entrega de ${dataBR(e.data)}${e.documento ? ' · ' + esc(e.documento) : ''}</b>
          ${e.itens.map(i => `<div class="linha" data-ri="${i.id}"><span>${esc(i.material_id)} · ${nf(i.quantidade, 3)} ${esc(i.unidade || '')}</span>
            <label>Aceito<input data-k="aceito" type="number" step="any" min="0" value="${i.quantidade}"></label><label>Recusado<input data-k="recusado" type="number" step="any" min="0" value="0"></label></div>`).join('')}
          ${rec ? `<div class="linha"><input data-laudo placeholder="laudo da entrega (obrigatório só com recusa)"><input data-motivo placeholder="motivo da recusa"></div>
          <div class="acoes"><button type="button" class="btn prim" data-nota-aceitar="${e.id}">Aceitar tudo desta entrega</button><button type="button" class="btn" data-nota-inspecionar="${e.id}">Registrar a inspeção</button></div>` : ''}</div>`).join('');
    }
    const aprovacao = !aprovar ? '' : pode('compras_aprovar') && USUARIO.login !== n.registrada_por
      ? `<div class="acoes"><button type="button" class="btn ok" data-nota-aprovar="${n.id}">Aprovar a nota sem pedido</button></div>`
      : '<div class="aviso info">Nota sem pedido: o material aceito fica no almoxarifado, mas só vai para as equipes depois da aprovação de Engenharia ou Administração (outra pessoa, não quem importou).</div>';
    return `<div class="registro nota-card"><div><b>NF ${esc(n.numero)}${n.serie ? '/' + esc(n.serie) : ''} · ${esc(n.fornecedor || '')}</b>
        <span class="chip ${st[1]}">${esc(st[0])}</span>${n.sem_pedido ? ` <span class="chip ${n.aprovada_em ? 'verde' : 'amarelo'}">sem pedido · ${n.aprovada_em ? 'aprovada por ' + esc(n.aprovada_por) : 'aguardando aprovação'}</span>` : ''}</div>
      <small>emissão ${esc(dataBR(n.data_emissao || ''))} · ${n.linhas.length} linha${n.linhas.length > 1 ? 's' : ''} · ${brl(n.valor_total)} · importada por ${esc(n.registrada_por || '')}</small>
      ${corpo}${aprovacao}</div>`;
  }).join('');
}
// vários XML de uma vez, um pedido por nota; o fornecedor que falta é cadastrado pelo próprio XML, com confirmação.
// O mesmo nas telas Estoque e movimentos e Compras e notas.
async function importarNotasXml(form, depois) {
  const arqs = [...form.arquivos.files], feitas = [], erros = [];
  for (const arq of arqs) {
    try {
      const corpo = { conteudo_b64: await lerOriginal(arq), nome: arq.name };
      let r = await api('/api/nf/importar-xml', corpo);
      if (r.fornecedor_novo) {
        const f = r.fornecedor_novo;
        if (!confirm(`NF ${r.numero}: o emitente ${f.nome} (CNPJ ${f.cnpj}) não está cadastrado. Cadastrar pelo XML e importar a nota?`)) continue;
        r = await api('/api/nf/importar-xml', { ...corpo, cadastrar_fornecedor: true });
      }
      feitas.push(`NF ${r.numero}`);
    } catch (e) { erros.push(`${arq.name}: ${e.message}`); }
  }
  if (feitas.length) toast(`Importada${feitas.length > 1 ? 's' : ''}: ${feitas.join(', ')}. Confira as linhas antes de receber.`, 'ok');
  if (erros.length) toast(erros.join(' · '), 'erro');
  form.reset(); depois(); driveEmSegundoPlano(depois);
}
$('#fXmlAlmox').addEventListener('submit', ev => { ev.preventDefault(); importarNotasXml(ev.target, carregarAlmox); });
$('#notasReceber').addEventListener('click', async ev => {
  const q = s => ev.target.closest(s);
  let r = null;
  if (q('[data-nota-conferir]')) {
    const box = q('.nota-conf');
    const linhas = $$('[data-l]', box).map(l => { const m = $('[data-k=material_id]', l).value.trim();
      return m ? { linha_id: l.dataset.l, material_id: m, fator: $('[data-k=fator]', l).value || null } : { linha_id: l.dataset.l, fora_do_estoque: true }; });
    r = await acao(() => api('/api/nf/conferir', { nf_id: q('[data-nota-conferir]').dataset.notaConferir, pedido_id: $('[data-c=pedido]', box).value || 0, linhas }),
      'Nota conferida: registre o que chegou.').catch(() => null);
  } else if (q('[data-nota-receber]')) {
    const box = q('.nota-chegou'), itens = $$('[data-ni]', box).map(l => ({ nf_item_id: l.dataset.ni, quantidade: +$('[data-chegou]', l).value || 0 })).filter(i => i.quantidade > 0);
    r = await acao(() => api('/api/recebimento', { nf_id: q('[data-nota-receber]').dataset.notaReceber, data: hoje(), itens, documento: $('[data-doc-entrega]', box).value }),
      'Entrega registrada: o material está em quarentena (o tubo da Caesb entrou como romaneio).').catch(() => null);
  } else if (q('[data-nota-aceitar]') || q('[data-nota-inspecionar]')) {
    const box = q('.nota-insp'), tudo = !!q('[data-nota-aceitar]');
    const itens = tudo ? [] : $$('[data-ri]', box).map(l => ({ recebimento_item_id: l.dataset.ri, aceito: $('[data-k=aceito]', l).value, recusado: $('[data-k=recusado]', l).value }));
    r = await acao(() => api('/api/inspecao/entrega', { recebimento_id: box.dataset.rec, itens, laudo: $('[data-laudo]', box).value, motivo_recusa: $('[data-motivo]', box).value, data: hoje() }),
      tudo ? 'Entrega aceita: o material entrou no estoque.' : 'Inspeção registrada: o aceito entrou no estoque e o recusado ficou de fora.').catch(() => null);
  } else if (q('[data-nota-aprovar]')) {
    r = await acao(() => api('/api/nf/aprovar', { nf_id: q('[data-nota-aprovar]').dataset.notaAprovar }), 'Nota aprovada: o material aceito já pode ser liberado às equipes.').catch(() => null);
  } else return;
  if (r) { carregarAlmox(); driveEmSegundoPlano(); }
});
function renderEstoque() {
  const f = $('#estFiltro').value, so = $('#estSaldo').checked;
  const lst = MATERIAIS.filter(m => (!f || m.propriedade === f) && (!so || m.saldo_almox || m.custodia || m.quarentena || m.reservado || m.aguardando_aprovacao));
  $('#estoque').innerHTML = lst.length ? `<table><thead><tr><th>Material</th><th>Propriedade</th><th>Unid.</th><th class="n">Saldo físico</th><th class="n">Reservado</th><th class="n">Disponível</th><th class="n">Quarentena</th><th class="n">Aguardando aprovação da nota</th><th class="n">Com as equipes</th><th class="n">Preço BM</th></tr></thead><tbody>
    ${lst.map(m => `<tr><td>${esc(m.id)} — ${esc(m.descricao.slice(0, 80))}</td><td><span class="chip ${m.propriedade === 'CAESB' ? 'azul' : m.propriedade === 'ANKARA' ? 'laranja' : ''}">${m.propriedade}</span></td><td>${esc(m.unidade)}</td>
      <td class="n">${nf(m.saldo_almox, 3)}</td><td class="n">${nf(m.reservado, 3)}</td><td class="n"><b>${nf(m.disponivel, 3)}</b></td><td class="n">${nf(m.quarentena, 3)}</td><td class="n">${m.aguardando_aprovacao ? `<span class="chip amarelo">${nf(m.aguardando_aprovacao, 3)}</span>` : '—'}</td><td class="n">${nf(m.custodia, 3)}</td><td class="n">${m.propriedade === 'CAESB' ? 'R$ 0,00' : brl(m.preco_unitario)}</td></tr>`).join('')}</tbody></table>`
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

async function carregarHistograma() {
  const h = await api(`/api/histograma?ini=${$('#hIni').value}&fim=${$('#hFim').value}`);
  const mx = Math.max(1, ...h.map(x => x.funcionarios + x.maquinas));
  $('#histograma').innerHTML = h.length ? `<table><thead><tr><th>Data</th><th>Equipe</th><th>Pessoas</th><th>Máquinas</th></tr></thead><tbody>${h.map(x => `<tr><td>${esc(x.data)}</td><td>${esc(x.equipe_id)}</td>
    <td>${x.funcionarios} <div class="barra" style="width:${x.funcionarios / mx * 100}%"></div></td><td>${x.maquinas} <div class="barra maq" style="width:${x.maquinas / mx * 100}%"></div></td></tr>`).join('')}</tbody></table>` : '<span class="vazio">Sem check-ins no período.</span>';
}
$('#hIni').addEventListener('change', carregarHistograma);
$('#hFim').addEventListener('change', carregarHistograma);

const maisDias = (d, n) => { const x = new Date(d + 'T12:00:00'); x.setDate(x.getDate() + n); return x.toISOString().slice(0, 10); };

/* ---------------------------------------------------------------- 2.1 compras & recebimento */
let COMPRAS = null;
const opMat = f => MATERIAIS.filter(f).map(m => `<option value="${esc(m.id)}">${esc(m.id)} — ${esc(m.descricao.slice(0, 48))} (${esc(m.unidade)})</option>`).join('');
const LINHA_ITEM = {
  solic: () => `<div class="linha lin-iv lin-item"><select data-k="material_id">${opMat(m => m.propriedade !== 'CAESB')}</select><input data-k="quantidade" type="number" step="any" min="0" placeholder="quantidade"><button type="button" class="btn" data-remover-linha>×</button></div>`,
  nfdig: () => `<div class="linha lin-iv lin-item"><input data-k="descricao" placeholder="descrição na nota"><input data-k="unidade" placeholder="unid." style="max-width:80px"><input data-k="quantidade" type="number" step="any" min="0" placeholder="qtd."><input data-k="valor_unitario" type="number" step="any" min="0" placeholder="valor unit."><button type="button" class="btn" data-remover-linha>×</button></div>`,
  inv: () => `<div class="linha lin-iv lin-item"><select data-k="material_id">${opMat(() => true)}</select><input data-k="contado" type="number" step="any" min="0" placeholder="contado"><button type="button" class="btn" data-remover-linha>×</button></div>`,
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
      ${['A_CONFERIR', 'CONFERIDA'].includes(n.status) && pode('receber') && !n.itens.some(i => i.recebido > 0) ? ` <button type="button" class="btn" data-cancelar-nf="${n.id}">Cancelar</button>` : ''}</span></div>${htmlDrive(n.drive)}${corpo}</div>`;
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
$('#fXml').addEventListener('submit', ev => { ev.preventDefault(); importarNotasXml(ev.target, carregarCompras); });
$('#fNfDig').addEventListener('submit', async ev => {
  ev.preventDefault(); const o = formObj(ev.target), arq = ev.target.arquivo.files[0];
  const r = await acao(async () => api('/api/nf/digitar', { numero: o.numero, data_emissao: o.data_emissao, fornecedor_id: o.fornecedor_id, chave: o.chave,
    linhas: lerItens(ev.target, 'nfdig'), documento_b64: await lerOriginal(arq), documento_tipo: arq.type === 'application/pdf' ? 'NF_PDF' : 'NF_IMAGEM', documento_nome: arq.name }), 'Nota registrada: outra pessoa confere contra o anexo.').catch(() => null);
  if (r) { ev.target.reset(); $('.editor-itens[data-itens=nfdig]').innerHTML = ''; carregarCompras(); driveEmSegundoPlano(carregarCompras); }
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
    r = await acao(() => api('/api/inspecao', { recebimento_item_id: l.dataset.ri, ...o, data: hoje() }), 'Inspeção registrada: o aceito entrou no estoque.').catch(() => null);
    if (r) driveEmSegundoPlano(); }
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
  ndAlvoEscolhido(d.nome || id);
  $('#apMetros').style.display = tipo === 'TRECHO' ? '' : 'none';
  const iv = d.intervalos;
  const editavel = tipo === 'TRECHO' && !(d.execucao && d.execucao.ok_fiscal_em);
  $('#apAlvo').innerHTML = tipo === 'TRECHO'
    ? `<div class="aviso info">${esc(nomeCompleto(d.nome))}: ${nf(d.extensao_m)} m · DE${d.de_mm} · ${esc(d.metodologia)}${d.perfil_bloqueado ? ' · <b>perfil bloqueado (E06)</b>' : ''} ${chipVerif(iv.verificacao)}
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
      <h4 style="margin:10px 0 4px">Topografia e cadastro de campo <small>(equipes terceirizadas, registrados pela engenharia)</small></h4>
      ${htmlTerceirizadas(d)}${(d.complementar.alertas || []).map(a => `<div class="aviso info">${esc(a)}</div>`).join('')}
      ${d.mnd ? '' : `<h4 style="margin:10px 0 4px">Escavação <small>(vala aberta; não gera quantidade)</small></h4>
      ${htmlComplementar(d.complementar, pode('retificar_campo'), ['ESCAVADO'])}`}
      ${editavel && !d.mnd ? `<div class="linha lin-compl" id="fCompl" style="margin-top:6px">
        <input data-c="ini_m" type="number" step="any" min="0" placeholder="escavado de (m)"><input data-c="fim_m" type="number" step="any" min="0" placeholder="até (m)">
        <input data-c="referencia" placeholder="observação (opcional)"><button type="button" class="btn" id="complBtn">Registrar escavação</button></div>` : ''}`
    : `<div class="aviso info">${esc(nomeCompleto(d.nome))}: ${esc(d.texto)}</div>`;
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
    const ok = await acao(() => api('/api/escavacao', { trecho_id: id, ini_m: o.ini_m, fim_m: o.fim_m, referencia: o.referencia, data: f.data || hoje() }), 'Escavação registrada.').catch(() => null);
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
    if (ok && TELA === 'topografia') { if (TOP) selecionarTop(TOP.id); carregarTopografia(); recarregarCamadaMapa(); }
    else if (ok && CAMPO) selecionarCampo(CAMPO.tipo, CAMPO.id); }
  if (r) { const resolucao = prompt('Resolução / correção feita:'); if (!resolucao) return;
    const ok = await acao(() => api('/api/ocorrencia/resolver', { ocorrencia_id: r.dataset.resolverOcorrencia, resolucao }), 'Ocorrência resolvida.').catch(() => null);
    if (ok && CAMPO) selecionarCampo(CAMPO.tipo, CAMPO.id); }
});
// retificação de intervalos: no Lançamento do dia (CAMPO) ou na aba Cadastro de campo (CADC)
const ctxRetif = el => el.closest('#aba-cadastro_campo') ? (CADC && { d: CADC.d, box: $('#cadRetif'), depois: () => selecionarCad(CADC.id) })
  : CAMPO && { d: CAMPO.d, box: $('#retifBox'), depois: () => selecionarCampo(CAMPO.tipo, CAMPO.id) };
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-retificar-ref]'), c = b && ctxRetif(b); if (!c) return;
  const [ref_tipo, ref_id] = b.dataset.retificarRef.split('|');
  const iv = c.d.intervalos, g = iv.registros.find(x => x.ref_tipo === ref_tipo && String(x.ref_id) === ref_id);
  const conc = ref_tipo === 'CONCILIACAO', cad = ref_tipo === 'CADASTRO_CAMPO';
  const etapas = conc ? (c.d.mnd ? ['ASSENTADO'] : ['ASSENTADO', 'REATERRADO']) : cad ? ['CADASTRO_CAMPO'] : Object.keys(iv.etapas);
  c.box.innerHTML = `<div class="caixa-retif" data-ref="${ref_tipo}|${ref_id}">
    <b>Retificar ${conc ? 'conciliação do legado' : cad ? 'cadastro de campo' : 'apontamento'} #${ref_id}</b> — informe o conjunto CORRETO de intervalos deste registro (linha vazia ou removida = intervalo anulado).
    ${conc ? 'A soma por etapa continua igual à da conciliação; não há quantidades.' : cad ? 'Cada intervalo precisa do registro do levantamento; não há quantidades.' : 'As quantidades do apontamento são recalculadas sem dupla contagem (veja a prévia).'}
    <div class="editor" data-etapas="${etapas.join(',')}" ${conc ? 'data-com-data="1"' : ''}>${g.intervalos.map(i => linhaIntervalo(etapas, i, conc, !conc)).join('')}</div>
    <button type="button" class="btn" data-mais-linha>+ intervalo</button>
    <div class="linha">${conc ? '' : `<label>${cad ? 'Data do levantamento' : 'Data do apontamento'}<input type="date" data-r="data" value="${esc(g.intervalos[0].data)}"></label>`}
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
  if (!corpo.simular) { const c = ctxRetif(b); if (c) c.depois(); if (TELA === 'cadastro_campo') carregarCadCampo(); recarregarCamadaMapa(); return; }
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
    <figcaption>${esc(f.categoria)} · ${esc(f.data_hora)} <small>(data: ${esc(f.origem_data || '—')}${f.origem_gps ? ' · GPS: ' + esc(f.origem_gps) : ''}${f.sha256 ? ' · sha256 ' + esc(f.sha256.slice(0, 12)) + '…' : ''})</small>${htmlDrive(f.drive)}</figcaption></figure>`).join('');
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
  const intervalos = [['ASSENTADO', 'ass'], ['REATERRADO', 'rea']]
    .filter(([, k]) => o[k + '_ini'] !== '' && o[k + '_fim'] !== '' && o[k + '_ini'] != null)
    .map(([etapa, k]) => ({ etapa, ini_m: +o[k + '_ini'], fim_m: +o[k + '_fim'] }));
  await acao(() => api('/api/apontamento', { data: o.data, equipe_id: o.equipe_id, alvo_tipo: CAMPO.tipo, alvo_id: CAMPO.id,
    concluido_100: !!o.concluido_100, intervalos: o.concluido_100 ? null : intervalos,
    estaca_ini: o.estaca_ini, estaca_fim: o.estaca_fim, quantidades, motivo_sem_ns: o.motivo_sem_ns }), 'Apontamento registrado.');
  $('#apQuant').innerHTML = ''; ['ass', 'rea'].forEach(k => { $(`input[name=${k}_ini]`, fAp).value = ''; $(`input[name=${k}_fim]`, fAp).value = ''; });
  $('input[name=concluido_100]', fAp).checked = false;
  selecionarCampo(CAMPO.tipo, CAMPO.id);
}

document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-verificar-intervalo]'); if (!b) return;
  if (!confirm(`Confirmar que você (${USUARIO.login}) conferiu este intervalo em campo? Quem informou não pode verificar.`)) return;
  const r = await acao(() => api('/api/intervalo/verificar', { intervalo_id: b.dataset.verificarIntervalo }), 'Intervalo verificado (conferência interna).').catch(() => null);
  const c = r && ctxRetif(b);
  if (c) { c.depois(); recarregarCamadaMapa(); }
});
function renderSoldas() {
  if (!CAMPO || !$('#soldas')) return;
  const s = CAMPO.d.soldas;
  $('#soldas').innerHTML = `<p style="margin:4px 0">${s.estimativa_barras_6m != null ? `Estimativa ⌈L/6⌉: <b>${s.estimativa_barras_6m}</b> (só referência) · ` : ''}Informadas <b>${s.informadas}</b> · aprovadas ${s.aprovadas} · reprovadas ${s.reprovadas} · sem verificação ${s.sem_verificacao}</p>
    ${s.registros.map(r => `<div><small>${esc(r.data)} · ${r.quantidade} ${esc(r.tipo)}${r.posicao_m != null ? ' @ ' + nf(r.posicao_m) + ' m' : ''} · ${esc(r.soldador)} · inf. ${esc(r.informado_por)}</small>
      ${r.verificado_em ? `<span class="chip ${r.resultado === 'APROVADA' ? 'verde' : 'vermelho'}">${esc(r.resultado)} · ${esc(r.verificado_por)}</span>` : pode('verificar') ? `<button type="button" class="btn" data-verificar-solda="${r.id}">Verificar</button>` : '<span class="chip amarelo">sem verificação</span>'}</div>`).join('')}`;
}
$('#fSolda').addEventListener('submit', async ev => {
  ev.preventDefault(); if (!CAMPO) return toast('Escolha o trecho ou o nó das soldas.', 'erro');
  const o = formObj(ev.target), d = formObj(fAp);
  const r = await acao(() => api('/api/solda', { ...o, data: d.data || hoje(), equipe_id: $('#ndEquipe').value || d.equipe_id || null, alvo_tipo: CAMPO.tipo, alvo_id: CAMPO.id }), 'Soldas registradas (aguardam verificação).').catch(() => null);
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
  if (!CAMPO) return toast('Escolha o trecho ou o nó da foto.', 'erro');
  const f = ev.target, arq = f.arquivo.files[0], cat = f.categoria.value;
  const pos = await gps(), quando = new Date(arq.lastModified || Date.now()), dh = new Date(quando - quando.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
  const b64 = await lerOriginal(arq);
  await acao(() => api('/api/foto', { alvo_tipo: CAMPO.tipo, alvo_id: CAMPO.id, categoria: cat, conteudo_b64: b64, data_hora: dh, lat: pos && pos.lat, lon: pos && pos.lon }), 'Foto original enviada (hash registrado).').catch(() => null);
  f.reset(); selecionarCampo(CAMPO.tipo, CAMPO.id);
  driveEmSegundoPlano(() => CAMPO && selecionarCampo(CAMPO.tipo, CAMPO.id));
});

/* ---------------------------------------------------------------- 4. caminho até a medição (ficha do trecho) */
// O que já foi feito e o que falta para o trecho entrar na medição, cada item com quem faz e onde, e a ação ali mesmo
// para quem pode: Verificar (com as fotos que faltam), OK interno e a esteira do cadastro. Serve à ficha do Mapa
// iluminado e à do Dados da obra.
const CAMPOS_ETAPA = {
  '1_PRONTO': [['2_ENVIADO', 'Enviar dados p/ empresa', [['empresa', 'Empresa'], ['data_envio', 'Data', 'date']]]],
  '2_ENVIADO': [['3_RECEBIDO', 'Cadastro recebido', [['arquivos', 'Arquivos DWG/PDF/BIM']]]],
  '3_RECEBIDO': [['4_GDOC_ANALISE', 'Catalogar no GDOC', [['protocolo_gdoc', 'Nº protocolo GDOC']]],
    ['2_ENVIADO', 'Devolver à empresa (conferência não conforme)', []]],
  '4_GDOC_ANALISE': [['6_APROVADO', 'Aprovado', [['memorando_eset', 'Memorando ESET']]], ['5A_NEGADO', 'Negado', [['motivo_negativa', 'Motivo da negativa']]]],
  '5A_NEGADO': [['2_ENVIADO', 'Reenviar p/ empresa ajustar', []]],
};
const camposFoto = faltam => `<div class="linha">${faltam.map(c => `<label>Foto: ${FOTO_NOME[c] || esc(c)}<input type="file" accept="image/*" data-foto="${c}"></label>`).join('')}</div>`;
async function montarCaminho(box, nome, depois) {
  if (!box) return;
  const cam = await api('/api/caminho?trecho=' + encodeURIComponent(nome)).catch(e => ({ erro: e.message }));
  if (cam.erro) { box.innerHTML = `<p class="vazio">${esc(cam.erro)}</p>`; return; }
  const it = Object.fromEntries(cam.itens.map(i => [i.id, i])), faltam = it.fotos.faltam || [];
  const verificar = !it.verificacao.feito && it.verificacao.pendentes > 0 && pode('verificar');
  const acao = {
    verificacao: verificar ? (faltam.length && pode('campo') ? camposFoto(faltam) : '')
      + `<div class="acoes"><button type="button" class="btn prim" data-cam="verificar">Verificar${faltam.length && pode('campo') ? ' e enviar as fotos escolhidas' : ''}</button></div>` : '',
    fotos: !it.fotos.feito && !verificar && pode('campo') ? camposFoto(faltam) + '<div class="acoes"><button type="button" class="btn" data-cam="fotos">Enviar as fotos</button></div>' : '',
    ok: it.ok.feito || !pode('ok_interno') ? '' : cam.pronto_para_ok
      ? '<div class="acoes"><button type="button" class="btn ok" data-cam="ok">OK interno</button></div>'
      : `<small>Falta para o OK: ${esc(cam.falta_para_ok.join(', ').toLowerCase())}.</small>`,
  };
  box.innerHTML = `<h3>Para entrar na medição</h3><ol class="caminho">${cam.itens.map(i => `<li class="${i.feito ? 'feito' : 'falta'}">
      <span class="marca" aria-hidden="true">${i.feito ? '✓' : ''}</span><div><b>${esc(i.nome)}</b><br><small>${esc(i.detalhe)}</small>
      ${i.feito ? '' : `<br><small class="quem">${esc(i.quem)} · ${esc(i.onde)}</small>`}${acao[i.id] || ''}</div></li>`).join('')}</ol>
    ${await htmlEsteira(cam)}`;
  box.dataset.trecho = nome; box.dataset.tid = cam.trecho_id; box.depois = depois;
  if (!box.dataset.ligado) { box.dataset.ligado = '1'; box.addEventListener('click', cliqueCaminho); box.addEventListener('submit', enviarEsteira); }
}
// a esteira do cadastro, para quem tem a permissão cadastro; a mesma ação vale para os outros trechos marcados na mesma etapa
async function htmlEsteira(cam) {
  const c = cam.cadastro; if (!c) return '';
  const cab = `<h3>Cadastro: ${esc(c.rotulo)}</h3>${c.empresa ? `<small>Empresa: ${esc(c.empresa)}</small> ` : ''}${c.protocolo_gdoc ? `<small>GDOC: ${esc(c.protocolo_gdoc)}</small> ` : ''}${c.memorando_eset ? `<small>ESET: ${esc(c.memorando_eset)}</small>` : ''}
    ${c.motivo_negativa ? `<div class="aviso problema">${esc(c.motivo_negativa)}</div>` : ''}
    ${c.conferencia ? `<div><span class="chip ${c.conferencia.resultado === 'CONFORME' ? 'azul' : 'vermelho'}" title="conferência interna Ankara: não é aprovação da Caesb">Rev. ${c.conferencia.revisao}: ${c.conferencia.resultado === 'CONFORME' ? 'conforme' : 'não conforme'} (interno) · ${esc(c.conferencia.revisor)}</span></div>` : ''}`;
  if (!pode('cadastro') && !pode('conferir_cadastro')) return `<div class="esteira-ficha">${cab}</div>`;
  const k = c.etapa;
  const outros = pode('cadastro') && CAMPOS_ETAPA[k] ? (await api('/api/esteira').catch(() => [])).filter(x => x.etapa === k && x.trecho_id !== c.trecho_id) : [];
  const conf = k === '3_RECEBIDO' && pode('conferir_cadastro') ? `<details class="conf"><summary>Conferência interna Ankara (não é aprovação da Caesb)</summary>
      ${Object.entries(RESUMO.checklist_conferencia || {}).map(([ck, txt]) => `<label class="check"><input type="checkbox" data-ck="${ck}"> ${esc(txt)}</label>`).join('')}
      <input data-c="obs" placeholder="Divergência (obrigatória se não conforme)">
      <div class="acoes"><button type="button" class="btn" data-conf="CONFORME">Conforme</button><button type="button" class="btn" data-conf="NAO_CONFORME">Não conforme</button></div></details>` : '';
  const forms = pode('cadastro') ? (CAMPOS_ETAPA[k] || []).filter(([dest]) => k !== '3_RECEBIDO' || (dest === '2_ENVIADO') === !!(c.conferencia && c.conferencia.resultado === 'NAO_CONFORME'))
    .map(([dest, rot, campos]) => `<form class="form" data-dest="${dest}">${campos.map(([n, l, t]) => `<input name="${n}" placeholder="${l}" ${t ? `type="${t}"` : ''} required>`).join('')}
      <button class="btn ${dest === '5A_NEGADO' || (k === '3_RECEBIDO' && dest === '2_ENVIADO') ? '' : 'prim'}">${rot}</button></form>`).join('') : '';
  const junto = outros.length ? `<details class="junto"><summary>Aplicar também a outros trechos nesta etapa (${outros.length})</summary>
      ${outros.map(x => `<label class="check"><input type="checkbox" data-junto="${esc(x.trecho_id)}"> ${esc(nomeCompleto(x.ponto))}</label>`).join('')}</details>` : '';
  return `<div class="esteira-ficha">${cab}${conf}${forms}${forms ? junto : ''}</div>`;
}
async function enviarFotosCaminho(box) {
  let n = 0;
  for (const inp of $$('input[data-foto]', box)) {
    const arq = inp.files[0]; if (!arq) continue;
    const pos = await gps(), quando = new Date(arq.lastModified || Date.now()), dh = new Date(quando - quando.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
    await api('/api/foto', { alvo_tipo: 'TRECHO', alvo_id: box.dataset.trecho, categoria: inp.dataset.foto, conteudo_b64: await lerOriginal(arq),
      data_hora: dh, lat: pos && pos.lat, lon: pos && pos.lon });
    n++;
  }
  return n;
}
async function cliqueCaminho(ev) {
  const box = ev.currentTarget, bt = ev.target.closest('[data-cam], [data-conf]'); if (!bt) return;
  const trecho = box.dataset.trecho;
  let feito = null;
  if (bt.dataset.cam === 'verificar') {
    feito = await acao(async () => {
      const f = await enviarFotosCaminho(box), r = await api('/api/trecho/verificar', { trecho });
      return `Verificado: ${r.verificados} intervalo(s)${r.de_outra_pessoa ? `; ${r.de_outra_pessoa} informado(s) por você ficam para outra pessoa` : ''}${f ? ` · ${f} foto(s) enviada(s)` : ''}.`;
    }).catch(() => null);
  } else if (bt.dataset.cam === 'fotos') {
    feito = await acao(async () => { const f = await enviarFotosCaminho(box); if (!f) throw new Error('Escolha a foto que falta.'); return `${f} foto(s) enviada(s) (hash registrado).`; }).catch(() => null);
  } else if (bt.dataset.cam === 'ok') {
    if (!confirm('Confirmar o OK interno? Gera PROPOSTA de lançamentos na medição de TESTE e envia o trecho para a esteira do cadastro. Não é aprovação da Caesb.')) return;
    feito = await acao(async () => {
      const r = await api('/api/ok-fiscal', { alvo_tipo: 'TRECHO', alvo_id: trecho, data: hoje() });
      return r.medicao_id ? 'OK interno registrado: proposta lançada na medição de TESTE.' : 'OK interno registrado. Sem medição de teste aberta: os lançamentos entram sozinhos quando ela abrir.';
    }).catch(() => null);
  } else if (bt.dataset.conf) {
    const det = bt.closest('details.conf'), checklist = Object.fromEntries($$('[data-ck]', det).map(i => [i.dataset.ck, i.checked]));
    feito = await acao(() => api('/api/cadastro/conferencia', { trecho_id: box.dataset.tid, resultado: bt.dataset.conf, checklist, obs: $('[data-c=obs]', det).value }),
      'Conferência interna registrada (não é aprovação da Caesb).').catch(() => null);
  }
  if (feito) { if (typeof feito === 'string') toast(feito, 'ok'); if (box.depois) box.depois(); }
}
async function enviarEsteira(ev) {
  ev.preventDefault();
  const box = ev.currentTarget, f = ev.target, dados = formObj(f);
  if (dados.arquivos) dados.arquivos = dados.arquivos.split(/[;,]/).map(s => s.trim()).filter(Boolean);
  const ids = [box.dataset.tid, ...$$('input[data-junto]:checked', box).map(i => i.dataset.junto)], erros = [];
  for (const id of ids) {
    try { await api('/api/cadastro', { trecho_id: id, destino: f.dataset.dest, dados, data: hoje() }); } catch (e) { erros.push(e.message); }
  }
  if (erros.length < ids.length) toast(`Esteira atualizada: ${ids.length - erros.length} trecho(s).`, 'ok');
  if (erros.length) toast(erros.join(' · '), 'erro');
  if (box.depois) box.depois();
}

/* ---------------------------------------------------------------- 5. medição */
async function carregarMedicoes() {
  const ms = await api('/api/medicoes');
  if (!ms.length) carregarCaminhoMedicao(null);
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
// o resumo do topo: cada número abre a lista dos trechos no Mapa iluminado
const CAMINHO_NUM = [['ok_nesta', 'Com OK interno nesta medição'], ['ok_sem_medicao', 'Com OK interno, esperando a medição abrir'],
  ['prontos', 'Prontos para o OK interno'], ['aguardando_verificacao', 'Aguardando verificação'], ['sem_fotos', 'Executados sem as 3 fotos']];
let MED_CAMINHO = null;
async function carregarCaminhoMedicao(id) {
  const r = await api('/api/medicao/caminho' + (id ? '?id=' + id : '')).catch(() => null), box = $('#medCaminho');
  if (!r) return;
  MED_CAMINHO = r; box.className = 'numeros-caminho';
  box.innerHTML = CAMINHO_NUM.filter(([k]) => k !== 'ok_sem_medicao' || r[k].length).map(([k, rot]) =>
    `<button type="button" class="numero-caminho" data-med-lista="${k}" ${r[k].length ? '' : 'disabled'}><b>${nf(r[k].length, 0)}</b><span>${esc(rot)}</span></button>`).join('');
}
$('#medCaminho').addEventListener('click', ev => {
  const b = ev.target.closest('[data-med-lista]'); if (!b || !MED_CAMINHO) return;
  abrirListaIlu(CAMINHO_NUM.find(([k]) => k === b.dataset.medLista)[1], MED_CAMINHO[b.dataset.medLista]);
});
async function carregarMedicao() {
  const id = $('#medSel').value; if (!id) return;
  MEDICAO_ATUAL = +id;
  carregarCaminhoMedicao(id);
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
  aprCarregarRestricoes(id);
}
const SIT_REGRA = { 'CONFIRMADA': 'verde', 'PROVISÓRIA': 'amarelo', 'HIPÓTESE': 'amarelo', 'BLOQUEADA': 'vermelho', 'VÍNCULO INCOMPLETO': 'vermelho' };
const SIT_ELEG = { PROPOSTO_NESTA: ['verde', 'proposto nesta'], OK_SEM_MEDICAO: ['amarelo', 'OK interno, espera a medição abrir'], APTO_SEM_OK: ['amarelo', 'completo, sem OK interno'],
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
  $('#painelDrive').hidden = !pode('documentos');
  if (pode('documentos')) carregarDrive();
  $('#painelUsuarios').hidden = !pode('usuarios');
  if (pode('usuarios')) {
    const us = await api('/api/usuarios');
    $('#selPerfil').innerHTML = Object.entries(RESUMO.perfis).map(([k, p]) => `<option value="${k}">${esc(p.nome)}</option>`).join('');
    $('#usuariosLista').innerHTML = `<table><thead><tr><th>Login</th><th>Nome</th><th>Perfil</th><th>Equipe</th><th></th></tr></thead><tbody>${us.map(u => `<tr${u.ativo ? '' : ' style="opacity:.5"'}>
      <td>${esc(u.login)}</td><td>${esc(u.nome)}</td><td>${esc(u.perfil_nome)}</td><td>${esc(u.equipe_id || '')}</td>
      <td>${u.login === USUARIO.login ? '' : `<div class="acoes"><button type="button" class="btn" data-usr-ativo="${esc(u.login)}" data-v="${u.ativo ? 0 : 1}">${u.ativo ? 'Desativar' : 'Reativar'}</button><button type="button" class="btn" data-usr-senha="${esc(u.login)}">Nova senha</button>${u.tem_historico ? '' : `<button type="button" class="btn" data-usr-excluir="${esc(u.login)}">Excluir</button>`}</div>`}</td></tr>`).join('')}</tbody></table>
      <p class="vazio" style="margin:6px 0 0">Excluir aparece só para a conta que nunca registrou nada (criada por engano). Quem já tem histórico é desativado: perde o acesso e o histórico fica.</p>`;
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
  const a = ev.target.closest('[data-usr-ativo]'), s = ev.target.closest('[data-usr-senha]'), x = ev.target.closest('[data-usr-excluir]');
  if (a) { const r = await acao(() => api('/api/usuarios', { acao: 'alterar', login: a.dataset.usrAtivo, ativo: a.dataset.v === '1' }), 'Usuário atualizado.').catch(() => null); if (r) carregarAdmin(); }
  if (x) {
    if (!confirm(`Excluir a conta ${x.dataset.usrExcluir}? Só funciona se ela nunca registrou nada; se já tiver histórico, use Desativar.`)) return;
    const r = await acao(() => api('/api/usuarios', { acao: 'excluir', login: x.dataset.usrExcluir }), 'Conta excluída.').catch(() => null);
    if (r) carregarAdmin();
  }
  if (s) { const senha = prompt('Nova senha (mín. 10 caracteres) para ' + s.dataset.usrSenha + ':'); if (!senha) return;
    await acao(() => api('/api/usuarios', { acao: 'senha', login: s.dataset.usrSenha, senha }), 'Senha redefinida; as sessões dessa pessoa foram encerradas.').catch(() => null); }
});

const dataBR = d => d ? d.split('-').reverse().join('/') : '—';
// planilhas e mapa do projeto que vêm com o sistema (config/fontes.json): baixam do próprio servidor, sem Drive
const tamanho = b => b >= 1048576 ? `${nf(b / 1048576, 1)} MB` : `${nf(Math.max(1, Math.round(b / 1024)), 0)} KB`;
/* ---------------------------------------------------------------- Google Drive conectado: fotos e notas sobem sozinhas */
let DRIVE = null, DRIVE_EM_CURSO = false;
const htmlDrive = e => !e ? '' : e.status === 'ENVIADO'
  ? `<div class="no-drive">No Drive: <a href="${esc(e.pasta_link || '#')}" target="_blank" rel="noopener">${esc(e.caminho)}</a> · <a href="${esc(e.drive_link || '#')}" target="_blank" rel="noopener">abrir</a></div>`
  : e.status === 'ERRO' ? `<div class="no-drive erro">Drive: não enviado (${esc(e.ultimo_erro || 'erro')})</div>`
    : `<div class="no-drive">Drive: na fila para ${esc(e.caminho)}</div>`;
// depois de salvar uma foto ou uma nota, o servidor sobe a fila para o Drive; a tela não espera
async function driveEmSegundoPlano(depois) {
  if (DRIVE_EM_CURSO) return;
  DRIVE_EM_CURSO = true;
  try {
    const r = await api('/api/drive/processar', {});
    if (r && r.enviados && depois) depois();
    if (TELA === 'admin' && pode('documentos')) carregarDrive();
  } catch (_) { /* sem conexão agora: a fila sobe na próxima vez */ } finally { DRIVE_EM_CURSO = false; }
}
const linkPasta = id => `https://drive.google.com/drive/folders/${encodeURIComponent(id)}`;
async function carregarDrive() {
  const d = await api('/api/drive').catch(() => null); if (!d) return;
  DRIVE = d;
  const c = d.contagem;
  $('#driveEstado').innerHTML = d.conectado
    ? `<span class="chip verde">conectado</span> ${esc(d.conta || 'conta Google')} · ${d.pasta_id ? `<a href="${linkPasta(d.pasta_id)}" target="_blank" rel="noopener">abrir a pasta da obra no Drive</a>` : '<b>falta informar a pasta da obra</b>'}`
    : `<span class="chip amarelo">não conectado</span> ${d.configurado ? 'Falta clicar em Conectar com o Google.' : 'Falta ligar a conta Google da obra.'} As fotos e as notas ficam guardadas aqui e sobem quando a conexão existir.`;
  $('#driveContagem').textContent = `${nf(c.enviados, 0)} enviados · ${nf(c.na_fila, 0)} na fila · ${nf(c.com_erro, 0)} com erro`
    + (c.fotos_so_no_drive ? ` · ${nf(c.fotos_so_no_drive, 0)} foto(s) só no Drive (${tamanho(c.bytes_liberados)} liberados no servidor)` : '');
  $('#driveErro').hidden = !d.ultimo_erro; $('#driveErro').textContent = d.ultimo_erro || '';
  $('#driveRecentes').innerHTML = d.recentes.map(e => `<div class="drive-item">
      <span class="doc-tipo">${e.origem === 'FOTO' ? 'FOTO' : 'NOTA'}</span>
      <span><b>${e.drive_link ? `<a href="${esc(e.drive_link)}" target="_blank" rel="noopener">${esc(e.nome)}</a>` : esc(e.nome)}</b>
        <small>Pasta: ${e.pasta_link ? `<a href="${esc(e.pasta_link)}" target="_blank" rel="noopener">${esc(e.caminho)}</a>` : esc(e.caminho)}${e.status === 'ERRO' ? ` · <span class="chip vermelho">não enviado</span> ${esc(e.ultimo_erro || '')}` : ''}</small></span>
      ${e.status === 'ERRO' && pode('documentos') ? `<button type="button" class="btn" data-drive-reenviar="${e.id}">Tentar de novo</button>` : ''}</div>`).join('');
  $('#driveEnviar').hidden = !d.conectado || !c.na_fila;
  $('#driveGerenciar').hidden = !pode('documentos');
  if (pode('documentos')) {
    const f = $('#fDrive');
    f.cliente_id.value = d.cliente_id || '';
    f.cliente_segredo.placeholder = d.tem_segredo ? 'guardado (em branco mantém o atual)' : 'cole o segredo do cliente';
    if (!f.pasta_url.value && d.pasta_id) f.pasta_url.value = linkPasta(d.pasta_id);
    $('#driveRetorno').textContent = location.origin + d.retorno;
    $('#driveConectar').disabled = !d.configurado;
    $('#driveConectar').textContent = d.conectado ? 'Conectar de novo' : 'Conectar com o Google';
    $('#driveDesconectar').hidden = $('#driveTestar').hidden = !d.conectado;
    if (!d.conectado && !d.configurado) $('#driveGerenciar').open = true;
  }
}
$('#fDrive').addEventListener('submit', async ev => {
  ev.preventDefault();
  const r = await acao(() => api('/api/drive/config', formObj(ev.target)), 'Dados do Google salvos.').catch(() => null);
  if (r) { ev.target.cliente_segredo.value = ''; carregarDrive(); }
});
$('#driveConectar').addEventListener('click', async () => {
  const r = await acao(() => api('/api/drive/conectar', {})).catch(() => null);
  if (r && r.url) location.href = r.url;            // a página do Google pede a sua conta e a permissão do Drive
});
$('#driveTestar').addEventListener('click', async () => {
  const r = await acao(() => api('/api/drive/testar', {})).catch(() => null);
  if (r) toast(`Pasta encontrada no Drive: ${r.pasta} (conta ${r.conta}).`, 'ok');
});
$('#driveDesconectar').addEventListener('click', async () => {
  if (!confirm('Desconectar a conta Google? O que já foi enviado continua no Drive; os próximos arquivos ficam na fila.')) return;
  const r = await acao(() => api('/api/drive/desconectar', {}), 'Google Drive desconectado.').catch(() => null);
  if (r) carregarDrive();
});
$('#driveEnviar').addEventListener('click', async () => { $('#driveEnviar').disabled = true; await driveEmSegundoPlano(); $('#driveEnviar').disabled = false; carregarDrive(); });
$('#driveCopiar').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('#driveRetorno').textContent); toast('Endereço copiado.', 'ok'); } catch (_) { toast('Selecione e copie o endereço.', ''); }
});
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-drive-reenviar]'); if (!b) return;
  const r = await acao(() => api('/api/drive/reenviar', { envio_id: +b.dataset.driveReenviar })).catch(() => null);
  if (r) { await driveEmSegundoPlano(); carregarDrive(); }
});
async function carregarPlanilhas() {
  const ls = await api('/api/planilhas').catch(() => []);
  $('#painelPlanilhas').hidden = !ls.length;
  $('#planilhasLista').innerHTML = ls.map(a => `<a class="arquivo" href="${esc(a.url)}" download>
      <span class="doc-tipo">${esc(a.arquivo.split('.').pop().toUpperCase())}</span>
      <span><b>${esc(a.descricao)}</b><small>${esc(a.arquivo)} · ${tamanho(a.bytes)}</small></span><span class="seta">Baixar</span></a>`).join('');
}
/* ---------------------------------------------------------------- campo: diário do dia */
const ROT_CATEG = { INTERFERENCIA: 'Interferência', FALTA_MATERIAL: 'Falta de material', CHUVA: 'Chuva', LIBERACAO: 'Liberação', PROJETO: 'Projeto',
  SEGURANCA: 'Segurança', ACESSO: 'Acesso', OUTRO: 'Outro', EXECUCAO: 'Execução', MATERIAL: 'Material', SOLDA: 'Solda', CADASTRO: 'Cadastro',
  DOCUMENTO: 'Documento' };
const ROT_PRODUCAO = { ASSENTADO: 'Assentado', CADASTRO_CAMPO: 'Cadastro de campo', REATERRADO: 'Reaterrado' };
const PROG_EXEC = { PROGRAMADO_E_EXECUTADO: ['programado e executado', 'verde'], PROGRAMADO_SEM_EXECUCAO: ['programado, sem execução', 'amarelo'],
  EXECUTADO_SEM_PROGRAMACAO: ['executado fora da programação', 'azul'] };
const rotCateg = c => ROT_CATEG[c] || c;
const tabelaHtml = (cab, linhas) => `<div class="tabela"><table><thead><tr>${cab}</tr></thead><tbody>${linhas.join('')}</tbody></table></div>`;
function opcoesEquipe(sel, primeira) {
  if (sel.options.length < 2) sel.innerHTML = `<option value="">${primeira}</option>` + RESUMO.equipes.map(e => `<option value="${esc(e.id)}">${esc(e.nome)}</option>`).join('');
}
const somarDia = (d, n) => { const x = new Date(d + 'T12:00:00'); x.setDate(x.getDate() + n); return x.toISOString().slice(0, 10); };
async function carregarDiario() {
  const sel = $('#diaEquipe'); opcoesEquipe(sel, 'Todas as equipes');
  if (USUARIO.restrito_a_equipe) { sel.value = USUARIO.equipe_id; sel.disabled = true; }   // o encarregado vê a própria equipe
  if (!$('#diaData').value) $('#diaData').value = hoje();
  const q = new URLSearchParams({ data: $('#diaData').value }); if (sel.value) q.set('equipe', sel.value);
  const d = await acao(() => api('/api/diario?' + q)).catch(() => null); if (!d) return;
  const t = d.totais, fila = d.ns_dia.reduce((x, n) => x + n.fila.length, 0);
  $('#diaAlertas').innerHTML = d.alertas.map(a => `<div class="aviso problema">${esc(a)}</div>`).join('');
  $('#diaKpis').innerHTML = [['Notas do dia', nf(d.ns_dia.length, 0)], ['Aguardando a engenharia', nf(fila, 0)], ['Assentado', nf(t.assentado_m) + ' m'],
    ['Cadastro de campo', nf(t.cadastro_m) + ' m'], ['Reaterrado', nf(t.reaterrado_m) + ' m'],
    ['Soldas', nf(t.soldas, 0)], ['Fotos', nf(t.fotos, 0)], ['Ocorrências', nf(t.ocorrencias, 0)]].map(([k, v]) => `<div class="kpi"><span>${k}</span><b>${v}</b></div>`).join('');
  renderDiarioNs(d.ns_dia);
  $('#diaProgExec').innerHTML = d.programado_executado.length ? tabelaHtml('<th>Equipe</th><th>Trecho / nó</th><th>Programado</th><th>Executado</th><th></th>',
    d.programado_executado.map(x => `<tr><td>${esc(x.equipe_id)}</td><td>${esc(curto(x.nome))}</td><td>${esc(x.servicos.join(', ') || '—')}</td>
      <td>${Object.entries(x.executado).map(([e, m]) => `${esc((ROT_PRODUCAO[e] || e).toLowerCase())} ${nf(m)} m`).join(' · ') || '—'}</td>
      <td><span class="chip ${PROG_EXEC[x.situacao][1]}">${PROG_EXEC[x.situacao][0]}</span></td></tr>`))
    : '<p class="vazio">Nada programado nem executado neste dia.</p>';
  const nada = '<p class="vazio">Nada registrado neste dia.</p>';
  $('#diaEquipes').innerHTML = d.equipes.map(e => `<div class="dia-equipe"><b>${esc(e.nome)}</b>
      <span>Manhã: ${esc(e.clima.MANHA || '—')}</span><span>Tarde: ${esc(e.clima.TARDE || '—')}</span></div>`).join('') || '<p class="vazio">Nenhuma equipe registrou nada neste dia.</p>';
  $('#diaProducao').innerHTML = d.producao.length ? tabelaHtml('<th>Equipe</th><th>Trecho</th><th>Etapa</th><th class="n">De–até (m)</th><th class="n">Metros</th><th>Registro</th><th></th>',
    d.producao.map(p => `<tr><td>${esc(p.equipe_id || (p.etapa === 'CADASTRO_CAMPO' ? 'terceirizada' : '—'))}</td><td>${esc(curto(p.trecho))}</td><td>${esc(ROT_PRODUCAO[p.etapa] || p.etapa)}</td>
      <td class="n">${nf(p.ini_m)}–${nf(p.fim_m)}</td><td class="n"><b>${nf(p.metros)}</b></td><td><small>${esc([p.informado_por, p.referencia].filter(Boolean).join(' · '))}</small></td>
      <td>${p.verificado ? '<span class="chip verde">verificado</span>' : '<span class="chip cinza">informado</span>'}</td></tr>`)) : nada;
  $('#diaSoldas').innerHTML = d.soldas.length ? tabelaHtml('<th>Equipe</th><th>Trecho / nó</th><th>Tipo</th><th class="n">Qtd.</th><th>Soldador</th><th></th>',
    d.soldas.map(s => `<tr><td>${esc(s.equipe_id || '—')}</td><td>${esc(curto(s.alvo_nome))}</td><td>${s.tipo === 'TOPO' ? 'Topo' : 'Eletrofusão'}</td>
      <td class="n">${nf(s.quantidade, 0)}</td><td>${esc(s.soldador)}</td>
      <td>${s.resultado ? `<span class="chip ${s.resultado === 'APROVADA' ? 'verde' : 'vermelho'}">${s.resultado === 'APROVADA' ? 'aprovada' : 'reprovada'}</span>` : '<span class="chip cinza">sem verificação</span>'}</td></tr>`)) : nada;
  $('#diaFotos').innerHTML = d.fotos.map(f => `<figure class="foto-carimbo"><img src="/fotos/${encodeURIComponent(f.arquivo)}" alt="${esc(f.categoria)} · ${esc(f.alvo_nome)}" loading="lazy">
      <span class="carimbo">${esc(f.carimbo)}</span><figcaption>${esc(curto(f.alvo_nome))}</figcaption></figure>`).join('') || nada;
  $('#diaProg').innerHTML = d.programacoes.map(p => `<div class="dia-equipe"><b>${esc(p.equipe_id)}</b><span>${esc(p.servico_nome)} · ${esc(curto(p.alvo_nome))}</span>
      <span class="chip ${p.status === 'REALIZADA' ? 'verde' : p.status === 'PLANEJADA' ? 'azul' : 'cinza'}">${esc(p.status.toLowerCase().replace('_', ' '))}</span></div>`).join('') || '<p class="vazio">Nada programado para este dia.</p>';
  $('#diaCheckins').innerHTML = d.checkins.map(c => `<div class="registro"><div><b>${esc(c.equipe_id)}${c.alvo_nome ? ' · ' + esc(curto(c.alvo_nome)) : ''}</b>
      <span class="chip ${c.encerrado ? 'verde' : 'amarelo'}">${c.encerrado ? 'check-out feito' : 'em campo'}</span></div>
      <small>${nf(c.funcionarios, 0)} pessoa(s) · ${nf(c.maquinas, 0)} máquina(s)${c.contingencia ? ' · ' + esc(c.contingencia) : ''}</small>
      ${c.materiais.length ? `<div><small>${c.materiais.map(m => `${esc(m.tipo.toLowerCase())} ${nf(m.quantidade, 3)} ${esc(m.material_id)}`).join(' · ')}</small></div>` : ''}</div>`).join('') || '<p class="vazio">Nenhum check-in neste dia.</p>';
  $('#diaOcorrencias').innerHTML = d.ocorrencias.map(htmlInterf).join('') || '<p class="vazio">Nenhuma interferência ou ocorrência aberta neste dia.</p>';
  $('#diaApropriacoes').innerHTML = d.apropriacoes.map(a => aprHtml(a, false)).join('') || '<p class="vazio">Nenhuma apropriação direta neste dia.</p>';
  $('#painelDiaLib').hidden = !!d.equipe;
  $('#diaLiberacoes').innerHTML = d.liberacoes.map(l => `<div class="dia-equipe"><b>${esc(ROT_ETAPA[l.etapa] || l.etapa)}</b><span>${esc(curto(l.trecho))} · ${nf(l.ini_m)}–${nf(l.fim_m)} m</span>
      <small>${esc([l.registrado_por, l.referencia].filter(Boolean).join(' · '))}</small></div>`).join('') || nada;
}
$('#diaData').addEventListener('change', carregarDiario);
$('#diaEquipe').addEventListener('change', carregarDiario);
$('#diaAnterior').addEventListener('click', () => { $('#diaData').value = somarDia($('#diaData').value || hoje(), -1); carregarDiario(); });
$('#diaProximo').addEventListener('click', () => { $('#diaData').value = somarDia($('#diaData').value || hoje(), 1); carregarDiario(); });

/* ---------------------------------------------------------------- campo: interferências e ocorrências */
let INT_SITUACAO = '1';
function htmlInterf(o) {
  return `<div class="int-item${o.resolvida_em ? ' resolvida' : ''}"><div class="topo"><b>${esc(rotCateg(o.categoria))} · ${esc(curto(o.alvo_nome))}</b>
      ${o.resolvida_em ? '<span class="chip verde">resolvida</span>' : `<span class="chip amarelo">${o.tipo === 'IMPEDIMENTO' ? 'impedimento' : 'não conformidade'} · aberta</span>`}</div>
    <p>${esc(o.descricao)}</p>
    <small>#${o.id} · ${dataBR(o.data)} · ${esc(o.equipe_id || 'sem equipe')} · aberta por ${esc(o.aberta_por)}</small>
    ${o.resolvida_em ? `<p><small>Resolução (${esc(o.resolvida_por)}, ${dataBR(o.resolvida_em.slice(0, 10))}):</small> ${esc(o.resolucao)}</p>`
      : pode('verificar') ? `<div class="acoes" style="margin-top:8px"><button type="button" class="btn" data-int-resolver="${o.id}">Marcar como resolvida</button></div>` : ''}</div>`;
}
function catsInterf() {
  const c = $('#intCat');
  c.innerHTML = (RESUMO.categorias_ocorrencia[$('#intTipo').value] || []).map(x => `<option value="${x}">${esc(rotCateg(x))}</option>`).join('');
  if ($('#intTipo').value === 'IMPEDIMENTO') c.value = 'INTERFERENCIA';
}
const marcarSituacao = () => $$('#intSituacao button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.intSituacao === INT_SITUACAO)));
async function carregarInterferencias() {
  opcoesEquipe($('#intEquipe'), 'Todas as equipes');
  if ($('#intCategoria').options.length < 2) {
    $('#intCategoria').innerHTML = '<option value="">Todas</option>' + [...new Set(Object.values(RESUMO.categorias_ocorrencia).flat())]
      .map(c => `<option value="${c}">${esc(rotCateg(c))}</option>`).join('');
    catsInterf();
    if (USUARIO.restrito_a_equipe) $('#fInterf').equipe_id.value = USUARIO.equipe_id;
  }
  const q = new URLSearchParams();
  if (INT_SITUACAO) q.set('abertas', INT_SITUACAO);
  if ($('#intEquipe').value) q.set('equipe', $('#intEquipe').value);
  if ($('#intCategoria').value) q.set('categoria', $('#intCategoria').value);
  const r = await acao(() => api('/api/interferencias?' + q)).catch(() => null); if (!r) return;
  const k = r.contagem;
  $('#intContagem').textContent = `${nf(k.abertas, 0)} aberta(s), ${nf(k.interferencias_abertas, 0)} delas interferência · ${nf(k.resolvidas, 0)} resolvida(s)`;
  $('#intLista').innerHTML = r.ocorrencias.map(htmlInterf).join('') || `<p class="vazio">${INT_SITUACAO === '1' ? 'Nenhuma interferência ou ocorrência aberta.' : 'Nada encontrado com esses filtros.'}</p>`;
}
const fInt = $('#fInterf');
ligarBusca($('input[name=alvo_txt]', fInt));
$('#intTipo').addEventListener('change', catsInterf);
$('#intSituacao').addEventListener('click', ev => {
  const b = ev.target.closest('[data-int-situacao]'); if (!b) return;
  INT_SITUACAO = b.dataset.intSituacao; marcarSituacao(); carregarInterferencias();
});
$('#intEquipe').addEventListener('change', carregarInterferencias);
$('#intCategoria').addEventListener('change', carregarInterferencias);
fInt.addEventListener('submit', async ev => {
  ev.preventDefault();
  const o = formObj(fInt), inp = $('input[name=alvo_txt]', fInt);
  if (!inp.dataset.id) { toast('Escolha o trecho, nó ou caixa na lista que aparece enquanto você digita.', 'erro'); return; }
  const r = await acao(() => api('/api/ocorrencia', { alvo_tipo: inp.dataset.tipo, alvo_id: inp.dataset.id, tipo: o.tipo, categoria: o.categoria,
    descricao: o.descricao, data: o.data, equipe_id: o.equipe_id || null }), 'Interferência registrada.').catch(() => null);
  if (r) { fInt.descricao.value = ''; inp.value = ''; inp.dataset.id = ''; INT_SITUACAO = '1'; marcarSituacao(); carregarInterferencias(); }
});
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-int-resolver]'); if (!b) return;
  const resolucao = prompt('Como foi resolvida? Descreva o que foi feito.'); if (!resolucao) return;
  const r = await acao(() => api('/api/ocorrencia/resolver', { ocorrencia_id: +b.dataset.intResolver, resolucao }), 'Marcada como resolvida.').catch(() => null);
  if (r) TELA === 'diario' ? carregarDiario() : carregarInterferencias();
});

/* ---------------------------------------------------------------- campo: topografia e cadastro de campo (terceirizadas) */
// as duas equipes são terceirizadas e não entram no sistema: a engenharia (ou a administração) registra o que elas entregam
const kpi = ([k, v]) => `<div class="kpi"><span>${k}</span><b>${v}</b></div>`;
const opcoesFrente = sel => { if (sel.options.length < 2) sel.innerHTML += RESUMO.frentes.map(x => `<option>${esc(x)}</option>`).join(''); };
const foraDe = ([a, b], cob) => lacunasDe((cob || []).map(([c, d]) => [Math.max(c, a) - a, Math.min(d, b) - a]).filter(([c, d]) => d > c), b - a)
  .map(([c, d]) => [c + a, d + a]);
const ROT_SERVICO = { LOCACAO: 'Locação', ESCAVACAO: 'Escavação', ASSENTAMENTO: 'Assentamento' };
const botaoTrecho = (attr, tid, ponto) => `<button type="button" class="btn" ${attr}="${esc(tid)}" data-ponto="${esc(ponto)}">${esc(nomeCompleto(ponto))}</button>`;
// o trecho tocado no Resumo (Topografia) ou em "O que foi feito" (Cadastro): quem registra vai à página de envio, com a
// exceção aberta nesse trecho; quem só consulta vê o trecho no Mapa iluminado
async function abrirTrechoDaLista(b, tela, perm, selecionar, form) {
  if (!pode(perm)) return verNoMapa('TRECHO', b.dataset.ponto);
  await abrirAba(tela + '/enviar');
  await selecionar(b.dataset.topTrecho || b.dataset.cadTrecho); form.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
// "Ver no Mapa iluminado": a zona filtrada (ou a obra inteira)
function zonaNoMapa(frente) { verNoMapa('ZONA', /^(Zona\d\d|ADUTORA)$/.test(frente || '') ? frente : null); }
function preencherTrecho(form, d, id) {
  const inp = $('input[name=alvo_txt]', form); inp.value = nomeCompleto(d.nome); inp.dataset.tipo = 'TRECHO'; inp.dataset.id = id;
}

let TOP_LISTA = 'programados', TOP = null, TOP_DADOS = null;
const fTop = $('#fTop');
async function carregarTopografia() {
  if (!fTop.data.value) fTop.data.value = hoje();
  if (PAGINA.topografia === 'enviar') { prepararEnvioNs('TOPOGRAFIA'); $('#topExcecao').hidden = !pode('topografia'); return; }
  opcoesFrente($('#topFrente'));
  $$('#topLista button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.topLista === TOP_LISTA)));
  const f = $('#topFrente').value;
  const r = await acao(() => api('/api/topografia' + (f ? '?frente=' + encodeURIComponent(f) : ''))).catch(() => null); if (!r) return;
  TOP_DADOS = r; const t = r.totais;
  nsCarregarLista('TOPOGRAFIA', '#topNsLista');
  $('#topKpis').innerHTML = [['Trechos liberados', nf(t.trechos_liberados, 0)], ['Liberados em parte', nf(t.trechos_parciais, 0)],
    ['Metros liberados', nf(t.liberado_m) + ' m'], ['Programado sem liberação (7 dias)', nf(t.programados_sem_liberacao, 0)],
    ['Executado sem liberação', nf(t.executado_sem_liberacao_m) + ' m']].map(kpi).join('');
  renderTopLista();
}
function renderTopLista() {
  const r = TOP_DADOS; if (!r) return;
  const bt = (tid, ponto) => botaoTrecho('data-top-trecho', tid, ponto);
  const listas = {
    programados: () => r.programados_sem_liberacao.length ? tabelaHtml('<th>Dia</th><th>Equipe</th><th>Serviço</th><th>Trecho</th><th>Falta liberar (m)</th>',
      r.programados_sem_liberacao.map(p => `<tr><td>${dataBR(p.data)}</td><td>${esc(p.equipe_id)}</td><td>${esc(ROT_SERVICO[p.servico] || p.servico)}</td>
        <td>${bt(p.trecho_id, p.ponto)}</td><td>${faixa(p.falta)}</td></tr>`))
      : `<p class="vazio">Nada programado de ${dataBR(r.hoje)} a ${dataBR(r.ate)} sem liberação.</p>`,
    executados: () => r.executado_sem_liberacao.length ? tabelaHtml('<th>Trecho</th><th class="n">Sem liberação (m)</th><th>Onde e quando</th>',
      r.executado_sem_liberacao.map(x => `<tr><td>${bt(x.trecho_id, x.ponto)}</td><td class="n"><b>${nf(x.falta_m)}</b></td>
        <td><small>${x.faltas.map(f => `${esc(ROT_PRODUCAO[f.etapa] || ROT_ETAPA[f.etapa] || f.etapa)} ${faixa(f.faixas)} (${dataBR(f.data)})`).join('<br>')}</small></td></tr>`))
      : '<p class="vazio">Nada assentado ou escavado sem liberação até a data.</p>',
    parciais: () => r.parciais.length ? tabelaHtml('<th>Trecho</th><th class="n">Liberado</th><th>Falta liberar (m)</th>',
      r.parciais.map(x => `<tr><td>${bt(x.trecho_id, x.ponto)}</td><td class="n">${nf(x.liberado_m)} de ${nf(x.extensao_m)} m</td><td>${faixa(x.falta)}</td></tr>`))
      : '<p class="vazio">Nenhum trecho liberado só em parte.</p>',
    recentes: () => r.recentes.length ? tabelaHtml('<th>Data</th><th>Trecho</th><th class="n">De–até (m)</th><th>Nota de serviço</th><th>Registrado por</th><th></th>',
      r.recentes.map(x => `<tr${x.anulado_em ? ' style="opacity:.6"' : ''}><td>${dataBR(x.data)}</td><td>${bt(x.trecho_id, x.ponto)}</td>
        <td class="n">${nf(x.ini_m)}–${nf(x.fim_m)}</td><td>${esc(x.referencia || '—')}</td><td>${esc(x.registrado_por)}</td>
        <td>${x.anulado_em ? `<span class="chip cinza" title="${esc(x.anulado_motivo || '')}">anulada</span>`
          : pode('retificar_campo') ? `<button type="button" class="btn" data-anular-etapa="${x.id}">Anular</button>` : ''}</td></tr>`))
      : '<p class="vazio">Nenhuma liberação registrada.</p>',
  };
  $('#topConteudo').innerHTML = listas[TOP_LISTA]();
}
async function selecionarTop(id) {
  const d = await acao(() => api(`/api/detalhe?tipo=TRECHO&id=${encodeURIComponent(id)}`)).catch(() => null); if (!d) return;
  TOP = { id, d }; preencherTrecho(fTop, d, id);
  $('#topExcecao').open = true;                       // o detalhe do trecho (e anular) fica no painel da exceção
  $('#topAlvo').innerHTML = `<div class="aviso info">${esc(nomeCompleto(d.nome))}: ${nf(d.extensao_m)} m · ${esc(d.metodologia || '')}</div>
    ${htmlComplementar(d.complementar, pode('retificar_campo'), ['LIBERACAO_TOPOGRAFICA'])}
    ${(d.complementar.alertas || []).map(a => `<div class="aviso problema">${esc(a)}</div>`).join('')}`;
}
ligarBusca($('input[name=alvo_txt]', fTop), r => r.tipo === 'TRECHO' ? selecionarTop(r.id) : toast('A liberação topográfica é por trecho.', 'erro'));
$('#topFrente').addEventListener('change', carregarTopografia);
$('#topLista').addEventListener('click', ev => {
  const b = ev.target.closest('[data-top-lista]'); if (!b) return;
  TOP_LISTA = b.dataset.topLista; $$('#topLista button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); renderTopLista();
});
$('#topConteudo').addEventListener('click', ev => {
  const b = ev.target.closest('[data-top-trecho]'); if (b) abrirTrechoDaLista(b, 'topografia', 'topografia', selecionarTop, fTop);
});
$('#topMapa').addEventListener('click', () => zonaNoMapa($('#topFrente').value));
$('#topTodo').addEventListener('click', () => { if (!TOP) return toast('Escolha o trecho.', 'erro'); fTop.ini_m.value = 0; fTop.fim_m.value = TOP.d.extensao_m; });
$('#topFalta').addEventListener('click', () => {
  if (!TOP) return toast('Escolha o trecho.', 'erro');
  const f = lacunasDe(TOP.d.complementar.LIBERACAO_TOPOGRAFICA.cobertura, TOP.d.extensao_m)[0];
  if (!f) return toast('O trecho já está todo liberado.', 'ok');
  fTop.ini_m.value = +f[0].toFixed(3); fTop.fim_m.value = +f[1].toFixed(3);
});
fTop.addEventListener('submit', async ev => {
  ev.preventDefault();
  if (!TOP || $('input[name=alvo_txt]', fTop).dataset.id !== TOP.id) return toast('Escolha o trecho na lista que aparece enquanto você digita.', 'erro');
  const o = formObj(fTop);
  const r = await acao(() => api('/api/liberacao', { trecho_id: TOP.id, ini_m: o.ini_m, fim_m: o.fim_m, data: o.data, referencia: o.referencia }),
    'Liberação registrada.').catch(() => null);
  if (r) { fTop.ini_m.value = ''; fTop.fim_m.value = ''; fTop.referencia.value = ''; selecionarTop(TOP.id); carregarTopografia(); recarregarCamadaMapa(); }
});

let CAD_LISTA = 'aberta', CADC = null, CAD_DADOS = null;
const fCad = $('#fCad');
async function carregarCadCampo() {
  if (!fCad.data.value) fCad.data.value = hoje();
  if (PAGINA.cadastro_campo === 'enviar') { prepararEnvioNs('CADASTRO'); $('#cadExcecao').hidden = !pode('cadastro_campo'); return; }
  opcoesFrente($('#cadFrente'));
  $$('#cadLista button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.cadLista === CAD_LISTA)));
  const f = $('#cadFrente').value;
  const r = await acao(() => api('/api/cadastro-campo' + (f ? '?frente=' + encodeURIComponent(f) : ''))).catch(() => null); if (!r) return;
  CAD_DADOS = r; const t = r.totais;
  nsCarregarLista('CADASTRO', '#cadNsLista');
  $('#cadAviso').innerHTML = t.reaterrado_sem_cadastro_m > 0 ? `<div class="aviso problema"><b>${nf(t.reaterrado_sem_cadastro_m)} m já reaterrados sem levantamento.</b>
    Com a vala fechada não dá mais para levantar: veja a lista "Reaterrado sem levantamento".</div>` : '';
  $('#cadKpis').innerHTML = [['Vala aberta sem levantamento', nf(t.vala_aberta_m) + ' m'], ['Reaterrado sem levantamento', nf(t.reaterrado_sem_cadastro_m) + ' m'],
    ['Trechos pendentes', nf(t.trechos_pendentes, 0)], ['Reaterros com alerta', nf(t.alertas_reaterro, 0)],
    ['Trechos com levantamento completo', nf(t.trechos_completos, 0)]].map(kpi).join('');
  renderCadLista();
}
function renderCadLista() {
  const r = CAD_DADOS; if (!r) return;
  const bt = (tid, ponto) => botaoTrecho('data-cad-trecho', tid, ponto);
  const leg = x => x.legado_pendente ? ' <span class="chip vermelho" title="Concilie o avanço anterior antes de registrar">legado sem posição</span>' : '';
  const aberta = r.fila.filter(x => x.vala_aberta_m > 0), fechada = r.fila.filter(x => x.reaterrado_sem_cadastro_m > 0 || x.alertas_reaterro > 0);
  const listas = {
    aberta: () => aberta.length ? tabelaHtml('<th>Trecho</th><th class="n">Assentado</th><th class="n">Levantado</th><th>Falta levantar, vala aberta (m)</th>',
      aberta.map(x => `<tr><td>${bt(x.trecho_id, x.ponto)}${leg(x)}</td><td class="n">${nf(x.assentado_m)} m</td><td class="n">${nf(x.cadastro_m)} m</td>
        <td><b>${faixa(x.vala_aberta)}</b></td></tr>`))
      : '<p class="vazio">Nenhum trecho assentado esperando levantamento com a vala aberta.</p>',
    reaterrados: () => fechada.length ? tabelaHtml('<th>Trecho</th><th>Reaterrado sem levantamento (m)</th><th class="n">Reaterros com alerta</th>',
      fechada.map(x => `<tr><td>${bt(x.trecho_id, x.ponto)}${leg(x)}</td><td>${x.reaterrado_sem_cadastro.length ? faixa(x.reaterrado_sem_cadastro) : '<small>levantado depois do reaterro</small>'}</td>
        <td class="n">${x.alertas_reaterro ? `<span class="chip amarelo">${nf(x.alertas_reaterro, 0)}</span>` : '—'}</td></tr>`))
      : '<p class="vazio">Nenhum reaterro sem levantamento.</p>',
    recentes: () => r.recentes.length ? tabelaHtml('<th>Data</th><th>Trecho</th><th class="n">De–até (m)</th><th>Registro do levantamento</th><th>Registrado por</th><th></th>',
      r.recentes.map(x => `<tr${x.anulado_por ? ' style="opacity:.6"' : ''}><td>${dataBR(x.data)}</td><td>${bt(x.trecho_id, x.ponto)}</td>
        <td class="n">${nf(x.ini_m)}–${nf(x.fim_m)}</td><td>${esc(x.referencia || '—')}</td>
        <td>${esc(x.informado_por || '—')}${x.apontamento_id ? ` <small>(apontamento #${x.apontamento_id})</small>` : ''}</td>
        <td>${x.anulado_por ? `<span class="chip cinza">retificado (#${x.anulado_por})</span>` : x.verificado_em ? `<span class="chip azul">verificado · ${esc(x.verificado_por)}</span>` : '<span class="chip amarelo">sem verificação</span>'}</td></tr>`))
      : '<p class="vazio">Nenhum levantamento registrado.</p>',
  };
  $('#cadConteudo').innerHTML = listas[CAD_LISTA]();
}
async function selecionarCad(id) {
  const d = await acao(() => api(`/api/detalhe?tipo=TRECHO&id=${encodeURIComponent(id)}`)).catch(() => null); if (!d) return;
  CADC = { id, d }; preencherTrecho(fCad, d, id);
  $('#cadExcecao').open = true;
  const iv = d.intervalos, ass = iv.etapas.ASSENTADO, cad = iv.etapas.CADASTRO_CAMPO;
  const falta = ass.cobertura.flatMap(x => foraDe(x, cad.cobertura));
  $('#cadRetif').innerHTML = '';
  $('#cadAlvo').innerHTML = `<div class="aviso info">${esc(nomeCompleto(d.nome))}: ${nf(d.extensao_m)} m · ${esc(d.metodologia || '')} · assentado ${faixa(ass.cobertura)}</div>
    <div class="registro"><div><b>Levantado</b> <span class="chip ${falta.length ? 'amarelo' : cad.metros ? 'azul' : 'cinza'}">${nf(cad.metros)} m</span></div>
      <small>Levantado: ${faixa(cad.cobertura)}${falta.length ? ` · <b>assentado sem levantamento: ${faixa(falta)}</b>` : ''}</small></div>
    ${htmlFases((d.fases_cadastro || []).slice(0, 1))}
    <h4 style="margin:10px 0 4px">Levantamentos registrados nesta aba</h4>
    ${htmlRegistros({ ...iv, registros: iv.registros.filter(g => g.ref_tipo === 'CADASTRO_CAMPO') }, pode('retificar_campo'))}`;
}
ligarBusca($('input[name=alvo_txt]', fCad), r => r.tipo === 'TRECHO' ? selecionarCad(r.id) : toast('O cadastro de campo é por trecho.', 'erro'));
$('#cadFrente').addEventListener('change', carregarCadCampo);
$('#cadLista').addEventListener('click', ev => {
  const b = ev.target.closest('[data-cad-lista]'); if (!b) return;
  CAD_LISTA = b.dataset.cadLista; $$('#cadLista button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); renderCadLista();
});
$('#cadConteudo').addEventListener('click', ev => {
  const b = ev.target.closest('[data-cad-trecho]'); if (b) abrirTrechoDaLista(b, 'cadastro_campo', 'cadastro_campo', selecionarCad, fCad);
});
$('#cadMapa').addEventListener('click', () => zonaNoMapa($('#cadFrente').value));
$('#cadFalta').addEventListener('click', () => {
  if (!CADC) return toast('Escolha o trecho.', 'erro');
  const f = CADC.d.intervalos.etapas.ASSENTADO.cobertura.flatMap(x => foraDe(x, CADC.d.intervalos.etapas.CADASTRO_CAMPO.cobertura))[0];
  if (!f) return toast('Todo o assentado já tem levantamento.', 'ok');
  fCad.ini_m.value = +f[0].toFixed(3); fCad.fim_m.value = +f[1].toFixed(3);
});
fCad.addEventListener('submit', async ev => {
  ev.preventDefault();
  if (!CADC || $('input[name=alvo_txt]', fCad).dataset.id !== CADC.id) return toast('Escolha o trecho na lista que aparece enquanto você digita.', 'erro');
  const o = formObj(fCad);
  const r = await acao(() => api('/api/cadastro-campo', { trecho_id: CADC.id, ini_m: o.ini_m, fim_m: o.fim_m, data: o.data, referencia: o.referencia }),
    'Levantamento registrado.').catch(() => null);
  if (r) { fCad.ini_m.value = ''; fCad.fim_m.value = ''; fCad.referencia.value = ''; selecionarCad(CADC.id); carregarCadCampo(); recarregarCamadaMapa(); }
});

/* ---------------------------------------------------------------- LEV: as planilhas da obra como tabelas */
let LEV_ABA = 'cronograma', LEV_BUSCA_T = null;
const LEV_ROTA = { cronograma: () => '/api/lev/cronograma', bm: q => '/api/lev/bm?planilha=JUNTADA&' + q, vertical: q => '/api/lev/bm?planilha=VERTICAL&' + q,
  redes: q => '/api/lev/redes?' + q, conexoes: q => '/api/lev/conexoes?' + q };
const reais = v => v == null ? '—' : 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (v, c = 1) => v == null ? '—' : nf(v * 100, c) + '%';
async function carregarLev() {
  $$('#levAbas button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lev === LEV_ABA)));
  const fr = $('#levFrente');
  if (fr.options.length < 2) fr.innerHTML += RESUMO.frentes.map(x => `<option>${esc(x)}</option>`).join('');
  $('#levFiltros').hidden = !['bm', 'vertical', 'redes', 'conexoes'].includes(LEV_ABA);
  $('#levFrenteRot').hidden = !['redes', 'conexoes'].includes(LEV_ABA);
  $('#painelPlanilhas').hidden = LEV_ABA !== 'arquivos';
  const alvo = $('#levConteudo'), aba = LEV_ABA;
  if (aba === 'arquivos') { alvo.innerHTML = ''; return carregarPlanilhas(); }
  const q = new URLSearchParams();
  if ($('#levBusca').value.trim()) q.set('q', $('#levBusca').value.trim());
  if (['redes', 'conexoes'].includes(aba) && fr.value) q.set('frente', fr.value);
  alvo.innerHTML = '<p class="vazio">Carregando…</p>';
  const r = await acao(() => api(LEV_ROTA[aba](q))).catch(() => null);
  if (!r || aba !== LEV_ABA) return;                  // trocou de aba enquanto carregava
  alvo.innerHTML = { cronograma: htmlCronograma, bm: htmlBM, vertical: htmlBM, redes: htmlRedes, conexoes: htmlConexoes }[aba](r);
}
// período da planilha "01-10-26 A 31-10-26" → ['2026-10-01', '2026-10-31']
const datasDoPeriodo = p => String(p).split(' A ').map(x => { const [d, m, a] = x.trim().split('-'); return `20${a}-${m}-${d}`; });
function htmlCronograma(r) {
  const h = hoje(), datas = r.meses.map(m => datasDoPeriodo(m.periodo));
  const agora = datas.findIndex(([a, b]) => h >= a && h <= b);
  const acum = r.totais.find(t => t.descricao.startsWith('FATURAMENTO - ACUMULADO')) || {};
  const ate = agora >= 0 ? agora : h < datas[0][0] ? -1 : r.meses.length - 1;     // antes do início: nada programado
  const kpi = (k, v) => `<div class="kpi"><span>${k}</span><b>${v}</b></div>`;
  const val = (lst, i) => lst && i >= 0 ? lst[i] : null;
  const cab = r.meses.map((m, i) => `<th class="mes" title="${esc(m.periodo)} · ${nf(m.dias, 0)} dias">M${String(m.n).padStart(2, '0')}</th>`).join('');
  const linha = it => {
    const mx = Math.max(...(it.fis_prog || []).map(v => v || 0), 0) || 1;
    return `<tr class="n${Math.min(it.nivel, 1)}"><td>${esc(it.item)}</td><td class="desc">${esc(it.descricao)}</td><td class="n">${reais(it.valor)}</td><td class="n">${pct(it.peso, 2)}</td>
      ${r.meses.map((m, i) => { const p = val(it.fis_prog, i) || 0, e = val(it.fis_exec, i) || 0;
        return `<td class="mes${i === agora ? ' agora' : ''}" title="${esc(m.periodo)}: programado ${pct(p, 2)} · executado ${pct(e, 2)}"><span style="--p:${(p / mx).toFixed(3)}">${p ? nf(p * 100, 1) : ''}</span></td>`; }).join('')}</tr>`;
  };
  return `<div class="kpis">${kpi('Valor do contrato (programado)', reais(val(acum.fin_prog, r.meses.length - 1)))}${kpi('Prazo', `${nf(r.prazo_dias, 0)} dias · ${r.meses.length} meses`)}
      ${kpi(agora >= 0 ? `Programado até o mês ${agora + 1}` : 'Programado até hoje', pct(val(acum.fis_prog, ate)))}${kpi('Executado (planilha)', pct(val(acum.fis_exec, ate)))}</div>
    <div class="painel"><h3>Físico programado por mês (% de cada item)</h3>
      <p class="crono-legenda"><span>Fonte: ${esc(r.arquivo)} · aba CRONOGRAMA FF CAESB</span><span><i style="background:var(--laranja)"></i>mais forte = maior parte do item naquele mês</span>${agora >= 0 ? '<span><i style="outline:2px solid var(--azul);outline-offset:-2px"></i>mês atual</span>' : ''}</p>
      <div class="tabela crono"><table><thead><tr><th>Item</th><th>Descrição</th><th class="n">Valor</th><th class="n">Peso</th>${cab}</tr></thead>
        <tbody>${r.itens.map(linha).join('')}</tbody></table></div></div>
    <div class="painel" style="margin-top:16px"><h3>Curva acumulada da obra</h3>
      ${tabelaHtml('<th>Mês</th><th>Período</th><th class="n">Faturamento programado acumulado</th><th class="n">Físico programado acumulado</th><th class="n">Físico executado acumulado</th>',
        r.meses.map((m, i) => `<tr${i === agora ? ' style="font-weight:700"' : ''}><td>M${String(m.n).padStart(2, '0')}</td><td>${esc(m.periodo)}</td>
          <td class="n">${reais(val(acum.fin_prog, i))}</td><td class="n">${pct(val(acum.fis_prog, i))}</td><td class="n">${pct(val(acum.fis_exec, i))}</td></tr>`))}</div>`;
}
function htmlBM(r) {
  const vert = r.planilha === 'VERTICAL';
  let sub = null;
  const linhas = r.itens.flatMap(i => {
    const grupo = vert && i.subgrupo !== sub ? (sub = i.subgrupo, [`<tr class="grupo"><td colspan="8">${esc(i.subgrupo)} · ${esc(i.subgrupo_nome || '')}</td></tr>`]) : [];
    const sit = vert ? `<td><span class="chip ${i.situacao === 'APROVADO' ? 'verde' : 'vermelho'}">${esc(i.situacao === 'APROVADO' ? 'aprovado' : 'a aprovar')}</span>
      <br><small>${esc(i.origem_rotulo || '')}${i.codigo_oficial ? ' · oficial ' + esc(i.codigo_oficial) : ''}${i.conciliado ? ' · ' + esc(i.conciliado) : ''}</small></td>` : '';
    return [...grupo, `<tr><td>${esc(vert ? i.item_bm || i.item : i.item)}</td><td>${esc(i.codigo_caesb || '')}</td>${sit}<td>${esc(i.descricao)}</td><td>${esc(i.unidade || '')}</td>
      <td class="n">${nf(i.quantidade, 3)}</td><td class="n">${reais(i.preco_unitario)}</td><td class="n">${reais(i.valor_total)}</td></tr>`];
  });
  return `<div class="kpis"><div class="kpi"><span>Total ${vert ? 'BM Vertical' : 'BM'} (sem BDI)</span><b>${reais(r.total)}</b></div>
      ${Object.entries(r.por_classe).map(([k, v]) => `<div class="kpi"><span>${esc(k)}</span><b>${reais(v)}</b></div>`).join('')}
      <div class="kpi"><span>BDI material · serviço</span><b>${r.bdi == null ? '—' : pct(+r.bdi, 2)} · ${r.bdi_servico == null ? '—' : pct(+r.bdi_servico, 2)}</b></div></div>
    <p class="vazio" style="margin:0 0 8px">${nf(r.itens.length, 0)} itens${$('#levBusca').value.trim() ? ' encontrados' : ''}. Preços sem BDI (contrato, cláusula 5.2).</p>
    ${r.itens.length ? tabelaHtml(`<th>Item</th><th>Cód. Caesb</th>${vert ? '<th>Situação</th>' : ''}<th>Descrição</th><th>Und.</th><th class="n">Quantidade</th><th class="n">Preço unit.</th><th class="n">Total</th>`, linhas)
      : '<p class="vazio">Nenhum item com essa busca.</p>'}`;
}
function htmlRedes(r) {
  return `<div class="kpis"><div class="kpi"><span>Trechos</span><b>${nf(r.total_trechos, 0)}</b></div><div class="kpi"><span>Extensão</span><b>${nf(r.total_m)} m</b></div></div>
    <div class="painel"><h3>Resumo por diâmetro</h3>${tabelaHtml('<th class="n">DE (mm)</th><th>Material</th><th>Método</th><th class="n">Trechos</th><th class="n">Extensão (m)</th>',
      r.resumo.map(x => `<tr><td class="n">${nf(x.de_mm, 0)}</td><td>${esc(x.material || '—')}</td><td>${esc(x.metodologia || '—')}</td><td class="n">${nf(x.trechos, 0)}</td><td class="n">${nf(x.extensao_m)}</td></tr>`))}</div>
    <div class="painel" style="margin-top:16px"><h3>Trechos (06.1)</h3>
      ${r.mostrando < r.total_trechos ? `<p class="vazio" style="margin:0 0 8px">Mostrando ${nf(r.mostrando, 0)} de ${nf(r.total_trechos, 0)}: escolha a frente ou busque para afinar.</p>` : ''}
      ${tabelaHtml('<th>Trecho</th><th>Frente</th><th>PB</th><th>Prancha</th><th class="n">DE</th><th>Material</th><th>Método</th><th>Classe</th><th class="n">Extensão (m)</th><th>Nós</th><th>Cód. BM</th>',
        r.trechos.map(t => `<tr><td>${esc(curto(t.ponto))}</td><td>${esc(t.frente_id || '')}</td><td>${esc(t.pb || '')}</td><td>${esc(t.prancha || '')}</td><td class="n">${nf(t.de_mm, 0)}</td>
          <td>${esc(t.material || '')}</td><td>${esc(t.metodologia || '')}</td><td>${esc(t.classe || '')}</td><td class="n">${nf(t.extensao_m)}</td>
          <td><small>${esc([t.no_ini, t.no_fim].filter(Boolean).map(curto).join(' → '))}</small></td><td>${esc(t.codigo_bm || '')}</td></tr>`))}</div>`;
}
function htmlConexoes(r) {
  return `<div class="kpis"><div class="kpi"><span>Peças</span><b>${nf(r.total_itens, 0)}</b></div><div class="kpi"><span>Nós e caixas</span><b>${nf(r.total_nos, 0)}</b></div></div>
    <div class="painel"><h3>Resumo por peça</h3>${tabelaHtml('<th>Peça</th><th>DE</th><th>Und.</th><th>Cód. BM</th><th class="n">Nós</th><th class="n">Quantidade</th>',
      r.resumo.map(x => `<tr><td>${esc(x.descricao)}</td><td>${esc(x.diametro || '')}</td><td>${esc(x.unidade || '—')}</td><td>${esc(x.codigo_bm || '')}</td>
        <td class="n">${nf(x.nos, 0)}</td><td class="n">${nf(x.quantidade, 3)}</td></tr>`))}</div>
    <div class="painel" style="margin-top:16px"><h3>Peças por nó e caixa (06.2)</h3>
      ${r.mostrando < r.total_itens ? `<p class="vazio" style="margin:0 0 8px">Mostrando ${nf(r.mostrando, 0)} de ${nf(r.total_itens, 0)} peças: escolha a frente ou busque para afinar.</p>` : ''}
      ${tabelaHtml('<th>Nó / caixa</th><th>Frente</th><th>Peça</th><th>DE</th><th>PN</th><th>Material</th><th class="n">Qtd.</th><th>Und.</th><th>Cód. BM</th><th>Situação</th>',
        r.itens.map(i => `<tr><td>${esc(curto(i.nomenclatura))}</td><td>${esc(i.frente_id || '')}</td><td>${esc(i.descricao)}</td><td>${esc(i.diametro || '')}</td><td>${esc(i.pressao || '')}</td>
          <td>${esc(i.material || '')}</td><td class="n">${nf(i.quantidade, 3)}</td><td>${esc(i.unidade || '—')}</td><td>${esc(i.codigo_bm || '')}</td><td><small>${esc(i.status_conexao || '')}</small></td></tr>`))}</div>`;
}
$('#levAbas').addEventListener('click', ev => {
  const b = ev.target.closest('[data-lev]'); if (!b || b.dataset.lev === LEV_ABA) return;
  LEV_ABA = b.dataset.lev; $('#levBusca').value = ''; carregarLev();
});
$('#levBusca').addEventListener('input', () => { clearTimeout(LEV_BUSCA_T); LEV_BUSCA_T = setTimeout(carregarLev, 350); });
$('#levFrente').addEventListener('change', carregarLev);

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
const sair = async () => { await api('/api/logout', {}).catch(() => null); location.hash = ''; location.reload(); };
$('#sairBtn').addEventListener('click', sair);
$('#inicioSair').addEventListener('click', sair);
$('#senhaBtn').addEventListener('click', async () => {
  const atual = prompt('Senha atual:'); if (!atual) return;
  const nova = prompt('Nova senha (mín. 10 caracteres):'); if (!nova) return;
  await acao(() => api('/api/senha', { senha_atual: atual, nova_senha: nova }), 'Senha alterada.').catch(() => null);
});
function aplicarPermissoes() {
  const perfil = USUARIO.perfil_nome + (USUARIO.equipe_id ? ' · ' + USUARIO.equipe_id : '');
  $('#quemNome').textContent = $('#inicioNome').textContent = USUARIO.nome;
  $('#quemPerfil').textContent = $('#inicioPerfil').textContent = perfil;
  $('#railAvatar').textContent = $('#inicioAvatar').textContent = iniciais(USUARIO.nome);
  $('.rail-quem').title = `${USUARIO.nome} (${USUARIO.login})`;
  $('#sairBtn').hidden = $('#senhaBtn').hidden = false;
  $('#faixaDemo').hidden = $('#inicioPe').hidden = !DEMONSTRACAO;
  // a tela só indica o que o perfil pode fazer; quem decide é o servidor (403)
  $$('[data-perm]').forEach(el => { const ok = el.dataset.perm.split(' ').some(pode); el.toggleAttribute('data-sem-permissao', !ok); el.title = ok ? '' : 'Seu perfil não tem esta permissão'; });
  // o menu mostra só as telas do perfil: o encarregado vê Mapa e Execução; o almoxarife, também o Planejamento
  $$('.rail-item[data-tela]').forEach(b => { b.hidden = !podeTela(b.dataset.tela); });
  $$('button.rail-grupo').forEach(b => { b.hidden = $(`.rail-sub[data-grupo="${b.dataset.grupo}"]`).hidden = !telasDoGrupo(b.dataset.grupo).length; });
  $$('.rail-itens .rail-div').forEach(d => {                    // divisória sem nada visível depois dela some
    let x = d.nextElementSibling, algo = false;
    for (; x && !x.classList.contains('rail-div'); x = x.nextElementSibling) algo = algo || !x.hidden;
    d.hidden = !algo;
  });
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
  $$('input[type=date]').forEach(i => { if (!i.value && !['periodo_ini', 'periodo_fim', 'data_documento'].includes(i.name)) i.value = hoje(); });
  if (podeTela('medicao')) { const ms = await api('/api/medicoes'); const ab = ms.find(m => m.status === 'ABERTA'); if (ab) MEDICAO_ATUAL = ab.id; }
  abrirAba(location.hash.slice(1) || 'inicio', { substituir: true });
  setTimeout(() => driveEmSegundoPlano(), 4000);   // o que ficou na fila (sem rede, sem conexão) sobe agora
}
iniciar();
