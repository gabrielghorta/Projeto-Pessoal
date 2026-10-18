"""Visão geral do mapa REV02 para o Mapa Iluminado: satélite, zonas oficiais e traçado dos trechos.

Tudo sai do próprio HTML PLANTAS_..._REV02_EQUIPES (bloco `const DADOS = {...}`, chave `visaoGeral`), sem coordenada
nova: as zonas, os quadros das plantas, as imagens das 25 PBs e as polilinhas dos 1.436 trechos já vêm no espaço da
visão geral (largura × altura em unidades da prancha). O arquivo não é alterado; o resultado fica em memória e é
refeito quando o HTML muda (data de modificação).

* geometria(caminho)  → dicionário enxuto para a tela (zonas, nomes, quadros, trechos por nome visível, imagens)
* mosaico(caminho)    → as 25 imagens montadas numa só (webp), se o Pillow estiver instalado; senão None e a tela
                        monta as imagens uma a uma (imagem_pb)
* imagem_pb(caminho, pb) → bytes webp da imagem de uma PB, como está no HTML
"""
import base64
import io
import json
import os
import re
import threading

_TRAVA = threading.Lock()
_CACHE = {}


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
            dados = {"visaoGeral": dados.get("visaoGeral"), "trechos": dados.get("trechos"),   # o resto (peças, PBs) fica no HTML
                     "els": [{"noms": e.get("noms") or []} for e in dados.get("els") or []]}
            _CACHE.clear()
            _CACHE.update(chave=chave, dados=dados, imagens=imagens)
        return _CACHE


def _r(v):
    return round(float(v), 1)


def geometria(caminho):
    c = _ler(caminho)
    if "geometria" in c:
        return c["geometria"]
    d = c["dados"]
    g = d.get("visaoGeral")
    if not g:
        raise ValueError("O HTML do mapa não tem a visão geral (visaoGeral).")
    trechos = d["trechos"]
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
        out["trechos"].append({"n": f["R"], "z": f.get("loc"), "tp": f.get("tipo"), "de": f.get("de"), "L": f.get("L"),
                               "pb": f.get("pb"), "p": [[_r(v) for v in parte] for parte in t["p"]]})
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
