"""Dados da obra (grupo Planejamento): a seleção no mapa (o trecho físico inteiro e o nó que liga dois trechos escolhidos),
a programação por período (lote), a liberação do material do dia pelo almoxarife (check-in novo ou somado ao do dia), a
reserva para um dia que ainda não chegou, a devolução (check-out) e o que pinta o mapa e o Mapa iluminado. Planilhas
SINTÉTICAS: TR001 (NÓ1.8 → NÓ2.7) e TR002 (NÓ2.7 → DF-33); o teste acrescenta o TR003 (DF-33 → NÓ3.1)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import dados_obra as DO  # noqa: E402
import planejamento as P  # noqa: E402
import relogio as RL  # noqa: E402
import servicos as S  # noqa: E402
import topologia as TP  # noqa: E402
from test_acesso import TR, BaseHTTP  # noqa: E402

TR2, TR3 = "Zona01_PB01_Rede_TR002", "Zona01_PB01_Rede_TR003"
DF33, NO27 = "Zona01_PB01_Rede_DF-33", "Zona01_PB01_Rede_NÓ2.7"
TUBO, TE = "CAESB-PEAD-DE63", "1.2_1.14.53"
SEG, SAB, DOM = "2026-10-12", "2026-10-17", "2026-10-18"          # segunda, sábado e domingo da mesma semana
D = "2026-10-15"


class BaseDadosObra(BaseHTTP):
    usuarios = BaseHTTP.usuarios

    def setUp(self):
        super().setUp()
        self.c.execute("""INSERT INTO trechos(id, ponto, vigente, frente_id, de_mm, material, metodologia, extensao_m, quantidades,
                          no_ini, no_fim) VALUES ('TR-00099', ?, 1, 'Zona01', 63, 'PEAD', 'VCA', 20, '{}', ?, 'Zona01_PB01_Rede_NÓ3.1')""",
                       (TR3, DF33))
        TP._CACHE.clear()

    def prog(self, alvo_nome, data):
        return self.q("""SELECT p.status, p.checkin_id FROM programacoes p LEFT JOIN trechos t ON p.alvo_tipo='TRECHO' AND t.id=p.alvo_id
                         LEFT JOIN atividades a ON p.alvo_tipo='ATIVIDADE' AND a.id=p.alvo_id
                         WHERE COALESCE(t.ponto, a.nomenclatura)=? AND p.data=?""", alvo_nome, data)


class TestSelecao(BaseDadosObra):
    def test_no_que_liga_dois_trechos_escolhidos_entra_sozinho(self):
        r = DO.selecao(self.c, [TR2, TR3], data=D, equipe="Zona01")
        self.assertEqual([(n["nome"], n["automatico"], n["liga"]) for n in r["nos"]], [(DF33, True, ["TR002", "TR003"])])
        mat = {m["material_id"]: m for m in r["materiais"]}
        self.assertEqual((mat[TUBO]["previsto"], mat[TUBO]["sugerido"]), (95.07, 95.07))     # 75,07 + 20 m de tubo
        self.assertEqual(mat[TE]["previsto"], 1)                                               # o tê do DF-33 (06.2)
        self.assertEqual((mat[TE]["liberavel"], mat[TE]["falta_no_almox"]), (0, 1))            # sem estoque: sugere 0 e avisa
        self.assertEqual(r["totais"], {"trechos_fisicos": 2, "linhas": 2, "nos": 1, "extensao_m": 95.07, "falta_assentar_m": 95.07})
        self.assertEqual(DO.selecao(self.c, [TR2])["nos"], [])                                 # um trecho só: nenhum nó entra
        manual = DO.selecao(self.c, [TR2], [DF33])["nos"]
        self.assertEqual([(n["nome"], n["automatico"]) for n in manual], [(DF33, False)])
        r = DO.selecao(self.c, [TR, TR2])                                                      # o NÓ2.7 não está na 06.2
        self.assertEqual(r["nos"], [])
        self.assertIn("NÓ2.7 liga TR001 e TR002", r["avisos"][0])

    def test_assentado_e_material_com_a_equipe_reduzem_a_sugestao(self):
        for turno in ("MANHA", "TARDE"):
            S.registrar_clima(self.c, D, "Zona01", turno, "SOL")
        S.apontar(self.c, D, "Zona01", "TRECHO", TR2, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 30}])
        S.entrada_material(self.c, D, TUBO, 100, "ROMANEIO_CAESB", "ROM 1", "almox1")
        S.checkin(self.c, D, "Zona01", "TRECHO", TR, materiais=[{"material_id": TUBO, "quantidade": 10}])
        r = DO.selecao(self.c, [TR2], data=D, equipe="Zona01")
        t = r["linhas"][0]
        self.assertEqual((t["assentado_m"], t["falta_assentar_m"]), (30, 45.07))
        m = r["materiais"][0]
        self.assertEqual((m["previsto"], m["com_equipe"], m["sugerido"], m["disponivel"], m["liberavel"]), (45.07, 10, 35.07, 90, 35.07))
        self.assertEqual([c["equipe_id"] for c in r["checkins"]], ["Zona01"])                # o check-in aberto da equipe

    def test_linha_puxa_o_trecho_fisico_inteiro(self):
        pasta = tempfile.mkdtemp()
        antigo = TP.CONFIG, TP.CONFIG_PROGRAMA
        try:
            TP.CONFIG = TP.CONFIG_PROGRAMA = os.path.join(pasta, "topologia.json")
            with open(TP.CONFIG, "w", encoding="utf-8") as f:
                json.dump({"juncoes": [{"id": "J1", "tipo": "CRUZAMENTO", "no": NO27, "decisao": "JUNTAR",
                                        "pontas": [{"trecho": TR, "lado": "fim"}, {"trecho": TR2, "lado": "ini"}]}], "pendencias": []}, f)
            TP._CACHE.clear()
            r = DO.selecao(self.c, [TR])
            self.assertEqual([f["membros"] for f in r["fisicos"]], [[TR, TR2]])
            self.assertEqual([t["ponto"] for t in r["linhas"]], [TR, TR2])
            self.assertEqual(r["nos"], [])                           # o NÓ2.7 é cruzamento, não ponta do trecho físico
            x = DO.programar(self.c, [TR], [], "Zona01", "ASSENTAMENTO", SEG, "eng1")
            self.assertEqual((x["criadas"], x["alvos"]), (2, 2))
        finally:
            TP.CONFIG, TP.CONFIG_PROGRAMA = antigo
            TP._CACHE.clear()
            shutil.rmtree(pasta)

    def test_trecho_inexistente_ou_retirado(self):
        with self.assertRaisesRegex(S.RegraViolada, "não encontrado"):
            DO.selecao(self.c, ["Zona01_PB01_Rede_TR999"])
        self.c.execute("UPDATE trechos SET vigente=0 WHERE ponto=?", (TR3,))
        TP._CACHE.clear()
        with self.assertRaisesRegex(S.RegraViolada, "não encontrado|retirado"):
            DO.selecao(self.c, [TR3])


class TestProgramacaoDoDia(BaseDadosObra):
    """O Dados da obra é o DIA da equipe (o macro é o Cronograma): programar vale para um dia só."""
    def test_um_dia_lote_confirmacao_e_cancelamento(self):
        x = DO.programar(self.c, [TR2, TR3], [], "Zona01", "ASSENTAMENTO", SEG, "eng1")
        self.assertEqual((x["criadas"], x["alvos"], x["data"]), (3, 3, SEG))       # TR002, TR003 e o DF-33 que os liga
        self.assertEqual(self.n("programacoes", "criada_em=? AND criada_por='eng1'", x["lote"].split("|")[0]), 3)
        with self.assertRaisesRegex(S.RegraViolada, "Nada novo"):
            DO.programar(self.c, [TR2, TR3], [], "Zona01", "ASSENTAMENTO", SEG, "eng1")
        y = DO.programar(self.c, [TR2, TR3], [], "Zona01", "ASSENTAMENTO", DOM, "eng1", obs="mutirão")
        self.assertEqual((y["criadas"], y["data"]), (3, DOM))
        # outra equipe no mesmo trecho e dia: pede confirmação e não grava nada; confirmada, grava
        r = DO.programar(self.c, [TR2], [], "Zona02", "REATERRO", SEG, "eng1")
        self.assertIn("Zona 01 · PB01 · TR002 (equipe Zona01)", r["confirmar"])
        self.assertEqual(self.n("programacoes", "equipe_id='Zona02'"), 0)
        self.assertEqual(DO.programar(self.c, [TR2], [], "Zona02", "REATERRO", SEG, "eng1", confirmar=True)["criadas"], 1)
        for args, msg in (((TR2, "VOAR", "Zona01", SEG), "Serviço inválido"), ((TR2, "REATERRO", "ZonaXX", SEG), "Equipe não cadastrada"),
                          ((None, "REATERRO", "Zona01", SEG), "ao menos um trecho"), ((TR2, "REATERRO", "Zona01", "amanhã"), "inválida")):
            with self.assertRaisesRegex(S.RegraViolada, msg):
                DO.programar(self.c, [args[0]] if args[0] else [], [], args[2], args[1], args[3], "eng1")
        e = DO.estado(self.c, SEG)
        self.assertEqual(e["programado"][TR2][0], {"equipe": "Zona01", "servico": "ASSENTAMENTO", "tipo": "TRECHO", "de": SEG,
                                                   "ate": DOM, "dias": 2, "hoje": True})
        self.assertIn(DF33, e["programado"])
        self.assertEqual(sorted(l["dias"] for l in e["lotes"]), [1, 1, 1])
        self.assertEqual(DO.cancelar_lote(self.c, x["lote"], "chuva", "eng1"), 3)
        self.assertEqual(self.prog(TR2, SEG), [("CANCELADA", None), ("PLANEJADA", None)])   # a da Zona02 continua
        with self.assertRaisesRegex(S.RegraViolada, "Nada a cancelar"):
            DO.cancelar_lote(self.c, x["lote"], "de novo", "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "motivo"):
            DO.cancelar_lote(self.c, y["lote"], " ", "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "Lote inválido"):
            DO.cancelar_lote(self.c, "abc", "x", "eng1")


class TestLiberacaoEDevolucao(BaseDadosObra):
    def setUp(self):
        super().setUp()
        S.entrada_material(self.c, D, TUBO, 200, "ROMANEIO_CAESB", "ROM 1", "almox1")

    def test_liberar_abre_o_checkin_soma_no_mesmo_dia_e_realiza_a_programacao(self):
        DO.programar(self.c, [TR2, TR3], [], "Zona01", "ASSENTAMENTO", D, "eng1")
        DO.programar(self.c, [TR], [], "Zona01", "ESCAVACAO", D, "eng1")
        x = DO.liberar(self.c, D, "Zona01", [TR2, TR3], [], [{"material_id": TUBO, "quantidade": 50}, {"material_id": TUBO, "quantidade": 0}], "almox1")
        self.assertEqual((x["novo"], x["itens"], x["programacoes_realizadas"]), (True, 1, 3))
        ck = x["checkin_id"]
        self.assertEqual(self.q("SELECT alvo_tipo, alvo_id, encerrado FROM checkins WHERE id=?", ck), [("TRECHO", "TR-00002", 0)])
        self.assertEqual(self.prog(DF33, D), [("REALIZADA", ck)])
        self.assertEqual(self.prog(TR, D), [("PLANEJADA", None)])                   # outro trecho: ainda não
        campo = P.em_campo(self.c, D)
        self.assertEqual({n: c["equipe"] for n, c in campo.items()}, {TR2: "Zona01", TR3: "Zona01", DF33: "Zona01"})
        y = DO.liberar(self.c, D, "Zona01", [TR], [], [{"material_id": TUBO, "quantidade": 10}], "almox1")
        self.assertEqual((y["novo"], y["checkin_id"], y["programacoes_realizadas"]), (False, ck, 1))
        self.assertEqual(S.custodia_equipe(self.c, "Zona01", TUBO), 60)
        self.assertIn(TR, P.em_campo(self.c, D))
        est = DO.estado(self.c, D)
        self.assertEqual([(c["id"], c["materiais"][0]["quantidade"]) for c in est["checkins"]], [(ck, 60)])
        self.assertEqual(est["em_campo"][TR3]["checkin_id"], ck)
        self.assertEqual(P.camadas_mapa(self.c, D)["em_campo"][TR2]["equipe"], "Zona01")
        # o check-in cobre todos os trechos do dia (v20); o pino da equipe vai em cada um
        self.assertEqual(self.q("SELECT a.alvo_id, a.origem FROM checkin_alvos a WHERE checkin_id=? ORDER BY rowid", ck),
                         [("TR-00002", "PROGRAMACAO"), ("TR-00099", "PROGRAMACAO"), (self.q("SELECT id FROM atividades WHERE nomenclatura=?", DF33)[0][0], "PROGRAMACAO"),
                          ("TR-00001", "PROGRAMACAO")])
        self.assertEqual(sorted(p["alvo_id"] for p in S.estado_mapa(self.c, data=D)["pins"]), sorted([TR, TR2, TR3, DF33]))
        S.checkout(self.c, ck, [{"material_id": TUBO, "aplicado": 45, "sobra": 15}])     # devolução do fim do dia
        self.assertEqual((S.saldo_almox(self.c, TUBO)[0], S.custodia_equipe(self.c, "Zona01", TUBO)), (155, 0))
        self.assertEqual(P.em_campo(self.c, D), {})
        self.assertEqual(S.estado_mapa(self.c, data=D)["pins"], [])                     # fechar a devolução tira o pino

    def test_trecho_fora_da_programacao_entra_na_hora(self):
        DO.programar(self.c, [TR2], [], "Zona01", "ASSENTAMENTO", D, "eng1")
        ck = DO.liberar(self.c, D, "Zona01", [TR2, TR], [], [], "almox1")["checkin_id"]    # TR001 não estava programado
        self.assertEqual(self.q("SELECT alvo_id, origem FROM checkin_alvos WHERE checkin_id=? ORDER BY rowid", ck),
                         [("TR-00002", "PROGRAMACAO"), ("TR-00001", "CHECKIN")])
        self.assertEqual(set(P.em_campo(self.c, D)), {TR, TR2})

    def test_recusas_da_liberacao(self):
        with self.assertRaisesRegex(S.RegraViolada, "data futura"):
            DO.liberar(self.c, (RL.hoje() + timedelta(days=2)).isoformat(), "Zona01", [TR2], [], [], "almox1")
        with self.assertRaisesRegex(S.RegraViolada, "trecho em que a equipe vai trabalhar"):
            DO.liberar(self.c, D, "Zona01", [], [], [], "almox1")
        with self.assertRaisesRegex(S.RegraViolada, "Disponível insuficiente"):
            DO.liberar(self.c, D, "Zona01", [TR2], [], [{"material_id": TUBO, "quantidade": 500}], "almox1")
        self.assertEqual(self.n("checkins"), 0)                                     # tudo ou nada
        with self.assertRaisesRegex(S.RegraViolada, "consumo"):
            DO.liberar(self.c, D, "Zona01", [TR2], [], [{"material_id": "CONS-AREIA", "quantidade": 1}], "almox1")
        DO.liberar(self.c, D, "Zona01", [TR2], [], [], "almox1")
        with self.assertRaisesRegex(S.RegraViolada, "check-in aberto em 2026-10-15"):
            DO.liberar(self.c, "2026-10-16", "Zona01", [TR2], [], [], "almox1")

    def test_reserva_para_dia_que_ainda_nao_chegou(self):
        dia = (RL.hoje() + timedelta(days=3)).isoformat()
        x = DO.reservar(self.c, dia, "Zona01", [TR2, TR3], [], [{"material_id": TUBO, "quantidade": 40}, {"material_id": TE, "quantidade": 0}], "almox1")
        self.assertEqual(len(x["reservas"]), 1)
        self.assertEqual(self.q("SELECT data, alvo_tipo, alvo_id, quantidade, responsavel FROM reservas"), [(dia, "TRECHO", "TR-00002", 40, "almox1")])
        self.assertEqual(S.disponivel(self.c, TUBO), 160)
        with self.assertRaisesRegex(S.RegraViolada, "ao menos um material"):
            DO.reservar(self.c, dia, "Zona01", [TR2], [], [], "almox1")


class TestHTTPDadosObra(BaseDadosObra):
    def test_quem_programa_quem_libera_e_quem_consulta(self):
        eng, almox, enc = self.cliente("eng1"), self.cliente("almox1"), self.cliente("enc1")
        sel = f"/api/dados-obra/selecao?linhas={TR2},{TR3}&data={D}&equipe=Zona01"
        st, r = almox.get(sel)
        self.assertEqual((st, [n["nome"] for n in r["nos"]]), (200, [DF33]))
        self.assertEqual(enc.get(sel)[0], 403)                                      # o encarregado não abre o Dados da obra
        prog = {"linhas": [TR2, TR3], "equipe_id": "Zona01", "servico": "ASSENTAMENTO", "data": D}
        self.assertEqual(almox.post("/api/dados-obra/programar", prog)[0], 403)     # programar é da engenharia
        st, x = eng.post("/api/dados-obra/programar", prog)
        self.assertEqual((st, x.get("criadas")), (200, 3), x)
        self.assertEqual(self.q("SELECT DISTINCT criada_por FROM programacoes"), [("eng1",)])
        self.assertEqual(eng.post("/api/entrada-qualquer", {})[0], 404)
        self.assertEqual(almox.post("/api/dados-obra/cancelar-lote", {"lote": x["lote"], "motivo": "x"})[0], 403)
        S.entrada_material(self.c, D, TUBO, 100, "ROMANEIO_CAESB", "ROM 1", "almox1")
        lib = {"linhas": [TR2, TR3], "data": D, "equipe_id": "Zona01", "materiais": [{"material_id": TUBO, "quantidade": 30}]}
        self.assertEqual(enc.post("/api/dados-obra/liberar", lib)[0], 403)
        st, y = almox.post("/api/dados-obra/liberar", lib)
        self.assertEqual((st, y.get("novo"), y.get("programacoes_realizadas")), (200, True, 3), y)
        st, est = almox.get(f"/api/dados-obra/estado?data={D}")
        self.assertEqual((st, sorted(est["em_campo"])), (200, sorted([TR2, TR3, DF33])))
        st, mapa = enc.get(f"/api/mapa/estado?data={D}")                            # o Mapa iluminado vê a equipe em campo
        self.assertEqual((st, mapa["camadas"]["em_campo"].get(TR3, {}).get("equipe")), (200, "Zona01"))
        st, _ = almox.post("/api/checkout", {"checkin_id": y["checkin_id"], "itens": [{"material_id": TUBO, "aplicado": 25, "sobra": 5}]})
        self.assertEqual(st, 200)
        self.assertEqual(almox.get("/api/almox/quarentena")[0], 200)
        self.assertEqual(enc.get("/api/almox/quarentena")[0], 403)
        self.assertEqual(almox.get("/api/estoque")[0], 200)


if __name__ == "__main__":
    unittest.main()
