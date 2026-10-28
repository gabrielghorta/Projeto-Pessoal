# Atualização v22 (28/10/2026): pedir material, entrega por linha, mapa e apontamento

Decisões D-172 a D-181 (`docs/DECISOES_PENDENTES.md`, seção 16).

## Instalar no PythonAnywhere

Depois do merge do PR no ramo do site (`claude/powerbi-modifications-wqxekj`):

1. No console Bash do PythonAnywhere, rode o instalador de sempre:

   ```bash
   bash ~/Projeto-Pessoal/morro-da-cruz/instalar_pythonanywhere.sh
   ```

   Ele baixa o código novo. Como o banco é da versão 21, ele avisa que o site migra sozinho ao recarregar.
2. Na aba **Web**, clique em **Reload**. No primeiro acesso, o site faz o backup verificado e migra o banco para a v22, sem apagar nada.
3. Para não ver a tela antiga, recarregue a página no navegador com Ctrl + Shift + R.

Não há biblioteca nova.

## Notas que a regra nova liberou

Antes da v22, o material aceito de nota sem pedido e sem aprovação ficava no almoxarifado, fora do saldo das equipes (era o caso da NF 18734). A v22 tirou essa aprovação: esse material passa a contar no saldo. A migração não cria movimento nem aprovador. Ela só guarda a lista em `nf_liberadas_v22`: nota, material e quantidade.

Para ver a lista, rode no console, depois do Reload:

```bash
cd ~/Projeto-Pessoal/morro-da-cruz
python3 - <<'PY'
import sqlite3
c = sqlite3.connect('file:dados_demo/obra.db?mode=ro', uri=True)
for r in c.execute('''SELECT n.numero, l.material_id, l.quantidade FROM nf_liberadas_v22 l
                      JOIN notas_fiscais n ON n.id = l.nf_id ORDER BY n.id, l.material_id'''):
    print(*r)
PY
```

## O que muda para cada pessoa

- **Encarregado e supervisor:** menu novo **Pedir material**. Tocam no tipo, no tamanho e no material, acertam a quantidade no − e no +, e tocam na zona. O que não acharem, escrevem ou fotografam. Acompanham em **Meus pedidos**. O encarregado pede só para a zona da equipe dele.
- **Almoxarife:** também pede material. Em **Estoque › Notas a receber**, marca as linhas e aceita a entrega mesmo com linha que o sistema não reconheceu. A linha reconhecida entra no estoque na hora. A desconhecida fica registrada e entra quando a engenharia disser o que é.
- **Engenharia e administração:**
  - Em **Pedir material**, aprovam com um toque ou recusam com o motivo. Antes de aprovar, dizem qual material é o item escrito ou fotografado.
  - Em **Compras e notas**, cadastram o fornecedor junto da nota. Confirmam só as linhas desconhecidas e as que alguém mandou corrigir. Podem ligar a nota a uma solicitação aprovada; isso só marca "Chegou" e não trava nada.
  - Em **Dados da obra**, o mapa tem satélite. Na obra inteira, cada toque escolhe um trecho ou nó. Com uma zona escolhida, os toques somam e tiram, sem Ctrl. O nó de fim de rua entra sozinho. A equipe já vem a da zona.
  - Em **Lançamento do dia › Apontamento sem NS**, depois da data e da equipe, aparecem os trechos e nós em que a equipe pegou material naquele dia. Um toque abre o trecho no formulário.
- **Pedido de compra:** saiu das telas. As tabelas antigas continuam no banco.
