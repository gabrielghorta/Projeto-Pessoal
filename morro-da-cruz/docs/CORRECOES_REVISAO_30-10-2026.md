# Correções da revisão do código (30/10/2026)

CT 10239/2026 · pedido do responsável em 30/10/2026: revisar todo o código do repositório e os PRs abertos (#18, #19 e
#20) para achar bugs e corrigi-los. Ramo `claude/pensive-lamport-szymez`, empilhado sobre o #20
(`claude/skill-continuidade`). Mesclar depois do #18, do #19 e do #20, nessa ordem.

**Como foi feito.** O código foi lido por partes (servidor e acesso; medição; compras e estoque; notas de serviço e
topologia; campo em `servicos.py`; importação, planejamento e relatórios; telas; os PRs #18 e #19; o motor do
cronograma do #20). Cada achado foi conferido no código antes de mudar qualquer coisa: o que não se confirmou ficou de
fora, e o que é regra de propósito (há teste para isso) foi mantido. Antes: 483 testes, 0 falhas.

**O que não muda:** o banco (sem esquema novo), as planilhas oficiais, o HTML REV02, os números do cronograma entregue
em 29/10 (cenário A continua 95 m/dia e 23/03/2028; B, 90 m/dia e 12/04/2028) e a medição, que continua só de TESTE.

As mudanças de regra (o que antes passava e agora é recusado ou avisado) estão em `DECISOES_PENDENTES.md`, seção 20
(D-188 a D-195).

## Servidor, acesso e segurança

| Achado | Correção | Onde |
|---|---|---|
| Uma página de fora que troca o DNS para 127.0.0.1 (DNS rebinding) contava como "o próprio computador" e entrava sem senha pelo `/api/entrar-local` | `_local()` também exige que o endereço pedido (`Host`) seja localhost, 127.0.0.1 ou ::1 | `server.py` (`_host_local`) |
| `Content-Length` negativo passava pelo limite de 32 MB e o servidor lia a conexão até o fim, sem limite (antes do login); valor não numérico derrubava o pedido | Negativo ou inválido = 400, e a conexão fecha | `server.py` (`_ler_corpo`) |
| O encarregado baixava as evidências das apropriações de outras equipes pelo número do documento | Usuário preso à equipe só abre evidência de apropriação da equipe dele | `server.py`, `apropriacao.documento_da_equipe` |
| Usuário preso à equipe que mandava o pedido sem `equipe_id` (solda, ocorrência) gravava sem equipe | Sem equipe no pedido, vale a do usuário (D-195) | `server.py` (`_gravar`) |
| O segredo do cliente do Google Drive ia em texto para a auditoria (e para os backups) | `cliente_segredo` entra nos campos omitidos | `acesso.py` |
| Com a autorização do Google revogada, "Testar" e "Sincronizar" limpavam o token dentro da transação que a recusa desfazia: o Drive continuava "conectado" | A desconexão é gravada depois do rollback do pedido | `drive.py` (`_recusa_google`), `server.py` |
| Download da medição, do pacote e dos relatórios com parâmetro errado fechava a conexão sem resposta | Responde 400 (parâmetro) ou 500 (falha), com a mensagem | `server.py` (`_falha_download`) |
| A restauração de backup aceitava no manifesto caminhos com `..` e gravava fora de `fotos/` e `documentos/` | Manifesto com caminho inválido cancela a restauração antes de mexer em qualquer coisa | `backup.py` |
| COMMIT recusado (banco ocupado) deixava a conexão presa numa transação aberta: tudo o que viesse depois se perdia ao reiniciar | COMMIT que falha faz ROLLBACK | `servicos.transacao` |

## Medição

| Achado | Correção | Onde |
|---|---|---|
| Apropriação antiga num item que uma revisão do BM retirou travava a sincronização (abrir medição, decidir item, código oficial) e a lista das apropriações | O item é achado mesmo retirado; o que falta propor fica parado | `apropriacao.item(so_vigente)`, `_propor`, `resumo` |
| A apropriação direta aceitava o item da administração local: a tela somava e o pacote ignorava | Recusada: a ADM é proporcional ao faturamento (D-188) | `apropriacao.apropriar` |
| A ADM das medições anteriores era recalculada a cada pacote com o BM atual | A quantidade da ADM é congelada no fechamento e usada nos pacotes seguintes (D-194) | `servicos.congelar_medicao`, `pacote_medicao` |
| O pacote de uma medição fechada com outra revisão do BM não avisava que usa os preços do BM atual | Aviso no pacote (o valor congelado continua valendo) | `pacote_medicao.resumo` |
| Item medido antes e retirado do BM sumia do vertical sem aviso | Aviso com os itens (o acumulado do pacote fica menor que o medido) | `pacote_medicao.resumo` |
| Total do BM e valor da apropriação arredondados pelo Python (empate vai para o par: 286.267,775 dava ,77) | ROUND do Excel (meio para cima), como no resto do BM | `regras.totalizar_bm`, `apropriacao` |
| "CT 10.239/2026" virava contrato 239/2026 no pacote e na leitura da NS | O ponto de milhar é ignorado | `pacote_medicao._contrato_numero`, `ns_leitura.norm_contrato` |
| Estaca da memória de cálculo com 3 casas e a quantidade com 4 | 4 casas, como o lançamento | `pacote_medicao` |

## Compras e estoque

| Achado | Correção | Onde |
|---|---|---|
| "Corrigir" uma linha marcada como frete/serviço deixava a marca: a entrega aceita fechava sem entrar no estoque | Corrigir tira a marca; a linha volta a ser material a confirmar | `recebimento.corrigir` |
| O fator da nota anterior do fornecedor era reaproveitado mesmo com outra unidade (100 barras viravam 100 m) | Unidade diferente: o fator não é reaproveitado e a linha pede a confirmação | `compras.sugerir_materiais` |
| Estornar só uma metade da transferência criava ou sumia material com a equipe | Recusado: registre a transferência de volta (D-191) | `servicos.estornar` |
| Ajuste de inventário e entrada de tubo da Caesb por nota podiam ser estornados por fora da contagem e da nota | Recusados: nova contagem / trate pela nota (D-191) | `servicos.estornar` |
| Estornar a retirada de um check-in já encerrado deixava aquela sessão com aplicado sem retirada | Recusado: corrija pela retificação do fechamento (D-191) | `servicos.estornar` |
| Devolução ao fornecedor estornada continuava contando como devolvida | Devolução estornada sai das contas (saldo do pedido, a faturar, "A comprar") | `compras.py`, `solicitacoes.listar` |
| Nas rotas antigas de entrega e inspeção, quem digitou a nota podia recebê-la e aceitá-la | A mesma regra do recebimento num toque: quem digitou não confere | `compras.receber`, `compras.inspecionar` |
| A mesma nota sem chave (digitada) entrava duas vezes, inclusive depois pelo XML | Mesmo fornecedor, mesmo número e série = recusada, com ou sem chave (D-190) | `compras._nf_repetida` |
| Contagem de inventário sem data dava erro interno; com data futura gerava ajuste no futuro | Data obrigatória e não futura | `compras.registrar_contagem` |
| "A comprar" só via as 200 solicitações mais novas: um pedido aprovado antigo sumia da lista | As abertas e as aprovadas aparecem sempre | `solicitacoes.listar` |
| Devolvido ao fornecedor continuava como "chegou" na solicitação | O devolvido volta a faltar em "A comprar" | `solicitacoes.listar` |
| XML da NF-e em UTF-16 passava pela trava do DOCTYPE | NF-e só em UTF-8 | `nfe.ler` |

## Notas de serviço, topologia e campo

| Achado | Correção | Onde |
|---|---|---|
| NS de topografia mais antiga registrada depois de uma mais nova (mesmo trecho) ficava sem gravar: a liberação ficava com a data posterior e o serviço do meio era recusado | O lote registra da mais antiga para a mais nova; na leitura, aviso quando a liberação já existe com data posterior (D-193) | `web/notas.js`, `notas_servico.plano` |
| NS "012" e "12" eram tratadas como números diferentes | Os zeros da frente não contam na chave da NS | `notas_servico._ja_registrada` |
| O aviso "conexão no meio, a X m do início do segmento" media da ponta errada quando a NS vai contra o sentido da 06.1 | Medido a partir do primeiro elemento da NS | `notas_servico` |
| O estado da topologia era limpo e refeito no mesmo dicionário: um pedido em paralelo podia ler um estado pela metade | Dicionário novo a cada reconstrução | `topologia._estado` |
| Corrigir a posição de um avanço antigo já conciliado exigia a liberação da topografia, que a conciliação dispensa | A retificação da conciliação segue a mesma regra do legado | `servicos.retificar_intervalos` |
| Foto com EXIF de tipo inesperado dava erro 500 e não subia | EXIF ilegível é ignorado (vale a data do aparelho ou do envio) | `servicos.exif_jpeg` |
| Data EXIF "0000:00:00" era gravada como data da foto | Data inválida é ignorada | `servicos._ler_tiff` |
| GPS com divisão por zero jogava fora também a data da foto | Data e GPS lidos à parte | `servicos._ler_tiff` |
| No OK interno do nó, a mesma peça em duas unidades ia para o item do BM da primeira | O item do BM é escolhido pela peça e pela unidade | `servicos._lancar_ok` |
| Peça do nó sem quantidade derrubava o OK interno com erro 500 | O código do BM é achado sem somar quantidades | `servicos._lancar_ok` |
| OK interno com data anterior ao serviço caía numa medição de antes da obra | Recusado: a data do OK não pode ser antes do último serviço registrado (D-189) | `servicos.ok_fiscalizacao` |

## Importação, planejamento e relatórios

| Achado | Correção | Onde |
|---|---|---|
| Uma conciliação salva (`usar_id`) era registrada de novo a cada importação: reimportar igual não dava `SEM_ALTERACOES` | A conciliação já aplicada antes não é registrada de novo | `importacao._concil_aplicada` |
| Trecho sem as pontas UTM casava com outro trecho sem pontas e herdava o histórico dele | Sem pontas, a identidade exige também o handle e o mesmo nome | `importacao` |
| Trecho com DE vazio ou em texto derrubava a importação | Sem DE, sem tubo (o aviso vem da carga do trecho) | `importacao.materiais` |
| Cronograma em planilha com % em fração: 100 % (1,0) virava 1 % e a tarefa aparecia atrasada | Coluna em fração é lida toda como fração | `cronograma.py` |
| Trecho sem frente derrubava o relatório de avanço | Frente vazia aparece como "—" | `relatorios.avanco` |
| O diário da equipe só via as fotos do primeiro trecho do check-in | Valem todos os trechos e nós do check-in | `diario.py` |
| Programação com só o início ou só o fim do intervalo dava erro interno | Pede os dois | `planejamento.py` |
| Reserva no Dados da obra aceitava dia passado (e prendia o material de todos) | Reserva só para dia futuro (D-192) | `dados_obra.reservar` |

## Telas

| Achado | Correção | Onde |
|---|---|---|
| "Verificar e enviar as fotos": se a verificação falhava, a nova tentativa mandava as mesmas fotos e era recusada para sempre | A foto enviada sai do campo | `web/app.js` |
| "Retificar fechamento" com reservas sem cobertura não tinha como confirmar o ajuste | Pede a confirmação, como o estorno | `web/app.js` |
| Na retificação, "10,5" virava zero | Vírgula aceita; texto que não é número é recusado | `web/app.js` |
| Novo login depois da sessão cair mantinha o carrinho e a tela do usuário anterior | A página recomeça limpa | `web/app.js` |
| Falha ao carregar uma tela deixava a tela em branco, sem aviso | Aviso com o erro | `web/app.js` (`abrirAba`) |
| Foto que falhou ao subir era apagada do formulário | Fica para tentar de novo | `web/app.js` |
| Trocar de medição rápido mostrava os números da anterior | Resposta de outra medição é descartada | `web/app.js` |
| Depois de gravar, o mapa podia mostrar a leitura feita antes da gravação | Lê de novo depois da leitura em curso | `web/iluminado.js` |
| Nome da equipe no pino e dados da medição na lista entravam no HTML sem escapar | Escapados | `web/mapa_iluminado.js`, `web/app.js` |

## PRs #18 e #19 (mapas e estoque)

| Achado | Correção | Onde |
|---|---|---|
| "Liberar o material do dia" (e o lote, a ficha) abria o mapa na obra inteira com a seleção da equipe: o primeiro toque abria a zona e apagava a seleção | A seleção de uma zona só abre já nessa zona; abrir a zona da própria seleção não apaga nada; seleção de mais de uma zona pede confirmação | `web/planejamento.js` |
| "Ver no mapa" de um trecho de outra zona, com uma zona em foco, levava a um lugar vazio | Alvo de outra zona volta à obra inteira | `web/iluminado.js` (`focarAlvo`) |
| A ficha de um trecho de outra zona trazia a equipe da zona anterior | Troca de zona solta a equipe anterior | `web/planejamento.js` (`aplicarFoco`) |
| Recarregar o Estoque apagava o material escolhido na transferência e remarcava as reservas vencidas desmarcadas | O que foi escolhido fica | `web/app.js` |
| Falha ao carregar inventário e reservas vencidas era calada | Aviso | `web/app.js` |
| Buscar um nó que não liga trecho de zona, com a obra inteira, não fazia nada | Aviso dizendo o que fazer | `web/planejamento.js` |

## PR #20 (motor do cronograma)

| Achado | Correção | Onde |
|---|---|---|
| A busca da produtividade parava com intervalo de 0,31 m/dia e arredondava para cima: podia dizer 0,5 m/dia a mais que o necessário | Busca de 0,5 em 0,5 exata. Conferido na base real: continua **95,0 m/dia** (94,5 termina em 27/03/2028) | `motor.resolver_prazo` |
| Se nem 200 m/dia fechasse no prazo, `gerar_tudo.sh` parava com erro sem explicação | Mensagem dizendo para rever as premissas | `gerar.py`, `animacao_dados.py` |
| Bloco sem ligação também esperava os 5 dias das ligações | Só o bloco com ligação | `motor.programar` |
| O Gantt e a animação acabavam em 01/05/2028: obra mais longa saía cortada | O eixo vai até o mês seguinte ao fim | `gantt.py`, `animacao_dados.py` |
| Resumo sem tarefa (equipe sem bloco) derrubava o XML do Project | Resumo vazio com duração zero | `gerar_project.py` |
| Canteiro mensal e aluguel de contêiner faturados depois do fim da obra quando ela acaba antes da 18ª medição | Até o mês em que a obra acaba (nos cenários A e B nada muda) | `faturamento.distribuir` |

## Conferido e mantido

- **Tubo da Caesb reconhecido pela descrição em nota de outro emitente:** é de propósito (a remessa pode vir de quem
  transporta) e há teste (`test_remessa_da_caesb_vira_romaneio`).
- **Interligação das zonas antes da Subadutora entrar em carga (cronograma):** segue a premissa escrita em
  `cronograma-executivo.md` (a zona espera o teste da Subadutora, não a interligação dela). Fica como pergunta para o
  responsável validar (ver pendências).

## Pendências (não corrigidas aqui)

1. **NS do dia mais antiga enviada depois de uma mais nova** (mesmo trecho): o assentado fica com a data posterior. O
   lote não sabe a data da NS do dia antes de enviar; corrigir pede ler a nota antes do registro. Por ora: enviar na
   ordem das datas.
2. **Chamadas ao Google dentro da trava** (Testar, Desconectar, Sincronizar documentos): com o Google lento, o site
   espera. Pede tirar a rede de dentro da transação, como já é no envio das fotos.
3. **Cronograma:** a zona entra em carga em ago/2027, mas a Subadutora só em jan/2028 (ela espera a montagem das
   caixas dela). Validar com o responsável se a zona deve esperar a interligação da Subadutora.
4. Pequenos, sem efeito hoje: o material de um DE que saiu do projeto guarda a quantidade antiga; a conferência da NS
   do dia aceita depois de mudar a topologia; o backup feito durante o envio ao Drive pode dar "incompleto" (sem perda).

## Testes

`python3 -m unittest discover -s tests`: veja o resultado no PR. Testes novos em `tests/test_revisao_30_10.py`.
