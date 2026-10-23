"""Nota de Serviço (NS) por upload: guarda os arquivos, casa cada segmento da NS com o trecho físico da obra e grava, por
linha da 06.1, o que a NS registra. Nada é gravado sem conferência humana: ler() só lê e mostra; registrar() grava o que
a pessoa conferiu, numa transação.

* TOPOGRAFIA: liberação topográfica só no que ainda não está liberado.
* CADASTRO: cadastro de campo só sobre o executado (assentado) até a data da nota; o resto é recusado, fica escrito no
  segmento e só entra à mão ("Aplicar de novo", aplicar()) se o assentamento até essa data for registrado depois.
* SERVICO: o plano do serviço da zona (PDF + croqui); não grava nada, mas cada trecho precisa estar liberado pela
  topografia até a data da nota (ordem obrigatória topografia → serviço → cadastro, D-20).
* EXECUCAO: a NS do dia (ver a seção "NS do dia" mais abaixo).
A 06.1 continua sendo a unidade do BM e da medição: o trecho físico (topologia.py) só converte metros da NS em metros de
cada linha. Pesquisa: docs/ns/01_NS_x_trechos_e_registros.md e docs/ns/03_armazenamento_e_upload.md.
"""
import base64
import binascii
import hashlib
import json
import re
from datetime import date

import compras as C
import ns_leitura as L
import regras as R
import relogio as RL
import servicos as S
import topologia as TP
from servicos import RegraViolada, _agora, _one, _rows, transacao

TIPOS = {"TOPOGRAFIA": "Topografia", "CADASTRO": "Cadastro de campo", "SERVICO": "Serviço de obra", "EXECUCAO": "Do dia (execução)"}
PERMISSAO_TIPO = {"TOPOGRAFIA": "topografia", "CADASTRO": "cadastro_campo"}      # além de notas_servico, para registrar
TOL_ABS, TOL_REL, LIM_REL = 0.10, 0.005, 0.05       # diferença NS × projeto: OK até max(0,10 m; 0,5 %); aviso até 5 %
LIMITE_CROQUI = 15 * 1024 * 1024
APLICADAS = ("AUTOMATICO", "CONFIRMADO")
RX_REDE = re.compile(r"^(?:NO\d|(?:VRP|VM|MV|DF|VTF|HID|RG)-\d)")
PAPEL = {"PONTA": "ponta", "JUNCAO": "junção (não é conexão)", "MEIO": "conexão no meio da linha"}


# ------------------------------------------------------------------ utilidades
def _bytes(conteudo_b64, rotulo, limite):
    if not conteudo_b64:
        raise RegraViolada(f"Envie {rotulo}.")
    try:
        dados = base64.b64decode(conteudo_b64, validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise RegraViolada(f"{rotulo[0].upper()}{rotulo[1:]}: arquivo inválido.") from None
    if not dados or len(dados) > limite:
        raise RegraViolada(f"{rotulo[0].upper()}{rotulo[1:]}: vazio ou maior que {limite // 2 ** 20} MB.")
    return dados


def chave_rede(nome):
    """Chave do elemento (NÓ9.1 → 'NO9.1') só quando é um elemento da rede (nó, VRP, VM, MV, DF, VTF, HID, RG)."""
    k = L.chave_elemento(nome)
    return k if k and RX_REDE.match(k) else None


def _zona_pb(nome):
    m = re.match(r"^(Zona\d\d|ADUTORA)_(PB\d\d)_", nome or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def _lugar(c):
    """'Zona03 PB08' (ou 'Zona03 PB05 e PB08') das linhas de um candidato."""
    zp = sorted({_zona_pb(p) for p in c["linhas"]} - {(None, None)})
    return " e ".join(f"{z} {pb}" for z, pb in zp) or "sem zona"


def _el(texto):
    """Elemento da NS sem a descrição: 'NÓ9.1 - TÊ 160x160' → 'NÓ9.1'; 'CH_VRP-15 (CAIXA DA VRP)' → 'CH_VRP-15'."""
    return re.split(r"\s+\(|\s+-\s+", str(texto or "").strip())[0] or "?"


def _curto(nome):
    return re.sub(r"^(Zona\d\d|ADUTORA)_PB\d\d_(Rede|CH|Adutora)_", "", nome or "")


def _m(v):
    return f"{v:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".") if v is not None else "—"


def _data_br(iso):
    return "/".join(reversed(str(iso or "")[:10].split("-")))


def referencia(numero, folhas):
    """Texto da NS gravado em cada registro: 'NS 012 fl. 01/01' (ou 'fl. 01–02/02')."""
    n = int(folhas or 1)
    return f"NS {numero} fl. {'01' if n == 1 else f'01–{n:02d}'}/{n:02d}"


def _diferenca_ok(ns_m, proj_m):
    dif = ns_m - proj_m
    return abs(dif) <= max(TOL_ABS, TOL_REL * proj_m)


def _nivel_diferenca(ns_m, proj_m):
    """OK (dentro da tolerância), AVISO (até 5 %) ou ERRO."""
    if _diferenca_ok(ns_m, proj_m):
        return "OK"
    return "AVISO" if abs(ns_m - proj_m) <= LIM_REL * proj_m else "ERRO"


# ------------------------------------------------------------------ casamento NS ↔ trecho físico
def indice(conn):
    """Onde cada elemento da rede aparece num trecho físico: {"chaves": {chave: [ponto]}, "meio": {fisico_id: [(pos, nó)]}},
    com a posição em metros (0 no no_ini do trecho físico) e o papel: PONTA (conexão real), JUNCAO (cruzamento, passagem,
    divisa, limite de MND: não é conexão) ou MEIO (conexão no meio de uma linha que a 06.1 não cortou, da pendência da
    topologia)."""
    fis = TP.trechos_fisicos(conn)
    por_ponto = {m["ponto"]: (F, m) for F in fis for m in F["membros"]}
    idx, meio = {}, {}

    def add(F, pos, nome, papel, **extra):
        k = chave_rede(nome)
        if papel == "MEIO":
            meio.setdefault(F["id"], []).append((round(float(pos), 3), nome))
        if k:
            idx.setdefault(k, []).append({"F": F, "pos": round(float(pos), 3), "nome": nome, "papel": papel, **extra})

    for F in fis:
        add(F, 0.0, F["no_ini"], "PONTA")
        add(F, F["extensao_m"], F["no_fim"], "PONTA")
        for j in F["juncoes"]:
            add(F, j["posicao_m"], j["no"], "JUNCAO")
    for p in TP.pendencias(conn):
        if p.get("tipo") == "CONEXAO_NO_MEIO_DA_LINHA" and p.get("trecho") in por_ponto and p.get("posicao_m") is not None:
            F, m = por_ponto[p["trecho"]]
            add(F, TP.para_fisico(F, m["trecho_id"], p["posicao_m"], p["posicao_m"])[0], p["no"], "MEIO", linha=p["trecho"],
                pos_linha=p["posicao_m"])
    return {"chaves": idx, "meio": meio}


def _no_contexto(pt, ctx):
    """O ponto vale para a zona/PB da NS: pelo prefixo do nome do nó ou pelas linhas do trecho físico (o nó pode estar
    desenhado na PB vizinha)."""
    z, pb = _zona_pb(pt["nome"])
    zonas = {z} | {_zona_pb(m["ponto"])[0] for m in pt["F"]["membros"]}
    pbs = {pb} | {_zona_pb(m["ponto"])[1] for m in pt["F"]["membros"]}
    return (not ctx.get("zona") or ctx["zona"] in zonas) and (not ctx.get("pb") or ctx["pb"] in pbs)


def _vaos(ind, ka, kb, ctx):
    """Candidatos para o trecho ka → kb da NS: o mesmo trecho físico tem os dois elementos (em posições diferentes)."""
    pa = [p for p in ind["chaves"].get(ka, ()) if _no_contexto(p, ctx)]
    pb = [p for p in ind["chaves"].get(kb, ()) if _no_contexto(p, ctx)]
    return [{"F": a["F"], "a": a, "b": b, "meio": ind["meio"].get(a["F"]["id"], ())} for a in pa for b in pb
            if a["F"] is b["F"] and abs(a["pos"] - b["pos"]) > R.TOL_M]


def _entre(c):
    """Pontos do trecho físico estritamente dentro do vão (junções e conexões no meio da linha que o segmento atravessa)."""
    x, y = sorted((c["a"]["pos"], c["b"]["pos"]))
    F = c["F"]
    out = [(j["posicao_m"], j["no"], "JUNCAO", j["tipo"]) for j in F["juncoes"] if x + R.TOL_M < j["posicao_m"] < y - R.TOL_M]
    return sorted(out + [(p[0], p[1], "MEIO", None) for p in c.get("meio", ()) if x + R.TOL_M < p[0] < y - R.TOL_M])


def _norm_zona_pb(zona, pb):
    """'3' / 'zona 3' → 'Zona03'; '8' / 'pb8' → 'PB08' (o formulário aceita do jeito que a pessoa escreve)."""
    z = re.search(r"\d+", str(zona or ""))
    p = re.search(r"\d+", str(pb or ""))
    zona = "ADUTORA" if "ADUTORA" in str(zona or "").upper() else (f"Zona{int(z.group()):02d}" if z else None)
    return zona, (f"PB{int(p.group()):02d}" if p else None)


def _contexto(ns, zona=None, pb=None):
    zona, pb = _norm_zona_pb(zona, pb)
    cab = ns["cabecalho"]
    ctx = L.contexto_zona_pb(cab.get("titulo"), cab.get("localizacao"))
    origem = "NS" if ctx["zona"] or ctx["pb"] else None
    if zona and not ctx["zona"]:
        ctx["zona"], origem = zona, "FORMULARIO"
    if pb and not ctx["pb"]:
        ctx["pb"], origem = pb, origem or "FORMULARIO"
    return dict(ctx, origem=origem)


def _no_meio(ls, k):
    return f"linha {k + 1} ({ls[k].get('elemento') or 'sem elemento'}) sem elemento da rede: tomada como ponto no meio"


def _fora(ls, k):
    return f"linha {k + 1} ({ls[k].get('elemento') or 'sem elemento'}) sem elemento da rede: fora dos segmentos"


def _soltas(ls, rec, gi, ctx_g):
    """NS do dia: a última linha sem elemento depois do último elemento é onde a execução parou; a primeira linha sem
    elemento antes do primeiro é de onde ela continuou (dia anterior). Cada uma vira um segmento com uma ponta só."""
    acc = lambda k: ls[k].get("dist_acumulada")
    out = []
    ini = next((k for k in range(rec[0]) if acc(k) is not None and acc(rec[0]) is not None and acc(k) < acc(rec[0]) - R.TOL_M), None)
    if ini is not None:
        out.append({"grupo": gi, "i": ini, "j": rec[0], "ka": None, "kb": chave_rede(ls[rec[0]]["elemento"]), "solta": "inicio",
                    "cands": [], "ctx": ctx_g, "avisos": [_fora(ls, k) for k in range(ini)] + [_no_meio(ls, k) for k in range(ini + 1, rec[0])]})
    fim = next((k for k in range(len(ls) - 1, rec[-1], -1) if acc(k) is not None and acc(rec[-1]) is not None
                and acc(k) > acc(rec[-1]) + R.TOL_M), None)
    if fim is not None:
        out.append({"grupo": gi, "i": rec[-1], "j": fim, "ka": chave_rede(ls[rec[-1]]["elemento"]), "kb": None, "solta": "fim",
                    "cands": [], "ctx": ctx_g, "avisos": [_no_meio(ls, k) for k in range(rec[-1] + 1, fim)]
                    + [_fora(ls, k) for k in range(fim + 1, len(ls))]})
    return out


def _segmentos_grupo(g, gi, ind, ctx, soltas=False):
    """Segmentos de um grupo: de um elemento reconhecido ao seguinte; linhas sem elemento reconhecido no meio viram
    ponto intermediário (aviso). Depois, segmentos que se encontram numa junção do mesmo trecho físico (cruzamento,
    divisa…) são juntados: a NS vai de conexão a conexão. Com `soltas` (NS do dia), a linha sem elemento no fim (parada)
    ou no começo (continuação) vira segmento de uma ponta só (_soltas)."""
    ls = g["linhas"]
    ctx_g = dict(ctx)
    cg = L.contexto_zona_pb(g.get("titulo"))
    ctx_g.update({k: v for k, v in cg.items() if v})
    rec = [k for k, l in enumerate(ls) if chave_rede(l.get("elemento"))]
    segs = []
    for i, j in zip(rec, rec[1:]):
        ka, kb = chave_rede(ls[i]["elemento"]), chave_rede(ls[j]["elemento"])
        segs.append({"grupo": gi, "i": i, "j": j, "ka": ka, "kb": kb, "cands": _vaos(ind, ka, kb, ctx_g),
                     "avisos": [_no_meio(ls, k) for k in range(i + 1, j)], "ctx": ctx_g})
    pontas = _soltas(ls, rec, gi, ctx_g) if soltas and rec else []
    if segs and not pontas:                        # linhas sem elemento antes do 1º ou depois do último: ficam de fora
        for k in [k for k in range(len(ls)) if k < rec[0] or k > rec[-1]]:
            (segs[0] if k < rec[0] else segs[-1])["avisos"].append(_fora(ls, k))
    mudou = True
    while mudou:
        mudou = False
        for n in range(len(segs) - 1):
            s1, s2 = segs[n], segs[n + 1]
            junta = []
            for c1 in s1["cands"]:
                for c2 in s2["cands"]:
                    if (c1["F"] is c2["F"] and c1["b"]["papel"] == "JUNCAO" and abs(c1["b"]["pos"] - c2["a"]["pos"]) <= R.TOL_M
                            and (c1["b"]["pos"] - c1["a"]["pos"]) * (c2["b"]["pos"] - c2["a"]["pos"]) > 0):
                        junta.append({"F": c1["F"], "a": c1["a"], "b": c2["b"], "meio": c1["meio"]})
            if junta:
                meio = ls[s1["j"]].get("elemento")
                segs[n] = {"grupo": gi, "i": s1["i"], "j": s2["j"], "ka": s1["ka"], "kb": s2["kb"], "cands": junta,
                           "avisos": s1["avisos"] + [f"{_curto(meio)} não é conexão (o tubo passa por ele): segmento juntado "
                                                     f"até {_curto(ls[s2['j']].get('elemento'))}"] + s2["avisos"],
                           "ctx": ctx_g}
                del segs[n + 1]
                mudou = True
                break
    return [p for p in pontas if p["solta"] == "inicio"] + segs + [p for p in pontas if p["solta"] == "fim"]


def _candidato(c, ns_m, de_mm):
    F = c["F"]
    x, y = c["a"]["pos"], c["b"]["pos"]
    proj = round(abs(y - x), 3)
    return {"fisico_id": F["id"], "ini_m": round(min(x, y), 3), "fim_m": round(max(x, y), 3), "sentido": 1 if y > x else -1,
            "extensao_m": proj, "extensao_fisico_m": F["extensao_m"], "de_mm": F["de_mm"], "metodologias": F["metodologias"],
            "diferenca_m": None if ns_m is None else round(ns_m - proj, 3), "de": c["a"]["nome"], "para": c["b"]["nome"],
            "texto": F["texto"], "linhas": [m["ponto"] for m in F["membros"]],
            "ponta_a": {k: c["a"].get(k) for k in ("nome", "papel", "linha", "pos_linha")},
            "ponta_b": {k: c["b"].get(k) for k in ("nome", "papel", "linha", "pos_linha")},
            "pontos_no_meio": [{"posicao_m": round(p - min(x, y), 3), "no": n, "papel": pp, "tipo": t} for p, n, pp, t in _entre(c)]}


def _conferir(c, ns_m, de_mm, metodo):
    """Situação de um candidato sozinho: (situação, motivo, avisos). DE ou método diferente e diferença acima de 5 % são
    ERRO; diferença entre 0,5 % e 5 % (ou NS sem distância) pede confirmação."""
    avisos = [f"{_curto(p['nome'])} é conexão no meio do {_curto(p['linha'])} (a {_m(p['pos_linha'])} m do início da linha): "
              "a 06.1 não corta ali, o intervalo vai até ela" for p in (c["ponta_a"], c["ponta_b"]) if p.get("papel") == "MEIO"]
    avisos += [f"passa por {_curto(p['no'])} (conexão no meio da linha, a {_m(p['posicao_m'])} m do início do segmento), "
               "que a NS não lista" for p in c["pontos_no_meio"] if p["papel"] == "MEIO"]
    if de_mm and int(c["de_mm"] or 0) != int(de_mm):
        return "ERRO", f"DE {de_mm} na NS × DE {int(c['de_mm'] or 0)} na 06.1", avisos
    if metodo and len(c["metodologias"]) == 1 and c["metodologias"][0] != metodo:
        return "ERRO", f"método {metodo} na NS × {c['metodologias'][0]} na 06.1", avisos
    if len(c["metodologias"]) > 1:
        avisos.append(f"o trecho físico tem partes em {' e '.join(c['metodologias'])}")
    if ns_m is None:
        return "CONFIRMAR", "a NS não tem a distância deste segmento", avisos
    nivel = _nivel_diferenca(ns_m, c["extensao_m"])
    dif = f"{_m(ns_m)} m na NS × {_m(c['extensao_m'])} m no projeto ({'+' if ns_m >= c['extensao_m'] else ''}{_m(ns_m - c['extensao_m'])} m)"
    if nivel == "OK":
        return "AUTOMATICO", None if abs(ns_m - c["extensao_m"]) < 0.005 else dif, avisos
    if nivel == "AVISO":
        return "CONFIRMAR", f"diferença acima de 0,5 %: {dif}", avisos
    return "ERRO", f"diferença acima de 5 %: {dif}", avisos


def _avaliar(s, ls, ns, conferir=_conferir):
    """Situação do segmento e o candidato escolhido (quando há um só). Cada candidato leva a própria situação: a pessoa
    só pode escolher um que não seja ERRO. `conferir`: a regra de distância (a NS do dia aceita execução parcial)."""
    a, b = ls[s["i"]], ls[s["j"]]
    ns_m = None if None in (a.get("dist_acumulada"), b.get("dist_acumulada")) else round(b["dist_acumulada"] - a["dist_acumulada"], 3)
    de_mm = b.get("dn_mm") or a.get("dn_mm")
    metodo = b.get("metodo")
    out = {"grupo": s["grupo"], "de": a.get("elemento"), "para": b.get("elemento"), "metros_ns": ns_m,
           "ini_ns_m": a.get("dist_acumulada"), "fim_ns_m": b.get("dist_acumulada"), "de_mm": de_mm, "metodo": metodo,
           "avisos": list(s["avisos"]), "candidatos": [], "escolhido": None}
    cands = s["cands"]
    if not cands:
        out.update(situacao="SEM_CORRESPONDENCIA", motivo=_sem_correspondencia(s))
        return out
    lista = [_candidato(c, ns_m, de_mm) for c in cands]
    for c in lista:
        c["situacao"], c["motivo"], c["avisos"] = conferir(c, ns_m, de_mm, metodo)
    out["candidatos"] = lista
    mesmo_de = [c for c in lista if not de_mm or int(c["de_mm"] or 0) == int(de_mm)]
    if de_mm and not mesmo_de:
        out.update(situacao="ERRO", motivo=f"DE {de_mm} na NS × DE {', '.join(sorted({str(int(c['de_mm'])) for c in lista}))} "
                                            "na 06.1")
        return out
    lista = mesmo_de
    if len(lista) > 1:
        lugares = sorted({_lugar(c) for c in lista})
        perto = [c for c in lista if ns_m is not None and _diferenca_ok(ns_m, c["extensao_m"])]
        if len(lugares) == 1 and len(perto) == 1:      # paralelos na mesma PB: a extensão separa
            out["avisos"].append(f"{len(lista)} trechos com as mesmas pontas; escolhido pela extensão ({_m(perto[0]['extensao_m'])} m)")
            lista = perto
        elif len(lugares) > 1:                          # o mesmo par de nós em outra PB: só a pessoa decide
            dica = f" (pela extensão, o de {_lugar(perto[0])})" if len(perto) == 1 else ""
            out.update(situacao="CONFIRMAR", motivo=f"{_curto(lista[0]['de'])} → {_curto(lista[0]['para'])} existe em "
                                                    f"{' e '.join(lugares)}: escolha o trecho{dica}")
            return out
        else:
            out.update(situacao="CONFIRMAR", motivo=f"{len(lista)} trechos com as mesmas pontas: escolha o trecho")
            return out
    c = out["escolhido"] = lista[0]
    out["avisos"] += c["avisos"]
    out.update(situacao=c["situacao"], motivo=c["motivo"])
    return out


def _sem_correspondencia(s):
    ka, kb = s["ka"], s["kb"]
    ctx = s["ctx"]
    onde = " e ".join(x for x in (ctx.get("zona"), ctx.get("pb")) if x) or "na obra"
    return (f"nenhum trecho físico {('da ' + onde) if onde != 'na obra' else 'da obra'} liga {ka} a {kb}"
            + ("" if ctx.get("zona") else " (informe a zona e a PB)"))


def casar(conn, ns, ctx, ind=None):
    """Segmentos da NS com a situação (AUTOMATICO, CONFIRMAR, ERRO, SEM_CORRESPONDENCIA), os candidatos e o escolhido."""
    ind = ind or indice(conn)
    out = []
    for gi, g in enumerate(ns["grupos"]):
        ls = g["linhas"]
        for s in _segmentos_grupo(g, gi, ind, ctx):
            seg = _avaliar(s, ls, ns)
            seg["ordem"] = len(out) + 1
            out.append(seg)
        if len(ls) > 1 and sum(1 for l in ls if chave_rede(l.get("elemento"))) < 2:
            out.append({"ordem": len(out) + 1, "grupo": gi, "de": ls[0].get("elemento"), "para": ls[-1].get("elemento"),
                        "metros_ns": None, "situacao": "SEM_CORRESPONDENCIA", "candidatos": [], "escolhido": None, "avisos": [],
                        "motivo": "o grupo não tem dois elementos da rede (nó, VRP, VM, MV, DF, VTF, HID) para ligar"})
    return out


# ------------------------------------------------------------------ prévia e gravação por linha da 06.1
def _fisico_salvo(seg):
    return {"id": seg["fisico_id"], "membros": json.loads(seg["membros"]) if isinstance(seg["membros"], str) else seg["membros"]}


def _cobertura_compl(conn, trecho_id, etapa):
    return R.unir_intervalos([(e["ini_m"], e["fim_m"]) for e in S.etapas_complementares(conn, trecho_id, etapa)])


def _faixas(lst):
    return [[round(a, 3), round(b, 3)] for a, b in lst if b - a > R.TOL_M]


def _historico(conn, seg_id, trecho_id, etapa):
    """Tudo o que o segmento já gravou nessa linha e etapa, inclusive o que depois foi anulado ou retificado: aplicar de
    novo nunca recria o que alguém tirou de propósito."""
    if seg_id is None:
        return []
    tab = "etapas_complementares" if etapa in ("LIBERACAO_TOPOGRAFICA", "ESCAVADO") else "intervalos_execucao"
    return R.unir_intervalos([tuple(r) for r in conn.execute(
        f"SELECT ini_m, fim_m FROM {tab} WHERE ns_segmento_id=? AND trecho_id=? AND etapa=?", (seg_id, trecho_id, etapa))])


def plano(conn, tipo, fisico, ini_m, fim_m, data, seg_id=None):
    """O que a NS gravaria em cada linha da 06.1 tocada pelo intervalo [ini_m, fim_m] do trecho físico:
    TOPOGRAFIA: liberação nas faixas ainda não liberadas; CADASTRO: levantamento sobre o assentado até a data ainda sem
    levantamento (o que não foi assentado fica pendente). Com `seg_id`, o que o segmento já gravou um dia (mesmo que
    depois anulado) fica de fora."""
    out = []
    for p in TP.para_linhas(fisico, ini_m, fim_m):
        faixa = (p["ini_m"], p["fim_m"])
        item = dict(p, gravar=[], ja_m=0.0, pendente=[])
        if tipo == "TOPOGRAFIA":
            cob = _cobertura_compl(conn, p["trecho_id"], "LIBERACAO_TOPOGRAFICA") + _historico(conn, seg_id, p["trecho_id"],
                                                                                              "LIBERACAO_TOPOGRAFICA")
            item["gravar"] = _faixas(R.fora_da_cobertura(faixa, R.unir_intervalos(cob)))
        elif tipo == "CADASTRO":
            ass = S._cobertura(conn, p["trecho_id"], "ASSENTADO", ate_data=data)
            cad = R.unir_intervalos(S._cobertura(conn, p["trecho_id"], "CADASTRO_CAMPO")
                                    + _historico(conn, seg_id, p["trecho_id"], "CADASTRO_CAMPO"))
            sobre = [(max(a, faixa[0]), min(b, faixa[1])) for a, b in ass if min(b, faixa[1]) - max(a, faixa[0]) > R.TOL_M]
            item["gravar"] = _faixas([x for s in sobre for x in R.fora_da_cobertura(s, cad)])
            item["pendente"] = _faixas([x for x in R.fora_da_cobertura(faixa, R.unir_intervalos(ass + cad))])
        item["ja_m"] = round(faixa[1] - faixa[0] - R.comprimento(item["gravar"]) - R.comprimento(item["pendente"]), 3)
        out.append(item)
    return out


def _aplicar_segmento(conn, ns, seg, por):
    """Grava o plano de um segmento (TOPOGRAFIA ou CADASTRO), uma linha da 06.1 por vez: uma recusa numa linha (avanço
    legado sem posição, trecho retirado) fica como pendência dela sem desfazer as outras. Devolve (gravado, pendente,
    motivos)."""
    ref = referencia(ns["numero"], ns["folhas"])
    gravado, pendente, motivos = 0.0, 0.0, []
    for item in plano(conn, ns["tipo"], _fisico_salvo(seg), seg["ini_fisico_m"], seg["fim_fisico_m"], ns["data"], seg["id"]):
        for a, b in item["gravar"]:
            try:
                with transacao(conn):
                    if ns["tipo"] == "TOPOGRAFIA":
                        S.registrar_etapa_complementar(conn, item["trecho_id"], "LIBERACAO_TOPOGRAFICA", a, b, ns["data"], por,
                                                       ref, None, ns_segmento_id=seg["id"])
                    else:
                        S.registrar_cadastro_campo(conn, item["trecho_id"], a, b, ns["data"], ref, por, ns_segmento_id=seg["id"])
                gravado += b - a
            except RegraViolada as e:
                pendente += b - a
                motivos.append(f"{_curto(item['ponto'])} {_m(a)}–{_m(b)} m: {e}")
        if item["pendente"]:
            pendente += R.comprimento(item["pendente"])
            motivos.append("recusado: " + R.falta_na_ordem(item["ponto"], item["pendente"], f"a execução até {_data_br(ns['data'])}",
                                                         "registre a NS do dia antes e use \"Aplicar de novo\""))
    return round(gravado, 3), round(pendente, 3), motivos


# ------------------------------------------------------------------ ler, registrar, aplicar, anular
def _ler_arquivos(conn, pdf_b64, planilha_b64=None, hoje=None):
    pdf = _bytes(pdf_b64, "o PDF da nota de serviço", L.LIMITE_PDF)
    planilha = _bytes(planilha_b64, "a planilha da nota de serviço", L.LIMITE_PLANILHA) if planilha_b64 else None
    try:
        ns = L.ler(pdf, S.contrato(conn), hoje or RL.hoje().isoformat(), planilha=planilha)
    except L.LeituraRecusada as e:
        raise RegraViolada(str(e)) from None
    return pdf, planilha, ns


def _cabeca(conn, ns_id):
    """A NS (vigente ou anulada) a que pertence uma versão substituída: segue quem a substituiu."""
    atual = _one(conn, "SELECT * FROM notas_servico WHERE id=?", ns_id)
    for _ in range(50):
        if not atual or atual["status"] != "SUBSTITUIDA":
            break
        atual = _one(conn, "SELECT * FROM notas_servico WHERE substitui_id=? ORDER BY id DESC LIMIT 1", atual["id"])
    return atual


def _ja_registrada(conn, ns, tipo, sha_pdf, equipe_id=None):
    """(o mesmo arquivo numa NS vigente, ainda que como versão substituída dela; a NS vigente de mesma chave). Chave:
    contrato, tipo e número; a NS do dia também pela equipe e pelo dia. Arquivo de NS anulada não bloqueia."""
    cab = ns["cabecalho"]
    com_arquivo = [r[0] for r in conn.execute("SELECT n.id FROM notas_servico n JOIN documentos d ON d.id = n.pdf_id "
                                              "WHERE d.sha256=? ORDER BY n.id DESC", (sha_pdf,))]
    por_arquivo = next((c for c in (_cabeca(conn, i) for i in com_arquivo) if c and c["status"] == "REGISTRADA"), None)
    sql = ("SELECT * FROM notas_servico WHERE contrato=? AND tipo=? AND numero=? AND status='REGISTRADA'"
           + (" AND equipe_id=? AND data=?" if tipo == "EXECUCAO" else ""))
    args = [L.norm_contrato(cab.get("contrato")) or "", tipo, str(cab.get("numero") or "")]
    mesma = _one(conn, sql, *(args + ([equipe_id, cab.get("data")] if tipo == "EXECUCAO" else [])))
    return por_arquivo, mesma


def _resumo_leitura(ns):
    cab = ns["cabecalho"]
    return {"numero": cab.get("numero"), "contrato": cab.get("contrato"), "data": cab.get("data"), "data_texto": cab.get("data_texto"),
            "folha": cab.get("folha"), "folhas": cab.get("total_folhas"), "localizacao": cab.get("localizacao"),
            "titulo": cab.get("titulo"), "bloco": cab.get("bloco"), "contratada": cab.get("contratada"),
            "assinaturas": ns.get("assinaturas"), "total_geral": ns.get("total_geral"),
            "grupos": [{"titulo": g["titulo"], "linhas": len(g["linhas"]), "dn_mm": g.get("dn_mm"), "extensao": g.get("extensao")}
                       for g in ns["grupos"]],
            "verificacoes": ns["verificacoes"], "resultado": ns["resultado"], "avisos": ns["avisos"],
            "fonte": {k: v for k, v in (ns.get("fonte") or {}).items() if k in ("extrator", "conferido_com", "paginas", "produtor")}}


def ler(conn, tipo, pdf_b64, planilha_b64=None, zona=None, pb=None, hoje=None, croqui_b64=None):
    """Só lê (não grava nada): a leitura e as contas da NS, o casamento de cada segmento com os trechos da obra, a prévia
    do que seria gravado por linha da 06.1 e a conferência do croqui."""
    if tipo not in TIPOS or tipo == "EXECUCAO":
        raise RegraViolada("Tipo de nota de serviço inválido (TOPOGRAFIA, CADASTRO ou SERVICO).")
    pdf, _, ns = _ler_arquivos(conn, pdf_b64, planilha_b64, hoje)
    ctx = _contexto(ns, zona, pb)
    segs = casar(conn, ns, ctx)
    data = ns["cabecalho"].get("data")
    for s in segs:
        for c in s["candidatos"]:
            c["plano"] = plano(conn, tipo, _fisico_por_id(conn, c["fisico_id"]), c["ini_m"], c["fim_m"], data) \
                if tipo in PERMISSAO_TIPO and data else []
        s["plano"] = s["escolhido"]["plano"] if s["escolhido"] else []
    por_arquivo, mesma = _ja_registrada(conn, ns, tipo, hashlib.sha256(pdf).hexdigest())
    aviso_tipo = None
    bloco = L.norm_txt(ns["cabecalho"].get("bloco"))
    if bloco and tipo in ("TOPOGRAFIA", "CADASTRO") and tipo not in bloco:
        aviso_tipo = f"o bloco da NS diz '{ns['cabecalho'].get('bloco')}' e o tipo escolhido é {TIPOS[tipo]}"
    return {"tipo": tipo, "leitura": _resumo_leitura(ns), "contexto": ctx, "segmentos": segs, "impressao": ns["impressao_dados"],
            "contrato_ok": L.norm_contrato(ns["cabecalho"].get("contrato")) == L.norm_contrato(S.contrato(conn)),
            "ja_registrada": por_arquivo and dict(por_arquivo, motivo="o mesmo arquivo já foi registrado"),
            "mesmo_numero": mesma and dict(mesma, mesma_impressao=mesma["impressao"] == ns["impressao_dados"]),
            "aviso_tipo": aviso_tipo, "avisos_croqui": _avisos_croqui(croqui_b64, ns)}


def _fisico_por_id(conn, fisico_id):
    F = next((F for F in TP.trechos_fisicos(conn) if F["id"] == fisico_id), None)
    if F is None:
        raise RegraViolada(f"Trecho físico {fisico_id} não existe mais (a topologia mudou): leia a NS de novo.")
    return F


def _guardar(conn, tipo_doc, dados, nome, por):
    sha = hashlib.sha256(dados).hexdigest()
    ja = _one(conn, "SELECT id, tipo FROM documentos WHERE sha256=?", sha)
    if ja and ja["tipo"] != tipo_doc:
        raise RegraViolada(f"Este arquivo já está guardado como outro tipo de documento ({ja['tipo']}).")
    return C.guardar_documento(conn, tipo_doc, base64.b64encode(dados).decode(), nome, por, C.documento_dir(conn))


def _croqui(conn, croqui_b64, nome, por):
    dados = _bytes(croqui_b64, "o croqui", LIMITE_CROQUI)
    ext, _ = C._tipo_arquivo(dados)
    if ext not in ("pdf", "jpg", "png"):
        raise RegraViolada("O croqui precisa ser PDF, JPG ou PNG (foto do celular vale).")
    return _guardar(conn, "NS_CROQUI", dados, nome, por)


def _avisos_croqui(croqui_b64, ns):
    """O croqui em PDF com texto é conferido com a nota (número, contrato e data escritos nele): só avisa."""
    return L.conferir_croqui(_bytes(croqui_b64, "o croqui", LIMITE_CROQUI), ns) if croqui_b64 else []


def _leitura_com_croqui(leitura_json, avisos):
    """A leitura guardada da NS com os avisos do croqui que ela tem agora."""
    leitura = json.loads(leitura_json or "{}")
    leitura.pop("avisos_croqui", None)
    if avisos:
        leitura["avisos_croqui"] = avisos
    return json.dumps(leitura, ensure_ascii=False, default=str)


def _decidir(segs, decisoes, por):
    """Aplica a conferência da pessoa: escolher o candidato (e aceitar a diferença) ou deixar de fora, com motivo.
    Só AUTOMATICO e CONFIRMADO gravam; ERRO e SEM_CORRESPONDENCIA só podem ficar de fora."""
    dec = {int(d["ordem"]): d for d in decisoes or [] if isinstance(d, dict) and d.get("ordem") is not None}
    faltam = []
    for s in segs:
        d = dec.get(s["ordem"])
        if d and d.get("acao") == "FORA":
            if not str(d.get("motivo") or "").strip():
                raise RegraViolada(f"Segmento {s['ordem']}: informe por que fica de fora.")
            s.update(situacao="FORA", motivo=str(d["motivo"]).strip(), confirmado_por=por)
            continue
        if s["situacao"] == "AUTOMATICO":
            continue
        if d and d.get("acao") == "ACEITAR" and s["situacao"] == "CONFIRMAR":
            esc = next((c for c in s["candidatos"] if c["fisico_id"] == d.get("fisico_id")), None) \
                if d.get("fisico_id") else s["escolhido"]
            if esc is None:
                raise RegraViolada(f"Segmento {s['ordem']}: escolha um dos trechos possíveis.")
            if esc.get("situacao") == "ERRO":
                raise RegraViolada(f"Segmento {s['ordem']}: o trecho escolhido não serve ({esc['motivo']}); escolha outro "
                                   "ou deixe de fora.")
            s.update(situacao="CONFIRMADO", escolhido=esc, confirmado_por=por, avisos=s["avisos"] + [
                a for a in esc.get("avisos") or [] if a not in s["avisos"]])
            continue
        faltam.append(str(s["ordem"]))
    if faltam:
        raise RegraViolada(f"Confira os segmentos {', '.join(faltam)}: escolha o trecho e aceite, ou deixe de fora com o motivo "
                           "(erro e sem correspondência só podem ficar de fora).")


def _inserir_ns(conn, tipo, ns, ctx, pdf_id, croqui_id, planilha_id, por, equipe_id=None, substitui_id=None):
    cab = ns["cabecalho"]
    if not cab.get("data"):
        raise RegraViolada("A NS não tem uma data válida.")
    ext = round(sum(g.get("extensao") or 0 for g in ns["grupos"]), 3)
    leitura = {k: ns[k] for k in ("cabecalho", "grupos", "notas", "resumo", "total_geral", "assinaturas", "avisos",
                                  "verificacoes", "resultado", "leitor")}
    leitura["fonte"] = {k: v for k, v in (ns.get("fonte") or {}).items() if k in ("extrator", "conferido_com", "paginas", "produtor")}
    if ns.get("avisos_croqui"):
        leitura["avisos_croqui"] = ns["avisos_croqui"]
    return conn.execute(
        """INSERT INTO notas_servico(tipo,contrato,numero,folhas,data,localizacao,titulo,zona,pb,equipe_id,pdf_id,croqui_id,
             planilha_id,impressao,leitura,extensao_m,status,substitui_id,registrada_por,registrada_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'REGISTRADA',?,?,?)""",
        (tipo, L.norm_contrato(cab.get("contrato")), str(cab.get("numero")), int(cab.get("total_folhas") or 1), cab["data"],
         cab.get("localizacao"), cab.get("titulo"), ctx.get("zona"), ctx.get("pb"), equipe_id, pdf_id, croqui_id, planilha_id,
         ns["impressao_dados"], json.dumps(leitura, ensure_ascii=False, default=str), ext, substitui_id, por, _agora())).lastrowid


def _inserir_segmento(conn, ns_id, s, por):
    e = s.get("escolhido")
    F = _fisico_por_id(conn, e["fisico_id"]) if e else None
    return conn.execute(
        """INSERT INTO ns_segmentos(ns_id,ordem,grupo,de,para,metros_ns,ini_ns_m,fim_ns_m,de_mm,metodo,fisico_id,membros,sentido,
             extensao_fisico_m,ini_fisico_m,fim_fisico_m,etapas,origem_sentido,situacao,motivo,candidatos,avisos,confirmado_por,
             confirmado_em,pendente_m,pendente)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ns_id, s["ordem"], s["grupo"], s.get("de"), s.get("para"), s.get("metros_ns"), s.get("ini_ns_m"), s.get("fim_ns_m"),
         s.get("de_mm"), s.get("metodo"), e and e["fisico_id"],
         json.dumps(F["membros"], ensure_ascii=False) if F else None, e and e["sentido"], F and F["extensao_m"],
         e and e["ini_m"], e and e["fim_m"], json.dumps(s["etapas"]) if s.get("etapas") else None, s.get("origem_sentido"),
         s["situacao"], s.get("motivo"),
         json.dumps([{k: c.get(k) for k in ("fisico_id", "ini_m", "fim_m", "sentido", "extensao_m", "de", "para", "texto",
                                            "situacao", "motivo")}
                     for c in s.get("candidatos") or []], ensure_ascii=False) or None,
         json.dumps(s.get("avisos") or [], ensure_ascii=False), s.get("confirmado_por"),
         _agora() if s.get("confirmado_por") else None, s.get("pendente_m") or 0, s.get("pendente"))).lastrowid


def _trocar_arquivo(conn, atual, novos, por):
    """Reenvio do mesmo conteúdo (por exemplo, a versão assinada) ou croqui depois: a versão anterior fica guardada como
    SUBSTITUIDA e a NS continua a mesma (os registros dela não mudam)."""
    cols = ",".join(r[1] for r in conn.execute("PRAGMA table_info(notas_servico)") if r[1] not in ("id", "status"))
    snap = conn.execute(f"INSERT INTO notas_servico({cols},status) SELECT {cols},'SUBSTITUIDA' FROM notas_servico WHERE id=?",
                        (atual["id"],)).lastrowid
    sets = ", ".join(f"{k}=?" for k in novos)
    conn.execute(f"UPDATE notas_servico SET {sets}, substitui_id=? WHERE id=?", (*novos.values(), snap, atual["id"]))
    return snap


def registrar(conn, tipo, pdf_b64, por, decisoes=None, croqui_b64=None, planilha_b64=None, nomes=None, zona=None, pb=None,
              hoje=None):
    """Grava a NS conferida: os arquivos, a NS, os segmentos e (TOPOGRAFIA e CADASTRO) os registros por linha da 06.1.
    Mesmo arquivo: recusa. Mesma NS (contrato, tipo, número) com a mesma impressão: troca só o arquivo. Com outra
    impressão: exige anular a anterior antes."""
    if tipo not in TIPOS or tipo == "EXECUCAO":
        raise RegraViolada("Tipo de nota de serviço inválido (TOPOGRAFIA, CADASTRO ou SERVICO).")
    nomes = nomes or {}
    pdf, planilha, ns = _ler_arquivos(conn, pdf_b64, planilha_b64, hoje)
    if not ns["resultado"]["aceita"]:
        raise RegraViolada("NS recusada: " + "; ".join(ns["resultado"]["motivos"][:4]))
    por_arquivo, mesma = _ja_registrada(conn, ns, tipo, hashlib.sha256(pdf).hexdigest())
    if por_arquivo:
        raise RegraViolada(f"Este arquivo já foi registrado: NS {por_arquivo['numero']} ({TIPOS.get(por_arquivo['tipo'])}), "
                           f"em {str(por_arquivo['registrada_em'])[:10]}.")
    if mesma and mesma["impressao"] != ns["impressao_dados"]:
        raise RegraViolada(f"A NS {mesma['numero']} já está registrada com outro conteúdo: anule a anterior (com o motivo) "
                           "antes de registrar a nova. Nada foi gravado.")
    if tipo == "SERVICO" and not croqui_b64 and not mesma:
        raise RegraViolada("A NS de serviço vai com o croqui (PDF, JPG ou PNG).")
    ns["avisos_croqui"] = _avisos_croqui(croqui_b64, ns)
    with transacao(conn):
        pdf_id = _guardar(conn, "NS_PDF", pdf, nomes.get("pdf"), por)
        croqui_id = _croqui(conn, croqui_b64, nomes.get("croqui"), por) if croqui_b64 else None
        planilha_id = _guardar(conn, "NS_PLANILHA", planilha, nomes.get("planilha"), por) if planilha else None
        if mesma:
            novos = {"pdf_id": pdf_id, **({"croqui_id": croqui_id, "leitura": _leitura_com_croqui(mesma["leitura"], ns["avisos_croqui"])}
                                          if croqui_id else {}),
                     **({"planilha_id": planilha_id} if planilha_id else {})}
            _trocar_arquivo(conn, mesma, novos, por)
            return {"id": mesma["id"], "arquivo_trocado": True, "segmentos": [], "gravado_m": 0.0, "pendente_m": 0.0,
                    "avisos_croqui": ns["avisos_croqui"]}
        ctx = _contexto(ns, zona, pb)
        segs = casar(conn, ns, ctx)
        _decidir(segs, decisoes, por)
        ns_id = _inserir_ns(conn, tipo, ns, ctx, pdf_id, croqui_id, planilha_id, por)
        reg = _one(conn, "SELECT * FROM notas_servico WHERE id=?", ns_id)
        out, falta = [], []
        for s in segs:
            sid = _inserir_segmento(conn, ns_id, s, por)
            r = {"ordem": s["ordem"], "id": sid, "situacao": s["situacao"], "gravado_m": 0.0, "pendente_m": 0.0, "pendencias": []}
            if tipo in PERMISSAO_TIPO and s["situacao"] in APLICADAS:
                seg = _one(conn, "SELECT * FROM ns_segmentos WHERE id=?", sid)
                r["gravado_m"], r["pendente_m"], r["pendencias"] = _aplicar_segmento(conn, reg, seg, por)
                _marcar(conn, sid, r)
            if tipo == "SERVICO" and s["situacao"] in APLICADAS:
                falta += _sem_liberacao(conn, _one(conn, "SELECT * FROM ns_segmentos WHERE id=?", sid), reg["data"])
            out.append(r)
        if falta:                                     # a transação desfaz tudo: nada é gravado
            raise RegraViolada("NS de serviço só sobre trecho liberado pela topografia até a data da nota. "
                               + "; ".join(falta[:6]) + (f"; e mais {len(falta) - 6}" if len(falta) > 6 else "") + ". Nada foi gravado.")
    return {"id": ns_id, "arquivo_trocado": False, "segmentos": out, "gravado_m": round(sum(r["gravado_m"] for r in out), 3),
            "pendente_m": round(sum(r["pendente_m"] for r in out), 3), "avisos_croqui": ns["avisos_croqui"]}


def _sem_liberacao(conn, seg, data):
    """O que o segmento da NS de serviço toca sem liberação topográfica até a data, uma mensagem por linha da 06.1."""
    out = []
    for p in TP.para_linhas(_fisico_salvo(seg), seg["ini_fisico_m"], seg["fim_fisico_m"]):
        falta = _faixas(R.fora_da_cobertura((p["ini_m"], p["fim_m"]), S.cobertura_liberacao(conn, p["trecho_id"], data)))
        if falta:
            out.append(R.falta_na_ordem(p["ponto"], falta, "a liberação topográfica", "registre a NS de topografia antes"))
    return out


def _marcar(conn, seg_id, r):
    """O aplicado é o que o segmento tem efetivo agora (um registro anulado deixa de contar)."""
    conn.execute("UPDATE ns_segmentos SET aplicado_m=?, pendente_m=?, pendente=? WHERE id=?",
                 (max(_lancado_seg(conn, seg_id).values(), default=0.0), r["pendente_m"], "; ".join(r["pendencias"]) or None, seg_id))


def _ns(conn, ns_id):
    ns = _one(conn, "SELECT * FROM notas_servico WHERE id=?", ns_id)
    if not ns:
        raise RegraViolada(f"Nota de serviço #{ns_id} não encontrada.")
    return ns


def aplicar(conn, ns_id, por):
    """"Aplicar de novo": grava a parte recusada que agora cabe (CADASTRO: o que foi assentado até a data da nota;
    qualquer tipo: o que uma recusa deixou de fora). Só à mão, nunca sozinho. Pode rodar de novo: só grava o que ainda
    falta (nunca duas vezes o mesmo pedaço)."""
    ns = _ns(conn, int(ns_id))
    if ns["status"] != "REGISTRADA":
        raise RegraViolada(f"NS {ns['numero']} está {ns['status'].lower()}: nada a aplicar.")
    if ns["tipo"] not in PERMISSAO_TIPO:
        raise RegraViolada("Só a NS de topografia e a de cadastro gravam registros por aqui.")
    out = []
    with transacao(conn):
        for seg in _rows(conn.execute(f"SELECT * FROM ns_segmentos WHERE ns_id=? AND situacao IN {APLICADAS} ORDER BY ordem",
                                      (ns["id"],))):
            g, p, m = _aplicar_segmento(conn, ns, seg, por)
            r = {"ordem": seg["ordem"], "id": seg["id"], "gravado_m": g, "pendente_m": p, "pendencias": m}
            _marcar(conn, seg["id"], r)
            out.append(r)
    return {"id": ns["id"], "segmentos": out, "gravado_m": round(sum(r["gravado_m"] for r in out), 3),
            "pendente_m": round(sum(r["pendente_m"] for r in out), 3)}


def anular(conn, ns_id, motivo, por):
    """Anula a NS e os registros dela (liberações anuladas; cadastros de campo e apontamentos retificados com lista vazia,
    com o mesmo motivo). Nada é apagado. Tudo ou nada: se um registro não pode ser anulado (por exemplo, um assentado de
    que um reaterro depende), nada muda."""
    ns = _ns(conn, int(ns_id))
    if ns["status"] != "REGISTRADA":
        raise RegraViolada(f"NS {ns['numero']} já está {ns['status'].lower()}.")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo da anulação.")
    motivo = f"NS {ns['numero']} anulada: {str(motivo).strip()}"
    segs = [r["id"] for r in conn.execute("SELECT id FROM ns_segmentos WHERE ns_id=?", (ns["id"],))]
    marcas = ",".join("?" * len(segs)) or "NULL"
    with transacao(conn):
        for e in _rows(conn.execute(f"SELECT id FROM etapas_complementares WHERE ns_segmento_id IN ({marcas}) AND anulado_em IS NULL",
                                    segs)):
            S.anular_etapa_complementar(conn, e["id"], motivo, por)
        for i in _rows(conn.execute(f"SELECT id FROM intervalos_execucao WHERE ns_segmento_id IN ({marcas}) AND {S.EFETIVO} "
                                    "AND apontamento_id IS NULL AND etapa='CADASTRO_CAMPO'", segs)):
            S.retificar_intervalos(conn, "CADASTRO_CAMPO", i["id"], [], motivo, por)
        aps = sorted({r[0] for r in conn.execute(        # o mais novo primeiro: o reaterro sai antes do assentado dele
            f"SELECT apontamento_id FROM intervalos_execucao WHERE ns_segmento_id IN ({marcas}) AND {S.EFETIVO} "
            "AND apontamento_id IS NOT NULL", segs)}, reverse=True)
        for ap in aps:
            S.retificar_intervalos(conn, "APONTAMENTO", ap, [], motivo, por)
        conn.execute("UPDATE notas_servico SET status='ANULADA', anulada_por=?, anulada_em=?, anulada_motivo=? WHERE id=?",
                     (por, _agora(), str(motivo), ns["id"]))
    return {"id": ns["id"], "apontamentos_anulados": len(aps)}


def anexar(conn, ns_id, croqui_b64, nome, por):
    """Croqui enviado depois (ou trocado): a versão anterior da NS fica guardada como SUBSTITUIDA."""
    ns = _ns(conn, int(ns_id))
    if ns["status"] != "REGISTRADA":
        raise RegraViolada(f"NS {ns['numero']} está {ns['status'].lower()}.")
    avisos = _avisos_croqui(croqui_b64, json.loads(ns["leitura"] or "{}"))
    with transacao(conn):
        cid = _croqui(conn, croqui_b64, nome, por)
        if cid == ns["croqui_id"]:
            raise RegraViolada("Este croqui já está na NS.")
        _trocar_arquivo(conn, ns, {"croqui_id": cid, "leitura": _leitura_com_croqui(ns["leitura"], avisos)}, por)
    return {"id": ns["id"], "croqui_id": cid, "avisos_croqui": avisos}


# ------------------------------------------------------------------ consulta
def _drive(conn, doc_ids):
    ids = [i for i in doc_ids if i]
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))
    return {r["ref_id"]: r for r in _rows(conn.execute(
        f"""SELECT ref_id, status, drive_link, pasta_link, caminho, ultimo_erro FROM envios_drive
            WHERE origem='DOCUMENTO' AND ref_id IN ({marcas})""", ids))}


def segmentos(conn, ns_id):
    out = []
    for s in _rows(conn.execute("SELECT * FROM ns_segmentos WHERE ns_id=? ORDER BY ordem", (ns_id,))):
        for k in ("candidatos", "avisos", "etapas"):
            s[k] = json.loads(s[k]) if s.get(k) else ([] if k != "etapas" else None)
        membros = json.loads(s.pop("membros")) if s.get("membros") else []
        s["linhas"] = TP.para_linhas({"membros": membros}, s["ini_fisico_m"], s["fim_fisico_m"]) if membros and s["ini_fisico_m"] is not None else []
        out.append(s)
    return out


def listar(conn, tipo=None, zona=None, vigentes=True, equipe=None, data=None, limite=200):
    """Notas recebidas, as mais novas primeiro, com o que cada uma gravou e o que ficou pendente."""
    sql, args = "SELECT * FROM notas_servico WHERE 1=1", []
    for cond, val in (("tipo=?", tipo), ("zona=?", zona), ("equipe_id=?", equipe), ("data=?", data)):
        if val:
            sql, args = f"{sql} AND {cond}", args + [val]
    if vigentes:
        sql += " AND status='REGISTRADA'"
    else:
        sql += " AND status<>'SUBSTITUIDA'"
    lista = _rows(conn.execute(sql + " ORDER BY data DESC, id DESC LIMIT ?", args + [int(limite)]))
    drive = _drive(conn, [i for n in lista for i in (n["pdf_id"], n["croqui_id"], n["planilha_id"])])
    for n in lista:
        n.pop("leitura", None)
        n["tipo_nome"] = TIPOS.get(n["tipo"], n["tipo"])
        n["referencia"] = referencia(n["numero"], n["folhas"])
        n["segmentos"] = _rows(conn.execute(
            "SELECT situacao, COUNT(*) AS n, SUM(aplicado_m) AS aplicado_m, SUM(pendente_m) AS pendente_m FROM ns_segmentos "
            "WHERE ns_id=? GROUP BY situacao", (n["id"],)))
        n["aplicado_m"] = round(sum(x["aplicado_m"] or 0 for x in n["segmentos"]), 3)
        n["pendente_m"] = round(sum(x["pendente_m"] or 0 for x in n["segmentos"]), 3)
        n["drive"] = {q: drive.get(n[f"{q}_id"]) for q in ("pdf", "croqui", "planilha") if n.get(f"{q}_id")}
    return lista


def detalhe(conn, ns_id):
    ns = _ns(conn, int(ns_id))
    ns["leitura"] = json.loads(ns["leitura"])
    ns["segmentos"] = segmentos(conn, ns["id"])
    ns["tipo_nome"] = TIPOS.get(ns["tipo"], ns["tipo"])
    ns["referencia"] = referencia(ns["numero"], ns["folhas"])
    versoes, sid = [], ns["substitui_id"]
    while sid and len(versoes) < 50:                  # a cadeia desta NS: cada versão aponta para a anterior
        v = _one(conn, "SELECT id, pdf_id, croqui_id, planilha_id, registrada_em, substitui_id, status FROM notas_servico "
                       "WHERE id=?", sid)
        if not v or v["status"] != "SUBSTITUIDA":
            break
        versoes.append(v)
        sid = v["substitui_id"]
    ns["versoes"] = versoes[::-1]
    return ns


def arquivo(conn, ns_id, qual):
    """(documento, nome para baixar) do PDF, croqui ou planilha da NS."""
    if qual not in ("pdf", "croqui", "planilha"):
        raise RegraViolada("Arquivo inválido (pdf, croqui ou planilha).")
    ns = _ns(conn, int(ns_id))
    doc = _one(conn, "SELECT * FROM documentos WHERE id=?", ns[f"{qual}_id"]) if ns[f"{qual}_id"] else None
    if not doc:
        raise RegraViolada(f"A NS {ns['numero']} não tem {qual}.")
    ext = doc["arquivo"].rsplit(".", 1)[-1]
    rot = {"pdf": "", "croqui": " - croqui", "planilha": " - planilha"}[qual]
    return ns, doc, f"NS {ns['numero']}{rot}.{ext}"


# ------------------------------------------------------------------ NS do dia (EXECUCAO): o que a equipe executou
# A equipe envia a NS com o que foi executado e o croqui; o sistema lança sozinho o que é inequívoco, como execução
# INFORMADA (amarela no mapa, sem verificação), e o resto vai, sem gravar, para a fila "NS do dia a conferir".
ETAPAS_DIA = {"ASSENTADO": ("ASSENT",), "REATERRADO": ("REATERR",), "ESCAVADO": ("ESCAV", "VALA ABERTA")}
ROT_ETAPA = {"ASSENTADO": "assentado", "REATERRADO": "reaterrado", "ESCAVADO": "escavado"}
FILA = ("CONFIRMAR", "ERRO", "SEM_CORRESPONDENCIA")
ATRASO_DIAS = 3
SEM_ETAPA = "a NS não diz a etapa: considerado assentamento"
ORIGEM = {"NS": "da própria NS", "PROGRAMACAO": "da programação do dia da equipe", "NS_SERVICO": "da NS de serviço da zona",
          "ENGENHARIA": "escolhido pela engenharia"}


def etapas_do_texto(*textos):
    """Etapas escritas na NS do dia (título da NS, título do grupo, observações): ASSENT… → ASSENTADO, REATERR… →
    REATERRADO, ESCAV… ou VALA ABERTA → ESCAVADO. Mais de uma palavra, mais de uma etapa."""
    t = " ".join(L.norm_txt(x) for x in textos if x)
    return [e for e, chaves in ETAPAS_DIA.items() if any(re.search(rf"\b{k}", t) for k in chaves)]


def estaca(m):
    """122.01 → '6+2,01' (estaca de 20 m + fração, como na NS)."""
    if m is None:
        return "?"
    i = int(round(m, 2) // 20)
    return f"{i}+{_m(round(m - 20 * i, 2))}"


def _chaves_texto(texto):
    """Elementos da rede citados num texto livre: 'REDE … (NÓ6.1 - NÓ9.1 - VRP-15)' → ['NO6.1', 'NO9.1', 'VRP-15']."""
    return [k for k in (chave_rede(p) for p in re.split(r"\s+-\s+|[(),;/]|->|→", texto or "")) if k]


def _conferir_dia(c, ns_m, de_mm, metodo):
    """NS do dia: distância menor que a do projeto é execução parcial, a partir do elemento de menor estaca, no sentido
    do outro (não é erro); maior, além da tolerância, vai para a engenharia (até 5 %: aceitar a diferença; acima: erro)."""
    sit, motivo, avisos = _conferir(c, None, de_mm, metodo)          # DE e método
    if sit == "ERRO" or ns_m is None:
        return sit, motivo, avisos
    proj = c["extensao_m"]
    if _diferenca_ok(ns_m, proj) or ns_m > proj:
        return _conferir(c, ns_m, de_mm, metodo)
    x = c["ini_m"] if c["sentido"] == 1 else c["fim_m"]
    c["ini_m"], c["fim_m"] = (x, round(x + ns_m, 3)) if c["sentido"] == 1 else (round(x - ns_m, 3), x)
    c["executado_m"] = ns_m
    return "AUTOMATICO", f"execução parcial: {_m(ns_m)} de {_m(proj)} m, a partir do {_curto(c['de'])}", avisos


def _programados(conn, equipe_id, data):
    """Linhas da 06.1 programadas para a equipe no dia (Dados da obra ou Programação), menos as canceladas."""
    return {r[0] for r in conn.execute("SELECT alvo_id FROM programacoes WHERE equipe_id=? AND data=? AND alvo_tipo='TRECHO' "
                                        "AND status <> 'CANCELADA'", (equipe_id, data))}


def _servico_zona(conn, zona):
    """Intervalos dos trechos físicos da NS de serviço vigente da zona: (fisico_id, ini, fim)."""
    if not zona:
        return []
    return [tuple(r) for r in conn.execute(
        """SELECT s.fisico_id, s.ini_fisico_m, s.fim_fisico_m FROM ns_segmentos s JOIN notas_servico n ON n.id = s.ns_id
           WHERE n.tipo='SERVICO' AND n.status='REGISTRADA' AND n.zona=? AND s.situacao IN ('AUTOMATICO','CONFIRMADO')
             AND s.fisico_id IS NOT NULL""", (zona,))]


def _avaliar_solta(s, g, ns, ind, fontes, vizinho=None):
    """Segmento de uma ponta só (a execução parou numa estaca sem elemento, ou continuou de uma): vai do elemento até a
    estaca. Para que lado, nesta ordem: o trecho físico em que a NS já vinha (o elemento é cruzamento ou conexão no meio
    dele), outro elemento citado no título ou nas observações, a programação do dia da equipe, a NS de serviço da zona;
    senão, a engenharia escolhe (CONFIRMAR). Nunca volta sobre o trecho do segmento vizinho (`vizinho`: o anterior, na
    parada; o seguinte, na continuação)."""
    ls, fim = g["linhas"], s["solta"] == "fim"
    a, b = ls[s["i"]], ls[s["j"]]
    el, solta = (a, b) if fim else (b, a)
    chave = s["ka"] if fim else s["kb"]
    d = None if None in (a.get("dist_acumulada"), b.get("dist_acumulada")) else round(b["dist_acumulada"] - a["dist_acumulada"], 3)
    de_mm, metodo = solta.get("dn_mm") or el.get("dn_mm"), solta.get("metodo") or el.get("metodo")
    rot = lambda l: l.get("elemento") or f"estaca {estaca(l.get('dist_acumulada'))}"
    out = {"grupo": s["grupo"], "de": rot(a), "para": rot(b), "metros_ns": d, "ini_ns_m": a.get("dist_acumulada"),
           "fim_ns_m": b.get("dist_acumulada"), "de_mm": de_mm, "metodo": metodo, "candidatos": [], "escolhido": None,
           "solta": s["solta"], "avisos": list(s["avisos"]) + [
               f"a execução {'parou na' if fim else 'continuou da'} estaca {estaca(solta.get('dist_acumulada'))} (sem elemento)"]}
    pontos = [p for p in ind["chaves"].get(chave, ()) if _no_contexto(p, s["ctx"])]
    if not pontos or d is None:
        out.update(situacao="SEM_CORRESPONDENCIA", motivo=f"{_el(el.get('elemento'))} não está nos trechos da "
                   f"{' '.join(x for x in (s['ctx'].get('zona'), s['ctx'].get('pb')) if x) or 'obra'}" if not pontos
                   else "a linha sem elemento não tem a distância")
        return out
    cands, lado_de = [], []
    for p in pontos:
        F = p["F"]
        for lado in (1, -1):
            folga = F["extensao_m"] - p["pos"] if lado == 1 else p["pos"]
            if folga <= R.TOL_M:
                continue
            x0, x1 = sorted((p["pos"], p["pos"] + lado * min(d, folga)))
            prox = F["no_fim"] if lado == 1 else F["no_ini"]
            c = {"fisico_id": F["id"], "ini_m": round(x0, 3), "fim_m": round(x1, 3), "sentido": lado if fim else -lado,
                 "extensao_m": round(folga, 3), "extensao_fisico_m": F["extensao_m"], "executado_m": d, "diferenca_m": None,
                 "de_mm": F["de_mm"], "metodologias": F["metodologias"], "de": p["nome"], "para": prox, "texto": F["texto"],
                 "linhas": [m["ponto"] for m in F["membros"]], "situacao": "AUTOMATICO", "motivo": None, "avisos": []}
            if d > folga + max(TOL_ABS, TOL_REL * folga):
                c.update(situacao="ERRO", motivo=f"a NS passa do fim do trecho: {_m(d)} m na NS × {_m(folga)} m até "
                                                 f"{_curto(prox)} (falta o elemento seguinte na NS)")
            elif de_mm and int(F["de_mm"] or 0) != int(de_mm):
                c.update(situacao="ERRO", motivo=f"DE {de_mm} na NS × DE {int(F['de_mm'] or 0)} na 06.1")
            elif metodo and len(F["metodologias"]) == 1 and F["metodologias"][0] != metodo:
                c.update(situacao="ERRO", motivo=f"método {metodo} na NS × {F['metodologias'][0]} na 06.1")
            elif d > folga:
                c["avisos"].append(f"chegou ao {_curto(prox)} (a NS não lista)")
            ev = (vizinho or {}).get("escolhido")
            if ev and ev["fisico_id"] == F["id"] and min(ev["fim_m"], c["fim_m"]) - max(ev["ini_m"], c["ini_m"]) > R.TOL_M:
                c.update(situacao="ERRO", motivo="é o trecho do segmento ao lado (a execução não volta sobre ele)")
            cands.append(c)
            lado_de.append((F, p["pos"], lado))
    out["candidatos"] = cands
    validos = [k for k, c in enumerate(cands) if c["situacao"] != "ERRO"]
    if not validos:
        out.update(situacao="ERRO", motivo=cands[0]["motivo"] if cands else "nenhum trecho sai do elemento")
        return out
    filtros = []
    e = (vizinho or {}).get("escolhido")
    if e:                               # a NS vinha (ou segue) num trecho físico que passa pelo elemento: o mesmo, no mesmo sentido
        filtros.append(("NS", lambda k: cands[k]["fisico_id"] == e["fisico_id"] and cands[k]["sentido"] == e["sentido"]))
    andados = {chave_rede(l.get("elemento")) for n, l in enumerate(ls) if (n <= s["i"] if fim else n >= s["j"])}
    citados = (set(_chaves_texto(g.get("titulo")) + _chaves_texto(ns["cabecalho"].get("titulo")) + _chaves_texto(solta.get("obs")))
               - andados - {None})
    if citados:                         # outro elemento citado: o lado em que ele está
        filtros.append(("NS", lambda k: any(q["F"] is lado_de[k][0] and (q["pos"] - lado_de[k][1]) * lado_de[k][2] > R.TOL_M
                                            for kk in citados for q in ind["chaves"].get(kk, ()))))
    filtros.append(("PROGRAMACAO", lambda k: bool(fontes["programados"] & {x["trecho_id"] for x in TP.para_linhas(
        lado_de[k][0], cands[k]["ini_m"], cands[k]["fim_m"])})))
    filtros.append(("NS_SERVICO", lambda k: any(f == cands[k]["fisico_id"] and min(y, cands[k]["fim_m"]) - max(x, cands[k]["ini_m"])
                                                > R.TOL_M for f, x, y in fontes["servico"])))
    escolha, origem = (validos[0], "NS") if len(validos) == 1 else (None, None)
    for org, f in ([] if escolha is not None else filtros):
        sel = [k for k in validos if f(k)]
        if len(sel) == 1:
            escolha, origem = sel[0], org
            break
    if escolha is None:
        out.update(situacao="CONFIRMAR", motivo=f"a NS não diz para que lado a execução {'seguiu depois do' if fim else 'veio até o'} "
                   f"{_el(el.get('elemento'))} ({len(validos)} trechos possíveis, sem programação do dia que decida): escolha o trecho")
        return out
    c = out["escolhido"] = cands[escolha]
    out["avisos"] += c["avisos"] + ([f"sentido {ORIGEM[origem]}"] if origem != "NS" else [])
    out.update(situacao="AUTOMATICO", motivo=None, origem_sentido=origem)
    return out


def casar_dia(conn, ns, ctx, equipe_id, data, ind=None):
    """Segmentos da NS do dia: o casamento das outras NS (elemento a elemento, com junção e conexão no meio da linha),
    a execução parcial e as pontas soltas (_avaliar_solta), e as etapas de cada segmento."""
    ind = ind or indice(conn)
    fontes = {"programados": _programados(conn, equipe_id, data), "servico": _servico_zona(conn, ctx.get("zona"))}
    titulo, out = ns["cabecalho"].get("titulo"), []
    for gi, g in enumerate(ns["grupos"]):
        ls = g["linhas"]
        segs = _segmentos_grupo(g, gi, ind, ctx, soltas=True)
        avals = [None if s.get("solta") else dict(_avaliar(s, ls, ns, _conferir_dia), origem_sentido="NS") for s in segs]
        for k, s in enumerate(segs):                  # as pontas soltas depois, conhecendo o segmento vizinho
            if s.get("solta"):
                viz = avals[k - 1] if s["solta"] == "fim" and k else avals[k + 1] if s["solta"] == "inicio" and k + 1 < len(segs) else None
                avals[k] = _avaliar_solta(s, g, ns, ind, fontes, viz)
        for s, seg in zip(segs, avals):
            i0 = s["i"] if s["i"] == 0 else s["i"] + 1                      # observações das estacas que o segmento alcança
            seg["etapas"] = etapas_do_texto(titulo, g.get("titulo"), *[ls[k].get("obs") for k in range(i0, s["j"] + 1)])
            if not seg["etapas"]:
                seg["etapas"], seg["avisos"] = ["ASSENTADO"], seg["avisos"] + [SEM_ETAPA]
            seg["ordem"] = len(out) + 1
            out.append(seg)
        if ls and not any(chave_rede(l.get("elemento")) for l in ls):
            out.append({"ordem": len(out) + 1, "grupo": gi, "de": ls[0].get("elemento"), "para": ls[-1].get("elemento"),
                        "metros_ns": None, "situacao": "SEM_CORRESPONDENCIA", "candidatos": [], "escolhido": None, "avisos": [],
                        "etapas": None, "motivo": "o grupo não tem elemento da rede (nó, VRP, VM, MV, DF, VTF, HID) para "
                                                  "localizar a execução"})
    return out


def _intersec(a_lst, b_lst):
    return [(max(a, x), min(b, y)) for a, b in a_lst for x, y in b_lst if min(b, y) - max(a, x) > R.TOL_M]


def _proprios(conn, seg_id, trecho_id, etapa):
    """Cobertura que o próprio segmento já lançou (para não contar como 'já estava lançado' ao repetir)."""
    if seg_id is None:
        return []
    if etapa == "ESCAVADO":
        sql = "SELECT ini_m, fim_m FROM etapas_complementares WHERE ns_segmento_id=? AND trecho_id=? AND etapa=? AND anulado_em IS NULL"
    else:
        sql = f"SELECT ini_m, fim_m FROM intervalos_execucao WHERE ns_segmento_id=? AND trecho_id=? AND etapa=? AND {S.EFETIVO}"
    return R.unir_intervalos([tuple(r) for r in conn.execute(sql, (seg_id, trecho_id, etapa))])


def plano_dia(conn, fisico, ini_m, fim_m, etapas, data, seg_id=None):
    """O que a NS do dia lança em cada linha da 06.1 tocada por [ini_m, fim_m]: por etapa, só o que ainda não está
    lançado (o resto conta como 'já estava'); reaterro só sobre o assentado até a data (o de antes ou o desta NS); no
    pedaço MND, escavação e reaterro não se aplicam (pulados, com aviso)."""
    out = []
    for p in TP.para_linhas(fisico, ini_m, fim_m):
        tid, faixa = p["trecho_id"], (p["ini_m"], p["fim_m"])
        mnd = (_one(conn, "SELECT metodologia FROM trechos WHERE id=?", tid) or {}).get("metodologia") == "MND"
        item = dict(p, mnd=mnd, gravar={e: [] for e in ETAPAS_DIA}, ja={e: 0.0 for e in ETAPAS_DIA}, pulado=[], sem_assentado=[])
        novo_ass = []
        for e in ETAPAS_DIA:
            if e not in etapas:
                continue
            if mnd and e != "ASSENTADO":
                item["pulado"].append(e)
                continue
            todos = _cobertura_compl(conn, tid, e) if e == "ESCAVADO" else S._cobertura(conn, tid, e)
            livre = R.fora_da_cobertura(faixa, R.unir_intervalos(todos + _historico(conn, seg_id, tid, e)))
            if e == "REATERRADO":
                base = R.unir_intervalos(S._cobertura(conn, tid, "ASSENTADO", ate_data=data) + novo_ass)
                item["sem_assentado"] = _faixas([x for f in livre for x in R.fora_da_cobertura(f, base)])
                livre = _intersec(livre, base)
            item["gravar"][e] = _faixas(livre)
            if e == "ASSENTADO":
                novo_ass = [tuple(x) for x in item["gravar"][e]]
            coberto = faixa[1] - faixa[0] - R.comprimento(R.fora_da_cobertura(faixa, todos))
            item["ja"][e] = round(max(coberto - R.comprimento(_intersec([faixa], _proprios(conn, seg_id, tid, e))), 0.0), 3)
        out.append(item)
    return out


def _lancado_seg(conn, seg_id):
    """{etapa: metros} que o segmento tem lançados (registros efetivos)."""
    out = dict(conn.execute(f"SELECT etapa, SUM(fim_m - ini_m) FROM intervalos_execucao WHERE ns_segmento_id=? AND {S.EFETIVO} "
                            "GROUP BY etapa", (seg_id,)))
    out.update(conn.execute("SELECT etapa, SUM(fim_m - ini_m) FROM etapas_complementares WHERE ns_segmento_id=? "
                            "AND anulado_em IS NULL GROUP BY etapa", (seg_id,)))
    return {k: round(v, 3) for k, v in out.items() if v}


def _lancar_segmento(conn, ns, seg, por):
    """Lança um segmento conferido (AUTOMATICO ou CONFIRMADO) numa transação própria (SAVEPOINT): um apontamento por
    linha da 06.1 (assentado e reaterro) e a escavação como etapa complementar. Uma recusa manda só este segmento
    para a fila, com o motivo. Informado por quem enviou a NS."""
    etapas = json.loads(seg["etapas"]) if seg["etapas"] else ["ASSENTADO"]
    plano = plano_dia(conn, _fisico_salvo(seg), seg["ini_fisico_m"], seg["fim_fisico_m"], etapas, ns["data"], seg["id"])
    ref = referencia(ns["numero"], ns["folhas"])
    ini, fim = seg["ini_ns_m"], seg["fim_ns_m"]
    if ini is not None and fim is not None and ini > fim:
        ini, fim = fim, ini
    est = (f"NS {ns['numero']} · {estaca(ini)}", estaca(fim))           # "NS 015 · 0+0,00" a "6+2,01"
    quem = ns["registrada_por"]
    lancado, pendente = [], None
    try:
        with transacao(conn):
            for item in plano:
                novos = [{"etapa": e, "ini_m": a, "fim_m": b, "referencia": ref, "ns_segmento_id": seg["id"]}
                         for e in ("ASSENTADO", "REATERRADO") for a, b in item["gravar"][e]]
                if novos:
                    S.apontar(conn, ns["data"], ns["equipe_id"], "TRECHO", item["trecho_id"], estaca_ini=est[0], estaca_fim=est[1],
                              intervalos_novos=novos, informado_por=quem)
                for a, b in item["gravar"]["ESCAVADO"]:
                    S.registrar_etapa_complementar(conn, item["trecho_id"], "ESCAVADO", a, b, ns["data"], quem, ref, None,
                                                   ns_segmento_id=seg["id"])
                lancado += [{"ponto": item["ponto"], "etapa": e, "ini_m": a, "fim_m": b} for e in ETAPAS_DIA for a, b in item["gravar"][e]]
    except RegraViolada as e:
        lancado, pendente = [], f"não lançado: {e}"
    sem = [(item["ponto"], f) for item in plano for f in item["sem_assentado"]]
    if not pendente and sem:
        pendente = (f"reaterro sem assentamento lançado até {_data_br(ns['data'])}: "
                    + ", ".join(f"{_curto(pt)} {_m(a)}–{_m(b)} m" for pt, (a, b) in sem))
    feito = _lancado_seg(conn, seg["id"])
    pendente_m = 0.0 if not pendente else (sum(b - a for _, (a, b) in sem) if not pendente.startswith("não lançado")
                                           else (seg["fim_fisico_m"] or 0) - (seg["ini_fisico_m"] or 0))
    return {"ordem": seg["ordem"], "id": seg["id"], "lancado": lancado, "pendente": pendente, "pendente_m": round(pendente_m, 3),
            "aplicado_m": max(feito.values(), default=0.0), "feito": feito,
            "ja": {e: round(sum(i["ja"][e] for i in plano), 3) for e in ETAPAS_DIA if sum(i["ja"][e] for i in plano) > R.TOL_M},
            "pulado": sorted({f"{_curto(i['ponto'])} é MND (sem vala): {' e '.join(ROT_ETAPA[e] for e in i['pulado'])} não se "
                              f"aplica{'m' if len(i['pulado']) > 1 else ''}; o assentado vale" for i in plano if i["pulado"]})}


def registrar_dia(conn, ns_id, por):
    """Lança o que está conferido na NS do dia (AUTOMATICO e CONFIRMADO), um SAVEPOINT por segmento. Pode ser chamada de
    novo (a engenharia, depois de resolver a fila): só lança o que ainda falta, nunca duas vezes o mesmo pedaço."""
    ns = _ns(conn, int(ns_id))
    if ns["tipo"] != "EXECUCAO":
        raise RegraViolada("Só a NS do dia lança a execução.")
    if ns["status"] != "REGISTRADA":
        raise RegraViolada(f"NS {ns['numero']} está {ns['status'].lower()}.")
    out = []
    with transacao(conn):
        for seg in _rows(conn.execute(f"SELECT * FROM ns_segmentos WHERE ns_id=? AND situacao IN {APLICADAS} ORDER BY ordem",
                                      (ns["id"],))):
            r = _lancar_segmento(conn, ns, seg, por)
            conn.execute("UPDATE ns_segmentos SET aplicado_m=?, pendente_m=?, pendente=? WHERE id=?",
                         (r["aplicado_m"], r["pendente_m"], r["pendente"], seg["id"]))
            out.append(r)
    return out


def _clima_do_dia(conn, data, equipe_id, clima):
    """O clima é o único toque da tela de envio: a NS não traz o clima e o apontamento exige manhã e tarde."""
    for turno in ("MANHA", "TARDE"):
        if (clima or {}).get(turno):
            S.registrar_clima(conn, data, equipe_id, turno, clima[turno])
    turnos = {r[0] for r in conn.execute("SELECT turno FROM clima WHERE data=? AND equipe_id=?", (data, equipe_id))}
    if turnos != {"MANHA", "TARDE"}:
        raise RegraViolada(f"Informe o clima da manhã e da tarde de {_data_br(data)}: o diário precisa dele.")


def enviar_dia(conn, equipe_id, pdf_b64, croqui_b64, por, planilha_b64=None, nomes=None, clima=None, hoje=None):
    """A NS do dia enviada pela equipe (ou em nome dela): lê, recusa o que não é desta obra, o PDF sem texto e a data
    futura, guarda os arquivos e a NS, casa os segmentos e lança sozinho o que é inequívoco (registrar_dia)."""
    if not equipe_id or not _one(conn, "SELECT 1 FROM equipes WHERE id=?", equipe_id):
        raise RegraViolada("Escolha a equipe da nota do dia.")
    nomes = nomes or {}
    pdf, planilha, ns = _ler_arquivos(conn, pdf_b64, planilha_b64, hoje)
    if not ns["resultado"]["aceita"]:
        raise RegraViolada("NS recusada: " + "; ".join(ns["resultado"]["motivos"][:4]))
    cab = ns["cabecalho"]
    por_arquivo, mesma = _ja_registrada(conn, ns, "EXECUCAO", hashlib.sha256(pdf).hexdigest(), equipe_id)
    if por_arquivo:
        raise RegraViolada(f"Esta NS já foi enviada: NS {por_arquivo['numero']} ({TIPOS.get(por_arquivo['tipo'])}"
                           f"{', equipe ' + por_arquivo['equipe_id'] if por_arquivo['equipe_id'] else ''}, {_data_br(por_arquivo['data'])}).")
    if mesma and mesma["impressao"] != ns["impressao_dados"]:
        raise RegraViolada(f"A NS {mesma['numero']} desta equipe em {_data_br(mesma['data'])} já foi enviada com outro conteúdo: "
                           "anule o envio anterior (com o motivo) antes de enviar o novo. Nada foi gravado.")
    if not croqui_b64 and not mesma:
        raise RegraViolada("Envie o croqui junto com a nota (PDF, JPG ou PNG; foto do celular vale).")
    ns["avisos_croqui"] = _avisos_croqui(croqui_b64, ns)
    with transacao(conn):
        _clima_do_dia(conn, cab["data"], equipe_id, clima)
        pdf_id = _guardar(conn, "NS_PDF", pdf, nomes.get("pdf"), por)
        croqui_id = _croqui(conn, croqui_b64, nomes.get("croqui"), por) if croqui_b64 else None
        planilha_id = _guardar(conn, "NS_PLANILHA", planilha, nomes.get("planilha"), por) if planilha else None
        if mesma:
            _trocar_arquivo(conn, mesma, {"pdf_id": pdf_id, **({"croqui_id": croqui_id, "leitura": _leitura_com_croqui(
                mesma["leitura"], ns["avisos_croqui"])} if croqui_id else {}), **({"planilha_id": planilha_id} if planilha_id else {})}, por)
            return dict(resumo_dia(conn, mesma["id"]), arquivo_trocado=True)
        zona = equipe_id if re.fullmatch(r"Zona\d\d|ADUTORA", equipe_id) else None
        ctx = _contexto(ns, zona)
        if ctx["origem"] == "FORMULARIO":
            ctx["origem"] = "EQUIPE"
        segs = casar_dia(conn, ns, ctx, equipe_id, cab["data"])
        ns_id = _inserir_ns(conn, "EXECUCAO", ns, ctx, pdf_id, croqui_id, planilha_id, por, equipe_id=equipe_id)
        for s in segs:
            _inserir_segmento(conn, ns_id, s, por)
        lancamento = registrar_dia(conn, ns_id, por)
    return dict(resumo_dia(conn, ns_id, lancamento), arquivo_trocado=False)


def _na_fila(s):
    return s["situacao"] in FILA or (s["situacao"] in APLICADAS and (s.get("pendente_m") or 0) > R.TOL_M)


def _registros_seg(conn, seg_id):
    """O que o segmento gravou: [{ponto, etapa, ini_m, fim_m, verificado}] (efetivos)."""
    out = [{"ponto": r["ponto"], "trecho_id": r["trecho_id"], "etapa": r["etapa"], "ini_m": r["ini_m"], "fim_m": r["fim_m"],
            "verificado": bool(r["verificado_em"]), "apontamento_id": r["apontamento_id"]}
           for r in _rows(conn.execute(f"""SELECT i.*, t.ponto FROM intervalos_execucao i JOIN trechos t ON t.id = i.trecho_id
                                           WHERE i.ns_segmento_id=? AND {S.EFETIVO.replace('anulado_por', 'i.anulado_por')}
                                           ORDER BY t.ponto, i.etapa, i.ini_m""", (seg_id,)))]
    out += [{"ponto": r["ponto"], "trecho_id": r["trecho_id"], "etapa": r["etapa"], "ini_m": r["ini_m"], "fim_m": r["fim_m"],
             "verificado": False, "apontamento_id": None}
            for r in _rows(conn.execute("""SELECT e.*, t.ponto FROM etapas_complementares e JOIN trechos t ON t.id = e.trecho_id
                                           WHERE e.ns_segmento_id=? AND e.anulado_em IS NULL ORDER BY t.ponto, e.ini_m""", (seg_id,)))]
    return out


def _atraso(ns):
    try:
        return (date.fromisoformat(str(ns["registrada_em"])[:10]) - date.fromisoformat(str(ns["data"])[:10])).days
    except (TypeError, ValueError):
        return 0


def resumo_dia(conn, ns_id, lancamento=None):
    """A NS do dia com os segmentos, o que cada um gravou e o que está na fila da engenharia (para a tela e o diário)."""
    ns = _ns(conn, int(ns_id))
    ns["avisos_croqui"] = croqui = json.loads(ns.pop("leitura", None) or "{}").get("avisos_croqui") or []
    ns["referencia"] = referencia(ns["numero"], ns["folhas"])
    ns["segmentos"] = segmentos(conn, ns["id"])
    por_ordem = {r["ordem"]: r for r in lancamento or []}
    for s in ns["segmentos"]:
        s["registros"] = _registros_seg(conn, s["id"])
        s["na_fila"] = ns["status"] == "REGISTRADA" and _na_fila(s)
        r = por_ordem.get(s["ordem"])
        if r:
            s["agora"] = {"lancado": r["lancado"], "ja": r["ja"], "pulado": r["pulado"]}
    ns["fila"] = [s["ordem"] for s in ns["segmentos"] if s["na_fila"]]
    ns["atraso_dias"] = _atraso(ns)
    ns["atrasada"] = ns["atraso_dias"] > ATRASO_DIAS
    ns["verificada"] = any(r["verificado"] for s in ns["segmentos"] for r in s["registros"])
    ns["avisos"] = sorted({a for s in ns["segmentos"] for a in (s.get("avisos") or []) if a == SEM_ETAPA}) + (
        [f"NS enviada com atraso: {ns['atraso_dias']} dias depois da data da nota"] if ns["atrasada"] else []) + croqui
    ns["drive"] = {q: v for q, v in ((q, _drive(conn, [ns[f"{q}_id"]]).get(ns[f"{q}_id"])) for q in ("pdf", "croqui")) if v}
    ns["croqui_mime"] = (_one(conn, "SELECT mime FROM documentos WHERE id=?", ns["croqui_id"]) or {}).get("mime")
    return ns


def listar_dia(conn, data=None, equipe=None, fila=False, desde=None):
    """NS do dia vigentes (por dia e equipe, ou desde um dia) com a situação de cada segmento; `fila`: só as que têm
    segmento esperando a engenharia, de qualquer dia."""
    sql, args = "SELECT id FROM notas_servico WHERE tipo='EXECUCAO' AND status='REGISTRADA'", []
    for cond, val in (("data=?", data), ("equipe_id=?", equipe), ("data>=?", desde)):
        if val:
            sql, args = f"{sql} AND {cond}", args + [val]
    if fila:
        sql += (f" AND id IN (SELECT ns_id FROM ns_segmentos WHERE situacao IN {FILA} OR (situacao IN {APLICADAS} "
                "AND pendente_m > 0.001))")
    return [resumo_dia(conn, r[0]) for r in conn.execute(sql + " ORDER BY data DESC, equipe_id, id DESC LIMIT 200", args)]


def conferir_dia(conn, ns_id, decisoes, por):
    """A engenharia resolve a fila da NS do dia: escolhe o trecho (e, com ele, o sentido) e aceita, ou deixa de fora com
    o motivo; depois lança o que ficou conferido (registrar_dia). Sem decisão, só tenta de novo o que ficou pendente."""
    ns = _ns(conn, int(ns_id))
    if ns["tipo"] != "EXECUCAO" or ns["status"] != "REGISTRADA":
        raise RegraViolada("Só a NS do dia vigente é conferida aqui.")
    segs = {s["ordem"]: s for s in _rows(conn.execute("SELECT * FROM ns_segmentos WHERE ns_id=?", (ns["id"],)))}
    with transacao(conn):
        for d in decisoes or []:
            s = segs.get(int(d.get("ordem") or 0))
            if not s:
                raise RegraViolada(f"Segmento {d.get('ordem')} não existe nesta NS.")
            if d.get("acao") == "FORA":
                if not str(d.get("motivo") or "").strip():
                    raise RegraViolada(f"Segmento {s['ordem']}: informe por que fica de fora.")
                if _lancado_seg(conn, s["id"]):
                    raise RegraViolada(f"Segmento {s['ordem']} já tem execução lançada: para desfazer, anule a NS (ou retifique "
                                       "o apontamento).")
                conn.execute("UPDATE ns_segmentos SET situacao='FORA', motivo=?, pendente=NULL, pendente_m=0, confirmado_por=?, "
                             "confirmado_em=? WHERE id=?", (str(d["motivo"]).strip(), por, _agora(), s["id"]))
            elif d.get("acao") == "ACEITAR":
                if s["situacao"] != "CONFIRMAR":
                    raise RegraViolada(f"Segmento {s['ordem']}: {NS_SITUACAO.get(s['situacao'], s['situacao'])} "
                                       + ("só pode ficar de fora." if s["situacao"] in FILA else "não precisa de conferência."))
                cands = json.loads(s["candidatos"] or "[]")
                k = d.get("candidato")
                if k is None and s["fisico_id"]:
                    c = {"fisico_id": s["fisico_id"], "ini_m": s["ini_fisico_m"], "fim_m": s["fim_fisico_m"], "sentido": s["sentido"]}
                elif k is not None and 0 <= int(k) < len(cands):
                    c = cands[int(k)]
                else:
                    raise RegraViolada(f"Segmento {s['ordem']}: escolha um dos trechos possíveis.")
                if c.get("situacao") == "ERRO":
                    raise RegraViolada(f"Segmento {s['ordem']}: o trecho escolhido não serve ({c.get('motivo')}).")
                F = _fisico_por_id(conn, c["fisico_id"])
                conn.execute("""UPDATE ns_segmentos SET situacao='CONFIRMADO', fisico_id=?, membros=?, sentido=?, extensao_fisico_m=?,
                                  ini_fisico_m=?, fim_fisico_m=?, origem_sentido=?, confirmado_por=?, confirmado_em=? WHERE id=?""",
                             (F["id"], json.dumps(F["membros"], ensure_ascii=False), c["sentido"], F["extensao_m"], c["ini_m"],
                              c["fim_m"], s["origem_sentido"] if k is None else "ENGENHARIA", por, _agora(), s["id"]))
            elif d.get("acao") not in (None, "", "REPETIR"):
                raise RegraViolada("Ação inválida (ACEITAR ou FORA).")
        lancamento = registrar_dia(conn, ns["id"], por)
    return resumo_dia(conn, ns["id"], lancamento)


NS_SITUACAO = {"AUTOMATICO": "lançado automaticamente", "CONFIRMADO": "já conferido", "FORA": "fora",
               "CONFIRMAR": "a confirmar", "ERRO": "com erro", "SEM_CORRESPONDENCIA": "sem correspondência"}


def verificado_dia(conn, ns_id):
    """Algum registro da NS já foi verificado (conferência interna): o encarregado não anula mais o envio."""
    return bool(conn.execute(f"""SELECT 1 FROM intervalos_execucao i JOIN ns_segmentos s ON s.id = i.ns_segmento_id
                                 WHERE s.ns_id=? AND i.verificado_em IS NOT NULL AND {S.EFETIVO.replace('anulado_por', 'i.anulado_por')}
                                 LIMIT 1""", (ns_id,)).fetchone())
