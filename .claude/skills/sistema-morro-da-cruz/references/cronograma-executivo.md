# Cronograma físico executivo base (REV00, 29/10/2026)

Referência da skill `sistema-morro-da-cruz`. O cronograma foi feito para a reunião do responsável com a chefia em
29/10/2026, como "norte" da obra. Ele **não** está no web app: é um conjunto de scripts em
`morro-da-cruz/cronograma_executivo/`, que leem as planilhas oficiais e o REV02 e geram os arquivos.

Conteúdo: o que foi entregue · como gerar de novo · resultado dos dois cenários · regras do responsável · decisões
tomadas (e o porquê) · o que o responsável ainda deve validar · como o motor funciona · faturamento na planilha · o
arquivo do Project · como mudar uma premissa · próximos passos.

## O que foi entregue

Para cada cenário (A: prazo; B: 90 m/dia):

| Arquivo | O que é |
|---|---|
| `CRONOGRAMA_BASE_MORRO_DA_CRUZ_<A_PRAZO|B_90M_DIA>.xlsx` | Modelo do BM por equipe. Abas: PREMISSAS (parâmetros nas células amarelas, comparativo dos cenários, regras e premissas), BM POR EQUIPE (o vertical com um bloco por equipe, quantidade e valor por medição), BM CONSOLIDADO (a juntada somando as equipes, com BDI e K), CRONOGRAMA FF (modelo Caesb, por grupo), RESUMO POR EQUIPE (faturamento mensal, produção física, gráficos), PROGRAMAÇÃO (datas de cada trecho e caixa) |
| `….xml` | MS Project (MSPDI): Equipe › Zona · PB › os trechos com o nome da 06.1, cada caixa, cada montagem, as NS de topografia, os fechamentos; linha de base salva; 23/03/2028 como data limite. Cerca de 1.940 tarefas |
| `…_GANTT.pdf` | Gantt resumido por equipe e por zona, A3 deitado, para quem não tem o Project |
| `AVANCO_MORRO_DA_CRUZ_ANIMACAO.html` | O Mapa iluminado sendo preenchido dia a dia pelos dois cenários, com a régua do faturamento mensal. Abre com dois cliques, sem internet |

Também foi publicada uma versão da animação como artefato no claude.ai (privada, do responsável).

## Como gerar de novo

```bash
cd morro-da-cruz/cronograma_executivo
bash gerar_tudo.sh                 # saída em ./saida (fora do Git); ou: bash gerar_tudo.sh /outra/pasta
MPXJ=1 bash gerar_tudo.sh          # também regrava o XML pelo MPXJ (pip install mpxj; precisa de Java)
```

Leva cerca de 3 minutos (o cenário A procura a produtividade por bisseção, ~10 programações). Sem Node/Playwright, o
Gantt fica em HTML (imprima em A3 deitado). As fórmulas do xlsx são calculadas ao abrir no Excel; para conferir sem o
Excel, recalcule no LibreOffice (`soffice --headless --convert-to xlsx`) e procure `#REF!`, `#VALUE!` etc. A última
geração deu 0 erros de fórmula, e uma CPM independente sobre o XML deu 0 divergências.

**Abrir o XML no Project** (o Project vem configurado para recusar XML):
1. Arquivo › Opções › Central de Confiabilidade › Configurações da Central de Confiabilidade › **Formatos Herdados**.
2. Marque "Permitir carregamento de arquivos com formatos herdados ou não padrão" › OK.
3. Arquivo › Abrir, tipo **Formato XML (*.xml)**, "Como um novo projeto"; depois salve como .mpp.

Com dois cliques o Windows abre o XML no navegador; no celular não abre. O .mpp não é gerado por aqui.

## Resultado dos dois cenários

| | A – prazo contratual | B – ritmo médio |
|---|---|---|
| Produtividade das frentes de rede depois do reajuste | **95,0 m/dia** (a menor que fecha no prazo, de 0,5 em 0,5) | 90 m/dia (meio da faixa de 80 a 100) |
| Fim da obra | **23/03/2028** (folga 0) | 12/04/2028 (20 dias de atraso) |
| Fim da Subadutora | 13/07/2027 | 21/07/2027 |
| Fim da rede das zonas | 04/02/2028 | 24/02/2028 |
| Fim das caixas e do hidromecânico | 28/01/2028 | 17/02/2028 |
| Faturado até jan/2027, antes do reajuste (P0) | R$ 2,97 mi (5,96 %) | R$ 2,89 mi (5,80 %) |
| Mês de maior faturamento (P0) | 11ª medição, ago/27: R$ 4,78 mi | 10ª medição, jul/27: R$ 4,56 mi |
| Outubro/2026 (P0) | R$ 102,8 mil | R$ 102,8 mil |
| Total programado (P0) | R$ 49,79 mi | R$ 49,82 mi |
| Medições | 18 | 19 |

O total fica abaixo dos R$ 49,88 mi do contrato porque o aluguel de contêiner é contado da chegada de cada um (82 % do
item do BM, cerca de R$ 84 mil a menos).

## Regras do responsável (29/10/2026)

- 5 equipes de rede: 1 equipe Ankara (a da adutora) e 2 empreiteiros com 2 equipes cada nas zonas. As caixas ficam
  com uma 2ª equipe Ankara.
- **Pé alto até o reajuste de janeiro de 2027:** faturar pouco no começo. Até lá, só a equipe da adutora, em redes de
  160 mm (não classificadas como adutora), produzindo pouco.
- O 1º empreiteiro entra em janeiro de 2027 com 2 equipes; o 2º em abril de 2027.
- Produtividade de 80 a 100 m/dia por equipe, em dia sem interferência.
- Caixas hidráulicas a partir de março de 2027, com redes já feitas; hidromecânico a partir de julho de 2027 (peças de
  SP e do exterior, compradas com o que a obra fatura).
- Depois do reajuste, a equipe da adutora vai para onde for melhor; os empreiteiros não têm zonas definidas.
- As ligações prediais acompanham a rede.
- Segunda a sexta, 7h às 17h.
- Dois cenários: um que fecha no prazo e um que mantém a média.
- Em outubro/2026, só demarcação, alambrado metálico, portão e 2 contêineres (a primeira versão punha R$ 446 mil em
  outubro e foi corrigida).
- Entregáveis: Project e xlsx no modelo do BM, dividido por equipes.

## Decisões tomadas (e o porquê)

1. **Calendário:** 9 h/dia (07–12 e 13–17), sem os feriados nacionais e do DF (Carnaval, Sexta-feira Santa, Corpus
   Christi, 21/04, 30/11). Sem recesso de fim de ano e sem desconto por chuva.
2. **Cenários:** B usa 90 m/dia; A usa a menor produtividade que fecha em 23/03/2028 (95 m/dia, perto do teto, sem
   folga). A mesma produtividade para todos os diâmetros, do 63 ao 500.
3. **Equipe Adutora:** começa em 16/11/2026 (a NS de topografia fica de 03 a 13/11). No pé alto, até 29/01/2027, faz
   60 m/dia nos trechos de DE 160 das zonas que serão atacadas primeiro, para a rede principal estar pronta quando os
   empreiteiros chegarem. Em 01/02/2027 vai para a **Subadutora** (10,5 km): é o trabalho mais caro (fatura já com
   reajuste) e nenhuma zona entra em carga sem a Subadutora testada. Depois, apoia as zonas.
4. **Zonas e empreiteiros:** zonas da mais perto para a mais longe do canteiro (06, 01, 04, 03, 10, 07, 05, 02, 08,
   11, 09). Cada zona em blocos por prancha (zona × PB), da PB mais perto para a mais longe. Cada bloco vai para a
   primeira equipe livre, que prefere continuar na mesma zona. Dentro do bloco: primária, secundária, terciária, do
   maior diâmetro para o menor.
5. **Ligações (11.894):** só nos trechos de DE 63 (o BM usa tê de serviço 63 e tê de sela 63 × 20), pelo
   comprimento; a mesma frente, 5 dias úteis atrás da rede; não reduzem os metros por dia.
6. **Caixas (132):** a obra civil começa depois dos trechos que chegam na caixa. Dias de obra civil: DF 1, VTF 1,5,
   VM 2, VRP 3, MV 3, HID 0,5. Montagem hidromecânica como frente separada da Ankara 2, a partir de 01/07/2027: DF,
   VTF e HID 0,5; VM 1; VRP e MV 2. As conexões de PEAD dos nós (tês, curvas, luvas), que o BM põe no grupo
   hidromecânico, vão com a rede; só as peças das caixas (válvulas, VRP, macromedidor) esperam julho.
7. **Fechamento de cada zona:** teste hidrostático e desinfecção de 10 dias úteis depois do último trecho; entrada em
   carga (interligação) de 3 dias, só depois do teste da zona, do teste da Subadutora e da montagem das caixas da
   zona; cadastro técnico 30 dias corridos (22 úteis) depois de cada trecho; desmobilização de 10 dias no fim.
8. **Canteiro:** outubro só com o que foi feito; o resto das instalações de 03/11 a 18/12/2026. Contêineres: 2 em
   out/26, +4 em nov/26, +6 em jan/27, +6 em abr/27; o aluguel conta da chegada ao fim da obra. Custos mensais do
   canteiro (gerador, banheiro químico, consumo, infraestrutura da fiscalização) a partir de novembro.
9. **Faturamento:** material faturado na aplicação; valores em P0 (sem reajuste); administração local proporcional ao
   faturamento do mês (2,7624 %, TR 14.6).
10. **MND:** os R$ 1,2 mi de furo direcional do BM ficaram com os trechos do mesmo diâmetro (os 4 trechos MND da 06.1).

## O que o responsável ainda deve validar

1. 60 m/dia no pé alto (define os R$ 2,97 mi até janeiro).
2. A Subadutora logo depois do reajuste, antes de apoiar as zonas.
3. 95 m/dia no cenário A: sem dia perdido, não sobra margem. Na prática o prazo pede mais uma equipe ou aditivo.
4. A mesma produtividade em 500 mm e em 63 mm (o diâmetro grande deve render menos).
5. Os tempos das caixas e a montagem como frente separada.
6. O MND (se não houver furo, o valor sai do cronograma).
7. Sem recesso e sem chuva.

## Como o motor funciona (`motor.py`)

- **Tempo em minutos úteis** (540 por dia) sobre um calendário de dias úteis a partir da OS (`Calendario`: `w(data)`
  dá o minuto do início do dia; `inicio(w)`/`fim(w)` voltam para data e hora).
- `ler_dados()`: o `DADOS` do REV02 (trechos `t` com `R` = nome da 06.1, `de`, `tipo`, `loc` = zona, `pb`, `L` =
  metros, `ini`/`fim` = nós; elementos `els` com `tp`, `noms`, `tr`, `pecas`), a aba REDE da 06.1 e o vertical do BM.
- `base()`: marca a Subadutora (`tipo == 'Adutora'` ou DE ≥ 200), a distância ao canteiro, a ordem das zonas e as
  ligações estimadas por trecho.
- `programar(D, rede, p)`: (1) pé alto da ANK1 a 60 m/dia nos DE 160 das zonas até o reajuste; (2) a Subadutora em
  ordem de caminhamento (`ordem_subadutora`: da ponta de maior DE, andando pelo grafo, maior DE primeiro); (3) os
  blocos zona × PB para a primeira equipe livre entre E1A, E1B, E2C, E2D e ANK1; (4) caixas: obra civil em fila
  única da ANK2 pela data em que os trechos ficam prontos, montagem em fila a partir de jul/2027; (5) fechamento por
  zona e da Subadutora, desmobilização. Devolve o plano com as datas de cada trecho, bloco e caixa.
- `resolver_prazo()`: bisseção entre 40 e 200 m/dia até 0,5 m/dia.

## Faturamento na planilha (`faturamento.py`)

Cada item do BM vertical vai para as equipes e os meses pelo critério que o mede (o critério de cada item aparece na
planilha):
- **Rede (2.1, 2.2):** coluna da 06.1 que mede o item (`DRIVER_FIXO`: escavações por categoria, esgotamento, locação
  com NS, cadastro); item com diâmetro, pelos metros daquele DE (o 160 junta o 125); senão, a coluna da 06.1 cuja
  soma bate com a quantidade do BM (±6 %); senão, o volume de escavação. Locação: 2 semanas antes do trecho;
  cadastro: 30 dias depois.
- **Caixas (3.1, 3.2):** obra civil das 132 caixas, pelo porte de cada tipo, na ANK2.
- **Ligações (4.1, 4.2):** nos trechos de DE 63, 5 dias úteis atrás da rede; a interligação, em partes iguais pelas
  zonas e a Subadutora.
- **Hidromecânico (5.1, 5.2):** peças da 06.2 — a parte dos nós entra com o primeiro trecho do nó; a parte das caixas,
  na montagem. 5.2 (serviço) na montagem das VRP.
- **Canteiro (1.1, 1.2):** alambrado e portão em out/2026; demais instalações de 03/11 a 18/12; itens mensais iguais
  de nov/2026 ao fim; aluguel de contêiner pelos contêineres no canteiro; desinstalação metade na chegada, metade na
  desmobilização.
- **Administração local (6.2):** fórmula na planilha, proporcional ao faturamento do mês.

## O arquivo do Project (`gerar_project.py`)

MSPDI escrito à mão, com a ordem dos elementos conferida contra o `propOrder` do JAXB do MPXJ (o Project é rigoroso
com a ordem). `LinkLag` em décimos de minuto. Campos extras: Text1 Equipe, Text2 Zona/frente, Text3 Fase, Number1
Extensão (m), Number2 DE (mm), Number3 Ligações (est.). Calendário com os feriados. Linha de base igual ao plano.
No MPXJ, `Relation.getTargetTask()` é o predecessor (não confunda com `getSourceTask()`, que é a própria tarefa).

## Como mudar uma premissa

As constantes estão no topo de `motor.py` (datas de entrada das equipes em `EQUIPES`, `P_PE_ALTO`, `CAIXA_DIAS`,
`HIDRO_DIAS`, `LIG_ATRASO`, `TOPO_ANTES`, `CADASTRO_DEPOIS`, `TESTE_DIAS`, `INTERLIG_DIAS`, `DESMOB_DIAS`,
`CANT_*`, `CONTEINERES`, `TOPO_INICIO`, `INICIO_HIDRO`, `REAJUSTE`). O cenário B está em `gerar.py` (`'p': 90.0`).
Mude, rode `gerar_tudo.sh` e confira na aba PREMISSAS e no comparativo. Ao mudar uma premissa, atualize a aba
PREMISSAS (`gerar_xlsx.py`, função da aba) e este arquivo.

## Próximos passos

- Ligar o cronograma ao executado: % concluído por trecho (do web app) e linha de status na data de corte; título
  "REV nn - nª MEDIÇÃO", como no modelo do Lago Sul (`modelo-lago-sul.md`, seção do cronograma físico executivo).
- O web app já importa um XML do Project na tela Cronograma da obra (`cronograma.py`); o cronograma ligado ao
  executado é a D-150 (depois).
- Revisar com o responsável os 7 pontos a validar e gerar a REV01.
