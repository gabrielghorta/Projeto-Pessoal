# Módulo F — relatórios e operação

CT 10.239/2026 · 17/10/2026 · esquema v13 (sem mudança de esquema) · plano: `docs/PLANO_ENTREGA_COMPLETA.md` §F

## Relatórios (aba 7, `relatorios.py`)

Todos os relatórios são calculados a partir dos registros efetivos: sem movimentos estornados e sem intervalos anulados por retificação. O filtro é por período e frente. A exportação gera um .xlsx com as abas MATERIAIS, AVANÇO, PENDÊNCIAS e FALTANTES.

| Relatório | Colunas e regras | O que não é |
|---|---|---|
| **Ciclo do material** | Previsto (projeto) · solicitado (aprovado) · comprado (pedidos não cancelados) · a receber (pendente dos pedidos) · quarentena · recebido (aceito − devolvido ao fornecedor) · saldo do almoxarifado · reservado · com as equipes · aplicado · perda · medido.<br>Conferência: recebido = almoxarifado + equipes + aplicado + perda + emprestado. | **Medido** mostra "bloqueado (D-53 · D-54)": material não entra na medição enquanto o regime não for aprovado. Não é zero inventado. Pedido não é estoque; recebido não é faturável. |
| **Avanço** | Metros por frente × equipe × etapa (assentado, cadastro de campo, reaterrado) no período; assentado por dia; acumulado por frente (extensão, assentado, %, reaterrado, legado sem posição, nós concluídos). A soma por frente é igual à soma geral. | O avanço legado sem posição aparece à parte, sem data nem posição. Ele não entra no período. |
| **Pendências por frente** | Impedimentos e não conformidades abertos; intervalos sem verificação; reaterro sem cadastro de campo; legado sem posição; concluídos aguardando OK interno; concluídos sem as fotos obrigatórias; cadastro não enviado, a conferir ou negado; programação vencida sem encerramento. Gerais: reservas vencidas, notas a conferir, itens em quarentena. | — |
| **Faltantes** | A mesma regra da aba 1.1: previsto na programação − reservado para a equipe no dia − disponível; mostra também o a receber. | — |

Rotas:
- `GET /api/relatorios?ini=&fim=&frente=`: basta estar logado;
- `GET /api/relatorios/exportar?...`: a exportação fica registrada na auditoria.

## Celular (360 px)

Conferido no navegador em 360 × 740 (perfil de toque) em todas as abas:
- **antes:** 172 px de rolagem lateral em todas as abas (cabeçalho), formulários de campo além da tela, KPIs do mapa e a tabela de tetos da medição;
- **depois:** **0 px** em todas as 9 abas.

O que mudou:
- cabeçalho em duas linhas;
- abas roláveis;
- formulários em uma coluna;
- KPIs em duas colunas;
- tabelas largas com rolagem própria dentro do painel.

O acesso real pelo celular continua dependendo da hospedagem (D-60).

## Operação

- **Logs:** `dados/logs/servidor.log`, com rotação (5 × 2 MB). O módulo A já fazia o registro; aqui ele foi documentado.
- **Implantação, rotina de backup, restauração, nova revisão, atualização de versão e recuperação de desastre:** `docs/IMPLANTACAO.md`. O ensaio está no ciclo da Zona01.
- **Funcionamento sem internet:** não iniciado, por regra (D-61).

## Testes (`tests/test_relatorios.py`, 4)

- **Ciclo do material:**
  - pedido 100, entrega 60 (quarentena 60, a receber 40), aceite 50 e recusa 10, devolução 5;
  - reservas 8 (Zona01) e 3 (Zona02); retirada 20; aplicado 12, sobra 3, perda 1, fica 4;
  - resultado: recebido 45, saldo 28, reservado 3 (a da Zona01 foi consumida na retirada), com as equipes 4, aplicado 12, perda 1, a receber 55;
  - a igualdade de conferência fecha;
  - o estorno da devolução volta o recebido a 50;
  - medido = bloqueado, nunca 0.
- **Avanço:**
  - por frente e equipe; retificação conta 10, não 12 nem 22;
  - soma por frente = total; por dia;
  - acumulado e % da Zona01;
  - filtros de período, frente e equipe;
  - legado sem posição à parte.
- **Pendências:** impedimento, reaterro sem cadastro (2), concluído sem OK e sem fotos, não conformidade, programação vencida, filtro por frente.
- **HTTP:** sem login, 401; a equipe consulta; a exportação tem as 4 abas e fica registrada na auditoria.

## Navegador (banco v7 real migrado, usuários de demonstração)

- **Relatórios de 01 a 17/10:**
  - 45,22 m assentados, 23,22 m de cadastro de campo e 23,22 m reaterrados (Zona01, 2 trechos), com barras por dia;
  - acumulado da Zona01: 10.898,35 m de extensão, 0,41 % assentado e 25 m de legado sem posição;
  - pendências da Zona01: 6 intervalos sem verificação, 1 legado e 1 cadastro a conferir;
  - o filtro Zona02 zera o período;
  - exportação `RELATORIOS_2026-10-01_2026-10-17.xlsx`.
- **Celular:** 0 px de rolagem lateral nas 9 abas.
- Sem erros de JavaScript.

## Limitações

- Os relatórios são consultas ao vivo. Não há histórico de fotografias mensais além da medição congelada.
- O avanço não estima o legado sem posição por período.
- O "previsto" de material é a quantidade de projeto do cadastro (`qtd_projeto`). Material sem previsão aparece só se tiver movimento.
