/* Camada "Mapa Iluminado" injetada pelo servidor no HTML PLANTAS_..._REV02_EQUIPES.
 * Não altera o motor gráfico da REV02: lê o mesmo DADOS, recolore as polylines já desenhadas
 * (polyline.tr[data-pipe], [data-e]) e conversa com a tela principal por postMessage.
 * Topologia (/api/topologia?desenho=1): a ponta de cada trecho vai para o centro do nó em todos os desenhos (lei da
 * obra: todo trecho termina numa conexão; as pontas de cruzamento e de passagem ficam como estão) e, ao tocar num
 * trecho que faz parte de um trecho físico, as outras linhas dele também acendem e o painel diz de onde até onde vai. */
(function () {
  'use strict';
  if (typeof DADOS === 'undefined') return;
  const T = DADOS.trechos, E = DADOS.els;
  const PB_DADOS = Object.fromEntries((DADOS.pbs || []).map(p => [p.id, p]));
  const IDX_T = new Map(T.map((t, i) => [t.R, i]));
  const FIS = new Map();                      // nome visível → trecho físico com mais de uma linha
  let SEL = null;                             // trecho selecionado (nome visível)
  try { const [, k, v] = decodeURIComponent(location.hash.slice(1)).split('/'); if (k === 't') SEL = v; } catch (_) { /* sem seleção */ }
  const escH = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const COR = { NAO_EXECUTADO: '#9AA3AE', EM_EXECUCAO: '#F08C00', CONCLUIDO_MES: '#D62828', OK_FISCAL: '#0F9D58', MEDIDO_ANTERIOR: '#E8B10A' };
  const PIOR = ['CONCLUIDO_MES', 'EM_EXECUCAO', 'OK_FISCAL', 'MEDIDO_ANTERIOR', 'NAO_EXECUTADO'];
  // miolo branco sobre a linha = execução ainda não verificada (conferência interna Ankara, não é aprovação Caesb)
  const MIOLO = { INFORMADO: '2 3', PARCIAL: '7 3', LEGADO_SEM_POSICAO: '0.6 2.4' };
  let modo = 'iluminado', camada = 'andamento', estado = { status: {}, verificacao: {}, pins: [], camadas: {} };
  try { modo = localStorage.getItem('mc-modo') || 'iluminado'; camada = localStorage.getItem('mc-camada') || 'andamento'; } catch (_) { /* sem storage */ }
  const CINZA = '#9AA3AE';
  const cam = k => (estado.camadas || {})[k] || {};
  // camadas operacionais: cada uma calculada no servidor só a partir dos registros efetivos; "verificado" e
  // "conforme" são conferência interna Ankara; verde só para decisão da Caesb registrada (memorando ESET)
  const CAMADAS = {
    andamento: { nome: 'Andamento', legenda: [['#9AA3AE', 'não executado'], ['#F08C00', 'em execução'], ['#D62828', 'concluído — aguarda OK interno'],
      ['#0F9D58', 'OK interno Ankara (não é aprovação Caesb)'], ['#E8B10A', 'medido antes'], ['', 'miolo branco: informado sem verificação']] },
    planejado: { nome: 'Planejado (7 dias)', cor: n => { const p = cam('planejado')[n]; return p && (p.hoje ? '#7C3AED' : '#2F6FD6'); },
      legenda: [['#7C3AED', 'programado para hoje'], ['#2F6FD6', 'programado nos próximos 7 dias'], [CINZA, 'sem programação']] },
    material: { nome: 'Material', cor: n => ({ COM_EQUIPE: '#F08C00', RESERVADO: '#E8B10A' })[cam('material')[n]],
      legenda: [['#F08C00', 'material com a equipe'], ['#E8B10A', 'material reservado'], [CINZA, 'sem material disponibilizado']] },
    verificacao: { nome: 'Informado × verificado', cor: n => ({ VERIFICADO: '#2F6FD6', PARCIAL: '#8EB8FF', INFORMADO: '#F08C00', LEGADO_SEM_POSICAO: '#D62828' })[(estado.verificacao || {})[n]],
      legenda: [['#2F6FD6', 'verificado (conferência interna)'], ['#8EB8FF', 'verificação parcial'], ['#F08C00', 'informado, sem verificação'], ['#D62828', 'legado sem posição'], [CINZA, 'sem execução']] },
    cadastro: { nome: 'Cadastro', cor: n => ({ LEVANTAMENTO_PARCIAL: '#E8B10A', LEVANTAMENTO_COMPLETO: '#8EB8FF', '1_PRONTO': '#B794F4', '2_ENVIADO': '#9F7AEA',
      '3_RECEBIDO': '#805AD5', '4_GDOC_ANALISE': '#2F6FD6', '5A_NEGADO': '#D62828', '6_APROVADO': '#0F9D58' })[cam('cadastro')[n]],
      legenda: [['#E8B10A', 'levantamento de campo parcial'], ['#8EB8FF', 'levantamento completo'], ['#B794F4', 'esteira: pronto / em produção / recebido'],
        ['#2F6FD6', 'protocolado no GDOC (em análise)'], ['#D62828', 'negado pela Caesb'], ['#0F9D58', 'aprovação Caesb registrada (ESET)'], [CINZA, 'sem levantamento']] },
    pendencias: { nome: 'Pendências', cor: n => { const k = cam('pendencias')[n]; return k ? (k >= 3 ? '#D62828' : '#F08C00') : null; },
      legenda: [['#D62828', '3 ou mais pendências'], ['#F08C00', '1 ou 2 pendências (ocorrência, reaterro sem cadastro, legado)'], [CINZA, 'nenhuma registrada']] },
  };
  // tema da tela principal (escuro por padrão), pelo mecanismo da própria REV02 (data-theme); o arquivo não muda
  const tema = t => document.documentElement.setAttribute('data-theme', t === 'claro' ? 'light' : 'dark');
  try { tema(localStorage.getItem('mc-tema') || 'escuro'); } catch (_) { tema('escuro'); }

  // ---- controle de modo
  const box = document.createElement('div');
  box.className = 'mc-modo';
  box.innerHTML = '<button data-m="projeto">Modo Projeto (cores DE)</button><button data-m="iluminado">Modo Mapa Iluminado</button>'
    + `<select class="mc-camada" title="Camada do Mapa Iluminado">${Object.entries(CAMADAS).map(([k, c]) => `<option value="${k}">${c.nome}</option>`).join('')}</select>`;
  document.body.appendChild(box);
  const sel = box.querySelector('.mc-camada');
  sel.value = CAMADAS[camada] ? camada : 'andamento';
  sel.addEventListener('change', () => { camada = sel.value; try { localStorage.setItem('mc-camada', camada); } catch (_) { /* sem storage */ } aplicar(); });
  const leg = document.createElement('div');
  leg.className = 'mc-legenda';
  document.body.appendChild(leg);
  box.addEventListener('click', ev => {
    const b = ev.target.closest('button[data-m]'); if (!b) return;
    modo = b.dataset.m; try { localStorage.setItem('mc-modo', modo); } catch (_) { /* sem storage */ }
    aplicar();
  });

  const statusTrecho = i => estado.status[T[i].R] || 'NAO_EXECUTADO';
  const statusElemento = j => {
    const st = (E[j].noms || []).map(n => estado.status[n]).filter(Boolean);
    return st.length ? PIOR.find(p => st.includes(p)) : 'NAO_EXECUTADO';
  };

  function aplicar() {
    box.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.m === modo));
    const svg = document.querySelector('#stage svg'); if (!svg) return;
    svg.classList.toggle('mc-iluminado', modo === 'iluminado');
    const c = CAMADAS[camada] || CAMADAS.andamento;
    svg.querySelectorAll('polyline.tr[data-pipe]').forEach(pl => {
      if (!pl.dataset.mcCor) pl.dataset.mcCor = pl.getAttribute('stroke');
      if (modo === 'projeto' || pl.dataset.active === 'false') {
        pl.setAttribute('stroke', pl.dataset.mcCor); pl.removeAttribute('data-mc'); return;
      }
      if (c.cor) {
        const cor = c.cor(T[+pl.dataset.pipe].R);
        pl.setAttribute('stroke', cor || CINZA); pl.setAttribute('data-mc', cor ? 'C_SIM' : 'C_NAO'); return;
      }
      const st = statusTrecho(+pl.dataset.pipe);
      pl.setAttribute('stroke', COR[st]); pl.setAttribute('data-mc', st);
    });
    svg.querySelectorAll('.el[data-e]').forEach(el => {
      if (!el.dataset.mcCor) el.dataset.mcCor = el.getAttribute('fill');
      if (modo !== 'iluminado') { el.setAttribute('fill', el.dataset.mcCor); return; }
      if (c.cor) {
        const cor = (E[+el.dataset.e].noms || []).map(n => c.cor(n)).find(Boolean);
        el.setAttribute('fill', cor || el.dataset.mcCor); return;
      }
      const st = statusElemento(+el.dataset.e);
      el.setAttribute('fill', st !== 'NAO_EXECUTADO' ? COR[st] : el.dataset.mcCor);
    });
    sel.style.display = modo === 'iluminado' ? '' : 'none';
    leg.style.display = modo === 'iluminado' ? '' : 'none';
    leg.innerHTML = `<b>${c.nome}</b>` + c.legenda.map(([cor, txt]) => `<div><i style="${cor ? 'background:' + cor : 'background:#5B6675;outline:2px dashed #fff;outline-offset:-3px'}"></i>${txt}</div>`).join('');
    if (camada === 'andamento') marcarVerificacao(svg); else svg.querySelectorAll('.mc-verif').forEach(p => p.remove());
    desenharPins(svg);
    marcarFisico(svg);
  }

  // ---- pontas no centro do nó: corrige DADOS no lugar (o HTML não muda) e as linhas já desenhadas
  function encaixar(corr) {
    Object.entries(corr).forEach(([id, lista]) => {
      const dz = id === 'GERAL' ? DADOS.visaoGeral : PB_DADOS[id]; if (!dz) return;
      const por = new Map(dz.tr.map(t => [t.i, t]));
      lista.forEach(([i, k, ponta, cortar, x, y]) => {
        const p = por.has(i) && por.get(i).p[k]; if (!p || p.length < 2) return;
        const c = Math.max(0, Math.min(cortar, p.length / 2 - 1));
        if (ponta === 0) p.splice(0, 2 * c, x, y); else p.splice(p.length - 2 * c, 2 * c, x, y);
      });
    });
    const svg = document.querySelector('#stage svg'); if (!svg) return;
    const cur = svg.classList.contains('overview-svg') ? 'GERAL' : ((document.querySelector('#pblist button.cur') || {}).dataset || {}).pb;
    const dz = cur === 'GERAL' ? DADOS.visaoGeral : PB_DADOS[cur]; if (!dz) return;
    const por = new Map(dz.tr.map(t => [t.i, t]));
    const pts = a => { let s = ''; for (let k = 0; k < a.length; k += 2) s += a[k] + ',' + a[k + 1] + ' '; return s; };
    [['polyline.tr[data-pipe]', 'pipe'], ['polyline.hit[data-t]', 't']].forEach(([q, atr]) => {
      const parte = new Map();                // a k-ésima linha de um trecho no desenho é a parte k da polilinha
      svg.querySelectorAll(q).forEach(pl => {
        const i = +pl.dataset[atr], k = parte.get(i) || 0; parte.set(i, k + 1);
        const t = por.get(i); if (t && t.p[k]) pl.setAttribute('points', pts(t.p[k]));
      });
    });
  }

  // ---- trecho físico: as outras linhas acendem junto com a selecionada e o painel diz o trecho inteiro
  function marcarFisico(svg) {
    svg.querySelectorAll('.mc-fisico').forEach(g => g.remove());
    const f = SEL && FIS.get(SEL); if (!f) return;
    const NS = 'http://www.w3.org/2000/svg', g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'mc-fisico');
    f.membros.filter(n => n !== SEL).forEach(n => svg.querySelectorAll(`polyline.tr[data-pipe="${IDX_T.get(n)}"]`).forEach(pl => {
      [['#fff', '10px', '.75'], [pl.getAttribute('stroke'), '5px', '1']].forEach(([cor, larg, op]) => {
        const o = document.createElementNS(NS, 'polyline');
        o.setAttribute('class', 'selt'); o.setAttribute('points', pl.getAttribute('points'));
        o.setAttribute('stroke', cor); o.setAttribute('stroke-width', larg); o.setAttribute('stroke-opacity', op);
        g.appendChild(o);
      });
    }));
    const gsel = svg.querySelector('#gsel');
    if (gsel) svg.insertBefore(g, gsel); else svg.appendChild(g);
  }
  function textoFisico() {
    const det = document.getElementById('det'); if (!det) return;
    det.querySelectorAll('.mc-fisico-txt').forEach(x => x.remove());
    const f = SEL && FIS.get(SEL); if (!f) return;
    const div = document.createElement('div');
    div.className = 'sec mc-fisico-txt';
    div.innerHTML = `<h4>Trecho físico</h4><div style="color:var(--ink)">${escH(f.texto.replace(/^Trecho físico:\s*/, ''))}</div>`;
    const hd = det.querySelector('.hd');
    if (hd) hd.after(div); else det.prepend(div);
  }
  async function topologia() {
    try {
      const r = await fetch('/api/topologia?desenho=1'); if (!r.ok) return;
      const t = await r.json();
      (t.fisicos || []).forEach(f => f.membros.forEach(n => FIS.set(n, f)));
      encaixar(t.correcoes || {});
    } catch (_) { /* sem topologia: o desenho fica como no HTML */ }
    aplicar(); textoFisico();
  }

  function marcarVerificacao(svg) {
    svg.querySelectorAll('.mc-verif').forEach(p => p.remove());
    if (modo !== 'iluminado') return;
    svg.querySelectorAll('polyline.tr[data-pipe]').forEach(pl => {
      const v = pl.dataset.active === 'false' ? null : (estado.verificacao || {})[T[+pl.dataset.pipe].R];
      if (!v || !MIOLO[v]) return;
      const o = pl.cloneNode(false), w = parseFloat(pl.getAttribute('stroke-width')) || 3;
      ['data-pipe', 'data-mc', 'data-mc-cor', 'data-active', 'id'].forEach(a => o.removeAttribute(a));
      o.setAttribute('class', 'mc-verif'); o.setAttribute('data-verif', v);
      o.setAttribute('stroke', '#fff'); o.setAttribute('stroke-width', String(Math.max(w * 0.38, 0.8)));
      o.setAttribute('stroke-dasharray', MIOLO[v]);
      pl.after(o);
    });
  }

  function desenharPins(svg) {
    svg.querySelectorAll('.mc-pin').forEach(p => p.remove());
    if (modo !== 'iluminado') return;
    const NS = 'http://www.w3.org/2000/svg';
    estado.pins.forEach(p => {
      let alvo = null;
      if (p.alvo_tipo === 'TRECHO') {
        const i = T.findIndex(t => t.R === p.alvo_id);
        alvo = i >= 0 && svg.querySelector(`polyline.tr[data-pipe="${i}"]`);
      } else {
        const j = E.findIndex(e => (e.noms || []).includes(p.alvo_id));
        alvo = j >= 0 && svg.querySelector(`.el[data-e="${j}"]`);
      }
      if (!alvo) return;
      const bb = alvo.getBBox(), x = bb.x + bb.width / 2, y = bb.y + bb.height / 2;
      const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'mc-pin');
      g.setAttribute('transform', `translate(${x} ${y})`);
      g.innerHTML = `<path d="M0 0 C -6 -10 -9 -14 -9 -19 A 9 9 0 1 1 9 -19 C 9 -14 6 -10 0 0 Z" fill="#E85D22" stroke="#fff" stroke-width="1.5"/>
        <circle cy="-19" r="3.5" fill="#fff"/><text y="-32" text-anchor="middle">📍 Equipe ${p.equipe} · programado ${p.data || ''}</text>`;
      svg.appendChild(g);
    });
  }

  async function recarregar() {
    try {
      const r = await fetch('/api/mapa/estado'); if (r.ok) estado = await r.json();
    } catch (_) { /* servidor fora do ar: mantém o modo projeto */ }
    aplicar();
  }

  // a REV02 recria o SVG a cada troca de PB/frente: reaplica as cores
  const stage = document.getElementById('stage');
  if (stage) new MutationObserver(() => requestAnimationFrame(aplicar)).observe(stage, { childList: true });

  // seleção na REV02 → painel de fiscalização da tela principal (setHash usa history.replaceState)
  const rs = history.replaceState.bind(history);
  history.replaceState = function (s, t, url) {
    rs(s, t, url);
    try {
      const [, k, v] = decodeURIComponent(String(url || '').replace(/^#/, '')).split('/');
      SEL = k === 't' ? v : null;
      const svg = document.querySelector('#stage svg');
      if (svg) marcarFisico(svg);
      textoFisico();
      let msg = null;
      if (k === 't') msg = { alvo_tipo: 'TRECHO', alvo_id: v };
      else if (k === 'e') { const e = E.find(x => x.k === v); if (e && e.noms && e.noms.length) msg = { alvo_tipo: 'CONJUNTO', alvo_id: e.noms[0] }; }
      if (msg && window.parent !== window) window.parent.postMessage({ tipo: 'mc-selecao', ...msg }, location.origin);
    } catch (_) { /* endereço sem seleção */ }
  };

  // comandos da tela principal
  window.addEventListener('message', ev => {
    if (ev.origin !== location.origin || !ev.data) return;
    if (ev.data.tipo === 'mc-recarregar') recarregar();
    if (ev.data.tipo === 'mc-tema') tema(ev.data.tema);
    if (ev.data.tipo === 'mc-focar') {
      const q = document.getElementById('q'); if (!q) return;
      const nome = ev.data.alvo_tipo === 'TRECHO' ? ev.data.alvo_id : String(ev.data.alvo_id).split('_').pop();
      q.value = nome; q.dispatchEvent(new Event('input', { bubbles: true }));
      setTimeout(() => { const b = document.querySelector('#res button[data-n]'); if (b) b.click(); }, 60);
    }
  });

  recarregar();
  topologia();
  setInterval(recarregar, 60000);
})();
