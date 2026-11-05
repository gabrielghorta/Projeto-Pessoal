> Pesquisa de 20/10/2026 para a Nota de Serviço por upload (somente leitura do código). Os caminhos em /tmp são do rascunho da sessão e não existem no repositório; o protótipo citado está em `ferramentas/ns/`.

# Protótipo de leitura da Nota de Serviço (NS 006): parser, conferências e robustez

Não alterei nada em `/home/user/projeto-pessoal/morro-da-cruz`: o `git status` está igual ao de antes. Tudo foi escrito em `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/`. O rascunho antigo `scratchpad/proto/parse_ns.py` fica substituído.

## Resultado
- **Leitura da NS 006:** os dois PDFs (assinado e não assinado), lidos com pypdf e com pdftotext, dão exatamente os mesmos dados (impressão `4a16e8250898f74f`). Todas as conferências de estrutura e de aritmética passam.
- **Contrato:** a única recusa é a esperada. O contrato da NS (9702/2024) é diferente do contrato da obra (10239/2026).
- **Robustez:**
  - 61 variantes em texto e 4 PDFs reais renderizados pelo LibreOffice (lidos com pypdf, pdftotext e leitura dupla).
  - Nenhuma leitura deu dado errado sem alarme.
  - Ficam dois pontos frágeis: uma coluna vazia em todas as linhas quando só há pypdf, e os rótulos do cabeçalho, que são lidos ao pé da letra. Os dois falham de forma visível.
- **Casamento com a obra:**
  - O demo leva os segmentos da NS até os trechos físicos e daí aos intervalos de cada linha da 06.1, usando linhas reais (TR020, e TR007+TR006 com o cruzamento NÓ113.1).
  - Zona e PB precisam estar escritos na NS; sem isso o casamento fica ambíguo e é recusado.

## 1. Arquivos
Todos em `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/`:

| Arquivo | O que é |
|---|---|
| `ns_parser.py` | O parser (Python puro + pypdf). Uso: `python3 -I ns_parser.py NS.pdf -o saida.json --contrato-obra "CT 10239/2026" [--hoje AAAA-MM-DD] [--inicio-contrato AAAA-MM-DD] [--extrator auto\|pypdf\|pdftotext] [--sem-comparar]`. O modo `--texto pag1.txt ...` serve para testes. |
| `ns.json`, `topografia.json` | Saídas oficiais dos dois PDFs. |
| `testes_variantes.py` | 61 variantes sintetizadas em texto. Resumo em `variantes/_resumo.json`; cada variante tem um `.json` e um `.txt`. |
| `gerar_pdf_variantes.py` | Monta uma planilha parecida com o modelo Caesb, gera o PDF no LibreOffice e lê com os 3 modos. Saídas em `pdf_lo/*.pdf` e `*.json`. Precisa de LibreOffice, então não é para o PythonAnywhere. |
| `demo_casamento.py` | Casamento NS → trecho físico → linhas da 06.1, sobre a interface `trechos_fisicos`. Saídas em `demo_casamento.json` e `.log`. Uso: `python3 -I demo_casamento.py <pasta> mapa_scripts/rede061.json`. |

## 2. O que os PDFs mostraram
- **Rotação do ns.pdf:** o arquivo tem `/Rotate 90`. Sem `transfer_rotation_to_content()` o modo layout devolve texto vazio (`ns_parser.py:198`).
- **Valor antes do rótulo:** no ns.pdf (Ghostscript) lido com pypdf sai `006NS nº :` e `01 de 01FOLHA:`. No topografia.pdf (Microsoft Print To PDF) a ordem é a normal. `_campo` aceita as duas ordens (`:224`).
- **RESUMO colado:** no ns.pdf com pypdf sai `…(PV.3 - PV.2 e PV.1)40,22`. A primeira versão lia 0,22 (regex gulosa); está corrigido em `:607`.
- **Colunas no pypdf:**
  - Os rótulos do cabeçalho não ficam alinhados com os dados (VISOR do cabeçalho na coluna 282, valores na 207).
  - A linha inteira desliza até 27 colunas conforme o tamanho do elemento, e a menor distância entre colunas é 10,5.
  - Medidas a partir do método (V.C.A) ou do material (PEAD-1000) da própria linha, as posições variam no máximo 3. Por isso as âncoras são relativas, aprendidas nas linhas completas (`_ancoras` `:337`, `_alinhar` `:303`).
  - Sem método nem material, procuro o deslocamento da linha junto com as colunas (`_alinhar_livre` `:320`).
- **Colunas no pdftotext:** as posições são fiéis (variação ≤ 2,5) e os rótulos do cabeçalho servem de âncora.
- **Visitor do pypdf:** não serve. No ns.pdf devolve códigos de glifo sem tradução; no topografia.pdf devolve linhas inteiras na posição (0, 595).
- **Croqui:** o texto do desenho CAD vem embaralhado. O carimbo, porém, dá `N.S.006`, `9702/2024` e `27/10/2025`, o que permite conferir se o anexo é da mesma NS (melhor esforço; não é para ler o desenho).
- **Assinatura:** o ns.pdf assinado tem 2 imagens por página (logotipo + assinatura escaneada); o não assinado tem 1. Isso aparece em `V07` só como indício; o texto não prova assinatura.

## 3. JSON produzido (abreviado)
A chave `header` pedida saiu como `cabecalho`, para manter o português do resto. Também há campos extras: `chave`, `entre`, `sentido`, `continua_de`, `incerto`, `fonte`, `impressao_dados` e `verificacoes`.

```json
{"cabecalho":{"numero":"006","numero_int":6,"contrato":"9702/2024","folha":1,"total_folhas":1,"data":"2025-10-27","data_texto":"27-out-25",
  "localizacao":"TRATAMENTO PRELIMINAR - ETE - ESTAÇÃO DE TRATAMENTO DE ESGOTOS PARANOÁ/DF","titulo":"\"EMISSÁRIO DE ENTRADA\" - … - VER PROJETO EXECUTIVO",
  "bloco":"TOPOGRAFIA","contratada":"CONSTRUTORA ANKARA ENGENHARIA LTDA","orgao":"Caesb"},
 "grupos":[{"titulo":"COLETOR PRINCIPAL - EMISSÁRIO DE ENTRADA (TP - PV.3 - PV.6 - PV.5 e PV.4)","material":"PEAD","dn_mm":1000,"soma_parcial":30.49,"extensao":30.49,"continua_de":null,
   "linhas":[{"estaca_inteira":0,"estaca_fracao":0.0,"estaca_m":0.0,"elemento":"CAIXA DE ENTRADA - TRATAMENTO PRELIMINAR","chave":"CAIXA DE ENTRADA","cota_terreno":1089.55,"cota_gi":1087.95,
     "profundidade":1.6,"metodo":"VCA","material":"PEAD","dn_mm":1000,"dist_parcial":0.0,"dist_acumulada":0.0,"esc_boca":2.2,"esc_fundo":1.4,"visor":1.9,"cruzeta":3.5,"obs":"CAIXA DE ENTRADA- TRATAMENTO PRELIMINAR"},
     {"estaca_inteira":0,"estaca_fracao":17.32,"estaca_m":17.32,"elemento":"PV-3 EMISSÁRIO DE ENTRADA","chave":"PV-3","cota_terreno":1089.324,"cota_gi":1087.98,"profundidade":1.34,"dist_parcial":17.32,"dist_acumulada":17.32,"…":"…"}, "… (5 linhas)"],
   "segmentos":[{"de":"PV3","para":"Caixa de Entrada","metros":17.32,"chave_de":"PV-3","chave_para":"CAIXA DE ENTRADA","entre":[0,1],"sentido":"contra_estaqueamento"}, "… (4)"]},
  {"titulo":"COLETOR SECUNDÁRIO - EMISSÁRIO DE ENTRADA (PV.3 - PV.2 e PV.1)","dn_mm":800,"soma_parcial":40.22,"extensao":40.22,
   "continua_de":{"grupo":0,"linha":1,"elemento":"PV-3 EMISSÁRIO DE ENTRADA","acumulada":17.32},
   "linhas":[{"estaca_m":17.32,"elemento":"PV-3 EMISSÁRIO DE ENTRADA","dist_parcial":0.0,"dist_acumulada":17.32,"visor":1.66,"cruzeta":3.0,"…":"…"}, "… (3 linhas)"]}],
 "notas":[{"elemento":"PV-1","tipo":"BALÃO A2"}, "… (6)"],
 "resumo":[{"descricao":"TUBO PEAD 1000mm","metros":30.49,"coletor":"COLETOR PRINCIPAL - …","grupo":0},{"descricao":"TUBO PEAD 800mm","metros":40.22,"coletor":"COLETOR SECUNDÁRIO - …","grupo":1}],
 "total_geral":70.71,
 "assinaturas":[{"papel":"TOPOGRAFIA","nome":"[NOME DO TOPÓGRAFO]","crea":"[CREA]"},{"papel":"CONTRATADA","empresa":"CONSTRUTORA ANKARA","nome":"[NOME DO ENGENHEIRO DA CONSTRUTORA]","crea":"[CREA]"},
   {"papel":"FISCALIZACAO","empresa":"CONCREMAT","nome":null,"crea":null},{"papel":"FISCALIZACAO","empresa":"CAESB","nome":null,"crea":null}],
 "avisos":["p1: RESUMO com valor colado ao texto: '…(PV.3 - PV.2 e PV.1)40,22'"],"falhas_leitura":[],
 "resultado":{"erros":1,"avisos":1,"aceita":false,"motivos":["V01: contrato da NS (9702/2024) = contrato da obra (10239/2026)"]},
 "fonte":{"extrator":"pypdf 6.17.0 layout","produtor":"GPL Ghostscript 9.06","imagens_por_pagina":[2],"conferido_com":{"extrator":"pdftotext -layout","mesma_impressao":true}},
 "impressao_dados":"4a16e8250898f74f…"}
```

## 4. Conferências na NS 006 (todas passam, salvo V01 e V06)
- **PDFs e extratores dão o mesmo dado:** a impressão é o SHA-256 do conteúdo, sem posições, folhas, avisos e fonte (`impressao_dados` `:706`).
- **Soma das parciais = RESUMO:**
  - Grupo 1: 0 + 17,32 + 8,24 + 2,31 + 2,62 = 30,49, igual ao RESUMO de 1000 mm.
  - Grupo 2: 25,98 + 14,24 = 40,22 = 57,54 − 17,32, igual ao RESUMO de 800 mm.
  - Total: 70,71 = TOTAL GERAL (A11, A13, A14).
- **Continuação do grupo 2:** começa no PV-3 com parcial 0 e acumulada 17,32, que é a posição do PV-3 no grupo 1. O parser grava isso em `continua_de` (`:645-653`) e a extensão do grupo é a acumulada final menos a inicial.
- **Linhas de segmento:** os 6 segmentos conferem com a parcial e com a diferença das acumuladas, e os nomes conferem com as linhas vizinhas (A08, A09). A seta está no sentido do fluxo, do PV para a caixa, ao contrário do estaqueamento (`sentido` em `:663`). Para calcular intervalos uso a estaca, nunca a seta.
- **Contas por linha (8 de 8):**
  - Profundidade = terreno − GI.
  - Cruzeta = visor + profundidade.
  - Estaca × 20 + fração = acumulada.
  - Boca ≥ fundo. Obs.: aqui boca = fundo + 0,5 × prof (talude 1:4), mas isso é desta obra e não é regra.
- **V06 (aviso):** os campos da fiscalização (CONCREMAT e CAESB) estão sem nome.

## 5. Robustez

### 5.1 Variantes em texto (`testes_variantes.py`)
61 casos: 35 OK, 11 OK com aviso, 15 quebras detectadas, 0 quebras silenciosas. Das 15 detectadas, 12 são erros e violações de regra injetados de propósito e pegos como devido (RESUMO, segmento, acumulada, profundidade, data futura, folha faltando).

- **Funcionam com os dois extratores:**
  - Linha MND sem escavação, ou só com parcial/acumulada.
  - Linha sem visor/cruzeta.
  - Elemento com parênteses, números e hífen: `NÓ 9.1 (TÊ 160x160 - DERIV. P/ VRP-15)` dá a chave `NO9.1`.
  - Elemento com 2 espaços internos.
  - Célula do elemento quebrada em 2 linhas, com a parte de cima ou a de baixo fora da linha dos números.
  - 2 folhas com cabeçalho repetido; grupo partido entre folhas sem título ou com "(CONTINUAÇÃO)". Nos dois casos a impressão é igual à da NS de 1 folha.
  - Estaca escrita `0+17,32`; número inteiro `3`.
  - Data `27/10/2025`; rótulo `N.S. Nº:`; valor antes do rótulo; RESUMO colado.
  - PDF digitalizado: recusado com a mensagem "sem camada de texto".
- **Pegos como devido:** só a folha 1 de 2 enviada (E02); texto numa célula de número (E06); segmento sem metros (E06); segmento apagado (A10, aviso).
- **Limitação real:**
  - Situação: uma coluna está vazia em todas as linhas e só o pypdf está disponível. Sem nenhuma linha completa não há âncora, e as células vão pela ordem.
  - Visor/cruzeta vazios em todas as linhas (cara de NS de água): os valores saem certos, mas marcados como incertos.
  - Boca/fundo vazios em todas as linhas: os valores de visor/cruzeta caem em boca/fundo.
  - Agora isso dá ERRO (E05) e A03 acusa.
  - O pdftotext acerta, porque usa os rótulos do cabeçalho.

### 5.2 PDFs reais gerados pelo LibreOffice (`gerar_pdf_variantes.py`)

| Caso | O que é | Resultado |
|---|---|---|
| R1 | Réplica da NS 006 | Mesma impressão `4a16e8250898f74f` em pypdf, pdftotext e leitura dupla, apesar de ser outro motor de PDF |
| R3 | 2 planilhas, FOLHA 01/02 e 02/02, grupo partido sem título | Mesma impressão |
| R2 | NS de água: sem visor/cruzeta, linha MND sem escavação, elemento longo quebrado na célula | Certo nos 3 modos. Só com pypdf, E05 bloqueia; a leitura dupla confirma e libera |
| R4 | Boca/fundo vazios em todas as linhas | Só pypdf: errado, mas bloqueado (E05 + A03). Só pdftotext: certo. Leitura dupla: ERRO E06 (os extratores divergem) |

**Leitura dupla (`ler_ns` `:867`):** quando o pdftotext existe, relê o PDF com ele e compara as impressões. Se forem iguais, as células "incertas" ficam confirmadas; se forem diferentes, vira falha de leitura com a lista das diferenças.

**Bugs que só os PDFs reais revelaram (já corrigidos):**
- O pdftotext põe a 1ª parte de uma célula quebrada ACIMA da linha dos números, que fica com o elemento vazio. Ela virava título de grupo (`aceita_continuacao` `:297`).
- A linha "CONTRATADA: CONSTRUTORA ANKARA" era tomada como linha de assinaturas (`_eh_papeis` `:362`).
- Uma linha sem método nem material jogava a observação como célula estranha.

## 6. O que é confiável e o que é frágil

**Confiável (testado):**
- Números no formato brasileiro e datas `27-out-25`.
- Cabeçalho nas duas ordens (valor antes ou depois do rótulo).
- Linhas completas, segmentos, NOTAS, RESUMO (inclusive colado), TOTAL, nome e CREA das assinaturas.
- Continuação de grupo e várias folhas.
- As contas cruzadas pegam qualquer número lido ou digitado errado que quebre a coerência interna.

**Frágil:**
1. **Coluna vazia em todas as linhas só com pypdf.** Mitigação: leitura dupla e confirmação humana obrigatória. Falta verificar com `which pdftotext` num console Bash do PythonAnywhere se ele existe lá. Sem ele, o sistema perde a leitura dupla e as âncoras de cabeçalho.
2. **Rótulos literais no cabeçalho** (NS nº, CONTRATO:, FOLHA:, DATA:, LOCALIZAÇÃO:). Outra redação deixa o campo vazio e dá E01, um erro visível. O número também pode vir do título do PDF (`N.S.006`).
3. **Título de grupo × texto do elemento quebrado:** a separação é uma regra geométrica (coluna do elemento, antes do 1º número), testada em 4 casos.
4. **Nomes de elementos:** `chave_elemento` (`:120`) cobre PV-n, NÓx.y, VRP-n, DF, VM, MV, VTF, HID e RG. Precisa de uma NS de água real para ver a grafia verdadeira (ex.: "Nó 9-1", "RG 04 DN 90").
5. **Zona e PB:**
   - Na 06.1, 150 de 328 finais de nome de nó se repetem (`NÓ9.1` aparece em 9 zonas/PBs).
   - Mesmo pelo par de pontas, 159 de 1.006 pares (467 de 1.314 linhas) se repetem sem a zona, e 68 pares mesmo dentro da zona.
   - No demo, o par NÓ1.8–NÓ2.7 (Zona01/PB01 TR001 e Zona07/PB18 TR034) é recusado sem "ZONA 01 - PB01" no texto e casa com ele.
6. **Assinatura:** o texto não prova que a NS foi assinada.
7. **Versão do pypdf:** o modo layout pode mudar entre versões. É preciso fixar a versão (testei com 6.17.0; pelo que lembro o modo layout entrou na série 3.17, sem conferir) e manter ns.pdf/topografia.pdf como teste de regressão (impressão `4a16e8250898f74f`).
8. **Significado das colunas (confirmar com o dono):** método, material e parcial da linha i parecem valer para o segmento da linha i−1 até a i, e a 1ª linha do grupo não descreve segmento.

## 7. Regras para aceitar uma NS na implementação real

**Bloqueiam (ERRO, a NS volta para revisão):**
1. **Arquivo e cabeçalho:**
   - O PDF tem texto; se não tiver, pedir o PDF gerado do Excel.
   - Cabeçalho completo: nº, contrato, data válida, folha x de y (E01).
2. **Contrato e datas:**
   - Contrato normalizado igual ao da obra (V01, 10239/2026); a amostra é recusada aqui.
   - Data ≤ hoje (V02). Data ≥ início do contrato (V03, hoje aviso; decidir se vira bloqueio).
3. **Folhas e leitura:**
   - Folhas 1..N completas, N = total declarado = páginas do arquivo, com o mesmo nº, contrato e data em todas (E02).
   - Nenhuma falha de leitura (E06): célula estranha, linha sem estaca, segmento sem metros, extratores divergentes.
   - Nenhuma célula incerta sem confirmação humana (E05).
4. **Contas:**
   - Profundidade = terreno − GI (A01).
   - Acumulada = anterior + parcial (A04).
   - Estacas crescentes, fração < 20 (A06).
   - Segmento = parcial = diferença das acumuladas (A08).
   - Soma das parciais = extensão = RESUMO do grupo (A11).
   - Material/DN do grupo = RESUMO (A12).
   - Soma do RESUMO = TOTAL GERAL (A13).
   - Cada linha em metros do RESUMO casa com um grupo (A14).
5. **Unicidade:** (contrato, número) único, mais o `bloco` (TOPOGRAFIA, CADASTRO ou serviço) se a numeração for separada por tipo; perguntar ao dono.
   - Reenvio com a mesma impressão de dados = mesmo conteúdo (por exemplo, trocar pelo PDF assinado).
   - Impressão diferente = revisão com motivo e histórico, nunca sobrescrever.
6. **Casamento com a obra:**
   - Zona e PB identificados.
   - Cada segmento casa com exatamente um trecho físico pelas duas pontas.
   - Diferença NS × projeto ≤ max(0,10 m; 0,5%): OK. Até 5%: aviso. Acima: erro.
   - DN e método da NS iguais aos da 06.1 (o demo acusou "método NS MND × 06.1 VCA" no TR020).
7. **Intervalos gerados:** respeitar as regras que já existem (sem sobreposição; reaterro e cadastro de campo só sobre assentado até a data). Trecho MND não gera ESCAVADO nem REATERRADO.

**Avisos (aceita com conferência):**
- Contas auxiliares: cruzeta (A02), boca ≥ fundo (A03), estaca = acumulada (A05), início do grupo (A07).
- Segmentos e notas: nomes dos segmentos (A09), segmento faltando (A10), notas (A15).
- Pessoas: contratada (V04), responsáveis técnicos com CREA (V05), fiscalização sem nome (V06).
- Segmento que termina num nó de cruzamento.

**Fluxo sugerido:** RECEBIDA → CONFERIDA (sem ERRO e revisada por uma pessoa, com a tabela lida ao lado do PDF aberto no próprio navegador, sem render no servidor) → LIBERADA (fiscalização) → usada na medição. Guardar o PDF original, o sha256, a impressão dos dados e a versão do parser.

**Para gravar:**
- O pypdf é Python puro e pequeno; entra no `requirements.txt`. O pdftotext é opcional.
- `etapas_complementares.referencia` já comporta "NS 006".
- `intervalos_execucao.origem` não aceita 'NS' hoje (o CHECK só tem INFORMADO, COMPLETO, SEQUENCIAL, LEGADO, RETIFICACAO). Precisa de migração, ou de origem INFORMADO com a referência da NS.

## 8. Demo de casamento (`demo_casamento.py`)
O stub segue a interface `trechos_fisicos(conn) -> [{id, membros:[{trecho_id, ordem, offset_m, sentido}], extensao_m, no_ini, no_fim}]` (`fisico` `:23`). Foi rodado sobre `pdf_lo/R2_agua.pdf`.

| Situação | Resultado |
|---|---|
| Segmento NÓ6.1→NÓ9.1 | Casa com F-A = TR020, diferença 0 m |
| Segmento NÓ9.1→CH_VRP-15 | Casa com F-B = TR007 + TR006, 295,98 m, diferença 0 m |
| Liberação topográfica da NS inteira | TR020 [0–277,99], TR007 [0–2,51], TR006 [0–293,47] |
| ASSENTADO da estaca 13+17,99 até 20+0,00 | F-B [0–122,01], dividido em TR007 [0–2,51] e TR006 [0–119,50]; atravessa o cruzamento |
| NS que lista o NÓ113.1 como linha | Casa dentro do F-B, com aviso "não é conexão" |

Funções: `casar` `:52`, `intervalo_ns_para_linhas` `:103`, tolerâncias `:20`.
