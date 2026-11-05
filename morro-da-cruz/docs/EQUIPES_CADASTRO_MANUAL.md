# Criar e montar as equipes da obra (D-212)

Depois da atualização, **Equipes** começa sem equipes disponíveis para novos serviços. As antigas continuam
referenciadas nos lançamentos anteriores; não foram redistribuídas para as equipes novas. As zonas do projeto e o
mapa continuam existindo, mesmo sem equipes cadastradas.

1. Engenharia/Administração abre **Equipes › Integrantes e máquinas** e escolhe a empresa em **Criar equipe**.
2. Informa um nome, se quiser, e cria a equipe. A sigla vem da sequência da empresa.
3. Abre a equipe e usa **Designar integrante**: escolhe uma pessoa já cadastrada ou informa nome e função.
4. Adiciona as máquinas. Os integrantes ficam disponíveis para marcar a presença na liberação do dia.
5. Em **Usuários e histórico**, vincula o login de perfil **Equipe (encarregado)** à equipe criada.
6. Na **Programação**, escolhe a zona/trechos e a equipe que vai trabalhar ali. Uma equipe pode trabalhar em
   diferentes zonas, conforme a programação.

O planejamento inicial é criar estas seis equipes manualmente:

| Empresa | Siglas iniciais | Uso planejado |
|---|---|---|
| Ankara | A1 e A2 | Subadutora; caixas e hidromecânico |
| Empreiteiro 1 | E1.1 e E1.2 | Redes |
| Empreiteiro 2 | E2.1 e E2.2 | Redes |

Pode criar mais equipes. A terceira Ankara será A3; a terceira do Empreiteiro 1 será E1.3. Nenhuma composição,
encarregado ou nome de pessoa é preenchido automaticamente. A equipe precisa de integrantes antes de receber
serviços; máquinas sozinhas não completam sua composição.

**Retirar da equipe** conserva a pessoa cadastrada para designá-la depois. Se ela consta da presença de um check-in
aberto, primeiro registre a devolução. Para trocar de uma equipe ativa para outra, retire-a da anterior e depois a
designe na nova. A presença anterior permanece associada ao check-in original.

**Excluir equipe** a retira das opções de novos serviços. Histórico, estoques em custódia, notas, apontamentos e
presenças permanecem com a equipe original; uma devolução de check-in antigo continua possível. O código da equipe
excluída não é reaproveitado. Reimportar as planilhas não traz equipes excluídas de volta.

O pedido do encarregado usa a equipe de seu login e só oferece as zonas com programação futura/hoje ou check-in
aberto dela. A engenharia precisa programar a equipe antes de uma requisição para uma zona nova.

A migração v23 → v24 ocorre pelo procedimento normal do site, com backup e verificação da integridade. Não é
necessário executar um comando que apague os lançamentos do banco.
