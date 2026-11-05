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
    LIBERAR_TUDO = True                   # lança execução: a liberação topográfica antes (D-20)

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
        S.apontar(self.c, D1, "Zona01", "TRECHO", TR001, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 10}])
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


# ====================================================================== auditoria de 16/10 (commit fae5818)
class TestSequenciaDosFechamentos(BaseEstoque):
    """Achado 1: o fechamento de um dia não pode consumir material retirado em dia posterior."""

    def test_reproducao_segundo_checkin_com_o_anterior_aberto_e_recusado(self):
        self.entrada(50)
        k1 = S.checkin(self.c, D1, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 20}])
        with self.assertRaisesRegex(S.RegraViolada, "check-in aberto em 2026-10-15"):
            S.checkin(self.c, D2, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 5}])
        with self.assertRaisesRegex(S.RegraViolada, "fechar a custódia"):
            S.checkout(self.c, k1, [{"material_id": TUBO, "aplicado": 25}])          # 25 > 20 retirados até 15/10
        S.checkout(self.c, k1, [{"material_id": TUBO, "aplicado": 20}])
        S.checkin(self.c, D2, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 5}])
        self.assertEqual(self.q("SELECT data, quantidade FROM movimentos WHERE tipo='APLICADO'"), [(D1, 20.0)])

    def test_checkin_retroativo_e_recusado(self):
        self.entrada(50)
        k = S.checkin(self.c, D2, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 10}])
        S.checkout(self.c, k, [{"material_id": TUBO, "aplicado": 4, "fica_com_equipe": 6}])
        with self.assertRaisesRegex(S.RegraViolada, "retroativo"):
            S.checkin(self.c, D1, "Zona01", "TRECHO", TR001)                         # 15/10 depois de 16/10
        S.checkin(self.c, D1, "Zona02", "TRECHO", "Zona02_PB04_Rede_TR036")          # outra equipe: independente

    def test_legado_com_duas_sessoes_abertas_fecha_em_ordem_e_sem_material_futuro(self):
        self.entrada(50)
        k1 = S.checkin(self.c, D1, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 20}])
        # banco legado (antes desta correção): segunda sessão aberta com mais 5 m em 16/10
        k2 = self.c.execute("INSERT INTO checkins(data,equipe_id,alvo_tipo,alvo_id) VALUES (?, 'Zona01', 'TRECHO', ?)",
                            (D2, self.tid(TR001))).lastrowid
        self.c.execute("INSERT INTO movimentos(data,material_id,tipo,quantidade,equipe_id,checkin_id) VALUES (?,?,'CUSTODIA',5,'Zona01',?)",
                       (D2, TUBO, k2))
        m1 = S.checkins_abertos(self.c, D1)[0]["materiais"][0]
        self.assertEqual((m1["quantidade"], m1["trazido"]), (20, 0))                    # não mostra os 5 m de 16/10
        with self.assertRaisesRegex(S.RegraViolada, "Feche antes o check-in de 2026-10-15"):
            S.checkout(self.c, k2, [{"material_id": TUBO, "aplicado": 25}])
        with self.assertRaisesRegex(S.RegraViolada, "fechar a custódia da equipe \\(20\\)"):
            S.checkout(self.c, k1, [{"material_id": TUBO, "aplicado": 25}])
        S.checkout(self.c, k1, [{"material_id": TUBO, "aplicado": 20}])
        S.checkout(self.c, k2, [{"material_id": TUBO, "aplicado": 5}])
        self.assertEqual(self.q("SELECT data, quantidade FROM movimentos WHERE tipo='APLICADO' ORDER BY id"),
                         [(D1, 20.0), (D2, 5.0)])


class TestEstornoComReservas(BaseEstoque):
    """Achado 2: estorno não pode deixar reserva ativa sem cobertura."""

    def test_reproducao_estorno_da_entrada_com_reserva_e_recusado_sem_efeito(self):
        self.entrada(100)
        r = S.reservar(self.c, D2, "Zona01", TUBO, 80)
        mid = self.q("SELECT id FROM movimentos")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "reservas ativas sem cobertura"):
            S.estornar(self.c, mid, "entrada lançada em duplicidade", "almoxarife")
        self.assertEqual(self.q("SELECT COUNT(*) FROM estornos")[0][0], 0)                 # transação desfeita
        self.assertEqual(self.q("SELECT status, quantidade FROM reservas WHERE id=?", r), [("ATIVA", 80.0)])
        self.assertEqual((self.saldo(), S.disponivel(self.c, TUBO)), (100, 20))

    def test_estorno_com_ajuste_explicito_reduz_as_reservas_mais_recentes(self):
        self.entrada(100)
        self.entrada(30)
        r1 = S.reservar(self.c, D2, "Zona01", TUBO, 60)
        r2 = S.reservar(self.c, D2, "Zona02", TUBO, 50)
        mid = self.q("SELECT id FROM movimentos ORDER BY id")[0][0]                       # estorna a entrada de 100
        S.estornar(self.c, mid, "entrada lançada em duplicidade", "almoxarife", ajustar_reservas=True)
        self.assertEqual((self.saldo(), S.disponivel(self.c, TUBO)), (30, 0))              # nunca negativo
        self.assertEqual(self.q("SELECT id, status, quantidade FROM reservas ORDER BY id"),
                         [(r1, "ATIVA", 30.0), (r2, "CANCELADA", 50.0)])
        self.assertEqual(self.q("SELECT reserva_id, de, para, movimento_id FROM reserva_ajustes ORDER BY id"),
                         [(r2, 50.0, 0.0, mid), (r1, 60.0, 30.0, mid)])


class TestRetificacaoDoFechamento(BaseEstoque):
    """Achado 3: corrigir aplicação depois do check-out sem simular nova visita e sem apagar o histórico."""

    def _fechado(self):
        self.entrada(50)
        k = S.checkin(self.c, D1, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 20}])
        S.checkout(self.c, k, [{"material_id": TUBO, "aplicado": 20}])
        return k, self.q("SELECT id FROM movimentos WHERE tipo='APLICADO'")[0][0]

    def test_estorno_simples_do_fechamento_aponta_para_a_retificacao(self):
        _, ap = self._fechado()
        with self.assertRaisesRegex(S.RegraViolada, "retificação do fechamento"):
            S.estornar(self.c, ap, "aplicou 15", "almoxarife")

    def test_retificacao_redistribui_no_mesmo_dia_e_preserva_o_historico(self):
        k, ap = self._fechado()
        with self.assertRaisesRegex(S.RegraViolada, "mesma quantidade"):
            S.retificar_fechamento(self.c, ap, {"aplicado": 15}, "contagem", "encarregado")
        rid = S.retificar_fechamento(self.c, ap, {"aplicado": 15, "sobra": 2, "fica_com_equipe": 3},
                                     "aplicou 15; 2 devolvidos; 3 ficaram", "encarregado")
        self.assertEqual(self.q("SELECT encerrado FROM checkins WHERE id=?", k), [(1,)])           # não reabre
        self.assertTrue(self.q("SELECT motivo FROM estornos WHERE movimento_id=?", ap)[0][0].startswith(f"retificação #{rid}:"))
        self.assertEqual(self.q("SELECT tipo, quantidade, data, checkin_id, retificacao_id FROM movimentos "
                                "WHERE retificacao_id IS NOT NULL ORDER BY tipo"),
                         [("APLICADO", 15.0, D1, k, rid), ("SOBRA", 2.0, D1, k, rid)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM movimentos WHERE id=?", ap), [(1,)])           # original preservado
        self.assertEqual((self.saldo(), S.custodia_equipe(self.c, "Zona01", TUBO)), (32, 3))
        self.assertEqual(self.q("SELECT quantidade FROM custodia_declarada WHERE checkin_id=?", k), [(3.0,)])
        k2 = S.checkin(self.c, D2, "Zona01", "TRECHO", TR001)                                      # os 3 voltam como trazidos
        self.assertEqual(S.checkins_abertos(self.c, D2)[0]["materiais"][0]["trazido"], 3)
        S.checkout(self.c, k2, [{"material_id": TUBO, "aplicado": 3}])
        with self.assertRaisesRegex(S.RegraViolada, "já estornado"):
            S.retificar_fechamento(self.c, ap, {"aplicado": 20}, "de novo", "encarregado")

    def test_retificacao_nao_deixa_reserva_descoberta(self):
        self.entrada(50)
        k = S.checkin(self.c, D1, "Zona01", "TRECHO", TR001, materiais=[{"material_id": TUBO, "quantidade": 20}])
        S.checkout(self.c, k, [{"material_id": TUBO, "aplicado": 10, "sobra": 10}])
        S.reservar(self.c, D2, "Zona02", TUBO, 40)                                                 # disponível 0
        so = self.q("SELECT id FROM movimentos WHERE tipo='SOBRA'")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "sem cobertura"):
            S.retificar_fechamento(self.c, so, {"aplicado": 10}, "não houve sobra", "encarregado")
        self.assertEqual(self.q("SELECT COUNT(*) FROM retificacoes")[0][0], 0)
        S.retificar_fechamento(self.c, so, {"aplicado": 10}, "não houve sobra", "encarregado", ajustar_reservas=True)
        self.assertEqual(S.disponivel(self.c, TUBO), 0)
        self.assertEqual(self.q("SELECT quantidade FROM reservas"), [(30.0,)])


class TestMigracaoEstoque(Base):
    def test_v2_com_baixa_teorica_migra_para_o_esquema_atual_sem_perda(self):
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
        self.assertEqual(self.q("SELECT MAX(versao) FROM schema_versao")[0][0], S.VERSAO_ESQUEMA)
        self.assertEqual(self.q("SELECT tipo, quantidade, responsavel FROM movimentos ORDER BY id"),
                         [("ROMANEIO_CAESB", 50.0, None), ("BAIXA_TEORICA", 12.0, None)])   # nada apagado
        self.assertEqual(S.saldo_almox(self.conectar(), TUBO)[0], 50)                       # baixa teórica fora do físico


if __name__ == "__main__":
    unittest.main()
