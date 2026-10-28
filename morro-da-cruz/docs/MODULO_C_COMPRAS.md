# Módulo C — compras, recebimento e almoxarifado

CT 10.239/2026 · 17/10/2026 · esquema v11 · plano: `docs/PLANO_ENTREGA_COMPLETA.md` §C

Completa as pendências da etapa 3 (`docs/ETAPA_3_ESTOQUE.md`):
- pedido e compra;
- entrega e aceite parciais;
- devolução;
- XML da NF-e;
- transferência entre equipes;
- reservas vencidas;
- inventário.

O estoque por especificação e unidade, a reserva, a retirada, a custódia, o estorno e a retificação de fechamento continuam como estavam.

## Fluxo e finalidade operacional

| Etapa | Para que serve | Regra |
|---|---|---|
| Fornecedor | Saber de quem o material veio | CNPJ válido (dígitos verificadores) e único. |
| Solicitação | Registrar a necessidade (material, quantidade, destino) | **Quem solicita não aprova.** Material fornecido pela Caesb não é comprado (sai por romaneio). |
| Pedido | Formalizar a compra com o fornecedor | Só a partir de solicitação **aprovada**, sem pedir mais do que o aprovado. **Pedido não altera nenhum saldo.** |
| Nota fiscal: XML | Evitar digitação | Leitura com biblioteca padrão: DOCTYPE/ENTITY recusados, modelo 55, chave com dígito verificador, itens e totais conferidos, nota repetida recusada, emitente precisa estar cadastrado. Fica **A CONFERIR**, sem movimento. |
| Nota fiscal: digitada do PDF/imagem | Notas sem XML | Anexo obrigatório (PDF ou imagem válida). Fica **A CONFERIR** e **quem digitou não confere**. |
| Conferência | De-para de cada linha da nota para um material do estoque | Cada linha vai para um material, com o item do pedido, ou fica "fora do estoque" (frete, serviço). **Unidade diferente exige fator de conversão declarado** (ex.: 10 CX × 10 = 100 UN); mesma unidade usa fator 1. Não fatura além do saldo do pedido. Só depois disso a nota aceita entregas. |
| Entrega | Registrar o que chegou, quando e com qual canhoto | Parcial ou total, nunca além do saldo da nota. Entra em **QUARENTENA** (não é estoque). |
| Inspeção | Aceitar ou recusar item a item | Aceito + recusado = entregue. Exige referência do laudo (com anexo opcional) e motivo da recusa. **O aceito vira estoque, nunca lançamento de medição**; o recusado volta na entrega e pode vir em outra nota. |
| Devolução ao fornecedor | Material já aceito e depois rejeitado | Até o aceito ainda não devolvido, e só do disponível (não tira material reservado nem com as equipes). |
| Transferência entre equipes | A equipe A passa material para a B em campo | Exige as sessões abertas das duas, quantidade até a custódia da origem e quem autorizou. Não passa pelo almoxarifado. Os dois check-outs fecham com o novo saldo. |
| Inventário | Corrigir diferença física | Contagem guarda o saldo do sistema no momento. **Quem contou não aprova.** O ajuste é recusado se o saldo mudou desde a contagem (recontar) ou se deixaria reservas sem cobertura. |
| Reservas vencidas | Não prender saldo com reserva de dia passado | Lista das ATIVAS de dias anteriores e liberação em lote, com motivo. |

**Pendente de entrega do pedido** = pedido − (aceito − devolvido) − em quarentena.

**Saldo do pedido a faturar** = pedido − notas conferidas + recusado + devolvido.

**Documentos** (XML, PDF ou imagem da nota, laudo) ficam byte a byte em `<pasta do banco>/documentos`, nomeados pelo SHA-256. Entram no **backup** e na **restauração** com a mesma conferência de hash das fotos.

## Migração v10 → v11

`notas_fiscais` e `movimentos` são recriadas para aceitar os estados e tipos novos, com todas as linhas copiadas, mesmos ids e contagem conferida. As notas anteriores ficam com origem DIRETA e continuam com o aceite antigo.

**Defeito achado e corrigido nesta etapa.** Renomear uma tabela-pai com chaves estrangeiras ativas fazia as tabelas-filhas apontarem para a tabela antiga. A checagem adiada também falhava. Agora:
- a recriação cria a tabela nova com outro nome, copia e descarta a antiga, sem renomear a pai;
- as chaves ficam desligadas durante a migração de esquema, como no procedimento do SQLite;
- `foreign_key_check` antes do COMMIT reprova a importação inteira se houver violação.

O formulário antigo de "NF direta" saiu da tela e da API: ele criava movimento sem conferência.

## Testes (`tests/test_compras.py`, 11)

- **XML:** leitura válida; DOCTYPE, chave inválida, modelo 65, XML malformado, não NF-e e item com valor incoerente são recusados.
- **Pedido:** não vira estoque; a própria solicitação não é aprovada; sem solicitação aprovada não há pedido; excesso e material Caesb são recusados.
- **Ciclo da nota:** NF de 10 CX → conferência com fator 10 (100 UN) → entrega 60 → inspeção 50/10 → reserva impede a devolução → devolução de 5 → entrega 40 → inspeção → nota ENCERRADA, saldo 85, nenhum lançamento de medição.
  - No meio do caminho, o pedido mostra 100/60/0/50/10, pendente 50 e a faturar 10.
- **NF digitada:** anexo obrigatório; imagem falsa recusada; quem digitou não confere.
- **Backup:** inclui o documento; documento apagado deixa o backup INCOMPLETO; a restauração devolve o arquivo com o hash certo.
- **Transferência:** sem sessão, acima da custódia e sem autorização são recusadas; custódias 12/8; check-outs fecham.
- **Inventário:** quem contou não aprova; ajuste −2; saldo mudado depois da contagem pede recontagem.
- **Reservas vencidas:** só as de dias anteriores são liberadas.
- **Pelo HTTP:** permissões por perfil (solicitar, aprovar, pedir, receber, conferir), aprovação da própria recusada, entrega reenviada 3 vezes com a mesma chave grava 1, autor da sessão.
- **Migração v10 → v11:** movimentos e estorno com os mesmos ids, nota DIRETA, aceite antigo funcionando, índice recriado.
- **Migração com chave estrangeira quebrada:** reprova e o banco fica byte a byte igual.

## Navegador (banco v7 real migrado para v11, usuários de demonstração)

1. eng.ana solicita 100 e não vê "Aprovar" na própria solicitação. eng.bruno aprova.
2. adm.eva: CNPJ com dígito errado é recusado; o correto é cadastrado; emite o pedido PC-2026-001.
3. almox.carla importa o XML (10 CX de luva e frete). Sem fator, a conferência é recusada; com fator 10, a nota fica conferida.
4. Entrega de 60. Inspeção 50/10 sem motivo é recusada; com motivo, é registrada.
5. Devolução de 5.
   - Pedido: 100 pedido, 100 faturado, 60 entregue, 0 em quarentena, 50 aceito, 10 recusado, 5 devolvido, 55 pendente.
   - Estoque: saldo 45. Nenhum lançamento de medição.
6. Inventário: contagem 44. almox.carla não aprova a própria contagem; eng.ana aprova e o saldo vai a 44.

Sem erros de JavaScript.

## Limitações e decisões

- **NF-e:** a assinatura digital e a situação na SEFAZ não são verificadas, só lidas quando o protocolo vem no XML. Por isso há conferência humana antes de qualquer movimento.
- **PDF ou imagem da nota:** não há extração automática; os dados são digitados e conferidos por outra pessoa.
- **Decisões:**
  - D-40: quem aprova e emite a compra;
  - D-41: quem inspeciona e quais documentos;
  - D-42: quem aprova o ajuste de inventário;
  - D-43: expiração automática de reservas;
  - D-44 (nova): pedido sem solicitação aprovada em caso de emergência.
- Pedido e nota com faturamento por etapas só **registram a intenção**: o regime continua bloqueado (D-53, D-54).

## A NF no almoxarifado, sem pedido, e a NF da Caesb (esquema v20, 23/10/2026)

Tela Estoque e movimentos › **Notas a receber** (o almoxarife):
1. **Importar XML**, vários de uma vez (também em Compras e notas). Emitente sem cadastro: o sistema pergunta e cadastra pelo CNPJ e pela razão social do próprio XML.
2. **Conferir as linhas:** cada linha vem com o material sugerido (`compras.sugerir_materiais`: código do produto = id do material; o de-para anterior do mesmo fornecedor; a descrição com os mesmos números e 60 % das palavras). O pedido é opcional.
3. **Registrar o que chegou:** entra em quarentena (a linha de tubo da Caesb vira romaneio, sem quarentena).
4. **Aceitar tudo desta entrega** ou registrar a inspeção com aceito e recusado. Um laudo por entrega, obrigatório só quando há recusa.
5. **Nota sem pedido:** o aceito fica no almoxarifado, na coluna "Aguardando aprovação da nota", até a aprovação de Engenharia ou Administração (outra pessoa, não quem importou). Depois, libera no Dados da obra.

Decisões D-105, D-110 e D-111. Testes: `TestNotaNoAlmoxarifado` em `tests/test_compras.py` (as NF-e de teste 18734, sem pedido, e 4521, remessa da Caesb) e `TestNotaFiscalPeloHTTP` em `tests/test_fluxo_integrado.py`.

### Recebimento num toque (26/10/2026, D-135)

Na maioria das vezes a nota chega certa. Cada nota em "Notas a receber" mostra as linhas (com o material sugerido) e dois botões:
- **Recebido conforme a nota:** confere pelo material sugerido, registra a entrega do que falta chegar e aceita tudo na inspeção, de uma vez (`compras.receber_nota`, rota `/api/nf/receber`, permissão `receber`). Linha de frete, serviço, taxa ou seguro (unidade SV ou a descrição começando assim) fica fora do estoque sozinha. Linha de material sem sugestão trava o botão: escolha o material em "Conferir linha a linha".
- **Registrar problema:** em cada linha, o que chegou e o que veio avariado, na unidade da nota, e o que aconteceu (obrigatório). O que não chegou continua a receber na nota (o mesmo botão recebe o resto depois); o avariado é recusado, com o texto como motivo e laudo; o texto também fica na entrega ("obs.: …"). Tubo da Caesb avariado não entra no romaneio.

A nota sem pedido continua esperando a aprovação de outra pessoa. O passo a passo antigo (conferir, o que chegou, inspeção) continua em "Conferir linha a linha". Testes: `TestRecebimentoNumToque` em `tests/test_compras.py`.

### Aceite ou recusa na lateral (27/10/2026, D-169 e D-170)

A nota sobe só em **Compras e notas** (XML ou digitada); a tela Estoque e movimentos não importa mais. Em "Notas a receber", os dois botões acima deram lugar a três, na lateral de cada nota (no celular, embaixo):
- **Aceitar a entrega** (verde): o mesmo "Recebido conforme a nota".
- **Recusar a entrega:** abre o campo do porquê (obrigatório). Tudo o que falta chegar é entregue e recusado: nada entra no estoque, a nota é encerrada e a recusa fica como motivo e laudo da inspeção e na entrega ("recusa: …"). Rota `/api/nf/receber` com `recusa`.
- **Aceite ou recusa parcial:** em cada linha, o aceito e o recusado (na unidade da nota) e o porquê (obrigatório). O que não for nem aceito nem recusado não chegou e continua a receber; o mesmo botão verde recebe o resto depois. Rota `/api/nf/receber` com `problema.linhas[linha] = {aceito, recusado}`.

O tubo da Caesb recusado conta como entregue, não entra no romaneio e fica registrado como recusado; ele não volta ao fornecedor pela devolução (não é compra). A conferência em que nenhuma linha vai para o estoque é recusada, a menos que se confirme que a nota é só de frete ou serviço (aí ela é encerrada). A nota que ficou "a receber" sem nada a receber (conferida sem material antes disso) mostra **Refazer a conferência** (`/api/nf/refazer-conferencia`). Testes: `TestRecebimentoNaLateral` em `tests/test_compras.py`.

### Conferir é marcar (27/10/2026, D-171)

O almoxarife não escolhe material nem pedido. Em **Estoque › Notas a receber**, cada linha da nota mostra o material que o sistema reconheceu (`compras.sugerir_materiais`), com uma caixinha: ele marca a linha que conferiu no caminhão, ou toca em **Marcar todas**, e o verde **Aceitar a entrega** só libera com todas marcadas. Frete e serviço aparecem sem caixinha (não entram no estoque). Recusar e o aceite parcial continuam como antes.

O sistema reconhece, nesta ordem: a linha já confirmada em Compras; o código do produto igual ao id do material; a mesma linha numa nota anterior do fornecedor (com o fator de antes); o tubo de PEAD da Caesb pela bitola (`CAESB-PEAD-DE<n>`, quando a linha ou o emitente diz Caesb); a descrição (as mesmas medidas e a maior parte das palavras; o número de PE 100 e de SDR 17 não conta como medida).

A linha que ele não reconhece, ou cuja unidade é diferente da do material sem fator conhecido, fica **faltando a confirmação** em **Compras e notas** (a mesma aba onde a nota sobe). Quem tem a permissão de receber (na prática, a engenharia) marca um dos materiais mais parecidos, outro material ou frete/serviço, e diz quantos vêm em cada unidade da nota quando a unidade é outra (`compras.confirmar_linhas`, rota `/api/nf/confirmar-linhas`). Uma linha reconhecida errada também é corrigida ali (**Corrigir**). A próxima nota do fornecedor com a mesma linha já vem reconhecida. Enquanto falta confirmar, a entrega pode ser recusada (a linha desconhecida é recusada junto; se nenhuma linha foi reconhecida, a nota é cancelada com a recusa como motivo), mas não aceita.

O pedido é achado sozinho (`compras._pedido_automatico`): o único pedido emitido do fornecedor com todos os materiais comprados da nota. Nenhum, mais de um, ou um que não comporta a nota: ela entra sem pedido e espera a aprovação de Engenharia/Administração. A nota só de frete ou serviço é encerrada pelo verde. Testes: `TestConferenciaPorMarcacao` em `tests/test_compras.py`.

### Pedir material e entrega antes da identificação (28/10/2026, esquema v22, D-172 a D-175)

Substitui o que vem acima sobre pedido de compra, nota "sem pedido" com aprovação e "até lá, a entrega pode ser recusada, mas não aceita". Instalação e o que muda para cada pessoa: `docs/ATUALIZACAO_V22.md`.

**Saiu o pedido de compra (D-172).** A nota fiscal já diz o que foi comprado. Saíram da tela e das rotas: o pedido, a lista de pedidos, a solicitação de compra antiga de Compras, a aprovação da nota sem pedido (`/api/nf/aprovar`) e o pedido achado sozinho (`_pedido_automatico`). As tabelas `pedidos_compra` e `pedido_itens` e o que já estava nelas continuam no banco. O fornecedor é cadastrado junto da nota (permissão nova `fornecedores`).

**Pedir material (D-173)** é uma tela própria (`solicitar`), de quem tem `compras_solicitar`: almoxarifado, supervisor, encarregado (só para a frente da equipe dele), engenharia e administração. Quem é de campo não vê nota fiscal.
- O material é escolhido por toques: o **tipo** (Tubo, Luva, Tê, Curva, Redução, Flange, Toco, Válvula, Tampa, Ligação de água, Obra), o **tamanho** e o material, com um nome curto e sem código ("Redução PEAD 110×63 mm", "Tê de sela eletrofusão 110×63 mm", "Parafuso sextavado 20 mm · 90 mm de comprimento"). Há também a busca por palavras.
- O nome sai da descrição do material (`solicitacoes.catalogo`). Quando dois materiais ficariam com o mesmo nome, entra o primeiro detalhe que os separa (alma, comprimento, pressão). Serviço e administração local (taxa, locação, bombeamento) não aparecem. `config/materiais_pedido.json` corrige o nome, o tipo ou o tamanho de um material, pelo id.
- **Não achei:** escrever o que é ou tirar uma foto, com a unidade. A foto fica nos documentos (`NF_IMAGEM`) e só a vê quem pediu e quem aprova.
- A quantidade é acertada no − e no +; o destino é um toque na zona ou frente (a tabela `equipes`); a observação é opcional.
- **Aprovar ou recusar** é de quem tem `compras_aprovar` (engenharia e administração), num toque; a recusa pede o motivo. Quem pediu não aprova o próprio pedido. O item escrito ou fotografado precisa do material escolhido antes da aprovação, com a quantidade na unidade do material.
- **Meus pedidos** mostra cada pedido com cor e texto: aguardando, aprovado, recusado (com o motivo) e chegou.
- Ligar a nota a uma solicitação aprovada é opcional (`/api/solicitacao/vincular`, permissão `nf_confirmar`). Só marca "Chegou" quando o aceito das notas ligadas cobre o que foi pedido. A solicitação nunca trava nota, entrega nem estoque.

**Entrega antes da identificação (D-174).** Em **Estoque › Notas a receber**, o almoxarife marca todas as linhas, inclusive a que o sistema não reconheceu (ele confere pela descrição), e aceita a entrega.
- A linha reconhecida entra no estoque na hora, como antes.
- A linha não reconhecida fica registrada em `nf_entregas_linhas`, na unidade da nota, sem saldo. Ela vai para **faltando a confirmação** em Compras e notas (`nf_confirmacoes`).
- Quando a engenharia diz o material e o fator (`nf_confirmar`, `/api/nf/confirmar-linhas`), a entrega já registrada vira estoque uma vez só, com a data e o recebedor da entrega (`recebimento.materializar`). Se a linha for frete ou serviço, a pendência fecha sem movimento.
- **Corrigir** (quem tem `receber`) devolve uma linha reconhecida errada para "faltando a confirmação", desde que ela ainda não tenha entrado no estoque.
- A recusa e o aceite parcial continuam. A nota inteira recusada é encerrada com a recusa registrada, mesmo quando nenhuma linha foi reconhecida (antes ela era cancelada).
- A quarentena das entregas anteriores à v22 continua até a inspeção.

**Sem aprovação da nota (D-175).** O saldo deixou de esperar a aprovação da nota sem pedido. Na migração para a v22 (`importacao.preparar_v22`), o aceito dessas notas é guardado em `nf_liberadas_v22` (nota, material, quantidade) e vai no relatório da importação (`notas_liberadas_v22`). Nenhum movimento nem aprovador é inventado.

**Relatório de materiais e faltantes:** "comprado" vem das linhas das notas (sem o tubo da Caesb); "a receber" é o que está numa nota aberta e ainda não chegou (`planejamento.a_receber_por_material`, com o reconhecimento só nas notas que têm linha sem material).

Testes: `tests/test_fluxo_v22.py` (`TestEntregaAntesDaIdentificacao`, `TestSolicitacoesHTTP`, `TestCatalogoDoPedido`) e `tests/test_compras.py`.
