-- Sistema de Gestão e Mapa Iluminado — Morro da Cruz (Caesb × Ankara nº 10239/2026, LC 014/2026)
-- Banco relacional SQLite. Convenção: alvo_tipo ∈ ('TRECHO','ELEMENTO').
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- parâmetros
CREATE TABLE IF NOT EXISTS parametros (
  chave TEXT PRIMARY KEY,
  valor TEXT NOT NULL
);

-- Índices de reajuste por janela de vigência (aba REAJUSTE da 03.3.2)
CREATE TABLE IF NOT EXISTS reajuste_indices (
  vigencia_ini TEXT NOT NULL,          -- ISO yyyy-mm-dd (inclusive)
  vigencia_fim TEXT NOT NULL,          -- ISO yyyy-mm-dd (inclusive)
  indice REAL NOT NULL,                -- 0.0329 = 3,29 %
  descricao TEXT,
  PRIMARY KEY (vigencia_ini)
);

-- ---------------------------------------------------------------- equipes
CREATE TABLE IF NOT EXISTS equipes (
  id TEXT PRIMARY KEY,                 -- Zona01..Zona11, ADUTORA, CH
  nome TEXT NOT NULL,
  cor TEXT                             -- cor pastel do polígono da frente (REV02)
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

-- ---------------------------------------------------------------- projeto (06.1 / 06.2)
-- Trechos da aba REDE (06.1 REV01). Perfil de vala vem das colunas AE:AH;
-- perfil ausente ou 'A CONFIRMAR' bloqueia o cálculo (auditoria E06).
CREATE TABLE IF NOT EXISTS trechos (
  id TEXT PRIMARY KEY,                 -- PONTO (col. R): Zona01_PB01_Rede_TR001
  item INTEGER,                        -- col. A
  frente_id TEXT REFERENCES equipes(id),  -- LOCAL (col. K)
  equipe TEXT,                         -- col. BM
  tipo TEXT,                           -- Rede / Adutora (col. BN)
  pb TEXT,                             -- col. BO
  prancha TEXT,                        -- col. U
  area TEXT,                           -- DELIMITAÇÃO (col. X)
  de_mm REAL,                          -- col. H
  material TEXT,
  solda TEXT,                          -- ELETROFUSÃO / TERMOFUSÃO (col. G)
  metodologia TEXT,                    -- VCA / MND (col. N)
  classe TEXT,                         -- PRIMÁRIA / SECUNDÁRIA / TERCIÁRIA (col. S)
  extensao_m REAL NOT NULL,            -- col. M
  codigo_bm TEXT,                      -- assentamento (col. AC) -> BM Vertical 2.2_<código>
  recobrimento_m REAL, profundidade_m REAL, largura_m REAL, lastro_m REAL,   -- AE:AH
  perfil_status TEXT,                  -- NULL = definido; 'A CONFIRMAR' = bloqueado
  quantidades TEXT NOT NULL,           -- JSON {coluna: quantidade total do trecho} (AL:BK)
  no_ini TEXT, no_fim TEXT,            -- cols. BP / BQ
  handle TEXT,
  utm_ini TEXT, utm_fim TEXT,          -- JSON [E,N]
  lat REAL, lon REAL,                  -- meio do trecho
  aviso_problema TEXT,                 -- AA (vermelho)
  aviso_sugestao TEXT,                 -- AB (azul)
  observacao TEXT
);

-- Elementos físicos da 06.2 (1.191 = 1.059 nós + 132 caixas/dispositivos).
CREATE TABLE IF NOT EXISTS elementos (
  id TEXT PRIMARY KEY,                 -- identificador da auditoria: SUBDMC1_NÓ1.8 (único)
  numero TEXT NOT NULL,                -- número no projeto: NÓ1.8, DF-33, MV-11 ...
  nomenclaturas TEXT,                  -- "Zona01_PB01_CH_DF-33 | Zona01_PB01_Rede_DF-33"
  tipo TEXT NOT NULL,                  -- NÓ, DF, VM, VRP, MV, VTF, HID
  pb TEXT,
  zona TEXT,                           -- zona física
  handle TEXT,
  utm_e REAL, utm_n REAL,
  lat REAL, lon REAL,                  -- NULL = bandeja "Sem Posição" (nunca inventar)
  status_posicao TEXT                  -- COERENTE / PROVÁVEL — EXIGE VALIDAÇÃO / NÃO DETERMINADO
);

-- Conjunto de trabalho = nomenclatura por equipe (1.242):
-- Zona01_PB01_Rede_DF-33 e Zona01_PB01_CH_DF-33 são dois conjuntos do mesmo elemento.
CREATE TABLE IF NOT EXISTS conjuntos (
  id TEXT PRIMARY KEY,                 -- nomenclatura completa
  elemento_id TEXT NOT NULL REFERENCES elementos(id),
  frente_id TEXT REFERENCES equipes(id)   -- LOCAL (Zona01..Zona11, ADUTORA, CH)
);

-- Linhas de itens da aba CONEXÕES (6.539). M e UN nunca são somados no mesmo
-- contador (auditoria N02). quantidade NULL = ainda não importada da 06.2 xlsm
-- (estrutura veio das EVIDÊNCIAS REV08) — nunca é tratada como zero.
CREATE TABLE IF NOT EXISTS pecas (
  id INTEGER PRIMARY KEY,
  conjunto_id TEXT NOT NULL REFERENCES conjuntos(id),
  descricao TEXT NOT NULL,
  diametro TEXT,
  material TEXT,
  unidade TEXT NOT NULL,
  unidade_fonte TEXT,                  -- '06.2' ou 'REGRA' (tubo/escada = M; peça = UN)
  quantidade REAL,
  codigo_bm TEXT,
  trechos TEXT,                        -- coluna TRECHO (06.1), separados por " / "
  aviso_problema TEXT,                 -- AA
  aviso_sugestao TEXT,                 -- AB
  linha_origem INTEGER UNIQUE          -- linha da aba CONEXÕES, para rastreabilidade
);

-- ---------------------------------------------------------------- BM
CREATE TABLE IF NOT EXISTS bm_itens (
  id INTEGER PRIMARY KEY,
  planilha TEXT NOT NULL CHECK (planilha IN ('JUNTADA','VERTICAL')),
  item TEXT NOT NULL,                  -- Vertical: 2.2_5.2.1 · Juntada: 5.2.1
  item_bm TEXT,                        -- item da Juntada correspondente (5.2.1)
  subgrupo TEXT,                       -- Vertical: código do cronograma FF (2.2)
  subgrupo_nome TEXT,
  codigo_caesb TEXT,
  classificacao TEXT,                  -- MATERIAL / SERVIÇO (define o BDI)
  descricao TEXT NOT NULL,
  unidade TEXT,
  quantidade REAL,
  preco_unitario REAL,                 -- sem BDI (P0 = (Σ + BDI) × (1 − K))
  valor_total REAL,
  atributos TEXT,                      -- JSON das colunas técnicas (Juntada B:J / Vertical F:N)
  linha_origem INTEGER,
  UNIQUE (planilha, item)
);

-- ---------------------------------------------------------------- almoxarifado
CREATE TABLE IF NOT EXISTS materiais (
  id TEXT PRIMARY KEY,
  descricao TEXT NOT NULL,
  unidade TEXT NOT NULL,
  propriedade TEXT NOT NULL CHECK (propriedade IN ('CAESB','ANKARA','CONSUMO')),
  preco_unitario REAL NOT NULL DEFAULT 0,   -- CAESB sempre 0 no BM
  bm_item_id INTEGER REFERENCES bm_itens(id),
  qtd_projeto REAL,                          -- quantitativo de projeto (06.1/06.2)
  estoque_caesb REAL                         -- saldo informado no depósito Caesb (tubos)
);

CREATE TABLE IF NOT EXISTS notas_fiscais (
  id INTEGER PRIMARY KEY,
  numero TEXT NOT NULL,
  chave_nfe TEXT,
  fornecedor TEXT,
  data_entrega TEXT NOT NULL,
  arquivo TEXT,
  faturamento_etapas INTEGER NOT NULL DEFAULT 0,   -- Seção 7 do SL0327
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
    'ROMANEIO_CAESB',        -- retirada no depósito Caesb (entra no canteiro)
    'EMPRESTIMO_OUTRA_OBRA', -- tubo Caesb emprestado p/ outra obra (sai do canteiro)
    'ENTRADA_NF',            -- material Ankara (nota fiscal)
    'ENTRADA_CONSUMO',       -- caminhão de areia/brita/terra/cimento/madeira
    'CUSTODIA',              -- check-in: almoxarifado -> equipe
    'APLICADO',              -- check-out: custódia -> obra
    'SOBRA',                 -- check-out: custódia -> almoxarifado
    'PERDA',                 -- check-out: quebrou/perdeu
    'BAIXA_TEORICA'          -- consumo diário por volume geométrico
  )),
  quantidade REAL NOT NULL CHECK (quantidade >= 0),
  equipe_id TEXT REFERENCES equipes(id),
  alvo_tipo TEXT, alvo_id TEXT,
  documento TEXT,
  status TEXT,                         -- ACEITO / QUARENTENA (entradas)
  motivo TEXT,
  checkin_id INTEGER REFERENCES checkins(id),
  nf_id INTEGER REFERENCES notas_fiscais(id)
);

-- ---------------------------------------------------------------- campo
CREATE TABLE IF NOT EXISTS checkins (
  id INTEGER PRIMARY KEY,
  data TEXT NOT NULL,
  equipe_id TEXT NOT NULL REFERENCES equipes(id),
  alvo_tipo TEXT, alvo_id TEXT,        -- trecho/nó atacado no dia (pin no mapa)
  contingencia TEXT,                   -- 'Confecção de Bloquetes' | 'Execução de Calçadas/Asfalto'
  encerrado INTEGER NOT NULL DEFAULT 0
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
  estaca_ini TEXT, estaca_fim TEXT     -- compatibilização com a NS da topografia
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

-- Estado consolidado de execução/fiscalização por trecho ou elemento
CREATE TABLE IF NOT EXISTS execucao (
  alvo_tipo TEXT NOT NULL, alvo_id TEXT NOT NULL,
  metros_executados REAL NOT NULL DEFAULT 0,
  metros_reaterrados REAL NOT NULL DEFAULT 0,
  concluido INTEGER NOT NULL DEFAULT 0,          -- 100 % executado e reaterrado
  ok_fiscal_em TEXT, ok_fiscal_por TEXT,
  medicao_id INTEGER REFERENCES medicoes(id),     -- medição em que entrou
  recomposicao_ok INTEGER NOT NULL DEFAULT 0,
  recomposicao_medicao_id INTEGER REFERENCES medicoes(id),
  PRIMARY KEY (alvo_tipo, alvo_id)
);

-- Ligações prediais (etapa futura, binária)
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
  arquivos TEXT,                       -- JSON com DWG/PDF/BIM recebidos
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
CREATE TABLE IF NOT EXISTS medicoes (
  id INTEGER PRIMARY KEY,
  numero INTEGER NOT NULL UNIQUE,
  periodo_ini TEXT NOT NULL,
  periodo_fim TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ABERTA' CHECK (status IN ('ABERTA','FECHADA'))
);

-- Gavetas: 1 serviços de trechos + 20 % mat.; 2 NF 80 %; 3 cadastro GDOC; 4 calçada/asfalto
CREATE TABLE IF NOT EXISTS medicao_lancamentos (
  id INTEGER PRIMARY KEY,
  medicao_id INTEGER NOT NULL REFERENCES medicoes(id),
  gaveta INTEGER NOT NULL CHECK (gaveta BETWEEN 1 AND 4),
  servico TEXT NOT NULL,
  bm_item_id INTEGER REFERENCES bm_itens(id),   -- NULL = pendente de vínculo (nunca descartado)
  alvo_tipo TEXT, alvo_id TEXT,
  nf_id INTEGER REFERENCES notas_fiscais(id),
  material_id TEXT REFERENCES materiais(id),
  unidade TEXT NOT NULL,
  quantidade REAL NOT NULL,
  valor REAL NOT NULL DEFAULT 0,
  observacao TEXT
);

CREATE INDEX IF NOT EXISTS ix_pecas_conj ON pecas(conjunto_id);
CREATE INDEX IF NOT EXISTS ix_conj_elem ON conjuntos(elemento_id);
CREATE INDEX IF NOT EXISTS ix_mov_mat ON movimentos(material_id);
CREATE INDEX IF NOT EXISTS ix_fotos_alvo ON fotos(alvo_tipo, alvo_id);
CREATE INDEX IF NOT EXISTS ix_lanc_med ON medicao_lancamentos(medicao_id, gaveta);
