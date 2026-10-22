"""Topografia e cadastro de campo (equipes terceirizadas, registrados só pela engenharia e pela administração), pelo HTTP:
quem registra, as filas das duas abas, a retificação do levantamento avulso, o diário com registro sem equipe e a
migração v17 (CHECK de retificacoes_intervalos recriado sem perder linhas)."""
import os
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import importacao as I  # noqa: E402
import servicos as S  # noqa: E402
from test_acesso import D, TR, BaseHTTP  # noqa: E402

D2 = "2026-10-16"


class TestTerceirizadas(BaseHTTP):
    usuarios = BaseHTTP.usuarios + (("topo1", "TOPOGRAFIA", None), ("cad1", "CADASTRO", None))

    def assentar(self, ini, fim, data=D, extra=()):
        enc = self.cliente("enc1")
        self.assertEqual(enc.post("/api/clima", {"data": data, "equipe_id": "Zona01", "MANHA": "SOL", "TARDE": "SOL"})[0], 200)
        st, r = self.cliente("eng1").post("/api/apontamento", {          # sem NS do dia: à mão, pela engenharia, com motivo
            "data": data, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR, "motivo_sem_ns": "teste",
            "intervalos": [{"etapa": "ASSENTADO", "ini_m": ini, "fim_m": fim}, *extra]})
        self.assertEqual(st, 200, r)
        return r["id"]

    def cad(self, login, ini, fim, data=D, ref="caderneta 7"):
        return self.cliente(login).post("/api/cadastro-campo", {"trecho_id": TR, "ini_m": ini, "fim_m": fim, "data": data,
                                                                "referencia": ref})

    def fila(self, ponto=TR):
        st, r = self.cliente("eng1").get("/api/cadastro-campo")
        self.assertEqual(st, 200, r)
        return r, next((x for x in r["fila"] if x["ponto"] == ponto), None)

    def test_so_engenharia_e_administracao_registram_o_levantamento(self):
        self.assentar(0, 30)
        st, r = self.cliente("enc1").post("/api/apontamento", {
            "data": D, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
            "intervalos": [{"etapa": "CADASTRO_CAMPO", "ini_m": 0, "fim_m": 10, "referencia": "caderneta"}]})
        self.assertEqual(st, 403)
        self.assertIn("aba Cadastro de campo", r["erro"])
        for login in ("enc1", "almox1", "topo1", "cad1"):
            self.assertEqual(self.cad(login, 0, 10)[0], 403, login)
        self.assertEqual(self.cad("eng1", 0, 10, ref="  ")[0], 422)          # registro do levantamento obrigatório
        self.assertEqual(self.cad("eng1", 0, 40)[0], 422)                    # só sobre o assentado
        self.assertEqual(self.cad("eng1", 0, 10, data="2099-01-01")[0], 422)  # data futura
        st, r = self.cad("eng1", 0, 20)
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT informado_por, equipe_id, apontamento_id, referencia, etapa FROM intervalos_execucao "
                                "WHERE id=?", r["id"]), [("eng1", None, None, "caderneta 7", "CADASTRO_CAMPO")])
        self.assertEqual(self.cad("adm", 10, 25)[0], 422)                    # sobrepõe 0–20
        self.assertEqual(self.cad("adm", 20, 30)[0], 200)
        _, f = self.fila()
        self.assertIsNone(f)                                                 # todo o assentado levantado

    def test_filas_de_cadastro_e_de_topografia(self):
        self.assentar(0, 30)
        r, f = self.fila()
        self.assertEqual((f["vala_aberta"], f["reaterrado_sem_cadastro"], f["alertas_reaterro"]), ([[0.0, 30.0]], [], 0))
        self.assertGreaterEqual(r["totais"]["vala_aberta_m"], 30)
        self.assertEqual(self.cliente("cad1").get("/api/cadastro-campo")[0], 200)     # CADASTRO só consulta
        for login in ("enc1", "almox1", "topo1"):
            self.assertEqual(self.cliente(login).get("/api/cadastro-campo")[0], 403, login)
        lib = {"trecho_id": TR, "ini_m": 0, "fim_m": 20, "data": D, "referencia": "NS 012"}
        self.assertEqual(self.cliente("topo1").post("/api/liberacao", lib)[0], 403)   # TOPOGRAFIA só consulta
        st, r = self.cliente("eng1").post("/api/liberacao", lib)
        self.assertEqual(st, 200, r)
        st, t = self.cliente("topo1").get("/api/topografia")
        self.assertEqual(st, 200, t)
        x = next(x for x in t["executado_sem_liberacao"] if x["ponto"] == TR)
        self.assertEqual(x["faltas"][0]["faixas"], [[20.0, 30.0]])
        p = next(x for x in t["parciais"] if x["ponto"] == TR)
        self.assertAlmostEqual(p["liberado_m"], 20)
        self.assertEqual(t["recentes"][0]["referencia"], "NS 012")
        for login in ("enc1", "almox1", "cad1"):
            self.assertEqual(self.cliente(login).get("/api/topografia")[0], 403, login)

    def test_reaterro_sem_levantamento_e_levantamento_tardio(self):
        self.assentar(0, 30, extra=[{"etapa": "REATERRADO", "ini_m": 0, "fim_m": 30}])
        _, f = self.fila()
        self.assertEqual((f["reaterrado_sem_cadastro"], f["alertas_reaterro"], f["vala_aberta_m"]), ([[0.0, 30.0]], 1, 0))
        self.assertEqual(self.cad("eng1", 0, 30, data=D2)[0], 200)            # levantado depois do reaterro
        _, f = self.fila()
        self.assertEqual((f["falta_m"], f["alertas_reaterro"]), (0, 1))       # coberto, mas o alerta do reaterro fica

    def test_retificacao_do_levantamento_avulso(self):
        ap = self.assentar(0, 30)
        cid = self.cad("eng1", 0, 30, ref="caderneta 12")[1]["id"]
        eng = self.cliente("eng1")
        d = eng.get(f"/api/detalhe?tipo=TRECHO&id={TR}")[1]
        self.assertIn(("CADASTRO_CAMPO", cid), [(g["ref_tipo"], g["ref_id"]) for g in d["intervalos"]["registros"]])
        menor = {"ref_tipo": "APONTAMENTO", "ref_id": ap, "intervalos": [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 25}],
                 "motivo": "trena: 25 m"}
        st, r = eng.post("/api/intervalos/retificar", {**menor, "simular": True})
        self.assertEqual(st, 422)
        self.assertIn(f"cadastro de campo #{cid}", r["erro"])               # o levantamento é corrigido antes
        novo = [{"etapa": "CADASTRO_CAMPO", "ini_m": 0, "fim_m": 25, "referencia": "caderneta 12 (corrigida)"}]
        corr = {"ref_tipo": "CADASTRO_CAMPO", "ref_id": cid, "intervalos": novo, "motivo": "conferido com a trena"}
        self.assertEqual(eng.post("/api/intervalos/retificar", {**corr, "intervalos": [dict(novo[0], referencia="")]})[0], 422)
        self.assertEqual(self.cliente("enc1").post("/api/intervalos/retificar", corr)[0], 403)
        st, r = eng.post("/api/intervalos/retificar", corr)
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT anulado_por IS NOT NULL FROM intervalos_execucao WHERE id=?", cid), [(1,)])
        self.assertEqual(self.q("SELECT ref_tipo, ref_id FROM retificacoes_intervalos"), [("CADASTRO_CAMPO", cid)])
        self.assertEqual(self.q("SELECT fim_m, referencia, apontamento_id FROM intervalos_execucao WHERE etapa='CADASTRO_CAMPO' "
                                "AND anulado_por IS NULL"), [(25.0, "caderneta 12 (corrigida)", None)])
        st, r = eng.post("/api/intervalos/retificar", menor)
        self.assertEqual(st, 200, r)
        st, r = eng.post("/api/intervalos/retificar", {**corr, "motivo": "de novo"})
        self.assertEqual(st, 422)
        self.assertIn("já foi retificado", r["erro"])

    def test_diario_da_obra_com_levantamento_sem_equipe(self):
        self.assentar(0, 30)
        self.assertEqual(self.cad("eng1", 0, 20)[0], 200)
        st, d = self.cliente("eng1").get(f"/api/diario?data={D}")
        self.assertEqual(st, 200, d)
        self.assertEqual([e["id"] for e in d["equipes"]], ["Zona01"])
        self.assertIn((None, "CADASTRO_CAMPO"), [(p["equipe_id"], p["etapa"]) for p in d["producao"]])
        self.assertEqual(d["totais"]["cadastro_m"], 20)
        st, d = self.cliente("enc1").get(f"/api/diario?data={D}")            # a equipe vê só o que é dela
        self.assertEqual(st, 200, d)
        self.assertNotIn("CADASTRO_CAMPO", [p["etapa"] for p in d["producao"]])


class TestMigracaoV17(unittest.TestCase):
    def test_check_de_retificacoes_recriado_sem_perder_linhas(self):
        with tempfile.TemporaryDirectory() as pasta:
            conn = S.conectar(os.path.join(pasta, "obra.db"))
            try:
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("DROP TABLE retificacoes_intervalos")
                conn.execute("""CREATE TABLE retificacoes_intervalos (id INTEGER PRIMARY KEY, trecho_id TEXT NOT NULL REFERENCES trechos(id),
                                ref_tipo TEXT NOT NULL CHECK (ref_tipo IN ('APONTAMENTO','CONCILIACAO')), ref_id INTEGER NOT NULL,
                                novo_apontamento_id INTEGER REFERENCES apontamentos(id), motivo TEXT NOT NULL, responsavel TEXT NOT NULL,
                                detalhe TEXT NOT NULL, em TEXT NOT NULL)""")
                conn.execute("INSERT INTO retificacoes_intervalos(trecho_id,ref_tipo,ref_id,motivo,responsavel,detalhe,em) "
                             "VALUES ('TR-00001','APONTAMENTO',1,'trena','eng1','{}','2026-10-01')")
                conn.execute("PRAGMA legacy_alter_table = ON")
                conn.execute("BEGIN")
                I.preparar_v17(conn)
                conn.execute("COMMIT")
                sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='retificacoes_intervalos'").fetchone()[0]
                self.assertIn("CADASTRO_CAMPO", sql)
                self.assertEqual([tuple(r) for r in conn.execute("SELECT ref_tipo, motivo FROM retificacoes_intervalos")],
                                 [("APONTAMENTO", "trena")])
                self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='retificacoes_intervalos_v16'").fetchone())
                ivs = conn.execute("SELECT sql FROM sqlite_master WHERE name='intervalos_execucao'").fetchone()[0]
                self.assertIn("REFERENCES retificacoes_intervalos", ivs)        # a referência continua no nome da tabela
                conn.execute("INSERT INTO retificacoes_intervalos(trecho_id,ref_tipo,ref_id,motivo,responsavel,detalhe,em) "
                             "VALUES ('TR-00001','CADASTRO_CAMPO',7,'m','eng1','{}','2026-10-02')")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
