"""Medição e faturamento (módulo E) — só o que tem fonte e aprovação confirmadas; o resto fica identificado e bloqueado.

* Parcela única: a mesma parcela (alvo × serviço × item) não entra em duas medições do mesmo tipo (servicos._lancar,
  chave única no banco). Aqui: o relatório de duplicidades e as parcelas já medidas por item do BM.
* Elegibilidade por período: o que foi executado e verificado no período × o que está proposto nesta medição × o que
  falta para propor. Execução parcial não é proposta (D-30): aparece só como conferência.
* Regimes: material aplicado e recebido no período aparece por propriedade, BLOQUEADO até a matriz de regimes (D-53,
  D-54). Material recebido não vira quantidade faturável. Nenhum percentual (80/20 ou outro) é aplicado.
* Conferência interna da engenharia antes do fechamento (D-59, provisório): retrato das evidências e pendências de cada
  lançamento e assinatura dos lançamentos conferidos. Não é aprovação da Caesb. A medição OFICIAL segue bloqueada (D-56).
"""
import json
from collections import defaultdict

import regras as R
import servicos as S
from servicos import RegraViolada, _agora, _one, _rows, transacao


# ------------------------------------------------------------------ regras: confirmadas, provisórias e bloqueadas
def regras(conn):
    """Cada regra de cálculo com sua situação e decisão. BLOQUEADA = lançamento fica PENDENTE, fora do valor."""
    cfg = S.mapa_servicos()
    out = []
    add = lambda regra, situacao, efeito, fonte=None, decisao=None: out.append(
        {"regra": regra, "situacao": situacao, "efeito": efeito, "fonte": fonte, "decisao": decisao})
    sem_item = []
    for s in cfg["gaveta1"]:
        if s["status"] != "CONFIRMADO" or not s["itens"]:
            sem_item.append(s["servico"])
            continue
        if "{codigo_bm}" in "".join(s["itens"]):
            falta = conn.execute(
                """SELECT COUNT(*) FROM trechos t WHERE t.vigente=1 AND NOT EXISTS (SELECT 1 FROM bm_itens b WHERE b.vigente=1
                   AND b.planilha='VERTICAL' AND b.item='2.2_' || t.codigo_bm)""").fetchone()[0]
            add(f"{s['servico']} → item do BM pelo código da 06.1 (2.2_<código>)", "CONFIRMADA" if not falta else "VÍNCULO INCOMPLETO",
                "proposto pelo OK interno do trecho completo" + (f"; {falta} trecho(s) sem item correspondente no BM vigente ficam PENDENTES"
                                                                 if falta else ""), s.get("fonte"))
            continue
        ausentes = [k for k in s["itens"] if not S._bm_item(conn, k)]
        if ausentes:
            add(f"{s['servico']} → {', '.join(s['itens'])}", "VÍNCULO INCOMPLETO", f"item(ns) {', '.join(ausentes)} fora do BM vigente: PENDENTE",
                s.get("fonte"), "D-51" if len(s["itens"]) > 1 else None)
        elif len(s["itens"]) > 1:
            add(f"{s['servico']} → {' + '.join(s['itens'])} (rateio pela proporção contratual)", "HIPÓTESE",
                "proposto como estimativa; impede a medição oficial", s.get("fonte"), "D-51")
        else:
            add(f"{s['servico']} → {s['itens'][0]}", "CONFIRMADA", "proposto pelo OK interno do trecho completo", s.get("fonte"))
    if sem_item:
        add(f"Serviços sem item de BM comprovado ({len(sem_item)}): " + ", ".join(sem_item), "BLOQUEADA",
            "quantidade apurada e lançada como PENDENTE, fora do valor (não é R$ 0 contratual)", None, "D-50")
    add("Solda: item de BM e regra de quantidade", "BLOQUEADA",
        "PENDENTE com a quantidade de soldas verificadas e APROVADAS; a estimativa ⌈L/6⌉ não é usada", None, "D-31")
    add("Assentamento MND (itens 5.16.x)", "BLOQUEADA", "PENDENTE; não é substituído pelo item de vala aberta", None, "D-52")
    add("Material: categorias do SL0327 e regime de faturamento (inclui conexões PEAD)", "BLOQUEADA",
        "nenhum material entra em valor; nenhum percentual (80/20 ou outro) é aplicado; recebido ≠ faturável", None, "D-53 · D-54")
    rec = cfg["recomposicao"]
    add(f"Recomposição calçada/asfalto → {', '.join(rec['itens_por_tipo'].values())}",
        "CONFIRMADA" if rec["status"] == "CONFIRMADO" else "BLOQUEADA",
        "lançada na gaveta 4 só depois do OK interno" + ("" if rec["status"] == "CONFIRMADO" else "; item A CONFIRMAR: PENDENTE"),
        None, None if rec["status"] == "CONFIRMADO" else "D-50")
    add(f"Cadastro → {cfg['cadastro']['item']} pela extensão do trecho, na aprovação GDOC (memorando ESET)", "PROVISÓRIA",
        "gaveta 3, só na medição de TESTE", cfg["cadastro"].get("nota"), "D-58")
    add("Rede medida por intervalo dentro do mês", "PROVISÓRIA",
        "só trecho completo com OK interno é proposto; execução parcial aparece como conferência", None, "D-30")
    add("Teto por subgrupo do BM", "HIPÓTESE", "desconta o excedente na simulação (controle interno proposto)", None, "D-57")
    add("Reajuste: revisão da parcela elegível (REV03 × REV04) e pedido protocolado", "HIPÓTESE",
        "simulado sobre o total limitado, sem frações elegíveis; impede a medição oficial", None, "D-55")
    add("Estorno de lançamento depois do OK interno", "BLOQUEADA", "não há estorno de proposta; a retificação depois do OK é recusada",
        None, "D-16")
    add("Conferência interna da engenharia antes de fechar", "PROVISÓRIA",
        "fechamento exige conferência CONFORME sobre os lançamentos atuais", None, "D-59")
    add("Medição OFICIAL", "BLOQUEADA",
        "só medição de TESTE (parâmetro medicao_oficial_liberada = " + ("SIM" if S.medicao_oficial_liberada(conn) else "NAO")
        + "); o pacote no modelo oficial do BM (juntada, nª MC, FF, gráficos) sai marcado TESTE – NÃO OFICIAL", None, "D-56")
    return out


# ------------------------------------------------------------------ parcelas já medidas e duplicidade
def duplicidades(conn, medicao_id=None):
    """Mesmo alvo × serviço (mesma gaveta) em mais de uma medição do mesmo tipo — inclusive de antes da chave única."""
    out = []
    for r in conn.execute(
            """SELECT m.tipo, l.gaveta, l.servico, l.alvo_tipo, l.alvo_id, GROUP_CONCAT(DISTINCT m.numero) numeros,
                      GROUP_CONCAT(DISTINCT l.medicao_id) ids
               FROM medicao_lancamentos l JOIN medicoes m ON m.id=l.medicao_id WHERE l.alvo_id IS NOT NULL
                 AND l.id NOT IN (SELECT origem_id FROM medicao_lancamentos WHERE origem_id IS NOT NULL)
               GROUP BY m.tipo, l.gaveta, l.servico, l.alvo_tipo, l.alvo_id HAVING COUNT(DISTINCT l.medicao_id) > 1""").fetchall():
        ids = {int(x) for x in r["ids"].split(",")}
        if medicao_id is None or medicao_id in ids:
            out.append({"tipo": r["tipo"], "gaveta": r["gaveta"], "servico": r["servico"], "alvo_tipo": r["alvo_tipo"],
                        "alvo_id": r["alvo_id"], "alvo_nome": S.nome_alvo(conn, r["alvo_tipo"], r["alvo_id"]),
                        "medicoes": sorted(int(x) for x in r["numeros"].split(","))})
    return out


def acumulado_itens(conn, medicao_id):
    """Por item do BM com lançamento PROPOSTO: quantidade do contrato, já medida antes, nesta, acumulada e saldo."""
    med = _one(conn, "SELECT * FROM medicoes WHERE id=?", medicao_id)
    q = defaultdict(lambda: [0.0, 0.0])
    for r in conn.execute(
            """SELECT COALESCE(l.item_congelado, b.item) item, l.quantidade, m.numero FROM medicao_lancamentos l
               JOIN medicoes m ON m.id=l.medicao_id JOIN bm_itens b ON b.id=l.bm_item_id
               WHERE l.status='PROPOSTO' AND m.tipo=? AND m.numero <= ?""", (med["tipo"], med["numero"])):
        q[r["item"]][0 if r["numero"] < med["numero"] else 1] += r["quantidade"]
    out = []
    for item, (ant, nesta) in sorted(q.items()):
        if not nesta and not ant:
            continue
        b = S._bm_item(conn, item) or {}
        contrato = b.get("quantidade")
        acum = ant + nesta
        out.append({"item": item, "descricao": b.get("descricao"), "unidade": b.get("unidade"), "contrato": contrato,
                    "anterior": round(ant, 4), "nesta": round(nesta, 4), "acumulado": round(acum, 4),
                    "saldo": round((contrato or 0) - acum, 4) if contrato is not None else None,
                    "excede_contrato": contrato is not None and acum > float(contrato) + R.TOL_M})
    return out


# ------------------------------------------------------------------ elegibilidade por período
def _m(lst):
    return round(R.comprimento(R.unir_intervalos(lst)), 3)


def elegibilidade(conn, medicao_id):
    """O que o período produziu e o que pode ou não ser proposto nesta medição, a partir dos registros efetivos."""
    med = _one(conn, "SELECT * FROM medicoes WHERE id=?", medicao_id)
    if not med:
        raise RegraViolada("Medição não encontrada.")
    ini, fim = med["periodo_ini"], med["periodo_fim"]
    no_periodo = defaultdict(lambda: {"ASSENTADO": [], "ASSENTADO_VER": [], "REATERRADO": [], "CADASTRO_CAMPO": []})
    for i in conn.execute(f"""SELECT trecho_id, etapa, ini_m, fim_m, verificado_em FROM intervalos_execucao
                              WHERE {S.EFETIVO} AND data BETWEEN ? AND ?""", (ini, fim)):
        d = no_periodo[i["trecho_id"]]
        d[i["etapa"]].append((i["ini_m"], i["fim_m"]))
        if i["etapa"] == "ASSENTADO" and i["verificado_em"]:
            d["ASSENTADO_VER"].append((i["ini_m"], i["fim_m"]))
    ex = {(r["alvo_tipo"], r["alvo_id"]): dict(r) for r in conn.execute("SELECT * FROM execucao")}
    ativos_periodo = {(r[0], r[1]) for r in conn.execute(
        "SELECT DISTINCT alvo_tipo, alvo_id FROM apontamentos WHERE anulado_por IS NULL AND data BETWEEN ? AND ?", (ini, fim))}
    alvos = set(("TRECHO", t) for t in no_periodo) | ativos_periodo | {k for k, e in ex.items() if e["medicao_id"] == medicao_id
                                                                         or (e["concluido"] and not e["ok_fiscal_em"])}
    ocorr = defaultdict(int)
    for r in conn.execute("SELECT alvo_tipo, alvo_id, COUNT(*) FROM ocorrencias WHERE resolvida_em IS NULL GROUP BY 1, 2"):
        ocorr[(r[0], r[1])] = r[2]
    linhas = []
    for tipo, aid in sorted(alvos):
        try:
            a = S.alvo(conn, tipo, aid)
        except RegraViolada:
            continue
        e = ex.get((tipo, aid)) or {}
        p = no_periodo.get(aid) if tipo == "TRECHO" else None
        l = {"alvo_tipo": tipo, "alvo_id": aid, "nome": a["nome"], "frente_id": a.get("frente_id"),
             "extensao_m": float(a["extensao_m"]) if tipo == "TRECHO" else None,
             "assentado_periodo_m": _m(p["ASSENTADO"]) if p else None, "verificado_periodo_m": _m(p["ASSENTADO_VER"]) if p else None,
             "reaterrado_periodo_m": _m(p["REATERRADO"]) if p else None, "concluido": bool(e.get("concluido")),
             "ok_interno_em": e.get("ok_fiscal_em"), "medicao_id": e.get("medicao_id"), "impedimentos": [], "alertas": []}
        if tipo == "TRECHO":
            l["assentado_total_m"] = round(R.comprimento(S._cobertura(conn, aid, "ASSENTADO")), 3)
        if e.get("medicao_id") == medicao_id:
            l["situacao"] = "PROPOSTO_NESTA"
        elif e.get("medicao_id"):
            n = _one(conn, "SELECT numero FROM medicoes WHERE id=?", e["medicao_id"])
            l["situacao"], l["medido_na"] = "MEDIDO_ANTES", n["numero"] if n else None
        elif e.get("ok_fiscal_em"):
            l["situacao"] = "OK_SEM_MEDICAO"           # entra quando houver medição de teste aberta para a data
        elif e.get("concluido"):
            l["situacao"] = "APTO_SEM_OK"
            falt = S.fotos_faltando(conn, tipo, aid)
            if falt:
                l["impedimentos"].append("fotos obrigatórias: " + ", ".join(falt))
            if tipo == "TRECHO" and S.legado_pendente(conn, a):
                l["impedimentos"].append("avanço anterior sem posição (conciliar)")
        else:
            l["situacao"] = "PARCIAL_NAO_ELEGIVEL"
            l["impedimentos"].append("execução incompleta: só trecho/nó completo com OK interno é proposto (D-30)")
        if ocorr[(tipo, aid)]:
            l["alertas"].append(f"{ocorr[(tipo, aid)]} ocorrência(s) aberta(s) (D-22)")
        if p and l["assentado_periodo_m"] and l["verificado_periodo_m"] < l["assentado_periodo_m"] - R.TOL_M:
            l["alertas"].append(f"{l['assentado_periodo_m'] - l['verificado_periodo_m']:g} m assentados no período sem verificação (D-18)")
        linhas.append(l)
    ordem = {"PROPOSTO_NESTA": 0, "OK_SEM_MEDICAO": 1, "APTO_SEM_OK": 2, "PARCIAL_NAO_ELEGIVEL": 3, "MEDIDO_ANTES": 4}
    linhas.sort(key=lambda l: (ordem[l["situacao"]], l["frente_id"] or "", l["nome"]))
    cont = {s: sum(1 for l in linhas if l["situacao"] == s) for s in ordem}
    cad = defaultdict(int)
    for r in conn.execute("SELECT etapa, COUNT(*) FROM cadastro GROUP BY etapa"):
        cad[r[0]] = r[1]
    cad_nesta = conn.execute("SELECT COUNT(*) FROM cadastro WHERE medicao_id=?", (medicao_id,)).fetchone()[0]
    rec_falta = conn.execute("SELECT COUNT(*) FROM execucao WHERE ok_fiscal_em IS NOT NULL AND recomposicao_ok=0").fetchone()[0]
    mats = []
    for r in conn.execute(
            f"""SELECT m.material_id, mt.descricao, mt.unidade, mt.propriedade,
                       SUM(CASE WHEN m.tipo='APLICADO' THEN m.quantidade ELSE 0 END) aplicado,
                       SUM(CASE WHEN m.tipo IN ('ENTRADA_NF','ROMANEIO_CAESB') THEN m.quantidade ELSE 0 END) recebido
                FROM movimentos m JOIN materiais mt ON mt.id=m.material_id
                WHERE m.data BETWEEN ? AND ? AND m.{S.VALIDO} AND (m.tipo='APLICADO' OR m.tipo='ROMANEIO_CAESB'
                      OR (m.tipo='ENTRADA_NF' AND COALESCE(m.status,'ACEITO')='ACEITO'))
                GROUP BY m.material_id ORDER BY mt.propriedade, m.material_id""", (ini, fim)):
        mats.append({**dict(r), "situacao": "BLOQUEADO", "decisao": "D-53 · D-54",
                     "motivo": "regime de faturamento de material não aprovado; recebido não é faturável"})
    tr = [l for l in linhas if l["alvo_tipo"] == "TRECHO"]
    return {
        "medicao": {k: med[k] for k in ("id", "numero", "tipo", "periodo_ini", "periodo_fim", "status")},
        "linhas": linhas, "contagem": cont,
        "resumo": {"assentado_periodo_m": round(sum(l["assentado_periodo_m"] or 0 for l in tr), 3),
                   "verificado_periodo_m": round(sum(l["verificado_periodo_m"] or 0 for l in tr), 3),
                   "proposto_nesta_m": round(sum(l["extensao_m"] for l in tr if l["situacao"] == "PROPOSTO_NESTA"), 3)},
        "cadastro": {"por_etapa": dict(cad), "medidos_nesta": cad_nesta},
        "recomposicao_nao_lancada": rec_falta,
        "materiais": mats,
        "regra": "Só trecho/nó completo com OK interno é proposto (D-30). Execução parcial e material ficam como conferência.",
    }


# ------------------------------------------------------------------ conferência interna (engenharia) antes do fechamento
def _evidencias(conn, tipo, aid):
    if tipo == "APROPRIACAO":                      # gaveta 5: as evidências são os anexos da apropriação direta
        n = conn.execute("SELECT COUNT(*) FROM apropriacao_documentos WHERE apropriacao_id=?", (aid,)).fetchone()[0]
        ap = _one(conn, "SELECT registrado_por, registrado_em FROM apropriacoes WHERE id=?", aid) or {}
        return {"ok_interno_em": None, "ok_interno_por": None, "fotos_validas": 0, "fotos_faltando": [] if n else ["evidência"],
                "ocorrencias_abertas": 0, "soldas_informadas": 0, "soldas_aprovadas": 0, "soldas_sem_verificacao": 0,
                "evidencias": n, "registrado_por": ap.get("registrado_por"), "registrado_em": ap.get("registrado_em")}
    ex = S.execucao(conn, tipo, aid) or {}
    fotos = conn.execute(f"SELECT COUNT(*) FROM fotos WHERE alvo_tipo=? AND alvo_id=? AND {S.FOTO_VALIDA}", (tipo, aid)).fetchone()[0]
    ev = {"ok_interno_em": ex.get("ok_fiscal_em"), "ok_interno_por": ex.get("ok_fiscal_por"), "fotos_validas": fotos,
          "fotos_faltando": S.fotos_faltando(conn, tipo, aid),
          "ocorrencias_abertas": conn.execute("SELECT COUNT(*) FROM ocorrencias WHERE alvo_tipo=? AND alvo_id=? AND resolvida_em IS NULL",
                                              (tipo, aid)).fetchone()[0]}
    s = S.resumo_soldas(conn, tipo, aid)
    ev.update(soldas_informadas=s["informadas"], soldas_aprovadas=s["aprovadas"], soldas_sem_verificacao=s["sem_verificacao"])
    if tipo == "TRECHO":
        n, v = conn.execute(f"SELECT COUNT(*), SUM(verificado_em IS NOT NULL) FROM intervalos_execucao WHERE trecho_id=? AND {S.EFETIVO}",
                            (aid,)).fetchone()
        ev["verificacao"] = S.estado_verificacao(n, v or 0, None)
        c = _one(conn, "SELECT etapa, revisao, protocolo_gdoc, memorando_eset FROM cadastro WHERE trecho_id=?", aid)
        ev["cadastro"] = c
    return ev


def retrato(conn, medicao_id):
    """Lançamentos, evidências por alvo, duplicidades e pendências — o que a engenharia confere."""
    lanc = _rows(conn.execute("""SELECT l.id, l.gaveta, l.servico, l.alvo_tipo, l.alvo_id,
                                        COALESCE(b.item, CASE WHEN l.item_novo_id IS NOT NULL THEN 'NOVO-' || l.item_novo_id END) item,
                                        l.unidade, l.quantidade, l.status, l.motivo
                                 FROM medicao_lancamentos l LEFT JOIN bm_itens b ON b.id=l.bm_item_id
                                 WHERE l.medicao_id=? ORDER BY l.gaveta, l.id""", (medicao_id,)))
    alvos = {}
    for l in lanc:
        if l["alvo_id"] and (l["alvo_tipo"], l["alvo_id"]) not in alvos:
            alvos[(l["alvo_tipo"], l["alvo_id"])] = {"alvo_tipo": l["alvo_tipo"], "alvo_id": l["alvo_id"],
                                                     "nome": S.nome_alvo(conn, l["alvo_tipo"], l["alvo_id"]),
                                                     **_evidencias(conn, l["alvo_tipo"], l["alvo_id"])}
    impeditivos, alertas = [], []
    dup = duplicidades(conn, medicao_id)
    for d in dup:
        impeditivos.append(f"Parcela em mais de uma medição: {d['servico']} de {d['alvo_nome']} (medições {d['medicoes']}).")
    propostos = {(l["alvo_tipo"], l["alvo_id"]) for l in lanc if l["status"] == "PROPOSTO"}
    for k, a in alvos.items():
        if k in propostos and a["fotos_faltando"]:
            impeditivos.append(f"{a['nome']}: evidência fotográfica obrigatória ausente ou inválida ({', '.join(a['fotos_faltando'])}).")
        if a["ocorrencias_abertas"]:
            alertas.append(f"{a['nome']}: {a['ocorrencias_abertas']} ocorrência(s) aberta(s) (D-22).")
        if a.get("verificacao") not in (None, "VERIFICADO"):
            alertas.append(f"{a['nome']}: intervalos {str(a['verificacao']).lower()} — verificação não exigida (D-18).")
        if a["soldas_sem_verificacao"]:
            alertas.append(f"{a['nome']}: {a['soldas_sem_verificacao']} solda(s) sem verificação.")
    excede = [i for i in acumulado_itens(conn, medicao_id) if i["excede_contrato"]]
    for i in excede:
        alertas.append(f"Item {i['item']}: acumulado {i['acumulado']:g} acima da quantidade contratual {i['contrato']:g}.")
    pend = [l for l in lanc if l["status"] == "PENDENTE"]
    return {"lancamentos": lanc, "alvos": list(alvos.values()), "duplicidades": dup, "impeditivos": impeditivos,
            "alertas": alertas, "pendentes": len(pend), "propostos": len(lanc) - len(pend),
            "regras_bloqueadas": [r for r in regras(conn) if r["situacao"] in ("BLOQUEADA", "HIPÓTESE", "VÍNCULO INCOMPLETO")]}


def conferir(conn, medicao_id, resultado, checklist, por, obs=None):
    """Conferência interna da engenharia sobre os lançamentos atuais. CONFORME é recusada com impeditivo (duplicidade,
    evidência obrigatória ausente). Não aprova nada pela Caesb; não altera lançamento."""
    med = _one(conn, "SELECT * FROM medicoes WHERE id=?", medicao_id)
    if not med:
        raise RegraViolada("Medição não encontrada.")
    if med["status"] != "ABERTA":
        raise RegraViolada("Medição fechada: a conferência é feita antes do fechamento.")
    itens = R.validar_conferencia(resultado, checklist, por, obs, roteiro=R.CHECKLIST_CONFERENCIA_MEDICAO,
                                  exige_obs="Descreva o que não confere (lançamento, evidência ou regra).")
    ret = retrato(conn, medicao_id)
    if not ret["lancamentos"]:
        raise RegraViolada("Nada lançado nesta medição para conferir.")
    if resultado == "CONFORME" and ret["impeditivos"]:
        raise RegraViolada("CONFORME recusado: " + " ".join(ret["impeditivos"]))
    with transacao(conn):
        return conn.execute(
            """INSERT INTO conferencias_medicao(medicao_id,resultado,checklist,assinatura,retrato,obs,por,em)
               VALUES (?,?,?,?,?,?,?,?)""",
            (medicao_id, resultado, json.dumps(itens), S.assinatura_medicao(conn, medicao_id),
             json.dumps(ret, ensure_ascii=False, default=str), (obs or "").strip() or None, por, _agora())).lastrowid


def conferencias(conn, medicao_id):
    return [{**r, "checklist": json.loads(r["checklist"])} for r in _rows(conn.execute(
        "SELECT id, medicao_id, resultado, checklist, assinatura, obs, por, em FROM conferencias_medicao WHERE medicao_id=? ORDER BY id",
        (medicao_id,)))]


def complementos(conn, medicao_id):
    """O que a aba 5 mostra junto do resumo: conferência vigente, duplicidades, parcelas por item e regras."""
    c = S.conferencia_vigente(conn, medicao_id)
    if c:
        c.pop("retrato")
    return {"conferencia": c, "conferencias": conferencias(conn, medicao_id), "duplicidades": duplicidades(conn, medicao_id),
            "acumulado": acumulado_itens(conn, medicao_id), "regras": regras(conn),
            "roteiro_conferencia": dict(R.CHECKLIST_CONFERENCIA_MEDICAO)}
