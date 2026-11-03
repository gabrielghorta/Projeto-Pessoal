"""Cores da REV01 (Gantt, planilha e animação), uma legenda de cada vez.

Conferidas em 30/10/2026: em cada legenda, todo par de cores tem diferença CIEDE2000 de pelo menos 20 (com as linhas do
reajuste e do término incluídas), e as categorias passam no validador da skill dataviz (validate_palette.js) no fundo
escuro da animação (#0D0F11) e no branco do Gantt, com todos os pares: faixa de luminosidade, croma mínimo, separação
para daltonismo (protan/deutan ≥ 8) e diferença em visão normal (≥ 15). As zonas não têm cor: o número de cada uma
fica escrito no mapa (11 matizes bem separadas não cabem junto das equipes e das situações).
"""
# equipes: menor par CIEDE2000 = 20,3 (Empreiteiro 1 - Equipe A × linha do término)
EQUIPES = {'ANK1': '#21A4B1', 'E1A': '#CA460D', 'E1B': '#AE903C', 'E2C': '#388149', 'E2D': '#8F73F5', 'ANK2': '#A75791'}
# situação de cada trecho na animação: menor par CIEDE2000 = 22,7 (em execução × linha do término)
SITUACOES = {'nao_iniciado': '#6E6E6E', 'execucao': '#BA5C1F', 'nao_ligado': '#9465A3', 'ligado': '#A09809',
             'carga': '#26A7AD'}
NOME_SITUACAO = {'nao_iniciado': 'não iniciado', 'execucao': 'em execução',
                 'nao_ligado': 'executado, não ligado ao reservatório',
                 'ligado': 'executado, ligado ao reservatório (aguardando água)', 'carga': 'em carga'}
# linhas da régua do tempo: não repetem nenhuma categoria
REAJUSTE, TERMINO, CURSOR = '#1A97F4', '#E75E6A', '#EEF1F3'
# neutros: canteiro e administração local (planilha e Gantt), caixas na animação (contorno, obra civil pronta, montada)
CANTEIRO = '#8C8C8C'
CAIXA_PRONTA, CAIXA_MONTADA = '#A9AFB6', '#F4F6F8'
