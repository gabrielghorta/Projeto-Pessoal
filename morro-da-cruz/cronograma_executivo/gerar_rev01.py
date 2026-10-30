"""Gera a REV01 do cronograma (30/10/2026), só o cenário B (90 m/dia): a obra sai do reservatório (Zona 11).

    python3 gerar_rev01.py [PASTA_DE_SAIDA]

Grava o xlsx (modelo do BM por equipe, com as PREMISSAS, a PROGRAMAÇÃO e a aba CARGA da regra nova), o XML do MS Project
e o Gantt em HTML (o gerar_rev01.sh imprime em PDF A3 e passa o XML pelo MPXJ). A REV00 do cenário B é refeita aqui só
para o quadro REV00 × REV01."""
import datetime as dt
import os
import sys

import analise_rev01 as AN
import gantt_rev01
import gerar_project as GP
import motor
import motor_rev01 as M1
import projeto_rev01
import xlsx_rev01
from motor import CAL, DIA, PRAZO, REAJUSTE

SAIDA = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)) + '/saida'
os.makedirs(SAIDA, exist_ok=True)
CONTRATO = 49878748.6575869
CEN = {'id': 'B', 'p': 90.0, 'titulo': 'REV01 - CENÁRIO B - RITMO MÉDIO DE 90 m/dia - A OBRA SAI DO RESERVATÓRIO (ZONA 11)',
       'p_txt': 'a média de 80 a 100 m/dia informada pelo responsável',
       'arquivo': 'CRONOGRAMA_MORRO_DA_CRUZ_REV01_B_90M_DIA'}
MES = AN.MES
d = lambda w: f'{CAL.fim(w):%d/%m/%Y}'          # término
di = lambda w: f'{CAL.inicio(w):%d/%m/%Y}'      # início
mil = lambda v: f'{v:,.0f}'.replace(',', '.')
brl = lambda v: f'R$ {v:,.2f}'.replace(',', '#').replace('.', ',').replace('#', '.')
km = lambda v: f'{v:,.2f} km'.replace(',', '#').replace('.', ',').replace('#', '.')
pct = lambda v: f'{100 * v / CONTRATO:.1f}%'.replace('.', ',')

# ---------------------------------------------------------------- os dois planos
D, rede06, itens = motor.ler_dados()
pl = M1.programar(D, rede06, CEN['p'])
livro, origem, val = AN.faturamento_mensal(pl, itens, D)
A = AN.analisar(pl, livro)
D0, rede0, itens0 = motor.ler_dados()
pl0 = motor.programar(D0, rede0, CEN['p'])
livro0, _, val0 = AN.faturamento_mensal(pl0, itens0, D0)
assert [t['R'] for t in pl0['T']] == [t['R'] for t in pl['T']]
lig0 = AN.ligado_em(pl0, pl['rede'])                        # a REV00 no mesmo grafo, com as mesmas 4 saídas
mensal0 = AN.nao_ligados_mes(pl0, lig0, livro0)
T = pl['T']


def resumo_plano(p, lv, v, mensal, lig):
    k_reaj = next(k for k, m in enumerate(lv.meses) if m[1] >= REAJUSTE)
    pico = max(range(len(v)), key=lambda k: v[k])
    nl = [i for i, x in p['trechos'].items() if lig[i] > x['fim']]
    mx = max(mensal, key=lambda m: m['km_nl'])
    return {
        'fim': CAL.data_fim(p['fim']), 'antes': sum(v[:k_reaj]), 'out': v[0], 'pico': pico, 'v_pico': v[pico],
        'pico_txt': f"{lv.meses[pico][0]}ª medição ({MES[lv.meses[pico][1].month]}/{lv.meses[pico][1]:%y})",
        'n_med': len(lv.meses), 'rede_fim': max(f['fim'] for z, f in p['fechamento'].items() if z != 'SUB'),
        'cx_fim': max(c['hid_fim'] for c in p['caixas'].values()),
        'nl_n': len(nl), 'nl_km': sum(p['T'][i]['L'] for i in nl) / 1000,
        'nl_espera': max([(lig[i] - p['trechos'][i]['fim']) / DIA for i in nl], default=0),
        'nl_max': mx['km_nl'], 'nl_max_mes': mx['rot'], 'nl_kmmes': sum(m['km_nl'] for m in mensal),
        'sem_carga_kmmes': sum(m['km_prontos'] for m in mensal),
        'dist': AN.dist_canteiro(p, rede06, dt.date(2027, 8, 1)),
    }


r0 = resumo_plano(pl0, livro0, val0, mensal0, lig0)
r1 = resumo_plano(pl, livro, val, A['mensal'], pl['ligado'])


def pe_alto_txt(p):
    T_ = p['T']
    partes = []
    for b in sorted((b for b in p['blocos'] if b.get('pe_alto')), key=lambda b: b['ini']):
        m = sum(T_[i]['L'] for i in b['trechos'])
        partes.append((b, m))
    if 'pe_alto' in p:                                    # REV01: corridas de DE da Zona 11
        return '; '.join(f"{b['pb'].split(' · ')[-1]} da Zona 11: {mil(m)} m, {di(b['ini'])[:5]} a {d(b['fim'])}"
                         for b, m in partes)
    zs = []
    for b, m in partes:
        if b['zona'] not in zs:
            zs.append(b['zona'])
    return (f"DE 160 das zonas {', '.join(z.replace('Zona', '') for z in zs)}: {mil(sum(m for _, m in partes))} m, "
            'longe da saída do reservatório')


sub0 = [i for i in pl0['fila']['ANK1'] if pl0['trechos'][i]['fase'] == 'Subadutora']
sub1 = [i for i in pl['fila']['ANK1'] if pl['trechos'][i]['fase'] == 'Subadutora']
z11 = lambda p: [i for i, t in enumerate(p['T']) if t['loc'] == 'Zona11' and not t['sub']]
quadro = [
    ('Ordem das zonas', ', '.join(z.replace('Zona', '') for z in pl0['zonas']) + ' (da mais perto para a mais longe do canteiro)',
     ', '.join(z.replace('Zona', '') for z in pl['zonas']) + ' (na ordem em que a água chega do reservatório)'),
    ('Pé alto: Equipe Adutora a 60 m/dia, de 16/11/2026 a 01/02/2027', pe_alto_txt(pl0), pe_alto_txt(pl)),
    ('Subadutora (Equipe Adutora, a partir de 01/02/2027)',
     f"{di(pl0['trechos'][sub0[0]]['ini'])} a {d(pl0['fim_subadutora'])}, começando pelo {AN.curto(T[sub0[0]]['R'])}, "
     f"a ponta da Subadutora (fim do caminho da água)",
     f"{di(pl['trechos'][sub1[0]]['ini'])} a {d(pl['fim_subadutora'])}, do {AN.curto(T[sub1[0]]['R'])} (saída do "
     f"reservatório) para fora"),
    ('Rede da Zona 11 (onde fica o reservatório)',
     f"{di(min(pl0['trechos'][i]['ini'] for i in z11(pl0)))} a {d(max(pl0['trechos'][i]['fim'] for i in z11(pl0)))}",
     f"{di(min(pl['trechos'][i]['ini'] for i in z11(pl)))} a {d(max(pl['trechos'][i]['fim'] for i in z11(pl)))}"),
    ('Término da rede das zonas', d(r0['rede_fim']), d(r1['rede_fim'])),
    ('Término das caixas e do hidromecânico', d(r0['cx_fim']), d(r1['cx_fim'])),
    ('Término da obra', f"{r0['fim']:%d/%m/%Y}", f"{r1['fim']:%d/%m/%Y}"),
    ('Folga (+) ou atraso (−) em relação a 23/03/2028 (dias corridos)', str((PRAZO - r0['fim']).days),
     str((PRAZO - r1['fim']).days)),
    ('Faturamento programado até jan/2027, antes do reajuste (P0)',
     f"{brl(r0['antes'])} ({pct(r0['antes'])} do contrato)", f"{brl(r1['antes'])} ({pct(r1['antes'])} do contrato)"),
    ('Outubro/2026 (P0)', brl(r0['out']), brl(r1['out'])),
    ('Mês de maior faturamento (P0)', f"{r0['pico_txt']}: {brl(r0['v_pico'])}", f"{r1['pico_txt']}: {brl(r1['v_pico'])}"),
    ('Número de medições', str(r0['n_med']), str(r1['n_med'])),
    ('Km prontos e não ligados ao reservatório: maior valor no fim de um mês',
     f"{km(r0['nl_max'])} ({r0['nl_max_mes']})", f"{km(r1['nl_max'])} ({r1['nl_max_mes']})"),
    ('Km prontos e não ligados ao reservatório: soma em km × mês', km(r0['nl_kmmes']).replace(' km', ' km × mês'),
     km(r1['nl_kmmes']).replace(' km', ' km × mês')),
    ('Trechos que ficam prontos antes de ligados ao reservatório',
     f"{r0['nl_n']} trechos, {km(r0['nl_km'])}; maior espera {r0['nl_espera']:.0f} dias úteis",
     f"{r1['nl_n']} trechos, {km(r1['nl_km'])}; maior espera {r1['nl_espera']:.1f} dias úteis (aba CARGA, seção 6)".replace('.', ',', 1)),
    ('Rede pronta sem carga até o fim da obra (km × mês; com a data do reservatório em branco, toda a rede pronta conta)',
     km(r0['sem_carga_kmmes']).replace(' km', ' km × mês'), '=KM_MES_SEM_CARGA'),
    ('DIST. CANTEIRO (06.1) média da rede pronta até jul/2027 (o deslocamento não está no modelo)',
     f"{r0['dist']:.2f}".replace('.', ','), f"{r1['dist']:.2f}".replace('.', ',')),
]

ordem_agua = ', '.join(z.replace('Zona', '') for z in pl['zonas'])
nl1 = A['nl']
cats = {}
for x in nl1:
    c = A['mot'][x['i']]['cat']
    n, L = cats.get(c, (0, 0.0))
    cats[c] = (n + 1, L + T[x['i']]['L'] / 1000)
textos = [
    ('A REGRA NOVA (30/10/2026): A OBRA SAI DO RESERVATÓRIO', [
        'Rede construída sem pressão interna de água pode quebrar ou lascar, e a água desta obra vem só do reservatório da '
        'Zona 11. Por isso a obra avança do reservatório para fora, pelo caminho da água: cada trecho pronto já fica ligado '
        'ao reservatório por rede pronta e pode entrar em carga assim que houver água.',
        'LIGADO AO RESERVATÓRIO EM: quando fica pronto o último trecho do caminho entre o trecho e a saída do reservatório '
        '(o caminho que liga primeiro, pela rede da 06.1, com as caixas da 06.2 e as junções do config/topologia.json).',
        'ENTRADA EM CARGA: a maior entre a operação do reservatório (célula C13), o caminho pronto, testado e desinfetado, as '
        'VRPs, registros (VM), ventosas (VTF), descargas (DF) e demais caixas do caminho montadas, e a zona do trecho testada '
        'e interligada. DIAS SEM CARGA = ENTRADA EM CARGA − TÉRMINO do trecho, em branco enquanto não houver a data.',
        'O reservatório ainda vai ser licitado: não tem data de operação e não há carga provisória (nem by-pass, registro ou '
        'outra fonte). A data não foi inventada nem trocada por outra: a célula C13 fica em branco até haver a data.',
        'Meta: nenhum trecho pronto fora da ligação, a não ser a frente em execução. Na REV01, '
        + '; '.join(f'{c}: {n} trechos, {km(L)}' for c, (n, L) in cats.items())
        + '. A lista, com o motivo de cada um, está na aba CARGA (seção 6) e nas colunas S e T da PROGRAMAÇÃO.',
        'Subadutora: da saída do reservatório para fora, começando pelo TR005 da Zona11_PB23, de montante para jusante pelo '
        'grafo; zona por zona, na ordem em que a água chega ao ponto de alimentação de cada uma.',
        f'Zonas na ordem da água: {ordem_agua}. Cada equipe livre pega o bloco (zona × PB, cortado nos pedaços ligados entre '
        'si) cujo caminho até o reservatório já está pronto ou fica pronto primeiro, e não o mais perto do canteiro; dentro '
        'do bloco, da alimentação para as pontas: primária, depois secundária, depois terciária. A equipe espera na zona '
        'dela a frente de outra equipe por até 10 dias úteis.',
        'Caixas (Equipe Ankara 2, a partir de mar/2027): primeiro as do caminho da água (as da Subadutora e as de entrada de '
        'cada zona: VRP, VM, VTF, DF, MV), depois as demais.']),
    ('DECISÕES DO RESPONSÁVEL (30/10/2026)', [
        'Saídas do reservatório: 4. O projeto está errado e será corrigido com a Caesb e o engenheiro sênior. Do lado '
        'esquerdo, o TR005 (DE 500) e o TR080 (DE 225); do lado direito, o TR077 (DE 225). O TR006 (DE 500, 2,4 m, solto nas '
        'duas pontas) é a 2ª saída de DE 500. O lado leste da Zona 11 conta como ligado pelo TR077.',
        'Pé alto: primeiro o DE 160 da Zona 11 (16/11 a 21/12/2026), depois o DE 225 da Zona 11 (até 15/01/2027) e o DE '
        '90/110 (até 01/02/2027), sempre a 60 m/dia. O DE 160 feito antes do DE 225 que o alimenta espera a ligação.',
        'Teste e interligação por zona, como na REV00 (12: as 11 zonas e a Subadutora). A aba CARGA mostra os setores entre '
        'registros, para uma decisão futura.',
        'Hidromecânico a partir de jul/2027, sem antecipar a compra das peças do caminho.',
        'Gerar a REV01 agora e ajustar depois com o engenheiro sênior.']),
    ('REGRAS DO RESPONSÁVEL (29/10/2026): CONTINUAM VALENDO', [
        '5 equipes de rede/obra: 1 equipe Ankara (adutora) e 2 empreiteiros com 2 equipes cada nas zonas; a equipe de caixas é uma 2ª equipe Ankara.',
        'Pé alto até o reajuste de janeiro de 2027: até lá só a equipe da adutora, em redes de diâmetro não tão alto (160 mm), produzindo pouco.',
        'O 1º empreiteiro entra em janeiro de 2027 com 2 equipes; o 2º entra em abril de 2027, completando as equipes.',
        'Produtividade média de 80 a 100 m por dia por equipe, em dias sem interferência.',
        'Caixas hidráulicas a partir de março de 2027, com redes já feitas; hidromecânico a partir de julho de 2027 (peças de SP e do exterior).',
        'Depois do reajuste, a equipe da adutora vai para onde for melhor; os empreiteiros não têm zonas definidas.',
        'As ligações prediais vão sendo feitas conforme a rede avança.',
        'Trabalho de segunda a sexta, das 7h às 17h.',
        'Na REV01, só o cenário B: a média de 90 m/dia, sem compensar o atraso com mais produtividade.']),
    ('PREMISSAS ADOTADAS NESTE CRONOGRAMA', [
        'Calendário: seg a sex, 07:00-12:00 e 13:00-17:00 (9 h/dia), sem os feriados nacionais e do DF (Carnaval, '
        'Sexta-feira Santa, Corpus Christi, 21/04, 30/11 e os nacionais). Sem recesso de fim de ano.',
        'Produtividade das frentes de rede depois do reajuste: 90,0 m/dia por equipe, igual para todos os diâmetros.',
        f'Pé alto: a Equipe Adutora começa em 16/11/2026 (a NS de topografia vem de 03 a 13/11), a {motor.P_PE_ALTO:.0f} m/dia, '
        'na Zona 11, do ponto mais perto da saída do reservatório: DE 160, depois DE 225 e DE 90/110 da Zona 11, até '
        '01/02/2027. Depois vai para a Subadutora, a partir do TR005, e, ao terminá-la, para as zonas.',
        'Grafo da água: vértices nas peças da 06.2 e nos nós da 06.1 (NÓ INICIAL e NÓ FINAL); as junções do '
        'config/topologia.json (divisa de zona, emenda sem nó, cruzamento e passagem não se ligam ao nó); as pontas sem nó '
        'ligadas pela coordenada, com a folga de 1,0 m do sistema; as peças no meio da linha. Nada inventado: com as 4 '
        'saídas, os 1.436 trechos ficam ligados ao reservatório.',
        'Ligações prediais: as 11.894 do BM ficam nos trechos de DE 63 (tê de serviço 63 e tê de sela 63 × 20), pelo '
        'comprimento, e são feitas pela mesma frente, 5 dias úteis atrás da rede.',
        'Caixas hidráulicas: os 132 dispositivos da 06.2 (45 DF, 26 VTF, 27 VM, 17 VRP, 11 MV e 6 HID). Obra civil a partir '
        'de 01/03/2027, depois dos trechos que chegam na caixa: DF 1 dia, VTF 1,5, VM 2, VRP e MV 3, HID 0,5. '
        'Hidromecânico a partir de 01/07/2027, depois da obra civil: DF, VTF e HID 0,5 dia, VM 1, VRP e MV 2.',
        'Peças da 06.2 (grupo hidromecânico do BM): as dos nós entram com o primeiro trecho do nó; as das caixas, na '
        'montagem hidromecânica. O item sem peça na 06.2 vai para a montagem.',
        'Topografia (NS) 2 semanas antes de cada trecho; cadastro técnico 30 dias corridos depois; teste hidrostático e '
        'desinfecção de 10 dias úteis no fim de cada zona; interligação de 3 dias depois do teste da zona, do teste da '
        'Subadutora e da montagem das caixas da zona; desmobilização de 10 dias no fim.',
        'Itens de rede do BM: cada um vai para os trechos pela coluna da aba REDE da 06.1 que o mede; o item com diâmetro, '
        'pelos metros daquele DE; os furos direcionais (MND) do BM ficam nos trechos do mesmo DE. O critério de cada linha '
        'está na última coluna da aba BM POR EQUIPE.',
        'Canteiro: em out/2026, só o que foi feito (demarcação, alambrado metálico, portão e 2 contêineres); as demais '
        'instalações de 03/11 a 18/12/2026. Os contêineres chegam com as equipes (2 em out/26, 4 em nov/26, 6 em jan/27 e 6 '
        'em abr/27); o aluguel conta do mês de chegada até o fim da obra. Os demais itens mensais em partes iguais por mês, '
        'de nov/2026 ao fim da obra.',
        'Administração local medida em proporção ao faturamento do mês (fórmula na aba BM POR EQUIPE).',
        'Material faturado na aplicação. Valores em P0 (sem reajuste). O reajuste de janeiro de 2027 vale para o que '
        'começar a partir de 01/02/2027 (contrato 6.1 a 6.4, com pedido da contratada).']),
    ('PENDÊNCIAS (A CONFIRMAR COM A CAESB E O ENGENHEIRO SÊNIOR)', [
        'Saídas do reservatório: no projeto, o TR077 (DE 225, lado leste) não encosta no reservatório e o TR006 (DE 500) está '
        'solto nas duas pontas. Se o lado leste da Zona 11 não puder sair pelo TR077, ele passa a depender do DE 500 e a '
        'ordem muda.',
        'Data de operação do reservatório: preencher a célula C13 quando houver (licitação do reservatório).',
        'Distância do canteiro: a obra começa longe do canteiro (a Zona 11 fica entre '
        f"{min(float(rede06[t['R']].get('DIST. CANTEIRO') or 0) for t in T if t['loc'] == 'Zona11'):.1f} e "
        f"{max(float(rede06[t['R']].get('DIST. CANTEIRO') or 0) for t in T if t['loc'] == 'Zona11'):.1f}".replace('.', ',')
        + ' na DIST. CANTEIRO da 06.1); o deslocamento não está no modelo.']),
    ('ABAS', [('BM POR EQUIPE', 'o BM vertical com um bloco por equipe: quantidade e valor de cada item em cada medição'),
              ('BM CONSOLIDADO', 'o BM horizontal (juntada) somando as equipes, com o resumo de BDI e K'),
              ('CRONOGRAMA FF', 'o cronograma físico-financeiro no modelo da Caesb, por grupo'),
              ('RESUMO POR EQUIPE', 'faturamento mensal por equipe, produção física e gráficos'),
              ('PROGRAMAÇÃO', 'datas de cada trecho e de cada caixa (mesmas do Project), com a ligação ao reservatório e a carga'),
              ('CARGA', 'zonas na ordem da água, caminho até a saída do reservatório, dependências, km ligados e não '
                        'ligados mês a mês, exceções e setores')]),
]

# ---------------------------------------------------------------- arquivos
x = f"{SAIDA}/{CEN['arquivo']}.xlsx"
info = xlsx_rev01.gerar(x, CEN, pl, livro, origem, itens, A, quadro, textos)
P = projeto_rev01.montar(pl, CEN, A)
ruins, sem, nlinks = projeto_rev01.conferir(P)
assert not ruins and not sem, (ruins, sem)
n = GP.xml(P, pl, CEN, f"{SAIDA}/{CEN['arquivo']}.xml", criacao=dt.datetime(2026, 10, 30, 12, 0))
resumo = [('Produtividade das frentes de rede (depois do reajuste)', '90,0 m/dia'),
          ('Fim da obra', f"{r1['fim']:%d/%m/%Y}"),
          ('Folga (+) ou atraso (−) no prazo', f"{(PRAZO - r1['fim']).days} dias (REV00: {(PRAZO - r0['fim']).days})"),
          ('Fim da Subadutora', d(pl['fim_subadutora'])),
          ('Faturado até jan/2027 (P0)', f"R$ {r1['antes'] / 1e6:.2f} mi (REV00: {r0['antes'] / 1e6:.2f})".replace('.', ',')),
          ('Maior mês (P0)', f"{MES[livro.meses[r1['pico']][1].month]}/{livro.meses[r1['pico']][1]:%y}: R$ {r1['v_pico'] / 1e6:.2f} mi".replace('.', ',')),
          ('Outubro/2026 (P0)', f"R$ {r1['out'] / 1e3:,.0f} mil".replace(',', '.')),
          ('Prontos antes de ligados ao reservatório', f"{r1['nl_n']} trechos, {km(r1['nl_km'])}"),
          ('Operação do reservatório', 'a definir')]
open(f"{SAIDA}/{CEN['arquivo']}_GANTT.html", 'w', encoding='utf-8').write(gantt_rev01.html(pl, CEN, A, resumo))
print('REV01', 'fim', r1['fim'], 'até jan/27', round(r1['antes']), 'outubro', round(r1['out']), 'pico', r1['pico_txt'],
      round(r1['v_pico']), 'total', round(sum(val)), '| REV00 fim', r0['fim'], 'até jan/27', round(r0['antes']))
print('prontos antes de ligados:', r1['nl_n'], 'trechos', round(r1['nl_km'], 2), 'km; km×mês não ligados',
      round(r1['nl_kmmes'], 2), '| REV00:', r0['nl_n'], round(r0['nl_km'], 2), round(r0['nl_kmmes'], 2))
print('Project:', n, 'tarefas; predecessoras dos marcos "em carga":', dict(nlinks))
print('ok', x)
