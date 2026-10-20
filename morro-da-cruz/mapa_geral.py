"""Visão geral do mapa REV02 para o Mapa Iluminado: satélite, zonas oficiais e traçado dos trechos.

Tudo sai do próprio HTML PLANTAS_..._REV02_EQUIPES (bloco `const DADOS = {...}`, chave `visaoGeral`), sem coordenada
nova: as zonas, os quadros das plantas, as imagens das 25 PBs e as polilinhas dos 1.436 trechos já vêm no espaço da
visão geral (largura × altura em unidades da prancha). O arquivo não é alterado; o resultado fica em memória e é
refeito quando o HTML muda (data de modificação).

* geometria(caminho)  → dicionário enxuto para a tela (zonas, nomes, quadros, trechos por nome visível, imagens),
                        com as pontas dos trechos encaixadas no centro do nó (correcoes)
* mosaico(caminho)    → as 25 imagens montadas numa só (webp), se o Pillow estiver instalado; senão None e a tela
                        monta as imagens uma a uma (imagem_pb)
* imagem_pb(caminho, pb) → bytes webp da imagem de uma PB, como está no HTML
* pontas(caminho)     → cada ponta de trecho medida em metros contra o nó da 06.1, com classe e ação de desenho
* correcoes(caminho)  → por desenho (GERAL e PBxx), as pontas a encaixar no nó: [trecho, parte, ponta, cortar, x, y]

Pontas: a lei da obra é que todo trecho termina numa conexão, então o desenho tem de terminar no centro do nó. A ponta
de cada polilinha está sobre a UTM da 06.1 (colunas BS..BV, até 2,5 cm), mas a 06.1 ligou ponta a nó com folga de até
~1,6 m: a linha pode parar antes do nó (NAO_CHEGA), ao lado dele (DESLOCADA) ou passar um pouco dele (PASSA_DO_NO).
Essas pontas são encaixadas no nó até TOL_ENCAIXE_M; acima disso viram pendência de desenho, sem encaixe forçado.
As pontas que, pelas decisões de config/topologia.json, passam pelo nó sem se ligar a ele (cruzamento com semicírculo,
tubo ao lado do nó) não são puxadas: o arco do pulo fica como está.
"""
import base64
import io
import json
import math
import os
import re
import threading

import topologia

_TRAVA = threading.Lock()
_CACHE = {}

TOL_NO_M = 0.10            # ponta a até 10 cm do centro do nó: já está no nó (arredondamento do desenho e das UTM)
TOL_ENCAIXE_M = 2.0        # a 06.1 liga ponta a nó até 1,59 m (2.721 pontas): acima de 2 m não encaixa, é pendência
TOL_PONTA_UTM_M = 0.5      # a ponta do desenho fica sobre a UTM da 06.1; acima disso o desenho não chega ao fim do trecho
ALCANCE_ARCO_M = 3.0       # trecho perto da ponta onde se procura o arco do pulo
SEM_NO = {"DIVISA DE ZONA": "DIVISA_ZONA", "LIMITE DA TRAVESSIA MND": "LIMITE_MND",
          "PONTA SEM NÓ NA TABELA": "PONTA_SEM_NO", "JUNÇÃO SEM NÓ NA TABELA": "JUNCAO_SEM_NO"}


def _ler(caminho):
    chave = (os.path.abspath(caminho), os.path.getmtime(caminho))
    with _TRAVA:
        if _CACHE.get("chave") != chave:
            with open(caminho, encoding="utf-8") as f:
                html = f.read()
            i = html.find("const DADOS")
            if i < 0:
                raise ValueError("O HTML do mapa não tem o bloco DADOS.")
            j = html.find("=", i) + 1
            dados, _ = json.JSONDecoder().raw_decode(html[j:].lstrip())
            imagens = dict(re.findall(r'"(PB\d+)":\s*"data:image/webp;base64,([A-Za-z0-9+/=]+)"', html))
            dados = {"visaoGeral": dados.get("visaoGeral"), "trechos": dados.get("trechos"),   # o resto (peças) fica no HTML
                     "els": [{"noms": e.get("noms") or [], "E": e.get("E"), "N": e.get("N")} for e in dados.get("els") or []],
                     "pbs": [{"id": p["id"], "tr": [{"i": t["i"], "p": t["p"]} for t in p.get("tr") or []],
                              "el": p.get("el") or []} for p in dados.get("pbs") or []]}
            _CACHE.clear()
            _CACHE.update(chave=chave, dados=dados, imagens=imagens)
        return _CACHE


def _r(v):
    return round(float(v), 1)


# ---------------------------------------------------------------- coordenadas: UTM ↔ desenho
def _resolver3(m, b):
    a = [linha[:] + [b[k]] for k, linha in enumerate(m)]
    for c in range(3):
        p = max(range(c, 3), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-12:
            return None
        a[c], a[p] = a[p], a[c]
        for r in range(3):
            if r != c:
                f = a[r][c] / a[c][c]
                for k in range(c, 4):
                    a[r][k] -= f * a[c][k]
    return [a[k][3] / a[k][k] for k in range(3)]


def ajuste_afim(pares):
    """(E, N) → (x, y) por mínimos quadrados: [A, B, C, D, E, F] com x = A·E + B·N + C e y = D·E + E·N + F.
    None se os pontos não bastam (menos de 3 ou alinhados)."""
    if len(pares) < 3:
        return None
    e0 = sum(u[0] for u, _ in pares) / len(pares)
    n0 = sum(u[1] for u, _ in pares) / len(pares)
    m = [[0.0] * 3 for _ in range(3)]
    bx, by = [0.0] * 3, [0.0] * 3
    for (e, n), (x, y) in pares:
        r = (e - e0, n - n0, 1.0)
        for a in range(3):
            bx[a] += r[a] * x
            by[a] += r[a] * y
            for b in range(3):
                m[a][b] += r[a] * r[b]
    cx, cy = _resolver3(m, bx), _resolver3(m, by)
    if cx is None or cy is None or abs(cx[0] * cy[1] - cx[1] * cy[0]) < 1e-12:
        return None
    return [cx[0], cx[1], cx[2] - cx[0] * e0 - cx[1] * n0, cy[0], cy[1], cy[2] - cy[0] * e0 - cy[1] * n0]


def aplicar(t, x, y):
    return t[0] * x + t[1] * y + t[2], t[3] * x + t[4] * y + t[5]


def inversa(t):
    det = t[0] * t[4] - t[1] * t[3]
    a, b, d, e = t[4] / det, -t[1] / det, -t[3] / det, t[0] / det
    return [a, b, -(a * t[2] + b * t[5]), d, e, -(d * t[2] + e * t[5])]


def escala(t):
    """unidades do desenho por metro"""
    return math.sqrt(abs(t[0] * t[4] - t[1] * t[3]))


def desenhos(caminho):
    """Visão geral e pranchas: {id: {"tr": {i: partes}, "el": {j: (x, y)}, "t": UTM→desenho, "inv": desenho→UTM,
    "escala": unidades/m, "residuo_m": [mediana, p95, máx], "n": nós usados}}. A transformação de cada desenho é
    ajustada nos nós que têm UTM e posição nele; a prancha com poucos nós usa a da visão geral composta com a matriz
    da imagem dela."""
    c = _ler(caminho)
    if "desenhos" in c:
        return c["desenhos"]
    d = c["dados"]
    els = d["els"]
    vg = d["visaoGeral"]

    def montar(ident, trs, el):
        pares = [((els[j]["E"], els[j]["N"]), (x, y)) for j, x, y in el if j < len(els) and els[j].get("E") is not None]
        t = ajuste_afim(pares) if len(pares) >= 4 else None
        return {"id": ident, "tr": {tr["i"]: tr["p"] for tr in trs}, "el": {j: (x, y) for j, x, y in el},
                "t": t, "pares": pares}

    out = {"GERAL": montar("GERAL", vg.get("tr") or [], vg.get("el") or [])}
    for pb in d.get("pbs") or []:
        out[pb["id"]] = montar(pb["id"], pb["tr"], pb["el"])
    tg = out["GERAL"]["t"]
    for im in vg.get("images") or []:                  # prancha sem nós suficientes: visão geral ∘ inversa da imagem
        dz = out.get(im["id"])
        if dz is not None and dz["t"] is None and tg is not None:
            a, b, cc, dd, e, f = im["matrix"]           # SVG: x = a·u + c·v + e; y = b·u + d·v + f
            dz["t"] = _compor(inversa([a, cc, e, b, dd, f]), tg)
    for dz in out.values():
        if dz["t"] is None:
            continue
        dz["inv"], dz["escala"] = inversa(dz["t"]), escala(dz["t"])
        res = sorted(math.dist(aplicar(dz["t"], *u), xy) / dz["escala"] for u, xy in dz["pares"])
        dz["n"] = len(res)
        dz["residuo_m"] = [round(res[len(res) // 2], 4), round(res[int(0.95 * (len(res) - 1))], 4), round(res[-1], 4)] if res else None
        del dz["pares"]
    c["desenhos"] = {k: v for k, v in out.items() if v["t"] is not None}
    return c["desenhos"]


def _compor(t2, t1):
    """t2 ∘ t1"""
    return [t2[0] * t1[0] + t2[1] * t1[3], t2[0] * t1[1] + t2[1] * t1[4], t2[0] * t1[2] + t2[1] * t1[5] + t2[2],
            t2[3] * t1[0] + t2[4] * t1[3], t2[3] * t1[1] + t2[4] * t1[4], t2[3] * t1[2] + t2[4] * t1[5] + t2[5]]


# ---------------------------------------------------------------- pontas dos trechos
def _pontos(parte):
    return [(parte[k], parte[k + 1]) for k in range(0, len(parte) - 1, 2)]


def _casar_ponta(partes, alvo):
    """Ponta da polilinha (várias partes, qualquer sentido) mais perto do alvo: (parte, 0 = começo | 1 = fim, distância)."""
    melhor = None
    for k, p in enumerate(partes):
        for qual, q in ((0, p[0]), (1, p[-1])):
            dd = math.dist(q, alvo)
            if melhor is None or dd < melhor[2]:
                melhor = (k, qual, dd)
    return melhor


def _ponto_a(p, s):
    """ponto a s metros do começo da polilinha p (ou o último)"""
    acum = 0.0
    for a, b in zip(p, p[1:]):
        L = math.dist(a, b)
        if L > 0 and acum + L >= s:
            f = (s - acum) / L
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        acum += L
    return p[-1]


def arco(p, alcance=ALCANCE_ARCO_M, giro_min=3.0):
    """Curva desenhada perto da ponta (p começa na ponta): vértices que giram ≥ giro_min graus nos primeiros
    `alcance` metros, soma dos giros (graus) e giro líquido. O semicírculo do pulo é desenhado com muitos vértices."""
    n, soma, liq, acum = 0, 0.0, 0.0, 0.0
    for k in range(1, len(p) - 1):
        acum += math.dist(p[k - 1], p[k])
        if acum > alcance:
            break
        a = (p[k][0] - p[k - 1][0], p[k][1] - p[k - 1][1])
        b = (p[k + 1][0] - p[k][0], p[k + 1][1] - p[k][1])
        if math.hypot(*a) < 1e-9 or math.hypot(*b) < 1e-9:
            continue
        g = math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))
        if abs(g) >= giro_min:
            n += 1
            soma += abs(g)
        liq += g
    return {"vertices": n, "giro": round(soma), "liquido": round(liq), "tem": n >= 4 and soma >= 60}


def medir(dz, trecho, i, lado, no_utm):
    """Uma ponta de trecho num desenho, em metros. None se o trecho não está nesse desenho."""
    partes = dz["tr"].get(i)
    if not partes:
        return None
    U = trecho["A"] if lado == "ini" else trecho["B"]
    pu = [[aplicar(dz["inv"], x, y) for x, y in _pontos(p)] for p in partes]
    k, qual, d_utm = _casar_ponta(pu, U)
    p = pu[k] if qual == 0 else pu[k][::-1]
    L = sum(math.dist(a, b) for a, b in zip(p, p[1:]))
    out = {"parte": k, "ponta": qual, "xy": tuple(partes[k][0:2]) if qual == 0 else tuple(partes[k][-2:]),
           "utm": p[0], "d_utm_m": d_utm, "arco": arco(p), "comprimento_m": L}
    if no_utm is not None:
        q = _ponto_a(p, min(2.0, L / 2))
        u = (p[0][0] - q[0], p[0][1] - q[1])           # direção da linha saindo pela ponta
        nu = math.hypot(*u) or 1.0
        u = (u[0] / nu, u[1] / nu)
        v = (no_utm[0] - p[0][0], no_utm[1] - p[0][1])
        out.update(d_no_m=math.hypot(*v), ao_longo_m=v[0] * u[0] + v[1] * u[1], lateral_m=abs(v[0] * u[1] - v[1] * u[0]))
    return out


def classificar(no, m, nao_conexao=None):
    """Classe e ação de desenho de uma ponta medida (m = medir(...)), dado o nome do nó na 06.1."""
    if no in SEM_NO:
        if m is not None and m["d_utm_m"] > TOL_PONTA_UTM_M:
            return "DESENHO_INCOMPLETO", "PENDENCIA_DESENHO"
        return SEM_NO[no], "MANTER_SEM_NO"
    if m is None:
        return "SEM_DESENHO", "PENDENCIA_DESENHO"
    if "d_no_m" not in m:
        return "NO_SEM_POSICAO", "PENDENCIA_DESENHO"
    if nao_conexao:
        return nao_conexao, "NAO_ENCAIXAR"
    d = m["d_no_m"]
    if d <= TOL_NO_M:
        return "NO_NO", "NADA"
    if d > TOL_ENCAIXE_M or m["d_utm_m"] > TOL_PONTA_UTM_M:
        return "LONGE_DO_NO", "PENDENCIA_DESENHO"
    if m["ao_longo_m"] >= 0.8 * d:
        return "NAO_CHEGA", "ESTENDER_ATE_NO"
    if m["ao_longo_m"] <= -0.8 * d:
        return "PASSA_DO_NO", "APARAR"
    return "DESLOCADA", "ESTENDER_ATE_NO"


def _derivados(caminho):
    """pontas e correções, refeitos quando o HTML ou o arquivo de decisões mudam"""
    c = _ler(caminho)
    chave = topologia.chave_config()
    if c.get("derivados_chave") != chave or "pontas" not in c:
        c.pop("geometria", None)
        c["pontas"], c["correcoes"] = _calcular(c["dados"], desenhos(caminho), topologia.pontas_nao_conexao())
        c["derivados_chave"] = chave
    return c


def pontas(caminho):
    """Cada ponta de trecho na visão geral (em metros): [{"trecho", "i", "lado", "no", "classe", "acao", "d_no_m",
    "d_utm_m", "ao_longo_m", "lateral_m", "arco"}], na ordem dos trechos do HTML."""
    return _derivados(caminho)["pontas"]


def correcoes(caminho):
    """{desenho: [[trecho (índice em DADOS.trechos), parte, ponta (0 começo | 1 fim), cortar, x, y], ...]}:
    em cada desenho, tira `cortar` vértices daquela ponta e põe o centro do nó (x, y) no lugar."""
    return _derivados(caminho)["correcoes"]


def _calcular(d, dzs, nao_conexao):
    trechos, els = d["trechos"], d["els"]
    geral = dzs.get("GERAL")
    lista, acoes = [], {}
    for i, t in enumerate(trechos):
        for lado in ("ini", "fim"):
            no = t.get(lado)
            j = t.get(lado + "E", -1)
            no_utm = (els[j]["E"], els[j]["N"]) if j is not None and 0 <= j < len(els) and els[j].get("E") is not None else None
            m = medir(geral, t, i, lado, no_utm) if geral else None
            classe, acao = classificar(no, m, nao_conexao.get((t["R"], lado)))
            item = {"trecho": t["R"], "i": i, "lado": lado, "no": no, "classe": classe, "acao": acao}
            if m is not None:
                item.update({k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()
                             if k in ("d_no_m", "d_utm_m", "ao_longo_m", "lateral_m", "arco")})
            lista.append(item)
            if acao in ("ESTENDER_ATE_NO", "APARAR"):
                acoes[(i, lado)] = (j, no_utm, acao)
    corr = {}
    for ident, dz in dzs.items():
        out = []
        for (i, lado), (j, no_utm, acao) in sorted(acoes.items()):
            partes = dz["tr"].get(i)
            if not partes:
                continue
            t = trechos[i]
            U = aplicar(dz["t"], *(t["A"] if lado == "ini" else t["B"]))
            k, qual, dd = _casar_ponta([_pontos(p) for p in partes], U)
            if dd > TOL_PONTA_UTM_M * dz["escala"]:
                continue                                    # essa ponta não está neste desenho (trecho cortado pela prancha)
            alvo = dz["el"].get(j) or aplicar(dz["t"], *no_utm)
            cortar = _aparar(_pontos(partes[k]) if qual == 0 else _pontos(partes[k])[::-1], alvo, dz["escala"]) if acao == "APARAR" else 0
            out.append([i, k, qual, cortar, round(alvo[0], 2), round(alvo[1], 2)])
        if out:
            corr[ident] = out
    return lista, corr


def _aparar(p, alvo, esc):
    """p começa na ponta que passou do nó: quantos vértices tirar para a linha terminar no nó (sem passar dele)."""
    acum = 0.0
    for k in range(len(p) - 1):
        a, b = p[k], p[k + 1]
        L = math.dist(a, b)
        if L > 0 and ((alvo[0] - a[0]) * (b[0] - a[0]) + (alvo[1] - a[1]) * (b[1] - a[1])) / (L * L) <= 1.0:
            return min(k + 1, len(p) - 1)                   # o nó cai neste segmento: some com os vértices antes dele
        acum += L
        if acum > ALCANCE_ARCO_M * esc:
            break
    return 0


def encaixar(partes, correcoes_trecho):
    """Aplica as correções de um trecho (lista de [parte, ponta, cortar, x, y]) às partes da polilinha (cópia)."""
    partes = [list(p) for p in partes]
    for k, qual, cortar, x, y in correcoes_trecho:
        p = partes[k]
        cortar = min(cortar, len(p) // 2 - 1)
        partes[k] = [x, y] + p[2 * cortar:] if qual == 0 else p[:len(p) - 2 * cortar] + [x, y]
    return partes


def geometria(caminho):
    c = _derivados(caminho)
    if "geometria" in c:
        return c["geometria"]
    d = c["dados"]
    g = d.get("visaoGeral")
    if not g:
        raise ValueError("O HTML do mapa não tem a visão geral (visaoGeral).")
    trechos = d["trechos"]
    corr = {}
    for i, k, qual, cortar, x, y in c["correcoes"].get("GERAL", []):
        corr.setdefault(i, []).append((k, qual, cortar, x, y))
    out = {
        "versao": int(c["chave"][1]),                       # muda com o HTML: a tela pede o satélite novo
        "w": g["w"], "h": g["h"],
        "zonas": [{"id": z["id"], "cor": z.get("color") or "#9AA3AE", "p": [_r(v) for v in z["p"]]} for z in g.get("zf", [])],
        "nomes": [{"id": n[0], "x": _r(n[1]), "y": _r(n[2])} for n in g.get("zn", [])],
        "quadros": [{"id": q["id"], "p": [_r(v) for v in q["p"]]} for q in g.get("frames", [])],
        "imagens": [{"id": im["id"], "w": im["w"], "h": im["h"], "m": im["matrix"]} for im in g.get("images", [])],
        "trechos": [],
        # nós e caixas desenhados na visão geral: [índice em DADOS.els, x, y]; os sem posição não aparecem aqui
        "els": [{"n": d["els"][e[0]]["noms"], "x": _r(e[1]), "y": _r(e[2])} for e in g.get("el", []) if e[0] < len(d["els"])],
    }
    for t in g.get("tr", []):
        f = trechos[t["i"]]
        partes = encaixar(t["p"], corr[t["i"]]) if t["i"] in corr else t["p"]   # ponta no centro do nó (lei da obra)
        out["trechos"].append({"n": f["R"], "z": f.get("loc"), "tp": f.get("tipo"), "de": f.get("de"), "L": f.get("L"),
                               "pb": f.get("pb"), "p": [[_r(v) for v in parte] for parte in partes]})
    c["geometria"] = out
    return out


def imagem_pb(caminho, pb):
    b64 = _ler(caminho)["imagens"].get(pb)
    return base64.b64decode(b64) if b64 else None


def mosaico(caminho, escala=1.3, qualidade=58):
    c = _ler(caminho)
    if "mosaico" in c:
        return c["mosaico"]
    try:
        from PIL import Image
    except ImportError:
        c["mosaico"] = None
        return None
    g = c["dados"]["visaoGeral"]
    tela = Image.new("RGB", (round(g["w"] * escala), round(g["h"] * escala)), (14, 14, 14))
    for im in g["images"]:
        b64 = c["imagens"].get(im["id"])
        if not b64:
            continue
        a, _, _, d, e, f = im["matrix"]                    # as PBs só têm escala e deslocamento (rotação ~1e-7)
        src = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        tam = (max(1, round(im["w"] * a * escala)), max(1, round(im["h"] * d * escala)))
        tela.paste(src.resize(tam, Image.LANCZOS, reducing_gap=2.0), (round(e * escala), round(f * escala)))
    buf = io.BytesIO()
    tela.save(buf, "WEBP", quality=qualidade, method=4)
    c["mosaico"] = buf.getvalue()
    return c["mosaico"]
