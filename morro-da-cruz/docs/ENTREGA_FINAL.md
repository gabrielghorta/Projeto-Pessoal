# Entrega para revisão — webapp de gestão da obra Morro da Cruz

CT 10.239/2026 Caesb × Ankara · LC 014/2026 · 17/10/2026 · branch `claude/powerbi-modifications-wqxekj` · esquema v13

## 1. Situação: ENTREGA PARCIAL (declarada com precisão)

**O software do escopo acordado está implementado, integrado e demonstrado:**
- módulos A–F;
- falhas F01–F05 corrigidas;
- ciclo completo da Zona01 executado pelo HTTP sobre a cópia das planilhas reais.

**A entrega é PARCIAL porque decisões indispensáveis continuam com você.** Sem elas, o sistema não pode entrar em operação real nem produzir medição oficial:

| Bloqueio | O que fica travado | Decisão |
|---|---|---|
| Aprovação dos controles CTRL-01 | Importação no banco operacional (só a simulação roda) | D-01 |
| Distribuição dos perfis e usuários reais | Uso por outras pessoas (a matriz atual é provisória) | D-10, D-11 |
| Regras financeiras sem fonte | Valor de material, solda, MND, 14 serviços, rateio da escavação, reajuste com frações elegíveis | D-31, D-50…D-55, D-57 |
| Liberação da medição oficial e do modelo `01ª MC` | Toda medição é TESTE | D-56 |
| Acesso de campo (hospedagem, HTTPS, rede) | Uso pelo celular: o layout está pronto, mas o servidor só escuta em 127.0.0.1 | D-60 |
| Funcionamento sem internet | Não iniciado, por regra | D-61 |

**O que não foi feito (fora das decisões acima):**
- de-para de material numa revisão do BM (A2 parcial);
- ensaio em Windows;
- estorno de proposta de medição e reabertura de medição (dependem da D-16).

## 2. Commits desta entrega

| Commit | Conteúdo |
|---|---|
| `3f7441c` | F01–F05 corrigidos (campo) |
| `dd63fd4` | Retificação de intervalos, conciliação do legado, cadastro em fases, visão integrada |
| `7ba8c99` | Tema escuro |
| `664ce0d` | Plano de entrega completa e documento único de decisões |
| `3f0f071` | Módulo A — login, perfis, permissões no servidor, autoria, auditoria, reenvio |
| `76d611f` | Módulo B — liberação topográfica, escavação, ocorrências |
| `df8cc03` | Módulo C — compras, NF-e, aceites parciais, devolução, transferência, inventário |
| `e357211` | Módulo D — programação, faltantes, frentes, camadas do mapa |
| `fbae473` | Módulo E — parcela única, elegibilidade, conferência antes do fechamento, regras bloqueadas |
| `e2419aa` | Módulo F — relatórios, celular, guia de implantação |
| (este) | Etapa Z — ciclo Zona01, recusa de data futura, evidências, matriz final e esta entrega |

## 3. Matriz de requisitos

A matriz completa, com finalidade, aceitação, testes e decisões de cada requisito, está em `docs/PLANO_ENTREGA_COMPLETA.md` §2. Resumo:

| Módulo | Concluídos | Parciais / bloqueados |
|---|---|---|
| A. Base, histórico e acesso | A1, A3–A8 | A2 parcial (material sem de-para); A4 com matriz provisória (D-10) |
| B. Campo, qualidade e cadastro | B1–B3, B5–B9 | B4 bloqueado depois do OK interno (D-16). Regras provisórias: D-12…D-15, D-17, D-18, D-20…D-22 |
| C. Compras e almoxarifado | C1–C9 | Regras provisórias de alçada: D-40…D-44 |
| D. Planejamento e mapa | D1–D6 | — |
| E. Medição e faturamento | E1, E5, E8; E2, E3 e E7 dentro das regras provisórias | E4 (regimes) e E6 (reajuste) bloqueados; medição por intervalo (D-30), estorno (D-16) e oficial (D-56) bloqueados |
| F. Relatórios e operação | F1–F3, F5; F4 no layout | F4 acesso real (D-60); F6 não iniciado (D-61) |

Nenhum requisito foi dado como concluído só por existir tela ou função. Cada um tem critério conferido por teste automatizado e, quando há interface, no navegador.

## 4. Como iniciar e testar

**Mais fácil:** baixe `MorroDaCruz-Windows.zip` em Releases, descompacte e dê dois cliques em `MorroDaCruz.exe`. O navegador abre sozinho e, na primeira vez, pede as planilhas.

**Instalação e operação pelo código:** `docs/IMPLANTACAO.md`. Em resumo:
```
pip install openpyxl pillow
python importar.py                       # simulação (exige as planilhas em planilhas/)
python importar.py --aplicar             # só depois de você aprovar os controles (D-01)
python usuarios.py criar --login seu.nome --nome "Seu Nome" --perfil ADMINISTRACAO
python server.py                         # http://127.0.0.1:8765
```

**Testes:**
```
python -m unittest discover -s tests            # suíte completa
python -m unittest -v tests.test_ciclo_zona01   # ciclo Zona01 (exige as planilhas)
```
Os testes usam bancos temporários: planilhas sintéticas ou cópia das reais com o perfil TESTE. Nenhum toca `dados/` nem as planilhas originais.

## 5. Resultado dos testes no ambiente utilizado

Ambiente: Linux (contêiner de desenvolvimento), Python 3.13, SQLite 3.45.1, Chromium (Playwright) para as verificações de interface.

Execução da suíte completa **depois da última alteração de código desta entrega**:

```
python3 -m unittest discover -s tests -v
Ran 219 tests in 244.026s
OK
```
- Nenhum teste foi pulado: as planilhas oficiais estavam presentes. Entram na conta os testes sobre a base real (`test_base_real`, piloto `test_fluxo_zona01`) e os 12 passos do ciclo (`test_ciclo_zona01`).
- Novos nesta etapa: `test_ciclo_zona01` (12) e `TestDataFutura` (1).
- Contagem por módulo: acesso 12, retificação/cadastro 15, campo B 5, compras 11, planejamento 4, medição 7, relatórios 4, ciclo 12. O restante são as suítes anteriores (importação, regras, estoque, campo, base real, piloto).

As verificações de interface foram feitas no navegador, módulo a módulo, sobre bancos isolados:
- telas de cada módulo;
- 0 px de rolagem lateral nas 9 abas em 360 px;
- telas do banco final do ciclo.

Não houve erros de JavaScript. Os detalhes estão nos documentos `docs/MODULO_*.md`.

## 6. Evidências do ciclo Zona01

`docs/EVIDENCIAS_CICLO_ZONA01.md` traz os 12 passos com os números conferidos:
- planejar → comprar → receber parcial e conferir → reservar e retirar → executar com fotos e soldas → devolver e manter saldo → corrigir → concluir, verificar e mapa → medição de TESTE com pendências → revisão sem perda → restauração íntegra;
- o banco operacional e as planilhas originais ficaram inalterados (hash).

A demonstração também apontou três comportamentos, registrados no documento:
- a referência do levantamento não é herdada na retificação;
- a data futura era aceita (corrigido: agora é recusada);
- o recebimento antes da emissão da NF-e é recusado.

## 7. Limitações

- **Windows: ensaio parcial.**
  - Pelo GitHub Actions (17/10), a suíte passou no Windows: 219 testes OK, com 27 pulados (os que exigem as planilhas reais, que não vão para o GitHub).
  - O `MorroDaCruz.exe` foi gerado e abriu a primeira abertura no Windows.
  - Ainda não ensaiados no Windows: a montagem com as planilhas reais e o uso completo. Confira o primeiro backup e a primeira restauração na máquina da obra.
- **Servidor de um processo:** as gravações são serializadas. A concorrência é segura, mas o servidor é dimensionado para o porte da obra, não para muitos acessos simultâneos.
- **Só 127.0.0.1** até a D-60; o login está pronto para quando houver hospedagem com HTTPS.
- **Medição de TESTE:** valores com hipóteses (teto por subgrupo, reajuste sem frações elegíveis, rateio da escavação) e pendências fora do valor. Nada é oficial.
- **Relatórios ao vivo:** não há histórico mensal além da medição fechada (congelada).
- **Material sem de-para** numa revisão do BM (A2).
- **A retificação não herda a referência do levantamento** (intencional: deve ser informada de novo).

## 8. Decisões necessárias (por prioridade)

Documento único com opções, impacto, recomendação e regra provisória: `docs/DECISOES_PENDENTES.md`.

1. **D-01**: conferir e aprovar os controles CTRL-01 (você preenche `aprovacao` em `config/controles.json`). Libera a importação real.
2. **D-10 / D-11**: aprovar a matriz de perfis e criar os usuários reais. Definir se a verificação exige perfil diferente.
3. **D-60**: forma de acesso de campo (rede local do canteiro ou servidor privado com HTTPS e VPN).
4. **D-30, D-31, D-50…D-55, D-57, D-58**: regras de medição com fonte (intervalo × trecho completo, soldas, itens sem vínculo, escavação, MND, regimes de material, reajuste, teto, cadastro).
5. **D-56**: liberação da medição oficial e do modelo `01ª MC`, depois das anteriores.
6. **D-59** (nova): conferência interna obrigatória antes de fechar a medição; roteiro e segregação.
7. Regras provisórias de campo e almoxarifado: D-12…D-18, D-20…D-22, D-40…D-44. Hoje são alertas ou travas propostas.
8. **D-61**: necessidade e alcance de funcionamento sem internet.
9. **D-02, D-03**: vínculos da DEC-0001; posição de MV-11, VTF-12 e VTF-16 (sem coordenada inventada).

## 9. Implantação e recuperação

O procedimento está em `docs/IMPLANTACAO.md`:
- instalação e primeiro usuário;
- operação diária e logs;
- rotina de backup, com cópia externa semanal;
- restauração com o servidor parado;
- nova revisão das planilhas;
- atualização de versão (migração sem perda);
- recuperação de desastre;
- checklist de implantação.

A restauração e a importação de revisão foram ensaiadas no ciclo da Zona01, passos 10 e 11.

**Nesta tarefa, por regra:**
- o banco operacional não foi migrado;
- nada foi publicado;
- nenhuma aprovação foi preenchida;
- a medição oficial continua bloqueada.
