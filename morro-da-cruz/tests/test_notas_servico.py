"""Nota de Serviço por upload (notas_servico): migração v18, casamento NS ↔ trecho físico na base real, registro por tipo
(topografia, cadastro, serviço), anulação, reenvio e permissões pelo HTTP. Sem os PDFs reais: a NS é sintética
(tests/ns_sintetica.py). O banco das planilhas reais é montado uma vez (perfil TESTE) e copiado para cada teste."""
import base64
import hashlib
import http.client
import io
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import acesso as A  # noqa: E402
import importacao as I  # noqa: E402
import importar  # noqa: E402
import notas_servico as NS  # noqa: E402
import nuvem  # noqa: E402
import server  # noqa: E402
import servicos as S  # noqa: E402
import ns_sintetica as NSS  # noqa: E402
from perfil_teste import cfg_teste_real  # noqa: E402
from test_acesso import SENHA, Cliente  # noqa: E402
from test_importacao import Base  # noqa: E402

CFG = I.carregar_config()
TEM_DADOS = all(I.caminho(CFG, k) for k in ("redes", "conexoes", "evidencias", "bm", "reajuste"))
PB08 = "Zona03_PB08_Rede_"
TR020, TR007, TR006 = PB08 + "TR020", PB08 + "TR007", PB08 + "TR006"
USUARIOS = (("eng1", "ENGENHARIA", None), ("adm", "ADMINISTRACAO", None), ("enc3", "EQUIPE", "Zona03"),
            ("enc1", "EQUIPE", "Zona01"), ("sup1", "SUPERVISOR", None), ("almox1", "ALMOXARIFADO", None),
            ("topo1", "TOPOGRAFIA", None), ("cad1", "CADASTRO", None))
_MODELO = {}


def _ddl(tabela, trocas=()):
    with open(os.path.join(os.path.dirname(AQUI), "schema.sql"), encoding="utf-8") as f:
        ddl = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \(.*?\n\);", f.read(), re.S).group(0)
    for velho, novo in trocas:
        assert velho in ddl, velho
        ddl = ddl.replace(velho, novo)
    return ddl.replace(f"CREATE TABLE IF NOT EXISTS {tabela} (", f"CREATE TABLE {tabela} (", 1)


class TestMigracaoV18(Base):
    """A migração roda pelo caminho de verdade (importar.aplicar) sobre um banco rebaixado: as linhas ficam e as tabelas
    que apontam para a tabela recriada continuam apontando para o nome certo (com as chaves estrangeiras ligadas, o
    rename da tabela antiga reescreveria as referências para o nome provisório)."""

    def rebaixar(self, versao, sql_extra=()):
        c = sqlite3.connect(self.db, isolation_level=None)
        try:
            c.execute("PRAGMA foreign_keys = OFF")
            c.execute("PRAGMA legacy_alter_table = ON")      # o rename não reescreve as referências das outras tabelas
            c.execute("BEGIN")
            c.execute("ALTER TABLE documentos RENAME TO documentos_atual")
            c.execute(_ddl("documentos", [(",'NS_PDF','NS_CROQUI','NS_PLANILHA'", "")]))
            c.execute("INSERT INTO documentos SELECT * FROM documentos_atual")
            c.execute("DROP TABLE documentos_atual")
            c.execute("DROP TABLE ns_segmentos")
            c.execute("DROP TABLE notas_servico")
            for sql in sql_extra:
                c.execute(sql)
            c.execute("DELETE FROM schema_versao WHERE versao > ?", (versao,))
            c.execute("INSERT OR IGNORE INTO schema_versao VALUES (?, '2026-10-20T00:00:00', 'rebaixado no teste')", (versao,))
            c.execute("COMMIT")
        finally:
            c.close()

    def test_v17_para_v18_documentos_recriado_sem_perder_linhas(self):
        self.aplicar()
        pdf = b"%PDF-1.4 nota fiscal de teste"
        h = hashlib.sha256(pdf).hexdigest()
        os.makedirs(os.path.join(self.dados, "documentos"), exist_ok=True)
        with open(os.path.join(self.dados, "documentos", f"{h}.pdf"), "wb") as f:      # o backup confere o anexo
            f.write(pdf)
        self.rebaixar(17, [
            "INSERT INTO documentos(id,tipo,arquivo,nome_original,sha256,bytes,mime,enviado_por,enviado_em) VALUES "
            f"(7,'NF_PDF','{h}.pdf','nf.pdf','{h}',{len(pdf)},'application/pdf','eng1','2026-10-01')",
            "INSERT INTO notas_fiscais(numero,status,documento_id,origem) VALUES ('123','A_CONFERIR',7,'DIGITADA')"])
        self.assertEqual(self.q("SELECT MAX(versao) FROM schema_versao"), [(17,)])
        rel = self.aplicar()
        self.assertEqual((rel["esquema_antes"], rel["esquema_depois"]), (17, S.VERSAO_ESQUEMA))
        sql = lambda t: self.q("SELECT sql FROM sqlite_master WHERE name=?", t)[0][0]
        self.assertIn("NS_PDF", sql("documentos"))
        self.assertIn("REFERENCES documentos(id)", sql("notas_fiscais"))            # não "documentos_v17"
        self.assertIn("REFERENCES documentos(id)", sql("inspecoes"))
        self.assertEqual(self.q("SELECT d.sha256 FROM notas_fiscais n JOIN documentos d ON d.id=n.documento_id"), [(h,)])
        self.assertEqual(self.q("SELECT name FROM sqlite_master WHERE name LIKE 'documentos_v%'"), [])
        for t, col in (("intervalos_execucao", "ns_segmento_id"), ("etapas_complementares", "ns_segmento_id"),
                       ("apontamentos", "motivo_sem_ns")):
            self.assertIn(col, [r[1] for r in self.q(f"PRAGMA table_info({t})")], t)
        c = self.conectar()
        self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
        c.execute("INSERT INTO documentos(tipo,arquivo,sha256,bytes,enviado_por,enviado_em) "
                  "VALUES ('NS_PDF','bb.pdf','bb',5,'eng1','2026-10-21')")
        c.execute("INSERT INTO notas_fiscais(numero,status,documento_id) VALUES ('124','A_CONFERIR',?)",
                  (c.execute("SELECT id FROM documentos WHERE sha256='bb'").fetchone()[0],))   # a referência resolve

    def test_v16_para_v18_retificacoes_continuam_referenciadas(self):
        self.aplicar()
        tr = self.q("SELECT id FROM trechos WHERE vigente=1 ORDER BY id LIMIT 1")[0][0]
        self.rebaixar(16, [
            "ALTER TABLE retificacoes_intervalos RENAME TO retif_atual",
            _ddl("retificacoes_intervalos", [("'APONTAMENTO','CONCILIACAO','CADASTRO_CAMPO'", "'APONTAMENTO','CONCILIACAO'")]),
            "INSERT INTO retificacoes_intervalos SELECT * FROM retif_atual",
            "DROP TABLE retif_atual",
            f"INSERT INTO retificacoes_intervalos(id,trecho_id,ref_tipo,ref_id,motivo,responsavel,detalhe,em) "
            f"VALUES (5,'{tr}','APONTAMENTO',1,'trena','eng1','{{}}','2026-10-01')",
            f"INSERT INTO apontamentos(id,data,equipe_id,alvo_tipo,alvo_id,anulado_por) VALUES (1,'2026-10-01','Zona01','TRECHO','{tr}',5)"])
        rel = self.aplicar()
        self.assertEqual((rel["esquema_antes"], rel["esquema_depois"]), (16, S.VERSAO_ESQUEMA))
        ap = self.q("SELECT sql FROM sqlite_master WHERE name='apontamentos'")[0][0]
        self.assertIn("REFERENCES retificacoes_intervalos(id)", ap)                 # não "retificacoes_intervalos_v16"
        self.assertIn("CADASTRO_CAMPO", self.q("SELECT sql FROM sqlite_master WHERE name='retificacoes_intervalos'")[0][0])
        self.assertEqual(self.q("SELECT a.id, r.motivo FROM apontamentos a JOIN retificacoes_intervalos r ON r.id=a.anulado_por"),
                         [(1, "trena")])
        self.assertEqual(self.conectar().execute("PRAGMA foreign_key_check").fetchall(), [])


# ====================================================================== base real (planilhas do repositório)
def _modelo():
    """Banco das planilhas reais com os usuários do teste: montado uma vez, copiado para cada teste."""
    if not _MODELO:
        raiz = tempfile.mkdtemp(prefix="ns_modelo_")
        db = os.path.join(raiz, "obra.db")
        importar.aplicar(db, I.DIR_PLANILHAS, cfg=cfg_teste_real(), dir_relatorios=os.path.join(raiz, "rel"))
        c = S.conectar(db)
        for login, perfil, eq in USUARIOS:
            A.criar_usuario(c, login, login.upper(), perfil, SENHA, eq, "teste da nota de serviço")
        c.close()
        _MODELO.update(raiz=raiz, db=db)
    return _MODELO["db"]


def tearDownModule():
    if _MODELO:
        shutil.rmtree(_MODELO["raiz"], ignore_errors=True)


def b64(dados):
    return base64.b64encode(dados).decode()


def pdf_ns(girar=False, **kw):
    """PDF da NS sintética da Zona03 PB08 (NÓ6.1 → NÓ9.1 → VRP-15); kw muda os argumentos de paginas_ns."""
    return NSS.pdf_de_texto(NSS.paginas_ns(**NSS.ns_zona03_pb08(**kw)), girar=girar)


def pdf_grupo(elementos, distancias, grupo="REDE ZONA 03 - PB08 - PEAD DE 160", material="PEAD-160", **kw):
    g = NSS.grupo_padrao(grupo, elementos, distancias, material=material)
    return NSS.pdf_de_texto(NSS.paginas_ns(**dict({"grupos": [g]}, **kw)))


@unittest.skipUnless(TEM_DADOS, "planilhas oficiais ausentes em planilhas/")
class BaseReal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ns_")
        self.dados = os.path.join(self.tmp, "dados")
        self.fotos = os.path.join(self.dados, "fotos")
        os.makedirs(self.fotos)
        self.db = os.path.join(self.dados, "obra.db")
        shutil.copy(_modelo(), self.db)
        self.c = S.conectar(self.db)
        self.srv_conn = S.conectar(self.db)
        self._antigos = (server.CONN, server.DB_PATH, server.DIR_FOTOS)
        server.CONN, server.DB_PATH, server.DIR_FOTOS = self.srv_conn, self.db, self.fotos
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.u = {}
        self.tid = {p: S.alvo(self.c, "TRECHO", p)["id"] for p in (TR020, TR007, TR006)}

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        server.CONN, server.DB_PATH, server.DIR_FOTOS = self._antigos
        self.srv_conn.close()
        self.c.close()
        shutil.rmtree(self.tmp)

    def cli(self, login):
        if login not in self.u:
            self.u[login] = Cliente(self.url)
            self.u[login].entrar(login)
        return self.u[login]

    def ler(self, login, tipo, pdf, **kw):
        return self.cli(login).post("/api/ns/ler", dict(tipo=tipo, pdf_b64=b64(pdf), **kw))

    def registrar(self, login, tipo, pdf, **kw):
        return self.cli(login).post("/api/ns", dict(tipo=tipo, pdf_b64=b64(pdf), pdf_nome="nota.pdf", **kw))

    def ok(self, resposta):
        st, r = resposta
        self.assertEqual(st, 200, r)
        return r

    def recusa(self, resposta, status, trecho):
        st, r = resposta
        self.assertEqual(st, status, r)
        self.assertIn(trecho, r["erro"])
        return r

    def n(self, tabela, onde="1=1", *args):
        return self.c.execute(f"SELECT COUNT(*) FROM {tabela} WHERE {onde}", args).fetchone()[0]

    def liberacoes(self, ponto):
        return [(e["ini_m"], e["fim_m"], e["referencia"], e["ns_segmento_id"] is not None)
                for e in S.etapas_complementares(self.c, self.tid[ponto], "LIBERACAO_TOPOGRAFICA")]

    def cadastros(self, ponto):
        return [(i["ini_m"], i["fim_m"]) for i in S.intervalos(self.c, self.tid[ponto], "CADASTRO_CAMPO")]

    def assentar(self, ponto, ini, fim, data, equipe="Zona03"):
        for turno in ("MANHA", "TARDE"):
            S.registrar_clima(self.c, data, equipe, turno, "SOL")
        S.apontar(self.c, data, equipe, "TRECHO", ponto, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": ini, "fim_m": fim}],
                  informado_por="eng1")

    def abrir(self, login, rota):
        """GET cru (status, cabeçalhos, corpo) para conferir os cabeçalhos do arquivo."""
        try:
            with self.cli(login).op.open(urllib.request.Request(self.url + rota), timeout=20) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()


class TestTopografia(BaseReal):
    def test_lida_casada_e_gravada_por_linha_da_06_1(self):
        pdf = pdf_ns()
        r = self.ok(self.ler("eng1", "TOPOGRAFIA", pdf))
        self.assertTrue(r["contrato_ok"])
        self.assertEqual((r["contexto"]["zona"], r["contexto"]["pb"]), ("Zona03", "PB08"))
        segs = r["segmentos"]
        self.assertEqual([(s["situacao"], s["escolhido"]["fisico_id"], s["escolhido"]["extensao_m"], s["escolhido"]["sentido"])
                          for s in segs], [("AUTOMATICO", "TF-00351", 277.99, 1), ("AUTOMATICO", "TF-00337", 295.98, 1)])
        self.assertEqual([(p["ponto"], p["gravar"]) for p in segs[1]["plano"]],
                         [(TR007, [[0.0, 2.51]]), (TR006, [[0.0, 293.47]])])
        self.assertEqual(self.n("notas_servico"), 0)                          # ler não grava nada
        r = self.ok(self.registrar("eng1", "TOPOGRAFIA", pdf))
        self.assertEqual((r["gravado_m"], r["pendente_m"], r["arquivo_trocado"]), (573.97, 0.0, False))
        ref = "NS 012 fl. 01/01"
        self.assertEqual(self.liberacoes(TR020), [(0.0, 277.99, ref, True)])
        self.assertEqual(self.liberacoes(TR007), [(0.0, 2.51, ref, True)])
        self.assertEqual(self.liberacoes(TR006), [(0.0, 293.47, ref, True)])
        ns = self.c.execute("SELECT * FROM notas_servico").fetchone()
        self.assertEqual((ns["tipo"], ns["contrato"], ns["numero"], ns["data"], ns["zona"], ns["pb"], ns["status"]),
                         ("TOPOGRAFIA", "10239/2026", "012", "2026-10-15", "Zona03", "PB08", "REGISTRADA"))
        seg = self.c.execute("SELECT * FROM ns_segmentos WHERE ordem=2").fetchone()
        self.assertEqual((seg["fisico_id"], seg["ini_fisico_m"], seg["fim_fisico_m"], seg["aplicado_m"]), ("TF-00337", 0, 295.98, 295.98))
        self.assertIn("TR-00338", seg["membros"])                             # cópia dos membros (a topologia pode mudar)
        corpo = self.c.execute("SELECT corpo FROM auditoria WHERE rota='/api/ns' AND status=200").fetchone()[0]
        self.assertIn("[omitido]", corpo)
        self.assertNotIn(b64(pdf)[:40], corpo)                                # o base64 não vai para a auditoria

        st, h, dados = self.abrir("eng1", f"/api/ns/arquivo?id={ns['id']}&qual=pdf")
        self.assertEqual((st, h["Content-Type"], dados), (200, "application/pdf", pdf))
        self.assertTrue(h["Content-Disposition"].startswith("inline"))
        self.assertEqual((h["Content-Security-Policy"], h["X-Content-Type-Options"]), ("sandbox", "nosniff"))
        self.assertEqual(self.abrir("eng1", f"/api/ns/arquivo?id={ns['id']}&qual=croqui")[0], 404)

    def test_grava_so_o_que_nao_estava_liberado(self):
        S.registrar_etapa_complementar(self.c, TR006, "LIBERACAO_TOPOGRAFICA", 50, 120, "2026-10-10", "eng1", "locação antiga")
        r = self.ok(self.registrar("eng1", "TOPOGRAFIA", pdf_ns()))
        self.assertEqual(r["gravado_m"], 503.97)                              # 573,97 − 70 já liberados
        self.assertEqual([x[:2] for x in self.liberacoes(TR006)], [(0.0, 50.0), (50.0, 120.0), (120.0, 293.47)])
        self.assertEqual([x[3] for x in self.liberacoes(TR006)], [True, False, True])

    def test_reenvio_mesma_ns_outro_arquivo_e_outro_conteudo(self):
        pdf = pdf_ns()
        nid = self.ok(self.registrar("eng1", "TOPOGRAFIA", pdf))["id"]
        self.recusa(self.registrar("eng1", "TOPOGRAFIA", pdf), 422, "já foi registrado")
        assinada = pdf_ns(girar=True)                                        # outro arquivo, a mesma impressão dos dados
        self.assertNotEqual(assinada, pdf)
        r = self.ok(self.registrar("eng1", "TOPOGRAFIA", assinada))
        self.assertEqual((r["id"], r["arquivo_trocado"], r["gravado_m"]), (nid, True, 0.0))
        vig = self.c.execute("SELECT * FROM notas_servico WHERE id=?", (nid,)).fetchone()
        ant = self.c.execute("SELECT * FROM notas_servico WHERE id=?", (vig["substitui_id"],)).fetchone()
        self.assertEqual((vig["status"], ant["status"]), ("REGISTRADA", "SUBSTITUIDA"))
        self.assertNotEqual(vig["pdf_id"], ant["pdf_id"])
        self.assertEqual(self.n("etapas_complementares"), 3)                 # os registros não mudam
        detalhe = self.ok(self.cli("eng1").get(f"/api/ns/detalhe?id={nid}"))
        self.assertEqual([v["id"] for v in detalhe["versoes"]], [ant["id"]])
        outra = pdf_ns(grupos=[NSS.grupo_padrao('REDE ZONA 03 - PB08 - PEAD DE 160', ['NÓ6.1 - TÊ 160x110', 'NÓ9.1 - TÊ 160x160'],
                                                 [278.05])])
        self.recusa(self.registrar("eng1", "TOPOGRAFIA", outra), 422, "anule a anterior")
        self.recusa(self.cli("eng1").post("/api/ns/anular", {"ns_id": nid}), 422, "motivo")
        self.ok(self.cli("eng1").post("/api/ns/anular", {"ns_id": nid, "motivo": "NS refeita pela topografia"}))
        self.assertEqual(self.n("etapas_complementares", "anulado_em IS NULL"), 0)
        self.assertEqual(self.n("etapas_complementares"), 3)                 # nada apagado
        self.assertIn("NS 012 anulada: NS refeita",
                      self.c.execute("SELECT anulado_motivo FROM etapas_complementares LIMIT 1").fetchone()[0])
        r = self.ok(self.registrar("eng1", "TOPOGRAFIA", outra))             # depois de anular, a nova entra
        self.assertEqual(r["gravado_m"], 277.99)
        self.assertEqual(self.ok(self.cli("eng1").get("/api/ns?tipo=TOPOGRAFIA&vigentes=0"))[0]["id"], r["id"])


class TestCadastro(BaseReal):
    def test_grava_sobre_o_assentado_deixa_pendente_e_aplica_depois(self):
        self.assentar(TR006, 0, 100, "2026-10-14")
        pdf = pdf_ns(numero="013", bloco="CADASTRO")
        prev = self.ok(self.ler("eng1", "CADASTRO", pdf))
        self.assertIsNone(prev["aviso_tipo"])
        self.assertEqual([(p["ponto"], p["gravar"], p["pendente"]) for p in prev["segmentos"][1]["plano"]],
                         [(TR007, [], [[0.0, 2.51]]), (TR006, [[0.0, 100.0]], [[100.0, 293.47]])])
        r = self.ok(self.registrar("eng1", "CADASTRO", pdf))
        self.assertEqual((r["gravado_m"], r["pendente_m"]), (100.0, 473.97))   # 277,99 + 2,51 + 193,47 sem assentado
        self.assertEqual(self.cadastros(TR006), [(0.0, 100.0)])
        seg = self.c.execute("SELECT * FROM ns_segmentos WHERE ordem=2").fetchone()
        self.assertEqual((seg["aplicado_m"], seg["pendente_m"]), (100.0, 195.98))
        self.assertIn("ainda não assentado", seg["pendente"])
        self.assentar(TR006, 100, 150, "2026-10-15")                         # lançado depois, com a data da vala aberta
        self.assentar(TR006, 150, 160, "2026-10-17")                         # depois da data da NS: não conta
        r = self.ok(self.cli("eng1").post("/api/ns/aplicar", {"ns_id": r["id"]}))
        self.assertEqual((r["gravado_m"], r["pendente_m"]), (50.0, 423.97))
        self.assertEqual(self.cadastros(TR006), [(0.0, 100.0), (100.0, 150.0)])
        self.assertEqual(self.ok(self.cli("eng1").post("/api/ns/aplicar", {"ns_id": r["id"]}))["gravado_m"], 0.0)   # idempotente
        self.ok(self.cli("eng1").post("/api/ns/anular", {"ns_id": r["id"], "motivo": "levantamento refeito"}))
        self.assertEqual(self.cadastros(TR006), [])
        self.assertEqual(self.n("intervalos_execucao", "etapa='CADASTRO_CAMPO'"), 2)   # retificados, não apagados
        self.assertEqual(len(S.intervalos(self.c, self.tid[TR006], "ASSENTADO")), 3)  # o assentado não muda

    def test_aviso_quando_o_bloco_e_de_outro_tipo(self):
        r = self.ok(self.ler("eng1", "CADASTRO", pdf_ns()))                  # bloco TOPOGRAFIA
        self.assertIn("TOPOGRAFIA", r["aviso_tipo"])


class TestServico(BaseReal):
    def test_exige_croqui_e_nao_grava_registro(self):
        pdf = pdf_ns(numero="020", bloco="TOPOGRAFIA")
        self.recusa(self.registrar("eng1", "SERVICO", pdf), 422, "croqui")
        croqui = NSS.pdf_de_texto(["CROQUI NS 020"])
        r = self.ok(self.registrar("eng1", "SERVICO", pdf, croqui_b64=b64(croqui), croqui_nome="croqui.pdf"))
        self.assertEqual((r["gravado_m"], self.n("etapas_complementares"), self.n("intervalos_execucao")), (0.0, 0, 0))
        self.assertEqual([s["situacao"] for s in r["segmentos"]], ["AUTOMATICO", "AUTOMATICO"])
        self.recusa(self.cli("eng1").post("/api/ns/anexo", {"ns_id": r["id"], "croqui_b64": b64(croqui)}), 422, "já está")
        novo = NSS.pdf_de_texto(["CROQUI NS 020 REV 1"])
        self.ok(self.cli("eng1").post("/api/ns/anexo", {"ns_id": r["id"], "croqui_b64": b64(novo), "croqui_nome": "c.pdf"}))
        st, h, dados = self.abrir("eng1", f"/api/ns/arquivo?id={r['id']}&qual=croqui")
        self.assertEqual((st, dados), (200, novo))
        self.recusa(self.cli("eng1").post("/api/ns/aplicar", {"ns_id": r["id"]}), 422, "Só a NS de topografia")
        self.recusa(self.cli("eng1").post("/api/ns/anexo", {"ns_id": r["id"], "croqui_b64": b64(b"GIF89a")}), 422, "PDF, JPG ou PNG")


class TestCasamento(BaseReal):
    def ler_direto(self, pdf, tipo="TOPOGRAFIA", **kw):
        return NS.ler(self.c, tipo, b64(pdf), **kw)

    def test_no_listado_no_meio_e_juncao(self):
        pdf = pdf_grupo(["NÓ9.1 - TÊ 160x160", "NÓ113.1", "CH_VRP-15 (CAIXA DA VRP)"], [2.51, 293.47])
        segs = self.ler_direto(pdf)["segmentos"]
        self.assertEqual([(s["situacao"], s["escolhido"]["fisico_id"], s["metros_ns"]) for s in segs], [("AUTOMATICO", "TF-00337", 295.98)])
        self.assertTrue(any("NÓ113.1 não é conexão" in a for a in segs[0]["avisos"]), segs[0]["avisos"])

    def test_par_de_nos_repetido_em_outra_pb_pede_confirmacao(self):
        sem_pb = dict(titulo='"REDE DE ÁGUA" - ZONA 03 - VER CROQUI ANEXO', localizacao="MORRO DA CRUZ - SÃO SEBASTIÃO/DF")
        pdf = pdf_grupo(["NÓ56.1", "NÓ8.1"], [32.4], grupo="REDE ZONA 03 - PEAD DE 160", **sem_pb)
        s = self.ler_direto(pdf)["segmentos"][0]
        self.assertEqual(s["situacao"], "CONFIRMAR")
        self.assertEqual(sorted(c["fisico_id"] for c in s["candidatos"]), ["TF-00280", "TF-00365"])
        self.assertIn("Zona03 PB05 e Zona03 PB08", s["motivo"])
        self.assertIn("pela extensão, o de Zona03 PB08", s["motivo"])
        s = self.ler_direto(pdf, pb="PB08")["segmentos"][0]                  # a PB escolhida no formulário resolve
        self.assertEqual((s["situacao"], s["escolhido"]["fisico_id"]), ("AUTOMATICO", "TF-00365"))

    def test_diferenca_de_3_por_cento_confirma_e_de_8_por_cento_e_erro(self):
        casos = {1.03: ("CONFIRMAR", "acima de 0,5 %"), 1.08: ("ERRO", "acima de 5 %"), 1.004: ("AUTOMATICO", None)}
        for k, (situacao, motivo) in casos.items():
            pdf = pdf_grupo(["NÓ9.1 - TÊ 160x160", "CH_VRP-15"], [round(295.98 * k, 2)])
            s = self.ler_direto(pdf)["segmentos"][0]
            self.assertEqual(s["situacao"], situacao, k)
            if motivo:
                self.assertIn(motivo, s["motivo"])
        s = self.ler_direto(pdf_grupo(["NÓ9.1", "CH_VRP-15"], [295.98], material="PEAD-110"))["segmentos"][0]
        self.assertEqual((s["situacao"], s["motivo"]), ("ERRO", "DE 110 na NS × DE 160 na 06.1"))
        s = self.ler_direto(pdf_grupo(["NÓ9.1", "NÓ77.7"], [10.0]))["segmentos"][0]
        self.assertEqual(s["situacao"], "SEM_CORRESPONDENCIA")

    def test_registrar_exige_a_conferencia_de_cada_segmento(self):
        tres = pdf_grupo(["NÓ6.1 - TÊ 160x110", "NÓ9.1 - TÊ 160x160", "CH_VRP-15"], [277.99, round(295.98 * 1.03, 2)])
        self.recusa(self.registrar("eng1", "TOPOGRAFIA", tres), 422, "Confira os segmentos 2")
        self.assertEqual(self.n("notas_servico") + self.n("documentos"), 0)   # nada gravado (nem o arquivo)
        r = self.ok(self.registrar("eng1", "TOPOGRAFIA", tres, decisoes=[{"ordem": 2, "acao": "ACEITAR"}]))
        self.assertEqual([s["situacao"] for s in r["segmentos"]], ["AUTOMATICO", "CONFIRMADO"])
        self.assertEqual(r["gravado_m"], 573.97)                              # grava a extensão do projeto, não a da NS
        self.assertEqual(self.c.execute("SELECT confirmado_por FROM ns_segmentos WHERE ordem=2").fetchone()[0], "eng1")
        oito = pdf_grupo(["NÓ6.1", "NÓ9.1", "CH_VRP-15"], [277.99, round(295.98 * 1.08, 2)], numero="014")
        self.recusa(self.registrar("eng1", "TOPOGRAFIA", oito, decisoes=[{"ordem": 2, "acao": "ACEITAR"}]), 422, "Confira")
        self.recusa(self.registrar("eng1", "TOPOGRAFIA", oito, decisoes=[{"ordem": 2, "acao": "FORA"}]), 422, "por que")
        r = self.ok(self.registrar("eng1", "TOPOGRAFIA", oito, decisoes=[{"ordem": 2, "acao": "FORA", "motivo": "conferir em campo"}]))
        self.assertEqual([(s["situacao"], s["gravado_m"]) for s in r["segmentos"]], [("AUTOMATICO", 0.0), ("FORA", 0.0)])

    def test_ns_de_outra_obra_e_recusada(self):
        g = NSS.grupo_padrao('COLETOR PRINCIPAL - EMISSÁRIO DE ENTRADA (TP - PV.3 - PV.6)',
                             ['CAIXA DE ENTRADA - TRATAMENTO PRELIMINAR', 'PV-3 EMISSÁRIO DE ENTRADA', 'PV-6 EMISSÁRIO DE ENTRADA'],
                             [17.32, 8.24], material='PEAD-1000')
        pdf = NSS.pdf_de_texto(NSS.paginas_ns(numero='006', contrato='9702/2024', data='27-out-25', grupos=[g],
                                              titulo='"EMISSÁRIO DE ENTRADA" - TRATAMENTO PRELIMINAR - ETE PARANOÁ/DF'))
        r = self.ok(self.ler("eng1", "TOPOGRAFIA", pdf))
        self.assertFalse(r["contrato_ok"])
        self.assertFalse(r["leitura"]["resultado"]["aceita"])
        self.recusa(self.registrar("eng1", "TOPOGRAFIA", pdf), 422, "NS recusada: V01")
        self.recusa(self.ler("eng1", "TOPOGRAFIA", b"%PDF-1.4 sem nada"), 422, "")


class TestPermissoes(BaseReal):
    def test_so_engenharia_e_administracao_enviam(self):
        pdf = pdf_ns()
        for login in ("enc3", "almox1", "sup1", "topo1", "cad1"):
            for rota, corpo in (("/api/ns/ler", {"tipo": "TOPOGRAFIA", "pdf_b64": b64(pdf)}),
                                ("/api/ns", {"tipo": "TOPOGRAFIA", "pdf_b64": b64(pdf)}),
                                ("/api/ns/anexo", {"ns_id": 1}), ("/api/ns/aplicar", {"ns_id": 1}),
                                ("/api/ns/anular", {"ns_id": 1, "motivo": "x"})):
                st, r = self.cli(login).post(rota, corpo)
                self.assertEqual(st, 403, (login, rota, r))
        self.ok(self.registrar("adm", "TOPOGRAFIA", pdf))
        self.assertEqual(self.n("notas_servico"), 1)

    def test_quem_ve_o_que(self):
        topo = self.ok(self.registrar("eng1", "TOPOGRAFIA", pdf_ns()))["id"]
        serv = self.ok(self.registrar("eng1", "SERVICO", pdf_ns(numero="020"), croqui_b64=b64(NSS.pdf_de_texto(["CROQUI"]))))["id"]
        # encarregado: a NS de serviço (lista, PDF e croqui), nunca a de topografia
        self.assertEqual([n["id"] for n in self.ok(self.cli("enc3").get("/api/ns"))], [serv])
        self.assertEqual(self.abrir("enc3", f"/api/ns/arquivo?id={serv}&qual=pdf")[0], 200)
        self.assertEqual(self.abrir("enc3", f"/api/ns/arquivo?id={serv}&qual=croqui")[0], 200)
        self.assertEqual(self.abrir("enc3", f"/api/ns/arquivo?id={topo}&qual=pdf")[0], 403)
        self.assertEqual(self.cli("enc3").get("/api/ns?tipo=TOPOGRAFIA")[0], 403)
        self.assertEqual(self.cli("enc3").get(f"/api/ns/detalhe?id={topo}")[0], 403)
        # topografia e cadastro: só consultam o tipo deles
        self.assertEqual([n["id"] for n in self.ok(self.cli("topo1").get("/api/ns?tipo=TOPOGRAFIA"))], [topo])
        self.assertEqual(self.cli("topo1").get("/api/ns?tipo=CADASTRO")[0], 403)
        self.assertEqual(self.abrir("topo1", f"/api/ns/arquivo?id={topo}&qual=pdf")[0], 200)
        self.assertEqual(self.ok(self.cli("cad1").get("/api/ns")), [])
        self.assertEqual(self.abrir("cad1", f"/api/ns/arquivo?id={topo}&qual=pdf")[0], 403)
        self.assertEqual(self.cli("almox1").get("/api/ns")[0], 200)          # almoxarifado abre a tela do campo
        self.assertEqual({n["id"] for n in self.ok(self.cli("eng1").get("/api/ns"))}, {topo, serv})

    def test_corpo_grande_recusado_sem_ler(self):
        self.cli("eng1")
        porta = self.httpd.server_address[1]
        h = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
        h.putrequest("POST", "/api/ns")
        h.putheader("X-MC", "1")
        h.putheader("Content-Type", "application/json")
        h.putheader("Content-Length", str(server.LIMITE_CORPO + 1))
        h.endheaders()                                                       # o corpo nunca é enviado
        r = h.getresponse()
        self.assertEqual(r.status, 413)
        self.assertIn("grande demais", r.read().decode())
        h.close()
        entrada = io.BytesIO(b"x" * 10)
        environ = {"CONTENT_LENGTH": str(server.LIMITE_CORPO + 1), "CONTENT_TYPE": "application/json", "HTTP_X_MC": "1",
                   "wsgi.input": entrada, "REQUEST_METHOD": "POST", "PATH_INFO": "/api/ns", "QUERY_STRING": ""}
        p = nuvem._pedido(environ)
        self.assertEqual(entrada.tell(), 0)                                  # a nuvem também não lê o corpo
        p.do_POST()
        self.assertIn(b" 413 ", p.wfile.getvalue().split(b"\r\n")[0])


if __name__ == "__main__":
    unittest.main()
