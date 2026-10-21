"""Ciclo completo da Zona01 (etapa Z), pelo HTTP, em ambiente ISOLADO com cópia das planilhas reais.

Banco, fotos, documentos e backups ficam numa pasta temporária; o perfil de controles é o TESTE (cfg_teste_real). O banco
operacional (dados/) e as planilhas originais são conferidos por hash antes e depois: a demonstração não gera movimento
nem aprovação no ambiente operacional. Pulado quando as planilhas oficiais não estão em planilhas/.

Passos (um teste por passo, em ordem, sobre o mesmo banco):
 1 planejar · 2 solicitar e comprar · 3 receber parcialmente e conferir · 4 reservar e retirar · 5 execução parcial com
 fotos, soldas e cadastro de campo · 6 devolver sobra e manter saldo com a equipe · 7 corrigir lançamentos · 8 concluir,
 verificar e atualizar o mapa · 9 proposta de medição de TESTE com pendências · 10 importar revisão sem perder histórico ·
 11 restaurar backup e conferir integridade.

Com a variável MC_EVIDENCIAS=<arquivo.json>, grava os números do ciclo (base de docs/EVIDENCIAS_CICLO_ZONA01.md).
"""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from openpyxl import load_workbook

AQUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(AQUI)
sys.path.insert(0, APP)
sys.path.insert(0, AQUI)
import acesso as A  # noqa: E402
import backup  # noqa: E402
import importacao as I  # noqa: E402
import importar  # noqa: E402
import nfe_teste as NT  # noqa: E402
import regras as R  # noqa: E402
import server  # noqa: E402
import servicos as S  # noqa: E402
from fotos_teste import jpeg  # noqa: E402
from perfil_teste import cfg_teste_real  # noqa: E402
from test_acesso import SENHA, Cliente  # noqa: E402

CFG = I.carregar_config()
TEM_DADOS = all(I.caminho(CFG, k) for k in ("redes", "conexoes", "evidencias", "bm", "reajuste"))
TR = "Zona01_PB01_Rede_TR001"
D0, D1, D2, D3 = "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-16"
FUTURO = "2099-01-01"
USUARIOS = (("eng1", "ENGENHARIA", None), ("eng2", "ENGENHARIA", None), ("almox1", "ALMOXARIFADO", None),
            ("almox2", "ALMOXARIFADO", None), ("enc1", "EQUIPE", "Zona01"), ("adm", "ADMINISTRACAO", None))
TUDO_MED = dict.fromkeys(R.CHECKLIST_CONFERENCIA_MEDICAO, True)


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def hashes_operacionais():
    """Banco operacional e planilhas originais: não podem mudar com a demonstração."""
    arqs = [os.path.join(I.DIR_PLANILHAS, n) for n in sorted(os.listdir(I.DIR_PLANILHAS)) if not n.startswith(".")]
    op = os.path.join(APP, "dados", "morro_da_cruz.db")
    if os.path.exists(op):
        arqs.append(op)
    return {a: sha(a) for a in arqs if os.path.isfile(a)}


@unittest.skipUnless(TEM_DADOS, "planilhas oficiais ausentes em planilhas/")
class CicloZona01(unittest.TestCase):
    ev = {}

    @classmethod
    def setUpClass(cls):
        cls.hash_antes = hashes_operacionais()
        cls.raiz = tempfile.mkdtemp(prefix="ciclo_zona01_")
        cls.dados = os.path.join(cls.raiz, "dados")
        cls.fotos = os.path.join(cls.dados, "fotos")
        os.makedirs(cls.fotos)
        cls.db = os.path.join(cls.dados, "obra.db")
        cls.rels = os.path.join(cls.dados, "relatorios")
        cls.rel_carga = importar.aplicar(cls.db, I.DIR_PLANILHAS, cfg=cfg_teste_real(), dir_relatorios=cls.rels)
        c = S.conectar(cls.db)
        for login, perfil, eq in USUARIOS:
            A.criar_usuario(c, login, login.upper(), perfil, SENHA, eq, "demonstração isolada")
        t = S.alvo(c, "TRECHO", TR)
        cls.tid, cls.L, cls.de = t["id"], float(t["extensao_m"]), int(t["de_mm"])
        cls.tubo = f"CAESB-PEAD-DE{cls.de}"
        luva = c.execute("""SELECT id FROM materiais WHERE propriedade='ANKARA' AND unidade='UN'
                            ORDER BY (descricao LIKE 'LUVA%' AND descricao LIKE '%' || ? || ' MM%') DESC, (descricao LIKE '%LUVA%') DESC,
                                     id LIMIT 1""",
                         (cls.de,)).fetchone()
        cls.luva = luva[0]
        assert c.execute("SELECT 1 FROM materiais WHERE id=?", (cls.tubo,)).fetchone(), cls.tubo
        c.close()
        cls.ev.update(trecho=TR, trecho_id=cls.tid, extensao_m=cls.L, tubo=cls.tubo, luva=cls.luva,
                      carga={"status": cls.rel_carga["status"], "trechos": cls.rel_carga["auditoria"].get("contagens", {}).get("trechos")})
        cls.subir()

    @classmethod
    def subir(cls):
        cls.srv_conn = S.conectar(cls.db)
        cls._antigos = (server.CONN, server.DB_PATH, server.DIR_FOTOS)
        server.CONN, server.DB_PATH, server.DIR_FOTOS = cls.srv_conn, cls.db, cls.fotos
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        url = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.u = {}
        for login, _, _ in USUARIOS:
            cl = Cliente(url)
            cl.entrar(login)
            cls.u[login] = cl

    @classmethod
    def parar(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()
        server.CONN, server.DB_PATH, server.DIR_FOTOS = cls._antigos
        cls.srv_conn.close()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "httpd", None) and cls.thread.is_alive():
            cls.parar()
        destino = os.environ.get("MC_EVIDENCIAS")
        if destino:
            with open(destino, "w", encoding="utf-8") as f:
                json.dump(cls.ev, f, ensure_ascii=False, indent=2, default=str)
        copia = os.environ.get("MC_CICLO_COPIA")          # cópia do banco final para as telas (pasta isolada)
        if copia:
            shutil.rmtree(copia, ignore_errors=True)
            shutil.copytree(cls.dados, copia)
        shutil.rmtree(cls.raiz)

    # ---------------------------------------------------------------- utilitários
    def ok(self, login, rota, corpo, **kw):
        st, r = self.u[login].post(rota, corpo, **kw)
        self.assertEqual(st, 200, f"{login} {rota}: {r}")
        return r

    def recusa(self, login, rota, corpo, status=422):
        st, r = self.u[login].post(rota, corpo)
        self.assertEqual(st, status, f"{login} {rota}: {r}")
        return r.get("erro")

    def get(self, rota, login="eng1"):
        st, r = self.u[login].get(rota)
        self.assertEqual(st, 200, f"{rota}: {r}")
        return r

    def q(self, sql, *a):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(sql, a).fetchall()
        finally:
            c.close()

    def material(self, mid):
        return {m["material_id"]: m for m in self.get(f"/api/relatorios?ini=2026-10-01&fim=2026-10-31")["materiais"]}[mid]

    # ---------------------------------------------------------------- 1. planejar
    def test_01_planejar(self):
        self.recusa("enc1", "/api/programacao", {"data": D2, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                                 "servico": "ASSENTAMENTO"}, 403)
        r = self.ok("eng1", "/api/programacao", {"data": D2, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                                 "servico": "ASSENTAMENTO", "ini_m": 0, "fim_m": self.L,
                                                 "materiais": [{"material_id": self.tubo, "quantidade": 40},
                                                               {"material_id": self.luva, "quantidade": 6}]})
        type(self).prog_id = r["id"]
        p = self.get(f"/api/programacoes?ini={D2}&fim={D2}&frente=Zona01")
        falt = {f["material_id"]: f for f in p["faltantes"]}
        self.assertEqual((falt[self.tubo]["previsto"], falt[self.tubo]["faltante"]), (40, 40))
        self.assertEqual(self.q("SELECT COUNT(*) FROM movimentos")[0][0], 0)                   # planejar não movimenta
        self.ev["1_planejar"] = {"programacao": p["programacoes"][0]["status"], "faltante_tubo": falt[self.tubo]["faltante"],
                                 "faltante_luva": falt[self.luva]["faltante"]}

    # ---------------------------------------------------------------- 2. solicitar e comprar
    def test_02_solicitar_e_comprar(self):
        sid = self.ok("eng1", "/api/solicitacao", {"data": D0, "itens": [{"material_id": self.luva, "quantidade": 20}],
                                                   "motivo": "Zona01 TR001 — programação de 16/10"})["id"]
        erro = self.recusa("eng1", "/api/solicitacao/decidir", {"solicitacao_id": sid, "aprovar": True})
        self.ok("eng2", "/api/solicitacao/decidir", {"solicitacao_id": sid, "aprovar": True})
        self.recusa("almox1", "/api/fornecedor", {"cnpj": NT.CNPJ_FORNECEDOR, "nome": "Fornecedor de Teste Ltda"}, 403)
        fid = self.ok("adm", "/api/fornecedor", {"cnpj": NT.CNPJ_FORNECEDOR, "nome": "Fornecedor de Teste Ltda"})["id"]
        pid = self.ok("adm", "/api/pedido", {"numero": "PC-Z01-001", "data": D0, "fornecedor_id": fid, "solicitacao_id": sid,
                                             "itens": [{"material_id": self.luva, "quantidade": 20, "valor_unitario": 12.5}]})["id"]
        type(self).pedido_id = pid
        self.assertEqual(self.q("SELECT COUNT(*) FROM movimentos")[0][0], 0)                   # pedido não é estoque
        m = self.material(self.luva)
        self.assertEqual((m["solicitado"], m["comprado"], m["recebido"], m["a_receber"]), (20, 20, 0, 20))
        self.ev["2_comprar"] = {"autoaprovacao_recusada": erro, "pedido": "PC-Z01-001", "comprado": 20, "estoque_luva": m["saldo_almox"]}

    # ---------------------------------------------------------------- 3. receber parcialmente e conferir
    def test_03_receber_parcial_e_conferir(self):
        x = NT.xml(9001, [("LV", "Luva eletrofusão", "UN", 20, 12.5)], emissao=f"{D0}T15:00:00-03:00")
        nf = self.ok("almox1", "/api/nf/importar-xml", {"conteudo_b64": NT.b64(x), "nome": "nfe9001.xml"})["nf_id"]
        self.assertEqual(self.q("SELECT status FROM notas_fiscais WHERE id=?", nf), [("A_CONFERIR",)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM movimentos")[0][0], 0)                   # NF importada não movimenta
        lid = self.q("SELECT id FROM nf_linhas WHERE nf_id=?", nf)[0][0]
        pi = self.q("SELECT id FROM pedido_itens WHERE pedido_id=?", self.pedido_id)[0][0]
        self.ok("almox2", "/api/nf/conferir", {"nf_id": nf, "pedido_id": self.pedido_id,
                                               "linhas": [{"linha_id": lid, "material_id": self.luva, "fator": 1, "pedido_item_id": pi}]})
        ni = self.q("SELECT id FROM nf_itens WHERE nf_id=?", nf)[0][0]
        self.ok("almox1", "/api/recebimento", {"nf_id": nf, "data": D1, "itens": [{"nf_item_id": ni, "quantidade": 12}], "documento": "canhoto 1"})
        self.assertEqual(self.material(self.luva)["quarentena"], 12)                           # quarentena, não estoque
        ri = self.q("SELECT id FROM recebimento_itens")[0][0]
        self.ok("almox1", "/api/inspecao", {"recebimento_item_id": ri, "aceito": 10, "recusado": 2, "laudo": "LAUDO-Z01-1",
                                             "data": D1, "motivo_recusa": "2 luvas com ovalização"})
        self.ok("almox1", "/api/movimento", {"data": D1, "material_id": self.tubo, "quantidade": 120, "tipo": "ROMANEIO_CAESB",
                                             "documento": "ROM-CAESB-123"})
        self.ok("almox1", "/api/movimento", {"data": D1, "material_id": self.tubo, "quantidade": 120, "tipo": "ROMANEIO_CAESB",
                                             "documento": "ROM-CAESB-123 (lançado de novo por engano)"})
        m = self.material(self.luva)
        self.assertEqual((m["recebido"], m["saldo_almox"], m["quarentena"], m["a_receber"]), (10, 10, 0, 10))
        self.assertEqual(self.q("SELECT COUNT(*) FROM medicao_lancamentos")[0][0], 0)          # recebido ≠ faturável
        self.assertTrue(os.listdir(os.path.join(self.dados, "documentos")))                    # XML guardado com hash
        self.ev["3_receber"] = {"nf": 9001, "entregue": 12, "aceito": 10, "recusado": 2, "a_receber": m["a_receber"],
                                "romaneio_tubo": 120, "romaneio_duplicado": 120}

    # ---------------------------------------------------------------- 4. reservar e retirar
    def test_04_reservar_e_retirar(self):
        corpo = {"data": D2, "equipe_id": "Zona01", "material_id": self.tubo, "quantidade": 40, "alvo_tipo": "TRECHO", "alvo_id": TR}
        r1 = self.ok("almox1", "/api/reserva", corpo, cabecalhos={"X-Idem": "ciclo-reserva-tubo"})
        r2 = self.ok("almox1", "/api/reserva", corpo, cabecalhos={"X-Idem": "ciclo-reserva-tubo"})   # clique repetido
        self.assertEqual(r1, r2)
        self.assertEqual(self.q("SELECT COUNT(*) FROM reservas WHERE material_id=?", self.tubo)[0][0], 1)
        self.ok("almox1", "/api/reserva", dict(corpo, material_id=self.luva, quantidade=6))
        self.assertEqual(self.get(f"/api/programacoes?ini={D2}&fim={D2}")["faltantes"][0]["faltante"], 0)
        ck = self.ok("almox1", "/api/checkin", {"data": D2, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                                "materiais": [{"material_id": self.tubo, "quantidade": 40},
                                                              {"material_id": self.luva, "quantidade": 6}]})["id"]
        type(self).ck1 = ck
        self.assertEqual(self.q("SELECT status, checkin_id FROM programacoes WHERE id=?", self.prog_id), [("REALIZADA", ck)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM reservas WHERE status='ATIVA'")[0][0], 0)       # consumidas na retirada
        self.ev["4_retirar"] = {"reserva_repetida_mesma_resposta": r1 == r2, "retirado_tubo": 40, "retirado_luva": 6,
                                "programacao": "REALIZADA"}

    # ---------------------------------------------------------------- 5. execução parcial, fotos, soldas, cadastro de campo
    def test_05_execucao_parcial(self):
        self.ok("eng1", "/api/liberacao", {"trecho_id": TR, "ini_m": 0, "fim_m": self.L, "data": D1, "referencia": "NS-Z01-001"})
        self.ok("enc1", "/api/clima", {"data": D2, "equipe_id": "Zona01", "MANHA": "SOL", "TARDE": "SOL"})
        self.recusa("enc1", "/api/apontamento", {"data": D2, "equipe_id": "Zona02", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                                 "intervalos": [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 10}]}, 403)
        cad_enc = self.recusa("enc1", "/api/apontamento", {"data": D2, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                                           "intervalos": [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 30},
                                                                          {"etapa": "CADASTRO_CAMPO", "ini_m": 0, "fim_m": 30}]}, 403)
        self.assertIn("aba Cadastro de campo", cad_enc)                     # o levantamento é da equipe terceirizada
        ap = self.ok("enc1", "/api/apontamento", {"data": D2, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                                  "intervalos": [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 30}]})["id"]
        type(self).ap1 = ap
        self.recusa("enc1", "/api/cadastro-campo", {"trecho_id": TR, "ini_m": 0, "fim_m": 30, "data": D2, "referencia": "caderneta 12"}, 403)
        type(self).cad1 = self.ok("eng1", "/api/cadastro-campo", {"trecho_id": TR, "ini_m": 0, "fim_m": 30, "data": D2,
                                                                  "referencia": "caderneta 12"})["id"]
        self.recusa("enc1", "/api/apontamento", {"data": D2, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                                 "intervalos": [{"etapa": "ASSENTADO", "ini_m": 20, "fim_m": 35}]})    # sobreposição
        futuro = self.recusa("enc1", "/api/clima", {"data": FUTURO, "equipe_id": "Zona01", "MANHA": "SOL", "TARDE": "SOL"})
        self.assertIn("data futura", futuro)
        for cat in ("SINALIZACAO", "EXECUCAO"):
            self.ok("enc1", "/api/foto", {"alvo_tipo": "TRECHO", "alvo_id": TR, "categoria": cat, "conteudo_b64": jpeg(),
                                          "data_hora": f"{D2}T10:00:00"})
        foto_ruim = self.recusa("enc1", "/api/foto", {"alvo_tipo": "TRECHO", "alvo_id": TR, "categoria": "EXECUCAO",
                                                      "conteudo_b64": "AAAAbm90IGFuIGltYWdl"})
        sid = self.ok("enc1", "/api/solda", {"data": D2, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                             "tipo": "ELETROFUSAO", "quantidade": 4, "soldador": "Soldador A"})["id"]
        self.recusa("enc1", "/api/solda/verificar", {"solda_id": sid, "resultado": "APROVADA"}, 403)
        self.ok("eng2", "/api/solda/verificar", {"solda_id": sid, "resultado": "APROVADA"})
        d = self.get(f"/api/detalhe?tipo=TRECHO&id={TR}")
        self.assertEqual(d["intervalos"]["etapas"]["ASSENTADO"]["metros"], 30)
        self.assertEqual(d["soldas"]["aprovadas"], 4)
        self.ev["5_execucao"] = {"assentado_m": 30, "cadastro_campo_m": 30, "fotos": 2, "foto_invalida_recusada": foto_ruim,
                                 "soldas_aprovadas": 4, "liberacao": "NS-Z01-001",
                                 "data_futura_recusada": futuro}

    # ---------------------------------------------------------------- 6. devolver sobra e manter saldo com a equipe
    def test_06_devolver_e_manter_saldo(self):
        self.ok("almox1", "/api/checkout", {"checkin_id": self.ck1, "itens": [
            {"material_id": self.tubo, "aplicado": 30, "sobra": 6, "fica_com_equipe": 4},
            {"material_id": self.luva, "aplicado": 4, "sobra": 2}]})
        t = self.material(self.tubo)
        self.assertEqual((t["saldo_almox"], t["com_equipes"], t["aplicado"]), (240 - 40 + 6, 4, 30))
        self.ev["6_checkout"] = {"tubo_aplicado": 30, "tubo_sobra": 6, "tubo_com_equipe": 4, "luva_aplicada": 4, "luva_sobra": 2}

    # ---------------------------------------------------------------- 7. corrigir lançamentos
    def test_07_corrigir(self):
        # a retificação substitui os intervalos: a referência do levantamento é informada de novo (não é herdada;
        # sem ela, o detalhe aponta "levantamento sem registro de referência")
        # o levantamento (registro próprio da engenharia) é corrigido antes: sem isso o assentado não encolhe por baixo dele
        motivo = "trena: 28 m assentados, não 30"
        novos = [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 28}]
        self.assertIn(f"cadastro de campo #{self.cad1}", self.recusa("eng1", "/api/intervalos/retificar", {
            "ref_tipo": "APONTAMENTO", "ref_id": self.ap1, "intervalos": novos, "motivo": motivo, "simular": True}))
        cad = [{"etapa": "CADASTRO_CAMPO", "ini_m": 0, "fim_m": 28, "referencia": "caderneta 12 (corrigida)"}]
        self.ok("eng1", "/api/intervalos/retificar", {"ref_tipo": "CADASTRO_CAMPO", "ref_id": self.cad1, "intervalos": cad,
                                                      "motivo": motivo, "simular": True})
        self.assertEqual(self.q("SELECT COUNT(*) FROM retificacoes_intervalos")[0][0], 0)        # prévia não grava
        self.ok("eng1", "/api/intervalos/retificar", {"ref_tipo": "CADASTRO_CAMPO", "ref_id": self.cad1, "intervalos": cad, "motivo": motivo})
        previa = self.ok("eng1", "/api/intervalos/retificar", {"ref_tipo": "APONTAMENTO", "ref_id": self.ap1, "intervalos": novos,
                                                               "motivo": motivo, "simular": True})
        self.ok("eng1", "/api/intervalos/retificar", {"ref_tipo": "APONTAMENTO", "ref_id": self.ap1, "intervalos": novos, "motivo": motivo})
        self.assertEqual(self.q("SELECT etapa, fim_m FROM intervalos_execucao WHERE anulado_por IS NULL ORDER BY etapa"),
                         [("ASSENTADO", 28.0), ("CADASTRO_CAMPO", 28.0)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM intervalos_execucao WHERE anulado_por IS NOT NULL")[0][0], 2)  # histórico
        mv = self.q("SELECT id FROM movimentos WHERE tipo='APLICADO' AND material_id=?", self.tubo)[0][0]
        self.ok("almox2", "/api/retificar", {"movimento_id": mv, "destino": {"aplicado": 28, "sobra": 2},
                                             "motivo": "aplicado corrigido com a retificação do assentado (28 m)"})
        dup = self.q("SELECT id FROM movimentos WHERE tipo='ROMANEIO_CAESB' ORDER BY id DESC LIMIT 1")[0][0]
        self.recusa("almox2", "/api/estorno", {"movimento_id": dup, "motivo": ""})
        self.ok("almox2", "/api/estorno", {"movimento_id": dup, "motivo": "romaneio ROM-CAESB-123 lançado duas vezes"})
        t = self.material(self.tubo)
        self.assertEqual((t["recebido"], t["saldo_almox"], t["aplicado"], t["com_equipes"]), (120, 88, 28, 4))
        self.assertEqual(self.q("SELECT COUNT(*) FROM movimentos")[0][0] >= 9, True)             # nada apagado
        self.ev["7_corrigir"] = {"retificacao": motivo, "antes": previa["resumo_antes"] if "resumo_antes" in previa else None,
                                 "assentado_efetivo_m": 28, "intervalos_anulados_preservados": 2, "aplicado_tubo": 28,
                                 "estorno": "romaneio duplicado", "saldo_tubo": t["saldo_almox"]}

    # ---------------------------------------------------------------- 8. concluir, verificar e atualizar o mapa
    def test_08_concluir_verificar_mapa(self):
        self.ok("enc1", "/api/clima", {"data": D3, "equipe_id": "Zona01", "MANHA": "SOL", "TARDE": "CHUVA_FRACA_TENDA"})
        ck = self.ok("almox1", "/api/checkin", {"data": D3, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                                "materiais": [{"material_id": self.tubo, "quantidade": 50}]})["id"]
        resto = round(self.L - 28, 6)
        self.ok("enc1", "/api/apontamento", {"data": D3, "equipe_id": "Zona01", "alvo_tipo": "TRECHO", "alvo_id": TR,
                                             "intervalos": [{"etapa": "ASSENTADO", "ini_m": 28, "fim_m": self.L},
                                                            {"etapa": "REATERRADO", "ini_m": 0, "fim_m": self.L}]})
        self.ok("eng1", "/api/cadastro-campo", {"trecho_id": TR, "ini_m": 28, "fim_m": self.L, "data": D3, "referencia": "caderneta 13"})
        self.ok("enc1", "/api/foto", {"alvo_tipo": "TRECHO", "alvo_id": TR, "categoria": "CONCLUIDO", "conteudo_b64": jpeg(),
                                      "data_hora": f"{D3}T16:00:00"})
        self.ok("almox1", "/api/checkout", {"checkin_id": ck, "itens": [
            {"material_id": self.tubo, "aplicado": resto, "sobra": round(54 - resto, 6)}]})
        m = self.get(f"/api/mapa/estado?data={D3}")
        nome = TR
        antes = (m["status"].get(nome), m["verificacao"].get(nome))
        ids = [r[0] for r in self.q("SELECT id FROM intervalos_execucao WHERE anulado_por IS NULL AND trecho_id=?", self.tid)]
        self.recusa("enc1", "/api/intervalo/verificar", {"intervalo_id": ids[0]}, 403)          # a equipe não verifica
        for iid in ids:
            self.ok("eng2", "/api/intervalo/verificar", {"intervalo_id": iid})
        m = self.get(f"/api/mapa/estado?data={D3}")
        depois = (m["status"].get(nome), m["verificacao"].get(nome))
        self.assertEqual(antes, ("CONCLUIDO_MES", "INFORMADO"))
        self.assertEqual(depois, ("CONCLUIDO_MES", "VERIFICADO"))
        self.assertEqual(self.q("SELECT concluido FROM execucao WHERE alvo_id=?", self.tid), [(1,)])
        self.assertFalse(self.q("SELECT 1 FROM intervalos_execucao WHERE anulado_por IS NULL AND sem_cadastro_campo=1"))
        pend = self.get(f"/api/detalhe?tipo=TRECHO&id={TR}")["pendencias"]
        self.assertFalse([p for p in pend if p["area"].startswith("1. Levantamento")], pend)   # levantamento com referência
        t = self.material(self.tubo)
        self.assertAlmostEqual(t["aplicado"], self.L)                                          # material = assentado
        self.ev["8_concluir"] = {"mapa_antes_verificacao": antes, "mapa_depois": depois, "aplicado_tubo_total": t["aplicado"],
                                 "saldo_tubo": t["saldo_almox"], "com_equipes": t["com_equipes"]}

    # ---------------------------------------------------------------- 9. proposta de medição de TESTE com pendências
    def test_09_medicao_teste(self):
        mid = self.ok("eng1", "/api/medicao", {"numero": 1, "periodo_ini": "2026-10-01", "periodo_fim": "2026-10-31"})["id"]
        self.recusa("eng1", "/api/medicao", {"numero": 2, "periodo_ini": "2026-11-01", "periodo_fim": "2026-11-30", "tipo": "OFICIAL"})
        self.ok("eng1", "/api/ok-fiscal", {"alvo_tipo": "TRECHO", "alvo_id": TR, "data": D3})
        self.recusa("eng1", "/api/ok-fiscal", {"alvo_tipo": "TRECHO", "alvo_id": TR, "data": D3})          # clique repetido
        self.assertEqual(self.get(f"/api/mapa/estado?data={D3}&medicao={mid}")["status"][TR], "OK_FISCAL")
        r = self.get(f"/api/medicao?id={mid}")
        lanc = [l for g in r["gavetas"].values() for l in g["lancamentos"]]
        ass = sum(l["quantidade"] for l in lanc if l["servico"] == "ASSENTAMENTO" and l["status"] == "PROPOSTO")
        self.assertAlmostEqual(ass, self.L, places=3)                                            # 28 + resto, sem os 2 m do erro
        solda = [l for l in lanc if l["servico"] == "SOLDA"]
        self.assertEqual([(l["quantidade"], l["status"]) for l in solda], [(4.0, "PENDENTE")])
        self.assertGreater(r["pendentes"], 0)
        self.assertTrue(r["teste"])
        el = self.get(f"/api/medicao/elegibilidade?id={mid}")
        self.assertEqual({l["nome"]: l["situacao"] for l in el["linhas"]}[TR], "PROPOSTO_NESTA")
        self.recusa("eng2", "/api/medicao/fechar", {"medicao_id": mid})                         # sem conferência
        self.ok("eng2", "/api/medicao/conferir", {"medicao_id": mid, "resultado": "CONFORME", "checklist": TUDO_MED})
        self.ok("eng2", "/api/medicao/fechar", {"medicao_id": mid})
        st, xlsx = self.u["eng1"].get(f"/api/medicao/exportar?id={mid}")
        self.assertEqual(st, 200)
        wb = load_workbook(io.BytesIO(xlsx))
        self.assertIn("TESTE — NÃO OFICIAL", wb["RESUMO"]["A1"].value)
        r = self.get(f"/api/medicao?id={mid}")
        type(self).medicao_id, type(self).valor_congelado = mid, r["valor_pi"]
        self.assertEqual(self.q("SELECT tipo, status, fechada_por FROM medicoes"), [("TESTE", "FECHADA", "eng2")])
        self.assertEqual(self.q("SELECT valor FROM parametros WHERE chave='medicao_oficial_liberada'") or [("NAO",)], [("NAO",)])
        self.assertEqual(self.q("SELECT etapa FROM cadastro WHERE trecho_id=?", self.tid), [("1_PRONTO",)])
        self.ev["9_medicao"] = {"assentamento_proposto_m": round(ass, 3), "solda": "4 aprovadas, PENDENTE (D-31)",
                                "pendentes": r["pendentes"], "propostos": sum(1 for l in lanc if l["status"] == "PROPOSTO"),
                                "valor_pi_teste": r["valor_pi"], "total_teste": r["valor_total"], "conferencia": "CONFORME por eng2",
                                "status": "FECHADA (TESTE)", "regras_bloqueadas": sorted({x["decisao"] for x in r["regras"]
                                                                                        if x["situacao"] == "BLOQUEADA" and x["decisao"]})}

    # ---------------------------------------------------------------- 10. importar revisão sem perder histórico
    def test_10_revisao_sem_perder_historico(self):
        self.parar()                                                                             # importação: servidor parado
        antes = {t: self.q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in importar.OPERACIONAIS
                 if self.q("SELECT 1 FROM sqlite_master WHERE name=?", t)}
        hist = {t: self.q(f"SELECT COUNT(*) FROM {t} WHERE alvo_id=?", self.tid)[0][0]
                for t in ("checkins", "apontamentos", "fotos", "soldas", "medicao_lancamentos", "movimentos")}
        pl = os.path.join(self.raiz, "planilhas_rev")
        shutil.copytree(I.DIR_PLANILHAS, pl)
        p = os.path.join(pl, CFG["arquivos"]["redes"])
        wb = load_workbook(p, data_only=True)
        ws = wb["REDE"]
        linha = next(r for r in range(6, ws.max_row + 1) if ws.cell(r, 18).value == TR)
        obs_nova = "REVISÃO DE TESTE: recobrimento conferido em campo"
        ws.cell(linha, 28, obs_nova)                                                             # coluna AB (observação)
        wb.save(p)
        wb.close()
        cfg = json.loads(json.dumps(cfg_teste_real()))
        ctl = dict(cfg["controles"][0], id="CTRL-TESTE revisão do ciclo Zona01")
        ctl["fontes"] = dict(ctl["fontes"], redes=backup.sha256(p))
        cfg["controles"] = [ctl]
        rel = importar.aplicar(self.db, pl, cfg=cfg, dir_relatorios=self.rels)
        self.assertEqual(rel["status"], "CONCLUIDA")
        self.assertTrue(rel["auditoria"]["contagens_ok"])
        depois = {t: self.q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in antes}
        self.assertEqual(depois, antes)                                                          # nenhum registro perdido
        self.assertEqual({t: self.q(f"SELECT COUNT(*) FROM {t} WHERE alvo_id=?", self.tid)[0][0] for t in hist}, hist)
        self.assertEqual(self.q("SELECT observacao FROM trechos WHERE id=?", self.tid), [(obs_nova,)])
        self.assertTrue(self.q("SELECT 1 FROM alteracoes WHERE entidade_id=? AND campo='observacao'", self.tid))
        c = S.conectar(self.db)
        try:
            self.assertEqual(S.resumo_medicao(c, self.medicao_id)["valor_pi"], self.valor_congelado)   # medição fechada congelada
        finally:
            c.close()
        self.ev["10_revisao"] = {"status": rel["status"], "backup_antes": bool(rel.get("backup")), "contagens_ok": True,
                                 "registros_operacionais": sum(antes.values()), "historico_TR001": hist,
                                 "campo_alterado": "observacao", "medicao_fechada_inalterada": True}

    # ---------------------------------------------------------------- 11. restaurar backup e conferir integridade
    def test_11_backup_e_restauracao(self):
        pasta = backup.criar(self.db, os.path.join(self.dados, "backups"), self.fotos)
        v = backup.verificar_detalhado(pasta)
        self.assertTrue(v["integro"] and v["completo"], v)
        conteudo = backup.conteudo(self.db)
        anexos = {os.path.join(r, n): sha(os.path.join(r, n)) for d in ("fotos", "documentos")
                  for r, _, ns in os.walk(os.path.join(self.dados, d)) for n in ns}
        # perda simulada: uma foto apagada, um documento apagado e um lançamento depois do backup
        foto = next(a for a in anexos if os.sep + "fotos" + os.sep in a)
        doc = next(a for a in anexos if os.sep + "documentos" + os.sep in a)
        os.remove(foto)
        os.remove(doc)
        c = S.conectar(self.db)
        S.registrar_clima(c, "2026-10-17", "Zona01", "MANHA", "PARALISADO_CHUVA")
        c.close()
        self.assertNotEqual(backup.conteudo(self.db), conteudo)
        seg = backup.restaurar(pasta, self.db, self.fotos)
        self.assertEqual(backup.conteudo(self.db), conteudo)                                     # banco idêntico ao backup
        self.assertEqual({a: sha(a) for a in anexos}, anexos)                                    # fotos e documentos de volta
        self.assertTrue(backup.verificar_detalhado(seg)["integro"])                              # estado anterior guardado
        self.subir()
        d = self.get(f"/api/detalhe?tipo=TRECHO&id={TR}")
        self.assertEqual(d["fotos_faltando"], [])
        self.assertTrue(all(f["validacao"] not in (None, "INVALIDA", "ARQUIVO_AUSENTE") for f in d["fotos"]))
        aud = self.get(f"/api/auditoria?alvo_id={self.tid}")
        self.assertTrue(aud)
        self.parar()
        self.ev["11_restauracao"] = {"backup": os.path.basename(pasta), "integro": True, "completo": True,
                                     "tabelas_conferidas": len(conteudo), "anexos_conferidos": len(anexos),
                                     "banco_identico": True, "backup_de_seguranca": os.path.basename(seg),
                                     "auditoria_TR001": len(aud)}

    # ---------------------------------------------------------------- isolamento
    def test_12_ambiente_operacional_intacto(self):
        self.assertEqual(hashes_operacionais(), self.hash_antes)
        self.ev["12_isolamento"] = {"arquivos_conferidos": len(self.hash_antes), "inalterados": True}


if __name__ == "__main__":
    unittest.main()
