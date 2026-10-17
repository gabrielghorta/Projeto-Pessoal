"""Backup verificável do banco e dos anexos (fotos e documentos).

Uso:
  python backup.py criar      [--db dados/morro_da_cruz.db] [--destino dados/backups] [--permitir-incompleto]
  python backup.py verificar  <pasta-do-backup>
  python backup.py restaurar  <pasta-do-backup> [--db dados/morro_da_cruz.db]

* O banco é copiado pela API de backup do SQLite: a cópia é consistente e inclui o que estiver no WAL.
* Primeiro se copia o banco; depois, as fotos. Assim toda foto referenciada na cópia já existia no disco
  (o servidor grava o arquivo antes da linha em `fotos`).
* Duas verificações separadas:
  - integridade: hash e tamanho de cada arquivo, `integrity_check`, linhas e conteúdo de cada tabela;
  - completude: toda foto referenciada no banco copiado está na cópia.
  Backup incompleto é guardado, mas marcado INCOMPLETO e reprovado na verificação.
* Backup, restauração e importação rodam com a trava de manutenção (MANUTENCAO.lock ao lado do banco).
  Com a trava, o servidor recusa gravações.
* Backups nunca são apagados por este programa.
"""
import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime

import caminhos

BASE = caminhos.PASTA
DB_PADRAO = os.path.join(BASE, "dados", "morro_da_cruz.db")
DIR_FOTOS = os.path.join(BASE, "dados", "fotos")
DESTINO_PADRAO = os.path.join(BASE, "dados", "backups")
MANIFESTO = "manifesto.json"
TRAVA = "MANUTENCAO.lock"
MARCA_SERVIDOR = "SERVIDOR_ATIVO.json"


class BackupIncompleto(RuntimeError):
    """Backup íntegro, mas sem todos os anexos referenciados no banco. A pasta fica guardada."""

    def __init__(self, pasta, ausentes):
        super().__init__(f"Backup INCOMPLETO em {pasta}: {len(ausentes)} anexo(s) referenciado(s) no banco e ausente(s): "
                         + ", ".join(ausentes[:10]))
        self.pasta, self.ausentes = pasta, ausentes


class EmManutencao(RuntimeError):
    """Outra operação de manutenção (backup, restauração ou importação) está em andamento."""


def utf8_console():
    """Saída em UTF-8 mesmo com a saída redirecionada no Windows (cp1252 não tem '→', '✓' etc.)."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


class ServidorAtivo(EmManutencao):
    """Importação e restauração exigem o servidor parado (limitação de concorrência desta versão)."""


def marcar_servidor(pasta_db, host, porta):
    """O servidor registra onde está escutando; removido ao encerrar."""
    p = os.path.join(pasta_db, MARCA_SERVIDOR)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "host": host, "porta": porta,
                   "desde": datetime.now().isoformat(timespec="seconds")}, f)
    return p


def servidor_ativo(pasta_db):
    """Há servidor do sistema respondendo para este banco? (marca + porta aceitando conexão; marca órfã não conta)."""
    p = os.path.join(pasta_db, MARCA_SERVIDOR)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            m = json.load(f)
        with socket.create_connection((m["host"], int(m["porta"])), timeout=0.5):
            return m
    except (OSError, ValueError, KeyError):
        return None


def exigir_servidor_parado(pasta_db, operacao):
    m = servidor_ativo(pasta_db)
    if m:
        raise ServidorAtivo(f"{operacao} exige o servidor parado: há um servidor em http://{m['host']}:{m['porta']} "
                            f"(pid {m['pid']}, desde {m['desde']}). Encerre-o (Ctrl+C), aguarde as operações em curso "
                            "e repita.")


def caminho_trava(pasta_db):
    return os.path.join(pasta_db, TRAVA)


def em_manutencao(pasta_db):
    return os.path.exists(caminho_trava(pasta_db))


@contextmanager
def trava_manutencao(pasta_db, operacao):
    """Cria MANUTENCAO.lock de forma exclusiva; o servidor recusa gravações enquanto ela existir."""
    os.makedirs(pasta_db, exist_ok=True)
    p = caminho_trava(pasta_db)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        with open(p, encoding="utf-8", errors="replace") as f:
            dono = f.read().strip()
        raise EmManutencao(f"Manutenção em andamento ({dono}). Se nenhuma operação estiver rodando, apague {p}.") from None
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"{operacao} · pid {os.getpid()} · {datetime.now().isoformat(timespec='seconds')}")
    try:
        yield
    finally:
        os.remove(p)


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _ler(caminho_db):
    return sqlite3.connect(f"file:{caminho_db}?mode=ro", uri=True)


def contagens(caminho_db):
    c = _ler(caminho_db)
    try:
        integridade = c.execute("PRAGMA integrity_check").fetchone()[0]
        tabelas = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        linhas = {t: c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tabelas}
    finally:
        c.close()
    return integridade, linhas


def conteudo(caminho_db):
    """SHA-256 do conteúdo de cada tabela (linhas em ordem de rowid). Confere valores e vínculos, não só contagens."""
    c = _ler(caminho_db)
    try:
        out = {}
        for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            h = hashlib.sha256()
            for row in c.execute(f'SELECT * FROM "{t}" ORDER BY rowid'):
                h.update(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
                h.update(b"\n")
            out[t] = h.hexdigest()
        return out
    finally:
        c.close()


# Anexos gravados em disco pelo sistema: pasta (ao lado do banco) → tabela com a coluna `arquivo` (e `sha256`)
ANEXOS = (("fotos", "fotos"), ("documentos", "documentos"))


def _pastas_anexos(dir_fotos):
    """{subpasta: caminho} — fotos em dir_fotos; documentos na pasta irmã (<pasta do banco>/documentos)."""
    return {"fotos": dir_fotos, "documentos": os.path.join(os.path.dirname(os.path.abspath(dir_fotos)), "documentos")}


def anexos_referenciados(caminho_db):
    """Anexos citados no banco, como 'fotos/<arquivo>' e 'documentos/<arquivo>'."""
    c = _ler(caminho_db)
    try:
        tabelas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return sorted({f"{pasta}/{r[0]}" for pasta, tab in ANEXOS if tab in tabelas
                       for r in c.execute(f"SELECT arquivo FROM {tab} WHERE arquivo IS NOT NULL")})
    finally:
        c.close()


def hashes_registrados(caminho_db):
    """{'fotos/<arquivo>': sha256, 'documentos/<arquivo>': sha256} dos anexos com hash registrado no banco."""
    c = _ler(caminho_db)
    try:
        out = {}
        for pasta, tab in ANEXOS:
            if "sha256" in {r[1] for r in c.execute(f"PRAGMA table_info({tab})")}:
                out.update({f"{pasta}/{r[0]}": r[1] for r in c.execute(f"SELECT arquivo, sha256 FROM {tab} WHERE sha256 IS NOT NULL")})
        return out
    finally:
        c.close()


def copiar_banco(origem, destino):
    """Cópia pela API de backup do SQLite (inclui o WAL; consistente com o banco em uso)."""
    o, d = sqlite3.connect(origem), sqlite3.connect(destino)
    try:
        o.backup(d)
    finally:
        d.close()
        o.close()


def _pasta_nova(destino, rotulo):
    base = os.path.join(destino, datetime.now().strftime("%Y%m%d-%H%M%S-%f") + (f"_{rotulo}" if rotulo else ""))
    pasta, n = base, 1
    while True:
        try:
            os.makedirs(pasta, exist_ok=False)
            return pasta
        except FileExistsError:
            n += 1
            pasta = f"{base}_{n}"


def criar(db=DB_PADRAO, destino=DESTINO_PADRAO, dir_fotos=DIR_FOTOS, rotulo=None, permitir_incompleto=False, trava=True):
    """Cria e verifica um backup e retorna a pasta.

    Lança RuntimeError se a cópia não for íntegra. Lança BackupIncompleto se faltar anexo
    referenciado; a pasta fica guardada e marcada como incompleta. Com permitir_incompleto=True,
    devolve a pasta mesmo assim, ainda marcada como incompleta.
    """
    if not os.path.exists(db):
        raise RuntimeError(f"Banco {db} não existe — nada a copiar.")
    if trava:
        with trava_manutencao(os.path.dirname(os.path.abspath(db)), "backup"):
            return criar(db, destino, dir_fotos, rotulo, permitir_incompleto, trava=False)
    pasta = _pasta_nova(destino, rotulo)
    alvo_db = os.path.join(pasta, os.path.basename(db))
    copiar_banco(db, alvo_db)                                     # 1º o banco (instantâneo consistente)
    referenciados = anexos_referenciados(alvo_db)
    copiados = []
    for sub, origem_dir in _pastas_anexos(dir_fotos).items():     # 2º os arquivos (todos, inclusive não referenciados)
        if not os.path.isdir(origem_dir):
            continue
        for raiz, _, nomes in os.walk(origem_dir):
            for n in sorted(nomes):
                orig = os.path.join(raiz, n)
                rel = sub + "/" + os.path.relpath(orig, origem_dir).replace(os.sep, "/")
                dest = os.path.join(pasta, *rel.split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(orig, dest)
                if sha256(orig) != sha256(dest):
                    raise RuntimeError(f"Anexo {rel} divergiu durante a cópia.")
                copiados.append(rel)
    ausentes = sorted(set(referenciados) - set(copiados))
    integridade, linhas = contagens(alvo_db)
    if integridade != "ok":
        raise RuntimeError(f"Cópia do banco falhou no integrity_check: {integridade}")
    arquivos = [os.path.basename(db)] + copiados
    manifesto = {
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "banco_origem": os.path.abspath(db),
        "fotos_origem": os.path.abspath(dir_fotos) if os.path.isdir(dir_fotos) else None,
        "integrity_check": integridade,
        "linhas_por_tabela": linhas,
        "conteudo_por_tabela": conteudo(alvo_db),
        "arquivos": {a: {"sha256": sha256(os.path.join(pasta, a)), "bytes": os.path.getsize(os.path.join(pasta, a))}
                     for a in arquivos},
        "anexos": {"referenciados_no_banco": len(referenciados), "copiados": len(copiados), "ausentes": ausentes},
        "completo": not ausentes,
        "situacao": "COMPLETO" if not ausentes else "INCOMPLETO",
    }
    with open(os.path.join(pasta, MANIFESTO), "w", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=2)
    det = verificar_detalhado(pasta)
    if not det["integro"]:
        raise RuntimeError("Backup criado mas não verificou: " + "; ".join(det["erros_integridade"]))
    if det["ausentes"] and not permitir_incompleto:
        raise BackupIncompleto(pasta, det["ausentes"])
    return pasta


def verificar_detalhado(pasta):
    """Integridade (arquivos, banco, linhas, conteúdo) e completude (anexos referenciados × copiados)."""
    erros, ausentes = [], []
    caminho = os.path.join(pasta, MANIFESTO)
    if not os.path.exists(caminho):
        return {"integro": False, "completo": False, "erros_integridade": ["manifesto.json ausente"], "ausentes": []}
    with open(caminho, encoding="utf-8") as f:
        m = json.load(f)
    for a, info in m["arquivos"].items():
        p = os.path.join(pasta, a)
        if not os.path.exists(p):
            erros.append(f"{a}: ausente")
        elif os.path.getsize(p) != info["bytes"] or sha256(p) != info["sha256"]:
            erros.append(f"{a}: hash/tamanho diverge")
    db = os.path.join(pasta, os.path.basename(m["banco_origem"]))
    if not os.path.exists(db):
        erros.append("banco ausente")
    else:
        integridade, linhas = contagens(db)
        if integridade != "ok":
            erros.append(f"integrity_check: {integridade}")
        if linhas != m["linhas_por_tabela"]:
            erros.append("contagem de linhas diverge do manifesto")
        if "conteudo_por_tabela" not in m:
            erros.append("manifesto sem conteúdo por tabela (backup de versão anterior: refazer)")
        elif conteudo(db) != m["conteudo_por_tabela"]:
            erros.append("conteúdo de tabela diverge do manifesto")
        # completude: recalculada a partir do banco copiado, não só do manifesto
        copiados = {a for a in m["arquivos"] if a.split("/", 1)[0] in dict(ANEXOS)}
        ausentes = sorted(set(anexos_referenciados(db)) - copiados)
        # foto/documento original: o arquivo copiado precisa ter o hash registrado no banco (cadeia de evidência)
        for arq, h in hashes_registrados(db).items():
            info = m["arquivos"].get(arq)
            if info and info["sha256"] != h:
                erros.append(f"{'foto' if arq.startswith('fotos/') else 'documento'} {arq.split('/', 1)[1]}: hash do arquivo "
                             "difere do registrado no banco")
    return {"integro": not erros, "completo": not ausentes and not erros, "erros_integridade": erros, "ausentes": ausentes}


def verificar(pasta):
    """(ok, erros): ok só se o backup for íntegro E completo."""
    d = verificar_detalhado(pasta)
    erros = d["erros_integridade"] + [f"INCOMPLETO: anexo referenciado no banco e ausente no backup: {a}" for a in d["ausentes"]]
    return not erros, erros


def restaurar(pasta, db=DB_PADRAO, dir_fotos=DIR_FOTOS, destino_seguranca=None, permitir_incompleto=False):
    """Volta o banco ao estado do backup, em manutenção (trava ativa), sem apagar nada. Exige o servidor parado.

    1. Verifica o backup. Se estiver incompleto, só restaura com permitir_incompleto=True.
    2. Cria um backup de segurança do estado atual pela API do SQLite (inclui o WAL) com as
       fotos atuais, e o verifica. É uma pasta completa em backups/, não uma cópia solta do arquivo.
    3. Restaura o banco pela API do SQLite. Devolve as fotos do backup ausentes ou diferentes e
       mantém as fotos posteriores.
    4. Verificação final: conteúdo de cada tabela igual ao manifesto e fotos referenciadas presentes e íntegras.
    Retorna a pasta do backup de segurança.
    """
    det = verificar_detalhado(pasta)
    if not det["integro"]:
        raise RuntimeError("Backup não verificou; restauração cancelada: " + "; ".join(det["erros_integridade"]))
    if det["ausentes"] and not permitir_incompleto:
        raise BackupIncompleto(pasta, det["ausentes"])
    with open(os.path.join(pasta, MANIFESTO), encoding="utf-8") as f:
        m = json.load(f)
    pasta_db = os.path.dirname(os.path.abspath(db))
    exigir_servidor_parado(pasta_db, "A restauração")
    destino_seguranca = destino_seguranca or os.path.join(pasta_db, "backups")
    origem = os.path.join(pasta, os.path.basename(m["banco_origem"]))
    with trava_manutencao(pasta_db, f"restauração de {os.path.basename(pasta)}"):
        seguranca = None
        if os.path.exists(db):
            seguranca = criar(db, destino_seguranca, dir_fotos, rotulo="antes_restauracao", permitir_incompleto=True,
                              trava=False)
        d = sqlite3.connect(db, timeout=30)
        try:
            d.execute("BEGIN IMMEDIATE")                         # espera gravações já em curso terminarem
            d.execute("COMMIT")
            o = sqlite3.connect(origem)
            try:
                o.backup(d)
            finally:
                o.close()
        finally:
            d.close()
        destinos = _pastas_anexos(dir_fotos)
        for a, info in m["arquivos"].items():
            sub = a.split("/", 1)[0]
            if sub not in destinos or "/" not in a:
                continue
            alvo = os.path.join(destinos[sub], *a.split("/")[1:])
            if not os.path.exists(alvo) or sha256(alvo) != info["sha256"]:
                os.makedirs(os.path.dirname(alvo), exist_ok=True)
                shutil.copy2(os.path.join(pasta, *a.split("/")), alvo)
        erros = []
        integridade, _ = contagens(db)
        if integridade != "ok":
            erros.append(f"integrity_check: {integridade}")
        if conteudo(db) != m["conteudo_por_tabela"]:
            erros.append("conteúdo restaurado diverge do manifesto")
        for a in anexos_referenciados(db):
            info = m["arquivos"].get(a)
            p = os.path.join(destinos[a.split("/", 1)[0]], *a.split("/")[1:])
            if info and (not os.path.exists(p) or sha256(p) != info["sha256"]):
                erros.append(f"anexo {a} não restaurado")
        if erros:
            raise RuntimeError("Restauração não conferiu: " + "; ".join(erros) +
                               (f". O estado anterior está em {seguranca}" if seguranca else ""))
    return seguranca


def main():
    utf8_console()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("criar")
    c.add_argument("--db", default=DB_PADRAO)
    c.add_argument("--destino", default=DESTINO_PADRAO)
    c.add_argument("--permitir-incompleto", action="store_true", help="guarda o backup mesmo sem todos os anexos")
    v = sub.add_parser("verificar")
    v.add_argument("pasta")
    r = sub.add_parser("restaurar")
    r.add_argument("pasta")
    r.add_argument("--db", default=DB_PADRAO)
    r.add_argument("--permitir-incompleto", action="store_true", help="restaura backup marcado INCOMPLETO")
    a = ap.parse_args()
    fotos = os.path.join(os.path.dirname(os.path.abspath(getattr(a, "db", DB_PADRAO))), "fotos")
    if a.cmd == "criar":
        pasta = criar(a.db, a.destino, fotos, permitir_incompleto=a.permitir_incompleto)
        d = verificar_detalhado(pasta)
        print(f"Backup {'COMPLETO' if d['completo'] else 'INCOMPLETO'} e íntegro: {pasta}")
        for x in d["ausentes"]:
            print(f"  anexo ausente: {x}")
    elif a.cmd == "restaurar":
        seg = restaurar(a.pasta, a.db, fotos, permitir_incompleto=a.permitir_incompleto)
        print(f"Banco restaurado de {a.pasta}." + (f" Estado anterior guardado (backup verificado) em {seg}" if seg else ""))
    else:
        d = verificar_detalhado(a.pasta)
        print(f"Integridade: {'OK' if d['integro'] else 'FALHOU'}   Completude: {'OK' if d['completo'] else 'INCOMPLETO'}")
        for e in d["erros_integridade"]:
            print(f"  {e}")
        for x in d["ausentes"]:
            print(f"  anexo referenciado e ausente: {x}")
        sys.exit(0 if d["integro"] and d["completo"] else 1)


if __name__ == "__main__":
    main()
