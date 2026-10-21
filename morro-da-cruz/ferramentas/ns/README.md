# Leitor da Nota de Serviço — protótipo

Protótipo da pesquisa de 20/10/2026 (ver `docs/ns/`). **Não é usado pelo sistema**: serve de ponto de partida para o
leitor definitivo da Nota de Serviço (NS) por upload.

- `ns_parser_prototipo.py` — lê o PDF da NS (pypdf no modo layout, com a correção da página girada; `pdftotext` como
  segunda leitura se existir), monta cabeçalho, grupos, linhas, segmentos, RESUMO e assinaturas e faz as conferências
  (contrato, folhas, profundidade = terreno − GI, acumulada, soma das parciais = RESUMO = TOTAL GERAL).
  Uso: `python3 -I ns_parser_prototipo.py NS.pdf -o saida.json --contrato-obra "CT 10239/2026"`; `--texto pag1.txt` para testes.
- `testes_variantes.py` — 61 variantes sintéticas em texto (linhas MND, folhas, células quebradas, RESUMO colado…).
- `demo_casamento.py` — casamento dos segmentos da NS com o trecho físico (interface de `topologia.py`).

Os PDFs de exemplo (NS 006, de outra obra, e o croqui) **não** ficam no Git: o repositório é público e eles têm nome e
CREA de pessoas. Estão com o responsável (Drive da obra).
