"""Chuva como interferência, medidas na origem e RM Word editável (D-214 a D-216)."""
import io
import json
import os
import sqlite3
import sys
import unittest
import zipfile
from xml.etree import ElementTree as ET

AQUI=os.path.dirname(os.path.abspath(__file__))
sys.path[:0]=[os.path.dirname(AQUI),AQUI]
import apropriacao as AP
import diario as DI
import importacao as I
import importar
import memoria_calculo as MC
import pacote_medicao as PM
import regras as R
import relatorio_mensal as RM
import servicos as S
from base_real import BaseReal
from perfil_teste import cfg_teste_real
from test_apropriacao import BaseAp,CONTEINER
from test_notas_servico import _ddl
from test_ns_dia import CROQUI,grupo,pdf_dia
from base_real import b64


class TestMedidas(unittest.TestCase):
    def test_perimetro_vezes_altura_e_mais_de_uma_parcela(self):
        r=MC.calcular('m²',[{'comprimento':'80+50+40+20+45','largura':'2','descricao':'Tapume'},
                           {'comprimento':'1,5','largura':'2','repeticoes':2}])
        self.assertEqual(r['quantidade'],476)
        self.assertIn('(80 + 50 + 40 + 20 + 45) × 2 = 470 m²',r['memoria'])
        self.assertIn('Total = 476 m²',r['memoria'])

    def test_metro_e_volume(self):
        self.assertEqual(MC.calcular('M',[{'comprimento':'10+20,5'}])['quantidade'],30.5)
        self.assertEqual(MC.calcular('M3',[{'comprimento':'10','largura':'2','profundidade':'0,15'}])['quantidade'],3)

    def test_nao_aceita_conta_arbitraria_dimensao_ausente_ou_quantidade_falsa(self):
        for p in ([{'comprimento':'__import__(1)','largura':'2'}],[{'comprimento':'80*50','largura':'2'}],
                  [{'comprimento':'80'}],[{'comprimento':'80','largura':'0'}]):
            with self.assertRaises(R.RegraViolada):MC.calcular('M2',p)
        with self.assertRaisesRegex(R.RegraViolada,'não confere'):
            MC.calcular('M2',[{'comprimento':'10','largura':'2'}],500)
        with self.assertRaises(R.RegraViolada):MC.calcular('M2',None,500)


class TestChuva(BaseReal):
    LIBERAR_TUDO=True
    def registrar(self,login='enc3',**kw):
        return self.cli(login).post('/api/ocorrencia',dict({'tipo':'IMPEDIMENTO','categoria':'CHUVA','data':'2026-10-20',
            'equipe_id':'Zona03','turno':'TARDE','clima_condicao':'PARALISADO_CHUVA'},**kw))

    def test_padrao_nao_inventa_linha_de_clima(self):
        d=DI.diario(self.c,'2026-10-20','Zona03')
        self.assertEqual(d['equipes'][0]['clima'],dict.fromkeys(('MANHA','TARDE'),'Sem chuva (padrão)'))
        self.assertEqual(self.n('clima'),0)

    def test_chuva_sem_trecho_com_turno_e_historico_apos_resolver(self):
        oid=self.ok(self.registrar())['id']
        self.assertEqual(S.clima_no_dia(self.c,'2026-10-20','Zona03'),{'MANHA':'SEM_CHUVA','TARDE':'PARALISADO_CHUVA'})
        d=DI.interferencias(self.c,True,'Zona03')
        self.assertEqual((d['ocorrencias'][0]['id'],d['ocorrencias'][0]['categoria']),(oid,'CHUVA'))
        self.ok(self.cli('sup1').post('/api/ocorrencia/resolver',{'ocorrencia_id':oid,'resolucao':'Chuva terminou'}))
        self.assertEqual(S.clima_no_dia(self.c,'2026-10-20','Zona03')['TARDE'],'PARALISADO_CHUVA')
        self.assertEqual(self.n('clima'),0)

    def test_encarregado_nao_registra_outra_equipe_e_rh_nao_grava(self):
        self.assertEqual(self.registrar(equipe_id='Zona04')[0],403)
        self.assertEqual(self.registrar('rh1')[0],403)
        self.recusa(self.registrar(turno='NOITE'),422,'manhã')
        self.assertEqual(self.n('ocorrencia_chuvas'),0)

    def test_nota_sem_clima_e_chuva_informada_depois_pelo_campo(self):
        pdf=pdf_dia([grupo(['NÓ9.1','CH_VRP-15'],[295.98],obs=['ASSENTAMENTO',None])],data='2026-10-20')
        r=self.ok(self.cli('eng1').post('/api/ns/execucao',{'equipe_id':'Zona03','pdf_b64':b64(pdf),'croqui_b64':CROQUI}))
        self.assertEqual(r['fila'],[]);self.assertEqual(self.n('clima'),0)
        self.ok(self.registrar())
        self.assertEqual(S.clima_no_dia(self.c,'2026-10-20','Zona03')['TARDE'],'PARALISADO_CHUVA')


class TestMemoriaNaOrigem(BaseAp):
    def tapume(self):
        return next(it for it in AP.buscar(self.c,'tapume') if R.normalizar_unidade(it['unidade'])=='M2')

    def lancar_tapume(self):
        it=self.tapume()
        return self.ok(self.cli('eng1').post('/api/apropriacao',{'item_ref':it['ref'],'data':'2026-10-20',
            'parcelas':[{'comprimento':'80+50+40+20+45','largura':'2','descricao':'Tapume'}]}))

    def test_sem_extras_obrigatorios_e_quantidade_calculada(self):
        r=self.lancar_tapume()
        self.assertEqual(r['quantidade'],470)
        self.assertEqual((r['executor_tipo'],r['justificativa'],r['documentos']),('NAO_INFORMADO','',[]))
        self.assertIn('80 + 50 + 40 + 20 + 45',r['memoria_calculo'])
        self.assertEqual(r['calculo']['parcelas'][0]['largura'],'2')
        self.assertEqual(r['registrado_por'],'eng1')

    def test_memoria_segue_para_bm_sem_duplicar_quantidade(self):
        mid=self.medicao(ini='2026-10-01',fim='2026-10-31')
        a=self.lancar_tapume();linhas=PM._linhas_memorial(self.c,mid,a['item'],a['unidade'])
        self.assertEqual(sum(l['quantidade'] for l in linhas),470)
        self.assertIn('PERÍMETRO (80 + 50 + 40 + 20 + 45)',linhas[0]['ref'])
        self.assertEqual(len(linhas),1)
        self.assertEqual(linhas[0]['medidas']['comprimento'],235)
        nome,dados,_=PM.gerar(self.c,mid)
        from openpyxl import load_workbook
        w=load_workbook(io.BytesIO(dados),data_only=False)
        mc=next(s for s in w if s.title.endswith('MC'))
        textos=' '.join(str(c.value) for row in mc for c in row if c.value is not None)
        self.assertIn('80 + 50 + 40 + 20 + 45',textos)
        self.assertIn('ALTURA/LARGURA (M)',textos)

    def test_quantidade_sozinha_nao_basta_para_area(self):
        self.recusa(self.cli('eng1').post('/api/apropriacao',{'item_ref':self.tapume()['ref'],
            'data':'2026-10-20','quantidade':500}),422,'medidas')
        self.assertEqual(self.n('apropriacoes'),0)

    def test_word_editavel_com_mesmos_totais_e_sem_perder_figuras(self):
        mid=self.medicao(ini='2026-10-01',fim='2026-10-31');self.lancar_tapume()
        self.apropriar(CONTEINER,1,data='2026-10-20')  # foto sintética opcional aparece no Word
        nome,dados,d=RM.gerar_docx(self.c,mid)
        self.assertTrue(nome.endswith('.docx'))
        z=zipfile.ZipFile(io.BytesIO(dados));raiz=ET.fromstring(z.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        t=' '.join(e.text or '' for e in raiz.findall('.//w:t',ns))
        self.assertIn('Morro da Cruz',t);self.assertIn('TESTE',t)
        self.assertIn('470,00',t)
        self.assertIn('montagem do canteiro',t)
        self.assertGreater(len(raiz.findall('.//w:tbl',ns)),8)
        self.assertTrue(any(n.startswith('word/media/') for n in z.namelist()))
        self.assertEqual(d['totais']['total'],RM.dados(self.c,mid)['totais']['total'])
        st,h,b=self.abrir('eng1',f'/api/relatorios/mensal?id={mid}')
        self.assertEqual((st,h['Content-Type']),(200,'application/vnd.openxmlformats-officedocument.wordprocessingml.document'))
        self.assertTrue(b.startswith(b'PK'))

    def test_migracao_v25_preserva_memoria_e_evidencia_sem_inventar_dimensoes(self):
        a=self.apropriar(CONTEINER,2)
        c=sqlite3.connect(self.db,isolation_level=None);c.execute('PRAGMA foreign_keys=OFF')
        for tabela,alteracoes in [('apropriacoes',[("'NAO_INFORMADO',",''),
            ('  calculo_json TEXT,                  -- parcelas e dimensões informadas; não reconstruídas do total antigo\n','')]),
            ('clima',[("'SEM_CHUVA',",'')])]:
            sql=_ddl(tabela,alteracoes).replace('CREATE TABLE '+tabela+' (','CREATE TABLE '+tabela+'__25 (')
            c.execute(sql)
            cols=','.join(r[1] for r in c.execute('PRAGMA table_info('+tabela+'__25)'))
            c.execute(f'INSERT INTO {tabela}__25({cols}) SELECT {cols} FROM {tabela}')
            c.execute('DROP TABLE '+tabela);c.execute(f'ALTER TABLE {tabela}__25 RENAME TO {tabela}')
        c.execute('DROP TABLE ocorrencia_chuvas');c.execute('DELETE FROM schema_versao')
        c.execute("INSERT INTO schema_versao VALUES (25,'2026-11-05','estado anterior')");c.close()
        rel=importar.aplicar(self.db,I.DIR_PLANILHAS,cfg=cfg_teste_real(),dir_relatorios=os.path.join(self.tmp,'mig26'))
        self.assertEqual((rel['esquema_antes'],rel['esquema_depois']),(25,26))
        b=AP.resumo(self.c,a['id']);self.assertEqual((b['quantidade'],b['memoria_calculo']),(a['quantidade'],a['memoria_calculo']))
        self.assertIsNone(b['calculo']);self.assertEqual(len(b['documentos']),1)
        self.assertEqual(self.c.execute('PRAGMA foreign_key_check').fetchall(),[])


if __name__=='__main__':unittest.main()
