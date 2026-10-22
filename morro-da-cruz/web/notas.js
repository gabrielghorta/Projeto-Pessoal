'use strict';
/* Notas de serviço (NS) por upload: enviar, ler, conferir cada segmento contra os trechos da obra e registrar.
 * "Ler a nota" não grava nada; o PDF e o croqui abrem no próprio navegador antes de registrar (URL.createObjectURL) e,
 * depois de registrados, pela rota /api/ns/arquivo. As abas Topografia e Cadastro de campo mostram as NS do tipo delas. */

const NS_TIPOS = { TOPOGRAFIA: 'Topografia', CADASTRO: 'Cadastro de campo', SERVICO: 'Serviço de obra', EXECUCAO: 'Do dia (execução)' };
const NS_DESC = {
  TOPOGRAFIA: 'Gera a liberação topográfica dos trechos da nota, só no que ainda não está liberado.',
  CADASTRO: 'Gera o cadastro de campo sobre o que já foi assentado até a data da nota. O resto fica pendente e entra depois, '
    + 'quando o assentamento for lançado ("Aplicar o que falta").',
  SERVICO: 'O plano do serviço da zona: a nota e o croqui ficam para a equipe abrir na Nota do dia. Não grava avanço.',
};
const NS_ETAPA = { TOPOGRAFIA: 'liberação topográfica', CADASTRO: 'cadastro de campo' };
const NS_SITU = { AUTOMATICO: ['automático', 'azul'], CONFIRMAR: ['confirmar', 'amarelo'], ERRO: ['erro', 'vermelho'],
  SEM_CORRESPONDENCIA: ['sem correspondência', 'vermelho'], CONFIRMADO: ['confirmado', 'azul'], FORA: ['fora', 'cinza'] };
const NSV = { tipo: 'TOPOGRAFIA', envio: null, leitura: null, decisoes: {}, marcado: {}, filtro: '', anuladas: false, fila: {} };
const chipNs = s => `<span class="chip ${(NS_SITU[s] || ['', ''])[1]}">${esc((NS_SITU[s] || [s])[0])}</span>`;
const mNs = v => v == null ? '—' : nf(v) + ' m';
const linhaNs = n => String(n || '').split('_').pop();                       // Zona03_PB08_Rede_TR020 → TR020
const elNs = t => String(t || '').split(/\s+\(|\s+-\s+/)[0].trim() || '?';       // NÓ6.1 - TÊ 160x110 → NÓ6.1
const PERM_NS = { TOPOGRAFIA: 'topografia', CADASTRO: 'cadastro_campo' };     // registrar, aplicar e anular pedem também a do tipo
const podeNs = tipo => pode('notas_servico') && (!PERM_NS[tipo] || pode(PERM_NS[tipo]));
const linkNs = (id, qual, rot) => `<a class="btn" href="/api/ns/arquivo?id=${id}&qual=${qual}" target="_blank" rel="noopener">${rot}</a>`;

/* ---------------------------------------------------------------- envio e leitura */
async function carregarNotas() {
  const z = $('#nsZona');
  if (z.options.length < 2) z.innerHTML += RESUMO.frentes.filter(f => /^(Zona\d\d|ADUTORA)$/.test(f)).map(f => `<option>${esc(f)}</option>`).join('');
  nsMarcarTipo();
  $$('#nsFiltro button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.nsFiltro === NSV.filtro)));
  $('#nsAnuladas').checked = NSV.anuladas;
  nsCarregarFila();
  await nsCarregarLista(NSV.filtro, '#nsLista', { anuladas: NSV.anuladas });
}
function nsMarcarTipo() {
  $$('#nsTipo button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.nsTipo === NSV.tipo)));
  $('#nsTipoDesc').textContent = NS_DESC[NSV.tipo];
  $('#nsCroquiRot').textContent = NSV.tipo === 'SERVICO' ? 'Croqui (PDF, JPG ou PNG; obrigatório no serviço de obra)' : 'Croqui (PDF, JPG ou PNG; opcional)';
}
function nsLimpar(form = true) {
  if (NSV.envio) Object.values(NSV.envio.arquivos).forEach(a => a && URL.revokeObjectURL(a.url));
  NSV.envio = NSV.leitura = null; NSV.decisoes = {}; NSV.marcado = {};
  if (form) $('#fNs').reset();
  $('#nsResultado').innerHTML = '<p class="vazio">Escolha o tipo e o PDF da nota e toque em "Ler a nota".</p>';
  $('#nsSegPainel').hidden = true;
}
async function nsArquivo(input) {
  const f = input.files[0];
  return f ? { b64: await lerOriginal(f), nome: f.name, url: URL.createObjectURL(f) } : null;
}
$('#nsTipo').addEventListener('click', ev => {
  const b = ev.target.closest('[data-ns-tipo]'); if (!b) return;
  if (NSV.leitura && b.dataset.nsTipo !== NSV.tipo) nsLimpar(false);     // a prévia muda com o tipo: ler de novo
  NSV.tipo = b.dataset.nsTipo; nsMarcarTipo();
});
const nsTravar = sim => { $$('#nsTipo button, #fNs button.prim').forEach(b => { b.disabled = sim; }); };
$('#fNs').addEventListener('submit', async ev => {
  ev.preventDefault();
  const f = ev.target, o = formObj(f), tipo = NSV.tipo;          // o tipo fica preso durante a leitura
  nsLimpar(false);
  const arquivos = { pdf: await nsArquivo(f.pdf), croqui: await nsArquivo(f.croqui), planilha: await nsArquivo(f.planilha) };
  if (!arquivos.pdf) return toast('Escolha o PDF da nota de serviço.', 'erro');
  $('#nsResultado').innerHTML = '<p class="vazio">Lendo a nota…</p>';
  nsTravar(true);
  const r = await acao(() => api('/api/ns/ler', { tipo, pdf_b64: arquivos.pdf.b64, planilha_b64: arquivos.planilha && arquivos.planilha.b64,
    zona: o.zona || null, pb: o.pb || null })).catch(() => null).finally(() => nsTravar(false));
  if (!r || r.tipo !== NSV.tipo) { $('#nsResultado').innerHTML = '<p class="vazio">A nota não foi lida. Veja o aviso acima.</p>'; return; }
  NSV.envio = { tipo: r.tipo, arquivos, zona: o.zona || null, pb: o.pb || null };
  NSV.leitura = r; NSV.decisoes = {}; NSV.marcado = {};
  renderNsLeitura();
  if (r.contrato_ok) renderNsSegmentos();             // nota de outra obra: não há o que conferir
});

function renderNsLeitura() {
  const r = NSV.leitura, l = r.leitura, a = NSV.envio.arquivos, res = l.resultado;
  const contas = l.verificacoes.filter(v => v.nivel !== 'INFO');
  const falhas = contas.filter(v => !v.ok), erros = falhas.filter(v => v.nivel === 'ERRO');
  const ctx = r.contexto, onde = [ctx.zona, ctx.pb].filter(Boolean).join(' ');
  const avisos = [];
  if (!r.contrato_ok) avisos.push(['problema', `<b>Recusada: a nota é de outro contrato (${esc(l.contrato || 'sem contrato')}).</b> Esta obra é o ${esc(RESUMO.contrato)}. Nada pode ser registrado.`]);
  else if (!res.aceita) avisos.push(['problema', `<b>Recusada:</b> ${res.motivos.map(esc).join('; ')}. Confira o PDF ou envie a planilha da nota (.xlsx).`]);
  if (r.ja_registrada) avisos.push(['problema', `<b>Este arquivo já foi registrado</b> (NS ${esc(r.ja_registrada.numero)}, ${esc(NS_TIPOS[r.ja_registrada.tipo] || r.ja_registrada.tipo)}, em ${dataBR(String(r.ja_registrada.registrada_em).slice(0, 10))}).`]);
  if (r.mesmo_numero) avisos.push(r.mesmo_numero.mesma_impressao
    ? ['sugestao', `A NS ${esc(r.mesmo_numero.numero)} já está registrada com o mesmo conteúdo (por exemplo, a versão sem assinatura). Ao registrar, só o arquivo é trocado; a versão anterior fica guardada.`]
    : ['problema', `<b>A NS ${esc(r.mesmo_numero.numero)} já está registrada com outro conteúdo.</b> Anule a anterior (com o motivo) na lista "Notas recebidas" antes de registrar esta.`]);
  if (r.aviso_tipo) avisos.push(['info', `Confira o tipo: ${esc(r.aviso_tipo)}.`]);
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
  else if (!NS_ETAPA[tipo]) html = '<p>Nada é gravado nos trechos: a nota e o croqui ficam para a equipe abrir na Nota do dia da zona.</p>';
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
    : `NS registrada${NS_ETAPA[e.tipo] ? `: ${nf(r.gravado_m)} m de ${NS_ETAPA[e.tipo]} gravados${r.pendente_m > 0.001 ? `, ${nf(r.pendente_m)} m pendentes` : ''}` : ''}.`, 'ok');
  nsLimpar(); NSV.filtro = e.tipo; carregarNotas(); recarregarCamadaMapa(); driveEmSegundoPlano();
});

/* ---------------------------------------------------------------- notas recebidas (tela Notas e abas Topografia / Cadastro) */
async function nsCarregarLista(tipo, alvo, opcoes = {}) {
  const q = new URLSearchParams({ vigentes: opcoes.anuladas ? '0' : '1' }); if (tipo) q.set('tipo', tipo);
  const lista = await acao(() => api('/api/ns?' + q)).catch(() => null); if (!lista) return;
  $(alvo).innerHTML = htmlNsLista(lista);
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
        ${podeNs(n.tipo) && n.status === 'REGISTRADA' && NS_ETAPA[n.tipo] && n.pendente_m > 0.001 ? `<button type="button" class="btn azul" data-ns-aplicar="${n.id}">Aplicar o que falta</button>` : ''}
        ${podeNs(n.tipo) && n.status === 'REGISTRADA' && n.tipo !== 'EXECUCAO' ? `<button type="button" class="btn" data-ns-anular="${n.id}">Anular</button>` : ''}</div></td></tr>
      <tr hidden data-ns-detalhe="${n.id}"><td colspan="9"></td></tr>`));
}
async function nsVer(id, linha) {
  if (!linha.hidden) { linha.hidden = true; return; }
  const d = await acao(() => api('/api/ns/detalhe?id=' + id)).catch(() => null); if (!d) return;
  linha.hidden = false;
  $('td', linha).innerHTML = `${d.status === 'ANULADA' ? `<div class="aviso problema">Anulada por ${esc(d.anulada_por)} em ${dataBR(String(d.anulada_em).slice(0, 10))}: ${esc(d.anulada_motivo)}</div>` : ''}
    ${d.segmentos.map(s => `<div class="registro"><div><b>${s.ordem}. ${esc(elNs(s.de))} → ${esc(elNs(s.para))} · ${mNs(s.metros_ns)} na nota</b> ${chipNs(s.situacao)}</div>
      <small>${s.linhas.length ? s.linhas.map(l => `${esc(linhaNs(l.ponto))} ${nf(l.ini_m)}–${nf(l.fim_m)} m`).join(' · ') : 'sem trecho da obra'}
        ${s.aplicado_m > 0.001 ? ` · gravado ${nf(s.aplicado_m)} m` : ''}${s.pendente_m > 0.001 ? ` · <b>pendente ${nf(s.pendente_m)} m</b>` : ''}${s.confirmado_por ? ` · conferido por ${esc(s.confirmado_por)}` : ''}</small>
      ${[s.motivo, s.pendente, ...(s.avisos || [])].filter(Boolean).map(t => `<div><small>${esc(t)}</small></div>`).join('')}</div>`).join('') || '<p class="vazio">Sem segmentos.</p>'}
    ${d.versoes.length ? `<p style="margin:6px 0 0"><small>Versões anteriores do arquivo: ${d.versoes.length} (guardadas, registradas em ${d.versoes.map(v => dataBR(String(v.registrada_em).slice(0, 10))).join(', ')})</small></p>` : ''}`;
}
document.addEventListener('click', async ev => {
  const ver = ev.target.closest('[data-ns-ver]'), apl = ev.target.closest('[data-ns-aplicar]'), anu = ev.target.closest('[data-ns-anular]');
  const env = ev.target.closest('[data-ns-enviar]');
  if (env) { NSV.tipo = env.dataset.nsEnviar; nsLimpar(); abrirAba('notas'); return; }
  if (ver) return nsVer(ver.dataset.nsVer, ver.closest('table').querySelector(`[data-ns-detalhe="${ver.dataset.nsVer}"]`));
  let r = null;
  if (apl) r = await acao(() => api('/api/ns/aplicar', { ns_id: +apl.dataset.nsAplicar }), null).catch(() => null);
  if (apl && r) toast(r.gravado_m > 0.001 ? `Gravados mais ${nf(r.gravado_m)} m.${r.pendente_m > 0.001 ? ` Ainda pendentes: ${nf(r.pendente_m)} m.` : ''}`
    : 'Nada novo a gravar: o que falta ainda não foi assentado até a data da nota.', 'ok');
  if (anu) {
    const motivo = prompt('Motivo da anulação (os registros desta nota também são anulados; nada é apagado):'); if (!motivo || !motivo.trim()) return;
    r = await acao(() => api('/api/ns/anular', { ns_id: +anu.dataset.nsAnular, motivo: motivo.trim() }), 'Nota anulada com os registros dela.').catch(() => null);
  }
  if (r) { if (TELA === 'notas') carregarNotas(); else if (TELA === 'topografia') carregarTopografia(); else if (TELA === 'cadastro_campo') carregarCadCampo(); recarregarCamadaMapa(); }
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
  || (pode('campo') && !n.verificada && (!USUARIO.restrito_a_equipe || n.equipe_id === USUARIO.equipe_id)));
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

/* ---------------------------------------------------------------- Nota do dia (tela campo: o encarregado envia, sem digitar o que fez) */
const ND = { clima: {} };
const zonaDaEquipe = eq => /^(Zona\d\d|ADUTORA)$/.test(eq || '') ? eq : '';
async function carregarNotaDia() {
  const sel = $('#ndEquipe');
  if (sel.options.length < 2) sel.innerHTML = '<option value="">Escolha a equipe</option>' + RESUMO.equipes.map(e => `<option value="${esc(e.id)}">${esc(e.nome)}</option>`).join('');
  if (USUARIO.restrito_a_equipe) { sel.value = USUARIO.equipe_id; sel.disabled = true; }        // o encarregado envia só a dele
  $$('#fNd [data-turno]').forEach(box => { if (!box.children.length) box.innerHTML = Object.entries(RESUMO.clima)
    .map(([k, v]) => `<button type="button" data-clima="${esc(k)}" aria-pressed="false">${esc(v)}</button>`).join(''); });
  $('#ndExcecao').hidden = !pode('lancar_sem_ns');
  await ndListas();
}
async function ndListas() {
  const eq = $('#ndEquipe').value, q = new URLSearchParams({ desde: somarDia(hoje(), -7) }), z = zonaDaEquipe(eq);
  if (eq) q.set('equipe', eq);
  const [env, serv] = await Promise.all([api('/api/ns/dia?' + q).catch(() => null), api('/api/ns?tipo=SERVICO' + (z ? '&zona=' + z : '')).catch(() => null)]);
  if (env) $('#ndEnviadas').innerHTML = env.slice(0, 10).map(htmlNdNota).join('') || '<p class="vazio">Nenhuma nota enviada nos últimos 7 dias.</p>';
  if (serv) $('#ndServico').innerHTML = serv.slice(0, 8).map(n => `<div class="registro"><div><b>${esc(n.referencia)} · ${dataBR(n.data)}</b>
      <span>${esc([n.zona, n.pb].filter(Boolean).join(' '))}</span></div><small>${esc(n.titulo || '')}</small>
      <div class="acoes" style="margin-top:6px">${linkNs(n.id, 'pdf', 'Abrir a nota')}${n.croqui_id ? linkNs(n.id, 'croqui', 'Abrir o croqui') : ''}</div></div>`).join('')
    || '<p class="vazio">Nenhuma nota de serviço da zona.</p>';
}
$('#ndEquipe').addEventListener('change', ndListas);
$('#fNd').addEventListener('click', ev => {
  const b = ev.target.closest('[data-clima]'); if (!b) return;
  const box = b.closest('[data-turno]');
  ND.clima[box.dataset.turno] = b.dataset.clima;
  $$('button', box).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
});
$('#fNd').addEventListener('submit', async ev => {
  ev.preventDefault();
  const f = ev.target, eq = $('#ndEquipe').value, pdf = f.pdf.files[0], cro = f.croqui.files[0], pla = f.planilha.files[0];
  if (!eq) return toast('Escolha a equipe.', 'erro');
  if (!pdf || !cro) return toast('Escolha a nota do dia (PDF) e o croqui.', 'erro');
  if (!ND.clima.MANHA || !ND.clima.TARDE) return toast('Toque no clima da manhã e no da tarde.', 'erro');
  const bt = $('#ndEnviar'); bt.disabled = true; bt.textContent = 'Enviando…';
  try {
    const corpo = { equipe_id: eq, pdf_b64: await lerOriginal(pdf), pdf_nome: pdf.name, croqui_b64: await lerOriginal(cro), croqui_nome: cro.name, clima: ND.clima };
    if (pla) Object.assign(corpo, { planilha_b64: await lerOriginal(pla), planilha_nome: pla.name });
    const r = await acao(() => api('/api/ns/dia', corpo)).catch(() => null);
    if (!r) return;
    toast(r.arquivo_trocado ? 'Arquivo da nota trocado (a versão anterior ficou guardada).'
      : r.fila.length ? 'Nota enviada: o que deu para lançar foi lançado; o resto aguarda a engenharia.' : 'Nota enviada e lançada.', 'ok');
    const res = $('#ndResultado'); res.hidden = false; res.innerHTML = `<h3>Resultado do envio</h3>${htmlNdNota(r)}`;
    f.reset(); $('#ndEquipe').value = eq;
    ndListas(); recarregarCamadaMapa(); driveEmSegundoPlano();
  } finally { bt.disabled = false; bt.textContent = 'Enviar a nota do dia'; }
});
ligarBusca($('#ndAlvo'), r => selecionarCampo(r.tipo, r.id));
// o trecho (ou nó) das soldas e fotos é um só na tela, venha da busca, do formulário de exceção ou da ficha do mapa
function ndAlvoEscolhido(nome) {
  $('#ndAlvo').value = curto(nome); $('#ndAlvoInfo').textContent = `Soldas e fotos de ${curto(nome)}.`;
  if (!$('#ndOutros').open && !$('#ndExcecao').open) (pode('lancar_sem_ns') ? $('#ndExcecao') : $('#ndOutros')).open = true;
}
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-nd-anular]'); if (!b) return;
  const motivo = prompt('Motivo da anulação (o que esta nota lançou também é anulado; nada é apagado):'); if (!motivo || !motivo.trim()) return;
  const r = await acao(() => api('/api/ns/dia/anular', { ns_id: +b.dataset.ndAnular, motivo: motivo.trim() }), 'Envio anulado.').catch(() => null);
  if (!r) return;
  if (TELA === 'campo') { $('#ndResultado').hidden = true; ndListas(); } else if (TELA === 'diario') carregarDiario();
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
