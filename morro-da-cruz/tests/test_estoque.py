"""Etapa 3 — estoque: reserva, saldo que fica com a equipe, empréstimo autorizado, consumo previsto × confirmado,
estorno sem apagar e baixa teórica fora do saldo físico. Planilhas SINTÉTICAS (perfil TESTE).

Critérios de aceitação do diagnóstico (§5, item 3):
  * saída de 20 → aplica 16, devolve 3, perde 1 (com motivo): almoxarifado 35 → 38, custódia 0, sem segunda baixa;
  * saldo que fica com a equipe passa para o dia seguinte;
  * duas equipes não consomem o mesmo saldo.
Nada aqui gera lançamento de medição ou faturamento.
"""
import os
import sqlite3
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import servicos as S  # noqa: E402
from test_importacao import Base  # noqa: E402

TUBO = "CAESB-PEAD-DE63"
TR001 = "Zona01_PB01_Rede_TR001"
D1, D2 = "2026-10-15", "2026-10-16"


class BaseEstoque(Base):
    def setUp(self):
        super().setUp()
        self.aplicar()
        self.c = self.conectar()

    def saldo(self, m=TUBO):
        return S.saldo_almox(self.c, m)[0]

    def entrada(self, q, m=TUBO, data=D1):
        S.entrada_material(self.c, data, m, q, "ROMANEIO_CAESB", "ROM-1", "almoxarife")

    def lancamentos(self):
        return self.q("SELECT COUNT(*) FROM medicao_lancamentos")[0][0]


class TestCustodiaEDevolucao(BaseEstoque):
    def test_saida_20_aplica_16_devolve_3_perde_1(self):
        self.entrada(55)
        ck = S.checkin(self.c, D1, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 20}])
        self.assertEqual(self.saldo(), 35)
        with self.assertRaisesRegex(S.RegraViolada, "motivo"):
            S.checkout(self.c, ck, [{"material_id": TUBO, "aplicado": 16, "sobra": 3, "perda": 1}])
        S.checkout(self.c, ck, [{"material_id": TUBO, "aplicado": 16, "sobra": 3, "perda": 1, "motivo": "barra trincada"}])
        self.assertEqual(self.saldo(), 38)                                      # sobra volta; aplicado não baixa de novo
        self.assertEqual(S.custodia_equipe(self.c, "Zona01", TUBO), 0)
        self.assertEqual(self.q("SELECT tipo, quantidade FROM movimentos WHERE tipo IN ('APLICADO','SOBRA','PERDA') ORDER BY tipo"),
                         [("APLICADO", 16.0), ("PERDA", 1.0), ("SOBRA", 3.0)])
        self.assertEqual(self.lancamentos(), 0)                                 # estoque não gera medição

    def test_saldo_que_fica_com_a_equipe_passa_para_o_dia_seguinte(self):
        self.entrada(50)
        ck1 = S.checkin(self.c, D1, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 20}])
        with self.assertRaisesRegex(S.RegraViolada, "fechar a custódia"):
            S.checkout(self.c, ck1, [{"material_id": TUBO, "aplicado": 12}])      # 8 sem destino declarado
        S.checkout(self.c, ck1, [{"material_id": TUBO, "aplicado": 12, "fica_com_equipe": 8}])
        self.assertEqual((self.saldo(), S.custodia_equipe(self.c, "Zona01", TUBO)), (30, 8))
        self.assertEqual(self.q("SELECT quantidade FROM custodia_declarada"), [(8.0,)])
        ck2 = S.checkin(self.c, D2, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 5}])
        m = S.checkins_abertos(self.c, D2)[0]["materiais"][0]
        self.assertEqual((m["quantidade"], m["retirado_hoje"], m["trazido"]), (13, 5, 8))
        with self.assertRaisesRegex(S.RegraViolada, "Declare"):
            S.checkout(self.c, ck2, [])                                           # material com a equipe precisa ser declarado
        S.checkout(self.c, ck2, [{"material_id": TUBO, "aplicado": 13}])
        self.assertEqual(S.custodia_equipe(self.c, "Zona01", TUBO), 0)
        self.assertEqual(self.saldo(), 25)


class TestReservas(BaseEstoque):
    def test_duas_equipes_nao_consomem_o_mesmo_saldo(self):
        self.entrada(30)
        S.reservar(self.c, D1, "Zona01", TUBO, 25, "TRECHO", TR001, "programação")
        self.assertEqual((self.saldo(), S.disponivel(self.c, TUBO)), (30, 5))   # reserva não é saída
        with self.assertRaisesRegex(S.RegraViolada, "Disponível insuficiente"):
            S.reservar(self.c, D1, "Zona02", TUBO, 6)
        with self.assertRaisesRegex(S.RegraViolada, "Disponível insuficiente"):
            S.checkin(self.c, D1, "Zona02", "TRECHO", "Zona02_PB04_Rede_TR036", materiais=[{"material_id": TUBO, "quantidade": 10}])
        S.checkin(self.c, D1, "Zona02", "TRECHO", "Zona02_PB04_Rede_TR036", materiais=[{"material_id": TUBO, "quantidade": 5}])
        ck = S.checkin(self.c, D1, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 25}])
        self.assertEqual(self.q("SELECT status, checkin_id FROM reservas"), [("ATENDIDA", ck)])
        self.assertEqual((self.saldo(), S.disponivel(self.c, TUBO)), (0, 0))

    def test_cancelamento_exige_motivo_e_libera_o_disponivel(self):
        self.entrada(10)
        r = S.reservar(self.c, D1, "Zona01", TUBO, 10)
        with self.assertRaises(S.RegraViolada):
            S.cancelar_reserva(self.c, r, "")
        S.cancelar_reserva(self.c, r, "programação alterada")
        self.assertEqual(S.disponivel(self.c, TUBO), 10)
        self.assertEqual(self.q("SELECT status, motivo FROM reservas"), [("CANCELADA", "programação alterada")])

    def test_reserva_para_objeto_retirado_e_recusada(self):
        self.entrada(10)
        self.regerar(trechos=__import__("planilhas_sinteticas").TRECHOS[:2])
        self.aplicar()
        tid = self.q("SELECT id FROM trechos WHERE ponto LIKE '%TR036'")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "retirado"):
            S.reservar(self.c, D1, "Zona02", TUBO, 1, "TRECHO", tid)


class TestEmprestimoEBaixaTeorica(BaseEstoque):
    def test_emprestimo_exige_documento_responsavel_e_autorizacao(self):
        self.entrada(40)
        with self.assertRaisesRegex(S.RegraViolada, "autorização"):
            S.entrada_material(self.c, D1, TUBO, 10, "EMPRESTIMO_OUTRA_OBRA", "OF-12", "almoxarife")
        S.reservar(self.c, D1, "Zona01", TUBO, 35)
        with self.assertRaisesRegex(S.RegraViolada, "Disponível insuficiente"):
            S.entrada_material(self.c, D1, TUBO, 10, "EMPRESTIMO_OUTRA_OBRA", "OF-12", "almoxarife", "Eng. Fulano (OF-12)")
        S.entrada_material(self.c, D1, TUBO, 5, "EMPRESTIMO_OUTRA_OBRA", "OF-12", "almoxarife", "Eng. Fulano (OF-12)")
        self.assertEqual(self.saldo(), 35)
        self.assertEqual(self.q("SELECT responsavel, autorizacao FROM movimentos WHERE tipo='EMPRESTIMO_OUTRA_OBRA'"),
                         [("almoxarife", "Eng. Fulano (OF-12)")])

    def test_baixa_teorica_nao_altera_saldo_fisico(self):
        self.entrada(40)
        with self.assertRaisesRegex(S.RegraViolada, "Baixa teórica"):
            S.entrada_material(self.c, D1, TUBO, 10, "BAIXA_TEORICA")
        self.c.execute("INSERT INTO movimentos(data,material_id,tipo,quantidade,status) VALUES (?,?,'BAIXA_TEORICA',7,'ACEITO')",
                       (D1, TUBO))                                               # registro legado do MVP
        self.assertEqual(self.saldo(), 40)
        est = next(m for m in S.estoque(self.c) if m["id"] == TUBO)
        self.assertEqual((est["saldo_almox"], est["baixa_teorica_legada"]), (40, 7))

    def test_consumo_previsto_x_confirmado(self):
        self.entrada(40)
        ck = S.checkin(self.c, D1, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 12}])
        for t in ("MANHA", "TARDE"):
            S.registrar_clima(self.c, D1, "Zona01", t, "SOL")
        S.apontar(self.c, D1, "Zona01", "TRECHO", TR001, metros_executados=10)
        self.assertEqual(self.saldo(), 28)                                       # apontamento não baixa estoque
        S.checkout(self.c, ck, [{"material_id": TUBO, "aplicado": 8, "sobra": 4}])
        c = next(x for x in S.consumo_previsto_x_confirmado(self.c) if x["material_id"] == TUBO)
        self.assertEqual((c["previsto_apontado"], c["aplicado_confirmado"], c["diferenca"]), (10, 8, -2))


class TestEstorno(BaseEstoque):
    def test_estorno_corrige_sem_apagar(self):
        self.entrada(100)
        mid = self.q("SELECT id FROM movimentos")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "motivo e responsável"):
            S.estornar(self.c, mid, "", "almoxarife")
        S.estornar(self.c, mid, "quantidade digitada errada (era 10)", "almoxarife")
        self.assertEqual(self.saldo(), 0)
        self.assertEqual(self.q("SELECT COUNT(*) FROM movimentos")[0][0], 1)      # o original continua
        with self.assertRaisesRegex(S.RegraViolada, "já estornado"):
            S.estornar(self.c, mid, "de novo", "almoxarife")
        mv = S.movimentos(self.c)[0]
        self.assertEqual((mv["id"], mv["estorno_motivo"]), (mid, "quantidade digitada errada (era 10)"))

    def test_estorno_que_deixaria_saldo_negativo_e_recusado(self):
        self.entrada(30)
        rom = self.q("SELECT id FROM movimentos")[0][0]
        ck = S.checkin(self.c, D1, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 20}])
        with self.assertRaisesRegex(S.RegraViolada, "almoxarifado ficaria negativo"):
            S.estornar(self.c, rom, "teste", "almoxarife")
        S.checkout(self.c, ck, [{"material_id": TUBO, "aplicado": 20}])
        cust = self.q("SELECT id FROM movimentos WHERE tipo='CUSTODIA'")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "custódia da equipe ficaria negativa"):
            S.estornar(self.c, cust, "teste", "almoxarife")
        self.assertEqual(self.q("SELECT COUNT(*) FROM estornos")[0][0], 0)        # recusa não deixa estorno parcial

    def test_entrada_por_nf_nao_e_estornada_aqui(self):
        nf = S.registrar_nf(self.c, "123", "Fornecedor", D1, [{"material_id": "1.2_1.14.27", "quantidade": 5}])
        mid = self.q("SELECT id FROM movimentos WHERE nf_id=?", nf)[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "nota fiscal"):
            S.estornar(self.c, mid, "x", "y")


class TestMigracaoV4(Base):
    def test_v2_com_baixa_teorica_migra_para_v4_sem_perda(self):
        c = sqlite3.connect(self.db)
        with open(os.path.join(AQUI, "fixtures", "schema_v2.sql"), encoding="utf-8") as f:
            c.executescript(f.read())
        c.execute("INSERT INTO schema_versao VALUES (2, 'x', 'v2')")
        c.execute("INSERT INTO materiais(id,descricao,unidade,propriedade) VALUES (?,'tubo','M','CAESB')", (TUBO,))
        c.execute("INSERT INTO movimentos(data,material_id,tipo,quantidade,status) VALUES (?,?,'ROMANEIO_CAESB',50,'ACEITO')", (D1, TUBO))
        c.execute("INSERT INTO movimentos(data,material_id,tipo,quantidade,status) VALUES (?,?,'BAIXA_TEORICA',12,'ACEITO')", (D1, TUBO))
        c.commit()
        c.close()
        rel = self.aplicar()
        self.assertEqual(rel["esquema_depois"], S.VERSAO_ESQUEMA)
        self.assertEqual(self.q("SELECT MAX(versao) FROM schema_versao")[0][0], 4)
        self.assertEqual(self.q("SELECT tipo, quantidade, responsavel FROM movimentos ORDER BY id"),
                         [("ROMANEIO_CAESB", 50.0, None), ("BAIXA_TEORICA", 12.0, None)])   # nada apagado
        self.assertEqual(S.saldo_almox(self.conectar(), TUBO)[0], 50)                       # baixa teórica fora do físico


if __name__ == "__main__":
    unittest.main()
