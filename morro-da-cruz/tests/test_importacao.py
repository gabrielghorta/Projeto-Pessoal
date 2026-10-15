"""Etapas 0 e 1: backup verificável, carga não destrutiva, importação idempotente, proveniência,
identidade estável, unidades com fonte, BA/BB/AW, decisões preservadas e migração do esquema v1.
Usa planilhas SINTÉTICAS (tests/planilhas_sinteticas.py) — independe dos arquivos do contrato."""
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import backup  # noqa: E402
import importar  # noqa: E402
import planilhas_sinteticas as PS  # noqa: E402
import servicos as S  # noqa: E402


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.planilhas = os.path.join(self.tmp, "planilhas")
        self.cfg = PS.gerar(self.planilhas)
        self.dados = os.path.join(self.tmp, "dados")
        os.makedirs(os.path.join(self.dados, "fotos"))
        self.db = os.path.join(self.dados, "obra.db")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def aplicar(self, **kw):
        return importar.aplicar(self.db, self.planilhas, cfg=self.cfg, **kw)

    def q(self, sql, *a):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(sql, a).fetchall()
        finally:
            c.close()


class TestBackup(Base):
    def test_criar_verificar_e_detectar_adulteracao(self):
        self.aplicar()
        open(os.path.join(self.dados, "fotos", "f1.jpg"), "wb").write(b"foto")
        pasta = backup.criar(self.db, os.path.join(self.dados, "backups"), os.path.join(self.dados, "fotos"))
        self.assertEqual(backup.verificar(pasta), (True, []))
        with open(os.path.join(pasta, "fotos", "f1.jpg"), "ab") as f:
            f.write(b"x")
        ok, erros = backup.verificar(pasta)
        self.assertFalse(ok)
        self.assertIn("hash", erros[0])


class TestRestauracao(Base):
    def test_restaurar_volta_ao_estado_e_guarda_o_atual(self):
        self.aplicar()
        pasta = backup.criar(self.db, os.path.join(self.dados, "backups"), os.path.join(self.dados, "fotos"))
        antes = self.q("SELECT COUNT(*) FROM medicoes")[0][0]
        c = S.conectar(self.db)
        S.criar_medicao(c, 1, "2026-10-01", "2026-10-31")
        c.close()
        guardado = backup.restaurar(pasta, self.db, os.path.join(self.dados, "fotos"))
        self.assertEqual(self.q("SELECT COUNT(*) FROM medicoes")[0][0], antes)
        self.assertTrue(os.path.exists(guardado))                # o banco substituído não foi apagado
        g = sqlite3.connect(guardado)
        self.assertEqual(g.execute("SELECT COUNT(*) FROM medicoes").fetchone()[0], antes + 1)
        g.close()


class TestCargaNaoDestrutiva(Base):
    def test_simulacao_nao_altera_o_banco(self):
        self.aplicar()
        antes = sha(self.db)
        rel = importar.simular(self.db, self.planilhas, cfg=self.cfg)
        self.assertEqual(rel["modo"], "SIMULACAO")
        self.assertEqual(sha(self.db), antes)

    def test_aplicar_faz_backup_verificado_antes(self):
        self.aplicar()
        rel = self.aplicar()
        self.assertTrue(rel["backup"] and backup.verificar(rel["backup"])[0])

    def test_erro_desfaz_tudo_e_preserva_backup(self):
        self.aplicar()
        c = S.conectar(self.db)
        S.criar_medicao(c, 1, "2026-10-01", "2026-10-31")
        c.close()
        antes = sha(self.db)
        # 06.2 corrompida (sem cabeçalho de nomenclatura)
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.title = "CONEXÕES"
        wb.save(os.path.join(self.planilhas, PS.ARQ["conexoes"]))
        with self.assertRaises(RuntimeError):
            self.aplicar()
        self.assertEqual(sha(self.db), antes)
        self.assertEqual(self.q("SELECT COUNT(*) FROM medicoes")[0][0], 1)
        self.assertTrue(os.listdir(os.path.join(self.dados, "backups")))

    def test_seed_antigo_nao_apaga_mais(self):
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(AQUI), "seed.py")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("importar.py", r.stderr)


class TestIdempotencia(Base):
    def test_reimportar_mesmos_arquivos_sem_alteracoes(self):
        r1 = self.aplicar()
        self.assertEqual(r1["status"], "CONCLUIDA")
        self.assertTrue(r1["auditoria"]["contagens_ok"], r1["auditoria"]["contagens"])
        self.assertTrue(r1["auditoria"]["totalizacao_bm"]["ok"])
        ids = self.q("SELECT id FROM itens_projeto ORDER BY id")
        r2 = self.aplicar()
        self.assertEqual(r2["status"], "SEM_ALTERACOES")
        self.assertEqual(r2["alteracoes_registradas"], 0)
        self.assertEqual(self.q("SELECT id FROM itens_projeto ORDER BY id"), ids)
        self.assertEqual(self.q("SELECT COUNT(*) FROM fontes_arquivo")[0][0], 5)

    def test_proveniencia_com_hash_aba_linha(self):
        self.aplicar()
        p = self.q("""SELECT p.aba, p.linha, f.sha256, f.revisao FROM proveniencia p JOIN fontes_arquivo f ON f.id=p.fonte_id
                      JOIN itens_projeto i ON i.id=p.entidade_id WHERE p.entidade='item_projeto' AND i.descricao='TUBO'""")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0][:2], ("CONEXÕES", 11))
        self.assertEqual(p[0][2], sha(os.path.join(self.planilhas, PS.ARQ["conexoes"])))
        self.assertEqual(p[0][3], "REV08")


class TestIdentidade(Base):
    def test_elemento_fisico_unico_com_duas_atividades(self):
        self.aplicar()
        el = self.q("SELECT id, chave_natural FROM elementos WHERE numero='DF-33'")
        self.assertEqual(len(el), 1)
        self.assertEqual(el[0][1], "H:5FDEA")
        at = self.q("SELECT tipo_frente, frente_id FROM atividades WHERE elemento_id=? ORDER BY 1", el[0][0])
        self.assertEqual(at, [("CH", "CH"), ("Rede", "Zona01")])

    def test_sem_handle_fica_sem_posicao(self):
        self.aplicar()
        self.assertEqual(self.q("SELECT numero, chave_natural, lat FROM elementos WHERE numero='MV-11'"), [("MV-11", "N:MV-11", None)])

    def test_linha_inserida_nao_troca_identidade(self):
        self.aplicar()
        antes = dict(self.q("SELECT chave_ocorrencia || '@' || atividade_id, id FROM itens_projeto"))
        nova = ("Zona01_PB01_Rede_NÓ1.8", "CURVA 90º", "63", "PN10", 1, "1.14.27", "5FD4F", None, None, None,
                "CONTRATUAL CONFIRMADO", None, None)
        PS.gerar(self.planilhas, conexoes=[nova] + PS.CONEXOES)       # todas as linhas descem uma posição
        rel = self.aplicar()
        depois = dict(self.q("SELECT chave_ocorrencia || '@' || atividade_id, id FROM itens_projeto"))
        for k, v in antes.items():
            self.assertEqual(depois[k], v)                            # mesmos itens, mesmos IDs
        self.assertEqual(rel["alteracoes"]["item_projeto"]["novos"], 1)
        self.assertEqual(rel["alteracoes"]["item_projeto"].get("alterados", 0), 0)

    def test_item_retirado_fica_nao_vigente(self):
        self.aplicar()
        PS.gerar(self.planilhas, conexoes=[l for l in PS.CONEXOES if l[1] != "TUBO"])
        self.aplicar()
        self.assertEqual(self.q("SELECT vigente FROM itens_projeto WHERE descricao='TUBO'"), [(0,)])

    def test_trecho_renomeado_mantem_id_e_historico(self):
        self.aplicar()
        tid = self.q("SELECT id FROM trechos WHERE ponto='Zona01_PB01_Rede_TR002'")[0][0]
        renomeado = [("Zona01_PB01_Rede_TR099",) + t[1:] if t[0].endswith("TR002") else t for t in PS.TRECHOS]
        PS.gerar(self.planilhas, trechos=renomeado)
        self.aplicar()
        self.assertEqual(self.q("SELECT ponto FROM trechos WHERE id=?", tid), [("Zona01_PB01_Rede_TR099",)])
        self.assertEqual(sorted(r[0] for r in self.q("SELECT nome FROM nomes_historico WHERE entidade_id=?", tid)),
                         ["Zona01_PB01_Rede_TR002", "Zona01_PB01_Rede_TR099"])

    def test_quantidade_alterada_registra_antes_e_depois(self):
        self.aplicar()
        mod = [l[:4] + (5,) + l[5:] if l[1] == "TUBO" else l for l in PS.CONEXOES]
        PS.gerar(self.planilhas, conexoes=mod)
        rel = self.aplicar()
        self.assertEqual(rel["alteracoes"]["item_projeto"]["alterados"], 1)
        self.assertEqual(self.q("SELECT antes, depois FROM alteracoes WHERE campo='quantidade'"), [("0.71", "5.0")])


class TestUnidadesEAvisos(Base):
    def test_unidade_so_com_fonte(self):
        self.aplicar()
        un = dict(self.q("SELECT descricao, unidade FROM itens_projeto"))
        self.assertEqual(un["TUBO"], "M")                                    # Juntada 1.14.77 = M
        self.assertEqual(un["TÊ 90º DE REDUÇÃO"], "PÇ")                      # 'pç' preservado, não vira UN
        self.assertIsNone(un["TUBO C/ FLANGE E PONTA PN10 L=0,36 M"])        # código APROVAR: pendente, não M
        self.assertIn("PENDENTE", self.q("SELECT unidade_fonte FROM itens_projeto WHERE codigo_bm='APROVAR'")[0][0])

    def test_contador_por_unidade_separa_pendente(self):
        self.aplicar()
        c = S.conectar(self.db)
        t = S.totais_atividade(c, "Zona01_PB01_CH_DF-33")
        self.assertEqual(dict(t["totais"]), {"UN": 2.0, "M": 0.71, "PÇ": 2.0})
        self.assertEqual(t["pendentes"], 1)
        with self.assertRaisesRegex(Exception, "sem quantidade/unidade"):
            S.previsto(c, "ATIVIDADE", "Zona01_PB01_CH_DF-33", 0)
        c.close()

    def test_ba_bb_aw_e_avisos_separados(self):
        self.aplicar()
        self.assertEqual(self.q("SELECT enquadramento_bm, obs_enquadramento_bm FROM itens_projeto WHERE descricao='TÊ 90º DE REDUÇÃO'"),
                         [("CONTRATUAL — VALIDAR", "PN diferente")])
        av = self.q("SELECT tipo, prioridade, texto FROM avisos_origem a JOIN itens_projeto i ON i.id=a.item_id "
                    "WHERE i.descricao='LUVA ELETROFUSÃO' AND i.atividade_id IN (SELECT id FROM atividades WHERE nomenclatura LIKE '%NÓ1.8') ORDER BY 1,3")
        self.assertEqual(av, [("PROBLEMA", "P1", "P1 aviso A"), ("PROBLEMA", "P1", "P1 aviso B"), ("SUGESTAO", "P1", "sugestão A")])


class TestDecisoes(Base):
    def test_reimportacao_nao_altera_decisao_e_liga_aviso(self):
        self.aplicar()
        c = sqlite3.connect(self.db)
        c.execute("UPDATE decisoes SET decisao='texto revisto pelo usuário' WHERE id='DEC-0001'")
        c.commit()
        c.close()
        self.aplicar()
        self.assertEqual(self.q("SELECT decisao FROM decisoes WHERE id='DEC-0001'"), [("texto revisto pelo usuário",)])
        c = S.conectar(self.db)
        d = S.detalhe(c, "ATIVIDADE", "Zona01_PB01_Rede_DF-33")
        c.close()
        aviso = [a for a in d["avisos"] if "DF-05" in a["texto"]][0]
        self.assertEqual(aviso["decisoes"], ["DEC-0001"])
        self.assertEqual(self.q("SELECT vigente FROM avisos_origem WHERE texto LIKE '%DF-05%'"), [(1,)])  # aviso de origem preservado


class TestMigracaoV1(Base):
    def _criar_v1(self):
        c = sqlite3.connect(self.db)
        with open(os.path.join(AQUI, "fixtures", "schema_v1.sql"), encoding="utf-8") as f:
            c.executescript(f.read())
        c.execute("INSERT INTO equipes(id,nome) VALUES ('Zona01','EQUIPE ZONA 01')")
        c.execute("INSERT INTO trechos(id,frente_id,extensao_m,quantidades) VALUES ('Zona01_PB01_Rede_TR001','Zona01',76.55,'{}')")
        c.execute("INSERT INTO trechos(id,frente_id,extensao_m,quantidades) VALUES ('Zona09_PB99_Rede_TR777','Zona01',1,'{}')")
        c.execute("INSERT INTO elementos(id,numero,tipo) VALUES ('SUBDMC1_DF-33','DF-33','DF')")
        c.execute("INSERT INTO conjuntos(id,elemento_id,frente_id) VALUES ('Zona01_PB01_CH_DF-33','SUBDMC1_DF-33','Zona01')")
        c.execute("INSERT INTO materiais(id,descricao,unidade,propriedade) VALUES ('CAESB-PEAD-DE63','tubo','M','CAESB')")
        c.execute("INSERT INTO medicoes(id,numero,periodo_ini,periodo_fim) VALUES (1,1,'2026-10-01','2026-10-31')")
        c.execute("INSERT INTO checkins(id,data,equipe_id,alvo_tipo,alvo_id) VALUES (1,'2026-10-15','Zona01','TRECHO','Zona01_PB01_Rede_TR001')")
        c.execute("INSERT INTO movimentos(data,material_id,tipo,quantidade,alvo_tipo,alvo_id,checkin_id) "
                  "VALUES ('2026-10-15','CAESB-PEAD-DE63','CUSTODIA',80,'TRECHO','Zona01_PB01_Rede_TR001',1)")
        c.execute("INSERT INTO fotos(alvo_tipo,alvo_id,categoria,arquivo,data_hora,carimbo) "
                  "VALUES ('CONJUNTO','Zona01_PB01_CH_DF-33','EXECUCAO','a.jpg','2026-10-15T10:00','c')")
        c.execute("INSERT INTO fotos(alvo_tipo,alvo_id,categoria,arquivo,data_hora,carimbo) "
                  "VALUES ('TRECHO','Zona09_PB99_Rede_TR777','EXECUCAO','b.jpg','2026-10-15T10:00','c')")
        c.execute("INSERT INTO execucao(alvo_tipo,alvo_id,concluido,ok_fiscal_em,medicao_id) VALUES ('TRECHO','Zona01_PB01_Rede_TR001',1,'2026-10-15',1)")
        c.execute("INSERT INTO cadastro(trecho_id,etapa,atualizado_em) VALUES ('Zona01_PB01_Rede_TR001','1_PRONTO','x')")
        c.execute("INSERT INTO medicao_lancamentos(medicao_id,gaveta,servico,alvo_tipo,alvo_id,unidade,quantidade,valor) "
                  "VALUES (1,1,'MATERIAL 20%','TRECHO','Zona01_PB01_Rede_TR001','UN',1,99.9)")
        c.commit()
        c.close()

    def test_migra_preservando_movimentos_e_remapeando(self):
        self._criar_v1()
        with self.assertRaises(S.EsquemaAntigo):
            S.conectar(self.db)                                  # servidor recusa v1 sem migração
        rel = self.aplicar()
        self.assertEqual(rel["esquema_antes"], 1)
        tr = self.q("SELECT id FROM trechos WHERE ponto='Zona01_PB01_Rede_TR001'")[0][0]
        at = self.q("SELECT id FROM atividades WHERE nomenclatura='Zona01_PB01_CH_DF-33'")[0][0]
        self.assertEqual(self.q("SELECT alvo_tipo, alvo_id FROM movimentos"), [("TRECHO", tr)])
        self.assertEqual(self.q("SELECT alvo_tipo, alvo_id FROM checkins"), [("TRECHO", tr)])
        self.assertEqual(self.q("SELECT trecho_id FROM cadastro"), [(tr,)])
        self.assertIn(("ATIVIDADE", at), self.q("SELECT alvo_tipo, alvo_id FROM fotos"))
        # trecho que não existe mais na 06.1: valor antigo preservado e pendência registrada
        self.assertIn(("TRECHO", "Zona09_PB99_Rede_TR777"), self.q("SELECT alvo_tipo, alvo_id FROM fotos"))
        self.assertTrue(self.q("SELECT 1 FROM pendencias_importacao WHERE referencia LIKE '%TR777%'"))
        self.assertEqual(self.q("SELECT tipo FROM medicoes"), [("TESTE",)])
        self.assertEqual(self.q("SELECT status FROM medicao_lancamentos"), [("PENDENTE",)])
        self.assertEqual(self.q("SELECT valor FROM v1_medicao_lancamentos"), [(99.9,)])     # histórico preservado
        self.assertEqual(rel["registros_operacionais_preservados"]["fotos"], 2)
        self.assertTrue(backup.verificar(rel["backup"])[0])
        S.conectar(self.db).close()                                # agora abre normalmente


if __name__ == "__main__":
    unittest.main()
