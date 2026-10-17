# Implantação, operação e recuperação

CT 10.239/2026 · 17/10/2026 · esquema v13

Este é o procedimento para pôr o sistema em uso no computador da obra, operá-lo, fazer backup e recuperar.

**Situação de cada etapa:**
- Ensaiado em Linux (ambiente de desenvolvimento) e no ciclo da Zona01 (`docs/EVIDENCIAS_CICLO_ZONA01.md`).
- **Não ensaiado em Windows**: os comandos são os mesmos (`python` no lugar de `python3`). Confira o primeiro backup e a primeira restauração nessa máquina antes de depender deles.

**Limites que continuam valendo:**
- O servidor escuta **só em 127.0.0.1**. O acesso pelo celular depende da decisão D-60 (hospedagem, HTTPS, rede).
- Não há funcionamento sem internet. A instalação como aplicativo também não existe, e não seria prova de funcionamento offline (D-61).
- A medição oficial continua bloqueada (D-56).
- A importação no banco real exige os controles CTRL-01 aprovados por você (D-01).

## 1. Requisitos

| Item | Versão / observação |
|---|---|
| Python | 3.11 ou mais novo (testado com 3.13) |
| `openpyxl` | obrigatório: `pip install openpyxl` |
| `pillow` | recomendado (decodificação completa de JPEG): `pip install pillow` |
| Navegador | Chrome, Edge ou Firefox atuais |
| Disco | banco + fotos + documentos + backups. Reserve ao menos 3× o tamanho da pasta `dados/` para os backups |

## 2. Pastas

```
morro-da-cruz/
  planilhas/        planilhas oficiais (nomes em config/fontes.json) — NUNCA são alteradas pelo sistema
  mapa/             HTML REV02 do mapa — não é alterado
  config/           controles (aprovação sua), perfis, serviços × BM, decisões, de-para de conciliação
  dados/
    morro_da_cruz.db   banco SQLite (operacional)
    fotos/             fotos originais (nome = hash SHA-256)
    documentos/        NF-e (XML), PDFs e imagens de documentos (nome = hash)
    backups/           um backup por pasta, com manifesto e hashes
    relatorios/        relatório JSON de cada importação/simulação
    logs/servidor.log  log do servidor (rotação: 5 arquivos de 2 MB)
```

As pastas `planilhas/`, `mapa/` e `dados/` ficam **fora do Git** (`.gitignore`). Os dados da obra não vão para o repositório.

## 2.1 Demonstração antes da implantação

`python demo.py` cria `dados_demo/obra.db` a partir das planilhas, com o perfil TESTE e usuários de demonstração (senha `demo-morro-123`), e abre o sistema em http://127.0.0.1:8765.
- Não usa nem altera `dados/`.
- Não preenche a aprovação real.
- `python demo.py --recriar` apaga só `dados_demo/` e recria.

## 3. Primeira instalação

1. Copie o código (ou faça `git clone`) para a pasta da obra.
2. Coloque as planilhas em `planilhas/` e o mapa REV02 em `mapa/`.
3. Confira cada valor de `config/controles.json` na fonte e preencha você mesmo o bloco `aprovacao` (D-01).
4. Simule a importação: `python importar.py`. Leia o relatório; nada é gravado.
5. Aplique: `python importar.py --aplicar`. O comando trava a manutenção, faz backup verificado, importa numa transação única e grava o relatório.
6. Crie o primeiro usuário: `python usuarios.py criar --login seu.nome --nome "Seu Nome" --perfil ADMINISTRACAO`. A senha é pedida no terminal, com 10 caracteres ou mais.
7. Crie os demais usuários pela aba 6 ou pelo mesmo comando, conforme a distribuição de perfis que você aprovar (D-10, `config/perfis.json`).
8. Suba o servidor: `python server.py` e abra http://127.0.0.1:8765.
9. Faça e verifique o primeiro backup (§5).

## 4. Operação diária

- **Iniciar:** `python server.py` (opções: `--porta 8765`, `--db caminho`). Um banco em esquema antigo é recusado com a orientação de migrar.
- **Encerrar:** Ctrl+C. O servidor apaga a marca de "servidor ativo".
- **Logs:** em `dados/logs/servidor.log` ficam as requisições com status, as recusas e os erros com rastreamento.
- **Auditoria:** a aba 6 mostra, por objeto ou usuário, quem fez cada gravação, aceita ou recusada.
- **Relatórios:** a aba 7 mostra o ciclo do material, o avanço, as pendências e os faltantes, com exportação .xlsx.
- **Senhas:** cada usuário troca a própria no botão "Trocar senha". O administrador redefine com `python usuarios.py senha --login x`.
- **Desativar quem saiu:** `python usuarios.py desativar --login x`. O histórico é preservado.

## 5. Backup

```
python backup.py criar                 # cria e verifica (pode rodar com o servidor no ar)
python backup.py verificar dados/backups/<pasta>
```

**O que o backup faz:**
- copia o banco com a API de backup do SQLite (instantâneo consistente);
- copia as fotos e os documentos referenciados;
- grava o manifesto com o SHA-256 de cada arquivo e confere a cópia;
- sem algum anexo referenciado, fica marcado **INCOMPLETO** e o comando avisa;
- durante a cópia, a trava de manutenção faz o servidor recusar gravações por alguns segundos.

**Rotina recomendada:**
1. Um backup ao fim de cada dia de trabalho.
2. Uma cópia semanal da pasta `dados/backups/<mais recente>` para um disco externo ou nuvem privada da Ankara, fora do computador da obra.
3. Antes de importar uma revisão ou atualizar o sistema, o próprio `importar.py --aplicar` faz backup verificado.

**Agendamento no Windows** (não ensaiado): no Agendador de Tarefas, crie uma ação diária `python C:\obra\morro-da-cruz\backup.py criar`, com "Iniciar em" = pasta do sistema. Confira o resultado com `verificar` na primeira semana.

**Retenção:** nada é apagado automaticamente. Apague backups antigos manualmente, mantendo ao menos os 7 últimos diários e 4 semanais.

## 6. Restauração (servidor PARADO)

```
python backup.py verificar dados/backups/<pasta>     # tem de dar Integridade OK e Completude OK
python backup.py restaurar dados/backups/<pasta>
```

- A restauração é recusada se o servidor estiver no ar ou se houver outra manutenção em andamento.
- Antes de substituir, ela guarda o estado atual num backup de segurança verificado e informa a pasta.
- Banco, fotos e documentos voltam e são conferidos pelos hashes.
- Backup INCOMPLETO só é restaurado com `--permitir-incompleto` (decisão consciente: os anexos ausentes continuam ausentes).

Depois de restaurar:
1. suba o servidor;
2. confira na aba 7 as pendências e o avanço;
3. confira na aba 6 o último registro de auditoria. Ele marca até quando os dados foram recuperados; o que foi lançado depois precisa ser relançado.

## 7. Nova revisão das planilhas (servidor PARADO)

1. Coloque os arquivos novos em `planilhas/`, com os nomes de `config/fontes.json`.
2. Atualize e aprove os controles da nova revisão (D-01).
3. `python importar.py`: leia o relatório. Uma alteração de trecho com histórico, sem de-para em `config/conciliacoes.json`, reprova a importação, e nada é gravado.
4. `python importar.py --aplicar`.

O histórico (check-in, intervalos, fotos, execução, medição, cadastro) segue a identidade estável do objeto.

## 8. Atualização do sistema (nova versão do código)

1. Faça um backup (§5) e pare o servidor.
2. Atualize o código (`git pull` na branch aprovada).
3. `python importar.py` (simulação): se o esquema mudou, o relatório mostra `esquema_antes` → `esquema_depois`.
4. `python importar.py --aplicar`: migra sem perda, porque as tabelas são recriadas com cópia conferida e a integridade das chaves estrangeiras é verificada antes do COMMIT.
5. Suba o servidor e confira (§6, passos 2 e 3).

## 9. Recuperação de desastre (perda ou pane do computador)

1. Instale o sistema em outro computador (§1 e §3, passos 1–2).
2. Copie a pasta do último backup externo para `dados/backups/`.
3. `python backup.py verificar ...` e depois `python backup.py restaurar ...`.
4. Se o backup for de uma versão anterior do código, rode a atualização (§8, passos 3–5).
5. Suba o servidor, confira e relance o que foi feito depois do backup.

## 10. Checklist de implantação

- [ ] Python e `openpyxl` instalados; `python -m unittest discover -s tests` passa na máquina da obra.
- [ ] Controles CTRL-01 conferidos e aprovados por você (D-01).
- [ ] Importação simulada e aplicada; relatório arquivado.
- [ ] Usuários reais criados por você, com a matriz de perfis aprovada (D-10).
- [ ] Primeiro backup criado, verificado e copiado para fora do computador.
- [ ] Uma restauração ensaiada numa cópia (outra pasta, `--db` de teste) antes do uso real.
- [ ] Decisão sobre o acesso de campo (D-60). Até lá, só no computador da obra.

## 11. O que não fazer

- Não edite o banco SQLite à mão. Correções passam por estorno, retificação ou conciliação, que guardam autor e motivo.
- Não apague `dados/fotos` nem `dados/documentos`: os registros apontam para eles pelo hash.
- Não rode `importar.py --aplicar` nem `backup.py restaurar` com o servidor no ar. Ambos recusam, mas não force apagando a marca.
- Não exponha o servidor na rede (`--host`) antes da D-60. O servidor recusa um host diferente de 127.0.0.1.
