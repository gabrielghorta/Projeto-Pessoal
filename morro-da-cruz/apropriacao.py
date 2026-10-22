"""Apropriação direta (lançamento sem nota de serviço) e a base de custo (módulos B e E).

* Situação do item, só duas: APROVADO (código da base Caesb, SINAPI ou SICRO, que vieram no orçamento da licitação, ou
  código provisório com o código oficial já registrado) ou A_APROVAR (código provisório com "X" sem o oficial, ou item
  novo fora do BM). Vale para toda a medição: servicos._lancar segura o item a aprovar (restrição ITEM_A_APROVAR).
* Busca por qualquer identificador (item, código, descrição, resumida, grupo, material, diâmetro…), sem acento e em
  qualquer ordem, com os sinônimos do orçamento (TÊ/TE, PEAD, FOFO, PVC, Ø/DE/DN/MM).
* Apropriação: Engenharia e Administração; data já ocorrida; pelo menos uma evidência; correção só por estorno com
  motivo (o original fica). A apropriação em item aprovado, de serviço e dentro da quantidade do BM vira proposta na
  gaveta 5 da medição de TESTE aberta (a do mês da data ou a próxima), com a chave da parcela: não duplica.
* restricoes(): o que foi executado ou registrado e está parado, com o valor, há quantos dias e a ação que libera.
  Quando a restrição cai, sincronizar() propõe sozinho na medição de teste aberta.
A planilha do BM não muda: o código oficial fica em codigos_oficiais e o item novo em itens_novos_base.
"""
import base64
import binascii
import json
import re
import unicodedata
from collections import OrderedDict
from datetime import date

import compras as C
import regras as R
import servicos as S
from servicos import RegraViolada, _agora, _one, _rows, transacao

GRUPOS = OrderedDict([("CANTEIRO", "Canteiro"), ("REDES", "Redes"), ("CAIXAS", "Caixas"), ("INTERLIGAÇÃO", "Interligação"),
                      ("LIGAÇÕES", "Ligações"), ("HIDROMECÂNICO", "Hidromecânico"), ("ADMINISTRAÇÃO LOCAL", "Administração local")])
TIPOS = ("MATERIAL", "SERVIÇO")
EXECUTORES = OrderedDict([("EQUIPE_OBRA", "equipe da obra"), ("OUTRA_OBRA", "equipe de outra obra da Ankara"),
                          ("TERCEIRO", "terceiro")])
LOCAIS = OrderedDict([("CANTEIRO", "canteiro"), ("ZONA", "zona"), ("TRECHO", "trecho"), ("ATIVIDADE", "nó ou caixa")])
FONTES_PRECO = OrderedDict([("COTACAO", "cotação"), ("NF", "nota fiscal"), ("SINAPI", "SINAPI"), ("SICRO", "SICRO")])
SERVICO = "APROPRIAÇÃO DIRETA"
GAVETA = 5
LIMITE_EVIDENCIAS = 10
TOL = 1e-6
# restrição: (letra do pedido, o que é, ação que libera, quem faz)
RESTRICOES = OrderedDict([
    ("ITEM_A_APROVAR", ("a", "Item a aprovar na base de custo", "registrar o código oficial da Caesb",
                        "Engenharia ou Administração, com o ofício ou memorando da Caesb")),
    ("ITEM_REPROVADO", ("a", "Item novo reprovado pela Caesb", "estornar a apropriação ou lançar em outro item",
                        "Engenharia ou Administração")),
    ("ACIMA_DO_BM", ("b", "Quantidade acima da contratada no BM", "aditivo ou apostilamento", "Engenharia, com a Caesb")),
    ("TETO_SUBGRUPO", ("c", "Excedente do teto do subgrupo (D-57)", "aditivo ou apostilamento", "Engenharia, com a Caesb")),
    ("MATERIAL_SEM_REGIME", ("d", "Material sem regime de faturamento aprovado (D-53/D-54)",
                             "aprovar a matriz de regimes de material", "Engenharia, com a Caesb")),
    ("CADASTRO_GDOC", ("e", "Cadastro em análise no GDOC", "cobrar a liberação (memorando ESET)", "Engenharia, com a Caesb")),
    ("CADASTRO_PROTOCOLAR", ("e", "Cadastro recebido, falta protocolar no GDOC", "protocolar no GDOC",
                             "Engenharia (esteira do cadastro)")),
    ("CADASTRO_NEGADO", ("e", "Cadastro negado no GDOC", "reenviar à empresa de cadastro", "Engenharia (esteira do cadastro)")),
    ("SEM_MEDICAO_ABERTA", ("—", "Sem medição de teste aberta para a data", "abrir a medição de teste do mês",
                            "Engenharia ou Administração")),
])
CADASTRO_PARADO = {"4_GDOC_ANALISE": "CADASTRO_GDOC", "3_RECEBIDO": "CADASTRO_PROTOCOLAR", "5A_NEGADO": "CADASTRO_NEGADO"}


# ------------------------------------------------------------------ texto da busca
SINONIMOS = (("POLIETILENO DE ALTA DENSIDADE", "PEAD"), ("FERRO FUNDIDO", "FOFO"), ("POLICLORETO DE VINILA", "PVC"))
PARADAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "EM", "COM", "PARA", "P", "A", "O", "AS", "OS", "NA", "NO", "DN", "D"}
_TOKEN = re.compile(r"[A-Z0-9]+(?:[._,/-][A-Z0-9]+)*")


def _norm(s):
    s = str(s if s is not None else "").replace("Ø", " DN ").replace("ø", " DN ")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).upper()
    return re.sub(r"\s+", " ", s).strip()


def _compacto(s):
    return re.sub(r"\s+", "", _norm(s))


def _tokens(texto):
    out = set()
    for t in _TOKEN.findall(texto):
        out.add(t)
        out.update(p for p in re.split(r"[._,/-]", t) if p)
    return out


def palavras(q):
    """As palavras da busca, normalizadas: 'Tê Ø63 PE100' → ['TE', '63', 'PE100']; '63MM' e 'DE63' → '63'."""
    t = _norm(q)
    for longo, curto in SINONIMOS:
        t = t.replace(longo, curto)
    out = []
    for w in _TOKEN.findall(t):
        m = re.fullmatch(r"(?:DN|DE|D)?(\d+(?:[.,]\d+)?)MM|(?:DN|DE)(\d+(?:[.,]\d+)?)", w)
        out.append(m.group(1) or m.group(2) if m else w)
    sig = [w for w in out if w not in PARADAS]
    return list(dict.fromkeys(sig or out))


def _texto_busca(it):
    a = it["atributos"]
    partes = [it["item"], it.get("item_bm"), it.get("codigo"), it.get("codigo_oficial"), it["descricao"], it.get("resumida"),
              it["grupo"], it.get("subgrupo_nome"), it["unidade"], it["classificacao"], R.ORIGEM_CODIGO.get(it["origem"])]
    partes += [v for k, v in a.items() if v not in (None, "", "N/A")]
    t = _norm(" ".join(str(p) for p in partes if p))
    for longo, curto in SINONIMOS:                     # os dois lados acham: PEAD ↔ POLIETILENO DE ALTA DENSIDADE
        if longo in t:
            t += " " + curto
        elif re.search(rf"(?<![A-Z0-9]){curto}(?![A-Z0-9])", t):
            t += " " + longo
    diam = "" if a.get("diametro") in (None, "N/A") else _norm(a.get("diametro"))
    t += "".join(f" {n} DN{n} DE{n} {n}MM" for n in sorted(set(re.findall(r"\d+(?:[.,]\d+)?", diam))))
    return t, diam                                     # o diâmetro inteiro ('63', '110X63') para o bônus da busca


# ------------------------------------------------------------------ catálogo: itens do BM e itens novos, com a situação
def _grupo_tipo(subgrupo, subgrupo_nome):
    nome = str(subgrupo_nome or "").upper().strip()
    if " - " in nome:
        g, tp = nome.rsplit(" - ", 1)
        return g.strip(), tp.strip()
    return nome, "SERVIÇO" if str(subgrupo or "").endswith(".2") else "MATERIAL"


def _rev_bm(conn):
    f = _one(conn, "SELECT nome, revisao FROM fontes_arquivo WHERE chave='bm' ORDER BY id DESC LIMIT 1")
    return (f or {}).get("revisao") or (f or {}).get("nome")


def _situacao_bm(b, oficial, rev=None):
    origem = R.origem_codigo(b["codigo_caesb"])
    comp = R.composicao_referencia(b["codigo_caesb"]) if origem in ("SINAPI", "SICRO") else None
    s = {"origem": origem, "origem_rotulo": f"base Caesb · composição {comp}" if comp else R.ORIGEM_CODIGO[origem],
         "codigo_oficial": None, "conciliado": None}
    if oficial:
        s["codigo_oficial"] = oficial["codigo"]
        s["oficial"] = {k: oficial[k] for k in ("codigo", "data", "por", "em", "documento_id", "codigo_provisorio")}
        if origem != "PROVISORIO" and str(b["codigo_caesb"]).strip() == str(oficial["codigo"]).strip():
            s["conciliado"] = f"conciliado com a {rev}" if rev else "conciliado com o BM"
    if origem != "PROVISORIO":                         # SI/SC: código oficial da base Caesb, com a composição de referência
        s.update(situacao="APROVADO", rotulo=f"Aprovado · base Caesb ({comp})" if comp else "Aprovado · base Caesb")
    elif oficial:
        s.update(situacao="APROVADO", rotulo=f"Aprovado · código oficial {oficial['codigo']}")
    else:
        s.update(situacao="A_APROVAR", rotulo="A aprovar · código provisório")
    return s


def _item_bm(b, oficial, rev=None):
    a = json.loads(b["atributos"] or "{}")
    g, tp = _grupo_tipo(b["subgrupo"], b["subgrupo_nome"])
    it = {"ref": f"BM:{b['id']}", "tipo_ref": "BM", "id": b["id"], "item": b["item"], "item_bm": b["item_bm"],
          "codigo": b["codigo_caesb"], "descricao": b["descricao"], "resumida": a.get("descricao_resumida"),
          "unidade": b["unidade"], "preco": b["preco_unitario"], "preco_estimado": False, "contratado": b["quantidade"],
          "classificacao": str(b["classificacao"] or "").upper(), "grupo": g, "tipo": tp, "subgrupo": b["subgrupo"],
          "subgrupo_nome": b["subgrupo_nome"], "atributos": a, **_situacao_bm(b, oficial, rev)}
    it["_texto"], it["_diam"] = _texto_busca(it)
    return it


def _item_novo(n):
    a = json.loads(n["atributos"] or "{}")
    aprovado = n["situacao"] == "APROVADO"
    rotulo = {"APROVADO": f"Aprovado · código oficial {n['codigo_oficial']}", "REPROVADO": "Reprovado pela Caesb"}.get(
        n["situacao"], "A aprovar · item novo")
    it = {"ref": f"NOVO:{n['id']}", "tipo_ref": "NOVO", "id": n["id"], "item": f"NOVO-{n['id']}", "item_bm": None,
          "codigo": n["codigo_oficial"], "descricao": n["descricao"], "resumida": a.get("descricao_resumida"),
          "unidade": n["unidade"], "preco": n["preco_aprovado"] if aprovado else n["preco_proposto"],
          "preco_estimado": not aprovado, "contratado": None, "classificacao": n["classificacao"], "grupo": n["grupo"],
          "tipo": n["classificacao"], "subgrupo": None, "subgrupo_nome": f"{n['grupo']} - {n['classificacao']}",
          "atributos": a, "situacao": n["situacao"], "origem": "NOVO", "origem_rotulo": R.ORIGEM_CODIGO["NOVO"], "rotulo": rotulo,
          "codigo_oficial": n["codigo_oficial"], "conciliado": None,
          "novo": {k: n[k] for k in ("preco_proposto", "fonte_preco", "fonte_ref", "justificativa", "situacao", "motivo",
                                     "preco_aprovado", "data_decisao", "documento_id", "proposto_por", "proposto_em",
                                     "decidido_por", "decidido_em")}}
    it["_texto"], it["_diam"] = _texto_busca(it)
    return it


def catalogo(conn, com_reprovados=True):
    """Os itens do BM Vertical vigente e os itens novos, cada um com a situação na base de custo."""
    oficiais = {}
    for o in _rows(conn.execute("SELECT * FROM codigos_oficiais ORDER BY id")):
        oficiais[o["item"]] = o                           # vale o último registrado
    rev = _rev_bm(conn)
    out = [_item_bm(b, oficiais.get(b["item"]), rev) for b in
           _rows(conn.execute("SELECT * FROM bm_itens WHERE planilha='VERTICAL' AND vigente=1 ORDER BY linha_origem, id"))]
    out += [_item_novo(n) for n in _rows(conn.execute("SELECT * FROM itens_novos_base ORDER BY id"))
            if com_reprovados or n["situacao"] != "REPROVADO"]
    return out


def publico(it):
    return {k: v for k, v in it.items() if not k.startswith("_")}


def item(conn, ref):
    """Um item pela referência ('BM:675', 'NOVO:3') ou pelo item da Vertical ('5.1_1.14.27')."""
    ref = str(ref or "").strip()
    m = re.fullmatch(r"(BM|NOVO):(\d+)", ref)
    if m and m.group(1) == "BM":
        b = _one(conn, "SELECT * FROM bm_itens WHERE id=? AND planilha='VERTICAL' AND vigente=1", int(m.group(2)))
    elif m:
        n = _one(conn, "SELECT * FROM itens_novos_base WHERE id=?", int(m.group(2)))
        if not n:
            raise RegraViolada(f"Item novo {ref} não encontrado.")
        return _item_novo(n)
    else:
        b = S._bm_item(conn, ref)
    if not b:
        raise RegraViolada(f"Item '{ref}' não encontrado no BM Vertical vigente.")
    return _item_bm(b, S.codigo_oficial(conn, b["item"]), _rev_bm(conn))


# ------------------------------------------------------------------ busca e cascata
def buscar(conn, q, grupo=None, tipo=None, limite=50, catalogo_=None):
    """A busca da decisão 3: casamento exato de item, item do BM ou código primeiro; depois quem casa mais palavras
    inteiras (pedaço também vale, valendo menos). Toda palavra precisa casar."""
    ws = palavras(q)
    if not ws:
        return []
    exato = _compacto(q)
    out = []
    for it in catalogo_ if catalogo_ is not None else catalogo(conn, com_reprovados=False):
        if (grupo and _norm(it["grupo"]) != _norm(grupo)) or (tipo and _norm(it["tipo"]) != _norm(tipo)):
            continue
        e = exato in {_compacto(x) for x in (it["item"], it.get("item_bm"), it.get("codigo"), it.get("codigo_oficial")) if x}
        toks = it.get("_toks") or it.setdefault("_toks", _tokens(it["_texto"]))
        pontos, inteiras = 0, 0
        for w in ws:
            if w in toks:
                p, inteiras = 3, inteiras + 1
            elif any(t.startswith(w) for t in toks):
                p = 2
            elif w in it["_texto"]:
                p = 1
            else:
                p = 0
            if not p and not e:
                break
            if it["_diam"] == w:
                p += 2                                    # o diâmetro do item, não um dos lados de "110X63"
            pontos += p
        else:
            out.append((not e, -inteiras, -pontos, it))
    out.sort(key=lambda x: x[:3])
    return [dict(publico(it), exato=not x, pontos=-p) for x, _, p, it in out[:limite]]


def itens_do_subgrupo(conn, grupo, tipo):
    """Os itens do grupo e do tipo (material ou serviço), com a situação e o saldo."""
    g, tp = _norm(grupo), _norm(tipo)
    out = [it for it in catalogo(conn, com_reprovados=False) if _norm(it["grupo"]) == g and _norm(it["tipo"]) == tp]
    return [dict(publico(it), **saldo(conn, it)) for it in out]


def grupos():
    return {"grupos": [{"id": k, "nome": v} for k, v in GRUPOS.items()], "tipos": list(TIPOS),
            "executores": [{"id": k, "nome": v} for k, v in EXECUTORES.items()],
            "locais": [{"id": k, "nome": v} for k, v in LOCAIS.items()],
            "fontes_preco": [{"id": k, "nome": v} for k, v in FONTES_PRECO.items()]}


# ------------------------------------------------------------------ saldo do item
def _medido(conn, it):
    """Quantidade PROPOSTA nas medições de teste, fora da gaveta 5 (OK interno, cadastro, recomposição)."""
    if it["tipo_ref"] == "BM":
        return conn.execute("""SELECT COALESCE(SUM(l.quantidade),0) FROM medicao_lancamentos l JOIN medicoes m ON m.id=l.medicao_id
                               JOIN bm_itens b ON b.id=l.bm_item_id WHERE l.status='PROPOSTO' AND m.tipo='TESTE' AND l.gaveta<>?
                               AND COALESCE(l.item_congelado, b.item)=?""", (GAVETA, it["item"])).fetchone()[0]
    return conn.execute("""SELECT COALESCE(SUM(l.quantidade),0) FROM medicao_lancamentos l JOIN medicoes m ON m.id=l.medicao_id
                           WHERE l.status='PROPOSTO' AND m.tipo='TESTE' AND l.gaveta<>? AND l.item_novo_id=?""",
                        (GAVETA, it["id"])).fetchone()[0]


def _proposto_g5(conn, it):
    """Quantidade das apropriações do item já proposta na gaveta 5 (medições de teste)."""
    return conn.execute("""SELECT COALESCE(SUM(l.quantidade),0) FROM medicao_lancamentos l JOIN medicoes m ON m.id=l.medicao_id
                           JOIN apropriacoes a ON l.alvo_tipo='APROPRIACAO' AND a.id=CAST(l.alvo_id AS INTEGER)
                           WHERE l.gaveta=? AND l.status='PROPOSTO' AND m.tipo='TESTE' AND a.item=?""",
                        (GAVETA, it["item"])).fetchone()[0]


def saldo(conn, it):
    """Contratado no BM, já medido (gavetas 1 a 4), já apropriado (apropriações não estornadas) e o saldo."""
    medido = _medido(conn, it)
    apropriado = conn.execute("SELECT COALESCE(SUM(quantidade),0) FROM apropriacoes WHERE item=? AND estornado_em IS NULL",
                              (it["item"],)).fetchone()[0]
    c = it["contratado"]
    return {"contratado": c, "medido": round(medido, 4), "apropriado": round(apropriado, 4),
            "saldo": round(c - medido - apropriado, 4) if c is not None else None}


# ------------------------------------------------------------------ apropriação
def _num(v, rotulo):
    try:
        x = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        raise RegraViolada(f"{rotulo}: informe um número.") from None
    if x <= 0:
        raise RegraViolada(f"{rotulo} precisa ser maior que zero.")
    return x


def _data(v, rotulo):
    d = str(v or "").strip()[:10]
    try:
        date.fromisoformat(d)
    except ValueError:
        raise RegraViolada(f"{rotulo}: data inválida.") from None
    S.exigir_data_ocorrida(d, rotulo)
    return d


def _texto(d, campo, rotulo):
    v = re.sub(r"\s+", " ", str(d.get(campo) or "")).strip()
    if not v:
        raise RegraViolada(f"Informe {rotulo}.")
    return v


def _local(conn, d):
    tipo = (d.get("local_tipo") or "").strip().upper() or None
    if tipo is None:
        return None, None, (str(d.get("local_texto") or "").strip() or None)
    if tipo not in LOCAIS:
        raise RegraViolada("Local inválido (canteiro, zona, trecho ou nó).")
    ref, texto = str(d.get("local_id") or "").strip(), str(d.get("local_texto") or "").strip()
    if tipo == "CANTEIRO":
        return tipo, None, texto or "canteiro de obra"
    if tipo == "ZONA":
        if ref not in R.FRENTES:
            raise RegraViolada("Escolha a zona.")
        return tipo, ref, texto or ref
    if not ref:
        raise RegraViolada("Escolha o trecho ou o nó pela busca.")
    a = S.alvo(conn, tipo, ref)
    return tipo, a["id"], a["nome"]


def _executor(conn, d):
    tipo = (d.get("executor_tipo") or "").strip().upper()
    if tipo not in EXECUTORES:
        raise RegraViolada("Diga quem executou: equipe da obra, equipe de outra obra da Ankara ou terceiro.")
    if tipo == "EQUIPE_OBRA":
        eq = str(d.get("equipe_id") or "").strip()
        if not _one(conn, "SELECT 1 FROM equipes WHERE id=?", eq):
            raise RegraViolada("Escolha a equipe da obra.")
        return tipo, eq, None, None
    nome = str(d.get("executor_nome") or "").strip()
    if tipo == "OUTRA_OBRA":
        obra = str(d.get("executor_obra") or "").strip()
        if not obra or not nome:
            raise RegraViolada("Equipe de outra obra: diga qual obra ou contrato da Ankara e qual equipe.")
        return tipo, None, obra, nome
    if not nome:
        raise RegraViolada("Terceiro: informe o nome de quem executou.")
    return tipo, None, None, nome


def _evidencias(conn, lista, por, dir_docs):
    lista = [e for e in (lista or []) if isinstance(e, dict) and e.get("conteudo_b64")]
    if not lista:
        raise RegraViolada("Envie pelo menos uma evidência: foto, croqui ou documento (PDF, JPG ou PNG).")
    if len(lista) > LIMITE_EVIDENCIAS:
        raise RegraViolada(f"No máximo {LIMITE_EVIDENCIAS} evidências por apropriação.")
    return list(dict.fromkeys(C.guardar_documento(conn, "OUTRO", e["conteudo_b64"], e.get("nome"), por, dir_docs) for e in lista))


def apropriar(conn, d, por, dir_docs):
    """Grava a apropriação direta e propõe na gaveta 5 o que puder entrar. Devolve a apropriação com a situação."""
    it = item(conn, d.get("item_ref"))
    if it["situacao"] == "REPROVADO":
        raise RegraViolada(f"O item {it['item']} foi reprovado pela Caesb ({it['novo']['motivo']}): escolha outro item.")
    data = _data(d.get("data"), "Apropriação")
    qtd = _num(d.get("quantidade"), "Quantidade")
    local = _local(conn, d)
    exe = _executor(conn, d)
    textos = [_texto(d, "o_que_foi_feito", "o que foi feito"), _texto(d, "memoria_calculo", "a memória de cálculo da quantidade"),
              _texto(d, "justificativa", "a justificativa técnica")]
    with transacao(conn):
        docs = _evidencias(conn, d.get("evidencias"), por, dir_docs)
        aid = conn.execute(
            """INSERT INTO apropriacoes(data,bm_item_id,item_novo_id,item,quantidade,unidade,local_tipo,local_id,local_texto,
                 executor_tipo,equipe_id,executor_obra,executor_nome,o_que_foi_feito,memoria_calculo,justificativa,
                 registrado_por,registrado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data, it["id"] if it["tipo_ref"] == "BM" else None, it["id"] if it["tipo_ref"] == "NOVO" else None, it["item"],
             round(qtd, 4), it["unidade"], *local, *exe, *textos, por, _agora())).lastrowid
        conn.executemany("INSERT INTO apropriacao_documentos(apropriacao_id, documento_id) VALUES (?,?)",
                         [(aid, doc) for doc in docs])
        _propor(conn, _ap(conn, aid), it)
    return resumo(conn, aid)


def _ap(conn, aid):
    ap = _one(conn, "SELECT * FROM apropriacoes WHERE id=?", int(aid))
    if not ap:
        raise RegraViolada(f"Apropriação nº {aid} não encontrada.")
    return ap


def _lancamentos(conn, aid):
    return _rows(conn.execute("""SELECT l.*, m.numero, m.status AS medicao_status FROM medicao_lancamentos l
                                 JOIN medicoes m ON m.id=l.medicao_id WHERE l.alvo_tipo='APROPRIACAO' AND l.alvo_id=?
                                 AND l.gaveta=? ORDER BY l.id""", (str(aid), GAVETA)))


def _medicao_aberta(conn, data):
    """A medição de teste aberta do mês da data ou, se ela já fechou ou não existe, a próxima aberta."""
    return _one(conn, "SELECT * FROM medicoes WHERE tipo='TESTE' AND status='ABERTA' AND periodo_fim>=? "
                      "ORDER BY periodo_ini LIMIT 1", data)


def _disponivel(conn, it):
    """Quanto do BM ainda cabe na gaveta 5: contratado − medido (gavetas 1 a 4) − já proposto de apropriações."""
    if it["contratado"] is None:
        return None                                    # item novo: sem quantidade no BM; a aprovação define o item
    return max(0.0, float(it["contratado"]) - _medido(conn, it) - _proposto_g5(conn, it))


def _propor(conn, ap, it=None):
    """Propõe na gaveta 5 o que a apropriação ainda não tem proposto, se o item é aprovado e de serviço, dentro do BM e
    com medição de teste aberta. Devolve o id do lançamento (ou None)."""
    if ap["estornado_em"]:
        return None
    it = it or item(conn, f"BM:{ap['bm_item_id']}" if ap["bm_item_id"] else f"NOVO:{ap['item_novo_id']}")
    if it["situacao"] != "APROVADO" or it["classificacao"] != "SERVIÇO":
        return None
    lanc = _lancamentos(conn, ap["id"])
    resta = ap["quantidade"] - sum(l["quantidade"] for l in lanc if l["status"] == "PROPOSTO")
    disp = _disponivel(conn, it)
    pode = resta if disp is None else min(resta, disp)
    med = _medicao_aberta(conn, ap["data"])
    if pode <= TOL or not med:
        return None
    servico = SERVICO if not lanc else f"{SERVICO} · complemento {len(lanc) + 1}"
    exe = _rotulo_executor(conn, ap)
    obs = f"{ap['o_que_foi_feito']} · {exe} · por {ap['registrado_por']}"
    bm = S._bm_item(conn, it["item"]) if it["tipo_ref"] == "BM" else None
    novo = {"id": it["id"]} if it["tipo_ref"] == "NOVO" else None
    return S._lancar(conn, med["id"], GAVETA, servico, bm, ap["unidade"], pode, "APROPRIACAO", str(ap["id"]), obs=obs, novo=novo)


def estornar(conn, aid, motivo, por):
    """Estorno com motivo: a apropriação fica riscada (nada é apagado) e a proposta da gaveta 5 numa medição aberta volta
    a PENDENTE. Proposta em medição fechada não se desfaz (D-16)."""
    ap = _ap(conn, aid)
    if ap["estornado_em"]:
        raise RegraViolada(f"A apropriação nº {ap['id']} já foi estornada em {ap['estornado_em'][:10]}.")
    motivo = re.sub(r"\s+", " ", str(motivo or "")).strip()
    if not motivo:
        raise RegraViolada("Informe o motivo do estorno.")
    lanc = _lancamentos(conn, ap["id"])
    fechadas = [l for l in lanc if l["status"] == "PROPOSTO" and l["medicao_status"] != "ABERTA"]
    if fechadas:
        raise RegraViolada(f"A apropriação nº {ap['id']} já está na {fechadas[0]['numero']}ª medição, que está fechada: "
                           "o estorno não desfaz medição fechada (D-16).")
    with transacao(conn):
        for l in lanc:
            if l["status"] == "PROPOSTO":
                conn.execute("UPDATE medicao_lancamentos SET status='PENDENTE', motivo=?, restricao='ESTORNADA' WHERE id=?",
                             (f"apropriação estornada: {motivo}", l["id"]))
        conn.execute("UPDATE apropriacoes SET estornado_por=?, estornado_em=?, estorno_motivo=? WHERE id=?",
                     (por, _agora(), motivo, ap["id"]))
    return resumo(conn, ap["id"])


def _rotulo_executor(conn, ap):
    if ap["executor_tipo"] == "EQUIPE_OBRA":
        eq = _one(conn, "SELECT nome FROM equipes WHERE id=?", ap["equipe_id"])
        return (eq or {}).get("nome") or ap["equipe_id"]
    if ap["executor_tipo"] == "OUTRA_OBRA":
        return f"{ap['executor_nome']} (outra obra: {ap['executor_obra']})"
    return f"{ap['executor_nome']} (terceiro)"


def resumo(conn, aid, cat=None):
    ap = _ap(conn, aid)
    it = None
    if cat is not None:
        it = cat.get(ap["item"])
    it = it or item(conn, f"BM:{ap['bm_item_id']}" if ap["bm_item_id"] else f"NOVO:{ap['item_novo_id']}")
    lanc = _lancamentos(conn, ap["id"])
    proposto = round(sum(l["quantidade"] for l in lanc if l["status"] == "PROPOSTO"), 4)
    ap["item_info"] = {k: it.get(k) for k in ("ref", "item", "item_bm", "codigo", "descricao", "resumida", "unidade", "preco",
                                              "preco_estimado", "classificacao", "grupo", "tipo", "situacao", "rotulo",
                                              "origem", "origem_rotulo", "codigo_oficial")}
    ap["executor"] = _rotulo_executor(conn, ap)
    ap["documentos"] = _rows(conn.execute("""SELECT d.id, d.nome_original, d.mime, d.bytes FROM apropriacao_documentos x
                                             JOIN documentos d ON d.id=x.documento_id WHERE x.apropriacao_id=? ORDER BY d.id""",
                                          (ap["id"],)))
    ap["lancamentos"] = [{k: l[k] for k in ("id", "medicao_id", "numero", "medicao_status", "servico", "quantidade", "status",
                                            "motivo")} for l in lanc]
    ap["proposto"] = proposto
    ap["parado"] = 0.0 if ap["estornado_em"] else round(ap["quantidade"] - proposto, 4)
    ap["valor"] = round(ap["quantidade"] * (it.get("preco") or 0), 2)
    ap["situacao"] = ("ESTORNADA" if ap["estornado_em"] else "PROPOSTA" if ap["parado"] <= TOL
                      else "PARCIAL" if proposto > TOL else "PARADA")
    return ap


def listar(conn, ini=None, fim=None, equipe=None, limite=300):
    """Apropriações do período (todas, com as estornadas riscadas), da mais nova para a mais antiga."""
    sql, args = "SELECT id FROM apropriacoes WHERE 1=1", []
    for cond, v in (("data>=?", ini), ("data<=?", fim), ("equipe_id=?", equipe)):
        if v:
            sql, args = f"{sql} AND {cond}", args + [v]
    cat = {it["item"]: it for it in catalogo(conn)}
    return [resumo(conn, r[0], cat) for r in conn.execute(sql + " ORDER BY data DESC, id DESC LIMIT ?", (*args, limite))]


def arquivo(conn, documento_id):
    """(documento, nome) de uma evidência de apropriação ou do documento de um código oficial ou item novo."""
    doc = _one(conn, "SELECT * FROM documentos WHERE id=?", int(documento_id))
    ligado = doc and (_one(conn, "SELECT apropriacao_id AS id FROM apropriacao_documentos WHERE documento_id=?", doc["id"])
                      or _one(conn, "SELECT id FROM codigos_oficiais WHERE documento_id=?", doc["id"])
                      or _one(conn, "SELECT id FROM itens_novos_base WHERE documento_id=?", doc["id"]))
    if not ligado:
        raise RegraViolada("Documento não encontrado.")
    return doc, doc["nome_original"] or doc["arquivo"]


# ------------------------------------------------------------------ itens a aprovar: item novo, decisão e código oficial
def parecidos(conn, descricao, atributos=None, limite=3):
    """Itens que já existem com a mesma descrição e os mesmos identificadores (pelo menos 60 % das palavras)."""
    extra = " ".join(str(v) for v in (atributos or {}).values() if v not in (None, "", "N/A"))
    ws = [w for w in palavras(f"{descricao} {extra}") if len(w) >= 3 or w.isdigit()]
    if not ws:
        return []
    out = []
    for it in catalogo(conn, com_reprovados=False):     # só a descrição e os identificadores (o grupo casaria com tudo)
        texto = " ".join(str(x) for x in [it["descricao"], it.get("resumida")] + [v for k, v in it["atributos"].items() if k != "grupo"]
                         if x not in (None, "", "N/A"))
        toks = _tokens(" ".join(palavras(texto)))
        n = sum(1 for w in ws if w in toks)
        if n >= 2 and n / len(ws) >= 0.6:
            out.append((n / len(ws), it))
    out.sort(key=lambda x: -x[0])
    return [dict(publico(it), semelhanca=round(f * 100)) for f, it in out[:limite]]


def _atributos(d):
    a = d.get("atributos") or {}
    if not isinstance(a, dict):
        raise RegraViolada("Identificadores inválidos.")
    chaves = ("descricao_resumida", "material", "diametro", "pressao", "resina", "tipo_conexao", "solda", "grupo_orcamento_ankara")
    return {k: str(a.get(k)).strip() for k in chaves if str(a.get(k) or "").strip()}


def propor_item(conn, d, por):
    """Cadastro rápido de item novo (fora do BM): entra A_APROVAR e já recebe apropriação. Antes de gravar, avisa os itens
    parecidos que já existem (gravado=False); com confirmar=True grava assim mesmo."""
    grupo = {_norm(k): k for k in GRUPOS}.get(_norm(d.get("grupo")))
    if not grupo:
        raise RegraViolada("Escolha o grupo do item.")
    classificacao = {_norm(k): k for k in TIPOS}.get(_norm(d.get("classificacao")))
    if not classificacao:
        raise RegraViolada("Diga se o item é material ou serviço.")
    descricao = _texto(d, "descricao", "a descrição do item")
    unidade = _texto(d, "unidade", "a unidade").upper()
    preco = _num(d.get("preco_proposto"), "Preço proposto")
    fonte = _norm(d.get("fonte_preco"))
    if fonte not in FONTES_PRECO:
        raise RegraViolada("Diga a fonte do preço: cotação, nota fiscal, SINAPI ou SICRO.")
    ref = str(d.get("fonte_ref") or "").strip() or None
    if fonte in ("SINAPI", "SICRO") and not ref:
        raise RegraViolada(f"Informe o código {fonte} do preço.")
    justificativa = _texto(d, "justificativa", "a justificativa do item novo")
    atributos = _atributos(d)
    if not d.get("confirmar"):
        par = parecidos(conn, descricao, atributos)
        if par:
            return {"gravado": False, "parecidos": par}
    with transacao(conn):
        nid = conn.execute(
            """INSERT INTO itens_novos_base(grupo,classificacao,descricao,unidade,atributos,preco_proposto,fonte_preco,fonte_ref,
                 justificativa,proposto_por,proposto_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (grupo, classificacao, descricao, unidade, json.dumps(atributos, ensure_ascii=False), round(preco, 2), fonte, ref,
             justificativa, por, _agora())).lastrowid
    return {"gravado": True, "item": publico(item(conn, f"NOVO:{nid}"))}


def _documento_pdf(conn, b64, nome, por, dir_docs):
    try:
        dados = base64.b64decode(b64 or "", validate=True)
    except (binascii.Error, ValueError):
        dados = b""
    if dados[:5] != b"%PDF-":
        raise RegraViolada("Envie o ofício ou o memorando da Caesb em PDF.")
    return C.guardar_documento(conn, "OUTRO", b64, nome or "documento Caesb.pdf", por, dir_docs)


def _codigo_valido(codigo):
    c = str(codigo or "").strip().upper()
    if not c or R.origem_codigo(c) == "PROVISORIO":
        raise RegraViolada("Informe o código oficial da Caesb (só números, ou o código SINAPI/SICRO), sem 'X'.")
    return c


def registrar_codigo_oficial(conn, d, por, dir_docs):
    """O código oficial de um item do BM com código provisório: com o documento da Caesb e a data. A planilha do BM não
    muda. O que estava parado por este item entra sozinho na medição de teste aberta."""
    it = item(conn, d.get("item_ref"))
    if it["tipo_ref"] != "BM" or it["origem"] != "PROVISORIO":
        raise RegraViolada(f"O item {it['item']} não tem código provisório: nada a registrar.")
    if it["codigo_oficial"]:
        raise RegraViolada(f"O item {it['item']} já tem o código oficial {it['codigo_oficial']} "
                           f"(registrado por {it['oficial']['por']} em {it['oficial']['em'][:10]}).")
    codigo = _codigo_valido(d.get("codigo"))
    data = _data(d.get("data"), "Data do documento")
    with transacao(conn):
        doc = _documento_pdf(conn, d.get("documento_b64"), d.get("documento_nome"), por, dir_docs)
        conn.execute("""INSERT INTO codigos_oficiais(item,bm_item_id,codigo_provisorio,codigo,documento_id,data,por,em)
                        VALUES (?,?,?,?,?,?,?,?)""", (it["item"], it["id"], it["codigo"] or "", codigo, doc, data, por, _agora()))
        liberados = sincronizar(conn)
    return {"item": publico(item(conn, it["ref"])), "liberados": liberados}


def decidir_item(conn, d, por, dir_docs):
    """Aprova (código oficial, preço aprovado, documento e data) ou reprova (motivo) um item novo. Nada é apagado."""
    it = item(conn, d.get("item_ref"))
    if it["tipo_ref"] != "NOVO":
        raise RegraViolada("Só o item novo (fora do BM) é aprovado aqui; o item do BM com código provisório recebe o código oficial.")
    if it["situacao"] != "A_APROVAR":
        raise RegraViolada(f"O item {it['item']} já foi {'aprovado' if it['situacao'] == 'APROVADO' else 'reprovado'}.")
    acao = str(d.get("acao") or "").upper()
    if acao == "REPROVAR":
        motivo = _texto(d, "motivo", "o motivo da reprovação")
        with transacao(conn):
            conn.execute("""UPDATE itens_novos_base SET situacao='REPROVADO', motivo=?, decidido_por=?, decidido_em=?,
                            data_decisao=? WHERE id=?""", (motivo, por, _agora(), date.today().isoformat(), it["id"]))
        return {"item": publico(item(conn, it["ref"])), "liberados": 0}
    if acao != "APROVAR":
        raise RegraViolada("Ação inválida: aprovar ou reprovar.")
    codigo = _codigo_valido(d.get("codigo"))
    preco = _num(d.get("preco_aprovado"), "Preço aprovado")
    data = _data(d.get("data"), "Data do documento")
    with transacao(conn):
        doc = _documento_pdf(conn, d.get("documento_b64"), d.get("documento_nome"), por, dir_docs)
        conn.execute("""UPDATE itens_novos_base SET situacao='APROVADO', codigo_oficial=?, preco_aprovado=?, documento_id=?,
                        data_decisao=?, decidido_por=?, decidido_em=? WHERE id=?""",
                     (codigo, round(preco, 2), doc, data, por, _agora(), it["id"]))
        liberados = sincronizar(conn)
    return {"item": publico(item(conn, it["ref"])), "liberados": liberados}


def itens_a_aprovar(conn, linhas=None):
    """Os itens do BM com código provisório (registrados ou não) e os itens novos, com o valor parado de cada um."""
    parado = {}
    for l in restricoes(conn)["linhas"] if linhas is None else linhas:
        if l["restricao"] in ("ITEM_A_APROVAR", "ITEM_REPROVADO") and l.get("item"):
            parado[l["item"]] = round(parado.get(l["item"], 0) + l["valor"], 2)
    out = [dict(publico(it), valor_parado=parado.get(it["item"], 0.0)) for it in catalogo(conn)
           if it["origem"] in ("PROVISORIO", "NOVO")]
    ordem = {"A_APROVAR": 0, "APROVADO": 1, "REPROVADO": 2}
    out.sort(key=lambda x: (ordem[x["situacao"]], x["tipo_ref"], x["item"]))
    return out


# ------------------------------------------------------------------ liberação: o que cai vira proposta
def sincronizar(conn, hoje=None):
    """Propõe o que ficou livre, sem duplicar: as apropriações com quantidade ainda não proposta (item aprovado, de
    serviço, dentro do BM, com medição de teste aberta) e os lançamentos das gavetas 1 a 4 retidos por item a aprovar
    cujo código foi registrado (na própria medição, se aberta; senão na medição de teste aberta)."""
    hoje = hoje or date.today().isoformat()
    n = 0
    for ap in _rows(conn.execute("SELECT * FROM apropriacoes WHERE estornado_em IS NULL ORDER BY data, id")):
        if _propor(conn, ap):
            n += 1
    retidos = _rows(conn.execute(
        """SELECT l.*, m.status AS medicao_status, m.tipo AS medicao_tipo FROM medicao_lancamentos l
           JOIN medicoes m ON m.id=l.medicao_id
           WHERE l.status='PENDENTE' AND l.restricao='ITEM_A_APROVAR' AND l.gaveta<>?
             AND NOT EXISTS (SELECT 1 FROM medicao_lancamentos x WHERE x.origem_id=l.id) ORDER BY l.id""", (GAVETA,)))
    for l in retidos:
        b = _one(conn, "SELECT * FROM bm_itens WHERE id=?", l["bm_item_id"]) if l["bm_item_id"] else None
        if b is None or S.item_a_aprovar(conn, b):
            continue
        oficial = S.codigo_oficial(conn, b["item"])
        obs = "; ".join(x for x in (l["observacao"], f"liberado em {hoje}: código oficial {oficial['codigo'] if oficial else b['codigo_caesb']}"
                                    " registrado") if x)
        if l["medicao_status"] == "ABERTA":
            conn.execute("UPDATE medicao_lancamentos SET status='PROPOSTO', motivo=NULL, restricao=NULL, observacao=? WHERE id=?",
                         (obs, l["id"]))
            n += 1
            continue
        med = _medicao_aberta(conn, hoje) if l["medicao_tipo"] == "TESTE" else None
        if not med:
            continue
        conn.execute(
            """INSERT INTO medicao_lancamentos(medicao_id,gaveta,servico,bm_item_id,item_novo_id,alvo_tipo,alvo_id,nf_id,material_id,
                 unidade,quantidade,status,observacao,chave,origem_id,lancado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,'PROPOSTO',?,?,?,?)""",
            (med["id"], l["gaveta"], l["servico"], l["bm_item_id"], l["item_novo_id"], l["alvo_tipo"], l["alvo_id"], l["nf_id"],
             l["material_id"], l["unidade"], l["quantidade"], obs, f"{l['chave'] or 'lanc' + str(l['id'])}|liberado", l["id"],
             _agora()))
        n += 1
    return n


# ------------------------------------------------------------------ medível com restrição (dinheiro parado)
def _dias(desde, hoje):
    try:
        return max(0, (date.fromisoformat(hoje) - date.fromisoformat(str(desde)[:10])).days)
    except (TypeError, ValueError):
        return None


def _linha(codigo, hoje, desde, tags=None, **kw):
    letra, rotulo, acao, quem = RESTRICOES[codigo]
    kw.setdefault("valor", 0.0)
    return {"restricao": codigo, "letra": letra, "rotulo": rotulo, "acao": acao, "quem": quem,
            "tags": tags or [codigo], "desde": str(desde)[:10] if desde else None, "dias": _dias(desde, hoje), **kw}


def restricoes(conn, medicao_id=None, hoje=None):
    """Tudo o que foi executado ou registrado e está parado, com o valor (R$ sem BDI = quantidade × preço do BM; no item
    novo, o preço proposto, "estimado"), há quantos dias e a ação que libera. Não entra no valor da medição."""
    hoje = hoje or date.today().isoformat()
    cat = {it["item"]: it for it in catalogo(conn)}
    linhas = []

    def do_item(it, qtd):
        preco = it.get("preco") or 0
        return {"item": it["item"], "item_bm": it.get("item_bm"), "descricao": it.get("resumida") or it["descricao"],
                "grupo": it["grupo"], "unidade": it["unidade"], "quantidade": round(qtd, 4), "preco": preco,
                "valor": round(qtd * preco, 2), "estimado": bool(it.get("preco_estimado")), "situacao_item": it["situacao"]}

    # apropriações: o que ainda não foi proposto, pela restrição (no mesmo item, a primeira apropriação usa o saldo antes)
    disp = {}
    for ap in _rows(conn.execute("SELECT * FROM apropriacoes WHERE estornado_em IS NULL ORDER BY data, id")):
        it = cat.get(ap["item"])
        if not it:
            continue
        resta = ap["quantidade"] - sum(l["quantidade"] for l in _lancamentos(conn, ap["id"]) if l["status"] == "PROPOSTO")
        if resta <= TOL:
            continue
        base = {"origem": f"Apropriação nº {ap['id']} · {ap['data']}", "ref": {"tipo": "APROPRIACAO", "id": ap["id"]},
                "executor": _rotulo_executor(conn, ap)}
        tags = (["ITEM_A_APROVAR"] if it["situacao"] == "A_APROVAR" else ["ITEM_REPROVADO"] if it["situacao"] == "REPROVADO" else [])
        if it["classificacao"] == "MATERIAL":
            tags.append("MATERIAL_SEM_REGIME")
        if tags:
            linhas.append(_linha(tags[0], hoje, ap["data"], tags, **base, **do_item(it, resta)))
            continue
        if it["contratado"] is None:
            livre, excesso = resta, 0.0
        else:
            if it["item"] not in disp:
                disp[it["item"]] = _disponivel(conn, it)
            livre = min(resta, disp[it["item"]])
            disp[it["item"]] -= livre
            excesso = resta - livre
        if excesso > TOL:
            linhas.append(_linha("ACIMA_DO_BM", hoje, ap["data"], **base, **do_item(it, excesso),
                                 contratado=it["contratado"]))
        if livre > TOL:
            linhas.append(_linha("SEM_MEDICAO_ABERTA", hoje, ap["data"], **base, **do_item(it, livre)))

    # lançamentos das gavetas 1 a 4 retidos (item a aprovar, material sem regime), ainda não liberados
    for l in _rows(conn.execute(
            """SELECT l.*, m.numero, m.periodo_ini, b.item AS bm_item FROM medicao_lancamentos l JOIN medicoes m ON m.id=l.medicao_id
               LEFT JOIN bm_itens b ON b.id=l.bm_item_id
               WHERE l.status='PENDENTE' AND l.restricao IN ('ITEM_A_APROVAR','MATERIAL_SEM_REGIME') AND l.gaveta<>? AND m.tipo='TESTE'
                 AND NOT EXISTS (SELECT 1 FROM medicao_lancamentos x WHERE x.origem_id=l.id) ORDER BY l.id""", (GAVETA,))):
        it = cat.get(l["bm_item"])
        if not it:
            continue
        tags = (["ITEM_A_APROVAR"] if it["situacao"] == "A_APROVAR" else []) + \
               (["MATERIAL_SEM_REGIME"] if l["restricao"] == "MATERIAL_SEM_REGIME" else [])
        if not tags:
            continue                                   # código registrado: entra no próximo sincronizar
        alvo = S.nome_alvo(conn, l["alvo_tipo"], l["alvo_id"]) if l["alvo_id"] else "—"
        linhas.append(_linha(tags[0], hoje, l["lancado_em"] or l["periodo_ini"], tags,
                             origem=f"{l['servico']} · {alvo} · {l['numero']}ª medição",
                             ref={"tipo": "LANCAMENTO", "id": l["id"], "alvo_tipo": l["alvo_tipo"], "alvo_id": l["alvo_id"]},
                             **do_item(it, l["quantidade"])))

    # excedente do teto do subgrupo (D-57) na medição pedida ou na de teste aberta
    med = (_one(conn, "SELECT * FROM medicoes WHERE id=?", int(medicao_id)) if medicao_id else
           _one(conn, "SELECT * FROM medicoes WHERE tipo='TESTE' AND status='ABERTA' ORDER BY periodo_ini DESC LIMIT 1"))
    if med:
        for t in S.resumo_medicao(conn, med["id"])["tetos"]:
            if t["excedente"] > 0.004:
                g, _ = _grupo_tipo(t["subgrupo"], t["nome"])
                linhas.append(_linha("TETO_SUBGRUPO", hoje, med["periodo_ini"], item=None, item_bm=None,
                                     descricao=f"Subgrupo {t['subgrupo']} · {t['nome']}", grupo=g, unidade=None, quantidade=None,
                                     preco=None, valor=round(t["excedente"], 2), estimado=False,
                                     origem=f"{med['numero']}ª medição", ref={"tipo": "MEDICAO", "id": med["id"]},
                                     teto=t["teto"]))

    # cadastro esperando o GDOC (o valor é o do item de cadastro pela extensão do trecho, a regra D-58)
    cfg = S.mapa_servicos()["cadastro"]
    it_cad = cat.get(cfg["item"])
    for c in _rows(conn.execute(
            """SELECT c.trecho_id, c.etapa, c.revisao, c.protocolo_gdoc, c.motivo_negativa, c.atualizado_em, t.ponto, t.extensao_m
               FROM cadastro c JOIN trechos t ON t.id=c.trecho_id WHERE c.etapa IN ('3_RECEBIDO','4_GDOC_ANALISE','5A_NEGADO')
               ORDER BY c.etapa, t.ponto""")):
        codigo = CADASTRO_PARADO[c["etapa"]]
        extra = {"protocolo_gdoc": c["protocolo_gdoc"], "motivo_negativa": c["motivo_negativa"]}
        dados = do_item(it_cad, float(c["extensao_m"])) if it_cad else {"item": cfg["item"], "grupo": "REDES", "unidade": "M",
                                                                         "quantidade": float(c["extensao_m"]), "valor": 0.0}
        linhas.append(_linha(codigo, hoje, c["atualizado_em"], origem=f"Cadastro {c['ponto']} · {R.rotulo_etapa(c['etapa'], c['revisao'])}",
                             ref={"tipo": "TRECHO", "id": c["trecho_id"]}, **dados, **extra))

    totais = OrderedDict((k, 0.0) for k in RESTRICOES)
    for x in linhas:
        totais[x["restricao"]] = round(totais[x["restricao"]] + x["valor"], 2)
    return {"linhas": linhas, "totais": {k: v for k, v in totais.items() if v or any(x["restricao"] == k for x in linhas)},
            "total": round(sum(x["valor"] for x in linhas), 2), "medicao": med and {k: med[k] for k in ("id", "numero", "status")},
            "restricoes": [{"id": k, "letra": v[0], "rotulo": v[1], "acao": v[2], "quem": v[3]} for k, v in RESTRICOES.items()],
            "grupos": sorted({x["grupo"] for x in linhas if x.get("grupo")}), "hoje": hoje,
            "aviso": "Valor sem BDI (quantidade × preço do BM; no item novo, o preço proposto, estimado). Não entra no valor "
                     "da medição: é o que está parado e a ação que libera."}
