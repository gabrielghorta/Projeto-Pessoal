'use strict';
/* Apropriação direta (Lançamento do dia › Apropriação direta) e a base de custo na tela Medição.
 * O item é escolhido como no BM Vertical (grupo → material ou serviço → item) ou pela busca, que acha por qualquer
 * identificador; o cartão mostra a situação (aprovado ou a aprovar), o preço, o contratado e o saldo. Item que não está
 * no orçamento entra pelo cadastro rápido, com o aviso de item parecido. Correção só por estorno com motivo.
 * Na Medição: "medível com restrição" (o dinheiro parado e a ação que libera) e os itens a aprovar. */

const APR = { listas: null, item: null, busca: 0, tBusca: null, rest: null };
const APR_COR = { APROVADO: 'verde', A_APROVAR: 'vermelho', REPROVADO: 'cinza' };
const APR_SIT = { PROPOSTA: ['verde', 'na medição'], PARCIAL: ['amarelo', 'em parte na medição'], PARADA: ['vermelho', 'parada'],
  ESTORNADA: ['cinza', 'estornada'] };
const APR_DIM = {M:1,M2:2,M3:3};
function aprParcelas() {
  return $$('#aprMedidas [data-parcela]').map(parte => {
    const p = Object.fromEntries($$('[data-medida]', parte).map(i => [i.dataset.medida, i.value]));
    p.lados = $$('[data-lado]', parte).map(l => ({nome:$('[data-lado-nome]',l).value.trim(), comprimento:$('[data-lado-comprimento]',l).value.trim()}))
      .filter(l => l.nome || l.comprimento);
    return p;
  });
}
function aprDimensao() { return APR_DIM[String(APR.item?.unidade || '').toUpperCase().replace('²','2').replace('³','3')]; }
function aprMontarMedidas() {
  const dim=aprDimensao(), q=$('#fApr').quantidade;
  q.readOnly=!!dim; q.value='';
  $('#aprMedidas').innerHTML=dim ? `<h4>Medidas do serviço</h4><p class="vazio">Preencha os lados um por um ou digite a soma. A quantidade é calculada automaticamente.</p><div id="aprParcelas"></div><button type="button" class="btn" id="aprMaisParcela">+ outra parte</button><p id="aprConta" aria-live="polite"></p>` : '';
  if(dim) aprAdicionarParcela(dim);
}
function aprAdicionarLado(parte) {
  if($$('[data-lado]',parte).length>=30) return toast('No máximo 30 lados por parte.','erro');
  $('[data-lados]',parte).insertAdjacentHTML('beforeend',`<div data-lado class="apr-lado"><label>Nome do lado (opcional)<input data-lado-nome maxlength="40" placeholder="A-B"></label><label>Comprimento (m)<input data-lado-comprimento inputmode="decimal" placeholder="80,00"></label><button type="button" class="btn" data-apr-tirar-lado aria-label="Remover este lado">Remover</button></div>`);
}
function aprAdicionarParcela(dim) {
  const n=$$('#aprMedidas [data-parcela]').length;
  if(n>=30)return toast('No máximo 30 partes.','erro');
  $('#aprParcelas').insertAdjacentHTML('beforeend',`<fieldset data-parcela><legend>Parte ${n+1}</legend>
    <label>Identificação (opcional)<input data-medida="descricao" maxlength="150" placeholder="ex.: tapume da frente"></label>
    <div data-lados></div><button type="button" class="btn" data-apr-mais-lado>+ lado</button>
    <label>Ou digite a soma dos lados (m)<input data-medida="soma" inputmode="decimal" placeholder="80 + 50 + 40 + 20 + 45" maxlength="400"></label>
    <div class="linha">${dim>1?`<label>${dim===2?'Altura ou largura':'Largura'} (m)<input data-medida="largura" inputmode="decimal" placeholder="2,00" required></label>`:''}
    ${dim>2?'<label>Profundidade ou espessura (m)<input data-medida="profundidade" inputmode="decimal" placeholder="0,10" required></label>':''}
    <label>Repetições (opcional)<input type="number" min="1" max="99999" step="1" data-medida="repeticoes" value="1"></label></div>
    <p data-resultado-parte aria-live="polite" class="apr-resultado"></p><button type="button" class="btn" data-apr-tirar-parcela>Remover parte</button></fieldset>`);
  aprAdicionarLado($('#aprParcelas').lastElementChild);
}
function aprSomarMedida(v) {
  const ps=String(v).split('+');
  if(String(v).length>400 || ps.length>30)return NaN;
  const vs=ps.map(t=>{t=t.trim();return /^(?:\d+(?:[.,]\d+)?|\d{1,3}(?:\.\d{3})+,\d+)$/.test(t)?Number(t.includes(',')?t.replace(/\./g,'').replace(',','.'):t):NaN;});
  return vs.every(n=>Number.isFinite(n)&&n>0&&n<=1e9)?vs.reduce((a,b)=>a+b,0):NaN;
}
function aprAtualizarConta() {
  if(!aprDimensao())return;
  const partes=aprParcelas(), dim=aprDimensao(), unidade=['','m','m²','m³'][dim];
  const medida=n=>n.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:4});
  let total=0, valido=partes.length>0;
  partes.forEach((p,i)=>{
    const box=$$('#aprMedidas [data-parcela]')[i]; let mensagem='';
    if(p.lados.length && p.soma.trim()) mensagem='Escolha os lados ou a soma. Não preencha os dois na mesma parte.';
    const comp=p.lados.length?p.lados.reduce((a,l)=>a+aprSomarMedida(l.comprimento),0):aprSomarMedida(p.soma);
    const larg=dim>1?aprSomarMedida(p.largura):1, prof=dim>2?aprSomarMedida(p.profundidade):1, rep=Number(p.repeticoes||1);
    const q=comp*larg*prof*rep;
    if(!mensagem && (![comp,larg,prof,q].every(n=>Number.isFinite(n)&&n>0)||!Number.isInteger(rep)||rep<1||rep>99999)) mensagem='Preencha as medidas positivas para calcular esta parte.';
    if(mensagem) valido=false; else total+=q;
    $('[data-resultado-parte]',box).textContent=mensagem || `${dim>1?'Perímetro':'Comprimento'} ${medida(comp)} m${dim>1?' × '+(dim===2?'altura/largura ':'largura ')+medida(larg)+' m':''}${dim>2?' × espessura '+medida(prof)+' m':''}${rep!==1?' × '+rep+' vezes':''} = ${medida(q)} ${unidade}`;
    box.classList.toggle('apr-medida-conflito',!!(p.lados.length && p.soma.trim()));
  });
  $('#fApr').quantidade.value=valido?Number(total.toFixed(4)):'';
  $('#aprConta').textContent=valido?`Total: ${medida(total)} ${unidade}`:'Complete as medidas de todas as partes.';
  aprCartao();
}
$('#aprMedidas').addEventListener('input',aprAtualizarConta);
$('#aprMedidas').addEventListener('click',ev=>{
  if(ev.target.closest('#aprMaisParcela'))aprAdicionarParcela(aprDimensao());
  if(ev.target.closest('[data-apr-mais-lado]'))aprAdicionarLado(ev.target.closest('[data-parcela]'));
  if(ev.target.closest('[data-apr-tirar-lado]'))ev.target.closest('[data-lado]').remove();
  if(ev.target.closest('[data-apr-tirar-parcela]'))ev.target.closest('[data-parcela]').remove();
  aprAtualizarConta();
});
const APR_ATRIBUTOS = ['descricao_resumida', 'material', 'diametro', 'pressao', 'resina', 'tipo_conexao', 'solda', 'grupo_orcamento_ankara'];
const aprEtiqueta = it => `<span class="chip ${APR_COR[it.situacao] || ''}">${esc(it.rotulo)}</span>`;
const aprPreco = it => it.preco == null ? '—' : reais(it.preco) + (it.preco_estimado ? ' <small>(estimado)</small>' : '');
const aprNome = it => `${esc(it.item_bm || it.item)} · ${esc(it.resumida || it.descricao)}`;
const aprGrupo = it => {                                 // "CANTEIRO - SERVIÇO" → "Canteiro · serviço (1.2)"
  const [g, t] = String(it.subgrupo_nome || `${it.grupo} - ${it.tipo}`).split(' - '), m = s => String(s || '').toLowerCase();
  return `${esc(g.charAt(0) + m(g.slice(1)))}${t ? ' · ' + esc(m(t)) : ''}${it.subgrupo ? ` (${esc(it.subgrupo)})` : ''}`;
};

/* ---------------------------------------------------------------- Lançamento do dia: as páginas do lançamento solto */
// apropriação direta, apontamento sem NS, fotos e soldas, clima do dia (PAGINAS.campo em app.js); a NS do dia é em Notas de serviço
function carregarLancamentoDia() {
  if (PAGINA.campo === 'apontamento') return carregarAlvosDoDia();
  if (PAGINA.campo === 'apropriacao') return carregarApropriacao();
}

/* ---------------------------------------------------------------- aba Apropriação direta */
async function carregarApropriacao() {
  if (!APR.listas) {
    const l = await acao(() => api('/api/base-custo/itens')).catch(() => null); if (!l) return;
    APR.listas = l;
    const op = lista => lista.map(x => `<option value="${esc(x.id)}">${esc(x.nome)}</option>`).join('');
    $('#aprGrupo').innerHTML = '<option value="">Escolha</option>' + op(l.grupos);
    $('#novoGrupo').innerHTML = op(l.grupos);
    $('#aprExecutor').innerHTML = op(l.executores);
    $('#novoFonte').innerHTML = op(l.fontes_preco);
    opcoesEquipe($('#aprEquipe'), 'Escolha a equipe');
    $('#aprZona').innerHTML = RESUMO.frentes.map(f => `<option>${esc(f)}</option>`).join('');
    ligarBusca($('#aprAlvo'));
  }
  const f = $('#fApr');
  if (!f.data.value) f.data.value = hoje();
  f.data.max = hoje();
  aprExecutorCampos(); aprLocalCampos();
  aprCarregarLista();
}
function aprLocalCampos() {
  const t = $('#aprLocalTipo').value;
  $('#aprZonaRot').hidden = t !== 'ZONA';
  $('#aprAlvoRot').hidden = !['TRECHO', 'ATIVIDADE'].includes(t);
}
function aprExecutorCampos() {
  const t = $('#aprExecutor').value;
  $('#aprEquipeRot').hidden = t !== 'EQUIPE_OBRA';
  $('#aprObraRot').hidden = t !== 'OUTRA_OBRA';
  $('#aprNomeRot').hidden = !t || ['EQUIPE_OBRA','NAO_INFORMADO'].includes(t);
  $('#aprNomeRot').firstChild.textContent = t === 'TERCEIRO' ? 'Nome do terceiro' : 'Equipe da outra obra';
}
$('#aprLocalTipo').addEventListener('change', aprLocalCampos);
$('#aprExecutor').addEventListener('change', aprExecutorCampos);

// busca única: qualquer identificador (item, código, descrição, diâmetro, material…)
$('#aprBusca').addEventListener('input', () => { clearTimeout(APR.tBusca); APR.tBusca = setTimeout(aprBuscar, 220); });
async function aprBuscar() {
  const q = $('#aprBusca').value.trim(), n = ++APR.busca;
  if (q.length < 2) { $('#aprResultados').innerHTML = ''; return; }
  const r = await api('/api/base-custo/busca?q=' + encodeURIComponent(q)).catch(() => null);
  if (!r || n !== APR.busca) return;                       // chegou a resposta de uma busca mais velha
  // o mesmo item aparece uma vez por orçamento parcial (canteiro, redes, caixas…): cada um diz o seu, e o do grupo
  // escolhido vem primeiro
  const g = $('#aprGrupo').value, itens = r.itens.slice(0, 20);
  if (g) itens.sort((a, b) => (a.grupo !== g) - (b.grupo !== g));
  $('#aprResultados').innerHTML = itens.length ? itens.map(it => `<button type="button" class="apr-res" data-apr-ref="${esc(it.ref)}"
      aria-pressed="${String(!!APR.item && APR.item.ref === it.ref)}"><span><b>${aprNome(it)}</b><br><span class="apr-grupo">${aprGrupo(it)}</span><br><small>${esc(it.descricao.slice(0, 140))}</small></span>
      <span style="text-align:right">${aprEtiqueta(it)}<br><small>${esc(it.unidade)} · ${aprPreco(it)}</small></span></button>`).join('')
    : '<p class="vazio">Nada encontrado. Se o item não está no orçamento, use "O item não está na lista".</p>';
}
$('#aprResultados').addEventListener('click', ev => { const b = ev.target.closest('[data-apr-ref]'); if (b) aprEscolher(b.dataset.aprRef, true); });

// cascata: grupo → material ou serviço → item
async function aprCarregarSubgrupo(selecionar) {
  const g = $('#aprGrupo').value, t = $('#aprTipo').value, sel = $('#aprItem');
  if (!g || !t) { sel.innerHTML = '<option value="">Escolha o grupo e o tipo</option>'; return; }
  const r = await api(`/api/base-custo/itens?grupo=${encodeURIComponent(g)}&tipo=${encodeURIComponent(t)}`).catch(() => null); if (!r) return;
  sel.innerHTML = (r.itens.length ? '<option value="">Escolha o item</option>' : '<option value="">Nenhum item neste subgrupo</option>')
    + r.itens.map(it => `<option value="${esc(it.ref)}">${esc(it.item_bm || it.item)} · ${esc((it.resumida || it.descricao).slice(0, 70))}${it.situacao === 'A_APROVAR' ? ' · A APROVAR' : ''}</option>`).join('');
  if (typeof selecionar === 'string') sel.value = selecionar;
}
$('#aprGrupo').addEventListener('change', aprCarregarSubgrupo);
$('#aprTipo').addEventListener('change', aprCarregarSubgrupo);
$('#aprItem').addEventListener('change', () => { if ($('#aprItem').value) aprEscolher($('#aprItem').value, false); });

async function aprEscolher(ref, preencher) {
  const r = await acao(() => api('/api/base-custo/itens?ref=' + encodeURIComponent(ref))).catch(() => null); if (!r) return;
  APR.item = r.item;
  if (preencher) {                                         // escolher pela busca preenche o grupo e o tipo sozinho
    $('#aprGrupo').value = r.item.grupo; $('#aprTipo').value = r.item.tipo;
    await aprCarregarSubgrupo(r.item.ref);
  }
  $$('#aprResultados [data-apr-ref]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.aprRef === ref)));
  $('#fItemNovo').hidden = true; $('#novoParecidos').innerHTML = '';     // achou o item: o cadastro de item novo não é preciso
  aprMontarMedidas(); aprCartao();
}
function aprCartao() {
  const it = APR.item;
  $('#aprUnidade').textContent = it ? `(${it.unidade})` : '';
  if (!it) { $('#aprCartao').innerHTML = ''; return; }
  const q = Number($('#fApr').quantidade.value || 0), passa = it.saldo != null && q > it.saldo + 1e-9;
  const sit = { APROVADO: 'Aprovado', A_APROVAR: 'A aprovar', REPROVADO: 'Reprovado' }[it.situacao];
  $('#aprCartao').innerHTML = `<div class="apr-cartao"><div class="acoes" style="justify-content:space-between"><b>${aprNome(it)}</b>${aprEtiqueta(it)}</div>
    <small>${esc(it.descricao)}</small>
    <dl><div><dt>Situação</dt><dd>${sit}</dd></div>
      <div><dt>Origem do código</dt><dd>${esc(it.origem_rotulo)}${it.codigo ? ' · ' + esc(it.codigo) : ''}${it.codigo_oficial && it.codigo_oficial !== it.codigo ? ' → ' + esc(it.codigo_oficial) : ''}</dd></div>
      <div><dt>Preço unitário (sem BDI)</dt><dd>${aprPreco(it)}</dd></div>
      <div><dt>Contratado</dt><dd>${it.contratado == null ? 'fora do BM' : nf(it.contratado, 3) + ' ' + esc(it.unidade)}</dd></div>
      <div><dt>Já medido · apropriado</dt><dd>${nf(it.medido, 3)} · ${nf(it.apropriado, 3)}</dd></div>
      <div><dt>Saldo</dt><dd>${it.saldo == null ? '—' : nf(it.saldo, 3) + ' ' + esc(it.unidade)}</dd></div></dl>
    ${it.situacao === 'A_APROVAR' ? '<div class="aviso problema"><b>Item a aprovar:</b> a apropriação é gravada, mas fica fora da medição até a Caesb dar o código oficial.</div>' : ''}
    ${it.situacao === 'REPROVADO' ? '<div class="aviso problema"><b>Item reprovado pela Caesb:</b> escolha outro item.</div>' : ''}
    ${it.classificacao === 'MATERIAL' ? '<div class="aviso info">Material: fica fora da medição até a matriz de regimes ser aprovada (D-53/D-54).</div>' : ''}
    ${passa ? `<div class="aviso problema">A quantidade passa do saldo do item (${nf(it.saldo, 3)} ${esc(it.unidade)}): o excedente fica parado até aditivo ou apostilamento.</div>` : ''}
    ${it.situacao !== 'REPROVADO' && pode('apropriacao') ? '<div class="acoes" style="margin-top:8px"><button type="button" class="btn prim" data-apr-ir="1">Apropriar este item ↓</button></div>' : ''}</div>`;
}
$('#fApr').quantidade.addEventListener('input', aprCartao);

$('#fApr').addEventListener('submit', async ev => {
  ev.preventDefault();
  if (!APR.item) return toast('Escolha o item (pela busca ou pelo grupo, tipo e item).', 'erro');
  if(aprDimensao() && !$('#fApr').quantidade.value) return toast('Confira as medidas. Use lados ou soma em cada parte.', 'erro');
  const f = ev.target, o = formObj(f), arqs = [...f.evidencias.files], lt = o.local_tipo, alvo = $('#aprAlvo');
  const bt = $('#aprGravar'); bt.disabled = true;
  try {
    const corpo = { parcelas: aprParcelas(), item_ref: APR.item.ref, data: o.data, quantidade: o.quantidade, executor_tipo: o.executor_tipo, equipe_id: o.equipe_id,
      executor_obra: o.executor_obra, executor_nome: o.executor_nome, o_que_foi_feito: o.o_que_foi_feito, memoria_calculo: o.memoria_calculo,
      justificativa: o.justificativa, local_tipo: lt || null,
      local_id: lt === 'ZONA' ? $('#aprZona').value : ['TRECHO', 'ATIVIDADE'].includes(lt) ? alvo.dataset.id || '' : null,
      evidencias: await Promise.all(arqs.map(async a => ({ nome: a.name, conteudo_b64: await lerOriginal(a) }))) };
    if (['TRECHO', 'ATIVIDADE'].includes(lt) && alvo.dataset.tipo) corpo.local_tipo = alvo.dataset.tipo;   // escolheu um nó na busca
    const r = await acao(() => api('/api/apropriacao', corpo)).catch(() => null);
    if (!r) return;
    toast(r.situacao === 'PROPOSTA' ? `Apropriação nº ${r.id} gravada e proposta na medição de teste (gaveta 5).`
      : `Apropriação nº ${r.id} gravada. Ela fica parada: a restrição aparece na Medição, em "Medível com restrição".`, 'ok');
    f.reset(); f.data.value = hoje(); alvo.value = ''; alvo.dataset.id = alvo.dataset.tipo = '';
    aprExecutorCampos(); aprLocalCampos();
    aprEscolher(r.item_info.ref, false); aprCarregarLista(); driveEmSegundoPlano();
  } finally { bt.disabled = false; }
});

// lista das apropriações recentes (e a seção do Diário de obra)
async function aprCarregarLista() {
  const ini = new Date(Date.now() - 60 * 864e5).toISOString().slice(0, 10);
  const r = await api('/api/apropriacoes?ini=' + ini).catch(() => null); if (!r) return;
  $('#aprLista').innerHTML = r.length ? r.map(a => aprHtml(a, true)).join('') : '<p class="vazio">Nenhuma apropriação nos últimos 60 dias.</p>';
}
function aprHtml(a, comEstorno) {
  const [cor, rot] = APR_SIT[a.situacao] || ['', a.situacao], it = a.item_info;
  const med = a.lancamentos.filter(l => l.status === 'PROPOSTO').map(l => `${nf(l.quantidade, 3)} ${esc(a.unidade)} na ${l.numero}ª medição`).join(' · ');
  return `<div class="registro${a.estornado_em ? ' estornada' : ''}"><div><b>nº ${a.id} · ${dataBR(a.data)} · ${aprNome(it)}</b><span class="chip ${cor}">${rot}</span></div>
    <div class="apr-riscado">${nf(a.quantidade, 3)} ${esc(a.unidade)} · ${reais(a.valor)} · ${aprEtiqueta(it)}</div>
    <small>${esc(a.executor)}${a.local_texto ? ' · ' + esc(a.local_texto) : ''} · ${esc(a.o_que_foi_feito)}</small>${med ? `<br><small>${med}</small>` : ''}
    ${a.estornado_em ? `<div class="aviso info">Estornada por ${esc(a.estornado_por)} em ${dataBR(String(a.estornado_em).slice(0, 10))}: ${esc(a.estorno_motivo)}</div>` : ''}
    ${(a.correcoes || []).map(c => `<div class="aviso info">Data corrigida de ${dataBR(c.antes)} para ${dataBR(c.depois)} por ${esc(c.por)} em ${dataBR(String(c.em).slice(0, 10))}: ${esc(c.motivo)}</div>`).join('')}
    <div class="acoes" style="margin-top:6px">${a.documentos.map(d => `<a class="btn" href="/api/apropriacao/arquivo?doc=${d.id}" target="_blank" rel="noopener">${esc(d.nome_original || 'evidência')}</a>`).join('')}
      ${comEstorno && !a.estornado_em && pode('apropriacao') ? `<button type="button" class="btn" data-apr-data="${a.id}" data-atual="${esc(a.data)}">Corrigir data</button><button type="button" class="btn" data-apr-estornar="${a.id}">Estornar</button>` : ''}</div>
    <small>Registrada por ${esc(a.registrado_por)} em ${dataBR(String(a.registrado_em).slice(0, 10))}</small></div>`;
}

// cadastro rápido do item novo, com o aviso de item parecido antes de gravar
$('#aprNovoBtn').addEventListener('click', () => {
  const f = $('#fItemNovo');
  f.hidden = false; $('#novoParecidos').innerHTML = '';
  if ($('#aprGrupo').value) f.grupo.value = $('#aprGrupo').value;
  if ($('#aprTipo').value) f.classificacao.value = $('#aprTipo').value;
  if (!f.descricao.value && $('#aprBusca').value.trim()) f.descricao.value = $('#aprBusca').value.trim().toUpperCase();
  f.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
$('#novoCancelar').addEventListener('click', () => { $('#fItemNovo').hidden = true; });
$('#fItemNovo').addEventListener('submit', ev => { ev.preventDefault(); aprGravarNovo(false); });
async function aprGravarNovo(confirmar) {
  const f = $('#fItemNovo'), o = formObj(f);
  const r = await acao(() => api('/api/base-custo/item-novo', { grupo: o.grupo, classificacao: o.classificacao, descricao: o.descricao,
    unidade: o.unidade, preco_proposto: o.preco_proposto, fonte_preco: o.fonte_preco, fonte_ref: o.fonte_ref, justificativa: o.justificativa,
    atributos: Object.fromEntries(APR_ATRIBUTOS.map(k => [k, o[k]])), confirmar })).catch(() => null);
  if (!r) return;
  if (!r.gravado) {
    $('#novoParecidos').innerHTML = `<div class="aviso sugestao"><b>Parece um item que já existe. É esse?</b>${r.parecidos.map(p => `
      <div class="acoes" style="margin-top:6px;justify-content:space-between"><span>${aprNome(p)} ${aprEtiqueta(p)} <small>(${p.semelhanca}% parecido)</small></span>
      <button type="button" class="btn" data-apr-usar="${esc(p.ref)}">É esse</button></div>`).join('')}
      <div class="acoes" style="margin-top:8px"><button type="button" class="btn prim" data-apr-novo-confirmar="1">Não, é outro: cadastrar o item novo</button></div></div>`;
    return;
  }
  toast(`Item novo ${r.item.item} cadastrado como a aprovar. Já pode receber a apropriação.`, 'ok');
  f.reset(); f.hidden = true; $('#novoParecidos').innerHTML = '';
  aprEscolher(r.item.ref, true);
}

/* ---------------------------------------------------------------- Medição: medível com restrição e itens a aprovar */
async function aprCarregarRestricoes(medId) {
  const r = await api('/api/medicao/restricoes' + (medId ? '?medicao=' + medId : '')).catch(() => null); if (!r) return;
  APR.rest = r;
  const usadas = r.restricoes.filter(x => r.totais[x.id] != null), fv = $('#medRestFiltro').value, gv = $('#medRestGrupo').value;
  $('#medRestFiltro').innerHTML = '<option value="">Todas</option>' + usadas.map(x => `<option value="${x.id}">${esc(x.letra)} · ${esc(x.rotulo)}</option>`).join('');
  $('#medRestGrupo').innerHTML = '<option value="">Todos</option>' + r.grupos.map(g => `<option>${esc(g)}</option>`).join('');
  $('#medRestFiltro').value = usadas.some(x => x.id === fv) ? fv : '';
  $('#medRestGrupo').value = r.grupos.includes(gv) ? gv : '';
  $('#medRestTotais').innerHTML = `<div class="kpis"><div class="kpi"><span>Total parado (sem BDI)</span><b>${reais(r.total)}</b></div>
    ${usadas.map(x => `<div class="kpi"><span>${esc(x.letra)} · ${esc(x.rotulo)}</span><b>${reais(r.totais[x.id])}</b></div>`).join('')}</div>`;
  aprRenderRestricoes();
  aprRenderItensAprovar(r.itens_a_aprovar);
}
function aprRenderRestricoes() {
  const r = APR.rest; if (!r) return;
  const f = $('#medRestFiltro').value, g = $('#medRestGrupo').value, rot = Object.fromEntries(r.restricoes.map(x => [x.id, x]));
  const ls = r.linhas.filter(l => (!f || l.tags.includes(f)) && (!g || l.grupo === g));
  $('#medRestricoes').className = ls.length ? '' : 'vazio';
  $('#medRestricoes').innerHTML = ls.length ? tabelaHtml('<th>Restrição</th><th>Origem</th><th>Item</th><th class="n">Quantidade</th><th class="n">Valor parado</th><th class="n">Dias</th><th>Ação que libera · quem faz</th>',
    ls.map(l => `<tr><td>${l.tags.map(t => `<span class="chip forte">${esc(rot[t].letra)} · ${esc(rot[t].rotulo)}</span>`).join(' ')}</td>
      <td>${esc(l.origem)}${l.executor ? `<br><small>${esc(l.executor)}</small>` : ''}</td>
      <td>${l.item ? `<b>${esc(l.item_bm || l.item)}</b> ` : ''}${esc(l.descricao || '')}</td>
      <td class="n">${l.quantidade == null ? '—' : nf(l.quantidade, 3) + ' ' + esc(l.unidade || '')}</td>
      <td class="n"><b>${reais(l.valor)}</b>${l.estimado ? '<br><small>estimado</small>' : ''}</td><td class="n">${l.dias ?? '—'}</td>
      <td class="rest-acao"><b>${esc(l.acao)}</b><br><small>${esc(l.quem)}</small></td></tr>`)) : 'Nada parado com este filtro.';
}
$('#medRestFiltro').addEventListener('change', aprRenderRestricoes);
$('#medRestGrupo').addEventListener('change', aprRenderRestricoes);
$('#medRestCodigo').addEventListener('click', () => $('#itensAprovar').scrollIntoView({ behavior: 'smooth', block: 'start' }));
// a esteira do cadastro fica na ficha do trecho (Mapa iluminado): a lista leva a cada trecho parado
$('#medRestEsteira').addEventListener('click', async () => {
  const lst = await api('/api/esteira').catch(() => []);
  abrirListaIlu('Cadastro parado', lst.filter(c => ['3_RECEBIDO', '4_GDOC_ANALISE', '5A_NEGADO'].includes(c.etapa)).map(c => c.ponto));
});

function aprRenderItensAprovar(itens) {
  const el = $('#medItensAprovar');
  el.className = itens.length ? '' : 'vazio';
  el.innerHTML = itens.length ? itens.map(it => `<div class="registro"><div><b>${aprNome(it)}</b>${aprEtiqueta(it)}</div>
      <small>${esc(it.descricao)}</small><br>
      <small>${it.tipo_ref === 'BM' ? `código provisório ${esc(it.codigo || '—')} · ${esc(it.grupo)} · ${reais(it.preco)} / ${esc(it.unidade)}`
        : `item novo · ${esc(it.grupo)} · ${esc(it.classificacao)} · preço proposto ${reais(it.novo.preco_proposto)} (${esc(it.novo.fonte_preco)}${it.novo.fonte_ref ? ' ' + esc(it.novo.fonte_ref) : ''}) · proposto por ${esc(it.novo.proposto_por)} · ${esc(it.novo.justificativa)}`}
        ${it.codigo_oficial ? ` · <b>código oficial ${esc(it.codigo_oficial)}</b>${it.conciliado ? ' · ' + esc(it.conciliado) : ''}` : ''}
        ${it.novo && it.novo.motivo ? ` · reprovado: ${esc(it.novo.motivo)}` : ''}</small>
      ${it.valor_parado ? `<div style="margin-top:4px"><span class="chip forte">valor parado ${reais(it.valor_parado)}</span></div>` : ''}
      ${it.situacao === 'A_APROVAR' && pode('medicao') ? `<div class="acoes" style="margin-top:6px">${it.tipo_ref === 'BM'
        ? `<button type="button" class="btn" data-apr-cod="${esc(it.ref)}">Registrar o código oficial</button>`
        : `<button type="button" class="btn" data-apr-aprovar="${esc(it.ref)}">Aprovar</button><button type="button" class="btn" data-apr-reprovar="${esc(it.ref)}">Reprovar</button>`}</div>
        <div data-apr-form="${esc(it.ref)}"></div>` : ''}</div>`).join('') : 'Nenhum item a aprovar.';
}

// "15/10/2026" ou "2026-10-15" → "2026-10-15" (ou null)
const aprIso = t => { const m = String(t || '').trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  return m ? `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}` : (/^\d{4}-\d{2}-\d{2}$/.test(String(t || '').trim()) ? String(t).trim() : null); };

document.addEventListener('click', async ev => {
  const cd = ev.target.closest('[data-apr-data]');
  if (cd) {                                                // a data errada se corrige sem estorno; a de antes fica guardada
    const txt = prompt('Data em que o serviço foi feito (dd/mm/aaaa):', dataBR(cd.dataset.atual));
    if (txt === null) return;
    const data = aprIso(txt);
    if (!data) { toast('Data inválida: use dd/mm/aaaa.', 'erro'); return; }
    const motivo = prompt('Motivo da correção da data (a data de antes fica no histórico):');
    if (!motivo || !motivo.trim()) return;
    const r = await acao(() => api('/api/apropriacao/corrigir-data', { apropriacao_id: +cd.dataset.aprData, data, motivo }),
      'Data corrigida.').catch(() => null);
    if (r) { aprCarregarLista(); if (APR.item) aprEscolher(APR.item.ref, false); }
    return;
  }
  const est = ev.target.closest('[data-apr-estornar]');
  if (est) {
    const motivo = prompt('Motivo do estorno (a apropriação fica riscada; nada é apagado):');
    if (!motivo || !motivo.trim()) return;
    const r = await acao(() => api('/api/apropriacao/estornar', { apropriacao_id: +est.dataset.aprEstornar, motivo }), 'Apropriação estornada.').catch(() => null);
    if (r) { aprCarregarLista(); if (APR.item) aprEscolher(APR.item.ref, false); }
    return;
  }
  if (ev.target.closest('[data-apr-ir]')) {                // do cartão do item para o formulário da apropriação
    $('#fApr').scrollIntoView({ behavior: 'smooth', block: 'start' });
    setTimeout(() => $('#fApr').quantidade.focus({ preventScroll: true }), 350);
    return;
  }
  const usar = ev.target.closest('[data-apr-usar]');
  if (usar) { $('#fItemNovo').hidden = true; $('#novoParecidos').innerHTML = ''; aprEscolher(usar.dataset.aprUsar, true); return; }
  if (ev.target.closest('[data-apr-novo-confirmar]')) { aprGravarNovo(true); return; }
  const cod = ev.target.closest('[data-apr-cod], [data-apr-aprovar]');
  if (cod) {
    const ref = cod.dataset.aprCod || cod.dataset.aprAprovar, novo = !!cod.dataset.aprAprovar;
    const alvo = [...document.querySelectorAll('[data-apr-form]')].find(x => x.dataset.aprForm === ref);
    alvo.innerHTML = `<form class="form-inline" data-apr-enviar="${esc(ref)}" data-novo="${novo ? '1' : ''}">
      <label>Código oficial Caesb<input name="codigo" required inputmode="numeric"></label>
      ${novo ? '<label>Preço aprovado (R$, sem BDI)<input type="number" step="0.01" min="0" name="preco_aprovado" required></label>' : ''}
      <label>Data do documento<input type="date" name="data" required max="${hoje()}"></label>
      <label>Ofício ou memorando (PDF)<input type="file" name="documento" accept="application/pdf,.pdf" required></label>
      <button class="btn prim">${novo ? 'Aprovar o item' : 'Registrar o código'}</button></form>`;
    return;
  }
  const rep = ev.target.closest('[data-apr-reprovar]');
  if (rep) {
    const motivo = prompt('Motivo da reprovação (fica no histórico):');
    if (!motivo || !motivo.trim()) return;
    const r = await acao(() => api('/api/base-custo/decidir', { item_ref: rep.dataset.aprReprovar, acao: 'REPROVAR', motivo }), 'Item reprovado.').catch(() => null);
    if (r) aprCarregarRestricoes(MEDICAO_ATUAL);
  }
});
document.addEventListener('submit', async ev => {
  const f = ev.target.closest('[data-apr-enviar]'); if (!f) return;
  ev.preventDefault();
  const o = formObj(f), arq = f.documento.files[0], novo = !!f.dataset.novo;
  if (!arq) return toast('Envie o ofício ou o memorando da Caesb em PDF.', 'erro');
  const corpo = { item_ref: f.dataset.aprEnviar, codigo: o.codigo, data: o.data, documento_b64: await lerOriginal(arq), documento_nome: arq.name };
  if (novo) Object.assign(corpo, { acao: 'APROVAR', preco_aprovado: o.preco_aprovado });
  const r = await acao(() => api(novo ? '/api/base-custo/decidir' : '/api/base-custo/codigo-oficial', corpo)).catch(() => null);
  if (!r) return;
  toast(`${novo ? 'Item aprovado' : 'Código oficial registrado'}${r.liberados ? `: ${r.liberados} lançamento(s) entraram na medição de teste aberta` : ''}.`, 'ok');
  carregarMedicao(); driveEmSegundoPlano();
});
