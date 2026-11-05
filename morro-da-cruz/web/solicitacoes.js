/* Compras › Requisições (D-196): pedir material (nomes de uso, destino por toque) e acompanhar as requisições, sem aprovação. */
const SOL_UI = { dados: null, tipo: '', tamanho: '', busca: '', carrinho: [], frente: '', obs: '', novo: false };
const SOL_UN = { UN: 'unidades', M: 'metros', 'PÇ': 'peças', KG: 'quilos', M2: 'metros quadrados', M3: 'metros cúbicos' };
const solTexto = x => String(x || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
// o nome da frente no botão: "Zona 08", "Adutora", "Caixas hidráulicas" (o nome da equipe sem "EQUIPE" e sem a sigla)
const solFrente = id => {
  if (/^Zona\d\d$/.test(id || '')) return id.replace('Zona', 'Zona ');
  const f = ((SOL_UI.dados || {}).frentes || []).find(x => x.id === id), nome = String(f ? f.nome : id || '').replace(/^EQUIPE\s+/i, '').replace(/^\S+\s+—\s+/, '');
  return nome.charAt(0).toUpperCase() + nome.slice(1).toLowerCase();
};
// "1 unidade", "3 unidades", "1 metro cúbico"
const solUn = (q, nome) => Math.abs(q - 1) > 1e-9 ? nome : String(nome || '').replace(/(ões|s)\b/g, (m, f) => f === 'ões' ? 'ão' : '');
async function carregarSolicitacoes() {
  SOL_UI.dados = await api('/api/solicitacoes');
  if (!SOL_UI.dados.frentes.some(f => f.id === SOL_UI.frente)) SOL_UI.frente = SOL_UI.dados.frentes.length === 1 ? SOL_UI.dados.frentes[0].id : '';
  const box = $('#solicitarConteudo');
  // quem compra vê a lista primeiro e abre o formulário em "Nova requisição"; quem só pede vê o formulário aberto
  const obra = podeTela('compras'), aberto = !obra || SOL_UI.novo || SOL_UI.carrinho.length > 0;
  box.innerHTML = `${obra ? `<div class="acoes" style="margin:0 0 12px"><button type="button" class="btn prim grande" id="solNova" aria-expanded="${aberto}">${aberto ? 'Fechar a nova requisição' : 'Nova requisição'}</button></div>` : ''}
    <div class="sol-grade${aberto ? '' : ' so-lista'}"><div class="painel sol-pedir"${aberto ? '' : ' hidden'}><h2>O que precisa?</h2>
    <div id="solTipos" class="sol-botoes"></div><label>Buscar material<input id="solBusca" type="search" placeholder="Ex.: luva 110" value="${esc(SOL_UI.busca)}"></label>
    <div id="solTamanhos" class="sol-botoes"></div><div id="solMateriais" class="sol-materiais"></div>
    <button type="button" class="btn grande" id="solNaoAchei">Não achei: escrever ou tirar foto</button>
    <form id="solAvulso" class="form" hidden><label>O que precisa?<input name="descricao" maxlength="600" placeholder="Escreva como você conhece o material"></label>
      <label>Tirar foto ou escolher imagem<input name="foto" type="file" accept="image/jpeg,image/png" capture="environment"></label>
      <label>Unidade<select name="unidade">${Object.entries(SOL_UN).map(([v,n]) => `<option value="${v}">${n}</option>`).join('')}</select></label>
      <button class="btn prim">Adicionar à requisição</button></form>
    <h2>Quanto?</h2><div id="solCarrinho"></div><h2>Para onde?</h2><div id="solFrentes" class="sol-botoes"></div>
    <label>Observação (opcional)<textarea id="solObs" maxlength="600" rows="2">${esc(SOL_UI.obs)}</textarea></label>
    <button type="button" class="btn prim grande" id="solEnviar">Enviar requisição</button><p id="solMensagem" role="status"></p></div>
    <div class="painel"><h2>${podeTela('compras') ? 'Requisições da obra' : 'Minhas requisições'}</h2><div id="solMeus"></div></div></div>`;
  renderSolCatalogo(); renderSolCarrinho(); renderSolFrentes(); renderSolPedidos();
  $('#solBusca').addEventListener('input', e => { SOL_UI.busca = e.target.value; renderSolCatalogo(); });
  $('#solObs').addEventListener('input', e => { SOL_UI.obs = e.target.value; });
  $('#solAvulso').addEventListener('submit', async e => {
    e.preventDefault(); const f = e.target, foto = f.foto.files[0], descricao = f.descricao.value.trim();
    if (!descricao && !foto) return toast('Escreva ou tire uma foto.', 'erro');
    if (foto && foto.size > 8 * 1024 * 1024) return toast('Use uma foto de até 8 MB.', 'erro');
    SOL_UI.carrinho.push({ descricao: descricao || 'Material da foto', nome: descricao || 'Material da foto', foto_b64: foto ? await lerOriginal(foto) : null,
      quantidade: 1, unidade: f.unidade.value, unidade_nome: SOL_UN[f.unidade.value] });
    f.reset(); f.hidden = true; renderSolCarrinho();
  });
}
function renderSolCatalogo() {
  const d = SOL_UI, cat = d.dados.catalogo;
  const botoes = (valores, campo, atual) => valores.map(v => `<button type="button" class="btn" data-sol-${campo}="${esc(v)}" aria-pressed="${atual === v}">${esc(v || 'Todos')}</button>`).join('');
  $('#solTipos').innerHTML = botoes(['', ...new Set(cat.map(m => m.tipo))], 'tipo', d.tipo);
  // o catálogo já vem na ordem dos tipos e, dentro deles, da bitola menor para a maior
  const grupo = cat.filter(m => !d.tipo || m.tipo === d.tipo), tamanhos = [...new Set(grupo.map(m => m.tamanho).filter(Boolean))];
  $('#solTamanhos').innerHTML = d.tipo && tamanhos.length > 1 ? botoes(['', ...tamanhos], 'tamanho', d.tamanho) : '';
  const palavras = solTexto(d.busca).split(/\s+/).filter(Boolean);
  const filtrados = grupo.filter(m => (!d.tamanho || m.tamanho === d.tamanho) && palavras.every(p => solTexto(m.nome + ' ' + m.descricao).includes(p)));
  $('#solMateriais').innerHTML = !d.tipo && !palavras.length ? '<p>Toque no tipo ou escreva na busca.</p>' : filtrados.length
    ? filtrados.map(m => { const no = SOL_UI.carrinho.find(x => x.material_id === m.id);
      return `<button type="button" class="btn sol-material${no ? ' no-pedido' : ''}" data-sol-material="${esc(m.id)}"><b>${esc(m.nome)}</b><small>${no ? `no pedido: ${nf(no.quantidade, 3)} ${esc(solUn(no.quantidade, m.unidade_nome))}` : esc(m.unidade_nome)}${m.caesb ? ' · fornecido pela Caesb' : ''}</small></button>`; }).join('')
    : '<p>Não encontrou? Use o botão abaixo.</p>';
}
function renderSolCarrinho() {
  $('#solCarrinho').innerHTML = SOL_UI.carrinho.length ? SOL_UI.carrinho.map((m,i) => `<div class="sol-item" data-sol-item="${i}"><b>${esc(m.nome)}</b>
    <div class="sol-quantidade"><button type="button" class="btn" data-sol-menos aria-label="Diminuir quantidade">−</button>
    <input type="number" inputmode="decimal" min="0.001" step="any" value="${m.quantidade}" aria-label="Quantidade de ${esc(m.nome)}" data-sol-qtd>
    <button type="button" class="btn" data-sol-mais aria-label="Aumentar quantidade">+</button><span>${esc(m.unidade_nome)}</span></div>
    <button type="button" class="btn" data-sol-tirar>Retirar</button></div>`).join('') : '<p>Nenhum material escolhido.</p>';
}
function renderSolFrentes() {
  $('#solFrentes').innerHTML = SOL_UI.dados.frentes.map(f => `<button type="button" class="btn" data-sol-frente="${esc(f.id)}" aria-pressed="${SOL_UI.frente === f.id}">${esc(solFrente(f.id))}</button>`).join('') || '<p>A engenharia precisa programar a equipe em uma zona antes da requisição.</p>';
}
const solMeu = s => String(s.solicitante).toLowerCase() === String(USUARIO.login).toLowerCase();
// D-196: a requisição não tem aprovação. Aberta (sem nota) → aguardando a entrega (a nota foi ligada) → recebida; ou cancelada
const SOL_ESTADOS = { ABERTA: ['Aberta', 'amarelo'], AGUARDANDO: ['Aguardando a entrega', 'azul'], RECEBIDA: ['Recebida', 'verde'], CANCELADA: ['Cancelada', ''] };
const solAberta = s => s.situacao === 'ABERTA' || s.situacao === 'AGUARDANDO';
const solLista = (l, titulo) => l.length ? `<p class="vazio" style="margin:6px 0 4px">${titulo}: ${l.map(f => `${esc(f.nome)} ${nf(f.quantidade, 3)} ${esc(solUn(f.quantidade, f.unidade_nome))}`).join(' · ')}</p>` : '';
function solCard(s, quem) {
  const st = SOL_ESTADOS[s.situacao] || [s.situacao, ''], foto = solMeu(s) || podeTela('compras');   // a foto: quem pediu e quem compra
  const identifica = solAberta(s) && pode('nf_confirmar'), cancela = solAberta(s) && (solMeu(s) || pode('requisicoes_cancelar'));
  return `<div class="registro sol-card" data-sol-id="${s.id}"><b>Requisição ${s.id} · ${esc(solFrente(s.frente_id))}</b> <span class="chip ${st[1]}">${esc(st[0])}</span>
    <p>${esc(dataBR(s.data))}${quem ? ' · ' + esc(s.solicitante) : ''}${s.status === 'CANCELADA' && s.decidida_por ? ` · cancelada por ${esc(s.decidida_por)}` : ''}${s.status === 'RECUSADA' ? ` · recusada por ${esc(s.decidida_por)} (antes da D-196)` : ''}</p>
    ${[...s.itens, ...s.avulsos].map(m => `<div><b>${esc(m.nome)}</b> · ${nf(m.quantidade, 3)} ${esc(solUn(m.quantidade, m.unidade_nome))}${'descricao' in m && !m.material_id ? ' <span class="chip amarelo">a identificar</span>' : ''}
      ${m.documento_id && foto ? `<button type="button" class="btn" data-sol-foto="${m.id}">Ver foto</button><div data-sol-imagem="${m.id}"></div>` : ''}</div>`).join('')}
    ${s.motivo ? `<p>${esc(s.motivo)}</p>` : ''}${s.decisao_motivo ? `<p>Motivo: ${esc(s.decisao_motivo)}</p>` : ''}
    ${(s.notas || []).length ? `<p>Nota${s.notas.length > 1 ? 's' : ''} ligada${s.notas.length > 1 ? 's' : ''}: NF ${s.notas.map(esc).join(', NF ')}</p>` : ''}
    ${solLista(s.sem_nota || [], 'Sem nota ainda')}${s.situacao === 'AGUARDANDO' || (s.notas || []).length ? solLista(s.falta || [], 'Falta chegar') : ''}
    ${s.situacao === 'ABERTA' && !(s.notas || []).length && podeTela('compras') ? '<p class="vazio" style="margin:4px 0">Quando a nota chegar, ligue a nota a esta requisição em <b>Compras › Notas fiscais</b>: ela passa a "aguardando a entrega".</p>' : ''}
    ${identifica ? s.avulsos.filter(x => !x.material_id).map(x => `<fieldset data-sol-avulso="${x.id}"><legend>Qual material é "${esc(x.descricao)}"?</legend>
      <label>Material<select data-sol-resolver><option value="">Escolha o material</option>${SOL_UI.dados.catalogo.map(m => `<option value="${esc(m.id)}">${esc(m.nome)} (${esc(m.unidade_nome)})</option>`).join('')}</select></label>
      <label>Quantidade na unidade do material<input type="number" inputmode="decimal" min="0.001" step="any" data-sol-convertida value="${x.quantidade}"></label></fieldset>`).join('') : ''}
    ${(identifica && s.a_identificar) || cancela ? `<div class="acoes">${identifica && s.a_identificar ? '<button type="button" class="btn ok" data-sol-identificar>Identificar</button>' : ''}${cancela ? `<button type="button" class="btn recusar" data-sol-cancelar>${(s.notas || []).length ? 'Cancelar o que falta' : 'Cancelar'}</button>` : ''}</div>` : ''}</div>`;
}
// Compras › Requisições: abertas em cima, aguardando a entrega no meio, recebidas e canceladas recolhidas embaixo.
// Quem abre Compras vê as da obra; quem só pede vê as suas
function renderSolPedidos() {
  const ss = SOL_UI.dados.solicitacoes, obra = podeTela('compras');
  const bloco = (titulo, l, vazio) => `<h3 style="margin:16px 0 8px">${titulo} (${l.length})</h3>${l.map(s => solCard(s, obra)).join('') || `<p class="vazio">${vazio}</p>`}`;
  const fechadas = ss.filter(s => !solAberta(s));
  $('#solMeus').innerHTML = bloco('Abertas', ss.filter(s => s.situacao === 'ABERTA'), 'Nenhuma requisição aberta.')
    + bloco('Aguardando a entrega', ss.filter(s => s.situacao === 'AGUARDANDO'), 'Nenhuma nota ligada esperando a entrega.')
    + `<details class="nota-mais" style="margin-top:16px"><summary>Recebidas e canceladas (${fechadas.length})</summary>${fechadas.slice(0, 60).map(s => solCard(s, obra)).join('') || '<p class="vazio">Nenhuma.</p>'}</details>`;
}
// Ver foto, Identificar e Cancelar: no cartão da requisição
async function solAcaoCard(b, recarregar) {
  if (b.dataset.solFoto) {
    const r = await acao(() => api('/api/solicitacao/foto?id=' + b.dataset.solFoto)).catch(() => null);
    if (r) { const img = new Image(); img.src = r.imagem; img.alt = 'Material solicitado'; img.className = 'sol-foto'; $('[data-sol-imagem="' + b.dataset.solFoto + '"]', b.closest('.sol-card')).replaceChildren(img); }
    return;
  }
  const card = b.closest('[data-sol-id]');
  if (b.hasAttribute('data-sol-identificar')) {
    const avulsos = $$('[data-sol-avulso]', card).map(f => ({ id: f.dataset.solAvulso, material_id: $('[data-sol-resolver]', f).value, quantidade: +$('[data-sol-convertida]', f).value }))
      .filter(x => x.material_id);
    if (!avulsos.length) return toast('Escolha o material.', 'erro');
    if (await acao(() => api('/api/solicitacao/identificar', { solicitacao_id: card.dataset.solId, avulsos }), 'Material identificado.').catch(() => null)) await recarregar();
    return;
  }
  if (b.hasAttribute('data-sol-cancelar')) {
    const motivo = prompt('Por que a requisição foi cancelada?'); if (!motivo || !motivo.trim()) return;
    if (await acao(() => api('/api/solicitacao/cancelar', { solicitacao_id: card.dataset.solId, motivo }), 'Requisição cancelada.').catch(() => null)) await recarregar();
  }
}
$('#solicitarConteudo').addEventListener('change', e => {
  if (e.target.matches('[data-sol-qtd]')) { SOL_UI.carrinho[+e.target.closest('[data-sol-item]').dataset.solItem].quantidade = +e.target.value; renderSolCatalogo(); }
});
$('#solicitarConteudo').addEventListener('click', async e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.hasAttribute('data-sol-tipo')) { SOL_UI.tipo = b.dataset.solTipo; SOL_UI.tamanho = ''; return renderSolCatalogo(); }
  if (b.hasAttribute('data-sol-tamanho')) { SOL_UI.tamanho = b.dataset.solTamanho; return renderSolCatalogo(); }
  if (b.dataset.solMaterial) {
    const m = SOL_UI.dados.catalogo.find(x => x.id === b.dataset.solMaterial), ja = SOL_UI.carrinho.find(x => x.material_id === m.id);
    if (ja) ja.quantidade++; else SOL_UI.carrinho.push({ material_id: m.id, nome: m.nome, quantidade: 1, unidade_nome: m.unidade_nome });
    const q = (ja || SOL_UI.carrinho[SOL_UI.carrinho.length - 1]).quantidade;
    toast(`${m.nome}: ${nf(q, 3)} ${solUn(q, m.unidade_nome)} no pedido. Acerte a quantidade em "Quanto?".`, 'ok');
    renderSolCatalogo(); return renderSolCarrinho();
  }
  const it = b.closest('[data-sol-item]');
  if (it) { const i = +it.dataset.solItem, m = SOL_UI.carrinho[i];
    if (b.hasAttribute('data-sol-tirar')) SOL_UI.carrinho.splice(i, 1);
    else { const q = Number(m.quantidade) || 0; m.quantidade = b.hasAttribute('data-sol-mais') ? q + 1 : q > 1 ? q - 1 : q; }   // o − para em 1
    renderSolCatalogo(); return renderSolCarrinho(); }
  if (b.dataset.solFrente) { SOL_UI.frente = b.dataset.solFrente; return renderSolFrentes(); }
  if (b.id === 'solNova') { SOL_UI.novo = b.getAttribute('aria-expanded') !== 'true'; return carregarSolicitacoes(); }
  if (b.id === 'solNaoAchei') { $('#solAvulso').hidden = !$('#solAvulso').hidden; return; }
  if (b.id === 'solEnviar') {
    b.disabled = true;
    const r = await acao(() => api('/api/solicitacao', { frente_id: SOL_UI.frente, observacao: SOL_UI.obs, itens: SOL_UI.carrinho }), 'Requisição enviada: ela entra aberta, sem aprovação.').catch(() => null);
    b.disabled = false; if (r) { SOL_UI.carrinho = []; SOL_UI.obs = ''; await carregarSolicitacoes(); } return;
  }
  if (b.dataset.solFoto || b.hasAttribute('data-sol-identificar') || b.hasAttribute('data-sol-cancelar')) return solAcaoCard(b, carregarSolicitacoes);
});
