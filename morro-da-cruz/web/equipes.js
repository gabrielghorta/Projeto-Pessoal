/* D-212: o projeto tem zonas; a obra tem equipes criadas e montadas pelo usuário. */
const EQUIPES_UI = { id: null, dados: null };
async function atualizarEquipes() {
  RESUMO = await api('/api/resumo'); preencherEquipes();
  if (typeof PLN !== 'undefined' && PLN.equipe && !RESUMO.equipes.some(e => e.id === PLN.equipe)) {
    PLN.equipe = null; PLN.equipeFixa = false;
  }
}
async function carregarEquipes() {
  if (PAGINA.equipes === 'histograma') return carregarHistograma();
  const d = EQUIPES_UI.dados = await api('/api/equipes');
  if (!d.equipes.some(e => e.id === EQUIPES_UI.id)) EQUIPES_UI.id = null;
  const podeEditar = pode('equipes');
  $('#equipesCadastro').innerHTML = `<div class="grade"><div class="painel"><h3>Equipes da obra</h3>
    <p>Planejamento inicial: duas da Ankara, duas do Empreiteiro 1 e duas do Empreiteiro 2. Você pode criar outras quando precisar.</p>
    ${d.equipes.length ? d.equipes.map(e => `<button type="button" class="btn grande" data-eq-abrir="${esc(e.id)}" aria-pressed="${e.id === EQUIPES_UI.id}" style="display:block;width:100%;margin-bottom:8px;text-align:left">
      <b>${esc(equipeRotulo(e))}</b><br><small>${esc(d.empresas[e.empresa] || '')} · ${e.integrantes} integrante(s) · ${e.maquinas} máquina(s)${!e.integrantes ? ' · Adicione integrantes para usar' : ''}</small></button>`).join('')
      : '<p class="vazio">Nenhuma equipe cadastrada. Crie a primeira equipe e adicione seus integrantes.</p>'}
    ${podeEditar ? `<h3 style="margin-top:20px">Criar equipe</h3><form id="fNovaEquipe"><label>Empresa<select name="empresa" required><option value="">Escolha a empresa</option>${Object.entries(d.empresas).map(([k,v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('')}</select></label>
      <label>Nome da equipe<input name="nome" maxlength="100" placeholder="Ex.: Subadutora ou Caixas e hidromecânico"></label>
      <p class="vazio">As siglas são A1, A2… para Ankara; E1.1, E1.2… para Empreiteiro 1; E2.1, E2.2… para Empreiteiro 2.</p>
      <div class="acoes"><button class="btn prim">Criar equipe</button></div></form>` : ''}</div>
    <div class="painel" id="eqIntegrantes"><p>Escolha uma equipe para designar os integrantes e as máquinas.</p></div></div>`;
  if (EQUIPES_UI.id) await renderEquipe();
}
async function renderEquipe() {
  const e = EQUIPES_UI.dados.equipes.find(e => e.id === EQUIPES_UI.id); if (!e) return;
  const r = await api('/api/equipe?id=' + encodeURIComponent(e.id));
  if (EQUIPES_UI.id !== e.id) return;
  const editavel = pode('equipes');
  $('#eqIntegrantes').innerHTML = `<h3>${esc(equipeRotulo(e))}</h3>
    <p>${r.funcionarios.length ? `${r.funcionarios.length} integrante(s) designado(s).` : 'Esta equipe ainda não pode receber serviços: designe seus integrantes.'}</p>
    ${r.funcionarios.map(f => `<div class="registro"><b>${esc(f.nome)}</b> · ${esc(f.funcao || 'Função não informada')}
      ${editavel ? `<button type="button" class="btn" data-eq-retirar="${f.id}">Retirar da equipe</button>` : ''}</div>`).join('')}
    ${editavel ? `<form id="fEquipeMembro"><h4>Designar integrante</h4>
      <label>Pessoa já cadastrada<select name="funcionario_id"><option value="">Cadastrar novo integrante</option>${EQUIPES_UI.dados.disponiveis.map(f => `<option value="${f.id}">${esc(f.nome)} · ${esc(f.funcao || 'sem função')}</option>`).join('')}</select></label>
      <div class="linha"><label>Nome<input name="nome" maxlength="150"></label><label>Função<input name="funcao" maxlength="100" placeholder="Encarregado, encanador, ajudante…"></label></div>
      <div class="acoes"><button class="btn prim">Designar integrante</button></div></form>` : ''}
    <h4>Máquinas</h4>${r.maquinas.map(m => `<div class="registro">${esc(m.descricao)}</div>`).join('') || '<p class="vazio">Nenhuma máquina designada.</p>'}
    ${editavel ? `<form id="fEquipeMaquina"><label>Máquina<input name="descricao" maxlength="150" required placeholder="Retroescavadeira, compactador…"></label><div class="acoes"><button class="btn">Adicionar máquina</button></div></form>
      <p style="margin-top:20px">O login do encarregado é vinculado a esta equipe em Usuários e histórico.</p>
      <button type="button" class="btn" data-eq-excluir="${esc(e.id)}">Excluir equipe</button>` : ''}`;
  $('#eqIntegrantes').dataset.equipe = e.id;
}
$('#equipesCadastro').addEventListener('click', async ev => {
  const abrir = ev.target.closest('[data-eq-abrir]');
  if (abrir) { EQUIPES_UI.id = abrir.dataset.eqAbrir; return carregarEquipes(); }
  const retirar = ev.target.closest('[data-eq-retirar]');
  if (retirar) {
    await acao(() => api('/api/equipes/retirar-integrante', {equipe_id:EQUIPES_UI.id, funcionario_id:+retirar.dataset.eqRetirar}), 'Integrante retirado da equipe.');
    await atualizarEquipes(); return carregarEquipes();
  }
  const excluir = ev.target.closest('[data-eq-excluir]');
  if (excluir && confirm('Excluir esta equipe das opções de novos serviços? Os registros anteriores permanecem no histórico.')) {
    await acao(() => api('/api/equipes/excluir', {equipe_id:excluir.dataset.eqExcluir}), 'Equipe excluída.');
    EQUIPES_UI.id = null; await atualizarEquipes(); return carregarEquipes();
  }
});
$('#equipesCadastro').addEventListener('submit', async ev => {
  ev.preventDefault(); const f = ev.target, b = formObj(f);
  if (f.id === 'fNovaEquipe') {
    const r = await acao(() => api('/api/equipes/criar', b), 'Equipe criada. Agora designe os integrantes.'); EQUIPES_UI.id = r.id;
  } else if (f.id === 'fEquipeMembro') await acao(() => api('/api/funcionario', {...b,equipe_id:EQUIPES_UI.id}), 'Integrante designado.');
  else if (f.id === 'fEquipeMaquina') await acao(() => api('/api/maquina', {...b,equipe_id:EQUIPES_UI.id}), 'Máquina adicionada.');
  else return;
  await atualizarEquipes(); await carregarEquipes();
});
