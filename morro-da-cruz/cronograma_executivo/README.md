# Cronograma físico executivo

Scripts que geram o cronograma físico executivo do Morro da Cruz a partir das planilhas oficiais (`../planilhas/`) e do
mapa REV02 (`../mapa/`). Não fazem parte do web app.

- **REV00 (29/10/2026):** os dois cenários (A: prazo; B: 90 m/dia), zonas pela distância ao canteiro.
- **REV01 (30/10/2026):** só o cenário B; a obra sai do reservatório da Zona 11 e sobe com a rede (regra "ligado ao
  reservatório"). Todas as regras da REV00 continuam; muda só a ordem.

```bash
bash gerar_tudo.sh            # REV00: os dois cenários e a animação em ./saida (fora do Git)
MPXJ=1 bash gerar_rev01.sh    # REV01: xlsx, XML (regravado pelo MPXJ), Gantt em PDF, animação e as conferências
```

| Arquivo | O que faz |
|---|---|
| `motor.py` | Calendário (seg a sex, 7h às 17h, feriados nacionais e do DF), equipes, premissas e a programação trecho a trecho e caixa a caixa (REV00) |
| `faturamento.py` | Distribui cada item do BM vertical pelas equipes e pelos meses |
| `gerar_xlsx.py` | Planilha no modelo do BM, por equipe (premissas, BM por equipe, consolidado, cronograma FF, resumo, programação) |
| `gerar_project.py` | XML do MS Project (MSPDI) com linha de base |
| `gantt.py`, `pdf.js` | Gantt resumido em HTML e a impressão em PDF A3 |
| `animacao_dados.py`, `animacao_modelo.html` | Animação do Mapa iluminado pelos dois cenários, em HTML independente |
| `gerar.py`, `gerar_tudo.sh` | Gera a REV00 |
| `rede_agua.py` | REV01: o grafo da água (06.1, 06.2, junções do `config/topologia.json`, pontas pela coordenada) e o instante em que cada trecho fica ligado ao reservatório |
| `motor_rev01.py` | REV01: a ordem a partir do reservatório (Subadutora do TR005 para fora, blocos já ligados primeiro, caixas do caminho primeiro), o que cada trecho espera para receber água e os trechos prontos antes de ligados |
| `analise_rev01.py` | REV01: zonas na ordem da água, setores, km ligados e não ligados mês a mês, motivo de cada exceção |
| `paleta_rev01.py` | REV01: as cores (CIEDE2000 ≥ 20 em cada legenda, conferidas no validador da skill dataviz) |
| `xlsx_rev01.py`, `projeto_rev01.py`, `gantt_rev01.py` | REV01: a planilha (data do reservatório, quadro REV00 × REV01, PROGRAMAÇÃO com a carga e a aba CARGA), o Project (marcos do reservatório, "ligada" e "em carga") e o Gantt |
| `animacao_rev01.py`, `animacao_rev01_modelo.html` | REV01: a animação só do cenário B, com o reservatório e a situação de cada trecho na ligação |
| `gerar_rev01.py`, `gerar_rev01.sh`, `conferir_rev01.py` | Gera a REV01 e faz as conferências antes da entrega (BM em 100%, juntada, recálculo no LibreOffice com a data em branco e com data de teste, outubro, exceções) |

Premissas, decisões, resultados e como abrir o XML no Project: `.claude/skills/sistema-morro-da-cruz/references/cronograma-executivo.md`
(na raiz do repositório).
