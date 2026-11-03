# Conferência do mapa com os levantamentos (03/11/2026)

Pedido do responsável em 03/11/2026: o mapa mostrava trechos que não existem. Por isso foram revisados os trechos e os
nós contra os levantamentos originais. A ficha passou a mostrar as coordenadas reais de cada trecho e nó, como no HTML
do projeto. Depois foi conferido se os metros de cada diâmetro fecham com a planilha de tubos e com o projeto.

**Fontes:**
- `planilhas/06.1 - LEV_DMC_MORRO_DA_CRUZ_REDES_REV01_13-10-26.xlsx`, aba REDE: trecho, DE, comprimento e UTM das pontas;
- `planilhas/06.2 - LEV_DMC_MORRO_DA_CRUZ_CONEXÕES_REV08_13-10-26.xlsm`, aba CONEXÕES: coordenadas dos nós;
- `mapa/PLANTAS_TRECHOS_E_NOS_MORRO_DA_CRUZ_REV02_EQUIPES.html`, bloco DADOS: o desenho da visão geral e das 25 PBs;
- o banco do sistema, importado das planilhas;
- o BM, itens 2.2_5.8.x (assentamento de tubo PEAD do grupo REDES);
- a conciliação 06.1 × BM de 17/10/2026, que fica no Drive da obra.

Regra nova: **D-201**, seção 22 de `DECISOES_PENDENTES.md`.

## 1. Trechos e nós: as fontes batem

| Conferência | Resultado |
|---|---|
| Trechos na 06.1, no HTML e no banco | 1.436 nas três; nenhum nome sobrando ou faltando |
| DE, comprimento, nó inicial e nó final | iguais nas três, nos 1.436 trechos |
| UTM das pontas (06.1 × HTML × banco) | diferença de 0 cm em todos |
| Nós: banco × HTML (06.2) | 1.191 elementos e 1.242 nomes, a mesma posição (0 cm). Três sem coordenada no projeto: MV-11, VTF-12 e VTF-16, na bandeja |
| Ponta do trecho × coordenada do nó ligado | 2.721 pontas: mediana de 0 cm. 169 passam de 0,5 m e nenhuma passa de 2 m (a folga da 06.1, já tratada pelo encaixe no nó) |

O que estava errado era **o desenho**, não os dados.

## 2. Os "trechos que não existem": o vetor da PB25

- **A causa.** A visão geral é montada com as 25 pranchas, cada uma passada pela matriz da sua imagem. A foto e o quadro da PB25 estão no lugar certo, mas o **desenho vetorial dela estava deslocado 37,68 m para o norte e 1,81 m para o oeste**. A PB25 tem só 2 nós e a matriz foi feita pelo quadro.
- **O efeito.** Os 3 trechos que passam pela PB25 apareciam duas vezes, e a cópia ficava fora do lugar (o caso do print do responsável):
  - Zona11_PB22_Rede_TR031 (DE 225): cópia de 81,9 m;
  - Zona11_PB22_Rede_TR032 (DE 225): cópia de 0,5 m;
  - Zona11_PB25_Rede_TR001 (DE 225): cópia de 1,9 m.
- **A correção.** `mapa_geral.CORRECAO_VETOR_M` leva as partes da PB25 para o lugar certo na visão geral. O deslocamento foi medido contra o desenho da PB22 nos mesmos trechos. Depois da correção, cada parte da PB25 fica sobre a da PB22, com resíduo médio de 3 cm e máximo de 18 cm.
- **O que não muda.** O HTML do projeto não é alterado, e a foto de satélite da PB25 fica onde estava.
- **Teste:** `tests/test_topologia.py`, `test_pb25_vetor_corrigido_cai_em_cima_da_pb22`.

As 24 outras pranchas foram conferidas pelos nós: o resíduo é de 1 cm.

## 3. Desenho × levantamento, trecho a trecho

O desenho mede a linha do trecho: L − Lx. Lx é o tubo desenhado dentro do nó (410 trechos, 888,89 m).

**Partes repetidas.** O trecho que passa por duas pranchas é desenhado por cada uma delas, e as partes se sobrepõem. Por isso a medição soma cada pedaço uma vez só (264 trechos têm mais de uma parte).

**Resultado:**
- 1.373 trechos (96 %) ficam a até 1 % do comprimento da 06.1;
- nenhum trecho passa de 0,5 m a mais;
- o total desenhado é **135,40 m menor** que a linha da 06.1 (0,12 %).

**Onde está a diferença:**
- **Três desenhos incompletos,** que já eram pendência (`TOPOLOGIA_TRECHOS.md` 2.3):
  - Zona11_PB25_Rede_TR001: faltam 15,09 m (a ponta fica a 15,07 m do NÓ11.1);
  - Zona11_PB23_Rede_TR081: faltam 6,69 m (a ponta fica a 6,69 m do NÓ11.1);
  - Zona07_PB19_Rede_TR019: faltam 5,44 m (o desenho termina antes da UTM do fim).
- **O resto, em emendas entre pranchas:** 108,18 m em 354 trechos, cada um com menos de 2,6 m. Os 105 que passam de 0,5 m estão todos na emenda entre duas pranchas.
- **O que se faz com isso.** A tela já encaixa no centro do nó as pontas a até 2 m. Acima disso, fica pendência de desenho; o sistema não inventa traçado. Os metros de cada trecho no sistema são sempre os da 06.1, nunca os do desenho.

## 4. Metros por diâmetro: sistema × planilha de tubos × projeto

| DE | Sistema | 06.1 (tubos) | Desenho do mapa | Linha da 06.1 (L − Lx) | Desenho − linha | Projeto (BM 2.2) | BM − 06.1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 63 | 70.439,31 | 70.439,31 | 69.531,27 | 69.602,16 | −70,89 | 70.458,38 | +19,07 |
| 90 | 7.877,16 | 7.877,16 | 7.854,60 | 7.860,77 | −6,17 | 7.892,38 | +15,22 |
| 110 | 8.529,34 | 8.529,34 | 8.515,46 | 8.520,26 | −4,80 | 8.672,68 | +143,34 |
| 125 | 881,67 | 881,67 | 880,23 | 880,82 | −0,59 | — (no item 160) | −881,67 |
| 160 | 12.495,17 | 12.495,17 | 12.462,88 | 12.479,78 | −16,90 | 13.455,06 | +959,89 |
| 225 | 4.097,25 | 4.097,25 | 4.069,49 | 4.095,33 | −25,84 | 4.097,26 | +0,01 |
| 250 | 1.001,08 | 1.001,08 | 998,89 | 1.001,08 | −2,19 | 1.001,09 | +0,01 |
| 280 | 463,85 | 463,85 | 463,13 | 463,85 | −0,72 | 463,85 | 0,00 |
| 315 | 2.173,44 | 2.173,44 | 2.161,64 | 2.165,48 | −3,84 | 2.450,75 | +277,31 |
| 355 | 683,91 | 683,91 | 682,85 | 683,91 | −1,06 | 683,91 | 0,00 |
| 400 | 608,93 | 608,93 | 608,40 | 608,93 | −0,53 | 608,93 | 0,00 |
| 500 | 1.434,92 | 1.434,92 | 1.432,90 | 1.434,77 | −1,87 | 1.434,91 | −0,01 |
| **Total** | **110.686,03** | **110.686,03** | **109.661,74** | **109.797,14** | **−135,40** | **111.219,20** | **+533,17** |

**Como ler a tabela:**
- **Sistema = planilha de tubos,** em todos os diâmetros. O sistema mede, programa e libera material pelos metros da 06.1.
- **Desenho − linha** é a seção 3. O DE 225 carrega dois dos três desenhos incompletos (21,78 m). O DE 63 tem o terceiro (5,44 m) e soma 65,45 m de emendas em 211 trechos.
- **BM − 06.1 (+533,17 m)** é a diferença que a conciliação de 17/10/2026 já explica, por diâmetro:
  - **Tubo desenhado duas vezes no DWG** (o quadro e o BM somam, a 06.1 conta uma vez): 452,54 m:
    - DE 110: 143,34 m, quatro pares de linhas iguais no Zona05_PB08_Rede_TR010;
    - DE 315: 277,31 m, duas cópias por cima do tubo;
    - DE 90: 15,19 m;
    - DE 63: 16,64 m.
  - **Pedaços soltos e sobra de desenho no DE 63:** 2,39 m.
  - **DE 125:** o BM não tem item próprio. Os 881,69 m estão no 5.8.37, que descreve DE 160. Juntos, DE 125 e DE 160 dão 13.455,06 m no BM e 13.376,84 m na 06.1.
  - **DE 160: 78,25 m no quadro da prancha que não existem no desenho da V03.** É contradição documental de origem não localizada: o provável é um quadro desatualizado. **Pendente com o projetista.**
  - **Arredondamentos:** −0,01 m.

## 5. Coordenadas reais na ficha

Como no HTML do projeto, a ficha mostra as coordenadas reais (UTM, SIRGAS 2000, fuso 23 Sul):
- **Trecho:** as duas pontas. Cada ponta tem o nó, E e N com 3 casas (as da 06.1) e o link "abrir no mapa" (Google Maps). A latitude e a longitude das pontas saem da UTM (`coordenadas.py`, conferido contra as 4.060 coordenadas do HTML: erro máximo de 1,5 cm, que é o arredondamento do próprio HTML).
- **Nó:** E e N da 06.2, com a latitude e a longitude da planilha.

**Onde aparece:**
- Mapa iluminado: na ficha ao tocar no trecho ou no nó;
- Almoxarifado › Programação: no painel, com um trecho ou um nó escolhido;
- a ficha completa.

**Dados:**
- `servicos.detalhe` → `coordenadas`;
- `dados_obra.selecao` → `linhas[].coordenadas` e `nos[].coordenadas`.

**Testes:**
- `tests/test_coordenadas.py`;
- `tests/test_topologia.py`, `test_coordenadas_reais_nas_fichas` e `test_metros_por_diametro_sistema_igual_a_06_1`;
- `tests/test_telas.py`, `test_coordenadas_reais_nas_tres_fichas`.

## 6. Pendências

1. **DE 160:** os 78,25 m do quadro sem desenho. Confirmar com o projetista qual vale.
2. **DE 125 no item 5.8.37:** validar a equivalência com a Caesb.
3. **Os três desenhos incompletos** (TR001 da PB25, TR081 da PB23 e TR019 da PB19). O vetor do HTML não tem esses pedaços. A planta (imagem do DWG) mostra a linha, e a 06.1 dá a ponta certa. Fica como está até uma nova revisão do HTML.
