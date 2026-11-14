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
