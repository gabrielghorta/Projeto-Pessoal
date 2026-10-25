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
// a situação do mapa é lida uma vez por pedido: telas que pedem juntas (Dados da obra) dividem a mesma resposta. O dia é
// o da tela (Brasília, no navegador): o servidor no PythonAnywhere roda em UTC
async function estadoMapa(novo) {
  if (novo || !ESTADO_MAPA || Date.now() - ESTADO_EM > 30000) {
    if (!ESTADO_P) ESTADO_P = api('/api/mapa/estado?data=' + hoje() + (MEDICAO_ATUAL ? '&medicao=' + MEDICAO_ATUAL : ''))
      .then(e => { ESTADO_MAPA = e; ESTADO_EM = Date.now(); return e; }).finally(() => { ESTADO_P = null; });
    return ESTADO_P;
  }
  return ESTADO_MAPA;
}
const SVGNS = 'http://www.w3.org/2000/svg';
const pontos = p => { let s = ''; for (let i = 0; i < p.length; i += 2) s += (i ? ' ' : '') + p[i] + ',' + p[i + 1]; return s; };
const caminho = partes => partes.map(p => 'M' + pontos(p)).join('');
// Tracejado pesa: o navegador calcula cada traço do caminho inteiro, até fora da tela (de perto, 1,7 s por quadro com a
// rede toda num caminho só). Por isso o tracejado vai em pedaços que o navegador pula quando estão fora da vista: um
// caminho por zona (e por situação: quem chama separa) e o contorno das zonas em pedaços de ~40 unidades do mapa.
// Por zona, e não por trecho: medido em 23/10/2026, são ~80 elementos no lugar de 1.436, e o redesenho ao soltar e a
// passagem do SVG para a placa de vídeo no começo do gesto caem pela metade, sem mudar o desenho. Cada pedaço do contorno
// continua o tracejado de onde o anterior parou (--k = pixels da tela por unidade do mapa, posto a cada zoom), para
// o desenho ficar igual ao do contorno inteiro, inclusive onde duas zonas vizinhas se sobrepõem.
function linhasTracejadas(trechos, attrs) {
  const por = new Map();
  trechos.forEach(t => { const z = zonaDoTrecho(t); if (!por.has(z)) por.set(z, []); por.get(z).push(t); });
  return [...por.values()].map(ts => `<path ${attrs} d="${caminho(ts.flatMap(t => t.p))}"/>`).join('');
}
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
    return `<g><title>${esc(p.equipe)} em ${esc(nomeCompleto(p.alvo_id))} (check-in de hoje)</title><circle cx="${x}" cy="${y}" r="${r}" fill="#F15922" stroke="#101010" stroke-width="${r / 5}"/>
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
// etapa de cada trecho, da mais atrasada à mais adiantada (calculada no servidor, regras.etapa_trecho). "Verificado" e
// "OK interno" são conferência da Ankara; o verde só aparece com a aprovação da Caesb registrada
const SITU = [
  { id: 'nao', nome: 'Não iniciado', cor: '#8C8C8C', tracejado: true },
  { id: 'liberado', nome: 'Liberado pela topografia', cor: '#6CB8F0' },
  { id: 'execucao', nome: 'Em execução hoje', cor: '#F15922' },
  { id: 'executado', nome: 'Executado, aguardando verificação', cor: '#F2C94C' },
  { id: 'verificado', nome: 'Verificado pelo supervisor', cor: '#F28AC0' },
  { id: 'campo', nome: 'Cadastro de campo feito', cor: '#2EC5D9' },
  { id: 'pronto', nome: 'Pronto para o OK interno', cor: '#F2F2F2' },
  { id: 'ok', nome: 'OK interno, na medição', cor: '#A77BF3' },
  { id: 'cad_andamento', nome: 'Cadastro em andamento', cor: '#D6C2FF' },
  { id: 'cadastrado', nome: 'Cadastro aprovado pela Caesb', cor: '#3FD68F' },
];
const SITU_ID = Object.fromEntries(SITU.map(s => [s.id, s]));
const etapaDe = (est, nome) => ((est.camadas || {}).etapas || {})[nome];
function situacao(est, nome) {
  const e = etapaDe(est, nome);
  return e && SITU_ID[e.s] ? e.s : 'nao';
}
// "parcial" quando a execução ainda não cobre o trecho inteiro
const nomeSituacao = (est, nome, s) => SITU_ID[s].nome + ((etapaDe(est, nome) || {}).parcial && ['executado', 'verificado', 'campo'].includes(s) ? ' (parcial)' : '');
// o visor (arrastar, aproximar, clique) serve a este mapa e ao do Dados da obra (planejamento.js): cada um passa o seu
// contexto com svg(), caixa(), desenhar(px, zoom) e clique(alvo, ev)
const ILU = { pronto: false, vb: null, base: null, zona: null, sel: null, pop: null, est: null, anim: 0,
  vis: Object.fromEntries(SITU.map(s => [s.id, true])), cam: { zonas: true, nomes: true, equipes: true }, fundo: 'escura',
  prefixo: 'ilu', svg: () => $('#iluSvg'), caixa: () => $('#ilu'), desenhar: desenharIlu, clique: cliqueNoMapa,
  copia: (g, u) => copiaIlu(g, u), tocavel: t => !t.s || ILU.vis[t.s],     // situação escondida não se toca
  copiaChave: () => [ILU.fundo, ILU.cam.zonas, SITU.map(s => +ILU.vis[s.id]).join(''), ILU.cores || 0, !!ILU.mosaico].join('|') };
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
// o mosaico pela metade, para a cópia leve do gesto (decodificado e reduzido fora do desenho)
function carregarMosaicoCopia(g) {
  const im = new Image(); im.src = `/mapa/geral.webp?v=${g.versao}`;
  im.decode().then(() => createImageBitmap(im, { resizeWidth: Math.max(1, Math.round(im.naturalWidth / 2)),
    resizeHeight: Math.max(1, Math.round(im.naturalHeight / 2)), resizeQuality: 'medium' }))
    .then(b => { ILU.mosaico = b; agendarCopia(ILU); }).catch(() => null);      // sem mosaico (sem Pillow): cópia sem satélite
}
// a cópia leve do Mapa iluminado: o mosaico com o véu, cortado nas zonas, as zonas e as linhas por situação
function copiaIlu(g, u) {
  if (ILU.fundo !== 'sem' && ILU.mosaico) {
    g.save(); g.beginPath(); GERAL.zonas.forEach(z => poligonoCopia(g, z.p)); g.clip();
    g.drawImage(ILU.mosaico, 0, 0, GERAL.w, GERAL.h);
    g.globalAlpha = FUNDOS[ILU.fundo][1]; g.fillStyle = '#000'; g.fillRect(0, 0, GERAL.w, GERAL.h);
    g.restore();
  }
  if (ILU.cam.zonas) zonasCopia(g, u, () => 0.26);         // sem a zona em foco: mudar o foco não refaz a cópia
  linhasCopia(g, u, SITU.filter(s => ILU.vis[s.id]).map(s => ({ cor: s.cor, tracejado: s.tracejado ? '5 4' : null, trechos: GERAL.trechos.filter(t => t.s === s.id) })));
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
  if (!ILU.lista && pode('verificar')) $('#iluBlocoLista').hidden = false;          // supervisor: "Aguardando verificação"
  else if (ILU.lista && ILU.lista.verificacao) { ILU.lista = null; if (ILU.pop === 'lista') abrirPop('lista', true); }   // relê depois de verificar
  if (ILU.abrirLista && ILU.est) { ILU.abrirLista = false; abrirPop('lista', true); }
}
function avisoIlu(msg) { const a = $('#iluAviso'); a.textContent = msg; a.hidden = !msg; }

function montarIluminado(g) {
  const svg = iluSvg();
  const zonas = g.zonas.map(z => `<polygon class="ilu-zf" data-zona="${esc(z.id)}" points="${pontos(z.p)}" fill="${esc(z.cor)}"/>`).join('')
    + contornosTracejados(g.zonas.map(z => z.p), 'ilu-zl');
  svg.innerHTML = `${htmlSatelite(g, 'ilu')}<g id="iluZonas">${zonas}</g><g id="iluSel"></g><g id="iluLinhas"></g>
    <g id="iluNomes">${g.nomes.map(n => `<text class="ilu-nome" x="${n.x}" y="${n.y}">${esc(nomeZona(n.id))}</text>`).join('')}</g><g id="iluPins"></g>`;
  ligarSatelite(ILU, g); carregarMosaicoCopia(g);
  ILU.base = limites([...g.zonas.map(z => z.p), ...g.trechos.flatMap(t => t.p)], 0.02);
  ILU.vb = null; ajustarAspecto();
  ligarGestos(svg);
  aplicarCamadas();
  ILU.pronto = true;
  new ResizeObserver(() => TELA === 'iluminado' && ajustarAspecto()).observe($('#ilu'));
}

// a área visível acompanha a proporção da tela: arrastar e aproximar usam a mesma escala nos dois eixos
function ajustarAspecto(ctx = ILU) {
  const r = ctx.caixa().getBoundingClientRect(); if (!r.width || !r.height) return;   // a caixa: o SVG pode estar transformado
  const [x0, y0, x1, y1] = ctx.vb ? [ctx.vb[0], ctx.vb[1], ctx.vb[0] + ctx.vb[2], ctx.vb[1] + ctx.vb[3]] : ctx.base;
  ctx.vb = encaixar([x0, y0, x1, y1], r.width / r.height);
  pararAnimacao(ctx); redesenhar(ctx); agendarCopia(ctx);
}
function encaixar([x0, y0, x1, y1], asp) {
  let w = x1 - x0, h = y1 - y0; const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  if (w / h > asp) h = w / asp; else w = h * asp;
  return [cx - w / 2, cy - h / 2, w, h];
}
// o desenho de verdade: o viewBox muda e o navegador refaz estilo, pintura e rasterização do SVG inteiro
function desenharVista(ctx = ILU) {
  const svg = ctx.svg(), [x, y, w, h] = ctx.vb, larg = ctx.caixa().getBoundingClientRect().width || 1;   // lido antes de escrever
  if (svg.style.transform || svg.style.willChange) { svg.style.transform = ''; svg.style.willChange = ''; }   // repinta na escala certa
  ctx.vbDes = ctx.vb.slice();
  svg.setAttribute('viewBox', `${x} ${y} ${w} ${h}`);
  if (!ctx.fundoVista || !ctx.fundoVista.isConnected) {          // fundo opaco do desenho: esconde a cópia leve por baixo
    svg.insertAdjacentHTML('afterbegin', '<rect class="vista-fundo"/>'); ctx.fundoVista = svg.firstElementChild;
  }
  ['x', 'y', 'width', 'height'].forEach((a, i) => ctx.fundoVista.setAttribute(a, ctx.vb[i]));
  posicionarCopia(ctx, larg);
  ctx.desenhar(w / larg, (ctx.base[2] - ctx.base[0]) / w);   // unidades do mapa por pixel e zoom
}
// gesto (arrastar, roda, pinça, botões + e −, animação de irPara): a placa de vídeo só move e amplia a imagem já
// desenhada (transform), sem refazer o SVG; o desenho de verdade vem quando o gesto para (150 ms sem evento) ou, ao
// soltar o dedo ou o botão do mouse, na hora
function gestoVista(ctx, espera = 150) {
  ctx.gesto = true; agendarVista(ctx);
  clearTimeout(ctx.tGesto); ctx.tGesto = setTimeout(() => soltarVista(ctx), espera);
}
function soltarVista(ctx) { if (ctx.gesto) redesenhar(ctx); else clearTimeout(ctx.tGesto); }
function redesenhar(ctx) {
  clearTimeout(ctx.tGesto); ctx.gesto = false;
  if (ctx.quadro) { cancelAnimationFrame(ctx.quadro); ctx.quadro = 0; }
  desenharVista(ctx);
}
// um quadro por vez: o touchpad e a pinça mandam vários eventos por quadro
function agendarVista(ctx = ILU) {
  if (!ctx.quadro) ctx.quadro = requestAnimationFrame(() => { ctx.quadro = 0; (ctx.gesto ? moverVista : desenharVista)(ctx); });
}
// translate + scale entre o que está desenhado (ctx.vbDes) e o que se pede (ctx.vb). O will-change só vale durante o
// gesto: ligado depois, o navegador guardava a escala de pintura do gesto e o mapa ficava preto ao aproximar
function moverVista(ctx) {
  const svg = ctx.svg(), larg = ctx.caixa().getBoundingClientRect().width || 1;
  if (!svg.style.willChange) { svg.style.willChange = 'transform'; svg.style.transformOrigin = '0 0'; }
  svg.style.transform = transformVista(ctx, ctx.vb, larg);
  posicionarCopia(ctx, larg);
}
// o transform que leva o desenho (ctx.vbDes) até a vista vb
function transformVista(ctx, [x, y, w], larg) {
  const [dx, dy, dw] = ctx.vbDes || ctx.vb, k = larg / w;
  return `translate(${(dx - x) * k}px, ${(dy - y) * k}px) scale(${dw / w})`;
}
// fração da área visível que ainda não foi desenhada (o gesto afastou ou arrastou além do desenho e da cópia)
function descoberto(ctx) {
  if (!ctx.gesto || !ctx.vbDes || ctx.regiaoCopia) return 0;      // a cópia cobre a maior vista possível
  const [x, y, w, h] = ctx.vb, [dx, dy, dw, dh] = ctx.vbDes;
  const cobre = Math.max(0, Math.min(x + w, dx + dw) - Math.max(x, dx)) * Math.max(0, Math.min(y + h, dy + dh) - Math.max(y, dy));
  return 1 - cobre / (w * h);
}

/* ---- cópia leve por baixo do mapa, para o gesto: a obra inteira desenhada de vez em quando num <canvas>, em baixa
   resolução, que se move junto com o SVG. Ao afastar ou arrastar além do que está desenhado aparece ela, e não o fundo
   vazio. O SVG tem um fundo opaco do tamanho do desenho (.vista-fundo): parado, a cópia fica toda escondida atrás dele.
   Cada mapa diz o que vai na cópia em ctx.copia(g, u), em unidades do mapa (u: unidades por pixel da cópia). */
const COPIA_FOLGA = 1.6;                 // zoomEm afasta até 1,6 × a obra: a cópia cobre a maior vista possível
const COPIA_RES = 0.75;                  // pixels da cópia por pixel da tela, com a obra inteira à vista (é só para a borda do gesto)
function agendarCopia(ctx) {
  clearTimeout(ctx.tCopia);
  ctx.tCopia = setTimeout(() => (ctx.gesto ? agendarCopia(ctx) : desenharCopia(ctx)), 300);   // nunca no meio do gesto
}
function desenharCopia(ctx) {
  const caixa = ctx.caixa(), r = caixa.getBoundingClientRect(); if (!r.width || !r.height || !ctx.base || !ctx.copia) return;
  const chave = `${Math.round(r.width)}×${Math.round(r.height)}|${ctx.copiaChave()}`;   // só refaz o que mudou: refazer a cópia
  if (chave === ctx.copiaFeita) return;                                                // custa um quadro (a imagem vai de novo
  ctx.copiaFeita = chave;                                                              // para a placa de vídeo)
  if (!ctx.copiaEl) {
    ctx.copiaEl = document.createElement('canvas'); ctx.copiaEl.className = 'vista-copia'; ctx.copiaEl.setAttribute('aria-hidden', 'true');
    caixa.prepend(ctx.copiaEl);
  }
  const [x, y, w, h] = encaixar(ctx.base, r.width / r.height), cv = ctx.copiaEl;
  const R = [x + w / 2 - w * COPIA_FOLGA / 2, y + h / 2 - h * COPIA_FOLGA / 2, w * COPIA_FOLGA, h * COPIA_FOLGA];
  const larg = Math.min(4096, Math.round(r.width * COPIA_FOLGA * COPIA_RES)), alt = Math.min(4096, Math.round(larg * R[3] / R[2])), s = larg / R[2];
  if (cv.width !== larg || cv.height !== alt) { cv.width = larg; cv.height = alt; cv.style.width = larg + 'px'; cv.style.height = alt + 'px'; }
  const g = cv.getContext('2d');
  g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, larg, alt);
  g.setTransform(s, 0, 0, s, -R[0] * s, -R[1] * s);
  ctx.copia(g, 1 / s);
  ctx.regiaoCopia = R; posicionarCopia(ctx, r.width);
}
function posicionarCopia(ctx, largCaixa) {
  if (ctx.copiaEl && ctx.regiaoCopia) ctx.copiaEl.style.transform = transformCopia(ctx, ctx.vb, largCaixa);
}
function transformCopia(ctx, [x, y, w], largCaixa) {
  const R = ctx.regiaoCopia, k = largCaixa / w;
  return `translate(${(R[0] - x) * k}px, ${(R[1] - y) * k}px) scale(${R[2] * k / ctx.copiaEl.width})`;
}
// peças da cópia, o mesmo desenho do SVG: zonas (preenchimento e contorno tracejado) e linhas por situação
function poligonoCopia(g, p) { g.moveTo(p[0], p[1]); for (let i = 2; i < p.length; i += 2) g.lineTo(p[i], p[i + 1]); g.closePath(); }
function zonasCopia(g, u, opacidade) {
  GERAL.zonas.forEach(z => { g.beginPath(); poligonoCopia(g, z.p); g.globalAlpha = opacidade(z); g.fillStyle = z.cor; g.fill(); });
  g.globalAlpha = 0.6; g.strokeStyle = '#F2F2F2'; g.lineWidth = 1.6 * u; g.setLineDash([7 * u, 5 * u]);
  g.beginPath(); GERAL.zonas.forEach(z => poligonoCopia(g, z.p)); g.stroke();
  g.globalAlpha = 1; g.setLineDash([]);
}
function linhasCopia(g, u, grupos) {          // grupos: [{ cor, tracejado: '5 4' | null, opacidade, trechos }]
  g.lineCap = g.lineJoin = 'round'; g.lineWidth = 2.4 * u;
  grupos.forEach(({ cor, tracejado, opacidade, trechos }) => {
    g.strokeStyle = cor; g.globalAlpha = opacidade || 1;
    g.setLineDash(tracejado ? tracejado.split(' ').map(v => v * u) : []);
    g.beginPath();
    trechos.forEach(t => t.p.forEach(p => { g.moveTo(p[0], p[1]); for (let i = 2; i < p.length; i += 2) g.lineTo(p[i], p[i + 1]); }));
    g.stroke();
  });
  g.globalAlpha = 1; g.setLineDash([]);
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
// focar zona, ver a obra inteira, ir até o trecho: 520 ms de animação e um desenho só, no fim. A animação roda no
// compositor (Web Animations), sem passar pela thread principal a cada quadro: quadros-chave tirados do mesmo caminho
// de antes (a vista vai de ini a fim com saída suave, 1 − (1 − k)³)
const IR_MS = 520, IR_PASSOS = 16;
function irPara(alvo, animar = true, ctx = ILU) {
  const r = ctx.caixa().getBoundingClientRect();
  const fim = encaixar(alvo, r.width / r.height), ini = ctx.vb.slice();
  const reduzir = matchMedia('(prefers-reduced-motion: reduce)').matches;
  pararAnimacao(ctx);
  if (!animar || reduzir) { ctx.vb = fim; return redesenhar(ctx); }
  clearTimeout(ctx.tGesto); ctx.gesto = true;
  const vista = k => { const e = 1 - Math.pow(1 - k, 3); return ini.map((v, i) => v + (fim[i] - v) * e); };
  const passos = Array.from({ length: IR_PASSOS + 1 }, (_, i) => vista(i / IR_PASSOS)), larg = r.width || 1, svg = ctx.svg();
  svg.style.willChange = 'transform'; svg.style.transformOrigin = '0 0';
  const anims = [svg.animate(passos.map(vb => ({ transform: transformVista(ctx, vb, larg) })), { duration: IR_MS, fill: 'forwards' })];
  if (ctx.copiaEl && ctx.regiaoCopia) anims.push(ctx.copiaEl.animate(passos.map(vb => ({ transform: transformCopia(ctx, vb, larg) })), { duration: IR_MS, fill: 'forwards' }));
  ctx.anim = { anims, vista };
  ctx.vb = fim;
  anims[0].onfinish = () => { if (ctx.anim && ctx.anim.anims === anims) { ctx.anim = null; anims.forEach(a => a.cancel()); redesenhar(ctx); } };
}
// outro gesto no meio da animação: ela para onde está e o mapa se desenha ali
function pararAnimacao(ctx) {
  const a = ctx.anim; if (!a) return;
  ctx.anim = null;
  ctx.vb = a.vista(Math.min(1, (a.anims[0].currentTime || 0) / IR_MS));
  a.anims.forEach(x => x.cancel());
  soltarVista(ctx);
}
function zoomEm(fator, cx, cy, ctx = ILU) {
  pararAnimacao(ctx);
  const [x, y, w, h] = ctx.vb, larg = ctx.base[2] - ctx.base[0];
  const nw = Math.max(larg / 60, Math.min(larg * 1.6, w * fator)); const k = nw / w;
  if (cx == null) { cx = x + w / 2; cy = y + h / 2; }
  ctx.vb = [cx - (cx - x) * k, cy - (cy - y) * k, w * k, h * k];
  gestoVista(ctx);
}
// o ponto do mapa sob o cursor, pela caixa (o SVG fica transformado durante o gesto)
function pontoDoMapa(ev, ctx = ILU) {
  const r = ctx.caixa().getBoundingClientRect(), [x, y, w, h] = ctx.vb;
  return [x + (ev.clientX - r.left) / r.width * w, y + (ev.clientY - r.top) / r.height * h];
}

/* ---- clique por cálculo: o trecho mais perto do ponto tocado, por uma grade de índice em unidades do mapa. Substitui
   1.436 caminhos invisíveis de 14 px no SVG (um por trecho, só para receber o clique), que pesavam em cada redesenho. */
const TOQUE_PX = 7;                       // metade dos 14 px do antigo caminho de clique
let GRADE = null;
function gradeTrechos(g) {
  if (GRADE && GRADE.g === g) return GRADE;
  const [x0, y0, x1, y1] = limites(g.trechos.flatMap(t => t.p)), lado = Math.max(x1 - x0, y1 - y0) / 64 || 1, cel = new Map();
  const celula = (x, y) => [Math.floor((x - x0) / lado), Math.floor((y - y0) / lado)];
  g.trechos.forEach((t, i) => t.p.forEach(p => {
    for (let j = 0; j + 3 < p.length; j += 2) {
      const [a, c] = celula(Math.min(p[j], p[j + 2]), Math.min(p[j + 1], p[j + 3])), [b, d] = celula(Math.max(p[j], p[j + 2]), Math.max(p[j + 1], p[j + 3]));
      for (let u = a; u <= b; u++) for (let v = c; v <= d; v++) { const k = u * 4096 + v; if (!cel.has(k)) cel.set(k, new Set()); cel.get(k).add(i); }
    }
  }));
  return (GRADE = { g, celula, cel });
}
function distSegmento(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, l = dx * dx + dy * dy, k = l ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l)) : 0;
  return Math.hypot(px - ax - k * dx, py - ay - k * dy);
}
// índice do trecho mais perto do ponto [x, y] do mapa, até TOQUE_PX pixels da tela; -1 se não há. Empate (linhas
// sobrepostas, a menos de meio pixel): o de cima no desenho, que é o de índice maior, como era com os caminhos de clique
function trechoPerto(ctx, [x, y]) {
  if (!GERAL || !ctx.vb) return -1;
  const unid = ctx.vb[2] / (ctx.caixa().getBoundingClientRect().width || 1), tol = TOQUE_PX * unid, G = gradeTrechos(GERAL);
  const [a, c] = G.celula(x - tol, y - tol), [b, d] = G.celula(x + tol, y + tol), vistos = new Set();
  let melhor = -1, menor = tol;
  for (let u = a; u <= b; u++) for (let v = c; v <= d; v++) (G.cel.get(u * 4096 + v) || []).forEach(i => {
    if (vistos.has(i)) return; vistos.add(i);
    const t = GERAL.trechos[i]; if (ctx.tocavel && !ctx.tocavel(t)) return;
    let dt = Infinity;
    t.p.forEach(p => { for (let j = 0; j + 3 < p.length; j += 2) dt = Math.min(dt, distSegmento(x, y, p[j], p[j + 1], p[j + 2], p[j + 3])); });
    if (dt > tol) return;
    if (melhor < 0 || dt < menor - unid / 2 || (dt <= menor + unid / 2 && i > melhor)) { menor = Math.min(menor, dt); melhor = i; }
  });
  return melhor;
}

// arrastar para mover, roda/pinça para aproximar; toque sem arrastar = clique (trecho, pino ou zona)
function ligarGestos(svg, ctx = ILU) {
  const dedos = new Map(); let inicio = null, arrastou = false, pinca = null;
  const comecar = (x, y) => { inicio = { x, y, vb: ctx.vb.slice(), alvo: inicio && inicio.alvo }; };
  svg.addEventListener('pointerdown', ev => {
    pararAnimacao(ctx);
    dedos.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (dedos.size === 1) { inicio = { x: ev.clientX, y: ev.clientY, vb: ctx.vb.slice(), alvo: ev.target }; arrastou = false; }
    if (dedos.size === 2) { const [a, b] = [...dedos.values()]; pinca = { d: Math.hypot(a.x - b.x, a.y - b.y), vb: ctx.vb.slice() }; arrastou = true; }
  });
  svg.addEventListener('pointermove', ev => {
    if (!dedos.has(ev.pointerId)) return;
    dedos.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (dedos.size === 2 && pinca) {
      const [a, b] = [...dedos.values()], d = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      ctx.vb = pinca.vb.slice(); zoomEm(pinca.d / d, ...pontoDoMapa({ clientX: (a.x + b.x) / 2, clientY: (a.y + b.y) / 2 }, ctx), ctx);
      return;
    }
    if (!inicio) return;
    const dx = ev.clientX - inicio.x, dy = ev.clientY - inicio.y;
    if (!arrastou && Math.hypot(dx, dy) < 5) return;
    if (!arrastou) { arrastou = true; svg.setPointerCapture(ev.pointerId); ctx.caixa().classList.add('arrastando'); }
    const k = inicio.vb[2] / ctx.caixa().getBoundingClientRect().width;
    ctx.vb = [inicio.vb[0] - dx * k, inicio.vb[1] - dy * k, inicio.vb[2], inicio.vb[3]];
    gestoVista(ctx);
  });
  const soltar = ev => {
    dedos.delete(ev.pointerId);
    if (dedos.size < 2) pinca = null;
    if (dedos.size) { const [a] = [...dedos.values()]; comecar(a.x, a.y); return; }   // da pinça para o arrastar sem pular
    ctx.caixa().classList.remove('arrastando');
    soltarVista(ctx);                                  // soltou: o desenho de verdade na hora
    if (inicio && !arrastou && ev.type === 'pointerup') {
      ctx.clique(inicio.alvo, ev, trechoPerto(ctx, pontoDoMapa({ clientX: inicio.x, clientY: inicio.y }, ctx)));
    }
    inicio = null;
  };
  // mão sobre o trecho (mouse parado em cima), um cálculo por quadro
  let sobre = 0;
  svg.addEventListener('pointermove', ev => {
    if (ev.pointerType !== 'mouse' || ev.buttons || sobre) return;
    sobre = requestAnimationFrame(() => { sobre = 0; ctx.caixa().classList.toggle('sobre-trecho', trechoPerto(ctx, pontoDoMapa(ev, ctx)) >= 0); });
  });
  svg.addEventListener('pointerup', soltar);
  svg.addEventListener('pointercancel', soltar);
  svg.addEventListener('wheel', ev => { ev.preventDefault(); pararAnimacao(ctx); zoomEm(Math.pow(1.0018, ev.deltaY), ...pontoDoMapa(ev, ctx), ctx); }, { passive: false });
}
// i: o trecho mais perto do toque (trechoPerto), ou -1; o pino fica por cima do trecho, como no desenho
function cliqueNoMapa(alvo, ev, i) {
  fecharPop();
  const pin = alvo.closest && alvo.closest('.ilu-pin'), zona = alvo.closest && alvo.closest('.ilu-zf');
  if (pin) return focarAlvo(pin.dataset.tipo, pin.dataset.alvo);
  // com uma zona em foco, o primeiro toque em outra zona (no polígono ou num trecho dela) troca o foco
  const outra = ILU.zona && (i >= 0 ? zonaDoTrecho(GERAL.trechos[i]) : zona && zona.dataset.zona);
  if (outra && outra !== ILU.zona) return focarZona(outra);
  if (i >= 0) return abrirFicha('TRECHO', GERAL.trechos[i].n);
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
  ILU.cores = (ILU.cores || 0) + 1;
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
    return `<g class="ilu-pin" data-tipo="${esc(p.alvo_tipo)}" data-alvo="${esc(p.alvo_id)}"><title>${esc(equipeNome(p.equipe))} em ${esc(nomeCompleto(p.alvo_id))} (check-in de hoje)</title>
      <circle cx="${x}" cy="${y}"/><text x="${x}" y="${y}">${esc(rotuloEquipe(p.equipe))}</text></g>`;
  }).join('');
}
const equipeNome = id => ((RESUMO && RESUMO.equipes) || []).find(e => e.id === id)?.nome || id;
function aplicarCamadas() {
  satDe(ILU).style.display = ILU.fundo === 'sem' ? 'none' : '';
  $('.sat-veu', satDe(ILU)).setAttribute('fill-opacity', FUNDOS[ILU.fundo][1]);
  $('#iluZonas').style.display = ILU.cam.zonas ? '' : 'none';
  // a zona em foco um pouco mais forte; as outras com a cor delas (nunca cinza) e clicáveis
  $$('#iluZonas .ilu-zf').forEach(p => p.setAttribute('fill-opacity', ILU.zona ? (p.dataset.zona === ILU.zona ? 0.36 : 0.22) : 0.26));
  $('#iluNomes').style.display = ILU.cam.nomes ? '' : 'none';
  $('#iluPins').style.display = ILU.cam.equipes ? '' : 'none';
  $$('#iluLinhas .ilu-tr').forEach(p => p.style.display = ILU.vis[p.dataset.situ] ? '' : 'none');
  try { localStorage.setItem('mc-ilu-camadas', JSON.stringify(ILU.cam)); localStorage.setItem('mc-ilu-fundo', ILU.fundo); } catch (_) { /* sem storage */ }
  agendarCopia(ILU);
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
      const txt = p ? `em ${esc(nomeCompleto(p.alvo_id))}, check-in de hoje` : pl.length ? `programada para ${esc(pl.slice(0, 3).map(nomeCompleto).join(', '))}${pl.length > 3 ? '…' : ''}; sem check-in` : 'sem check-in hoje';
      return `<button type="button" class="ilu-linha" ${p ? `data-ir-tipo="${esc(p.alvo_tipo)}" data-ir="${esc(p.alvo_id)}"` : pl.length ? `data-ir-tipo="TRECHO" data-ir="${esc(pl[0])}"` : 'disabled'}>
        <span class="num${p ? '' : ' sem'}">${esc(rotuloEquipe(e.id))}</span><span>${esc(e.nome)}<small>${txt}</small></span></button>`;
    }).join('') + '<p>O pino aparece onde a equipe fez o check-in hoje. Equipe sem check-in não tem pino.</p>';
  }
  if (nome === 'lista') listaIlu(pop);
  if (nome === 'camadas') {
    const ch = (k, rot) => `<button type="button" class="ilu-linha" data-camada="${k}" aria-pressed="${ILU.cam[k]}"><span>${ILU.cam[k] ? '☑' : '☐'}</span><span>${rot}</span></button>`;
    pop.innerHTML = '<h3>Fundo de satélite</h3><div class="ilu-fundos">' + Object.entries(FUNDOS).map(([k, [rot]]) =>
      `<button type="button" class="ilu-fundo" data-fundo="${k}" aria-pressed="${ILU.fundo === k}">${rot}</button>`).join('') + '</div>'
      + '<h3 style="margin-top:14px">Camadas</h3>' + ch('zonas', 'Zonas oficiais') + ch('nomes', 'Nomes das zonas') + ch('equipes', 'Equipes');
  }
}
// lista de trechos à parte: "Aguardando verificação" (supervisor, o mais perto primeiro quando o celular dá a posição) ou
// a que a tela Medição abriu. Tocar leva ao trecho e abre a ficha, onde está a ação
function abrirListaIlu(titulo, nomes) {
  ILU.lista = { titulo, itens: nomes.map(n => ({ nome: n })) };
  $('#iluBtLista').textContent = titulo; $('#iluBlocoLista').hidden = false;
  if (TELA !== 'iluminado') { ILU.abrirLista = true; return abrirAba('iluminado'); }
  if (GERAL && ILU.est) abrirPop('lista', true);
}
async function listaIlu(pop) {
  if (!ILU.lista || ILU.lista.verificacao) {
    const pedir = pos => api('/api/verificacao/pendentes' + (pos ? `?lat=${pos.lat}&lon=${pos.lon}` : ''));
    if (!ILU.lista) {
      pop.innerHTML = '<h3>Aguardando verificação</h3><p>Carregando…</p>';
      ILU.lista = { titulo: 'Aguardando verificação', verificacao: true, itens: await pedir(null).catch(() => []) };
      gps().then(pos => pos && pedir(pos)).then(r => { if (r && ILU.lista && ILU.lista.verificacao) { ILU.lista.itens = r; if (ILU.pop === 'lista') listaIlu($('#popLista')); } });
    }
  }
  const zonas = {};
  ILU.lista.itens.forEach(x => (zonas[x.zona || zonaDoTrecho(indexar(GERAL).trecho.get(x.nome) || {}) || '—'] ||= []).push(x));
  const sub = x => [x.intervalos ? `${x.intervalos} intervalo${x.intervalos > 1 ? 's' : ''}` : '', x.desde ? 'desde ' + dataBR(x.desde) : '',
    x.distancia_m != null ? (x.distancia_m < 1000 ? `${x.distancia_m} m daqui` : km(x.distancia_m) + ' daqui') : ''].filter(Boolean).join(' · ');
  pop.innerHTML = `<h3>${esc(ILU.lista.titulo)} (${ILU.lista.itens.length})</h3>`
    + (Object.entries(zonas).map(([z, xs]) => `<h4>${esc(nomeZona(z))}</h4>` + xs.map(x =>
      `<button type="button" class="ilu-linha" data-ir-tipo="TRECHO" data-ir="${esc(x.nome)}"><span>${esc(nomeCompleto(x.nome))}<small>${esc(sub(x))}</small></span></button>`).join('')).join('')
      || '<p>Nenhum trecho.</p>')
    + (ILU.lista.verificacao ? '<p>Trechos com execução informada e ainda não verificada. Toque para abrir a ficha e verificar (com as fotos que faltam).</p>' : '');
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
// o nome para quem escolhe ou confere: Zona03_PB06_Rede_TR014 → "Zona 03 · PB06 · TR014". A numeração TR recomeça a cada PB
// (o TR001 existe em dezenas delas): o TR sozinho não identifica o trecho (regras.nome_completo, no servidor)
const nomeCompleto = n => {
  const m = /^(?:Zona(\d+)|(ADUTORA))_(PB\d+)_(?:Rede_)?(.+)$/.exec(String(n || ''));
  return m ? `${m[1] ? 'Zona ' + m[1] : 'Adutora'} · ${m[3]} · ${m[4]}` : String(n || '');
};
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
  f.innerHTML = `<button type="button" class="ilu-bt quadrado fechar" aria-label="Fechar">×</button><h2>${esc(nomeCompleto(nome))}</h2><p class="vazio">Carregando…</p>`;
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
    <h2>${esc(nomeCompleto(d.nome || nome))}</h2>
    ${tipo === 'TRECHO' ? `<span class="situ"><i style="border-color:${s.cor}${s.tracejado ? ';border-top-style:dashed' : ''}"></i>${esc(ILU.est ? nomeSituacao(ILU.est, nome, s.id) : s.nome)}</span>` : ''}
    ${d.retirado ? '<div class="aviso problema">Retirado da revisão vigente do projeto: só consulta.</div>' : ''}
    <dl>${linhas.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
    <div class="acoes">${pode('campo') && !d.retirado ? `<button type="button" class="btn prim" data-ficha-campo>Lançar avanço</button>` : ''}
      <button type="button" class="btn" data-ficha-completa>Ver a ficha completa</button></div>
    ${tipo === 'TRECHO' && !d.retirado ? '<div class="caminho-box" id="iluCaminho"><p class="vazio">Carregando o caminho até a medição…</p></div>' : ''}
    <p class="vazio" style="font-size:13px">${esc(d.nome || nome)}</p>`;
  f.dataset.tipo = tipo; f.dataset.id = d.id;
  if (tipo === 'TRECHO' && !d.retirado) montarCaminho($('#iluCaminho'), d.nome || nome, () => { recarregarCamadaMapa(); abrirFicha(tipo, nome); });
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
