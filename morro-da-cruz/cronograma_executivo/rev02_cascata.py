"""Uma etapa da cascata REV01 → REV02: as mudanças da REV02, uma de cada vez e acumulando (gerar_rev02.py roda cada
etapa num processo, porque o calendário com chuva muda o processo inteiro).

    python3 rev02_cascata.py N      (N = 0 a 7; imprime: N|mudança|fim da obra|folga|fim da Subadutora|Zona 11 pronta|
                                     trechos prontos antes de ligados)
"""
import sys

import motor
import motor_rev01 as M1
import rev02

PASSOS = ['emp2', 'chuva', 'prod_por_de', 'entrada_meia_dias', 'troca_frente_dias', 'ligacoes_por_dia', 'caminho']
n = int(sys.argv[1])
ativos = PASSOS[:n]
rev02.preparar(chuva='chuva' in ativos, emp2='emp2' in ativos)
op = {k: v for k, v in rev02.OPCOES.items() if k in ativos}
if 'caminho' in ativos:
    op.update(hidro_caminho_antes=True, interlig_por_caminho=True)
D, rede, _ = motor.ler_dados()
pl = M1.programar(D, rede, 90.0, op)
C = motor.CAL
det = M1.carga_detalhe(pl)
z11 = max(det[i]['pronto'] for i in range(len(pl['T'])) if M1.frente_de(pl['T'][i]) == 'Zona11')
print(f"{n}|{PASSOS[n - 1] if n else 'REV01'}|{C.data_fim(pl['fim'])}|{(motor.PRAZO - C.data_fim(pl['fim'])).days}|"
      f"{C.data_fim(pl['fim_subadutora'])}|{C.data_fim(z11)}|{len(M1.nao_ligados(pl))}")
