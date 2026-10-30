"""Gera os dois cenários do cronograma físico executivo base: xlsx (modelo do BM, por equipe) e XML do MS Project."""
import collections
import os
import sys

import faturamento
import gerar_project
import gantt
import gerar_xlsx
import motor
from motor import CAL, PRAZO, REAJUSTE

SAIDA = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)) + '/saida'
os.makedirs(SAIDA, exist_ok=True)
D, rede, itens = motor.ler_dados()
p_prazo = motor.resolver_prazo(D, rede)
cenarios = [
    {'id': 'A', 'p': p_prazo, 'titulo': f'CENÁRIO A - PRAZO CONTRATUAL ({p_prazo:.1f} m/dia)'.replace('.', ','),
     'p_txt': 'a menor produtividade que fecha a obra no prazo contratual',
     'arquivo': 'CRONOGRAMA_BASE_MORRO_DA_CRUZ_A_PRAZO'},
    {'id': 'B', 'p': 90.0, 'titulo': 'CENÁRIO B - RITMO MÉDIO DE 90 m/dia',
     'p_txt': 'a média de 80 a 100 m/dia informada pelo responsável',
     'arquivo': 'CRONOGRAMA_BASE_MORRO_DA_CRUZ_B_90M_DIA'},
]
res = []
for cen in cenarios:
    pl = motor.programar(D, rede, cen['p'])
    livro, origem = faturamento.distribuir(pl, itens, D)
    Q = gerar_xlsx.quantidades(itens, livro)
    vu = {it['chave']: it for it in itens}
    nm = len(livro.meses)
    val = [0.0] * nm
    for (eq, ch), qs in Q.items():
        it = vu[ch]
        fat = (1.1528 if it['classe'] == 'MATERIAL' else 1.2148) * (1 - 0.1404)
        for k, q in enumerate(qs):
            val[k] += round(q * it['vu'], 2) * fat
    pct_adm = 1304685.94 / (48534308.16 - 1304685.94)
    sem_bdi = [0.0] * nm
    for (eq, ch), qs in Q.items():
        for k, q in enumerate(qs):
            sem_bdi[k] += round(q * vu[ch]['vu'], 2)
    val = [v + s * pct_adm * 1.2148 * (1 - 0.1404) for v, s in zip(val, sem_bdi)]
    k_reaj = next(k for k, m in enumerate(livro.meses) if m[1] >= REAJUSTE)
    antes = sum(val[:k_reaj])
    pico = max(range(nm), key=lambda k: val[k])
    rede_fim = max(f['fim'] for z, f in pl['fechamento'].items() if z != 'SUB')
    res.append({'cen': cen, 'pl': pl, 'livro': livro, 'origem': origem, 'val': val, 'antes': antes, 'pico': pico,
                'rede_fim': rede_fim})
    print(cen['id'], cen['p'], 'fim', CAL.data_fim(pl['fim']), 'antes do reajuste', round(antes), 'pico', pico + 1,
          round(val[pico]), 'total', round(sum(val)))
MES = gerar_xlsx.MES


def linha(r):
    pl, lv = r['pl'], r['livro']
    fim = CAL.data_fim(pl['fim'])
    return [r['cen']['p'], fim, CAL.data_fim(pl['fim_subadutora']), CAL.data_fim(r['rede_fim']),
            CAL.data_fim(max(c['hid_fim'] for c in pl['caixas'].values())), (PRAZO - fim).days, r['antes'],
            r['antes'] / 49878748.6575869,
            f"{lv.meses[r['pico']][0]}ª medição ({MES[lv.meses[r['pico']][1].month]}/{lv.meses[r['pico']][1]:%y})",
            r['val'][r['pico']], len(lv.meses)]


nomes = ['Produtividade das frentes de rede depois do reajuste (m/dia)', 'Término da obra',
         'Término da Subadutora', 'Término da rede das zonas', 'Término das caixas e do hidromecânico',
         'Folga (+) ou atraso (−) em relação a 23/03/2028 (dias corridos)',
         'Faturamento programado até jan/2027, antes do reajuste (R$, P0)', 'Faturamento até jan/2027 (% do contrato)',
         'Mês de maior faturamento', 'Faturamento no mês de maior faturamento (R$, P0)', 'Número de medições']
la, lb = linha(res[0]), linha(res[1])
comparativo = list(zip(nomes, la, lb))
for r in res:
    cen = r['cen']
    x = f"{SAIDA}/{cen['arquivo']}.xlsx"
    gerar_xlsx.gerar(x, cen, r['pl'], r['livro'], r['origem'], itens, D, comparativo)
    P = gerar_project.montar(r['pl'], cen)
    n = gerar_project.xml(P, r['pl'], cen, f"{SAIDA}/{cen['arquivo']}.xml")
    lv = r['livro']
    resumo = [('Produtividade das frentes de rede (depois do reajuste)', f"{cen['p']:.1f} m/dia".replace('.', ',')),
              ('Fim da obra', f"{CAL.fim(r['pl']['fim']):%d/%m/%Y}"),
              ('Folga (+) ou atraso (−) no prazo', f"{(PRAZO - CAL.data_fim(r['pl']['fim'])).days} dias"),
              ('Fim da Subadutora', f"{CAL.fim(r['pl']['fim_subadutora']):%d/%m/%Y}"),
              ('Faturado até jan/2027 (P0)', f"R$ {r['antes'] / 1e6:.2f} mi".replace('.', ',')),
              ('Maior mês (P0)', f"{MES[lv.meses[r['pico']][1].month]}/{lv.meses[r['pico']][1]:%y}: R$ {r['val'][r['pico']] / 1e6:.2f} mi".replace('.', ',')),
              ('Outubro/2026 (P0)', f"R$ {r['val'][0] / 1e3:,.0f} mil".replace(',', '.'))]
    open(f"{SAIDA}/{cen['arquivo']}_GANTT.html", 'w', encoding='utf-8').write(gantt.html(r['pl'], cen, resumo))
    print('ok', x, n, 'tarefas', 'outubro', round(r['val'][0]))
