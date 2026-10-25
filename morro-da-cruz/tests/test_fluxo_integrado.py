"""Ponta a ponta do fluxo integrado, pelo HTTP, sobre o banco das planilhas do repositório (tests/base_real.py) com NS e
NF-e sintéticas: da NS de topografia ao cadastro aprovado, cada etapa acendendo no mapa (regras.etapa_trecho), o OK
interno sem medição aberta entrando sozinho quando ela abre, e o almoxarife da NF ao estoque. É o mesmo caminho do
docs/ROTEIRO_DE_TESTE_MEDICAO.md. Os trechos são os da NS sintética da Zona03 PB08 (TR020, TR007 e TR006)."""
import os
import sys
import unittest
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import compras as C  # noqa: E402
import nfe_teste as NT  # noqa: E402
import ns_sintetica as NSS  # noqa: E402
import relogio as RL  # noqa: E402
import regras as R  # noqa: E402
import servicos as S  # noqa: E402
from base_real import TR006, TR007, TR020, BaseReal, b64, data_ns, pdf_ns  # noqa: E402
from fotos_teste import jpeg  # noqa: E402
from test_ns_dia import grupo, pdf_dia  # noqa: E402

TRES = [TR020, TR007, TR006]
CAMINHO = ["NÓ6.1 - TÊ 160x110", "NÓ9.1 - TÊ 160x160", "CH_VRP-15 (CAIXA DA VRP)"]


class TestCaminhoAteAMedicao(BaseReal):
    def etapas(self, login="eng1"):
        st, est = self.cli(login).get(f"/api/mapa/estado?data={self.hoje}")
        self.assertEqual(st, 200, est)
        e = est["camadas"]["etapas"]
        return {n: e.get(n, {"s": "nao"})["s"] for n in TRES}, est

    def tudo(self, etapa, login="eng1"):
        self.assertEqual(self.etapas(login)[0], dict.fromkeys(TRES, etapa))

    def test_da_topografia_ao_cadastro_aprovado(self):
        self.hoje = RL.hoje().isoformat()
        h = date.fromisoformat(self.hoje)
        self.tudo("nao")
        # 1. NS de topografia: os três ficam liberados
        self.ok(self.registrar("eng1", "TOPOGRAFIA", pdf_ns(numero="012")))
        self.tudo("liberado")
        # 2. Dados da obra: a equipe da Zona03 programada para hoje nos três; o almoxarife libera
        self.ok(self.cli("eng1").post("/api/dados-obra/programar", {"linhas": TRES, "nos": [], "equipe_id": "Zona03",
                                                                    "servico": "ASSENTAMENTO", "data": self.hoje}))
        self.ok(self.cli("almox1").post("/api/dados-obra/liberar", {"data": self.hoje, "equipe_id": "Zona03", "linhas": TRES,
                                                                    "nos": [], "materiais": []}))
        etapas, est = self.etapas()
        self.assertEqual(etapas, dict.fromkeys(TRES, "execucao"))                      # em execução hoje
        self.assertLessEqual(set(TRES), {p["alvo_id"] for p in est["pins"]})          # o pino em cada um (e no nó que os liga)
        self.assertLessEqual(set(TRES), set(est["camadas"]["em_campo"]))
        # 3. NS do dia com assentamento e reaterro, enviada pela engenharia: executado, aguardando verificação
        r = self.ok(self.cli("eng1").post("/api/ns/dia", {
            "equipe_id": "Zona03", "pdf_b64": b64(pdf_dia([grupo(CAMINHO, [277.99, 295.98], obs=["ASSENTAMENTO E REATERRO"] * 3)],
                                                         numero="030", data=h)),
            "pdf_nome": "ns_030.pdf", "croqui_b64": b64(NSS.pdf_de_texto(["CROQUI NS 030"])), "croqui_nome": "c.pdf",
            "clima": {"MANHA": "SOL", "TARDE": "SOL"}}))
        self.assertEqual(r["fila"], [])
        self.tudo("executado")
        self.assertEqual({n: e["parcial"] for n, e in self.etapas()[1]["camadas"]["etapas"].items() if n in TRES}, dict.fromkeys(TRES, False))
        # 4. o supervisor (outra pessoa) verifica e envia as 3 fotos de cada trecho: pronto para o OK
        sup = self.cli("sup1")
        self.assertEqual({x["nome"] for x in sup.get("/api/verificacao/pendentes")[1]}, set(TRES))
        for n in TRES:
            self.ok(sup.post("/api/trecho/verificar", {"trecho": n}))
        self.tudo("verificado")
        for n in TRES:
            for cat in R.FOTOS_TRECHO:
                self.ok(sup.post("/api/foto", {"alvo_tipo": "TRECHO", "alvo_id": n, "categoria": cat, "conteudo_b64": jpeg(),
                                               "data_hora": f"{self.hoje}T10:00:00"}))
        self.tudo("pronto")
        self.assertTrue(all(sup.get(f"/api/caminho?trecho={n}")[1]["pronto_para_ok"] for n in TRES))
        # 5. NS de cadastro: cadastro de campo feito (e o supervisor confere também o levantamento)
        self.ok(self.registrar("eng1", "CADASTRO", pdf_ns(numero="013", bloco="CADASTRO", data=data_ns(h))))
        self.tudo("campo")
        for n in TRES:
            self.ok(sup.post("/api/trecho/verificar", {"trecho": n}))
        self.tudo("pronto")
        # 6. OK interno sem medição aberta: espera (SEM_MEDICAO_ABERTA); a medição abre e os lançamentos entram uma vez
        eng = self.cli("eng1")
        for n in TRES:
            self.assertEqual(self.ok(eng.post("/api/ok-fiscal", {"alvo_tipo": "TRECHO", "alvo_id": n, "data": self.hoje})), {"medicao_id": None})
        self.tudo("ok")
        self.assertEqual(self.n("medicao_lancamentos"), 0)
        rest = self.ok(eng.get("/api/medicao/restricoes"))
        self.assertEqual(len([l for l in rest["linhas"] if l["restricao"] == "SEM_MEDICAO_ABERTA"]), 3)
        ini, fim = h.replace(day=1).isoformat(), (date(h.year + h.month // 12, h.month % 12 + 1, 1)).isoformat()
        fim = date.fromordinal(date.fromisoformat(fim).toordinal() - 1).isoformat()
        med = self.ok(eng.post("/api/medicao", {"numero": 1, "periodo_ini": ini, "periodo_fim": fim}))
        self.assertEqual(med["liberados"], 3)
        n_lanc = self.n("medicao_lancamentos")
        self.assertGreater(n_lanc, 0)
        self.assertEqual(self.ok(eng.post("/api/medicao", {"numero": 2, "periodo_ini": "2099-01-01", "periodo_fim": "2099-01-31"}))["liberados"], 0)
        self.assertEqual(self.n("medicao_lancamentos"), n_lanc)                       # sem duplicar
        self.assertEqual(self.ok(eng.get(f"/api/medicao/caminho?id={med['id']}"))["ok_nesta"], sorted(TRES))
        # 7. a esteira pela ficha (cadastro) até a aprovação da Caesb registrada: o cadastro entra na medição (gaveta 3)
        cad, tid = self.cli("cad1"), self.tid[TR020]
        self.ok(cad.post("/api/cadastro", {"trecho_id": tid, "destino": "2_ENVIADO", "dados": {"empresa": "Cadastro Ltda", "data_envio": self.hoje}, "data": self.hoje}))
        self.assertEqual(self.etapas()[0][TR020], "cad_andamento")
        self.ok(cad.post("/api/cadastro", {"trecho_id": tid, "destino": "3_RECEBIDO", "dados": {"arquivos": ["TR020.dwg"]}, "data": self.hoje}))
        self.ok(eng.post("/api/cadastro/conferencia", {"trecho_id": tid, "resultado": "CONFORME",
                                                       "checklist": dict.fromkeys(R.CHECKLIST_CONFERENCIA_CADASTRO, True)}))
        self.ok(cad.post("/api/cadastro", {"trecho_id": tid, "destino": "4_GDOC_ANALISE", "dados": {"protocolo_gdoc": "GDOC-77"}, "data": self.hoje}))
        self.ok(cad.post("/api/cadastro", {"trecho_id": tid, "destino": "6_APROVADO", "dados": {"memorando_eset": "ESET-9"}, "data": self.hoje}))
        self.assertEqual(self.etapas()[0][TR020], "cadastrado")
        self.assertTrue(self.c.execute("SELECT 1 FROM medicao_lancamentos WHERE gaveta=3 AND alvo_id=?", (tid,)).fetchone())


class TestRecusasDaOrdem(BaseReal):
    """Execução sem topografia, cadastro sem execução, OK sem verificação, OK sem fotos e retificação que quebra a ordem."""

    def test_cada_recusa_diz_o_que_falta(self):
        hoje = RL.hoje()
        eng, enc = self.cli("eng1"), self.cli("enc3")
        enc.post("/api/clima", {"data": hoje.isoformat(), "equipe_id": "Zona03", "MANHA": "SOL", "TARDE": "SOL"})
        ap = {"data": hoje.isoformat(), "equipe_id": "Zona03", "alvo_tipo": "TRECHO", "alvo_id": TR020, "motivo_sem_ns": "teste",
              "intervalos": [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 50}]}
        self.recusa(eng.post("/api/apontamento", ap), 422, "falta a liberação topográfica")           # execução sem topografia
        self.ok(self.registrar("eng1", "TOPOGRAFIA", pdf_ns(numero="012")))
        r = self.ok(self.registrar("eng1", "CADASTRO", pdf_ns(numero="013", bloco="CADASTRO", data=data_ns(hoje))))
        self.assertEqual(r["gravado_m"], 0.0)                                                          # cadastro sem execução
        self.assertIn("falta a execução", " ".join(p for s in r["segmentos"] for p in s["pendencias"]))
        self.ok(eng.post("/api/apontamento", dict(ap, intervalos=[{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 277.99},
                                                               {"etapa": "REATERRADO", "ini_m": 0, "fim_m": 277.99}])))
        ok = {"alvo_tipo": "TRECHO", "alvo_id": TR020, "data": hoje.isoformat()}
        self.recusa(eng.post("/api/ok-fiscal", ok), 422, "fotos obrigatórias")                         # OK sem fotos
        for cat in R.FOTOS_TRECHO:
            self.ok(eng.post("/api/foto", {"alvo_tipo": "TRECHO", "alvo_id": TR020, "categoria": cat, "conteudo_b64": jpeg()}))
        self.recusa(eng.post("/api/ok-fiscal", ok), 422, "verificação do supervisor")                  # OK sem verificação
        # retificação que quebra a ordem: a liberação usada pela execução não sai
        lib = self.c.execute("SELECT id FROM etapas_complementares WHERE trecho_id=? AND etapa='LIBERACAO_TOPOGRAFICA'",
                             (self.tid[TR020],)).fetchone()[0]
        with self.assertRaisesRegex(S.RegraViolada, "retifique antes a execução"):
            S.anular_etapa_complementar(self.c, lib, "liberação errada", "eng1")


class TestNotaFiscalPeloHTTP(BaseReal):
    """O almoxarife: importa o XML (vários, um por pedido), confere com a sugestão, recebe, aceita tudo; a nota sem pedido
    só libera depois da aprovação de outra pessoa."""

    def test_da_nf_ao_estoque_e_a_aprovacao(self):
        alm, eng = self.cli("almox1"), self.cli("eng1")
        mat = self.c.execute("SELECT id FROM materiais WHERE propriedade<>'CAESB' AND unidade='UN' ORDER BY id LIMIT 1").fetchone()[0]
        xmls = [NT.b64(NT.xml(18734, [(mat, "peça (código = id do material)", "UN", 4, 12.0)])),
                NT.b64(NT.xml(18735, [(mat, "peça", "UN", 1, 12.0)]))]
        r = self.ok(alm.post("/api/nf/importar-xml", {"conteudo_b64": xmls[0], "nome": "a.xml"}))
        self.assertIn("fornecedor_novo", r)                                          # o fornecedor vem do XML, com confirmação
        for x in xmls:
            self.ok(alm.post("/api/nf/importar-xml", {"conteudo_b64": x, "nome": "n.xml", "cadastrar_fornecedor": True}))
        notas = self.ok(alm.get("/api/almox/notas"))
        nf = next(n for n in notas if n["numero"] == "18734")
        self.assertEqual(nf["sugestoes"][0]["material_id"], mat)
        self.assertEqual(self.ok(alm.post("/api/nf/conferir", {"nf_id": nf["id"], "pedido_id": 0, "linhas": [
            {"linha_id": nf["linhas"][0]["id"], "material_id": mat}]}))["sem_pedido"], True)
        ni = self.c.execute("SELECT id FROM nf_itens WHERE nf_id=?", (nf["id"],)).fetchone()[0]
        rec = self.ok(alm.post("/api/recebimento", {"nf_id": nf["id"], "data": RL.hoje().isoformat(), "itens": [{"nf_item_id": ni, "quantidade": 4}]}))
        rid = rec["id"] if isinstance(rec, dict) else rec
        self.ok(alm.post("/api/inspecao/entrega", {"recebimento_id": rid, "itens": [], "data": RL.hoje().isoformat()}))   # Aceitar tudo
        est = {m["id"]: m for m in self.ok(alm.get("/api/estoque"))}[mat]
        self.assertEqual(est["aguardando_aprovacao"], 4)
        self.recusa(alm.post("/api/nf/aprovar", {"nf_id": nf["id"]}), 403, "")         # o almoxarifado não aprova
        self.recusa(self.cli("adm").post("/api/nf/aprovar", {"nf_id": 999999}), 422, "")
        self.ok(eng.post("/api/nf/aprovar", {"nf_id": nf["id"]}))
        est = {m["id"]: m for m in self.ok(alm.get("/api/estoque"))}[mat]
        self.assertEqual(est["aguardando_aprovacao"], 0)


if __name__ == "__main__":
    unittest.main()
