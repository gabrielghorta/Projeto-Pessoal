"""D-209: enquadramento da prancha 01 e canteiro, sem alterar a geometria da rede ou a topologia.

O retângulo vem do viewport do DWG, não da área das zonas ou de um recorte de tela.
Transformação UTM → desenho ajustada nos nós do REV02 (a mesma de mapa_geral.desenhos).
"""
import json
import os


def contexto(transformacao, inversa):
    with open(os.path.join(os.path.dirname(__file__), "config", "mapa_contexto.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    t = transformacao

    def xy(e, n):
        return [t[0] * e + t[1] * n + t[2], t[3] * e + t[4] * n + t[5]]

    x0, y0, x1, y1 = cfg["prancha01"]["limites_utm"]
    cantos = [xy(e, n) for e, n in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    ps = [xy(*p) for p in cfg["canteiro"]["vertices_utm"]]
    return {"crs": cfg["crs"], "utm_para_mapa": t, "mapa_para_utm": inversa,
            "limites": [min(p[0] for p in cantos), min(p[1] for p in cantos),
                        max(p[0] for p in cantos), max(p[1] for p in cantos)],
            "canteiro": {"p": [v for p in ps for v in p],
                         "centro": [sum(p[k] for p in ps) / len(ps) for k in (0, 1)]}}
