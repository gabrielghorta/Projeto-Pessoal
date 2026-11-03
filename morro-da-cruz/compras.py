"""Notas fiscais, inspeção e estoque. D-172 a D-175: solicitação independente e sem pedido de compra.

A entrega e a identificação por linha estão em recebimento.py; solicitar/decidir em solicitacoes.py.
Funções antigas de pedido/conferência permanecem para compatibilidade do histórico, sem rotas de criação.
Nota reconhecida e conferida pelo almoxarife não precisa de aprovação global. Desconhecida/corrigida
pode chegar antes de ser identificada pela engenharia; só entra no saldo depois da identificação.
Material recebido não é lançamento de medição. Quem digita não confere; quem pede não aprova.
"""
import base64
import hashlib
import os
import re
import unicodedata
from datetime import date

import imagens
import nfe
import planilha_xls
import regras as R
import servicos as S
from servicos import RegraViolada, _agora, _one, _rows, transacao

TOL = 1e-6
LIMITE_DOC = 20 * 1024 * 1024
TIPOS_DOC = {"NFE_XML", "NF_PDF", "NF_IMAGEM", "LAUDO", "ROMANEIO", "OUTRO", "NS_PDF", "NS_CROQUI", "NS_PLANILHA"}


# ------------------------------------------------------------------ documentos anexos
def _tipo_arquivo(dados):
    if dados[:5] == b"%PDF-":
        return "pdf", "application/pdf"
    if dados[:4] == b"PK\x03\x04" and b"xl/workbook.xml" in dados[:65536] + dados[-65536:]:
        return "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if planilha_xls.eh_xls(dados):
        return "xls", "application/vnd.ms-excel"
    ext, mime = imagens.tipo(dados)
    if ext in ("jpg", "png"):
        return ext, mime
    inicio = dados.lstrip()[:5]
    if inicio.startswith(b"<?xml") or inicio.startswith(b"<"):
        return "xml", "application/xml"
    return None, None


def guardar_documento(conn, tipo, conteudo_b64, nome_original, por, dir_docs):
    """Guarda o arquivo original (nomeado pelo SHA-256) e devolve o id. O mesmo arquivo já guardado é reaproveitado."""
    if tipo not in TIPOS_DOC:
        raise RegraViolada("Tipo de documento inválido.")
    try:
        dados = base64.b64decode(conteudo_b64 or "", validate=True)
    except (ValueError, TypeError):
        raise RegraViolada("Conteúdo do documento inválido.") from None
    if not dados or len(dados) > LIMITE_DOC:
        raise RegraViolada("Documento vazio ou maior que 20 MB.")
    ext, mime = _tipo_arquivo(dados)
    esperado = {"NFE_XML": ("xml",), "NF_PDF": ("pdf",), "NF_IMAGEM": ("jpg", "png"), "NS_PDF": ("pdf",),
                "NS_PLANILHA": ("xlsx", "xls")}.get(tipo, ("pdf", "jpg", "png"))
    if ext not in esperado:
        raise RegraViolada(f"Arquivo de {tipo} precisa ser {'/'.join(e.upper() for e in esperado)}.")
    if ext in ("jpg", "png"):
        try:
            imagens.validar(dados)
        except imagens.ImagemInvalida as e:
            raise RegraViolada(f"Imagem do documento recusada: {e}") from None
    h = hashlib.sha256(dados).hexdigest()
    ja = _one(conn, "SELECT id FROM documentos WHERE sha256=?", h)
    if ja:
        return ja["id"]
    os.makedirs(dir_docs, exist_ok=True)
    nome = f"{h}.{ext}"
    caminho = os.path.join(dir_docs, nome)
    if not os.path.exists(caminho):
        with open(caminho, "xb") as f:
            f.write(dados)
    return conn.execute(
        "INSERT INTO documentos(tipo,arquivo,nome_original,sha256,bytes,mime,enviado_por,enviado_em) VALUES (?,?,?,?,?,?,?,?)",
        (tipo, nome, nome_original, h, len(dados), mime, por, _agora())).lastrowid


# ------------------------------------------------------------------ fornecedores
def cnpj_valido(cnpj):
    d = re.sub(r"\D", "", str(cnpj or ""))
    if len(d) != 14 or len(set(d)) == 1:
        return False
    for n in (12, 13):
        pesos = list(range(n - 7, 1, -1)) + list(range(9, 1, -1))
        dv = 11 - sum(int(a) * b for a, b in zip(d[:n], pesos)) % 11
        if (0 if dv >= 10 else dv) != int(d[n]):
            return False
    return True


def cadastrar_fornecedor(conn, cnpj, nome, por, contato=None):
    d = re.sub(r"\D", "", str(cnpj or ""))
    if not cnpj_valido(d):
        raise RegraViolada("CNPJ inválido.")
    if not str(nome or "").strip():
        raise RegraViolada("Informe a razão social.")
    if _one(conn, "SELECT 1 FROM fornecedores WHERE cnpj=?", d):
        raise RegraViolada("Fornecedor com este CNPJ já cadastrado.")
    return conn.execute("INSERT INTO fornecedores(cnpj,nome,contato,criado_por,criado_em) VALUES (?,?,?,?,?)",
                        (d, nome.strip(), contato, por, _agora())).lastrowid


# ------------------------------------------------------------------ solicitação e pedido
def _material_compravel(conn, material_id):
    m = _one(conn, "SELECT * FROM materiais WHERE id=?", material_id)
    if not m:
        raise RegraViolada(f"Material '{material_id}' não cadastrado.")
    if m["propriedade"] == "CAESB":
        raise RegraViolada(f"{m['descricao']}: fornecido pela Caesb (retirada por romaneio), não é comprado.")
    return m


def abrir_solicitacao(conn, data, itens, motivo, solicitante, alvo_tipo=None, alvo_id=None):
    if not itens:
        raise RegraViolada("A solicitação precisa de ao menos um item.")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo/destino da compra.")
    ref = None
    if alvo_tipo and alvo_id:
        a = S.alvo(conn, alvo_tipo, alvo_id)
        alvo_tipo, ref = a["alvo_tipo"], a["id"]
    linhas = []
    for it in itens:
        _material_compravel(conn, it.get("material_id"))
        q = float(it.get("quantidade") or 0)
        if q <= 0:
            raise RegraViolada("Quantidade solicitada deve ser maior que zero.")
        linhas.append((it["material_id"], q))
    with transacao(conn):
        sid = conn.execute("INSERT INTO solicitacoes_compra(data,solicitante,motivo,alvo_tipo,alvo_id,criada_em) VALUES (?,?,?,?,?,?)",
                           (data, solicitante, motivo.strip(), alvo_tipo if ref else None, ref, _agora())).lastrowid
        for m, q in linhas:
            conn.execute("INSERT INTO solicitacao_itens(solicitacao_id,material_id,quantidade) VALUES (?,?,?)", (sid, m, q))
    return sid


def decidir_solicitacao(conn, solicitacao_id, aprovar, motivo, por):
    s_ = _one(conn, "SELECT * FROM solicitacoes_compra WHERE id=?", solicitacao_id)
    if not s_:
        raise RegraViolada("Solicitação não encontrada.")
    if s_["status"] != "ABERTA":
        raise RegraViolada(f"Solicitação já {s_['status'].lower()}.")
    if s_["solicitante"].lower() == str(por).lower():
        raise RegraViolada("Quem solicitou não aprova a própria solicitação.")
    if not aprovar and not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo da recusa.")
    conn.execute("UPDATE solicitacoes_compra SET status=?, decidida_por=?, decidida_em=?, decisao_motivo=? WHERE id=?",
                 ("APROVADA" if aprovar else "RECUSADA", por, _agora(), (motivo or "").strip() or None, solicitacao_id))


def cancelar_solicitacao(conn, solicitacao_id, motivo, por):
    s_ = _one(conn, "SELECT * FROM solicitacoes_compra WHERE id=?", solicitacao_id)
    if not s_ or s_["status"] not in ("ABERTA", "APROVADA"):
        raise RegraViolada("Só solicitação aberta ou aprovada pode ser cancelada.")
    if _one(conn, "SELECT 1 FROM pedidos_compra WHERE solicitacao_id=? AND status<>'CANCELADO'", solicitacao_id):
        raise RegraViolada("A solicitação já tem pedido: cancele o pedido antes.")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo do cancelamento.")
    conn.execute("UPDATE solicitacoes_compra SET status='CANCELADA', decidida_por=?, decidida_em=?, decisao_motivo=? WHERE id=?",
                 (por, _agora(), motivo.strip(), solicitacao_id))


def emitir_pedido(conn, numero, data, fornecedor_id, solicitacao_id, itens, por, prazo=None, faturamento_etapas=False):
    """Pedido a partir de solicitação APROVADA, sem pedir mais do que foi aprovado. Não altera nenhum saldo."""
    if not str(numero or "").strip():
        raise RegraViolada("Informe o número do pedido.")
    if _one(conn, "SELECT 1 FROM pedidos_compra WHERE numero=?", numero.strip()):
        raise RegraViolada("Já existe pedido com este número.")
    if not _one(conn, "SELECT 1 FROM fornecedores WHERE id=?", fornecedor_id):
        raise RegraViolada("Fornecedor não cadastrado.")
    s_ = _one(conn, "SELECT * FROM solicitacoes_compra WHERE id=?", solicitacao_id)
    if not s_ or s_["status"] != "APROVADA":
        raise RegraViolada("O pedido precisa de uma solicitação APROVADA.")
    aprovado = {r["material_id"]: r["q"] for r in _rows(conn.execute(
        "SELECT material_id, SUM(quantidade) q FROM solicitacao_itens WHERE solicitacao_id=? GROUP BY material_id", (solicitacao_id,)))}
    ja = {r["material_id"]: r["q"] for r in _rows(conn.execute(
        """SELECT pi.material_id, SUM(pi.quantidade) q FROM pedido_itens pi JOIN pedidos_compra p ON p.id=pi.pedido_id
           WHERE p.solicitacao_id=? AND p.status<>'CANCELADO' GROUP BY pi.material_id""", (solicitacao_id,)))}
    if not itens:
        raise RegraViolada("O pedido precisa de ao menos um item.")
    soma = {}
    for it in itens:
        q, vu = float(it.get("quantidade") or 0), float(it.get("valor_unitario") or 0)
        if q <= 0 or vu < 0:
            raise RegraViolada("Quantidade > 0 e valor unitário ≥ 0 em cada item.")
        soma[it["material_id"]] = soma.get(it["material_id"], 0) + q
    for m, q in soma.items():
        if m not in aprovado:
            raise RegraViolada(f"{m} não está na solicitação aprovada.")
        if q + ja.get(m, 0) > aprovado[m] + TOL:
            raise RegraViolada(f"{m}: o pedido ({q:g}) excede o saldo aprovado na solicitação ({aprovado[m] - ja.get(m, 0):g}).")
    with transacao(conn):
        pid = conn.execute(
            """INSERT INTO pedidos_compra(numero,data,fornecedor_id,solicitacao_id,prazo,faturamento_etapas,emitido_por,emitido_em)
               VALUES (?,?,?,?,?,?,?,?)""",
            (numero.strip(), data, fornecedor_id, solicitacao_id, prazo, 1 if faturamento_etapas else 0, por, _agora())).lastrowid
        for it in itens:
            conn.execute("INSERT INTO pedido_itens(pedido_id,material_id,quantidade,valor_unitario) VALUES (?,?,?,?)",
                         (pid, it["material_id"], float(it["quantidade"]), float(it.get("valor_unitario") or 0)))
    return pid


def _nf_ativa():
    return "nf.status NOT IN ('CANCELADA','A_CONFERIR')"


def situacao_pedido(conn, pedido_id):
    """Por item: pedido, faturado (NF conferida), entregue, em quarentena, aceito, recusado, devolvido e pendente de
    entrega = pedido − (aceito − devolvido) − em quarentena."""
    p = _one(conn, "SELECT p.*, f.nome fornecedor, f.cnpj FROM pedidos_compra p JOIN fornecedores f ON f.id=p.fornecedor_id WHERE p.id=?",
             pedido_id)
    if not p:
        raise RegraViolada("Pedido não encontrado.")
    p["itens"] = []
    for it in _rows(conn.execute("SELECT * FROM pedido_itens WHERE pedido_id=? ORDER BY id", (pedido_id,))):
        q = lambda sql: conn.execute(sql, (it["id"],)).fetchone()[0] or 0
        fat = q(f"SELECT SUM(ni.quantidade) FROM nf_itens ni JOIN notas_fiscais nf ON nf.id=ni.nf_id WHERE ni.pedido_item_id=? AND {_nf_ativa()}")
        ent = q("SELECT SUM(ri.quantidade) FROM recebimento_itens ri JOIN nf_itens ni ON ni.id=ri.nf_item_id WHERE ni.pedido_item_id=?")
        quar = q("""SELECT SUM(ri.quantidade) FROM recebimento_itens ri JOIN nf_itens ni ON ni.id=ri.nf_item_id
                    WHERE ni.pedido_item_id=? AND ri.id NOT IN (SELECT recebimento_item_id FROM inspecoes)""")
        ace = q("""SELECT SUM(i.aceito) FROM inspecoes i JOIN recebimento_itens ri ON ri.id=i.recebimento_item_id
                   JOIN nf_itens ni ON ni.id=ri.nf_item_id WHERE ni.pedido_item_id=?""")
        rec = q("""SELECT SUM(i.recusado) FROM inspecoes i JOIN recebimento_itens ri ON ri.id=i.recebimento_item_id
                   JOIN nf_itens ni ON ni.id=ri.nf_item_id WHERE ni.pedido_item_id=?""")
        dev = q("SELECT SUM(d.quantidade) FROM devolucoes_fornecedor d JOIN nf_itens ni ON ni.id=d.nf_item_id WHERE ni.pedido_item_id=? AND d.movimento_id NOT IN (SELECT movimento_id FROM estornos)")
        p["itens"].append({**it, "faturado": fat, "entregue": ent, "quarentena": quar, "aceito": ace, "recusado": rec,
                           "devolvido": dev, "pendente_entrega": round(max(it["quantidade"] - (ace - dev) - quar, 0), 6),
                           "a_faturar": round(_a_faturar(conn, it["id"]), 6)})
    p["atendido"] = all(i["pendente_entrega"] <= TOL for i in p["itens"])
    return p


def cancelar_pedido(conn, pedido_id, motivo, por):
    p = _one(conn, "SELECT * FROM pedidos_compra WHERE id=?", pedido_id)
    if not p or p["status"] != "EMITIDO":
        raise RegraViolada("Só pedido emitido pode ser cancelado.")
    if _one(conn, f"SELECT 1 FROM notas_fiscais nf WHERE pedido_id=? AND {_nf_ativa()}", pedido_id):
        raise RegraViolada("O pedido já tem nota fiscal conferida: encerre o saldo em vez de cancelar.")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo do cancelamento.")
    conn.execute("UPDATE pedidos_compra SET status='CANCELADO', encerrado_motivo=? WHERE id=?", (f"{motivo.strip()} ({por})", pedido_id))


def encerrar_pedido(conn, pedido_id, motivo, por):
    """Encerra o saldo que não será entregue (o já recebido continua valendo)."""
    p = _one(conn, "SELECT * FROM pedidos_compra WHERE id=?", pedido_id)
    if not p or p["status"] != "EMITIDO":
        raise RegraViolada("Só pedido emitido pode ser encerrado.")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo do encerramento.")
    conn.execute("UPDATE pedidos_compra SET status='ENCERRADO', encerrado_motivo=? WHERE id=?", (f"{motivo.strip()} ({por})", pedido_id))


# ------------------------------------------------------------------ nota fiscal: importação, digitação e conferência
def _fornecedor_cnpj(conn, cnpj):
    f = _one(conn, "SELECT * FROM fornecedores WHERE cnpj=?", re.sub(r"\D", "", cnpj or ""))
    if not f:
        raise RegraViolada(f"Emitente CNPJ {cnpj} não está cadastrado como fornecedor: cadastre-o antes (compras).")
    return f


def importar_nfe_xml(conn, conteudo_b64, nome_arquivo, por, cadastrar=False):
    """XML da NF-e → nota A CONFERIR com as linhas como vieram. Nenhum movimento é criado. Emitente sem cadastro: devolve
    {"fornecedor_novo": {cnpj, nome}} e nada grava; com cadastrar=True, o fornecedor é cadastrado pelo CNPJ e pela razão
    social do próprio XML (o almoxarife recebe nota de quem ainda não está em Compras)."""
    try:
        dados = base64.b64decode(conteudo_b64 or "", validate=True)
    except (ValueError, TypeError):
        raise RegraViolada("Conteúdo do XML inválido.") from None
    n = nfe.ler(dados)
    if _one(conn, "SELECT id FROM notas_fiscais WHERE chave_nfe=? AND status<>'CANCELADA'", n["chave"]):
        raise RegraViolada(f"NF-e {n['numero']} (chave {n['chave']}) já importada.")
    f = _one(conn, "SELECT * FROM fornecedores WHERE cnpj=?", re.sub(r"\D", "", n["emitente_cnpj"] or ""))
    if not f and not cadastrar:
        return {"fornecedor_novo": {"cnpj": n["emitente_cnpj"], "nome": n["emitente_nome"]}, "numero": n["numero"]}
    if f and _nf_repetida(conn, f["id"], n["numero"], n.get("serie")):
        raise RegraViolada(f"A NF {n['numero']} deste fornecedor já foi registrada (digitada ou por outro XML).")
    with transacao(conn):
        if not f:
            f = _one(conn, "SELECT * FROM fornecedores WHERE id=?", cadastrar_fornecedor(conn, n["emitente_cnpj"], n["emitente_nome"], por))
        doc = guardar_documento(conn, "NFE_XML", conteudo_b64, nome_arquivo, por, documento_dir(conn))
        nf_id = conn.execute(
            """INSERT INTO notas_fiscais(numero,chave_nfe,serie,fornecedor,fornecedor_id,data_emissao,valor_total,origem,
                 documento_id,status,registrada_por,registrada_em) VALUES (?,?,?,?,?,?,?, 'XML', ?, 'A_CONFERIR', ?, ?)""",
            (n["numero"], n["chave"], n["serie"], f["nome"], f["id"], n["data_emissao"], n["valor_total"], doc, por, _agora())).lastrowid
        for it in n["itens"]:
            conn.execute(
                """INSERT INTO nf_linhas(nf_id,n_item,codigo,descricao,ncm,cfop,unidade,quantidade,valor_unitario,valor_total)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (nf_id, it["n_item"], it["codigo"], it["descricao"], it["ncm"], it["cfop"], it["unidade"], it["quantidade"],
                 it["valor_unitario"], it["valor_total"]))
    return {"nf_id": nf_id, "numero": n["numero"], "itens": len(n["itens"]), "autorizacao": n["autorizacao"],
            "fornecedor": f["nome"]}


def _data_iso(data, o_que):
    try:
        return date.fromisoformat(str(data)[:10]).isoformat()
    except ValueError:
        raise RegraViolada(f"{o_que}: data inválida ({data}).") from None


def _nf_repetida(conn, fornecedor_id, numero, serie):
    """A mesma nota do mesmo fornecedor (número e série, sem os zeros da frente), mesmo sem a chave de acesso."""
    def limpo(x):
        return str(x or "").strip().lstrip("0") or "0"
    for r in conn.execute("SELECT id, numero, serie FROM notas_fiscais WHERE fornecedor_id=? AND status<>'CANCELADA'",
                          (fornecedor_id,)):
        if limpo(r["numero"]) == limpo(numero) and (not r["serie"] or not serie or limpo(r["serie"]) == limpo(serie)):
            return r["id"]
    return None


def registrar_nf_digitada(conn, numero, fornecedor_id, data_emissao, linhas, por, documento_b64, documento_tipo,
                          nome_arquivo=None, serie=None, chave=None, valor_total=None):
    """Dados digitados a partir do PDF/imagem da NF (anexo obrigatório). Fica A CONFERIR por OUTRA pessoa."""
    if not str(numero or "").strip() or not data_emissao:
        raise RegraViolada("Informe número e data de emissão.")
    if not _one(conn, "SELECT 1 FROM fornecedores WHERE id=?", fornecedor_id):
        raise RegraViolada("Fornecedor não cadastrado.")
    if chave:
        chave = re.sub(r"\D", "", chave)
        if not nfe.chave_valida(chave):
            raise RegraViolada("Chave de acesso inválida.")
        if _one(conn, "SELECT 1 FROM notas_fiscais WHERE chave_nfe=? AND status<>'CANCELADA'", chave):
            raise RegraViolada("NF com esta chave já registrada.")
    if _nf_repetida(conn, fornecedor_id, numero, serie):
        raise RegraViolada(f"A NF {str(numero).strip()} deste fornecedor já está registrada (cancele a anterior para lançar de novo).")
    if documento_tipo not in ("NF_PDF", "NF_IMAGEM") or not documento_b64:
        raise RegraViolada("Anexe o PDF ou a imagem da nota fiscal: os dados digitados são conferidos contra ele.")
    if not linhas:
        raise RegraViolada("Informe as linhas da nota.")
    lin = []
    for k, li in enumerate(linhas, 1):
        q, vu = float(li.get("quantidade") or 0), float(li.get("valor_unitario") or 0)
        if q <= 0 or vu < 0 or not str(li.get("descricao") or "").strip() or not str(li.get("unidade") or "").strip():
            raise RegraViolada(f"Linha {k}: descrição, unidade, quantidade > 0 e valor ≥ 0.")
        lin.append((k, li.get("codigo"), li["descricao"].strip(), li["unidade"].strip(), q, vu, round(q * vu, 2)))
    with transacao(conn):
        doc = guardar_documento(conn, documento_tipo, documento_b64, nome_arquivo, por, documento_dir(conn))
        f = _one(conn, "SELECT nome FROM fornecedores WHERE id=?", fornecedor_id)
        nf_id = conn.execute(
            """INSERT INTO notas_fiscais(numero,chave_nfe,serie,fornecedor,fornecedor_id,data_emissao,valor_total,origem,
                 documento_id,status,registrada_por,registrada_em) VALUES (?,?,?,?,?,?,?, 'DIGITADA', ?, 'A_CONFERIR', ?, ?)""",
            (numero.strip(), chave, serie, f["nome"], fornecedor_id, data_emissao,
             float(valor_total) if valor_total not in (None, "") else round(sum(x[6] for x in lin), 2), doc, por, _agora())).lastrowid
        for k, cod, desc, un, q, vu, vt in lin:
            conn.execute("""INSERT INTO nf_linhas(nf_id,n_item,codigo,descricao,unidade,quantidade,valor_unitario,valor_total)
                            VALUES (?,?,?,?,?,?,?,?)""", (nf_id, k, cod, desc, un, q, vu, vt))
    return nf_id


def _palavras(texto):
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z]+|\d+", t)                  # "DE63" → de, 63


def _medidas(ps):
    """Os números que são medida (DE, bitola, comprimento…): o da classe do material (PE 100, PE-80) e o do SDR não contam,
    porque o fornecedor escreve e o cadastro da obra não ("TUBO PEAD PE100 DE63 SDR17" é o tubo DE63)."""
    return {p for i, p in enumerate(ps) if p.isdigit() and not (i and ps[i - 1] in ("pe", "sdr"))}


def _bitola_tubo_pead(ps):
    """O DE do tubo de PEAD escrito na linha (DE63, DE 63, DE = 63 mm), ou None se a linha não é tubo de PEAD."""
    if "tubo" not in ps or not ({"pead", "polietileno"} & set(ps)):
        return None
    return next((ps[i + 1] for i, p in enumerate(ps[:-1]) if p == "de" and ps[i + 1].isdigit()), None)


def sugerir_materiais(conn, nf_id):
    """O material de cada linha da nota, e o porquê. Nada é gravado aqui. Ninguém escolhe material na tela do
    almoxarife (D-171): o que esta função reconhece ele só confere e marca; o que ela não reconhece fica "faltando a
    confirmação" em Compras e notas, com os candidatos mais prováveis para marcar.
    0. a linha já foi confirmada em Compras e notas (confirmar_linhas);
    1. o código do produto é o id de um material (ex.: 5.1_1.14.15);
    2. a mesma linha (código ou descrição) já foi conferida ou confirmada numa nota anterior deste fornecedor;
    3. tubo de PEAD da Caesb (a linha ou o emitente diz Caesb): o tubo CAESB-PEAD-DE<n> pela bitola;
    4. a descrição bate com a de um material: as mesmas medidas (_medidas) e a maior parte das palavras; empate entre
       dois materiais não sugere nada.
    Material com unidade diferente da da nota e sem fator conhecido também fica faltando a confirmação (com ele como
    primeiro candidato): só quem confirma diz quantos vêm em cada unidade da nota."""
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", nf_id)
    if not nf:
        raise RegraViolada("Nota não encontrada.")
    mats = {r["id"]: r for r in _rows(conn.execute("SELECT id, descricao, unidade, propriedade FROM materiais"))}
    nota_caesb = "caesb" in _palavras(nf["fornecedor"])
    cand = []
    for m in mats.values():
        ps = _palavras(m["descricao"])
        cand.append((m["id"], {p for p in ps if not p.isdigit()}, _medidas(ps)))
    hist_cod, hist_desc = {}, {}                       # (material, fator, unidade) da linha igual numa nota anterior
    for cod, desc, mid, fat, un in conn.execute(
            """SELECT l.codigo, l.descricao, l.material_id, l.fator, l.unidade FROM nf_linhas l JOIN notas_fiscais n ON n.id=l.nf_id
               WHERE n.fornecedor_id=? AND n.id<>? AND n.status<>'CANCELADA' AND l.material_id IS NOT NULL AND l.id NOT IN (SELECT linha_id FROM nf_confirmacoes WHERE pendente=1) ORDER BY l.id""",
            (nf["fornecedor_id"], nf_id)):
        if cod:
            hist_cod[cod] = (mid, fat, un)
        hist_desc[" ".join(_palavras(desc))] = (mid, fat, un)
    out = []
    for li in _rows(conn.execute("SELECT * FROM nf_linhas WHERE nf_id=? ORDER BY n_item", (nf_id,))):
        mid, motivo, desc = None, None, " ".join(_palavras(li["descricao"]))
        ps = _palavras(li["descricao"])
        pal, num = {p for p in ps if not p.isdigit()}, _medidas(ps)
        bitola = _bitola_tubo_pead(ps)
        fator = None
        if li["material_id"] in mats or li["fora_do_estoque"]:                  # 0. confirmada em Compras e notas
            mid, motivo, fator = li["material_id"], "confirmado em Compras e notas", li["fator"]
        elif li["codigo"] in mats:
            mid, motivo = li["codigo"], "código do produto"
        elif (hist_cod.get(li["codigo"]) or hist_desc.get(desc) or (None,))[0] in mats:
            (mid, fator, un_ant), motivo = hist_cod.get(li["codigo"]) or hist_desc[desc], "como na nota anterior deste fornecedor"
            if R.normalizar_unidade(un_ant) != R.normalizar_unidade(li["unidade"]):
                fator = None                           # o fator da nota anterior era de outra unidade (ex.: M × BR)
        elif bitola and (nota_caesb or "caesb" in pal) and f"CAESB-PEAD-DE{bitola}" in mats:
            mid, motivo = f"CAESB-PEAD-DE{bitola}", "tubo da Caesb pela bitola"
        else:
            notas = sorted(((len(pal & mp) / len(pal), i) for i, mp, mn in cand if pal and mn == num and len(pal & mp) / len(pal) >= 0.6),
                           reverse=True)
            if notas and (len(notas) == 1 or notas[0][0] > notas[1][0]):
                mid, motivo = notas[0][1], "pela descrição"
        pendente = _one(conn, "SELECT 1 FROM nf_confirmacoes WHERE linha_id=? AND pendente=1", li["id"])
        if pendente:
            mid, motivo, fator = None, "aguardando confirmação da engenharia", None
        m = mats.get(mid)
        fora = bool(li["fora_do_estoque"]) if motivo == "confirmado em Compras e notas" else (not mid and _frete_ou_servico(li))
        if pendente:
            fora = False
        mesma = m and R.normalizar_unidade(li["unidade"]) == R.normalizar_unidade(m["unidade"])
        candidatos = []
        if m and not mesma and not fator:              # unidade diferente sem fator: quem confirma diz o fator
            candidatos = [{"material_id": mid, "descricao": m["descricao"], "unidade": m["unidade"], "caesb": m["propriedade"] == "CAESB"}]
            mid = m = None
            motivo = "unidade diferente da do material: falta dizer quantos vêm em cada"
        elif not mid and not fora:                     # para quem confirma: os mais prováveis, para só marcar
            pontos = []
            for i, mp, mn in cand:
                if mats[i]["propriedade"] == "CAESB" and not (nota_caesb or "caesb" in pal):
                    continue                           # tubo da Caesb só na nota da Caesb
                s = len(pal & mp) / len(pal) if pal else 0
                s *= (0.5 + 0.5 * len(num & mn) / len(num)) if num else 1
                if s >= 0.35:
                    pontos.append((s, i))
            candidatos = [{"material_id": i, "descricao": mats[i]["descricao"], "unidade": mats[i]["unidade"],
                           "caesb": mats[i]["propriedade"] == "CAESB"} for _, i in sorted(pontos, reverse=True)[:3]]
        out.append({"linha_id": li["id"], "material_id": mid, "motivo": "frete ou serviço: fora do estoque" if fora else motivo,
                    "caesb": bool(m and m["propriedade"] == "CAESB"), "fora_do_estoque": fora,
                    "descricao_material": m["descricao"] if m else None,
                    "fator": 1.0 if mesma else fator, "candidatos": candidatos})
    return out


def confirmar_linhas(conn, nf_id, linhas, por):
    from recebimento import confirmar
    return confirmar(conn, nf_id, linhas, por)


_NAO_MATERIAL = {"frete", "fretes", "servico", "servicos", "taxa", "taxas", "seguro", "despesa", "despesas"}


def _frete_ou_servico(linha):
    """Linha que não é material (frete, serviço, taxa, seguro): fica fora do estoque no recebimento num toque."""
    ps = _palavras(linha["descricao"])
    return R.normalizar_unidade(linha["unidade"]) in ("SV", "SERV") or bool(ps and ps[0] in _NAO_MATERIAL)


def documento_dir(conn):
    """<pasta do banco>/documentos — a mesma que o backup copia e confere (ao lado de <pasta do banco>/fotos)."""
    caminho = conn.execute("PRAGMA database_list").fetchone()[2]
    if not caminho:
        raise RegraViolada("Banco em memória não guarda documentos.")
    return os.path.join(os.path.dirname(os.path.abspath(caminho)), "documentos")


def _a_faturar(conn, pedido_item_id, ignorar_nf=None):
    """Saldo do item do pedido ainda não faturado: pedido − Σ notas conferidas + recusado + devolvido (o que voltou ao
    fornecedor pode ser reposto por outra nota)."""
    it = _one(conn, "SELECT * FROM pedido_itens WHERE id=?", pedido_item_id)
    ja = conn.execute(f"""SELECT COALESCE(SUM(ni.quantidade),0) FROM nf_itens ni JOIN notas_fiscais nf ON nf.id=ni.nf_id
                          WHERE ni.pedido_item_id=? AND {_nf_ativa()} AND nf.id<>?""", (pedido_item_id, ignorar_nf or -1)).fetchone()[0]
    voltou = conn.execute(
        """SELECT COALESCE((SELECT SUM(i.recusado) FROM inspecoes i JOIN recebimento_itens ri ON ri.id=i.recebimento_item_id
                             JOIN nf_itens ni ON ni.id=ri.nf_item_id WHERE ni.pedido_item_id=?),0)
                + COALESCE((SELECT SUM(d.quantidade) FROM devolucoes_fornecedor d JOIN nf_itens ni ON ni.id=d.nf_item_id
                             WHERE ni.pedido_item_id=? AND d.movimento_id NOT IN (SELECT movimento_id FROM estornos)),0)""",
        (pedido_item_id, pedido_item_id)).fetchone()[0]
    return it["quantidade"] - ja + voltou


def conferir_nf(conn, nf_id, pedido_id, linhas_conf, por, so_fora_do_estoque=False):
    """De-para de cada linha da NF: material + fator de conversão (quantidade no material = quantidade da NF × fator)
    + item do pedido, ou 'fora do estoque' (frete, serviço). Unidade diferente exige fator declarado; mesma unidade,
    fator 1. Com pedido: não fatura além do pedido (o item do pedido com o mesmo material é achado sozinho, se for um só).
    Compatibilidade histórica: sem pedido fica marcado, mas não bloqueia o saldo na v22. Linha de
    tubo da Caesb (remessa) não é compra: vira romaneio Caesb na entrega. Só depois da conferência a nota aceita entregas.
    Nenhuma linha para o estoque (D-169): recusada, porque a nota ficava "a receber" sem nada a receber; com
    so_fora_do_estoque (a pessoa confirmou que a nota é só de frete ou serviço) ela é encerrada na hora."""
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", nf_id)
    if not nf or nf["status"] != "A_CONFERIR":
        raise RegraViolada("Só nota A CONFERIR pode ser conferida.")
    if nf["origem"] == "DIGITADA" and str(nf["registrada_por"]).lower() == str(por).lower():
        raise RegraViolada("Quem digitou os dados da nota não pode conferi-los.")
    p = None
    if pedido_id:
        p = _one(conn, "SELECT * FROM pedidos_compra WHERE id=?", pedido_id)
        if not p or p["status"] != "EMITIDO":
            raise RegraViolada("Vincule a nota a um pedido emitido (ou confira sem pedido).")
        if p["fornecedor_id"] != nf["fornecedor_id"]:
            raise RegraViolada("O fornecedor do pedido é diferente do emitente da nota.")
    linhas = {r["id"]: r for r in _rows(conn.execute("SELECT * FROM nf_linhas WHERE nf_id=?", (nf_id,)))}
    conf = {int(c["linha_id"]): c for c in linhas_conf or []}
    if set(conf) != set(linhas):
        raise RegraViolada(f"Confira todas as linhas da nota ({len(linhas)}): cada uma vai para um material ou fica fora do estoque.")
    itens_pedido = {r["id"]: r for r in _rows(conn.execute("SELECT * FROM pedido_itens WHERE pedido_id=?", (pedido_id,)))} if p else {}
    plano, por_item = [], {}
    for lid, li in sorted(linhas.items()):
        c = conf[lid]
        if c.get("fora_do_estoque"):
            plano.append((lid, None, None, None, None, None, False))
            continue
        m = _one(conn, "SELECT * FROM materiais WHERE id=?", c.get("material_id"))
        if not m:
            raise RegraViolada(f"Linha {li['n_item']}: material '{c.get('material_id')}' não cadastrado.")
        caesb = m["propriedade"] == "CAESB"
        pi = None
        if p and not caesb:
            pi = itens_pedido.get(int(c.get("pedido_item_id") or 0))
            if not pi:                                # o item do pedido com o mesmo material, se for um só
                mesmos = [x for x in itens_pedido.values() if x["material_id"] == m["id"]]
                pi = mesmos[0] if len(mesmos) == 1 else None
            if not pi or pi["material_id"] != m["id"]:
                raise RegraViolada(f"Linha {li['n_item']}: escolha o item do pedido com o mesmo material ({m['id']}).")
        mesma = R.normalizar_unidade(li["unidade"]) == R.normalizar_unidade(m["unidade"])
        fator = c.get("fator")
        if mesma:
            if fator not in (None, "", 1, 1.0, "1"):
                raise RegraViolada(f"Linha {li['n_item']}: mesma unidade ({m['unidade']}) usa fator 1.")
            fator = 1.0
        else:
            try:
                fator = float(fator)
            except (TypeError, ValueError):
                fator = 0
            if fator <= 0:
                raise RegraViolada(f"Linha {li['n_item']}: a nota está em {li['unidade']} e o material em {m['unidade']}: "
                                   "declare o fator de conversão.")
        q = round(li["quantidade"] * fator, 6)
        if pi:
            por_item[pi["id"]] = por_item.get(pi["id"], 0) + q
        plano.append((lid, m["id"], fator, pi["id"] if pi else None, q, li["valor_unitario"] / fator, caesb))
    for piid, q in por_item.items():
        saldo = _a_faturar(conn, piid, nf_id)
        if q > saldo + TOL:
            raise RegraViolada(f"Item do pedido {itens_pedido[piid]['material_id']}: a nota ({q:g}) excede o saldo do pedido ({saldo:g}).")
    so_fora = not any(mid for _, mid, _, _, _, _, _ in plano)
    if so_fora and not so_fora_do_estoque:
        raise RegraViolada("Nenhuma linha vai para o estoque: escolha o material das linhas. Se a nota é só de frete ou "
                           "serviço, confirme (ela é encerrada sem nada a receber).")
    sem_pedido = 1 if not p and any(mid and not caesb for _, mid, _, _, _, _, caesb in plano) else 0
    with transacao(conn):
        for lid, mid, fator, piid, q, vu, caesb in plano:
            conn.execute("UPDATE nf_linhas SET material_id=?, fator=?, pedido_item_id=?, fora_do_estoque=?, romaneio_caesb=? WHERE id=?",
                         (mid, fator, piid, 1 if mid is None else 0, 1 if caesb else 0, lid))
            if mid:
                conn.execute("INSERT INTO nf_itens(nf_id,material_id,quantidade,valor_unitario,pedido_item_id,linha_id) VALUES (?,?,?,?,?,?)",
                             (nf_id, mid, q, vu, piid, lid))
        conn.execute("UPDATE notas_fiscais SET status=?, pedido_id=?, sem_pedido=?, conferida_por=?, conferida_em=? WHERE id=?",
                     ("ENCERRADA" if so_fora else "CONFERIDA", p["id"] if p else None, sem_pedido, por, _agora(), nf_id))
    return {"sem_pedido": bool(sem_pedido), **({"encerrada": True} if so_fora else {})}


def refazer_conferencia(conn, nf_id, por):
    """A nota que ficou "a receber" sem nada a receber (conferida com todas as linhas fora do estoque, antes da D-169)
    volta a "a conferir", com as linhas como vieram. Só ela: a conferida com material segue o caminho de sempre
    (receber, ou cancelar e importar de novo)."""
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", nf_id)
    if not nf or nf["status"] != "CONFERIDA":
        raise RegraViolada("Só nota conferida volta para a conferência.")
    if _one(conn, "SELECT 1 FROM nf_itens WHERE nf_id=?", nf_id) or _one(conn, "SELECT 1 FROM recebimentos WHERE nf_id=?", nf_id):
        raise RegraViolada("A nota já tem material conferido ou entregue: receba por ela, ou cancele e importe de novo.")
    with transacao(conn):
        conn.execute("""UPDATE nf_linhas SET material_id=NULL, fator=NULL, pedido_item_id=NULL, fora_do_estoque=0, romaneio_caesb=0
                        WHERE nf_id=?""", (nf_id,))
        conn.execute("""UPDATE notas_fiscais SET status='A_CONFERIR', pedido_id=NULL, sem_pedido=0, conferida_por=NULL,
                        conferida_em=NULL WHERE id=?""", (nf_id,))
    return {"ok": True, "por": por}


def cancelar_nf(conn, nf_id, motivo, por):
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", nf_id)
    if not nf or nf["status"] not in ("A_CONFERIR", "CONFERIDA"):
        raise RegraViolada("Só nota a conferir ou conferida (sem entregas) pode ser cancelada.")
    if _one(conn, "SELECT 1 FROM recebimentos WHERE nf_id=?", nf_id):
        raise RegraViolada("A nota já tem entrega registrada: use a devolução ao fornecedor.")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo do cancelamento.")
    conn.execute("UPDATE notas_fiscais SET status='CANCELADA', cancelada_motivo=? WHERE id=?", (f"{motivo.strip()} ({por})", nf_id))


# ------------------------------------------------------------------ entrega, inspeção e devolução
def _recebido(conn, nf_item_id):
    return conn.execute("SELECT COALESCE(SUM(quantidade),0) FROM recebimento_itens WHERE nf_item_id=?", (nf_item_id,)).fetchone()[0]


def _romaneio(conn, ni):
    return bool(ni["linha_id"] and _one(conn, "SELECT 1 FROM nf_linhas WHERE id=? AND romaneio_caesb=1", ni["linha_id"]))


def receber(conn, nf_id, data, itens, por, documento=None, motivo=None):
    """Entrega (parcial ou total): cada item entra em QUARENTENA, nunca direto no estoque. O tubo da Caesb (remessa) entra
    como romaneio Caesb, com a quantidade que o almoxarife conferiu. Na remessa, o "avariado" do item conta como entregue
    (a nota não fica esperando por ele), não entra no romaneio e fica registrado como recusado, com o motivo."""
    S.exigir_data_ocorrida(data, "Recebimento")
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", nf_id)
    if not nf or nf["status"] != "CONFERIDA":
        raise RegraViolada("Só nota CONFERIDA recebe entregas (confira a nota antes).")
    _quem_digitou_nao_confere(nf, por)
    if not data or (nf["data_emissao"] and data < nf["data_emissao"]):
        raise RegraViolada("Data da entrega ausente ou anterior à emissão da nota.")
    plano = []
    for it in itens or []:
        q = float(it.get("quantidade") or 0)
        if q <= 0:
            continue
        ni = _one(conn, "SELECT * FROM nf_itens WHERE id=? AND nf_id=?", it.get("nf_item_id"), nf_id)
        if not ni:
            raise RegraViolada("Item não pertence a esta nota.")
        resta = ni["quantidade"] - _recebido(conn, ni["id"])
        if q > resta + TOL:
            raise RegraViolada(f"{ni['material_id']}: entrega ({q:g}) maior que o saldo da nota ({resta:g}).")
        rom = _romaneio(conn, ni)
        avar = float(it.get("avariado") or 0)
        if avar and not rom:
            raise RegraViolada(f"{ni['material_id']}: o avariado da compra é recusado na inspeção da entrega.")
        if avar < -TOL or avar > q + TOL:
            raise RegraViolada(f"{ni['material_id']}: o avariado fica entre 0 e o entregue ({q:g}).")
        if avar > TOL and not str(motivo or "").strip():
            raise RegraViolada("Descreva a avaria (ou a recusa) do tubo da Caesb.")
        plano.append((ni, q, rom, round(max(avar, 0.0), 6)))
    if not plano:
        raise RegraViolada("Informe a quantidade entregue de ao menos um item.")
    with transacao(conn):
        rid = conn.execute("INSERT INTO recebimentos(nf_id,data,documento,recebido_por,registrado_em) VALUES (?,?,?,?,?)",
                           (nf_id, data, documento, por, _agora())).lastrowid
        for ni, q, rom, avar in plano:
            if rom:                                    # remessa da Caesb: romaneio, sem quarentena de compra
                doc = f"NF {nf['numero']} (remessa Caesb)" + (f"; {avar:g} recusado, fora do romaneio" if avar else "")
                mid = conn.execute(
                    """INSERT INTO movimentos(data,material_id,tipo,quantidade,documento,status,nf_id,responsavel,ref_tipo,ref_id)
                       VALUES (?,?,'ROMANEIO_CAESB',?,?, 'ACEITO', ?, ?, 'RECEBIMENTO', ?)""",
                    (data, ni["material_id"], round(q - avar, 6), doc, nf_id, por, rid)).lastrowid
            else:
                mid = conn.execute(
                    """INSERT INTO movimentos(data,material_id,tipo,quantidade,documento,status,nf_id,responsavel,ref_tipo,ref_id)
                       VALUES (?,?,'ENTRADA_NF',?,?, 'QUARENTENA', ?, ?, 'RECEBIMENTO', ?)""",
                    (data, ni["material_id"], q, f"NF {nf['numero']}", nf_id, por, rid)).lastrowid
            ri = conn.execute("INSERT INTO recebimento_itens(recebimento_id,nf_item_id,quantidade,movimento_id) VALUES (?,?,?,?)",
                              (rid, ni["id"], q, mid)).lastrowid
            if avar:                                   # tubo da Caesb recusado: registrado na entrega, sem novo movimento
                m = str(motivo).strip()
                conn.execute("""INSERT INTO inspecoes(recebimento_item_id,aceito,recusado,laudo,motivo_recusa,inspecionado_por,
                                  inspecionado_em,movimento_aceito_id) VALUES (?,?,?,?,?,?,?,?)""",
                             (ri, round(q - avar, 6), avar, m, m, por, _agora(), mid))
        _encerrar_se_completa(conn, nf_id)          # remessa da Caesb toda recebida: não há inspeção a esperar
    return rid


# o tubo da Caesb (remessa) entra como romaneio: sem quarentena nem inspeção
_SEM_ROMANEIO = "COALESCE(ni.linha_id, 0) NOT IN (SELECT id FROM nf_linhas WHERE romaneio_caesb=1)"


def _encerrar_se_completa(conn, nf_id):
    if _one(conn, "SELECT 1 FROM nf_entregas_linhas e JOIN nf_linhas l ON l.id=e.linha_id WHERE l.nf_id=?", nf_id):
        from recebimento import encerrar
        return encerrar(conn, nf_id)
    pend = conn.execute(
        """SELECT COUNT(*) FROM nf_itens ni WHERE ni.nf_id=? AND (ni.quantidade - COALESCE((SELECT SUM(quantidade)
             FROM recebimento_itens WHERE nf_item_id=ni.id),0)) > 1e-6""", (nf_id,)).fetchone()[0]
    sem_insp = conn.execute(
        """SELECT COUNT(*) FROM recebimento_itens ri JOIN nf_itens ni ON ni.id=ri.nf_item_id
           WHERE ni.nf_id=? AND ri.id NOT IN (SELECT recebimento_item_id FROM inspecoes) AND """ + _SEM_ROMANEIO, (nf_id,)).fetchone()[0]
    if not pend and not sem_insp:
        conn.execute("UPDATE notas_fiscais SET status='ENCERRADA' WHERE id=?", (nf_id,))


def _quem_digitou_nao_confere(nf, por):
    """A mesma regra do recebimento num toque (D-171) vale nas rotas antigas de entrega e inspeção."""
    if nf and nf["origem"] == "DIGITADA" and str(nf["registrada_por"] or "").lower() == str(por or "").lower():
        raise RegraViolada("Quem digitou os dados da nota não pode conferi-los.")


def inspecionar(conn, recebimento_item_id, aceito, recusado, laudo, por, data, motivo_recusa=None, documento_b64=None,
                documento_nome=None):
    """Aceito + recusado = entregue. O aceito entra no estoque (novo ENTRADA_NF ACEITO); o recusado não entra. O laudo é
    opcional; com recusa, obrigatório."""
    S.exigir_data_ocorrida(data, "Inspeção")
    ri = _one(conn, """SELECT ri.*, r.data data_entrega, r.nf_id, ni.material_id FROM recebimento_itens ri
                       JOIN recebimentos r ON r.id=ri.recebimento_id JOIN nf_itens ni ON ni.id=ri.nf_item_id WHERE ri.id=?""",
              recebimento_item_id)
    if not ri:
        raise RegraViolada("Item de entrega não encontrado.")
    _quem_digitou_nao_confere(_one(conn, "SELECT origem, registrada_por FROM notas_fiscais WHERE id=?", ri["nf_id"]), por)
    if _one(conn, "SELECT 1 FROM inspecoes WHERE recebimento_item_id=?", recebimento_item_id):
        raise RegraViolada("Item já inspecionado.")
    a, r = float(aceito or 0), float(recusado or 0)
    if a < 0 or r < 0 or abs(a + r - ri["quantidade"]) > TOL:
        raise RegraViolada(f"Aceito + recusado deve ser igual ao entregue ({ri['quantidade']:g}).")
    if r > 0 and not str(motivo_recusa or "").strip():
        raise RegraViolada("Informe o motivo da recusa.")
    if r > 0 and not str(laudo or "").strip():
        raise RegraViolada("Com recusa, informe a referência do laudo da inspeção.")
    tem_laudo = bool(str(laudo or "").strip())
    laudo = str(laudo or "").strip() or f"conferido por {por}"           # sem recusa, o laudo é opcional
    if not data or data < ri["data_entrega"]:
        raise RegraViolada("Data da inspeção ausente ou anterior à entrega.")
    with transacao(conn):
        doc = guardar_documento(conn, "LAUDO", documento_b64, documento_nome, por, documento_dir(conn)) if documento_b64 else None
        conn.execute("UPDATE movimentos SET status='INSPECIONADO' WHERE id=? AND status='QUARENTENA'", (ri["movimento_id"],))
        iid = conn.execute(
            """INSERT INTO inspecoes(recebimento_item_id,aceito,recusado,laudo,documento_id,motivo_recusa,inspecionado_por,inspecionado_em)
               VALUES (?,?,?,?,?,?,?,?)""",
            (recebimento_item_id, a, r, laudo, doc, (motivo_recusa or "").strip() or None, por, _agora())).lastrowid
        if a > 0:
            nf = _one(conn, "SELECT numero FROM notas_fiscais WHERE id=?", ri["nf_id"])
            mid = conn.execute(
                """INSERT INTO movimentos(data,material_id,tipo,quantidade,documento,status,nf_id,responsavel,ref_tipo,ref_id)
                   VALUES (?,?,'ENTRADA_NF',?,?, 'ACEITO', ?, ?, 'INSPECAO', ?)""",
                (data, ri["material_id"], a, f"NF {nf['numero']} · " + (f"laudo {laudo}" if tem_laudo else f"aceito sem laudo por {por}"),
                 ri["nf_id"], por, iid)).lastrowid
            conn.execute("UPDATE inspecoes SET movimento_aceito_id=? WHERE id=?", (mid, iid))
        _encerrar_se_completa(conn, ri["nf_id"])
    return iid


def inspecionar_entrega(conn, recebimento_id, itens, laudo, por, data, motivo_recusa=None, documento_b64=None, documento_nome=None):
    """A inspeção da entrega inteira, com um laudo só (opcional; obrigatório quando há recusa). itens: [{recebimento_item_id,
    aceito, recusado}]; vazio = "Aceitar tudo desta entrega" (o que ainda está em quarentena nela)."""
    pend = {r["id"]: r for r in _rows(conn.execute(
        """SELECT ri.id, ri.quantidade FROM recebimento_itens ri JOIN nf_itens ni ON ni.id=ri.nf_item_id
           WHERE ri.recebimento_id=? AND ri.id NOT IN (SELECT recebimento_item_id FROM inspecoes) AND """ + _SEM_ROMANEIO,
        (recebimento_id,)))}
    if not pend:
        raise RegraViolada("Nada em quarentena nesta entrega.")
    itens = itens or [{"recebimento_item_id": i, "aceito": r["quantidade"], "recusado": 0} for i, r in pend.items()]
    if any(int(i["recebimento_item_id"]) not in pend for i in itens):
        raise RegraViolada("Item fora desta entrega ou já inspecionado.")
    if any(float(i.get("recusado") or 0) > 0 for i in itens) and not str(laudo or "").strip():
        raise RegraViolada("Com recusa, informe a referência do laudo da inspeção.")
    with transacao(conn):
        return [inspecionar(conn, int(i["recebimento_item_id"]), i.get("aceito"), i.get("recusado"), laudo, por, data, motivo_recusa,
                            documento_b64, documento_nome) for i in itens]


def receber_nota(conn, nf_id, por, data, pedido_id=None, problema=None, recusa=None):
    from recebimento import receber as receber_linhas
    return receber_linhas(conn, nf_id, por, data, problema, recusa)


def _tem_aceito(conn, nf_id):
    """Algo da compra foi aceito na inspeção (o que a nota sem pedido tem para aprovar; o tubo da Caesb não conta)."""
    return bool(conn.execute("""SELECT 1 FROM inspecoes i JOIN recebimento_itens ri ON ri.id=i.recebimento_item_id
                                JOIN recebimentos r ON r.id=ri.recebimento_id JOIN nf_itens ni ON ni.id=ri.nf_item_id
                                WHERE r.nf_id=? AND i.aceito>0 AND """ + _SEM_ROMANEIO + " LIMIT 1", (nf_id,)).fetchone())


def devolver_ao_fornecedor(conn, nf_item_id, data, quantidade, motivo, por, documento=None):
    """Devolução de material JÁ aceito (defeito descoberto depois). Sai do disponível: material reservado ou com as
    equipes não pode ser devolvido sem antes voltar ao almoxarifado/liberar a reserva."""
    S.exigir_data_ocorrida(data, "Devolução ao fornecedor")
    ni = _one(conn, "SELECT ni.*, nf.numero FROM nf_itens ni JOIN notas_fiscais nf ON nf.id=ni.nf_id WHERE ni.id=?", nf_item_id)
    if not ni:
        raise RegraViolada("Item da nota não encontrado.")
    if _romaneio(conn, ni):
        raise RegraViolada("O tubo da Caesb (remessa) não é compra: não volta ao fornecedor. A avaria na chegada fica "
                           "recusada no recebimento.")
    q = float(quantidade or 0)
    aceito = conn.execute("""SELECT COALESCE(SUM(i.aceito),0) FROM inspecoes i JOIN recebimento_itens ri ON ri.id=i.recebimento_item_id
                             WHERE ri.nf_item_id=?""", (nf_item_id,)).fetchone()[0]
    dev = conn.execute("SELECT COALESCE(SUM(quantidade),0) FROM devolucoes_fornecedor WHERE nf_item_id=? "
                       "AND movimento_id NOT IN (SELECT movimento_id FROM estornos)", (nf_item_id,)).fetchone()[0]
    if q <= 0 or q > aceito - dev + TOL:
        raise RegraViolada(f"Devolução deve ser > 0 e ≤ aceito ainda não devolvido ({aceito - dev:g}).")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo da devolução.")
    disp = S.disponivel(conn, ni["material_id"])
    if q > disp + TOL:
        raise RegraViolada(f"Disponível no almoxarifado ({disp:g}) menor que a devolução: traga o material de volta das equipes "
                           "ou libere reservas antes.")
    with transacao(conn):
        mid = conn.execute(
            """INSERT INTO movimentos(data,material_id,tipo,quantidade,documento,motivo,nf_id,responsavel,ref_tipo)
               VALUES (?,?,'DEVOLUCAO_FORNECEDOR',?,?,?,?,?, 'DEVOLUCAO')""",
            (data, ni["material_id"], q, documento or f"devolução NF {ni['numero']}", motivo.strip(), ni["nf_id"], por)).lastrowid
        did = conn.execute(
            """INSERT INTO devolucoes_fornecedor(nf_id,nf_item_id,data,quantidade,motivo,documento,responsavel,registrado_em,movimento_id)
               VALUES (?,?,?,?,?,?,?,?,?)""", (ni["nf_id"], nf_item_id, data, q, motivo.strip(), documento, por, _agora(), mid)).lastrowid
        conn.execute("UPDATE movimentos SET ref_id=? WHERE id=?", (did, mid))
    return did


# ------------------------------------------------------------------ transferência, inventário e reservas vencidas
def transferir(conn, data, material_id, quantidade, de_equipe, para_equipe, autorizacao, por, motivo=None):
    """Transferência entre equipes em campo (sessões abertas das duas), sem passar pelo almoxarifado."""
    S.exigir_data_ocorrida(data, "Transferência")
    if de_equipe == para_equipe:
        raise RegraViolada("Escolha equipes diferentes.")
    if not str(autorizacao or "").strip():
        raise RegraViolada("Informe quem autorizou a transferência.")
    q = float(quantidade or 0)
    if q <= 0:
        raise RegraViolada("Quantidade deve ser maior que zero.")
    sessoes = {}
    for eq in (de_equipe, para_equipe):
        ck = _one(conn, "SELECT * FROM checkins WHERE equipe_id=? AND encerrado=0 ORDER BY data, id LIMIT 1", eq)
        if not ck:
            raise RegraViolada(f"A {eq} não tem check-in aberto: a transferência é entre sessões abertas das duas equipes.")
        if data < ck["data"]:
            raise RegraViolada(f"Data anterior à sessão aberta da {eq} ({ck['data']}).")
        sessoes[eq] = ck
    cust = S.custodia_equipe(conn, de_equipe, material_id, sessoes[de_equipe]["id"])
    if q > cust + TOL:
        raise RegraViolada(f"A {de_equipe} tem {cust:g} de {material_id}: não transfere {q:g}.")
    with transacao(conn):
        tid = conn.execute(
            """INSERT INTO transferencias(data,material_id,quantidade,de_equipe,para_equipe,de_checkin,para_checkin,autorizacao,motivo,
                 responsavel,registrado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (data, material_id, q, de_equipe, para_equipe, sessoes[de_equipe]["id"], sessoes[para_equipe]["id"], autorizacao.strip(),
             motivo, por, _agora())).lastrowid
        for tipo, eq in (("TRANSF_SAIDA", de_equipe), ("TRANSF_ENTRADA", para_equipe)):
            ck = sessoes[eq]
            conn.execute(
                """INSERT INTO movimentos(data,material_id,tipo,quantidade,equipe_id,alvo_tipo,alvo_id,checkin_id,responsavel,autorizacao,
                     motivo,ref_tipo,ref_id) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'TRANSFERENCIA', ?)""",
                (data, material_id, tipo, q, eq, ck["alvo_tipo"], ck["alvo_id"], ck["id"], por, autorizacao.strip(), motivo, tid))
    return tid


def registrar_contagem(conn, data, itens, por, obs=None):
    """Contagem física do almoxarifado; guarda o saldo do sistema no momento para conferir no ajuste."""
    if not str(data or "").strip():
        raise RegraViolada("Informe a data da contagem.")
    data = _data_iso(data, "Contagem")
    S.exigir_data_ocorrida(data, "Contagem")
    if not itens:
        raise RegraViolada("Informe ao menos um material contado.")
    vistos = set()
    with transacao(conn):
        iid = conn.execute("INSERT INTO inventarios(data,contado_por,contado_em,obs) VALUES (?,?,?,?)",
                           (data, por, _agora(), obs)).lastrowid
        for it in itens:
            m = _one(conn, "SELECT * FROM materiais WHERE id=?", it.get("material_id"))
            if not m or m["id"] in vistos:
                raise RegraViolada("Material inexistente ou repetido na contagem.")
            vistos.add(m["id"])
            c = float(it.get("contado") if it.get("contado") not in (None, "") else -1)
            if c < 0:
                raise RegraViolada(f"{m['id']}: informe a quantidade contada (≥ 0).")
            conn.execute("INSERT INTO inventario_itens(inventario_id,material_id,saldo_sistema,contado) VALUES (?,?,?,?)",
                         (iid, m["id"], S.saldo_almox(conn, m["id"])[0], c))
    return iid


def decidir_inventario(conn, inventario_id, aprovar, motivo, por):
    """Ajuste aprovado por OUTRA pessoa. Recusa se o saldo mudou desde a contagem (recontar) ou se o ajuste negativo
    deixaria reservas sem cobertura."""
    inv = _one(conn, "SELECT * FROM inventarios WHERE id=?", inventario_id)
    if not inv or inv["status"] != "CONTADO":
        raise RegraViolada("Só inventário contado e ainda não decidido.")
    if inv["contado_por"].lower() == str(por).lower():
        raise RegraViolada("Quem contou não aprova o próprio ajuste.")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo da decisão.")
    itens = _rows(conn.execute("SELECT * FROM inventario_itens WHERE inventario_id=?", (inventario_id,)))
    with transacao(conn):
        if aprovar:
            for it in itens:
                atual = S.saldo_almox(conn, it["material_id"])[0]
                if abs(atual - it["saldo_sistema"]) > TOL:
                    raise RegraViolada(f"{it['material_id']}: o saldo mudou desde a contagem ({it['saldo_sistema']:g} → {atual:g}). Recontar.")
                dif = round(it["contado"] - it["saldo_sistema"], 6)
                if abs(dif) <= TOL:
                    continue
                if dif < 0 and S.disponivel(conn, it["material_id"]) + dif < -TOL:
                    raise RegraViolada(f"{it['material_id']}: o ajuste de {dif:g} deixaria reservas sem cobertura. Cancele ou reduza "
                                       "reservas antes.")
                mid = conn.execute(
                    """INSERT INTO movimentos(data,material_id,tipo,quantidade,documento,motivo,responsavel,ref_tipo,ref_id)
                       VALUES (?,?,?,?,?,?,?, 'INVENTARIO', ?)""",
                    (inv["data"], it["material_id"], "AJUSTE_INVENTARIO_ENTRADA" if dif > 0 else "AJUSTE_INVENTARIO_SAIDA", abs(dif),
                     f"Inventário #{inventario_id}", motivo.strip(), por, inventario_id)).lastrowid
                conn.execute("UPDATE inventario_itens SET movimento_id=? WHERE id=?", (mid, it["id"]))
        conn.execute("UPDATE inventarios SET status=?, decidido_por=?, decidido_em=?, decisao_motivo=? WHERE id=?",
                     ("AJUSTADO" if aprovar else "DESCARTADO", por, _agora(), motivo.strip(), inventario_id))


def inventarios(conn):
    out = _rows(conn.execute("SELECT * FROM inventarios ORDER BY id DESC"))
    for i in out:
        i["itens"] = _rows(conn.execute("SELECT *, contado - saldo_sistema diferenca FROM inventario_itens WHERE inventario_id=?", (i["id"],)))
    return out


def reservas_vencidas(conn, hoje):
    return _rows(conn.execute("SELECT * FROM reservas WHERE status='ATIVA' AND data < ? ORDER BY data, id", (hoje,)))


def liberar_reservas_vencidas(conn, ids, motivo, por, hoje):
    if not ids:
        raise RegraViolada("Escolha as reservas a liberar.")
    if not str(motivo or "").strip():
        raise RegraViolada("Informe o motivo.")
    with transacao(conn):
        for rid in ids:
            r = _one(conn, "SELECT * FROM reservas WHERE id=?", rid)
            if not r or r["status"] != "ATIVA" or r["data"] >= hoje:
                raise RegraViolada(f"Reserva #{rid} não está vencida (só reservas ATIVAS de dias anteriores).")
            conn.execute("UPDATE reservas SET status='CANCELADA', encerrada_em=?, motivo=? WHERE id=?",
                         (_agora(), f"vencida — {motivo.strip()} ({por})", rid))
    return len(ids)


# ------------------------------------------------------------------ consultas para a tela
def painel(conn):
    from recebimento import linhas as linhas_entrega
    nfs = _rows(conn.execute("""SELECT n.*, sn.solicitacao_id FROM notas_fiscais n
                                LEFT JOIN solicitacao_notas sn ON sn.nf_id=n.id ORDER BY n.id DESC LIMIT 200"""))
    for n in nfs:
        if n["status"] in ("A_CONFERIR", "CONFERIDA") and n["origem"] != "DIRETA":
            # as linhas "faltando a confirmação" (D-171) e o que já chegou de cada linha, na unidade da nota (D-174)
            n["sugestoes"] = sugerir_materiais(conn, n["id"])
            n["linhas"] = linhas_entrega(conn, n["id"])
        else:
            n["linhas"] = _rows(conn.execute("SELECT * FROM nf_linhas WHERE nf_id=? ORDER BY n_item", (n["id"],)))
        n["itens"] = _rows(conn.execute(
            """SELECT ni.*, (SELECT COALESCE(SUM(quantidade),0) FROM recebimento_itens WHERE nf_item_id=ni.id) recebido,
                      (SELECT COALESCE(SUM(i.aceito),0) FROM inspecoes i JOIN recebimento_itens ri ON ri.id=i.recebimento_item_id
                        WHERE ri.nf_item_id=ni.id) aceito,
                      (SELECT COALESCE(SUM(quantidade),0) FROM devolucoes_fornecedor WHERE nf_item_id=ni.id
                       AND movimento_id NOT IN (SELECT movimento_id FROM estornos)) devolvido
               FROM nf_itens ni WHERE ni.nf_id=? ORDER BY ni.id""", (n["id"],)))
        n["a_inspecionar"] = _rows(conn.execute(
            """SELECT ri.id, ri.quantidade, ni.material_id, r.data FROM recebimento_itens ri JOIN recebimentos r ON r.id=ri.recebimento_id
               JOIN nf_itens ni ON ni.id=ri.nf_item_id WHERE r.nf_id=? AND ri.id NOT IN (SELECT recebimento_item_id FROM inspecoes)
               AND """ + _SEM_ROMANEIO + " ORDER BY ri.id", (n["id"],)))
    return {
        "fornecedores": _rows(conn.execute("SELECT * FROM fornecedores ORDER BY nome")),
        # as aprovadas, para ligar a nota a uma delas (D-172: só marca "Chegou")
        "solicitacoes": _rows(conn.execute("""SELECT s.id, s.data, s.solicitante, d.frente_id FROM solicitacoes_compra s
                                              LEFT JOIN solicitacao_detalhes d ON d.solicitacao_id=s.id
                                              WHERE s.status='APROVADA' ORDER BY s.id DESC LIMIT 200""")),
        "notas": nfs,
    }


def a_inspecionar(conn):
    """Material entregue ainda em quarentena (fluxo de compras), de todas as notas: o que o almoxarife aceita ou recusa
    na inspeção (também na tela Estoque e movimentos)."""
    return _rows(conn.execute(
        """SELECT ri.id, ri.quantidade, ni.material_id, m.descricao, m.unidade, r.data, r.documento, nf.id nf_id, nf.numero,
                  nf.serie, nf.fornecedor
           FROM recebimento_itens ri JOIN recebimentos r ON r.id=ri.recebimento_id JOIN nf_itens ni ON ni.id=ri.nf_item_id
           JOIN notas_fiscais nf ON nf.id=r.nf_id LEFT JOIN materiais m ON m.id=ni.material_id
           WHERE ri.id NOT IN (SELECT recebimento_item_id FROM inspecoes) AND """ + _SEM_ROMANEIO + " ORDER BY r.data, ri.id"))


def notas_a_receber(conn):
    """O que o almoxarife tem a fazer com as notas (tela Estoque e movimentos): cada linha com o material reconhecido e o
    que já chegou (D-171, D-174) e, das entregas anteriores à v22, a quarentena por entrega."""
    from recebimento import linhas as linhas_entrega
    out = []
    for n in _rows(conn.execute("""SELECT * FROM notas_fiscais WHERE origem<>'DIRETA' AND status IN ('A_CONFERIR','CONFERIDA')
                                     ORDER BY id DESC LIMIT 100""")):
        n["sugestoes"] = sugerir_materiais(conn, n["id"])
        n["linhas"] = linhas_entrega(conn, n["id"])
        n["itens"] = _rows(conn.execute(
            """SELECT ni.*, l.romaneio_caesb, l.descricao linha_descricao, m.descricao, m.unidade,
                      (SELECT COALESCE(SUM(quantidade),0) FROM recebimento_itens WHERE nf_item_id=ni.id) recebido
               FROM nf_itens ni LEFT JOIN nf_linhas l ON l.id=ni.linha_id LEFT JOIN materiais m ON m.id=ni.material_id
               WHERE ni.nf_id=? ORDER BY ni.id""", (n["id"],)))
        entregas = {}
        for r in _rows(conn.execute(
                """SELECT ri.id, ri.recebimento_id, ri.quantidade, ni.material_id, m.unidade, r.data, r.documento
                   FROM recebimento_itens ri JOIN recebimentos r ON r.id=ri.recebimento_id JOIN nf_itens ni ON ni.id=ri.nf_item_id
                   LEFT JOIN materiais m ON m.id=ni.material_id
                   WHERE r.nf_id=? AND ri.id NOT IN (SELECT recebimento_item_id FROM inspecoes) AND """ + _SEM_ROMANEIO
                + " ORDER BY ri.id", (n["id"],))):
            e = entregas.setdefault(r["recebimento_id"], {"id": r["recebimento_id"], "data": r["data"], "documento": r["documento"], "itens": []})
            e["itens"].append(r)
        n["entregas"] = list(entregas.values())
        out.append(n)
    return out

