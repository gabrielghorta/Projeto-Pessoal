# Fiscalização da Caesb

O fiscal titular e o substituto usam contas individuais com o perfil **Fiscalização (Caesb)**. Esse perfil
abre o **Mapa Iluminado** e **Fiscalização**. A ficha do mapa é de consulta e apresenta execução, verificação,
coordenadas, fotos e documentos vinculados ao trecho. A Engenharia e a Administração da Ankara enviam linhas
e acompanham as respostas com seus próprios logins.

## Da execução à medição

1. Abra a medição do período em **Administrativo → Medição**.
2. O OK interno e os demais lançamentos elegíveis formam as linhas propostas do BM. Em **Fiscalização → Pronto para medir**,
   selecione as linhas em ordem de valor e clique em **Enviar à fiscalização**.
3. Em **Para aprovar**, o fiscal abre a ficha ou os anexos e escolhe **Aceitar**, **Aceitar menos** ou **Recusar**.
   Redução e recusa exigem motivo. O aceite integral também pode ser feito em lote.
4. Em **Respostas e histórico**, a Ankara vê os motivos e reenvia o que revisou. Se 70 m de 76,55 m já foram aceitos,
   o boletim continua com os 70 m e o próximo envio traz só os 6,55 m. O mesmo vale se o fiscal recusar esse saldo.
   Mudar o item, o alvo, a unidade ou outra característica que identifica a parcela exige nova conferência.
5. Enquanto a medição estiver aberta, o fiscal pode reabrir uma resposta indicando o motivo. A reabertura
   incide sobre a resposta do último envio. Autor, perfil, data e hora de Brasília ficam no histórico.
6. A Engenharia confere e fecha em **Medição**. Depois do primeiro envio à Caesb, juntada, vertical, memória de
   cálculo e RM usam as quantidades aceitas. A administração local é calculada sobre o faturamento aceito. O XLSX
   lista o restante na aba **Fora do aceite**. Medições sem envio seguem as regras anteriores.

O painel permite consultar as medições anteriores, que ficam em leitura. A data de execução continua
vinculada ao período da medição. As respostas podem ocorrer enquanto a medição estiver aberta.

O aceite registrado aqui é prévio. O documento oficial é o BM assinado e protocolado. A medição oficial
continua bloqueada pela D-56, e o verde do Mapa Iluminado continua reservado ao cadastro com memorando ESET.

## Avisos por e-mail

O contador no menu funciona com ou sem e-mail. O administrador pode cadastrar e atualizar o e-mail em
**Usuários e histórico**. O envio da Ankara gera um aviso para os fiscais ativos com e-mail. As respostas
geram um aviso para a Engenharia. O sistema salva a ação antes de tentar o e-mail.

O PythonAnywhere usa as variáveis do servidor `MC_EMAIL_USUARIO`, `MC_EMAIL_SENHA_APP` e, opcionalmente,
`MC_EMAIL_NOME` e `MC_SITE_URL`. Configure-as no WSGI da aplicação ou no arquivo que ele carrega fora do Git,
conforme o guia de hospedagem. O SMTP usa Gmail em `smtp.gmail.com:587` com STARTTLS e senha de aplicativo.
A disponibilidade da conexão deve ser conferida na conta gratuita. Se ela falhar, a ação e o contador continuam
funcionando e o painel interno registra a situação do aviso. Consulte a
[orientação do suporte do PythonAnywhere](https://www.pythonanywhere.com/forums/topic/36555/).

## Conferência em demonstração

Use a conta de Engenharia para enviar ao menos três linhas. Use uma conta de Fiscalização para aceitar uma,
reduzir outra e recusar a terceira. Confira o saldo na conta de Engenharia e envie só a diferença. Aceite o
saldo na conta de Fiscalização. Confira o painel, o histórico, a memória, a aba **Fora do aceite** e o RM.
Os testes de e-mail usam SMTP simulado.
