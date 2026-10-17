# Módulo D — planejamento e mapa

CT 10.239/2026 · 17/10/2026 · esquema v12 · plano: `docs/PLANO_ENTREGA_COMPLETA.md` §D

## Finalidade operacional

| Novo | Para que serve | O que não é |
|---|---|---|
| **Programação** (data, equipe, trecho ou nó, serviço, intervalo previsto, materiais previstos) | Planejar a semana das equipes e cobrar o realizado. | Não é presença nem execução. O check-in da equipe naquele dia e alvo a marca como **REALIZADA**. O que não aconteceu é encerrado como **NÃO REALIZADA** ou **CANCELADA**, com motivo. |
| **Programado × realizado** | Medir a aderência ao planejamento. | — |
| **Faltantes** | Antecipar falta de material para a programação. | Mostra previsto, reservado para a equipe naquele dia, disponível, a receber dos pedidos e faltante = previsto − reservado − disponível. |
| **Filtro por frente** (11 zonas, Adutora, CH) | Ver os números de uma frente. | — |
| **Camadas do mapa** | Andamento, Planejado (7 dias), Material, Informado × verificado, Cadastro e Pendências, todas calculadas no servidor **só a partir dos registros efetivos**. | "Verificado" e "conforme" são conferência interna Ankara (azul). O verde fica para o OK interno (já identificado como "não é aprovação Caesb") e para a decisão da Caesb registrada pelo memorando ESET. |

## Camadas (seletor dentro do mapa, com legenda própria)

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
