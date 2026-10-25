# Módulo B — campo, qualidade e cadastro (complementos)

CT 10.239/2026 · 17/10/2026 · esquema v10 · plano: `docs/PLANO_ENTREGA_COMPLETA.md` §B

O que já existia e foi conferido: intervalos por etapa com cronologia e sem duplicidade, retificação sem apagar, soldas (previstas × informadas × verificadas), foto original validada, cadastro em quatro fases, conferência interna e pendências consolidadas. Detalhes em `docs/ETAPA_4_CAMPO.md`. Este módulo acrescenta o que faltava.

## Finalidade operacional dos registros novos

| Novo | Para que serve | O que não é |
|---|---|---|
| **Liberação topográfica** (por intervalo do trecho, com referência da nota de serviço ou locação, quem registrou e data) | Saber onde a vala pode abrir e conferir se o assentamento foi feito em trecho locado. | Não gera quantidade nem altera o resumo de execução. Ainda não bloqueia o assentamento (D-20). |
| **Escavado** (vala aberta, por intervalo) | Acompanhar a vala aberta e a etapa entre locação e assentamento. | Informativo: não é pré-requisito (D-21). MND não tem. |
| **Ocorrência — impedimento** (interferência, falta de material, chuva, liberação, projeto, segurança, acesso, outro) | Registrar o que impede o avanço, com data, equipe e quem abriu, e como foi resolvido. | Não bloqueia lançamentos. |
| **Ocorrência — não conformidade** (execução, material, solda, segurança, cadastro, documento, outro) | Registrar o que precisa ser corrigido e a correção feita. | Não bloqueia o OK interno (decisão pendente, D-22). |

Nada disso é aprovação da Caesb. Anulações e resoluções guardam motivo, quem fez e quando, e nada é apagado.

## Regras

- **Liberação:** exige referência. Sobreposição na mesma etapa e intervalo fora do trecho são recusados. Correção é pela **anulação** (motivo obrigatório) mais um novo registro.
- **Assentado ou escavado sem liberação até a data do serviço** gera **alerta**. Uma liberação posterior não vale como anterior: é a mesma regra de cronologia da F03.
- **Ocorrência:**
  - abre com tipo, categoria válida para o tipo, descrição e data;
  - resolver exige a descrição da resolução ou correção;
  - ocorrência resolvida não reabre (abre-se outra);
  - as abertas aparecem como alerta nas pendências do detalhe.
- **Permissões** (matriz provisória, D-10):
  - liberação: topografia ou engenharia;
  - escavação e abertura de ocorrência: perfil de campo;
  - anulação: `retificar_campo` (engenharia);
  - resolução: `verificar` (engenharia).
- **Autor:** sempre o usuário da sessão.
- **Histórico:** liberação, escavação e ocorrências entram na definição única de histórico. Um trecho com esses registros não some numa revisão sem de-para.

## Testes (`tests/test_campo_b.py`, 4)

- Registro e recusas (sobreposição, sem referência, fora do trecho, escavação em MND), sem efeito na execução.
- Assentado em 15/10 com liberação de 16/10: alerta. Depois da anulação (com motivo) e da liberação correta de 14/10: sem alerta, com o anulado preservado.
- Impedimento e não conformidade abertos, recusas, resolução, histórico preservado.
- **Pelo HTTP:**
  - a equipe não registra liberação (403);
  - abre ocorrência, e o autor fica sendo o usuário da sessão, não o nome digitado;
  - a equipe não resolve (403);
  - a engenharia registra e resolve;
  - a auditoria guarda o objeto pela identidade estável (TR-00001).

## Navegador (banco v7 real migrado para v10)

- topo.fabio: liberação sem referência foi recusada; com referência, registrada. Como a liberação é de 17/10, o assentamento de 15 e 16/10 continua com alerta (cronologia).
- enc.davi: abriu um impedimento por interferência e não vê o botão "Resolver".
- eng.ana: resolveu. O detalhe do trecho mostra a liberação, a ocorrência resolvida e o alerta de topografia.
- Sem erros de JavaScript.

## Decisões

- D-20: liberação obrigatória antes do assentamento?
- D-21: quais etapas são obrigatórias e em que ordem?
- **D-22 (nova):** não conformidade aberta deve impedir o OK interno?

## Data futura (etapa Z)

Execução, clima, soldas, liberação e escavação, ocorrência, movimentos de estoque, OK interno e recomposição registram o que já aconteceu. Data posterior a hoje é recusada com a mensagem "… com data futura (…): só se registra o que já aconteceu.", e nada é gravado.

Valem para (servicos e compras):
- check-in e entrada de material;
- recebimento, inspeção, devolução ao fornecedor e transferência.

Programação, reserva e período de medição continuam podendo ser futuros. Teste: `tests/test_campo_b.py::TestDataFutura`. A falta dessa recusa apareceu no ciclo da Zona01.

## Apropriação direta (esquema v19, 22/10/2026)

Decisões D-90 a D-97 (`docs/DECISOES_PENDENTES.md`, seção 8). Código: `apropriacao.py`, `web/apropriacao.js`.

A **Apropriação direta** é uma página da tela **Lançamento do dia** (Execução, tela `campo`; ver "Execução
reorganizada" no fim): o lançamento sem nota de serviço direto no item do orçamento. Ex.: o canteiro feito por uma
equipe de outra obra da Ankara no período entre obras e os gastos do canteiro. A página só aparece com a permissão
`apropriacao` (Engenharia e Administração); para os outros perfis o servidor responde 403.

**Escolha do item, como no BM Vertical:** grupo (Canteiro, Redes, Caixas, Interligação, Ligações, Hidromecânico,
Administração local) → material ou serviço (os dois dão o subgrupo) → item. A **busca única** no topo acha o item por
qualquer identificador:
- item do BM Vertical (`5.1_1.14.27`) e do BM (`1.14.27`), o código Caesb inteiro ou um pedaço;
- descrição oficial e resumida, grupo e grupo de orçamento Ankara;
- material, diâmetro, pressão, resina, tipo de conexão, solda e unidade.

Sem acento e sem diferença de maiúscula, palavras em qualquer ordem e cada uma podendo ser pedaço ("tê 63 pe100" acha o
TÊ 90° eletrofusão DE 63 PE100). Sinônimos: TE/TÊ, PEAD/POLIETILENO DE ALTA DENSIDADE, Ø/DE/DN/"63MM" para o diâmetro,
PVC/POLICLORETO DE VINILA e FOFO/FERRO FUNDIDO. Primeiro o casamento exato de item ou código, depois quem casa mais palavras
inteiras; o diâmetro exato do item vale mais que um pedaço ("63" não empata com "110X63"). A busca também acha os itens
novos. Escolher pela busca preenche o grupo e o tipo sozinho. Cada resultado mostra a situação em etiqueta: verde
"Aprovado · base Caesb" (com a composição de referência quando o código tem SI ou SC, como "Aprovado · base Caesb
(SINAPI 98459)" no tapume 8000508010SI98459, que é código oficial da base de custos da Caesb), vermelha "A aprovar ·
código provisório" ou "A aprovar · item novo". Achado o item, o formulário Apropriação vem logo abaixo (botão "Apropriar
este item"); o cadastro de item novo é só para o que não está no orçamento.

**Cartão do item:** situação, origem do código, preço unitário sem BDI, contratado, já medido e apropriado, saldo, e o
aviso quando a quantidade passa do saldo (o excedente fica parado até aditivo ou apostilamento), quando o item é a
aprovar ou quando é material (D-53/D-54).

**Campos da apropriação:** data (não futura), quantidade na unidade do item, local opcional (canteiro, zona, ou trecho ou
nó pela busca de trecho), quem executou (equipe da obra; equipe de outra obra ou contrato da Ankara, com a obra e a
equipe; terceiro, com o nome), o que foi feito, memória de cálculo, justificativa técnica e **pelo menos uma evidência**
(foto, croqui ou documento: PDF, JPG ou PNG, até 10). As evidências alimentam o memorial da medição e vão para o Drive em
`03_EXECUCAO_DE_CAMPO/03_Apropriacao_Direta/<AAAA-MM>`. O responsável é o usuário da sessão; o base64 não vai para a
auditoria.

**Correção só por estorno com motivo:** a apropriação fica riscada (nada é apagado); a proposta dela numa medição aberta
volta a PENDENTE; já medida numa medição fechada, o estorno é recusado (D-16).

**"O item não está na lista":** cadastro rápido do item novo (grupo, material ou serviço, descrição, unidade, os
identificadores da busca, preço proposto e a fonte, que pode ser cotação, NF ou SINAPI/SICRO com o código, e a
justificativa). Antes de gravar, o sistema avisa se a descrição e os identificadores batem com um item que já existe
("parece o item 5.1_1.14.27: é esse?"). O item entra como a aprovar e já pode receber apropriação.

**Diário de obra:** as apropriações do dia aparecem numa seção própria.

| Rota | Permissão ou tela |
|---|---|
| `GET /api/base-custo/busca?q=&grupo=&tipo=` | telas `campo`, `medicao`, `lev` |
| `GET /api/base-custo/itens?grupo=&tipo=` (ou `?ref=` para um item com o saldo) | as mesmas |
| `POST /api/apropriacao` (com `evidencias: [{nome, conteudo_b64}]`) | `apropriacao` |
| `POST /api/apropriacao/estornar` `{apropriacao_id, motivo}` | `apropriacao` |
| `GET /api/apropriacoes?ini=&fim=&equipe=` | telas `campo`, `diario`, `medicao` |
| `POST /api/base-custo/item-novo` (com `confirmar` para gravar apesar do parecido) | `apropriacao` |
| `GET /api/apropriacao/arquivo?doc=` (evidência ou documento da Caesb, inline) | telas `campo`, `diario`, `medicao` |

Testes: `tests/test_apropriacao.py` (`TestBusca`, `TestApropriacaoHttp`).

## Fluxo integrado (esquema v20, 23/10/2026): o caminho até a medição e a ordem obrigatória

**Caminho até a medição** (ficha do trecho, bloco "Para entrar na medição", `servicos.caminho_medicao`), cada item com quem faz e onde:
1. liberação topográfica (Topografia, NS de topografia, em Topografia › Enviar NS de topografia);
2. executado 100 %, assentado e reaterrado (a equipe, pela NS do dia em Notas de serviço › NS do dia);
3. verificado pelo supervisor (botão "Verificar" na ficha; quem informou não verifica; `servicos.verificar_trecho`);
4. as 3 fotos (sinalização, execução, concluído), enviadas por quem manda a NS do dia ou pelo supervisor, no mesmo lugar da verificação;
5. cadastro de campo (Cadastro, pela NS de cadastro, em Cadastro de campo › Enviar NS de cadastro);
6. OK interno (Engenharia ou Administração, botão "OK interno" na ficha).

O OK interno exige 2, 3 e 4 (D-112), e não depende mais de medição aberta (D-113). O supervisor tem a lista "Aguardando verificação" no Mapa iluminado, por zona, com o mais perto primeiro quando o celular dá a posição.

**Ordem obrigatória** (D-20 DECIDIDA, D-115): assentamento e escavação só sobre a liberação topográfica até a data, venham do apontamento, da NS do dia ou da retificação. A mensagem diz o que falta, por exemplo "Zona 03 · PB06 · TR014, de 12,0 m a 30,0 m: falta a liberação topográfica (registre a NS de topografia antes)". A liberação que a execução já usou não é anulada. O legado conciliado só ganha posição; o legado fora de ordem fica listado em Notas de serviço › "Fora de ordem (legado)" (`servicos.fora_de_ordem`), sem apagar nada. A apropriação direta fica fora da regra.

**O que acende no mapa** (`regras.etapa_trecho`, D-118): não iniciado → liberado → em execução hoje → executado, aguardando verificação (parcial ou não) → verificado → cadastro de campo feito → pronto para o OK → OK interno, na medição → cadastro em andamento → cadastro aprovado pela Caesb. Testes: `tests/test_etapas_mapa.py`, `tests/test_ordem_obra.py` e o ponta a ponta `tests/test_fluxo_integrado.py`.

## Execução reorganizada (23/10/2026): o Lançamento do dia é o lançamento solto

Decisões D-121 a D-130 (`docs/DECISOES_PENDENTES.md`, seção 11). As regras não mudaram; só onde cada coisa fica.

**Menu Execução, nesta ordem:** Lançamento do dia, Notas de serviço, Topografia, Cadastro de campo, Interferências e
ocorrências, Diário de obra.

**Lançamento do dia** ("Lançamentos sem nota de serviço. A NS do dia é enviada em Execução › Notas de serviço."). Quatro
páginas; cada perfil vê só as que pode usar:

| Página | O que tem | Quem vê |
|---|---|---|
| Apropriação direta | o lançamento direto no item do orçamento (acima) | Engenharia e Administração (`apropriacao`) |
| Apontamento sem NS | o antigo "Sem nota de serviço (exceção)": trecho, nó ou caixa, metros, motivo obrigatório | Engenharia e Administração (`lancar_sem_ns`) |
| Fotos e soldas | o trecho ou nó pela busca com o nome completo ("Zona 03 · PB06 · TR014") ou pelo Mapa iluminado ("Lançar avanço" na ficha); as 3 fotos obrigatórias e as soldas | quem tem `campo` (encarregado, supervisor, almoxarifado, Engenharia, Administração) |
| Clima do dia | a equipe e os dois toques (manhã e tarde), gravados na tabela `clima`, onde a NS do dia grava. A NS do dia é a fonte principal (D-131): o clima tocado no envio dela substitui o daqui; sem toque, vale o daqui. Depois que a NS do dia chega, o Clima do dia só preenche o turno vazio, e mudar é correção da engenharia | quem tem `campo`; o encarregado, só a equipe dele |

**Saiu daqui:** a NS do dia (o formulário, "Notas do dia enviadas" e "Notas de serviço da zona"), que foi para
**Notas de serviço › NS do dia** (`docs/NOTAS_DE_SERVICO.md`, seção 6).

**Páginas dentro da aba** (um componente só em `web/app.js`: `PAGINAS`, `paginaDe`, `mostrarPagina`):
- chips no topo, de 44 px, quebrando a linha no celular;
- a página fica no endereço (`#campo/fotos`, `#topografia/resumo`, `#cadastro_campo/feito`…) e funciona com voltar e
  avançar do navegador;
- cada aba lembra a última página na sessão (`sessionStorage`, chave `mc-pagina-<tela>`);
- link antigo sem página, ou com uma página que o perfil não usa, abre na primeira que ele usa.
