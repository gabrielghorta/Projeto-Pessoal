# Medição Caesb × Ankara e o pacote mensal no modelo oficial do BM

Referência da skill `sistema-morro-da-cruz`: as regras de cálculo do contrato, as gavetas, a conferência, o reajuste,
a administração local e o pacote mensal que o sistema gera no próprio BM REV04. O formato completo do modelo da Ankara
(Lago Sul: juntada, MC, cronograma FF, gráficos, relatório mensal) está em `modelo-lago-sul.md`.

## Medição: as regras Caesb × Ankara

### Cálculo (contrato 5.2, células do BM)

1. Total do item: `ROUND(quantidade × preço sem BDI; 2)` (arredondamento do Excel, metade para cima:
   6.026,69 × 47,50 = 286.267,775 → 286.267,78; `regras.produto_excel`).
2. Σ por classe (MATERIAL / SERVIÇO) → SUB-TOTAL 01.
3. BDI por classe (15,28 % / 21,48 %) → SUB-TOTAL 02. **Sem arredondar no meio.**
4. TOTAL 01 + 02; COEF. K = total × K; **P0 = (Σ + BDI) × (1 + K)**.
5. Reajuste por classe = i × (Σ classe + BDI classe) × (1 + K); total geral = P0 + reajuste.
- Contrato (coluna P0): `ROUND(SUMPRODUCT(quant.; preço))` por classe. Medição: ROUND por item.
- No vertical, o ROUND é por chave; na juntada, por código Caesb (a soma das chaves do mesmo código): podem diferir em
  centavos — mostrar como aviso, **nunca esconder ajuste numa fórmula** (o modelo do Lago Sul tinha −0,27, −0,11, −0,58).
- `regras.totalizar_bm(itens, bdi_material, bdi_servico, coef_k, modo)`.

### Lançamentos e gavetas

| Gaveta | O que entra | Quando |
|---|---|---|
| 1 | Serviços de trechos e nós (06.1 → item do BM por `config/servicos_rede.json`) | no OK interno |
| 2 | Materiais (regime pendente) | OK interno de nós; sempre PENDENTE (`MATERIAL_SEM_REGIME`) |
| 3 | Cadastro aprovado no GDOC (item `2.2_5.2.1`, pela extensão) | na etapa 6 da esteira (D-58, provisória) |
| 4 | Calçada/asfalto (`2.2_5.9.3`, `2.2_5.9.5`) | recomposição; item A CONFIRMAR → PENDENTE |
| 5 | Apropriação direta | item aprovado, de serviço, dentro do saldo do BM |

- **PROPOSTO** entra no valor; **PENDENTE** fica fora (com o motivo e a restrição). Serviços com item comprovado:
  assentamento (`2.2_` + código BM do trecho), escavações, esgotamento, locação com NS (`2.2_5.2.7`). Bloqueados:
  14 serviços sem item (D-50), solda (D-31, PENDENTE com as aprovadas), MND sem substituição (D-52), material (D-53,
  D-54). Escavação mecanizada em dois itens: rateio pela proporção contratual, hipótese (D-51).
- **Parcela única:** a mesma parcela (tipo|gaveta|serviço|alvo|item|unidade) não entra em duas medições (regra + índice
  único no banco); o mesmo alvo × serviço também é conferido sem o item.
- **Item a aprovar** (16 itens "XX" e itens novos): todo lançamento fica PENDENTE (`ITEM_A_APROVAR`) até o código
  oficial (`codigos_oficiais`) ou a aprovação; quando a restrição cai, **entra sozinho** (na medição aberta vira
  PROPOSTO; numa fechada, uma cópia entra na próxima aberta com `origem_id`).
- Painel **"Medível com restrição"**: valor parado por restrição (item a aprovar, acima do contrato, teto do subgrupo,
  material sem regime, cadastro esperando o GDOC, sem medição aberta), com a ação que libera e quem faz.
- **Teto por subgrupo** do vertical: hipótese (D-57); a simulação desconta o excedente.
- **Elegibilidade do período:** proposto nesta; OK interno esperando a medição; completo sem OK (com impedimentos);
  parcial não elegível (só trecho completo é proposto, D-30); medido antes.

### Conferência, fechamento e congelamento

- **Conferência interna da engenharia** (D-59, provisória): roteiro de 5 itens (executado, evidências, pendentes,
  duplicidade, hipóteses); grava o **retrato** das evidências e a **assinatura** dos lançamentos. CONFORME é recusada com
  duplicidade ou foto obrigatória ausente/inválida. Se um lançamento muda depois, a conferência deixa de valer.
- **Fechar** exige a última conferência CONFORME e vigente e **justificativa em todo item acima de 100 % do contrato**
  (D-144). Grava quem fechou e qual conferência liberou.
- **Medição fechada é congelada:** preço, classificação, item, BDI, K e o resumo gravados; revisão posterior do BM só
  gera alerta. Não há estorno de proposta nem reabertura (D-16).
- **Só existe medição de TESTE** (`medicao_oficial_liberada = NAO`, D-56). Ela lista as hipóteses não validadas.

### Material: regimes (SL0327) — bloqueado

Nada desta matriz está aplicado (`docs/MATRIZ_REGIMES_FATURAMENTO.md`): tubo da Caesb = só custódia (R$ 0 de
fornecimento); tubos da contratada 80 % (recebido + inspeção) / 20 % (implantado); eletromecânicos 20/15/40/15/10 %;
aço/ferro fundido 80/10/10 %; conexões PEAD sem regime documentado; regime normal depende da cláusula 2.16 do Edital.
**Sem 80/20 automático e sem 100 % na aplicação.** Recebido não é faturável.

### Reajuste

Contrato 6.1–6.4: preços fixos por 1 ano a partir de 31/01/2025; depois, ICC-Brasília-DI **com pedido da
contratada**, só para obrigações iniciadas e concluídas após a anualidade; reajustes seguintes contam dos efeitos
financeiros do último. CEFR: até 3,29 %. A aba REAJUSTE do BM pede a **fração elegível** de material e de serviço por
medição (zero = nenhuma parcela). **Decisão do responsável (D-140): no pacote, reajuste R$ 0,00, "não pedido"**
(fração 0). A revisão que vale para a parcela elegível (REV03 × REV04) segue pendente (D-55).

### Administração local (D-141, TR 14.6)

Igual à folha da ADM do modelo: `% ADM = ADM ÷ (subtotal 01 do contrato − ADM)`;
`faturamento do mês = Σ ROUND(quant. × preço; 2)` de material e serviço, sem BDI e sem a ADM;
`quantidade da ADM = faturamento × % ADM ÷ ADM` (fração de 1 UN); `valor = ROUND(quantidade × preço da ADM; 2)`.
Lançamento direto no item da ADM é ignorado. `pacote_medicao.adm_local`.

## O pacote mensal no modelo oficial do BM

O que a Caesb recebe é o **BM REV04 preenchido, no próprio arquivo** (`pacote_medicao.gerar`), com as fórmulas do
modelo (D-138). Tela Medição › "Pacote da medição no modelo oficial" › **Baixar pacote (.xlsx)**
(`GET /api/medicao/pacote/baixar?id=`). O "Resumo interno (.xlsx)" é outra coisa: a conferência interna.

**Cadeia de fórmulas preservada:**
```
nª MC (folha por item; chave em C7) ─SUMIFS(W; C; chave)─► vertical (coluna QUANT. do mês)
vertical ─SUMIFS por código Caesb─► juntada ─► resumo (BDI, K, reajuste) 
vertical ─SUMIFS por Cód. Cron. FF─► CRONOGRAMA FF CAESB ─► GRÁFICOS (4)
folha da ADM ─► vertical (linha 546)
```

| Aba | O que o sistema preenche |
|---|---|
| BM MORRO DA CRUZ (juntada) | linhas dos itens sem medição no mês ocultas (grupos/subgrupos visíveis se têm item medido); colunas das outras medições ocultas; uma página de largura em A4 paisagem (D-154) |
| BM … VERTICAL | coluna do mês = `IFERROR(SUMIFS('nª MC'!$W:…,'nª MC'!$C:…,$D<linha>),0)`; **medições anteriores como valor congelado** (D-152); meses seguintes 0; ADM do mês = `'nª MC'!$W$<linha da ADM>`; data do boletim |
| nª MC (renomeada `02ª MC`, `03ª MC`…) | uma folha de 92 linhas por item medido, na ordem do vertical, cada uma numa página; folha da ADM no fim |
| REAJUSTE | E/F = 0 de todas as medições até a do pacote; situação "NÃO PEDIDO NESTA MEDIÇÃO (R$ 0,00)" |
| CRONOGRAMA FF, GRÁFICOS, CONFERÊNCIA CONTRATO | só o nº do contrato; o resto são as fórmulas |
| AVISOS DO TESTE (nova, só no teste) | total, ADM e avisos (pendentes fora, aditivo pendente, período, arredondamento, teto) |

**Folha da MC (template linhas 1–92; ADM nas linhas 1841–1932 do modelo):** cabeçalho (FOLHA nnn, título, contrato,
período e nº da medição puxados do vertical, logo Ankara); linha do item (linha 7: chave em C, descrição, código,
classificação, unidade e total por INDEX/MATCH); **galeria** (linhas 9–24, colunas B a W: até 6 fotos lado a lado, com o
carimbo gravado numa faixa no pé — data, trecho, GPS, contrato); **justificativa técnica** (X9:X24 mesclada);
**memorial** (linhas 27–92, 66 linhas: CÓD. CRON. FF, descrição, NOMENCLATURA DA OBRA, PROJETO, EST. INICIAL + FRAÇÃO,
EST. FINAL + FRAÇÃO, PONTO REFERÊNCIA, DISTANCIA = (K×20+L)−(I×20+J), QUANT., UNID., SUB-TOTAL). Regras do sistema
(D-153): trecho inteiro em metro sai da estaca 0+0,00 até a estaca do fim, quantidade 1 (sem encadear estacas);
outras unidades, a quantidade direta (SUB-TOTAL = QUANT.) e o trecho, os nós e a extensão no ponto de referência;
mais de 66 linhas viram folha de continuação com a mesma chave. A folha da ADM lista a equipe administrativa ativa do
cadastro de usuários (D-156).

**Fotos e justificativa** (`medicao_folhas`, `POST /api/medicao/folha`, permissão `medicao`, medição aberta): o sistema
sugere as **6 fotos mais recentes** dos trechos e nós do item; a engenharia troca (até 6, na ordem do toque) ou volta à
sugestão; justificativa por frase pronta (`pacote_medicao.FRASES`) ou texto livre (até 600). Item acima de 100 % do
contrato: "ADITIVO PENDENTE" na folha e fechamento só com justificativa (D-142 a D-144).

**Marca TESTE – NÃO OFICIAL** (D-139): no título de cada aba, no cabeçalho de impressão de todas as páginas e no nome
do arquivo (`BM_MORRO_DA_CRUZ_01a_MEDICAO_TESTE_NAO_OFICIAL.xlsx`). Período no cabeçalho = o do modelo (da OS
01/10/2026, prazo 540 dias, na aba REAJUSTE); se o do sistema for outro, aviso (D-155). O pacote recusa um BM em
`planilhas/` diferente do importado (SHA-256, D-157).

**Por que editar o .xlsx por dentro (`xlsx_modelo.py`):** abrir e salvar pelo openpyxl perde ou altera desenhos,
logos, comentários e gráficos. O editor trata o arquivo como pacote: expande as fórmulas compartilhadas das abas
editadas (Translator), desloca as referências locais ao copiar blocos, remove os valores guardados das fórmulas e a
`calcChain`, liga `fullCalcOnLoad` e reconstrói os desenhos (logo por folha + fotos com âncora numa célula). Conferido:
ida e volta do modelo sem mudar nenhuma das 56 mil células recalculadas; o pacote recalculado no LibreOffice bate com
o sistema (P0 da juntada e do vertical, ADM, total geral, cronograma FF). No PDF do LibreOffice, logos e fotos descem
um pouco a cada folha (o modelo original também); **gere o PDF pelo Excel**.

**Conferências cruzadas (o mesmo número em vários lugares):** P0 do mês (BM, cronograma FF, relatório, gráfico R$/1000);
acumulado e saldo P0; reajuste; locado acumulado (= item de locação com NS); rede executada no mês e acumulada
(relatório, item de assentamento, mapa); aplicado de tubo Caesb; efetivo e equipamentos.

### Relatório mensal (fase 2, ainda não feito)

Word (cabeçalho com o logo da Ankara: contrato, nº do relatório, período — D-151), capa com o **mapa das zonas** como
no relatório de conexões das 11 zonas (não a ponte do Lago Sul, D-148). Estrutura de referência (Lago Sul): capa,
sumário, apresentação, identificação, empreendimento, dados contratuais, quadro resumo gerencial, dados gerenciais
(faturado, reajuste, saldo, prazos), desenvolvimento e canteiro, organogramas, atividades por semana (croqui com
executado/anterior/não executado e estacas), equipes e materiais (compatibilização de tubos Caesb), execução (locação
com NS; rede executada), próximo mês, cronograma FF e os 4 gráficos, histograma (efetivo por dia), observações,
relatório fotográfico (6 fotos por página), anexos (mapa iluminado e caminhamento da medição). Decisões já dadas:
dados fixos numa tela "Dados do contrato" preenchida uma vez (D-145); textos do mês completados no Word, nos lugares
marcados (D-146); presença diária marcada no sistema por RH ou supervisor (D-147); imagens fixas enviadas uma vez
(D-148); IDA/SAOB fora (D-149); cronograma do Project depois (D-150). Dados pessoais só onde a Caesb exige, vindos do
cadastro; histograma por iniciais ou matrícula. Falta o documento da juntada (o Drive não abriu).
