# Evidências — ciclo completo da Zona01 (etapa Z)

CT 10.239/2026 · 17/10/2026 · esquema v13 · teste `tests/test_ciclo_zona01.py` (12 passos)

## Ambiente

| Item | Como foi feito |
|---|---|
| Dados | Cópia das planilhas oficiais (06.1 REV01, 06.2 REV08, evidências, BM REV04, reajuste REV03), importada num banco **temporário** com o perfil de controles **TESTE**. A aprovação dos controles reais (D-01) não foi usada nem preenchida. Carga: CONCLUÍDA, 1.436 trechos (esperado 1.436). |
| Servidor | O `server.py` real, numa thread, só em 127.0.0.1. Todas as ações passam pelo HTTP com login, permissão por rota e auditoria. |
| Usuários | De demonstração, criados só no banco temporário: `eng1`, `eng2` (engenharia), `almox1`, `almox2` (almoxarifado), `enc1` (equipe Zona01), `adm` (administração). |
| Alvo | `Zona01_PB01_Rede_TR001` (TR-00001), 76,55 m, PEAD DE 63, VCA. Tubo `CAESB-PEAD-DE63` (fornecimento Caesb) e luva eletrofusão DE 63 `5.1_1.14.27` (material da contratada). |
| Datas | 12/10 compra · 13/10 recebimento e liberação · 14/10 execução parcial · 16/10 conclusão. Todas anteriores a hoje: registro de execução com data futura é recusado. |
| Isolamento | Banco operacional `dados/morro_da_cruz.db` e planilhas originais conferidos por SHA-256 antes e depois (7 arquivos): **inalterados**. Nenhum movimento nem aprovação no ambiente operacional. |

Resultado do teste no ambiente usado (Linux, Python 3.13):

```
python -m unittest -v tests.test_ciclo_zona01   →   Ran 12 tests … OK
```

## Passo a passo

| # | Passo | Ações (quem) | Resultado conferido |
|---|---|---|---|
| 1 | Planejar | `eng1` programa o TR001 para 14/10 (assentamento 0–76,55 m; 40 m de tubo e 6 luvas). A equipe tenta programar: **403**. | Programação PLANEJADA. Faltantes: tubo 40, luva 6. Nenhum movimento. |
| 2 | Solicitar e comprar | `eng1` solicita 20 luvas. Aprovar a própria solicitação é recusado ("Quem solicitou não aprova a própria solicitação."). `eng2` aprova. `eng1` tenta cadastrar o fornecedor: 403. `adm` cadastra o fornecedor e emite o pedido PC-Z01-001. | Solicitado 20, comprado 20, a receber 20, **estoque 0** (pedido não é estoque). |
| 3 | Receber parcialmente e conferir | `almox1` importa o XML da NF-e 9001 (20 luvas). `almox2` confere item a item contra o pedido. `almox1` recebe 12 e inspeciona: 10 aceitas, 2 recusadas (laudo LAUDO-Z01-1). Romaneio Caesb de 120 m de tubo, mais um segundo lançamento do mesmo romaneio **por engano**. | NF importada não movimenta (A_CONFERIR). Quarentena 12 → estoque 10, a receber 10. XML guardado com hash em `documentos/`. Nenhum lançamento de medição (recebido ≠ faturável). |
| 4 | Reservar e retirar | `almox1` reserva 40 m de tubo **duas vezes com a mesma chave** (clique repetido), mais 6 luvas, e faz o check-in com a retirada. | A reserva repetida devolve a mesma resposta e grava **uma** reserva. Faltante 0. Programação **REALIZADA** pelo check-in; reservas consumidas na retirada. |
| 5 | Execução parcial, fotos, soldas, cadastro | `eng1` libera 0–76,55 m (NS-Z01-001). `enc1`: apontamento para outra equipe recusado (403) e o apontamento do trecho digitado também (403: desde 21/10/2026 o avanço vem da NS do dia, D-71); `eng1` lança por exceção, com o motivo obrigatório (sem ele, 422), 0–30 m, com cadastro de campo 0–30 m (caderneta 12); sobreposição recusada; clima com data futura recusado; fotos de sinalização e execução; arquivo que não é imagem recusado; 4 soldas registradas. A equipe tenta verificar a solda: 403. `eng2` verifica: APROVADA. | Assentado 30 m, soldas aprovadas 4. Recusas: "Foto recusada: Arquivo não é uma imagem JPEG ou PNG." e "Clima com data futura (2099-01-01): só se registra o que já aconteceu." |
| 6 | Devolver sobra / manter saldo | Check-out do dia: tubo aplicado 30, sobra 6, **4 m ficam com a equipe**; luva aplicada 4, sobra 2. | Saldo e custódia batem com os movimentos. |
| 7 | Corrigir lançamentos | `eng1` retifica o apontamento: prévia (sem gravar) e depois "trena: 28 m assentados, não 30", com a referência do levantamento. `almox2` retifica o fechamento do tubo (aplicado 28 + sobra 2) e estorna o romaneio duplicado (estorno sem motivo é recusado). | Antes 30/30/0 → efetivo 28 m. **2 intervalos anulados preservados** no histórico. Tubo: recebido 120, almoxarifado 88, aplicado 28, com a equipe 4. Nada apagado. |
| 8 | Concluir, verificar, mapa | Check-in de 16/10 com +50 m (mais os 4 m que a equipe trouxe). Assentamento (à mão, pela engenharia, com motivo) e cadastro 28–76,55 m, reaterro 0–76,55 m, foto de conclusão, check-out (aplicado 48,55, sobra 5,45). A equipe tenta verificar: 403. `eng2` verifica todos os intervalos. | Mapa: antes da verificação, **CONCLUÍDO_MES / INFORMADO**; depois, **CONCLUÍDO_MES / VERIFICADO**. Concluído = 1, sem reaterro sem cadastro, sem pendência de levantamento. Material aplicado total = 76,55 m = assentado. Tubo no almoxarifado: 43,45. |
| 9 | Proposta de medição de TESTE com pendências | `eng1` abre a 1ª medição de TESTE; a OFICIAL é recusada. OK interno (o repetido é recusado). `eng2`: fechar sem conferência é recusado; confere CONFORME e fecha. Exportação .xlsx. | Mapa **OK_FISCAL**. Assentamento proposto **76,55 m** (28 + 48,55; sem os 2 m do erro). Solda: 4 aprovadas, **PENDENTE** (D-31). 12 lançamentos propostos e **14 pendentes** (fora do valor). Simulação TESTE: P0 R$ 1.034,04, total com reajuste simulado R$ 1.068,06 (**não é valor oficial**). Regras bloqueadas: D-16, D-31, D-50, D-52, D-53·D-54, D-56. Medição FECHADA (TESTE) por `eng2`. `medicao_oficial_liberada` = NAO. Trecho na esteira em 1_PRONTO. |
| 10 | Importar revisão sem perder histórico | Servidor parado. Cópia da 06.1 com a observação do TR001 alterada; controle TESTE com o hash do novo arquivo; `importar.aplicar`. | CONCLUÍDA, com backup antes e contagens OK. **225** registros operacionais: mesma contagem antes e depois. Histórico do TR001 intacto (2 check-ins, 3 apontamentos, 3 fotos, 1 registro de soldas, 26 lançamentos, 11 movimentos). Campo `observacao` alterado e registrado em `alteracoes`. Medição fechada com o valor congelado inalterado. |
| 11 | Restaurar backup e conferir integridade | Backup verificado (íntegro e completo). Perda simulada: uma foto e um documento apagados, mais um lançamento novo. Restauração com o servidor parado. | Banco **idêntico** ao do backup (SHA por tabela, 72 tabelas). 4 anexos de volta, com o mesmo hash. Backup de segurança do estado anterior guardado e íntegro. Com o servidor de novo no ar: detalhe do TR001 sem foto faltando, fotos válidas, 19 registros de auditoria do objeto. |
| 12 | Ambiente operacional intacto | — | 7 arquivos (banco operacional e planilhas) com o mesmo SHA-256 do início. |

## Observações da demonstração (o que a validação mostrou)

1. **A retificação não herda a referência do levantamento de campo.**
   - Na primeira execução, a retificação de 0–30 m para 0–28 m foi feita sem informar de novo a referência (caderneta). O detalhe passou a mostrar "levantamento sem registro de referência: 0–28 m".
   - O comportamento é intencional: a referência não é inventada para uma extensão diferente.
   - O procedimento correto, já adotado no ciclo, é informar a referência na retificação.
2. **Data futura.** O ciclo inicialmente usava 19/10, posterior a hoje, e o sistema aceitava. Foi incluída a recusa de data futura em execução, clima, soldas, liberação, ocorrência, estoque (entrada, check-in, recebimento, inspeção, devolução, transferência), OK interno e recomposição. Programação, reserva e período de medição continuam podendo ser futuros.
3. **Recebimento antes da emissão da NF-e.** Com o recebimento datado antes da emissão da nota, o sistema recusou ("Data da entrega ausente ou anterior à emissão da nota."), como esperado.

## Telas (navegador, banco final do ciclo)

As telas foram capturadas do banco final do ciclo, numa cópia isolada servida em 127.0.0.1. Sem erros de JavaScript:
- **mapa** com o detalhe do TR001: executado e verificado 76,55 m nas três etapas, histórico com 1 retificação e 2 intervalos anulados;
- compras, almoxarifado e esteira;
- **medição** FECHADA (TESTE), conferência CONFORME vigente, 14 pendentes;
- **relatórios** da Zona01: 76,55 m assentados, cadastrados e reaterrados no período; ciclo do material da luva e do tubo; pendência "cadastro não enviado";
- **auditoria** do TR-00001: 19 registros.

As imagens ficam fora do repositório (dados reais do contrato) e foram enviadas na conversa da entrega.

## Como repetir

```
python -m unittest -v tests.test_ciclo_zona01                      # exige as planilhas em planilhas/
MC_EVIDENCIAS=ciclo.json python -m unittest tests.test_ciclo_zona01   # grava os números do ciclo
```

O banco e os arquivos ficam numa pasta temporária, apagada ao fim. Com `MC_CICLO_COPIA=<pasta>`, uma cópia do banco final fica guardada para inspeção, por exemplo com `python server.py --db <pasta>/obra.db --porta 8798`.
