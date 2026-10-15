"""Backup verificável do banco e dos arquivos operacionais (fotos).

Uso:
  python backup.py criar      [--db dados/morro_da_cruz.db] [--destino dados/backups]
  python backup.py verificar  <pasta-do-backup>
  python backup.py restaurar  <pasta-do-backup> [--db dados/morro_da_cruz.db]

O banco é copiado pela API de backup do SQLite (cópia consistente mesmo com o servidor aberto).
O manifesto registra SHA-256 e tamanho de cada arquivo, contagem de linhas por tabela e o
resultado de PRAGMA integrity_check. `verificar` recalcula tudo e falha se algo divergir.
Backups nunca são apagados por este programa.
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PADRAO = os.path.join(BASE, "dados", "morro_da_cruz.db")
DIR_FOTOS = os.path.join(BASE, "dados", "fotos")
DESTINO_PADRAO = os.path.join(BASE, "dados", "backups")
MANIFESTO = "manifesto.json"


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def contagens(caminho_db):
    c = sqlite3.connect(f"file:{caminho_db}?mode=ro", uri=True)
    try:
        integridade = c.execute("PRAGMA integrity_check").fetchone()[0]
        tabelas = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        linhas = {t: c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tabelas}
    finally:
        c.close()
    return integridade, linhas


def criar(db=DB_PADRAO, destino=DESTINO_PADRAO, dir_fotos=DIR_FOTOS, rotulo=None):
    """Cria e verifica um backup. Retorna a pasta. Lança RuntimeError se a verificação falhar."""
    if not os.path.exists(db):
        raise RuntimeError(f"Banco {db} não existe — nada a copiar.")
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    pasta = os.path.join(destino, carimbo + (f"_{rotulo}" if rotulo else ""))
    os.makedirs(pasta, exist_ok=False)
    alvo_db = os.path.join(pasta, os.path.basename(db))
    origem = sqlite3.connect(db)
    copia = sqlite3.connect(alvo_db)
    try:
        origem.backup(copia)
    finally:
        copia.close()
        origem.close()
    arquivos = [os.path.basename(db)]
    if os.path.isdir(dir_fotos):
        shutil.copytree(dir_fotos, os.path.join(pasta, "fotos"))
        for raiz, _, nomes in os.walk(os.path.join(pasta, "fotos")):
            arquivos += [os.path.relpath(os.path.join(raiz, n), pasta) for n in sorted(nomes)]
    integridade, linhas = contagens(alvo_db)
    if integridade != "ok":
        raise RuntimeError(f"Cópia do banco falhou no integrity_check: {integridade}")
    manifesto = {
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "banco_origem": os.path.abspath(db),
        "fotos_origem": os.path.abspath(dir_fotos) if os.path.isdir(dir_fotos) else None,
        "integrity_check": integridade,
        "linhas_por_tabela": linhas,
        "arquivos": {a: {"sha256": sha256(os.path.join(pasta, a)), "bytes": os.path.getsize(os.path.join(pasta, a))}
                     for a in arquivos},
    }
    # as fotos de origem precisam ser idênticas às copiadas
    if manifesto["fotos_origem"]:
        for a, info in manifesto["arquivos"].items():
            if a.startswith("fotos" + os.sep) and sha256(os.path.join(dir_fotos, a[len("fotos") + 1:])) != info["sha256"]:
                raise RuntimeError(f"Foto {a} divergiu durante a cópia.")
    with open(os.path.join(pasta, MANIFESTO), "w", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=2)
    ok, erros = verificar(pasta)
    if not ok:
        raise RuntimeError("Backup criado mas não verificou: " + "; ".join(erros))
    return pasta


def verificar(pasta):
    """Recalcula hashes, tamanhos, integridade e contagens. Retorna (ok, lista_de_erros)."""
    erros = []
    caminho = os.path.join(pasta, MANIFESTO)
    if not os.path.exists(caminho):
        return False, ["manifesto.json ausente"]
    with open(caminho, encoding="utf-8") as f:
        m = json.load(f)
    for a, info in m["arquivos"].items():
        p = os.path.join(pasta, a)
        if not os.path.exists(p):
            erros.append(f"{a}: ausente")
        elif os.path.getsize(p) != info["bytes"] or sha256(p) != info["sha256"]:
            erros.append(f"{a}: hash/tamanho diverge")
    db = os.path.join(pasta, os.path.basename(m["banco_origem"]))
    if os.path.exists(db):
        integridade, linhas = contagens(db)
        if integridade != "ok":
            erros.append(f"integrity_check: {integridade}")
        if linhas != m["linhas_por_tabela"]:
            erros.append("contagem de linhas diverge do manifesto")
    return not erros, erros


def restaurar(pasta, db=DB_PADRAO, dir_fotos=DIR_FOTOS):
    """Volta o banco ao estado do backup. Nada é apagado: o banco atual é guardado ao lado como
    <nome>.substituido-<data>; fotos do backup ausentes ou diferentes são copiadas de volta e fotos
    novas (posteriores ao backup) são mantidas."""
    ok, erros = verificar(pasta)
    if not ok:
        raise RuntimeError("Backup não verificou; restauração cancelada: " + "; ".join(erros))
    with open(os.path.join(pasta, MANIFESTO), encoding="utf-8") as f:
        m = json.load(f)
    origem = os.path.join(pasta, os.path.basename(m["banco_origem"]))
    guardado = None
    if os.path.exists(db):
        guardado = f"{db}.substituido-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(db, guardado)
    o, d = sqlite3.connect(origem), sqlite3.connect(db)
    try:
        o.backup(d)
    finally:
        d.close()
        o.close()
    fotos_bkp = os.path.join(pasta, "fotos")
    if os.path.isdir(fotos_bkp):
        for raiz, _, nomes in os.walk(fotos_bkp):
            for n in nomes:
                rel = os.path.relpath(os.path.join(raiz, n), fotos_bkp)
                alvo = os.path.join(dir_fotos, rel)
                if not os.path.exists(alvo) or sha256(alvo) != sha256(os.path.join(raiz, n)):
                    os.makedirs(os.path.dirname(alvo), exist_ok=True)
                    shutil.copy2(os.path.join(raiz, n), alvo)
    if contagens(db)[1] != m["linhas_por_tabela"]:
        raise RuntimeError("Banco restaurado não confere com o manifesto.")
    return guardado


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("criar")
    c.add_argument("--db", default=DB_PADRAO)
    c.add_argument("--destino", default=DESTINO_PADRAO)
    v = sub.add_parser("verificar")
    v.add_argument("pasta")
    r = sub.add_parser("restaurar")
    r.add_argument("pasta")
    r.add_argument("--db", default=DB_PADRAO)
    a = ap.parse_args()
    if a.cmd == "criar":
        pasta = criar(a.db, a.destino)
        print(f"Backup verificado: {pasta}")
    elif a.cmd == "restaurar":
        guardado = restaurar(a.pasta, a.db, os.path.join(os.path.dirname(os.path.abspath(a.db)), "fotos"))
        print(f"Banco restaurado de {a.pasta}." + (f" Banco anterior guardado em {guardado}" if guardado else ""))
    else:
        ok, erros = verificar(a.pasta)
        print("OK — backup íntegro" if ok else "FALHOU:\n  " + "\n  ".join(erros))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
