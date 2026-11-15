# Assistente: a IA conversacional do sistema

14/11/2026 · D-219 a D-224 · esquema v26 (sem mudança no banco)

A tela **Assistente** (menu lateral e botão no Início) começa com **“O que você quer fazer?”**. A pessoa escreve ou
fala do jeito dela. Um modelo de linguagem lê a mensagem inteira, com o contexto da conversa, e decide se responde,
consulta o sistema ou pergunta o que falta. Todo login conversa; cada um só lança o que já podia lançar nas telas.

## O que ela faz

| Uso | Exemplo de frase | O que sai |
|---|---|---|
| Dúvida de uso | “chegou uma nota fiscal, onde dou entrada?” | resposta curta, tirada do guia do sistema, com o botão que abre a tela |
| Pedido de material | “tô sem luva de 110, manda 25” | rascunho da requisição (materiais, quantidades, zona) |
| Chuva ou interferência | “ontem de tarde choveu e o empreiteiro parou” | rascunho do relato (dia, equipe, turno, efeito ou trecho e descrição) |
| Apropriação direta | “lança dois contêineres no canteiro” | rascunho com o item do orçamento, a memória de cálculo e o local |

**O modelo só interpreta. O código valida, calcula e grava.**

- O que a pessoa disse vira um **rascunho**, montado pelo código com as mesmas regras das rotinas
  (`solicitacoes.py`, `servicos.py`, `apropriacao.py`, `memoria_calculo.py`). A conta é do código: `3 contêineres × 1 mês
  = 3 MES`, `85 × 2,2 = 187 m²`.
- A tela mostra o rascunho como **formulário**: dá para corrigir qualquer campo à mão. O botão do rascunho (“Enviar
  requisição”, “Registrar chuva”, “Gravar apropriação”) envia o corpo à **rota de sempre** (`/api/solicitacao`,
  `/api/ocorrencia`, `/api/apropriacao`), que confere tudo de novo com permissão, autoria, reenvio e auditoria.
  **Nada é gravado antes desse toque**, e o assistente não tem rota de gravação.
- **Botões grandes** aparecem quando há opções claras (Instalação × Locação, a zona, a equipe, manhã × tarde × dia
  todo). A pessoa também pode responder por texto ou voz. **Correção** (“na verdade, foram três”) muda só aquele campo.
- **O que já está determinado o próprio sistema aplica, sem chamar o modelo**: o toque num botão, a edição de um
  campo, os atalhos da abertura (Pedir material, Choveu, Relatar interferência, Lançar um serviço) e o texto igual ao
  nome de um botão. Isso poupa a cota gratuita.

## Permissões

- Qualquer login abre a tela e conversa (inclusive RH, Topografia e Cadastro, para dúvidas de uso).
- Quem confere a permissão é o **código**, não o modelo: o modelo encaminha o pedido para a função do assunto e o
  sistema recusa e explica quando o perfil não lança aquilo. Apropriação direta: só Engenharia e Administração. Pedido de material: quem tem `compras_solicitar`. Chuva e
  interferência: quem tem `campo`.
- O encarregado (login preso à equipe) pede só para a frente em que a equipe está programada e relata só para a
  equipe dele; “todas as equipes” não existe para ele. As mesmas travas continuam na rota que grava.
- Consultas por função específica, sempre com o login da sessão: `consultar_catalogo` (materiais de Pedir material),
  `consultar_orcamento` (itens do BM, só para quem apropria), `consultar_frentes` (zonas e equipes do login),
  `consultar_pedidos` (as requisições que o login vê) e `consultar_ajuda` (guia de uso em `config/assistente.json`).

## Custo zero (obrigatório)

- Serviço: **Groq, plano gratuito**, modelo `openai/gpt-oss-20b`, endereço `https://api.groq.com/openai/v1`. Sem
  cartão cadastrado na Groq, não existe cobrança: quando a cota acaba, a Groq recusa a chamada.
- **Não há troca automática para outro serviço.** O código só chama o endereço configurado.
- Limites medidos em 14/11/2026 na conta gratuita, para a obra inteira: **200.000 tokens por dia** (o que aperta
  primeiro; não aparece no painel de cabeçalhos, só na recusa), **8.000 tokens por minuto** e **1.000 chamadas por
  dia**. Uma mensagem gasta 1 chamada (às vezes 2) e cerca de 1.300 a 1.500 tokens. Na prática: umas **140 mensagens
  por dia** e **4 a 5 por minuto, no site todo**. O toque em botão, a edição de campo e os atalhos não contam.
- Passou do limite por minuto, a tela espera alguns segundos e tenta de novo sozinha (até duas vezes). Acabou a cota
  do dia, ela avisa; a cota volta aos poucos (cerca de 8 mil tokens por hora, umas 6 mensagens).
- Freio por login: 8 mensagens por minuto (`mensagens_por_minuto`), para uma pessoa não gastar a cota de todos.
- **Cota esgotada:** a tela mostra o aviso, **o texto digitado e o rascunho ficam guardados**, o rascunho continua
  editável e gravável pelo formulário e aparecem os botões das telas manuais (Requisições, Interferências e chuva,
  Apropriação direta). O mesmo vale para IA desligada ou sem internet.
- Voz: usa a transcrição do **próprio navegador** (Chrome e Edge, no celular e no computador), sem custo. Onde o
  navegador não tem, o botão do microfone não aparece. O piloto anterior de microfone não está no repositório, então
  não havia código a reaproveitar.

## Ligar a IA no PythonAnywhere (uma vez)

1. Crie a chave gratuita em `console.groq.com` (menu API Keys). Não cadastre cartão.
2. No PythonAnywhere, abra **Consoles › Bash** e cole (ele pede a chave sem mostrar na tela):

   ```bash
   read -rsp "Cole a chave da Groq e aperte Enter: " K && printf 'GROQ_API_KEY=%s\n' "$K" > ~/Projeto-Pessoal/morro-da-cruz/segredos.env && chmod 600 ~/Projeto-Pessoal/morro-da-cruz/segredos.env; unset K; echo " gravada."
   ```

3. Teste a chave e a saída para a internet:

   ```bash
   cd ~/Projeto-Pessoal/morro-da-cruz && python3 assistente.py testar
   ```

   - `OK: a IA respondeu` → pronto.
   - `A hospedagem bloqueou a saída para api.groq.com` → a conta gratuita do PythonAnywhere só acessa os endereços da
     lista deles. **Não foi possível confirmar daqui se `api.groq.com` já está na lista.** Se não estiver, peça a
     inclusão pelo formulário gratuito do PythonAnywhere (“Requesting Allowlist additions”, na ajuda deles): a Groq tem
     API pública documentada, que é o critério. Até liberarem, a tela do assistente avisa e os formulários seguem.
   - `NÃO FUNCIONOU` com `O que o serviço respondeu: …` → a linha diz o motivo que a Groq deu, sem mostrar a chave.
     Os mais comuns: chave errada ou incompleta (gere outra no painel, copie pelo botão de copiar e grave de novo);
     conta restringida pela Groq (`organization_restricted`: só o suporte deles resolve, ou outra conta gratuita);
     modelo indisponível na conta (troque em `config/assistente.json`). O teste também diz o tamanho da chave e se ela
     veio com caracteres estranhos da colagem.
4. Abra **Web** e clique em **Reload**. A tela Assistente passa a responder.

A chave fica só no arquivo `segredos.env` (fora do Git, ignorado pelo `.gitignore`; o comando de atualização do site
não o apaga). Ela nunca vai para a tela, o log ou a auditoria. Em outras hospedagens (Render), use a variável de
ambiente `GROQ_API_KEY`. Para desligar a IA, apague o arquivo e recarregue: a tela avisa e os formulários continuam.

**Trocar o modelo ou o endereço:** `config/assistente.json` (`modelo`, `base_url`) ou as variáveis `MC_IA_MODELO` e
`MC_IA_BASE_URL`. O arquivo também guarda os limites (`chamadas_por_mensagem`, `mensagens_por_minuto`), os parâmetros
do modelo e o guia de uso que responde às dúvidas (`ajuda`): mudou uma tela, ajuste o texto ali.

## Privacidade

A mensagem da pessoa, o perfil dela (não o nome nem o login) e os dados consultados para responder (nomes de materiais,
itens do orçamento, nomes de equipes) saem do sistema para a Groq interpretar. A tela avisa: **não escreva dados
pessoais**. Cada mensagem fica na auditoria (`/api/assistente/mensagem`: o texto, as funções chamadas e os tokens).

## Como é feito

| Arquivo | O que faz |
|---|---|
| `assistente.py` | configuração e chave, chamada ao modelo (`urllib`, sem dependência nova), as funções de consulta, o rascunho (campos, validação, conta, corpo da rota), a conversa e o teste pelo console |
| `config/assistente.json` | modelo, endereço, limites e o guia de uso |
| `server.py` | `GET /api/assistente` (estado), `POST /api/assistente/mensagem` (conversa; o modelo é chamado fora da trava do banco) e `POST /api/assistente/rascunho` (botão e campo, sem modelo) |
| `web/assistente.js`, `web/index.html`, `web/app.css` | a tela: conversa, botões, microfone, rascunho, aviso de cota |
| `tests/test_assistente.py` | 22 testes com o modelo **simulado** (nenhum usa a rede) |
| `ferramentas/assistente/validar_api_real.py` | os quatro usos com a **API real**, em banco de demonstração descartável |
| `ferramentas/assistente/conferir_tela.cjs` | a tela no navegador, em 390 e 1280 px |

- **Sem estado no servidor e sem mudança no banco:** a conversa e o rascunho ficam no navegador (por login) e voltam a
  cada mensagem; o servidor confere o rascunho de novo toda vez. Recarregar a página não perde nada.
- **Uma chamada por mensagem, na maioria das vezes:** quando o modelo anota dados no rascunho, quem responde é o
  código (“Anotei: … Falta: …”), com os botões da próxima pergunta. Só consulta ou erro voltam ao modelo (no máximo 3
  chamadas por mensagem).
- **Item ou material com mais de uma possibilidade:** o código monta os botões; quando a primeira palavra separa os
  itens em poucos grupos (Instalação × Locação), o botão é o grupo e o toque abre os itens dele.
- **Resposta por texto a uma lista de botões** (“sanitário”): o código calcula qual opção da tela mais casa com as
  palavras e passa ao modelo como dica; o modelo decide.
- Unidades compostas do orçamento (MES, H, CHP, CHI, M3XKM, TXKM): dois fatores que se multiplicam, cada um com o nome
  do que conta. m, m² e m³ usam a memória dimensional de sempre (`memoria_calculo.calcular`).
- A busca do orçamento passou a tratar CONTAINER e CONTÊINER como a mesma palavra (o BM escreve dos dois jeitos).

## Limites conhecidos do piloto

- O modelo gratuito é pequeno. Ele acerta os casos comuns, mas pode deixar de extrair um dado da frase (aí o sistema
  pergunta, com botões) ou escolher o item errado: **confira sempre o rascunho antes de gravar**.
- Na conta gratuita do PythonAnywhere o site atende um pedido por vez: enquanto o modelo responde (em geral 1 a 2
  segundos; no máximo 20), as outras telas esperam.
- Fotos e evidências: a apropriação aceita anexos no rascunho; pedido por foto continua só na tela Requisições.
- Fora do escopo desta entrega: nota de serviço, apontamento, estoque, medição e qualquer gravação que não seja as três acima.
