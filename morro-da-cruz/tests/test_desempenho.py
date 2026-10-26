"""Desempenho pelo link (D-135): texto comprimido, código da tela guardado no navegador pela impressão do conteúdo,
traçado do mapa validado pela ETag, conexão aberta entre os pedidos e sessão sem gravação a cada pedido. Pelo HTTP
(servidor real em thread, banco temporário com planilhas sintéticas)."""
import gzip
import hashlib
import http.client
import json
import os
import re
import sys
import unittest
from datetime import timedelta
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import acesso as A  # noqa: E402
import apropriacao as AP  # noqa: E402
import server  # noqa: E402
from test_acesso import SENHA, BaseHTTP  # noqa: E402


class TestDesempenhoHTTP(BaseHTTP):
    usuarios = (("eng1", "ENGENHARIA", None),)

    def http(self, metodo, rota, cab=None, corpo=None, conn=None):
        if conn is None:
            conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=20)
            self.addCleanup(conn.close)
        conn.request(metodo, rota, body=corpo, headers=cab or {})
        r = conn.getresponse()
        return r, r.read(), conn

    def cookie(self):
        r, _, _ = self.http("POST", "/api/login", {"Content-Type": "application/json", "X-MC": "1"},
                            json.dumps({"login": "eng1", "senha": SENHA}))
        self.assertEqual(r.status, 200)
        return {"Cookie": r.getheader("Set-Cookie").split(";")[0]}

    def test_codigo_da_tela_comprimido_e_guardado_pela_impressao(self):
        r, html, _ = self.http("GET", "/", {"Accept-Encoding": "gzip, deflate, br"})
        self.assertEqual((r.getheader("Content-Encoding"), r.getheader("Cache-Control")), ("gzip", "no-store"))
        html = gzip.decompress(html)
        for nome in ("app.js", "iluminado.js", "planejamento.js", "notas.js", "apropriacao.js", "app.css"):
            self.assertRegex(html, rb'="/' + re.escape(nome).encode() + rb'\?v=[0-9a-f]{12}"')
        v = re.search(rb'src="/app\.js\?v=([0-9a-f]{12})"', html).group(1).decode()
        with open(os.path.join(server.WEB, "app.js"), "rb") as f:
            original = f.read()
        self.assertEqual(v, hashlib.sha256(original).hexdigest()[:12])
        r, corpo, _ = self.http("GET", f"/app.js?v={v}", {"Accept-Encoding": "gzip"})
        self.assertEqual(r.getheader("Content-Encoding"), "gzip")
        self.assertEqual(gzip.decompress(corpo), original)
        self.assertLess(len(corpo), len(original) / 2)
        self.assertEqual(r.getheader("Cache-Control"), "public, max-age=31536000, immutable")
        r, corpo, _ = self.http("GET", "/app.js")                                 # sem gzip pedido: o arquivo como está
        self.assertEqual((r.getheader("Content-Encoding"), corpo), (None, original))
        self.assertEqual(r.getheader("Cache-Control"), "no-cache")
        r, _, _ = self.http("GET", "/app.js?v=000000000000")                     # impressão velha: pergunta de novo
        self.assertEqual(r.getheader("Cache-Control"), "no-cache")
        r, corpo, _ = self.http("GET", "/app.js", {"If-None-Match": f'"{v}"'})    # já tem: 304 sem corpo
        self.assertEqual((r.status, corpo, r.getheader("ETag")), (304, b"", f'"{v}"'))
        # pelo link, o proxy devolve o ETag fraco (W/"…"), às vezes numa lista: a comparação é a fraca
        r, corpo, _ = self.http("GET", "/app.js", {"If-None-Match": f'"outra", W/"{v}"'})
        self.assertEqual((r.status, corpo), (304, b""))
        r, _, _ = self.http("GET", "/app.js", {"If-None-Match": 'W/"000000000000"'})
        self.assertEqual(r.status, 200)
        r, _, _ = self.http("GET", "/notas.js")                                   # o código da tela abre antes do login
        self.assertEqual(r.status, 200)

    def test_tracado_do_mapa_validado_pela_etag_e_o_resto_sem_guardar(self):
        ck = self.cookie()
        r, corpo, _ = self.http("GET", "/api/mapa/geral", ck)
        etag = r.getheader("ETag")
        self.assertEqual((r.status, r.getheader("Cache-Control")), (200, "private, no-cache"))
        self.assertTrue(etag)
        r, corpo, _ = self.http("GET", "/api/mapa/geral", {**ck, "If-None-Match": etag})
        self.assertEqual((r.status, corpo), (304, b""))
        r, _, _ = self.http("GET", "/api/mapa/geral", {"If-None-Match": etag})     # sem sessão: nada de 304
        self.assertEqual(r.status, 401)
        r, corpo, _ = self.http("GET", "/api/resumo", {**ck, "Accept-Encoding": "gzip"})
        self.assertEqual((r.getheader("Cache-Control"), r.getheader("ETag")), ("no-store", None))
        self.assertEqual(r.getheader("Content-Encoding"), "gzip")
        self.assertIn("trechos", json.loads(gzip.decompress(corpo)))

    def test_conexao_aberta_entre_pedidos_e_fechada_quando_o_corpo_nao_foi_lido(self):
        r, _, conn = self.http("GET", "/app.css")
        sock = conn.sock
        r, _, conn = self.http("GET", "/app.js", conn=conn)
        self.assertEqual(r.status, 200)
        self.assertIs(conn.sock, sock)                                             # o mesmo socket nos dois pedidos
        for rota, cab in (("/api/nada", {"X-MC": "1"}), ("/api/login", {})):      # recusado antes de ler o corpo
            r, _, conn = self.http("POST", rota, {"Content-Type": "application/json", **cab}, b'{"login": "eng1"}')
            self.assertIn(r.status, (403, 404))
            self.assertEqual(r.getheader("Connection"), "close")
        r, _, _ = self.http("POST", "/api/login", {"Content-Type": "application/json", "X-MC": "1"},
                            json.dumps({"login": "eng1", "senha": SENHA}), conn=self.http("GET", "/app.css")[2])
        self.assertEqual(r.status, 200)                                            # corpo lido: a conexão segue

    def test_sessao_renovada_no_maximo_a_cada_10_min(self):
        tok, _ = A.autenticar(self.c, "eng1", SENHA, "127.0.0.1")
        sha = hashlib.sha256(tok.encode()).hexdigest()

        def expira():
            return self.q("SELECT expira_em FROM sessoes WHERE token_sha=?", sha)[0][0]
        antes = expira()
        agora = A._agora()
        with mock.patch.object(A, "_agora", return_value=agora + timedelta(minutes=9)):
            self.assertEqual(A.sessao(self.c, tok)["login"], "eng1")
        self.assertEqual(expira(), antes)                                          # 9 min depois: não grava
        with mock.patch.object(A, "_agora", return_value=agora + timedelta(minutes=11)):
            self.assertEqual(A.sessao(self.c, tok)["login"], "eng1")
        self.assertEqual(expira(), (agora + timedelta(minutes=11) + A.VALIDADE_SESSAO).isoformat(timespec="seconds"))
        with mock.patch.object(A, "_agora", return_value=agora + timedelta(minutes=11) + A.VALIDADE_SESSAO + timedelta(seconds=1)):
            self.assertIsNone(A.sessao(self.c, tok))                               # 12 h sem uso: expirou


class TestBuscaGuardada(unittest.TestCase):
    def test_texto_normalizado_e_palavras_guardados_sem_mudar_o_resultado(self):
        self.assertEqual(AP._norm("Tê  Ø63\tPE100"), "TE DN 63 PE100")
        self.assertEqual((AP._norm(None), AP._norm(63)), ("", "63"))
        self.assertEqual(AP._tokens("TUBO PEAD 63X2,3"), {"TUBO", "PEAD", "63X2,3", "63X2", "3"})
        self.assertIsInstance(AP._tokens("TUBO"), frozenset)                       # guardado: ninguém altera


if __name__ == "__main__":
    unittest.main()
