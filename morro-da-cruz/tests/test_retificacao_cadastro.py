"""Etapa 4 (continuação) — retificação de intervalos, conciliação do legado retificável, fases do cadastro com
conferência interna e visão integrada (detalhe e mapa). Planilhas SINTÉTICAS (perfil TESTE), bancos temporários.

Nada aqui aprova pela Caesb nem habilita medição oficial: o OK interno e a esteira continuam como antes.
"""
import json
import os
import sys
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import regras as R  # noqa: E402
import servicos as S  # noqa: E402
from fotos_teste import jpeg  # noqa: E402
from test_campo import TR, TR_ID, BaseCampo, D, banco_legado  # noqa: E402
from test_importacao import Base  # noqa: E402

D2 = "2026-10-16"
TUDO_OK = {k: True for k in R.CHECKLIST_CONFERENCIA_CADASTRO}


class BaseRetif(BaseCampo):
    def ret(self, ref_id, *intervalos, ref_tipo="APONTAMENTO", motivo="trena conferida em campo", resp="Eng. Responsável", **kw):
        return S.retificar_intervalos(self.c, ref_tipo, ref_id, [
            dict(etapa=e, ini_m=a, fim_m=b, **x) for e, a, b, *r in intervalos for x in (r[0] if r else {},)],
            motivo, resp, **kw)

    def efetivos(self):
        return self.q("SELECT etapa, ini_m, fim_m FROM intervalos_execucao WHERE anulado_por IS NULL ORDER BY etapa, ini_m")

    def soma_servico(self, servico="ASSENTAMENTO"):
        return self.q("""SELECT COALESCE(SUM(q.confirmado),0) FROM apontamento_quantidades q JOIN apontamentos ap
                         ON ap.id=q.apontamento_id WHERE ap.anulado_por IS NULL AND q.servico=?""", servico)[0][0]

    def fotos_e_medicao(self):
        for cat in ("SINALIZACAO", "EXECUCAO", "CONCLUIDO"):
            S.registrar_foto(self.c, "TRECHO", TR, cat, jpeg(), dir_fotos=self.fotos)
        S.criar_medicao(self.c, 1, "2026-10-01", "2026-10-31")


class TestRetificacao(BaseRetif):
    def test_corrige_extensao_sem_dupla_contagem_e_preserva_historico(self):
        ap = self.ap(("ASSENTADO", 0, 12), informado_por="Encarregado A")
        self.assertEqual(self.soma_servico(), 12)
        plano = self.ret(ap, ("ASSENTADO", 0, 10), motivo="trena: eram 10 m, não 12")
        self.assertEqual(self.ex(), (10, 0, 0))
        self.assertEqual(self.efetivos(), [("ASSENTADO", 0.0, 10.0)])
        rid = plano["id"]
        # nada apagado: original anulado, ligado à retificação; apontamento original fora das somas
        self.assertEqual(self.q("SELECT ini_m, fim_m, origem, anulado_por FROM intervalos_execucao ORDER BY id"),
                         [(0.0, 12.0, "INFORMADO", rid), (0.0, 10.0, "RETIFICACAO", None)])
        self.assertEqual(self.q("SELECT id, anulado_por, retificacao_id, informado_por FROM apontamentos ORDER BY id"),
                         [(ap, rid, None, "Encarregado A"), (ap + 1, None, rid, "Eng. Responsável")])
        self.assertEqual(self.soma_servico(), 10)                                     # não 22, não 12
        self.assertEqual(self.q("SELECT COUNT(*) FROM apontamento_quantidades WHERE apontamento_id=?", ap)[0][0] > 0, True)
        r = self.q("SELECT ref_tipo, ref_id, novo_apontamento_id, motivo, responsavel, detalhe FROM retificacoes_intervalos")[0]
        self.assertEqual(r[:5], ("APONTAMENTO", ap, ap + 1, "trena: eram 10 m, não 12", "Eng. Responsável"))
        det = json.loads(r[5])
        self.assertEqual((det["resumo_antes"]["ASSENTADO"], det["resumo_depois"]["ASSENTADO"]), (12, 10))
        # continuidade: o trecho segue até o OK, e a proposta usa só os registros efetivos
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, concluido_100=True)
        self.fotos_e_medicao()
        S.verificar_trecho(self.c, TR, "sup")                            # o OK interno exige a verificação (v20)
        S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng", D)
        ass = self.q("SELECT SUM(quantidade) FROM medicao_lancamentos WHERE servico='ASSENTAMENTO'")[0][0]
        self.assertAlmostEqual(ass, 76.55)                                            # sem os 2 m do erro
        with self.assertRaisesRegex(S.RegraViolada, "OK interno"):
            self.ret(ap + 1, ("ASSENTADO", 0, 9))                                     # depois do OK: recusada

    def test_corrigir_assentamento_nao_deixa_reaterro_ou_cadastro_sem_suporte(self):
        ap1 = self.ap(("ASSENTADO", 0, 30))
        ap2 = self.ap(("CADASTRO_CAMPO", 0, 30), ("REATERRADO", 0, 30))
        antes = {t: self.q(f"SELECT * FROM {t}") for t in ("intervalos_execucao", "apontamentos", "apontamento_quantidades",
                                                           "execucao", "retificacoes_intervalos")}
        with self.assertRaisesRegex(S.RegraViolada, rf"deixaria CADASTRO_CAMPO 0–30 m de {D} \(apontamento #{ap2}\) sem "
                                                    r"assentamento registrado até essa data: 25–30 m\. Retifique antes"):
            self.ret(ap1, ("ASSENTADO", 0, 25))
        for t, linhas in antes.items():                                               # recusa integral: nada gravado
            self.assertEqual(self.q(f"SELECT * FROM {t}"), linhas, t)
        self.ret(ap2, ("CADASTRO_CAMPO", 0, 25), ("REATERRADO", 0, 25))               # primeiro o que depende
        self.ret(ap1, ("ASSENTADO", 0, 25))                                           # depois o assentamento
        self.assertEqual(self.ex(), (25, 25, 0))
        self.assertEqual(self.efetivos(), [("ASSENTADO", 0.0, 25.0), ("CADASTRO_CAMPO", 0.0, 25.0), ("REATERRADO", 0.0, 25.0)])

    def test_falha_no_meio_da_gravacao_desfaz_tudo(self):
        ap = self.ap(("ASSENTADO", 0, 12))
        antes = {t: self.q(f"SELECT * FROM {t}") for t in ("intervalos_execucao", "apontamentos", "apontamento_quantidades",
                                                           "execucao", "retificacoes_intervalos")}
        with mock.patch.object(S, "_atualizar_execucao_trecho", side_effect=RuntimeError("queda simulada")):
            with self.assertRaises(RuntimeError):
                self.ret(ap, ("ASSENTADO", 0, 10))
        for t, linhas in antes.items():
            self.assertEqual(self.q(f"SELECT * FROM {t}"), linhas, t)

    def test_data_corrigida_respeita_a_cronologia(self):
        ap1 = self.ap(("ASSENTADO", 0, 20))
        self.ap(("REATERRADO", 0, 20))
        with self.assertRaisesRegex(S.RegraViolada, "clima"):
            self.ret(ap1, ("ASSENTADO", 0, 20), data=D2)
        for t in ("MANHA", "TARDE"):
            S.registrar_clima(self.c, D2, "Zona01", t, "SOL")
        with self.assertRaisesRegex(S.RegraViolada, f"deixaria REATERRADO 0–20 m de {D}"):
            self.ret(ap1, ("ASSENTADO", 0, 20), data=D2)                              # reaterro de 15/10 sem suporte
        ap3 = self.ap(("ASSENTADO", 20, 30))
        self.ret(ap3, ("ASSENTADO", 20, 30), data=D2, motivo="data errada no apontamento")
        self.assertEqual(self.q("SELECT data FROM intervalos_execucao WHERE anulado_por IS NULL AND ini_m=20"), [(D2,)])
        self.assertEqual(self.q("SELECT data FROM apontamentos WHERE anulado_por IS NULL ORDER BY id"), [(D,), (D,), (D2,)])

    def test_quantidade_editada_a_mao_exige_quantidade_corrigida(self):
        ap = self.ap(("ASSENTADO", 0, 12), quantidades=[{"servico": "ASSENTAMENTO", "unidade": "M", "confirmado": 11}])
        ap2 = self.ret(ap, ("ASSENTADO", 2, 14))["id"]                                # só posição: mantém 11
        self.assertEqual(self.soma_servico(), 11)
        novo = self.q("SELECT novo_apontamento_id FROM retificacoes_intervalos WHERE id=?", ap2)[0][0]
        with self.assertRaisesRegex(S.RegraViolada, r"confirmada à mão \(ASSENTAMENTO\)"):
            self.ret(novo, ("ASSENTADO", 2, 12))
        self.ret(novo, ("ASSENTADO", 2, 12), quantidades=[{"servico": "ASSENTAMENTO", "unidade": "M", "confirmado": 9.5}])
        self.assertEqual(self.soma_servico(), 9.5)
        self.assertEqual(self.ex(), (10, 0, 0))

    def test_posicao_presumida_confirmada_e_verificacao_so_no_intervalo_identico(self):
        ap = self.ap(("ASSENTADO", 0, 10), ("CADASTRO_CAMPO", 0, 10), informado_por="Enc")
        self.c.execute("UPDATE intervalos_execucao SET origem='SEQUENCIAL' WHERE etapa='ASSENTADO'")   # resíduo da v6
        for (iid,) in self.q("SELECT id FROM intervalos_execucao"):
            S.verificar_intervalo(self.c, iid, "Fiscal")
        self.assertTrue(any("posição presumida" in a for a in S.situacao_intervalos(self.c, TR)["alertas"]))
        self.ret(ap, ("ASSENTADO", 0, 12), ("CADASTRO_CAMPO", 0, 10, {"referencia": "Caderneta 3"}))
        sit = S.situacao_intervalos(self.c, TR)
        self.assertFalse(any("posição presumida" in a for a in sit["alertas"]))
        self.assertEqual(self.q("SELECT etapa, verificado_por, referencia FROM intervalos_execucao WHERE anulado_por IS NULL ORDER BY etapa"),
                         [("ASSENTADO", None, None), ("CADASTRO_CAMPO", "Fiscal", "Caderneta 3")])
        anulado = self.q("SELECT id FROM intervalos_execucao WHERE anulado_por IS NOT NULL LIMIT 1")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "anulado pela retificação"):
            S.verificar_intervalo(self.c, anulado, "Fiscal 2")
        self.assertEqual(len(sit["anulados"]), 2)
        self.assertEqual(sit["retificacoes"][0]["motivo"], "trena conferida em campo")

    def test_recusas_e_previa_sem_gravar(self):
        ap = self.ap(("ASSENTADO", 0, 12))
        with self.assertRaisesRegex(S.RegraViolada, "motivo"):
            self.ret(ap, ("ASSENTADO", 0, 10), motivo=" ")
        with self.assertRaisesRegex(S.RegraViolada, "não altera nada"):
            self.ret(ap, ("ASSENTADO", 0, 12))
        with self.assertRaisesRegex(S.RegraViolada, "controle de soldas"):
            self.ret(ap, ("ASSENTADO", 0, 10), quantidades=[{"servico": "SOLDA", "unidade": "UN", "confirmado": 2}])
        with self.assertRaisesRegex(S.RegraViolada, "fora do trecho"):
            self.ret(ap, ("ASSENTADO", 70, 80))
        antes = self.q("SELECT COUNT(*) FROM intervalos_execucao")[0][0]
        prev = S.retificar_intervalos(self.c, "APONTAMENTO", ap, [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 10}], "", "", simular=True)
        self.assertEqual((prev["resumo_antes"]["ASSENTADO"], prev["resumo_depois"]["ASSENTADO"]), (12, 10))
        self.assertEqual([q["confirmado"] for q in prev["quantidades_depois"] if q["servico"] == "ASSENTAMENTO"], [10])
        self.assertEqual(self.q("SELECT COUNT(*) FROM intervalos_execucao")[0][0], antes)    # prévia não grava
        self.assertEqual(self.q("SELECT COUNT(*) FROM retificacoes_intervalos")[0][0], 0)
        r = self.ret(ap, ("ASSENTADO", 0, 10))
        with self.assertRaisesRegex(S.RegraViolada, rf"já foi retificado .*apontamento #{ap + 1}"):
            self.ret(ap, ("ASSENTADO", 0, 9))
        self.assertEqual(r["anulados"][0]["fim_m"], 12)

    def test_anulacao_de_apontamento_lancado_no_trecho_errado(self):
        ap = self.ap(("ASSENTADO", 0, 10))
        self.ret(ap, motivo="lançado no trecho errado (era o TR002)")
        self.assertEqual(self.ex(), (0, 0, 0))
        self.assertEqual(self.soma_servico(), 0)
        self.assertEqual(self.q("SELECT novo_apontamento_id FROM retificacoes_intervalos"), [(None,)])
        self.assertIsNone(S.situacao_intervalos(self.c, TR)["legado"])                 # anulado não vira legado


class TestRetificacaoDoLegado(Base):
    LIBERAR_TUDO = True

    def setUp(self):
        super().setUp()
        banco_legado(self).close()
        self.aplicar()
        self.c = self.conectar()
        for t in ("MANHA", "TARDE"):
            S.registrar_clima(self.c, D2, "Zona01", t, "SOL")

    def test_conciliacao_retificada_mantem_os_mesmos_metros_sem_quantidades(self):
        cid = S.conciliar_legado(self.c, TR, [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 30},
                                              {"etapa": "REATERRADO", "ini_m": 0, "fim_m": 20}], "trena", "Eng.")
        with self.assertRaisesRegex(S.RegraViolada, f"conciliação #{cid} tem 30 m"):
            S.retificar_intervalos(self.c, "CONCILIACAO", cid, [{"etapa": "ASSENTADO", "ini_m": 5, "fim_m": 36},
                                                                {"etapa": "REATERRADO", "ini_m": 5, "fim_m": 25}], "m", "r")
        with self.assertRaisesRegex(S.RegraViolada, "retifique a conciliação"):
            S.retificar_intervalos(self.c, "APONTAMENTO", 1, [{"etapa": "ASSENTADO", "ini_m": 5, "fim_m": 35}], "m", "r")
        q_antes = self.q("SELECT * FROM apontamento_quantidades")
        S.retificar_intervalos(self.c, "CONCILIACAO", cid, [{"etapa": "ASSENTADO", "ini_m": 5, "fim_m": 35},
                                                            {"etapa": "REATERRADO", "ini_m": 5, "fim_m": 25}],
                               "posição revista com o cadastro de campo", "Eng.")
        self.assertEqual(self.q("SELECT etapa, ini_m, fim_m, origem, conciliacao_id, data FROM intervalos_execucao "
                                "WHERE anulado_por IS NULL ORDER BY etapa"),
                         [("ASSENTADO", 5.0, 35.0, "RETIFICACAO", cid, "2026-10-14"),
                          ("REATERRADO", 5.0, 25.0, "RETIFICACAO", cid, "2026-10-14")])
        self.assertEqual(self.q("SELECT * FROM apontamento_quantidades"), q_antes)            # nenhuma quantidade nova
        self.assertEqual(self.q("SELECT COUNT(*) FROM apontamentos")[0][0], 1)
        e = S.execucao(self.c, "TRECHO", TR_ID)
        self.assertEqual((e["metros_executados"], e["metros_reaterrados"]), (30, 20))
        S.apontar(self.c, D2, "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 5}])
        e = S.execucao(self.c, "TRECHO", TR_ID)
        self.assertEqual((e["metros_executados"], e["metros_reaterrados"]), (35, 20))

    def test_legado_pendente_bloqueia_retificacao(self):
        with self.assertRaisesRegex(S.RegraViolada, "não tem intervalos .* use a conciliação do legado"):
            S.retificar_intervalos(self.c, "APONTAMENTO", 1, [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 30}], "m", "r")
        # estado danificado pela f035f5c (intervalo gravado por cima do legado): concilie antes de retificar
        self.c.execute("INSERT INTO apontamentos(data,equipe_id,alvo_tipo,alvo_id,metros_executados) VALUES (?,?,?,?,10)",
                       (D2, "Zona01", "TRECHO", TR_ID))
        self.c.execute("INSERT INTO intervalos_execucao(trecho_id,etapa,ini_m,fim_m,data,apontamento_id,origem,registrado_em) "
                       "VALUES (?,'ASSENTADO',30,40,?,2,'INFORMADO','x')", (TR_ID, D2))
        with self.assertRaisesRegex(S.RegraViolada, "Concilie a posição desses metros .* antes de retificar"):
            S.retificar_intervalos(self.c, "APONTAMENTO", 2, [{"etapa": "ASSENTADO", "ini_m": 30, "fim_m": 38}], "m", "r")


class TestFasesDoCadastro(BaseRetif):
    def fase(self, nome):
        return next(f for f in S.detalhe(self.c, "TRECHO", TR)["fases_cadastro"] if f["fase"] == nome)

    def test_levantamento_de_campo_evidencias_e_pendencias(self):
        self.ap(("ASSENTADO", 0, 30), ("CADASTRO_CAMPO", 0, 20), informado_por="Topógrafo")
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, intervalos_novos=[
            {"etapa": "CADASTRO_CAMPO", "ini_m": 20, "fim_m": 25, "referencia": "Caderneta 12 p. 3"},
            {"etapa": "REATERRADO", "ini_m": 0, "fim_m": 28}], informado_por="Topógrafo")
        lev = self.fase("LEVANTAMENTO_CAMPO")
        self.assertEqual(lev["status"], "PARCIAL")
        self.assertIn("Assentado sem levantamento de campo: 25–30 m", lev["pendencias"])
        self.assertIn(f"Reaterrado antes do levantamento (alerta): 25–28 m (reaterro de {D})", lev["pendencias"])
        self.assertTrue(any("sem registro de referência" in p and "0–20 m" in p for p in lev["pendencias"]))
        self.assertTrue(any("registro: Caderneta 12 p. 3" in e for e in lev["evidencias"]))
        self.assertEqual(self.fase("PREPARACAO")["status"], "AGUARDA_OK_INTERNO")
        self.assertEqual(self.fase("CONFERENCIA_INTERNA")["status"], "AGUARDA_ARQUIVOS")
        self.assertEqual(self.fase("ENTREGA_GDOC")["status"], "NAO_PROTOCOLADO")

    def test_conferencia_interna_devolucao_e_protocolo(self):
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, intervalos_novos=[
            {"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 76.55},
            {"etapa": "CADASTRO_CAMPO", "ini_m": 0, "fim_m": 76.55, "referencia": "Arquivo pontos TR001.csv"}])
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, concluido_100=True)
        self.fotos_e_medicao()
        S.verificar_trecho(self.c, TR, "sup")                            # o OK interno exige a verificação (v20)
        S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng", D)
        n_lanc = self.q("SELECT COUNT(*) FROM medicao_lancamentos")[0][0]
        self.assertEqual(self.fase("LEVANTAMENTO_CAMPO")["status"], "COMPLETO")
        with self.assertRaisesRegex(S.RegraViolada, "etapa 3"):
            S.registrar_conferencia_cadastro(self.c, TR, "CONFORME", TUDO_OK, "Eng. Revisor")
        S.avancar_cadastro(self.c, TR, "2_ENVIADO", {"empresa": "Topo Ltda", "data_envio": D})
        S.avancar_cadastro(self.c, TR, "3_RECEBIDO", {"arquivos": ["TR001.dwg", "TR001.pdf"]})
        self.assertEqual(self.fase("CONFERENCIA_INTERNA")["status"], "SEM_CONFERENCIA")
        with self.assertRaisesRegex(S.RegraViolada, "exige conferência interna NÃO CONFORME"):
            S.avancar_cadastro(self.c, TR, "2_ENVIADO", {})
        with self.assertRaisesRegex(S.RegraViolada, "CONFORME exige todos os itens"):
            S.registrar_conferencia_cadastro(self.c, TR, "CONFORME", dict(TUDO_OK, PROFUNDIDADE=False), "Eng. Revisor")
        with self.assertRaisesRegex(S.RegraViolada, "Descreva a divergência"):
            S.registrar_conferencia_cadastro(self.c, TR, "NAO_CONFORME", dict(TUDO_OK, PROFUNDIDADE=False), "Eng. Revisor")
        S.registrar_conferencia_cadastro(self.c, TR, "NAO_CONFORME", dict(TUDO_OK, PROFUNDIDADE=False), "Eng. Revisor",
                                         "cota do PV de jusante difere do levantamento")
        with self.assertRaisesRegex(S.RegraViolada, "NÃO CONFORME .* devolva o cadastro à empresa"):
            S.avancar_cadastro(self.c, TR, "4_GDOC_ANALISE", {"protocolo_gdoc": "GDOC-1"})
        S.avancar_cadastro(self.c, TR, "2_ENVIADO", {})                                     # devolução: Rev. 1
        cad = self.q("SELECT etapa, revisao, arquivos FROM cadastro")[0]
        self.assertEqual(cad, ("2_ENVIADO", 1, None))
        hist = json.loads(self.q("SELECT dados FROM cadastro_historico ORDER BY id DESC LIMIT 1")[0][0])
        self.assertEqual(hist["motivo_devolucao"], "cota do PV de jusante difere do levantamento")
        S.avancar_cadastro(self.c, TR, "3_RECEBIDO", {"arquivos": ["TR001_R1.dwg"]})
        conf = self.fase("CONFERENCIA_INTERNA")
        self.assertEqual(conf["status"], "SEM_CONFERENCIA")                                 # nova revisão, nova conferência
        self.assertIn("conferência interna ankara — não é aprovação da caesb", conf["nome"].lower())
        S.registrar_conferencia_cadastro(self.c, TR, "CONFORME", TUDO_OK, "Eng. Revisor")
        S.avancar_cadastro(self.c, TR, "4_GDOC_ANALISE", {"protocolo_gdoc": "GDOC-77"})
        self.assertEqual(self.fase("CONFERENCIA_INTERNA")["status"], "CONFORME")
        gd = self.fase("ENTREGA_GDOC")
        self.assertEqual(gd["status"], "EM_ANALISE_CAESB")
        self.assertIn("Aguardando a análise da Caesb (protocolo GDOC-77).", gd["pendencias"])
        self.assertEqual(self.q("SELECT COUNT(*) FROM medicao_lancamentos")[0][0], n_lanc)  # conferência não lança nada
        est = {c["ponto"]: c for c in S.esteira(self.c)}[TR]
        self.assertEqual((est["conferencia"]["revisao"], est["conferencia"]["resultado"], est["levantamento_completo"]),
                         (1, "CONFORME", True))                                            # a da revisão protocolada
        self.assertEqual(S.ultima_conferencia(self.c, TR_ID, 0)["resultado"], "NAO_CONFORME")   # Rev. 0 no histórico


class TestVisaoIntegrada(BaseRetif):
    def test_pendencias_consolidadas_e_mapa_informado_x_verificado(self):
        ap = self.ap(("ASSENTADO", 0, 30), ("REATERRADO", 0, 20), informado_por="Enc")
        s1 = S.registrar_soldas(self.c, D, "Zona01", "TRECHO", TR, "ELETROFUSAO", 4, "Soldador", "Enc")
        S.registrar_soldas(self.c, D, "Zona01", "TRECHO", TR, "ELETROFUSAO", 1, "Soldador", "Enc")
        S.verificar_soldas(self.c, s1, "Fiscal", "REPROVADA", "fusão fria")
        d = S.detalhe(self.c, "TRECHO", TR)
        txt = [(p["nivel"], p["area"], p["texto"]) for p in d["pendencias"]]
        self.assertIn(("PENDENTE", "Execução", "ASSENTADO: falta 30–76.55 m."), txt)
        self.assertIn(("PENDENTE", "Verificação interna", "2 intervalo(s) informados sem verificação."), txt)
        self.assertIn(("PENDENTE", "Soldas", "1 solda(s) sem verificação."), txt)
        self.assertIn(("ALERTA", "Soldas", "4 solda(s) reprovada(s): refazer e registrar de novo."), txt)
        self.assertTrue(any(n == "PENDENTE" and a == "Fotos" for n, a, _ in txt))
        self.assertTrue(any(a.startswith("1. Levantamento de campo") for _, a, _ in txt))
        self.assertTrue(any(n == "ALERTA" and "Reaterrado antes do levantamento" in t for n, _, t in txt))
        mapa = lambda: S.estado_mapa(self.c)
        self.assertEqual(mapa()["verificacao"], {TR: "INFORMADO"})
        ids = [r[0] for r in self.q("SELECT id FROM intervalos_execucao ORDER BY etapa")]
        S.verificar_intervalo(self.c, ids[0], "Fiscal")
        self.assertEqual(mapa()["verificacao"], {TR: "PARCIAL"})
        S.verificar_intervalo(self.c, ids[1], "Fiscal")
        self.assertEqual(mapa()["verificacao"], {TR: "VERIFICADO"})
        self.assertEqual(S.detalhe(self.c, "TRECHO", TR)["intervalos"]["etapas"]["ASSENTADO"]["verificado_m"], 30)
        self.ret(ap, ("ASSENTADO", 0, 25), ("REATERRADO", 0, 20))                    # o mapa segue o efetivo
        self.assertEqual(mapa()["verificacao"], {TR: "PARCIAL"})
        self.assertEqual(mapa()["status"][TR], "EM_EXECUCAO")

    def test_mapa_mostra_legado_sem_posicao(self):
        self.ap(("ASSENTADO", 0, 10))
        self.c.execute("INSERT INTO apontamentos(data,equipe_id,alvo_tipo,alvo_id,metros_executados) VALUES (?,?,?,?,?)",
                       (D, "Zona01", "TRECHO", S.alvo(self.c, "TRECHO", TR)["id"], 7))
        m = S.estado_mapa(self.c)
        self.assertEqual(m["verificacao"][TR], "LEGADO_SEM_POSICAO")
        self.assertEqual([(x["nome"], x["assentado_m"]) for x in m["legado_sem_posicao"]], [(TR, 7)])
        self.assertEqual(S.detalhe(self.c, "TRECHO", TR)["pendencias"][0]["nivel"], "BLOQUEIO")


class TestMigracaoV7ParaV8(Base):
    LIBERAR_TUDO = True

    def test_v7_com_legado_conciliado_e_intervalos_continua_e_retifica(self):
        c = banco_legado(self, versao=7)
        c.execute("INSERT INTO conciliacoes_legado(trecho_id,metros_assentado,metros_reaterrado,motivo,responsavel,em) "
                  "VALUES (?,30,20,'trena','Eng.','x')", (TR_ID,))
        c.execute("INSERT INTO conciliacao_legado_apontamentos VALUES (1,1)")
        for e, a, b in (("ASSENTADO", 0, 30), ("REATERRADO", 0, 20)):
            c.execute("INSERT INTO intervalos_execucao(trecho_id,etapa,ini_m,fim_m,data,origem,conciliacao_id,registrado_em) "
                      "VALUES (?,?,?,?,'2026-10-14','LEGADO',1,'x')", (TR_ID, e, a, b))
        c.execute("INSERT INTO apontamentos(data,equipe_id,alvo_tipo,alvo_id,metros_executados) VALUES ('2026-10-15','Zona01','TRECHO',?,10)", (TR_ID,))
        c.execute("INSERT INTO apontamento_quantidades VALUES (2,'ASSENTAMENTO','M',10,10)")
        c.execute("INSERT INTO intervalos_execucao(trecho_id,etapa,ini_m,fim_m,data,apontamento_id,origem,informado_por,"
                  "verificado_em,verificado_por,registrado_em) VALUES (?,'ASSENTADO',30,40,'2026-10-15',2,'INFORMADO','Enc','y','Fiscal','x')", (TR_ID,))
        c.execute("UPDATE execucao SET metros_executados=40, metros_reaterrados=20")
        c.commit()
        antes = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
                 ("apontamentos", "apontamento_quantidades", "intervalos_execucao", "conciliacoes_legado", "execucao")}
        c.close()
        rel = self.aplicar()
        self.assertEqual((rel["esquema_antes"], rel["esquema_depois"]), (7, S.VERSAO_ESQUEMA))
        c2 = self.conectar()
        for t, n in antes.items():
            self.assertEqual(c2.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], n, t)
        self.assertEqual(self.q("SELECT COUNT(*) FROM intervalos_execucao WHERE anulado_por IS NULL")[0][0], 3)
        sit = S.situacao_intervalos(c2, TR)
        self.assertIsNone(sit["legado"])
        self.assertEqual((sit["etapas"]["ASSENTADO"]["metros"], sit["etapas"]["ASSENTADO"]["verificado_m"]), (40, 10))
        self.assertEqual([(g["ref_tipo"], g["ref_id"]) for g in sit["registros"]], [("CONCILIACAO", 1), ("APONTAMENTO", 2)])
        self.assertEqual(S.estado_mapa(c2)["verificacao"][TR], "PARCIAL")
        # continuidade: os dados migrados aceitam retificação e novos apontamentos
        for t in ("MANHA", "TARDE"):
            S.registrar_clima(c2, D2, "Zona01", t, "SOL")
        S.retificar_intervalos(c2, "APONTAMENTO", 2, [{"etapa": "ASSENTADO", "ini_m": 30, "fim_m": 38}], "trena", "Eng.")
        S.apontar(c2, D2, "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 38, "fim_m": 45}])
        e = S.execucao(c2, "TRECHO", TR_ID)
        self.assertEqual((e["metros_executados"], e["metros_reaterrados"]), (45, 20))
        self.assertEqual(self.q("""SELECT SUM(q.confirmado) FROM apontamento_quantidades q JOIN apontamentos ap ON ap.id=q.apontamento_id
                                   WHERE ap.anulado_por IS NULL AND q.servico='ASSENTAMENTO'""")[0][0], 45)


if __name__ == "__main__":
    unittest.main()
