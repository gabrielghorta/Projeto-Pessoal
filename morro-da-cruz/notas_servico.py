"""Nota de Serviço (NS) por upload: guarda os arquivos, casa cada segmento da NS com o trecho físico da obra e grava, por
linha da 06.1, o que a NS registra. Nada é gravado sem conferência humana: ler() só lê e mostra; registrar() grava o que
a pessoa conferiu, numa transação.

* TOPOGRAFIA: liberação topográfica só no que ainda não está liberado.
* CADASTRO: cadastro de campo só sobre o assentado até a data; o resto fica pendente no segmento e aplicar() completa
  quando o assentado chegar.
* SERVICO: o plano do serviço da zona (PDF + croqui); não grava nada.
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
    m = re.match(r"^(Zona\d\d)_(PB\d\d)_", nome or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def _lugar(c):
    """'Zona03 PB08' (ou 'Zona03 PB05 e PB08') das linhas de um candidato."""
    zp = sorted({_zona_pb(p) for p in c["linhas"]} - {(None, None)})
    return " e ".join(f"{z} {pb}" for z, pb in zp) or "sem zona"


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

    def add(F, pos, nome, papel):
        k = chave_rede(nome)
        if papel == "MEIO":
            meio.setdefault(F["id"], []).append((round(float(pos), 3), nome))
        if k:
            idx.setdefault(k, []).append({"F": F, "pos": round(float(pos), 3), "nome": nome, "papel": papel})

    for F in fis:
        add(F, 0.0, F["no_ini"], "PONTA")
        add(F, F["extensao_m"], F["no_fim"], "PONTA")
        for j in F["juncoes"]:
            add(F, j["posicao_m"], j["no"], "JUNCAO")
    for p in TP.pendencias(conn):
        if p.get("tipo") == "CONEXAO_NO_MEIO_DA_LINHA" and p.get("trecho") in por_ponto and p.get("posicao_m") is not None:
            F, m = por_ponto[p["trecho"]]
            add(F, TP.para_fisico(F, m["trecho_id"], p["posicao_m"], p["posicao_m"])[0], p["no"], "MEIO")
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


def _contexto(ns, zona=None, pb=None):
    cab = ns["cabecalho"]
    ctx = L.contexto_zona_pb(cab.get("titulo"), cab.get("localizacao"))
    origem = "NS" if ctx["zona"] or ctx["pb"] else None
    if zona and not ctx["zona"]:
        ctx["zona"], origem = zona, "FORMULARIO"
    if pb and not ctx["pb"]:
        ctx["pb"], origem = pb, origem or "FORMULARIO"
    return dict(ctx, origem=origem)


def _segmentos_grupo(g, gi, ind, ctx):
    """Segmentos de um grupo: de um elemento reconhecido ao seguinte; linhas sem elemento reconhecido no meio viram
    ponto intermediário (aviso). Depois, segmentos que se encontram numa junção do mesmo trecho físico (cruzamento,
    divisa…) são juntados: a NS vai de conexão a conexão."""
    ls = g["linhas"]
    ctx_g = dict(ctx)
    cg = L.contexto_zona_pb(g.get("titulo"))
    ctx_g.update({k: v for k, v in cg.items() if v})
    rec = [k for k, l in enumerate(ls) if chave_rede(l.get("elemento"))]
    segs = []
    for i, j in zip(rec, rec[1:]):
        ka, kb = chave_rede(ls[i]["elemento"]), chave_rede(ls[j]["elemento"])
        avisos = [f"linha {k + 1} ({ls[k].get('elemento') or 'sem elemento'}) sem elemento da rede: tomada como ponto no meio"
                  for k in range(i + 1, j)]
        segs.append({"grupo": gi, "i": i, "j": j, "ka": ka, "kb": kb, "cands": _vaos(ind, ka, kb, ctx_g), "avisos": avisos,
                     "ctx": ctx_g})
    if segs:                                       # linhas sem elemento antes do 1º ou depois do último: ficam de fora
        for k in [k for k in range(len(ls)) if k < rec[0] or k > rec[-1]]:
            (segs[0] if k < rec[0] else segs[-1])["avisos"].append(
                f"linha {k + 1} ({ls[k].get('elemento') or 'sem elemento'}) sem elemento da rede: fora dos segmentos")
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
    return segs


def _candidato(c, ns_m, de_mm):
    F = c["F"]
    x, y = c["a"]["pos"], c["b"]["pos"]
    proj = round(abs(y - x), 3)
    return {"fisico_id": F["id"], "ini_m": round(min(x, y), 3), "fim_m": round(max(x, y), 3), "sentido": 1 if y > x else -1,
            "extensao_m": proj, "extensao_fisico_m": F["extensao_m"], "de_mm": F["de_mm"], "metodologias": F["metodologias"],
            "diferenca_m": None if ns_m is None else round(ns_m - proj, 3), "de": c["a"]["nome"], "para": c["b"]["nome"],
            "texto": F["texto"], "linhas": [m["ponto"] for m in F["membros"]],
            "pontos_no_meio": [{"posicao_m": round(p - min(x, y), 3), "no": n, "papel": pp, "tipo": t} for p, n, pp, t in _entre(c)]}


def _avaliar(s, ls, ns):
    """Situação do segmento e o candidato escolhido (quando há um só)."""
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
    for p in c["pontos_no_meio"]:
        if p["papel"] == "MEIO":
            out["avisos"].append(f"passa por {_curto(p['no'])} (conexão no meio da linha, a {_m(p['posicao_m'])} m do início "
                                 "do segmento), que a NS não lista")
    if metodo and len(c["metodologias"]) == 1 and c["metodologias"][0] != metodo:
        out.update(situacao="ERRO", motivo=f"método {metodo} na NS × {c['metodologias'][0]} na 06.1")
        return out
    if len(c["metodologias"]) > 1:
        out["avisos"].append(f"o trecho físico tem partes em {' e '.join(c['metodologias'])}")
    if ns_m is None:
        out.update(situacao="CONFIRMAR", motivo="a NS não tem a distância deste segmento")
        return out
    nivel = _nivel_diferenca(ns_m, c["extensao_m"])
    dif = f"{_m(ns_m)} m na NS × {_m(c['extensao_m'])} m no projeto ({'+' if ns_m >= c['extensao_m'] else ''}{_m(ns_m - c['extensao_m'])} m)"
    if nivel == "OK":
        out.update(situacao="AUTOMATICO", motivo=None if abs(ns_m - c["extensao_m"]) < 0.005 else dif)
    elif nivel == "AVISO":
        out.update(situacao="CONFIRMAR", motivo=f"diferença acima de 0,5 %: {dif}")
    else:
        out.update(situacao="ERRO", motivo=f"diferença acima de 5 %: {dif}")
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


def plano(conn, tipo, fisico, ini_m, fim_m, data):
    """O que a NS gravaria em cada linha da 06.1 tocada pelo intervalo [ini_m, fim_m] do trecho físico:
    TOPOGRAFIA: liberação nas faixas ainda não liberadas; CADASTRO: levantamento sobre o assentado até a data ainda sem
    levantamento (o que não foi assentado fica pendente)."""
    out = []
    for p in TP.para_linhas(fisico, ini_m, fim_m):
        faixa = (p["ini_m"], p["fim_m"])
        item = dict(p, gravar=[], ja_m=0.0, pendente=[])
        if tipo == "TOPOGRAFIA":
            cob = _cobertura_compl(conn, p["trecho_id"], "LIBERACAO_TOPOGRAFICA")
            item["gravar"] = _faixas(R.fora_da_cobertura(faixa, cob))
        elif tipo == "CADASTRO":
            ass = S._cobertura(conn, p["trecho_id"], "ASSENTADO", ate_data=data)
            cad = S._cobertura(conn, p["trecho_id"], "CADASTRO_CAMPO")
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
    for item in plano(conn, ns["tipo"], _fisico_salvo(seg), seg["ini_fisico_m"], seg["fim_fisico_m"], ns["data"]):
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
            motivos.append(f"{_curto(item['ponto'])} {', '.join(f'{_m(a)}–{_m(b)}' for a, b in item['pendente'])} m: ainda não "
                           f"assentado até {_data_br(ns['data'])}")
    return round(gravado, 3), round(pendente, 3), motivos


# ------------------------------------------------------------------ ler, registrar, aplicar, anular
def _ler_arquivos(conn, pdf_b64, planilha_b64=None, hoje=None):
    pdf = _bytes(pdf_b64, "o PDF da nota de serviço", L.LIMITE_PDF)
    planilha = _bytes(planilha_b64, "a planilha da nota de serviço", L.LIMITE_PLANILHA) if planilha_b64 else None
    try:
        ns = L.ler(pdf, S.contrato(conn), hoje or date.today().isoformat(), planilha=planilha)
    except L.LeituraRecusada as e:
        raise RegraViolada(str(e)) from None
    return pdf, planilha, ns


def _ja_registrada(conn, ns, tipo, sha_pdf):
    cab = ns["cabecalho"]
    por_arquivo = _one(conn, """SELECT n.id, n.numero, n.tipo, n.status, n.registrada_em FROM notas_servico n
                                JOIN documentos d ON d.id = n.pdf_id WHERE d.sha256=? AND n.status <> 'ANULADA'
                                ORDER BY n.id DESC LIMIT 1""", sha_pdf)
    mesma = _one(conn, "SELECT id, numero, impressao, registrada_em FROM notas_servico WHERE contrato=? AND tipo=? AND numero=? "
                       "AND status='REGISTRADA'", L.norm_contrato(cab.get("contrato")) or "", tipo, str(cab.get("numero") or ""))
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


def ler(conn, tipo, pdf_b64, planilha_b64=None, zona=None, pb=None, hoje=None):
    """Só lê (não grava nada): a leitura e as contas da NS, o casamento de cada segmento com os trechos da obra e a prévia
    do que seria gravado por linha da 06.1."""
    if tipo not in TIPOS or tipo == "EXECUCAO":
        raise RegraViolada("Tipo de nota de serviço inválido (TOPOGRAFIA, CADASTRO ou SERVICO).")
    pdf, _, ns = _ler_arquivos(conn, pdf_b64, planilha_b64, hoje)
    ctx = _contexto(ns, zona, pb)
    segs = casar(conn, ns, ctx)
    data = ns["cabecalho"].get("data")
    for s in segs:
        e = s["escolhido"]
        s["plano"] = plano(conn, tipo, _fisico_por_id(conn, e["fisico_id"]), e["ini_m"], e["fim_m"], data) \
            if e and tipo in PERMISSAO_TIPO and data else []
    por_arquivo, mesma = _ja_registrada(conn, ns, tipo, hashlib.sha256(pdf).hexdigest())
    aviso_tipo = None
    bloco = L.norm_txt(ns["cabecalho"].get("bloco"))
    if bloco and tipo in ("TOPOGRAFIA", "CADASTRO") and tipo not in bloco:
        aviso_tipo = f"o bloco da NS diz '{ns['cabecalho'].get('bloco')}' e o tipo escolhido é {TIPOS[tipo]}"
    return {"tipo": tipo, "leitura": _resumo_leitura(ns), "contexto": ctx, "segmentos": segs, "impressao": ns["impressao_dados"],
            "contrato_ok": L.norm_contrato(ns["cabecalho"].get("contrato")) == L.norm_contrato(S.contrato(conn)),
            "ja_registrada": por_arquivo and dict(por_arquivo, motivo="o mesmo arquivo já foi registrado"),
            "mesmo_numero": mesma and dict(mesma, mesma_impressao=mesma["impressao"] == ns["impressao_dados"]),
            "aviso_tipo": aviso_tipo}


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
                if d.get("fisico_id") else (s["escolhido"] if s["escolhido"] else None)
            if esc is None:
                raise RegraViolada(f"Segmento {s['ordem']}: escolha um dos trechos possíveis.")
            s.update(situacao="CONFIRMADO", escolhido=esc, confirmado_por=por)
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
         json.dumps([{k: c[k] for k in ("fisico_id", "ini_m", "fim_m", "sentido", "extensao_m", "de", "para", "texto")}
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
    with transacao(conn):
        pdf_id = _guardar(conn, "NS_PDF", pdf, nomes.get("pdf"), por)
        croqui_id = _croqui(conn, croqui_b64, nomes.get("croqui"), por) if croqui_b64 else None
        planilha_id = _guardar(conn, "NS_PLANILHA", planilha, nomes.get("planilha"), por) if planilha else None
        if mesma:
            novos = {"pdf_id": pdf_id, **({"croqui_id": croqui_id} if croqui_id else {}),
                     **({"planilha_id": planilha_id} if planilha_id else {})}
            _trocar_arquivo(conn, mesma, novos, por)
            return {"id": mesma["id"], "arquivo_trocado": True, "segmentos": [], "gravado_m": 0.0, "pendente_m": 0.0}
        ctx = _contexto(ns, zona, pb)
        segs = casar(conn, ns, ctx)
        _decidir(segs, decisoes, por)
        ns_id = _inserir_ns(conn, tipo, ns, ctx, pdf_id, croqui_id, planilha_id, por)
        reg = _one(conn, "SELECT * FROM notas_servico WHERE id=?", ns_id)
        out = []
        for s in segs:
            sid = _inserir_segmento(conn, ns_id, s, por)
            r = {"ordem": s["ordem"], "id": sid, "situacao": s["situacao"], "gravado_m": 0.0, "pendente_m": 0.0, "pendencias": []}
            if tipo in PERMISSAO_TIPO and s["situacao"] in APLICADAS:
                seg = _one(conn, "SELECT * FROM ns_segmentos WHERE id=?", sid)
                r["gravado_m"], r["pendente_m"], r["pendencias"] = _aplicar_segmento(conn, reg, seg, por)
                _marcar(conn, sid, r)
            out.append(r)
    return {"id": ns_id, "arquivo_trocado": False, "segmentos": out, "gravado_m": round(sum(r["gravado_m"] for r in out), 3),
            "pendente_m": round(sum(r["pendente_m"] for r in out), 3)}


def _marcar(conn, seg_id, r):
    conn.execute("UPDATE ns_segmentos SET aplicado_m=aplicado_m+?, pendente_m=?, pendente=? WHERE id=?",
                 (r["gravado_m"], r["pendente_m"], "; ".join(r["pendencias"]) or None, seg_id))


def _ns(conn, ns_id):
    ns = _one(conn, "SELECT * FROM notas_servico WHERE id=?", ns_id)
    if not ns:
        raise RegraViolada(f"Nota de serviço #{ns_id} não encontrada.")
    return ns


def aplicar(conn, ns_id, por):
    """Grava o que ficou pendente (CADASTRO: o que já foi assentado; qualquer tipo: o que uma recusa deixou de fora).
    Pode rodar de novo: só grava o que ainda falta (nunca duas vezes o mesmo pedaço)."""
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
        aps = sorted({r[0] for r in conn.execute(
            f"SELECT apontamento_id FROM intervalos_execucao WHERE ns_segmento_id IN ({marcas}) AND {S.EFETIVO} "
            "AND apontamento_id IS NOT NULL", segs)})
        for ap in aps:
            S.retificar_intervalos(conn, "APONTAMENTO", ap, [], motivo, por)
        for i in _rows(conn.execute(f"SELECT id FROM intervalos_execucao WHERE ns_segmento_id IN ({marcas}) AND {S.EFETIVO} "
                                    "AND apontamento_id IS NULL AND etapa='CADASTRO_CAMPO'", segs)):
            S.retificar_intervalos(conn, "CADASTRO_CAMPO", i["id"], [], motivo, por)
        conn.execute("UPDATE notas_servico SET status='ANULADA', anulada_por=?, anulada_em=?, anulada_motivo=? WHERE id=?",
                     (por, _agora(), str(motivo), ns["id"]))
    return {"id": ns["id"], "apontamentos_anulados": len(aps)}


def anexar(conn, ns_id, croqui_b64, nome, por):
    """Croqui enviado depois (ou trocado): a versão anterior da NS fica guardada como SUBSTITUIDA."""
    ns = _ns(conn, int(ns_id))
    if ns["status"] != "REGISTRADA":
        raise RegraViolada(f"NS {ns['numero']} está {ns['status'].lower()}.")
    with transacao(conn):
        cid = _croqui(conn, croqui_b64, nome, por)
        if cid == ns["croqui_id"]:
            raise RegraViolada("Este croqui já está na NS.")
        _trocar_arquivo(conn, ns, {"croqui_id": cid}, por)
    return {"id": ns["id"], "croqui_id": cid}


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
    ns["versoes"] = _rows(conn.execute("SELECT id, pdf_id, croqui_id, planilha_id, registrada_em FROM notas_servico "
                                       "WHERE status='SUBSTITUIDA' AND contrato=? AND tipo=? AND numero=? ORDER BY id",
                                       (ns["contrato"], ns["tipo"], ns["numero"])))
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
