"""Teste ponta a ponta na Zona01 sobre o banco carregado das planilhas oficiais.

Usa uma cópia de dados/morro_da_cruz.db (rode `python seed.py` antes). TR001, NÓ1.8 e DF-33.
"""
import os
import shutil
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
import regras as R  # noqa: E402
import servicos as S  # noqa: E402

DB = os.path.join(AQUI, "dados", "morro_da_cruz.db")
TR = "Zona01_PB01_Rede_TR001"
NO18 = "Zona01_PB01_Rede_NÓ1.8"
DF33_CH = "Zona01_PB01_CH_DF-33"
DF33_REDE = "Zona01_PB01_Rede_DF-33"
FOTO = "aGVsbG8="   # conteúdo irrelevante para a regra


@unittest.skipUnless(os.path.exists(DB), "banco não carregado — rode python seed.py")
class FluxoZona01(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        db = os.path.join(cls.tmp, "t.db")
        shutil.copy(DB, db)
        cls.c = S.conectar(db)
        cls.fotos = os.path.join(cls.tmp, "fotos")
        cls.m1 = S.criar_medicao(cls.c, 1, "2026-10-01", "2026-10-31")
        cls.c.execute("INSERT INTO funcionarios(nome,funcao,equipe_id) VALUES ('Encarregado A','Encarregado','Zona01')")
        cls.c.execute("INSERT INTO maquinas(descricao,equipe_id) VALUES ('Retroescavadeira','Zona01')")

    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        shutil.rmtree(cls.tmp)

    def foto(self, tipo, alvo, cat):
        S.registrar_foto(self.c, tipo, alvo, cat, FOTO, data_hora="2026-10-15T10:00:00", lat=-15.9085, lon=-47.7689,
                         dir_fotos=self.fotos)

    def test_1_trecho_tr001_ponta_a_ponta(self):
        c, d = self.c, "2026-10-15"
        t = S.alvo(c, "TRECHO", TR)
        self.assertEqual((t["extensao_m"], t["de_mm"], t["codigo_bm"]), (76.55, 63, "5.8.44"))

        # almoxarifado: tubo Caesb retirado por romaneio
        S.entrada_material(c, d, "CAESB-PEAD-DE63", 100, "ROMANEIO_CAESB", "Romaneio 001")
        with self.assertRaisesRegex(R.RegraViolada, "Trecho/Nó"):
            S.checkin(c, d, "Zona01")
        ck = S.checkin(c, d, "Zona01", "TRECHO", TR, funcionarios=[1], maquinas=[1],
                       materiais=[{"material_id": "CAESB-PEAD-DE63", "quantidade": 80}])
        self.assertEqual(S.saldo_almox(c, "CAESB-PEAD-DE63")[0], 20)
        pins = S.estado_mapa(c, self.m1, d)["pins"]
        self.assertIn({"equipe": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR, "checkin": ck}, pins)
        self.assertEqual(S.histograma(c, d, d)[0]["funcionarios"], 1)

        # campo: clima obrigatório nos dois turnos
        with self.assertRaisesRegex(R.RegraViolada, "Clima"):
            S.apontar(c, d, "Zona01", "TRECHO", TR, 40, 30)
        S.registrar_clima(c, d, "Zona01", "MANHA", "SOL")
        S.registrar_clima(c, d, "Zona01", "TARDE", "CHUVA_FRACA_TENDA")

        prev = {q["servico"]: q for q in S.previsto(c, "TRECHO", TR, 40)}
        self.assertEqual(prev["SOLDA"]["previsto"], 7)            # ⌈40 / 6⌉
        self.assertEqual(prev["ASSENTAMENTO"]["previsto"], 40)
        self.assertAlmostEqual(prev["REATERRO"]["previsto"], 44.78175 * 40 / 76.55, places=3)

        S.apontar(c, d, "Zona01", "TRECHO", TR, 40, 30)           # [OK, Confirmar Previsto]
        self.assertEqual(S.estado_mapa(c, self.m1)["status"][TR], "EM_EXECUCAO")
        S.apontar(c, d, "Zona01", "TRECHO", TR, concluido_100=True,
                  quantidades=[{"servico": "SOLDA", "unidade": "UN", "confirmado": 6}])   # editado: 6 soldas reais

        # OK Fiscalização só com 3 fotos
        with self.assertRaisesRegex(R.RegraViolada, "fotos"):
            S.ok_fiscalizacao(c, "TRECHO", TR, "eng", d)
        for cat in ("SINALIZACAO", "EXECUCAO", "CONCLUIDO"):
            self.foto("TRECHO", TR, cat)
        self.assertEqual(S.estado_mapa(c, self.m1)["status"][TR], "CONCLUIDO_MES")

        S.checkout(c, ck, [{"material_id": "CAESB-PEAD-DE63", "aplicado": 76.55, "sobra": 3.45}])
        self.assertAlmostEqual(S.saldo_almox(c, "CAESB-PEAD-DE63")[0], 23.45)
        compat = {x["material_id"]: x for x in S.compatibilizacao_caesb(c)}["CAESB-PEAD-DE63"]
        self.assertEqual((compat["retirado"], compat["aplicado"]), (100, 76.55))

        S.ok_fiscalizacao(c, "TRECHO", TR, "eng", d)
        self.assertEqual(S.estado_mapa(c, self.m1)["status"][TR], "OK_FISCAL")
        r = S.resumo_medicao(c, self.m1)
        lanc = {l["servico"]: l for l in r["gavetas"][1]["lancamentos"]}
        self.assertEqual(lanc["ASSENTAMENTO"]["item"], "2.2_5.8.44")
        self.assertAlmostEqual(lanc["ASSENTAMENTO"]["quantidade"], 76.55)
        self.assertAlmostEqual(lanc["ASSENTAMENTO"]["valor"], 62.35, places=2)
        self.assertEqual(lanc["SOLDA"]["quantidade"], 6 + 7)                 # 1º dia previsto 7, 2º dia editado 6
        self.assertIsNone(lanc["SOLDA"]["bm_item_id"])                       # item a confirmar: não some, fica sinalizado
        self.assertNotIn("CADASTRO", lanc)
        self.assertEqual(r["indice_reajuste"], 0.0329)
        self.assertEqual(S.esteira(c)[0]["trecho_id"], TR)

        # esteira GDOC: negado → reenviado (Rev. 1) → aprovado → gaveta 3
        S.avancar_cadastro(c, TR, "2_ENVIADO", {"empresa": "Cadastro X", "data_envio": "2026-10-16"})
        S.avancar_cadastro(c, TR, "3_RECEBIDO", {"arquivos": ["TR001.dwg"]})
        S.avancar_cadastro(c, TR, "4_GDOC_ANALISE", {"protocolo_gdoc": "GDOC 111"})
        S.avancar_cadastro(c, TR, "5A_NEGADO", {"motivo_negativa": "cota de fundo divergente"})
        S.avancar_cadastro(c, TR, "2_ENVIADO")
        self.assertEqual(S.esteira(c)[0]["rotulo"], "2. Em Produção (Rev. 1)")
        S.avancar_cadastro(c, TR, "3_RECEBIDO", {"arquivos": ["TR001_rev1.dwg"]})
        S.avancar_cadastro(c, TR, "4_GDOC_ANALISE", {"protocolo_gdoc": "GDOC 222"})
        S.avancar_cadastro(c, TR, "6_APROVADO", {"memorando_eset": "ESET 9"}, data=d)
        cad = S.resumo_medicao(c, self.m1)["gavetas"][3]["lancamentos"][0]
        self.assertEqual((cad["item"], cad["quantidade"]), ("2.2_5.2.1", 76.55))

        # recomposição só com checkbox próprio (gaveta 4)
        S.recomposicao_ok(c, "TRECHO", TR, "CALÇADA", 12.5, d)
        self.assertEqual(len(S.resumo_medicao(c, self.m1)["gavetas"][4]["lancamentos"]), 1)

    def test_2_no18_herda_sinalizacao_e_exige_quantidades_da_062(self):
        c = self.c
        self.assertIn(TR, S.trechos_do_conjunto(c, NO18))
        sem_q = S.totais_conjunto(c, NO18)["sem_quantidade"]
        if sem_q:
            with self.assertRaisesRegex(R.RegraViolada, "06.2"):
                S.previsto(c, "CONJUNTO", NO18, 0)
        # depois do teste 1 o TR001 tem foto de sinalização → o nó pede só 2 fotos
        self.assertEqual(S.fotos_faltando(c, "CONJUNTO", NO18), ["EXECUCAO", "CONCLUIDO"])

    def test_3_df33_dois_conjuntos_e_contador_por_unidade(self):
        c = self.c
        self.assertEqual(S.alvo(c, "CONJUNTO", DF33_CH)["frente_id"], "CH")
        self.assertEqual(S.alvo(c, "CONJUNTO", DF33_REDE)["frente_id"], "Zona01")
        t = S.totais_conjunto(c, DF33_CH)
        self.assertEqual(t["linhas"], 18)
        if t["sem_quantidade"] == 0:
            self.assertEqual(t["texto"], "17 UN · 0,71 m")
        else:
            self.assertIn("sem quantidade", t["texto"])
            self.assertNotIn("0 UN", t["texto"])        # pendente nunca vira zero

    def test_4_sem_posicao_e_nf_80(self):
        c = self.c
        self.assertEqual([e["numero"] for e in S.estado_mapa(c, self.m1)["sem_posicao"]], ["MV-11", "VTF-12", "VTF-16"])
        mat = c.execute("SELECT * FROM materiais WHERE propriedade='ANKARA' AND unidade='UN' LIMIT 1").fetchone()
        nf = S.registrar_nf(c, "123", "Fornecedor", "2026-10-10", [{"material_id": mat["id"], "quantidade": 10,
                                                                    "valor_unitario": 1}], faturamento_etapas=True)
        self.assertEqual(S.saldo_almox(c, mat["id"]), (0, 10))               # em quarentena
        S.aceitar_nf(c, nf, "laudo.pdf")
        self.assertEqual(S.saldo_almox(c, mat["id"])[0], 10)
        l = S.resumo_medicao(c, self.m1)["gavetas"][2]["lancamentos"][-1]
        b = c.execute("SELECT * FROM bm_itens WHERE id=?", (mat["bm_item_id"],)).fetchone()
        esperado = R.valor_bm(10, b["preco_unitario"], "MATERIAL", 0.1528, 0.2148, -0.1404) * 0.8
        self.assertAlmostEqual(l["valor"], esperado, places=1)

    def test_5_medicao_janeiro_2027_reajuste_pendente(self):
        m4 = S.criar_medicao(self.c, 4, "2027-01-01", "2027-01-31")
        r = S.resumo_medicao(self.c, m4)
        self.assertIsNone(r["indice_reajuste"])
        self.assertIn("sem índice", r["aviso_reajuste"])


if __name__ == "__main__":
    unittest.main()
