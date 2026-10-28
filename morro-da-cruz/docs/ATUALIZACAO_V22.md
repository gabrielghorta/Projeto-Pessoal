# Instalar a atualização v22

Ramo de trabalho: `codex/solicitacoes-recebimento-mapa`. Base: `claude/powerbi-modifications-wqxekj`, já com o PR #14 incorporado. Estas instruções são para depois da revisão e do merge do novo PR.

## PythonAnywhere

No console Bash, atualize o código:

```bash
cd ~/Projeto-Pessoal
git pull --ff-only origin claude/powerbi-modifications-wqxekj
```

Na aba **Web**, clique em **Reload**. O primeiro acesso faz a migração v22 com o backup verificado que já faz parte da inicialização do site. Não há dependência de produção nova. Não rode importação manual com o site atendendo.

## Notas liberadas pela regra nova

O relatório JSON da migração inclui `notas_liberadas_v22`. A consulta abaixo lista a auditoria do banco padrão, sem alterá-lo. Use o caminho configurado no seu site se ele for diferente de `dados_demo/obra.db`.

```bash
cd ~/Projeto-Pessoal/morro-da-cruz
python3.13 - <<'PY'
import json, sqlite3
with sqlite3.connect('file:dados_demo/obra.db?mode=ro', uri=True) as c:
    c.row_factory = sqlite3.Row
    notas = [dict(r) for r in c.execute('''
        SELECT n.numero, n.serie, l.material_id, l.quantidade, l.registrada_em
        FROM nf_liberadas_v22 l JOIN notas_fiscais n ON n.id=l.nf_id
        ORDER BY n.id, l.material_id
    ''')]
print(json.dumps(notas, ensure_ascii=False, indent=2))
PY
```

Anexe essa lista ao registro da implantação. A NF 18734 utilizada na validação é sintética; não foi alterada nenhuma nota do site durante o desenvolvimento.

## Uso após atualizar

- Almoxarife: pode solicitar material e receber linhas desconhecidas pela descrição. A parte reconhecida fica disponível; a engenharia resolve a identificação restante.
- Encarregado e supervisor: usam **Pedir material**, sem acesso a notas fiscais.
- Engenharia/administração: aprovam solicitações de outra pessoa e identificam somente exceções da nota. Em **Dados da obra**, escolhem a zona para somar trechos com toques. Em **Apontamento sem NS**, escolhem data/equipe e tocam nos alvos sugeridos.
- Lançamento de vários alvos a 100% ficou como proposta D-181; cada botão abre o formulário individual, mantendo todas as validações atuais.
