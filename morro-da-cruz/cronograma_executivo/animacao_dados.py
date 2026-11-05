"""Animação do Mapa iluminado pelo cronograma: monta o HTML independente (abre com dois cliques, sem internet).

    python3 animacao_dados.py SAIDA.html

Junta o traçado da visão geral do REV02, as datas de cada trecho e caixa nos dois cenários e o faturamento de cada mês
ao modelo `animacao_modelo.html` (que tem o marcador __DADOS__)."""
import base64
import datetime as dt
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(AQUI))          # mapa_geral.py, do web app
import mapa_geral as MG  # noqa: E402

import faturamento  # noqa: E402
import gerar_xlsx  # noqa: E402
import motor  # noqa: E402
from motor import CAL, OS, PRAZO, REAJUSTE  # noqa: E402

MAPA = motor.HTML
g = MG.geometria(MAPA)
D, rede, itens = motor.ler_dados()
p_prazo = motor.resolver_prazo(D, rede)
if p_prazo is None:
    sys.exit('Nem com 200 m/dia a obra termina no prazo contratual: revise as premissas em motor.py.')

dia = lambda d: round((d - dt.datetime.combine(OS, dt.time(0, 0))).total_seconds() / 86400, 3)
idx_geo = {t['n']: k for k, t in enumerate(g['trechos'])}
pos_el = {}
for e in g['els']:
    for n in e['n']:
        pos_el[n] = (e['x'], e['y'])

saida = {
    'w': g['w'], 'h': g['h'],
    'zonas': [{'id': z['id'], 'cor': z['cor'], 'p': z['p']} for z in g['zonas']],
    'nomes': [{'id': n['id'], 'x': n['x'], 'y': n['y']} for n in g['nomes']],
    'trechos': [{'n': t['n'], 'de': t['de'], 'z': t['z'], 'L': t['L'], 'p': t['p']} for t in g['trechos']],
    'marcos': {'reajuste': dia(dt.datetime.combine(REAJUSTE, dt.time(0))),
               'prazo': dia(dt.datetime.combine(PRAZO, dt.time(17))), 'fim_eixo': dia(dt.datetime(2028, 5, 1))},
    'equipes': [{'id': k, 'nome': motor.NOME[k]} for k in ['ANK1', 'E1A', 'E1B', 'E2C', 'E2D', 'ANK2']],
    'cenarios': {},
}
for cid, p in (('A', p_prazo), ('B', 90.0)):
    pl = motor.programar(D, rede, p)
    livro, origem = faturamento.distribuir(pl, itens, D)
    Q = gerar_xlsx.quantidades(itens, livro)
    vu = {it['chave']: it for it in itens}
    nm = len(livro.meses)
    val, sem = [0.0] * nm, [0.0] * nm
    for (eq, ch), qs in Q.items():
        it = vu[ch]
        fat = (1.1528 if it['classe'] == 'MATERIAL' else 1.2148) * (1 - 0.1404)
        for k, q in enumerate(qs):
            v = round(q * it['vu'], 2)
            val[k] += v * fat
            sem[k] += v
    pct_adm = 1304685.94 / (48534308.16 - 1304685.94)
    val = [round(v + s * pct_adm * 1.2148 * (1 - 0.1404), 2) for v, s in zip(val, sem)]
    T = pl['T']
    tr = []
    for i, x in pl['trechos'].items():
        k = idx_geo.get(T[i]['R'])
        if k is None:
            continue
        tr.append([k, dia(CAL.inicio(x['ini'])), dia(CAL.fim(x['fim'])), x['eq'], round(T[i]['lig'], 2)])
    caixas = []
    for j, c in pl['caixas'].items():
        e = pl['E'][j]
        xy = next((pos_el[n] for n in e['noms'] if n in pos_el), None)
        if not xy:
            continue
        caixas.append([round(xy[0], 1), round(xy[1], 1), e['tp'], dia(CAL.inicio(c['civ_ini'])), dia(CAL.fim(c['civ_fim'])),
                       dia(CAL.inicio(c['hid_ini'])), dia(CAL.fim(c['hid_fim'])), e['noms'][0]])
    carga = {('Adutora' if z == 'SUB' else z): dia(CAL.fim(f['interlig'][1])) for z, f in pl['fechamento'].items()}
    meses = [[n, dia(dt.datetime.combine(ini, dt.time(0))), dia(dt.datetime.combine(fim, dt.time(23, 59))),
              f'{gerar_xlsx.MES[ini.month]}/{ini:%y}'] for n, ini, fim in livro.meses]
    saida['cenarios'][cid] = {'p': p, 'fim': dia(CAL.fim(pl['fim'])), 'fim_txt': f"{CAL.fim(pl['fim']):%d/%m/%Y}",
                              'trechos': tr, 'caixas': caixas, 'carga': carga, 'meses': meses, 'fat': val,
                              'canteiro': [dia(CAL.inicio(pl['canteiro'][0])), dia(CAL.fim(pl['canteiro_inst'][1]))]}
    saida['marcos']['fim_eixo'] = max(saida['marcos']['fim_eixo'], dia(CAL.fim(pl['fim'])) + 30)   # obra além de mai/2028
    print(cid, p, len(tr), 'trechos', len(caixas), 'caixas', 'fim', CAL.fim(pl['fim']), 'fat', round(sum(val)))
mos = MG.mosaico(MAPA)
saida['mosaico'] = 'data:image/webp;base64,' + base64.b64encode(mos).decode()
modelo = open(os.path.join(AQUI, 'animacao_modelo.html'), encoding='utf-8').read()
assert modelo.count('__DADOS__') == 1
open(sys.argv[1], 'w', encoding='utf-8').write(modelo.replace('__DADOS__', json.dumps(saida, ensure_ascii=False, separators=(',', ':'))))
print('ok', sys.argv[1], round(os.path.getsize(sys.argv[1]) / 1e6, 2), 'MB')
