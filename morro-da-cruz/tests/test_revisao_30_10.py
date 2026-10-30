"""Revisão do código de 30/10/2026 (docs/CORRECOES_REVISAO_30-10-2026.md): uma regressão para cada correção que se
testa sem o navegador. Bancos temporários e planilhas sintéticas, como em test_compras."""
import os
import sys
import unittest
from datetime import timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "cronograma_executivo"))
import compras as C  # noqa: E402
import ns_leitura  # noqa: E402
import regras as R  # noqa: E402
import relogio as RL  # noqa: E402
import server  # noqa: E402
import servicos as S  # noqa: E402
from fotos_teste import jpeg, jpeg_bytes  # noqa: E402
from test_compras import D, BaseCompras  # noqa: E402

TUBO_CAESB = "CAESB-PEAD-DE63"


class TestRegrasPuras(unittest.TestCase):
    def test_host_local_barra_dns_rebinding(self):
        for h in ("localhost", "127.0.0.1:8765", "LOCALHOST:80", "[::1]:8765", "::1"):
            self.assertTrue(server._host_local(h), h)
        for h in (None, "", "obra.exemplo.com", "evil.example:8765", "127.0.0.1.evil.example", "[::2]:80"):
            self.assertFalse(server._host_local(h), h)

    def test_total_do_bm_arredonda_como_o_excel(self):
        # 1,00 + 12,5 % de BDI = 1,125: o Excel dá 1,13; o round do Python (meio para o par) daria 1,12
        self.assertEqual(R.totalizar_bm([("SERVIÇO", 1, 1.0)], 0, 0.125, 0)["total"], 1.13)

    def test_contrato_com_ponto_de_milhar(self):
        self.assertEqual(ns_leitura.norm_contrato("CT 10.239/2026 Caesb × Ankara"), "10239/2026")
        self.assertEqual(ns_leitura.norm_contrato("10239/26"), "10239/2026")

    def test_exif_com_data_zerada_nao_vira_data_da_foto(self):
        self.assertNotIn("capturada_em", S.exif_jpeg(jpeg_bytes("0000:00:00 00:00:00")))
        self.assertEqual(S.exif_jpeg(jpeg_bytes("2026-10-20T08:30:00"))["capturada_em"], "2026-10-20T08:30:00")

    def test_bisseccao_da_produtividade_anda_de_meio_em_meio(self):
        import motor
        lim = motor.CAL.w(motor.PRAZO + timedelta(days=1))
        original = motor.programar
        try:
            for minimo in (85.5, 86.0, 95.0, 40.0):
                motor.programar = lambda D_, rede, p, m=minimo: {"fim": lim if p >= m - 1e-9 else lim + 1}
                self.assertEqual(motor.resolver_prazo(None, None), minimo)
            motor.programar = lambda D_, rede, p: {"fim": lim + 1}
            self.assertIsNone(motor.resolver_prazo(None, None))
        finally:
            motor.programar = original


class TestEstornosComCaminhoProprio(BaseCompras):
    def entrada(self, q=50):
        S.entrada_material(self.c, D, TUBO_CAESB, q, "ROMANEIO_CAESB", "ROM-1", "almox1")

    def test_transferencia_nao_se_estorna_pela_metade(self):
        self.entrada()
        S.checkin(self.c, D, "Zona01", "TRECHO", "Zona01_PB01_Rede_TR001", materiais=[{"material_id": TUBO_CAESB, "quantidade": 20}])
        S.checkin(self.c, D, "Zona02", "TRECHO", "Zona02_PB04_Rede_TR036")
        C.transferir(self.c, D, TUBO_CAESB, 8, "Zona01", "Zona02", "Eng. Ana", "almox1")
        for tipo in ("TRANSF_SAIDA", "TRANSF_ENTRADA"):
            mid = self.q("SELECT id FROM movimentos WHERE tipo=?", tipo)[0][0]
            with self.assertRaisesRegex(S.RegraViolada, "transferência de volta"):
                S.estornar(self.c, mid, "lançada errada", "almox1")

    def test_ajuste_de_inventario_nao_se_estorna(self):
        self.entrada()
        inv = C.registrar_contagem(self.c, D, [{"material_id": TUBO_CAESB, "contado": 48}], "almox1")
        C.decidir_inventario(self.c, inv, True, "diferença aceita", "almox2")
        mid = self.q("SELECT id FROM movimentos WHERE tipo LIKE 'AJUSTE_INVENTARIO_%'")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "nova contagem"):
            S.estornar(self.c, mid, "contagem errada", "almox1")

    def test_retirada_de_check_in_encerrado_vai_pela_retificacao(self):
        self.entrada()
        ck = S.checkin(self.c, D, "Zona01", "TRECHO", "Zona01_PB01_Rede_TR001", materiais=[{"material_id": TUBO_CAESB, "quantidade": 10}])
        S.checkout(self.c, ck, [{"material_id": TUBO_CAESB, "aplicado": 10}])
        mid = self.q("SELECT id FROM movimentos WHERE tipo='CUSTODIA' AND checkin_id=?", ck)[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "retificação do fechamento"):
            S.estornar(self.c, mid, "retirada errada", "almox1")


class TestNotaRepetidaEContagem(BaseCompras):
    LINHAS = [{"descricao": "Luva PEAD DE63", "unidade": "UN", "quantidade": 3, "valor_unitario": 9}]

    def test_mesma_nota_sem_chave_nao_entra_duas_vezes(self):
        C.registrar_nf_digitada(self.c, "77", self.forn, D, self.LINHAS, "almox1", jpeg(), "NF_IMAGEM", "nf77.jpg")
        for numero in ("77", "077"):
            with self.assertRaisesRegex(S.RegraViolada, "já está registrada"):
                C.registrar_nf_digitada(self.c, numero, self.forn, D, self.LINHAS, "almox2", jpeg(), "NF_IMAGEM", "nf77b.jpg")
        C.registrar_nf_digitada(self.c, "78", self.forn, D, self.LINHAS, "almox1", jpeg(), "NF_IMAGEM", "nf78.jpg")

    def test_contagem_exige_data_e_nao_aceita_futuro(self):
        itens = [{"material_id": TUBO_CAESB, "contado": 1}]
        with self.assertRaisesRegex(S.RegraViolada, "data da contagem"):
            C.registrar_contagem(self.c, None, itens, "almox1")
        with self.assertRaisesRegex(S.RegraViolada, "data futura"):
            C.registrar_contagem(self.c, (RL.hoje() + timedelta(days=2)).isoformat(), itens, "almox1")


if __name__ == "__main__":
    unittest.main()
