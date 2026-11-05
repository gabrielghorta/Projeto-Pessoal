#!/usr/bin/env python3
"""Robustez do ns_parser: variantes sintetizadas como TEXTO a partir do texto real extraído da NS 006.

Uso: python3 -I testes_variantes.py <pasta ns006>
Para cada variante: o que se espera, o que saiu, e a classificação:
  OK                 dado certo, sem alarme indevido
  OK+AVISO           dado certo, mas pede conferência (aviso/incerto) — aceitável
  QUEBRA_DETECTADA   dado errado ou faltando, mas alguma conferência acusa (ERRO/AVISO) — a NS volta para revisão
  QUEBRA_SILENCIOSA  dado errado e nada acusa — o pior caso
"""
import json
import os
import sys

PASTA = sys.argv[1]
sys.path.insert(0, PASTA)
import ns_parser_prototipo as P  # noqa: E402

OUT = os.path.join(PASTA, 'variantes')
os.makedirs(OUT, exist_ok=True)

pg_pypdf, meta_pypdf = P.extrair_paginas(os.path.join(PASTA, 'topografia.pdf'), 'pypdf')
pg_pdft, meta_pdft = P.extrair_paginas(os.path.join(PASTA, 'topografia.pdf'), 'pdftotext')
pg_ns_pypdf, _ = P.extrair_paginas(os.path.join(PASTA, 'ns.pdf'), 'pypdf')
BASE = {'pypdf': (pg_pypdf[0], {'posicoes_fieis': False}), 'pdftotext': (pg_pdft[0], {'posicoes_fieis': True}),
        'pypdf_ns': (pg_ns_pypdf[0], {'posicoes_fieis': False})}
REF = P.parse_texto([pg_pypdf[0]], {'posicoes_fieis': False, 'paginas': 1})
IMPRESSAO_REF = REF['impressao_dados']
REF.update(P.verificar(REF, hoje='2026-10-20'))
BASE_NOK = {v['id'] for v in REF['verificacoes'] if not v['ok']}      # V06 (fiscalização em branco) já vem da NS 006


# ------------------------------------------------------------------ utilidades de edição de texto
def acha(ls, contem, ocorr=0, linha_dados=True):
    idx = [i for i, l in enumerate(ls) if contem in l and (not linha_dados or P.RX_ESTACA.match(l))]
    return idx[ocorr]


def troca_tok(l, k, novo):
    """Troca a k-ésima célula (0 inteira, 1 '+', 2 fração, 3 elemento, 4 terreno, 5 GI, 6 prof, 7 método,
    8 material, 9 parcial, 10 acumulada, 11 boca, 12 fundo, 13 visor, 14 cruzeta, 15 obs); '' = célula vazia."""
    t = P.tokens(l)[k]
    w = t.b - t.a
    novo = novo.center(w) if len(novo) <= w else novo
    return l[:t.a] + novo + l[t.b:]


def editar(pag, contem, trocas, ocorr=0):
    ls = pag.split('\n')
    i = acha(ls, contem, ocorr)
    for k, novo in sorted(trocas.items(), reverse=True):     # da direita para a esquerda: posições estáveis
        ls[i] = troca_tok(ls[i], k, novo)
    return '\n'.join(ls)


def subst(pag, velho, novo, n=1):
    assert velho in pag, velho
    return pag.replace(velho, novo, n)


def linha(ns, gi, chave, ocorr=0):
    return [l for l in ns['grupos'][gi]['linhas'] if l['chave'] == chave][ocorr]


def rodar(paginas, fieis, **regras):
    ns = P.parse_texto(paginas, {'posicoes_fieis': fieis, 'paginas': len(paginas)})
    ns.update(P.verificar(ns, hoje='2026-10-20', **regras))
    return ns


def nok(ns):
    return [v['id'] for v in ns['verificacoes'] if not v['ok']]


RESULT = []


def caso(nome, descricao, paginas, fieis, esperado, **regras):
    """esperado(ns) -> (dado_certo: bool, detalhe: str)."""
    try:
        ns = rodar(paginas, fieis, **regras)
    except Exception as e:  # noqa: BLE001
        RESULT.append((nome, descricao, 'EXCECAO', f'{type(e).__name__}: {e}', []))
        return None
    certo, det = esperado(ns)
    falhas = nok(ns)
    alarme = bool(set(falhas) - BASE_NOK) or bool(ns['falhas_leitura']) or any(l.get('incerto') for g in ns['grupos'] for l in g['linhas'])
    if certo:
        cls = 'OK+AVISO' if alarme else 'OK'
    else:
        cls = 'QUEBRA_DETECTADA' if alarme else 'QUEBRA_SILENCIOSA'
    RESULT.append((nome, descricao, cls, det, falhas))
    with open(os.path.join(OUT, f'{nome}.json'), 'w', encoding='utf-8') as f:
        json.dump(ns, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, f'{nome}.txt'), 'w', encoding='utf-8') as f:
        f.write('\n\f\n'.join(paginas))
    return ns


def campos(l, *cs):
    return {c: l.get(c) for c in cs}


# ------------------------------------------------------------------ variantes
for ext in ('pypdf', 'pdftotext'):
    base, mf = BASE[ext]
    fieis = mf['posicoes_fieis']

    # 1. linha MND: método MND, sem escavação (boca/fundo vazios), visor/cruzeta mantidos
    t = editar(base, 'PV-5 EMISSÁRIO', {7: 'MND', 11: '', 12: ''})
    caso(f'{ext}_01_mnd_sem_escavacao', 'PV-5 vira MND com boca/fundo vazios', [t], fieis,
         lambda ns: ((lambda l: (l['metodo'] == 'MND' and l['esc_boca'] is None and l['esc_fundo'] is None
                                 and l['visor'] == 0.68 and l['cruzeta'] == 3.5, campos(l, 'metodo', 'esc_boca', 'esc_fundo', 'visor', 'cruzeta', 'incerto')))
                     (linha(ns, 0, 'PV-5'))))

    # 2. linha MND só com parcial/acumulada
    t = editar(base, 'PV-5 EMISSÁRIO', {7: 'MND', 11: '', 12: '', 13: '', 14: ''})
    caso(f'{ext}_02_mnd_so_distancias', 'PV-5 MND com boca/fundo/visor/cruzeta vazios', [t], fieis,
         lambda ns: ((lambda l: (l['dist_parcial'] == 2.31 and l['dist_acumulada'] == 27.87 and
                                 all(l[c] is None for c in ('esc_boca', 'esc_fundo', 'visor', 'cruzeta')),
                                 campos(l, 'dist_parcial', 'dist_acumulada', 'esc_boca', 'esc_fundo', 'visor', 'cruzeta', 'incerto')))
                     (linha(ns, 0, 'PV-5'))))

    # 3. uma linha sem visor/cruzeta
    t = editar(base, 'PV-6 EMISSÁRIO', {13: '', 14: ''})
    caso(f'{ext}_03_sem_visor_cruzeta_1linha', 'PV-6 sem visor/cruzeta', [t], fieis,
         lambda ns: ((lambda l: (l['visor'] is None and l['cruzeta'] is None and l['esc_boca'] == 2.77 and l['esc_fundo'] == 1.4,
                                 campos(l, 'esc_boca', 'esc_fundo', 'visor', 'cruzeta', 'incerto')))
                     (linha(ns, 0, 'PV-6'))))

    # 4. TODAS as linhas sem visor/cruzeta (cara de NS de rede de água: sem greide por cruzeta)
    t = base
    for k, el in enumerate(['CAIXA DE ENTRADA - TRAT', 'PV-3 EMISS', 'PV-6 EMISS', 'PV-5 EMISS', 'PV-4 EMISS', 'PV-3 EMISS', 'PV-2 EMISS', 'PV-1 EMISS']):
        t = editar(t, el, {13: '', 14: ''}, ocorr=1 if (el == 'PV-3 EMISS' and k == 5) else 0)
    caso(f'{ext}_04_sem_visor_cruzeta_todas', 'nenhuma linha com visor/cruzeta (sem linha completa para âncora)', [t], fieis,
         lambda ns: (all(l['visor'] is None and l['cruzeta'] is None and l['esc_boca'] and l['esc_fundo'] == 1.4
                         for g in ns['grupos'] for l in g['linhas']),
                     f"âncoras={ns['colunas']['ancoras']}; incertos={sum(1 for g in ns['grupos'] for l in g['linhas'] if l.get('incerto'))}"))

    # 5. TODAS sem boca/fundo, visor/cruzeta preenchidos (o vazio fica no meio): pior caso p/ ordem
    t = base
    for k, el in enumerate(['CAIXA DE ENTRADA - TRAT', 'PV-3 EMISS', 'PV-6 EMISS', 'PV-5 EMISS', 'PV-4 EMISS', 'PV-3 EMISS', 'PV-2 EMISS', 'PV-1 EMISS']):
        t = editar(t, el, {11: '', 12: ''}, ocorr=1 if (el == 'PV-3 EMISS' and k == 5) else 0)
    caso(f'{ext}_05_sem_boca_fundo_todas', 'nenhuma linha com boca/fundo, visor/cruzeta preenchidos', [t], fieis,
         lambda ns: (all(l['esc_boca'] is None and l['visor'] is not None for g in ns['grupos'] for l in g['linhas']),
                     f"âncoras={ns['colunas']['ancoras']}; PV-6: {campos(linha(ns, 0, 'PV-6'), 'esc_boca', 'esc_fundo', 'visor', 'cruzeta')}"))

    # 6. elemento com parênteses, números e hífen (nome de rede de água)
    t = editar(base, 'PV-6 EMISSÁRIO', {3: 'NÓ 9.1 (TÊ 160x160 - DERIV. P/ VRP-15)', 15: 'NÓ 9.1 (TÊ 160x160)'})
    caso(f'{ext}_06_elemento_parenteses', 'elemento "NÓ 9.1 (TÊ 160x160 - DERIV. P/ VRP-15)"', [t], fieis,
         lambda ns: ((lambda ls: (ls[2]['elemento'] == 'NÓ 9.1 (TÊ 160x160 - DERIV. P/ VRP-15)' and ls[2]['chave'] == 'NO9.1'
                                  and ls[2]['cota_terreno'] == 1090.837 and ls[2]['cruzeta'] == 3.5,
                                  campos(ls[2], 'elemento', 'chave', 'cota_terreno', 'obs')))(ns['grupos'][0]['linhas'])))

    # 7. elemento com 2 espaços internos (vira 2 células)
    t = editar(base, 'PV-6 EMISSÁRIO', {3: 'PV-6  EMISSÁRIO DE ENTRADA'})
    caso(f'{ext}_07_elemento_2_espacos', 'elemento com 2 espaços dentro do nome', [t], fieis,
         lambda ns: ((lambda l: (l['elemento'] == 'PV-6 EMISSÁRIO DE ENTRADA' and l['cota_terreno'] == 1090.837,
                                 campos(l, 'elemento', 'cota_terreno')))(ns['grupos'][0]['linhas'][2])))

    # 8. célula do elemento quebrada em 2 linhas (texto que não coube): parte de baixo na linha seguinte
    ls = base.split('\n')
    i = acha(ls, 'PV-1 EMISSÁRIO')
    tk = P.tokens(ls[i])[3]
    ls[i] = troca_tok(ls[i], 3, 'PV-1 EMISSÁRIO DE ENTRADA')
    ls.insert(i + 1, ' ' * (tk.a + 6) + '(SOBRE A REDE EXISTENTE)')
    caso(f'{ext}_08_elemento_quebrado_abaixo', 'elemento em 2 linhas (continuação abaixo, dentro da coluna)', ['\n'.join(ls)], fieis,
         lambda ns: ((lambda l: (l['elemento'] == 'PV-1 EMISSÁRIO DE ENTRADA (SOBRE A REDE EXISTENTE)' and len(ns['grupos']) == 2,
                                 f"elemento={l['elemento']!r}; grupos={len(ns['grupos'])}"))(ns['grupos'][-1]['linhas'][-1])))

    # 9. idem, com a primeira parte ACIMA da linha dos números (Excel centraliza vertical)
    ls = base.split('\n')
    i = acha(ls, 'PV-1 EMISSÁRIO')
    tk = P.tokens(ls[i])[3]
    ls[i] = troca_tok(ls[i], 3, '(SOBRE A REDE EXISTENTE)')
    ls.insert(i, ' ' * (tk.a + 6) + 'PV-1 EMISSÁRIO DE ENTRADA')
    caso(f'{ext}_09_elemento_quebrado_acima', 'elemento em 2 linhas (começo acima da linha dos números)', ['\n'.join(ls)], fieis,
         lambda ns: ((lambda l: (l['elemento'] == 'PV-1 EMISSÁRIO DE ENTRADA (SOBRE A REDE EXISTENTE)' and len(ns['grupos']) == 2,
                                 f"elemento={l['elemento']!r}; grupos={[g['titulo'][:30] for g in ns['grupos']]}"))(ns['grupos'][-1]['linhas'][-1])))

    # 10. duas folhas: FOLHA 01 de 02 (grupo 1) e FOLHA 02 de 02 (grupo 2 + notas + resumo + assinaturas)
    ls = base.split('\n')
    i_g2 = next(i for i, l in enumerate(ls) if 'COLETOR SECUNDÁRIO' in l and not P.RX_ESTACA.match(l) and 'TUBO' not in l)
    i_cab_fim = next(i for i, l in enumerate(ls) if P.RX_SUBCAB.search(l))
    i_ass = next(i for i, l in enumerate(ls) if l.strip().startswith('TOPOGRAFIA:'))
    cab = [l.replace('01 de 01', '01 de 02') for l in ls[:i_cab_fim + 1]]
    p1 = cab + ls[i_cab_fim + 1:i_g2] + [''] * 3 + ls[i_ass:]
    p2 = [l.replace('01 de 02', '02 de 02') for l in cab] + [''] + ls[i_g2:]
    caso(f'{ext}_10_duas_folhas', 'NS em 2 folhas, cabeçalho repetido, grupo 2 na folha 2', ['\n'.join(p1), '\n'.join(p2)], fieis,
         lambda ns: (ns['impressao_dados'] == IMPRESSAO_REF and [f['folha'] for f in ns['folhas']] == [1, 2],
                     f"mesma impressão da NS de 1 folha: {ns['impressao_dados'] == IMPRESSAO_REF}; folhas={[(f['folha'], f['total_folhas']) for f in ns['folhas']]}"))

    # 11. grupo 1 partido entre as folhas, SEM repetir o título na folha 2
    i_pv5 = acha(ls, 'PV-5 EMISSÁRIO')
    p1 = cab + ls[i_cab_fim + 1:i_pv5] + [''] * 3 + ls[i_ass:]
    p2 = [l.replace('01 de 02', '02 de 02') for l in cab] + [''] + ls[i_pv5:]
    caso(f'{ext}_11_grupo_partido_sem_titulo', 'grupo 1 continua na folha 2 sem título', ['\n'.join(p1), '\n'.join(p2)], fieis,
         lambda ns: (ns['impressao_dados'] == IMPRESSAO_REF, f"grupos={[(g['titulo'][:25], len(g['linhas'])) for g in ns['grupos']]}"))

    # 12. idem, repetindo o título com "(CONTINUAÇÃO)"
    tit = next(l for l in ls if 'COLETOR PRINCIPAL' in l)
    p2b = [l.replace('01 de 02', '02 de 02') for l in cab] + ['', tit.rstrip() + ' (CONTINUAÇÃO)', ''] + ls[i_pv5:]
    caso(f'{ext}_12_grupo_partido_continuacao', 'grupo 1 continua na folha 2 com "(CONTINUAÇÃO)"', ['\n'.join(p1), '\n'.join(p2b)], fieis,
         lambda ns: (ns['impressao_dados'] == IMPRESSAO_REF, f"grupos={[(g['titulo'][:25], len(g['linhas'])) for g in ns['grupos']]}"))

    # 13. só a folha 1 de 2 enviada
    caso(f'{ext}_13_falta_folha', 'enviada só a FOLHA 01 de 02', ['\n'.join(p1)], fieis,
         lambda ns: (False, 'NS incompleta: deve ser recusada (E02)'))

    # 14. estaca colada "0+17,32"
    t = editar(base, 'PV-3 EMISSÁRIO', {0: '', 1: '', 2: '0+17,32'})
    caso(f'{ext}_14_estaca_colada', 'estaca escrita "0+17,32"', [t], fieis,
         lambda ns: ((lambda l: (l['estaca_m'] == 17.32 and l['cota_terreno'] == 1089.324, campos(l, 'estaca_m', 'cota_terreno')))
                     (ns['grupos'][0]['linhas'][1])))

    # 15. número inteiro numa célula ("3" em vez de "3,50")
    t = editar(base, 'PV-4 EMISSÁRIO', {14: '3'})
    caso(f'{ext}_15_inteiro_na_celula', 'cruzeta "3" sem casas decimais', [t], fieis,
         lambda ns: ((lambda l: (l['cruzeta'] == 3.0 and l['visor'] == 0.86, campos(l, 'visor', 'cruzeta')))(linha(ns, 0, 'PV-4'))))

    # 16. texto no lugar de número ("ver obs" na profundidade)
    t = editar(base, 'PV-4 EMISSÁRIO', {6: 'ver obs'})
    caso(f'{ext}_16_texto_na_celula', '"ver obs" na coluna profundidade', [t], fieis,
         lambda ns: (False, f"falhas={ns['falhas_leitura'][:1]}; PV-4 prof={linha(ns, 0, 'PV-4')['profundidade']}"))

    # 17. linha sem método (V.C.A vazio): referência passa a ser o material
    t = editar(base, 'PV-2 EMISSÁRIO', {7: ''})
    caso(f'{ext}_17_sem_metodo', 'PV-2 sem método executivo', [t], fieis,
         lambda ns: ((lambda l: (l['metodo'] is None and l['profundidade'] == 2.13 and l['visor'] == 0.87,
                                 campos(l, 'metodo', 'profundidade', 'visor', 'incerto')))(linha(ns, 1, 'PV-2'))))

    # 18. linha sem método e sem material: números pela ordem
    t = editar(base, 'PV-2 EMISSÁRIO', {7: '', 8: '', 11: '', 12: ''})
    caso(f'{ext}_18_sem_metodo_material', 'PV-2 sem método, material, boca e fundo', [t], fieis,
         lambda ns: ((lambda l: (l['esc_boca'] is None and l['visor'] == 0.87, campos(l, 'esc_boca', 'esc_fundo', 'visor', 'cruzeta', 'incerto')))
                     (linha(ns, 1, 'PV-2'))))

    # 19. erros de conteúdo que as conferências precisam pegar
    l_res = next(l for l in base.split('\n') if 'TUBO PEAD 1000mm' in l)
    caso(f'{ext}_19_resumo_errado', 'RESUMO 1000mm = 31,49 (soma das parciais é 30,49)', [subst(base, l_res, l_res.replace('30,49', '31,49'))], fieis,
         lambda ns: (False, f"conferências que acusam: {nok(ns)}"))
    caso(f'{ext}_20_segmento_errado', 'segmento "PV6 ----> PV3 = 8,42" (parcial 8,24)', [subst(base, 'PV6 ----> PV3 = 8,24', 'PV6 ----> PV3 = 8,42')], fieis,
         lambda ns: (False, f"conferências que acusam: {nok(ns)}"))
    caso(f'{ext}_21_acumulada_errada', 'acumulada do PV-6 = 25,65 (certo 25,56)', [editar(base, 'PV-6 EMISSÁRIO', {10: '25,65'})], fieis,
         lambda ns: (False, f"conferências que acusam: {nok(ns)}"))
    caso(f'{ext}_22_profundidade_errada', 'profundidade do PV-5 = 2,28 (terreno - GI = 2,82)', [editar(base, 'PV-5 EMISSÁRIO', {6: '2,28'})], fieis,
         lambda ns: (False, f"conferências que acusam: {nok(ns)}"))
    sem_seg = '\n'.join(l for l in base.split('\n') if 'PV5 ----> PV6' not in l)
    caso(f'{ext}_23_falta_segmento', 'linha "PV5 ----> PV6" apagada', [sem_seg], fieis,
         lambda ns: (True, f"conferências que acusam: {nok(ns)}"))
    caso(f'{ext}_24_segmento_sem_metros', 'linha "PV5 ----> PV6" sem "= x metros"', [subst(base, 'PV5 ----> PV6 = 2,31 metros', 'PV5 ----> PV6')], fieis,
         lambda ns: (True, f"falhas={ns['falhas_leitura']}"))

    # 25. regras da obra: contrato certo -> aceita; data futura -> recusa
    t = subst(base, '9702/2024', '10239/2026')
    caso(f'{ext}_25_contrato_da_obra', 'contrato 10239/2026 (o da obra)', [t], fieis,
         lambda ns: (ns['resultado']['aceita'], f"aceita={ns['resultado']['aceita']} erros={ns['resultado']['motivos']}"),
         contrato_obra='CT 10239/2026 Caesb × Ankara')
    caso(f'{ext}_26_data_futura', 'data 27-out-27 (futura)', [subst(t, '27-out-25', '27-out-27')], fieis,
         lambda ns: (False, f"motivos={ns['resultado']['motivos']}"), contrato_obra='10239/2026')
    caso(f'{ext}_27_data_antes_contrato', 'NS de 2025 em contrato de 2026', [t], fieis,
         lambda ns: (True, f"conferências que acusam: {nok(ns)}"), contrato_obra='10239/2026', inicio_contrato='2026-03-01')
    caso(f'{ext}_28_data_numerica', 'data "27/10/2025"', [subst(t, '27-out-25', '27/10/2025')], fieis,
         lambda ns: (ns['cabecalho']['data'] == '2025-10-27', f"data={ns['cabecalho']['data']}"))
    caso(f'{ext}_29_rotulo_ns_diferente', 'rótulo "N.S. Nº:" em vez de "NS nº :"', [subst(t, 'NS nº :', 'N.S. Nº:')], fieis,
         lambda ns: (ns['cabecalho']['numero'] == '006', f"numero={ns['cabecalho']['numero']} motivos={ns['resultado']['motivos']}"))

# 30. cabeçalho com valor ANTES do rótulo (ns.pdf no pypdf: "006NS nº :", "01 de 01FOLHA:") + RESUMO colado
caso('pypdf_ns_30_valor_antes_rotulo', 'ns.pdf/pypdf: "006NS nº :", "01 de 01FOLHA:", RESUMO "...)40,22"', [BASE['pypdf_ns'][0]], False,
     lambda ns: (ns['impressao_dados'] == IMPRESSAO_REF, f"numero={ns['cabecalho']['numero']} folha={ns['cabecalho']['folha']} resumo={[r['metros'] for r in ns['resumo']]}"))

# ------------------------------------------------------------------ NS de REDE DE ÁGUA sintética (nomes reais da 06.1)
def linha_fix(cols):
    """Monta uma linha com células em colunas fixas (como o pdftotext)."""
    s = ''
    for col, txt, al in cols:
        txt = str(txt)
        ini = col if al == 'l' else col - len(txt) if al == 'r' else col - len(txt) // 2
        ini = max(ini, len(s) + 2 if s else ini)
        s = s.ljust(ini) + txt
    return s


# centros medidos das colunas no pdftotext da topografia.pdf (inteira, +, fração, elemento, terreno, GI, prof, método,
# material, parcial, acumulada, boca, fundo, visor, cruzeta, observação)
C = [(c, 'c') for c in (4, 14, 24, 58, 91, 104, 121, 135, 148, 158, 173, 185, 196, 207, 223, 266)]


def lin(vals):
    return linha_fix([(c, v, a[0] if a != 'c' else 'c') for (c, a), v in zip(C, vals) if v != ''])


cab_agua = pg_pdft[0].split('\n')
i_cab_fim = next(i for i, l in enumerate(cab_agua) if P.RX_SUBCAB.search(l))
cab_agua = '\n'.join(cab_agua[:i_cab_fim + 1])
cab_agua = (cab_agua.replace('9702/2024', '10239/2026').replace('27-out-25', '15-out-26')
            .replace('TRATAMENTO PRELIMINAR - ETE - ESTAÇÃO DE TRATAMENTO DE ESGOTOS PARANOÁ/DF',
                     'REDE DE DISTRIBUIÇÃO DE ÁGUA - MORRO DA CRUZ - SÃO SEBASTIÃO/DF')
            .replace('"EMISSÁRIO DE ENTRADA" - TRATAMENTO PRELIMINAR - ETE PARANOÁ/DF - VER CROQUI ANEXO - VER PROJETO EXECUTIVO',
                     '"REDE DE ÁGUA" - ZONA 03 - PB08 - VER CROQUI ANEXO - VER PROJETO EXECUTIVO'))
TIT = 'REDE ZONA 03 - PB08 - PEAD DE 160 (NÓ6.1 - NÓ9.1 - VRP-15)'
agua = cab_agua + '\n\n\n\n' + ' ' * 98 + TIT + '\n' + '\n'.join([
    lin(['0', '+', '0,00', 'NÓ6.1 - TÊ 160x110', '1.012,450', '1.011,250', '1,20', 'V.C.A', 'PEAD-160', '0,00', '0,00', '0,60', '0,60', '', '', 'NÓ6.1']),
    ' ' * 40 + 'NÓ9.1 ----> NÓ6.1 = 277,99 metros',
    lin(['13', '+', '17,99', 'NÓ9.1 - TÊ 160x160', '1.009,870', '1.008,620', '1,25', 'V.C.A', 'PEAD-160', '277,99', '277,99', '0,60', '0,60', '', '', 'NÓ9.1']),
    ' ' * 40 + 'VRP-15 ----> NÓ9.1 = 295,98 metros',
    lin(['28', '+', '13,97', 'CH_VRP-15 (CAIXA DA VRP)', '1.004,300', '1.003,000', '1,30', 'V.C.A', 'PEAD-160', '295,98', '573,97', '0,60', '0,60', '', '', 'VRP-15']),
    '', '', ' ' * 47 + 'NOTAS',
    ' ' * 17 + 'NÓ9.1         TÊ PEAD DE 160x160 ELETROFUSÃO',
    ' ' * 17 + 'VRP-15        CAIXA DE VRP "PADRÃO CAESB"',
    '', '', ' ' * 142 + 'RESUMO',
    ' ' * 143 + 'TUBO PEAD 160mm            573,97      metros               ' + TIT,
    '', ' ' * 197 + 'TOTAL GERAL         =      573,97      metros', '', '',
    'TOPOGRAFIA:' + ' ' * 75 + 'CONSTRUTORA ANKARA' + ' ' * 62 + 'Fiscalização: CONCREMAT' + ' ' * 33 + 'Fiscalização: CAESB',
    'Eng°. FULANO TOPOGRAFO' + ' ' * 64 + 'Eng° [NOME DO ENGENHEIRO DA CONSTRUTORA]' + ' ' * 54 + 'Eng°.' + ' ' * 51 + 'Eng°.',
    'CREA: 000000/D-DF' + ' ' * 69 + 'CREA: [CREA]' + ' ' * 63 + 'CREA:' + ' ' * 51 + 'CREA:'])
ns_agua = caso('agua_31_rede_zona03_pb08', 'NS de água sintética: NÓ6.1 -> NÓ9.1 -> CH_VRP-15, sem visor/cruzeta', [agua], True,
               lambda ns: (ns['resultado']['aceita'] and ns['grupos'][0]['linhas'][2]['chave'] == 'VRP-15'
                           and all(l['visor'] is None for l in ns['grupos'][0]['linhas']),
                           f"aceita={ns['resultado']['aceita']} chaves={[l['chave'] for l in ns['grupos'][0]['linhas']]} "
                           f"ctx={P.contexto_zona_pb(ns['cabecalho']['titulo'], ns['grupos'][0]['titulo'])} avisos={nok(ns)}"),
               contrato_obra='CT 10239/2026 Caesb × Ankara')
with open(os.path.join(OUT, 'agua_31_texto.txt'), 'w', encoding='utf-8') as f:
    f.write(agua)

# 32. PDF digitalizado (só imagem): gerado a partir de ns-1.png
try:
    from PIL import Image
    pdf_img = os.path.join(OUT, 'ns_digitalizada.pdf')
    Image.open(os.path.join(PASTA, 'ns-1.png')).convert('RGB').save(pdf_img, 'PDF', resolution=100.0)
    try:
        P.ler_ns(pdf_img)
        RESULT.append(('pdf_32_digitalizado', 'PDF só com imagem (digitalizado)', 'QUEBRA_SILENCIOSA', 'leu algo de um PDF sem texto?', []))
    except ValueError as e:
        RESULT.append(('pdf_32_digitalizado', 'PDF só com imagem (digitalizado)', 'OK', f'recusado: {e}', []))
except ImportError:
    RESULT.append(('pdf_32_digitalizado', 'PDF só com imagem', 'NAO_TESTADO', 'sem Pillow', []))

# ------------------------------------------------------------------ relatório
larg = max(len(r[0]) for r in RESULT)
for nome, desc, cls, det, falhas in RESULT:
    print(f'{nome:<{larg}}  {cls:<17}  {desc}')
    print(f'{"":<{larg}}  {"":<17}  -> {det}' + (f' | conferências não ok: {falhas}' if falhas else ''))
cont = {}
for r in RESULT:
    cont[r[2]] = cont.get(r[2], 0) + 1
print('\nRESUMO:', cont)
with open(os.path.join(OUT, '_resumo.json'), 'w', encoding='utf-8') as f:
    json.dump([{'variante': r[0], 'descricao': r[1], 'classe': r[2], 'detalhe': str(r[3]), 'conferencias_nao_ok': r[4]}
               for r in RESULT], f, ensure_ascii=False, indent=1)
