# Etapa 4 — Campo: intervalos, cadastro de campo, soldas e foto original

CT 10239/2026 · 16/10/2026 · esquema v6

**Nada nesta etapa gera lançamento de medição ou faturamento:**
- a medição oficial continua bloqueada;
- o OK interno continua exigindo o trecho 100 % concluído, como antes.

**Uso nesta versão:** piloto de teste. Importação e restauração exigem o servidor parado.

## O que mudou (diagnóstico D1, D2, D5)

| # | Antes | Agora |
|---|---|---|
| D1 | Medição por trecho inteiro: só metros acumulados e estaca em texto livre. Não havia como impedir intervalo sobreposto ou repetido. | **Intervalos por etapa** (`intervalos_execucao`): ASSENTADO, CADASTRO_CAMPO e REATERRADO, de x m a y m desde o início do trecho (sentido da 06.1). **Recusados:** sobreposição na mesma etapa (com o registrado ou entre os novos), repetição, intervalo fora do trecho, e reaterro ou cadastro de campo sobre trecho não assentado. Os metros executados e reaterrados passam a ser o comprimento coberto por etapa, e o detalhe mostra o que foi feito e as **lacunas**. MND não tem vala: só ASSENTADO e CADASTRO_CAMPO. |
| D1 | — | **Informado × verificado:** cada intervalo guarda quem informou; a verificação é feita por outra pessoa (`verificar_intervalo`). |
| D5 | Não havia levantamento de campo antes do fechamento da vala. | **Cadastro de campo** como etapa própria. Reaterro sobre trecho ainda sem cadastro de campo gera **alerta** (`sem_cadastro_campo`), não bloqueio. Ver decisão abaixo. |
| — | Soldas só estimadas por ⌈L/6⌉. | **Soldas informadas** (tipo eletrofusão/topo, quantidade inteira, soldador, posição opcional) e **verificadas por outra pessoa** (nem o soldador nem quem informou), com resultado APROVADA/REPROVADA (reprovação exige motivo). A estimativa ⌈L/6⌉ aparece só como referência. |
| D2 | O navegador desenhava o carimbo e enviava só a imagem recomprimida. Original, EXIF e hash se perdiam; a data era a do envio. | **Arquivo original** guardado byte a byte, nomeado pelo **SHA-256** e conferido no backup (arquivo × hash do banco). **Tipo** validado pelo conteúdo (JPEG/PNG/HEIC), com limite de 20 MB. **Data:** EXIF > aparelho > envio. **GPS:** EXIF > navegador > indisponível, nunca inventado. A **origem** de cada dado fica registrada. A **mesma imagem** não pode ser usada em outro registro. O **carimbo** é texto exibido sobre a foto, não gravado na imagem. Pedido de GPS sem resposta em 10 s não trava o envio. |
| D4 | — | O pin já diz "programado" (feito nas etapas 0 e 1). |

## Compatibilidade

- **Apontamento só em metros** (chamadas antigas): os metros ocupam as lacunas em sequência a partir do início, com origem **SEQUENCIAL**. O detalhe avisa "posição presumida — confirme em campo".
- **"100 % concluído":** preenche exatamente as lacunas (origem **COMPLETO**).
- **Migração v1–v5 → v6** (`python importar.py --aplicar`, com o servidor parado):
  - fotos antigas ficam marcadas **LEGADO** (imagem carimbada, original não preservado, sem hash);
  - apontamentos antigos **não** ganham intervalo inventado.

**Defeito corrigido junto:** com `--db` fora de `dados/`, o servidor gravava e servia fotos em `dados/fotos` do programa, e não na pasta `fotos` ao lado do banco, que é a que o backup copia. Agora usa sempre `<pasta do banco>/fotos`.

## Testes (`tests/test_campo.py`, 14)

**Critério do diagnóstico:** 30 m assentados e 20 m reaterrados. Recusados: intervalo sobreposto, a mesma medição repetida, reaterro além do assentado, sobreposição entre os novos e intervalo fora do trecho. Nenhuma recusa grava nada.

**Também cobertos:**
- previsto pelo comprimento assentado;
- alerta de reaterro sem cadastro de campo;
- 100 % preenche só as lacunas;
- apontamento só em metros sinalizado;
- MND sem reaterro;
- verificação por outra pessoa;
- trecho com OK não aceita intervalo;
- soldas, com verificação segregada e motivo de reprovação;
- foto original byte a byte, com EXIF (data e GPS);
- origem da data e do GPS sem EXIF;
- reuso e arquivo inválido recusados;
- backup detecta foto trocada mesmo com o manifesto "acertado";
- migração com foto e apontamento legados.

**Navegador** (cópia da base real, perfil de teste):
- intervalos pelo formulário, com tabela de feito e lacunas e o alerta;
- envio de JPEG com EXIF pelo campo de arquivo;
- soldas registradas e verificadas.

Sem erros de console.

## Decisões para você

1. **Reaterro sem cadastro de campo:** hoje é alerta. Deve **bloquear** o reaterro?
2. **Verificação dos intervalos e das soldas:** deve ser exigida antes do OK interno? Hoje não é, e o OK continua como antes.
3. **Herança da foto de sinalização (D3):** um nó herda a sinalização de qualquer trecho ligado, sem conferir a data. Deve exigir a mesma data ou uma janela de dias?

## Pendências desta frente

- Correção de intervalo já registrado (estorno coordenado com o apontamento e as quantidades), ainda não implementada.
- A etapa ESCAVADO não é registrada separadamente.
- Interligações e manobras (D8) não estão modeladas.
- O carimbo derivado (imagem com o texto gravado) para relatórios ainda não é gerado; hoje o carimbo é só exibido.
