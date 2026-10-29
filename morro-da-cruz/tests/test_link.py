"""Link para a equipe (site pelo computador do escritório): só abre depois de um administrador real, criado no próprio
computador; usuários de demonstração são desativados; quem chega pelo túnel não configura nada nem vê as senhas de
demonstração; cookie com Secure atrás do HTTPS; o link aparece quando o túnel conecta (cloudflared substituído)."""
import http.client
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import acesso as A  # noqa: E402
import caminhos  # noqa: E402
import link  # noqa: E402
import server  # noqa: E402
from test_acesso import SENHA, BaseHTTP  # noqa: E402

TUNEL = {"Cf-Connecting-Ip": "200.1.2.3", "X-Forwarded-For": "200.1.2.3", "X-Forwarded-Proto": "https"}
FALSO = '''import sys, time
print("INF Requesting new quick Tunnel on trycloudflare.com...", flush=True)
print('ERR failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel" (tentativa anterior)', flush=True)
print("INF |  https://teste-link-morro-cruz.trycloudflare.com                      |", flush=True)
time.sleep(60)
'''


class TestRegex(unittest.TestCase):
    def test_reconhece_o_endereco_e_ignora_a_api(self):
        self.assertIsNone(link.URL.search('Post "https://api.trycloudflare.com/tunnel"'))
        self.assertEqual(link.URL.search("|  https://abc-def-ghi.trycloudflare.com  |").group(0), "https://abc-def-ghi.trycloudflare.com")


class BaseLink(BaseHTTP):
    usuarios = (("eng.demo", "ENGENHARIA", None), ("almox.demo", "ALMOXARIFADO", None))

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.falso = os.path.join(self.tmp, "cloudflared_falso.py")
        with open(self.falso, "w", encoding="utf-8") as f:
            f.write(FALSO)
        self._antes = (server.DEMONSTRACAO, server.LINK, server.PORTA)
        server.DEMONSTRACAO, server.LINK, server.PORTA = True, True, self.httpd.server_address[1]
        self.patches = [mock.patch.dict(os.environ, {"MC_CLOUDFLARED": self.falso}), mock.patch.object(caminhos, "PASTA", self.tmp)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        link.parar()
        link.estado.update(situacao="DESLIGADO", url=None, erro=None)
        for p in self.patches:
            p.stop()
        server.DEMONSTRACAO, server.LINK, server.PORTA = self._antes
        super().tearDown()

    def bruto(self, metodo, rota, corpo=None, cab=None):
        h = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=10)
        cab = dict(cab or {}, **({"Content-Type": "application/json", "X-MC": "1"} if corpo is not None else {}))
        h.request(metodo, rota, body=None if corpo is None else json.dumps(corpo), headers=cab)
        r = h.getresponse()
        dados = r.read()
        h.close()
        return r.status, dict(r.getheaders()), dados


class TestConfigurarAcesso(BaseLink):
    def test_so_no_computador_desativa_demonstracao_e_liga_o_link(self):
        st, _, html = self.bruto("GET", "/")
        self.assertIn(b'id="dicaDemo" class="aviso info">', html)                     # local: dicas aparecem
        self.assertIn(b'id="dicaPrimeiro" class="aviso sugestao">', html)            # botão "Criar meu usuário"
        st, _, html = self.bruto("GET", "/", cab=TUNEL)
        self.assertIn(b'id="dicaDemo" class="aviso info" hidden', html)                # pelo link: nada de senha na tela
        self.assertEqual(self.bruto("GET", "/configurar", cab=TUNEL)[0], 403)
        self.assertEqual(self.bruto("GET", "/configurar")[0], 200)
        self.assertEqual(self.bruto("GET", "/api/link", cab=TUNEL)[0], 401)
        corpo = {"login": "gabriel.horta", "nome": "Gabriel", "senha": "senha-forte-do-admin"}
        self.assertEqual(self.bruto("POST", "/api/configurar-acesso", corpo, TUNEL)[0], 403)  # de fora: recusado
        self.assertEqual(self.bruto("POST", "/api/configurar-acesso", dict(corpo, senha="curta"))[0], 422)
        self.assertEqual(self.bruto("POST", "/api/configurar-acesso", dict(corpo, login="chefe.demo"))[0], 422)
        self.assertFalse(A.acesso_configurado(self.c))
        st, _, r = self.bruto("POST", "/api/configurar-acesso", corpo)
        self.assertEqual(st, 200, r)
        self.assertEqual(json.loads(r)["desativados"], 2)
        self.assertTrue(A.acesso_configurado(self.c))
        self.assertEqual(self.q("SELECT login, ativo FROM usuarios ORDER BY login"),
                         [("almox.demo", 0), ("eng.demo", 0), ("gabriel.horta", 1)])
        self.assertEqual(self.bruto("POST", "/api/login", {"login": "eng.demo", "senha": SENHA})[0], 401)   # demo fora
        self.assertEqual(self.bruto("POST", "/api/configurar-acesso", corpo)[0], 422)     # só uma vez
        self.assertEqual(self.q("SELECT status FROM auditoria WHERE rota='/api/configurar-acesso' AND status=200"), [(200,)])
        for _ in range(50):                                                            # o túnel (falso) conecta
            st, _, r = self.bruto("GET", "/api/link")
            if json.loads(r)["situacao"] == "NO_AR":
                break
            time.sleep(0.1)
        r = json.loads(r)
        self.assertEqual((r["situacao"], r["url"], r["configurado"]), ("NO_AR", "https://teste-link-morro-cruz.trycloudflare.com", True))
        with open(os.path.join(self.tmp, link.ARQUIVO), encoding="utf-8") as f:
            self.assertIn(r["url"], f.read())
        st, _, html = self.bruto("GET", "/")
        self.assertIn(b'id="dicaPrimeiro" class="aviso sugestao" hidden', html)        # configurado: sem "primeiro acesso"
        self.assertIn(b'id="dicaLocal" class="aviso sugestao">', html)                 # e com "entrar sem senha" (local)
        st, _, html = self.bruto("GET", "/", cab=TUNEL)
        self.assertIn(b'id="dicaLocal" class="aviso sugestao" hidden', html)

    def test_entrar_sem_senha_so_no_computador_e_login_tolerante(self):
        self.assertEqual(self.bruto("POST", "/api/entrar-local", {})[0], 409)              # ainda sem administrador
        st, _, r = self.bruto("POST", "/api/configurar-acesso", {"login": "Gabriel Horta", "nome": "Gabriel", "senha": "senha-forte-do-admin"})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT login FROM usuarios WHERE ativo=1"), [("gabriel.horta",)])   # sem espaço nem maiúscula
        self.assertEqual(self.bruto("POST", "/api/entrar-local", {}, TUNEL)[0], 403)       # pelo link: nunca sem senha
        st, cab, r = self.bruto("POST", "/api/entrar-local", {})
        self.assertEqual((st, json.loads(r)["usuario"]["login"]), (200, "gabriel.horta"))
        self.assertIn("mc_sessao=", cab["Set-Cookie"])
        self.assertEqual(self.q("SELECT COUNT(*) FROM auditoria WHERE rota='/api/entrar-local' AND status=200"), [(1,)])
        for escrito in ("gabriel horta", "GABRIEL.HORTA", " Gabriel  Horta "):            # do jeito que a pessoa digitar
            self.assertEqual(self.bruto("POST", "/api/login", {"login": escrito, "senha": "senha-forte-do-admin"}, TUNEL)[0], 200, escrito)
        A.criar_usuario(self.c, "Maria.Souza@Ankara.com.br", "Maria", "ENGENHARIA", "senha-da-maria-1", None, "teste")
        self.assertEqual(self.bruto("POST", "/api/login", {"login": "maria.souza@ankara.com.br", "senha": "senha-da-maria-1"}, TUNEL)[0], 200)
        A.criar_usuario(self.c, "João Pedro", "João", "ENGENHARIA", "senha-do-joao-12", None, "teste")
        self.assertEqual(self.q("SELECT login FROM usuarios WHERE nome='João'"), [("joao.pedro",)])

    def test_cookie_seguro_so_atras_do_https(self):
        A.configurar_acesso(self.c, "gabriel.horta", "Gabriel", "senha-forte-do-admin")
        login = {"login": "gabriel.horta", "senha": "senha-forte-do-admin"}
        st, cab, _ = self.bruto("POST", "/api/login", login, TUNEL)
        self.assertEqual(st, 200)
        self.assertIn("Secure", cab["Set-Cookie"])
        self.assertEqual(self.q("SELECT origem FROM sessoes ORDER BY rowid DESC LIMIT 1"), [("200.1.2.3",)])
        st, cab, _ = self.bruto("POST", "/api/login", login)
        self.assertNotIn("Secure", cab["Set-Cookie"])                                  # http local continua funcionando


if __name__ == "__main__":
    unittest.main()
