"""Base das ferramentas de topologia dos trechos (diagnóstico, junções, cadeias e recortes).

Lê, sem alterar nada:
  * o mapa REV02 (mapa/PLANTAS_..._REV02_EQUIPES.html), pelo próprio mapa_geral do sistema (as mesmas medidas que a
    tela usa para encaixar as pontas);
  * um banco montado a partir das planilhas do repositório (06.1 e 06.2) pelo mesmo caminho dos testes
    (importar.aplicar com o perfil de teste), numa pasta temporária; ou um banco indicado em --banco.

Todas as medidas são em metros, no espaço UTM. Os nomes de nó são sempre o nome completo (Zona_PB_Tipo_NÓx.y):
o mesmo número de nó se repete em várias PBs (NÓ113.1 existe na PB05 e na PB08, a 47,52 m uma da outra).
"""
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
from collections import defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(AQUI))
for _p in (APP, os.path.join(APP, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import mapa_geral as MG  # noqa: E402
import topologia as TP  # noqa: E402

SAIDA = os.path.join(AQUI, "saida")
SEM_NO = MG.SEM_NO                       # texto da 06.1 → tipo de junção
PRIORIDADE_SEM_NO = ("LIMITE_MND", "DIVISA_ZONA", "JUNCAO_SEM_NO", "PONTA_SEM_NO")

# ---- tolerâncias da regra (justificadas em docs/TOPOLOGIA_TRECHOS.md)
FOLGA_PAR_M = 0.30           # as duas pontas de um tubo que continua ficam juntas (no caso B, 6 cm)
ANGULO_MIN = 150.0           # continuação: ângulo entre as direções de saída das duas pontas ≥ 150° (180° = reta)
FORA_DO_NO_M = 0.50          # o par que passa fica afastado do marcador do nó (as peças do nó ficam no marcador)
CORDA_M = 10.0               # comprimento da corda usada no ângulo
CRUZA_M = 0.75               # outra linha a até 0,75 m do ponto de junção = linha que cruza (o semicírculo pula ela)
JUNTOS_SEM_NO_M = 1.5        # pontas sem nó a até 1,5 m uma da outra são candidatas a emenda
EMENDA_FIRME_M = 0.10        # divisa de zona / limite MND: a 06.1 cortou o tubo num ponto só (folga 0)
EMENDA_M = 1.0               # emenda sem nó: folga até 1 m (vão de desenho no mesmo tubo, visto nas pranchas) ...
ANGULO_EMENDA_MIN = 120.0    # ... e dobra de até 60° (vértice da linha, sem curva na 06.2); acima disso: DUVIDA


def caminho_mapa():
    with open(os.path.join(APP, "config", "fontes.json"), encoding="utf-8") as f:
        return os.path.join(APP, "mapa", json.load(f)["arquivos"]["mapa"])


def montar_banco(pasta=None):
    """Banco novo a partir das planilhas do repositório (planilhas/), numa pasta temporária. Devolve o caminho."""
    import importacao as I
    import importar
    from perfil_teste import cfg_teste_real
    pasta = pasta or tempfile.mkdtemp(prefix="topologia_")
    db = os.path.join(pasta, "obra.db")
    os.makedirs(os.path.join(pasta, "fotos"), exist_ok=True)
    importar.aplicar(db, I.DIR_PLANILHAS, cfg=cfg_teste_real(), dir_relatorios=os.path.join(pasta, "rel"))
    return db


def _f(v):
    return float(v or 0)


def portas(pecas):
    """Quantas pontas de tubo as peças de um nó conseguem ligar (montagem em árvore: Σ bocas − 2 × (peças − 1)).
    Tê (inclusive de redução e de sela) = 3 bocas; curva, redução, válvula, VRP e medidor = 2; luva = 2 só quando é a
    única peça (luva em linha); junto de outra peça a luva é acessório da solda. Parafuso, flange, colarinho, toco,
    tubo curto, tampa etc. não contam."""
    bocas, luvas = [], 0
    for p in pecas:
        tc = (p.get("tipo_conexao") or "").upper()
        un = p.get("unidade")
        q = int(round(_f(p.get("quantidade")) or 1)) if un in ("UN", "PÇ", None) else 1
        if tc.startswith("TÊ"):
            k = 3
        elif tc.startswith(("CURVA", "REDUÇÃO", "VÁLVULA", "VRP", "MEDIDOR")):
            k = 2
        elif tc.startswith("LUVA"):
            luvas += max(q, 1)
            continue
        else:
            continue
        bocas += [k] * max(q, 1)
    if bocas:
        return sum(bocas) - 2 * (len(bocas) - 1)
    return 2 if luvas else 0


def resumo_pecas(pecas):
    vistos = {}
    for p in pecas:
        tc = p.get("tipo_conexao") or ""
        if tc in ("PARAFUSO", "ARRUELA", "FLANGE AVULSO", "COLARINHO", "ALÇA DE IÇAMENTO", "CHAPA EXPANDIDA",
                  "ESCADA MARINHEIRO", "TAMPÃO ARTICULADO", "TAMPA BIARTICULADA", "TAMPA ACIONAMENTO"):
            continue
        k = f"{tc} {p.get('diametro') or ''}".strip()
        vistos[k] = vistos.get(k, 0) + _f(p.get("quantidade") or 1)
    return ", ".join(f"{int(q) if q == int(q) else q}× {k}" for k, q in sorted(vistos.items()))


def direcao(p, L=CORDA_M):
    """p começa na ponta: direção (unitária) com que a linha sai dela, medida numa corda de até L metros que começa
    depois do arco do pulo (o semicírculo perto da ponta desvia a corda em até ~25°)."""
    comp = sum(math.dist(a, b) for a, b in zip(p, p[1:]))
    s1, acum = 0.0, 0.0
    for k in range(1, len(p) - 1):                       # último vértice que gira nos primeiros metros (fim do arco),
        acum += math.dist(p[k - 1], p[k])                # deixando ao menos 0,5 m de corda (degrau de 3 cm na outra
        if acum > min(MG.ALCANCE_ARCO_M, comp - 0.5):    # ponta não conta)
            break
        a = (p[k][0] - p[k - 1][0], p[k][1] - p[k - 1][1])
        b = (p[k + 1][0] - p[k][0], p[k + 1][1] - p[k][1])
        if math.hypot(*a) > 1e-9 and math.hypot(*b) > 1e-9:
            g = math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))
            if abs(g) >= 3.0:
                s1 = acum
    a, b = MG._ponto_a(p, s1), MG._ponto_a(p, min(s1 + L, comp))
    v = (b[0] - a[0], b[1] - a[1])
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n) if n > 1e-9 else (0.0, 0.0)


def angulo(u, v):
    """ângulo entre as direções de saída de duas pontas (180 = uma linha continua na outra)"""
    c = max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))
    return math.degrees(math.acos(c))


def diametros(pecas):
    """DE das peças de PEAD do nó (tê, curva, redução, luva): {160, 110, ...}"""
    out = set()
    for p in pecas:
        if (p.get("tipo_conexao") or "").upper().startswith(("TÊ", "CURVA", "REDUÇÃO", "LUVA")):
            for x in str(p.get("diametro") or "").upper().replace(" ", "").split("X"):
                if x.isdigit():
                    out.add(int(x))
    return out


def dist_ponto_segmento(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    if L2 <= 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
    return math.dist(p, (a[0] + t * vx, a[1] + t * vy))


class Base:
    """Tudo o que as ferramentas precisam, carregado uma vez."""

    def __init__(self, banco, mapa=None):
        self.banco, self.mapa = banco, mapa or caminho_mapa()
        c = sqlite3.connect(banco)
        try:
            cols = ("id", "ponto", "no_ini", "no_fim", "extensao_m", "de_mm", "material", "metodologia", "frente_id",
                    "tipo", "pb", "utm_ini", "utm_fim", "handle", "observacao")
            self.trechos = [dict(zip(cols, r)) for r in
                            c.execute(f"SELECT {', '.join(cols)} FROM trechos WHERE vigente = 1 ORDER BY id")]
            for t in self.trechos:
                t["ui"] = json.loads(t["utm_ini"]) if t["utm_ini"] else None
                t["uf"] = json.loads(t["utm_fim"]) if t["utm_fim"] else None
            self.nos = {}           # nomenclatura → elemento
            for r in c.execute("SELECT a.nomenclatura, e.id, e.numero, e.tipo, e.utm_e, e.utm_n, e.pb, e.zona "
                               "FROM atividades a JOIN elementos e ON e.id = a.elemento_id WHERE a.vigente = 1"):
                self.nos[r[0]] = {"eid": r[1], "numero": r[2], "tipo": r[3],
                                  "utm": (r[4], r[5]) if r[4] is not None else None, "pb": r[6], "zona": r[7]}
            self.pecas = defaultdict(list)    # elemento → itens da 06.2
            for r in c.execute("SELECT a.elemento_id, i.descricao, i.diametro, i.quantidade, i.unidade, i.tipo_conexao, "
                               "i.trechos FROM itens_projeto i JOIN atividades a ON a.id = i.atividade_id "
                               "WHERE i.vigente = 1 AND a.vigente = 1"):
                self.pecas[r[0]].append({"descricao": r[1], "diametro": r[2], "quantidade": r[3], "unidade": r[4],
                                         "tipo_conexao": r[5], "trechos": r[6]})
        finally:
            c.close()
        self.por_ponto = {t["ponto"]: t for t in self.trechos}
        self.elementos = {}
        for nom, n in self.nos.items():
            self.elementos.setdefault(n["eid"], dict(n, noms=[]))["noms"].append(nom)
        self.pontas_el = defaultdict(list)    # elemento → [(trecho, lado)]
        for t in self.trechos:
            for lado in ("ini", "fim"):
                n = self.nos.get(t["no_" + lado])
                if n:
                    self.pontas_el[n["eid"]].append((t, lado))
        # mapa: as mesmas medidas da tela
        dados = MG._ler(self.mapa)["dados"]
        self.html = dados
        self.idx = {t["R"]: i for i, t in enumerate(dados["trechos"])}
        self.desenhos = MG.desenhos(self.mapa)
        self.geral = self.desenhos["GERAL"]
        self._polis = {}

    # ---------------------------------------------------------------- geometria de um trecho (visão geral, em UTM)
    def partes_utm(self, ponto):
        if ponto not in self._polis:
            i = self.idx.get(ponto)
            partes = self.geral["tr"].get(i) if i is not None else None
            self._polis[ponto] = [[MG.aplicar(self.geral["inv"], x, y) for x, y in MG._pontos(p)] for p in partes or []]
        return self._polis[ponto]

    def utm_ponta(self, t, lado):
        return tuple(t["ui"] if lado == "ini" else t["uf"])

    def poli_da_ponta(self, t, lado):
        """polilinha (UTM) começando na ponta pedida (casada com a UTM da 06.1)"""
        partes = self.partes_utm(t["ponto"])
        if not partes:
            return None
        k, qual, _ = MG._casar_ponta(partes, self.utm_ponta(t, lado))
        return partes[k] if qual == 0 else partes[k][::-1]

    def medida(self, t, lado):
        """mapa_geral.medir na visão geral (d_no_m, d_utm_m, ao_longo_m, lateral_m, arco)"""
        i = self.idx.get(t["ponto"])
        no = self.nos.get(t["no_" + lado])
        if i is None:
            return None
        return MG.medir(self.geral, self.html["trechos"][i], i, lado, no["utm"] if no and no["utm"] else None)

    def medida_pb(self, t, lado):
        """d_no_m em cada prancha onde a ponta aparece: {PB: metros}"""
        i = self.idx.get(t["ponto"])
        no = self.nos.get(t["no_" + lado])
        out = {}
        if i is None or not no or not no["utm"]:
            return out
        for ident, dz in self.desenhos.items():
            if ident == "GERAL" or i not in dz["tr"]:
                continue
            m = MG.medir(dz, self.html["trechos"][i], i, lado, no["utm"])
            if m and m["d_utm_m"] <= MG.TOL_PONTA_UTM_M:
                out[ident] = m["d_no_m"]
        return out

    def linha_que_cruza(self, ponto_j, excluir):
        """outro trecho cuja polilinha passa a até CRUZA_M do ponto de junção (o semicírculo pula ele)"""
        melhor = None
        for t in self.trechos:
            if t["ponto"] in excluir:
                continue
            for p in self.partes_utm(t["ponto"]):
                for a, b in zip(p, p[1:]):
                    if abs(a[0] - ponto_j[0]) > 60 and abs(b[0] - ponto_j[0]) > 60:
                        continue
                    d = dist_ponto_segmento(ponto_j, a, b)
                    if d <= CRUZA_M and (melhor is None or d < melhor[1]):
                        melhor = (t["ponto"], d)
        return melhor
