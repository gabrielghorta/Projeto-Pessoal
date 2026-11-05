"""D-213: uma nota de serviço registra execução; reutilização explícita dos anexos anteriores."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(AQUI), AQUI]
import importacao as I
import importar
import notas_servico as NS
import ns_sintetica as NSS
import servicos as S
from base_real import BaseReal, TR006, TR007, TR020, b64, pdf_ns
from perfil_teste import cfg_teste_real

CLIMA = {"MANHA": "SOL", "TARDE": "SOL"}
CROQUI = b64(NSS.pdf_de_texto(["CROQUI NS 020 - TRECHOS EXECUTADOS"]))


class TestNotaUnificada(BaseReal):
    LIBERAR_TUDO = True

    def pdf(self, **kw):
        return pdf_ns(numero="020", bloco="ASSENTAMENTO", **kw)

    def enviar(self, rota="/api/ns/execucao", **kw):
        corpo = dict(tipo="SERVICO", equipe_id="Zona03", pdf_b64=b64(self.pdf()),
                     pdf_nome="ns020.pdf", croqui_b64=CROQUI, clima=CLIMA)
        return self.cli("eng1").post(rota, dict(corpo, **kw))

    def antiga(self):
        return self.ok(self.registrar_servico_historico("eng1", self.pdf(), croqui_b64=CROQUI))["id"]

    def aproveitar(self, nid, login="eng1", **kw):
        return self.cli(login).post("/api/ns/registrar-execucao",
            {"ns_id": nid, "equipe_id": "Zona03", "clima": CLIMA, **kw})

    def conferir_mapa(self):
        mapa = self.ok(self.cli("sup1").get("/api/mapa/estado?data=2026-11-05"))["camadas"]["etapas"]
        self.assertEqual({p: mapa[p]["s"] for p in (TR006, TR007, TR020)},
                         dict.fromkeys((TR006, TR007, TR020), "executado"))
        pend = self.ok(self.cli("sup1").get("/api/verificacao/pendentes"))
        self.assertEqual({p["nome"] for p in pend}, {TR006, TR007, TR020})
        self.assertEqual(self.n("intervalos_execucao", "verificado_em IS NOT NULL"), 0)

    def test_nota_de_servico_registra_execucao_e_aguarda_supervisor(self):
        r = self.ok(self.enviar())
        self.assertEqual((r["tipo"], r["fila"]), ("EXECUCAO", []))
        self.assertEqual(self.n("notas_servico", "tipo='SERVICO'"), 0)
        self.assertEqual(self.n("intervalos_execucao", "etapa='ASSENTADO'"), 3)
        self.assertEqual(self.n("intervalos_execucao", "etapa='REATERRADO'"), 0)
        self.conferir_mapa()
        # Quem informou não pode conferir a própria execução.
        self.recusa(self.cli("eng1").post("/api/trecho/verificar", {"trecho": TR006}), 422, "informou")

    def test_api_anterior_servico_agora_tambem_registra_execucao(self):
        self.ok(self.enviar("/api/ns"))
        self.conferir_mapa()

    def test_sem_equipe_nao_arquiva_como_planejamento(self):
        self.recusa(self.enviar("/api/ns", equipe_id=None), 422, "agora registra execução")
        self.assertEqual(self.n("notas_servico"), 0)

    def test_sem_croqui_ou_clima_nao_inventa_dados(self):
        self.recusa(self.enviar(croqui_b64=None), 422, "croqui")
        self.assertEqual((self.n("notas_servico"), self.n("intervalos_execucao"), self.n("clima")), (0, 0, 0))

    def test_aproveita_anexos_da_nota_antiga_sem_mudar_original(self):
        nid = self.antiga()
        antes = dict(self.c.execute("SELECT * FROM notas_servico WHERE id=?", (nid,)).fetchone())
        r = self.ok(self.aproveitar(nid))
        self.assertEqual((r["origem_servico_id"], r["tipo"], r["equipe_id"]), (nid, "EXECUCAO", "Zona03"))
        self.assertEqual(dict(self.c.execute("SELECT * FROM notas_servico WHERE id=?", (nid,)).fetchone()), antes)
        self.assertEqual(self.n("documentos"), 2)  # armazenamento por hash, sem cópias desnecessárias
        lista = self.ok(self.cli("eng1").get("/api/ns?tipo=SERVICO"))
        self.assertEqual((lista[0]["execucao_id"], lista[0]["execucao_status"]), (r["id"], "REGISTRADA"))
        self.assertEqual(self.c.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.conferir_mapa()

    def test_repetir_aproveitamento_nao_duplica_nem_transfere_equipe(self):
        nid = self.antiga()
        r = self.ok(self.aproveitar(nid))
        r2 = self.ok(self.aproveitar(nid))
        self.assertEqual(r2["id"], r["id"])
        self.assertTrue(r2["ja_registrada"])
        self.assertEqual((self.n("intervalos_execucao"), self.n("notas_servico")), (3, 2))
        self.recusa(self.aproveitar(nid, equipe_id="Zona04"), 422, "Não é transferida")

    def test_reenvio_do_pdf_antigo_no_formulario_unico_tambem_funciona(self):
        nid = self.antiga()
        r = self.ok(self.enviar())
        self.assertEqual(self.c.execute("SELECT ns_execucao_id FROM ns_execucoes_origem WHERE ns_servico_id=?", (nid,)).fetchone()[0], r["id"])
        self.recusa(self.enviar(), 422, "já foi enviada")
        self.conferir_mapa()

    def test_execucao_identica_ja_existente_e_vinculada_sem_repetir(self):
        nid = self.antiga()
        r = self.ok(self.enviar(pdf_b64=b64(self.pdf(girar=True))))
        r2 = self.ok(self.aproveitar(nid))
        self.assertEqual(r2["id"], r["id"])
        self.assertEqual((self.n("notas_servico"), self.n("intervalos_execucao")), (2, 3))

    def test_aproveitamento_exige_equipe_clima_e_anexo_disponivel(self):
        nid = self.antiga()
        self.recusa(self.aproveitar(nid, equipe_id=None), 422, "equipe")
        self.c.execute("UPDATE documentos SET arquivo='../fora_da_pasta.pdf'")
        self.recusa(self.aproveitar(nid), 422, "não está disponível")
        self.assertEqual((self.n("intervalos_execucao"), self.n("clima"), self.n("ns_execucoes_origem")), (0, 0, 0))

    def test_permissoes_e_nota_anulada(self):
        nid = self.antiga()
        for login in ("sup1", "rh1", "enc3", "almox1", "topo1", "cad1"):
            self.assertEqual(self.aproveitar(nid, login)[0], 403, login)
            self.assertEqual(self.cli(login).post("/api/ns/execucao", {})[0], 403, login)
        self.ok(self.cli("eng1").post("/api/ns/anular", {"ns_id": nid, "motivo": "nota cancelada"}))
        self.recusa(self.aproveitar(nid), 422, "vigente")
        self.assertEqual(self.n("intervalos_execucao"), 0)

    def test_v24_para_v25_preserva_equipes_e_nao_inventa_execucao(self):
        nid = self.antiga()
        equipes = [tuple(r) for r in self.c.execute("SELECT * FROM equipes ORDER BY id")]
        self.c.execute("DROP TABLE ns_execucoes_origem")
        self.c.execute("DELETE FROM schema_versao WHERE versao>24")
        self.c.execute("INSERT OR IGNORE INTO schema_versao VALUES (24,'2026-11-05','estado anterior à D-213')")
        rel = importar.aplicar(self.db, I.DIR_PLANILHAS, cfg=cfg_teste_real(),
                              dir_relatorios=os.path.join(self.tmp, "migracao25"))
        self.assertEqual((rel["esquema_antes"], rel["esquema_depois"]), (24, S.VERSAO_ESQUEMA))
        self.assertEqual([tuple(r) for r in self.c.execute("SELECT * FROM equipes ORDER BY id")], equipes)
        self.assertEqual((self.n("ns_execucoes_origem"), self.n("intervalos_execucao")), (0, 0))
        self.assertEqual(NS.detalhe(self.c, nid)["tipo"], "SERVICO")
        self.assertEqual(self.c.execute("PRAGMA foreign_key_check").fetchall(), [])


class TestNotaUnificadaSemLiberacao(BaseReal):
    def test_nota_aceita_fica_com_pendencia_real_sem_execucao_ficticia(self):
        r = self.ok(self.registrar("eng1", "SERVICO", pdf_ns(numero="020", bloco="ASSENTAMENTO"),
            equipe_id="Zona03", croqui_b64=CROQUI, clima=CLIMA))
        self.assertEqual(r["tipo"], "EXECUCAO")
        self.assertTrue(r["fila"])
        self.assertIn("falta a liberação topográfica", str(r))
        self.assertEqual(self.n("intervalos_execucao"), 0)


if __name__ == "__main__":
    unittest.main()
