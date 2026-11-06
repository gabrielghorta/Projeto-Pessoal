"""D-218: lados/soma, colunas calculáveis na MC e Word interoperável, sem dados pessoais reais."""
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from xml.etree import ElementTree as ET

from openpyxl import load_workbook
import apropriacao as AP
import memoria_calculo as MC
import pacote_medicao as PM
import relatorio_mensal as RM
import relatorio_word as RW
import docx_simples as DS
import regras as R
import servicos as S
from test_apropriacao import BaseAp
from base_real import BaseReal
from test_pacote_medicao import BasePacote, TRS


class TestMedidasV2(unittest.TestCase):
    def test_croqui_mostra_rede_anterior_mesmo_fora_dos_alvos_da_semana(self):
        d={'trechos':{'antigo':{'seg':(0,0,20,0),'extensao_m':20},
                      'atual':{'seg':(20,0,40,0),'extensao_m':20}},
           'word_registros':[dict(trecho_id='antigo',etapa='ASSENTADO',ini_m=0,fim_m=20,data='2026-10-10'),
                             dict(trecho_id='atual',etapa='ASSENTADO',ini_m=0,fim_m=20,data='2026-10-13')]}
        with patch.object(RW.RM,'_mapa') as mapa:
            RW.croqui_semana(None,None,0,0,700,205,d,{'trechos':{'atual'}},'2026-10-12','2026-10-18')
        camadas=mapa.call_args.args[6]
        self.assertEqual(camadas[1],('F2C200',1.7,[(0,0,20,0)]))
        self.assertEqual(camadas[2],('D00000',2.5,[(20,0,40,0)]))

    def test_lados_ou_soma_mesmo_total(self):
        lados=[dict(nome=n,comprimento=v) for n,v in zip(('A-B','B-C','C-D','D-E','E-A'),(80,50,40,20,45))]
        a=MC.calcular('M2',[dict(lados=lados,largura=2)])
        b=MC.calcular('M2',[dict(soma='80+50+40+20+45',largura=2)])
        self.assertEqual((a['quantidade'],b['quantidade']),(470,470))
        self.assertEqual(a['versao'],2)
        self.assertEqual(a['parcelas'][0]['lados'],[dict(nome=l['nome'],comprimento=str(l['comprimento'])) for l in lados])
        self.assertEqual(MC.ler(a)['quantidade'],470)
        self.assertEqual(MC.ler(b)['quantidade'],470)

    def test_dois_caminhos_juntos_recusados_e_limites(self):
        for p in ([dict(lados=[dict(comprimento=80)],soma='50',largura=2)],
                  [dict(lados=[dict(comprimento=1)]*31,largura=2)],
                  [dict(lados=[dict(comprimento='80+50')],largura=2)],
                  [dict(comprimento=1,largura=2)]*31,
                  [dict(comprimento=1,largura=2,repeticoes=0)]):
            with self.subTest(p=p),self.assertRaises(R.RegraViolada):MC.calcular('M2',p)

    def test_duas_partes_repeticoes_m3_m_e_outras_unidades(self):
        self.assertEqual(MC.calcular('M2',[dict(soma='10+20',largura=2),dict(lados=[dict(comprimento=5)],largura='2,2',repeticoes=2)])['quantidade'],82)
        self.assertEqual(MC.calcular('M3',[dict(lados=[dict(comprimento=10)],largura=2,profundidade='0,15',repeticoes=2)])['quantidade'],6)
        self.assertEqual(MC.calcular('M',[dict(lados=[dict(comprimento=10),dict(comprimento=20)])])['quantidade'],30)
        self.assertIsNone(MC.calcular('MES',None,3))

    def test_grafico_inclui_todos_colaboradores_somente_identificadores(self):
        class Folha:
            w=700
            def figura(self,w,h,fn,legenda):fn(None,None,0,0,w,h)
            def paragrafo(self,*args,**kw):pass
        col=[(f'IS-{i}',1) for i in range(83)]
        with patch.object(RW.RM,'_grafico') as grafico:
            RW.colaboradores({'efetivo':{'colaboradores':col}},Folha())
            labels=[v for chamada in grafico.call_args_list for v in chamada.args[6]]
        self.assertEqual(labels,[c for c,_ in col])

    def test_v1_lida_sem_inventar_lados_e_conta_nao_e_cortada(self):
        c=MC.ler(dict(versao=1,unidade='M2',parcelas=[dict(descricao='Tapume',comprimento='80 + 50 + 40 + 20 + 45',largura='2',repeticoes=1,quantidade=470)],quantidade=470))
        self.assertEqual(c['quantidade'],470)
        self.assertEqual(c['parcelas'][0]['lados'],[])
        self.assertIn('PERÍMETRO (80 + 50 + 40 + 20 + 45)',MC.referencia(c['parcelas'][0],1))
        c=MC.calcular('M2',[dict(descricao='Descrição muito extensa '*7,soma='+'.join(['80']*30),largura=2)])
        ref=MC.referencia(c['parcelas'][0],1)
        self.assertLessEqual(len(ref),64);self.assertNotIn('80 +',ref);self.assertIn('VER APROPRIAÇÃO',ref)


class TestMCColunas(BaseAp):
    def criar(self,parcelas,unidade='M2'):
        itens=AP.buscar(self.c,'tapume') if unidade=='M2' else AP.catalogo(self.c)
        it=next(x for x in itens if R.normalizar_unidade(x['unidade'])==unidade and x['classificacao']=='SERVIÇO' and x['situacao']=='APROVADO')
        self.mid=self.medicao(ini='2026-10-01',fim='2026-10-31')
        return self.ok(self.cli('eng1').post('/api/apropriacao',dict(item_ref=it['ref'],data='2026-10-20',parcelas=parcelas)))

    def folha(self,a):
        _,dados,r=PM.gerar(self.c,self.mid)
        wb=load_workbook(io.BytesIO(dados))
        mc=wb[r['aba_mc']]
        base=next(row[0].row-6 for row in mc.iter_rows(min_col=3,max_col=3) if row[0].value==a['item'])
        return mc,base,r

    def test_tapume_em_uma_linha_numeros_e_titulos(self):
        a=self.criar([dict(soma='80+50+40+20+45',largura=2)])
        self.assertEqual((a['quantidade'],a['executor_tipo'],a['justificativa'],a['documentos']),(470,'NAO_INFORMADO','',[]))
        mc,r0,r=self.folha(a);row=r0+PM.MEMORIAL
        self.assertIn('PERÍMETRO (80 + 50 + 40 + 20 + 45)',mc[f'N{row}'].value)
        self.assertEqual((mc[f'T{row}'].value,mc[f'U{row}'].value),(235,2))
        self.assertEqual(mc[f'W{row}'].value,f'=IF(OR(T{row}="",U{row}=""),0,T{row}*U{row})')
        self.assertEqual(mc[f'T{row-1}'].value,'COMPRIMENTO (M)')
        self.assertEqual(mc[f'U{row-1}'].value,'ALTURA/LARGURA (M)')
        self.assertTrue(mc[f'T{row-1}'].alignment.wrap_text)
        self.assertTrue(mc[f'U{row-1}'].alignment.wrap_text)
        self.assertEqual(mc[f'N{row+1}'].value,None)
        self.assertIn('235',mc[f'X{r0+8}'].value)
        self.assertEqual(sum(l['quantidade'] for l in r['folhas'][0]['linhas']),470)

    def test_duas_partes_duas_linhas_repeticoes(self):
        a=self.criar([dict(soma='10+20',largura=2),dict(lados=[dict(nome='A-B',comprimento=5)],largura='2,2',repeticoes=2)])
        mc,r0,r=self.folha(a);row=r0+PM.MEMORIAL
        self.assertEqual(len(r['folhas'][0]['linhas']),2)
        self.assertEqual((mc[f'T{row+1}'].value,mc[f'U{row+1}'].value,mc[f'K{row+1}'].value),(5,2.2,2))
        self.assertEqual(mc[f'W{row+1}'].value,f'=T{row+1}*U{row+1}*K{row+1}')
        self.assertEqual(mc[f'K{row-1}'].value,'VEZES')
        self.assertAlmostEqual(sum(l['quantidade'] for l in r['folhas'][0]['linhas']),82)

    def test_volume_i_vezes_j_em_t(self):
        a=self.criar([dict(soma='10',largura='2',profundidade='0,15')],'M3')
        mc,r0,r=self.folha(a);row=r0+PM.MEMORIAL
        self.assertEqual((mc[f'I{row}'].value,mc[f'J{row}'].value,mc[f'U{row}'].value),(10,2,.15))
        self.assertEqual(mc[f'T{row}'].value,f'=I{row}*J{row}')
        self.assertEqual(mc[f'T{row-1}'].value,'ÁREA (M²)')

    def test_medicao_parcial_conserva_medidas_e_desconta_parcela(self):
        a=self.criar([dict(soma='80+50+40+20+45',largura=2)])
        # Mesmo caso do rateio por saldo contratual, aplicado ao lançamento para isolar a MC.
        self.c.execute("UPDATE medicao_lancamentos SET quantidade=300 WHERE alvo_tipo='APROPRIACAO' AND alvo_id=?",(str(a['id']),))
        mc,r0,r=self.folha(a);row=r0+PM.MEMORIAL
        self.assertEqual((mc[f'T{row}'].value,mc[f'U{row}'].value),(235,2))
        self.assertIn('PARCELA FORA DESTA MEDIÇÃO',mc[f'N{row+1}'].value)
        self.assertEqual(mc[f'U{row+1}'].value,-170)
        self.assertEqual(sum(l['quantidade'] for l in r['folhas'][0]['linhas']),300)

    def test_arredondamento_dimensional_explicito_concilia_total(self):
        a=self.criar([dict(soma='0,00007',largura=2)])
        linhas=PM._linhas_memorial(self.c,self.mid,a['item'],a['unidade'])
        self.assertAlmostEqual(sum(l['quantidade'] for l in linhas),a['quantidade'],places=12)
        self.assertIn('ARREDONDAMENTO',linhas[-1]['ref'])

    def test_legado_sem_medidas_nao_vira_altura_ficticia(self):
        a=self.criar([dict(soma='10',largura=2)])
        self.c.execute('UPDATE apropriacoes SET calculo_json=NULL WHERE id=?',(a['id'],))
        mc,r0,_=self.folha(a);row=r0+PM.MEMORIAL
        self.assertIsNone(mc[f'T{row}'].value);self.assertIsNone(mc[f'U{row}'].value)
        self.assertEqual(mc[f'W{row}'].value,20)
        self.assertIn('SEM DIMENSÕES',mc[f'N{row}'].value)


class TestAtalhoChuva(BaseReal):
    def test_todas_equipes_checkin_distintas_inclui_devolvido(self):
        for eq,fechado in [('Zona01',0),('Zona03',1),('Zona03',0)]:
            self.c.execute('INSERT INTO checkins(data,equipe_id,encerrado) VALUES (?,?,?)',('2026-10-20',eq,fechado))
        corpo=dict(tipo='IMPEDIMENTO',categoria='CHUVA',data='2026-10-20',todas_equipes=True,turno='DIA_TODO',clima_condicao='PARALISADO_CHUVA')
        r=self.ok(self.cli('sup1').post('/api/ocorrencia',corpo))
        self.assertEqual(r['equipes'],['Zona01','Zona03']);self.assertEqual(len(r['ids']),2)
        self.assertEqual(self.cli('enc3').post('/api/ocorrencia',corpo)[0],403)
        self.assertEqual(self.cli('rh1').post('/api/ocorrencia',corpo)[0],403)
        for eq in r['equipes']:self.assertEqual(set(S.clima_no_dia(self.c,'2026-10-20',eq).values()),{'PARALISADO_CHUVA'})

    def test_todas_sem_checkin_e_turno_invalido_nao_gravam_parcial(self):
        corpo=dict(tipo='IMPEDIMENTO',categoria='CHUVA',data='2026-10-20',todas_equipes=True,turno='NOITE',clima_condicao='PARALISADO_CHUVA')
        self.recusa(self.cli('eng1').post('/api/ocorrencia',corpo),422,'check-in')
        for eq in ('Zona01','Zona03'):self.c.execute('INSERT INTO checkins(data,equipe_id) VALUES (?,?)',('2026-10-20',eq))
        self.recusa(self.cli('eng1').post('/api/ocorrencia',corpo),422,'manhã')
        self.assertEqual(self.n('ocorrencia_chuvas'),0)


class TestWordRevisado(BasePacote):
    def gerar(self):
        self.executar(TRS[0]);self.executar(TRS[1])
        S.registrar_soldas(self.c,'2026-10-10','Zona01','TRECHO',TRS[0],'TOPO',2,'Soldador sintético','eng1')
        nome,dados,d=RM.gerar_docx(self.c,self.mid,dir_fotos=self.fotos)
        return nome,dados,d

    def test_ooxml_namespaces_ordem_datas_estilos_cabecalho(self):
        nome,b,d=self.gerar();z=zipfile.ZipFile(io.BytesIO(b));ns=DS.NS
        for f in z.namelist():
            if f.endswith(('.xml','.rels')):
                self.assertNotIn(b'ns0:',z.read(f),f);ET.fromstring(z.read(f))
        self.assertIn(b'<Types xmlns=',z.read('[Content_Types].xml'))
        self.assertIn(b'<Relationships xmlns=',z.read('_rels/.rels'))
        for f in ('word/document.xml','word/header1.xml','word/footer1.xml','word/styles.xml'):
            raiz=ET.fromstring(z.read(f))
            for no in raiz.iter():
                tipo=no.tag.rsplit('}',1)[-1]
                if tipo in DS.ORDEM:
                    ordem=DS.ORDEM[tipo].split();pos=[ordem.index(c.tag.rsplit('}',1)[-1]) for c in no if c.tag.rsplit('}',1)[-1] in ordem]
                    self.assertEqual(pos,sorted(pos),(f,tipo))
        text=' '.join(e.text or '' for f in ('word/document.xml','word/header1.xml','word/header2.xml') for e in ET.fromstring(z.read(f)).iter('{'+ns['w']+'}t'))
        self.assertNotRegex(text,r'\b\d{4}-\d{2}-\d{2}\b')
        for esperado in ('Contrato número','Número do relatório','Período de execução','01/10/26 a 15/10/26','Relatório mensal da obra Morro da Cruz','01/10/2026'):
            self.assertIn(esperado,text)
        self.assertIn(b'Heading3',z.read('word/styles.xml'));self.assertIn(b'TOC ',z.read('word/document.xml'))
        self.assertIn(b'PAGEREF',z.read('word/document.xml'))
        self.assertEqual(d['totais']['total'],RM.dados(self.c,self.mid)['totais']['total'])

    def test_semana_croqui_estacas_somente_checklists_registrados(self):
        _,b,d=self.gerar();ns=DS.NS;root=ET.fromstring(zipfile.ZipFile(io.BytesIO(b)).read('word/document.xml'))
        text=' '.join(e.text or '' for e in root.iter('{'+ns['w']+'}t'))
        self.assertIn('ZONA 01 – PB01 – REDE PEAD DN 63 MM',text)
        self.assertIn('Croqui de Locação – PRANCHA PB01',text)
        self.assertIn('EST. 0+00,00 ATÉ EST.',text)
        self.assertIn('✓',text);self.assertIn('SOLDA TERMOFUSÃO (TOPO)',text)
        self.assertNotIn('SOLDA POR ELETROFUSÃO',text)
        self.assertIn('COMPATIBILIZAÇÃO DE TUBOS',text);self.assertIn('ESTOQUE VIRTUAL',text)
        self.assertIn('REDE EXEC. MÊS:',text)
        self.assertEqual(RW.estaca(122.85),'6+02,85')
        self.assertEqual(RW.estaca(19.999),'1+00,00')
        for nome in ('Imagem','Figura','Tabela','Gráfico'):
            labels=[]
            for p in root.findall('.//w:p',ns):
                t=''.join(p.itertext());m=re.match(r'^'+nome+r' (\d+)',t)
                if m:labels.append(int(m[1]))
            self.assertEqual(labels,list(range(1,len(labels)+1)),nome)

    @unittest.skipUnless(shutil.which('soffice') or shutil.which('libreoffice'),'LibreOffice ausente: conversão opcional não executada')
    def test_libreoffice_abre_word(self):
        _,b,_=self.gerar()
        with tempfile.TemporaryDirectory() as pasta:
            src=os.path.join(pasta,'rm.docx')
            with open(src,'wb') as f:f.write(b)
            r=subprocess.run([shutil.which('soffice') or shutil.which('libreoffice'),'--headless','--convert-to','pdf','--outdir',pasta,src],capture_output=True,timeout=120)
            self.assertTrue(os.path.getsize(os.path.join(pasta,'rm.pdf'))>1000,r.stderr.decode(errors='replace'))
