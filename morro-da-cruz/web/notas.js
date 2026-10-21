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
const NSV = { tipo: 'TOPOGRAFIA', envio: null, leitura: null, decisoes: {}, marcado: {}, filtro: '', anuladas: false };
const chipNs = s => `<span class="chip ${(NS_SITU[s] || ['', ''])[1]}">${esc((NS_SITU[s] || [s])[0])}</span>`;
const mNs = v => v == null ? '—' : nf(v) + ' m';
const linhaNs = n => String(n || '').split('_').pop();                       // Zona03_PB08_Rede_TR020 → TR020
const elNs = t => String(t || '').split(/\s+\(|\s+-\s+/)[0].trim() || '?';       // NÓ6.1 - TÊ 160x110 → NÓ6.1
const linkNs = (id, qual, rot) => `<a class="btn" href="/api/ns/arquivo?id=${id}&qual=${qual}" target="_blank" rel="noopener">${rot}</a>`;

/* ---------------------------------------------------------------- envio e leitura */
async function carregarNotas() {
  const z = $('#nsZona');
  if (z.options.length < 2) z.innerHTML += RESUMO.frentes.map(f => `<option>${esc(f)}</option>`).join('');
  nsMarcarTipo();
  $$('#nsFiltro button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.nsFiltro === NSV.filtro)));
  $('#nsAnuladas').checked = NSV.anuladas;
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
$('#fNs').addEventListener('submit', async ev => {
  ev.preventDefault();
  const f = ev.target, o = formObj(f);
  nsLimpar(false);
  const arquivos = { pdf: await nsArquivo(f.pdf), croqui: await nsArquivo(f.croqui), planilha: await nsArquivo(f.planilha) };
  if (!arquivos.pdf) return toast('Escolha o PDF da nota de serviço.', 'erro');
  $('#nsResultado').innerHTML = '<p class="vazio">Lendo a nota…</p>';
  const r = await acao(() => api('/api/ns/ler', { tipo: NSV.tipo, pdf_b64: arquivos.pdf.b64, planilha_b64: arquivos.planilha && arquivos.planilha.b64,
    zona: o.zona || null, pb: o.pb || null })).catch(() => null);
  if (!r) { $('#nsResultado').innerHTML = '<p class="vazio">A nota não foi lida. Veja o aviso acima.</p>'; return; }
  NSV.envio = { tipo: NSV.tipo, arquivos, zona: o.zona || null, pb: o.pb || null };
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
  if (!pode('notas_servico')) out.push('seu perfil não registra notas de serviço');
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
  const gerir = pode('notas_servico');
  return tabelaHtml('<th>NS</th><th>Tipo</th><th>Onde</th><th>Data</th><th>Situação</th><th class="n">Gravou</th><th class="n">Pendente</th><th>Drive</th><th></th>',
    lista.map(n => `<tr${n.status === 'ANULADA' ? ' style="opacity:.6"' : ''}><td><b>${esc(n.referencia)}</b><br><small>${esc(n.titulo || '')}</small></td>
      <td>${esc(NS_TIPOS[n.tipo] || n.tipo)}</td><td>${esc([n.zona, n.pb, n.equipe_id && n.tipo === 'EXECUCAO' ? 'equipe ' + n.equipe_id : null].filter(Boolean).join(' · ') || '—')}</td>
      <td>${dataBR(n.data)}</td><td>${n.status === 'ANULADA' ? `<span class="chip cinza" title="${esc(n.anulada_motivo || '')}">anulada</span>` : `<small>${situNs(n)}</small>`}</td>
      <td class="n">${NS_ETAPA[n.tipo] || n.tipo === 'EXECUCAO' ? mNs(n.aplicado_m) : '—'}</td><td class="n">${n.pendente_m > 0.001 ? `<b>${mNs(n.pendente_m)}</b>` : '—'}</td>
      <td>${driveNs((n.drive || {}).pdf)}</td>
      <td><div class="acoes">${linkNs(n.id, 'pdf', 'PDF')}${n.croqui_id ? linkNs(n.id, 'croqui', 'Croqui') : ''}
        <button type="button" class="btn" data-ns-ver="${n.id}">Ver</button>
        ${gerir && n.status === 'REGISTRADA' && NS_ETAPA[n.tipo] && n.pendente_m > 0.001 ? `<button type="button" class="btn azul" data-ns-aplicar="${n.id}">Aplicar o que falta</button>` : ''}
        ${gerir && n.status === 'REGISTRADA' && n.tipo !== 'EXECUCAO' ? `<button type="button" class="btn" data-ns-anular="${n.id}">Anular</button>` : ''}</div></td></tr>
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
