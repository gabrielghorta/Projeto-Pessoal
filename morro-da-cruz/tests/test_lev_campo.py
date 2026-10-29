"""Campo (diário do dia e interferências) e LEV (cronograma, BM, redes e conexões), pelo HTTP: quem abre cada tela,
o encarregado preso à própria equipe, o supervisor resolvendo a interferência e os números conferidos com o banco."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import server  # noqa: E402
from test_acesso import D, TR, BaseHTTP  # noqa: E402

INTERF = {"alvo_tipo": "TRECHO", "alvo_id": TR, "tipo": "IMPEDIMENTO", "categoria": "INTERFERENCIA",
          "descricao": "Rede de esgoto cruzando a vala a 1,2 m", "data": D, "equipe_id": "Zona01"}


class TestCampo(BaseHTTP):
    usuarios = BaseHTTP.usuarios + (("sup1", "SUPERVISOR", None),)

    def test_diario_do_dia_e_encarregado_so_ve_a_propria_equipe(self):
        enc, eng = self.cliente("enc1"), self.cliente("eng1")
        self.assertEqual(enc.post("/api/clima", {"data": D, "equipe_id": "Zona01", "MANHA": "SOL", "TARDE": "PARALISADO_CHUVA"})[0], 200)
        self.assertEqual(enc.post("/api/ocorrencia", INTERF)[0], 200)
        st, d = enc.get(f"/api/diario?data={D}&equipe=Zona02")             # pediu outra equipe: recebe a própria
        self.assertEqual((st, d["equipe"]), (200, "Zona01"))
        self.assertEqual(d["equipes"][0]["clima"], {"MANHA": "Sol", "TARDE": "Paralisado por Chuva"})
        self.assertEqual([(o["categoria"], o["aberta_por"]) for o in d["ocorrencias"]], [("INTERFERENCIA", "enc1")])
        self.assertEqual(d["ocorrencias"][0]["alvo_nome"], TR)
        st, d = eng.get(f"/api/diario?data={D}")                             # a engenharia vê a obra inteira
        self.assertEqual((st, d["equipe"], [e["id"] for e in d["equipes"]], d["totais"]["ocorrencias"]), (200, None, ["Zona01"], 1))
        self.assertEqual(eng.get("/api/diario?data=2026-13-40")[0], 422)
        self.assertEqual(eng.get(f"/api/diario?data={D}&equipe=ZonaXX")[0], 422)

    def test_interferencia_aberta_pela_equipe_e_resolvida_pelo_supervisor(self):
        enc, sup, almox = self.cliente("enc1"), self.cliente("sup1"), self.cliente("almox1")
        st, r = enc.post("/api/ocorrencia", INTERF)
        self.assertEqual(st, 200, r)
        st, p = almox.get("/api/interferencias?abertas=1")                   # o almoxarife também abre a tela de Campo
        self.assertEqual((st, p["contagem"]["abertas"], p["contagem"]["interferencias_abertas"]), (200, 1, 1))
        self.assertEqual(p["ocorrencias"][0]["alvo_nome"], TR)
        self.assertEqual(enc.post("/api/ocorrencia/resolver", {"ocorrencia_id": r["id"], "resolucao": "desviado"})[0], 403)
        self.assertEqual(sup.post("/api/ocorrencia/resolver", {"ocorrencia_id": r["id"], "resolucao": "Caesb remanejou a rede"})[0], 200)
        p = sup.get("/api/interferencias")[1]
        self.assertEqual((p["contagem"]["abertas"], p["contagem"]["resolvidas"], p["ocorrencias"][0]["resolvida_por"]), (0, 1, "sup1"))
        self.assertEqual(sup.get("/api/interferencias?abertas=1")[1]["ocorrencias"], [])
        self.assertEqual(sup.get("/api/estoque")[0], 403)                    # supervisor: mapa e campo


class TestLev(BaseHTTP):
    def test_so_engenharia_e_administracao_abrem_o_lev(self):
        enc, almox, eng, adm = (self.cliente(x) for x in ("enc1", "almox1", "eng1", "adm"))
        for rota in ("/api/lev/bm", "/api/lev/redes", "/api/lev/conexoes", "/api/lev/cronograma"):
            self.assertEqual((enc.get(rota)[0], almox.get(rota)[0]), (403, 403), rota)
        self.assertEqual(adm.get("/api/lev/redes")[0], 200)
        for planilha in ("JUNTADA", "VERTICAL"):
            st, b = eng.get("/api/lev/bm?planilha=" + planilha)
            self.assertEqual((st, len(b["itens"])), (200, self.n("bm_itens", "planilha=? AND vigente=1", planilha)), planilha)
            self.assertAlmostEqual(b["total"], self.q("SELECT SUM(valor_total) FROM bm_itens WHERE planilha=? AND vigente=1",
                                                      planilha)[0][0] or 0, places=2)
        self.assertEqual(eng.get("/api/lev/bm?planilha=OUTRA")[0], 422)
        st, r = eng.get("/api/lev/redes")
        self.assertEqual((st, r["total_trechos"]), (200, self.n("trechos", "vigente=1")))
        self.assertAlmostEqual(sum(x["extensao_m"] for x in r["resumo"]), r["total_m"], places=2)
        self.assertEqual(eng.get("/api/lev/redes?frente=Zona01&q=TR001")[1]["trechos"][0]["ponto"], TR)
        st, r = eng.get("/api/lev/conexoes")
        self.assertEqual((st, r["total_itens"]), (200, self.n("itens_projeto", "vigente=1")))

    @unittest.skipUnless(server._arquivo_oficial("reajuste") or server._arquivo_oficial("bm"), "planilha do BM ausente")
    def test_cronograma_ff_caesb_da_planilha(self):
        st, r = self.cliente("eng1").get("/api/lev/cronograma")
        self.assertEqual((st, len(r["meses"]), r["prazo_dias"], r["meses"][0]["periodo"]), (200, 18, 540, "01-10-26 A 31-10-26"))
        self.assertEqual([i["item"] for i in r["itens"]][:3], ["1", "1.1", "2.1"])
        acum = next(t for t in r["totais"] if t["descricao"].startswith("FATURAMENTO - ACUMULADO"))
        self.assertAlmostEqual(acum["fin_prog"][-1], 49878748.66, places=1)       # = valor do contrato
        self.assertAlmostEqual(acum["fis_prog"][-1], 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
