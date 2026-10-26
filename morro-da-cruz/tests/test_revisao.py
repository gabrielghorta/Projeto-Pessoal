"""Achados da revisão de 26/10/2026 (ramo do site depois dos PRs #6, #7 e #8): cada teste reproduz o problema e confere
a correção. Os do estoque (nota sem aprovação, tubo da Caesb) ficam em test_compras.py."""
import os
import sys
import unittest
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import apropriacao as AP  # noqa: E402
import dados_obra as DO  # noqa: E402
import regras as R  # noqa: E402
import relogio as RL  # noqa: E402
import servicos as S  # noqa: E402
from base_real import BaseReal  # noqa: E402
from test_acesso import BaseHTTP  # noqa: E402
from test_campo import TR, TR_ID, D, banco_legado  # noqa: E402
from test_etapas_mapa import BaseEtapas  # noqa: E402
from test_importacao import Base  # noqa: E402
from test_retificacao_cadastro import BaseRetif  # noqa: E402


class TestBuscaDaAdutora(BaseReal):
    """Os trechos da adutora se chamam Zona02_PB07_Adutora_TR001: a busca procurava 'ADUTORA_…' e não achava nada; o
    texto livre trocava o sublinhado por espaço e 'Rede_TR' também não achava."""

    def test_adutora_e_texto_com_sublinhado(self):
        r = S.buscar(self.c, "adutora tr1")
        self.assertTrue(r)
        self.assertTrue(all("_Adutora_" in x["rotulo"] and x["rotulo"].endswith("_TR001") for x in r), [x["rotulo"] for x in r])
        self.assertTrue(S.buscar(self.c, "Rede_TR"))
        self.assertEqual({x["rotulo"] for x in S.buscar(self.c, "Rede_TR020", limite=200)},
                         {x["rotulo"] for x in S.buscar(self.c, "rede tr020", limite=200)})


class TestEtapasDoMapa(BaseEtapas):
    def test_apontamento_anulado_nao_pinta_executado(self):
        """A retificação que anula o apontamento deixa a linha de execucao com 0 m: o trecho não está executado."""
        ap = self.ap(("ASSENTADO", 0, 10))
        self.assertEqual(self.etapa()["s"], "executado")
        S.retificar_intervalos(self.c, "APONTAMENTO", ap, [], "lançado no trecho errado", "Eng.")
        self.assertNotEqual(self.etapa()["s"], "executado")
        self.assertFalse(self.etapa()["parcial"])

    def test_ok_que_espera_a_medicao_nao_entra_se_o_trecho_saiu_da_revisao(self):
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, concluido_100=True, informado_por="eng1", motivo_sem_ns="teste")
        self.tres_fotos()
        S.verificar_trecho(self.c, TR, "sup1")
        self.assertIsNone(S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng1", D))          # espera a medição abrir
        self.c.execute("UPDATE trechos SET vigente=0 WHERE id=?", (self.tid,))         # a importação retira o trecho
        S.criar_medicao(self.c, 1, "2026-10-01", "2026-10-31")
        AP.sincronizar(self.c)
        self.assertEqual(S.lancar_oks_pendentes(self.c), 0)
        self.assertEqual(self.q("SELECT COUNT(*) FROM medicao_lancamentos")[0][0], 0)


class TestContingenciaENaoRealizada(BaseEtapas):
    """As rotas de check-in e de encerrar a programação saíram com o menu; o dia sem trecho e o programado que não
    aconteceu voltam pelo Dados da obra."""

    def test_contingencia_registra_a_presenca_sem_trecho(self):
        x = DO.contingencia(self.c, D, "Zona01", R.CONTINGENCIAS[0], "almox1")
        self.assertEqual(self.q("SELECT contingencia, alvo_id, encerrado FROM checkins WHERE id=?", x["checkin_id"]),
                         [(R.CONTINGENCIAS[0], None, 0)])
        n = self.q("SELECT COUNT(*) FROM funcionarios WHERE equipe_id='Zona01'")[0][0]
        self.assertEqual(self.q("SELECT COUNT(*) FROM checkin_presencas WHERE checkin_id=? AND recurso_tipo='FUNCIONARIO'",
                                x["checkin_id"])[0][0], n)
        with self.assertRaisesRegex(S.RegraViolada, "Escolha a contingência"):
            DO.contingencia(self.c, D, "Zona02", "Outra coisa", "almox1")
        with self.assertRaisesRegex(S.RegraViolada, "check-in aberto"):
            DO.contingencia(self.c, D, "Zona01", R.CONTINGENCIAS[0], "almox1")              # fecha na devolução antes

    def test_programado_que_nao_aconteceu(self):
        DO.programar(self.c, [TR], [], "Zona01", "ASSENTAMENTO", D, "eng1")
        self.assertEqual(DO.nao_realizada(self.c, D, "Zona01", "chuva", "eng1"), {"nao_realizadas": 1})
        self.assertEqual(self.q("SELECT status, motivo, encerrada_por FROM programacoes"), [("NAO_REALIZADA", "chuva", "eng1")])
        with self.assertRaisesRegex(S.RegraViolada, "Nada planejado"):
            DO.nao_realizada(self.c, D, "Zona01", "chuva", "eng1")
        DO.programar(self.c, [TR], [], "Zona01", "ASSENTAMENTO", "2026-10-20", "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "ainda não chegou"):
            DO.nao_realizada(self.c, "2026-10-20", "Zona01", "chuva", "eng1")


class TestRetificacaoSemLiberacao(BaseRetif):
    def test_apontamento_antigo_so_exige_liberacao_do_que_a_correcao_acrescenta(self):
        ap = self.ap(("ASSENTADO", 0, 10))
        # como um apontamento de antes do bloqueio: a liberação do trecho não existe (anulada)
        self.c.execute("UPDATE etapas_complementares SET anulado_em='2026-10-20T00:00:00' WHERE trecho_id=? "
                       "AND etapa='LIBERACAO_TOPOGRAFICA'", (TR_ID,))
        self.ret(ap, ("ASSENTADO", 0, 9))                                              # corrigir dentro do que já tinha
        with self.assertRaisesRegex(S.RegraViolada, "liberação topográfica"):
            self.ret(ap + 1, ("ASSENTADO", 0, 12))                                     # 9–12 m é novo: exige a NS


class TestLegadoSemLiberacao(Base):
    LIBERAR_TUDO = False

    def setUp(self):
        super().setUp()
        banco_legado(self).close()
        self.aplicar()
        self.c = self.conectar()

    def test_conciliacao_do_legado_pode_ser_retificada(self):
        """A conciliação do legado dispensa a liberação; a retificação dela também (a lista 'Fora de ordem' manda
        retificar)."""
        cid = S.conciliar_legado(self.c, TR, [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 30},
                                              {"etapa": "REATERRADO", "ini_m": 0, "fim_m": 20}], "trena", "Eng.")
        S.retificar_intervalos(self.c, "CONCILIACAO", cid, [{"etapa": "ASSENTADO", "ini_m": 5, "fim_m": 35},
                                                            {"etapa": "REATERRADO", "ini_m": 5, "fim_m": 25}],
                               "posição revista com o cadastro de campo", "Eng.")
        self.assertEqual(self.q("SELECT etapa, ini_m, fim_m, origem FROM intervalos_execucao WHERE anulado_por IS NULL ORDER BY etapa"),
                         [("ASSENTADO", 5.0, 35.0, "RETIFICACAO"), ("REATERRADO", 5.0, 25.0, "RETIFICACAO")])


class TestEsteiraPorPermissao(BaseHTTP):
    """A etapa do cadastro aparece para todos no Mapa iluminado; empresa, protocolo, memorando, motivo e conferência só
    para quem trabalha a esteira ou a medição."""

    def test_equipe_ve_a_etapa_sem_os_dados_do_processo(self):
        self.c.execute("""INSERT INTO cadastro(trecho_id, etapa, revisao, empresa, protocolo_gdoc, motivo_negativa, atualizado_em)
                          VALUES (?, '5A_NEGADO', 0, 'Empresa de Cadastro X', 'GDOC-123', 'cota errada', 'x')""", (TR_ID,))
        self.c.commit()
        enc, eng = self.cliente("enc1"), self.cliente("eng1")
        st, lst = enc.get("/api/esteira")
        self.assertEqual(st, 200)
        self.assertEqual({k: lst[0].get(k) for k in ("etapa", "empresa", "protocolo_gdoc", "motivo_negativa")},
                         {"etapa": "5A_NEGADO", "empresa": None, "protocolo_gdoc": None, "motivo_negativa": None})
        cam = enc.get(f"/api/caminho?trecho={TR}")[1]["cadastro"]
        self.assertEqual(cam["etapa"], "5A_NEGADO")
        self.assertNotIn("empresa", cam)
        self.assertNotIn("conferencia", cam)
        self.assertEqual(eng.get("/api/esteira")[1][0]["protocolo_gdoc"], "GDOC-123")
        self.assertEqual(eng.get(f"/api/caminho?trecho={TR}")[1]["cadastro"]["empresa"], "Empresa de Cadastro X")


if __name__ == "__main__":
    unittest.main()
