> Pesquisa de 20/10/2026 para a Nota de Serviço por upload (somente leitura do código). Os caminhos em /tmp são do rascunho da sessão e não existem no repositório; o protótipo citado está em `ferramentas/ns/`.

# Fotos pelo Telegram, subidas depois só para a medição: mapa do impacto

Fiz só leitura. Nenhum arquivo de `/home/user/projeto-pessoal/morro-da-cruz` mudou: conferi o md5 de todos os 159 arquivos antes e depois, e o `git status` ficou igual. Os testes rodaram num banco de demonstração montado a partir das planilhas reais, dentro da pasta de rascunho (seção 8).

## Resumo
1. **Hoje, a foto é condição do OK interno.** A regra está em `regras.py:182-183`, chamada em `servicos.py:1752`. O OK faz três coisas: põe o trecho na esteira de cadastro (`servicos.py:1786-1788`), gera a proposta de medição e escolhe a medição pela data do OK (`servicos.py:1754` e `2069-2077`; a tela manda `hoje()`, `web/app.js:373`).
   - Com fotos chegando semanas depois, o OK e a esteira ficam esperando.
   - Se o OK for dado no dia do upload, o trecho cai na medição daquele dia. Se essa medição estiver fechada, dá erro.
2. **A trava certa já existe na medição.** O retrato tem o impeditivo "evidência fotográfica obrigatória ausente" (`medicao.py:248-250`) e a conferência CONFORME é recusada (`medicao.py:279-280`). Proposta: a foto deixa de ser exigida no OK e passa a ser exigida só na medição.
3. **O fluxo atual de envio grava evidência errada quando o dono sobe depois.** O navegador manda como data o `lastModified` do arquivo exportado e como GPS a posição do computador de quem envia (`web/app.js:929-931`).
   - No laboratório, uma foto do dia 05/10 enviada em 20/10 ficou registrada com `data_hora` 2026-10-20, coordenadas do escritório, origem DISPOSITIVO e GPS NAVEGADOR.
   - Ela apareceu no Diário de 20/10, não no de 05/10.
4. **O Telegram remove o EXIF.** A única data confiável é a da mensagem, e o código não tem essa origem (cai em "DISPOSITIVO", `servicos.py:1639-1640`).
   - A data da mensagem é um limite superior: a foto não pode ter sido tirada depois de postada.
   - Isso permite regras de coerência novas. Exemplo: foto de "concluído" postada antes do reaterro registrado indica alvo errado.
5. **Upload.** O servidor não tem teto de tamanho do corpo do pedido (`server.py:875-877`, `nuvem.py:138-139`). O pico de memória medido é cerca de 5,7 vezes o tamanho da foto.
   - Uma foto do Telegram tem uns 180 KB e gera pico de ~1,4 MB. O caminho atual (JSON com base64, uma foto por pedido) serve.
   - ZIP não serve no PythonAnywhere (seção 3.5).
6. **Importação proposta: no navegador.** O dono escolhe a pasta exportada. O sistema sugere o alvo pela legenda, pelo remetente (equipe), pelo que a equipe fez no dia e pelo segmento da NS (que leva ao trecho físico).
   - Sobem só as fotos necessárias, uma por pedido, por uma rota nova e idempotente `/api/foto/telegram`.
   - Há um protótipo testado com os nomes reais (seção 8).
7. **Telas de campo.** Sai o envio de foto do Lançamento do dia. O Diário passa a mostrar as fotos importadas pela data da mensagem.

## 1. O que depende de foto hoje

### 1.1 Regras e telas

"Verificado" = reproduzido no laboratório.

| Onde | Regra hoje | Com fotos do Telegram semanas depois | O que mudar |
|---|---|---|---|
| `regras.py:155-170` (`FOTOS_TRECHO`, `FOTOS_ELEMENTO`, `fotos_pendentes`) | Trecho exige 3 fotos (SINALIZACAO, EXECUCAO, CONCLUIDO). Nó exige 2, com a sinalização herdada do trecho. | A categoria passa a vir da legenda. Na travessia em semicírculo, TR007 (2,51 m) e TR006 pediriam 3 fotos cada. | Exigir as fotos por **trecho físico**, somando as fotos das linhas-membro. |
| `servicos.py:265-284` (`FOTO_VALIDA`, `_sinalizacao_herdada`, `fotos_faltando`) | A herança da sinalização não confere data (D-13, `docs/DECISOES_PENDENTES.md:33`). | A data da mensagem permite aplicar a janela (mesmo dia ±1). | Idem, mais o trecho físico. |
| `regras.py:179-185` e `servicos.py:1742-1752` | OK recusado: "OK Fiscalização exige as fotos obrigatórias" (verificado). | OK, esteira e proposta esperam o upload. A medição sai pela data do OK. | OK sem foto (R1). |
| `web/app.js:339` e `357-359` | Checkbox do OK desabilitado sem foto, com o texto "Exige 100 % reaterrado e as fotos". | Igual ao item acima. | Idem. |
| `regras.py:188-198` e `servicos.py:2364-2372` | `CONCLUIDO_MES` só com as fotos; sem foto, fica `EM_EXECUCAO`. | Trecho 100 % reaterrado aparece laranja ("faltando foto") por semanas (verificado). | Status sem foto; foto vira camada própria. Legendas em `web/index.html:565-566`, `web/mapa_iluminado.js:8-9,19-20`, `web/iluminado.js:106-113,358,372,379`. |
| `servicos.py:2035-2040` | PENDENTE "Faltam … (exigidas no OK interno)" (verificado); ALERTA para foto inválida. | Texto e momento errados. | "Faltam para a medição". |
| `servicos.py:1952` | "Entra na esteira com o OK interno (trecho 100 % reaterrado e fotos)". | Texto errado. | Tirar "e fotos". |
| `medicao.py:165-169` | APTO_SEM_OK tem o impedimento "fotos obrigatórias" (verificado). | Deixa de ser impedimento do OK. | Campo novo "evidência para a medição", também para PROPOSTO_NESTA. |
| `medicao.py:214-218`, `248-250`, `279-280` | Retrato com fotos válidas e faltando; impeditivo; CONFORME recusada. | Passa a ser a trava principal. | Manter, somar por trecho físico e mostrar a origem (mensagem do Telegram). Falta uma saída para foto que nunca vai existir (R3). |
| `relatorios.py:131-135,160` e `web/app.js:1087` | "Concluídos sem fotos" só conta quem não tem OK. | Com OK dado sem foto, o trecho some do relatório. | Contar "sem fotos para a medição" até a medição fechar. |
| `exportar.py:141-143,158` | Aba CONFERÊNCIA mostra fotos válidas e faltando. | Sem origem. | Acrescentar origem e mensagem. |
| `regras.py:239` | Roteiro EVIDENCIAS. | Texto não cita o Telegram. | Ajustar o texto. |
| `diario.py:67-72,89`, `web/app.js:1291-1305`, `web/index.html:197` | Fotos do dia por `substr(data_hora,1,10)`; equipe pelos lugares onde trabalhou. | Dia da postagem (à noite ou no dia seguinte). Diário recente fica vazio; dias passados se preenchem depois. | Equipe pelo remetente; rótulo "importadas". |
| `server.py:648` (`"/api/foto": "campo"`) e `config/perfis.json:14` | EQUIPE, SUPERVISOR e ALMOXARIFADO enviam foto. | Quem sobe é o dono. | Permissão nova `fotos_medicao` (R10). |
| `servicos.py:2322` e `importacao.py:245-247,1108` | Foto conta como histórico do alvo. | Sem mudança. | — |

### 1.2 Linha a linha de `registrar_foto` (`servicos.py:1607-1662`)
- **1617, `alvo(..., operacao=True)`:** se o trecho ou nó foi retirado da revisão entre a execução e a importação, a foto tardia é recusada. Precisa de decisão (R11).
- **1618, categorias:** são fixas, com CHECK em `schema.sql:560`. Categoria nova exige recriar a tabela (como na v17).
- **1620-1625, limite:** base64 e `LIMITE_FOTO` de 20 MB (`servicos.py:1547`).
- **1627, `imagens.validar`:** a foto comprimida do Telegram é sempre JPEG e passa como "DECODIFICADA (Pillow)" (verificado). Imagem enviada "como arquivo" de iPhone pode ser HEIC e é recusada (`imagens.py:163-164`).
- **1630-1634 (e índice único em `servicos.py:64-65`), SHA-256 único:**
  - Reimportar a mesma exportação dá erro 422 a cada foto (verificado). Na importação, isso deve virar "já importada".
  - Mensagem encaminhada no grupo tem os mesmos bytes e é recusada. Isso é bom: evita reuso de foto.
  - Em compensação, a mesma foto não pode servir às duas linhas de um trecho físico.
- **1635-1648, data e GPS:** a data vem do EXIF, senão do aparelho (`data_hora`), senão do envio; o GPS vem do EXIF, senão do navegador.
  - A foto do Telegram não tem EXIF, então a data só pode ser a da mensagem.
  - O GPS do navegador de quem importa nunca pode ser usado.
  - `exif_jpeg` (`servicos.py:1550-1604`) continua útil para imagem enviada "como arquivo". No Android, o GPS pode sumir mesmo assim.
- **1649, carimbo:** `regras.py:173-175` monta "CT … | trecho | 2026-10-05T10:02:10 | GPS indisponível" e não diz que é a data da mensagem.
  - Não existe carimbo gravado em `imagens.py`. O carimbo é só texto sobre a foto (`web/app.css:246-247`, `web/app.js:850,1304-1305`).
  - `imagens.py` só valida (`imagens.py:158-176`) e gera miniatura (`imagens.py:142-155`).
- **1656-1660:** não há colunas para chat, mensagem nem remetente.

### 1.3 Arquivos, Drive e backup
- **Miniatura (`imagens.py:142-155`, 640 px, qualidade 70).**
  - Medi com recortes do satélite do mapa REV02 reduzidos a 1280 px, qualidade 82, como substituto de foto de campo. Ainda não medi com foto real.
  - O "original" do Telegram ficou com ~184 KB e a miniatura com ~38 KB. Para 8.000 fotos, ≈ 297 MB. O documento estimava 25 KB e 200 MB (`docs/GOOGLE_DRIVE.md:16-21`).
  - Com 480 px e qualidade 60: ~18 KB, ≈ 138 MB. Com 320 px: ~8 KB.
- **Destino no Drive (`drive.py:352-365`):** usa `data_hora` e o nome do alvo, e funciona com a data da mensagem (verificado: "…PB01_Rede_TR001 - Execução - 2026-10-05 10h02 (a18582c4).jpg").
- **Fila do Drive (`drive.py:386-474`):** envia 4 arquivos por chamada, em até 25 s. Hoje é disparada pelo navegador depois de cada foto (`web/app.js:933,1200-1208`). No PythonAnywhere há um só worker, e o site espera durante o envio. Na importação, chamar a fila em lotes.
- **Liberação do original na v16 (`drive.py:477-500`):** a conferência pelo MD5 funciona igual. Mas o "original" guardado já é a cópia recomprimida do Telegram, então a liberação economiza ~80% por foto, não ~98%. O verdadeiro original fica no Telegram e na pasta exportada.
- **Backup (`backup.py`):**
  - `backup.py:173-205` exige a miniatura de cada foto que está só no Drive.
  - `backup.py:247-259` copia a pasta `fotos/` inteira, miniaturas inclusive, em CADA backup. `importar.py:208-224` faz um backup completo antes da importação.
  - Com ~300 MB de miniaturas, um backup sozinho não cabe nos 512 MiB.
- **Cache (`server.py:713-714` e `867-872`):** `/fotos/` é servido com `no-store`, então cada tela baixa as fotos de novo. Como o nome do arquivo é o SHA-256, dá para usar cache imutável.
- **`revalidar_fotos`** (`servicos.py:1665-1681`, `importar.py:134`): não muda, porque só olha fotos com `validacao` vazia.

## 2. Limites de upload

**No servidor**
- `server.py:875-877` (`_ler_corpo`) lê o `Content-Length` inteiro, sem teto, e só aceita JSON.
- `server.py:1029` duplica o corpo (`json.loads(json.dumps(body))`).
- `acesso.py:342-343` calcula o hash do corpo inteiro, base64 incluído, para a chave de reenvio.
- `acesso.py:29` tira `conteudo_b64` da auditoria (correto).
- `nuvem.py:138-139` (WSGI) lê o corpo inteiro para um `BytesIO`.
- O único 413 do projeto é o do assistente da primeira abertura (`iniciar.py:173-174`).

**Formato de `/api/foto`** (`server.py:320-322`, `web/app.js:917-931`)
- JSON `{alvo_tipo, alvo_id, categoria, conteudo_b64, data_hora?, lat?, lon?}`. O navegador lê com `readAsDataURL` e corta o prefixo.
- Cabeçalhos `X-MC: 1` (`server.py:885`) e `X-Idem`.
- `api()` (`web/app.js:98-113`) usa o corpo inteiro, com o base64, como chave de um Map. Gera um `X-Idem` aleatório e tenta mais 2 vezes com a mesma chave.

**Pico de memória medido no caminho do servidor (com as cópias)**

| Foto | Corpo JSON | Pico |
|---|---|---|
| 0,25 MB | 0,33 MB | 1,4 MB |
| 3 MB | 4 MB | 17 MB |
| 21 MB | 28 MB | 119 MB |

O tempo de servidor por foto do Telegram é de ~26 ms em `registrar_foto` e ~22 ms na miniatura.

**PythonAnywhere grátis**
- Pelo `docs/NUVEM.md`, conferido em 18/10/2026: 512 MiB de disco, um pedido por vez (1 worker) e renovação mensal.
- Pela busca (não consegui abrir a página oficial): 100 s de CPU por dia nos consoles; contas novas sem tarefa agendada.
- Pelos fóruns (respostas da equipe, não documentação): 413 acima de ~100 MB por pedido e ~5 min por pedido.
- Já ocupados: clone com `.git` (~50 MB), banco de 22,5 MB, backups e logs de até 12 MB.

**Recomendação**
- 413 explícito (por exemplo, 25 MB) antes de ler o corpo, em `server.py` e em `nuvem.py`.
- Conferir `file.size` no navegador antes de ler o arquivo.
- Uma foto por pedido.

## 3. Importação do export do Telegram Desktop

### 3.1 Formato
Conferido no código-fonte do Telegram Desktop.
- **`result.json`:** `{name, type ("private_supergroup"…), id (id puro), messages[]}`.
- **Cada mensagem:**
  - `id`, `type` ("message" ou "service").
  - `date`: hora local do computador que exportou, sem fuso.
  - `date_unixtime`: UTC, como texto. É a fonte certa da data.
  - `edited`, `from`, `from_id` ("user<n>").
  - `forwarded_from` e `forwarded_from_id`: não trazem a data original.
  - `reply_to_message_id`; `text` (texto, ou lista de texto e `{type, text}`); `location_information`.
- **Foto comprimida:** `photo: "photos/photo_N@dd-MM-yyyy_HH-mm-ss.jpg"`, `photo_file_size`, `width`, `height`. É o maior tamanho, sempre `.jpg`, sem EXIF.
- **Imagem "como arquivo":** `file: "files/<nome original>"`, `file_name`, `file_size`, `mime_type`, `thumbnail`. Mantém o EXIF.
- **Arquivo não exportado:** o campo traz "(File not included…)", "(File exceeds maximum size…)" ou "(File unavailable…)".
- **Não existe `grouped_id` nem `media_group_id`.** O álbum só se reconhece por heurística: mesmo remetente, ids seguidos, até 2 s de diferença.
- **Como orientar o dono a exportar:**
  - Formato "Machine-readable JSON".
  - Marcar Fotos, e Arquivos se as equipes mandam "como arquivo".
  - Período da medição mais uns 3 dias.

### 3.2 Leitura no navegador
- Botão `<input type="file" webkitdirectory>` (navegadores de computador) ou arrastar a pasta. Alternativa: escolher o `result.json` e as fotos e casar pelo nome.
- Tudo é lido localmente; nada sobe antes da confirmação. A miniatura para conferência sai de `URL.createObjectURL`.
- SHA-256 calculado no navegador (`crypto.subtle`, que exige https ou localhost). Um contexto vindo do servidor diz o que já foi importado, e essas fotos são puladas sem enviar nada.

### 3.3 Sugestão de alvo, calibrada nos nomes reais
**Por que a legenda sozinha não basta**
- TR001 existe em 70 trechos.
- O mesmo par PB+TR se repete entre zonas (PB01_TR001 existe na Zona01 e na Zona04).
- NÓ2.1 aparece 22 vezes.
- VRP-15 é único; DF-33 aparece 2 vezes (frentes Rede e CH).

**O que a sugestão combina**
- **Legenda:** Zona, PB, TR, NÓ, CH, NS, estaca, categoria e segmento.
- **Remetente:** tabela que liga o remetente à equipe; a equipe dá a zona.
- **Dia:** check-in, programação e intervalos da equipe no dia ±1.
- **Medição:** o que falta de foto nela.
- **Segmento da NS:** leva ao trecho físico (`topologia.trechos_fisicos`).

**Resultado no protótipo, com 13 fotos sintéticas:** 8 ALTA, 1 MÉDIA, 2 AMBÍGUAS e 2 sem sugestão.
- "NS 012 NÓ9.1 até VRP-15" foi para TR007 + TR006 (295,98 m), o exemplo do dono.
- "tr 7" de alguém da Zona03 foi para Zona03_PB08_Rede_TR007, pela agenda do dia.
- Fotos encaminhadas, não exportadas e em HEIC aparecem marcadas.

### 3.4 Envio
- **Rota nova `/api/foto/telegram`**, com permissão `fotos_medicao` e autoria `importada_por`. Ela reaproveita `registrar_foto`.
  - Corpo: `{alvo, categoria, conteudo_b64, telegram:{chat_id, message_id, date_unixtime, de, de_id, legenda, como, encaminhada}}`.
  - O servidor calcula a data em UTC−3 com origem `TELEGRAM`; o EXIF continua tendo prioridade quando a imagem veio "como arquivo".
  - Ignora `lat` e `lon`.
  - É idempotente por (chat, mensagem): repetir devolve `ja_importada`.
- **Contexto da importação:** GET `/api/fotos/contexto?medicao=` com a tela `medicao`. Traz os alvos sem foto, o índice de nomes (~375 KB), a agenda das equipes por dia, os remetentes e as mensagens já importadas ou ignoradas.
- **Fila:** envio sequencial, uma foto por vez, com nova tentativa. A fila do Drive é disparada a cada ~10 fotos.
- **Por que não reaproveitar `/api/foto`:** funciona mandando a data da mensagem como `data_hora`, mas perde a origem, a proveniência e a idempotência.

### 3.5 ZIP: não recomendado no PythonAnywhere
- Um mês de grupo com 13 equipes pode passar de 1 GB, mas a medição só precisa de ~3 fotos por trecho físico e 2-3 por nó (algo como 50 MB).
- O PythonAnywhere recusa pedidos acima de ~100 MB e tem 512 MiB de disco; o ZIP mais as fotos extraídas ocupam o dobro.
- O corpo inteiro vai para a memória (`nuvem.py:139`).
- Há o limite de ~5 min por pedido, com o único worker preso nesse tempo.
- A conferência das fotos pelo dono exigiria guardá-las no servidor antes de confirmar.
- Há o risco de ZIP malicioso.
- **Futuro possível:** um bot no grupo. Não é o que o dono pediu, e não confirmei se o plano grátis libera o `api.telegram.org`.

## 4. Telas de campo
- **Lançamento do dia** (`web/index.html:154-167`; `web/app.js:843-852,910-934`):
  - Tirar o formulário `#fFoto` e o envio dos perfis de campo.
  - No lugar, um painel só de leitura "Fotos (Telegram → medição)" com as fotos importadas e o que falta, que não bloqueia nada.
  - Foto avulsa só para quem tiver `fotos_medicao`, com data informada. Nunca usar `lastModified` nem o GPS do navegador, a não ser que a pessoa marque "tirada agora no local".
- **Diário:**
  - Manter o painel, rotulado "Fotos importadas (pela data da mensagem)", com o aviso "ainda não importadas".
  - KPI "Fotos importadas" (`web/app.js:1292`).
  - Filtrar a equipe pelo remetente (`diario.py:69-72`).
  - Link "abrir no Telegram": `t.me/c/<id>/<mensagem>`.
- **Ficha, Fiscalização e mapa:** OK liberado sem foto; a linha passa a ser "Fotos para a medição".
- **Medição:** painel novo "Fotos da medição (Telegram)":
  1. Exportar o grupo.
  2. Escolher a pasta.
  3. Revisar as sugestões por alvo e categoria (aceitar as ALTA em bloco).
  4. Enviar.

## 5. Mudanças de regra
- **R1. OK interno sem foto** (`regras.py:179-183`, `servicos.py:1752`, `web/app.js:339,359`). Decisão nova; dá para manter um parâmetro `fotos_no_ok` com padrão NÃO.
- **R2. Foto exigida na medição.** Manter `medicao.py:248-250,279-280`. Em `medicao.py:165-169`, a foto vira campo "evidência", não impedimento do OK.
- **R3. Foto que nunca vai existir.** A EXECUÇÃO não se refaz depois do reaterro. Opções:
  - (a) bloquear sempre, como hoje;
  - (b) dispensa justificada pela engenharia, que aparece no retrato e na planilha;
  - (c) adiar o lançamento para a próxima medição. Exige status novo, porque a chave da parcela impede propor de novo (`servicos.py:1715-1723`).
- **R4. Mapa sem foto** (`regras.py:188-198`, `servicos.py:2364-2372` e legendas). A foto vira camada própria.
- **R5. Textos e contagens:** `servicos.py:1952,2035-2036` e `relatorios.py:131-135`.
- **R6. Foto por trecho físico** em `fotos_faltando` (`servicos.py:280-284`) e em `_evidencias` (`medicao.py:214-218`). A linha curta da travessia não exige fotos próprias, e a mesma foto não precisa ser duplicada.
- **R7. Origem TELEGRAM em `registrar_foto`:**
  - Data da mensagem; o EXIF tem prioridade, com alerta se o EXIF for mais antigo que a mensagem por mais de 7 dias.
  - GPS só do EXIF ou de uma mensagem de localização do mesmo remetente; nunca do navegador.
  - Gravar a proveniência e ajustar o carimbo.
- **R8. Idempotência** por (chat, mensagem). O mesmo SHA-256 vindo de outra mensagem continua recusado, com a referência.
- **R9. Coerência de datas,** como ALERTA:
  - CONCLUIDO postada antes do reaterro registrado;
  - EXECUCAO postada antes do primeiro escavado ou assentado, menos 1 dia;
  - foto encaminhada (a data é a do encaminhamento);
  - D-13 com janela de ±1 dia.
- **R10. Permissão `fotos_medicao`** para ENGENHARIA e ADMINISTRAÇÃO. Tirar "fotos" da permissão `campo` (`config/perfis.json:14`) e mudar `server.py:648`.
- **R11. Alvo retirado** depois da execução: decidir se a foto pode ser anexada (`servicos.py:1617`).
- **R12. Teto 413** em `server.py:875-877` e `nuvem.py:138-139`.
- **R13. Miniatura e backup:** miniatura de 480 px com qualidade 60, e backup sem duplicar `fotos/` (`backup.py:173-205,247-259`). O Drive e os hashes guardados no banco fazem o papel de cópia.
- **R14. Cache imutável** para `/fotos/<sha256>` (`server.py:713-714,867-872`).
- **R15. Diário pelo remetente** (`diario.py:67-72`).
- **R16. Fila do Drive em lotes** na importação (`web/app.js:933`).

**Documentos a atualizar:** `README.md:116-117`, `docs/GOOGLE_DRIVE.md:16-21` e `docs/DECISOES_PENDENTES.md` (D-13 na linha 33, D-59 na 68, D-62 na 75, D-65 na 79), além das decisões novas de R1 e R3.

## 6. Esquema sugerido (v18)
- **Tabela `fotos`:** colunas novas por `_add_coluna`, sem recriar a tabela: `origem`, `telegram_chat_id`, `telegram_msg_id`, `telegram_de`, `telegram_de_id`, `legenda`, `encaminhada`, `importada_por`.
- **Índice único** `(telegram_chat_id, telegram_msg_id)`, criado em `aplicar_esquema` como o `ux_fotos_sha`.
- **`telegram_remetentes`:** `from_id` → `equipe_id`.
- **`telegram_decisoes`:** (chat, mensagem) com IMPORTADA ou IGNORADA, `foto_id`, `por` e `em`.
- **Se R3 for a opção (b):** tabela `dispensas_foto`.
- **Categorias:** manter as 3; categoria nova exige recriar a tabela.

## 7. Testes que codificam as regras atuais
- **`tests/test_medicao.py:87,99`:** "fotos obrigatórias" como impedimento. Muda com R1 e R2. `tests/test_medicao.py:130-137` continua valendo.
- **`tests/test_ciclo_zona01.py:260-264,328-329`:** `enc1` envia foto. Quebra com R10. As linhas 341-342 (`CONCLUIDO_MES`) continuam passando com R4.
- **`tests/test_relatorios.py:98-104`:** R5.
- **`tests/test_retificacao_cadastro.py:291`:** texto da pendência "Fotos".
- **`tests/test_campo.py:141-211`:** origens; acrescentar TELEGRAM.
- **`tests/test_fluxo_zona01.py:91-136`:** acrescentar o caso "OK sem foto".
- **Sem mudança:** `tests/test_regras.py:62-70` e `tests/test_drive.py:192-216`.

## 8. Laboratório e rascunhos
- `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/fotos_lab/banco/obra.db`: demonstração montada das planilhas (1.436 trechos, 1.242 atividades). Montada por `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/fotos_lab/montar.py`.
- `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/fotos_lab/experimento.py`: OK recusado, mapa, pendências, elegibilidade, relatórios, fluxo atual com data e GPS errados, reimportação e pico de memória.
- `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/fotos_lab/miniaturas2.py` e `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/fotos_lab/tempo.py`: tamanho das miniaturas e tempo por foto.
- `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/telegram_v2/telegram_import_v2.js`: leitura do export, sugestão e segmento → trecho físico. Roda com `node telegram_import_v2.js result_sintetico.json indice.json contexto_sintetico.json`, arquivos que estão na mesma pasta.
- A v1 já estava no rascunho: `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/telegram_export_proto.js`.

## Fontes externas
- [export_output_json.cpp](https://raw.githubusercontent.com/telegramdesktop/tdesktop/dev/Telegram/SourceFiles/export/output/export_output_json.cpp) e [export_data_types.cpp](https://raw.githubusercontent.com/telegramdesktop/tdesktop/dev/Telegram/SourceFiles/export/data/export_data_types.cpp): formato do export.
- EXIF no Telegram: [fast.io](https://www.fast.io/resources/whatsapp-telegram-signal-photo-metadata-preservation.md); GPS no Android "como arquivo": [bugs.telegram.org/c/19150](https://bugs.telegram.org/c/19150).
- PythonAnywhere: [recursos da conta grátis](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/) (vista só pela busca); fóruns [topic/35833](https://www.pythonanywhere.com/forums/topic/35833/) (100 MB, 413) e [topic/36101](https://www.pythonanywhere.com/forums/topic/36101/) (5 min); [blog sobre bots do Telegram](https://blog.pythonanywhere.com/148/); [allowlist](https://www.pythonanywhere.com/whitelist/).