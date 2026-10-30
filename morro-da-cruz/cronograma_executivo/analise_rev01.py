"""Análise da REV01 que a planilha, o Gantt, o Project e a animação usam: o que cada trecho espera para receber água,
os trechos prontos antes de ligados ao reservatório (com o motivo), os km mês a mês, as zonas e os setores."""
import collections
import datetime as dt

import faturamento
import gerar_xlsx
import motor_rev01 as M1
import rede_agua as RA
from motor import CAL, DIA, NOME

MES = {1: 'JAN', 2: 'FEV', 3: 'MAR', 4: 'ABR', 5: 'MAI', 6: 'JUN', 7: 'JUL', 8: 'AGO', 9: 'SET', 10: 'OUT', 11: 'NOV', 12: 'DEZ'}


def curto(nome):
    """'Zona11_PB23_Adutora_TR005' -> 'TR005 (Zona11_PB23)'"""
    p = nome.split('_')
    return f"{p[-1]} ({p[0]}_{p[1]})" if len(p) >= 3 else nome


def zona_txt(z):
    return 'Subadutora' if z == 'SUB' else z.replace('Zona', 'Zona ')


def fim_mes(fim):
    """O instante (minutos úteis) do fim do último dia do mês: o que fica pronto até ele conta no mês."""
    return CAL.w(fim + dt.timedelta(days=1))


def faturamento_mensal(pl, itens, D):
    """(livro, origem, valor de cada medição em P0 com BDI, K e a administração local), como na REV00."""
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
    return livro, origem, [v + s * pct_adm * 1.2148 * (1 - 0.1404) for v, s in zip(val, sem)]


def ligado_em(pl, R):
    """{trecho: instante em que fica ligado ao reservatório} para qualquer plano (a REV00 também), no mesmo grafo."""
    return R.ligado_em({i: x['fim'] for i, x in pl['trechos'].items()})


def nao_ligados_mes(pl, lig, livro):
    """Mês a mês: km prontos, ligados e não ligados no fim do mês."""
    T = pl['T']
    out = []
    for n, ini, fim in livro.meses:
        wf = fim_mes(fim)
        prontos = [i for i, x in pl['trechos'].items() if x['fim'] <= wf]
        nl = [i for i in prontos if lig.get(i, RA.INF) > wf]
        out.append({'n': n, 'ini': ini, 'fim': fim, 'rot': f'{MES[ini.month]}/{ini:%y}', 'wf': wf, 'prontos': prontos,
                    'nao_ligados': nl, 'km_prontos': sum(T[i]['L'] for i in prontos) / 1000,
                    'km_nl': sum(T[i]['L'] for i in nl) / 1000})
    return out


def motivo(pl, x):
    """(categoria, texto) do trecho pronto antes de ligado."""
    T, tr = pl['T'], pl['trechos']
    i, k = x['i'], x['k']
    ti, tk = tr[i], tr[k]
    if ti['fase'] == 'pé alto' and tk['fase'] == 'pé alto':
        return ('decisão de 30/10 (pé alto: DE 160 antes do DE 225)',
                f"alimentado pelo {curto(T[k]['R'])} (DE {T[k]['de']}), que o pé alto assenta depois: o DE 160 da Zona 11 "
                f"vem primeiro, por decisão do responsável em 30/10/2026; ligado em {CAL.fim(tk['fim']):%d/%m/%Y}")
    if x['em_execucao']:
        return ('frente em execução',
                f"o {curto(T[k]['R'])} (DE {T[k]['de']}), que liga este trecho, está sendo assentado pela "
                f"{NOME[tk['eq']]}: pronto em {CAL.fim(tk['fim']):%d/%m/%Y}")
    dias = (tk['ini'] - ti['fim']) / DIA
    return ('frente da outra equipe logo em seguida',
            f"o {curto(T[k]['R'])} (DE {T[k]['de']}), que liga este trecho, começa {dias:.1f} dia(s) útil(eis) depois, "
            f"com a {NOME[tk['eq']]}: pronto em {CAL.fim(tk['fim']):%d/%m/%Y}".replace('.', ','))


def resumo_mes(pl, nl_mes, mot):
    """Texto dos trechos prontos não ligados no fim do mês, agrupados pelo trecho que falta."""
    T, tr = pl['T'], pl['trechos']
    g = collections.defaultdict(list)
    for i in nl_mes:
        g[mot[i]['k']].append(i)
    partes = []
    for k, lst in sorted(g.items(), key=lambda kv: -sum(T[i]['L'] for i in kv[1])):
        zs = sorted({zona_txt(M1.frente_de(T[i])) for i in lst})
        m = f"{sum(T[i]['L'] for i in lst):,.0f}".replace(',', '.')
        partes.append(f"{len(lst)} trecho(s) da {', '.join(zs)} ({m} m) esperam o {curto(T[k]['R'])}, pronto em "
                      f"{CAL.fim(tr[k]['fim']):%d/%m/%Y} [{mot[lst[0]]['cat']}]")
    return '; '.join(partes)


def analisar(pl, livro):
    T, E, R, tr = pl['T'], pl['E'], pl['rede'], pl['trechos']
    det = M1.carga_detalhe(pl)
    nl = M1.nao_ligados(pl)
    mot = {}
    for x in nl:
        cat, txt = motivo(pl, x)
        mot[x['i']] = dict(x, cat=cat, txt=txt)
    mensal = nao_ligados_mes(pl, pl['ligado'], livro)
    for m in mensal:
        m['texto'] = resumo_mes(pl, m['nao_ligados'], mot)
    ent, dist, pai = R.arvore()
    nomes_saida = set(pl['saidas'])
    # zonas na ordem da água (a Subadutora primeiro: é o tronco que sai do reservatório)
    zonas = []
    for z in ['SUB'] + pl['zonas']:
        zi = pl['zinfo'][z]
        trs = zi['trechos']
        p = zi['principal']
        v = ent[p][1]
        if v == RA.RES:
            peca = 'saída do reservatório'
        elif v.startswith('E'):
            e = E[int(v[1:])]
            peca = e['noms'][0] if e['noms'] else e['id']
        else:
            peca = 'emenda / divisa de zona'
        caixas = zi['caixas']
        zonas.append({
            'z': z, 'km': zi['km'], 'saida': zi['saida'], 'entrada': T[p]['R'], 'peca': peca, 'agua_km': ent[p][0] / 1000,
            'saidas': sorted({T[det[i]['caminho'][0]]['R'] for i in trs} & nomes_saida),
            'n_entradas': len(zi['entradas']), 'fora': zi['fora'], 'caminho': zi['caminho'],
            'caminho_km': sum(T[k]['L'] for k in zi['caminho'][:-1]) / 1000,
            'sub_no_caminho': [k for k in zi['caminho'][:-1] if T[k]['sub']],
            'caminho_pronto': zi['caminho_pronto'], 'caixas': caixas,
            'caixas_montadas': max([pl['caixas'][j]['hid_fim'] for j in caixas], default=None),
            'rede_pronta': zi['rede_pronta'], 'toda_ligada': zi['toda_ligada'],
            'ini': min(tr[i]['ini'] for i in trs),
            'teste': pl['fechamento'][z]['teste'], 'interlig': pl['fechamento'][z]['interlig'],
            'pronta_carga': max(det[i]['pronto'] for i in trs),
            'frentes_caminho': sorted({f for i in trs for f in det[i]['frentes']} - {z}),
            'caixas_carga': sorted({j for i in trs for j in det[i]['caixas']}),
        })
    # setores entre registros (VM), VRPs e macromedidores
    st = M1.setores(pl)
    membros = collections.defaultdict(list)
    for i, s in st.items():
        membros[s].append(i)
    setores = []
    for s, lst in membros.items():
        prim = min(lst, key=lambda i: (ent[i][0], i))
        v = ent[prim][1]
        if v == RA.RES:
            entra = 'saída do reservatório'
        elif v.startswith('E') and E[int(v[1:])]['tp'] in M1.VALVULAS:
            e = E[int(v[1:])]
            entra = e['noms'][0] if e['noms'] else e['id']
        else:
            entra = T[prim]['R']
        setores.append({'membros': lst, 'frentes': sorted({M1.frente_de(T[i]) for i in lst}, key=lambda z: (z != 'SUB', z)),
                        'km': sum(T[i]['L'] for i in lst) / 1000, 'entra': entra, 'agua_km': ent[prim][0] / 1000,
                        'ligado': max(pl['ligado'][i] for i in lst), 'pronto': max(tr[i]['fim'] for i in lst),
                        'pronta_carga': max(det[i]['pronto'] for i in lst)})
    setores.sort(key=lambda s: (s['agua_km'], s['entra']))
    for n, s in enumerate(setores, 1):
        s['n'] = n
        for i in s['membros']:
            st[i] = n
    # caixas: as zonas que dependem de cada uma para receber água
    depende = collections.defaultdict(set)
    for i, d in det.items():
        for j in d['caixas']:
            depende[j].add(M1.frente_de(T[i]))
    return {'det': det, 'nl': nl, 'mot': mot, 'mensal': mensal, 'zonas': zonas, 'setores': setores, 'setor_de': st,
            'depende': depende, 'ent': ent}


def dist_canteiro(pl, rede06, ate):
    """Média da DIST. CANTEIRO (06.1) pelos metros prontos até a data."""
    w = CAL.w(ate)
    a = b = 0.0
    for i, x in pl['trechos'].items():
        if x['fim'] <= w:
            d = float(rede06[pl['T'][i]['R']].get('DIST. CANTEIRO') or 0)
            a += pl['T'][i]['L'] * d
            b += pl['T'][i]['L']
    return a / b if b else 0.0
