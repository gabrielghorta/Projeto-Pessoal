# Google Drive conectado: fotos e notas sobem sozinhas

O site fala direto com o Google Drive da obra pela **sua conta Google**, conectada uma vez. Depois disso:

- **Fotos de campo:** cada foto enviada no Lançamento de campo sobe para
  `03_EXECUCAO_DE_CAMPO/01_Fotos_por_Trecho/<Zona>/<trecho>`, com um nome claro. Exemplo:
  `Morro da Cruz - Foto de Campo - PB01_Rede_TR001 - Execução - 2026-10-18 10h20 (7278749e).jpg`.
- **Notas fiscais:** o XML da NF-e, o PDF ou a imagem da nota e os laudos sobem para
  `04_COMPRAS_E_ALMOXARIFADO/01_Notas_Fiscais/<AAAA-MM>` (laudos em `04_Laudos_de_Inspecao`).
- **Onde ficou:** cada foto (na ficha do trecho) e cada nota (em Compras e notas) mostra a pasta do Drive, com link para
  a pasta e para o arquivo. A tela Documentos mostra os últimos envios e o que ainda está na fila.
- **Planilha-índice:** passa a ser lida pela sua conta, sem precisar deixá-la pública.

**O que não muda:**
- O arquivo original continua guardado no sistema, com o hash e o backup de sempre. O Drive é a cópia que a equipe abre.
- Nada é apagado no Drive. Um arquivo que já foi enviado não é enviado duas vezes: o nome leva o começo do hash.
- Sem conexão, sem internet ou com a autorização revogada, nada se perde. Os arquivos ficam na fila e sobem quando
  a conexão voltar, ou pelo botão **Enviar a fila agora**.
- O ID, o segredo e a autorização ficam no banco do sistema, nunca no código (o repositório é público).

## 1. Criar o acesso no Google Cloud (uma vez, uns 10 minutos)

Use a conta dona da pasta da obra (`gabrielghorta@gmail.com`).

1. Abra https://console.cloud.google.com e aceite os termos, se aparecerem.
2. **Projeto:** no topo, clique no seletor de projeto e depois em **Novo projeto**. Dê o nome `Morro da Cruz`, clique em
   **Criar** e selecione o projeto.
3. **Ativar o Drive:** menu ☰ › **APIs e serviços** › **Biblioteca**. Procure **Google Drive API** e clique em **Ativar**.
4. **Tela de consentimento:** menu ☰ › **APIs e serviços** › **Tela de consentimento OAuth** (em algumas contas aparece
   como **Google Auth Platform**). Clique em **Começar** e preencha:
   - Nome do app: `Sistema Morro da Cruz`; e-mail de suporte: o seu;
   - Público: **Externo**;
   - Dados de contato: o seu e-mail. Aceite e clique em **Criar**.
5. **Publicar o app:** em **Público** (Audience), clique em **Publicar app**, para o status ficar **Em produção**.
   - Sem isso, o Google desliga a conexão a cada 7 dias.
   - O app não passa pela verificação do Google, e não precisa: é só para a sua conta.
6. **Cliente:** em **Clientes** (ou **Credenciais**), clique em **Criar cliente**:
   - Tipo de aplicativo: **Aplicativo da Web**; nome: `Site Morro da Cruz`;
   - em **URIs de redirecionamento autorizados**, clique em **Adicionar URI** e cole o endereço que o sistema mostra em
     Documentos. No PythonAnywhere é `https://morrodacruz.pythonanywhere.com/drive/retorno`;
   - clique em **Criar**. Copie o **ID do cliente** (termina em `.apps.googleusercontent.com`) e a **Chave secreta do
     cliente**.

## 2. Conectar no sistema

1. Entre no site com um perfil de Engenharia ou Administração e abra **Documentos**.
2. No quadro **Fotos e notas no Google Drive**, abra **Ligar a conta Google da obra**.
3. Cole o **ID do cliente**, o **segredo** e o link da **pasta da obra** (`ANKARA_Morro_da_Cruz`). Clique em **Salvar**.
4. Clique em **Conectar com o Google**:
   - escolha a sua conta;
   - na tela "O Google não verificou este app", clique em **Avançado** e depois em **Acessar Sistema Morro da Cruz**.
     É o app que você mesmo criou;
   - marque a permissão do **Google Drive** e clique em **Continuar**.
5. O site volta para Documentos com **conectado** e a sua conta. Clique em **Testar a pasta**: aparece o nome da pasta da
   obra.
6. As fotos e as notas que já estavam no sistema entram na fila e sobem aos poucos (4 por vez). Para adiantar, clique em
   **Enviar a fila agora** algumas vezes.

## 3. Deixar a equipe abrir os arquivos

Os arquivos ficam na sua conta. Para quem usa o sistema abrir os links (documentos, fotos e notas), compartilhe a pasta
`ANKARA_Morro_da_Cruz` no Drive:
- **Compartilhar** › adicione o e-mail de cada pessoa como **Leitor**; ou
- em **Acesso geral**, escolha **Qualquer pessoa com o link** › **Leitor**. Só entra quem tiver o link.

## 4. Trazer o índice de documentos

1. Em Documentos › **Gerenciar a lista de documentos**, cole o link da planilha **Morro da Cruz - Índice de
   Documentos** e clique em **Salvar os links**.
2. Clique em **Ver o que muda pelo índice**. Com o Drive conectado, o sistema lê a planilha pela sua conta. O Drive
   entrega a primeira aba, que é a **Índice**.
3. A prévia mostra os novos e os ignorados. As pastas de trabalho (`07_IA_CHATGPT_E_CLAUDE` e
   `99_TEMPORARIOS_E_SISTEMA`, com caches e duplicatas) ficam de fora. Para trazê-las também, marque a opção
   correspondente e veja de novo.
4. Clique em **Aplicar**.

Na lista, **Abrir** mostra o arquivo na internet: Word e Excel abrem no Google Docs e no Planilhas; PDF, imagem e DWG na
visualização do Drive. **Baixar** baixa o arquivo original do Drive. A pasta de cada documento aparece na coluna Pasta;
passe o mouse para ver o caminho completo.

## Se algo der errado

| O que aparece | O que fazer |
|---|---|
| "O Google recusou a conexão: redirect_uri_mismatch" | o endereço de retorno no Google Cloud precisa ser exatamente o que o sistema mostra (com `https://` e `/drive/retorno`) |
| "A conexão com o Google foi revogada ou venceu" | confira se o app está **Em produção** (passo 1.5) e clique em **Conectar com o Google** de novo |
| "Sem acesso ao Google pelo servidor" | a hospedagem bloqueou a saída. No PythonAnywhere gratuito, `.googleapis.com` está liberado; se mudar, os arquivos continuam na fila |
| "O link da pasta da obra não é uma pasta ativa do Drive" | cole o link da pasta (`https://drive.google.com/drive/folders/…`), não de um arquivo |
| Foto ou nota com "Drive: não enviado" | em Documentos, clique em **Tentar de novo** no envio com erro |

**Desconectar:** o botão **Desconectar** remove a autorização do sistema e a revoga no Google. O que já foi enviado
continua no Drive.
