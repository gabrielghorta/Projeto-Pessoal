"""Documentos oficiais (v14) — catálogo de links do Google Drive: validação do link, cadastro sem apagar nada, importação
da planilha-índice (prévia e aplicação), leitura pelo link da planilha e, pelo HTTP, permissão, autoria e auditoria."""
import os
import sys
import tempfile
import unittest
import urllib.error

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import documentos as D  # noqa: E402
import importacao as I  # noqa: E402
import servicos as S  # noqa: E402
from test_acesso import BaseHTTP  # noqa: E402

ARQ = "https://drive.google.com/file/d/1Arquivo061Ficticio0000000000000/view?usp=drivesdk"
ARQ2 = "https://drive.google.com/file/d/1Arquivo062Ficticio0000000000000/view?usp=drivesdk"
PASTA = "https://drive.google.com/drive/folders/1PastaDaObraFicticia00000000000?usp=drive_link"
PLANILHA = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit#gid=42"
INDICE = ("nome antigo;nome novo;pasta;tipo;revisão;data;link;observação\n"
          "06.1 - LEV_DMC_MORRO_DA_CRUZ_REDES_REV01_13-10-26.xlsx;"
          "Morro da Cruz - Levantamento de Quantitativos das Redes - Rev 01 - 2026-10-13 (06.1).xlsx;"
          f"01_DOCUMENTOS_OFICIAIS / 03_Quantitativos;XLSX;Rev 01;2026-10-13;{ARQ};\n"
          "06.2 - LEV_DMC_MORRO_DA_CRUZ_CONEXÕES_REV08_13-10-26.xlsm;"
          "Morro da Cruz - Levantamento de Conexões e Peças por Nó - Rev 08 - 2026-10-13 (06.2).xlsm;"
          f"01_DOCUMENTOS_OFICIAIS / 03_Quantitativos;;Rev 08;13/10/2026;{ARQ2};tem macros\n"
          "sem link;Documento sem link;01_DOCUMENTOS_OFICIAIS;PDF;;;;\n"
          f"repetido;Repetido;01_DOCUMENTOS_OFICIAIS;PDF;;;{ARQ};\n")


class BaseDoc(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = S.conectar(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def n(self, onde="1=1"):
        return self.c.execute(f"SELECT COUNT(*) FROM documentos_obra WHERE {onde}").fetchone()[0]


class TestLinkECampos(unittest.TestCase):
    def test_so_aceita_link_https_do_google_drive(self):
        self.assertEqual(D.analisar_link(ARQ)["drive_id"], "1Arquivo061Ficticio0000000000000")
        self.assertEqual(D.analisar_link(PASTA)["google"], "folders")
        self.assertEqual(D.analisar_link("https://drive.google.com/open?id=1Arquivo061Ficticio0000000000000")["google"], "file")
        self.assertEqual(D.analisar_link(PLANILHA)["google"], "spreadsheets")
        for ruim in ("http://drive.google.com/file/d/1Arquivo061Ficticio0000000000000/view", "https://drive.google.com.evil.com/x",
                     "javascript:alert(1)", "https://exemplo.com/arquivo.pdf", ""):
            with self.assertRaisesRegex(S.RegraViolada, "link do Google Drive"):
                D.analisar_link(ruim)

    def test_download_direto_por_tipo_de_item(self):
        self.assertEqual(D.link_baixar(ARQ), "https://drive.google.com/uc?export=download&id=1Arquivo061Ficticio0000000000000")
        self.assertTrue(D.link_baixar(PLANILHA).endswith("/export?format=xlsx"))
        self.assertIsNone(D.link_baixar(PASTA))

    def test_data_codigo_e_rotulo_da_pasta(self):
        self.assertEqual([D.data_iso(x) for x in ("2026-10-13", "13/10/2026", "13-10-26", "2026-10-13 00:00:00", "")],
                         ["2026-10-13"] * 4 + [None])
        with self.assertRaisesRegex(S.RegraViolada, "Data"):
            D.data_iso("31/02/2026")
        self.assertEqual(D.codigo_do_titulo("Morro da Cruz - Projeto - Rev 03 (A.RED.SSB-D014.V03.T01).pdf"), "A.RED.SSB-D014.V03.T01")
        self.assertEqual(D.pasta_rotulo("01_DOCUMENTOS_OFICIAIS / 02_Projeto_Executivo/01_Pranchas_PDF"),
                         "Documentos oficiais / Projeto Executivo / Pranchas PDF")
        self.assertEqual(D.pasta_rotulo("06_REFERENCIA_OUTRAS_OBRAS / 04_Medicao/02_Memorias_de_Calculo"),
                         "Referência outras obras / Medição / Memórias de Cálculo")
        self.assertEqual(D.tipo_do_arquivo("Contrato.pdf", ARQ), "PDF")
        self.assertEqual(D.tipo_do_arquivo("Índice", PLANILHA), "PLANILHA GOOGLE")


class TestCatalogo(BaseDoc):
    def test_cadastrar_alterar_e_retirar_sem_apagar(self):
        did = D.cadastrar(self.c, {"titulo": "Morro da Cruz - Contrato Caesb x Ankara.pdf", "pasta": "01_DOCUMENTOS_OFICIAIS",
                                   "link": ARQ}, "eng1")
        d = self.c.execute("SELECT * FROM documentos_obra WHERE id=?", (did,)).fetchone()
        self.assertEqual((d["tipo"], d["origem"], d["criado_por"]), ("PDF", "MANUAL", "eng1"))
        with self.assertRaisesRegex(S.RegraViolada, "já está na lista"):
            D.cadastrar(self.c, {"titulo": "Outro nome", "pasta": "X", "link": ARQ + "&x=1"}, "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "pasta"):
            D.cadastrar(self.c, {"titulo": "Sem pasta", "link": ARQ2}, "eng1")
        D.alterar(self.c, did, {"revisao": "Rev 01", "data_documento": "13/10/2026"}, "eng2")
        d = self.c.execute("SELECT * FROM documentos_obra WHERE id=?", (did,)).fetchone()
        self.assertEqual((d["revisao"], d["data_documento"], d["alterado_por"], d["criado_por"]), ("Rev 01", "2026-10-13", "eng2", "eng1"))
        with self.assertRaisesRegex(S.RegraViolada, "por que"):
            D.retirar(self.c, did, "eng1", "")
        D.retirar(self.c, did, "eng1", "substituído pela revisão 02")
        self.assertEqual((self.n(), self.n("ativo=1")), (1, 0))                     # nada é apagado
        D.cadastrar(self.c, {"titulo": "Contrato (nova cópia).pdf", "pasta": "01_DOCUMENTOS_OFICIAIS", "link": ARQ}, "eng1")
        self.assertEqual(D.listar(self.c)["total"], 1)


class TestIndice(BaseDoc):
    def test_previa_nao_grava_e_aplicacao_atualiza_sem_retirar_quem_saiu(self):
        r = D.importar_indice(self.c, INDICE, "eng1", simular=True)
        self.assertEqual((r["linhas"], r["novos"], r["atualizados"], self.n()), (4, 2, 0, 0))
        self.assertEqual([(i["linha"], "link" in i["motivo"] or "mesmo arquivo" in i["motivo"]) for i in r["ignorados"]],
                         [(4, True), (5, True)])
        r = D.importar_indice(self.c, INDICE, "eng1")
        self.assertEqual((r["novos"], self.n("origem='INDICE'")), (2, 2))
        d = self.c.execute("SELECT * FROM documentos_obra WHERE drive_id=?", ("1Arquivo062Ficticio0000000000000",)).fetchone()
        self.assertEqual((d["tipo"], d["codigo"], d["data_documento"], d["nome_anterior"][:4], d["descricao"]),
                         ("XLSM", "06.2", "2026-10-13", "06.2", "tem macros"))
        so_um = INDICE.splitlines()[0] + "\n" + INDICE.splitlines()[1].replace("Rev 01;2026", "Rev 02;2026") + "\n"
        r = D.importar_indice(self.c, so_um.replace(";", ","), "eng2")     # vírgula também serve
        self.assertEqual((r["novos"], r["atualizados"], r["fora_do_indice"]), (0, 1, 1))
        self.assertEqual(self.n("ativo=1"), 2)                              # quem saiu do índice continua na lista
        self.assertEqual(self.c.execute("SELECT revisao, alterado_por FROM documentos_obra WHERE drive_id=?",
                                        ("1Arquivo061Ficticio0000000000000",)).fetchone()[:], ("Rev 02", "eng2"))
        self.assertEqual(D.obter_config(self.c)["ultima_importacao"]["atualizados"], 1)

    def test_colunas_obrigatorias(self):
        with self.assertRaisesRegex(S.RegraViolada, "link"):
            D.importar_indice(self.c, "nome novo;pasta\nX;Y\n", "eng1")
        with self.assertRaisesRegex(S.RegraViolada, "vazio"):
            D.importar_indice(self.c, "﻿  ", "eng1")

    def test_link_da_planilha_vira_csv_e_redirecionamento_so_para_o_google(self):
        self.assertEqual(D.url_csv_do_indice(PLANILHA),
                         "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/export?format=csv&gid=42")
        self.assertIn("/pub?output=csv", D.url_csv_do_indice("https://docs.google.com/spreadsheets/d/e/2PACX-1vAbCdEfGhIjKl/pubhtml"))
        with self.assertRaisesRegex(S.RegraViolada, "planilha Google"):
            D.url_csv_do_indice("https://drive.google.com/file/d/1Arquivo061Ficticio0000000000000/view")
        h = D._SoGoogle()
        with self.assertRaises(urllib.error.HTTPError):
            h.redirect_request(None, None, 302, "Found", {}, "https://evil.example.com/x.csv")

    def test_sincronizar_pelo_link_salvo(self):
        with self.assertRaisesRegex(S.RegraViolada, "link da planilha"):
            D.sincronizar(self.c, "eng1", baixar=lambda u: INDICE)
        with self.assertRaisesRegex(S.RegraViolada, "pasta do Drive"):
            D.salvar_config(self.c, ARQ, "", "eng1")
        D.salvar_config(self.c, PASTA, PLANILHA, "eng1")
        pedidos = []
        r = D.sincronizar(self.c, "eng1", simular=True, baixar=lambda u: pedidos.append(u) or INDICE)
        self.assertEqual((r["novos"], self.n(), pedidos[0][-6:]), (2, 0, "gid=42"))
        self.assertEqual(D.obter_config(self.c)["pasta_url"], PASTA)

    def test_migracao_v14_so_acrescenta_a_tabela(self):
        self.c.execute("DROP TABLE documentos_obra")
        I.preparar_v14(self.c)
        self.assertEqual(self.n(), 0)


class TestIndiceGrande(BaseDoc):
    def test_indice_inteiro_da_pasta_e_pastas_de_trabalho(self):
        linhas = ["nome antigo,nome novo,pasta,tipo,revisão,data,link,observação"]
        for i in range(6500):                 # o índice real tem 6.690 linhas
            pasta = "99_TEMPORARIOS_E_SISTEMA/Pastas_de_Trabalho_IA/cache" if i % 2 else "01_DOCUMENTOS_OFICIAIS/03_Quantitativos"
            linhas.append(f"a{i}.pdf,Documento {i}.pdf,{pasta},Planilha de Quantitativos,,,https://drive.google.com/file/d/1Arquivo{i:08d}xx/view,")
        texto = "\n".join(linhas)
        r = D.importar_indice(self.c, texto, "eng1", simular=True)
        self.assertEqual((r["linhas"], r["novos"], r["pastas_de_trabalho"]), (6500, 3250, {"99_TEMPORARIOS_E_SISTEMA": 3250}))
        r = D.importar_indice(self.c, texto, "eng1", incluir_trabalho=True)
        self.assertEqual((r["novos"], self.n("ativo=1")), (6500, 6500))
        d = D.listar(self.c)["documentos"][0]
        self.assertEqual((d["tipo"], d["formato"]), ("Planilha de Quantitativos", "PDF"))   # tipo do documento, como veio


class TestDocumentosHTTP(BaseHTTP):
    def test_permissao_autoria_e_auditoria(self):
        eng, alm = self.cliente("eng1"), self.cliente("almox1")
        corpo = {"titulo": "Morro da Cruz - Projeto Executivo - Rev 03 (A.RED.SSB-D014.V03.T01).pdf",
                 "pasta": "01_DOCUMENTOS_OFICIAIS / 02_Projeto_Executivo", "link": ARQ, "por": "outra.pessoa"}
        self.assertEqual(alm.post("/api/documento", corpo)[0], 403)
        st, r = eng.post("/api/documento", corpo)
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT criado_por, codigo FROM documentos_obra WHERE id=?", r["id"]),
                         [("eng1", "A.RED.SSB-D014.V03.T01")])
        self.assertEqual(alm.get("/api/documentos")[0], 403)       # consultar: só quem abre Usuários e histórico
        st, lista = eng.get("/api/documentos")
        self.assertEqual((st, lista["total"], lista["documentos"][0]["pasta_rotulo"]), (200, 1, "Documentos oficiais / Projeto Executivo"))
        self.assertEqual(eng.post("/api/documento/retirar", {"documento_id": r["id"], "motivo": "teste"})[0], 200)
        self.assertEqual(self.q("""SELECT alvo_tipo, alvo_id, login FROM auditoria WHERE rota='/api/documento/retirar'
                                   AND status=200"""), [("DOCUMENTO", str(r["id"]), "eng1")])
        st, r = eng.post("/api/documentos/importar", {"csv": INDICE, "simular": True})
        self.assertEqual((st, r["novos"]), (200, 2))
        self.assertEqual(self.n("documentos_obra", "ativo=1"), 0)


if __name__ == "__main__":
    unittest.main()
