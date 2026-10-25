"""Sistema na nuvem (link fixo, sem computador da obra): a preparação monta a obra das planilhas do repositório na
pasta persistente, cria o administrador das variáveis de ambiente e desativa os usuários de demonstração; o adaptador
WSGI (PythonAnywhere) e o comando de início (Render) atendem com as mesmas rotas, permissões e auditoria; nada é tratado
como "do próprio computador" e o cookie de sessão vai com Secure."""
import gzip
import http.client
import io
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from wsgiref.util import setup_testing_defaults
from wsgiref.validate import validator

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
import acesso as A  # noqa: E402
import importacao as I  # noqa: E402
import nuvem  # noqa: E402
import server  # noqa: E402
import servicos as S  # noqa: E402

CFG = I.carregar_config()
TEM_DADOS = all(I.caminho(CFG, k) for k in ("redes", "conexoes", "evidencias", "bm", "reajuste"))
ADMIN = {"MC_ADMIN_LOGIN": "Gabriel Horta", "MC_ADMIN_NOME": "Gabriel", "MC_ADMIN_SENHA": "senha-forte-da-nuvem"}
LOGIN = {"login": "gabriel.horta", "senha": "senha-forte-da-nuvem"}
GLOBAIS = ("CONN", "DB_PATH", "DIR_FOTOS", "DEMONSTRACAO", "NUVEM", "COOKIE_SEGURO")


@unittest.skipUnless(TEM_DADOS, "planilhas oficiais ausentes em planilhas/")
class TestNuvem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dados = tempfile.mkdtemp(prefix="nuvem_")
        with mock.patch.dict(os.environ, dict(ADMIN, MC_DADOS=cls.dados)):
            cls.info = nuvem.preparar()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dados, ignore_errors=True)

    def setUp(self):
        self.antes = {g: getattr(server, g) for g in GLOBAIS}
        self.log = server.LOG.handlers[:]
        nuvem._pronto = None
        self.env = mock.patch.dict(os.environ, {"MC_DADOS": self.dados})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        if nuvem._pronto and server.CONN is not self.antes["CONN"]:
            server.CONN.close()
        for g, v in self.antes.items():
            setattr(server, g, v)
        for h in server.LOG.handlers:
            if h not in self.log:
                h.close()
        server.LOG.handlers[:] = self.log
        nuvem._pronto = None

    def q(self, sql, *a):
        c = S.conectar(self.info["db"])
        try:
            return [tuple(r) for r in c.execute(sql, a)]
        finally:
            c.close()

    def pedir(self, metodo, rota, corpo=None, cab=None, cookie=None):
        caminho, _, qs = rota.partition("?")
        dados = b"" if corpo is None else json.dumps(corpo).encode()
        env = {"REQUEST_METHOD": metodo, "SCRIPT_NAME": "", "PATH_INFO": caminho, "QUERY_STRING": qs, "REMOTE_ADDR": "127.0.0.1",
               "wsgi.url_scheme": "https", "wsgi.input": io.BytesIO(dados), "CONTENT_LENGTH": str(len(dados))}
        if corpo is not None:
            env.update(CONTENT_TYPE="application/json", HTTP_X_MC="1")
        if cookie:
            env["HTTP_COOKIE"] = f"mc_sessao={cookie}"
        for k, v in (cab or {}).items():
            env["HTTP_" + k.upper().replace("-", "_")] = v
        setup_testing_defaults(env)
        r = {}

        def iniciar(status, cabecalhos, exc_info=None):
            r["status"], r["cab"] = int(status.split()[0]), cabecalhos
            return lambda _: None
        it = validator(nuvem.app)(env, iniciar)                 # confere a conformidade WSGI de cada resposta
        try:
            resposta = b"".join(it)
        finally:
            it.close()
        return r["status"], dict(r["cab"]), resposta

    def test_preparacao_monta_a_obra_cria_o_administrador_e_desativa_a_demonstracao(self):
        self.assertTrue(self.info["demonstracao"])
        self.assertEqual(self.info["db"], os.path.join(self.dados, "dados_demo", "obra.db"))
        self.assertEqual((self.info["administrador_criado"], self.info["configurado"]), ("gabriel.horta", True))
        self.assertEqual(self.q("SELECT login FROM usuarios WHERE ativo=1 AND perfil='ADMINISTRACAO'"), [("gabriel.horta",)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM usuarios WHERE ativo=0 AND login LIKE '%.demo'"), [(8,)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM trechos WHERE vigente=1"), [(1436,)])
        self.assertEqual(self.q("SELECT rota, status FROM auditoria WHERE metodo='NUVEM'"), [("/nuvem/administrador", 200)])
        with mock.patch.dict(os.environ, dict(ADMIN, MC_ADMIN_LOGIN="outro.admin")):   # reinício: nada muda
            info = nuvem.preparar()
        self.assertEqual((info["administrador_criado"], info["demo_desativados"]), (None, 0))
        self.assertEqual(self.q("SELECT login FROM usuarios WHERE ativo=1 AND perfil='ADMINISTRACAO'"), [("gabriel.horta",)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM usuarios WHERE login='outro.admin'"), [(0,)])
        self.assertFalse(os.path.exists(os.path.join(self.dados, "dados")))          # banco oficial não é criado

    def test_pelo_wsgi_nada_e_local_e_o_login_vale_com_cookie_seguro(self):
        st, cab, html = self.pedir("GET", "/")
        self.assertEqual(st, 200)
        for dica in (b"dicaDemo", b"dicaPrimeiro", b"dicaLocal"):                   # nenhuma dica do computador
            self.assertRegex(html, rb'id="' + dica + rb'" class="[^"]+" hidden')
        self.assertEqual(cab["Strict-Transport-Security"], "max-age=31536000")
        self.assertEqual(self.pedir("GET", "/configurar")[0], 403)                   # mesmo vindo de 127.0.0.1
        self.assertEqual(self.pedir("POST", "/api/entrar-local", {})[0], 403)
        self.assertEqual(self.pedir("POST", "/api/configurar-acesso", {"login": "x.y", "nome": "X", "senha": "1234567890ab"})[0], 403)
        self.assertEqual(self.pedir("POST", "/api/login", {"login": "eng.demo", "senha": "demo-morro-123"})[0], 401)
        self.assertEqual(self.pedir("GET", "/api/resumo")[0], 401)
        st, cab, r = self.pedir("POST", "/api/login", LOGIN, {"X-Forwarded-For": "200.1.2.3, 10.0.0.1"})
        self.assertEqual(st, 200, r)
        self.assertIn("Secure", cab["Set-Cookie"])
        self.assertIn("HttpOnly", cab["Set-Cookie"])
        token = cab["Set-Cookie"].split(";")[0].split("=", 1)[1]
        self.assertEqual(self.q("SELECT origem FROM sessoes ORDER BY rowid DESC LIMIT 1"), [("200.1.2.3",)])
        st, _, r = self.pedir("GET", "/api/sessao", cookie=token)
        self.assertEqual((st, json.loads(r)["demonstracao"]), (200, True))
        st, _, r = self.pedir("GET", "/api/resumo", cookie=token)
        self.assertEqual((st, json.loads(r)["trechos"]), (200, 1436))
        nova = {"acao": "criar", "login": "maria.souza", "nome": "Maria", "perfil": "ENGENHARIA", "senha": "senha-da-maria-1"}
        st, _, r = self.pedir("POST", "/api/usuarios", nova, {"X-Idem": "nuvem-1"}, cookie=token)
        self.assertEqual(st, 200, r)
        st, cab, _ = self.pedir("POST", "/api/login", {"login": "Maria Souza", "senha": "senha-da-maria-1"})
        self.assertEqual(st, 200)
        self.assertEqual(self.q("SELECT login, status FROM auditoria WHERE rota='/api/usuarios'"), [("gabriel.horta", 200)])
        st, _, r = self.pedir("GET", "/mapa", cookie=token)
        self.assertEqual(st, 200)
        self.assertIn(b"/mapa_iluminado.js", r)

    def test_pelo_wsgi_texto_comprimido_e_304(self):
        st, cab, html = self.pedir("GET", "/", cab={"Accept-Encoding": "gzip"})
        self.assertEqual((st, cab["Content-Encoding"]), (200, "gzip"))
        v = re.search(rb'src="/app\.js\?v=([0-9a-f]{12})"', gzip.decompress(html)).group(1).decode()
        st, cab, js = self.pedir("GET", "/app.js?v=" + v, cab={"Accept-Encoding": "gzip"})
        self.assertEqual((st, cab["Cache-Control"]), (200, "public, max-age=31536000, immutable"))
        self.assertIn(b"function iniciar", gzip.decompress(js))
        st, cab, corpo = self.pedir("GET", "/app.js", cab={"If-None-Match": f'"{v}"'})
        self.assertEqual((st, corpo, cab["ETag"]), (304, b"", f'"{v}"'))
        self.assertNotIn("Connection", cab)                                        # salto a salto: não vai ao WSGI

    def test_endereco_sem_https_vai_para_https(self):
        st, cab, _ = self.pedir("GET", "/?frente=Zona01", cab={"X-Forwarded-Proto": "http", "Host": "obra.exemplo.com"})
        self.assertEqual((st, cab["Location"]), (301, "https://obra.exemplo.com/?frente=Zona01"))

    def test_comando_de_inicio_da_hospedagem(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            porta = s.getsockname()[1]
        env = dict(os.environ, MC_DADOS=self.dados, PORT=str(porta))
        for k in ADMIN:
            env.pop(k, None)
        proc = subprocess.Popen([sys.executable, os.path.join(RAIZ, "nuvem.py")], cwd=RAIZ, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", porta), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            h = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
            h.request("POST", "/api/login", json.dumps(LOGIN), {"Content-Type": "application/json", "X-MC": "1",
                                                                 "X-Forwarded-Proto": "https", "X-Forwarded-For": "200.9.9.9"})
            r = h.getresponse()
            r.read()
            self.assertEqual(r.status, 200)
            self.assertIn("Secure", r.getheader("Set-Cookie"))
            h.request("GET", "/configurar")
            r = h.getresponse()
            r.read()
            self.assertEqual(r.status, 403)
            h.close()
        finally:
            proc.terminate()
            saida = proc.communicate(timeout=10)[0]
        self.assertIn("(nuvem)", saida)
        if os.name == "posix":                                   # no Windows, terminate() não deixa o servidor limpar
            self.assertFalse(os.path.exists(os.path.join(self.dados, "dados_demo", "SERVIDOR_ATIVO.json")))

    def test_versao_nova_do_codigo_migra_a_demonstracao_ao_subir(self):
        outra = tempfile.mkdtemp(prefix="nuvem_antiga_")
        try:
            shutil.copytree(os.path.join(self.dados, "dados_demo"), os.path.join(outra, "dados_demo"),
                            ignore=shutil.ignore_patterns("logs", "SERVIDOR_ATIVO.json"))
            db = os.path.join(outra, "dados_demo", "obra.db")
            c = S.conectar(db)
            with S.transacao(c):
                c.execute("UPDATE schema_versao SET versao=? WHERE versao=?", (S.VERSAO_ESQUEMA - 1, S.VERSAO_ESQUEMA))
            c.close()
            with self.assertRaises(nuvem.MigraAoRecarregar):          # pelo console, com o site no ar: não migra
                nuvem.preparar(outra, migrar=False)
            info = nuvem.preparar(outra)                              # o próprio servidor, ao subir
            c = S.conectar(db)
            try:
                self.assertEqual(S.versao_banco(c), S.VERSAO_ESQUEMA)
                self.assertEqual(c.execute("SELECT COUNT(*) FROM trechos WHERE vigente=1").fetchone()[0], 1436)
                self.assertEqual([tuple(r) for r in c.execute("SELECT login FROM usuarios WHERE ativo=1 AND perfil='ADMINISTRACAO'")],
                                 [("gabriel.horta",)])
            finally:
                c.close()
            self.assertTrue(info["configurado"])
            self.assertEqual(len(os.listdir(os.path.join(outra, "dados_demo", "backups"))), 1)   # backup verificado antes
        finally:
            shutil.rmtree(outra, ignore_errors=True)

    def test_sem_administrador_a_hospedagem_nao_sobe(self):
        outra = tempfile.mkdtemp(prefix="nuvem_vazia_")
        try:
            shutil.copytree(os.path.join(self.dados, "dados_demo"), os.path.join(outra, "dados_demo"))
            c = S.conectar(os.path.join(outra, "dados_demo", "obra.db"))
            with S.transacao(c):
                c.execute("UPDATE usuarios SET ativo=0")
            c.close()
            with mock.patch.dict(os.environ, {"MC_DADOS": outra}), mock.patch.object(sys, "argv", ["nuvem.py"]):
                for k in ADMIN:
                    os.environ.pop(k, None)
                with self.assertRaises(SystemExit) as e:
                    nuvem.main()
            self.assertIn("MC_ADMIN_LOGIN", str(e.exception))
        finally:
            shutil.rmtree(outra, ignore_errors=True)


class TestServidorSoNaNuvemEscutaNaRede(unittest.TestCase):
    def test_host_de_rede_sem_modo_nuvem_e_recusado(self):
        with mock.patch.object(sys, "argv", ["server.py", "--host", "0.0.0.0"]), self.assertRaises(SystemExit) as e:
            server.main()
        self.assertIn("nuvem", str(e.exception))


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
