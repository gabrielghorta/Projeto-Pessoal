"""Importação das planilhas oficiais — simulação por padrão, aplicação só com --aplicar.

  python importar.py              # SIMULAÇÃO: roda tudo numa cópia do banco e mostra o relatório; nada muda
  python importar.py --aplicar    # trava de manutenção → backup verificado → migração → importação → conferências
                                  # → COMMIT só se nenhuma conferência impeditiva reprovar

Garantias:
  * nunca apaga o banco nem movimentos; o que sai de uma revisão fica com vigente = 0;
  * --aplicar faz backup verificado e COMPLETO (banco + fotos referenciadas) antes de tocar no banco;
  * as conferências são avaliadas ANTES do COMMIT. Se alguma reprovar, a transação é desfeita e o banco
    fica byte a byte igual. O relatório da reprovação fica em dados/relatorios/:
      - controles aprovados para estes arquivos (config/controles.json): contagens, unidades, agrupamento;
      - totalização do BM igual ao rodapé da própria planilha;
      - pendências impeditivas de identidade (nome × geometria, retirada de objeto com histórico, conciliação inválida);
  * reimportar os mesmos arquivos termina em SEM_ALTERACOES;
  * banco em esquema anterior (v1 do MVP, v2 a v6) é migrado sem perda.
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import traceback
from datetime import datetime

import caminhos
import backup
import importacao as I
import servicos as S

BASE = caminhos.PASTA
DIR_RELATORIOS = os.path.join(BASE, "dados", "relatorios")
OPERACIONAIS = ["movimentos", "checkins", "checkin_presencas", "clima", "apontamentos", "apontamento_quantidades", "fotos",
                "execucao", "cadastro", "cadastro_historico", "ligacoes_prediais", "notas_fiscais", "nf_itens",
                "funcionarios", "maquinas", "medicoes", "medicao_lancamentos", "reservas", "estornos", "custodia_declarada",
                "retificacoes", "reserva_ajustes", "intervalos_execucao", "soldas",
                "conciliacoes_legado", "conciliacao_legado_apontamentos", "retificacoes_intervalos", "revisoes_cadastro",
                "usuarios", "auditoria", "etapas_complementares", "ocorrencias",
                "fornecedores", "documentos", "solicitacoes_compra", "solicitacao_itens", "pedidos_compra", "pedido_itens",
                "nf_linhas", "recebimentos", "recebimento_itens", "inspecoes", "devolucoes_fornecedor", "transferencias",
                "inventarios", "inventario_itens", "programacoes", "programacao_materiais", "conferencias_medicao",
                "notas_servico", "ns_segmentos"]


class ImportacaoReprovada(RuntimeError):
    """Conferência impeditiva reprovada: a transação foi desfeita. `relatorio` traz os motivos."""

    def __init__(self, relatorio):
        super().__init__(f"Importação REPROVADA ({len(relatorio['bloqueios'])} bloqueio(s)); banco não alterado. "
                         f"Relatório: {relatorio.get('arquivo_relatorio')}")
        self.relatorio = relatorio


def contar_operacionais(conn):
    tabelas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in OPERACIONAIS if t in tabelas}


def _gravar_relatorio(rel, dir_relatorios):
    os.makedirs(dir_relatorios, exist_ok=True)
    destino = os.path.join(dir_relatorios, f"importacao_{rel['modo'].lower()}_{rel['status'].lower()}_"
                                           f"{datetime.now():%Y%m%d-%H%M%S-%f}.json")
    rel["arquivo_relatorio"] = destino
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(rel, f, ensure_ascii=False, indent=2, default=str)
    return destino


def executar(caminho_db, modo, pasta_planilhas=I.DIR_PLANILHAS, backup_dir=None, cfg=None, dir_relatorios=DIR_RELATORIOS,
             dir_fotos=None):
    """Roda a importação completa sobre `caminho_db` numa transação.

    Retorna o relatório (dict). Se uma conferência impeditiva reprovar, faz ROLLBACK, grava o
    relatório de reprovação e lança ImportacaoReprovada. Erro inesperado também faz ROLLBACK e
    grava relatório FALHOU.
    """
    cfg = cfg or I.carregar_config()
    existia = os.path.exists(caminho_db)
    conn = sqlite3.connect(caminho_db, isolation_level=None)
    conn.row_factory = sqlite3.Row
    versao = S.versao_banco(conn)
    antes = contar_operacionais(conn)
    # Migração de esquema roda com as chaves estrangeiras desligadas, como manda o procedimento do SQLite: há migrações que
    # recriam tabelas (v1; notas_fiscais/movimentos na v11; retificacoes_intervalos na v17; documentos na v18) e, com as
    # chaves ligadas, renomear a tabela antiga reescreveria as referências das outras tabelas para o nome provisório, que
    # depois é descartado. A integridade é conferida por PRAGMA foreign_key_check antes do COMMIT e qualquer violação
    # reprova a importação inteira. Banco já no esquema atual: chaves ligadas.
    conn.execute("PRAGMA foreign_keys = OFF" if 0 < versao < S.VERSAO_ESQUEMA else "PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA legacy_alter_table = ON")
    base_rel = {"modo": modo, "esquema_antes": versao, "esquema_depois": S.VERSAO_ESQUEMA, "backup": backup_dir,
                "banco": os.path.abspath(caminho_db), "planilhas": os.path.abspath(pasta_planilhas)}
    conn.execute("BEGIN")
    try:
        congeladas = []
        if versao == 1:
            I.preparar_v1(conn)
        elif versao == 2:
            I.preparar_v3(conn)
        if 0 < versao < 4:
            I.preparar_v4(conn)
        if 0 < versao < 5:
            I.preparar_v5(conn)
        if 0 < versao < 6:
            I.preparar_v6(conn)
        if 0 < versao < 7:
            I.preparar_v7(conn)
        if 0 < versao < 8:
            I.preparar_v8(conn)
        if 0 < versao < 9:
            I.preparar_v9(conn)
        if 0 < versao < 10:
            I.preparar_v10(conn)
        if 0 < versao < 11:
            I.preparar_v11(conn)
        if 0 < versao < 12:
            I.preparar_v12(conn)
        if 0 < versao < 13:
            I.preparar_v13(conn)
        if 0 < versao < 14:
            I.preparar_v14(conn)
        if 0 < versao < 15:
            I.preparar_v15(conn)
        if 0 < versao < 16:
            I.preparar_v16(conn)
        if 0 < versao < 17:
            I.preparar_v17(conn)
        if 0 < versao < 18:
            I.preparar_v18(conn)
        S.aplicar_esquema(conn)
        if versao in (1, 2):
            congeladas = I.congelar_fechadas(conn)        # antes de o novo BM entrar
        imp = conn.execute("INSERT INTO importacoes(iniciada_em,modo,status,backup) VALUES (?,?,?,?)",
                           (S._agora(), modo, "EM_ANDAMENTO", backup_dir)).lastrowid
        imp_obj = I.Importador(conn, cfg, imp, pasta_planilhas)
        imp_obj.executar()
        migracao = I.remapear_v1(conn, imp) if versao == 1 else None
        fotos_revalidadas = S.revalidar_fotos(conn, dir_fotos or os.path.join(os.path.dirname(os.path.abspath(caminho_db)), "fotos"))
        aud = I.auditar(conn, cfg, imp, imp_obj.fontes, imp_obj.conferencias, modo)
        depois = contar_operacionais(conn)
        # tabelas v1_* são arquivo de auditoria (referências antigas preservadas como estavam)
        fk = [tuple(r) for r in conn.execute("PRAGMA foreign_key_check").fetchall() if not str(r[0]).startswith("v1_")]
        n_alt = conn.execute("SELECT COUNT(*) FROM alteracoes WHERE importacao_id=?", (imp,)).fetchone()[0]
        perdidos = {t: (antes[t], depois.get(t)) for t in antes if depois.get(t) != antes[t]}
        bloqueios = imp_obj.bloqueios + aud["bloqueios"]
        if perdidos:
            bloqueios.append({"tipo": "REGISTROS_OPERACIONAIS_ALTERADOS", "referencia": "contagem", "detalhe": str(perdidos)})
        if fk:
            bloqueios.append({"tipo": "CHAVE_ESTRANGEIRA_VIOLADA", "referencia": "foreign_key_check", "detalhe": str(fk[:5])})
        if bloqueios:
            status = "REPROVADA"
        elif aud["avisos_controle"]:                 # só na simulação: conferência ainda não confirmada
            status = "SIMULADA_SEM_CONTROLE_APROVADO"
        else:
            status = "SEM_ALTERACOES" if n_alt == 0 and versao == S.VERSAO_ESQUEMA else "CONCLUIDA"
        rel = {
            "importacao_id": imp, **base_rel, "status": status,
            "bloqueios": bloqueios,
            "fontes": imp_obj.fontes,
            "colunas_06_2_localizadas_pelo_cabecalho": imp_obj.colunas_06_2,
            "conferencias": imp_obj.conferencias,
            "alteracoes": {e: dict(c) for e, c in imp_obj.stats.items()},
            "alteracoes_registradas": n_alt,
            "decisoes_novas": imp_obj.decisoes_novas,
            "medicoes_congeladas_na_migracao": congeladas,
            "fotos_revalidadas": fotos_revalidadas,
            "registros_operacionais_preservados": depois,
            "migracao_v1": migracao,
            "pendencias": [dict(r) for r in conn.execute(
                "SELECT tipo, referencia, detalhe, bloqueante FROM pendencias_importacao WHERE importacao_id=? ORDER BY id",
                (imp,))],
            "auditoria": aud,
        }
        if bloqueios:
            conn.execute("ROLLBACK")
            rel["resultado"] = "Transação desfeita: o banco não foi alterado."
            _gravar_relatorio(rel, dir_relatorios)
            raise ImportacaoReprovada(rel)
        conn.execute("UPDATE importacoes SET concluida_em=?, status=?, relatorio=? WHERE id=?",
                     (S._agora(), status, json.dumps(rel, ensure_ascii=False, default=str), imp))
        conn.execute("COMMIT")
        _gravar_relatorio(rel, dir_relatorios)
        return rel
    except ImportacaoReprovada:
        raise
    except Exception as e:
        conn.execute("ROLLBACK")
        _gravar_relatorio({**base_rel, "status": "FALHOU", "bloqueios": [], "erro": f"{type(e).__name__}: {e}",
                           "traceback": traceback.format_exc(),
                           "resultado": "Transação desfeita: o banco não foi alterado."}, dir_relatorios)
        raise
    finally:
        conn.close()
        if not existia and os.path.exists(caminho_db) and os.path.getsize(caminho_db) == 0:
            os.remove(caminho_db)                      # primeira carga desfeita: não deixa banco vazio para trás


def simular(db, pasta_planilhas=I.DIR_PLANILHAS, cfg=None, dir_relatorios=DIR_RELATORIOS):
    """Executa sobre uma cópia temporária do banco (ou banco novo) e descarta a cópia."""
    tmp = tempfile.mkdtemp(prefix="simulacao_")
    copia = os.path.join(tmp, "simulacao.db")
    try:
        if os.path.exists(db):
            backup.copiar_banco(db, copia)
        # fotos: as do banco original (a cópia temporária não tem pasta de fotos)
        return executar(copia, "SIMULACAO", pasta_planilhas, cfg=cfg, dir_relatorios=dir_relatorios,
                        dir_fotos=os.path.join(os.path.dirname(os.path.abspath(db)), "fotos"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def aplicar(db, pasta_planilhas=I.DIR_PLANILHAS, destino_backup=None, dir_fotos=None, cfg=None,
            dir_relatorios=DIR_RELATORIOS, aceitar_backup_incompleto=False):
    """Com a trava de manutenção: backup verificado e completo → importação numa transação.
    Backups ficam em <pasta do banco>/backups e as fotos copiadas são <pasta do banco>/fotos."""
    base_db = os.path.dirname(os.path.abspath(db))
    destino_backup = destino_backup or os.path.join(base_db, "backups")
    dir_fotos = dir_fotos or os.path.join(base_db, "fotos")
    backup.exigir_servidor_parado(base_db, "A aplicação da importação")
    with backup.trava_manutencao(base_db, "importação"):
        pasta = None
        if os.path.exists(db):
            # lança RuntimeError (não íntegro) ou BackupIncompleto (anexo ausente) — a importação não começa
            pasta = backup.criar(db, destino_backup, dir_fotos, rotulo="antes_importacao",
                                 permitir_incompleto=aceitar_backup_incompleto, trava=False)
        rel = executar(db, "APLICACAO", pasta_planilhas, pasta, cfg=cfg, dir_relatorios=dir_relatorios, dir_fotos=dir_fotos)
        if pasta:
            rel["backup_completo"] = backup.verificar_detalhado(pasta)["completo"]
        return rel


def imprimir(rel):
    a = rel["auditoria"]
    print(f"\n=== IMPORTAÇÃO — {rel['modo']} — {rel['status']} (esquema v{rel['esquema_antes']} → v{rel['esquema_depois']}) ===")
    if rel.get("backup"):
        print(f"Backup verificado: {rel['backup']}")
    for k, f in rel["fontes"].items():
        print(f"  fonte {k:<10} {f['revisao'] or '-':<6} sha256 {f['sha256'][:16]}…  {f['nome']}")
    print("\nAlterações por entidade:")
    for e, c in sorted(rel["alteracoes"].items()):
        print(f"  {e:<14} " + "  ".join(f"{k} {v}" for k, v in sorted(c.items())))
    print(f"\nControles: {a['controle_aplicado'] or 'NENHUM conjunto para estes arquivos'} — situação {a['controle_situacao']}")
    if a["controle_situacao"] == "APROVADO":
        ap = a["controle_aprovacao"]
        print(f"  aprovado por {ap['por']} em {ap['em']}")
    for x in a["avisos_controle"] if not rel["bloqueios"] else []:
        print(f"  [AVISO {x['tipo']}] {x['detalhe']}")
    if a["avisos_controle"] and rel["modo"] == "SIMULACAO":
        print("  SIMULAÇÃO: a conferência NÃO está confirmada; a aplicação será recusada até o conjunto estar completo e aprovado.")
    for k, c in a["contagens"].items():
        print(f"  [{'OK ' if c['ok'] else 'ERRO'}] {k:<30} esperado {c['esperado']!s:<28} obtido {c['obtido']}")
    t = a["totalizacao_bm"]
    print(f"\nTotalização do BM na ordem das células: {'OK' if t['ok'] else 'DIVERGE'} — "
          f"sistema P0 {t['sistema']['p0']:.7f} × célula {t['celulas_bm']['p0_bm']:.7f}")
    tc = a["total_contratual"]
    print(f"Total contratual: contrato {tc['contrato_3_1']:.2f} × BM {tc['bm_p0']:.7f} → {tc['situacao']} ({tc['diferenca']:+.7f})")
    print("\nUnidades da 06.2 (com fonte na Juntada; PENDENTE = sem fonte):")
    for u, d in a["unidades_06_2"].items():
        print(f"  {u:<9} {d['linhas']:>5} linhas   quantidade {d['quantidade']}")
    print(f"Enquadramento BM (BA): {a['enquadramento_bm_BA']}")
    print(f"Avisos de origem (AA/AB × AW): {a['avisos_AA_AB_AW']}")
    print(f"Decisões registradas: {a['decisoes_registradas']} (novas nesta importação: {rel['decisoes_novas']})")
    print(f"Pendências da importação: {a['pendencias_importacao'] or 'nenhuma'}")
    if rel["migracao_v1"] is not None:
        print(f"Migração v1: {rel['migracao_v1']}")
    if rel["medicoes_congeladas_na_migracao"]:
        print(f"Medições fechadas congeladas na migração: {rel['medicoes_congeladas_na_migracao']}")
    print(f"Registros operacionais preservados: {rel['registros_operacionais_preservados']}")
    if rel["bloqueios"]:
        print(f"\n*** REPROVADA — {len(rel['bloqueios'])} bloqueio(s); transação desfeita, banco NÃO alterado ***")
        for b in rel["bloqueios"]:
            print(f"  [{b['tipo']}] {b['referencia']}: {b['detalhe']}")
    if a.get("modelo_controles"):
        print("\nModelo de conjunto de controles (conferir na fonte antes de copiar para config/controles.json;"
              " a aprovação fica PENDENTE até a pessoa responsável preenchê-la):")
        print(json.dumps(a["modelo_controles"], ensure_ascii=False, indent=2))


def main():
    backup.utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=S.DB_PADRAO)
    ap.add_argument("--aplicar", action="store_true", help="aplica no banco (com backup verificado antes)")
    ap.add_argument("--aceitar-backup-incompleto", action="store_true",
                    help="prossegue mesmo com foto referenciada ausente (o backup fica marcado INCOMPLETO)")
    a = ap.parse_args()
    try:
        rel = (aplicar(a.db, aceitar_backup_incompleto=a.aceitar_backup_incompleto) if a.aplicar else simular(a.db))
    except ImportacaoReprovada as e:
        imprimir(e.relatorio)
        print(f"\nRelatório da reprovação: {e.relatorio['arquivo_relatorio']}")
        sys.exit(2)
    except (backup.BackupIncompleto, backup.EmManutencao) as e:
        print(f"Importação não iniciada: {e}")
        sys.exit(3)
    imprimir(rel)
    print(f"\nRelatório completo: {rel['arquivo_relatorio']}")
    if not a.aplicar:
        print("SIMULAÇÃO: nenhum dado foi alterado. Para aplicar: python importar.py --aplicar")


if __name__ == "__main__":
    main()
