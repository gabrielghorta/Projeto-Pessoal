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
