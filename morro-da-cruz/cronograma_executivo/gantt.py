"""Gantt resumido (por equipe e por zona) em HTML, para imprimir em PDF A3: abre em qualquer lugar, sem o Project."""
import collections
import datetime as dt
import sys
from xml.sax.saxutils import escape

import motor
from motor import CAL, NOME, OS, PRAZO, REAJUSTE

CORES = {'ANK1': '#2a78d6', 'E1A': '#eb6834', 'E1B': '#1baf7a', 'E2C': '#eda100', 'E2D': '#e87ba4',
         'ANK2': '#008300', 'ANK2H': '#6250d6'}
MES = ['', 'JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ']
INI, FIM = dt.date(2026, 10, 1), dt.date(2028, 5, 1)
X0, LARG = 250, 1300


def x(d):
    if isinstance(d, dt.datetime):
        d = d.date() + dt.timedelta(hours=d.hour, minutes=d.minute) if False else d
        frac = (d.hour * 60 + d.minute) / 1440
        d = d.date()
    else:
        frac = 0
    return X0 + ((d - INI).days + frac) / (FIM - INI).days * LARG


def segmentos(lista):
    """[(rótulo, ini_w, fim_w)] juntando os vizinhos com o mesmo rótulo."""
    out = []
    for rot, a, b in sorted(lista, key=lambda s: s[1]):
        if out and out[-1][0] == rot and a - out[-1][2] <= motor.DIA:
            out[-1] = (rot, out[-1][1], max(b, out[-1][2]))
        else:
            out.append((rot, a, b))
    return out


def svg_gantt(plano, cen):
    T = plano['T']
    tr = plano['trechos']
    y = 0
    o = []
    linhas = []                                  # (rótulo, [(cor, ini, fim, texto)], marcos)

    def zona_curta(z):
        return 'Sub' if z == 'SUB' else z.replace('Zona', 'Z')
    linhas.append(('Canteiro', [('#6B7280', *plano['canteiro'], 'feito'), ('#9CA3AF', *plano['canteiro_inst'], 'instalações')], []))
    # equipes
    for eq in ['ANK1', 'E1A', 'E1B', 'E2C', 'E2D']:
        segs = []
        for i in plano['fila'][eq]:
            x_ = tr[i]
            rot = '160 mm' if x_['fase'].startswith('160') else ('Subadutora' if x_['fase'] == 'Subadutora' else
                                                                   zona_curta(T[i]['loc']))
            segs.append((rot, x_['ini'], x_['fim']))
        linhas.append((NOME[eq], [(CORES[eq], a, b, r) for r, a, b in segmentos(segs)], []))
    cx = plano['caixas']
    civ = [(CORES['ANK2'], c['civ_ini'], c['civ_fim'], '') for c in cx.values()]
    hid = [(CORES['ANK2H'], c['hid_ini'], c['hid_fim'], '') for c in cx.values()]
    linhas.append(('Ankara 2 - caixas (obra civil)', civ, []))
    linhas.append(('Ankara 2 - hidromecânico', hid, []))
    linhas.append(('§ZONAS - a rede na cor da equipe que executa, o teste e a entrada em carga', [], []))
    sec_zonas = len(linhas) - 1
    fe = plano['fechamento']
    for z in plano['zonas'] + ['SUB']:
        segs = collections.defaultdict(list)
        for i, x_ in tr.items():
            t = T[i]
            if (z == 'SUB' and t['sub']) or (z != 'SUB' and t['loc'] == z and not t['sub']):
                segs[x_['eq']].append((x_['eq'], x_['ini'], x_['fim']))
        partes = []
        for eq, l in segs.items():
            for r, a, b in segmentos(l):
                partes.append((CORES[eq], a, b, ''))
        f = fe[z]
        marcos = [('teste', f['teste'][0], f['teste'][1]), ('carga', f['interlig'][1], f['interlig'][1])]
        rot = 'Subadutora' if z == 'SUB' else z.replace('Zona', 'Zona ')
        km = sum(T[i]['L'] for i in tr if (z == 'SUB' and T[i]['sub']) or (z != 'SUB' and T[i]['loc'] == z and not T[i]['sub'])) / 1000
        linhas.append((f'{rot} ({km:.1f} km)', partes, marcos))
    H_LIN, TOPO = 26, 118
    altura = TOPO + len(linhas) * H_LIN + 90
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1580 {altura}" width="1580" height="{altura}" font-family="Arial, Helvetica, sans-serif">')
    o.append('<rect width="100%" height="100%" fill="#fff"/>')
    # meses
    d = INI
    n = 1
    while d < FIM:
        prox = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        xa, xb = x(d), x(prox)
        fundo = '#F3F4F6' if n % 2 else '#FFFFFF'
        o.append(f'<rect x="{xa:.1f}" y="{TOPO - 34}" width="{xb - xa:.1f}" height="{len(linhas) * H_LIN + 34}" fill="{fundo}"/>')
        o.append(f'<text x="{(xa + xb) / 2:.1f}" y="{TOPO - 20}" font-size="10" text-anchor="middle" fill="#374151">{MES[d.month]}/{d:%y}</text>')
        rot_med = f'{n}ª' if n <= 18 else f'{n}ª*'
        o.append(f'<text x="{(xa + xb) / 2:.1f}" y="{TOPO - 7}" font-size="9" text-anchor="middle" fill="#6B7280">{rot_med}</text>')
        d, n = prox, n + 1
    o.append(f'<text x="{X0 - 8}" y="{TOPO - 7}" font-size="9" text-anchor="end" fill="#6B7280">medição</text>')
    # linhas
    for k, (rot, partes, marcos) in enumerate(linhas):
        yy = TOPO + k * H_LIN
        if rot.startswith('§'):
            o.append(f'<line x1="10" x2="{X0 + LARG}" y1="{yy + 2}" y2="{yy + 2}" stroke="#9CA3AF" stroke-width="1"/>')
            o.append(f'<text x="10" y="{yy + H_LIN / 2 + 6}" font-size="12" font-weight="bold" fill="#111827">{escape(rot[1:])}</text>')
            continue
        o.append(f'<text x="{X0 - 8}" y="{yy + H_LIN / 2 + 4}" font-size="11" text-anchor="end" fill="#111827">{escape(rot)}</text>')
        for cor, a, b, txt in partes:
            xa, xb = x(CAL.inicio(a)), x(CAL.fim(b))
            o.append(f'<rect x="{xa:.1f}" y="{yy + 5}" width="{max(1.2, xb - xa):.1f}" height="{H_LIN - 10}" rx="2" fill="{cor}"/>')
            if txt and xb - xa > 7 * len(txt) + 4:
                o.append(f'<text x="{(xa + xb) / 2:.1f}" y="{yy + H_LIN / 2 + 4}" font-size="10" text-anchor="middle" fill="#fff" font-weight="bold">{escape(txt)}</text>')
        for tipo, a, b in marcos:
            if tipo == 'teste':
                xa, xb = x(CAL.inicio(a)), x(CAL.fim(b))
                o.append(f'<rect x="{xa:.1f}" y="{yy + 9}" width="{max(2, xb - xa):.1f}" height="{H_LIN - 18}" fill="#111827"/>')
            else:
                xc = x(CAL.fim(a))
                cy = yy + H_LIN / 2
                o.append(f'<path d="M{xc:.1f} {cy - 7} L{xc + 7:.1f} {cy} L{xc:.1f} {cy + 7} L{xc - 7:.1f} {cy} Z" fill="#DC2626" stroke="#fff" stroke-width="1.5"/>')
    base = TOPO + len(linhas) * H_LIN
    # marcos verticais
    for d_, cor, txt in [(REAJUSTE, '#1971C2', 'Reajuste (01/02/2027)'), (PRAZO + dt.timedelta(days=1), '#DC2626', 'Término contratual (23/03/2028)')]:
        xv = x(d_)
        o.append(f'<line x1="{xv:.1f}" x2="{xv:.1f}" y1="{TOPO - 34}" y2="{base}" stroke="{cor}" stroke-width="1.6" stroke-dasharray="5 4"/>')
        ancora, dx = ('end', -4) if xv > X0 + LARG * 0.8 else ('start', 4)
        o.append(f'<text x="{xv + dx:.1f}" y="{TOPO - 40}" font-size="10" fill="{cor}" font-weight="bold" text-anchor="{ancora}">{txt}</text>')
    xf = x(CAL.fim(plano['fim']))
    o.append(f'<line x1="{xf:.1f}" x2="{xf:.1f}" y1="{TOPO - 34}" y2="{base}" stroke="#111827" stroke-width="1.6"/>')
    o.append(f'<text x="{xf - 4:.1f}" y="{base + 14}" font-size="10" text-anchor="end" fill="#111827" font-weight="bold">Fim da obra: {CAL.fim(plano["fim"]):%d/%m/%Y}</text>')
    # legenda
    ly = base + 40
    itens = [(CORES[e], NOME[e]) for e in ['ANK1', 'E1A', 'E1B', 'E2C', 'E2D']] + [
        (CORES['ANK2'], 'Ankara 2 - caixas'), (CORES['ANK2H'], 'Ankara 2 - hidromecânico')]
    lx = 20
    for cor, txt in itens:
        o.append(f'<rect x="{lx}" y="{ly - 10}" width="14" height="12" rx="2" fill="{cor}"/><text x="{lx + 19}" y="{ly}" font-size="11" fill="#111827">{escape(txt)}</text>')
        lx += 30 + 6.4 * len(txt)
    ly += 22
    o.append(f'<rect x="20" y="{ly - 9}" width="14" height="8" fill="#111827"/><text x="39" y="{ly}" font-size="11">teste hidrostático e desinfecção da zona</text>')
    o.append(f'<path d="M327 {ly - 11} L334 {ly - 4} L327 {ly + 3} L320 {ly - 4} Z" fill="#DC2626"/><text x="340" y="{ly}" font-size="11">interligação e entrada em carga</text>')
    o.append(f'<text x="560" y="{ly}" font-size="11" fill="#6B7280">* medição depois do prazo contratual</text>')
    o.append(f'<text x="10" y="{TOPO - 50}" font-size="12" font-weight="bold" fill="#111827">EQUIPES (o que cada uma faz, mês a mês)</text>')
    o.append(f'<text x="10" y="{TOPO + sec_zonas * H_LIN + 16}" font-size="1" fill="#fff">.</text>')
    o.append('</svg>')
    return '\n'.join(o), TOPO + sec_zonas * H_LIN


def html(plano, cen, resumo):
    svg, y_zonas = svg_gantt(plano, cen)
    linhas = ''.join(f'<tr><td>{escape(a)}</td><td>{escape(b)}</td></tr>' for a, b in resumo)
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Cronograma base - {escape(cen['titulo'])}</title>
<style>@page {{ size: A3 landscape; margin: 10mm; }} body {{ font-family: Arial, Helvetica, sans-serif; color: #111827; margin: 0; }}
h1 {{ font-size: 20px; margin: 0 0 2px; }} h2 {{ font-size: 15px; margin: 0 0 8px; color: #B91C1C; }}
.topo {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; }}
table {{ border-collapse: collapse; font-size: 12px; }} td {{ padding: 2px 8px; border-bottom: 1px solid #E5E7EB; }}
td:last-child {{ font-weight: bold; text-align: right; }} .nota {{ font-size: 11px; color: #4B5563; margin-top: 6px; }}
.zonas {{ font-size: 12px; font-weight: bold; margin: 0; }}</style></head><body>
<div class="topo"><div><h1>CT 10.239/2026 - Morro da Cruz - Cronograma físico executivo base (REV00, 29/10/2026)</h1>
<h2>{escape(cen['titulo'])}</h2>
<div class="nota">OS em 01/10/2026 · prazo de 540 dias · seg a sex, 7h às 17h, sem feriados nacionais e do DF · 06.1 REV01, 06.2 REV08 e BM REV04.<br>
Em cima, o que cada equipe faz mês a mês (Z = zona). Embaixo, cada zona: a rede na cor da equipe que executa, o teste e a entrada em carga.<br>
O detalhe trecho a trecho está no arquivo do Project e na aba PROGRAMAÇÃO da planilha.</div></div>
<table>{linhas}</table></div>
{svg}
</body></html>'''


if __name__ == '__main__':
    pass
