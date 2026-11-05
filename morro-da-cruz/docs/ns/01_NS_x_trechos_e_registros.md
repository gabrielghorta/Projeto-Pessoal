> Pesquisa de 20/10/2026 para a Nota de Serviço por upload (somente leitura do código). Os caminhos em /tmp são do rascunho da sessão e não existem no repositório; o protótipo citado está em `ferramentas/ns/`.

# Mapeamento das NS para trechos, nós e fluxos de registro (somente leitura)

Escopo: análise somente leitura. Nenhum arquivo do projeto foi alterado. Os scripts e despejos de rascunho estão em `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/mapa_scripts/`.

## 0. Conclusões

- **A NS 006 não casa com nada desta obra, e é isso que se espera dela.** Fiz uma varredura com openpyxl em todas as abas das 6 planilhas procurando: ETE, PARANOÁ, EMISSÁRIO, TRATAMENTO PRELIMINAR, BALÃO, CAIXA DE ENTRADA, 9702, ESTACA, GERATRIZ, COLETOR, CONCREMAT e PEAD/DE/DN 800 ou 1000.
  - Resultado: **0 ocorrências**.
  - "PV" só aparece no cabeçalho "ORIGINAL - P0 (CAESB) - PV" das abas de BM.
  - Os DE da 06.1 são só 63, 90, 110, 125, 160, 225, 250, 280, 315, 355, 400 e 500.
  - A rede de água não tem PV. Os elementos são NÓ, DF, VM, VRP, MV, VTF e HID.
  - Portanto a conferência do contrato tem de **recusar** a NS 006: 9702/2024 ≠ 10239/2026.
  - O parser não pode trazer vocabulário de esgoto embutido no código (COLETOR, PV, BALÃO).
- **Os segmentos da NS precisam ser casados com o trecho físico**, que vai de conexão a conexão. A conversão gera intervalos **por linha da 06.1**, e cada linha continua sendo a unidade do BM e da medição.
- Isso é viável: o servidor já faz cada requisição numa transação única (`server.py:1021-1048`), e `transacao` vira SAVEPOINT (`servicos.py:90-112`). Uma NS que cobre N linhas pode chamar N vezes `S.apontar`, `S.registrar_etapa_complementar` ou `S.registrar_cadastro_campo` dentro do mesmo POST: grava tudo ou nada.
- **Casamento automático só com contexto.**
  - O nome do nó, sozinho, é ambíguo: NÓ1.1 existe em 23 combinações Zona_PB.
  - É preciso juntar zona ou PB, vizinhança no grafo, extensão, DE e método.
  - O resto vai para confirmação humana.
- **Hoje a medição não usa nenhum dado de campo de profundidade ou largura.** Tudo vem de constantes da 06.1. A NS serve primeiro para **conferência e evidência**. Para alimentar quantidades é preciso decisão (D-51, D-30, D-58).

## 1. Esquema, importação e nomes

### 1.1 Trechos (06.1)

**Colunas** (`schema.sql:133-162`; preenchidas em `importacao.py:401-410`):

| Campo | Coluna da 06.1 |
|---|---|
| `ponto` | R, ex. `Zona01_PB01_Rede_TR001` |
| `frente_id` | K |
| `de_mm` | H |
| `material` | I |
| `metodologia` | N |
| `extensao_m` | M |
| `codigo_bm` | AC |
| `recobrimento_m`, `profundidade_m`, `largura_m`, `lastro_m` | AE, AF, AG, AH |
| `quantidades` (JSON) | AL..BK |
| `no_ini`, `no_fim` | BP, BQ |
| `handle` | BR |
| `utm_ini`, `utm_fim` | BS/BT, BU/BV |
| `observacao` | AB |

- **Identidade:** dada por handle + pontas UTM (`importacao.py:416-494`). O TR- é estável entre revisões.
- **Dados reais:**
  - 1.436 linhas: 1.400 Rede e 36 Adutora. Todas TUBO PEAD PN10.
  - VCA 1.432 e MND 4.
  - Extensão total de 110.686,03 m. 115 linhas têm menos de 5 m e 11 têm menos de 1 m.
- **Profundidade (AF):** é uma **constante por DE**, igual a recobrimento 1,20 + DE + lastro 0,10. Exemplos: 1,363 em 840 linhas; 1,46 em 206; até 1,80 no DE500; 0 nas 4 MND.

**Sentido dos metros**
- Vai de 0 em `no_ini` (BP) até a extensão em `no_fim` (BQ). Está escrito em `schema.sql:468`, `web/index.html:144` e `docs/ETAPA_4_CAMPO.md:15`.
- Conferi: em 1.357 de 1.357 linhas cujo nó BP tem coordenada na 06.2, o par BS/BT está nesse nó (mediana 0 m, p95 0,59 m, máximo 1,58 m).
- O sentido é arbitrário em relação ao fluxo. Em 59 dos 334 nós de grau 2, as duas linhas chegam ambas ou saem ambas do nó. Logo, o `sentido` dos membros vai ser −1 com frequência.

### 1.2 Nós e peças (06.2)

- **`elementos`** (`schema.sql:167-180`): `numero` (NÓ9.1, VRP-15, DF-33…), `tipo` (`importacao.py:119-125`).
- **`atividades`** (`schema.sql:183-193`): elemento × frente, Rede/CH/Adutora; `nomenclatura` vem da coluna K.
- **`itens_projeto`** (`schema.sql:197-215`): peças por atividade.
- **Volume:** 6.539 linhas e 1.242 nomenclaturas.
- **Coluna "PROJETO (NÓ)":** traz o tipo do nó do projeto (ex.: "09" para NÓ9.1) ou a descrição do dispositivo (ex.: "VRP - DN80 em DE160").
- **Pontas da 06.1 × 06.2:** todos os 1.158 nomes de ponta da 06.1 existem como nomenclatura na 06.2. É o mesmo JOIN que `trechos_da_atividade` faz (`servicos.py:246-262`).
- **Pontas sem identidade:** 151 ocorrências, em 122 trechos.
  - DIVISA DE ZONA: 72.
  - PONTA SEM NÓ NA TABELA: 63.
  - LIMITE DA TRAVESSIA MND: 10.
  - JUNÇÃO SEM NÓ NA TABELA: 6.
- **Prefixo do nó ≠ prefixo do trecho:** em 246 linhas o BP tem Zona_PB_Tipo diferente do PONTO; em 241, o BQ. Não dá para deduzir a PB do nó pelo nome do trecho.

### 1.3 Estacas no apontamento

`apontamentos.estaca_ini` e `estaca_fim` (`schema.sql:462`):
- São texto livre, com o rótulo "Estaca inicial (NS, referência)" (`web/index.html:147`).
- São gravados em `servicos.py:1047-1051` e copiados na retificação (`servicos.py:1287-1290`).
- Nunca entram em cálculo nem aparecem em outra tela. É o encaixe natural para a referência estruturada da NS.

### 1.4 Dá para casar os elementos da NS automaticamente?

**Ambiguidade dos números de nó**
- Há 328 números distintos; 145 aparecem em mais de uma Zona_PB.
- Dentro da mesma zona, 235 se repetem em PBs diferentes. Ex.: Zona01 NÓ1.8 está na PB01 e na PB02.
- Há 5 casos de (zona, PB, número) que existem como Rede e também como Adutora.

**Zeros à esquerda**
- A 06.1 escreve MV-01, VRP-03 e DF-06. Uma NS com "VRP 3" precisa ser normalizada numericamente.

**Trechos paralelos com as mesmas pontas (4 pares)**

| Par | Como separar |
|---|---|
| Zona03_PB08 TR024 (DE160) × TR026 (DE63) | pelo DE |
| Zona11_PB23 TR057 × TR058 | pelo DE |
| Zona06_PB15 TR003 (28,70 m) × TR005 (182,55 m) | pela extensão |
| **Zona11_PB24 TR039 × TR040** (ambos DE160; 95,19 × 94,80 m) | **só por pessoa** |

**Um nó com peças nem sempre é conexão daquele tubo**
- O NÓ113.1 tem, na 06.2, LUVA DE110, TÊ DE110 e REDUÇÃO 160X110, com BC = TR003/TR004/TR006/TR007/TR011.
- Pela regra do responsável, ele é só cruzamento da cadeia TR007 + TR006, que mede 295,98 m.
- Se a NS listar esse nó, ele vira **ponto intermediário** do segmento, não limite. Quem decide é a topologia, não a 06.2.

**Extensão NS × 06.1**
- 410 linhas da 06.1 "INCLUEM x M DE TUBO DESENHADO NO PRÓPRIO NÓ": 888,89 m no total, até 8,4 m numa linha, 222 linhas acima de 1 m.
- A distância medida pelo topógrafo vai divergir disso.
- 55 trechos foram divididos na DIVISA DE ZONA, atravessando frentes. Ex.: VRP-16 → MV-01 = TR015 (Zona01, 80,35 m) + TR001 (Zona02, 8,61 m), total 88,96 m.
- 9 trechos foram divididos no LIMITE DA TRAVESSIA MND. Ex.: Zona09_PB16 TR003 (VCA 114) + TR002 (MND 54,36) + TR011 (VCA 265,83) = 434,19 m.

**Algoritmo sugerido, por grupo da NS**
1. Conferir o contrato pelo par número/ano: o da obra sai de `S.contrato` (`servicos.py:129-130`), `config/fontes.json:2` e da célula REDE!BI2 = 10239/2026. Divergência é bloqueante.
2. Definir o contexto: zona e PB pela LOCALIZAÇÃO e pelo título da NS, ou escolhidas por quem envia.
3. Normalizar o elemento com sinônimos: REGISTRO→VM, VENTOSA→VTF, DESCARGA→DF, MACROMEDIDOR→MV, HIDRANTE→HID, NO/N→NÓ.
4. **Percorrer o grafo de trechos físicos:** o elemento seguinte precisa ser vizinho do anterior, com |L_ns − L_físico| dentro da tolerância e DE e método iguais.
5. Classificar o resultado:
   - **AUTOMÁTICO:** candidato único e Δ ≤ máx(0,5 m; 1 %).
   - **CONFIRMAR:** em qualquer outro caso, com uma lista de alternativas.
   - **SEM CORRESPONDÊNCIA:** quando não há candidato.

Com só a zona: NÓ9.1 e VRP-15 da Zona03 têm candidato único; NÓ1.8 da Zona01 e NÓ60.1 da Zona11 têm dois cada.

### 1.5 Conversão de metros (interface `trechos_fisicos`)

Usa `membros: [{trecho_id, ordem, offset_m, sentido}]`.

**Ida (NS → linhas da 06.1)**
- k = L_físico / L_ns. A escala proporcional mantém as duas pontas da NS sobre os nós.
- Sentido da NS: dir = +1 se a linha da NS de menor estaca é `no_ini` do trecho físico; −1 se é `no_fim`.
- Intervalo [u, v] na NS → no trecho físico:
  - com dir = +1: [p, q] = [u·k, v·k];
  - com dir = −1: [p, q] = [L − v·k, L − u·k].
- Para cada membro: tomar a interseção de [p, q] com [offset, offset + ext].
- Converter para o local da linha: [x, y] = interseção − offset. Se `sentido` = −1, usar [ext − y, ext − x].
- Arredondar a mm e limitar a [0, ext]. Os testes usam `R.TOL_M = 1e-3` (`regras.py:361`) e `servicos.py:886-887`, `1413-1415`.
- REATERRADO e ESCAVADO **pulam membros MND**. Hoje eles são recusados lá (`servicos.py:884-885`, `1405-1406`).

**Volta (linha → NS):** é a inversa. Serve para mostrar na NS o que já foi feito e para o botão "só o que falta".

**Conferido em protótipo** (`conv.py`):
- NS de VRP-15 → NÓ9.1 com 296,40 m medidos; trecho 0–200 m; k = 0,99858.
  - Vai para 96,263–295,98 m no trecho físico, ou seja, TR006 93,753–293,47 m.
  - A volta devolve 0–200 m.
- Quando o sentido foi deduzido por igualdade exata de UTM, saiu **espelhado** (TR006 0–199,717 m). No cruzamento, o fim de TR007 e o início de TR006 estão 6 cm um do outro.
- Refinamento possível: conversão linear por partes entre pontos casados (limite MND quando a coluna MÉTODO da NS muda, cruzamento listado).

**Estacas são globais, não por grupo**
- O coletor secundário começa em 0+17,32, com acumulada 17,32 e parcial 0.
- O deslocamento de cada linha é acumulada − acumulada da 1ª linha do grupo.
- Invariantes conferidas nos dois PDFs (`checa_ns.py`):
  - profundidade = terreno − GI;
  - cruzeta = visor + profundidade;
  - estaca × 20 m + fração = acumulada;
  - Σ parciais = RESUMO (30,49 e 40,22);
  - soma = TOTAL GERAL (70,71).

## 2. Onde o intervalo é digitado hoje e o que vira "escolher na NS"

### Lançamento do dia (trecho)
- **Hoje:**
  - Tela: busca em `web/index.html:139-141`; Assentado e Reaterrado de/até em 145-146; estacas em texto em 147; "100 %" em 149.
  - Prévia: `app.js:853-865` calcula metros = ass_fim − ass_ini de **um** trecho.
  - Envio: `app.js:866-879` → `/api/apontamento` (`server.py:287-290`) → `S.apontar` (`servicos.py:1005-1061`).
  - `S.apontar` trata um alvo só:
    - clima obrigatório: 1017-1019;
    - legado: 1028;
    - `_validar_intervalos`: 868-908;
    - previsto: 1041;
    - gravação: 1047-1055.
- **Vira escolha na NS:**
  - Escolher NS → segmento → "segmento inteiro" ou "da estaca X à Y".
  - O servidor converte e chama `S.apontar` uma vez por membro, na mesma requisição.
  - `estaca_ini` e `estaca_fim` são preenchidas sozinhas (ex.: "NS 006 fl.01 · 1+5,56").
  - "100 %" passa a valer por segmento: `_intervalos_completo` em cada membro (911-919).
  - É preciso uma prévia nova com o previsto por membro; `/api/previsto` atende só um trecho.
  - Nó ou caixa: escolher a linha da NS → elemento → atividade Rede ou CH.
- **Continua digitado:** data, equipe, clima, confirmação ou edição das quantidades, soldas (posição pode sair da estaca), ocorrências.

### Escavação
- **Hoje:** `app.js:747-749` e `761-766` → `_etapa` (`server.py:385-389`) → `servicos.py:1398-1422`.
- **Vira escolha na NS:** "escavado da estaca X à Y" convertido por membro, sem os membros MND.
- **Continua digitado:** data e observação.

### Planejamento
- **Hoje:**
  - Tela: alvo, serviço e De/Até em `index.html:342-351`; envio em `app.js:552-558`.
  - Servidor: `planejamento.programar` (`planejamento.py:23-57`), com intervalo opcional (31-38) e unicidade por (dia, equipe, alvo, serviço) (39-41).
- **Vira escolha na NS** (NS de serviço + croqui):
  - Programar os segmentos da NS gera uma programação por membro, com ini/fim.
  - Os materiais previstos podem vir sugeridos do RESUMO (TUBO PEAD DEnnn → `CAESB-PEAD-DEnnn`, `importacao.py:797-801`) e das peças da 06.2 dos nós listados.
- **Continua digitado:** data, equipe, serviço, ajuste dos materiais, observação.

### Topografia (liberação)
- **Hoje:**
  - Tela: trecho, De/Até, "Trecho todo" / "Só o que falta", Data e "Nota de serviço" em texto (`index.html:257-268`); botões e envio em `app.js:1446-1461`.
  - Servidor: `/api/liberacao` (`server.py:635`, permissão 654) → `registrar_etapa_complementar`, que exige referência (1409-1410) e recusa sobreposição (1416-1418).
- **Vira escolha na NS** (NS de TOPOGRAFIA):
  - Enviar o PDF.
  - Conferir o cabeçalho: contrato, nº, folha, data e revisão.
  - Revisar a tabela de segmentos casados.
  - Um clique grava uma LIBERACAO por membro, **só na parte ainda não liberada** (`R.fora_da_cobertura`). A referência fica estruturada.
- **Continua digitado:** data da liberação (padrão = DATA da NS; ela muda os alertas de `servicos.py:1445-1451`), anulação com motivo (1425-1434), filas da tela (`terceirizadas.py:44-101`). O formulário digitado fica como "sem NS".

### Cadastro de campo (alteração não commitada)
- **Hoje:**
  - Tela: `index.html:289-300`; "Só o que falta" e envio em `app.js:1524-1538`.
  - Servidor: `/api/cadastro-campo` (`server.py:450-453`, 638, 655) → `S.registrar_cadastro_campo` (`servicos.py:966-985`), só sobre o assentado até a data.
- **Vira escolha na NS** (NS de CADASTRO, as-built):
  - Gera CADASTRO_CAMPO por membro, **só sobre o assentado até a data**.
  - O resto fica "pendente de aplicação" na NS. Hoje a chamada é tudo ou nada.
- **Continua digitado:** data do levantamento (padrão = DATA da NS).

### Conciliação do legado
- **Hoje:** `app.js:732-738`, `771-776` → `server.py:293-294` → `servicos.py:1089-1114`. A soma por etapa tem de ser igual ao legado (1081-1086).
- **Com NS:** só um atalho, o seletor de estacas preenche de/até por linha.
- **Continua digitado:** motivo e datas. A soma exata não muda.

### Retificação
- **Hoje:** `app.js:779-786` e `806-842` → `server.py:297-300` → `servicos.py:1173-1301`. É recusada depois do OK (1194), exceto CADASTRO_CAMPO.
- **Com NS:** o editor continua por linha, porque o registro retificado é de uma linha. A NS entra só como seletor.
- **Continua digitado:** o conjunto de intervalos e o motivo.

### Soldas e ocorrências
- **Hoje:** soldas têm `posicao_m` (`index.html:173`); ocorrências usam texto livre com estacas (`index.html:233`).
- **Com NS:** a estaca da NS pode ser convertida em metro da linha (opcional).

**Persistência (proposta de esquema v18):**
- Tabelas novas:
  - `ns_documentos`: tipo TOPOGRAFIA, CADASTRO ou SERVICO; nº, contrato, folha, data, revisão, `documento_id` do PDF e do croqui.
  - `ns_linhas`: grupo, estaca, elemento, cotas, profundidade, método, DE, parcial, boca, fundo, casamento.
  - `ns_segmentos`: linhas a e b, L_ns, k, dir, **cópia JSON dos membros** e quem confirmou.
- Coluna anulável `ns_segmento_id` em `etapas_complementares`, `intervalos_execucao`, `programacoes` e `apontamentos`. Dá para criar com `_add_coluna`, `importacao.py:867`.
- `documentos.tipo` não tem tipo para NS nem croqui (CHECK em `schema.sql:722`; `compras.TIPOS_DOC` em `compras.py:28`). Incluir exige recriar a tabela, como em `preparar_v17` (`importacao.py:1079-1096`).
- O Drive manda todo documento para 04_COMPRAS (`drive.py:368-383`).
- Não há rota para abrir o PDF guardado no servidor.
- As tabelas novas precisam entrar em `HISTORICO_POR_TRECHO` (`servicos.py:2324-2326`).

## 3. Medição

### Como é hoje

**Quantidades do apontamento**
- `S.previsto` (`servicos.py:234-243`) → `R.quantidades_previstas_trecho` (`regras.py:95-132`):
  - ASSENTAMENTO = L;
  - demais serviços = coluna da 06.1 × L / extensão;
  - MND só comprimento;
  - solda ⌈L/6⌉ só como estimativa.
- O apontamento confirma ou edita esses valores (`servicos.py:988-995`).

**OK interno** (`servicos.py:1742-1798`)
- Exige 100 % e fotos (`regras.py:179-185`, chamado em 1752).
- Soma as quantidades confirmadas (1760-1765).
- Acha o item do BM por `config/servicos_rede.json` (`_itens_servico` 1689-1697). O rateio entre 2 itens é hipótese (D-51).
- MND fica PENDENTE (1775-1779).
- Põe o trecho na esteira de cadastro (1786-1788).

**Escavação**
- Volume AP = L × LARG × PROF. Conferido: 76,55 × 0,65 × 1,363 = 67,82.
- As faixas AU..AZ são **frações fixas da aba APOIO_REDES**, um rateio do BM. Não dependem da profundidade do trecho:

| Faixa | Fração |
|---|---|
| Mecânica 1ª cat. < 1,50 | 68,64 % |
| Mecânica 1ª cat. 1,50–3,00 | 9,50 % |
| Mecânica 2ª cat. < 1,50 | 17,38 % |
| Mecânica 2ª cat. > 1,50 | 2,40 % |
| Rocha | 1,09 % |
| Manual < 1,50 | 0,87 % |
| Manual > 1,50 | 0,12 % |

- Os itens 5.4.11, 5.4.13, 5.4.15 e 5.4.14 do BM dizem textualmente: "MÉDIA MONTANTE E JUSANTE/UMA COMPOSIÇÃO POR TRECHO".

**Locação e cadastro**
- "LOCAÇÃO C/ NOTA" (coluna AL = M em 1.432 linhas; 0 nas 4 MND) → item 2.2_5.2.7 "LOCAÇÃO E NIVELAMENTO … COM ELABORAÇÃO DE NOTA DE SERVIÇOS" (BM REV04: 111.219,2 m a R$ 1,50; `servicos_rede.json:13`).
  - É proposta no OK pelo metro **assentado**, sem olhar NS nem liberação.
- Cadastro: item 2.2_5.2.1 (R$ 2,61/m), na gaveta 3 quando o GDOC aprova (`servicos_rede.json:30`, `medicao.py:62-63`, D-58).

**Elegibilidade e evidências**
- Só trecho completo é proposto (`medicao.py:124-210`, D-30).
- Foto ausente impede a CONFORME (`medicao.py:248-250`).

**Observação:** a 06.1 e a 06.2 já têm uma aba "RESUMO - NS LIBERADAS", **vazia**.

### O que a NS pode alimentar ou conferir

| Dado da NS | Uso | Situação |
|---|---|---|
| PARCIAL/ACUMULADA, RESUMO por DE, TOTAL | NS × trecho físico (Σ das linhas) e RESUMO × Σ das linhas casadas por DE. Nunca altera a extensão da 06.1. | Conferência |
| MATERIAL "D", ex. PEAD-160 | Comparar com `de_mm`/`material`. Divergência bloqueia o casamento automático. | Conferência |
| MÉTODO V.C.A/MND | Comparar com `metodologia`. MND muda itens (D-52) e não tem vala. | Conferência |
| Terreno, GI, PROFUNDIDADE (= terreno − GI) | Média montante/jusante + lastro 0,10 dá a faixa (< 1,50 ou 1,50–3,00) e o tipo de escoramento (BD/BE/BF). Serve de evidência para D-51. | Só alimenta com decisão. Não comparar com AF diretamente: AF inclui o lastro. |
| ESCAVAÇÃO BOCA/FUNDO | Comparar com `largura_m` (0,65–1,20). Volume trapezoidal L × (boca + fundo)/2 × profundidade. | Decisão |
| VISOR/CRUZETA | Consistência do documento. | Validação |
| NS de topografia registrada | Evidência da 2.2_5.2.7: locação proposta ≤ metros cobertos por NS na linha, sem os membros MND. | Evidência; alerta ou PENDENTE |
| NS de cadastro × NS de topografia | Diferenças de cota e profundidade por nó → itens PROFUNDIDADE e EXTENSAO do checklist (`regras.py:225-232`) e medição do 2.2_5.2.1. | Conferência |
| NOTAS (tipo de caixa) | Comparar com as peças CH da 06.2 do elemento. | Conferência |
| RESUMO por DE | Materiais previstos da programação e faltantes no almoxarifado. | Alimenta o planejamento |

### Fotos pelo Telegram, só na medição

- Hoje a foto é **pré-requisito do OK interno**, e é o OK que cria a proposta de medição e põe o trecho na esteira.
- Uma imagem só vale para um registro:
  - `servicos.py:1615` e `1631-1634`;
  - índice único `ux_fotos_sha` (`servicos.py:64-65`).
- Por isso **uma foto do trecho físico não serve para as várias linhas** que o formam. Um trecho de 2,51 m (TR007) exigiria 3 fotos próprias.
- A exigência teria de passar para a conferência da medição e ser avaliada por trecho físico (decisão).

## 4. Riscos

1. **Contrato:**
   - Comparar só o par número/ano.
   - A contratada é a mesma nas duas obras, então não distingue nada.
   - A NS 006 tem de ser recusada; no máximo, mostrar a prévia como "modelo".
2. **Ambiguidade de nomes:** os números de nó se repetem entre PBs e há 4 pares de trechos paralelos. Sem PB ou vizinhança no grafo, o casamento erra.
3. **Pontas genéricas:** são 151.
   - As cadeias por DIVISA DE ZONA ou limite de MND só se encadeiam por UTM com tolerância.
   - O trecho físico atravessa frentes (55 casos) e métodos (9 casos).
4. **Sentido:**
   - O encadeamento por UTM exata falha no cruzamento (6 cm de diferença) e espelha os intervalos sem avisar.
   - Testar os dois sentidos e a NS invertida.
5. **Diferença de extensão:** os 410 trechos com tubo desenhado dentro do nó exigem escala proporcional e mostrar o Δ sempre.
6. **Ids do trecho físico:**
   - São derivados em memória (cache por data de modificação). Guardar a cópia dos membros ao confirmar.
   - Avisar quando a topologia mudar.
   - Incluir as tabelas de NS na conferência de histórico da importação.
7. **Gravação tudo ou nada:**
   - Hoje há várias recusas: sobreposição na liberação (1416-1418), cadastro fora do assentado (895-907), legado pendente (1028, 980), OK já dado (1023-1024), trecho retirado (175-177), MND.
   - A aplicação da NS precisa de prévia por membro e de gravação parcial explícita.
8. **Desfazer uma NS:**
   - A retificação é por apontamento ou por intervalo (v17: `servicos.py:1142-1149`).
   - Corrigir ou revisar uma NS significa N retificações ou anulações. Falta a operação "substituir NS (Rev. N)".
9. **Planejamento por membro:**
   - O check-in marca REALIZADA só a programação do alvo do check-in (`servicos.py:654-657`); os outros membros do segmento ficam PLANEJADA.
   - A unicidade por (dia, equipe, alvo, serviço) (`planejamento.py:39-41`) quebra quando dois segmentos tocam a mesma linha no mesmo dia.
10. **Fotos:** o hash único impede usar a mesma foto em duas linhas, e a foto ainda é exigida no OK. Fotos de Telegram enviadas como "photo" perdem EXIF e GPS (no export sintético há photo e file); a origem vira DISPOSITIVO ou ENVIO.
11. **PDF assinado (Ghostscript, página com /Rotate 90):**
    - O modo layout do pypdf embaralha os campos da direita: "006NS nº :", "01 de 01FOL", e o valor do RESUMO de 800 mm vai para o fim da linha.
    - O `pdftotext -layout` sai limpo, mas não sei se existe no PythonAnywhere.
    - O parser precisa tolerar a ordem e validar com as invariantes da seção 1.5.
12. **Croqui:** o texto é legível só em parte ("N.S.006", "9702/2024", T/F/P). Usar só para ligar o croqui à NS e como anexo.
13. **Medição:** usar profundidade, largura ou locação vindas da NS muda quantidades do BM. Precisa de decisão (D-51, D-30, D-58). Até lá, só alertas.
14. **Permissões:** `PERMISSAO` é por rota (`server.py:645-655`). Se uma rota única de NS servir os três tipos, a permissão precisa ser conferida dentro do handler, como já se faz em 1032-1035.
15. **Ordem de integração:**
    - `topologia.py` ainda não existe neste ramo, e o ramo da topologia está proibido de mexer em `servicos.py`, `schema.sql` e `app.js`.
    - Ordem: commitar e testar a v17 (Topografia e Cadastro de campo) → PR da topologia → NS (v18).

## 5. Rascunho

Pasta `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/mapa_scripts/`:

| Arquivo | O que contém |
|---|---|
| `rede061.json`, `con062.json` | despejo da 06.1 e da 06.2 |
| `busca.py` | varredura de termos nas planilhas |
| `anal061.py`, `anal062.py`, `unic.py`, `paralelos.py`, `ab.py`, `sentido.py` | números da seção 1 |
| `conv.py` | protótipo da conversão NS ↔ linhas |
| `checa_ns.py` | invariantes da NS |
| `pdf_hdr.py` | teste de extração com pypdf |
