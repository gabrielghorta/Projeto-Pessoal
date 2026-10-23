"""Planejamento das equipes e camadas do mapa (módulo D).

* Programação: o PLANEJADO (equipe, dia, trecho/nó, serviço, intervalo e materiais previstos). Não é presença nem
  execução. O check-in da equipe naquele dia e alvo a torna REALIZADA (servicos.checkin); o que não aconteceu é
  encerrado como NÃO REALIZADA ou CANCELADA, com motivo. Nada é apagado.
* Faltantes: materiais previstos na programação × reservado para a equipe naquele dia × disponível × a receber.
* Camadas do mapa, todas a partir dos registros efetivos: planejado, material disponibilizado (reserva ou com a
  equipe), execução (andamento e informado × verificado, em servicos.estado_mapa), cadastro e pendências.
"""
from datetime import date, timedelta

import compras as C
import regras as R
import relogio as RL
import servicos as S
from servicos import RegraViolada, _agora, _one, _rows, transacao

SERVICOS = {"LOCACAO": "Locação / topografia", "ESCAVACAO": "Escavação", "ASSENTAMENTO": "Assentamento",
            "CADASTRO_CAMPO": "Cadastro de campo", "REATERRO": "Reaterro", "RECOMPOSICAO": "Recomposição",
            "LIGACOES": "Ligações prediais", "INTERLIGACAO": "Interligação / manobra", "OUTRO": "Outro"}
TOL = 1e-6


def programar(conn, data, equipe_id, alvo_tipo, ref, servico, por, ini_m=None, fim_m=None, materiais=(), obs=None):
    if not data:
        raise RegraViolada("Informe a data.")
    if not _one(conn, "SELECT 1 FROM equipes WHERE id=?", equipe_id):
        raise RegraViolada("Equipe não cadastrada.")
    if servico not in SERVICOS:
        raise RegraViolada("Serviço inválido.")
    a = S.alvo(conn, alvo_tipo, ref, operacao=True)
    if ini_m not in (None, "") or fim_m not in (None, ""):
        if a["alvo_tipo"] != "TRECHO":
            raise RegraViolada("Intervalo só se aplica a trecho.")
        ini_m, fim_m = float(ini_m), float(fim_m)
        if not (0 <= ini_m < fim_m <= float(a["extensao_m"]) + R.TOL_M):
            raise RegraViolada(f"Intervalo {ini_m:g}–{fim_m:g} m fora do trecho (0–{float(a['extensao_m']):g} m).")
    else:
        ini_m = fim_m = None
    if _one(conn, "SELECT 1 FROM programacoes WHERE data=? AND equipe_id=? AND alvo_tipo=? AND alvo_id=? AND servico=? AND status='PLANEJADA'",
            data, equipe_id, a["alvo_tipo"], a["id"], servico):
        raise RegraViolada("Esta programação já existe (mesma equipe, dia, alvo e serviço).")
    linhas = []
    for m in materiais or []:
        q = float(m.get("quantidade") or 0)
        if q <= 0:
            continue
        if not _one(conn, "SELECT 1 FROM materiais WHERE id=?", m.get("material_id")):
            raise RegraViolada(f"Material '{m.get('material_id')}' não cadastrado.")
        linhas.append((m["material_id"], q))
    with transacao(conn):
        pid = conn.execute(
            """INSERT INTO programacoes(data,equipe_id,alvo_tipo,alvo_id,servico,ini_m,fim_m,obs,criada_por,criada_em)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (data, equipe_id, a["alvo_tipo"], a["id"], servico, ini_m, fim_m, obs, por, _agora())).lastrowid
        for mid, q in linhas:
            conn.execute("INSERT INTO programacao_materiais(programacao_id,material_id,quantidade) VALUES (?,?,?)", (pid, mid, q))
    return pid


def encerrar(conn, programacao_id, status, motivo, por):
    p = _one(conn, "SELECT * FROM programacoes WHERE id=?", programacao_id)
    if not p or p["status"] != "PLANEJADA":
        raise RegraViolada("Só programação PLANEJADA pode ser encerrada.")
    if status not in ("NAO_REALIZADA", "CANCELADA"):
        raise RegraViolada("Encerramento: NAO_REALIZADA ou CANCELADA.")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo.")
    conn.execute("UPDATE programacoes SET status=?, motivo=?, encerrada_por=?, encerrada_em=? WHERE id=?",
                 (status, motivo.strip(), por, _agora(), programacao_id))


def _frente_do_alvo(conn, tipo, aid):
    tab = "trechos" if tipo == "TRECHO" else "atividades"
    r = conn.execute(f"SELECT frente_id FROM {tab} WHERE id=?", (aid,)).fetchone()
    return r[0] if r else None


def programacoes(conn, ini, fim, frente=None, equipe=None):
    sql, args = "SELECT * FROM programacoes WHERE data BETWEEN ? AND ?", [ini, fim]
    if equipe:
        sql, args = sql + " AND equipe_id=?", args + [equipe]
    out = []
    for p in _rows(conn.execute(sql + " ORDER BY data, equipe_id, id", args)):
        p["frente_id"] = _frente_do_alvo(conn, p["alvo_tipo"], p["alvo_id"])
        if frente and p["frente_id"] != frente:
            continue
        p["alvo_nome"] = S.nome_alvo(conn, p["alvo_tipo"], p["alvo_id"])
        p["servico_nome"] = SERVICOS.get(p["servico"], p["servico"])
        p["materiais"] = _rows(conn.execute("SELECT material_id, quantidade FROM programacao_materiais WHERE programacao_id=?", (p["id"],)))
        out.append(p)
    return out


def resumo(conn, ini, fim, frente=None, equipe=None):
    ps = programacoes(conn, ini, fim, frente, equipe)
    cont = {s: sum(1 for p in ps if p["status"] == s) for s in ("PLANEJADA", "REALIZADA", "NAO_REALIZADA", "CANCELADA")}
    passadas = [p for p in ps if p["data"] < RL.hoje().isoformat() and p["status"] != "CANCELADA"]
    return {"contagem": cont, "realizadas_no_passado": sum(1 for p in passadas if p["status"] == "REALIZADA"), "programadas_no_passado": len(passadas)}


def a_receber(conn, material_id):
    """Pendente de entrega em pedidos emitidos (compras)."""
    total = 0.0
    for (pid,) in conn.execute("""SELECT DISTINCT p.id FROM pedidos_compra p JOIN pedido_itens i ON i.pedido_id=p.id
                                  WHERE p.status='EMITIDO' AND i.material_id=?""", (material_id,)):
        total += sum(i["pendente_entrega"] for i in C.situacao_pedido(conn, pid)["itens"] if i["material_id"] == material_id)
    return round(total, 6)


def faltantes(conn, ini, fim, frente=None):
    """Por material previsto em programações PLANEJADAS do período: previsto, reservado para essas programações (reserva
    da equipe no dia), disponível agora, a receber e faltante = previsto − reservado − disponível (nunca negativo)."""
    agg = {}
    for p in programacoes(conn, ini, fim, frente):
        if p["status"] != "PLANEJADA":
            continue
        for m in p["materiais"]:
            a = agg.setdefault(m["material_id"], {"material_id": m["material_id"], "previsto": 0.0, "reservado": 0.0, "pares": set()})
            a["previsto"] += m["quantidade"]
            a["pares"].add((p["equipe_id"], p["data"]))
    out = []
    for mid, a in sorted(agg.items()):
        res = sum(S.reservado(conn, mid, eq, d) for eq, d in a["pares"])
        disp = S.disponivel(conn, mid)
        mat = _one(conn, "SELECT descricao, unidade, propriedade FROM materiais WHERE id=?", mid)
        out.append({"material_id": mid, **mat, "previsto": round(a["previsto"], 6), "reservado": round(res, 6),
                    "disponivel": round(disp, 6), "a_receber": a_receber(conn, mid),
                    "faltante": round(max(a["previsto"] - res - max(disp, 0), 0), 6)})
    return out


def nomes_vigentes(conn):
    """{(alvo_tipo, id estável): nome visível} dos trechos e atividades vigentes."""
    nomes = {("TRECHO", r[0]): r[1] for r in conn.execute("SELECT id, ponto FROM trechos WHERE vigente=1")}
    nomes.update({("ATIVIDADE", r[0]): r[1] for r in conn.execute(
        "SELECT a.id, a.nomenclatura FROM atividades a JOIN elementos e ON e.id=a.elemento_id WHERE a.vigente=1 AND e.vigente=1")})
    return nomes


def em_campo(conn, data=None, nomes=None):
    """Onde cada equipe está no dia: o alvo do check-in aberto e os alvos das programações que esse check-in realizou
    (a liberação de material pelo mapa do Dados da obra cobre vários trechos de uma vez).
    {nome visível: {"equipe": id, "checkin_id": id}}."""
    data = data or RL.hoje().isoformat()
    nomes = nomes if nomes is not None else nomes_vigentes(conn)
    out = {}
    for cid, eq, tipo, aid in conn.execute("SELECT id, equipe_id, alvo_tipo, alvo_id FROM checkins WHERE encerrado=0 AND data=? "
                                           "ORDER BY id", (data,)).fetchall():
        alvos = ([(tipo, aid)] if aid else []) + [tuple(r) for r in conn.execute(
            "SELECT alvo_tipo, alvo_id FROM programacoes WHERE checkin_id=? ORDER BY id", (cid,))]
        for a in alvos:
            if a in nomes:
                out.setdefault(nomes[a], {"equipe": eq, "checkin_id": cid})
    return out


def camadas_mapa(conn, hoje=None, dias=7):
    """Por nome visível (objetos vigentes): planejado (próximos dias), material disponibilizado, cadastro, pendências,
    liberação topográfica e onde cada equipe está hoje (em_campo)."""
    hoje = hoje or RL.hoje().isoformat()
    ate = (date.fromisoformat(hoje) + timedelta(days=dias)).isoformat()
    nomes = nomes_vigentes(conn)
    planejado = {}
    for p in _rows(conn.execute("SELECT * FROM programacoes WHERE status='PLANEJADA' AND data BETWEEN ? AND ? ORDER BY data",
                                (hoje, ate))):
        n = nomes.get((p["alvo_tipo"], p["alvo_id"]))
        if n:
            x = planejado.setdefault(n, {"data": p["data"], "hoje": False, "equipes": [], "servicos": []})
            x["hoje"] = x["hoje"] or p["data"] == hoje
            x["equipes"] = sorted(set(x["equipes"]) | {p["equipe_id"]})
            x["servicos"] = sorted(set(x["servicos"]) | {SERVICOS.get(p["servico"], p["servico"])})
    material = {}
    for r in conn.execute("SELECT DISTINCT alvo_tipo, alvo_id FROM reservas WHERE status='ATIVA' AND alvo_id IS NOT NULL"):
        if (r[0], r[1]) in nomes:
            material[nomes[(r[0], r[1])]] = "RESERVADO"
    for r in conn.execute("""SELECT DISTINCT m.alvo_tipo, m.alvo_id FROM movimentos m JOIN checkins c ON c.id=m.checkin_id
                              WHERE c.encerrado=0 AND m.tipo IN ('CUSTODIA','TRANSF_ENTRADA') AND m.alvo_id IS NOT NULL
                                AND m.id NOT IN (SELECT movimento_id FROM estornos)"""):
        if (r[0], r[1]) in nomes:
            material[nomes[(r[0], r[1])]] = "COM_EQUIPE"
    cadastro = {}
    for tid, cob in _levantamentos(conn).items():
        n = nomes.get(("TRECHO", tid))
        if n:
            cadastro[n] = cob
    for r in conn.execute("SELECT trecho_id, etapa FROM cadastro"):
        n = nomes.get(("TRECHO", r[0]))
        if n:
            cadastro[n] = r[1]
    pend = {}
    for r in conn.execute("SELECT alvo_tipo, alvo_id, COUNT(*) FROM ocorrencias WHERE resolvida_em IS NULL GROUP BY alvo_tipo, alvo_id"):
        n = nomes.get((r[0], r[1]))
        if n:
            pend[n] = pend.get(n, 0) + r[2]
    for r in conn.execute(f"SELECT trecho_id, COUNT(*) FROM intervalos_execucao WHERE {S.EFETIVO} AND sem_cadastro_campo=1 GROUP BY trecho_id"):
        n = nomes.get(("TRECHO", r[0]))
        if n:
            pend[n] = pend.get(n, 0) + r[1]
    for r in conn.execute(f"SELECT DISTINCT ap.alvo_id {S._SQL_LEGADO}"):
        n = nomes.get(("TRECHO", r[0]))
        if n:
            pend[n] = pend.get(n, 0) + 1
    # liberação topográfica (nota de serviço/locação registrada, não anulada): trecho todo ou só uma parte
    liberado = {}
    ext = {r[0]: r[1] for r in conn.execute("SELECT id, extensao_m FROM trechos WHERE vigente=1")}
    for r in conn.execute("""SELECT trecho_id, SUM(fim_m - ini_m) FROM etapas_complementares
                              WHERE etapa='LIBERACAO_TOPOGRAFICA' AND anulado_em IS NULL GROUP BY trecho_id"""):
        n = nomes.get(("TRECHO", r[0]))
        if n:
            liberado[n] = "TOTAL" if r[1] >= (ext.get(r[0]) or 0) - 0.01 else "PARCIAL"
    return {"planejado": planejado, "material": material, "cadastro": cadastro, "pendencias": pend, "liberado": liberado,
            "em_campo": em_campo(conn, hoje, nomes), "hoje": hoje, "ate": ate}


def _levantamentos(conn):
    out = {}
    ext = {r[0]: r[1] for r in conn.execute("SELECT id, extensao_m FROM trechos WHERE vigente=1")}
    cob = {}
    for r in conn.execute(f"SELECT trecho_id, ini_m, fim_m FROM intervalos_execucao WHERE {S.EFETIVO} AND etapa='CADASTRO_CAMPO'"):
        cob.setdefault(r[0], []).append((r[1], r[2]))
    for tid, lst in cob.items():
        if tid in ext:
            out[tid] = "LEVANTAMENTO_COMPLETO" if R.comprimento(lst) >= float(ext[tid]) - R.TOL_M else "LEVANTAMENTO_PARCIAL"
    return out
