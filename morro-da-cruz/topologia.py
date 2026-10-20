"""Trecho físico: a cadeia de linhas da 06.1 entre duas conexões reais (topologia derivada, sem tabela nova).

A 06.1 continua sendo a unidade da medição e do BM: nenhuma linha é juntada, renomeada ou apagada no banco, e a
execução continua gravada em metros ao longo de cada linha (0 no no_ini da linha). O trecho físico é uma visão por
cima das linhas, montada em memória a partir de:
  * trechos vigentes do banco (pontas BP/BQ, extensão, DE, material, metodologia, frente);
  * config/topologia.json: as junções que NÃO são conexão (cruzamento com semicírculo, tubo que passa ao lado do nó,
    divisa de zona, limite da travessia MND, emenda sem nó), cada uma com a decisão JUNTAR / NAO_JUNTAR / DUVIDA.
    O arquivo é gerado por ferramentas/topologia/ (com o mapa REV02 e a 06.2) e revisado pelo responsável pela obra;
    o sistema só lê. Uma mudança no desenho nunca muda sozinha o que é trecho físico.
O resultado fica em cache pela data de modificação do arquivo e por uma impressão digital dos trechos vigentes.

Conversão de metros (0 do trecho físico no seu no_ini; 0 de cada linha no no_ini da linha):
  sentido +1: local = [x − offset, y − offset];  sentido −1: local = [ext − (y − offset), ext − (x − offset)],
  cortado em [0, ext] e arredondado ao mm. Sentido da cadeia: o da 06.1 no seu membro mais longo (empate: menor id).

* trechos_fisicos(conn) / fisico_do_trecho(conn, trecho_id) → trechos físicos (interface da Nota de Serviço)
* para_linhas(fisico, ini_m, fim_m) / para_fisico(fisico, trecho_id, ini_m, fim_m) → conversão de intervalos
* pendencias(conn) → pontas fora do nó, nós inexistentes, decisões em DUVIDA e decisões que não batem com o banco
* consulta(conn, trecho_id) → resposta de GET /api/topologia;  pontas_nao_conexao() → pontas que o desenho não encaixa
"""
import hashlib
import json
import os
import threading

import caminhos

CONFIG = os.path.join(caminhos.PASTA, "config", "topologia.json")
TOL_M = 1e-3                                   # o mesmo R.TOL_M: posições ao milímetro
JUNTAR, NAO_JUNTAR, DUVIDA = "JUNTAR", "NAO_JUNTAR", "DUVIDA"
# pontas que a 06.1 deixa sem nó (colunas BP/BQ): texto da 06.1 → tipo de junção
SEM_NO = {"DIVISA DE ZONA": "DIVISA_ZONA", "LIMITE DA TRAVESSIA MND": "LIMITE_MND",
          "PONTA SEM NÓ NA TABELA": "PONTA_SEM_NO", "JUNÇÃO SEM NÓ NA TABELA": "JUNCAO_SEM_NO"}
# junções no nome de um nó (o tubo não se liga às peças dele): o desenho não puxa essas pontas para o nó
NO_NOME = ("CRUZAMENTO", "PASSAGEM")
FRASE = {"DIVISA_ZONA": "na divisa de zona o tubo continua (muda só a frente)",
         "LIMITE_MND": "no limite da travessia MND o tubo continua (muda o método)",
         "PONTA_SEM_NO": "na emenda sem nó na tabela o tubo continua",
         "JUNCAO_SEM_NO": "na junção sem nó na tabela o tubo continua"}

_TRAVA = threading.Lock()
_CACHE = {}


def _f(v):
    return float(v or 0)


def _mm(v):
    return round(v + 0.0, 3)


def _ler_config(caminho=None):
    """config/topologia.json (ou vazio, se não existir): {"juncoes": [...], "pendencias": [...], ...}."""
    p = caminho or CONFIG
    if not os.path.exists(p):
        return {"juncoes": [], "pendencias": [], "ausente": True}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _chave_config(caminho=None):
    p = caminho or CONFIG
    return (os.path.abspath(p), os.path.getmtime(p)) if os.path.exists(p) else (os.path.abspath(p), None)


def _trechos(conn):
    cols = ("id", "ponto", "no_ini", "no_fim", "extensao_m", "de_mm", "material", "metodologia", "frente_id")
    rows = conn.execute(f"SELECT {', '.join(cols)} FROM trechos WHERE vigente = 1 ORDER BY id").fetchall()
    return [dict(zip(cols, r)) for r in rows]


def _impressao(trechos):
    h = hashlib.sha1()
    for t in trechos:
        h.update("|".join(str(t[k]) for k in ("id", "ponto", "no_ini", "no_fim", "extensao_m", "de_mm", "material",
                                               "metodologia", "frente_id")).encode("utf-8"))
    return h.hexdigest()


def _curto(nome):
    """Zona03_PB08_Rede_TR007 → TR007; Zona03_PB08_CH_VRP-15 → VRP-15 (texto sem nó fica como está)."""
    return str(nome or "").split("_")[-1] if str(nome or "").startswith(("Zona", "ADUTORA")) else str(nome or "")


def _nf(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _validar(juncao, por_ponto):
    """Pontas de uma junção JUNTAR conferidas com o banco: [(trecho, lado), (trecho, lado)] ou o motivo da recusa."""
    pontas = juncao.get("pontas") or []
    if len(pontas) != 2:
        return None, "a junção JUNTAR precisa de exatamente duas pontas"
    out = []
    for p in pontas:
        t = por_ponto.get(p.get("trecho"))
        lado = p.get("lado")
        if t is None:
            return None, f"{p.get('trecho')} não existe (ou não está vigente) no banco"
        if lado not in ("ini", "fim"):
            return None, f"lado inválido em {p.get('trecho')}: {lado}"
        no = t["no_" + lado]
        esperado = juncao.get("no") if juncao.get("tipo") in NO_NOME else None
        if esperado is not None and no != esperado:
            return None, f"{t['ponto']} ({lado}) termina em {no}, não em {esperado}"
        if esperado is None and no not in SEM_NO and no != juncao.get("no"):
            return None, f"{t['ponto']} ({lado}) termina em {no}: a junção não bate com a 06.1"
        out.append((t, lado))
    (a, _), (b, _) = out
    if a["id"] == b["id"]:
        return None, "as duas pontas são do mesmo trecho"
    if _f(a["de_mm"]) != _f(b["de_mm"]) or (a["material"] or "") != (b["material"] or ""):
        return None, (f"troca de DE ou material ({a['ponto']}: DE {_f(a['de_mm']):g} {a['material']}; "
                      f"{b['ponto']}: DE {_f(b['de_mm']):g} {b['material']}): não se junta")
    return out, None


def _montar(trechos, cfg):
    por_ponto = {t["ponto"]: t for t in trechos}
    por_id = {t["id"]: t for t in trechos}
    elo, avisos, usadas = {}, [], []
    for j in cfg.get("juncoes") or []:
        if j.get("decisao") != JUNTAR:
            continue
        pontas, motivo = _validar(j, por_ponto)
        if motivo:
            avisos.append({"tipo": "DECISAO_DESATUALIZADA", "juncao": j.get("id"), "no": j.get("no"),
                           "detalhe": f"junção {j.get('id')} ignorada: {motivo}"})
            continue
        (a, la), (b, lb) = pontas
        ka, kb = (a["id"], la), (b["id"], lb)
        if ka in elo or kb in elo:
            avisos.append({"tipo": "DECISAO_EM_CONFLITO", "juncao": j.get("id"), "no": j.get("no"),
                           "detalhe": f"junção {j.get('id')} ignorada: a ponta já está em outra junção JUNTAR"})
            continue
        elo[ka] = (kb, j)
        elo[kb] = (ka, j)
        usadas.append(j)
    fisicos, de_trecho, vistos = [], {}, set()
    for t in trechos:
        if t["id"] in vistos:
            continue
        lado, atual, passos = "ini", t["id"], 0           # anda até uma ponta livre (ou volta ao início: anel)
        while (atual, lado) in elo and passos <= len(trechos):
            (prox, lp), _ = elo[(atual, lado)]
            atual, lado = prox, ("fim" if lp == "ini" else "ini")
            passos += 1
            if atual == t["id"]:
                avisos.append({"tipo": "CADEIA_EM_ANEL", "trecho": t["ponto"],
                               "detalhe": f"as junções JUNTAR fecham um anel a partir de {t['ponto']}: cortado nele"})
                lado = "ini"
                break
        membros, juncoes, entrada = [], [], lado        # entra pela ponta livre e segue até a outra ponta livre
        while atual not in vistos:
            vistos.add(atual)
            membros.append((por_id[atual], 1 if entrada == "ini" else -1))
            saida = "fim" if entrada == "ini" else "ini"
            if (atual, saida) not in elo:
                break
            (prox, lp), j = elo[(atual, saida)]
            if prox in vistos:
                break
            juncoes.append(j)
            atual, entrada = prox, lp
        fisicos.append(_fisico(membros, juncoes))
    fisicos.sort(key=lambda f: f["id"])
    for f in fisicos:
        for m in f["membros"]:
            de_trecho[m["trecho_id"]] = f
    return fisicos, de_trecho, avisos, usadas


def _fisico(membros, juncoes):
    longo = min(membros, key=lambda m: (-_f(m[0]["extensao_m"]), m[0]["id"]))
    if longo[1] == -1:                                  # a cadeia segue a 06.1 do membro mais longo
        membros = [(t, -s) for t, s in reversed(membros)]
        juncoes = list(reversed(juncoes))
    out, pos = [], 0.0
    for k, (t, s) in enumerate(membros, 1):
        ext = _f(t["extensao_m"])
        out.append({"trecho_id": t["id"], "ponto": t["ponto"], "ordem": k, "offset_m": _mm(pos), "extensao_m": ext,
                    "sentido": s})
        pos += ext
    pri, ult = membros[0], membros[-1]
    no_ini = pri[0]["no_ini"] if pri[1] == 1 else pri[0]["no_fim"]
    no_fim = ult[0]["no_fim"] if ult[1] == 1 else ult[0]["no_ini"]
    unicos = lambda vals: list(dict.fromkeys(v for v in vals if v))
    menor = min(t["id"] for t, _ in membros)
    f = {"id": "TF-" + menor.split("-", 1)[-1], "no_ini": no_ini, "no_fim": no_fim, "extensao_m": _mm(pos),
         "de_mm": int(round(_f(pri[0]["de_mm"]))), "material": pri[0]["material"],
         "metodologias": unicos(t["metodologia"] for t, _ in membros), "frentes": unicos(t["frente_id"] for t, _ in membros),
         "membros": out,
         "juncoes": [{"id": j.get("id"), "no": j.get("no"), "tipo": j.get("tipo"), "decisao": j.get("decisao"),
                      "posicao_m": out[k + 1]["offset_m"]} for k, j in enumerate(juncoes)]}
    f["texto"] = _texto(f)
    return f


def _texto(f):
    """Frase simples para a ficha: 'Trecho físico: TR007 + TR006 = 295,98 m, de NÓ9.1 até VRP-15. NÓ113.1 é ...'."""
    ms = f["membros"]
    if len(ms) == 1:
        return f"Trecho físico de uma linha só: {_curto(ms[0]['ponto'])}, {_nf(f['extensao_m'])} m."
    partes = [m["ponto"].split("_") for m in ms]
    k = 1                                               # TR007; PB07 Adutora TR001 quando o número se repete
    while k < 3 and len({tuple(p[-k:]) for p in partes}) < len(partes):
        k += 2
    zona = len({p[0] for p in partes}) > 1
    nome = lambda p: " ".join(([p.split("_")[0]] if zona else []) + p.split("_")[-k:])
    grupos = {}
    for j in f["juncoes"]:
        grupos.setdefault(j["tipo"], []).append(_curto(j["no"]))
    frases = []
    for tipo, nos in grupos.items():
        nos = list(dict.fromkeys(nos))
        lista = nos[0] if len(nos) == 1 else ", ".join(nos[:-1]) + " e " + nos[-1]
        if tipo == "CRUZAMENTO":
            frases.append(lista + (" são cruzamentos (não são conexão)" if len(nos) > 1 else " é cruzamento (não é conexão)"))
        elif tipo == "PASSAGEM":
            frases.append(lista + ": o tubo passa ao lado do nó, sem ligação")
        else:
            frases.append(FRASE.get(tipo, "o tubo continua"))
    frase = "; ".join(frases)
    return (f"Trecho físico: {' + '.join(nome(m['ponto']) for m in ms)} = {_nf(f['extensao_m'])} m, de "
            f"{_curto(f['no_ini'])} até {_curto(f['no_fim'])}. " + frase[:1].upper() + frase[1:] + ".")


def _estado(conn, cfg_caminho=None):
    trechos = _trechos(conn)
    chave = (_chave_config(cfg_caminho), _impressao(trechos))
    with _TRAVA:
        if _CACHE.get("chave") != chave:
            cfg = _ler_config(cfg_caminho)
            fisicos, de_trecho, avisos, usadas = _montar(trechos, cfg)
            _CACHE.clear()
            _CACHE.update(chave=chave, cfg=cfg, fisicos=fisicos, de_trecho=de_trecho, avisos=avisos, usadas=usadas,
                          trechos=trechos)
        return _CACHE


def trechos_fisicos(conn):
    """Todos os trechos físicos (conexão → conexão) dos trechos vigentes:
    [{"id": "TF-<número do menor trechos.id entre os membros>",     # estável enquanto os membros não mudam
      "no_ini": str, "no_fim": str,                                 # conexões reais nas pontas (texto da 06.1)
      "extensao_m": float,                                          # soma das extensões da 06.1
      "de_mm": int, "material": str, "metodologias": [..], "frentes": [..],
      "membros": [{"trecho_id": "TR-xxxxx", "ponto": "Zona03_PB08_Rede_TR007", "ordem": 1,
                   "offset_m": 0.0, "extensao_m": 2.51, "sentido": 1}, ...],
      "juncoes": [{"id": "J-0001", "no": "Zona03_PB08_Rede_NÓ113.1", "tipo": "CRUZAMENTO", "decisao": "JUNTAR",
                   "posicao_m": 2.51}],
      "texto": "Trecho físico: TR007 + TR006 = 295,98 m, de NÓ9.1 até VRP-15. NÓ113.1 é cruzamento (não é conexão)."}]
    Trecho sem junção = trecho físico de um membro (offset 0, sentido 1). Não altere o que volta (é o cache)."""
    return _estado(conn)["fisicos"]


def fisico_do_trecho(conn, trecho_id):
    """O trecho físico que contém essa linha da 06.1 (ou None)."""
    return _estado(conn)["de_trecho"].get(trecho_id)


def para_linhas(fisico, ini_m, fim_m):
    """Metros do trecho físico (0 em no_ini) → [{"trecho_id", "ponto", "ini_m", "fim_m"}] por membro tocado."""
    x, y = sorted((_f(ini_m), _f(fim_m)))
    out = []
    for m in fisico["membros"]:
        o, ext = _f(m["offset_m"]), _f(m["extensao_m"])
        a, b = max(x, o), min(y, o + ext)
        if b - a <= TOL_M:
            continue
        ini, fim = (a - o, b - o) if m["sentido"] == 1 else (ext - (b - o), ext - (a - o))
        ini, fim = _mm(min(max(ini, 0.0), ext)), _mm(min(max(fim, 0.0), ext))
        if fim - ini > TOL_M:
            out.append({"trecho_id": m["trecho_id"], "ponto": m["ponto"], "ini_m": ini, "fim_m": fim})
    return out


def para_fisico(fisico, trecho_id, ini_m, fim_m):
    """Intervalo local de uma linha da 06.1 (0 no no_ini dela) → (ini, fim) no trecho físico."""
    m = next((m for m in fisico["membros"] if m["trecho_id"] == trecho_id), None)
    if m is None:
        raise ValueError(f"{trecho_id} não faz parte do trecho físico {fisico['id']}")
    o, ext = _f(m["offset_m"]), _f(m["extensao_m"])
    x, y = sorted((min(max(_f(ini_m), 0.0), ext), min(max(_f(fim_m), 0.0), ext)))
    ini, fim = (o + x, o + y) if m["sentido"] == 1 else (o + ext - y, o + ext - x)
    return _mm(ini), _mm(fim)


def pendencias(conn):
    """Pontas fora do nó (do arquivo de decisões), nós inexistentes, pontas sem conexão, decisões em DUVIDA e
    decisões que não batem com o banco. Cada item: {"tipo", "detalhe", e "trecho"/"lado"/"no"/"juncao" quando houver}."""
    est = _estado(conn)
    cfg, out = est["cfg"], []
    if cfg.get("ausente"):
        out.append({"tipo": "SEM_ARQUIVO_DE_DECISOES", "detalhe": "config/topologia.json não existe: cada linha da "
                     "06.1 é um trecho físico separado"})
    for j in cfg.get("juncoes") or []:
        if j.get("decisao") == DUVIDA:
            out.append({"tipo": "DECISAO_EM_DUVIDA", "juncao": j.get("id"), "no": j.get("no"),
                        "trechos": [p.get("trecho") for p in j.get("pontas") or []],
                        "detalhe": f"{j.get('tipo')}: {j.get('motivo') or 'decisão do responsável pendente'}"})
    out += [dict(a) for a in est["avisos"]]
    nomes = {r[0] for r in conn.execute("SELECT nomenclatura FROM atividades WHERE vigente = 1")}
    livres = set()
    for f in est["fisicos"]:                               # pontas que terminam o trecho físico
        a, b = f["membros"][0], f["membros"][-1]
        livres.add((a["trecho_id"], "ini" if a["sentido"] == 1 else "fim"))
        livres.add((b["trecho_id"], "fim" if b["sentido"] == 1 else "ini"))
    for t in est["trechos"]:
        for lado in ("ini", "fim"):
            no = t["no_" + lado]
            if no in SEM_NO:
                if (t["id"], lado) in livres:
                    out.append({"tipo": "PONTA_SEM_CONEXAO", "trecho": t["ponto"], "lado": lado, "no": no,
                                "detalhe": f"o trecho físico termina em '{no}' (a 06.2 não tem conexão nesse ponto)"})
            elif no and no not in nomes:
                out.append({"tipo": "NO_INEXISTENTE", "trecho": t["ponto"], "lado": lado, "no": no,
                            "detalhe": f"{no} não existe na 06.2 vigente"})
    out += [dict(p) for p in cfg.get("pendencias") or []]
    return out


def resumo(conn):
    est = _estado(conn)
    fis = est["fisicos"]
    multi = [f for f in fis if len(f["membros"]) > 1]
    por_tipo, por_decisao = {}, {}
    for j in est["cfg"].get("juncoes") or []:
        por_tipo.setdefault(j.get("tipo"), {}).setdefault(j.get("decisao"), 0)
        por_tipo[j.get("tipo")][j.get("decisao")] += 1
        por_decisao[j.get("decisao")] = por_decisao.get(j.get("decisao"), 0) + 1
    return {"linhas_06_1": len(est["trechos"]), "trechos_fisicos": len(fis), "com_mais_de_uma_linha": len(multi),
            "linhas_em_cadeias": sum(len(f["membros"]) for f in multi),
            "extensao_m": _mm(sum(f["extensao_m"] for f in fis)), "juncoes_por_tipo": por_tipo,
            "juncoes_por_decisao": por_decisao, "juncoes_aplicadas": len(est["usadas"]),
            "arquivo": os.path.relpath(CONFIG, caminhos.PASTA), "gerado_em": est["cfg"].get("gerado_em")}


def consulta(conn, trecho_id=None):
    """GET /api/topologia: resumo, cadeias (trechos físicos com mais de uma linha), junções e pendências;
    com ?trecho=<id> (ou nome visível vigente), só o trecho físico daquela linha."""
    if trecho_id:
        tid = trecho_id
        if not str(tid).startswith("TR-"):
            r = conn.execute("SELECT id FROM trechos WHERE ponto = ? AND vigente = 1", (tid,)).fetchone()
            tid = r[0] if r else tid
        return {"trecho_id": tid, "trecho_fisico": fisico_do_trecho(conn, tid)}
    est = _estado(conn)
    return {"resumo": resumo(conn), "cadeias": [f for f in est["fisicos"] if len(f["membros"]) > 1],
            "cruzamentos": est["cfg"].get("juncoes") or [], "pendencias": pendencias(conn)}


def mapa(conn):
    """Para as telas do mapa: os trechos físicos com mais de uma linha, pelo nome visível de cada membro."""
    return [{"id": f["id"], "texto": f["texto"], "membros": [m["ponto"] for m in f["membros"]],
             "nos": [j["no"] for j in f["juncoes"] if j["tipo"] in NO_NOME]}
            for f in trechos_fisicos(conn) if len(f["membros"]) > 1]


def pontas_nao_conexao(caminho=None):
    """Pontas que terminam no nome de um nó sem se ligar a ele (CRUZAMENTO / PASSAGEM em JUNTAR ou DUVIDA):
    {(nome visível, 'ini'|'fim'): tipo}. O desenho não puxa essas pontas para o centro do nó."""
    cfg = _ler_config(caminho)
    out = {}
    for j in cfg.get("juncoes") or []:
        if j.get("tipo") in NO_NOME and j.get("decisao") in (JUNTAR, DUVIDA):
            for p in j.get("pontas") or []:
                out[(p.get("trecho"), p.get("lado"))] = j.get("tipo")
    return out


def chave_config(caminho=None):
    """Muda quando config/topologia.json muda (para quem guarda cálculo derivado dele)."""
    return _chave_config(caminho)[1]
