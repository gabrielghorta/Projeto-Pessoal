"""Google Drive conectado (v15): configuração no banco, conexão OAuth pelo navegador (state de uso único), fila das fotos e
dos anexos das notas, pastas por trecho e por mês, reaproveitamento sem duplicar, falha de rede sem perder nada, conexão
revogada e leitura da planilha-índice pela conta. Tudo contra um Google de mentira: nenhum acesso real ao Drive."""
import base64
import json
import os
import sys
import unittest
import urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import compras as C  # noqa: E402
import documentos as D  # noqa: E402
import drive as DR  # noqa: E402
import nfe_teste as NT  # noqa: E402
import servicos as S  # noqa: E402
from fotos_teste import jpeg  # noqa: E402
from test_acesso import TR, BaseHTTP  # noqa: E402

CLIENTE = "123456789012-abcdefghij0123456789.apps.googleusercontent.com"
PASTA = "https://drive.google.com/drive/folders/1PastaDaObraFicticia00000000000"
RAIZ = "1PastaDaObraFicticia00000000000"
PLANILHA = "https://docs.google.com/spreadsheets/d/1IndiceFicticio000000000000000000000000000AB/edit?usp=drivesdk"
INDICE = ("nome antigo,nome novo,pasta,tipo,revisão,data,link,observação\n"
          ",Morro da Cruz - Índice de Documentos,Raiz,Índice de Documentos,,2026-10-18,"
          "https://docs.google.com/spreadsheets/d/1IndiceFicticio000000000000000000000000000AB/edit?usp=drivesdk,Criado.\n"
          "Edital.pdf,Morro da Cruz - Edital de Licitação - LC 014-2026 (4894325).pdf,01_DOCUMENTOS_OFICIAIS/01_Edital_Licitacao_e_Contrato/01_Edital,"
          "Edital de Licitação,,2026-06-02,https://drive.google.com/file/d/1EditalFicticio00000000000000000/view?usp=drivesdk,Origem: x\n"
          "cache.json,cache.json,99_TEMPORARIOS_E_SISTEMA/Pastas_de_Trabalho_IA/rotas_osrm_cache,,,,"
          "https://drive.google.com/file/d/1CacheCacheCacheCacheCacheCac/view?usp=drivesdk,\n")


def id_token(email):
    carga = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"cabecalho.{carga}.assinatura"


class GoogleFalso:
    """Imita o que o drive.py usa: token (código e atualização), item, busca, criar pasta, envio retomável, export."""

    def __init__(self):
        self.itens = {RAIZ: {"id": RAIZ, "name": "ANKARA_Morro_da_Cruz", "mimeType": DR.PASTA_MIME, "parents": [], "dados": None}}
        self.n, self.envios_abertos, self.pedidos, self.falhar_rede, self.refresh_invalido = 0, {}, [], False, False

    def novo_id(self):
        self.n += 1
        return f"falso{self.n:06d}xyz"

    def __call__(self, metodo, url, cab=None, corpo=None, tempo=60):
        self.pedidos.append((metodo, url))
        if self.falhar_rede:
            raise DR.SemConexao("o servidor não alcançou o Google (bloqueado)")
        u = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(u.query)
        if url == DR.TOKEN:
            f = urllib.parse.parse_qs(corpo.decode())
            if f["grant_type"] == ["authorization_code"]:
                return 200, {}, json.dumps({"access_token": "acesso1", "expires_in": 3600, "refresh_token": "atualiza1",
                                            "scope": "https://www.googleapis.com/auth/drive openid email",
                                            "id_token": id_token("gabriel@exemplo.com")}).encode()
            if self.refresh_invalido:
                return 400, {}, json.dumps({"error": "invalid_grant"}).encode()
            return 200, {}, json.dumps({"access_token": "acesso2", "expires_in": 3600}).encode()
        if url == DR.REVOGAR:
            return 200, {}, b""
        assert (cab or {}).get("Authorization", "").startswith("Bearer "), url
        if metodo == "GET" and u.path.endswith("/export"):
            return 200, {}, INDICE.encode()
        if metodo == "GET" and u.path.startswith("/drive/v3/files/"):
            fid = urllib.parse.unquote(u.path.rsplit("/", 1)[1])
            it = self.itens.get(fid)
            if not it:
                return 404, {}, json.dumps({"error": {"code": 404, "message": "File not found"}}).encode()
            return 200, {}, json.dumps(self._publico(it)).encode()
        if metodo == "GET" and u.path == "/drive/v3/files":
            consulta = q["q"][0]
            pai = consulta.split("'")[1]
            nome = consulta.split("name = '")[1].split("' and")[0].replace("\\'", "'")
            pasta = "mimeType = '" in consulta
            achados = [self._publico(i) for i in self.itens.values() if pai in i["parents"] and i["name"] == nome
                       and (i["mimeType"] == DR.PASTA_MIME) == pasta]
            return 200, {}, json.dumps({"files": achados}).encode()
        if metodo == "POST" and u.path == "/drive/v3/files":
            m = json.loads(corpo)
            fid = self.novo_id()
            self.itens[fid] = {"id": fid, "name": m["name"], "mimeType": m["mimeType"], "parents": m["parents"], "dados": None}
            return 200, {}, json.dumps(self._publico(self.itens[fid])).encode()
        if metodo == "POST" and u.path == "/upload/drive/v3/files":
            m = json.loads(corpo)
            sessao = self.novo_id()
            self.envios_abertos[sessao] = (m, cab.get("X-Upload-Content-Type"))
            return 200, {"Location": f"https://www.googleapis.com/upload/drive/v3/files?upload_id={sessao}"}, b""
        if metodo == "PUT" and "upload_id=" in url:
            m, mime = self.envios_abertos.pop(q["upload_id"][0])
            fid = self.novo_id()
            self.itens[fid] = {"id": fid, "name": m["name"], "mimeType": mime, "parents": m["parents"], "dados": corpo}
            return 200, {}, json.dumps(self._publico(self.itens[fid])).encode()
        raise AssertionError(f"pedido inesperado: {metodo} {url}")

    @staticmethod
    def _publico(i):
        return {"id": i["id"], "name": i["name"], "mimeType": i["mimeType"], "trashed": False,
                "webViewLink": f"https://drive.google.com/{'drive/folders' if i['mimeType'] == DR.PASTA_MIME else 'file/d'}/{i['id']}"}

    def caminho(self, fid):
        partes, it = [], self.itens[fid]
        while it["parents"]:
            it = self.itens[it["parents"][0]]
            partes.append(it["name"])
        return "/".join(reversed(partes[:-1]))

    def arquivos(self):
        return [i for i in self.itens.values() if i["dados"] is not None]


class BaseDrive(BaseHTTP):
    def setUp(self):
        super().setUp()
        self.g = GoogleFalso()
        self._http, DR.HTTP = DR.HTTP, self.g
        DR._ACESSO.clear()
        DR._PASTAS.clear()

    def tearDown(self):
        DR.HTTP = self._http
        DR._ACESSO.clear()
        DR._PASTAS.clear()
        super().tearDown()

    def ligar_google(self, eng):
        self.assertEqual(eng.post("/api/drive/config", {"cliente_id": CLIENTE, "cliente_segredo": "segredo-1", "pasta_url": PASTA})[0], 200)
        st, r = eng.post("/api/drive/conectar", {})
        self.assertEqual(st, 200, r)
        estado = urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query)["state"][0]
        st, pagina = self.cliente().get(f"{DR.RETORNO}?state={estado}&code=codigo-do-google")   # sem cookie, como no retorno real
        self.assertEqual(st, 200)
        return r, pagina


class TestConexao(BaseDrive):
    def test_configurar_conectar_e_quem_pode(self):
        eng, alm = self.cliente("eng1"), self.cliente("almox1")
        self.assertEqual(alm.post("/api/drive/config", {"cliente_id": CLIENTE})[0], 403)
        self.assertEqual(eng.post("/api/drive/config", {"cliente_id": "qualquer-coisa"})[0], 422)
        self.assertEqual(eng.post("/api/drive/config", {"cliente_id": CLIENTE, "pasta_url": "https://drive.google.com/file/d/1abcdefghijk/view"})[0], 422)
        self.assertEqual(alm.post("/api/drive/conectar", {})[0], 403)
        r, pagina = self.ligar_google(eng)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query)
        self.assertTrue(r["url"].startswith(DR.AUTH))
        self.assertEqual((q["redirect_uri"][0], q["access_type"][0], q["client_id"][0]), (self.url + DR.RETORNO, "offline", CLIENTE))
        self.assertIn("auth/drive", q["scope"][0])
        self.assertIn(b"Google Drive conectado", pagina)
        st, d = eng.get("/api/drive")
        self.assertEqual((d["conectado"], d["conta"], d["pasta_id"], d["cliente_id"], d["tem_segredo"]), (True, "gabriel@exemplo.com", RAIZ, CLIENTE, True))
        self.assertEqual(alm.get("/api/drive")[0], 403)      # o Drive fica em Usuários e histórico: engenharia e adm
        d = DR.resumo(self.c, completo=False)                 # quem não configura vê o estado, não as credenciais
        self.assertTrue(d["conectado"])
        self.assertNotIn("cliente_id", d)
        self.assertNotIn("drive_cliente_segredo", json.dumps(d))
        self.assertEqual(self.q("SELECT valor FROM parametros WHERE chave='drive_token'"), [("atualiza1",)])
        self.assertTrue(self.q("SELECT 1 FROM auditoria WHERE rota=? AND login='eng1' AND status=200", DR.RETORNO))

    def test_state_de_uso_unico_e_vencido(self):
        eng = self.cliente("eng1")
        eng.post("/api/drive/config", {"cliente_id": CLIENTE, "cliente_segredo": "s", "pasta_url": PASTA})
        st, r = eng.post("/api/drive/conectar", {})
        estado = urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query)["state"][0]
        self.cliente().get(f"{DR.RETORNO}?state=forjado&code=x")                 # state errado: nada conectado, e o pedido vence
        self.assertFalse(eng.get("/api/drive")[1]["conectado"])
        self.cliente().get(f"{DR.RETORNO}?state={estado}&code=x")                # o verdadeiro já não vale (uso único)
        d = eng.get("/api/drive")[1]
        self.assertFalse(d["conectado"])
        self.assertIn("venceu", d["ultimo_erro"])
        self.assertFalse([p for p in self.g.pedidos if p[1] == DR.TOKEN])     # o código nunca foi trocado

    def test_trocar_o_cliente_desfaz_a_conexao(self):
        eng = self.cliente("eng1")
        self.ligar_google(eng)
        eng.post("/api/drive/config", {"cliente_id": "999999999999-outro0123456789.apps.googleusercontent.com"})
        self.assertFalse(eng.get("/api/drive")[1]["conectado"])


class TestFila(BaseDrive):
    def preparar(self):
        S.registrar_foto(self.c, "TRECHO", TR, "EXECUCAO", jpeg(), data_hora="2026-10-15T12:00:00", dir_fotos=self.fotos)
        self.c.commit()
        forn = C.cadastrar_fornecedor(self.c, NT.CNPJ_FORNECEDOR, "Fornecedor de Teste Ltda", "comprador")
        self.assertTrue(forn)
        nf = C.importar_nfe_xml(self.c, NT.b64(NT.xml("4321", [("T63", "TE 63", "UN", 2, 10.0)])), "nfe4321.xml", "almox1")
        self.c.commit()
        return nf

    def test_fotos_e_notas_sobem_para_a_pasta_certa_sem_duplicar(self):
        eng, alm = self.cliente("eng1"), self.cliente("almox1")
        self.preparar()
        self.assertEqual(alm.post("/api/drive/processar", {})[1], {"conectado": False})   # sem conexão: fica guardado aqui
        self.ligar_google(eng)
        self.assertEqual(eng.get("/api/drive")[1]["contagem"]["na_fila"], 2)
        st, r = alm.post("/api/drive/processar", {})                                      # qualquer pessoa logada dispara
        self.assertEqual((st, r["enviados"], r["pendentes"]), (200, 2, 0), r)
        arqs = {self.g.caminho(a["id"]): a for a in self.g.arquivos()}
        foto = next(a for c, a in arqs.items() if c.startswith("03_EXECUCAO_DE_CAMPO/01_Fotos_por_Trecho/Zona01/"))
        nota = next(a for c, a in arqs.items() if c.startswith("04_COMPRAS_E_ALMOXARIFADO/01_Notas_Fiscais/2026-10"))
        sha = self.q("SELECT sha256 FROM fotos")[0][0]
        self.assertTrue(foto["name"].startswith("Morro da Cruz - Foto de Campo - PB01_Rede_TR001 - Execução - 2026-10-15 12h00"), foto["name"])
        self.assertTrue(foto["name"].endswith(f"({sha[:8]}).jpg"))
        with open(os.path.join(self.fotos, f"{sha}.jpg"), "rb") as f:
            self.assertEqual(foto["dados"], f.read())                                    # o original, byte a byte
        self.assertIn("Nota Fiscal 4321", nota["name"])
        self.assertTrue(nota["name"].endswith(".xml"))
        # a pasta aparece na foto (ficha do trecho) e na nota (compras)
        f0 = self.cliente("eng1").get(f"/api/detalhe?tipo=TRECHO&id={TR}")[1]["fotos"][0]["drive"]
        self.assertEqual((f0["status"], f0["pasta_nome"]), ("ENVIADO", "PB01_Rede_TR001"))
        self.assertTrue(f0["caminho"].endswith("Zona01/PB01_Rede_TR001"))
        n0 = [n for n in eng.get("/api/compras")[1]["notas"] if n.get("documento_id")][0]["drive"]
        self.assertEqual(n0["status"], "ENVIADO")
        # de novo: nada a enviar; mesmo forçando o reenvio, o arquivo já no Drive é reaproveitado
        self.assertEqual(alm.post("/api/drive/processar", {})[1]["enviados"], 0)
        self.c.execute("UPDATE envios_drive SET status='PENDENTE'")
        self.c.commit()
        self.assertEqual(alm.post("/api/drive/processar", {})[1]["enviados"], 2)
        self.assertEqual(len(self.g.arquivos()), 2)
        self.assertEqual(len([i for i in self.g.itens.values() if i["name"] == "Zona01"]), 1)   # pastas também não duplicam

    def test_sem_rede_fica_na_fila_e_conexao_revogada_desconecta(self):
        eng, alm = self.cliente("eng1"), self.cliente("almox1")
        self.preparar()
        self.ligar_google(eng)
        self.g.falhar_rede = True
        r = alm.post("/api/drive/processar", {})[1]
        self.assertEqual((r["enviados"], r["pendentes"]), (0, 2))
        self.assertIn("não alcançou o Google", r["erro"])
        self.assertEqual(self.q("SELECT status, tentativas FROM envios_drive ORDER BY id LIMIT 1"), [("PENDENTE", 1)])
        self.g.falhar_rede = False
        DR._ACESSO.clear()
        self.g.refresh_invalido = True                                   # o responsável revogou o acesso no Google
        r = alm.post("/api/drive/processar", {})[1]
        self.assertIn("Conectar com o Google", r["erro"])
        d = eng.get("/api/drive")[1]
        self.assertFalse(d["conectado"])
        self.assertIn("revogada", d["ultimo_erro"])
        self.assertEqual(self.q("SELECT COUNT(*) FROM envios_drive WHERE status='PENDENTE'"), [(2,)])   # nada perdido

    def test_indice_lido_pela_conta_conectada(self):
        eng = self.cliente("eng1")
        self.ligar_google(eng)
        eng.post("/api/documentos/config", {"pasta_url": PASTA, "indice_url": PLANILHA})
        st, r = eng.post("/api/documentos/sincronizar", {"simular": True})
        self.assertEqual((st, r["novos"], r["pastas_de_trabalho"]), (200, 2, {"99_TEMPORARIOS_E_SISTEMA": 1}), r)
        self.assertTrue([p for p in self.g.pedidos if p[1].endswith("/export?mimeType=text%2Fcsv")])
        st, r = eng.post("/api/documentos/sincronizar", {"simular": False, "incluir_trabalho": True})
        self.assertEqual(r["novos"], 3)
        docs = {d["titulo"]: d for d in eng.get("/api/documentos")[1]["documentos"]}
        ed = docs["Morro da Cruz - Edital de Licitação - LC 014-2026 (4894325).pdf"]
        self.assertEqual((ed["tipo"], ed["formato"], ed["pasta_rotulo"]),
                         ("Edital de Licitação", "PDF", "Documentos oficiais / Edital Licitação e Contrato / Edital"))
        self.assertEqual(ed["abrir"], "https://drive.google.com/file/d/1EditalFicticio00000000000000000/view?usp=drivesdk")
        self.assertEqual(ed["baixar"], "https://drive.google.com/uc?export=download&id=1EditalFicticio00000000000000000")


class TestLinks(unittest.TestCase):
    def test_abrir_no_google_e_baixar_o_original(self):
        f = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view?usp=drivesdk"
        planilha_office = "https://docs.google.com/spreadsheets/d/1PlanilhaOfficeFicticia/edit?usp=drivesdk&rtpof=true&sd=true"
        self.assertEqual(D.link_abrir(f, "Memorial.docx"), "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOp/edit?rtpof=true&usp=drivesdk")
        self.assertEqual(D.link_abrir(f, "BM.xlsm"), "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOp/edit?rtpof=true&usp=drivesdk")
        self.assertEqual(D.link_abrir(f, "Prancha.pdf"), "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view?usp=drivesdk")
        self.assertEqual(D.link_abrir(PLANILHA, "Morro da Cruz - Índice de Documentos"), PLANILHA)       # nativa do Google
        self.assertEqual(D.link_baixar(planilha_office, "Edições.xlsx"), "https://drive.google.com/uc?export=download&id=1PlanilhaOfficeFicticia")
        self.assertTrue(D.link_baixar(PLANILHA, "Morro da Cruz - Índice de Documentos").endswith("/export?format=xlsx"))
        self.assertIsNone(D.link_baixar(PASTA, "pasta"))

    def test_nome_e_pasta_no_drive_sem_caractere_proibido(self):
        self.assertEqual(DR._limpo('NF 12/3: "teste"?'), "NF 12-3- -teste")
        self.assertEqual(DR._limpo("  "), "arquivo")


if __name__ == "__main__":
    unittest.main()
