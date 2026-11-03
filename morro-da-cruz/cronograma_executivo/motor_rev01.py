"""Motor da REV01 do cronograma (30/10/2026): a obra sai do reservatório, na Zona 11, e sobe com a rede.

Mantém todas as regras da REV00 (motor.py: calendário, equipes e datas de entrada, pé alto a 60 m/dia até o reajuste,
90 m/dia depois, ligações 5 dias atrás, tempos das caixas, topografia, cadastro, teste, interligação, desmobilização,
canteiro). Muda só a ORDEM, pela regra nova "ligado ao reservatório":

* Subadutora: da saída do reservatório para fora (TR005 primeiro), zona por zona, na ordem em que a água chega ao
  ponto de alimentação de cada uma; dentro de cada parte, de montante para jusante (caminho em profundidade).
* Zonas: cada equipe livre pega o bloco (zona × PB, cortado nos pedaços ligados entre si) cujo caminho até o
  reservatório já está pronto ou fica pronto primeiro; entre os já ligados, o da zona onde ela está, depois o da zona
  que vem antes na ordem da água e, na zona, secundária antes de terciária; dentro do bloco, da alimentação para as
  pontas.
* Caixas: as do caminho da água primeiro (as da Subadutora e as de entrada de cada zona), depois as demais.

Decisões do responsável em 30/10/2026 (os padrões de OPCOES): o reservatório tem 4 saídas (o projeto será corrigido
com a Caesb): o TR005 e o TR006 (DE 500) e os DE 225 TR080 e TR077 da Zona 11; o pé alto faz primeiro o DE 160 da
Zona 11, depois o DE 225 dela e por fim o DE 90/110; teste e interligação por zona, como na REV00; hidromecânico a
partir de jul/2027, sem antecipar peças do caminho.
"""
import collections
import datetime as dt
import heapq

import motor
import rede_agua as RA
from motor import (CAL, DIA, CAIXA_DIAS, CADASTRO_DEPOIS, CANT_FEITO, CANT_INST, DESMOB_DIAS, EQUIPES, HIDRO_DIAS,
                   INICIO_HIDRO, INTERLIG_DIAS, LIG_ATRASO, P_PE_ALTO, REAJUSTE, TESTE_DIAS)

INF = RA.INF
SAIDA_DE500 = ('Zona11_PB23_Adutora_TR005', 'ini')
SAIDAS_ZONA11 = [('Zona11_PB23_Rede_TR080', 'fim'), ('Zona11_PB23_Rede_TR077', 'ini')]   # DE 225 soltos junto do reservatório
TR006 = ('Zona11_PB23_Adutora_TR006', 'ini')                                            # DE 500, 2,4 m, solto nas duas pontas
CLASSE = {'PRIMÁRIA': 0, 'SECUNDÁRIA': 1, 'TERCIÁRIA': 2}
OPCOES = {
    'saidas_zona11': True,          # a Zona 11 sai direto do reservatório pelos dois DE 225 (TR080 e TR077)
    'pe_alto_extra': 'zona11_de225',  # o que o pé alto faz além do DE 160 da Zona 11: 'zona11_de225' ou [nomes da 06.1]
    'pe_alto_extra_depois': True,   # True: o pé alto faz primeiro o DE 160 e só depois esses trechos extras
    'pe_alto_resto': 'zona11_menor',  # acabou o DE 160 da Zona 11: 'zona11_menor' (DE 90 e 110 dela) | 'de160_outras'
    'hidro_caminho_antes': False,   # montar as caixas do caminho logo depois da obra civil (peças compradas antes)
    'teste_por_setor': False,       # só na análise (carga(pl, por_setor=True)): teste e interligação por setor
    # REV02 (30/10/2026); os padrões deixam a REV01 como era
    'prod_por_de': (),              # ((DE mínimo, m/dia), ...), do maior DE para o menor: teto da produtividade pelo diâmetro
    'entrada_meia_dias': 0,         # dias úteis iniciais de cada equipe de empreiteiro a meia produtividade
    'troca_frente_dias': 0.0,       # dias úteis que a equipe perde ao mudar de frente (deslocamento e mobilização)
    'ligacoes_por_dia': None,       # ligações prediais por dia feitas pela própria equipe, logo depois do trecho; None:
                                    # as ligações não tomam tempo da rede (REV00 e REV01)
    'interlig_por_caminho': False,  # a interligação de cada frente espera só as caixas do caminho da água até ela (e a
                                    # Subadutora, só as caixas dela), e não todas as caixas que encostam na frente
}


def frente_de(t):
    return 'SUB' if t['sub'] else t['loc']


def programar(D, rede, p=90.0, opcoes=None):
    o = dict(OPCOES, **(opcoes or {}))
    T, E, _, caixas = motor.base(D, rede)
    saidas = [SAIDA_DE500, TR006] + (SAIDAS_ZONA11 if o['saidas_zona11'] else [])
    R = RA.Rede(D, saidas)
    ent, dist, pai = R.arvore()
    agua = lambda i: ent.get(i, (INF,))[0]                          # metros de tubo do reservatório até o trecho
    ent_w = {e[0]: CAL.w(e[3]) for e in EQUIPES}
    w_reaj = CAL.w(REAJUSTE)
    plano = {'p': p, 'opcoes': o, 'trechos': {}, 'blocos': [], 'fila': collections.defaultdict(list), 'rede': R,
             'agua': {i: agua(i) for i in range(len(T))}}
    dur = lambda L, prod: max(30, round(L / prod * DIA))
    meia = {k: ent_w[k] + o['entrada_meia_dias'] * DIA for k in ('E1A', 'E1B', 'E2C', 'E2D')}

    def produtividade(eq, i, w0, prod):
        for de_min, teto in o['prod_por_de']:
            if T[i]['de'] >= de_min:
                prod = min(prod, teto)
                break
        return prod / 2 if w0 < meia.get(eq, -1) else prod

    def fazer(eq, i, w0, prod, fase):
        """Assenta o trecho; devolve quando a equipe fica livre (com 'ligacoes_por_dia', depois das ligações dele)."""
        w1 = w0 + dur(T[i]['L'], produtividade(eq, i, w0, prod))
        plano['trechos'][i] = {'eq': eq, 'ini': w0, 'fim': w1, 'fase': fase}
        plano['fila'][eq].append(i)
        if o['ligacoes_por_dia'] and T[i]['lig'] > 0 and fase == 'Rede da zona':
            plano['trechos'][i]['lig_fim'] = w1 + round(T[i]['lig'] / o['ligacoes_por_dia'] * DIA)
            return plano['trechos'][i]['lig_fim']
        return w1

    # ---- zonas: a ordem em que a água chega ao começo de cada uma
    zonas_trs = collections.defaultdict(list)
    for i, t in enumerate(T):
        if not t['sub']:
            zonas_trs[t['loc']].append(i)
    entrada_zona = {z: min(agua(i) for i in trs) for z, trs in zonas_trs.items()}
    zonas = sorted(zonas_trs, key=lambda z: (entrada_zona[z], z))
    plano['zonas'], plano['entrada_zona'] = zonas, entrada_zona

    # ---- caminho da água de cada zona (trechos da Subadutora até cada trecho dela)
    precisa = {}
    for z in zonas:
        s = set()
        for i in zonas_trs[z]:
            if i in ent:
                s.update(k for k in RA.Rede.caminho(i, ent, pai) if T[k]['sub'])
        s.update(i for i, t in enumerate(T) if t['sub'] and t['zona'] == z and i in ent)
        for i in list(s):
            s.update(k for k in RA.Rede.caminho(i, ent, pai) if T[k]['sub'])
        precisa[z] = s

    # ---- ordem da Subadutora: TR005; depois, zona por zona, o caminho e as redes principais dela, em profundidade
    filhos = collections.defaultdict(list)
    for i in range(len(T)):
        if T[i]['sub'] and i in ent:
            cam = RA.Rede.caminho(i, ent, pai)
            subs = [k for k in cam[:-1] if T[k]['sub']]
            filhos[subs[-1] if subs else None].append(i)
    for k in filhos:
        filhos[k].sort(key=agua)

    def profundidade(raiz_set):
        out, pilha = [], sorted((i for i in filhos[None]), key=agua, reverse=True)
        vistos = set()
        while pilha:
            i = pilha.pop()
            if i in vistos:
                continue
            vistos.add(i)
            if i in raiz_set:
                out.append(i)
            pilha.extend(sorted(filhos[i], key=agua, reverse=True))
        return out
    ordem_sub, feitos = [], set()
    tr005 = R.idx[SAIDA_DE500[0]]
    ordem_sub.append(tr005)
    feitos.add(tr005)
    for z in zonas:
        for i in profundidade(precisa[z]):
            if i not in feitos:
                ordem_sub.append(i)
                feitos.add(i)
    resto = [i for i in range(len(T)) if T[i]['sub'] and i not in feitos]
    ordem_sub += sorted(resto, key=lambda i: (agua(i), T[i]['R']))
    plano['ordem_sub'] = ordem_sub

    # ---- 1) pé alto: a Equipe Adutora a 60 m/dia, do ponto mais perto da saída, até o reajuste
    extra = ({i for i, t in enumerate(T) if t['loc'] == 'Zona11' and t['de'] == 225} if o['pe_alto_extra'] == 'zona11_de225'
             else {R.idx[n] for n in o['pe_alto_extra']})
    z11_160 = [i for i in zonas_trs['Zona11'] if T[i]['de'] == 160]
    if o['pe_alto_extra_depois']:
        cands = (sorted(z11_160, key=lambda i: (agua(i), T[i]['R'])) +
                 sorted((i for i in extra if i not in z11_160), key=lambda i: (agua(i), T[i]['R'])))
    else:
        cands = sorted(z11_160 + [i for i in extra if i not in z11_160], key=lambda i: (agua(i), T[i]['R']))
    if o['pe_alto_resto'] == 'zona11_menor':
        cands += sorted((i for i in zonas_trs['Zona11'] if T[i]['de'] in (90, 110)), key=lambda i: (agua(i), T[i]['R']))
    else:
        cands += [i for z in zonas if z != 'Zona11'
                  for i in sorted((i for i in zonas_trs[z] if T[i]['de'] == 160), key=lambda i: (agua(i), T[i]['R']))]
    w = ent_w['ANK1']
    pe_alto = []
    for i in cands:
        if w >= w_reaj:
            break
        if i in plano['trechos']:
            continue
        w = fazer('ANK1', i, w, P_PE_ALTO, 'pé alto')
        pe_alto.append(i)
    plano['pe_alto'] = pe_alto
    # ---- 2) depois do reajuste, a Subadutora (o que o pé alto já fez fica fora)
    w = max(w, w_reaj)
    for i in ordem_sub:
        if i not in plano['trechos']:
            w = fazer('ANK1', i, w, p, 'Subadutora')
    plano['fim_subadutora'] = w

    # ---- 3) blocos das zonas: zona × PB, cortado nos pedaços ligados entre si
    feitos = set(plano['trechos'])
    blocos = []
    for z in zonas:
        por_pb = collections.defaultdict(list)
        for i in zonas_trs[z]:
            if i not in feitos:
                por_pb[(T[i]['pb'], T[i]['cl'] == 'TERCIÁRIA')].append(i)
        for (pb, terc), lst in por_pb.items():
            resto_b = set(lst)
            while resto_b:
                semente = min(resto_b, key=lambda i: (agua(i), i))
                pedaco, pilha = set(), [semente]
                while pilha:
                    i = pilha.pop()
                    if i in pedaco:
                        continue
                    pedaco.add(i)
                    for v in R.TV[i]:
                        pilha.extend(k for k in R.VT[v] if k in resto_b and k not in pedaco)
                resto_b -= pedaco
                blocos.append({'zona': z, 'pb': pb, 'classe': 'terciária' if terc else 'secundária', 'membros': pedaco,
                               'agua': min(agua(i) for i in pedaco)})
    PEQUENO_M = 150.0
    mudou = True
    while mudou:
        mudou = False
        for b in sorted(blocos, key=lambda b: sum(T[i]['L'] for i in b['membros'])):
            if sum(T[i]['L'] for i in b['membros']) >= PEQUENO_M:
                continue
            vs = {v for i in b['membros'] for v in R.TV[i]}
            viz = [c for c in blocos if c is not b and c['zona'] == b['zona'] and c['classe'] == b['classe']
                   and any(v in vs for i in c['membros'] for v in R.TV[i])]
            if viz:
                c = min(viz, key=lambda c: c['agua'])
                c['membros'] |= b['membros']
                c['agua'] = min(c['agua'], b['agua'])
                if b['pb'] not in c['pb'].split('+'):
                    c['pb'] = '+'.join(sorted(set(c['pb'].split('+')) | {b['pb']}))
                blocos.remove(b)
                mudou = True
                break
    ordem_z = {z: k for k, z in enumerate(zonas)}
    fim = {i: x['fim'] for i, x in plano['trechos'].items()}

    def vertices_ligados():
        _, melhor = R.ligado_em(fim, vertices=True)
        return melhor

    def ordem_no_bloco(b, melhor):
        """Da alimentação para as pontas: a fronteira a partir dos vértices já ligados; secundária antes de
        terciária; empate pela distância da água."""
        membros = b['membros']
        ligado = {v for i in membros for v in R.TV[i] if melhor.get(v, INF) < INF}
        if not ligado:
            ligado = {min((v for i in membros for v in R.TV[i]), key=lambda v: dist.get(v, INF))}
        fila, saida, vistos = [], [], set()

        def empurra(v):
            for i in R.VT[v]:
                if i in membros and i not in vistos:
                    vistos.add(i)
                    heapq.heappush(fila, (CLASSE.get(T[i]['cl'], 3), agua(i), i))
        for v in ligado:
            empurra(v)
        while fila:
            _, _, i = heapq.heappop(fila)
            saida.append(i)
            for v in R.TV[i]:
                empurra(v)
        sobra = sorted(membros - set(saida), key=lambda i: (agua(i), i))
        return saida + sobra

    livre = {k: ent_w[k] for k in ('E1A', 'E1B', 'E2C', 'E2D')}
    livre['ANK1'] = plano['fim_subadutora']
    rede_eqs = ['E1A', 'E1B', 'E2C', 'E2D', 'ANK1']
    ultima = {'ANK1': 'SUB'} if o['troca_frente_dias'] else {}
    pendentes = list(blocos)
    while pendentes:
        eq = min(rede_eqs, key=lambda k: (livre[k], rede_eqs.index(k)))
        w = livre[eq]
        melhor = vertices_ligados()
        def pronto(b):
            return min((melhor.get(v, INF) for i in b['membros'] for v in R.TV[i]), default=INF)
        # o bloco já ligado (ou o que fica ligado primeiro); entre os já ligados, a zona onde a equipe está, depois a
        # ordem da água e, na zona, secundária antes de terciária
        def chave(b):
            return (max(w, pronto(b)), ultima.get(eq) != b['zona'], ordem_z[b['zona']], b['classe'] != 'secundária',
                    b['agua'], b['pb'])
        b = min(pendentes, key=chave)
        b['pronto'] = pronto(b)
        pendentes.remove(b)
        b['trechos'] = ordem_no_bloco(b, melhor)
        if o['troca_frente_dias'] and ultima.get(eq) not in (None, b['zona']):
            w += round(o['troca_frente_dias'] * DIA)                          # deslocamento para a outra frente
        for i in b['trechos']:
            w = fazer(eq, i, w, p, 'Rede da zona')
            fim[i] = plano['trechos'][i]['fim']
        livre[eq] = w
        ultima[eq] = b['zona']
        b['eq'] = eq
        tr = [plano['trechos'][i] for i in b['trechos']]
        b['ini'], b['fim'] = tr[0]['ini'], tr[-1]['fim']
        b['lig'] = sum(T[i]['lig'] for i in b['trechos'])
        del b['membros']
        plano['blocos'].append(b)
    # o pé alto também vira bloco (para as ligações e o Project): cada corrida do mesmo diâmetro, na ordem do tempo
    grupo_de = lambda d: 'DE 225' if d >= 200 else 'DE 160' if d == 160 else 'DE 90/110' if d in (90, 110) else f'DE {d}'
    corridas = []
    for i in pe_alto:
        chave = (frente_de(T[i]), grupo_de(T[i]['de']))
        if corridas and corridas[-1][0] == chave:
            corridas[-1][1].append(i)
        else:
            corridas.append((chave, [i]))
    for (z, g), lst in corridas:
        tr = [plano['trechos'][i] for i in lst]
        plano['blocos'].append({'zona': z, 'pb': f"pé alto · {T[lst[0]]['zona'].replace('Zona', 'Zona ')} · {g}",
                                'trechos': lst, 'eq': 'ANK1', 'ini': tr[0]['ini'], 'fim': tr[-1]['fim'],
                                'lig': sum(T[i]['lig'] for i in lst), 'pe_alto': True})

    # ---- 4) caixas: as do caminho da água primeiro; obra civil a partir de mar/2027, montagem a partir de jul/2027
    caminho_cx = set()
    for z in zonas:
        entra = min(zonas_trs[z], key=lambda i: (agua(i), i))
        for k in RA.Rede.caminho(entra, ent, pai):
            caminho_cx.update(R.pecas_do_trecho(k))
    for j in caixas:
        if any(T[i]['sub'] for i in E[j]['tr']):
            caminho_cx.add(j)
    plano['caixas_caminho'] = caminho_cx

    def pronto_cx(j):
        trs = [plano['trechos'][i]['fim'] for i in E[j]['tr'] if i in plano['trechos']]
        if trs:
            return max(trs)
        z = next((n[:6] for n in E[j]['noms'] if n.startswith('Zona')), None)
        return max((plano['trechos'][i]['fim'] for i in zonas_trs.get(z, [])), default=ent_w['ANK2'])
    cx, ordem_civil = {}, []
    resto_c = set(caixas)
    w = ent_w['ANK2']
    while resto_c:
        prontas = [j for j in resto_c if pronto_cx(j) <= w]
        if prontas:
            j = min(prontas, key=lambda j: (j not in caminho_cx, pronto_cx(j), j))
        else:
            j = min(resto_c, key=lambda j: (pronto_cx(j), j not in caminho_cx, j))
        w0 = max(w, pronto_cx(j))
        w1 = w0 + round(CAIXA_DIAS[E[j]['tp']] * DIA)
        cx[j] = {'civ_ini': w0, 'civ_fim': w1, 'pronto': pronto_cx(j), 'caminho': j in caminho_cx}
        ordem_civil.append(j)
        w = w1
        resto_c.discard(j)
    # montagem: uma frente só, a partir de jul/2027; com 'hidro_caminho_antes', as do caminho logo depois da obra civil
    w_h = CAL.w(INICIO_HIDRO)
    ordem_hidro = []
    if o['hidro_caminho_antes']:
        w_a = ent_w['ANK2']
        for j in sorted((j for j in caixas if j in caminho_cx), key=lambda j: (cx[j]['civ_fim'], j)):
            w0 = max(w_a, cx[j]['civ_fim'])
            w1 = w0 + round(HIDRO_DIAS[E[j]['tp']] * DIA)
            cx[j].update(hid_ini=w0, hid_fim=w1)
            ordem_hidro.append(j)
            w_a = w1
    resto_h = {j for j in caixas if 'hid_ini' not in cx[j]}
    while resto_h:
        prontas = [j for j in resto_h if cx[j]['civ_fim'] <= w_h]
        j = (min(prontas, key=lambda j: (j not in caminho_cx, cx[j]['civ_fim'], j)) if prontas
             else min(resto_h, key=lambda j: (cx[j]['civ_fim'], j not in caminho_cx, j)))
        w0 = max(w_h, cx[j]['civ_fim'])
        w1 = w0 + round(HIDRO_DIAS[E[j]['tp']] * DIA)
        cx[j].update(hid_ini=w0, hid_fim=w1)
        ordem_hidro.append(j)
        w_h = w1
        resto_h.discard(j)
    plano['caixas'], plano['ordem_civil'], plano['ordem_hidro'] = cx, ordem_civil, ordem_hidro

    # ---- 5) fechamento (como na REV00): teste e interligação por zona e da Subadutora, cadastro, desmobilização
    zona_cx = collections.defaultdict(list)
    for j in caixas:
        z = next((n[:6] for n in E[j]['noms'] if n.startswith('Zona')), None)
        if any(T[i]['sub'] for i in E[j]['tr']):
            z = 'SUB'
        zona_cx[z].append(j)
    fech = {}

    def teste_do_caminho(cam):
        """Teste hidrostático do pedaço da Subadutora que está no caminho (entre registros), e não da Subadutora toda."""
        sub_cam = [plano['trechos'][k]['fim'] for k in cam if T[k]['sub']]
        return max(sub_cam) + TESTE_DIAS * DIA if sub_cam else 0
    plano['teste_do_caminho'] = teste_do_caminho
    sub_trs = [plano['trechos'][i] for i in range(len(T)) if T[i]['sub']]
    sub_fim = max(x['fim'] for x in sub_trs)
    fech['SUB'] = {'teste': (sub_fim, sub_fim + TESTE_DIAS * DIA)}
    if o['interlig_por_caminho']:      # só as caixas da própria Subadutora (a de entrada de uma zona fica com a zona)
        hid_sub = max((cx[j]['hid_fim'] for j in zona_cx['SUB'] if all(T[i]['sub'] for i in E[j]['tr'])), default=0)
    else:
        hid_sub = max((cx[j]['hid_fim'] for j in zona_cx['SUB']), default=0)
    a = max(fech['SUB']['teste'][1], hid_sub)
    fech['SUB']['interlig'] = (a, a + INTERLIG_DIAS * DIA)
    for z in zonas:
        trs = [plano['trechos'][i] for i in zonas_trs[z]]
        ini, fim_z = min(x['ini'] for x in trs), max(x['fim'] for x in trs)
        teste = (fim_z, fim_z + TESTE_DIAS * DIA)
        if o['interlig_por_caminho']:  # as caixas do caminho da água até a entrada da zona e o teste do que vem antes
            entra = min((i for i in zonas_trs[z] if i in ent), key=lambda i: (agua(i), i))
            cam = RA.Rede.caminho(entra, ent, pai)
            cxs = {j for k in cam for j in R.pecas_do_trecho(k) if j in cx}
            sub_antes = teste_do_caminho(cam)
            a = max(teste[1], sub_antes, max((cx[j]['hid_fim'] for j in cxs), default=0))
        else:
            a = max(teste[1], fech['SUB']['teste'][1], max((cx[j]['hid_fim'] for j in zona_cx[z]), default=0))
        prim = min(x['fim'] for x in trs)
        fech[z] = {'ini': ini, 'fim': fim_z, 'teste': teste, 'interlig': (a, a + INTERLIG_DIAS * DIA),
                   'cadastro': (prim + CADASTRO_DEPOIS, fim_z + CADASTRO_DEPOIS),
                   'eq': max(trs, key=lambda x: x['fim'])['eq']}
    fech['SUB'].update(ini=min(x['ini'] for x in sub_trs), fim=sub_fim, eq='ANK1',
                       cadastro=(min(x['fim'] for x in sub_trs) + CADASTRO_DEPOIS, sub_fim + CADASTRO_DEPOIS))
    ultimo = max([f['interlig'][1] for f in fech.values()] + [f['cadastro'][1] for f in fech.values()] +
                 [b['fim'] + LIG_ATRASO for b in plano['blocos']] + [cx[j]['hid_fim'] for j in caixas])
    plano['fechamento'], plano['zona_cx'] = fech, zona_cx
    plano['desmob'] = (ultimo, ultimo + DESMOB_DIAS * DIA)
    plano['fim'] = ultimo + DESMOB_DIAS * DIA
    plano['canteiro'] = (CAL.w(CANT_FEITO[0]), CAL.w(CANT_FEITO[1] + dt.timedelta(days=1)))
    plano['canteiro_inst'] = (CAL.w(CANT_INST[0]), CAL.w(CANT_INST[1] + dt.timedelta(days=1)))
    plano['T'], plano['E'] = T, E
    # ---- 6) ligado ao reservatório: quando o último trecho do caminho fica pronto
    fim = {i: x['fim'] for i, x in plano['trechos'].items()}
    plano['ligado'], melhor, pai_b = R.ligado_em(fim, vertices=True, pais=True)
    plano['ligacao_pai'] = (melhor, pai_b)
    # ---- 7) cada zona: a entrada principal, o caminho até a saída do reservatório e as caixas desse caminho
    saida_de = {R.idx[n]: n for n, _ in saidas}
    zinfo = {}
    for z in zonas + ['SUB']:
        trs = [i for i in range(len(T)) if frente_de(T[i]) == z and i in ent]
        principal = min(trs, key=lambda i: (agua(i), i))
        cam = RA.Rede.caminho(principal, ent, pai)
        fora = []                                   # o que fica fora da zona e alimenta algum trecho dela
        for i in trs:
            for k in RA.Rede.caminho(i, ent, pai):
                if frente_de(T[k]) != z and k not in fora:
                    fora.append(k)
        fora.sort(key=agua)
        caixas_cam = []
        for k in cam:
            for j in R.pecas_do_trecho(k):
                if j not in caixas_cam:
                    caixas_cam.append(j)
        saida = next((saida_de[k] for k in cam if k in saida_de), None)
        zinfo[z] = {'trechos': trs, 'principal': principal, 'caminho': cam, 'fora': fora, 'caixas': caixas_cam,
                    'saida': saida, 'entradas': sorted({next((k for k in RA.Rede.caminho(i, ent, pai) if frente_de(T[k]) == z), i)
                                                        for i in trs}, key=agua),
                    'caminho_pronto': max([fim[k] for k in cam[:-1]] or [fim[principal]]),
                    'toda_ligada': max(plano['ligado'][i] for i in trs),
                    'rede_pronta': max(fim[i] for i in trs), 'km': sum(T[i]['L'] for i in trs) / 1000}
    plano['zinfo'] = zinfo
    plano['saidas'] = [n for n, _ in saidas]
    return plano


def gargalo(pl, i):
    """O trecho que faltava no melhor caminho até o reservatório quando o trecho i ficou pronto (o último a ficar
    pronto nesse caminho), ou None se o trecho já nasceu ligado."""
    R = pl['rede']
    melhor, pai_b = pl['ligacao_pai']
    fim = {k: x['fim'] for k, x in pl['trechos'].items()}
    v = min(R.TV[i], key=lambda u: melhor.get(u, INF))
    pior, k_pior = -INF, None
    while v in pai_b:
        k, v = pai_b[v]
        if fim.get(k, INF) > pior:
            pior, k_pior = fim.get(k, INF), k
    return k_pior if pior > fim[i] else None


VALVULAS = ('VM', 'VRP', 'MV')                 # registros, redutoras e macromedidores: limites de setor


def setores(pl):
    """Setores entre registros (VM), VRPs e macromedidores: os pedaços da rede que um teste isola."""
    T, E, R = pl['T'], pl['E'], pl['rede']
    corte = {'E%d' % j for j, e in enumerate(E) if e['tp'] in VALVULAS}
    setor, n = {}, 0
    for s0 in range(len(T)):
        if s0 in setor:
            continue
        pilha = [s0]
        setor[s0] = n
        while pilha:
            i = pilha.pop()
            for v in R.TV[i] - corte:
                for k in R.VT[v]:
                    if k not in setor:
                        setor[k] = n
                        pilha.append(k)
        n += 1
    return setor


def carga_detalhe(pl):
    """Por trecho, o que ele espera para poder receber água, sem contar o reservatório (teste e interligação por zona,
    como na REV00): o caminho da água (árvore do menor caminho), as frentes desse caminho testadas e interligadas e as
    caixas do caminho montadas. {i: {'caminho', 'frentes', 'teste', 'interlig', 'caixas', 'montagem', 'pronto'}}"""
    T, R, cx, f = pl['T'], pl['rede'], pl['caixas'], pl['fechamento']
    ent, _, pai = R.arvore()
    caixas_do = {}
    out = {}
    for i in range(len(T)):
        cam = RA.Rede.caminho(i, ent, pai)
        frentes = []
        caixas = []
        for k in cam:
            if frente_de(T[k]) not in frentes:
                frentes.append(frente_de(T[k]))
            if k not in caixas_do:
                caixas_do[k] = R.pecas_do_trecho(k)
            caixas += [j for j in caixas_do[k] if j in cx and j not in caixas]
        montagem = max([cx[j]['hid_fim'] for j in caixas], default=0)
        if pl['opcoes'].get('interlig_por_caminho'):
            # REV02: a Subadutora conta pelo pedaço do caminho (testado e com as caixas dele); cada zona do caminho,
            # pela interligação dela (que já é pelo caminho até a entrada)
            parte = pl['teste_do_caminho'](cam)
            zs = [z for z in frentes if z != 'SUB']
            teste = max([parte] + [f[z]['teste'][1] for z in zs])
            interlig = max([parte + INTERLIG_DIAS * DIA if parte else 0] + [f[z]['interlig'][1] for z in zs])
        else:
            teste = max(f[z]['teste'][1] for z in frentes)
            interlig = max(f[z]['interlig'][1] for z in frentes)
        out[i] = {'caminho': cam, 'frentes': frentes, 'teste': teste, 'interlig': interlig, 'caixas': caixas,
                  'montagem': montagem, 'pronto': max(interlig, montagem)}
    return out


def nao_ligados(pl):
    """Os trechos que ficam prontos antes de estar ligados ao reservatório: [{'i', 'espera', 'k', 'em_execucao'}],
    com k = o trecho que faltava no caminho (o último a ficar pronto) e em_execucao = k já tinha começado quando o
    trecho i ficou pronto (é a frente em execução de outra equipe)."""
    tr, lig = pl['trechos'], pl['ligado']
    out = []
    for i, x in tr.items():
        if lig[i] > x['fim']:
            k = gargalo(pl, i)
            out.append({'i': i, 'espera': lig[i] - x['fim'], 'k': k,
                        'em_execucao': k is not None and tr[k]['ini'] <= x['fim']})
    return sorted(out, key=lambda d: (tr[d['i']]['fim'], d['i']))


def carga(pl, por_setor=False):
    """{trecho: instante em que ele pode receber água, sem contar o reservatório} = o maior entre: o caminho pronto,
    testado e desinfetado; as caixas do caminho montadas; o setor (ou a zona) testado e interligado."""
    T, R, cx = pl['T'], pl['rede'], pl['caixas']
    ent, dist, pai = R.arvore()
    fim = {i: x['fim'] for i, x in pl['trechos'].items()}
    caixas_do = {i: R.pecas_do_trecho(i) for i in range(len(T))}
    out = {}
    if not por_setor:
        return {i: d['pronto'] for i, d in carga_detalhe(pl).items()}
    st = setores(pl)
    membros = collections.defaultdict(list)
    for i, s_ in st.items():
        membros[s_].append(i)
    teste = {s_: max(fim[i] for i in lst) + TESTE_DIAS * DIA for s_, lst in membros.items()}
    for i in range(len(T)):
        cam = RA.Rede.caminho(i, ent, pai)
        w = max(teste[st[k]] for k in cam)
        w = max([w] + [cx[j]['hid_fim'] for k in cam for j in caixas_do[k] if j in cx])
        out[i] = w + INTERLIG_DIAS * DIA
    return out

