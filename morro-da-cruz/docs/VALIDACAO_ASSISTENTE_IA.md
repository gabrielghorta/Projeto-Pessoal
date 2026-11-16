# Validação do assistente (IA) — 14/11/2026

D-219 a D-224 · guia em `docs/ASSISTENTE_IA.md`. Aqui está o que foi conferido, separando o que usou a **API real** da
Groq (plano gratuito, `openai/gpt-oss-20b`) do que usou o **modelo simulado**. Tudo em banco de demonstração
descartável; o site e o banco dele não foram tocados.

## Resumo

| O que | Como | Resultado |
|---|---|---|
| Exemplo de aceitação (dois contêineres → Locação → sanitário por um mês → foram três → gravar) | **API real**, versão final, roteiro HTTP | 6 de 6 conferências; 3 chamadas ao modelo |
| O mesmo exemplo na tela, até a gravação | **API real**, navegador 390 px, antes dos últimos ajustes de texto | passou duas vezes |
| Cota esgotada: aviso, texto e rascunho guardados, formulário manual, gravação sem a IA | **API real** (429 do teto diário), navegador 390 e 1280 px, versão final | passou |
| Frases inéditas, uma a uma: dúvida de uso, RH pedindo material, pedido com dois materiais, chuva, interferência, tapume com medidas | **API real**, versão final ou perto dela, chamadas avulsas | lidas corretamente depois dos ajustes (ver abaixo) |
| Quatro usos, correções, item e material ambíguos, perfis, consultas por login, cota por minuto e por dia, IA desligada, chave | **Simulado**, `tests/test_assistente.py` | 23 testes, todos passam |
| Suíte completa do projeto | sem IA | 604 testes passam |

## O que ficou sem rodar com a API real na versão final

O roteiro completo (`ferramentas/assistente/validar_api_real.py`) cobre também: pedido com correção e gravação, chuva e
interferência com correção do trecho e gravação, item ambíguo com medidas, perfil sem permissão tentando apropriar.
Essas partes **não rodaram na versão final**: os testes do dia esgotaram os 200 mil tokens gratuitos e a cota só volta
aos poucos. Elas estão cobertas pelo modelo simulado e, em parte, pelas chamadas avulsas. Para rodar quando houver cota
(gasta uns 55 mil tokens):

```bash
cd morro-da-cruz && GROQ_API_KEY=... python3 ferramentas/assistente/validar_api_real.py --saida validacao.md
```

## O que a API real ensinou durante o dia

- O modelo gratuito é pequeno. Sozinho, ele: esquecia de dizer o serviço ao anotar a quantidade; escolhia “escritório
  com sanitário” quando a pessoa dizia “sanitário”; tratava “fizemos 85 metros de tapume” como interferência; seguia
  conversando com um perfil que não podia pedir material. Cada caso virou uma correção **no código** (o que foi contado
  serve de busca; dica da opção mais próxima; descrições das funções; permissão conferida fora do modelo) e um teste.
- Erro em campo opcional não pode travar a conversa: o modelo inventa “local” e “equipe” com facilidade.
- O teto que aperta é o de **200 mil tokens por dia**, que só aparece na mensagem de recusa.

## 15/11/2026: primeiro teste no site

Frase do responsável: “eu quero dar o ok em TR confecionados, pra liberalos pra fiscalização”. O modelo abriu um
rascunho de apropriação vazio e perguntou o item. O pedido era o OK interno, fora dos quatro lançamentos. Correção: o
guia ganhou as seções do OK interno e da verificação; a regra do modelo manda consultar o guia para qualquer outra ação
do sistema; o código não abre rascunho de apropriação sem item nem quantidade e devolve ao modelo que não é apropriação.
Com a **API real**, depois da correção (2 de 2): a IA consulta o guia e responde onde se dá o OK interno, com o botão
“Abrir Mapa iluminado” e sem rascunho. Repetidos com a API real, sem regressão: o exemplo dos contêineres (primeira
mensagem), “quero lançar um serviço” (pergunta qual, sem rascunho vazio), o tapume com medidas (187 m²) e a dúvida do
supervisor sobre verificar trecho. Teste simulado novo em `tests/test_assistente.py`.

## 15/11/2026: histórico quase zero e conhecimento por seção (D-226), antes × depois

Mesmas seis conversas, **API real** da Groq (plano gratuito), banco de demonstração descartável, servidor de verdade,
conversa pelo HTTP como a tela faz (`ferramentas/assistente/medir_tokens.py`). Conta chamadas ao modelo e tokens até
chegar à resposta ou ao rascunho correto. “Antes” é o código do PR #39; “depois”, o deste PR.

| Conversa | Mensagens | Antes: chamadas | Antes: tokens | Antes | Depois: chamadas | Depois: tokens | Depois |
|---|---|---|---|---|---|---|---|
| Resposta curta (“tapume” depois de “Qual serviço?”) | 3 | 3 | 4.590 | certo | 3 | 3.692 | certo |
| Correção no meio (contêineres: “na verdade, foram três”) | 3 | 3 | 4.972 | certo | 3 | 3.849 | certo |
| Item ambíguo (placa de obra, com medidas) | 1 | 1 | 1.526 | certo | 1 | 1.277 | certo |
| Dúvida sobre o OK interno | 1 | 2 | 3.165 | errado | 2 | 2.799 | certo |
| Pedido de material com correção | 2 | 2 | 3.079 | certo | 2 | 2.017 | certo |
| Chuva numa frase só | 1 | 1 | 1.529 | certo | 1 | 1.049 | certo |
| **Total** | 11 | **12** | **18.861** | 5 de 6 | **12** | **14.683** | **6 de 6** |

**−22 % de tokens** com as mesmas chamadas; nas cinco conversas que já acertavam antes, −24 % (15.696 → 11.884). O
botão “Locação” e o toque no item da placa não chamam o modelo (contam zero nas duas colunas).

Como os números foram obtidos, sem esconder as idas e vindas:

- A primeira versão enxuta caiu para 3 de 6 certas. O modelo pequeno deixou de anotar “um mês”, trocou “ontem” por
  hoje e confundiu a consulta de trecho com a dúvida do OK interno. Correções: o exemplo da função passou a ser um par
  frase → anotação e a pedir só os números da mensagem atual; o rascunho vai ao modelo em linguagem natural; as
  instruções dizem a data de ontem; sem número de trecho, a consulta de trecho devolve a seção do guia.
- O código passou a aceitar “4m” numa medida (a validação recusava).
- Coluna “depois”: conversas 1, 2, 3, 5 e 6 da última rodada completa; a 4 é a média de três rodadas depois do último
  ajuste no texto da seção do OK interno (que só mexe nela). Nas rodadas intermediárias, a do OK oscilou: o modelo achava
  a seção certa e ainda perguntava “qual trecho?”; a frase da seção que convidava a pergunta foi reescrita. Numa das três
  rodadas finais a resposta estava certa mas dizia “dar o OK” em vez de “OK interno”; o critério do medidor passou a
  aceitar a explicação (fala do OK interno ou do Mapa iluminado, sem rascunho, com o botão da tela).
- Consumo de cota no dia da medição: perto de 150 mil dos 200 mil tokens gratuitos (todas as rodadas, inclusive as
  intermediárias). Uma rodada completa do medidor gasta cerca de 15 mil.

Também com a API real: “o que falta no zona 3 pb06 tr014 pra dar o ok?” chama `consultar_trecho` e responde a lista
do que falta (execução, verificação, fotos), sem citar o cadastro de campo como exigência.

## Transcrição da rodada final com a API real (exemplo de aceitação)

As linhas com `·` são as chamadas de função do modelo e o que o código devolveu.

### 4. Apropriação direta: o exemplo de aceitação (login eng.demo, perfil Engenharia)
eng.demo: Lança dois contêineres no canteiro
    · rascunho_apropriacao({"data": "2026-11-14", "fatores": [{"nome": "contêineres", "valor": 2}], "item": "contêiner", "local": "canteiro"}) → {"ok": true, "erros": [], "rascunho": "APROPRIACAO | fatores contêineres=2 | falta: Qual item do orçamento? Diga o serviço ou o número do item.", "falta": ["Qual item do orçamento? Diga
    (1 chamada(s), 1514 tokens; rascunho_apropriacao)
IA: O orçamento tem mais de um item para “contêiner”. Qual é? [Instalação | Locação]
  ✔ a IA procurou no orçamento e ofereceu Instalação ou Locação
eng.demo: [toca em “Locação”]
IA: Qual locação? [6.1.1 · LOCAÇÃO CONTAINER ESCRITÓRIO C/ 01 SANITÁRIO (Canteiro, MES) | 6.1.2 · LOCAÇÃO CONTAINER ESCRITÓRIO S/ SANITÁRIO (Canteiro, MES) | 6.1.3 · LOCAÇÃO CONTAINER SANITÁRIO (Canteiro, MES)]
  ✔ Locação abre os três tipos, sem chamar a IA
eng.demo: sanitário por um mês
    · rascunho_apropriacao({"data": "2026-11-14", "fatores": [{"nome": "contêineres", "valor": 2}, {"nome": "mês", "valor": 1}], "item": "1.1_6.1.3", "local": "canteiro"}) → {"ok": true, "erros": [], "rascunho": "APROPRIACAO | item 1.1_6.1.3 (6.1.3 LOCAÇÃO CONTAINER SANITÁRIO, MES) | fatores contêineres=2, mês=1 | local Canteiro
    (1 chamada(s), 1670 tokens; rascunho_apropriacao)
IA: Anotei: 6.1.3 · LOCAÇÃO CONTAINER SANITÁRIO, 2 contêineres × 1 mês = 2 MES, canteiro de obra, dia 14/11/2026. Confira o rascunho e toque em “Gravar apropriação”.
  ✔ anotou o contêiner sanitário (6.1.3) por 1 mês
eng.demo: na verdade, foram três
    · rascunho_apropriacao({"data": "2026-11-14", "fatores": [{"nome": "contêineres", "valor": 3}, {"nome": "mês", "valor": 1}], "item": "6.1.3", "local": "Canteiro de obra"}) → {"ok": true, "erros": [], "rascunho": "APROPRIACAO | item 1.1_6.1.3 (6.1.3 LOCAÇÃO CONTAINER SANITÁRIO, MES) | fatores contêineres=3, mês=1 | local Cant
    (1 chamada(s), 1626 tokens; rascunho_apropriacao)
IA: Anotei: 6.1.3 · LOCAÇÃO CONTAINER SANITÁRIO, 3 contêineres × 1 mês = 3 MES, canteiro de obra, dia 14/11/2026. Confira o rascunho e toque em “Gravar apropriação”.
  ✔ rascunho final: item 6.1.3, Canteiro e a memória de 3 contêineres por 1 mês
  ✔ nada gravado antes do toque
eng.demo: [toca em “Gravar apropriação”] → /api/apropriacao respondeu 200: {"id": 1, "data": "2026-11-14", "bm_item_id": 390, "item_novo_id": null, "item": "1.1_6.1.3", "quantidade": 3.0, "unidade": "MES", "local_tipo": "CANTEIRO", "lo
  ✔ depois do toque: apropriação gravada pela rota de sempre

### 4b. Item ambíguo e medidas (login admin.demo, perfil Administração)
admin.demo: ontem a gente terminou a placa de obra, ficou com 4 metros por 2 e meio
    (0 chamada(s), 0 tokens; sem função)
AVISO: A cota gratuita de hoje da IA acabou. Ela volta sozinha, aos poucos (dá para tentar de novo em cerca de 8 minutos); enquanto isso, use o formulário.

**Interrompido: a cota gratuita do dia acabou (tokens; a Groq pede 474 s).** As conferências acima valem; as seguintes não foram executadas.
