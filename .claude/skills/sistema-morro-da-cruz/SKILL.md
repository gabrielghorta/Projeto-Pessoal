---
name: sistema-morro-da-cruz
description: Lógica completa do sistema web de gestão da obra Morro da Cruz (Ankara × Caesb, CT 10.239/2026) e da relação contratual entre a Caesb e a Ankara. Cobre planilhas oficiais e importação, perfis e segregação de funções, execução por nota de serviço (topografia → serviço → cadastro), fotos, verificação e OK interno, esteira do cadastro no GDOC, almoxarifado e notas fiscais, planejamento do dia, mapas, medição (gavetas, BDI, K, administração local, reajuste, conferência, congelamento), o pacote mensal no modelo oficial do BM, as decisões do responsável e as regras de trabalho no repositório. Use ao manter, corrigir, evoluir, testar ou explicar o sistema, ou ao produzir medição e relatório mensal para a Caesb.
---

# Sistema Morro da Cruz — a obra, o contrato Caesb × Ankara e o web app

Estado de 26/10/2026, esquema do banco **v21**, ramo do site `claude/powerbi-modifications-wqxekj` (repositório
`gabrielghorta/Projeto-Pessoal`, pasta `morro-da-cruz/`). Último PR desta fase: medição no modelo oficial do BM.

## 0. Como usar este arquivo

- É o mapa do sistema e das regras do negócio. **A fonte de verdade é o repositório:** `docs/DECISOES_PENDENTES.md`
  (todas as decisões, D-01 a D-157), `docs/MODULO_*.md`, `docs/NOTAS_DE_SERVICO.md`, `docs/TOPOLOGIA_TRECHOS.md`,
  `docs/MATRIZ_REGIMES_FATURAMENTO.md`, `config/*.json` e o código. Se algo aqui divergir deles, vale o repositório, e
  este arquivo deve ser corrigido.
- Decisão tem três situações: **DECIDIDA** (o responsável decidiu, com data), **PROVISÓRIA** (regra em uso, a
  confirmar) e **ABERTA/BLOQUEADA** (falta decisão ou fonte; o sistema trava e diz por quê).
- Regra de ouro do domínio: **o sistema nunca preenche aprovação, responsável autorizado ou condição da Caesb.** Toda
  conferência da Ankara (verificação, OK interno, conferência interna) é interna e aparece como tal.
- O modelo de medição e de relatório do Lago Sul (CT 10.159/2026) é referência de **formato**, não de números. Os
  parâmetros do Morro da Cruz estão na seção 1.

---

## 1. A obra e o contrato

| Item | Valor |
|---|---|
| Objeto | Implantação de Redes de Distribuição no Morro da Cruz, São Sebastião/DF |
| Contrato | CT **10.239/2026**, Caesb (contratante) × Ankara Engenharia (contratada) |
| Licitação | LC 014/2026 · Juntada 1426 (RED.SSB-D014) |
| Valor do contrato (cláusula 3.1) | R$ 49.878.748,56 |
| P0 recalculado do BM REV04 | R$ 49.878.748,6575869 (= célula T556 do vertical). A diferença de +0,0975869 fica **registrada, nunca ajustada** |
| BDI | material **15,28 %**, serviço **21,48 %**, por classe |
| Coeficiente K | **−14,04 %**: `K = −1 + (1 − 14,04 %) = −0,1404` (contrato 5.2) |
| Data-base | 31/01/2025 (preços fixos por 1 ano); 1º aniversário 31/01/2026 |
| Reajuste | ICC-Brasília-DI, **só com pedido da contratada**; até 3,29 % (Despacho 322/2026-CEFR, GDOC 2998208) |
| OS | 01/10/2026 · prazo **540 dias** · **18 medições** (pares de colunas no BM) |
| Administração local | item 4.1.1 (chave `6.2_4.1.1`), R$ 1.304.685,94, medida **proporcional ao faturamento do mês** (TR 14.6) |
| Rede | 1.436 trechos (linhas da 06.1), **110.686,03 m** de PEAD (1.400 Rede, 36 Adutora; 1.432 VCA, 4 MND); DE 63 a 500 |
| Tubo PEAD da rede | **fornecido pela Caesb**, fora do BM (SL0327 §6): a Ankara guarda, aplica e responde por perda; os serviços são medidos |
| Frentes | 13: Zona01 a Zona11, ADUTORA e CH (caixas hidráulicas) |
| Pranchas | 25 PBs (PB20 desenhada girada 90°; o vetor da PB25 está deslocado ~37,6 m no HTML) |
| Elementos (06.2) | 1.191 elementos físicos (1.059 nós + 132 dispositivos), 1.242 atividades (elemento × frente), 6.539 itens |
| BM REV04 | 347 itens na juntada, 432 no vertical |
| Ligações prediais | item de código Caesb 8005508120013 |

**Nomes:** a 06.1 nomeia `Zona01_PB01_Rede_TR001`; a tela mostra o nome completo `Zona 03 · PB06 · TR014`. "TR1" busca
o TR001 de cada PB (código inteiro, D-120). Os números de nó se repetem entre zonas e PBs (o NÓ1.1 aparece em 23
combinações): por isso o par de nós sozinho nunca identifica um trecho.

---

## 2. Quem é quem

| Parte | Papel no sistema |
|---|---|
| **Caesb** (contratante) | Fiscaliza; manda a nota de serviço (NS) no formato dela; fornece o tubo PEAD (romaneio); aprova o cadastro no GDOC (memorando ESET); dá o código oficial dos itens provisórios ("XX") e aprova item novo por ofício; a CEFR comunica o reajuste; a área ambiental faz o SAOB/IDA. |
| **Ankara** (contratada) | Engenharia e Administração (tudo), Supervisor de campo (verifica e fotografa), Almoxarifado (estoque e notas), Equipes (encarregados), RH (consulta das NS). |
| **Terceirizadas** | Topografia (locação, NS de topografia) e empresa de cadastro (levantamento de campo e desenho do cadastro). **Não entram no sistema para registrar:** a engenharia registra por elas (D-66); os perfis TOPOGRAFIA e CADASTRO só consultam. |

**Cores com significado contratual:** o **verde** é só da Caesb (cadastro aprovado com memorando ESET). Verificação e
OK interno usam outras cores (rosa, roxo, azul) e dizem "conferência interna Ankara — não é aprovação da Caesb".

---

## 3. Glossário

| Termo | Significado |
|---|---|
| 06.1 (LEV REDES REV01) | Planilha dos trechos: perfil de vala, quantidades (colunas AL:BK), pontas UTM, handle CAD, código do BM. **Unidade da medição e do BM.** |
| 06.2 (LEV CONEXÕES REV08) | Planilha das conexões: elementos, atividades, itens com quantidade, unidade pelo item da juntada, avisos AA/AB. |
| EVIDÊNCIAS REV08 | Conferência do agrupamento por handle, zona, status de posição, ID da auditoria. |
| BM REV04 | Boletim de medição oficial do Morro da Cruz: juntada (horizontal), vertical, 01ª MC, cronograma FF, reajuste, gráficos e conferência. Também é o **modelo** do pacote mensal. |
| 03.3.2 BM REV03 REAJUSTE | Data-base, aniversário e índice da CEFR. |
| REV02 (HTML) | `PLANTAS_TRECHOS_E_NOS_MORRO_DA_CRUZ_REV02_EQUIPES.html`: mapa técnico com satélite das 25 PBs; **nunca é alterado** (o servidor injeta a camada). |
| BM juntada (horizontal) | Uma linha por item do orçamento Caesb e colunas por medição; é a peça anexada ao processo. |
| BM vertical | Os mesmos itens repetidos por frente × material/serviço × categoria; chave `CódCronFF_ItemBM` (ex.: `2.2_5.8.44`). Alimenta o cronograma FF. |
| nª MC | Memória de cálculo do mês: uma folha por item medido (fotos, justificativa, memorial). |
| Cód. Cron. FF | Grupo do cronograma físico-financeiro (ex.: `2.2` REDES – SERVIÇO, `6.2` ADMINISTRAÇÃO LOCAL). |
| Código Caesb | Código da composição; liga o vertical à juntada. Só números = base Caesb; com "SI" = SINAPI; com "SC" = SICRO (todos contratuais); com "XX" = provisório (a aprovar). |
| P0 | Preço original, sem reajuste. |
| NS | Nota de serviço da Caesb (PDF; planilha opcional .xlsx/.xls). Tipos no sistema: topografia, cadastro, serviço de obra e NS do dia (execução). |
| Estaca | 20 m: `EST. 3+16,55` = 3 × 20 + 16,55 = 76,55 m. |
| VCA / MND | Vala a céu aberto / método não destrutivo (furo direcional; não tem vala, nem escavação nem reaterro). |
| Trecho físico | Cadeia de linhas da 06.1 entre duas conexões reais (`topologia.py`); a NS vai de conexão a conexão. |
| OK interno | "[✓] OK" da Ankara: trecho pronto para a medição; não é aprovação da Caesb. |
| Esteira | Etapas do cadastro até o GDOC (1 a 6). |
| GDOC / ESET | Sistema de documentos da Caesb / memorando que registra a aprovação do cadastro. |
| Gaveta | Grupo de lançamentos da medição (1 a 5, seção 12). |
| PROPOSTO / PENDENTE | Lançamento com item e regra com fonte (entra no valor) / sem item ou regra (fora do valor; **não é R$ 0 contratual**). |
| Romaneio | Entrada de tubo da Caesb (sem compra, sem quarentena de compra). |
| Quarentena | Material entregue e ainda não aceito na inspeção: **não é estoque**. |
| SL0327 | Norma de faturamento de material por etapas (80/20, 20/15/40/15/10, 80/10/10). |

---

## 4. O ciclo da obra até a medição (ponta a ponta)

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
executado 100 % (assentado e reaterrado) → verificado → 3 fotos → cadastro de campo → OK interno. O OK interno exige
execução 100 %, as fotos obrigatórias e **todos os intervalos efetivos verificados** (D-112); não depende de medição
aberta (D-113: os lançamentos esperam em `SEM_MEDICAO_ABERTA` e entram quando a medição do período abre).

---

## 5. Arquitetura técnica

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

### 5.1 Mapa do código

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

### 5.2 Banco (SQLite) e esquema

`schema.sql` + `VERSAO_ESQUEMA` em `servicos.py`. Banco em versão anterior é recusado (`EsquemaAntigo`) até a
migração (`python importar.py --aplicar`, servidor parado; na nuvem o site migra ao recarregar). Marcos: v3 identidade
estável · v5 estoque (reservas, estornos, custódia) · v7/v8 intervalos, retificação, foto original · v9 acesso · v10
liberação e ocorrências · v11 compras · v12 programação · v13 parcela única e conferência da medição · v14 documentos ·
v15/v16 Drive · v17 levantamento avulso · v18 NS · v19 apropriação e gaveta 5 · v20 `checkin_alvos`, NF sem pedido,
romaneio · **v21 `medicao_folhas`** (fotos e justificativa da memória de cálculo).

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

---

## 6. Importação e identidade

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

---

## 7. Trecho físico (topologia)

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

---

## 8. Perfis, telas, permissões e segregação

Menu principal: **Mapa iluminado · Execução · Planejamento · Administrativo** (D-67, D-75).
- Execução: Lançamento do dia, Notas de serviço, Topografia, Cadastro de campo, Interferências e ocorrências, Diário de obra.
- Planejamento: Dados da obra, Cronograma da obra, Estoque e movimentos, Compras e notas.
- Administrativo: Equipes, Relatórios, Usuários e histórico, LEV, Medição.
- Links antigos redirecionam: `#prog` e `#ponto` → Dados da obra; `#esteira` → Mapa iluminado.

| Perfil | Telas | Permissões |
|---|---|---|
| ADMINISTRACAO, ENGENHARIA | todas | todas (25), inclusive usuários |
| ALMOXARIFADO | Mapa iluminado, Lançamento do dia, Diário, Interferências, Dados da obra, Estoque, Compras | `almox`, `receber`, `inventario_contar`, `compras_solicitar`, `campo` |
| SUPERVISOR | Mapa iluminado, Lançamento do dia, Notas de serviço (consulta), Diário, Interferências | `campo`, `verificar` |
| EQUIPE (encarregado, preso à equipe) | Mapa iluminado, Lançamento do dia, Diário, Interferências | `campo` |
| RH | Mapa iluminado, Notas de serviço (consulta) | — |
| TOPOGRAFIA (consulta) | Mapa iluminado, Topografia | — |
| CADASTRO | Mapa iluminado, Cadastro de campo | `cadastro` |

Permissões: `usuarios`, `auditoria`, `equipes`, `almox`, `receber`, `compras_solicitar`, `compras_aprovar`,
`compras_pedir`, `inventario_contar`, `inventario_ajustar`, `campo`, `topografia`, `cadastro_campo`, `verificar`,
`retificar_campo`, `ok_interno`, `cadastro`, `conferir_cadastro`, `planejar`, `medicao`, `documentos`, `notas_servico`,
`lancar_sem_ns`, `ns_dia`, `apropriacao`. A matriz é provisória (D-10) e mora em `config/perfis.json`.

**Segregação de funções (sempre pela identidade da sessão; o nome digitado é ignorado):**
- quem informa não verifica (intervalos, soldas: nem o soldador nem quem informou);
- quem solicita a compra não aprova;
- quem importa ou digita a NF não confere nem aprova a nota sem pedido;
- quem conta o inventário não aprova o ajuste;
- a engenharia envia as NS (inclusive a do dia, em nome da equipe); o supervisor verifica.

**Quem vê as notas de serviço (D-134):** Administração, Engenharia, RH e Supervisor. Equipes e almoxarifado não veem
a aba, as listas, os PDFs nem os croquis (no Diário, o dia sem a nota). Topografia e Cadastro veem as do tipo deles.

Usuários: o sistema **nunca cria usuário sozinho** (o primeiro é criado pelo terminal: `python usuarios.py criar`).
Quem tem histórico é desativado, não excluído. Demonstração: `admin.demo`, `eng.demo`, `eng2.demo`, `almox.demo`,
`almox2.demo`, `equipe.demo`, `topo.demo`, `cadastro.demo` (senha pública; sempre desativados na nuvem).

---

## 9. Execução

### 9.1 Notas de serviço (D-69 em diante)

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

### 9.2 Lançamento do dia (o lançamento solto, sem NS)

Quatro páginas, cada perfil vê as dele (chips no topo, a página no endereço `#campo/fotos`, lembrada na sessão):
**Apropriação direta** (`apropriacao`), **Apontamento sem NS** (`lancar_sem_ns`, motivo obrigatório; nó e caixa
continuam aqui), **Fotos e soldas** (`campo`) e **Clima do dia** (`campo`; o encarregado só a equipe dele).

### 9.3 Intervalos, verificação, soldas, fotos e ocorrências

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

### 9.4 Cadastro: quatro fases e a esteira

Levantamento de campo (vala aberta, com referência) → preparação pela empresa → **conferência interna Ankara**
(roteiro de 6 itens: extensão, traçado, profundidade, material/DE, peças e nós, arquivos; NÃO CONFORME devolve à
empresa) → GDOC.

Esteira (`regras.ETAPAS`, ações na ficha do trecho, D-114): `1_PRONTO` → `2_ENVIADO` (empresa, data) → `3_RECEBIDO`
(arquivos) → `4_GDOC_ANALISE` (protocolo) → `6_APROVADO` (memorando ESET) ou `5A_NEGADO` (motivo) → `2_ENVIADO`
(nova revisão). Só o `6_APROVADO` é decisão da Caesb (verde) e gera a gaveta 3 da medição.

### 9.5 Apropriação direta (D-90 a D-97)

Lançamento direto no item do orçamento, sem NS (ex.: canteiro feito por equipe de outra obra da Ankara). Item
escolhido como no BM vertical (grupo → material/serviço → item) ou pela **busca única** (item, código Caesb,
descrição, DE, material, sinônimos TE/TÊ, PEAD, Ø/DE/DN, PVC, FOFO). Data não futura, quem executou (equipe, outra
obra, terceiro), o que foi feito, memória de cálculo, justificativa e **pelo menos uma evidência**. Correção só por
estorno com motivo. Item que não está no BM: cadastro de item novo (a aprovar). Entra na medição pela gaveta 5.

---

## 10. Planejamento e almoxarifado

**Dados da obra = o dia da equipe (D-104):** programar equipe + trechos (Ctrl+clique ou "Juntar trechos"; o nó entre
dois trechos entra sozinho) para um dia ou período (uma programação por alvo e dia, num lote cancelável) → o
almoxarife **libera o material do dia** (sugestão do projeto: tubo pelo que falta assentar, peças dos nós pela 06.2 →
BM vertical, limitada ao que há no almoxarifado), o que abre o check-in com todos os trechos (`checkin_alvos`) e acende
"em execução hoje" com o pino da equipe até a NS do dia chegar → **devolução** no fim do dia (aplicado, sobra, perda
com motivo, fica com a equipe). Dia futuro vira reserva. **Cronograma da obra** = XML do MS Project (ou .xlsx/.csv;
`.mpp` recusado), o macro de 18 meses, com tarefas ligadas a trechos citados no nome.

**Estoque:** disponível = físico − reservas; reserva por equipe e dia; uma sessão aberta por equipe, fechamentos em
ordem, sem check-in retroativo; o que fica com a equipe é declarado e volta no dia seguinte; correção só por estorno
(com motivo, nunca deixando reserva descoberta) ou retificação do fechamento (mesma quantidade e data); empréstimo só
com documento, responsável e autorização; transferência entre equipes com as duas sessões abertas; inventário com
recontagem se o saldo mudou; reservas vencidas liberadas em lote com motivo.

**Compras e notas:** solicitação (quem solicita não aprova; material da Caesb não se compra) → pedido (não mexe em
saldo) → NF por XML (biblioteca padrão; DOCTYPE recusado; modelo 55; chave com dígito; repetida recusada; emitente
cadastrado na hora pelo CNPJ do XML) ou digitada do PDF/imagem (anexo obrigatório; quem digitou não confere) →
**conferência** (cada linha para um material, com fator de conversão declarado para unidade diferente; frete e serviço
fora do estoque; material sugerido por código, de-para anterior ou descrição) → entrega em **quarentena** → inspeção
(aceito + recusado = entregue; recusa com motivo e laudo) → estoque. **Nota sem pedido:** o aceito espera a aprovação
de Engenharia/Administração, outra pessoa (D-110). **NF da Caesb:** a linha de tubo da Caesb vira `ROMANEIO_CAESB`, sem
quarentena (D-111). **Recebimento num toque (D-135):** "Recebido conforme a nota" confere, recebe e aceita numa
transação; "Registrar problema" pede o que chegou e o avariado por linha e o texto do problema (o que faltou continua
a receber; o avariado é recusado). **Material recebido nunca vira lançamento de medição.**

---

## 11. Mapas

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

**Dados da obra:** mapa próprio sobre o traçado do REV02 (sem plantas), tela cheia, o mapa não se move sozinho, zonas
sempre com cor, nomes completos.

**Mapa técnico REV02** (aberto à parte): camadas Andamento, Planejado (7 dias), Material, Informado × verificado,
Cadastro e Pendências, calculadas no servidor; modo Projeto restaura as cores de DE.

**Desempenho (D-98 a D-100):** durante o gesto o mapa se move por `transform` (desenho de verdade 150 ms depois ou ao
soltar); cópia leve em `<canvas>` por baixo para a borda; trecho tocado = o mais perto até 7 px; nós só na área
visível; tracejado por zona. Medição em `ferramentas/desempenho/`.

---

## 12. Medição: as regras Caesb × Ankara

### 12.1 Cálculo (contrato 5.2, células do BM)

1. Total do item: `ROUND(quantidade × preço sem BDI; 2)` (arredondamento do Excel, metade para cima:
   6.026,69 × 47,50 = 286.267,775 → 286.267,78; `regras.produto_excel`).
2. Σ por classe (MATERIAL / SERVIÇO) → SUB-TOTAL 01.
3. BDI por classe (15,28 % / 21,48 %) → SUB-TOTAL 02. **Sem arredondar no meio.**
4. TOTAL 01 + 02; COEF. K = total × K; **P0 = (Σ + BDI) × (1 + K)**.
5. Reajuste por classe = i × (Σ classe + BDI classe) × (1 + K); total geral = P0 + reajuste.
- Contrato (coluna P0): `ROUND(SUMPRODUCT(quant.; preço))` por classe. Medição: ROUND por item.
- No vertical, o ROUND é por chave; na juntada, por código Caesb (a soma das chaves do mesmo código): podem diferir em
  centavos — mostrar como aviso, **nunca esconder ajuste numa fórmula** (o modelo do Lago Sul tinha −0,27, −0,11, −0,58).
- `regras.totalizar_bm(itens, bdi_material, bdi_servico, coef_k, modo)`.

### 12.2 Lançamentos e gavetas

| Gaveta | O que entra | Quando |
|---|---|---|
| 1 | Serviços de trechos e nós (06.1 → item do BM por `config/servicos_rede.json`) | no OK interno |
| 2 | Materiais (regime pendente) | OK interno de nós; sempre PENDENTE (`MATERIAL_SEM_REGIME`) |
| 3 | Cadastro aprovado no GDOC (item `2.2_5.2.1`, pela extensão) | na etapa 6 da esteira (D-58, provisória) |
| 4 | Calçada/asfalto (`2.2_5.9.3`, `2.2_5.9.5`) | recomposição; item A CONFIRMAR → PENDENTE |
| 5 | Apropriação direta | item aprovado, de serviço, dentro do saldo do BM |

- **PROPOSTO** entra no valor; **PENDENTE** fica fora (com o motivo e a restrição). Serviços com item comprovado:
  assentamento (`2.2_` + código BM do trecho), escavações, esgotamento, locação com NS (`2.2_5.2.7`). Bloqueados:
  14 serviços sem item (D-50), solda (D-31, PENDENTE com as aprovadas), MND sem substituição (D-52), material (D-53,
  D-54). Escavação mecanizada em dois itens: rateio pela proporção contratual, hipótese (D-51).
- **Parcela única:** a mesma parcela (tipo|gaveta|serviço|alvo|item|unidade) não entra em duas medições (regra + índice
  único no banco); o mesmo alvo × serviço também é conferido sem o item.
- **Item a aprovar** (16 itens "XX" e itens novos): todo lançamento fica PENDENTE (`ITEM_A_APROVAR`) até o código
  oficial (`codigos_oficiais`) ou a aprovação; quando a restrição cai, **entra sozinho** (na medição aberta vira
  PROPOSTO; numa fechada, uma cópia entra na próxima aberta com `origem_id`).
- Painel **"Medível com restrição"**: valor parado por restrição (item a aprovar, acima do contrato, teto do subgrupo,
  material sem regime, cadastro esperando o GDOC, sem medição aberta), com a ação que libera e quem faz.
- **Teto por subgrupo** do vertical: hipótese (D-57); a simulação desconta o excedente.
- **Elegibilidade do período:** proposto nesta; OK interno esperando a medição; completo sem OK (com impedimentos);
  parcial não elegível (só trecho completo é proposto, D-30); medido antes.

### 12.3 Conferência, fechamento e congelamento

- **Conferência interna da engenharia** (D-59, provisória): roteiro de 5 itens (executado, evidências, pendentes,
  duplicidade, hipóteses); grava o **retrato** das evidências e a **assinatura** dos lançamentos. CONFORME é recusada com
  duplicidade ou foto obrigatória ausente/inválida. Se um lançamento muda depois, a conferência deixa de valer.
- **Fechar** exige a última conferência CONFORME e vigente e **justificativa em todo item acima de 100 % do contrato**
  (D-144). Grava quem fechou e qual conferência liberou.
- **Medição fechada é congelada:** preço, classificação, item, BDI, K e o resumo gravados; revisão posterior do BM só
  gera alerta. Não há estorno de proposta nem reabertura (D-16).
- **Só existe medição de TESTE** (`medicao_oficial_liberada = NAO`, D-56). Ela lista as hipóteses não validadas.

### 12.4 Material: regimes (SL0327) — bloqueado

Nada desta matriz está aplicado (`docs/MATRIZ_REGIMES_FATURAMENTO.md`): tubo da Caesb = só custódia (R$ 0 de
fornecimento); tubos da contratada 80 % (recebido + inspeção) / 20 % (implantado); eletromecânicos 20/15/40/15/10 %;
aço/ferro fundido 80/10/10 %; conexões PEAD sem regime documentado; regime normal depende da cláusula 2.16 do Edital.
**Sem 80/20 automático e sem 100 % na aplicação.** Recebido não é faturável.

### 12.5 Reajuste

Contrato 6.1–6.4: preços fixos por 1 ano a partir de 31/01/2025; depois, ICC-Brasília-DI **com pedido da
contratada**, só para obrigações iniciadas e concluídas após a anualidade; reajustes seguintes contam dos efeitos
financeiros do último. CEFR: até 3,29 %. A aba REAJUSTE do BM pede a **fração elegível** de material e de serviço por
medição (zero = nenhuma parcela). **Decisão do responsável (D-140): no pacote, reajuste R$ 0,00, "não pedido"**
(fração 0). A revisão que vale para a parcela elegível (REV03 × REV04) segue pendente (D-55).

### 12.6 Administração local (D-141, TR 14.6)

Igual à folha da ADM do modelo: `% ADM = ADM ÷ (subtotal 01 do contrato − ADM)`;
`faturamento do mês = Σ ROUND(quant. × preço; 2)` de material e serviço, sem BDI e sem a ADM;
`quantidade da ADM = faturamento × % ADM ÷ ADM` (fração de 1 UN); `valor = ROUND(quantidade × preço da ADM; 2)`.
Lançamento direto no item da ADM é ignorado. `pacote_medicao.adm_local`.

---

## 13. O pacote mensal no modelo oficial do BM

O que a Caesb recebe é o **BM REV04 preenchido, no próprio arquivo** (`pacote_medicao.gerar`), com as fórmulas do
modelo (D-138). Tela Medição › "Pacote da medição no modelo oficial" › **Baixar pacote (.xlsx)**
(`GET /api/medicao/pacote/baixar?id=`). O "Resumo interno (.xlsx)" é outra coisa: a conferência interna.

**Cadeia de fórmulas preservada:**
```
nª MC (folha por item; chave em C7) ─SUMIFS(W; C; chave)─► vertical (coluna QUANT. do mês)
vertical ─SUMIFS por código Caesb─► juntada ─► resumo (BDI, K, reajuste) 
vertical ─SUMIFS por Cód. Cron. FF─► CRONOGRAMA FF CAESB ─► GRÁFICOS (4)
folha da ADM ─► vertical (linha 546)
```

| Aba | O que o sistema preenche |
|---|---|
| BM MORRO DA CRUZ (juntada) | linhas dos itens sem medição no mês ocultas (grupos/subgrupos visíveis se têm item medido); colunas das outras medições ocultas; uma página de largura em A4 paisagem (D-154) |
| BM … VERTICAL | coluna do mês = `IFERROR(SUMIFS('nª MC'!$W:…,'nª MC'!$C:…,$D<linha>),0)`; **medições anteriores como valor congelado** (D-152); meses seguintes 0; ADM do mês = `'nª MC'!$W$<linha da ADM>`; data do boletim |
| nª MC (renomeada `02ª MC`, `03ª MC`…) | uma folha de 92 linhas por item medido, na ordem do vertical, cada uma numa página; folha da ADM no fim |
| REAJUSTE | E/F = 0 de todas as medições até a do pacote; situação "NÃO PEDIDO NESTA MEDIÇÃO (R$ 0,00)" |
| CRONOGRAMA FF, GRÁFICOS, CONFERÊNCIA CONTRATO | só o nº do contrato; o resto são as fórmulas |
| AVISOS DO TESTE (nova, só no teste) | total, ADM e avisos (pendentes fora, aditivo pendente, período, arredondamento, teto) |

**Folha da MC (template linhas 1–92; ADM nas linhas 1841–1932 do modelo):** cabeçalho (FOLHA nnn, título, contrato,
período e nº da medição puxados do vertical, logo Ankara); linha do item (linha 7: chave em C, descrição, código,
classificação, unidade e total por INDEX/MATCH); **galeria** (linhas 9–24, colunas B a W: até 6 fotos lado a lado, com o
carimbo gravado numa faixa no pé — data, trecho, GPS, contrato); **justificativa técnica** (X9:X24 mesclada);
**memorial** (linhas 27–92, 66 linhas: CÓD. CRON. FF, descrição, NOMENCLATURA DA OBRA, PROJETO, EST. INICIAL + FRAÇÃO,
EST. FINAL + FRAÇÃO, PONTO REFERÊNCIA, DISTANCIA = (K×20+L)−(I×20+J), QUANT., UNID., SUB-TOTAL). Regras do sistema
(D-153): trecho inteiro em metro sai da estaca 0+0,00 até a estaca do fim, quantidade 1 (sem encadear estacas);
outras unidades, a quantidade direta (SUB-TOTAL = QUANT.) e o trecho, os nós e a extensão no ponto de referência;
mais de 66 linhas viram folha de continuação com a mesma chave. A folha da ADM lista a equipe administrativa ativa do
cadastro de usuários (D-156).

**Fotos e justificativa** (`medicao_folhas`, `POST /api/medicao/folha`, permissão `medicao`, medição aberta): o sistema
sugere as **6 fotos mais recentes** dos trechos e nós do item; a engenharia troca (até 6, na ordem do toque) ou volta à
sugestão; justificativa por frase pronta (`pacote_medicao.FRASES`) ou texto livre (até 600). Item acima de 100 % do
contrato: "ADITIVO PENDENTE" na folha e fechamento só com justificativa (D-142 a D-144).

**Marca TESTE – NÃO OFICIAL** (D-139): no título de cada aba, no cabeçalho de impressão de todas as páginas e no nome
do arquivo (`BM_MORRO_DA_CRUZ_01a_MEDICAO_TESTE_NAO_OFICIAL.xlsx`). Período no cabeçalho = o do modelo (da OS
01/10/2026, prazo 540 dias, na aba REAJUSTE); se o do sistema for outro, aviso (D-155). O pacote recusa um BM em
`planilhas/` diferente do importado (SHA-256, D-157).

**Por que editar o .xlsx por dentro (`xlsx_modelo.py`):** abrir e salvar pelo openpyxl perde ou altera desenhos,
logos, comentários e gráficos. O editor trata o arquivo como pacote: expande as fórmulas compartilhadas das abas
editadas (Translator), desloca as referências locais ao copiar blocos, remove os valores guardados das fórmulas e a
`calcChain`, liga `fullCalcOnLoad` e reconstrói os desenhos (logo por folha + fotos com âncora numa célula). Conferido:
ida e volta do modelo sem mudar nenhuma das 56 mil células recalculadas; o pacote recalculado no LibreOffice bate com
o sistema (P0 da juntada e do vertical, ADM, total geral, cronograma FF). No PDF do LibreOffice, logos e fotos descem
um pouco a cada folha (o modelo original também); **gere o PDF pelo Excel**.

**Conferências cruzadas (o mesmo número em vários lugares):** P0 do mês (BM, cronograma FF, relatório, gráfico R$/1000);
acumulado e saldo P0; reajuste; locado acumulado (= item de locação com NS); rede executada no mês e acumulada
(relatório, item de assentamento, mapa); aplicado de tubo Caesb; efetivo e equipamentos.

### 13.1 Relatório mensal (fase 2, ainda não feito)

Word (cabeçalho com o logo da Ankara: contrato, nº do relatório, período — D-151), capa com o **mapa das zonas** como
no relatório de conexões das 11 zonas (não a ponte do Lago Sul, D-148). Estrutura de referência (Lago Sul): capa,
sumário, apresentação, identificação, empreendimento, dados contratuais, quadro resumo gerencial, dados gerenciais
(faturado, reajuste, saldo, prazos), desenvolvimento e canteiro, organogramas, atividades por semana (croqui com
executado/anterior/não executado e estacas), equipes e materiais (compatibilização de tubos Caesb), execução (locação
com NS; rede executada), próximo mês, cronograma FF e os 4 gráficos, histograma (efetivo por dia), observações,
relatório fotográfico (6 fotos por página), anexos (mapa iluminado e caminhamento da medição). Decisões já dadas:
dados fixos numa tela "Dados do contrato" preenchida uma vez (D-145); textos do mês completados no Word, nos lugares
marcados (D-146); presença diária marcada no sistema por RH ou supervisor (D-147); imagens fixas enviadas uma vez
(D-148); IDA/SAOB fora (D-149); cronograma do Project depois (D-150). Dados pessoais só onde a Caesb exige, vindos do
cadastro; histograma por iniciais ou matrícula. Falta o documento da juntada (o Drive não abriu).

---

## 14. Decisões: o que manda e o que está aberto

**Decididas que moldam o sistema:** D-20 ordem obrigatória · D-60/62 nuvem · D-63/65 Drive · D-64 telas por perfil ·
D-66 terceirizadas registradas pela engenharia · D-67/75 menu · D-68 trecho físico · D-69/71/74 NS por upload,
exceção com motivo, croqui guardado · D-90/91/95 apropriação, base de custo, restrição que cai sozinha · D-101 a D-108
fluxo integrado · D-121 a D-124 execução reorganizada · D-131 a D-134 clima, NS só pela engenharia, RH · D-135
recebimento num toque · D-136 cores claras · D-137 a D-151 medição e relatório no modelo da Ankara.

**Abertas ou bloqueadas (o sistema trava e explica):** D-01 aprovação dos controles (importação real) · D-10/D-11
matriz de perfis e usuários reais · D-16 retificação/estorno depois do OK · D-30 medir por intervalo · D-31 soldas ·
D-50 14 serviços sem item · D-51 rateio da escavação · D-52 MND · D-53/D-54 regimes de material · D-55 parcela
elegível do reajuste · **D-56 medição oficial** · D-57 teto por subgrupo · D-58 critério do cadastro · D-59 conferência
da medição · D-61 sem internet (não iniciado) · D-70 numeração da NS · D-85 nós na NS do dia · D-92 quantidade do item
novo · e as provisórias de campo e almoxarifado (D-12 a D-18, D-21, D-22, D-40 a D-44) e da medição (D-152 a D-157).

---

## 15. Como trabalhar neste repositório

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

**Testes:** `python -m unittest discover -s tests` (448 testes em 26/10/2026, ~7 min; 2 pulados). Os de base real
exigem as planilhas em `planilhas/`. Navegador: Playwright com o Chromium do ambiente
(`/opt/pw-browsers/chromium-1194/chrome-linux/chrome`, módulo `/opt/node-tools/node_modules/playwright`): logar, abrir
`abrirAba('<tela>')`, conferir rolagem (`scrollWidth − innerWidth`), erros de página e respostas ≥ 500, em 390 e 1280 px.
LibreOffice (`soffice --headless --convert-to xlsx|pdf`) para recalcular e ver o pacote da medição.

**Documentação a atualizar junto com o código:** `docs/DECISOES_PENDENTES.md` (nova seção com as decisões, no formato
ID | Decisão | Opções | Impacto | Recomendação | Situação), o `docs/MODULO_*.md` do módulo, e o README quando muda a
operação.

**Armadilhas já vistas:** `sqlite3.Row` não compara com tupla (converta); `_palavras` devolve minúsculas; o PythonAnywhere
está em UTC (use `relogio`); openpyxl perde desenhos ao salvar (use `xlsx_modelo`); o LibreOffice só recalcula tudo
sem os valores guardados das fórmulas; fotos de teste precisam ser imagens decodificáveis (`tests/fotos_teste.py`);
`registrar_foto` recebe base64; o OK interno exige verificação, fotos e clima registrado nos testes.

---

## 16. Próximos passos conhecidos

1. Relatório mensal em Word (fase 2), com a tela "Dados do contrato", a presença diária e as imagens fixas.
2. Documento da juntada (ordem das peças, folha de rosto, ofício) — pedir de novo ao responsável.
3. Decisões que liberam a medição oficial (D-30, D-31, D-50 a D-57) e a importação real (D-01).
4. Cronograma do Project ligado ao executado (% por trecho) e a reprogramação do cronograma FF.
5. Primeiras NS reais (formato da NS do dia, nós na NS do dia) para ajustar tolerâncias e leitura.
