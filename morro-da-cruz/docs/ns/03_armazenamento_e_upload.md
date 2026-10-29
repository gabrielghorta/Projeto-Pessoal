> Pesquisa de 20/10/2026 para a Nota de Serviço por upload (somente leitura do código). Os caminhos em /tmp são do rascunho da sessão e não existem no repositório; o protótipo citado está em `ferramentas/ns/`.

# NS por upload: onde guardar o PDF, o croqui e a planilha, e o que muda (pesquisa só de leitura)

Não alterei nenhum arquivo do projeto: `git status` está igual ao do início e nenhum arquivo do projeto ficou mais novo. Para testar, copiei o projeto para o scratchpad e rodei a suíte completa nessa cópia, já com o trabalho não commitado: **266 testes OK**, inclusive a migração v16 → v17 do banco de demonstração.

## Resumo
- **Onde guardar:** na tabela `documentos` que já existe, em `<pasta do banco>/documentos/<sha256>.<ext>`, e mandar para a mesma fila do Drive. `documentos_obra` não serve: ela guarda só links do Drive.
- **Leitura do PDF:** com pypdf no modo layout, a NS assinada sai **vazia**, porque a página tem `/Rotate 90`. É preciso chamar `page.transfer_rotation_to_content()` antes de extrair.
- **Croqui:** nunca extrair texto do croqui com pypdf no servidor. Medi 24–28 s e cerca de 150 MB, contra 7 ms para só abrir e ler os metadados.
- **Duplicidade:** o SHA-256 sozinho não basta. A NS assinada e a reimpressa têm hashes diferentes e conteúdo lido idêntico.
- **Contrato:** a NS de exemplo é do contrato 9702/2024 e esta obra é o CT 10239/2026. A NS de exemplo tem que ser recusada.
- **Migração:** a v17 ainda não foi publicada. Convém juntar as tabelas da NS na mesma v17, porque o banco oficial na nuvem só migra à mão, com o site parado (`nuvem.py:100-102`).

## 1. Onde guardar e o ciclo de vida

### Como é hoje
- **`documentos_obra`** (`schema.sql:920-942`, `documentos.py:1-10`) é só um catálogo de links do Drive: o arquivo não vem para o servidor. A tela saiu em 19/10/2026 (`docs/GOOGLE_DRIVE.md:75`). Não serve para a NS.
- **`documentos`** (`schema.sql:718-729`; o CHECK do tipo está na linha 722) guarda o arquivo byte a byte:
  - `guardar_documento` (`compras.py:44-75`) nomeia o arquivo pelo SHA-256 e, se o mesmo hash já existe, devolve o id que já existe (`compras.py:63-66`).
  - O tipo é conferido pelos primeiros bytes do arquivo (`compras.py:32-41`, mapa de extensões esperadas em `:55`).
  - Limite de 20 MB (`compras.py:27`, conferido em `:52`).
  - A pasta é `documento_dir` (`compras.py:324-329`).
- **Fila do Drive:**
  - `envios_drive` (`schema.sql:944-964`) aceita origem FOTO ou DOCUMENTO e tem UNIQUE(origem, ref_id).
  - `sincronizar_fila` põe na fila **toda** linha de `documentos` (`drive.py:386-404`).
  - Pasta e nome vêm de `_destino_documento` (`drive.py:368-383`) com `DOC_ROTULO`/`DOC_PASTA` (`drive.py:42-45`). Um tipo novo cairia em `04_COMPRAS_E_ALMOXARIFADO/99_Outros_Documentos/<AAAA-MM>`.
  - `processar` (`drive.py:411-474`) envia até 4 arquivos por vez, com a rede fora da trava do banco.
  - O nome no Drive leva o começo do hash, então reenviar reaproveita o arquivo que já está lá (`drive.py:291-294`).
- **Liberar o disco:** hoje só a foto sai do servidor. `_liberar_foto` (`drive.py:477-500`) confere o MD5 do Google e o SHA-256 antes de apagar, e grava em `fotos_no_drive` (`schema.sql:965-977`). A regra atual diz "Notas e laudos … nunca saem do servidor" (`drive.py:480`).
- **Backup:**
  - `ANEXOS` cobre fotos e documentos (`backup.py:165`).
  - A cópia leva todos os arquivos da pasta (`backup.py:247-259`).
  - A completude e o hash são conferidos em `backup.py:180-205`, e a foto liberada vira a miniatura (`backup.py:173-177`).
- **Mostrar o arquivo:** não existe rota GET que entregue arquivo de `documentos`. O servidor só serve `/fotos/` e `/arquivos/` (`server.py:858-872`), e a tela usa o link do Drive (`app.js:1195-1198`).
- **Painel do Drive** (`index.html:635-653`, `app.js:1210-1238`): tudo que não é foto aparece como "NOTA" (`app.js:1221`).

### Proposta
1. **Tabela e pasta.** Reaproveitar `documentos` com três tipos novos: `NS_PDF`, `NS_PLANILHA` e `NS_CROQUI`.
   - O CHECK de `documentos.tipo` muda. A tabela é recriada com o ajudante que já existe, `importacao._recriar_tabela(conn, "documentos", "NS_PDF")` (`importacao.py:999-1020`).
   - Atualizar `TIPOS_DOC` (`compras.py:28`).
   - `_tipo_arquivo` passa a reconhecer `.xls` (começa com `D0 CF 11 E0 A1 B1 1A E1`) e `.xlsx` (começa com `PK\x03\x04` e tem `xl/workbook.xml`).
   - Se o hash já existe com outro tipo, recusar.
   - Com isso, backup, conferência de hash e fila do Drive passam a valer para a NS sem outra mudança.
2. **Cabeçalho da NS.** Tabela nova `notas_servico` com:
   - serviço (TOPOGRAFIA, CADASTRO ou CAMPO), contrato, número, folha e data;
   - os ids do PDF, da planilha e do croqui em `documentos`;
   - versão, `substitui_id` e se é a versão assinada;
   - de onde vieram os dados (PLANILHA, PDF_TEXTO ou DIGITADO), `extrator` e `texto_extraido`;
   - o que foi lido e o que a pessoa confirmou, ambos em JSON;
   - status (REGISTRADA, SUBSTITUIDA ou ANULADA) e anulação com motivo.
   - Índice único só para a NS vigente: `(numero, folha[, servico]) WHERE status='REGISTRADA'`.
   - De onde veio cada registro: coluna `ns_id` em `intervalos_execucao` e em `etapas_complementares`, com `_add_coluna` (`importacao.py:867-869`).
   - Pôr 'NOTA_SERVICO' no CHECK de `retificacoes_intervalos.ref_tipo` (`schema.sql:504`) **agora**, porque a v17 já recria essa tabela (`importacao.py:1079-1096`).
3. **Drive.**
   - Somar ramos NS a `DOC_ROTULO`, `DOC_PASTA` e `_destino_documento`. Pasta: `03_EXECUCAO_DE_CAMPO/02_Notas_de_Servico/<Topografia|Cadastro|Servicos>/<Zona>`. Nome, por exemplo: `Morro da Cruz - NS 006 fl 01 - Topografia - Zona04 PB06 - 2025-10-27 - Nota de Serviço (ea1178d1).pdf`.
   - Em `sincronizar_fila`, pôr na fila só o arquivo NS que já está ligado a uma NS registrada. Assim um envio abandonado não vira arquivo solto no Drive.
   - No painel, mostrar o tipo do documento (juntar `documentos.tipo` na consulta de `drive.py:536-539` e trocar o rótulo em `app.js:1221`).
   - Depois do registro, chamar `driveEmSegundoPlano()`, como já se faz após a nota fiscal (`app.js:672`, `:678`).
4. **Manter ou liberar a cópia do servidor.**
   - **PDF da NS e planilha: manter.** São a fonte dos intervalos registrados e a evidência do item do BM 2.2_5.2.7 "LOCAÇÃO E NIVELAMENTO … NOTA DE SERVIÇOS" (`config/servicos_rede.json:13`).
   - **Croqui: liberar** depois que o Drive confirmar os mesmos bytes, como na foto, mas sem miniatura. Isso pede:
     - tabela `documentos_no_drive`;
     - uma função `_liberar_documento`, chamada ao lado de `drive.py:470-471`;
     - estender a consulta `so_no_drive` (`drive.py:430`);
     - em `backup.py:173-205`, não exigir o documento liberado.
   - Guardar `texto_extraido` no banco permite, mais tarde, liberar também o PDF da NS (com um parâmetro) se o disco apertar.
   - **Contas de disco:** o plano grátis tem 512 MB e cada backup copia tudo de novo (`docs/NUVEM.md:20`, `:92`). Pelos tamanhos das amostras, cada 100 NS ocupam:

     | Versão do PDF da NS | Guardando tudo | Liberando o croqui |
     |---|---|---|
     | Assinada (Ghostscript, 193 KB) | 75,6 MB | 19,3 MB |
     | Reimpressa (Microsoft Print to PDF, 588 KB) | 115 MB | 58,8 MB |

     O croqui tem 563 KB. A rede tem 1.436 linhas na 06.1, cerca de 110,7 km e 67 combinações zona × PB (contei pela coluna M do dump `mapa_scripts/rede061.json`): são centenas de NS. Pedir a versão assinada original, que é três vezes menor.
5. **Duplicidade.**
   - Mesmo arquivo: se o hash já está ligado a uma NS, recusar com "já registrada como NS 006 em …".
   - Mesma NS em arquivo diferente: a chave é contrato + número + folha. Isso está comprovado na amostra: `ns.pdf` (sha256 ea1178d1…) e `topografia.pdf` (sha256 67b59e3e…) dão leitura idêntica.
   - Nesse caso, oferecer "nova versão (assinada ou revisada)". A anterior fica SUBSTITUIDA. Se a leitura for igual, só o arquivo muda; se for diferente, os registros são refeitos com retificação NOTA_SERVICO.
   - **Decisão pendente:** se a numeração da NS é por contrato ou por serviço. Isso define se o serviço entra na chave.
6. **Tamanho máximo.**
   - PDF da NS: 5 MB e até 20 páginas.
   - Planilha: 5 MB.
   - Croqui: 15 MB.
   - Um envio por arquivo: o croqui vai numa rota de anexo à parte, que também permite anexá-lo depois.
7. **Quem envia.**
   - Permissão nova `notas_servico` ("Enviar notas de serviço e croquis"), dada à ENGENHARIA e à ADMINISTRACAO (`config/perfis.json:46-53`).
   - Ao confirmar, o servidor exige também a permissão do serviço: `topografia` ou `cadastro_campo` (`perfis.json:15-16`), do mesmo jeito que `server.py:1032-1035` já faz.
   - Os perfis TOPOGRAFIA e CADASTRO continuam só de consulta (`perfis.json:60-61`), porque a terceirizada não entra no sistema.
   - As consultas GET entram em `TELA_GET` (`server.py:678-688`) com as telas `topografia`, `cadastro_campo`, `campo` e `medicao`.
8. **Mostrar o arquivo.**
   - Na conferência, o navegador mostra o próprio arquivo escolhido (`URL.createObjectURL(file)`), sem ida ao servidor.
   - Depois do registro: rota nova `GET /api/ns/arquivo?id=` com `inline`, `Content-Security-Policy: sandbox` e `nosniff`. O arquivo é lido fora da trava, como em `/fotos/` (`server.py:867-872`). Se o arquivo já saiu do servidor, a rota redireciona para o link do Drive.
9. **Auditoria.**
   - Chamar o campo do arquivo de `conteudo_b64` ou `arquivo_b64`, ou somar o nome novo a `CAMPOS_OCULTOS` (`acesso.py:29`).
   - **Falha que já existe:** `documento_b64` (`server.py:554`, `:562`) não é ocultado. A auditoria de `/api/nf/digitar` e de `/api/inspecao` guarda até 20.000 caracteres do base64 (`acesso.py:313-328`).

## 2. Como o servidor recebe arquivos hoje
- **No navegador:** `FileReader.readAsDataURL` transforma o arquivo em base64 (`app.js:917-924`). O envio é um POST JSON com os cabeçalhos X-MC e X-Idem (`app.js:98-113`). Exemplos: XML da NF-e (`app.js:669-673`), NF digitada com o PDF (`:674-679`), foto (`:925-934`).
- **No servidor:**
  - `_ler_corpo` lê o Content-Length inteiro e faz `json.loads`, **sem limite de tamanho e sem multipart** (`server.py:875-877`).
  - O adaptador WSGI da nuvem também lê o corpo inteiro (`nuvem.py:138-139`).
  - `_gravar` (`server.py:1021-1060`) roda tudo dentro da trava global `LOCK` (`:1025`) e copia o corpo inteiro uma vez (`:1029`).
  - O hash de reenvio é calculado sobre o corpo inteiro (`acesso.py:342-355`).
- **Limites que existem**, só depois de decodificar:
  - documento: 20 MB (`compras.py:27`, `:52`);
  - foto: 20 MB (`servicos.py:1547`, `:1624`);
  - XML da NF-e: 5 MB (`nfe.py:20`, `:49`).
- **NF:**
  - `/api/nf/importar-xml` → `importar_nfe_xml` (`compras.py:262-284`): lê o XML com segurança (`nfe.py:51-52`), confere duplicidade pela chave, chama `guardar_documento` na mesma transação e a nota fica A_CONFERIR.
  - `/api/nf/digitar` (`compras.py:287-321`): o anexo é obrigatório e outra pessoa confere.
- **Padrão para a NS:**
  - `POST /api/ns/ler`: só leitura, não grava arquivo.
  - `POST /api/ns`: reenvia o PDF e a grade corrigida. Grava `documentos`, `notas_servico` e os registros numa só transação, usando a mesma ideia de "simular" de `server.py:297-300` e `:473-475`.
  - `POST /api/ns/anexo`: o croqui.
  - Validar todas as linhas e devolver os erros com o número da linha, como `importar_indice` faz (`documentos.py:323-327`).
- **Multipart não compensa:** o módulo `cgi` não existe no Python 3.13 (conferi: `ModuleNotFoundError`). Manter JSON com base64.
- **Limite novo:**
  - Recusar com 413 acima de cerca de 32 MB, antes de ler o corpo, em `_ler_corpo` **e** em `nuvem._pedido`. Uma foto de 20 MB em base64 tem cerca de 26,7 MB, então cabe.
  - No PythonAnywhere, o fórum fala em 100 MB por upload; não é fonte oficial e não consegui conferir.
  - No PythonAnywhere atende "um pedido por vez" (`docs/NUVEM.md:24`).

## 3. Extração de texto no PythonAnywhere
- **pdftotext:** **não consegui confirmar.** O proxy desta máquina recusou pythonanywhere.com (CONNECT 403) e a busca não achou fonte oficial. Não depender dele.
  - Testar no console: `which pdftotext; python3.13 -c "import pypdf, xlrd"`.
  - Usar só se existir (`shutil.which`), como conferência opcional.
  - No croqui, o pdftotext leva 0,2 s e acha "N.S.006" e "9702/2024" no carimbo. As etiquetas dos PVs saem embaralhadas.
- **pypdf:**
  - Puro Python, sem dependências no Python 3.11 ou mais novo. O pacote baixado tem 405 KB; instalado ocupa cerca de 3,8 MB.
  - Testado nas versões 6.17.0 e 6.21.1.
  - NS assinada (Ghostscript, `/Rotate 90`): modo layout devolve **0 caracteres** ("Rotated text discovered"), mesmo na 6.21.1. Com a correção abaixo, a leitura fica igual à do `pdftotext -layout` nas duas versões da NS 006:
    - 8 linhas, 6 segmentos e 2 grupos;
    - NS 006, contrato 9702/2024, folha 01 de 01, data 27-out-25, total 70,71 m;
    - cerca de 0,1 s na assinada; 0,8 s em layout na reimpressa.
  - A correção:
    ```python
    if page.get("/Rotate", 0): page.transfer_rotation_to_content()
    texto = page.extract_text(extraction_mode="layout")
    ```
  - Na reimpressa (Microsoft Print to PDF, sem rotação) funciona direto.
  - Esquisitices do layout: "006NS nº :", "01 de 01FOLHA:", "…(PV.3 - PV.2 e PV.1)40,22 metros". As expressões do cabeçalho precisam aceitar o valor antes ou depois do rótulo.
  - Não usar o modo simples: ele joga os títulos dos grupos para o fim do texto.
  - Silenciar o aviso de fontTools com o logger `pypdf`.
  - O título nos metadados traz o nome da planilha original (`N.S.006_TP-EMISS\301RIO….xls`), útil para conferir o número.
- **Croqui:** extrair texto com pypdf leva 24–28 s e cerca de 150 MB e travaria o único worker. Fazer só a validação barata: primeiros bytes, número de páginas, tamanho da página e título (cerca de 7 ms).
- **Planilha:**
  - `.xls` precisa de `xlrd>=2.0.1` (2.0.2, 96 KB, puro Python), importado só quando necessário e com aviso se faltar.
  - `.xlsx` já é lido pelo openpyxl.
- **Estratégia de leitura:**
  1. Planilha, se vier (valores exatos).
  2. Camada de texto do PDF com pypdf e a correção da rotação, com pdftotext como conferência se existir.
  3. Grade de conferência **sempre**, com o PDF ao lado.
  - PDF escaneado: preencher só o cabeçalho; não há OCR.
  - Contrato diferente do desta obra (102392026 × 97022024, comparando só os dígitos): aviso vermelho na leitura e recusa (422) ao registrar.
- **Onde instalar:**
  - `requirements.txt` (`pypdf>=6,<7`, `xlrd>=2.0.1,<3`);
  - `instalar_pythonanywhere.sh:20-24` (hoje instala para 3.11, 3.12 e 3.13; instalar só na versão do site economiza disco);
  - `ABRIR_SISTEMA.bat:14`;
  - `README.md:6`, `:33`, `:42`;
  - `/home/user/projeto-pessoal/.github/workflows/morro-da-cruz-windows.yml:24`, `:40`;
  - `MorroDaCruz.spec:9`: o import estático já resolve.

## 4. Trabalho não commitado: o que fica, o que muda, o que sai

| Peça | Onde | Veredito |
|---|---|---|
| Permissões `topografia` e `cadastro_campo`, telas | `perfis.json:15-16, 31-32, 48, 52` | Fica, mas mudar o texto para "enviar/confirmar NS"; somar `notas_servico` |
| Perfis TOPOGRAFIA e CADASTRO só de consulta | `perfis.json:60-61` | Fica como está |
| LEV e Medição dentro do Administrativo | `perfis.json:42-43`; `index.html:53-54`; `app.js:155-156, 217-221` | Fica como está |
| v17: CHECK `ref_tipo` + CADASTRO_CAMPO | `schema.sql:497-511`; `servicos.py:28, 68-69`; `importacao.py:1079-1096`; `importar.py:124-125` | Fica, mas mudar: juntar na mesma v17 os tipos NS de `documentos`, `notas_servico`, `documentos_no_drive`, `ns_id` e NOTA_SERVICO; usar `_recriar_tabela` |
| `registrar_cadastro_campo`, `_gravar_intervalos` devolvendo ids, referência obrigatória | `servicos.py:945-985` | Fica, mas mudar: vira função interna chamada para cada linha da 06.1 pela confirmação da NS (mesma transação, SAVEPOINT em `servicos.py:98-100`); recebe `ns_id` e referência gerada "NS 006 fl. 01/01" |
| Retificação do CADASTRO_CAMPO avulso, também depois do OK | `servicos.py:804-813, 1142-1150, 1194, 1210-1221, 1295-1296, 1349` | Fica como está |
| Bloqueio de CADASTRO_CAMPO no apontamento do encarregado | `server.py:1032-1035` | Fica como está |
| GET `/api/topografia` e `/api/cadastro-campo` + `terceirizadas.py` | `server.py:442-447, 622-623, 686-687`; `terceirizadas.py:44-144` | Fica, mas ampliar: lista "NS recebidas" com link e situação no Drive; em "recentes", mostrar o nº da NS no lugar do texto livre |
| POST `/api/cadastro-campo` e `/api/liberacao` chamados pela tela | `server.py:450-452, 635, 638, 654-655, 663` | Mudar: deixam de ser o caminho da tela; ficam as funções de serviço; as rotas podem sair quando a NS estiver coberta por testes |
| Formulários digitados fTop e fCad, botões "Trecho todo" e "Só o que falta" | `index.html:257-267, 289-300`; `app.js:1446-1460, 1524-1537` | Sai: trocar por "Enviar nota de serviço" (PDF obrigatório, planilha e croqui opcionais) → grade → Registrar; manter `#cadRetif` (`index.html:301`) |
| Abas, menu lateral, indicadores e listas | `index.html:36-37, 241-256, 272-288`; `app.js:144-145, 1379-1445, 1462-1523` | Fica como está |
| Ficha do trecho: topografia e cadastro só para leitura, escavação continua | `app.js:58-78, 743-749` | Fica; somar o link da NS |
| Lançamento do dia sem cadastro de campo | `index.html:143-147`; `app.js:870-872` | Fica; o texto da linha 144 deve dizer "pela NS"; o campo "Estaca (NS)" da linha 147 pode virar escolha de linha da NS |
| `ROT_REGISTRO` e `ctxRetif` | `app.js:36-48, 807-808` | Fica; somar o rótulo NOTA_SERVICO |
| Diário: equipe vazia = terceirizada | `diario.py:80`; `app.js:1297` | Fica como está |
| Testes alterados | `tests/test_ciclo_zona01.py:246-256, 289-300, 327` | Ficam; somar testes da NS: contrato errado recusado (usar a NS 006), versão assinada substituindo, arquivo repetido e tamanho |

## Arquivos de trabalho
Estão em `/tmp/claude-0/-home-user-projeto-pessoal/e91b97ac-c694-57f7-a186-dad2dc7e7934/scratchpad/ns006/`:
- **Scripts** (pasta `armazenamento_scripts/`): `extrair_pypdf.py`, `rotacao_pypdf.py`, `abrir_barato.py`, `ler_ns_prova.py`.
- **Saídas** (pasta `armazenamento_saida/`): textos extraídos de cada PDF e o resultado dos testes, em `testes_completos.txt`.

## Fontes
- [Fórum do PythonAnywhere: limite de upload](https://pythonanywhere.com/forums/topic/11785)
- [Fórum do PythonAnywhere: upload pelo site](https://www.pythonanywhere.com/forums/topic/35833/)
- ["Batteries included" do PythonAnywhere](https://pythonanywhere.com/batteries_included): não consegui ler pelo proxy.