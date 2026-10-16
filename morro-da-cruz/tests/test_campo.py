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
        with self.assertRaisesRegex(S.RegraViolada, "não assentado: 30–35"):
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
        with self.assertRaisesRegex(S.RegraViolada, "não assentado"):
            self.ap(("CADASTRO_CAMPO", 25, 35))

    def test_cem_por_cento_preenche_so_as_lacunas(self):
        self.ap(("ASSENTADO", 0, 30), ("ASSENTADO", 40, 50), ("REATERRADO", 0, 30))
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, concluido_100=True)
        self.assertEqual(self.q("SELECT etapa, ini_m, fim_m FROM intervalos_execucao WHERE origem='COMPLETO' ORDER BY etapa, ini_m"),
                         [("ASSENTADO", 30.0, 40.0), ("ASSENTADO", 50.0, 76.55),
                          ("REATERRADO", 30.0, 76.55)])
        self.assertEqual(self.ex(), (76.55, 76.55, 1))
        self.assertEqual(S.situacao_intervalos(self.c, TR)["etapas"]["ASSENTADO"]["lacunas"], [])

    def test_apontamento_so_em_metros_fica_sinalizado(self):
        S.apontar(self.c, D, "Zona01", "TRECHO", TR, metros_executados=10, metros_reaterrados=5)
        self.assertEqual(self.q("SELECT etapa, ini_m, fim_m, origem FROM intervalos_execucao ORDER BY etapa"),
                         [("ASSENTADO", 0.0, 10.0, "SEQUENCIAL"), ("REATERRADO", 0.0, 5.0, "SEQUENCIAL")])
        self.assertTrue(any("posição presumida" in a for a in S.situacao_intervalos(self.c, TR)["alertas"]))

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
