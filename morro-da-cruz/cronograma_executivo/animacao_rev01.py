"""Animação da REV01 (só o cenário B): o Mapa iluminado dia a dia a partir do reservatório da Zona 11, com a situação de
cada trecho na ligação ao reservatório. Monta o HTML independente (abre com dois cliques, sem internet).

    python3 animacao_rev01.py SAIDA.html

Junta o traçado da visão geral do REV02, as datas de cada trecho (início, término, ligado ao reservatório e pronto para
carga) e de cada caixa, o faturamento de cada mês e as cores da REV01 ao modelo `animacao_rev01_modelo.html`."""
import base64
import datetime as dt
import json
import math
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(AQUI))          # mapa_geral.py, do web app
import mapa_geral as MG  # noqa: E402

import analise_rev01 as AN  # noqa: E402
import motor  # noqa: E402
import motor_rev01 as M1  # noqa: E402
import paleta_rev01 as PAL  # noqa: E402
from motor import CAL, OS, PRAZO, REAJUSTE  # noqa: E402

MAPA = motor.HTML
g = MG.geometria(MAPA)
D, rede, itens = motor.ler_dados()
pl = M1.programar(D, rede)
livro, origem, val = AN.faturamento_mensal(pl, itens, D)
A = AN.analisar(pl, livro)
T, E = pl['T'], pl['E']

dia = lambda d: round((d - dt.datetime.combine(OS, dt.time(0, 0))).total_seconds() / 86400, 3)
idx_geo = {t['n']: k for k, t in enumerate(g['trechos'])}
pos_el = {n: (e['x'], e['y']) for e in g['els'] for n in e['n']}


def ponta_de_saida(nome, lado):
    """A ponta do trecho que sai do reservatório: a que fica longe do nó da outra ponta."""
    t = g['trechos'][idx_geo[nome]]
    a, b = (t['p'][0][0], t['p'][0][1]), (t['p'][-1][-2], t['p'][-1][-1])
    outro = pos_el.get(t['b'] if lado == 'ini' else t['a'])
    if not outro:
        return None
    return max((a, b), key=lambda q: math.dist(q, outro))


saidas = []
for nome, lado in [M1.SAIDA_DE500, M1.TR006] + M1.SAIDAS_ZONA11:
    q = ponta_de_saida(nome, lado)
    if q is None:                                 # TR006: solto nas duas pontas, a ponta mais perto do TR005
        t = g['trechos'][idx_geo[nome]]
        ref = saidas[0]['xy']
        q = min(((t['p'][0][0], t['p'][0][1]), (t['p'][-1][-2], t['p'][-1][-1])), key=lambda p: math.dist(p, ref))
    saidas.append({'n': nome.split('_')[-1], 'de': T[pl['rede'].idx[nome]]['de'], 'xy': [round(q[0], 1), round(q[1], 1)]})
principais = [s['xy'] for s in saidas if s['n'] != 'TR006']
centro = [round(sum(p[0] for p in principais) / len(principais), 1), round(sum(p[1] for p in principais) / len(principais), 1)]

ordem = {z['z']: n for n, z in enumerate(A['zonas'])}
saida = {
    'w': g['w'], 'h': g['h'],
    'zonas': [{'id': z['id'], 'p': z['p']} for z in g['zonas']],
    'nomes': [{'id': n['id'], 'x': n['x'], 'y': n['y'], 'ordem': ordem.get(n['id'])} for n in g['nomes']],
    'trechos': [{'n': t['n'], 'de': t['de'], 'z': t['z'], 'L': t['L'], 'p': t['p']} for t in g['trechos']],
    'marcos': {'reajuste': dia(dt.datetime.combine(REAJUSTE, dt.time(0))),
               'prazo': dia(dt.datetime.combine(PRAZO, dt.time(17))), 'fim_eixo': dia(dt.datetime(2028, 5, 1))},
    'equipes': [{'id': k, 'nome': motor.NOME[k], 'cor': PAL.EQUIPES[k]} for k in ['ANK1', 'E1A', 'E1B', 'E2C', 'E2D', 'ANK2']],
    'situacoes': [{'id': k, 'nome': PAL.NOME_SITUACAO[k], 'cor': PAL.SITUACOES[k]} for k in PAL.SITUACOES],
    'linhas': {'reajuste': PAL.REAJUSTE, 'termino': PAL.TERMINO, 'cursor': PAL.CURSOR},
    'caixa': {'pronta': PAL.CAIXA_PRONTA, 'montada': PAL.CAIXA_MONTADA},
    'reservatorio': {'xy': centro, 'saidas': saidas},
}
tr = []
for i, x in pl['trechos'].items():
    k = idx_geo.get(T[i]['R'])
    if k is None:
        continue
    tr.append([k, dia(CAL.inicio(x['ini'])), dia(CAL.fim(x['fim'])), x['eq'], round(T[i]['lig'], 2),
               dia(CAL.fim(pl['ligado'][i])), dia(CAL.fim(A['det'][i]['pronto']))])
caixas = []
for j, c in pl['caixas'].items():
    e = E[j]
    xy = next((pos_el[n] for n in e['noms'] if n in pos_el), None)
    if not xy:
        continue
    caixas.append([round(xy[0], 1), round(xy[1], 1), e['tp'], dia(CAL.inicio(c['civ_ini'])), dia(CAL.fim(c['civ_fim'])),
                   dia(CAL.inicio(c['hid_ini'])), dia(CAL.fim(c['hid_fim'])), e['noms'][0], int(j in pl['caixas_caminho'])])
meses = [[n, dia(dt.datetime.combine(ini, dt.time(0))), dia(dt.datetime.combine(fim, dt.time(23, 59))),
          f'{AN.MES[ini.month].lower()}/{ini:%y}'] for n, ini, fim in livro.meses]
saida['cen'] = {'p': 90.0, 'fim': dia(CAL.fim(pl['fim'])), 'fim_txt': f"{CAL.fim(pl['fim']):%d/%m/%Y}",
                'trechos': tr, 'caixas': caixas, 'meses': meses, 'fat': [round(v, 2) for v in val],
                'canteiro': [dia(CAL.inicio(pl['canteiro'][0])), dia(CAL.fim(pl['canteiro_inst'][1]))]}
saida['mosaico'] = 'data:image/webp;base64,' + base64.b64encode(MG.mosaico(MAPA)).decode()
modelo = open(os.path.join(AQUI, 'animacao_rev01_modelo.html'), encoding='utf-8').read()
assert modelo.count('__DADOS__') == 1
open(sys.argv[1], 'w', encoding='utf-8').write(modelo.replace('__DADOS__', json.dumps(saida, ensure_ascii=False, separators=(',', ':'))))
print('ok', sys.argv[1], len(tr), 'trechos', len(caixas), 'caixas', 'fim', saida['cen']['fim_txt'],
      round(os.path.getsize(sys.argv[1]) / 1e6, 2), 'MB')
