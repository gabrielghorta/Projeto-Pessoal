"""Base real para os testes da Nota de Serviço (tests/test_notas_servico.py e tests/test_ns_dia.py): o banco das
planilhas do repositório (perfil TESTE) com os usuários do teste, montado uma vez por execução e copiado para cada
teste, e o servidor HTTP em thread. As NS são sintéticas (tests/ns_sintetica.py)."""
import atexit
import base64
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import acesso as A  # noqa: E402
import importacao as I  # noqa: E402
import importar  # noqa: E402
import ns_sintetica as NSS  # noqa: E402
import server  # noqa: E402
import servicos as S  # noqa: E402
from perfil_teste import cfg_teste_real  # noqa: E402
from test_acesso import SENHA, Cliente  # noqa: E402

CFG = I.carregar_config()
TEM_DADOS = all(I.caminho(CFG, k) for k in ("redes", "conexoes", "evidencias", "bm", "reajuste"))
PB08 = "Zona03_PB08_Rede_"
TR020, TR007, TR006 = PB08 + "TR020", PB08 + "TR007", PB08 + "TR006"
USUARIOS = (("eng1", "ENGENHARIA", None), ("eng2", "ENGENHARIA", None), ("adm", "ADMINISTRACAO", None),
            ("enc3", "EQUIPE", "Zona03"), ("enc1", "EQUIPE", "Zona01"), ("sup1", "SUPERVISOR", None),
            ("almox1", "ALMOXARIFADO", None), ("topo1", "TOPOGRAFIA", None), ("cad1", "CADASTRO", None))
_MODELO = {}
MES = "jan fev mar abr mai jun jul ago set out nov dez".split()


def modelo():
    """Banco das planilhas reais com os usuários do teste: montado uma vez, copiado para cada teste."""
    if not _MODELO:
        raiz = tempfile.mkdtemp(prefix="ns_modelo_")
        atexit.register(shutil.rmtree, raiz, True)
        db = os.path.join(raiz, "obra.db")
        importar.aplicar(db, I.DIR_PLANILHAS, cfg=cfg_teste_real(), dir_relatorios=os.path.join(raiz, "rel"))
        c = S.conectar(db)
        for login, perfil, eq in USUARIOS:
            A.criar_usuario(c, login, login.upper(), perfil, SENHA, eq, "teste da nota de serviço")
        c.close()
        _MODELO.update(raiz=raiz, db=db)
    return _MODELO["db"]


def b64(dados):
    return base64.b64encode(dados).decode()


def data_ns(d):
    """date(2026, 10, 15) → '15-out-26' (a DATA como a NS escreve)."""
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d.day:02d}-{MES[d.month - 1]}-{d.year % 100:02d}"


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
        shutil.copy(modelo(), self.db)
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

    def trecho(self, ponto):
        if ponto not in self.tid:
            self.tid[ponto] = S.alvo(self.c, "TRECHO", ponto)["id"]
        return self.tid[ponto]

    def liberacoes(self, ponto):
        return [(e["ini_m"], e["fim_m"], e["referencia"], e["ns_segmento_id"] is not None)
                for e in S.etapas_complementares(self.c, self.trecho(ponto), "LIBERACAO_TOPOGRAFICA")]

    def cadastros(self, ponto):
        return [(i["ini_m"], i["fim_m"]) for i in S.intervalos(self.c, self.trecho(ponto), "CADASTRO_CAMPO")]

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
