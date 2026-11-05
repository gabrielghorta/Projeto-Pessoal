# Validação da nota de serviço unificada — D-213

05/11/2026 · esquema v25 · testes somente em bancos temporários/cópias locais.

- **548 testes únicos cobertos**, conferidos contra a descoberta completa de `unittest`; 3 pulados por recursos
  opcionais. Execução distribuída por módulo, sem dividir classes de ciclo. Uma expectativa antiga da mensagem de
  permissão foi atualizada; os 7 casos de `test_execucao` foram reconferidos e passaram. Nenhuma falha pendente.
- Os 12 casos novos de `test_ns_unificada.py` cobrem envio único, compatibilidade da API anterior, equipe/clima/croqui,
  mapa e lista do supervisor, autoria independente, reaproveitamento dos anexos, histórico intacto, idempotência,
  vínculo a execução idêntica existente, anulação, permissões, arquivo indisponível, liberação e migração v24 → v25.
- Navegador Edge/Playwright em **390 e 1280 px**: uma página Nota de serviço; endereço antigo `#notas/dia` abre essa
  página; Topografia e Cadastro continuam disponíveis. Sem erro JavaScript, HTTP 500 ou rolagem horizontal.
- Caso do pacote sintético de 50%: NS 7105, antes recebida como `SERVICO`, reutilizada pela equipe A1 criada e
  composta manualmente na cópia. **Zona 04 · PB01 · TR003** passa a executado e entra na lista de verificação do
  supervisor. O original não muda. NS 7106 enviada pelo formulário único também registra execução; a lista usa a
  data da nota, inclusive quando é de mês anterior.
- Repetição do teste anula apenas as execuções sintéticas da cópia local, preservando histórico. Nenhum acesso ao
  site ou banco de produção. Tiles OpenStreetMap e fontes externas interceptados por fixtures no navegador.
- Sintaxe JavaScript e `git diff --check` conferidos.

A entrega não registra verificação, aprovação Caesb ou equipe/clima por suposição. Segmentos com pendências ficam
identificados para a engenharia; não são pintados como executados sem intervalos gravados.
