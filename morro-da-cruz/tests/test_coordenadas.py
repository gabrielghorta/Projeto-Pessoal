"""UTM (SIRGAS 2000, fuso 23 Sul) → latitude e longitude, conferida contra as coordenadas do HTML do projeto (D-201)."""
import json
import math
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import coordenadas as K  # noqa: E402
import server  # noqa: E402

MAPA = server._mapa_path()


def _metros(a, b, la, lo):
    return math.hypot((a - la) * 111320, (b - lo) * 111320 * math.cos(math.radians(la)))


class TestCoordenadas(unittest.TestCase):
    def test_ponto_conhecido(self):
        self.assertEqual(K.utm_para_geo(203552.494, 8239199.097), (-15.9087023, -47.7685795))

    def test_ponto_sem_utm_e_com_lat_lon_da_planilha(self):
        self.assertIsNone(K.ponto(None, 8239199.097))
        self.assertEqual(K.ponto(203552.4941, 8239199.0969, -15.9, -47.7, "NÓ1"),
                         {"e": 203552.494, "n": 8239199.097, "lat": -15.9, "lon": -47.7, "no": "NÓ1"})
        self.assertEqual(K.do_trecho("[203552.494, 8239199.097]", None)["fim"], None)

    @unittest.skipUnless(os.path.isfile(MAPA), "sem o HTML do mapa")
    def test_todas_as_pontas_e_nos_do_html_do_projeto(self):
        with open(MAPA, encoding="utf-8") as f:
            html = f.read()
        i = html.find("const DADOS")
        d, _ = json.JSONDecoder().raw_decode(html[html.find("=", i) + 1:].lstrip())
        erros = []
        for t in d["trechos"]:
            for (e, n), (la, lo) in ((t["A"], t["gA"]), (t["B"], t["gB"])):
                erros.append(_metros(*K.utm_para_geo(e, n), la, lo))
        for el in d["els"]:
            if el.get("E") is not None:
                erros.append(_metros(*K.utm_para_geo(el["E"], el["N"]), el["lat"], el["lon"]))
        self.assertEqual(len(erros), 4060)
        self.assertLess(max(erros), 0.02)        # o arredondamento das 7 casas do próprio HTML (cerca de 1 cm)


if __name__ == "__main__":
    unittest.main()
