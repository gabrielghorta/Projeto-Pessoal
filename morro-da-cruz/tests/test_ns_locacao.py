"""Modelo de locação por estacas, com os arquivos de teste gerados a partir de dados sintéticos."""
import io
import json
import unittest

import openpyxl

from base_real import TR006, TR007, TR020, BaseReal, b64, pdf_ns
import importacao as I
import ns_leitura as L
import ns_sintetica as NSS

CONTRATO = '10239/2026'
HOJE = '2026-11-15'


def folhas():
    intervalos = [
        (('NÓ6.1', 0, 0), ('NÓ9.1', 13, 17.99)),
        (('NÓ 9.1', 13, 17.99), ('CURVA', 28, 13.97)),
    ]
    out = []
    for i, extremos in enumerate(intervalos, 1):
        celulas = {(0, 24): 'CONTRATO No.:', (1, 6): 'LOCAL: MORRO DA CRUZ', (1, 24): f'No. Folha: {i}/2',
                   (2, 24): 'DATA:', (2, 25): '04/11/2026', (3, 6): 'TRECHO: SUB ADUTORA REDE 4 PEAD 160mm',
                   (5, 1): 'PV', (5, 2): 'ESTACAS', (7, 2): 'Int.', (7, 3): 'Fração', (7, 30): 'ACUM'}
        for j, (pv, est, frac) in enumerate(extremos, 8):
            celulas.update({(j, 0): 1, (j, 1): pv, (j, 2): est, (j, 3): frac, (j, 13): 0.160,
                            (j, 30): round(est * 20 + frac, 2)})
        celulas[(8, 31)] = '#VALUE!'   # não existe uma estaca anterior na primeira linha
        celulas[(10, 30)], celulas[(10, 31)] = '-', '#VALUE!'
        out.append((f'REDE 4 ({i})', celulas))
    return out


def xlsx(abas):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nome, celulas in abas:
        w = wb.create_sheet(nome)
        for (lin, col), valor in celulas.items():
            w.cell(lin + 1, col + 1, valor)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestPlanilhaLocacao(unittest.TestCase):
    def test_xls_e_xlsx_mesma_leitura_com_folhas_fora_de_ordem(self):
        abas = folhas()
        legado = NSS.xls_de_celulas([(nome, {rc: (v, 'General') for rc, v in c.items()}) for nome, c in abas])
        a = L.ler_locacao(legado, CONTRATO, HOJE)
        b = L.ler_locacao(xlsx(abas[::-1]), CONTRATO, HOJE)
        self.assertEqual(a['impressao_dados'], b['impressao_dados'])
        self.assertEqual(a['total_geral'], 573.97)
        self.assertEqual([x['folha'] for x in b['resumo']], [1, 2])

    def test_valida_folhas_contrato_continuidade_e_celulas(self):
        abas = folhas()
        with self.assertRaisesRegex(L.LeituraRecusada, 'Folhas de locação faltando'):
            L.ler_locacao(xlsx(abas[:1]), CONTRATO, HOJE)
        abas[1][1][(0, 25)] = '77777/2026'
        with self.assertRaisesRegex(L.LeituraRecusada, 'contrato informado'):
            L.ler_locacao(xlsx(abas), CONTRATO, HOJE)
        abas[1][1].pop((0, 25))
        abas[1][1][(8, 3)] += 1
        with self.assertRaisesRegex(L.LeituraRecusada, r'linha 9: a distância acumulada'):
            L.ler_locacao(xlsx(abas), CONTRATO, HOJE)
        abas[1][1][(8, 30)] += 1
        with self.assertRaisesRegex(L.LeituraRecusada, 'estaca inicial não coincide'):
            L.ler_locacao(xlsx(abas), CONTRATO, HOJE)


class TestLocacaoHTTP(BaseReal):
    def test_envio_libera_identificado_e_vincula_pendencia_sem_duplicar(self):
        planilha = xlsx(folhas())
        anexo1 = NSS.pdf_de_texto(['PLANTA DE LOCAÇÃO\nNº DA PRANCHA: 9/12\nNº DO CONTRATO: 00/2026'])
        anexo2 = NSS.pdf_de_texto(['PLANTA DE LOCAÇÃO\nNº DA PRANCHA: 9/12\nOutra planta'])
        pacote = {'planilha_b64': b64(planilha), 'planilha_nome': 'tyopogradia.xlsx', 'zona': 'Zona03', 'pb': 'PB08',
                  'croquis': [{'nome': 'Croqui 8.pdf', 'croqui_b64': b64(anexo1)},
                              {'nome': 'Croqui 9.pdf', 'croqui_b64': b64(anexo2)}]}
        self.assertEqual(self.cli('sup1').post('/api/ns/locacao', pacote)[0], 403)
        cliente = self.cli('eng1')
        r = self.ok(cliente.post('/api/ns/locacao', pacote))
        self.assertEqual((r['gravado_m'], r['pendente_m'], r['conferir']), (277.99, 295.98, 1))
        self.assertIn('mesmo número de prancha', ' '.join(r['avisos']))
        self.assertEqual(self.liberacoes(TR020), [(0.0, 277.99, 'tyopogradia.xlsx', True)])
        self.assertEqual(self.liberacoes(TR006), [])
        self.assertEqual(self.ok(cliente.post('/api/ns/locacao', dict(pacote, planilha_nome='renomeada.xlsx')))['id'], r['id'])
        self.assertEqual(self.n('notas_servico'), 1)
        nota = self.ok(cliente.get(f"/api/ns/detalhe?id={r['id']}"))
        self.assertIsNone(nota['pdf_id'])
        self.assertEqual(nota['referencia'], 'tyopogradia.xlsx')
        self.assertEqual([c['nome'] for c in nota['croquis_locacao']], ['Croqui 8.pdf', 'Croqui 9.pdf'])
        self.assertEqual(self.abrir('eng1', f"/api/ns/arquivo?id={r['id']}&qual=croqui-2")[2], anexo2)
        self.assertEqual(self.abrir('eng1', f"/api/ns/arquivo?id={r['id']}&qual=planilha")[2], planilha)
        self.assertEqual(self.abrir('sup1', f"/api/ns/arquivo?id={r['id']}&qual=planilha")[0], 403)

        seg = next(s for s in nota['segmentos'] if s['situacao'] != 'AUTOMATICO')
        rota = '/api/ns/locacao/vincular'
        corpo = {'ns_id': r['id'], 'segmento_id': seg['id'],
                 'vinculos': [{'fisico_id': 'TF-00337', 'ini_m': 0, 'fim_m': 295.98}]}
        incompleto = dict(corpo, vinculos=[dict(corpo['vinculos'][0], fim_m=50)])
        self.recusa(cliente.post(rota, incompleto), 422, 'diferença máxima')
        self.assertEqual(self.ok(cliente.post(rota, corpo))['gravado_m'], 295.98)
        self.assertEqual(self.liberacoes(TR007), [(0.0, 2.51, 'tyopogradia.xlsx', True)])
        self.assertEqual(self.liberacoes(TR006), [(0.0, 293.47, 'tyopogradia.xlsx', True)])
        self.assertTrue(self.ok(cliente.post(rota, corpo))['repetida'])
        dados = self.ok(cliente.get(f'/api/detalhe?tipo=TRECHO&id={TR020}'))
        self.assertEqual(dados['complementar']['LIBERACAO_TOPOGRAFICA']['registros'][0]['referencia'], 'tyopogradia.xlsx')
        audit = json.loads(self.c.execute("SELECT corpo FROM auditoria WHERE rota='/api/ns/locacao' AND status=200").fetchone()[0])
        self.assertEqual((audit['planilha_b64'], audit['croquis'][0]['croqui_b64']), ('[omitido]', '[omitido]'))

    def test_migracao_preserva_nota_pdf_e_liberacoes(self):
        planilha_antiga = b64(NSS.xls_de_ns(**NSS.ns_zona03_pb08()))
        r = self.ok(self.registrar('eng1', 'TOPOGRAFIA', pdf_ns(), planilha_b64=planilha_antiga))
        c = self.c
        c.execute('PRAGMA foreign_keys=OFF')
        ddl = I._ddl_atual('notas_servico').split('  arquivo_locacao TEXT,', 1)[0].rstrip().removesuffix(',') + '\n);'
        ddl = ddl.replace('IF NOT EXISTS notas_servico', 'ns_v26').replace(
            'pdf_id INTEGER REFERENCES', 'pdf_id INTEGER NOT NULL REFERENCES')
        c.execute(ddl)
        colunas = ','.join(row[1] for row in c.execute('PRAGMA table_info(ns_v26)'))
        c.execute(f'INSERT INTO ns_v26 SELECT {colunas} FROM notas_servico')
        c.execute('DROP TABLE notas_servico')
        c.execute('ALTER TABLE ns_v26 RENAME TO notas_servico')
        c.execute('DELETE FROM schema_versao WHERE versao=27')
        I.preparar_v27(c)
        c.execute('PRAGMA foreign_keys=ON')
        self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.liberacoes(TR020), [(0.0, 277.99, 'NS 012 fl. 01/01', True)])
        nota = self.ok(self.cli('eng1').get(f"/api/ns/detalhe?id={r['id']}"))
        self.assertIsNotNone(nota['pdf_id'])
        self.assertIsNone(nota['arquivo_locacao'])


if __name__ == '__main__':
    unittest.main()
