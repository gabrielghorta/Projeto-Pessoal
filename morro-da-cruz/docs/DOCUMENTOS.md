# Documentos oficiais: a tela Documentos do sistema

> **Fora do menu desde 19/10/2026 (decisão do responsável).** Quem precisa de um documento abre direto no Google Drive
> da obra. As planilhas oficiais baixam pela aba **LEV › Baixar planilhas**, e a ligação com o Drive (fotos e notas)
> fica em **Administrativo › Usuários e histórico**. As rotas `/api/documento*` e a tabela `documentos_obra` continuam
> no servidor, sem perda de dados, só para Engenharia e Administração.

As planilhas e o mapa que são a base do sistema (BM REV04, BM 03.3.2 REV03, 06.1 REV01, 06.2 REV08, Evidências e o HTML
REV02, nomes em `config/fontes.json`) já vêm com o programa e aparecem no topo da tela, para baixar direto do servidor.
Não precisam de link nem de índice.

Abaixo delas fica a lista dos demais arquivos oficiais da obra. Os arquivos ficam no **Google Drive da obra**. O sistema
guarda só o endereço (link) de cada um e o que é preciso para achá-lo sem abrir: nome claro, pasta, tipo, revisão,
data e código original. Nada é enviado nem copiado para o servidor.

- Quem consulta: qualquer pessoa logada. Abre o arquivo no Drive ou baixa direto de lá.
- Quem organiza a lista: perfis com a permissão `documentos`, hoje Engenharia e Administração (`config/perfis.json`).
- Só entram links do Google Drive ou do Google Docs, com https. Outro endereço é recusado.
- Nada é apagado. Retirar da lista exige o motivo, registra quem e quando, e o arquivo continua no Drive.
- Toda alteração fica no histórico (Administrativo › Usuários e histórico, objeto `DOCUMENTO`).

Com o **Google Drive conectado** (`docs/GOOGLE_DRIVE.md`), a planilha-índice é lida pela conta da obra e não precisa
ser pública, e as fotos de campo e os anexos das notas sobem sozinhos para a pasta da obra.

Cada documento tem dois botões. **Abrir** mostra o arquivo na internet: Word e Excel no Google Docs e no Planilhas; PDF,
imagem e DWG na visualização do Drive. **Baixar** baixa o original. As pastas de trabalho (`07_IA_CHATGPT_E_CLAUDE`,
`99_TEMPORARIOS_E_SISTEMA`) ficam fora da lista, a não ser que se marque a opção na importação.

## Como colocar os documentos

1. Organize a pasta do Drive e crie a planilha-índice. O prompt para o ChatGPT faz isso e cria a planilha
   "Morro da Cruz - Índice de Documentos".
2. Na planilha-índice, clique em **Compartilhar** e escolha "qualquer pessoa com o link pode ver".
3. No sistema, abra **Documentos** e depois **Gerenciar a lista de documentos**:
   - cole o link da pasta da obra e o link da planilha-índice, e clique em **Salvar os links**;
   - clique em **Ver o que muda pelo índice**. A prévia mostra os novos, os atualizados e as linhas ignoradas, com o
     motivo de cada uma. Nada é gravado até você clicar em **Aplicar**.
4. Se a hospedagem bloquear o acesso ao Google, baixe a planilha em CSV (Arquivo › Fazer download › CSV) e use
   **Importe o índice em arquivo**. O resultado é o mesmo.
5. Documento novo depois disso: acrescente a linha na planilha-índice e repita o passo 3, ou cadastre o documento
   direto na tela, em **Adicionar um documento**.

## Colunas da planilha-índice

| Coluna | Uso |
|---|---|
| nome novo | **obrigatória**: o nome claro que aparece na lista |
| link | **obrigatória**: link do arquivo no Drive |
| nome antigo | aparece embaixo do nome e entra na busca |
| pasta | caminho da pasta, por exemplo `01_DOCUMENTOS_OFICIAIS / 02_Projeto_Executivo`. Vira os filtros por pasta e subpasta |
| tipo, revisão, data | data em AAAA-MM-DD ou DD/MM/AAAA. O tipo sai da extensão do nome, se ficar vazio |
| observação | texto livre |
| código | opcional. Se ficar vazio, usa o que estiver entre parênteses no fim do nome novo, por exemplo `(06.2)` |

A ordem das colunas não importa. Vírgula, ponto e vírgula ou tabulação servem de separador.

## Como a lista é atualizada pelo índice

- O mesmo arquivo do Drive (mesmo id no link) atualiza a linha que já existe. Nunca vira uma segunda linha.
- Linha sem link válido, ou repetida dentro do índice, é ignorada e aparece na prévia com o número da linha.
- Documento que está na lista e não está no índice **continua na lista**. A prévia avisa quantos são; retirar é à
  mão, com o motivo.
- Os links da pasta e da planilha ficam no banco (`parametros`), não no código. O repositório é público.

## Banco

Esquema v14: tabela `documentos_obra`, só acréscimo. Esquema v15: fila `envios_drive` do envio para o Drive. No PythonAnywhere, cole de novo o comando de instalação e clique
em **Reload**: o site migra sozinho no primeiro acesso, depois de um backup verificado. No computador do escritório,
rode `python importar.py` (simulação) e depois `python importar.py --aplicar`, com o servidor parado.
