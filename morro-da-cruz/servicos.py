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
import hashlib
import json
import struct
import os
import re
import sqlite3
from datetime import date, datetime

import caminhos
import imagens
import regras as R
from regras import RegraViolada

BASE = caminhos.PASTA
DB_PADRAO = os.path.join(BASE, "dados", "morro_da_cruz.db")
DIR_FOTOS = os.path.join(BASE, "dados", "fotos")
VERSAO_ESQUEMA = 13
TOL = 1e-6
ALIAS_ALVO = {"CONJUNTO": "ATIVIDADE", "ELEMENTO": "ATIVIDADE"}


class EsquemaAntigo(RuntimeError):
    """Banco em esquema anterior: precisa de migração (importar.py) antes de ser usado."""


def exigir_data_ocorrida(data, o_que):
    """Execução, clima, estoque e OK registram o que já aconteceu: data posterior a hoje é recusada (a programação,
    a reserva e o período da medição podem ser futuros)."""
    if data and str(data)[:10] > date.today().isoformat():
        raise RegraViolada(f"{o_que} com data futura ({data}): só se registra o que já aconteceu.")


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
    with open(os.path.join(caminhos.RECURSOS, "schema.sql"), encoding="utf-8") as f:
        for cmd in comandos_sql(f.read()):
            conn.execute(cmd)
    if "sha256" in {r[1] for r in conn.execute("PRAGMA table_info(fotos)")}:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_fotos_sha ON fotos(sha256) WHERE sha256 IS NOT NULL")
    if "chave" in {r[1] for r in conn.execute("PRAGMA table_info(medicao_lancamentos)")}:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_lanc_chave ON medicao_lancamentos(chave) WHERE chave IS NOT NULL")
    conn.execute("INSERT OR IGNORE INTO schema_versao VALUES (?,?,?)",
                 (VERSAO_ESQUEMA, _agora(), "medição: parcela única, conferência interna e elegibilidade por período"))


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
    """Tudo ou nada. Dentro de outra transação (o servidor envolve cada requisição numa só, com o registro de
    reenvio e a auditoria), vira SAVEPOINT: a falha desfaz só esta parte e a externa decide o resto."""

    def __init__(self, conn):
        self.conn, self.ponto = conn, None

    def __enter__(self):
        if self.conn.in_transaction:
            self.ponto = f"sp_{id(self)}"
            self.conn.execute(f"SAVEPOINT {self.ponto}")
        else:
            self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, tipo, *_):
        if self.ponto:
            if tipo:
                self.conn.execute(f"ROLLBACK TO {self.ponto}")
            self.conn.execute(f"RELEASE {self.ponto}")
        else:
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


# Só foto com imagem validada conta como evidência (INVALIDA / ARQUIVO_AUSENTE / não validada não contam)
FOTO_VALIDA = "validacao IS NOT NULL AND validacao NOT IN ('INVALIDA','ARQUIVO_AUSENTE')"


def _sinalizacao_herdada(conn, alvo_tipo, alvo_id):
    if alvo_tipo == "TRECHO":
        return False
    ids = [t["id"] for t in trechos_da_atividade(conn, alvo_id)]
    if not ids:
        return False
    ph = ",".join("?" * len(ids))
    return conn.execute(f"SELECT 1 FROM fotos WHERE alvo_tipo='TRECHO' AND categoria='SINALIZACAO' AND {FOTO_VALIDA} "
                        f"AND alvo_id IN ({ph}) LIMIT 1", ids).fetchone() is not None


def fotos_faltando(conn, alvo_tipo, ref):
    a = alvo(conn, alvo_tipo, ref)
    cats = [r[0] for r in conn.execute(f"SELECT categoria FROM fotos WHERE alvo_tipo=? AND alvo_id=? AND {FOTO_VALIDA}",
                                       (a["alvo_tipo"], a["id"]))]
    return R.fotos_pendentes(a["alvo_tipo"], cats, _sinalizacao_herdada(conn, a["alvo_tipo"], a["id"]))


# ------------------------------------------------------------------ almoxarifado (etapa 3)
# Saldo físico do almoxarifado = entradas − saídas físicas, sem movimentos estornados.
# BAIXA_TEORICA (MVP antigo) não é saída física: estimativa geométrica não baixa estoque.
# Disponível = físico − reservas ATIVAS. Custódia é da EQUIPE (o que fica com ela passa para o dia seguinte).
ENTRA_ALMOX = ("ROMANEIO_CAESB", "ENTRADA_NF", "ENTRADA_CONSUMO", "SOBRA", "AJUSTE_INVENTARIO_ENTRADA")
SAI_ALMOX = ("EMPRESTIMO_OUTRA_OBRA", "CUSTODIA", "DEVOLUCAO_FORNECEDOR", "AJUSTE_INVENTARIO_SAIDA")
# custódia da equipe: retirada e transferência recebida entram; aplicado, sobra, perda e transferência enviada saem
CUSTODIA_SQL = """COALESCE(SUM(CASE WHEN tipo IN ('CUSTODIA','TRANSF_ENTRADA') THEN quantidade
                                   WHEN tipo IN ('APLICADO','SOBRA','PERDA','TRANSF_SAIDA') THEN -quantidade END),0)"""
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
        f"""SELECT {CUSTODIA_SQL}
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
            f"""SELECT {CUSTODIA_SQL}
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
               WHERE ap.alvo_tipo='TRECHO' AND ap.anulado_por IS NULL AND t.de_mm=?""", (de,)).fetchone()[0]
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
    exigir_data_ocorrida(data, "Movimento de material")
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
            """INSERT INTO notas_fiscais(numero,chave_nfe,fornecedor,data_entrega,arquivo,faturamento_etapas,status,origem)
               VALUES (?,?,?,?,?,?, 'QUARENTENA', 'DIRETA')""",
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
    if nf["status"] != "QUARENTENA":
        raise RegraViolada("Esta nota segue o fluxo de conferência, entrega e inspeção por item (compras).")
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
    exigir_data_ocorrida(data, "Check-in")
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
        if ref:                                    # o planejado daquele dia e alvo passa a realizado (módulo D)
            conn.execute("""UPDATE programacoes SET status='REALIZADA', checkin_id=?, encerrada_em=?
                            WHERE equipe_id=? AND data=? AND alvo_tipo=? AND alvo_id=? AND status='PLANEJADA'""",
                         (cid, _agora(), equipe_id, data, tipo, ref))
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
        transf = {r[0]: r[1] for r in conn.execute(
            f"""SELECT material_id, SUM(CASE WHEN tipo='TRANSF_ENTRADA' THEN quantidade ELSE -quantidade END) FROM movimentos
                WHERE checkin_id=? AND tipo IN ('TRANSF_ENTRADA','TRANSF_SAIDA') AND {VALIDO} GROUP BY material_id""", (c["id"],))}
        c["materiais"] = [{"material_id": m, "quantidade": custodia_equipe(conn, c["equipe_id"], m, c["id"]),
                           "retirado_hoje": hoje.get(m, 0.0), "transferido": transf.get(m, 0.0),
                           "trazido": round(custodia_equipe(conn, c["equipe_id"], m, c["id"]) - hoje.get(m, 0.0) - transf.get(m, 0.0), 6)}
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
    exigir_data_ocorrida(data, "Clima")
    if condicao not in R.CONDICOES_CLIMA:
        raise RegraViolada("Condição de clima inválida.")
    conn.execute("INSERT OR REPLACE INTO clima VALUES (?,?,?,?)", (data, equipe_id, turno, condicao))


# ------------------------------------------------------------------ intervalos de execução (etapa 4)
# Intervalo e apontamento nunca são apagados: a retificação os ANULA (anulado_por) e grava os substitutos.
EFETIVO = "anulado_por IS NULL"
# Avanço anterior aos intervalos (só em metros, sem posição), ainda não conciliado nem retificado
_SQL_LEGADO = """FROM apontamentos ap
           WHERE ap.alvo_tipo='TRECHO' AND ap.anulado_por IS NULL
             AND NOT EXISTS (SELECT 1 FROM intervalos_execucao i WHERE i.apontamento_id=ap.id)
             AND ap.id NOT IN (SELECT apontamento_id FROM conciliacao_legado_apontamentos)
             AND (COALESCE(ap.metros_executados,0) > 0 OR COALESCE(ap.metros_reaterrados,0) > 0)"""


def intervalos(conn, trecho_id, etapa=None, ate_data=None, anulados=False):
    """Intervalos EFETIVOS do trecho; com anulados=True, só os anulados por retificação (histórico)."""
    sql = "SELECT * FROM intervalos_execucao WHERE trecho_id=? AND " + ("anulado_por IS NOT NULL" if anulados else EFETIVO)
    args = [trecho_id]
    if etapa:
        sql, args = sql + " AND etapa=?", args + [etapa]
    if ate_data:
        sql, args = sql + " AND data<=?", args + [ate_data]
    return _rows(conn.execute(sql + " ORDER BY etapa, ini_m", args))


def _cobertura(conn, trecho_id, etapa, extra=(), ate_data=None):
    return R.unir_intervalos([(i["ini_m"], i["fim_m"]) for i in intervalos(conn, trecho_id, etapa, ate_data)] + list(extra))


def _faixas(lst):
    return ", ".join(f"{a:g}–{b:g} m" for a, b in lst)


def _ref_intervalo(i):
    if i.get("conciliacao_id"):
        return f"conciliação #{i['conciliacao_id']}"
    if i.get("apontamento_id"):
        return f"apontamento #{i['apontamento_id']}"
    return f"intervalo #{i.get('id')}"


def _incoerencias(lista):
    """{chave: faixas sem suporte}: reaterro/cadastro de campo sem assentamento (da mesma lista) com data ≤ a dele.
    No mesmo dia a ordem não é conhecida: o assentamento do próprio dia conta."""
    out = {}
    for i in lista:
        if i["etapa"] in ("REATERRADO", "CADASTRO_CAMPO"):
            sup = [(x["ini_m"], x["fim_m"]) for x in lista if x["etapa"] == "ASSENTADO" and x["data"] <= i["data"]]
            falta = R.fora_da_cobertura((i["ini_m"], i["fim_m"]), sup)
            if falta:
                out[i["chave"]] = falta
    return out


def _sem_cadastro(lista):
    """Chaves dos reaterros sem cadastro de campo (da mesma lista) com data ≤ a do reaterro (alerta, não bloqueio)."""
    out = set()
    for r in lista:
        if r["etapa"] == "REATERRADO":
            cad = [(x["ini_m"], x["fim_m"]) for x in lista if x["etapa"] == "CADASTRO_CAMPO" and x["data"] <= r["data"]]
            if R.fora_da_cobertura((r["ini_m"], r["fim_m"]), cad):
                out.add(r["chave"])
    return out


def legado_pendente(conn, trecho):
    """Avanço registrado antes dos intervalos (apontamentos só em metros, sem posição) e ainda não conciliado.
    É preservado como está: o resumo de execução não é recalculado enquanto ele existir."""
    mnd = trecho.get("metodologia") == "MND"
    aps = _rows(conn.execute(
        f"""SELECT ap.id, ap.data, COALESCE(ap.metros_executados,0) AS ass, COALESCE(ap.metros_reaterrados,0) AS rea
           {_SQL_LEGADO} AND ap.alvo_id=? ORDER BY ap.data, ap.id""", (trecho["id"],)))
    if not aps:
        return None
    ass = round(sum(a["ass"] for a in aps), 6)
    rea = 0.0 if mnd else round(sum(a["rea"] for a in aps), 6)
    return {"ASSENTADO": ass, "REATERRADO": rea, "apontamentos": aps, "datas": _datas_legado(aps, mnd)}


def _datas_legado(aps, mnd):
    return {"ASSENTADO": sorted({a["data"] for a in aps if a["ass"] > 0}),
            "REATERRADO": sorted({a["data"] for a in aps if a["rea"] > 0 and not mnd})}


def _exigir_sem_legado(conn, t, acao):
    pend = legado_pendente(conn, t)
    if pend:
        raise RegraViolada(
            f"{t['ponto']} tem avanço anterior sem posição ({pend['ASSENTADO']:g} m assentados, {pend['REATERRADO']:g} m "
            f"reaterrados; apontamentos de {', '.join(sorted({a['data'] for a in pend['apontamentos']}))}). Concilie a "
            f"posição desses metros (conciliação do legado) antes de {acao}.")


def _validar_intervalos(conn, t, novos, excluir=()):
    """Valida o CONJUNTO resultante do trecho: efetivos − `excluir` (anulados por uma retificação) + `novos`.

    Recusa sobreposição na mesma etapa (com o registrado ou entre os novos), intervalo fora do trecho e reaterro/
    cadastro de campo sem assentamento JÁ FEITO NA DATA do serviço — inclusive um reaterro/cadastro já registrado que
    perderia o suporte por causa da correção. Incoerência anterior (gravada antes da correção F03) que não é agravada
    não bloqueia: aparece como alerta para ser corrigida por retificação. MND não tem vala."""
    ext, mnd = float(t["extensao_m"]), t.get("metodologia") == "MND"
    atuais = [dict(i, chave=i["id"]) for i in intervalos(conn, t["id"])]
    restantes = [i for i in atuais if i["id"] not in set(excluir)]
    por_etapa = {e: [] for e in R.ETAPAS_INTERVALO}
    hip = list(restantes)
    for k, n in enumerate(novos):
        e, a, b = n.get("etapa"), float(n["ini_m"]), float(n["fim_m"])
        if e not in R.ETAPAS_INTERVALO:
            raise RegraViolada(f"Etapa inválida: {e}.")
        if mnd and e == "REATERRADO":
            raise RegraViolada("Trecho MND não tem vala: registre só ASSENTADO e CADASTRO_CAMPO.")
        if not (0 <= a < b <= ext + R.TOL_M):
            raise RegraViolada(f"{e} {a:g}–{b:g} m fora do trecho (0–{ext:g} m) ou com início ≥ fim.")
        existentes = [(i["ini_m"], i["fim_m"]) for i in restantes if i["etapa"] == e]
        sob = R.sobreposicao((a, b), existentes + por_etapa[e])
        if sob:
            raise RegraViolada(f"{e} {a:g}–{b:g} m sobrepõe intervalo já registrado ({sob[0]:g}–{sob[1]:g} m). "
                               "Intervalo repetido ou sobreposto não é aceito.")
        por_etapa[e].append((a, b))
        hip.append({"etapa": e, "ini_m": a, "fim_m": b, "data": n["data"], "chave": ("novo", k)})
    antes, depois = _incoerencias(atuais), _incoerencias(hip)
    por_id = {i["id"]: i for i in atuais}
    for chave, falta in sorted(depois.items(), key=lambda x: isinstance(x[0], int)):
        if chave in antes and R.comprimento(falta) <= R.comprimento(antes[chave]) + R.TOL_M:
            continue
        if not isinstance(chave, int):
            n = novos[chave[1]]
            raise RegraViolada(f"{n['etapa']} {float(n['ini_m']):g}–{float(n['fim_m']):g} m em {n['data']} inclui trecho "
                               f"sem assentamento registrado até essa data: {_faixas(falta)}.")
        i = por_id[chave]
        raise RegraViolada(f"A correção deixaria {i['etapa']} {i['ini_m']:g}–{i['fim_m']:g} m de {i['data']} "
                           f"({_ref_intervalo(i)}) sem assentamento registrado até essa data: {_faixas(falta)}. "
                           "Retifique antes esse registro. Nada foi gravado.")
    return por_etapa


def _intervalos_completo(conn, t, data):
    """'100 % concluído': preenche exatamente as lacunas de assentado e, em VCA, de reaterro (origem COMPLETO)."""
    ext, mnd = float(t["extensao_m"]), t.get("metodologia") == "MND"
    novos = [{"etapa": "ASSENTADO", "ini_m": round(a, 6), "fim_m": round(b, 6), "origem": "COMPLETO", "data": data}
             for a, b in R.lacunas(_cobertura(conn, t["id"], "ASSENTADO"), ext)]
    if not mnd:
        novos += [{"etapa": "REATERRADO", "ini_m": round(a, 6), "fim_m": round(b, 6), "origem": "COMPLETO", "data": data}
                  for a, b in R.lacunas(_cobertura(conn, t["id"], "REATERRADO"), ext)]
    return novos


def _recalcular_alertas(conn, trecho_id):
    """Reaterro sem cadastro de campo registrado ATÉ a data do reaterro (cadastro posterior não conta como anterior)."""
    efetivos = [dict(i, chave=i["id"]) for i in intervalos(conn, trecho_id)]
    sem = _sem_cadastro(efetivos)
    for r in efetivos:
        if r["etapa"] == "REATERRADO" and int(r["id"] in sem) != r["sem_cadastro_campo"]:
            conn.execute("UPDATE intervalos_execucao SET sem_cadastro_campo=? WHERE id=?", (int(r["id"] in sem), r["id"]))


def _atualizar_execucao_trecho(conn, t, exato=False):
    """Resumo de execução a partir dos intervalos efetivos. Só é chamado sem legado pendente (ver _exigir_sem_legado).
    `exato` (retificação): 'concluído' acompanha a correção também para baixo (o trecho não tem OK interno)."""
    ext = float(t["extensao_m"])
    ass = R.comprimento(_cobertura(conn, t["id"], "ASSENTADO"))
    reat = ass if t.get("metodologia") == "MND" else R.comprimento(_cobertura(conn, t["id"], "REATERRADO"))
    concl = "excluded.concluido" if exato else "MAX(concluido, excluded.concluido)"
    conn.execute(
        f"""INSERT INTO execucao(alvo_tipo,alvo_id,metros_executados,metros_reaterrados,concluido) VALUES ('TRECHO',?,?,?,?)
           ON CONFLICT(alvo_tipo,alvo_id) DO UPDATE SET metros_executados=excluded.metros_executados,
             metros_reaterrados=excluded.metros_reaterrados, concluido={concl}""",
        (t["id"], ass, reat, 1 if reat >= ext - R.TOL_M else 0))


def _gravar_intervalos(conn, t, novos, equipe_id, apontamento_id, informado_por, conciliacao_id=None,
                       retificacao_id=None, exato=False):
    for n in novos:
        conn.execute(
            """INSERT INTO intervalos_execucao(trecho_id,etapa,ini_m,fim_m,data,equipe_id,apontamento_id,origem,
                 informado_por,conciliacao_id,registrado_em,referencia,verificado_em,verificado_por,retificacao_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t["id"], n["etapa"], float(n["ini_m"]), float(n["fim_m"]), n["data"], equipe_id, apontamento_id, n["origem"],
             informado_por, conciliacao_id, _agora(), (n.get("referencia") or "").strip() or None,
             n.get("verificado_em"), n.get("verificado_por"), retificacao_id))
    _recalcular_alertas(conn, t["id"])
    _atualizar_execucao_trecho(conn, t, exato)


def _linhas_quantidades(prev, quantidades):
    """[(serviço, unidade, previsto, confirmado)]: previsto confirmado como está, salvo o que vier em `quantidades`."""
    confirmadas = {(q["servico"], q["unidade"]): q["confirmado"] for q in (quantidades or [])}
    out = []
    for q in prev:
        out.append((q["servico"], q["unidade"], q["previsto"], float(confirmadas.pop((q["servico"], q["unidade"]), q["previsto"]))))
    out += [(s, u, None, float(c)) for (s, u), c in confirmadas.items()]
    return out


def _recusar_solda(quantidades):
    servico_solda = mapa_servicos()["solda"]["servico"]
    if any(q["servico"] == servico_solda for q in (quantidades or [])):
        raise RegraViolada("Soldas não são confirmadas no apontamento: registre-as no controle de soldas "
                           "(informadas e verificadas).")


def apontar(conn, data, equipe_id, alvo_tipo, ref, metros_executados=0, metros_reaterrados=0,
            concluido_100=False, estaca_ini=None, estaca_fim=None, quantidades=None, intervalos_novos=None,
            informado_por=None):
    """Lança avanço de campo. `quantidades=None` equivale a [✅ OK, Confirmar Previsto].

    Trecho: o avanço é registrado em INTERVALOS por etapa (`intervalos_novos`: [{etapa, ini_m, fim_m, referencia?}],
    em metros desde o início do trecho; `referencia` = registro do levantamento de campo) ou com '100 % concluído'
    (preenche as lacunas). Apontamento só em metros não é mais aceito para trecho (criaria posição presumida). Com
    avanço anterior sem posição, exige antes a conciliação. Estimativas (soldas ⌈L/6⌉) nunca viram quantidade
    confirmada: soldas têm controle próprio.
    """
    exigir_data_ocorrida(data, "Apontamento")
    turnos = {r["turno"] for r in conn.execute("SELECT turno FROM clima WHERE data=? AND equipe_id=?", (data, equipe_id))}
    if turnos != {"MANHA", "TARDE"}:
        raise RegraViolada("Clima do dia obrigatório nos dois turnos (manhã e tarde) antes do apontamento.")
    a = alvo(conn, alvo_tipo, ref, operacao=True)
    tipo, aid = a["alvo_tipo"], a["id"]
    ex = execucao(conn, tipo, aid) or {"metros_executados": 0, "metros_reaterrados": 0, "concluido": 0}
    if ex.get("ok_fiscal_em"):
        raise RegraViolada("Alvo já validado pela fiscalização — não aceita novos apontamentos.")
    _recusar_solda(quantidades)
    novos = []
    if tipo == "TRECHO":
        _exigir_sem_legado(conn, a, "registrar novos intervalos")
        if intervalos_novos:
            novos = [dict(n, origem="INFORMADO", data=data) for n in intervalos_novos]
        elif concluido_100:
            novos = _intervalos_completo(conn, a, data)
        elif metros_executados or metros_reaterrados:
            raise RegraViolada("Informe o intervalo executado (de/até, em metros desde o início do trecho): apontamento "
                               "só em metros não indica a posição.")
        if not novos:
            raise RegraViolada("Informe o intervalo executado (de/até, em metros) ou marque 100 % concluído.")
        por_etapa = _validar_intervalos(conn, a, novos)
        metros_executados = sum(b - x for x, b in por_etapa["ASSENTADO"])
        metros_reaterrados = sum(b - x for x, b in por_etapa["REATERRADO"])
        prev = previsto(conn, tipo, aid, metros_executados) if metros_executados > 0 else []
    else:
        concluido = 1 if concluido_100 else 0
        prev = previsto(conn, tipo, aid, 0) if concluido else []
    prev = [q for q in prev if not q.get("estimativa")]          # estimativa é referência, não confirmação
    with transacao(conn):
        apid = conn.execute(
            """INSERT INTO apontamentos(data,equipe_id,alvo_tipo,alvo_id,metros_executados,metros_reaterrados,estaca_ini,
                 estaca_fim,informado_por) VALUES (?,?,?,?,?,?,?,?,?)""",
            (data, equipe_id, tipo, aid, metros_executados, metros_reaterrados, estaca_ini, estaca_fim,
             informado_por)).lastrowid
        for linha in _linhas_quantidades(prev, quantidades):
            conn.execute("INSERT INTO apontamento_quantidades VALUES (?,?,?,?,?)", (apid, *linha))
        if tipo == "TRECHO":
            _gravar_intervalos(conn, a, novos, equipe_id, apid, informado_por)
        else:
            conn.execute(
                """INSERT INTO execucao(alvo_tipo,alvo_id,metros_executados,metros_reaterrados,concluido) VALUES (?,?,0,0,?)
                   ON CONFLICT(alvo_tipo,alvo_id) DO UPDATE SET concluido=MAX(concluido, excluded.concluido)""",
                (tipo, aid, concluido))
    return apid


def _posicoes_legado(novos, datas, padrao=None):
    """Intervalos de conciliação (só ASSENTADO/REATERRADO), cada um com data dentro do período do legado da etapa."""
    out = []
    for n in novos or []:
        e = n.get("etapa")
        if e not in ("ASSENTADO", "REATERRADO"):
            raise RegraViolada("A conciliação posiciona só ASSENTADO e REATERRADO do legado.")
        ds = datas[e]
        if not ds:
            raise RegraViolada(f"Não há {e} no avanço legado deste trecho.")
        d = n.get("data") or (padrao or {}).get(e) or ds[-1]
        if not (ds[0] <= d <= ds[-1]):
            raise RegraViolada(f"Data {d} fora do período do legado de {e} ({ds[0]} a {ds[-1]}).")
        out.append({"etapa": e, "ini_m": float(n["ini_m"]), "fim_m": float(n["fim_m"]), "data": d})
    return out


def _exigir_mesmos_metros(novos, ass, rea, origem):
    for e, total in (("ASSENTADO", ass), ("REATERRADO", rea)):
        soma = sum(n["fim_m"] - n["ini_m"] for n in novos if n["etapa"] == e)
        if abs(soma - total) > 0.01:
            raise RegraViolada(f"{e}: a conciliação posiciona {soma:g} m, mas {origem} tem {total:g} m. A conciliação "
                               "distribui exatamente os metros antigos (nem mais, nem menos).")


def conciliar_legado(conn, trecho_ref, intervalos_conc, motivo, responsavel):
    """Associa o avanço anterior sem posição a posições confirmadas em campo.

    A soma por etapa precisa ser IGUAL ao legado pendente (ASSENTADO = metros executados; REATERRADO = metros
    reaterrados; MND sem reaterro). Os intervalos ficam com origem LEGADO, ligados à conciliação e aos apontamentos
    antigos; NÃO geram quantidades de serviço (já registradas no apontamento original). Data de cada intervalo:
    informada (entre a primeira e a última data do legado daquela etapa) ou, por padrão, a última.
    """
    t = alvo(conn, "TRECHO", trecho_ref, operacao=True)
    pend = legado_pendente(conn, t)
    if not pend:
        raise RegraViolada(f"{t['ponto']} não tem avanço anterior pendente de conciliação.")
    if not (motivo or "").strip() or not (responsavel or "").strip():
        raise RegraViolada("A conciliação exige motivo (como a posição foi confirmada) e responsável.")
    novos = [dict(n, origem="LEGADO") for n in _posicoes_legado(intervalos_conc, pend["datas"])]
    _exigir_mesmos_metros(novos, pend["ASSENTADO"], pend["REATERRADO"], "o legado")
    _validar_intervalos(conn, t, novos)
    with transacao(conn):
        cid = conn.execute(
            "INSERT INTO conciliacoes_legado(trecho_id,metros_assentado,metros_reaterrado,motivo,responsavel,em) "
            "VALUES (?,?,?,?,?,?)", (t["id"], pend["ASSENTADO"], pend["REATERRADO"], motivo.strip(), responsavel.strip(),
                                     _agora())).lastrowid
        for ap in pend["apontamentos"]:
            conn.execute("INSERT INTO conciliacao_legado_apontamentos VALUES (?,?)", (ap["id"], cid))
        _gravar_intervalos(conn, t, novos, None, None, responsavel.strip(), conciliacao_id=cid)
    return cid


# ------------------------------------------------------------------ retificação de intervalos (v8)
def _grupo_retificacao(conn, ref_tipo, ref_id):
    """(trecho_id, intervalos efetivos do registro, registro): o que uma retificação substitui por inteiro."""
    if ref_tipo == "APONTAMENTO":
        ap = _one(conn, "SELECT * FROM apontamentos WHERE id=?", ref_id)
        if not ap or ap["alvo_tipo"] != "TRECHO":
            raise RegraViolada(f"Apontamento de trecho #{ref_id} não encontrado.")
        if ap["anulado_por"]:
            r = _one(conn, "SELECT novo_apontamento_id FROM retificacoes_intervalos WHERE id=?", ap["anulado_por"])
            raise RegraViolada(f"O apontamento #{ref_id} já foi retificado (retificação #{ap['anulado_por']})"
                               + (f": retifique o apontamento #{r['novo_apontamento_id']}, que o substituiu." if r and r["novo_apontamento_id"] else "."))
        ivs = _rows(conn.execute(f"SELECT * FROM intervalos_execucao WHERE apontamento_id=? AND {EFETIVO} ORDER BY etapa, ini_m", (ref_id,)))
        if not ivs:
            c = _one(conn, "SELECT conciliacao_id FROM conciliacao_legado_apontamentos WHERE apontamento_id=?", ref_id)
            if c:
                raise RegraViolada(f"Os metros do apontamento #{ref_id} foram posicionados na conciliação "
                                   f"#{c['conciliacao_id']}: retifique a conciliação.")
            raise RegraViolada(f"O apontamento #{ref_id} não tem intervalos (avanço anterior sem posição): use a conciliação do legado.")
        return ap["alvo_id"], ivs, ap
    if ref_tipo == "CONCILIACAO":
        c = _one(conn, "SELECT * FROM conciliacoes_legado WHERE id=?", ref_id)
        if not c:
            raise RegraViolada(f"Conciliação #{ref_id} não encontrada.")
        ivs = _rows(conn.execute(f"SELECT * FROM intervalos_execucao WHERE conciliacao_id=? AND {EFETIVO} ORDER BY etapa, ini_m", (ref_id,)))
        return c["trecho_id"], ivs, c
    raise RegraViolada("Retificação: informe um apontamento ou uma conciliação do legado.")


def _quantidades_retificadas(conn, t, ap, antes, metros, quantidades):
    """Quantidades do apontamento substituto. Sem `quantidades` informadas:
    * mesmo comprimento assentado → as mesmas quantidades (correção só de posição/data);
    * comprimento diferente → previsto do novo comprimento, a regra do [✅ OK, Confirmar Previsto] (a mesma do
      apontamento). Se o original tinha quantidade confirmada à mão (ou serviço fora do previsto), não há regra
      para recalcular: a retificação pede as quantidades corrigidas (nada é presumido)."""
    servico_solda = mapa_servicos()["solda"]["servico"]
    antes = [q for q in antes if q[0] != servico_solda]          # estimativa antiga gravada como confirmada (F02)
    prev = [q for q in previsto(conn, "TRECHO", t["id"], metros) if not q.get("estimativa")] if metros > 0 else []
    if quantidades is not None:
        return _linhas_quantidades(prev, quantidades)
    if abs(metros - float(ap["metros_executados"] or 0)) <= R.TOL_M:
        return list(antes)
    editadas = [q[0] for q in antes if q[2] is None or abs(q[3] - q[2]) > 1e-9]
    if editadas:
        raise RegraViolada("O comprimento assentado muda e o apontamento original tem quantidade confirmada à mão ("
                           + ", ".join(editadas) + "): informe as quantidades corrigidas na retificação.")
    return _linhas_quantidades(prev, None)


def retificar_intervalos(conn, ref_tipo, ref_id, novos, motivo, responsavel, data=None, quantidades=None,
                         simular=False):
    """Corrige os intervalos de UM apontamento ou de UMA conciliação do legado (posição, extensão, etapa, data).

    `novos` = conjunto completo que substitui os intervalos efetivos do registro ([] anula o registro). Aplicação
    integral ou recusa: o conjunto resultante do trecho é validado inteiro (sobreposição, limites, reaterro e cadastro
    de campo com assentamento até a data — inclusive os de outros registros que dependiam do que muda) antes de
    gravar qualquer coisa. Nada é apagado: os originais ficam anulados e ligados à retificação (motivo, responsável).

    * APONTAMENTO: o original sai das somas (anulado_por) e um apontamento substituto, ligado à retificação, recebe
      as quantidades corrigidas (ver _quantidades_retificadas): não há dupla contagem. Mesma equipe; a data pode
      ser corrigida (exige o clima daquele dia, como o apontamento).
    * CONCILIACAO: os metros por etapa continuam IGUAIS aos da conciliação (sem nova contagem) e sem quantidades.

    Verificação: um intervalo que volta idêntico (etapa, posição e data) mantém a verificação; os demais voltam a
    "informado". Recusada em trecho com OK interno e com avanço legado pendente. `simular=True` devolve o plano
    (antes × depois) sem gravar.
    """
    trecho_id, originais, reg = _grupo_retificacao(conn, ref_tipo, int(ref_id))
    t = alvo(conn, "TRECHO", trecho_id, operacao=True)
    ex = execucao(conn, "TRECHO", t["id"]) or {}
    if ex.get("ok_fiscal_em"):
        raise RegraViolada(f"{t['ponto']} já tem OK interno ({ex['ok_fiscal_em']}): a proposta da medição de teste e a "
                           "esteira de cadastro partiram desses metros. Retificação depois do OK não está implementada.")
    _exigir_sem_legado(conn, t, "retificar intervalos")
    if not simular and (not (motivo or "").strip() or not (responsavel or "").strip()):
        raise RegraViolada("A retificação exige motivo (o que estava errado e como foi confirmado) e responsável.")
    _recusar_solda(quantidades)
    mnd = t.get("metodologia") == "MND"
    if ref_tipo == "APONTAMENTO":
        d = data or reg["data"]
        if d != reg["data"]:
            turnos = {r[0] for r in conn.execute("SELECT turno FROM clima WHERE data=? AND equipe_id=?", (d, reg["equipe_id"]))}
            if turnos != {"MANHA", "TARDE"}:
                raise RegraViolada(f"Nova data {d}: registre antes o clima da equipe {reg['equipe_id']} nos dois turnos.")
        lista = [{"etapa": n.get("etapa"), "ini_m": float(n["ini_m"]), "fim_m": float(n["fim_m"]), "data": d,
                  "referencia": (n.get("referencia") or "").strip() or None} for n in novos or []]
    else:
        if quantidades:
            raise RegraViolada("A conciliação não tem quantidades: elas continuam nos apontamentos antigos.")
        aps = _rows(conn.execute(
            """SELECT ap.data, COALESCE(ap.metros_executados,0) ass, COALESCE(ap.metros_reaterrados,0) rea FROM apontamentos ap
               JOIN conciliacao_legado_apontamentos c ON c.apontamento_id=ap.id WHERE c.conciliacao_id=?""", (reg["id"],)))
        padrao = {}
        for i in originais:
            padrao.setdefault(i["etapa"], i["data"])
        lista = _posicoes_legado(novos, _datas_legado(aps, mnd), padrao)
        _exigir_mesmos_metros(lista, reg["metros_assentado"], reg["metros_reaterrado"], f"a conciliação #{reg['id']}")
        d = None
    chave = lambda i: (i["etapa"], round(float(i["ini_m"]), 6), round(float(i["fim_m"]), 6), i["data"])
    excluir = {i["id"] for i in originais}
    _validar_intervalos(conn, t, lista, excluir)
    q_antes = [tuple(r) for r in conn.execute(
        "SELECT servico, unidade, previsto, confirmado FROM apontamento_quantidades WHERE apontamento_id=? ORDER BY servico, unidade",
        (reg["id"],))] if ref_tipo == "APONTAMENTO" else []
    q_depois = None
    if ref_tipo == "APONTAMENTO":
        metros = sum(n["fim_m"] - n["ini_m"] for n in lista if n["etapa"] == "ASSENTADO")
        q_depois = _quantidades_retificadas(conn, t, reg, q_antes, metros, quantidades)
    for n in lista:
        n["origem"] = "RETIFICACAO"
        igual = next((i for i in originais if chave(i) == chave(n)), None)
        if igual:
            n.setdefault("verificado_em", igual["verificado_em"])
            n.setdefault("verificado_por", igual["verificado_por"])
            if not n.get("referencia"):
                n["referencia"] = igual.get("referencia")
    mesmos = sorted(map(chave, originais)) == sorted(map(chave, lista)) and \
        sorted((i["etapa"], i.get("referencia") or None) for i in originais) == sorted((n["etapa"], n.get("referencia") or None) for n in lista)
    if mesmos and (q_depois is None or sorted(q_depois, key=str) == sorted(q_antes, key=str)):
        raise RegraViolada("A retificação não altera nada.")
    restantes = [dict(i, chave=i["id"]) for i in intervalos(conn, t["id"]) if i["id"] not in excluir]
    hip = restantes + [dict(n, chave=("novo", k)) for k, n in enumerate(lista)]
    resumo = lambda lst: {e: R.comprimento([(i["ini_m"], i["fim_m"]) for i in lst if i["etapa"] == e]) for e in R.ETAPAS_INTERVALO
                          if not (mnd and e == "REATERRADO")}
    sem_cad = _sem_cadastro(hip)
    campos_iv = ("id", "etapa", "ini_m", "fim_m", "data", "origem", "informado_por", "verificado_por", "referencia")
    plano = {"trecho": t["ponto"], "ref_tipo": ref_tipo, "ref_id": int(ref_id),
             "anulados": [{k: i.get(k) for k in campos_iv} for i in originais],
             "novos": [{k: n.get(k) for k in campos_iv if k != "id"} for n in lista],
             "data_antes": reg.get("data"), "data_depois": d,
             "quantidades_antes": [dict(zip(("servico", "unidade", "previsto", "confirmado"), q)) for q in q_antes],
             "quantidades_depois": None if q_depois is None else
             [dict(zip(("servico", "unidade", "previsto", "confirmado"), q)) for q in q_depois],
             "resumo_antes": resumo([dict(i) for i in intervalos(conn, t["id"])]), "resumo_depois": resumo(hip),
             "alertas": [f"Reaterro {i['ini_m']:g}–{i['fim_m']:g} m ({i['data']}) ficará sem cadastro de campo até a data "
                         "(alerta, não bloqueio)." for i in hip if i["chave"] in sem_cad]}
    if simular:
        return plano
    with transacao(conn):
        rid = conn.execute(
            "INSERT INTO retificacoes_intervalos(trecho_id,ref_tipo,ref_id,motivo,responsavel,detalhe,em) VALUES (?,?,?,?,?,?,?)",
            (t["id"], ref_tipo, int(ref_id), motivo.strip(), responsavel.strip(), json.dumps(plano, ensure_ascii=False),
             _agora())).lastrowid
        conn.execute(f"UPDATE intervalos_execucao SET anulado_por=? WHERE id IN ({','.join('?' * len(excluir))})",
                     (rid, *sorted(excluir)))
        if ref_tipo == "APONTAMENTO":
            conn.execute("UPDATE apontamentos SET anulado_por=? WHERE id=?", (rid, reg["id"]))
            novo_ap = None
            if lista or q_depois:
                novo_ap = conn.execute(
                    """INSERT INTO apontamentos(data,equipe_id,alvo_tipo,alvo_id,metros_executados,metros_reaterrados,
                         estaca_ini,estaca_fim,informado_por,retificacao_id) VALUES (?,?,'TRECHO',?,?,?,?,?,?,?)""",
                    (d, reg["equipe_id"], t["id"], sum(n["fim_m"] - n["ini_m"] for n in lista if n["etapa"] == "ASSENTADO"),
                     sum(n["fim_m"] - n["ini_m"] for n in lista if n["etapa"] == "REATERRADO"), reg["estaca_ini"],
                     reg["estaca_fim"], responsavel.strip(), rid)).lastrowid
                for linha in q_depois:
                    conn.execute("INSERT INTO apontamento_quantidades VALUES (?,?,?,?,?)", (novo_ap, *linha))
                conn.execute("UPDATE retificacoes_intervalos SET novo_apontamento_id=? WHERE id=?", (novo_ap, rid))
            _gravar_intervalos(conn, t, lista, reg["equipe_id"], novo_ap, responsavel.strip(), retificacao_id=rid, exato=True)
        else:
            _gravar_intervalos(conn, t, lista, None, None, responsavel.strip(), conciliacao_id=reg["id"],
                               retificacao_id=rid, exato=True)
    plano["id"] = rid
    return plano


def verificar_intervalo(conn, intervalo_id, verificado_por):
    """Fiscal confere em campo um intervalo informado (quem informou não verifica). Conferência interna Ankara."""
    i = _one(conn, "SELECT * FROM intervalos_execucao WHERE id=?", intervalo_id)
    if not i:
        raise RegraViolada("Intervalo não encontrado.")
    if i["anulado_por"]:
        raise RegraViolada(f"Intervalo anulado pela retificação #{i['anulado_por']}: verifique o que o substituiu.")
    if i["verificado_em"]:
        raise RegraViolada("Intervalo já verificado.")
    if not (verificado_por or "").strip():
        raise RegraViolada("Informe quem verificou.")
    if i["informado_por"] and i["informado_por"].strip().lower() == verificado_por.strip().lower():
        raise RegraViolada("Quem informou o intervalo não pode verificá-lo.")
    conn.execute("UPDATE intervalos_execucao SET verificado_em=?, verificado_por=? WHERE id=?", (_agora(), verificado_por.strip(), intervalo_id))


def estado_verificacao(n_intervalos, n_verificados, legado):
    """Execução INFORMADA × VERIFICADA (conferência interna Ankara; não é aprovação da Caesb)."""
    if legado:
        return "LEGADO_SEM_POSICAO"
    if not n_intervalos:
        return None
    return "VERIFICADO" if n_verificados >= n_intervalos else "PARCIAL" if n_verificados else "INFORMADO"


def situacao_intervalos(conn, trecho_id):
    t = alvo(conn, "TRECHO", trecho_id)
    ext = float(t["extensao_m"])
    out = {"extensao_m": ext, "etapas": {}, "alertas": [], "execucao_registrada": execucao(conn, "TRECHO", t["id"])}
    out["intervalos"] = intervalos(conn, t["id"])
    for e in R.ETAPAS_INTERVALO:
        if e == "REATERRADO" and t.get("metodologia") == "MND":
            continue
        cob = _cobertura(conn, t["id"], e)
        ver = R.unir_intervalos([(i["ini_m"], i["fim_m"]) for i in out["intervalos"] if i["etapa"] == e and i["verificado_em"]])
        out["etapas"][e] = {"metros": R.comprimento(cob), "cobertura": cob, "lacunas": R.lacunas(cob, ext),
                            "verificado_m": R.comprimento(ver), "verificado": ver}
    out["legado"] = legado_pendente(conn, t)
    out["anulados"] = intervalos(conn, t["id"], anulados=True)
    out["retificacoes"] = _rows(conn.execute(
        "SELECT id, ref_tipo, ref_id, novo_apontamento_id, motivo, responsavel, em FROM retificacoes_intervalos "
        "WHERE trecho_id=? ORDER BY id", (t["id"],)))
    out["conciliacoes"] = _rows(conn.execute("SELECT * FROM conciliacoes_legado WHERE trecho_id=? ORDER BY id", (t["id"],)))
    grupos = {}
    for i in out["intervalos"]:
        k = ("CONCILIACAO", i["conciliacao_id"]) if i["conciliacao_id"] else ("APONTAMENTO", i["apontamento_id"]) if i["apontamento_id"] else None
        if k:
            g = grupos.setdefault(k, {"ref_tipo": k[0], "ref_id": k[1], "intervalos": []})
            g["intervalos"].append(i)
    out["registros"] = sorted(grupos.values(), key=lambda g: (min(i["data"] for i in g["intervalos"]), g["ref_tipo"], g["ref_id"]))
    out["verificacao"] = estado_verificacao(len(out["intervalos"]), sum(1 for i in out["intervalos"] if i["verificado_em"]),
                                            out["legado"])
    if out["legado"]:
        lg = out["legado"]
        out["alertas"].append(f"Avanço anterior SEM POSIÇÃO: {lg['ASSENTADO']:g} m assentados e {lg['REATERRADO']:g} m "
                              "reaterrados (preservados no resumo de execução). As lacunas acima não incluem esses metros. "
                              "Concilie a posição antes de novos intervalos, do 100 % e do OK interno.")
    inc = _incoerencias([dict(i, chave=i["id"]) for i in out["intervalos"]])
    if inc:
        por_id = {i["id"]: i for i in out["intervalos"]}
        out["alertas"].append("Cronologia incoerente em registro anterior (reaterro/cadastro antes do assentamento): " + "; ".join(
            f"{por_id[k]['etapa']} {por_id[k]['ini_m']:g}–{por_id[k]['fim_m']:g} m de {por_id[k]['data']} ({_ref_intervalo(por_id[k])}) "
            f"sem assentamento até a data em {_faixas(f)}" for k, f in inc.items()) + ". Corrija por retificação.")
    out["incoerencias"] = sorted(inc)
    sem_cad = [i for i in out["intervalos"] if i["sem_cadastro_campo"]]
    if sem_cad:
        out["alertas"].append("Reaterro sem cadastro de campo registrado até a data do reaterro: " +
                              ", ".join(f"{i['ini_m']:g}–{i['fim_m']:g} m ({i['data']})" for i in sem_cad))
    seq = [i for i in out["intervalos"] if i["origem"] == "SEQUENCIAL"]
    if seq:
        out["alertas"].append(f"{len(seq)} intervalo(s) com posição presumida (apontamento só em metros, versão anterior): "
                              "confirme a posição em campo e corrija por retificação.")
    pend = [i for i in out["intervalos"] if not i["verificado_em"]]
    if pend:
        out["alertas"].append(f"{len(pend)} intervalo(s) informados ainda sem verificação.")
    return out


# ------------------------------------------------------------------ liberação topográfica, escavação e ocorrências (v10)
ETAPAS_COMPLEMENTARES = ("LIBERACAO_TOPOGRAFICA", "ESCAVADO")
CATEGORIAS_OCORRENCIA = {
    "IMPEDIMENTO": ("INTERFERENCIA", "FALTA_MATERIAL", "CHUVA", "LIBERACAO", "PROJETO", "SEGURANCA", "ACESSO", "OUTRO"),
    "NAO_CONFORMIDADE": ("EXECUCAO", "MATERIAL", "SOLDA", "SEGURANCA", "CADASTRO", "DOCUMENTO", "OUTRO"),
}


def etapas_complementares(conn, trecho_id, etapa=None, anuladas=False):
    sql = "SELECT * FROM etapas_complementares WHERE trecho_id=? AND anulado_em IS " + ("NOT NULL" if anuladas else "NULL")
    args = [trecho_id]
    if etapa:
        sql, args = sql + " AND etapa=?", args + [etapa]
    return _rows(conn.execute(sql + " ORDER BY etapa, ini_m", args))


def registrar_etapa_complementar(conn, trecho_ref, etapa, ini_m, fim_m, data, registrado_por, referencia=None, obs=None):
    """Liberação topográfica (exige a referência da nota de serviço/locação) ou escavação, por intervalo do trecho.
    Não gera quantidade nem altera o resumo de execução. Repetição/sobreposição na mesma etapa é recusada."""
    exigir_data_ocorrida(data, "Liberação/escavação")
    t = alvo(conn, "TRECHO", trecho_ref, operacao=True)
    if etapa not in ETAPAS_COMPLEMENTARES:
        raise RegraViolada("Etapa inválida (LIBERACAO_TOPOGRAFICA ou ESCAVADO).")
    if etapa == "ESCAVADO" and t.get("metodologia") == "MND":
        raise RegraViolada("Trecho MND não tem vala aberta.")
    if not str(registrado_por or "").strip():
        raise RegraViolada("Informe quem registra.")
    if etapa == "LIBERACAO_TOPOGRAFICA" and not str(referencia or "").strip():
        raise RegraViolada("A liberação topográfica exige a referência da locação (nota de serviço, caderneta ou arquivo).")
    if not data:
        raise RegraViolada("Informe a data.")
    a, b, ext = float(ini_m), float(fim_m), float(t["extensao_m"])
    if not (0 <= a < b <= ext + R.TOL_M):
        raise RegraViolada(f"{etapa} {a:g}–{b:g} m fora do trecho (0–{ext:g} m) ou com início ≥ fim.")
    sob = R.sobreposicao((a, b), [(e["ini_m"], e["fim_m"]) for e in etapas_complementares(conn, t["id"], etapa)])
    if sob:
        raise RegraViolada(f"{etapa} {a:g}–{b:g} m sobrepõe registro existente ({sob[0]:g}–{sob[1]:g} m).")
    return conn.execute(
        """INSERT INTO etapas_complementares(trecho_id,etapa,ini_m,fim_m,data,registrado_por,referencia,obs,registrado_em)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (t["id"], etapa, a, b, data, registrado_por.strip(), (referencia or "").strip() or None, obs, _agora())).lastrowid


def anular_etapa_complementar(conn, registro_id, motivo, por):
    e = _one(conn, "SELECT * FROM etapas_complementares WHERE id=?", registro_id)
    if not e:
        raise RegraViolada("Registro não encontrado.")
    if e["anulado_em"]:
        raise RegraViolada("Registro já anulado.")
    if not str(motivo or "").strip():
        raise RegraViolada("A anulação exige o motivo.")
    conn.execute("UPDATE etapas_complementares SET anulado_em=?, anulado_por=?, anulado_motivo=? WHERE id=?",
                 (_agora(), por, motivo.strip(), registro_id))


def situacao_complementar(conn, t, sit):
    """Liberação e escavação do trecho, com o que foi assentado ou escavado sem liberação ATÉ a data (alerta, D-20)."""
    regs = etapas_complementares(conn, t["id"])
    cob = lambda e, ate=None: R.unir_intervalos([(r["ini_m"], r["fim_m"]) for r in regs if r["etapa"] == e and (ate is None or r["data"] <= ate)])
    out = {e: {"cobertura": cob(e), "metros": R.comprimento(cob(e)), "registros": [r for r in regs if r["etapa"] == e]}
           for e in ETAPAS_COMPLEMENTARES}
    out["anulados"] = etapas_complementares(conn, t["id"], anuladas=True)
    out["alertas"] = []
    for etapa, nome in (("ASSENTADO", "Assentado"), ("ESCAVADO", "Escavado")):
        lst = [i for i in sit["intervalos"] if i["etapa"] == etapa] if etapa == "ASSENTADO" else out["ESCAVADO"]["registros"]
        faltas = [(i, R.fora_da_cobertura((i["ini_m"], i["fim_m"]), cob("LIBERACAO_TOPOGRAFICA", i["data"]))) for i in lst]
        faltas = [(i, f) for i, f in faltas if f]
        if faltas:
            out["alertas"].append(f"{nome} sem liberação topográfica até a data (alerta): "
                                  + "; ".join(f"{_faixas(f)} ({i['data']})" for i, f in faltas))
    return out


def abrir_ocorrencia(conn, alvo_tipo, ref, tipo, categoria, descricao, data, aberta_por, equipe_id=None):
    exigir_data_ocorrida(data, "Ocorrência")
    a = alvo(conn, alvo_tipo, ref)
    if tipo not in CATEGORIAS_OCORRENCIA:
        raise RegraViolada("Tipo de ocorrência: IMPEDIMENTO ou NAO_CONFORMIDADE.")
    if categoria not in CATEGORIAS_OCORRENCIA[tipo]:
        raise RegraViolada(f"Categoria inválida para {tipo}: {', '.join(CATEGORIAS_OCORRENCIA[tipo])}.")
    if not str(descricao or "").strip() or not data or not str(aberta_por or "").strip():
        raise RegraViolada("A ocorrência exige descrição, data e quem abre.")
    return conn.execute(
        """INSERT INTO ocorrencias(alvo_tipo,alvo_id,tipo,categoria,descricao,data,equipe_id,aberta_por,aberta_em)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (a["alvo_tipo"], a["id"], tipo, categoria, descricao.strip(), data, equipe_id or None, aberta_por.strip(), _agora())).lastrowid


def resolver_ocorrencia(conn, ocorrencia_id, resolucao, por):
    o = _one(conn, "SELECT * FROM ocorrencias WHERE id=?", ocorrencia_id)
    if not o:
        raise RegraViolada("Ocorrência não encontrada.")
    if o["resolvida_em"]:
        raise RegraViolada("Ocorrência já resolvida.")
    if not str(resolucao or "").strip():
        raise RegraViolada("Descreva a resolução" + (" e a correção feita." if o["tipo"] == "NAO_CONFORMIDADE" else "."))
    conn.execute("UPDATE ocorrencias SET resolvida_em=?, resolvida_por=?, resolucao=? WHERE id=?",
                 (_agora(), por, resolucao.strip(), ocorrencia_id))


def ocorrencias(conn, alvo_tipo=None, ref=None, abertas=None):
    sql, args = "SELECT * FROM ocorrencias WHERE 1=1", []
    if ref:
        a = alvo(conn, alvo_tipo, ref)
        sql, args = sql + " AND alvo_tipo=? AND alvo_id=?", args + [a["alvo_tipo"], a["id"]]
    if abertas is not None:
        sql += " AND resolvida_em IS NULL" if abertas else " AND resolvida_em IS NOT NULL"
    return _rows(conn.execute(sql + " ORDER BY resolvida_em IS NOT NULL, data DESC, id DESC", args))


# ------------------------------------------------------------------ soldas (informadas × verificadas)
def registrar_soldas(conn, data, equipe_id, alvo_tipo, ref, tipo, quantidade, soldador, informado_por,
                     posicao_m=None, maquina=None, obs=None):
    exigir_data_ocorrida(data, "Solda")
    a = alvo(conn, alvo_tipo, ref, operacao=True)
    if tipo not in ("ELETROFUSAO", "TOPO"):
        raise RegraViolada("Tipo de solda inválido (ELETROFUSAO ou TOPO).")
    try:
        q = int(quantidade)
    except (TypeError, ValueError):
        q = 0
    if q <= 0 or float(quantidade) != q:
        raise RegraViolada("Quantidade de soldas deve ser um inteiro maior que zero.")
    if not (soldador or "").strip() or not (informado_por or "").strip():
        raise RegraViolada("Informe o soldador e quem registra.")
    if posicao_m is not None and a["alvo_tipo"] == "TRECHO" and not (0 <= float(posicao_m) <= float(a["extensao_m"]) + R.TOL_M):
        raise RegraViolada("Posição da solda fora do trecho.")
    return conn.execute(
        """INSERT INTO soldas(alvo_tipo,alvo_id,data,equipe_id,tipo,quantidade,posicao_m,soldador,maquina,informado_por,obs,
             registrado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a["alvo_tipo"], a["id"], data, equipe_id, tipo, q, posicao_m, soldador.strip(), maquina, informado_por.strip(), obs,
         _agora())).lastrowid


def verificar_soldas(conn, solda_id, verificado_por, resultado, obs=None):
    s_ = _one(conn, "SELECT * FROM soldas WHERE id=?", solda_id)
    if not s_:
        raise RegraViolada("Registro de solda não encontrado.")
    if s_["verificado_em"]:
        raise RegraViolada("Soldas já verificadas.")
    if resultado not in ("APROVADA", "REPROVADA"):
        raise RegraViolada("Resultado: APROVADA ou REPROVADA.")
    if not (verificado_por or "").strip():
        raise RegraViolada("Informe quem verificou.")
    if verificado_por.strip().lower() in (s_["informado_por"].lower(), s_["soldador"].lower()):
        raise RegraViolada("Quem soldou ou informou não pode verificar.")
    if resultado == "REPROVADA" and not (obs or "").strip():
        raise RegraViolada("Descreva o motivo da reprovação.")
    conn.execute("UPDATE soldas SET verificado_em=?, verificado_por=?, resultado=?, obs=COALESCE(?, obs) WHERE id=?",
                 (_agora(), verificado_por.strip(), resultado, obs, solda_id))


def resumo_soldas(conn, alvo_tipo, ref):
    a = alvo(conn, alvo_tipo, ref)
    regs = _rows(conn.execute("SELECT * FROM soldas WHERE alvo_tipo=? AND alvo_id=? ORDER BY data, id", (a["alvo_tipo"], a["id"])))
    soma = lambda f: sum(r["quantidade"] for r in regs if f(r))
    est = None
    if a["alvo_tipo"] == "TRECHO" and str(a.get("material") or "").upper() == "PEAD" and a.get("metodologia") != "MND":
        est = R.qtd_soldas(float(a["extensao_m"]), mapa_servicos()["solda"]["comprimento_barra_m"])
    return {"estimativa_barras_6m": est, "informadas": soma(lambda r: True),
            "aprovadas": soma(lambda r: r["resultado"] == "APROVADA"), "reprovadas": soma(lambda r: r["resultado"] == "REPROVADA"),
            "sem_verificacao": soma(lambda r: not r["verificado_em"]), "registros": regs}


# ------------------------------------------------------------------ fotos: original preservado com hash
LIMITE_FOTO = 20 * 1024 * 1024


def exif_jpeg(dados):
    """Data/hora de captura (DateTimeOriginal) e GPS do EXIF de um JPEG. {} se não houver ou estiver ilegível."""
    try:
        i = 2
        while i + 4 <= len(dados) and dados[i] == 0xFF:
            marcador, tam = dados[i + 1], struct.unpack(">H", dados[i + 2:i + 4])[0]
            if marcador == 0xE1 and dados[i + 4:i + 10] == b"Exif\x00\x00":
                return _ler_tiff(dados[i + 10:i + 2 + tam])
            if marcador == 0xDA:
                break
            i += 2 + tam
    except (struct.error, IndexError, ValueError, ZeroDivisionError):
        pass
    return {}


def _ler_tiff(t):
    e = "<" if t[:2] == b"II" else ">"
    u16 = lambda o: struct.unpack(e + "H", t[o:o + 2])[0]
    u32 = lambda o: struct.unpack(e + "I", t[o:o + 4])[0]

    def ifd(o):
        out = {}
        for k in range(u16(o)):
            p = o + 2 + 12 * k
            out[u16(p)] = (u16(p + 2), u32(p + 4), p + 8)
        return out

    def valor(ent):
        tipo, n, p = ent
        if tipo == 2:                                               # ASCII
            o = p if n <= 4 else u32(p)
            return t[o:o + n].rstrip(b"\x00").decode("ascii", "replace")
        if tipo == 5:                                               # RATIONAL
            o = u32(p)
            return [u32(o + 8 * j) / u32(o + 8 * j + 4) for j in range(n)]
        if tipo in (3, 4):
            return u16(p) if tipo == 3 else u32(p)
        return None

    out = {}
    ifd0 = ifd(u32(4))
    if 0x8769 in ifd0:
        ex = ifd(valor(ifd0[0x8769]))
        if 0x9003 in ex:
            d = valor(ex[0x9003])                                   # "AAAA:MM:DD HH:MM:SS"
            out["capturada_em"] = d[:10].replace(":", "-") + "T" + d[11:19]
    if 0x8825 in ifd0:
        g = ifd(valor(ifd0[0x8825]))
        if all(k in g for k in (1, 2, 3, 4)):
            dms = lambda v: v[0] + v[1] / 60 + v[2] / 3600
            lat, lon = dms(valor(g[2])), dms(valor(g[4]))
            out["lat"] = -lat if valor(g[1]).startswith("S") else lat
            out["lon"] = -lon if valor(g[3]).startswith("W") else lon
    return out


def registrar_foto(conn, alvo_tipo, ref, categoria, conteudo_b64, extensao=None, data_hora=None, lat=None, lon=None,
                   dir_fotos=DIR_FOTOS):
    """Guarda o ARQUIVO ORIGINAL (sem recompressão nem carimbo), com SHA-256, tipo e tamanho — depois de
    validar que é uma imagem íntegra (imagens.validar: decodificação com Pillow quando instalado; sem Pillow, PNG
    decodificado e JPEG verificado na estrutura). O método de validação fica registrado em `validacao`.

    Data de captura: EXIF (DateTimeOriginal) > informada pelo aparelho (`data_hora`) > hora do envio; a origem fica
    registrada. GPS: EXIF > navegador (`lat`/`lon`) > indisponível (nunca inventado). O carimbo é texto exibido sobre
    a foto. A mesma imagem (mesmo hash) não pode ser usada em outro registro.
    """
    a = alvo(conn, alvo_tipo, ref, operacao=True)
    if categoria not in R.FOTOS_TRECHO:
        raise RegraViolada("Categoria de foto inválida.")
    try:
        dados = base64.b64decode(conteudo_b64, validate=True)
    except (ValueError, TypeError):
        raise RegraViolada("Conteúdo da foto inválido.") from None
    if not dados or len(dados) > LIMITE_FOTO:
        raise RegraViolada(f"Foto vazia ou maior que {LIMITE_FOTO // (1024 * 1024)} MB.")
    try:
        ext, mime, metodo = imagens.validar(dados)
    except imagens.ImagemInvalida as e:
        raise RegraViolada(f"Foto recusada: {e}") from None
    h = hashlib.sha256(dados).hexdigest()
    dup = _one(conn, "SELECT alvo_tipo, alvo_id, categoria, data_hora FROM fotos WHERE sha256=?", h)
    if dup:
        raise RegraViolada(f"Esta mesma imagem já foi registrada ({dup['categoria']} de {nome_alvo(conn, dup['alvo_tipo'], dup['alvo_id'])}, "
                           f"{dup['data_hora']}). Cada evidência precisa de uma foto própria.")
    ex = exif_jpeg(dados) if ext == "jpg" else {}
    agora = _agora()
    if ex.get("capturada_em"):
        quando, origem_data = ex["capturada_em"], "EXIF"
    elif data_hora:
        quando, origem_data = data_hora, "DISPOSITIVO"
    else:
        quando, origem_data = agora, "ENVIO"
    if "lat" in ex:
        lat, lon, origem_gps = ex["lat"], ex["lon"], "EXIF"
    elif lat is not None and lon is not None:
        origem_gps = "NAVEGADOR"
    else:
        lat = lon = origem_gps = None
    carimbo = R.carimbo(contrato(conn), a["nome"], quando, lat, lon)
    os.makedirs(dir_fotos, exist_ok=True)
    nome = f"{h}.{ext}"
    caminho = os.path.join(dir_fotos, nome)
    if not os.path.exists(caminho):
        with open(caminho, "xb") as f:
            f.write(dados)
    conn.execute(
        """INSERT INTO fotos(alvo_tipo,alvo_id,area,categoria,arquivo,data_hora,lat,lon,carimbo,sha256,bytes,mime,origem_data,
             origem_gps,enviada_em,validacao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a["alvo_tipo"], a["id"], a.get("area"), categoria, nome, quando, lat, lon, carimbo, h, len(dados), mime,
         origem_data, origem_gps, agora, metodo))
    return {"arquivo": nome, "carimbo": carimbo, "sha256": h, "origem_data": origem_data, "origem_gps": origem_gps,
            "validacao": metodo}


def revalidar_fotos(conn, dir_fotos):
    """Valida as fotos ainda sem validação (gravadas antes do esquema v7, inclusive as LEGADO carimbadas).
    Não altera arquivos: só registra o resultado. Foto INVALIDA ou ARQUIVO_AUSENTE deixa de contar como evidência."""
    out = {}
    for f in _rows(conn.execute("SELECT id, arquivo FROM fotos WHERE validacao IS NULL")):
        p = os.path.join(dir_fotos, f["arquivo"])
        if not os.path.exists(p):
            res = "ARQUIVO_AUSENTE"
        else:
            with open(p, "rb") as fh:
                try:
                    res = imagens.validar(fh.read())[2]
                except imagens.ImagemInvalida:
                    res = "INVALIDA"
        conn.execute("UPDATE fotos SET validacao=? WHERE id=?", (res, f["id"]))
        out[res] = out.get(res, 0) + 1
    return out


# ------------------------------------------------------------------ lançamentos (sem regime financeiro aplicado)
def _bm_item(conn, chave):
    return _one(conn, "SELECT * FROM bm_itens WHERE planilha='VERTICAL' AND item=? AND vigente=1", chave)


def _itens_servico(conn, servico, trecho):
    """[(bm_item, fração)] de um serviço da 06.1, segundo config/servicos_rede.json; [] = sem vínculo com fonte."""
    cfg = next((s for s in mapa_servicos()["gaveta1"] if s["servico"] == servico), None)
    if not cfg or cfg["status"] != "CONFIRMADO" or not cfg["itens"]:
        return []
    itens = [_bm_item(conn, k.format(codigo_bm=trecho.get("codigo_bm"))) for k in cfg["itens"]]
    if not all(itens):                   # vínculo incompleto no BM vigente: não rateia tudo no item que sobrou
        return []
    return R.ratear(1.0, [(i, i["quantidade"] or 0) for i in itens])


def chave_parcela(tipo_medicao, gaveta, servico, alvo_tipo, alvo_id, item, unidade, nf_id=None, material_id=None):
    """Identidade da parcela medida: a mesma parcela (alvo × serviço × item) não entra em duas medições do mesmo tipo.
    O item vai pelo código (e não pelo id interno), para valer também depois de uma revisão do BM."""
    return "|".join(str(x if x is not None else "") for x in
                    (tipo_medicao, gaveta, servico, alvo_tipo, alvo_id, item, unidade, nf_id, material_id))


def _lancar(conn, medicao_id, gaveta, servico, bm, unidade, quantidade, alvo_tipo=None, alvo_id=None,
            nf_id=None, material_id=None, motivo=None, obs=None):
    status = "PROPOSTO" if bm is not None and not motivo else "PENDENTE"
    if status == "PENDENTE" and not motivo:
        motivo = "sem item de BM com fonte"
    med = _one(conn, "SELECT numero, tipo, status FROM medicoes WHERE id=?", medicao_id)
    if med["status"] != "ABERTA":
        raise RegraViolada(f"A {med['numero']}ª medição já está fechada.")
    chave = chave_parcela(med["tipo"], gaveta, servico, alvo_tipo, alvo_id, bm["item"] if bm else None, unidade, nf_id, material_id)
    # a mesma parcela em outra medição (ou repetida nesta), inclusive pelo alvo × serviço quando o item mudou de id
    ja = _one(conn, """SELECT m.numero FROM medicao_lancamentos l JOIN medicoes m ON m.id=l.medicao_id
                        WHERE l.chave=? OR (m.tipo=? AND l.gaveta=? AND l.servico=? AND l.alvo_tipo IS ? AND l.alvo_id IS ?
                                            AND l.alvo_id IS NOT NULL AND l.medicao_id<>?)""",
              chave, med["tipo"], gaveta, servico, alvo_tipo, alvo_id, medicao_id)
    if ja:
        raise RegraViolada(f"Parcela já medida: {servico} de {nome_alvo(conn, alvo_tipo, alvo_id) if alvo_id else 'NF/material'} "
                           f"já está na {ja['numero']}ª medição ({med['tipo']}). Nada foi lançado.")
    conn.execute(
        """INSERT INTO medicao_lancamentos(medicao_id,gaveta,servico,bm_item_id,alvo_tipo,alvo_id,nf_id,material_id,
             unidade,quantidade,status,motivo,observacao,chave) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (medicao_id, gaveta, servico, bm["id"] if bm else None, alvo_tipo, alvo_id, nf_id, material_id, unidade,
         round(quantidade, 4), status, motivo, obs, chave))


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
    exigir_data_ocorrida(data, "OK interno")
    a = alvo(conn, alvo_tipo, ref, operacao=True)
    tipo, aid = a["alvo_tipo"], a["id"]
    if tipo == "TRECHO":
        _exigir_sem_legado(conn, a, "o OK interno")
    ex = execucao(conn, tipo, aid)
    R.validar_ok_fiscal(ex, fotos_faltando(conn, tipo, aid))
    servico_solda = mapa_servicos()["solda"]["servico"]
    med = medicao_para(conn, data)
    with transacao(conn):
        conn.execute("UPDATE execucao SET ok_fiscal_em=?, ok_fiscal_por=?, medicao_id=? WHERE alvo_tipo=? AND alvo_id=?",
                     (data, usuario, med["id"], tipo, aid))
        # SOLDA de apontamentos antigos (estimativa ⌈L/6⌉ gravada como confirmada) é ignorada: vale o controle de soldas.
        # Apontamento retificado (anulado_por) fica fora: vale o substituto, sem dupla contagem.
        servs = _rows(conn.execute(
            """SELECT q.servico, q.unidade, SUM(q.confirmado) qtd FROM apontamento_quantidades q
               JOIN apontamentos ap ON ap.id=q.apontamento_id
               WHERE ap.alvo_tipo=? AND ap.alvo_id=? AND ap.anulado_por IS NULL AND q.servico<>?
               GROUP BY q.servico, q.unidade""",
            (tipo, aid, servico_solda)))
        aprov = conn.execute("SELECT COALESCE(SUM(quantidade),0) FROM soldas WHERE alvo_tipo=? AND alvo_id=? "
                             "AND resultado='APROVADA'", (tipo, aid)).fetchone()[0]
        if aprov:
            _lancar(conn, med["id"], 1, servico_solda, None, "UN", aprov, tipo, aid,
                    motivo="SOLDA: item de BM e regra contratual a confirmar; quantidade = soldas verificadas e "
                           "APROVADAS no controle de soldas (a estimativa ⌈L/6⌉ não é usada)")
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
    exigir_data_ocorrida(data, "Recomposição")
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
def ultima_conferencia(conn, trecho_id, revisao):
    """Última conferência interna Ankara registrada para a revisão do cadastro (ou None)."""
    r = _one(conn, "SELECT * FROM revisoes_cadastro WHERE trecho_id=? AND revisao=? ORDER BY id DESC LIMIT 1", trecho_id, revisao)
    if r:
        r["checklist"] = json.loads(r["checklist"])
    return r


def registrar_conferencia_cadastro(conn, trecho_ref, resultado, checklist, revisor, obs=None):
    """Conferência interna Ankara do cadastro recebido da empresa (etapa 3), antes do protocolo no GDOC.

    Finalidade: achar divergência entre o desenho e o executado/levantamento de campo antes de protocolar, para
    evitar negativa no GDOC. NÃO é aprovação da Caesb nem libera medição. NAO_CONFORME impede protocolar aquela
    revisão e permite devolver o cadastro à empresa (nova revisão)."""
    t = alvo(conn, "TRECHO", trecho_ref, operacao=True)
    c = _one(conn, "SELECT * FROM cadastro WHERE trecho_id=?", t["id"])
    if not c or c["etapa"] != "3_RECEBIDO":
        raise RegraViolada("A conferência interna é feita sobre o cadastro recebido da empresa (etapa 3).")
    itens = R.validar_conferencia(resultado, checklist, revisor, obs)
    return conn.execute(
        "INSERT INTO revisoes_cadastro(trecho_id,revisao,resultado,checklist,revisor,obs,em) VALUES (?,?,?,?,?,?,?)",
        (t["id"], c["revisao"], resultado, json.dumps(itens), revisor.strip(), (obs or "").strip() or None, _agora())).lastrowid


def avancar_cadastro(conn, trecho_ref, destino, dados=None, data=None):
    dados = dados or {}
    t = alvo(conn, "TRECHO", trecho_ref, operacao=True)
    c = _one(conn, "SELECT * FROM cadastro WHERE trecho_id=?", t["id"])
    if not c:
        raise RegraViolada("Trecho não está na esteira (exige OK Fiscalização).")
    R.validar_transicao(c["etapa"], destino, dados)
    conf = ultima_conferencia(conn, t["id"], c["revisao"]) if c["etapa"] == "3_RECEBIDO" else None
    if c["etapa"] == "3_RECEBIDO" and destino == "4_GDOC_ANALISE" and conf and conf["resultado"] == "NAO_CONFORME":
        raise RegraViolada(f"A conferência interna da Rev. {c['revisao']} foi NÃO CONFORME ({conf['obs']}): devolva o "
                           "cadastro à empresa antes de protocolar no GDOC.")
    if c["etapa"] == "3_RECEBIDO" and destino == "2_ENVIADO":
        if not conf or conf["resultado"] != "NAO_CONFORME":
            raise RegraViolada("Devolver à empresa exige conferência interna NÃO CONFORME registrada para esta revisão.")
        dados = dict(dados, conferencia_id=conf["id"], motivo_devolucao=conf["obs"])
    campos = {"etapa": destino, "atualizado_em": _agora()}
    if destino == "2_ENVIADO":
        if c["etapa"] in ("5A_NEGADO", "3_RECEBIDO"):
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
        c["conferencia"] = ultima_conferencia(conn, c["trecho_id"], c["revisao"])
        cad = R.comprimento(_cobertura(conn, c["trecho_id"], "CADASTRO_CAMPO"))
        c["levantamento_m"] = cad
        c["levantamento_completo"] = cad >= float(c["extensao_m"]) - R.TOL_M
    return out


ROTULO_CONFERENCIA = "Conferência interna Ankara — não é aprovação da Caesb"


def fases_cadastro(conn, t, sit=None):
    """Do levantamento em campo (antes de fechar a vala) à entrega do cadastro final, com evidências e pendências.

    1. LEVANTAMENTO_CAMPO — o que a equipe levanta com a vala aberta (intervalos CADASTRO_CAMPO, com registro de
       referência: caderneta, croqui ou arquivo de pontos). Depois do reaterro não dá mais para levantar.
    2. PREPARACAO — a empresa de cadastro produz o desenho a partir do levantamento (esteira 1 → 3).
    3. CONFERENCIA_INTERNA — a Ankara confere o desenho com o executado antes de protocolar (não é aprovação Caesb).
    4. ENTREGA_GDOC — protocolo no GDOC e decisão da Caesb, registrada a partir do documento dela (ESET/negativa).
    """
    sit = sit or situacao_intervalos(conn, t["id"])
    ext = float(t["extensao_m"])
    fmt = lambda i: f"{i['ini_m']:g}–{i['fim_m']:g} m ({i['data']})"
    cads = [i for i in sit["intervalos"] if i["etapa"] == "CADASTRO_CAMPO"]
    cob_cad = sit["etapas"]["CADASTRO_CAMPO"]["cobertura"]
    falta_lev = [f for a, b in sit["etapas"]["ASSENTADO"]["cobertura"] for f in R.fora_da_cobertura((a, b), cob_cad)]
    lev = {"fase": "LEVANTAMENTO_CAMPO", "nome": "1. Levantamento de campo (vala aberta, antes do reaterro)",
           "evidencias": [f"{fmt(i)} · {i['informado_por'] or 'sem informante'} · "
                          + (f"registro: {i['referencia']}" if i["referencia"] else "sem registro de referência")
                          + (f" · verificado por {i['verificado_por']}" if i["verificado_em"] else " · sem verificação")
                          for i in cads], "pendencias": []}
    m_cad = sit["etapas"]["CADASTRO_CAMPO"]["metros"]
    lev["status"] = "NAO_INICIADO" if not cads else "COMPLETO" if m_cad >= ext - R.TOL_M else "PARCIAL"
    if sit["legado"]:
        lev["pendencias"].append("Avanço anterior sem posição: conciliar antes de conferir o levantamento.")
    if falta_lev:
        lev["pendencias"].append("Assentado sem levantamento de campo: " + _faixas(falta_lev))
    sem = [(i, R.fora_da_cobertura((i["ini_m"], i["fim_m"]), [(x["ini_m"], x["fim_m"]) for x in cads if x["data"] <= i["data"]]))
           for i in sit["intervalos"] if i["sem_cadastro_campo"]]
    if sem:
        lev["pendencias"].append("Reaterrado antes do levantamento (alerta): "
                                 + "; ".join(f"{_faixas(f)} (reaterro de {i['data']})" for i, f in sem))
    if [i for i in cads if not i["referencia"]]:
        lev["pendencias"].append("Levantamento sem registro de referência (caderneta, croqui ou arquivo): "
                                 + ", ".join(fmt(i) for i in cads if not i["referencia"]))
    if [i for i in cads if not i["verificado_em"]]:
        lev["pendencias"].append(f"{sum(1 for i in cads if not i['verificado_em'])} intervalo(s) de levantamento sem verificação interna.")
    c = _one(conn, "SELECT * FROM cadastro WHERE trecho_id=?", t["id"])
    etapa = c["etapa"] if c else None
    ordem = list(R.ETAPAS)
    pos = ordem.index(etapa) if etapa else -1
    prep = {"fase": "PREPARACAO", "nome": "2. Preparação do cadastro final (empresa de cadastro)", "evidencias": [], "pendencias": []}
    if not c:
        prep["status"] = "AGUARDA_OK_INTERNO"
        prep["pendencias"].append("Entra na esteira com o OK interno (trecho 100 % reaterrado e fotos).")
    else:
        prep["status"] = {"1_PRONTO": "PRONTO_PARA_ENVIO", "2_ENVIADO": "EM_PRODUCAO"}.get(etapa, "RECEBIDO")
        if c["empresa"]:
            prep["evidencias"].append(f"Enviado a {c['empresa']} em {c['data_envio']}" + (f" (Rev. {c['revisao']})" if c["revisao"] else ""))
        if c["arquivos"]:
            prep["evidencias"].append("Arquivos recebidos: " + ", ".join(json.loads(c["arquivos"]) if c["arquivos"].startswith("[") else [c["arquivos"]]))
        if etapa == "1_PRONTO":
            prep["pendencias"].append("Enviar os dados do levantamento à empresa de cadastro.")
        if etapa == "2_ENVIADO":
            prep["pendencias"].append("Aguardando os arquivos da empresa.")
        if etapa in ("1_PRONTO", "2_ENVIADO") and lev["status"] != "COMPLETO":
            prep["pendencias"].append("Levantamento de campo incompleto: a empresa trabalharia com dados parciais (alerta).")
    conf = {"fase": "CONFERENCIA_INTERNA", "nome": "3. " + ROTULO_CONFERENCIA, "evidencias": [], "pendencias": []}
    revs = _rows(conn.execute("SELECT * FROM revisoes_cadastro WHERE trecho_id=? ORDER BY id", (t["id"],)))
    for r in revs:
        nao = [R.CHECKLIST_CONFERENCIA_CADASTRO[k] for k, v in json.loads(r["checklist"]).items() if not v]
        conf["evidencias"].append(f"Rev. {r['revisao']}: {r['resultado']} por {r['revisor']} em {r['em'][:10]}"
                                  + (f" — {r['obs']}" if r["obs"] else "") + (f" (não conferido: {'; '.join(nao)})" if nao else ""))
    ult = ultima_conferencia(conn, t["id"], c["revisao"]) if c else None
    if pos < ordem.index("3_RECEBIDO"):
        conf["status"] = "AGUARDA_ARQUIVOS"
    elif etapa == "3_RECEBIDO":
        conf["status"] = ult["resultado"] if ult else "SEM_CONFERENCIA"
        if not ult:
            conf["pendencias"].append(f"Conferir o cadastro recebido (Rev. {c['revisao']}) antes de protocolar no GDOC.")
        elif ult["resultado"] == "NAO_CONFORME":
            conf["pendencias"].append(f"Não conforme: {ult['obs']} — devolver à empresa.")
    else:
        conf["status"] = ult["resultado"] if ult else "PROTOCOLADO_SEM_CONFERENCIA"
    gd = {"fase": "ENTREGA_GDOC", "nome": "4. Entrega à Caesb (GDOC)", "evidencias": [], "pendencias": []}
    gd["status"] = {"4_GDOC_ANALISE": "EM_ANALISE_CAESB", "5A_NEGADO": "NEGADO_CAESB", "6_APROVADO": "APROVACAO_CAESB_REGISTRADA"}.get(etapa, "NAO_PROTOCOLADO")
    for h in _rows(conn.execute("SELECT * FROM cadastro_historico WHERE trecho_id=? AND para_etapa IN ('4_GDOC_ANALISE','5A_NEGADO','6_APROVADO') ORDER BY id", (t["id"],))):
        dd = json.loads(h["dados"] or "{}")
        gd["evidencias"].append(f"{R.ETAPAS[h['para_etapa']]} em {h['em'][:10]}: "
                                + (dd.get("protocolo_gdoc") or dd.get("motivo_negativa") or dd.get("memorando_eset") or ""))
    if etapa == "4_GDOC_ANALISE":
        gd["pendencias"].append(f"Aguardando a análise da Caesb (protocolo {c['protocolo_gdoc']}).")
    elif etapa == "5A_NEGADO":
        gd["pendencias"].append(f"Negado pela Caesb: {c['motivo_negativa']} — reenviar à empresa para ajuste.")
    elif etapa == "6_APROVADO":
        gd["evidencias"].append(f"Registrado a partir do memorando ESET {c['memorando_eset']} (documento da Caesb; o sistema não aprova).")
    return [lev, prep, conf, gd]


def pendencias_alvo(conn, d):
    """Pendências consolidadas do detalhe (visão integrada): BLOQUEIO impede uma ação; ALERTA pede correção ou decisão;
    PENDENTE é o que falta fazer. Nada aqui é aprovação da Caesb."""
    out = []
    add = lambda nivel, area, texto: out.append({"nivel": nivel, "area": area, "texto": texto})
    if d.get("perfil_bloqueado"):
        add("BLOQUEIO", "Cálculo", f"{d['perfil_bloqueado']} (quantidades previstas bloqueadas).")
    iv = d.get("intervalos")
    if iv:
        if iv["legado"]:
            add("BLOQUEIO", "Execução", f"Avanço anterior sem posição ({iv['legado']['ASSENTADO']:g} m assentados, "
                f"{iv['legado']['REATERRADO']:g} m reaterrados): conciliar antes de novos intervalos, 100 % e OK interno.")
        ex = d.get("execucao") or {}
        if not iv["legado"] and (ex.get("metros_executados") or 0) > 0:
            for e, v in iv["etapas"].items():
                if e != "CADASTRO_CAMPO" and v["lacunas"]:
                    add("PENDENTE", "Execução", f"{e}: falta {_faixas(v['lacunas'])}.")
        if iv["incoerencias"]:
            add("ALERTA", "Execução", "Cronologia incoerente em registro anterior: corrigir por retificação.")
        seq = [i for i in iv["intervalos"] if i["origem"] == "SEQUENCIAL"]
        if seq:
            add("ALERTA", "Execução", f"{len(seq)} intervalo(s) com posição presumida: confirmar por retificação.")
        nv = [i for i in iv["intervalos"] if not i["verificado_em"]]
        if nv:
            add("PENDENTE", "Verificação interna", f"{len(nv)} intervalo(s) informados sem verificação.")
    for txt in (d.get("complementar") or {}).get("alertas", []):
        add("ALERTA", "Topografia", txt)
    for o in d.get("ocorrencias") or []:
        if not o["resolvida_em"]:
            add("ALERTA", "Ocorrências", f"{'Impedimento' if o['tipo'] == 'IMPEDIMENTO' else 'Não conformidade'} aberto(a) desde "
                f"{o['data']} ({o['categoria']}): {o['descricao']}")
    s_ = d.get("soldas") or {}
    if s_.get("sem_verificacao"):
        add("PENDENTE", "Soldas", f"{s_['sem_verificacao']} solda(s) sem verificação.")
    if s_.get("reprovadas"):
        add("ALERTA", "Soldas", f"{s_['reprovadas']} solda(s) reprovada(s): refazer e registrar de novo.")
    if s_.get("estimativa_barras_6m") and not s_.get("informadas") and (d.get("execucao") or {}).get("metros_executados"):
        add("PENDENTE", "Soldas", f"Nenhuma solda registrada (estimativa ⌈L/6⌉ = {s_['estimativa_barras_6m']}, só referência).")
    if d.get("fotos_faltando"):
        add("PENDENTE", "Fotos", "Faltam: " + ", ".join(d["fotos_faltando"]) + " (exigidas no OK interno).")
    ruins = [f for f in d.get("fotos", []) if f.get("validacao") in (None, "INVALIDA", "ARQUIVO_AUSENTE")]
    if ruins:
        add("ALERTA", "Fotos", f"{len(ruins)} foto(s) que não contam como evidência (" +
            ", ".join(f"{f['categoria']}: {f.get('validacao') or 'não validada'}" for f in ruins) + ").")
    for f in d.get("fases_cadastro") or []:
        for p in f["pendencias"]:
            add("ALERTA" if "(alerta)" in p or p.startswith("Não conforme") or p.startswith("Negado") else "PENDENTE",
                f["nome"].split(" (")[0], p)
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


def assinatura_medicao(conn, medicao_id):
    """Hash dos lançamentos da medição (id, gaveta, serviço, alvo, item, quantidade, status): muda se qualquer um mudar."""
    linhas = conn.execute("""SELECT id, gaveta, servico, alvo_tipo, alvo_id, bm_item_id, quantidade, status FROM medicao_lancamentos
                             WHERE medicao_id=? ORDER BY id""", (medicao_id,)).fetchall()
    return hashlib.sha256(json.dumps([list(r) for r in linhas], default=str).encode()).hexdigest()


def conferencia_vigente(conn, medicao_id):
    """Última conferência interna da medição e se ela ainda vale (mesmos lançamentos conferidos)."""
    c = _one(conn, "SELECT * FROM conferencias_medicao WHERE medicao_id=? ORDER BY id DESC LIMIT 1", medicao_id)
    if not c:
        return None
    c["checklist"], c["retrato"] = json.loads(c["checklist"]), json.loads(c["retrato"])
    c["vale"] = c["assinatura"] == assinatura_medicao(conn, medicao_id)
    return c


def fechar_medicao(conn, medicao_id, por=None):
    """Fecha e CONGELA a medição. O preço, a classificação e o item de cada lançamento, os fatores
    (BDI, K) e o resumo ficam gravados. Uma revisão posterior do BM não recalcula o valor dela.

    Exige a conferência interna CONFORME da engenharia sobre os lançamentos atuais (D-59, provisório)."""
    med = _one(conn, "SELECT * FROM medicoes WHERE id=?", medicao_id)
    if not med:
        raise RegraViolada("Medição não encontrada.")
    if med["status"] != "ABERTA":
        raise RegraViolada(f"A {med['numero']}ª medição ({med['tipo']}) já está fechada.")
    conf = conferencia_vigente(conn, medicao_id)
    if not conf:
        raise RegraViolada("Fechar exige a conferência interna da medição (aba 5 — Conferência).")
    if conf["resultado"] != "CONFORME":
        raise RegraViolada(f"A última conferência interna foi NÃO CONFORME ({conf['obs']}): corrija e confira de novo.")
    if not conf["vale"]:
        raise RegraViolada("Os lançamentos mudaram depois da conferência interna: confira de novo antes de fechar.")
    with transacao(conn):
        congelar_medicao(conn, medicao_id, "fechamento")
        conn.execute("UPDATE medicoes SET status='FECHADA', fechada_por=?, fechada_em=?, conferencia_id=? WHERE id=?",
                     (por, _agora(), conf["id"], medicao_id))


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
        d["intervalos"] = situacao_intervalos(conn, aid)
        d["complementar"] = situacao_complementar(conn, a, d["intervalos"])
        d["fases_cadastro"] = fases_cadastro(conn, a, d["intervalos"])
    else:
        d.update(totais_atividade(conn, aid))
        d["itens"] = itens_atividade(conn, aid)
        d["trechos_ligados"] = trechos_da_atividade(conn, aid)
        d["outras_atividades"] = _rows(conn.execute(
            "SELECT id, nomenclatura, frente_id FROM atividades WHERE elemento_id=? AND id<>? AND vigente=1",
            (a["elemento_id"], aid)))
        d.update(avisos_e_decisoes(conn, aid))
    d["soldas"] = resumo_soldas(conn, tipo, aid)
    d["ocorrencias"] = ocorrencias(conn, tipo, aid)
    d["pendencias"] = pendencias_alvo(conn, d)
    return d


# Tabelas com registro operacional ligado a um alvo. A importação não retira um alvo com histórico sem
# conciliação, e o mapa lista os retirados que têm histórico. Uma definição só, usada pelos dois.
HISTORICO_POR_ALVO = ["checkins", "apontamentos", "fotos", "execucao", "movimentos", "medicao_lancamentos", "soldas",
                      "reservas", "ocorrencias", "programacoes"]
HISTORICO_POR_TRECHO = [("cadastro", "trecho_id"), ("ligacoes_prediais", "trecho_id"), ("intervalos_execucao", "trecho_id"),
                        ("conciliacoes_legado", "trecho_id"), ("retificacoes_intervalos", "trecho_id"),
                        ("revisoes_cadastro", "trecho_id"), ("etapas_complementares", "trecho_id")]
NOMES_HISTORICO = {"checkins": "check-in", "apontamentos": "apontamento", "fotos": "foto", "execucao": "execução",
                   "movimentos": "movimento de material", "medicao_lancamentos": "lançamento de medição (teste)",
                   "soldas": "soldas", "reservas": "reserva de material", "cadastro": "esteira de cadastro",
                   "ligacoes_prediais": "ligação predial", "intervalos_execucao": "intervalos executados",
                   "conciliacoes_legado": "conciliação do legado", "retificacoes_intervalos": "retificação de intervalos",
                   "revisoes_cadastro": "conferência interna do cadastro", "ocorrencias": "ocorrência de campo", "programacoes": "programação de equipe",
                   "etapas_complementares": "liberação topográfica / escavação"}


def historico_alvos(conn, alvo_tipo):
    """{id: [tabelas com registro]} para TRECHO ou ATIVIDADE."""
    tabelas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    out = {}
    for t in HISTORICO_POR_ALVO:
        if t in tabelas:
            for (aid,) in conn.execute(f"SELECT DISTINCT alvo_id FROM {t} WHERE alvo_tipo=? AND alvo_id IS NOT NULL", (alvo_tipo,)):
                out.setdefault(aid, []).append(t)
    if alvo_tipo == "TRECHO":
        for t, col in HISTORICO_POR_TRECHO:
            if t in tabelas:
                for (aid,) in conn.execute(f"SELECT DISTINCT {col} FROM {t}"):
                    out.setdefault(aid, []).append(t)
    return out


def estado_mapa(conn, medicao_atual_id=None, data=None):
    """Mapa Iluminado: estado CORRENTE por nome visível (só objetos vigentes), pins e bandeja sem posição.

    O histórico de objetos retirados não é apagado. Cada objeto retirado com qualquer registro operacional
    (execução, check-in, foto, soldas, intervalos, reserva...) aparece UMA vez em `retirados_com_historico`, com
    o que existe e o que precisa de tratamento; não entra nas cores do mapa.
    """
    vig = {("TRECHO", r[0]): r[1] for r in conn.execute("SELECT id, ponto FROM trechos WHERE vigente=1")}
    vig.update({("ATIVIDADE", r[0]): r[1] for r in conn.execute(
        "SELECT a.id, a.nomenclatura FROM atividades a JOIN elementos e ON e.id=a.elemento_id "
        "WHERE a.vigente=1 AND e.vigente=1")})
    ex = {(r["alvo_tipo"], r["alvo_id"]): dict(r) for r in conn.execute("SELECT * FROM execucao")}
    fotos = {}
    for r in conn.execute(f"SELECT alvo_tipo, alvo_id, categoria FROM fotos WHERE {FOTO_VALIDA}"):
        fotos.setdefault((r[0], r[1]), []).append(r[2])
    status = {}
    for (tipo, aid), e in ex.items():
        if (tipo, aid) in vig:
            her = _sinalizacao_herdada(conn, tipo, aid) if tipo == "ATIVIDADE" else False
            falt = R.fotos_pendentes(tipo, fotos.get((tipo, aid), []), her)
            status[vig[(tipo, aid)]] = R.status_mapa(e, falt, medicao_atual_id)
    # informado × verificado (conferência interna Ankara) e avanço legado sem posição, só de registros efetivos
    legado = {r[0]: (r[1], r[2]) for r in conn.execute(
        f"SELECT ap.alvo_id, SUM(COALESCE(ap.metros_executados,0)), SUM(COALESCE(ap.metros_reaterrados,0)) {_SQL_LEGADO} GROUP BY ap.alvo_id")}
    contagem = {r[0]: (r[1], r[2]) for r in conn.execute(
        f"SELECT trecho_id, COUNT(*), SUM(verificado_em IS NOT NULL) FROM intervalos_execucao WHERE {EFETIVO} GROUP BY trecho_id")}
    verificacao = {}
    for (tipo, aid), nome in vig.items():
        if tipo == "TRECHO":
            v = estado_verificacao(*contagem.get(aid, (0, 0)), aid in legado)
            if v:
                verificacao[nome] = v
    retirados = {}
    for tipo in ("TRECHO", "ATIVIDADE"):
        for aid, tabs in historico_alvos(conn, tipo).items():
            if (tipo, aid) in vig:
                continue
            retirados[(tipo, aid)] = {"alvo_tipo": tipo, "alvo_id": aid, "nome": nome_alvo(conn, tipo, aid),
                                      "historico": sorted({NOMES_HISTORICO.get(t, t) for t in tabs}), "situacoes": []}
            if (tipo, aid) in ex and not ex[(tipo, aid)].get("ok_fiscal_em"):
                retirados[(tipo, aid)]["situacoes"].append("execução registrada sem OK interno")
            n = conn.execute("SELECT COALESCE(SUM(quantidade),0) FROM soldas WHERE alvo_tipo=? AND alvo_id=?", (tipo, aid)).fetchone()[0]
            if n:
                retirados[(tipo, aid)]["situacoes"].append(f"{n} solda(s) registrada(s)")
    pins = []
    for c in checkins_abertos(conn, data or date.today().isoformat()):
        if not c["alvo_id"]:
            continue
        if c["alvo_retirado"]:
            r = retirados.setdefault((c["alvo_tipo"], c["alvo_id"]), {
                "alvo_tipo": c["alvo_tipo"], "alvo_id": c["alvo_id"], "nome": c["alvo_nome"], "historico": ["check-in"],
                "situacoes": []})
            r["situacoes"].append(f"check-in {c['id']} aberto ({c['equipe_id']}) — encerrar no check-out")
            continue
        pins.append({"equipe": c["equipe_id"], "alvo_tipo": c["alvo_tipo"], "alvo_id": c["alvo_nome"], "checkin": c["id"],
                     "data": c["data"], "origem": "programação do check-in"})
    return {
        "status": status,
        "verificacao": verificacao,
        "legado_sem_posicao": [{"alvo_id": aid, "nome": vig[("TRECHO", aid)], "assentado_m": m[0], "reaterrado_m": m[1]}
                               for aid, m in sorted(legado.items(), key=lambda x: str(vig.get(("TRECHO", x[0]))))
                               if ("TRECHO", aid) in vig],
        "pins": pins,
        "retirados_com_historico": sorted(retirados.values(), key=lambda r: (r["alvo_tipo"], str(r["nome"]))),
        "sem_posicao": _rows(conn.execute(
            """SELECT e.id, e.numero, e.status_posicao, GROUP_CONCAT(a.nomenclatura, ' | ') nomenclaturas
               FROM elementos e JOIN atividades a ON a.elemento_id=e.id AND a.vigente=1
               WHERE e.vigente=1 AND (e.lat IS NULL OR e.lon IS NULL) GROUP BY e.id ORDER BY e.numero""")),
    }
