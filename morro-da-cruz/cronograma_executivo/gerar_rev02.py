"""Gera a REV02 do cronograma (30/10/2026), só o cenário B: a REV01 com as correções da análise crítica (rev02.py).

    python3 gerar_rev02.py [PASTA_DE_SAIDA]

Grava o xlsx (modelo do BM por equipe, PREMISSAS com o quadro REV01 × REV02 e a cascata das mudanças, PROGRAMAÇÃO e
CARGA), o XML do MS Project e o Gantt em HTML (o gerar_rev02.sh imprime em PDF A3). A REV01 é refeita aqui, com o
calendário dela, só para o quadro."""
import datetime as dt
import os
import subprocess
import sys

import analise_rev01 as AN
import gantt_rev01
import gerar_project as GP
import motor
import motor_rev01 as M1
import projeto_rev01
import rev02
import xlsx_rev01
from motor import CAL, DIA, PRAZO, REAJUSTE

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = sys.argv[1] if len(sys.argv) > 1 else AQUI + '/saida'
os.makedirs(SAIDA, exist_ok=True)
CONTRATO = 49878748.6575869
CEN = {'id': 'B', 'p': 90.0, 'titulo': 'REV02 - CENÁRIO B - 90 m/dia - A OBRA SAI DO RESERVATÓRIO, COM CHUVA, DIÂMETRO E '
                                       'LIGAÇÕES PELAS EQUIPES',
       'p_txt': 'a média de 80 a 100 m/dia informada pelo responsável, com teto pelo diâmetro',
       'arquivo': 'CRONOGRAMA_MORRO_DA_CRUZ_REV02_B_90M_DIA'}
MES = AN.MES
d = lambda w: f'{CAL.fim(w):%d/%m/%Y}'          # término
di = lambda w: f'{CAL.inicio(w):%d/%m/%Y}'      # início
mil = lambda v: f'{v:,.0f}'.replace(',', '.')
brl = lambda v: f'R$ {v:,.2f}'.replace(',', '#').replace('.', ',').replace('#', '.')
km = lambda v: f'{v:,.2f} km'.replace(',', '#').replace('.', ',').replace('#', '.')
pct = lambda v: f'{100 * v / CONTRATO:.1f}%'.replace('.', ',')


def resumo_plano(p, lv, v, mensal):
    """Os números do quadro, já em texto: a data de cada instante sai do calendário em uso agora."""
    k_reaj = next(k for k, m in enumerate(lv.meses) if m[1] >= REAJUSTE)
    pico = max(range(len(v)), key=lambda k: v[k])
    lig = p['ligado']
    nl = [i for i, x in p['trechos'].items() if lig[i] > x['fim']]
    T = p['T']
    det = M1.carga_detalhe(p)
    pronto_z = {}
    for i, x in det.items():
        z = M1.frente_de(T[i])
        pronto_z[z] = max(pronto_z.get(z, 0), x['pronto'])
    z11 = [i for i, t in enumerate(T) if t['loc'] == 'Zona11' and not t['sub']]
    sub = [i for i in p['fila']['ANK1'] if p['trechos'][i]['fase'] == 'Subadutora']
    fim = CAL.data_fim(p['fim'])
    return {
        'fim': fim, 'fim_txt': f'{fim:%d/%m/%Y}', 'folga': (PRAZO - fim).days, 'antes': sum(v[:k_reaj]), 'out': v[0],
        'pico': pico, 'v_pico': v[pico], 'total': sum(v),
        'pico_txt': f"{lv.meses[pico][0]}ª medição ({MES[lv.meses[pico][1].month]}/{lv.meses[pico][1]:%y})",
        'n_med': len(lv.meses),
        'rede_fim': d(max(f['fim'] for z, f in p['fechamento'].items() if z != 'SUB')),
        'cx_fim': d(max(c['hid_fim'] for c in p['caixas'].values())),
        'sub_txt': f"{di(p['trechos'][sub[0]]['ini'])} a {d(p['fim_subadutora'])}",
        'z11_txt': f"{di(min(p['trechos'][i]['ini'] for i in z11))} a {d(max(p['trechos'][i]['fim'] for i in z11))}",
        'carga_z11': d(pronto_z['Zona11']), 'carga_ultima': d(max(pronto_z.values())),
        'nl_n': len(nl), 'nl_km': sum(T[i]['L'] for i in nl) / 1000,
        'nl_espera': max([(lig[i] - p['trechos'][i]['fim']) / DIA for i in nl], default=0),
        'sem_carga_kmmes': sum(m['km_prontos'] for m in mensal),
        'pe_alto': '; '.join(f"{b['pb'].split(' · ')[-1]}: {mil(sum(T[i]['L'] for i in b['trechos']))} m, "
                             f"{di(b['ini'])[:5]} a {d(b['fim'])}"
                             for b in sorted((b for b in p['blocos'] if b.get('pe_alto')), key=lambda b: b['ini'])),
        'trocas': sum(sum(1 for a, b in zip(z, z[1:]) if a != b) for z in
                      ([M1.frente_de(T[i]) for i in p['fila'][e]] for e in ('E1A', 'E1B', 'E2C', 'E2D', 'ANK1'))),
    }


# ---------------------------------------------------------------- 1) a REV01, com o calendário e as equipes dela
D1, rede1, itens1 = motor.ler_dados()
pl1 = M1.programar(D1, rede1, CEN['p'])
livro1, _, val1 = AN.faturamento_mensal(pl1, itens1, D1)
r1 = resumo_plano(pl1, livro1, val1, AN.analisar(pl1, livro1)['mensal'])
del pl1, livro1

# ---------------------------------------------------------------- 2) a cascata: uma mudança de cada vez (cada uma num processo)
cascata = []
for n in range(8):
    out = subprocess.run([sys.executable, os.path.join(AQUI, 'rev02_cascata.py'), str(n)], capture_output=True, text=True,
                         check=True).stdout.strip().splitlines()[-1].split('|')
    cascata.append(out)

# ---------------------------------------------------------------- 3) a REV02
tirados = rev02.preparar()
AN.REV.update(rev02.ROTULOS)
D, rede06, itens = motor.ler_dados()
pl = M1.programar(D, rede06, CEN['p'], rev02.OPCOES)
livro, origem, val = AN.faturamento_mensal(pl, itens, D)
A = AN.analisar(pl, livro)
r2 = resumo_plano(pl, livro, val, A['mensal'])
T = pl['T']
por_ano = {}
for dia_, m in tirados.items():
    if dt.date(2026, 10, 1) <= dia_ <= max(r2['fim'], PRAZO):
        por_ano.setdefault(m, 0)
        por_ano[m] += 1

quadro = [
    ('Ordem das zonas', ', '.join(z.replace('Zona', '') for z in pl['zonas']) + ' (na ordem em que a água chega)',
     ', '.join(z.replace('Zona', '') for z in pl['zonas']) + ' (a mesma)'),
    ('Calendário', 'seg a sex, sem feriados; sem recesso e sem chuva',
     f"seg a sex, sem feriados; recesso de 22/12 a 02/01 ({por_ano.get('Recesso de fim de ano', 0)} dias úteis) e 4 dias "
     f"de chuva por mês de out a abr ({por_ano.get('Chuva (estimativa)', 0)} dias úteis)"),
    ('Entrada do Empreiteiro 2 (Equipes C e D)', '01/04/2027', f'{rev02.ENTRADA_EMP2:%d/%m/%Y}'),
    ('Produtividade das frentes de rede (depois do reajuste)', '90 m/dia em todo diâmetro',
     '90 m/dia até DE 160; 60 m/dia de DE 225 a 315; 45 m/dia de DE 355 a 500; 1ª semana de cada empreiteiro a 45 m/dia'),
    ('Ligações prediais', 'na mesma frente, 5 dias úteis atrás, sem tirar tempo da rede',
     f"pela própria equipe, {rev02.OPCOES['ligacoes_por_dia']} por dia, logo depois de cada trecho de DE 63"),
    ('Troca de frente (deslocamento)', f"não contada ({r1['trocas']} trocas)",
     f"{rev02.OPCOES['troca_frente_dias']:.1f} dia útil por troca ({r2['trocas']} trocas)".replace('.', ',')),
    ('Caixas do caminho da água e interligação', 'montagem a partir de jul/2027; interligação de cada frente depois de todas '
     'as caixas dela', 'peças do caminho (Subadutora inclusive) compradas antes e montadas logo depois da obra civil; '
     'teste e interligação pelo caminho da água'),
    ('Pé alto (Equipe Adutora a 60 m/dia até 01/02/2027)', r1['pe_alto'], r2['pe_alto']),
    ('Subadutora (Equipe Adutora)', r1['sub_txt'], r2['sub_txt']),
    ('Rede da Zona 11', r1['z11_txt'], r2['z11_txt']),
    ('Zona 11 pronta para receber água (sem contar o reservatório)', r1['carga_z11'], r2['carga_z11']),
    ('Última frente pronta para receber água', r1['carga_ultima'], r2['carga_ultima']),
    ('Término da rede das zonas', r1['rede_fim'], r2['rede_fim']),
    ('Término das caixas e do hidromecânico', r1['cx_fim'], r2['cx_fim']),
    ('Término da obra', r1['fim_txt'], r2['fim_txt']),
    ('Folga (+) ou atraso (−) em relação a 23/03/2028 (dias corridos)', str(r1['folga']), str(r2['folga'])),
    ('Faturamento programado até jan/2027, antes do reajuste (P0)', f"{brl(r1['antes'])} ({pct(r1['antes'])} do contrato)",
     f"{brl(r2['antes'])} ({pct(r2['antes'])} do contrato)"),
    ('Outubro/2026 (P0)', brl(r1['out']), brl(r2['out'])),
    ('Mês de maior faturamento (P0)', f"{r1['pico_txt']}: {brl(r1['v_pico'])}", f"{r2['pico_txt']}: {brl(r2['v_pico'])}"),
    ('Número de medições', str(r1['n_med']), str(r2['n_med'])),
    ('Total programado (P0)', brl(r1['total']), brl(r2['total'])),
    ('Trechos que ficam prontos antes de ligados ao reservatório',
     f"{r1['nl_n']} trechos, {km(r1['nl_km'])}; maior espera {r1['nl_espera']:.1f} dias úteis".replace('.', ',', 1),
     f"{r2['nl_n']} trechos, {km(r2['nl_km'])}; maior espera {r2['nl_espera']:.1f} dias úteis (aba CARGA, seção 6)".replace('.', ',', 1)),
    ('Rede pronta sem carga até o fim da obra (km × mês; com a data do reservatório em branco)',
     km(r1['sem_carga_kmmes']).replace(' km', ' km × mês'), '=KM_MES_SEM_CARGA'),
]
NOMES_PASSO = {'REV01': 'REV01 como está', 'emp2': '+ 2º empreiteiro em 01/03/2027', 'chuva': '+ recesso e chuva',
               'prod_por_de': '+ produtividade pelo diâmetro', 'entrada_meia_dias': '+ 1ª semana a meia produtividade',
               'troca_frente_dias': '+ meio dia por troca de frente', 'ligacoes_por_dia': '+ ligações pelas equipes (20/dia)',
               'caminho': '+ caixas do caminho antes e interligação pelo caminho (= REV02)'}
cascata_txt = [f"{NOMES_PASSO[c[1]]}: fim da obra {dt.date.fromisoformat(c[2]):%d/%m/%Y} ({int(c[3]):+d} dias); "
               f"Zona 11 pronta para receber água em {dt.date.fromisoformat(c[5]):%d/%m/%Y}" for c in cascata]

textos = [
    ('A REV02 (30/10/2026): A REV01 COM A ANÁLISE CRÍTICA', [
        'A regra continua a da REV01: a obra sai do reservatório da Zona 11 e sobe com a rede, pelo caminho da água, para '
        'cada trecho pronto já ficar ligado ao reservatório. A REV02 põe no cronograma o que a REV01 deixava de fora: a '
        'chuva e o recesso, o diâmetro na produtividade, as ligações feitas pelas próprias equipes, o deslocamento entre '
        'frentes, a entrada dos empreiteiros e a ligação do caminho da água antes de montar todas as caixas.',
        'O que mais pesa no prazo são as ligações prediais pelas equipes de rede (11.894 ligações a 20 por dia = 595 dias '
        'de equipe) e a chuva com o recesso. O resultado mostra o atraso real; a solução (equipes só de ligação, mais uma '
        'frente, aditivo) fica para depois, a pedido do responsável.',
        'Primeira água: na REV01 nenhuma zona podia receber água antes de 18/11/2027, porque a interligação da Subadutora '
        'esperava todas as caixas que encostam nela, até o macromedidor de entrada da Zona 02 (MV-02). Na REV02 cada frente '
        'espera só o caminho até ela: o pedaço da Subadutora testado e as caixas desse caminho montadas.']),
    ('A CASCATA: O QUE CADA MUDANÇA FAZ NO PRAZO (UMA DE CADA VEZ, ACUMULANDO)', cascata_txt),
    ('DECISÕES DO RESPONSÁVEL (30/10/2026)', [
        'Pé alto até o reajuste, só com a equipe própria da Ankara (Equipe Adutora): DE 160 da Zona 11, depois o DE 225 e '
        'o DE 90/110 dela, a 60 m/dia; a Subadutora a partir de 01/02/2027, do TR005 para fora.',
        'Empreiteiro 1 com 2 equipes em 04/01/2027; Empreiteiro 2 com 2 equipes em 01/03/2027.',
        'Antecipar as peças das caixas da Subadutora (e do caminho da água).',
        'As ligações prediais são feitas pelas próprias equipes de empreiteiro (por enquanto), umas 20 por dia.',
        'Se a obra passar de 23/03/2028, mostrar o atraso; a solução vem depois.',
        'Aluguel de contêiner: do mês em que cada um chega ao fim da obra (o que está no canteiro), como na REV01.',
        'Continuam as decisões da REV01: 4 saídas do reservatório (TR005, TR006, TR080, TR077), a confirmar com a Caesb e o '
        'engenheiro sênior; data de operação do reservatório em branco (C13), sem carga provisória.']),
    ('PREMISSAS ADOTADAS NESTA REVISÃO', [
        'Calendário: seg a sex, 07:00-12:00 e 13:00-17:00 (9 h/dia), sem os feriados nacionais e do DF; recesso de 22/12 a '
        '02/01; 4 dias úteis de chuva por mês de outubro a abril, espalhados no mês (um em cada quarto). O Project leva '
        'esses dias como não úteis.',
        'Produtividade: 90 m/dia por equipe até DE 160; 60 m/dia de DE 225 a 315; 45 m/dia de DE 355 a 500 (o pé alto '
        'continua a 60 m/dia). Nos 5 primeiros dias úteis, cada equipe de empreiteiro rende a metade.',
        f"Ligações prediais: as 11.894 do BM nos trechos de DE 63, pelo comprimento; a equipe que assenta o trecho faz as "
        f"ligações dele logo depois, {rev02.OPCOES['ligacoes_por_dia']} por dia, e só então pega o próximo trecho.",
        'Troca de frente: meio dia útil cada vez que uma equipe muda de zona (ou a Equipe Adutora sai da Subadutora).',
        'Caixas: obra civil a partir de 01/03/2027, depois dos trechos que chegam na caixa; as do caminho da água '
        '(Subadutora inclusive) montadas logo depois da obra civil, com as peças compradas antes; as demais a partir de '
        '01/07/2027.',
        'Teste hidrostático: de cada zona, 10 dias úteis depois do último trecho; o da Subadutora, por pedaço do caminho '
        'até cada zona. Interligação de 3 dias depois do teste e das caixas do caminho. A desinfecção vem logo antes da '
        'entrada em carga, que depende da operação do reservatório: feita no fim da zona, ela venceria antes da água '
        'chegar.',
        'Tudo o mais é a REV01: ordem da água, blocos zona × PB, topografia 2 semanas antes, cadastro 30 dias depois, '
        'desmobilização de 10 dias, canteiro, material faturado na aplicação, valores em P0, ADM proporcional ao '
        'faturamento.']),
    ('PENDÊNCIAS', [
        'Ligações: dimensionar equipes só de ligação e comparar com esta revisão (é o que mais atrasa).',
        'Confirmar as 4 saídas do reservatório com a Caesb e o engenheiro sênior; preencher a C13 quando houver a data.',
        'Validar com o engenheiro sênior os tetos de produtividade por diâmetro e os dias de chuva.']),
    ('ABAS', [('BM POR EQUIPE', 'o BM vertical com um bloco por equipe: quantidade e valor de cada item em cada medição'),
              ('BM CONSOLIDADO', 'o BM horizontal (juntada) somando as equipes, com o resumo de BDI e K'),
              ('CRONOGRAMA FF', 'o cronograma físico-financeiro no modelo da Caesb, por grupo'),
              ('RESUMO POR EQUIPE', 'faturamento mensal por equipe, produção física e gráficos'),
              ('PROGRAMAÇÃO', 'datas de cada trecho e de cada caixa (mesmas do Project), com a ligação ao reservatório e a carga'),
              ('CARGA', 'zonas na ordem da água, caminho até a saída do reservatório, dependências, km ligados e não '
                        'ligados mês a mês, exceções e setores')]),
]

# ---------------------------------------------------------------- 4) arquivos
x = f"{SAIDA}/{CEN['arquivo']}.xlsx"
xlsx_rev01.gerar(x, CEN, pl, livro, origem, itens, A, quadro, textos)
P = projeto_rev01.montar(pl, CEN, A)
for t in P.tarefas:                      # a desinfecção sai do fim da zona: vai para antes da carga
    t['nome'] = t['nome'].replace('TESTE HIDROSTÁTICO E DESINFECÇÃO', 'TESTE HIDROSTÁTICO')
for data, nome in ((dt.date(2027, 2, 1), 'PEDIR O REAJUSTE À CAESB (1º aniversário: 31/01/2027)'),
                   (dt.date(2028, 2, 1), 'PEDIR O REAJUSTE À CAESB (2º aniversário: 31/01/2028)')):
    if CAL.w(data) < pl['fim']:
        P.add(nome, 2, CAL.w(data), CAL.w(data), marco=True,
              notas='O reajuste só vem com o pedido da contratada (contrato 6.1 a 6.4).')
ruins, sem, nlinks = projeto_rev01.conferir(P)
assert not ruins and not sem, (ruins, sem)
n = GP.xml(P, pl, CEN, f"{SAIDA}/{CEN['arquivo']}.xml", criacao=dt.datetime(2026, 10, 30, 18, 0))
resumo = [('Produtividade', '90 m/dia (DE 225-315: 60; DE 355-500: 45)'),
          ('Fim da obra', r2['fim_txt']),
          ('Folga (+) ou atraso (−) no prazo', f"{r2['folga']} dias (REV01: {r1['folga']})"),
          ('Fim da Subadutora', d(pl['fim_subadutora'])),
          ('Zona 11 pronta para receber água', r2['carga_z11']),
          ('Faturado até jan/2027 (P0)', f"R$ {r2['antes'] / 1e6:.2f} mi (REV01: {r1['antes'] / 1e6:.2f})".replace('.', ',')),
          ('Maior mês (P0)', f"{MES[livro.meses[r2['pico']][1].month]}/{livro.meses[r2['pico']][1]:%y}: "
                             f"R$ {r2['v_pico'] / 1e6:.2f} mi".replace('.', ',')),
          ('Ligações prediais', f"pelas equipes, {rev02.OPCOES['ligacoes_por_dia']}/dia"),
          ('Operação do reservatório', 'a definir')]
open(f"{SAIDA}/{CEN['arquivo']}_GANTT.html", 'w', encoding='utf-8').write(gantt_rev01.html(pl, CEN, A, resumo))
print('REV02 fim', r2['fim'], 'folga', r2['folga'], 'até jan/27', round(r2['antes']), 'outubro', round(r2['out']),
      'pico', r2['pico_txt'], round(r2['v_pico']), 'total', round(r2['total']), 'medições', r2['n_med'])
print('REV01 fim', r1['fim'], 'até jan/27', round(r1['antes']), 'total', round(r1['total']))
print('Zona 11 pronta para água: REV01', r1['carga_z11'], 'REV02', r2['carga_z11'])
print('cascata:'); [print('  ', t) for t in cascata_txt]
print('Project:', n, 'tarefas; predecessoras dos marcos "em carga":', dict(nlinks))
print('ok', x)
