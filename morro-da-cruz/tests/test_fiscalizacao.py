"""Aceite prévio, segregação, alterações, pacote e SMTP simulado, sobre o BM real."""
import io
import json
import os
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from openpyxl import load_workbook
import acesso as A
import fiscalizacao as F
import fiscalizacao_email as FE
import importacao as I
import medicao as M
import pacote_medicao as PM
import servicos as S
from test_acesso import SENHA
from test_pacote_medicao import BasePacote, TRS


class TestFiscalizacao(BasePacote):
    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {"MC_EMAIL_USUARIO": "", "MC_EMAIL_SENHA_APP": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        A.criar_usuario(self.c, "fiscal1", "Fiscal fictício", "FISCALIZACAO", SENHA, email="fiscal@example.invalid")
        A.criar_usuario(self.c, "fiscal2", "Fiscal substituto fictício", "FISCALIZACAO", SENHA)
        A.alterar_usuario(self.c, "eng1", "adm", email="engenharia@example.invalid")
        self.ids = [l["id"] for l in F.pronto_para_medir(self.c, self.mid)["prontas"][:3]]
        self.assertEqual(len(self.ids), 3)

    def send(self, ids=None):
        return F.enviar(self.c, self.mid, ids or self.ids, "eng1", "Conferência do mês")

    def reply(self, lid, acao="ACEITAR", **kw):
        return F.responder(self.c, [dict(lancamento_id=lid, acao=acao, **kw)], "fiscal1")

    def test_pronto_ordem_valor_bdi_k_sem_adm_pendente(self):
        r = F.pronto_para_medir(self.c, self.mid)
        vals = [l["valor"] for l in r["prontas"]]
        self.assertEqual(vals, sorted(vals, reverse=True))
        self.assertTrue(all(l["status"] == "PROPOSTO" and l["item"] != PM.CHAVE_ADM for l in r["prontas"]))
        self.assertTrue(all("evidencias" in l and l["alvo_nome"] for l in r["prontas"]))
        self.assertEqual({l["id"] for l in r["pendentes"]}, {l[0] for l in self.c.execute(
            "SELECT id FROM medicao_lancamentos WHERE medicao_id=? AND status='PENDENTE'", (self.mid,))})

    def test_perfis_separados_e_sem_usuarios_reais_automaticos(self):
        f = A.publico(A._usuario(self.c, "fiscal1"))
        self.assertEqual(set(f["telas"]), {"iluminado", "fiscalizacao"})
        with self.assertRaises(A.AcessoNegado): F.enviar(self.c, self.mid, self.ids, "fiscal1")
        self.send()
        with self.assertRaises(A.AcessoNegado): F.responder(self.c, [{"lancamento_id": self.ids[0], "acao": "ACEITAR"}], "eng1")
        with self.assertRaises(A.AcessoNegado): F.reenviar(self.c, self.ids[0], "fiscal1")

    def test_envio_recusa_vazio_repetido_pendente_adm_e_fechada(self):
        pend = self.c.execute("SELECT id FROM medicao_lancamentos WHERE status='PENDENTE' AND medicao_id=? LIMIT 1", (self.mid,)).fetchone()[0]
        adm = S._lancar(self.c,self.mid,5,"ADM direta",S._bm_item(self.c,PM.CHAVE_ADM),"UN",0.01)
        for ids in ([], [self.ids[0], self.ids[0]], [True], [pend], [adm], [999999], [self.ids[0], pend]):
            with self.subTest(ids=ids), self.assertRaises(S.RegraViolada): F.enviar(self.c,self.mid,ids,"eng1")
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM fiscalizacao_envios").fetchone()[0],0)
        self.send()
        with self.assertRaises(S.RegraViolada): self.send()
        self.c.execute("UPDATE medicoes SET status='FECHADA' WHERE id=?",(self.mid,))
        with self.assertRaises(S.RegraViolada): self.reply(self.ids[0])
        with self.assertRaises(S.RegraViolada): self.send()

    def test_aceitar_reduzir_recusar_e_eventos(self):
        self.send()
        qtd = F.linhas(self.c,self.mid)[0]["quantidade"]
        l = next(l for l in F.linhas(self.c,self.mid) if l["id"]==self.ids[1])
        q = l["quantidade_enviada"]/2
        self.reply(self.ids[0])
        self.reply(self.ids[1],"REDUZIR",quantidade=q,motivo="Conferido parcialmente")
        self.reply(self.ids[2],"RECUSAR",motivo="Rever a memória")
        aceitas = F.quantidades_aceitas(self.c,self.mid)
        self.assertEqual(aceitas[self.ids[1]],q)
        self.assertNotIn(self.ids[2],aceitas)
        self.assertEqual(len(F.historico(self.c,self.mid)),6)
        h=F.historico(self.c,self.mid)[0]
        self.assertEqual((h["nome"],h["perfil"]),("Fiscal fictício","FISCALIZACAO"))
        self.assertTrue(h["em"].endswith("-03:00"))
        p=F.painel(self.c,self.mid)
        self.assertEqual(p["totais"]["aceito"]["linhas"],2)
        self.assertEqual(p["totais"]["reduzido"]["linhas"],1)
        self.assertEqual(p["totais"]["recusado"]["linhas"],1)

    def test_reducao_invalida_motivos_lote_atomico(self):
        self.send()
        q=next(l["quantidade_enviada"] for l in F.linhas(self.c,self.mid) if l["id"]==self.ids[1])
        for acao,kw in [("REDUZIR",dict(quantidade=x,motivo="Rever")) for x in (0,-1,q,q+1,float("nan"),float("inf"),True)]+[
            ("REDUZIR",dict(quantidade=q/2)),("RECUSAR",{}),("INVALIDA",{})]:
            with self.subTest(acao=acao,kw=kw),self.assertRaises(S.RegraViolada):
                F.responder(self.c,[{"lancamento_id":self.ids[0],"acao":"ACEITAR"},dict(lancamento_id=self.ids[1],acao=acao,**kw)],"fiscal1")
            self.assertEqual(F.quantidades_aceitas(self.c,self.mid),{})
        with self.assertRaises(S.RegraViolada): F.responder(self.c,[],"fiscal1")

    def test_alteracao_invalida_aceite_reenvio_assinatura_nova(self):
        self.send()
        self.reply(self.ids[0])
        self.c.execute("UPDATE medicao_lancamentos SET quantidade=quantidade+1 WHERE id=?",(self.ids[0],))
        self.assertNotIn(self.ids[0],F.quantidades_aceitas(self.c,self.mid))
        self.assertEqual(next(l["situacao"] for l in F.linhas(self.c,self.mid) if l["id"]==self.ids[0]),"ALTERADA")
        with self.assertRaisesRegex(S.RegraViolada,"alterou"): self.reply(self.ids[0])
        F.reenviar(self.c,self.ids[0],"eng1","Conta corrigida")
        self.reply(self.ids[0])
        self.assertEqual(F.historico(self.c,self.mid)[1]["acao"],"REENVIADA")

    def test_preco_unidade_status_tambem_invalidam_envio(self):
        self.send()
        for campo,valor in (("unidade","KG"),("status","PENDENTE")):
            with S.transacao(self.c):
                antigo=self.c.execute(f"SELECT {campo} FROM medicao_lancamentos WHERE id=?",(self.ids[0],)).fetchone()[0]
                self.c.execute(f"UPDATE medicao_lancamentos SET {campo}=? WHERE id=?",(valor,self.ids[0]))
                with self.assertRaisesRegex(S.RegraViolada,"alterou"): self.reply(self.ids[0])
                self.c.execute(f"UPDATE medicao_lancamentos SET {campo}=? WHERE id=?",(antigo,self.ids[0]))
        bid=self.c.execute("SELECT bm_item_id FROM medicao_lancamentos WHERE id=?",(self.ids[0],)).fetchone()[0]
        self.c.execute("UPDATE bm_itens SET preco_unitario=preco_unitario+1 WHERE id=?",(bid,))
        with self.assertRaisesRegex(S.RegraViolada,"alterou"): self.reply(self.ids[0])

    def test_reabrir_propria_resposta_com_motivo_antes_fechar(self):
        self.send()
        self.reply(self.ids[0])
        with self.assertRaises(S.RegraViolada): F.reabrir(self.c,self.ids[0],"","fiscal1")
        with self.assertRaises(S.RegraViolada): F.reabrir(self.c,self.ids[0],"Rever","fiscal2")
        F.reabrir(self.c,self.ids[0],"Nova conferência","fiscal1")
        self.assertNotIn(self.ids[0],F.quantidades_aceitas(self.c,self.mid))
        self.reply(self.ids[0])
        self.c.execute("UPDATE medicoes SET status='FECHADA' WHERE id=?",(self.mid,))
        with self.assertRaises(S.RegraViolada): F.reabrir(self.c,self.ids[0],"Rever","fiscal1")

    def test_reenvio_reduzida_recusada_cancelada(self):
        self.send()
        q=next(l["quantidade_enviada"] for l in F.linhas(self.c,self.mid) if l["id"]==self.ids[0])
        self.reply(self.ids[0],"REDUZIR",quantidade=q/2,motivo="Menor")
        self.reply(self.ids[1],"RECUSAR",motivo="Rever")
        F.cancelar(self.c,self.ids[2],"Corrigir anexo","eng1")
        for lid in self.ids: F.reenviar(self.c,lid,"eng1","Corrigido")
        self.assertEqual(F.quantidades_aceitas(self.c,self.mid),{})
        self.assertEqual(sum(l["situacao"]=="AGUARDANDO" for l in F.linhas(self.c,self.mid)),3)

    def test_contador_por_papel_abertas(self):
        self.send()
        f=A.publico(A._usuario(self.c,"fiscal1")); e=A.publico(A._usuario(self.c,"eng1"))
        self.assertEqual((F.contador(self.c,f),F.contador(self.c,e)),(3,0))
        self.reply(self.ids[0],"RECUSAR",motivo="Rever")
        self.assertEqual((F.contador(self.c,f),F.contador(self.c,e)),(2,1))
        self.c.execute("UPDATE medicoes SET status='FECHADA' WHERE id=?",(self.mid,))
        self.assertEqual(F.contador(self.c,f),0)

    def test_sem_envio_preserva_pacote_e_assinatura(self):
        antes=PM.resumo(self.c,self.mid)
        self.assertIsNone(F.efetivas(self.c,self.mid))
        linhas=self.c.execute("SELECT id,gaveta,servico,alvo_tipo,alvo_id,bm_item_id,quantidade,status FROM medicao_lancamentos WHERE medicao_id=? ORDER BY id",(self.mid,)).fetchall()
        import hashlib
        self.assertEqual(S.assinatura_medicao(self.c,self.mid),hashlib.sha256(json.dumps([list(r) for r in linhas],default=str).encode()).hexdigest())
        self.assertEqual(antes["totais"],PM.resumo(self.c,self.mid)["totais"])

    def test_pacote_so_aceito_reducao_adm_e_fora_aceite(self):
        antes=PM.resumo(self.c,self.mid)
        self.send()
        self.reply(self.ids[0])
        l=next(l for l in F.linhas(self.c,self.mid) if l["id"]==self.ids[1]);q=l["quantidade_enviada"]/2
        self.reply(self.ids[1],"REDUZIR",quantidade=q,motivo="Parcial")
        r=PM.resumo(self.c,self.mid)
        self.assertLess(r["totais"]["juntada"],antes["totais"]["juntada"])
        self.assertLess(r["adm"]["valor"],antes["adm"]["valor"])
        memorial=[l for f in r["folhas"] for l in f["linhas"]]
        self.assertEqual({l["lancamento_id"] for l in memorial},set(self.ids[:2]))
        self.assertEqual(next(x["quantidade"] for x in memorial if x["lancamento_id"]==self.ids[1]),q)
        _,dados,_=PM.gerar(self.c,self.mid,dir_fotos=self.fotos)
        wb=load_workbook(io.BytesIO(dados))
        self.assertIn("Fora do aceite",wb.sheetnames)
        self.assertIn(self.ids[2],[row[0].value for row in wb["Fora do aceite"].iter_rows(min_row=2)])

    def test_aceite_muda_assinatura_conferencia_e_fechada_congela(self):
        antes=S.assinatura_medicao(self.c,self.mid)
        self.send(); self.reply(self.ids[0])
        self.assertNotEqual(antes,S.assinatura_medicao(self.c,self.mid))
        S.congelar_medicao(self.c,self.mid,"teste fictício")
        self.c.execute("UPDATE medicoes SET status='FECHADA' WHERE id=?",(self.mid,))
        p=F.painel(self.c,self.mid);q=F.quantidades_aceitas(self.c,self.mid)
        self.c.execute("UPDATE bm_itens SET preco_unitario=preco_unitario*2")
        self.c.execute("UPDATE parametros SET valor='0.99' WHERE chave='coef_k'")
        self.assertEqual(F.painel(self.c,self.mid),p)
        self.assertEqual(F.quantidades_aceitas(self.c,self.mid),q)

    def test_email_sem_config_nao_impede_acao(self):
        r=self.send()
        self.assertEqual(r["email_situacao"],"SEM_CONFIGURACAO")
        self.assertEqual(self.c.execute("SELECT email_situacao FROM fiscalizacao_envios").fetchone()[0],"SEM_CONFIGURACAO")

    @patch.dict(os.environ,{"MC_EMAIL_USUARIO":"obra@example.invalid","MC_EMAIL_SENHA_APP":"segredo-ficticio"})
    def _email(self,falha=False):
        with patch.object(FE.smtplib,"SMTP") as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value={}
            if falha: smtp.return_value.__enter__.return_value.login.side_effect=RuntimeError("segredo-ficticio")
            self.send();FE.processar(self.c)
            self.reply(self.ids[0]);FE.processar(self.c)
            linhas=[dict(r) for r in self.c.execute("SELECT * FROM fiscalizacao_emails")]
            self.assertNotIn("segredo-ficticio",json.dumps(linhas))
            self.assertEqual({r["situacao"] for r in linhas},{"FALHOU" if falha else "ENVIADO"})
            if not falha:
                chamadas=smtp.return_value.__enter__.return_value.send_message.call_args_list
                self.assertEqual(chamadas[0].kwargs["to_addrs"],["fiscal@example.invalid"])
                self.assertEqual(chamadas[1].kwargs["to_addrs"],["engenharia@example.invalid"])
                smtp.assert_called_with("smtp.gmail.com",587,timeout=10)

    def test_email_mock_destinatarios_corretos(self): self._email()
    def test_email_falha_nao_desfaz_resposta(self): self._email(True)

    def test_email_valida_limpa_e_nao_expoe_senha(self):
        for mail in ("x\r\nBcc: x@example.invalid","sem-arroba","a@b", "x "*200):
            with self.assertRaises(S.RegraViolada): A.alterar_usuario(self.c,"fiscal1","adm",email=mail)
        A.alterar_usuario(self.c,"fiscal1","adm",email="")
        self.assertIsNone(A.publico(A._usuario(self.c,"fiscal1"))["email"])
        self.assertNotIn("senha",A.publico(A._usuario(self.c,"fiscal1")))

    def test_migracao_v26_preserva_lancamentos_usuarios_sem_aceite(self):
        antes=self.c.execute("SELECT COUNT(*) FROM medicao_lancamentos").fetchone()[0]
        self.c.execute("ALTER TABLE usuarios DROP COLUMN email")
        self.c.execute("DELETE FROM schema_versao WHERE versao=27")
        I.preparar_v27(self.c)
        self.assertEqual(S.versao_banco(self.c),27)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM medicao_lancamentos").fetchone()[0],antes)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM fiscalizacao_linhas").fetchone()[0],0)
        self.assertIsNone(A._usuario(self.c,"fiscal1")["email"])
