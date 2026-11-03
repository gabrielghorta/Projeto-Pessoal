# O web app do Morro da Cruz: ciclo, arquitetura, telas e regras

Referência da skill `sistema-morro-da-cruz`. Leia a seção do assunto que vai mexer. A fonte de verdade é o repositório
(`morro-da-cruz/docs/`, `config/` e o código): se algo aqui divergir, vale o repositório e este arquivo deve ser corrigido.

Conteúdo:
1. O ciclo da obra até a medição (ponta a ponta)
2. Arquitetura técnica — mapa do código; banco (SQLite) e esquema
3. Importação e identidade
4. Trecho físico (topologia)
5. Perfis, telas, permissões e segregação
6. Execução — notas de serviço; lançamento do dia; intervalos, verificação, soldas, fotos e ocorrências; cadastro e
   esteira; apropriação direta
7. Planejamento e almoxarifado (Dados da obra, estoque, pedir material, requerimentos, compras e notas)
8. Mapas (Mapa iluminado, Subadutora, nós e caixas, Dados da obra, foco por zona, REV02, desempenho)
9. Como trabalhar neste repositório (restrições, interface, esquema, rotas, testes, armadilhas)

## O ciclo da obra até a medição (ponta a ponta)

```
planilhas oficiais ─► importação (controles aprovados) ─► banco
        │
Planejamento: Cronograma (Project, macro) · Dados da obra (o dia: equipe + trechos, liberar o material)
        │
1. Topografia: NS de topografia ─► liberação topográfica (azul-claro no mapa)
2. Execução: a engenharia envia a NS do dia da equipe ─► assentado/reaterrado/escavado INFORMADO (amarelo)
3. Supervisor verifica (quem informou não verifica) + 3 fotos (sinalização, execução, concluído) ─► verificado (rosa)
4. Cadastro de campo: NS de cadastro ─► levantamento sobre o executado (ciano)
5. Completo + verificado + fotos ─► pronto para o OK (branco)
6. OK interno (Engenharia/Administração) ─► lançamentos na medição de TESTE (roxo) + esteira 1_PRONTO
7. Esteira do cadastro: empresa ─► recebido ─► conferência interna ─► protocolo GDOC ─► memorando ESET (verde)
8. Medição: conferência interna CONFORME ─► fechamento (congelado) ─► pacote no modelo oficial do BM
```

**Ordem obrigatória (D-20 decidida, D-115):** assentamento e escavação só sobre liberação topográfica até a data
(apontamento, NS do dia ou retificação); NS de serviço só sobre trecho liberado até a data da nota; cadastro de campo
só sobre o executado até a data. O que falta é recusado com a mensagem exata, por exemplo
"Zona 03 · PB06 · TR014, de 12,0 m a 30,0 m: falta a liberação topográfica (registre a NS de topografia antes)". A
liberação já usada pela execução não é anulada; o legado fora de ordem é listado ("Fora de ordem (legado)"), nunca
apagado. A apropriação direta fica fora da regra.

**Caminho até a medição** (ficha do trecho, bloco "Para entrar na medição", `servicos.caminho_medicao`): liberação →
executado 100 % (assentado e reaterrado) → verificado → 3 fotos → cadastro de campo → OK interno (data não anterior ao
último serviço registrado, D-189). O OK interno exige
execução 100 %, as fotos obrigatórias e **todos os intervalos efetivos verificados** (D-112); não depende de medição
aberta (D-113: os lançamentos esperam em `SEM_MEDICAO_ABERTA` e entram quando a medição do período abre).

## Arquitetura técnica

- **Python 3.11+ só com biblioteca padrão** + `openpyxl` (planilhas), `pypdf` (NS em PDF) e `pillow` (opcional:
  satélite, decodificação das fotos, galeria da medição). **Sem framework, sem dependência nova, sem CDN, sem
  biblioteca de mapa.** Interface HTML/CSS/JS puro (só fontes do Google Fonts, com fonte do sistema de reserva).
- **Servidor** `server.py` (`http.server`, um processo, uma conexão SQLite, `LOCK`): cada gravação é **uma transação**
  com permissão, restrição de equipe, autoria, reenvio e auditoria. Serviços aninhados viram `SAVEPOINT`
  (`servicos.transacao`); a externa usa `BEGIN IMMEDIATE`. Na recusa, tudo é desfeito e a auditoria da recusa é gravada
  fora da transação.
- **Rotas:** tabelas `GET`, `GET_PERM`, `GET_USUARIO`, `POST`, `POST_USUARIO`; `PERMISSAO` (permissão de cada gravação),
  `AUTOR` (campos de autoria preenchidos com o usuário da sessão), `TELA_GET`/`TELA_ARQUIVO` (tela exigida em cada
  consulta) e `COMUNS`. **Asserts** no carregamento: toda rota de gravação tem permissão e toda consulta tem tela — o
  servidor não sobe se faltar.
- **Segurança:** senha PBKDF2-SHA256 (200 mil iterações, sal); 5 falhas em 15 min bloqueiam; cookie `HttpOnly`,
  `SameSite=Strict` (e `Secure` + HSTS na nuvem); gravação exige o cabeçalho `X-MC` (CSRF); reenvio idempotente por
  `X-Idem` (por usuário); corpo acima de 32 MB recusado (413) sem ler; base64 de arquivos fora da auditoria; arquivos de
  NS servidos `inline` com `nosniff` e `Content-Security-Policy: sandbox`.
- **Relógio:** `relogio.py` — hoje e agora de **Brasília** em todo o servidor (o PythonAnywhere roda em UTC; D-109).
  Data futura é recusada em tudo o que registra o que aconteceu (execução, clima, fotos, estoque, OK); programação,
  reserva e período de medição podem ser futuros.
- **Hospedagem:** site no **PythonAnywhere** (grátis, 512 MB, um clique por mês para manter), instalado por
  `instalar_pythonanywhere.sh` a partir do ramo do site; alternativa Render (pago, `render.yaml`); `nuvem.py` (modo
  nuvem: nada é "o próprio computador"); no Windows, `MorroDaCruz.exe` (PyInstaller, `iniciar.py`) com link temporário
  pelo túnel da Cloudflare (`link.py`). Na nuvem o banco é o de **demonstração** (`dados_demo/`, faixa DEMONSTRAÇÃO)
  até a aprovação dos controles (D-01); o site migra o esquema sozinho ao recarregar, com backup verificado antes.
- **Google Drive** (`drive.py`, v15/v16): fotos sobem para `03_EXECUCAO_DE_CAMPO/01_Fotos_por_Trecho/<Zona>/<trecho>`,
  notas para `04_COMPRAS_E_ALMOXARIFADO/01_Notas_Fiscais/<AAAA-MM>`, NS para
  `03_EXECUCAO_DE_CAMPO/02_Notas_de_Servico/...`, apropriações para `03_Apropriacao_Direta/<AAAA-MM>`, base de custo em
  `05_MEDICAO/01_Base_de_Custo`. A foto original pode ficar só no Drive depois de conferida pelo MD5 (fica a miniatura
  e o SHA-256 no servidor, D-65).
- **Pastas:** `planilhas/` (oficiais, versionadas por decisão do responsável; nunca alteradas), `mapa/` (REV02),
  `config/`, `dados/` ou `dados_demo/` (banco, `fotos/` e `documentos/` pelo SHA-256, `backups/`, `relatorios/`,
  `logs/servidor.log` com rotação 5 × 2 MB). Dados da obra **não** vão para o Git.

### Mapa do código

| Arquivo | O que faz |
|---|---|
| `server.py` | Rotas, sessões, permissões, auditoria, downloads, injeção da camada no REV02 |
| `servicos.py` | Casos de uso: alvos, almoxarifado, campo, fotos, OK interno, esteira, medição, resumo, congelamento |
| `regras.py` | Regras puras (sem banco): BM (`totalizar_bm`, `produto_excel`), fotos, etapa no mapa, esteira, roteiros, reajuste |
| `importacao.py` / `importar.py` | Importação idempotente com simulação, controles, proveniência e migrações `preparar_vNN` |
| `acesso.py` / `usuarios.py` | Senha, sessão, permissão, auditoria, reenvio / terminal de usuários |
| `notas_servico.py` / `ns_leitura.py` / `planilha_xls.py` | NS: casamento com o trecho físico, registro, NS do dia / leitor do PDF / leitor .xls (BIFF8) |
| `topologia.py` | Trecho físico (cadeia de linhas da 06.1), `config/topologia.json` |
| `terceirizadas.py` | Resumos da Topografia e do Cadastro de campo (feito × falta) |
| `compras.py` / `nfe.py` | Compras, NF (XML e digitada), conferência, recebimento num toque, inspeção, inventário / leitor do XML da NF-e |
| `dados_obra.py` / `planejamento.py` / `cronograma.py` | O dia da equipe no mapa / camadas e caminho da medição / MS Project |
| `medicao.py` | Regras da medição, duplicidades, parcelas, elegibilidade, conferência interna |
| `apropriacao.py` | Apropriação direta, base de custo, itens a aprovar, sincronização das restrições |
| `pacote_medicao.py` / `xlsx_modelo.py` | Pacote mensal no modelo oficial do BM / edição de .xlsx por dentro (XML) |
| `exportar.py` | Resumo interno da medição (.xlsx de conferência) |
| `relatorios.py` / `diario.py` | Relatórios de operação / diário de obra e interferências |
| `mapa_geral.py` | Visão geral do REV02 para o Mapa iluminado (satélite, zonas, traçado) |
| `imagens.py` | Validação de imagem, miniatura |
| `documentos.py` / `drive.py` | Documentos oficiais (links do Drive) / ligação com o Drive |
| `backup.py` | Backup verificável e restauração |
| `relogio.py`, `caminhos.py`, `nuvem.py`, `link.py`, `iniciar.py`, `demo.py` | Relógio, pastas, nuvem, túnel, executável, demonstração |
| `web/app.js` | Interface: menu, telas, páginas dentro da aba, medição, almoxarifado… |
| `web/iluminado.js` | Visor do Mapa iluminado e da tela Início (gesto, cores, fichas) |
| `web/planejamento.js` | Dados da obra e cronograma |
| `web/notas.js` | Envio em lote e conferência das NS (`criarFilaNs`, `montarEnvioNs`) |
| `web/apropriacao.js` | Apropriação direta e base de custo |
| `web/mapa_iluminado.js` | Camada injetada no REV02 |

### Banco (SQLite) e esquema

`schema.sql` + `VERSAO_ESQUEMA` em `servicos.py`. Banco em versão anterior é recusado (`EsquemaAntigo`) até a
migração (`python importar.py --aplicar`, servidor parado; na nuvem o site migra ao recarregar). Marcos: v3 identidade
estável · v5 estoque (reservas, estornos, custódia) · v7/v8 intervalos, retificação, foto original · v9 acesso · v10
liberação e ocorrências · v11 compras · v12 programação · v13 parcela única e conferência da medição · v14 documentos ·
v15/v16 Drive · v17 levantamento avulso · v18 NS · v19 apropriação e gaveta 5 · v20 `checkin_alvos`, NF sem pedido,
romaneio · v21 `medicao_folhas` (fotos e justificativa da memória de cálculo) · **v22** solicitação de material
(`solicitacao_detalhes`, `solicitacao_avulsos`, `solicitacao_notas`), entrega por linha (`nf_entregas_linhas`,
`nf_confirmacoes`) e `nf_liberadas_v22`.

Tabelas centrais: `trechos`, `elementos`, `atividades`, `itens_projeto`, `bm_itens` (planilha JUNTADA/VERTICAL, item,
código Caesb, classificação, quantidade, preço sem BDI, `linha_origem`), `intervalos_execucao`, `apontamentos`,
`etapas_complementares` (liberação, escavação), `fotos`, `soldas`, `execucao` (concluído, OK, medição), `cadastro`
(esteira), `notas_servico`/`ns_segmentos`, `materiais`, `movimentos`, `reservas`, `checkins`/`checkin_alvos`,
`notas_fiscais`/`nf_linhas`/`nf_itens`, `medicoes`, `medicao_lancamentos`, `conferencias_medicao`, `medicao_folhas`,
`apropriacoes`, `itens_novos_base`, `codigos_oficiais`, `usuarios`, `sessoes`, `auditoria`, `requisicoes`,
`parametros`, `proveniencia`, `fontes_arquivo`, `alteracoes`.

**Princípios do banco:** nada é apagado (o que sai de uma revisão fica `vigente = 0`; correção é por estorno,
anulação ou retificação com motivo e autor); o que não tem fonte fica **pendente**, nunca zero nem chute; o banco não
é editado à mão.

## Importação e identidade

| Fonte | Entra | Conferência |
|---|---|---|
| 06.1 REDES REV01, aba REDE | trechos, perfil de vala, quantidades, pontas, handle, código BM | 1.436 · 110.686,03 m |
| 06.2 CONEXÕES REV08 | elementos (handle), atividades, itens, unidade, BA/BB/AW/AG/AH, avisos | 1.191 · 1.242 · 6.539 |
| EVIDÊNCIAS REV08 | agrupamento, zona, status de posição | 1.191 de 1.191 grupos iguais |
| BM REV04 | juntada e vertical; BDI, K e totais do rodapé | 347/432; P0 = T556 |
| 03.3.2 REV03 REAJUSTE | data-base, aniversário, índice | — |

- **Simulação por padrão**; `--aplicar` faz trava de manutenção + backup verificado + tudo numa transação. As
  conferências rodam **antes do COMMIT** (controles CTRL-01 aprovados pelo SHA-256 de cada arquivo, totalização do BM
  igual ao rodapé, identidade com histórico). Reprovou → rollback, banco byte a byte igual, relatório em `relatorios/`.
- **Controles:** `config/controles.json` precisa do bloco `aprovacao` preenchido **pelo responsável** (D-01, ainda
  pendente). Os testes e a demonstração usam o perfil TESTE.
- **Identidade:** trecho `TR-00001` = handle CAD + pontas UTM (o handle sozinho se repete); elemento `EL-0001` = handle
  (provisório pelo número, promovido quando o handle aparece); atividade `AT-0001` = elemento + frente; item
  `IP-000001` = atividade + assinatura técnica completa. **Nunca pelo nº da linha, pela ordem ou só pelo nome.**
- Histórico só muda de identidade por de-para explícito (`config/conciliacoes.json`); trecho com histórico sem par
  reprova a importação. Proveniência por registro (arquivo, SHA-256, aba, linha, células). Reimportar igual =
  `SEM_ALTERACOES`. Decisões (`config/decisoes.json`) nunca são alteradas pela reimportação e só se ligam a avisos por
  vínculo explícito.
- **Unidades (N02):** nunca se misturam; UN ≠ PÇ; sem fonte = PENDENTE (361 linhas "APROVAR — sem item no BM").
- **Perfil de vala (E06):** "A CONFIRMAR", incompleto ou volume negativo bloqueia o cálculo; MND não exige perfil.

## Trecho físico (topologia)

Duas regras do responsável: **"todo trecho termina em algum tipo de conexão"** e **"rede que passa por outra com um
semicírculo é o mesmo trecho"**. A 06.1 continua intacta para o BM e a medição; o trecho físico é uma visão por cima
(cada linha com `offset_m` e sentido), que converte um intervalo da NS em intervalos de cada linha.

- Juntam: cruzamento com semicírculo; tubo que passa ao lado do nó sem peça para ele; divisa de zona e limite de MND
  (mesmo ponto, mesmo DE); emenda sem nó (folga ≤ 1,0 m, ângulo ≥ 120°). Não juntam: quando as peças do nó (orçamento
  de bocas: tê 3, curva/redução/válvula 2) ligam o par; 3 ou mais tubos sem nó (tê faltando na 06.2); troca de DE ou
  material.
- **Conexão no meio de uma linha da 06.1** (29 casos: 23 ventosas, um hidrante, 5 nós): a NS corta ali e a 06.1 não; o
  segmento vira o intervalo da linha até a conexão.
- Resultado: 1.358 trechos físicos, 48 com mais de uma linha. Ferramentas e diagnóstico em `ferramentas/topologia/`.

## Perfis, telas, permissões e segregação

Menu principal: **Mapa iluminado · Execução · Planejamento · Administrativo** (D-67, D-75).
- Execução: Lançamento do dia, Notas de serviço, Topografia, Cadastro de campo, Interferências e ocorrências, Diário de obra.
- Planejamento: Dados da obra, Cronograma da obra, Estoque e movimentos, Pedir material, Compras e notas.
- Administrativo: Equipes, Relatórios, Usuários e histórico, LEV, Medição.
- Links antigos redirecionam: `#prog` e `#ponto` → Dados da obra; `#esteira` → Mapa iluminado.

| Perfil | Telas | Permissões |
|---|---|---|
| ADMINISTRACAO, ENGENHARIA | todas | todas (26), inclusive usuários |
| ALMOXARIFADO | Mapa iluminado, Lançamento do dia, Diário, Interferências, Dados da obra, Estoque, Pedir material, Compras | `almox`, `receber`, `inventario_contar`, `compras_solicitar`, `campo` |
| SUPERVISOR | Mapa iluminado, Lançamento do dia, Notas de serviço (consulta), Diário, Interferências, Pedir material | `campo`, `verificar`, `compras_solicitar` |
| EQUIPE (encarregado, preso à equipe) | Mapa iluminado, Lançamento do dia, Diário, Interferências, Pedir material | `campo`, `compras_solicitar` |
| RH | Mapa iluminado, Notas de serviço (consulta) | — |
| TOPOGRAFIA (consulta) | Mapa iluminado, Topografia | — |
| CADASTRO | Mapa iluminado, Cadastro de campo | `cadastro` |

Permissões: `usuarios`, `auditoria`, `equipes`, `almox`, `receber`, `compras_solicitar`, `compras_aprovar`,
`fornecedores`, `nf_confirmar`, `inventario_contar`, `inventario_ajustar`, `campo`, `topografia`, `cadastro_campo`, `verificar`,
`retificar_campo`, `ok_interno`, `cadastro`, `conferir_cadastro`, `planejar`, `medicao`, `documentos`, `notas_servico`,
`lancar_sem_ns`, `ns_dia`, `apropriacao`. A matriz é provisória (D-10) e mora em `config/perfis.json`.

**Segregação de funções (sempre pela identidade da sessão; o nome digitado é ignorado):**
- quem informa não verifica (intervalos, soldas: nem o soldador nem quem informou);
- quem pede material não aprova o próprio pedido;
- quem digita a NF não a confere;
- quem conta o inventário não aprova o ajuste;
- a engenharia envia as NS (inclusive a do dia, em nome da equipe); o supervisor verifica.

**Quem vê as notas de serviço (D-134):** Administração, Engenharia, RH e Supervisor. Equipes e almoxarifado não veem
a aba, as listas, os PDFs nem os croquis (no Diário, o dia sem a nota). Topografia e Cadastro veem as do tipo deles.

Usuários: o sistema **nunca cria usuário sozinho** (o primeiro é criado pelo terminal: `python usuarios.py criar`).
Quem tem histórico é desativado, não excluído. Demonstração: `admin.demo`, `eng.demo`, `eng2.demo`, `almox.demo`,
`almox2.demo`, `equipe.demo`, `topo.demo`, `cadastro.demo` (senha pública; sempre desativados na nuvem).

## Execução

### Notas de serviço (D-69 em diante)

| Tipo | Onde (Execução ›) | Quem envia | Arquivos | O que grava |
|---|---|---|---|---|
| Topografia | Topografia › Enviar NS de topografia | Engenharia/Administração (`notas_servico` + `topografia`) | PDF | liberação topográfica, só no que não estava liberado |
| Cadastro de campo | Cadastro de campo › Enviar NS de cadastro | Engenharia/Administração (`notas_servico` + `cadastro_campo`) | PDF | cadastro de campo só sobre o executado até a data; o resto fica escrito e volta à mão ("Aplicar de novo") |
| Serviço de obra | Notas de serviço › Serviço de obra | Engenharia/Administração | PDF + croqui | o plano da zona; nada nos trechos; não acende o mapa |
| NS do dia | Notas de serviço › NS do dia | Engenharia/Administração em nome da equipe (`ns_dia`) | PDF + croqui + clima | assentado, reaterrado e escavado **informados** |

**Leitura (não grava nada):** contrato só por número/ano (`10239/26`; outro contrato é recusado); contas da nota
(profundidade = terreno − GI; estaca × 20 + fração = acumulada; parciais = RESUMO = TOTAL GERAL; folhas "x de y"
completas; data não futura); PDF sem texto é recusado (sem OCR); duas leituras (pypdf e pdftotext, ou PDF e
planilha) precisam dizer o mesmo. Croqui em PDF com texto: confere número, contrato e data (aviso "confira o croqui";
o desenho não é lido, D-74).

**Casamento segmento × trecho:** cada par de elementos consecutivos do grupo vira um segmento, casado com o trecho
físico na zona e PB da nota. Automático até max(0,10 m; 0,5 %) de diferença; confirmar entre 0,5 % e 5 % ou com mais
de um trecho possível (o mesmo par de nós em outra PB é sempre "confirmar", D-73); erro acima de 5 % ou DE/método
diferente; sem correspondência → só deixar de fora com motivo. "Registrar" só libera com tudo conferido; registra numa
transação, por linha da 06.1, com a referência `NS 012 fl. 01/01` e o `ns_segmento_id`.

**Reenvio:** o mesmo arquivo é recusado; mesmo conteúdo em outro arquivo troca só o arquivo; mesmo número com outro
conteúdo exige anular a anterior (motivo; anula liberações e retifica cadastros, sem apagar). Chave da NS: (contrato,
tipo, número) (D-70). Envio em lote: até 20 arquivos; croqui e planilha casam pelo número escrito neles (D-119).

**NS do dia:** etapa pelo título e observações (ASSENT… → assentado; REATERR… → reaterrado, só sobre assentado;
ESCAV…/VALA ABERTA → escavado; nada escrito = assentado, com aviso). Distância menor = execução parcial a partir do
elemento de menor estaca. Linha sem elemento no fim = parada: o sentido vem do trecho em que a nota vinha → outro
elemento citado → programação do dia da equipe → NS de serviço da zona → a engenharia (D-84). MND: escavação e
reaterro pulados. O que não é inequívoco vai para a fila **NS do dia a conferir** (Engenharia), sem gravar. Nota
com mais de 3 dias de atraso entra com aviso. Nós e caixas na NS do dia: ABERTA (D-85), só à mão.

**Clima:** obrigatório nos dois turnos. A NS do dia é a fonte principal (D-131): o clima tocado no envio dela
substitui o do Clima do dia; sem toque, vale o marcado; depois que a NS chega, o Clima do dia só preenche turno vazio.

### Lançamento do dia (o lançamento solto, sem NS)

Quatro páginas, cada perfil vê as dele (chips no topo, a página no endereço `#campo/fotos`, lembrada na sessão):
**Apropriação direta** (`apropriacao`), **Apontamento sem NS** (`lancar_sem_ns`, motivo obrigatório; nó e caixa
continuam aqui), **Fotos e soldas** (`campo`) e **Clima do dia** (`campo`; o encarregado só a equipe dele).

### Intervalos, verificação, soldas, fotos e ocorrências

- **Intervalos por etapa** no trecho (ASSENTADO, CADASTRO_CAMPO, REATERRADO), de x m a y m no sentido da 06.1.
  Recusados: sobreposição, repetição, fora do trecho, reaterro ou cadastro sobre o não assentado até a data. MND só
  ASSENTADO e CADASTRO_CAMPO. "100 % concluído" preenche só as lacunas. Apontamento só em metros (sem posição) é
  recusado. Avanço antigo sem posição fica como **legado pendente** até a conciliação (mesma soma, sem gerar
  quantidade).
- **Retificação:** corrige o conjunto completo de um apontamento (vazio anula), valida o trecho inteiro antes de
  gravar, guarda antes × depois, motivo e autor. Não vale depois do OK interno (D-16).
- **Verificação:** cada intervalo guarda quem informou; outra pessoa verifica (`verificar`). Mapa: INFORMADO, PARCIAL,
  VERIFICADO, LEGADO_SEM_POSICAO.
- **Soldas:** informadas (tipo, quantidade, soldador) e verificadas por outra pessoa (APROVADA/REPROVADA com motivo).
  A estimativa ⌈L/6⌉ é só referência e nunca vira quantidade.
- **Fotos:** trecho = 3 (sinalização, execução, concluído); nó/caixa = 2, herdando a sinalização de um trecho ligado
  (senão 3). Original guardado byte a byte pelo **SHA-256**; validada como imagem (Pillow decodifica; sem Pillow, PNG
  decodificado e JPEG estrutural); HEIC recusado; até 20 MB; data EXIF > aparelho > envio; GPS EXIF > navegador >
  indisponível (nunca inventado); a mesma imagem não serve para outro registro; o **carimbo é texto exibido**
  (`contrato | alvo | data-hora | GPS`), não gravado na imagem.
- **Liberação e escavação** (por intervalo, com referência); **ocorrências**: impedimento ou não conformidade, com
  categoria, resolução obrigatória para fechar, sem reabrir.

### Cadastro: quatro fases e a esteira

Levantamento de campo (vala aberta, com referência) → preparação pela empresa → **conferência interna Ankara**
(roteiro de 6 itens: extensão, traçado, profundidade, material/DE, peças e nós, arquivos; NÃO CONFORME devolve à
empresa) → GDOC.

Esteira (`regras.ETAPAS`, ações na ficha do trecho, D-114): `1_PRONTO` → `2_ENVIADO` (empresa, data) → `3_RECEBIDO`
(arquivos) → `4_GDOC_ANALISE` (protocolo) → `6_APROVADO` (memorando ESET) ou `5A_NEGADO` (motivo) → `2_ENVIADO`
(nova revisão). Só o `6_APROVADO` é decisão da Caesb (verde) e gera a gaveta 3 da medição.

### Apropriação direta (D-90 a D-97)

Lançamento direto no item do orçamento, sem NS (ex.: canteiro feito por equipe de outra obra da Ankara). Item
escolhido como no BM vertical (grupo → material/serviço → item) ou pela **busca única** (item, código Caesb,
descrição, DE, material, sinônimos TE/TÊ, PEAD, Ø/DE/DN, PVC, FOFO). Data não futura, quem executou (equipe, outra
obra, terceiro), o que foi feito, memória de cálculo, justificativa e **pelo menos uma evidência**. Correção só por
estorno com motivo. Item que não está no BM: cadastro de item novo (a aprovar). Entra na medição pela gaveta 5.

## Planejamento e almoxarifado

**Dados da obra = o dia da equipe (D-104):** programar equipe + trechos (só dentro da zona: cada toque soma,
Desselecionar tira, D-186; o nó entre dois trechos escolhidos e a ponta de rua da 06.2 entram
sozinhos, D-178; a equipe já vem a da frente, D-179; DE 225, 250 e adutora → EQUIPE ADUTORA, D-182) para um dia
ou período (uma programação por alvo e dia, num lote cancelável) → o
almoxarife **libera o material do dia** (sugestão do projeto: tubo pelo que falta assentar, peças dos nós pela 06.2 →
BM vertical, limitada ao que há no almoxarifado), o que abre o check-in com todos os trechos (`checkin_alvos`) e acende
"em execução hoje" com o pino da equipe até a NS do dia chegar → **devolução** no fim do dia (aplicado, sobra, perda
com motivo, fica com a equipe). Dia futuro vira reserva. **Cronograma da obra** = XML do MS Project (ou .xlsx/.csv;
`.mpp` recusado), o macro de 18 meses, com tarefas ligadas a trechos citados no nome.

**Estoque:** disponível = físico − reservas; reserva por equipe e dia (no Dados da obra, só para dia futuro, D-192);
estorno só do que não tem caminho próprio (transferência volta por outra transferência, ajuste por nova contagem, nota
pela nota, retirada de check-in encerrado pela retificação, D-191); uma sessão aberta por equipe, fechamentos em
ordem, sem check-in retroativo; o que fica com a equipe é declarado e volta no dia seguinte; correção só por estorno
(com motivo, nunca deixando reserva descoberta) ou retificação do fechamento (mesma quantidade e data); empréstimo só
com documento, responsável e autorização; transferência entre equipes com as duas sessões abertas; inventário com
recontagem se o saldo mudou; reservas vencidas liberadas em lote com motivo.

**Pedir material (D-172, D-173):** o pedido de compra saiu (a nota fiscal diz o que foi comprado; as tabelas antigas
ficam). Tela **Pedir material** (`compras_solicitar`: almoxarifado, supervisor, encarregado só para a frente dele,
engenharia, administração): tipo, tamanho e nome curto sem código, tirados da descrição (`solicitacoes.catalogo`;
ajuste em `config/materiais_pedido.json`), busca, "Não achei: escrever ou tirar foto", quantidade no − e no +, zona por
toque. **Meus pedidos** com cor e texto. A solicitação nunca trava nota nem estoque; ligar a nota a ela (`nf_confirmar`)
só marca "Chegou". **Requerimentos em Compras e notas (D-187):** os pedidos aguardando decisão, onde engenharia e
administração (`compras_aprovar`) aprovam num toque ou recusam com motivo (nunca o próprio) e identificam o item escrito
ou fotografado antes de aprovar; **A comprar** soma por material o aprovado que ainda não chegou (pedido − aceito das
notas ligadas, `solicitacoes.listar` → `falta`, `notas`); quem abre Compras vê os pedidos da obra. Pedir material só
aponta para lá. Transferência entre equipes, inventário e reservas vencidas ficam em **Estoque e movimentos**.

**Compras e notas:** NF por XML (biblioteca padrão; só UTF-8; DOCTYPE recusado; modelo 55; chave com dígito; repetida
recusada pela chave ou pelo fornecedor, número e série, D-190;
emitente cadastrado na hora pelo CNPJ do XML) ou digitada do PDF/imagem (anexo obrigatório; quem digitou não confere);
o fornecedor é cadastrado junto (`fornecedores`). **A nota sobe só em Compras e notas (D-170);** em Estoque › Notas a
receber, cada nota tem na lateral **Aceitar a entrega**, **Recusar a entrega** (o porquê é obrigatório; nada entra no
estoque e a nota fecha) e **Aceite ou recusa parcial** (o que não chegou continua a receber). **Conferir é marcar
(D-171):** cada linha mostra o material que o sistema reconheceu (código; nota anterior do fornecedor, com o fator; tubo
da Caesb pela bitola; descrição, sem contar PE 100 e SDR 17 como medida), com uma caixinha e "Marcar todas"; o verde
libera com todas marcadas. **Entrega antes da identificação (D-174):** a linha não reconhecida também é marcada (pela
descrição) e aceita; fica em `nf_entregas_linhas`, na unidade da nota, sem saldo, e aparece **faltando a confirmação** em
Compras e notas; quando a engenharia (`nf_confirmar`) diz o material e o fator, ela vira estoque uma vez só, com a data e
o recebedor da entrega (`recebimento.materializar`). **Corrigir** devolve à confirmação a linha reconhecida errada que
ainda não entrou no estoque. **Não existe aprovação da nota (D-175):** nota conferida e entrega aceita bastam; a migração
v22 lista em `nf_liberadas_v22` o que a regra antiga prendia. Tubo da Caesb vira `ROMANEIO_CAESB`, sem quarentena (D-111);
recusado, não entra no romaneio. Frete e serviço ficam fora do estoque; a nota só deles fecha no verde. A quarentena das
entregas anteriores à v22 segue a inspeção. **Material recebido nunca vira lançamento de medição.**

**Apontamento sem NS (D-180):** com a data e a equipe, aparecem como botões os trechos e nós de todos os check-ins dela
na data (abertos ou devolvidos), com "já lançado hoje"; o toque abre o formulário de sempre (motivo sem NS, liberação da
topografia, intervalo sem sobreposição), e a busca continua. Lançar vários a 100% de uma vez é proposta (D-181).

## Mapas

**Mapa iluminado** (`web/iluminado.js`, tela Início e Mapa iluminado): satélite das 25 PBs alinhado e cortado nas zonas,
zonas oficiais e o traçado dos 1.436 trechos, cor só pelo que foi gravado (`regras.etapa_trecho`, D-118):

| Etapa | Cor (clara, D-136) |
|---|---|
| Não iniciado | cinza `#B4B4B4` tracejado |
| Liberado pela topografia | azul-claro `#9FD1F5` |
| Em execução hoje (vale até a NS do dia chegar) | laranja `#F6936F` |
| Executado, aguardando verificação | amarelo `#F7DC8B` |
| Verificado pelo supervisor | rosa `#F7B3D6` |
| Cadastro de campo feito | ciano `#77D9E6` |
| Pronto para o OK interno | branco `#F7F7F7` |
| OK interno, na medição | roxo `#C6A9F7` |
| Cadastro em andamento (esteira 2 a 5A) | lilás `#E4D7FF` |
| Cadastro aprovado pela Caesb (ESET) | verde `#82E4B6` |

Ficha do trecho: caminho até a medição, verificação, fotos, esteira, histórico. Lista "Aguardando verificação" para o
supervisor, por zona, o mais perto primeiro. O pino diz "programado" (do check-in), não a posição real. Nada sem
posição no projeto ganha coordenada (MV-11, VTF-12, VTF-16 na bandeja, D-03).

**Subadutora (D-182):** adutora + redes de 200 mm pra cima (DE 225 e 250) = 132 trechos (~10,5 km), executados pela
EQUIPE ADUTORA e fora das zonas nos dois mapas e no HTML base (`ehSubadutora`/`zonaDoTrecho` no `iluminado.js`;
`isSub`/`pipeFront` no HTML). O nó que liga um trecho dela é da Subadutora; o que também liga trecho da zona fica nas
duas frentes. O `frente_id` do banco continua a zona do local.

**Nós e caixas (D-183):** nó = bola; DF ▼, VTF ▲, VM ■, VRP ◆, MV ⬢, HID ✚ (`TIPOS_NO`). No Mapa iluminado os trechos
ficam como estavam e os nós/caixas ganham a cor da situação (caixa sempre, nó só de perto; toque abre a ficha).

**Dados da obra (D-186, revoga a planta clara da D-184 e a D-177):** o Mapa iluminado (mesmo fundo escuro de satélite)
com os trechos na cor do diâmetro do projeto, finos (Subadutora mais grossa, MND tracejado) ou, à escolha na legenda, na
cor da programação; barra **Frentes** (Obra inteira, Zona 01 a 11, Subadutora). Seleção só dentro da zona: na obra
inteira o toque abre a zona; na zona cada toque soma; **Desselecionar** (modo) tira um a um; **Limpar seleção** zera.

**Foco por zona nos dois mapas (D-185):** só a zona escolhida tem cor, trechos, nós e equipes; as outras ficam sem
preenchimento, sem trechos e sem toque, com o contorno e o satélite, até "Obra inteira" ou outra zona pela janela Zonas.

**Mapa técnico REV02** (aberto à parte): camadas Andamento, Planejado (7 dias), Material, Informado × verificado,
Cadastro e Pendências, calculadas no servidor; modo Projeto restaura as cores de DE.

**Desempenho (D-98 a D-100):** durante o gesto o mapa se move por `transform` (desenho de verdade 150 ms depois ou ao
soltar); cópia leve em `<canvas>` por baixo para a borda; trecho tocado = o mais perto até 7 px; nós só na área
visível; tracejado por zona. Medição em `ferramentas/desempenho/`.

## Como trabalhar neste repositório

**Restrições permanentes:**
- **Não acesse o site nem o banco de produção.** Teste em bancos temporários (`tests/base_real.py` copia o banco das
  planilhas reais; `demo.py` usa `dados_demo/`).
- **Repositório público:** nunca versione PDF real de NS, nomes, telefones, e-mails ou CREA de pessoas; nada pessoal
  copiado dos modelos.
- Ramo do site: **não faça merge nem push em `claude/powerbi-modifications-wqxekj`**; trabalhe num ramo `claude/…` e
  abra PR. Commits, PR e código sem identificador de modelo de IA.
- Sem dependência nova (Python ou JS), sem framework, sem biblioteca de mapa, sem CDN.
- `pkill -f`/`pgrep -f padrão` casam com a própria linha de comando e matam o shell: guarde o PID (`$!`) ou filtre com
  `ps -eo pid,args | awk '$2 ~ /^python3/ && /server\.py --porta NNNN/'`.
- O `gh` não tem GraphQL neste ambiente: use a REST (`gh api repos/<dono>/<repo>/pulls …`).
- Português do Brasil, frases curtas, comentários curtos, vocabulário de água (não de esgoto).

**Interface:** mobile first; alvos de 44 px; **sem rolagem horizontal em 390 px** (tabela larga dentro de
`.tabela`, que rola no painel); tema escuro por padrão; sem variável global repetida entre scripts; páginas dentro da
aba pelo componente `PAGINAS` (endereço `#tela/pagina`, `sessionStorage` com `try/catch`); formulários esmaecidos sem a
permissão, mas quem decide é o servidor.

**Mudança de esquema:** subir `VERSAO_ESQUEMA` (`servicos.py`) e a descrição em `aplicar_esquema`; a tabela nova em
`schema.sql` (`CREATE TABLE IF NOT EXISTS`, com comentário de finalidade); `preparar_vNN` em `importacao.py`; a chamada
`if 0 < versao < NN` em `importar.py`; teste de migração. Nunca renomear tabela-pai com chaves ativas (recriar com outro
nome, copiar, descartar; `foreign_key_check` antes do COMMIT).

**Rota nova:** função em `server.py`; registrar em `GET`/`POST`; `PERMISSAO` e `AUTOR` (o autor é a sessão) para
gravação; `TELA_GET` ou `TELA_ARQUIVO` para consulta; download com `A.exigir` e `A.auditar`.

**Testes:** `python -m unittest discover -s tests` (483 testes em 29/10/2026, ~6 min; 2 pulados). Os de base real
exigem as planilhas em `planilhas/`. Navegador: Playwright com o Chromium do ambiente (`require('playwright')` funciona
de qualquer pasta; `chromium.launch()` sem opções): servidor de demonstração (`python3 server.py --db <cópia> --porta N
--demonstracao`, logins `eng.demo`, `eng2.demo`, `almox.demo`…), logar, abrir `abrirAba('<tela>')`, conferir rolagem
(`scrollWidth − innerWidth`), erros de página e respostas ≥ 500, em 390 e 1280 px. O menu lateral abre ao passar o
mouse e cobre botões: clique pelo DOM (`$eval(sel, b => b.click())`) ou mova o mouse para o canto.
LibreOffice (`soffice --headless --convert-to xlsx|pdf`) para recalcular e ver o pacote da medição.

**Documentação a atualizar junto com o código:** `docs/DECISOES_PENDENTES.md` (nova seção com as decisões, no formato
ID | Decisão | Opções | Impacto | Recomendação | Situação), o `docs/MODULO_*.md` do módulo, e o README quando muda a
operação.

**Armadilhas já vistas:** `sqlite3.Row` não compara com tupla (converta); `_palavras` devolve minúsculas; o PythonAnywhere
está em UTC (use `relogio`); openpyxl perde desenhos ao salvar (use `xlsx_modelo`); o LibreOffice só recalcula tudo
sem os valores guardados das fórmulas; fotos de teste precisam ser imagens decodificáveis (`tests/fotos_teste.py`);
`registrar_foto` recebe base64; o OK interno exige verificação, fotos e clima registrado nos testes.
