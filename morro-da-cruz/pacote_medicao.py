"""Medição no modelo oficial do BM do Morro da Cruz (planilhas/BM_MORRO_DA_CRUZ_REV04…xlsx), no formato da juntada.

O pacote sai do próprio arquivo oficial, editado por dentro (xlsx_modelo): logos, estilos, fórmulas, impressão e os 4
gráficos ficam iguais aos do modelo, e a cadeia de fórmulas dele continua valendo:

    nª MC (uma folha por item, chave CÓD.CRON.FF_ITEM-BM) ─SUMIFS─► BM vertical ─SUMIFS por código Caesb─► BM juntada
    BM vertical ─► cronograma FF ─► gráficos;  folha da ADM ─► administração local proporcional ao faturamento do mês

Decisões do responsável (26/10/2026, D-137 a D-145 em docs/DECISOES_PENDENTES.md):
* planilha COM fórmulas, no modelo oficial; enquanto a medição oficial estiver bloqueada (D-56), tudo sai marcado
  TESTE – NÃO OFICIAL (título, cabeçalho de impressão, nome do arquivo e a aba AVISOS DO TESTE);
* administração local (4.1.1) proporcional ao faturamento do mês, pela folha da ADM do modelo (TR 14.6);
* reajuste R$ 0,00, "não pedido" (fração elegível 0 no mês, na aba REAJUSTE);
* fotos: o sistema sugere as 6 mais recentes dos trechos e nós do item; a engenharia troca antes de gerar;
* justificativa técnica no sistema (frase pronta ou texto livre); item acima de 100 % só fecha com justificativa e sai
  marcado ADITIVO PENDENTE.
Medições anteriores (1ª a n-1ª) entram no vertical como valor, congeladas no fechamento; só a coluna do mês tem a
fórmula que puxa da nª MC (SKILL §3.2).
"""
import calendar
import hashlib
import io
import json
import os
import re
import zipfile
from collections import defaultdict
from datetime import date, timedelta

import drive
import importacao as I
import regras as R
import relogio
import servicos as S
import xlsx_modelo as X
from servicos import RegraViolada, _agora, _one, _rows, transacao

try:
    from PIL import Image as _PIL
    from PIL import ImageDraw, ImageFont, ImageOps
except ImportError:                                     # pragma: no cover - depende do ambiente
    _PIL = None

# ------------------------------------------------------------------ o modelo (BM REV04): onde fica cada coisa
JUNTADA, VERTICAL, MC, FF, REAJUSTE = ("BM MORRO DA CRUZ", "BM MORRO DA CRUZ - VERTICAL", "01ª MC", "CRONOGRAMA FF CAESB",
                                       "REAJUSTE")
FOLHA = 92                       # linhas de uma folha da MC
ADM_INI = 1841                   # 1ª linha da folha da administração local no modelo (a folha de item começa na 1)
MEMORIAL = 26                    # 1ª linha do memorial, contada da 1ª linha da folha (27 na folha 1); vai até a 92
LINHAS_MEMORIAL = FOLHA - MEMORIAL
CHAVE_ADM = "6.2_4.1.1"
MEDICOES = 18                    # pares de colunas QUANT./TOTAL do BM (prazo de 540 dias)
COL_VERTICAL, COL_JUNTADA = 22, 18     # QUANT. da 1ª medição: V no vertical, R na juntada
FOTOS_POR_FOLHA = 6
ESTACA_M = 20.0
MARCA = "TESTE – NÃO OFICIAL"
AVISOS = "AVISOS DO TESTE"
FRASES = [
    "SERVIÇO EXECUTADO CONFORME PROJETO E NOTA DE SERVIÇO.",
    "MATERIAL NÃO PREVISTO NO PROJETO, NECESSÁRIO À EXECUÇÃO.",
    "SERVIÇO NÃO PREVISTO NO PROJETO, NECESSÁRIO À EXECUÇÃO.",
    "QUANTIDADE ACIMA DA PREVISTA NO CONTRATO: ADITIVO PENDENTE.",
    "UTILIZADO PARA FECHAR REDE POR CONTA DE PEDRA.",
    "EQUIPE ADMINISTRATIVA/ENGENHARIA DA OBRA.",
]
PERFIS_ADM = {"ENGENHARIA": "Engenharia", "ADMINISTRACAO": "Administração", "SUPERVISOR": "Supervisão de campo",
              "PLANEJAMENTO": "Planejamento", "ALMOXARIFADO": "Almoxarifado", "RH": "RH"}


# ------------------------------------------------------------------ dados da medição
def _medicao(conn, medicao_id):
    med = _one(conn, "SELECT id, numero, tipo, periodo_ini, periodo_fim, status FROM medicoes WHERE id=?", medicao_id)
    if not med:
        raise RegraViolada("Medição não encontrada.")
    if not 1 <= med["numero"] <= MEDICOES:
        raise RegraViolada(f"O BM tem colunas para {MEDICOES} medições; a {med['numero']}ª não cabe no modelo.")
    return med


def _vertical(conn):
    return {b["item"]: b for b in _rows(conn.execute("SELECT * FROM bm_itens WHERE planilha='VERTICAL' AND vigente=1"))}


def quantidades(conn, med):
    """{número da medição: {chave do vertical: quantidade}} do mesmo tipo, até esta (PROPOSTO; item congelado se fechada)."""
    q = defaultdict(lambda: defaultdict(float))
    for r in conn.execute(
            """SELECT m.numero, COALESCE(l.item_congelado, b.item) item, l.quantidade
               FROM medicao_lancamentos l JOIN medicoes m ON m.id=l.medicao_id JOIN bm_itens b ON b.id=l.bm_item_id
               WHERE l.status='PROPOSTO' AND m.tipo=? AND m.numero<=? AND b.planilha='VERTICAL'""",
            (med["tipo"], med["numero"])):
        q[r["numero"]][r["item"]] += r["quantidade"]
    return q


def adm_local(conn, q_mes, vert=None):
    """Administração local do mês como a folha da ADM do modelo (TR 14.6, proporcional aos serviços medidos):
    % ADM = ADM ÷ (subtotal 01 do contrato − ADM); faturamento = Σ ROUND(quant. × preço; 2) do mês, sem a ADM;
    quantidade = faturamento × % ADM ÷ ADM. Mesma ordem de contas das células (N, O, P, Q, R, S, U da folha)."""
    vert = vert or _vertical(conn)
    adm = vert.get(CHAVE_ADM)
    if not adm:
        raise RegraViolada(f"Item da administração local ({CHAVE_ADM}) fora do BM vertical vigente.")
    junt = _rows(conn.execute("SELECT classificacao, quantidade, preco_unitario, codigo_caesb FROM bm_itens "
                              "WHERE planilha='JUNTADA' AND vigente=1"))
    contrato = R.totalizar_bm([(j["classificacao"], j["quantidade"] or 0, j["preco_unitario"] or 0) for j in junt], 0, 0, 0,
                              modo="contrato")["subtotal_01"]
    j_adm = next((j for j in junt if j["codigo_caesb"] == adm["codigo_caesb"]), None)
    total_adm = float(R.produto_excel(j_adm["quantidade"], j_adm["preco_unitario"])) if j_adm else 0.0
    fat = sum(float(R.produto_excel(q, vert[k]["preco_unitario"] or 0)) for k, q in q_mes.items()
              if k != CHAVE_ADM and k in vert and str(vert[k]["classificacao"]).upper().startswith(("MATERIAL", "SERVI")))
    pct = total_adm / (contrato - total_adm) if contrato - total_adm else 0.0
    q = (fat * pct) / total_adm if total_adm else 0.0
    return {"quantidade": q, "faturamento": round(fat, 2), "percentual": pct, "total_contrato": total_adm,
            "preco": adm["preco_unitario"], "valor": float(R.produto_excel(q, adm["preco_unitario"] or 0))}


def totais(conn, q_mes, vert=None):
    """P0 do mês com BDI e K, como o vertical (ROUND por chave) e como a juntada (ROUND por código Caesb)."""
    vert = vert or _vertical(conn)
    fat = S._fatores(conn)
    linhas = [(vert[k]["classificacao"], q, vert[k]["preco_unitario"] or 0) for k, q in q_mes.items() if k in vert]
    por_cod = defaultdict(lambda: [None, 0.0, 0.0])
    for k, q in q_mes.items():
        if k in vert:
            c = por_cod[vert[k]["codigo_caesb"]]
            c[0], c[2] = vert[k]["classificacao"], vert[k]["preco_unitario"] or 0
            c[1] += q
    return {"vertical": R.totalizar_bm(linhas, *fat), "juntada": R.totalizar_bm([tuple(v) for v in por_cod.values()], *fat)}


def _alvo_info(conn, tipo, aid):
    if tipo == "APROPRIACAO":
        a = _one(conn, "SELECT local_texto, o_que_foi_feito FROM apropriacoes WHERE id=?", aid) or {}
        return {"nome": f"APROPRIAÇÃO Nº {aid}", "projeto": None, "ref": " · ".join(x for x in (a.get("local_texto"),
                                                                                              a.get("o_que_foi_feito")) if x)}
    try:
        a = S.alvo(conn, tipo, aid)
    except RegraViolada:
        return {"nome": aid, "projeto": None, "ref": None}
    if tipo == "TRECHO":
        nos = " → ".join(x for x in (a.get("no_ini"), a.get("no_fim")) if x)
        return {"nome": a["nome"], "projeto": a.get("prancha") or a.get("pb"), "ref": nos, "extensao": a.get("extensao_m")}
    return {"nome": a["nome"], "projeto": a.get("pb"), "ref": a.get("numero")}


def _linhas_memorial(conn, medicao_id, item, unidade):
    """Uma linha por lançamento PROPOSTO do item: trecho inteiro em metro sai em estacas (20 m) da estaca 0 ao fim."""
    out = []
    for l in conn.execute(
            """SELECT l.id, l.alvo_tipo, l.alvo_id, l.quantidade FROM medicao_lancamentos l JOIN bm_itens b ON b.id=l.bm_item_id
               WHERE l.medicao_id=? AND l.status='PROPOSTO' AND b.item=? ORDER BY l.id""", (medicao_id, item)):
        info = _alvo_info(conn, l["alvo_tipo"], l["alvo_id"]) if l["alvo_id"] else {"nome": None, "projeto": None, "ref": None}
        q = l["quantidade"]
        lin = {"lancamento_id": l["id"], "nomenclatura": info["nome"], "projeto": info["projeto"], "ref": info["ref"],
               "quantidade": q, "estacas": None}
        ext = info.get("extensao")
        if R.normalizar_unidade(unidade) == "M" and l["alvo_tipo"] == "TRECHO" and ext and abs(ext - q) <= R.TOL_M:
            est = int(q // ESTACA_M)
            lin["estacas"] = (0, 0.0, est, round(q - est * ESTACA_M, 3))
        elif ext and l["alvo_tipo"] == "TRECHO":
            lin["ref"] = " · ".join(x for x in (info["ref"], f"L = {ext:.2f} m".replace(".", ",")) if x)
        out.append(lin)
    return out


def _candidatas(conn, alvos):
    fotos = []
    for tipo, aid in alvos:
        fotos += _rows(conn.execute(f"""SELECT id, alvo_tipo, alvo_id, categoria, arquivo, data_hora, carimbo FROM fotos
                                        WHERE alvo_tipo=? AND alvo_id=? AND {S.FOTO_VALIDA}""", (tipo, aid)))
    fotos.sort(key=lambda f: (f["data_hora"] or "", f["id"]), reverse=True)
    return fotos


def _escolhas(conn, medicao_id):
    return {r["item"]: r for r in _rows(conn.execute("SELECT * FROM medicao_folhas WHERE medicao_id=?", (medicao_id,)))}


def folhas(conn, medicao_id):
    """As folhas da nª MC: itens com quantidade proposta na medição, na ordem do BM vertical, com as fotos (escolhidas
    ou sugeridas), a justificativa, o acumulado e a marca de aditivo pendente (acima de 100 % do contrato)."""
    med = _medicao(conn, medicao_id)
    vert = _vertical(conn)
    q = quantidades(conn, med)
    esc = _escolhas(conn, medicao_id)
    acum = defaultdict(float)
    for n, por in q.items():
        for k, v in por.items():
            acum[k] += v
    out = []
    for k in sorted(q[med["numero"]], key=lambda k: (vert[k]["linha_origem"] if k in vert else 10 ** 9, k)):
        if k == CHAVE_ADM or k not in vert or abs(q[med["numero"]][k]) < 1e-12:
            continue
        b = vert[k]
        alvos = [(r[0], r[1]) for r in conn.execute(
            """SELECT DISTINCT l.alvo_tipo, l.alvo_id FROM medicao_lancamentos l WHERE l.medicao_id=? AND l.status='PROPOSTO'
               AND l.bm_item_id=? AND l.alvo_tipo IN ('TRECHO','ATIVIDADE')""", (medicao_id, b["id"]))]
        cand = _candidatas(conn, alvos)
        e = esc.get(k) or {}
        ids_validos = {f["id"] for f in cand}
        if e.get("fotos") is not None:
            fotos, sugeridas = [i for i in json.loads(e["fotos"]) if i in ids_validos][:FOTOS_POR_FOLHA], False
        else:
            fotos, sugeridas = [f["id"] for f in cand[:FOTOS_POR_FOLHA]], True
        contrato = b["quantidade"]
        excede = contrato is not None and acum[k] > float(contrato) + R.TOL_M
        out.append({"item": k, "item_bm": b["item_bm"], "descricao": b["descricao"], "unidade": b["unidade"],
                    "classificacao": b["classificacao"], "quantidade": round(q[med["numero"]][k], 6),
                    "contrato": contrato, "acumulado": round(acum[k], 6),
                    "percentual": round(acum[k] / float(contrato), 6) if contrato else None,
                    "excede": excede, "justificativa": e.get("justificativa"), "fotos": fotos, "fotos_sugeridas": sugeridas,
                    "candidatas": cand, "linhas": _linhas_memorial(conn, medicao_id, k, b["unidade"])})
    return out


def periodo_no_modelo(numero, modelo=None):
    """(início, fim) da medição `numero` como o modelo calcula (aba REAJUSTE: a partir da data da OS e do prazo; a 1ª
    vai até o fim do mês, ou do mês seguinte se a OS for depois do dia 15). None sem o modelo."""
    modelo = modelo or caminho_modelo()
    if not modelo:
        return None
    try:
        with open(modelo, "rb") as f:
            aba = X.Pacote(f.read()).aba(REAJUSTE)
        os_, prazo = aba.valor("B21"), aba.valor("D21")
        if not isinstance(os_, (int, float)) or not isinstance(prazo, (int, float)):
            return None
    except (KeyError, ValueError, OSError, zipfile.BadZipFile):
        return None
    ini = date(1899, 12, 30) + timedelta(days=int(os_))
    ultimo = ini + timedelta(days=int(prazo) - 1)
    fim_mes = lambda d, mais: date(d.year + (d.month + mais - 1) // 12, (d.month + mais - 1) % 12 + 1,
                                   calendar.monthrange(d.year + (d.month + mais - 1) // 12, (d.month + mais - 1) % 12 + 1)[1])
    fim = min(fim_mes(ini, 1 if ini.day > 15 else 0), ultimo)
    for _ in range(numero - 1):
        ini = fim + timedelta(days=1)
        fim = min(fim_mes(ini, 0), ultimo)
    return ini.isoformat(), fim.isoformat()


def resumo(conn, medicao_id):
    """O que vai no pacote: folhas, administração local, totais (vertical e juntada) e os avisos do teste."""
    med = _medicao(conn, medicao_id)
    vert = _vertical(conn)
    q = quantidades(conn, med)
    fl = folhas(conn, medicao_id)
    adm = adm_local(conn, q[med["numero"]], vert)
    mes = dict(q[med["numero"]])
    mes.pop(CHAVE_ADM, None)
    if adm["quantidade"]:
        mes[CHAVE_ADM] = adm["quantidade"]
    tot = totais(conn, mes, vert)
    avisos = []
    teste = med["tipo"] == "TESTE"
    if teste:
        avisos.append("Medição de TESTE: o pacote segue o modelo oficial, mas não vale como medição (D-56).")
    avisos.append("Reajuste R$ 0,00: não pedido nesta medição (fração elegível 0 na aba REAJUSTE).")
    if med["numero"] > 1:
        avisos.append(f"Medições anteriores (1ª a {med['numero'] - 1}ª): quantidades como valor, congeladas no fechamento "
                      "de cada uma; só a coluna desta medição puxa da memória de cálculo.")
    for f in fl:
        if f["excede"]:
            avisos.append(f"Item {f['item_bm']} ({f['item']}): acumulado {f['acumulado']:g} acima do contrato "
                          f"({f['contrato']:g}) — ADITIVO PENDENTE" + ("" if (f["justificativa"] or "").strip()
                                                                      else "; falta a justificativa técnica."))
        if not f["fotos"]:
            avisos.append(f"Item {f['item_bm']} ({f['item']}): sem foto na galeria.")
    pend = conn.execute("SELECT COUNT(*) FROM medicao_lancamentos WHERE medicao_id=? AND status='PENDENTE'",
                        (medicao_id,)).fetchone()[0]
    if pend:
        avisos.append(f"{pend} lançamento(s) PENDENTE(S) fora do pacote (sem item ou regra confirmada): veja a tela Medição.")
    novos = conn.execute("SELECT COUNT(*) FROM medicao_lancamentos WHERE medicao_id=? AND status='PROPOSTO' "
                         "AND bm_item_id IS NULL", (medicao_id,)).fetchone()[0]
    if novos:
        avisos.append(f"{novos} lançamento(s) de item novo (fora do BM) não cabem no modelo do BM e ficaram de fora.")
    if any(k == CHAVE_ADM for k in q[med["numero"]]):
        avisos.append("Lançamento direto no item da administração local ignorado: a ADM sai proporcional, pela folha da ADM.")
    dif = round(tot["juntada"]["total"] - tot["vertical"]["total"], 2)
    if dif:
        avisos.append(f"Arredondamento: a juntada (ROUND por código Caesb) difere do vertical (ROUND por chave) em "
                      f"R$ {dif:.2f}.")
    try:
        exc = S.resumo_medicao(conn, medicao_id).get("excedente_teto") or 0
    except RegraViolada:
        exc = 0
    if exc:
        avisos.append(f"Teto por subgrupo (D-57, hipótese) não aplicado no modelo oficial: excedente de R$ {exc:.2f}.")
    per = periodo_no_modelo(med["numero"])
    if per and per != (med["periodo_ini"], med["periodo_fim"]):
        avisos.append(f"Período: o modelo põe a {med['numero']}ª medição de {_br(per[0])} a {_br(per[1])} (data da OS na aba "
                      f"REAJUSTE); a do sistema vai de {_br(med['periodo_ini'])} a {_br(med['periodo_fim'])}. O cabeçalho "
                      "do pacote mostra o período do modelo.")
    return {"medicao": med, "teste": teste, "aba_mc": f"{med['numero']:02d}ª MC", "folhas": fl, "adm": adm,
            "totais": {"vertical": tot["vertical"]["total"], "juntada": tot["juntada"]["total"],
                       "material": tot["juntada"]["material"], "servico": tot["juntada"]["servico"]},
            "frases": FRASES, "avisos": avisos}


def _br(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def salvar_folha(conn, medicao_id, item, por, fotos=None, justificativa=None):
    """Fotos da galeria (até 6, na ordem; None = volta à sugestão do sistema) e justificativa técnica do item."""
    med = _medicao(conn, medicao_id)
    if med["status"] != "ABERTA":
        raise RegraViolada("Medição fechada: a memória de cálculo dela não muda mais.")
    fl = {f["item"]: f for f in folhas(conn, medicao_id)}
    if item not in fl:
        raise RegraViolada(f"O item {item} não tem quantidade proposta nesta medição.")
    if fotos is not None:
        fotos = [int(i) for i in fotos]
        validas = {f["id"] for f in fl[item]["candidatas"]}
        fora = [i for i in fotos if i not in validas]
        if fora:
            raise RegraViolada(f"Foto(s) {fora} não são dos trechos e nós deste item ou não são válidas.")
        if len(fotos) > FOTOS_POR_FOLHA:
            raise RegraViolada(f"A galeria tem {FOTOS_POR_FOLHA} lugares: escolha no máximo {FOTOS_POR_FOLHA} fotos.")
        if len(set(fotos)) != len(fotos):
            raise RegraViolada("A mesma foto foi escolhida duas vezes.")
    just = (justificativa or "").strip() or None
    if just and len(just) > 600:
        raise RegraViolada("Justificativa longa demais para a folha (até 600 caracteres).")
    with transacao(conn):
        conn.execute("""INSERT INTO medicao_folhas(medicao_id, item, fotos, justificativa, por, em) VALUES (?,?,?,?,?,?)
                        ON CONFLICT(medicao_id, item) DO UPDATE SET fotos=excluded.fotos,
                          justificativa=excluded.justificativa, por=excluded.por, em=excluded.em""",
                     (medicao_id, item, json.dumps(fotos) if fotos is not None else None, just, por, _agora()))
    return {"item": item, "fotos": fotos, "justificativa": just}


def sem_justificativa(conn, medicao_id):
    """Itens acima de 100 % do contrato sem justificativa técnica (o fechamento exige; aditivo pendente)."""
    return [f for f in folhas(conn, medicao_id) if f["excede"] and not (f["justificativa"] or "").strip()]


# ------------------------------------------------------------------ fotos da galeria
def _fonte(tam):
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:                                   # Pillow < 10.1: fonte fixa
        return ImageFont.load_default()


def imagem_galeria(dados, carimbo, lado=820):
    """JPEG reduzido para a folha, com o carimbo (data, local, GPS) gravado numa faixa no pé da foto."""
    if _PIL is None:
        return None
    try:
        with _PIL.open(io.BytesIO(dados)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
    except (OSError, ValueError):
        return None
    im.thumbnail((lado, lado))
    partes = [p.strip() for p in str(carimbo or "").split("|")]
    if len(partes) >= 4:
        quando = partes[2].replace("T", " ")[:16]
        if re.match(r"\d{4}-\d{2}-\d{2}", quando):
            quando = f"{quando[8:10]}/{quando[5:7]}/{quando[:4]}{quando[10:]}"
        linhas = [f"{quando} · {partes[1]}", f"{partes[3]} · {partes[0]}"]
    else:
        linhas = [x for x in partes if x]
    tam = max(12, im.width // 42)
    fonte = _fonte(tam)
    alt = (tam + 6) * len(linhas) + 8
    faixa = _PIL.new("RGBA", (im.width, alt), (0, 0, 0, 150))
    base = im.convert("RGBA")
    base.alpha_composite(faixa, (0, im.height - alt))
    d = ImageDraw.Draw(base)
    for i, t in enumerate(linhas):
        d.text((8, im.height - alt + 4 + i * (tam + 6)), t, fill=(255, 235, 59, 255), font=fonte)
    saida = io.BytesIO()
    base.convert("RGB").save(saida, "JPEG", quality=80, optimize=True)
    return saida.getvalue(), base.width, base.height


def _bytes_foto(conn, foto, dir_fotos):
    """O original da foto ou, se ele ficou só no Drive, a miniatura guardada no servidor."""
    for rel in (foto["arquivo"], drive.miniatura_de(conn, foto["arquivo"])):
        if rel and os.path.isfile(os.path.join(dir_fotos, rel)):
            with open(os.path.join(dir_fotos, rel), "rb") as f:
                return f.read()
    return None


# ------------------------------------------------------------------ o arquivo
def caminho_modelo():
    return I.caminho(I.carregar_config(), "bm")


def _contrato_numero(conn):
    m = re.search(r"(\d{3,6})\s*/\s*(\d{4})", S.contrato(conn) or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def _px(largura):
    """Largura da coluna (caracteres) em pixels, como o Excel (fonte padrão de 7 px)."""
    return int(((256 * largura + int(128 / 7)) / 256) * 7)


def gerar(conn, medicao_id, dir_fotos=None, modelo=None):
    """(nome do arquivo, bytes do .xlsx, resumo) da medição no modelo oficial."""
    r = resumo(conn, medicao_id)
    med = r["medicao"]
    n = med["numero"]
    modelo = modelo or caminho_modelo()
    if not modelo:
        raise RegraViolada("Modelo oficial do BM ausente em planilhas/ (config/fontes.json, chave bm).")
    with open(modelo, "rb") as f:
        dados = f.read()
    fonte = _one(conn, "SELECT nome, sha256 FROM fontes_arquivo WHERE chave='bm' ORDER BY id DESC LIMIT 1")
    if fonte and fonte["sha256"] != hashlib.sha256(dados).hexdigest():
        raise RegraViolada(f"O BM em planilhas/ não é o que o sistema importou ({fonte['nome']}): rode a importação "
                           "antes de gerar a medição no modelo.")
    p = X.Pacote(dados)
    nomes = [a for a, _ in p.abas()]
    for a in (JUNTADA, VERTICAL, MC, FF, REAJUSTE):
        if a not in nomes:
            raise RegraViolada(f"O modelo do BM mudou: falta a aba '{a}'.")
    vert = _vertical(conn)
    q = quantidades(conn, med)
    teste = r["teste"]
    aba_mc = r["aba_mc"]
    num, ano = _contrato_numero(conn)
    hoje = relogio.hoje()
    cq = lambda m: X.get_column_letter(COL_VERTICAL + 2 * (m - 1))         # QUANT. da medição m no vertical
    ct = lambda m: X.get_column_letter(COL_VERTICAL + 2 * (m - 1) + 1)     # TOTAL da medição m no vertical

    for nome in (JUNTADA, VERTICAL, REAJUSTE):
        p.aba(nome).expandir_compartilhadas()
    fim_mc = _memoria(p, conn, r, aba_mc, n, cq, ct, teste, num, ano, dir_fotos)
    _vertical_preencher(p, vert, q, r, n, aba_mc, fim_mc, cq, teste, num, hoje)
    _juntada_preencher(p, conn, vert, q[n], r, n, teste, num)
    _reajuste_preencher(p, n, teste)
    ff = p.aba(FF)
    if num and isinstance(ff.valor("F2"), str) and "_____" in ff.valor("F2"):
        ff.texto("F2", ff.valor("F2").replace("_____", num))
    if teste:
        for nome, _ in p.abas():
            p.aba(nome).cabecalho(f"{MARCA} · {n}ª MEDIÇÃO")
        _aba_avisos(p, r, hoje)
    p.renomear_aba(MC, aba_mc)
    p.recalcular_ao_abrir()
    p.por_texto("docProps/app.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Properties xmlns='
                '"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Microsoft Excel'
                '</Application></Properties>')
    nome = f"BM_MORRO_DA_CRUZ_{n:02d}a_MEDICAO" + ("_TESTE_NAO_OFICIAL" if teste else "") + ".xlsx"
    return nome, p.salvar(), r


def _titulo(aba, ref, teste):
    t = aba.valor(ref)
    if teste and isinstance(t, str) and MARCA not in t:
        aba.texto(ref, f"{t} — {MARCA}")


def _memoria(p, conn, r, aba_mc, n, cq, ct, teste, num, ano, dir_fotos):
    """Reescreve a aba da MC: uma folha (92 linhas) por item e página, as de continuação quando o memorial passa de
    66 linhas, e a folha da ADM no fim. Devolve a última linha da aba (o SUMIFS do vertical vai até ela)."""
    parte = p.parte_da_aba(MC)
    modelo = X.Aba(p.texto(parte), p.textos)
    modelo.expandir_compartilhadas()
    aba = p.aba(MC)
    aba.linhas = {}
    mesc_item = [m for m in modelo.mesclagens() if X.ref_partes(m.split(":")[0])[1] <= FOLHA]
    mesc_adm = [m for m in modelo.mesclagens() if ADM_INI <= X.ref_partes(m.split(":")[0])[1] < ADM_INI + FOLHA]
    desl = lambda m, d: ":".join(f"{c}{l + d}" for c, l in (X.ref_partes(x) for x in m.split(":")))
    paginas = []                                   # (folha, pedaço do memorial, nº da continuação: 0 = a 1ª)
    for f in r["folhas"]:
        pedacos = [f["linhas"][i:i + LINHAS_MEMORIAL] for i in range(0, max(len(f["linhas"]), 1), LINHAS_MEMORIAL)]
        for i, ped in enumerate(pedacos):
            paginas.append((f, ped, i))
    mesclas, quebras, fotos_pos = [], [], []
    for k, (f, ped, cont) in enumerate(paginas):
        r0 = 1 + FOLHA * k
        d = r0 - 1
        aba.copiar_bloco(1, FOLHA, r0, origem=modelo)
        mesclas += [desl(m, d) for m in mesc_item]
        _cabecalho_folha(aba, r0, k + 1, cq(n), teste, num, ano)
        aba.texto(f"C{r0 + 6}", f["item"])
        just = (f["justificativa"] or "").strip()
        if f["excede"]:
            just = "ADITIVO PENDENTE — acumulado acima do contrato." + (f"\n{just}" if just else "")
        if cont:
            just = f"CONTINUAÇÃO DA FOLHA {k + 1 - cont:03d}." + (f"\n{just}" if just else "")
        if just:
            aba.texto(f"X{r0 + 8}", just)
        for i in range(LINHAS_MEMORIAL):           # sem encadear estacas: cada trecho começa na estaca 0
            lin = r0 + MEMORIAL + i
            aba.vazia(f"I{lin}")
            aba.vazia(f"J{lin}")
        for i, l in enumerate(ped):
            lin = r0 + MEMORIAL + i
            if l["nomenclatura"]:
                aba.texto(f"E{lin}", l["nomenclatura"])
            if l["projeto"]:
                aba.texto(f"G{lin}", l["projeto"])
            if l["ref"]:
                aba.texto(f"N{lin}", l["ref"])
            if l["estacas"]:
                for col, v in zip("IJKL", l["estacas"]):
                    aba.numero(f"{col}{lin}", v)
                aba.numero(f"U{lin}", 1)
            else:
                aba.numero(f"U{lin}", l["quantidade"])
                aba.formula(f"W{lin}", f'IF(U{lin}="",0,U{lin})')
        if not cont:
            fotos_pos.append((r0, f))
        quebras.append(r0 + FOLHA - 1)
    fim_itens = FOLHA * len(paginas)
    r0 = fim_itens + 1                             # folha da ADM
    d = r0 - ADM_INI
    aba.copiar_bloco(ADM_INI, ADM_INI + FOLHA - 1, r0, origem=modelo)
    mesclas += [desl(m, d) for m in mesc_adm]
    _cabecalho_folha(aba, r0, len(paginas) + 1, cq(n), teste, num, ano)
    f_r = modelo.celula(f"R{ADM_INI + MEMORIAL}").f
    aba.formula(f"R{r0 + MEMORIAL}", re.sub(r"!\$W\$(\d+):\$W\$(\d+)", lambda m: f"!${ct(n)}${m[1]}:${ct(n)}${m[2]}", f_r))
    equipe = _equipe(conn)
    aba.texto(f"X{r0 + 8}", "EQUIPE ADMINISTRATIVA/ENGENHARIA DA OBRA." + (f"\n\n{equipe}" if equipe else ""))
    quebras.append(r0 + FOLHA - 1)
    ultima = r0 + FOLHA - 1
    padrao = re.search(r'defaultRowHeight="([\d.]+)"', modelo.antes)
    aba.fixar_alturas(1, ultima, padrao.group(1) if padrao else "14.25")
    aba.por_mesclagens(mesclas)
    aba.quebras_de_pagina(quebras[:-1])
    p.nome_definido("_xlnm.Print_Area", [a for a, _ in p.abas()].index(MC), f"'{aba_mc}'!$B$1:$X${ultima}")
    # comentários do modelo (instruções de preenchimento manual) saem: o sistema preenche
    for rid, (tipo, alvo) in p.relacoes(parte).items():
        if tipo in ("comments", "vmlDrawing"):
            p.desrelacionar(parte, rid)
            p.remover(alvo)
    aba.por_elemento("legacyDrawing", "")
    _desenhos(p, conn, parte, modelo, len(paginas) + 1, fotos_pos, dir_fotos)
    r["linha_adm"] = r0 + 6
    return ultima


def _cabecalho_folha(aba, r0, numero, col_mes, teste, num, ano):
    aba.texto(f"B{r0}", f"FOLHA - {numero:03d}")
    _titulo(aba, f"C{r0}", teste)
    if num:
        aba.texto(f"R{r0 + 1}", f"{num} / {ano}")
    aba.formula(f"T{r0 + 1}", f"'{VERTICAL}'!${col_mes}$4")
    aba.formula(f"T{r0 + 3}", f"'{VERTICAL}'!${col_mes}$2")


def _equipe(conn):
    linhas = []
    for perfil, rotulo in PERFIS_ADM.items():
        nomes = [r[0] for r in conn.execute("SELECT nome FROM usuarios WHERE perfil=? AND ativo=1 ORDER BY nome", (perfil,))]
        if nomes:
            linhas.append(f"{rotulo}: " + ", ".join(nomes))
    return "\n".join(linhas)


def _desenhos(p, conn, parte, modelo, n_folhas, fotos_pos, dir_fotos):
    """Logo em cada folha (cópia da âncora do modelo) e as fotos da galeria, 6 lado a lado nas colunas B a W."""
    rels = p.relacoes(parte)
    dr = next((alvo for t, alvo in rels.values() if t == "drawing"), None)
    if not dr:
        return
    xml = p.texto(dr)
    ancoras = re.findall(r"<xdr:(?:twoCellAnchor|oneCellAnchor)\b.*?</xdr:(?:twoCellAnchor|oneCellAnchor)>", xml, re.S)
    ini = xml.index(ancoras[0]) if ancoras else xml.index("</xdr:wsDr>")
    cab, pe = xml[:ini], "</xdr:wsDr>"
    novas, nid = [], [1]

    def proximo_id():
        nid[0] += 1
        return nid[0]

    logo = ancoras[0] if ancoras else None
    for k in range(n_folhas):
        if logo:
            a = re.sub(r"<xdr:row>(\d+)</xdr:row>", lambda m: f"<xdr:row>{int(m[1]) + FOLHA * k}</xdr:row>", logo)
            novas.append(re.sub(r'<xdr:cNvPr id="\d+"', f'<xdr:cNvPr id="{proximo_id()}"', a, count=1))
    larg = {2: 30.796875, 23: 20.796875}
    cols = [(c, _px(larg.get(c, 15.796875))) for c in range(2, 24)]          # B..W
    total = sum(w for _, w in cols)
    vaga = total // FOTOS_POR_FOLHA
    alt_px = int(sum((modelo.altura(r) or 14.25) for r in range(9, 25)) * 96 / 72)
    caixa_w, caixa_h = vaga - 16, int(alt_px * 0.9)       # folga: o LibreOffice desloca um pouco os desenhos
    seq, midias = 0, {}                            # a mesma foto em várias folhas usa a mesma imagem do pacote
    for r0, f in fotos_pos:
        cand = {c["id"]: c for c in f["candidatas"]}
        for i, fid in enumerate(f["fotos"]):
            foto = cand.get(fid)
            if fid not in midias:
                dados = _bytes_foto(conn, foto, dir_fotos or S.DIR_FOTOS) if foto else None
                img = imagem_galeria(dados, foto["carimbo"]) if dados else None
                if img:
                    midia = f"xl/media/mc_foto_{len(midias) + 1:04d}.jpeg"
                    p.por_texto(midia, img[0])
                    img = (p.relacionar(dr, "image", midia), img[1], img[2])
                midias[fid] = img
            if not midias[fid]:
                continue
            rid, w, h = midias[fid]
            esc = min(caixa_w / w, caixa_h / h)
            cw, ch = int(w * esc), int(h * esc)
            x = i * vaga + (vaga - cw) // 2
            col, acc = cols[0][0], 0
            for c, wpx in cols:
                if acc + wpx > x:
                    col = c
                    break
                acc += wpx
            seq += 1
            emu = 9525
            novas.append(
                f'<xdr:oneCellAnchor><xdr:from><xdr:col>{col - 1}</xdr:col><xdr:colOff>{(x - acc) * emu}</xdr:colOff>'
                f'<xdr:row>{r0 + 7}</xdr:row><xdr:rowOff>{7 * emu}</xdr:rowOff></xdr:from><xdr:ext cx="{cw * emu}" '
                f'cy="{ch * emu}"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="{proximo_id()}" name="Foto {seq}" '
                f'descr="{X.escape(str(foto["carimbo"] or ""), {chr(34): "&quot;"})}"/><xdr:cNvPicPr><a:picLocks '
                f'noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr><xdr:blipFill><a:blip xmlns:r="{X.NS_REL}" '
                f'r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:xfrm><a:off x="0" '
                f'y="0"/><a:ext cx="{cw * emu}" cy="{ch * emu}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
                f'</xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor>')
    if seq:
        p.extensao("jpeg", "image/jpeg")
    p.por_texto(dr, cab + "".join(novas) + pe)


def _vertical_preencher(p, vert, q, r, n, aba_mc, fim_mc, cq, teste, num, hoje):
    """Medições anteriores como valor (congeladas), a do mês com SUMIFS da nª MC, as seguintes em zero."""
    aba = p.aba(VERTICAL)
    _titulo(aba, "E1", teste)
    if num and isinstance(aba.valor("T2"), str) and "_____" in aba.valor("T2"):
        aba.texto("T2", aba.valor("T2").replace("_____", num))
    aba.texto("BF2", hoje.strftime("%d/%m/%Y"))
    fim = fim_mc
    adm_ant = {}
    for m in range(1, n):
        mes = dict(q.get(m, {}))
        mes.pop(CHAVE_ADM, None)
        adm_ant[m] = adm_local_por_vertical(vert, mes, r)
    for k, b in vert.items():
        lin = b["linha_origem"]
        for m in range(1, MEDICOES + 1):
            ref = f"{cq(m)}{lin}"
            if k == CHAVE_ADM:
                if m < n:
                    aba.numero(ref, adm_ant[m])
                elif m == n:
                    aba.formula(ref, f"'{aba_mc}'!$W${r['linha_adm']}")
                else:
                    aba.numero(ref, 0)
            elif m < n:
                aba.numero(ref, q.get(m, {}).get(k, 0))
            elif m == n:
                aba.formula(ref, f"IFERROR(SUMIFS('{aba_mc}'!$W$1:$W${fim},'{aba_mc}'!$C$1:$C${fim},$D{lin}),0)")
            else:
                aba.numero(ref, 0)


def adm_local_por_vertical(vert, q_mes, r):
    """ADM de uma medição anterior com os mesmos números da folha (percentual e total da ADM do contrato)."""
    adm = r["adm"]
    fat = sum(float(R.produto_excel(q, vert[k]["preco_unitario"] or 0)) for k, q in q_mes.items()
              if k in vert and str(vert[k]["classificacao"]).upper().startswith(("MATERIAL", "SERVI")))
    return (fat * adm["percentual"]) / adm["total_contrato"] if adm["total_contrato"] else 0.0


def _juntada_preencher(p, conn, vert, q_mes, r, n, teste, num):
    """Juntada impressa só com os itens medidos no mês: as outras linhas e as colunas das outras medições ficam ocultas."""
    aba = p.aba(JUNTADA)
    _titulo(aba, "A1", teste)
    if num and isinstance(aba.valor("P2"), str) and "_____" in aba.valor("P2"):
        aba.texto("P2", aba.valor("P2").replace("_____", num))
    codigos = {vert[k]["codigo_caesb"] for k, v in q_mes.items() if k in vert and k != CHAVE_ADM and abs(v) > 1e-12}
    if r["adm"]["quantidade"]:
        codigos.add(vert[CHAVE_ADM]["codigo_caesb"])
    junt = _rows(conn.execute("SELECT item, codigo_caesb, linha_origem FROM bm_itens WHERE planilha='JUNTADA' AND vigente=1"))
    medidos = {j["item"] for j in junt if j["codigo_caesb"] in codigos}
    linhas_itens = {j["linha_origem"] for j in junt}
    resumo_ini = next((lin for lin in sorted(aba.linhas) if aba.valor(f"A{lin}") == "RESUMO PRINCIPAL"), None)
    for lin in sorted(aba.linhas):
        if lin <= 5 or (resumo_ini and lin >= resumo_ini):
            continue
        a = aba.valor(f"A{lin}")
        a = str(a) if a is not None else ""
        if lin in linhas_itens:
            oculta = a not in medidos
        else:                                      # grupo e subgrupo: aparecem se algum item medido é deles
            oculta = not a or not any(i == a or i.startswith(a + ".") for i in medidos)
        aba.ocultar_linha(lin, oculta)
    outras = [COL_JUNTADA + 2 * (m - 1) + d for m in range(1, MEDICOES + 1) if m != n for d in (0, 1)]
    aba.ocultar_colunas(outras)
    aba.uma_pagina_de_largura()                    # A4 paisagem: P0, a medição do mês e o acumulado na mesma folha


def _reajuste_preencher(p, n, teste):
    """Fração elegível 0 nas medições até esta: reajuste R$ 0,00, não pedido (decisão do responsável)."""
    aba = p.aba(REAJUSTE)
    _titulo(aba, "A1", teste)
    for m in range(1, n + 1):
        lin = 23 + m
        aba.numero(f"E{lin}", 0)
        aba.numero(f"F{lin}", 0)
        aba.texto(f"I{lin}", "NÃO PEDIDO NESTA MEDIÇÃO (R$ 0,00)")


def _aba_avisos(p, r, hoje):
    """Aba no fim da pasta com o que o teste assume e o que ficou de fora (não existe no modelo oficial)."""
    med = r["medicao"]
    linhas = [f"MEDIÇÃO DE TESTE – NÃO OFICIAL · {med['numero']}ª medição · {med['periodo_ini']} a {med['periodo_fim']}",
              f"Gerada em {hoje.strftime('%d/%m/%Y')} pelo sistema Morro da Cruz", "",
              f"Total P0 da juntada (com BDI e K): R$ {r['totais']['juntada']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
              f"Administração local proporcional: {r['adm']['quantidade']:.6f} UN = R$ {r['adm']['valor']:,.2f}"
              .replace(",", "X").replace(".", ",").replace("X", "."), ""] + [f"• {a}" for a in r["avisos"]]
    corpo = "".join(f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t xml:space="preserve">{X.escape(t)}</t></is></c></row>'
                    for i, t in enumerate(linhas, 1))
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/'
           'spreadsheetml/2006/main"><dimension ref="A1"/><sheetViews><sheetView workbookViewId="0"/></sheetViews>'
           '<cols><col min="1" max="1" width="140" customWidth="1"/></cols>'
           f"<sheetData>{corpo}</sheetData></worksheet>")
    nums = [int(x) for x in re.findall(r"xl/worksheets/sheet(\d+)\.xml", " ".join(p.partes))]
    parte = f"xl/worksheets/sheet{max(nums) + 1}.xml"
    p.por_texto(parte, xml, "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
    rid = p.relacionar("xl/workbook.xml", "worksheet", parte)
    wb = p.texto("xl/workbook.xml")
    sid = max(int(x) for x in re.findall(r'sheetId="(\d+)"', wb)) + 1
    p.por_texto("xl/workbook.xml", wb.replace("</sheets>", f'<sheet name="{AVISOS}" sheetId="{sid}" r:id="{rid}"/></sheets>'))
