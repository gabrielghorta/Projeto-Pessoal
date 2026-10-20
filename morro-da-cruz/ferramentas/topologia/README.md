# Ferramentas de topologia dos trechos

Diagnóstico das pontas dos trechos (ponta no nó, cruzamento, passagem, emendas sem nó) e geração do arquivo de decisões `config/topologia.json`, que o sistema lê (`topologia.py`). A regra, os números e a revisão estão em `docs/TOPOLOGIA_TRECHOS.md`.

```
python ferramentas/topologia/diagnostico.py            # mede e grava os CSVs em saida/ (nada mais muda)
python ferramentas/topologia/diagnostico.py --gravar   # ... e regrava config/topologia.json (mantém as decisões revisadas)
python ferramentas/topologia/diagnostico.py --banco dados/morro_da_cruz.db   # usa um banco já carregado
python ferramentas/topologia/recortes.py               # uma imagem por junção, em saida/recortes/
python ferramentas/topologia/recortes.py --cego        # sem a decisão no título (revisão independente)
python ferramentas/topologia/recortes.py --no Zona03_PB08_Rede_NÓ113.1
```

Sem `--banco`, o diagnóstico monta um banco descartável a partir de `planilhas/`, pelo mesmo caminho dos testes. O mapa, as planilhas e o banco nunca são alterados.

| Arquivo | O que faz |
|---|---|
| `base.py` | Carrega o mapa (pelo próprio `mapa_geral`), o banco, os nós e as peças. Também tem o orçamento de peças (`portas`) e a direção das pontas. |
| `juncoes.py` | Decide cada junção: cruzamento, passagem ao lado do nó, divisa de zona, limite MND e emenda sem nó. |
| `diagnostico.py` | Etapas 5.1 a 5.5. Grava `saida/*.csv` e `saida/resumo.json` e, com `--gravar`, `config/topologia.json`. |
| `recortes.py` | Gera recortes das pranchas embutidas no HTML para conferir cada junção. |

Saídas:

* `cruzamentos.csv`: uma linha por candidato a junção, com os sinais e a decisão.
* `cadeias.csv`: cada trecho físico com mais de uma linha, um membro por linha do arquivo.
* `pontas_fora_do_no.csv`: as pontas que não estão no nó.
* `resumo.json`: os números do diagnóstico.

O `pontas.csv` completo (2.872 pontas) fica fora do Git, na pasta de trabalho do Drive `07_IA_CHATGPT_E_CLAUDE/topologia_trechos_2026-10-20`, dentro de `pontas_completo.zip`. Os recortes também ficam fora do Git e se geram de novo com `recortes.py`.
