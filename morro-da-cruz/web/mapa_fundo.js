/* D-209: fundo contínuo de ruas, sem biblioteca de mapas. O desenho REV02 continua nas suas coordenadas:
   só as imagens do fundo são transformadas de Web Mercator para SIRGAS 2000 / UTM 23S e daí para o desenho.
   Pede apenas os tiles da vista parada. Cache HTTP do navegador, sem proxy, pré-busca nem pacote offline. */
const FUNDO_CTX = new Set(), FUNDO_CACHE = new Map(), FUNDO_MAX_CACHE = 96;
const FUNDO_N = (1 / 298.257222101) / (2 - 1 / 298.257222101);
const FUNDO_A = 6378137 / (1 + FUNDO_N) * (1 + FUNDO_N ** 2 / 4 + FUNDO_N ** 4 / 64);
const FUNDO_ALPHA = [FUNDO_N / 2 - 2 * FUNDO_N ** 2 / 3 + 5 * FUNDO_N ** 3 / 16,
  13 * FUNDO_N ** 2 / 48 - 3 * FUNDO_N ** 3 / 5, 61 * FUNDO_N ** 3 / 240];
const FUNDO_BETA = [FUNDO_N / 2 - 2 * FUNDO_N ** 2 / 3 + 37 * FUNDO_N ** 3 / 96,
  FUNDO_N ** 2 / 48 + FUNDO_N ** 3 / 15, 17 * FUNDO_N ** 3 / 480];
const FUNDO_DELTA = [2 * FUNDO_N - 2 * FUNDO_N ** 2 / 3 - 2 * FUNDO_N ** 3,
  7 * FUNDO_N ** 2 / 3 - 8 * FUNDO_N ** 3 / 5, 56 * FUNDO_N ** 3 / 15];
const fundoAfim = (t, x, y) => [t[0] * x + t[1] * y + t[2], t[3] * x + t[4] * y + t[5]];
function fundoUTMGeo(e, n) {
  const xi = (n - 10000000) / (.9996 * FUNDO_A), eta = (e - 500000) / (.9996 * FUNDO_A);
  const x = xi - FUNDO_BETA.reduce((s, b, i) => s + b * Math.sin(2 * (i + 1) * xi) * Math.cosh(2 * (i + 1) * eta), 0);
  const y = eta - FUNDO_BETA.reduce((s, b, i) => s + b * Math.cos(2 * (i + 1) * xi) * Math.sinh(2 * (i + 1) * eta), 0);
  const chi = Math.asin(Math.sin(x) / Math.cosh(y));
  return [(chi + FUNDO_DELTA.reduce((s, d, i) => s + d * Math.sin(2 * (i + 1) * chi), 0)) * 180 / Math.PI,
    -45 + Math.atan2(Math.sinh(y), Math.cos(x)) * 180 / Math.PI];
}
function fundoGeoUTM(lat, lon) {
  const phi = lat * Math.PI / 180, lam = (lon + 45) * Math.PI / 180, ep = 2 * Math.sqrt(FUNDO_N) / (1 + FUNDO_N);
  const tau = Math.sinh(Math.atanh(Math.sin(phi)) - ep * Math.atanh(ep * Math.sin(phi)));
  const xi = Math.atan2(tau, Math.cos(lam)), eta = Math.asinh(Math.sin(lam) / Math.hypot(tau, Math.cos(lam)));
  const x = xi + FUNDO_ALPHA.reduce((s, a, i) => s + a * Math.sin(2 * (i + 1) * xi) * Math.cosh(2 * (i + 1) * eta), 0);
  const y = eta + FUNDO_ALPHA.reduce((s, a, i) => s + a * Math.cos(2 * (i + 1) * xi) * Math.sinh(2 * (i + 1) * eta), 0);
  return [500000 + .9996 * FUNDO_A * y, 10000000 + .9996 * FUNDO_A * x];
}
const fundoGeoTile = (lat, lon, z) => [(lon + 180) / 360 * 2 ** z,
  (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * 2 ** z];
function fundoPontoTile(z, x, y, geo) {
  const lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * y / 2 ** z))) * 180 / Math.PI, lon = x / 2 ** z * 360 - 180;
  return fundoAfim(geo.utm_para_mapa, ...fundoGeoUTM(lat, lon));
}
function fundoMatrizTile(z, x, y, geo) {
  const a = fundoPontoTile(z, x, y, geo), b = fundoPontoTile(z, x + 1, y, geo), c = fundoPontoTile(z, x, y + 1, geo);
  return [(b[0] - a[0]) / 256, (b[1] - a[1]) / 256, (c[0] - a[0]) / 256, (c[1] - a[1]) / 256, a[0], a[1]];
}
function fundoTilesVista(vb, largura, geo) {
  const [x, y, w, h] = vb;
  const cantos = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    .map(p => fundoUTMGeo(...fundoAfim(geo.mapa_para_utm, ...p)));
  const lat = cantos.reduce((s, p) => s + p[0], 0) / 4;
  const escala = Math.sqrt(Math.abs(geo.utm_para_mapa[0] * geo.utm_para_mapa[4] - geo.utm_para_mapa[1] * geo.utm_para_mapa[3]));
  let z = Math.max(12, Math.min(19, Math.ceil(Math.log2(40075016.68558 * Math.cos(lat * Math.PI / 180) * escala / (256 * w / largura)))));
  let box;
  do {
    const cs = cantos.map(p => fundoGeoTile(...p, z));
    box = [Math.floor(Math.min(...cs.map(p => p[0]))), Math.floor(Math.min(...cs.map(p => p[1]))),
      Math.floor(Math.max(...cs.map(p => p[0]))), Math.floor(Math.max(...cs.map(p => p[1])))];
    if ((box[2] - box[0] + 1) * (box[3] - box[1] + 1) <= 64 || z === 12) break;
    z--;
  } while (true);
  const out = [];
  for (let u = box[0]; u <= box[2]; u++) for (let v = box[1]; v <= box[3]; v++) {
    out.push({ chave: `${z}/${u}/${v}`, m: fundoMatrizTile(z, u, v, geo) });
  }
  return out;
}
// Na visão geral, centraliza a prancha e permite só a margem necessária à proporção da tela. Aproximando, a vista
// fica dentro do retângulo da prancha. Vale para arrasto, pinça, roda, botões, busca, animação e vista salva da sessão.
function limitarVistaMapa(ctx, vb) {
  if (!ctx.limiteMapa) return vb;
  const [x0, y0, x1, y1] = ctx.limiteMapa, asp = vb[2] / vb[3];
  const max = encaixar(ctx.limiteMapa, asp), k = Math.min(1, max[2] / vb[2]);
  const w = vb[2] * k, h = vb[3] * k, cx = vb[0] + vb[2] / 2, cy = vb[1] + vb[3] / 2;
  return [w >= x1 - x0 ? (x0 + x1 - w) / 2 : Math.max(x0, Math.min(x1 - w, cx - w / 2)),
    h >= y1 - y0 ? (y0 + y1 - h) / 2 : Math.max(y0, Math.min(y1 - h, cy - h / 2)), w, h];
}
function htmlFundoRuas(g, prefixo) {
  if (!g.contexto) return '';
  return `<g id="${prefixo}Ruas" class="mapa-ruas" pointer-events="none"></g>`;
}
function htmlCanteiro(g) {
  const c = g.contexto && g.contexto.canteiro; if (!c) return '';
  return `<g class="mapa-canteiro" role="button" tabindex="0" aria-label="Aproximar o canteiro de obras">`
    + `<title>Canteiro de obras</title><polygon points="${pontos(c.p)}"/><circle class="canteiro-toque" cx="${c.centro[0]}" cy="${c.centro[1]}"/>`
    + `<text x="${c.centro[0]}" y="${c.centro[1]}">Canteiro</text></g>`;
}
function escalarCanteiro(ctx, px) {
  const c = $('.mapa-canteiro', ctx.svg()); if (!c) return;
  $('circle', c).setAttribute('r', 22 * px);
  $('text', c).setAttribute('font-size', 12 * px); $('text', c).setAttribute('dy', -27 * px);
}
function destacarCanteiro(ctx) {
  const c = GERAL.contexto && GERAL.contexto.canteiro; if (!c) return;
  $('.mapa-canteiro', ctx.svg()).classList.add('destacado');
  irPara(limites([c.p], .8), true, ctx);
}
function ligarFundoRuas(ctx, g) {
  if (!g.contexto) return;
  ctx.limiteMapa = g.contexto.limites;
  FUNDO_CTX.add(ctx);
  const caixa = ctx.caixa();
  caixa.insertAdjacentHTML('beforeend', '<div class="mapa-credito">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> · <a href="https://www.openstreetmap.org/fixthemap" target="_blank" rel="noopener">Corrigir mapa</a></div>'
    + '<div class="mapa-fundo-aviso" role="status" hidden>Fundo de ruas indisponível. A rede continua disponível. <button type="button">Tentar novamente</button></div>');
  $('.mapa-fundo-aviso button', caixa).addEventListener('click', () => {
    for (const [k, t] of FUNDO_CACHE) if (t.erro) FUNDO_CACHE.delete(k);
    atualizarFundoRuas(ctx);
  });
  $('.mapa-canteiro', ctx.svg())?.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); destacarCanteiro(ctx); }
  });
  aplicarFundoRuas(ctx);
}
// Contorno sob os traços claros (branco, amarelo, ciano etc.): as cores e seus significados não mudam.
// Copiado só quando as linhas/visibilidades mudam, nunca durante o gesto na GPU.
function contrasteFundoRuas(ctx, px, zoom) {
  const fonte = $(`#${ctx.prefixo}Linhas`); if (!fonte) return;
  if (!ctx.contrasteEl) { ctx.contrasteEl = document.createElementNS(SVGNS, 'g');
    ctx.contrasteEl.setAttribute('class', 'rede-contraste'); fonte.before(ctx.contrasteEl); }
  const chave = `${ctx.cores || 0}|${Object.values(ctx.vis || {}).join(',')}`;
  if (ctx.contrasteChave !== chave) {
    ctx.contrasteChave = chave; ctx.contrasteEl.innerHTML = fonte.innerHTML;
    $$('[id]', ctx.contrasteEl).forEach(e => { e.removeAttribute('id'); e.style.strokeWidth = ''; });
  }
  const larg = larguraTrecho(zoom, ctx.prefixo === 'ilu' ? 1.1 : .75);
  espessura(ctx.contrasteEl, larg + 1.5);
  // No Iluminado o traço colorido é mais largo que o não iniciado; seu contorno acompanha a mesma escala.
  if (ctx.prefixo === 'ilu') $$('.ilu-tr', ctx.contrasteEl).forEach(p => espessura(p, larguraIlu(zoom, p.dataset.situ) + 1.5));
}
function aplicarFundoRuas(ctx) {
  const ruas = $(`#${ctx.prefixo}Ruas`), ativo = ILU.fundo === 'ruas';
  if (ruas) ruas.style.display = ativo ? '' : 'none';
  const caixa = ctx.caixa(); caixa.classList.toggle('fundo-ruas', ativo);
  const credito = $('.mapa-credito', caixa); if (credito) credito.hidden = !ativo;
  if (!ativo) { const aviso = $('.mapa-fundo-aviso', caixa); if (aviso) aviso.hidden = true; }
  else if (ctx.vb) atualizarFundoRuas(ctx);
}
function fundoTileRecurso(chave) {
  let t = FUNDO_CACHE.get(chave);
  if (t) { FUNDO_CACHE.delete(chave); FUNDO_CACHE.set(chave, t); return t; }
  const im = new Image();
  t = { im, pronto: false, erro: false }; FUNDO_CACHE.set(chave, t);
  im.crossOrigin = 'anonymous'; im.referrerPolicy = 'strict-origin-when-cross-origin';
  im.onload = () => { t.pronto = true; for (const ctx of FUNDO_CTX) if ((ctx.ruasQuero || []).some(q => q.chave === chave)) pintarFundoRuas(ctx); };
  im.onerror = () => { t.erro = true; for (const ctx of FUNDO_CTX) if ((ctx.ruasQuero || []).some(q => q.chave === chave)) pintarFundoRuas(ctx); };
  im.src = `https://tile.openstreetmap.org/${chave}.png`;
  // Só memória: o navegador continua usando seu cache HTTP depois da remoção. Não cria armazenamento offline.
  while (FUNDO_CACHE.size > FUNDO_MAX_CACHE) {
    const protegido = new Set([...FUNDO_CTX].flatMap(ctx => (ctx.ruasQuero || []).map(q => q.chave)));
    const k = [...FUNDO_CACHE.keys()].find(k => !protegido.has(k)); if (!k) break;
    FUNDO_CACHE.delete(k);
  }
  return t;
}
function atualizarFundoRuas(ctx) {
  const caixa = ctx.caixa(), r = caixa.getBoundingClientRect();
  if (ILU.fundo !== 'ruas' || !GERAL.contexto || !ctx.vb || !r.width || !r.height || !caixa.offsetParent) return;
  ctx.ruasQuero = fundoTilesVista(ctx.vb, r.width, GERAL.contexto);
  ctx.ruasQuero.forEach(q => fundoTileRecurso(q.chave));
  pintarFundoRuas(ctx);
}
function pintarFundoRuas(ctx) {
  const box = $(`#${ctx.prefixo}Ruas`); if (!box || ILU.fundo !== 'ruas') return;
  const quero = ctx.ruasQuero || [], prontos = quero.filter(q => FUNDO_CACHE.get(q.chave)?.pronto);
  // Mantém o nível anterior enquanto chegam os tiles novos; não apaga o fundo ao mudar o zoom.
  const manter = new Set(prontos.map(q => q.chave));
  if (prontos.length === quero.length) $$('image', box).forEach(e => { if (!manter.has(e.dataset.tile)) e.remove(); });
  const ja = new Set($$('image', box).map(e => e.dataset.tile));
  prontos.filter(q => !ja.has(q.chave)).forEach(q => {
    const el = document.createElementNS(SVGNS, 'image'); el.dataset.tile = q.chave;
    el.setAttribute('width', '256.1'); el.setAttribute('height', '256.1'); // pequena sobreposição evita frestas de rasterização
    el.setAttribute('preserveAspectRatio', 'none'); el.setAttribute('transform', `matrix(${q.m.join(' ')})`);
    el.setAttribute('href', FUNDO_CACHE.get(q.chave).im.src); el.setAttribute('crossorigin', 'anonymous');
    el.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin'); box.append(el);
  });
  // No máximo o nível atual e um nível anterior durante a carga; erros não acumulam centenas de imagens.
  while (box.children.length > 128) box.firstElementChild.remove();
  const aviso = $('.mapa-fundo-aviso', ctx.caixa()); if (aviso) aviso.hidden = !quero.some(q => FUNDO_CACHE.get(q.chave)?.erro);
  ctx.ruasVersao = (ctx.ruasVersao || 0) + 1; agendarCopia(ctx);
}
function copiarFundoRuas(ctx, canvas) {
  // Usa só imagens que a pessoa já viu. A cópia do gesto nunca dispara pedidos nem pré-carrega outras áreas.
  const box = $(`#${ctx.prefixo}Ruas`); if (!box) return;
  $$('image', box).forEach(el => {
    const t = FUNDO_CACHE.get(el.dataset.tile); if (!t?.pronto) return;
    const m = el.transform.baseVal.consolidate().matrix;
    canvas.save(); canvas.transform(m.a, m.b, m.c, m.d, m.e, m.f); canvas.drawImage(t.im, 0, 0, 256.1, 256.1); canvas.restore();
  });
}
window.addEventListener('online', () => { for (const [k, t] of FUNDO_CACHE) if (t.erro) FUNDO_CACHE.delete(k);
  for (const ctx of FUNDO_CTX) atualizarFundoRuas(ctx); });
