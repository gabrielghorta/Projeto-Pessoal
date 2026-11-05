"""Data da obra = Brasília (relogio.py). O PythonAnywhere roda em UTC: das 21h à meia-noite de Brasília o servidor já estava
no dia seguinte, e o pino e o laranja da equipe liberada no dia sumiam do mapa. Aqui o relógio fica parado em 01:30 UTC,
que é 22:30 em Brasília."""
import os
import sys
import unittest
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import dados_obra as DO  # noqa: E402
import planejamento as P  # noqa: E402
import relogio as RL  # noqa: E402
import servicos as S  # noqa: E402
from test_dados_obra import TR2, BaseDadosObra  # noqa: E402

NOITE_UTC = datetime(2026, 11, 4, 1, 30)           # 22:30 de 03/11 em Brasília (longe do dia real do teste)


class TestRelogio(unittest.TestCase):
    def tearDown(self):
        RL.fixar()

    def test_hoje_e_agora_de_brasilia(self):
        RL.fixar(NOITE_UTC)
        self.assertEqual(RL.hoje().isoformat(), "2026-11-03")
        self.assertEqual(RL.agora().strftime("%H:%M"), "22:30")
        self.assertTrue(S._agora().startswith("2026-11-03T22:30"))
        RL.fixar(datetime(2026, 11, 4, 3, 30))                       # 00:30 em Brasília: aí sim é dia 4
        self.assertEqual(RL.hoje().isoformat(), "2026-11-04")

    def test_data_futura_nos_dois_lados_da_meia_noite(self):
        RL.fixar(NOITE_UTC)
        S.exigir_data_ocorrida("2026-11-03", "Check-in")
        with self.assertRaises(S.RegraViolada):
            S.exigir_data_ocorrida("2026-11-04", "Check-in")             # em UTC já seria "hoje"
        RL.fixar(datetime(2026, 11, 4, 3, 30))
        S.exigir_data_ocorrida("2026-11-04", "Check-in")


class TestPinoANoite(BaseDadosObra):
    def tearDown(self):
        RL.fixar()
        super().tearDown()

    def test_liberacao_as_22h30_acende_o_pino_e_o_laranja(self):
        RL.fixar(NOITE_UTC)
        DO.liberar(self.c, "2026-11-03", "Zona01", [TR2], [], [], "almox1")
        est = S.estado_mapa(self.c)                                    # sem data: o dia de Brasília
        self.assertIn(TR2, [p["alvo_id"] for p in est["pins"]])
        self.assertIn(TR2, P.camadas_mapa(self.c)["em_campo"])
        self.assertIn(TR2, DO.estado(self.c)["em_campo"])


if __name__ == "__main__":
    unittest.main()
