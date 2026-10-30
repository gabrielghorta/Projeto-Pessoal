---
name: sistema-morro-da-cruz
description: Tudo o que é preciso para dar continuidade à obra Morro da Cruz (Ankara × Caesb, CT 10.239/2026) — o web app de gestão da obra (repositório gabrielghorta/Projeto-Pessoal, pasta morro-da-cruz/, site no PythonAnywhere), o cronograma físico executivo base (MS Project, xlsx no modelo do BM por equipe, Gantt e animação do Mapa iluminado), a relação contratual Caesb × Ankara (medição, BDI, K, reajuste, administração local, pacote mensal no BM oficial, relatório mensal no modelo do Lago Sul) e os dados do projeto (zonas, trechos, diâmetros, Subadutora, caixas, ligações, BM REV04, equipes, prazos). Use sempre que o assunto for o Morro da Cruz, a Ankara, a Caesb, o web app ou o site da obra, Mapa iluminado, Dados da obra, notas de serviço, almoxarifado, compras e notas fiscais, medição, BM, cronograma, Project, PythonAnywhere ou o relatório mensal, mesmo que o pedido não cite esta skill, e sempre ao retomar o trabalho numa sessão nova.
---

# Obra Morro da Cruz — web app, cronograma, contrato Caesb × Ankara e dados do projeto

Estado em **30/10/2026**. Esquema do banco **v22**. Site no PythonAnywhere a partir do ramo
`claude/powerbi-modifications-wqxekj` do repositório `gabrielghorta/Projeto-Pessoal` (pasta `morro-da-cruz/`).

## 0. Como usar esta skill (e retomar numa sessão nova)

1. Leia o **estado atual** (§1) e confira se mudou: `git log --oneline -5 origin/claude/powerbi-modifications-wqxekj`
   e os PRs abertos (`gh api "repos/gabrielghorta/Projeto-Pessoal/pulls?state=open"`).
2. Para o assunto do pedido, abra a referência certa (tabela abaixo). Esta página é o resumo; os detalhes estão nelas.
3. Trabalhe pelas regras do §6 e entregue como o responsável gosta (§7).

**A fonte de verdade é o repositório:** `morro-da-cruz/docs/DECISOES_PENDENTES.md` (todas as decisões, D-01 a D-187),
`docs/MODULO_*.md`, `docs/NOTAS_DE_SERVICO.md`, `docs/TOPOLOGIA_TRECHOS.md`, `docs/MATRIZ_REGIMES_FATURAMENTO.md`,
`config/*.json` e o código. Se algo aqui divergir deles, vale o repositório, e esta skill deve ser corrigida.

| Referência | Leia quando… |
|---|---|
| `references/dados-do-projeto.md` | precisar de um número da obra ou do contrato, de um arquivo oficial, de um termo (glossário) |
| `references/webapp.md` | for mexer no web app: ciclo, arquitetura, mapa do código, banco, importação, trecho físico, perfis, execução, almoxarifado e compras, mapas, regras do repositório |
| `references/medicao-caesb.md` | o assunto for medição: cálculo do contrato, gavetas, conferência, reajuste, administração local, o pacote mensal no BM REV04 |
| `references/modelo-lago-sul.md` | precisar do formato completo do pacote e do relatório mensal da Ankara (modelo do Lago Sul) |
| `references/cronograma-executivo.md` | o assunto for o cronograma físico executivo (REV01: a obra sai do reservatório; REV00): premissas, decisões, resultados, como gerar de novo, abrir no Project |
| `references/historico-e-pendencias.md` | quiser saber o que já foi feito (PRs), as decisões recentes, o que falta e o jeito de trabalhar com o responsável |
| `scripts/zerar_dados_de_teste.sh` | o responsável pedir para zerar os dados de teste do site |

## 1. Estado atual (30/10/2026)

- **Mesclado no ramo do site:** até o PR #17 (v22 com pedir material e entrega por linha; Subadutora; trechos
  finos). O site só muda depois que o responsável roda o comando de atualização (§8).
- **Abertos, empilhados (mesclar nesta ordem):** #18 foco por zona e Dados da obra igual ao Mapa iluminado
  (D-185, D-186) → #19 requerimentos de material em Compras e almoxarifado no Estoque (D-187) → o PR desta skill
  (`claude/skill-continuidade`: skill reorganizada e o motor do cronograma em `morro-da-cruz/cronograma_executivo/`).
- **Fora do site, entregue em 29/10/2026:** cronograma físico executivo base, cenários A (95 m/dia, fim 23/03/2028) e
  B (90 m/dia, fim 12/04/2028), em xlsx, XML do Project e Gantt em PDF; animação do Mapa iluminado em HTML.
- **REV01 do cronograma, 30/10/2026 (a que vale):** só o cenário B; a obra sai do reservatório da Zona 11 (4 saídas, a
  confirmar com a Caesb); fim em 20/03/2028; reservatório sem data (célula amarela em branco). PR
  `claude/cronograma-rev01`, empilhado no da skill.
- **Banco no site:** o de demonstração (`dados_demo/`, faixa DEMONSTRAÇÃO). A importação real espera a D-01.
- **Medição:** só de TESTE (D-56). O pacote mensal no BM REV04 já é gerado com a marca "TESTE – NÃO OFICIAL".
- **Próximos passos:** `references/historico-e-pendencias.md`.

## 2. A obra em uma página

| Item | Valor |
|---|---|
| Objeto | Implantação de redes de distribuição de água no Morro da Cruz, São Sebastião/DF |
| Contrato | CT 10.239/2026, Caesb (contratante) × Ankara Engenharia (contratada); LC 014/2026 |
| Valor (P0) | R$ 49.878.748,56 (cláusula 3.1); BM REV04 dá 49.878.748,6575869 (diferença registrada, nunca ajustada) |
| BDI / K | material 15,28 %, serviço 21,48 %; K = −14,04 % (`P0 = (Σ + BDI) × (1 + K)`) |
| Prazo | OS em 01/10/2026, 540 dias, término **23/03/2028**, 18 medições |
| Reajuste | ICC-Brasília-DI, só a pedido da contratada; o responsável conta com o de 31/01/2027 (no pacote de teste, R$ 0, "não pedido", D-140) |
| Administração local | R$ 1.304.685,94, medida em proporção ao faturamento do mês (2,7624 %, TR 14.6) |
| Rede | 1.436 trechos, 110.686 m de PEAD (DE 63 a 500; 70,4 km de DE 63); tubo **fornecido pela Caesb** (a Ankara guarda, aplica e responde por perda) |
| Frentes | Zona 01 a 11 e a **Subadutora** (adutora + DE ≥ 200 mm: 132 trechos, 10,5 km, da Equipe Adutora) |
| Nós e caixas | 1.059 nós; 132 caixas (45 DF, 26 VTF, 27 VM, 17 VRP, 11 MV, 6 HID) |
| Ligações prediais | 11.894 |
| Arquivos oficiais | 06.1 REDES REV01, 06.2 CONEXÕES REV08, BM REV04, 03.3.2 REAJUSTE REV03, EVIDÊNCIAS REV08 (`planilhas/`) e o mapa REV02 (`mapa/`) |

**Quem é quem.** A **Caesb** fiscaliza, manda as notas de serviço (NS), fornece o tubo, aprova o cadastro no GDOC
(memorando ESET) e o reajuste. A **Ankara** executa com equipes próprias e empreiteiros; dentro dela: Engenharia e
Administração, Supervisor de campo, Almoxarifado, encarregados, RH. **Topografia e cadastro são terceirizados** e a
engenharia registra por eles.

**Regra de ouro do domínio:** o sistema nunca preenche aprovação, responsável autorizado ou condição da Caesb. Toda
conferência da Ankara (verificação, OK interno, conferência interna) é interna e aparece como tal; o **verde** nos
mapas é só da Caesb (cadastro aprovado). O que não tem fonte fica **pendente**, nunca zero nem chute.

## 3. O web app em uma página

- **Técnica:** Python 3.11+ só com a biblioteca padrão + `openpyxl`, `pypdf` e `pillow`; SQLite; HTML/CSS/JS puro.
  Sem framework, sem dependência nova, sem CDN, sem biblioteca de mapa. Um processo (`server.py`), cada gravação numa
  transação com permissão, autoria e auditoria. Hoje e agora sempre de Brasília (`relogio.py`).
- **Menu:** Mapa iluminado · Execução (Lançamento do dia, Notas de serviço, Topografia, Cadastro de campo,
  Interferências, Diário) · Planejamento (Dados da obra, Cronograma da obra, Estoque e movimentos, Pedir material,
  Compras e notas) · Administrativo (Equipes, Relatórios, Usuários e histórico, LEV, Medição).
- **Ciclo:** NS de topografia libera o trecho → NS do dia informa o executado → o supervisor verifica (quem informou
  não verifica) e fotografa → cadastro de campo → OK interno → lançamentos na medição de teste + esteira do cadastro
  até o GDOC → conferência interna, fechamento congelado e pacote no BM oficial. A ordem é obrigatória (D-20).
- **Almoxarifado e compras:** o almoxarife libera o material do dia no Dados da obra e recebe a devolução; a nota
  fiscal sobe só em Compras e notas (XML ou digitada) e é aceita ou recusada no Estoque; os pedidos de material viram
  requerimentos em Compras (aprovar, "A comprar"); quem pede não aprova, quem digita a nota não confere, quem conta o
  inventário não ajusta.
- **Mapas:** o Mapa iluminado pinta cada trecho pela etapa gravada (cinza, azul-claro, laranja, amarelo, rosa,
  ciano, branco, roxo, lilás, verde); o Dados da obra usa o mesmo fundo com os trechos na cor do diâmetro e a seleção
  só dentro da zona; foco por zona nos dois (as outras zonas somem).
- **Princípios do banco:** nada é apagado (vigente = 0, estorno, anulação ou retificação com motivo e autor); a
  identidade do trecho é o handle CAD + as pontas UTM, nunca a linha da planilha.

Detalhes, mapa do código e armadilhas: `references/webapp.md`.

## 4. Medição Caesb × Ankara em uma página

- Valor do item: `ROUND(quantidade × preço sem BDI; 2)`; soma por classe; BDI por classe sem arredondar no meio; K
  sobre o total; reajuste por classe sobre o P0 medido.
- **Gavetas:** 1 serviços de trechos e nós (no OK interno) · 2 materiais (pendente: regime SL0327 bloqueado) ·
  3 cadastro aprovado no GDOC · 4 recomposição · 5 apropriação direta. PROPOSTO entra no valor; PENDENTE fica fora
  com o motivo. A mesma parcela nunca entra em duas medições.
- Fechar exige a conferência interna CONFORME e justificativa em todo item acima de 100 % do contrato; a medição
  fechada é congelada.
- O pacote é o **próprio BM REV04 preenchido** (juntada, vertical, nª MC com fotos e memorial, reajuste, cronograma
  FF, gráficos), editado por dentro do .xlsx (`xlsx_modelo.py`) para não perder desenhos. Gere o PDF pelo Excel.

Detalhes: `references/medicao-caesb.md`; formato do modelo da Ankara: `references/modelo-lago-sul.md`.

## 5. Cronograma físico executivo base em uma página

- Feito em 29/10/2026 para a reunião do responsável com a chefia. Código em `morro-da-cruz/cronograma_executivo/`
  (`bash gerar_tudo.sh` refaz tudo em ~3 min, a partir das planilhas e do REV02).
- Equipes: Equipe Adutora (Ankara 1) desde 16/11/2026, em DE 160 no "pé alto" a 60 m/dia até o reajuste e na
  Subadutora a partir de 01/02/2027; Empreiteiro 1 (2 equipes) em jan/2027; Empreiteiro 2 (2 equipes) em abr/2027;
  Ankara 2 nas caixas a partir de mar/2027 e no hidromecânico a partir de jul/2027.
- Cenário A: 95 m/dia fecha em 23/03/2028 sem folga. Cenário B: 90 m/dia, 20 dias de atraso. Faturado até jan/2027:
  R$ 2,97 mi; pico em ago/2027 (R$ 4,78 mi); outubro/2026: R$ 102,8 mil (só o que foi feito no canteiro).
- Sete premissas ainda a validar pelo responsável (pé alto, Subadutora logo após o reajuste, 95 m/dia sem margem,
  produtividade igual em todo DE, tempos das caixas, MND, sem chuva e sem recesso).

- **REV01 (30/10/2026):** só o cenário B; a obra sai do reservatório da Zona 11 e as zonas seguem a ordem da água
  (11, 09, 07, 06, 10, 05, 08, 03, 02, 01, 04); pé alto no DE 160 da Zona 11, depois DE 225 e DE 90/110; Subadutora
  do TR005 para fora; fim em 20/03/2028; R$ 2,85 mi até jan/2027; 34 trechos (2,09 km) prontos antes de ligados, com
  o motivo. Ligado ao reservatório, entrada em carga e dias sem carga dependem da data de operação do reservatório,
  em branco até a licitação.

Detalhes, decisões e como abrir o XML no Project: `references/cronograma-executivo.md`.

## 6. Como trabalhar (regras permanentes)

- **Não acesse o site nem o banco de produção.** Teste em cópias: `tests/base_real.py`, `demo.py`, ou
  `python3 server.py --db <cópia> --porta N --demonstracao` (logins `eng.demo`, `eng2.demo`, `almox.demo`…; senha
  pública de demonstração em `demo.py`).
- **Repositório público:** nunca versione nome, telefone, e-mail, CREA ou documento pessoal, nem PDF real de NS, nem
  o link da pasta do Drive da obra. Fale das pessoas pelo papel ("a equipe da adutora", "o responsável").
- **Ramos:** trabalhe num ramo `claude/…`, abra PR para `claude/powerbi-modifications-wqxekj` pela REST
  (`gh api repos/gabrielghorta/Projeto-Pessoal/pulls -f …` ou `--input pr.json`; o `gh` não tem GraphQL aqui). Nunca
  faça merge nem push no ramo do site. Se houver PR aberto mexendo nos mesmos documentos, **empilhe** o ramo novo
  sobre ele e diga a ordem de mesclar.
- **Commits e PRs:** em português, sem identificador de modelo de IA; o rodapé de atribuição vem das instruções da
  sessão.
- Sem dependência nova (Python ou JS), sem framework, sem CDN, sem biblioteca de mapa.
- `pkill -f`/`pgrep -f` com um padrão casam com a própria linha de comando e matam o shell: guarde o PID ou filtre com
  `ps -eo pid,args | awk '$2 ~ /python3/ && $3 == "server.py" && /PORTA/ {print $1}' | xargs -r kill`.
- **Cada mudança:** código + teste (`python -m unittest discover -s tests`, ~6 min, 483 testes em 29/10/2026) +
  conferência no navegador (Playwright, 390 e 1280 px, sem erro de JS e sem rolagem lateral) + documentos: uma seção
  nova em `docs/DECISOES_PENDENTES.md` com o próximo D-nnn, o `docs/MODULO_*.md` do módulo e a referência desta
  skill que o assunto toca.
- **Interface:** português do Brasil, frases curtas, vocabulário de água; mobile first, alvos de 44 px, tema escuro.
- O HTML do mapa REV02 tem fim de linha CRLF: ao editar por script, preserve o `\r\n`.

## 7. Como o responsável trabalha

- Escreve rápido, em português, muitas vezes em maiúsculas e com erros de digitação: leia pela intenção e responda em
  português simples.
- Dá a fila e a ordem dos trabalhos; siga a ordem e entregue cada item antes do próximo.
- Em entrega grande e nova, quer perguntas antes; em correção, quer a coisa feita.
- "Não mude nada em X" é literal.
- **Depois de cada PR, mande o comando de atualização do site** (§8) e diga a ordem de mesclar.
- Quer os arquivos prontos na conversa (xlsx, XML do Project, PDF, HTML), abrindo também no celular.

Mais em `references/historico-e-pendencias.md`.

## 8. Comandos úteis

**Atualizar o site** (console Bash do PythonAnywhere, depois de mesclar; depois Web › Reload e Ctrl+Shift+R):
```bash
cd ~/Projeto-Pessoal && git fetch origin claude/powerbi-modifications-wqxekj && git reset --hard origin/claude/powerbi-modifications-wqxekj && bash morro-da-cruz/instalar_pythonanywhere.sh
```

**Zerar os dados de teste do site:** o conteúdo de `scripts/zerar_dados_de_teste.sh` colado no mesmo console (apaga
o que foi lançado, mantém usuários e planilhas, guarda cópia antes, para se houver banco oficial).

**Refazer o cronograma:** `cd morro-da-cruz/cronograma_executivo && bash gerar_tudo.sh` (REV00) ou
`MPXJ=1 bash gerar_rev01.sh` (REV01, com as conferências).

**Testes:** `cd morro-da-cruz && python -m unittest discover -s tests`.

## 9. Manter esta skill

- Atualize o §1 (estado) e a referência do assunto a cada PR; registre a data.
- Mantenha esta página curta (abaixo de 500 linhas): detalhe novo vai para a referência certa.
- Números saem das planilhas oficiais; não copie números do Lago Sul para o Morro da Cruz.
