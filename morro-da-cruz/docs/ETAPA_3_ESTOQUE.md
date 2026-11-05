# Etapa 3 — Estoque e custódia

CT 10239/2026 · 16/10/2026 · esquema v5 (revisto após a auditoria do commit `fae5818`)

A etapa 2 (regras financeiras) continua **parada**, à espera das 5 decisões da `MATRIZ_REGIMES_FATURAMENTO.md`. A etapa 3 não depende delas.

**Nada nesta etapa gera lançamento de medição ou faturamento:**
- a medição oficial continua bloqueada;
- NF aceita só cria estoque.

**Uso nesta versão:** piloto de teste. Importação e restauração exigem o servidor parado.

## O que mudou (diagnóstico C1–C7)

| # | Antes | Agora |
|---|---|---|
| C1 | O check-in era presença e saída numa coisa só; não havia programação. | **Reserva** por equipe e dia (`reservas`). A reserva não tira material do almoxarifado: só reduz o **disponível** para as outras equipes. O check-in consome a reserva da própria equipe; o restante precisa caber no disponível. |
| C2 | O check-out exigia fechar toda a custódia no mesmo dia. | **Saldo que fica com a equipe**, declarado no check-out (`custodia_declarada`). A custódia passa a ser da equipe e volta no próximo check-in como "trazido". Todo material com a equipe precisa ser declarado: aplicado + sobra devolvida + perda + fica com a equipe = custódia. |
| C3 | Empréstimo para outra obra livre, com documento opcional. | Exige **documento, responsável e autorização**, e só dentro do disponível. |
| C4 | `BAIXA_TEORICA` reduzia o saldo físico. | **Não é mais aceita.** Registros antigos ficam guardados, mas fora do saldo físico (coluna "baixa teórica legada"). Novo quadro **previsto (metros apontados) × aplicado confirmado** por tubo, só para conferência. |
| C6 | Só havia saldo. | **Saldo físico, reservado, disponível, quarentena e com as equipes.** |
| C7 | Sem estorno: correção só apagando. | **Estorno com motivo e responsável** (`estornos`). O movimento original fica e só sai dos saldos. É recusado se deixar saldo do almoxarifado ou custódia da equipe negativos. Entrada por NF não se estorna aqui; é tratada pela nota. |
| C5 | Pedido, compra e aceite parcial de NF | **Não feito nesta etapa** (ver pendências). |

## Correções da auditoria de 16/10 (commit `fae5818`)

| Achado | Antes (reprodução) | Agora | Teste |
|---|---|---|---|
| 1. Fechamento consumia retirada futura | Zona01 retirou 20 m em 15/10 e 5 m em 16/10, com os dois check-ins abertos. O check-out de 15/10 aceitou 25 m aplicados em 15/10. | **Uma sessão aberta por equipe.** Novo check-in é recusado enquanto houver outro aberto, em qualquer data. **Check-in retroativo** (data anterior a uma sessão já registrada da equipe) é recusado. **Custódia cronológica:** o fechamento e a tela do check-out só enxergam movimentos das sessões até aquela, em ordem (data, id). Em banco legado com duas sessões abertas, os fechamentos são exigidos em ordem e 15/10 só fecha os 20 m. | `TestSequenciaDosFechamentos` (3) |
| 2. Estorno deixava reserva sem cobertura | Entrada 100 m, reserva 80 m, estorno → físico 0, reserva ATIVA 80, disponível −80. | O estorno é **recusado** (transação desfeita, nada muda) e lista as reservas afetadas. Só passa com **ajuste explícito** (`ajustar_reservas`): reduz ou cancela as reservas mais recentes até o disponível voltar a zero, e cada ajuste fica em `reserva_ajustes` (de, para, motivo, responsável, movimento). Nunca sobra reserva ATIVA descoberta. | `TestEstornoComReservas` (2) |
| 3. Sem retificação após o check-out | Estornar o APLICADO de um check-out encerrado devolvia 20 m à custódia, mas o fechamento não podia ser corrigido sem nova visita. | **Retificação do fechamento** (`retificar_fechamento`, botão "Retificar fechamento"): estorna o aplicado/sobra/perda original (que fica no histórico) e redistribui a **mesma quantidade** em aplicado, sobra, perda e fica com a equipe, na **mesma data e sessão**. Registra motivo, responsável e o vínculo com o movimento e o fechamento originais (`retificacoes`, `movimentos.retificacao_id`). O check-in não é reaberto. O estorno simples desses movimentos passa a ser recusado e aponta para a retificação. A retificação também não deixa reserva descoberta. | `TestRetificacaoDoFechamento` (3) |

## Critérios de aceitação (diagnóstico §5.3), em `tests/test_estoque.py`

- Saída de 20 → aplica 16, devolve 3 e perde 1 (com motivo): almoxarifado 35 → 38, custódia 0, sem segunda baixa.
- 20 retirados, 12 aplicados, 8 ficam com a equipe: no dia seguinte, o check-in mostra 8 trazidos + 5 retirados.
- Duas equipes não consomem o mesmo saldo: com 30 em estoque e 25 reservados para a Zona01, a Zona02 só retira 5.
- Mais: empréstimo sem autorização recusado; baixa teórica recusada e legada fora do saldo; estorno com e sem saldo; reserva para objeto retirado recusada; migração v2 → v4 sem perda.

**Navegador:** reserva, retirada recusada além do disponível, check-out com saldo que fica, estorno e quadros conferidos sobre uma cópia da base real.

## Migração

`python importar.py --aplicar` (com o servidor parado) migra v1/v2/v3/v4 → v5:
- acrescenta `movimentos.responsavel` e `movimentos.autorizacao`;
- cria as tabelas `reservas`, `estornos`, `custodia_declarada`, `retificacoes` e `reserva_ajustes`, e a coluna `movimentos.retificacao_id`;
- não altera nenhum movimento existente.

O servidor recusa banco em esquema anterior até a migração.

## Pendências desta frente — atualizado em 17/10 (módulo C)

Pedido e compra, entregas e aceites parciais, devolução, XML da NF-e, transferência entre equipes, reservas vencidas e inventário foram implementados no módulo C (`docs/MODULO_C_COMPRAS.md`). A lista abaixo é o registro original de 16/10.

### Registro original

- **NF (C5):** pedido/compra, entrega e aceite parciais, devolução e leitura do XML da NF-e. Sem isso, o ciclo de compra do material Ankara não está completo.
- **Transferência entre equipes:** hoje só por sobra devolvida + nova retirada.
- **Reservas de dias passados:** ficam ATIVAS até cancelar ou atender. Avaliar expiração automática com aviso.
- **Previsto × confirmado:** só para os tubos PEAD da Caesb (metros). Para conexões, depende da regra de apontamento por item.
