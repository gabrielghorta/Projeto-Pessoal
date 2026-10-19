# Módulo A — base, histórico e acesso

CT 10.239/2026 · 17/10/2026 · esquema v9 · plano: `docs/PLANO_ENTREGA_COMPLETA.md` §A

## Critérios de aceitação e resultado

| # | Critério | Resultado | Evidência |
|---|---|---|---|
| A3 | Sem login, toda rota da API responde 401. Mapa e fotos também ficam fechados. Só a página de login abre. | ✔ | `TestSenhaESessao.test_sem_sessao_…` |
| A3 | Sem nenhum usuário cadastrado, nada abre e o sistema orienta a criar o primeiro pelo terminal. O sistema nunca cria usuário sozinho. | ✔ | `TestSemUsuarios` |
| A3 | A senha fica só como hash PBKDF2-SHA256 (200 mil iterações, com sal). Erro de login dá uma mensagem única. Depois de 5 falhas em 15 min, o login fica bloqueado. A senha nunca vai para o log. | ✔ | `TestSenhaESessao` |
| A3 | Gravação sem o cabeçalho da aplicação é recusada (proteção contra CSRF). O cookie é HttpOnly e SameSite=Strict. | ✔ | idem |
| A4 | Perfil sem permissão recebe 403, nada é gravado e a recusa fica na auditoria. Cada rota de gravação tem uma permissão: o servidor não sobe se faltar alguma. | ✔ | `TestPermissoesEAutoria` |
| A4 | O perfil Equipe só lança para a própria equipe. | ✔ | idem |
| A5 | O autor é o usuário da sessão: o nome digitado no navegador é ignorado. Assim, a regra "quem informou não verifica" passa a valer pela identidade real. | ✔ | `test_verificacao_segregada_pela_identidade_real` |
| A5 | Toda gravação aceita ou recusada, e todo login e saída, ficam com usuário, perfil, rota, objeto, resultado e data. É possível consultar por objeto e por usuário. | ✔ | `test_auditoria_…` + aba 6 |
| A7 | O mesmo reenvio (chave X-Idem) executa uma vez só. A chave reaproveitada em outra operação é recusada. A chave vale por usuário. | ✔ | `test_reenvio_…` |
| A8 | Dois usuários ao mesmo tempo, com saldo de 30 e duas reservas de 20: uma é aceita e a outra recusada, e o disponível fica em 10. | ✔ | `test_dois_usuarios_…` (threads) |
| — | Falha no meio da gravação desfaz a operação e o registro de reenvio, e grava a falha na auditoria. O reenvio depois disso executa normalmente. | ✔ | `test_falha_no_meio_…` |
| A6 | Backup e restauração incluem usuários e auditoria (estão no banco). A inclusão dos documentos anexos fica para o módulo C. | parcial | `test_importacao` (backup) |

## Como funciona

- `acesso.py` cuida de senha, sessão, permissão, auditoria e reenvio. `usuarios.py` é o terminal do servidor: criar, listar, redefinir senha, desativar e reativar.
- `config/perfis.json` traz a matriz **provisória** (decisão D-10) com os perfis ADMINISTRACAO, ENGENHARIA, ALMOXARIFADO, SUPERVISOR (supervisor de campo), EQUIPE (restrito à equipe), TOPOGRAFIA e CADASTRO, 20 permissões e as **telas** de cada perfil (D-64).
- **Telas por perfil (D-64, 19/10/2026):** encarregado e supervisor de campo abrem Mapa iluminado e Campo; o almoxarife abre também o Almoxarifado; Engenharia e Administração abrem tudo e têm todas as permissões, inclusive criar, desativar e excluir usuários. O servidor confere a tela em cada consulta (`TELA_GET` em `server.py`; `A.exigir_tela`), não só nas gravações.
- **Excluir usuário:** apaga só a conta que nunca registrou nada (criada por engano); quem tem histórico é desativado, porque a auditoria nunca é apagada.
- **Servidor.** Uma requisição de gravação é uma transação só, com:
  - permissão;
  - restrição de equipe;
  - autoria;
  - reenvio;
  - operação;
  - auditoria do aceite.

  Na recusa, tudo é desfeito e a auditoria da recusa é gravada fora da transação. Os serviços que já usavam transação passam a usar SAVEPOINT dentro dela, e a transação externa usa BEGIN IMMEDIATE.
- **Tela:**
  - login;
  - cabeçalho com nome, login e perfil, mais trocar senha e sair;
  - formulários esmaecidos quando o perfil não tem a permissão (quem decide é o servidor);
  - aba **6. Usuários & Histórico**: usuários (só administração) e auditoria (completa para engenharia e administração; por objeto para os demais);
  - os campos "responsável", "informado por", "verificado por" e "conferido por" saíram dos formulários;
  - clique repetido reaproveita a requisição em curso; falha de rede reenvia com a mesma chave.
- **Log do servidor:** `<pasta do banco>/logs/servidor.log`, com rotação de 5 arquivos de 2 MB.

## Navegador (banco isolado: v7 real migrado para v9, usuários de demonstração)

- Senha errada mostra "Login ou senha inválidos." e a tela de login continua.
- eng.ana (Engenharia):
  - entra e vê o nome e o perfil no cabeçalho;
  - o formulário de movimento aparece esmaecido;
  - ao tentar lançar, recebe "Seu perfil (Engenharia) não tem a permissão…";
  - verifica o intervalo informado por outra pessoa;
  - a auditoria mostra verificação, recusa e login;
  - não vê o painel de usuários.
- enc.davi (Equipe Zona01): o clima da Zona02 é recusado com 403 e ele não consulta a auditoria geral.
- adm.eva cria enc.helena (Equipe Zona02) pela tela. Depois de sair, volta a tela de login.
- Defeito achado e corrigido nessa validação: a tela de login oculta continuava cobrindo a página, porque o CSS sobrepunha o `hidden`.
- Sem erros de JavaScript.

## Limitações e decisões

- No computador, o acesso é só em `127.0.0.1`. Na nuvem (`nuvem.py`, D-60 revista), o servidor liga `COOKIE_SEGURO` e o HSTS, e nada é tratado como local.
- Um processo e uma conexão: as gravações são serializadas. É seguro para o porte da obra, mas não é feito para muitos acessos simultâneos.
- A matriz de perfis e as pessoas autorizadas dependem de você (D-10, D-11). Os usuários desta validação existem só no banco isolado.
