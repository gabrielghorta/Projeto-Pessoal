-- Sistema de Gestão e Mapa Iluminado — Morro da Cruz (CT Caesb × Ankara 10239/2026, LC 014/2026)
-- Esquema v5. Banco SQLite local.
--   * Identidades estáveis próprias (TR-/EL-/AT-/IP-) separadas dos nomes visíveis, que são versionados.
--   * Toda linha importada guarda proveniência (arquivo + hash + aba + linha + células).
--   * Importação nunca apaga: o que sai de uma revisão fica com vigente = 0.
--   * alvo_tipo ∈ ('TRECHO','ATIVIDADE').
--   * v3: pendência bloqueante, escopo explícito das decisões, medição fechada congelada,
--     identidade dos itens pela assinatura técnica completa (não pela ordem das linhas).
--   * v4 (etapa 3, estoque): reservas, saldo que fica com a equipe, empréstimo autorizado, estorno sem apagar,
--     baixa teórica fora do saldo físico.
--   * v5: custódia por sessão (fechamentos em ordem), reserva nunca descoberta, retificação de fechamento.
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

CREATE TABLE IF NOT EXISTS notas_fiscais (
  id INTEGER PRIMARY KEY,
  numero TEXT NOT NULL,
  chave_nfe TEXT,
  fornecedor TEXT,
  data_entrega TEXT NOT NULL,
  arquivo TEXT,
  faturamento_etapas INTEGER NOT NULL DEFAULT 0,   -- só registro da intenção; regime não aplicado (matriz pendente)
  laudo_arquivo TEXT,
  status TEXT NOT NULL DEFAULT 'QUARENTENA' CHECK (status IN ('ACEITO','QUARENTENA'))
);

CREATE TABLE IF NOT EXISTS nf_itens (
  id INTEGER PRIMARY KEY,
  nf_id INTEGER NOT NULL REFERENCES notas_fiscais(id),
  material_id TEXT NOT NULL REFERENCES materiais(id),
  quantidade REAL NOT NULL,
  valor_unitario REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS movimentos (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL,
  material_id TEXT NOT NULL REFERENCES materiais(id),
  tipo TEXT NOT NULL CHECK (tipo IN (
    'ROMANEIO_CAESB','EMPRESTIMO_OUTRA_OBRA','ENTRADA_NF','ENTRADA_CONSUMO',
    'CUSTODIA','APLICADO','SOBRA','PERDA','BAIXA_TEORICA')),
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
  retificacao_id INTEGER REFERENCES retificacoes(id)   -- lançamento criado por retificação de fechamento
);

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
  estaca_ini TEXT, estaca_fim TEXT
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
  carimbo TEXT NOT NULL
);

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
  item_congelado TEXT
);

CREATE INDEX IF NOT EXISTS ix_itens_ativ ON itens_projeto(atividade_id);
CREATE INDEX IF NOT EXISTS ix_ativ_elem ON atividades(elemento_id);
CREATE INDEX IF NOT EXISTS ix_avisos_item ON avisos_origem(item_id);
CREATE INDEX IF NOT EXISTS ix_mov_mat ON movimentos(material_id);
CREATE INDEX IF NOT EXISTS ix_reservas ON reservas(material_id, status);
CREATE INDEX IF NOT EXISTS ix_fotos_alvo ON fotos(alvo_tipo, alvo_id);
CREATE INDEX IF NOT EXISTS ix_lanc_med ON medicao_lancamentos(medicao_id, gaveta);
CREATE INDEX IF NOT EXISTS ix_prov_fonte ON proveniencia(fonte_id);
