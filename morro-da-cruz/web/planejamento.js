/* Planejamento: o mapa do Dados da obra e o cronograma do MS Project.
 * O mapa usa a mesma base do Mapa iluminado (iluminado.js: traçado do REV02 e o visor de arrastar e aproximar), sem as
 * plantas baixas: nem fotos de satélite nem divisão das PBs, só as zonas, os nomes, os trechos, os nós e os pinos
 * (pedido do responsável em 22/10/2026; também deixa a aba leve, sem baixar imagem nenhuma).
 * Aqui se escolhem trechos: o toque escolhe um; Ctrl + clique (ou o botão "Juntar trechos", no celular) junta vários.
 * O servidor completa a seleção (/api/dados-obra/selecao): cada linha traz o trecho físico inteiro e o nó entre dois
 * trechos escolhidos entra sozinho. Com a seleção, o painel ao lado programa a equipe (período e dias), libera o material
 * do dia (check-in), reserva para um dia que ainda não chegou e recebe a devolução do fim do dia (check-out). */

/* ---------------------------------------------------------------- estado */
const PLAN = [   // de baixo para cima no desenho: o último fica por cima
  { id: 'livre', nome: 'Sem programação', cor: '#8C8C8C', tracejado: '5 4' },
  { id: 'liberado', nome: 'Liberado pela topografia', cor: '#6CB8F0' },
  { id: 'feito', nome: 'Concluído (reaterrado)', cor: '#F2F2F2', opacidade: 0.7 },
  { id: 'execucao', nome: 'Começado, sem equipe no dia', cor: '#F15922', tracejado: '9 6' },
  { id: 'programado', nome: 'Programado para os próximos dias', cor: '#FFD23F', tracejado: '9 6' },
  { id: 'hoje', nome: 'Programado para o dia', cor: '#FFD23F' },
  { id: 'campo', nome: 'Equipe trabalhando no dia (check-in)', cor: '#F15922' },
];
const PLN = { pronto: false, vb: null, base: null, anim: 0, zona: null, pop: null, multi: false, dia: null, est: null,
  sel: [], nos: [], resp: null, aba: null, pedido: 0, equipe: null, equipeFixa: false, crono: null, foco: null, ultPx: 0,
  extra: [], qtd: {}, noIdx: null, vis: Object.fromEntries(PLAN.map(s => [s.id, true])),
  cam: { zonas: true, nomes: true },
  prefixo: 'pln', svg: () => $('#plnSvg'), caixa: () => $('#plnMapa'), desenhar: desenharPln, clique: cliquePln,
  copia: (g, u) => copiaPln(g, u), copiaChave: () => [PLN.cam.zonas, PLAN.map(s => +PLN.vis[s.id]).join(''), PLN.cores || 0].join('|') };
const CAMADAS_PLN = { zonas: 'Zonas oficiais', nomes: 'Nomes das zonas' };
try {                                 // só as camadas que existem: as antigas (plantas, quadros) salvas no navegador caem fora
  const salvas = JSON.parse(localStorage.getItem('mc-pln-camadas') || '{}');
  Object.keys(CAMADAS_PLN).forEach(k => { if (typeof salvas[k] === 'boolean') PLN.cam[k] = salvas[k]; });
} catch (_) { /* sem storage */ }
const nomeAlvoCurto = n => nomeCurto(n).replace(/^NÓ/, 'NÓ ');

function planSitu(nome, mapa) {
  const e = PLN.est || {};
  if ((e.em_campo || {})[nome]) return 'campo';
  const prog = (e.programado || {})[nome];
  if (prog) return prog.some(p => p.hoje) ? 'hoje' : 'programado';
  const et = mapa ? etapaDe(mapa, nome) : null, s = et ? et.s : 'nao';
  if (s === 'execucao' || (et && et.parcial)) return 'execucao';        // executado em parte: ainda tem o que fazer
  if (s !== 'nao' && s !== 'liberado') return 'feito';
  return s === 'liberado' ? 'liberado' : 'livre';
}
// equipe da frente do trecho (Zona01 … Zona11, ADUTORA)
const equipeDoTrecho = t => t ? (t.tp === 'Adutora' ? 'ADUTORA' : t.z) : null;

/* ---------------------------------------------------------------- abrir a tela */
async function carregarDadosObra() {
  carregarMapa().catch(e => toast(e.message, 'erro'));              // números da obra, bandeja e conciliação (app.js)
  if (!PLN.dia) { PLN.dia = hoje(); $('#plnDia').value = PLN.dia; }
  let g;
  try { g = await obterGeral(); } catch (e) { return avisoPln('Não consegui abrir o traçado do mapa: ' + e.message); }
  if (g.ausente) return avisoPln('O mapa do projeto (REV02) não está na pasta mapa/ do sistema.');
  if (!PLN.pronto) montarPln(g); else ajustarAspecto(PLN);
  if (!MATERIAIS.length && pode('almox')) MATERIAIS = await api('/api/estoque').catch(() => []);
  await recarregarPln();
  if (PLN.abrir) { const a = PLN.abrir; PLN.abrir = null; escolherEquipeDoDia(a.equipe, a.aba); }   // vindo do Estoque
  if (podeTela('cronograma') && !PLN.crono) api('/api/cronograma').then(c => { PLN.crono = c.vazio ? null : c; if (PLN.crono) renderPainel(); }).catch(() => null);
  if (PLN.foco) aplicarFoco();
}
function avisoPln(msg) { const a = $('#plnAviso'); a.textContent = msg; a.hidden = !msg; }

// depois de qualquer registro que muda o mapa: a próxima leitura do Mapa iluminado vem nova e, com o Dados da obra
// aberto, a seleção e as cores se refazem
function plnRecarregar() {
  ESTADO_EM = 0;
  if (TELA === 'mapa' && PLN.pronto) recarregarPln();
}
async function recarregarPln() {
  const [est] = await Promise.all([api('/api/dados-obra/estado?data=' + PLN.dia), estadoMapa(true)]).catch(e => { toast(e.message, 'erro'); return [null]; });
  if (est) PLN.est = est;
  colorirPln();
  if (PLN.sel.length || PLN.nos.length) buscarSelecao(); else renderPainel();
}

function montarPln(g) {
  const svg = PLN.svg();
  const zonas = g.zonas.map(z => `<polygon class="ilu-zf" data-zona="${esc(z.id)}" points="${pontos(z.p)}" fill="${esc(z.cor)}" fill-opacity=".16"/>`).join('')
    + contornosTracejados(g.zonas.map(z => z.p), 'ilu-zl');
  PLN.noIdx = new Map();
  g.els.forEach((e, i) => e.n.forEach(n => PLN.noIdx.set(n, i)));
  svg.innerHTML = `<g id="plnZonas">${zonas}</g><g id="plnSelG"></g><g id="plnLinhas"></g><g id="plnNos" class="longe"></g>
    <g id="plnNomes">${g.nomes.map(n => `<text class="ilu-nome" x="${n.x}" y="${n.y}">${esc(nomeZona(n.id))}</text>`).join('')}</g><g id="plnPins"></g>`;
  aplicarCamadasPln();
  PLN.base = limites([...g.zonas.map(z => z.p), ...g.trechos.flatMap(t => t.p)], 0.02);
  PLN.vb = null; ajustarAspecto(PLN);
  ligarGestos(svg, PLN);
  PLN.pronto = true;
  new ResizeObserver(() => TELA === 'mapa' && ajustarAspecto(PLN)).observe($('#plnMapa'));
}

function desenharPln(px, zoom) {
  espessura($('#plnLinhas'), Math.min(6, 2.4 * Math.pow(Math.max(zoom, 1), 0.35)));
  if (escalaMudou(PLN, px)) {                          // arrastar não muda a escala: só o zoom mexe em textos, pinos e nós
    $('#plnZonas').style.setProperty('--k', 1 / px);  // só no contorno tracejado: na raiz, refazia o estilo do mapa inteiro
    espessura($('#plnSelG'), Math.min(14, 9 * Math.pow(Math.max(zoom, 1), 0.3)));
    $$('#plnNomes text').forEach(t => { t.setAttribute('font-size', 14 * px); t.setAttribute('stroke-width', 3.5 * px); });
    $$('#plnPins .ilu-pin').forEach(p => {
      const c = p.querySelector('circle'), tx = p.querySelector('text');
      c.setAttribute('r', 15 * px); c.setAttribute('stroke-width', 3 * px); tx.setAttribute('font-size', 13 * px);
    });
  }
  desenharNos(px, zoom < 3);
  trilha($('#plnTrilha'), PLN.zona ? `<button type="button" data-pln-tudo>Obra inteira</button> › ${esc(nomeZona(PLN.zona))}`
    : zoom > 1.15 ? '<button type="button" data-pln-tudo>Ver a obra inteira</button>' : 'Obra inteira');
}

// os nós só existem onde aparecem: de perto (zoom ≥ 3), os da área visível com folga; de longe, só os escolhidos. Os
// 1.188 círculos sempre no SVG (escondidos de longe) pesavam em cada redesenho. Raio constante na tela, exato a cada desenho.
function desenharNos(px, longe) {
  const g = GERAL, caixa = $('#plnNos'), sel = PLN.noSel || new Map(), [x, y, w, h] = PLN.vb;
  const dentro = e => e.x > x - w / 2 && e.x < x + w * 1.5 && e.y > y - h / 2 && e.y < y + h * 1.5;
  const chave = `${longe}|${px.toPrecision(3)}|${longe ? '' : PLN.vb.map(v => Math.round(v)).join(',')}|${[...sel].join(',')}`;
  if (caixa.dataset.chave === chave) return;
  caixa.dataset.chave = chave; caixa.classList.toggle('longe', longe);
  caixa.innerHTML = g.els.map((e, i) => {
    const k = sel.get(i); if (longe ? !k : !k && !dentro(e)) return '';
    const nome = e.n.find(n => n.includes('_Rede_')) || e.n[0];          // a ponta do trecho cita o nome da Rede
    return `<circle class="pln-no${k ? ' sel' : ''}${k === 'auto' ? ' auto' : ''}" data-i="${i}" data-n="${esc(nome)}" cx="${e.x}" cy="${e.y}" r="${(k ? 7 : 4.5) * px}"><title>${esc(nomeCurto(nome))}</title></circle>`;
  }).join('');
}

function colorirPln() {
  if (!PLN.pronto || !GERAL) return;
  const mapa = ESTADO_MAPA, por = Object.fromEntries(PLAN.map(s => [s.id, []]));
  GERAL.trechos.forEach(t => { t.ps = planSitu(t.n, mapa); por[t.ps].push(t); });
  PLN.cores = (PLN.cores || 0) + 1;
  $('#plnLinhas').innerHTML = PLAN.map(s => {
    const attrs = `class="ilu-tr" data-situ="${s.id}" stroke="${s.cor}"${s.opacidade ? ` stroke-opacity="${s.opacidade}"` : ''}`;
    return s.tracejado ? linhasTracejadas(por[s.id], `${attrs} stroke-dasharray="${s.tracejado}"`) : `<path ${attrs} d="${caminho(por[s.id].flatMap(t => t.p))}"/>`;
  }).join('');
  $$('#plnLinhas .ilu-tr').forEach(p => p.style.display = PLN.vis[p.dataset.situ] ? '' : 'none');
  const doDia = ((PLN.est || {}).checkins || []).filter(c => c.data === PLN.dia);
  $('#plnPins').innerHTML = doDia.flatMap(c => c.alvos.map(n => {        // o pino da equipe em cada trecho e nó do dia
    const tipo = indexar(GERAL).trecho.has(n) ? 'TRECHO' : 'ATIVIDADE', pos = posicaoAlvo(GERAL, tipo, n);
    if (!pos) return '';
    return `<g class="ilu-pin" data-alvo="${esc(n)}"><title>${esc(equipeNome(c.equipe_id))}: ${esc(c.alvos.map(nomeCompleto).join(', '))} (check-in de ${dataBR(c.data)})</title>
      <circle cx="${pos.xy[0]}" cy="${pos.xy[1]}"/><text x="${pos.xy[0]}" y="${pos.xy[1]}">${esc(rotuloEquipe(c.equipe_id))}</text></g>`;
  })).join('');
  PLN.ultPx = 0; desenharVista(PLN); marcarSelPln(); agendarCopia(PLN);
  if (PLN.pop) abrirPopPln(PLN.pop, true);
}
// a cópia leve do gesto (iluminado.js): as zonas e as linhas por situação do dia
function copiaPln(g, u) {
  if (PLN.cam.zonas) zonasCopia(g, u, () => 0.16);
  linhasCopia(g, u, PLAN.filter(s => PLN.vis[s.id]).map(s => ({ cor: s.cor, tracejado: s.tracejado, opacidade: s.opacidade, trechos: GERAL.trechos.filter(t => t.ps === s.id) })));
}

/* ---------------------------------------------------------------- seleção */
function marcarSelPln() {
  if (!PLN.pronto) return;
  const ix = indexar(GERAL), r = PLN.resp;
  const nomes = new Set([...PLN.sel, ...(r ? r.fisicos.flatMap(f => f.membros) : [])]);
  const ts = [...nomes].map(n => ix.trecho.get(n)).filter(Boolean);
  $('#plnSelG').innerHTML = ts.length ? `<path class="ilu-sel pln-sel" d="${caminho(ts.flatMap(t => t.p))}"/>` : '';
  const sel = new Map();                                              // nó escolhido: 'sel', ou 'auto' (entrou sozinho)
  [...PLN.nos, ...(r ? r.nos.filter(n => !n.automatico).map(n => n.nome) : [])].forEach(n => sel.set(PLN.noIdx.get(n), 'sel'));
  (r ? r.nos.filter(n => n.automatico) : []).forEach(n => sel.set(PLN.noIdx.get(n.nome), 'auto'));
  sel.delete(undefined);
  PLN.noSel = sel;
  if (PLN.vb && PLN.ultPx) desenharNos(PLN.ultPx, (PLN.base[2] - PLN.base[0]) / PLN.vb[2] < 3);
}
function membrosDe(nome) {
  const f = PLN.resp && PLN.resp.fisicos.find(x => x.membros.includes(nome));
  return f ? f.membros : [nome];
}
function escolherTrecho(nome, juntar) {
  const ja = PLN.sel.includes(nome) || !!(PLN.resp && PLN.resp.fisicos.some(f => f.membros.includes(nome)));
  if (juntar) {
    if (ja) { const tirar = new Set(membrosDe(nome)); PLN.sel = PLN.sel.filter(n => !tirar.has(n)); }
    else PLN.sel = [...PLN.sel, nome];
  } else {
    const so = ja && (PLN.resp ? PLN.resp.fisicos.length === 1 : PLN.sel.length === 1);
    PLN.sel = so ? [] : [nome]; PLN.nos = [];                          // tocar no único escolhido desmarca
  }
  if (!PLN.equipeFixa) PLN.equipe = null;
  atualizarSelecao();
}
function alternarNo(nome) {
  const i = PLN.noIdx.get(nome), r = PLN.resp;
  const auto = r && r.nos.find(n => n.automatico && PLN.noIdx.get(n.nome) === i);
  if (auto) return toast(`${auto.numero} já entra sozinho: liga ${auto.liga.join(' e ')}.`);
  const ja = PLN.nos.find(n => PLN.noIdx.get(n) === i) || (r && r.nos.find(n => !n.automatico && PLN.noIdx.get(n.nome) === i) || {}).nome;
  PLN.nos = ja ? PLN.nos.filter(n => PLN.noIdx.get(n) !== i) : [...PLN.nos, nome];
  atualizarSelecao();
}
function limparSelecao() { PLN.sel = []; PLN.nos = []; PLN.resp = null; PLN.extra = []; if (!PLN.equipeFixa) PLN.equipe = null; atualizarSelecao(); }
let SEL_T = 0;
function atualizarSelecao() {
  marcarSelPln();
  clearTimeout(SEL_T);
  if (!PLN.sel.length && !PLN.nos.length) { PLN.resp = null; PLN.pedido++; marcarSelPln(); return renderPainel(); }
  SEL_T = setTimeout(buscarSelecao, 120);
}
function equipePadrao() {
  const e = PLN.est || {}, ix = indexar(GERAL);
  for (const n of PLN.sel) {                                       // a equipe programada para o dia nesses trechos…
    const p = ((e.programado || {})[n] || []).find(x => x.hoje); if (p) return p.equipe;
    const c = (e.em_campo || {})[n]; if (c) return c.equipe;
  }
  const eq = equipeDoTrecho(ix.trecho.get(PLN.sel[0]));            // …senão a da frente do primeiro trecho
  return ((RESUMO && RESUMO.equipes) || []).some(x => x.id === eq) ? eq : null;
}
async function buscarSelecao() {
  const n = ++PLN.pedido;
  if (!PLN.equipe) PLN.equipe = equipePadrao();
  const q = new URLSearchParams({ linhas: PLN.sel.join(','), nos: PLN.nos.join(','), data: PLN.dia });
  if (PLN.equipe) q.set('equipe', PLN.equipe);
  let r;
  try { r = await api('/api/dados-obra/selecao?' + q); } catch (e) { if (n === PLN.pedido) toast(e.message, 'erro'); return; }
  if (n !== PLN.pedido) return;                                    // chegou depois de outra escolha: descarta
  PLN.resp = r; PLN.qtd = {};
  marcarSelPln(); renderPainel();
}

/* ---------------------------------------------------------------- clique no mapa, busca e foco */
// i: o trecho mais perto do toque (trechoPerto, iluminado.js), ou -1; nó e pino ficam por cima do trecho, como no desenho
function cliquePln(alvo, ev, i) {
  fecharPopPln();
  const perto = s => alvo.closest && alvo.closest(s);
  const no = perto('.pln-no'), pin = perto('.ilu-pin'), zona = perto('.ilu-zf');
  const juntar = PLN.multi || !!(ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey));
  if (no && !$('#plnNos').classList.contains('longe')) return alternarNo(no.dataset.n);
  if (pin) { PLN.sel = [pin.dataset.alvo].filter(n => indexar(GERAL).trecho.has(n)); return atualizarSelecao(); }
  if (i >= 0) return escolherTrecho(GERAL.trechos[i].n, juntar);
  if (zona && !juntar) return focarZonaPln(zona.dataset.zona);
}
function focarZonaPln(z) {
  PLN.zona = z;
  const ts = GERAL.trechos.filter(t => zonaDoTrecho(t) === z), poli = GERAL.zonas.find(x => x.id === z);
  irPara(limites([...(poli ? [poli.p] : []), ...ts.flatMap(t => t.p)], 0.06), true, PLN);
}
function verTudoPln() { PLN.zona = null; irPara(PLN.base, true, PLN); }
function focarNomes(nomes) {
  const ix = indexar(GERAL), ps = [];
  nomes.forEach(n => { const t = ix.trecho.get(n); if (t) ps.push(...t.p); else { const e = ix.el.get(n); if (e) ps.push([e.x, e.y]); } });
  if (!ps.length) return;
  const [x0, y0, x1, y1] = limites(ps, 0.25), larg = (PLN.base[2] - PLN.base[0]) / 14;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, w = Math.max(x1 - x0, larg), h = Math.max(y1 - y0, larg);
  irPara([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], true, PLN);
}
// "Ver a ficha completa" e a busca da ficha levam o mapa até o trecho (e o escolhem)
function plnFocar(tipo, nome) { PLN.foco = { tipo, nome }; if (PLN.pronto && TELA === 'mapa') aplicarFoco(); }
function aplicarFoco() {
  const f = PLN.foco; PLN.foco = null;
  if (!f || !GERAL) return;
  focarNomes([f.nome]);
  if (f.tipo === 'TRECHO' && indexar(GERAL).trecho.has(f.nome) && !PLN.sel.includes(f.nome)) { PLN.sel = [f.nome]; PLN.nos = []; atualizarSelecao(); }
}
ligarBusca($('#plnBusca'), r => {
  $('#plnBusca').value = '';
  if (r.tipo === 'TRECHO') { focarNomes([r.rotulo]); return escolherTrecho(r.rotulo, PLN.multi || PLN.sel.length > 0); }
  focarNomes([r.rotulo]);
  if (PLN.sel.length) alternarNo(r.rotulo); else toast('Escolha os trechos no mapa: o nó entre dois trechos escolhidos entra sozinho.');
});

/* ---------------------------------------------------------------- ferramentas: dia, juntar, legenda e zonas */
$('#plnDia').addEventListener('change', ev => {
  if (!ev.target.value) { ev.target.value = PLN.dia; return; }
  PLN.dia = ev.target.value; PLN.extra = [];
  recarregarPln();
});
$('#plnMulti').addEventListener('click', ev => {
  PLN.multi = !PLN.multi; ev.currentTarget.setAttribute('aria-pressed', String(PLN.multi));
  toast(PLN.multi ? 'Juntar trechos ligado: cada toque soma ou tira um trecho da seleção.' : 'Juntar trechos desligado: o toque escolhe um trecho só.');
});
$('#plnMais').addEventListener('click', () => zoomEm(1 / 1.5, null, null, PLN));
$('#plnMenos').addEventListener('click', () => zoomEm(1.5, null, null, PLN));
$('#plnTudo').addEventListener('click', verTudoPln);
$('#plnTrilha').addEventListener('click', ev => { if (ev.target.closest('[data-pln-tudo]')) verTudoPln(); });
function abrirPopPln(nome, recarregar) {
  if (PLN.pop === nome && !recarregar) return fecharPopPln();
  fecharPopPln(); PLN.pop = nome;
  const pop = $('#plnPop' + nome[0].toUpperCase() + nome.slice(1)); pop.hidden = false;
  $(`[data-pln-pop="${nome}"]`).setAttribute('aria-expanded', 'true');
  const ts = GERAL.trechos.filter(t => !PLN.zona || zonaDoTrecho(t) === PLN.zona);
  if (nome === 'legenda') {
    const conta = Object.fromEntries(PLAN.map(s => [s.id, { n: 0, m: 0 }]));
    ts.forEach(t => { if (t.ps) { conta[t.ps].n++; conta[t.ps].m += t.L || 0; } });
    pop.innerHTML = `<h3>Trechos em ${esc(dataBR(PLN.dia))}${PLN.zona ? ' · ' + esc(nomeZona(PLN.zona)) : ''}</h3>`
      + [...PLAN].reverse().map(s => `<button type="button" class="ilu-linha" data-pln-situ="${s.id}" aria-pressed="${PLN.vis[s.id]}"><i class="${s.tracejado ? 'tracejado' : ''}" style="border-color:${s.cor}"></i>
        <span>${esc(s.nome)}</span><span class="fim">${nf(conta[s.id].n, 0)} · ${km(conta[s.id].m)}</span></button>`).join('')
      + '<p>Toque numa linha para mostrar ou esconder. O pino é a equipe com check-in no dia; contorno branco é a seleção e o nó com anel entrou sozinho (liga dois trechos escolhidos).</p>';
  } else if (nome === 'camadas') {
    pop.innerHTML = '<h3>Camadas</h3>' + Object.entries(CAMADAS_PLN).map(([k, rot]) => `<button type="button" class="ilu-linha" data-pln-camada="${k}" aria-pressed="${PLN.cam[k]}"><span>${PLN.cam[k] ? '☑' : '☐'}</span><span>${rot}</span></button>`).join('')
      + '<p>Sem plantas baixas neste mapa: só as zonas, os trechos e os nós. O satélite fica no Mapa iluminado.</p>';
  } else {
    const zs = [...new Set(GERAL.trechos.map(zonaDoTrecho))].sort((a, b) => (a === ZONA_ADUTORA) - (b === ZONA_ADUTORA) || String(a).localeCompare(String(b)));
    pop.innerHTML = '<h3>Zonas</h3>' + `<button type="button" class="ilu-linha" data-pln-zona="" aria-current="${!PLN.zona}"><i class="zona"></i><span>Obra inteira</span></button>`
      + zs.map(z => { const cor = (GERAL.zonas.find(x => x.id === z) || {}).cor || '#F2F2F2';
        return `<button type="button" class="ilu-linha" data-pln-zona="${esc(z)}" aria-current="${PLN.zona === z}"><i class="zona" style="background:${cor}33;border-color:${cor}"></i><span>${esc(nomeZona(z))}</span></button>`; }).join('');
  }
}
function fecharPopPln() {
  PLN.pop = null;
  $$('#plnFerr .ilu-pop').forEach(p => p.hidden = true);
  $$('[data-pln-pop]').forEach(b => b.setAttribute('aria-expanded', 'false'));
}
$('#plnFerr').addEventListener('click', ev => {
  const bt = ev.target.closest('[data-pln-pop]'); if (bt) return GERAL && abrirPopPln(bt.dataset.plnPop);
  const s = ev.target.closest('[data-pln-situ]');
  if (s) { PLN.vis[s.dataset.plnSitu] = !PLN.vis[s.dataset.plnSitu]; colorirPln(); return abrirPopPln('legenda', true); }
  const z = ev.target.closest('[data-pln-zona]'); if (z) { fecharPopPln(); return z.dataset.plnZona ? focarZonaPln(z.dataset.plnZona) : verTudoPln(); }
  const c = ev.target.closest('[data-pln-camada]');
  if (c) { PLN.cam[c.dataset.plnCamada] = !PLN.cam[c.dataset.plnCamada]; aplicarCamadasPln(); desenharVista(PLN); return abrirPopPln('camadas', true); }
});
function aplicarCamadasPln() {
  [['zonas', $('#plnZonas')], ['nomes', $('#plnNomes')]].forEach(([k, el]) => {
    if (el) el.style.display = PLN.cam[k] ? '' : 'none';
  });
  try { localStorage.setItem('mc-pln-camadas', JSON.stringify(PLN.cam)); } catch (_) { /* sem storage */ }
  agendarCopia(PLN);
}
document.addEventListener('pointerdown', ev => { if (PLN.pop && !ev.target.closest('#plnFerr .ilu-bloco')) fecharPopPln(); });
document.addEventListener('keydown', ev => {
  if (ev.key !== 'Escape' || TELA !== 'mapa') return;
  if (PLN.pop) fecharPopPln(); else if (PLN.sel.length || PLN.nos.length) limparSelecao();
});

/* ---------------------------------------------------------------- painel ao lado do mapa */
const htmlEquipes = sel => ((RESUMO && RESUMO.equipes) || []).map(e => `<option value="${esc(e.id)}"${e.id === sel ? ' selected' : ''}>${esc(e.nome)}</option>`).join('');
const futuro = () => PLN.dia > hoje();
function abasPainel() {
  if (!PLN.resp) return [['dia', 'O dia'], pode('almox') && ['devolucao', 'Devolução']].filter(Boolean);
  return [pode('planejar') && ['programar', 'Programar'], pode('almox') && ['liberar', futuro() ? 'Reservar material' : 'Liberar material'],
    pode('almox') && ['devolucao', 'Devolução'], PLN.crono && ['cronograma', 'No cronograma'], ['trechos', 'Trechos']].filter(Boolean);
}
function renderPainel() {
  const p = $('#plnPainel'), abas = abasPainel();
  if (!abas.some(a => a[0] === PLN.aba)) PLN.aba = abas[0][0];
  p.innerHTML = (PLN.resp ? cabecalhoSel(PLN.resp) : cabecalhoDia())
    + `<div class="pln-abas" role="tablist">${abas.map(([id, rot]) => `<button type="button" role="tab" class="pln-aba" data-pln-aba="${id}" aria-selected="${PLN.aba === id}">${esc(rot)}</button>`).join('')}</div>
      <div class="pln-corpo" role="tabpanel">${corpoAba()}</div>`;
  if (PLN.aba === 'liberar' && !futuro()) carregarPresentes();
  $$('.pln-dev').forEach(atualizarAplicado);
}
function cabecalhoDia() {
  return `<div class="pln-cab"><h2>${esc(dataBR(PLN.dia))}${PLN.dia === hoje() ? ' · hoje' : ''}</h2></div>
    <p class="vazio" style="margin:0 0 10px">Toque num trecho para escolher. <b>Ctrl + clique</b> (no celular, o botão <b>Juntar trechos</b>) junta vários; o nó entre dois trechos escolhidos entra sozinho.</p>`;
}
function cabecalhoSel(r) {
  const t = r.totais, um = r.fisicos.length === 1;
  return `<div class="pln-cab"><h2>${um ? esc(r.fisicos[0].membros.map(nomeCurto).join(' + ')) : `${t.trechos_fisicos} trechos`}</h2>
      <button type="button" class="btn-texto" data-pln-limpar>Limpar</button></div>
    <p class="pln-resumo">${nf(t.extensao_m)} m · falta assentar ${nf(t.falta_assentar_m)} m${t.nos ? ` · ${t.nos} nó${t.nos > 1 ? 's' : ''}` : ''}${um && r.fisicos[0].membros.length > 1 ? ' · trecho físico de ' + r.fisicos[0].membros.length + ' linhas' : ''}</p>
    <div class="pln-chips">${r.fisicos.map(f => `<span class="chip" title="${esc(f.texto)}">${esc(f.membros.map(nomeCurto).join(' + '))} · DE ${esc(f.de_mm)}</span>`).join('')}
      ${r.nos.map(n => `<span class="chip ${n.automatico ? 'azul' : 'laranja'}" title="${n.automatico ? 'Entrou sozinho: liga ' + esc(n.liga.join(' e ')) : 'Tocado no mapa'}">${esc(n.numero)}${n.automatico ? ' · liga ' + esc(n.liga.join(' e ')) : ''}</span>`).join('')}</div>
    ${r.avisos.map(a => `<div class="aviso sugestao">${esc(a)}</div>`).join('')}
    ${r.linhas.length === 1 || (r.nos.length === 1 && !r.linhas.length) ? `<button type="button" class="btn" data-pln-ficha style="margin-top:8px">Ver a ficha completa</button>` : ''}`;
}
function corpoAba() {
  const r = PLN.resp;
  if (PLN.aba === 'dia') return corpoDia();
  if (PLN.aba === 'devolucao') return corpoDevolucao(r ? r.checkins : ((PLN.est || {}).checkins || []));
  if (PLN.aba === 'programar') return corpoProgramar(r);
  if (PLN.aba === 'liberar') return corpoLiberar(r);
  if (PLN.aba === 'cronograma') return corpoCronoSel(r);
  return corpoTrechos(r);
}
function corpoDia() {
  const e = PLN.est || { programado: {}, em_campo: {}, checkins: [], lotes: [] }, eqs = {};
  Object.entries(e.programado).forEach(([n, ps]) => ps.filter(p => p.hoje).forEach(p => {
    const x = eqs[p.equipe] = eqs[p.equipe] || { prog: new Set(), serv: new Set(), campo: new Set() }; x.prog.add(n); x.serv.add(p.servico);
  }));
  Object.entries(e.em_campo).forEach(([n, c]) => { const x = eqs[c.equipe] = eqs[c.equipe] || { prog: new Set(), serv: new Set(), campo: new Set() }; x.campo.add(n); });
  const serv = s => (RESUMO.servicos_programacao || {})[s] || s;
  const lista = Object.entries(eqs).sort(([a], [b]) => a.localeCompare(b)).map(([eq, x]) => `<div class="registro"><div><b>${esc(equipeNome(eq))}</b>
      ${x.campo.size ? `<span class="chip laranja">em campo · ${x.campo.size} alvo${x.campo.size > 1 ? 's' : ''}</span>` : '<span class="chip">sem check-in</span>'}</div>
    <small>${x.prog.size ? `programada: ${esc([...x.serv].map(serv).join(', '))} em ${esc([...x.prog].map(nomeCurto).slice(0, 8).join(', '))}${x.prog.size > 8 ? '…' : ''}` : 'sem programação no dia'}</small>
    <div class="acoes"><button type="button" class="btn" data-pln-equipe-dia="${esc(eq)}">Escolher no mapa</button>
      ${pode('almox') && !futuro() ? `<button type="button" class="btn prim" data-pln-equipe-dia="${esc(eq)}" data-aba="liberar">Liberar o material do dia</button>` : ''}</div></div>`).join('');
  const lotes = (e.lotes || []).filter(l => (l.status.PLANEJADA || 0) > 0);
  return `<h3>Equipes no dia</h3>${lista || '<div class="vazio">Nenhuma equipe programada nem com check-in neste dia.</div>'}
    <h3 style="margin-top:14px">Programado nas próximas semanas</h3>${lotes.length ? lotes.map(htmlLote).join('') : '<div class="vazio">Nada programado.</div>'}`;
}
function htmlLote(l) {
  const st = l.status, chips = [['PLANEJADA', 'amarelo', 'planejada'], ['REALIZADA', 'azul', 'realizada'], ['NAO_REALIZADA', 'vermelho', 'não realizada']]
    .filter(([k]) => st[k]).map(([k, c, rot]) => `<span class="chip ${c}">${st[k]} ${rot}${st[k] > 1 ? 's' : ''}</span>`).join(' ');
  return `<div class="registro"><div><b>${esc(equipeNome(l.equipe_id))} · ${esc(l.servico_nome)}</b> ${chips}</div>
    <small>${dataBR(l.de)}${l.ate !== l.de ? ' a ' + dataBR(l.ate) : ''} · ${l.dias} dia${l.dias > 1 ? 's' : ''} · ${esc(l.alvos.map(nomeCurto).slice(0, 6).join(', '))}${l.alvos.length > 6 ? ` e mais ${l.alvos.length - 6}` : ''} · por ${esc(l.criada_por)}</small>
    <div class="acoes"><button type="button" class="btn" data-pln-lote-ver="${esc(l.lote)}">Ver no mapa</button>
      ${st.PLANEJADA && pode('planejar') ? `<button type="button" class="btn" data-pln-cancelar="${esc(l.lote)}">Cancelar o que falta</button>` : ''}</div></div>`;
}
function corpoProgramar(r) {
  const serv = Object.entries((RESUMO && RESUMO.servicos_programacao) || {}).map(([k, v]) => `<option value="${esc(k)}"${k === 'ASSENTAMENTO' ? ' selected' : ''}>${esc(v)}</option>`).join('');
  return `<form class="form" id="plnFormProg">
      <div class="linha"><label>Equipe<select name="equipe_id" data-pln-equipe required><option value="">—</option>${htmlEquipes(PLN.equipe)}</select></label>
        <label>Serviço<select name="servico" required>${serv}</select></label></div>
      <div class="linha"><label>Dia<input type="date" name="data" value="${PLN.dia}" required></label></div>
      <label>Observação<input name="obs" placeholder="ex.: começar pelo NÓ2.7"></label>
      <p class="vazio" style="margin:0">O que a equipe executa <b>nesse dia</b>, uma programação por trecho. O almoxarife libera as peças do dia para estes trechos e, na hora, eles ficam "em execução hoje" no Mapa iluminado, com o pino da equipe. Os 18 meses da obra ficam no Cronograma.</p>
      <div class="acoes"><button class="btn prim">Programar para o dia</button></div></form>
    <h3 style="margin-top:14px">Já programado nestes trechos</h3>${r.programacoes.length ? r.programacoes.map(htmlLote).join('') : '<div class="vazio">Nada programado.</div>'}`;
}
function checkinDaEquipe(r) { return (r.checkins || []).find(c => c.equipe_id === PLN.equipe); }
function corpoLiberar(r) {
  const ck = PLN.equipe && checkinDaEquipe(r), fut = futuro();
  const aviso = !PLN.equipe ? '<div class="aviso info">Escolha a equipe.</div>'
    : ck && ck.data < PLN.dia ? `<div class="aviso problema">A ${esc(equipeNome(ck.equipe_id))} está com o check-in de ${dataBR(ck.data)} aberto: faça a devolução (aba Devolução) antes de liberar o material de outro dia.</div>`
    : ck && ck.data === PLN.dia && !fut ? `<div class="aviso info">A equipe já fez check-in neste dia (${esc(ck.alvos.map(nomeCurto).join(', '))}): o material é somado a ele.</div>`
    : fut ? '<div class="aviso info">Dia que ainda não chegou: o material fica <b>reservado</b> para a equipe e sai no check-in daquele dia.</div>' : '';
  const linhas = [...r.materiais, ...PLN.extra.filter(x => !r.materiais.some(m => m.material_id === x.material_id))];
  const outros = MATERIAIS.filter(m => m.propriedade !== 'CONSUMO' && !linhas.some(l => l.material_id === m.id));
  return `<form class="form" id="plnFormLib">
      <div class="linha"><label>Equipe<select name="equipe_id" data-pln-equipe required><option value="">—</option>${htmlEquipes(PLN.equipe)}</select></label>
        <label>Dia<input type="date" value="${PLN.dia}" disabled></label></div>
      ${aviso}
      ${!fut ? '<details class="pln-presentes"><summary>Quem foi para o campo (gera o histograma)</summary><div class="checks" id="plnPresentes"><span class="vazio">Escolha a equipe.</span></div></details>' : ''}
      <div class="pln-mat">${linhas.map(m => `<div class="pln-item" data-m="${esc(m.material_id)}">
          <div><b>${esc(m.material_id)}</b> <small>${esc(String(m.descricao || '').slice(0, 60))}</small>
            <small>${m.previsto != null ? `previsto ${nf(m.previsto, 3)} ${esc(m.unidade)}` : 'fora do projeto'} · com a equipe ${nf(m.com_equipe, 3)} · disponível ${nf(m.disponivel, 3)}${m.origem ? ' · ' + esc(m.origem) : ''}</small>
            ${m.falta_no_almox > 0 ? `<span class="chip vermelho">faltam ${nf(m.falta_no_almox, 3)} ${esc(m.unidade)} no almoxarifado</span>` : ''}</div>
          <label>${fut ? 'Reservar' : 'Liberar'}<input type="number" step="any" min="0" data-q value="${esc(PLN.qtd[m.material_id] ?? m.liberavel ?? m.sugerido ?? '')}"></label></div>`).join('')
        || '<div class="vazio">O projeto não traz material para estes trechos.</div>'}</div>
      <div class="linha"><label>Outro material<select data-pln-outro><option value="">—</option>${outros.map(m => `<option value="${esc(m.id)}">${esc(m.id)} — ${esc(m.descricao.slice(0, 50))} (disp. ${nf(m.disponivel)} ${esc(m.unidade)})</option>`).join('')}</select></label></div>
      ${r.sem_material.length ? `<details><summary>${r.sem_material.length} peça${r.sem_material.length > 1 ? 's' : ''} dos nós sem material único no BM (não sugeridas)</summary>${r.sem_material.map(x => `<div><small>${esc(x.no)} · ${esc(x.descricao)}${x.diametro ? ' DE ' + esc(x.diametro) : ''} · ${x.quantidade != null ? nf(x.quantidade, 3) : '?'} ${esc(x.unidade || '')} · item ${esc(x.codigo_bm || '—')}</small></div>`).join('')}</details>` : ''}
      <p class="vazio" style="margin:0">Sugestão do projeto: tubo pelo que falta assentar e as peças dos nós, menos o que já está com a equipe, até o que há no almoxarifado. Confira antes.</p>
      <div class="acoes"><button class="btn prim"${ck && ck.data < PLN.dia ? ' disabled' : ''}>${fut ? 'Reservar para o dia' : ck && ck.data === PLN.dia ? 'Somar ao check-in do dia' : 'Liberar e registrar a saída (check-in)'}</button></div></form>`;
}
async function carregarPresentes() {
  const box = $('#plnPresentes'); if (!box || !PLN.equipe) return;
  const eq = PLN.equipe, x = await api('/api/equipe?id=' + encodeURIComponent(eq)).catch(() => null);
  if (!x || eq !== PLN.equipe || !$('#plnPresentes')) return;
  const it = [...x.funcionarios.map(f => ['f', f.id, `${f.nome}${f.funcao ? ' · ' + f.funcao : ''}`]), ...x.maquinas.map(m => ['m', m.id, '🚜 ' + m.descricao])];
  $('#plnPresentes').innerHTML = it.length ? it.map(([t, id, n]) => `<label class="check"><input type="checkbox" data-t="${t}" value="${id}" checked> ${esc(n)}</label>`).join('')
    : '<span class="vazio">Cadastre os funcionários e as máquinas da equipe (Administrativo › Equipes).</span>';
}
function corpoDevolucao(cks) {
  if (!cks.length) return `<div class="vazio">${PLN.resp ? 'Nenhuma equipe com check-in aberto nestes trechos.' : 'Nenhuma equipe com check-in aberto.'}</div>`;
  return '<p class="vazio" style="margin:0 0 8px">No fim do dia, com o encarregado: o que volta para o almoxarifado, o que quebrou e o que fica com a equipe. O resto conta como aplicado.</p>'
    + cks.map(c => `<form class="registro pln-dev" data-ck="${c.id}"><div><b>${esc(equipeNome(c.equipe_id))}</b> <small>check-in de ${dataBR(c.data)}</small>
        ${c.atrasado ? '<span class="chip vermelho">de outro dia: feche antes do próximo</span>' : ''}</div>
      <small>${esc(c.alvos.map(nomeCurto).join(', ') || c.contingencia || '')}</small>
      ${c.materiais.length ? `<div class="pln-mat">${c.materiais.map(m => `<div class="pln-item pln-item-dev" data-m="${esc(m.material_id)}" data-c="${m.quantidade}">
          <div><b>${esc(m.material_id)}</b> <small>${esc(String(m.descricao || '').slice(0, 50))}</small>
            <small>com a equipe ${nf(m.quantidade, 3)} ${esc(m.unidade || '')} · aplicado <b data-aplicado>${nf(m.quantidade, 3)}</b></small></div>
          <div class="pln-dev-q"><label>Devolvido<input type="number" step="any" min="0" data-k="sobra" value="0"></label>
            <label>Perda<input type="number" step="any" min="0" data-k="perda" value="0"></label>
            <label>Fica com a equipe<input type="number" step="any" min="0" data-k="fica_com_equipe" value="0"></label></div></div>`).join('')}</div>
        <label>Motivo da perda (se houver)<input data-motivo></label>` : '<div class="vazio">Sem material com a equipe: o fechamento só encerra o dia.</div>'}
      <div class="acoes"><button class="btn ok">Registrar a devolução e fechar o dia</button></div></form>`).join('');
}
function atualizarAplicado(f) {
  let ok = true;
  $$('[data-m]', f).forEach(tr => {
    const v = k => +($(`[data-k=${k}]`, tr).value || 0), ap = +tr.dataset.c - v('sobra') - v('perda') - v('fica_com_equipe');
    const td = $('[data-aplicado]', tr); td.textContent = nf(Math.max(ap, 0), 3); td.classList.toggle('erro', ap < -1e-9);
    ok = ok && ap >= -1e-9;
  });
  $('button', f.querySelector('.acoes')).disabled = !ok;
}
function corpoCronoSel(r) {
  const c = PLN.crono, membros = new Set(r.linhas.map(l => l.ponto)), frentes = new Set(r.linhas.map(l => l.frente_id));
  const fim = maisDias(PLN.dia, 30);
  const ligadas = c.tarefas.filter(t => (t.alvos || []).some(a => membros.has(a)));
  const daFrente = c.tarefas.filter(t => !t.resumo && !ligadas.includes(t) && t.frente && frentes.has(t.frente) && t.inicio && t.fim && t.fim >= PLN.dia && t.inicio <= fim).slice(0, 25);
  const linha = t => `<div class="registro"><div><b>${esc(t.nome)}</b> ${t.critica ? '<span class="chip vermelho">crítica</span>' : ''}</div>
    <small>${esc(t.edt || '')} · ${dataBR(t.inicio)} a ${dataBR(t.fim)} · Project ${t.concluido != null ? nf(t.concluido, 0) + ' %' : '—'}${t.executado_pct != null ? ` · assentado no sistema ${nf(t.executado_pct, 0)} %` : ''}${(t.recursos || []).length ? ' · ' + esc(t.recursos.join(', ')) : ''}</small></div>`;
  return `<p class="vazio" style="margin:0 0 8px">Cronograma versão ${c.versao} (${esc(c.nome_original)}).</p>
    <h3>Tarefas que citam estes trechos</h3>${ligadas.map(linha).join('') || '<div class="vazio">Nenhuma tarefa cita estes trechos pelo nome.</div>'}
    <h3 style="margin-top:12px">Da mesma frente, até ${dataBR(fim)}</h3>${daFrente.map(linha).join('') || '<div class="vazio">Nada da frente neste período.</div>'}`;
}
function corpoTrechos(r) {
  return `<div class="tabela"><table><thead><tr><th>Linha</th><th class="n">Extensão</th><th class="n">Assentado</th><th class="n">Reaterrado</th><th class="n">Liberado (topografia)</th></tr></thead><tbody>
    ${r.linhas.map(l => `<tr><td><b>${esc(nomeCurto(l.ponto))}</b><br><small>${esc(l.frente_id || '')} · DE ${esc(l.de_mm)} · ${esc(l.metodologia || '')}</small></td><td class="n">${nf(l.extensao_m)} m</td>
      <td class="n">${nf(l.assentado_m)}</td><td class="n">${nf(l.reaterrado_m)}</td><td class="n">${nf(l.liberado_m)}</td></tr>`).join('')}</tbody></table></div>
    ${r.nos.length ? `<h3 style="margin-top:12px">Nós</h3>${r.nos.map(n => `<div><small><b>${esc(n.numero)}</b> · ${esc(n.tipo)} · ${n.automatico ? 'entrou sozinho: liga ' + esc(n.liga.join(' e ')) : 'tocado no mapa'}</small></div>`).join('')}` : ''}`;
}

// os trechos e nós do dia de uma equipe (o programado e o que já está no check-in) ficam escolhidos no mapa
function escolherEquipeDoDia(eq, aba) {
  const e = PLN.est || { programado: {}, em_campo: {} }, ix = indexar(GERAL);
  const alvos = Object.entries(e.programado).filter(([, ps]) => ps.some(p => p.hoje && p.equipe === eq)).map(([n]) => n)
    .concat(Object.entries(e.em_campo).filter(([, c]) => c.equipe === eq).map(([n]) => n));
  PLN.sel = [...new Set(alvos.filter(n => ix.trecho.has(n)))]; PLN.nos = [...new Set(alvos.filter(n => !ix.trecho.has(n)))];
  PLN.equipe = eq; PLN.equipeFixa = true; if (aba) PLN.aba = aba;
  if (alvos.length) focarNomes(alvos);
  atualizarSelecao();
}
// Estoque e movimentos › "Equipes programadas hoje": cada equipe com os trechos do dia (nome completo) e as peças
// sugeridas pelo projeto; "Liberar" abre o Dados da obra com o dia da equipe escolhido, na aba Liberar material
async function almoxEquipesDoDia() {
  const box = $('#almoxDia'), dia = hoje();
  $('#almoxDiaPainel').hidden = false;
  const e = await api('/api/dados-obra/estado?data=' + dia).catch(() => null); if (!e) return;
  const eqs = {};
  Object.entries(e.programado).forEach(([n, ps]) => ps.filter(p => p.hoje).forEach(p => {
    const x = eqs[p.equipe] = eqs[p.equipe] || { linhas: new Set(), nos: new Set() }; (p.tipo === 'TRECHO' ? x.linhas : x.nos).add(n);
  }));
  const ids = Object.keys(eqs).sort();
  if (!ids.length) { box.className = 'vazio'; box.textContent = 'Nenhuma equipe programada para hoje (programe no Dados da obra).'; return; }
  const sels = await Promise.all(ids.map(eq => api('/api/dados-obra/selecao?' + new URLSearchParams({ linhas: [...eqs[eq].linhas].join(','),
    nos: [...eqs[eq].nos].join(','), data: dia, equipe: eq })).catch(() => null)));
  box.className = '';
  box.innerHTML = ids.map((eq, i) => {
    const r = sels[i], alvos = [...eqs[eq].linhas, ...eqs[eq].nos], ja = Object.values(e.em_campo).some(c => c.equipe === eq);
    const mats = r ? r.materiais.filter(m => m.sugerido > 0) : [];
    return `<div class="registro"><div><b>${esc(equipeNome(eq))}</b> ${ja ? '<span class="chip laranja">material liberado · em campo</span>' : '<span class="chip amarelo">aguardando a liberação</span>'}</div>
      <small>${alvos.map(n => esc(nomeCompleto(n))).join(' · ')}</small>
      ${mats.length ? `<div><small>Peças sugeridas: ${mats.slice(0, 8).map(m => `${esc(m.material_id)} ${nf(m.liberavel, 3)} ${esc(m.unidade)}${m.falta_no_almox > 0 ? ` (faltam ${nf(m.falta_no_almox, 3)})` : ''}`).join(' · ')}${mats.length > 8 ? ' …' : ''}</small></div>` : ''}
      <div class="acoes"><button type="button" class="btn prim" data-almox-liberar="${esc(eq)}">${ja ? 'Somar material no Dados da obra' : 'Liberar o material do dia'}</button></div></div>`;
  }).join('');
}
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-almox-liberar]'); if (!b) return;
  PLN.dia = hoje(); if ($('#plnDia')) $('#plnDia').value = PLN.dia;
  PLN.abrir = { equipe: b.dataset.almoxLiberar, aba: 'liberar' };
  abrirAba('mapa');
});

/* ---------------------------------------------------------------- ações do painel */
const PAINEL = $('#plnPainel');
PAINEL.addEventListener('click', async ev => {
  const t = ev.target, q = s => t.closest(s);
  if (q('[data-pln-aba]')) { PLN.aba = q('[data-pln-aba]').dataset.plnAba; return renderPainel(); }
  if (q('[data-pln-limpar]')) return limparSelecao();
  if (q('[data-pln-ficha]')) {
    const r = PLN.resp, [tipo, id] = r.linhas.length ? ['TRECHO', r.linhas[0].id] : ['ATIVIDADE', r.nos[0].atividade_id];
    await mostrarFiscal(tipo, id); return $('#fiscDetalhe').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  if (q('[data-pln-equipe-dia]')) return escolherEquipeDoDia(q('[data-pln-equipe-dia]').dataset.plnEquipeDia, q('[data-pln-equipe-dia]').dataset.aba);
  if (q('[data-pln-lote-ver]')) {
    const l = [...((PLN.est || {}).lotes || []), ...((PLN.resp || {}).programacoes || [])].find(x => x.lote === q('[data-pln-lote-ver]').dataset.plnLoteVer);
    if (!l) return;
    const ix = indexar(GERAL);
    PLN.sel = l.alvos.filter(n => ix.trecho.has(n)); PLN.nos = l.alvos.filter(n => !ix.trecho.has(n));
    PLN.equipe = l.equipe_id; PLN.equipeFixa = true; focarNomes(l.alvos); return atualizarSelecao();
  }
  if (q('[data-pln-cancelar]')) {
    const motivo = prompt('Motivo do cancelamento (as programações já realizadas continuam):'); if (!motivo) return;
    const r = await acao(() => api('/api/dados-obra/cancelar-lote', { lote: q('[data-pln-cancelar]').dataset.plnCancelar, motivo, a_partir_de: hoje() })).catch(() => null);
    if (r) { toast(`${r.canceladas} programaç${r.canceladas > 1 ? 'ões canceladas' : 'ão cancelada'}.`, 'ok'); recarregarCamadaMapa(); }
  }
});
PAINEL.addEventListener('change', ev => {
  const t = ev.target;
  if (t.matches('[data-pln-equipe]')) { PLN.equipe = t.value || null; PLN.equipeFixa = !!t.value; return buscarSelecao(); }
  if (t.matches('[data-pln-outro]') && t.value) {
    const m = MATERIAIS.find(x => x.id === t.value);
    if (m) PLN.extra.push({ material_id: m.id, descricao: m.descricao, unidade: m.unidade, previsto: null, com_equipe: 0, disponivel: m.disponivel, sugerido: '' });
    return renderPainel();
  }
});
PAINEL.addEventListener('input', ev => {
  const f = ev.target.closest('.pln-dev'); if (f) return atualizarAplicado(f);
  if (ev.target.matches('[data-q]')) PLN.qtd[ev.target.closest('[data-m]').dataset.m] = ev.target.value;   // o que foi digitado sobrevive ao redesenho
});
PAINEL.addEventListener('submit', async ev => {
  ev.preventDefault();
  const f = ev.target, r = PLN.resp, sel = { linhas: PLN.sel, nos: PLN.nos };
  if (f.id === 'plnFormProg') {
    const o = formObj(f), corpo = { ...sel, equipe_id: o.equipe_id, servico: o.servico, data: o.data, obs: o.obs };
    let x = await acao(() => api('/api/dados-obra/programar', corpo)).catch(() => null);
    if (x && x.confirmar) {                                        // outra equipe já está nesse trecho no dia
      if (!confirm(x.confirmar)) return;
      x = await acao(() => api('/api/dados-obra/programar', { ...corpo, confirmar: true })).catch(() => null);
    }
    if (!x) return;
    toast(`Programado para ${dataBR(x.data)}: ${x.criadas} trecho${x.criadas > 1 ? 's' : ''} e nó${x.criadas > 1 ? 's' : ''}${x.ja_existiam ? `; ${x.ja_existiam} já estava${x.ja_existiam > 1 ? 'm' : ''}` : ''}.`, 'ok');
    return recarregarCamadaMapa();
  }
  if (f.id === 'plnFormLib') {
    const materiais = $$('[data-m]', f).map(tr => ({ material_id: tr.dataset.m, quantidade: +($('[data-q]', tr).value || 0) })).filter(m => m.quantidade > 0);
    const corpo = { ...sel, data: PLN.dia, equipe_id: PLN.equipe, materiais };
    if (futuro()) {
      const x = await acao(() => api('/api/dados-obra/reservar', corpo)).catch(() => null);
      if (!x) return;
      toast(`Reservado para ${dataBR(PLN.dia)}: ${x.reservas.length} material${x.reservas.length > 1 ? 'is' : ''}.`, 'ok');
    } else {
      corpo.funcionarios = $$('#plnPresentes input[data-t=f]:checked').map(i => +i.value);
      corpo.maquinas = $$('#plnPresentes input[data-t=m]:checked').map(i => +i.value);
      const x = await acao(() => api('/api/dados-obra/liberar', corpo)).catch(() => null);
      if (!x) return;
      toast(x.novo ? `Material liberado e check-in registrado: a ${equipeNome(PLN.equipe)} aparece em campo no Mapa iluminado.` : 'Material somado ao check-in do dia.', 'ok');
    }
    PLN.extra = []; PLN.qtd = {};
    MATERIAIS = await api('/api/estoque').catch(() => MATERIAIS);
    return recarregarCamadaMapa();
  }
  if (f.matches('.pln-dev')) {
    const motivo = ($('[data-motivo]', f) || { value: '' }).value;
    const itens = $$('[data-m]', f).map(tr => {
      const v = k => +($(`[data-k=${k}]`, tr).value || 0);
      return { material_id: tr.dataset.m, sobra: v('sobra'), perda: v('perda'), fica_com_equipe: v('fica_com_equipe'), motivo,
        aplicado: Math.max(+(+tr.dataset.c - v('sobra') - v('perda') - v('fica_com_equipe')).toFixed(6), 0) };
    });
    const x = await acao(() => api('/api/checkout', { checkin_id: f.dataset.ck, itens })).catch(() => null);
    if (!x) return;
    toast('Devolução registrada e dia fechado.', 'ok');
    MATERIAIS = await api('/api/estoque').catch(() => MATERIAIS);
    return recarregarCamadaMapa();
  }
});

/* ---------------------------------------------------------------- Cronograma da obra (MS Project) */
let CRONO = null;
async function carregarCronograma() {
  CRONO = await api('/api/cronograma');
  PLN.crono = CRONO.vazio ? null : CRONO;
  const fr = [...new Set((CRONO.tarefas || []).map(t => t.frente).filter(Boolean))].sort();
  const atual = $('#cronoFrente').value;
  $('#cronoFrente').innerHTML = '<option value="">todas</option>' + fr.map(f => `<option${f === atual ? ' selected' : ''}>${esc(f)}</option>`).join('');
  renderCronoInfo(); renderGantt();
}
function renderCronoInfo() {
  const c = CRONO, info = $('#cronoInfo');
  $('#cronoVersoes').innerHTML = (c.versoes || []).map(v => `<div><small><b>versão ${v.versao}</b> · ${esc(String(v.enviado_em).replace('T', ' ').slice(0, 16))} · ${esc(v.enviado_por)} · ${esc(v.nome_original)} · ${nf(v.n_tarefas, 0)} tarefas</small></div>`).join('')
    || '<div class="vazio">Nenhuma versão.</div>';
  if (c.vazio) { info.className = 'vazio'; info.textContent = 'Nenhum cronograma enviado. ' + c.como_exportar; return; }
  info.className = '';
  info.innerHTML = `<p style="margin:0 0 4px"><b>${esc(c.projeto.nome || c.nome_original)}</b> <span class="chip azul">versão ${c.versao}</span></p>
    <p class="vazio" style="margin:0 0 10px;padding:0">${esc(c.formato)} · ${esc(c.nome_original)} · enviado por ${esc(c.enviado_por)} em ${esc(String(c.enviado_em).replace('T', ' ').slice(0, 16))}</p>
    <div class="kpis pln-kpis">${[['Tarefas', nf(c.n_tarefas, 0)], ['Período', `${dataBR(c.projeto.inicio)} a ${dataBR(c.projeto.fim)}`],
      ['Em andamento hoje', nf(c.em_andamento, 0)], ['Atrasadas', nf(c.atrasadas, 0)], ['Ligadas a trechos', nf(c.ligadas_a_trechos, 0)]]
      .map(([k, v]) => `<div class="kpi"><span>${k}</span><b>${v}</b></div>`).join('')}</div>`;
}
const MAX_LINHAS_GANTT = 600;
function renderGantt() {
  const c = CRONO, box = $('#cronoGantt');
  if (!c || c.vazio) { box.innerHTML = ''; $('#cronoResumo').textContent = ''; return; }
  const busca = $('#cronoBusca').value.trim().toLowerCase(), fr = $('#cronoFrente').value, modo = $('#cronoMostrar').value, nivel = +$('#cronoNivel').value || 0;
  const h = hoje(), ate = maisDias(h, 14);
  const lst = c.tarefas.filter(t => (!busca || [t.nome, t.edt, ...(t.recursos || [])].join(' ').toLowerCase().includes(busca))
    && (!fr || t.frente === fr) && (!nivel || t.nivel <= nivel)
    && (!modo || (modo === 'andamento' && !t.resumo && t.inicio <= h && t.fim >= h) || (modo === 'proximas' && !t.resumo && t.inicio > h && t.inicio <= ate)
      || (modo === 'atrasadas' && !t.resumo && t.fim && t.fim < h && (t.concluido || 0) < 100) || (modo === 'ligadas' && (t.alvos || []).length)));
  const ini = c.projeto.inicio || h, fim = c.projeto.fim || h;
  const dia = d => (new Date(d + 'T12:00:00') - new Date(ini + 'T12:00:00')) / 864e5, total = Math.max(dia(fim), 1);
  const pos = d => Math.min(Math.max(dia(d) / total * 100, 0), 100);
  const meses = [];
  for (let d = ini.slice(0, 8) + '01'; d <= fim; d = maisDias(d.slice(0, 8) + '28', 4).slice(0, 8) + '01') meses.push(d);
  const marca = h >= ini && h <= fim ? `<span class="crono-hoje" style="left:${pos(h)}%" title="hoje"></span>` : '';
  $('#cronoResumo').innerHTML = `<small class="vazio">${nf(lst.length, 0)} de ${nf(c.tarefas.length, 0)} tarefas${lst.length > MAX_LINHAS_GANTT ? ` · mostrando as ${MAX_LINHAS_GANTT} primeiras: use os filtros` : ''}. A barra laranja é o % concluído do Project; "campo" é o assentado registrado no sistema nos trechos que a tarefa cita.</small>`;
  box.innerHTML = `<div class="crono-l crono-cab"><span>EDT</span><span>Tarefa</span><span>Início – fim</span><span class="n">%</span><span class="crono-barra">${meses.map(m => `<em style="left:${pos(m)}%">${m.slice(5, 7)}/${m.slice(2, 4)}</em>`).join('')}${marca}</span></div>`
    + lst.slice(0, MAX_LINHAS_GANTT).map(t => {
      const a = t.inicio ? pos(t.inicio) : null, b = t.fim ? pos(t.fim) : null, larg = a != null && b != null ? Math.max(b - a, 0.4) : 0;
      return `<div class="crono-l${t.resumo ? ' resumo' : ''}${t.critica ? ' critica' : ''}"><span class="crono-edt">${esc(t.edt || t.id)}</span>
        <span class="crono-nome" style="padding-left:${Math.min(t.nivel - 1, 6) * 14}px" title="${esc(t.nome)}">${t.marco ? '◆ ' : ''}${esc(t.nome)}${(t.alvos || []).length ? ` <span class="chip azul">${t.alvos.length} trecho${t.alvos.length > 1 ? 's' : ''}</span>` : ''}</span>
        <span class="crono-datas">${dataBR(t.inicio)} – ${dataBR(t.fim)}</span>
        <span class="n">${t.concluido != null ? nf(t.concluido, 0) + '%' : '—'}${t.executado_pct != null ? `<small>campo ${nf(t.executado_pct, 0)}%</small>` : ''}</span>
        <span class="crono-barra">${a != null ? `<i style="left:${a}%;width:${larg}%"><b style="width:${Math.min(t.concluido || 0, 100)}%"></b></i>` : ''}${marca}</span></div>`;
    }).join('');
}
['#cronoBusca', '#cronoFrente', '#cronoMostrar', '#cronoNivel'].forEach(s => $(s).addEventListener(s === '#cronoBusca' ? 'input' : 'change', () => CRONO && renderGantt()));
$('#fCrono').addEventListener('submit', async ev => {
  ev.preventDefault();
  const arq = ev.target.arquivo.files[0]; if (!arq) return;
  if (/\.mpp$/i.test(arq.name)) return toast('O arquivo .mpp só abre no próprio Project. No Project: Arquivo › Salvar como › Formato XML (*.xml) e envie esse arquivo.', 'erro');
  const r = await acao(async () => api('/api/cronograma', { conteudo_b64: await lerOriginal(arq), nome: arq.name })).catch(() => null);
  if (!r) return;
  toast(`Cronograma versão ${r.versao}: ${nf(r.n_tarefas, 0)} tarefas lidas (${nf(r.ligadas_a_trechos, 0)} ligadas a trechos).`, 'ok');
  ev.target.reset(); PLN.crono = null; carregarCronograma();
});
