"""Campo: o diário de cada dia (o que cada equipe fez) e o painel de interferências e ocorrências.

Só leitura: junta o que o lançamento de campo, o check-in, o planejamento e as ocorrências já gravaram. Nada aqui grava;
abrir e resolver uma interferência continuam nas rotas de ocorrência (servicos.abrir_ocorrencia / resolver_ocorrencia).
"""
import re
from datetime import date

import planejamento as P
import regras as R
import servicos as S
from servicos import RegraViolada, _rows

ETAPAS = ("ASSENTADO", "CADASTRO_CAMPO", "REATERRADO")


def _data(d):
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d or "")):
            return date.fromisoformat(d).isoformat()
    except ValueError:
        pass
    raise RegraViolada("Informe a data no formato AAAA-MM-DD.")


def _equipe(conn, equipe):
    if equipe and not conn.execute("SELECT 1 FROM equipes WHERE id=?", (equipe,)).fetchone():
        raise RegraViolada(f"Equipe '{equipe}' não existe.")
    return equipe or None


def diario(conn, data, equipe=None):
    """Tudo o que foi registrado no dia, por seção: clima, programação, check-in, produção, liberações, soldas, fotos e
    ocorrências. Com `equipe`, só o daquela equipe (fotos: as dos trechos e nós em que ela trabalhou no dia)."""
    data, equipe = _data(data), _equipe(conn, equipe)
    so = (" AND equipe_id=?", (equipe,)) if equipe else ("", ())
    nomes = dict(conn.execute("SELECT id, nome FROM equipes"))
    nome = lambda tipo, aid: S.nome_alvo(conn, tipo, aid)

    clima = {}
    for eq, turno, cond in conn.execute("SELECT equipe_id, turno, condicao FROM clima WHERE data=?" + so[0], (data, *so[1])):
        clima.setdefault(eq, {})[turno] = R.CONDICOES_CLIMA.get(cond, cond)

    producao = [{"equipe_id": i["equipe_id"], "trecho_id": i["trecho_id"], "trecho": nome("TRECHO", i["trecho_id"]), "etapa": i["etapa"],
                 "ini_m": i["ini_m"], "fim_m": i["fim_m"], "metros": round(i["fim_m"] - i["ini_m"], 2), "informado_por": i["informado_por"],
                 "referencia": i["referencia"], "verificado": bool(i["verificado_em"])}
                for i in _rows(conn.execute(f"SELECT * FROM intervalos_execucao WHERE data=? AND {S.EFETIVO}" + so[0]
                                            + " ORDER BY equipe_id, trecho_id, etapa, ini_m", (data, *so[1])))]

    soldas = [dict(s, alvo_nome=nome(s["alvo_tipo"], s["alvo_id"]))
              for s in _rows(conn.execute("SELECT * FROM soldas WHERE data=?" + so[0] + " ORDER BY equipe_id, id", (data, *so[1])))]

    checkins = []
    for c in _rows(conn.execute("SELECT * FROM checkins WHERE data=?" + so[0] + " ORDER BY equipe_id, id", (data, *so[1]))):
        pres = dict(conn.execute("SELECT recurso_tipo, COUNT(*) FROM checkin_presencas WHERE checkin_id=? GROUP BY recurso_tipo", (c["id"],)))
        mats = _rows(conn.execute(f"""SELECT material_id, tipo, ROUND(SUM(quantidade), 3) AS quantidade FROM movimentos
                                      WHERE checkin_id=? AND {S.VALIDO} GROUP BY material_id, tipo ORDER BY material_id, tipo""", (c["id"],)))
        checkins.append(dict(c, alvo_nome=nome(c["alvo_tipo"], c["alvo_id"]) if c["alvo_id"] else None,
                             funcionarios=pres.get("FUNCIONARIO", 0), maquinas=pres.get("MAQUINA", 0), materiais=mats))

    liberacoes = [dict(e, trecho=nome("TRECHO", e["trecho_id"]))
                  for e in _rows(conn.execute("SELECT * FROM etapas_complementares WHERE data=? AND anulado_em IS NULL ORDER BY id", (data,)))]

    ocorrencias = [dict(o, alvo_nome=nome(o["alvo_tipo"], o["alvo_id"]))
                   for o in _rows(conn.execute("SELECT * FROM ocorrencias WHERE data=?" + so[0] + " ORDER BY id", (data, *so[1])))]

    fotos = _rows(conn.execute(f"""SELECT id, alvo_tipo, alvo_id, categoria, arquivo, carimbo, data_hora FROM fotos
                                   WHERE substr(data_hora, 1, 10)=? AND {S.FOTO_VALIDA} ORDER BY data_hora, id""", (data,)))
    if equipe:                                       # foto não tem equipe: valem as dos lugares em que a equipe trabalhou
        lugares = ({("TRECHO", p["trecho_id"]) for p in producao} | {(s["alvo_tipo"], s["alvo_id"]) for s in soldas}
                   | {(c["alvo_tipo"], c["alvo_id"]) for c in checkins if c["alvo_id"]})
        fotos = [f for f in fotos if (f["alvo_tipo"], f["alvo_id"]) in lugares]
    for f in fotos:
        f["alvo_nome"] = nome(f["alvo_tipo"], f["alvo_id"])

    programacoes = P.programacoes(conn, data, data, None, equipe)
    if equipe:                                       # liberação e escavação não têm equipe: só no diário da obra inteira
        liberacoes = []

    equipes = sorted({*clima, *(p["equipe_id"] for p in producao if p["equipe_id"]), *(s["equipe_id"] for s in soldas if s["equipe_id"]),
                      *(c["equipe_id"] for c in checkins), *(p["equipe_id"] for p in programacoes),
                      *(o["equipe_id"] for o in ocorrencias if o["equipe_id"])})
    metros = {e: round(sum(p["metros"] for p in producao if p["etapa"] == e), 2) for e in ETAPAS}
    return {"data": data, "equipe": equipe,
            "equipes": [{"id": e, "nome": nomes.get(e, e), "clima": clima.get(e, {})} for e in equipes],
            "programacoes": programacoes, "checkins": checkins, "producao": producao, "liberacoes": liberacoes,
            "soldas": soldas, "fotos": fotos, "ocorrencias": ocorrencias,
            "totais": {"assentado_m": metros["ASSENTADO"], "cadastro_m": metros["CADASTRO_CAMPO"], "reaterrado_m": metros["REATERRADO"],
                       "soldas": sum(s["quantidade"] for s in soldas), "fotos": len(fotos), "ocorrencias": len(ocorrencias),
                       "equipes": len(equipes)}}


def interferencias(conn, abertas=None, equipe=None, tipo=None, categoria=None, ini=None, fim=None, limite=300):
    """Interferências, impedimentos e não conformidades: as abertas primeiro, com o nome do trecho/nó e a contagem."""
    equipe = _equipe(conn, equipe)
    sql, args = "SELECT * FROM ocorrencias WHERE 1=1", []
    for cond, val in (("equipe_id=?", equipe), ("tipo=?", tipo), ("categoria=?", categoria),
                      ("data>=?", ini and _data(ini)), ("data<=?", fim and _data(fim))):
        if val:
            sql, args = f"{sql} AND {cond}", args + [val]
    base_sql, base_args = sql, list(args)
    if abertas is not None:
        sql += " AND resolvida_em IS NULL" if abertas else " AND resolvida_em IS NOT NULL"
    lista = _rows(conn.execute(sql + " ORDER BY resolvida_em IS NOT NULL, data DESC, id DESC LIMIT ?", args + [int(limite)]))
    for o in lista:
        o["alvo_nome"] = S.nome_alvo(conn, o["alvo_tipo"], o["alvo_id"])
    cont = conn.execute(f"""SELECT SUM(resolvida_em IS NULL), SUM(resolvida_em IS NOT NULL),
                                   SUM(resolvida_em IS NULL AND categoria='INTERFERENCIA')
                            FROM ({base_sql})""", base_args).fetchone()
    por_categoria = dict(conn.execute(f"SELECT categoria, COUNT(*) FROM ({base_sql}) WHERE resolvida_em IS NULL GROUP BY categoria",
                                      base_args).fetchall())
    return {"ocorrencias": lista, "categorias": S.CATEGORIAS_OCORRENCIA,
            "contagem": {"abertas": cont[0] or 0, "resolvidas": cont[1] or 0, "interferencias_abertas": cont[2] or 0,
                         "abertas_por_categoria": por_categoria}}
