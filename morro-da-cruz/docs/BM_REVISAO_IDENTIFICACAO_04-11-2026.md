# Revisão da identificação do BM REV04 (04/11/2026)

Pedido do responsável em 04/11/2026. O item 5.14.3 é o portão de veículos padrão Caesb e foi medido na 1ª medição, mas a
descrição curta da Ankara dizia "TUBO". O responsável pediu a revisão da planilha toda.

Regra: **D-203**, seção 23 de `DECISOES_PENDENTES.md`.

## O que foi revisado

Arquivo: `planilhas/BM_MORRO_DA_CRUZ_REV04_IDENTIFICACAO_09-10-26.xlsx`.

São as colunas de identificação, que são da Ankara:
- **na aba principal:** B (descrição curta), C (pressão), D (resina), E (tipo), F (solda), G (diâmetro), H (material),
  I (grupo), J (grupo do orçamento Ankara) e L (classificação);
- **na vertical:** as mesmas, de F a P.

Cada item foi lido contra a descrição da Caesb (coluna M da principal, Q da vertical): os 347 itens da principal e as 432
linhas da vertical.

**Conferências automáticas:**

| Conferência | Resultado |
|---|---|
| Principal × vertical, mesmo código | iguais nas 432 linhas da vertical |
| Grupo (I) × orçamentos parciais da vertical | iguais |
| Diâmetro (G) e pressão (C) × números da descrição | iguais onde a descrição tem o número |
| Classificação (L) × grupo do BM | uniforme dentro de cada grupo. Material: 1, 2, 3, 6 e 7. Serviço: 4, 5 e 8. Fecha o P0 de R$ 49.878.748,66 |

O que mudou foi só a identificação da Ankara. Código Caesb, descrição da Caesb, unidade, quantidade, preço e fórmulas
continuam os mesmos, e o P0 não mudou.

## Itens corrigidos (23)

| Item | O que estava | O que ficou |
|---|---|---|
| 5.14.3 | B "TUBO", tipo TUBO, material N/A, grupo Ankara TUBO | B "PORTÃO PARA VEÍCULOS PADRÃO CAESB - ESTRUTURA EM TUBO E TELA DE ARAME GALVANIZADO"; tipo PORTÃO; material AÇO GALVANIZADO; grupo CANTEIRO; diâmetro N/A |
| 5.7.7 | B "CAIXA D'ÁGUA", tipo CAIXA D'ÁGUA, grupo RESERVATÓRIO | é o assentamento do hidrante de coluna: B "ASSENTAMENTO DE HIDRANTE DE COLUNA C/ REGISTRO E CONEXÕES, CAIXA DE REGISTRO E LAJE DE APOIO"; tipo HIDRANTE; grupo ASSENTAMENTO |
| 5.18.1 | B "HIDRÔMETRO", tipo HIDRÔMETRO | é o kit cavalete sem hidrômetro: B "MONTAGEM E ASSENTAMENTO DE KIT CAVALETE 3/4" DE LATÃO (SEM HIDRÔMETRO E TUBETE)"; tipo KIT CAVALETE; 3/4"; LATÃO; grupo LIGAÇÕES |
| 5.10.1 | B "HIDRÔMETRO" | B "ASSENTAMENTO DE HIDRÔMETRO 1,5 M³/H" (é serviço) |
| 5.10.2 | B "HIDRÔMETRO CONCRETO", tipo HIDRÔMETRO | B "ASSENTAMENTO DE MURETA PRÉ-MOLDADA DE CONCRETO P/ HIDRÔMETROS"; tipo MURETA |
| 5.7.8 | B "TAMPÃO FºFº (EXCLUSÕES NA DESCRIÇÃO OFICIAL)" | B "ASSENTAMENTO DE TAMPA FºFº BIARTICULADA 1200 X 980 MM (SEM FORNECIMENTO)"; 1200X980 |
| 5.7.9 | B "TAMPÃO FºFº" | B "ASSENTAMENTO DE TAMPÃO FºFº T-100" |
| 5.10.5 | B "ASSENTAMENTO DE TUBO PEAD", diâmetro N/I | B "LIGAÇÃO PREDIAL - ASSENTAMENTO DE TUBO PEAD 20 MM C/ ADAPTADOR E LUVA ELETROFUSÃO"; 20 |
| 5.10.3 | tipo HIDRÔMETRO | tipo CAIXA PROTEÇÃO (é a caixa de concreto do hidrômetro) |
| 5.10.4 | tipo HIDRÔMETRO, diâmetro N/A | tipo KIT CAVALETE; 25 (PVC 25 mm) |
| 5.15.3 | tipo CAIXA D'ÁGUA, diâmetro N/A | tipo TORNEIRA DE BOIA; 1.1/2" |
| 5.11.2 | tipo e grupo TRANSPORTE | é a trama de aço do telhado: tipo ESTRUTURA DE TELHADO; grupo CANTEIRO (como o 5.11.1) |
| 5.7.15 | tipo e grupo TRANSPORTE | é o lastro de areia: tipo e grupo LASTRO |
| 5.9.5 | tipo e grupo DEMOLIÇÃO, material CONCRETO | é a recomposição em concreto asfáltico: tipo RECOMPOSIÇÃO ASFÁLTICA; material ASFALTO; grupo PAVIMENTAÇÃO |
| 5.7.1 | tipo VRP | tipo ALÇA; 12,5; AÇO CA-60 (é a alça da tampa da caixa da VRP) |
| 1.5.1 | diâmetro 50, material PVC | 0,70X0,60X0,15; CONCRETO (mureta pré-moldada de concreto) |
| 1.18.3 | material BRITA | CONCRETO (concreto usinado C35) |
| 5.7.16 | material PP | CONCRETO (peça pré-moldada com fibra de PP) |
| 5.10.6 | diâmetro N/A | 63X20 |
| 5.13.3 | diâmetro N/I | 50 |
| 1.14.76 e 1.14.77 | B "TUBO" | B "TUBO PEAD PE100 PN10" |
| 1.18.13 | B "TUBO" | B "TUBO PEAD PE80 20 MM P/ LIGAÇÃO PREDIAL" |

## A confirmar (não mudou)

- **Unidades da Caesb que parecem trocadas:**
  - 1.14.31, luva eletrofusão DE 355: em "M";
  - 1.14.57, tê: em "pç";
  - 1.16.1, escada marinheiro: em "M".

  São do contrato e não mudam aqui. Vale perguntar à Caesb antes de medir.
- **1.9.1, tampa T2RBI:** a identificação diz 1285X980. A descrição não traz a medida, e o assentamento (5.7.8) é de 1200 × 980.
- **1.11.1, caixa de proteção do hidrômetro:** "50X40" e "PLÁSTICO" não estão na descrição.

## A 1ª medição na planilha do responsável

As quantidades da 1ª medição tinham sido digitadas direto na aba principal (coluna R), no lugar da fórmula. Na 6.1.1, a
fórmula tinha sido apagada. Os itens:
- 5.1.2;
- 5.14.3 a 5.14.5;
- 5.15.2;
- 6.1.3;
- 7.1.1.

Com isso:
- a vertical, o cronograma FF e os gráficos ficavam em zero;
- a administração local proporcional não entrava.

**No arquivo devolvido ao responsável:**
- as quantidades estão na 01ª MC, uma folha por item;
- a vertical puxa da MC, e a principal volta a puxar da vertical;
- a administração local entra pela folha da ADM: R$ 1.973,25 sem BDI;
- o reajuste da 1ª medição fica em R$ 0,00, "não pedido" (D-140).

O arquivo do repositório não leva medição: é o modelo do pacote.

## No site

- **O modelo do pacote mensal** é o próprio arquivo do repositório. O pacote passa a sair com a identificação corrigida.
- **Os itens do BM no banco** (apropriação, medição) vêm da importação. O BM novo tem outro SHA-256, e a demonstração
  se reimporta sozinha quando o site recarrega (`nuvem._atualizar_demonstracao`, com backup verificado antes). Se a
  importação reprovar, o site abre com o banco como estava e não tenta de novo os mesmos arquivos.
- **Controles:** `config/controles.json` ganha o conjunto **CTRL-02**, com o SHA-256 do BM novo e os mesmos valores do
  CTRL-01. A aprovação fica PENDENTE (D-01) e o CTRL-01 não mudou.

Testes: `tests/test_bm_identificacao.py` e `tests/test_nuvem.py`
(`test_planilha_nova_no_repositorio_reimporta_a_demonstracao_ao_subir`).
