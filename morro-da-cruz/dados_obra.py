"""Dados da obra: o mapa em que se planeja a obra trecho a trecho (grupo Planejamento) e de onde sai o que o Mapa
iluminado mostra (programado, equipe em campo e material com a equipe).

Seleção no mapa (linhas da 06.1 escolhidas com Ctrl+clique):
  * cada linha puxa o trecho físico inteiro (topologia.py: de conexão a conexão; cruzamento com semicírculo, divisa de
    zona etc. não separam o tubo);
  * a conexão que liga dois trechos escolhidos entra sozinha (dois cliques, não três); outro nó entra se for tocado;
  * ponta que não é nó da 06.2 vigente fica de fora da sugestão de peças e vira aviso.
Com a seleção (o Dados da obra é o DIA da equipe; o macro de 18 meses é o Cronograma):
  * programar: equipe, serviço e UM dia → uma programação por alvo, todas com o mesmo carimbo de criação (o "lote", que
    se cancela de uma vez). Não é presença nem execução. O mesmo alvo para outra equipe no dia pede confirmação;
  * liberar: o almoxarife entrega o material do dia — abre o check-in da equipe (ou soma ao check-in aberto dela no mesmo
    dia) com TODOS os trechos e nós da seleção (checkin_alvos: PROGRAMACAO o que estava programado, CHECKIN o acrescentado
    na hora), e as programações daquele dia para a seleção ficam realizadas por esse check-in. Na hora, os trechos ficam
    "em execução hoje" e o pino da equipe aparece no Mapa iluminado e no mapa da tela Início;
  * reservar: para um dia que ainda não chegou, o material fica separado para a equipe (servicos.reservar);
  * devolução das peças não usadas: o check-out de sempre (servicos.checkout), com o que está com a equipe (estado()).
O material sugerido vem do projeto: tubo da 06.1 pelo que falta assentar em cada linha e as peças da 06.2 dos nós, pelo
item do BM Vertical. É sugestão: quem libera confere e muda a quantidade. Nada aqui muda o esquema do banco.
"""
from datetime import date, timedelta

import planejamento as P
import regras as R
import relogio as RL
import servicos as S
import topologia as TP
from servicos import RegraViolada, _agora, _one, _rows, transacao

TOL = 1e-6
LIMITE_LINHAS = 400
LIMITE_PROGRAMACOES = 400
# o mesmo item da Juntada aparece em mais de um subgrupo do BM Vertical (ex.: tubo 1.14.77 no canteiro e no
# hidromecânico): para peça de nó vale o primeiro subgrupo desta ordem que tiver o item
PREFERENCIA_BM = ("HIDROMEC", "REDES", "CAIXAS", "INTERLIGA", "LIGA", "CANTEIRO")


def _curto(nome):
    return str(nome or "").split("_")[-1]


def _lista(v):
    if v is None:
        return []
    if isinstance(v, str):
        v = v.split(",")
    return [str(x).strip() for x in v if str(x).strip()]


def _data(v, rotulo):
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise RegraViolada(f"Data de {rotulo} inválida.") from None


# ------------------------------------------------------------------ seleção
def _selecao(conn, linhas, nos=()):
    """Linhas tocadas → trechos físicos inteiros, as linhas deles e os nós (os que ligam dois trechos escolhidos e os
    tocados). Recusa linha inexistente ou retirada da revisão vigente."""
    refs = list(dict.fromkeys(_lista(linhas)))
    if len(refs) > LIMITE_LINHAS:
        raise RegraViolada(f"Seleção grande demais ({len(refs)} linhas; até {LIMITE_LINHAS}).")
    fisicos = {}
    for ref in refs:
        t = S.alvo(conn, "TRECHO", ref, operacao=True)
        f = TP.fisico_do_trecho(conn, t["id"])
        if f:
            fisicos.setdefault(f["id"], f)
    ids = [m["trecho_id"] for f in fisicos.values() for m in f["membros"]]
    ph = ",".join("?" * len(ids))
    tr = {r["id"]: r for r in _rows(conn.execute(
        f"SELECT id, ponto, extensao_m, de_mm, frente_id, metodologia, material FROM trechos WHERE id IN ({ph})", ids))} if ids else {}
    pontas = {}
    for f in fisicos.values():
        for no in {f["no_ini"], f["no_fim"]} - {None, ""}:
            pontas.setdefault(no, []).append(f)
    avisos, nos_out, vistos = [], [], set()
    ligam = {no: fs for no, fs in pontas.items() if len(fs) > 1}
    if ligam:
        ph = ",".join("?" * len(ligam))
        ativs = {r["nomenclatura"]: r for r in _rows(conn.execute(
            f"""SELECT a.id, a.nomenclatura, a.frente_id, e.numero, e.tipo FROM atividades a JOIN elementos e ON e.id=a.elemento_id
                WHERE a.nomenclatura IN ({ph}) AND a.vigente=1 AND e.vigente=1""", list(ligam)))}
        for no, fs in sorted(ligam.items()):
            liga = [" + ".join(_curto(m["ponto"]) for m in f["membros"]) for f in fs]
            a = ativs.get(no)
            if not a:
                avisos.append(f"{_curto(no)} liga {' e '.join(liga)}, mas não é nó da 06.2 vigente: fica fora da sugestão de peças.")
                continue
            vistos.add(a["id"])
            nos_out.append({"atividade_id": a["id"], "nome": a["nomenclatura"], "numero": a["numero"], "tipo": a["tipo"],
                            "frente_id": a["frente_id"], "automatico": True, "liga": liga})
    for ref in dict.fromkeys(_lista(nos)):
        a = S.alvo(conn, "ATIVIDADE", ref, operacao=True)
        if a["id"] in vistos:
            continue
        vistos.add(a["id"])
        nos_out.append({"atividade_id": a["id"], "nome": a["nomenclatura"], "numero": a["numero"], "tipo": a["tipo_elemento"],
                        "frente_id": a["frente_id"], "automatico": False,
                        "liga": [_curto(f["membros"][0]["ponto"]) for f in pontas.get(a["nomenclatura"], [])]})
    linhas_out = [tr[i] for i in ids if i in tr]
    return {"fisicos": [{"id": f["id"], "texto": f["texto"], "extensao_m": f["extensao_m"], "de_mm": f["de_mm"],
                         "no_ini": f["no_ini"], "no_fim": f["no_fim"], "membros": [m["ponto"] for m in f["membros"]]}
                        for f in fisicos.values()],
            "linhas": linhas_out, "nos": nos_out, "avisos": avisos}


def _alvos(sel):
    return [("TRECHO", t["id"]) for t in sel["linhas"]] + [("ATIVIDADE", n["atividade_id"]) for n in sel["nos"]]


def _execucao(conn, ids):
    """Por linha: metros assentados, reaterrados e liberados pela topografia (registros efetivos) e o que falta assentar.
    O avanço legado sem posição conta no assentado (o maior dos dois), para a sugestão de tubo não passar do que falta."""
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    cob = {i: {} for i in ids}
    for tid, etapa, a, b in conn.execute(f"""SELECT trecho_id, etapa, ini_m, fim_m FROM intervalos_execucao
                                             WHERE {S.EFETIVO} AND trecho_id IN ({ph})""", ids):
        cob[tid].setdefault(etapa, []).append((a, b))
    for tid, a, b in conn.execute(f"""SELECT trecho_id, ini_m, fim_m FROM etapas_complementares WHERE etapa='LIBERACAO_TOPOGRAFICA'
                                      AND anulado_em IS NULL AND trecho_id IN ({ph})""", ids):
        cob[tid].setdefault("LIBERACAO_TOPOGRAFICA", []).append((a, b))
    legado = dict(conn.execute(f"SELECT alvo_id, metros_executados FROM execucao WHERE alvo_tipo='TRECHO' AND alvo_id IN ({ph})", ids))
    m = lambda tid, e: round(R.comprimento(R.unir_intervalos(cob[tid].get(e, []))), 2)
    return {tid: {"assentado_m": max(m(tid, "ASSENTADO"), round(float(legado.get(tid) or 0), 2)),
                  "reaterrado_m": m(tid, "REATERRADO"), "liberado_m": m(tid, "LIBERACAO_TOPOGRAFICA")} for tid in ids}


def _materiais_bm(conn):
    """{item da Juntada: material} pelo BM Vertical (só material com correspondência única pela PREFERENCIA_BM)."""
    cands = {}
    for item_bm, mid, sg in conn.execute("""SELECT b.item_bm, m.id, b.subgrupo_nome FROM bm_itens b JOIN materiais m ON m.bm_item_id=b.id
                                            WHERE b.planilha='VERTICAL' AND b.vigente=1 ORDER BY m.id"""):
        cands.setdefault(item_bm, []).append((mid, (sg or "").upper()))
    out = {}
    for item, cs in cands.items():
        if len(cs) == 1:
            out[item] = cs[0][0]
            continue
        for pref in PREFERENCIA_BM:
            hit = [mid for mid, sg in cs if pref in sg]
            if len(hit) == 1:
                out[item] = hit[0]
                break
    return out


def _sugestao(conn, sel, exe, equipe=None, data=None):
    """Material do projeto para a seleção: tubo Caesb por DE (o que falta assentar) e peças dos nós (06.2 → BM Vertical)."""
    previsto, origem, sem = {}, {}, []
    for t in sel["linhas"]:
        falta = round(max(float(t["extensao_m"]) - exe[t["id"]]["assentado_m"], 0), 2)
        if falta <= TOL:
            continue
        mid = f"CAESB-PEAD-DE{int(round(float(t['de_mm'] or 0)))}"
        previsto[mid] = previsto.get(mid, 0) + falta
        origem.setdefault(mid, []).append(f"{_curto(t['ponto'])} {R.fmt_num(falta)} m")
    if sel["nos"]:
        por_bm = _materiais_bm(conn)
        ph = ",".join("?" * len(sel["nos"]))
        for it in _rows(conn.execute(f"""SELECT i.atividade_id, i.descricao, i.diametro, i.quantidade, i.unidade, i.codigo_bm, a.nomenclatura
                                         FROM itens_projeto i JOIN atividades a ON a.id=i.atividade_id
                                         WHERE i.vigente=1 AND i.atividade_id IN ({ph}) ORDER BY a.nomenclatura, i.id""",
                                      [n["atividade_id"] for n in sel["nos"]])):
            mid = por_bm.get(it["codigo_bm"])
            if not mid or it["quantidade"] is None:
                sem.append({"no": _curto(it["nomenclatura"]), "descricao": it["descricao"], "diametro": it["diametro"],
                            "codigo_bm": it["codigo_bm"], "quantidade": it["quantidade"], "unidade": it["unidade"]})
                continue
            previsto[mid] = previsto.get(mid, 0) + float(it["quantidade"])
            origem.setdefault(mid, []).append(f"{_curto(it['nomenclatura'])} {float(it['quantidade']):g}")
    cat = {r["id"]: r for r in _rows(conn.execute(
        f"SELECT id, descricao, unidade, propriedade FROM materiais WHERE id IN ({','.join('?' * len(previsto))})", list(previsto)))} \
        if previsto else {}
    out = []
    for mid, q in sorted(previsto.items(), key=lambda x: (not x[0].startswith("CAESB-"), x[0])):
        m = cat.get(mid)
        if not m:
            sem.append({"no": ", ".join(origem[mid][:4]), "descricao": f"material {mid} fora do catálogo do almoxarifado",
                        "codigo_bm": None, "quantidade": round(q, 3), "unidade": None})
            continue
        com = round(S.custodia_equipe(conn, equipe, mid), 3) if equipe else 0.0
        disp = round(S.disponivel(conn, mid), 3)
        res = round(S.reservado(conn, mid, equipe, data), 3) if equipe and data else 0.0
        sug = round(max(q - max(com, 0), 0), 3)
        # o que dá para entregar: no dia, o disponível mais a reserva da própria equipe; para um dia futuro, só o disponível
        pode = max(disp, 0) + (res if data and data <= RL.hoje().isoformat() else 0)
        out.append({"material_id": mid, "descricao": m["descricao"], "unidade": m["unidade"], "propriedade": m["propriedade"],
                    "previsto": round(q, 3), "origem": ", ".join(origem[mid]), "disponivel": disp, "com_equipe": com,
                    "reservado_equipe": res, "sugerido": sug, "liberavel": round(min(sug, pode), 3),
                    "falta_no_almox": round(max(sug - pode, 0), 3)})
    return out, sem


def _agrupar_lotes(rows, nomes):
    """Programações do mesmo pedido (mesma equipe, serviço, autor e carimbo de criação) formam um lote."""
    lotes = {}
    for p in rows:
        k = f"{p['criada_em']}|{p['criada_por']}|{p['equipe_id']}|{p['servico']}"
        x = lotes.setdefault(k, {"lote": k, "equipe_id": p["equipe_id"], "servico": p["servico"],
                                 "servico_nome": P.SERVICOS.get(p["servico"], p["servico"]), "criada_por": p["criada_por"],
                                 "criada_em": p["criada_em"], "de": p["data"], "ate": p["data"], "datas": set(), "alvos": set(),
                                 "status": {}})
        x["de"], x["ate"] = min(x["de"], p["data"]), max(x["ate"], p["data"])
        x["datas"].add(p["data"])
        x["alvos"].add(nomes.get((p["alvo_tipo"], p["alvo_id"]), p["alvo_id"]))
        x["status"][p["status"]] = x["status"].get(p["status"], 0) + 1
    out = []
    for x in lotes.values():
        x["dias"] = len(x.pop("datas"))
        x["alvos"] = sorted(x["alvos"])
        out.append(x)
    return sorted(out, key=lambda x: (x["de"], x["equipe_id"], x["criada_em"]))


def _checkins(conn, nomes, hoje, filtro=None):
    """Check-ins abertos (o que está com cada equipe), com os alvos que cada um cobre; `filtro(c, alvos)` escolhe quais."""
    cat = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT id, descricao, unidade FROM materiais")}
    out = []
    for c in S.checkins_abertos(conn):
        alvos = [(a["alvo_tipo"], a["alvo_id"]) for a in c["alvos"]]
        if filtro and not filtro(c, alvos):
            continue
        out.append({"id": c["id"], "data": c["data"], "equipe_id": c["equipe_id"], "contingencia": c["contingencia"],
                    "alvo_nome": c["alvo_nome"], "atrasado": c["data"] < hoje,
                    "alvos": list(dict.fromkeys(nomes.get(a, a[1]) for a in alvos)),
                    "materiais": [dict(m, descricao=cat.get(m["material_id"], ("", ""))[0], unidade=cat.get(m["material_id"], ("", ""))[1])
                                  for m in c["materiais"]]})
    return out


def selecao(conn, linhas, nos=(), data=None, equipe=None):
    """Tudo o que o painel do mapa mostra para a seleção: trechos físicos, linhas (com o executado), nós, avisos, material
    sugerido para a equipe/dia, programações que já tocam a seleção e check-ins abertos ligados a ela."""
    sel = _selecao(conn, linhas, nos)
    hoje = (data or RL.hoje().isoformat())[:10]
    if equipe and not _one(conn, "SELECT 1 FROM equipes WHERE id=?", equipe):
        raise RegraViolada(f"Equipe '{equipe}' não cadastrada.")
    exe = _execucao(conn, [t["id"] for t in sel["linhas"]])
    for t in sel["linhas"]:
        t.update(exe[t["id"]], falta_assentar_m=round(max(float(t["extensao_m"]) - exe[t["id"]]["assentado_m"], 0), 2))
    sel["materiais"], sel["sem_material"] = _sugestao(conn, sel, exe, equipe, hoje)
    nomes = P.nomes_vigentes(conn)
    alvos = set(_alvos(sel))
    rows = []
    if alvos:
        ini = (date.fromisoformat(hoje) - timedelta(days=7)).isoformat()
        fim = (date.fromisoformat(hoje) + timedelta(days=120)).isoformat()
        rows = [p for p in _rows(conn.execute("SELECT * FROM programacoes WHERE data BETWEEN ? AND ? AND status<>'CANCELADA' "
                                              "ORDER BY data, id", (ini, fim))) if (p["alvo_tipo"], p["alvo_id"]) in alvos]
    sel["programacoes"] = _agrupar_lotes(rows, nomes)
    sel["checkins"] = _checkins(conn, nomes, hoje, lambda c, a: c["equipe_id"] == equipe or bool(alvos & set(a)))
    sel["totais"] = {"trechos_fisicos": len(sel["fisicos"]), "linhas": len(sel["linhas"]), "nos": len(sel["nos"]),
                     "extensao_m": round(sum(float(t["extensao_m"]) for t in sel["linhas"]), 2),
                     "falta_assentar_m": round(sum(t["falta_assentar_m"] for t in sel["linhas"]), 2)}
    return sel


# ------------------------------------------------------------------ programar, liberar, reservar
def programar(conn, linhas, nos, equipe_id, servico, data, por, obs=None, confirmar=False):
    """O que a equipe executa NAQUELE dia (o macro de 18 meses é o Cronograma; o dia é aqui): uma programação por alvo
    (linha ou nó), todas com o mesmo carimbo de criação (o lote). Programação igual já existente é mantida. O alvo já
    programado para OUTRA equipe no mesmo dia não é gravado sem confirmação: devolve {"confirmar": texto} e nada muda;
    com confirmar=True grava assim mesmo (duas equipes no mesmo trecho)."""
    if not _one(conn, "SELECT 1 FROM equipes WHERE id=?", equipe_id):
        raise RegraViolada("Equipe não cadastrada.")
    if servico not in P.SERVICOS:
        raise RegraViolada("Serviço inválido.")
    dia = _data(data, "programação").isoformat()
    alvos = _alvos(_selecao(conn, linhas, nos))
    if not alvos:
        raise RegraViolada("Escolha no mapa ao menos um trecho.")
    if len(alvos) > LIMITE_PROGRAMACOES:
        raise RegraViolada(f"São {len(alvos)} alvos; o limite por vez é {LIMITE_PROGRAMACOES}. Divida a seleção.")
    nomes = P.nomes_vigentes(conn)
    outras = [(nomes.get((t, a), a), r["equipe_id"]) for t, a in alvos for r in conn.execute(
        "SELECT DISTINCT equipe_id FROM programacoes WHERE data=? AND alvo_tipo=? AND alvo_id=? AND equipe_id<>? AND status='PLANEJADA'",
        (dia, t, a, equipe_id))]
    if outras and not confirmar:
        lista = "; ".join(f"{R.nome_completo(n)} (equipe {eq})" for n, eq in outras[:6]) + (" e outros" if len(outras) > 6 else "")
        return {"confirmar": f"Já programado para outra equipe em {dia}: {lista}. Programar também a equipe {equipe_id}?"}
    # o carimbo de criação é a identidade do lote: com microssegundos, dois pedidos seguidos não viram um lote só
    agora, criadas, existentes = RL.agora().isoformat(timespec="microseconds"), 0, 0
    obs = str(obs or "").strip() or None
    with transacao(conn):
        for tipo, aid in alvos:
            if _one(conn, "SELECT 1 FROM programacoes WHERE data=? AND equipe_id=? AND alvo_tipo=? AND alvo_id=? AND servico=? "
                          "AND status='PLANEJADA'", dia, equipe_id, tipo, aid, servico):
                existentes += 1
                continue
            conn.execute("""INSERT INTO programacoes(data,equipe_id,alvo_tipo,alvo_id,servico,obs,criada_por,criada_em)
                            VALUES (?,?,?,?,?,?,?,?)""", (dia, equipe_id, tipo, aid, servico, obs, por, agora))
            criadas += 1
    if not criadas:
        raise RegraViolada("Nada novo: a equipe já está programada para esse serviço nesse dia em todos esses alvos.")
    return {"lote": f"{agora}|{por}|{equipe_id}|{servico}", "criadas": criadas, "ja_existiam": existentes,
            "alvos": len(alvos), "data": dia}


def cancelar_lote(conn, lote, motivo, por, a_partir_de=None):
    """Cancela as programações ainda PLANEJADAS do lote (a partir de uma data, se informada). O realizado fica."""
    partes = str(lote or "").split("|")
    if len(partes) != 4:
        raise RegraViolada("Lote inválido.")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo do cancelamento.")
    sql = "SELECT id FROM programacoes WHERE criada_em=? AND criada_por=? AND equipe_id=? AND servico=? AND status='PLANEJADA'"
    args = list(partes)
    if a_partir_de:
        sql, args = sql + " AND data>=?", args + [_data(a_partir_de, "início").isoformat()]
    ids = [r[0] for r in conn.execute(sql, args)]
    if not ids:
        raise RegraViolada("Nada a cancelar: o lote não tem programação planejada (já realizada, encerrada ou inexistente).")
    with transacao(conn):
        conn.executemany("UPDATE programacoes SET status='CANCELADA', motivo=?, encerrada_por=?, encerrada_em=? WHERE id=?",
                         [(motivo.strip(), por, _agora(), i) for i in ids])
    return len(ids)


def _realizar(conn, checkin_id, equipe_id, data, alvos):
    """Programações do dia da equipe para a seleção passam a realizadas por este check-in (o check-in novo já marcou a
    do alvo dele). Devolve quantas da seleção estão realizadas por ele."""
    n = 0
    for tipo, aid in alvos:
        conn.execute("""UPDATE programacoes SET status='REALIZADA', checkin_id=?, encerrada_em=?
                        WHERE equipe_id=? AND data=? AND alvo_tipo=? AND alvo_id=? AND status='PLANEJADA'""",
                     (checkin_id, _agora(), equipe_id, data, tipo, aid))
        n += conn.execute("SELECT COUNT(*) FROM programacoes WHERE checkin_id=? AND data=? AND alvo_tipo=? AND alvo_id=?",
                          (checkin_id, data, tipo, aid)).fetchone()[0]
    return n


def liberar(conn, data, equipe_id, linhas, nos, materiais, por, funcionarios=(), maquinas=()):
    """O almoxarife libera o material do dia para a seleção: abre o check-in da equipe (alvo = primeira linha da seleção)
    ou, se ela já tem check-in aberto nesse dia, soma a retirada a ele. As programações do dia da equipe para a seleção
    ficam realizadas por esse check-in (é o que pinta a equipe em campo no mapa)."""
    S.exigir_data_ocorrida(data, "Liberação de material")
    if not _one(conn, "SELECT 1 FROM equipes WHERE id=?", equipe_id):
        raise RegraViolada(f"Equipe '{equipe_id}' não cadastrada.")
    sel = _selecao(conn, linhas, nos)
    alvos = _alvos(sel)
    if not alvos:
        raise RegraViolada("Escolha no mapa o trecho em que a equipe vai trabalhar.")
    tipo, ref = alvos[0]
    itens = [{"material_id": m.get("material_id"), "quantidade": float(m.get("quantidade") or 0)} for m in materiais or []]
    itens = [m for m in itens if m["quantidade"] > 0]
    aberto = _one(conn, "SELECT * FROM checkins WHERE equipe_id=? AND encerrado=0 ORDER BY data, id LIMIT 1", equipe_id)
    with transacao(conn):
        if aberto and aberto["data"] == data:
            cid, novo = aberto["id"], False
            for rec, ids in (("FUNCIONARIO", funcionarios), ("MAQUINA", maquinas)):
                for i in ids or ():
                    conn.execute("INSERT OR IGNORE INTO checkin_presencas VALUES (?,?,?)", (cid, rec, int(i)))
            S.retirar_materiais(conn, cid, data, equipe_id, tipo, ref, itens)
        else:
            cid, novo = S.checkin(conn, data, equipe_id, tipo, ref, [int(i) for i in funcionarios or ()],
                                  [int(i) for i in maquinas or ()], itens), True
        n = _realizar(conn, cid, equipe_id, data, alvos)
        for t, a in alvos:                         # todos os trechos do dia (v20): o programado e o acrescentado na hora
            prog = _one(conn, "SELECT 1 FROM programacoes WHERE checkin_id=? AND alvo_tipo=? AND alvo_id=?", cid, t, a)
            conn.execute("INSERT OR IGNORE INTO checkin_alvos VALUES (?,?,?,?)", (cid, t, a, "PROGRAMACAO" if prog else "CHECKIN"))
    return {"checkin_id": cid, "novo": novo, "itens": len(itens), "programacoes_realizadas": n}


def contingencia(conn, data, equipe_id, contingencia, por, materiais=(), funcionarios=None, maquinas=None):
    """Equipe em campo sem trecho (contingência: bloquetes, calçadas): o check-in do dia sem alvo, para a presença (o
    histograma e o diário) e, se houver, a retirada de material. Sem a lista de presentes, conta todos os funcionários e
    máquinas da equipe. Fecha-se na devolução, como qualquer check-in."""
    S.exigir_data_ocorrida(data, "Contingência")
    if contingencia not in R.CONTINGENCIAS:
        raise RegraViolada("Escolha a contingência: " + ", ".join(R.CONTINGENCIAS) + ".")
    if funcionarios is None:
        funcionarios = [r[0] for r in conn.execute("SELECT id FROM funcionarios WHERE equipe_id=?", (equipe_id,))]
    if maquinas is None:
        maquinas = [r[0] for r in conn.execute("SELECT id FROM maquinas WHERE equipe_id=?", (equipe_id,))]
    itens = [{"material_id": m.get("material_id"), "quantidade": float(m.get("quantidade") or 0)} for m in materiais or []]
    cid = S.checkin(conn, data, equipe_id, funcionarios=[int(i) for i in funcionarios], maquinas=[int(i) for i in maquinas],
                    materiais=[m for m in itens if m["quantidade"] > 0], contingencia=contingencia)
    return {"checkin_id": cid}


def nao_realizada(conn, data, equipe_id, motivo, por):
    """O programado de um dia que já chegou e não aconteceu: as programações ainda PLANEJADAS da equipe nesse dia passam a
    NAO_REALIZADA, com o motivo (o dia futuro se cancela pelo lote)."""
    dia = _data(data, "dia").isoformat()
    if dia > RL.hoje().isoformat():
        raise RegraViolada("Dia que ainda não chegou: cancele a programação pelo lote.")
    ids = [r[0] for r in conn.execute("SELECT id FROM programacoes WHERE equipe_id=? AND data=? AND status='PLANEJADA'",
                                      (equipe_id, dia))]
    if not ids:
        raise RegraViolada("Nada planejado para a equipe nesse dia (já realizado, encerrado ou sem programação).")
    with transacao(conn):
        for i in ids:
            P.encerrar(conn, i, "NAO_REALIZADA", motivo, por)
    return {"nao_realizadas": len(ids)}


def reservar(conn, data, equipe_id, linhas, nos, materiais, por):
    """Para um dia que ainda não chegou: reserva o material da seleção para a equipe (não sai do almoxarifado; o check-in
    daquele dia consome a reserva)."""
    sel = _selecao(conn, linhas, nos)
    alvos = _alvos(sel)
    if not alvos:
        raise RegraViolada("Escolha no mapa o trecho em que a equipe vai trabalhar.")
    _data(data, "reserva")
    itens = [m for m in materiais or [] if float(m.get("quantidade") or 0) > 0]
    if not itens:
        raise RegraViolada("Informe a quantidade de ao menos um material.")
    tipo, ref = alvos[0]
    with transacao(conn):
        ids = [S.reservar(conn, data, equipe_id, m.get("material_id"), float(m["quantidade"]), tipo, ref, por) for m in itens]
    return {"reservas": ids}


# ------------------------------------------------------------------ estado do mapa
def estado(conn, data=None, dias=21):
    """Para pintar o mapa do Dados da obra a partir de `data` (hoje): o programado por alvo (equipe, serviço e período),
    onde cada equipe está no dia (check-in aberto e o que ele cobre), os check-ins abertos com o material de cada equipe
    (para a devolução) e os lotes de programação do período."""
    hoje = (data or RL.hoje().isoformat())[:10]
    ate = (_data(hoje, "consulta") + timedelta(days=int(dias))).isoformat()
    nomes = P.nomes_vigentes(conn)
    rows = _rows(conn.execute("SELECT * FROM programacoes WHERE data BETWEEN ? AND ? AND status IN ('PLANEJADA','REALIZADA') "
                              "ORDER BY data, id", (hoje, ate)))
    programado = {}
    for p in rows:
        n = nomes.get((p["alvo_tipo"], p["alvo_id"]))
        if not n or p["status"] != "PLANEJADA":
            continue
        x = programado.setdefault(n, {}).setdefault((p["equipe_id"], p["servico"]), {
            "equipe": p["equipe_id"], "servico": p["servico"], "tipo": p["alvo_tipo"], "de": p["data"], "ate": p["data"], "dias": 0,
            "hoje": False})
        x["de"], x["ate"], x["dias"] = min(x["de"], p["data"]), max(x["ate"], p["data"]), x["dias"] + 1
        x["hoje"] = x["hoje"] or p["data"] == hoje
    return {"hoje": hoje, "ate": ate,
            "programado": {n: sorted(v.values(), key=lambda x: (x["de"], x["equipe"])) for n, v in programado.items()},
            "em_campo": P.em_campo(conn, hoje, nomes), "checkins": _checkins(conn, nomes, hoje),
            "lotes": _agrupar_lotes(rows, nomes)}
