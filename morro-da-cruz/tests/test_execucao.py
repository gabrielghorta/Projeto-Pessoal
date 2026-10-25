"""Execução reorganizada (23/10/2026): cada nota de serviço na sua aba. A NS do dia e a de serviço de obra em Notas de
serviço; a de topografia e a de cadastro nas abas Topografia e Cadastro de campo, com a página de envio e a do resumo.
Quem envia é a engenharia; as equipes não têm acesso às notas (D-134). Pelo HTTP, sobre a base real, com NS sintéticas.
As rotas e as regras de gravação não mudam: só onde cada coisa fica na tela. A página que cada perfil abre roda o
código da tela no Node, se houver."""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
from base_real import TR006, TR007, BaseReal, b64, pdf_ns  # noqa: E402
from test_ns_dia import ONTEM, BaseDia, grupo, pdf_dia  # noqa: E402

WEB = os.path.join(os.path.dirname(AQUI), "web")


def ler_web(nome):
    with open(os.path.join(WEB, nome), encoding="utf-8") as f:
        return f.read()


def paginas_abertas(permissoes):
    """{tela: [páginas que o perfil usa]} e a que abre primeiro, pelo próprio código da tela (app.js e notas.js)."""
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("sem Node")
    app, notas = ler_web("app.js"), ler_web("notas.js")
    codigo = (re.search(r"const PAGINAS = \{.*?\n\};\n", app, re.S).group(0)
              + re.search(r"const paginasDe = [^\n]*\n", app).group(0)
              + re.search(r"function paginaDe\(.*?\n\}\n", app, re.S).group(0)
              + re.search(r"const PERM_NS = [^\n]*\n", notas).group(0)
              + re.search(r"const podeNs = [^\n]*\n", notas).group(0))
    roteiro = f"""
const PERMS = {json.dumps(permissoes)};
const pode = p => PERMS.includes(p);
const sessionStorage = {{ getItem: () => null }};
{codigo}
const r = {{}};
for (const t of Object.keys(PAGINAS)) r[t] = {{ usa: paginasDe(t).map(p => p[0]), abre: paginaDe(t, null), pedida: paginaDe(t, 'enviar') }};
console.log(JSON.stringify(r));
"""
    saida = subprocess.run([node, "-e", roteiro], capture_output=True, text=True, timeout=30)
    if saida.returncode:
        raise AssertionError(saida.stderr)
    return json.loads(saida.stdout)


class TestNotasDaObra(BaseDia):
    """D-134 (25/10/2026): a nota de serviço, inclusive a do dia, é enviada pela engenharia; as equipes não têm acesso
    às notas; a administração, a engenharia, o RH e o supervisor, sim (o RH e o supervisor só consultam)."""

    def test_o_encarregado_nao_ve_as_notas_e_fica_com_o_lancamento_do_dia(self):
        enc = self.cli("enc3")
        sessao = self.ok(enc.get("/api/sessao"))["usuario"]
        self.assertNotIn("notas", sessao["telas"])
        self.assertEqual(sessao["permissoes"], ["campo"])
        self.assertEqual(paginas_abertas(sessao["permissoes"])["campo"]["usa"], ["fotos", "clima"])   # o Lançamento do dia
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98], obs=["ASSENTAMENTO", None])]
        self.assertEqual(self.enviar("enc3", pdf_dia(g))[0], 403)
        r = self.ok(self.enviar("eng1", pdf_dia(g)))                                         # a engenharia envia pela equipe
        self.assertEqual((r["equipe_id"], self.gravado()), ("Zona03", [("TR006", 0.0, 293.47), ("TR007", 0.0, 2.51)]))
        for rota in ("/api/ns?tipo=EXECUCAO", "/api/ns?tipo=SERVICO", "/api/ns/dia", "/api/ns/fora-de-ordem"):
            self.assertEqual(enc.get(rota)[0], 403, rota)
        self.assertEqual(self.abrir("enc3", f"/api/ns/arquivo?id={r['id']}&qual=croqui")[0], 403)
        # Lançamento do dia › Clima do dia: grava onde a NS do dia grava, só para a equipe dele
        dia = "2026-10-20"
        self.assertEqual(enc.post("/api/clima", {"data": dia, "equipe_id": "Zona04", "MANHA": "SOL", "TARDE": "SOL"})[0], 403)
        self.ok(enc.post("/api/clima", {"data": dia, "equipe_id": "Zona03", "MANHA": "SOL", "TARDE": "CHUVA_FRACA_TENDA"}))
        self.assertEqual([tuple(x) for x in self.c.execute("SELECT turno, condicao FROM clima WHERE equipe_id='Zona03' AND data=? ORDER BY turno", (dia,))],
                         [("MANHA", "SOL"), ("TARDE", "CHUVA_FRACA_TENDA")])

    def test_supervisor_e_rh_consultam_e_a_engenharia_envia(self):
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98], obs=["ASSENTAMENTO", None])]
        r = self.ok(self.enviar("eng1", pdf_dia(g), equipe="Zona04"))
        self.assertEqual(r["equipe_id"], "Zona04")
        for login, telas in (("sup1", ["campo", "diario", "iluminado", "interferencias", "notas"]), ("rh1", ["iluminado", "notas"])):
            u = self.ok(self.cli(login).get("/api/sessao"))["usuario"]
            self.assertEqual(u["telas"], telas, login)
            self.assertNotIn("ns_dia", u["permissoes"])
            self.assertEqual(paginas_abertas(u["permissoes"])["notas"]["usa"], ["dia"], login)          # a NS do dia, para consultar
            self.assertEqual([n["id"] for n in self.ok(self.cli(login).get("/api/ns/dia?equipe=Zona04"))], [r["id"]], login)
            self.assertEqual(self.enviar(login, pdf_dia(g, numero="016"))[0], 403, login)
            self.assertEqual(self.cli(login).get("/api/ns/fora-de-ordem")[0], 403, login)                 # o legado: a engenharia
        eng = self.ok(self.cli("eng1").get("/api/sessao"))["usuario"]
        p = paginas_abertas(eng["permissoes"])
        self.assertEqual(p["notas"]["usa"], ["dia", "servico"])
        self.assertEqual(p["campo"]["usa"], ["apropriacao", "apontamento", "fotos", "clima"])
        self.assertEqual(self.ok(self.cli("eng1").get("/api/ns/fora-de-ordem")), [])

    def test_almoxarifado_nao_envia_nem_ve_as_notas(self):
        """D-132 e D-134: o almoxarife tem `campo` (fotos, soldas e clima), mas não a NS do dia nem acesso às notas."""
        alm = self.cli("almox1")
        sessao = self.ok(alm.get("/api/sessao"))["usuario"]
        self.assertNotIn("notas", sessao["telas"])
        self.assertNotIn("ns_dia", sessao["permissoes"])
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98], obs=["ASSENTAMENTO", None])]
        self.recusa(self.enviar("almox1", pdf_dia(g), equipe="Zona03"), 403, "Enviar e anular a NS do dia")
        self.assertEqual(self.n("notas_servico"), 0)
        r = self.ok(self.enviar("eng1", pdf_dia(g)))
        self.assertEqual(alm.post("/api/ns/dia/anular", {"ns_id": r["id"], "motivo": "x"})[0], 403)
        self.assertEqual(alm.get("/api/ns/dia")[0], 403)
        d = self.ok(alm.get(f"/api/diario?data={ONTEM.isoformat()}"))
        self.assertEqual((d["ns_visivel"], d["ns_dia"]), (False, []))                      # o diário, sem as notas


class TestClimaDoDia(BaseDia):
    """D-131: a NS do dia é a fonte principal do clima. Tocado no envio, substitui o marcado; sem toque, vale o marcado em
    Lançamento do dia › Clima do dia. Com a NS do dia no dia, o Clima do dia só preenche o turno vazio: mudar é da engenharia."""

    def clima(self, data=None):
        return [tuple(x) for x in self.c.execute("SELECT turno, condicao FROM clima WHERE equipe_id='Zona03' AND data=? ORDER BY turno",
                                                 ((data or ONTEM).isoformat(),))]

    def marcar(self, login, manha, tarde, data=None):
        return self.cli(login).post("/api/clima", {"data": (data or ONTEM).isoformat(), "equipe_id": "Zona03", "MANHA": manha, "TARDE": tarde})

    def test_sem_toque_vale_o_marcado_e_com_toque_vale_a_ns(self):
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98], obs=["ASSENTAMENTO", None])]
        self.recusa(self.enviar("eng1", pdf_dia(g), clima=None), 422, "Informe o clima da manhã e da tarde")   # nada marcado
        self.ok(self.marcar("enc3", "SOL", "CHUVA_FRACA_TENDA"))                       # o encarregado marca o clima do dia
        r = self.ok(self.enviar("eng1", pdf_dia(g), clima=None))                       # sem toque: fica o marcado
        self.assertEqual(self.clima(), [("MANHA", "SOL"), ("TARDE", "CHUVA_FRACA_TENDA")])
        self.ok(self.cli("eng1").post("/api/ns/dia/anular", {"ns_id": r["id"], "motivo": "teste do clima"}))
        self.ok(self.enviar("eng1", pdf_dia(g, numero="016"), clima={"MANHA": "SOL", "TARDE": "SOL"}))
        self.assertEqual(self.clima(), [("MANHA", "SOL"), ("TARDE", "SOL")])           # tocado no envio: vale o da NS

    def test_depois_da_ns_o_clima_do_dia_nao_muda_o_dela(self):
        g = [grupo(["NÓ9.1", "CH_VRP-15"], [295.98], obs=["ASSENTAMENTO", None])]
        self.ok(self.enviar("eng1", pdf_dia(g), clima={"MANHA": "SOL", "TARDE": "PARALISADO_CHUVA"}))
        self.recusa(self.marcar("enc3", "SOL", "SOL"), 422, "veio com a NS do dia 015, que é a fonte principal")
        self.recusa(self.marcar("sup1", "SOL", "SOL"), 422, "só a engenharia corrige")
        self.assertEqual(self.clima(), [("MANHA", "SOL"), ("TARDE", "PARALISADO_CHUVA")])
        self.ok(self.marcar("enc3", "SOL", "PARALISADO_CHUVA"))                       # o mesmo: nada muda
        self.ok(self.marcar("eng1", "SOL", "SOL"))                                     # a engenharia corrige
        self.assertEqual(self.clima(), [("MANHA", "SOL"), ("TARDE", "SOL")])
        outro = ONTEM.replace(day=1) if ONTEM.day > 1 else ONTEM.replace(day=2)
        self.ok(self.marcar("enc3", "SOL", "CHUVA_FRACA_TENDA", outro))                # dia sem NS do dia: o Clima do dia vale
        self.assertEqual(self.clima(outro), [("MANHA", "SOL"), ("TARDE", "CHUVA_FRACA_TENDA")])


class TestTopografia(BaseReal):
    LIBERAR_TUDO = False

    def test_perfil_topografia_abre_no_resumo_e_nao_registra(self):
        topo = self.cli("topo1")
        sessao = self.ok(topo.get("/api/sessao"))["usuario"]
        self.assertEqual(sessao["telas"], ["iluminado", "topografia"])
        p = paginas_abertas(sessao["permissoes"])["topografia"]
        self.assertEqual(p, {"usa": ["resumo"], "abre": "resumo", "pedida": "resumo"})   # #topografia/enviar abre o resumo
        self.assertEqual(paginas_abertas(self.ok(self.cli("eng1").get("/api/sessao"))["usuario"]["permissoes"])["topografia"]["abre"], "enviar")
        # o resumo: os indicadores, as listas e as NS de topografia, só para consultar
        self.ok(self.registrar("eng1", "TOPOGRAFIA", pdf_ns()))
        self.assertEqual(topo.get("/api/topografia")[0], 200)
        self.assertEqual(len(self.ok(topo.get("/api/ns?tipo=TOPOGRAFIA"))), 1)
        n = self.n("notas_servico")
        for rota, corpo in (("/api/ns/ler", {"tipo": "TOPOGRAFIA", "pdf_b64": b64(pdf_ns(numero="014"))}),
                            ("/api/ns", {"tipo": "TOPOGRAFIA", "pdf_b64": b64(pdf_ns(numero="014")), "pdf_nome": "nota.pdf"}),
                            ("/api/liberacao", {"trecho_id": self.trecho(TR007), "ini_m": 0, "fim_m": 1, "data": "2026-10-14",
                                                "referencia": "NS 014/2026"})):            # a exceção sem NS
            self.assertEqual(topo.post(rota, corpo)[0], 403, rota)
        self.assertEqual(self.n("notas_servico"), n)


class TestCadastroDeCampo(BaseReal):
    LIBERAR_TUDO = True

    def test_ns_de_cadastro_enviada_no_cadastro_de_campo_grava_igual(self):
        """O envio da página "Enviar NS de cadastro" chama as mesmas rotas, com o mesmo corpo, que a antiga tela Notas
        de serviço: ler, registrar (com as decisões da conferência) e "Aplicar de novo"."""
        self.assentar(TR006, 0, 100, "2026-10-14")
        pdf = pdf_ns(numero="013", bloco="CADASTRO")
        lida = self.ok(self.ler("eng1", "CADASTRO", pdf))
        self.assertTrue(lida["contrato_ok"])
        r = self.ok(self.cli("eng1").post("/api/ns", {"tipo": "CADASTRO", "decisoes": [], "pdf_b64": b64(pdf), "pdf_nome": "ns013.pdf",
                                                      "croqui_b64": None, "croqui_nome": None, "planilha_b64": None,
                                                      "planilha_nome": None, "zona": None, "pb": None}))
        self.assertEqual((r["gravado_m"], r["pendente_m"]), (100.0, 473.97))
        self.assertEqual(self.cadastros(TR006), [(0.0, 100.0)])
        self.assentar(TR006, 100, 150, "2026-10-15")
        self.assertEqual(self.ok(self.cli("eng1").post("/api/ns/aplicar", {"ns_id": r["id"]}))["gravado_m"], 50.0)
        # o perfil Cadastro vê a nota e o que foi feito, abre na página "O que foi feito" e não registra
        cad = self.cli("cad1")
        sessao = self.ok(cad.get("/api/sessao"))["usuario"]
        self.assertEqual(paginas_abertas(sessao["permissoes"])["cadastro_campo"], {"usa": ["feito"], "abre": "feito", "pedida": "feito"})
        self.assertEqual([n["id"] for n in self.ok(cad.get("/api/ns?tipo=CADASTRO"))], [r["id"]])
        self.assertEqual(cad.get("/api/cadastro-campo")[0], 200)
        self.assertEqual(cad.post("/api/ns", {"tipo": "CADASTRO", "pdf_b64": b64(pdf_ns(numero="015", bloco="CADASTRO"))})[0], 403)
        # e a aba Notas de serviço não lista mais a de cadastro para quem só a vê de lá
        self.assertEqual(self.cli("enc3").get("/api/ns?tipo=CADASTRO")[0], 403)


if __name__ == "__main__":
    unittest.main()
