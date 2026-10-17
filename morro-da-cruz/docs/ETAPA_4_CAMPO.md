# Etapa 4 — Campo e cadastro: intervalos, retificação, levantamento de campo, conferência do cadastro, soldas e foto original

CT 10239/2026 · 16/10/2026 · esquema v8 (v7 revisto em 17/10 após a auditoria do commit `f035f5c`; v8 em 17/10: continuação)

**Nada nesta etapa gera lançamento de medição ou faturamento:**
- a medição oficial continua bloqueada;
- o OK interno continua exigindo o trecho 100 % concluído, como antes.

**Uso nesta versão:** piloto de teste. Importação e restauração exigem o servidor parado.

## O que mudou (diagnóstico D1, D2, D5)

| # | Antes | Agora |
|---|---|---|
| D1 | Medição por trecho inteiro: só metros acumulados e estaca em texto livre. Não havia como impedir intervalo sobreposto ou repetido. | **Intervalos por etapa** (`intervalos_execucao`): ASSENTADO, CADASTRO_CAMPO e REATERRADO, de x m a y m desde o início do trecho (sentido da 06.1). **Recusados:** sobreposição na mesma etapa (com o registrado ou entre os novos), repetição, intervalo fora do trecho, e reaterro ou cadastro de campo sobre trecho não assentado. Os metros executados e reaterrados passam a ser o comprimento coberto por etapa, e o detalhe mostra o que foi feito e as **lacunas**. MND não tem vala: só ASSENTADO e CADASTRO_CAMPO. |
| D1 | — | **Informado × verificado:** cada intervalo guarda quem informou; a verificação é feita por outra pessoa (`verificar_intervalo`). |
| D5 | Não havia levantamento de campo antes do fechamento da vala. | **Cadastro de campo** como etapa própria. Reaterro sobre trecho ainda sem cadastro de campo gera **alerta** (`sem_cadastro_campo`), não bloqueio. Ver decisão abaixo. |
| — | Soldas só estimadas por ⌈L/6⌉. | **Soldas informadas** (tipo eletrofusão/topo, quantidade inteira, soldador, posição opcional) e **verificadas por outra pessoa** (nem o soldador nem quem informou), com resultado APROVADA/REPROVADA (reprovação exige motivo). A estimativa ⌈L/6⌉ aparece só como referência. |
| D2 | O navegador desenhava o carimbo e enviava só a imagem recomprimida. Original, EXIF e hash se perdiam; a data era a do envio. | **Arquivo original** guardado byte a byte, nomeado pelo **SHA-256** e conferido no backup (arquivo × hash do banco). **Tipo** validado pelo conteúdo (JPEG/PNG/HEIC), com limite de 20 MB. **Data:** EXIF > aparelho > envio. **GPS:** EXIF > navegador > indisponível, nunca inventado. A **origem** de cada dado fica registrada. A **mesma imagem** não pode ser usada em outro registro. O **carimbo** é texto exibido sobre a foto, não gravado na imagem. Pedido de GPS sem resposta em 10 s não trava o envio. |
| D4 | — | O pin já diz "programado" (feito nas etapas 0 e 1). |

## Correções da auditoria do commit `f035f5c` (17/10)

Cada achado foi reproduzido antes da correção. Sonda "antes" no código `f035f5c` → resultado "depois" no mesmo cenário:

| Achado | Antes | Agora | Teste |
|---|---|---|---|
| F01. Avanço legado sumia | Banco v5 real, com 30 m assentados e 20 m reaterrados só em metros. Depois da migração, a tela mostrava zero e o primeiro intervalo novo (30–40 m) levou o resumo a **10/0**. | O avanço anterior sem posição é reconhecido como **legado pendente** e **preservado** no resumo (30/20), com alerta. Enquanto existir, o trecho **recusa** novos intervalos, "100 %" e OK interno. A **conciliação do legado** (tela de campo) distribui exatamente os mesmos metros em posições confirmadas (origem LEGADO, motivo e responsável), **sem gerar quantidades de serviço**. Depois: 30/20 → novo 30–40 → **40/20**, com ASSENTAMENTO 30 + 10 = 40. Um banco já danificado pela versão anterior (10/0) volta a 40/20 após conciliar. | `TestF01AvancoLegado` (3) |
| F02. Solda estimada virava confirmada | 12 m gravavam SOLDA previsto 2 / confirmado 2, mesmo com a solda real reprovada. O OK usava esse número. | ⌈L/6⌉ aparece só como **estimativa** (não editável) e **não é gravada** no apontamento. Confirmar SOLDA no apontamento é recusado. O OK interno ignora SOLDA de apontamentos antigos e propõe, na medição de TESTE, uma linha **PENDENTE** com as soldas **verificadas e APROVADAS** (reprovadas e sem verificação ficam fora). A regra contratual continua pendente. | `TestF02SoldasSoReferencia` + piloto Zona01 (11 aprovadas, não 13) |
| F03. Cronologia ignorada | Com assentamento e cadastro de 16/10, um reaterro de 15/10 foi aceito como "com cadastro". | Reaterro e cadastro só sobre assentamento registrado **até a data do serviço**. O alerta "sem cadastro de campo" considera só cadastro **até a data do reaterro**, e é recalculado a cada lançamento (inclusive retroativo). No mesmo dia, a ordem não é conhecida e o serviço do próprio dia conta. | `TestF03Cronologia` |
| F04. Soldas fora da proteção de histórico | Trecho só com soldas foi retirado numa revisão sem conciliação e não aparecia nos retirados. | **Uma definição de histórico** (`servicos.historico_alvos`) usada pela importação e pelo mapa: check-in, apontamento, foto, execução, movimento, medição, **soldas, reservas, intervalos, conciliação**, cadastro e ligação. A retirada reprova até haver de-para/retirada explícita. "Retirados com histórico" mostra uma linha por objeto, com o que existe e o que pede tratamento. | `TestF04HistoricoDeSoldas` (2) |
| F05. Arquivo inválido aceito como foto | Assinatura JPEG + texto foi aceita, com hash, e contou como EXECUCAO. O gerador de fotos dos testes não produzia imagem decodificável. | `imagens.validar` antes de aceitar: **Pillow** (se instalado) decodifica os pixels. Sem Pillow, **PNG** é decodificado com a biblioteca padrão (CRC, zlib, tamanho exato) e **JPEG** tem a estrutura verificada (marcadores, DQT/DHT, SOF com dimensões, varredura e EOI). O método fica em `fotos.validacao`. HEIC é recusado (sem decodificador). Os bytes originais não mudam. Na migração, as fotos antigas são revalidadas: as **INVALIDA** e com **ARQUIVO_AUSENTE** deixam de contar como evidência. Os testes usam imagens reais (32×24 px), inclusive truncadas, corrompidas, progressivas e com EXIF ilegível. | `TestF05ImagemValida` (5), `TestMigracaoV6ParaV7` |

**Também mudou:** apontamento de trecho só em metros (sem de/até) passou a ser **recusado**, porque criava posição presumida. Intervalos SEQUENCIAIS antigos continuam marcados como "posição presumida", para confirmar por retificação.

**Navegador** (banco v5 migrado):
- alerta do legado;
- apontamento recusado até conciliar;
- conciliação pela tela;
- novo intervalo, com o resumo em 42/20;
- solda como estimativa;
- JPEG falso recusado;
- JPEG real com EXIF aceito.

Sem erros de console.

**Limitação: Windows** (registrada em 17/10, na continuação; o commit `3f7441c` não a trazia). Tudo foi executado em Linux, porque este ambiente não tem Windows. O código usa só caminhos com `os.path`, arquivos abertos com `with` (inclusive a revalidação de fotos) e SQLite da biblioteca padrão. Na primeira execução no Windows, conferir:
- gravação e leitura das fotos em `<pasta do banco>\fotos`;
- `pip install pillow`, recomendado para decodificar as fotos (sem ele, o JPEG passa só pela verificação estrutural);
- migração de um banco real v5/v6/v7 → v8 com `python importar.py --aplicar` e o servidor parado;
- `python -m unittest discover -s tests`.

A execução real no Windows continua pendente, como já registrado em `docs/CORRECOES_AUDITORIA_b63b5db.md`.

## Compatibilidade

- **Apontamento só em metros:** recusado desde a v7, porque não indica posição. Na v6, ele gerava intervalos SEQUENCIAIS presumidos; os existentes ficam sinalizados.
- **"100 % concluído":** preenche exatamente as lacunas (origem **COMPLETO**).
- **Migração v1–v6 → v7** (hoje v1–v7 → v8; `python importar.py --aplicar`, com o servidor parado):
  - fotos antigas ficam marcadas **LEGADO** (imagem carimbada, original não preservado, sem hash) e são **revalidadas**;
  - apontamentos antigos **não** ganham intervalo inventado: viram legado pendente, a conciliar;
  - a tabela de intervalos é recriada para aceitar as novas origens, com todas as linhas copiadas e conferidas.

**Defeito corrigido junto:** com `--db` fora de `dados/`, o servidor gravava e servia fotos em `dados/fotos` do programa, e não na pasta `fotos` ao lado do banco, que é a que o backup copia. Agora usa sempre `<pasta do banco>/fotos`.

## Testes (`tests/test_campo.py`, 14)

**Critério do diagnóstico:** 30 m assentados e 20 m reaterrados. Recusados: intervalo sobreposto, a mesma medição repetida, reaterro além do assentado, sobreposição entre os novos e intervalo fora do trecho. Nenhuma recusa grava nada.

**Também cobertos:**
- previsto pelo comprimento assentado;
- alerta de reaterro sem cadastro de campo;
- 100 % preenche só as lacunas;
- apontamento só em metros sinalizado;
- MND sem reaterro;
- verificação por outra pessoa;
- trecho com OK não aceita intervalo;
- soldas, com verificação segregada e motivo de reprovação;
- foto original byte a byte, com EXIF (data e GPS);
- origem da data e do GPS sem EXIF;
- reuso e arquivo inválido recusados;
- backup detecta foto trocada mesmo com o manifesto "acertado";
- migração com foto e apontamento legados.

**Navegador** (cópia da base real, perfil de teste):
- intervalos pelo formulário, com tabela de feito e lacunas e o alerta;
- envio de JPEG com EXIF pelo campo de arquivo;
- soldas registradas e verificadas.

Sem erros de console.

## Continuação (17/10, esquema v8): retificação, conciliação, cadastro e visão integrada

**Onde isto está no plano versionado.** O diagnóstico (§4) define a etapa 4 como "campo e cadastro": intervalos por etapa, cadastro de campo antes do fechamento (D5), soldas verificadas e foto original. Esta continuação completa a etapa 4 e adianta um item da etapa 5 (legenda do mapa: informado × verificado). A numeração não mudou e nenhuma etapa nova foi criada. A esteira continua com as mesmas seis colunas.

**O que não mudou:**
- OK interno, medição de TESTE, regras financeiras, CTRL-01 e vínculos da DEC-0001;
- medição oficial bloqueada;
- reaterro sem cadastro de campo continua só alerta.

### Finalidade operacional dos campos e estados novos

| Novo | Para que serve na obra | O que não é |
|---|---|---|
| Retificação (`retificacoes_intervalos`: registro corrigido, motivo, responsável, antes × depois) | Corrigir posição, extensão, etapa ou data informada errada (trena, croqui, data trocada) **sem apagar** o lançamento original. Fica registrado quem corrigiu e por quê. | Não serve para lançar avanço novo. |
| `anulado_por` / `retificacao_id` (intervalos e apontamentos) | Separar o registro **efetivo** do substituído. Só os efetivos contam no resumo, nas somas de quantidades (OK interno, consumo), no mapa e nas pendências. O substituído continua no histórico. | Nenhuma regra financeira nova. |
| `referencia` do levantamento (intervalo CADASTRO_CAMPO) | Dizer **qual registro de campo** (caderneta, croqui, arquivo de pontos) a empresa de cadastro vai receber para aquele trecho. | Não guarda o arquivo, só a referência a ele. |
| Conferência interna do cadastro (`revisoes_cadastro`: CONFORME / NAO_CONFORME, roteiro, quem conferiu, divergência) | Comparar o desenho da empresa com o executado e com o levantamento **antes de protocolar**, para evitar negativa no GDOC. | **Não é aprovação da Caesb** e não libera medição. Na tela: "conferência interna", chip azul (o verde fica para a decisão da Caesb). |
| Esteira "3 → 2: devolver à empresa" | Devolver o cadastro com a divergência apontada, abrindo nova revisão (Rev. N), como já acontecia depois de uma negativa (5A → 2). Só aparece com conferência NÃO CONFORME. | — |
| Verificação no mapa: INFORMADO, PARCIAL, VERIFICADO, LEGADO_SEM_POSICAO | Mostrar no mapa o que **só a equipe informou** e o que já foi conferido em campo. | "Verificado" é conferência interna Ankara. |

### Retificação de intervalos

**Unidade corrigida:** um apontamento ou uma conciliação do legado. Informa-se o conjunto **completo e correto** de intervalos daquele registro. Um conjunto vazio anula o registro (exemplo: lançado no trecho errado).

**Coerência das etapas.** Antes de gravar, o sistema valida o **trecho inteiro como ficaria** depois da correção:
- sem sobreposição e dentro do trecho;
- reaterro e cadastro de campo, **de qualquer registro**, com assentamento até a data deles.

Se a correção deixar um reaterro ou cadastro sem suporte, ela é recusada. A mensagem nomeia o registro dependente: "A correção deixaria CADASTRO_CAMPO 0–20 m de 16/10 (apontamento #2) sem assentamento… Retifique antes esse registro. Nada foi gravado." A ordem natural funciona: primeiro corrige-se o dependente, depois o assentamento.

**Tudo ou nada.** Toda a validação acontece antes da gravação. A gravação (anular, criar o substituto, quantidades, intervalos, alertas, resumo) ocorre numa única transação. Um teste simula a queda no meio da gravação e confere que nenhuma tabela mudou.

**Quantidades, sem dupla contagem.** O apontamento original fica anulado e sai de todas as somas; o substituto, ligado à retificação, entra no lugar dele:
- **mesmo comprimento assentado** (correção só de posição ou data): mantém as mesmas quantidades;
- **comprimento diferente**: usa o previsto do novo comprimento, pela mesma regra do "[✅ OK, Confirmar previsto]";
- **original com quantidade confirmada à mão**, ou com serviço fora do previsto: não há regra para recalcular, então o sistema pede as quantidades corrigidas em vez de presumir;
- **SOLDA**: nunca entra no apontamento.

**Data.** Pode ser corrigida. Exige o clima do novo dia, como o apontamento, e a cronologia continua valendo.

**Verificação:**
- intervalo que volta idêntico (mesma etapa, posição e data) mantém a verificação;
- os demais voltam a "informado";
- intervalo anulado não pode ser verificado.

**Recusada:**
- em trecho com OK interno (ver decisões);
- com avanço legado pendente (conciliar antes);
- em registro já retificado (a mensagem indica o substituto);
- quando nada muda;
- sem motivo ou sem responsável.

**Prévia.** Mostra antes × depois, o resumo do trecho, as quantidades que mudam e os alertas, sem gravar nada.

**Posição presumida.** Intervalos SEQUENCIAIS da v6 são confirmados por retificação, com as mesmas quantidades.

**Incoerência antiga.** Reaterro gravado antes da correção F03 aparece como alerta. Ela não bloqueia correções de outros registros, desde que a correção não a agrave.

### Conciliação do legado

O serviço vem do commit `3f7441c`: a soma por etapa é igual e não gera quantidades. Agora também:
- a tela aceita **vários intervalos por etapa** (o legado pode estar em trechos separados);
- uma conciliação pode ser **retificada**, mantendo exatamente os mesmos metros e sem quantidades;
- o mapa tem o painel "Avanço anterior sem posição — conciliar", com a lista dos trechos pendentes.

Depois de uma recusa, a tela mantém o que foi digitado.

### Cadastro: do levantamento em campo à entrega

| Fase | O que é | Evidências | Pendências |
|---|---|---|---|
| 1. Levantamento de campo | O que a equipe levanta **com a vala aberta**. Depois do reaterro não dá mais. | Intervalos CADASTRO_CAMPO: quem, quando, registro de referência e verificação. | Assentado sem levantamento; reaterrado antes do levantamento (alerta, com as faixas); sem registro de referência; sem verificação; legado a conciliar. |
| 2. Preparação do cadastro final | A empresa de cadastro desenha a partir do levantamento (esteira 1 → 3). | Empresa, data de envio, revisão, arquivos recebidos. | Aguarda OK interno; enviar à empresa; aguardando arquivos; levantamento incompleto (alerta). |
| 3. Conferência interna Ankara | A Ankara confere o desenho antes de protocolar. **Não é aprovação da Caesb.** | Conferências por revisão: resultado, quem conferiu, data, divergência e itens não conferidos. | Conferir a revisão recebida; não conforme → devolver à empresa. |
| 4. Entrega à Caesb (GDOC) | Protocolo e decisão da Caesb, registrada a partir do documento dela. | Protocolo, negativa ou memorando ESET, com data. | Aguardando análise; negado → reenviar. |

**Roteiro proposto da conferência** (6 itens, para ajustar ao que a Ankara usa):
- extensão;
- traçado e posição;
- profundidade e cotas;
- material e diâmetro;
- peças e nós;
- arquivos e nomenclatura.

CONFORME exige todos os itens. NÃO CONFORME exige a descrição da divergência.

**O que bloqueia:** só a conferência **NÃO CONFORME** registrada impede protocolar aquela revisão. Conferência ausente e levantamento incompleto aparecem como pendência, não como bloqueio (ver decisões). A conferência não gera lançamento de medição.

### Visão integrada

**Detalhe do trecho** (Fiscalização):
- pendências consolidadas por nível (bloqueio, alerta, pendente);
- execução por etapa: informado × verificado (m), feito e lacunas;
- intervalos por registro e histórico (conciliações, retificações, anulados);
- soldas;
- fotos com a validação (as que não contam aparecem marcadas);
- as quatro fases do cadastro.

**Aba Campo:** os mesmos intervalos por registro, com "Verificar" e "Retificar" (com prévia).

**Mapa:**
- a cor de andamento vem só dos registros efetivos;
- um miolo branco sobre a linha distingue informado sem verificação (tracejado curto), verificação parcial (tracejado longo) e legado sem posição (pontilhado);
- linha sem miolo = verificada (conferência interna);
- a legenda diz isso por escrito.

### Migração v7 → v8 e continuidade dos dados

A v8 só acrescenta colunas e tabelas: nenhuma linha é alterada. Para aplicar: `python importar.py --aplicar`, com o servidor parado.

**Testes:**
- `TestMigracaoV7ParaV8`: banco v7 com conciliação, intervalo informado verificado e quantidades. Depois da migração, todas as contagens são iguais; o resumo fica em 40/20, com 10 m verificados, e o mapa em PARCIAL. O banco migrado aceita retificação (30–40 → 30–38) e um apontamento novo, terminando em 45/20 com ASSENTAMENTO 45.
- `TestRetificacaoDoLegado`: banco v5 → v8, com conciliação, retificação da conciliação e apontamento novo.

**Demonstração com as planilhas reais** (perfil TESTE, banco isolado em pasta temporária):
- o banco foi criado e lançado com o **código do commit `3f7441c` (v7)**: apontamentos, legado, soldas, fotos, OK interno e esteira até "recebido";
- depois foi migrado com o código atual: CONCLUIDA 7 → 8, com todas as contagens iguais (5 apontamentos, 69 quantidades, 7 intervalos, 2 soldas, 4 fotos, 24 lançamentos de teste, 3 históricos de cadastro);
- a reaplicação resultou em SEM_ALTERACOES;
- as planilhas e o banco operacional não foram tocados.

### Testes (`tests/test_retificacao_cadastro.py`, 15)

- **Retificação:**
  - extensão corrigida, sem dupla contagem: o OK posterior propõe 76,55 m, não 78,55;
  - histórico preservado;
  - recusa quando reaterro ou cadastro perderiam suporte, sem gravar nada em 5 tabelas, e a sequência correta funciona;
  - queda simulada no meio da gravação;
  - data corrigida, com clima e cronologia;
  - quantidade editada à mão pede a correção;
  - posição presumida confirmada, com verificação só no intervalo idêntico;
  - recusas e prévia sem gravar;
  - anulação de lançamento no trecho errado.
- **Legado:** conciliação retificada com os mesmos metros e sem quantidades; legado pendente bloqueia a retificação.
- **Cadastro:**
  - evidências e pendências do levantamento;
  - conferência CONFORME e NÃO CONFORME;
  - protocolo bloqueado com NÃO CONFORME;
  - devolução (Rev. 1), nova conferência e protocolo;
  - nenhum lançamento de medição gerado.
- **Visão integrada:** pendências consolidadas; mapa INFORMADO → PARCIAL → VERIFICADO → PARCIAL depois da retificação; legado sem posição no mapa.
- **Migração v7 → v8.**

### Navegador (banco v7 real migrado, perfil TESTE)

- **Mapa:** miolos PARCIAL, INFORMADO e legado; painel do legado com TR002.
- **Detalhe do TR001:** pendências, informado × verificado e as quatro fases.
- **Campo, retificações:**
  - a correção do assentamento de 15/10 para 0–15 m foi recusada, nomeando o cadastro do apontamento #2, e nada mudou;
  - a correção de 30–42 para 30–40 m passou pela prévia (ASSENTAMENTO 12 → 10 e os demais serviços proporcionais) e foi aplicada;
  - o histórico mostra a retificação #1 e os 3 intervalos anulados.
- **TR002, conciliação:** com reaterro 10 m (legado 15) foi recusada, mantendo o que foi digitado; com assentado em 0–15 e 20–30 m e reaterro em 0–15 m foi aceita, e o resumo seguiu em 25/15.
- **Esteira, TR003:**
  - CONFORME com item não conferido foi recusada;
  - NÃO CONFORME registrada: "Catalogar no GDOC" sumiu, e o protocolo pela API foi recusado;
  - devolvido à empresa (Rev. 1), recebido, CONFORME, protocolado (GDOC-2026-0457);
  - os lançamentos de medição continuaram 24.
- **Console:** sem erros de JavaScript. Os 4 avisos de rede são as respostas 422 das 4 recusas provocadas de propósito.

## Decisões para você

1. **Reaterro sem cadastro de campo:** hoje é alerta. Deve **bloquear** o reaterro?
2. **Verificação dos intervalos e das soldas:** deve ser exigida antes do OK interno? Hoje não é, e o OK continua como antes.
3. **Herança da foto de sinalização (D3):** um nó herda a sinalização de qualquer trecho ligado, sem conferir a data. Deve exigir a mesma data ou uma janela de dias?
4. **Conferência interna antes do protocolo no GDOC:** deve ser obrigatória? Hoje, sem conferência é pendência; só a NÃO CONFORME bloqueia.
5. **Levantamento de campo completo antes de enviar à empresa:** exigir? Hoje é alerta.
6. **Retificação depois do OK interno:** o OK já gerou proposta na medição de teste e a entrada na esteira. Hoje a retificação é recusada, até definir como desfazer a proposta e o cadastro.
7. **Roteiro da conferência:** os 6 itens são proposta. Ajustar aos critérios usados pela Ankara (não são critérios da Caesb).

Continuam pendentes, sem alteração:
- aprovação do CTRL-01;
- confirmação dos vínculos da DEC-0001;
- as 5 decisões da matriz financeira;
- liberação da medição oficial.

## Pendências desta frente

- Retificação depois do OK interno (decisão 6).
- A etapa ESCAVADO não é registrada separadamente.
- Interligações e manobras (D8) não estão modeladas.
- O carimbo derivado (imagem com o texto gravado) para relatórios ainda não é gerado; hoje o carimbo é só exibido.
- Pessoas (informou, verificou, corrigiu, conferiu) são texto livre. Sem usuários e perfis (etapa 6), a segregação é só pela comparação de nomes.
- Arquivos do levantamento e do cadastro: o sistema guarda a referência (nome), não o arquivo.
- Etapa 5 (mapa): camada de pendências no mapa e teste das 13 frentes.
- Mantidas da etapa 3: pedido/compra e aceite parcial de NF não implementados. O fluxo integral de almoxarifado não está concluído (`docs/ETAPA_3_ESTOQUE.md`).
- Ambiente: os testes rodam em Linux. O Windows não foi testado (ver "Limitação: Windows" nas correções F01–F05).
