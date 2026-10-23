"""Módulo D — programação das equipes, programado × realizado, faltantes, camadas do mapa e filtro por frente."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import planejamento as P  # noqa: E402
import servicos as S  # noqa: E402
from test_acesso import BaseHTTP  # noqa: E402
from test_campo import TR, BaseCampo, D  # noqa: E402

D2 = "2026-10-16"
TUBO = "CAESB-PEAD-DE63"


class TestProgramacao(BaseCampo):
    def test_programar_recusas_e_realizacao_pelo_checkin(self):
        p1 = P.programar(self.c, D2, "Zona01", "TRECHO", TR, "ASSENTAMENTO", "eng1", 0, 30, [{"material_id": TUBO, "quantidade": 30}])
        with self.assertRaisesRegex(S.RegraViolada, "já existe"):
            P.programar(self.c, D2, "Zona01", "TRECHO", TR, "ASSENTAMENTO", "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "fora do trecho"):
            P.programar(self.c, D2, "Zona01", "TRECHO", TR, "REATERRO", "eng1", 70, 80)
        with self.assertRaisesRegex(S.RegraViolada, "Serviço inválido"):
            P.programar(self.c, D2, "Zona01", "TRECHO", TR, "VOAR", "eng1")
        p2 = P.programar(self.c, D2, "Zona02", "TRECHO", "Zona02_PB04_Rede_TR036", "ASSENTAMENTO", "eng1")
        self.assertEqual(self.q("SELECT COUNT(*) FROM movimentos")[0][0], 0)          # planejar não movimenta nada
        S.entrada_material(self.c, D, TUBO, 100, "ROMANEIO_CAESB", "ROM", "almox1")
        ck = S.checkin(self.c, D2, "Zona01", "TRECHO", TR, materiais=[{"material_id": TUBO, "quantidade": 30}])
        self.assertEqual(self.q("SELECT id, status, checkin_id FROM programacoes ORDER BY id"), [(p1, "REALIZADA", ck), (p2, "PLANEJADA", None)])
        with self.assertRaisesRegex(S.RegraViolada, "motivo"):
            P.encerrar(self.c, p2, "NAO_REALIZADA", "", "eng1")
        P.encerrar(self.c, p2, "NAO_REALIZADA", "chuva forte — vala alagada", "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "Só programação PLANEJADA"):
            P.encerrar(self.c, p1, "CANCELADA", "x", "eng1")
        r = P.resumo(self.c, D, D2)
        self.assertEqual(r["contagem"], {"PLANEJADA": 0, "REALIZADA": 1, "NAO_REALIZADA": 1, "CANCELADA": 0})

    def test_faltantes_previsto_reservado_disponivel_e_a_receber(self):
        S.entrada_material(self.c, D, TUBO, 25, "ROMANEIO_CAESB", "ROM", "almox1")
        P.programar(self.c, D2, "Zona01", "TRECHO", TR, "ASSENTAMENTO", "eng1", materiais=[{"material_id": TUBO, "quantidade": 30}])
        P.programar(self.c, D2, "Zona02", "TRECHO", "Zona02_PB04_Rede_TR036", "ASSENTAMENTO", "eng1",
                    materiais=[{"material_id": TUBO, "quantidade": 10}])
        S.reservar(self.c, D2, "Zona01", TUBO, 5)
        f = {x["material_id"]: x for x in P.faltantes(self.c, D, D2)}[TUBO]
        self.assertEqual((f["previsto"], f["reservado"], f["disponivel"], f["faltante"]), (40, 5, 20, 15))
        self.assertEqual(P.faltantes(self.c, D, D2, frente="Zona02")[0]["previsto"], 10)   # filtro por frente

    def test_camadas_do_mapa_a_partir_dos_registros(self):
        tr2 = "Zona02_PB04_Rede_TR036"
        P.programar(self.c, D, "Zona01", "TRECHO", TR, "ASSENTAMENTO", "eng1")
        S.entrada_material(self.c, D, TUBO, 50, "ROMANEIO_CAESB", "ROM", "almox1")
        S.reservar(self.c, D2, "Zona02", TUBO, 5, "TRECHO", tr2)
        cam = P.camadas_mapa(self.c, D)
        self.assertEqual(cam["planejado"][TR]["hoje"], True)
        self.assertEqual(cam["material"], {tr2: "RESERVADO"})
        S.checkin(self.c, D, "Zona01", "TRECHO", TR, materiais=[{"material_id": TUBO, "quantidade": 10}])
        cam = P.camadas_mapa(self.c, D)
        self.assertNotIn(TR, cam["planejado"])                                        # realizada sai do planejado
        self.assertEqual(cam["material"][TR], "COM_EQUIPE")
        self.ap(("ASSENTADO", 0, 30), ("CADASTRO_CAMPO", 0, 10))
        self.ap(("REATERRADO", 0, 20))
        S.abrir_ocorrencia(self.c, "TRECHO", TR, "IMPEDIMENTO", "CHUVA", "Vala alagada", D, "enc1")
        cam = P.camadas_mapa(self.c, D)
        self.assertEqual(cam["cadastro"][TR], "LEVANTAMENTO_PARCIAL")
        self.assertEqual(cam["pendencias"][TR], 2)                                   # ocorrência + reaterro sem cadastro


class TestPlanejamentoPeloHTTP(BaseHTTP):
    def test_permissao_frente_e_estado_do_mapa(self):
        enc, eng = self.cliente("enc1"), self.cliente("eng1")
        corpo = {"data": D2, "equipe_id": "Zona01", "linhas": [TR], "servico": "ASSENTAMENTO"}   # o dia da equipe (Dados da obra)
        self.assertEqual(enc.post("/api/dados-obra/programar", corpo)[0], 403)
        st, r = eng.post("/api/dados-obra/programar", corpo)
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT criada_por FROM programacoes"), [("eng1",)])
        self.assertEqual(eng.post("/api/programacao", corpo)[0], 404)              # a tela Programação das equipes saiu
        st, est = eng.get(f"/api/dados-obra/estado?data={D2}")
        self.assertEqual(list(est["programado"]), [TR])
        st, z1 = eng.get("/api/resumo?frente=Zona01")
        self.assertEqual(z1["trechos"], self.q("SELECT COUNT(*) FROM trechos WHERE vigente=1 AND frente_id='Zona01'")[0][0])
        self.assertLess(z1["trechos"], eng.get("/api/resumo")[1]["trechos"])
        st, m = eng.get(f"/api/mapa/estado?data={D2}")
        self.assertIn(TR, m["camadas"]["planejado"])
        st, d = eng.get(f"/api/detalhe?tipo=TRECHO&id={TR}")                        # o detalhe do mapa mostra a programação
        self.assertEqual([(p["data"], p["servico"], p["status"]) for p in d["programacoes"]], [(D2, "ASSENTAMENTO", "PLANEJADA")])


if __name__ == "__main__":
    unittest.main()
