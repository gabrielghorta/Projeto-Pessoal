# Continuidade dos trechos no mapa (05/11/2026)

**O pedido.** Na Programação, com a Zona 03 em foco, as linhas de 160 não se encontravam. O responsável mandou o
recorte do CAD com o 160 contínuo, passando pelo MV-03, pelo VM-3.2 e pelo HID-02. Também pediu a revisão do mapa
inteiro, nos dois mapas (Mapa iluminado e Programação).

**Onde está o desenho.** Os dois mapas desenham a mesma geometria, `/api/mapa/geral` (`mapa_geral.geometria`).
Por isso a revisão foi feita nessa geometria, com as medidas abaixo, e conferida no navegador.

## 1. O que foi medido

As medidas foram feitas na visão geral do REV02, em metros, sobre os 1.436 trechos e as 2.872 pontas.

| Conferência | Antes | Depois |
|---|---|---|
| Ponta ligada a um nó na 06.1 a mais de 0,25 m do nó (fora cruzamento e passagem) | 17 pontas em 11 nós (até 15,09 m) | 0 |
| Pontas de um tubo só (JUNTAR, 73 junções) a mais de 0,25 m entre si | 4 (J-086, J-087, J-098 e J-103; até 5,89 m) | 0 |
| Desenho que para antes do nó (LONGE_DO_NO) | 2 (15,09 m e 6,65 m) | 0, completado em linha reta |
| Trecho em partes (uma por prancha) que não se tocam na emenda | 2 (2,11 m) | 0 |
| Com uma zona em foco, trechos de outras frentes | escondidos | cinza fino, por baixo |

## 2. As causas

**1. A zona em foco escondia as outras frentes (a causa do print).**
* Com uma zona em foco, os dois mapas desenhavam só os trechos daquela zona.
* A 06.1, porém, divide o tubo na divisa de zona. Na rua do MV-03, o 160 sai do VM-3.2 pelo
  Zona03_PB07_Rede_TR022, passa pela Zona 05 (Zona05_PB07_Rede_TR003, 40,61 m) e volta para a Zona 03
  (Zona03_PB08_Rede_TR036). O trecho original tem 332,12 m.
* A mesma coisa acontece com a Subadutora: os trechos de 200 mm pra cima ficam fora das zonas (D-182). Por isso o
  160 da Zona 03 chegava ao NÓ85.1 e não aparecia o 250 que segue até o MV-03.
* Na tela, a linha parava no meio da rua.

**2. A cópia do trecho que vem de outra prancha.**
* Na visão geral, um trecho que passa por duas pranchas vem em duas partes que se sobrepõem.
* Só a parte mais perto era encaixada no nó. A outra ficava como um rabicho de até 1,6 m ao lado dele.

**3. Pontas de um tubo só, separadas no desenho.**
* O arquivo de decisões (`config/topologia.json`) diz que essas pontas são um tubo só. A prancha, porém, deixou
  as pontas afastadas.
* A maior: J-098, entre Zona07_PB18_Rede_TR004 e Zona07_PB19_Rede_TR019, com 5,89 m.

**4. Desenho curto no NÓ11.1 (Zona 11).**
* O vetor do HTML não tem os últimos 15,09 m do Zona11_PB25_Rede_TR001 nem os primeiros 6,65 m do
  Zona11_PB23_Rede_TR081.
* A parte desenhada mais o que falta dá a extensão da 06.1 nos dois: 30,7 + 15,1 = 45,8 m (L = 45,92 m) e
  94,3 + 6,65 = 100,95 m (L = 100,96 m).

**5. A emenda PB15/PB19.**
* As duas partes do Zona07_PB15_Rede_TR032 (160) e do Zona07_PB19_Adutora_TR001 (315) ficavam 2,11 m afastadas.

## 3. O que mudou

**Servidor (`mapa_geral.py`, `topologia.pontas_juntar`).** O HTML não é alterado.
* Toda parte que termina na ponta do trecho é encaixada no nó, não só a mais perto.
* As pontas JUNTAR se encontram no ponto médio, até 6 m, em todos os desenhos.
* O desenho curto do NÓ11.1 é completado em linha reta até o nó.
  * Vale só na visão geral, e só quando a parte desenhada mais o que falta dá a extensão da 06.1 (até 20 m).
  * Continua pendência de desenho, porque o caminho exato não está no HTML.
* Na visão geral, a ponta solta de uma parte vai até a parte vizinha do mesmo trecho, até 5 m.

**Telas (`iluminado.js`, `planejamento.js`).**
* Com uma zona em foco, os trechos das outras frentes ficam por baixo, cinza e finos.
* Eles não respondem ao toque, não entram na contagem da legenda e aparecem também na cópia do gesto.
* A legenda explica a linha cinza.
* Na obra inteira, nada muda.

## 4. O que fica como está (não é falha de desenho)

* **Cruzamento e passagem (20 pontas):** o tubo passa ao lado do nó, de propósito.
  * Exemplos: NÓ113.1 da Zona 03 e os nós de passagem da PB23/PB24.
  * As duas pontas se encontram entre si, a cerca de 1,5 m do marcador do nó.
* **Junções em dúvida J-099 (1,09 m) e J-100 (0,20 m), Zona 07, PB19:** ficam afastadas até o responsável decidir
  em `config/topologia.json`.
* **Zona 11:** a rede aparece em três partes que não se ligam no desenho.
  * Correm paralelas às da Zona 07, a 3 ou 4 m, cada uma do seu lado da rua.
  * Chegam perto da adutora de 500 em pontas sem nó na tabela.
  * A 06.1 não liga essas partes. Não foi criada ligação.
* **NÓ9.2/NÓ104.1 da Zona 03:** o 160 da Zona 05 (TR003) passa a 2,7 m desse nó sem ligar.
  * A 06.1 liga o nó ao TR035, que corre paralelo ao TR003/TR036, a 2 ou 3 m.
  * Se o projeto tem um 160 só nessa rua, isso precisa ser conferido no CAD.

## 5. Testes

**`tests/test_topologia.py`:**
* `test_toda_ponta_de_no_chega_ao_no`
* `test_pontas_de_um_tubo_so_se_encontram`
* `test_partes_do_mesmo_trecho_formam_uma_peca_so`
* `test_emendar_liga_a_ponta_solta_e_nao_mexe_no_resto`

**`tests/test_telas.py`:**
* `test_zona_em_foco_mostra_as_outras_frentes_em_cinza`
