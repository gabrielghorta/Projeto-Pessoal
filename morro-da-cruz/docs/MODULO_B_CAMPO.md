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

A tela **Lançamento do dia** (Execução, tela `campo`) tem duas abas: **Nota de serviço** (a NS do dia e o croqui,
`docs/NOTAS_DE_SERVICO.md`) e **Apropriação direta**, o lançamento sem nota de serviço direto no item do orçamento. Ex.: o
canteiro feito por uma equipe de outra obra da Ankara no período entre obras e os gastos do canteiro. A segunda aba só
aparece com a permissão `apropriacao` (Engenharia e Administração); para os outros perfis o servidor responde 403.

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
"Aprovado · base Caesb/SINAPI/SICRO", vermelha "A aprovar · código provisório" ou "A aprovar · item novo".

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
