#!/bin/bash
# REV01 do cronograma (30/10/2026), só o cenário B: xlsx, XML do MS Project, Gantt em PDF A3 e a animação.
# Uso: bash gerar_rev01.sh [PASTA_DE_SAIDA]   (padrão: ./saida, fora do Git)
#
# Opcionais, cada um só roda se existir no computador:
#   - Node com Playwright: imprime o Gantt em PDF (senão fica o _GANTT.html, que o navegador imprime em A3 deitado);
#   - MPXJ (pip install mpxj, precisa de Java) com MPXJ=1: regrava o XML pelo leitor/gravador do MPXJ e confere que ele
#     relê o arquivo (o marco do reservatório continua manual e sem data);
#   - LibreOffice: conferir_rev01.py recalcula a planilha com a data do reservatório em branco e com uma data de teste.
set -e
AQUI="$(cd "$(dirname "$0")" && pwd)"
SAIDA="$(mkdir -p "${1:-$AQUI/saida}" && cd "${1:-$AQUI/saida}" && pwd)"
cd "$AQUI"
python3 gerar_rev01.py "$SAIDA"
python3 animacao_rev01.py "$SAIDA/AVANCO_MORRO_DA_CRUZ_REV01_ANIMACAO.html"
if node -e "require('playwright')" 2>/dev/null; then
  node pdf.js "$SAIDA"/*REV01*_GANTT.html && rm -f "$SAIDA"/*REV01*_GANTT.html
fi
if [ "${MPXJ:-0}" = 1 ]; then
  python3 - "$SAIDA" <<'PY'
import glob, sys
import jpype, mpxj  # noqa: F401
jpype.startJVM()
from jpype import JClass
R, W = JClass('net.sf.mpxj.mspdi.MSPDIReader'), JClass('net.sf.mpxj.mspdi.MSPDIWriter')
for f in sorted(glob.glob(sys.argv[1] + '/*REV01*.xml')):
    W().write(R().read(f), f)
    p = R().read(f)
    res = next(t for t in p.getTasks() if 'RESERVATÓRIO EM OPERAÇÃO' in str(t.getName()))
    print(f, 'MPXJ:', p.getTasks().size(), 'tarefas, fim', p.getProjectProperties().getFinishDate(),
          '| reservatório:', res.getTaskMode(), 'início', res.getStart())
PY
fi
python3 conferir_rev01.py "$SAIDA" || echo "ATENÇÃO: veja os PROBLEMAS acima"
ls -la "$SAIDA"
