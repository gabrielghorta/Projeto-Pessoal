/* Pedir material: nomes de uso, destino por toque e apenas as solicitações permitidas pela sessão. */
const SOL_UI = { dados: null, tipo: '', tamanho: '', busca: '', carrinho: [], frente: '', obs: '' };
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
  if (USUARIO.restrito_a_equipe) SOL_UI.frente = USUARIO.equipe_id;
  const box = $('#solicitarConteudo');
  box.innerHTML = `<div class="sol-grade"><div class="painel sol-pedir"><h2>O que precisa?</h2>
    <div id="solTipos" class="sol-botoes"></div><label>Buscar material<input id="solBusca" type="search" placeholder="Ex.: luva 110" value="${esc(SOL_UI.busca)}"></label>
    <div id="solTamanhos" class="sol-botoes"></div><div id="solMateriais" class="sol-materiais"></div>
    <button type="button" class="btn grande" id="solNaoAchei">Não achei: escrever ou tirar foto</button>
    <form id="solAvulso" class="form" hidden><label>O que precisa?<input name="descricao" maxlength="600" placeholder="Escreva como você conhece o material"></label>
      <label>Tirar foto ou escolher imagem<input name="foto" type="file" accept="image/jpeg,image/png" capture="environment"></label>
      <label>Unidade<select name="unidade">${Object.entries(SOL_UN).map(([v,n]) => `<option value="${v}">${n}</option>`).join('')}</select></label>
      <button class="btn prim">Adicionar à solicitação</button></form>
    <h2>Quanto?</h2><div id="solCarrinho"></div><h2>Para onde?</h2><div id="solFrentes" class="sol-botoes"></div>
    <label>Observação (opcional)<textarea id="solObs" maxlength="600" rows="2">${esc(SOL_UI.obs)}</textarea></label>
    <button type="button" class="btn prim grande" id="solEnviar">Enviar solicitação</button><p id="solMensagem" role="status"></p></div>
    <div class="painel"><h2>Meus pedidos</h2><div id="solMeus"></div>${pode('compras_aprovar') ? `<h2>Para a engenharia</h2><div id="solAprovar"></div>
      <details class="nota-mais"><summary>Os outros pedidos da obra</summary><div id="solOutros"></div></details>` : ''}</div></div>`;
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
  $('#solFrentes').innerHTML = SOL_UI.dados.frentes.filter(f => !USUARIO.restrito_a_equipe || f.id === USUARIO.equipe_id).map(f => `<button type="button" class="btn" data-sol-frente="${esc(f.id)}" aria-pressed="${SOL_UI.frente === f.id}">${esc(solFrente(f.id))}</button>`).join('');
}
function solCard(s, decidir, quem = decidir) {
  const estados = { ABERTA: ['Aguardando', 'amarelo'], APROVADA: ['Aprovado', 'azul'], RECUSADA: ['Recusado', 'vermelho'], CHEGOU: ['Chegou', 'verde'], CANCELADA: ['Cancelado', ''] };
  const st = estados[s.situacao] || [s.situacao, ''];
  return `<div class="registro sol-card" data-sol-id="${s.id}"><b>Solicitação ${s.id} · ${esc(solFrente(s.frente_id))}</b> <span class="chip ${st[1]}">${esc(st[0])}</span>
    <p>${esc(dataBR(s.data))}${quem ? ' · ' + esc(s.solicitante) : ''}</p>
    ${[...s.itens, ...s.avulsos].map(m => `<div><b>${esc(m.nome)}</b> · ${nf(m.quantidade, 3)} ${esc(solUn(m.quantidade, m.unidade_nome))}
      ${m.documento_id ? `<button type="button" class="btn" data-sol-foto="${m.id}">Ver foto</button><div data-sol-imagem="${m.id}"></div>` : ''}</div>`).join('')}
    ${s.motivo ? `<p>${esc(s.motivo)}</p>` : ''}${s.decisao_motivo ? `<p>Motivo: ${esc(s.decisao_motivo)}</p>` : ''}
    ${decidir ? s.avulsos.filter(x => !x.material_id).map(x => `<fieldset data-sol-avulso="${x.id}"><legend>${esc(x.descricao)}</legend>
      <label>Material<select data-sol-resolver><option value="">Escolha o material</option>${SOL_UI.dados.catalogo.map(m => `<option value="${esc(m.id)}">${esc(m.nome)} (${esc(m.unidade_nome)})</option>`).join('')}</select></label>
      <label>Quantidade na unidade do material<input type="number" inputmode="decimal" min="0.001" step="any" data-sol-convertida value="${x.quantidade}"></label></fieldset>`).join('') + '<div class="acoes"><button type="button" class="btn ok" data-sol-decidir="sim">Aprovar</button><button type="button" class="btn recusar" data-sol-decidir="nao">Recusar</button></div>' : ''}</div>`;
}
function renderSolPedidos() {
  const ss = SOL_UI.dados.solicitacoes, meus = ss.filter(s => s.solicitante === USUARIO.login);
  $('#solMeus').innerHTML = meus.map(s => solCard(s, false)).join('') || '<p>Você ainda não fez solicitações.</p>';
  const box = $('#solAprovar'); if (box) box.innerHTML = ss.filter(s => s.status === 'ABERTA' && s.solicitante !== USUARIO.login).map(s => solCard(s, true)).join('') || '<p>Nenhuma solicitação aguardando sua decisão.</p>';
  // quem aprova acompanha os já decididos dos outros (aprovado, recusado, chegou)
  const outros = $('#solOutros'); if (outros) outros.innerHTML = ss.filter(s => s.status !== 'ABERTA' && s.solicitante !== USUARIO.login).slice(0, 30).map(s => solCard(s, false, true)).join('') || '<p>Nenhum.</p>';
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
  if (b.id === 'solNaoAchei') { $('#solAvulso').hidden = !$('#solAvulso').hidden; return; }
  if (b.id === 'solEnviar') {
    b.disabled = true;
    const r = await acao(() => api('/api/solicitacao', { frente_id: SOL_UI.frente, observacao: SOL_UI.obs, itens: SOL_UI.carrinho }), 'Solicitação enviada.').catch(() => null);
    b.disabled = false; if (r) { SOL_UI.carrinho = []; SOL_UI.obs = ''; await carregarSolicitacoes(); } return;
  }
  if (b.dataset.solFoto) {
    const r = await acao(() => api('/api/solicitacao/foto?id=' + b.dataset.solFoto)).catch(() => null);
    if (r) { const img = new Image(); img.src = r.imagem; img.alt = 'Material solicitado'; img.className = 'sol-foto'; $('[data-sol-imagem="' + b.dataset.solFoto + '"]', b.closest('.sol-card')).replaceChildren(img); } return;
  }
  if (b.dataset.solDecidir) {
    const card = b.closest('[data-sol-id]'), aprovar = b.dataset.solDecidir === 'sim', motivo = aprovar ? null : prompt('Por que foi recusado?');
    if (!aprovar && !motivo) return;
    const avulsos = $$('[data-sol-avulso]', card).map(f => ({ id: f.dataset.solAvulso, material_id: $('[data-sol-resolver]', f).value, quantidade: +$('[data-sol-convertida]', f).value }));
    const r = await acao(() => api('/api/solicitacao/decidir', { solicitacao_id: card.dataset.solId, aprovar, motivo, avulsos }), aprovar ? 'Solicitação aprovada.' : 'Solicitação recusada.').catch(() => null);
    if (r) await carregarSolicitacoes();
  }
});
