# Topologia dos trechos: ponta no nó, cruzamento e trecho físico

Obra da rede de água do Morro da Cruz (CT 10239/2026, Caesb × Ankara). Este documento explica:

* o diagnóstico das pontas dos trechos e das junções que não são conexão;
* a regra adotada e os casos em dúvida;
* como revisar `config/topologia.json`;
* uma proposta, ainda não implementada, de uso do trecho físico no Lançamento do dia e na Nota de Serviço.

Todo número daqui sai de `ferramentas/topologia/diagnostico.py` (arquivo `ferramentas/topologia/saida/resumo.json`).

## 1. As duas regras do responsável pela obra

1. "A LEI MAIS IMPORTANTE DOS TRECHOS É QUE TODO O TRECHO TERMINA EM ALGUM TIPO DE CONEXÃO."
2. "Sempre que tiver uma rede passando por outra com um semicírculo, considere como o mesmo trecho."

A 06.1 continua sendo a unidade da medição e do BM. Nenhuma linha é juntada, renomeada ou apagada no banco.

O **trecho físico** é uma visão por cima das linhas: a cadeia de linhas da 06.1 entre duas conexões reais. Cada linha tem um deslocamento (`offset_m`) e um sentido. Assim, um intervalo do trecho físico vira intervalos em cada linha, e o inverso também.

## 2. Diagnóstico (números verificados)

### 2.1 06.1 e nomes de nó (reproduz a seção 4 do roteiro)

| Dado | Valor |
|---|---|
| Linhas da 06.1 | 1.436 (1.400 Rede, 36 Adutora), todas PEAD; VCA 1.432 e MND 4; 110.686,03 m |
| DE presentes | 63, 90, 110, 125, 160, 225, 250, 280, 315, 355, 400 e 500 |
| Pontas sem identidade de nó | 151, em 122 trechos: DIVISA DE ZONA 72, PONTA SEM NÓ NA TABELA 63, LIMITE DA TRAVESSIA MND 10, JUNÇÃO SEM NÓ NA TABELA 6 |
| Trechos divididos pela 06.1 | 55 na divisa de zona e 9 no limite da travessia MND |
| Números de nó nas pontas | 328 distintos (NÓ, DF, VM, VRP…); 145 se repetem entre PBs; o NÓ1.1 aparece em 23 combinações Zona_PB; contando só nós, 231 números |
| Ponta com prefixo Zona_PB do nó diferente do prefixo do trecho | 234 (o roteiro dizia ~246) |
| Pares de trechos com as mesmas pontas | 4: Zona03_PB08 TR024 × TR026, Zona06_PB15 TR003 × TR005, Zona11_PB23 TR057 × TR058 e Zona11_PB24 TR039 × TR040 |
| Nós de grau 2 | 329; em 57 deles as duas linhas chegam ambas ou saem ambas do nó (o roteiro dizia 59 de 334) |

No par Zona11_PB24 TR039 × TR040, só um tubo se liga aos nós NÓ60.1 e NÓ65.1, que é o TR039. O TR040 passa ao lado dos dois nós (ver 2.4). Agora eles se separam pela topologia: o TR040 faz parte do trecho físico TR061 + TR040 + TR037.

### 2.2 Sistemas de coordenadas (5.1)

A transformação afim UTM → desenho foi ajustada por mínimos quadrados nos nós que têm UTM (06.2) e posição no desenho:

* **Visão geral:** 0,700 unidade por metro, sem rotação, 1.188 nós. Resíduo: mediana 5,7 mm, p95 8,4 mm, máximo 1,04 cm.
* **Pranchas PB01–PB24:** 2,834645 unidades por metro (1:1000 em pontos). Resíduo máximo de 2,6 mm. A PB20 é desenhada girada 90°.
* **PB25:** tem só 2 nós. A transformação composta (visão geral ∘ matriz da imagem) erra 37,8 m nesses nós. O quadro e a imagem da PB25 estão no lugar certo, mas o **desenho vetorial da PB25 no HTML está deslocado ~37,6 m**. Por isso aparecem cópias fora do lugar de 3 trechos na visão geral: Zona11_PB22_Rede_TR031, TR032 e Zona11_PB25_Rede_TR001. Isso foi registrado como pendência e o HTML não foi alterado.

### 2.3 Pontas (5.2)

Cada ponta foi medida em metros, contra o nó da 06.1, a partir da polilinha da visão geral (a mesma que a tela usa). Os resultados estão em `pontas.csv`: as 2.872 pontas vão para o Drive, e o PR traz `pontas_fora_do_no.csv`.

| Classe | Pontas | Ação de desenho |
|---|---|---|
| NO_NO (até 10 cm do nó) | 2.249 | NADA |
| DESLOCADA (ao lado do nó) | 318 | ESTENDER_ATE_NO |
| NAO_CHEGA (para antes do nó, na linha) | 130 | ESTENDER_ATE_NO |
| PASSA_DO_NO | 2 | APARAR |
| DIVISA_ZONA / LIMITE_MND / PONTA_SEM_NO / JUNCAO_SEM_NO | 72 / 10 / 62 / 6 | MANTER_SEM_NO |
| PASSAGEM / CRUZAMENTO (pelas decisões) | 16 / 4 | NAO_ENCAIXAR |
| LONGE_DO_NO (> 2 m) | 2 | PENDENCIA_DESENHO |
| DESENHO_INCOMPLETO (o desenho para antes da UTM da 06.1) | 1 | PENDENCIA_DESENHO |

* **Distância da ponta ao nó:** 472 pontas a mais de 0,10 m, 164 a mais de 0,5 m, 55 a mais de 1 m e 2 a mais de 3 m. Tirando as pontas das junções, ficam 396, 88, 35 e 2.
* **As duas pontas a mais de 3 m:**
  * Zona11_PB25_Rede_TR001, fim, a 15,07 m do Zona11_PB23_Rede_NÓ11.1;
  * Zona11_PB23_Rede_TR081, início, a 6,69 m do mesmo nó (o NÓ11.1 já vem marcado "fora" no HTML).
* **Desenho incompleto:** a polilinha do Zona07_PB19_Rede_TR019 termina 5,44 m antes da ponta que a 06.1 dá para o fim desse trecho.
* **Visão geral × pranchas:** é o mesmo traçado. Em 2.719 pontas comparadas, a maior diferença é 0,20 m, e só 2 passam de 5 cm. O problema está nas duas, porque vem das polilinhas do levantamento. A imagem das pranchas (plotagem do DWG) mostra a linha chegando ao nó, como no caso A.
* **Comprimento desenhado × L:** o desenho mede L − Lx.
  * Lx é o "tubo desenhado no próprio nó": 410 trechos, 888,89 m, até 8,40 m numa linha.
  * Nos 1.172 trechos desenhados numa parte só, 320 diferem de L em mais de 5 cm e só 19 diferem de L − Lx. A maior diferença é 5,45 m, no TR019 citado acima.
  * Σ L = 110.686,03 m e Σ (L − Lx) = 109.797,14 m.
* **A ponta do desenho fica sobre a UTM da 06.1** (até 2,5 cm). A diferença é que a 06.1 ligou a ponta ao nó com folga.

**Caso A** (Zona04_PB06_Rede_TR002):

* A ponta inicial fica a **1,465 m** do NÓ2.1: 1,445 m ao longo da linha e 0,24 m de lateral. Classe NAO_CHEGA.
* Agora o desenho é estendido até o centro do nó, na visão geral e na PB06.
* O fim do trecho (NÓ2.2) já estava no nó.

### 2.3.1 Hipótese do anel de ~1,5 m: derrubada

Se o marcador do nó fosse um anel de ~1,5 m onde as linhas param, as pontas fora do nó se juntariam perto de 1,5 m. Não é o que acontece:

* Das 2.721 pontas com nó, 2.253 (83 %) estão a até 10 cm.
* As 468 restantes se espalham de 0,1 a 1,6 m, com mediana de 0,43 m. O maior grupo fica entre 0,3 e 0,5 m (181 pontas).
* Só 36 pontas (1,3 %) ficam entre 1,3 e 1,7 m, e 18 delas são de tubos que passam ao lado do nó (cruzamento ou passagem).
* Nenhuma ponta passa de 1,60 m, e o máximo é 1,58 m. Esse teto é a folga que a 06.1 usou para ligar ponta a nó, e não o raio de um anel.
* O "tubo desenhado no próprio nó" (Lx) também não é o vão até o nó. No lado citado na observação, a ponta desenhada está a até 10 cm do nó em 287 de 386 pontas.
* O caso A (1,465 m) é uma linha que para antes do nó, como as outras 129 da classe NAO_CHEGA.

A correção do desenho continua sendo levar a ponta ao centro do nó, mas pela medida de cada ponta e com teto de 2 m, e não por um raio fixo.

### 2.4 Junções que não são conexão (5.3 e 5.4)

Arquivo `cruzamentos.csv` (110 candidatos) e `config/topologia.json`.

| Tipo | JUNTAR | NAO_JUNTAR | DUVIDA |
|---|---|---|---|
| CRUZAMENTO (semicírculo do pulo) | 2 | – | – |
| PASSAGEM (tubo ao lado do nó, sem peça para ele) | 8 | – | – |
| CONEXAO (candidato rejeitado: as peças do nó ligam o par) | – | 28 | – |
| DIVISA_ZONA | 36 | – | – |
| LIMITE_MND | 5 | – | – |
| PONTA_SEM_NO (emenda sem nó na tabela) | 27 | – | 2 |
| JUNCAO_SEM_NO (3 tubos sem nó: tê que falta na 06.2) | – | 2 | – |
| **Total** | **78** | **30** | **2** |

**Cruzamentos com semicírculo:**

* **J-001, caso B, Zona03_PB08_Rede_NÓ113.1:**
  * TR007 + TR006 (DE 160), com arco nas duas pontas e o TR011 cruzando ali.
  * O NÓ113.1 recebe 5 pontas, mas as peças ligam 3: o tê 90º 110 e a redução 160×110, com a luva 110 como acessório. Elas ligam TR003, TR004 e TR011, e não sobra peça para o tubo que passa.
  * A imagem da PB08 mostra o semicírculo do DE 160 pulando o TR011, que sobe até o tê.
  * A observação da 06.1 do TR006 ("anel de ponta/toco") se refere a esse arco.
* **J-002, Zona06_PB14_Rede_NÓ56.12:** TR004 + TR012 (DE 160), com arco nas duas pontas. São 5 pontas para peças que ligam 3. Na prancha aparecem dois semicírculos.

**Passagens ao lado do nó (sem semicírculo):** a linha passa reta, a 1,25–1,59 m do marcador de um nó de outra rede paralela, e a 06.1 cortou a linha ali. Na prancha, o tubo é contínuo e o nó pertence à outra linha.

* **J-003, Zona02_PB10_CH_MV-02:** a Adutora DE 280 (TR004 + TR001) passa ao lado da caixa do macromedidor. Pela redução 160×90, as peças da caixa são da Rede DE 160. O par da Rede, TR004 + TR007, foi rejeitado como CONEXAO.
* **J-004 a J-008, Zona11_PB23 (NÓ11.3, NÓ11.4, NÓ9.2, NÓ9.4, NÓ9.6):** duas redes paralelas, DE 160 e DE 225. O canto de uma fica a ~1,5 m do canto da outra.
* **J-009 e J-010, Zona11_PB24 (NÓ60.1 e NÓ65.1):** o tubo TR061 + TR040 + TR037 passa ao lado dos dois nós da linha paralela TR039.

**Divisa de zona e limite de MND:**

* Os 36 + 5 pares estão no mesmo ponto (0,00 m) e têm o mesmo DE. A própria 06.1 diz que o tubo foi dividido ali.
* A 06.1 registra 23 grupos de trechos divididos com "TRECHO ORIGINAL ENTRE PONTOS DA REDE". Cada um ficou inteiro dentro de um só trecho físico.

**Emendas sem nó (PONTA SEM NÓ NA TABELA):**

* São 29 pares. Em 27 deles as pontas estão a até 1,0 m e a linha segue com ângulo ≥ 120°. Nas pranchas, o tubo é contínuo.
* Os 2 restantes estão em dúvida (seção 4).
* Há 5 pontas sem par: são pontas de trecho físico sem conexão (pendência).

### 2.4.1 O inverso do cruzamento: conexão no meio de uma linha da 06.1

A revisão cega (seção 3) achou o caso contrário no NÓ1.5 da Zona08/PB10. O tê do nó (TÊ 90º 63) tem só o ramal TR029 chegando. O TR016 passa por ele, 0,46 m depois de sair do NÓ1.4, e a 06.1 não cortou a linha ali.

A ferramenta procura esse caso em todo nó ou caixa com pelo menos 2 bocas sobrando, que é a passagem de um tê, e com uma linha da 06.1 a até 0,5 m do marcador, no meio da linha. Encontrou **29**:

* 23 ventosas (VTF), cujo tê, inclusive o de sela, fica sobre a linha;
* o hidrante HID-02;
* 5 nós com tê ou curva a 0,4–0,6 m da ponta de uma linha que termina num nó vizinho: NÓ1.1 (Zona04_PB03), NÓ1.4 (Zona02_PB07), NÓ107.2 (Zona05_PB08), NÓ1.5 (Zona08_PB10) e NÓ2.3 (Zona08_PB13).

A Nota de Serviço corta o tubo nesses pontos, e a 06.1 não. Como o trecho físico é feito de linhas inteiras, esses pontos ficam como pendência `CONEXAO_NO_MEIO_DA_LINHA`, com a posição em metros a partir da ponta inicial da linha. A posição sai do desenho e por isso é aproximada; nas 6 linhas desenhadas em mais de uma prancha ela não é calculada. Ver a seção 8.

### 2.5 Trechos físicos (5.5)

* **1.358 trechos físicos**, dos quais **48 têm mais de uma linha** e somam 126 linhas da 06.1. A maior cadeia tem 9 linhas: as divisas de zona entre a Zona09 e a Zona10, de VM-10.2 até NÓ9.2, com 540,44 m.
* As 1.436 linhas estão, cada uma, em exatamente um trecho físico. Σ extensões = 110.686,03 m, igual à 06.1.
* 10 cadeias têm membro com sentido −1.
* `cadeias.csv` traz os membros em ordem, com offset, extensão, sentido e a junção seguinte.

## 3. Regra final

Uma ponta que termina no **nome de um nó** só deixa de ser fim de trecho quando estes sinais concordam:

1. **Orçamento de peças:** as peças do nó na 06.2 ligam no máximo N pontas de tubo, e chegam mais do que N.
   * Tê (inclusive o de redução e o de sela) = 3 bocas; curva, redução, válvula, VRP e medidor = 2.
   * A luva conta 2 só quando é a única peça do nó.
   * Montagem em árvore: Σ bocas − 2 × (peças − 1).
2. **Continuidade:** um par do mesmo DE e material, com pontas juntas (≤ 0,30 m) e alinhadas (≥ 150° entre as direções de saída, medidas depois do arco), afastadas do marcador do nó (≥ 0,50 m).
3. **Tirando o par**, as outras pontas cabem exatamente nas peças. Se mais de um par passa, entra primeiro o par cujo DE não aparece nas peças do nó e, depois, o mais afastado do marcador.
4. **Tipo:** CRUZAMENTO se há arco perto da ponta ou outra linha cruzando a até 0,75 m; senão, PASSAGEM.

Se sobra peça para o par, é conexão (luva, redução, tê, válvula): NAO_JUNTAR. Se falta peça mas o par está no marcador ou a conta não fecha: DUVIDA.

Pontas **sem nó** na 06.1:

* **Divisa de zona e limite de MND:** juntam quando as duas pontas estão no mesmo ponto e têm o mesmo DE e material. Muda só a frente ou o método.
* **Emenda sem nó:** junta com folga ≤ 1,0 m e ângulo ≥ 120°.
* **3 ou mais tubos no mesmo ponto:** não junta (é um tê que falta na 06.2).
* **Troca de DE ou de material:** nunca junta sem decisão do responsável, e o sistema recusa essa decisão no arquivo.

**Por que essas tolerâncias:**

* A 06.1 ligou ponta a nó até 1,59 m: das 2.721 pontas com nó, nenhuma passa de 1,60 m.
* Encaixar até 2 m cobre todas, e o que passa disso é defeito de desenho (6,7 m e 15,1 m).
* 10 cm é o arredondamento do desenho: 0,1 unidade de prancha = 3,5 cm.
* As pontas dos tubos que passam ficam a 1,25–1,59 m do marcador. As das caixas, em que o tê fica na linha ao lado da caixa, ficam a 0,5–0,85 m e são rejeitadas pelo orçamento de peças.

**O que mudou na regra ao tentar derrubá-la (5.6):**

* **Arco do pulo:** o ângulo do caso B dava 152°, porque o arco desvia a corda e há um degrau de 3 cm no começo do TR007. A direção passou a ser medida depois do arco, e o caso B foi para 178°.
* **Na MV-02:** a primeira versão juntava dois pares, a Adutora e a Rede. Pelo orçamento só um passa, e agora entra primeiro o par cujo DE não aparece nas peças.
* **Emendas sem nó:** a primeira regra (folga ≤ 0,10 m e ângulo ≥ 150°) deixava 8 em dúvida. Nas pranchas, 7 eram tubo contínuo (folgas de 0,05 a 1,0 m, uma dobra de 149°). A regra passou a folga ≤ 1,0 m e ângulo ≥ 120°.
* **Falsos negativos:**
  * Das 18 pontas com arco fora das junções, todas estão no marcador de um nó cujas peças dão conta dos tubos. São pulos ou curvas logo depois de sair do nó.
  * Os 10 nós de grau 4 ou 5 são todos passagens ou cruzamentos.
  * O único outro nó com peça a menos é a VM-5.4 (pendência).
* **Falsos positivos:**
  * Os 19 nós de grau 2 só com redução não juntam.
  * Nenhum JUNTAR tem troca de DE ou material.
  * As 28 caixas e tês com par alinhado (DF, MV, VM, NÓ56.x) são rejeitadas pelo orçamento de peças.
* **Revisão cega por imagem:**
  * Um revisor independente olhou 31 recortes de 10 zonas sem ver as decisões: cruzamentos, passagens, conexões rejeitadas, emendas sem nó, divisas, MND e tês sem nó.
  * Concordou em juntar ou não juntar nos 31: 17 JUNTAR, 13 NAO_JUNTAR e 1 DUVIDA. A única diferença é o J-100, que ficou em DUVIDA aqui e ele marcou NAO_JUNTAR; nos dois casos a linha não junta.
  * Ele leu as conexões rejeitadas como caixas de dispositivo (círculo laranja com triângulo) ou tês, e as passagens como "linha contínua, nó da rede paralela a ~1,5 m".
  * Nos 4 controles com arco:
    * 3 se ligam no nó: o semicírculo fica a 2–2,5 m, pulando outra linha;
    * o quarto (Zona08_PB10_Rede_NÓ1.5) mostrou o caso inverso da seção 2.4.1.

## 4. Casos em dúvida e pendências (`GET /api/topologia` → `pendencias`)

* **Decisões em DUVIDA:**
  * **J-099:** Zona07_PB19_Rede_TR016 (fim) + Zona07_PB19_Rede_TR019 (início). Pontas sem nó a 1,00 m, com ângulo de 141°. A prancha mostra um vão de ~1 m na linha laranja.
  * **J-100:** Zona07_PB19_Rede_TR017 (6,00 m) + Zona07_PB19_Rede_TR018 (1,99 m), junto do NÓ54.9. Ângulo de 50°: os dois formam um quadradinho desenhado na camada da rede, que parece símbolo e não tubo.
* **Desenho:**
  * Zona11_PB23_Rede_TR081 (início, 6,69 m do NÓ11.1).
  * Zona11_PB25_Rede_TR001 (fim, 15,07 m do NÓ11.1).
  * Zona07_PB19_Rede_TR019 (fim, desenho incompleto).
  * PB25 com o desenho vetorial deslocado 37,8 m.
* **Peças a menos:** Zona03_PB08_CH_VM-5.4. Chegam 3 pontas (TR032, TR040 e TR041), e a 06.2 lista 2 luvas DE 125 e uma válvula 100 para nenhum tubo DE 125.
* **Tês sem nó na 06.2:**
  * Zona04_PB05 TR020 + TR027 + TR031 (160/160/63);
  * Zona06_PB12 TR017 + TR022 + TR024 (63).
* **Trecho isolado:** Zona11_PB23_Adutora_TR006, com 2,40 m de DE 500 no meio da rua, a 32 m do nó mais perto.
* **Conexão no meio de uma linha da 06.1 (29):** ver 2.4.1. São 23 ventosas, o HID-02 e 5 nós com tê ou curva junto da ponta de uma linha que termina no nó vizinho.
* **Pontas de trecho físico sem conexão** (15): as 6 dos tês sem nó, as 4 das duas dúvidas e:
  * Zona11_PB23_Adutora_TR005 (início da adutora DE 500);
  * Zona11_PB23_Adutora_TR006 (as duas pontas);
  * Zona11_PB23_Rede_TR077 (ponta de 9,44 m de DE 225);
  * Zona11_PB23_Rede_TR080 (fim do DE 225, a 6,64 m do início da adutora).

## 5. Como revisar `config/topologia.json`

* **O que tem em cada junção:**
  * `id`, `tipo`, `no` e `utm`;
  * `pontas`: o trecho pelo nome visível vigente e o lado `ini` ou `fim`;
  * `decisao` (JUNTAR / NAO_JUNTAR / DUVIDA) e `motivo`;
  * `sinais`: geometria, continuidade, peças e observação da 06.1.
* **Para mudar uma decisão:**
  1. Troque `decisao`.
  2. Explique em `motivo`.
  3. Preencha `"revisao": {"por": "nome", "em": "AAAA-MM-DD"}`.
  4. Faça commit. O histórico fica no Git.
* **O que o sistema usa:** só lê o arquivo e usa apenas JUNTAR.
* **O que o sistema recusa:** uma junção que não bate com o banco (trecho que não existe mais, ponta em outro nó, troca de DE) é ignorada e vira pendência DECISAO_DESATUALIZADA.
* **Quando regerar:** depois de uma revisão nova da 06.1, da 06.2 ou do mapa, rode `python ferramentas/topologia/diagnostico.py --gravar`. A ferramenta mantém o `id` de cada junção e **toda decisão com `revisao` preenchida**.
* **Por que um arquivo revisável:** se o sistema decidisse sozinho a cada leitura do mapa, um desenho novo mudaria em silêncio o que é trecho físico, e com isso os metros lançados.

## 6. Interface

* `topologia.trechos_fisicos(conn)`: lista de trechos físicos. Cada um tem `id` = `TF-` + o número do menor `trechos.id` entre os membros (ex.: TF-00337), `no_ini`, `no_fim`, `extensao_m`, `de_mm`, `material`, `metodologias`, `frentes`, `membros` [`trecho_id`, `ponto`, `ordem`, `offset_m`, `extensao_m`, `sentido`], `juncoes` [`id`, `no`, `tipo`, `decisao`, `posicao_m`] e `texto` (frase para a ficha). Uma linha sem junção vira um trecho físico de um membro (offset 0, sentido 1).
* **Sentido da cadeia:** o da 06.1 no membro mais longo (empate: menor `id`). Regra estável enquanto os membros não mudam. O caso B sai de NÓ9.1 até VRP-15, com os dois membros em +1.
* `fisico_do_trecho(conn, trecho_id)`, `para_linhas(fisico, ini_m, fim_m)`, `para_fisico(fisico, trecho_id, ini_m, fim_m)` e `pendencias(conn)`.
  * Conversão: com sentido +1, local = [x − offset, y − offset]; com −1, [ext − (y − offset), ext − (x − offset)].
  * Os valores são cortados em [0, ext] e arredondados ao mm.
* **Cache:** pela data de modificação do arquivo e por uma impressão digital dos trechos vigentes. Funciona sem o mapa.
* `GET /api/topologia`: devolve `resumo`, `cadeias` (só as de mais de uma linha), `cruzamentos` (todas as junções do arquivo) e `pendencias`.
  * `?trecho=<id ou nome visível>` devolve só o trecho físico daquela linha.
  * `?desenho=1` devolve, para o mapa REV02, as pontas a encaixar em cada desenho.
  * Telas: mapa e iluminado.

## 7. O que mudou na tela

* **Mapa iluminado:**
  * A ponta de cada linha vai até o centro do nó. A exceção são as pontas de cruzamento e de passagem, em que o arco do pulo fica como está.
  * Ao tocar num trecho de uma cadeia, as outras linhas acendem junto.
  * A ficha ganha a linha "Trecho físico", por exemplo: "TR007 + TR006 = 295,98 m, de NÓ9.1 até VRP-15. NÓ113.1 é cruzamento (não é conexão)."
* **Dados da obra (mapa REV02):**
  * O encaixe vale na visão geral e nas 25 pranchas, sem mudar o HTML.
  * O trecho físico acende ao selecionar.
  * O painel ganha a seção "Trecho físico".

## 8. Proposta (não implementada): Lançamento do dia e Nota de Serviço

* **Conversão de metros:**
  * A equipe ou a NS informa um intervalo no trecho físico, de estaca a estaca, com 0 no `no_ini`. Se a NS vier no sentido contrário, troca-se x por ext − x.
  * `para_linhas` devolve um intervalo por linha da 06.1.
  * A NS casa cada segmento (conexão → conexão, DE, extensão) com um trecho físico pelos nós das pontas. A extensão serve de conferência: a diferença vira alerta, nunca ajuste silencioso.
  * **Conexão no meio de uma linha (2.4.1):** quando a NS termina um segmento numa ventosa ou num tê que a 06.1 não cortou, o segmento vira um intervalo do trecho físico. Ex.: do NÓ1.4 até o NÓ1.5 = [0; 0,46] m do TR016. A posição da pendência serve de ponto de partida, e quem manda é a estaca da NS.
* **Gravação:**
  * `servicos.apontar` é chamado **uma vez por membro, na mesma requisição e na mesma transação**: ou grava todos, ou nenhum.
  * Cada chamada leva o intervalo local da linha, e `intervalos_execucao` continua com 0 no `no_ini` de cada linha.
  * A requisição guarda o `id` do trecho físico em `referencia`, para o histórico mostrar o lançamento como um só.
* **"100 % concluído":** é calculado por trecho físico. Fica concluído quando todos os membros estão cobertos. Mostra "TR007 + TR006: 295,98 de 295,98 m" e marca os membros juntos no mapa.
* **OK interno, medição e BM:** continuam **por linha da 06.1**, porque o BM é por linha. O OK do trecho físico é a soma dos OKs dos membros, e a tela sugere dar o OK nos membros juntos.

## 9. Como rodar

```
python ferramentas/topologia/diagnostico.py            # mede e grava os CSVs em ferramentas/topologia/saida/
python ferramentas/topologia/diagnostico.py --gravar   # ... e regrava config/topologia.json (mantém as revisões)
python ferramentas/topologia/recortes.py               # uma imagem por junção (saida/recortes/, fora do Git)
python ferramentas/topologia/recortes.py --no Zona03_PB08_Rede_NÓ113.1
python -m unittest tests.test_topologia -v
```

O `pontas.csv` completo e os recortes ficam na pasta de trabalho do Drive: `07_IA_CHATGPT_E_CLAUDE/topologia_trechos_2026-10-20`.
