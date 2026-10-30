# Histórico, decisões, pendências e o jeito de trabalhar com o responsável

Referência da skill `sistema-morro-da-cruz`. Use para saber o que já foi feito, o que está aberto e como o
responsável gosta de receber o trabalho. A lista completa e oficial das decisões é
`morro-da-cruz/docs/DECISOES_PENDENTES.md` (formato ID | Decisão | Opções | Impacto | Recomendação | Situação).

## Linha do tempo (PRs em `gabrielghorta/Projeto-Pessoal`, base `claude/powerbi-modifications-wqxekj`)

| PR | Data | Ramo | O que trouxe | Situação em 30/10/2026 |
|---|---|---|---|---|
| #1 | 17/10 | claude/powerbi-modifications-wqxekj | Banco, carga auditada das planilhas, regras e servidor (o ramo do site; o PR fica aberto) | aberto (é a base) |
| #2 | 20/10 | claude/topologia-trechos | Trecho físico (pontas no nó, cruzamentos) | mesclado |
| #3, #5 | 22/10 | claude/notas-de-servico | NS por upload, diário pela NS do dia, apropriação direta | mesclados |
| #4 | 22/10 | claude/project-thread-m8tjoy | CI do Windows (teste do .exe) | aberto, parado |
| #6 | 23/10 | claude/mapas-fluidos | Gesto pela placa de vídeo, cópia leve na borda | mesclado |
| #7 | 23/10 | claude/fluxo-integrado | NF até a quarentena, o dia da equipe, caminho até a medição, data de Brasília | mesclado |
| #8 | 23/10 | claude/execucao-reorganizada | Cada NS na sua aba; Lançamento do dia; Topografia e Cadastro | mesclado |
| #9 | 26/10 | claude/recebimento-simples | Recebimento num toque; cores claras no Mapa iluminado | mesclado |
| #10 | 26/10 | claude/medicao-modelo-oficial | Pacote da medição no próprio BM REV04 | mesclado |
| #11 | 26/10 | claude/skill-sistema-morro-da-cruz | Primeira versão desta skill | mesclado |
| #12–#14 | 27/10 | claude/notas-* , claude/conferencia-marcar | Nota sobe só em Compras; aceite/recusa na lateral do Estoque; conferir é marcar (D-169 a D-171) | mesclados |
| #15 | 28/10 | claude/v22-revisao | v22 (revisão do código feito no ChatGPT): pedir material, nota sem pedido, entrega por linha (D-172 a D-181) | mesclado |
| #16 | 29/10 | claude/mapa-frentes | Subadutora ≥ 200 mm, nós e caixas com forma, HTML base (D-182 a D-184) | mesclado |
| #17 | 29/10 | claude/mapa-linhas-finas | Trechos finos, traçado sem esperar o servidor, mosaico no instalador | mesclado |
| #18 | 29/10 | claude/mapa-foco-zona | Foco por zona como no HTML; Dados da obra igual ao Mapa iluminado, seleção só na zona (D-185, D-186) | **aberto** |
| #19 | 29/10 | claude/compras-requerimentos | Requerimentos em Compras; transferência, inventário e reservas vencidas no Estoque (D-187). Empilhado sobre o #18 | **aberto** |
| #20 | 30/10 | claude/skill-continuidade | Esta skill reorganizada e o motor do cronograma no repositório. Empilhado sobre o #19 | **aberto** |
| — | 30/10 | claude/cronograma-rev01 | REV01 do cronograma (só o cenário B): a obra sai do reservatório da Zona 11; grafo da água, carga, aba CARGA, marcos no Project, Gantt e animação novos. Empilhado sobre o #20 | PR novo |

Os PRs empilhados devem ser mesclados na ordem (#18, #19, #20, depois o da REV01). Fora do Git: em 29/10/2026, o
cronograma físico executivo base (dois cenários) e a animação; em 30/10/2026, a REV01 (`cronograma-executivo.md`).

Existe também o repositório `gabrielghorta/morrodacruz_webapp` (cópia anterior, parada em 27/10/2026, com a skill
`medicao-e-relatorio-mensal-caesb`, hoje em `modelo-lago-sul.md`). O site usa o `Projeto-Pessoal`.

## Decisões que moldam o sistema e as que estão abertas

**Decididas que moldam o sistema:** D-20 ordem obrigatória · D-60/62 nuvem · D-63/65 Drive · D-64 telas por perfil ·
D-66 terceirizadas registradas pela engenharia · D-67/75 menu · D-68 trecho físico · D-69/71/74 NS por upload,
exceção com motivo, croqui guardado · D-90/91/95 apropriação, base de custo, restrição que cai sozinha · D-101 a D-108
fluxo integrado · D-121 a D-124 execução reorganizada · D-131 a D-134 clima, NS só pela engenharia, RH · D-135
recebimento num toque · D-136 cores claras · D-137 a D-151 medição e relatório no modelo da Ankara.

**Abertas ou bloqueadas (o sistema trava e explica):** D-01 aprovação dos controles (importação real) · D-10/D-11
matriz de perfis e usuários reais · D-16 retificação/estorno depois do OK · D-30 medir por intervalo · D-31 soldas ·
D-50 14 serviços sem item · D-51 rateio da escavação · D-52 MND · D-53/D-54 regimes de material · D-55 parcela
elegível do reajuste · **D-56 medição oficial** · D-57 teto por subgrupo · D-58 critério do cadastro · D-59 conferência
da medição · D-61 sem internet (não iniciado) · D-70 numeração da NS · D-85 nós na NS do dia · D-92 quantidade do item
novo · e as provisórias de campo e almoxarifado (D-12 a D-18, D-21, D-22, D-40 a D-44) e da medição (D-152 a D-157).

**Decididas de 26 a 29/10/2026 (D-150 a D-187):**

| ID | Assunto |
|---|---|
| D-150 a D-157 | Cronograma do Project depois; cabeçalho do relatório; medições anteriores congeladas no vertical; memória de cálculo do trecho; juntada impressa; período no cabeçalho; equipe da folha da ADM; BM diferente do importado |
| D-169 a D-171 | Nota conferida sem linha para o estoque; a nota sobe só em Compras e o aceite/recusa é na lateral do Estoque; conferir é marcar |
| D-172 a D-175 | Sem pedido de compra; pedir material por toques; linha não reconhecida entra depois da confirmação; nota sem aprovação |
| D-176 a D-181 | Fundo do Dados da obra; vários trechos; nó de fim de rua; equipe já escolhida; apontamento sem NS com os trechos do dia; lançar vários a 100 % (proposta) |
| D-182 a D-184 | DE 225 e 250 com a Equipe Adutora (frente Subadutora); nós e caixas com forma; desenho do Dados da obra (a parte visual revogada pela D-186) |
| D-185, D-186 | Foco por zona nos dois mapas; Dados da obra igual ao Mapa iluminado, seleção só na zona, Desselecionar e Limpar seleção |
| D-187 | Requerimentos de material em Compras e notas (A comprar); transferência, inventário e reservas vencidas no Estoque |

## Pendências e próximos passos

1. Mesclar #18, #19, #20 e o PR da REV01; rodar o comando de atualização do site.
2. Cronograma REV01: confirmar as 4 saídas do reservatório com a Caesb e o engenheiro sênior, preencher a data de
   operação quando houver, decidir o aluguel de contêiner (82,1 % do item); depois, ligar o cronograma ao executado
   (% por trecho, linha de status, "REV nn - nª MEDIÇÃO").
3. Relatório mensal em Word (fase 2), com a tela "Dados do contrato", a presença diária e as imagens fixas.
4. Documento da juntada (ordem das peças, folha de rosto, ofício): pedir de novo ao responsável.
5. Decisões que liberam a medição oficial (D-30, D-31, D-50 a D-57) e a importação real (D-01).
6. Primeiras NS reais (formato da NS do dia, nós na NS do dia) para ajustar tolerâncias e leitura.
7. Ideia oferecida e não respondida: contador de pedidos aguardando decisão no menu.

## Como o responsável trabalha (o que funciona com ele)

- Escreve rápido, em português, muitas vezes em maiúsculas e com erros de digitação: leia pela intenção. Responda em
  português do Brasil, com palavras simples e frases curtas.
- **Depois de todo PR, mande o comando de atualização do site** (ele já reclamou quando faltou):
  ```bash
  cd ~/Projeto-Pessoal && git fetch origin claude/powerbi-modifications-wqxekj && git reset --hard origin/claude/powerbi-modifications-wqxekj && bash morro-da-cruz/instalar_pythonanywhere.sh
  ```
  Depois: aba Web › Reload e Ctrl+Shift+R no navegador. O banco (`dados_demo/`) não é tocado pelo reset.
- Ele mesmo mescla os PRs. A sessão não faz merge nem push no ramo do site.
- Dá a fila de trabalho e a ordem ("faça X e só depois Y"): siga a ordem e entregue cada item antes do próximo.
- Para entregas grandes e novas (o cronograma), pediu perguntas antes de começar. Para correções e ajustes, quer a
  coisa feita.
- Restrições do tipo "não mude nada no Mapa iluminado" são literais: mude só o que ele pediu.
- Quer os arquivos (xlsx, XML do Project, PDF, HTML) enviados na conversa, prontos para abrir, inclusive no celular
  (por isso o Gantt em PDF além do XML).
- Testa no site com o banco de demonstração e pede para zerar os dados de teste: `scripts/zerar_dados_de_teste.sh`
  (cole no console do PythonAnywhere; guarda cópia antes; para se existir o banco oficial).
- Usa o resultado em reuniões com a chefia: números fechados entre si e as premissas explícitas.
