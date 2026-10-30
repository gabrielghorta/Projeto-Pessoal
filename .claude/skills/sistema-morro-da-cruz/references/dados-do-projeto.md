# Dados do projeto Morro da Cruz (CT 10.239/2026)

Referência da skill `sistema-morro-da-cruz`. Os números saem das planilhas oficiais em `morro-da-cruz/planilhas/`
(06.1 REV01, 06.2 REV08, BM REV04) e do mapa `mapa/PLANTAS_TRECHOS_E_NOS_MORRO_DA_CRUZ_REV02_EQUIPES.html`. Quando
precisar de um número que não está aqui, calcule a partir desses arquivos (o `cronograma_executivo/motor.py` tem
`ler_dados()` e `base()`, que já leem tudo) em vez de estimar.

Conteúdo: a obra e o contrato · quem é quem · arquivos oficiais · a rede em números (zonas, diâmetros, Subadutora,
caixas, ligações) · o BM REV04 por grupo · equipes e canteiro · glossário.

## A obra e o contrato

| Item | Valor |
|---|---|
| Objeto | Implantação de Redes de Distribuição no Morro da Cruz, São Sebastião/DF |
| Contrato | CT **10.239/2026**, Caesb (contratante) × Ankara Engenharia (contratada) |
| Licitação | LC 014/2026 · Juntada 1426 (RED.SSB-D014) |
| Valor do contrato (cláusula 3.1) | R$ 49.878.748,56 |
| P0 recalculado do BM REV04 | R$ 49.878.748,6575869 (= célula T556 do vertical). A diferença de +0,0975869 fica **registrada, nunca ajustada** |
| BDI | material **15,28 %**, serviço **21,48 %**, por classe |
| Coeficiente K | **−14,04 %**: `K = −1 + (1 − 14,04 %) = −0,1404` (contrato 5.2) |
| Data-base | 31/01/2025 (preços fixos por 1 ano); 1º aniversário 31/01/2026. O responsável conta com o reajuste do aniversário de **31/01/2027**: o cronograma faz o que começa a partir de 01/02/2027 entrar nele |
| Reajuste | ICC-Brasília-DI, **só com pedido da contratada**; até 3,29 % (Despacho 322/2026-CEFR, GDOC 2998208) |
| OS | 01/10/2026 · prazo **540 dias** · **18 medições** (pares de colunas no BM) |
| Administração local | item 4.1.1 (chave `6.2_4.1.1`), R$ 1.304.685,94, medida **proporcional ao faturamento do mês** (TR 14.6) |
| Rede | 1.436 trechos (linhas da 06.1), **110.686,03 m** de PEAD (1.400 Rede, 36 Adutora; 1.432 VCA, 4 MND); DE 63 a 500 |
| Tubo PEAD da rede | **fornecido pela Caesb**, fora do BM (SL0327 §6): a Ankara guarda, aplica e responde por perda; os serviços são medidos |
| Frentes | 13 no banco: Zona01 a Zona11, ADUTORA e CH (caixas hidráulicas). Nos mapas e no cronograma, a **Subadutora** (adutora + redes de DE ≥ 200 mm) é uma frente à parte (D-182) |
| Pranchas | 25 PBs (PB20 desenhada girada 90°; o vetor da PB25 está deslocado ~37,6 m no HTML) |
| Elementos (06.2) | 1.191 elementos físicos (1.059 nós + 132 dispositivos), 1.242 atividades (elemento × frente), 6.539 itens |
| BM REV04 | 347 itens na juntada, 432 no vertical |
| Ligações prediais | item de código Caesb 8005508120013 |

**Nomes:** a 06.1 nomeia `Zona01_PB01_Rede_TR001`; a tela mostra o nome completo `Zona 03 · PB06 · TR014`. "TR1" busca
o TR001 de cada PB (código inteiro, D-120). Os números de nó se repetem entre zonas e PBs (o NÓ1.1 aparece em 23
combinações): por isso o par de nós sozinho nunca identifica um trecho.

## Quem é quem

| Parte | Papel no sistema |
|---|---|
| **Caesb** (contratante) | Fiscaliza; manda a nota de serviço (NS) no formato dela; fornece o tubo PEAD (romaneio); aprova o cadastro no GDOC (memorando ESET); dá o código oficial dos itens provisórios ("XX") e aprova item novo por ofício; a CEFR comunica o reajuste; a área ambiental faz o SAOB/IDA. |
| **Ankara** (contratada) | Engenharia e Administração (tudo), Supervisor de campo (verifica e fotografa), Almoxarifado (estoque e notas), Equipes (encarregados), RH (consulta das NS). |
| **Terceirizadas** | Topografia (locação, NS de topografia) e empresa de cadastro (levantamento de campo e desenho do cadastro). **Não entram no sistema para registrar:** a engenharia registra por elas (D-66); os perfis TOPOGRAFIA e CADASTRO só consultam. |

**Cores com significado contratual:** o **verde** é só da Caesb (cadastro aprovado com memorando ESET). Verificação e
OK interno usam outras cores (rosa, roxo, azul) e dizem "conferência interna Ankara — não é aprovação da Caesb".

## Arquivos oficiais (no repositório, nunca alterados)

| Arquivo | O que é |
|---|---|
| `planilhas/06.1 - LEV_DMC_MORRO_DA_CRUZ_REDES_REV01_13-10-26.xlsx` | Os 1.436 trechos (aba REDE, cabeçalho na linha 5, chave `PONTO`): perfil de vala, quantidades por serviço (escavação por categoria, reaterro, escoramento, transporte, locação, cadastro), `DIST. CANTEIRO`, `CLASSIFICAÇÃO EXECUTIVA` (primária, secundária, terciária) |
| `planilhas/06.2 - LEV_DMC_MORRO_DA_CRUZ_CONEXÕES_REV08_13-10-26.xlsm` | Nós e dispositivos, atividades e as peças de cada um, com o item do BM |
| `planilhas/BM_MORRO_DA_CRUZ_REV04_IDENTIFICACAO_09-10-26.xlsx` | BM oficial: juntada, vertical (aba `BM MORRO DA CRUZ - VERTICAL`, itens nas linhas 6 a 547), 01ª MC, cronograma FF, reajuste, gráficos. Também é o modelo do pacote mensal |
| `planilhas/03.3.2 - BM_MORRO_DA_CRUZ_REV03_REAJUSTE_13-10-26.xlsx` | Data-base, aniversário e índice da CEFR |
| `planilhas/EVIDENCIAS_REV08_06.2_e_REV01_06.1_MORRO_DA_CRUZ.xlsx` | Conferência do agrupamento por handle, zona e status de posição |
| `mapa/PLANTAS_TRECHOS_E_NOS_MORRO_DA_CRUZ_REV02_EQUIPES.html` | Mapa técnico com satélite das 25 PBs. O objeto `const DADOS = {…}` (traçado, nós, peças, imagens) nunca é alterado; o bloco de código do fim só muda a pedido do responsável. Arquivo com fim de linha CRLF (`.gitattributes` o trata como binário): ao editar por script, preserve o `\r\n` |

Os documentos da obra (NS reais, contrato, TR, relatórios do Lago Sul) ficam numa pasta do Google Drive do
responsável, fora do repositório público. Peça o link quando precisar; o conector do Drive nem sempre abre a pasta.

## A rede em números

**Total:** 1.436 trechos, 110.686,03 m (1.400 Rede e 36 Adutora; 1.432 VCA e 4 MND), 1.059 nós e 132 dispositivos
(caixas). A **Subadutora** (adutora + DE 225 a 500) tem 132 trechos e 10.463 m.

**Por zona** (sem a Subadutora). Ligações estimadas pelo cronograma: as 11.894 do BM rateadas pelos metros de DE 63.

| Zona | Trechos | Metros | Ligações (est.) |
|---|---:|---:|---:|
| Zona 01 | 114 | 10.073 | 1.258 |
| Zona 02 | 117 | 8.171 | 1.152 |
| Zona 03 | 108 | 9.396 | 717 |
| Zona 04 | 94 | 6.903 | 775 |
| Zona 05 | 79 | 7.474 | 1.024 |
| Zona 06 | 107 | 7.574 | 838 |
| Zona 07 | 152 | 10.469 | 1.009 |
| Zona 08 | 71 | 4.925 | 574 |
| Zona 09 | 149 | 12.100 | 1.543 |
| Zona 10 | 99 | 7.173 | 983 |
| Zona 11 | 214 | 15.965 | 2.022 |
| Subadutora | 132 | 10.463 | — |

**Ordem das zonas pela distância do canteiro** (média da coluna `DIST. CANTEIRO` da 06.1, usada no cronograma):
06, 01, 04, 03, 10, 07, 05, 02, 08, 11, 09.

**Por diâmetro (DE, mm):**

| DE | 63 | 90 | 110 | 125 | 160 | 225 | 250 | 280 | 315 | 355 | 400 | 500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Trechos | 844 | 120 | 118 | 16 | 206 | 75 | 21 | 8 | 9 | 4 | 2 | 13 |
| Metros | 70.439 | 7.877 | 8.529 | 882 | 12.495 | 4.097 | 1.001 | 464 | 2.173 | 684 | 609 | 1.435 |

**Caixas (dispositivos da 06.2):** 45 DF, 26 VTF, 27 VM, 17 VRP, 11 MV e 6 HID = 132 (129 com posição no mapa; MV-11,
VTF-12 e VTF-16 ficam na bandeja, D-03). Símbolos nos mapas: nó = bola; DF ▼, VTF ▲, VM ■, VRP ◆, MV ⬢, HID ✚.

**Ligações prediais:** 11.894 no BM (tê de serviço 63 e tê de sela 63 × 20), item de código Caesb 8005508120013.

## O BM REV04 por grupo do cronograma FF (preço sem BDI)

| Cód. Cron. FF | Grupo | R$ sem BDI |
|---|---|---:|
| 1.1 | CANTEIRO - MATERIAL | 588.692,86 |
| 1.2 | CANTEIRO - SERVIÇO | 578.135,17 |
| 2.1 | REDES - MATERIAL | 1.083.366,32 |
| 2.2 | REDES - SERVIÇO | 28.341.359,98 |
| 3.1 | CAIXAS - MATERIAL | 328.293,03 |
| 3.2 | CAIXAS - SERVIÇO | 1.169.456,85 |
| 4.1 | LIGAÇÕES - MATERIAL | 11.043.381,57 |
| 4.2 | LIGAÇÕES - SERVIÇO | 2.076.793,20 |
| 5.1 | HIDROMECÂNICO - MATERIAL | 2.019.878,84 |
| 5.2 | HIDROMECÂNICO - SERVIÇO | 264,48 |
| 6.2 | ADMINISTRAÇÃO LOCAL | 1.304.685,94 |
| | **Soma dos 432 itens do vertical** | **48.534.308,24** |

O subtotal 01 do contrato é R$ 48.534.308,16 (ROUND por código Caesb na juntada; a soma por chave do vertical dá
centavos a mais: mostre a diferença como aviso, nunca a esconda numa fórmula). Com BDI por classe e K, o P0 é R$ 49.878.748,66. A administração local é 2,7624 % do
faturamento sem BDI do mês: `1.304.685,94 ÷ (48.534.308,16 − 1.304.685,94)`.

## Equipes e canteiro (planejamento de 29/10/2026)

| Equipe | Empresa | Entra | Faz |
|---|---|---|---|
| Equipe Adutora (Ankara 1) | Ankara | 16/11/2026 | DE 160 das zonas no "pé alto" até jan/2027; a Subadutora a partir de 01/02/2027; depois, as zonas |
| Empreiteiro 1 · Equipes A e B | Empreiteiro 1 | 04/01/2027 | Rede das zonas (sem zona fixa) |
| Empreiteiro 2 · Equipes C e D | Empreiteiro 2 | 01/04/2027 | Rede das zonas (sem zona fixa) |
| Equipe Caixas e Hidromecânico (Ankara 2) | Ankara | 01/03/2027 | Obra civil das caixas; montagem hidromecânica a partir de 01/07/2027 (peças de SP e importadas) |

Produtividade esperada pelo responsável: 80 a 100 m/dia por equipe, em dia sem interferência. Trabalho de segunda a
sexta, das 7h às 17h.

**Canteiro em out/2026 (informado em 29/10/2026):** só a demarcação, o alambrado metálico, o portão e 2 contêineres.
A NS de topografia ainda não tinha sido feita (ficou para 03 a 13/11/2026).

## Glossário

| Termo | Significado |
|---|---|
| 06.1 (LEV REDES REV01) | Planilha dos trechos: perfil de vala, quantidades (colunas AL:BK), pontas UTM, handle CAD, código do BM. **Unidade da medição e do BM.** |
| 06.2 (LEV CONEXÕES REV08) | Planilha das conexões: elementos, atividades, itens com quantidade, unidade pelo item da juntada, avisos AA/AB. |
| EVIDÊNCIAS REV08 | Conferência do agrupamento por handle, zona, status de posição, ID da auditoria. |
| BM REV04 | Boletim de medição oficial do Morro da Cruz: juntada (horizontal), vertical, 01ª MC, cronograma FF, reajuste, gráficos e conferência. Também é o **modelo** do pacote mensal. |
| 03.3.2 BM REV03 REAJUSTE | Data-base, aniversário e índice da CEFR. |
| REV02 (HTML) | `PLANTAS_TRECHOS_E_NOS_MORRO_DA_CRUZ_REV02_EQUIPES.html`: mapa técnico com satélite das 25 PBs. O `DADOS` (traçado, peças, imagens) **nunca é alterado**; o servidor injeta a camada. O bloco de código do fim só muda a pedido do responsável (29/10/2026: frente Subadutora e formas dos dispositivos, D-182/D-183). |
| BM juntada (horizontal) | Uma linha por item do orçamento Caesb e colunas por medição; é a peça anexada ao processo. |
| BM vertical | Os mesmos itens repetidos por frente × material/serviço × categoria; chave `CódCronFF_ItemBM` (ex.: `2.2_5.8.44`). Alimenta o cronograma FF. |
| nª MC | Memória de cálculo do mês: uma folha por item medido (fotos, justificativa, memorial). |
| Cód. Cron. FF | Grupo do cronograma físico-financeiro (ex.: `2.2` REDES – SERVIÇO, `6.2` ADMINISTRAÇÃO LOCAL). |
| Código Caesb | Código da composição; liga o vertical à juntada. Só números = base Caesb; com "SI" = SINAPI; com "SC" = SICRO (todos contratuais); com "XX" = provisório (a aprovar). |
| P0 | Preço original, sem reajuste. |
| NS | Nota de serviço da Caesb (PDF; planilha opcional .xlsx/.xls). Tipos no sistema: topografia, cadastro, serviço de obra e NS do dia (execução). |
| Estaca | 20 m: `EST. 3+16,55` = 3 × 20 + 16,55 = 76,55 m. |
| VCA / MND | Vala a céu aberto / método não destrutivo (furo direcional; não tem vala, nem escavação nem reaterro). |
| Trecho físico | Cadeia de linhas da 06.1 entre duas conexões reais (`topologia.py`); a NS vai de conexão a conexão. |
| OK interno | "[✓] OK" da Ankara: trecho pronto para a medição; não é aprovação da Caesb. |
| Esteira | Etapas do cadastro até o GDOC (1 a 6). |
| GDOC / ESET | Sistema de documentos da Caesb / memorando que registra a aprovação do cadastro. |
| Gaveta | Grupo de lançamentos da medição (1 a 5; veja `medicao-caesb.md`). |
| PROPOSTO / PENDENTE | Lançamento com item e regra com fonte (entra no valor) / sem item ou regra (fora do valor; **não é R$ 0 contratual**). |
| Romaneio | Entrada de tubo da Caesb (sem compra, sem quarentena de compra). |
| Quarentena | Material entregue e ainda não aceito na inspeção: **não é estoque**. |
| SL0327 | Norma de faturamento de material por etapas (80/20, 20/15/40/15/10, 80/10/10). |
