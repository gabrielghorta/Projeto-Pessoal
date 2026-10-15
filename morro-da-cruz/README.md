# Sistema de Gestão e Mapa Iluminado — Morro da Cruz (Ankara Engenharia)

Aplicação web **privada e local** da obra *Implantação de Redes de Distribuição no Morro da Cruz,
São Sebastião/DF*, Contrato Caesb × Ankara nº 10239/2026, LC 014/2026.

- Tecnologia: Python (biblioteca padrão + `openpyxl`), banco SQLite e interface HTML/JS sem dependências externas.
- Roda só no computador da obra (`127.0.0.1`), sem autenticação. Ainda não serve para acesso pelo celular.
- **Estado atual: piloto de TESTE.**
  - Medição oficial bloqueada.
  - Regras financeiras de material pendentes: veja `docs/MATRIZ_REGIMES_FATURAMENTO.md`.
  - Detalhes das etapas 0 e 1: `docs/ETAPAS_0_1_APROVACAO.md`.

## Como rodar (Windows)

1. Instale o Python 3.11+ e rode `pip install openpyxl`.
2. Coloque as planilhas oficiais em `planilhas/` e o HTML REV02 em `mapa/`. Os nomes exatos estão em `config/fontes.json`.
3. Faça a importação. Ela nunca apaga o banco nem movimentos.
   ```
   python importar.py              # simulação: mostra o relatório, não altera nada
   python importar.py --aplicar    # backup verificado + importação numa transação
   ```
4. Suba o sistema e abra **http://127.0.0.1:8765**:
   ```
   python server.py
   ```
5. Backup a qualquer momento: `python backup.py criar | verificar <pasta> | restaurar <pasta>`.
6. Testes: `python -m unittest discover -s tests -v`. Os 8 testes do piloto Zona01 exigem as planilhas reais em `planilhas/`.

## Importação (`importar.py` / `importacao.py`)

| Fonte | O que entra | Conferência |
|---|---|---|
| 06.1 REDES REV01, aba `REDE` | Trechos: perfil de vala, quantidades AL:BK, pontas, handle, código BM | 1.436 trechos · 110.686,03 m |
| 06.2 CONEXÕES REV08, aba `CONEXÕES` (colunas localizadas pelo cabeçalho) | Elementos físicos (por handle CAD), atividades por frente, itens com quantidade; unidade pelo item da Juntada; BA/BB/AW/AG/AH; avisos AA/AB | 1.191 elementos · 1.242 atividades · 6.539 itens |
| EVIDÊNCIAS REV08 | Conferência do agrupamento; zona; status de posição; ID da auditoria | 1.191 de 1.191 grupos iguais |
| BM REV04 IDENTIFICAÇÃO | Juntada e Vertical; BDI, K e totais do rodapé | 347 / 432 itens; P0 recalculado = célula T556 |
| 03.3.2 REV03 REAJUSTE | Data-base, aniversário, índice CEFR | — |

**Garantias da importação:**
- **Identidade estável:** TR-, EL-, AT- e IP- casados por chave natural, nunca pelo nº da linha.
- **Proveniência:** cada registro guarda arquivo, SHA-256, aba, linha e células lidas.
- **Histórico:** os nomes antigos ficam registrados, e cada diferença entre revisões também.
- **Nada é apagado:** o que sai de uma revisão fica com `vigente = 0`.
- **Pendente não vira chute:** quantidade e unidade sem fonte ficam **pendentes** (361 linhas "APROVAR — sem item no BM").
- **Decisões posteriores** (`config/decisoes.json`) nunca são alteradas pela reimportação.
- **Divergência registrada:** o valor do contrato (R$ 49.878.748,56, cláusula 3.1) e o P0 do BM (R$ 49.878.748,6575869) aparecem lado a lado, sem ajuste.

## Regras em vigor

- **N02:** unidades nunca se misturam e UN ≠ PÇ. DF-33 (CH) aparece como `17 UN · 0,71 m`.
- **E06:** perfil de vala `A CONFIRMAR`, incompleto ou com volume negativo bloqueia o cálculo. Trecho MND não exige perfil de vala.
- **BDI e K na ordem do BM:**
  - medição com `ROUND(q×p;2)` por item;
  - BDI por classe;
  - total = (Σ + BDI) × (1 + K), com K = −1 + (1 − 14,04 %) (contrato 5.2).
- **Lançamentos:**
  - `PROPOSTO` quando há item de BM com fonte;
  - `PENDENTE` (fora do valor) sem item ou regra; não é R$ 0 contratual;
  - **material nunca recebe regime automático:** sem 80/20 e sem 100 % na aplicação;
  - **MND** sem substituição automática de item.
- **OK interno:** o "[✓] OK" é da Ankara e só gera proposta numa medição de **TESTE**. Também envia o trecho para a esteira GDOC.
- **Fotos e clima:** controles operacionais propostos (3 fotos por trecho, 2 por nó com sinalização herdada; clima por turno).
- **Pin do mapa:** mostra a programação do check-in, não a posição atual da equipe.

## Mapa

O servidor abre `mapa/PLANTAS_..._REV02_EQUIPES.html` **sem alterá-lo** e injeta `web/mapa_iluminado.js`. A camada lê o mesmo `DADOS` da REV02 e faz o seguinte:
- alterna Modo Projeto (cores de DE) e Mapa Iluminado (andamento);
- desenha os pins de programação;
- envia a seleção para o painel de Fiscalização.

## Pendências

- **Faturamento de material:** matriz de regimes aguardando aprovação.
- **Itens de BM a definir:** 14 serviços da 06.1, o MND e o critério da escavação em dois itens.
- **Reajuste:** frações elegíveis e o pedido da contratada.
- **Próximas etapas:**
  - soldas, intervalos por estaca, reserva de estoque e foto original com hash;
  - exportação no modelo oficial (`01ª MC`);
  - usuários, perfis e acesso de campo.
