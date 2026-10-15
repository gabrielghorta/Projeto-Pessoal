"""Importação das planilhas oficiais — simulação por padrão, aplicação só com --aplicar.

  python importar.py              # SIMULAÇÃO: roda tudo numa cópia do banco e mostra o relatório; nada muda
  python importar.py --aplicar    # backup verificado → migração (se v1) → importação → auditoria, numa transação

Garantias:
  * nunca apaga o banco nem movimentos; o que sai de uma revisão fica com vigente = 0;
  * --aplicar faz backup verificado (backup.py) antes de tocar no banco e aborta se a verificação falhar;
  * qualquer erro desfaz a transação inteira (o banco volta ao estado anterior; o backup fica guardado);
  * reimportar os mesmos arquivos termina em SEM_ALTERACOES;
  * banco no esquema v1 (MVP) é migrado: tabelas antigas preservadas como v1_*, referências remapeadas.
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime

import backup
import importacao as I
import servicos as S

BASE = os.path.dirname(os.path.abspath(__file__))
DIR_RELATORIOS = os.path.join(BASE, "dados", "relatorios")
OPERACIONAIS = ["movimentos", "checkins", "checkin_presencas", "clima", "apontamentos", "apontamento_quantidades", "fotos",
                "execucao", "cadastro", "cadastro_historico", "ligacoes_prediais", "notas_fiscais", "nf_itens",
                "funcionarios", "maquinas", "medicoes", "medicao_lancamentos"]


def contar_operacionais(conn):
    tabelas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in OPERACIONAIS if t in tabelas}


def executar(caminho_db, modo, pasta_planilhas=I.DIR_PLANILHAS, backup_dir=None, cfg=None):
    """Roda a importação completa sobre `caminho_db`. Retorna o relatório (dict)."""
    cfg = cfg or I.carregar_config()
    conn = sqlite3.connect(caminho_db, isolation_level=None)
    conn.row_factory = sqlite3.Row
    versao = S.versao_banco(conn)
    antes = contar_operacionais(conn)
    conn.execute("PRAGMA foreign_keys = OFF" if versao == 1 else "PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA legacy_alter_table = ON")
    conn.execute("BEGIN")
    try:
        if versao == 1:
            I.preparar_v1(conn)
        else:
            S.aplicar_esquema(conn)
        imp = conn.execute("INSERT INTO importacoes(iniciada_em,modo,status,backup) VALUES (?,?,?,?)",
                           (S._agora(), modo, "EM_ANDAMENTO", backup_dir)).lastrowid
        imp_obj = I.Importador(conn, cfg, imp, pasta_planilhas)
        imp_obj.executar()
        migracao = I.remapear_v1(conn, imp) if versao == 1 else None
        aud = I.auditar(conn, cfg, imp)
        depois = contar_operacionais(conn)
        # tabelas v1_* são arquivo de auditoria (referências antigas preservadas como estavam)
        fk = [tuple(r) for r in conn.execute("PRAGMA foreign_key_check").fetchall() if not str(r[0]).startswith("v1_")]
        n_alt = conn.execute("SELECT COUNT(*) FROM alteracoes WHERE importacao_id=?", (imp,)).fetchone()[0]
        status = "SEM_ALTERACOES" if n_alt == 0 and versao == 2 else "CONCLUIDA"
        perdidos = {t: (antes[t], depois.get(t)) for t in antes if depois.get(t) != antes[t]}
        if perdidos:
            raise RuntimeError(f"Contagem de registros operacionais mudou: {perdidos}")
        if fk:
            raise RuntimeError(f"Violação de chave estrangeira após a importação: {fk[:5]}")
        rel = {
            "importacao_id": imp, "modo": modo, "status": status, "esquema_antes": versao, "esquema_depois": 2,
            "backup": backup_dir,
            "fontes": imp_obj.fontes,
            "colunas_06_2_localizadas_pelo_cabecalho": imp_obj.colunas_06_2,
            "conferencias": imp_obj.conferencias,
            "alteracoes": {e: dict(c) for e, c in imp_obj.stats.items()},
            "alteracoes_registradas": n_alt,
            "decisoes_novas": imp_obj.decisoes_novas,
            "registros_operacionais_preservados": depois,
            "migracao_v1": migracao,
            "auditoria": aud,
        }
        conn.execute("UPDATE importacoes SET concluida_em=?, status=?, relatorio=? WHERE id=?",
                     (S._agora(), status, json.dumps(rel, ensure_ascii=False, default=str), imp))
        conn.execute("COMMIT")
        return rel
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def simular(db, pasta_planilhas=I.DIR_PLANILHAS, cfg=None):
    """Executa sobre uma cópia temporária do banco (ou banco novo) e descarta a cópia."""
    tmp = tempfile.mkdtemp(prefix="simulacao_")
    copia = os.path.join(tmp, "simulacao.db")
    try:
        if os.path.exists(db):
            o, d = sqlite3.connect(db), sqlite3.connect(copia)
            o.backup(d)
            d.close()
            o.close()
        return executar(copia, "SIMULACAO", pasta_planilhas, cfg=cfg)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def aplicar(db, pasta_planilhas=I.DIR_PLANILHAS, destino_backup=None, dir_fotos=None, cfg=None):
    """Backups ficam em <pasta do banco>/backups e as fotos copiadas são <pasta do banco>/fotos."""
    base_db = os.path.dirname(os.path.abspath(db))
    destino_backup = destino_backup or os.path.join(base_db, "backups")
    dir_fotos = dir_fotos or os.path.join(base_db, "fotos")
    pasta = None
    if os.path.exists(db):
        pasta = backup.criar(db, destino_backup, dir_fotos, rotulo="antes_importacao")   # já verificado; lança se falhar
    return executar(db, "APLICACAO", pasta_planilhas, pasta, cfg=cfg)


def imprimir(rel):
    a = rel["auditoria"]
    print(f"\n=== IMPORTAÇÃO — {rel['modo']} — {rel['status']} (esquema v{rel['esquema_antes']} → v2) ===")
    if rel["backup"]:
        print(f"Backup verificado: {rel['backup']}")
    for k, f in rel["fontes"].items():
        print(f"  fonte {k:<10} {f['revisao'] or '-':<6} sha256 {f['sha256'][:16]}…  {f['nome']}")
    print("\nAlterações por entidade:")
    for e, c in sorted(rel["alteracoes"].items()):
        print(f"  {e:<14} " + "  ".join(f"{k} {v}" for k, v in sorted(c.items())))
    print("\nContagens (vigentes):")
    for k, c in a["contagens"].items():
        print(f"  [{'OK ' if c['ok'] else 'ERRO'}] {k:<12} esperado {c['esperado']!s:<28} obtido {c['obtido']}")
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
    print(f"Registros operacionais preservados: {rel['registros_operacionais_preservados']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=S.DB_PADRAO)
    ap.add_argument("--aplicar", action="store_true", help="aplica no banco (com backup verificado antes)")
    ap.add_argument("--json", help="grava o relatório completo neste arquivo")
    a = ap.parse_args()
    rel = aplicar(a.db) if a.aplicar else simular(a.db)
    imprimir(rel)
    os.makedirs(DIR_RELATORIOS, exist_ok=True)
    destino = a.json or os.path.join(DIR_RELATORIOS, f"importacao_{rel['modo'].lower()}_{datetime.now():%Y%m%d-%H%M%S}.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(rel, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nRelatório completo: {destino}")
    if not a.aplicar:
        print("SIMULAÇÃO: nenhum dado foi alterado. Para aplicar: python importar.py --aplicar")
    ok = rel["auditoria"]["contagens_ok"] and rel["auditoria"]["totalizacao_bm"]["ok"]
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
