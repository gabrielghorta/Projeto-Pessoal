"""Aceite prévio da Caesb, por lançamento (D-218). Não é o OK interno nem o BM oficial.

A Ankara envia PROPOSTO; o fiscal aceita, reduz ou recusa. O retrato assinado invalida o aceite
se a origem mudar. Depois do primeiro envio só a quantidade aceita segue ao pacote; sem envio,
o comportamento anterior é preservado. Toda transição é atômica e mantém eventos imutáveis.
O e-mail fica numa fila durável; o servidor só a despacha depois do commit da requisição.
"""
import hashlib
import json
import math

import acesso as A
import servicos as S
from regras import RegraViolada

AVISO = "Aceite prévio da fiscalização. O documento oficial é o BM assinado e protocolado."
CHAVE_ADM = "6.2_4.1.1"


def _json(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _medicao(conn, mid=None, aberta=False):
    m = S._one(conn, "SELECT id,numero,periodo_ini,periodo_fim,status,resumo_congelado FROM medicoes "
                      + ("WHERE id=?" if mid else "ORDER BY (status='ABERTA') DESC,numero DESC LIMIT 1"),
               *([mid] if mid else []))
    if not m:
        raise RegraViolada("Nenhuma medição disponível. A engenharia precisa abrir a medição do mês.")
    if aberta and m["status"] != "ABERTA":
        raise RegraViolada("Medição fechada: o aceite e o envio são somente leitura.")
    return m


def medicoes(conn):
    # Não expõe o selo/tipo de teste ao fiscal. D-56 continua aplicada no domínio.
    return S._rows(conn.execute("SELECT id,numero,periodo_ini,periodo_fim,status FROM medicoes ORDER BY numero DESC"))


def _autor(conn, por, permissao):
    u = A._usuario(conn, por)
    if not u or not u["ativo"]:
        raise A.AcessoNegado("Usuário ativo obrigatório.")
    A.exigir(A.publico(u), permissao)
    return u


def ativo(conn, mid):
    return conn.execute("SELECT 1 FROM fiscalizacao_envios WHERE medicao_id=? LIMIT 1", (mid,)).fetchone() is not None


def _origens(conn, mid):
    return S._rows(conn.execute("""SELECT l.*, b.item,b.item_bm,b.codigo_caesb,b.descricao,b.vigente,b.planilha,
        b.classificacao,b.preco_unitario FROM medicao_lancamentos l LEFT JOIN bm_itens b ON b.id=l.bm_item_id
        WHERE l.medicao_id=? ORDER BY l.id""", (mid,)))


def _retrato(conn, l):
    campos = ("id", "medicao_id", "gaveta", "servico", "bm_item_id", "item_novo_id", "alvo_tipo", "alvo_id",
              "unidade", "quantidade", "status", "restricao", "item", "classificacao", "preco_unitario", "vigente", "planilha")
    d = {k: l.get(k) for k in campos}
    if l.get("preco_congelado") is not None:
        d.update(preco_unitario=l["preco_congelado"], classificacao=l["classificacao_congelada"],
                 item=l["item_congelado"], vigente=1)
    if l["alvo_tipo"] == "APROPRIACAO":
        ap = S._one(conn, "SELECT data,quantidade,memoria_calculo,calculo_json,o_que_foi_feito,justificativa_tecnica "
                          "FROM apropriacoes WHERE id=?", l["alvo_id"])
        d["apropriacao"] = ap
    return d


def _assinatura(conn, l):
    return hashlib.sha256(_json(_retrato(conn, l)).encode()).hexdigest()


def _total(conn, ls, campo="quantidade"):
    return S._totalizar(conn, [(l["item"] or ("NOVO", l["item_novo_id"]), l["classificacao"], l["preco_unitario"],
                               l.get(campo) or 0) for l in ls])["total"]


def _evidencias(conn, l):
    if l["alvo_tipo"] == "APROPRIACAO":
        docs = S._rows(conn.execute("""SELECT d.id,d.nome_original nome,d.mime FROM apropriacao_documentos x
            JOIN documentos d ON d.id=x.documento_id WHERE x.apropriacao_id=? ORDER BY d.id""", (l["alvo_id"],)))
        for d in docs:
            d["url"] = f"/api/fiscalizacao/arquivo?linha={l['id']}&doc={d['id']}"
        ap = S._one(conn, "SELECT memoria_calculo,o_que_foi_feito,justificativa_tecnica FROM apropriacoes WHERE id=?", l["alvo_id"]) or {}
        return {"fotos": sum(str(d["mime"] or "").startswith("image/") for d in docs), "documentos": docs, **ap}
    n = conn.execute(f"SELECT COUNT(*) FROM fotos WHERE alvo_tipo=? AND alvo_id=? AND {S.FOTO_VALIDA}",
                     (l["alvo_tipo"], l["alvo_id"])).fetchone()[0]
    return {"fotos": n, "documentos": [], "ficha": f"/api/fiscalizacao/ficha?tipo={l['alvo_tipo']}&id={l['alvo_id']}"}


def linhas(conn, medicao_id=None, situacao=None, evidencias=True):
    m = _medicao(conn, medicao_id)
    congelado = json.loads(m["resumo_congelado"] or "{}").get("aceite_fiscalizacao")
    if m["status"] == "FECHADA" and congelado:
        out = congelado["linhas"]
    else:
        estados = {r["lancamento_id"]: dict(r) for r in conn.execute(
            "SELECT * FROM fiscalizacao_linhas WHERE medicao_id=?", (m["id"],))}
        out = []
        for origem in _origens(conn, m["id"]):
            l = dict(origem)
            if l["preco_congelado"] is not None:
                l.update(preco_unitario=l["preco_congelado"], classificacao=l["classificacao_congelada"], item=l["item_congelado"])
            if l["item"] == CHAVE_ADM:
                continue
            f = estados.get(l["id"])
            st = f["situacao"] if f else ("NAO_ENVIADA" if l["status"] == "PROPOSTO" else "PENDENTE")
            if f and f["assinatura"] != _assinatura(conn, origem):
                st = "ALTERADA"
            l.update(situacao=st, quantidade_enviada=f["quantidade_enviada"] if f else 0,
                     quantidade_aceita=(f["quantidade_aceita"] or 0) if f and st in ("ACEITA", "REDUZIDA") else 0,
                     motivo_fiscal=f["motivo"] if f else None, respondido_por=f["respondido_por"] if f else None,
                     respondido_em=f["respondido_em"] if f else None, envio_id=f["envio_id"] if f else None)
            l["alvo_nome"] = S.nome_alvo(conn, l["alvo_tipo"], l["alvo_id"]) if l["alvo_id"] else "Sem alvo"
            l["valor"] = _total(conn, [l])
            l["valor_aceito"] = _total(conn, [l], "quantidade_aceita")
            if f:
                retrato = json.loads(f["retrato"])
                l["valor_enviado"] = _total(conn, [dict(l, **{k: retrato[k] for k in ("item", "classificacao", "preco_unitario")})],
                                             "quantidade_enviada")
            else:
                l["valor_enviado"] = 0
            l["evidencias"] = _evidencias(conn, l) if evidencias else {}
            out.append(l)
    return [l for l in out if not situacao or l["situacao"] in str(situacao).split(",")]


def pronto_para_medir(conn, medicao_id=None):
    m = _medicao(conn, medicao_id)
    ls = linhas(conn, m["id"])
    return {"medicao": {k: v for k, v in m.items() if k != "resumo_congelado"},
            "prontas": sorted([l for l in ls if l["situacao"] == "NAO_ENVIADA" and l["planilha"] == "VERTICAL"
                               and l["vigente"] and l["preco_unitario"] is not None and m["status"] == "ABERTA"],
                              key=lambda l: (-l["valor"], l["id"])),
            "pendentes": [dict(l, motivo=l["motivo"] or "Item fora do BM vertical vigente: aguarde a inclusão no contrato.")
                          for l in ls if l["status"] == "PENDENTE" or not l["bm_item_id"] or l["planilha"] != "VERTICAL"
                          or not l["vigente"] or l["preco_unitario"] is None]}


def _ids(ids):
    if not isinstance(ids, list) or not ids or any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise RegraViolada("Selecione ao menos uma linha, sem repetição.")
    return ids


def _texto(s, obrigatorio=False):
    s = str(s or "").strip()
    if obrigatorio and not s:
        raise RegraViolada("Informe o motivo.")
    if len(s) > 4000:
        raise RegraViolada("Texto muito longo: limite de 4.000 caracteres.")
    return s or None


def _evento(conn, l, acao, qtd, motivo, u):
    conn.execute("""INSERT INTO fiscalizacao_eventos(lancamento_id,medicao_id,acao,quantidade,motivo,por,nome,perfil,em,retrato)
        VALUES (?,?,?,?,?,?,?,?,?,?)""", (l["id"], l["medicao_id"], acao, qtd, motivo, u["login"], u["nome"], u["perfil"],
                                         S._agora(), _json(_retrato(conn, l))))


def _enviar(conn, medicao_id, ids, por, obs, reenvio):
    u = _autor(conn, por, "fiscalizacao_enviar")
    ids = _ids(ids)
    obs = _texto(obs)
    with S.transacao(conn):
        m = _medicao(conn, medicao_id, aberta=True)
        atuais = {l["id"]: l for l in linhas(conn, m["id"], evidencias=False)}
        origens = {l["id"]: l for l in _origens(conn, m["id"])}
        selecionadas = []
        for lid in ids:
            l = atuais.get(lid)
            if not l:
                raise RegraViolada("Linha não pertence à medição, ou é administração local (calculada proporcionalmente).")
            if l["status"] != "PROPOSTO" or l["planilha"] != "VERTICAL" or not l["vigente"] or l["preco_unitario"] is None:
                raise RegraViolada("Só é possível enviar linha PROPOSTO do BM vertical vigente, com preço confirmado.")
            permitidas = ("RECUSADA", "REDUZIDA", "ALTERADA", "CANCELADA") if reenvio else ("NAO_ENVIADA",)
            if l["situacao"] not in permitidas:
                raise RegraViolada("Linha já enviada ou aguardando o fiscal. Use Reenviar após corrigir a resposta.")
            if not math.isfinite(l["quantidade"]) or l["quantidade"] <= 0:
                raise RegraViolada("A quantidade enviada deve ser maior que zero.")
            selecionadas.append(origens[lid])
        eid = conn.execute("INSERT INTO fiscalizacao_envios(medicao_id,enviado_por,enviado_em,obs) VALUES (?,?,?,?)",
                           (m["id"], u["login"], S._agora(), obs)).lastrowid
        for l in selecionadas:
            conn.execute("""INSERT INTO fiscalizacao_linhas(lancamento_id,medicao_id,situacao,envio_id,quantidade_enviada,
                assinatura,retrato,atualizado_em) VALUES (?,?,'AGUARDANDO',?,?,?,?,?) ON CONFLICT(lancamento_id) DO UPDATE SET
                situacao='AGUARDANDO',envio_id=excluded.envio_id,quantidade_enviada=excluded.quantidade_enviada,
                quantidade_aceita=NULL,assinatura=excluded.assinatura,retrato=excluded.retrato,motivo=NULL,
                respondido_por=NULL,respondido_em=NULL,atualizado_em=excluded.atualizado_em""",
                (l["id"], m["id"], eid, l["quantidade"], _assinatura(conn, l), _json(_retrato(conn, l)), S._agora()))
            _evento(conn, l, "REENVIADA" if reenvio else "ENVIADA", l["quantidade"], obs, u)
        from fiscalizacao_email import enfileirar
        status = enfileirar(conn, m["id"], eid, "ENVIO", "FISCALIZACAO", len(ids), _total(conn, selecionadas))
        return {"envio_id": eid, "linhas": len(ids), "email_situacao": status}


def enviar(conn, medicao_id, ids, por, obs=None):
    return _enviar(conn, medicao_id, ids, por, obs, False)


def reenviar(conn, lancamento_id, por, obs=None):
    l = S._one(conn, "SELECT medicao_id FROM medicao_lancamentos WHERE id=?", lancamento_id)
    if not l:
        raise RegraViolada("Lançamento não encontrado.")
    return _enviar(conn, l["medicao_id"], [lancamento_id], por, obs, True)


def responder(conn, itens, por):
    u = _autor(conn, por, "fiscalizacao_responder")
    if not isinstance(itens, list) or not itens or any(not isinstance(i, dict) for i in itens):
        raise RegraViolada("Selecione as linhas a responder.")
    _ids([i.get("lancamento_id") for i in itens])
    with S.transacao(conn):
        respostas = []
        for i in itens:
            f = S._one(conn, "SELECT * FROM fiscalizacao_linhas WHERE lancamento_id=?", i["lancamento_id"])
            if not f:
                raise RegraViolada("Linha ainda não enviada à fiscalização.")
            _medicao(conn, f["medicao_id"], aberta=True)
            l = next(l for l in _origens(conn, f["medicao_id"]) if l["id"] == i["lancamento_id"])
            if f["assinatura"] != _assinatura(conn, l):
                raise RegraViolada("A Ankara alterou esta linha depois do envio: aguarde o reenvio.")
            if f["situacao"] != "AGUARDANDO":
                raise RegraViolada("Esta linha não está aguardando resposta.")
            acao = i.get("acao")
            if acao not in ("ACEITAR", "REDUZIR", "RECUSAR"):
                raise RegraViolada("Resposta inválida.")
            motivo = _texto(i.get("motivo"), acao != "ACEITAR")
            qtd = f["quantidade_enviada"] if acao == "ACEITAR" else 0
            if acao == "REDUZIR":
                try:
                    qtd = float(i.get("quantidade"))
                except (TypeError, ValueError):
                    raise RegraViolada("Informe a quantidade aceita.") from None
                if isinstance(i.get("quantidade"), bool) or not math.isfinite(qtd) or not 0 < qtd < f["quantidade_enviada"]:
                    raise RegraViolada("A quantidade reduzida deve ser maior que zero e menor que a enviada.")
            respostas.append((l, {"ACEITAR": "ACEITA", "REDUZIR": "REDUZIDA", "RECUSAR": "RECUSADA"}[acao], qtd, motivo))
        por_med = {}
        for l, st, qtd, motivo in respostas:
            conn.execute("UPDATE fiscalizacao_linhas SET situacao=?,quantidade_aceita=?,motivo=?,respondido_por=?,"
                         "respondido_em=?,atualizado_em=? WHERE lancamento_id=?",
                         (st, qtd, motivo, u["login"], S._agora(), S._agora(), l["id"]))
            _evento(conn, l, st, qtd, motivo, u)
            por_med.setdefault(l["medicao_id"], []).append(dict(l, quantidade=qtd))
        from fiscalizacao_email import enfileirar
        for mid, ls in por_med.items():
            enfileirar(conn, mid, None, "RESPOSTA", "ENGENHARIA", len(ls), _total(conn, ls))
        return {"respondidas": len(respostas)}


def _voltar(conn, lancamento_id, motivo, por, cancelar):
    u = _autor(conn, por, "fiscalizacao_enviar" if cancelar else "fiscalizacao_responder")
    motivo = _texto(motivo, True)
    with S.transacao(conn):
        f = S._one(conn, "SELECT * FROM fiscalizacao_linhas WHERE lancamento_id=?", lancamento_id)
        if not f:
            raise RegraViolada("Linha não enviada.")
        _medicao(conn, f["medicao_id"], aberta=True)
        l = next(l for l in _origens(conn, f["medicao_id"]) if l["id"] == lancamento_id)
        if cancelar:
            if f["situacao"] != "AGUARDANDO":
                raise RegraViolada("Só é possível cancelar um envio aguardando resposta.")
        elif f["situacao"] not in ("ACEITA", "REDUZIDA", "RECUSADA") or f["respondido_por"] != u["login"]:
            raise RegraViolada("Você só pode reabrir uma resposta sua.")
        if not cancelar and f["assinatura"] != _assinatura(conn, l):
            raise RegraViolada("Linha em correção: aguarde o reenvio da Ankara.")
        conn.execute("UPDATE fiscalizacao_linhas SET situacao=?,quantidade_aceita=NULL,motivo=?,respondido_por=NULL,"
                     "respondido_em=NULL,atualizado_em=? WHERE lancamento_id=?",
                     ("CANCELADA" if cancelar else "AGUARDANDO", motivo, S._agora(), lancamento_id))
        _evento(conn, l, "CANCELADA" if cancelar else "REABERTA", None, motivo, u)
        from fiscalizacao_email import enfileirar
        enfileirar(conn, f["medicao_id"], None, "CANCELAMENTO" if cancelar else "REABERTURA",
                   "FISCALIZACAO" if cancelar else "ENGENHARIA", 1, 0)
    return {"ok": True}


def reabrir(conn, lancamento_id, motivo, por):
    return _voltar(conn, lancamento_id, motivo, por, False)


def cancelar(conn, lancamento_id, motivo, por):
    return _voltar(conn, lancamento_id, motivo, por, True)


def quantidades_aceitas(conn, medicao_id):
    return {l["id"]: l["quantidade_aceita"] for l in linhas(conn, medicao_id, evidencias=False)
            if l["situacao"] in ("ACEITA", "REDUZIDA")}


def efetivas(conn, medicao_id):
    """None = fluxo anterior intacto. Dicionário vazio = houve envio, mas nada aceito."""
    return quantidades_aceitas(conn, medicao_id) if ativo(conn, medicao_id) else None


def painel(conn, medicao_id=None):
    m = _medicao(conn, medicao_id)
    frozen = json.loads(m["resumo_congelado"] or "{}").get("aceite_fiscalizacao")
    if m["status"] == "FECHADA" and frozen:
        return frozen["painel"]
    ls = linhas(conn, m["id"], evidencias=False)
    def grupo(sts, campo="quantidade"):
        sel = [l for l in ls if l["situacao"] in sts]
        return {"linhas": len(sel), "valor": _total(conn, sel, campo)}
    cards = {"enviado": grupo({"AGUARDANDO", "ACEITA", "REDUZIDA", "RECUSADA", "ALTERADA"}, "quantidade_enviada"),
             "aguardando": grupo({"AGUARDANDO"}, "quantidade_enviada"),
             "aceito": grupo({"ACEITA", "REDUZIDA"}, "quantidade_aceita"),
             "recusado": grupo({"RECUSADA"}, "quantidade_enviada"), "nao_enviado": grupo({"NAO_ENVIADA", "CANCELADA"}),
             "pendente": grupo({"PENDENTE"}), "alterado": grupo({"ALTERADA"}, "quantidade_enviada")}
    reduzidas = [dict(l, diferenca=l["quantidade_enviada"] - l["quantidade_aceita"]) for l in ls if l["situacao"] == "REDUZIDA"]
    cards["reduzido"] = {"linhas": len(reduzidas), "valor": _total(conn, reduzidas, "diferenca")}
    itens = []
    for item in sorted({l["item"] or "Fora do BM" for l in ls}):
        il = [l for l in ls if (l["item"] or "Fora do BM") == item]
        enviadas = [l for l in il if l["envio_id"] and l["situacao"] != "CANCELADA"]
        qtd_env = sum(l["quantidade_enviada"] for l in enviadas)
        qtd_ok = sum(l["quantidade_aceita"] for l in il)
        itens.append({"item": item, "descricao": il[0]["descricao"], "unidade": il[0]["unidade"],
                      "enviado": qtd_env, "aceito": qtd_ok, "valor_enviado": _total(conn, enviadas, "quantidade_enviada"),
                      "valor_aceito": _total(conn, il, "quantidade_aceita"), "percentual": qtd_ok / qtd_env if qtd_env else 0})
    return {"medicao": {k: v for k, v in m.items() if k != "resumo_congelado"}, "aviso": AVISO,
            "controlada": ativo(conn, m["id"]), "totais": cards, "itens": itens}


def historico(conn, medicao_id=None):
    m = _medicao(conn, medicao_id)
    return S._rows(conn.execute("SELECT id,lancamento_id,acao,quantidade,motivo,por,nome,perfil,em "
                               "FROM fiscalizacao_eventos WHERE medicao_id=? ORDER BY id DESC", (m["id"],)))


def contador(conn, usuario):
    fiscal = usuario["perfil"] == "FISCALIZACAO"
    if not fiscal and "fiscalizacao_enviar" not in usuario["permissoes"]:
        return 0
    sts = {"AGUARDANDO"} if fiscal else {"RECUSADA", "REDUZIDA", "ALTERADA"}
    return sum(l["situacao"] in sts for m in conn.execute("SELECT id FROM medicoes WHERE status='ABERTA'")
               for l in linhas(conn, m[0], evidencias=False))


def assinatura_controle(conn, medicao_id):
    if not ativo(conn, medicao_id):
        return None
    return [(l["id"], l["situacao"], l["quantidade_aceita"], _assinatura(conn, l))
            for l in linhas(conn, medicao_id, evidencias=False)]


def congelar(conn, medicao_id):
    if not ativo(conn, medicao_id):
        return None
    return {"linhas": linhas(conn, medicao_id), "painel": painel(conn, medicao_id)}


def fora_do_aceite(conn, medicao_id):
    if not ativo(conn, medicao_id):
        return []
    out = []
    for l in linhas(conn, medicao_id, evidencias=False):
        if l["situacao"] == "ACEITA":
            continue
        q = (l["quantidade_enviada"] - l["quantidade_aceita"]) if l["situacao"] == "REDUZIDA" else l["quantidade"]
        out.append(dict(l, quantidade_fora=q, motivo_fora=l["motivo_fiscal"] or l["motivo"] or {
            "AGUARDANDO": "Aguardando resposta do fiscal.", "ALTERADA": "Alterada depois do envio: exige reenvio.",
            "NAO_ENVIADA": "Ainda não enviada.", "CANCELADA": "Envio cancelado."}.get(l["situacao"], "Fora do aceite.")))
    return out


def notas_do_alvo(conn, tipo, ref):
    """Só NS com vínculo registrado ao trecho. Não concede acesso à lista geral de notas."""
    a = S.alvo(conn, tipo, ref)
    if a["alvo_tipo"] != "TRECHO":
        return []  # não inventa vínculo com NS de rede para um nó
    ids = set()
    for s in conn.execute("SELECT ns_id,membros FROM ns_segmentos WHERE membros IS NOT NULL AND situacao IN ('AUTOMATICO','CONFIRMADO')"):
        if any(m.get("trecho_id") == a["id"] for m in json.loads(s["membros"])):
            ids.add(s["ns_id"])
    out = []
    for nid in sorted(ids):
        n = S._one(conn, "SELECT id,numero,data,tipo,pdf_id,croqui_id,planilha_id FROM notas_servico WHERE id=? AND status='REGISTRADA'", nid)
        if n:
            n["arquivos"] = [{"nome": qual, "url": f"/api/fiscalizacao/arquivo?tipo=TRECHO&alvo={a['id']}&ns={nid}&qual={qual}"}
                              for qual in ("pdf", "croqui", "planilha") if n[qual+"_id"]]
            out.append(n)
    return out


def ficha(conn, tipo, ref):
    """Ficha de leitura: obra, execução, verificação, fotos, NS e coordenadas. Sem estoque/RH/custos."""
    d = S.detalhe(conn, tipo, ref)
    campos = ("id", "nome", "alvo_tipo", "tipo", "frente_id", "pb", "numero", "tipo_elemento", "extensao_m",
              "de_mm", "material", "metodologia", "no_ini", "no_fim", "coordenadas", "execucao", "fotos_faltando",
              "fases_cadastro", "complementar", "intervalos", "cadastro", "retirado")
    out = {k: d[k] for k in campos if k in d}
    out["fotos"] = [{k: f.get(k) for k in ("id", "categoria", "arquivo", "data_hora", "validacao")}
                    for f in d.get("fotos", []) if f.get("validacao") not in ("INVALIDA", "ARQUIVO_AUSENTE")]
    out["notas"] = notas_do_alvo(conn, tipo, ref)
    return out


def documento(conn, q):
    """Autoriza anexo de AP enviada ou NS ligada ao alvo pedido, nunca NF/doc arbitrário."""
    if q.get("linha"):
        l = S._one(conn, "SELECT l.* FROM medicao_lancamentos l JOIN fiscalizacao_linhas f ON f.lancamento_id=l.id WHERE l.id=?",
                   int(q["linha"]))
        if not l or l["alvo_tipo"] != "APROPRIACAO":
            raise A.AcessoNegado("Evidência fora do escopo da fiscalização.")
        doc = S._one(conn, "SELECT d.* FROM documentos d JOIN apropriacao_documentos x ON x.documento_id=d.id "
                          "WHERE x.apropriacao_id=? AND d.id=?", l["alvo_id"], int(q.get("doc") or 0))
        if not doc:
            raise A.AcessoNegado("Documento não pertence à apropriação enviada.")
        return doc, doc["nome_original"] or "Evidência"
    nid = int(q.get("ns") or 0)
    permitidas = {n["id"] for n in notas_do_alvo(conn, q.get("tipo"), q.get("alvo"))}
    if nid not in permitidas:
        raise A.AcessoNegado("A nota de serviço não está vinculada a este alvo.")
    import notas_servico as NS
    _, doc, nome = NS.arquivo(conn, nid, q.get("qual") or "pdf")
    return doc, nome
