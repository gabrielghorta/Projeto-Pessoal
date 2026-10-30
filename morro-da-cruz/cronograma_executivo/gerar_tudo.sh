#!/bin/bash
# Cronograma físico executivo base: os dois cenários (xlsx no modelo do BM por equipe, XML do MS Project e Gantt em PDF)
# e a animação do Mapa iluminado. Uso: bash gerar_tudo.sh [PASTA_DE_SAIDA]   (padrão: ./saida, fora do Git)
#
# Opcionais, cada um só roda se existir no computador:
#   - Node com Playwright: imprime o Gantt em PDF (senão fica o _GANTT.html, que o navegador imprime em A3 deitado);
#   - MPXJ (pip install mpxj, precisa de Java) com MPXJ=1: regrava o XML pelo leitor/gravador do MPXJ, o formato que o
#     Project abre com menos queixa, e confere que ele relê o arquivo.
set -e
AQUI="$(cd "$(dirname "$0")" && pwd)"
SAIDA="$(mkdir -p "${1:-$AQUI/saida}" && cd "${1:-$AQUI/saida}" && pwd)"
cd "$AQUI"
python3 gerar.py "$SAIDA"
python3 animacao_dados.py "$SAIDA/AVANCO_MORRO_DA_CRUZ_ANIMACAO.html"
if node -e "require('playwright')" 2>/dev/null; then
  node pdf.js "$SAIDA"/*_GANTT.html && rm -f "$SAIDA"/*_GANTT.html
fi
if [ "${MPXJ:-0}" = 1 ]; then
  python3 - "$SAIDA" <<'PY'
import glob, sys
import jpype, mpxj  # noqa: F401
jpype.startJVM()
from jpype import JClass
R, W = JClass('net.sf.mpxj.mspdi.MSPDIReader'), JClass('net.sf.mpxj.mspdi.MSPDIWriter')
for f in sorted(glob.glob(sys.argv[1] + '/*.xml')):
    W().write(R().read(f), f)
    p = R().read(f)
    print(f, 'MPXJ:', p.getTasks().size(), 'tarefas, fim', p.getProjectProperties().getFinishDate())
PY
fi
ls -la "$SAIDA"
