# Correções da auditoria das etapas 0 e 1 (commit `b63b5db`)

CT 10239/2026 · 16/10/2026 · base: `AUDITORIA_ETAPAS_0_1_CLAUDE_b63b5db_15-10-2026.md`

O HEAD da branch continuava em `b63b5db` quando o trabalho começou, então **os 12 achados se aplicavam**. Antes de qualquer edição, cada um foi reproduzido em bancos descartáveis: A01–A04, A06–A10 e A12 com planilhas sintéticas; A05 e A11 com a base real.

**O que não foi feito nesta etapa:**
- nenhuma migração no banco operacional;
- nenhuma publicação;
- a medição oficial continua bloqueada;
- nenhuma regra financeira foi liberada.

## Resumo

| Achado | Antes (reprodução) | Depois (mesmo cenário) | Regressão |
|---|---|---|---|
| A01 | Item retirado gravado (`CONCLUIDA`, conferência falsa). Preço 999 gravado com BM divergente. | `REPROVADA`, rollback, banco byte a byte igual, relatório da reprovação em arquivo. | `TestA01ConferenciasAntesDoCommit` (4) |
| A02 | Nomes TR001/TR002 trocados: check-in passou para a outra geometria, sem pendência. | Check-in fica na geometria física original (agora chamada TR002). Pendência `TRECHO_RENOMEADO`. Divisão e união com histórico reprovam até haver de-para. | `TestA02IdentidadeTrechos` (5) + base real |
| A03 | Foto referenciada e ausente: `verificar()` dava `(True, [])`. | `BackupIncompleto`; pasta guardada e marcada INCOMPLETO; `verificar()` dá False. A importação não começa. | `TestA03BackupCompletude` (5) |
| A04 | Cópia `.substituido` sem os dados do WAL (`no such table: marca`). | O estado anterior vira um backup completo pela API do SQLite (contém `antes` e `posterior`) e é verificado. | `TestA04Restauracao` (2) + base real |
| A05 | DEC-0001 ligada a 18 avisos de DF-32, DF-02, DF-03 e nós vizinhos (base real). | Zero vínculos fora da DF-05. Na DF-05, só os 2 avisos de sobreposição. Padrão de texto vira "revisar", sem aplicar a decisão. | `TestA05Decisoes` (3) + base real |
| A06 | Sem EVIDÊNCIAS, as zonas viraram NULL. | Zonas, status e ID preservados, com pendência `EVIDENCIAS_AUSENTES`. Revisão incompatível reprova. | `TestA06Evidencias` (3) |
| A07 | MV-11 com handle: `IntegrityError` (UNIQUE da nomenclatura). | Mesmo `EL-`/`AT-`, chave `N:MV-11` → `H:7AB01`, check-in mantido, `IDENTIDADE_PROMOVIDA`. VTF sem handle continua sem coordenada. | `TestA07IdentidadeProvisoria` (2) |
| A08 | Resinas PE80/PE100 reordenadas trocaram de ID. | IDs seguem a resina; `SEM_ALTERACOES`. Correspondência ambígua cria itens novos com pendência, sem transferir identidade. | `TestA08IdentidadeItens` (5) |
| A09 | Medição TESTE fechada: R$ 6,82 → R$ 13,63 com BM de preço dobrado. | Continua R$ 6,82 (congelada), com alerta mostrando o valor que o cadastro atual daria. Migração v2 congela as medições fechadas antes do novo BM. | `TestA09MedicaoCongelada` (2) |
| A10 | Trecho com `vigente=0` aceitava check-in pelo ID. | Check-in, apontamento, foto, OK, recomposição e cadastro bloqueados. Consulta e check-out continuam. O mapa mostra só vigentes e lista os retirados com histórico. | `TestA10ObjetoRetirado` (2) |
| A11 | TR036 (MND): `previsto()` aceitava, `detalhe()` dizia "cálculo bloqueado". | Uma única regra (`regras.bloqueio_perfil`) para cálculo e detalhe. MND continua "item a definir". | `TestA11MND` + base real |
| A12 | Cinco planilhas ficavam abertas após importar (sem `gc`). Saída do subprocesso sem codificação definida. | Zero arquivos abertos. Workbooks fechados em `finally`. Programas escrevem em UTF-8. | Verificação em todo `tearDown` + `TestA12ArquivosECodificacao` (2) |

**Testes:** 90 OK.

| Arquivo | Testes |
|---|---|
| `test_importacao` (sintéticos, inclui as regressões) | 50 |
| `test_regras` | 26 |
| `test_fluxo_zona01` (base real) | 8 |
| `test_base_real` (base real em cópias) | 6 |

pyflakes sem avisos.

---

## A01 — conferências impeditivas antes do COMMIT

**Correção:** `importar.executar` reúne os bloqueios antes do COMMIT. Se houver algum, faz `ROLLBACK` e grava `dados/relatorios/importacao_<modo>_reprovada_<data>.json`. Erro inesperado também faz rollback e grava `..._falhou_...json`. Na linha de comando, sai com código 2.

**São impeditivos:**
- **`SEM_CONTROLES_APROVADOS`:** não há conjunto de controles para estes arquivos.
- **`CONTROLE_DIVERGENTE`:** contagens, extensão, unidades, quantidade em metros, agrupamento das evidências ou itens sem posição.
- **`TOTALIZACAO_BM_DIVERGE_DAS_CELULAS`:** a soma do sistema não reproduz o rodapé da própria planilha.
- **Pendências de identidade:** trecho, elemento ou atividade com histórico sem correspondência; PONTO duplicado; nomenclatura em dois elementos; conciliação inválida; evidência de outra revisão.
- **Integridade:** registro operacional que mudou de contagem; chave estrangeira violada.

**Decisão técnica — controles por revisão, não totais fixos:**
- Os controles ficam em `config/controles.json`, um conjunto por combinação exata de arquivos (SHA-256 de cada fonte).
- Uma revisão nova sem conjunto aprovado é reprovada. O relatório traz um `modelo_controles` com os hashes e os valores obtidos, para conferir na fonte e aprovar.
- **Justificativa:** um total antigo não serve para uma revisão legítima, e liberar qualquer diferença automaticamente anularia a conferência.
- A conferência do BM contra o próprio rodapé vale para qualquer revisão, por isso não depende do conjunto.

**Atenção:** o conjunto CTRL-01 (fontes atuais) está marcado **"A CONFIRMAR pelo usuário"**.
- Origem dos valores: pacote de 15/10 e auditoria independente.
- A importação aceita o conjunto, mas o relatório mostra quem aprovou.

## A02 — identidade física dos trechos

**Correção:** a identidade do trecho é **handle CAD + pontas UTM**.
- Na 06.1 REV01 real, o handle sozinho se repete em 123 trechos (TR001 e TR002 têm o mesmo handle, 5FD12). As pontas são únicas.

**Ordem de correspondência:**
1. De-para explícito.
2. Identidade física exata.
3. Mesmas pontas com handle redesenhado: casa e gera pendência informativa.
4. Nenhuma correspondência: ID novo.

**O nome nunca decide sozinho.** Trecho com histórico (check-in, apontamento, foto, execução, medição, cadastro, ligação) sem correspondência física reprova a importação, com os possíveis sucessores listados. Isso cobre traçado alterado, divisão, união e exclusão.

**De-para (`config/conciliacoes.json`):**
- `usar_id`: qual linha da fonte herda o ID.
- `retirar_id`: confirma a retirada; o histórico fica no ID retirado.
- Todas as entradas exigem responsável, data e motivo, e ficam registradas em `alteracoes`.

**Troca de nomes entre trechos:** usa nomes temporários dentro da transação, por causa do índice único do PONTO vigente.

**Verificado:**

| Cenário | Base | Resultado |
|---|---|---|
| Nomes trocados | Sintética e cópia da 06.1 real (TR001 ↔ TR002) | Check-in e foto ficam no TR-00001, com handle, pontas e extensão originais |
| Divisão com de-para | Sintética | Parte A herda o histórico; parte B ganha ID novo |
| União | Sintética | Reprovada |
| Mesmo nome com outra geometria, sem histórico | Sintética | ID novo, `TRECHO_SUBSTITUIDO` |

## A03 — completude do backup

**Correção:** o backup ficou em duas fases e duas verificações.
1. **Cópia:** primeiro o banco pela API do SQLite (instantâneo consistente); depois as fotos. O servidor grava o arquivo antes da linha em `fotos`, então toda foto citada no instantâneo já existe no disco.
2. **Verificação:**
   - **Integridade:** hash e tamanho dos arquivos, `integrity_check`, linhas e **SHA-256 do conteúdo de cada tabela**.
   - **Completude:** fotos citadas no banco copiado × fotos copiadas, recalculada a partir do banco do backup.

**Backup incompleto:**
- Fica guardado e marcado `INCOMPLETO`.
- `criar` lança `BackupIncompleto`, salvo com `--permitir-incompleto`.
- `importar --aplicar` não começa sem backup completo, salvo com `--aceitar-backup-incompleto`.

**Concorrência:** backup, restauração e importação criam `MANUTENCAO.lock`. Enquanto a trava existir, o servidor responde 503 a qualquer gravação.

## A04 — restauração com WAL e fotos

**Correção:** antes de restaurar, `restaurar` faz um **backup completo do estado atual**:
- pela API do SQLite, que inclui o WAL;
- com as fotos atuais;
- na pasta `backups/` e verificado.

**Sequência da restauração:**
1. Trava de manutenção ativa.
2. `BEGIN IMMEDIATE` espera gravações já em curso terminarem.
3. Restauração pela API do SQLite.
4. Fotos do backup devolvidas; fotos posteriores mantidas.
5. Verificação final: conteúdo de cada tabela igual ao manifesto e fotos referenciadas presentes e íntegras.

**Nomes de pasta sem colisão:** data com microssegundos e sufixo se já existir.

**Verificado:**
- Banco em WAL com a conexão aberta: a cópia de segurança contém `antes` e `posterior`.
- Foto apagada depois do backup volta; foto nova é mantida.
- Teste repetido sobre a base real.

## A05 — escopo das decisões

**Correção:** decisão só se liga a aviso por vínculo explícito (`decisao_vinculos`: nº do elemento + hash do texto) ou a objeto por escopo (`decisao_objetos`).
- O antigo `padrao_aviso` agora só **sugere** avisos parecidos: chip cinza "possível relação com DEC-xxxx — revisar".
- Avisos originais não foram tocados.

**Vínculos em `config/decisoes.json`:**

| Decisão | Vínculo |
|---|---|
| DEC-0001 | Só os 2 avisos de sobreposição da DF-05: "P1 — DF-05 contada em duas pranchas (16 e 19)" e "Tirar a DF-05 do resumo e do quadro de uma das pranchas" |
| DEC-0004 | Escopo nos objetos MV-11, VTF-12 e VTF-16 |
| DEC-0002, DEC-0003 | Sem vínculos: só sugestão |

**Base real:** 0 vínculos fora da DF-05 (antes, 18).

**Confirme os vínculos da DEC-0001.** O 3º aviso da DF-05 (tês 488/521) aparece apenas como "revisar DEC-0002".

**Limitação:** bancos já carregados com a DEC-0001 antiga mantêm o padrão antigo, porque a importação não altera decisões. Isso só afeta sugestões; vínculos dependem da tabela nova.

## A06 — evidências ausentes ou incompatíveis

**Correção:** quando não há evidência para o grupo, zona, status de posição e ID da auditoria **não entram no UPDATE**: ficam preservados.

| Situação | Resultado |
|---|---|
| Evidências ausentes | Pendência `EVIDENCIAS_AUSENTES` |
| Grupo sem par nas evidências | Pendência por elemento |
| Revisão incompatível (o nome indica REV da 06.2/06.1 diferente das fontes) | **Reprova** |

Se o conjunto de controles aprovado inclui o hash das evidências, a ausência delas também reprova. Só um conjunto aprovado sem evidências permite importar sem elas.

## A07 — identidade provisória → handle CAD

**Correção:** antes de criar elemento novo, procura um elemento vigente:
- com o mesmo nº;
- cuja chave não aparece na revisão;
- com as nomenclaturas contidas nas novas.

**Resultado da busca:**
- **`N:` → `H:`:** promove, mantendo o ID (`IDENTIDADE_PROMOVIDA`).
- **`H:` → `H:`** com mesma posição (±1 cm) e nomenclaturas: casa como handle redesenhado.
- **Qualquer outro caso:** ID novo. Se houver histórico, a retirada reprova até haver de-para.

**Posição:** coordenadas só vêm da fonte. VTF-12 sem handle continua sem coordenada e aparece na bandeja.

## A08 — identidade dos itens

**Correção:** o item passa a ser identificado por:
- **assinatura técnica completa:** descrição, DE, PN, resina, tipo, solda, material;
- **atributos mutáveis:** quantidade, código BM, BA/BB/BC, AG/AH.

**Correspondência:**
1. Exata (todos os campos).
2. Mesma assinatura com 1 item de cada lado: atualização.
3. Qualquer outro caso: itens novos, e os anteriores ficam não vigentes, com `ITEM_SEM_CORRESPONDENCIA_INEQUIVOCA`.

**Número na chave:** o nº em `chave_ocorrencia` é sequencial de criação, não posição. Duplicatas idênticas são intercambiáveis: reordená-las dá `SEM_ALTERACOES`.

**Migração v2 → v3:** recalcula a assinatura dos itens já importados, mantendo o nº e o ID.

## A09 — medição fechada congelada

**Correção:** `fechar_medicao` grava, numa transação:
- em cada lançamento: preço, classificação e item;
- na medição: fatores (BDI, K), fonte do BM e resumo completo (`resumo_congelado`).

**Comportamento:**
- **Medição fechada:** devolve os valores congelados e, se o cadastro atual daria outro valor, um `alerta_recalculo` sem alterar nada. Não pode ser fechada de novo.
- **Tetos de medições posteriores:** usam os preços congelados das anteriores.
- **Exportação:** usa o preço da medição.
- **Migração:** v1 e v2 congelam as medições já fechadas **antes** de o BM novo entrar.

## A10 — objeto retirado

**Correção:** `alvo(..., operacao=True)` exige objeto vigente (para atividade, também o elemento).

| Operação | Objeto retirado |
|---|---|
| Check-in, apontamento, foto, OK, recomposição, esteira GDOC | Bloqueados |
| Consulta e detalhe | Permitidos; a interface mostra "retirado" |
| Check-out | Permitido, para encerrar custódia aberta |

**Mapa:** pinta só objetos vigentes. Execução ou check-in aberto em objeto retirado vai para "Retirados da revisão vigente — com histórico". A bandeja sem posição filtra atividades vigentes e confere `lat` **e** `lon`.

## A11 — MND

**Correção:** `regras.bloqueio_perfil` é a única regra de perfil, usada em `quantidades_previstas_trecho` e em `detalhe`.
- TR036 (base real): sem "cálculo bloqueado".
- O enquadramento financeiro do MND continua "item a definir" e PENDENTE na medição.

## A12 — arquivos abertos e codificação

**Correção:**
- `importacao.planilha()` abre em modo leitura e fecha no `finally`, inclusive em erro.
- Os programas de linha de comando escrevem em UTF-8 (`backup.utf8_console()`).
- `seed.py` escreve a mensagem em UTF-8.

**Teste:** todo teste falha se sobrar arquivo aberto na pasta temporária (leitura de `/proc/self/fd`, sem `gc`).

**Achado novo, corrigido:** a conferência de conteúdo por tabela mostrou que a reimportação reescrevia `proveniencia`, `parametros` e `reajuste_indices` com `INSERT OR REPLACE`. As linhas eram apagadas e reinseridas com o mesmo valor. Agora só se atualiza o que mudou. Na base real, a reimportação altera apenas a tabela `importacoes`.

---

## Reavaliação de 16/10 — controles sem aprovação efetiva (commit seguinte ao `46616af`)

**Problema confirmado na reavaliação:** um conjunto de controles com `esperado` vazio e sem aprovador era aceito: `CONCLUIDA` e `contagens_ok = true`. Era uma falsa confirmação de conferência.

**Correção:** `importacao.validar_controle` confere a estrutura e a aprovação antes de aplicar.

| Exigência | Resultado se faltar |
|---|---|
| `id` e `perfil` (`REAL` ou `TESTE`, igual ao da importação) | `CONTROLE_INCOMPLETO` |
| Hashes SHA-256 válidos em `fontes` | `CONTROLE_INCOMPLETO` |
| Todas as conferências obrigatórias em `esperado`, com tipo válido (`trechos`, `extensao_m`, `elementos`, `atividades`, `itens_projeto`, `bm_vertical`, `bm_juntada`, `sem_posicao`, `unidades_linhas`; com EVIDÊNCIAS, `agrupamento_evidencias_iguais`) | `CONTROLE_INCOMPLETO`, com a lista do que falta |
| `origem_dos_valores` preenchida | `CONTROLE_INCOMPLETO` |
| Bloco `aprovacao` com `status: "APROVADO"`, `por` (nome) e `em` (AAAA-MM-DD), sem texto provisório | `CONTROLE_SEM_APROVACAO` |

- Na **aplicação**, qualquer um desses problemas reprova (rollback e relatório legível).
- Na **simulação**, vira aviso: status `SIMULADA_SEM_CONTROLE_APROVADO`, `contagens_ok = false`. A comparação dos valores continua visível, para conferir antes de aprovar.
- `aprovado_por` solto ou "A CONFIRMAR" não vale como aprovação.
- **O sistema não preenche a aprovação.** O conjunto real (CTRL-01) está com `aprovacao.status = "PENDENTE"`; aplicar a importação real fica recusado até você preencher.
- **Perfis separados:** os testes usam perfil `TESTE` (sintético, ou cópia dos controles reais aprovada pelo teste automatizado). Um conjunto `TESTE` não vale numa importação `REAL`.

**Servidor parado:** importação (`--aplicar`) e restauração recusam rodar se o servidor deste banco estiver respondendo (`ServidorAtivo`). O servidor registra `SERVIDOR_ATIVO.json` ao iniciar e o apaga ao sair. Marca órfã (servidor que caiu) não bloqueia. A simulação continua liberada.

**Testes:** 11 novos em `TestControlesAprovacao` e `TestServidorParado`, mais 1 na base real:
- os dois casos da sonda da auditoria (esperado vazio + sem aprovador; sem aprovador);
- campo obrigatório ausente;
- tipo inválido, origem provisória e conferência desconhecida;
- aprovação solta, provisória, pendente ou com data inválida;
- perfil trocado;
- aprovação válida (`CONCLUIDA`, registra quem aprovou);
- simulação sem aprovação;
- modelo com aprovação pendente;
- conjunto real completo e sem aprovação inventada;
- servidor respondendo;
- na base real: perfil real pendente simula, mas não aplica.

**Suíte:** 102 testes OK.

## Verificações sobre a base real (em cópias)

| Verificação | Resultado |
|---|---|
| Carga | 1.436 trechos · 110.686,03 m · 1.191 elementos (1.059 nós / 132 caixas) · 1.242 atividades · 6.539 itens · BM 432/347 · sem posição MV-11, VTF-12, VTF-16 · agrupamento 1.191/1.191 |
| Unidades | UN 6.051 · M 73 linhas = 72,95 m · PÇ 54 · PENDENTE 361 (nada ajustado) |
| BM | P0 recalculado = célula 49.878.748,6575869; diferença de +0,0975869 para o contrato registrada |
| Reimportação | `SEM_ALTERACOES`; SHA-256 do conteúdo igual em todas as tabelas exceto `importacoes` |
| Nomes trocados TR001 ↔ TR002 (cópia da 06.1 com controle próprio) | Check-in e foto no TR-00001, com geometria original |
| Migração v1 com movimentos | Romaneio, custódia, aplicado e sobra; foto, execução e medição fechada; tudo remapeado, congelado e preservado; DF-33 CH = "17 UN · 0,71 m" |
| Restauração com WAL e foto | Cópia de segurança com o estado do WAL; conteúdo restaurado igual ao manifesto |
| Decisões e MND | DEC-0001 só na DF-05; TR036 sem bloqueio de vala |
| Navegador (Chromium) | Detalhe de DF-05, DF-32 e TR036 e medição TESTE com a lista de hipóteses. Único erro de console: `favicon.ico` 404, que o navegador pede sozinho (corrigido com ícone inline) |

## O que não foi testado

- **Windows.** Não há Windows neste ambiente. A suíte foi preparada para ele:
  - a verificação de arquivo aberto é mais rígida que o bloqueio do Windows;
  - a saída é testada com console `cp1252` simulado.
  - **A execução real no Windows ainda precisa ser feita.**
- **Seu banco operacional:** não existe aqui. A migração real (v1 → v3) não foi executada.
- **Concorrência real servidor × restauração.**
  - Coberta pela trava, pelo 503 do servidor e por `BEGIN IMMEDIATE`.
  - Resta uma janela teórica: uma requisição que conferiu a trava pouco antes de ela ser criada ainda pode gravar.
  - **Nesta versão, importação e restauração exigem o servidor parado** (agora verificado pelo programa). Aguarde as operações em curso antes de importar ou restaurar. Manutenção com usuários simultâneos exige sincronização adicional, não implementada.
- **Só com sintéticos** (não há revisões reais desses casos):
  - MV-11 com handle;
  - divisão e união de trechos;
  - revisão do BM.
- **Interface:** clique no mapa REV02 e uso no celular não foram repetidos.

## Mantido sem alteração

- **Contagens e unidades:** as da tabela acima; UN, PÇ e M separados; unidade sem fonte PENDENTE; DF-33 CH "17 UN · 0,71 m".
- **Colunas da 06.2:** avisos AA/AB/AW preservados; BA/BB importados.
- **Travas financeiras:**
  - medição oficial bloqueada;
  - NF aceita sem lançamento;
  - MND sem item automático;
  - nenhum 80/20 nem 100 % na aplicação.
- **BM:** diferença para o contrato registrada sem ajuste.
