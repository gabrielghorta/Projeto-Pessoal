# Chuva, memória de cálculo e relatório mensal em Word

06/11/2026 · esquema v26 · D-215 a D-218. A D-214 é do PR #34, sobre continuidade dos mapas.

## Interferências e chuva

**Lançamento do dia › Interferências e chuva** reúne os relatos. Não existe mais uma página separada para marcar
Sol. Sem informação de chuva, o diário mostra **Sem chuva (padrão)**, identificando a premissa; não cria uma observação
de clima no banco. A nota de serviço, o apontamento e a correção de data não exigem preencher clima.

Para chuva, escolha categoria Chuva, equipe, dia, manhã/tarde/dia todo e o efeito no serviço. Trecho e descrição são
opcionais nesse caso. Para os demais impedimentos e não conformidades continuam necessários o alvo e a descrição.
O encarregado só registra para sua equipe. Resolver a interferência conserva o registro de chuva daquele dia.
Os registros explícitos antigos de clima permanecem; relatos novos de chuva prevalecem na leitura do diário.
O endereço antigo `#campo/clima` abre Interferências e chuva. APIs antigas continuam compatíveis.

O botão **Choveu** abre só dia, equipe, turno, efeito e observação opcional. A opção **Todas as equipes com check-in
no dia** usa check-ins abertos ou encerrados e cria um registro por equipe, numa transação. Sem check-in, pede para
escolher uma equipe. Quem tem login restrito à equipe só registra a própria; a mesma trava vale no servidor.
**Relatar outra interferência** volta ao formulário geral. Ambos usam `/api/ocorrencia` e a permissão `campo`.

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

Podem existir até 30 partes, com identificação e repetições. Cada parte aceita até 30 lados individuais, com nome
opcional, **ou** uma soma em um campo. Preencher lados e soma juntos é recusado, sem somar os dois. Os campos aceitam
números positivos e somas simples; não executam expressões. A quantidade é calculada no formulário e novamente no servidor. Uma quantidade
que não bate com as medidas é recusada. Área/volume novos não entram somente com o total, sem medidas.

As partes são guardadas em `apropriacoes.calculo_json` versão 2, com lados ou texto da soma, dimensões, repetições e
resultado. A versão 1 continua legível, sem inventar lados. Registros sem medidas estruturadas conservam o total e
a memória existente; não se deduzem dimensões antigas. Não há mudança de esquema nesta revisão.

Na **MC**, cada parte ocupa uma linha. Em m², T recebe o perímetro, U a altura/largura e W calcula T × U. Com
repetições, K recebe as vezes e W usa T × U × K. Em m³, I/J recebem comprimento/largura, T = I × J, U a espessura e
W = T × U. Em m, T recebe comprimento e U as vezes; uma folha mista com trechos conserva os títulos de estacas.
Outras unidades recebem a quantidade sem fabricar dimensões. Os cabeçalhos acompanham a unidade.

A referência contém a soma inteira ou os lados; quando longa, abrevia a identificação ou remete à apropriação,
sem cortar a conta. Parcela fora da medição aparece em uma linha negativa explícita, mantendo o levantamento de
origem. Diferença de arredondamento dimensional aparece identificada, para a soma da folha bater com o medido.
Registros antigos sem dimensões ficam só no total, sem virar altura/largura fictícia. A justificativa da folha prevalece; sem ela, usa a da apropriação ou um resumo automático das medidas.

## RM em Word

**Relatórios › Relatório mensal (Word .docx)** baixa um documento editável, com parágrafos e tabelas nativos.
Usa os mesmos totais do relatório mensal existente. O conteúdo segue os capítulos do Lago Sul e o visual REV01;
as referências com dados pessoais ficam somente fora do repositório. A capa anterior é preservada, com datas em
dd/mm/aaaa. Cabeçalho de quatro colunas: logo, contrato, número do RM e período. Arial Narrow, títulos vinho com
Heading 1/2/3, tabelas nativas com cabeçalhos repetidos, linhas indivisíveis e moldura dupla. Seções largas usam paisagem.

As semanas trazem frente/prancha/DN, croqui com legenda fora da rede, intervalos convertidos em estacas de 20 m e
checklists dos serviços registrados (`config/rm_checklists.json`). Os textos marcados `revisar` aguardam a engenharia.
Sem data para uma ligação, ela não aparece como serviço de uma semana. O canteiro usa o polígono de `mapa_contexto`
e a composição pelas apropriações do grupo Canteiro, inclusive quando o local opcional não foi preenchido.

Tubos mostram projeto, romaneio, empréstimo, retirada líquida, aplicação, cadastro, estoque virtual e percentual.
Locação e execução medidas conciliam com os lançamentos do BM; as semanas mantêm a produção física registrada.
Efetivo: direto/terceirizado pela empresa da equipe, sem inventar presença, falta ou atestado. Fotos: seis por página.
Mapas, gráficos e fotos são imagens; textos e tabelas continuam editáveis. Legendas são sequenciais por tipo.

O sumário usa TOC/PAGEREF e os títulos nativos. O Word atualiza os campos e as páginas; depois de editar, use
**Atualizar Sumário** para repaginar. O servidor não inventa números de página nem depende de um aplicativo de escritório.
O pacote OOXML usa namespaces padrão em `[Content_Types].xml` e `.rels`, e propriedades na ordem do esquema.
Mantém a marca TESTE – NÃO OFICIAL e as pendências sem fonte. O PDF anterior continua disponível pela API com
`formato=pdf`. O servidor gera Word sem depender do Microsoft Word ou LibreOffice: só stdlib e Pillow já existente.

Código: `memoria_calculo.py`, `apropriacao.py`, `servicos.py`, `diario.py`, `pacote_medicao.py`,
`docx_simples.py`, `relatorio_mensal.py`, `relatorio_word.py` e telas existentes. Testes em
`tests/test_campo_memoria_word.py` e `tests/test_revisao_pr35.py`.
