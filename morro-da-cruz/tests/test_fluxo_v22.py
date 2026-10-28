"""Regras aprovadas em 27/10: solicitações, entrega antes da identificação e sugestões do apontamento."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import compras as C
import importacao as I
import recebimento as RC
import servicos as S
import solicitacoes as SOL
from test_compras import BaseCompras, MAT, D, D2
from test_acesso import BaseHTTP, TR
from fotos_teste import jpeg


class TestEntregaAntesDaIdentificacao(BaseCompras):
    def test_no_terminal_da_062_entra_sozinho_mas_juncao_nao(self):
        import dados_obra as DO
        import topologia as TP
        TP._CACHE.clear()
        r = DO.selecao(self.c, ['Zona01_PB01_Rede_TR002'])
        self.assertEqual([(n['nome'], n['automatico']) for n in r['nos']], [('Zona01_PB01_Rede_DF-33', True)])
        self.assertNotIn('Zona01_PB01_Rede_NÓ2.7', [n['nome'] for n in r['nos']])
        self.c.execute("UPDATE atividades SET vigente=0 WHERE nomenclatura='Zona01_PB01_Rede_DF-33'")
        self.assertEqual(DO.selecao(self.c, ['Zona01_PB01_Rede_TR002'])['nos'], [])

    def test_mista_entrega_agora_identifica_depois_sem_aprovacao_da_nota(self):
        nf = self.importar(18734, [(MAT, 'Peça conhecida', 'UN', 4, 12), ('X9', 'Peça desconhecida', 'CX', 2, 10)])
        l1, l2 = [r[0] for r in self.linhas(nf)]
        r = C.receber_nota(self.c, nf, 'almox1', D2)
        self.assertEqual((self.saldo(), r['aguardando_identificacao'], r['encerrada']), ((4, 0), 2, False))
        self.assertEqual(self.q('SELECT COUNT(*) FROM pedidos_compra'), [(0,)])
        self.assertEqual(self.q('SELECT aprovada_por,aprovada_em FROM notas_fiscais'), [(None, None)])
        self.assertEqual(self.q('SELECT linha_id FROM nf_confirmacoes WHERE pendente=1'), [(l2,)])
        with self.assertRaises(S.RegraViolada):
            C.receber_nota(self.c, nf, 'almox1', D2)
        C.confirmar_linhas(self.c, nf, [{'linha_id': l2, 'material_id': MAT, 'fator': 10}], 'eng1')
        self.assertEqual(self.saldo(), (24, 0))
        self.assertEqual(self.q('SELECT status FROM notas_fiscais'), [('ENCERRADA',)])
        self.assertEqual(self.q('SELECT recebido_por FROM recebimentos'), [('almox1',)])
        self.assertEqual(self.q('SELECT confirmada_por FROM nf_confirmacoes'), [('eng1',)])
        with self.assertRaises(S.RegraViolada):
            C.confirmar_linhas(self.c, nf, [{'linha_id': l2, 'material_id': MAT, 'fator': 10}], 'eng2')
        self.assertEqual(self.saldo(), (24, 0))

    def test_corrigir_reconhecida_exige_engenharia_mesmo_depois_da_entrega(self):
        nf = self.importar(8001, [(MAT, 'Peça', 'UN', 3, 12)])
        lid = self.linhas(nf)[0][0]
        RC.corrigir(self.c, nf, lid, 'almox1')
        self.assertIsNone(C.sugerir_materiais(self.c, nf)[0]['material_id'])
        C.receber_nota(self.c, nf, 'almox1', D2)
        self.assertEqual(self.saldo(), (0, 0))
        C.confirmar_linhas(self.c, nf, [{'linha_id': lid, 'material_id': MAT}], 'eng1')
        self.assertEqual(self.saldo(), (3, 0))

    def test_desconhecida_parcial_duas_entregas_e_recusa(self):
        nf = self.importar(8002, [('X9', 'Peça desconhecida', 'CX', 10, 10)])
        lid = self.linhas(nf)[0][0]
        C.receber_nota(self.c, nf, 'almox1', D2, problema={'observacao': 'uma avariada, faltam seis',
            'linhas': {str(lid): {'chegou': 4, 'avariado': 1}}})
        self.assertEqual((self.saldo(), RC.linhas(self.c, nf)[0]['entregue']), ((0, 0), 4))
        C.confirmar_linhas(self.c, nf, [{'linha_id': lid, 'material_id': MAT, 'fator': 2}], 'eng1')
        self.assertEqual(self.saldo(), (6, 0))
        C.receber_nota(self.c, nf, 'almox2', D2)
        self.assertEqual((self.saldo(), RC.linhas(self.c, nf)[0]['entregue']), ((18, 0), 10))
        self.assertEqual(self.q('SELECT status FROM notas_fiscais'), [('ENCERRADA',)])

    def test_identificada_como_servico_apos_entrega_nao_vira_estoque(self):
        nf = self.importar(8003, [('X9', 'Descrição desconhecida', 'UN', 1, 10)])
        lid = self.linhas(nf)[0][0]
        C.receber_nota(self.c, nf, 'almox1', D2)
        C.confirmar_linhas(self.c, nf, [{'linha_id': lid, 'fora_do_estoque': True}], 'eng1')
        self.assertEqual(self.q('SELECT status FROM notas_fiscais'), [('ENCERRADA',)])
        self.assertEqual(self.q('SELECT COUNT(*) FROM movimentos'), [(0,)])

    def test_migracao_libera_sem_fingir_aprovacao_sem_duplicar(self):
        nf = self.importar(18734, [(MAT, 'Peça', 'UN', 4, 12)])
        lid = self.linhas(nf)[0][0]
        C.conferir_nf(self.c, nf, None, [{'linha_id': lid, 'material_id': MAT}], 'almox1')
        ni = self.q('SELECT id FROM nf_itens')[0][0]
        rid = C.receber(self.c, nf, D2, [{'nf_item_id': ni, 'quantidade': 4}], 'almox1')
        C.inspecionar_entrega(self.c, rid, [], None, 'almox1', D2)
        antes = self.q('SELECT * FROM movimentos')
        self.c.execute('DELETE FROM schema_versao WHERE versao=22')
        self.c.execute("INSERT OR IGNORE INTO schema_versao VALUES (21,'antes','v21')")
        with S.transacao(self.c):
            I.preparar_v22(self.c)
        with S.transacao(self.c):
            I.preparar_v22(self.c)
        self.assertEqual(self.q('SELECT nf_id,material_id,quantidade FROM nf_liberadas_v22'), [(nf, MAT, 4)])
        self.assertEqual(self.q('SELECT aprovada_por,aprovada_em FROM notas_fiscais'), [(None, None)])
        self.assertEqual((self.saldo(), S.versao_banco(self.c)), ((4, 0), 22))
        self.assertEqual(self.q('SELECT * FROM movimentos'), antes)
        self.assertEqual(self.q('PRAGMA foreign_key_check'), [])


class TestSolicitacoesHTTP(BaseHTTP):
    usuarios = BaseHTTP.usuarios + (('sup', 'SUPERVISOR', None),)

    def test_perfis_pedem_sem_ver_notas_e_somente_engenharia_decide(self):
        for login in ('almox1', 'enc1', 'sup', 'eng1', 'adm'):
            cl = self.cliente(login)
            st, r = cl.post('/api/solicitacao', {'frente_id': 'Zona01', 'itens': [{'material_id': MAT, 'quantidade': 2}]})
            self.assertEqual(st, 200, r)
            self.assertEqual(cl.get('/api/solicitacoes')[0], 200)
        for login in ('enc1', 'sup'):
            for rota in ('/api/compras', '/api/almox/notas', '/api/nfs'):
                self.assertEqual(self.cliente(login).get(rota)[0], 403, (login, rota))
        self.assertEqual(self.cliente('eng1').post('/api/solicitacao/decidir', {'solicitacao_id': 4, 'aprovar': True})[0], 422)
        self.assertEqual(self.cliente('almox1').post('/api/solicitacao/decidir', {'solicitacao_id': 1, 'aprovar': True})[0], 403)
        self.assertEqual(self.cliente('eng2').post('/api/solicitacao/decidir', {'solicitacao_id': 1, 'aprovar': True})[0], 200)
        self.assertEqual([x['id'] for x in self.cliente('enc1').get('/api/solicitacoes')[1]['solicitacoes']], [2])

    def test_nao_achei_foto_e_texto_identificacao_recusa_e_chegou(self):
        almox, eng = self.cliente('almox1'), self.cliente('eng1')
        st, s = almox.post('/api/solicitacao', {'frente_id': 'Zona01', 'itens': [{'descricao': 'A peça da foto', 'foto_b64': jpeg(), 'quantidade': 2}]})
        self.assertEqual(st, 200, s)
        aid = self.q('SELECT id FROM solicitacao_avulsos')[0][0]
        self.assertEqual(almox.get(f'/api/solicitacao/foto?id={aid}')[0], 200)
        self.assertEqual(self.cliente('enc1').get(f'/api/solicitacao/foto?id={aid}')[0], 422)
        corpo = {'solicitacao_id': s['id'], 'aprovar': True}
        self.assertEqual(eng.post('/api/solicitacao/decidir', corpo)[0], 422)
        self.assertEqual(eng.post('/api/solicitacao/decidir', {**corpo, 'avulsos': [{'id': aid, 'material_id': MAT}]})[0], 200)
        import nfe_teste as NT
        nf = C.importar_nfe_xml(self.c, NT.b64(NT.xml(8004, [(MAT, 'Peça', 'UN', 2, 10)])), 'n.xml', 'almox1', cadastrar=True)['nf_id']
        self.assertEqual(eng.post('/api/solicitacao/vincular', {'nf_id': nf, 'solicitacao_id': s['id']})[0], 200)
        C.receber_nota(self.c, nf, 'almox1', D2)
        self.assertEqual(almox.get('/api/solicitacoes')[1]['solicitacoes'][0]['situacao'], 'CHEGOU')
        st, s2 = almox.post('/api/solicitacao', {'frente_id': 'Zona01', 'itens': [{'descricao': 'Outra peça', 'quantidade': 1}]})
        self.assertEqual(st, 200, s2)
        self.assertEqual(eng.post('/api/solicitacao/decidir', {'solicitacao_id': s2['id'], 'aprovar': False})[0], 422)
        self.assertEqual(eng.post('/api/solicitacao/decidir', {'solicitacao_id': s2['id'], 'aprovar': False, 'motivo': 'Já tem na obra'})[0], 200)

    def test_rotas_antigas_removidas_e_confirmacao_restrita(self):
        import server
        for rota in ('/api/pedido', '/api/pedido/cancelar', '/api/nf/aprovar'):
            self.assertNotIn(rota, server.POST)
        self.assertEqual(self.cliente('almox1').post('/api/nf/confirmar-linhas', {'nf_id': 1, 'linhas': []})[0], 403)


class TestAlvosDoDia(BaseHTTP):
    def ck(self, equipe='Zona01', data=D, alvo=TR):
        return S.checkin(self.c, data, equipe, 'TRECHO', alvo)

    def lista(self, equipe='Zona01', data=D):
        st, r = self.cliente('eng1').get(f'/api/campo/alvos-do-dia?equipe_id={equipe}&data={data}')
        self.assertEqual(st, 200, r)
        return r

    def test_equipe_data_e_checkin_devolvido(self):
        ck = self.ck()
        r = self.lista()
        self.assertEqual([x['nome'] for x in r['alvos']], [TR])
        self.assertFalse(r['alvos'][0]['ja_lancado_hoje'])
        S.checkout(self.c, ck, [])
        self.assertEqual(self.lista()['alvos'], r['alvos'])
        self.assertEqual(self.lista(data=D2)['alvos'], [])
        self.assertEqual(self.lista(equipe='Zona02')['alvos'], [])
        self.assertEqual(self.lista(equipe='Zona02')['checkins'], 0)

    def test_dois_checkins_unem_sem_repetir_e_marca_execucao(self):
        ck = self.ck()
        S.checkout(self.c, ck, [])
        ck2 = self.ck(alvo='Zona01_PB01_Rede_TR002')
        aid = S.alvo(self.c, 'TRECHO', TR)['id']
        self.c.execute("INSERT INTO checkin_alvos VALUES (?, 'TRECHO', ?, 'CHECKIN')", (ck2, aid))
        for turno in ('MANHA', 'TARDE'):
            S.registrar_clima(self.c, D, 'Zona01', turno, 'SOL')
        S.apontar(self.c, D, 'Zona01', 'TRECHO', aid, intervalos_novos=[{'etapa': 'ASSENTADO', 'ini_m': 0, 'fim_m': 1}])
        r = self.lista()
        self.assertEqual((r['checkins'], len(r['alvos'])), (2, 2))
        self.assertEqual([x['ja_lancado_hoje'] for x in r['alvos']], [True, False])

    def test_permissao_e_validacao(self):
        self.assertEqual(self.cliente('enc1').get(f'/api/campo/alvos-do-dia?equipe_id=Zona01&data={D}')[0], 403)
        self.assertEqual(self.cliente('eng1').get('/api/campo/alvos-do-dia?equipe_id=Zona01&data=invalida')[0], 422)


class TestMapaNoNavegador(unittest.TestCase):
    def test_selecao_por_zona_e_troca_de_equipe(self):
        import re
        import shutil
        import subprocess
        from pathlib import Path
        node = shutil.which('node')
        if not node:
            self.skipTest('Node não disponível')
        js = Path(AQUI, '..', 'web', 'planejamento.js').read_text(encoding='utf-8')
        funcs = '\n'.join(re.search(r'function ' + n + r'\(.*?\n\}', js, re.S).group(0)
                          for n in ('escolherTrecho', 'alternarNo', 'equipePadrao', 'cliquePln'))
        funcs += '\n' + re.search(r'const equipeDoTrecho = .*?;', js).group(0)
        roteiro = """
const assert = require('node:assert/strict');
const PLN = {sel:[],nos:[],resp:null,zona:null,noIdx:new Map([['N1',1],['N2',2]])};
const RESUMO = {equipes:[{id:'Zona01'},{id:'Zona08'}]};
const GERAL = {trechos:[{n:'Zona01_PB01_Rede_TR001',z:'01'}, {n:'Zona08_PB20_Rede_TR046',z:'08'}]};
const indexar = () => ({trecho:new Map(GERAL.trechos.map(t=>[t.n,t]))});
const atualizarSelecao = () => {}, fecharPopPln = () => {}, toast = () => {};
const membrosDe = n => [n], $ = () => ({classList:{contains:()=>false}});
const focarZonaPln = z => { PLN.zona=z; };
""" + funcs + """
const alvo = {closest:()=>null};
cliquePln(alvo, {ctrlKey:true}, 0);
cliquePln(alvo, {ctrlKey:true}, 1);
assert.deepEqual(PLN.sel,[GERAL.trechos[1].n]); // obra inteira substitui até com Ctrl
assert.equal(equipePadrao(),'Zona08');
PLN.equipe='Zona01'; PLN.equipeFixa=true;
escolherTrecho(GERAL.trechos[0].n,false);
assert.equal(PLN.equipeFixa,false);
PLN.zona='Zona08'; PLN.sel=[];
cliquePln(alvo, {}, 0); cliquePln(alvo, {}, 1);
assert.equal(PLN.sel.length,2);
cliquePln(alvo, {}, 0); assert.deepEqual(PLN.sel,[GERAL.trechos[1].n]);
alternarNo('N1'); alternarNo('N2'); assert.equal(PLN.nos.length,2);
PLN.zona=null; alternarNo('N1'); assert.deepEqual(PLN.nos,['N1']); assert.deepEqual(PLN.sel,[]);
PLN.sel=[GERAL.trechos[1].n]; PLN.nos=[]; assert.equal(equipePadrao(),'Zona08');
"""
        r = subprocess.run([node, '-e', roteiro], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
