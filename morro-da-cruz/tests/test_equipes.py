"""D-212: cadastro vazio, composição manual, permissões e histórico independente das zonas."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import equipes as E
import importacao as I
import servicos as S
from test_acesso import BaseHTTP
from test_importacao import Base


class Cadastro(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = S.conectar(os.path.join(self.tmp.name, 'obra.db'))

    def tearDown(self):
        self.c.close(); self.tmp.cleanup()

    def criar(self, empresa='ANKARA'):
        return E.criar(self.c,empresa,'','eng.teste')

    def test_cadastro_vazio_com_zonas_e_seis_equipes_criadas_a_mao(self):
        self.assertEqual(E.listar(self.c),[])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM frentes').fetchone()[0],13)
        ids=[self.criar(grupo) for grupo in ['ANKARA','ANKARA','E1','E1','E2','E2']]
        self.assertEqual(ids,['A1','A2','E1.1','E1.2','E2.1','E2.2'])
        self.assertEqual(self.criar('E1'),'E1.3')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM funcionarios').fetchone()[0],0)
        with self.assertRaises(S.RegraViolada): self.criar('Outra')

    def test_exige_designar_integrantes_antes_de_usar(self):
        equipe=self.criar()
        for f in [lambda:E.exigir(self.c,equipe),lambda:S.registrar_clima(self.c,'2026-10-15',equipe,'MANHA','SOL'),
                  lambda:S.checkin(self.c,'2026-10-15',equipe)]:
            with self.assertRaisesRegex(S.RegraViolada,'integrantes'):f()
        E.membro(self.c,equipe,'Integrante de teste','Encarregado')
        self.assertEqual(E.exigir(self.c,equipe)['id'],equipe)

    def test_codigo_nao_e_reaproveitado_e_integrante_invalido_e_recusado(self):
        self.c.execute("INSERT INTO equipes(id,nome,ativa) VALUES('A1','Referência antiga',0)")
        self.assertEqual(self.criar(),'A2')
        E.excluir(self.c,'A2','eng.teste')
        self.assertEqual(self.criar(),'A3')
        with self.assertRaises(S.RegraViolada):E.membro(self.c,'A3',funcionario_id='abc')

    def test_vincular_e_retirar_sem_duplicar_ou_transferir_silenciosamente(self):
        a,b=self.criar(),self.criar('E1')
        fid=E.membro(self.c,a,'Pessoa de teste','Encanador')
        self.assertEqual(E.membro(self.c,a,funcionario_id=fid),fid)
        with self.assertRaises(S.RegraViolada):E.membro(self.c,b,funcionario_id=fid)
        E.retirar_membro(self.c,a,fid)
        E.membro(self.c,b,funcionario_id=fid)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM funcionarios').fetchone()[0],1)
        self.assertEqual(E.recursos(self.c,b)['funcionarios'][0]['id'],fid)

    def test_presenca_da_equipe_e_troca_so_apos_devolucao(self):
        a,b=self.criar(),self.criar('E1')
        fa=E.membro(self.c,a,'Pessoa A','Encarregado');fb=E.membro(self.c,b,'Pessoa B','Encarregado')
        with self.assertRaisesRegex(S.RegraViolada,'não pertence'):S.checkin(self.c,'2026-10-15',a,funcionarios=[fb])
        cid=S.checkin(self.c,'2026-10-15',a,funcionarios=[fa],contingencia=S.R.CONTINGENCIAS[0])
        with self.assertRaisesRegex(S.RegraViolada,'check-in aberto'):E.retirar_membro(self.c,a,fa)
        E.excluir(self.c,a,'eng.teste')
        self.assertEqual([e['id'] for e in E.listar(self.c)],[b])
        self.assertEqual(self.c.execute('SELECT equipe_id FROM checkins WHERE id=?',(cid,)).fetchone()[0],a)
        with self.assertRaisesRegex(S.RegraViolada,'ativa'):E.exigir(self.c,a)
        import relatorio_mensal as RM
        self.assertIn(a,[e['id'] for e in RM._equipes(self.c,'2026-10-01','2026-10-31')])
        self.assertNotIn(a,[e['id'] for e in RM._equipes(self.c,'2026-11-01','2026-11-30')])

    def test_migracao_v23_mantem_historico_e_separa_as_zonas(self):
        db=os.path.join(self.tmp.name,'legado.db');c=sqlite3.connect(db,isolation_level=None);c.row_factory=sqlite3.Row
        schema=(Path(S.caminhos.RECURSOS)/'schema.sql').read_text(encoding='utf-8')
        for cmd in S.comandos_sql(schema):
            if cmd.startswith('CREATE TABLE IF NOT EXISTS frentes '):continue
            if cmd.startswith('CREATE TABLE IF NOT EXISTS equipes '):cmd='CREATE TABLE equipes(id TEXT PRIMARY KEY,nome TEXT NOT NULL,cor TEXT)'
            c.execute(cmd.replace('REFERENCES frentes','REFERENCES equipes'))
        c.execute("INSERT INTO schema_versao VALUES(23,'2026-10-01','legado')")
        c.execute("INSERT INTO equipes VALUES('Zona01','Equipe antiga',NULL)")
        c.execute("INSERT INTO funcionarios(id,nome,equipe_id) VALUES(1,'Integrante legado','Zona01')")
        c.execute("INSERT INTO trechos(id,ponto,frente_id,extensao_m,quantidades) VALUES('TR-T','Zona01_PB01_Rede_TR001','Zona01',10,'{}')")
        c.execute("INSERT INTO checkins(id,data,equipe_id,encerrado) VALUES(1,'2026-10-01','Zona01',1)")
        c.execute("INSERT INTO checkin_presencas VALUES(1,'FUNCIONARIO',1)")
        c.execute('PRAGMA foreign_keys=OFF')
        with S.transacao(c):I.preparar_v24(c)
        c.execute('PRAGMA foreign_keys=ON')
        self.assertEqual(E.listar(c),[])
        self.assertEqual(c.execute('SELECT frente_id,extensao_m FROM trechos').fetchone()[:],('Zona01',10.0))
        self.assertEqual(c.execute('SELECT equipe_id FROM checkins').fetchone()[0],'Zona01')
        self.assertEqual(c.execute('SELECT COUNT(*) FROM checkin_presencas').fetchone()[0],1)
        self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertIn('frentes',[r['table'] for r in c.execute('PRAGMA foreign_key_list(trechos)')])
        novo=E.criar(c,'ANKARA','Nova equipe','eng.teste')
        E.membro(c,novo,funcionario_id=1)
        self.assertEqual(c.execute('SELECT equipe_id FROM checkins').fetchone()[0],'Zona01')
        c.close()


class Reimportacao(Base):
    def test_importacao_nao_cria_equipes_nem_restaura_excluidas(self):
        I_rel=__import__('importar').aplicar(self.db,self.planilhas,cfg=self.cfg,dir_relatorios=self.rels)
        self.assertEqual(I_rel['status'],'CONCLUIDA')
        c=self.conectar();self.assertEqual(E.listar(c),[])
        eid=E.criar(c,'E2','','eng.teste');E.membro(c,eid,'Pessoa de teste','Encarregado');E.excluir(c,eid,'eng.teste')
        self.aplicar()
        self.assertEqual(E.listar(c),[])
        self.assertEqual(c.execute('SELECT COUNT(*) FROM trechos').fetchone()[0],3)


class EquipesHTTP(BaseHTTP):
    def test_conta_da_equipe_excluida_pode_ser_desativada(self):
        import acesso as A
        from test_acesso import SENHA
        eid=E.criar(self.c,'ANKARA','','eng1')
        A.criar_usuario(self.c,'enc.novo','Encarregado sintético','EQUIPE',SENHA,eid,'eng1')
        E.excluir(self.c,eid,'eng1')
        A.alterar_usuario(self.c,'enc.novo','eng1',ativo=False)
        self.assertEqual(self.c.execute("SELECT ativo FROM usuarios WHERE login='enc.novo'").fetchone()[0],0)
        with self.assertRaises(S.RegraViolada):A.alterar_usuario(self.c,'enc.novo','eng1',ativo=True)

    def test_zona_do_pedido_independe_da_sigla_da_equipe(self):
        import planejamento as P
        import solicitacoes as SOL
        eid=E.criar(self.c,'E1','','eng1');E.membro(self.c,eid,'Pessoa sintética','Encarregado')
        u={'login':'enc1','equipe_id':eid,'restrito_a_equipe':True}
        self.assertEqual(SOL.frentes_do_usuario(self.c,u),set())
        hoje=S.RL.hoje().isoformat()
        P.programar(self.c,hoje,eid,'TRECHO','Zona01_PB01_Rede_TR001','LOCACAO','eng1')
        self.assertEqual(SOL.frentes_do_usuario(self.c,u),{'Zona01'})
        with self.assertRaisesRegex(S.RegraViolada,'própria equipe'):
            SOL.abrir(self.c,{'frente_id':'Zona02'},u)

    def test_permissoes_cadastro_e_conteudo_do_resumo(self):
        enc=self.cliente('enc1');eng=self.cliente('eng1')
        self.assertEqual(enc.post('/api/equipes/criar',{'empresa':'ANKARA'})[0],403)
        st,r=eng.post('/api/equipes/criar',{'empresa':'ANKARA','nome':'Equipe de teste'})
        self.assertEqual(st,200);eid=r['id']
        self.assertEqual(eng.post('/api/funcionario',{'equipe_id':eid,'nome':'Integrante de teste','funcao':'Encarregado'})[0],200)
        self.assertEqual(eng.get('/api/equipes')[0],200)
        self.assertEqual(eng.post('/api/equipes/excluir',{'equipe_id':eid})[0],200)
        st,r=eng.get('/api/resumo');self.assertEqual(st,200)
        self.assertNotIn(eid,[x['id'] for x in r['equipes']])
        self.assertIn(eid,[x['id'] for x in r['equipes_historicas']])


from base_real import BaseReal as BaseNs


class EquipeNovaNaNS(BaseNs):
    LIBERAR_TUDO=True

    def test_ns_da_zona_nao_confunde_equipe_e_frente(self):
        from test_ns_dia import pdf_dia,grupo,CROQUI,CLIMA
        from base_real import b64
        eid=E.criar(self.c,'E1','','eng1');E.membro(self.c,eid,'Pessoa sintética','Encarregado')
        pdf=pdf_dia([grupo(['NÓ9.1','CH_VRP-15'],[295.98],obs=['ASSENTAMENTO',None])],numero='81234')
        r=self.ok(self.cli('eng1').post('/api/ns/dia',dict(equipe_id=eid,pdf_b64=b64(pdf),croqui_b64=CROQUI,
                 clima=CLIMA,pdf_nome='simulacao.pdf',croqui_nome='croqui.pdf')))
        self.assertEqual((r['equipe_id'],r['fila']),(eid,[]))
        nomes=[p[0] for p in self.c.execute('SELECT DISTINCT t.ponto FROM intervalos_execucao i JOIN trechos t ON t.id=i.trecho_id WHERE i.equipe_id=?',(eid,))]
        self.assertTrue(nomes and all(n.startswith('Zona03_') for n in nomes))


if __name__=='__main__':unittest.main()
