"""Leitor da Nota de Serviço (ns_leitura): NS de água sintética desta obra em texto, PDF (deitado e girado) e planilha,
a NS 006 de outra obra recusada pelo contrato, contas quebradas, PDF sem texto e nomes dos elementos da rede de água.
Os PDFs reais (com nome e CREA de pessoas) não ficam no repositório: o teste deles só roda com MC_NS_EXEMPLOS apontando
para a pasta local com ns_assinada.pdf e ns_nao_assinada.pdf."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import ns_leitura as L  # noqa: E402
import ns_sintetica as NS  # noqa: E402

OBRA = 'CT 10239/2026 Caesb × Ankara'
HOJE = '2026-10-21'


def ler_texto(pags, fieis=True, **regras):
    ns = L.parse_texto(pags, {'posicoes_fieis': fieis, 'paginas': len(pags)})
    ns.update(L.verificar(ns, contrato_obra=regras.pop('contrato_obra', OBRA), hoje=regras.pop('hoje', HOJE), **regras))
    return ns


def falhas(ns):
    return sorted({v['id'] for v in ns['verificacoes'] if not v['ok'] and v['nivel'] == 'ERRO'})


class ChaveElemento(unittest.TestCase):
    def test_mesma_chave_dos_dois_lados(self):
        casos = {'Zona03_PB08_Rede_NÓ9.1': 'NO9.1', 'NÓ 9.1': 'NO9.1', 'N 9-1': 'NO9.1', 'Nó-09.1': 'NO9.1',
                 'NÓ 9.1 (TÊ 160x160 - DERIV. P/ VRP-15)': 'NO9.1', 'Zona03_PB08_CH_VRP-15': 'VRP-15', 'VRP 015': 'VRP-15',
                 'CH_VRP-15 (CAIXA DA VRP)': 'VRP-15', 'Zona02_PB05_CH_MV-01': 'MV-1', 'MACROMEDIDOR 1': 'MV-1',
                 'Zona01_PB02_CH_VM-1.2': 'VM-1.2', 'REGISTRO 1.2': 'VM-1.2', 'VENTOSA 22': 'VTF-22',
                 'Zona04_PB02_CH_VTF-22': 'VTF-22', 'DESCARGA 33': 'DF-33', 'Zona01_PB01_Rede_DF-33': 'DF-33',
                 'HIDRANTE 02': 'HID-2', 'Zona02_PB07_Adutora_NÓ94.1': 'NO94.1', 'TUBO PEAD DN 160': 'TUBO PEAD DN 160'}
        for texto, chave in casos.items():
            self.assertEqual(L.chave_elemento(texto), chave, texto)
        self.assertIsNone(L.chave_elemento(''))

    def test_contrato_so_numero_e_ano(self):
        self.assertEqual(L.norm_contrato(OBRA), '10239/2026')
        self.assertEqual(L.norm_contrato('CT 9702/24'), '9702/2024')
        self.assertEqual(L.contexto_zona_pb('"REDE DE ÁGUA" - ZONA 03 - PB08 - VER CROQUI'), {'zona': 'Zona03', 'pb': 'PB08'})


class NsDeAgua(unittest.TestCase):
    """NÓ6.1 → NÓ9.1 → CH_VRP-15 (Zona03 PB08) no leiaute Caesb: texto, PDF deitado e girado e planilha dão a mesma NS."""

    @classmethod
    def setUpClass(cls):
        cls.args = NS.ns_zona03_pb08()
        cls.pags = NS.paginas_ns(**cls.args)

    def test_texto_aceito_com_contas_e_segmentos(self):
        ns = ler_texto(self.pags)
        self.assertTrue(ns['resultado']['aceita'], ns['resultado'])
        c = ns['cabecalho']
        self.assertEqual((c['numero'], L.norm_contrato(c['contrato']), c['data'], c['folha'], c['total_folhas'], c['bloco']),
                         ('012', '10239/2026', '2026-10-15', 1, 1, 'TOPOGRAFIA'))
        g = ns['grupos'][0]
        self.assertEqual([l['chave'] for l in g['linhas']], ['NO6.1', 'NO9.1', 'VRP-15'])
        self.assertEqual([l['dist_acumulada'] for l in g['linhas']], [0.0, 277.99, 573.97])
        self.assertEqual([(s['chave_de'], s['chave_para'], s['metros'], s['sentido']) for s in g['segmentos']],
                         [('NO9.1', 'NO6.1', 277.99, 'contra_estaqueamento'), ('VRP-15', 'NO9.1', 295.98, 'contra_estaqueamento')])
        self.assertEqual((ns['total_geral'], g['dn_mm'], g['material']), (573.97, 160, 'PEAD'))
        self.assertEqual(L.contexto_zona_pb(c['titulo'], g['titulo']), {'zona': 'Zona03', 'pb': 'PB08'})
        self.assertEqual([a['nome'] for a in ns['assinaturas']][:2], ['[NOME]', '[NOME]'])

    def test_pdf_deitado_girado_e_planilha_dao_a_mesma_ns(self):
        ref = ler_texto(self.pags)
        for girar in (False, True):
            r = L.ler(NS.pdf_de_texto(self.pags, girar=girar), OBRA, HOJE, comparar=False)
            self.assertEqual(L.impressao_tecnica(r), L.impressao_tecnica(ref), girar)
            self.assertTrue(r['fonte']['extrator'].startswith('pypdf'))
        r = L.ler(NS.pdf_de_texto(self.pags), OBRA, HOJE, planilha=NS.xlsx_de_ns(**self.args))
        self.assertEqual(r['fonte']['conferido_com'], {'extrator': 'planilha .xlsx', 'mesma_impressao': True})
        self.assertTrue(r['resultado']['aceita'], r['resultado'])

    def test_planilha_diferente_do_pdf_e_falha_de_leitura(self):
        outra = NS.ns_zona03_pb08()
        outra['grupos'] = [NS.grupo_padrao(outra['grupos'][0]['titulo'], ['NÓ6.1 - TÊ 160x110', 'NÓ9.1 - TÊ 160x160',
                                                                           'CH_VRP-15 (CAIXA DA VRP)'], [277.99, 296.10])]
        r = L.ler(NS.pdf_de_texto(self.pags), OBRA, HOJE, planilha=NS.xlsx_de_ns(**outra))
        self.assertFalse(r['fonte']['conferido_com']['mesma_impressao'])
        self.assertIn('E06', falhas(r))
        self.assertIn('leram dados diferentes', r['falhas_leitura'][-1])

    def test_varias_folhas_e_folha_faltando(self):
        g2 = NS.grupo_padrao('REDE ZONA 03 - PB08 - PEAD DE 160 (NÓ9.1 - NÓ113.1)', ['NÓ9.1 - TÊ 160x160', 'NÓ113.1'], [2.51],
                             inicio=277.99)
        args = dict(self.args, grupos=self.args['grupos'] + [g2])
        duas = NS.paginas_ns(folhas=[[0], [1]], **args)
        ns = ler_texto(duas)
        self.assertTrue(ns['resultado']['aceita'], ns['resultado'])
        self.assertEqual([f['folha'] for f in ns['folhas']], [1, 2])
        self.assertEqual(ns['grupos'][1]['continua_de']['elemento'], 'NÓ9.1 - TÊ 160x160')
        self.assertIn('E02', falhas(ler_texto(duas[:1])))                     # só a folha 1 de 2

    def test_contas_quebradas_sao_recusadas(self):
        g = self.args['grupos'][0]
        casos = {'A11': dict(self.args, resumo=[('TUBO PEAD 160mm', 574.97, g['titulo'])], total=574.97),
                 'A13': dict(self.args, total=600.0)}
        for erro, args in casos.items():
            self.assertIn(erro, falhas(ler_texto(NS.paginas_ns(**args))), erro)
        pag = self.pags[0].replace('  277,99', '  279,99', 1)                 # parcial da 2ª linha ≠ acumulada
        self.assertTrue({'A04', 'A08'} & set(falhas(ler_texto([pag]))))
        pag = self.pags[0].replace('1,25', '1,52', 1)                         # profundidade ≠ terreno − GI
        self.assertIn('A01', falhas(ler_texto([pag])))

    def test_data_futura_e_outro_contrato(self):
        self.assertIn('V02', falhas(ler_texto(NS.paginas_ns(**dict(self.args, data='15-out-27')))))
        self.assertIn('V01', falhas(ler_texto(NS.paginas_ns(**dict(self.args, contrato='10240/2026')))))


class NsDeOutraObra(unittest.TestCase):
    def test_ns_006_de_esgoto_recusada_pelo_contrato(self):
        g = NS.grupo_padrao('COLETOR PRINCIPAL - EMISSÁRIO DE ENTRADA (TP - PV.3 - PV.6)',
                            ['CAIXA DE ENTRADA - TRATAMENTO PRELIMINAR', 'PV-3 EMISSÁRIO DE ENTRADA', 'PV-6 EMISSÁRIO DE ENTRADA'],
                            [17.32, 8.24], material='PEAD-1000')
        pags = NS.paginas_ns(numero='006', contrato='9702/2024', data='27-out-25', grupos=[g],
                             localizacao='TRATAMENTO PRELIMINAR - ETE - ESTAÇÃO DE TRATAMENTO DE ESGOTOS PARANOÁ/DF',
                             titulo='"EMISSÁRIO DE ENTRADA" - TRATAMENTO PRELIMINAR - ETE PARANOÁ/DF - VER CROQUI ANEXO')
        for ns in (ler_texto(pags), L.ler(NS.pdf_de_texto(pags), OBRA, HOJE)):
            self.assertFalse(ns['resultado']['aceita'])
            self.assertEqual(falhas(ns), ['V01'], ns['resultado'])
            self.assertIn('9702/2024', ns['resultado']['motivos'][0])


class ArquivoRecusado(unittest.TestCase):
    def test_sem_texto_nao_pdf_e_grande_demais(self):
        try:
            sem_texto = NS.pdf_sem_texto()
        except ImportError:
            self.skipTest('sem Pillow')
        with self.assertRaisesRegex(L.LeituraRecusada, 'sem camada de texto'):
            L.ler(sem_texto, OBRA, HOJE)
        with self.assertRaisesRegex(L.LeituraRecusada, 'não é um PDF'):
            L.ler(b'GIF89a...', OBRA, HOJE)
        with self.assertRaisesRegex(L.LeituraRecusada, 'maior que'):
            L.ler(b'%PDF-' + b'0' * L.LIMITE_PDF, OBRA, HOJE)
        with self.assertRaisesRegex(L.LeituraRecusada, 'folhas'):
            L.ler(NS.pdf_de_texto(['x'] * (L.LIMITE_PAGINAS + 1)), OBRA, HOJE)
        with self.assertRaisesRegex(L.LeituraRecusada, '.xlsx'):
            L.ler_planilha(b'\xd0\xcf\x11\xe0 planilha .xls antiga')


EXEMPLOS = os.environ.get('MC_NS_EXEMPLOS')


@unittest.skipUnless(EXEMPLOS and os.path.isdir(EXEMPLOS), 'PDFs reais da NS 006 fora do repositório (MC_NS_EXEMPLOS)')
class PdfsReais(unittest.TestCase):
    def test_assinada_e_nao_assinada_mesma_impressao_e_recusadas(self):
        lidas = []
        for nome in ('ns_assinada.pdf', 'ns_nao_assinada.pdf'):
            with open(os.path.join(EXEMPLOS, nome), 'rb') as f:
                r = L.ler(f.read(), OBRA, HOJE)
            self.assertEqual(falhas(r), ['V01'], nome)
            self.assertEqual((r['cabecalho']['numero'], r['total_geral'], len(r['grupos'])), ('006', 70.71, 2))
            if r['fonte'].get('conferido_com'):
                self.assertTrue(r['fonte']['conferido_com']['mesma_impressao'], nome)
            lidas.append(r['impressao_dados'])
        self.assertEqual(lidas[0], lidas[1])


if __name__ == '__main__':
    unittest.main()
