"""Leitor do .xls (planilha_xls): os tipos de célula do Excel 97-2003, o mini fluxo do arquivo composto e os arquivos
quebrados ou maliciosos (recusados com XlsInvalido, sem laço nem estouro). As planilhas são montadas pelo
tests/ns_sintetica.py (o mesmo formato que o LibreOffice e o Excel abrem)."""
import os
import struct
import sys
import unittest
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import compras as C  # noqa: E402
import ns_sintetica as NS  # noqa: E402
import planilha_xls as X  # noqa: E402

CELULAS = {(0, 0): ('NS nº :', 'General'), (0, 1): (12, '0'), (1, 0): ('Ação — VRP', 'General'), (1, 1): (2.5, '0.00'),
           (1, 2): (-7, '0'), (1, 3): (1234.567891, '#,##0.000'), (2, 0): (datetime(2026, 10, 15), 'dd/mm/yyyy'),
           (2, 2): (True, 'General')}


def valores(linhas):
    return {(r, c): v for r, l in enumerate(linhas) for c, (v, _) in enumerate(l) if v is not None}


class Celulas(unittest.TestCase):
    def test_texto_numero_data_e_booleano_no_mini_fluxo(self):
        dados = NS.xls_de_celulas([('NS', CELULAS)])
        self.assertLess(len(X._fluxo(dados, 'Workbook')), 4096)       # pequena: mora no mini fluxo da raiz
        self.assertTrue(X.eh_xls(dados))
        [(nome, linhas)] = X.abas(dados)
        self.assertEqual(nome, 'NS')
        self.assertEqual(valores(linhas), {k: v for k, (v, _) in CELULAS.items()})
        self.assertIsInstance(valores(linhas)[(0, 1)], int)            # inteiro vem int, como no openpyxl
        self.assertEqual(linhas[1][3][1], '#,##0.000')
        self.assertEqual(linhas[0][3], (None, ''))                     # célula vazia no meio da grade

    def test_fluxo_grande_e_varias_abas(self):
        muitas = {(r, 0): (f'linha {r} ' + 'x' * 40, 'General') for r in range(150)}
        dados = NS.xls_de_celulas([('Primeira', muitas), ('Segunda', CELULAS)], limite_registro=100)
        self.assertGreaterEqual(len(X._fluxo(dados, 'Workbook')), 4096)       # setores normais
        abas = X.abas(dados)
        self.assertEqual([n for n, _ in abas], ['Primeira', 'Segunda'])
        self.assertEqual(valores(abas[0][1])[(149, 0)], 'linha 149 ' + 'x' * 40)
        self.assertEqual(valores(abas[1][1])[(1, 0)], 'Ação — VRP')

    def test_numero_compacto_rk(self):
        for v in (0, 1, -1, 12, -7, 2 ** 29 - 1, -2 ** 29):
            self.assertEqual(X._rk(NS._rk(v)), v, v)
        for v in (2.5, -0.01, 293.47, 1012.45):
            self.assertAlmostEqual(X._rk(NS._rk(v)), v, places=9)
        bits = struct.unpack('<Q', struct.pack('<d', 1.5))[0] >> 32       # double com os 30 bits altos
        self.assertEqual(X._rk(bits & 0xFFFFFFFC), 1.5)

    def test_formato_de_data(self):
        for f in ('dd/mm/yyyy', 'd-mmm-yy', '[$-416]dd/mm/yyyy', 'h:mm'):
            self.assertTrue(X.eh_formato_data(f), f)
        for f in ('General', '0.00', '#,##0.000', '"m" 0.00', '0.00_);[Red](0.00)', '@', ''):
            self.assertFalse(X.eh_formato_data(f), f)


class Recusas(unittest.TestCase):
    def setUp(self):
        self.ok = NS.xls_de_celulas([('NS', {(r, 0): ('x' * 60, 'General') for r in range(120)})])

    def test_cortado_ou_sem_fluxo_workbook(self):
        for dados in (self.ok[:600], self.ok[:300], X.ASSINATURA + b'\0' * 100):
            with self.assertRaises(X.XlsInvalido):
                X.abas(dados)
        doc = NS.composto({'WordDocument': b'\0' * 5000})         # o .doc também é composto, mas não é planilha
        self.assertFalse(X.eh_xls(doc))
        with self.assertRaisesRegex(X.XlsInvalido, 'Workbook'):
            X.abas(doc)
        self.assertEqual(C._tipo_arquivo(doc), (None, None))
        self.assertEqual(C._tipo_arquivo(self.ok), ('xls', 'application/vnd.ms-excel'))

    def test_cadeia_em_laco_e_setor_fora_do_arquivo(self):
        dados = bytearray(self.ok)
        fat1, dir1 = struct.unpack_from('<I', dados, 76)[0], struct.unpack_from('<I', dados, 48)[0]
        ini = struct.unpack_from('<I', dados, (dir1 + 1) * 512 + 128 + 116)[0]      # 1º setor do Workbook
        laco = bytearray(dados)
        struct.pack_into('<I', laco, (fat1 + 1) * 512 + 4 * ini, ini)
        with self.assertRaisesRegex(X.XlsInvalido, 'cadeia'):
            X.abas(bytes(laco))
        fora = bytearray(dados)
        struct.pack_into('<I', fora, 48, 10 ** 6)
        with self.assertRaisesRegex(X.XlsInvalido, 'fora do arquivo|cadeia'):
            X.abas(bytes(fora))

    def test_versao_antiga_e_senha(self):
        bof5 = NS._reg(0x0809, struct.pack('<HHHHII', 0x0500, 5, 0, 0, 0, 0)) + NS._reg(0x000A, b'')
        with self.assertRaisesRegex(X.XlsInvalido, 'BIFF8'):
            X.abas(NS.composto({'Workbook': bof5}))
        senha = (NS._reg(0x0809, struct.pack('<HHHHII', 0x0600, 5, 0, 0, 0, 6)) + NS._reg(0x002F, b'\1\0' + bytes(52))
                 + NS._reg(0x000A, b''))
        with self.assertRaisesRegex(X.XlsInvalido, 'senha'):
            X.abas(NS.composto({'Workbook': senha}))

    def test_tabela_de_textos_cortada(self):
        """SST que promete mais textos do que tem: recusa, sem ler fora do registro."""
        sst = NS._reg(0x00FC, struct.pack('<II', 5, 5) + struct.pack('<HB', 3, 0) + b'abc')
        livro = NS._reg(0x0809, struct.pack('<HHHHII', 0x0600, 5, 0, 0, 0, 6)) + sst + NS._reg(0x000A, b'')
        with self.assertRaisesRegex(X.XlsInvalido, 'truncado'):
            X.abas(NS.composto({'Workbook': livro}))


if __name__ == '__main__':
    unittest.main()
