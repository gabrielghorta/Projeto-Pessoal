# Módulo D — planejamento e mapa

CT 10.239/2026 · 17/10/2026 · esquema v12 · plano: `docs/PLANO_ENTREGA_COMPLETA.md` §D

## Atualização de 21/10/2026: grupo Planejamento, mapa do Dados da obra e cronograma (D-75 a D-77)

**Grupo Planejamento** (antes Almoxarifado): Dados da obra, Programação das equipes, Cronograma da obra, Estoque e movimentos (com o aceite ou a recusa do material entregue, o mesmo da inspeção em Compras e notas), Compras e notas, Check-in e check-out.

**Dados da obra** (`web/planejamento.js`, `dados_obra.py`) é um mapa próprio sobre o traçado do REV02 (o mesmo visor do Mapa iluminado); o mapa técnico REV02 continua abrindo à parte, pelo botão da tela.

| Ação | Como funciona | Grava em |
|---|---|---|
| Escolher trechos | Toque escolhe um; Ctrl + clique (ou o botão "Juntar trechos") junta vários. Cada linha traz o trecho físico inteiro (`topologia.py`); o nó que liga dois trechos escolhidos entra sozinho; outro nó entra se for tocado (com o mapa aproximado). | — (`GET /api/dados-obra/selecao`) |
| Programar | Equipe, serviço, de/até e os dias da semana de trabalho: uma programação por alvo (linha ou nó) e por dia, com o mesmo carimbo de criação (o lote). A igual já existente é mantida. "Cancelar o que falta" cancela as PLANEJADAS do lote a partir de hoje, com motivo. | `programacoes` |
| Liberar material | Sugestão do projeto: tubo da 06.1 pelo que falta assentar e as peças dos nós (06.2 → BM Vertical), menos o que já está com a equipe e limitada ao que há no almoxarifado. Abre o check-in da equipe (alvo = primeira linha) ou soma ao check-in aberto do mesmo dia; as programações do dia da equipe para a seleção ficam REALIZADAS por esse check-in. | `checkins`, `movimentos` (CUSTODIA), `programacoes` |
| Reservar | Para um dia que ainda não chegou: reserva para a equipe (o check-in daquele dia consome). | `reservas` |
| Devolução | O check-out de sempre, por material: devolvido, perda (com motivo) e o que fica com a equipe; o resto conta como aplicado. | `movimentos` (APLICADO/SOBRA/PERDA) |

**Cores do mapa:** sem programação (cinza tracejado), liberado pela topografia (azul-claro), concluído (branco), começado sem equipe no dia (laranja tracejado), programado para os próximos dias (amarelo tracejado), programado para o dia (amarelo), equipe trabalhando no dia (laranja, com o pino da equipe). O que se faz aqui alimenta o Mapa iluminado: a camada `em_campo` (`planejamento.em_campo`) acende como "em execução" os trechos cobertos pelo check-in aberto do dia.

**Cronograma da obra** (`cronograma.py`): o XML do Project (Arquivo › Salvar como › Formato XML), ou a planilha .xlsx/.csv exportada. O `.mpp` é recusado com a instrução. O arquivo fica como veio em `documentos/cronograma/` (com `cronograma.json` e `historico.json`); a tela mostra as tarefas em barras (filtros por texto, frente, em andamento, próximas 2 semanas, atrasadas e ligadas a trechos), o % do Project e, nas tarefas que citam trechos, o assentado registrado no sistema.

**Testes:** `tests/test_dados_obra.py` (9) e `tests/test_cronograma.py` (5).

## Finalidade operacional

| Novo | Para que serve | O que não é |
|---|---|---|
| **Programação** (data, equipe, trecho ou nó, serviço, intervalo previsto, materiais previstos) | Planejar a semana das equipes e cobrar o realizado. | Não é presença nem execução. O check-in da equipe naquele dia e alvo a marca como **REALIZADA**. O que não aconteceu é encerrado como **NÃO REALIZADA** ou **CANCELADA**, com motivo. |
| **Programado × realizado** | Medir a aderência ao planejamento. | — |
| **Faltantes** | Antecipar falta de material para a programação. | Mostra previsto, reservado para a equipe naquele dia, disponível, a receber dos pedidos e faltante = previsto − reservado − disponível. |
| **Filtro por frente** (11 zonas, Adutora, CH) | Ver os números de uma frente. | — |
| **Camadas do mapa** | Andamento, Planejado (7 dias), Material, Informado × verificado, Cadastro e Pendências, todas calculadas no servidor **só a partir dos registros efetivos**. | "Verificado" e "conforme" são conferência interna Ankara (azul). O verde fica para o OK interno (já identificado como "não é aprovação Caesb") e para a decisão da Caesb registrada pelo memorando ESET. |

## Camadas do mapa técnico REV02 (aberto à parte desde 21/10/2026)

| Camada | Cores |
|---|---|
| Andamento | Não executado, em execução, concluído aguardando OK, OK interno, medido antes. O miolo branco marca informado sem verificação. |
| Planejado (7 dias) | Programado para hoje (roxo); nos próximos 7 dias (azul); sem programação (cinza pontilhado). |
| Material | Com a equipe (custódia de check-in aberto); reservado; sem material. |
| Informado × verificado | Verificado; parcial; informado; legado sem posição; sem execução. |
| Cadastro | Levantamento parcial ou completo; esteira (pronto, produção, recebido); protocolado no GDOC; negado pela Caesb; aprovação Caesb registrada. |
| Pendências | Ocorrências abertas, reaterro sem cadastro e legado sem posição: 1–2 (laranja) e 3 ou mais (vermelho). |

O modo Projeto restaura as cores de diâmetro da REV02 e esconde o seletor. Zoom, enquadrar, tela cheia e painéis recolhíveis são os da própria REV02, que não é alterada.

## Detalhe pelo mapa

Clique no trecho ou nó, ou use a busca. O painel de Fiscalização mostra:
- pendências;
- informado × verificado;
- intervalos e histórico de retificações;
- soldas;
- fotos (com validação);
- liberação e escavação;
- ocorrências;
- fases do cadastro;
- **programação**;
- **histórico de alterações** (auditoria do objeto: quem fez o quê, aceito ou recusado).

Documentos de compra (NF, laudo) ficam na aba 2.1, porque se ligam à nota e não ao trecho.

## Testes (`tests/test_planejamento.py`, 4)

- **Programação:** recusas (repetida, fora do trecho, serviço inválido). Planejar não movimenta nada. O check-in marca REALIZADA só a do mesmo dia e alvo; NÃO REALIZADA exige motivo; contagem por situação.
- **Faltantes:** previsto 40, reserva 5, disponível 20 → faltante 15. O filtro por frente funciona.
- **Camadas:**
  - planejado para hoje;
  - reservado → com a equipe depois do check-in;
  - a programação realizada sai do planejado;
  - levantamento parcial;
  - 2 pendências (ocorrência e reaterro sem cadastro).
- **Pelo HTTP:**
  - a equipe não programa (403);
  - o autor é o usuário da sessão;
  - filtro por frente na programação e nos números;
  - camadas no estado do mapa;
  - programação no detalhe.

## Navegador (banco v7 real migrado para v12)

- **Frente:** obra inteira 110.686,03 m e 1.436 trechos; Zona01 10.898,35 m e 128 trechos; CH sem trechos (só caixas).
- **Programação:** TR001 para amanhã (assentamento 40–76,55 m, com 40 m de tubo) aceita; a repetida é recusada; TR003 hoje (ligações). Faltantes: 40 m (disponível 0).
- **Camadas** (prancha PB01):
  - planejado: 2 trechos;
  - verificação: 3;
  - cadastro: 2;
  - pendências: 1;
  - andamento: 2 em execução e 1 com OK.
- **Modo Projeto:** seletor oculto e cores de DE restauradas.
- **Zoom:** "−" e "+" mudam o enquadramento; o botão de tela cheia está presente; o painel lateral recolhe.
- **Detalhe do TR001:** programação de 18/10 planejada, e o histórico mostra o aceite e a recusa da programação repetida.
- **Defeitos achados e corrigidos nessa validação:**
  1. a data padrão da programação abria com hoje;
  2. no detalhe, o campo `tipo` do trecho ("TERCIÁRIA") sobrescrevia o tipo do objeto e escondia a programação;
  3. a seleção ia ao mapa e voltava, redesenhando o painel e fechando o histórico.
- Sem erros de JavaScript.

## Limitações

- A cobertura dos pins (o local de cada equipe) continua vindo do check-in, como "programado". A programação antecipada aparece na camada Planejado.
- O filtro por frente vale para números, programação e faltantes. No desenho, a navegação por frente e PB é a da REV02.

## O dia da equipe no Dados da obra (esquema v20, 23/10/2026)

Saem os menus Programação das equipes e Check-in e check-out (D-102, D-103); os links antigos `#prog` e `#ponto` levam ao Dados da obra. O macro é o Cronograma; o micro é o Dados da obra, que é **o dia** (D-104):
1. **Programar:** equipe + trechos escolhidos no mapa para um dia (`dados_obra.programar`). Outra equipe no mesmo trecho no mesmo dia pede confirmação.
2. **Liberar o material do dia:** o almoxarife abre a equipe do dia (também pela lista "Equipes programadas hoje" em Estoque e movimentos) e libera as peças; o check-in grava todos os trechos (`checkin_alvos`, D-116).
3. **Mapa:** na hora, os trechos ficam "em execução hoje" e o pino da equipe aparece em cada um, no Mapa iluminado e na tela Início, até a NS do dia de hoje chegar.
4. **Devolução** no fim do dia, pela mesma tela.

O mapa do Dados da obra (D-108):
- tela cheia de verdade (⛶), com o painel como gaveta ou folha de baixo;
- o mapa não se move sozinho (⌖ para ver a obra inteira; a última vista fica guardada na sessão);
- zonas sempre com a cor delas, e o primeiro toque em outra zona troca o foco;
- nomes completos ("Zona 03 · PB06 · TR014");
- busca pelo código inteiro (D-120).

## Satélite, seleção por zona, ponta de rua e equipe da zona (28/10/2026, D-176 a D-179)

Substitui o pedido de 22/10 de mapa sem satélite e a seleção com Ctrl (ou "Juntar trechos").
- **Satélite (D-176):** o mapa do Dados da obra usa as mesmas fotos do Mapa iluminado (o mosaico `/mapa/geral.webp` e as PBs em resolução cheia quando se aproxima), com o véu claro, e as cores das situações ficaram mais claras para aparecer por cima. Não baixa nada além do que o Mapa iluminado já usa.
- **Seleção (D-177):** com a obra inteira, mesmo aproximada, cada toque escolhe um trecho ou um nó e troca a seleção. Com uma zona escolhida (toque na zona), os toques somam ou tiram trechos e nós, sem Ctrl. Trocar de zona ou voltar à obra inteira (⌖) limpa a seleção.
- **Ponta de rua (D-178):** o nó em que só um trecho chega, em toda a rede vigente (`topologia.trechos_fisicos`), entra sozinho com o trecho, se for nó da 06.2 vigente. Ponta de rua sem peça na 06.2 não gera aviso. O nó que liga dois trechos escolhidos continua entrando; a ponta da seleção que continua noutro trecho não entra.
- **Equipe da zona (D-179):** a equipe já vem a da frente dos trechos escolhidos (Zona 08 → EQUIPE ZONA 08; o nome completo do trecho diz a frente). A escolha feita à mão vale enquanto a seleção continua na mesma frente; trocar de frente ou limpar a seleção volta para a equipe da zona.

Testes: `test_no_terminal_da_062_entra_sozinho_mas_juncao_nao` (`tests/test_fluxo_v22.py`) e `TestMapaNoNavegador`.

## Frentes, Subadutora e o desenho do HTML (29/10/2026, D-182 a D-184)

Substitui o satélite da D-176 no Dados da obra.
- **Subadutora (D-182):** a adutora mais as redes de 200 mm pra cima (DE 225 e 250) formam a frente **Subadutora**: 132 trechos, cerca de 10,5 km. Quem executa é a EQUIPE ADUTORA. Esses trechos saem das zonas: a Zona 05, por exemplo, fica com 79 trechos. O nó vai para a Subadutora quando liga um trecho dela; o que liga também um trecho da zona aparece nas duas frentes, e nele vem a equipe da frente em foco. A regra é a mesma no Mapa iluminado e no HTML do mapa base. No banco nada muda: o `frente_id` continua sendo a zona do local.
- **Frentes:** a barra acima do mapa traz Obra inteira, Zona 01 a 11 e Subadutora. Tocar numa zona do mapa também escolhe a frente. Com uma frente escolhida, só ela tem cor: fora dela não aparece trecho nem nó, e um véu branco cobre o resto. A busca, a equipe do dia e o lote voltam para a obra inteira quando o trecho está fora da frente.
- **Desenho (D-184):**
  - o fundo é a planta das PBs clara, cortada nos quadros; o satélite escuro saiu;
  - os trechos têm a cor do diâmetro da legenda do projeto (`coresTubos` do HTML, em `mapa_geral.geometria` como `cores_de`), a Subadutora mais grossa e o MND tracejado;
  - na legenda, **Cor dos trechos** troca para a cor da programação do dia, e a escolha fica guardada no navegador;
  - o trecho escolhido ganha contorno escuro com miolo branco.
- **Nós e caixas (D-183):**
  - o nó é bola; DF é triângulo invertido, VTF é triângulo, VM é quadrado, VRP é losango, MV é hexágono e HID é cruz;
  - no Dados da obra só aparecem os da frente em foco; a caixa aparece sempre, e o nó só de perto ou escolhido;
  - no Mapa iluminado, os trechos ficam como estavam e os nós e as caixas ganham a cor da situação (Camadas › Nós e caixas). O toque abre a ficha do nó.

Testes: `test_geometria_traz_o_que_as_frentes_e_as_cores_pedem`, `test_html_base_com_a_frente_subadutora`, `test_dados_da_obra_com_a_planta_clara_sem_satelite` e `test_frentes_do_mapa_com_a_subadutora` (`tests/test_telas.py`), e `TestMapaNoNavegador` (a equipe do trecho de DE 225 e do nó compartilhado).

**Ajuste de 29/10/2026 (depois da instalação):**
- Os trechos dos dois mapas ficaram finos como no HTML do projeto: 1 px na obra inteira, crescendo pouco com o zoom.
- O traçado aparece logo, sem esperar o estado do dia nem o estoque. No site, quando o servidor demorava, ficavam só as zonas e as caixas.
- A imagem da planta (`mapa_geral.mosaico`) abre uma PB por vez: o pico de memória caiu de 874 MB para 196 MB. O instalador monta essa imagem antes do Reload, para o site não montá-la no primeiro acesso.

## Foco por zona e seleção só na zona (29/10/2026, D-185 e D-186)

Substitui a seleção na obra inteira (D-177) e a planta clara (D-184).
- **Desenho:** o Dados da obra tem o fundo do Mapa iluminado: o satélite cortado nas zonas, escurecido pelo fundo escolhido lá. Os trechos ficam na cor do diâmetro, finos (0,75 px na obra inteira). O trecho escolhido ganha halo branco.
- **Foco por zona, nos dois mapas:**
  - só a zona escolhida tem cor, trechos, nós, caixas e equipes;
  - as outras ficam sem preenchimento, sem trechos e sem nome, e não respondem ao toque;
  - o contorno das zonas e o satélite continuam;
  - para sair, há "Obra inteira", a janela Zonas e, no Dados da obra, a barra de frentes.
- **Seleção:**
  - na obra inteira, o toque só abre a zona (o trecho tocado leva à frente dele);
  - na zona, cada toque escolhe um trecho ou nó, e tocar de novo não tira;
  - **Desselecionar** liga um modo em que cada toque tira só o que foi tocado; outro toque no botão volta a escolher;
  - **Limpar seleção** zera;
  - os dois botões aparecem na barra do mapa quando há uma zona em foco.
- A busca e "Ver a ficha completa" abrem a zona do trecho e o escolhem.

Testes: `test_dados_da_obra_com_o_fundo_do_iluminado_e_selecao_na_zona` e `test_mapa_do_dados_da_obra_tela_cheia_vista_e_zonas` (`tests/test_telas.py`), e `TestMapaNoNavegador` (`tests/test_fluxo_v22.py`).

## Revisão do código (30/10/2026, D-192)

- **Reserva** no Dados da obra só para dia futuro; para hoje, libere o material do dia.
- O dia da equipe aberto pelo Estoque (Liberar), pelo lote ou pela ficha abre já na zona da seleção; abrir a zona da
  própria seleção não a apaga, e a seleção de mais de uma zona pede confirmação antes de abrir uma zona.
- Programação com intervalo pede o início e o fim.
- Detalhes: `CORRECOES_REVISAO_30-10-2026.md`.
