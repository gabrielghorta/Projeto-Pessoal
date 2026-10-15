"""Substituído por importar.py (carga não destrutiva, com simulação, backup verificado e proveniência).

O seed.py antigo apagava o banco antes de carregar; isso destruía movimentos, fotos e medições.
"""
import sys

if __name__ == "__main__":
    sys.exit("seed.py foi substituído. Use:\n  python importar.py            (simulação, não altera nada)\n"
             "  python importar.py --aplicar  (backup verificado + importação)")
