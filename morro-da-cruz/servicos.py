"""Casos de uso sobre o banco (esquema v3): almoxarifado, campo, fiscalização, cadastro e medição.

Travas desta versão (etapas 0 e 1 — regras financeiras ainda não aprovadas):
  * nenhum regime de faturamento de material é aplicado (sem 80/20, sem 100 % na aplicação);
  * trecho MND não recebe item de assentamento VCA nem substituição automática: fica pendente;
  * lançamento sem item/regra com fonte fica PENDENTE e fora do valor (nunca R$ 0 contratual);
  * medições são do tipo TESTE; OFICIAL só com o parâmetro medicao_oficial_liberada = SIM;
  * objeto retirado da revisão vigente (vigente = 0) pode ser consultado, mas não recebe operação nova;
  * medição fechada fica congelada: revisão posterior do BM não altera o valor dela.
"""
import base64
import json
import os
import re
import sqlite3
from datetime import date, datetime

import regras as R
from regras import RegraViolada

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PADRAO = os.path.join(BASE, "dados", "morro_da_cruz.db")
DIR_FOTOS = os.path.join(BASE, "dados", "fotos")
VERSAO_ESQUEMA = 5
TOL = 1e-6
ALIAS_ALVO = {"CONJUNTO": "ATIVIDADE", "ELEMENTO": "ATIVIDADE"}


class EsquemaAntigo(RuntimeError):
    """Banco em esquema anterior: precisa de migração (importar.py) antes de ser usado."""


# ------------------------------------------------------------------ conexão e esquema
def comandos_sql(texto):
    """Divide um script SQL em comandos (sem comentários) para executar dentro de uma transação."""
    sem_coment = "\n".join(l.split("--", 1)[0] for l in texto.splitlines())
    return [c.strip() for c in sem_coment.split(";") if c.strip()]


def versao_banco(conn):
    tabelas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "schema_versao" in tabelas:
        return conn.execute("SELECT MAX(versao) FROM schema_versao").fetchone()[0] or 0
    if "conjuntos" in tabelas or "trechos" in tabelas:
        return 1
    return 0


def aplicar_esquema(conn):
    with open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        for cmd in comandos_sql(f.read()):
            conn.execute(cmd)
    conn.execute("INSERT OR IGNORE INTO schema_versao VALUES (?,?,?)",
                 (VERSAO_ESQUEMA, _agora(), "estoque: custódia por sessão, reserva coberta, retificação de fechamento"))


def conectar(caminho=DB_PADRAO, permitir_antigo=False):
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    conn = sqlite3.connect(caminho, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    v = versao_banco(conn)
    if 0 < v < VERSAO_ESQUEMA:
        if not permitir_antigo:
            conn.close()
            raise EsquemaAntigo(f"{caminho} está no esquema v{v}. Rode `python importar.py` (simulação) e depois "
                                "`python importar.py --aplicar` para migrar preservando os movimentos.")
        return conn
    conn.execute("PRAGMA foreign_keys = ON")
    if v == 0:
        with transacao(conn):
            aplicar_esquema(conn)
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
    return parametro(conn, "contrato", "CT 10239/2026 Caesb × Ankara")


def _agora():
    return datetime.now().isoformat(timespec="seconds")


def mapa_servicos():
    with open(os.path.join(BASE, "config", "servicos_rede.json"), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ alvos: trecho e atividade (elemento × frente)
def _tipo_alvo(t):
    t = ALIAS_ALVO.get(t, t)
    if t not in ("TRECHO", "ATIVIDADE"):
        raise RegraViolada(f"Tipo de alvo inválido: {t}")
    return t


def alvo(conn, alvo_tipo, ref, operacao=False):
    """Aceita o ID estável (TR-/AT-) ou o nome visível vigente (PONTO / nomenclatura).

    Retorna o registro com `id` estável e `nome` visível. Consulta pelo ID alcança também o
    histórico (vigente = 0). Com operacao=True o alvo precisa estar vigente: objeto retirado
    da revisão do projeto não recebe check-in, apontamento, foto, OK, recomposição nem cadastro.
    """
    t = _tipo_alvo(alvo_tipo)
    if t == "TRECHO":
        a = (_one(conn, "SELECT * FROM trechos WHERE id=?", ref)
             or _one(conn, "SELECT * FROM trechos WHERE ponto=? AND vigente=1", ref))
        if a:
            a["nome"] = a["ponto"]
    else:
        sql = """SELECT a.*, e.numero, e.tipo AS tipo_elemento, e.pb, e.lat, e.lon, e.handle, e.status_posicao,
                        e.zona
                 FROM atividades a JOIN elementos e ON e.id=a.elemento_id WHERE """
        sql = sql.replace("e.zona", "e.zona, e.vigente AS elemento_vigente")
        a = _one(conn, sql + "a.id=?", ref) or _one(conn, sql + "a.nomenclatura=? AND a.vigente=1", ref)
        if a:
            a["nome"] = a["nomenclatura"]
    if not a:
        raise RegraViolada(f"{t} '{ref}' não encontrado.")
    a["alvo_tipo"] = t
    a["retirado"] = not a["vigente"] or (t == "ATIVIDADE" and not a.get("elemento_vigente", 1))
    if operacao and a["retirado"]:
        raise RegraViolada(f"{a['nome']} ({a['id']}) foi retirado da revisão vigente do projeto: consulta permitida, "
                           "novos lançamentos bloqueados. Trate o histórico pela conciliação da importação.")
    return a


def _retirado(conn, alvo_tipo, alvo_id):
    try:
        return alvo(conn, alvo_tipo, alvo_id)["retirado"]
    except RegraViolada:
        return True


def nome_alvo(conn, alvo_tipo, alvo_id):
    try:
        return alvo(conn, alvo_tipo, alvo_id)["nome"]
    except RegraViolada:
        return alvo_id


def buscar(conn, q, limite=30):
    """Busca por trecho (TR001 / nome), nó/caixa (NÓ1.8, NO1.8, DF-33) ou nomenclatura."""
    q = (q or "").strip()
    if not q:
        return []
    up = q.upper()
    termo = "%" + (up.replace("NO", "NÓ", 1) if up.startswith("NO") else up) + "%"
    out = [{"tipo": "TRECHO", "id": r["id"], "rotulo": r["ponto"], "extra": f"DE{int(r['de_mm'])} · {r['extensao_m']:.2f} m"}
           for r in conn.execute("SELECT id, ponto, de_mm, extensao_m FROM trechos WHERE vigente=1 AND UPPER(ponto) LIKE ? "
                                 "ORDER BY ponto LIMIT ?", (termo, limite))]
    out += [{"tipo": "ATIVIDADE", "id": r["id"], "rotulo": r["nomenclatura"], "extra": r["frente_id"]}
            for r in conn.execute("SELECT id, nomenclatura, frente_id FROM atividades WHERE vigente=1 AND "
                                  "UPPER(nomenclatura) LIKE ? ORDER BY nomenclatura LIMIT ?", (termo, limite))]
    return out[:limite]


def execucao(conn, alvo_tipo, alvo_id):
    return _one(conn, "SELECT * FROM execucao WHERE alvo_tipo=? AND alvo_id=?", _tipo_alvo(alvo_tipo), alvo_id)


def itens_atividade(conn, atividade_id):
    return _rows(conn.execute("SELECT * FROM itens_projeto WHERE atividade_id=? AND vigente=1 ORDER BY id", (atividade_id,)))


def totais_atividade(conn, atividade_ref):
    """Contador por unidade (ex.: Zona01_PB01_CH_DF-33 → 17 UN · 0,71 m).

    Itens sem quantidade ou sem unidade com fonte não entram como zero: são contados à parte.
    """
    itens = itens_atividade(conn, alvo(conn, "ATIVIDADE", atividade_ref)["id"])
    ok = [(i["unidade"], i["quantidade"]) for i in itens if i["quantidade"] is not None and i["unidade"]]
    pend = len(itens) - len(ok)
    tot = R.somar_por_unidade(ok)
    texto = R.formatar_por_unidade(tot) if tot else ""
    if pend:
        texto = (texto + " · " if texto else "") + f"{pend} item(ns) com quantidade/unidade pendente"
    return {"totais": tot, "texto": texto, "linhas": len(itens), "pendentes": pend}


def previsto(conn, alvo_tipo, ref, metros):
    a = alvo(conn, alvo_tipo, ref)
    if a["alvo_tipo"] == "TRECHO":
        return R.quantidades_previstas_trecho(a, json.loads(a["quantidades"]), metros, mapa_servicos())
    itens = itens_atividade(conn, a["id"])
    pend = [i for i in itens if i["quantidade"] is None or not i["unidade"]]
    if pend:
        raise RegraViolada(f"{a['nome']}: {len(pend)} item(ns) sem quantidade/unidade com fonte — apontamento bloqueado "
                           "até a definição (ex.: " + "; ".join(f"{i['descricao']} ({i['unidade_fonte']})" for i in pend[:3]) + ").")
    return R.quantidades_previstas_elemento(itens)


def trechos_da_atividade(conn, atividade_id):
    """Trechos ligados: pontas da 06.1 nas nomenclaturas do elemento + coluna TRECHO (BC) da 06.2."""
    a = alvo(conn, "ATIVIDADE", atividade_id)
    noms = [r[0] for r in conn.execute("SELECT nomenclatura FROM atividades WHERE elemento_id=?", (a["elemento_id"],))]
    pontos = set()
    if noms:
        ph = ",".join("?" * len(noms))
        pontos |= {r[0] for r in conn.execute(
            f"SELECT ponto FROM trechos WHERE vigente=1 AND (no_ini IN ({ph}) OR no_fim IN ({ph}))", noms + noms)}
    for r in conn.execute("SELECT DISTINCT trechos FROM itens_projeto WHERE atividade_id=? AND vigente=1 AND trechos IS NOT NULL",
                          (a["id"],)):
        pontos |= {t.strip() for t in r[0].split("/") if t.strip()}
    if not pontos:
        return []
    ph = ",".join("?" * len(pontos))
    return [dict(r) for r in conn.execute(f"SELECT id, ponto FROM trechos WHERE vigente=1 AND ponto IN ({ph}) ORDER BY ponto",
                                          sorted(pontos))]


def _sinalizacao_herdada(conn, alvo_tipo, alvo_id):
    if alvo_tipo == "TRECHO":
        return False
    ids = [t["id"] for t in trechos_da_atividade(conn, alvo_id)]
    if not ids:
        return False
    ph = ",".join("?" * len(ids))
    return conn.execute(f"SELECT 1 FROM fotos WHERE alvo_tipo='TRECHO' AND categoria='SINALIZACAO' AND alvo_id IN ({ph}) LIMIT 1",
                        ids).fetchone() is not None


def fotos_faltando(conn, alvo_tipo, ref):
    a = alvo(conn, alvo_tipo, ref)
    cats = [r[0] for r in conn.execute("SELECT categoria FROM fotos WHERE alvo_tipo=? AND alvo_id=?", (a["alvo_tipo"], a["id"]))]
    return R.fotos_pendentes(a["alvo_tipo"], cats, _sinalizacao_herdada(conn, a["alvo_tipo"], a["id"]))


# ------------------------------------------------------------------ almoxarifado (etapa 3)
# Saldo físico do almoxarifado = entradas − saídas físicas, sem movimentos estornados.
# BAIXA_TEORICA (MVP antigo) não é saída física: estimativa geométrica não baixa estoque.
# Disponível = físico − reservas ATIVAS. Custódia é da EQUIPE (o que fica com ela passa para o dia seguinte).
ENTRA_ALMOX = ("ROMANEIO_CAESB", "ENTRADA_NF", "ENTRADA_CONSUMO", "SOBRA")
SAI_ALMOX = ("EMPRESTIMO_OUTRA_OBRA", "CUSTODIA")
VALIDO = "id NOT IN (SELECT movimento_id FROM estornos)"


def saldo_almox(conn, material_id):
    r = conn.execute(
        f"""SELECT
              COALESCE(SUM(CASE WHEN tipo IN {ENTRA_ALMOX} AND COALESCE(status,'ACEITO')='ACEITO' THEN quantidade END),0)
            - COALESCE(SUM(CASE WHEN tipo IN {SAI_ALMOX} THEN quantidade END),0) AS saldo,
              COALESCE(SUM(CASE WHEN tipo='ENTRADA_NF' AND status='QUARENTENA' THEN quantidade END),0) AS quarentena
            FROM movimentos WHERE material_id=? AND {VALIDO}""", (material_id,)).fetchone()
    return r["saldo"], r["quarentena"]


def reservado(conn, material_id, equipe_id=None, data=None):
    sql, args = "SELECT COALESCE(SUM(quantidade),0) FROM reservas WHERE material_id=? AND status='ATIVA'", [material_id]
    if equipe_id:
        sql, args = sql + " AND equipe_id=? AND data=?", args + [equipe_id, data]
    return conn.execute(sql, args).fetchone()[0]


def disponivel(conn, material_id):
    return saldo_almox(conn, material_id)[0] - reservado(conn, material_id)


def _ate_sessao(ck):
    """Filtro dos movimentos das sessões (check-ins) da equipe até `ck` inclusive, em ordem (data, id).
    Um fechamento nunca enxerga retiradas de sessões posteriores."""
    if ck is None:
        return "", ()
    return (" AND checkin_id IN (SELECT id FROM checkins WHERE equipe_id=? AND (data < ? OR (data = ? AND id <= ?)))",
            (ck["equipe_id"], ck["data"], ck["data"], ck["id"]))


def custodia_equipe(conn, equipe_id, material_id, ate_checkin=None):
    """Material com a equipe (retiradas − aplicado − sobra devolvida − perda), sem estornos.
    Com `ate_checkin`, só até aquela sessão (custódia cronológica)."""
    ck = _one(conn, "SELECT * FROM checkins WHERE id=?", ate_checkin) if ate_checkin else None
    filtro, args = _ate_sessao(ck)
    return conn.execute(
        f"""SELECT COALESCE(SUM(CASE WHEN tipo='CUSTODIA' THEN quantidade
                                    WHEN tipo IN ('APLICADO','SOBRA','PERDA') THEN -quantidade END),0)
            FROM movimentos WHERE equipe_id=? AND material_id=? AND checkin_id IS NOT NULL AND {VALIDO}{filtro}""",
        (equipe_id, material_id, *args)).fetchone()[0]


def _materiais_com_equipe(conn, equipe_id, ate_checkin=None):
    return [r[0] for r in conn.execute(
        f"SELECT DISTINCT material_id FROM movimentos WHERE equipe_id=? AND checkin_id IS NOT NULL AND {VALIDO} "
        "ORDER BY material_id", (equipe_id,)) if abs(custodia_equipe(conn, equipe_id, r[0], ate_checkin)) > 1e-9]


def _soma(conn, material_id, tipo):
    return conn.execute(f"SELECT COALESCE(SUM(quantidade),0) FROM movimentos WHERE material_id=? AND tipo=? AND {VALIDO}",
                        (material_id, tipo)).fetchone()[0]


def estoque(conn):
    out = []
    for m in _rows(conn.execute("SELECT * FROM materiais ORDER BY propriedade, id")):
        saldo, quar = saldo_almox(conn, m["id"])
        res = reservado(conn, m["id"])
        cust = conn.execute(
            f"""SELECT COALESCE(SUM(CASE WHEN tipo='CUSTODIA' THEN quantidade
                                        WHEN tipo IN ('APLICADO','SOBRA','PERDA') THEN -quantidade END),0)
                FROM movimentos WHERE material_id=? AND checkin_id IS NOT NULL AND {VALIDO}""", (m["id"],)).fetchone()[0]
        out.append({**m, "saldo_almox": round(saldo, 3), "quarentena": round(quar, 3), "reservado": round(res, 3),
                    "disponivel": round(saldo - res, 3), "custodia": round(cust, 3),
                    "baixa_teorica_legada": round(_soma(conn, m["id"], "BAIXA_TEORICA"), 3)})
    return out


def compatibilizacao_caesb(conn):
    """Projeto 06.1 × Estoque Caesb × Emprestado × Retirado × Aplicado × Saldo Virtual (sem movimentos estornados)."""
    out = []
    for m in _rows(conn.execute("SELECT * FROM materiais WHERE propriedade='CAESB' ORDER BY id")):
        s = {t: _soma(conn, m["id"], t) for t in ("ROMANEIO_CAESB", "EMPRESTIMO_OUTRA_OBRA", "APLICADO", "PERDA")}
        projeto = m["qtd_projeto"] or 0
        out.append({
            "material_id": m["id"], "descricao": m["descricao"], "unidade": m["unidade"],
            "projeto": projeto, "estoque_caesb": m["estoque_caesb"],
            "emprestado": s["EMPRESTIMO_OUTRA_OBRA"], "retirado": s["ROMANEIO_CAESB"],
            "aplicado": s["APLICADO"], "perdido": s["PERDA"],
            "saldo_virtual": round(projeto - (s["ROMANEIO_CAESB"] - s["EMPRESTIMO_OUTRA_OBRA"]), 3),
            "saldo_fisico": round(s["ROMANEIO_CAESB"] - s["EMPRESTIMO_OUTRA_OBRA"] - s["APLICADO"] - s["PERDA"], 3),
        })
    return out


def consumo_previsto_x_confirmado(conn):
    """Tubos PEAD Caesb: metros apontados nos trechos de cada DE (previsto) × APLICADO no check-out (confirmado).
    O previsto é só referência de conferência: nunca baixa estoque."""
    out = []
    for m in _rows(conn.execute("SELECT * FROM materiais WHERE propriedade='CAESB' AND id LIKE 'CAESB-PEAD-DE%' ORDER BY id")):
        de = float(m["id"].rsplit("DE", 1)[1])
        prev = conn.execute(
            """SELECT COALESCE(SUM(ap.metros_executados),0) FROM apontamentos ap JOIN trechos t ON t.id=ap.alvo_id
               WHERE ap.alvo_tipo='TRECHO' AND t.de_mm=?""", (de,)).fetchone()[0]
        conf = _soma(conn, m["id"], "APLICADO")
        out.append({"material_id": m["id"], "unidade": m["unidade"], "previsto_apontado": round(prev, 3),
                    "aplicado_confirmado": round(conf, 3), "diferenca": round(conf - prev, 3)})
    return out


def movimentos(conn, limite=100, material_id=None):
    sql = """SELECT m.*, e.motivo AS estorno_motivo, e.responsavel AS estorno_responsavel, e.em AS estornado_em,
                    c.encerrado AS checkin_encerrado
             FROM movimentos m LEFT JOIN estornos e ON e.movimento_id=m.id LEFT JOIN checkins c ON c.id=m.checkin_id"""
    args = []
    if material_id:
        sql, args = sql + " WHERE m.material_id=?", [material_id]
    return _rows(conn.execute(sql + " ORDER BY m.id DESC LIMIT ?", args + [limite]))


def entrada_material(conn, data, material_id, quantidade, tipo, documento=None, responsavel=None, autorizacao=None):
    if tipo == "BAIXA_TEORICA":
        raise RegraViolada("Baixa teórica não altera o estoque físico: o consumo é confirmado no check-out "
                           "(aplicado / sobra / perda). Para corrigir um lançamento, use o estorno.")
    if tipo not in ("ROMANEIO_CAESB", "ENTRADA_CONSUMO", "EMPRESTIMO_OUTRA_OBRA"):
        raise RegraViolada(f"Tipo de movimento inválido aqui: {tipo}")
    if not quantidade or quantidade <= 0:
        raise RegraViolada("Informe uma quantidade maior que zero.")
    m = _one(conn, "SELECT * FROM materiais WHERE id=?", material_id)
    if not m:
        raise RegraViolada(f"Material '{material_id}' não cadastrado.")
    if tipo in ("ROMANEIO_CAESB", "EMPRESTIMO_OUTRA_OBRA") and m["propriedade"] != "CAESB":
        raise RegraViolada("Romaneio/empréstimo só se aplica a tubos de fornecimento Caesb.")
    if tipo == "ENTRADA_CONSUMO" and m["propriedade"] != "CONSUMO":
        raise RegraViolada("Entrada por caminhão/nota de canteiro só para materiais de consumo diário.")
    if tipo == "EMPRESTIMO_OUTRA_OBRA":
        falta = [n for n, v in (("documento", documento), ("responsável", responsavel), ("autorização", autorizacao))
                 if not (v or "").strip()]
        if falta:
            raise RegraViolada("Empréstimo para outra obra exige " + ", ".join(falta) + ".")
        if disponivel(conn, material_id) + TOL < quantidade:
            raise RegraViolada(f"Disponível insuficiente ({disponivel(conn, material_id):g} {m['unidade']}, já descontadas "
                               "as reservas das equipes).")
    conn.execute("INSERT INTO movimentos(data,material_id,tipo,quantidade,documento,status,responsavel,autorizacao) "
                 "VALUES (?,?,?,?,?,?,?,?)", (data, material_id, tipo, quantidade, documento, "ACEITO", responsavel, autorizacao))


def reservar(conn, data, equipe_id, material_id, quantidade, alvo_tipo=None, alvo_id=None, responsavel=None):
    """Reserva do almoxarifado para a programação de uma equipe/dia. Não é saída: só tira do disponível."""
    if equipe_id not in [r[0] for r in conn.execute("SELECT id FROM equipes")]:
        raise RegraViolada(f"Equipe '{equipe_id}' não cadastrada.")
    m = _one(conn, "SELECT * FROM materiais WHERE id=?", material_id)
    if not m:
        raise RegraViolada(f"Material '{material_id}' não cadastrado.")
    if m["propriedade"] == "CONSUMO":
        raise RegraViolada("Material de consumo diário não é reservado por equipe.")
    q = float(quantidade or 0)
    if q <= 0:
        raise RegraViolada("Informe uma quantidade maior que zero.")
    tipo = ref = None
    if alvo_tipo and alvo_id:
        a = alvo(conn, alvo_tipo, alvo_id, operacao=True)
        tipo, ref = a["alvo_tipo"], a["id"]
    disp = disponivel(conn, material_id)
    if disp + TOL < q:
        raise RegraViolada(f"Disponível insuficiente de {material_id}: {disp:g} {m['unidade']} (saldo físico menos "
                           "reservas de outras equipes).")
    return conn.execute(
        "INSERT INTO reservas(data,equipe_id,material_id,quantidade,alvo_tipo,alvo_id,responsavel,criada_em) "
        "VALUES (?,?,?,?,?,?,?,?)", (data, equipe_id, material_id, q, tipo, ref, responsavel, _agora())).lastrowid


def cancelar_reserva(conn, reserva_id, motivo):
    r = _one(conn, "SELECT * FROM reservas WHERE id=?", reserva_id)
    if not r or r["status"] != "ATIVA":
        raise RegraViolada("Reserva inexistente ou já encerrada.")
    if not (motivo or "").strip():
        raise RegraViolada("Informe o motivo do cancelamento.")
    conn.execute("UPDATE reservas SET status='CANCELADA', encerrada_em=?, motivo=? WHERE id=?", (_agora(), motivo, reserva_id))


def reservas_ativas(conn, data=None):
    sql = "SELECT * FROM reservas WHERE status='ATIVA'" + (" AND data=?" if data else "") + " ORDER BY data, equipe_id"
    return _rows(conn.execute(sql, (data,) if data else ()))


def _ajustar_reservas_descobertas(conn, material_id, motivo, responsavel, movimento_id):
    """Reduz (ou cancela) as reservas ativas mais recentes até o disponível voltar a zero. Cada ajuste fica
    registrado em reserva_ajustes, com o estorno que o causou."""
    falta = -disponivel(conn, material_id)
    for r in _rows(conn.execute("SELECT * FROM reservas WHERE material_id=? AND status='ATIVA' ORDER BY criada_em DESC, id DESC",
                                (material_id,))):
        if falta <= TOL:
            break
        nova = round(r["quantidade"] - min(falta, r["quantidade"]), 6)
        falta -= r["quantidade"] - nova
        if nova <= TOL:
            conn.execute("UPDATE reservas SET status='CANCELADA', encerrada_em=?, motivo=? WHERE id=?",
                         (_agora(), f"sem cobertura após estorno do movimento {movimento_id}: {motivo}", r["id"]))
        else:
            conn.execute("UPDATE reservas SET quantidade=? WHERE id=?", (nova, r["id"]))
        conn.execute("INSERT INTO reserva_ajustes(reserva_id,de,para,motivo,responsavel,movimento_id,em) VALUES (?,?,?,?,?,?,?)",
                     (r["id"], r["quantidade"], max(nova, 0), motivo, responsavel, movimento_id, _agora()))


def _estornar_sem_transacao(conn, mv, motivo, responsavel, ajustar_reservas=False):
    conn.execute("INSERT INTO estornos VALUES (?,?,?,?)", (mv["id"], motivo.strip(), responsavel.strip(), _agora()))
    if saldo_almox(conn, mv["material_id"])[0] < -TOL:
        raise RegraViolada("Estorno recusado: o saldo do almoxarifado ficaria negativo (o material já saiu). "
                           "Estorne antes os movimentos posteriores.")
    if mv["equipe_id"] and mv["checkin_id"] and custodia_equipe(conn, mv["equipe_id"], mv["material_id"]) < -TOL:
        raise RegraViolada("Estorno recusado: a custódia da equipe ficaria negativa. Retifique antes o fechamento "
                           "que consumiu esse material.")
    if disponivel(conn, mv["material_id"]) < -TOL:
        if not ajustar_reservas:
            res = reservas_ativas(conn)
            lista = ", ".join(f"#{r['id']} {r['equipe_id']} {r['data']} {r['quantidade']:g}" for r in res
                              if r["material_id"] == mv["material_id"])
            raise RegraViolada(f"Estorno recusado: deixaria reservas ativas sem cobertura (disponível "
                               f"{disponivel(conn, mv['material_id']):g}). Reservas: {lista}. Cancele/reduza essas reservas "
                               "ou confirme o ajuste automático das mais recentes (ajustar_reservas).")
        _ajustar_reservas_descobertas(conn, mv["material_id"], motivo, responsavel, mv["id"])


def estornar(conn, movimento_id, motivo, responsavel, ajustar_reservas=False):
    """Correção de movimento sem apagar: o original fica, marcado como estornado, e sai dos saldos.

    Recusa se deixar saldo do almoxarifado ou custódia da equipe negativos, ou reservas ativas sem cobertura
    (a não ser com ajustar_reservas=True: as reservas mais recentes são reduzidas/canceladas e o ajuste fica
    registrado). Aplicado/sobra/perda de um fechamento já encerrado só se corrige pela retificação do fechamento.
    """
    mv = _one(conn, "SELECT * FROM movimentos WHERE id=?", movimento_id)
    if not mv:
        raise RegraViolada("Movimento não encontrado.")
    if _one(conn, "SELECT 1 AS x FROM estornos WHERE movimento_id=?", movimento_id):
        raise RegraViolada("Movimento já estornado.")
    if not (motivo or "").strip() or not (responsavel or "").strip():
        raise RegraViolada("Estorno exige motivo e responsável.")
    if mv["tipo"] == "ENTRADA_NF":
        raise RegraViolada("Entrada por NF não é estornada aqui: trate pela nota fiscal (devolução/recusa).")
    if mv["tipo"] in ("APLICADO", "SOBRA", "PERDA") and mv["checkin_id"]:
        raise RegraViolada("Aplicado/sobra/perda de um check-out encerrado: use a retificação do fechamento, que "
                           "estorna e redistribui a mesma quantidade no mesmo dia, com motivo.")
    with transacao(conn):
        _estornar_sem_transacao(conn, mv, motivo, responsavel, ajustar_reservas)


def retificar_fechamento(conn, movimento_id, destino, motivo, responsavel, ajustar_reservas=False):
    """Retifica um aplicado/sobra/perda de um check-out já encerrado, sem nova visita de campo.

    O movimento original é estornado (fica no histórico) e a MESMA quantidade é redistribuída em
    aplicado / sobra / perda / fica_com_equipe, com a data e a sessão originais, ligada à retificação
    (motivo, responsável, movimento original). O check-in continua encerrado; nada é reaberto.
    """
    mv = _one(conn, "SELECT * FROM movimentos WHERE id=?", movimento_id)
    if not mv or mv["tipo"] not in ("APLICADO", "SOBRA", "PERDA") or not mv["checkin_id"]:
        raise RegraViolada("Só se retifica aplicado, sobra ou perda lançados num check-out.")
    ck = _one(conn, "SELECT * FROM checkins WHERE id=?", mv["checkin_id"])
    if not ck["encerrado"]:
        raise RegraViolada("O check-in ainda está aberto: corrija no próprio check-out.")
    if _one(conn, "SELECT 1 AS x FROM estornos WHERE movimento_id=?", movimento_id):
        raise RegraViolada("Movimento já estornado.")
    if not (motivo or "").strip() or not (responsavel or "").strip():
        raise RegraViolada("Retificação exige motivo e responsável.")
    ap, so, pe, fica = (float(destino.get(k) or 0) for k in ("aplicado", "sobra", "perda", "fica_com_equipe"))
    if min(ap, so, pe, fica) < 0:
        raise RegraViolada("Quantidades não podem ser negativas.")
    if abs(ap + so + pe + fica - mv["quantidade"]) > 1e-3:
        raise RegraViolada(f"A retificação redistribui a mesma quantidade ({mv['quantidade']:g}); informado {ap + so + pe + fica:g}.")
    if pe > 0 and not (destino.get("motivo_perda") or "").strip():
        raise RegraViolada("Informe o motivo da perda.")
    with transacao(conn):
        rid = conn.execute("INSERT INTO retificacoes(checkin_id,movimento_id,destino,motivo,responsavel,em) VALUES (?,?,?,?,?,?)",
                           (ck["id"], movimento_id, json.dumps(destino, ensure_ascii=False), motivo.strip(),
                            responsavel.strip(), _agora())).lastrowid
        conn.execute("INSERT INTO estornos VALUES (?,?,?,?)", (movimento_id, f"retificação #{rid}: {motivo.strip()}",
                                                             responsavel.strip(), _agora()))
        for tipo, q in (("APLICADO", ap), ("SOBRA", so), ("PERDA", pe)):
            if q > 0:
                conn.execute(
                    """INSERT INTO movimentos(data,material_id,tipo,quantidade,equipe_id,alvo_tipo,alvo_id,motivo,checkin_id,
                         responsavel,retificacao_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (mv["data"], mv["material_id"], tipo, q, mv["equipe_id"], mv["alvo_tipo"], mv["alvo_id"],
                     destino.get("motivo_perda") if tipo == "PERDA" else None, ck["id"], responsavel.strip(), rid))
        if fica > 0:
            conn.execute("""INSERT INTO custodia_declarada VALUES (?,?,?,?) ON CONFLICT(checkin_id, material_id)
                            DO UPDATE SET quantidade = quantidade + excluded.quantidade, em = excluded.em""",
                         (ck["id"], mv["material_id"], fica, _agora()))
        if saldo_almox(conn, mv["material_id"])[0] < -TOL:
            raise RegraViolada("Retificação recusada: o saldo do almoxarifado ficaria negativo (a sobra já saiu de novo).")
        if disponivel(conn, mv["material_id"]) < -TOL:
            if not ajustar_reservas:
                raise RegraViolada("Retificação recusada: deixaria reservas ativas sem cobertura. Trate as reservas ou "
                                   "confirme o ajuste (ajustar_reservas).")
            _ajustar_reservas_descobertas(conn, mv["material_id"], motivo, responsavel, movimento_id)
    return rid


def registrar_nf(conn, numero, fornecedor, data_entrega, itens, faturamento_etapas=False, chave_nfe=None, arquivo=None):
    """NF entra em quarentena. `faturamento_etapas` só registra a intenção: nenhum regime é aplicado."""
    with transacao(conn):
        nf_id = conn.execute(
            """INSERT INTO notas_fiscais(numero,chave_nfe,fornecedor,data_entrega,arquivo,faturamento_etapas,status)
               VALUES (?,?,?,?,?,?, 'QUARENTENA')""",
            (numero, chave_nfe, fornecedor, data_entrega, arquivo, 1 if faturamento_etapas else 0)).lastrowid
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
    """Laudo aprovado: material sai da quarentena e passa a compor estoque.

    Aceite do almoxarifado cria estoque, não elegibilidade financeira: nenhum lançamento de
    medição é gerado até a aprovação da matriz de regimes (docs/MATRIZ_REGIMES_FATURAMENTO.md).
    """
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", nf_id)
    if not nf:
        raise RegraViolada("Nota fiscal não encontrada.")
    if nf["status"] == "ACEITO":
        raise RegraViolada("Nota fiscal já aceita.")
    if not laudo_arquivo:
        raise RegraViolada("Anexe o laudo de inspeção.")
    with transacao(conn):
        conn.execute("UPDATE notas_fiscais SET status='ACEITO', laudo_arquivo=? WHERE id=?", (laudo_arquivo, nf_id))
        conn.execute("UPDATE movimentos SET status='ACEITO' WHERE nf_id=? AND tipo='ENTRADA_NF'", (nf_id,))


# ------------------------------------------------------------------ check-in / check-out
def checkin(conn, data, equipe_id, alvo_tipo=None, alvo_id=None, funcionarios=(), maquinas=(),
            materiais=(), contingencia=None):
    """Presença + retirada do dia. A retirada consome primeiro a reserva da própria equipe para o dia;
    o restante precisa caber no disponível (saldo físico − reservas de outras equipes)."""
    if equipe_id not in [r[0] for r in conn.execute("SELECT id FROM equipes")]:
        raise RegraViolada(f"Equipe '{equipe_id}' não cadastrada.")
    tipo = ref = None
    if contingencia:
        if contingencia not in R.CONTINGENCIAS:
            raise RegraViolada("Contingência inválida.")
    elif not (alvo_tipo and alvo_id):
        raise RegraViolada("Informe o Trecho/Nó que a equipe vai atacar hoje (ou uma contingência).")
    else:
        a = alvo(conn, alvo_tipo, alvo_id, operacao=True)
        tipo, ref = a["alvo_tipo"], a["id"]
    aberto = _one(conn, "SELECT id, data FROM checkins WHERE equipe_id=? AND encerrado=0 ORDER BY data, id LIMIT 1", equipe_id)
    if aberto:
        raise RegraViolada(f"A {equipe_id} tem check-in aberto em {aberto['data']} — faça o check-out dele antes de um novo "
                           "check-in (a custódia é fechada dia a dia, em ordem).")
    ultimo = _one(conn, "SELECT MAX(data) AS d FROM checkins WHERE equipe_id=?", equipe_id)["d"]
    if ultimo and data < ultimo:
        raise RegraViolada(f"Check-in retroativo recusado: a {equipe_id} já tem sessão em {ultimo}. Um dia anterior não pode "
                           "consumir nem alterar a custódia de dias posteriores.")
    with transacao(conn):
        cid = conn.execute("INSERT INTO checkins(data,equipe_id,alvo_tipo,alvo_id,contingencia) VALUES (?,?,?,?,?)",
                           (data, equipe_id, tipo, ref, contingencia)).lastrowid
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
                raise RegraViolada(f"{mat['descricao']}: material de consumo não sai por requisição de equipe.")
            propria = reservado(conn, mat["id"], equipe_id, data)
            livre = disponivel(conn, mat["id"]) + propria          # a reserva da própria equipe pode ser usada
            if livre + TOL < q:
                raise RegraViolada(f"Disponível insuficiente de {mat['descricao']}: {livre:g} {mat['unidade']} "
                                   f"(inclui a reserva da {equipe_id} para {data}; reservas de outras equipes não são usadas).")
            conn.execute(
                """INSERT INTO movimentos(data,material_id,tipo,quantidade,equipe_id,alvo_tipo,alvo_id,checkin_id)
                   VALUES (?,?,'CUSTODIA',?,?,?,?,?)""", (data, mat["id"], q, equipe_id, tipo, ref, cid))
            if propria:
                obs = "retirada menor que a reserva; restante liberado" if q + TOL < propria else None
                conn.execute("UPDATE reservas SET status='ATENDIDA', checkin_id=?, encerrada_em=?, motivo=? "
                             "WHERE material_id=? AND equipe_id=? AND data=? AND status='ATIVA'",
                             (cid, _agora(), obs, mat["id"], equipe_id, data))
    return cid


def checkout(conn, checkin_id, itens):
    """Fecha o dia com o encarregado. Para cada material com a equipe (inclusive o que ela trouxe de dias
    anteriores): aplicado + sobra devolvida + perda + fica_com_equipe = custódia da equipe.
    O que fica com a equipe é declarado e volta como custódia no próximo check-in."""
    ck = _one(conn, "SELECT * FROM checkins WHERE id=?", checkin_id)
    if not ck or ck["encerrado"]:
        raise RegraViolada("Check-in inexistente ou já encerrado. Para corrigir um fechamento, use a retificação.")
    anterior = _one(conn, "SELECT id, data FROM checkins WHERE equipe_id=? AND encerrado=0 AND id<>? AND "
                          "(data < ? OR (data = ? AND id < ?)) ORDER BY data, id LIMIT 1",
                    ck["equipe_id"], checkin_id, ck["data"], ck["data"], checkin_id)
    if anterior:
        raise RegraViolada(f"Feche antes o check-in de {anterior['data']} da {ck['equipe_id']} (fechamentos em ordem).")
    declarados = {it["material_id"]: it for it in itens}
    faltam = [m for m in _materiais_com_equipe(conn, ck["equipe_id"], checkin_id) if m not in declarados]
    if faltam:
        raise RegraViolada("Declare no check-out todo material com a equipe (aplicado, sobra, perda ou fica com a "
                           "equipe): " + ", ".join(faltam))
    with transacao(conn):
        for mid, it in declarados.items():
            ap, so, pe, fica = (float(it.get(k) or 0) for k in ("aplicado", "sobra", "perda", "fica_com_equipe"))
            if min(ap, so, pe, fica) < 0:
                raise RegraViolada("Quantidades do check-out não podem ser negativas.")
            if pe > 0 and not (it.get("motivo") or "").strip():
                raise RegraViolada("Informe o motivo da quebra/perda.")
            cust = custodia_equipe(conn, ck["equipe_id"], mid, checkin_id)     # só até esta sessão
            if abs((ap + so + pe + fica) - cust) > 1e-3:
                raise RegraViolada(f"{mid}: aplicado + sobra + perda + fica com a equipe ({ap + so + pe + fica:g}) deve "
                                   f"fechar a custódia da equipe ({cust:g}).")
            for tipo, q in (("APLICADO", ap), ("SOBRA", so), ("PERDA", pe)):
                if q > 0:
                    conn.execute(
                        """INSERT INTO movimentos(data,material_id,tipo,quantidade,equipe_id,alvo_tipo,alvo_id,motivo,checkin_id)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (ck["data"], mid, tipo, q, ck["equipe_id"], ck["alvo_tipo"], ck["alvo_id"],
                         it.get("motivo") if tipo == "PERDA" else None, checkin_id))
            if fica > 0:
                conn.execute("INSERT OR REPLACE INTO custodia_declarada VALUES (?,?,?,?)", (checkin_id, mid, fica, _agora()))
        conn.execute("UPDATE checkins SET encerrado=1 WHERE id=?", (checkin_id,))


def checkins_abertos(conn, data=None):
    sql = "SELECT * FROM checkins WHERE encerrado=0" + (" AND data=?" if data else "") + " ORDER BY equipe_id"
    out = _rows(conn.execute(sql, (data,) if data else ()))
    for c in out:
        c["alvo_nome"] = nome_alvo(conn, c["alvo_tipo"], c["alvo_id"]) if c["alvo_id"] else None
        c["alvo_retirado"] = bool(c["alvo_id"]) and _retirado(conn, c["alvo_tipo"], c["alvo_id"])
        hoje = {r[0]: r[1] for r in conn.execute(
            f"SELECT material_id, SUM(quantidade) FROM movimentos WHERE checkin_id=? AND tipo='CUSTODIA' AND {VALIDO} "
            "GROUP BY material_id", (c["id"],))}
        c["materiais"] = [{"material_id": m, "quantidade": custodia_equipe(conn, c["equipe_id"], m, c["id"]),
                           "retirado_hoje": hoje.get(m, 0.0),
                           "trazido": round(custodia_equipe(conn, c["equipe_id"], m, c["id"]) - hoje.get(m, 0.0), 6)}
                          for m in _materiais_com_equipe(conn, c["equipe_id"], c["id"])]
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


def apontar(conn, data, equipe_id, alvo_tipo, ref, metros_executados=0, metros_reaterrados=0,
            concluido_100=False, estaca_ini=None, estaca_fim=None, quantidades=None):
    """Lança avanço de campo. `quantidades=None` equivale a [✅ OK, Confirmar Previsto]."""
    turnos = {r["turno"] for r in conn.execute("SELECT turno FROM clima WHERE data=? AND equipe_id=?", (data, equipe_id))}
    if turnos != {"MANHA", "TARDE"}:
        raise RegraViolada("Clima do dia obrigatório nos dois turnos (manhã e tarde) antes do apontamento.")
    a = alvo(conn, alvo_tipo, ref, operacao=True)
    tipo, aid = a["alvo_tipo"], a["id"]
    ex = execucao(conn, tipo, aid) or {"metros_executados": 0, "metros_reaterrados": 0, "concluido": 0}
    if ex.get("ok_fiscal_em"):
        raise RegraViolada("Alvo já validado pela fiscalização — não aceita novos apontamentos.")
    if tipo == "TRECHO":
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
        prev = previsto(conn, tipo, aid, metros_executados) if metros_executados > 0 else []
    else:
        novo_exec = novo_reat = 0
        concluido = 1 if concluido_100 else 0
        prev = previsto(conn, tipo, aid, 0) if concluido else []
    with transacao(conn):
        apid = conn.execute(
            """INSERT INTO apontamentos(data,equipe_id,alvo_tipo,alvo_id,metros_executados,metros_reaterrados,estaca_ini,estaca_fim)
               VALUES (?,?,?,?,?,?,?,?)""",
            (data, equipe_id, tipo, aid, metros_executados, metros_reaterrados, estaca_ini, estaca_fim)).lastrowid
        confirmadas = {(q["servico"], q["unidade"]): q["confirmado"] for q in (quantidades or [])}
        for q in prev:
            conf = confirmadas.pop((q["servico"], q["unidade"]), q["previsto"])
            conn.execute("INSERT INTO apontamento_quantidades VALUES (?,?,?,?,?)",
                         (apid, q["servico"], q["unidade"], q["previsto"], float(conf)))
        for (serv, un), conf in confirmadas.items():
            conn.execute("INSERT INTO apontamento_quantidades VALUES (?,?,?,NULL,?)", (apid, serv, un, float(conf)))
        conn.execute(
            """INSERT INTO execucao(alvo_tipo,alvo_id,metros_executados,metros_reaterrados,concluido)
               VALUES (?,?,?,?,?)
               ON CONFLICT(alvo_tipo,alvo_id) DO UPDATE SET metros_executados=excluded.metros_executados,
                 metros_reaterrados=excluded.metros_reaterrados, concluido=MAX(concluido, excluded.concluido)""",
            (tipo, aid, novo_exec, novo_reat, concluido))
    return apid


def registrar_foto(conn, alvo_tipo, ref, categoria, conteudo_b64, extensao="jpg", data_hora=None, lat=None, lon=None,
                   dir_fotos=DIR_FOTOS):
    a = alvo(conn, alvo_tipo, ref, operacao=True)
    if categoria not in R.FOTOS_TRECHO:
        raise RegraViolada("Categoria de foto inválida.")
    data_hora = data_hora or _agora()
    carimbo = R.carimbo(contrato(conn), a["nome"], data_hora, lat, lon)
    os.makedirs(dir_fotos, exist_ok=True)
    nome = re.sub(r"[^\w.-]", "_", f"{a['id']}_{categoria}_{data_hora.replace(':', '').replace('-', '')}.{extensao}")
    with open(os.path.join(dir_fotos, nome), "wb") as f:
        f.write(base64.b64decode(conteudo_b64))
    conn.execute(
        "INSERT INTO fotos(alvo_tipo,alvo_id,area,categoria,arquivo,data_hora,lat,lon,carimbo) VALUES (?,?,?,?,?,?,?,?,?)",
        (a["alvo_tipo"], a["id"], a.get("area"), categoria, nome, data_hora, lat, lon, carimbo))
    return {"arquivo": nome, "carimbo": carimbo}


# ------------------------------------------------------------------ lançamentos (sem regime financeiro aplicado)
def _bm_item(conn, chave):
    return _one(conn, "SELECT * FROM bm_itens WHERE planilha='VERTICAL' AND item=? AND vigente=1", chave)


def _itens_servico(conn, servico, trecho):
    """[(bm_item, fração)] de um serviço da 06.1, segundo config/servicos_rede.json; [] = sem vínculo com fonte."""
    cfg = next((s for s in mapa_servicos()["gaveta1"] if s["servico"] == servico), None)
    if not cfg or cfg["status"] != "CONFIRMADO" or not cfg["itens"]:
        return []
    itens = [_bm_item(conn, k.format(codigo_bm=trecho.get("codigo_bm"))) for k in cfg["itens"]]
    itens = [i for i in itens if i]
    if not itens:
        return []
    return R.ratear(1.0, [(i, i["quantidade"] or 0) for i in itens])


def _lancar(conn, medicao_id, gaveta, servico, bm, unidade, quantidade, alvo_tipo=None, alvo_id=None,
            nf_id=None, material_id=None, motivo=None, obs=None):
    status = "PROPOSTO" if bm is not None and not motivo else "PENDENTE"
    if status == "PENDENTE" and not motivo:
        motivo = "sem item de BM com fonte"
    conn.execute(
        """INSERT INTO medicao_lancamentos(medicao_id,gaveta,servico,bm_item_id,alvo_tipo,alvo_id,nf_id,material_id,
             unidade,quantidade,status,motivo,observacao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (medicao_id, gaveta, servico, bm["id"] if bm else None, alvo_tipo, alvo_id, nf_id, material_id, unidade,
         round(quantidade, 4), status, motivo, obs))


def _vertical_por_codigo(conn, codigo_bm):
    """Item da Vertical para um código da Juntada (col. R da 06.2). Só devolve se for inequívoco."""
    if not codigo_bm:
        return None, "sem código BM"
    c = _rows(conn.execute("SELECT * FROM bm_itens WHERE planilha='VERTICAL' AND vigente=1 AND item_bm=?", (codigo_bm,)))
    if len(c) == 1:
        return c[0], None
    return None, (f"código {codigo_bm} sem item na Vertical" if not c else
                  f"código {codigo_bm} ambíguo na Vertical ({', '.join(i['item'] for i in c)})")


def ok_fiscalizacao(conn, alvo_tipo, ref, usuario, data=None):
    """[✓] OK Fiscalização (interno Ankara). Gera PROPOSTA de lançamentos na medição de teste e
    envia o trecho à Esteira de Cadastro. Não aprova nada pela Caesb e não aplica regime de material."""
    data = data or date.today().isoformat()
    a = alvo(conn, alvo_tipo, ref, operacao=True)
    tipo, aid = a["alvo_tipo"], a["id"]
    ex = execucao(conn, tipo, aid)
    R.validar_ok_fiscal(ex, fotos_faltando(conn, tipo, aid))
    med = medicao_para(conn, data)
    with transacao(conn):
        conn.execute("UPDATE execucao SET ok_fiscal_em=?, ok_fiscal_por=?, medicao_id=? WHERE alvo_tipo=? AND alvo_id=?",
                     (data, usuario, med["id"], tipo, aid))
        servs = _rows(conn.execute(
            """SELECT q.servico, q.unidade, SUM(q.confirmado) qtd FROM apontamento_quantidades q
               JOIN apontamentos ap ON ap.id=q.apontamento_id
               WHERE ap.alvo_tipo=? AND ap.alvo_id=? GROUP BY q.servico, q.unidade""", (tipo, aid)))
        if tipo == "TRECHO":
            mnd = a.get("metodologia") == "MND"
            for s in servs:
                if mnd and s["servico"] == "ASSENTAMENTO":
                    _lancar(conn, med["id"], 1, s["servico"], None, s["unidade"], s["qtd"], tipo, aid,
                            motivo=f"MND: item a definir pela engenharia (a 06.1 traz {a.get('codigo_bm')}, "
                                   "de assentamento em vala; não substituído automaticamente)")
                    continue
                itens = _itens_servico(conn, s["servico"], a)
                if not itens:
                    _lancar(conn, med["id"], 1, s["servico"], None, s["unidade"], s["qtd"], tipo, aid)
                for bm, frac in itens:
                    obs = "rateio pela proporção contratual (estimativa)" if len(itens) > 1 else None
                    _lancar(conn, med["id"], 1, s["servico"], bm, s["unidade"], s["qtd"] * frac, tipo, aid, obs=obs)
            conn.execute("INSERT INTO cadastro(trecho_id,etapa,atualizado_em) VALUES (?, '1_PRONTO', ?)", (aid, _agora()))
            conn.execute("INSERT INTO cadastro_historico(trecho_id,de_etapa,para_etapa,em) VALUES (?,NULL,'1_PRONTO',?)",
                         (aid, _agora()))
        else:
            codigos = {}
            for i in itens_atividade(conn, aid):
                codigos.setdefault(R.quantidades_previstas_elemento([i])[0]["servico"], i["codigo_bm"])
            for s in servs:
                bm, motivo = _vertical_por_codigo(conn, codigos.get(s["servico"]))
                if bm and str(bm["classificacao"]).upper().startswith("MATERIAL"):
                    bm, motivo = None, "material: regime de faturamento pendente (matriz de regimes não aprovada)"
                _lancar(conn, med["id"], 1, s["servico"], bm, s["unidade"], s["qtd"], tipo, aid, motivo=motivo)
    return med["id"]


def recomposicao_ok(conn, alvo_tipo, ref, tipo, quantidade, data=None):
    """Checkbox separado: calçada/asfalto entra só quando a equipe de pavimento executar (gaveta 4)."""
    data = data or date.today().isoformat()
    a = alvo(conn, alvo_tipo, ref, operacao=True)
    ex = execucao(conn, a["alvo_tipo"], a["id"])
    if not ex or not ex.get("ok_fiscal_em"):
        raise RegraViolada("Recomposição só pode ser lançada após o OK Fiscalização do trecho/nó.")
    if ex["recomposicao_ok"]:
        raise RegraViolada("Recomposição já lançada.")
    cfg = mapa_servicos()["recomposicao"]
    if tipo not in cfg["itens_por_tipo"]:
        raise RegraViolada("Tipo de recomposição inválido (CALÇADA ou ASFALTO).")
    if quantidade <= 0:
        raise RegraViolada("Informe a quantidade recomposta.")
    bm = _bm_item(conn, cfg["itens_por_tipo"][tipo]) if cfg["status"] == "CONFIRMADO" else None
    med = medicao_para(conn, data)
    with transacao(conn):
        conn.execute("UPDATE execucao SET recomposicao_ok=1, recomposicao_medicao_id=? WHERE alvo_tipo=? AND alvo_id=?",
                     (med["id"], a["alvo_tipo"], a["id"]))
        _lancar(conn, med["id"], 4, f"RECOMPOSIÇÃO {tipo}", bm, bm["unidade"] if bm else "A DEFINIR", quantidade,
                a["alvo_tipo"], a["id"], motivo=None if bm else "item de recomposição A CONFIRMAR")


# ------------------------------------------------------------------ esteira de cadastro
def avancar_cadastro(conn, trecho_ref, destino, dados=None, data=None):
    dados = dados or {}
    t = alvo(conn, "TRECHO", trecho_ref, operacao=True)
    c = _one(conn, "SELECT * FROM cadastro WHERE trecho_id=?", t["id"])
    if not c:
        raise RegraViolada("Trecho não está na esteira (exige OK Fiscalização).")
    R.validar_transicao(c["etapa"], destino, dados)
    campos = {"etapa": destino, "atualizado_em": _agora()}
    if destino == "2_ENVIADO":
        if c["etapa"] == "5A_NEGADO":
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
            med = medicao_para(conn, data or date.today().isoformat())
            _lancar(conn, med["id"], 3, "CADASTRO", _bm_item(conn, mapa_servicos()["cadastro"]["item"]), "M",
                    t["extensao_m"], "TRECHO", t["id"], obs=f"GDOC {c['protocolo_gdoc']} · ESET {dados['memorando_eset']}")
            campos["medicao_id"] = med["id"]
        sets = ", ".join(f"{k}=?" for k in campos)
        conn.execute(f"UPDATE cadastro SET {sets} WHERE trecho_id=?", (*campos.values(), t["id"]))
        conn.execute("INSERT INTO cadastro_historico(trecho_id,de_etapa,para_etapa,dados,em) VALUES (?,?,?,?,?)",
                     (t["id"], c["etapa"], destino, json.dumps(dados, ensure_ascii=False), _agora()))


def esteira(conn):
    out = _rows(conn.execute(
        """SELECT c.*, t.ponto, t.extensao_m, t.frente_id FROM cadastro c JOIN trechos t ON t.id=c.trecho_id
           ORDER BY c.etapa, t.ponto"""))
    for c in out:
        c["rotulo"] = R.rotulo_etapa(c["etapa"], c["revisao"])
        c["proximas"] = list(R.TRANSICOES.get(c["etapa"], {}).keys())
    return out


# ------------------------------------------------------------------ medição (TESTE)
def medicao_oficial_liberada(conn):
    return str(parametro(conn, "medicao_oficial_liberada", "NAO")).upper() == "SIM"


def criar_medicao(conn, numero, periodo_ini, periodo_fim, tipo="TESTE"):
    if tipo not in ("TESTE", "OFICIAL"):
        raise RegraViolada("Tipo de medição inválido.")
    if tipo == "OFICIAL" and not medicao_oficial_liberada(conn):
        raise RegraViolada("Medição OFICIAL bloqueada: regras financeiras, controle de acesso e exportação no modelo "
                           "oficial ainda não foram validados. Use medição de TESTE.")
    if periodo_fim < periodo_ini:
        raise RegraViolada("Período inválido.")
    sob = _one(conn, "SELECT numero FROM medicoes WHERE tipo=? AND NOT (periodo_fim < ? OR periodo_ini > ?)",
               tipo, periodo_ini, periodo_fim)
    if sob:
        raise RegraViolada(f"Período sobrepõe a {sob['numero']}ª medição ({tipo}).")
    return conn.execute("INSERT INTO medicoes(numero,tipo,periodo_ini,periodo_fim) VALUES (?,?,?,?)",
                        (numero, tipo, periodo_ini, periodo_fim)).lastrowid


def medicao_para(conn, data):
    tipos = ("OFICIAL", "TESTE") if medicao_oficial_liberada(conn) else ("TESTE",)
    for t in tipos:
        m = _one(conn, "SELECT * FROM medicoes WHERE tipo=? AND ? BETWEEN periodo_ini AND periodo_fim", t, data)
        if m:
            if m["status"] != "ABERTA":
                raise RegraViolada(f"A {m['numero']}ª medição ({t}) cobrindo {data} já está fechada.")
            return m
    raise RegraViolada(f"Nenhuma medição de teste cobrindo {data}. Abra a medição na aba 5.")


def fechar_medicao(conn, medicao_id):
    """Fecha e CONGELA a medição. O preço, a classificação e o item de cada lançamento, os fatores
    (BDI, K) e o resumo ficam gravados. Uma revisão posterior do BM não recalcula o valor dela."""
    med = _one(conn, "SELECT * FROM medicoes WHERE id=?", medicao_id)
    if not med:
        raise RegraViolada("Medição não encontrada.")
    if med["status"] != "ABERTA":
        raise RegraViolada(f"A {med['numero']}ª medição ({med['tipo']}) já está fechada.")
    with transacao(conn):
        congelar_medicao(conn, medicao_id, "fechamento")
        conn.execute("UPDATE medicoes SET status='FECHADA' WHERE id=?", (medicao_id,))


def congelar_medicao(conn, medicao_id, origem):
    """Grava os valores de cálculo vigentes neste momento. Uso: fechamento, ou migração de medição já fechada."""
    r = _resumo_calculado(conn, medicao_id)
    for g in r["gavetas"].values():
        for l in g["lancamentos"]:
            if l["bm_item_id"] is not None:
                conn.execute("UPDATE medicao_lancamentos SET preco_congelado=?, classificacao_congelada=?, item_congelado=? "
                             "WHERE id=?", (l["preco_unitario"], l["classificacao"], l["item"], l["id"]))
    bdi_m, bdi_s, k = _fatores(conn)
    r["congelamento"] = {"em": _agora(), "origem": origem,
                         "fatores": {"bdi_material": bdi_m, "bdi_servico": bdi_s, "coef_k": k},
                         "bm_fonte": _one(conn, "SELECT nome, sha256 FROM fontes_arquivo WHERE chave='bm' ORDER BY id DESC LIMIT 1")}
    r["medicao"].pop("resumo_congelado", None)
    conn.execute("UPDATE medicoes SET congelada_em=?, resumo_congelado=? WHERE id=?",
                 (r["congelamento"]["em"], json.dumps(r, ensure_ascii=False, default=str), medicao_id))


def indices_reajuste(conn):
    return _rows(conn.execute("SELECT * FROM reajuste_indices ORDER BY vigencia_ini"))


GAVETAS = {
    1: "Serviços de Trechos e Nós (OK interno)",
    2: "Materiais — regime pendente (matriz de regimes)",
    3: "Cadastros Aprovados GDOC",
    4: "Calçadas / Asfalto",
}


def _fatores(conn):
    return (float(parametro(conn, "bdi_material", 0)), float(parametro(conn, "bdi_servico", 0)),
            float(parametro(conn, "coef_k", 0)))


def _totalizar(conn, linhas):
    """linhas: [(item, classificação, preço sem BDI, quantidade)] → totalização na ordem do BM (regras.totalizar_bm).

    Quantidades do mesmo item (e mesmo preço) são somadas antes do ROUND por item, como na coluna W do BM."""
    por_item = {}
    for it, cl, pr, q in linhas:
        por_item.setdefault((it, cl, pr or 0), [cl, 0.0, pr or 0])[1] += q
    return R.totalizar_bm([tuple(v) for v in por_item.values()], *_fatores(conn))


HIPOTESES_FIXAS = [
    "Teto por subgrupo: o total limitado desconta o excedente sobre o P0 do subgrupo — controle interno proposto "
    "(matriz, item 15), ainda não validado.",
    "Reajuste: simulado sobre o total limitado, sem as frações elegíveis de material e serviço (REV03 × REV04, matriz "
    "item 18) e sem confirmação do pedido da contratada (contrato 6.2).",
]


def _resumo_calculado(conn, medicao_id, usar_congelado=True):
    med = _one(conn, "SELECT * FROM medicoes WHERE id=?", medicao_id)
    if not med:
        raise RegraViolada("Medição não encontrada.")
    med.pop("resumo_congelado", None)
    lanc = _rows(conn.execute(
        """SELECT l.*, b.item, b.subgrupo, b.planilha, b.descricao AS bm_descricao, b.classificacao, b.preco_unitario
           FROM medicao_lancamentos l LEFT JOIN bm_itens b ON b.id=l.bm_item_id
           WHERE l.medicao_id=? ORDER BY l.gaveta, l.id""", (medicao_id,)))
    for l in lanc:
        l["alvo_nome"] = nome_alvo(conn, l["alvo_tipo"], l["alvo_id"]) if l["alvo_id"] else None
        if usar_congelado and l["preco_congelado"] is not None:
            l["preco_unitario"], l["classificacao"], l["item"] = (l["preco_congelado"], l["classificacao_congelada"],
                                                                  l["item_congelado"])
    linha = lambda l: (l["bm_item_id"], l["classificacao"], l["preco_unitario"], l["quantidade"])
    propostos = [l for l in lanc if l["status"] == "PROPOSTO"]
    gavetas = {}
    for g, n in GAVETAS.items():
        lg = [l for l in lanc if l["gaveta"] == g]
        tot = _totalizar(conn, [linha(l) for l in lg if l["status"] == "PROPOSTO"])
        gavetas[g] = {"nome": n, "valor": tot["total"], "lancamentos": lg,
                      "pendentes": sum(1 for l in lg if l["status"] == "PENDENTE")}
    total = _totalizar(conn, [linha(l) for l in propostos])
    # teto por subgrupo do BM Vertical: valor P0 do subgrupo (mesma ordem de cálculo) — controle proposto
    tetos = []
    for sg in sorted({l["subgrupo"] for l in propostos if l["planilha"] == "VERTICAL"}):
        itens_sg = _rows(conn.execute("SELECT * FROM bm_itens WHERE planilha='VERTICAL' AND vigente=1 AND subgrupo=?", (sg,)))
        teto = _totalizar(conn, [(b["id"], b["classificacao"], b["preco_unitario"], b["quantidade"] or 0)
                                 for b in itens_sg])["total"]
        ant = conn.execute(
            """SELECT l.bm_item_id, COALESCE(l.classificacao_congelada, b.classificacao),
                      COALESCE(l.preco_congelado, b.preco_unitario), l.quantidade
               FROM medicao_lancamentos l JOIN bm_itens b ON b.id=l.bm_item_id JOIN medicoes m ON m.id=l.medicao_id
               WHERE l.status='PROPOSTO' AND b.subgrupo=? AND m.tipo=? AND m.numero < ?""",
            (sg, med["tipo"], med["numero"])).fetchall()
        anterior = _totalizar(conn, [tuple(r) for r in ant])["total"]
        atual = _totalizar(conn, [linha(l) for l in propostos if l["subgrupo"] == sg])["total"]
        aceito, exced = R.aplicar_teto(atual, anterior, teto)
        tetos.append({"subgrupo": sg, "nome": itens_sg[0]["subgrupo_nome"] if itens_sg else "", "teto": teto,
                      "anterior": anterior, "atual": atual, "aceito": aceito, "excedente": exced})
    excedente = round(sum(t["excedente"] for t in tetos), 2)
    pi = round(total["total"] - excedente, 2)
    try:
        indice, aviso = R.indice_reajuste(med["periodo_ini"], med["periodo_fim"], indices_reajuste(conn)), None
    except RegraViolada as e:
        indice, aviso = None, str(e)
    hipoteses = list(HIPOTESES_FIXAS)
    if any("estimativa" in (l["observacao"] or "") for l in lanc):
        hipoteses.append("Escavação em dois itens (5.4.11/5.4.13 e 5.4.15/5.4.14): rateio pela proporção contratual — "
                         "estimativa sem critério aprovado (matriz, item 11).")
    if any(l["servico"] == mapa_servicos()["solda"]["servico"] for l in lanc):
        hipoteses.append("Soldas: ⌈L/6⌉ por barra de 6 m — estimativa sem validação.")
    return {
        "medicao": med, "teste": med["tipo"] == "TESTE", "simulacao": True, "hipoteses": hipoteses,
        "gavetas": gavetas, "tetos": tetos, "totalizacao": total,
        "valor_pi": total["total"], "excedente_teto": excedente, "valor_pi_limitado": pi,
        "indice_reajuste": indice, "aviso_reajuste": aviso,
        "valor_reajuste": round(pi * indice, 2) if indice is not None else None,
        "valor_total": round(pi * (1 + indice), 2) if indice is not None else None,
        "pendentes": sum(1 for l in lanc if l["status"] == "PENDENTE"),
    }


def resumo_medicao(conn, medicao_id):
    """Medição aberta: calculada com o cadastro atual. Medição fechada: valores congelados no fechamento.
    Se o cadastro atual daria outro valor, isso aparece como alerta, sem alterar a medição."""
    med = _one(conn, "SELECT * FROM medicoes WHERE id=?", medicao_id)
    if not med:
        raise RegraViolada("Medição não encontrada.")
    if med["status"] == "FECHADA" and med["resumo_congelado"]:
        r = json.loads(med["resumo_congelado"])
        r["gavetas"] = {int(g): v for g, v in r["gavetas"].items()}
        med.pop("resumo_congelado")
        r["medicao"] = med
        r["congelada"] = True
        recalc = _resumo_calculado(conn, medicao_id, usar_congelado=False)
        if abs((recalc["valor_pi"] or 0) - (r["valor_pi"] or 0)) > 0.004:
            r["alerta_recalculo"] = (f"Com o cadastro atual do BM o subtotal P0 seria {recalc['valor_pi']:.2f}. "
                                     f"Mantido o valor congelado no fechamento ({r['valor_pi']:.2f}).")
        return r
    r = _resumo_calculado(conn, medicao_id)
    r["congelada"] = False
    return r


# ------------------------------------------------------------------ detalhe e mapa
def avisos_e_decisoes(conn, atividade_id):
    """Avisos de origem (AA/AB/AW) da atividade, agrupados sem repetição.

    Uma decisão só fica ligada ao aviso por vínculo explícito (decisao_vinculos: nº do elemento +
    hash do texto). O padrão de texto da decisão (padrao_aviso) apenas SUGERE avisos parecidos para
    revisão: a sugestão não aplica a decisão nem encerra o aviso.
    """
    a = alvo(conn, "ATIVIDADE", atividade_id)
    av = _rows(conn.execute(
        """SELECT tipo, prioridade, texto, texto_hash, COUNT(*) linhas FROM avisos_origem x
           JOIN itens_projeto i ON i.id=x.item_id
           WHERE i.atividade_id=? AND x.vigente=1 GROUP BY tipo, prioridade, texto, texto_hash ORDER BY tipo, texto""",
        (a["id"],)))
    decs = _rows(conn.execute("SELECT * FROM decisoes ORDER BY id"))
    vinc = {(r[0], r[1]) for r in conn.execute(
        "SELECT decisao_id, texto_hash FROM decisao_vinculos WHERE elemento_numero=?", (a["numero"],))}
    escopo = {r[0] for r in conn.execute(
        "SELECT decisao_id FROM decisao_objetos WHERE objeto_tipo='ELEMENTO' AND objeto_ref=?", (a["numero"],))}
    for x in av:
        x["decisoes"] = [d["id"] for d in decs if (d["id"], x["texto_hash"]) in vinc]
        x["sugestoes"] = [d["id"] for d in decs if d["id"] not in x["decisoes"] and d["padrao_aviso"]
                          and re.search(d["padrao_aviso"], x["texto"], re.I)]
    ligadas = {i for x in av for i in x["decisoes"]} | escopo
    sugeridas = {i for x in av for i in x["sugestoes"]} - ligadas
    return {"avisos": av,
            "decisoes": [dict(d, vinculo="ESCOPO_EXPLICITO") for d in decs if d["id"] in ligadas],
            "decisoes_sugeridas": [dict(d, vinculo="SUGESTAO_POR_TEXTO — revisar; não aplicada") for d in decs
                                   if d["id"] in sugeridas]}


def detalhe(conn, alvo_tipo, ref):
    a = alvo(conn, alvo_tipo, ref)
    tipo, aid = a["alvo_tipo"], a["id"]
    d = {"tipo": tipo, **a, "execucao": execucao(conn, tipo, aid),
         "fotos": _rows(conn.execute("SELECT * FROM fotos WHERE alvo_tipo=? AND alvo_id=? ORDER BY id", (tipo, aid))),
         "fotos_faltando": fotos_faltando(conn, tipo, aid),
         "proveniencia": _rows(conn.execute(
             """SELECT p.aba, p.linha, f.nome, f.revisao, substr(f.sha256,1,16) sha FROM proveniencia p
                JOIN fontes_arquivo f ON f.id=p.fonte_id WHERE p.entidade=? AND p.entidade_id=?""",
             ("trecho" if tipo == "TRECHO" else "atividade", aid)))}
    if tipo == "TRECHO":
        d["quantidades"] = json.loads(a["quantidades"])
        d["cadastro"] = _one(conn, "SELECT * FROM cadastro WHERE trecho_id=?", aid)
        d["perfil_bloqueado"] = R.bloqueio_perfil(a)       # mesma regra do cálculo (MND não tem vala)
        d["mnd"] = a.get("metodologia") == "MND"
    else:
        d.update(totais_atividade(conn, aid))
        d["itens"] = itens_atividade(conn, aid)
        d["trechos_ligados"] = trechos_da_atividade(conn, aid)
        d["outras_atividades"] = _rows(conn.execute(
            "SELECT id, nomenclatura, frente_id FROM atividades WHERE elemento_id=? AND id<>? AND vigente=1",
            (a["elemento_id"], aid)))
        d.update(avisos_e_decisoes(conn, aid))
    return d


def estado_mapa(conn, medicao_atual_id=None, data=None):
    """Mapa Iluminado: estado CORRENTE por nome visível (só objetos vigentes), pins e bandeja sem posição.

    O histórico de objetos retirados não é apagado. Ele aparece em `retirados_com_historico` para
    tratamento explícito (check-in aberto, execução sem OK) e não entra nas cores do mapa.
    """
    vig = {("TRECHO", r[0]): r[1] for r in conn.execute("SELECT id, ponto FROM trechos WHERE vigente=1")}
    vig.update({("ATIVIDADE", r[0]): r[1] for r in conn.execute(
        "SELECT a.id, a.nomenclatura FROM atividades a JOIN elementos e ON e.id=a.elemento_id "
        "WHERE a.vigente=1 AND e.vigente=1")})
    ex = {(r["alvo_tipo"], r["alvo_id"]): dict(r) for r in conn.execute("SELECT * FROM execucao")}
    fotos = {}
    for r in conn.execute("SELECT alvo_tipo, alvo_id, categoria FROM fotos"):
        fotos.setdefault((r[0], r[1]), []).append(r[2])
    status, retirados = {}, []
    for (tipo, aid), e in ex.items():
        if (tipo, aid) not in vig:
            retirados.append({"alvo_tipo": tipo, "alvo_id": aid, "nome": nome_alvo(conn, tipo, aid),
                              "situacao": "execução registrada em objeto retirado da revisão vigente"})
            continue
        her = _sinalizacao_herdada(conn, tipo, aid) if tipo == "ATIVIDADE" else False
        falt = R.fotos_pendentes(tipo, fotos.get((tipo, aid), []), her)
        status[vig[(tipo, aid)]] = R.status_mapa(e, falt, medicao_atual_id)
    pins = []
    for c in checkins_abertos(conn, data or date.today().isoformat()):
        if not c["alvo_id"]:
            continue
        if c["alvo_retirado"]:
            retirados.append({"alvo_tipo": c["alvo_tipo"], "alvo_id": c["alvo_id"], "nome": c["alvo_nome"],
                              "situacao": f"check-in {c['id']} aberto ({c['equipe_id']}) em objeto retirado — encerrar no check-out"})
            continue
        pins.append({"equipe": c["equipe_id"], "alvo_tipo": c["alvo_tipo"], "alvo_id": c["alvo_nome"], "checkin": c["id"],
                     "data": c["data"], "origem": "programação do check-in"})
    return {
        "status": status,
        "pins": pins,
        "retirados_com_historico": retirados,
        "sem_posicao": _rows(conn.execute(
            """SELECT e.id, e.numero, e.status_posicao, GROUP_CONCAT(a.nomenclatura, ' | ') nomenclaturas
               FROM elementos e JOIN atividades a ON a.elemento_id=e.id AND a.vigente=1
               WHERE e.vigente=1 AND (e.lat IS NULL OR e.lon IS NULL) GROUP BY e.id ORDER BY e.numero""")),
    }
