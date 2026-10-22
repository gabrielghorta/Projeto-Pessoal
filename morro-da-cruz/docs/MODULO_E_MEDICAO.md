# Módulo E — medição e faturamento

CT 10.239/2026 · 17/10/2026 · esquema v13 · plano: `docs/PLANO_ENTREGA_COMPLETA.md` §E

Este módulo implementa só o que tem fonte e aprovação confirmadas. O resto fica **identificado e bloqueado**, com a decisão correspondente em `docs/DECISOES_PENDENTES.md`. Continua tudo como medição de **TESTE**:
- a medição oficial segue bloqueada (`medicao_oficial_liberada = NAO`, D-56);
- nenhuma aprovação é preenchida pelo sistema;
- a conferência da engenharia é interna da Ankara e não é aprovação da Caesb.

## Finalidade operacional

| Novo | Para que serve | O que não é |
|---|---|---|
| **Parcela única** | A mesma parcela (alvo × serviço × item do BM) não entra em duas medições do mesmo tipo. A trava está na regra (mensagem clara, nada gravado) e no banco (índice único sobre a chave da parcela). O alvo × serviço também é conferido sem o item, para valer depois de uma revisão do BM que troque o item. | Não estorna proposta: o estorno depois do OK interno depende da D-16. |
| **Parcelas por item do BM** | Por item com lançamento proposto: quantidade do contrato, medido antes, nesta medição, acumulado e saldo. O acumulado acima do contrato vira alerta. | — |
| **Duplicidades** | Lista as parcelas em mais de uma medição, inclusive as gravadas antes da trava (migração v13). Uma duplicidade impede a conferência CONFORME. | Nada é apagado. |
| **Elegibilidade do período** | Por trecho ou nó com atividade no período:<br>• **proposto nesta**;<br>• **completo sem OK interno** (com os impedimentos: fotos obrigatórias, legado sem posição);<br>• **parcial, não elegível** (D-30);<br>• **medido antes**.<br>Mostra assentado e verificado no período, cadastros medidos nesta, recomposições não lançadas e material recebido e aplicado por propriedade. | Execução parcial não é proposta (D-30). O material aparece **BLOQUEADO** (D-53, D-54): recebido não é faturável e nenhum percentual (80/20 ou outro) é aplicado. |
| **Conferência interna da engenharia** | Antes de fechar, a engenharia confere a proposta. O sistema grava:<br>• o roteiro de 5 itens;<br>• o resultado;<br>• quem conferiu (o usuário da sessão);<br>• o **retrato** das evidências e pendências de cada lançamento (OK interno por e em, fotos válidas e faltantes, verificação, soldas, ocorrências abertas, cadastro com GDOC e ESET);<br>• a **assinatura** dos lançamentos conferidos.<br>Se um lançamento mudar depois, a conferência deixa de valer. | Não é aprovação da Caesb. A CONFORME é recusada com impeditivo (duplicidade, ou foto obrigatória ausente ou inválida num alvo com lançamento proposto). Os alertas (ocorrência aberta, intervalo sem verificação, solda sem verificação, acima do contrato) ficam registrados sem bloquear (D-18, D-22). |
| **Fechamento** | Exige a última conferência CONFORME e vigente. Grava quem fechou, quando e qual conferência liberou o fechamento. Depois disso, a medição fica congelada (como antes). | Fechar a medição de TESTE não a torna oficial. |
| **Regras da medição** | Painel com cada regra e sua situação: **confirmada** (com fonte), **provisória**, **hipótese**, **bloqueada** ou **vínculo incompleto** (item do BM vigente ausente). Cada regra mostra o efeito no cálculo e a decisão. | — |
| **Exportação .xlsx** | Abas novas: **CONFERÊNCIA** (retrato gravado ou atual), **REGRAS**, **ELEGIBILIDADE** e **PARCELAS**. Continua marcada TESTE — NÃO OFICIAL. | O modelo oficial `01ª MC` segue bloqueado (D-56). |

## Mudança de comportamento: vínculo incompleto não rateia no item que sobrou

Um serviço configurado com dois itens (escavação mecanizada: 5.4.11 + 5.4.13; 5.4.15 + 5.4.14) é rateado pela proporção contratual (hipótese, D-51).

Antes, se um dos itens faltasse no BM vigente, a quantidade inteira ia para o item restante. Agora o lançamento fica **PENDENTE** ("sem item de BM com fonte"). O painel de regras mostra **VÍNCULO INCOMPLETO** e o item ausente.

Com o BM real (REV04), os dois itens existem e a regra aparece como hipótese.

## Regras e decisões (situação em 17/10/2026)

| Regra | Situação | Decisão |
|---|---|---|
| Serviços com item comprovado na 06.1 (assentamento pelo código BM, escavações, esgotamento, locação) | confirmada | — |
| Escavação mecanizada em dois itens (rateio) | hipótese (impede a oficial) | D-51 |
| 14 serviços sem item comprovado; recomposição com item A CONFIRMAR | bloqueada (PENDENTE, fora do valor) | D-50 |
| Solda | bloqueada (PENDENTE com as aprovadas) | D-31 |
| Assentamento MND | bloqueada (sem substituir por vala) | D-52 |
| Material: categorias e regime | bloqueada | D-53, D-54 |
| Cadastro na aprovação GDOC (ESET) | provisória | D-58 |
| Medir por intervalo | provisória (só trecho completo) | D-30 |
| Teto por subgrupo | hipótese | D-57 |
| Reajuste (revisão elegível e pedido) | hipótese (impede a oficial) | D-55 |
| Estorno de proposta depois do OK | bloqueada | D-16 |
| Conferência interna obrigatória antes de fechar | provisória | **D-59 (nova)** |
| Medição oficial e modelo 01ª MC | bloqueada | D-56 |

## Esquema v13 (migração sem perda)

O que muda no banco:
- `medicao_lancamentos.chave`: a chave da parcela, com índice único parcial (`WHERE chave IS NOT NULL`);
- `medicoes.fechada_por`, `fechada_em` e `conferencia_id`;
- tabela `conferencias_medicao`, com o histórico de todas as conferências, inclusive as NÃO CONFORME.

Na migração, os lançamentos existentes recebem a chave na ordem em que foram gravados. Uma parcela repetida por versão anterior fica **sem chave**: é preservada e aparece no relatório de duplicidades. A conferência CONFORME da medição que a contém fica impedida até a decisão da engenharia.

## Gaveta 5, item a aprovar e "medível com restrição" (esquema v19, 22/10/2026)

Decisões D-90 a D-97 (`docs/DECISOES_PENDENTES.md`, seção 8). Código: `apropriacao.py`; a regra do item a aprovar está em
`servicos._lancar`.

**Situação do item na base de custo** (só duas, para toda a medição):
- **aprovado:** código da base Caesb (215 itens), SINAPI ("SI" no código, 185) ou SICRO ("SC", 16), que vieram no orçamento
  da licitação (P0), ou código provisório com o código oficial registrado;
- **a aprovar:** os 16 itens do BM com "X" no código (ex.: `1514603060XX11`) até a Caesb dar o código oficial, e os itens
  novos, fora do BM.

Qualquer lançamento num item a aprovar fica **PENDENTE** com a restrição `ITEM_A_APROVAR`, inclusive os que vêm do OK
interno (gavetas 1 a 4). O lançamento de material do OK interno de nós passa a guardar o item do BM (continua PENDENTE,
restrição `MATERIAL_SEM_REGIME`), para o valor parado aparecer.

**Gaveta 5 — Apropriação direta.** Entra na medição de TESTE a apropriação em item **aprovado**, de **serviço** e dentro
da quantidade do BM (contratado − medido nas gavetas 1 a 4 − já proposto de apropriações). Vai para a medição de teste
aberta do mês da data ou, se ela já fechou ou não existe, para a próxima aberta. A chave da parcela é
`TESTE|5|APROPRIAÇÃO DIRETA|APROPRIACAO|<nº>|<item>|<unid.>`: não duplica. Passa pela mesma conferência interna
(o retrato mostra as evidências da apropriação). A medição oficial continua bloqueada (D-56). O item novo aprovado entra
com o preço aprovado no cálculo (sem BDI na linha; o BDI e o K são os da medição).

**Quando a restrição cai, entra sozinho** (`apropriacao.sincronizar`), na hora em que o código é registrado, o item novo
é aprovado ou uma medição de teste é aberta:
- apropriação: a quantidade ainda não proposta vira proposta (complemento com outro nome de serviço, se já havia uma parte);
- lançamento retido numa medição **aberta**: vira PROPOSTO ali mesmo (a conferência deixa de valer, como em qualquer mudança);
- lançamento retido numa medição **fechada**: uma cópia PROPOSTA entra na próxima medição de teste aberta, apontando para
  o original (`origem_id`). O original fica como estava; o relatório de duplicidades não conta o par.

**Painel "Medível com restrição"** (`GET /api/medicao/restricoes?medicao=`). Não entra no valor da medição. Cada linha:
item, quantidade, **valor parado** (sem BDI: quantidade × preço do BM; no item novo, o preço proposto, "estimado"), a
restrição em etiqueta forte, há quantos dias está parado e a ação que libera e quem faz. No topo, o total por restrição,
filtros por restrição e por grupo e os botões "Registrar código oficial" e "Abrir a esteira do cadastro".

| Restrição | O que entra | Libera |
|---|---|---|
| a. Item a aprovar | apropriações e lançamentos retidos em item XX ou novo; item novo reprovado aparece à parte | registrar o código oficial da Caesb |
| b. Acima da contratada no BM | o excedente da apropriação sobre o saldo do item | aditivo ou apostilamento |
| c. Excedente do teto do subgrupo (D-57) | o excedente da tabela de tetos da medição | aditivo ou apostilamento |
| d. Material sem regime (D-53/D-54) | apropriação em item de material e lançamento de material do OK interno | aprovar a matriz de regimes |
| e. Cadastro esperando o GDOC | trecho em `4_GDOC_ANALISE` (cobrar o memorando ESET), `3_RECEBIDO` (protocolar) e `5A_NEGADO` (reenviar à empresa); valor = extensão × item de cadastro (D-58) | as ações da esteira |
| — Sem medição aberta | apropriação livre, mas sem medição de teste aberta para a data | abrir a medição do mês |

**Painel "Itens a aprovar na base de custo":** os 16 XX e os itens novos, com a situação, o valor parado e as ações
registrar o código (XX), aprovar (código, preço aprovado, data e o ofício ou memorando em PDF) e reprovar (motivo, fica no
histórico). A planilha do BM não muda: o código fica em `codigos_oficiais` e aparece junto do item (LEV › BM Vertical,
coluna Situação). Quando uma revisão nova do BM vier já com o código, a tela mostra "conciliado com a REV xx".

| Rota | Permissão |
|---|---|
| `POST /api/base-custo/codigo-oficial` `{item_ref, codigo, data, documento_b64}` | `medicao` |
| `POST /api/base-custo/decidir` `{item_ref, acao: APROVAR\|REPROVAR, codigo, preco_aprovado, data, documento_b64, motivo}` | `medicao` |
| `GET /api/medicao/restricoes?medicao=` (lista, totais e os itens a aprovar) | tela `medicao` |
| `POST /api/medicao` (abrir medição de teste) | `medicao`; agora também propõe o que estava livre |

Testes: `tests/test_apropriacao.py` (`TestMedicao`, `TestSituacao`, `TestMigracaoV19`).

## Rotas

| Rota | Permissão | Autor gravado |
|---|---|---|
| `GET /api/medicao?id=` (resumo, conferência vigente, histórico de conferências, duplicidades, parcelas por item, regras e roteiro) | logado | — |
| `GET /api/medicao/elegibilidade?id=` | logado | — |
| `POST /api/medicao/conferir` `{medicao_id, resultado, checklist, obs}` | `medicao` | `por` = usuário da sessão |
| `POST /api/medicao/fechar` `{medicao_id}` | `medicao` | `por` = usuário da sessão |

## Testes (`tests/test_medicao.py`, 7)

- **Parcela única:**
  - a mesma parcela é recusada na medição seguinte;
  - o mesmo alvo × serviço com outro item (revisão do BM) também é recusado;
  - o OK repetido é recusado;
  - um INSERT direto com a mesma chave é barrado pelo banco;
  - nada é gravado nas recusas;
  - parcelas: 76,55 m nesta, saldo = contrato − 76,55, e "anterior" 76,55 na medição seguinte.
- **Medição fechada:** lançamento novo (recomposição) recusado, sem gravação parcial.
- **Elegibilidade:**
  - TR001 proposto;
  - TR002 completo sem fotos → apto sem OK, com impedimento;
  - MND parcial → não elegível (D-30), com 10 m assentados e verificados e ocorrência aberta (alerta D-22);
  - material: recebido 100 e aplicado 24, BLOQUEADO, sem nenhum lançamento de material;
  - no mês seguinte, o medido sai e o apto continua.
- **Conferência e fechamento:**
  - fechar sem conferência: recusado;
  - CONFORME incompleta, NÃO CONFORME sem observação e medição vazia: recusadas;
  - fechar com a última NÃO CONFORME: recusado;
  - com a foto obrigatória perdida (ARQUIVO_AUSENTE), a CONFORME é recusada; restaurada, é aceita;
  - o retrato registra OK interno por eng1 e 3 fotos;
  - lançamento novo depois da conferência → a conferência deixa de valer e o fechamento é recusado; nova conferência → fecha, com quem fechou e qual conferência;
  - histórico com as 3 conferências;
  - conferir depois de fechada: recusado.
- **Regras:**
  - D-31, D-50, D-52, D-53·D-54, D-56 e D-16 bloqueadas;
  - D-55 e D-57 hipóteses;
  - D-51 com vínculo incompleto no BM sintético;
  - "nenhum percentual (80/20 ou outro)";
  - MND fica PENDENTE sem item;
  - OFICIAL recusada.
- **Migração v12 → v13:**
  - duplicidade antiga preservada (sem chave);
  - aparece no relatório;
  - a medição segue utilizável;
  - CONFORME recusada pela duplicidade; NÃO CONFORME registrada.
- **Pelo HTTP:**
  - almoxarifado recebe 403;
  - fechar sem conferência dá 422;
  - o autor é a sessão, não o nome digitado ("Fiscal da Caesb" foi ignorado);
  - resumo com regras e roteiro;
  - elegibilidade;
  - fechamento grava quem fechou, com auditoria no alvo MEDICAO;
  - a exportação traz as 4 abas novas, marcadas TESTE.

## Navegador (banco v7 real migrado para v13, usuários de demonstração)

- **Medição 1 (ABERTA):** o fechamento começa desabilitado, com o aviso "Sem conferência interna".
- **Regras:** 22 linhas. Com o BM real, a escavação mecanizada aparece como hipótese (D-51).
- **Elegibilidade:** 1 proposto (TR003) e 2 parciais (TR001, TR002), com 45,22 m assentados e 30 m verificados no período.
- **Parcelas:** 12 itens com contrato, nesta e saldo.
- **Conferência:**
  - CONFORME sem os itens marcados: recusada, com a lista dos itens pendentes;
  - NÃO CONFORME com observação: registrada; o fechamento continua desabilitado;
  - CONFORME completa: registrada; o fechamento é habilitado; o histórico mostra as 2 conferências.
- **Almoxarifado:** o formulário de conferência fica oculto; o POST direto devolve 403.
- **Exportação:** `TESTE_MEDICAO_01_MORRO_DA_CRUZ.xlsx`.
- **Fechamento:** a medição passa a FECHADA e o formulário de conferência some.
- **Link na elegibilidade:** abre o mapa no detalhe do trecho.
- Sem erros de JavaScript.

## Limitações

- O roteiro de 5 itens e a obrigatoriedade da conferência são provisórios (D-59).
- A conferência não exige pessoa diferente de quem deu o OK interno (segregação: ver D-11).
- A elegibilidade lista trechos e nós com atividade no período, mais os completos sem OK de qualquer data. Ela não substitui a apuração mensal da fiscalização.
- O estorno de proposta e a reabertura de medição não existem (D-16).
- O regime de material, o reajuste com frações elegíveis e o modelo oficial `01ª MC` continuam bloqueados.
