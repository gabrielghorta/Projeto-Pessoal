# Cronograma físico executivo base

Scripts que geram o cronograma físico executivo base do Morro da Cruz (REV00, 29/10/2026) a partir das planilhas
oficiais (`../planilhas/`) e do mapa REV02 (`../mapa/`). Não fazem parte do web app.

```bash
bash gerar_tudo.sh            # os dois cenários e a animação em ./saida (fora do Git)
```

| Arquivo | O que faz |
|---|---|
| `motor.py` | Calendário (seg a sex, 7h às 17h, feriados nacionais e do DF), equipes, premissas e a programação trecho a trecho e caixa a caixa |
| `faturamento.py` | Distribui cada item do BM vertical pelas equipes e pelos meses |
| `gerar_xlsx.py` | Planilha no modelo do BM, por equipe (premissas, BM por equipe, consolidado, cronograma FF, resumo, programação) |
| `gerar_project.py` | XML do MS Project (MSPDI) com linha de base |
| `gantt.py`, `pdf.js` | Gantt resumido em HTML e a impressão em PDF A3 |
| `animacao_dados.py`, `animacao_modelo.html` | Animação do Mapa iluminado pelos dois cenários, em HTML independente |
| `gerar.py`, `gerar_tudo.sh` | Gera tudo |

Premissas, decisões, resultados e como abrir o XML no Project: `.claude/skills/sistema-morro-da-cruz/references/cronograma-executivo.md`
(na raiz do repositório).
