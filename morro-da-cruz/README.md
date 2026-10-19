# Sistema de Gestão e Mapa Iluminado — Morro da Cruz (Ankara Engenharia)

Aplicação web **privada e local** da obra *Implantação de Redes de Distribuição no Morro da Cruz,
São Sebastião/DF*, Contrato Caesb × Ankara nº 10239/2026, LC 014/2026.

- Tecnologia: Python (biblioteca padrão + `openpyxl`; `pillow` opcional, para o satélite do Mapa iluminado), banco SQLite e interface HTML/JS sem bibliotecas externas (só as fontes do Google Fonts, com fonte do sistema se faltar internet).
- Com login, perfis e permissões checadas no servidor. Roda no computador (`MorroDaCruz.exe`) ou **na nuvem, com link fixo e sem depender de computador** (`nuvem.py`, passo a passo em `docs/NUVEM.md`). O layout funciona em tela de celular (360 px).
- **Implantação, backup e recuperação:** `docs/IMPLANTACAO.md`.
- **Entrega para revisão** (situação, matriz, testes, decisões): `docs/ENTREGA_FINAL.md`. Ciclo completo da Zona01: `docs/EVIDENCIAS_CICLO_ZONA01.md`.
- **Estado atual: piloto de TESTE.**
  - Medição oficial bloqueada.
  - Regras financeiras de material pendentes: veja `docs/MATRIZ_REGIMES_FATURAMENTO.md`.
  - Detalhes das etapas 0 e 1: `docs/ETAPAS_0_1_APROVACAO.md`.
  - Correções da auditoria do commit `b63b5db` (A01–A12): `docs/CORRECOES_AUDITORIA_b63b5db.md`.
  - Etapa 3, estoque (reserva, saldo com a equipe, empréstimo autorizado, estorno): `docs/ETAPA_3_ESTOQUE.md`.
  - **Plano de entrega completa** (requisitos, situação, aceitação): `docs/PLANO_ENTREGA_COMPLETA.md`. **Decisões pendentes** (documento único): `docs/DECISOES_PENDENTES.md`.
  - Etapa 4, campo e cadastro (intervalos por etapa, retificação, conciliação do legado, levantamento de campo, conferência interna do cadastro, soldas verificadas, foto original com hash): `docs/ETAPA_4_CAMPO.md`.
  - Módulos do plano: acesso e auditoria `docs/MODULO_A_ACESSO.md`; campo `docs/MODULO_B_CAMPO.md`; compras e recebimento `docs/MODULO_C_COMPRAS.md`; planejamento e mapa `docs/MODULO_D_PLANEJAMENTO.md`; medição (parcela única, elegibilidade, conferência antes do fechamento, regras bloqueadas) `docs/MODULO_E_MEDICAO.md`; relatórios e operação `docs/MODULO_F_RELATORIOS.md`.

## Site para a equipe: um link, a partir do computador do escritório (Windows)

1. Baixe `MorroDaCruz-Windows.zip` em **Releases** do repositório (versão mais recente) e descompacte numa pasta. Ele já traz as planilhas, o mapa e o túnel (cloudflared).
2. Dê dois cliques em `MorroDaCruz.exe`. Se o Windows avisar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.
3. Na primeira vez, a obra é montada sozinha e o navegador abre em "Link para a equipe". Crie o seu administrador; os usuários de demonstração são desativados.
4. Aparece o **link para a equipe** (`https://….trycloudflare.com`). Quem abre o link entra pelo computador ou celular, de qualquer lugar. Crie os usuários de cada pessoa em Administrativo › Usuários e histórico.

Não precisa instalar o Python nem criar conta em lugar nenhum. O link vale enquanto o programa estiver aberto e muda a cada reinício. O link atual fica na janela do programa, em `LINK_DA_EQUIPE.txt` e no botão "Link da equipe" do sistema. Os dados ficam na pasta do programa (`dados_demo/`).

O executável é gerado e testado no Windows pelo GitHub Actions (`.github/workflows/morro-da-cruz-windows.yml`). Para gerar à mão: `python -m PyInstaller MorroDaCruz.spec`. Sem o executável, `ABRIR_SISTEMA.bat` faz o mesmo usando o Python instalado.

## Testar no seu computador pelo código (demonstração, sem tocar no banco oficial)

1. Instale o Python 3.11+ (no Windows, marque "Add python.exe to PATH") e rode `pip install openpyxl pillow`.
2. Baixe esta branch (`claude/powerbi-modifications-wqxekj`) e entre na pasta `morro-da-cruz`.
3. Copie as 5 planilhas oficiais para `planilhas/` e o HTML do mapa REV02 para `mapa/` (nomes em `planilhas/LEIA-ME.md` e `mapa/LEIA-ME.md`).
4. Rode `python demo.py` e abra **http://127.0.0.1:8765**. Entre com `eng.demo` e a senha `demo-morro-123` (outros perfis: o comando lista).
   - O banco de demonstração fica em `dados_demo/`, separado de `dados/`. Ele é importado com o perfil de controles TESTE; a aprovação real (D-01) continua pendente.
   - Para fechar: Ctrl+C. Para começar do zero: `python demo.py --recriar`.

## Como rodar (Windows)

1. Instale o Python 3.11+ e rode `pip install openpyxl`. Recomendado: `pip install pillow`, para decodificar por completo as fotos enviadas. Sem o Pillow, PNG continua sendo decodificado e JPEG passa só pela verificação estrutural; o método fica registrado em cada foto.
2. Coloque as planilhas oficiais em `planilhas/` e o HTML REV02 em `mapa/`. Os nomes exatos estão em `config/fontes.json`.
3. Faça a importação. Ela nunca apaga o banco nem movimentos.
   ```
   python importar.py              # simulação: mostra o relatório, não altera nada
   python importar.py --aplicar    # trava + backup verificado e completo + importação numa transação
   ```
   Se uma conferência reprovar, nada é gravado (código de saída 2) e o motivo fica em `dados/relatorios/`.
   - **A aplicação exige o servidor parado** e um conjunto de controles completo e **aprovado por você** em `config/controles.json`: bloco `aprovacao` com status `APROVADO`, nome e data.
   - Sem isso, só a simulação roda (`SIMULADA_SEM_CONTROLE_APROVADO`).
   - O sistema não preenche a aprovação.
4. Crie você mesmo o primeiro usuário (o sistema não cria usuários sozinho). A senha é pedida no terminal:
   ```
   python usuarios.py perfis                                   # perfis e permissões (matriz provisória, D-10)
   python usuarios.py criar --login seu.nome --nome "Seu Nome" --perfil ADMINISTRACAO
   ```
   Os demais usuários podem ser criados pela aba **6. Usuários & Histórico** ou pelo mesmo comando.
5. Suba o sistema e abra **http://127.0.0.1:8765** (tela de login):
   ```
   python server.py
   ```
   Cada gravação fica registrada com o usuário logado (auditoria). O log do servidor fica em `dados/logs/servidor.log`.
6. Backup a qualquer momento: `python backup.py criar | verificar <pasta> | restaurar <pasta>`. A restauração exige o servidor parado.
7. Testes: `python -m unittest discover -s tests -v`. Os testes do piloto Zona01 e de `test_base_real.py` exigem as planilhas reais em `planilhas/` (sempre em cópias descartáveis).

## Importação (`importar.py` / `importacao.py`)

| Fonte | O que entra | Conferência |
|---|---|---|
| 06.1 REDES REV01, aba `REDE` | Trechos: perfil de vala, quantidades AL:BK, pontas, handle, código BM | 1.436 trechos · 110.686,03 m |
| 06.2 CONEXÕES REV08, aba `CONEXÕES` (colunas localizadas pelo cabeçalho) | Elementos físicos (por handle CAD), atividades por frente, itens com quantidade; unidade pelo item da Juntada; BA/BB/AW/AG/AH; avisos AA/AB | 1.191 elementos · 1.242 atividades · 6.539 itens |
| EVIDÊNCIAS REV08 | Conferência do agrupamento; zona; status de posição; ID da auditoria | 1.191 de 1.191 grupos iguais |
| BM REV04 IDENTIFICAÇÃO | Juntada e Vertical; BDI, K e totais do rodapé | 347 / 432 itens; P0 recalculado = célula T556 |
| 03.3.2 REV03 REAJUSTE | Data-base, aniversário, índice CEFR | — |

**Garantias da importação:**
- **Conferências antes do COMMIT:** controles aprovados por conjunto exato de arquivos (`config/controles.json`, SHA-256 de cada fonte), totalização do BM igual ao rodapé da planilha e pendências de identidade impeditivas. Reprovou → rollback + relatório.
- **Identidade física:** trecho = handle + pontas UTM; elemento = handle (provisório pelo nº, promovido quando o handle aparecer); item = assinatura técnica completa. Nunca pelo nº da linha, pela ordem nem só pelo nome.
- **Sem transferência presumida:** histórico (check-in, foto, execução, medição, cadastro) só muda de identidade por de-para explícito (`config/conciliacoes.json`).
- **Fonte ausente não apaga dado:** sem EVIDÊNCIAS, zona/status/ID ficam preservados com pendência.
- **Proveniência:** cada registro guarda arquivo, SHA-256, aba, linha e células lidas.
- **Histórico:** os nomes antigos ficam registrados, e cada diferença entre revisões também.
- **Nada é apagado:** o que sai de uma revisão fica com `vigente = 0`.
- **Pendente não vira chute:** quantidade e unidade sem fonte ficam **pendentes** (361 linhas "APROVAR — sem item no BM").
- **Decisões posteriores** (`config/decisoes.json`) nunca são alteradas pela reimportação e só se ligam a avisos por vínculo explícito (semelhança de texto = "revisar").
- **Divergência registrada:** o valor do contrato (R$ 49.878.748,56, cláusula 3.1) e o P0 do BM (R$ 49.878.748,6575869) aparecem lado a lado, sem ajuste.

## Regras em vigor

- **N02:** unidades nunca se misturam e UN ≠ PÇ. DF-33 (CH) aparece como `17 UN · 0,71 m`.
- **E06:** perfil de vala `A CONFIRMAR`, incompleto ou com volume negativo bloqueia o cálculo. Trecho MND não exige perfil de vala.
- **BDI e K na ordem do BM:**
  - medição com `ROUND(q×p;2)` por item;
  - BDI por classe;
  - total = (Σ + BDI) × (1 + K), com K = −1 + (1 − 14,04 %) (contrato 5.2).
- **Lançamentos:**
  - `PROPOSTO` quando há item de BM com fonte;
  - `PENDENTE` (fora do valor) sem item ou regra; não é R$ 0 contratual;
  - **material nunca recebe regime automático:** sem 80/20 e sem 100 % na aplicação;
  - **MND** sem substituição automática de item.
- **Estoque:**
  - disponível = saldo físico − reservas;
  - a reserva é da equipe e do dia;
  - o que fica com a equipe é declarado no check-out e volta no dia seguinte;
  - uma sessão (check-in) aberta por equipe, fechamentos em ordem, sem check-in retroativo;
  - fechamento encerrado só se corrige por retificação (mesma quantidade, mesma data, histórico preservado);
  - nenhum estorno deixa reserva sem cobertura (recusa ou ajuste explícito registrado);
  - empréstimo só com documento, responsável e autorização;
  - correção só por estorno (com motivo, sem apagar);
  - baixa teórica não reduz o saldo físico.
- **Objeto retirado** da revisão vigente: consulta permitida; check-in, apontamento, foto, OK, recomposição e cadastro bloqueados.
- **Medição fechada é congelada:** revisão posterior do BM não muda o valor dela (só alerta).
- **Simulação explícita:** a medição de TESTE lista as hipóteses não validadas (teto que desconta excedente, reajuste sem fração elegível, rateio da escavação, soldas ⌈L/6⌉).
- **OK interno:** o "[✓] OK" é da Ankara e só gera proposta numa medição de **TESTE**. Também envia o trecho para a esteira GDOC.
- **Fotos e clima:** controles operacionais propostos (3 fotos por trecho, 2 por nó com sinalização herdada; clima por turno).
- **Foto original:** só é aceita depois de validada como imagem íntegra. É guardada sem alteração, com SHA-256 conferido no backup. Data e GPS vêm do EXIF, depois do aparelho, sem nunca inventar; a origem fica registrada. A mesma imagem não pode ser reutilizada. O carimbo é exibido, não gravado.
- **Intervalos por etapa no trecho** (assentado, cadastro de campo, reaterrado):
  - sobreposição e repetição são recusadas;
  - reaterro e cadastro só sobre assentamento registrado até a data do serviço;
  - reaterro sem cadastro de campo gera alerta;
  - avanço antigo, só em metros, fica preservado como legado pendente até a conciliação da posição (um ou mais intervalos por etapa, mesma soma);
  - **retificação**: corrige os intervalos de um apontamento ou de uma conciliação (motivo, responsável, vínculo ao original). O trecho inteiro é conferido antes de gravar (tudo ou nada); nada é apagado; o apontamento retificado sai das somas e o substituto traz as quantidades corrigidas. Não vale depois do OK interno;
  - a estimativa de soldas ⌈L/6⌉ nunca vira quantidade confirmada;
  - soldas são informadas e verificadas por outra pessoa.
- **Cadastro em quatro fases:** levantamento de campo (vala aberta, com registro de referência), preparação pela empresa, **conferência interna Ankara** (não é aprovação da Caesb; NÃO CONFORME impede protocolar e permite devolver à empresa) e entrega no GDOC (decisão da Caesb registrada a partir do documento dela).
- **Visão integrada:** o detalhe do trecho reúne intervalos, lacunas, soldas, fotos (com validação), verificações, histórico e pendências (bloqueio, alerta, pendente).
- **Pin do mapa:** mostra a programação do check-in, não a posição atual da equipe.

## Telas

Depois do login abre a **tela inicial**: o Menu do perfil (Mapa iluminado, Lançamento de campo, Administrativo, Documentos e
Medição, na ordem do trabalho de cada perfil) e, ao lado, o traçado real da rede, com as equipes que fizeram check-in hoje.
O subtítulo sai do banco: a extensão dos trechos da 06.1 e as ligações prediais do BM (item de código Caesb
8005508120013).

Nas outras telas, o **menu lateral** fica recolhido em ícones; passar o mouse abre por cima e o botão do topo fixa aberto.
No celular, ele abre pelo botão ☰. O Administrativo reúne Equipes, Planejamento, Compras e notas, Almoxarifado, Check-in e
check-out, Dados da obra (o mapa técnico REV02 com a ficha de cada trecho), Cadastro, Relatórios e Usuários e histórico.
Cada tela tem endereço próprio (`/#iluminado`, `/#campo`, `/#docs`…), e o botão Voltar do navegador funciona.

O **Mapa iluminado** (`web/iluminado.js`) desenha a visão geral do HTML REV02, que o `mapa_geral.py` lê sem alterar o
arquivo: satélite (as 25 plantas montadas numa imagem, se houver Pillow; senão, uma a uma), zonas oficiais e o traçado dos
1.436 trechos. A cor de cada trecho vem só dos registros do banco: não iniciado, liberado pela topografia, em execução,
concluído aguardando o OK interno, OK interno com o cadastro pendente e cadastro aprovado pela Caesb. O pino de cada equipe
fica no alvo do check-in de hoje. Nada sem posição no projeto ganha coordenada; isso continua na bandeja do Dados da obra.

## Documentos oficiais

A tela **Documentos** começa pelas planilhas e pelo mapa que já vêm com o sistema (BM REV04, BM 03.3.2 REV03, 06.1 REV01,
06.2 REV08, Evidências e o HTML REV02): baixam do próprio servidor, com login, sem Drive. Abaixo fica a lista dos arquivos
oficiais no Google Drive, da qual o sistema guarda só o link. Essa lista vem da planilha-índice da pasta (pelo link ou em
CSV, sempre com prévia) ou do cadastro na própria tela. **Abrir** mostra o arquivo na internet (Word e Excel no Google
Docs e no Planilhas) e **Baixar** baixa o original. Como colocar os documentos: `docs/DOCUMENTOS.md`.

## Google Drive conectado

Com a conta Google da obra conectada pelo site (`drive.py`, esquema v15), as fotos de campo e os anexos das notas fiscais
sobem sozinhos para a pasta da obra, em subpastas por trecho e por mês, e o app mostra a pasta de cada um. O original
continua no servidor. A planilha-índice é lida pela mesma conta. Passo a passo (Google Cloud e conexão):
`docs/GOOGLE_DRIVE.md`.

## Mapa técnico (Dados da obra)

O servidor abre `mapa/PLANTAS_..._REV02_EQUIPES.html` **sem alterá-lo** e injeta `web/mapa_iluminado.js`. A camada lê o mesmo `DADOS` da REV02 e faz o seguinte:
- alterna Modo Projeto (cores de DE) e Mapa Iluminado (andamento, a partir só dos registros efetivos);
- marca com um miolo branco a execução **informada sem verificação**, parcialmente verificada ou legada sem posição (verificado = conferência interna Ankara);
- desenha os pins de programação;
- envia a seleção para o painel de Fiscalização.

## Pendências

- **Faturamento de material:** matriz de regimes aguardando aprovação.
- **Itens de BM a definir:** 14 serviços da 06.1, o MND e o critério da escavação em dois itens.
- **Reajuste:** frações elegíveis e o pedido da contratada.
- **Próximas etapas:**
  - etapa 4: retificação depois do OK interno, etapa de escavação, interligações e manobras, carimbo derivado para relatório;
  - etapa 5 (mapa): camada de pendências e teste das 13 frentes;
  - NF com pedido/compra e aceite parcial (complemento da etapa 3 — o fluxo integral de almoxarifado ainda não está concluído);
  - exportação no modelo oficial (`01ª MC`);
  - usuários, perfis e acesso de campo.
