"""NS do dia (diário de obra pela nota de serviço): o encarregado envia a NS executada e o croqui; o sistema lê, casa com
os trechos e lança sozinho o que é inequívoco; o resto vai para a fila da engenharia. Pelo HTTP, sobre a base real
(tests/base_real.py), com NS sintéticas: segmento inteiro, parcial, parada (sentido pela programação do dia),
continuação e trecho já lançado, reaterro e escavação, MND, conexão no meio da linha, sem etapa escrita, recusas,
permissões, anulação e o Diário de obra."""
import os
import sys
import unittest
from datetime import timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import dados_obra as DO  # noqa: E402
import notas_servico as NS  # noqa: E402
import ns_sintetica as NSS  # noqa: E402
import relogio as RL  # noqa: E402
import servicos as S  # noqa: E402
from base_real import TR006, BaseReal, b64, data_ns  # noqa: E402

HOJE = RL.hoje()
ONTEM, ANTEONTEM = HOJE - timedelta(days=1), HOJE - timedelta(days=2)
CLIMA = {"MANHA": "SOL", "TARDE": "CHUVA_FRACA_TENDA"}
CROQUI = b64(NSS.pdf_de_texto(["CROQUI DO DIA - TRECHOS EXECUTADOS"]))
TITULO = '"REDE DE ÁGUA" - ZONA 03 - PB08 - NOTA DO DIA'


def grupo(elementos, distancias, obs=None, titulo="REDE ZONA 03 - PB08 - PEAD DE 160", material="PEAD-160", inicio=0.0):
    return NSS.grupo_padrao(titulo, elementos, distancias, obs=obs, material=material, segmentos=False, inicio=inicio)


def pdf_dia(grupos, numero="015", data=ONTEM, titulo=TITULO, contrato="10239/2026", girar=False):
    return NSS.pdf_de_texto(NSS.paginas_ns(numero=numero, contrato=contrato, data=data_ns(data), titulo=titulo, bloco="EXECUÇÃO",
                                           grupos=grupos), girar=girar)


class BaseDia(BaseReal):
    def enviar(self, login, pdf, equipe="Zona03", croqui=CROQUI, clima=CLIMA, **kw):
        corpo = dict(pdf_b64=b64(pdf), pdf_nome="ns_do_dia.pdf", croqui_b64=croqui, croqui_nome="croqui.jpg", clima=clima, **kw)
        if equipe:
            corpo["equipe_id"] = equipe
        return self.cli(login).post("/api/ns/dia", corpo)

    def gravado(self, etapa="ASSENTADO"):
        """[(linha, ini, fim)] efetivos da etapa (assentado e reaterro) ou da escavação."""
        if etapa == "ESCAVADO":
            sql = ("SELECT t.ponto, e.ini_m, e.fim_m FROM etapas_complementares e JOIN trechos t ON t.id=e.trecho_id "
                   "WHERE e.etapa='ESCAVADO' AND e.anulado_em IS NULL ORDER BY t.ponto, e.ini_m")
            return [(NS._curto(p), a, b) for p, a, b in self.c.execute(sql)]
        sql = ("SELECT t.ponto, i.ini_m, i.fim_m FROM intervalos_execucao i JOIN trechos t ON t.id=i.trecho_id "
               "WHERE i.etapa=? AND i.anulado_por IS NULL ORDER BY t.ponto, i.ini_m")
        return [(NS._curto(p), a, b) for p, a, b in self.c.execute(sql, (etapa,))]

    def programar(self, linhas, data, equipe="Zona03"):
        DO.programar(self.c, linhas, [], equipe, "ASSENTAMENTO", data.isoformat(), "eng1")


class TestLancamento(BaseDia):
    def test_segmento_inteiro_lancado_sozinho_nas_duas_linhas(self):
        r = self.ok(self.enviar("enc3", pdf_dia([grupo(["NÓ9.1 - TÊ 160x160", "CH_VRP-15 (CAIXA DA VRP)"], [295.98],
                                                       obs=["ASSENTAMENTO", None])])))
        self.assertEqual((r["tipo"], r["equipe_id"], r["data"], r["fila"], r["arquivo_trocado"]), ("EXECUCAO", "Zona03", ONTEM.isoformat(), [], False))
        s = r["segmentos"][0]
        self.assertEqual((s["situacao"], s["fisico_id"], s["etapas"], s["origem_sentido"]), ("AUTOMATICO", "TF-00337", ["ASSENTADO"], "NS"))
        self.assertEqual(self.gravado(), [("TR006", 0.0, 293.47), ("TR007", 0.0, 2.51)])
        lin = self.c.execute("""SELECT i.informado_por, i.ns_segmento_id, i.origem, i.referencia, i.equipe_id, a.estaca_ini, a.estaca_fim,
                                       a.informado_por FROM intervalos_execucao i JOIN apontamentos a ON a.id=i.apontamento_id""").fetchall()
        self.assertEqual({tuple(x) for x in lin}, {("enc3", s["id"], "INFORMADO", "NS 015 fl. 01/01", "Zona03", "NS 015 · 0+0,00",
                                                     "14+15,98", "enc3")})
        self.assertEqual(self.n("clima", "equipe_id='Zona03' AND data=?", ONTEM.isoformat()), 2)    # o único toque da tela
        doc = self.c.execute("SELECT tipo FROM documentos WHERE id=?", (r["croqui_id"],)).fetchone()[0]
        self.assertEqual(doc, "NS_CROQUI")

    def test_distancia_menor_e_execucao_parcial(self):
        r = self.ok(self.enviar("enc3", pdf_dia([grupo(["NÓ9.1", "CH_VRP-15"], [122.01], obs=["ASSENTAMENTO", None])])))
        s = r["segmentos"][0]
        self.assertEqual((s["situacao"], s["ini_fisico_m"], s["fim_fisico_m"], r["fila"]), ("AUTOMATICO", 0.0, 122.01, []))
        self.assertIn("execução parcial: 122,01 de 295,98 m, a partir do NÓ9.1", s["motivo"])
        self.assertEqual(self.gravado(), [("TR006", 0.0, 119.5), ("TR007", 0.0, 2.51)])

    def test_parada_pela_programacao_do_dia_e_sem_ela_a_engenharia_confere(self):
        parada = [grupo(["NÓ9.1 - TÊ 160x160", ""], [122.01], obs=["ASSENTAMENTO", "PARADA"])]
        r = self.ok(self.enviar("enc3", pdf_dia(parada, numero="020", data=ANTEONTEM)))            # sem programação: fila
        s = r["segmentos"][0]
        self.assertEqual((s["situacao"], r["fila"], self.gravado()), ("CONFIRMAR", [1], []))
        self.assertEqual(sorted(c["fisico_id"] for c in s["candidatos"]), ["TF-00337", "TF-00351"])
        ver = self.ok(self.cli("enc3").get(f"/api/ns/dia?data={ANTEONTEM.isoformat()}"))
        self.assertEqual([x["fila"] for x in ver], [[1]])                                          # "aguardando a engenharia"
        k = next(i for i, c in enumerate(s["candidatos"]) if c["fisico_id"] == "TF-00337")
        self.assertEqual(self.cli("enc3").post("/api/ns/dia/conferir", {"ns_id": r["id"], "decisoes": []})[0], 403)
        r = self.ok(self.cli("eng1").post("/api/ns/dia/conferir", {"ns_id": r["id"], "decisoes": [{"ordem": 1, "acao": "ACEITAR",
                                                                                                    "candidato": k}]}))
        self.assertEqual((r["segmentos"][0]["situacao"], r["segmentos"][0]["origem_sentido"], r["fila"]), ("CONFIRMADO", "ENGENHARIA", []))
        self.assertEqual(self.gravado(), [("TR006", 0.0, 119.5), ("TR007", 0.0, 2.51)])
        self.assertEqual(self.c.execute("SELECT DISTINCT informado_por FROM intervalos_execucao").fetchall()[0][0], "enc3")
        self.ok(self.cli("eng1").post("/api/ns/dia/conferir", {"ns_id": r["id"]}))                 # repetir não duplica
        self.assertEqual(len(self.gravado()), 2)

    def test_parada_com_programacao(self):
        self.programar([TR006], ONTEM)
        r = self.ok(self.enviar("enc3", pdf_dia([grupo(["NÓ9.1 - TÊ 160x160", ""], [122.01], obs=["ASSENTAMENTO", "ATÉ AQUI"])])))
        s = r["segmentos"][0]
        self.assertEqual((s["situacao"], s["origem_sentido"], r["fila"]), ("AUTOMATICO", "PROGRAMACAO", []))
        self.assertIn("sentido da programação do dia da equipe", s["avisos"])
        self.assertEqual(self.gravado(), [("TR006", 0.0, 119.5), ("TR007", 0.0, 2.51)])

    def test_continuacao_do_dia_anterior_e_trecho_ja_lancado(self):
        titulo = "REDE ZONA 03 - PB08 - PEAD DE 160 (NÓ9.1 - VRP-15)"            # o título diz para onde a rede vai
        self.ok(self.enviar("enc3", pdf_dia([grupo(["NÓ9.1", ""], [122.01], obs=["ASSENTAMENTO", "PARADA"], titulo=titulo)],
                                            numero="030", data=ANTEONTEM)))
        self.assertEqual(self.gravado(), [("TR006", 0.0, 119.5), ("TR007", 0.0, 2.51)])
        # continuação: a 1ª linha é a estaca onde parou (sem elemento); as posições contam a partir do VRP-15
        r = self.ok(self.enviar("enc3", pdf_dia([grupo(["", "CH_VRP-15"], [173.97], obs=["ASSENTAMENTO", None], titulo=titulo,
                                                       inicio=122.01)], numero="031")))
        s = r["segmentos"][0]
        self.assertEqual((s["situacao"], s["ini_fisico_m"], s["fim_fisico_m"], r["fila"]), ("AUTOMATICO", 122.01, 295.98, []))
        self.assertEqual(self.gravado(), [("TR006", 0.0, 119.5), ("TR006", 119.5, 293.47), ("TR007", 0.0, 2.51)])
        # o trecho inteiro de novo: nada é lançado duas vezes, e a resposta diz quanto já estava
        r = self.ok(self.enviar("enc3", pdf_dia([grupo(["NÓ9.1", "CH_VRP-15"], [295.98], obs=["ASSENTAMENTO", None])], numero="032")))
        s = r["segmentos"][0]
        self.assertEqual((s["situacao"], s["agora"]["ja"], r["fila"]), ("AUTOMATICO", {"ASSENTADO": 295.98}, []))
        self.assertEqual(len(self.gravado()), 3)

    def test_reaterro_so_sobre_o_assentado_e_escavacao_complementar(self):
        self.ok(self.enviar("enc3", pdf_dia([grupo(["NÓ9.1", "CH_VRP-15"], [122.01], obs=["ESCAVAÇÃO E ASSENTAMENTO", None])],
                                            numero="040", data=ANTEONTEM)))
        self.assertEqual(self.gravado("ESCAVADO"), [("TR006", 0.0, 119.5), ("TR007", 0.0, 2.51)])
        self.assertEqual(self.n("etapas_complementares", "ns_segmento_id IS NOT NULL AND etapa='ESCAVADO'"), 2)
        r = self.ok(self.enviar("enc3", pdf_dia([grupo(["NÓ9.1", "CH_VRP-15"], [295.98], obs=["REATERRO", None])], numero="041")))
        self.assertEqual(self.gravado("REATERRADO"), [("TR006", 0.0, 119.5), ("TR007", 0.0, 2.51)])
        s = r["segmentos"][0]
        self.assertIn("reaterro sem assentamento", s["pendente"])
        self.assertEqual((s["pendente_m"], r["fila"]), (173.97, [1]))                              # o resto espera o assentado

    def test_mnd_sem_vala_pula_escavacao_e_reaterro(self):
        z9 = '"REDE DE ÁGUA" - ZONA 09 - PB16 - NOTA DO DIA'
        r = self.ok(self.enviar("eng1", pdf_dia([grupo(["NÓ59.1", "NÓ1.1"], [567.7], obs=["ESCAVAÇÃO, ASSENTAMENTO E REATERRO", None],
                                                       titulo="REDE ZONA 09 - PB16", material="PEAD-63")], numero="050", titulo=z9),
                                equipe="Zona09"))
        s = r["segmentos"][0]
        self.assertEqual((s["situacao"], s["fisico_id"], r["fila"]), ("AUTOMATICO", "TF-01016", []))
        self.assertEqual(s["agora"]["pulado"], ["TR002 é MND (sem vala): reaterrado e escavado não se aplicam; o assentado vale"])
        self.assertEqual([x[0] for x in self.gravado()], ["TR002", "TR003", "TR004", "TR011"])
        self.assertEqual([x[0] for x in self.gravado("REATERRADO")], ["TR003", "TR004", "TR011"])
        self.assertEqual([x[0] for x in self.gravado("ESCAVADO")], ["TR003", "TR004", "TR011"])

    def test_conexao_no_meio_da_linha_e_sem_etapa_escrita(self):
        z4 = '"REDE DE ÁGUA" - ZONA 04 - PB02 - NOTA DO DIA'
        r = self.ok(self.enviar("eng1", pdf_dia([grupo(["NÓ56.1", "VTF-22 (VENTOSA)", "CH_VM-4.2"], [31.24, 8.26], titulo="REDE ZONA 04 - PB02")],
                                                numero="060", titulo=z4), equipe="Zona04"))
        self.assertEqual([(s["situacao"], s["ini_fisico_m"], s["fim_fisico_m"]) for s in r["segmentos"]],
                         [("AUTOMATICO", 0.0, 31.24), ("AUTOMATICO", 31.24, 39.5)])
        self.assertEqual(self.gravado(), [("TR019", 0.0, 31.24), ("TR019", 31.24, 39.5)])
        self.assertIn(NS.SEM_ETAPA, r["avisos"])
        self.assertTrue(any("VTF-22 é conexão no meio do TR019" in a for a in r["segmentos"][0]["avisos"]))

    def test_par_de_nos_repetido_vai_para_a_fila_e_a_engenharia_confere(self):
        r = self.ok(self.enviar("enc3", pdf_dia([grupo(["NÓ56.1", "NÓ8.1"], [32.4], titulo="REDE ZONA 03")], numero="070",
                                                titulo='"REDE DE ÁGUA" - ZONA 03 - NOTA DO DIA')))
        self.assertEqual((r["segmentos"][0]["situacao"], r["fila"], self.gravado()), ("CONFIRMAR", [1], []))
        fila = self.ok(self.cli("eng1").get("/api/ns/dia?fila=1"))
        self.assertEqual([n["id"] for n in fila], [r["id"]])
        k = next(i for i, c in enumerate(r["segmentos"][0]["candidatos"]) if c["fisico_id"] == "TF-00365")
        errado = next(i for i, c in enumerate(r["segmentos"][0]["candidatos"]) if c["fisico_id"] == "TF-00280")
        self.recusa(self.cli("eng1").post("/api/ns/dia/conferir", {"ns_id": r["id"], "decisoes": [
            {"ordem": 1, "acao": "ACEITAR", "candidato": errado}]}), 422, "não serve")
        self.ok(self.cli("eng1").post("/api/ns/dia/conferir", {"ns_id": r["id"], "decisoes": [{"ordem": 1, "acao": "ACEITAR", "candidato": k}]}))
        self.assertEqual(self.gravado(), [("TR034", 0.0, 32.4)])
        self.assertEqual(self.ok(self.cli("eng1").get("/api/ns/dia?fila=1")), [])
        self.assertEqual(NS.registrar_dia(self.c, r["id"], "eng1")[0]["lancado"], [])            # repetir não duplica


class TestRevisao(BaseDia):
    """Achados da revisão: a ponta solta não volta sobre o segmento vizinho, o que foi tirado de propósito não volta,
    a anulação com reaterro e assentado na mesma NS e o apontamento à mão não traz verificação nem NS do navegador."""

    def test_parada_nao_volta_sobre_o_trecho_anterior(self):
        self.programar(["Zona03_PB08_Rede_TR020"], ONTEM)                  # a programação só tem o trecho de antes
        g = grupo(["NÓ6.1 - TÊ 160x110", "NÓ9.1 - TÊ 160x160", ""], [277.99, 122.01], obs=["ASSENTAMENTO", None, "PARADA"])
        r = self.ok(self.enviar("enc3", pdf_dia([g])))
        self.assertEqual([(s["fisico_id"], s["ini_fisico_m"], s["fim_fisico_m"]) for s in r["segmentos"]],
                         [("TF-00351", 0.0, 277.99), ("TF-00337", 0.0, 122.01)])
        self.assertEqual(self.gravado(), [("TR006", 0.0, 119.5), ("TR007", 0.0, 2.51), ("TR020", 0.0, 277.99)])

    def test_continuacao_nao_cai_sobre_o_trecho_seguinte(self):
        self.programar([TR006], ONTEM)
        g = grupo(["", "NÓ9.1 - TÊ 160x160", "CH_VRP-15"], [77.99, 295.98], obs=["ASSENTAMENTO", None, None], inicio=200.0)
        r = self.ok(self.enviar("enc3", pdf_dia([g])))
        self.assertEqual([(s["fisico_id"], s["ini_fisico_m"], s["fim_fisico_m"]) for s in r["segmentos"]],
                         [("TF-00351", 200.0, 277.99), ("TF-00337", 0.0, 295.98)])

    def test_o_que_foi_retificado_nao_volta_ao_conferir_a_fila(self):
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98]), grupo(["NÓ56.1", "NÓ8.1"], [32.4], titulo="REDE ZONA 03")]
        r = self.ok(self.enviar("enc3", pdf_dia(g, titulo='"REDE DE ÁGUA" - ZONA 03 - NOTA DO DIA')))
        self.recusa(self.cli("eng1").post("/api/ns/dia/conferir", {"ns_id": r["id"], "decisoes": [
            {"ordem": 1, "acao": "FORA", "motivo": "x"}]}), 422, "já tem execução")
        for (ap,) in self.c.execute("SELECT DISTINCT apontamento_id FROM intervalos_execucao WHERE anulado_por IS NULL").fetchall():
            S.retificar_intervalos(self.c, "APONTAMENTO", ap, [], "trecho medido errado na nota", "eng1")
        k = next(i for i, c in enumerate(r["segmentos"][1]["candidatos"]) if c["fisico_id"] == "TF-00365")
        self.ok(self.cli("eng1").post("/api/ns/dia/conferir", {"ns_id": r["id"], "decisoes": [
            {"ordem": 1, "acao": "FORA", "motivo": "retificado"}, {"ordem": 2, "acao": "ACEITAR", "candidato": k}]}))
        self.assertEqual(self.gravado(), [("TR034", 0.0, 32.4)])                 # o segmento 1 não foi relançado

    def test_anular_com_assentado_e_reaterro_na_mesma_nota(self):
        g = [grupo(["NÓ9.1", ""], [100.0], obs=["ASSENTAMENTO", "PARADA"], titulo="REDE ZONA 03 - PB08 - PEAD DE 160 - FRENTE A"),
             grupo(["NÓ9.1", ""], [80.0], obs=["REATERRO", "PARADA"], titulo="REDE ZONA 03 - PB08 - PEAD DE 160 - FRENTE B")]
        self.programar([TR006], ONTEM)
        r = self.ok(self.enviar("enc3", pdf_dia(g)))
        self.assertEqual(len(self.gravado("REATERRADO")), 2)
        self.ok(self.cli("enc3").post("/api/ns/dia/anular", {"ns_id": r["id"], "motivo": "nota errada"}))
        self.assertEqual((self.gravado(), self.gravado("REATERRADO")), ([], []))

    def test_apontamento_a_mao_nao_traz_verificacao_nem_ns(self):
        for t in ("MANHA", "TARDE"):
            S.registrar_clima(self.c, ONTEM.isoformat(), "Zona03", t, "SOL")
        r = self.ok(self.cli("eng1").post("/api/apontamento", {
            "data": ONTEM.isoformat(), "equipe_id": "Zona03", "alvo_tipo": "TRECHO", "alvo_id": TR006, "motivo_sem_ns": "teste",
            "intervalos": [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 10, "verificado_em": "2026-10-01", "verificado_por": "eng2",
                            "ns_segmento_id": 1}]}))
        i = self.c.execute("SELECT verificado_em, verificado_por, ns_segmento_id FROM intervalos_execucao WHERE apontamento_id=?",
                           (r["id"],)).fetchone()
        self.assertEqual(tuple(i), (None, None, None))


class TestRecusas(BaseDia):
    def test_outra_obra_data_futura_sem_texto_sem_croqui_e_sem_clima(self):
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98])]
        self.recusa(self.enviar("enc3", pdf_dia(g, contrato="9702/2024")), 422, "V01")
        self.recusa(self.enviar("enc3", pdf_dia(g, data=HOJE + timedelta(days=1))), 422, "V02")
        try:
            self.recusa(self.enviar("enc3", NSS.pdf_sem_texto()), 422, "sem camada de texto")
        except ImportError:
            pass
        self.recusa(self.enviar("enc3", pdf_dia(g), croqui=None), 422, "croqui")
        self.recusa(self.enviar("enc3", pdf_dia(g), clima=None), 422, "clima")
        self.assertEqual(self.n("notas_servico") + self.n("intervalos_execucao") + self.n("documentos"), 0)   # nada gravado
        S.registrar_clima(self.c, ONTEM.isoformat(), "Zona03", "MANHA", "SOL")
        S.registrar_clima(self.c, ONTEM.isoformat(), "Zona03", "TARDE", "SOL")
        self.ok(self.enviar("enc3", pdf_dia(g), clima=None))                                       # o clima do dia já estava

    def test_mesma_ns_duas_vezes_e_versao_assinada(self):
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98])]
        r = self.ok(self.enviar("enc3", pdf_dia(g)))
        self.recusa(self.enviar("enc3", pdf_dia(g)), 422, "já foi enviada")
        t = self.ok(self.enviar("enc3", pdf_dia(g, girar=True), croqui=None))                     # mesmo conteúdo, outro arquivo
        self.assertEqual((t["id"], t["arquivo_trocado"]), (r["id"], True))
        self.assertEqual(self.n("notas_servico", "status='SUBSTITUIDA'"), 1)
        self.recusa(self.enviar("enc3", pdf_dia([grupo(["NÓ9.1", "CH_VRP-15"], [122.01])])), 422, "anule o envio anterior")
        self.ok(self.enviar("enc3", pdf_dia([grupo(["NÓ9.1", "CH_VRP-15"], [122.01])], numero="016")))   # outra NS no mesmo dia
        self.assertEqual(len(self.gravado()), 2)

    def test_ns_enviada_com_atraso(self):
        r = self.ok(self.enviar("enc3", pdf_dia([grupo(["NÓ9.1", "CH_VRP-15"], [295.98])], data=HOJE - timedelta(days=5))))
        self.assertTrue(r["atrasada"])
        self.assertIn("NS enviada com atraso: 5 dias depois da data da nota", r["avisos"])


class TestPermissoes(BaseDia):
    def test_encarregado_envia_so_para_a_propria_equipe(self):
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98])]
        self.recusa(self.enviar("enc3", pdf_dia(g), equipe="Zona04"), 403, "Zona03")
        r = self.ok(self.enviar("enc3", pdf_dia(g), equipe=None))                                 # sem equipe: a dele
        self.assertEqual(r["equipe_id"], "Zona03")
        for rota, corpo in (("/api/ns", {"tipo": "SERVICO", "pdf_b64": b64(pdf_dia(g, numero="099"))}),
                            ("/api/ns/ler", {"tipo": "TOPOGRAFIA", "pdf_b64": b64(pdf_dia(g, numero="099"))})):
            self.assertEqual(self.cli("enc3").post(rota, corpo)[0], 403, rota)
        self.assertEqual(self.cli("enc3").post("/api/ns/anular", {"ns_id": r["id"], "motivo": "x"})[0], 403)  # NS do dia: rota própria
        # a outra equipe não vê a NS do dia nem abre o PDF dela
        self.assertEqual(self.ok(self.cli("enc1").get("/api/ns/dia?equipe=Zona03")), [])
        self.assertEqual(self.abrir("enc1", f"/api/ns/arquivo?id={r['id']}&qual=pdf")[0], 403)
        self.assertEqual(self.abrir("enc3", f"/api/ns/arquivo?id={r['id']}&qual=croqui")[0], 200)
        self.assertEqual(self.ok(self.enviar("sup1", pdf_dia(g, numero="017"), equipe="Zona04"))["equipe_id"], "Zona04")

    def test_anular_antes_e_depois_da_verificacao(self):
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98])]
        r = self.ok(self.enviar("enc3", pdf_dia(g)))
        self.recusa(self.cli("enc3").post("/api/ns/dia/anular", {"ns_id": r["id"]}), 422, "motivo")
        self.ok(self.cli("enc3").post("/api/ns/dia/anular", {"ns_id": r["id"], "motivo": "enviei a nota errada"}))
        self.assertEqual((self.gravado(), self.n("intervalos_execucao")), ([], 2))                  # anulado, não apagado
        r = self.ok(self.enviar("enc3", pdf_dia(g, numero="016")))
        iid = self.c.execute("SELECT id FROM intervalos_execucao WHERE anulado_por IS NULL LIMIT 1").fetchone()[0]
        self.ok(self.cli("eng2").post("/api/intervalo/verificar", {"intervalo_id": iid}))
        self.recusa(self.cli("enc3").post("/api/ns/dia/anular", {"ns_id": r["id"], "motivo": "x"}), 403, "verificado")
        self.ok(self.cli("eng1").post("/api/ns/dia/anular", {"ns_id": r["id"], "motivo": "trecho refeito"}))
        self.assertEqual(self.gravado(), [])


class TestDiarioDeObra(BaseDia):
    def test_diario_com_ns_croqui_fila_programado_e_alertas(self):
        dia = ONTEM.isoformat()
        S.checkin(self.c, dia, "Zona01", "TRECHO", "Zona01_PB01_Rede_TR001")                      # check-in sem NS do dia
        self.programar([TR006, "Zona03_PB08_Rede_TR020"], ONTEM)
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98], obs=["ASSENTAMENTO", None]),
             grupo(["NÓ56.1", "NÓ8.1"], [32.4], titulo="REDE ZONA 03")]
        r = self.ok(self.enviar("enc3", pdf_dia(g, titulo='"REDE DE ÁGUA" - ZONA 03 - NOTA DO DIA')))   # o 2º grupo não diz a PB
        d = self.ok(self.cli("eng1").get(f"/api/diario?data={dia}"))
        self.assertEqual([(n["id"], n["croqui_id"] is not None, n["fila"]) for n in d["ns_dia"]], [(r["id"], True, [2])])
        self.assertEqual(sorted((NS._curto(x["ponto"]), x["etapa"]) for s in d["ns_dia"][0]["segmentos"] for x in s["registros"]),
                         [("TR006", "ASSENTADO"), ("TR007", "ASSENTADO")])
        pe = {NS._curto(x["nome"]): x["situacao"] for x in d["programado_executado"] if x["equipe_id"] == "Zona03"}
        self.assertEqual({k: pe.get(k) for k in ("TR006", "TR007", "TR020", "TR034")},       # o TF inteiro entra na programação
                         {"TR006": "PROGRAMADO_E_EXECUTADO", "TR007": "PROGRAMADO_E_EXECUTADO", "TR020": "PROGRAMADO_SEM_EXECUCAO",
                          "TR034": None})
        self.assertTrue(any("check-in feito e nenhuma NS do dia" in a and "ZONA 01" in a for a in d["alertas"]), d["alertas"])
        self.assertTrue(any("1 segmento(s) aguardando a engenharia" in a for a in d["alertas"]), d["alertas"])
        enc = self.ok(self.cli("enc3").get(f"/api/diario?data={dia}&equipe=Zona03"))
        self.assertEqual(len(enc["ns_dia"]), 1)

    def test_croqui_de_outra_nota_avisa_no_envio_e_no_diario(self):
        """O croqui em PDF diz outra NS: a nota é lançada do mesmo jeito, o aviso aparece no resultado do envio e vira
        alerta no Diário de obra. A planilha .xls vai junto e confere o PDF."""
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98], obs=["ASSENTAMENTO", None])]
        errado = b64(NSS.pdf_de_texto(["CROQUI DO DIA - N.S.014 - TRECHOS EXECUTADOS"]))
        args = dict(numero="015", contrato="10239/2026", data_ns=ONTEM, titulo=TITULO, bloco="EXECUÇÃO", grupos=g)
        r = self.ok(self.enviar("enc3", pdf_dia(g), croqui=errado, planilha_b64=b64(NSS.xls_de_ns(**args)),
                                planilha_nome="nota.xls"))
        self.assertEqual(self.gravado(), [("TR006", 0.0, 293.47), ("TR007", 0.0, 2.51)])
        self.assertEqual(r["avisos_croqui"], ["o croqui é da NS 014, e a nota é a 015"])
        self.assertIn("o croqui é da NS 014, e a nota é a 015", r["avisos"])
        d = self.ok(self.cli("eng1").get(f"/api/diario?data={ONTEM.isoformat()}"))
        self.assertTrue(any("confira o croqui, o croqui é da NS 014" in a for a in d["alertas"]), d["alertas"])
        self.assertEqual(self.c.execute("SELECT d.mime FROM notas_servico n JOIN documentos d ON d.id=n.planilha_id").fetchone()[0],
                         "application/vnd.ms-excel")


if __name__ == "__main__":
    unittest.main()
