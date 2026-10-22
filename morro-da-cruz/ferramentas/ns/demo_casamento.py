#!/usr/bin/env python3
"""Demonstração: segmentos da NS -> trechos FÍSICOS -> intervalos por linha da 06.1.

Interface prevista (outra análise): topologia.trechos_fisicos(conn) -> [{id, membros:[{trecho_id, ordem, offset_m,
sentido}], extensao_m, no_ini, no_fim}]. Aqui um stub monta 2 trechos físicos com linhas REAIS da 06.1
(dump rede061.json de outra análise): F-A = TR020 (NÓ6.1 -> NÓ9.1) e F-B = TR007 + TR006 (NÓ9.1 -> NÓ113.1, que é
só cruzamento, -> CH_VRP-15), o exemplo do dono.

Uso: python3 -I demo_casamento.py <pasta ns006> <rede061.json>
"""
import json
import os
import sys

PASTA, REDE = sys.argv[1], sys.argv[2]
sys.path.insert(0, PASTA)
import ns_parser_prototipo as P  # noqa: E402

rede = {r['R']: r for r in json.load(open(REDE, encoding='utf-8'))}
TOL_ABS, TOL_REL, LIM_REL = 0.10, 0.005, 0.05     # m; 0,5% = aviso; 5% = casamento duvidoso (erro)


def fisico(fid, ids):
    """Stub de topologia.trechos_fisicos: cadeia ordenada de linhas da 06.1 com offset e sentido."""
    membros, off = [], 0.0
    for k, tid in enumerate(ids):
        r = rede[tid]
        if k + 1 < len(ids):
            prox = rede[ids[k + 1]]
            s = 1 if r['BQ'] in (prox['BP'], prox['BQ']) else -1
        else:
            ant = rede[ids[k - 1]]
            s = 1 if r['BP'] in (ant['BP'], ant['BQ']) else -1
        membros.append({'trecho_id': tid, 'ordem': k, 'offset_m': round(off, 3), 'sentido': s})
        off += float(r['M'])
    a, b = rede[ids[0]], rede[ids[-1]]
    return {'id': fid, 'membros': membros, 'extensao_m': round(off, 3),
            'no_ini': a['BP'] if membros[0]['sentido'] == 1 else a['BQ'], 'no_fim': b['BQ'] if membros[-1]['sentido'] == 1 else b['BP']}


def posicoes(F):
    """Nós ao longo do trecho físico (inclui os internos, ex. cruzamento) -> metros desde no_ini."""
    pos = {}
    for m in F['membros']:
        r = rede[m['trecho_id']]
        ini, fim = (r['BP'], r['BQ']) if m['sentido'] == 1 else (r['BQ'], r['BP'])
        pos.setdefault(ini, m['offset_m'])
        pos[fim] = round(m['offset_m'] + float(r['M']), 3)
    return pos


def casar(ns, fisicos):
    ctx = P.contexto_zona_pb(ns['cabecalho'].get('titulo'), ns['cabecalho'].get('localizacao'),
                             *[g['titulo'] for g in ns['grupos']])
    prefixo = f"{ctx['zona']}_{ctx['pb']}_" if ctx['zona'] and ctx['pb'] else None
    idx = []                                   # (F, nome completo do nó, chave, posição)
    for F in fisicos:
        for nome, p in posicoes(F).items():
            if prefixo is None or nome.startswith(prefixo):
                idx.append((F, nome, P.chave_elemento(nome), p))
    out = []
    for gi, g in enumerate(ns['grupos']):
        ls = g['linhas']
        for i in range(len(ls) - 1):
            a, b = ls[i], ls[i + 1]
            achados = []
            for F in fisicos:
                pa = [(n, p) for (FF, n, k, p) in idx if FF is F and k == a['chave']]
                pb = [(n, p) for (FF, n, k, p) in idx if FF is F and k == b['chave']]
                if pa and pb:
                    achados.append((F, pa[0], pb[0]))
            seg = {'grupo': gi, 'de_linha': i, 'elementos': (a['elemento'], b['elemento']), 'ns_m': b['dist_parcial'],
                   'estacas': (a['estaca_m'], b['estaca_m'])}
            if len(achados) != 1:
                cand_a = sorted({n for (_, n, k, _) in idx if k == a['chave']})
                cand_b = sorted({n for (_, n, k, _) in idx if k == b['chave']})
                seg.update(status='ERRO', motivo=f'{len(achados)} trechos físicos com as duas pontas '
                           f'(candidatos {a["chave"]}: {cand_a}; {b["chave"]}: {cand_b})')
                out.append(seg)
                continue
            F, (na, pa), (nb, pb_) = achados[0]
            proj = abs(pb_ - pa)
            dif = round(b['dist_parcial'] - proj, 3)
            rel = abs(dif) / proj if proj else 1
            nivel = 'OK' if abs(dif) <= TOL_ABS or rel <= TOL_REL else ('AVISO' if rel <= LIM_REL else 'ERRO')
            internos = [n for n, p in posicoes(F).items() if n in (na, nb) and n not in (F['no_ini'], F['no_fim'])]
            seg.update(status=nivel, fisico=F['id'], nos=(na, nb), posicao_no_fisico=(pa, pb_), sentido_estacas=1 if pb_ > pa else -1,
                       projeto_m=proj, diferenca_m=dif, diferenca_rel=round(rel, 5),
                       aviso_cruzamento=f'{internos} não é conexão (só cruzamento): a NS deveria ir de conexão a conexão' if internos else None)
            # atributos da linha b (valem para o segmento a->b) x 06.1
            attrs = []
            for m in F['membros']:
                r = rede[m['trecho_id']]
                if b['dn_mm'] and r.get('H') and int(r['H']) != b['dn_mm']:
                    attrs.append(f"{m['trecho_id']}: DN NS {b['dn_mm']} x 06.1 {r['H']}")
                if b['metodo'] and r.get('N') and r['N'] != b['metodo']:
                    attrs.append(f"{m['trecho_id']}: método NS {b['metodo']} x 06.1 {r['N']}")
            seg['divergencias_06_1'] = attrs
            out.append(seg)
    return ctx, out


def intervalo_ns_para_linhas(seg, F, u, v, etapa):
    """[u, v] em metros de ESTACA da NS (dentro do segmento) -> intervalos [x, y] de cada linha da 06.1."""
    sa, sb = seg['estacas']
    pa, pb_ = seg['posicao_no_fisico']
    k = abs(pb_ - pa) / (sb - sa)                       # fator NS -> projeto (medido x projetado)
    p1, p2 = sorted((pa + (pb_ - pa) / abs(pb_ - pa) * (w - sa) * k) for w in (u, v))
    res = []
    for m in F['membros']:
        r = rede[m['trecho_id']]
        ext = float(r['M'])
        a, b = max(p1, m['offset_m']), min(p2, m['offset_m'] + ext)
        if b - a <= 1e-3:
            continue
        x, y = a - m['offset_m'], b - m['offset_m']
        if m['sentido'] < 0:
            x, y = ext - y, ext - x
        if etapa in ('REATERRADO', 'ESCAVADO') and r.get('N') == 'MND':
            res.append({'trecho': m['trecho_id'], 'etapa': etapa, 'ignorado': 'MND sem vala'})
            continue
        res.append({'trecho': m['trecho_id'], 'etapa': etapa, 'ini_m': round(max(0.0, x), 3), 'fim_m': round(min(ext, y), 3)})
    return {'fator_ns_para_projeto': round(k, 6), 'no_fisico_m': (round(p1, 3), round(p2, 3)), 'linhas_06_1': res}


FIS = [fisico('F-A', ['Zona03_PB08_Rede_TR020']), fisico('F-B', ['Zona03_PB08_Rede_TR007', 'Zona03_PB08_Rede_TR006'])]
porid = {F['id']: F for F in FIS}
ns = P.ler_ns(os.path.join(PASTA, 'pdf_lo', 'R2_agua.pdf'), contrato_obra='CT 10239/2026', hoje='2026-10-20')
print('NS lida:', ns['resultado'], '| conferido:', ns['fonte'].get('conferido_com'))
print('trechos físicos (stub da interface):')
for F in FIS:
    print('  ', json.dumps(F, ensure_ascii=False))
ctx, segs = casar(ns, FIS)
print('contexto zona/PB tirado do título/grupo:', ctx)
for s in segs:
    print('segmento', s['elementos'][0][:20], '->', s['elementos'][1][:20], '|', s['status'], '|', s.get('fisico'), s.get('nos'),
          'NS', s['ns_m'], 'projeto', s.get('projeto_m'), 'dif', s.get('diferenca_m'), '|', s.get('divergencias_06_1') or '', s.get('motivo') or '')
demo = {'contexto': ctx, 'segmentos': segs, 'intervalos': []}
# (a) liberação topográfica de toda a NS: cada segmento inteiro
for s in segs:
    if s['status'] != 'ERRO':
        r = intervalo_ns_para_linhas(s, porid[s['fisico']], s['estacas'][0], s['estacas'][1], 'LIBERACAO_TOPOGRAFICA')
        demo['intervalos'].append({'caso': 'NS inteira', 'segmento': s['elementos'], **r})
        print('  LIBERACAO', s['fisico'], '->', r['linhas_06_1'])
# (b) assentamento da estaca 13+17,99 (NÓ9.1) até 20+0,00 = 400 m de estaca: atravessa o cruzamento NÓ113.1
s = segs[1]
r = intervalo_ns_para_linhas(s, porid[s['fisico']], 277.99, 400.0, 'ASSENTADO')
demo['intervalos'].append({'caso': 'ASSENTADO estaca 13+17,99 a 20+0,00', **r})
print('  ASSENTADO 277,99-400 (estaca) ->', r)
# (c) NS que lista o cruzamento NÓ113.1 como linha (2 segmentos dentro do mesmo trecho físico)
ns_c = json.loads(json.dumps(ns))
g = ns_c['grupos'][0]
novo = dict(g['linhas'][1], elemento='NÓ113.1 (CRUZAMENTO)', chave='NO113.1', estaca_m=280.5, dist_parcial=2.51, dist_acumulada=280.5)
g['linhas'][2] = dict(g['linhas'][2], dist_parcial=293.47)
g['linhas'].insert(2, novo)
_, segs_c = casar(ns_c, FIS)
for s in segs_c:
    print('  [com NÓ113.1]', s['elementos'][0][:12], '->', s['elementos'][1][:22], s['status'], s.get('posicao_no_fisico'), s.get('aviso_cruzamento') or '')
demo['caso_cruzamento_listado'] = segs_c
# (d) mesmo par de pontas em 2 zonas/PBs (real na 06.1: TR001 da Zona01/PB01 e TR034 da Zona07/PB18)
FIS_D = [fisico('F-Z1', ['Zona01_PB01_Rede_TR001']), fisico('F-Z7', ['Zona07_PB18_Rede_TR034'])]
r1 = rede['Zona01_PB01_Rede_TR001']
L1 = float(r1['M'])
base_l = dict(ns['grupos'][0]['linhas'][0])
def ns_min(titulo):
    l0 = dict(base_l, elemento=r1['BP'].split('_')[-1], chave=P.chave_elemento(r1['BP']), estaca_m=0.0, dist_parcial=0.0, dist_acumulada=0.0)
    l1 = dict(base_l, elemento=r1['BQ'].split('_')[-1], chave=P.chave_elemento(r1['BQ']), estaca_m=L1, dist_parcial=L1, dist_acumulada=L1)
    return {'cabecalho': {'titulo': titulo, 'localizacao': 'MORRO DA CRUZ'}, 'grupos': [{'titulo': 'REDE PEAD', 'linhas': [l0, l1]}]}
for titulo in ('"REDE DE ÁGUA" - VER CROQUI ANEXO', '"REDE DE ÁGUA" - ZONA 01 - PB01 - VER CROQUI ANEXO'):
    ctx_d, segs_d = casar(ns_min(titulo), FIS_D)
    print('  [par repetido]', titulo[:45], '| contexto', ctx_d, '->', [(s['status'], s.get('fisico'), s.get('motivo')) for s in segs_d])
    demo.setdefault('caso_par_repetido', []).append({'titulo': titulo, 'contexto': ctx_d, 'segmentos': segs_d})
with open(os.path.join(PASTA, 'demo_casamento.json'), 'w', encoding='utf-8') as f:
    json.dump(demo, f, ensure_ascii=False, indent=1, default=list)
