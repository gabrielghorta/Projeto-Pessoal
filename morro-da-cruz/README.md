# Sistema de Gestão e Mapa Iluminado — Morro da Cruz (Ankara Engenharia)

Aplicação web **privada e local** para a obra *Implantação de Redes de Distribuição no Morro da Cruz,
São Sebastião/DF* — Contrato Caesb × Ankara nº 10239/2026, LC 014/2026.

Python (biblioteca padrão + `openpyxl`), banco SQLite e interface HTML/JS sem dependências externas.
Roda inteiro no computador da obra: nada sai para a internet.

## Como rodar (Windows)

1. Instale o Python 3.11 ou superior e rode: `pip install openpyxl`
2. Copie as planilhas oficiais para `planilhas/` e as plantas REV02 para `mapa/`. Os nomes exatos estão em
   `config/fontes.json`, e as duas pastas têm um `LEIA-ME.md`.
3. Faça a carga inicial, que confere os totais da auditoria:
   ```
   python seed.py
   ```
4. Suba o sistema e abra **http://127.0.0.1:8765**:
   ```
   python server.py
   ```
5. Para rodar os testes: `python -m unittest discover -s tests -v`

## Carga e auditoria (`seed.py`)

| Fonte | Conteúdo carregado | Conferência |
|---|---|---|
| 06.1 REDES REV01 (aba `REDE`) | trechos, perfil de vala, quantidades AL:BK, nós das pontas, código BM | 1.436 trechos · 110.686,03 m |
| EVIDÊNCIAS REV08 | elementos (UTM → lat/lon), conjuntos por equipe, linhas de peças, coluna TRECHO | 1.191 elementos (1.059 nós + 132 caixas) · 1.242 conjuntos · 6.539 linhas |
| 06.2 CONEXÕES REV08 (.xlsm) | quantidade, unidade, código BM e avisos AA/AB de cada peça (casando pela linha) | — |
| BM REV04 IDENTIFICAÇÃO | BM Juntada (B:J) e Vertical (F:N), BDI, K | 347 / 432 itens · P0 R$ 49.878.748,66 |
| 03.3.2 REAJUSTE | data-base 31/01/2025, 1º aniversário 31/01/2026, índice CEFR 3,29 % | — |

MV-11, VTF-12 e VTF-16 ficam na **bandeja "sem posição"**. O sistema nunca inventa coordenadas para eles.

## Regras implementadas

- **N02:** M e UN nunca entram no mesmo contador. Por exemplo, DF-33 aparece como `17 UN · 0,71 m`. Peça sem quantidade não vira zero: fica sinalizada à parte.
- **E06:** perfil `A CONFIRMAR`, incompleto ou com volume negativo **bloqueia** o cálculo. Não há `IFERROR → 0`.
- **Quantidades previstas:** vêm da própria 06.1, rateadas por metro executado. Nº de soldas = ⌈L / 6 m⌉. Ao apontar, o encarregado clica em **[✅ OK, Confirmar Previsto]** ou edita as quantidades.
- **Clima:** obrigatório por turno (manhã e tarde) antes do apontamento.
- **Fotos:** o trecho exige 3 fotos (sinalização, execução e concluído). O nó ou caixa exige 2 e herda a sinalização do trecho ligado. Se nenhum trecho ligado tiver foto de sinalização, o nó também exige as 3. O carimbo com contrato, ID, data/hora e GPS é gravado na própria imagem.
- **Almoxarifado:**
  - Tubo PEAD Caesb (romaneio): movimenta o estoque e vale R$ 0,00 no BM.
  - Material Ankara: NF entra em quarentena e é aceita com laudo. Com faturamento por etapas, paga **80 % na entrega** (gaveta 2) e **20 % no OK Fiscal** do trecho ou nó onde foi aplicado. Sem etapas, paga 100 % na aplicação.
  - Consumo diário: entrada por caminhão ou nota e baixa teórica.
- **Check-in e check-out:** o check-in passa o material para a custódia da equipe e acende o pin **📍 Equipe Zona XX Aqui Hoje** no mapa. O check-out fecha a custódia em aplicado, sobra e perda; a perda exige motivo.
- **[✓] OK Fiscalização:** só é liberado com o trecho 100 % reaterrado e as fotos completas. Dispara dois eventos:
  1. Lança os serviços na medição do mês (gaveta 1).
  2. Envia o trecho para a esteira de cadastro.

  A recomposição de calçada ou asfalto tem checkbox próprio (gaveta 4).
- **Esteira GDOC:** 1 → 2 → 3 → 4 → (5A negado → reenvio, que cria a Rev. N) → 6 aprovado. A aprovação lança a extensão no item **2.2_5.2.1** (gaveta 3).
- **Medição:**
  - Valor = preço × (1 + BDI da classe) × (1 − K), o mesmo cálculo do rodapé do BM.
  - O valor é limitado ao teto de cada subgrupo do BM Vertical.
  - Reajuste de 3,29 % nas medições de out, nov e dez/2026. A partir de jan/2027 (período que cruza o aniversário) o reajuste fica **pendente**, não repete 3,29 %.
- **Exportação .xlsx:** RESUMO (as 4 gavetas), BM VERTICAL, BM JUNTADA, REAJUSTE, MC REDE e MC CANTEIRO.

## Mapa Iluminado

O servidor abre `mapa/PLANTAS_..._REV02_EQUIPES.html` **sem alterá-lo** e injeta `web/mapa_iluminado.js`.
A camada lê o mesmo `DADOS` da REV02 e faz o seguinte:

- alterna entre **Modo Projeto** (as cores de DE da REV02) e **Modo Mapa Iluminado**:
  - cinza pontilhado: não executado;
  - laranja tracejado: em execução;
  - vermelho: concluído no mês, aguardando OK;
  - verde: OK Fiscalização;
  - amarelo: medido em medição anterior;
- desenha os pins das equipes;
- envia o trecho ou nó clicado para o painel de Fiscalização.

## Pendências (dependem de dados ou de decisão da engenharia)

1. **06.2 REV08 (.xlsm):** sem ela, as 6.539 peças ficam sem quantidade. O apontamento de nós e caixas fica bloqueado com aviso.
2. **Plantas REV02 (.html):** sem o arquivo, a aba 1 funciona pela busca, mas sem a planta.
3. **Vínculos de BM a confirmar (`config/servicos_rede.json`):**
   - os serviços são lastro, aterro de areia, reaterro, carga, escoramento, transporte, sondagem, tapume, sinalização, passadiços, solda e recomposição;
   - eles entram na medição com valor zero e a marca **SEM ITEM BM** até alguém confirmar o item.
4. **Reajuste:** frações elegíveis de material e serviço e o índice de 31/01/2027 (aba REAJUSTE da 03.3.2).
5. **Próximas entregas:**
   - PDF da prancha do Mapa Iluminado da medição;
   - Relatório Mensal com caderno fotográfico (6 fotos por folha);
   - layout da MC no padrão da planilha 04.1.
