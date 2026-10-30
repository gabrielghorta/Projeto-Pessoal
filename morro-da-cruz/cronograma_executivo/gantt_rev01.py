"""Gantt resumido da REV01 em HTML, para imprimir em PDF A3: as equipes mês a mês, a saída do reservatório e as zonas
na ordem em que a água chega, com o teste, a interligação e o marco "ligada ao reservatório" de cada uma."""
import collections
import datetime as dt
from xml.sax.saxutils import escape

import analise_rev01 as AN
import gantt as G0
import paleta_rev01 as PAL
from motor import CAL, NOME, PRAZO, REAJUSTE
from gantt import MES, X0, LARG, x, segmentos

TINTA, APAGADO = '#111827', '#6B7280'


def _lum(h):
    h = h.lstrip('#')
    c = [int(h[k:k + 2], 16) / 255 for k in (0, 2, 4)]
    c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def texto_sobre(cor):
    """Branco ou tinta escura, o que tiver mais contraste com a barra."""
    L = _lum(cor)
    return '#FFFFFF' if (1.05 / (L + 0.05)) >= ((L + 0.05) / (_lum(TINTA) + 0.05)) else TINTA


def svg_gantt(pl, A):
    T, tr = pl['T'], pl['trechos']
    cores = dict(PAL.EQUIPES, ANK2H=PAL.EQUIPES['ANK2'])
    linhas = []                       # (rótulo, [(cor, ini, fim, texto)], marcos)
    linhas.append(('Canteiro', [(PAL.CANTEIRO, *pl['canteiro'], 'feito'), (PAL.CANTEIRO, *pl['canteiro_inst'], 'instalações')], []))
    # a saída do reservatório: quando fica pronto o trecho de cada saída
    saidas = []
    for n in pl['saidas']:
        i = pl['rede'].idx[n]
        saidas.append(('saida', tr[i]['fim'], f"{n.split('_')[-1]} DE {T[i]['de']}"))
    linhas.append(('Reservatório (Zona 11, PB23)', [], saidas))
    # equipes
    zc = lambda z: 'Sub' if z == 'SUB' else z.replace('Zona', 'Z')
    for eq in ['ANK1', 'E1A', 'E1B', 'E2C', 'E2D']:
        segs = []
        for i in pl['fila'][eq]:
            x_ = tr[i]
            if x_['fase'] == 'pé alto':
                d = T[i]['de']
                rot = 'Z11 ' + ('225' if d >= 200 else '160' if d == 160 else '90/110')
            elif x_['fase'] == 'Subadutora':
                rot = 'Subadutora'
            else:
                rot = zc(T[i]['loc'])
            segs.append((rot, x_['ini'], x_['fim']))
        linhas.append((NOME[eq], [(cores[eq], a, b, r) for r, a, b in segmentos(segs)], []))
    cx = pl['caixas']
    linhas.append(('Ankara 2 - caixas (obra civil)', [(cores['ANK2'], c['civ_ini'], c['civ_fim'], '') for c in cx.values()], []))
    linhas.append(('Ankara 2 - hidromecânico', [(cores['ANK2H'], c['hid_ini'], c['hid_fim'], '') for c in cx.values()], []))
    linhas.append(('§ZONAS NA ORDEM EM QUE A ÁGUA CHEGA - a rede na cor da equipe (uma faixa por equipe), o teste, a interligação e a ligação ao reservatório', [], []))
    sec_zonas = len(linhas) - 1
    fe = pl['fechamento']
    for n, z in enumerate(A['zonas']):
        zid = z['z']
        segs = collections.defaultdict(list)
        for i in pl['zinfo'][zid]['trechos']:
            segs[tr[i]['eq']].append((tr[i]['eq'], tr[i]['ini'], tr[i]['fim']))
        # uma faixa por equipe dentro da linha da zona, na ordem em que cada uma entra (nenhuma esconde a outra)
        eqs = sorted(segs, key=lambda eq: min(a for _, a, _ in segs[eq]))
        partes = [(cores[eq], a, b, ('faixa', k, len(eqs))) for k, eq in enumerate(eqs) for _, a, b in segmentos(segs[eq])]
        f = fe[zid]
        marcos = [('teste', f['teste'][0], f['teste'][1]), ('interlig', f['interlig'][1], f['interlig'][1]),
                  ('ligada', z['toda_ligada'], z['toda_ligada'])]
        rot = (f"Subadutora - sai do TR005 ({z['km']:.1f} km)" if zid == 'SUB'
               else f"{n}ª {AN.zona_txt(zid)} ({z['km']:.1f} km)").replace('.', ',')
        linhas.append((rot, partes, marcos))
    TOPO = 122
    H = [34 if k > sec_zonas else 26 for k in range(len(linhas))]       # as zonas mais altas: uma faixa por equipe
    Y = [TOPO + sum(H[:k]) for k in range(len(linhas))]
    total = sum(H)
    altura = TOPO + total + 84
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1580 {altura}" width="1580" height="{altura}" font-family="Arial, Helvetica, sans-serif">',
         '<rect width="100%" height="100%" fill="#fff"/>']
    d, n = G0.INI, 1
    while d < G0.FIM:
        prox = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        xa, xb = x(d), x(prox)
        o.append(f'<rect x="{xa:.1f}" y="{TOPO - 34}" width="{xb - xa:.1f}" height="{total + 34}" fill="{"#F3F4F6" if n % 2 else "#FFFFFF"}"/>')
        o.append(f'<text x="{(xa + xb) / 2:.1f}" y="{TOPO - 20}" font-size="10" text-anchor="middle" fill="#374151">{MES[d.month]}/{d:%y}</text>')
        o.append(f'<text x="{(xa + xb) / 2:.1f}" y="{TOPO - 7}" font-size="9" text-anchor="middle" fill="{APAGADO}">{n}ª{"*" if n > 18 else ""}</text>')
        d, n = prox, n + 1
    o.append(f'<text x="{X0 - 8}" y="{TOPO - 7}" font-size="9" text-anchor="end" fill="{APAGADO}">medição</text>')
    for k, (rot, partes, marcos) in enumerate(linhas):
        yy, H_LIN = Y[k], H[k]
        cy = yy + H_LIN / 2
        if rot.startswith('§'):
            o.append(f'<line x1="10" x2="{X0 + LARG}" y1="{yy + 2}" y2="{yy + 2}" stroke="#9CA3AF" stroke-width="1"/>')
            o.append(f'<text x="10" y="{cy + 6}" font-size="12" font-weight="bold" fill="{TINTA}">{escape(rot[1:])}</text>')
            continue
        o.append(f'<text x="{X0 - 8}" y="{cy + 4}" font-size="11" text-anchor="end" fill="{TINTA}">{escape(rot)}</text>')
        for cor, a, b, txt in partes:
            xa, xb = x(CAL.inicio(a)), x(CAL.fim(b))
            if isinstance(txt, tuple):
                _, kf, nf = txt
                hf = (H_LIN - 8) / nf
                o.append(f'<rect x="{xa:.1f}" y="{yy + 4 + kf * hf:.1f}" width="{max(1.2, xb - xa):.1f}" height="{hf:.1f}" fill="{cor}"/>')
                continue
            o.append(f'<rect x="{xa:.1f}" y="{yy + 5}" width="{max(1.2, xb - xa):.1f}" height="{H_LIN - 10}" rx="2" fill="{cor}"/>')
            if txt and xb - xa > 6.2 * len(txt) + 4:
                o.append(f'<text x="{(xa + xb) / 2:.1f}" y="{cy + 4}" font-size="10" text-anchor="middle" fill="{texto_sobre(cor)}" font-weight="bold">{escape(txt)}</text>')
        ult_x = None
        for tipo, a, b in marcos:
            if tipo == 'teste':
                xa, xb = x(CAL.inicio(a)), x(CAL.fim(b))
                o.append(f'<rect x="{xa:.1f}" y="{cy - 4}" width="{max(2, xb - xa):.1f}" height="8" fill="{TINTA}"/>')
            elif tipo == 'interlig':
                xc = x(CAL.fim(a))
                o.append(f'<path d="M{xc:.1f} {cy - 7} L{xc + 7:.1f} {cy} L{xc:.1f} {cy + 7} L{xc - 7:.1f} {cy} Z" fill="{TINTA}" stroke="#fff" stroke-width="1.5"/>')
                ult_x = max(ult_x or 0, xc)
            elif tipo == 'ligada':
                xc = x(CAL.fim(a))
                o.append(f'<circle cx="{xc:.1f}" cy="{cy}" r="6" fill="#fff" stroke="{TINTA}" stroke-width="2.2"/>')
                o.append(f'<circle cx="{xc:.1f}" cy="{cy}" r="2" fill="{TINTA}"/>')
            elif tipo == 'saida':
                xc = x(CAL.fim(a))
                o.append(f'<path d="M{xc - 6:.1f} {yy + 4} L{xc + 6:.1f} {yy + 4} L{xc:.1f} {yy + 14} Z" fill="{TINTA}"/>')
                o.append(f'<text x="{xc + 8:.1f}" y="{yy + 13 + (8 if b.startswith("TR006") or b.startswith("TR080") else 0)}" font-size="8.5" fill="{TINTA}">{escape(b)}</text>')
                ult_x = max(ult_x or 0, xc)
        if rot.startswith('Reservatório'):
            o.append(f'<text x="{(ult_x or X0) + 110:.1f}" y="{cy + 4}" font-size="10.5" font-weight="bold" fill="#B91C1C">'
                     f'operação do reservatório: a definir (licitação) · célula amarela nas PREMISSAS · sem carga provisória</text>')
    base = TOPO + total
    for d_, cor, txt in [(REAJUSTE, PAL.REAJUSTE, 'Reajuste (01/02/2027)'),
                         (PRAZO + dt.timedelta(days=1), PAL.TERMINO, 'Término contratual (23/03/2028)')]:
        xv = x(d_)
        o.append(f'<line x1="{xv:.1f}" x2="{xv:.1f}" y1="{TOPO - 34}" y2="{base}" stroke="{cor}" stroke-width="1.8" stroke-dasharray="5 4"/>')
        ancora, dx = ('end', -4) if xv > X0 + LARG * 0.8 else ('start', 4)
        o.append(f'<text x="{xv + dx:.1f}" y="{TOPO - 40}" font-size="10" fill="{cor}" font-weight="bold" text-anchor="{ancora}">{txt}</text>')
    xf = x(CAL.fim(pl['fim']))
    o.append(f'<line x1="{xf:.1f}" x2="{xf:.1f}" y1="{TOPO - 34}" y2="{base}" stroke="{TINTA}" stroke-width="1.6"/>')
    o.append(f'<text x="{xf - 4:.1f}" y="{base + 14}" font-size="10" text-anchor="end" fill="{TINTA}" font-weight="bold">Fim da obra: {CAL.fim(pl["fim"]):%d/%m/%Y}</text>')
    # legenda
    ly = base + 42
    lx = 20
    for cor, txt in [(PAL.EQUIPES[e], NOME[e]) for e in ['ANK1', 'E1A', 'E1B', 'E2C', 'E2D']] + [
            (PAL.EQUIPES['ANK2'], 'Ankara 2 - caixas e hidromecânico'), (PAL.CANTEIRO, 'Canteiro')]:
        o.append(f'<rect x="{lx}" y="{ly - 10}" width="14" height="12" rx="2" fill="{cor}"/><text x="{lx + 19}" y="{ly}" font-size="11" fill="{TINTA}">{escape(txt)}</text>')
        lx += 30 + 6.3 * len(txt)
    ly += 24
    o.append(f'<path d="M20 {ly - 10} L32 {ly - 10} L26 {ly} Z" fill="{TINTA}"/><text x="38" y="{ly}" font-size="11">saída do reservatório construída</text>')
    o.append(f'<circle cx="250" cy="{ly - 4}" r="6" fill="#fff" stroke="{TINTA}" stroke-width="2.2"/><circle cx="250" cy="{ly - 4}" r="2" fill="{TINTA}"/><text x="262" y="{ly}" font-size="11">zona toda ligada ao reservatório</text>')
    o.append(f'<rect x="470" y="{ly - 9}" width="14" height="8" fill="{TINTA}"/><text x="490" y="{ly}" font-size="11">teste hidrostático e desinfecção</text>')
    o.append(f'<path d="M703 {ly - 11} L710 {ly - 4} L703 {ly + 3} L696 {ly - 4} Z" fill="{TINTA}"/><text x="716" y="{ly}" font-size="11">interligação (a entrada em carga espera a operação do reservatório)</text>')
    o.append(f'<text x="1130" y="{ly}" font-size="11" fill="{APAGADO}">* medição depois do prazo contratual</text>')
    o.append(f'<text x="10" y="{TOPO - 52}" font-size="12" font-weight="bold" fill="{TINTA}">EQUIPES (o que cada uma faz, mês a mês) E A SAÍDA DO RESERVATÓRIO</text>')
    o.append('</svg>')
    return '\n'.join(o)


def html(pl, cen, A, resumo):
    svg = svg_gantt(pl, A)
    linhas = ''.join(f'<tr><td>{escape(a)}</td><td>{escape(b)}</td></tr>' for a, b in resumo)
    ordem = ', '.join(AN.zona_txt(z['z']).replace('Zona ', '') for z in A['zonas'] if z['z'] != 'SUB')
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Cronograma REV01 - {escape(cen['titulo'])}</title>
<style>@page {{ size: A3 landscape; margin: 9mm; }} body {{ font-family: Arial, Helvetica, sans-serif; color: {TINTA}; margin: 0; }}
h1 {{ font-size: 19px; margin: 0 0 2px; }} h2 {{ font-size: 14px; margin: 0 0 6px; color: #B91C1C; }}
.topo {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }}
table {{ border-collapse: collapse; font-size: 10.5px; }} td {{ padding: 1px 6px; border-bottom: 1px solid #E5E7EB; }}
svg {{ width: 100%; height: auto; display: block; }}
td:last-child {{ font-weight: bold; text-align: right; }} .nota {{ font-size: 11px; color: #4B5563; margin-top: 4px; }}</style></head><body>
<div class="topo"><div><h1>CT 10.239/2026 - Morro da Cruz - Cronograma físico executivo (REV01, 30/10/2026): a obra sai do reservatório (Zona 11)</h1>
<h2>{escape(cen['titulo'])}</h2>
<div class="nota">OS em 01/10/2026 · prazo de 540 dias · seg a sex, 7h às 17h, sem feriados nacionais e do DF · 06.1 REV01, 06.2 REV08 e BM REV04.<br>
A água sai do reservatório da Zona 11 por 4 saídas (TR005 e TR006, DE 500; TR080 e TR077, DE 225 - a corrigir no projeto com a Caesb).
A Subadutora sai do TR005 para fora e as zonas seguem a ordem em que a água chega: {escape(ordem)}.<br>
Em cima, o que cada equipe faz mês a mês (Z = zona). Embaixo, cada frente: a rede na cor da equipe, o teste, a interligação e quando a frente toda fica ligada ao reservatório.
Nenhuma rede entra em carga antes da operação do reservatório, que ainda não tem data. Detalhe trecho a trecho: Project e abas PROGRAMAÇÃO e CARGA.</div></div>
<table>{linhas}</table></div>
{svg}
</body></html>'''
