# Etapas 0 e 1 — preparadas para aprovação

CT 10239/2026 · 15/10/2026 · **revisto em 16/10/2026** após a auditoria independente do commit `b63b5db`:
os 12 achados (A01–A12) foram corrigidos e estão detalhados em `docs/CORRECOES_AUDITORIA_b63b5db.md`.

O código está pronto e testado, mas **ainda não foi executado no seu banco**. A importação só altera o banco com `--aplicar`, e esse comando sempre faz antes um backup verificado.

## O que muda

### Etapa 0 — proteção

| Antes (MVP) | Agora |
|---|---|
| `seed.py` apagava o banco e recriava tudo | `seed.py` foi desativado; usar `importar.py`. |
| Sem backup | `backup.py criar \| verificar \| restaurar`. O backup copia o banco pela API do SQLite (inclui o WAL) e depois as fotos. O manifesto guarda SHA-256 e tamanho de cada arquivo, linhas **e SHA-256 do conteúdo** de cada tabela, e o `integrity_check`. **Completude:** toda foto citada no banco copiado precisa estar na cópia; senão o backup fica guardado como INCOMPLETO e a verificação falha. Os backups nunca são apagados. |
| Carga direta | **Simulação por padrão:** a importação roda inteira numa cópia temporária e mostra o relatório. `--aplicar` faz backup verificado e completo, depois executa tudo numa única transação. **As conferências são avaliadas antes do COMMIT:** se alguma reprovar (controles da revisão, totalização do BM, identidade com histórico sem conciliação), ou se houver erro, a transação inteira é desfeita, o banco fica byte a byte igual e o relatório da reprovação é gravado em `dados/relatorios/`. |
| Restauração manual | `backup.py restaurar` verifica o backup, cria antes um **backup completo do estado atual** (API do SQLite, inclui o WAL, com as fotos) e restaura em manutenção. Devolve fotos ausentes ou diferentes sem apagar as novas e confere o conteúdo final contra o manifesto. |
| Gravações durante manutenção | Backup, restauração e importação criam `MANUTENCAO.lock`; enquanto existir, o servidor recusa gravações (503). **Importação e restauração exigem o servidor parado** e recusam rodar se ele estiver respondendo. |
| Servidor abria qualquer banco | O servidor recusa banco v1 sem migração e só escuta em `127.0.0.1`, porque não tem autenticação. |

### Etapa 1 — importação

**Identidade estável:**

| Objeto | ID | Como é casado |
|---|---|---|
| Trecho | `TR-00001` | Pela **geometria física: handle CAD + pontas UTM** (o handle sozinho se repete em 123 trechos). O nome nunca decide sozinho. Trecho com histórico sem correspondência física (traçado alterado, divisão, união, exclusão) **reprova** a importação até haver de-para em `config/conciliacoes.json`. |
| Elemento físico | `EL-0001` | Pelo **handle CAD** (coluna AR); sem handle, pelo número do projeto (identidade provisória, **promovida** para o handle quando ele aparecer, mantendo ID e histórico). |
| Atividade (elemento × frente) | `AT-0001` | Pelo elemento + tipo de frente (Rede, CH ou Adutora). |
| Item de projeto (linha da 06.2) | `IP-000001` | Pela atividade + **assinatura técnica completa** (descrição, DE, PN, resina, tipo, solda, material). Correspondência ambígua cria itens novos com pendência. **Nunca pelo nº da linha nem pela ordem.** |

- O mesmo agrupamento por handle gerou exatamente os 1.191 grupos das EVIDÊNCIAS REV08: 1.191 de 1.191 iguais.

**Proveniência:**
- Cada registro guarda arquivo, SHA-256, revisão, aba, linha e as células lidas.
- Os nomes visíveis (PONTO, nomenclatura) ficam em `nomes_historico`.
- Cada diferença entre revisões fica em `alteracoes`, com valor antes e depois.

**Idempotência:**
- Reimportar os mesmos arquivos termina em `SEM_ALTERACOES`, com zero alterações registradas.
- O que sai de uma revisão fica com `vigente = 0`; nada é apagado.

**Unidades — só com fonte:**
- A unidade vem do item da Juntada indicado na coluna R da 06.2.
- Sem fonte, fica **PENDENTE**. Não há regra por descrição nem equivalência UN↔PÇ.

**Colunas da 06.2:**
- BA, BB, AW, AG e AH são importadas.
- Os avisos AA/AB viram texto de origem, separado por `|`, com a prioridade AW.

**Decisões posteriores** (`config/decisoes.json`):
- DF-05 sobreposta.
- Comparação 521 × 488 / saldo 33.
- Tês sem chamada (F10).
- MV-11, VTF-12 e VTF-16 sem posição.

A importação só **insere** decisões novas e nunca altera as existentes. O aviso de origem continua guardado. A decisão só aparece ligada a um aviso por **vínculo explícito** (nº do elemento + hash do texto) ou a um objeto pelo **escopo**; semelhança de texto aparece apenas como "possível relação — revisar", sem aplicar a decisão.

**Migração do banco v1 (MVP):**
- As tabelas antigas ficam preservadas como `v1_*`.
- As referências de movimentos, check-ins, apontamentos, fotos, execução, esteira e lançamentos passam para os IDs estáveis.
- Referência sem par mantém o valor antigo e vira pendência.
- Medições antigas viram `TESTE`; lançamentos de material antigos viram `PENDENTE`.

**BDI e K na ordem do BM:**
- Medição: `ROUND(q×p;2)` por item → Σ por classe → BDI por classe → K no total.
- P0 contratual: SUMPRODUCT por classe, arredondado.
- O arredondamento segue o do Excel: 6.026,69 × 47,50 = 286.267,775 → 286.267,78.

**Travas até a etapa financeira:**
- Sem 80/20, sem 100 % na aplicação e sem substituição automática de MND.
- Lançamento sem item ou regra fica `PENDENTE`, fora do valor.
- Medição só do tipo **TESTE**: a OFICIAL fica bloqueada e a exportação sai como `TESTE_…` com o aviso "NÃO OFICIAL".
- O pin do mapa diz "programado" (vem do check-in), não presença.

**Corrigido durante os testes com a base real:**
- Os 4 trechos MND têm profundidade 0 na 06.1 (não há vala), e a trava E06 bloqueava o apontamento deles. Agora o perfil de vala só é exigido em VCA, e o MND prevê apenas o comprimento.

## Evidências (planilhas reais do pacote de 15/10)

| Conferência | Resultado |
|---|---|
| Trechos / extensão | 1.436 / 110.686,03 m ✔ |
| Elementos / nós / caixas | 1.191 / 1.059 / 132 ✔ |
| Atividades / itens da 06.2 | 1.242 / 6.539 ✔ |
| BM Vertical / Juntada | 432 / 347 ✔ |
| Sem posição | MV-11, VTF-12, VTF-16 ✔ |
| P0 recalculado × célula `T556` | 49.878.748,6575869 = 49.878.748,6575869 ✔ |
| Contrato 3.1 × P0 do BM | 49.878.748,56 × 49.878.748,6575869 → **diferença +0,0975869 registrada, não ajustada** |
| Unidades da 06.2 | UN 6.051 linhas · **M 73 linhas = 72,95 m** · **PÇ 54** · **PENDENTE 361** (código "APROVAR — sem item no BM") |
| DF-33 (CH) | 17 UN · 0,71 m; um elemento físico, duas atividades (CH e Zona01) |
| Enquadramento BA | 5.647 CONTRATUAL CONFIRMADO · 531 CONTRATUAL — VALIDAR · 361 APROVAR |
| Avisos | 6.789 problemas e 6.789 sugestões de origem (P1/P2), contados por item após separar os blocos `\|` |
| Reimportação real | SEM_ALTERACOES |
| Migração de um banco v1 com movimentos (feita em cópia) | 5 movimentos, 4 fotos, check-in, OK, esteira, NF e 27 lançamentos preservados e remapeados; tabelas v1 mantidas; backup verificado. Em 16/10: repetida em teste automático sobre a base real (romaneio, custódia, aplicado, sobra, foto, execução e medição fechada congelada). |
| Reimportação real — conteúdo | SHA-256 do conteúdo de todas as tabelas igual antes/depois, exceto o registro da própria importação |
| Nomes TR001 ↔ TR002 trocados numa cópia da 06.1 real | Check-in e foto ficam no TR-00001 (mesmo handle e pontas); pendência TRECHO_RENOMEADO |
| Testes automáticos | **90 OK** (16/10): 26 de regras, 50 de importação/backup/migração com planilhas sintéticas (inclui uma regressão por achado A01–A12), 8 do piloto Zona01 e 6 de verificações sobre a base real em cópias |
| Navegador (Chromium, HTML REV02 real) | Medição TESTE, apontamento, fotos, avisos e decisões do DF-33, OK interno, exportação `TESTE_MEDICAO_01…`, camada do mapa pintando o TR001. Zero erros de console. |

## Como executar na sua máquina (depois da aprovação)

```
cd morro-da-cruz
pip install openpyxl
# planilhas oficiais em planilhas/ (nomes em config/fontes.json) e o HTML REV02 em mapa/
python importar.py                 # 1) SIMULAÇÃO: não altera nada; leia o relatório
                                   #    (código 2 = REPROVADA: veja os bloqueios e o relatório em dados/relatorios/)
python importar.py --aplicar       # 2) trava + backup verificado e completo + migração/importação numa transação
python backup.py verificar dados/backups/<pasta>     # 3) conferir o backup a qualquer momento
python server.py                   # 4) http://127.0.0.1:8765
```

**Antes de aplicar:**
- Pare o servidor. Importação e restauração recusam rodar com ele ligado, por limitação de concorrência desta versão.
- Rode a simulação e confira cada valor de `CTRL-01` na fonte.
- Preencha você mesmo, em `config/controles.json`, o bloco `"aprovacao": {"status": "APROVADO", "por": "<seu nome>", "em": "AAAA-MM-DD"}`. Hoje ele está `PENDENTE`, e a aplicação é recusada (`CONTROLE_SEM_APROVACAO`) até lá. O sistema nunca preenche a aprovação.
- Confirme os vínculos da DEC-0001 em `config/decisoes.json`.

**Para desfazer:** pare o servidor e rode `python backup.py restaurar dados/backups/<pasta>`. O estado atual vira antes um backup completo e verificado em `dados/backups/`.

**Nova revisão de planilha:** a simulação reprova com `SEM_CONTROLES_APROVADOS` e traz um `modelo_controles`; confira cada valor na fonte e acrescente o conjunto em `config/controles.json`. Se a revisão alterar trecho/elemento com histórico, registre o de-para em `config/conciliacoes.json`.

O relatório completo de cada execução fica em `dados/relatorios/importacao_*.json`.

## O que **não** foi feito (fica para as próximas etapas)

- **Regras financeiras:** veja `docs/MATRIZ_REGIMES_FATURAMENTO.md`, que precisa da sua aprovação.
- **Rateio de escavação** entre 5.4.11/5.4.13 e 5.4.15/5.4.14: continua como estimativa sinalizada.
- **Soldas ⌈L/6⌉, intervalos por estaca, reserva de estoque, foto original com hash** (etapas 3 e 4).
- **Exportação no modelo oficial** (`01ª MC`), **usuários e perfis**, acesso pelo celular (etapa 6).
