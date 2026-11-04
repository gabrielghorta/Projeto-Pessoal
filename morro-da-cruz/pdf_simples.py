"""PDF simples, só com a biblioteca padrão e o Pillow (já no projeto): é o que gera o relatório mensal (D-207).

* Página A4 em retrato ou paisagem. Coordenadas em pontos, com a origem no canto de cima à esquerda (y cresce para
  baixo); a conversão para o PDF (origem embaixo) é feita aqui.
* Fontes padrão do PDF (Helvetica, negrito, itálico e negrito itálico, em WinAnsi) condensadas a 82 %, para ficar com a
  cara da Arial Narrow do modelo da Ankara sem embutir fonte. O ✓ é desenhado.
* Imagens pelo Pillow: foto em JPEG reduzido; desenho e logo (PNG com transparência) em RGB comprimido.
* `Fluxo`: parágrafos justificados com destaque amarelo, títulos numerados (com o sumário), tabelas com o cabeçalho
  repetido na quebra de página, figuras e desenhos vetoriais; cabeçalho, rodapé "Página X | N" e borda em toda página.
"""
import hashlib
import io
import zlib

try:
    from PIL import Image, ImageOps
except ImportError:                                     # o site sempre tem o Pillow; sem ele, o PDF sai sem imagens
    Image = ImageOps = None

A4 = (595.28, 841.89)
ESCALA = 82                                             # condensação horizontal (Tz), em %
FONTES = {(False, False): "F1", (True, False): "F2", (False, True): "F3", (True, True): "F4"}
_BASE = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Helvetica-Oblique", "F4": "Helvetica-BoldOblique"}
_TROCA = {"\u2212": "-", "\u2264": "<=", "\u2265": ">=", "\u2192": "->", "\u2190": "<-", "\u00a0": " ", "\u2009": " ",
          "\u2010": "-", "\u2011": "-", "\u2713": "", "\u2714": "", "\u00ad": ""}

# larguras (1/1000 do corpo) dos caracteres 32 a 255 em WinAnsi: as métricas da Helvetica (iguais às da Liberation Sans)
_REG = (
    278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,556,556,556,556,556,556,556,556,556,556,278,
    278,584,584,584,556,1015,667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,667,778,722,667,611,722,
    667,944,667,667,611,278,278,278,469,556,333,556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,556,
    556,333,500,278,556,500,722,500,500,500,334,260,334,584,750,556,0,222,556,333,1000,556,556,333,1000,667,333,
    1000,0,611,0,0,222,222,333,333,350,556,1000,333,1000,500,333,944,0,500,667,278,333,556,556,556,556,260,556,
    333,737,370,556,584,0,737,552,400,549,333,333,333,576,537,333,333,333,365,556,834,834,834,611,667,667,667,667,
    667,667,1000,722,667,667,667,667,278,278,278,278,722,722,778,778,778,778,778,584,778,722,722,722,722,667,667,
    611,556,556,556,556,556,556,889,500,556,556,556,556,278,278,278,278,556,556,556,556,556,556,556,549,611,556,
    556,556,556,500,556,500,
)
_NEG = (
    278,333,474,556,556,889,722,238,333,333,389,584,278,333,278,278,556,556,556,556,556,556,556,556,556,556,333,
    333,584,584,584,611,975,722,722,722,722,667,611,778,722,278,556,722,611,833,722,778,667,778,722,667,611,722,
    667,944,667,667,611,333,278,333,584,556,333,556,611,556,611,556,333,611,611,278,278,556,278,889,611,611,611,
    611,389,556,333,611,556,778,556,556,500,389,280,389,584,750,556,0,278,556,500,1000,556,556,333,1000,667,333,
    1000,0,611,0,0,278,278,500,500,350,556,1000,333,1000,556,333,944,0,500,667,278,333,556,556,556,556,280,556,
    333,737,370,556,584,0,737,552,400,549,333,333,333,576,556,333,333,333,365,556,834,834,834,611,722,722,722,722,
    722,722,1000,722,667,667,667,667,278,278,278,278,722,722,778,778,778,778,778,584,778,722,722,722,722,667,667,
    611,556,556,556,556,556,556,889,556,556,556,556,556,278,278,278,278,611,611,611,611,611,611,611,549,611,611,
    611,611,611,556,611,556,
)


def cor(c):
    """'8B3430', (r, g, b) de 0 a 1 ou de 0 a 255 → (r, g, b) de 0 a 1."""
    if c is None:
        return None
    if isinstance(c, str):
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    if max(c) > 1:
        return tuple(v / 255 for v in c)
    return tuple(c)


def _bytes(s):
    s = "".join(_TROCA.get(ch, ch) for ch in str(s))
    return s.encode("cp1252", errors="replace")


def _esc(b):
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)").replace(b"\r", b"").replace(b"\n", b" ")


def largura(s, tam, negrito=False, escala=ESCALA):
    tab = _NEG if negrito else _REG
    return sum(tab[c - 32] if 32 <= c <= 255 else 500 for c in _bytes(s)) * tam / 1000 * escala / 100


def _n(v):
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


class Pagina:
    def __init__(self, paisagem=False):
        self.paisagem = paisagem
        self.largura, self.altura = (A4[1], A4[0]) if paisagem else A4
        self.ops = []
        self.imagens = set()


class Documento:
    def __init__(self, titulo="", cache_imagens=None):
        self.titulo = titulo
        self.paginas = []
        self.imagens = {}                               # id → (w, h, filtro, dados)
        self._cache = cache_imagens if cache_imagens is not None else {}

    # ---------------------------------------------------------------- páginas
    def nova_pagina(self, paisagem=False, posicao=None):
        p = Pagina(paisagem)
        if posicao is None:
            self.paginas.append(p)
        else:
            self.paginas.insert(posicao, p)
        return p

    # ---------------------------------------------------------------- desenho (y a partir do topo)
    def texto(self, p, x, y, s, tam=10, negrito=False, italico=False, cor_=(0, 0, 0), escala=ESCALA):
        """Texto com a linha de base em y."""
        b = _bytes(s)
        if not b:
            return
        r, g, bl = cor(cor_)
        p.ops.append(f"BT /{FONTES[(bool(negrito), bool(italico))]} {_n(tam)} Tf {escala} Tz {r:.3f} {g:.3f} {bl:.3f} rg "
                     f"1 0 0 1 {_n(x)} {_n(p.altura - y)} Tm (" + _esc(b).decode("latin-1") + ") Tj ET")

    def texto_girado(self, p, x, y, s, tam=8, negrito=False, cor_=(0, 0, 0), angulo=90):
        """Texto girado (90 = de baixo para cima) com a origem em (x, y)."""
        import math
        a = math.radians(angulo)
        c, sn = math.cos(a), math.sin(a)
        r, g, bl = cor(cor_)
        p.ops.append(f"BT /{FONTES[(bool(negrito), False)]} {_n(tam)} Tf {ESCALA} Tz {r:.3f} {g:.3f} {bl:.3f} rg "
                     f"{c:.4f} {sn:.4f} {-sn:.4f} {c:.4f} {_n(x)} {_n(p.altura - y)} Tm ("
                     + _esc(_bytes(s)).decode("latin-1") + ") Tj ET")

    def check(self, p, x, y, tam=9, cor_=(0, 0, 0)):
        """✓ desenhado (não depende da fonte ZapfDingbats no leitor de PDF); y é a linha de base do texto."""
        t = tam * 0.8
        self.poli(p, [(x, y - t * 0.42), (x + t * 0.32, y - t * 0.08), (x + t * 0.85, y - t * 0.85)], cor_, max(0.8, tam * 0.11))

    def ret(self, p, x, y, w, h, fundo=None, borda=None, lw=0.5):
        if fundo is None and borda is None:
            return
        ops = ["q"]
        if fundo is not None:
            ops.append("{:.3f} {:.3f} {:.3f} rg".format(*cor(fundo)))
        if borda is not None:
            ops.append("{:.3f} {:.3f} {:.3f} RG {} w".format(*cor(borda), _n(lw)))
        ops.append(f"{_n(x)} {_n(p.altura - y - h)} {_n(w)} {_n(h)} re " + ("B" if fundo is not None and borda is not None
                                                                              else "f" if fundo is not None else "S"))
        ops.append("Q")
        p.ops.append(" ".join(ops))

    def linha(self, p, x1, y1, x2, y2, cor_=(0, 0, 0), lw=0.5, traco=None):
        self.poli(p, [(x1, y1), (x2, y2)], cor_, lw, traco)

    def poli(self, p, pts, cor_=(0, 0, 0), lw=0.5, traco=None, fechar=False, fundo=None):
        if len(pts) < 2:
            return
        ops = ["q", "1 J 1 j", "{:.3f} {:.3f} {:.3f} RG {} w".format(*cor(cor_), _n(lw))]
        if traco:
            ops.append("[" + " ".join(_n(v) for v in traco) + "] 0 d")
        if fundo is not None:
            ops.append("{:.3f} {:.3f} {:.3f} rg".format(*cor(fundo)))
        ops.append(f"{_n(pts[0][0])} {_n(p.altura - pts[0][1])} m " + " ".join(f"{_n(x)} {_n(p.altura - y)} l" for x, y in pts[1:]))
        ops.append(("b" if fundo is not None else "s") if fechar else "S")
        ops.append("Q")
        p.ops.append(" ".join(ops))

    def tracos(self, p, segmentos, cor_=(0, 0, 0), lw=0.5):
        """Muitos segmentos ((x1, y1, x2, y2), …) com a mesma cor num só bloco (mapas)."""
        if not segmentos:
            return
        corpo = " ".join(f"{_n(round(a, 1))} {_n(round(p.altura - b, 1))} m {_n(round(c, 1))} {_n(round(p.altura - d, 1))} l"
                         for a, b, c, d in segmentos)
        p.ops.append("q 1 J 1 j {:.3f} {:.3f} {:.3f} RG {} w ".format(*cor(cor_), _n(lw)) + corpo + " S Q")

    def circulo(self, p, x, y, r, fundo=None, borda=None, lw=0.5):
        k = 0.5523 * r
        Y = p.altura - y
        caminho = (f"{_n(x + r)} {_n(Y)} m {_n(x + r)} {_n(Y + k)} {_n(x + k)} {_n(Y + r)} {_n(x)} {_n(Y + r)} c "
                   f"{_n(x - k)} {_n(Y + r)} {_n(x - r)} {_n(Y + k)} {_n(x - r)} {_n(Y)} c "
                   f"{_n(x - r)} {_n(Y - k)} {_n(x - k)} {_n(Y - r)} {_n(x)} {_n(Y - r)} c "
                   f"{_n(x + k)} {_n(Y - r)} {_n(x + r)} {_n(Y - k)} {_n(x + r)} {_n(Y)} c")
        ops = ["q"]
        if fundo is not None:
            ops.append("{:.3f} {:.3f} {:.3f} rg".format(*cor(fundo)))
        if borda is not None:
            ops.append("{:.3f} {:.3f} {:.3f} RG {} w".format(*cor(borda), _n(lw)))
        ops.append(caminho + (" B" if fundo is not None and borda is not None else " f" if fundo is not None else " S"))
        ops.append("Q")
        p.ops.append(" ".join(ops))

    def recortar(self, p, x, y, w, h):
        """Daqui até fim_recorte, só aparece o que cai dentro do retângulo."""
        p.ops.append(f"q {_n(x)} {_n(p.altura - y - h)} {_n(w)} {_n(h)} re W n")

    def fim_recorte(self, p):
        p.ops.append("Q")

    # ---------------------------------------------------------------- imagens
    def registrar_imagem(self, dados, foto=True, max_px=1100, qualidade=78):
        """Bytes de uma imagem → (id, largura px, altura px), ou None se o Pillow não abrir. A mesma imagem é
        guardada uma vez (e reaproveitada entre documentos pelo cache)."""
        if Image is None or not dados:
            return None
        chave = hashlib.sha1(dados).hexdigest() + f"|{int(foto)}|{max_px}"
        if chave not in self._cache:
            try:
                with Image.open(io.BytesIO(dados)) as im:
                    im = ImageOps.exif_transpose(im)
                    if im.mode in ("RGBA", "LA", "P"):
                        im = im.convert("RGBA")
                        fundo = Image.new("RGBA", im.size, (255, 255, 255, 255))
                        fundo.alpha_composite(im)
                        im = fundo
                    im = im.convert("RGB")
                    im.thumbnail((max_px, max_px))
                    if foto:
                        buf = io.BytesIO()
                        im.save(buf, "JPEG", quality=qualidade, optimize=True)
                        self._cache[chave] = (im.width, im.height, "DCTDecode", buf.getvalue())
                    else:
                        self._cache[chave] = (im.width, im.height, "FlateDecode", zlib.compress(im.tobytes(), 9))
            except (OSError, ValueError):
                self._cache[chave] = None
        reg = self._cache[chave]
        if reg is None:
            return None
        iid = "Im" + hashlib.sha1(chave.encode()).hexdigest()[:10]
        self.imagens[iid] = reg
        return iid, reg[0], reg[1]

    def imagem(self, p, iid, x, y, w, h):
        p.imagens.add(iid)
        p.ops.append(f"q {_n(w)} 0 0 {_n(h)} {_n(x)} {_n(p.altura - y - h)} cm /{iid} Do Q")

    # ---------------------------------------------------------------- arquivo
    def salvar(self):
        objs = []

        def novo(corpo):
            objs.append(corpo)
            return len(objs)

        fontes = {k: novo(f"<< /Type /Font /Subtype /Type1 /BaseFont /{v} /Encoding /WinAnsiEncoding >>".encode())
                  for k, v in _BASE.items()}
        imgs = {}
        for iid, (w, h, filtro, dados) in self.imagens.items():
            imgs[iid] = novo((f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB "
                              f"/BitsPerComponent 8 /Filter /{filtro} /Length {len(dados)} >>\nstream\n").encode()
                             + dados + b"\nendstream")
        raiz_paginas = len(objs) + 1
        objs.append(None)                                # a árvore de páginas, preenchida depois
        filhos = []
        rfont = " ".join(f"/{k} {v} 0 R" for k, v in fontes.items())
        for p in self.paginas:
            corpo = zlib.compress("\n".join(p.ops).encode("latin-1"), 6)
            cid = novo(f"<< /Length {len(corpo)} /Filter /FlateDecode >>\nstream\n".encode() + corpo + b"\nendstream")
            rimg = " ".join(f"/{i} {imgs[i]} 0 R" for i in sorted(p.imagens) if i in imgs)
            filhos.append(novo((f"<< /Type /Page /Parent {raiz_paginas} 0 R /MediaBox [0 0 {_n(p.largura)} {_n(p.altura)}] "
                                f"/Resources << /Font << {rfont} >> /XObject << {rimg} >> >> /Contents {cid} 0 R >>").encode()))
        objs[raiz_paginas - 1] = (f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in filhos)}] /Count {len(filhos)} >>").encode()
        cat = novo(f"<< /Type /Catalog /Pages {raiz_paginas} 0 R >>".encode())
        titulo = b"\xfe\xff" + str(self.titulo).encode("utf-16-be")        # texto do Info: UTF-16 (não WinAnsi)
        info = novo(b"<< /Title <" + titulo.hex().upper().encode() + b"> /Producer (Morro da Cruz - relatorio mensal) >>")
        out = io.BytesIO()
        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        pos = []
        for i, corpo in enumerate(objs, 1):
            pos.append(out.tell())
            out.write(f"{i} 0 obj\n".encode() + corpo + b"\nendobj\n")
        xref = out.tell()
        out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
        for o in pos:
            out.write(f"{o:010d} 00000 n \n".encode())
        out.write(f"trailer\n<< /Size {len(objs) + 1} /Root {cat} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        return out.getvalue()


# ==================================================================== fluxo (parágrafos, títulos, tabelas, figuras)
def quebrar(runs, largura_max, tam):
    """runs [(texto, estilo)] → linhas [(palavra, estilo, espaço depois, largura)] que cabem em largura_max."""
    return Fluxo.linhas_de(None, runs, largura_max, tam)


def linhas_texto(texto, largura_max, tam, negrito=False):
    """O texto quebrado em linhas (strings) que cabem em largura_max."""
    return [" ".join(a for a, _, _, _ in ln) for ln in quebrar([(texto, {"negrito": negrito})], largura_max, tam)]


class Fluxo:
    """Põe os blocos um depois do outro, quebrando a página quando falta espaço.

    `moldura(doc, pagina)` desenha o que se repete (borda, cabeçalho) e devolve a área útil (x0, y0, x1, y1);
    `rodape(doc, pagina, numero, total)` é desenhado no fim, quando o total de páginas é conhecido."""

    def __init__(self, doc, moldura, rodape=None, cor_titulo=(0, 0, 0), primeira_pagina=1):
        self.doc, self.moldura, self.rodape = doc, moldura, rodape
        self.cor_titulo = cor_titulo
        self.paisagem = False
        self.p = None
        self.titulos = []                               # (nível, número, texto, página)
        self._cont = [0, 0, 0]
        self.primeira = primeira_pagina                 # número da 1ª página do fluxo (capa e sumário vêm antes)

    # ---------------------------------------------------------------- páginas
    def nova_pagina(self, paisagem=None):
        if paisagem is not None:
            self.paisagem = paisagem
        self.p = self.doc.nova_pagina(self.paisagem)
        self.x0, self.y0, self.x1, self.y1 = self.moldura(self.doc, self.p)
        self.y = self.y0
        return self.p

    def _garante(self, h):
        if self.p is None or self.y + h > self.y1:
            self.nova_pagina()
            return True
        return False

    @property
    def w(self):
        return self.x1 - self.x0

    def numero_pagina(self):
        return self.doc.paginas.index(self.p) + 1

    def espaco(self, h):
        if self.p is not None:
            self.y = min(self.y + h, self.y1)

    # ---------------------------------------------------------------- texto
    @staticmethod
    def _palavras(runs):
        """runs: [(texto, estilo)] → [(palavra, estilo, espaço depois)]."""
        out = []
        for txt, est in runs:
            partes = str(txt).replace("\n", " ").split(" ")
            for i, pal in enumerate(partes):
                if pal == "" and i not in (0, len(partes) - 1):
                    continue
                if pal:
                    out.append([pal, est or {}, False])
                if i < len(partes) - 1 and out:
                    out[-1][2] = True
        return out

    def linhas_de(self, runs, largura_max, tam):
        pal = Fluxo._palavras(runs)
        linhas, cur, w = [], [], 0.0
        esp = largura(" ", tam)
        for p_, est, sp in pal:
            lw = largura(p_, tam, est.get("negrito"))
            extra = (esp if cur and cur[-1][2] else 0)
            if cur and w + extra + lw > largura_max:
                linhas.append(cur)
                cur, w = [], 0.0
                extra = 0
            if not cur and lw > largura_max:             # palavra maior que a linha: corta
                while largura(p_, tam, est.get("negrito")) > largura_max and len(p_) > 1:
                    k = len(p_)
                    while k > 1 and largura(p_[:k], tam, est.get("negrito")) > largura_max:
                        k -= 1
                    linhas.append([(p_[:k], est, False, largura(p_[:k], tam, est.get("negrito")))])
                    p_ = p_[k:]
                lw = largura(p_, tam, est.get("negrito"))
            cur.append((p_, est, sp, lw))
            w += extra + lw
        if cur:
            linhas.append(cur)
        return linhas

    def _desenha_linha(self, p, x, y, linha, larg, tam, alin, ultima, cor_padrao):
        esp = largura(" ", tam)
        natural = sum(l for _, _, _, l in linha) + sum(esp for i, (_, _, sp, _) in enumerate(linha) if sp and i < len(linha) - 1)
        vaos = sum(1 for i, (_, _, sp, _) in enumerate(linha) if sp and i < len(linha) - 1)
        gap = esp
        if alin == "J" and not ultima and vaos:
            gap = esp + (larg - natural) / vaos
        elif alin == "C":
            x += (larg - natural) / 2
        elif alin == "D":
            x += larg - natural
        for i, (pal, est, sp, lw) in enumerate(linha):
            fim_esp = gap if sp and i < len(linha) - 1 else 0
            if est.get("fundo"):
                self.doc.ret(p, x - 0.5, y - tam * 0.82, lw + fim_esp + (0.5 if fim_esp else 1), tam * 1.08, fundo=est["fundo"])
            self.doc.texto(p, x, y, pal + (" " if fim_esp else ""), tam, est.get("negrito"), est.get("italico"),
                           est.get("cor") or cor_padrao)
            x += lw + fim_esp

    def paragrafo(self, runs, tam=10, alin="J", antes=0, depois=5, recuo=0, marcador=False, entrelinha=1.28,
                  cor_=(0, 0, 0), junto=False):
        if isinstance(runs, str):
            runs = [(runs, {})]
        rec = recuo + (13 if marcador else 0)
        linhas = self.linhas_de(runs, self.w - rec, tam)
        lh = tam * entrelinha
        if self.p is not None and self.y > self.y0:
            self.y += antes
        if junto:
            self._garante(len(linhas) * lh + 2)
        for i, ln in enumerate(linhas):
            self._garante(lh)
            y = self.y + tam * 0.95
            if marcador and i == 0:
                self.doc.check(self.p, self.x0 + recuo + 1, y, tam * 0.85, cor_)
            self._desenha_linha(self.p, self.x0 + rec, y, ln, self.w - rec, tam, alin, i == len(linhas) - 1, cor_)
            self.y += lh
        self.y += depois

    def titulo(self, nivel, texto, nova_pagina=False, paisagem=None, numerar=True, sumario=True):
        if nova_pagina or paisagem is not None and paisagem != self.paisagem or self.p is None:
            self.nova_pagina(paisagem)
        if numerar:
            self._cont[nivel - 1] += 1
            for k in range(nivel, 3):
                self._cont[k] = 0
            num = ".".join(str(v) for v in self._cont[:nivel])
        else:
            num = ""
        tam = {1: 12, 2: 11, 3: 10.5}[nivel]
        self._garante(tam * 1.3 + 46)                    # o título não fica sozinho no pé da página
        if self.y > self.y0:
            self.y += 9 if nivel == 1 else 6
        txt = texto.upper() if nivel == 1 else texto
        y = self.y + tam
        x = self.x0
        if num:
            self.doc.texto(self.p, x, y, num, tam, True, nivel < 3, self.cor_titulo)
            x += max(largura(num + "  ", tam, True), 20 if nivel == 1 else 26)
        for ln in self.linhas_de([(txt, {"negrito": True})], self.x1 - x, tam):
            self._desenha_linha(self.p, x, y, [(a, {"negrito": True, "italico": nivel < 3, "cor": self.cor_titulo}, b, c)
                                               for a, _, b, c in ln], self.x1 - x, tam, "E", True, self.cor_titulo)
            y += tam * 1.25
        self.y = y - tam + tam * 0.45 + 4
        if sumario:
            self.titulos.append((nivel, num, texto, self.numero_pagina()))
        return num

    # ---------------------------------------------------------------- tabelas
    def tabela(self, larguras, linhas, cab=1, tam=8, cor_cab="173B59", cor_borda="C8D0D6", alin=None, total=False,
               pad=3, depois=4, cor_total="F2F2F2"):
        """linhas: listas de células; célula = texto, ou dict {t, fundo, negrito, cor, alin ('E','C','D'), span}.
        Larguras em fração do espaço útil (soma 1) ou em pontos (soma > 1)."""
        soma = sum(larguras)
        lw = [v / soma * self.w for v in larguras] if soma <= 1.0001 else list(larguras)
        alin = alin or ["E"] * len(lw)

        def celula(c):
            return c if isinstance(c, dict) else {"t": "" if c is None else str(c)}

        def altura(linha, cabe):
            hmax, desenho = 0.0, []
            k = 0
            for c in linha:
                c = celula(c)
                span = c.get("span", 1)
                w = sum(lw[k:k + span])
                t_ = c.get("tam", tam)
                runs = c["t"] if isinstance(c["t"], list) else [(c["t"], {"negrito": c.get("negrito") or cabe,
                                                                         "cor": c.get("cor") or ("FFFFFF" if cabe else None),
                                                                         "fundo": c.get("destaque")})]
                ls = self.linhas_de(runs, w - 2 * pad, t_) or [[]]
                h = len(ls) * t_ * 1.2 + 2 * pad
                hmax = max(hmax, h)
                desenho.append((k, span, w, c, ls, t_))
                k += span
            return hmax, desenho

        def desenha(linha, cabe, ultima):
            h, desenho = altura(linha, cabe)
            if self._garante(h) and not cabe and cab:
                for lc in linhas[:cab]:
                    desenha(lc, True, False)
            x = self.x0
            for k, _span, w, c, ls, t_ in desenho:
                x = self.x0 + sum(lw[:k])
                fundo = c.get("fundo") or (cor_cab if cabe else (cor_total if total and ultima else None))
                self.doc.ret(self.p, x, self.y, w, h, fundo=fundo, borda=cor_borda, lw=0.4)
                al = c.get("alin") or ("C" if cabe else alin[k] if k < len(alin) else "E")
                yy = self.y + pad + t_ * 0.95 + (h - 2 * pad - len(ls) * t_ * 1.2) / 2
                for ln in ls:
                    if ln:
                        self._desenha_linha(self.p, x + pad, yy, [(a, dict(e, negrito=e.get("negrito") or (total and ultima)), b, l)
                                                                  for a, e, b, l in ln], w - 2 * pad, t_, al, True,
                                            "FFFFFF" if cabe else "000000")
                    yy += t_ * 1.2
            self.y += h

        if self.p is None:
            self.nova_pagina()
        # cabeçalho + 1ª linha juntos
        if len(linhas) > cab:
            self._garante(altura(linhas[0], True)[0] + altura(linhas[cab], False)[0])
        for i, ln in enumerate(linhas):
            desenha(ln, i < cab, i == len(linhas) - 1)
        self.y += depois

    # ---------------------------------------------------------------- figuras e desenhos
    def figura(self, w, h, desenhar, legenda=None, tam_leg=8, cor_leg="595959"):
        """desenhar(doc, pagina, x, y, w, h); a figura fica centrada, com a legenda embaixo, na mesma página."""
        leg = self.linhas_de([(legenda, {"italico": True, "cor": cor_leg})], self.w, tam_leg) if legenda else []
        total = h + 6 + len(leg) * tam_leg * 1.25 + 6
        self._garante(total)
        if self.y + total > self.y1:                     # maior que a página: encolhe
            k = (self.y1 - self.y - 6 - len(leg) * tam_leg * 1.25 - 6) / h
            w, h = w * k, h * k
        x = self.x0 + (self.w - w) / 2
        desenhar(self.doc, self.p, x, self.y + 3, w, h)
        self.y += h + 6
        for ln in leg:
            self._desenha_linha(self.p, self.x0, self.y + tam_leg, ln, self.w, tam_leg, "C", True, cor_leg)
            self.y += tam_leg * 1.25
        self.y += 6

    def imagem(self, dados, w_max, h_max, legenda=None, foto=True):
        reg = self.doc.registrar_imagem(dados, foto=foto)
        if not reg:
            self.paragrafo([("(imagem indisponível)", {"italico": True})], tam=8, alin="C")
            return
        iid, pw, ph = reg
        k = min(w_max / pw, h_max / ph)
        self.figura(pw * k, ph * k, lambda d, p, x, y, w, h: d.imagem(p, iid, x, y, w, h), legenda)

    # ---------------------------------------------------------------- fim
    def fechar(self):
        total = len(self.doc.paginas)
        if self.rodape:
            for i, p in enumerate(self.doc.paginas, 1):
                self.rodape(self.doc, p, i, total)
