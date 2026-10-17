# Etapa 4 — Campo: intervalos, cadastro de campo, soldas e foto original

CT 10239/2026 · 16/10/2026 · esquema v7 (revisto em 17/10 após a auditoria do commit `f035f5c`)

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

## Compatibilidade

- **Apontamento só em metros:** recusado desde a v7, porque não indica posição. Na v6, ele gerava intervalos SEQUENCIAIS presumidos; os existentes ficam sinalizados.
- **"100 % concluído":** preenche exatamente as lacunas (origem **COMPLETO**).
- **Migração v1–v6 → v7** (`python importar.py --aplicar`, com o servidor parado):
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

## Decisões para você

1. **Reaterro sem cadastro de campo:** hoje é alerta. Deve **bloquear** o reaterro?
2. **Verificação dos intervalos e das soldas:** deve ser exigida antes do OK interno? Hoje não é, e o OK continua como antes.
3. **Herança da foto de sinalização (D3):** um nó herda a sinalização de qualquer trecho ligado, sem conferir a data. Deve exigir a mesma data ou uma janela de dias?

## Pendências desta frente

- Correção de intervalo já registrado (estorno coordenado com o apontamento e as quantidades), ainda não implementada.
- A etapa ESCAVADO não é registrada separadamente.
- Interligações e manobras (D8) não estão modeladas.
- O carimbo derivado (imagem com o texto gravado) para relatórios ainda não é gerado; hoje o carimbo é só exibido.
