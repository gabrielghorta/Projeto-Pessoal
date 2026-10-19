"""Módulo A — acesso, permissões no servidor, autoria, auditoria, reenvio e concorrência, testados PELO HTTP
(servidor real em thread, banco temporário com planilhas sintéticas). Nenhum usuário real é criado."""
import http.cookiejar
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import acesso as A  # noqa: E402
import server  # noqa: E402
import servicos as S  # noqa: E402
from test_importacao import Base  # noqa: E402

TR = "Zona01_PB01_Rede_TR001"
D = "2026-10-15"
SENHA = "senha-de-teste-123"


class Cliente:
    def __init__(self, url):
        self.url = url
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def req(self, metodo, rota, corpo=None, cabecalhos=None, app=True):
        h = {"Content-Type": "application/json"}
        if app and metodo == "POST":
            h["X-MC"] = "1"
        h.update(cabecalhos or {})
        r = urllib.request.Request(self.url + rota, data=None if corpo is None else json.dumps(corpo).encode(), headers=h,
                                   method=metodo)
        try:
            with self.op.open(r, timeout=20) as resp:
                dados = resp.read()
                return resp.status, (json.loads(dados) if resp.headers.get_content_type() == "application/json" else dados)
        except urllib.error.HTTPError as e:
            dados = e.read()
            try:
                return e.code, json.loads(dados)
            except ValueError:
                return e.code, dados

    def get(self, rota):
        return self.req("GET", rota)

    def post(self, rota, corpo, **kw):
        return self.req("POST", rota, corpo, **kw)

    def entrar(self, login, senha=SENHA):
        st, r = self.post("/api/login", {"login": login, "senha": senha})
        assert st == 200, r
        return r["usuario"]


class BaseHTTP(Base):
    usuarios = (("eng1", "ENGENHARIA", None), ("eng2", "ENGENHARIA", None), ("almox1", "ALMOXARIFADO", None),
                ("almox2", "ALMOXARIFADO", None), ("enc1", "EQUIPE", "Zona01"), ("adm", "ADMINISTRACAO", None))

    def setUp(self):
        super().setUp()
        self.aplicar()
        self.c = self.conectar()
        self.criar_usuarios()
        self.srv_conn = S.conectar(self.db)
        self._antigos = (server.CONN, server.DB_PATH, server.DIR_FOTOS)
        server.CONN, server.DB_PATH, server.DIR_FOTOS = self.srv_conn, self.db, self.fotos
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def criar_usuarios(self):
        for login, perfil, eq in self.usuarios:
            A.criar_usuario(self.c, login, login.upper(), perfil, SENHA, eq)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        server.CONN, server.DB_PATH, server.DIR_FOTOS = self._antigos
        self.srv_conn.close()
        super().tearDown()

    def cliente(self, login=None):
        c = Cliente(self.url)
        if login:
            c.entrar(login)
        return c

    def n(self, tabela, onde="1=1", *args):
        return self.q(f"SELECT COUNT(*) FROM {tabela} WHERE {onde}", *args)[0][0]


class TestSemUsuarios(BaseHTTP):
    usuarios = ()

    def test_sem_usuarios_nada_abre_e_orienta_a_criar_o_primeiro(self):
        cl = self.cliente()
        st, r = cl.get("/api/sessao")
        self.assertEqual((st, r.get("sem_usuarios")), (401, True))
        self.assertIn("usuarios.py criar", r["erro"])
        self.assertEqual(cl.get("/api/resumo")[0], 401)
        self.assertEqual(cl.post("/api/login", {"login": "x", "senha": "y" * 10})[0], 401)
        self.assertEqual(cl.get("/")[0], 200)                                   # a página de login abre


class TestSenhaESessao(BaseHTTP):
    def test_senha_so_como_hash_e_regras(self):
        h = self.q("SELECT senha FROM usuarios WHERE login='eng1'")[0][0]
        self.assertTrue(h.startswith("pbkdf2_sha256$200000$") and SENHA not in h)
        self.assertTrue(A.conferir_senha(SENHA, h) and not A.conferir_senha("outra", h))
        with self.assertRaisesRegex(S.RegraViolada, "10 caracteres"):
            A.criar_usuario(self.c, "novo", "Novo", "ENGENHARIA", "curta")
        with self.assertRaisesRegex(S.RegraViolada, "exige a equipe"):
            A.criar_usuario(self.c, "novo", "Novo", "EQUIPE", SENHA)
        with self.assertRaisesRegex(S.RegraViolada, "Perfil inválido"):
            A.criar_usuario(self.c, "novo", "Novo", "SUPER", SENHA)

    def test_login_invalido_generico_bloqueio_por_tentativas_e_saida(self):
        cl = self.cliente()
        for _ in range(5):
            st, r = cl.post("/api/login", {"login": "eng1", "senha": "errada-errada"})
            self.assertEqual((st, r["erro"]), (401, "Login ou senha inválidos."))
        st, r = cl.post("/api/login", {"login": "eng1", "senha": SENHA})
        self.assertEqual(st, 429)                                                # mesmo com a senha certa
        self.assertEqual(self.n("auditoria", "rota='/api/login' AND status=401 AND login='eng1'"), 5)
        self.assertNotIn("errada", self.q("SELECT corpo FROM auditoria LIMIT 1")[0][0])   # senha nunca vai para o log
        cl2 = self.cliente("eng2")
        self.assertEqual(cl2.get("/api/sessao")[0], 200)
        cl2.post("/api/logout", {})
        self.assertEqual(cl2.get("/api/resumo")[0], 401)

    def test_sem_sessao_api_fotos_e_mapa_fechados_e_gravacao_sem_cabecalho_recusada(self):
        cl = self.cliente()
        self.assertEqual(cl.get("/api/resumo")[0], 401)
        self.assertEqual(cl.get("/mapa/")[0], 401)
        self.assertEqual(cl.get("/fotos/x.jpg")[0], 401)
        st, _ = cl.post("/api/movimento", {"data": D, "material_id": "CAESB-PEAD-DE63", "quantidade": 10, "tipo": "ROMANEIO_CAESB"})
        self.assertEqual(st, 401)
        self.assertEqual(self.n("movimentos"), 0)
        self.assertEqual(self.n("auditoria", "rota='/api/movimento' AND status=401"), 1)
        logado = self.cliente("almox1")
        st, r = logado.req("POST", "/api/movimento", {"data": D, "material_id": "CAESB-PEAD-DE63", "quantidade": 10,
                                                      "tipo": "ROMANEIO_CAESB"}, app=False)
        self.assertEqual(st, 403)                                                # sem X-MC (proteção contra CSRF)
        self.assertEqual(self.n("movimentos"), 0)


class TestPermissoesEAutoria(BaseHTTP):
    def test_permissao_insuficiente_nao_grava_e_fica_na_auditoria(self):
        almox = self.cliente("almox1")
        st, r = almox.post("/api/ok-fiscal", {"alvo_tipo": "TRECHO", "alvo_id": TR, "data": D})
        self.assertEqual(st, 403)
        self.assertIn("OK interno", r["erro"])
        st, _ = almox.post("/api/usuarios", {"acao": "criar", "login": "x1", "nome": "X", "perfil": "ADMINISTRACAO", "senha": SENHA})
        self.assertEqual(st, 403)
        self.assertEqual(self.n("usuarios", "login='x1'"), 0)
        self.assertEqual(self.n("auditoria", "login='almox1' AND status=403"), 2)
        enc = self.cliente("enc1")
        self.assertEqual(enc.post("/api/movimento", {"data": D, "material_id": "CAESB-PEAD-DE63", "quantidade": 5,
                                                     "tipo": "ROMANEIO_CAESB"})[0], 403)   # o encarregado não movimenta estoque
        self.assertEqual(almox.get("/api/usuarios")[0], 403)                    # usuários: só Engenharia e Administração
        eng = self.cliente("eng1")
        self.assertEqual(eng.get("/api/usuarios")[0], 200)
        self.assertEqual(eng.get("/api/auditoria")[0], 200)                     # engenharia consulta o histórico
        objeto = "/api/auditoria?alvo_id=" + S.alvo(self.c, "TRECHO", TR)["id"]
        self.assertEqual((enc.get("/api/auditoria")[0], enc.get(objeto)[0]), (403, 403))   # o encarregado não abre essas telas
        self.assertEqual(eng.get(objeto)[0], 200)

    def test_cada_perfil_consulta_so_as_proprias_telas(self):
        enc, almox, eng, adm = (self.cliente(x) for x in ("enc1", "almox1", "eng1", "adm"))
        self.assertEqual(enc.get("/api/sessao")[1]["usuario"]["telas"], ["campo", "diario", "iluminado", "interferencias"])
        for rota in ("/api/resumo", "/api/mapa/estado", "/api/buscar?q=TR001"):             # comuns: mapa e busca
            self.assertEqual((enc.get(rota)[0], almox.get(rota)[0]), (200, 200), rota)
        for rota in ("/api/estoque", "/api/movimentos", "/api/compras", "/api/medicoes", "/api/relatorios", "/api/planilhas"):
            self.assertEqual(enc.get(rota)[0], 403, rota)                                   # encarregado: mapa e campo
        for rota in ("/api/estoque", "/api/movimentos", "/api/compras", "/api/checkins"):
            self.assertEqual(almox.get(rota)[0], 200, rota)                                 # almoxarife: + almoxarifado
        for rota in ("/api/medicoes", "/api/relatorios", "/api/planilhas", "/api/usuarios"):
            self.assertEqual(almox.get(rota)[0], 403, rota)
            self.assertEqual((eng.get(rota)[0], adm.get(rota)[0]), (200, 200), rota)         # engenharia e adm: tudo
        st, r = enc.get("/api/estoque")
        self.assertIn("não abre esta tela", r["erro"])

    def test_excluir_so_conta_sem_historico(self):
        eng = self.cliente("eng1")
        novo = {"acao": "criar", "login": "errado.digitado", "nome": "Errado", "perfil": "EQUIPE", "senha": SENHA, "equipe_id": "Zona01"}
        self.assertEqual(eng.post("/api/usuarios", novo)[0], 200)
        self.assertEqual(eng.post("/api/usuarios", {"acao": "excluir", "login": "errado.digitado"})[0], 200)
        self.assertEqual(self.n("usuarios", "login='errado.digitado'"), 0)
        self.cliente("almox2")                                                              # entrou: já tem histórico
        st, r = eng.post("/api/usuarios", {"acao": "excluir", "login": "almox2"})
        self.assertEqual(st, 422)
        self.assertIn("Desativar", r["erro"])
        self.assertEqual(self.n("usuarios", "login='almox2'"), 1)
        self.assertEqual(eng.post("/api/usuarios", {"acao": "excluir", "login": "eng1"})[0], 422)   # nunca o próprio
        self.assertEqual(self.cliente("almox1").post("/api/usuarios", {"acao": "excluir", "login": "almox2"})[0], 403)

    def test_equipe_so_lanca_para_a_propria_e_autor_e_o_usuario_da_sessao(self):
        enc = self.cliente("enc1")
        st, r = enc.post("/api/clima", {"data": D, "equipe_id": "Zona02", "MANHA": "SOL", "TARDE": "SOL"})
        self.assertEqual(st, 403)
        self.assertIn("Zona01", r["erro"])
        self.assertEqual(enc.post("/api/clima", {"data": D, "equipe_id": "Zona01", "MANHA": "SOL", "TARDE": "SOL"})[0], 200)
        st, r = enc.post("/api/apontamento", {"data": D, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                              "intervalos": [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 10}],
                                              "informado_por": "Outra Pessoa"})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT informado_por FROM apontamentos"), [("enc1",)])          # não o nome digitado
        self.assertEqual(self.q("SELECT informado_por FROM intervalos_execucao"), [("enc1",)])
        iid = self.q("SELECT id FROM intervalos_execucao")[0][0]
        eng = self.cliente("eng1")
        st, r = eng.post("/api/intervalo/verificar", {"intervalo_id": iid, "verificado_por": "enc1"})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT verificado_por FROM intervalos_execucao"), [("eng1",)])
        self.assertEqual(enc.post("/api/intervalo/verificar", {"intervalo_id": iid})[0], 403)   # equipe não verifica

    def test_verificacao_segregada_pela_identidade_real(self):
        for t in ("MANHA", "TARDE"):
            S.registrar_clima(self.c, D, "Zona01", t, "SOL")
        eng1 = self.cliente("eng1")
        st, _ = eng1.post("/api/apontamento", {"data": D, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                               "intervalos": [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 10}]})
        self.assertEqual(st, 200)
        iid = self.q("SELECT id FROM intervalos_execucao")[0][0]
        st, r = eng1.post("/api/intervalo/verificar", {"intervalo_id": iid, "verificado_por": "outra pessoa"})
        self.assertEqual(st, 422)                                                # não adianta digitar outro nome
        self.assertIn("não pode verificá-lo", r["erro"])
        self.assertEqual(self.cliente("eng2").post("/api/intervalo/verificar", {"intervalo_id": iid})[0], 200)

    def test_administracao_gerencia_usuarios_e_desativado_perde_a_sessao(self):
        adm = self.cliente("adm")
        st, r = adm.post("/api/usuarios", {"acao": "criar", "login": "topo1", "nome": "Topógrafo", "perfil": "TOPOGRAFIA", "senha": SENHA})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.q("SELECT criado_por FROM usuarios WHERE login='topo1'"), [("adm",)])
        topo = self.cliente("topo1")
        self.assertEqual(topo.get("/api/resumo")[0], 200)
        self.assertEqual(adm.post("/api/usuarios", {"acao": "alterar", "login": "topo1", "ativo": False})[0], 200)
        self.assertEqual(topo.get("/api/resumo")[0], 401)
        st, r = adm.post("/api/usuarios", {"acao": "alterar", "login": "adm", "ativo": False})
        self.assertEqual(st, 422)                                                # não desativa a si mesmo


class TestReenvioConcorrenciaEAtomicidade(BaseHTTP):
    ENTRADA = {"data": D, "material_id": "CAESB-PEAD-DE63", "quantidade": 30, "tipo": "ROMANEIO_CAESB", "documento": "ROM-1"}

    def test_reenvio_com_a_mesma_chave_nao_duplica(self):
        almox = self.cliente("almox1")
        for _ in range(3):                                                       # clique repetido / rede instável
            st, r = almox.post("/api/movimento", self.ENTRADA, cabecalhos={"X-Idem": "chave-1"})
            self.assertEqual(st, 200)
        self.assertEqual(self.n("movimentos"), 1)
        self.assertEqual(self.n("auditoria", "rota='/api/movimento' AND resultado LIKE 'reenvio%'"), 2)
        st, r = almox.post("/api/movimento", dict(self.ENTRADA, quantidade=31), cabecalhos={"X-Idem": "chave-1"})
        self.assertEqual(st, 422)                                                # chave reaproveitada em outra operação
        self.assertEqual(self.n("movimentos"), 1)
        self.assertEqual(self.q("SELECT responsavel FROM movimentos"), [("almox1",)])
        outro = self.cliente("almox2")                                          # a chave é por usuário
        self.assertEqual(outro.post("/api/movimento", self.ENTRADA, cabecalhos={"X-Idem": "chave-1"})[0], 200)
        self.assertEqual(self.n("movimentos"), 2)

    def test_dois_usuarios_ao_mesmo_tempo_nao_consomem_o_mesmo_saldo(self):
        a1, a2 = self.cliente("almox1"), self.cliente("almox2")
        self.assertEqual(a1.post("/api/movimento", self.ENTRADA)[0], 200)
        largada, res = threading.Barrier(2), {}

        def reservar(nome, cl, equipe):
            largada.wait()
            res[nome] = cl.post("/api/reserva", {"data": D, "equipe_id": equipe, "material_id": "CAESB-PEAD-DE63", "quantidade": 20})

        ts = [threading.Thread(target=reservar, args=a) for a in (("a1", a1, "Zona01"), ("a2", a2, "Zona02"))]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(sorted(r[0] for r in res.values()), [200, 422])
        self.assertEqual(self.q("SELECT SUM(quantidade) FROM reservas WHERE status='ATIVA'"), [(20.0,)])
        self.assertEqual(S.disponivel(self.c, "CAESB-PEAD-DE63"), 10)

    def test_falha_no_meio_desfaz_a_operacao_e_o_registro_de_reenvio(self):
        enc = self.cliente("enc1")
        enc.post("/api/clima", {"data": D, "equipe_id": "Zona01", "MANHA": "SOL", "TARDE": "SOL"})
        corpo = {"data": D, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                 "intervalos": [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 10}]}
        with mock.patch.object(S, "_atualizar_execucao_trecho", side_effect=RuntimeError("queda simulada")):
            st, r = enc.post("/api/apontamento", corpo, cabecalhos={"X-Idem": "k-falha"})
        self.assertEqual(st, 500)
        for t in ("apontamentos", "apontamento_quantidades", "intervalos_execucao", "requisicoes"):
            self.assertEqual(self.n(t), 0, t)
        self.assertEqual(self.n("auditoria", "rota='/api/apontamento' AND status=500"), 1)
        st, r = enc.post("/api/apontamento", corpo, cabecalhos={"X-Idem": "k-falha"})   # reenvio depois da falha executa
        self.assertEqual(st, 200)
        self.assertEqual(self.n("apontamentos"), 1)

    def test_auditoria_registra_aceite_e_recusa_com_objeto(self):
        almox = self.cliente("almox1")
        almox.post("/api/movimento", self.ENTRADA)
        almox.post("/api/estorno", {"movimento_id": 1, "motivo": ""})
        ls = A.consultar_auditoria(self.c, alvo_id="1")
        self.assertEqual([(a["rota"], a["status"], a["login"]) for a in ls], [("/api/estorno", 422, "almox1")])
        self.assertIn("motivo", ls[0]["resultado"].lower())
        st, r = self.cliente("eng1").get("/api/auditoria?login=almox1")
        self.assertEqual([x["status"] for x in r][:2], [422, 200])


if __name__ == "__main__":
    unittest.main()
