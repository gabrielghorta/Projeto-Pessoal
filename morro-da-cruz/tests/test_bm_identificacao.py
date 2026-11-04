"""Identificação da Ankara no BM REV04 (colunas B a L da principal e F a P da vertical), revisada em 04/11/2026 (D-203):
cada item diz o que a descrição da Caesb diz, e as duas abas dizem o mesmo para o mesmo código."""
import os
import sys
import unittest

from openpyxl.utils import get_column_letter

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import importacao as I  # noqa: E402

CFG = I.carregar_config()
BM = I.caminho(CFG, "bm")
VERTICAL_DE = {"B": "F", "C": "G", "D": "H", "E": "I", "F": "J", "G": "K", "H": "L", "J": "N", "L": "P"}


@unittest.skipUnless(BM, "BM ausente em planilhas/")
class TestIdentificacaoBM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        letras = lambda r: {get_column_letter(k): v for k, v in enumerate(r, 1)}
        with I.planilha(BM) as wb:
            cls.jun = {str(r[0]): letras(r) for r in wb["BM MORRO DA CRUZ"].iter_rows(min_row=6, values_only=True)
                       if r[0] and r[1]}          # o mesmo filtro da importação
            cls.ver = [letras(r) for r in wb["BM MORRO DA CRUZ - VERTICAL"].iter_rows(min_row=6, values_only=True)
                       if r[3]]

    def test_o_portao_e_os_itens_trocados_dizem_o_que_sao(self):
        j = self.jun
        self.assertEqual((j["5.14.3"]["B"], j["5.14.3"]["E"], j["5.14.3"]["J"]),
                         ("PORTÃO PARA VEÍCULOS PADRÃO CAESB - ESTRUTURA EM TUBO E TELA DE ARAME GALVANIZADO", "PORTÃO", "CANTEIRO"))
        self.assertIn("PORTÃO PARA VEÍCULOS", j["5.14.3"]["M"])
        self.assertTrue(j["5.7.7"]["B"].startswith("ASSENTAMENTO DE HIDRANTE DE COLUNA"))
        self.assertEqual(j["5.18.1"]["E"], "KIT CAVALETE")
        self.assertEqual((j["5.9.5"]["E"], j["5.9.5"]["J"]), ("RECOMPOSIÇÃO ASFÁLTICA", "PAVIMENTAÇÃO"))
        self.assertEqual(j["5.11.2"]["J"], "CANTEIRO")                 # trama do telhado, não transporte
        self.assertEqual(j["1.5.1"]["H"], "CONCRETO")
        # descrição curta sozinha ("TUBO", "HIDRÔMETRO") não identifica o item
        self.assertEqual([i for i, x in j.items() if str(x["B"]).strip() in ("TUBO", "HIDRÔMETRO", "TAMPÃO FºFº", "CAIXA D’ÁGUA")], [])

    def test_principal_e_vertical_iguais_para_o_mesmo_codigo(self):
        por_codigo = {str(x["K"]): x for x in self.jun.values()}
        dif = [(v["E"], cv, v[cv], por_codigo[str(v["O"])][cj]) for v in self.ver for cj, cv in VERTICAL_DE.items()
               if str(v[cv]) != str(por_codigo[str(v["O"])][cj])]
        self.assertEqual(dif, [])
        self.assertEqual((len(self.jun), len(self.ver)), (347, 432))

    def test_quantidades_e_precos_do_contrato_nao_mudaram(self):
        j = self.jun
        self.assertEqual((j["5.14.3"]["N"], j["5.14.3"]["O"], j["5.14.3"]["P"]), ("M2", 10, 771.04))
        self.assertEqual(sum(1 for x in j.values() if x["L"] == "MATERIAL"), 185)


if __name__ == "__main__":
    unittest.main()
