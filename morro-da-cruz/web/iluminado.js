/* Traçado real da rede para a tela inicial e para o Mapa iluminado.
 * A geometria vem da visão geral do HTML REV02 (/api/mapa/geral: satélite das PBs, zonas oficiais, trechos, nós) e a situação
 * de cada trecho vem só dos registros do banco (/api/mapa/estado). Nenhuma coordenada é criada aqui: o que não tem
 * posição no projeto não aparece no mapa (continua na bandeja do Dados da obra). */

/* ---------------------------------------------------------------- dados compartilhados */
let GERAL = null, GERAL_P = null, ESTADO_MAPA = null, ESTADO_EM = 0, ESTADO_P = null;
function obterGeral() {
  if (!GERAL_P) GERAL_P = api('/api/mapa/geral').then(g => (GERAL = g)).catch(e => { GERAL_P = null; throw e; });
  return GERAL_P;
}
// a situação do mapa é lida uma vez por pedido: telas que pedem juntas (Dados da obra) dividem a mesma resposta
async function estadoMapa(novo) {
  if (novo || !ESTADO_MAPA || Date.now() - ESTADO_EM > 30000) {
    if (!ESTADO_P) ESTADO_P = api('/api/mapa/estado' + (MEDICAO_ATUAL ? '?medicao=' + MEDICAO_ATUAL : ''))
      .then(e => { ESTADO_MAPA = e; ESTADO_EM = Date.now(); return e; }).finally(() => { ESTADO_P = null; });
    return ESTADO_P;
  }
  return ESTADO_MAPA;
}
const SVGNS = 'http://www.w3.org/2000/svg';
const pontos = p => { let s = ''; for (let i = 0; i < p.length; i += 2) s += (i ? ' ' : '') + p[i] + ',' + p[i + 1]; return s; };
const caminho = partes => partes.map(p => 'M' + pontos(p)).join('');
// Tracejado pesa: o navegador calcula cada traço do caminho inteiro, até fora da tela, a cada quadro (de perto, 1,7 s por
// quadro com a rede toda num caminho só). Por isso o tracejado vai em pedaços curtos, que o navegador pula quando estão
// fora da vista: um caminho por trecho e o contorno das zonas e dos quadros em pedaços de ~40 unidades do mapa. Cada
// pedaço continua o tracejado de onde o anterior parou (--k = pixels da tela por unidade do mapa, posto a cada zoom), para
// o desenho ficar igual ao do contorno inteiro, inclusive onde duas zonas vizinhas se sobrepõem.
const linhasTracejadas = (trechos, attrs) => trechos.map(t => `<path ${attrs} d="${caminho(t.p)}"/>`).join('');
function contornosTracejados(polis, cls, passo = 40) {
  let s = '';
  for (const p of polis) {
    const q = p.length > 4 ? [...p, p[0], p[1]] : p;            // contorno fechado
    let ini = 0, acc = 0, feito = 0;
    for (let i = 2; i < q.length; i += 2) {
      acc += Math.hypot(q[i] - q[i - 2], q[i + 1] - q[i - 1]);
      if (acc - feito >= passo || i === q.length - 2) {
        s += `<polyline class="${cls}" style="stroke-dashoffset:calc(var(--k, 1) * ${-feito.toFixed(2)}px)" points="${pontos(q.slice(ini, i + 2))}"/>`;
        ini = i; feito = acc;
      }
    }
  }
  return s;
}
function limites(listas, folga = 0) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  listas.forEach(p => { for (let i = 0; i < p.length; i += 2) { x0 = Math.min(x0, p[i]); x1 = Math.max(x1, p[i]); y0 = Math.min(y0, p[i + 1]); y1 = Math.max(y1, p[i + 1]); } });
  const fx = (x1 - x0) * folga, fy = (y1 - y0) * folga;
  return [x0 - fx, y0 - fy, x1 + fx, y1 + fy];
}
// ponto do meio do trecho (na parte mais longa da polilinha), onde fica o pino da equipe
function meioDoTrecho(t) {
  let melhor = null, maior = -1;
  t.p.forEach(p => {
    let L = 0; for (let i = 2; i < p.length; i += 2) L += Math.hypot(p[i] - p[i - 2], p[i + 1] - p[i - 1]);
    if (L > maior) { maior = L; melhor = { p, L }; }
  });
  const p = melhor.p; let falta = melhor.L / 2;
  for (let i = 2; i < p.length; i += 2) {
    const d = Math.hypot(p[i] - p[i - 2], p[i + 1] - p[i - 1]);
    if (d >= falta && d > 0) { const k = falta / d; return [p[i - 2] + (p[i] - p[i - 2]) * k, p[i - 1] + (p[i + 1] - p[i - 1]) * k]; }
    falta -= d;
  }
  return [p[0], p[1]];
}
let IDX = null;   // nome visível → trecho / nó
function indexar(g) {
  if (IDX) return IDX;
  IDX = { trecho: new Map(), el: new Map() };
  g.trechos.forEach((t, i) => { t.i = i; IDX.trecho.set(t.n, t); });
  g.els.forEach(e => e.n.forEach(n => IDX.el.set(n, e)));
  return IDX;
}
function posicaoAlvo(g, tipo, nome) {
  const ix = indexar(g);
  if (tipo === 'TRECHO') { const t = ix.trecho.get(nome); return t ? { xy: meioDoTrecho(t), trecho: t } : null; }
  const e = ix.el.get(nome); return e ? { xy: [e.x, e.y] } : null;
}
const rotuloEquipe = id => /^Zona(\d\d)$/.test(id) ? id.slice(4) : id === 'ADUTORA' ? 'AD' : String(id || '?').slice(0, 2).toUpperCase();
const ZONA_ADUTORA = 'Adutora';
const zonaDoTrecho = t => t.tp === 'Adutora' ? ZONA_ADUTORA : t.z;
const nomeZona = z => z === ZONA_ADUTORA ? 'Adutora' : String(z).replace(/^Zona(\d\d)$/, 'Zona $1');

/* ---------------------------------------------------------------- tela inicial: a rede acendendo */
let REDE_OK = false;
async function desenharRede() {
  const svg = $('#redeSvg');
  let g; try { g = await obterGeral(); } catch (_) { return; }
  if (g.ausente) { svg.closest('.inicio-rede').hidden = true; return; }
  if (!REDE_OK) {
    const b = limites(g.trechos.flatMap(t => t.p), 0.03);
    svg.setAttribute('viewBox', `${b[0]} ${b[1]} ${b[2] - b[0]} ${b[3] - b[1]}`);
    const grupos = new Map();
    g.trechos.forEach(t => { const z = zonaDoTrecho(t); if (!grupos.has(z)) grupos.set(z, []); grupos.get(z).push(t); });
    const ordem = [...grupos.keys()].sort((a, b) => (a === ZONA_ADUTORA) - (b === ZONA_ADUTORA) || String(a).localeCompare(String(b)));
    const linhas = ordem.map((z, k) => `<path class="rede-tr rede-zona" style="animation-delay:${z === ZONA_ADUTORA ? 0 : 200 + k * 120}ms;stroke-width:${z === ZONA_ADUTORA ? 3 : 1.5}px" d="${caminho(grupos.get(z).flatMap(t => t.p))}"><title>${esc(nomeZona(z))}</title></path>`).join('');
    svg.innerHTML = `<g id="redeLinhas">${linhas}</g><g id="redePins" class="rede-pins" style="opacity:0"></g>`;
    REDE_OK = true;
  }
  realcarRede(MENU_FOCO === 'iluminado');
  const est = await estadoMapa().catch(() => null);
  if (!est) return;
  const vb = svg.viewBox.baseVal, r = vb.width / 42;
  $('#redePins').innerHTML = est.pins.map(p => {
    const pos = posicaoAlvo(g, p.alvo_tipo, p.alvo_id); if (!pos) return '';
    const [x, y] = pos.xy;
    return `<g><title>${esc(p.equipe)} em ${esc(curto(p.alvo_id))} (check-in de hoje)</title><circle cx="${x}" cy="${y}" r="${r}" fill="#F15922" stroke="#101010" stroke-width="${r / 5}"/>
      <text x="${x}" y="${y}" fill="#fff" font-size="${r * 0.9}" font-weight="700" text-anchor="middle" dominant-baseline="central">${esc(rotuloEquipe(p.equipe))}</text></g>`;
  }).join('');
}
function realcarRede(acesa) {
  const g = $('#redeLinhas'); if (!g) return;
  const luz = acesa ? '#8AD3FA' : '#4DB2EA', brilho = acesa ? 7 : 3;
  g.style.stroke = luz; g.style.filter = `drop-shadow(0 0 ${brilho}px ${luz})`;
  $('#redePins').style.opacity = acesa ? 1 : 0;
}

/* ---------------------------------------------------------------- Mapa iluminado */
// situação de cada trecho, da mais atrasada à mais adiantada; "OK interno" é conferência da Ankara, não aprovação da Caesb
const SITU = [
  { id: 'nao', nome: 'Não iniciado', cor: '#8C8C8C', tracejado: true },
  { id: 'liberado', nome: 'Liberado pela topografia', cor: '#6CB8F0' },
  { id: 'execucao', nome: 'Em execução', cor: '#F15922' },
  { id: 'aguarda', nome: 'Concluído, aguarda o OK interno', cor: '#F2F2F2' },
  { id: 'cadastro', nome: 'OK interno, falta o cadastro', cor: '#A77BF3' },
  { id: 'cadastrado', nome: 'Cadastro aprovado pela Caesb', cor: '#3FD68F' },
];
const SITU_ID = Object.fromEntries(SITU.map(s => [s.id, s]));
function situacao(est, nome) {
  const st = est.status[nome], cam = est.camadas || {};
  if ((cam.cadastro || {})[nome] === '6_APROVADO') return 'cadastrado';
  if (st === 'OK_FISCAL' || st === 'MEDIDO_ANTERIOR') return 'cadastro';
  if (st === 'CONCLUIDO_MES') return 'aguarda';
  if (st === 'EM_EXECUCAO' || (cam.em_campo || {})[nome]) return 'execucao';     // equipe com check-in hoje no trecho (Dados da obra)
  if ((cam.liberado || {})[nome]) return 'liberado';
  return 'nao';
}
// o visor (arrastar, aproximar, clique) serve a este mapa e ao do Dados da obra (planejamento.js): cada um passa o seu
// contexto com svg(), caixa(), desenhar(px, zoom) e clique(alvo, ev)
const ILU = { pronto: false, vb: null, base: null, zona: null, sel: null, pop: null, est: null, anim: 0,
  vis: Object.fromEntries(SITU.map(s => [s.id, true])), cam: { zonas: true, nomes: true, equipes: true }, fundo: 'escura',
  prefixo: 'ilu', svg: () => $('#iluSvg'), caixa: () => $('#ilu'), desenhar: desenharIlu, clique: alvo => cliqueNoMapa(alvo) };
// satélite escurecido por padrão: as cores da situação aparecem por cima, como no mapa do projeto. O escurecimento é um
// véu preto por cima das fotos (opacidade): filtro CSS no satélite refazia a imagem inteira a cada quadro
const FUNDOS = { escura: ['Escura', 0.58], clara: ['Clara', 0.15], sem: ['Sem satélite', 0] };
try { Object.assign(ILU.cam, JSON.parse(localStorage.getItem('mc-ilu-camadas') || '{}')); ILU.fundo = FUNDOS[localStorage.getItem('mc-ilu-fundo')] ? localStorage.getItem('mc-ilu-fundo') : 'escura'; } catch (_) { /* sem storage */ }

/* ---- satélite: as fotos das 25 PBs (o mesmo nos dois mapas) */
// De longe, o mosaico montado no servidor (mapa_geral.mosaico: matriz completa de cada PB, cada uma recortada pelo seu
// quadro). Aproximando, as PBs à vista entram em resolução cheia por cima. Tudo cortado no limite das zonas: fora delas
// não há nada (pedido do responsável em 21/10/2026). Onde nenhuma PB tem foto (~3 % da área, na borda das zonas), fica escuro.
const SAT_DETALHE_PX = 0.7, SAT_DETALHE_MAX = 6;     // unidades do mapa por pixel da tela; PBs carregadas ao mesmo tempo
function htmlSatelite(g, p) {
  return `<defs><clipPath id="${p}ZonasClip">${g.zonas.map(z => `<polygon points="${pontos(z.p)}"/>`).join('')}</clipPath>
      ${g.quadros.map(q => `<clipPath id="${p}Q${esc(q.id)}"><polygon points="${pontos(q.p)}"/></clipPath>`).join('')}</defs>
    <g id="${p}Sat" clip-path="url(#${p}ZonasClip)"><image class="sat-mosaico" href="/mapa/geral.webp?v=${g.versao}" x="0" y="0" width="${g.w}" height="${g.h}" preserveAspectRatio="none"/><g class="sat-detalhe"></g>
      <rect class="sat-veu" x="0" y="0" width="${g.w}" height="${g.h}"/></g>`;
}
const satDe = ctx => $(`#${ctx.prefixo}Sat`);
function ligarSatelite(ctx, g) {                     // sem Pillow no servidor não há mosaico: as PBs inteiras, sempre
  $('.sat-mosaico', satDe(ctx)).addEventListener('error', () => { ctx.semMosaico = true; detalheSatelite(ctx, g, 0); }, { once: true });
}
function detalheSatelite(ctx, g, px) {
  const box = satDe(ctx) && $('.sat-detalhe', satDe(ctx)); if (!box || !ctx.vb) return;
  let quero = [];
  if (ctx.semMosaico) quero = g.imagens.map(im => im.id);
  else if (px < SAT_DETALHE_PX) {
    const [x, y, w, h] = ctx.vb;
    quero = g.quadros.filter(q => { const [x0, y0, x1, y1] = limites([q.p]); return x1 > x && x0 < x + w && y1 > y && y0 < y + h; }).map(q => q.id);
    if (quero.length > SAT_DETALHE_MAX) quero = [];
  }
  ctx.satQuero = quero;
  const ja = new Set($$('[data-pb]', box).map(e => e.dataset.pb));
  if (quero.length === ja.size && quero.every(id => ja.has(id))) return;
  $$('[data-pb]', box).forEach(e => { if (!quero.includes(e.dataset.pb)) e.remove(); });
  const comQuadro = new Set(g.quadros.map(q => q.id));
  ctx.satPend = ctx.satPend || new Set();
  quero.filter(id => !ja.has(id) && !ctx.satPend.has(id)).forEach(id => {
    const im = g.imagens.find(x => x.id === id); if (!im) return;
    // a foto (7 megapixels) é decodificada fora do desenho e só entra pronta: decodificar no meio do zoom travava ~1 s
    const url = `/mapa/pb/${esc(id)}.webp?v=${g.versao}`, pre = new Image();
    ctx.satPend.add(id); pre.src = url;
    pre.decode().catch(() => null).then(() => {
      ctx.satPend.delete(id);
      if (!box.isConnected || !ctx.satQuero.includes(id) || $(`[data-pb="${id}"]`, box)) return;
      box.insertAdjacentHTML('beforeend', `<g data-pb="${esc(id)}"${comQuadro.has(id) ? ` clip-path="url(#${ctx.prefixo}Q${esc(id)})"` : ''}><image href="${url}" width="${im.w}" height="${im.h}" preserveAspectRatio="none" transform="matrix(${im.m.join(' ')})"/></g>`);
    });
  });
}
// as fotos em resolução cheia só são pedidas quando o mapa para (arrastar ou zoom): durante o gesto, fica o mosaico
function satDepois(ctx, g, px) { clearTimeout(ctx.tSat); ctx.tSat = setTimeout(() => detalheSatelite(ctx, g, px), 180); }
const iluSvg = () => $('#iluSvg');

async function carregarIluminado() {
  let g;
  try { g = await obterGeral(); } catch (e) { return avisoIlu('Não consegui abrir o traçado do mapa: ' + e.message); }
  if (g.ausente) return avisoIlu('O mapa do projeto (REV02) não está na pasta mapa/ do sistema.');
  if (!ILU.pronto) montarIluminado(g);
  else ajustarAspecto();
  ILU.est = await estadoMapa(true).catch(() => ILU.est);
  if (ILU.est) colorirIluminado();
}
function avisoIlu(msg) { const a = $('#iluAviso'); a.textContent = msg; a.hidden = !msg; }

function montarIluminado(g) {
  const svg = iluSvg();
  const zonas = g.zonas.map(z => `<polygon class="ilu-zf" data-zona="${esc(z.id)}" points="${pontos(z.p)}" fill="${esc(z.cor)}"/>`).join('')
    + contornosTracejados(g.zonas.map(z => z.p), 'ilu-zl');
  const hits = g.trechos.map((t, i) => `<path class="ilu-hit" data-i="${i}" d="${caminho(t.p)}"/>`).join('');
  svg.innerHTML = `${htmlSatelite(g, 'ilu')}<g id="iluZonas">${zonas}</g><g id="iluSel"></g><g id="iluLinhas"></g><g id="iluHits">${hits}</g>
    <g id="iluNomes">${g.nomes.map(n => `<text class="ilu-nome" x="${n.x}" y="${n.y}">${esc(nomeZona(n.id))}</text>`).join('')}</g><g id="iluPins"></g>`;
  ligarSatelite(ILU, g);
  ILU.base = limites([...g.zonas.map(z => z.p), ...g.trechos.flatMap(t => t.p)], 0.02);
  ILU.vb = null; ajustarAspecto();
  ligarGestos(svg);
  aplicarCamadas();
  ILU.pronto = true;
  new ResizeObserver(() => TELA === 'iluminado' && ajustarAspecto()).observe($('#ilu'));
}

// a área visível acompanha a proporção da tela: arrastar e aproximar usam a mesma escala nos dois eixos
function ajustarAspecto(ctx = ILU) {
  const r = ctx.svg().getBoundingClientRect(); if (!r.width || !r.height) return;
  const [x0, y0, x1, y1] = ctx.vb ? [ctx.vb[0], ctx.vb[1], ctx.vb[0] + ctx.vb[2], ctx.vb[1] + ctx.vb[3]] : ctx.base;
  ctx.vb = encaixar([x0, y0, x1, y1], r.width / r.height);
  desenharVista(ctx);
}
function encaixar([x0, y0, x1, y1], asp) {
  let w = x1 - x0, h = y1 - y0; const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  if (w / h > asp) h = w / asp; else w = h * asp;
  return [cx - w / 2, cy - h / 2, w, h];
}
function desenharVista(ctx = ILU) {
  const svg = ctx.svg(), [x, y, w, h] = ctx.vb, larg = ctx.caixa().getBoundingClientRect().width || 1;   // lido antes de escrever
  if (svg.style.transform || svg.style.willChange) { svg.style.transform = ''; svg.style.willChange = ''; }   // repinta na escala certa
  ctx.vbDes = ctx.vb.slice();
  svg.setAttribute('viewBox', `${x} ${y} ${w} ${h}`);
  ctx.desenhar(w / larg, (ctx.base[2] - ctx.base[0]) / w);   // unidades do mapa por pixel e zoom
}
// um desenho por quadro: o touchpad e a pinça mandam vários eventos por quadro, e cada desenho refaz estilo e layout
function agendarVista(ctx = ILU) {
  if (!ctx.quadro) ctx.quadro = requestAnimationFrame(() => { ctx.quadro = 0; (window.__GPU && ctx.gesto ? moverVista : desenharVista)(ctx); });
}
// PROTÓTIPO: durante o gesto a placa de vídeo move e amplia a imagem já pronta (transform); o desenho de verdade só
// quando o gesto para (150 ms sem evento)
function moverVista(ctx) {
  const svg = ctx.svg(), [x, y, w] = ctx.vb, [dx, dy, dw] = ctx.vbDes || ctx.vb, larg = ctx.caixa().getBoundingClientRect().width || 1;
  if (!svg.style.willChange) { svg.style.willChange = 'transform'; svg.style.transformOrigin = '0 0'; }
  const k = larg / w;
  svg.style.transform = `translate(${(dx - x) * k}px, ${(dy - y) * k}px) scale(${dw / w})`;
  clearTimeout(ctx.tGesto);
  ctx.tGesto = setTimeout(() => { ctx.gesto = false; desenharVista(ctx); }, 150);
}
// espessura que acompanha o zoom em degraus de 0,25 px: mudar a espessura do grupo refaz o estilo de todos os trechos
const degrau = v => Math.round(v * 4) / 4;
function espessura(el, px) { const v = degrau(px) + 'px'; if (el.style.strokeWidth !== v) el.style.strokeWidth = v; }
function desenharIlu(px, zoom) {
  if (ILU.fundo !== 'sem') satDepois(ILU, GERAL, px);
  if (escalaMudou(ILU, px)) {                        // arrastar não muda a escala: só o zoom mexe em traços e textos
    $('#iluZonas').style.setProperty('--k', 1 / px);   // só no grupo do contorno: na raiz, refazia o estilo do mapa inteiro
    espessura($('#iluLinhas'), Math.min(6, 2.4 * Math.pow(Math.max(zoom, 1), 0.35)));
    $$('#iluNomes text').forEach(t => { t.setAttribute('font-size', 14 * px); t.setAttribute('stroke-width', 3.5 * px); });
    $$('#iluPins .ilu-pin').forEach(p => {
      const c = p.querySelector('circle'), tx = p.querySelector('text');
      c.setAttribute('r', 15 * px); c.setAttribute('stroke-width', 3 * px); tx.setAttribute('font-size', 13 * px);
    });
    espessura($('#iluSel'), Math.min(11, 7 * Math.pow(Math.max(zoom, 1), 0.3)));
  }
  trilha($('#iluTrilha'), ILU.zona ? `<button type="button" data-ilu-tudo>Obra inteira</button> › ${esc(nomeZona(ILU.zona))}` : zoom > 1.15 ? '<button type="button" data-ilu-tudo>Ver a obra inteira</button>' : 'Obra inteira');
}
// a escala só muda com o zoom (2 % de folga); ctx.ultPx = 0 força o redesenho (pinos novos, cores novas)
function escalaMudou(ctx, px) {
  if (ctx.ultPx && Math.abs(px - ctx.ultPx) <= ctx.ultPx * 0.02) return false;
  ctx.ultPx = px;
  return true;
}
const trilha = (el, html) => { if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; } };
function irPara(alvo, animar = true, ctx = ILU) {
  const r = ctx.caixa().getBoundingClientRect();
  const fim = encaixar(alvo, r.width / r.height), ini = ctx.vb.slice();
  const reduzir = matchMedia('(prefers-reduced-motion: reduce)').matches;
  cancelAnimationFrame(ctx.anim);
  if (!animar || reduzir) { ctx.vb = fim; return desenharVista(ctx); }
  const t0 = performance.now(), dur = 520;
  const passo = t => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    ctx.vb = ini.map((v, i) => v + (fim[i] - v) * e); desenharVista(ctx);
    if (k < 1) ctx.anim = requestAnimationFrame(passo);
  };
  ctx.anim = requestAnimationFrame(passo);
}
function zoomEm(fator, cx, cy, ctx = ILU) {
  const [x, y, w, h] = ctx.vb, larg = ctx.base[2] - ctx.base[0];
  const nw = Math.max(larg / 60, Math.min(larg * 1.6, w * fator)); const k = nw / w;
  if (cx == null) { cx = x + w / 2; cy = y + h / 2; }
  ctx.vb = [cx - (cx - x) * k, cy - (cy - y) * k, w * k, h * k];
  agendarVista(ctx);
}
function pontoDoMapa(ev, ctx = ILU) {
  const r = ctx.caixa().getBoundingClientRect(), [x, y, w, h] = ctx.vb;
  return [x + (ev.clientX - r.left) / r.width * w, y + (ev.clientY - r.top) / r.height * h];
}

// arrastar para mover, roda/pinça para aproximar; toque sem arrastar = clique (trecho, pino ou zona)
function ligarGestos(svg, ctx = ILU) {
  const dedos = new Map(); let inicio = null, arrastou = false, pinca = null;
  svg.addEventListener('pointerdown', ev => {
    dedos.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (dedos.size === 1) { inicio = { x: ev.clientX, y: ev.clientY, vb: ctx.vb.slice(), alvo: ev.target }; arrastou = false; }
    if (dedos.size === 2) { const [a, b] = [...dedos.values()]; pinca = { d: Math.hypot(a.x - b.x, a.y - b.y), vb: ctx.vb.slice() }; arrastou = true; }
  });
  svg.addEventListener('pointermove', ev => {
    if (!dedos.has(ev.pointerId)) return;
    dedos.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    const r = ctx.caixa().getBoundingClientRect();
    if (dedos.size === 2 && pinca) {
      const [a, b] = [...dedos.values()], d = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      ctx.vb = pinca.vb.slice(); zoomEm(pinca.d / d, ...pontoDoMapa({ clientX: (a.x + b.x) / 2, clientY: (a.y + b.y) / 2 }, ctx), ctx);
      return;
    }
    if (!inicio) return;
    const dx = ev.clientX - inicio.x, dy = ev.clientY - inicio.y;
    if (!arrastou && Math.hypot(dx, dy) < 5) return;
    if (!arrastou) { arrastou = true; svg.setPointerCapture(ev.pointerId); ctx.caixa().classList.add('arrastando'); }
    const k = inicio.vb[2] / r.width;
    ctx.vb = [inicio.vb[0] - dx * k, inicio.vb[1] - dy * k, inicio.vb[2], inicio.vb[3]];
    ctx.gesto = true; agendarVista(ctx);
  });
  const soltar = ev => {
    dedos.delete(ev.pointerId);
    if (dedos.size < 2) pinca = null;
    if (dedos.size) return;
    ctx.caixa().classList.remove('arrastando');
    if (inicio && !arrastou && ev.type === 'pointerup') ctx.clique(inicio.alvo, ev);
    inicio = null;
  };
  svg.addEventListener('pointerup', soltar);
  svg.addEventListener('pointercancel', soltar);
  svg.addEventListener('wheel', ev => { ev.preventDefault(); ctx.gesto = true; zoomEm(Math.pow(1.0018, ev.deltaY), ...pontoDoMapa(ev, ctx), ctx); }, { passive: false });
}
function cliqueNoMapa(alvo) {
  fecharPop();
  const hit = alvo.closest && alvo.closest('.ilu-hit'), pin = alvo.closest && alvo.closest('.ilu-pin'), zona = alvo.closest && alvo.closest('.ilu-zf');
  if (hit) return abrirFicha('TRECHO', GERAL.trechos[+hit.dataset.i].n);
  if (pin) return focarAlvo(pin.dataset.tipo, pin.dataset.alvo);
  if (zona) return focarZona(zona.dataset.zona);
}
function focarZona(z) {
  ILU.zona = z;
  const ts = GERAL.trechos.filter(t => zonaDoTrecho(t) === z), poli = GERAL.zonas.find(x => x.id === z);
  const b = limites([...(poli ? [poli.p] : []), ...ts.flatMap(t => t.p)], 0.06);
  aplicarCamadas(); irPara(b);
}
function verTudo() { ILU.zona = null; aplicarCamadas(); irPara(ILU.base); }
function focarAlvo(tipo, nome) {
  const pos = posicaoAlvo(GERAL, tipo, nome); if (!pos) return;
  const larg = (ILU.base[2] - ILU.base[0]) / 9, [x, y] = pos.xy;
  irPara([x - larg / 2, y - larg / 2, x + larg / 2, y + larg / 2]);
  abrirFicha(tipo, nome);
}

function colorirIluminado() {
  const est = ILU.est, por = Object.fromEntries(SITU.map(s => [s.id, []]));
  GERAL.trechos.forEach(t => { t.s = situacao(est, t.n); por[t.s].push(t); });
  $('#iluLinhas').innerHTML = SITU.map(s => s.tracejado
    ? linhasTracejadas(por[s.id], `class="ilu-tr" data-situ="${s.id}" stroke="${s.cor}" stroke-dasharray="5 4"`)
    : `<path class="ilu-tr" data-situ="${s.id}" stroke="${s.cor}" d="${caminho(por[s.id].flatMap(t => t.p))}"/>`).join('');
  desenharPins(); aplicarCamadas(); ILU.ultPx = 0; desenharVista();
  if (ILU.sel) marcarSelecao();
  if (ILU.pop) abrirPop(ILU.pop, true);
}
function desenharPins() {
  $('#iluPins').innerHTML = (ILU.est.pins || []).map(p => {
    const pos = posicaoAlvo(GERAL, p.alvo_tipo, p.alvo_id); if (!pos) return '';
    const [x, y] = pos.xy;
    return `<g class="ilu-pin" data-tipo="${esc(p.alvo_tipo)}" data-alvo="${esc(p.alvo_id)}"><title>${esc(equipeNome(p.equipe))} em ${esc(curto(p.alvo_id))} (check-in de hoje)</title>
      <circle cx="${x}" cy="${y}"/><text x="${x}" y="${y}">${esc(rotuloEquipe(p.equipe))}</text></g>`;
  }).join('');
}
const equipeNome = id => ((RESUMO && RESUMO.equipes) || []).find(e => e.id === id)?.nome || id;
function aplicarCamadas() {
  satDe(ILU).style.display = ILU.fundo === 'sem' ? 'none' : '';
  $('.sat-veu', satDe(ILU)).setAttribute('fill-opacity', FUNDOS[ILU.fundo][1]);
  $('#iluZonas').style.display = ILU.cam.zonas ? '' : 'none';
  $$('#iluZonas .ilu-zf').forEach(p => p.setAttribute('fill-opacity', ILU.zona ? (p.dataset.zona === ILU.zona ? 0.38 : 0.08) : 0.26));
  $('#iluNomes').style.display = ILU.cam.nomes ? '' : 'none';
  $('#iluPins').style.display = ILU.cam.equipes ? '' : 'none';
  $$('#iluLinhas .ilu-tr').forEach(p => p.style.display = ILU.vis[p.dataset.situ] ? '' : 'none');
  if (GERAL && GERAL.trechos[0] && GERAL.trechos[0].s) $$('#iluHits .ilu-hit').forEach(h => h.style.display = ILU.vis[GERAL.trechos[+h.dataset.i].s] ? '' : 'none');
  try { localStorage.setItem('mc-ilu-camadas', JSON.stringify(ILU.cam)); localStorage.setItem('mc-ilu-fundo', ILU.fundo); } catch (_) { /* sem storage */ }
}

/* ---- janelas das ferramentas: Situação, Zonas, Equipes e Camadas */
const km = m => (m / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' km';
function abrirPop(nome, recarregar) {
  if (ILU.pop === nome && !recarregar) return fecharPop();
  fecharPop(); ILU.pop = nome;
  const pop = $('#pop' + nome[0].toUpperCase() + nome.slice(1)); pop.hidden = false;
  $(`.ilu-bt[data-pop="${nome}"]`).setAttribute('aria-expanded', 'true');
  const ts = GERAL.trechos.filter(t => !ILU.zona || zonaDoTrecho(t) === ILU.zona);
  if (nome === 'situacao') {
    const conta = Object.fromEntries(SITU.map(s => [s.id, { n: 0, m: 0 }]));
    ts.forEach(t => { if (t.s) { conta[t.s].n++; conta[t.s].m += t.L || 0; } });
    pop.innerHTML = `<h3>Situação dos trechos: ${esc(ILU.zona ? nomeZona(ILU.zona) : 'obra inteira')}</h3>`
      + SITU.map(s => `<button type="button" class="ilu-linha" data-situ="${s.id}" aria-pressed="${ILU.vis[s.id]}"><i class="${s.tracejado ? 'tracejado' : ''}" style="border-color:${s.cor}"></i>
        <span>${esc(s.nome)}</span><span class="fim">${nf(conta[s.id].n, 0)} · ${km(conta[s.id].m)}</span></button>`).join('')
      + '<p>Toque numa linha para mostrar ou esconder. "OK interno" é a conferência da Ankara; o verde só aparece com a aprovação da Caesb registrada.</p>';
  }
  if (nome === 'zonas') {
    const zs = [...new Set(GERAL.trechos.map(zonaDoTrecho))].sort((a, b) => (a === ZONA_ADUTORA) - (b === ZONA_ADUTORA) || String(a).localeCompare(String(b)));
    const tot = z => GERAL.trechos.filter(t => zonaDoTrecho(t) === z);
    pop.innerHTML = '<h3>Zonas</h3>' + `<button type="button" class="ilu-linha" data-zona="" aria-current="${!ILU.zona}"><i class="zona"></i><span>Obra inteira</span><span class="fim">${nf(GERAL.trechos.length, 0)} trechos · ${km(GERAL.trechos.reduce((a, t) => a + (t.L || 0), 0))}</span></button>`
      + zs.map(z => { const l = tot(z); const cor = (GERAL.zonas.find(x => x.id === z) || {}).cor || '#F2F2F2';
        return `<button type="button" class="ilu-linha" data-zona="${esc(z)}" aria-current="${ILU.zona === z}"><i class="zona" style="background:${cor}33;border-color:${cor}"></i><span>${esc(nomeZona(z))}</span>
          <span class="fim">${nf(l.length, 0)} trechos · ${km(l.reduce((a, t) => a + (t.L || 0), 0))}</span></button>`; }).join('');
  }
  if (nome === 'equipes') {
    const pins = Object.fromEntries((ILU.est.pins || []).map(p => [p.equipe, p]));
    const plan = {};
    Object.entries((ILU.est.camadas || {}).planejado || {}).forEach(([n, p]) => p.hoje && p.equipes.forEach(e => (plan[e] = plan[e] || []).push(n)));
    pop.innerHTML = '<h3>Equipes hoje</h3>' + ((RESUMO && RESUMO.equipes) || []).map(e => {
      const p = pins[e.id], pl = plan[e.id] || [];
      const txt = p ? `em ${esc(curto(p.alvo_id))}, check-in de hoje` : pl.length ? `programada para ${esc(pl.slice(0, 3).map(curto).join(', '))}${pl.length > 3 ? '…' : ''}; sem check-in` : 'sem check-in hoje';
      return `<button type="button" class="ilu-linha" ${p ? `data-ir-tipo="${esc(p.alvo_tipo)}" data-ir="${esc(p.alvo_id)}"` : pl.length ? `data-ir-tipo="TRECHO" data-ir="${esc(pl[0])}"` : 'disabled'}>
        <span class="num${p ? '' : ' sem'}">${esc(rotuloEquipe(e.id))}</span><span>${esc(e.nome)}<small>${txt}</small></span></button>`;
    }).join('') + '<p>O pino aparece onde a equipe fez o check-in hoje. Equipe sem check-in não tem pino.</p>';
  }
  if (nome === 'camadas') {
    const ch = (k, rot) => `<button type="button" class="ilu-linha" data-camada="${k}" aria-pressed="${ILU.cam[k]}"><span>${ILU.cam[k] ? '☑' : '☐'}</span><span>${rot}</span></button>`;
    pop.innerHTML = '<h3>Fundo de satélite</h3><div class="ilu-fundos">' + Object.entries(FUNDOS).map(([k, [rot]]) =>
      `<button type="button" class="ilu-fundo" data-fundo="${k}" aria-pressed="${ILU.fundo === k}">${rot}</button>`).join('') + '</div>'
      + '<h3 style="margin-top:14px">Camadas</h3>' + ch('zonas', 'Zonas oficiais') + ch('nomes', 'Nomes das zonas') + ch('equipes', 'Equipes');
  }
}
function fecharPop() {
  ILU.pop = null;
  $$('.ilu-pop').forEach(p => p.hidden = true);
  $$('.ilu-bt[data-pop]').forEach(b => b.setAttribute('aria-expanded', 'false'));
}
$('#iluFerr').addEventListener('click', ev => {
  const bt = ev.target.closest('.ilu-bt[data-pop]'); if (bt) return GERAL && ILU.est && abrirPop(bt.dataset.pop);
  const s = ev.target.closest('[data-situ]'); if (s) { ILU.vis[s.dataset.situ] = !ILU.vis[s.dataset.situ]; aplicarCamadas(); return abrirPop('situacao', true); }
  const z = ev.target.closest('[data-zona]'); if (z) { fecharPop(); return z.dataset.zona ? focarZona(z.dataset.zona) : verTudo(); }
  const e = ev.target.closest('[data-ir]'); if (e) { fecharPop(); return focarAlvo(e.dataset.irTipo, e.dataset.ir); }
  const c = ev.target.closest('[data-camada]'); if (c) { ILU.cam[c.dataset.camada] = !ILU.cam[c.dataset.camada]; aplicarCamadas(); return abrirPop('camadas', true); }
  const fu = ev.target.closest('[data-fundo]'); if (fu) { ILU.fundo = fu.dataset.fundo; aplicarCamadas(); desenharVista(); return abrirPop('camadas', true); }
});
document.addEventListener('pointerdown', ev => { if (ILU.pop && !ev.target.closest('.ilu-bloco')) fecharPop(); });
document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && TELA === 'iluminado') { fecharPop(); fecharFicha(); } });
$('#iluMais').addEventListener('click', () => zoomEm(1 / 1.5));
$('#iluMenos').addEventListener('click', () => zoomEm(1.5));
$('#iluTudo').addEventListener('click', verTudo);
$('#iluTrilha').addEventListener('click', ev => { if (ev.target.closest('[data-ilu-tudo]')) verTudo(); });

/* ---- ficha do trecho (ou do nó) tocado no mapa */
const nomeCurto = n => String(n || '').split('_').pop();          // Zona03_PB06_Rede_TR014 → TR014
const FOTO_NOME = { SINALIZACAO: 'sinalização', EXECUCAO: 'execução', CONCLUIDO: 'concluído' };
// o trecho tocado e, se ele faz parte de um trecho físico (cruzamento, divisa de zona…), as outras linhas dele
function marcarSelecao() {
  const ix = ILU.sel && ILU.sel.tipo === 'TRECHO' && GERAL ? indexar(GERAL) : null, t = ix && ix.trecho.get(ILU.sel.nome);
  const outros = t && ILU.sel.fisico ? ILU.sel.fisico.membros.map(m => ix.trecho.get(m.ponto)).filter(x => x && x !== t) : [];
  $('#iluSel').innerHTML = !t ? '' : (outros.length ? `<path class="ilu-sel" stroke-opacity=".55" d="${caminho(outros.flatMap(x => x.p))}"/>` : '')
    + `<path class="ilu-sel" stroke-opacity=".9" d="${caminho(t.p)}"/>`;
}
function fecharFicha() { ILU.sel = null; $('#iluFicha').hidden = true; marcarSelecao(); }
async function abrirFicha(tipo, nome) {
  ILU.sel = { tipo, nome }; marcarSelecao();
  const f = $('#iluFicha'); f.hidden = false;
  f.innerHTML = `<button type="button" class="ilu-bt quadrado fechar" aria-label="Fechar">×</button><h2>${esc(nomeCurto(nome))}</h2><p class="vazio">Carregando…</p>`;
  const [d, topo] = await Promise.all([api(`/api/detalhe?tipo=${tipo}&id=${encodeURIComponent(nome)}`).catch(e => ({ erro: e.message })),
    tipo === 'TRECHO' ? api(`/api/topologia?trecho=${encodeURIComponent(nome)}`).catch(() => null) : null]);
  if (!ILU.sel || ILU.sel.nome !== nome) return;
  if (d.erro) { f.querySelector('.vazio').textContent = d.erro; return; }
  const fis = topo && topo.trecho_fisico && topo.trecho_fisico.membros.length > 1 ? topo.trecho_fisico : null;
  ILU.sel.fisico = fis; marcarSelecao();
  const t = indexar(GERAL).trecho.get(nome), s = SITU_ID[t && t.s ? t.s : ILU.est ? situacao(ILU.est, nome) : 'nao'];
  const ex = d.execucao, faltam = d.fotos_faltando || [];
  const pend = (d.pendencias || []).length;
  const linhas = tipo === 'TRECHO' ? [
    ['Zona e planta', `${esc(nomeZona(t ? zonaDoTrecho(t) : d.frente_id))} · ${esc(d.pb || (t && t.pb) || '')}`],
    ['Extensão', `${nf(d.extensao_m)} m`], ['Tubo', `DE ${esc(d.de_mm)} · ${esc(d.material || '')} · ${esc(d.metodologia || '')}`],
    ['Pontas', `${esc(curto(d.no_ini))} → ${esc(curto(d.no_fim))}`],
    ...(fis ? [['Trecho físico', esc(fis.texto.replace(/^Trecho físico:\s*/, ''))]] : []),
    ['Executado', ex ? `${nf(ex.metros_executados)} m assentados · ${nf(ex.metros_reaterrados)} m reaterrados` : 'nada lançado'],
    ['Fotos', faltam.length ? `faltam ${faltam.map(c => FOTO_NOME[c] || esc(c)).join(', ')}` : ex ? 'completas' : '—'],
    ['Pendências', pend ? `${pend} aberta${pend > 1 ? 's' : ''}` : 'nenhuma'],
  ] : [['Elemento', `${esc(d.numero)} · ${esc(d.tipo_elemento || '')} · ${esc(d.pb || '')}`], ['Frente', esc(d.frente_id)], ['Pendências', pend ? `${pend} aberta${pend > 1 ? 's' : ''}` : 'nenhuma']];
  const prox = (d.programacoes || []).find(p => p.status === 'PLANEJADA');
  if (prox) linhas.push(['Programado', `${esc(prox.data.split('-').reverse().join('/'))} · ${esc(equipeNome(prox.equipe_id))}`]);
  f.innerHTML = `<button type="button" class="ilu-bt quadrado fechar" aria-label="Fechar">×</button>
    <h2>${esc(nomeCurto(d.nome || nome))}</h2>
    ${tipo === 'TRECHO' ? `<span class="situ"><i style="border-color:${s.cor}${s.tracejado ? ';border-top-style:dashed' : ''}"></i>${esc(s.nome)}</span>` : ''}
    ${d.retirado ? '<div class="aviso problema">Retirado da revisão vigente do projeto: só consulta.</div>' : ''}
    <dl>${linhas.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
    <div class="acoes">${pode('campo') && !d.retirado ? `<button type="button" class="btn prim" data-ficha-campo>Lançar avanço</button>` : ''}
      <button type="button" class="btn" data-ficha-completa>Ver a ficha completa</button></div>
    <p class="vazio" style="font-size:13px">${esc(d.nome || nome)}</p>`;
  f.dataset.tipo = tipo; f.dataset.id = d.id;
}
$('#iluFicha').addEventListener('click', async ev => {
  const f = $('#iluFicha');
  if (ev.target.closest('.fechar')) return fecharFicha();
  if (ev.target.closest('[data-ficha-completa]')) { await abrirAba('mapa'); return mostrarFiscal(f.dataset.tipo, f.dataset.id); }
  if (ev.target.closest('[data-ficha-campo]')) {
    abrirAba('campo');
    const inp = $('#fApont input[name=alvo_txt]'); inp.value = curto(ILU.sel.nome); inp.dataset.tipo = f.dataset.tipo; inp.dataset.id = f.dataset.id;
    return selecionarCampo(f.dataset.tipo, f.dataset.id);
  }
});
