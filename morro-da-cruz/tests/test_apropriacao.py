"""Apropriação direta e base de custo (apropriacao.py): a busca por qualquer identificador, a situação do item (aprovado ou
a aprovar), a apropriação pelo HTTP (permissão, data, evidência, quem executou, estorno), a gaveta 5 da medição de teste,
a lista "medível com restrição" (item a aprovar, acima do BM, teto, material, cadastro no GDOC), a liberação quando o
código oficial é registrado e a migração v18 → v19. Sobre a base real das planilhas (tests/base_real.py)."""
import base64
import os
import sqlite3
import sys
import unittest
from datetime import timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import apropriacao as AP  # noqa: E402
import fotos_teste as FT  # noqa: E402
import lev as LV  # noqa: E402
import medicao as M  # noqa: E402
import regras as R  # noqa: E402
import relogio as RL  # noqa: E402
import servicos as S  # noqa: E402
from base_real import BaseReal, b64  # noqa: E402
from test_importacao import Base  # noqa: E402
from test_notas_servico import _ddl  # noqa: E402

ONTEM = RL.hoje() - timedelta(days=1)
DIA = ONTEM.isoformat()
INI_MES, FIM_MES = ONTEM.replace(day=1).isoformat(), (ONTEM.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
FIM_MES = FIM_MES.isoformat()
CONTEINER, ISOLAMENTO, FOSSA, LUVA_XX, CADASTRO = "1.2_5.1.1", "2.2_5.3.2", "1.1_1.18.5", "5.1_1.14.1", "2.2_5.2.1"
PDF = b"%PDF-1.4 oficio da Caesb com o codigo oficial"


def evidencia(nome="foto.png", png=None):
    return [{"nome": nome, "conteudo_b64": png or FT.png()}]          # fotos_teste.png() já vem em base64


class BaseAp(BaseReal):
    def setUp(self):
        super().setUp()
        self.docs = os.path.join(self.dados, "documentos")

    def ref(self, item):
        return AP.item(self.c, item)["ref"]

    def corpo(self, item, quantidade, **kw):
        d = dict(item_ref=self.ref(item), data=DIA, quantidade=quantidade, local_tipo="CANTEIRO", executor_tipo="OUTRA_OBRA",
                 executor_obra="CT 9702/2024 ETE Paranoá", executor_nome="equipe do encarregado João",
                 o_que_foi_feito="montagem do canteiro", memoria_calculo="conforme croqui", justificativa="período entre obras",
                 evidencias=evidencia())
        d.update(kw)
        return d

    def apropriar(self, item, quantidade, **kw):
        with S.transacao(self.c):
            return AP.apropriar(self.c, self.corpo(item, quantidade, **kw), "eng1", self.docs)

    def medicao(self, numero=1, ini=INI_MES, fim=FIM_MES):
        with S.transacao(self.c):
            return S.criar_medicao(self.c, numero, ini, fim)

    def gaveta5(self, mid):
        return [(l["item"], l["quantidade"], l["status"]) for l in S.resumo_medicao(self.c, mid)["gavetas"][5]["lancamentos"]]

    def linhas(self, restricao=None):
        return [x for x in AP.restricoes(self.c)["linhas"] if restricao is None or restricao in x["tags"]]

    def codigo(self, item, codigo):
        with S.transacao(self.c):
            return AP.registrar_codigo_oficial(self.c, {"item_ref": self.ref(item), "codigo": codigo, "data": DIA,
                                                        "documento_b64": b64(PDF), "documento_nome": "oficio.pdf"}, "eng1", self.docs)


class TestBusca(BaseAp):
    def primeiro(self, q, **kw):
        r = AP.buscar(self.c, q, **kw)
        return r[0]["item"] if r else None

    def test_qualquer_identificador_acha_o_item_certo(self):
        self.assertEqual(self.primeiro("tê 63 pe100"), "5.1_1.14.53")            # TÊ 90º eletrofusão DE 63 PE100
        self.assertEqual(self.primeiro("1.14.27"), "5.1_1.14.27")
        self.assertEqual(self.primeiro("5.1_1.14.27"), "5.1_1.14.27")
        self.assertEqual(self.primeiro("0173003001001"), "1.1_1.1.1")
        self.assertEqual(self.primeiro("fossa"), FOSSA)
        self.assertTrue(AP.buscar(self.c, "1.14.27")[0]["exato"])
        self.assertIn("1.1_1.1.1", [x["item"] for x in AP.buscar(self.c, "0173003")])          # pedaço do código

    def test_acento_ordem_e_sinonimos(self):
        for q in ("PE100 63 TE", "Tê eletrofusão 63", "te eletrofusao de 63 pe100"):
            self.assertEqual(self.primeiro(q), "5.1_1.14.53", q)
        for q in ("luva 63 polietileno de alta densidade", "pead luva 63mm", "Ø63 luva", "luva DE63", "LUVA 63 MM"):
            self.assertEqual(self.primeiro(q), "5.1_1.14.27", q)
        fofo = {x["item"] for x in AP.buscar(self.c, "fofo", limite=200)}
        self.assertTrue(fofo and fofo == {x["item"] for x in AP.buscar(self.c, "ferro fundido", limite=200)})
        self.assertEqual(self.primeiro("fóssa SÉPTICA"), FOSSA)
        self.assertEqual(AP.buscar(self.c, "palavra-que-nao-existe-xyz"), [])

    def test_grupo_e_tipo_filtram_e_o_item_novo_aparece(self):
        r = AP.buscar(self.c, "luva", grupo="Hidromecânico", tipo="Material")
        self.assertTrue(r and all((x["grupo"], x["tipo"]) == ("HIDROMECÂNICO", "MATERIAL") for x in r))
        with S.transacao(self.c):
            n = AP.propor_item(self.c, {"grupo": "Canteiro", "classificacao": "Serviço", "descricao": "Dedetização do canteiro",
                                        "unidade": "mes", "preco_proposto": 480, "fonte_preco": "COTACAO", "justificativa": "não há no BM",
                                        "atributos": {"descricao_resumida": "DEDETIZAÇÃO"}}, "eng1")
        self.assertTrue(n["gravado"], n)
        with S.transacao(self.c):                                           # o banheiro químico já existe no BM (1.1_7.1.1)
            par = AP.propor_item(self.c, {"grupo": "Canteiro", "classificacao": "Serviço", "descricao": "Banheiro químico, locação",
                                          "unidade": "MES", "preco_proposto": 480, "fonte_preco": "COTACAO", "justificativa": "x"}, "eng1")
        self.assertEqual([p["item"] for p in par["parecidos"]], ["1.1_7.1.1"])
        r = AP.buscar(self.c, "dedetizacao canteiro")
        self.assertEqual([(x["item"], x["situacao"], x["origem"], x["unidade"]) for x in r[:1]], [(n["item"]["item"], "A_APROVAR", "NOVO", "MES")])
        self.assertIn(n["item"]["item"], [x["item"] for x in AP.itens_do_subgrupo(self.c, "CANTEIRO", "SERVIÇO")])


class TestSituacao(BaseAp):
    def test_origem_do_codigo(self):
        casos = {"0173003001001": "BASE_CAESB", "8900103001SI39363": "SINAPI", "2202019100SCE9779": "SICRO",
                 "1514603060XX11": "PROVISORIO", "8008508024X238": "PROVISORIO", "": "PROVISORIO", None: "PROVISORIO"}
        for cod, origem in casos.items():
            self.assertEqual(R.origem_codigo(cod), origem, cod)
        self.assertEqual([R.composicao_referencia(c) for c in ("8000508010SI98459", "2202019100SCE9779", "0173003001001")],
                         ["SINAPI 98459", "SICRO E9779", None])
        tapume = AP.item(self.c, "1.2_5.1.2")                  # SI: código oficial da base Caesb, com a composição SINAPI
        self.assertEqual((tapume["situacao"], tapume["rotulo"], tapume["origem_rotulo"]),
                         ("APROVADO", "Aprovado · base Caesb (SINAPI 98459)", "base Caesb · composição SINAPI 98459"))

    def test_bm_aprovados_e_a_aprovar_e_o_codigo_oficial(self):
        cont = {}
        for it in AP.catalogo(self.c):
            cont[(it["situacao"], it["origem"])] = cont.get((it["situacao"], it["origem"]), 0) + 1
        self.assertEqual(cont, {("APROVADO", "BASE_CAESB"): 215, ("APROVADO", "SINAPI"): 185, ("APROVADO", "SICRO"): 16,
                                ("A_APROVAR", "PROVISORIO"): 16})
        self.assertEqual(AP.item(self.c, LUVA_XX)["rotulo"], "A aprovar · código provisório")
        r = self.codigo(LUVA_XX, "1514603060011")
        self.assertEqual((r["item"]["situacao"], r["item"]["rotulo"]), ("APROVADO", "Aprovado · código oficial 1514603060011"))
        self.assertEqual(self.c.execute("SELECT codigo_caesb FROM bm_itens WHERE item=? AND vigente=1", (LUVA_XX,)).fetchone()[0],
                         "1514603060XX11")                                         # a planilha do BM não muda
        with self.assertRaisesRegex(R.RegraViolada, "já tem o código oficial"):
            self.codigo(LUVA_XX, "1514603060099")
        with self.assertRaisesRegex(R.RegraViolada, "não tem código provisório"):
            self.codigo(FOSSA, "123")
        lev = {i["item"]: i for i in LV.bm(self.c, "VERTICAL")["itens"]}
        self.assertEqual((lev[LUVA_XX]["situacao"], lev[LUVA_XX]["codigo_oficial"]), ("APROVADO", "1514603060011"))
        self.assertEqual(lev["5.1_1.14.14"]["situacao"], "A_APROVAR")
        # revisão nova do BM já com o código: "conciliado com a REV xx"
        self.c.execute("UPDATE bm_itens SET codigo_caesb='1514603060011' WHERE item=? AND vigente=1", (LUVA_XX,))
        it = AP.item(self.c, LUVA_XX)
        self.assertEqual((it["origem"], it["conciliado"]), ("BASE_CAESB", "conciliado com a REV04"))

    def test_item_novo_aprovar_e_reprovar(self):
        with S.transacao(self.c):
            par = AP.propor_item(self.c, {"grupo": "HIDROMECÂNICO", "classificacao": "MATERIAL", "unidade": "UN",
                                          "descricao": "LUVA DE POLIETILENO DE ALTA DENSIDADE ELETROFUSÃO 63 MM PE100",
                                          "preco_proposto": 31.5, "fonte_preco": "NF", "fonte_ref": "NF 123", "justificativa": "x"}, "eng1")
        self.assertFalse(par["gravado"])                                         # avisa o parecido antes de gravar
        self.assertEqual(par["parecidos"][0]["item"], "5.1_1.14.27")
        with self.assertRaisesRegex(R.RegraViolada, "código SINAPI"):
            AP.propor_item(self.c, {"grupo": "CANTEIRO", "classificacao": "SERVIÇO", "descricao": "X", "unidade": "UN",
                                    "preco_proposto": 1, "fonte_preco": "SINAPI", "justificativa": "x"}, "eng1")
        novos = []
        for desc in ("PLACA DE OBRA EM LONA IMPRESSA 3X2", "ESCORAMENTO METÁLICO ESPECIAL"):
            with S.transacao(self.c):
                novos.append(AP.propor_item(self.c, {"grupo": "CANTEIRO", "classificacao": "SERVIÇO", "descricao": desc, "unidade": "UN",
                                                     "preco_proposto": 900, "fonte_preco": "COTACAO", "justificativa": "x",
                                                     "confirmar": True}, "eng1")["item"])
        with S.transacao(self.c):
            r = AP.decidir_item(self.c, {"item_ref": novos[0]["ref"], "acao": "APROVAR", "codigo": "8099900001001", "preco_aprovado": 850,
                                         "data": DIA, "documento_b64": b64(PDF)}, "adm", self.docs)
            AP.decidir_item(self.c, {"item_ref": novos[1]["ref"], "acao": "REPROVAR", "motivo": "usar o item do BM"}, "adm", self.docs)
        self.assertEqual((r["item"]["situacao"], r["item"]["preco"], r["item"]["preco_estimado"]), ("APROVADO", 850, False))
        rep = AP.item(self.c, novos[1]["ref"])
        self.assertEqual((rep["situacao"], rep["novo"]["motivo"]), ("REPROVADO", "usar o item do BM"))
        self.assertNotIn(rep["item"], [x["item"] for x in AP.buscar(self.c, "escoramento metalico especial")])
        with self.assertRaisesRegex(R.RegraViolada, "reprovado"):
            self.apropriar(rep["ref"], 1)
        with self.assertRaisesRegex(R.RegraViolada, "já foi aprovado"):
            AP.decidir_item(self.c, {"item_ref": novos[0]["ref"], "acao": "REPROVAR", "motivo": "x"}, "adm", self.docs)


class TestApropriacaoHttp(BaseAp):
    def test_so_engenharia_e_administracao(self):
        png = FT.png()
        corpo = self.corpo(CONTEINER, 2, evidencias=evidencia(png=png))
        for login in ("enc3", "almox1", "sup1"):
            self.recusa(self.cli(login).post("/api/apropriacao", corpo), 403, "permissão")
            self.recusa(self.cli(login).post("/api/base-custo/item-novo", {"descricao": "x"}), 403, "permissão")
        self.assertEqual(self.n("apropriacoes"), 0)
        for login in ("eng1", "adm"):
            r = self.ok(self.cli(login).post("/api/apropriacao", corpo))
            self.assertEqual(r["registrado_por"], login)                     # quem grava é o usuário da sessão
        self.recusa(self.cli("enc3").post("/api/base-custo/codigo-oficial", {"item_ref": self.ref(LUVA_XX)}), 403, "permissão")
        busca = self.ok(self.cli("enc3").get("/api/base-custo/busca?q=fossa"))          # a busca serve à tela campo
        self.assertEqual(busca["itens"][0]["item"], FOSSA)
        auditoria = self.c.execute("SELECT corpo FROM auditoria WHERE rota='/api/apropriacao' AND status=200").fetchone()[0]
        self.assertIn("[omitido]", auditoria)
        self.assertNotIn(png[:60], auditoria)                         # o base64 não vai para a auditoria

    def test_recusas(self):
        cli = self.cli("eng1")
        futuro = (RL.hoje() + timedelta(days=1)).isoformat()
        self.recusa(cli.post("/api/apropriacao", self.corpo(CONTEINER, 2, data=futuro)), 422, "data futura")
        self.recusa(cli.post("/api/apropriacao", self.corpo(CONTEINER, 2, evidencias=[])), 422, "pelo menos uma evidência")
        self.recusa(cli.post("/api/apropriacao", self.corpo(CONTEINER, 2, executor_obra="")), 422, "qual obra ou contrato")
        self.recusa(cli.post("/api/apropriacao", self.corpo(CONTEINER, 2, executor_nome="")), 422, "qual obra ou contrato")
        self.recusa(cli.post("/api/apropriacao", self.corpo(CONTEINER, 2, executor_tipo="TERCEIRO", executor_nome="")), 422, "nome")
        self.recusa(cli.post("/api/apropriacao", self.corpo(CONTEINER, 2, executor_tipo="EQUIPE_OBRA")), 422, "equipe")
        self.recusa(cli.post("/api/apropriacao", self.corpo(CONTEINER, 0)), 422, "maior que zero")
        self.recusa(cli.post("/api/apropriacao", self.corpo(CONTEINER, 2, justificativa=" ")), 422, "justificativa")
        self.recusa(cli.post("/api/apropriacao", self.corpo(CONTEINER, 2, evidencias=[{"nome": "x.gif", "conteudo_b64": b64(b"GIF89a")}])),
                    422, "")
        self.assertEqual(self.n("apropriacoes"), 0)

    def test_local_equipe_da_obra_estorno_e_evidencia(self):
        mid = self.medicao()
        cli = self.cli("eng1")
        png = FT.png()
        r = self.ok(cli.post("/api/apropriacao", self.corpo(CONTEINER, 3, executor_tipo="EQUIPE_OBRA", equipe_id="Zona03",
                                                           local_tipo="TRECHO", local_id="Zona03_PB08_Rede_TR020",
                                                           evidencias=evidencia(png=png))))
        self.assertEqual((r["executor"], r["local_tipo"], r["local_texto"], r["situacao"]), ("EQUIPE ZONA 03", "TRECHO",
                                                                                            "Zona03_PB08_Rede_TR020", "PROPOSTA"))
        st, h, dados = self.abrir("eng1", f"/api/apropriacao/arquivo?doc={r['documentos'][0]['id']}")
        self.assertEqual((st, h["Content-Type"], dados), (200, "image/png", base64.b64decode(png)))
        self.assertEqual(self.abrir("eng1", "/api/apropriacao/arquivo?doc=999")[0], 404)
        self.recusa(cli.post("/api/apropriacao/estornar", {"apropriacao_id": r["id"]}), 422, "motivo")
        e = self.ok(cli.post("/api/apropriacao/estornar", {"apropriacao_id": r["id"], "motivo": "quantidade errada"}))
        self.assertEqual((e["situacao"], e["estorno_motivo"], e["estornado_por"]), ("ESTORNADA", "quantidade errada", "eng1"))
        self.assertEqual(self.n("apropriacoes"), 1)                            # o original fica (riscado)
        self.assertEqual(self.gaveta5(mid), [(CONTEINER, 3.0, "PENDENTE")])     # a proposta voltou a pendente, nada apagado
        self.recusa(cli.post("/api/apropriacao/estornar", {"apropriacao_id": r["id"], "motivo": "x"}), 422, "já foi estornada")
        lista = self.ok(cli.get(f"/api/apropriacoes?ini={DIA}&fim={DIA}"))
        self.assertEqual([(a["id"], a["situacao"]) for a in lista], [(r["id"], "ESTORNADA")])
        diario = self.ok(cli.get(f"/api/diario?data={DIA}"))
        self.assertEqual([a["id"] for a in diario["apropriacoes"]], [r["id"]])
        self.assertEqual(self.ok(self.cli("enc1").get(f"/api/apropriacoes?ini={DIA}")), [])   # o encarregado vê só a equipe dele


class TestMedicao(BaseAp):
    def test_servico_aprovado_vira_proposta_na_gaveta_5_sem_duplicar(self):
        mid = self.medicao()
        a = self.apropriar(CONTEINER, 2)
        self.assertEqual((a["situacao"], a["proposto"]), ("PROPOSTA", 2.0))
        self.assertEqual(self.gaveta5(mid), [(CONTEINER, 2.0, "PROPOSTO")])
        with S.transacao(self.c):
            self.assertEqual(AP.sincronizar(self.c), 0)
        self.assertEqual(self.gaveta5(mid), [(CONTEINER, 2.0, "PROPOSTO")])     # sincronizar de novo não duplica
        r = S.resumo_medicao(self.c, mid)
        self.assertGreater(r["gavetas"][5]["valor"], 261.83)                   # 2 × 130,92 com BDI e K
        self.assertEqual(r["gavetas"][5]["nome"], "Apropriação direta")
        ret = M.retrato(self.c, mid)
        self.assertEqual(ret["impeditivos"], [])
        self.assertEqual([x["nome"] for x in ret["alvos"]], [f"Apropriação nº {a['id']}"])
        self.assertEqual(AP.saldo(self.c, AP.item(self.c, CONTEINER))["saldo"], 16.0)

    def test_item_a_aprovar_fica_parado_e_entra_com_o_codigo(self):
        mid = self.medicao()
        a = self.apropriar(ISOLAMENTO, 100)
        self.assertEqual((a["situacao"], self.gaveta5(mid)), ("PARADA", []))
        [l] = self.linhas("ITEM_A_APROVAR")
        self.assertEqual((l["item"], l["quantidade"], l["valor"], l["estimado"], l["acao"]),
                         (ISOLAMENTO, 100.0, 3091.0, False, "registrar o código oficial da Caesb"))
        self.assertEqual(l["dias"], 1)
        aprovar = {x["item"]: x for x in AP.itens_a_aprovar(self.c)}
        self.assertEqual(aprovar[ISOLAMENTO]["valor_parado"], 3091.0)
        self.assertEqual(len([x for x in aprovar.values() if x["origem"] == "PROVISORIO"]), 16)
        r = self.codigo(ISOLAMENTO, "8001508020010")
        self.assertEqual(r["liberados"], 1)
        self.assertEqual(self.gaveta5(mid), [(ISOLAMENTO, 100.0, "PROPOSTO")])
        self.assertEqual(self.linhas("ITEM_A_APROVAR"), [])

    def test_ok_interno_com_item_a_aprovar_e_liberado_na_proxima_medicao(self):
        """A regra vale para as gavetas 1 a 4: o lançamento num item XX fica PENDENTE (ITEM_A_APROVAR); fechada a medição,
        registrado o código, ele entra na próxima medição de teste aberta, uma vez só."""
        m1 = self.medicao()
        tr = S.alvo(self.c, "TRECHO", "Zona03_PB08_Rede_TR020")
        with S.transacao(self.c):
            S._lancar(self.c, m1, 1, "ISOLAMENTO DA OBRA", S._bm_item(self.c, ISOLAMENTO), "M2", 50, "TRECHO", tr["id"])
        l = self.c.execute("SELECT * FROM medicao_lancamentos").fetchone()
        self.assertEqual((l["status"], l["restricao"]), ("PENDENTE", "ITEM_A_APROVAR"))
        self.assertIn("código provisório 8001508020XX10", l["motivo"])
        self.assertEqual([x["origem"] for x in self.linhas("ITEM_A_APROVAR")], ["ISOLAMENTO DA OBRA · Zona03_PB08_Rede_TR020 · 1ª medição"])
        self.c.execute("UPDATE medicoes SET status='FECHADA' WHERE id=?", (m1,))
        prox = (ONTEM.replace(day=28) + timedelta(days=4)).replace(day=1)
        m2 = self.medicao(2, prox.isoformat(), (prox + timedelta(days=27)).isoformat())
        self.codigo(ISOLAMENTO, "8001508020010")
        novo = self.c.execute("SELECT * FROM medicao_lancamentos WHERE medicao_id=?", (m2,)).fetchall()
        self.assertEqual([(x["status"], x["quantidade"], x["origem_id"]) for x in novo], [("PROPOSTO", 50.0, l["id"])])
        self.assertEqual(M.duplicidades(self.c), [])                              # o PENDENTE liberado não conta como duplicidade
        with S.transacao(self.c):
            self.assertEqual(AP.sincronizar(self.c), 0)
        self.assertEqual(self.n("medicao_lancamentos"), 2)

    def test_acima_do_bm_material_e_sem_medicao_aberta(self):
        a = self.apropriar(CONTEINER, 20)                                        # contratado: 18 UN
        self.assertEqual(a["situacao"], "PARADA")                                # sem medição aberta ainda
        self.assertEqual([(x["restricao"], x["quantidade"]) for x in self.linhas()], [("ACIMA_DO_BM", 2.0), ("SEM_MEDICAO_ABERTA", 18.0)])
        mid = self.ok(self.cli("eng1").post("/api/medicao", {"numero": 1, "periodo_ini": INI_MES, "periodo_fim": FIM_MES}))
        self.assertEqual(mid["liberados"], 1)                                    # abrir a medição propõe o que estava livre
        self.assertEqual(self.gaveta5(mid["id"]), [(CONTEINER, 18.0, "PROPOSTO")])
        [l] = self.linhas()
        self.assertEqual((l["restricao"], l["quantidade"], l["valor"], l["acao"]), ("ACIMA_DO_BM", 2.0, 261.84, "aditivo ou apostilamento"))
        self.apropriar(FOSSA, 1)
        [m] = self.linhas("MATERIAL_SEM_REGIME")
        self.assertEqual((m["item"], m["valor"], m["letra"]), (FOSSA, 6307.51, "d"))
        self.assertEqual(len(self.gaveta5(mid["id"])), 1)                       # material não entra

    def test_item_novo_parado_estimado_e_aprovado_entra(self):
        mid = self.medicao()
        with S.transacao(self.c):
            n = AP.propor_item(self.c, {"grupo": "CANTEIRO", "classificacao": "SERVIÇO", "descricao": "PLACA DE OBRA EM LONA 3X2",
                                        "unidade": "UN", "preco_proposto": 900, "fonte_preco": "COTACAO", "justificativa": "x",
                                        "confirmar": True}, "eng1")["item"]
        self.apropriar(n["ref"], 2)
        [l] = self.linhas()
        self.assertEqual((l["restricao"], l["valor"], l["estimado"]), ("ITEM_A_APROVAR", 1800.0, True))
        with S.transacao(self.c):
            r = AP.decidir_item(self.c, {"item_ref": n["ref"], "acao": "APROVAR", "codigo": "8099900001001", "preco_aprovado": 850,
                                         "data": DIA, "documento_b64": b64(PDF)}, "adm", self.docs)
        self.assertEqual(r["liberados"], 1)
        self.assertEqual(self.gaveta5(mid), [(n["item"], 2.0, "PROPOSTO")])
        res = S.resumo_medicao(self.c, mid)
        [lanc] = res["gavetas"][5]["lancamentos"]
        self.assertEqual((lanc["preco_unitario"], lanc["classificacao"]), (850, "SERVIÇO"))
        self.assertEqual(res["totalizacao"]["servico"], 1700.0)

    def test_cadastro_esperando_o_gdoc_e_teto(self):
        tr = S.alvo(self.c, "TRECHO", "Zona03_PB08_Rede_TR020")
        for etapa in ("4_GDOC_ANALISE",):
            self.c.execute("INSERT INTO cadastro(trecho_id, etapa, protocolo_gdoc, atualizado_em) VALUES (?,?,?,?)",
                           (tr["id"], etapa, "GDOC 123", ONTEM.isoformat() + "T10:00:00"))
        [l] = self.linhas("CADASTRO_GDOC")
        self.assertEqual((l["letra"], l["quantidade"], l["valor"], l["acao"]),
                         ("e", float(tr["extensao_m"]), round(float(tr["extensao_m"]) * 2.61, 2), "cobrar a liberação (memorando ESET)"))
        self.c.execute("UPDATE cadastro SET etapa='3_RECEBIDO' WHERE trecho_id=?", (tr["id"],))
        self.assertEqual([x["restricao"] for x in self.linhas()], ["CADASTRO_PROTOCOLAR"])
        mid = self.medicao()
        antigo = S.resumo_medicao
        S.resumo_medicao = lambda conn, m: {**antigo(conn, m), "tetos": [{"subgrupo": "2.2", "nome": "REDES - SERVIÇO", "teto": 10.0,
                                                                         "excedente": 123.45}]}
        try:
            [t] = self.linhas("TETO_SUBGRUPO")
        finally:
            S.resumo_medicao = antigo
        self.assertEqual((t["valor"], t["grupo"], t["letra"]), (123.45, "REDES", "c"))
        rs = AP.restricoes(self.c, mid)
        self.assertEqual(rs["total"], sum(x["valor"] for x in rs["linhas"]))
        self.assertEqual(set(rs["totais"]), {"CADASTRO_PROTOCOLAR"})


class TestMigracaoV19(Base):
    def test_v18_para_v19_lancamentos_recriados_sem_perder_linhas(self):
        self.aplicar()
        c = sqlite3.connect(self.db, isolation_level=None)
        try:
            c.execute("PRAGMA foreign_keys = OFF")
            c.execute("PRAGMA legacy_alter_table = ON")
            c.execute("BEGIN")
            for t in ("apropriacao_documentos", "apropriacoes", "codigos_oficiais", "itens_novos_base"):
                c.execute(f"DROP TABLE {t}")
            c.execute("DROP TABLE medicao_lancamentos")
            c.execute(_ddl("medicao_lancamentos", [
                ("BETWEEN 1 AND 5", "BETWEEN 1 AND 4"),
                ("  item_novo_id INTEGER REFERENCES itens_novos_base(id),     -- v19: item fora do BM, aprovado pela Caesb\n", ""),
                ("  chave TEXT,", "  chave TEXT"),
                ("  restricao TEXT,                      -- v19: o que segura o PENDENTE (ITEM_A_APROVAR, MATERIAL_SEM_REGIME); vira proposta quando cai\n", ""),
                ("  origem_id INTEGER REFERENCES medicao_lancamentos(id),     -- v19: o PENDENTE de medição fechada que este lançamento liberou\n", ""),
                ("  lancado_em TEXT                      -- v19: quando foi lançado (dias parados na lista \"medível com restrição\")\n", "")]))
            c.execute("INSERT INTO medicoes(id,numero,tipo,periodo_ini,periodo_fim) VALUES (1,1,'TESTE','2026-10-01','2026-10-31')")
            for i in range(1, 4):
                c.execute("INSERT INTO medicao_lancamentos(id,medicao_id,gaveta,servico,unidade,quantidade,status,chave) "
                          f"VALUES ({i},1,{i},'SERVIÇO {i}','M',{i}.5,'PENDENTE','TESTE|{i}|SERVIÇO {i}')")
            c.execute("DELETE FROM schema_versao WHERE versao > 18")
            c.execute("INSERT OR IGNORE INTO schema_versao VALUES (18, '2026-10-21T00:00:00', 'rebaixado no teste')")
            c.execute("COMMIT")
        finally:
            c.close()
        rel = self.aplicar()
        self.assertEqual((rel["esquema_antes"], rel["esquema_depois"]), (18, S.VERSAO_ESQUEMA))
        self.assertEqual(self.q("SELECT id, gaveta, quantidade, chave FROM medicao_lancamentos ORDER BY id"),
                         [(i, i, i + .5, f"TESTE|{i}|SERVIÇO {i}") for i in range(1, 4)])
        sql = self.q("SELECT sql FROM sqlite_master WHERE name='medicao_lancamentos'")[0][0]
        self.assertIn("BETWEEN 1 AND 5", sql)
        cols = [r[1] for r in self.q("PRAGMA table_info(medicao_lancamentos)")]
        for col in ("item_novo_id", "restricao", "origem_id", "lancado_em"):
            self.assertIn(col, cols)
        for t in ("apropriacoes", "apropriacao_documentos", "itens_novos_base", "codigos_oficiais"):
            self.assertEqual(self.q(f"SELECT COUNT(*) FROM {t}"), [(0,)])
        self.assertEqual(self.q("SELECT name FROM sqlite_master WHERE name LIKE 'medicao_lancamentos__%'"), [])
        conn = self.conectar()
        self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        conn.execute("INSERT INTO medicao_lancamentos(medicao_id,gaveta,servico,unidade,quantidade) VALUES (1,5,'APROPRIAÇÃO DIRETA','UN',1)")
        self.assertIsNotNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='ux_lanc_chave'").fetchone())


if __name__ == "__main__":
    unittest.main()
