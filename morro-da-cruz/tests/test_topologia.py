"""Topologia dos trechos: ponta no nó, cruzamento e trecho físico (topologia.py, mapa_geral.py, config/topologia.json).

Sobre o banco montado a partir das planilhas REAIS do repositório (06.1 REV01 e 06.2 REV08) e o mapa REV02:
  * caso A: Zona04_PB06_Rede_TR002 para 1,47 m antes do NÓ2.1 e é desenhado encaixado no nó (visão geral e PB06);
  * caso B: TR007 + TR006 (PB08) = um trecho físico de 295,98 m de NÓ9.1 até VRP-15; o NÓ113.1 é cruzamento e os
    outros tubos do nó (TR011, TR003, TR004) ficam fora da cadeia DE 160;
  * luva ou redução entre dois trechos é conexão: não junta;
  * para_linhas / para_fisico fazem ida e volta com sentido +1 e −1;
  * os números do diagnóstico ficam fixados (mudam só com mudança de planilha, mapa ou regra, de propósito).
"""
import json
import math
import os
import random
import shutil
import sqlite3
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(AQUI)
sys.path.insert(0, APP)
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(APP, "ferramentas", "topologia"))
import importacao as I  # noqa: E402
import importar  # noqa: E402
import mapa_geral as MG  # noqa: E402
import server  # noqa: E402
import topologia as TP  # noqa: E402
from perfil_teste import cfg_teste_real  # noqa: E402

MAPA = server._mapa_path()
CFG = I.carregar_config()
TEM_DADOS = all(I.caminho(CFG, k) for k in ("redes", "conexoes", "evidencias", "bm", "reajuste")) and os.path.exists(MAPA)
TR002, NO21 = "Zona04_PB06_Rede_TR002", "Zona04_PB06_Rede_NÓ2.1"
TR006, TR007, NO113 = "Zona03_PB08_Rede_TR006", "Zona03_PB08_Rede_TR007", "Zona03_PB08_Rede_NÓ113.1"


def _cfg():
    with open(TP.CONFIG, encoding="utf-8") as f:
        return json.load(f)


def _limpar_caches():
    TP._CACHE.clear()
    for k in ("pontas", "correcoes", "geometria", "derivados_chave"):
        MG._CACHE.pop(k, None)


class Conversao(unittest.TestCase):
    """para_linhas / para_fisico: sem banco, num trecho físico montado à mão com sentidos +1 e −1."""
    F = {"id": "TF-TESTE", "membros": [
        {"trecho_id": "TR-A", "ponto": "A", "ordem": 1, "offset_m": 0.0, "extensao_m": 10.0, "sentido": 1},
        {"trecho_id": "TR-B", "ponto": "B", "ordem": 2, "offset_m": 10.0, "extensao_m": 5.5, "sentido": -1},
        {"trecho_id": "TR-C", "ponto": "C", "ordem": 3, "offset_m": 15.5, "extensao_m": 7.25, "sentido": 1}]}

    def test_fisico_para_linhas_com_sentido_menos_um(self):
        self.assertEqual(TP.para_linhas(self.F, 3, 18), [
            {"trecho_id": "TR-A", "ponto": "A", "ini_m": 3.0, "fim_m": 10.0},
            {"trecho_id": "TR-B", "ponto": "B", "ini_m": 0.0, "fim_m": 5.5},       # linha inteira (sentido −1)
            {"trecho_id": "TR-C", "ponto": "C", "ini_m": 0.0, "fim_m": 2.5}])
        self.assertEqual(TP.para_linhas(self.F, 11, 12.5), [{"trecho_id": "TR-B", "ponto": "B", "ini_m": 3.0, "fim_m": 4.5}])
        self.assertEqual(TP.para_linhas(self.F, 12.5, 11), TP.para_linhas(self.F, 11, 12.5))   # ordem não importa
        self.assertEqual(TP.para_linhas(self.F, 10, 10.0005), [])                              # abaixo de 1 mm: nada
        self.assertEqual(TP.para_linhas(self.F, -5, 100)[-1]["fim_m"], 7.25)                   # cortado na linha

    def test_linha_para_fisico(self):
        self.assertEqual(TP.para_fisico(self.F, "TR-A", 2, 4), (2.0, 4.0))
        self.assertEqual(TP.para_fisico(self.F, "TR-B", 3, 4.5), (11.0, 12.5))    # sentido −1: ext − y, ext − x
        self.assertEqual(TP.para_fisico(self.F, "TR-C", 0, 7.25), (15.5, 22.75))
        self.assertEqual(TP.para_fisico(self.F, "TR-B", -1, 99), (10.0, 15.5))     # cortado em [0, ext]
        with self.assertRaises(ValueError):
            TP.para_fisico(self.F, "TR-X", 0, 1)

    def test_ida_e_volta(self):
        rnd = random.Random(10239)
        for _ in range(500):
            x, y = sorted(round(rnd.uniform(0, 22.75), 3) for _ in range(2))
            pedacos = TP.para_linhas(self.F, x, y)
            volta = sorted(TP.para_fisico(self.F, p["trecho_id"], p["ini_m"], p["fim_m"]) for p in pedacos)
            if y - x > 1e-3:
                self.assertAlmostEqual(volta[0][0], x, places=3)
                self.assertAlmostEqual(volta[-1][1], y, places=3)
            for (a, b), (c, d) in zip(volta, volta[1:]):                 # pedaços colados, sem buraco
                self.assertAlmostEqual(b, c, places=3)
            for p in pedacos:                                            # e a volta pela linha dá o mesmo pedaço
                ini, fim = TP.para_fisico(self.F, p["trecho_id"], p["ini_m"], p["fim_m"])
                self.assertEqual(TP.para_linhas(self.F, ini, fim), [p])


@unittest.skipUnless(TEM_DADOS, "planilhas oficiais ou mapa REV02 ausentes")
class TopologiaReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raiz = tempfile.mkdtemp(prefix="topologia_")
        cls.db = os.path.join(cls.raiz, "obra.db")
        os.makedirs(os.path.join(cls.raiz, "fotos"))
        importar.aplicar(cls.db, I.DIR_PLANILHAS, cfg=cfg_teste_real(), dir_relatorios=os.path.join(cls.raiz, "rel"))
        cls.c = sqlite3.connect(cls.db)
        cls.id = dict(cls.c.execute("SELECT ponto, id FROM trechos WHERE vigente = 1"))
        _limpar_caches()

    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        _limpar_caches()
        shutil.rmtree(cls.raiz)

    def ponta(self, trecho, lado):
        return next(p for p in MG.pontas(MAPA) if p["trecho"] == trecho and p["lado"] == lado)

    # ---------------------------------------------------------------- caso A: desenho que não chega ao nó
    def test_caso_a_ponta_para_antes_do_no_e_e_encaixada(self):
        p = self.ponta(TR002, "ini")
        self.assertEqual((p["no"], p["classe"], p["acao"]), (NO21, "NAO_CHEGA", "ESTENDER_ATE_NO"))
        self.assertAlmostEqual(p["d_no_m"], 1.465, delta=0.01)
        self.assertLess(p["d_utm_m"], 0.03)                                # o desenho está na UTM da 06.1 ...
        self.assertGreater(p["ao_longo_m"], 0.95 * p["d_no_m"])           # ... e o nó fica à frente, na linha
        self.assertEqual(self.ponta(TR002, "fim")["classe"], "NO_NO")
        g = MG.geometria(MAPA)
        no = next(e for e in g["els"] if NO21 in e["n"])
        tr = next(t for t in g["trechos"] if t["n"] == TR002)
        pontas = [(pt[0], pt[1]) for pt in tr["p"]] + [(pt[-2], pt[-1]) for pt in tr["p"]]
        self.assertLess(min(math.dist(q, (no["x"], no["y"])) for q in pontas), 0.15)   # 0,1 unidade = arredondamento
        d = MG._ler(MAPA)["dados"]
        i = next(k for k, t in enumerate(d["trechos"]) if t["R"] == TR002)
        pb06 = MG.correcoes(MAPA)["PB06"]
        pos = dict((j, (x, y)) for j, x, y in next(p for p in d["pbs"] if p["id"] == "PB06")["el"])[d["trechos"][i]["iniE"]]
        self.assertIn([i, 0, 0, 0, round(pos[0], 2), round(pos[1], 2)], pb06)       # na prancha também

    # ---------------------------------------------------------------- caso B: cruzamento com semicírculo
    def test_caso_b_vira_um_trecho_fisico_de_295_98_m(self):
        f = TP.fisico_do_trecho(self.c, self.id[TR007])
        self.assertIs(f, TP.fisico_do_trecho(self.c, self.id[TR006]))
        self.assertEqual(f["id"], "TF-" + min(self.id[TR006], self.id[TR007]).split("-")[1])
        self.assertEqual((f["no_ini"], f["no_fim"], f["extensao_m"], f["de_mm"], f["material"]),
                         ("Zona03_PB08_Rede_NÓ9.1", "Zona03_PB08_CH_VRP-15", 295.98, 160, "PEAD"))
        self.assertEqual([(m["ponto"], m["ordem"], m["offset_m"], m["extensao_m"], m["sentido"]) for m in f["membros"]],
                         [(TR007, 1, 0.0, 2.51, 1), (TR006, 2, 2.51, 293.47, 1)])
        self.assertEqual([(j["no"], j["tipo"], j["decisao"], j["posicao_m"]) for j in f["juncoes"]],
                         [(NO113, "CRUZAMENTO", "JUNTAR", 2.51)])
        self.assertEqual(f["texto"], "Trecho físico: TR007 + TR006 = 295,98 m, de NÓ9.1 até VRP-15. "
                                     "NÓ113.1 é cruzamento (não é conexão).")
        # 10 m do trecho físico a partir de 1 m: 1,51 m no fim do TR007 e 8,49 m no começo do TR006
        self.assertEqual(TP.para_linhas(f, 1, 11), [
            {"trecho_id": self.id[TR007], "ponto": TR007, "ini_m": 1.0, "fim_m": 2.51},
            {"trecho_id": self.id[TR006], "ponto": TR006, "ini_m": 0.0, "fim_m": 8.49}])

    def test_no113_os_outros_tubos_ficam_fora_da_cadeia(self):
        cadeia = {m["ponto"] for m in TP.fisico_do_trecho(self.c, self.id[TR007])["membros"]}
        for nome in ("Zona03_PB08_Rede_TR011", "Zona03_PB08_Rede_TR003", "Zona03_PB08_Rede_TR004"):
            f = TP.fisico_do_trecho(self.c, self.id[nome])
            self.assertNotIn(nome, cadeia)
            self.assertEqual([m["ponto"] for m in f["membros"]], [nome])
        # o desenho não puxa as pontas do cruzamento para o NÓ113.1: o arco do pulo fica como está
        for trecho, lado in ((TR007, "fim"), (TR006, "ini")):
            p = self.ponta(trecho, lado)
            self.assertEqual((p["classe"], p["acao"]), ("CRUZAMENTO", "NAO_ENCAIXAR"))
            self.assertTrue(p["arco"]["tem"])
        self.assertEqual(self.ponta("Zona03_PB08_Rede_TR011", "fim")["acao"], "ESTENDER_ATE_NO")  # o TR011 vai ao nó

    # ---------------------------------------------------------------- conexão de verdade não junta
    def test_luva_ou_reducao_entre_dois_trechos_nao_junta(self):
        import base as B
        import juncoes as J
        luva = [{"tipo_conexao": "LUVA", "diametro": "63", "quantidade": 1, "unidade": "UN"}]
        reducao = [{"tipo_conexao": "REDUÇÃO", "diametro": "90X63", "quantidade": 1, "unidade": "UN"}]
        self.assertEqual((B.portas(luva), B.portas(reducao)), (2, 2))
        # mesmo par alinhado, junto e afastado do marcador: com a luva (2 bocas para 2 pontas) é conexão
        self.assertEqual(J.decidir_par(2, B.portas(luva), 0.0, 180, 0.8, True)[1], "NAO_JUNTAR")
        self.assertEqual(J.decidir_par(2, B.portas(reducao), 0.0, 180, 0.8, False)[1], "NAO_JUNTAR")   # troca de DE
        self.assertEqual(J.decidir_par(4, 2, 0.0, 180, 1.5, True)[1], "JUNTAR")                       # sem peça: passa
        # nos dados reais: nó de grau 2 só com redução (19 casos) nunca junta os dois trechos
        base = B.Base(self.db, MAPA)
        pares = []
        for eid, pontas in base.pontas_el.items():
            tipos = {(p["tipo_conexao"] or "").split(" ")[0] for p in base.pecas.get(eid, [])
                     if (p["tipo_conexao"] or "").startswith(("LUVA", "REDUÇÃO", "TÊ", "CURVA", "VÁLVULA"))}
            if len(pontas) == 2 and tipos and tipos <= {"LUVA", "REDUÇÃO"}:
                pares.append((pontas[0][0]["id"], pontas[1][0]["id"]))
        self.assertEqual(len(pares), 19)
        for a, b in pares:
            self.assertNotEqual(TP.fisico_do_trecho(self.c, a)["id"], TP.fisico_do_trecho(self.c, b)["id"])

    def test_decisao_com_troca_de_de_e_ignorada(self):
        cfg = {"juncoes": [{"id": "J-X", "tipo": "PASSAGEM", "no": "Zona03_PB08_Rede_NÓ113.1", "decisao": "JUNTAR",
                            "pontas": [{"trecho": TR006, "lado": "ini"}, {"trecho": "Zona03_PB08_Rede_TR003", "lado": "fim"}]}]}
        p = os.path.join(self.raiz, "topologia_troca_de.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        antigo = TP.CONFIG
        try:
            TP.CONFIG = p
            TP._CACHE.clear()
            self.assertEqual(len(TP.fisico_do_trecho(self.c, self.id[TR006])["membros"]), 1)
            pend = [x for x in TP.pendencias(self.c) if x["tipo"] == "DECISAO_DESATUALIZADA"]
            self.assertEqual(len(pend), 1)
            self.assertIn("troca de DE", pend[0]["detalhe"])
        finally:
            TP.CONFIG = antigo
            _limpar_caches()

    def test_sem_arquivo_de_decisoes_cada_linha_e_um_trecho_fisico(self):
        antigo = TP.CONFIG
        try:
            TP.CONFIG = os.path.join(self.raiz, "nao_existe.json")
            TP._CACHE.clear()
            fis = TP.trechos_fisicos(self.c)
            self.assertEqual(len(fis), 1436)
            self.assertTrue(all(len(f["membros"]) == 1 and f["membros"][0]["sentido"] == 1 for f in fis))
            self.assertIn("SEM_ARQUIVO_DE_DECISOES", [p["tipo"] for p in TP.pendencias(self.c)])
        finally:
            TP.CONFIG = antigo
            _limpar_caches()

    # ---------------------------------------------------------------- cadeias reais: sentido −1 e ida e volta
    def test_cadeias_reais_ida_e_volta(self):
        fis = TP.trechos_fisicos(self.c)
        multi = [f for f in fis if len(f["membros"]) > 1]
        com_menos_um = [f for f in multi if any(m["sentido"] == -1 for m in f["membros"])]
        self.assertTrue(com_menos_um)
        for f in multi:
            pos = 0.0
            for m in f["membros"]:
                self.assertAlmostEqual(m["offset_m"], pos, places=3)
                pos += m["extensao_m"]
                ini, fim = TP.para_fisico(f, m["trecho_id"], 0, m["extensao_m"])
                self.assertEqual((ini, fim), (m["offset_m"], round(m["offset_m"] + m["extensao_m"], 3)))
                meio = TP.para_linhas(f, ini + 0.25, fim - 0.25) if m["extensao_m"] > 0.6 else []
                if meio:
                    self.assertEqual(len(meio), 1)
                    self.assertEqual(TP.para_fisico(f, meio[0]["trecho_id"], meio[0]["ini_m"], meio[0]["fim_m"]),
                                     (round(ini + 0.25, 3), round(fim - 0.25, 3)))
            self.assertAlmostEqual(pos, f["extensao_m"], places=2)
            # a cadeia segue a 06.1 do membro mais longo
            longo = min(f["membros"], key=lambda m: (-m["extensao_m"], m["trecho_id"]))
            self.assertEqual(longo["sentido"], 1)

    # ---------------------------------------------------------------- números do diagnóstico (fixados)
    def test_numeros_do_diagnostico(self):
        from collections import Counter
        dz = MG.desenhos(MAPA)
        self.assertEqual((round(dz["GERAL"]["escala"], 4), dz["GERAL"]["n"]), (0.7, 1188))
        self.assertLess(dz["GERAL"]["residuo_m"][2], 0.02)                 # UTM → visão geral: ≤ 1 cm
        self.assertGreater(dz["PB25"]["residuo_m"][2], 30)                 # PB25: desenho vetorial deslocado (pendência)
        pontas = MG.pontas(MAPA)
        self.assertEqual(len(pontas), 2872)
        self.assertEqual(dict(Counter(p["classe"] for p in pontas)), {
            "NO_NO": 2249, "DESLOCADA": 318, "NAO_CHEGA": 130, "DIVISA_ZONA": 72, "PONTA_SEM_NO": 62, "PASSAGEM": 16,
            "LIMITE_MND": 10, "JUNCAO_SEM_NO": 6, "CRUZAMENTO": 4, "PASSA_DO_NO": 2, "LONGE_DO_NO": 2,
            "DESENHO_INCOMPLETO": 1})
        d = [p["d_no_m"] for p in pontas if "d_no_m" in p]
        self.assertEqual((sum(x > 0.5 for x in d), sum(x > 1 for x in d), sum(x > 3 for x in d)), (164, 55, 2))
        self.assertEqual(sorted((p["trecho"], p["lado"]) for p in pontas if p["classe"] == "LONGE_DO_NO"),
                         [("Zona11_PB23_Rede_TR081", "ini"), ("Zona11_PB25_Rede_TR001", "fim")])
        cfg = _cfg()
        self.assertEqual(dict(Counter(j["decisao"] for j in cfg["juncoes"])), {"JUNTAR": 78, "NAO_JUNTAR": 30, "DUVIDA": 2})
        self.assertEqual(dict(Counter(j["tipo"] for j in cfg["juncoes"] if j["decisao"] == "JUNTAR")),
                         {"CRUZAMENTO": 2, "PASSAGEM": 8, "DIVISA_ZONA": 36, "LIMITE_MND": 5, "PONTA_SEM_NO": 27})
        r = TP.resumo(self.c)
        self.assertEqual((r["linhas_06_1"], r["trechos_fisicos"], r["com_mais_de_uma_linha"], r["linhas_em_cadeias"],
                          r["juncoes_aplicadas"]), (1436, 1358, 48, 126, 78))
        fis = TP.trechos_fisicos(self.c)
        ids = Counter(m["trecho_id"] for f in fis for m in f["membros"])
        self.assertEqual((len(ids), set(ids.values())), (1436, {1}))      # toda linha em exatamente um trecho físico
        self.assertAlmostEqual(sum(f["extensao_m"] for f in fis), 110686.03, places=2)
        pend = Counter(p["tipo"] for p in TP.pendencias(self.c))
        self.assertEqual(pend["DECISAO_EM_DUVIDA"], 2)
        self.assertEqual(pend["DECISAO_DESATUALIZADA"] + pend["DECISAO_EM_CONFLITO"] + pend["NO_INEXISTENTE"], 0)

    def test_arquivo_de_decisoes_bate_com_a_ferramenta(self):
        """config/topologia.json é o que ferramentas/topologia gera hoje (fora as decisões revisadas à mão)."""
        import base as B
        import juncoes as J
        novas, _ = J.todas(B.Base(self.db, MAPA))
        chave = lambda j: tuple(sorted((p["trecho"], p["lado"]) for p in j["pontas"]))
        cfg = _cfg()
        arquivo = {chave(j): (j["tipo"], j["decisao"]) for j in cfg["juncoes"] if not j.get("revisao")}
        geradas = {chave(j): (j["tipo"], j["decisao"]) for j in novas}
        self.assertEqual({k: v for k, v in geradas.items() if k in arquivo}, arquivo)
        self.assertEqual(set(geradas) - {chave(j) for j in cfg["juncoes"]}, set())

    # ---------------------------------------------------------------- rota
    def test_rota_api_topologia(self):
        self.assertIs(server.GET["/api/topologia"], server.r_topologia)
        self.assertEqual(server.TELA_GET["/api/topologia"], ("mapa", "iluminado"))
        r = server.r_topologia({}, self.c)
        self.assertEqual(set(r), {"resumo", "cadeias", "cruzamentos", "pendencias"})
        self.assertTrue(all(len(f["membros"]) > 1 for f in r["cadeias"]))
        um = server.r_topologia({"trecho": TR007}, self.c)
        self.assertEqual((um["trecho_id"], um["trecho_fisico"]["extensao_m"]), (self.id[TR007], 295.98))
        self.assertEqual(server.r_topologia({"trecho": self.id[TR006]}, self.c)["trecho_fisico"]["id"],
                         um["trecho_fisico"]["id"])
        des = server.r_topologia({"desenho": "1"}, self.c)
        self.assertIn("GERAL", des["correcoes"])
        self.assertIn([TR007, TR006], [f["membros"] for f in des["fisicos"]])


if __name__ == "__main__":
    unittest.main()
