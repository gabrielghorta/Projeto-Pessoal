# Conhecimento do assistente (IA)

15/11/2026 · D-226. Este arquivo é o que o assistente sabe sobre o sistema. Ele **não vai inteiro** para o modelo: a cada
dúvida, o código escolhe a seção que mais casa com a pergunta (às vezes duas) e manda só ela. Por isso cada seção é
curta e se explica sozinha.

**Fonte:** os documentos do repositório (`docs/MODULO_*.md`, `docs/DECISOES_PENDENTES.md`, `docs/NOTAS_DE_SERVICO.md`,
`docs/CAMPO_MEMORIA_RM_WORD.md`, a referência `webapp.md` da skill) conferidos com o código do servidor. Valores, prazos,
saldos e a situação atual de um trecho **não ficam aqui**: o assistente consulta o sistema na hora.

**Como editar:** cada seção começa com `## Título` e uma linha `<!-- ... -->` com:
`palavras` (como o pessoal fala, sem acento; é o que a busca usa), `tela` (o endereço que o botão abre),
`botao` (o nome no botão), `telas` (as telas do perfil que abrem aquela) e, se houver, `permissao` (sem ela, o botão
não aparece). Tela ou regra nova: acrescente ou corrija a seção. Escreva sem nomes de pessoas, telefones ou links do
Drive: este arquivo é público e o trecho escolhido vai para o serviço de IA.

## O que o assistente faz
<!-- palavras: assistente ia ajuda voce faz consegue conversa microfone voz rascunho gravar | tela: | telas: -->
Tira dúvidas de uso e monta o rascunho de três lançamentos: pedido de material, relato de chuva ou interferência e
apropriação direta. Ele não grava nada: mostra o rascunho, a pessoa confere e toca no botão de gravar, que usa a
rotina de sempre. Cada perfil só lança o que já podia lançar nas telas. Outras ações (OK interno, verificar, nota de
serviço, estoque, nota fiscal, medição) ele explica onde se fazem, mas não faz. A conversa some ao recarregar a
página; o rascunho e o texto digitado ficam.

## Perfis: quem pode o quê
<!-- palavras: perfil perfis permissao permissoes quem pode posso consigo acesso engenharia administracao almoxarifado almoxarife supervisor encarregado equipe rh topografia cadastro | tela: | telas: -->
Engenharia e Administração: tudo, inclusive usuários, OK interno, medição, notas de serviço e apropriação direta.
Almoxarifado: estoque, receber notas, inventário, pedir material, confirmar o material de uma linha de nota, chuva e
interferência. Supervisor: verificar trechos e soldas, resolver interferências, pedir material, chuva e interferência;
consulta as notas de serviço. Encarregado (login preso à equipe): só a própria equipe — chuva, interferência, fotos e
pedido de material para a frente em que a equipe está programada. RH: consulta notas de serviço. Topografia e
Cadastro: consultam as notas do seu tipo; o Cadastro avança a esteira do cadastro. A matriz é provisória (D-10).

## Ciclo da obra até a medição
<!-- palavras: ciclo ordem etapa etapas fluxo processo caminho sequencia passo passos medicao como funciona obra topografia liberacao execucao | tela: iluminado | botao: Mapa iluminado | telas: iluminado -->
A ordem é obrigatória (D-20): 1) NS de topografia libera o trecho; 2) a NS do dia registra o executado (assentado,
reaterrado); 3) o supervisor verifica e as 3 fotos são enviadas; 4) cadastro de campo pela NS de cadastro, só sobre o
executado; 5) OK interno pela Engenharia ou Administração; 6) o OK gera a proposta na medição de teste e põe o trecho
na esteira do cadastro (empresa → recebido → conferência interna → protocolo no GDOC → memorando ESET). Execução sem
liberação é recusada com o trecho e os metros que faltam. A apropriação direta fica fora dessa ordem.

## Mapa iluminado e as cores
<!-- palavras: mapa iluminado cor cores etapa situacao zona equipe onde ficha cinza azul laranja amarelo rosa ciano branco roxo lilas verde legenda | tela: iluminado | botao: Mapa iluminado | telas: iluminado -->
Cada trecho tem a cor da etapa gravada: cinza tracejado (não iniciado), azul-claro (liberado pela topografia), laranja
(em execução hoje), amarelo (executado, aguardando verificação), rosa (verificado), ciano (cadastro de campo feito),
branco (pronto para o OK interno), roxo (OK interno, na medição), lilás (cadastro em andamento) e verde (cadastro
aprovado pela Caesb). Só o verde é decisão da Caesb. Toque no trecho para abrir a ficha. A etiqueta de cada equipe mostra
onde ela está programada hoje, não a posição real.

## Notas de serviço
<!-- palavras: nota notas servico ns pdf croqui enviar mandar registrar subir dia topografia cadastro numero planilha locacao topografo vincular faixa | tela: notas/servico | botao: Notas de serviço | telas: notas, topografia, cadastro_campo -->
Execução › Notas de serviço. Só a Engenharia e a Administração enviam. Topografia: a planilha de locação (.xls ou
.xlsx) com os croquis, ou a NS em PDF, libera as faixas que casam com a 06.1; as outras se vinculam à mão em Notas
recebidas › Ver › Vincular faixa ao mapa (D-225). NS do dia
(PDF + croqui, em nome da equipe): registra o assentado, reaterrado ou escavado; o trecho fica amarelo, esperando o
supervisor. NS de cadastro: registra o cadastro de campo, só sobre o que já foi executado. O mesmo arquivo não entra
duas vezes; o mesmo número com outro conteúdo exige anular a anterior, com motivo. O que a leitura do PDF não entende
vai para “NS do dia a conferir”. Equipes e almoxarifado não veem as notas (D-134).

## Verificar um trecho executado
<!-- palavras: verificar verificacao verificado conferir conferencia supervisor aguardando executado amarelo rosa intervalo | tela: iluminado | botao: Mapa iluminado | telas: iluminado | permissao: verificar -->
Quem verifica tem a permissão de verificar (Supervisor, Engenharia, Administração); quem informou a execução não
verifica. No Mapa iluminado, a lista “Aguardando verificação” mostra os trechos executados, o mais perto primeiro. Abra
a ficha do trecho e use Verificar; as fotos que faltam podem ir junto. O trecho passa de amarelo para rosa. O
assistente não verifica: é um toque na ficha.

## Fotos e soldas
<!-- palavras: foto fotos solda soldas sinalizacao execucao concluido imagem enviar tirar soldador | tela: campo/fotos | botao: Fotos e soldas | telas: campo | permissao: campo -->
Execução › Lançamento do dia › Fotos e soldas. Trecho: 3 fotos (sinalização, execução e concluído). Nó ou caixa: 2,
herdando a sinalização de um trecho ligado (senão 3). A foto é guardada como veio; a mesma imagem não serve para outro
registro; HEIC é recusado; até 20 MB. Soldas: informadas por um (tipo, quantidade, soldador) e verificadas por outra
pessoa.

## OK interno (liberar o trecho para a medição)
<!-- palavras: ok interno fiscalizacao fiscal liberar liberacao liberalos validar aprovar trecho trechos tr no caixa pronto prontos concluido confeccionado confeccionados executado executados medir medicao branco | tela: iluminado | botao: Mapa iluminado | telas: iluminado | permissao: ok_interno -->
O OK interno é dado na ficha do trecho (ou do nó ou caixa), no Mapa iluminado, no bloco “Para entrar na medição”. Só a
Engenharia e a Administração dão o OK. O sistema exige: execução 100 % (assentado e reaterrado; no MND, só assentado),
todos os intervalos verificados pelo supervisor, as fotos obrigatórias e nenhum avanço antigo sem posição a conciliar.
A data do OK não pode ser anterior ao último serviço. O cadastro de campo não é exigido para o OK (aparece no bloco só
para mostrar onde o trecho está). Os trechos brancos estão prontos. O OK gera a proposta na medição de teste (sem
medição aberta, espera) e põe o trecho na esteira do cadastro. Não é aprovação da Caesb. O OK é um toque
da pessoa, trecho a trecho, não do assistente. Se a pessoa citar um trecho pelo nome, o assistente mostra o que falta.

## Cadastro de campo e esteira do cadastro
<!-- palavras: cadastro campo esteira gdoc eset memorando protocolo empresa levantamento as-built asbuilt aprovado negado ciano lilas verde conferencia | tela: notas/cadastro | botao: Notas de serviço › Cadastro | telas: cadastro_campo, notas -->
Cadastro de campo: o levantamento com a vala aberta, feito pela empresa terceirizada e registrado pela Engenharia pela
NS de cadastro, só sobre o executado. Depois do OK interno o trecho entra na esteira: pronto → enviado à empresa →
recebido (arquivos) → conferência interna da Ankara (não conforme volta à empresa) → protocolo no GDOC → aprovado
(memorando ESET, verde no mapa) ou negado (volta para nova revisão). Só o aprovado é decisão da Caesb e entra na
medição como cadastro. As ações ficam na ficha do trecho.

## Apontamento sem nota de serviço
<!-- palavras: apontamento apontar sem nota ns manual caderneta lancar avanco metros exceção excecao motivo | tela: campo/apontamento | botao: Apontamento sem NS | telas: campo | permissao: lancar_sem_ns -->
Execução › Lançamento do dia › Apontamento sem NS. É exceção da Engenharia e da Administração, com o motivo
obrigatório (ex.: a nota molhou). Com a data e a equipe, aparecem os trechos e nós do check-in dela no dia. O intervalo
precisa de liberação topográfica e não pode se sobrepor a outro. O avanço do trecho normalmente vem da NS do dia.

## Registrar chuva
<!-- palavras: chuva choveu chovendo chuvoso aguaceiro temporal clima tempo paralisou paralisado parou vala alagada bomba tenda sol | tela: campo/interferencia | botao: Interferências e chuva | telas: interferencias | permissao: campo -->
Execução › Lançamento do dia › Interferências e chuva › Choveu. Informe o dia (não futuro), a equipe (ou todas as
equipes com check-in no dia), se foi de manhã, à tarde ou o dia todo, e o efeito: chuva fraca com tenda, paralisou o
serviço ou vala alagada com bomba. O trecho é opcional. Sem relato, o diário mostra “Sem chuva (padrão)”. O
encarregado registra só para a equipe dele.

## Relatar interferência ou não conformidade
<!-- palavras: interferencia impedimento ocorrencia rede existente esgoto cabo fibra poste acesso seguranca nao conformidade relatar resolver obstaculo encontrou achamos | tela: campo/interferencia | botao: Interferências e chuva | telas: interferencias | permissao: campo -->
Execução › Lançamento do dia › Interferências e chuva › Relatar outra interferência. Escolha o trecho, nó ou caixa, o
tipo (impedimento ou não conformidade), a categoria, o dia, a equipe (opcional) e descreva o que foi encontrado. Fica
registrado com o seu usuário. Quem tem a permissão de verificar marca como resolvida, com a resolução escrita;
resolvida não reabre.

## Apropriação direta
<!-- palavras: apropriacao apropriar direta lancar lancamento servico item orcamento canteiro sem nota memoria calculo medidas estorno estornar corrigir data conteiner tapume placa | tela: campo/apropriacao | botao: Apropriação direta | telas: campo | permissao: apropriacao -->
Execução › Lançamento do dia › Apropriação direta: lança um item do orçamento sem nota de serviço (ex.: o canteiro).
Só a Engenharia e a Administração. Ache o item pela busca, informe a data (não futura) e a quantidade; em m, m² e m³
preencha as medidas e o sistema faz a conta. Local, executor, justificativa e evidências são opcionais. Item a aprovar
é gravado, mas fica fora da medição até o código oficial da Caesb; material fica fora até a matriz de regimes
(D-53/D-54); a administração local não se apropria. Correção: estorno com motivo; data errada tem “Corrigir data”.

## Pedir material
<!-- palavras: pedir pedido material requisicao requisitar solicitar solicitacao comprar falta precisa preciso manda luva tubo te curva reducao | tela: compras/requisicoes | botao: Requisições | telas: solicitar, compras | permissao: compras_solicitar -->
Almoxarifado › Compras › Requisições. Toque no tipo ou busque, ajuste a quantidade, toque na zona de destino e envie.
Material que não está no catálogo: “Não achei: escrever ou tirar foto”, e Compras identifica depois. A requisição entra
aberta, sem aprovação (D-196). O encarregado pede só para a frente em que a equipe está programada; sem programação,
peça à Engenharia para programar a equipe.

## Acompanhar ou cancelar um pedido
<!-- palavras: acompanhar pedido requisicao situacao chegou aberta aguardando recebida cancelar cancelamento meus pedidos | tela: compras/requisicoes | botao: Requisições | telas: solicitar, compras -->
Em Requisições, cada pedido mostra a situação: aberta (sem nota), aguardando a entrega (nota ligada), recebida ou
cancelada. Quem pediu cancela o próprio, com motivo; Engenharia e Administração cancelam qualquer um. Quem abre Compras
vê os pedidos da obra; os outros, só os seus.

## Programação do dia e material da equipe
<!-- palavras: programacao programar dia equipe trechos liberar material retirada devolucao devolver check-in checkin checkout reserva reservar conciliar amanha | tela: mapa/programar | botao: Programação | telas: mapa -->
Almoxarifado › Programação. A Engenharia e a Administração programam: escolhem a equipe e tocam nos trechos da zona,
para um dia ou período. O almoxarife libera o material do dia (a sugestão vem do projeto, limitada ao estoque), o que
abre o check-in da equipe e acende o trecho em laranja; no fim do dia registra a devolução (aplicado, sobra, perda com
motivo, fica com a equipe). Dia futuro vira reserva.

## Estoque
<!-- palavras: estoque saldo movimento movimentos inventario contagem ajuste transferencia tubos caesb romaneio receber entrega aceitar recusar estorno almoxarifado | tela: almox/saldo | botao: Estoque | telas: almox -->
Almoxarifado › Estoque: Dia, Receber, Saldo e movimentos, Inventário e transferência, Tubos Caesb. Disponível = físico
menos reservas. Em Receber, cada nota tem Aceitar, Recusar (com o porquê) ou Aceite parcial. Inventário: o ajuste entra
na contagem e outra pessoa dá ciência (D-197). Correção é por estorno com motivo. O tubo da Caesb entra pelo romaneio.
Material recebido nunca vira lançamento de medição.

## Notas fiscais e fornecedores
<!-- palavras: nota fiscal nf xml danfe fornecedor fornecedores conferir conferencia linha reconhecida identificar compras entrada dar entrada | tela: compras/notas | botao: Notas fiscais | telas: compras -->
Almoxarifado › Compras › Notas fiscais: a nota sobe pelo XML ou digitada do PDF ou da foto (anexo obrigatório). Nota
repetida é recusada. Conferir é marcar cada linha; quem digitou a nota não confere. Linha que o sistema não reconheceu
é marcada pela descrição e depois a Engenharia ou o almoxarifado diz qual material é. O aceite ou a recusa da entrega é
em Estoque › Receber. Não existe aprovação da nota (D-175). Fornecedores têm página própria.

## Medição
<!-- palavras: medicao medir bm boletim gaveta gavetas conferencia teto restricao base custo pacote fechar fechamento proposta pendente parada | tela: medicao/mes | botao: Medição | telas: medicao -->
Administrativo › Medição, só de TESTE por enquanto (D-56). Entra pelas gavetas: 1 serviços dos trechos e nós (no OK
interno), 2 materiais (bloqueada até a matriz de regimes), 3 cadastro aprovado no GDOC, 4 recomposição, 5 apropriação
direta. Proposto entra no valor; pendente fica fora, com o motivo. Fechar exige a conferência interna conforme e
justificativa no item acima de 100 % do contrato; fechada, a medição é congelada e o estorno não a desfaz. O pacote sai
no próprio BM oficial. “Medível com restrição” mostra o que está parado e o que libera.

## Equipes
<!-- palavras: equipe equipes integrante integrantes maquina maquinas criar histograma funcionario empreiteiro ankara | tela: equipes/integrantes | botao: Equipes | telas: equipes | permissao: equipes -->
Administrativo › Equipes. A Engenharia e a Administração criam as equipes por empresa (Ankara, Empreiteiro 1,
Empreiteiro 2), designam os integrantes e cadastram as máquinas. Equipe sem integrantes não recebe lançamento. As
equipes não são as zonas: a programação diz onde cada uma trabalha.

## Diário de obra
<!-- palavras: diario obra dia resumo programado executado ocorrencias clima pessoas | tela: diario | botao: Diário de obra | telas: diario -->
Execução › Diário de obra: o dia de cada equipe — o que foi lançado, programado × executado, clima, pessoas, material,
soldas, fotos e ocorrências. O encarregado vê só a equipe dele; quem não vê as notas de serviço vê o dia sem a nota.

## Relatórios
<!-- palavras: relatorio relatorios avanco pendencias ciclo material mensal word rm pdf | tela: relatorios/avanco | botao: Relatórios | telas: relatorios -->
Administrativo › Relatórios: Avanço, Pendências e Ciclo do material, e o relatório mensal (RM) da medição em Word
editável. O que não tem fonte sai marcado PENDENTE, nunca zero.

## Usuários, senha e histórico
<!-- palavras: usuario usuarios senha trocar esqueci login perfil historico auditoria link drive acesso criar | tela: admin/usuarios | botao: Usuários e histórico | telas: admin -->
Administrativo › Usuários e histórico (Engenharia e Administração): criar e desativar usuários, ver o histórico e ligar
o Google Drive. Quem tem histórico é desativado, não excluído. Qualquer pessoa troca a própria senha em “Trocar senha”,
no pé do menu lateral. Senha esquecida: peça à Engenharia ou à Administração.

## Quando o sistema recusa
<!-- palavras: erro recusa recusou nao deixa travou trava bloqueado bloqueio porque nao consigo mensagem falta motivo | tela: | telas: -->
Recusas comuns e o que fazer: “falta a liberação topográfica” → registrar antes a NS de topografia do trecho; “data
futura” → só se registra o que já aconteceu; “equipe sem integrantes” → designar em Equipes; “quem informou não
verifica” → outra pessoa verifica; “OK interno exige a verificação” ou “as fotos” → verificar e enviar as fotos na
ficha; “avanço anterior sem posição” → conciliar o legado; “medição fechada” → o estorno não desfaz medição fechada
(D-16); “seu perfil não tem a permissão” → peça a quem tem. A mensagem da recusa diz o trecho, os metros ou o item.

## Valores, prazos, saldos e situação atual
<!-- palavras: valor valores prazo prazos saldo quanto falta situacao status contrato data termino medido contratado andamento | tela: | telas: -->
Esses números mudam e não ficam neste guia. O assistente consulta na hora a situação de um trecho (o que já foi feito e
o que falta para o OK) e o saldo de um item do orçamento. Contrato, valores e prazos ficam em Administrativo › Medição e
› Projeto e cronograma; o andamento, no Mapa iluminado e em Relatórios › Avanço.

## Glossário da obra
<!-- palavras: significa sigla o que e quer dizer glossario ns pb tr de dn mnd vca bm mc gdoc eset caesb ankara pead zona subadutora no caixa | tela: | telas: -->
NS: nota de serviço da Caesb. PB: prancha do projeto. TR: trecho de rede entre dois nós (a numeração recomeça em cada
PB; o nome completo é Zona 03 · PB06 · TR014). Nó: conexão; caixa: DF, VTF, VM, VRP, MV, HID. DE: diâmetro externo do
tubo PEAD. MND: método não destrutivo (sem vala). BM: boletim de medição; MC: memória de cálculo. GDOC: protocolo de
documentos da Caesb; ESET: memorando de aprovação do cadastro. Subadutora: a frente dos tubos de DE 200 mm para cima.
