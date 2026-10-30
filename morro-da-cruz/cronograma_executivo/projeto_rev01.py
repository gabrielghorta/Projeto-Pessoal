"""XML do MS Project da REV01: o plano trecho a trecho da REV00 (gerar_project.montar) e o que a regra nova pede: o
marco "Reservatório em operação" sem data (a definir) e, para a Subadutora e cada zona, os marcos "ligada ao
reservatório" e "em carga", com as predecessoras de verdade (os trechos do caminho da água, o teste, a interligação, as
caixas do caminho e o marco do reservatório)."""
import collections

import analise_rev01 as AN
import gerar_project as GP
import motor_rev01 as M1
from motor import CAL

NOTA_RES = ('Sem data: o reservatório ainda vai ser licitado. Quando houver a data de operação, troque "a definir" pela '
            'data (ou agende a tarefa automaticamente com a restrição "Não começar antes de" essa data): os marcos '
            '"em carga" se recalculam. Não há carga provisória.')


def caminho_ligacao(pl, i):
    """Os trechos do melhor caminho (o que liga primeiro) do trecho i até a saída do reservatório."""
    R = pl['rede']
    melhor, pai_b = pl['ligacao_pai']
    v = min(R.TV[i], key=lambda u: melhor.get(u, M1.INF))
    out = []
    while v in pai_b:
        k, v = pai_b[v]
        out.append(k)
    return out


def montar(pl, cen, A):
    P = GP.montar(pl, cen)
    T, E, tr = pl['T'], pl['E'], pl['trechos']
    P.tarefas[0]['nome'] = f"CT 10.239/2026 - MORRO DA CRUZ - REV01 - {cen['titulo']}"
    novo_nome = {
        'REDES DE 160 mm - PÉ ALTO ATÉ O REAJUSTE':
            'PÉ ALTO ATÉ O REAJUSTE - ZONA 11, JUNTO DA SAÍDA DO RESERVATÓRIO (DE 160; DEPOIS DE 225 E DE 90/110)',
        'SUBADUTORA (ADUTORA + REDES DE DE 225 E 250)':
            'SUBADUTORA (ADUTORA + REDES DE DE 225 E 250) - DA SAÍDA DO RESERVATÓRIO (TR005) PARA FORA'}
    for t in P.tarefas:
        t['nome'] = novo_nome.get(t['nome'], t['nome'])
        if ' · pé alto · ' in t['nome']:           # blocos do pé alto: "ZONA 11 · pé alto · Zona 11 · DE 160"
            frente, resto = t['nome'].split(' · pé alto · ')
            ns = frente.startswith('NS - ')
            t['nome'] = (('NS - ' if ns else '') + f"PÉ ALTO · {resto.upper()} · "
                         + ('SUBADUTORA' if frente.endswith('SUB') else 'REDE DA ZONA'))
        if t['nome'].startswith('INTERLIGAÇÃO E ENTRADA EM CARGA - '):
            t['nome'] = t['nome'].replace('INTERLIGAÇÃO E ENTRADA EM CARGA - ', 'INTERLIGAÇÃO - ')
    # as tarefas que viram predecessoras, pelo nome que gerar_project dá a cada uma
    por_nome = {t['nome']: t['uid'] for t in P.tarefas}
    uid_tr = {i: por_nome[f"{t['R']} - DE {t['de']} - {t['L']:.2f} m"] for i, t in enumerate(T)}
    uid_hid = {j: por_nome[f"MONTAGEM {E[j]['tp']} - {E[j]['noms'][0] if E[j]['noms'] else E[j]['id']}"]
               for j in pl['caixas']}
    rot = lambda z: AN.zona_txt(z).upper()
    uid_teste = {z: por_nome[f'TESTE HIDROSTÁTICO E DESINFECÇÃO - {rot(z)}'] for z in ['SUB'] + pl['zonas']}
    uid_int = {z: por_nome[f'INTERLIGAÇÃO - {rot(z)}'] for z in ['SUB'] + pl['zonas']}
    n0 = len(P.tarefas)
    P.add('LIGAÇÃO AO RESERVATÓRIO E ENTRADA EM CARGA (REGRA DA REV01)', 2, resumo=True)
    res = P.add('RESERVATÓRIO EM OPERAÇÃO - DATA A DEFINIR (licitação do reservatório)', 3, marco=True, notas=NOTA_RES)
    res['manual'] = 'a definir'
    for z in A['zonas']:
        zid = z['z']
        trs = pl['zinfo'][zid]['trechos']
        P.add(f'{rot(zid)} - {z["km"]:.1f} km'.replace('.', ','), 3, resumo=True)
        # ligada: todos os trechos da frente prontos e o melhor caminho de cada um até a saída do reservatório;
        # as tarefas de cada equipe já estão em fila (término → início), então basta a última de cada equipe
        precisa = set(trs)
        for i in trs:
            precisa.update(caminho_ligacao(pl, i))
        ultima = {}
        for i in precisa:
            eq = tr[i]['eq']
            if eq not in ultima or tr[i]['fim'] > tr[ultima[eq]]['fim']:
                ultima[eq] = i
        lig = P.add(f'{rot(zid)} LIGADA AO RESERVATÓRIO', 4, z['toda_ligada'], z['toda_ligada'], marco=True,
                    links=[('FS', uid_tr[i], 0) for i in sorted(ultima.values(), key=lambda i: tr[i]['fim'])],
                    notas=f'A rede toda da frente construída e ligada à saída do reservatório por rede pronta. O caminho '
                          f'até a entrada da frente fica pronto em {CAL.fim(z["caminho_pronto"]):%d/%m/%Y}.')
        # em carga: ligada, o teste e a interligação de cada frente do caminho da água, as caixas desse caminho
        # montadas e o reservatório em operação
        frentes = sorted({fr for i in trs for fr in A['det'][i]['frentes']}, key=lambda x: (x != 'SUB', x))
        caixas = sorted({j for i in trs for j in A['det'][i]['caixas']}, key=lambda j: (pl['caixas'][j]['hid_fim'], j))
        links = ([('FS', lig['uid'], 0), ('FS', res['uid'], 0)] + [('FS', uid_teste[fr], 0) for fr in frentes] +
                 [('FS', uid_int[fr], 0) for fr in frentes] + [('FS', uid_hid[j], 0) for j in caixas])
        P.add(f'{rot(zid)} EM CARGA (DEPOIS DA OPERAÇÃO DO RESERVATÓRIO)', 4, z['pronta_carga'], z['pronta_carga'],
              marco=True, links=links,
              notas='Sem a data do reservatório, a data mostrada é quando a frente fica pronta para carga: o caminho '
                    'testado, desinfetado e interligado e as caixas do caminho montadas. Com a data no marco do '
                    'reservatório, vale a maior das duas.')
    novos = P.tarefas[n0:]
    del P.tarefas[n0:]
    k = next(n for n, t in enumerate(P.tarefas) if t['nome'] == 'DESMOBILIZAÇÃO DO CANTEIRO')
    P.tarefas[k:k] = novos
    return P


def conferir(P):
    """Nenhuma predecessora aponta para tarefa inexistente e nenhum marco novo ficou sem predecessora."""
    uids = {t['uid'] for t in P.tarefas}
    ruins = [(t['nome'], u) for t in P.tarefas for _, u, _ in t['links'] if u not in uids]
    sem = [t['nome'] for t in P.tarefas if t['marco'] and ('LIGADA AO' in t['nome'] or 'EM CARGA (' in t['nome'])
           and not t['links']]
    return ruins, sem, collections.Counter(len(t['links']) for t in P.tarefas if t['marco'] and 'EM CARGA (' in t['nome'])
