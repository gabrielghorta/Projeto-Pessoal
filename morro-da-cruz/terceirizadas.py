"""Topografia e cadastro de campo: serviços de equipes terceirizadas, registrados pela engenharia em abas próprias.

Só leitura: as filas do que falta liberar e do que falta levantar e os registros recentes. Gravar continua em
servicos.registrar_etapa_complementar (liberação topográfica) e servicos.registrar_cadastro_campo (levantamento).
As regras de cobertura são as mesmas da ficha do trecho (servicos.situacao_complementar e servicos.fases_cadastro).
"""
from datetime import date, timedelta

import regras as R
import relogio as RL
import servicos as S
from servicos import RegraViolada, _rows

SERVICOS_LIBERACAO = ("LOCACAO", "ESCAVACAO", "ASSENTAMENTO")      # programados que dependem da nota de serviço


def _trechos(conn, frente=None):
    if frente and not conn.execute("SELECT 1 FROM equipes WHERE id=?", (frente,)).fetchone():
        raise RegraViolada(f"Frente '{frente}' não existe.")
    sql, args = "SELECT id, ponto, frente_id, extensao_m, metodologia FROM trechos WHERE vigente=1", []
    if frente:
        sql, args = sql + " AND frente_id=?", [frente]
    return {r["id"]: dict(r) for r in conn.execute(sql, args)}


def _por_trecho(linhas):
    out = {}
    for tid, a, b, d in linhas:
        out.setdefault(tid, []).append((a, b, d))
    return out


def _unir(lst, ate=None):
    return R.unir_intervalos([(a, b) for a, b, d in lst if ate is None or d <= ate])


def _faltas(cobrir, cobertura):
    return [f for a, b in cobrir for f in R.fora_da_cobertura((a, b), cobertura)]


def _m(lst):
    return round(R.comprimento(lst), 2)


def topografia(conn, frente=None, hoje=None, dias=7, limite=60):
    """O que falta a topografia liberar (nota de serviço / locação): programado para os próximos `dias` sem liberação,
    executado (assentado ou escavado) sem liberação até a data, trechos liberados só em parte e as liberações recentes."""
    hoje = hoje or RL.hoje().isoformat()
    ate = (date.fromisoformat(hoje) + timedelta(days=dias)).isoformat()
    tr = _trechos(conn, frente)
    lib = _por_trecho(conn.execute("""SELECT trecho_id, ini_m, fim_m, data FROM etapas_complementares
                                      WHERE etapa='LIBERACAO_TOPOGRAFICA' AND anulado_em IS NULL"""))
    programados = []
    for p in _rows(conn.execute(f"""SELECT * FROM programacoes WHERE status='PLANEJADA' AND alvo_tipo='TRECHO'
                                    AND data BETWEEN ? AND ? AND servico IN ({','.join('?' * len(SERVICOS_LIBERACAO))})
                                    ORDER BY data, id""", (hoje, ate, *SERVICOS_LIBERACAO))):
        t = tr.get(p["alvo_id"])
        if not t:
            continue
        iv = (p["ini_m"], p["fim_m"]) if p["ini_m"] is not None else (0.0, float(t["extensao_m"]))
        falta = R.fora_da_cobertura(iv, _unir(lib.get(t["id"], [])))
        if falta:
            programados.append({"programacao_id": p["id"], "data": p["data"], "equipe_id": p["equipe_id"], "servico": p["servico"],
                                "trecho_id": t["id"], "ponto": t["ponto"], "frente_id": t["frente_id"], "ini_m": iv[0], "fim_m": iv[1],
                                "falta": falta, "falta_m": _m(falta)})
    executados = {}
    for tid, etapa, a, b, d in conn.execute(
            f"""SELECT trecho_id, etapa, ini_m, fim_m, data FROM intervalos_execucao WHERE {S.EFETIVO} AND etapa='ASSENTADO'
                UNION ALL SELECT trecho_id, etapa, ini_m, fim_m, data FROM etapas_complementares
                WHERE etapa='ESCAVADO' AND anulado_em IS NULL"""):
        if tid not in tr:
            continue
        falta = R.fora_da_cobertura((a, b), _unir(lib.get(tid, []), d))
        if falta:
            x = executados.setdefault(tid, {"trecho_id": tid, "ponto": tr[tid]["ponto"], "frente_id": tr[tid]["frente_id"],
                                            "faltas": [], "falta_m": 0.0})
            x["faltas"].append({"etapa": etapa, "data": d, "faixas": falta})
            x["falta_m"] = round(x["falta_m"] + R.comprimento(falta), 2)
    parciais, liberado_m, total, com_liberacao = [], 0.0, 0, 0
    for tid, lst in lib.items():
        t = tr.get(tid)
        if not t:
            continue
        cob = _unir(lst)
        liberado_m += R.comprimento(cob)
        com_liberacao += 1
        lac = R.lacunas(cob, float(t["extensao_m"]))
        if R.comprimento(lac) > R.TOL_M:
            parciais.append({"trecho_id": tid, "ponto": t["ponto"], "frente_id": t["frente_id"], "extensao_m": t["extensao_m"],
                             "liberado_m": _m(cob), "liberado": cob, "falta": lac, "falta_m": _m(lac)})
        else:
            total += 1
    recentes = [r for r in _rows(conn.execute(
        """SELECT e.*, t.ponto, t.frente_id FROM etapas_complementares e JOIN trechos t ON t.id=e.trecho_id
           WHERE e.etapa='LIBERACAO_TOPOGRAFICA' ORDER BY e.data DESC, e.id DESC LIMIT ?""", (limite * 3,)))
                if r["trecho_id"] in tr][:limite]
    exec_lista = sorted(executados.values(), key=lambda x: (-x["falta_m"], x["ponto"]))
    rede_m = sum(float(t["extensao_m"]) for t in tr.values())         # o olhar macro: feito × falta na rede da frente
    return {"hoje": hoje, "ate": ate, "frente": frente,
            "programados_sem_liberacao": programados, "executado_sem_liberacao": exec_lista,
            "parciais": sorted(parciais, key=lambda x: (-x["falta_m"], x["ponto"])), "recentes": recentes,
            "totais": {"trechos_liberados": total, "trechos_parciais": len(parciais), "liberado_m": round(liberado_m, 2),
                       "programados_sem_liberacao": len(programados), "executado_sem_liberacao": len(exec_lista),
                       "executado_sem_liberacao_m": round(sum(x["falta_m"] for x in exec_lista), 2),
                       "rede_m": round(rede_m, 2), "trechos": len(tr), "falta_liberar_m": round(max(rede_m - liberado_m, 0.0), 2),
                       "trechos_sem_liberacao": len(tr) - com_liberacao}}


def cadastro_campo(conn, frente=None, limite=60):
    """O que falta a equipe de cadastro levantar: assentado sem levantamento (com a vala ainda aberta ou já reaterrado),
    os reaterros marcados "sem cadastro até a data" (alerta que um levantamento tardio não apaga) e os registros recentes."""
    tr = _trechos(conn, frente)
    ivs = {}
    for tid, etapa, a, b, d in conn.execute(f"""SELECT trecho_id, etapa, ini_m, fim_m, data FROM intervalos_execucao
                                                WHERE {S.EFETIVO} AND trecho_id IN (SELECT id FROM trechos WHERE vigente=1)"""):
        ivs.setdefault(tid, {}).setdefault(etapa, []).append((a, b, d))
    alerta = dict(conn.execute(f"""SELECT trecho_id, COUNT(*) FROM intervalos_execucao WHERE {S.EFETIVO}
                                   AND sem_cadastro_campo=1 GROUP BY trecho_id"""))
    legado = {r[0] for r in conn.execute(f"SELECT DISTINCT ap.alvo_id {S._SQL_LEGADO}")}
    fila, completos, assentado_m, levantado_m = [], 0, 0.0, 0.0
    for tid, e in ivs.items():
        t = tr.get(tid)
        if not t:
            continue
        ass, cad, rea = (_unir(e.get(k, [])) for k in ("ASSENTADO", "CADASTRO_CAMPO", "REATERRADO"))
        assentado_m, levantado_m = assentado_m + R.comprimento(ass), levantado_m + R.comprimento(cad)
        if cad and R.comprimento(cad) >= float(t["extensao_m"]) - R.TOL_M:
            completos += 1
        falta = _faltas(ass, cad)
        if not falta and not alerta.get(tid):
            continue
        fechado = _faltas(falta, R.lacunas(rea, float(t["extensao_m"]))) if t["metodologia"] != "MND" else []
        aberto = _faltas(falta, R.unir_intervalos(fechado))
        fila.append({"trecho_id": tid, "ponto": t["ponto"], "frente_id": t["frente_id"], "extensao_m": t["extensao_m"],
                     "metodologia": t["metodologia"], "assentado_m": _m(ass), "cadastro_m": _m(cad),
                     "falta": falta, "falta_m": _m(falta), "vala_aberta": aberto, "vala_aberta_m": _m(aberto),
                     "reaterrado_sem_cadastro": fechado, "reaterrado_sem_cadastro_m": _m(fechado),
                     "alertas_reaterro": alerta.get(tid, 0), "legado_pendente": tid in legado})
    recentes = [r for r in _rows(conn.execute(
        """SELECT i.id, i.trecho_id, i.ini_m, i.fim_m, i.data, i.informado_por, i.referencia, i.apontamento_id, i.equipe_id,
                  i.verificado_por, i.verificado_em, i.anulado_por, i.registrado_em, t.ponto, t.frente_id
           FROM intervalos_execucao i JOIN trechos t ON t.id=i.trecho_id
           WHERE i.etapa='CADASTRO_CAMPO' ORDER BY i.data DESC, i.id DESC LIMIT ?""", (limite * 3,)))
                if r["trecho_id"] in tr][:limite]
    fila.sort(key=lambda x: (-x["vala_aberta_m"], -x["reaterrado_sem_cadastro_m"], x["ponto"]))
    rede_m = sum(float(t["extensao_m"]) for t in tr.values())         # o olhar macro: feito × falta na rede da frente
    return {"frente": frente, "fila": fila, "recentes": recentes,
            "totais": {"vala_aberta_m": round(sum(x["vala_aberta_m"] for x in fila), 2),
                       "reaterrado_sem_cadastro_m": round(sum(x["reaterrado_sem_cadastro_m"] for x in fila), 2),
                       "trechos_pendentes": sum(1 for x in fila if x["falta_m"] > 0),
                       "alertas_reaterro": sum(alerta.get(t, 0) for t in tr), "trechos_completos": completos,
                       "rede_m": round(rede_m, 2), "assentado_m": round(assentado_m, 2), "levantado_m": round(levantado_m, 2),
                       "falta_levantar_m": round(sum(x["falta_m"] for x in fila), 2),
                       "nao_assentado_m": round(max(rede_m - assentado_m, 0.0), 2)}}
