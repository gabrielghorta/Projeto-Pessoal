/* Camada "Mapa Iluminado" injetada pelo servidor no HTML PLANTAS_..._REV02_EQUIPES.
 * Não altera o motor gráfico da REV02: lê o mesmo DADOS, recolore as polylines já desenhadas
 * (polyline.tr[data-pipe], [data-e]) e conversa com a tela principal por postMessage. */
(function () {
  'use strict';
  if (typeof DADOS === 'undefined') return;
  const T = DADOS.trechos, E = DADOS.els;
  const COR = { NAO_EXECUTADO: '#9AA3AE', EM_EXECUCAO: '#F08C00', CONCLUIDO_MES: '#D62828', OK_FISCAL: '#0F9D58', MEDIDO_ANTERIOR: '#E8B10A' };
  const PIOR = ['CONCLUIDO_MES', 'EM_EXECUCAO', 'OK_FISCAL', 'MEDIDO_ANTERIOR', 'NAO_EXECUTADO'];
  let modo = 'iluminado', estado = { status: {}, pins: [] };
  try { modo = localStorage.getItem('mc-modo') || 'iluminado'; } catch (_) { /* sem storage */ }

  // ---- controle de modo
  const box = document.createElement('div');
  box.className = 'mc-modo';
  box.innerHTML = '<button data-m="projeto">Modo Projeto (cores DE)</button><button data-m="iluminado">Modo Mapa Iluminado</button>';
  document.body.appendChild(box);
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
    svg.querySelectorAll('polyline.tr[data-pipe]').forEach(pl => {
      if (!pl.dataset.mcCor) pl.dataset.mcCor = pl.getAttribute('stroke');
      if (modo === 'projeto' || pl.dataset.active === 'false') {
        pl.setAttribute('stroke', pl.dataset.mcCor); pl.removeAttribute('data-mc'); return;
      }
      const st = statusTrecho(+pl.dataset.pipe);
      pl.setAttribute('stroke', COR[st]); pl.setAttribute('data-mc', st);
    });
    svg.querySelectorAll('.el[data-e]').forEach(el => {
      if (!el.dataset.mcCor) el.dataset.mcCor = el.getAttribute('fill');
      const st = statusElemento(+el.dataset.e);
      el.setAttribute('fill', modo === 'iluminado' && st !== 'NAO_EXECUTADO' ? COR[st] : el.dataset.mcCor);
    });
    desenharPins(svg);
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
    if (ev.data.tipo === 'mc-focar') {
      const q = document.getElementById('q'); if (!q) return;
      const nome = ev.data.alvo_tipo === 'TRECHO' ? ev.data.alvo_id : String(ev.data.alvo_id).split('_').pop();
      q.value = nome; q.dispatchEvent(new Event('input', { bubbles: true }));
      setTimeout(() => { const b = document.querySelector('#res button[data-n]'); if (b) b.click(); }, 60);
    }
  });

  recarregar();
  setInterval(recarregar, 60000);
})();
