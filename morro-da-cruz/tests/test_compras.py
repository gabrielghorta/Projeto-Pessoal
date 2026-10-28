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



def cnpj_de(base12):
    """CNPJ fictício com os dígitos verificadores certos."""
    d = [int(x) for x in base12]
    for n in (12, 13):
        pesos = list(range(n - 7, 1, -1)) + list(range(9, 1, -1))
        dv = 11 - sum(a * b for a, b in zip(d, pesos)) % 11
        d.append(0 if dv >= 10 else dv)
    return "".join(map(str, d))


class TestNotaNoAlmoxarifado(BaseCompras):
    """A nota que chega sem pedido: o almoxarife importa o XML (o fornecedor vem do próprio XML), confere com o material
    sugerido, recebe (quarentena) e aceita; o aceito só fica disponível depois da aprovação de outra pessoa. A remessa de
    tubo da Caesb vira romaneio."""
    def test_fornecedor_novo_vem_do_xml(self):
        outro = cnpj_de("998877660001")
        x = NT.b64(NT.xml(77, [("A1", "Luva", "UN", 1, 5.0)], cnpj=outro))
        r = C.importar_nfe_xml(self.c, x, "nfe77.xml", "almox1")
        self.assertEqual(r["fornecedor_novo"], {"cnpj": outro, "nome": "Fornecedor de Teste Ltda"})
        self.assertEqual(self.q("SELECT COUNT(*) FROM notas_fiscais")[0][0], 0)              # nada gravado sem a confirmação
        r = C.importar_nfe_xml(self.c, x, "nfe77.xml", "almox1", cadastrar=True)
        self.assertEqual(self.q("SELECT f.cnpj, f.criado_por FROM fornecedores f JOIN notas_fiscais n ON n.fornecedor_id=f.id WHERE n.id=?",
                                r["nf_id"]), [(outro, "almox1")])

    def test_sem_pedido_sugestao_quarentena_e_aprovacao_de_outra_pessoa(self):
        nf = self.importar(18734, [(MAT, "peça do nó (código = id do material)", "UN", 4, 12.0),
                                   ("X9", "Peça que ninguém conhece", "UN", 1, 3.0)])
        sug = {s["linha_id"]: s for s in C.sugerir_materiais(self.c, nf)}
        (l1, _), (l2, _) = self.linhas(nf)
        self.assertEqual((sug[l1]["material_id"], sug[l1]["motivo"], sug[l1]["fator"]), (MAT, "código do produto", 1.0))
        self.assertIsNone(sug[l2]["material_id"])
        r = C.conferir_nf(self.c, nf, 0, [{"linha_id": l1, "material_id": MAT}, {"linha_id": l2, "fora_do_estoque": True}], "almox1")
        self.assertEqual(r, {"sem_pedido": True})
        ni = self.q("SELECT id FROM nf_itens WHERE nf_id=?", nf)[0][0]
        rid = C.receber(self.c, nf, D2, [{"nf_item_id": ni, "quantidade": 4}], "almox1")
        self.assertEqual(self.saldo(), (0, 4))                                                # quarentena
        C.inspecionar_entrega(self.c, rid, [], None, "almox1", D2)                           # "Aceitar tudo", sem laudo
        self.assertEqual(self.saldo(), (4, 0))                                                # sem aprovação da nota (D-175)
        self.assertEqual(self.q("SELECT aprovada_por, aprovada_em FROM notas_fiscais"), [(None, None)])
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("ENCERRADA",)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM medicao_lancamentos")[0][0], 0)        # estoque ≠ faturável

    def test_recusa_na_entrega_exige_laudo(self):
        nf = self.importar(91, [(MAT, "peça", "UN", 5, 1.0)])
        (l1, _), = self.linhas(nf)
        C.conferir_nf(self.c, nf, 0, [{"linha_id": l1, "material_id": MAT}], "almox1")
        ni = self.q("SELECT id FROM nf_itens WHERE nf_id=?", nf)[0][0]
        rid = C.receber(self.c, nf, D2, [{"nf_item_id": ni, "quantidade": 5}], "almox1")
        ri = self.q("SELECT id FROM recebimento_itens WHERE recebimento_id=?", rid)[0][0]
        item = [{"recebimento_item_id": ri, "aceito": 3, "recusado": 2}]
        with self.assertRaisesRegex(S.RegraViolada, "Com recusa, informe"):
            C.inspecionar_entrega(self.c, rid, item, "", "almox1", D2, "2 trincadas")
        C.inspecionar_entrega(self.c, rid, item, "LAUDO-7", "almox1", D2, "2 trincadas")
        self.assertEqual(self.q("SELECT aceito, recusado, laudo FROM inspecoes"), [(3, 2, "LAUDO-7")])

    def test_remessa_da_caesb_vira_romaneio(self):
        tubo = self.q("SELECT id FROM materiais WHERE propriedade='CAESB' ORDER BY id LIMIT 1")[0][0]
        de = tubo.rsplit("DE", 1)[1]
        nf = self.importar(4521, [("T1", f"TUBO PEAD DE {de} PN 10", "M", 120, 0.01)])
        (l1, _), = self.linhas(nf)
        sug = C.sugerir_materiais(self.c, nf)[0]
        self.assertEqual((sug["material_id"], sug["motivo"], sug["caesb"]), (tubo, "pela descrição", True))
        self.assertEqual(C.conferir_nf(self.c, nf, 0, [{"linha_id": l1, "material_id": tubo}], "almox1"), {"sem_pedido": False})
        antes = {c["material_id"]: c["retirado"] for c in S.compatibilizacao_caesb(self.c)}[tubo]
        ni = self.q("SELECT id FROM nf_itens WHERE nf_id=?", nf)[0][0]
        C.receber(self.c, nf, D2, [{"nf_item_id": ni, "quantidade": 120}], "almox1")
        self.assertEqual(self.q("SELECT tipo, status, documento FROM movimentos WHERE nf_id=?", nf),
                         [("ROMANEIO_CAESB", "ACEITO", "NF 4521 (remessa Caesb)")])
        self.assertEqual({c["material_id"]: c["retirado"] for c in S.compatibilizacao_caesb(self.c)}[tubo], antes + 120)
        self.assertEqual(C.a_inspecionar(self.c), [])                                       # sem quarentena de compra
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("ENCERRADA",)])
        self.assertEqual([n["id"] for n in C.notas_a_receber(self.c)], [])

class TestRecebimentoNumToque(BaseCompras):
    """D-135 (26/10/2026): na maioria das vezes a nota chega certa. "Recebido conforme a nota" confere pelo material
    sugerido, recebe e aceita de uma vez; "Registrar problema" grava o que faltou (continua a receber) e o avariado
    (recusado, com a observação como motivo e laudo). A nota sem pedido continua esperando a aprovação de outra pessoa."""

    def test_num_toque_confere_recebe_e_aceita(self):
        tubo = self.q("SELECT id FROM materiais WHERE propriedade='CAESB' ORDER BY id LIMIT 1")[0][0]
        de = tubo.rsplit("DE", 1)[1]
        nf = self.importar(501, [(MAT, "peça do nó", "UN", 4, 12.0), ("T1", f"TUBO PEAD DE {de} PN 10", "M", 30, 0.01)])
        r = C.receber_nota(self.c, nf, "almox1", D2)
        self.assertEqual((r["itens"], r["recusado"], r["encerrada"], r["aguarda_aprovacao"]), (2, 0, True, False))
        self.assertEqual(self.q("SELECT status, conferida_por FROM notas_fiscais WHERE id=?", nf), [("ENCERRADA", "almox1")])
        self.assertEqual(self.saldo(), (4, 0))                                                # sem aprovação da nota (D-175)
        self.assertEqual(self.q("SELECT tipo, status FROM movimentos WHERE nf_id=? AND material_id=?", nf, tubo),
                         [("ROMANEIO_CAESB", "ACEITO")])                                       # o tubo da Caesb: romaneio
        import relatorios
        self.assertEqual(next(m for m in relatorios.materiais(self.c) if m['material_id'] == tubo)['comprado'], 0)
        self.assertEqual(self.saldo(), (4, 0))
        with self.assertRaisesRegex(S.RegraViolada, "Só nota a conferir ou conferida"):
            C.receber_nota(self.c, nf, "almox1", D2)

    def test_com_pedido_entra_direto(self):
        ped = self.pedido(10)
        nf = self.importar(502, [(MAT, "peça", "UN", 10, 10.0)])
        r = C.receber_nota(self.c, nf, "almox1", D2, pedido_id=ped)
        self.assertEqual((r["encerrada"], r["aguarda_aprovacao"], self.saldo()), (True, False, (10, 0)))

    def test_problema_falta_e_avaria(self):
        nf = self.importar(503, [(MAT, "peça", "UN", 10, 1.0)])
        (l1, _), = self.linhas(nf)
        with self.assertRaisesRegex(S.RegraViolada, "Diga o porquê"):
            C.receber_nota(self.c, nf, "almox1", D2, problema={"observacao": " ", "linhas": {}})
        with self.assertRaisesRegex(S.RegraViolada, "não passa do que chegou"):
            C.receber_nota(self.c, nf, "almox1", D2, problema={"observacao": "x", "linhas": {str(l1): {"chegou": 2, "avariado": 3}}})
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("A_CONFERIR",)])   # nada gravado
        r = C.receber_nota(self.c, nf, "almox1", D2, problema={"observacao": "faltaram 2; 1 trincada",
                                                               "linhas": {str(l1): {"chegou": 8, "avariado": 1}}})
        self.assertEqual((r["recusado"], r["encerrada"]), (1, False))
        self.assertEqual(self.q("SELECT aceito, recusado, laudo, motivo_recusa FROM inspecoes"), [(7, 1, "faltaram 2; 1 trincada", "faltaram 2; 1 trincada")])
        self.assertEqual(self.q("SELECT documento FROM recebimentos"), [("obs.: faltaram 2; 1 trincada",)])
        nota = next(n for n in C.notas_a_receber(self.c) if n["id"] == nf)
        self.assertEqual([(i["quantidade"], i["recebido"]) for i in nota["itens"]], [(10, 8)])   # faltam 2: a receber
        r = C.receber_nota(self.c, nf, "almox1", D2)                                          # o resto chegou certo
        self.assertEqual((r["encerrada"], self.q("SELECT SUM(aceito), SUM(recusado) FROM inspecoes")), (True, [(9, 1)]))

    def test_frete_e_servico_ficam_fora_do_estoque(self):
        nf = self.importar(505, [(MAT, "peça", "UN", 2, 1.0), ("F1", "Frete", "SV", 1, 30.0), ("S1", "SERVIÇO DE DESCARGA", "UN", 1, 9.0)])
        r = C.receber_nota(self.c, nf, "almox1", D2)
        self.assertEqual((r["itens"], r["encerrada"]), (1, True))
        self.assertEqual(self.q("SELECT n_item, fora_do_estoque FROM nf_linhas WHERE nf_id=? ORDER BY n_item", nf), [(1, 0), (2, 1), (3, 1)])

    def test_linha_sem_material_sugerido_fica_faltando_a_confirmacao(self):
        nf = self.importar(504, [(MAT, "peça", "UN", 1, 1.0), ("X9", "Peça que ninguém conhece", "UN", 1, 3.0)])
        r = C.receber_nota(self.c, nf, "almox1", D2)
        self.assertEqual((self.saldo(), r["aguardando_identificacao"]), ((1, 0), 1))
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("CONFERIDA",)])


class TestRecebimentoNaLateral(BaseCompras):
    """D-169 e D-170 (27/10/2026): a nota sobe em Compras e notas; no Estoque, cada nota tem na lateral Aceitar a entrega,
    Recusar a entrega (com o porquê) e Aceite ou recusa parcial (o aceito e o recusado de cada linha, e o porquê).
    A nota conferida sem nenhuma linha para o estoque não fica mais "a receber" sem nada a receber."""

    def tubo(self):
        t = self.q("SELECT id FROM materiais WHERE propriedade='CAESB' ORDER BY id LIMIT 1")[0][0]
        return t, t.rsplit("DE", 1)[1]

    def test_recusa_total_nada_entra_e_a_nota_fecha(self):
        tubo, de = self.tubo()
        nf = self.importar(601, [(MAT, "peça do nó", "UN", 5, 12.0), ("T1", f"TUBO PEAD DE {de} PN 10", "M", 30, 0.01)])
        with self.assertRaisesRegex(S.RegraViolada, "Diga por que a entrega foi recusada"):
            C.receber_nota(self.c, nf, "almox1", D2, recusa="  ")
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("A_CONFERIR",)])     # nada gravado
        r = C.receber_nota(self.c, nf, "almox1", D2, recusa="material diferente do pedido")
        self.assertEqual((r["recusado"], r["encerrada"], r["aguarda_aprovacao"]), (35, True, False))
        self.assertEqual(self.saldo(), (0, 0))                                          # nada entrou no estoque
        self.assertEqual(self.q("SELECT aceito, recusado, motivo_recusa FROM inspecoes ORDER BY recusado DESC"),
                         [(0, 30, "material diferente do pedido"), (0, 5, "material diferente do pedido")])
        self.assertEqual(self.q("SELECT quantidade, documento FROM movimentos WHERE nf_id=? AND tipo='ROMANEIO_CAESB'", nf),
                         [(0, "NF 601 (remessa Caesb); 30 recusado, fora do romaneio")])   # o tubo não entrou
        self.assertEqual(self.q("SELECT documento FROM recebimentos WHERE nf_id=?", nf), [("recusa: material diferente do pedido",)])
        self.assertEqual([n["id"] for n in C.notas_a_receber(self.c)], [])             # sem pedido e toda recusada: some

    def test_aceite_ou_recusa_parcial(self):
        tubo, de = self.tubo()
        nf = self.importar(602, [(MAT, "peça", "UN", 10, 1.0), ("T1", f"TUBO PEAD DE {de} PN 10", "M", 30, 0.01)])
        l1, l2 = [l for l, _ in self.linhas(nf)]
        with self.assertRaisesRegex(S.RegraViolada, "no máximo 10"):
            C.receber_nota(self.c, nf, "almox1", D2, problema={"observacao": "x", "linhas": {str(l1): {"aceito": 8, "recusado": 3}}})
        r = C.receber_nota(self.c, nf, "almox1", D2, problema={
            "observacao": "1 trincada; faltaram 3; 5 m de tubo amassado",
            "linhas": {str(l1): {"aceito": 6, "recusado": 1}, str(l2): {"aceito": 25, "recusado": 5}}})
        self.assertEqual((r["recusado"], r["encerrada"]), (6, False))                  # faltam 3 peças: a receber
        self.assertEqual(self.q("SELECT aceito, recusado FROM inspecoes ORDER BY aceito DESC"), [(25, 5), (6, 1)])
        self.assertEqual(self.q("SELECT quantidade FROM movimentos WHERE nf_id=? AND tipo='ROMANEIO_CAESB'", nf), [(25,)])
        nota = next(n for n in C.notas_a_receber(self.c) if n["id"] == nf)
        self.assertEqual(sorted((i["quantidade"], i["recebido"]) for i in nota["itens"]), [(10, 7), (30, 30)])
        r = C.receber_nota(self.c, nf, "almox1", D2)                                   # as 3 que faltavam chegaram
        self.assertEqual(r["encerrada"], True)
        self.assertEqual(self.q("SELECT SUM(aceito), SUM(recusado) FROM inspecoes"), [(34, 6)])

    def test_conferida_sem_material_nao_fica_presa(self):
        nf = self.importar(603, [(MAT, "peça", "UN", 2, 1.0), ("F1", "Frete", "SV", 1, 30.0)])
        fora = [{"linha_id": l, "fora_do_estoque": True} for l, _ in self.linhas(nf)]
        with self.assertRaisesRegex(S.RegraViolada, "Nenhuma linha vai para o estoque"):
            C.conferir_nf(self.c, nf, 0, fora, "almox1")
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("A_CONFERIR",)])
        self.assertEqual(C.conferir_nf(self.c, nf, 0, fora, "almox1", so_fora_do_estoque=True), {"sem_pedido": False, "encerrada": True})
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("ENCERRADA",)])   # só frete: fecha
        self.assertNotIn(nf, [n["id"] for n in C.notas_a_receber(self.c)])

    def test_refazer_a_conferencia_da_nota_que_ficou_presa(self):
        nf = self.importar(604, [(MAT, "peça", "UN", 4, 1.0)])
        # como ficavam as notas conferidas sem material antes da D-169: "a receber" sem nada a receber
        self.c.execute("UPDATE nf_linhas SET fora_do_estoque=1 WHERE nf_id=?", (nf,))
        self.c.execute("UPDATE notas_fiscais SET status='CONFERIDA', conferida_por='almox1' WHERE id=?", (nf,))
        nota = next(n for n in C.notas_a_receber(self.c) if n["id"] == nf)
        self.assertEqual((nota["status"], nota["itens"], nota["entregas"]), ("CONFERIDA", [], []))
        C.refazer_conferencia(self.c, nf, "almox1")
        self.assertEqual(self.q("SELECT status, conferida_por FROM notas_fiscais WHERE id=?", nf), [("A_CONFERIR", None)])
        self.assertEqual(self.q("SELECT fora_do_estoque, material_id FROM nf_linhas WHERE nf_id=?", nf), [(0, None)])
        r = C.receber_nota(self.c, nf, "almox1", D2)                                   # agora recebe pelos botões
        self.assertEqual((r["encerrada"], r["recusado"]), (True, 0))
        with self.assertRaisesRegex(S.RegraViolada, "Só nota conferida"):
            C.refazer_conferencia(self.c, nf, "almox1")
        outra = self.importar(605, [(MAT, "peça", "UN", 4, 1.0)])
        (l1, _), = self.linhas(outra)
        C.conferir_nf(self.c, outra, 0, [{"linha_id": l1, "material_id": MAT}], "almox1")
        with self.assertRaisesRegex(S.RegraViolada, "já tem material conferido"):
            C.refazer_conferencia(self.c, outra, "almox1")

    def test_tubo_da_caesb_nao_volta_ao_fornecedor(self):
        tubo, de = self.tubo()
        nf = self.importar(606, [("T1", f"TUBO PEAD DE {de} PN 10", "M", 30, 0.01)])
        C.receber_nota(self.c, nf, "almox1", D2)
        ni = self.q("SELECT id FROM nf_itens WHERE nf_id=?", nf)[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "não volta ao fornecedor"):
            C.devolver_ao_fornecedor(self.c, ni, D2, 1, "amassado", "almox1")


class TestConferenciaPorMarcacao(BaseCompras):
    """D-171 (27/10/2026): conferir é marcar. O sistema reconhece o material de cada linha (o tubo da Caesb pela bitola,
    sem confundir PE 100 e SDR 17 com medida); o almoxarife só marca e aceita, sem escolher material nem pedido. A linha
    que o sistema não reconhece fica "faltando a confirmação" em Compras e notas, e quem confirma é quem tem a
    permissão de receber (na prática, a engenharia); a próxima nota do mesmo fornecedor já vem reconhecida."""

    def material(self, mid, descricao, unidade="UN"):
        self.c.execute("INSERT INTO materiais(id, descricao, unidade, propriedade) VALUES (?,?,?,'ANKARA')", (mid, descricao, unidade))

    def fornecedor_caesb(self):
        cnpj = cnpj_de("003947740001")
        C.cadastrar_fornecedor(self.c, cnpj, "CAESB - Companhia de Saneamento Ambiental do DF", "comprador")
        return cnpj

    def sug(self, nf):
        return {s["linha_id"]: s for s in C.sugerir_materiais(self.c, nf)}

    def test_tubo_da_caesb_pela_bitola_sem_contar_pe_e_sdr(self):
        linha = "TUBO PEAD PE100 DE63 PN10 SDR17 - AGUA - FORNECIMENTO CAESB"
        nf = self.importar(701, [("2001", linha, "M", 100, 0.01)])
        s, = self.sug(nf).values()
        self.assertEqual((s["material_id"], s["motivo"], s["caesb"], s["fator"]), ("CAESB-PEAD-DE63", "tubo da Caesb pela bitola", True, 1.0))
        cnpj = self.fornecedor_caesb()                 # o emitente é a Caesb: a linha nem precisa dizer Caesb
        x = NT.b64(NT.xml(702, [("2002", "TUBO PEAD PE 100 DE 63 SDR 17", "M", 50, 0.01)], cnpj=cnpj))
        nf2 = C.importar_nfe_xml(self.c, x, "nfe702.xml", "almox1")["nf_id"]
        self.assertEqual([s["material_id"] for s in self.sug(nf2).values()], ["CAESB-PEAD-DE63"])
        r = C.receber_nota(self.c, nf2, "almox1", D2)
        self.assertEqual((r["encerrada"], r["aguarda_aprovacao"]), (True, False))
        self.assertEqual(self.q("SELECT tipo, quantidade FROM movimentos WHERE nf_id=?", nf2), [("ROMANEIO_CAESB", 50)])
        # PE 100 e SDR 17 não são medida: a luva DE 20 é achada pela descrição
        self.material("LUVA-EF-20", "LUVA ELETROFUSAO PEAD DE 20 MM")
        nf3 = self.importar(703, [("L20", "LUVA ELETROFUSAO PEAD PE100 DE 20 MM SDR 11", "UN", 4, 9.0)])
        s, = self.sug(nf3).values()
        self.assertEqual((s["material_id"], s["motivo"]), ("LUVA-EF-20", "pela descrição"))

    def test_linha_desconhecida_e_confirmada_em_compras_e_lembrada(self):
        self.material("CURVA-90-63", "CURVA 90 GRAUS PEAD DE 63")
        nf = self.importar(711, [(MAT, "peça", "UN", 2, 1.0), ("CV", "CURVA PEAD 90 DE 63 SOLDAVEL", "PC", 3, 20.0),
                                 ("X9", "Peça que ninguém conhece", "CX", 2, 3.0)])
        (l1, _), (l2, _), (l3, _) = self.linhas(nf)
        sug = self.sug(nf)
        self.assertEqual([c["material_id"] for c in sug[l2]["candidatos"]][:1], ["CURVA-90-63"])      # para só marcar
        self.assertNotIn("CAESB-PEAD-DE63", [c["material_id"] for s in sug.values() for c in s["candidatos"]])
        nota = next(n for n in C.painel(self.c)["notas"] if n["id"] == nf)
        self.assertEqual([s["material_id"] for s in nota["sugestoes"]], [MAT, None, None])          # faltando a confirmação
        with self.assertRaisesRegex(S.RegraViolada, "diga quantos UN vem em cada PC"):
            C.confirmar_linhas(self.c, nf, [{"linha_id": l2, "material_id": "CURVA-90-63"}], "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "Linha fora desta nota"):
            C.confirmar_linhas(self.c, nf, [{"linha_id": 99999, "fora_do_estoque": True}], "eng1")
        r = C.confirmar_linhas(self.c, nf, [{"linha_id": l2, "material_id": "CURVA-90-63", "fator": 1}], "eng1")
        self.assertEqual(r, {"confirmadas": 1, "faltam": 1, "por": "eng1"})
        r = C.receber_nota(self.c, nf, "almox1", D2)
        self.assertEqual((r["encerrada"], self.saldo()), (False, (2, 0)))
        C.confirmar_linhas(self.c, nf, [{"linha_id": l3, "material_id": MAT, "fator": 10}], "eng1")
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("ENCERRADA",)])
        self.assertEqual(self.saldo(), (22, 0))
        self.assertEqual(sorted(self.q("SELECT material_id, quantidade FROM nf_itens WHERE nf_id=?", nf)),
                         [("1.2_1.14.27", 2), ("1.2_1.14.27", 20), ("CURVA-90-63", 3)])
        with self.assertRaisesRegex(S.RegraViolada, "Linha já conferida para o estoque"):
            C.confirmar_linhas(self.c, nf, [{"linha_id": l3, "fora_do_estoque": True}], "eng1")
        # a próxima nota do mesmo fornecedor já vem reconhecida, com o fator de antes
        nf2 = self.importar(712, [("X9", "Peça que ninguém conhece", "CX", 1, 3.0)])
        s, = self.sug(nf2).values()
        self.assertEqual((s["material_id"], s["motivo"], s["fator"]), (MAT, "como na nota anterior deste fornecedor", 10.0))
        self.assertEqual(C.receber_nota(self.c, nf2, "almox1", D2)["itens"], 1)

    def test_unidade_diferente_sem_fator_fica_faltando_a_confirmacao(self):
        nf = self.importar(721, [(MAT, "peça em caixa", "CX", 2, 30.0)])
        (l1, _), = self.linhas(nf)
        s = self.sug(nf)[l1]
        self.assertEqual((s["material_id"], s["candidatos"][0]["material_id"]), (None, MAT))     # o material vem marcado
        self.assertTrue(s["motivo"].startswith("unidade diferente"))
        C.receber_nota(self.c, nf, "almox1", D2)
        self.assertEqual(self.saldo(), (0, 0))
        C.confirmar_linhas(self.c, nf, [{"linha_id": l1, "material_id": MAT, "fator": 12}], "eng1")
        self.assertEqual(self.q("SELECT quantidade FROM nf_itens WHERE nf_id=?", nf), [(24,)])

    def test_recusa_com_linha_desconhecida(self):
        nf = self.importar(731, [(MAT, "peça", "UN", 5, 1.0), ("X9", "Peça que ninguém conhece", "UN", 1, 3.0)])
        r = C.receber_nota(self.c, nf, "almox1", D2, recusa="veio material de outra obra")
        self.assertEqual((r["recusado"], r["encerrada"]), (6, True))                     # a desconhecida é recusada junto
        self.assertEqual(self.saldo(), (0, 0))
        nf2 = self.importar(732, [("X9", "Peça que ninguém conhece", "UN", 1, 3.0)])
        r = C.receber_nota(self.c, nf2, "almox1", D2, recusa="não é desta obra")
        self.assertTrue(r["encerrada"])
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf2), [("ENCERRADA",)])
        self.assertEqual(self.q("SELECT recusado,motivo FROM nf_entregas_linhas WHERE linha_id IN (SELECT id FROM nf_linhas WHERE nf_id=?)", nf2), [(1, "não é desta obra")])

    def test_pedidos_antigos_nao_sao_associados_automaticamente(self):
        self.pedido(10)
        for num, qt in [(741, 10), (742, 3), (743, 2)]:
            nf = self.importar(num, [(MAT, "peça", "UN", qt, 10.0)])
            r = C.receber_nota(self.c, nf, "almox1", D2)
            self.assertFalse(r["aguarda_aprovacao"])
            self.assertEqual(self.q("SELECT pedido_id,aprovada_por FROM notas_fiscais WHERE id=?", nf), [(None, None)])
        self.assertEqual(self.saldo(), (15, 0))

    def test_nota_so_de_frete_fecha_no_aceite(self):
        nf = self.importar(751, [("F1", "Frete", "SV", 1, 30.0), ("S1", "SERVIÇO DE DESCARGA", "UN", 1, 9.0)])
        r = C.receber_nota(self.c, nf, "almox1", D2)
        self.assertEqual((r["encerrada"], r["cancelada"], r["itens"]), (True, False, 0))
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("ENCERRADA",)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM recebimentos WHERE nf_id=?", nf), [(0,)])
        self.assertNotIn(nf, [n["id"] for n in C.notas_a_receber(self.c)])


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
        st, r = eng1.post("/api/solicitacao", {"data": D, "frente_id": "Zona01", "itens": [{"material_id": MAT, "quantidade": 10}]})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT solicitante FROM solicitacoes_compra"), [("eng1",)])
        self.assertEqual(eng1.post("/api/solicitacao/decidir", {"solicitacao_id": r["id"], "aprovar": True})[0], 422)   # própria
        self.assertEqual(almox.post("/api/solicitacao/decidir", {"solicitacao_id": r["id"], "aprovar": True})[0], 403)  # perfil
        self.assertEqual(eng2.post("/api/solicitacao/decidir", {"solicitacao_id": r["id"], "aprovar": True})[0], 200)
        import server
        self.assertNotIn("/api/pedido", server.POST)
        st, n = almox.post("/api/nf/importar-xml", {"conteudo_b64": NT.b64(NT.xml(901, [("L", "Luva", "UN", 10, 2.0)])), "nome": "n.xml"})
        self.assertEqual(st, 200, n)
        lid = self.q("SELECT id FROM nf_linhas")[0][0]
        # Simula nota conferida no fluxo antigo e entrega em quarentena já existente.
        C.conferir_nf(self.c, n["nf_id"], None, [{"linha_id": lid, "material_id": MAT}], "eng1")
        ni = self.q("SELECT id FROM nf_itens")[0][0]
        rec = {"nf_id": n["nf_id"], "data": D2, "itens": [{"nf_item_id": ni, "quantidade": 4}]}
        for _ in range(3):
            self.assertEqual(almox.post("/api/recebimento", rec, cabecalhos={"X-Idem": "rec-1"})[0], 200)
        self.assertEqual(self.q("SELECT COUNT(*), SUM(quantidade) FROM recebimento_itens"), [(1, 4.0)])
        self.assertEqual(self.q("SELECT recebido_por FROM recebimentos"), [("almox1",)])
        # num toque (D-135): o resto da nota, pelo almoxarife; o encarregado não recebe
        self.assertEqual(self.cliente("enc1").post("/api/nf/receber", {"nf_id": n["nf_id"]})[0], 403)
        st, r = almox.post("/api/nf/receber", {"nf_id": n["nf_id"], "data": D2})
        self.assertEqual((st, r["itens"], r["encerrada"]), (200, 1, False), r)               # os 4 da 1ª entrega esperam a inspeção
        self.assertEqual(self.q("SELECT COUNT(*), SUM(quantidade) FROM recebimento_itens"), [(2, 10.0)])


    def test_confirmar_linhas_pela_engenharia(self):
        """D-171: a linha faltando a confirmação é confirmada em Compras e notas por quem recebe (a engenharia, na prática)."""
        C.cadastrar_fornecedor(self.c, NT.CNPJ_FORNECEDOR, "Fornecedor de Teste Ltda", "adm")
        st, n = self.cliente("almox1").post("/api/nf/importar-xml", {"conteudo_b64": NT.b64(NT.xml(902, [("X9", "Peça que ninguém conhece", "UN", 2, 2.0)])), "nome": "n.xml"})
        self.assertEqual(st, 200, n)
        lid = self.q("SELECT id FROM nf_linhas")[0][0]
        corpo = {"nf_id": n["nf_id"], "linhas": [{"linha_id": lid, "material_id": MAT}]}
        self.assertEqual(self.cliente("enc1").post("/api/nf/confirmar-linhas", corpo)[0], 403)
        st, r = self.cliente("eng1").post("/api/nf/confirmar-linhas", corpo)
        self.assertEqual((st, r["faltam"]), (200, 0), r)
        self.assertEqual(self.q("SELECT material_id, fator FROM nf_linhas"), [(MAT, 1.0)])
        st, r = self.cliente("almox1").post("/api/nf/receber", {"nf_id": n["nf_id"], "data": D2})
        self.assertEqual((st, r["encerrada"]), (200, True), r)

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
