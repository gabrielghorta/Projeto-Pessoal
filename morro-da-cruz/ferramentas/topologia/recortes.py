"""Recortes de imagem para conferir as junções (e outras pontas) nas pranchas embutidas no HTML do mapa.

  python ferramentas/topologia/recortes.py                  # uma imagem por junção de config/topologia.json
  python ferramentas/topologia/recortes.py --cego           # sem a decisão no título (para revisão independente)
  python ferramentas/topologia/recortes.py --tipo PASSAGEM  # só as passagens, para a engenharia conferir
  python ferramentas/topologia/recortes.py --no Zona03_PB08_Rede_NÓ113.1 --no Zona04_PB06_Rede_NÓ2.1

Cada imagem tem à esquerda a prancha como está (imagem webp do HTML) e à direita a mesma área com as polilinhas
dos trechos (o par da junção em vermelho e azul, os outros trechos do nó em outras cores) e os nós (círculos pretos).
Saída: ferramentas/topologia/saida/recortes/ (fora do Git; a cópia de conferência vai para a pasta do Drive).
"""
import argparse
import io
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import base as B  # noqa: E402

MG = B.MG
PAR = [(230, 0, 0), (0, 110, 255)]
OUTRAS = [(0, 170, 0), (220, 0, 220), (255, 140, 0), (0, 190, 190), (130, 70, 0), (120, 0, 200)]


def _fonte(tam=13):
    """Fonte com acentos (NÓ, —); a fonte padrão do Pillow só tem ASCII."""
    from PIL import ImageFont
    for nome in ("DejaVuSans.ttf", "arial.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(nome, tam)
        except OSError:
            pass
    return ImageFont.load_default()


def recortar(mapa, E, N, destaque, saida, meia_m=6.0, zoom=10, titulo="", prancha=None):
    """Recorte em volta do ponto UTM (E, N) na prancha onde ele fica mais para dentro. destaque = [nome visível, ...]
    (os dois primeiros em vermelho e azul)."""
    from PIL import Image, ImageDraw
    dzs = MG.desenhos(mapa)
    d = MG._ler(mapa)["dados"]
    cand = []
    for ident, dz in dzs.items():
        if ident == "GERAL" or (prancha and ident != prancha) or dz["residuo_m"] is None or dz["residuo_m"][2] > 1.0:
            continue
        x, y = MG.aplicar(dz["t"], E, N)
        larg = max(v[0] for v in dz["el"].values()) if dz["el"] else 1788.66
        cand.append((min(x, 1788.66 - x, y, 1274.46 - y), ident, x, y))
    _, ident, cx, cy = max(cand)
    dz = dzs[ident]
    im = Image.open(io.BytesIO(MG.imagem_pb(mapa, ident))).convert("RGB")
    kx, ky = im.size[0] / 1788.66, im.size[1] / 1274.46
    r = meia_m * dz["escala"]
    caixa = (int((cx - r) * kx), int((cy - r) * ky), int((cx + r) * kx), int((cy + r) * ky))
    c = im.crop(caixa).resize(((caixa[2] - caixa[0]) * zoom, (caixa[3] - caixa[1]) * zoom), Image.LANCZOS)
    cru = c.copy()
    dr = ImageDraw.Draw(c)
    f = lambda x, y: ((x * kx - caixa[0]) * zoom, (y * ky - caixa[1]) * zoom)
    cores = {n: PAR[k] if k < 2 else OUTRAS[(k - 2) % len(OUTRAS)] for k, n in enumerate(destaque)}
    for i, partes in dz["tr"].items():
        nome = d["trechos"][i]["R"]
        if nome not in cores:
            continue
        for parte in partes:
            pts = [f(parte[q], parte[q + 1]) for q in range(0, len(parte) - 1, 2)]
            dr.line(pts, fill=cores[nome], width=3)
    for _j, (x, y) in dz["el"].items():
        X, Y = f(x, y)
        if -20 < X < c.size[0] + 20 and -20 < Y < c.size[1] + 20:
            dr.ellipse((X - 6, Y - 6, X + 6, Y + 6), outline=(0, 0, 0), width=2)
    out = Image.new("RGB", (c.size[0] * 2 + 10, c.size[1] + 26 + 17 * len(destaque)), (255, 255, 255))
    out.paste(cru, (0, 0))
    out.paste(c, (c.size[0] + 10, 0))
    dw, fonte = ImageDraw.Draw(out), _fonte()
    dw.text((4, c.size[1] + 4), f"{titulo}  [{ident}, {2 * meia_m:.0f} m de lado]", fill=(0, 0, 0), font=fonte)
    for k, n in enumerate(destaque):
        dw.text((4, c.size[1] + 24 + 17 * k), "■ " + n, fill=cores[n], font=fonte)
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    out.save(saida)
    return ident


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cego", action="store_true", help="sem tipo/decisão no título")
    ap.add_argument("--no", action="append", default=[], help="recorte em volta de um nó (nome completo)")
    ap.add_argument("--tipo", action="append", default=[], help="só as junções deste tipo (ex.: PASSAGEM)")
    ap.add_argument("--banco", help="banco (só para --no); padrão: monta das planilhas")
    ap.add_argument("--saida", default=os.path.join(B.SAIDA, "recortes"))
    a = ap.parse_args(argv)
    mapa = B.caminho_mapa()
    if a.no:
        banco = a.banco or B.montar_banco()
        base = B.Base(banco, mapa)
        for nome in a.no:
            n = base.nos[nome]
            trs = [t["ponto"] for t, _ in base.pontas_el.get(n["eid"], [])]
            p = os.path.join(a.saida, nome.replace("/", "_") + ".png")
            recortar(mapa, n["utm"][0], n["utm"][1], trs, p, titulo=nome)
            print(p)
        return
    with open(os.path.join(B.APP, "config", "topologia.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    for j in cfg["juncoes"]:
        if a.tipo and j["tipo"] not in a.tipo:
            continue
        par = [p["trecho"] for p in j["pontas"]]
        outras = [o.split(":")[0] for o in ((j.get("sinais") or {}).get("pecas") or {}).get("outras_pontas") or []]
        titulo = j["id"] if a.cego else f"{j['id']} {j['tipo']} {j['decisao']} — {j['no']}"
        p = os.path.join(a.saida, f"{j['id']}.png")
        recortar(mapa, j["utm"][0], j["utm"][1], par + [o for o in outras if o not in par], p, titulo=titulo)
        print(p)


if __name__ == "__main__":
    main()
