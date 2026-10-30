"""A rede da água para a REV01: o grafo dos trechos a partir das saídas do reservatório (Zona 11).

Vértices: a peça (nó ou caixa) em que a ponta do trecho termina, pelo REV02 (iniE/fimE); as duas pontas de uma
junção JUNTAR do config/topologia.json (o mesmo tubo continuando: divisa de zona, emenda sem nó, cruzamento com
semicírculo, passagem ao lado do nó), que NÃO se ligam ao nó; as pontas sem nó que sobram, agrupadas pela coordenada
com a folga de 1,0 m da emenda sem nó; e as peças no meio da linha (tê de sela, ventosa, derivação), que ligam o
trecho que passa por elas. O reservatório é um vértice só, ligado às pontas de saída.

Nada é inventado: a ponta que não encosta em nada fica solta e aparece no relatório.
"""
import collections
import heapq
import json
import math
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
TOPOLOGIA = os.path.join(os.path.dirname(AQUI), 'config', 'topologia.json')
FOLGA_M = 1.0                        # emenda sem nó: pontas a até 1,0 m são o mesmo ponto (topologia, D-68)
RES = 'RESERVATÓRIO'
INF = float('inf')


class Rede:
    def __init__(self, D, saidas, topologia=TOPOLOGIA):
        """saidas: [(nome do trecho na 06.1, 'ini' | 'fim')] — as pontas que saem do reservatório."""
        self.T, self.E = D['trechos'], D['els']
        T, E = self.T, self.E
        self.idx = {t['R']: i for i, t in enumerate(T)}
        cfg = json.load(open(topologia, encoding='utf-8'))
        junt = {}
        for j in cfg['juncoes']:
            if j['decisao'] == 'JUNTAR':
                chave = 'J:' + '|'.join(sorted(p['trecho'] + ':' + p['lado'] for p in j['pontas']))
                for p in j['pontas']:
                    junt[(self.idx[p['trecho']], p['lado'])] = chave
        saida = {(self.idx[n], lado) for n, lado in saidas}
        self.vert, soltas = {}, []
        for i, t in enumerate(T):
            for lado, e, xy in (('ini', t['iniE'], t['A']), ('fim', t['fimE'], t['B'])):
                if (i, lado) in saida:
                    self.vert[(i, lado)] = RES
                elif (i, lado) in junt:
                    self.vert[(i, lado)] = junt[(i, lado)]
                elif e is not None and e >= 0:
                    self.vert[(i, lado)] = 'E%d' % e
                else:
                    soltas.append((i, lado, xy))
        # pontas sem nó que sobraram: o mesmo ponto quando a até FOLGA_M uma da outra ou de uma ponta já ligada
        ligadas = [(xy, self.vert[(i, lado)]) for i, t in enumerate(T)
                   for lado, xy in (('ini', t['A']), ('fim', t['B'])) if (i, lado) in self.vert]
        grupos = []
        for i, lado, xy in soltas:
            perto = next((v for q, v in ligadas if math.dist(q, xy) <= FOLGA_M), None)
            if perto:
                self.vert[(i, lado)] = perto
                continue
            g = next((g for g in grupos if any(math.dist(xy, q) <= FOLGA_M for _, _, q in g)), None)
            (g.append((i, lado, xy)) if g is not None else grupos.append([(i, lado, xy)]))
        self.soltas = []
        for k, g in enumerate(grupos):
            for i, lado, xy in g:
                self.vert[(i, lado)] = 'C%d' % k
            if len(g) == 1:
                self.soltas.append(g[0])
        # peça no meio da linha: liga o trecho que passa por ela (e o que termina nela)
        self.meio = collections.defaultdict(set)
        for j, e in enumerate(E):
            for i in e['tr']:
                if T[i]['iniE'] != j and T[i]['fimE'] != j:
                    self.meio[i].add('E%d' % j)
        # e as que a topologia achou no meio da linha (a NS corta o tubo ali): CONEXAO_NO_MEIO_DA_LINHA
        por_nome = {n: j for j, e in enumerate(E) for n in e['noms']}
        for p in cfg['pendencias']:
            if p['tipo'] == 'CONEXAO_NO_MEIO_DA_LINHA' and p.get('no') in por_nome and p.get('trecho') in self.idx:
                self.meio[self.idx[p['trecho']]].add('E%d' % por_nome[p['no']])
        # cruzamento e passagem: o tubo que passa não se liga à peça (a junção JUNTAR já o tirou das pontas)
        self.TV, self.VT = {}, collections.defaultdict(set)
        for i in range(len(T)):
            vs = {self.vert[(i, 'ini')], self.vert[(i, 'fim')]} | self.meio.get(i, set())
            self.TV[i] = vs
            for v in vs:
                self.VT[v].add(i)

    # ------------------------------------------------------------ consultas
    def componente(self, de=RES):
        vistos, pilha = set(), [de]
        trs = set()
        while pilha:
            v = pilha.pop()
            if v in vistos:
                continue
            vistos.add(v)
            for i in self.VT[v]:
                if i not in trs:
                    trs.add(i)
                    pilha.extend(self.TV[i] - vistos)
        return trs

    def arvore(self, permitido=None):
        """Caminho mais curto (em metros de tubo) do reservatório a cada trecho. Devolve (entrada, dist, pai):
        entrada[i] = (metros do reservatório até o começo do trecho i, vértice por onde a água chega nele);
        pai[v] = (trecho, vértice anterior) no caminho até v. permitido(i) restringe os trechos usados."""
        dist, pai, entrada = {RES: 0.0}, {}, {}
        fila = [(0.0, RES)]
        while fila:
            d, v = heapq.heappop(fila)
            if d > dist.get(v, INF):
                continue
            for i in self.VT[v]:
                if permitido and not permitido(i):
                    continue
                if i not in entrada or d < entrada[i][0]:
                    entrada[i] = (d, v)
                for u in self.TV[i]:
                    nd = d + self.T[i]['L']
                    if u != v and nd < dist.get(u, INF):
                        dist[u] = nd
                        pai[u] = (i, v)
                        heapq.heappush(fila, (nd, u))
        return entrada, dist, pai

    @staticmethod
    def caminho(i, entrada, pai):
        """Os trechos do reservatório até o trecho i (inclusive), pela árvore do caminho mais curto."""
        out, v = [i], entrada[i][1]
        while v in pai:
            k, v = pai[v]
            out.append(k)
        return out[::-1]

    def ligado_em(self, fim, vertices=False, pais=False):
        """fim: {trecho: instante em que fica pronto (INF se nunca)}. Devolve {trecho: instante em que ele fica
        ligado ao reservatório por trechos prontos} = o menor, entre os caminhos, do maior término do caminho.
        Com vertices=True, devolve também {vértice: instante em que ele fica ligado}; com pais=True, ainda
        {vértice: (trecho, vértice anterior)} do melhor caminho."""
        melhor, pai = {RES: -INF}, {}
        fila = [(-INF, RES)]
        lig = {}
        while fila:
            w, v = heapq.heappop(fila)
            if w > melhor.get(v, INF):
                continue
            for i in self.VT[v]:
                wi = max(w, fim.get(i, INF))
                if wi < lig.get(i, INF):
                    lig[i] = wi
                for u in self.TV[i]:
                    if wi < melhor.get(u, INF):
                        melhor[u] = wi
                        pai[u] = (i, v)
                        heapq.heappush(fila, (wi, u))
        if pais:
            return lig, melhor, pai
        return (lig, melhor) if vertices else lig

    def pecas_do_trecho(self, i):
        """As caixas (não nós) nas pontas e no meio do trecho."""
        out = []
        for v in self.TV[i]:
            if v.startswith('E'):
                j = int(v[1:])
                if self.E[j]['tp'] != 'NÓ':
                    out.append(j)
        return out
