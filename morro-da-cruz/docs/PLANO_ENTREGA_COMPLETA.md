# Plano de entrega completa — webapp de gestão da obra Morro da Cruz

CT 10.239/2026 Caesb × Ankara · LC 014/2026 · plano de 17/10/2026 · branch `claude/powerbi-modifications-wqxekj`

**Ponto de partida.** Último commit: `7ba8c99`, com o tema escuro, esquema v8 e 164 testes.

**Situação ao fim da etapa Z (17/10/2026).** Esquema v13. Módulos A–F e ciclo da Zona01 entregues. A matriz abaixo está atualizada; a entrega e o que segue bloqueado estão em `docs/ENTREGA_FINAL.md`.

**O que já foi lido para este plano:**
- o diagnóstico de 15/10 (DIAGNOSTICO_MVP_MORRO_DA_CRUZ_REV01, §§1–8);
- as auditorias dos commits `b63b5db` (A01–A12), `fae5818`/`17a5b57` (estoque) e `f035f5c` (F01–F05);
- `docs/ETAPAS_0_1_APROVACAO.md`, `ETAPA_3_ESTOQUE.md`, `ETAPA_4_CAMPO.md` e `MATRIZ_REGIMES_FATURAMENTO.md`;
- o código atual.

As decisões que dependem de você ficam num documento único: `docs/DECISOES_PENDENTES.md`.

**Regra deste plano:** um requisito só fica **CONCLUÍDO** quando está implementado, integrado e demonstrado, com critério de aceitação conferido por teste ou pela interface. Ter tela ou função não basta. Os estados usados:

| Estado | Significado |
|---|---|
| **CONCLUÍDO** | implementado, integrado e demonstrado |
| **PARCIAL** | existe, mas falta parte |
| **A FAZER** | ainda não existe |
| **BLOQUEADO** | depende de decisão sua; a estrutura existe e a regra fica travada |

## 0. Ordem de execução e commits

| Etapa | Conteúdo | Commit |
|---|---|---|
| 0 | Este plano e o documento de decisões | `664ce0d` |
| 1 | F01–F05: já corrigidos em `3f7441c`; regressões em `tests/test_campo.py`. Reexecutados na suíte de cada etapa. | — |
| A | Base, histórico e acesso | `3f0f071` |
| B | Campo, qualidade e cadastro | `76d611f` |
| C | Compras, recebimento e almoxarifado | `df8cc03` |
| D | Planejamento e mapa | `e357211` |
| E | Medição e faturamento (estrutura; regras sem fonte ficam bloqueadas) | `fbae473` |
| F | Relatórios e operação | `e2419aa` |
| Z | Ciclo completo da Zona01 em ambiente isolado; suíte final; entrega | commit da etapa Z (`docs/ENTREGA_FINAL.md`) |

**Cada etapa segue os mesmos passos:**
1. critérios de aceitação;
2. implementação;
3. testes de casos normais, recusas, correções e falhas;
4. persistência sem gravação parcial;
5. interface;
6. evidências registradas;
7. commit e push.

**Limites que valem para todas as etapas:**
- nada é publicado ou exposto;
- o banco operacional não é migrado;
- as planilhas originais não são alteradas;
- nenhuma aprovação é preenchida em seu nome;
- a medição oficial continua bloqueada.

---

## 1. Falhas conhecidas (auditoria do commit `f035f5c`)

| # | Falha | Situação | Evidência |
|---|---|---|---|
| 1 | Legado 30/20 virava 10/0 | **CONCLUÍDO** (`3f7441c`): legado preservado, conciliação explícita, sem inventar posição | `TestF01AvancoLegado` (bancos v5 e v6 reais), `TestRetificacaoDoLegado` |
| 2 | Solda ⌈L/6⌉ gravada como confirmada | **CONCLUÍDO**: estimativa não é gravada; o OK usa as soldas verificadas e aprovadas | `TestF02SoldasSoReferencia`, piloto Zona01 |
| 3 | Pré-requisito de data posterior | **CONCLUÍDO**: cronologia por data do serviço; a retificação (v8) também respeita | `TestF03Cronologia`, `test_data_corrigida_respeita_a_cronologia` |
| 4 | Trecho com soldas retirado sem conciliação | **CONCLUÍDO**: definição única de histórico; reprova sem de-para | `TestF04HistoricoDeSoldas` |
| 5 | JPEG falso como evidência | **CONCLUÍDO**: imagem validada (Pillow ou estrutural); revalidação na migração | `TestF05ImagemValida`, `TestMigracaoV6ParaV7` |

---

## 2. Matriz de requisitos

### A. Base, histórico e acesso

| Requisito | Finalidade operacional | Existente | Restante | Dependências | Aceitação | Testes e evidências | Decisões |
|---|---|---|---|---|---|---|---|
| A1 Importação e conciliação de revisões sem perder registros | Trocar a revisão das planilhas sem apagar campo, estoque ou medição | **CONCLUÍDO**: simulação, backup, transação única, reprovação com histórico sem de-para, `SEM_ALTERACOES` na repetição, migração v1–v13 sem perda (cópia conferida + `foreign_key_check`) | — | — | revisão com trecho alterado reprova sem de-para; com histórico, preserva | `test_importacao`, `test_base_real`, ciclo Z passo 10 | D-01, D-02 |
| A2 Identidades estáveis (elemento, atividade, item, trecho) | Histórico não se perde quando o nome muda | **CONCLUÍDO** para trecho (handle + UTM), elemento, atividade e item. **PARCIAL** para material (id por especificação; sem de-para quando o BM mudar o item) | de-para de material numa revisão do BM | — | trocar nomes TR001↔TR002 mantém check-in e foto | `test_base_real` | — |
| A3 Login, usuários e permissões no servidor | Saber quem fez cada coisa; impedir que um perfil faça o que não lhe cabe | **CONCLUÍDO**: PBKDF2, sessão por cookie HttpOnly, permissão por rota no servidor, autor = usuário da sessão, limite de tentativas, X-MC contra CSRF | — | — | sem login, 401; sem permissão, 403 e nada gravado; autor = sessão | `test_acesso`, ciclo Z, navegador | D-10 |
| A4 Perfis: administração, engenharia, almoxarifado, equipe, topografia, cadastro | Separar funções | **CONCLUÍDO** com a matriz **PROVISÓRIA** de `config/perfis.json` (equipe restrita à própria frente) | distribuição real dos perfis e usuários reais (você) | A3 | cada rota tem permissão; a matriz é testada | `test_acesso` | D-10, D-11 |
| A5 Histórico de alterações e aprovações (autor, data, motivo) | Rastrear tudo que muda dado operacional | **CONCLUÍDO**: auditoria de toda gravação aceita ou recusada (usuário, perfil, rota, alvo estável, resultado); consulta por objeto na aba 6 e no detalhe do mapa | — | A3 | consulta por trecho mostra quem fez o quê | `test_acesso`, ciclo Z passo 11 | — |
| A6 Backup e restauração (banco + arquivos) | Recuperar a obra depois de erro ou perda | **CONCLUÍDO**: banco + fotos + documentos, manifesto com hashes, completude, restauração com backup de segurança; ensaiada no ciclo Z | ensaio em Windows | C | backup restaurado confere banco, fotos e documentos | `test_importacao`, ciclo Z passo 11 | — |
| A7 Reenvio sem duplicar | Clique repetido ou rede instável não lança duas vezes | **CONCLUÍDO**: chave X-Idem por requisição, mesma resposta no reenvio; a interface reenvia com a mesma chave | — | A3 | dois POST iguais com a mesma chave = um registro | `test_acesso`, ciclo Z passo 4 | — |
| A8 Concorrência (dois usuários, mesmo saldo) | Duas equipes não consomem o mesmo material | **CONCLUÍDO**: gravações serializadas numa transação por requisição; teste com requisições simultâneas pelo HTTP | — | A3 | só uma retirada passa; saldo nunca negativo | `test_acesso` (threads) | — |

### B. Campo, qualidade e cadastro

| Requisito | Finalidade | Existente | Restante | Dependências | Aceitação | Testes | Decisões |
|---|---|---|---|---|---|---|---|
| B1 Liberação topográfica | Só abrir vala onde a locação foi feita e conferida | **CONCLUÍDO**: liberação por intervalo com referência obrigatória; assentado sem liberação = alerta | bloqueio, se decidido | A3 | registro com intervalo, autor e referência; pendência no detalhe e no mapa | `test_campo_b`, ciclo Z passo 5 | D-20 |
| B2 Etapas executivas aplicáveis | Acompanhar escavação → assentamento → cadastro → reaterro → recomposição | **CONCLUÍDO**: escavação informativa; assentado, cadastro de campo, reaterrado; recomposição depois do OK | obrigatoriedade e ordem, se decididas | — | escavação registrada sem virar pré-requisito | `test_campo_b` | D-21 |
| B3 Execução parcial por intervalos, com cronologia e sem duplicidade | Medir o que foi feito, onde e quando | **CONCLUÍDO** (v6–v8); registros de execução, estoque e OK com data futura são recusados | — | — | critério 30/20; sobreposição, repetição e data futura recusadas | `test_campo`, `test_campo_b`, ciclo Z | D-30 |
| B4 Retificação sem apagar histórico | Corrigir lançamentos errados | **CONCLUÍDO** antes do OK (v8). **BLOQUEADO** depois do OK | — | — | ver `ETAPA_4_CAMPO.md` | `test_retificacao_cadastro` | D-16 |
| B5 Soldas previstas × informadas × verificadas | Não confundir estimativa com o executado | **CONCLUÍDO** | — | — | — | `test_campo`, piloto | D-31 (regra contratual) |
| B6 Fotos originais, hash, origem dos metadados | Evidência íntegra | **CONCLUÍDO** | — | — | — | `test_campo` (F05) | D-13 (janela da sinalização) |
| B7 Cadastro de campo separado da preparação, revisão e entrega | Não perder o levantamento com a vala aberta; conferir antes de protocolar | **CONCLUÍDO** (v8) | — | — | quatro fases com evidências e pendências | `test_retificacao_cadastro` | D-14, D-15, D-17 |
| B8 Pendências, impedimentos, correções, conferência interna | Saber o que impede o avanço e o que precisa ser corrigido | **CONCLUÍDO**: pendências consolidadas, conferência interna do cadastro, ocorrências (impedimento e não conformidade) abertas e resolvidas com autor, motivo e data | — | A3 | ocorrência aberta aparece no detalhe, no mapa e nos relatórios | `test_campo_b`, `test_relatorios` | D-22 |
| B9 Aprovação interna × Caesb | Não confundir as duas | **CONCLUÍDO** nos textos e nas cores (verde = Caesb registrada; azul = interno) | manter em toda tela nova | — | — | revisão de interface | — |

### C. Compras, recebimento e almoxarifado

| Requisito | Finalidade | Existente | Restante | Dependências | Aceitação | Testes | Decisões |
|---|---|---|---|---|---|---|---|
| C1 Solicitação e pedido de materiais | Comprar o que o planejamento precisa, com rastro | **CONCLUÍDO**: solicitação → aprovação por outra pessoa → pedido (fornecedor, itens, preço, prazo); o pedido nunca vira estoque | — | A3 | o pedido não altera nenhum saldo | `test_compras`, ciclo Z passo 2 | D-40, D-44 |
| C2 Fornecedor, documentos, vínculo pedido × recebimento | Saber de quem e por qual pedido o material chegou | **CONCLUÍDO**: fornecedor com CNPJ validado; documentos com hash; NF vinculada ao pedido, item a item, com saldo pendente | — | C1 | o recebimento abate o pendente do pedido; excesso é recusado | `test_compras` | — |
| C3 XML da NF-e e anexos; dados extraídos de imagem ou PDF conferidos antes de movimentar | Evitar digitação e não confiar em leitura automática sem conferência | **CONCLUÍDO**: XML validado (chave, modelo, totais, sem DOCTYPE) → NF A_CONFERIR → conferência item a item; PDF/imagem só com dados digitados e conferidos por outra pessoa | — | C2 | XML inválido recusado; NF importada não movimenta até a conferência | `test_compras`, ciclo Z passo 3 | — |
| C4 Entregas e aceites parciais, quarentena, recusa, devolução | Material só entra em estoque depois da inspeção, item a item | **CONCLUÍDO**: várias entregas por NF, quarentena, inspeção com aceito/recusado (laudo), devolução ao fornecedor do aceito | — | C2 | 100 pedidos, 60 entregues, 50 aceitos, 10 recusados: estoque 50 e pedido pendente de entrega 50 (o recusado precisa ser reposto) | `test_compras`, ciclo Z passo 3 | D-41 |
| C5 Estoque por especificação e unidade (Caesb / contratada / consumo) | Saldo certo de cada material | **CONCLUÍDO** (etapa 3 + módulo C) | — | — | — | `test_estoque` | — |
| C6 Reserva, retirada, destino, saldo em campo, aplicação, devolução, perda, transferência | Custódia completa | **CONCLUÍDO**, inclusive a transferência entre equipes com autorização | — | — | a custódia sai da equipe A e entra na B numa só transação | `test_estoque`, `test_compras`, ciclo Z passos 4 e 6 | — |
| C7 Inventário, estorno e retificação rastreáveis | Ajustar a diferença física com motivo | **CONCLUÍDO**: contagem → diferença → ajuste aprovado por outra pessoa; estorno e retificação de fechamento sem apagar | — | — | contagem 48 com saldo 50 → ajuste −2 registrado; saldo 48 | `test_compras`, ciclo Z passo 7 | D-42 |
| C8 Reservas antigas | Reserva de dia passado não pode prender saldo para sempre | **CONCLUÍDO**: listagem das vencidas e liberação explícita em lote, com motivo | expiração automática, se decidida | — | reserva vencida aparece; liberar devolve o disponível | `test_compras` | D-43 |
| C9 Pedido ≠ estoque ≠ faturável | — | **CONCLUÍDO** no fluxo de pedido, NF e aceite | — | — | nenhum lançamento de medição a partir de compra ou recebimento | `test_compras`, `test_medicao`, ciclo Z | — |

### D. Planejamento e mapa

| Requisito | Finalidade | Existente | Restante | Dependências | Aceitação | Testes | Decisões |
|---|---|---|---|---|---|---|---|
| D1 Visão geral e filtros (11 zonas, Adutora, CH) | Ver a obra por frente | **CONCLUÍDO**: filtro de frente nos números, na programação e nos relatórios (13 frentes) | — | — | cada frente filtra lista e números | `test_planejamento`, `test_relatorios`, navegador | — |
| D2 Programação das equipes por dia, nó e trecho | Planejar a semana e cobrar o realizado | **CONCLUÍDO**: programação (data, equipe, alvo, serviço, intervalo, materiais), realizada pelo check-in, encerramento com motivo, faltantes | — | A3, C | a programação aparece no mapa como planejado; o check-in a realiza | `test_planejamento`, ciclo Z passos 1 e 4 | — |
| D3 Situação de serviços e materiais ligada aos registros | O mapa reflete o que foi lançado | **CONCLUÍDO**: camadas planejado, material, andamento, verificação, cadastro e pendências, calculadas dos registros efetivos | — | D2 | cada camada vem só dos registros efetivos | `test_planejamento`, ciclo Z passo 8 | — |
| D4 Planejado × material × informado × verificado × cadastro | Diferenciar os estados | **CONCLUÍDO**: seletor de camada com legenda própria; verificado = interno | — | D3 | legendas distintas | navegador | — |
| D5 Fotos, documentos, histórico e pendências pelo mapa | Consultar tudo no clique | **CONCLUÍDO**: detalhe com fotos, pendências, intervalos, soldas, ocorrências, programação e histórico de auditoria; documentos de compra na aba 2.1 | — | A5, B8, C2 | o clique no trecho mostra tudo | navegador, ciclo Z | — |
| D6 Cores de diâmetro no modo Projeto; legendas operacionais; zoom, tela cheia, painéis | Não perder as funções da REV02 | **CONCLUÍDO** (a REV02 não é alterada) | — | — | zoom, tela cheia e painéis funcionam | navegador | — |

### E. Medição e faturamento

| Requisito | Finalidade | Existente | Restante | Dependências | Aceitação | Testes | Decisões |
|---|---|---|---|---|---|---|---|
| E1 Vínculo com os itens oficiais do BM | Medir no item certo | **CONCLUÍDO** para os serviços com fonte; sem item = PENDENTE. O painel de regras confere o vínculo no BM vigente (trecho sem item, item ausente = VÍNCULO INCOMPLETO); vínculo de dois itens incompleto fica PENDENTE (não rateia no que sobrou) | — | — | regras com fonte, situação e decisão | `test_regras`, `test_medicao`, navegador | D-50 (14 serviços), D-51, D-52 (MND) |
| E2 Quantidades elegíveis por período | Medir o que foi executado no mês | **CONCLUÍDO** dentro da regra provisória: o OK interno (trecho 100 %) propõe na medição do período; a elegibilidade por período mostra proposto, completo sem OK (com impedimentos), parcial não elegível e medido antes, com assentado e verificado no período. Medir por intervalo: **BLOQUEADO** | — | B3 | relatório elegível × medido por período | `test_medicao`, navegador | D-30 |
| E3 Parcelas já medidas e prevenção de duplicidade | Nunca medir duas vezes | **CONCLUÍDO**: chave da parcela com índice único; alvo × serviço conferido também sem o item (revisão do BM); parcelas por item (contrato, anterior, nesta, acumulado, saldo, acima do contrato); duplicidade antiga preservada e listada na migração v13. Estorno de proposta: **BLOQUEADO** | — | E2 | lançar de novo é recusado e nada é gravado | `test_medicao` | D-16 |
| E4 Regimes por categoria e fornecimento | Material faturado no regime certo | **BLOQUEADO**: material recebido e aplicado aparece por propriedade na elegibilidade, como BLOQUEADO; nenhum lançamento de material; nenhum percentual aplicado | estrutura de marcos por lançamento (matriz §4) quando a matriz for aprovada | — | material nunca entra em valor | `test_medicao` | D-53, D-54 |
| E5 Condições de liberação e evidências | Lançar só com a evidência do marco | **CONCLUÍDO** para as condições existentes (OK exige fotos; cadastro exige ESET): o retrato da conferência mostra as evidências de cada lançamento, e a CONFORME é recusada com foto obrigatória ausente ou inválida | — | E3 | a conferência mostra evidência ou falta | `test_medicao` | D-15, D-18, D-22 |
| E6 Reajuste e frações elegíveis | Reajuste correto | **BLOQUEADO**: simulação marcada como hipótese | — | — | — | — | D-55 |
| E7 Conferência e exportação | Revisar antes de apresentar | **CONCLUÍDO** para a medição de TESTE: conferência interna obrigatória e vigente antes do fechamento (retrato, assinatura, histórico); exportação com as abas CONFERÊNCIA, REGRAS, ELEGIBILIDADE e PARCELAS. Exportação no modelo `01ª MC` e medição oficial: **BLOQUEADAS** | — | — | fechamento só com conferência CONFORME vigente; oficial continua bloqueada | `test_medicao`, navegador | D-56, D-59 |
| E8 Não generalizar 80/20; sem item ≠ R$ 0; MND ≠ vala | — | **CONCLUÍDO** (etapas 0–1) | manter | — | — | `test_regras`, piloto | — |

### F. Relatórios e operação

| Requisito | Finalidade | Existente | Restante | Dependências | Aceitação | Testes | Decisões |
|---|---|---|---|---|---|---|---|
| F1 Previsto × comprado × recebido × reservado × aplicado × medido | Ver o ciclo do material de ponta a ponta | **CONCLUÍDO**: aba 7 e .xlsx, por material (previsto, solicitado, comprado, a receber, quarentena, recebido, almoxarifado, reservado, com as equipes, aplicado, perda); medido = bloqueado (D-53 · D-54), nunca zero | — | C | números batem com os movimentos (igualdade de conferência; estorno sai) | `test_relatorios`, navegador | D-53, D-54 |
| F2 Avanço por zona, equipe, período e etapa | Acompanhar a produção | **CONCLUÍDO**: intervalos efetivos por frente × equipe × etapa no período, por dia e acumulado por frente (%); legado sem posição à parte | — | — | soma por zona = soma geral; retificação conta o valor corrigido | `test_relatorios`, navegador | — |
| F3 Materiais faltantes, pendências, programação | Antecipar falta de material | **CONCLUÍDO**: faltantes da programação (D) e pendências por frente (ocorrências, verificação, reaterro sem cadastro, legado, aguardando OK, sem fotos, cadastro, programação vencida) e gerais | — | D2, C | a falta aparece antes do dia programado; cada pendência na sua frente | `test_planejamento`, `test_relatorios` | — |
| F4 Computador e celular | Usar em campo | **CONCLUÍDO no layout**: 0 px de rolagem lateral nas 9 abas em 360 px. acesso pelo celular **pronto para a nuvem** (`nuvem.py`, link fixo, `tests/test_nuvem.py`); falta a conta da hospedagem | — | — | navegação no celular sem rolagem lateral; login pelo https da hospedagem | navegador (360 × 740, toque); `test_nuvem` | D-60, D-62 |
| F5 Implantação, configuração, logs, backup e recuperação | Pôr em operação com segurança | **CONCLUÍDO**: log com rotação; `docs/IMPLANTACAO.md` (instalação, primeiro usuário, operação, rotina de backup, restauração, nova revisão, atualização de versão, recuperação de desastre, checklist); ensaio no ciclo Z. Windows não ensaiado | — | A3 | procedimento ensaiado no ciclo Z | etapa Z | D-60, D-61 |
| F6 Funcionamento sem internet | — | **NÃO INICIADO por regra**: depende de confirmar necessidade e alcance | — | — | — | — | D-61 |

---

## 3. Ciclo da Zona01 (etapa Z): critério de demonstração

O ciclo roda em ambiente isolado (cópia das planilhas reais, banco temporário, perfil TESTE), passo a passo:
1. planejamento;
2. solicitação e pedido;
3. recebimento parcial com conferência;
4. reserva e retirada;
5. execução parcial com fotos, soldas e cadastro;
6. devolução ou saldo com a equipe;
7. correção (retificação);
8. verificação e mapa;
9. proposta de medição de TESTE com pendências;
10. importação de revisão sem perder histórico;
11. restauração de backup com integridade.

Evidência: teste automatizado (`tests/test_ciclo_zona01.py`, que exige as planilhas reais), relatório em `docs/EVIDENCIAS_CICLO_ZONA01.md` e telas do navegador. Nada é gravado no ambiente operacional.

**Situação: CONCLUÍDO.** Os 12 passos passaram pelo HTTP, com a cópia das planilhas reais e o perfil TESTE, e o ambiente operacional foi conferido por hash. Ver `docs/EVIDENCIAS_CICLO_ZONA01.md`.

## 4. Riscos e limites conhecidos desde já

- **Windows não testado** (ambiente Linux).
- **Servidor de um processo**: a concorrência é segura porque as gravações são serializadas, mas não escala para muitos acessos simultâneos (adequado ao porte da obra; registrar).
- **Acesso pelo celular**: na nuvem, com link fixo (`docs/NUVEM.md`). Falta o responsável criar a conta da hospedagem (D-62).
- **Regras financeiras** sem fonte continuam bloqueadas (D-50 a D-56): a medição de TESTE mostra PENDENTE e hipóteses.
