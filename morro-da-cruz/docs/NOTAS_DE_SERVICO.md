# Notas de serviço (NS) por upload e diário de obra pela NS do dia

CT 10.239/2026 · 21/10/2026 · esquema v18 · decisões D-69 a D-74 e D-80 a D-85 (`docs/DECISOES_PENDENTES.md`)

Topografia, cadastro de campo e serviço de obra deixam de ser digitados: chegam como **nota de serviço em PDF**, no
formato da Caesb. O diário de obra também: a equipe envia **a NS do dia** (o que executou) e **o croqui**, e o sistema
lança sozinho o que é inequívoco. A 06.1 continua sendo a unidade do BM e da medição: tudo o que vem da NS é gravado
por linha da 06.1, convertendo pelo trecho físico (`topologia.py`, `docs/TOPOLOGIA_TRECHOS.md`).

| Tipo | Quem envia | Arquivos | O que gera |
|---|---|---|---|
| Topografia | Engenharia e Administração | PDF | liberação topográfica |
| Cadastro de campo | Engenharia e Administração | PDF | cadastro de campo, só sobre o assentado |
| Serviço de obra | Engenharia e Administração | PDF + croqui | o plano da zona (nada gravado nos trechos) |
| Do dia (execução) | o encarregado (só a equipe dele) ou, em nome da equipe, supervisor, engenharia e administração | PDF + croqui | assentado, reaterrado e escavado, informados |

Código: `ns_leitura.py` (leitor), `notas_servico.py` (casamento, registro e NS do dia), rotas `/api/ns*` em
`server.py`, telas em `web/notas.js`. Pesquisa que deu origem: `docs/ns/`.

---

## 1. Notas de topografia, cadastro e serviço (Execução · Notas de serviço)

### Como enviar

1. Escolha o tipo: **Topografia**, **Cadastro de campo** ou **Serviço de obra**.
2. Escolha o PDF da nota. O croqui é opcional (obrigatório no serviço de obra). A planilha `.xlsx` da nota é opcional:
   quando vem, é a leitura exata e o sistema confere se diz o mesmo que o PDF.
3. Se a nota não disser a zona e a PB, abra "A nota não diz a zona ou a PB" e escolha (aceita "8", "pb8" ou "PB08").
4. Toque em **Ler a nota**. Ler não grava nada. O PDF e o croqui abrem no próprio navegador.

As abas **Topografia** e **Cadastro de campo** têm o botão **Enviar nota de serviço** (abre esta tela com o tipo
escolhido) e a lista das notas do tipo. O formulário digitado antigo continua, recolhido em
**Sem nota de serviço (exceção)**. As filas e os indicadores das abas não mudaram.

### O que o sistema confere na leitura

- **Contrato:** só número e ano (`CT 10239/2026` = `10239/26`). Outro contrato é recusado: é o caso da NS 006 de
  exemplo (contrato 9702/2024, esgoto da ETE Paranoá).
- **Contas da nota:** profundidade = terreno − GI; cruzeta = visor + profundidade (aviso); estaca × 20 + fração =
  acumulada; acumulada = anterior + parcial; soma das parciais do grupo = linha do RESUMO; soma do RESUMO = TOTAL GERAL;
  folhas "x de y" completas; data válida e não futura.
- **PDF sem camada de texto** (escaneado) é recusado com mensagem clara. Não há leitura por imagem (OCR).
- **Duas leituras:** pypdf e, quando existe no servidor, o pdftotext. Se as duas (ou o PDF e a planilha) leem dados
  diferentes, a nota é recusada para conferência.

### Segmentos da nota × trechos da obra

Cada par de elementos consecutivos do grupo (nó, VRP, VM, MV, DF, VTF, HID) vira um segmento, casado com o trecho
físico que liga os dois, na zona e na PB da nota.

| Situação | Quando | O que fazer |
|---|---|---|
| automático | um trecho só, mesmo DE e método, diferença até max(0,10 m; 0,5 %) | nada (pode deixar de fora) |
| confirmar | mais de um trecho possível, ou diferença entre 0,5 % e 5 % | escolher o trecho e aceitar, ou deixar de fora com motivo |
| erro | diferença acima de 5 %, DE ou método diferente | só deixar de fora, com motivo |
| sem correspondência | nenhum trecho da zona liga os dois elementos | só deixar de fora, com motivo |

- **Cruzamento listado no meio** (ex.: NÓ113.1 entre NÓ9.1 e VRP-15): o segmento é um só (TR007 + TR006, 295,98 m),
  com o aviso "não é conexão".
- **Conexão no meio da linha** (ventosa, hidrante ou tê que a 06.1 não cortou, 29 casos): o segmento vira o intervalo
  da linha até a conexão. Ex.: NÓ56.1 → VTF-22 = TR019 0–31,24 m; VTF-22 → VM-4.2 = 31,24–39,50 m.
- **O mesmo par de nós em outra PB** (os números se repetem): sempre "confirmar", com a dica de qual PB a extensão
  indica. Paralelos da mesma PB são separados pelo DE ou pela extensão.
- Cada trecho possível mostra a própria situação e a prévia do que gravaria; o que não serve aparece desabilitado.

### Registrar

O botão **Registrar** só libera com todos os segmentos conferidos. Numa transação só:

- **Topografia:** grava a liberação topográfica em cada linha da 06.1, **só no que ainda não estava liberado**.
- **Cadastro:** grava o cadastro de campo **só sobre o assentado até a data da nota**; o resto fica **pendente** no
  segmento ("ainda não assentado até 15/10/2026"). Quando o assentamento for lançado (com data até a da nota),
  **Aplicar o que falta** grava o que faltava. Repetir não grava duas vezes.
- **Serviço de obra:** guarda a nota e o croqui. Nada é gravado nos trechos; a equipe abre a nota na Nota do dia.
- Cada registro leva a referência `NS 012 fl. 01/01` e o segmento da nota de onde veio (`ns_segmento_id`).

### Reenvio e anulação

- **O mesmo arquivo** de novo é recusado ("já foi registrado").
- **Mesmo conteúdo em outro arquivo** (por exemplo, a versão assinada): troca só o arquivo; a versão anterior fica
  guardada como substituída.
- **Mesmo número com outro conteúdo:** é preciso **anular** a anterior (com motivo) antes de registrar a nova.
- **Anular** (motivo obrigatório) anula as liberações e retifica os cadastros da nota com o mesmo motivo. Nada é
  apagado: o histórico fica.

### Quando a nota é recusada

| Mensagem | O que fazer |
|---|---|
| "a nota é de outro contrato" | conferir se é desta obra; a NS de outra obra nunca entra |
| "PDF sem camada de texto" | pedir o PDF gerado pelo Excel (não a digitalização) ou enviar a planilha `.xlsx` |
| erro nas contas (A01, A04, A08, A11, A13…) | conferir a nota com a topografia; corrigida, enviar de novo |
| "leram dados diferentes" | enviar a planilha `.xlsx` da nota, que é a leitura exata |
| "folhas … de …" | enviar o PDF com todas as folhas |
| "data … futura" | conferir a data da nota |

### Onde ficam os arquivos

No servidor (pasta `documentos`, pelo SHA-256, como as notas fiscais) e no Drive da obra:
`03_EXECUCAO_DE_CAMPO/02_Notas_de_Servico/<Topografia|Cadastro|Servicos>/<Zona>`, com nome legível, por exemplo
`Morro da Cruz - NS 012 fl 01 - Topografia - Zona03 PB08 - 2026-10-15 (hash).pdf`. Ao abrir pelo sistema, o arquivo vem
com `Content-Disposition: inline`, `X-Content-Type-Options: nosniff` e `Content-Security-Policy: sandbox`
(conferido no Chromium 141: o PDF abre normalmente). O envio acima de 32 MB é recusado antes de ser lido.

---

## 2. NS do dia (Execução · Nota do dia)

### Como enviar pelo celular

1. A equipe vem fixa para o encarregado (supervisor, engenharia e administração escolhem a equipe).
2. **Nota de serviço do dia (PDF)** e **Croqui (PDF ou foto)**, os dois obrigatórios. Foto do celular vale.
3. Toque no **clima de manhã** e no **clima à tarde**. É o único toque da tela: a nota não traz o clima e o diário
   precisa dele.
4. **Enviar a nota do dia**. A data é a da nota.

Nada a digitar sobre o que foi feito: vem da nota. Mais de uma nota por equipe e dia é permitido (folhas ou frentes
diferentes). Soldas e fotos continuam como antes, em **Outros registros do dia (opcional)**.

### O que o sistema recusa

Nota de outro contrato, PDF sem texto, data futura, a mesma nota de novo ("já foi enviada") e, sem o clima do dia, o
envio (a menos que o clima já esteja registrado). Nota com data mais de 3 dias antes do envio entra com o aviso "NS
enviada com atraso".

### O que o sistema lança sozinho

Os segmentos inequívocos viram execução **informada** (amarela no mapa, "sem verificação"), em nome de quem enviou,
com um apontamento por linha da 06.1 e a referência `NS 015 · 0+0,00` a `14+15,98`.

- **Etapa:** do título da nota, do título do grupo e das observações. ASSENT… → assentado; REATERR… → reaterrado
  (só sobre o assentado); ESCAV… ou VALA ABERTA → escavado (etapa complementar). Mais de uma palavra, mais de uma etapa.
  **Nada escrito: assentado**, com o aviso "a NS não diz a etapa: considerado assentamento".
- **Nó → nó com a distância do projeto:** o trecho inteiro.
- **Distância menor:** execução **parcial**, a partir do elemento de menor estaca. Não é erro.
- **Linha sem elemento no fim** (em branco, só estaca, "FIM", "PARADA", "ATÉ AQUI"): a execução parou naquela estaca.
  O sentido vem, nesta ordem: do trecho em que a nota já vinha, de outro elemento citado (no título do grupo, por
  exemplo "(NÓ9.1 - VRP-15)"), da **programação do dia da equipe** (Dados da obra), da **NS de serviço da zona**; senão,
  a engenharia escolhe. Ex.: NÓ9.1 e parada na estaca 6+2,01 = TR007 0–2,51 m e TR006 0–119,50 m.
- **Grupo que começa no meio** (continuação do dia anterior): a primeira estaca sem elemento é de onde a equipe
  continuou; as posições contam a partir do primeiro elemento reconhecido.
- **Trecho já lançado** naquela etapa: pulado, e a resposta diz "x m já estavam lançados".
- **Conexão no meio da linha:** intervalo da linha, como na seção 1.
- **MND não tem vala:** no pedaço MND do trecho físico, escavação e reaterro são pulados, com aviso; o assentado vale.
  Nada vai para a fila por causa do MND.

### O que vai para a engenharia

Sem gravar nada, vão para a fila **NS do dia a conferir** (tela Notas de serviço): mais de um trecho possível (por
exemplo, o mesmo par de nós em duas PBs), parada sem sentido definido, distância maior que a do projeto (até 5 %:
aceitar a diferença; acima: erro), elemento que não existe na zona e o segmento cujo lançamento foi recusado (avanço
legado sem posição, sobreposição…). O reaterro sem assentado espera na fila o assentamento. O encarregado vê
"aguardando a engenharia". A engenharia escolhe o trecho (e com ele o sentido) ou deixa de fora com o motivo e toca
**Registrar o que foi conferido**; repetir não grava duas vezes.

### Como anular

**Anular este envio**, com motivo: anula a nota e os registros dela (retificação com lista vazia; a escavação é
anulada), sem apagar nada. O encarregado anula o envio da própria equipe **enquanto nenhum registro dele foi
verificado**; depois disso, só a engenharia e a administração. Reenviar o mesmo conteúdo em outro arquivo troca só o
arquivo.

### Lançamento à mão (exceção)

O formulário digitado (trecho + metros) saiu da tela do encarregado. Fica em **Sem nota de serviço (exceção)**, só para
a engenharia e a administração (permissão `lancar_sem_ns`), com o **motivo obrigatório**, guardado no apontamento.
Nó e caixa continuam no mesmo formulário.

### Diário de obra (Execução · Diário de obra)

Por dia e equipe: a nota do dia e o croqui enviado, ao lado do **croqui do sistema** (um mapa pequeno com os trechos que
o sistema entendeu da nota acesos e os da fila tracejados), o que foi lançado (linha da 06.1, metros e etapa) e o que
espera a engenharia; **programado × executado** (programação do Dados da obra × o que foi lançado); clima, pessoas e
material, soldas, fotos, ocorrências e interferências, como antes; e os alertas: "check-in feito e nenhuma NS do dia",
"NS enviada com atraso" e "segmentos aguardando a engenharia".

No Drive: `03_EXECUCAO_DE_CAMPO/02_Notas_de_Servico/Execucao/<Zona>/<AAAA-MM>/`, com
`Morro da Cruz - NS do dia 015 - Zona03 PB08 - 2026-10-21 (hash).pdf` e o mesmo com "- croqui".

---

## 3. O que ainda é frágil

- **O formato real da NS do dia ainda não foi visto.** Os casos foram feitos com notas sintéticas no leiaute Caesb.
  A linha de parada é lida do PDF quando tem as cotas (com ou sem método e material). **Só com a estaca e as
  distâncias**, as colunas ficam incertas e a nota é recusada (E04/E05). A planilha `.xlsx` da nota deve resolver,
  mas esse caso ainda não foi testado.
- **O croqui não é lido** (o texto do AutoCAD sai embaralhado; a foto pode estar torta): é guardado e mostrado.
- **Nós e caixas** (tê, registro, VRP): a nota do dia não diz que a peça foi instalada; hoje só o lançamento à mão.
- **Nomes de elementos** de uma NS de água real ainda não vistos; sem vocabulário de esgoto (PV, coletor) como regra.
- **PDF escaneado:** recusado; não há OCR.

## 4. Testes

`tests/test_ns_leitura.py` (leitor), `tests/test_notas_servico.py` (migração v18, casamento, registro por tipo,
permissões, arquivo e 413) e `tests/test_ns_dia.py` (NS do dia: inteiro, parcial, parada pela programação e pela
engenharia, continuação e já lançado, reaterro e escavação, MND, conexão no meio da linha, sem etapa, recusas, atraso,
permissões, anulação e Diário de obra), sobre a base real das planilhas (`tests/base_real.py`). Os PDFs reais de
exemplo não ficam no repositório: `MC_NS_EXEMPLOS=<pasta>` roda o teste deles.
