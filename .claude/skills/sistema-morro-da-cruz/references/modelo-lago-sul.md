# Medição e relatório mensal Caesb (modelo Lago Sul)

Referência da skill `sistema-morro-da-cruz`, trazida da skill `medicao-e-relatorio-mensal-caesb` (repositório
`gabrielghorta/morrodacruz_webapp`, 26/10/2026). É o **formato** do pacote mensal da Ankara para a Caesb, tirado do
contrato Lago Sul (CT 10.159/2026). Os números do Morro da Cruz estão em `dados-do-projeto.md`; o que o web app já
gera está em `medicao-caesb.md`. Onde este arquivo fala em "este skill", leia "esta referência".

Conteúdo: 0 como usar · 1 glossário · 2 o pacote e a ordem de produção · 3 a lógica da medição (valor, colunas,
juntada, vertical, ADM, reajuste, MC, cronograma FF, gráficos, CPUs) · 4 juntada · 5 relatório mensal · 6 cronograma
físico executivo (MS Project) · 7 de onde vem cada dado no sistema · 8 calendário · 9 qualidade · 10 conferências
cruzadas · 11 erros do modelo · 12 parâmetros por contrato · 13 pendências.

## 0. Como usar este arquivo

Este documento descreve **o formato de saída e as regras de cálculo** que a Ankara usa com a Caesb. A referência é o Lago Sul. Não o use como fonte de números do Morro da Cruz: os parâmetros mudam por contrato (§12).

**Regras para quem usar este skill:**
- **Não copie dados pessoais do modelo.** Isso vale para nomes, telefones, e-mails, CREA e endereços de pessoas. Também não copie nomes de fornecedores que sejam pessoa física. Use campos preenchidos pelo sistema (`<engenheiro responsável>`, `<técnico de medição>` etc.).
- **Valores devem sair do sistema e bater entre si** (§10). Um número digitado à mão no relatório é erro.
- **Não repita os erros encontrados no modelo** (§11).
- **Medição fechada é congelada.** Não se recalcula medição anterior.

### Fontes analisadas

| Documento | Arquivo de referência | O que é |
|---|---|---|
| Cronograma físico executivo | `03.1_CRONOGRAMA_FISICO_EXECUTIVO.pdf` (1 página A0, impresso do MS Project) | Gantt com linha de base, % concluído e linha de status, título "REV00 - 2º MEDIÇÃO" |
| Relatório mensal | `08_RL_MENSAL_02-2026.pdf` (53 páginas A4, Word) | RM – 02/2026, período 01/08/26 a 31/08/26 |
| Boletim de medição | `03.3.2 - 2º_BM_LAGO_SUL_REV00_CAESB.xlsm` (15 abas, ~25 MB, com macros) | BM horizontal ("JUNTADA"), BM vertical, memórias de cálculo (MC) da 1ª e da 2ª medição, cronograma FF, gráficos, reajuste e CPUs |
| Juntada da medição | Link do Google Drive enviado pelo usuário | **Não foi acessado**: o conector respondeu "não encontrado". A aba `BM LAGO SUL PSxPV` se chama "BM - PLANILHA DE MEDIÇÃO - JUNTADA" e foi convertida em PDF para ver o impresso (§4.2). Se o documento do Drive tiver outras peças (ofício, folha de rosto, atestado), complete este skill quando ele chegar. |

---

## 1. Glossário

| Termo | Significado |
|---|---|
| **P0 / PV** | Preço original do contrato, sem reajuste ("ORIGINAL - P0 (CAESB) - PV"). Todo valor "P0" é antes do reajuste. |
| **BM** | Boletim de Medição: a planilha oficial com todos os itens do orçamento e a coluna de cada medição. |
| **BM horizontal (PSxPV)** | Uma linha por item do orçamento Caesb e colunas por medição. É a versão **juntada** ao processo. |
| **BM vertical ("orçamentos parciais")** | Mesmos itens repetidos por **frente / sub-DMC × material/serviço × categoria** (canteiro, rede, caixas, ligações, hidromecânico). É o que alimenta o cronograma FF. |
| **MC (memória de cálculo)** | "Memorial vertical de quantificação de serviços / materiais": uma folha por item medido no mês, com fotos, justificativa e conta. Uma aba por medição (`01ª MC`, `02ª MC`…). |
| **Cód. Cron. FF** | Código do grupo do cronograma físico-financeiro (ex.: `18.2` = "ADUTORA 01 - SERVIÇO"). |
| **Chave do item no vertical** | `CódCronFF_ItemBM` (ex.: `18.2_4.15.2`). Liga a MC ao BM vertical. |
| **Código Caesb** | Código da composição/insumo (ex.: `8010008010086`). Liga o BM vertical ao BM horizontal. |
| **Classificação** | `MATERIAL` ou `SERVIÇO`. Define qual BDI se aplica. |
| **BDI** | Por classe. Lago Sul: material 15,28 %, serviço 21,48 %. |
| **Coef. K** | Desconto da licitação aplicado sobre o total com BDI: `K = −1 + (1 − desconto)`. Lago Sul: −2,1 %. |
| **Reajuste** | Variação do índice (ICCB-Brasília DI) entre a data-base e o aniversário, aplicada ao valor P0 medido. |
| **Estaca** | 20 m. `EST. 41+08,00` = 41 × 20 + 8,00 = 828,00 m. |
| **Emboque** | Poço de entrada/saída do furo direcional (MND). |
| **MND / VCA** | Método não destrutivo (furo direcional) / vala a céu aberto (método destrutivo). |
| **Sub-DMC, DMC** | Distrito de medição e controle: a divisão da rede usada no cronograma e no BM vertical. |
| **SAOB / IDA** | Relatório de Supervisão Ambiental de Obras (Caesb) / Indicador de Desempenho Ambiental. |
| **Juntada** | Documento anexado ao processo da Caesb (GDOC/SEI). A planilha de medição "juntada" é o BM filtrado só com os itens medidos. |

---

## 2. O pacote mensal e a ordem de produção

Todo mês, ao fim do período de medição (do dia 1 ao último dia do mês; a 1ª medição vai da OS até o fim do mês seguinte), sai este pacote:

1. **Campo → memórias (MC)**: para cada item executado, uma folha com fotos, justificativa e memorial. Fonte: NS de topografia, croquis, diário e fotos com carimbo de data e local.
2. **BM vertical**: a coluna da medição do mês recebe `SUMIFS` da MC pela chave `CódCronFF_ItemBM`.
3. **BM horizontal (juntada)**: a coluna da medição recebe `SUMIFS` do vertical pelo código Caesb. É impresso filtrado só nos itens medidos.
4. **Reajuste da medição**: aba própria com o valor P0 do mês × variação do índice.
5. **Cronograma FF Caesb**: o financeiro executado do mês sai do vertical. Acumulados, % e reajuste mês a mês.
6. **Gráficos**: 4 gráficos (R$ e %, mensal e acumulado) a partir do cronograma FF.
7. **Cronograma físico executivo (MS Project)**: % concluído por trecho atualizado e linha de status na data de corte. O título leva "REV nn - nº MEDIÇÃO".
8. **Relatório mensal (RM)**: consolida tudo (§5), com croquis semanais, tabelas, histogramas, fotos e anexos.

**Fluxo de dados (é a cadeia de chaves que precisa ser preservada no sistema):**

```
NS / croqui / fotos / diário
        │ (trecho, estacas, dimensões)
        ▼
MC do mês  ──chave CódCronFF_ItemBM──►  BM VERTICAL (coluna do mês)
                                            │ SUMIFS por CÓDIGO CAESB
                                            ▼
                                     BM HORIZONTAL = JUNTADA (coluna do mês)
                                            │ total P0 do mês
                                            ▼
                    REAJUSTE (aba do mês) ─┤
                                            ▼
       BM VERTICAL ──SUMIFS por Cód. Cron. FF──► CRONOGRAMA FF CAESB ──► GRÁFICOS ──► RM
```

---

## 3. A lógica da medição (núcleo)

### 3.1 Valor por item, por classe e total

Na ordem exata do BM (vale nas duas versões do BM, horizontal e vertical):

1. **Total do item**: `ROUND(quantidade × preço unitário P0; 2)`. O preço unitário vem **sem BDI**.
2. **Σ por classe**: `SUMIFS(totais; classificação; "MATERIAL")` e o mesmo para `"SERVIÇO"`.
3. **SUB-TOTAL 01** = material + serviço.
4. **BDI por classe**: `BDI MATERIAL = Σmaterial × 15,28 %` e `BDI SERVIÇO = Σserviço × 21,48 %`. A soma dos dois é o **SUB-TOTAL 02**.
5. **TOTAL 01 + 02** = SUB-TOTAL 01 + SUB-TOTAL 02.
6. **COEF. K** = `TOTAL 01+02 × K`, com `K = −1 + (1 − 2,1 %) = −0,021`.
7. **TOTAL 01 + 02 + BDI − K** = valor P0 da medição. É o valor "faturado (P0)".
8. **% PRINCIPAL** = valor P0 da medição ÷ valor P0 do contrato.
9. **Reajuste por classe**: `REAJ. MATERIAL = i × (Σmaterial + BDI material) × (1 + K)` e o mesmo para serviço, onde `i` é a variação do índice (§3.6).
10. **SUB-TOTAL REAJ.** = soma dos dois. **% REAJUSTE** = reajuste ÷ P0 (dá `i`).
11. **TOTAL GERAL** = P0 + reajuste.

**Exemplo real (2ª medição, agosto/2026):**

| Linha | Contrato (P0) | 2ª medição | Acumulado |
|---|---:|---:|---:|
| Material | 3.192.913,03 | 5.631,10 | 8.637,32 |
| Serviço | 15.678.707,19 | 468.136,72 | 620.054,43 |
| SUB-TOTAL 01 | 18.871.620,22 | 473.767,82 | 628.691,75 |
| BDI material 15,28 % | 487.877,11 | 860,43 | 1.319,78 |
| BDI serviço 21,48 % | 3.367.786,30 | 100.555,77 | 133.187,69 |
| SUB-TOTAL 02 | 3.855.663,42 | 101.416,20 | 134.507,47 |
| TOTAL 01 + 02 | 22.727.283,64 | 575.184,02 | 763.199,22 |
| COEF. K −2,10 % | −477.272,96 | −12.078,86 | −16.027,18 |
| **TOTAL P0** | **22.250.010,68** | **563.105,16** | **747.172,04** |
| % principal | 97,90 % (= 1 + K) | 2,53 % | 3,36 % |
| Reajuste material 9,01 % | 324.703,08 | 572,65 | 878,37 |
| Reajuste serviço 9,01 % | 1.680.197,71 | 50.167,54 | 66.447,70 |
| **SUB-TOTAL REAJ.** | **2.004.900,80** | **50.740,20** | **67.326,07** |
| **TOTAL GERAL** | **24.254.911,48** | **613.845,35** | **814.498,11** |

A 1ª medição (16/06 a 31/07) foi de P0 184.066,87 mais 16.585,87 de reajuste. O saldo do contrato (P0) é 22.250.010,68 − 747.172,04 = **21.502.838,64**.

**Atenção:** o modelo tem ajustes manuais nos totais do contrato: `−0,27` no material, `−0,11` ou `−0,31` no serviço e `−0,58` no cronograma, só para bater com o valor do contrato. No sistema, guarde o valor contratual como **parâmetro conferido** e mostre a diferença de arredondamento como alerta. Não esconda a diferença dentro de uma fórmula.

### 3.2 Colunas por medição, acumulado e saldo

- O BM tem **18 pares de colunas (QUANT., TOTAL)**, um por medição prevista (prazo de 540 dias). O cabeçalho de cada par traz `MED. Nº.`, `nª MEDIÇÃO`, `PERÍODO: dd-mm-aa A dd-mm-aa`.
- **Acumulado** = `SUMIFS(colunas de quantidade; cabeçalho; "QUANT.")`: soma todas as colunas de quantidade da linha.
- `% MEDIDO = acumulado ÷ quantidade contratada` e `% SALDO = (contratada − acumulado) ÷ contratada`.
- **Saldo negativo** significa que o item foi medido acima do contratado. Na 2ª medição isso aconteceu em dois itens:
  - reaterro mecanizado (4.4.32): **1.486,88 %**;
  - luva de eletrofusão DN 160 (1.12.26): **150 %**.

  O modelo não sinaliza nada. **O sistema tem de barrar ou exigir justificativa e aditivo** quando o acumulado passar de 100 %. A regra do Morro da Cruz é o teto por subgrupo (§12).
- **Congelamento:** as colunas de medições fechadas guardam **valores digitados** (a 1ª medição do vertical é valor fixo, não fórmula). Só a coluna do mês corrente tem fórmula, apontando para a MC do mês. Ao fechar, converte-se em valor e a próxima coluna passa a apontar para a nova MC.

### 3.3 BM horizontal = "PLANILHA DE MEDIÇÃO – JUNTADA"

**Colunas:**
- `ITEM - BM`, `DESCRIÇÃO`, `PRESSÃO`, `RESINA`, `TIPO_CONEXÃO`, `SOLDA`, `DIÂMETRO`, `MATERIAL`, `GRUPO`, `GRUPO ORÇAMENTO ANKARA`;
- `CÓDIGO CAESB`, `CLASSIFICAÇÃO`, `DESCRIÇÃO` (a da Caesb), `UNID.`;
- `QUANT.`, `VALOR UNITÁRIO`, `TOTAL` (P0);
- 18 pares de medições;
- `QUANT.` e `TOTAL ACUMULADO`, `% MEDIDO`, `% SALDO`.

**Hierarquia:** grupo de 1º nível (código Caesb curto, ex.: `3` MATERIAL, `5` EQUIPAMENTO, `6` SERVIÇO, `8` SERVIÇOS COMPOSTOS, `19` CHE SEM OPERADOR) → subgrupo (ex.: `4.15` OBRAS SUBTERRÂNEAS, código 80100) → item (ex.: `4.15.2`). As linhas de grupo e subgrupo são `SUM` das filhas. O Lago Sul tem **326 itens**.

**A linha do item é calculada assim:**
- quantidade da medição n = `SUMIFS(vertical!coluna_n; vertical!CÓDIGO CAESB; este código)`;
- total = `ROUND(quantidade × preço; 2)`.

**Impressão para a juntada (A4 paisagem):**
- linhas filtradas, só os itens com medição;
- colunas das medições anteriores ocultas: aparecem P0, a medição do mês e o acumulado;
- bloco de resumo no rodapé (§3.1);
- cabeçalho com contrato, nº da medição, período, data, "ELAB. POR" e a faixa "STATUS DO CONTRATO" (% medido e % saldo).

**Itens medidos na 2ª medição (16 linhas):**
- materiais: tenda 1.3.1, luva PEAD DN 160 1.12.26, placa de obra 1.15.11;
- administração local 3.1.1;
- tapume 4.1.2;
- locação e nivelamento com NS 4.2.7;
- isolamento 4.3.2;
- escavação mecanizada 4.4.15 e reaterro mecanizado 4.4.32;
- junta por eletrofusão 4.8.35;
- meio-fio e sarjeta 4.9.6;
- espalhamento em bota-fora 4.13.2;
- placa de obra 4.13.4;
- limpeza manual 4.13.6 e mecanizada 4.13.7;
- **MND DN 160, 4.15.2**: o item de maior valor.

### 3.4 BM vertical ("orçamentos parciais")

- **Colunas:**
  - `SEQUÊNCIA`, `CÓD. CRON. FF`, `DESCRIÇÃO DO ORÇAMENTO`;
  - `ITEM - BM VERTICAL` (= `CONCAT(CódCronFF; "_"; ItemBM)`), `ITEM - BM`;
  - os atributos técnicos, o `CÓDIGO CAESB`, a `CLASSIFICAÇÃO`, a `DESCRIÇÃO SUMÁRIA`;
  - `UNID.`, `QUANT.`, `VALOR UNITÁRIO`, `TOTAL`;
  - as 18 medições e o acumulado.
- **20 blocos de 1º nível** (frente × tipo):
  - CANTEIRO;
  - SUBMDC 5.0, 5.1, 5.2 e 5.3, cada uma com: MATERIAL + SERVIÇO, CAIXAS, LIGAÇÕES e MATERIAL HIDROMECÂNICO;
  - ADUTORA 01: MATERIAL + SERVIÇO, CAIXAS e HIDROMECÂNICO.
- **Cada bloco se divide em `n.1` MATERIAL e `n.2` SERVIÇO.** São **36 códigos de cronograma**, por exemplo `10.2` "SUBMDC 5.2 - SERVIÇO" e `20.1` "ADUTORA 01 - MATERIAL - HIDROMECÂNIC".
- **A administração local fica num bloco à parte**: `21.2` (item 3.1.1, unidade UN, quantidade 1).
- A coluna `BH` dá o peso de cada bloco no contrato (ex.: SUBMDC 5.1 = 25,29 %).
- A quantidade da medição do mês vem de `SUMIFS('nª MC'!W:W; 'nª MC'!C:C; chave)`.

### 3.5 Administração local medida em proporção (fórmula do modelo)

A administração local (item 3.1.1, preço P0 de 1.247.894,78, quantidade 1 UN) é medida **em fração**, proporcional ao faturamento do mês sem ela:

```
% ADM        = ADM ÷ (TOTAL MAT+SERV P0 sem BDI − ADM) = 1.247.894,78 ÷ 17.623.725,44 = 7,0808 %
FAT. MÊS     = Σ(material + serviço P0, sem BDI) do mês, sem a ADM = 473.767,82 − 31.328,12 = 442.439,70
FAT. ADM MÊS = FAT. MÊS × % ADM = 31.328,12
QUANT. MÊS   = FAT. ADM MÊS ÷ ADM = 0,025105 UN
```

A folha de ADM na MC traz:
- essa conta;
- a lista da equipe administrativa/engenharia (função, nome, cargo, quantidade). **No sistema, preencha a partir do cadastro de usuários, sem nomes fixos no modelo**;
- a justificativa "EQUIPE ADMINISTRATIVA/ENGENHARIA DA SETORIZAÇÃO".

### 3.6 Reajuste

Há uma aba por medição (`REAJUSTE 2ª MED`) e uma aba de cálculo do índice (`REAJUSTE 2`).

**Parâmetros:**
- data do orçamento: 31/07/2024;
- pró-rata de 30 dias;
- indicador: **ICCB-Brasília DI**.

**Índices:**
- I0 = índice do mês da data-base (07/2024 = 830,538);
- I1 = índice do mês de aniversário (07/2026 = 905,376).

**Fórmula pró-rata** (com 30/30 dias, ela devolve o próprio índice do mês):

```
I = ((I_mês ÷ I_mês_anterior − 1) × 100 ÷ 30 × dias ÷ 100 + 1) × I_mês_anterior
i = (I1 − I0) ÷ I0 = 9,0108 %
VALOR REAJUSTE = valor P0 da medição × i     (2ª: 563.105,16 × 9,0108 % = 50.740,20)
```

- **`REAJUSTE 1` é histórica**: aniversário de 07/2025, 3,52 %, com a série do índice de 07/2024 a 09/2025. Não entra no cálculo.
- **Nomes definidos herdados de outro modelo:** `Loan_Years`, `Number_of_Payments` e `Total_Cost` são as células I0, I1 e i. No sistema, dê nomes próprios.
- No modelo, **o mesmo percentual foi aplicado também à 1ª medição** (16/06 a 31/07/2026). Confirme no contrato se o reajuste incide sobre medições anteriores ao aniversário e com que fração. No Morro da Cruz isso é a decisão D-55 ("frações elegíveis").

### 3.7 Memória de cálculo (aba `nª MC`) — uma folha por item medido

**Estrutura fixa de 92 linhas por folha.** A 2ª MC tem 14 folhas. A 1ª tem 10.

1. **Cabeçalho:**
   - `FOLHA - 001`;
   - "MEMORIAL VERTICAL DE QUANTIFICAÇÃO DE SERVIÇOS / MATERIAIS";
   - CONTRATO, PERÍODO e DATA (puxados do vertical), MED. Nº, ELAB. POR;
   - logos Ankara e Caesb.
2. **Linha do item** (faixa laranja):
   - DESCRIÇÃO DO ORÇAMENTO, ITEM-BM (a chave), CÓDIGO CAESB, CLASSIFICAÇÃO, DESCRIÇÃO SUMÁRIA, UNID., buscados no vertical por `INDEX/XMATCH` na chave;
   - TOTAL = `SUM` dos subtotais do memorial.
3. **GALERIA DE FOTOS / CROQUIS ILUSTRATIVOS:**
   - até 6 fotos lado a lado, ou croquis;
   - fotos com **carimbo de data, hora, local, altitude e velocidade** (app de câmera com marca d'água);
   - à direita, a coluna **JUSTIFICATIVA TÉCNICA**.
4. **MEMÓRIAL DE CÁLCULO:** uma linha por ocorrência, com:
   - `CÓD. CRON. FF`, `DESCRIÇÃO DO ORÇAMENTO`, `NOMENCLATURA DA OBRA` (ex.: `SUB-ADUTORA-TR385`, `SUBDMC-5.2-TR137`);
   - `PROJETO` (prancha nn/nn), `DATA REVISÃO`;
   - `EST. INICIAL` e `FRAÇÃO`, `EST. FINAL` e `FRAÇÃO`, `CLASSIFICAÇÃO` (rede primária/secundária), `PONTO REFERÊNCIA` (emboque nn, ventosa nn, descarga nn, travessia nn);
   - as dimensões, `QUANT.`, `UNID.`, `SUB-TOTAL`.

**Tipos de conta encontrados (o sistema deve ter um tipo de memorial por unidade):**

| Item (exemplo) | Unidade | Conta |
|---|---|---|
| MND, locação, rede | M | `(EST.final × 20 + fração) − (EST.inicial × 20 + fração)`. A estaca inicial de uma linha é a final da anterior (encadeado). |
| Escavação de emboque | M³ | `comprimento × largura × profundidade × quant.` |
| Corte de talude | M³ | `comprimento × área do triângulo ((B × b) ÷ 2) × quant.` |
| Reaterro de emboque | M³ | `C × L × P − volume do tubo`. **O modelo usa `π × D² × C` com D = 0,16 m (diâmetro no lugar do raio): desconta 4× mais. O certo é `π × (D/2)² × C`.** |
| Isolamento (tela) | M² | `(C1 + C2 + L1 + L2) × altura × quant.` (perímetro × altura) |
| Tapume | M² | `comprimento × altura − desconto (portão)` |
| Limpeza, placa | M² | `comprimento × largura` ou `comprimento × altura` |
| Junta, luva, peça | UN | uma linha por ocorrência (local e estaca) |
| Meio-fio | M | comprimento por ponto |
| Administração local | UN (fração) | §3.5 |

**Justificativas técnicas padronizadas usadas no modelo:**
- "MATERIAL NÃO PREVISTO NA EXECUÇÃO DA ADT.";
- "SERVIÇO NÃO PREVISTO NA EXECUÇÃO DA ADUTORA";
- "NECESSÁRIO P/ ESTABILIZAR A MÁQUINA NAVIGATOR";
- "UTILIZADO PARA FECHAR REDE POR CONTA DE PEDRA";
- "EQUIPE ADMINISTRATIVA/ENGENHARIA DA SETORIZAÇÃO".

O sistema deve oferecer essas frases como opção e permitir texto livre. **Todo item fora do previsto precisa de justificativa.**

### 3.8 Cronograma físico-financeiro (aba `CRONOGRAMA FF CAESB`)

- **Cabeçalho:** CLIENTE, CONTRATO Nº, OBJETO, REVISÃO / DATA (ex.: "V00 - 22 JUNHO 2026").
- **Colunas:** `ITEM`, `DESCRIÇÃO`, `VALORES` (R$ e % do total); depois os meses, cada um com rótulo, período e número de dias. O 1º "mês" tem 45 dias (16/06 a 31/07). O total é de 540 dias.
- **Cada item tem 4 linhas:**
  - `FINANC. PROGRAMADO - R$` = físico programado × valor do item;
  - `FINANC. EXECUTADO - R$` = `SUMIFS` da coluna da medição no vertical pelo Cód. Cron. FF;
  - `FÍSICO PROGRAMADO - %`: é **entrada** (a distribuição mensal planejada, que soma 100 %);
  - `FÍSICO EXECUTADO - %` = executado ÷ valor do item.
- **Barras tipo Gantt** por formatação: azul = programado, vermelho = executado.
- **Blocos de total:**
  - `1 FORNECIMENTO MATERIAIS`, depois `2 EXECUÇÃO DE SERVIÇOS`, cada um com BDI;
  - `DESCONTO CONTRATUAL` (2,1 %);
  - `TOTAL GERAL MATERIAL + SERVIÇO`;
  - `FATURAMENTO - ACUMULADO` (programado e executado, em R$ e em %);
  - `REAJUSTE - MÊS A MÊS` (material e serviço, programado e executado);
  - `TOTAL REAJUSTE`;
  - `TOTAL MEDIÇÃO + REAJUSTE`, com acumulados.
- **Saldo** = total geral − executado acumulado (21.502.838,65).

### 3.9 Gráficos (aba `GRÁFICOS`, 4 gráficos que vão para o RM)

São 18 meses (MÊS 01 a 18) e três séries: **PREVISTO**, **REALIZADO** e **REPROGRAMADO**. No modelo, a série reprogramado está vazia porque ainda não houve reprogramação. O sistema deve aceitar uma reprogramação (nova distribuição do saldo) e plotá-la.

| Gráfico | Conteúdo | Eixos |
|---|---|---|
| Físico Financeiro (R$) – Mensal | colunas por mês em **R$/1000** | um eixo |
| Físico Financeiro (%) – Mensal | % do mês sobre o contrato | um eixo |
| Físico Financeiro (R$) – Acumulado | colunas mensais (eixo direito) + linhas acumuladas (eixo esquerdo), R$/1000 | dois eixos |
| Físico Percentual (%) – Acumulado | idem, em % | dois eixos |

O valor do realizado tem **rótulo destacado em amarelo**. Os valores são sempre P0 (sem reajuste).

### 3.10 Composições (aba `CPUs`)

- **Conteúdo:** "Composições analíticas com preço unitário" do orçamento de venda com desconto final.
- **Bancos:** SINAPI 07/2024 DF, SICRO3 07/2024 e composições próprias Caesb.
- **Encargos sociais:** não desonerado (horista 110,14 %).
- **BDI da CPU = 0 %**, porque o BDI entra só no BM.
- **Estrutura de cada composição:** código, banco, descrição, tipo, unidade, quantidade, valor unitário e total. Embaixo dela vêm as composições auxiliares e os insumos, e a linha "MO sem LS / LS / MO com LS / Valor com BDI".
- **Uso:** consulta de preço de item novo e justificativa de preço. Não entra no cálculo mensal.

### 3.11 Abas que são lixo de modelo (não reproduzir)

Estas abas estão ocultas e vêm de outros contratos:
- `Plan1` e `Plan7`: ETA piloto, BDI de 26,19 %;
- `Plan2`: cronograma de 38 meses de outra obra;
- `RESUMO - NS LIBERADAS`: contrato 8879-2018, esgoto;
- `MEMÓRIA DE CÁLCULO`: calçada e asfalto, com `#REF!`.

O arquivo também tem **70 vínculos externos**, e os metadados do Word do RM vêm de outro lote. **O sistema gera os documentos do zero**, sem herdar esses restos.

---

## 4. Juntada

### 4.1 O que é

É a **peça anexada ao processo de pagamento** da Caesb. Pelo modelo, a planilha juntada é o **BM horizontal filtrado só com os itens medidos no mês**, impresso em A4 paisagem com o bloco de resumo. A memória de cálculo do mês, o reajuste e o cronograma FF acompanham a juntada como peças de apoio.

O documento de juntada do Drive não pôde ser aberto. Quando chegar, registre aqui:
- a ordem das peças;
- a folha de rosto e o ofício;
- quem assina;
- as numerações exigidas pelo GDOC.

### 4.2 Como o modelo imprime (convertido em PDF, 298 páginas no total)

| Páginas | Aba | Formato |
|---|---|---|
| 1–2 | BM horizontal (JUNTADA) | A4 paisagem: itens medidos, P0, mês, acumulado, % medido e % saldo, resumo |
| 3–74 | BM vertical | A3: todos os itens por frente |
| 75–98 | 01ª e 02ª MC | A3 paisagem, uma folha por página (cabeçalho, galeria, memorial) |
| 99–119 | Cronograma FF | A4 paisagem, com barras azul/vermelho |
| 120–121 | Gráficos | 4 gráficos |
| 122–124 | Reajustes | A4 retrato |
| 125–297 | CPUs | composições |

**Para a juntada mensal, o sistema precisa gerar, nesta ordem:**
1. BM horizontal filtrado (página da medição);
2. memória de cálculo do mês (todas as folhas);
3. reajuste da medição;
4. cronograma FF atualizado;
5. gráficos.

O vertical completo e as CPUs só entram quando pedidos.

---

## 5. Relatório mensal (RM) — estrutura completa

### 5.1 Formato

- **Arquivo:** Word → PDF, A4 retrato. Algumas páginas são paisagem (tabelas largas: 15.1 a 15.5, 16.4 a 16.7, 19.3.1).
- **Moldura:** borda dupla vinho em todas as páginas.
- **Cabeçalho de toda página:** tabela de 3 colunas, `Contrato Número | Número do Relatório | Período de Execução`, ex.: `10.159/2026 | RM – 02/2026 | 01/08/26 a 31/08/26`.
- **Rodapé:** `Página X | N`.
- **Títulos:**
  - nível 1 numerado, em vermelho escuro itálico e caixa alta (`2 APRESENTAÇÃO`);
  - nível 2 em preto negrito (`4.1 Características Gerais…`);
  - listas com ✓.
- **Legendas numeradas por tipo:**
  - `Imagem nn` (fotos e croquis do texto);
  - `Figura nn` (mapa geral);
  - `Tabela nn`;
  - `Gráfico nn`;
  - `FOTO nn – legenda;`.

  **A numeração precisa ser sequencial.** O modelo pula números (§11).
- **Tabelas importadas da planilha** como imagem, com cabeçalho padrão:
  - título em vermelho;
  - CONTRATO, DATA, OBRA;
  - ELAB. POR (fundo amarelo);
  - logos Ankara e Caesb;
  - cabeçalho das colunas laranja;
  - colunas de valor coloridas por tipo: verde = projeto, azul = Caesb ou locado, vermelho = emprestado, laranja = retirado, amarelo = aplicado, rosa = cadastro técnico.

### 5.2 Sumário (capítulos e subcapítulos, nesta ordem)

1. **Capa** (pág. 1):
   - foto de fundo de Brasília;
   - objeto completo em vermelho ("EXECUÇÃO DE OBRAS DE SETORIZAÇÃO, ADEQUAÇÃO E SUBSTITUIÇÃO DE REDES DE ABASTECIMENTO DE ÁGUA NA QI 17 ATÉ A QI 29, LAGO SUL/DF.");
   - "RELATÓRIO MENSAL – CONTRATO – nº".
2. **Sumário:** o capítulo "1 SUMÁRIO", automático, com páginas.
3. **2 APRESENTAÇÃO:** parágrafo fixo: razão social da contratada, sede, objeto, edital (ex.: "LPN 001/2025") e contratante.
4. **3 IDENTIFICAÇÃO:** quadro em 4 blocos com rótulo vertical.
   - **EMPRESA:** razão social, CNPJ, CNAE, atividade principal, endereço da sede.
   - **CONTRATANTE:** órgão, CNPJ, CNAE, atividade, grau de risco.
   - **OBRA:** nome, objeto, CNO, CNAE, atividade, grau de risco, endereço do canteiro, contatos (função e telefone), horário de trabalho (seg.–qui. e sex.) e endereço da sede da contratante.
   - **RESPONSÁVEIS:** informações da obra (engenheiro, cargo, CREA, e-mail), elaboração do PGAO (engenheira ambiental), suporte técnico de acompanhamento, segurança do trabalho e administrativo de obra.
   - **Tudo vem do cadastro do sistema. Não fixe dados pessoais no modelo.**
5. **4 DO EMPREENDIMENTO:**
   - **4.1 Características Gerais:** texto com:
     - objetivo, local e "conforme Projeto Básico";
     - extensão total (47,5 km);
     - diâmetros e materiais (PEAD DN 63 a 315; ferro fundido JGS e flangeado);
     - nº de ramais a substituir (3.689);
     - "Mapa Geral – figura 01": mapa com as áreas de projeto por sub-DMC e legenda.
6. **5 DADOS CONTRATUAIS DO EMPREENDIMENTO:** objeto, localização, contratada, nº do contrato, valor inicial, contratante, data de início (OS), data de conclusão, prazo de execução (540 dias consecutivos) e prazo de vigência (655 dias).
7. **6 QUADRO RESUMO GERENCIAL DO CONTRATO:** quadro com:
   - valor inicial;
   - valor da reprogramação 01 e da 02;
   - acréscimos (R$ e %), decréscimos (R$ e %), valor aditivado (R$ e %);
   - valor do reajuste (R$ e %);
   - **valor total aditivado e reajustado**, destacado em amarelo e vermelho.

   O reajuste total é o do contrato inteiro (2.004.900,80 = 9,01 %), não só o medido.
8. **7 DADOS GERENCIAIS CONTRATUAL:**
   - valor faturado acumulado até a nª medição (P0);
   - reajuste acumulado (o modelo chama de "valor faturado reajustado acumulado", mas é **só o reajuste**);
   - valor da nª medição no mês (P0) e o reajuste dela;
   - saldo do contrato (P0);
   - prazo de execução decorrido e restante;
   - prazo de vigência decorrido e restante, com a data limite.
9. **8 DESENVOLVIMENTO DOS TRABALHOS:**
   - texto de mobilização;
   - "Croqui da área de instalação do canteiro", com Imagem 01 (1ª locação do canteiro), Imagem 02 (Google Maps) e Imagem 03 (layout atual);
   - **8.1 Composição do Canteiro de Obras:** lista ✓ de cada instalação com dimensões e área (contêineres, almoxarifado, refeitório, vestiário, baias, depósitos, central de aço);
   - área total, área construída, tapume e área de brita, mais observação de fechamento.
10. **9 ORGANOGRAMA DA OBRA – 1ª parte:** contratada (administração e engenharia, apoio operacional) × fiscalização (Caesb). Imagem 04.
11. **10 ORGANOGRAMA DA OBRA – 2ª parte:** frentes de serviço e terceirizadas (MND, topografia, locações). Imagem 04.1. Os organogramas saem do cadastro de usuários, equipes e terceiros.
12. **11 PRINCIPAIS ATIVIDADES REALIZADAS NO PERÍODO:** **uma subseção por semana** (segunda a domingo):
   - a 1ª semana do mês absorve os dias anteriores à 1ª segunda-feira (ex.: 11.1 = 01 a 09/08, porque 01/08 é sábado);
   - a última pode ter só 1 dia (11.5 = 31/08);
   - **cada semana contém:**
     - frente (ex.: "SETORIZAÇÃO LAGO SUL – SUB-DMC 5.2 / SUB-ADUTORA PEAD DN 160 MM");
     - **croqui de locação** (recorte da prancha nn/nn) com legenda: **EXECUTADO** (vermelho), **ANTERIOR** (amarelo), **NÃO EXECUTADO** (azul) e setas no início e no fim;
     - quadro com setorização, DMC, frente e **trecho de estacas e extensão** (ex.: "EST. 051+00 ATÉ EST. 67+16,00 – 336,00 M", conferível: (67 × 20 + 16) − 51 × 20 = 336);
     - **SERVIÇOS** agrupados por atividade, com checklist padrão:
       - abertura de emboque nn (sinalização, remoção da camada vegetal, escavação mecânica e manual para sondagem, carga, isolamento com cerquite, limpeza);
       - solda termofusão (içamento e transporte dos tubos, fixação e alinhamento na máquina, faceamento, limpeza, placa térmica entre 210 e 260 °C, pressão de soldagem, inspeção visual do cordão);
       - MND (nivelamento da máquina, furo guia, alargamento, passagem do tubo);
       - método destrutivo (camada vegetal, escavação de 1ª e 2ª categoria, regularização do fundo, lastro, assentamento, reaterro compactado em camadas, bota-fora, material importado, retorno da camada vegetal);
       - canteiro (locação dos vértices, piquetes, escavação e concretagem dos pilares do tapume, telhas);
       - redes secundárias / topografia (levantamento com estação total, nivelamento, **elaboração de NS conforme normas Caesb**, croqui da NS, piqueteamento).
   - No sistema, essa seção sai do **diário por NS** (trecho, estacas e serviços marcados) e do mapa (croqui com as 3 cores).
13. **12 MATERIAIS E EQUIPAMENTOS:**
   - **12.1 Dimensionamento das Equipes de Trabalho:**
     - texto padrão (VCA × MND);
     - **Tabela 01 "RESUMO ID-EQUIPES"**: TIPOLOGIA (direto/terceirizado), EMPRESA, CATEGORIA (mão de obra, segurança, suprimento, equipamento), ID EQUIPE (apoio, engenharia, frente de serviço nn), DESCRIÇÃO, SITUAÇÃO (ativo/disponível), total.
     - **É a base única da qual saem as tabelas 10, 11 e 12 (tabelas dinâmicas).**
   - **12.2 MATERIAIS:**
     - **12.2.1 Materiais de consumo diário (fornecimento da contratada):** lista ✓ (cimento, areia lavada média, terra vermelha, prego, pontalete).
     - **12.2.2 Status de entrega de materiais (fornecimento Caesb – tubos PEAD):** **Tabela 02 "COMPATIBILIZAÇÃO DE TUBOS"**. Por tubo (descrição, pressão, DN):
       - levantamento de projeto;
       - estoque Caesb (com o nº do documento de reserva);
       - material emprestado para outras obras da Caesb;
       - **material retirado pela Ankara**;
       - **material aplicado**;
       - cadastro técnico;
       - **estoque virtual = estoque Caesb − emprestado − retirado pela Ankara**;
       - **% executado = aplicado ÷ levantamento de projeto**.

       Há subtotais por material (PEAD, ferro fundido, PVC) e total geral. No sistema, sai do almoxarifado (romaneio Caesb, saída para campo, aplicado pelo OK) e do cadastro.
14. **13 EXECUÇÃO DE OBRAS:**
   - **13.1 Redes de Água:**
     - **13.1.1 Locação Topográfica (com NS):** **Tabela 07**. Por tubo e DN: previsto (projeto), **locado** (NS de topografia), cadastro técnico, relocado, **pendente de locação** (= previsto − locado), % cadastrado e % locado. O total locado **= acumulado do item de locação e nivelamento com NS no BM** (9.769,72 m).
     - **13.1.2 Execução, Rede Acumulada:** **Tabela 08**. Por tubo e DN: levantamento de projeto, **executado no mês**, **executado acumulado**, % pendente e % executado. O executado deve bater com o item de assentamento ou MND medido e com o caminhamento do anexo 19.3.1.
15. **14 PRINCIPAIS ATIVIDADES PREVISTAS PARA O PRÓXIMO MÊS:** lista ✓. No sistema, sai da programação ou do cronograma do mês seguinte: continuação da frente, locação topográfica das próximas redes, visitas socioambientais, mobilização.
16. **15 CRONOGRAMA E GRÁFICOS:**
   - **15.1 Cronograma Físico-Financeiro – Reprogramado:** Tabela 09 (a aba do cronograma FF impressa);
   - **15.2 Gráfico Físico Financeiro (R$) – Mensal:** Gráfico 01;
   - **15.3 Gráfico Físico Financeiro (%) – Mensal:** Gráfico 02;
   - **15.4 Gráfico Físico Financeiro (R$) – Acumulado:** Gráfico 03;
   - **15.5 Gráfico Físico Percentual (%) – Acumulado:** Gráfico 04.
17. **16 HISTOGRAMA OPERACIONAL:**
   - **16.1 Disposição das Equipes Operacionais / Administrativas:** Tabela 10, mão de obra por empresa (soma por empresa e total geral);
   - **16.2 Quadro Resumo de Funções:** Tabela 11, por função;
   - **16.3 Quadro Resumo de Máquinas / Equipamentos / Veículos:** Tabela 12;
   - **16.4 Gráfico Detalhado Mensal do Histograma – Mão de Obra:** Gráfico 05, uma barra por colaborador com os dias: presente, falta, atestado, abono, desligado e meta do mês. **No sistema, use apenas as iniciais ou a matrícula do colaborador**;
   - **16.5 Gráfico Mensal do Histograma – Mão de Obra:** Gráfico 06 "EFETIVO DO DIA", por dia do mês, empilhado em direto e terceirizado, com o total;
   - **16.6 Gráfico de Produção Acumulada por Tipo de Tubo:** Gráfico 11, por tubo e DN: previsto, realizado no mês e acumulado, mais a barra "executado acumulado" total;
   - **16.7 Gráfico do IDA:** Gráfico 15, IDA Caesb por mês contra a meta (70 %), com balões "não houve vistoria da Caesb – nº nn", mais texto sobre o SAOB.
18. **17 OBSERVAÇÕES GERAIS, REUNIÕES E FATOS RELEVANTES:** lista ✓:
   - fechamento da nª medição e o período;
   - DDS e orientações de segurança;
   - situação da vistoria ambiental;
   - inspeções de agentes financiadores;
   - definições da fiscalização.
19. **18 RELATÓRIO FOTOGRÁFICO:**
   - **18.1 Fotos do mês:** **6 fotos por página** (2 colunas × 3 linhas), legenda `FOTO nn – descrição;` (30 fotos em 5 páginas);
   - as fotos saem das fotos obrigatórias e do diário do mês.
20. **19 ANEXOS:**
   - **19.1 Projeto do Canteiro de Obras – Atualizado:** prancha do canteiro;
   - **19.2 Relatório de Supervisão Ambiental de Obras nº nn:** ou a NOTA "Ainda não houve inspeção pela fiscalização da CAESB";
   - **19.3 Mapa Iluminado**, da frente do mês;
   - **19.3.1 Caminhamento – Redes da nª Medição:** planta com o trecho do mês destacado, caixa "PEAD 160 MM EST. 41+08,00 ATÉ EST. 125+15,03" e legenda **REDE EXEC. MÊS: 1.687,03 M** e **REDE EXEC. ACUMUL.: 2.250,00 M**. **No sistema, isso é o Mapa iluminado exportado com as cores do mês e do anterior.**

### 5.3 Textos fixos (modelo de redação)

- **Apresentação:** "A <CONTRATADA>, com sede em <cidade/UF>, <endereço>, para a execução completa e perfeita da <OBRA>, em <cidade/UF> – objeto do edital de licitação <modalidade e nº> da <CONTRATANTE>."
- **4.1:** "O presente documento tem como objetivo apresentar os materiais e serviços a serem fornecidos para <objeto>, denominada <obra>, localizada na <região>, conforme Projeto Básico. Esta <obra> desenvolverá percurso de <km> de extensão, nos diâmetros <lista> em <materiais>… Além da substituição de ligações prediais na quantidade de <n> ramais."
- **8:** "Montagem do canteiro de obra e disponibilização de máquinas, equipamentos e pessoal para execução das atividades, conforme descritos no relatório abaixo:"
- **12.1:** "Disposição de máquinas, ferramentas e acessórios das frentes de serviços para metodologia tipo 'VCA – vala a céu aberto' ou tipo 'MND – método não destrutivo', para andamento da execução dos serviços referentes a <obra>, tais como apresentados na tabela abaixo:"
- **12.2.2:** "Situação referente à entrega / execução dos materiais para <obra>, conforme tabela abaixo:"
- **17:**
  - "Fechamento da <n>ª medição, referente ao período de <início> até <fim>;";
  - "A CONTRATADA informa que ainda não existe data definida para ser realizada a vistoria da equipe ambiental da CAESB para emissão do relatório de supervisão ambiental, referente ao período <…>."

---

## 6. Cronograma físico executivo (MS Project)

- **Título:** `CT <nº> - <OBRA> - REV<nn> - <n>º MEDIÇÃO`. É reimpresso a cada medição, com a linha de status na data de corte.
- **Colunas:** `Id`, `EDT`, `Nome da Tarefa`, `Início`, `Término` e a escala semanal (Jun/26 a Dez/27).
- **Barras:** linha de base (cinza) × atual (azul); **% concluído** ao lado da barra; marcos ◆ (início da obra – OS; final da obra); linha vertical vermelha (status); legenda padrão do Project.
- **Hierarquia da EDT** (até 7 níveis):

```
0  CT <nº> – <obra>                                   (resumo do projeto, % geral)
1.1  INÍCIO DA OBRA – EMISSÃO O.S                      (marco)
1.2  DEFINIÇÃO DO LOCAL DO CANTEIRO
1.3  INSTALAÇÃO DO CANTEIRO
1.4  SUB-ADUTORA  |  1.5 SUB-DMC 5.1  |  1.6 SUB-DMC 5.0  |  1.7 SUB-DMC 5.2  |  1.8 SUB-DMC 5.3
  1.x.1  SETORIZAÇÃO – REDES
     1.x.1.k  <bairro: SHIS QI 26…>                      (só nas sub-DMC)
        REDE PRIMÁRIA | SECUNDÁRIA | TERCIÁRIA
           REDE PEAD DN <d> MM  (ou PVC, FºFº)
              EST. <a> ATÉ EST. <b>                     (só na sub-adutora)
                 TRECHO <nnn>
  1.x.2  SETORIZAÇÃO – ENTRONCAMENTOS  (REDE EXISTENTE / REDE NOVA; REDE NOVA / REDE NOVA)
  1.x.3  SETORIZAÇÃO – OBRA CIVIL  (CAIXA CONCRETO ARMADO: CX VENTOSA / VRP / MEDIDOR; CAIXA PRÉ-MOLDADO: CX DESCARGA)
  1.x.4  SETORIZAÇÃO – OBRA MECÂNICA  (montagem por caixa; interligação)
  1.x.5  SUBSTITUIÇÃO – REDES  (rede terciária DN 63)
  1.x.6  SUBSTITUIÇÃO – ENTRONCAMENTOS
  1.x.7  SUBSTITUIÇÃO – LIGAÇÕES PREDIAIS
1.9  DESMOBILIZAÇÃO DO CANTEIRO
1.10 FINAL DA OBRA                                     (marco)
```

- **% concluído por trecho:** 0, 50 ou 100 % no modelo, conforme o avanço do trecho. Os níveis acima consolidam a % (ex.: rede primária 69 %, sub-adutora 9 %, obra 4 %).
- **O sistema já lê o cronograma do Project (upload).** Para o RM, ele deve devolver a % concluída por trecho a partir do executado (mapa/OK) e registrar a revisão e a medição no título.

---

## 7. De onde vem cada dado no sistema Morro da Cruz (para automatizar)

| Peça do pacote | Fonte no sistema | Situação |
|---|---|---|
| Linhas da MC (trecho, estacas, dimensões) | NS do dia, croqui, OK interno do trecho (gaveta 1), apropriação direta | O site gera lançamentos por trecho. Ainda não existe a **folha de MC** no formato acima. |
| Galeria de fotos da MC | Fotos obrigatórias (sinalização, execução, concluído) e fotos do diário | Existem. Falta montar 6 por folha com o carimbo de data. |
| Justificativa técnica | Campo novo por linha ou folha, com frases padrão | Falta. |
| Quantidade da medição por item | Lançamentos da medição de TESTE (gavetas) | Existe com hipóteses (TESTE). |
| BM horizontal / juntada | BM REV04 importado + medição | O export .xlsx existe. Falta o **formato juntada** (filtrado, com resumo e % de saldo). |
| BM vertical e cronograma FF | Planilha "Cronograma FF Caesb" (aba LEV) + medição por grupo | Parcial. |
| Reajuste | `reajuste_indices`, D-55 | Bloqueado (hipótese). |
| Tabela 01/10/11/12 (equipes) | Usuários, equipes, terceiros, equipamentos | Parcial. |
| Gráficos 05/06 (efetivo) | Presença do dia (programação do dia / diário) | Depende do fluxo integrado. |
| Tabela 02 (tubos Caesb) | Almoxarifado: romaneio Caesb, retirada, aplicado | Romaneio existe. Faltam "emprestado" e "estoque virtual". |
| Tabela 07 (locação) | NS de topografia (trechos liberados) | Existe (azul no mapa). |
| Tabela 08 e Gráfico 11 (rede executada) | Executado por DN (mês e acumulado) | Existe nos dados. Falta o relatório. |
| Seção 11 (semanas) | Diário por NS + croqui + serviços | Parcial. |
| Anexo 19.3 e 19.3.1 | Mapa iluminado (mês, anterior, não executado) | Mapa existe. Falta exportar a imagem com a legenda e os metros. |
| Seções 3 a 7 | Cadastro do contrato (parâmetros) + totais da medição | Falta o cadastro de parâmetros do contrato. |

---

## 8. Calendário e prazos

- **Período de medição:** do dia 1 ao último dia do mês. A 1ª medição vai da OS (16/06/2026) até 31/07/2026: 46 dias corridos (o modelo diz 45).
- **Prazo decorrido** = (data de corte − data da OS) + 1 dia. Ex.: 16/06 a 31/08 = 77 dias.
- **Restante** = 540 − 77 = 463.
- **Vigência:** contar a partir do **marco contratual correto**. Se começar na OS, 655 dias vão até **31/03/2028**. O modelo diz "30/01/2028 (limite)", que só bate se a vigência começar em 16/04/2026, mas conta o decorrido a partir da OS. **Confirme no contrato.**
- **Data do relatório e do BM:** último dia do período (31-ago-26).

---

## 9. Regras de qualidade que o sistema deve aplicar

1. **Item acima de 100 % do contratado:** bloqueia o fechamento ou exige justificativa e marcação "aditivo pendente".
2. **Item medido sem folha de MC, ou folha de MC sem item:** erro.
3. **Linha da MC sem trecho, estaca ou foto:** aviso. A Caesb confere pela foto e pelo croqui.
4. **Estacas encadeadas:** a estaca inicial de uma linha deve ser a final da anterior (no MND e na locação). Buraco ou sobreposição gera alerta.
5. **Unidades:** o volume sai em M³. O modelo rotula a escavação como "M²", e isso é erro.
6. **Medição fechada:** congelada (preço, BDI, K, índice, quantidades). Uma revisão do BM depois do fechamento só gera alerta.
7. **Arredondamento:** `ROUND(…; 2)` por item. BDI por classe. K no total. **Não arredonde no meio do resumo.**
8. **Dados pessoais:** nomes de colaboradores só onde a Caesb exige (equipe de ADM e responsáveis técnicos), vindos do cadastro. O histograma usa matrícula ou iniciais.

---

## 10. Conferências cruzadas (o mesmo número em vários lugares)

| Número | Onde aparece | Deve ser igual a |
|---|---|---|
| Valor P0 da medição do mês (563.105,16) | BM (`TOTAL 01+02+BDI−K`, coluna do mês), RM §7, aba de reajuste, cronograma FF (executado do mês), Gráfico 01 (563,11 em R$/1000) | igual em todos |
| Acumulado P0 (747.172,04) | BM acumulado, RM §7, cronograma FF acumulado, Gráfico 03 | igual |
| Reajuste do mês e acumulado (50.740,20 / 67.326,07) | BM resumo de reajuste, aba de reajuste, RM §7, cronograma FF | igual |
| Saldo P0 (21.502.838,64) | RM §7, BM (`P0 − acumulado`), cronograma FF | igual |
| Reajuste total do contrato (2.004.900,80; 9,01 %) | BM coluna P0, RM §6 | igual |
| Locado acumulado (9.769,72 m) | Tabela 07, acumulado do item de locação com NS no BM | igual |
| Rede executada no mês e acumulada (1.687,03 / 2.250,00 m) | Tabela 08, item MND/assentamento no BM, Gráfico 11, legenda do anexo 19.3.1, % no cronograma do Project | igual |
| Aplicado de tubo Caesb (2.250 m DN 160) | Tabela 02, Tabela 08 | igual |
| Efetivo total (19) | Tabelas 10 e 11, Tabela 01 (mão de obra ativa) | igual |
| Equipamentos (14) | Tabela 12, Tabela 01 (equipamentos disponíveis) | igual |
| Extensão de cada semana | quadro da seção 11 (estacas), soma das linhas da MC daquela semana | igual |

---

## 11. Erros do modelo (não reproduzir)

**Datas e números de identificação:**
- Período no cabeçalho "01/08/26 a **31/08/25**" (págs. 1 a 10) e subseção "11.1 Período de 01/08/2026 até 09/08/**2025**".
- Tabela 02 com "CONTRATO: **9529/2022**" (copiada de outro contrato) e "% executado" do **total PEAD = 32,15 %**. Esse é o valor do DN 160; o total correto é 4,80 %, como na Tabela 08.
- Metadados do arquivo Word (título, assunto, autor) herdados de outro lote.

**Numeração e títulos:**
- Numeração das tabelas pula (01, 02, 07, 08, 09, 10, 11, 12) e a dos gráficos também (01–04, 05, 06, 11, 15).
- Título duplicado "12.2.1 **6.2.1** Materiais de Consumo Diário".
- O sumário escreve "DADOS GERENCIAis".
- O texto 16.7 fala em "indicador de **desenvolvimento** ambiental" (o certo é desempenho).

**Planilha:**
- Cronograma FF com rótulos "MÊS 01 e 02" seguido de "MÊS 02". O 1º período tem 46 dias, não 45.
- Escavação em "M²" (é M³) e reaterro descontando o tubo com o diâmetro no lugar do raio (§3.7).
- Ajustes manuais escondidos nas fórmulas dos totais (`−0,27`, `−0,11`, `−0,58`).
- Descrição da administração local cita "QI 28" (resto de orçamento parcial).
- Saldo negativo (1.486,88 %) sem nenhum alerta.

**Texto e anexos:**
- Legenda do anexo 19.3.1: o amarelo está como "REDE EXEC. ACUMUL. 2.250 m", mas o trecho amarelo é o **anterior** (562,97 m). Use 3 cores: mês, anterior, acumulado = soma.
- Rótulo "Valor faturado reajustado acumulado" para o que é só o reajuste acumulado.
- O anexo 19.2 traz o título "Relatório de Supervisão Ambiental nº 02" e logo depois diz que nenhum SAOB foi emitido. Use um título condicional.
- Texto padrão sobre COVID-19 (desatualizado). Revise os textos fixos a cada relatório.
- A página 19.3 (Mapa iluminado) saiu em branco.
- Vigência: data limite incoerente com a contagem (§8).

---

## 12. Parâmetros por contrato (não copie do Lago Sul)

| Parâmetro | Lago Sul (CT 10.159/2026) | Morro da Cruz (CT 10.239/2026) — conferir no repositório |
|---|---|---|
| Valor P0 do contrato | 22.250.010,68 | do BM REV04 importado |
| BDI material / serviço | 15,28 % / 21,48 % | do BM REV04 (por classe) |
| K (desconto) | −2,1 % | **−14,04 %** (`K = −1 + (1 − 14,04 %)`), matriz de regimes item 8 |
| Data-base / índice | 07/2024, ICCB-Brasília DI | **31/01/2025**, ICC-Brasília-DI, só **com pedido da contratada** |
| Reajuste | 9,0108 % (07/2026) | até 3,29 % (despacho CEFR), **frações elegíveis pendentes (D-55)** |
| Prazo / vigência | 540 / 655 dias | do contrato |
| Tubo da rede | PEAD Caesb (Tabela 02) | PEAD Caesb, **fora do BM** (matriz, item 1) |
| Limite por item | nenhum no modelo | **teto por subgrupo do BM vertical** (simulação, item 15) |
| Situação da medição | oficial | só **TESTE** até as decisões D-01, D-55 e D-56 |

---

## 13. Pendências deste skill

- **Documento de juntada do Drive:** não foi acessado. Pedir o PDF e registrar a ordem das peças, a folha de rosto, o ofício e as assinaturas (§4.1).
- **Anexos de imagem do RM:** organogramas, croquis semanais, layout do canteiro e mapa geral são imagens coladas. Definir quais o sistema gera (mapa, croqui, organograma a partir do cadastro) e quais o usuário anexa.
- **Reprogramação do cronograma FF:** o formato da série "reprogramado" ainda não tem exemplo preenchido.
- **SAOB/IDA:** a origem da nota (Caesb) e como ela entra no sistema.
