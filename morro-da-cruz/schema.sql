-- Sistema de Gestão e Mapa Iluminado — Morro da Cruz (CT Caesb × Ankara 10239/2026, LC 014/2026)
-- Esquema v7. Banco SQLite local.
--   * Identidades estáveis próprias (TR-/EL-/AT-/IP-) separadas dos nomes visíveis, que são versionados.
--   * Toda linha importada guarda proveniência (arquivo + hash + aba + linha + células).
--   * Importação nunca apaga: o que sai de uma revisão fica com vigente = 0.
--   * alvo_tipo ∈ ('TRECHO','ATIVIDADE').
--   * v3: pendência bloqueante, escopo explícito das decisões, medição fechada congelada,
--     identidade dos itens pela assinatura técnica completa (não pela ordem das linhas).
--   * v4 (etapa 3, estoque): reservas, saldo que fica com a equipe, empréstimo autorizado, estorno sem apagar,
--     baixa teórica fora do saldo físico.
--   * v5: custódia por sessão (fechamentos em ordem), reserva nunca descoberta, retificação de fechamento.
--   * v6 (etapa 4, campo): intervalos por etapa no trecho, soldas informadas × verificadas, foto original com hash.
--   * v7 (auditoria f035f5c): avanço legado sem posição + conciliação explícita, cronologia dos pré-requisitos,
--     validação da imagem antes de aceitar a foto como evidência.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_versao (
  versao INTEGER PRIMARY KEY,
  aplicada_em TEXT NOT NULL,
  descricao TEXT
);

-- ---------------------------------------------------------------- importação e proveniência
CREATE TABLE IF NOT EXISTS importacoes (
  id INTEGER PRIMARY KEY,
  iniciada_em TEXT NOT NULL,
  concluida_em TEXT,
  modo TEXT NOT NULL CHECK (modo IN ('SIMULACAO','APLICACAO')),
  status TEXT NOT NULL,                -- EM_ANDAMENTO / CONCLUIDA / SEM_ALTERACOES (reprovação = rollback + relatório em arquivo)
  backup TEXT,                         -- pasta do backup verificado feito antes
  relatorio TEXT                       -- JSON
);

CREATE TABLE IF NOT EXISTS fontes_arquivo (
  id INTEGER PRIMARY KEY,
  chave TEXT NOT NULL,                 -- redes / conexoes / evidencias / bm / reajuste
  nome TEXT NOT NULL,
  revisao TEXT,
  sha256 TEXT NOT NULL,
  bytes INTEGER NOT NULL,
  primeira_importacao_id INTEGER REFERENCES importacoes(id),
  UNIQUE (chave, sha256)
);

-- Onde cada registro foi lido (uma linha por registro × fonte)
CREATE TABLE IF NOT EXISTS proveniencia (
  entidade TEXT NOT NULL,              -- trecho / elemento / atividade / item_projeto / bm_item / aviso
  entidade_id TEXT NOT NULL,
  fonte_id INTEGER NOT NULL REFERENCES fontes_arquivo(id),
  aba TEXT NOT NULL,
  linha INTEGER,
  celulas TEXT,                        -- JSON {coluna: valor bruto}
  PRIMARY KEY (entidade, entidade_id, fonte_id)
);

-- Histórico de nomes visíveis (PONTO, nomenclatura) por identidade estável
CREATE TABLE IF NOT EXISTS nomes_historico (
  entidade TEXT NOT NULL,
  entidade_id TEXT NOT NULL,
  nome TEXT NOT NULL,
  fonte_id INTEGER REFERENCES fontes_arquivo(id),
  registrado_em TEXT NOT NULL,
  PRIMARY KEY (entidade, entidade_id, nome)
);

-- Diferenças aplicadas por importação (nova revisão)
CREATE TABLE IF NOT EXISTS alteracoes (
  id INTEGER PRIMARY KEY,
  importacao_id INTEGER NOT NULL REFERENCES importacoes(id),
  entidade TEXT NOT NULL,
  entidade_id TEXT NOT NULL,
  campo TEXT NOT NULL,
  antes TEXT,
  depois TEXT
);

-- Ambiguidades e pendências levantadas na importação (nada é casado em silêncio)
CREATE TABLE IF NOT EXISTS pendencias_importacao (
  id INTEGER PRIMARY KEY,
  importacao_id INTEGER NOT NULL REFERENCES importacoes(id),
  tipo TEXT NOT NULL,
  referencia TEXT,
  detalhe TEXT NOT NULL,
  bloqueante INTEGER NOT NULL DEFAULT 0  -- 1 = impede o COMMIT (só aparece no relatório de reprovação)
);

-- Mapa de migração de referências antigas (v1) para identidades estáveis (v2)
CREATE TABLE IF NOT EXISTS migracao_mapa (
  tabela TEXT NOT NULL,
  coluna TEXT NOT NULL,
  antigo TEXT NOT NULL,
  novo TEXT,                           -- NULL = não mapeado (valor antigo preservado)
  migrado_em TEXT NOT NULL,
  PRIMARY KEY (tabela, coluna, antigo)
);

-- ---------------------------------------------------------------- parâmetros
CREATE TABLE IF NOT EXISTS parametros (
  chave TEXT PRIMARY KEY,
  valor TEXT NOT NULL,
  fonte TEXT
);

CREATE TABLE IF NOT EXISTS reajuste_indices (
  vigencia_ini TEXT NOT NULL,
  vigencia_fim TEXT NOT NULL,
  indice REAL NOT NULL,
  descricao TEXT,
  PRIMARY KEY (vigencia_ini)
);

-- ---------------------------------------------------------------- equipes
CREATE TABLE IF NOT EXISTS equipes (
  id TEXT PRIMARY KEY,                 -- Zona01..Zona11, ADUTORA, CH (frentes)
  nome TEXT NOT NULL,
  cor TEXT
);

CREATE TABLE IF NOT EXISTS funcionarios (
  id INTEGER PRIMARY KEY,
  nome TEXT NOT NULL,
  funcao TEXT,
  equipe_id TEXT REFERENCES equipes(id)
);

CREATE TABLE IF NOT EXISTS maquinas (
  id INTEGER PRIMARY KEY,
  descricao TEXT NOT NULL,
  equipe_id TEXT REFERENCES equipes(id)
);

-- ---------------------------------------------------------------- projeto: redes (06.1)
CREATE TABLE IF NOT EXISTS trechos (
  id TEXT PRIMARY KEY,                 -- TR-00001 (estável)
  ponto TEXT NOT NULL,                 -- nome visível vigente (col. R): Zona01_PB01_Rede_TR001
  vigente INTEGER NOT NULL DEFAULT 1,
  item INTEGER,
  frente_id TEXT REFERENCES equipes(id),
  equipe TEXT,
  tipo TEXT,
  pb TEXT,
  prancha TEXT,
  area TEXT,
  de_mm REAL,
  material TEXT,
  solda TEXT,
  metodologia TEXT,                    -- VCA / MND
  classe TEXT,
  extensao_m REAL NOT NULL,
  codigo_bm TEXT,                      -- col. AC (como está na fonte; MND não é substituído)
  recobrimento_m REAL, profundidade_m REAL, largura_m REAL, lastro_m REAL,
  perfil_status TEXT,
  quantidades TEXT NOT NULL,           -- JSON {coluna: valor da 06.1}
  no_ini TEXT, no_fim TEXT,
  handle TEXT,
  utm_ini TEXT, utm_fim TEXT,
  lat REAL, lon REAL,
  aviso_problema TEXT,
  aviso_sugestao TEXT,
  observacao TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_trechos_ponto ON trechos(ponto) WHERE vigente = 1;

-- ---------------------------------------------------------------- projeto: conexões (06.2)
-- Elemento físico: 1.191 (1.059 nós + 132 dispositivos). Chave natural = handle CAD (col. AR);
-- sem handle (MV-11, VTF-12, VTF-16) = número do projeto. Nunca recebe coordenada inventada.
CREATE TABLE IF NOT EXISTS elementos (
  id TEXT PRIMARY KEY,                 -- EL-0001 (estável)
  chave_natural TEXT NOT NULL UNIQUE,  -- H:<handle> ou N:<número>
  numero TEXT NOT NULL,                -- NÓ1.8, DF-33 ...
  tipo TEXT NOT NULL,                  -- NÓ, DF, VM, VRP, MV, VTF, HID
  vigente INTEGER NOT NULL DEFAULT 1,
  handle TEXT,
  pb TEXT,
  zona TEXT,
  utm_e REAL, utm_n REAL,
  lat REAL, lon REAL,
  status_posicao TEXT,                 -- conferência EVIDÊNCIAS (zona), não aprovação técnica
  id_auditoria TEXT                    -- SUBDMC1_NÓ1.8 (referência histórica)
);

-- Atividade = elemento × frente (1.242). A DF-33 tem duas atividades (Rede e CH) e um só elemento.
CREATE TABLE IF NOT EXISTS atividades (
  id TEXT PRIMARY KEY,                 -- AT-0001 (estável)
  elemento_id TEXT NOT NULL REFERENCES elementos(id),
  tipo_frente TEXT NOT NULL,           -- Rede / CH / Adutora (da nomenclatura)
  nomenclatura TEXT NOT NULL,          -- nome visível vigente (col. K)
  frente_id TEXT REFERENCES equipes(id),  -- LOCAL (col. M)
  equipe TEXT,                         -- col. AE
  vigente INTEGER NOT NULL DEFAULT 1,
  UNIQUE (elemento_id, tipo_frente)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_atividades_nom ON atividades(nomenclatura) WHERE vigente = 1;

-- Item de projeto = linha de item de medição da 06.2 (6.539). Não é peça física unitária.
-- quantidade/unidade NULL = sem fonte (pendente) — nunca tratados como zero.
CREATE TABLE IF NOT EXISTS itens_projeto (
  id TEXT PRIMARY KEY,                 -- IP-000001 (estável)
  atividade_id TEXT NOT NULL REFERENCES atividades(id),
  chave_ocorrencia TEXT NOT NULL,      -- assinatura técnica (descr|DE|PN|resina|tipo|solda|material) + '#' nº de criação
                                       -- (o nº é sequencial de criação, nunca a posição da linha)
  vigente INTEGER NOT NULL DEFAULT 1,
  descricao TEXT NOT NULL,
  pressao TEXT, resina TEXT, tipo_conexao TEXT, solda TEXT, diametro TEXT, material TEXT, grupo TEXT,
  quantidade REAL,
  unidade TEXT,
  unidade_fonte TEXT,                  -- ex.: 'BM Juntada 1.14.27' ou motivo da pendência
  codigo_bm TEXT,                      -- col. R (item da Juntada) como na fonte
  enquadramento_bm TEXT,               -- col. BA
  obs_enquadramento_bm TEXT,           -- col. BB
  trechos TEXT,                        -- col. BC (vínculo direto ou por proximidade)
  tipo_entroncamento TEXT,             -- col. AG
  status_conexao TEXT,                 -- col. AH
  UNIQUE (atividade_id, chave_ocorrencia)
);

-- Avisos de origem (AA/AB/AW) — texto da fonte, imutável. Decisões ficam em `decisoes`.
CREATE TABLE IF NOT EXISTS avisos_origem (
  id INTEGER PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES itens_projeto(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('PROBLEMA','SUGESTAO')),
  prioridade TEXT,                     -- col. AW (P1/P2)
  texto TEXT NOT NULL,
  texto_hash TEXT NOT NULL,
  vigente INTEGER NOT NULL DEFAULT 1,
  UNIQUE (item_id, tipo, texto_hash)
);

-- Decisões posteriores aos avisos (nunca alteradas pela importação)
CREATE TABLE IF NOT EXISTS decisoes (
  id TEXT PRIMARY KEY,                 -- DEC-0001
  assunto TEXT NOT NULL,
  objeto_tipo TEXT,                    -- ELEMENTO / ATIVIDADE / GERAL
  objeto_ref TEXT,                     -- número ou nomenclatura citada na fonte da decisão
  status TEXT NOT NULL,                -- ENCERRADA / EM_ANALISE / FORA_DO_ESCOPO_ATE_RESPOSTA
  decisao TEXT NOT NULL,
  responsavel TEXT,
  evidencia TEXT NOT NULL,
  data TEXT,
  padrao_aviso TEXT,                   -- só SUGERE avisos relacionados para revisão; nunca vincula
  registrada_em TEXT NOT NULL
);

-- Escopo explícito: objetos (nº do elemento de projeto) sobre os quais a decisão foi tomada
CREATE TABLE IF NOT EXISTS decisao_objetos (
  decisao_id TEXT NOT NULL REFERENCES decisoes(id),
  objeto_tipo TEXT NOT NULL CHECK (objeto_tipo IN ('ELEMENTO')),
  objeto_ref TEXT NOT NULL,            -- nº de projeto: DF-05, MV-11 ...
  PRIMARY KEY (decisao_id, objeto_tipo, objeto_ref)
);

-- Vínculo explícito decisão × aviso de origem (elemento + hash do texto). Só estes ficam como "decididos".
CREATE TABLE IF NOT EXISTS decisao_vinculos (
  decisao_id TEXT NOT NULL REFERENCES decisoes(id),
  elemento_numero TEXT NOT NULL,
  texto_hash TEXT NOT NULL,
  registrado_em TEXT NOT NULL,
  PRIMARY KEY (decisao_id, elemento_numero, texto_hash)
);

-- ---------------------------------------------------------------- BM
CREATE TABLE IF NOT EXISTS bm_itens (
  id INTEGER PRIMARY KEY,              -- estável: upsert por (planilha, item)
  planilha TEXT NOT NULL CHECK (planilha IN ('JUNTADA','VERTICAL')),
  item TEXT NOT NULL,                  -- Vertical: 2.2_5.2.1 · Juntada: 5.2.1
  item_bm TEXT,
  subgrupo TEXT,
  subgrupo_nome TEXT,
  codigo_caesb TEXT,
  classificacao TEXT,                  -- MATERIAL / SERVIÇO (define o BDI)
  descricao TEXT NOT NULL,
  unidade TEXT,
  quantidade REAL,
  preco_unitario REAL,                 -- sem BDI (contrato 5.2)
  valor_total REAL,
  atributos TEXT,
  linha_origem INTEGER,
  vigente INTEGER NOT NULL DEFAULT 1,
  UNIQUE (planilha, item)
);

-- ---------------------------------------------------------------- almoxarifado
CREATE TABLE IF NOT EXISTS materiais (
  id TEXT PRIMARY KEY,
  descricao TEXT NOT NULL,
  unidade TEXT NOT NULL,
  propriedade TEXT NOT NULL CHECK (propriedade IN ('CAESB','ANKARA','CONSUMO')),
  preco_unitario REAL NOT NULL DEFAULT 0,
  bm_item_id INTEGER REFERENCES bm_itens(id),
  qtd_projeto REAL,
  estoque_caesb REAL
);

-- Nota fiscal. Fluxo v11: A_CONFERIR (XML importado ou dados digitados do PDF/imagem) → CONFERIDA (de-para dos itens
-- conferido; só então aceita entregas) → ENCERRADA. QUARENTENA/ACEITO = registro direto anterior à v11 (NF inteira).
-- NF nunca vira lançamento de medição: estoque ≠ faturável (matriz de regimes pendente).
CREATE TABLE IF NOT EXISTS notas_fiscais (
  id INTEGER PRIMARY KEY,
  numero TEXT NOT NULL,
  chave_nfe TEXT,
  fornecedor TEXT,
  data_entrega TEXT,
  arquivo TEXT,
  faturamento_etapas INTEGER NOT NULL DEFAULT 0,   -- só registro da intenção; regime não aplicado (matriz pendente)
  laudo_arquivo TEXT,
  status TEXT NOT NULL DEFAULT 'QUARENTENA'
    CHECK (status IN ('A_CONFERIR','CONFERIDA','QUARENTENA','ACEITO','ENCERRADA','CANCELADA')),
  serie TEXT,
  fornecedor_id INTEGER REFERENCES fornecedores(id),
  pedido_id INTEGER REFERENCES pedidos_compra(id),
  data_emissao TEXT,
  valor_total REAL,
  origem TEXT,                         -- XML · DIGITADA (de PDF/imagem) · DIRETA (anterior à v11)
  documento_id INTEGER REFERENCES documentos(id),
  registrada_por TEXT, registrada_em TEXT,
  conferida_por TEXT, conferida_em TEXT,
  cancelada_motivo TEXT
);

CREATE TABLE IF NOT EXISTS nf_itens (
  id INTEGER PRIMARY KEY,
  nf_id INTEGER NOT NULL REFERENCES notas_fiscais(id),
  material_id TEXT NOT NULL REFERENCES materiais(id),
  quantidade REAL NOT NULL,            -- na unidade do material (já convertida na conferência)
  valor_unitario REAL NOT NULL,
  pedido_item_id INTEGER REFERENCES pedido_itens(id),
  linha_id INTEGER REFERENCES nf_linhas(id)
);
-- Linhas da NF como vieram (XML) ou como foram digitadas (PDF/imagem): nunca geram movimento. A conferência liga cada
-- linha a um material (com o fator de conversão de unidade declarado) ou a marca como fora do estoque.
CREATE TABLE IF NOT EXISTS nf_linhas (
  id INTEGER PRIMARY KEY,
  nf_id INTEGER NOT NULL REFERENCES notas_fiscais(id),
  n_item INTEGER NOT NULL,
  codigo TEXT, descricao TEXT NOT NULL, ncm TEXT, cfop TEXT,
  unidade TEXT NOT NULL,
  quantidade REAL NOT NULL CHECK (quantidade > 0),
  valor_unitario REAL NOT NULL,
  valor_total REAL NOT NULL,
  material_id TEXT REFERENCES materiais(id),
  fator REAL,                          -- quantidade no material = quantidade da NF × fator
  pedido_item_id INTEGER REFERENCES pedido_itens(id),
  fora_do_estoque INTEGER NOT NULL DEFAULT 0,   -- frete, serviço etc. (conferido)
  UNIQUE (nf_id, n_item)
);

CREATE TABLE IF NOT EXISTS movimentos (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL,
  material_id TEXT NOT NULL REFERENCES materiais(id),
  tipo TEXT NOT NULL CHECK (tipo IN (
    'ROMANEIO_CAESB','EMPRESTIMO_OUTRA_OBRA','ENTRADA_NF','ENTRADA_CONSUMO',
    'CUSTODIA','APLICADO','SOBRA','PERDA','BAIXA_TEORICA',
    'DEVOLUCAO_FORNECEDOR','AJUSTE_INVENTARIO_ENTRADA','AJUSTE_INVENTARIO_SAIDA','TRANSF_SAIDA','TRANSF_ENTRADA')),
  quantidade REAL NOT NULL CHECK (quantidade >= 0),
  equipe_id TEXT REFERENCES equipes(id),
  alvo_tipo TEXT, alvo_id TEXT,
  documento TEXT,
  status TEXT,
  motivo TEXT,
  checkin_id INTEGER REFERENCES checkins(id),
  nf_id INTEGER REFERENCES notas_fiscais(id),
  responsavel TEXT,                    -- quem registrou/autorizou (obrigatório no empréstimo)
  autorizacao TEXT,                    -- documento/pessoa que autorizou (empréstimo para outra obra)
  retificacao_id INTEGER REFERENCES retificacoes(id),  -- lançamento criado por retificação de fechamento
  ref_tipo TEXT, ref_id INTEGER        -- v11: origem (INSPECAO, DEVOLUCAO, TRANSFERENCIA, INVENTARIO, RECEBIMENTO)
);
-- ENTRADA_NF: QUARENTENA (entregue, aguardando inspeção) → INSPECIONADO (fica como registro; o aceito entra como novo
-- ENTRADA_NF ACEITO ligado à inspeção; o recusado não entra). ACEITO direto = registro anterior à v11.

-- Retificação de um check-out encerrado: estorna o aplicado/sobra/perda original e redistribui a mesma
-- quantidade na mesma sessão. O check-in não é reaberto.
CREATE TABLE IF NOT EXISTS retificacoes (
  id INTEGER PRIMARY KEY,
  checkin_id INTEGER NOT NULL REFERENCES checkins(id),
  movimento_id INTEGER NOT NULL REFERENCES movimentos(id),
  destino TEXT NOT NULL,               -- JSON {aplicado, sobra, perda, fica_com_equipe, motivo_perda}
  motivo TEXT NOT NULL,
  responsavel TEXT NOT NULL,
  em TEXT NOT NULL
);

-- Ajuste de reserva que ficaria sem cobertura (por estorno/retificação confirmados com ajuste)
CREATE TABLE IF NOT EXISTS reserva_ajustes (
  id INTEGER PRIMARY KEY,
  reserva_id INTEGER NOT NULL REFERENCES reservas(id),
  de REAL NOT NULL,
  para REAL NOT NULL,
  motivo TEXT NOT NULL,
  responsavel TEXT NOT NULL,
  movimento_id INTEGER REFERENCES movimentos(id),
  em TEXT NOT NULL
);
-- BAIXA_TEORICA (MVP antigo) fica só como registro: não altera o saldo físico. Movimento nunca é apagado:
-- correção = estorno (tabela estornos), que tira o movimento dos saldos e guarda motivo e responsável.

-- Estorno de movimento (o movimento original permanece; saldos ignoram movimentos estornados)
CREATE TABLE IF NOT EXISTS estornos (
  movimento_id INTEGER PRIMARY KEY REFERENCES movimentos(id),
  motivo TEXT NOT NULL,
  responsavel TEXT NOT NULL,
  em TEXT NOT NULL
);

-- Reserva do almoxarifado para uma equipe/dia (programação). Disponível = saldo físico − reservas ativas.
CREATE TABLE IF NOT EXISTS reservas (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL,
  equipe_id TEXT NOT NULL REFERENCES equipes(id),
  material_id TEXT NOT NULL REFERENCES materiais(id),
  quantidade REAL NOT NULL CHECK (quantidade > 0),
  alvo_tipo TEXT, alvo_id TEXT,
  responsavel TEXT,
  status TEXT NOT NULL DEFAULT 'ATIVA' CHECK (status IN ('ATIVA','ATENDIDA','CANCELADA')),
  checkin_id INTEGER REFERENCES checkins(id),
  criada_em TEXT NOT NULL,
  encerrada_em TEXT,
  motivo TEXT
);

-- ---------------------------------------------------------------- campo
CREATE TABLE IF NOT EXISTS checkins (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL,
  equipe_id TEXT NOT NULL REFERENCES equipes(id),
  alvo_tipo TEXT, alvo_id TEXT,
  contingencia TEXT,
  encerrado INTEGER NOT NULL DEFAULT 0
);

-- Saldo que fica com a equipe no check-out (contado com o encarregado); volta como custódia no dia seguinte
CREATE TABLE IF NOT EXISTS custodia_declarada (
  checkin_id INTEGER NOT NULL REFERENCES checkins(id),
  material_id TEXT NOT NULL REFERENCES materiais(id),
  quantidade REAL NOT NULL CHECK (quantidade >= 0),
  em TEXT NOT NULL,
  PRIMARY KEY (checkin_id, material_id)
);

CREATE TABLE IF NOT EXISTS checkin_presencas (
  checkin_id INTEGER NOT NULL REFERENCES checkins(id),
  recurso_tipo TEXT NOT NULL CHECK (recurso_tipo IN ('FUNCIONARIO','MAQUINA')),
  recurso_id INTEGER NOT NULL,
  PRIMARY KEY (checkin_id, recurso_tipo, recurso_id)
);

CREATE TABLE IF NOT EXISTS clima (
  data TEXT NOT NULL,
  equipe_id TEXT NOT NULL REFERENCES equipes(id),
  turno TEXT NOT NULL CHECK (turno IN ('MANHA','TARDE')),
  condicao TEXT NOT NULL CHECK (condicao IN ('SOL','CHUVA_FRACA_TENDA','PARALISADO_CHUVA','VALA_ALAGADA_BOMBA')),
  PRIMARY KEY (data, equipe_id, turno)
);

CREATE TABLE IF NOT EXISTS apontamentos (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL,
  equipe_id TEXT NOT NULL REFERENCES equipes(id),
  alvo_tipo TEXT NOT NULL, alvo_id TEXT NOT NULL,
  metros_executados REAL NOT NULL DEFAULT 0,
  metros_reaterrados REAL NOT NULL DEFAULT 0,
  estaca_ini TEXT, estaca_fim TEXT,
  informado_por TEXT,
  anulado_por INTEGER REFERENCES retificacoes_intervalos(id),   -- v8: retificado: fica no histórico, fora das somas
  retificacao_id INTEGER REFERENCES retificacoes_intervalos(id) -- v8: apontamento criado por uma retificação
);

-- Intervalo executado de um trecho, por etapa (metros a partir do início do trecho, sentido da 06.1).
-- Não pode sobrepor outro da mesma etapa; reaterro e cadastro de campo só sobre o que foi assentado.
-- origem: INFORMADO (ini/fim do campo) · COMPLETO (100 % concluído: preenche as lacunas)
--         · SEQUENCIAL (v6: apontamento só em metros, posição presumida — não é mais aceito; confirmar por retificação)
--         · LEGADO (metros de apontamento anterior aos intervalos, posição confirmada por conciliação; sem quantidades novas)
--         · RETIFICACAO (substitui intervalos anulados por retificação)
-- v8: intervalo nunca é apagado. Retificação ANULA (anulado_por) e grava os substitutos (retificacao_id); só os
--     efetivos (anulado_por IS NULL) contam. referencia = registro do levantamento de campo (caderneta, croqui, arquivo).
CREATE TABLE IF NOT EXISTS intervalos_execucao (
  id INTEGER PRIMARY KEY,
  trecho_id TEXT NOT NULL REFERENCES trechos(id),
  etapa TEXT NOT NULL CHECK (etapa IN ('ASSENTADO','CADASTRO_CAMPO','REATERRADO')),
  ini_m REAL NOT NULL CHECK (ini_m >= 0),
  fim_m REAL NOT NULL,
  data TEXT NOT NULL,
  equipe_id TEXT REFERENCES equipes(id),
  apontamento_id INTEGER REFERENCES apontamentos(id),
  origem TEXT NOT NULL CHECK (origem IN ('INFORMADO','COMPLETO','SEQUENCIAL','LEGADO','RETIFICACAO')),
  conciliacao_id INTEGER REFERENCES conciliacoes_legado(id),
  informado_por TEXT,
  sem_cadastro_campo INTEGER NOT NULL DEFAULT 0,   -- reaterro sobre trecho ainda sem cadastro de campo (alerta)
  verificado_em TEXT, verificado_por TEXT,
  registrado_em TEXT NOT NULL,
  referencia TEXT,
  anulado_por INTEGER REFERENCES retificacoes_intervalos(id),
  retificacao_id INTEGER REFERENCES retificacoes_intervalos(id),
  CHECK (fim_m > ini_m)
);

-- Retificação de intervalos (v8): corrige a posição/extensão/data dos intervalos de UM apontamento ou de UMA
-- conciliação do legado. Aplicação integral ou recusa: o conjunto resultante do trecho precisa continuar coerente
-- (sem sobreposição; reaterro e cadastro de campo com assentamento até a data). Os originais ficam anulados, não
-- apagados; o apontamento original fica substituído (fora das somas) e o novo traz as quantidades corrigidas.
CREATE TABLE IF NOT EXISTS retificacoes_intervalos (
  id INTEGER PRIMARY KEY,
  trecho_id TEXT NOT NULL REFERENCES trechos(id),
  ref_tipo TEXT NOT NULL CHECK (ref_tipo IN ('APONTAMENTO','CONCILIACAO')),
  ref_id INTEGER NOT NULL,             -- apontamento ou conciliação retificados
  novo_apontamento_id INTEGER REFERENCES apontamentos(id),
  motivo TEXT NOT NULL,
  responsavel TEXT NOT NULL,
  detalhe TEXT NOT NULL,               -- JSON: intervalos e quantidades antes/depois
  em TEXT NOT NULL
);

-- Conciliação do avanço legado (apontamentos em metros, sem posição, anteriores aos intervalos): a pessoa
-- responsável informa onde esses metros estão; a soma por etapa precisa ser igual ao legado. Não gera quantidades.
CREATE TABLE IF NOT EXISTS conciliacoes_legado (
  id INTEGER PRIMARY KEY,
  trecho_id TEXT NOT NULL REFERENCES trechos(id),
  metros_assentado REAL NOT NULL,
  metros_reaterrado REAL NOT NULL,
  motivo TEXT NOT NULL,
  responsavel TEXT NOT NULL,
  em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conciliacao_legado_apontamentos (
  apontamento_id INTEGER PRIMARY KEY REFERENCES apontamentos(id),
  conciliacao_id INTEGER NOT NULL REFERENCES conciliacoes_legado(id)
);

-- Soldas informadas pela equipe e verificadas por outra pessoa (o previsto ⌈L/6⌉ continua só estimativa)
CREATE TABLE IF NOT EXISTS soldas (
  id INTEGER PRIMARY KEY,
  alvo_tipo TEXT NOT NULL, alvo_id TEXT NOT NULL,
  data TEXT NOT NULL,
  equipe_id TEXT REFERENCES equipes(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('ELETROFUSAO','TOPO')),
  quantidade INTEGER NOT NULL CHECK (quantidade > 0),
  posicao_m REAL,
  soldador TEXT NOT NULL,
  maquina TEXT,
  informado_por TEXT NOT NULL,
  verificado_em TEXT, verificado_por TEXT,
  resultado TEXT CHECK (resultado IN ('APROVADA','REPROVADA')),
  obs TEXT,
  registrado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS apontamento_quantidades (
  apontamento_id INTEGER NOT NULL REFERENCES apontamentos(id),
  servico TEXT NOT NULL,
  unidade TEXT NOT NULL,
  previsto REAL,
  confirmado REAL NOT NULL,
  PRIMARY KEY (apontamento_id, servico, unidade)
);

CREATE TABLE IF NOT EXISTS fotos (
  id INTEGER PRIMARY KEY,
  alvo_tipo TEXT NOT NULL, alvo_id TEXT NOT NULL,
  area TEXT,
  categoria TEXT NOT NULL CHECK (categoria IN ('SINALIZACAO','EXECUCAO','CONCLUIDO')),
  arquivo TEXT NOT NULL,
  data_hora TEXT NOT NULL,
  lat REAL, lon REAL,
  carimbo TEXT NOT NULL,                -- texto exibido sobre a foto (não é gravado na imagem)
  sha256 TEXT,                         -- hash do ARQUIVO ORIGINAL guardado (NULL = foto legada carimbada)
  bytes INTEGER,
  mime TEXT,
  origem_data TEXT,                    -- EXIF · DISPOSITIVO · ENVIO · LEGADO
  origem_gps TEXT,                     -- EXIF · NAVEGADOR · (NULL = indisponível)
  enviada_em TEXT,
  validacao TEXT                       -- DECODIFICADA (Pillow/PNG) · ESTRUTURAL (JPEG sem Pillow) · INVALIDA · ARQUIVO_AUSENTE
);
-- índice único de fotos.sha256: criado por servicos.aplicar_esquema quando a coluna existe (migração v6)

CREATE TABLE IF NOT EXISTS execucao (
  alvo_tipo TEXT NOT NULL, alvo_id TEXT NOT NULL,
  metros_executados REAL NOT NULL DEFAULT 0,
  metros_reaterrados REAL NOT NULL DEFAULT 0,
  concluido INTEGER NOT NULL DEFAULT 0,
  ok_fiscal_em TEXT, ok_fiscal_por TEXT,
  medicao_id INTEGER REFERENCES medicoes(id),
  recomposicao_ok INTEGER NOT NULL DEFAULT 0,
  recomposicao_medicao_id INTEGER REFERENCES medicoes(id),
  PRIMARY KEY (alvo_tipo, alvo_id)
);

CREATE TABLE IF NOT EXISTS ligacoes_prediais (
  id INTEGER PRIMARY KEY,
  trecho_id TEXT NOT NULL REFERENCES trechos(id),
  endereco TEXT,
  concluida INTEGER NOT NULL DEFAULT 0 CHECK (concluida IN (0,1))
);

-- ---------------------------------------------------------------- cadastro / GDOC
CREATE TABLE IF NOT EXISTS cadastro (
  trecho_id TEXT PRIMARY KEY REFERENCES trechos(id),
  etapa TEXT NOT NULL,
  revisao INTEGER NOT NULL DEFAULT 0,
  empresa TEXT,
  data_envio TEXT,
  arquivos TEXT,
  protocolo_gdoc TEXT,
  motivo_negativa TEXT,
  memorando_eset TEXT,
  medicao_id INTEGER REFERENCES medicoes(id),
  atualizado_em TEXT NOT NULL
);

-- Conferência interna Ankara do cadastro recebido da empresa, antes do protocolo no GDOC (v8). NÃO é aprovação da
-- Caesb: serve para achar divergência com o levantamento de campo antes de protocolar. NAO_CONFORME impede o
-- protocolo daquela revisão e permite devolver à empresa (nova revisão).
CREATE TABLE IF NOT EXISTS revisoes_cadastro (
  id INTEGER PRIMARY KEY,
  trecho_id TEXT NOT NULL REFERENCES trechos(id),
  revisao INTEGER NOT NULL,            -- Rev. N da esteira conferida
  resultado TEXT NOT NULL CHECK (resultado IN ('CONFORME','NAO_CONFORME')),
  checklist TEXT NOT NULL,             -- JSON {item: true|false}
  revisor TEXT NOT NULL,
  obs TEXT,
  em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cadastro_historico (
  id INTEGER PRIMARY KEY,
  trecho_id TEXT NOT NULL,
  de_etapa TEXT, para_etapa TEXT NOT NULL,
  dados TEXT,
  em TEXT NOT NULL
);

-- ---------------------------------------------------------------- medição
-- tipo TESTE: piloto, nunca oficial. OFICIAL só depois da validação das regras, do acesso e da
-- exportação no modelo (parâmetro medicao_oficial_liberada).
CREATE TABLE IF NOT EXISTS medicoes (
  id INTEGER PRIMARY KEY,
  numero INTEGER NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'TESTE' CHECK (tipo IN ('TESTE','OFICIAL')),
  periodo_ini TEXT NOT NULL,
  periodo_fim TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ABERTA' CHECK (status IN ('ABERTA','FECHADA')),
  congelada_em TEXT,                   -- fechamento: preços, fatores e totais congelados
  resumo_congelado TEXT,               -- JSON do resumo no fechamento (revisão cadastral posterior não recalcula)
  fechada_por TEXT, fechada_em TEXT,   -- v13: quem fechou (usuário da sessão) e quando
  conferencia_id INTEGER,              -- v13: conferência interna CONFORME que liberou o fechamento
  UNIQUE (tipo, numero)
);

-- Lançamento guarda quantidade e item; o valor é calculado na totalização (ordem do BM).
-- status PENDENTE = sem item/regra com fonte: não entra em valor (nunca R$ 0 contratual).
CREATE TABLE IF NOT EXISTS medicao_lancamentos (
  id INTEGER PRIMARY KEY,
  medicao_id INTEGER NOT NULL REFERENCES medicoes(id),
  gaveta INTEGER NOT NULL CHECK (gaveta BETWEEN 1 AND 4),
  servico TEXT NOT NULL,
  bm_item_id INTEGER REFERENCES bm_itens(id),
  alvo_tipo TEXT, alvo_id TEXT,
  nf_id INTEGER REFERENCES notas_fiscais(id),
  material_id TEXT REFERENCES materiais(id),
  unidade TEXT NOT NULL,
  quantidade REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDENTE' CHECK (status IN ('PROPOSTO','PENDENTE')),
  motivo TEXT,
  observacao TEXT,
  preco_congelado REAL,                -- preço sem BDI do item no fechamento da medição
  classificacao_congelada TEXT,
  item_congelado TEXT,
  chave TEXT                           -- v13: parcela (tipo da medição|gaveta|serviço|alvo|item|unid.): única entre medições
);

-- v13: conferência interna da medição de TESTE pela engenharia (Ankara), antes do fechamento. Guarda o retrato das
-- evidências e pendências de cada lançamento e a assinatura dos lançamentos conferidos: se um lançamento mudar depois,
-- a conferência deixa de valer. Não é aprovação da Caesb nem libera medição oficial.
CREATE TABLE IF NOT EXISTS conferencias_medicao (
  id INTEGER PRIMARY KEY,
  medicao_id INTEGER NOT NULL REFERENCES medicoes(id),
  resultado TEXT NOT NULL CHECK (resultado IN ('CONFORME','NAO_CONFORME')),
  checklist TEXT NOT NULL,
  assinatura TEXT NOT NULL,
  retrato TEXT NOT NULL,
  obs TEXT,
  por TEXT NOT NULL,
  em TEXT NOT NULL
);

-- ---------------------------------------------------------------- planejamento (v12, módulo D)
-- Programação das equipes: o PLANEJADO (equipe, dia, trecho/nó, serviço e materiais previstos). Não é presença nem
-- execução: o check-in da equipe naquele dia e alvo a marca como REALIZADA; o que não aconteceu é encerrado com motivo.
CREATE TABLE IF NOT EXISTS programacoes (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL,
  equipe_id TEXT NOT NULL REFERENCES equipes(id),
  alvo_tipo TEXT NOT NULL, alvo_id TEXT NOT NULL,
  servico TEXT NOT NULL,
  ini_m REAL, fim_m REAL,              -- trecho: intervalo previsto (opcional)
  obs TEXT,
  status TEXT NOT NULL DEFAULT 'PLANEJADA' CHECK (status IN ('PLANEJADA','REALIZADA','NAO_REALIZADA','CANCELADA')),
  checkin_id INTEGER REFERENCES checkins(id),
  motivo TEXT,
  criada_por TEXT NOT NULL, criada_em TEXT NOT NULL,
  encerrada_por TEXT, encerrada_em TEXT
);
CREATE TABLE IF NOT EXISTS programacao_materiais (
  id INTEGER PRIMARY KEY,
  programacao_id INTEGER NOT NULL REFERENCES programacoes(id),
  material_id TEXT NOT NULL REFERENCES materiais(id),
  quantidade REAL NOT NULL CHECK (quantidade > 0)
);
CREATE INDEX IF NOT EXISTS ix_programacoes ON programacoes(data, equipe_id);

-- ---------------------------------------------------------------- compras e recebimento (v11, módulo C)
CREATE TABLE IF NOT EXISTS fornecedores (
  id INTEGER PRIMARY KEY,
  cnpj TEXT UNIQUE,                    -- só dígitos (14)
  nome TEXT NOT NULL,
  contato TEXT,
  criado_por TEXT NOT NULL, criado_em TEXT NOT NULL
);
-- Documento anexo (XML da NF-e, PDF/imagem da NF, laudo, romaneio) guardado byte a byte em <pasta do banco>/documentos,
-- nomeado pelo SHA-256 e conferido no backup.
CREATE TABLE IF NOT EXISTS documentos (
  id INTEGER PRIMARY KEY,
  tipo TEXT NOT NULL CHECK (tipo IN ('NFE_XML','NF_PDF','NF_IMAGEM','LAUDO','ROMANEIO','OUTRO')),
  arquivo TEXT NOT NULL,
  nome_original TEXT,
  sha256 TEXT NOT NULL UNIQUE,
  bytes INTEGER NOT NULL,
  mime TEXT,
  enviado_por TEXT NOT NULL, enviado_em TEXT NOT NULL
);
-- Solicitação → aprovação (outra pessoa) → pedido. Pedido nunca vira estoque.
CREATE TABLE IF NOT EXISTS solicitacoes_compra (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL,
  solicitante TEXT NOT NULL,
  motivo TEXT NOT NULL,
  alvo_tipo TEXT, alvo_id TEXT,        -- frente/trecho/nó que precisa do material (opcional)
  status TEXT NOT NULL DEFAULT 'ABERTA' CHECK (status IN ('ABERTA','APROVADA','RECUSADA','CANCELADA')),
  decidida_por TEXT, decidida_em TEXT, decisao_motivo TEXT,
  criada_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS solicitacao_itens (
  id INTEGER PRIMARY KEY,
  solicitacao_id INTEGER NOT NULL REFERENCES solicitacoes_compra(id),
  material_id TEXT NOT NULL REFERENCES materiais(id),
  quantidade REAL NOT NULL CHECK (quantidade > 0)
);
CREATE TABLE IF NOT EXISTS pedidos_compra (
  id INTEGER PRIMARY KEY,
  numero TEXT NOT NULL UNIQUE,
  data TEXT NOT NULL,
  fornecedor_id INTEGER NOT NULL REFERENCES fornecedores(id),
  solicitacao_id INTEGER REFERENCES solicitacoes_compra(id),
  prazo TEXT,
  status TEXT NOT NULL DEFAULT 'EMITIDO' CHECK (status IN ('EMITIDO','CANCELADO','ENCERRADO')),
  faturamento_etapas INTEGER NOT NULL DEFAULT 0,   -- intenção registrada; regime não aplicado (matriz pendente)
  emitido_por TEXT NOT NULL, emitido_em TEXT NOT NULL,
  encerrado_motivo TEXT
);
CREATE TABLE IF NOT EXISTS pedido_itens (
  id INTEGER PRIMARY KEY,
  pedido_id INTEGER NOT NULL REFERENCES pedidos_compra(id),
  material_id TEXT NOT NULL REFERENCES materiais(id),
  quantidade REAL NOT NULL CHECK (quantidade > 0),
  valor_unitario REAL NOT NULL CHECK (valor_unitario >= 0)
);
-- Entrega (parcial ou total) de uma NF conferida: entra em QUARENTENA, nunca direto no estoque.
CREATE TABLE IF NOT EXISTS recebimentos (
  id INTEGER PRIMARY KEY,
  nf_id INTEGER NOT NULL REFERENCES notas_fiscais(id),
  data TEXT NOT NULL,
  documento TEXT,                      -- canhoto / romaneio de entrega
  recebido_por TEXT NOT NULL, registrado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recebimento_itens (
  id INTEGER PRIMARY KEY,
  recebimento_id INTEGER NOT NULL REFERENCES recebimentos(id),
  nf_item_id INTEGER NOT NULL REFERENCES nf_itens(id),
  quantidade REAL NOT NULL CHECK (quantidade > 0),
  movimento_id INTEGER NOT NULL REFERENCES movimentos(id)
);
-- Inspeção de cada item entregue: aceito entra no estoque; recusado volta ao fornecedor na própria entrega.
CREATE TABLE IF NOT EXISTS inspecoes (
  id INTEGER PRIMARY KEY,
  recebimento_item_id INTEGER NOT NULL UNIQUE REFERENCES recebimento_itens(id),
  aceito REAL NOT NULL CHECK (aceito >= 0),
  recusado REAL NOT NULL CHECK (recusado >= 0),
  laudo TEXT NOT NULL,                 -- referência do laudo/inspeção
  documento_id INTEGER REFERENCES documentos(id),
  motivo_recusa TEXT,
  inspecionado_por TEXT NOT NULL, inspecionado_em TEXT NOT NULL,
  movimento_aceito_id INTEGER REFERENCES movimentos(id)
);
-- Devolução ao fornecedor de material JÁ aceito (defeito descoberto depois): sai do disponível.
CREATE TABLE IF NOT EXISTS devolucoes_fornecedor (
  id INTEGER PRIMARY KEY,
  nf_id INTEGER NOT NULL REFERENCES notas_fiscais(id),
  nf_item_id INTEGER NOT NULL REFERENCES nf_itens(id),
  data TEXT NOT NULL,
  quantidade REAL NOT NULL CHECK (quantidade > 0),
  motivo TEXT NOT NULL,
  documento TEXT,                      -- NF de devolução / documento de saída
  responsavel TEXT NOT NULL, registrado_em TEXT NOT NULL,
  movimento_id INTEGER NOT NULL REFERENCES movimentos(id)
);
-- Transferência de material entre equipes em campo, sem passar pelo almoxarifado (sessões abertas das duas).
CREATE TABLE IF NOT EXISTS transferencias (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL,
  material_id TEXT NOT NULL REFERENCES materiais(id),
  quantidade REAL NOT NULL CHECK (quantidade > 0),
  de_equipe TEXT NOT NULL REFERENCES equipes(id),
  para_equipe TEXT NOT NULL REFERENCES equipes(id),
  de_checkin INTEGER NOT NULL REFERENCES checkins(id),
  para_checkin INTEGER NOT NULL REFERENCES checkins(id),
  autorizacao TEXT NOT NULL,
  motivo TEXT,
  responsavel TEXT NOT NULL, registrado_em TEXT NOT NULL
);
-- Inventário do almoxarifado: contagem por uma pessoa, ajuste aprovado por outra (permissão inventario_ajustar).
CREATE TABLE IF NOT EXISTS inventarios (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL,
  contado_por TEXT NOT NULL, contado_em TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'CONTADO' CHECK (status IN ('CONTADO','AJUSTADO','DESCARTADO')),
  decidido_por TEXT, decidido_em TEXT, decisao_motivo TEXT,
  obs TEXT
);
CREATE TABLE IF NOT EXISTS inventario_itens (
  id INTEGER PRIMARY KEY,
  inventario_id INTEGER NOT NULL REFERENCES inventarios(id),
  material_id TEXT NOT NULL REFERENCES materiais(id),
  saldo_sistema REAL NOT NULL,         -- saldo físico do sistema no momento da contagem
  contado REAL NOT NULL CHECK (contado >= 0),
  movimento_id INTEGER REFERENCES movimentos(id)
);
CREATE INDEX IF NOT EXISTS ix_nf_linhas ON nf_linhas(nf_id);
CREATE INDEX IF NOT EXISTS ix_receb_itens ON recebimento_itens(nf_item_id);

-- ---------------------------------------------------------------- campo complementar (v10, módulo B)
-- Etapas que não geram quantidade nem entram no resumo de execução (por isso ficam fora de intervalos_execucao):
--   LIBERACAO_TOPOGRAFICA: locação conferida pela topografia (referência da nota de serviço) — onde a vala pode abrir;
--   ESCAVADO: vala aberta (informativo; não é pré-requisito do assentamento sem a decisão D-21).
-- Nunca apagadas: anulação com motivo e responsável.
CREATE TABLE IF NOT EXISTS etapas_complementares (
  id INTEGER PRIMARY KEY,
  trecho_id TEXT NOT NULL REFERENCES trechos(id),
  etapa TEXT NOT NULL CHECK (etapa IN ('LIBERACAO_TOPOGRAFICA','ESCAVADO')),
  ini_m REAL NOT NULL CHECK (ini_m >= 0),
  fim_m REAL NOT NULL,
  data TEXT NOT NULL,
  registrado_por TEXT NOT NULL,
  referencia TEXT,                     -- nota de serviço / locação / caderneta
  obs TEXT,
  registrado_em TEXT NOT NULL,
  anulado_em TEXT, anulado_por TEXT, anulado_motivo TEXT,
  CHECK (fim_m > ini_m)
);
-- Ocorrências de campo: IMPEDIMENTO (o que impede o avanço) e NAO_CONFORMIDADE (o que precisa ser corrigido).
-- Abertas com descrição; resolvidas com a resolução/correção, por quem e quando. Nunca apagadas.
CREATE TABLE IF NOT EXISTS ocorrencias (
  id INTEGER PRIMARY KEY,
  alvo_tipo TEXT NOT NULL, alvo_id TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('IMPEDIMENTO','NAO_CONFORMIDADE')),
  categoria TEXT NOT NULL,
  descricao TEXT NOT NULL,
  data TEXT NOT NULL,
  equipe_id TEXT REFERENCES equipes(id),
  aberta_por TEXT NOT NULL, aberta_em TEXT NOT NULL,
  resolvida_em TEXT, resolvida_por TEXT, resolucao TEXT
);
CREATE INDEX IF NOT EXISTS ix_ocorrencias_alvo ON ocorrencias(alvo_tipo, alvo_id);
CREATE INDEX IF NOT EXISTS ix_etapas_compl ON etapas_complementares(trecho_id, etapa);

-- ---------------------------------------------------------------- acesso e auditoria (v9, módulo A)
-- Usuários do sistema: senha só como hash PBKDF2. Perfis e permissões em config/perfis.json (provisório, D-10).
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY,
  login TEXT NOT NULL UNIQUE,
  nome TEXT NOT NULL,
  perfil TEXT NOT NULL,
  senha TEXT NOT NULL,
  equipe_id TEXT REFERENCES equipes(id),     -- perfil EQUIPE só lança para a própria equipe
  ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0,1)),
  criado_em TEXT NOT NULL,
  criado_por TEXT NOT NULL
);
-- Sessão: só o SHA-256 do token (o token fica no cookie HttpOnly do navegador)
CREATE TABLE IF NOT EXISTS sessoes (
  token_sha TEXT PRIMARY KEY,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
  criada_em TEXT NOT NULL,
  expira_em TEXT NOT NULL,
  origem TEXT
);
-- Toda gravação (aceita ou recusada), login e saída. Nunca é apagada pelo sistema.
CREATE TABLE IF NOT EXISTS auditoria (
  id INTEGER PRIMARY KEY,
  em TEXT NOT NULL,
  usuario_id INTEGER REFERENCES usuarios(id),
  login TEXT, perfil TEXT,
  metodo TEXT NOT NULL, rota TEXT NOT NULL,
  alvo_tipo TEXT, alvo_id TEXT,
  status INTEGER NOT NULL,             -- 200 aceito · 4xx recusado · 5xx falha
  resultado TEXT,                      -- resposta resumida ou motivo da recusa
  corpo TEXT,                          -- requisição sem senha nem conteúdo de arquivo
  idem TEXT                            -- chave de reenvio
);
-- Reenvio idempotente: a mesma chave do mesmo usuário devolve a mesma resposta, sem executar de novo
CREATE TABLE IF NOT EXISTS requisicoes (
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
  chave TEXT NOT NULL,
  rota TEXT NOT NULL,
  corpo_sha TEXT NOT NULL,
  resposta TEXT NOT NULL,
  em TEXT NOT NULL,
  PRIMARY KEY (usuario_id, chave)
);
CREATE INDEX IF NOT EXISTS ix_auditoria_alvo ON auditoria(alvo_id);

CREATE INDEX IF NOT EXISTS ix_itens_ativ ON itens_projeto(atividade_id);
CREATE INDEX IF NOT EXISTS ix_ativ_elem ON atividades(elemento_id);
CREATE INDEX IF NOT EXISTS ix_avisos_item ON avisos_origem(item_id);
CREATE INDEX IF NOT EXISTS ix_mov_mat ON movimentos(material_id);
CREATE INDEX IF NOT EXISTS ix_reservas ON reservas(material_id, status);
CREATE INDEX IF NOT EXISTS ix_intervalos ON intervalos_execucao(trecho_id, etapa);
CREATE INDEX IF NOT EXISTS ix_soldas ON soldas(alvo_tipo, alvo_id);
CREATE INDEX IF NOT EXISTS ix_fotos_alvo ON fotos(alvo_tipo, alvo_id);
CREATE INDEX IF NOT EXISTS ix_lanc_med ON medicao_lancamentos(medicao_id, gaveta);
CREATE INDEX IF NOT EXISTS ix_prov_fonte ON proveniencia(fonte_id);
