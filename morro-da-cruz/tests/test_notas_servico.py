"""Nota de Serviço por upload (notas_servico): migração v18, casamento NS ↔ trecho físico na base real, registro por tipo
(topografia, cadastro, serviço), anulação, reenvio e permissões pelo HTTP. Sem os PDFs reais: a NS é sintética
(tests/ns_sintetica.py)."""
import hashlib
import os
import re
import sqlite3
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import servicos as S  # noqa: E402
from test_importacao import Base  # noqa: E402


def _ddl(tabela, trocas=()):
    with open(os.path.join(os.path.dirname(AQUI), "schema.sql"), encoding="utf-8") as f:
        ddl = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \(.*?\n\);", f.read(), re.S).group(0)
    for velho, novo in trocas:
        assert velho in ddl, velho
        ddl = ddl.replace(velho, novo)
    return ddl.replace(f"CREATE TABLE IF NOT EXISTS {tabela} (", f"CREATE TABLE {tabela} (", 1)


class TestMigracaoV18(Base):
    """A migração roda pelo caminho de verdade (importar.aplicar) sobre um banco rebaixado: as linhas ficam e as tabelas
    que apontam para a tabela recriada continuam apontando para o nome certo (com as chaves estrangeiras ligadas, o
    rename da tabela antiga reescreveria as referências para o nome provisório)."""

    def rebaixar(self, versao, sql_extra=()):
        c = sqlite3.connect(self.db, isolation_level=None)
        try:
            c.execute("PRAGMA foreign_keys = OFF")
            c.execute("PRAGMA legacy_alter_table = ON")      # o rename não reescreve as referências das outras tabelas
            c.execute("BEGIN")
            c.execute("ALTER TABLE documentos RENAME TO documentos_atual")
            c.execute(_ddl("documentos", [(",'NS_PDF','NS_CROQUI','NS_PLANILHA'", "")]))
            c.execute("INSERT INTO documentos SELECT * FROM documentos_atual")
            c.execute("DROP TABLE documentos_atual")
            c.execute("DROP TABLE ns_segmentos")
            c.execute("DROP TABLE notas_servico")
            for sql in sql_extra:
                c.execute(sql)
            c.execute("DELETE FROM schema_versao WHERE versao > ?", (versao,))
            c.execute("INSERT OR IGNORE INTO schema_versao VALUES (?, '2026-10-20T00:00:00', 'rebaixado no teste')", (versao,))
            c.execute("COMMIT")
        finally:
            c.close()

    def test_v17_para_v18_documentos_recriado_sem_perder_linhas(self):
        self.aplicar()
        pdf = b"%PDF-1.4 nota fiscal de teste"
        h = hashlib.sha256(pdf).hexdigest()
        os.makedirs(os.path.join(self.dados, "documentos"), exist_ok=True)
        with open(os.path.join(self.dados, "documentos", f"{h}.pdf"), "wb") as f:      # o backup confere o anexo
            f.write(pdf)
        self.rebaixar(17, [
            "INSERT INTO documentos(id,tipo,arquivo,nome_original,sha256,bytes,mime,enviado_por,enviado_em) VALUES "
            f"(7,'NF_PDF','{h}.pdf','nf.pdf','{h}',{len(pdf)},'application/pdf','eng1','2026-10-01')",
            "INSERT INTO notas_fiscais(numero,status,documento_id,origem) VALUES ('123','A_CONFERIR',7,'DIGITADA')"])
        self.assertEqual(self.q("SELECT MAX(versao) FROM schema_versao"), [(17,)])
        rel = self.aplicar()
        self.assertEqual((rel["esquema_antes"], rel["esquema_depois"]), (17, S.VERSAO_ESQUEMA))
        sql = lambda t: self.q("SELECT sql FROM sqlite_master WHERE name=?", t)[0][0]
        self.assertIn("NS_PDF", sql("documentos"))
        self.assertIn("REFERENCES documentos(id)", sql("notas_fiscais"))            # não "documentos_v17"
        self.assertIn("REFERENCES documentos(id)", sql("inspecoes"))
        self.assertEqual(self.q("SELECT d.sha256 FROM notas_fiscais n JOIN documentos d ON d.id=n.documento_id"), [(h,)])
        self.assertEqual(self.q("SELECT name FROM sqlite_master WHERE name LIKE 'documentos_v%'"), [])
        for t, col in (("intervalos_execucao", "ns_segmento_id"), ("etapas_complementares", "ns_segmento_id"),
                       ("apontamentos", "motivo_sem_ns")):
            self.assertIn(col, [r[1] for r in self.q(f"PRAGMA table_info({t})")], t)
        c = self.conectar()
        self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
        c.execute("INSERT INTO documentos(tipo,arquivo,sha256,bytes,enviado_por,enviado_em) "
                  "VALUES ('NS_PDF','bb.pdf','bb',5,'eng1','2026-10-21')")
        c.execute("INSERT INTO notas_fiscais(numero,status,documento_id) VALUES ('124','A_CONFERIR',?)",
                  (c.execute("SELECT id FROM documentos WHERE sha256='bb'").fetchone()[0],))   # a referência resolve

    def test_v16_para_v18_retificacoes_continuam_referenciadas(self):
        self.aplicar()
        tr = self.q("SELECT id FROM trechos WHERE vigente=1 ORDER BY id LIMIT 1")[0][0]
        self.rebaixar(16, [
            "ALTER TABLE retificacoes_intervalos RENAME TO retif_atual",
            _ddl("retificacoes_intervalos", [("'APONTAMENTO','CONCILIACAO','CADASTRO_CAMPO'", "'APONTAMENTO','CONCILIACAO'")]),
            "INSERT INTO retificacoes_intervalos SELECT * FROM retif_atual",
            "DROP TABLE retif_atual",
            f"INSERT INTO retificacoes_intervalos(id,trecho_id,ref_tipo,ref_id,motivo,responsavel,detalhe,em) "
            f"VALUES (5,'{tr}','APONTAMENTO',1,'trena','eng1','{{}}','2026-10-01')",
            f"INSERT INTO apontamentos(id,data,equipe_id,alvo_tipo,alvo_id,anulado_por) VALUES (1,'2026-10-01','Zona01','TRECHO','{tr}',5)"])
        rel = self.aplicar()
        self.assertEqual((rel["esquema_antes"], rel["esquema_depois"]), (16, S.VERSAO_ESQUEMA))
        ap = self.q("SELECT sql FROM sqlite_master WHERE name='apontamentos'")[0][0]
        self.assertIn("REFERENCES retificacoes_intervalos(id)", ap)                 # não "retificacoes_intervalos_v16"
        self.assertIn("CADASTRO_CAMPO", self.q("SELECT sql FROM sqlite_master WHERE name='retificacoes_intervalos'")[0][0])
        self.assertEqual(self.q("SELECT a.id, r.motivo FROM apontamentos a JOIN retificacoes_intervalos r ON r.id=a.anulado_por"),
                         [(1, "trena")])
        self.assertEqual(self.conectar().execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
