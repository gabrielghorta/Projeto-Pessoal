"""Onde ficam os arquivos do programa e os dados da obra.

* Rodando pelo código (python server.py / iniciar.py): tudo na pasta do código, como sempre.
* Rodando pelo executável (MorroDaCruz.exe, PyInstaller): o programa (web/, schema.sql e a configuração padrão) vem de
  dentro do executável; os DADOS (planilhas/, mapa/, config/, dados/, dados_demo/) ficam na pasta onde está o .exe,
  para sobreviver a atualizações do programa.
"""
import os
import sys

CONGELADO = bool(getattr(sys, "frozen", False))
CODIGO = os.path.dirname(os.path.abspath(__file__))
RECURSOS = getattr(sys, "_MEIPASS", CODIGO)                                   # web/, schema.sql, config padrão
PASTA = os.path.dirname(os.path.abspath(sys.executable)) if CONGELADO else CODIGO   # dados da obra
