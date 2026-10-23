"""Telas novas (tela inicial, menu lateral e Mapa iluminado): visão geral do mapa REV02 (traçado, zonas e satélite),
planilhas oficiais para baixar do próprio sistema, ligações prediais do BM, camada de liberação topográfica e a
coerência entre o HTML e o JavaScript (toda tela do menu existe, todo elemento usado pelo código está na página)."""
import io
import os
import re
import sys
import unittest
import urllib.error

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
import mapa_geral as MG  # noqa: E402
import planejamento as P  # noqa: E402
import server  # noqa: E402
import servicos as S  # noqa: E402
from test_acesso import BaseHTTP  # noqa: E402

WEB = os.path.join(RAIZ, "web")
MAPA = server._mapa_path()


def ler(nome):
    with open(os.path.join(WEB, nome), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(os.path.exists(MAPA), "mapa REV02 ausente")
class TestVisaoGeral(unittest.TestCase):
    def test_geometria_sai_do_html_sem_coordenada_nova(self):
        g = MG.geometria(MAPA)
        self.assertEqual((len(g["trechos"]), len(g["zonas"]), len(g["quadros"]), len(g["imagens"])), (1436, 11, 25, 25))
        nomes = [t["n"] for t in g["trechos"]]
        self.assertEqual(len(set(nomes)), 1436)
        self.assertTrue(all(re.match(r"^(Zona\d\d|ADUTORA)_PB\d\d_", n) for n in nomes), nomes[:3])
        # tudo dentro da prancha da visão geral
        dentro = lambda x, y: -1 <= x <= g["w"] + 1 and -1 <= y <= g["h"] + 1
        self.assertTrue(all(dentro(p[i], p[i + 1]) for t in g["trechos"] for p in t["p"] for i in range(0, len(p), 2)))
        self.assertTrue(all(dentro(e["x"], e["y"]) for e in g["els"]))
        # MV-11, VTF-12 e VTF-16 continuam sem posição: não aparecem entre os nós desenhados
        desenhados = {n for e in g["els"] for n in e["n"]}
        self.assertFalse([n for n in desenhados if re.search(r"_(MV-11|VTF-12|VTF-16)$", n)])

    def test_mosaico_do_satelite_com_todas_as_pbs_no_lugar(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("sem Pillow: a tela monta as PBs uma a uma")
        im = Image.open(io.BytesIO(MG.mosaico(MAPA))).convert("L")
        g = MG.geometria(MAPA)
        for pb in ("PB01", "PB12", "PB20"):            # a PB20 é girada 90° no REV02 e ficava de fora do mosaico
            q = next(q for q in g["quadros"] if q["id"] == pb)
            cx, cy = (min(q["p"][0::2]) + max(q["p"][0::2])) / 2 * 1.3, (min(q["p"][1::2]) + max(q["p"][1::2])) / 2 * 1.3
            reg = im.crop((round(cx - 40), round(cy - 40), round(cx + 40), round(cy + 40)))
            media = sum(i * n for i, n in enumerate(reg.histogram())) / (reg.width * reg.height)
            self.assertGreater(media, 60, pb)            # o fundo vazio do mosaico é 14

    def test_imagens_das_plantas(self):
        self.assertEqual(MG.imagem_pb(MAPA, "PB01")[:4], b"RIFF")
        self.assertIsNone(MG.imagem_pb(MAPA, "PB99"))


class TestCamadasELigacoes(BaseHTTP):
    def test_liberacao_topografica_total_e_parcial(self):
        t1, t2 = self.q("SELECT id, extensao_m FROM trechos WHERE vigente=1 AND metodologia='VCA' ORDER BY id LIMIT 2")
        S.registrar_etapa_complementar(self.c, t1[0], "LIBERACAO_TOPOGRAFICA", 0, t1[1], "2026-10-15", "eng1", "NS 01")
        S.registrar_etapa_complementar(self.c, t2[0], "LIBERACAO_TOPOGRAFICA", 0, t2[1] / 2, "2026-10-15", "eng1", "NS 02")
        nome = dict(self.q("SELECT id, ponto FROM trechos WHERE id IN (?, ?)", t1[0], t2[0]))
        lib = P.camadas_mapa(self.c)["liberado"]
        self.assertEqual((lib[nome[t1[0]]], lib[nome[t2[0]]], len(lib)), ("TOTAL", "PARCIAL", 2))
        st, est = self.cliente("almox1").get("/api/mapa/estado")
        self.assertEqual((st, est["camadas"]["liberado"].get(nome[t1[0]])), (200, "TOTAL"))

    def test_ligacoes_prediais_vem_do_bm(self):
        eng = self.cliente("eng1")
        self.c.execute("DELETE FROM bm_itens WHERE codigo_caesb='8005508120013'")
        self.c.commit()
        self.assertIsNone(eng.get("/api/resumo")[1]["ligacoes"])          # sem o item no BM: não inventa número
        self.c.execute("""INSERT INTO bm_itens(planilha, item, codigo_caesb, descricao, unidade, quantidade)
                          VALUES ('JUNTADA', '5.10.6', '8005508120013', 'LIGAÇÃO PREDIAL DE ÁGUA EM REDE DE PEAD', 'UN', 11894)""")
        self.c.commit()
        self.assertEqual(eng.get("/api/resumo")[1]["ligacoes"], {"quantidade": 11894, "fonte": "BM, item 5.10.6"})


class TestArquivosHTTP(BaseHTTP):
    def test_planilhas_baixam_do_sistema_so_com_sessao(self):
        anon, almox, alm = self.cliente(), self.cliente("almox1"), self.cliente("eng1")
        self.assertEqual(anon.get("/api/planilhas")[0], 401)
        self.assertEqual(anon.get("/arquivos/bm")[0], 401)
        self.assertEqual((almox.get("/api/planilhas")[0], almox.get("/arquivos/bm")[0]), (403, 403))   # LEV: engenharia e adm
        st, ls = alm.get("/api/planilhas")
        self.assertEqual(st, 200)
        cfg = server._cfg()["arquivos"]
        esperadas = [k for k in server.PLANILHAS if server._arquivo_oficial(k)]
        self.assertEqual([a["chave"] for a in ls], esperadas)
        for a in ls:
            self.assertEqual(a["arquivo"], cfg[a["chave"]])
        if "bm" in esperadas:
            with alm.op.open(self.url + "/arquivos/bm", timeout=20) as r:
                dados, disp = r.read(), r.headers["Content-Disposition"]
            caminho = os.path.join(server.BASE, "planilhas", cfg["bm"])
            with open(caminho, "rb") as f:
                self.assertEqual(dados, f.read())
            self.assertTrue(disp.startswith("attachment;"), disp)
        for rota in ("/arquivos/xyz", "/arquivos/../server.py", "/arquivos/", "/arquivos/%2e%2e%2fserver.py"):
            self.assertEqual(alm.get(rota)[0], 404, rota)

    @unittest.skipUnless(os.path.exists(MAPA), "mapa REV02 ausente")
    def test_mapa_geral_e_imagens_so_com_sessao(self):
        anon, alm = self.cliente(), self.cliente("almox1")
        for rota in ("/api/mapa/geral", "/mapa/geral.webp", "/mapa/pb/PB01.webp"):
            self.assertEqual(anon.get(rota)[0], 401, rota)
        st, g = alm.get("/api/mapa/geral")
        self.assertEqual((st, len(g["trechos"]), len(g["zonas"])), (200, 1436, 11))
        with alm.op.open(self.url + "/mapa/pb/PB01.webp", timeout=20) as r:
            self.assertEqual((r.headers.get_content_type(), r.read(4)), ("image/webp", b"RIFF"))
        try:                                                # o mosaico precisa do Pillow; sem ele, a tela monta as PBs
            with alm.op.open(self.url + "/mapa/geral.webp", timeout=60) as r:
                self.assertEqual(r.read(4), b"RIFF")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
            self.assertIsNone(MG.mosaico(MAPA))
        for rota in ("/mapa/pb/PB99.webp", "/mapa/pb/../../server.py", "/mapa/outra.webp"):
            self.assertEqual(alm.get(rota)[0], 404, rota)


class TestPaginaECodigo(unittest.TestCase):
    """Guarda contra tela quebrada: o menu, as seções e os elementos usados pelo JavaScript precisam existir no HTML."""

    def setUp(self):
        self.html, self.js = ler("index.html"), ler("app.js") + ler("iluminado.js") + ler("planejamento.js") + ler("notas.js") + ler("apropriacao.js")
        self.ids = set(re.findall(r'id="([^"]+)"', self.html))

    def test_cada_item_do_menu_abre_uma_tela_que_existe(self):
        telas = set(re.findall(r"^\s{2}(\w+): \{ titulo:", self.js, re.M))
        self.assertGreaterEqual(len(telas), 14)
        for t in telas:
            self.assertIn("aba-" + t, self.ids, t)
        for t in set(re.findall(r'data-tela="(\w+)"', self.html)):
            self.assertTrue(t in telas or t == "administrativo", t)

    def test_elementos_usados_pelo_codigo_existem(self):
        usados = set(re.findall(r"\$\('#([\w-]+)'\)", self.js))
        criados = set(re.findall(r'id="([\w-]+)"', self.js))      # elementos que o próprio JavaScript desenha
        self.assertFalse(sorted(usados - self.ids - criados))
        # campo achado pelo nome na página inteira: sem ele o início da página parava (contingência do check-in que saiu)
        nomes = set(re.findall(r"\$\('\w*\[name=(\w+)\]'\)", self.js))
        self.assertFalse(sorted(n for n in nomes if f'name="{n}"' not in self.html))

    def test_nomes_globais_sem_repeticao_entre_os_scripts(self):
        """Os scripts da página dividem o mesmo escopo global: um const/let repetido derruba o script que vem depois."""
        vistos = {}
        for arq in ("app.js", "iluminado.js", "planejamento.js", "notas.js", "apropriacao.js"):
            for m in re.finditer(r"^(?:async\s+)?(?:function\s+|const\s+|let\s+)(\w+)", ler(arq), re.M):
                self.assertNotIn(m.group(1), vistos, f"{m.group(1)} declarado em {vistos.get(m.group(1))} e em {arq}")
                vistos[m.group(1)] = arq

    def test_mapas_sem_o_que_travava_de_perto(self):
        """Medido em 22/10/2026: a rede inteira num caminho tracejado só e o filtro CSS no satélite levavam de 0,5 a 1,7 s
        por quadro ao arrastar de perto. O tracejado vai em pedaços (um caminho por trecho, contorno em pedaços) e o
        escurecimento é um véu por cima das fotos."""
        ilu, pln, css = ler("iluminado.js"), ler("planejamento.js"), ler("app.css")
        for js in (ilu, pln):
            self.assertIn("linhasTracejadas(por[s.id]", js)
            self.assertIn("contornosTracejados(g.zonas.map(z => z.p), 'ilu-zl')", js)
            self.assertNotIn("<polyline class=\"ilu-zl\" points=", js)
        self.assertNotIn(".style.filter = FUNDOS", ilu)
        self.assertNotRegex(css, r"#plnSat\s*\{[^}]*filter")
        self.assertIn('class="sat-veu"', ilu)
        # o zoom: um desenho por quadro e nada de variável na raiz do mapa (refazia o estilo de todos os elementos)
        self.assertIn("agendarVista(ctx);", ilu)
        self.assertNotIn("svg().style.setProperty('--k'", ilu + pln)

    def test_gesto_pela_placa_de_video(self):
        """Mapas fluidos (23/10/2026): durante o gesto (arrastar, roda, pinça, botões, focar zona) o SVG só é movido e
        ampliado por transform; o desenho de verdade (viewBox) vem quando o gesto para, e o will-change sai no redesenho
        (ligado depois, o navegador guardava a escala de pintura do gesto e o mapa ficava preto ao aproximar)."""
        ilu = ler("iluminado.js")
        corpo = lambda nome: re.search(r"\nfunction " + nome + r"\(.*?\n\}", ilu, re.S).group(0)
        self.assertIn("(ctx.gesto ? moverVista : desenharVista)(ctx)", corpo("agendarVista"))
        self.assertIn("svg.style.transform = transformVista(", corpo("moverVista"))
        self.assertIn("svg.style.willChange = 'transform'", corpo("moverVista"))
        self.assertIn("svg.style.willChange = ''", corpo("desenharVista"))
        self.assertIn("setTimeout(() => soltarVista(ctx), espera)", corpo("gestoVista"))
        self.assertIn("gestoVista(ctx)", corpo("zoomEm"))
        gestos = corpo("ligarGestos")
        self.assertIn("gestoVista(ctx)", gestos)                       # arrastar
        self.assertIn("soltarVista(ctx);", gestos)                     # soltar o dedo: o desenho na hora
        self.assertNotIn("__GPU", ilu)                                 # o protótipo virou o comportamento normal
        # a animação de irPara roda no compositor e desenha uma vez, no fim
        self.assertIn(".animate(", corpo("irPara"))
        self.assertIn("redesenhar(ctx)", corpo("irPara"))
        # o tamanho vem da caixa, nunca do SVG (transformado durante o gesto)
        for nome in ("pontoDoMapa", "irPara", "ajustarAspecto", "desenharVista", "moverVista"):
            self.assertIn("ctx.caixa().getBoundingClientRect()", corpo(nome), nome)
            self.assertNotIn("svg().getBoundingClientRect()", corpo(nome), nome)

    def test_borda_do_gesto_e_redesenho_leve(self):
        """5.2 e 5.3 dos mapas fluidos: a cópia leve por baixo cobre a borda do gesto; o clique acha o trecho por cálculo
        (sem 1.436 caminhos invisíveis); os nós do Dados da obra só existem onde aparecem; o tracejado vai por zona."""
        ilu, pln, css = ler("iluminado.js"), ler("planejamento.js"), ler("app.css")
        self.assertIn("class=\"vista-fundo\"", ilu)                    # fundo opaco do desenho esconde a cópia parada
        self.assertRegex(css, r"\.vista-fundo \{[^}]*fill: #0B0B0B")
        self.assertRegex(css, r"\.ilu \{[^}]*background: #0B0B0B")     # a mesma cor do fundo da caixa
        self.assertRegex(css, r"\.vista-copia \{[^}]*pointer-events: none")
        for js, ctx in ((ilu, "ILU"), (pln, "PLN")):
            self.assertNotIn("ilu-hit", js)
            self.assertRegex(js, r"const " + ctx + r" = \{[^;]*copia: \(g, u\) =>[^;]*copiaChave: ")
        self.assertIn("trechoPerto(ctx, pontoDoMapa(", ilu)
        self.assertIn("function cliquePln(alvo, ev, i)", pln)
        self.assertNotIn("${nos}</g>", pln)                            # nós sob demanda (desenharNos)
        self.assertIn("function desenharNos(", pln)
        self.assertIn("zonaDoTrecho(t)", re.search(r"function linhasTracejadas\(.*?\n\}", ilu, re.S).group(0))

    def test_trecho_mais_perto_do_toque(self):
        """O clique por cálculo acha o trecho da mesma forma que o antigo caminho de 14 px: até 7 px da tela; com duas
        linhas sobrepostas, a de cima no desenho (índice maior). Roda o código da tela no Node, se houver."""
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("sem Node")
        js = ler("iluminado.js")
        trecho = lambda nome: (re.search(r"\nfunction " + nome + r"\(.*?\n\}\n", js, re.S)
                               or re.search(r"\n(?:const|let) " + nome + r"\b[^\n]*\n", js)).group(0)
        codigo = "".join(trecho(n) for n in ("limites", "GRADE", "gradeTrechos", "distSegmento", "trechoPerto", "TOQUE_PX"))
        roteiro = codigo + """
const GERAL = { trechos: [
  { n: 'A', p: [[0, 0, 100, 0]] },            // horizontal em y = 0
  { n: 'B', p: [[0, 10, 100, 10]] },          // horizontal em y = 10
  { n: 'C', p: [[50, -50, 50, 50]] },         // vertical em x = 50 (cruza A e B)
  { n: 'D', p: [[0, 10, 100, 10]] },          // igual a B (sobreposta, desenhada depois)
] };
const ctx = { vb: [0, -50, 200, 100], caixa: () => ({ getBoundingClientRect: () => ({ width: 200 }) }) };   // 1 unidade = 1 px
const r = [[20, 1], [20, 6], [20, 9], [20, 30], [52, 30], [52, 0.5], [300, 300]].map(p => trechoPerto(ctx, p));
ctx.tocavel = t => t.n !== 'D';
r.push(trechoPerto(ctx, [20, 9]));
console.log(JSON.stringify(r));
"""
        saida = subprocess.run([node, "-e", roteiro], capture_output=True, text=True, timeout=30)
        self.assertEqual(saida.returncode, 0, saida.stderr)
        # perto de A; entre A e B fica B (mais perto); sobre B e D, a de cima (D); longe de tudo (> 7 px) nada;
        # perto de C; no cruzamento, o mais perto (A); fora do mapa nada; D intocável → B
        self.assertEqual(eval(saida.stdout.strip()), [0, 3, 3, -1, 2, 0, -1, 1])

    def test_dados_da_obra_sem_plantas_baixas(self):
        """Pedido do responsável (22/10/2026): no Dados da obra, só as zonas; nem fotos das PBs nem a divisão delas."""
        pln = ler("planejamento.js")
        for proibido in ("htmlSatelite", "ligarSatelite", "detalheSatelite", "/mapa/pb/", "/mapa/geral", "plnQuadros", "g.quadros"):
            self.assertNotIn(proibido, pln)

    def test_ids_unicos_e_scripts_carregados(self):
        todos = re.findall(r'id="([^"]+)"', self.html)
        self.assertEqual(len(todos), len(set(todos)))
        self.assertIn('<script src="/app.js"></script>\n<script src="/iluminado.js"></script>\n<script src="/planejamento.js"></script>\n'
                      '<script src="/notas.js"></script>\n<script src="/apropriacao.js"></script>', self.html)


if __name__ == "__main__":
    unittest.main()
