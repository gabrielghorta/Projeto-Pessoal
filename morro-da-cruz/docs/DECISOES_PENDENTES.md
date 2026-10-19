# Decisões pendentes — documento único

CT 10.239/2026 · consolidado em 17/10/2026. Substitui as listas espalhadas pelos documentos das etapas; essas listas passam a apontar para cá.

Cada decisão traz as opções, o impacto, a recomendação e **o que fica bloqueado enquanto ela não sai**. A regra provisória vale até a sua decisão. O sistema nunca preenche aprovação, responsável autorizado nem condição da Caesb por conta própria.

| Situação | Significado |
|---|---|
| **ABERTA** | aguardando você |
| **PROVISÓRIA** | regra provisória em uso, documentada |
| **DECIDIDA** | registrada, com data |

## 1. Dados, controles e projeto

| ID | Decisão | Opções | Impacto | Recomendação | Regra provisória / o que fica bloqueado |
|---|---|---|---|---|---|
| D-01 | Aprovar o conjunto de controles CTRL-01 (valores esperados das planilhas REV01/REV08/BM REV04/REAJUSTE REV03) | aprovar, preenchendo você mesmo `aprovacao` em `config/controles.json` / corrigir valores | Sem isso, a importação no banco real é recusada (`CONTROLE_SEM_APROVACAO`). A simulação funciona. | Conferir cada valor na fonte e aprovar. | **Bloqueia** a importação real. Testes e demonstrações usam o perfil TESTE. |
| D-02 | Confirmar os vínculos explícitos da DEC-0001 (`config/decisoes.json`) | confirmar / ajustar | Define quais avisos da 06.2 ficam ligados à decisão. | Conferir os elementos citados. | Os vínculos atuais seguem como estão; nenhum novo é criado automaticamente. |
| D-03 | Posição de MV-11, VTF-12 e VTF-16 | informar a coordenada com fonte / manter sem posição | Ficam fora do mapa, na bandeja "sem posição". | Obter da topografia. | Sem coordenada inventada. |

## 2. Acesso e responsáveis

| ID | Decisão | Opções | Impacto | Recomendação | Provisório / bloqueado |
|---|---|---|---|---|---|
| D-10 | Distribuição dos perfis (quem é administração, engenharia, almoxarifado, equipe, topografia, cadastro) e o que cada perfil pode fazer | aprovar a matriz de `config/perfis.json` / ajustar | Define quem lança, verifica, confere e corrige. | Revisar a matriz proposta; criar os usuários reais você mesmo (`python usuarios.py criar`). | **PROVISÓRIA**: matriz proposta em uso nos testes. Nenhum usuário real é criado pelo sistema. |
| D-11 | Quem pode verificar intervalos e soldas, e se precisa ser de perfil diferente de quem informou | mesmo perfil, pessoa diferente (hoje) / perfil específico (engenharia/fiscalização interna) | Segregação de funções. | Verificação só por engenharia, pessoa diferente. | **PROVISÓRIA**: pessoa diferente (usuário da sessão) e permissão `verificar`. |

## 3. Campo e cadastro

| ID | Decisão | Opções | Impacto | Recomendação | Provisório / bloqueado |
|---|---|---|---|---|---|
| D-12 | Reaterro sem cadastro de campo até a data | alerta (hoje) / bloqueio | Bloquear evita fechar vala sem levantamento, mas trava a equipe se o topógrafo atrasar. | Bloquear, com exceção registrada pela engenharia. | **PROVISÓRIA**: alerta. |
| D-13 | Herança da foto de sinalização pelo nó (D3) | qualquer data (hoje) / mesma data / janela de N dias | Evidência de sinalização no dia do serviço. | Mesma data ou janela de 1 dia. | **PROVISÓRIA**: sem conferência de data. |
| D-14 | Conferência interna obrigatória antes do protocolo no GDOC | opcional (hoje; só NÃO CONFORME bloqueia) / obrigatória | Reduz negativas no GDOC. | Obrigatória. | **PROVISÓRIA**: a falta é pendência. |
| D-15 | Levantamento de campo completo antes de enviar à empresa de cadastro | alerta (hoje) / bloqueio | — | Bloqueio. | **PROVISÓRIA**: alerta. |
| D-16 | Retificação depois do OK interno | recusada (hoje) / permitida com estorno da proposta de medição de TESTE e volta da esteira | O OK já gerou proposta e entrada na esteira. | Permitir só antes do fechamento da medição, com estorno da proposta. | **BLOQUEADA** depois do OK. |
| D-17 | Roteiro da conferência interna do cadastro (6 itens) | aprovar / ajustar | — | Ajustar aos critérios da Ankara. | **PROVISÓRIA**: 6 itens propostos. |
| D-18 | Verificação dos intervalos e soldas exigida antes do OK interno | não (hoje) / sim | — | Sim. | **PROVISÓRIA**: não exigida. |
| D-20 | Liberação topográfica antes do assentamento | alerta / bloqueio | Evita vala fora da locação. | Alerta no início; bloqueio depois do treinamento. | **PROVISÓRIA**: alerta (módulo B). |
| D-22 | Não conformidade aberta impede o OK interno do trecho/nó? | não (hoje) / sim | Evita validar internamente o que tem correção pendente. | Sim. | **PROVISÓRIA**: só alerta nas pendências. |
| D-21 | Etapas executivas obrigatórias e sua ordem (locação, escavação, assentamento, cadastro, reaterro, recomposição, teste de estanqueidade) | quais e em que ordem | Pré-requisitos de campo. | Locação → assentamento → cadastro → reaterro obrigatórios; escavação informativa. | **PROVISÓRIA**: só assentamento como pré-requisito de cadastro e reaterro. |

## 4. Compras e almoxarifado

| ID | Decisão | Opções | Impacto | Recomendação | Provisório / bloqueado |
|---|---|---|---|---|---|
| D-40 | Quem aprova a solicitação de compra e emite o pedido | engenharia / administração / alçada por valor | Controle de gastos. | Engenharia aprova; administração emite. | **PROVISÓRIA**: permissões `compras_aprovar` (engenharia, pessoa diferente de quem solicitou) e `compras_pedir` (administração). |
| D-41 | Quem faz a inspeção de recebimento (aceite/recusa) e quais documentos exige | almoxarifado / engenharia / laudo do fabricante | Material entra em estoque só depois do aceite. | Almoxarifado com laudo; engenharia em material hidráulico. | **PROVISÓRIA**: almoxarifado, com referência do laudo obrigatória. |
| D-42 | Quem aprova ajuste de inventário | almoxarifado / engenharia | — | Engenharia. | **PROVISÓRIA**: permissão `inventario_ajustar` (engenharia). |
| D-44 | Compra de emergência sem solicitação aprovada | proibida (hoje) / permitida com aprovação posterior | Hoje todo pedido nasce de solicitação aprovada por outra pessoa. | Manter; emergência com aprovação no mesmo dia. | **PROVISÓRIA**: proibida. |
| D-43 | Reserva vencida (data passada) | liberar manualmente (hoje) / expirar automaticamente após N dias | Saldo preso. | Aviso + liberação manual em lote. | **PROVISÓRIA**: manual. |

## 5. Medição e faturamento (matriz de regimes)

| ID | Decisão | Opções | Impacto | Recomendação | Provisório / bloqueado |
|---|---|---|---|---|---|
| D-30 | A fiscalização aceita medir rede por intervalo dentro do mês, ou só trecho completo? | intervalo / trecho completo (hoje) | Define a apuração mensal. | Perguntar à fiscalização da Caesb. | **PROVISÓRIA**: só trecho completo (OK interno). Apuração por intervalo só como conferência. |
| D-31 | Item de BM e regra de quantidade das soldas | — | — | Precisa de fonte. | **BLOQUEADA**: SOLDA fica PENDENTE. |
| D-50 | Item de BM dos 14 serviços sem item comprovado (lastro, areia, reaterro, carga, escoramento, transporte, sondagem, tapume, sinalização, passadiços, recomposição) | — | — | Precisa de fonte ou composição da Caesb. | **BLOQUEADA**: PENDENTE, fora do valor. |
| D-51 | Divisão da escavação mecanizada entre 5.4.11/5.4.13 e 5.4.15/5.4.14 | critério de campo / medição por item | — | — | Simulação marcada como estimativa; **bloqueia** a medição oficial. |
| D-52 | Itens 5.16.x para os 4 trechos MND localizados | — | — | — | **BLOQUEADA**: assentamento MND PENDENTE; sem substituição por vala. |
| D-53 | Itens do BM em cada categoria do SL0327 (§7.1, §7.2, §7.3) | — | — | Gerar lista candidata para você marcar. | **BLOQUEADA**: material PENDENTE. |
| D-54 | Regime das conexões PEAD e regime normal de material (cláusula 2.16 do Edital) | — | — | Ler a 2.16 e o TR. | **BLOQUEADA**. |
| D-55 | Revisão que vale para a parcela elegível do reajuste (REV03 × REV04) e pedido de reajuste protocolado | — | — | — | Simulação marcada como hipótese; **bloqueia** a oficial. |
| D-56 | Liberação da medição oficial e do modelo `01ª MC` | — | Só depois de D-30…D-55 e da validação do acesso. | — | **BLOQUEADA** (`medicao_oficial_liberada = NAO`). |
| D-57 | Teto por subgrupo: regra contratual ou controle interno? | — | Hoje desconta o excedente na simulação. | — | Hipótese listada. |
| D-58 | Critério da medição do cadastro (2.2_5.2.1) e se o memorando ESET é exigido | — | — | — | **PROVISÓRIA**: mede na etapa 6 da esteira, na medição de TESTE. |
| D-59 | Conferência interna da medição pela engenharia antes do fechamento: obrigatória? roteiro? pessoa diferente de quem deu o OK interno? | obrigatória com roteiro de 5 itens (hoje) / opcional / obrigatória e por outra pessoa | Evita fechar com duplicidade ou evidência perdida; a conferência deixa de valer se um lançamento mudar. | Obrigatória; roteiro ajustado pela Ankara; outra pessoa quando houver dois engenheiros. | **PROVISÓRIA**: obrigatória (CONFORME e vigente), roteiro de 5 itens, sem exigir outra pessoa. A CONFORME é recusada com duplicidade ou foto obrigatória ausente. |

## 6. Implantação

| ID | Decisão | Opções | Impacto | Recomendação | Provisório / bloqueado |
|---|---|---|---|---|---|
| D-60 | Acesso de campo: rede local do canteiro, servidor privado hospedado (com HTTPS) ou só o computador do escritório | hospedagem paga / grátis com limite / computador do escritório com link | Com login pronto, é a hospedagem que permite o celular. | — | **DECIDIDA em 17/10/2026 pelo responsável:** link pela internet a partir do computador do escritório (túnel gratuito da Cloudflare, https://….trycloudflare.com), com usuário e senha por pessoa. O link só liga depois do administrador real; os usuários de demonstração são desativados; a configuração só é feita no próprio computador. Limites: o link vale enquanto o programa estiver aberto e muda a cada reinício. Planilhas e mapa passam a ser versionados no GitHub (públicos, por decisão do responsável). **REVISTA em 18/10/2026 pelo responsável:** o sistema tem de rodar na nuvem, sem depender de computador ("empresa pequena, sem servidor"), com link fixo e acesso muito fácil. Preparado: `nuvem.py` (mesmo servidor, modo nuvem atrás do https da hospedagem) com receitas para PythonAnywhere (grátis, 512 MB, um clique por mês) e Render (cerca de US$ 7,25/mês, disco persistente), em `docs/NUVEM.md`. **Pendente do responsável:** escolher a hospedagem e criar a conta no nome dele (D-62). |
| D-62 | Hospedagem da nuvem | PythonAnywhere grátis / Render pago / outra | Conta, cartão e custo são do responsável; espaço para fotos decide o tempo de vida do plano grátis. | Começar no PythonAnywhere; passar ao Render quando as fotos encherem os 512 MB. | **PENDENTE:** criar a conta e seguir `docs/NUVEM.md`. |
| D-61 | Funcionamento sem internet (necessidade e alcance) | não precisa / leitura offline / lançamento offline com sincronização | Lançamento offline exige resolver conflitos. | Confirmar a necessidade antes de implementar. | **NÃO INICIADO** por regra. |
| D-63 | Onde ficam os documentos oficiais da obra | arquivos no servidor / links do Google Drive | O servidor grátis tem 512 MB; o Drive da obra tem 1 TB. | Links do Drive, sem chave de API do Google. | **DECIDIDA em 18/10/2026 pelo responsável:** os arquivos e as fotos ficam no Google Drive da obra; o site guarda só o endereço de cada um. Feito: aba 8. Documentos (esquema v14, `documentos_obra`), com a lista vinda da planilha-índice (link ou CSV, com prévia) ou do cadastro na tela, só links do Google, nada apagado. Guia em `docs/DOCUMENTOS.md`. Em 19/10/2026: a pasta foi organizada (índice de 6.690 linhas) e o site passou a falar direto com o Drive pela conta do responsável (esquema v15, `drive.py`, guia em `docs/GOOGLE_DRIVE.md`): fotos de campo e anexos das notas sobem sozinhos, com a pasta mostrada no app; o original continua no servidor. **Pendente do responsável:** criar o acesso no Google Cloud, conectar, compartilhar a pasta com a equipe e importar o índice. |
