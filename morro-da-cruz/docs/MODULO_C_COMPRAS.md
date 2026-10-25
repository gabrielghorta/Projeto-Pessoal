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
