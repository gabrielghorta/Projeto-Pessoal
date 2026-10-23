# Roteiro de teste: do trecho até a medição

Passo a passo para testar no site o caminho de um trecho, da nota de topografia até a medição e o cadastro. É o mesmo caminho do teste automático `tests/test_fluxo_integrado.py`.

**Antes de começar:**
- Use as NS de teste (nunca as reais) e um trecho que ainda não foi executado.
- Precisa de quatro logins, de perfis diferentes, porque **quem informa não verifica** e **quem importa a nota não aprova**:
  - Engenharia (ou Administração);
  - Almoxarifado;
  - Supervisor;
  - Cadastro.

O que acende no mapa aparece no **Mapa iluminado**, no botão **Situação**. Em qualquer momento, toque no trecho: a ficha mostra o bloco **"Para entrar na medição"**, com o que já foi feito, o que falta, quem faz e onde.

---

## 1. Topografia libera o trecho

**Quem:** Engenharia. **Tela:** Execução › **Notas de serviço**.

1. Toque no chip **Topografia**.
2. Escolha o PDF da NS de topografia. Pode ser mais de uma; o croqui e a planilha são opcionais.
3. Toque em **Ler as notas**.
4. Na fila, a nota fica **"lida, sem pendência"** ou **"precisa conferir"**. Se precisar, toque em **Conferir**, resolva os segmentos e toque em **Registrar**. Se não, use **Registrar todas as conferidas sem pendência**.

**No mapa:** o trecho fica azul, **"Liberado pela topografia"**.

> Sem esta nota, nada anda. A NS do dia, a NS de serviço e o lançamento à mão são recusados com a mensagem do que falta, por exemplo: "Zona 03 · PB08 · TR020, de 0,0 m a 278,0 m: falta a liberação topográfica (registre a NS de topografia antes)".

## 2. O dia da equipe: programar e liberar o material

**Quem:** Engenharia programa; o Almoxarifado libera. **Tela:** Planejamento › **Dados da obra**.

1. No mapa, toque nos trechos. **Ctrl + clique**, ou o botão **Juntar trechos** no celular, junta vários.
2. No painel, aba **Programar**: escolha a equipe e o dia, e toque em **Programar para o dia**.
3. O almoxarife abre **Estoque e movimentos**. Em **"Equipes programadas hoje"**, toca em **Liberar**: o Dados da obra abre com o dia da equipe já escolhido. Ele confere as peças e toca em **Liberar o material do dia**.

**No mapa:** os trechos ficam laranja, **"Em execução hoje"**, e o pino da equipe aparece em cada um, no Mapa iluminado e na tela Início.

## 3. A equipe manda a NS do dia

**Quem:** o encarregado da equipe (ou a Engenharia). **Tela:** Execução › **Lançamento do dia**, aba **Nota de serviço**.

1. Escolha a equipe e toque no clima da manhã e da tarde.
2. Escolha a NS do dia e o croqui. Pode ser mais de uma; cada croqui casa com a sua nota.
3. Toque em **Enviar a nota do dia**.

**No mapa:** amarelo, **"Executado, aguardando verificação"**. Diz **"(parcial)"** se o trecho ainda não está todo assentado e reaterrado.

## 4. O supervisor verifica e manda as fotos

**Quem:** o Supervisor (outra pessoa, não quem mandou a nota). **Tela:** **Mapa iluminado**.

1. Toque em **Aguardando verificação** (aparece para quem verifica: o supervisor, e também Engenharia e Administração). A lista vem por zona, com o mais perto primeiro quando o celular dá a posição.
2. Toque no trecho. Na ficha, em **"Verificado pelo supervisor"**, escolha as fotos que faltam (sinalização, execução, concluído) e toque em **Verificar e enviar as fotos escolhidas**.

**No mapa:**
- rosa, **"Verificado pelo supervisor"**;
- com a execução completa e as 3 fotos: branco, **"Pronto para o OK interno"**.

> "Verificado" e "OK interno" são conferência interna da Ankara, nunca aprovação da Caesb. O verde só aparece com a aprovação da Caesb registrada (memorando ESET).

## 5. O cadastro de campo

**Quem:** Engenharia. **Tela:** Execução › **Notas de serviço**, chip **Cadastro de campo**.

1. Mande a NS de cadastro, como no passo 1.
2. Ela grava só sobre o que já foi executado até a data da nota. O resto é recusado e fica escrito na nota. Se o assentamento até essa data for lançado depois, toque em **Aplicar de novo** na lista "Notas recebidas".

**No mapa:** ciano, **"Cadastro de campo feito"**. O supervisor confere também o levantamento: toque em **Verificar** de novo na ficha, e o trecho volta a **"Pronto para o OK interno"**.

## 6. O OK interno e a medição

**Quem:** Engenharia (ou Administração). **Telas:** **Mapa iluminado** (ou a ficha completa no Dados da obra) e Administrativo › **Medição**.

1. Na ficha do trecho, toque em **OK interno** e confirme.
2. **Sem medição de teste aberta,** o OK é aceito do mesmo jeito:
   - o aviso diz que os lançamentos entram quando a medição abrir;
   - na Medição, o trecho aparece em **"Com OK interno, esperando a medição abrir"**, e em "Medível com restrição" com **"Sem medição de teste aberta para a data"**.
3. Abra a medição de teste do mês, em Medição › **Nova medição de TESTE**. Os lançamentos do OK entram sozinhos, uma vez só, e o número **"Com OK interno nesta medição"** sobe.

**No mapa:** roxo, **"OK interno, na medição"**.

---

## Depois: a esteira do cadastro

**Quem:** o perfil Cadastro (a conferência interna é da Engenharia). **Tela:** **Mapa iluminado**, ficha do trecho, bloco **"Cadastro"**.

A esteira anda pela própria ficha:
1. enviar à empresa;
2. receber os arquivos;
3. conferência interna;
4. protocolo no GDOC;
5. memorando ESET (ou negativa, e reenviar).

A mesma ação pode valer para outros trechos na mesma etapa: marque-os em **"Aplicar também a outros trechos nesta etapa"**.

**No mapa:**
- lilás claro, **"Cadastro em andamento"**;
- com o memorando ESET, verde, **"Cadastro aprovado pela Caesb"**, e o cadastro entra na medição.

## O resumo da tela Medição

No topo da Medição há cinco números:
- com OK interno nesta medição;
- com OK interno, esperando a medição abrir;
- prontos para o OK interno;
- aguardando verificação;
- executados sem as 3 fotos.

Toque num número para ver os trechos no Mapa iluminado; tocar num trecho abre a ficha, onde está a ação.
