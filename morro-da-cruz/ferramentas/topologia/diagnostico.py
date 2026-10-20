"""Diagnóstico da topologia dos trechos e geração do arquivo de decisões config/topologia.json.

  python ferramentas/topologia/diagnostico.py            # só mede e grava os CSVs em ferramentas/topologia/saida/
  python ferramentas/topologia/diagnostico.py --gravar   # ... e regrava config/topologia.json (mantém o que o
                                                         #     responsável revisou: junção com "revisao" preenchida)
  python ferramentas/topologia/diagnostico.py --banco dados/morro_da_cruz.db   # usa um banco já carregado

Sem --banco, monta um banco descartável a partir das planilhas do repositório (o mesmo caminho dos testes).
Nada no mapa, nas planilhas ou no banco é alterado. Etapas (seções 5.1 a 5.5 de docs/TOPOLOGIA_TRECHOS.md):
  5.1 transformação UTM → desenho (visão geral e cada prancha) e o resíduo nos nós;
  5.2 cada ponta de trecho medida contra o nó (pontas.csv) e o teste da hipótese do anel de ~1,5 m;
  5.3/5.4 junções que não são conexão, com sinais e decisão (cruzamentos.csv);
  5.5 trechos físicos montados pelo próprio topologia.py com as decisões (cadeias.csv) e as conferências.
"""
import argparse
import csv
import json
import math
import os
import shutil
import sqlite3
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import base as B  # noqa: E402
import juncoes as J  # noqa: E402

MG, TP = B.MG, B.TP
CONFIG = os.path.join(B.APP, "config", "topologia.json")


def _m(v, casas=2):
    """número com vírgula decimal (texto para o responsável)"""
    return f"{v:.{casas}f}".replace(".", ",")


def _csv(nome, linhas, campos):
    os.makedirs(B.SAIDA, exist_ok=True)
    p = os.path.join(B.SAIDA, nome)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for l in linhas:
            w.writerow({k: ("" if v is None else v) for k, v in l.items()})
    return p


def _faixas(vals):
    return {"> 0,10 m": sum(v > 0.10 for v in vals), "> 0,5 m": sum(v > 0.5 for v in vals),
            "> 1 m": sum(v > 1.0 for v in vals), "> 3 m": sum(v > 3.0 for v in vals)}


# ---------------------------------------------------------------- 5.1
def coordenadas(base):
    out = {}
    for ident, dz in sorted(base.desenhos.items(), key=lambda x: (x[0] != "GERAL", x[0])):
        out[ident] = {"unidades_por_metro": round(dz["escala"], 6), "nos": dz["n"],
                      "residuo_m": dict(zip(("mediana", "p95", "max"), dz["residuo_m"])) if dz["residuo_m"] else None,
                      "rotacao_graus": round(math.degrees(math.atan2(dz["t"][3], dz["t"][0])), 3)}
    return out


# ---------------------------------------------------------------- 5.2
def pontas(base, juncoes):
    na = {(p["trecho"], p["lado"]): j for j in juncoes for p in j["pontas"]}
    lista = []
    pb_dif = []
    for item in MG.pontas(base.mapa):
        t = base.por_ponto.get(item["trecho"])
        lado = item["lado"]
        no = base.nos.get(item["no"])
        eid = no["eid"] if no else None
        pecas = base.pecas.get(eid, []) if eid else []
        u06 = base.utm_ponta(t, lado) if t else None
        d06 = math.dist(u06, no["utm"]) if (no and no["utm"] and u06) else None
        pbs = base.medida_pb(t, lado) if t else {}
        if pbs and "d_no_m" in item:
            pb_dif.append(max(abs(v - item["d_no_m"]) for v in pbs.values()))
        j = na.get((item["trecho"], lado))
        lista.append({
            "trecho_id": t["id"] if t else None, "ponto": item["trecho"], "lado": lado, "no": item["no"],
            "tipo_no": no["tipo"] if no else None, "pontas_no_no": len(base.pontas_el.get(eid, [])) if eid else None,
            "capacidade_pecas": B.portas(pecas) if eid else None, "pecas": B.resumo_pecas(pecas) if eid else None,
            "d_no_m": item.get("d_no_m"), "d_no_pranchas_m": ";".join(f"{k}={v:.3f}" for k, v in sorted(pbs.items())),
            "d_utm_desenho_m": item.get("d_utm_m"), "utm_06_1_x_no_06_2_m": round(d06, 3) if d06 is not None else None,
            "ao_longo_m": item.get("ao_longo_m"), "lateral_m": item.get("lateral_m"),
            "arco": (item.get("arco") or {}).get("tem"), "arco_giro_graus": (item.get("arco") or {}).get("giro"),
            "classe": item["classe"], "acao": item["acao"],
            "juncao": j.get("id") if j else None, "juncao_tipo": j["tipo"] if j else None,
            "juncao_decisao": j["decisao"] if j else None,
            "de_mm": int(B._f(t["de_mm"])) if t else None, "metodologia": t["metodologia"] if t else None,
            "observacao_06_1": t["observacao"] if t else None})
    return lista, pb_dif


def hipotese_anel(base, lista):
    """O marcador do nó seria um anel de ~1,5 m onde as linhas param? Testa com a distância ponta → nó."""
    ds = [l["utm_06_1_x_no_06_2_m"] for l in lista if l["utm_06_1_x_no_06_2_m"] is not None]
    fora = sorted(d for d in ds if d > MG.TOL_NO_M)
    anel = [d for d in fora if 1.3 <= d <= 1.7]
    passam = [l for l in lista if l["juncao_tipo"] in ("CRUZAMENTO", "PASSAGEM")]
    hist = Counter(min(int(d / 0.1), 16) for d in fora)
    lx = [(t["ponto"], t["observacao"]) for t in base.trechos if "PRÓPRIO NÓ" in (t["observacao"] or "")]
    # se o "tubo desenhado no próprio nó" (Lx) fosse o pedaço dentro do anel, a ponta desse lado ficaria a ~Lx do nó
    import re
    lado_lx = []
    por = {(l["ponto"], l["lado"]): l for l in lista}
    for t in base.trechos:
        m = re.search(r"\((NÓ[^:,)]*)[,:]", t["observacao"] or "")
        if not m or "PRÓPRIO NÓ" not in (t["observacao"] or ""):
            continue
        for lado in ("ini", "fim"):
            if (t["no_" + lado] or "").endswith("_" + m.group(1)):
                d = por[(t["ponto"], lado)]["utm_06_1_x_no_06_2_m"]
                if d is not None:
                    lado_lx.append(d)
    return {"pontas_com_no": len(ds), "no_no_ate_10cm": len(ds) - len(fora), "fora_do_no": len(fora),
            "tubo_no_proprio_no_ponta_ate_10cm_do_no": sum(d <= MG.TOL_NO_M for d in lado_lx),
            "tubo_no_proprio_no_pontas_medidas": len(lado_lx),
            "mediana_fora_m": round(statistics.median(fora), 3) if fora else None, "maximo_m": round(max(ds), 3),
            "entre_1_3_e_1_7_m": len(anel), "das_quais_pontas_que_passam_pelo_no": sum(
                1 for l in passam if l["utm_06_1_x_no_06_2_m"] and 1.3 <= l["utm_06_1_x_no_06_2_m"] <= 1.7),
            "acima_de_1_6_m": sum(d > 1.6 for d in ds),
            "histograma_10cm": {f"{_m(k / 10, 1)}-{_m((k + 1) / 10, 1)}": hist[k] for k in sorted(hist)},
            "trechos_com_tubo_no_proprio_no": len(lx)}


def comprimentos(base):
    """comprimento desenhado (visão geral, em metros) × L e Lg da 06.1, nos trechos desenhados numa parte só"""
    d = base.html["trechos"]
    difs_l, difs_lg, n = [], [], 0
    for t in base.trechos:
        partes = base.partes_utm(t["ponto"])
        if len(partes) != 1:
            continue
        n += 1
        L = sum(math.dist(a, b) for a, b in zip(partes[0], partes[0][1:]))
        h = d[base.idx[t["ponto"]]]
        difs_l.append(abs(L - h["L"]))
        difs_lg.append(abs(L - h["Lg"]))
    lx = [h for h in d if (h.get("Lx") or 0) > 0]
    return {"trechos_numa_parte": n, "desenho_x_L_acima_de_5cm": sum(x > 0.05 for x in difs_l),
            "desenho_x_Lg_acima_de_5cm": sum(x > 0.05 for x in difs_lg), "max_desenho_x_Lg_m": round(max(difs_lg), 3),
            "trechos_com_Lx": len(lx), "soma_Lx_m": round(sum(h["Lx"] for h in lx), 2),
            "max_Lx_m": max(h["Lx"] for h in lx), "soma_L_m": round(sum(h["L"] for h in d), 2),
            "soma_Lg_m": round(sum(h["Lg"] for h in d), 2)}


def dados_06_1(base):
    """Números da 06.1 e dos nomes de nó (seção 4 do roteiro: reproduzir ou derrubar)."""
    import re
    ts = base.trechos
    sem = Counter(t["no_" + l] for t in ts for l in ("ini", "fim") if t["no_" + l] in B.SEM_NO)
    divididos = Counter(m.group(1) for t in ts for m in
                        [re.search(r"TRECHO DIVIDIDO N[AO] (DIVISA DE ZONA|LIMITE DA TRAVESSIA MND)", t["observacao"] or "")] if m)
    nums, so_no = defaultdict(set), defaultdict(set)      # número (NÓ1.1, DF-05…) nas pontas da 06.1 → combinações Zona_PB
    for t in ts:
        for l in ("ini", "fim"):
            p = (t["no_" + l] or "").split("_")
            if len(p) >= 4 and p[0].startswith("Zona"):
                nums[p[-1]].add("_".join(p[:2]))
                if p[-1].startswith("NÓ"):
                    so_no[p[-1]].add("_".join(p[:2]))
    prefixo = sum(1 for t in ts for l in ("ini", "fim") if t["no_" + l] in base.nos
                  and "_".join(t["no_" + l].split("_")[:2]) != "_".join(t["ponto"].split("_")[:2]))
    pontas = defaultdict(list)
    for t in ts:
        pontas[tuple(sorted((t["no_ini"], t["no_fim"])))].append(t)
    paralelos = [[t["ponto"] for t in v] for k, v in pontas.items() if len(v) > 1 and not set(k) & set(B.SEM_NO)]
    grau2 = [v for v in base.pontas_el.values() if len(v) == 2]
    mesmo_lado = sum(1 for (a, la), (b, lb) in grau2 if la == lb)
    return {"linhas": len(ts), "por_tipo": dict(Counter(t["tipo"] for t in ts)),
            "por_metodologia": dict(Counter(t["metodologia"] for t in ts)),
            "materiais": sorted({t["material"] for t in ts}), "extensao_m": round(sum(B._f(t["extensao_m"]) for t in ts), 2),
            "de_mm": sorted({int(B._f(t["de_mm"])) for t in ts}),
            "pontas_sem_no": dict(sem), "pontas_sem_no_total": sum(sem.values()),
            "trechos_com_ponta_sem_no": sum(1 for t in ts if t["no_ini"] in B.SEM_NO or t["no_fim"] in B.SEM_NO),
            "trechos_divididos": dict(divididos),
            "numeros_distintos_nas_pontas": len(nums), "numeros_repetidos_entre_pbs": sum(1 for v in nums.values() if len(v) > 1),
            "numeros_de_NO_distintos": len(so_no), "no1_1_combinacoes": len(nums.get("NÓ1.1", ())),
            "pontas_com_prefixo_de_no_diferente": prefixo,
            "pares_paralelos_mesmas_pontas": paralelos, "nos_de_grau_2": len(grau2),
            "grau_2_ambas_chegam_ou_ambas_saem": mesmo_lado}


# ---------------------------------------------------------------- arquivo de decisões
def _chave(j):
    return tuple(sorted((p["trecho"], p["lado"]) for p in j["pontas"]))


def mesclar(novas, antigo):
    """Mantém id e, quando o responsável revisou ("revisao" preenchida), a decisão dele."""
    velhas = {_chave(j): j for j in (antigo or {}).get("juncoes") or []}
    usados = {j.get("id") for j in velhas.values()}
    prox = 1 + max([int(str(i).split("-")[-1]) for i in usados if i and str(i).split("-")[-1].isdigit()] or [0])
    out = []
    for j in novas:
        v = velhas.pop(_chave(j), None)
        if v and v.get("id"):
            j["id"] = v["id"]
        else:
            j["id"] = f"J-{prox:03d}"
            prox += 1
        j["revisao"] = None
        if v and v.get("revisao"):
            j["decisao_da_ferramenta"], j["motivo_da_ferramenta"] = j["decisao"], j["motivo"]
            j["decisao"], j["motivo"], j["revisao"] = v["decisao"], v.get("motivo"), v["revisao"]
        out.append(j)
    for v in velhas.values():                              # revisada pelo responsável e sumida dos dados: não se perde
        if v.get("revisao"):
            v["nao_encontrada_na_geracao"] = date.today().isoformat()
            out.append(v)
    out.sort(key=lambda j: j["id"])
    return out


def pendencias_desenho(base, lista):
    out = []
    for l in lista:
        if l["acao"] != "PENDENCIA_DESENHO":
            continue
        if l["classe"] == "LONGE_DO_NO":
            det = f"o desenho termina a {_m(l['d_no_m'])} m de {l['no']}: longe demais para encaixar sem conferir a planta"
        elif l["classe"] == "DESENHO_INCOMPLETO":
            det = f"o desenho para a {_m(l['d_utm_desenho_m'])} m da ponta que a 06.1 dá para o trecho"
        else:
            det = f"{l['classe']}: ponta sem desenho ou sem posição do nó"
        out.append({"tipo": "PONTA_FORA_DO_NO", "trecho": l["ponto"], "lado": l["lado"], "no": l["no"],
                    "classe": l["classe"], "detalhe": det})
    for ident, dz in base.desenhos.items():
        if ident != "GERAL" and dz["residuo_m"] and dz["residuo_m"][2] > 1.0:
            trs = sorted(base.html["trechos"][i]["R"] for i in dz["tr"])
            out.append({"tipo": "PRANCHA_DESLOCADA", "prancha": ident,
                        "detalhe": (f"o desenho vetorial da {ident} no HTML está deslocado {_m(dz['residuo_m'][2], 1)} m dos nós "
                                    f"(o quadro e a imagem estão certos); na visão geral aparecem cópias fora do lugar de "
                                    f"{', '.join(trs)}")})
    livres = defaultdict(list)
    for t in base.trechos:
        for lado in ("ini", "fim"):
            if t["no_" + lado] in B.SEM_NO:
                livres[t["id"]].append(lado)
    for t in base.trechos:
        if len(livres.get(t["id"], [])) == 2:
            u = [base.utm_ponta(t, l) for l in ("ini", "fim")]
            viz = min(math.dist(a, base.utm_ponta(o, lo)) for a in u for o in base.trechos if o is not t
                      for lo in ("ini", "fim"))
            if viz > B.JUNTOS_SEM_NO_M:
                out.append({"tipo": "TRECHO_ISOLADO", "trecho": t["ponto"],
                            "detalhe": (f"{t['ponto']} ({t['extensao_m']} m, DE {int(B._f(t['de_mm']))}) não toca nenhum "
                                        f"nó nem outro trecho (o mais perto está a {_m(viz, 1)} m)")})
    return out


def gravar_config(juncoes, pend, resumo, caminho):
    antigo = None
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            antigo = json.load(f)
    js = mesclar(juncoes, antigo)
    with open(os.path.join(B.APP, "config", "fontes.json"), encoding="utf-8") as f:
        arq = json.load(f)["arquivos"]
    cfg = {
        "versao": 1,
        "gerado_em": date.today().isoformat(),
        "gerado_por": "ferramentas/topologia/diagnostico.py --gravar",
        "fontes": {"redes": arq["redes"], "conexoes": arq["conexoes"], "mapa": arq["mapa"]},
        "como_revisar": ("Cada junção liga duas pontas de linhas da 06.1 que NÃO terminam numa conexão. JUNTAR = o "
                         "sistema trata as duas linhas como um só trecho físico; NAO_JUNTAR = conexão de verdade; DUVIDA = "
                         "pergunta ao responsável (não junta). Para corrigir: troque \"decisao\", explique em \"motivo\" e "
                         "preencha \"revisao\": {\"por\": \"nome\", \"em\": \"AAAA-MM-DD\"}. A ferramenta, ao gerar de novo, "
                         "mantém toda decisão com \"revisao\" preenchida."),
        "tipos": {"CRUZAMENTO": "o tubo passa por outra rede com o semicírculo do pulo, no nome de um nó que não é dele",
                  "PASSAGEM": "o tubo passa ao lado de um nó (de outra rede paralela), sem peça para ele",
                  "CONEXAO": "candidato rejeitado: as peças do nó ligam este par (luva, redução, tê, válvula)",
                  "DIVISA_ZONA": "a 06.1 dividiu o tubo na divisa de zona: muda só a frente",
                  "LIMITE_MND": "a 06.1 dividiu o tubo no limite da travessia MND: muda só o método",
                  "PONTA_SEM_NO": "duas pontas sem nó na tabela que se encontram: emenda do mesmo tubo",
                  "JUNCAO_SEM_NO": "três ou mais tubos se encontram sem nó na tabela (tê que falta na 06.2)"},
        "resumo": resumo,
        "juncoes": js,
        "pendencias": pend,
    }
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return cfg


# ---------------------------------------------------------------- 5.5
def cadeias(banco, cfg_caminho):
    """Monta os trechos físicos com o próprio topologia.py (o que o sistema vai mostrar) e confere."""
    antigo = TP.CONFIG
    TP.CONFIG = cfg_caminho
    TP._CACHE.clear()
    conn = sqlite3.connect(banco)
    try:
        fis = TP.trechos_fisicos(conn)
        pend = TP.pendencias(conn)
        res = TP.resumo(conn)
    finally:
        conn.close()
        TP.CONFIG = antigo
        TP._CACHE.clear()
    return fis, pend, res


def conferir_cadeias(base, fis):
    ids = Counter(m["trecho_id"] for f in fis for m in f["membros"])
    soma = sum(B._f(t["extensao_m"]) for t in base.trechos)
    grupos = defaultdict(list)                           # "TRECHO ORIGINAL ENTRE PONTOS DA REDE" da 06.1
    import re
    for t in base.trechos:
        m = re.search(r"TRECHO DIVIDIDO N[AO] (?:DIVISA DE ZONA|LIMITE DA TRAVESSIA MND) \(TRECHO ORIGINAL ENTRE PONTOS "
                      r"DA REDE: ([\d.,]+) M\)", t["observacao"] or "")
        if m:
            grupos[m.group(1)].append(t["id"])
    de = {m["trecho_id"]: f for f in fis for m in f["membros"]}
    juntos = sum(1 for g in grupos.values() if len({de[i]["id"] for i in g}) == 1)
    return {"linhas_em_exatamente_um_trecho_fisico": sum(1 for t in base.trechos if ids[t["id"]] == 1),
            "linhas_06_1": len(base.trechos), "soma_06_1_m": round(soma, 2),
            "soma_trechos_fisicos_m": round(sum(f["extensao_m"] for f in fis), 2),
            "grupos_trecho_original_06_1": len(grupos), "grupos_no_mesmo_trecho_fisico": juntos}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--banco", help="banco já carregado (padrão: monta um descartável a partir de planilhas/)")
    ap.add_argument("--gravar", action="store_true", help="regrava config/topologia.json")
    a = ap.parse_args(argv)
    tmp = None
    banco = a.banco
    if not banco:
        tmp = tempfile.mkdtemp(prefix="topologia_")
        print("montando o banco a partir das planilhas do repositório…")
        banco = B.montar_banco(tmp)
    try:
        base = B.Base(banco)
        juncoes, pend = J.todas(base)
        cfg_tmp = os.path.join(tmp or tempfile.mkdtemp(prefix="topologia_cfg_"), "topologia.json")
        resumo_j = {"juncoes": dict(Counter(f"{j['tipo']} {j['decisao']}" for j in juncoes))}
        lista_prev, _ = pontas(base, juncoes)
        pend_all = pend + pendencias_desenho(base, lista_prev)
        if os.path.exists(CONFIG):
            shutil.copy(CONFIG, cfg_tmp)
        cfg = gravar_config(juncoes, pend_all, resumo_j, cfg_tmp)  # ids e revisões preservados
        juncoes = cfg["juncoes"]
        # mapa_geral lê as decisões para não encaixar as pontas de cruzamento/passagem
        antigo = TP.CONFIG
        TP.CONFIG = cfg_tmp
        try:
            MG._CACHE.pop("pontas", None)
            MG._CACHE.pop("derivados_chave", None)
            lista, pb_dif = pontas(base, juncoes)
            correcoes = MG.correcoes(base.mapa)
        finally:
            TP.CONFIG = antigo
            MG._CACHE.pop("pontas", None)
            MG._CACHE.pop("derivados_chave", None)
        fis, pend_sis, res_tp = cadeias(banco, cfg_tmp)
        conf = conferir_cadeias(base, fis)
        classes = Counter(l["classe"] for l in lista)
        dist = [l["d_no_m"] for l in lista if l["d_no_m"] is not None]
        resumo = {
            "coordenadas": coordenadas(base),
            "dados_06_1": dados_06_1(base),
            "linhas_06_1": len(base.trechos), "pontas": len(lista),
            "pontas_por_classe": dict(classes.most_common()),
            "pontas_por_acao": dict(Counter(l["acao"] for l in lista).most_common()),
            "distancia_ponta_no_visao_geral": _faixas(dist),
            "distancia_ponta_no_fora_juncoes": _faixas([l["d_no_m"] for l in lista if l["d_no_m"] is not None
                                                        and not l["juncao_tipo"]]),
            "pranchas_x_visao_geral": {"pontas_comparadas": len(pb_dif),
                                       "diferenca_max_m": round(max(pb_dif), 3) if pb_dif else None,
                                       "acima_de_5cm": sum(x > 0.05 for x in pb_dif)},
            "correcoes_por_desenho": {k: len(v) for k, v in sorted(correcoes.items())},
            "hipotese_anel": hipotese_anel(base, lista),
            "comprimento_desenhado": comprimentos(base),
            "juncoes_por_tipo_e_decisao": dict(Counter(f"{j['tipo']} {j['decisao']}" for j in juncoes).most_common()),
            "juncoes_por_decisao": dict(Counter(j["decisao"] for j in juncoes).most_common()),
            "trechos_fisicos": res_tp,
            "conferencia_cadeias": conf,
            "pendencias_do_sistema": dict(Counter(p["tipo"] for p in pend_sis).most_common()),
            "pendencias_da_ferramenta": dict(Counter(p["tipo"] for p in pend_all).most_common()),
        }
        cfg["resumo"] = {k: resumo[k] for k in ("pontas_por_classe", "juncoes_por_tipo_e_decisao", "juncoes_por_decisao")}
        cfg["resumo"]["trechos_fisicos"] = {k: res_tp[k] for k in ("linhas_06_1", "trechos_fisicos", "com_mais_de_uma_linha",
                                                                    "linhas_em_cadeias")}
        if a.gravar:
            with open(cfg_tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=1)
                f.write("\n")
            shutil.copy(cfg_tmp, CONFIG)
            print("gravado:", os.path.relpath(CONFIG, B.APP))
        # ---- CSVs
        campos_p = list(lista[0].keys())
        _csv("pontas.csv", lista, campos_p)
        _csv("pontas_fora_do_no.csv", [l for l in lista if l["classe"] != "NO_NO"], campos_p)
        linhas_j = []
        for j in juncoes:
            g = j.get("sinais", {}).get("geometria", {})
            pc = j.get("sinais", {}).get("pecas", {})
            linhas_j.append({"id": j["id"], "tipo": j["tipo"], "decisao": j["decisao"], "no": j["no"],
                             "utm_e": j["utm"][0], "utm_n": j["utm"][1],
                             "pontas": " + ".join(f"{p['trecho']}:{p['lado']}" for p in j["pontas"]),
                             "de_mm": "/".join(sorted({str(p["de"]) for p in j["pontas"]})),
                             "folga_m": g.get("folga_entre_pontas_m"), "angulo_graus": g.get("angulo_graus"),
                             "afastamento_do_no_m": "/".join(str(x) for x in g.get("afastamento_do_no_m") or []),
                             "arco": "/".join(str(x) for x in g.get("arco") or []), "linha_que_cruza": g.get("linha_que_cruza"),
                             "pontas_no_no": pc.get("pontas_no_no"), "capacidade_pecas": pc.get("capacidade"),
                             "pecas": pc.get("resumo"), "outras_pontas": " ".join(pc.get("outras_pontas") or []),
                             "observacao_06_1": (j.get("sinais", {}).get("nome") or {}).get("observacao_06_1")
                             or (j.get("sinais", {}).get("nome") or {}).get("trecho_original"),
                             "motivo": j["motivo"], "revisao": json.dumps(j["revisao"], ensure_ascii=False) if j.get("revisao") else None})
        _csv("cruzamentos.csv", linhas_j, list(linhas_j[0].keys()))
        linhas_c = []
        for f in fis:
            if len(f["membros"]) < 2:
                continue
            for k, m in enumerate(f["membros"]):
                jn = f["juncoes"][k] if k < len(f["juncoes"]) else None
                linhas_c.append({"trecho_fisico": f["id"], "no_ini": f["no_ini"], "no_fim": f["no_fim"],
                                 "extensao_fisico_m": f["extensao_m"], "de_mm": f["de_mm"], "membros": len(f["membros"]),
                                 "ordem": m["ordem"], "trecho_id": m["trecho_id"], "ponto": m["ponto"],
                                 "offset_m": m["offset_m"], "extensao_m": m["extensao_m"], "sentido": m["sentido"],
                                 "juncao_seguinte": f"{jn['id']} {jn['tipo']} {jn['no']}" if jn else None,
                                 "metodologias": "/".join(f["metodologias"]), "frentes": "/".join(f["frentes"]),
                                 "texto": f["texto"] if k == 0 else None})
        _csv("cadeias.csv", linhas_c, list(linhas_c[0].keys()))
        with open(os.path.join(B.SAIDA, "resumo.json"), "w", encoding="utf-8") as f:
            json.dump(resumo, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(json.dumps({k: v for k, v in resumo.items() if k != "coordenadas"}, ensure_ascii=False, indent=1))
        print("coordenadas GERAL:", resumo["coordenadas"]["GERAL"])
        return resumo
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
