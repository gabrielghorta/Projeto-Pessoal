"""Relatório mensal da medição em PDF (relatorio_mensal.py e pdf_simples.py, D-207).

O PDF sai do banco, no formato do RM da Ankara (capítulos do Lago Sul) com o visual do relatório de conexões: capa,
sumário com as páginas, valores iguais aos do pacote no BM REV04, semanas como no modelo, todas as fotos do mês, páginas
em paisagem no cronograma e nos gráficos, e PENDENTE no que o sistema ainda não guarda. Sobre a base real (BM REV04)."""
import io
import os
import sys
import unittest

from pypdf import PdfReader

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import apropriacao as AP  # noqa: E402
import fotos_teste as FT  # noqa: E402
import pacote_medicao as PM  # noqa: E402
import pdf_simples as P  # noqa: E402
import relatorio_mensal as RM  # noqa: E402
import servicos as S  # noqa: E402
from test_pacote_medicao import TRS, BasePacote  # noqa: E402


class TestSemanas(unittest.TestCase):
    def test_semanas_como_no_modelo(self):
        # Lago Sul, agosto/2026: a 1ª semana leva os dias antes da 1ª segunda-feira; a última tem um dia
        self.assertEqual(RM.semanas("2026-08-01", "2026-08-31"),
                         [("2026-08-01", "2026-08-09"), ("2026-08-10", "2026-08-16"), ("2026-08-17", "2026-08-23"),
                          ("2026-08-24", "2026-08-30"), ("2026-08-31", "2026-08-31")])
        self.assertEqual(RM.semanas("2026-10-01", "2026-10-31")[0], ("2026-10-01", "2026-10-11"))
        self.assertEqual(RM.semanas("2026-10-05", "2026-10-15"), [("2026-10-05", "2026-10-11"), ("2026-10-12", "2026-10-15")])


class TestPdfSimples(unittest.TestCase):
    def test_paragrafo_tabela_quebra_de_pagina_e_rodape(self):
        doc = P.Documento("teste")

        def moldura(d, p):
            d.ret(p, 20, 20, p.largura - 40, p.altura - 40, borda="8B3430")
            return 50, 60, p.largura - 50, p.altura - 60

        fl = P.Fluxo(doc, moldura, lambda d, p, i, n: d.texto(p, 40, p.altura - 30, f"Página {i} | {n}", 8))
        fl.titulo(1, "Apresentação")
        fl.paragrafo([("Ação, ê, ç, ã, õ, m² e m³ – ", {}), ("PENDENTE", {"negrito": True, "fundo": "FFFF00"})], marcador=True)
        fl.tabela([0.2, 0.8], [["A", "B"]] + [[str(i), "linha " * (i % 5 + 1)] for i in range(90)])
        fl.titulo(1, "Paisagem", paisagem=True)
        fl.fechar()
        r = PdfReader(io.BytesIO(doc.salvar()))
        self.assertGreaterEqual(len(r.pages), 3)
        textos = [p.extract_text() for p in r.pages]
        self.assertIn("Ação, ê, ç, ã, õ, m² e m³", textos[0])
        self.assertEqual(textos[1].count("A B") + textos[1].count("AB"), 1)          # cabeçalho repetido na página 2
        self.assertTrue(all(f"Página {i} | {len(r.pages)}" in t for i, t in enumerate(textos, 1)))
        w, h = r.pages[-1].mediabox.width, r.pages[-1].mediabox.height
        self.assertGreater(w, h)
        self.assertEqual([t[:2] for t in fl.titulos], [(1, "1"), (1, "2")])


class TestRelatorioMensal(BasePacote):
    def setUp(self):
        super().setUp()
        self.docs = os.path.join(self.dados, "documentos")

    def apropriar_canteiro(self):
        corpo = dict(item_ref=AP.item(self.c, "1.2_5.1.1")["ref"], data="2026-10-12", quantidade=1, local_tipo="CANTEIRO",
                     executor_tipo="EQUIPE_OBRA", equipe_id="Zona01", o_que_foi_feito="montagem do portão do canteiro",
                     memoria_calculo="conforme croqui", justificativa="implantação do canteiro",
                     evidencias=[{"nome": "portao.png", "conteudo_b64": FT.png()}])
        with S.transacao(self.c):
            return AP.apropriar(self.c, corpo, "eng1", self.docs)

    def test_pdf_com_capitulos_valores_semanas_e_fotos(self):
        for p in TRS:
            self.executar(p)
        self.apropriar_canteiro()
        nome, pdf, d = RM.gerar(self.c, self.mid, dir_fotos=self.fotos)
        self.assertEqual(nome, "RM_01-2026_MORRO_DA_CRUZ_CT_10239-2026_TESTE_NAO_OFICIAL.pdf")
        r = PdfReader(io.BytesIO(pdf))
        textos = [p.extract_text() for p in r.pages]
        tudo = "\n".join(textos)
        n = len(r.pages)
        self.assertGreaterEqual(n, 20)
        self.assertIn("RELATÓRIO MENSAL", textos[0])
        self.assertIn("CONTRATO 10.239/26", textos[0])
        self.assertIn("2 APRESENTAÇÃO", textos[1])                                    # o sumário é o capítulo 1
        self.assertTrue(all(f"Página {i} | {n}" in t for i, t in enumerate(textos, 1)))
        self.assertTrue(all("MEDIÇÃO DE TESTE – NÃO OFICIAL" in t for t in textos))   # D-56
        # valores iguais aos do pacote no BM (juntada, com a ADM proporcional)
        pac = PM.resumo(self.c, self.mid)["totais"]["juntada"]
        self.assertAlmostEqual(d["totais"]["total"], pac, places=2)
        self.assertIn(RM.rs(pac), tudo)
        self.assertIn("5.8.44", tudo)
        # semanas do modelo e o executado por diâmetro
        self.assertIn("Período de 01/10/2026 até 11/10/2026", tudo)
        self.assertIn("Período de 12/10/2026 até 15/10/2026", tudo)
        ext = sum(S.alvo(self.c, "TRECHO", p)["extensao_m"] for p in TRS)
        self.assertAlmostEqual(sum(v["mes"] for v in d["por_de"].values()), ext, places=2)
        self.assertIn(f"Assentamento de rede – {RM.br(ext)} m", tudo)
        self.assertIn("montagem do portão do canteiro", tudo)                          # apropriação na semana e no canteiro
        # todas as fotos do mês: 3 por trecho + a da apropriação, 6 por página
        self.assertEqual(len(d["fotos"]), 3 * len(TRS) + 1)
        self.assertTrue(all(f["jpeg"] for f in d["fotos"]))
        self.assertIn(f"FOTO {3 * len(TRS) + 1:02d}", tudo)
        # cronograma e gráficos em paisagem; o que o sistema não guarda sai PENDENTE
        self.assertTrue(any(p.mediabox.width > p.mediabox.height for p in r.pages))
        self.assertIn("PENDENTE", tudo)
        self.assertIn("Gráfico 04", tudo)

    def test_http_baixa_o_pdf_com_permissao_e_auditoria(self):
        self.executar(TRS[0])
        eng = self.cli("eng1")
        st, pdf = eng.get(f"/api/relatorios/mensal?id={self.mid}&formato=pdf")
        self.assertEqual(st, 200)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(PdfReader(io.BytesIO(pdf)).pages), 10)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM auditoria WHERE rota='/api/relatorios/mensal'").fetchone()[0], 1)
        st, _ = self.cli("enc3").get(f"/api/relatorios/mensal?id={self.mid}")      # equipe: sem a tela de relatórios
        self.assertEqual(st, 403)


if __name__ == "__main__":
    unittest.main()
