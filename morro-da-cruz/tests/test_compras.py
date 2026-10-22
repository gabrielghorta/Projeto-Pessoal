"""Módulo C — compras, NF-e, entregas e aceites parciais, quarentena, recusa, devolução, transferência entre equipes,
inventário e reservas vencidas. Planilhas sintéticas, bancos temporários; XML de NF-e de teste."""
import base64
import json
import os
import sqlite3
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import backup  # noqa: E402
import compras as C  # noqa: E402
import nfe  # noqa: E402
import nfe_teste as NT  # noqa: E402
import servicos as S  # noqa: E402
from fotos_teste import jpeg  # noqa: E402
from test_acesso import BaseHTTP  # noqa: E402
from test_importacao import Base  # noqa: E402

D, D2 = "2026-10-15", "2026-10-16"
MAT = "1.2_1.14.27"            # material Ankara em UN
TUBO = "1.1_1.14.77"           # material Ankara em M


class BaseCompras(Base):
    def setUp(self):
        super().setUp()
        self.aplicar()
        self.c = self.conectar()
        self.forn = C.cadastrar_fornecedor(self.c, NT.CNPJ_FORNECEDOR, "Fornecedor de Teste Ltda", "comprador")

    def pedido(self, qtd=100, mat=MAT, numero="PC-001"):
        sid = C.abrir_solicitacao(self.c, D, [{"material_id": mat, "quantidade": qtd}], "Frente Zona01", "eng1")
        C.decidir_solicitacao(self.c, sid, True, None, "eng2")
        return C.emitir_pedido(self.c, numero, D, self.forn, sid, [{"material_id": mat, "quantidade": qtd, "valor_unitario": 10}], "comprador")

    def importar(self, numero, itens):
        return C.importar_nfe_xml(self.c, NT.b64(NT.xml(numero, itens)), f"nfe{numero}.xml", "almox1")["nf_id"]

    def linhas(self, nf):
        return self.q("SELECT id, n_item FROM nf_linhas WHERE nf_id=? ORDER BY n_item", nf)

    def saldo(self, mat=MAT):
        return S.saldo_almox(self.c, mat)


class TestNfeXml(unittest.TestCase):
    def test_leitura_e_recusas(self):
        d = nfe.ler(NT.xml(7, [("A1", "Luva", "UN", 3, 2.5), ("F", "Frete", "SV", 1, 30)]))
        self.assertEqual((d["numero"], len(d["itens"]), d["valor_produtos"], d["autorizacao"]["cStat"]), ("7", 2, 37.5, "100"))
        casos = {
            "DOCTYPE": NT.xml(7, [("A", "x", "UN", 1, 1)], extra='<!DOCTYPE a [<!ENTITY x "y">]>'),
            "Chave de acesso inválida": NT.xml(7, [("A", "x", "UN", 1, 1)], chave_nfe="1" * 44),
            "modelo 55": NT.xml(7, [("A", "x", "UN", 1, 1)], modelo=65),
            "XML inválido": b"<nfeProc><sem fechar>",
            "não é uma NF-e": b"<?xml version='1.0'?><outra/>",
        }
        for msg, dados in casos.items():
            with self.assertRaisesRegex(S.RegraViolada, msg):
                nfe.ler(dados)
        ruim = NT.xml(7, [("A", "x", "UN", 2, 5)]).replace(b"<vProd>10.00</vProd></prod>", b"<vProd>11.00</vProd></prod>")
        with self.assertRaisesRegex(S.RegraViolada, "diferente do valor"):
            nfe.ler(ruim)


class TestFluxoDeCompra(BaseCompras):
    def test_pedido_nao_vira_estoque_e_segregacao_na_aprovacao(self):
        sid = C.abrir_solicitacao(self.c, D, [{"material_id": MAT, "quantidade": 100}], "Zona01", "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "não aprova a própria"):
            C.decidir_solicitacao(self.c, sid, True, None, "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "solicitação APROVADA"):
            C.emitir_pedido(self.c, "PC-1", D, self.forn, sid, [{"material_id": MAT, "quantidade": 10, "valor_unitario": 1}], "comprador")
        C.decidir_solicitacao(self.c, sid, True, None, "eng2")
        with self.assertRaisesRegex(S.RegraViolada, "excede o saldo aprovado"):
            C.emitir_pedido(self.c, "PC-1", D, self.forn, sid, [{"material_id": MAT, "quantidade": 101, "valor_unitario": 1}], "comprador")
        with self.assertRaisesRegex(S.RegraViolada, "fornecido pela Caesb"):
            C.abrir_solicitacao(self.c, D, [{"material_id": "CAESB-PEAD-DE63", "quantidade": 1}], "x", "eng1")
        antes = self.saldo()
        C.emitir_pedido(self.c, "PC-1", D, self.forn, sid, [{"material_id": MAT, "quantidade": 100, "valor_unitario": 1}], "comprador")
        self.assertEqual(self.saldo(), antes)                                         # pedido não é estoque
        self.assertEqual(self.q("SELECT COUNT(*) FROM movimentos")[0][0], 0)

    def test_entrega_e_aceite_parciais_recusa_e_devolucao(self):
        pid = self.pedido(100)
        nf = self.importar(501, [("L1", "Luva eletrofusão", "CX", 10, 100.0), ("FR", "Frete", "SV", 1, 80.0)])
        self.assertEqual(self.q("SELECT status, origem FROM notas_fiscais WHERE id=?", nf), [("A_CONFERIR", "XML")])
        self.assertEqual(self.q("SELECT COUNT(*) FROM movimentos")[0][0], 0)          # importada não movimenta
        with self.assertRaisesRegex(S.RegraViolada, "já importada"):
            self.importar(501, [("L1", "Luva", "CX", 10, 100.0)])
        (l1, _), (l2, _) = self.linhas(nf)
        pi = self.q("SELECT id FROM pedido_itens WHERE pedido_id=?", pid)[0][0]
        conf = lambda fator, **kw: C.conferir_nf(self.c, nf, pid, [
            {"linha_id": l1, "material_id": MAT, "fator": fator, "pedido_item_id": pi}, {"linha_id": l2, "fora_do_estoque": True}], **kw)
        with self.assertRaisesRegex(S.RegraViolada, "declare o fator"):
            conf(None, por="almox2")
        with self.assertRaisesRegex(S.RegraViolada, "excede o saldo do pedido"):
            conf(11, por="almox2")                                                    # 110 > 100
        with self.assertRaisesRegex(S.RegraViolada, "Confira todas as linhas"):
            C.conferir_nf(self.c, nf, pid, [{"linha_id": l1, "material_id": MAT, "fator": 10, "pedido_item_id": pi}], "almox2")
        conf(10, por="almox2")                                                        # 10 CX × 10 = 100 UN
        self.assertEqual(self.q("SELECT material_id, quantidade, valor_unitario FROM nf_itens WHERE nf_id=?", nf), [(MAT, 100.0, 10.0)])
        ni = self.q("SELECT id FROM nf_itens WHERE nf_id=?", nf)[0][0]
        self.assertEqual(self.saldo(), (0, 0))
        C.receber(self.c, nf, D2, [{"nf_item_id": ni, "quantidade": 60}], "almox1", "canhoto 1")
        self.assertEqual(self.saldo(), (0, 60))                                       # quarentena, não estoque
        with self.assertRaisesRegex(S.RegraViolada, "maior que o saldo da nota"):
            C.receber(self.c, nf, D2, [{"nf_item_id": ni, "quantidade": 41}], "almox1")
        ri = self.q("SELECT id FROM recebimento_itens")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "igual ao entregue"):
            C.inspecionar(self.c, ri, 50, 5, "LAUDO-1", "almox1", D2)
        with self.assertRaisesRegex(S.RegraViolada, "motivo da recusa"):
            C.inspecionar(self.c, ri, 50, 10, "LAUDO-1", "almox1", D2)
        C.inspecionar(self.c, ri, 50, 10, "LAUDO-1", "almox1", D2, "10 luvas com ovalização", base64.b64encode(b"%PDF-1.4 laudo").decode(), "laudo.pdf")
        self.assertEqual(self.saldo(), (50, 0))
        with self.assertRaisesRegex(S.RegraViolada, "já inspecionado"):
            C.inspecionar(self.c, ri, 60, 0, "x", "almox1", D2)
        sp = C.situacao_pedido(self.c, pid)["itens"][0]
        self.assertEqual({k: sp[k] for k in ("faturado", "entregue", "quarentena", "aceito", "recusado", "pendente_entrega", "a_faturar")},
                         {"faturado": 100, "entregue": 60, "quarentena": 0, "aceito": 50, "recusado": 10, "pendente_entrega": 50,
                          "a_faturar": 10})                                          # o recusado pode vir em outra nota
        S.reservar(self.c, D2, "Zona01", MAT, 47)
        with self.assertRaisesRegex(S.RegraViolada, "Disponível no almoxarifado"):
            C.devolver_ao_fornecedor(self.c, ni, D2, 5, "defeito", "almox1")
        S.cancelar_reserva(self.c, self.q("SELECT id FROM reservas")[0][0], "remanejada")
        C.devolver_ao_fornecedor(self.c, ni, D2, 5, "defeito de fábrica constatado na montagem", "almox1", "NF dev 9")
        self.assertEqual(self.saldo(), (45, 0))
        self.assertEqual(C.situacao_pedido(self.c, pid)["itens"][0]["pendente_entrega"], 55)
        C.receber(self.c, nf, D2, [{"nf_item_id": ni, "quantidade": 40}], "almox1")
        ri2 = self.q("SELECT MAX(id) FROM recebimento_itens")[0][0]
        C.inspecionar(self.c, ri2, 40, 0, "LAUDO-2", "almox1", D2)
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("ENCERRADA",)])
        self.assertEqual(self.saldo(), (85, 0))
        self.assertEqual(self.q("SELECT COUNT(*) FROM medicao_lancamentos")[0][0], 0)    # estoque ≠ faturável
        self.assertEqual(self.q("SELECT status FROM movimentos WHERE tipo='ENTRADA_NF' ORDER BY id"),
                         [("INSPECIONADO",), ("ACEITO",), ("INSPECIONADO",), ("ACEITO",)])

    def test_nf_digitada_exige_anexo_e_conferencia_por_outra_pessoa(self):
        pid = self.pedido(20, TUBO, "PC-002")
        pi = self.q("SELECT id FROM pedido_itens WHERE pedido_id=?", pid)[0][0]
        linhas = [{"descricao": "Tubo PEAD DE63 PN10", "unidade": "M", "quantidade": 20, "valor_unitario": 9}]
        with self.assertRaisesRegex(S.RegraViolada, "Anexe o PDF ou a imagem"):
            C.registrar_nf_digitada(self.c, "77", self.forn, D, linhas, "almox1", None, None)
        with self.assertRaisesRegex(S.RegraViolada, "Imagem do documento recusada"):
            C.registrar_nf_digitada(self.c, "77", self.forn, D, linhas, "almox1", base64.b64encode(b"\xff\xd8\xff falso").decode(), "NF_IMAGEM")
        nf = C.registrar_nf_digitada(self.c, "77", self.forn, D, linhas, "almox1", jpeg(), "NF_IMAGEM", "nf77.jpg")
        lid = self.linhas(nf)[0][0]
        conf = [{"linha_id": lid, "material_id": TUBO, "pedido_item_id": pi}]
        with self.assertRaisesRegex(S.RegraViolada, "Quem digitou"):
            C.conferir_nf(self.c, nf, pid, conf, "almox1")
        C.conferir_nf(self.c, nf, pid, conf, "almox2")
        self.assertEqual(self.q("SELECT conferida_por, status FROM notas_fiscais WHERE id=?", nf), [("almox2", "CONFERIDA")])
        doc = self.q("SELECT arquivo, sha256 FROM documentos")[0]
        self.assertTrue(os.path.exists(os.path.join(self.dados, "documentos", doc[0])))

    def test_backup_e_restauracao_incluem_os_documentos(self):
        self.pedido(10)
        self.importar(601, [("L1", "Luva", "UN", 10, 3.0)])
        arq = self.q("SELECT arquivo FROM documentos")[0][0]
        self.c.close()
        self._conns.remove(self.c)
        pasta = backup.criar(self.db, os.path.join(self.dados, "backups"), self.fotos)
        self.assertTrue(backup.verificar(pasta)[0])
        with open(os.path.join(pasta, "manifesto.json"), encoding="utf-8") as f:
            self.assertIn("documentos/" + arq, json.load(f)["arquivos"])
        caminho = os.path.join(self.dados, "documentos", arq)
        os.remove(caminho)                                                             # documento perdido
        with self.assertRaises(backup.BackupIncompleto) as cm:
            backup.criar(self.db, os.path.join(self.dados, "backups"), self.fotos)
        self.assertEqual(cm.exception.ausentes, ["documentos/" + arq])
        backup.restaurar(pasta, self.db, self.fotos, os.path.join(self.dados, "seg"), permitir_incompleto=True)
        self.assertEqual(backup.sha256(caminho), self.q("SELECT sha256 FROM documentos")[0][0])


class TestTransferenciaInventarioReservas(BaseCompras):
    def entrada(self, q=50, mat="CAESB-PEAD-DE63"):
        S.entrada_material(self.c, D, mat, q, "ROMANEIO_CAESB", "ROM-1", "almox1")

    def test_transferencia_entre_equipes_em_campo(self):
        self.entrada()
        c1 = S.checkin(self.c, D, "Zona01", "TRECHO", "Zona01_PB01_Rede_TR001", materiais=[{"material_id": "CAESB-PEAD-DE63", "quantidade": 20}])
        with self.assertRaisesRegex(S.RegraViolada, "não tem check-in aberto"):
            C.transferir(self.c, D, "CAESB-PEAD-DE63", 8, "Zona01", "Zona02", "Eng. Ana", "almox1")
        c2 = S.checkin(self.c, D, "Zona02", "TRECHO", "Zona02_PB04_Rede_TR036")
        with self.assertRaisesRegex(S.RegraViolada, "não transfere"):
            C.transferir(self.c, D, "CAESB-PEAD-DE63", 21, "Zona01", "Zona02", "Eng. Ana", "almox1")
        with self.assertRaisesRegex(S.RegraViolada, "autorizou"):
            C.transferir(self.c, D, "CAESB-PEAD-DE63", 8, "Zona01", "Zona02", "", "almox1")
        C.transferir(self.c, D, "CAESB-PEAD-DE63", 8, "Zona01", "Zona02", "Eng. Ana", "almox1", "faltou na Zona02")
        cust = lambda eq, ck: S.custodia_equipe(self.c, eq, "CAESB-PEAD-DE63", ck)
        self.assertEqual((cust("Zona01", c1), cust("Zona02", c2)), (12, 8))
        self.assertEqual(self.saldo("CAESB-PEAD-DE63"), (30, 0))                      # almoxarifado não muda
        ab = {c["equipe_id"]: c for c in S.checkins_abertos(self.c)}
        self.assertEqual(ab["Zona02"]["materiais"][0]["transferido"], 8)
        with self.assertRaisesRegex(S.RegraViolada, "deve fechar a custódia"):
            S.checkout(self.c, c1, [{"material_id": "CAESB-PEAD-DE63", "aplicado": 20}])
        S.checkout(self.c, c1, [{"material_id": "CAESB-PEAD-DE63", "aplicado": 12}])
        S.checkout(self.c, c2, [{"material_id": "CAESB-PEAD-DE63", "aplicado": 6, "sobra": 2}])
        self.assertEqual(self.saldo("CAESB-PEAD-DE63"), (32, 0))

    def test_inventario_com_aprovacao_de_outra_pessoa_e_saldo_mudado(self):
        self.entrada(50)
        inv = C.registrar_contagem(self.c, D, [{"material_id": "CAESB-PEAD-DE63", "contado": 48}], "almox1")
        with self.assertRaisesRegex(S.RegraViolada, "Quem contou"):
            C.decidir_inventario(self.c, inv, True, "diferença aceita", "almox1")
        inv2 = C.registrar_contagem(self.c, D, [{"material_id": "CAESB-PEAD-DE63", "contado": 47}], "almox1")
        C.decidir_inventario(self.c, inv, True, "perda por corte não registrada", "eng1")
        self.assertEqual(self.saldo("CAESB-PEAD-DE63"), (48, 0))
        self.assertEqual(self.q("SELECT tipo, quantidade, ref_tipo FROM movimentos WHERE ref_tipo='INVENTARIO'"),
                         [("AJUSTE_INVENTARIO_SAIDA", 2.0, "INVENTARIO")])
        with self.assertRaisesRegex(S.RegraViolada, "saldo mudou desde a contagem"):
            C.decidir_inventario(self.c, inv2, True, "x", "eng1")                      # contada antes do ajuste
        C.decidir_inventario(self.c, inv2, False, "recontar amanhã", "eng1")
        self.assertEqual([i["status"] for i in C.inventarios(self.c)], ["DESCARTADO", "AJUSTADO"])

    def test_reservas_vencidas_liberadas_com_motivo(self):
        self.entrada(50)
        r1 = S.reservar(self.c, D, "Zona01", "CAESB-PEAD-DE63", 30)
        r2 = S.reservar(self.c, D2, "Zona02", "CAESB-PEAD-DE63", 10)
        self.assertEqual([r["id"] for r in C.reservas_vencidas(self.c, D2)], [r1])
        with self.assertRaisesRegex(S.RegraViolada, "não está vencida"):
            C.liberar_reservas_vencidas(self.c, [r2], "x", "almox1", D2)
        C.liberar_reservas_vencidas(self.c, [r1], "equipe não compareceu", "almox1", D2)
        self.assertEqual(S.disponivel(self.c, "CAESB-PEAD-DE63"), 40)
        self.assertIn("vencida", self.q("SELECT motivo FROM reservas WHERE id=?", r1)[0][0])


class TestComprasPeloHTTP(BaseHTTP):
    def test_permissoes_e_reenvio_do_recebimento(self):
        C.cadastrar_fornecedor(self.c, NT.CNPJ_FORNECEDOR, "Fornecedor de Teste Ltda", "adm")
        eng1, eng2, almox, adm = (self.cliente(x) for x in ("eng1", "eng2", "almox1", "adm"))
        st, r = eng1.post("/api/solicitacao", {"data": D, "motivo": "Zona01", "itens": [{"material_id": MAT, "quantidade": 10}]})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT solicitante FROM solicitacoes_compra"), [("eng1",)])
        self.assertEqual(eng1.post("/api/solicitacao/decidir", {"solicitacao_id": r["id"], "aprovar": True})[0], 422)   # própria
        self.assertEqual(almox.post("/api/solicitacao/decidir", {"solicitacao_id": r["id"], "aprovar": True})[0], 403)  # perfil
        self.assertEqual(eng2.post("/api/solicitacao/decidir", {"solicitacao_id": r["id"], "aprovar": True})[0], 200)
        corpo = {"numero": "PC-9", "data": D, "fornecedor_id": 1, "solicitacao_id": r["id"], "itens": [{"material_id": MAT, "quantidade": 10, "valor_unitario": 2}]}
        self.assertEqual(almox.post("/api/pedido", corpo)[0], 403)
        st, p = adm.post("/api/pedido", corpo)
        self.assertEqual(st, 200, p)
        st, n = almox.post("/api/nf/importar-xml", {"conteudo_b64": NT.b64(NT.xml(901, [("L", "Luva", "UN", 10, 2.0)])), "nome": "n.xml"})
        self.assertEqual(st, 200, n)
        lid = self.q("SELECT id FROM nf_linhas")[0][0]
        pi = self.q("SELECT id FROM pedido_itens")[0][0]
        self.assertEqual(self.cliente("enc1").post("/api/nf/conferir", {"nf_id": n["nf_id"], "pedido_id": p["id"], "linhas": []})[0], 403)
        st, _ = almox.post("/api/nf/conferir", {"nf_id": n["nf_id"], "pedido_id": p["id"],
                                                "linhas": [{"linha_id": lid, "material_id": MAT, "pedido_item_id": pi}]})
        self.assertEqual(st, 200)
        ni = self.q("SELECT id FROM nf_itens")[0][0]
        rec = {"nf_id": n["nf_id"], "data": D2, "itens": [{"nf_item_id": ni, "quantidade": 4}]}
        for _ in range(3):
            self.assertEqual(almox.post("/api/recebimento", rec, cabecalhos={"X-Idem": "rec-1"})[0], 200)
        self.assertEqual(self.q("SELECT COUNT(*), SUM(quantidade) FROM recebimento_itens"), [(1, 4.0)])
        self.assertEqual(self.q("SELECT recebido_por FROM recebimentos"), [("almox1",)])


class TestMigracaoV10ParaV11(Base):
    def test_nf_e_movimentos_existentes_continuam(self):
        c = sqlite3.connect(self.db)
        with open(os.path.join(AQUI, "fixtures", "schema_v10.sql"), encoding="utf-8") as f:
            c.executescript(f.read())
        c.execute("INSERT INTO schema_versao VALUES (10,'x','v10')")
        c.execute("INSERT INTO equipes(id,nome) VALUES ('Zona01','Z1')")
        c.execute("INSERT INTO materiais(id,descricao,unidade,propriedade) VALUES (?, 'Luva', 'UN', 'ANKARA')", (MAT,))
        c.execute("INSERT INTO notas_fiscais(numero,fornecedor,data_entrega,status) VALUES ('123','F','2026-10-10','QUARENTENA')")
        c.execute("INSERT INTO nf_itens(nf_id,material_id,quantidade,valor_unitario) VALUES (1,?,5,2)", (MAT,))
        c.execute("INSERT INTO movimentos(data,material_id,tipo,quantidade,documento,status,nf_id) VALUES ('2026-10-10',?,'ENTRADA_NF',5,'NF 123','QUARENTENA',1)", (MAT,))
        c.execute("INSERT INTO movimentos(data,material_id,tipo,quantidade,documento) VALUES ('2026-10-11',?,'ENTRADA_CONSUMO',3,'x')", (MAT,))
        c.execute("INSERT INTO estornos(movimento_id,motivo,responsavel,em) VALUES (2,'lançado errado','almox','x')")
        c.commit()
        c.close()
        rel = self.aplicar()
        self.assertEqual((rel["esquema_antes"], rel["esquema_depois"]), (10, S.VERSAO_ESQUEMA))
        c2 = self.conectar()
        self.assertEqual(self.q("SELECT id, tipo, quantidade, status, nf_id FROM movimentos ORDER BY id"),
                         [(1, "ENTRADA_NF", 5.0, "QUARENTENA", 1), (2, "ENTRADA_CONSUMO", 3.0, None, None)])
        self.assertEqual(self.q("SELECT movimento_id FROM estornos"), [(2,)])                       # vínculo preservado
        self.assertEqual(self.q("SELECT id, status, origem FROM notas_fiscais"), [(1, "QUARENTENA", "DIRETA")])
        self.assertIn("TRANSF_SAIDA", self.q("SELECT sql FROM sqlite_master WHERE name='movimentos'")[0][0])
        self.assertEqual(S.saldo_almox(c2, MAT), (0, 5))
        S.aceitar_nf(c2, 1, "laudo.pdf")                                                            # fluxo anterior continua
        self.assertEqual(S.saldo_almox(c2, MAT), (5, 0))
        self.assertEqual(self.q("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='movimentos'"), [("ix_mov_mat",)])


class TestMigracaoComChaveQuebrada(Base):
    def test_violacao_de_chave_estrangeira_reprova_e_nao_altera(self):
        c = sqlite3.connect(self.db)                                   # sqlite3 abre com chaves desligadas: dado quebrado
        with open(os.path.join(AQUI, "fixtures", "schema_v10.sql"), encoding="utf-8") as f:
            c.executescript(f.read())
        c.execute("INSERT INTO schema_versao VALUES (10,'x','v10')")
        c.execute("INSERT INTO materiais(id,descricao,unidade,propriedade) VALUES (?, 'Luva', 'UN', 'ANKARA')", (MAT,))
        c.commit()
        c.execute("PRAGMA foreign_keys = OFF")                         # o esquema liga as chaves; simula dado já quebrado
        c.execute("INSERT INTO movimentos(data,material_id,tipo,quantidade,status,nf_id) VALUES ('2026-10-10',?,'ENTRADA_NF',5,'ACEITO',99)", (MAT,))
        c.commit()
        c.close()
        rel = self.reprovar("CHAVE_ESTRANGEIRA_VIOLADA")                # banco byte a byte igual (conferido em reprovar)
        self.assertIn("movimentos", str(rel["bloqueios"]))


if __name__ == "__main__":
    unittest.main()
