# Módulo C — solicitação de material, notas e recebimento

CT 10.239/2026 · atualizado em 28/10/2026 · esquema v22 · D-172 a D-175.

## Operação atual

- **Pedir material** é uma tela própria. Almoxarifado, SUPERVISOR, EQUIPE (encarregado), engenharia e administração podem solicitar. Os perfis de campo não recebem acesso a notas fiscais. O encarregado pede para sua frente.
- Escolha por tipo, tamanho ou busca; nomes curtos sem código; quantidade com −/+; destino por botões de zona/frente; observação opcional. “Não achei: escrever ou tirar foto” aceita item ainda sem cadastro identificado.
- Nomes e grupos saem das descrições. `config/materiais_pedido.json` aceita ajustes por material (`nome`, `tipo`, `tamanho`). Pressão, resina e dimensões que distinguem peças devem ser preservadas.
- Engenharia/administração aprovam em um toque ou recusam informando o motivo. Quem solicitou não aprova a própria solicitação. Item descrito/fotografado precisa ser identificado antes da aprovação. Meus pedidos mostra aguardando, aprovado, recusado com motivo ou chegou, com cor e texto.
- Cadastro de fornecedor permanece junto da nota digitada. XML e PDF/imagem continuam em Compras e notas; imagem deve ser decodificável. Quem digitou a NF não a confere.
- Pedido de compra saiu das telas, das rotas e da associação automática. Suas tabelas e dados antigos permanecem. Funções de leitura e compatibilidade histórica não são o fluxo de operação novo.

## Conferência e entrega por linha

O almoxarife marca cada linha pela descrição e pelo material reconhecido. A linha reconhecida e marcada vale como conferência cara-crachá. Engenharia confirma **somente** desconhecidas (incluindo unidade diferente sem fator conhecido) e linhas encaminhadas por **Corrigir**. Não há aprovação da nota inteira.

A entrega pode ser registrada antes dessa identificação. O botão verde aceita a entrega depois da marcação de todas as linhas, mesmo que alguma esteja sem identificação. Reconhecidas entram no estoque; desconhecidas ficam registradas em `nf_entregas_linhas`, na unidade da NF, sem gerar saldo. Quando a engenharia confirma material/fator, a entrega já registrada gera estoque uma única vez, preservando data e recebedor originais. Frete/serviço identificado posteriormente encerra a pendência sem movimento.

Aceite e recusa parciais continuam: aceito + recusado nunca ultrapassa o saldo da linha. O que não chegou continua a receber. Recusa exige motivo. Recusa de linha desconhecida fica no histórico físico; não inventa material. Tubo da Caesb aceito vira romaneio, nunca compra nem quantidade de medição. Quarentenas antigas continuam dependendo da inspeção.

Uma solicitação não é pré-requisito de NF, conferência, recebimento ou estoque. Ligar uma NF a uma solicitação aprovada é opcional e serve para atualizar “Chegou”. Não gera saldo.

## Migração e rastreabilidade

`preparar_v22` acrescenta tabelas, sem apagar tabelas antigas. O saldo deixa de excluir entradas aceitas apenas por falta de aprovação da NF sem pedido. Não se cria movimento nem aprovador fictício.

`nf_liberadas_v22` guarda NF, material, quantidade aceita e momento da migração. O relatório JSON de `importar.py` inclui `notas_liberadas_v22`, com número e série, para relacionar as notas liberadas. Na simulação, a lista é previsão; só a aplicação concluída confirma a mudança. A reexecução não duplica a auditoria.

Nenhum banco de produção foi usado no desenvolvimento. A NF 18734 dos testes é um exemplo sintético. A lista real será a da migração do site e deve ser anexada ao registro da implantação.

Tabelas novas: `solicitacao_detalhes`, `solicitacao_avulsos`, `solicitacao_notas`, `nf_entregas_linhas`, `nf_confirmacoes`, `nf_liberadas_v22`. As rotas de escrita usam autor da sessão, permissão e transação. Fotos de solicitações só podem ser vistas pelo solicitante e por quem aprova.

## Verificação

`tests/test_fluxo_v22.py`: solicitação pelos perfis, foto/texto desconhecidos, segregação, recusa, vínculo informativo, identificação após entrega, corrigir reconhecida, entrega parcial, conversão, frete, reenvio sem duplicar e migração sem aprovação fictícia. `test_compras.py` mantém testes de XML, inspeção, estoque, devolução, inventário e compatibilidade dos registros antigos.

Relatório de materiais: comprado vem das linhas de NF já identificadas/conferidas; a receber é o saldo físico das linhas identificadas de notas abertas. Refugo e devolução não recriam compra pendente em pedido antigo. A consulta é agregada uma vez por relatório.
