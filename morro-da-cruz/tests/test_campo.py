"""Etapa 4 — campo: intervalos por etapa, cadastro de campo antes do reaterro, soldas informadas × verificadas e
foto original com hash. Planilhas SINTÉTICAS (perfil TESTE). Nada aqui gera lançamento de medição.

Critério do diagnóstico (§5, item 4): trecho com 30 m assentados e 20 m reaterrados; intervalo sobreposto é
rejeitado; a mesma medição repetida também.
"""
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
import backup  # noqa: E402
import servicos as S  # noqa: E402
from fotos_teste import jpeg  # noqa: E402
from test_importacao import Base  # noqa: E402

TR = "Zona01_PB01_Rede_TR001"            # 76,55 m, VCA, PEAD
MND = "Zona02_PB04_Rede_TR036"           # 17,95 m, MND
D = "2026-10-15"


class BaseCampo(Base):
    LIBERAR_TUDO = True

    def setUp(self):
        super().setUp()
        self.aplicar()
        self.c = self.conectar()
        for eq in ("Zona01", "Zona02"):
            for t in ("MANHA", "TARDE"):
                S.registrar_clima(self.c, D, eq, t, "SOL")

    def ap(self, *intervalos, alvo=TR, equipe="Zona01", **kw):
        return S.apontar(self.c, D, equipe, "TRECHO", alvo, intervalos_novos=[
            {"etapa": e, "ini_m": a, "fim_m": b} for e, a, b in intervalos] or None, **kw)

    def ex(self, alvo=TR):
        e = S.execucao(self.c, "TRECHO", S.alvo(self.c, "TRECHO", alvo)["id"])
        return (e["metros_executados"], e["metros_reaterrados"], e["concluido"])


class TestIntervalos(BaseCampo):
    def test_criterio_30_assentados_20_reaterrados_sem_sobreposicao(self):
        self.ap(("ASSENTADO", 0, 30), ("REATERRADO", 0, 20), informado_por="encarregado")
        self.assertEqual(self.ex(), (30, 20, 0))
        with self.assertRaisesRegex(S.RegraViolada, "sobrepõe"):
            self.ap(("ASSENTADO", 10, 40))                                     # sobreposto
        with self.assertRaisesRegex(S.RegraViolada, "sobrepõe"):
            self.ap(("ASSENTADO", 0, 30))                                      # a mesma medição repetida
        with self.assertRaisesRegex(S.RegraViolada, "sem assentamento registrado até essa data: 30–35"):
            self.ap(("REATERRADO", 25, 35))                                    # reaterro além do assentado
        with self.assertRaisesRegex(S.RegraViolada, "sobrepõe"):
            self.ap(("ASSENTADO", 30, 40), ("ASSENTADO", 35, 45))              # sobreposição entre os novos
        with self.assertRaisesRegex(S.RegraViolada, "fora do trecho"):
            self.ap(("ASSENTADO", 70, 80))
        self.assertEqual(self.ex(), (30, 20, 0))                               # recusas não gravaram nada
        self.assertEqual(self.q("SELECT COUNT(*) FROM intervalos_execucao")[0][0], 2)
        self.assertEqual(self.q("SELECT COUNT(*) FROM medicao_lancamentos")[0][0], 0)

    def test_quantidades_previstas_seguem_o_comprimento_assentado(self):
        apid = self.ap(("ASSENTADO", 40, 52))
        q = dict(self.q("SELECT servico, previsto FROM apontamento_quantidades WHERE apontamento_id=?", apid))
        self.assertEqual(q["ASSENTAMENTO"], 12)

    def test_reaterro_sem_cadastro_de_campo_gera_alerta(self):
        self.ap(("ASSENTADO", 0, 30), ("CADASTRO_CAMPO", 0, 15))
        self.ap(("REATERRADO", 0, 15))
        self.ap(("REATERRADO", 15, 25))
        self.assertEqual(self.q("SELECT ini_m, sem_cadastro_campo FROM intervalos_execucao WHERE etapa='REATERRADO' ORDER BY ini_m"),
                         [(0.0, 0), (15.0, 1)])
        sit = S.situacao_intervalos(self.c, TR)
        self.assertTrue(any("sem cadastro de campo" in a and "15–25 m" in a for a in sit["alertas"]))
        with self.assertRaisesRegex(S.RegraViolada, "sem assentamento registrado"):
            self.ap(("CADASTRO_CAMPO", 25, 35))

    def test_cem_por_cento_preenche_so_as_lacunas(self):
        self.ap(("ASSENTADO", 0, 30), ("ASSENTADO", 40, 50), ("REATERRADO", 0, 30))
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, concluido_100=True)
        self.assertEqual(self.q("SELECT etapa, ini_m, fim_m FROM intervalos_execucao WHERE origem='COMPLETO' ORDER BY etapa, ini_m"),
                         [("ASSENTADO", 30.0, 40.0), ("ASSENTADO", 50.0, 76.55),
                          ("REATERRADO", 30.0, 76.55)])
        self.assertEqual(self.ex(), (76.55, 76.55, 1))
        self.assertEqual(S.situacao_intervalos(self.c, TR)["etapas"]["ASSENTADO"]["lacunas"], [])

    def test_apontamento_so_em_metros_e_recusado_no_trecho(self):
        with self.assertRaisesRegex(S.RegraViolada, "não indica a posição"):
            S.apontar(self.c, D, "Zona01", "TRECHO", TR, metros_executados=10, metros_reaterrados=5)
        self.assertEqual(self.q("SELECT COUNT(*) FROM apontamentos")[0][0], 0)

    def test_mnd_sem_reaterro(self):
        with self.assertRaisesRegex(S.RegraViolada, "MND não tem vala"):
            self.ap(("ASSENTADO", 0, 10), ("REATERRADO", 0, 10), alvo=MND, equipe="Zona02")
        self.ap(("ASSENTADO", 0, 17.95), ("CADASTRO_CAMPO", 0, 17.95), alvo=MND, equipe="Zona02")
        self.assertEqual(self.ex(MND), (17.95, 17.95, 1))
        self.assertNotIn("REATERRADO", S.situacao_intervalos(self.c, MND)["etapas"])

    def test_verificacao_por_outra_pessoa(self):
        self.ap(("ASSENTADO", 0, 30), informado_por="Encarregado A")
        iid = self.q("SELECT id FROM intervalos_execucao")[0][0]
        with self.assertRaisesRegex(S.RegraViolada, "não pode verificá-lo"):
            S.verificar_intervalo(self.c, iid, "encarregado a")
        S.verificar_intervalo(self.c, iid, "Fiscal B")
        with self.assertRaisesRegex(S.RegraViolada, "já verificado"):
            S.verificar_intervalo(self.c, iid, "Fiscal B")
        self.assertEqual(self.q("SELECT verificado_por FROM intervalos_execucao"), [("Fiscal B",)])

    def test_trecho_com_ok_nao_aceita_intervalo(self):
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, concluido_100=True)
        tid = S.alvo(self.c, "TRECHO", TR)["id"]
        self.c.execute("UPDATE execucao SET ok_fiscal_em=? WHERE alvo_id=?", (D, tid))
        with self.assertRaisesRegex(S.RegraViolada, "já validado"):
            self.ap(("CADASTRO_CAMPO", 0, 10))


class TestSoldas(BaseCampo):
    def test_informadas_e_verificadas_por_outra_pessoa(self):
        sid = S.registrar_soldas(self.c, D, "Zona01", "TRECHO", TR, "ELETROFUSAO", 6, "Soldador X", "Encarregado A", posicao_m=12)
        S.registrar_soldas(self.c, D, "Zona01", "TRECHO", TR, "ELETROFUSAO", 4, "Soldador X", "Encarregado A")
        for args, msg in (((self.c, D, "Zona01", "TRECHO", TR, "ELETROFUSAO", 1.5, "S", "E"), "inteiro"),
                          ((self.c, D, "Zona01", "TRECHO", TR, "ARCO", 1, "S", "E"), "Tipo de solda"),
                          ((self.c, D, "Zona01", "TRECHO", TR, "TOPO", 1, "", "E"), "soldador"),
                          ((self.c, D, "Zona01", "TRECHO", TR, "TOPO", 1, "S", "E", 90), "fora do trecho")):
            with self.assertRaisesRegex(S.RegraViolada, msg):
                S.registrar_soldas(*args)
        for quem in ("soldador x", "Encarregado A"):
            with self.assertRaisesRegex(S.RegraViolada, "não pode verificar"):
                S.verificar_soldas(self.c, sid, quem, "APROVADA")
        with self.assertRaisesRegex(S.RegraViolada, "motivo da reprovação"):
            S.verificar_soldas(self.c, sid, "Fiscal B", "REPROVADA")
        S.verificar_soldas(self.c, sid, "Fiscal B", "APROVADA")
        r = S.resumo_soldas(self.c, "TRECHO", TR)
        self.assertEqual((r["estimativa_barras_6m"], r["informadas"], r["aprovadas"], r["sem_verificacao"]), (13, 10, 6, 4))
        self.assertEqual(self.q("SELECT COUNT(*) FROM medicao_lancamentos")[0][0], 0)


class TestFotoOriginal(BaseCampo):
    def test_original_preservado_com_hash_e_exif(self):
        b64 = jpeg("2026-10-15T09:41:07", -15.908712, -47.768601)
        r = S.registrar_foto(self.c, "TRECHO", TR, "EXECUCAO", b64, data_hora="2026-10-15T12:00:00", lat=-1.0, lon=-2.0,
                             dir_fotos=self.fotos)
        original = base64.b64decode(b64)
        with open(os.path.join(self.fotos, r["arquivo"]), "rb") as f:
            self.assertEqual(f.read(), original)                                  # byte a byte, sem recompressão
        self.assertEqual(r["sha256"], hashlib.sha256(original).hexdigest())
        f = self.q("SELECT data_hora, origem_data, round(lat,6), round(lon,6), origem_gps, mime, bytes FROM fotos")[0]
        self.assertEqual(f, ("2026-10-15T09:41:07", "EXIF", -15.908712, -47.768601, "EXIF", "image/jpeg", len(original)))

    def test_sem_exif_usa_dispositivo_ou_envio_e_nunca_inventa_gps(self):
        S.registrar_foto(self.c, "TRECHO", TR, "SINALIZACAO", jpeg(), data_hora="2026-10-15T08:00:00", dir_fotos=self.fotos)
        S.registrar_foto(self.c, "TRECHO", TR, "CONCLUIDO", jpeg(), lat=-15.9, lon=-47.7, dir_fotos=self.fotos)
        rows = self.q("SELECT categoria, origem_data, origem_gps, lat FROM fotos ORDER BY id")
        self.assertEqual(rows[0], ("SINALIZACAO", "DISPOSITIVO", None, None))
        self.assertEqual(rows[1][:3], ("CONCLUIDO", "ENVIO", "NAVEGADOR"))
        self.assertIn("GPS indisponível", self.q("SELECT carimbo FROM fotos ORDER BY id")[0][0])

    def test_reuso_e_arquivo_invalido_sao_recusados(self):
        b64 = jpeg()
        S.registrar_foto(self.c, "TRECHO", TR, "EXECUCAO", b64, dir_fotos=self.fotos)
        with self.assertRaisesRegex(S.RegraViolada, "mesma imagem já foi registrada"):
            S.registrar_foto(self.c, "TRECHO", "Zona01_PB01_Rede_TR002", "EXECUCAO", b64, dir_fotos=self.fotos)
        with self.assertRaisesRegex(S.RegraViolada, "não é uma imagem"):
            S.registrar_foto(self.c, "TRECHO", TR, "CONCLUIDO", base64.b64encode(b"%PDF-1.4 ...").decode(), dir_fotos=self.fotos)
        lim = S.LIMITE_FOTO
        try:
            S.LIMITE_FOTO = 10
            with self.assertRaisesRegex(S.RegraViolada, "maior que"):
                S.registrar_foto(self.c, "TRECHO", TR, "CONCLUIDO", jpeg(), dir_fotos=self.fotos)
        finally:
            S.LIMITE_FOTO = lim
        self.assertEqual(self.q("SELECT COUNT(*) FROM fotos")[0][0], 1)

    def test_backup_confere_o_hash_registrado_da_foto(self):
        S.registrar_foto(self.c, "TRECHO", TR, "EXECUCAO", jpeg(), dir_fotos=self.fotos)
        pasta = backup.criar(self.db, os.path.join(self.tmp, "bk"), self.fotos)
        self.assertEqual(backup.verificar(pasta), (True, []))
        nome = self.q("SELECT arquivo FROM fotos")[0][0]
        p = os.path.join(pasta, "fotos", nome)
        with open(p, "wb") as f:
            f.write(base64.b64decode(jpeg()))                                      # troca a foto…
        mp = os.path.join(pasta, "manifesto.json")
        with open(mp, encoding="utf-8") as f:
            m = json.load(f)
        m["arquivos"]["fotos/" + nome] = {"sha256": backup.sha256(p), "bytes": os.path.getsize(p)}   # …e "acerta" o manifesto
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(m, f)
        ok, erros = backup.verificar(pasta)
        self.assertFalse(ok)
        self.assertTrue(any("difere do registrado no banco" in e for e in erros), erros)


class TestMigracaoCampo(Base):
    def test_foto_e_apontamento_legados_sem_dados_inventados(self):
        c = sqlite3.connect(self.db)
        with open(os.path.join(AQUI, "fixtures", "schema_v2.sql"), encoding="utf-8") as f:
            c.executescript(f.read())
        c.execute("INSERT INTO schema_versao VALUES (2, 'x', 'v2')")
        c.execute("INSERT INTO equipes(id,nome) VALUES ('Zona01','Z1')")
        c.execute("INSERT INTO fotos(alvo_tipo,alvo_id,categoria,arquivo,data_hora,carimbo) VALUES ('TRECHO','TR-00001','EXECUCAO','velha.jpg','x','c')")
        c.execute("INSERT INTO apontamentos(data,equipe_id,alvo_tipo,alvo_id,metros_executados) VALUES (?, 'Zona01','TRECHO','TR-00001',12)", (D,))
        c.commit()
        c.close()
        with open(os.path.join(self.fotos, "velha.jpg"), "wb") as f:
            f.write(b"carimbada")
        rel = self.aplicar()
        self.assertEqual(self.q("SELECT MAX(versao) FROM schema_versao")[0][0], S.VERSAO_ESQUEMA)
        self.assertEqual(self.q("SELECT origem_data, sha256 FROM fotos"), [("LEGADO", None)])
        self.assertEqual(self.q("SELECT COUNT(*) FROM intervalos_execucao")[0][0], 0)   # posição antiga desconhecida
        self.assertEqual(rel["registros_operacionais_preservados"]["apontamentos"], 1)
        shutil.rmtree(os.path.join(self.dados, "backups"))


if __name__ == "__main__":
    unittest.main()


# ====================================================================== auditoria do commit f035f5c (F01–F05)
TR_ID = "TR-00001"


def banco_legado(test, versao=5):
    """Banco v5 (ou v6) REAL, com o esquema do commit correspondente: TR001 com 30 m assentados e 20 m reaterrados
    apontados só em metros (sem intervalos), como o modelo anterior permitia."""
    c = sqlite3.connect(test.db)
    with open(os.path.join(AQUI, "fixtures", f"schema_v{versao}.sql"), encoding="utf-8") as f:
        c.executescript(f.read())
    c.execute("INSERT INTO schema_versao VALUES (?,'x','legado')", (versao,))
    c.execute("INSERT INTO equipes(id,nome) VALUES ('Zona01','Z1')")
    c.execute("""INSERT INTO trechos(id,ponto,frente_id,de_mm,material,metodologia,extensao_m,quantidades,handle,utm_ini,utm_fim)
                 VALUES (?,?, 'Zona01', 63, 'PEAD', 'VCA', 76.55, '{}', '5FD12', '[10.0, 10.0]', '[20.0, 20.0]')""", (TR_ID, TR))
    c.execute("INSERT INTO apontamentos(data,equipe_id,alvo_tipo,alvo_id,metros_executados,metros_reaterrados) "
              "VALUES ('2026-10-14','Zona01','TRECHO',?,30,20)", (TR_ID,))
    c.execute("INSERT INTO apontamento_quantidades VALUES (1,'ASSENTAMENTO','M',30,30)")
    c.execute("INSERT INTO execucao(alvo_tipo,alvo_id,metros_executados,metros_reaterrados,concluido) VALUES ('TRECHO',?,30,20,0)",
              (TR_ID,))
    c.commit()
    return c


class TestF01AvancoLegado(Base):
    LIBERAR_TUDO = True

    def setUp(self):
        super().setUp()
        banco_legado(self).close()
        self.rel = self.aplicar()
        self.c = self.conectar()
        for d in ("2026-10-15", "2026-10-16"):
            for t in ("MANHA", "TARDE"):
                S.registrar_clima(self.c, d, "Zona01", t, "SOL")

    def ex(self):
        e = S.execucao(self.c, "TRECHO", TR_ID)
        return (e["metros_executados"], e["metros_reaterrados"])

    def iv(self, *t, data="2026-10-16"):
        return S.apontar(self.c, data, "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": e, "ini_m": a, "fim_m": b} for e, a, b in t])

    def test_reproducao_migracao_preserva_30_20_e_alerta(self):
        self.assertEqual(self.rel["esquema_antes"], 5)
        self.assertEqual(self.ex(), (30, 20))
        sit = S.situacao_intervalos(self.c, TR)
        self.assertEqual((sit["legado"]["ASSENTADO"], sit["legado"]["REATERRADO"]), (30, 20))
        self.assertTrue(any("SEM POSIÇÃO" in a for a in sit["alertas"]))
        with self.assertRaisesRegex(S.RegraViolada, "Concilie a posição"):
            self.iv(("ASSENTADO", 30, 40))                                     # antes virava 10/0
        with self.assertRaisesRegex(S.RegraViolada, "Concilie a posição"):
            S.apontar(self.c, "2026-10-16", "Zona01", "TRECHO", TR, concluido_100=True)
        self.c.execute("UPDATE execucao SET concluido=1 WHERE alvo_id=?", (TR_ID,))
        with self.assertRaisesRegex(S.RegraViolada, "Concilie a posição"):
            S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng", "2026-10-16")
        self.assertEqual(self.ex(), (30, 20))

    def test_conciliacao_exata_sem_duplicar_servicos_e_continuidade(self):
        conc = lambda *t, **kw: S.conciliar_legado(self.c, TR, [dict(etapa=e, ini_m=a, fim_m=b, **kw) for e, a, b in t],
                                                   "confirmado em campo com trena", "Eng. Responsável")
        with self.assertRaisesRegex(S.RegraViolada, "legado tem 30 m"):
            conc(("ASSENTADO", 0, 25), ("REATERRADO", 0, 20))
        with self.assertRaisesRegex(S.RegraViolada, "fora do período"):
            conc(("ASSENTADO", 0, 30), ("REATERRADO", 0, 20), data="2026-10-20")
        with self.assertRaisesRegex(S.RegraViolada, "motivo"):
            S.conciliar_legado(self.c, TR, [], "", "")
        cid = conc(("ASSENTADO", 0, 30), ("REATERRADO", 0, 20))
        self.assertEqual(self.ex(), (30, 20))
        self.assertEqual(self.q("SELECT etapa, ini_m, fim_m, origem, apontamento_id, conciliacao_id, data FROM intervalos_execucao ORDER BY etapa"),
                         [("ASSENTADO", 0.0, 30.0, "LEGADO", None, cid, "2026-10-14"),
                          ("REATERRADO", 0.0, 20.0, "LEGADO", None, cid, "2026-10-14")])
        self.assertEqual(self.q("SELECT COUNT(*) FROM apontamentos")[0][0], 1)                 # nenhum apontamento novo
        self.assertEqual(self.q("SELECT SUM(confirmado) FROM apontamento_quantidades")[0][0], 30)
        self.assertIsNone(S.situacao_intervalos(self.c, TR)["legado"])
        with self.assertRaisesRegex(S.RegraViolada, "não tem avanço anterior"):
            conc(("ASSENTADO", 30, 60), ("REATERRADO", 20, 40))
        self.iv(("ASSENTADO", 30, 40))
        self.assertEqual(self.ex(), (40, 20))                                                 # sem perda
        self.assertEqual(self.q("SELECT SUM(confirmado) FROM apontamento_quantidades WHERE servico='ASSENTAMENTO'")[0][0], 40)
        with self.assertRaisesRegex(S.RegraViolada, "sobrepõe"):
            self.iv(("ASSENTADO", 10, 20))                                                     # legado agora tem posição

    def test_estado_ja_danificado_pela_versao_anterior_volta_a_somar(self):
        # f035f5c: um intervalo 30–40 gravado por cima do legado deixou o resumo em 10/0
        self.c.execute("INSERT INTO apontamentos(data,equipe_id,alvo_tipo,alvo_id,metros_executados) VALUES ('2026-10-16','Zona01','TRECHO',?,10)", (TR_ID,))
        ap = self.q("SELECT MAX(id) FROM apontamentos")[0][0]
        self.c.execute("INSERT INTO intervalos_execucao(trecho_id,etapa,ini_m,fim_m,data,apontamento_id,origem,registrado_em) "
                       "VALUES (?,'ASSENTADO',30,40,'2026-10-16',?,'INFORMADO','x')", (TR_ID, ap))
        self.c.execute("UPDATE execucao SET metros_executados=10, metros_reaterrados=0 WHERE alvo_id=?", (TR_ID,))
        self.assertEqual(S.situacao_intervalos(self.c, TR)["legado"]["ASSENTADO"], 30)        # legado continua reconhecido
        S.conciliar_legado(self.c, TR, [{"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 30}, {"etapa": "REATERRADO", "ini_m": 0, "fim_m": 20}],
                           "posição confirmada", "Eng.")
        self.assertEqual(self.ex(), (40, 20))


class TestF02SoldasSoReferencia(BaseCampo):
    def test_estimativa_nao_vira_confirmada_e_ok_usa_soldas_aprovadas(self):
        ap = self.ap(("ASSENTADO", 0, 12))
        self.assertEqual(self.q("SELECT COUNT(*) FROM apontamento_quantidades WHERE servico='SOLDA'")[0][0], 0)
        prev = {q["servico"]: q for q in S.previsto(self.c, "TRECHO", TR, 12)}
        self.assertEqual((prev["SOLDA"]["previsto"], prev["SOLDA"]["estimativa"]), (2, True))  # aparece só como estimativa
        with self.assertRaisesRegex(S.RegraViolada, "controle de soldas"):
            self.ap(("ASSENTADO", 12, 20), quantidades=[{"servico": "SOLDA", "unidade": "UN", "confirmado": 2}])
        # resíduo da versão anterior: SOLDA "confirmada" pela estimativa num apontamento antigo
        self.c.execute("INSERT INTO apontamento_quantidades VALUES (?,'SOLDA','UN',2,2)", (ap,))
        s1 = S.registrar_soldas(self.c, D, "Zona01", "TRECHO", TR, "ELETROFUSAO", 3, "Soldador X", "Enc")
        s2 = S.registrar_soldas(self.c, D, "Zona01", "TRECHO", TR, "ELETROFUSAO", 1, "Soldador X", "Enc")
        S.verificar_soldas(self.c, s1, "Fiscal", "APROVADA")
        S.verificar_soldas(self.c, s2, "Fiscal", "REPROVADA", "fusão incompleta")
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, concluido_100=True)
        for cat in ("SINALIZACAO", "EXECUCAO", "CONCLUIDO"):
            S.registrar_foto(self.c, "TRECHO", TR, cat, jpeg(), dir_fotos=self.fotos)
        S.criar_medicao(self.c, 1, "2026-10-01", "2026-10-31")
        S.verificar_trecho(self.c, TR, "Fiscal")                        # o OK interno exige a verificação (v20)
        S.ok_fiscalizacao(self.c, "TRECHO", TR, "eng", D)
        sold = self.q("SELECT quantidade, status FROM medicao_lancamentos WHERE servico='SOLDA'")
        self.assertEqual(sold, [(3.0, "PENDENTE")])                                           # aprovadas; nem 2 nem 13


class TestF03Cronologia(BaseCampo):
    def test_pre_requisito_posterior_nao_vale_como_anterior(self):
        for t in ("MANHA", "TARDE"):
            for d in ("2026-10-14", "2026-10-16", "2026-10-17"):
                S.registrar_clima(self.c, d, "Zona01", t, "SOL")
        S.apontar(self.c, "2026-10-16", "Zona01", "TRECHO", TR, intervalos_novos=[
            {"etapa": "ASSENTADO", "ini_m": 0, "fim_m": 20}, {"etapa": "CADASTRO_CAMPO", "ini_m": 0, "fim_m": 10}])
        with self.assertRaisesRegex(S.RegraViolada, "sem assentamento registrado até essa data"):
            self.ap(("REATERRADO", 0, 20))                                                   # 15/10 < 16/10
        self.assertEqual(self.q("SELECT COUNT(*) FROM intervalos_execucao WHERE etapa='REATERRADO'")[0][0], 0)
        S.apontar(self.c, "2026-10-16", "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "REATERRADO", "ini_m": 0, "fim_m": 10}])
        S.apontar(self.c, "2026-10-16", "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "REATERRADO", "ini_m": 10, "fim_m": 20}])
        S.apontar(self.c, "2026-10-17", "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "CADASTRO_CAMPO", "ini_m": 10, "fim_m": 20}])
        self.assertEqual(self.q("SELECT ini_m, sem_cadastro_campo FROM intervalos_execucao WHERE etapa='REATERRADO' ORDER BY ini_m"),
                         [(0.0, 0), (10.0, 1)])                                               # cadastro de 17/10 não conta para 16/10
        S.apontar(self.c, "2026-10-14", "Zona01", "TRECHO", TR, intervalos_novos=[{"etapa": "ASSENTADO", "ini_m": 20, "fim_m": 30}])
        self.ap(("REATERRADO", 20, 30))                                                      # 15/10 sobre assentamento de 14/10: ok


class TestF04HistoricoDeSoldas(Base):
    def test_trecho_so_com_soldas_nao_some_sem_conciliacao(self):
        self.aplicar()
        c = self.conectar()
        S.registrar_soldas(c, D, "Zona02", "TRECHO", MND, "ELETROFUSAO", 2, "Soldador", "Enc")
        tid = S.alvo(c, "TRECHO", MND)["id"]
        import planilhas_sinteticas as PS
        self.regerar(trechos=PS.TRECHOS[:2])                                       # controles próprios da revisão
        rel = self.reprovar("TRECHO_COM_HISTORICO_SEM_CORRESPONDENCIA")
        self.assertTrue(any(tid == b["referencia"] for b in rel["bloqueios"]))
        self.cfg["conciliacoes"] = [{"tipo": "TRECHO", "retirar_id": tid, "responsavel": "Eng.", "data": "2026-10-17",
                                     "motivo": "trecho excluído do projeto"}]
        self.assertEqual(self.aplicar()["status"], "CONCLUIDA")
        (ret,) = S.estado_mapa(c)["retirados_com_historico"]
        self.assertEqual((ret["alvo_id"], ret["historico"]), (tid, ["soldas"]))
        self.assertIn("2 solda(s) registrada(s)", ret["situacoes"])

    def test_reserva_para_o_trecho_tambem_conta_como_historico(self):
        self.aplicar()
        c = self.conectar()
        S.entrada_material(c, D, "CAESB-PEAD-DE63", 10, "ROMANEIO_CAESB", "R", "a")
        S.reservar(c, D, "Zona02", "CAESB-PEAD-DE63", 5, "TRECHO", MND)
        import planilhas_sinteticas as PS
        self.regerar(trechos=PS.TRECHOS[:2])
        self.reprovar("TRECHO_COM_HISTORICO_SEM_CORRESPONDENCIA")


class TestF05ImagemValida(BaseCampo):
    def foto(self, b64, cat="EXECUCAO"):
        return S.registrar_foto(self.c, "TRECHO", TR, cat, b64, dir_fotos=self.fotos)

    def test_reproducao_assinatura_jpeg_sem_imagem_e_recusada(self):
        falso = base64.b64encode(b"\xff\xd8\xff" + b"isto nao e uma imagem" * 5).decode()
        with self.assertRaisesRegex(S.RegraViolada, "Foto recusada"):
            self.foto(falso)
        self.assertEqual(S.fotos_faltando(self.c, "TRECHO", TR), ["SINALIZACAO", "EXECUCAO", "CONCLUIDO"])

    def test_truncadas_corrompidas_e_heic_recusadas(self):
        from fotos_teste import jpeg_bytes, png
        d = jpeg_bytes()
        for corte in (len(d) - 2, len(d) - 40, len(d) // 2, 30):
            with self.assertRaisesRegex(S.RegraViolada, "Foto recusada"):
                self.foto(base64.b64encode(d[:corte]).decode())
        p = bytearray(base64.b64decode(png()))
        p[40] ^= 0xFF                                                        # CRC do bloco deixa de conferir
        with self.assertRaisesRegex(S.RegraViolada, "Foto recusada"):
            self.foto(base64.b64encode(bytes(p)).decode())
        heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 40
        with self.assertRaisesRegex(S.RegraViolada, "HEIC"):
            self.foto(base64.b64encode(heic).decode())
        self.assertEqual(self.q("SELECT COUNT(*) FROM fotos")[0][0], 0)

    def test_imagens_validas_jpeg_progressivo_png_e_exif_invalido(self):
        from fotos_teste import jpeg_bytes, png
        r1 = self.foto(jpeg(base="base_progressiva.jpg"), "SINALIZACAO")
        r2 = self.foto(png(), "EXECUCAO")
        d = jpeg_bytes()
        lixo = b"\xff\xe1\x00\x10Exif\x00\x00MM\x00\x2a\xff\xff\xff\xff"            # EXIF ilegível, imagem íntegra
        r3 = self.foto(base64.b64encode(d[:2] + lixo + d[2:]).decode(), "CONCLUIDO")
        self.assertEqual(r3["origem_data"], "ENVIO")                                          # EXIF ignorado, não inventado
        self.assertTrue(all(r["validacao"].startswith("DECODIFICADA") or r["validacao"].startswith("ESTRUTURAL")
                            for r in (r1, r2, r3)))
        self.assertEqual(S.fotos_faltando(self.c, "TRECHO", TR), [])

    def test_sem_pillow_a_validacao_estrutural_continua_recusando(self):
        import imagens
        from fotos_teste import jpeg_bytes
        pil = imagens._PIL
        imagens._PIL = None
        try:
            self.assertEqual(self.foto(jpeg())["validacao"], "ESTRUTURAL (JPEG, sem Pillow)")
            d = jpeg_bytes()
            with self.assertRaisesRegex(S.RegraViolada, "EOI"):
                self.foto(base64.b64encode(d[:-2]).decode(), "CONCLUIDO")
        finally:
            imagens._PIL = pil

    def test_fixtures_sao_imagens_decodificaveis(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow não instalado: decodificação completa não verificada aqui")
        import io
        from fotos_teste import png
        for b64 in (jpeg(), jpeg("2026-10-15T09:00:00", -15.9, -47.7), jpeg(base="base_progressiva.jpg"), png()):
            with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
                im.load()
                self.assertGreater(im.size[0] * im.size[1], 0)


class TestMigracaoV6ParaV7(Base):
    def test_intervalos_e_fotos_v6_continuam_e_sao_revalidadas(self):
        from fotos_teste import jpeg_bytes
        c = banco_legado(self, versao=6)
        c.execute("DELETE FROM apontamento_quantidades")
        c.execute("UPDATE apontamentos SET metros_executados=10, metros_reaterrados=0")
        c.execute("INSERT INTO intervalos_execucao(trecho_id,etapa,ini_m,fim_m,data,apontamento_id,origem,registrado_em) "
                  "VALUES (?, 'ASSENTADO', 0, 10, '2026-10-14', 1, 'SEQUENCIAL', 'x')", (TR_ID,))
        c.execute("UPDATE execucao SET metros_executados=10, metros_reaterrados=0")
        boa, ruim = jpeg_bytes(), b"\xff\xd8\xff texto"
        for nome, dados in (("boa.jpg", boa), ("ruim.jpg", ruim)):
            with open(os.path.join(self.fotos, nome), "wb") as f:
                f.write(dados)
        for cat, arq in (("SINALIZACAO", "boa.jpg"), ("EXECUCAO", "ruim.jpg"), ("CONCLUIDO", "sumiu.jpg")):
            c.execute("INSERT INTO fotos(alvo_tipo,alvo_id,categoria,arquivo,data_hora,carimbo,origem_data) "
                      "VALUES ('TRECHO',?,?,?,'2026-10-14','c','LEGADO')", (TR_ID, cat, arq))
        c.commit()
        c.close()
        with self.assertRaises(backup.BackupIncompleto):                      # foto referenciada e ausente
            self.aplicar()
        rel = self.aplicar(aceitar_backup_incompleto=True)
        self.assertEqual((rel["esquema_antes"], rel["esquema_depois"]), (6, S.VERSAO_ESQUEMA))
        self.assertEqual(self.q("SELECT id, etapa, ini_m, fim_m, origem FROM intervalos_execucao"),
                         [(1, "ASSENTADO", 0.0, 10.0, "SEQUENCIAL")])                     # copiado sem perda
        self.assertEqual(dict(self.q("SELECT arquivo, validacao FROM fotos")),
                         {"boa.jpg": "DECODIFICADA (Pillow)" if __import__("imagens")._PIL else "ESTRUTURAL (JPEG, sem Pillow)",
                          "ruim.jpg": "INVALIDA", "sumiu.jpg": "ARQUIVO_AUSENTE"})
        c2 = self.conectar()
        self.assertEqual(S.fotos_faltando(c2, "TRECHO", TR), ["EXECUCAO", "CONCLUIDO"])      # inválida/ausente não contam
        self.assertIsNone(S.situacao_intervalos(c2, TR)["legado"])                          # apontamento já tinha intervalo
        self.assertTrue(any("posição presumida" in a for a in S.situacao_intervalos(c2, TR)["alertas"]))
        c2.execute("INSERT INTO intervalos_execucao(trecho_id,etapa,ini_m,fim_m,data,origem,registrado_em) "
                               "VALUES (?, 'ASSENTADO', 50, 60, '2026-10-14', 'LEGADO', 'x')", (TR_ID,))   # CHECK aceita LEGADO
