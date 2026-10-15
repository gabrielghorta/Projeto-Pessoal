"""Casos de uso sobre o banco: almoxarifado, campo, fiscalização, cadastro e medição."""
import base64
import json
import os
import sqlite3
from datetime import date, datetime

import regras as R
from regras import RegraViolada

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PADRAO = os.path.join(BASE, "dados", "morro_da_cruz.db")
DIR_FOTOS = os.path.join(BASE, "dados", "fotos")
TOL = 1e-6


# ------------------------------------------------------------------ conexão
def conectar(caminho=DB_PADRAO):
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    conn = sqlite3.connect(caminho, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    with open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn


class transacao:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN")
        return self.conn

    def __exit__(self, tipo, *_):
        self.conn.execute("ROLLBACK" if tipo else "COMMIT")
        return False


def _rows(cur):
    return [dict(r) for r in cur.fetchall()]


def _one(conn, sql, *args):
    r = conn.execute(sql, args).fetchone()
    return dict(r) if r else None


def parametro(conn, chave, padrao=None):
    r = _one(conn, "SELECT valor FROM parametros WHERE chave=?", chave)
    return r["valor"] if r else padrao


def contrato(conn):
    return parametro(conn, "contrato", "Caesb × Ankara nº 10239/2026")


def _agora():
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ alvos (trecho / nó / caixa)
def alvo(conn, alvo_tipo, alvo_id):
    """TRECHO = PONTO da 06.1; CONJUNTO = nomenclatura da 06.2 (nó/caixa × equipe)."""
    if alvo_tipo == "TRECHO":
        a = _one(conn, "SELECT * FROM trechos WHERE id=?", alvo_id)
    elif alvo_tipo == "CONJUNTO":
        a = _one(conn, """SELECT c.*, e.numero, e.tipo AS tipo_elemento, e.pb, e.lat, e.lon, e.nomenclaturas, e.status_posicao
                          FROM conjuntos c JOIN elementos e ON e.id=c.elemento_id WHERE c.id=?""", alvo_id)
    else:
        raise RegraViolada(f"Tipo de alvo inválido: {alvo_tipo}")
    if not a:
        raise RegraViolada(f"{alvo_tipo} '{alvo_id}' não encontrado.")
    return a


def execucao(conn, alvo_tipo, alvo_id):
    return _one(conn, "SELECT * FROM execucao WHERE alvo_tipo=? AND alvo_id=?", alvo_tipo, alvo_id)


def totais_conjunto(conn, conjunto_id):
    """Contador por unidade de um conjunto (ex.: Zona01_PB01_CH_DF-33 → 17 UN · 0,71 m).

    Linhas sem quantidade (06.2 ainda não importada) não entram como zero: são contadas à parte.
    """
    itens = conn.execute("SELECT unidade, quantidade FROM pecas WHERE conjunto_id=?", (conjunto_id,)).fetchall()
    com_q = [(i["unidade"], i["quantidade"]) for i in itens if i["quantidade"] is not None]
    pend = len(itens) - len(com_q)
    tot = R.somar_por_unidade(com_q)
    texto = R.formatar_por_unidade(tot) if tot else ""
    if pend:
        texto = (texto + " · " if texto else "") + f"{pend} linha(s) sem quantidade (importar 06.2)"
    return {"totais": tot, "texto": texto, "linhas": len(itens), "sem_quantidade": pend}


def previsto(conn, alvo_tipo, alvo_id, metros):
    a = alvo(conn, alvo_tipo, alvo_id)
    if alvo_tipo == "TRECHO":
        return R.quantidades_previstas_trecho(a, json.loads(a["quantidades"]), metros, mapa_servicos())
    pecas = pecas_conjunto(conn, alvo_id)
    pend = [p for p in pecas if p["quantidade"] is None]
    if pend:
        raise RegraViolada(f"{alvo_id}: {len(pend)} peça(s) sem quantidade — importar a 06.2 REV08 antes de apontar.")
    return R.quantidades_previstas_elemento(pecas)


# ------------------------------------------------------------------ almoxarifado
ENTRA_ALMOX = ("ROMANEIO_CAESB", "ENTRADA_NF", "ENTRADA_CONSUMO", "SOBRA")
SAI_ALMOX = ("EMPRESTIMO_OUTRA_OBRA", "CUSTODIA", "BAIXA_TEORICA")


def saldo_almox(conn, material_id):
    r = conn.execute(
        f"""SELECT
              COALESCE(SUM(CASE WHEN tipo IN {ENTRA_ALMOX} AND COALESCE(status,'ACEITO')='ACEITO' THEN quantidade END),0)
            - COALESCE(SUM(CASE WHEN tipo IN {SAI_ALMOX} THEN quantidade END),0) AS saldo,
              COALESCE(SUM(CASE WHEN tipo='ENTRADA_NF' AND status='QUARENTENA' THEN quantidade END),0) AS quarentena
            FROM movimentos WHERE material_id=?""", (material_id,)).fetchone()
    return r["saldo"], r["quarentena"]


def custodia_checkin(conn, checkin_id, material_id):
    r = conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN tipo='CUSTODIA' THEN quantidade
                                   WHEN tipo IN ('APLICADO','SOBRA','PERDA') THEN -quantidade END),0)
           FROM movimentos WHERE checkin_id=? AND material_id=?""", (checkin_id, material_id)).fetchone()
    return r[0]


def estoque(conn):
    out = []
    for m in _rows(conn.execute("SELECT * FROM materiais ORDER BY propriedade, id")):
        saldo, quar = saldo_almox(conn, m["id"])
        cust = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN tipo='CUSTODIA' THEN quantidade
                                       WHEN tipo IN ('APLICADO','SOBRA','PERDA') THEN -quantidade END),0)
               FROM movimentos WHERE material_id=? AND checkin_id IS NOT NULL""", (m["id"],)).fetchone()[0]
        out.append({**m, "saldo_almox": round(saldo, 3), "quarentena": round(quar, 3), "custodia": round(cust, 3)})
    return out


def compatibilizacao_caesb(conn):
    """Projeto 06.1 × Estoque Caesb × Emprestado × Retirado × Aplicado × Saldo Virtual."""
    out = []
    for m in _rows(conn.execute("SELECT * FROM materiais WHERE propriedade='CAESB' ORDER BY id")):
        s = {t: conn.execute("SELECT COALESCE(SUM(quantidade),0) FROM movimentos WHERE material_id=? AND tipo=?",
                             (m["id"], t)).fetchone()[0]
             for t in ("ROMANEIO_CAESB", "EMPRESTIMO_OUTRA_OBRA", "APLICADO", "PERDA")}
        projeto = m["qtd_projeto"] or 0
        out.append({
            "material_id": m["id"], "descricao": m["descricao"], "unidade": m["unidade"],
            "projeto": projeto,
            "estoque_caesb": m["estoque_caesb"],
            "emprestado": s["EMPRESTIMO_OUTRA_OBRA"],
            "retirado": s["ROMANEIO_CAESB"],
            "aplicado": s["APLICADO"],
            "perdido": s["PERDA"],
            # o que ainda falta retirar na Caesb para cumprir o projeto
            "saldo_virtual": round(projeto - (s["ROMANEIO_CAESB"] - s["EMPRESTIMO_OUTRA_OBRA"]), 3),
            # tubo fisicamente no canteiro/custódia
            "saldo_fisico": round(s["ROMANEIO_CAESB"] - s["EMPRESTIMO_OUTRA_OBRA"] - s["APLICADO"] - s["PERDA"], 3),
        })
    return out


def entrada_material(conn, data, material_id, quantidade, tipo, documento=None):
    if tipo not in ("ROMANEIO_CAESB", "ENTRADA_CONSUMO", "EMPRESTIMO_OUTRA_OBRA", "BAIXA_TEORICA"):
        raise RegraViolada(f"Tipo de movimento inválido aqui: {tipo}")
    m = _one(conn, "SELECT * FROM materiais WHERE id=?", material_id)
    if not m:
        raise RegraViolada(f"Material '{material_id}' não cadastrado.")
    if tipo in ("ROMANEIO_CAESB", "EMPRESTIMO_OUTRA_OBRA") and m["propriedade"] != "CAESB":
        raise RegraViolada("Romaneio/empréstimo só se aplica a tubos de fornecimento Caesb.")
    if tipo == "ENTRADA_CONSUMO" and m["propriedade"] != "CONSUMO":
        raise RegraViolada("Entrada por caminhão/nota de canteiro só para materiais de consumo diário.")
    if tipo in ("EMPRESTIMO_OUTRA_OBRA", "BAIXA_TEORICA") and saldo_almox(conn, material_id)[0] + TOL < quantidade:
        raise RegraViolada("Saldo insuficiente no almoxarifado.")
    conn.execute("INSERT INTO movimentos(data,material_id,tipo,quantidade,documento,status) VALUES (?,?,?,?,?,?)",
                 (data, material_id, tipo, quantidade, documento, "ACEITO"))


def registrar_nf(conn, numero, fornecedor, data_entrega, itens, faturamento_etapas=False, chave_nfe=None, arquivo=None):
    with transacao(conn):
        cur = conn.execute(
            """INSERT INTO notas_fiscais(numero,chave_nfe,fornecedor,data_entrega,arquivo,faturamento_etapas,status)
               VALUES (?,?,?,?,?,?, 'QUARENTENA')""",
            (numero, chave_nfe, fornecedor, data_entrega, arquivo, 1 if faturamento_etapas else 0))
        nf_id = cur.lastrowid
        for it in itens:
            m = _one(conn, "SELECT * FROM materiais WHERE id=?", it["material_id"])
            if not m or m["propriedade"] != "ANKARA":
                raise RegraViolada(f"Material '{it['material_id']}' não é de aquisição Ankara.")
            conn.execute("INSERT INTO nf_itens(nf_id,material_id,quantidade,valor_unitario) VALUES (?,?,?,?)",
                         (nf_id, it["material_id"], it["quantidade"], it.get("valor_unitario", 0)))
            conn.execute(
                """INSERT INTO movimentos(data,material_id,tipo,quantidade,documento,status,nf_id)
                   VALUES (?,?,'ENTRADA_NF',?,?, 'QUARENTENA', ?)""",
                (data_entrega, it["material_id"], it["quantidade"], f"NF {numero}", nf_id))
    return nf_id


def aceitar_nf(conn, nf_id, laudo_arquivo):
    """Laudo de inspeção aprovado: material sai da quarentena; se faturamento por
    etapas, lança 80 % do valor na medição do mês da entrega (gaveta 2)."""
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", nf_id)
    if not nf:
        raise RegraViolada("Nota fiscal não encontrada.")
    if nf["status"] == "ACEITO":
        raise RegraViolada("Nota fiscal já aceita.")
    if not laudo_arquivo:
        raise RegraViolada("Anexe o laudo de inspeção.")
    med = medicao_para(conn, nf["data_entrega"]) if nf["faturamento_etapas"] else None
    with transacao(conn):
        conn.execute("UPDATE notas_fiscais SET status='ACEITO', laudo_arquivo=? WHERE id=?", (laudo_arquivo, nf_id))
        conn.execute("UPDATE movimentos SET status='ACEITO' WHERE nf_id=? AND tipo='ENTRADA_NF'", (nf_id,))
        if med:
            for it in _rows(conn.execute(
                    "SELECT i.*, m.bm_item_id, m.unidade FROM nf_itens i JOIN materiais m ON m.id=i.material_id WHERE nf_id=?",
                    (nf_id,))):
                bm = _one(conn, "SELECT * FROM bm_itens WHERE id=?", it["bm_item_id"]) if it["bm_item_id"] else None
                _lancar(conn, med["id"], 2, "MATERIAL 80%", bm, it["unidade"], it["quantidade"], nf_id=nf_id,
                        material_id=it["material_id"], obs=f"NF {nf['numero']} — 80 % na entrega", pct=R.PCT_MATERIAL_ENTREGA)


# ------------------------------------------------------------------ check-in / check-out
def checkin(conn, data, equipe_id, alvo_tipo=None, alvo_id=None, funcionarios=(), maquinas=(),
            materiais=(), contingencia=None):
    if equipe_id not in [r[0] for r in conn.execute("SELECT id FROM equipes")]:
        raise RegraViolada(f"Equipe '{equipe_id}' não cadastrada.")
    if contingencia:
        if contingencia not in R.CONTINGENCIAS:
            raise RegraViolada("Contingência inválida.")
    elif not (alvo_tipo and alvo_id):
        raise RegraViolada("Informe o Trecho/Nó que a equipe vai atacar hoje (ou uma contingência).")
    else:
        alvo(conn, alvo_tipo, alvo_id)
    if _one(conn, "SELECT id FROM checkins WHERE data=? AND equipe_id=? AND encerrado=0", data, equipe_id):
        raise RegraViolada("Equipe já tem check-in aberto hoje — faça o check-out antes.")
    with transacao(conn):
        cid = conn.execute(
            "INSERT INTO checkins(data,equipe_id,alvo_tipo,alvo_id,contingencia) VALUES (?,?,?,?,?)",
            (data, equipe_id, None if contingencia else alvo_tipo, None if contingencia else alvo_id, contingencia)).lastrowid
        for f in funcionarios:
            conn.execute("INSERT INTO checkin_presencas VALUES (?, 'FUNCIONARIO', ?)", (cid, f))
        for m in maquinas:
            conn.execute("INSERT INTO checkin_presencas VALUES (?, 'MAQUINA', ?)", (cid, m))
        for it in materiais:
            q = float(it["quantidade"])
            if q <= 0:
                continue
            mat = _one(conn, "SELECT * FROM materiais WHERE id=?", it["material_id"])
            if not mat:
                raise RegraViolada(f"Material '{it['material_id']}' não cadastrado.")
            if mat["propriedade"] == "CONSUMO":
                raise RegraViolada(f"{mat['descricao']}: material de consumo baixa por volume geométrico, não por requisição.")
            if saldo_almox(conn, mat["id"])[0] + TOL < q:
                raise RegraViolada(f"Saldo insuficiente de {mat['descricao']} no almoxarifado.")
            conn.execute(
                """INSERT INTO movimentos(data,material_id,tipo,quantidade,equipe_id,alvo_tipo,alvo_id,checkin_id)
                   VALUES (?,?,'CUSTODIA',?,?,?,?,?)""", (data, mat["id"], q, equipe_id, alvo_tipo, alvo_id, cid))
    return cid


def checkout(conn, checkin_id, itens):
    """itens: [{material_id, aplicado, sobra, perda, motivo}] — fecha a custódia do dia."""
    ck = _one(conn, "SELECT * FROM checkins WHERE id=?", checkin_id)
    if not ck or ck["encerrado"]:
        raise RegraViolada("Check-in inexistente ou já encerrado.")
    with transacao(conn):
        for it in itens:
            mid = it["material_id"]
            ap, so, pe = (float(it.get(k) or 0) for k in ("aplicado", "sobra", "perda"))
            if pe > 0 and not (it.get("motivo") or "").strip():
                raise RegraViolada("Informe o motivo da quebra/perda.")
            cust = custodia_checkin(conn, checkin_id, mid)
            if abs((ap + so + pe) - cust) > 1e-3:
                raise RegraViolada(
                    f"{mid}: aplicado + sobra + perda ({ap + so + pe:g}) deve fechar a custódia do dia ({cust:g}).")
            for tipo, q in (("APLICADO", ap), ("SOBRA", so), ("PERDA", pe)):
                if q > 0:
                    conn.execute(
                        """INSERT INTO movimentos(data,material_id,tipo,quantidade,equipe_id,alvo_tipo,alvo_id,motivo,checkin_id)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (ck["data"], mid, tipo, q, ck["equipe_id"], ck["alvo_tipo"], ck["alvo_id"],
                         it.get("motivo") if tipo == "PERDA" else None, checkin_id))
        pend = [r["material_id"] for r in conn.execute(
            "SELECT DISTINCT material_id FROM movimentos WHERE checkin_id=?", (checkin_id,))
            if abs(custodia_checkin(conn, checkin_id, r["material_id"])) > 1e-3]
        if pend:
            raise RegraViolada("Custódia não fechada para: " + ", ".join(pend))
        conn.execute("UPDATE checkins SET encerrado=1 WHERE id=?", (checkin_id,))


def checkins_abertos(conn, data=None):
    sql = "SELECT * FROM checkins WHERE encerrado=0" + (" AND data=?" if data else "") + " ORDER BY equipe_id"
    out = _rows(conn.execute(sql, (data,) if data else ()))
    for c in out:
        c["materiais"] = _rows(conn.execute(
            "SELECT material_id, SUM(quantidade) AS quantidade FROM movimentos WHERE checkin_id=? AND tipo='CUSTODIA' "
            "GROUP BY material_id", (c["id"],)))
    return out


def histograma(conn, data_ini, data_fim):
    return _rows(conn.execute(
        """SELECT c.data, c.equipe_id,
                  SUM(p.recurso_tipo='FUNCIONARIO') AS funcionarios,
                  SUM(p.recurso_tipo='MAQUINA') AS maquinas
           FROM checkins c LEFT JOIN checkin_presencas p ON p.checkin_id=c.id
           WHERE c.data BETWEEN ? AND ? GROUP BY c.data, c.equipe_id ORDER BY c.data, c.equipe_id""",
        (data_ini, data_fim)))


# ------------------------------------------------------------------ campo
def registrar_clima(conn, data, equipe_id, turno, condicao):
    if condicao not in R.CONDICOES_CLIMA:
        raise RegraViolada("Condição de clima inválida.")
    conn.execute("INSERT OR REPLACE INTO clima VALUES (?,?,?,?)", (data, equipe_id, turno, condicao))


def apontar(conn, data, equipe_id, alvo_tipo, alvo_id, metros_executados=0, metros_reaterrados=0,
            concluido_100=False, estaca_ini=None, estaca_fim=None, quantidades=None):
    """Lança avanço de campo. `quantidades=None` equivale a [✅ OK, Confirmar Previsto]."""
    turnos = {r["turno"] for r in conn.execute("SELECT turno FROM clima WHERE data=? AND equipe_id=?", (data, equipe_id))}
    if turnos != {"MANHA", "TARDE"}:
        raise RegraViolada("Clima do dia obrigatório nos dois turnos (manhã e tarde) antes do apontamento.")
    a = alvo(conn, alvo_tipo, alvo_id)
    ex = execucao(conn, alvo_tipo, alvo_id) or {"metros_executados": 0, "metros_reaterrados": 0, "concluido": 0}
    if ex.get("ok_fiscal_em"):
        raise RegraViolada("Alvo já validado pela fiscalização — não aceita novos apontamentos.")
    if alvo_tipo == "TRECHO":
        ext = a["extensao_m"]
        if concluido_100:
            metros_executados = ext - ex["metros_executados"]
            metros_reaterrados = ext - ex["metros_reaterrados"]
        novo_exec = ex["metros_executados"] + metros_executados
        novo_reat = ex["metros_reaterrados"] + metros_reaterrados
        if novo_exec > ext + 1e-3:
            raise RegraViolada(f"Metros executados ({novo_exec:g}) excedem a extensão do trecho ({ext:g} m).")
        if novo_reat > novo_exec + 1e-3:
            raise RegraViolada("Não é possível reaterrar mais do que foi executado.")
        concluido = 1 if novo_reat >= ext - 1e-3 else 0
        prev = previsto(conn, alvo_tipo, alvo_id, metros_executados) if metros_executados > 0 else []
    else:
        novo_exec = novo_reat = 0
        concluido = 1 if concluido_100 else 0
        prev = previsto(conn, alvo_tipo, alvo_id, 0) if concluido else []
    with transacao(conn):
        aid = conn.execute(
            """INSERT INTO apontamentos(data,equipe_id,alvo_tipo,alvo_id,metros_executados,metros_reaterrados,estaca_ini,estaca_fim)
               VALUES (?,?,?,?,?,?,?,?)""",
            (data, equipe_id, alvo_tipo, alvo_id, metros_executados, metros_reaterrados, estaca_ini, estaca_fim)).lastrowid
        confirmadas = {(q["servico"], q["unidade"]): q["confirmado"] for q in (quantidades or [])}
        for q in prev:
            conf = confirmadas.pop((q["servico"], q["unidade"]), q["previsto"])
            conn.execute("INSERT INTO apontamento_quantidades VALUES (?,?,?,?,?)",
                         (aid, q["servico"], q["unidade"], q["previsto"], float(conf)))
        for (serv, un), conf in confirmadas.items():   # quantidade real sem previsto
            conn.execute("INSERT INTO apontamento_quantidades VALUES (?,?,?,NULL,?)", (aid, serv, un, float(conf)))
        conn.execute(
            """INSERT INTO execucao(alvo_tipo,alvo_id,metros_executados,metros_reaterrados,concluido)
               VALUES (?,?,?,?,?)
               ON CONFLICT(alvo_tipo,alvo_id) DO UPDATE SET metros_executados=excluded.metros_executados,
                 metros_reaterrados=excluded.metros_reaterrados, concluido=MAX(concluido, excluded.concluido)""",
            (alvo_tipo, alvo_id, novo_exec, novo_reat, concluido))
    return aid


def fotos_faltando(conn, alvo_tipo, alvo_id):
    alvo(conn, alvo_tipo, alvo_id)
    cats = [r[0] for r in conn.execute("SELECT categoria FROM fotos WHERE alvo_tipo=? AND alvo_id=?", (alvo_tipo, alvo_id))]
    return R.fotos_pendentes(alvo_tipo, cats, _sinalizacao_herdada(conn, alvo_tipo, alvo_id))


def registrar_foto(conn, alvo_tipo, alvo_id, categoria, conteudo_b64, extensao="jpg", data_hora=None, lat=None, lon=None,
                   dir_fotos=DIR_FOTOS):
    a = alvo(conn, alvo_tipo, alvo_id)
    if categoria not in R.FOTOS_TRECHO:
        raise RegraViolada("Categoria de foto inválida.")
    data_hora = data_hora or _agora()
    carimbo = R.carimbo(contrato(conn), alvo_id, data_hora, lat, lon)
    os.makedirs(dir_fotos, exist_ok=True)
    nome = f"{alvo_id}_{categoria}_{data_hora.replace(':', '').replace('-', '')}.{extensao}".replace("/", "_")
    with open(os.path.join(dir_fotos, nome), "wb") as f:
        f.write(base64.b64decode(conteudo_b64))
    conn.execute(
        "INSERT INTO fotos(alvo_tipo,alvo_id,area,categoria,arquivo,data_hora,lat,lon,carimbo) VALUES (?,?,?,?,?,?,?,?,?)",
        (alvo_tipo, alvo_id, a.get("area"), categoria, nome, data_hora, lat, lon, carimbo))
    return {"arquivo": nome, "carimbo": carimbo}


# ------------------------------------------------------------------ OK Fiscalização
def _lancar(conn, medicao_id, gaveta, servico, bm, unidade, quantidade, alvo_tipo=None, alvo_id=None,
            nf_id=None, material_id=None, obs=None, pct=1.0):
    valor = _valor(conn, bm, quantidade, pct) if bm else 0.0
    if bm is None:
        obs = ((obs + " · ") if obs else "") + "SEM ITEM BM VINCULADO"
    conn.execute(
        """INSERT INTO medicao_lancamentos(medicao_id,gaveta,servico,bm_item_id,alvo_tipo,alvo_id,nf_id,material_id,unidade,quantidade,valor,observacao)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (medicao_id, gaveta, servico, bm["id"] if bm else None, alvo_tipo, alvo_id, nf_id, material_id, unidade,
         round(quantidade, 4), valor, obs))


def _material_20(conn, medicao_id, alvo_tipo, alvo_id):
    """Material Ankara aplicado no alvo: 20 % se os 80 % já foram pagos na entrega, senão 100 %."""
    aplic = _rows(conn.execute(
        """SELECT mv.material_id, SUM(mv.quantidade) q, m.unidade, m.bm_item_id
           FROM movimentos mv JOIN materiais m ON m.id=mv.material_id
           WHERE mv.tipo='APLICADO' AND mv.alvo_tipo=? AND mv.alvo_id=? AND m.propriedade='ANKARA'
           GROUP BY mv.material_id""", (alvo_tipo, alvo_id)))
    for a in aplic:
        bm = _one(conn, "SELECT * FROM bm_itens WHERE id=?", a["bm_item_id"]) if a["bm_item_id"] else None
        coberto = conn.execute(
            """SELECT COALESCE(SUM(i.quantidade),0) FROM nf_itens i JOIN notas_fiscais n ON n.id=i.nf_id
               WHERE i.material_id=? AND n.faturamento_etapas=1 AND n.status='ACEITO'""", (a["material_id"],)).fetchone()[0]
        ja_20 = conn.execute(
            "SELECT COALESCE(SUM(quantidade),0) FROM medicao_lancamentos WHERE servico='MATERIAL 20%' AND material_id=?",
            (a["material_id"],)).fetchone()[0]
        q20 = max(0.0, min(a["q"], coberto - ja_20))
        q100 = a["q"] - q20
        if q20 > 0:
            _lancar(conn, medicao_id, 1, "MATERIAL 20%", bm, a["unidade"], q20, alvo_tipo, alvo_id,
                    material_id=a["material_id"], obs="20 % finais na aplicação", pct=R.PCT_MATERIAL_APLICACAO)
        if q100 > 0:
            _lancar(conn, medicao_id, 1, "MATERIAL 100%", bm, a["unidade"], q100, alvo_tipo, alvo_id,
                    material_id=a["material_id"], obs="sem faturamento por etapas")


def ok_fiscalizacao(conn, alvo_tipo, alvo_id, usuario, data=None):
    """[✓] OK Fiscalização — Pronto p/ Medir. Dispara: (1) lançamentos na medição
    do mês; (2) envio do trecho para a Esteira de Cadastro (1. Pronto p/ Cadastro)."""
    data = data or date.today().isoformat()
    a = alvo(conn, alvo_tipo, alvo_id)
    ex = execucao(conn, alvo_tipo, alvo_id)
    R.validar_ok_fiscal(ex, fotos_faltando(conn, alvo_tipo, alvo_id))
    med = medicao_para(conn, data)
    with transacao(conn):
        conn.execute("UPDATE execucao SET ok_fiscal_em=?, ok_fiscal_por=?, medicao_id=? WHERE alvo_tipo=? AND alvo_id=?",
                     (data, usuario, med["id"], alvo_tipo, alvo_id))
        # evento 1 — serviços confirmados em campo (recomposição tem checkbox próprio)
        servs = _rows(conn.execute(
            """SELECT q.servico, q.unidade, SUM(q.confirmado) qtd FROM apontamento_quantidades q
               JOIN apontamentos ap ON ap.id=q.apontamento_id
               WHERE ap.alvo_tipo=? AND ap.alvo_id=? GROUP BY q.servico, q.unidade""", (alvo_tipo, alvo_id)))
        pecas_bm = {}
        if alvo_tipo == "CONJUNTO":
            for p in pecas_conjunto(conn, alvo_id):
                nome = R.quantidades_previstas_elemento([p])[0]["servico"]
                pecas_bm.setdefault(nome, p["codigo_bm"])
        for s in servs:
            if alvo_tipo == "TRECHO":
                itens = _itens_servico(conn, s["servico"], a)
                if not itens:
                    _lancar(conn, med["id"], 1, s["servico"], None, s["unidade"], s["qtd"], alvo_tipo, alvo_id)
                for bm, frac in itens:
                    _lancar(conn, med["id"], 1, s["servico"], bm, s["unidade"], s["qtd"] * frac, alvo_tipo, alvo_id)
            else:
                bm = _servico_conjunto_bm(conn, pecas_bm.get(s["servico"]))
                if bm and str(bm["classificacao"]).upper().startswith("MATERIAL"):
                    continue   # peça é material: paga pelo fluxo do almoxarifado (80 % + 20 %), nunca em dobro
                _lancar(conn, med["id"], 1, s["servico"], bm, s["unidade"], s["qtd"], alvo_tipo, alvo_id)
        _material_20(conn, med["id"], alvo_tipo, alvo_id)
        # evento 2 — esteira de cadastro (somente trechos de rede)
        if alvo_tipo == "TRECHO":
            conn.execute("INSERT INTO cadastro(trecho_id,etapa,atualizado_em) VALUES (?, '1_PRONTO', ?)", (alvo_id, _agora()))
            conn.execute("INSERT INTO cadastro_historico(trecho_id,de_etapa,para_etapa,em) VALUES (?,NULL,'1_PRONTO',?)",
                         (alvo_id, _agora()))
    return med["id"]


def recomposicao_ok(conn, alvo_tipo, alvo_id, tipo, quantidade, data=None):
    """Checkbox separado: calçada/asfalto entra só quando a equipe de pavimento executar (gaveta 4)."""
    data = data or date.today().isoformat()
    alvo(conn, alvo_tipo, alvo_id)
    ex = execucao(conn, alvo_tipo, alvo_id)
    if not ex or not ex.get("ok_fiscal_em"):
        raise RegraViolada("Recomposição só pode ser medida após o OK Fiscalização do trecho/nó.")
    if ex["recomposicao_ok"]:
        raise RegraViolada("Recomposição já medida.")
    cfg = mapa_servicos()["recomposicao"]
    if tipo not in cfg["itens_por_tipo"]:
        raise RegraViolada("Tipo de recomposição inválido (CALÇADA ou ASFALTO).")
    if quantidade <= 0:
        raise RegraViolada("Informe a quantidade recomposta.")
    bm = _bm_item(conn, cfg["itens_por_tipo"][tipo]) if cfg["status"] == "CONFIRMADO" else None
    med = medicao_para(conn, data)
    with transacao(conn):
        conn.execute("UPDATE execucao SET recomposicao_ok=1, recomposicao_medicao_id=? WHERE alvo_tipo=? AND alvo_id=?",
                     (med["id"], alvo_tipo, alvo_id))
        _lancar(conn, med["id"], 4, f"RECOMPOSIÇÃO {tipo}", bm, bm["unidade"] if bm else "M2", quantidade,
                alvo_tipo, alvo_id)


# ------------------------------------------------------------------ esteira de cadastro
def avancar_cadastro(conn, trecho_id, destino, dados=None, data=None):
    dados = dados or {}
    c = _one(conn, "SELECT * FROM cadastro WHERE trecho_id=?", trecho_id)
    if not c:
        raise RegraViolada("Trecho não está na esteira (exige OK Fiscalização).")
    R.validar_transicao(c["etapa"], destino, dados)
    campos = {"etapa": destino, "atualizado_em": _agora()}
    if destino == "2_ENVIADO":
        if c["etapa"] == "5A_NEGADO":   # [Reenviar p/ Empresa Ajustar]
            campos.update(revisao=c["revisao"] + 1, protocolo_gdoc=None, arquivos=None)
        else:
            campos.update(empresa=dados["empresa"], data_envio=dados["data_envio"])
    elif destino == "3_RECEBIDO":
        arq = dados["arquivos"]
        campos["arquivos"] = arq if isinstance(arq, str) else json.dumps(arq, ensure_ascii=False)
    elif destino == "4_GDOC_ANALISE":
        campos.update(protocolo_gdoc=dados["protocolo_gdoc"], motivo_negativa=None)
    elif destino == "5A_NEGADO":
        campos["motivo_negativa"] = dados["motivo_negativa"]
    elif destino == "6_APROVADO":
        campos["memorando_eset"] = dados["memorando_eset"]
    with transacao(conn):
        if destino == "6_APROVADO":
            t = alvo(conn, "TRECHO", trecho_id)
            med = medicao_para(conn, data or date.today().isoformat())
            _lancar(conn, med["id"], 3, "CADASTRO", _bm_item(conn, mapa_servicos()["cadastro"]["item"]), "M", t["extensao_m"],
                    "TRECHO", trecho_id, obs=f"GDOC {c['protocolo_gdoc']} · ESET {dados['memorando_eset']}")
            campos["medicao_id"] = med["id"]
        sets = ", ".join(f"{k}=?" for k in campos)
        conn.execute(f"UPDATE cadastro SET {sets} WHERE trecho_id=?", (*campos.values(), trecho_id))
        conn.execute("INSERT INTO cadastro_historico(trecho_id,de_etapa,para_etapa,dados,em) VALUES (?,?,?,?,?)",
                     (trecho_id, c["etapa"], destino, json.dumps(dados, ensure_ascii=False), _agora()))


def esteira(conn):
    out = _rows(conn.execute(
        "SELECT c.*, t.extensao_m, t.frente_id FROM cadastro c JOIN trechos t ON t.id=c.trecho_id ORDER BY c.etapa, c.trecho_id"))
    for c in out:
        c["rotulo"] = R.rotulo_etapa(c["etapa"], c["revisao"])
        c["proximas"] = list(R.TRANSICOES.get(c["etapa"], {}).keys())
    return out


# ------------------------------------------------------------------ medição
def criar_medicao(conn, numero, periodo_ini, periodo_fim):
    if periodo_fim < periodo_ini:
        raise RegraViolada("Período inválido.")
    sob = _one(conn, "SELECT numero FROM medicoes WHERE NOT (periodo_fim < ? OR periodo_ini > ?)", periodo_ini, periodo_fim)
    if sob:
        raise RegraViolada(f"Período sobrepõe a {sob['numero']}ª medição.")
    return conn.execute("INSERT INTO medicoes(numero,periodo_ini,periodo_fim) VALUES (?,?,?)",
                        (numero, periodo_ini, periodo_fim)).lastrowid


def medicao_para(conn, data):
    m = _one(conn, "SELECT * FROM medicoes WHERE ? BETWEEN periodo_ini AND periodo_fim", data)
    if not m:
        raise RegraViolada(f"Nenhuma medição cadastrada cobrindo {data}. Abra a medição do mês na aba 5.")
    if m["status"] != "ABERTA":
        raise RegraViolada(f"A {m['numero']}ª medição ({data}) já está fechada.")
    return m


def fechar_medicao(conn, medicao_id):
    conn.execute("UPDATE medicoes SET status='FECHADA' WHERE id=?", (medicao_id,))


def indices_reajuste(conn):
    return _rows(conn.execute("SELECT * FROM reajuste_indices ORDER BY vigencia_ini"))


GAVETAS = {
    1: "Serviços de Trechos Reaterrados + 20 % Mat.",
    2: "Notas Fiscais — 80 % na Entrega",
    3: "Cadastros Aprovados GDOC",
    4: "Calçadas / Asfalto",
}


def resumo_medicao(conn, medicao_id):
    med = _one(conn, "SELECT * FROM medicoes WHERE id=?", medicao_id)
    if not med:
        raise RegraViolada("Medição não encontrada.")
    lanc = _rows(conn.execute(
        """SELECT l.*, b.item, b.subgrupo, b.descricao AS bm_descricao, b.classificacao
           FROM medicao_lancamentos l LEFT JOIN bm_itens b ON b.id=l.bm_item_id
           WHERE l.medicao_id=? ORDER BY l.gaveta, l.id""", (medicao_id,)))
    gavetas = {g: {"nome": n, "valor": 0.0, "lancamentos": []} for g, n in GAVETAS.items()}
    for l in lanc:
        gavetas[l["gaveta"]]["lancamentos"].append(l)
        gavetas[l["gaveta"]]["valor"] = round(gavetas[l["gaveta"]]["valor"] + l["valor"], 2)
    # teto por subgrupo do BM Vertical = valor contratual (P0) dos itens do subgrupo
    tetos = []
    for sg in _rows(conn.execute(
            """SELECT b.subgrupo, MAX(b.subgrupo_nome) nome,
                      SUM(CASE WHEN m.numero < ? THEN l.valor ELSE 0 END) anterior,
                      SUM(CASE WHEN m.numero = ? THEN l.valor ELSE 0 END) atual
               FROM medicao_lancamentos l JOIN bm_itens b ON b.id=l.bm_item_id JOIN medicoes m ON m.id=l.medicao_id
               WHERE b.planilha='VERTICAL' AND m.numero <= ? GROUP BY b.subgrupo""", (med["numero"],) * 3)):
        teto = sum(_valor(conn, b, b["quantidade"] or 0) for b in
                   _rows(conn.execute("SELECT * FROM bm_itens WHERE planilha='VERTICAL' AND subgrupo=?", (sg["subgrupo"],))))
        aceito, exced = R.aplicar_teto(sg["atual"], sg["anterior"], teto)
        tetos.append({**sg, "teto": round(teto, 2), "aceito": aceito, "excedente": exced})
    excedente = round(sum(t["excedente"] for t in tetos), 2)
    bruto = round(sum(g["valor"] for g in gavetas.values()), 2)
    pi = round(bruto - excedente, 2)
    try:
        indice, aviso = R.indice_reajuste(med["periodo_ini"], med["periodo_fim"], indices_reajuste(conn)), None
    except RegraViolada as e:
        indice, aviso = None, str(e)
    return {
        "medicao": med, "gavetas": gavetas, "tetos": tetos,
        "valor_pi": bruto, "excedente_teto": excedente, "valor_pi_limitado": pi,
        "indice_reajuste": indice, "aviso_reajuste": aviso,
        "valor_reajuste": round(pi * indice, 2) if indice is not None else None,
        "valor_total": round(pi * (1 + indice), 2) if indice is not None else None,
        "sem_vinculo_bm": sum(1 for l in lanc if l["bm_item_id"] is None),
    }


# ------------------------------------------------------------------ mapa
def detalhe(conn, alvo_tipo, alvo_id):
    a = alvo(conn, alvo_tipo, alvo_id)
    d = {"tipo": alvo_tipo, **a, "execucao": execucao(conn, alvo_tipo, alvo_id),
         "fotos": _rows(conn.execute("SELECT * FROM fotos WHERE alvo_tipo=? AND alvo_id=? ORDER BY id", (alvo_tipo, alvo_id))),
         "fotos_faltando": fotos_faltando(conn, alvo_tipo, alvo_id)}
    if alvo_tipo == "TRECHO":
        d["quantidades"] = json.loads(a["quantidades"])
        d["cadastro"] = _one(conn, "SELECT * FROM cadastro WHERE trecho_id=?", alvo_id)
        d["perfil_bloqueado"] = R.perfil_pendente(a)
        d["conjuntos"] = [r[0] for r in conn.execute(
            "SELECT DISTINCT conjunto_id FROM pecas WHERE trechos LIKE ? ORDER BY conjunto_id", (f"%{alvo_id}%",))]
    else:
        d.update(totais_conjunto(conn, alvo_id))
        d["pecas"] = pecas_conjunto(conn, alvo_id)
        d["trechos_ligados"] = trechos_do_conjunto(conn, alvo_id)
        d["avisos"] = [{"problema": p["aviso_problema"], "sugestao": p["aviso_sugestao"]} for p in d["pecas"]
                       if p["aviso_problema"] or p["aviso_sugestao"]]
    return d


def estado_mapa(conn, medicao_atual_id=None, data=None):
    """Status do Mapa Iluminado por trecho e por nomenclatura de conjunto, pins e bandeja sem posição."""
    ex = {(r["alvo_tipo"], r["alvo_id"]): dict(r) for r in conn.execute("SELECT * FROM execucao")}
    fotos = {}
    for r in conn.execute("SELECT alvo_tipo, alvo_id, categoria FROM fotos"):
        fotos.setdefault((r[0], r[1]), []).append(r[2])
    status = {}
    for (tipo, aid), e in ex.items():
        her = _sinalizacao_herdada(conn, tipo, aid) if tipo == "CONJUNTO" else False
        falt = R.fotos_pendentes(tipo, fotos.get((tipo, aid), []), her)
        status[aid] = R.status_mapa(e, falt, medicao_atual_id)
    pins = []
    for c in checkins_abertos(conn, data or date.today().isoformat()):
        if c["alvo_id"]:
            pins.append({"equipe": c["equipe_id"], "alvo_tipo": c["alvo_tipo"], "alvo_id": c["alvo_id"], "checkin": c["id"]})
    return {
        "status": status,
        "pins": pins,
        "sem_posicao": _rows(conn.execute(
            "SELECT id, numero, nomenclaturas, status_posicao FROM elementos WHERE lat IS NULL ORDER BY numero")),
    }


def mapa_servicos():
    with open(os.path.join(BASE, "config", "servicos_rede.json"), encoding="utf-8") as f:
        return json.load(f)


def buscar(conn, q, limite=30):
    """Busca por trecho (TR001 / nome completo), nó/caixa (NÓ1.8, NO1.8, DF-33) ou nomenclatura."""
    q = (q or "").strip()
    if not q:
        return []
    termo = "%" + q.upper().replace("NO", "NÓ") + "%" if q.upper().startswith("NO") else "%" + q.upper() + "%"
    out = [{"tipo": "TRECHO", "id": r["id"], "rotulo": r["id"], "extra": f"DE{int(r['de_mm'])} · {r['extensao_m']:.2f} m"}
           for r in conn.execute("SELECT id, de_mm, extensao_m FROM trechos WHERE UPPER(id) LIKE ? ORDER BY id LIMIT ?",
                                 (termo, limite))]
    out += [{"tipo": "CONJUNTO", "id": r["id"], "rotulo": r["id"], "extra": r["frente_id"]}
            for r in conn.execute("SELECT id, frente_id FROM conjuntos WHERE UPPER(id) LIKE ? ORDER BY id LIMIT ?",
                                  (termo, limite))]
    return out[:limite]


def pecas_conjunto(conn, conjunto_id):
    return _rows(conn.execute("SELECT * FROM pecas WHERE conjunto_id=? ORDER BY linha_origem", (conjunto_id,)))


def trechos_do_conjunto(conn, conjunto_id):
    """Trechos ligados: pontas da 06.1 na nomenclatura do elemento + coluna TRECHO da 06.2."""
    c = alvo(conn, "CONJUNTO", conjunto_id)
    noms = [n.strip() for n in (c["nomenclaturas"] or "").split("|") if n.strip()]
    ids = set()
    if noms:
        ph = ",".join("?" * len(noms))
        ids |= {r[0] for r in conn.execute(f"SELECT id FROM trechos WHERE no_ini IN ({ph}) OR no_fim IN ({ph})", noms + noms)}
    for r in conn.execute("SELECT DISTINCT trechos FROM pecas WHERE conjunto_id=? AND trechos IS NOT NULL", (conjunto_id,)):
        ids |= {t.strip() for t in r[0].split("/") if t.strip()}
    return sorted(ids)


def _sinalizacao_herdada(conn, alvo_tipo, alvo_id):
    if alvo_tipo == "TRECHO":
        return False
    trs = trechos_do_conjunto(conn, alvo_id)
    if not trs:
        return False
    ph = ",".join("?" * len(trs))
    return conn.execute(f"SELECT 1 FROM fotos WHERE alvo_tipo='TRECHO' AND categoria='SINALIZACAO' AND alvo_id IN ({ph}) LIMIT 1",
                        trs).fetchone() is not None


def _bm_item(conn, chave):
    return _one(conn, "SELECT * FROM bm_itens WHERE planilha='VERTICAL' AND item=?", chave)


def _itens_servico(conn, servico, trecho):
    """[(bm_item, fração)] de um serviço da 06.1, segundo config/servicos_rede.json."""
    cfg = next((s for s in mapa_servicos()["gaveta1"] if s["servico"] == servico), None)
    if not cfg or cfg["status"] != "CONFIRMADO" or not cfg["itens"]:
        return []
    itens = [_bm_item(conn, k.format(codigo_bm=trecho.get("codigo_bm"))) for k in cfg["itens"]]
    itens = [i for i in itens if i]
    if not itens:
        return []
    return [(i, f) for i, f in R.ratear(1.0, [(i, i["quantidade"] or 0) for i in itens])]


def _valor(conn, bm, quantidade, pct=1.0):
    return round(R.valor_bm(quantidade, bm["preco_unitario"], bm["classificacao"], float(parametro(conn, "bdi_material", 0)),
                            float(parametro(conn, "bdi_servico", 0)), float(parametro(conn, "coef_k", 0))) * pct, 2)


def _servico_conjunto_bm(conn, codigo_bm):
    """Item do BM Vertical de uma peça da 06.2: só se o código for inequívoco."""
    if not codigo_bm:
        return None
    cands = _rows(conn.execute("SELECT * FROM bm_itens WHERE planilha='VERTICAL' AND item_bm=?", (codigo_bm,)))
    return cands[0] if len(cands) == 1 else None
