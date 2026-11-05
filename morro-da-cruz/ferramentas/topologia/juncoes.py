"""Junções que não são conexão: cruzamento com semicírculo, tubo que passa ao lado do nó e as emendas sem nó da 06.1
(divisa de zona, limite da travessia MND, ponta sem nó, junção sem nó).

Regra para as pontas que terminam no NOME de um nó (seção 3 de docs/TOPOLOGIA_TRECHOS.md):
  1. orçamento de peças: as peças do nó na 06.2 ligam no máximo `capacidade` pontas de tubo (base.portas);
     se chegam mais pontas do que isso, sobram tubos sem peça;
  2. continuidade: entre as pontas do nó, um par do mesmo DE e material, com as pontas juntas (≤ 0,30 m), alinhado
     (≥ 150° entre as direções de saída, medidas depois do arco) e afastado do marcador do nó (≥ 0,50 m; as peças ficam no marcador);
  3. tirando esse par, as pontas que ficam cabem nas peças do nó → o par passa direto: JUNTAR;
     com arco (semicírculo) numa das pontas ou outra linha cruzando ali, tipo CRUZAMENTO; sem isso, PASSAGEM;
  4. sobra peça para o par (capacidade ≥ pontas): é conexão de verdade (luva, redução, tê, válvula): NAO_JUNTAR;
  5. sobra tubo mas o par não fecha a conta ou está no marcador: DUVIDA (pergunta ao responsável).
"""
import math
from collections import defaultdict

import base as B

ORDEM_TIPO = {"CRUZAMENTO": 0, "PASSAGEM": 1, "CONEXAO": 2, "LIMITE_MND": 3, "DIVISA_ZONA": 4, "JUNCAO_SEM_NO": 5,
              "PONTA_SEM_NO": 6}


def _m(v, casas=2):
    """número com vírgula decimal (texto para o responsável)"""
    return f"{v:.{casas}f}".replace(".", ",")


def decidir_par(grau, capacidade, folga_m, angulo_graus, fora_do_no_m, mesmo_tubo, arco=False, linha_que_cruza=None,
                pares_passando=1):
    """Decisão de um par de pontas no nome de um nó. Devolve (tipo, decisao, motivo).
    grau = pontas de tubo que chegam ao nó; capacidade = pontas que as peças do nó ligam (base.portas);
    fora_do_no_m = o menor afastamento das duas pontas ao marcador do nó; mesmo_tubo = mesmo DE e material;
    pares_passando = quantos pares desse nó passam direto (normalmente 1)."""
    if not mesmo_tubo:
        return "CONEXAO", "NAO_JUNTAR", "troca de DE ou de material: precisa de peça (redução), é conexão"
    if folga_m > B.FOLGA_PAR_M or angulo_graus < B.ANGULO_MIN:
        return "CONEXAO", "NAO_JUNTAR", "as pontas não continuam uma na outra (afastadas ou em ângulo): é conexão"
    tipo = "CRUZAMENTO" if (arco or linha_que_cruza) else "PASSAGEM"
    if capacidade >= grau:
        return "CONEXAO", "NAO_JUNTAR", (f"as peças do nó ligam {capacidade} ponta(s) e chegam {grau}: sobra peça para "
                                         "este par, então é conexão (luva, redução, tê ou válvula)")
    if fora_do_no_m < B.FORA_DO_NO_M:
        return tipo, "DUVIDA", (f"chegam {grau} pontas e as peças ligam {capacidade}, mas este par está no marcador do nó "
                                f"({_m(fora_do_no_m)} m): não dá para dizer pelo desenho se passa direto")
    if grau - 2 * pares_passando > capacidade:
        return tipo, "DUVIDA", (f"chegam {grau} pontas e as peças ligam {capacidade}: mesmo tirando o tubo que passa "
                                "ainda falta peça no nó")
    sinal = ("com o semicírculo do pulo" if arco else f"cruzando {_curto(linha_que_cruza)}") if tipo == "CRUZAMENTO" else \
        "ao lado do nó, sem semicírculo"
    return tipo, "JUNTAR", (f"chegam {grau} pontas e as peças ligam {capacidade}: as {grau - 2 * pares_passando} outras "
                            f"pontas usam todas as peças e não sobra peça para este tubo, que passa reto a "
                            f"{_m(fora_do_no_m)} m do marcador do nó, {sinal}")


def _curto(nome):
    return str(nome or "").split("_")[-1]


def nos(base):
    """Candidatos nos nós com nome: [{junção}] e pendências de peças (nó com mais tubos que peças, sem par que passe)."""
    juncoes, pend = [], []
    for eid, pontas in sorted(base.pontas_el.items()):
        el = base.elementos[eid]
        grau = len(pontas)
        if grau < 2:
            continue
        pecas = base.pecas.get(eid, [])
        cap = B.portas(pecas)
        info = []
        for t, lado in pontas:
            m, p = base.medida(t, lado), base.poli_da_ponta(t, lado)
            if m is not None and p is not None and "d_no_m" in m:
                info.append((t, lado, m, p))
        pares = []                                        # pares que continuam um no outro (mesmo tubo, juntos, alinhados)
        for a in range(len(info)):
            for b in range(a + 1, len(info)):
                ta, la, ma, pa = info[a]
                tb, lb, mb, pb = info[b]
                ua, ub = base.utm_ponta(ta, la), base.utm_ponta(tb, lb)
                folga = math.dist(ua, ub)
                mesmo = B._f(ta["de_mm"]) == B._f(tb["de_mm"]) and (ta["material"] or "") == (tb["material"] or "")
                if folga > B.FOLGA_PAR_M or not mesmo:
                    continue
                j = ((ua[0] + ub[0]) / 2, (ua[1] + ub[1]) / 2)
                ang = B.angulo(B.direcao(pa), B.direcao(pb))
                if ang < B.ANGULO_MIN:
                    continue
                pares.append({"a": (ta, la, ma), "b": (tb, lb, mb), "folga": folga, "angulo": ang, "j": j,
                              "fora": min(ma["d_no_m"], mb["d_no_m"])})
        des = B.diametros(pecas)                          # o par cujo DE não está nas peças do nó passa primeiro
        pares.sort(key=lambda x: (int(B._f(x["a"][0]["de_mm"])) in des, -x["fora"], x["a"][0]["ponto"], x["b"][0]["ponto"]))
        escolhidos, usados = [], set()                    # pares afastados do marcador, sem repetir ponta
        for par in pares:
            ka, kb = (par["a"][0]["id"], par["a"][1]), (par["b"][0]["id"], par["b"][1])
            if par["fora"] >= B.FORA_DO_NO_M and ka not in usados and kb not in usados:
                escolhidos.append(par)
                usados |= {ka, kb}
        if not escolhidos:
            if cap < grau:
                pend.append({"tipo": "PECAS_A_MENOS", "no": el["noms"][0],
                             "detalhe": (f"{el['numero']}: chegam {grau} pontas de tubo e as peças da 06.2 ligam {cap} "
                                         f"({B.resumo_pecas(pecas)}); nenhum tubo passa reto afastado do nó")})
            continue
        precisa = max(0, (grau - cap + 1) // 2)           # pares que precisam passar para a conta das peças fechar
        for n, par in enumerate(escolhidos):
            (ta, la, ma), (tb, lb, mb) = par["a"], par["b"]
            arco = bool(ma["arco"]["tem"] or mb["arco"]["tem"])
            cruza = base.linha_que_cruza(par["j"], {ta["ponto"], tb["ponto"]})
            if n < precisa:
                tipo, dec, motivo = decidir_par(grau, cap, par["folga"], par["angulo"], par["fora"], True, arco,
                                                cruza[0] if cruza else None, pares_passando=min(precisa, len(escolhidos)))
            else:                                         # a conta já fechou: este par usa as peças do nó
                tipo, dec, motivo = decidir_par(grau - 2 * precisa, cap, par["folga"], par["angulo"], par["fora"], True,
                                                arco, cruza[0] if cruza else None)
            obs = [o for o in (ta["observacao"], tb["observacao"]) if o and "PRÓPRIO NÓ" in o]
            fora_par = {(ta["id"], la), (tb["id"], lb)}
            juncoes.append({
                "tipo": tipo, "no": ta["no_" + la], "utm": [round(par["j"][0], 3), round(par["j"][1], 3)],
                "pontas": [{"trecho": ta["ponto"], "lado": la, "de": int(B._f(ta["de_mm"])), "extensao_m": ta["extensao_m"]},
                           {"trecho": tb["ponto"], "lado": lb, "de": int(B._f(tb["de_mm"])), "extensao_m": tb["extensao_m"]}],
                "decisao": dec, "motivo": motivo,
                "sinais": {
                    "geometria": {"arco": [ma["arco"]["tem"], mb["arco"]["tem"]],
                                  "giro_graus": [ma["arco"]["giro"], mb["arco"]["giro"]],
                                  "linha_que_cruza": cruza[0] if cruza else None,
                                  "afastamento_do_no_m": [round(ma["d_no_m"], 3), round(mb["d_no_m"], 3)],
                                  "folga_entre_pontas_m": round(par["folga"], 3), "angulo_graus": round(par["angulo"], 1)},
                    "continuidade": {"de": int(B._f(ta["de_mm"])), "material": ta["material"],
                                     "metodologias": sorted({ta["metodologia"], tb["metodologia"]})},
                    "pecas": {"pontas_no_no": grau, "capacidade": cap, "sobra": grau - cap, "resumo": B.resumo_pecas(pecas),
                              "outras_pontas": [o["ponto"] + ":" + lo for o, lo in pontas if (o["id"], lo) not in fora_par]},
                    "nome": {"tipo_no": el["tipo"], "observacao_06_1": obs[0] if obs else None}}})
    return juncoes, pend


def sem_no(base):
    """Pontas sem nó na 06.1 (BP/BQ com DIVISA DE ZONA, LIMITE DA TRAVESSIA MND, PONTA SEM NÓ, JUNÇÃO SEM NÓ):
    agrupa as que estão a até 1 m uma da outra e decide a emenda."""
    pontas = [(t, lado) for t in base.trechos for lado in ("ini", "fim") if t["no_" + lado] in B.SEM_NO]
    pai = list(range(len(pontas)))

    def raiz(k):
        while pai[k] != k:
            pai[k] = pai[pai[k]]
            k = pai[k]
        return k
    for a in range(len(pontas)):
        for b in range(a + 1, len(pontas)):
            if pontas[a][0]["id"] != pontas[b][0]["id"] and \
                    math.dist(base.utm_ponta(*pontas[a]), base.utm_ponta(*pontas[b])) <= B.JUNTOS_SEM_NO_M:
                pai[raiz(a)] = raiz(b)
    grupos = defaultdict(list)
    for k in range(len(pontas)):
        grupos[raiz(k)].append(pontas[k])
    juncoes, pend = [], []
    for g in grupos.values():
        g.sort(key=lambda x: (x[0]["ponto"], x[1]))
        tipos = [B.SEM_NO[t["no_" + lado]] for t, lado in g]
        tipo = next(x for x in B.PRIORIDADE_SEM_NO if x in tipos)
        textos = sorted({t["no_" + lado] for t, lado in g})
        if len(g) == 1:
            continue                                      # ponta livre: pendência calculada pelo sistema (PONTA_SEM_CONEXAO)
        us = [base.utm_ponta(t, lado) for t, lado in g]
        j = (sum(u[0] for u in us) / len(us), sum(u[1] for u in us) / len(us))
        pts = [{"trecho": t["ponto"], "lado": lado, "de": int(B._f(t["de_mm"])), "extensao_m": t["extensao_m"]}
               for t, lado in g]
        if len(g) > 2:
            juncoes.append({"tipo": tipo, "no": textos[0], "utm": [round(j[0], 3), round(j[1], 3)], "pontas": pts,
                            "decisao": "NAO_JUNTAR",
                            "motivo": (f"{len(g)} tubos se encontram sem nó na 06.2 (DE {', '.join(str(p['de']) for p in pts)}): "
                                       "é um tê que falta na tabela de conexões, não emenda de um tubo só"),
                            "sinais": {"geometria": {"folga_entre_pontas_m": round(max(math.dist(a, b) for a in us for b in us), 3)}}})
            pend.append({"tipo": "TE_SEM_NO", "no": textos[0], "utm": [round(j[0], 3), round(j[1], 3)],
                         "detalhe": f"{len(g)} tubos se encontram sem nó na 06.2: " + ", ".join(p["trecho"] for p in pts)})
            continue
        (ta, la), (tb, lb) = g
        pa, pb = base.poli_da_ponta(ta, la), base.poli_da_ponta(tb, lb)
        folga = math.dist(us[0], us[1])
        ang = B.angulo(B.direcao(pa), B.direcao(pb)) if pa and pb else 0.0
        mesmo = B._f(ta["de_mm"]) == B._f(tb["de_mm"]) and (ta["material"] or "") == (tb["material"] or "")
        orig = sorted({o for o in (_original(ta), _original(tb)) if o})
        if not mesmo:
            dec, motivo = "NAO_JUNTAR", (f"troca de DE ({int(B._f(ta['de_mm']))} → {int(B._f(tb['de_mm']))}) ou de material "
                                         "sem nó: precisa de redução, não junta sem decisão do responsável")
        elif tipo in ("DIVISA_ZONA", "LIMITE_MND") and folga <= B.EMENDA_FIRME_M:
            dec = "JUNTAR"
            motivo = ("a 06.1 dividiu o tubo na divisa de zona: muda só a frente" if tipo == "DIVISA_ZONA" else
                      "a 06.1 dividiu o tubo no limite da travessia MND: muda só o método") + \
                (f" (trecho original entre pontos da rede: {orig[0]})" if orig else "")
        elif tipo in ("PONTA_SEM_NO", "JUNCAO_SEM_NO") and folga <= B.EMENDA_M and ang >= B.ANGULO_EMENDA_MIN:
            dec, motivo = "JUNTAR", (f"a 06.1 cortou o tubo sem nó: as pontas estão a {_m(folga)} m uma da outra e a linha "
                                     f"segue ({_m(ang, 0)}°); nas pranchas o tubo é contínuo")
        else:
            dec, motivo = "DUVIDA", (f"pontas sem nó a {_m(folga)} m uma da outra, ângulo de {_m(ang, 0)}°: pode ser emenda "
                                     "do mesmo tubo, vão no desenho ou peça que falta na 06.2")
        juncoes.append({"tipo": tipo, "no": textos[0] if len(textos) == 1 else " / ".join(textos),
                        "utm": [round(j[0], 3), round(j[1], 3)], "pontas": pts, "decisao": dec, "motivo": motivo,
                        "sinais": {"geometria": {"folga_entre_pontas_m": round(folga, 3), "angulo_graus": round(ang, 1)},
                                   "continuidade": {"de": [int(B._f(ta["de_mm"])), int(B._f(tb["de_mm"]))],
                                                    "metodologias": [ta["metodologia"], tb["metodologia"]],
                                                    "frentes": [ta["frente_id"], tb["frente_id"]]},
                                   "nome": {"trecho_original": orig[0] if orig else None}}})
    return juncoes, pend


def _original(t):
    import re
    m = re.search(r"TRECHO ORIGINAL ENTRE PONTOS DA REDE: ([\d.,]+) M", t["observacao"] or "")
    return m.group(1) + " m" if m else None


def todas(base):
    """Todas as junções (nós com nome + emendas sem nó), em ordem estável, e as pendências achadas no caminho."""
    j1, p1 = nos(base)
    j2, p2 = sem_no(base)
    js = j1 + j2
    for j in js:
        j.pop("_eid", None)
    js.sort(key=lambda j: (ORDEM_TIPO.get(j["tipo"], 9), j["no"], [p["trecho"] for p in j["pontas"]]))
    return js, p1 + p2
