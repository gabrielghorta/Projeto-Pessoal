"""Cada etapa acende no mapa e o caminho até a medição (v20): da liberação topográfica ao cadastro aprovado, só pelo que
foi gravado; o OK interno exige a verificação do supervisor e não depende mais de medição aberta (SEM_MEDICAO_ABERTA,
entra sozinho quando a medição abre); a lista "Aguardando verificação" e o resumo do topo da Medição."""
import os
import sys
import unittest
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import apropriacao as AP  # noqa: E402
import dados_obra as DO  # noqa: E402
import planejamento as P  # noqa: E402
import regras as R  # noqa: E402
import relogio as RL  # noqa: E402
import servicos as S  # noqa: E402
from fotos_teste import jpeg  # noqa: E402
from test_acesso import BaseHTTP  # noqa: E402
from test_campo import TR, BaseCampo, D  # noqa: E402

TR2 = "Zona01_PB01_Rede_TR002"
FOTOS = ("SINALIZACAO", "EXECUCAO", "CONCLUIDO")


class TestRegraDaEtapa(unittest.TestCase):
    """regras.etapa_trecho: cada transição, da mais atrasada à mais adiantada."""

    def test_cada_transicao(self):
        e = R.etapa_trecho
        self.assertEqual(e(), "nao")
        self.assertEqual(e(liberado=True), "liberado")
        self.assertEqual(e(liberado=True, equipe_hoje=True), "execucao")
        # a NS do dia de hoje chega: deixa de ser "em execução" e passa a aguardar a verificação
        self.assertEqual(e(equipe_hoje=True, informado_hoje=True, executado=True), "executado")
        # equipe de novo no dia seguinte, sobre o que já foi executado em parte: "em execução" até a NS do dia
        self.assertEqual(e(equipe_hoje=True, executado=True, verificado=True), "execucao")
        self.assertEqual(e(executado=True), "executado")
        self.assertEqual(e(executado=True, verificado=True), "verificado")
        self.assertEqual(e(executado=True, verificado=True, campo=True), "campo")
        self.assertEqual(e(executado=True, concluido=True, verificado=True, fotos_ok=False, campo=False), "verificado")
        self.assertEqual(e(executado=True, concluido=True, verificado=True, fotos_ok=True, campo=True), "pronto")
        self.assertEqual(e(executado=True, concluido=True, verificado=False, fotos_ok=True), "executado")
        self.assertEqual(e(ok=True, esteira="1_PRONTO"), "ok")
        self.assertEqual(e(ok=True, equipe_hoje=True), "ok")                       # concluído: a equipe no dia não volta atrás
        for etapa in ("2_ENVIADO", "3_RECEBIDO", "4_GDOC_ANALISE", "5A_NEGADO"):
            self.assertEqual(e(ok=True, esteira=etapa), "cad_andamento", etapa)
        self.assertEqual(e(ok=True, esteira="6_APROVADO"), "cadastrado")
        self.assertEqual(list(R.ETAPAS_MAPA)[0], "nao")
        self.assertEqual(list(R.ETAPAS_MAPA)[-1], "cadastrado")


class BaseEtapas(BaseCampo):
    def setUp(self):
        super().setUp()
        RL.fixar(datetime(2026, 10, 15, 15, 0))                      # meio-dia em Brasília no dia D
        self.tid = S.alvo(self.c, "TRECHO", TR)["id"]
        self.L = float(S.alvo(self.c, "TRECHO", TR)["extensao_m"])

    def tearDown(self):
        RL.fixar()
        super().tearDown()

    def etapa(self, nome=TR):
        return P.camadas_mapa(self.c, D)["etapas"].get(nome, {"s": "nao", "parcial": False})

    def tres_fotos(self):
        for cat in FOTOS:
            S.registrar_foto(self.c, "TRECHO", TR, cat, jpeg(), dir_fotos=self.fotos)


class TestEtapasNoMapa(BaseEtapas):
    LIBERAR_TUDO = False                  # a liberação é uma das etapas

    def test_do_nao_iniciado_ao_cadastro_aprovado(self):
        self.assertEqual(self.etapa()["s"], "nao")
        S.registrar_etapa_complementar(self.c, TR, "LIBERACAO_TOPOGRAFICA", 0, self.L, D, "topo1", "NS-TOPO-1")
        self.assertEqual(self.etapa()["s"], "liberado")
        DO.liberar(self.c, D, "Zona01", [TR], [], [], "almox1")
        self.assertEqual(self.etapa()["s"], "execucao")                    # equipe liberada hoje: em execução
        # NS do dia (parcial), informada por quem enviou
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 30}],
                  informado_por="eng1", motivo_sem_ns="teste")
        self.assertEqual(self.etapa(), {"s": "executado", "parcial": True})
        S.verificar_trecho(self.c, TR, "sup1")
        self.assertEqual(self.etapa(), {"s": "verificado", "parcial": True})
        # o resto do trecho e o reaterro: volta a aguardar a verificação, agora completo
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, concluido_100=True, informado_por="eng1", motivo_sem_ns="teste")
        self.assertEqual(self.etapa(), {"s": "executado", "parcial": False})
        S.verificar_trecho(self.c, TR, "sup1")
        self.assertEqual(self.etapa()["s"], "verificado")                  # verificado, mas faltam as fotos
        S.registrar_cadastro_campo(self.c, TR, 0, self.L, D, "caderneta 1", "cad1")
        self.assertEqual(self.etapa()["s"], "campo")
        self.tres_fotos()
        self.assertEqual(self.etapa()["s"], "campo")                       # o cadastro de campo também se verifica
        S.verificar_trecho(self.c, TR, "sup1")
        self.assertEqual(self.etapa()["s"], "pronto")
        S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng1", D)                  # sem medição aberta: aceito
        self.assertEqual(self.etapa()["s"], "ok")
        S.avancar_cadastro(self.c, TR, "2_ENVIADO", {"empresa": "Cadastro Ltda", "data_envio": D}, D)
        self.assertEqual(self.etapa()["s"], "cad_andamento")
        S.avancar_cadastro(self.c, TR, "3_RECEBIDO", {"arquivos": ["TR001.dwg"]}, D)
        S.registrar_conferencia_cadastro(self.c, TR, "CONFORME", dict.fromkeys(R.CHECKLIST_CONFERENCIA_CADASTRO, True), "eng2")
        S.avancar_cadastro(self.c, TR, "4_GDOC_ANALISE", {"protocolo_gdoc": "GDOC-1"}, D)
        self.assertEqual(self.etapa()["s"], "cad_andamento")
        S.criar_medicao(self.c, 1, "2026-10-01", "2026-10-31")              # o cadastro aprovado é medido (D-58)
        S.avancar_cadastro(self.c, TR, "6_APROVADO", {"memorando_eset": "ESET-1"}, D)
        self.assertEqual(self.etapa()["s"], "cadastrado")

    def test_ns_de_servico_nao_acende(self):
        """A NS de serviço de obra é o plano da zona: não grava nada nos trechos, então nada acende."""
        self.assertNotIn(TR, P.camadas_mapa(self.c, D)["etapas"])


class TestOkInterno(BaseEtapas):
    def concluir(self, verificar=True):
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, concluido_100=True, informado_por="eng1", motivo_sem_ns="teste")
        self.tres_fotos()
        if verificar:
            S.verificar_trecho(self.c, TR, "sup1")

    def test_exige_a_verificacao(self):
        self.concluir(verificar=False)
        with self.assertRaisesRegex(S.RegraViolada, "verificação do supervisor: 2 intervalo"):
            S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng1", D)
        cam = S.caminho_medicao(self.c, TR)
        self.assertFalse(cam["pronto_para_ok"])
        self.assertEqual(cam["falta_para_ok"], ["Verificado pelo supervisor"])
        self.assertEqual({i["id"]: i["feito"] for i in cam["itens"]},
                         {"topografia": True, "execucao": True, "verificacao": False, "fotos": True, "cadastro_campo": False, "ok": False})
        S.verificar_trecho(self.c, TR, "sup1")
        self.assertTrue(S.caminho_medicao(self.c, TR)["pronto_para_ok"])

    def test_sem_medicao_aberta_espera_e_entra_sozinho(self):
        self.concluir()
        self.assertIsNone(S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng1", D))
        self.assertEqual(self.q("SELECT COUNT(*) FROM medicao_lancamentos")[0][0], 0)
        self.assertEqual(self.q("SELECT medicao_id, ok_fiscal_por FROM execucao WHERE alvo_id=?", self.tid), [(None, "eng1")])
        self.assertEqual(self.q("SELECT etapa FROM cadastro WHERE trecho_id=?", self.tid), [("1_PRONTO",)])   # esteira já anda
        rest = [l for l in AP.restricoes(self.c)["linhas"] if l["restricao"] == "SEM_MEDICAO_ABERTA"]
        self.assertEqual([(l["ref"], l["desde"]) for l in rest], [({"tipo": "TRECHO", "id": self.tid}, D)])
        self.assertIn("espera a medição de teste abrir", S.caminho_medicao(self.c, TR)["itens"][-1]["detalhe"])
        with self.assertRaisesRegex(S.RegraViolada, "já marcado"):
            S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng1", D)              # o OK não se repete
        # a medição do período abre: os lançamentos entram uma vez só
        mid = S.criar_medicao(self.c, 1, "2026-10-01", "2026-10-31")
        self.assertEqual(AP.sincronizar(self.c), 1)
        self.assertEqual(AP.sincronizar(self.c), 0)
        self.assertEqual(self.q("SELECT medicao_id FROM execucao WHERE alvo_id=?", self.tid), [(mid,)])
        ass = self.q("SELECT SUM(quantidade) FROM medicao_lancamentos WHERE servico='ASSENTAMENTO' AND medicao_id=?", mid)[0][0]
        self.assertAlmostEqual(ass, self.L, places=3)
        self.assertFalse([l for l in AP.restricoes(self.c)["linhas"] if l["restricao"] == "SEM_MEDICAO_ABERTA"])
        self.assertEqual(P.caminho_da_medicao(self.c, mid)["ok_nesta"], [TR])

    def test_com_medicao_aberta_lanca_na_hora(self):
        mid = S.criar_medicao(self.c, 1, "2026-10-01", "2026-10-31")
        self.concluir()
        self.assertEqual(S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng1", D), mid)
        self.assertTrue(self.q("SELECT 1 FROM medicao_lancamentos WHERE medicao_id=?", mid))

    def test_medicao_do_periodo_fechada_vai_para_a_proxima_aberta(self):
        m1 = S.criar_medicao(self.c, 1, "2026-10-01", "2026-10-31")
        self.c.execute("UPDATE medicoes SET status='FECHADA' WHERE id=?", (m1,))
        m2 = S.criar_medicao(self.c, 2, "2026-11-01", "2026-11-30")
        self.concluir()
        self.assertEqual(S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng1", D), m2)


class TestVerificacao(BaseEtapas):
    def test_quem_informou_nao_verifica_e_o_resto_fica_verificado(self):
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 30}],
                  informado_por="sup1", motivo_sem_ns="teste")
        with self.assertRaisesRegex(S.RegraViolada, "Quem informou não verifica"):
            S.verificar_trecho(self.c, TR, "sup1")
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 30, "fim_m": 40}],
                  informado_por="eng1", motivo_sem_ns="teste")
        self.assertEqual(S.verificar_trecho(self.c, TR, "sup1"), {"verificados": 1, "de_outra_pessoa": 1})
        self.assertEqual(len(S.sem_verificacao(self.c, self.tid)), 1)
        self.assertEqual(S.verificar_trecho(self.c, TR, "sup2"), {"verificados": 1, "de_outra_pessoa": 0})
        with self.assertRaisesRegex(S.RegraViolada, "nada a verificar"):
            S.verificar_trecho(self.c, TR, "sup2")

    def test_lista_aguardando_verificacao_por_zona_e_mais_perto_primeiro(self):
        for nome in (TR, TR2):
            S.apontar(self.c, D, "Zona01", "TRECHO", nome, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 5}],
                      informado_por="eng1", motivo_sem_ns="teste")
        self.c.execute("UPDATE trechos SET lat=-15.80, lon=-47.90 WHERE ponto=?", (TR,))
        self.c.execute("UPDATE trechos SET lat=-15.70, lon=-47.80 WHERE ponto=?", (TR2,))
        perto_do_2 = S.aguardando_verificacao(self.c, -15.701, -47.801)
        self.assertEqual([x["nome"] for x in perto_do_2], [TR2, TR])
        self.assertLess(perto_do_2[0]["distancia_m"], 200)
        self.assertEqual([x["nome"] for x in S.aguardando_verificacao(self.c)], [TR, TR2])        # sem posição: pelo nome
        self.assertEqual(P.caminho_da_medicao(self.c)["aguardando_verificacao"], [TR, TR2])


class TestRotas(BaseHTTP):
    usuarios = BaseHTTP.usuarios + (("sup1", "SUPERVISOR", None),)

    def test_verificar_pelo_mapa_e_permissoes(self):
        RL.fixar(datetime(2026, 10, 15, 15, 0))
        try:
            for t in ("MANHA", "TARDE"):
                S.registrar_clima(self.c, D, "Zona01", t, "SOL")
            S.apontar(self.c, D, "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 10}],
                      informado_por="enc1", motivo_sem_ns="teste")
            enc, sup = self.cliente("enc1"), self.cliente("sup1")
            self.assertEqual(enc.post("/api/trecho/verificar", {"trecho": TR})[0], 403)
            self.assertEqual(sup.get("/api/verificacao/pendentes")[1][0]["nome"], TR)
            st, r = sup.post("/api/trecho/verificar", {"trecho": TR, "verificado_por": "outra pessoa"})
            self.assertEqual((st, r), (200, {"verificados": 1, "de_outra_pessoa": 0}))
            self.assertEqual(self.q("SELECT verificado_por FROM intervalos_execucao"), [("sup1",)])      # autor = sessão
            st, cam = enc.get(f"/api/caminho?trecho={TR}")
            self.assertEqual(st, 200)
            self.assertEqual([i["id"] for i in cam["itens"]], ["topografia", "execucao", "verificacao", "fotos", "cadastro_campo", "ok"])
            st, est = sup.get(f"/api/mapa/estado?data={D}")
            self.assertEqual(est["camadas"]["etapas"][TR], {"s": "verificado", "parcial": True})
            self.assertEqual(sup.get("/api/medicao/caminho")[0], 403)                             # resumo da Medição
            self.assertEqual(self.cliente("eng1").get("/api/medicao/caminho")[0], 200)
        finally:
            RL.fixar()


if __name__ == "__main__":
    unittest.main()
