"""Distribui cada item do BM vertical (REV04) pelas equipes e pelos meses, a partir do plano do motor."""
import collections
import datetime as dt
import re

import motor
from motor import (CAL, DIA, LIG_ATRASO, TOPO_ANTES, CADASTRO_DEPOIS, CAIXA_DIAS, HIDRO_DIAS, meses_do_contrato)

# colunas da aba REDE da 06.1 que medem os itens de rede do BM (APOIO_REDES da própria 06.1)
DRIVER_FIXO = {
    '5.4.8': 'ESCAV. EXT. ROCHA', '5.4.9': 'ESCAV. MAN. 1ª CAT. <1,50', '5.4.10': 'ESCAV. MAN. 1ª CAT. >1,50<3,00',
    '5.4.11': 'ESCAV. MEC. 1ª CAT. <1,50', '5.4.13': 'ESCAV. MEC. 1ª CAT. <1,50',
    '5.4.14': 'ESCAV. MEC. 1ª CAT. >1,50<3,00', '5.4.15': 'ESCAV. MEC. 1ª CAT. >1,50<3,00',
    '5.4.12': 'ESCAV. MEC. 2ª CAT. <1,50', '5.4.16': 'ESCAV. MEC. 2ª CAT. >1,50<3,00',
    '5.6.1': 'ESGOT. VALA', '5.2.7': 'LOCAÇÃO C/ NOTA', '5.2.1': 'CADASTRO',
}
CANDIDATAS = ['VOL. TOTAL ESC.', 'LASTRO2', 'ATERRO AREIA', 'REATERRO', 'CARGA', 'CARGA DE ROCHA',
              'ESC. PONTALETE >=1,25 M <1,5 M', 'ESC. DESCONTÍNUO >=1,5 M <3,0 M', 'ESC. CONTÍNUO MISTO >=3,0 M',
              'TRANSPORTE A GRANEL', 'PLACA SINALIZAÇÃO', 'SINALIZAÇÃO NOTURNA', 'PASSADIÇO - CHAPA DE AÇO (VEÍCULOS)',
              'PASSADIÇO - TÁBUAS (PEDESTRE)', 'TAPUME DESC. MÓVEL', 'FURO SOND.']
DES = {63, 90, 110, 125, 160, 225, 250, 280, 315, 355, 400, 500}


def num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def diametro(it):
    d = it['attrs'][5]                       # coluna DIÂMETRO do vertical
    try:
        d = int(float(d))
    except (TypeError, ValueError):
        return None
    return d if d in DES else None


def escolher_driver(it, T):
    """('coluna', nome) | ('de', d) — com o porquê, para a aba de premissas."""
    if it['item'] in DRIVER_FIXO:
        return ('col', DRIVER_FIXO[it['item']]), 'coluna da 06.1 (APOIO_REDES)'
    d = diametro(it)
    if d:
        return ('de', d), f'metros de DE {d}' + (' e 125' if d == 160 else '')
    alvo = it['q']
    melhor = None
    for c in CANDIDATAS:
        s = sum(num(t['rede'].get(c)) for t in T)
        if s > 0 and abs(s - alvo) / max(alvo, 1e-9) < 0.06:
            erro = abs(s - alvo) / alvo
            if not melhor or erro < melhor[1]:
                melhor = (c, erro)
    if melhor:
        return ('col', melhor[0]), f'coluna da 06.1 com a mesma soma ({melhor[0]})'
    return ('col', 'VOL. TOTAL ESC.'), 'volume de escavação do trecho (rateio)'


class Livro:
    """quantidade por (equipe, chave do vertical, mês)."""

    def __init__(self, plano):
        self.q = collections.defaultdict(float)
        fim = CAL.data_fim(plano['fim'])
        self.meses = meses_do_contrato(fim)
        if fim > self.meses[-1][2]:
            pass
        while self.meses[-1][2] < fim:       # cenário que passa do prazo: medições 19, 20…
            n, ini, _ = self.meses[-1]
            a, m = ini.year + (ini.month == 12), ini.month % 12 + 1
            ini2 = dt.date(a, m, 1)
            self.meses.append((n + 1, ini2, dt.date(a + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)))
        if fim > self.meses[17][2]:          # o 18º mês vai até o fim de março quando a obra continua
            n, ini, _ = self.meses[17]
            self.meses[17] = (n, ini, dt.date(2028, 3, 31))
        self.lim = [CAL.w(ini) for _, ini, _ in self.meses] + [10 ** 12]

    def mes(self, w):
        for k in range(len(self.meses)):
            if self.lim[k] <= w < self.lim[k + 1]:
                return k
        return len(self.meses) - 1 if w >= self.lim[-2] else 0

    def lancar(self, eq, chave, qtd, a, b=None):
        if qtd == 0:
            return
        if b is None or b <= a:
            self.q[(eq, chave, self.mes(a))] += qtd
            return
        k = self.mes(a)
        while True:
            fim_k = self.lim[k + 1]
            pedaco = min(b, fim_k) - max(a, self.lim[k])
            if pedaco > 0:
                self.q[(eq, chave, k)] += qtd * pedaco / (b - a)
            if b <= fim_k or k + 1 >= len(self.meses):
                if b > fim_k:                # depois do último mês: fica no último
                    self.q[(eq, chave, k)] += qtd * (b - fim_k) / (b - a)
                break
            k += 1


def distribuir(plano, itens, D):
    T, E = plano['T'], plano['E']
    tr = plano['trechos']
    cx = plano['caixas']
    L = Livro(plano)
    origem = {}                               # chave -> texto do critério (para as premissas)
    PC = D['pecas']
    # peças da 06.2 por item do BM: parte dos nós (vai com a rede) e parte das caixas (vai com a montagem)
    pecas_no = collections.defaultdict(lambda: collections.defaultdict(float))   # item -> nó -> qtd
    pecas_cx = collections.defaultdict(lambda: collections.defaultdict(float))
    for j, e in enumerate(E):
        for pc in e['pecas']:
            cod = str(PC[pc[0]][3])
            (pecas_cx if e['tp'] != 'NÓ' else pecas_no)[cod][j] += pc[1]

    def no_quando(j):
        """O nó entra com o primeiro dos seus trechos que fica pronto: a equipe e o intervalo desse trecho."""
        ts = [tr[i] for i in E[j]['tr'] if i in tr]
        if not ts:
            return None
        x = min(ts, key=lambda x: x['fim'])
        return x['eq'], x['ini'], x['fim']

    caixas = list(cx)
    peso_civ = {j: CAIXA_DIAS[E[j]['tp']] for j in caixas}
    peso_hid = {j: HIDRO_DIAS[E[j]['tp']] for j in caixas}
    zonas_fech = plano['fechamento']
    cant_ini, cant_fim = plano['canteiro']
    inst_ini, inst_fim = plano['canteiro_inst']
    des_ini, des_fim = plano['desmob']
    # contêineres no canteiro por mês: chegam com as equipes e ficam até o fim da obra
    ult = L.mes(plano['fim'] - 1)                      # o mês em que a obra acaba: o canteiro não fatura depois dele
    nm_ = len(L.meses) if ult is None else ult + 1
    no_canteiro = [0] * nm_
    chegadas = [(L.mes(CAL.w(d)), n) for d, n in motor.CONTEINERES]
    for k in range(nm_):
        no_canteiro[k] = sum(n for k0, n in chegadas if k0 <= k)
    total_cont = sum(n for _, n in motor.CONTEINERES)
    w_topo = CAL.w(motor.TOPO_INICIO)
    for it in itens:
        g, ch, q = it['grp'], it['chave'], it['q']
        if q == 0:
            origem[ch] = 'quantidade zero no BM'
            continue
        desc = (it['desc'] or '').upper()
        if g in ('1.1', '1.2'):
            un = str(it['un'] or '').upper()
            if 'CONTAINER' in desc and ('MES' in un or 'MÊS' in un):
                # aluguel: cada contêiner conta do mês em que chega até o fim da obra (não passa do BM)
                por_mes = q / 18 / total_cont
                usado = 0.0
                for k in range(nm_):
                    v = min(por_mes * no_canteiro[k], q - usado)
                    L.q[('CANT', ch, k)] += v
                    usado += v
                origem[ch] = (f'aluguel pelos contêineres no canteiro: 2 em out/26, 6 em nov/26, 12 em jan/27 e 18 em abr/27 '
                              f'({usado / q:.0%} do BM)')
            elif 'MES' in un or 'MÊS' in un or un in ('CHP', 'CHI'):
                # o funcionamento do canteiro: igual em cada mês, de nov/2026 (em out só o alambrado, o portão e 2 contêineres)
                n = nm_ - 1
                for k in range(1, n + 1):
                    L.q[('CANT', ch, k)] += q / n
                origem[ch] = f'mensal: 1/{n} por mês, de nov/2026 ao fim da obra'
            elif 'DESINSTALA' in desc:
                for (d, n) in motor.CONTEINERES:
                    L.q[('CANT', ch, L.mes(CAL.w(d)))] += q / 2 * n / total_cont
                L.lancar('CANT', ch, q / 2, des_ini, des_fim)
                origem[ch] = 'metade na chegada de cada contêiner (2 em out/26, 4 em nov/26, 6 em jan/27, 6 em abr/27), metade na desmobilização'
            elif it['item'] in motor.CANT_ITENS_OUT:
                L.lancar('CANT', ch, q, cant_ini, cant_fim)
                origem[ch] = 'executado em out/2026 (alambrado metálico e portão)'
            else:
                L.lancar('CANT', ch, q, inst_ini, inst_fim)
                origem[ch] = 'demais instalações do canteiro (03/11 a 18/12/2026)'
        elif g == '6.2':
            origem[ch] = 'administração local: proporcional ao faturamento do mês (TR 14.6), fórmula na planilha'
        elif g in ('2.1', '2.2'):
            drv, porque = escolher_driver(it, T)
            if drv[0] == 'de':
                d = drv[1]
                pesos = {t['i']: t['L'] for t in T if t['de'] == d or (d == 160 and t['de'] == 125)}
            else:
                pesos = {t['i']: num(t['rede'].get(drv[1])) for t in T}
            tot = sum(pesos.values())
            if tot <= 0:
                pesos = {t['i']: t['L'] for t in T}
                tot = sum(pesos.values())
                porque = 'metros de rede (rateio)'
            desloc = -TOPO_ANTES if it['item'] == '5.2.7' else CADASTRO_DEPOIS if it['item'] == '5.2.1' else 0
            for i, pw in pesos.items():
                if pw:
                    x = tr[i]
                    a_ = max(w_topo, x['ini'] + desloc) if desloc < 0 else x['ini'] + desloc
                    b_ = max(a_ + 1, x['fim'] + desloc)
                    L.lancar(x['eq'], ch, q * pw / tot, a_, b_)
            origem[ch] = porque + (' · 2 semanas antes do trecho' if desloc < 0 else
                                   ' · 30 dias depois do trecho' if desloc > 0 else '')
        elif g in ('3.1', '3.2'):
            tot = sum(peso_civ.values())
            for j in caixas:
                L.lancar('ANK2', ch, q * peso_civ[j] / tot, cx[j]['civ_ini'], cx[j]['civ_fim'])
            origem[ch] = 'obra civil das 132 caixas, pelo porte de cada tipo'
        elif g in ('4.1', '4.2') and 'INTERLIGA' in (it['orc'] or '').upper():
            ks = list(zonas_fech)
            for z in ks:
                a, b = zonas_fech[z]['interlig']
                L.lancar(zonas_fech[z]['eq'], ch, q / len(ks), a, b)
            origem[ch] = 'interligação de cada zona e da Subadutora (partes iguais)'
        elif g in ('4.1', '4.2'):
            tot = sum(t['lig'] for t in T)
            for t in T:
                if t['lig']:
                    x = tr[t['i']]
                    L.lancar(x['eq'], ch, q * t['lig'] / tot, x['ini'] + LIG_ATRASO, x['fim'] + LIG_ATRASO)
            origem[ch] = 'ligações prediais: nos trechos de DE 63, 5 dias úteis atrás da rede'
        elif g in ('5.1', '5.2'):
            pn, pcx = pecas_no.get(it['item'], {}), pecas_cx.get(it['item'], {})
            sn, sc = sum(pn.values()), sum(pcx.values())
            if g == '5.2':
                alvo = {j: 1.0 for j in caixas if E[j]['tp'] == 'VRP'}
                for j, pw in alvo.items():
                    L.lancar('ANK2', ch, q * pw / len(alvo), cx[j]['hid_ini'], cx[j]['hid_fim'])
                origem[ch] = 'montagem das VRP'
                continue
            if sn + sc == 0:
                tot = sum(peso_hid.values())
                for j in caixas:
                    L.lancar('ANK2', ch, q * peso_hid[j] / tot, cx[j]['hid_ini'], cx[j]['hid_fim'])
                origem[ch] = 'sem peça na 06.2: montagem hidromecânica das caixas'
                continue
            qn, qc = q * sn / (sn + sc), q * sc / (sn + sc)
            for j, pw in pn.items():
                w = no_quando(j)
                if w:
                    L.lancar(w[0], ch, qn * pw / sn, w[1], w[2])
                else:
                    qc += qn * pw / sn
            for j, pw in pcx.items():
                L.lancar('ANK2', ch, qc * pw / max(sc, 1e-9), cx[j]['hid_ini'], cx[j]['hid_fim'])
            if sc == 0 and qc > 0:            # parte de nó sem trecho: vai para a montagem
                tot = sum(peso_hid.values())
                for j in caixas:
                    L.lancar('ANK2', ch, qc * peso_hid[j] / tot, cx[j]['hid_ini'], cx[j]['hid_fim'])
            origem[ch] = (f'peças da 06.2: {sn / (sn + sc):.0%} nos nós (com a rede), '
                          f'{sc / (sn + sc):.0%} nas caixas (montagem a partir de jul/2027)')
        else:
            origem[ch] = 'sem regra'
    return L, origem


if __name__ == '__main__':
    import motor
    D, rede, itens = motor.ler_dados()
    pl = motor.programar(D, rede, 90.0)
    L, origem = distribuir(pl, itens, D)
    soma = collections.defaultdict(float)
    for (eq, ch, k), v in L.q.items():
        soma[ch] += v
    ruins = [(it['chave'], it['q'], round(soma[it['chave']], 3)) for it in itens
             if it['grp'] != '6.2' and abs(soma[it['chave']] - it['q']) > 1e-6 * max(1, it['q'])]
    print('itens que não fecham:', ruins[:20], len(ruins))
    cont = collections.Counter(origem.values())
    for k, v in cont.most_common():
        print(v, k)
    # valor por mês (sem BDI)
    vu = {it['chave']: it['vu'] for it in itens}
    cls = {it['chave']: it['classe'] for it in itens}
    por_mes = collections.defaultdict(float)
    for (eq, ch, k), v in L.q.items():
        f = 1.1528 if cls[ch] == 'MATERIAL' else 1.2148
        por_mes[k] += v * vu[ch] * f * (1 - 0.1404)
    acum = 0
    for k, (n, a, b) in enumerate(L.meses):
        acum += por_mes[k]
        print(n, a, b, round(por_mes[k]), round(acum))
