# Chuva, memória de cálculo e relatório mensal em Word

05/11/2026 · esquema v26 · D-215 a D-217. A D-214 é do PR #34, sobre continuidade dos mapas.

## Interferências e chuva

**Lançamento do dia › Interferências e chuva** reúne os relatos. Não existe mais uma página separada para marcar
Sol. Sem informação de chuva, o diário mostra **Sem chuva (padrão)**, identificando a premissa; não cria uma observação
de clima no banco. A nota de serviço, o apontamento e a correção de data não exigem preencher clima.

Para chuva, escolha categoria Chuva, equipe, dia, manhã/tarde/dia todo e o efeito no serviço. Trecho e descrição são
opcionais nesse caso. Para os demais impedimentos e não conformidades continuam necessários o alvo e a descrição.
O encarregado só registra para sua equipe. Resolver a interferência conserva o registro de chuva daquele dia.
Os registros explícitos antigos de clima permanecem; relatos novos de chuva prevalecem na leitura do diário.
O endereço antigo `#campo/clima` abre Interferências e chuva. APIs antigas continuam compatíveis.

## Apropriação com medidas

Obrigatórios: item do orçamento, data já ocorrida e dados da quantidade. Local, executor, descrição complementar,
justificativa e evidências são opcionais. Se informar um executor, os dados necessários para identificá-lo continuam
validados. Anexos enviados continuam sujeitos a validação de formato/tamanho. Aprovação de item novo, teto do BM,
regimes de material e medição fechada mantêm as regras anteriores. Motivo de estorno/correção continua obrigatório.

| Unidade | Dados na origem | Exemplo de conta |
|---|---|---|
| m | medida/comprimento | 12 + 8 = 20 m |
| m² | comprimento/perímetro × largura/altura | (80 + 50 + 40 + 20 + 45) × 2 = 470 m² |
| m³ | comprimento × largura × profundidade | 10 × 2 × 0,15 = 3 m³ |
| demais | quantidade na unidade do item | 2 UN; complemento livre opcional |

Podem existir várias parcelas, com identificação e repetições. Os campos aceitam números positivos e somas simples
de lados; não executam expressões. A quantidade é calculada no formulário e novamente no servidor. Uma quantidade
que não bate com as medidas é recusada. Área/volume novos não entram somente com o total, sem medidas.

As parcelas são guardadas em `apropriacoes.calculo_json`; a memória legível acompanha a apropriação e os lançamentos
da aba MC do BM. Textos longos ocupam linhas de continuação; só uma linha leva a quantidade, sem duplicar a soma.
Se apenas parte da apropriação entrou na medição, a memória identifica o total de origem e a parcela medida.
A migração conserva a memória antiga e deixa suas dimensões estruturadas vazias; não inventa levantamentos antigos.

## RM em Word

**Relatórios › Relatório mensal (Word .docx)** baixa um documento editável, com parágrafos e tabelas nativos.
Usa os mesmos dados, capítulos e totais do relatório mensal existente. Mapas, gráficos e fotos são imagens inseridas
no documento; títulos e sumário são texto editável. Tabelas têm cabeçalhos repetidos e seções em retrato/paisagem.
Mantém a marca TESTE – NÃO OFICIAL e as pendências sem fonte. O PDF anterior continua disponível pela API com
`formato=pdf`. O servidor gera Word sem depender do Microsoft Word ou LibreOffice: só stdlib e Pillow já existente.

Código: `memoria_calculo.py`, `apropriacao.py`, `servicos.py`, `diario.py`, `pacote_medicao.py`,
`docx_simples.py`, `relatorio_mensal.py` e telas existentes. Testes novos em `tests/test_campo_memoria_word.py`.
