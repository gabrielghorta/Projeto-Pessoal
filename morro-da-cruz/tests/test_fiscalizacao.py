"""Aceite prévio, segregação, alterações, pacote e SMTP simulado, sobre o BM real."""
import io
import json
import os
import sqlite3
import unittest
import zipfile
from datetime import datetime
from unittest.mock import patch, MagicMock

from openpyxl import load_workbook
import acesso as A
import fiscalizacao as F
import fiscalizacao_email as FE
import importacao as I
import medicao as M
import pacote_medicao as PM
import relatorio_mensal as RM
import relogio as RL
import servicos as S
from test_acesso import SENHA
from test_apropriacao import BaseAp, CONTEINER
from test_pacote_medicao import BasePacote, TRS


class TestFiscalizacaoApropriacao(BaseAp):
    def test_memoria_dimensional_desconta_saldo_com_motivo_correto(self):
        mid = self.medicao()
        ap = self.apropriar("1.2_5.1.2", 470, parcelas=[{"comprimento": "80+50+40+20+45", "largura": "2"}])
        A.criar_usuario(self.c, "fiscalqa", "Fiscal fictício", "FISCALIZACAO", SENHA)
        linha = next(l for l in F.pronto_para_medir(self.c, mid)["prontas"] if l["item"] == ap["item"])
        with patch.dict(os.environ, {"MC_EMAIL_USUARIO": "", "MC_EMAIL_SENHA_APP": ""}):
            F.enviar(self.c, mid, [linha["id"]], "eng1")
            F.responder(self.c, [{"lancamento_id": linha["id"], "acao": "REDUZIR", "quantidade": 400,
                                 "motivo": "Área conferida em campo"}], "fiscalqa")
        memoria = PM._linhas_memorial(self.c, mid, ap["item"], ap["unidade"])
        self.assertEqual([l["quantidade"] for l in memoria], [470, -70])
        self.assertIn("80 + 50 + 40 + 20 + 45", memoria[0]["ref"])
        self.assertIn("aceite parcial", memoria[1]["ref"])

    def test_aceite_parcial_apropriacao_anexo_xlsx_e_word(self):
        mid = self.medicao()
        ap = self.apropriar(CONTEINER, 2)
        A.criar_usuario(self.c, "fiscalqa", "Fiscal fictício", "FISCALIZACAO", SENHA)
        with patch.dict(os.environ, {"MC_EMAIL_USUARIO": "", "MC_EMAIL_SENHA_APP": ""}):
            linha = next(l for l in F.pronto_para_medir(self.c, mid)["prontas"]
                         if l["alvo_tipo"] == "APROPRIACAO")
            self.assertEqual(linha["evidencias"]["justificativa_tecnica"], ap["justificativa"])
            F.enviar(self.c, mid, [linha["id"]], "eng1")
            F.responder(self.c, [{"lancamento_id": linha["id"], "acao": "REDUZIR", "quantidade": 1,
                                 "motivo": "Uma unidade conferida"}], "fiscalqa")
            F.reenviar(self.c, linha["id"], "eng1")
        _, xlsx, resumo = PM.gerar(self.c, mid, dir_fotos=self.fotos)
        wb = load_workbook(io.BytesIO(xlsx))
        self.assertIn("Fora do aceite", wb.sheetnames)
        memoria = [l for folha in resumo["folhas"] for l in folha["linhas"]]
        self.assertEqual(sum(l["quantidade"] for l in memoria), 1)
        fiscal = self.cli("fiscalqa")
        doc = linha["evidencias"]["documentos"][0]
        self.assertEqual(fiscal.get(doc["url"])[0], 200)
        self.assertEqual(fiscal.get(f'/api/fiscalizacao/arquivo?linha={linha["id"]}&doc=999999')[0], 403)
        _, word, rm = RM.gerar_docx(self.c, mid, dir_fotos=self.fotos)
        with zipfile.ZipFile(io.BytesIO(word)) as pacote:
            self.assertIn("word/document.xml", pacote.namelist())
        itens = [i for i in rm["itens"] if i["chave"] != PM.CHAVE_ADM]
        self.assertEqual([i["quantidade"] for i in itens], [1])


class TestSoldasNaMedicao(BasePacote):
    def test_tipo_diametro_e_verificacao_definem_o_item(self):
        casos = [
            (63, {"ELETROFUSAO": "2.2_5.8.47", "TOPO": None}),
            (125, {"ELETROFUSAO": None, "TOPO": None}),
            (160, {"ELETROFUSAO": None, "TOPO": "2.2_5.8.49"}),
        ]
        for de, itens in casos:
            trecho = self.c.execute(
                "SELECT ponto FROM trechos WHERE de_mm=? AND metodologia='VCA' AND vigente=1 ORDER BY id LIMIT 1", (de,)
            ).fetchone()[0]
            for tipo in itens:
                aprovada = S.registrar_soldas(self.c, "2026-10-10", "Zona01", "TRECHO", trecho, tipo, 3,
                                             "Soldador fictício", "enc1")
                recusada = S.registrar_soldas(self.c, "2026-10-10", "Zona01", "TRECHO", trecho, tipo, 7,
                                            "Soldador fictício", "enc1")
                S.registrar_soldas(self.c, "2026-10-10", "Zona01", "TRECHO", trecho, tipo, 11,
                                   "Soldador fictício", "enc1")
                S.verificar_soldas(self.c, aprovada, "sup1", "APROVADA")
                S.verificar_soldas(self.c, recusada, "sup1", "REPROVADA", "Fusão incompleta")
            self.executar(trecho)
            for tipo, item in itens.items():
                with self.subTest(diametro=de, tipo=tipo):
                    linha = self.c.execute(
                        "SELECT m.quantidade,m.status,b.item,m.restricao FROM medicao_lancamentos m "
                        "LEFT JOIN bm_itens b ON b.id=m.bm_item_id WHERE m.servico=? AND m.medicao_id=?",
                        (f"SOLDA {tipo} DE{de}", self.mid),
                    ).fetchone()
                    self.assertEqual(tuple(linha), (3, "PROPOSTO", item, None) if item
                                     else (3, "PENDENTE", None, "SOLDA_SEM_ITEM"))


class TestFiscalizacao(BasePacote):
    def setUp(self):
        super().setUp()
        self.env = patch.dict(os.environ, {"MC_EMAIL_USUARIO": "", "MC_EMAIL_SENHA_APP": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        A.criar_usuario(self.c, "fiscal1", "Fiscal fictício", "FISCALIZACAO", SENHA, email="fiscal@example.invalid")
        A.criar_usuario(self.c, "fiscal2", "Fiscal substituto fictício", "FISCALIZACAO", SENHA)
        A.alterar_usuario(self.c, "eng1", "adm", email="engenharia@example.invalid")
        for ponto in TRS:
            self.executar(ponto)
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
        RL.fixar(datetime(2026, 11, 16, 15, 30))
        try:
            self.reply(self.ids[2],"RECUSAR",motivo="Rever a memória")
        finally:
            RL.fixar()
        aceitas = F.quantidades_aceitas(self.c,self.mid)
        self.assertEqual(aceitas[self.ids[1]],q)
        self.assertNotIn(self.ids[2],aceitas)
        self.assertEqual(len(F.historico(self.c,self.mid)),6)
        h=F.historico(self.c,self.mid)[0]
        self.assertEqual((h["nome"],h["perfil"]),("Fiscal fictício","FISCALIZACAO"))
        self.assertEqual(h["em"][:16], "2026-11-16T12:30")
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

    def test_substituto_pode_reabrir_com_motivo_antes_fechar(self):
        self.send()
        self.reply(self.ids[0])
        with self.assertRaises(S.RegraViolada): F.reabrir(self.c,self.ids[0],"","fiscal1")
        F.reabrir(self.c,self.ids[0],"Nova conferência","fiscal2")
        self.assertEqual(F.historico(self.c,self.mid)[0]["por"],"fiscal2")
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
        self.assertEqual(F.quantidades_aceitas(self.c,self.mid),{self.ids[0]: round(q / 2, 6)})
        self.assertEqual(sum(l["situacao"]=="AGUARDANDO" for l in F.linhas(self.c,self.mid)),3)

    def test_reenvia_apenas_saldo_e_mantem_aceito_no_pacote(self):
        lid = self.ids[0]
        self.c.execute("UPDATE medicao_lancamentos SET quantidade=76.55 WHERE id=?", (lid,))
        self.send([lid])
        self.reply(lid, "REDUZIR", quantidade=70, motivo="Conferido em campo")
        F.reenviar(self.c, lid, "eng1", "Saldo corrigido")
        l = next(l for l in F.linhas(self.c, self.mid) if l["id"] == lid)
        self.assertEqual((l["quantidade_lote"], l["quantidade_aceita"], l["quantidade_enviada"]), (6.55, 70, 76.55))
        self.assertEqual(F.efetivas(self.c, self.mid), {lid: 70})
        r = PM.resumo(self.c, self.mid)
        self.assertEqual([l["quantidade"] for f in r["folhas"] for l in f["linhas"]], [70])
        rm = RM.dados(self.c, self.mid)
        self.assertEqual([i["quantidade"] for i in rm["itens"] if i["chave"] != PM.CHAVE_ADM], [70])
        self.assertAlmostEqual(rm["totais"]["total"], r["totais"]["juntada"], places=2)
        erro = next(l for l in F.fora_do_aceite(self.c, self.mid) if l["id"] == lid)
        self.assertEqual(erro["quantidade_fora"], 6.55)
        self.reply(lid, "RECUSAR", motivo="Conferir saldo novamente")
        self.assertEqual(F.efetivas(self.c, self.mid), {lid: 70})
        F.reenviar(self.c, lid, "eng1", "Saldo confirmado")
        self.reply(lid)
        self.assertEqual(F.efetivas(self.c, self.mid), {lid: 76.55})
        F.reabrir(self.c, lid, "Rever só o último envio", "fiscal1")
        self.assertEqual(F.efetivas(self.c, self.mid), {lid: 70})

    def test_perfil_fiscal_http_le_mapa_e_lotes_sem_acesso_interno(self):
        fiscal = self.cli("fiscal1")
        for rota in ("/api/estoque", "/api/compras", "/api/equipes", "/api/usuarios", "/api/diario",
                     "/api/medicoes", "/api/fiscalizacao/pronto", "/api/assistente", "/api/previsto"):
            self.assertEqual(fiscal.get(rota)[0], 403, rota)
        for rota in ("/api/drive/processar", "/api/assistente/rascunho", "/api/fiscalizacao/enviar", "/api/ok-fiscal"):
            self.assertEqual(fiscal.post(rota,{})[0],403,rota)
        self.assertEqual(self.ok(fiscal.get("/api/fiscalizacao/linhas")), [])
        self.assertEqual(self.ok(fiscal.get("/api/fiscalizacao/resumo?contador=1")), {"contador": 0})
        self.assertEqual(fiscal.get("/api/mapa/geral")[0], 200)
        self.send([self.ids[0]])
        self.assertEqual([l["id"] for l in self.ok(fiscal.get("/api/fiscalizacao/linhas"))], [self.ids[0]])
        self.assertEqual(self.ok(fiscal.get("/api/fiscalizacao/resumo?contador=1")), {"contador": 1})

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

    @patch.dict(os.environ, {"MC_EMAIL_USUARIO": "obra@example.invalid", "MC_EMAIL_SENHA_APP": "segredo-ficticio",
                             "MC_EMAIL_NOME": "Obra Morro da Cruz"})
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
                self.assertEqual(str(chamadas[0].args[0]["From"]), "Obra Morro da Cruz <obra@example.invalid>")
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

    def test_migracao_v27_preserva_lancamentos_usuarios_sem_aceite(self):
        antes=self.c.execute("SELECT COUNT(*) FROM medicao_lancamentos").fetchone()[0]
        self.c.execute("ALTER TABLE usuarios DROP COLUMN email")
        self.c.execute("DELETE FROM schema_versao WHERE versao=28")
        self.c.execute("INSERT OR IGNORE INTO schema_versao VALUES (27,'2026-11-15','versão anterior')")
        I.preparar_v28(self.c)
        S.aplicar_esquema(self.c)
        self.assertEqual(S.versao_banco(self.c),28)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM medicao_lancamentos").fetchone()[0],antes)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM fiscalizacao_linhas").fetchone()[0],0)
        self.assertIsNone(A._usuario(self.c,"fiscal1")["email"])
