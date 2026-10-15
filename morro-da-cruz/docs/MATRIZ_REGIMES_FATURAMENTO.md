# Matriz de regimes, marcos e fontes — para aprovação antes da etapa financeira

CT 10239/2026 · versão de 15/10/2026 · **nada desta matriz está aplicado no sistema**.

Hoje o sistema funciona assim:
- Lançamento de material fica `PENDENTE` com o motivo "regime de faturamento pendente".
- Não existe 80/20 global nem 100 % na aplicação.
- Trecho MND não recebe item automaticamente.
- Só existe medição de **TESTE**.

**Como ler a coluna Situação:**

| Situação | Significado |
|---|---|
| **DOC** | Exigência documental conferida na fonte citada |
| **DEC** | Decisão sua, já registrada |
| **PROP** | Proposta, ainda não validada |
| **PEND** | Falta fonte ou decisão |

## 1. Fornecimento de material

| # | Categoria | Itens desta obra (exemplos) | Regime e marcos | Condição de cada marco | Fonte conferida | Situação | Sistema hoje |
|---|---|---|---|---|---|---|---|
| 1 | Tubo PEAD da rede principal, **fornecido pela Caesb** | Tubos PEAD da rede: 110.686,03 m (projeto 06.1). Não estão no BM. | Não há faturamento de fornecimento pela Ankara. A Ankara responde pela guarda, conservação e reposição em caso de extravio ou dano. | Romaneio na retirada; custódia; aplicação; perda com motivo. | SL0327 §6, p. 5 | DOC | Controle de custódia (romaneio, custódia, aplicação). Valor R$ 0,00 só para o fornecimento; os serviços são medidos. |
| 2 | Tubos para redes **fornecidos pela contratada** | Pouco objeto nesta obra, porque a rede PEAD é da Caesb. Candidatos: tubos PEAD de canteiro e hidromecânico (1.1_1.14.77, 5.1_1.14.77)? | **Opcional** ("poderá"), em duas etapas: **80 %** após recebimento no canteiro e inspeção; **20 %** após completa implantação. | 80 %: recebimento no canteiro **e** procedimentos de inspeção/avaliação técnica cumpridos. 20 %: assentamento **+** reaterro **+** cadastramento **+** recuperação de benfeitorias. | SL0327 §7.1, pp. 5–6 | DOC (regra); PEND (quais itens se enquadram) | Não aplicado. |
| 3 | **Equipamentos eletromecânicos** | Exemplos do SL0327: bombas, agitadores, sopradores, compressores, quadros, transformadores. Medidores de vazão eletromagnéticos (5.1_3.1.x) e VRPs **só se** a fiscalização os enquadrar. | **20 / 15 / 40 / 15 / 10 %**, a critério da fiscalização, com justificativa formal e anuência do agente financiador, se houver. | 20 %: aprovação pela fiscalização + contrato de fornecimento (sujeito à aprovação da Caesb). 15 %: teste em fábrica com relatório. 40 %: entrega no canteiro + relatório de armazenamento. 15 %: instalação em condição de comissionar. 10 %: comissionamento + relatório + documentação. Sem inspeção em fábrica, os 15 % passam para a entrega. | SL0327 §7.2, p. 6 | DOC (regra); PEND (enquadramento) | Não aplicado. |
| 4 | **Tubos e peças de aço / ferro fundido** | Válvulas, flanges, tocos, tubos FoFo, reduções e luvas de correr FoFo do grupo 5.1 (hidromecânico) e das caixas. | **80 / 10 / 10 %** sobre o preço unitário do material. | 80 %: recebimento pela Caesb após inspeção. 10 %: implantação completa + verificação das soldas (aço, ultrassom) + reaterro + aprovação da fiscalização. 10 %: testes de estanqueidade executados. Todas as condições sujeitas à anuência do agente financiador. | SL0327 §7.3, pp. 6–7 | DOC (regra); PEND (lista de itens) | Não aplicado. |
| 5 | **Conexões PEAD** compradas pela Ankara (luvas, tês, colarinhos, reduções) | Grupo 1.14.x da 06.2: maioria das 6.178 linhas com código BM. | **Sem regime de etapas documentado.** Não herdam a regra do tubo (§7.1) só por serem PEAD. | — | Nenhuma até agora | PEND | Lançamento fica PENDENTE. |
| 6 | **Regime normal** (material sem faturamento por etapas) | Todos os materiais fora dos regimes acima. | Contrato 5.2: "custos unitários sem BDI × K x BDI × quantitativos de serviço/**material efetivamente executado/fornecido**". O momento (entrega? aplicação?) depende da cláusula 2.16 do Edital, citada no contrato 5.1 e ainda não lida. | — | Contrato 5.1–5.2, p. 4 | PEND | Não aplicado. Os 100 % na aplicação foram retirados. |
| 7 | Seleção de compras ou lotes para faturamento por etapas | Ex.: `Compra01_ConexoesPEAD_EmpresaX`, se o regime existir para a categoria. | Escolha **sua** por item ou lote, no início da obra, para apoiar o caixa. Não é automática e não substitui as condições nem as aprovações. | Registro da decisão: lote, categoria, responsável, data, evidência da anuência quando exigida. | Decisão sua (15/10) | DEC | Só registra a intenção na NF; não gera lançamento. |

## 2. Serviços e medições

| # | Assunto | Regra | Fonte | Situação | Sistema hoje |
|---|---|---|---|---|---|
| 8 | Valor de cada medição | Preço sem BDI × (1 + BDI da classe) × (1 + K), com K = −1 + (1 − 14,04 %). O valor é arredondado por item (`ROUND(q×p;2)`), o BDI é aplicado por classe e o K no total. | Contrato 5.2 e 5.3, p. 4; células do BM (`W`, `T548:T556`) | DOC (fórmula esclarecida) | Implementado e conferido contra as células (P0 49.878.748,6575869). |
| 9 | Momento da medição de serviço | Medição mensal das quantidades executadas e aprovadas pela fiscalização. | Contrato 5.3, p. 4 | DOC | O OK interno só gera **proposta** em medição de TESTE; não é aprovação Caesb. |
| 10 | Serviços da 06.1 sem item comprovado | Lastro, aterro de areia, reaterro, carga (inclusive de rocha), escoramento (pontalete e descontínuo), transporte, sondagem, tapume, placa e sinalização noturna, passadiços (veículos e pedestres), solda e recomposição. | `config/servicos_rede.json` | PEND | Ficam PENDENTE, fora do valor. |
| 11 | Escavação mecanizada em dois itens (5.4.11 + 5.4.13; 5.4.15 + 5.4.14) | A APOIO_REDES liga cada categoria a dois itens **sem critério de divisão**. Hoje o volume é dividido pela proporção das quantidades contratuais e a linha leva a observação "estimativa". | 06.1 APOIO_REDES AA9/AA10 | PEND | PROPOSTO com observação de estimativa. **Precisa de regra antes de qualquer medição oficial.** |
| 12 | MND (4 trechos, 291,26 m) | A 06.1 traz 5.8.44 (assentamento em vala) nesses trechos. O BM tem perfuração direcional 5.16.x por DE; restam 6.978,95 m de MND no BM sem localização. | 06.1 col. AC; BM 2.2_5.16.x | PEND | Assentamento MND fica PENDENTE; sem substituição automática. |
| 13 | Cadastro de canalizações (2.2_5.2.1, M) | O MVP mede na aprovação do GDOC, uma única vez por trecho. Falta conferir o critério contratual e se o memorando ESET é exigido. | Item do BM; procedimento GDOC não conferido | PROP | Lança PROPOSTO só na etapa 6 da esteira (medição de TESTE). |
| 14 | Recomposição de calçada e asfalto | Itens candidatos: 5.9.3 (passeio), 5.9.5 (concreto asfáltico) e outros 5.9.x. | BM 2.2_5.9.x | PEND | PENDENTE. |
| 15 | Teto por subgrupo do BM Vertical | O valor medido acumulado por subgrupo é limitado ao valor P0 do subgrupo. | Estrutura do BM | PROP (controle interno) | Implementado só como alerta na medição de TESTE. |

## 3. Reajuste

| # | Assunto | Regra | Fonte | Situação |
|---|---|---|---|---|
| 16 | Data-base e 1º reajuste | Preços fixos por 1 ano a partir de 31/01/2025. Depois disso, reajuste pelo ICC-Brasília-DI, **desde que haja pedido da contratada**. | Contrato 6.1–6.2, p. 6 | DOC |
| 17 | Percentual | Até 3,29 % (CEFR), base 31/01/2025, 1º aniversário 31/01/2026. | Despacho 322/2026-CEFR (GDOC 2998208); aba REAJUSTE | DOC (ainda falta a memória SISFINR) |
| 18 | Parcela elegível | A REV04 pede frações elegíveis separadas para material e serviço; a REV03 usa a fração posterior ao aniversário. | BM REV03 × REV04, aba REAJUSTE (E24:H24) | PEND (divergência entre revisões) |
| 19 | Reajustes seguintes | O intervalo conta a partir dos **efeitos financeiros do último reajuste**. Jan/2027 em diante fica pendente. | Contrato 6.4, p. 6 | DOC; sistema bloqueia |

## 4. Estados financeiros (proposta de modelo para a etapa 2)

Conferido pela Ankara → pronto para apresentar → aprovação da Caesb (com evidência: documento, data, responsável) → elegível pela regra da categoria → apresentado → aprovado → faturado → pago.

Um clique interno nunca cria aprovação da Caesb. Cada marco do item 4 (FoFo 80/10/10) e do item 3 (equipamentos) vira um lançamento próprio, com a evidência do marco.

## 5. Decisões que preciso de você para abrir a etapa financeira

1. **Itens 2, 3 e 4:** quais itens do BM entram em cada categoria? Posso gerar a lista candidata por descrição e material para você marcar.
2. **Itens 5 e 6:** qual é o regime das conexões PEAD e o regime normal de material? Preciso da cláusula 2.16 do Edital e do Termo de Referência.
3. **Item 11:** qual o critério de divisão entre 5.4.11 e 5.4.13, e entre 5.4.15 e 5.4.14 (por exemplo, método ou região)? Ou a medição será feita por item, com memória de campo?
4. **Item 12:** quais itens 5.16.x valem para os 4 trechos MND localizados?
5. **Item 18:** qual revisão vale para a parcela elegível do reajuste, e o pedido de reajuste já foi protocolado?
