# Validação de campo, memória e RM Word

05/11/2026 · D-215 a D-217 · bancos temporários e cópia local, sem acessar o site de produção.

- Descoberta completa: **565 casos únicos cobertos**, 3 pulados por recursos opcionais. Os dois casos com expectativas antigas
  (PDF como padrão e bloqueio por clima vazio) foram atualizados para as decisões novas e reconferidos junto com
  os módulos de relatórios, retificação e os 12 casos novos: 30/30 OK. Depois, 45 casos da integração com o PR #34 e o cenário de chuva após NS foram conferidos. A união dos logs cobre todos os 565 casos, sem falhas pendentes.
- Medidas: soma de perímetro, altura, volume, parcelas, repetições, números com vírgula, campos ausentes, quantidade
  divergente e expressão inválida. A área sem medidas é recusada; a quantidade não pode ser adulterada no envio.
- Migração v25 → v26 preserva apropriações, memória antiga, evidências e referências. Dimensões antigas continuam
  desconhecidas; não são deduzidas do total. Conferência de chaves estrangeiras sem erro.
- Chuva sem alvo obrigatório, turno, equipe restrita ao encarregado e histórico após resolução. O padrão sem chuva
  é mostrado no diário sem criar linhas fictícias de clima. Registros legados continuam compatíveis.
- Memória no próprio BM: a soma dos lados e a altura aparecem na MC; linhas de continuação não duplicam a quantidade.
- Edge/Playwright em **390 e 1280 px**: tapume (80 + 50 + 40 + 20 + 45) × 2 = 470 m² e volume 3 × 2 × 1 = 6 m³;
  apropriação sem extras; chuva relatada em Interferências e refletida no diário; download em DOCX; endereço antigo
  do clima redireciona. Sem erro de JavaScript, HTTP 500 ou rolagem horizontal.
- RM com parágrafos/tabelas nativos e figuras. Aberto/exportado pelo Word instalado, invisível, e rasterizado com
  `render_docx.py` usando esse PDF (LibreOffice ausente). Conferência visual das **28 páginas** da amostra sintética,
  com retrato/paisagem, logo, cabeçalho e rodapé. Uma quebra vazia e a relação da imagem do cabeçalho foram corrigidas.
  O servidor não depende de Word/LibreOffice.
- Sintaxe JavaScript e `git diff --check` conferidos. Nenhuma dependência nova e nenhuma aprovação fabricada.
