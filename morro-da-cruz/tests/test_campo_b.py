"""Módulo B — liberação topográfica, escavação (informativa) e ocorrências (impedimentos e não conformidades).
Planilhas sintéticas, bancos temporários."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import servicos as S  # noqa: E402
from test_acesso import BaseHTTP  # noqa: E402
from test_campo import MND, TR, BaseCampo, D  # noqa: E402

D2 = "2026-10-16"


class TestDataFutura(BaseCampo):
    def test_execucao_estoque_e_ok_nao_aceitam_data_futura(self):
        F = "2099-01-01"
        casos = [lambda: S.registrar_clima(self.c, F, "Zona01", "MANHA", "SOL"),
                 lambda: S.apontar(self.c, F, "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 5}]),
                 lambda: S.checkin(self.c, F, "Zona01", "TRECHO", TR),
                 lambda: S.entrada_material(self.c, F, "CAESB-PEAD-DE63", 10, "ROMANEIO_CAESB", "ROM", "almox1"),
                 lambda: S.registrar_soldas(self.c, F, "Zona01", "TRECHO", TR, "ELETROFUSAO", 1, "S", "enc"),
                 lambda: S.registrar_etapa_complementar(self.c, TR, "LIBERACAO_TOPOGRAFICA", 0, 10, F, "topo", "NS-1"),
                 lambda: S.abrir_ocorrencia(self.c, "TRECHO", TR, "IMPEDIMENTO", "CHUVA", "x", F, "enc"),
                 lambda: S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng", F)]
        antes = {t: self.q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in ("clima", "apontamentos", "checkins", "movimentos", "soldas",
                                                                        "etapas_complementares", "ocorrencias")}
        for caso in casos:
            with self.assertRaisesRegex(S.RegraViolada, "data futura"):
                caso()
        self.assertEqual({t: self.q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in antes}, antes)   # nada gravado


class TestLiberacaoEEscavacao(BaseCampo):
    LIBERAR_TUDO = False                  # a liberação é o próprio assunto

    def lib(self, a, b, data=D, ref="NS-012", etapa="LIBERACAO_TOPOGRAFICA", alvo=TR):
        return S.registrar_etapa_complementar(self.c, alvo, etapa, a, b, data, "topo1", ref)

    def test_registro_recusas_e_nao_mexe_na_execucao(self):
        self.lib(0, 40)
        with self.assertRaisesRegex(S.RegraViolada, "sobrepõe"):
            self.lib(30, 50)
        with self.assertRaisesRegex(S.RegraViolada, "exige a referência"):
            self.lib(40, 50, ref="")
        with self.assertRaisesRegex(S.RegraViolada, "fora do trecho"):
            self.lib(70, 80)
        with self.assertRaisesRegex(S.RegraViolada, "MND não tem vala"):
            self.lib(0, 5, etapa="ESCAVADO", alvo=MND)
        self.lib(0, 20, etapa="ESCAVADO", ref=None)
        self.assertEqual(self.q("SELECT COUNT(*) FROM intervalos_execucao")[0][0], 0)    # não é execução nem quantidade
        self.assertIsNone(S.execucao(self.c, "TRECHO", S.alvo(self.c, "TRECHO", TR)["id"]))
        comp = S.detalhe(self.c, "TRECHO", TR)["complementar"]
        self.assertEqual((comp["LIBERACAO_TOPOGRAFICA"]["metros"], comp["ESCAVADO"]["metros"]), (40, 20))

    def test_assentado_sem_liberacao_ate_a_data_e_recusado(self):
        """D-20 DECIDIDA (23/10/2026): a ordem topografia → serviço é obrigatória; antes era só alerta."""
        self.lib(0, 20, data=D2)                                                 # liberação DEPOIS do assentamento
        with self.assertRaisesRegex(S.RegraViolada, r"Zona 01 · PB01 · TR001, de 0,0 m a 30,0 m: falta a liberação topográfica "
                                                    r"\(registre a NS de topografia antes\)"):
            self.ap(("ASSENTADO", 0, 30))
        self.assertFalse(self.q("SELECT 1 FROM intervalos_execucao"))            # nada gravado
        rid = self.q("SELECT id FROM etapas_complementares")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "motivo"):
            S.anular_etapa_complementar(self.c, rid, "", "eng1")
        S.anular_etapa_complementar(self.c, rid, "data errada: a liberação foi em 14/10", "eng1")
        self.lib(0, 40, data="2026-10-14")
        self.ap(("ASSENTADO", 0, 30))                                            # agora liberado até a data
        with self.assertRaisesRegex(S.RegraViolada, "de 40,0 m a 50,0 m: falta a liberação topográfica"):
            self.lib(30, 50, etapa="ESCAVADO")                                  # escavação também só no liberado
        d = S.detalhe(self.c, "TRECHO", TR)
        self.assertEqual(d["complementar"]["alertas"], [])
        self.assertEqual(len(d["complementar"]["anulados"]), 1)                 # nada apagado
        with self.assertRaisesRegex(S.RegraViolada, "já anulado"):
            S.anular_etapa_complementar(self.c, rid, "de novo", "eng1")
        lib2 = self.q("SELECT id FROM etapas_complementares WHERE anulado_em IS NULL")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "retifique antes a execução"):
            S.anular_etapa_complementar(self.c, lib2, "liberação errada", "eng1")   # a execução ficaria fora de ordem


class TestOcorrencias(BaseCampo):
    def test_impedimento_e_nao_conformidade_abertos_e_resolvidos(self):
        o1 = S.abrir_ocorrencia(self.c, "TRECHO", TR, "IMPEDIMENTO", "INTERFERENCIA", "Rede de esgoto não cadastrada a 1,2 m", D, "enc1", "Zona01")
        o2 = S.abrir_ocorrencia(self.c, "TRECHO", TR, "NAO_CONFORMIDADE", "SOLDA", "Solda sem alinhamento", D, "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "Categoria inválida"):
            S.abrir_ocorrencia(self.c, "TRECHO", TR, "IMPEDIMENTO", "SOLDA", "x", D, "enc1")
        with self.assertRaisesRegex(S.RegraViolada, "descrição"):
            S.abrir_ocorrencia(self.c, "TRECHO", TR, "IMPEDIMENTO", "CHUVA", " ", D, "enc1")
        pend = [p["texto"] for p in S.detalhe(self.c, "TRECHO", TR)["pendencias"] if p["area"] == "Ocorrências"]
        self.assertEqual(len(pend), 2)
        with self.assertRaisesRegex(S.RegraViolada, "correção feita"):
            S.resolver_ocorrencia(self.c, o2, "", "eng2")
        S.resolver_ocorrencia(self.c, o2, "Solda refeita e verificada (registro 14)", "eng2")
        S.resolver_ocorrencia(self.c, o1, "Desvio aprovado pela engenharia", "eng2")
        with self.assertRaisesRegex(S.RegraViolada, "já resolvida"):
            S.resolver_ocorrencia(self.c, o1, "de novo", "eng2")
        self.assertEqual([p for p in S.detalhe(self.c, "TRECHO", TR)["pendencias"] if p["area"] == "Ocorrências"], [])
        self.assertEqual(len(S.ocorrencias(self.c, "TRECHO", TR)), 2)            # histórico mantido
        self.assertIn(S.alvo(self.c, "TRECHO", TR)["id"], S.historico_alvos(self.c, "TRECHO"))


class TestPermissoesModuloB(BaseHTTP):
    LIBERAR_TUDO = False                  # registra a liberação pelo HTTP

    def test_liberacao_so_topografia_ou_engenharia_e_resolucao_so_engenharia(self):
        enc = self.cliente("enc1")
        st, _ = enc.post("/api/liberacao", {"trecho_id": TR, "ini_m": 0, "fim_m": 10, "data": D, "referencia": "NS-1"})
        self.assertEqual(st, 403)
        st, r = enc.post("/api/ocorrencia", {"alvo_tipo": "TRECHO", "alvo_id": TR, "tipo": "IMPEDIMENTO", "categoria": "CHUVA",
                                              "descricao": "Vala alagada", "data": D, "equipe_id": "Zona01", "aberta_por": "outro"})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT aberta_por FROM ocorrencias"), [("enc1",)])
        self.assertEqual(enc.post("/api/ocorrencia/resolver", {"ocorrencia_id": r["id"], "resolucao": "secou"})[0], 403)
        eng = self.cliente("eng1")
        self.assertEqual(eng.post("/api/liberacao", {"trecho_id": TR, "ini_m": 0, "fim_m": 10, "data": D, "referencia": "NS-1"})[0], 200)
        self.assertEqual(eng.post("/api/ocorrencia/resolver", {"ocorrencia_id": r["id"], "resolucao": "Bombeamento concluído"})[0], 200)
        self.assertEqual(self.q("SELECT registrado_por FROM etapas_complementares"), [("eng1",)])
        aud = self.q("SELECT rota, status, alvo_tipo, alvo_id FROM auditoria WHERE rota IN ('/api/liberacao','/api/ocorrencia') ORDER BY id")
        self.assertEqual([(a[0], a[1], a[2]) for a in aud], [("/api/liberacao", 403, "TRECHO"), ("/api/ocorrencia", 200, "TRECHO"),
                                                             ("/api/liberacao", 200, "TRECHO")])
        self.assertTrue(all(a[3] == "TR-00001" for a in aud))                     # objeto pela identidade estável


if __name__ == "__main__":
    unittest.main()
