import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import regras as R  # noqa: E402


class TestUnidades(unittest.TestCase):
    """Auditoria N02 — metros e peças nunca no mesmo contador."""

    def test_df33_separa_un_e_m(self):
        itens = [("UN", 1)] * 17 + [("M", 0.71)]
        tot = R.somar_por_unidade(itens)
        self.assertEqual(dict(tot), {"UN": 17, "M": 0.71})
        self.assertEqual(R.formatar_por_unidade(tot), "17 UN · 0,71 m")

    def test_alias_de_unidade(self):
        self.assertEqual(dict(R.somar_por_unidade([("und", 2), ("PÇ", 1), ("ml", 1.5)])), {"UN": 3, "M": 1.5})

    def test_sem_unidade_bloqueia(self):
        with self.assertRaises(R.RegraViolada):
            R.somar_por_unidade([("", 1)])


class TestPerfil(unittest.TestCase):
    """Auditoria E06 — perfil pendente bloqueia, sem IFERROR -> 0."""

    trecho = {"id": "T", "extensao_m": 10, "profundidade_m": 1.363, "largura_m": 0.65, "lastro_m": 0.1,
              "material": "PEAD", "metodologia": "VCA"}
    mapa = {"gaveta1": [{"servico": "ASSENTAMENTO", "coluna": "M", "unidade": "M"},
                        {"servico": "AREIA", "coluna": "AR", "unidade": "M3"}],
            "solda": {"servico": "SOLDA", "comprimento_barra_m": 6.0}}

    def test_a_confirmar_bloqueia(self):
        with self.assertRaises(R.PerfilPendente):
            R.quantidades_previstas_trecho({**self.trecho, "perfil_status": "A CONFIRMAR"}, {"AR": 1}, 5, self.mapa)

    def test_profundidade_ausente_bloqueia(self):
        with self.assertRaises(R.PerfilPendente):
            R.quantidades_previstas_trecho({**self.trecho, "profundidade_m": None}, {"AR": 1}, 5, self.mapa)

    def test_areia_negativa_bloqueia(self):
        with self.assertRaises(R.PerfilPendente):
            R.quantidades_previstas_trecho(self.trecho, {"AR": -0.238}, 10, self.mapa)

    def test_rateio_por_metro_e_soldas(self):
        q = {x["servico"]: x["previsto"] for x in R.quantidades_previstas_trecho(self.trecho, {"AR": 2.0}, 5, self.mapa)}
        self.assertEqual(q, {"ASSENTAMENTO": 5, "AREIA": 1.0, "SOLDA": 1})

    def test_soldas_teto(self):
        self.assertEqual([R.qtd_soldas(x) for x in (0, 6, 6.01, 12, 76.55)], [0, 1, 2, 2, 13])


class TestFotos(unittest.TestCase):
    def test_trecho_exige_tres(self):
        self.assertEqual(R.fotos_pendentes("TRECHO", [], False), ["SINALIZACAO", "EXECUCAO", "CONCLUIDO"])

    def test_no_herda_sinalizacao(self):
        self.assertEqual(R.fotos_pendentes("CONJUNTO", [], True), ["EXECUCAO", "CONCLUIDO"])

    def test_no_em_area_nova_exige_tres(self):
        self.assertEqual(R.fotos_pendentes("CONJUNTO", ["EXECUCAO"], False), ["SINALIZACAO", "CONCLUIDO"])


class TestEsteira(unittest.TestCase):
    def test_fluxo_valido(self):
        R.validar_transicao("1_PRONTO", "2_ENVIADO", {"empresa": "X", "data_envio": "2026-10-20"})
        R.validar_transicao("4_GDOC_ANALISE", "5A_NEGADO", {"motivo_negativa": "cota"})
        R.validar_transicao("5A_NEGADO", "2_ENVIADO", {})

    def test_gdoc_exige_protocolo(self):
        with self.assertRaises(R.RegraViolada):
            R.validar_transicao("3_RECEBIDO", "4_GDOC_ANALISE", {})

    def test_negado_exige_motivo(self):
        with self.assertRaises(R.RegraViolada):
            R.validar_transicao("4_GDOC_ANALISE", "5A_NEGADO", {"motivo_negativa": " "})

    def test_nao_pula_etapa(self):
        with self.assertRaises(R.RegraViolada):
            R.validar_transicao("1_PRONTO", "6_APROVADO", {"memorando_eset": "1"})

    def test_rotulo_revisao(self):
        self.assertEqual(R.rotulo_etapa("2_ENVIADO", 2), "2. Em Produção (Rev. 2)")


class TestMedicao(unittest.TestCase):
    IND = [{"vigencia_ini": "2026-01-31", "vigencia_fim": "2027-01-30", "indice": 0.0329}]

    def test_valor_bm_bdi_k(self):
        # 76,55 m × 0,78 × (1 + 21,48 %) × (1 − 14,04 %)
        self.assertAlmostEqual(R.valor_bm(76.55, 0.78, "SERVIÇO", 0.1528, 0.2148, -0.1404), 62.35, places=2)
        self.assertAlmostEqual(R.valor_bm(10, 100, "MATERIAL", 0.1528, 0.2148, -0.1404), 990.95, places=2)

    def test_reajuste_out_nov_dez_2026(self):
        for ini, fim in (("2026-10-01", "2026-10-31"), ("2026-11-01", "2026-11-30"), ("2026-12-01", "2026-12-31")):
            self.assertEqual(R.indice_reajuste(ini, fim, self.IND), 0.0329)

    def test_reajuste_jan_2027_pendente(self):
        with self.assertRaises(R.RegraViolada):
            R.indice_reajuste("2027-01-01", "2027-01-31", self.IND)

    def test_antes_do_aniversario_sem_reajuste(self):
        self.assertEqual(R.indice_reajuste("2025-10-01", "2025-10-31", self.IND), 0.0)

    def test_teto(self):
        self.assertEqual(R.aplicar_teto(100, 950, 1000), (50, 50))
        self.assertEqual(R.aplicar_teto(100, 0, None), (100, 0))

    def test_caesb_rateio(self):
        self.assertEqual([round(f, 4) for _, f in R.ratear(1.0, [("a", 3), ("b", 1)])], [0.75, 0.25])


if __name__ == "__main__":
    unittest.main()
