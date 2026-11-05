# Sistema na nuvem: link fixo, sempre no ar

CT 10.239/2026 · 18/10/2026 · decisão D-60 revista em 18/10/2026

**O que muda:**
- O sistema fica num endereço fixo `https://…`, no ar 24 horas.
- Não depende de computador da obra nem do `MorroDaCruz.exe` aberto.
- A equipe entra pelo celular ou pelo computador, cada pessoa com o próprio usuário e senha.

**Por que o Netlify não serve:** o Netlify só publica páginas fixas (HTML). O sistema precisa de um programa rodando o tempo todo, com o banco de dados que guarda o que engenharia, almoxarifado e equipes lançam. Por isso deu "Page not found" e, mesmo acertando a pasta, o login não funcionaria.

## Qual hospedagem

A conta fica no nome do responsável pela obra. Ninguém além dele cria conta nem cadastra cartão.

| | PythonAnywhere (grátis) | Render (pago) |
|---|---|---|
| Custo | zero, sem cartão | cerca de US$ 7,25/mês (servidor US$ 7 + disco de 1 GB US$ 0,25), com cartão |
| Link | `https://<seu usuário>.pythonanywhere.com` | `https://morro-da-cruz.onrender.com` (ou parecido) |
| Espaço para fotos e documentos | 512 MB no total (a obra carregada ocupa uns 50 MB): algumas centenas de fotos de celular | o disco aumenta quando precisar (US$ 0,25 por GB/mês) |
| Manutenção | um clique por mês ("Run until 1 month from today"), com aviso por e-mail | nenhuma |
| Versão nova do código | colar de novo o comando de instalação | automática a cada envio ao GitHub |
| Instalação | criar o site (3 cliques) e colar um comando | conectar o GitHub e preencher 3 campos |
| Velocidade | um pedido por vez; serve uma equipe pequena | melhor |

**Recomendação:**
- Comece no PythonAnywhere: dá o link fixo hoje, sem custo, e serve para a equipe começar a usar.
- Quando as fotos de campo começarem a encher os 512 MB, ou se o clique mensal incomodar, passe para o Render (§3, "Mudar de hospedagem").

Os limites acima foram conferidos nas páginas públicas em 18/10/2026: [PythonAnywhere, conta gratuita](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/) e preços do Render (serviço Starter e disco). Confira antes de contratar, porque esses valores mudam.

## 1. PythonAnywhere (grátis)

1. Crie a conta em https://www.pythonanywhere.com, no plano gratuito ("Beginner"). O nome de usuário vira o link: com `ankaramc`, o link é `https://ankaramc.pythonanywhere.com`.
2. Crie o site: abra **Web** → **Add a new web app** → **Next** → **Manual configuration** → **Python 3.13** (ou a mais nova da lista) → **Next**.
3. Abra **Consoles** → **Bash** e cole este comando (é uma linha só):
   ```
   [ -d ~/Projeto-Pessoal ] || git clone -b claude/powerbi-modifications-wqxekj --depth 1 https://github.com/gabrielghorta/Projeto-Pessoal.git ~/Projeto-Pessoal; bash ~/Projeto-Pessoal/morro-da-cruz/instalar_pythonanywhere.sh
   ```
   O comando:
   - baixa o código;
   - monta a obra a partir das planilhas (menos de 1 minuto);
   - pede **o seu login e a sua senha de administrador** (10 caracteres ou mais);
   - liga o site.
4. Se ele pedir, abra **Web**, ligue **Force HTTPS** e clique no botão verde **Reload**.
5. Abra o link, entre com o seu login e cadastre a equipe em Administrativo › Usuários e histórico.

**Depois:**
- Uma vez por mês, abra **Web** e clique em **Run until 1 month from today**. O PythonAnywhere manda e-mail antes de desligar.
- Para receber uma versão nova do sistema, cole de novo o comando do passo 3. Os dados não são apagados: ficam em `morro-da-cruz/dados_demo`, fora do Git.

## 2. Render (pago, sem manutenção)

1. Crie a conta em https://render.com, entrando com o GitHub. Cadastre o cartão em **Billing**.
2. Clique em **New** → **Blueprint**, escolha o repositório **Projeto-Pessoal** e a branch `claude/powerbi-modifications-wqxekj`. O Render lê o `render.yaml`, que fica na raiz do repositório.
3. Ele pede três valores. Preencha:
   - `MC_ADMIN_LOGIN`: o seu login, por exemplo `gabriel.horta`;
   - `MC_ADMIN_NOME`: o seu nome;
   - `MC_ADMIN_SENHA`: a sua senha, com 10 caracteres ou mais.
4. Clique em **Apply**. Em poucos minutos o link aparece no topo da página do serviço (`https://….onrender.com`).
5. Entre com o seu login. Troque a senha em **Trocar senha**, porque a do passo 3 fica visível para quem acessa a conta do Render. Depois cadastre a equipe em Administrativo › Usuários e histórico.

**Depois:** cada envio ao GitHub que mexe na pasta `morro-da-cruz/` publica sozinho a versão nova. Se a versão nova não subir, o Render mantém a anterior no ar.

## 3. Como funciona e o que continua valendo

**Banco:**
- Enquanto você não aprovar os controles CTRL-01 (D-01), o site roda no **banco de demonstração**, com a faixa amarela DEMONSTRAÇÃO, o mesmo do programa do Windows.
- Os dados da obra são os reais, das planilhas do repositório. Os lançamentos ficam nesse banco de teste e **não passam sozinhos para o banco oficial**.
- A importação oficial na nuvem depende da D-01 e é feita por você, com o site parado.
- A medição continua de TESTE (D-56).

**Segurança:**
- Cada pessoa entra com o próprio usuário e senha, sobre https.
- Usuários de demonstração (senha pública) ficam sempre desativados na nuvem.
- Não existe "entrar sem senha" nem página `/configurar`: na nuvem, nada é tratado como "o próprio computador".
- O cookie de sessão vai com `Secure` e `HttpOnly`, e o navegador é obrigado a usar https (HSTS).
- O primeiro administrador é criado uma vez só: com as variáveis `MC_ADMIN_*` no Render, ou pelo console no PythonAnywhere. Depois disso elas são ignoradas.

**Versão nova do código:**
- Se o banco for de uma versão anterior, o próprio site migra ao subir, antes de atender. Faz antes um backup verificado, no mesmo disco.
- No Render, com disco, o servidor antigo para antes de o novo subir.
- No PythonAnywhere, a migração acontece no primeiro acesso depois do **Reload**. O console não migra com o site no ar.

**Backup:**
- **Render:**
  - o disco tem cópia diária automática da própria hospedagem;
  - além disso, pelo **Shell** do serviço: `python backup.py criar --db /var/data/dados_demo/obra.db --destino /var/data/backups`.
- **PythonAnywhere:**
  - no console Bash: `cd ~/Projeto-Pessoal/morro-da-cruz && python3.13 backup.py criar --db dados_demo/obra.db --destino dados_demo/backups`;
  - baixe a pasta do backup em **Files** uma vez por semana;
  - cada backup ocupa espaço dos 512 MB.

**Restauração e importação:** só com o site parado.
- **PythonAnywhere:** **Web** → **Disable**; rode o comando no console; depois **Enable**.
- **Render:** fale comigo antes. Com o disco, o servidor e o console dividem a mesma máquina.

**Mudar de hospedagem:**
1. Faça o backup na antiga.
2. Copie a pasta do backup para a nova.
3. Rode `python backup.py restaurar` com o site parado.

## 4. O que continua igual

- O `MorroDaCruz.exe` continua funcionando como antes: no próprio computador, com o link temporário pelo túnel.
- As regras de negócio, as permissões por perfil, a auditoria e as travas da medição são as mesmas. O site da nuvem usa o mesmo servidor, sem cópia de regra.

## 5. Data de Brasília (23/10/2026)

O PythonAnywhere roda em UTC. Das 21h à meia-noite de Brasília, o servidor já estava no dia seguinte: o pino e o laranja da equipe liberada no dia sumiam do mapa, e datas de hoje eram recusadas como futuras. Desde 23/10/2026 todo o código usa `relogio.py` (`hoje()` e `agora()` de Brasília, `America/Sao_Paulo`, com UTC−3 de reserva se o fuso não existir). Os carimbos novos são gravados em horário de Brasília, no mesmo formato ISO; os antigos (UTC) não são reescritos (D-109). Não há nada a configurar no PythonAnywhere.
