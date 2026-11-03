# Cronograma físico executivo (REV00 de 29/10/2026, REV01 e REV02 de 30/10/2026)

Referência da skill `sistema-morro-da-cruz`. O cronograma foi feito para a reunião do responsável com a chefia em
29/10/2026, como "norte" da obra. Ele **não** está no web app: é um conjunto de scripts em
`morro-da-cruz/cronograma_executivo/`, que leem as planilhas oficiais e o REV02 e geram os arquivos.

A **REV02** (30/10/2026) é a mais nova: a REV01 com a análise crítica, a validar pelo responsável. A **REV01** (só o
cenário B, a obra saindo do reservatório da Zona 11) continua guardada e gera igual; ela mantém todas as regras da REV00
(seções depois da REV01, que continuam valendo) e muda só a ordem.

## REV02 (30/10/2026): a REV01 com a análise crítica

**Pedido.** Reformular a REV01 com a crítica, seguindo as regras: pé alto até o reajuste só com a equipe própria da
Ankara (DE 160 da Zona 11, depois o DE 225 dela), começando perto do reservatório; Empreiteiro 1 com 2 equipes em
04/01/2027; Empreiteiro 2 com 2 equipes em **01/03/2027** (antes era abril); antecipar as peças das caixas da Subadutora;
as ligações pelas próprias equipes de empreiteiro, ~20 por dia; se passar de 23/03/2028, mostrar o atraso (a solução vem
depois); aluguel de contêiner do que está no canteiro (82 % do item na REV01; 100 % na REV02, porque a obra fica mais
longa).

**O que muda (`rev02.py`; opções novas do `motor_rev01.py`, que com os padrões deixam a REV01 igual).**
- Calendário: recesso de 22/12 a 02/01 e 4 dias úteis de chuva por mês de out a abr, um em cada quarto do mês
  (`motor.aplicar_chuva_e_recesso`, que muda `FERIADOS` e `CAL` no processo: o Project leva os dias como não úteis).
- `prod_por_de`: 90 m/dia até DE 160; 60 de DE 225 a 315; 45 de DE 355 a 500 (o pé alto continua a 60).
- `entrada_meia_dias` = 5 (cada empreiteiro rende a metade na 1ª semana); `troca_frente_dias` = 0,5 dia por troca de zona.
- `ligacoes_por_dia` = 20: a equipe que assenta o trecho de DE 63 faz as ligações dele logo depois (`lig_fim`), e só
  então pega o próximo; a planilha fatura as ligações nesse intervalo.
- `hidro_caminho_antes` e `interlig_por_caminho`: as caixas do caminho da água (Subadutora inclusive) montadas logo depois
  da obra civil; a interligação de cada frente espera só o caminho até ela (o pedaço da Subadutora testado e as caixas
  desse caminho), e não todas as caixas que encostam na frente. Na REV01, a Subadutora inteira esperava o MV-02 (entrada
  da Zona 02, pronto em 10/11/2027), e por isso nenhuma zona podia receber água antes de 18/11/2027.
- Teste hidrostático no fim da zona; a desinfecção vai para os dias antes da entrada em carga (que depende do
  reservatório); marcos "pedir o reajuste" em 01/02/2027 e 01/02/2028 no Project.

**A cascata (uma mudança de cada vez, acumulando; `rev02_cascata.py`).**

| Mudança | Fim da obra | Folga |
|---|---|---|
| REV01 como está | 20/03/2028 | +3 |
| + Empreiteiro 2 em 01/03/2027 | 07/03/2028 | +16 |
| + recesso e chuva | 19/05/2028 | −57 |
| + produtividade pelo diâmetro | 08/06/2028 | −77 |
| + 1ª semana a meia produtividade | 13/06/2028 | −82 |
| + meio dia por troca de frente | 20/06/2028 | −89 |
| + ligações pelas equipes (20/dia) | 10/01/2029 | −293 |
| + caixas do caminho antes e interligação pelo caminho (= REV02) | 10/01/2029 | −293 |

**Resultado (REV01 → REV02).** Fim 20/03/2028 → **10/01/2029** (−293 dias; 28 medições); Subadutora até 06/07/2027 →
16/11/2027; Zona 11 pronta para receber água 18/11/2027 → **28/07/2027**; faturado até jan/2027 R$ 2,85 mi → R$ 2,03 mi
(4,1 %: a chuva e o recesso tiram dias do pé alto, que só faz o DE 160 e parte do DE 225 da Zona 11); outubro igual
(R$ 102,8 mil); maior mês ago/2027, R$ 4,53 mi → R$ 3,28 mi; total R$ 49,79 mi → R$ 49,88 mi (o aluguel de contêiner
chega a 100 % com a obra mais longa); prontos antes de ligados: 34 trechos (2,1 km) → 37 (3,0 km).

**O que mais pesa:** as ligações pelas equipes de rede (11.894 a 20 por dia = 595 dias de equipe, ~7 meses) e a chuva
com o recesso (~2,5 meses). Próximo passo sugerido: comparar com equipes só de ligação (a opção `ligacoes_por_dia`
volta a `None` e as ligações viram recurso próprio).

**Gerar:** `bash gerar_rev02.sh [pasta]` (~2 min; roda a cascata, a REV01 para o quadro, a REV02, a animação e
`conferir_rev01.py PASTA REV02 REV01`). Conferido em 30/10/2026: nenhum erro de fórmula com a data em branco e com data
de teste; juntada = soma das equipes nos 347 itens; outubro R$ 102.802,80; a REV01 continua gerando os mesmos números.

Conteúdo: REV01 (a regra nova, decisões, resultado, arquivos, como gerar, pendências) · REV00: o que foi entregue ·
como gerar de novo · resultado dos dois cenários · regras do responsável · decisões tomadas (e o porquê) · o que o
responsável ainda deve validar · como o motor funciona · faturamento na planilha · o arquivo do Project · como mudar
uma premissa · próximos passos.

## REV01 (30/10/2026): a obra sai do reservatório

**Por quê.** Rede sem pressão interna pode quebrar ou lascar, e a água vem só do reservatório da Zona 11. A obra
avança do reservatório para fora, pelo caminho da água, para cada trecho pronto já ficar ligado a ele por rede pronta.
O reservatório ainda vai ser licitado: **sem data de operação e sem carga provisória** (nada de by-pass ou outra
fonte). A data nunca é inventada: fica em branco (PREMISSAS!C13, nome `DATA_RESERVATORIO`).

**A regra.** LIGADO AO RESERVATÓRIO EM = quando fica pronto o último trecho do caminho até a saída (o caminho que liga
primeiro: Dijkstra de gargalo em `rede_agua.ligado_em`). ENTRADA EM CARGA = a maior entre a operação do reservatório,
o caminho pronto, testado e desinfetado, as caixas do caminho montadas (VRP, VM, VTF, DF, MV) e a zona testada e
interligada (`motor_rev01.carga_detalhe`). DIAS SEM CARGA = ENTRADA EM CARGA − TÉRMINO, em branco sem a data. Meta:
nenhum trecho pronto fora da ligação, a não ser a frente em execução.

**O grafo da água (`rede_agua.py`).** Vértices: a peça do REV02 em cada ponta (iniE/fimE); as junções JUNTAR do
`config/topologia.json` (divisa de zona, emenda sem nó, cruzamento e passagem não se ligam ao nó); as pontas soltas
pela coordenada (folga de 1,0 m); as peças no meio da linha (e['tr'] e as pendências CONEXAO_NO_MEIO_DA_LINHA); o
reservatório é um vértice só, ligado às pontas de saída. A Zona 11 **não** encosta no DE 500 (as curvas de 90° do
tronco; o 1º tê é o NÓ51.1 na PB17): ela sai pelos DE 225 TR080 (oeste, VM-11.2) e TR077 (leste, VM-11.1). Com as 4
saídas, os 1.436 trechos ficam ligados.

**Decisões do responsável (30/10/2026).**
- 4 saídas (o projeto está errado; corrigir com a Caesb e o engenheiro sênior): TR005 e TR006 (DE 500; o TR006, 2,4 m
  solto nas duas pontas, é a 2ª saída de DE 500), TR080 e TR077 (DE 225). O lado leste da Zona 11 conta como ligado
  pelo TR077.
- Pé alto "DE 160 primeiro": DE 160 da Zona 11 (16/11 a 21/12/2026), depois o DE 225 dela (até 15/01/2027) e o
  DE 90/110 (até 01/02/2027), a 60 m/dia. O DE 160 feito antes do DE 225 que o alimenta espera a ligação.
- Teste e interligação por zona, como na REV00 (a aba CARGA mostra os 48 setores entre registros para o futuro).
- Hidromecânico a partir de jul/2027, sem antecipar peças do caminho.

**A ordem (`motor_rev01.py`, padrões de `OPCOES` = as decisões acima).**
- Zonas na ordem em que a água chega: **11, 09, 07, 06, 10, 05, 08, 03, 02, 01, 04** (metros de tubo da saída até o
  1º trecho de cada uma).
- Subadutora a partir de 01/02/2027: TR005 primeiro e, zona por zona, o caminho de cada uma em profundidade (com o
  trecho de montante sempre antes).
- Blocos zona × PB × classe, cortados nos pedaços ligados entre si (pedaço < 150 m junta no vizinho da mesma classe).
  Cada equipe livre pega o bloco já ligado (ou o que liga primeiro); entre os já ligados: a zona onde ela está, depois
  a ordem da água e, na zona, secundária antes de terciária. Dentro do bloco, da alimentação para as pontas.
- Na geração (30/10) o desempate mudou: antes a classe vinha antes da zona e havia uma espera de até 10 dias úteis na
  zona da equipe; sobravam pedaços das Zonas 06 e 07 para jan/2028 e o fim ia a 31/03/2028. Seguindo a ordem da água
  (como o pedido diz) e sem a espera: fim em 20/03/2028, faturamento até jan/2027 igual, menos trechos esperando
  ligação. Custo: cerca de 50 trocas de zona das equipes (13 para pedaços < 300 m).
- Caixas: as do caminho da água primeiro (civil a partir de mar/2027; montagem a partir de jul/2027, entre as que têm
  a obra civil pronta, as do caminho primeiro).

**Resultado (REV00 B → REV01).**

| | REV00 B | REV01 |
|---|---|---|
| Fim da obra | 12/04/2028 (−20 dias) | **20/03/2028 (+3 dias)** |
| Subadutora | 01/02 a 21/07/2027, da ponta da Zona06_PB12 | 01/02 a 06/07/2027, do TR005 para fora |
| Rede da Zona 11 | 07/10/2027 a 12/01/2028 | 16/11/2026 a 29/04/2027 |
| Fim da rede / das caixas | 24/02/2028 / 17/02/2028 | 01/02/2028 / 02/02/2028 |
| Faturado até jan/2027 (P0) | R$ 2,89 mi (5,8 %) | R$ 2,85 mi (5,7 %) |
| Outubro/2026 | R$ 102,8 mil | R$ 102,8 mil |
| Maior mês | jul/27, R$ 4,56 mi | ago/27, R$ 4,53 mi |
| Medições | 19 | 18 |
| Prontos antes de ligados (mesmo grafo) | 932 trechos, 67,9 km; 188 km × mês | 34 trechos, 2,09 km; 0,71 km × mês |
| Rede pronta sem carga, data em branco | 1.058 km × mês | 949 km × mês (fórmula da data) |
| DIST. CANTEIRO média até jul/2027 | 2,89 | 3,98 (o deslocamento não está no modelo) |

Os 34 da REV01: 21 são o DE 160 do pé alto esperando o DE 225 (decisão de 30/10, até 29,5 dias úteis); 8 são a
frente em execução de outra equipe; 5 esperam uma frente que começa logo depois (poucos dias úteis). Lista com o motivo
na aba CARGA (seção 6) e nas colunas S e T da PROGRAMAÇÃO.

**Arquivos** (`MPXJ=1 bash gerar_rev01.sh [pasta]`, ~1 min; `conferir_rev01.py` roda no fim):
- `CRONOGRAMA_MORRO_DA_CRUZ_REV01_B_90M_DIA.xlsx`: as abas da REV00 e: PREMISSAS com a C13 amarela em branco, a
  regra, as decisões, o quadro REV00 × REV01 e as pendências; PROGRAMAÇÃO com LIGADO AO RESERVATÓRIO EM, PRONTO PARA
  CARGA, ENTRADA EM CARGA e DIAS SEM CARGA (fórmulas de `DATA_RESERVATORIO`), o motivo de cada exceção, a distância
  da saída e o setor; caixas com "no caminho da água"; aba **CARGA** (zonas na ordem da água com alimentação, caminho,
  caixas, teste, interligação e carga; mês a mês; zonas × meses; o caminho trecho a trecho; caixas do caminho;
  exceções; setores). O gráfico do RESUMO junta canteiro e administração local numa série cinza.
- `….xml` (2.561 tarefas): a REV00 trecho a trecho e o resumo "LIGAÇÃO AO RESERVATÓRIO E ENTRADA EM CARGA": o marco
  **"RESERVATÓRIO EM OPERAÇÃO - DATA A DEFINIR"** é manual e sem data (StartText "a definir"; o Project não o usa
  até alguém pôr a data); para cada frente, "LIGADA AO RESERVATÓRIO" (predecessoras: a última tarefa de cada equipe
  entre os trechos da frente e os do melhor caminho até a saída) e "EM CARGA (DEPOIS DA OPERAÇÃO DO RESERVATÓRIO)"
  (ligada, reservatório, teste e interligação de cada frente do caminho, montagem de cada caixa do caminho). Sem a
  data, o "em carga" mostra quando a frente fica pronta para carga. Para pôr a data no Project: digite a data no marco
  do reservatório (ou agende-o automaticamente com "Não começar antes de").
- `…_GANTT.pdf` (A3, 1 página): equipes mês a mês, a linha do reservatório com as 4 saídas, as zonas na ordem da água
  com uma faixa por equipe, o teste, a interligação e o marco "zona toda ligada".
- `AVANCO_MORRO_DA_CRUZ_REV01_ANIMACAO.html`: só o cenário B; o reservatório marcado; cor por situação (padrão) ou
  por equipe; campo da data de operação (simulação, em branco = nada em carga); contadores de km executados, ligados,
  prontos e não ligados e em carga; zonas sem cor, com o nome e a ordem da água escritos.

**Cores (`paleta_rev01.py`).** CIEDE2000 ≥ 20 em todo par de cada legenda (com as linhas do reajuste e do término) e
aprovadas no `validate_palette.js` da skill dataviz (todos os pares; fundo escuro #0D0F11 e branco):
- Equipes: Adutora #21A4B1 · Emp. 1 A #CA460D · Emp. 1 B #AE903C · Emp. 2 C #388149 · Emp. 2 D #8F73F5 · Ankara 2
  #A75791 (menor par 20,3). Canteiro e administração local #8C8C8C.
- Situações: não iniciado #6E6E6E (tracejado) · em execução #BA5C1F · executado não ligado #9465A3 · executado ligado
  (aguardando água) #A09809 · em carga #26A7AD (menor par 22,7).
- Linhas: reajuste #1A97F4, término #E75E6A, cursor #EEF1F3. Caixas na animação: contorno (obra civil), #A9AFB6
  (pronta), #F4F6F8 (montada).

**Conferências (item 11, `conferir_rev01.py`).** Recálculo no LibreOffice sem nenhum erro com a data em branco e com
01/12/2027 (o arquivo entregue fica em branco); juntada = soma das equipes nos 347 itens; outubro R$ 102.802,80;
quadro REV00 × REV01 nas PREMISSAS. Itens abaixo de 100 % (premissa herdada da REV00, a decidir): aluguel de
contêiner 6.1.1 a 6.1.3 em 82,1 % (o aluguel conta da chegada ao fim da obra; REV00 B: 87,7 %) e, por consequência,
a administração local 4.1.1 em 99,8 %.

**Pendências da REV01.** Confirmar as 4 saídas com a Caesb e o engenheiro sênior (no projeto o TR077 não encosta no
reservatório e o TR006 está solto; se o leste da Zona 11 não puder sair pelo TR077, a ordem muda); preencher a C13
quando houver a data; decidir o aluguel de contêiner (manter abaixo de 100 % ou faturar o saldo).

## REV00: o que foi entregue

Para cada cenário (A: prazo; B: 90 m/dia):

| Arquivo | O que é |
|---|---|
| `CRONOGRAMA_BASE_MORRO_DA_CRUZ_<A_PRAZO|B_90M_DIA>.xlsx` | Modelo do BM por equipe. Abas: PREMISSAS (parâmetros nas células amarelas, comparativo dos cenários, regras e premissas), BM POR EQUIPE (o vertical com um bloco por equipe, quantidade e valor por medição), BM CONSOLIDADO (a juntada somando as equipes, com BDI e K), CRONOGRAMA FF (modelo Caesb, por grupo), RESUMO POR EQUIPE (faturamento mensal, produção física, gráficos), PROGRAMAÇÃO (datas de cada trecho e caixa) |
| `….xml` | MS Project (MSPDI): Equipe › Zona · PB › os trechos com o nome da 06.1, cada caixa, cada montagem, as NS de topografia, os fechamentos; linha de base salva; 23/03/2028 como data limite. Cerca de 1.940 tarefas |
| `…_GANTT.pdf` | Gantt resumido por equipe e por zona, A3 deitado, para quem não tem o Project |
| `AVANCO_MORRO_DA_CRUZ_ANIMACAO.html` | O Mapa iluminado sendo preenchido dia a dia pelos dois cenários, com a régua do faturamento mensal. Abre com dois cliques, sem internet |

Também foi publicada uma versão da animação como artefato no claude.ai (privada, do responsável).

## Como gerar de novo

```bash
cd morro-da-cruz/cronograma_executivo
bash gerar_tudo.sh                 # saída em ./saida (fora do Git); ou: bash gerar_tudo.sh /outra/pasta
MPXJ=1 bash gerar_tudo.sh          # também regrava o XML pelo MPXJ (pip install mpxj; precisa de Java)
```

Leva cerca de 3 minutos (o cenário A procura a produtividade por bisseção, ~10 programações). Sem Node/Playwright, o
Gantt fica em HTML (imprima em A3 deitado). As fórmulas do xlsx são calculadas ao abrir no Excel; para conferir sem o
Excel, recalcule no LibreOffice (`soffice --headless --convert-to xlsx`) e procure `#REF!`, `#VALUE!` etc. A última
geração deu 0 erros de fórmula, e uma CPM independente sobre o XML deu 0 divergências.

**Abrir o XML no Project** (o Project vem configurado para recusar XML):
1. Arquivo › Opções › Central de Confiabilidade › Configurações da Central de Confiabilidade › **Formatos Herdados**.
2. Marque "Permitir carregamento de arquivos com formatos herdados ou não padrão" › OK.
3. Arquivo › Abrir, tipo **Formato XML (*.xml)**, "Como um novo projeto"; depois salve como .mpp.

Com dois cliques o Windows abre o XML no navegador; no celular não abre. O .mpp não é gerado por aqui.

## Resultado dos dois cenários

| | A – prazo contratual | B – ritmo médio |
|---|---|---|
| Produtividade das frentes de rede depois do reajuste | **95,0 m/dia** (a menor que fecha no prazo, de 0,5 em 0,5) | 90 m/dia (meio da faixa de 80 a 100) |
| Fim da obra | **23/03/2028** (folga 0) | 12/04/2028 (20 dias de atraso) |
| Fim da Subadutora | 13/07/2027 | 21/07/2027 |
| Fim da rede das zonas | 04/02/2028 | 24/02/2028 |
| Fim das caixas e do hidromecânico | 28/01/2028 | 17/02/2028 |
| Faturado até jan/2027, antes do reajuste (P0) | R$ 2,97 mi (5,96 %) | R$ 2,89 mi (5,80 %) |
| Mês de maior faturamento (P0) | 11ª medição, ago/27: R$ 4,78 mi | 10ª medição, jul/27: R$ 4,56 mi |
| Outubro/2026 (P0) | R$ 102,8 mil | R$ 102,8 mil |
| Total programado (P0) | R$ 49,79 mi | R$ 49,82 mi |
| Medições | 18 | 19 |

O total fica abaixo dos R$ 49,88 mi do contrato porque o aluguel de contêiner é contado da chegada de cada um (82 % do
item do BM, cerca de R$ 84 mil a menos).

## Regras do responsável (29/10/2026)

- 5 equipes de rede: 1 equipe Ankara (a da adutora) e 2 empreiteiros com 2 equipes cada nas zonas. As caixas ficam
  com uma 2ª equipe Ankara.
- **Pé alto até o reajuste de janeiro de 2027:** faturar pouco no começo. Até lá, só a equipe da adutora, em redes de
  160 mm (não classificadas como adutora), produzindo pouco.
- O 1º empreiteiro entra em janeiro de 2027 com 2 equipes; o 2º em abril de 2027.
- Produtividade de 80 a 100 m/dia por equipe, em dia sem interferência.
- Caixas hidráulicas a partir de março de 2027, com redes já feitas; hidromecânico a partir de julho de 2027 (peças de
  SP e do exterior, compradas com o que a obra fatura).
- Depois do reajuste, a equipe da adutora vai para onde for melhor; os empreiteiros não têm zonas definidas.
- As ligações prediais acompanham a rede.
- Segunda a sexta, 7h às 17h.
- Dois cenários: um que fecha no prazo e um que mantém a média.
- Em outubro/2026, só demarcação, alambrado metálico, portão e 2 contêineres (a primeira versão punha R$ 446 mil em
  outubro e foi corrigida).
- Entregáveis: Project e xlsx no modelo do BM, dividido por equipes.

## Decisões tomadas (e o porquê)

1. **Calendário:** 9 h/dia (07–12 e 13–17), sem os feriados nacionais e do DF (Carnaval, Sexta-feira Santa, Corpus
   Christi, 21/04, 30/11). Sem recesso de fim de ano e sem desconto por chuva.
2. **Cenários:** B usa 90 m/dia; A usa a menor produtividade que fecha em 23/03/2028 (95 m/dia, perto do teto, sem
   folga). A mesma produtividade para todos os diâmetros, do 63 ao 500.
3. **Equipe Adutora:** começa em 16/11/2026 (a NS de topografia fica de 03 a 13/11). No pé alto, até 29/01/2027, faz
   60 m/dia nos trechos de DE 160 das zonas que serão atacadas primeiro, para a rede principal estar pronta quando os
   empreiteiros chegarem. Em 01/02/2027 vai para a **Subadutora** (10,5 km): é o trabalho mais caro (fatura já com
   reajuste) e nenhuma zona entra em carga sem a Subadutora testada. Depois, apoia as zonas.
4. **Zonas e empreiteiros:** zonas da mais perto para a mais longe do canteiro (06, 01, 04, 03, 10, 07, 05, 02, 08,
   11, 09). Cada zona em blocos por prancha (zona × PB), da PB mais perto para a mais longe. Cada bloco vai para a
   primeira equipe livre, que prefere continuar na mesma zona. Dentro do bloco: primária, secundária, terciária, do
   maior diâmetro para o menor.
5. **Ligações (11.894):** só nos trechos de DE 63 (o BM usa tê de serviço 63 e tê de sela 63 × 20), pelo
   comprimento; a mesma frente, 5 dias úteis atrás da rede; não reduzem os metros por dia.
6. **Caixas (132):** a obra civil começa depois dos trechos que chegam na caixa. Dias de obra civil: DF 1, VTF 1,5,
   VM 2, VRP 3, MV 3, HID 0,5. Montagem hidromecânica como frente separada da Ankara 2, a partir de 01/07/2027: DF,
   VTF e HID 0,5; VM 1; VRP e MV 2. As conexões de PEAD dos nós (tês, curvas, luvas), que o BM põe no grupo
   hidromecânico, vão com a rede; só as peças das caixas (válvulas, VRP, macromedidor) esperam julho.
7. **Fechamento de cada zona:** teste hidrostático e desinfecção de 10 dias úteis depois do último trecho; entrada em
   carga (interligação) de 3 dias, só depois do teste da zona, do teste da Subadutora e da montagem das caixas da
   zona; cadastro técnico 30 dias corridos (22 úteis) depois de cada trecho; desmobilização de 10 dias no fim.
8. **Canteiro:** outubro só com o que foi feito; o resto das instalações de 03/11 a 18/12/2026. Contêineres: 2 em
   out/26, +4 em nov/26, +6 em jan/27, +6 em abr/27; o aluguel conta da chegada ao fim da obra. Custos mensais do
   canteiro (gerador, banheiro químico, consumo, infraestrutura da fiscalização) a partir de novembro.
9. **Faturamento:** material faturado na aplicação; valores em P0 (sem reajuste); administração local proporcional ao
   faturamento do mês (2,7624 %, TR 14.6).
10. **MND:** os R$ 1,2 mi de furo direcional do BM ficaram com os trechos do mesmo diâmetro (os 4 trechos MND da 06.1).

## O que o responsável ainda deve validar

1. 60 m/dia no pé alto (define os R$ 2,97 mi até janeiro).
2. A Subadutora logo depois do reajuste, antes de apoiar as zonas.
3. 95 m/dia no cenário A: sem dia perdido, não sobra margem. Na prática o prazo pede mais uma equipe ou aditivo.
4. A mesma produtividade em 500 mm e em 63 mm (o diâmetro grande deve render menos).
5. Os tempos das caixas e a montagem como frente separada.
6. O MND (se não houver furo, o valor sai do cronograma).
7. Sem recesso e sem chuva.

## Como o motor funciona (`motor.py`)

- **Tempo em minutos úteis** (540 por dia) sobre um calendário de dias úteis a partir da OS (`Calendario`: `w(data)`
  dá o minuto do início do dia; `inicio(w)`/`fim(w)` voltam para data e hora).
- `ler_dados()`: o `DADOS` do REV02 (trechos `t` com `R` = nome da 06.1, `de`, `tipo`, `loc` = zona, `pb`, `L` =
  metros, `ini`/`fim` = nós; elementos `els` com `tp`, `noms`, `tr`, `pecas`), a aba REDE da 06.1 e o vertical do BM.
- `base()`: marca a Subadutora (`tipo == 'Adutora'` ou DE ≥ 200), a distância ao canteiro, a ordem das zonas e as
  ligações estimadas por trecho.
- `programar(D, rede, p)`: (1) pé alto da ANK1 a 60 m/dia nos DE 160 das zonas até o reajuste; (2) a Subadutora em
  ordem de caminhamento (`ordem_subadutora`: da ponta de maior DE, andando pelo grafo, maior DE primeiro); (3) os
  blocos zona × PB para a primeira equipe livre entre E1A, E1B, E2C, E2D e ANK1; (4) caixas: obra civil em fila
  única da ANK2 pela data em que os trechos ficam prontos, montagem em fila a partir de jul/2027; (5) fechamento por
  zona e da Subadutora, desmobilização. Devolve o plano com as datas de cada trecho, bloco e caixa.
- `resolver_prazo()`: bisseção entre 40 e 200 m/dia até 0,5 m/dia.

## Faturamento na planilha (`faturamento.py`)

Cada item do BM vertical vai para as equipes e os meses pelo critério que o mede (o critério de cada item aparece na
planilha):
- **Rede (2.1, 2.2):** coluna da 06.1 que mede o item (`DRIVER_FIXO`: escavações por categoria, esgotamento, locação
  com NS, cadastro); item com diâmetro, pelos metros daquele DE (o 160 junta o 125); senão, a coluna da 06.1 cuja
  soma bate com a quantidade do BM (±6 %); senão, o volume de escavação. Locação: 2 semanas antes do trecho;
  cadastro: 30 dias depois.
- **Caixas (3.1, 3.2):** obra civil das 132 caixas, pelo porte de cada tipo, na ANK2.
- **Ligações (4.1, 4.2):** nos trechos de DE 63, 5 dias úteis atrás da rede; a interligação, em partes iguais pelas
  zonas e a Subadutora.
- **Hidromecânico (5.1, 5.2):** peças da 06.2 — a parte dos nós entra com o primeiro trecho do nó; a parte das caixas,
  na montagem. 5.2 (serviço) na montagem das VRP.
- **Canteiro (1.1, 1.2):** alambrado e portão em out/2026; demais instalações de 03/11 a 18/12; itens mensais iguais
  de nov/2026 ao fim; aluguel de contêiner pelos contêineres no canteiro; desinstalação metade na chegada, metade na
  desmobilização.
- **Administração local (6.2):** fórmula na planilha, proporcional ao faturamento do mês.

## O arquivo do Project (`gerar_project.py`)

MSPDI escrito à mão, com a ordem dos elementos conferida contra o `propOrder` do JAXB do MPXJ (o Project é rigoroso
com a ordem). `LinkLag` em décimos de minuto. Campos extras: Text1 Equipe, Text2 Zona/frente, Text3 Fase, Number1
Extensão (m), Number2 DE (mm), Number3 Ligações (est.). Calendário com os feriados. Linha de base igual ao plano.
No MPXJ, `Relation.getTargetTask()` é o predecessor (não confunda com `getSourceTask()`, que é a própria tarefa).

## Como mudar uma premissa

As constantes estão no topo de `motor.py` (datas de entrada das equipes em `EQUIPES`, `P_PE_ALTO`, `CAIXA_DIAS`,
`HIDRO_DIAS`, `LIG_ATRASO`, `TOPO_ANTES`, `CADASTRO_DEPOIS`, `TESTE_DIAS`, `INTERLIG_DIAS`, `DESMOB_DIAS`,
`CANT_*`, `CONTEINERES`, `TOPO_INICIO`, `INICIO_HIDRO`, `REAJUSTE`). O cenário B está em `gerar.py` (`'p': 90.0`).
Mude, rode `gerar_tudo.sh` e confira na aba PREMISSAS e no comparativo. Ao mudar uma premissa, atualize a aba
PREMISSAS (`gerar_xlsx.py`, função da aba) e este arquivo.

## Próximos passos

- Ligar o cronograma ao executado: % concluído por trecho (do web app) e linha de status na data de corte; título
  "REV nn - nª MEDIÇÃO", como no modelo do Lago Sul (`modelo-lago-sul.md`, seção do cronograma físico executivo).
- O web app já importa um XML do Project na tela Cronograma da obra (`cronograma.py`); o cronograma ligado ao
  executado é a D-150 (depois).
- REV01 entregue em 30/10/2026 (seção REV01). Ajustar com o engenheiro sênior as saídas do reservatório e, quando
  houver, a data de operação.
