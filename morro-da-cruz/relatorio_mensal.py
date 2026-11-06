"""Relatório mensal (RM) da medição, em PDF e Word editável (D-207, D-217).

Os capítulos são os do RM do Lago Sul (modelo da Ankara, `references/modelo-lago-sul.md` §5) e o visual é o do
relatório técnico de conexões RC 01/2026: capa com o mapa das zonas, cabeçalho com o logo e 3 campos, Arial Narrow
(Helvetica condensada), títulos vinho, tabelas com cabeçalho azul-marinho e borda dupla vinho em toda página.

Tudo sai do banco, no período da medição escolhida: os valores e os itens da medição (como o pacote no BM REV04, com a
administração local proporcional), o previsto do cronograma FF (aba GRÁFICOS do BM), as atividades por semana
(intervalos executados, liberações, apropriações e ocorrências), as equipes e o efetivo (check-in e presenças), os tubos
da Caesb (almoxarifado), a locação e a execução por diâmetro, todas as fotos do mês e os mapas vetoriais do traçado.
O que o sistema ainda não guarda (CNO, vigência, responsáveis, instalações do canteiro, vistoria ambiental) sai em
amarelo como PENDENTE, nunca zero nem chute. Medição de TESTE sai marcada TESTE – NÃO OFICIAL (D-56).
"""
import json
import os
import re
import zipfile
from collections import defaultdict
from datetime import date, timedelta

import pacote_medicao as PM
import pdf_simples as P
import regras as R
import relatorios as REL
import servicos as S
from servicos import RegraViolada, _one, _rows

VINHO, VERMELHO, MARINHO, CINZA = "8B3430", "C0504D", "173B59", "595959"
AMARELO = "FFFF00"
AZUL, LARANJA, VERDE = "4472C4", "ED7D31", "70AD47"
CORES_DE = {63: "ff7f00", 90: "8a00b8", 110: "006edd", 125: "bf00ff", 160: "b80000", 225: "00c060", 250: "9f7fff",
            280: "5cb800", 315: "ff007f", 355: "00b0b0", 400: "0000ff", 500: "ff0000"}      # legenda do projeto (prancha 02/037)
CORES_ZONA = ["E8A87C", "7EC8E3", "B5D99C", "F5D76E", "C3A6D8", "8E7CC3", "F28CB1", "A3D9C9", "E06C9F", "9BC1E6",
              "E4C99A", "B0B0B0", "D9A441"]
MAX_FOTOS = 60
FOTOS_POR_PAGINA = 6
CAMINHO_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "relatorio_mensal.json")
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro",
         "dezembro"]


# ==================================================================== números e datas
def br(v, casas=2):
    if v is None:
        return "—"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def rs(v):
    return "—" if v is None else ("-R$ " if v < 0 else "R$ ") + br(abs(v))


def pct(v, casas=2):
    return "—" if v is None else br(v * 100, casas) + "%"


def dbr(iso, curto=False):
    if not iso:
        return "—"
    a, m, d = str(iso)[:10].split("-")
    return f"{d}/{m}/{a[2:] if curto else a}"


def _d(iso):
    return date.fromisoformat(str(iso)[:10])


def semanas(ini, fim):
    """Os períodos do capítulo 11, como no modelo: segunda a domingo; a 1ª semana leva os dias antes da 1ª segunda-feira
    (01/08 a 09/08, com 01/08 num sábado) e a última pode ter um dia só."""
    a, b = _d(ini), _d(fim)
    dom = a + timedelta(days=(7 - a.weekday()) % 7 + 6) if a.weekday() else a + timedelta(days=6)
    out, cur = [], a
    while cur <= b:
        dom = min(dom, b)
        out.append((cur.isoformat(), dom.isoformat()))
        cur = dom + timedelta(days=1)
        dom = cur + timedelta(days=6)
    return out


def config():
    with open(CAMINHO_CONFIG, encoding="utf-8") as f:
        return json.load(f)


# ==================================================================== dados
def _modelo_serial(v):
    return date(1899, 12, 30) + timedelta(days=int(v)) if isinstance(v, (int, float)) else None


def _do_modelo():
    """Do BM oficial: data da OS e prazo (aba REAJUSTE, B21 e D21), previsto mensal (aba GRÁFICOS) e o logo da Ankara."""
    out = {"os": None, "prazo": None, "previsto": None, "previsto_pct": None, "logo": None}
    caminho = PM.caminho_modelo()
    if not caminho:
        return out
    try:
        import xlsx_modelo as X
        with open(caminho, "rb") as f:
            dados = f.read()
        aba = X.Pacote(dados).aba(PM.REAJUSTE)
        out["os"], out["prazo"] = _modelo_serial(aba.valor("B21")), aba.valor("D21")
    except (KeyError, ValueError, OSError, zipfile.BadZipFile):
        return out
    try:
        from openpyxl import load_workbook
        import io
        g = load_workbook(io.BytesIO(dados), data_only=True, read_only=True)["GRÁFICOS"]
        for r in g.iter_rows(min_row=1, max_row=120, max_col=19, values_only=True):
            rot = str(r[0] or "").strip()
            vals = [v for v in r[1:19]]
            if rot == "PREVISTO R$/1000" and out["previsto"] is None and all(isinstance(v, (int, float)) for v in vals):
                out["previsto"] = [v * 1000 for v in vals]
            if rot == "% - PREVISTO" and out["previsto_pct"] is None and all(isinstance(v, (int, float)) for v in vals):
                out["previsto_pct"] = list(vals)
    except (KeyError, ValueError, OSError, zipfile.BadZipFile):
        pass
    try:                                                 # logo: a imagem do modelo com mais laranja que azul
        from PIL import Image
        import io
        z = zipfile.ZipFile(io.BytesIO(dados))
        melhor = None
        for n in z.namelist():
            if not n.startswith("xl/media/") or not n.lower().endswith(".png"):
                continue
            b = z.read(n)
            with Image.open(io.BytesIO(b)) as im:
                im = im.convert("RGBA")
                w, h = im.size
                if not 2.0 <= w / h <= 4.5:
                    continue
                raw = im.resize((40, 14)).tobytes()
                px = [tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)]
                px = [c for c in px if c[3] > 128 and sum(c[:3]) < 690]
                if px and sum(c[0] for c in px) > 1.3 * sum(c[2] for c in px):
                    melhor = melhor or b
        out["logo"] = melhor
    except Exception:                                    # noqa: BLE001 — sem logo, o cabeçalho sai só com o texto
        out["logo"] = None
    return out


def _valores(conn, med, vert):
    """Quantidades e totais da medição como o pacote no BM (juntada: ROUND por código Caesb), com a ADM proporcional."""
    q = PM.quantidades(conn, med)

    def do_mes(n):
        try:
            adm = PM.adm_local(conn, q[n], vert)
        except RegraViolada:                             # BM sem o item da ADM (planilha sintética): ADM fica de fora
            adm = {"quantidade": 0.0, "valor": 0.0, "percentual": None, "faturamento": None}
        mes = {k: v for k, v in q[n].items() if k != PM.CHAVE_ADM}
        if adm["quantidade"]:
            mes[PM.CHAVE_ADM] = adm["quantidade"]
        return mes, adm, PM.totais(conn, mes, vert)["juntada"]

    mes, adm, tot = do_mes(med["numero"])
    anteriores = {n: do_mes(n)[2]["total"] for n in range(1, med["numero"]) if q.get(n)}
    acum = defaultdict(float)
    for n, por in q.items():
        for k, v in por.items():
            acum[k] += v
    itens = []
    for k in sorted(mes, key=lambda k: (vert[k]["linha_origem"] if k in vert else 10 ** 9, k)):
        if k not in vert or abs(mes[k]) < 1e-12:
            continue
        b = vert[k]
        contrato = b["quantidade"]
        ac = acum[k] + (mes[k] if k == PM.CHAVE_ADM else 0)
        itens.append({"chave": k, "item": b["item_bm"], "descricao": b["descricao"], "unidade": b["unidade"],
                      "classificacao": b["classificacao"], "quantidade": mes[k],
                      "valor": float(R.produto_excel(mes[k], b["preco_unitario"] or 0)),
                      "contrato": contrato, "acumulado": ac,
                      "excede": contrato is not None and k != PM.CHAVE_ADM and acum[k] > float(contrato) + R.TOL_M})
    return {"itens": itens, "adm": adm, "totais": tot, "anteriores": anteriores}


def _trechos(conn):
    out = {}
    for t in _rows(conn.execute("SELECT id, ponto, frente_id, de_mm, metodologia, extensao_m, utm_ini, utm_fim FROM trechos "
                                "WHERE vigente=1")):
        try:
            a, b = json.loads(t["utm_ini"] or "null"), json.loads(t["utm_fim"] or "null")
        except ValueError:
            a = b = None
        t["seg"] = (a[0], a[1], b[0], b[1]) if a and b else None
        out[t["id"]] = t
    return out


def _por_de(conn, trechos, ini, fim):
    """Por diâmetro: previsto, locado (liberação topográfica: no mês e acumulado), cadastro aprovado, assentado no mês e
    acumulado (uniões de intervalos efetivos por trecho, para não contar duas vezes)."""
    def uniao(sql, args):
        por = defaultdict(list)
        for tid, a, b in conn.execute(sql, args):
            por[tid].append((a, b))
        return {tid: R.comprimento(R.unir_intervalos(l)) for tid, l in por.items()}

    lib_ac = uniao("SELECT trecho_id, ini_m, fim_m FROM etapas_complementares WHERE etapa='LIBERACAO_TOPOGRAFICA' "
                   "AND anulado_em IS NULL AND data<=?", (fim,))
    lib_mes = uniao("SELECT trecho_id, ini_m, fim_m FROM etapas_complementares WHERE etapa='LIBERACAO_TOPOGRAFICA' "
                    "AND anulado_em IS NULL AND data BETWEEN ? AND ?", (ini, fim))
    ass_ac = uniao(f"SELECT trecho_id, ini_m, fim_m FROM intervalos_execucao WHERE {S.EFETIVO} AND etapa='ASSENTADO' "
                   "AND data<=?", (fim,))
    ass_mes = uniao(f"SELECT trecho_id, ini_m, fim_m FROM intervalos_execucao WHERE {S.EFETIVO} AND etapa='ASSENTADO' "
                    "AND data BETWEEN ? AND ?", (ini, fim))
    ass_antes = uniao(f"SELECT trecho_id, ini_m, fim_m FROM intervalos_execucao WHERE {S.EFETIVO} AND etapa='ASSENTADO' "
                      "AND data<?", (ini,))
    aprovado = {r[0] for r in conn.execute("SELECT trecho_id FROM cadastro WHERE etapa='6_APROVADO'")}
    linhas = defaultdict(lambda: defaultdict(float))
    for tid, t in trechos.items():
        de = int(t["de_mm"] or 0)
        L = float(t["extensao_m"] or 0)
        d = linhas[de]
        d["previsto"] += L
        d["locado"] += min(lib_ac.get(tid, 0.0), L)
        d["locado_mes"] += min(lib_mes.get(tid, 0.0), L)
        d["cadastro"] += L if tid in aprovado else 0.0
        d["mes"] += min(ass_mes.get(tid, 0.0), L)
        d["acumulado"] += min(ass_ac.get(tid, 0.0), L)
        d["trechos"] += 1
    return dict(sorted(linhas.items())), {"mes": ass_mes, "antes": ass_antes}


def _atividades(conn, trechos, ini, fim):
    """O que foi feito em cada semana: execução por frente e etapa, liberações topográficas, apropriações e ocorrências."""
    out = []
    for a, b in semanas(ini, fim):
        ex = defaultdict(lambda: defaultdict(float))
        tr_sem = defaultdict(set)
        for tid, etapa, m in conn.execute(f"""SELECT trecho_id, etapa, fim_m - ini_m FROM intervalos_execucao
                                              WHERE {S.EFETIVO} AND data BETWEEN ? AND ?""", (a, b)):
            t = trechos.get(tid)
            fr = (t or {}).get("frente_id") or "—"
            ex[fr][etapa] += m
            tr_sem[fr].add(tid)
        lib = defaultdict(float)
        for tid, m in conn.execute("""SELECT trecho_id, fim_m - ini_m FROM etapas_complementares
                                      WHERE etapa='LIBERACAO_TOPOGRAFICA' AND anulado_em IS NULL AND data BETWEEN ? AND ?""",
                                   (a, b)):
            lib[(trechos.get(tid) or {}).get("frente_id") or "—"] += m
        aps = _rows(conn.execute("""SELECT id, data, item, quantidade, unidade, o_que_foi_feito, local_texto, local_tipo
                                    FROM apropriacoes WHERE estornado_em IS NULL AND data BETWEEN ? AND ? ORDER BY data, id""",
                                 (a, b)))
        ocs = _rows(conn.execute("SELECT data, tipo, categoria, descricao FROM ocorrencias WHERE data BETWEEN ? AND ? "
                                 "ORDER BY data, id", (a, b)))
        out.append({"ini": a, "fim": b, "execucao": {k: dict(v) for k, v in sorted(ex.items())},
                    "trechos": {k: sorted(v) for k, v in tr_sem.items()}, "liberacao": dict(lib),
                    "apropriacoes": aps, "ocorrencias": ocs})
    return out


def _equipes(conn, ini, fim):
    eq = _rows(conn.execute("""SELECT e.id,e.nome FROM equipes e WHERE e.ativa=1 OR EXISTS
        (SELECT 1 FROM checkins c WHERE c.equipe_id=e.id AND c.data BETWEEN ? AND ?) ORDER BY e.id""", (ini,fim)))
    func = {r[0]: r[1] for r in conn.execute("SELECT equipe_id, COUNT(*) FROM funcionarios GROUP BY 1")}
    maq = {r[0]: r[1] for r in conn.execute("SELECT equipe_id, COUNT(*) FROM maquinas GROUP BY 1")}
    dias = {r[0]: r[1] for r in conn.execute("SELECT equipe_id, COUNT(DISTINCT data) FROM checkins WHERE data BETWEEN ? AND ? "
                                             "GROUP BY 1", (ini, fim))}
    for e in eq:
        e["funcionarios"], e["maquinas"], e["dias"] = func.get(e["id"], 0), maq.get(e["id"], 0), dias.get(e["id"], 0)
    return eq


def _efetivo(conn, ini, fim):
    """Presenças do check-in no período: efetivo por dia, dias por colaborador (iniciais), funções e máquinas."""
    pres = _rows(conn.execute("""SELECT c.data, c.equipe_id, p.recurso_tipo, p.recurso_id FROM checkin_presencas p
                                 JOIN checkins c ON c.id=p.checkin_id WHERE c.data BETWEEN ? AND ?""", (ini, fim)))
    func = {r["id"]: r for r in _rows(conn.execute("SELECT id, nome, funcao, equipe_id FROM funcionarios"))}
    maq = {r["id"]: r for r in _rows(conn.execute("SELECT id, descricao, equipe_id FROM maquinas"))}
    por_dia = defaultdict(set)
    dias_func = defaultdict(set)
    maq_pres = defaultdict(set)
    equipe_func = defaultdict(set)
    for p in pres:
        if p["recurso_tipo"] == "FUNCIONARIO":
            por_dia[p["data"]].add(p["recurso_id"])
            dias_func[p["recurso_id"]].add(p["data"])
            equipe_func[p["equipe_id"]].add(p["recurso_id"])
        else:
            maq_pres[p["recurso_id"]].add(p["data"])
    funcoes = defaultdict(int)
    for fid in dias_func:
        funcoes[(func.get(fid) or {}).get("funcao") or "SEM FUNÇÃO NO CADASTRO"] += 1
    maquinas = defaultdict(lambda: [0, 0])
    for mid_, ds in maq_pres.items():
        d = (maq.get(mid_) or {}).get("descricao") or "SEM DESCRIÇÃO"
        maquinas[d][0] += 1
        maquinas[d][1] += len(ds)

    def iniciais(nome):
        partes = [x for x in str(nome or "").replace(".", " ").split() if len(x) > 2 or x.isupper()]
        return "".join(x[0].upper() for x in partes[:3]) or "?"

    colab = sorted(((f"{iniciais((func.get(f) or {}).get('nome'))}-{f}", len(ds)) for f, ds in dias_func.items()),
                   key=lambda x: (-x[1], x[0]))
    return {"por_dia": {d: len(s) for d, s in sorted(por_dia.items())}, "colaboradores": colab,
            "funcoes": dict(sorted(funcoes.items(), key=lambda x: (-x[1], x[0]))),
            "maquinas": {k: tuple(v) for k, v in sorted(maquinas.items())},
            "por_equipe": {e: len(s) for e, s in sorted(equipe_func.items())},
            "total": len(dias_func)}


def _materiais(conn, ini, fim):
    """Consumo do período (fornecimento da Ankara) e o estado dos tubos da Caesb (acumulado do almoxarifado)."""
    cons = _rows(conn.execute(f"""SELECT m.id, m.descricao, m.unidade, SUM(v.quantidade) q FROM movimentos v
        JOIN materiais m ON m.id=v.material_id WHERE {S.VALIDO.replace('id NOT IN', 'v.id NOT IN')}
        AND v.tipo IN ('APLICADO','CUSTODIA') AND substr(v.data, 1, 10) BETWEEN ? AND ? AND m.propriedade<>'CAESB'
        GROUP BY m.id ORDER BY q DESC LIMIT 40""", (ini, fim))) if _tem_coluna(conn, "movimentos", "data") else []
    de = lambda m: int((re.search(r"DE\s*(\d+)", str(m["descricao"]).upper()) or re.search(r"(\d+)", "0")).group(1))
    tubos = sorted((m for m in REL.materiais(conn) if m["propriedade"] == "CAESB" and "TUBO" in str(m["descricao"]).upper()),
                   key=lambda m: (de(m), m["descricao"]))
    return {"consumo": cons, "tubos": tubos}


def _tem_coluna(conn, tabela, coluna):
    return any(r[1] == coluna for r in conn.execute(f"PRAGMA table_info({tabela})"))


def _fotos(conn, ini, fim, dir_fotos):
    """Todas as fotos do mês (campo e apropriação direta), em ordem de data, com o carimbo gravado (até MAX_FOTOS)."""
    lista = []
    for f in _rows(conn.execute(f"""SELECT id, alvo_tipo, alvo_id, categoria, arquivo, data_hora, carimbo FROM fotos
                                    WHERE {S.FOTO_VALIDA} AND substr(data_hora, 1, 10) BETWEEN ? AND ?
                                    ORDER BY data_hora, id""", (ini, fim))):
        info = PM._alvo_info(conn, f["alvo_tipo"], f["alvo_id"])
        cat = {"SINALIZACAO": "sinalização", "EXECUCAO": "execução", "CONCLUIDO": "concluído"}.get(f["categoria"],
                                                                                                    f["categoria"].lower())
        f["legenda"] = f"{info['nome']} – {cat} ({dbr(f['data_hora'])})"
        lista.append(f)
    aps = [r[0] for r in conn.execute("SELECT id FROM apropriacoes WHERE estornado_em IS NULL AND data BETWEEN ? AND ?",
                                      (ini, fim))]
    for f in PM._candidatas_apropriacao(conn, aps):
        ap = _one(conn, "SELECT data, o_que_foi_feito, local_texto FROM apropriacoes WHERE id=?", int(f["alvo_id"])) or {}
        f["legenda"] = " – ".join(x for x in (ap.get("o_que_foi_feito"), ap.get("local_texto")) if x) + f" ({dbr(ap.get('data'))})"
        f["data_hora"] = f["data_hora"] or ap.get("data")
        lista.append(f)
    lista.sort(key=lambda f: (str(f["data_hora"] or ""), f["id"]))
    excedente = max(0, len(lista) - MAX_FOTOS)
    out = []
    for f in lista[:MAX_FOTOS]:
        dados = PM._bytes_foto(conn, f, dir_fotos) if dir_fotos or f.get("documento_id") else None
        img = PM.imagem_galeria(dados, f.get("carimbo"), lado=900) if dados else None
        out.append({"legenda": f["legenda"], "jpeg": img[0] if img else None})
    return out, excedente


def _programado(conn, fim):
    a = _d(fim) + timedelta(days=1)
    b = (date(a.year + a.month // 12, a.month % 12 + 1, 1) - timedelta(days=1))
    out = {}
    for eq, serv, q, x, y in conn.execute("""SELECT equipe_id, servico, COUNT(*), MIN(data), MAX(data) FROM programacoes
                                             WHERE status='PLANEJADA' AND data BETWEEN ? AND ? GROUP BY 1, 2""",
                                          (a.isoformat(), b.isoformat())):
        out[(eq, serv)] = (q, x, y)
    return out


def dados(conn, medicao_id, dir_fotos=None):
    med = PM._medicao(conn, medicao_id)
    ini, fim = med["periodo_ini"], med["periodo_fim"]
    vert = PM._vertical(conn)
    cfg = config()
    mod = _do_modelo()
    num, ano = PM._contrato_numero(conn)
    trechos = _trechos(conn)
    por_de, ass = _por_de(conn, trechos, ini, fim)
    fotos, fotos_fora = _fotos(conn, ini, fim, dir_fotos)
    valor_contrato = float(S.parametro(conn, "valor_contrato", 0) or 0)
    v = _valores(conn, med, vert)
    termino = mod["os"] + timedelta(days=int(mod["prazo"]) - 1) if mod["os"] and mod["prazo"] else None
    return {"medicao": med, "teste": med["tipo"] == "TESTE", "ini": ini, "fim": fim, "cfg": cfg, "modelo": mod,
            "contrato": f"{num[:-3]}.{num[-3:]}/{ano}" if num and len(num) > 3 else (S.contrato(conn) or "—"),
            "valor_contrato": valor_contrato, "p0_bm": float(S.parametro(conn, "p0_bm", 0) or 0),
            "fatores": S._fatores(conn), "termino": termino, **v,
            "trechos": trechos, "por_de": por_de, "assentado": ass,
            "semanas": _atividades(conn, trechos, ini, fim), "equipes": _equipes(conn, ini, fim),
            "efetivo": _efetivo(conn, ini, fim), "materiais": _materiais(conn, ini, fim),
            "fotos": fotos, "fotos_fora": fotos_fora, "proximo": _programado(conn, fim),
            "ocorrencias_abertas": conn.execute("SELECT COUNT(*) FROM ocorrencias WHERE resolvida_em IS NULL").fetchone()[0],
            "chuva": conn.execute("""SELECT COUNT(DISTINCT data) FROM (
                SELECT data FROM clima WHERE condicao='PARALISADO_CHUVA'
                UNION SELECT o.data FROM ocorrencia_chuvas c JOIN ocorrencias o ON o.id=c.ocorrencia_id
                  WHERE c.condicao='PARALISADO_CHUVA') WHERE data BETWEEN ? AND ?""", (ini, fim)).fetchone()[0]}


# ==================================================================== desenho
def _caixa(doc, p, x, y, w, h, linhas, fundo="FFFFFF", borda=VINHO, tam=7.5, negrito=False, cor_txt="000000"):
    doc.ret(p, x, y, w, h, fundo=fundo, borda=borda, lw=0.8)
    lh = tam * 1.2
    ls = [x for t in linhas for x in P.linhas_texto(t, w - 6, tam, negrito)]
    y0 = y + (h - len(ls) * lh) / 2 + tam * 0.9
    for i, t in enumerate(ls):
        doc.texto(p, x + (w - P.largura(t, tam, negrito)) / 2, y0 + i * lh, t, tam, negrito, False, cor_txt)


def _mapa(doc, p, x, y, w, h, camadas, rotulos=(), borda=True, janela=None):
    """camadas: [(cor, largura, [(E1, N1, E2, N2), …])] na ordem de desenho; rotulos: [(E, N, texto)];
    janela: (E0, N0, E1, N1) para aproximar (o que sai da janela é recortado)."""
    pts = [s for _, _, segs in camadas for s in segs]
    if not pts:
        doc.texto(p, x + 4, y + h / 2, "Sem traçado com coordenadas.", 8, False, True, CINZA)
        return
    if janela:
        e0, n0, e1, n1 = janela
    else:
        e0 = min(min(s[0], s[2]) for s in pts)
        e1 = max(max(s[0], s[2]) for s in pts)
        n0 = min(min(s[1], s[3]) for s in pts)
        n1 = max(max(s[1], s[3]) for s in pts)
    k = min((w - 12) / max(e1 - e0, 1), (h - 12) / max(n1 - n0, 1))
    ox = x + (w - (e1 - e0) * k) / 2
    oy = y + (h - (n1 - n0) * k) / 2
    X_ = lambda e: ox + (e - e0) * k
    Y_ = lambda n: oy + (n1 - n) * k
    if borda:
        doc.ret(p, x, y, w, h, borda="BFBFBF", lw=0.5)
    doc.recortar(p, x, y, w, h)
    for cor_, lw, segs in camadas:
        doc.tracos(p, [(X_(a), Y_(b), X_(c), Y_(d)) for a, b, c, d in segs], cor_, lw)
    for e, n, t in rotulos:
        if janela and not (e0 <= e <= e1 and n0 <= n <= n1):
            continue
        tw = P.largura(t, 7, True) + 6
        doc.ret(p, X_(e) - tw / 2, Y_(n) - 6, tw, 10, fundo="FFFFFF", borda="595959", lw=0.4)
        doc.texto(p, X_(e) - tw / 2 + 3, Y_(n) + 1.5, t, 7, True)
    doc.fim_recorte(p)


def _legenda(doc, p, x, y, w, itens, tam=7):
    """itens: [(cor, texto)] lado a lado, centrados."""
    larg = [12 + P.largura(t, tam) + 12 for _, t in itens]
    x0 = x + max(0, (w - sum(larg)) / 2)
    for (c, t), lw in zip(itens, larg):
        doc.ret(p, x0, y - tam * 0.8, 9, tam * 0.9, fundo=c)
        doc.texto(p, x0 + 12, y, t, tam)
        x0 += lw


def _grafico(doc, p, x, y, w, h, rotulos, barras=(), linhas=(), fmt=br, titulo="", destaque=None, fmt_eixo=None,
             eixo_unico=False, vmax=None):
    """Barras (eixo da esquerda) e linhas (eixo da direita, se houver barras). destaque: (série, índice) com o rótulo
    em amarelo, como o realizado do modelo."""
    fmt_eixo = fmt_eixo or fmt
    doc.texto(p, x + (w - P.largura(titulo, 9, True)) / 2, y + 10, titulo, 9, True)
    duas = bool(barras) and bool(linhas) and not eixo_unico
    px0, px1 = x + 52, x + w - (52 if duas else 12)
    py0, py1 = y + 22, y + h - 58
    n = len(rotulos)
    vb = max([v for _, vs, _ in barras for v in vs if v is not None] + [0]) * 1.18 or 1
    vl = max([v for _, vs, _ in linhas for v in vs if v is not None] + [0]) * 1.12 or 1
    if not barras or eixo_unico:
        vb = vl = max(vb, vl)
    if vmax:
        vb = vl = vmax
    doc.ret(p, px0, py0, px1 - px0, py1 - py0, borda="BFBFBF", lw=0.4)
    for i in range(6):
        yy = py1 - (py1 - py0) * i / 5
        doc.linha(p, px0, yy, px1, yy, "E6E6E6", 0.3)
        t = fmt_eixo(vb * i / 5)
        doc.texto(p, px0 - 3 - P.largura(t, 6), yy + 2, t, 6, cor_=CINZA)
        if duas:
            doc.texto(p, px1 + 3, yy + 2, fmt_eixo(vl * i / 5), 6, cor_=CINZA)
    slot = (px1 - px0) / max(n, 1)
    bw = slot * 0.78 / max(len(barras), 1)
    for j, (nome, vs, c) in enumerate(barras):
        for i, v in enumerate(vs):
            if v is None:
                continue
            xb = px0 + i * slot + slot * 0.11 + j * bw
            hb = (py1 - py0) * v / vb
            doc.ret(p, xb, py1 - hb, bw, hb, fundo=c)
            t = fmt(v)
            if destaque == (j, i):
                tw = P.largura(t, 6.5, True) + 4
                doc.ret(p, xb + bw / 2 - tw / 2, py1 - hb - 12, tw, 9, fundo=AMARELO, borda="999900", lw=0.3)
                doc.texto(p, xb + bw / 2 - tw / 2 + 2, py1 - hb - 5, t, 6.5, True)
            elif v and n <= 24:
                doc.texto_girado(p, xb + bw / 2 + 2, py1 - hb - 2, t, 5.5, cor_=CINZA)
    for nome, vs, c in linhas:
        k = (py1 - py0) / vl
        pts = [(px0 + (i + 0.5) * slot, py1 - v * k) for i, v in enumerate(vs) if v is not None]
        doc.poli(p, pts, c, 1.2)
        for xx, yy in pts:
            doc.circulo(p, xx, yy, 1.6, fundo=c)
    for i, r in enumerate(rotulos):
        doc.texto_girado(p, px0 + (i + 0.5) * slot + 2, py1 + 4 + P.largura(r, 6), r, 6)
    _legenda(doc, p, x, y + h - 6, w, [(c, nome) for nome, _, c in list(barras) + list(linhas)])


# ==================================================================== o documento
def gerar(conn, medicao_id, dir_fotos=None):
    d = dados(conn, medicao_id, dir_fotos)
    cache = {}
    for reservadas in (1, 2, 3):
        doc, _, n_tit = _montar(d, reservadas, cache)
        if n_tit <= reservadas * 58:
            break
    med = d["medicao"]
    nome = (f"RM_{med['numero']:02d}-{_d(d['fim']).year}_MORRO_DA_CRUZ_CT_{d['contrato'].replace('.', '').replace('/', '-')}"
            + ("_TESTE_NAO_OFICIAL" if d["teste"] else "") + ".pdf")
    return nome, doc.salvar(), d


def gerar_docx(conn, medicao_id, dir_fotos=None):
    """Mesmo conteúdo do RM em Word editável. Somente mapas, gráficos e fotos são imagens."""
    import docx_simples as D
    d = dados(conn, medicao_id, dir_fotos)
    import relatorio_word as RW
    RW.complementar(conn, d)
    doc = D.Documento()
    doc.paragrafo("Relatório mensal da obra Morro da Cruz", tam=22, alin="C", antes=28, depois=18, estilo="Title")
    doc.paragrafo(f"Contrato {d['contrato']} · RM {d['medicao']['numero']:02d}/{d['fim'][:4]}", tam=15, alin="C", depois=12)
    doc.paragrafo(f"Período de execução de {dbr(d['ini'])} a {dbr(d['fim'])}", tam=12, alin="C", depois=12)
    if d["teste"]:
        doc.paragrafo([("MEDIÇÃO DE TESTE – NÃO OFICIAL", {"negrito":True,"cor":"C00000"})], alin="C")
    zonas = sorted({t["frente_id"] or "—" for t in d["trechos"].values()})
    camadas = [(CORES_ZONA[i % len(CORES_ZONA)],1.1,[t["seg"] for t in d["trechos"].values() if t["seg"] and (t["frente_id"] or "—")==z]) for i,z in enumerate(zonas)]
    doc.figura(doc.w,320,lambda dr,p,x,y,w,h:_mapa(dr,p,x,y,w,h,camadas,_rotulos_zona(d["trechos"]),borda=False),"Traçado das redes da obra por zona")
    _corpo(d,doc,doc)
    nome = f"RM_{d['medicao']['numero']:02d}-{d['fim'][:4]}_MORRO_DA_CRUZ_CT_{d['contrato'].replace('.','').replace('/','-')}" + ("_TESTE_NAO_OFICIAL" if d["teste"] else "") + ".docx"
    return nome,doc.salvar(d),d


def _montar(d, reservadas, cache):
    cfg, med = d["cfg"], d["medicao"]
    rm = f"RM – {med['numero']:02d}/{_d(d['fim']).year}"
    periodo = f"{dbr(d['ini'], True)} a {dbr(d['fim'], True)}"
    doc = P.Documento(f"Relatório mensal {rm} – CT {d['contrato']}", cache)
    logo = doc.registrar_imagem(d["modelo"]["logo"], foto=False, max_px=400) if d["modelo"]["logo"] else None

    def moldura(doc, p):
        m = 22
        doc.ret(p, m, m, p.largura - 2 * m, p.altura - 2 * m, borda=VINHO, lw=0.9)
        doc.ret(p, m + 2.2, m + 2.2, p.largura - 2 * m - 4.4, p.altura - 2 * m - 4.4, borda=VINHO, lw=0.5)
        x0, x1, y = 48, p.largura - 48, 40
        if logo:
            iid, lw_, lh_ = logo
            k = 34 / lh_
            doc.imagem(p, iid, x0, y, lw_ * k, 34)
        else:
            doc.texto(p, x0, y + 22, "ANKARA", 14, True, False, LARANJA)
        cx = x0 + 110
        col = (x1 - cx) / 3
        for i, (rot, val) in enumerate((("Contrato número", d["contrato"]), ("Número do relatório", rm),
                                        ("Período de execução", periodo))):
            doc.texto(p, cx + i * col, y + 11, rot, 7.5, cor_=VERMELHO)
            doc.texto(p, cx + i * col, y + 26, val, 11, True, cor_=VERMELHO)
        doc.linha(p, x0, y + 38, x1, y + 38, "7F7F7F", 0.6)
        if d["teste"]:
            t = "MEDIÇÃO DE TESTE – NÃO OFICIAL (D-56)"
            doc.texto(p, (p.largura - P.largura(t, 7.5, True)) / 2, y + 48, t, 7.5, True, cor_="C00000")
        return x0, y + 56, x1, p.altura - 52

    def rodape(doc, p, i, n):
        t = f"Página {i} | {n}"
        doc.texto(p, p.largura - 48 - P.largura(t, 8), p.altura - 34, t, 8)

    # capa
    capa = doc.nova_pagina()
    x0, y0, x1, y1 = moldura(doc, capa)
    W = x1 - x0
    for i, (t, tam) in enumerate(((cfg["obra"]["nome_caixa_alta"], 13), (cfg["obra"]["local_capa"], 13))):
        doc.texto(capa, x0 + (W - P.largura(t, tam, True)) / 2, y0 + 22 + i * 16, t, tam, True, cor_=VERMELHO)
    for i, t in enumerate(("RELATÓRIO MENSAL", f"CONTRATO {d['contrato'].replace('/20', '/')}")):
        doc.texto(capa, x0 + (W - P.largura(t, 34, True)) / 2, y0 + 92 + i * 40, t, 34, True, cor_=VERMELHO)
    for i, t in enumerate((f"RELATÓRIO MENSAL DE ATIVIDADES – {rm.replace('–', '').replace('  ', ' ')}",
                           f"{med['numero']:02d}ª MEDIÇÃO – PERÍODO DE {dbr(d['ini'])} A {dbr(d['fim'])}")):
        doc.texto(capa, x0 + (W - P.largura(t, 12, True)) / 2, y0 + 166 + i * 15, t, 12, True, cor_=VERMELHO)
    zonas = sorted({t["frente_id"] or "—" for t in d["trechos"].values()})
    cores = {z: CORES_ZONA[i % len(CORES_ZONA)] for i, z in enumerate(zonas)}
    camadas = [(cores[z], 1.1, [t["seg"] for t in d["trechos"].values() if t["seg"] and (t["frente_id"] or "—") == z])
               for z in zonas]
    _mapa(doc, capa, x0, y0 + 196, W, y1 - y0 - 200, camadas, _rotulos_zona(d["trechos"]), borda=False)
    # sumário (preenchido depois do fluxo)
    sumarios = [doc.nova_pagina() for _ in range(reservadas)]
    fl = P.Fluxo(doc, moldura, rodape, cor_titulo=VINHO)
    fl._cont[0] = 1                                      # o sumário é o capítulo 1
    _corpo(d, doc, fl)
    titulos = fl.titulos
    linhas = [(1, "1", "SUMÁRIO", None)] + titulos
    for k, pg in enumerate(sumarios):
        x0, y0, x1, y1 = moldura(doc, pg)
        y = y0 + 12
        if k == 0:
            doc.texto(pg, x0, y + 4, "1", 12, True, True, VINHO)
            doc.texto(pg, x0 + 20, y + 4, "SUMÁRIO", 12, True, True, VINHO)
            y += 24
        for nivel, num, texto, pag in linhas[1 + k * 58: 1 + (k + 1) * 58]:
            tam = 9
            rec = (nivel - 1) * 12
            t = f"{num} {texto.upper() if nivel == 1 else texto}"
            t = t if P.largura(t, tam, nivel == 1) < x1 - x0 - rec - 30 else t[:110] + "…"
            doc.texto(pg, x0 + rec, y, t, tam, nivel == 1)
            ps = str(pag)
            doc.texto(pg, x1 - P.largura(ps, tam), y, ps, tam)
            ini = x0 + rec + P.largura(t, tam, nivel == 1) + 3
            fimx = x1 - P.largura(ps, tam) - 3
            if fimx > ini:
                pontos = "." * int((fimx - ini) / P.largura(".", tam))
                doc.texto(pg, fimx - P.largura(pontos, tam), y, pontos, tam, cor_=CINZA)
            y += 11.6
    fl.fechar()
    return doc, fl, len(titulos)


def _rotulos_zona(trechos):
    pos = defaultdict(list)
    for t in trechos.values():
        if t["seg"] and t["frente_id"]:
            pos[t["frente_id"]].append(((t["seg"][0] + t["seg"][2]) / 2, (t["seg"][1] + t["seg"][3]) / 2))
    out = []
    for z, ps in sorted(pos.items()):
        nome = z.replace("Zona", "ZONA ") if z.startswith("Zona") else z
        out.append((sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps), nome))
    return out


def _pend(t):
    return [("PENDENTE: ", {"negrito": True, "fundo": AMARELO}), (t, {"fundo": AMARELO})]


def _celula_pend(v, texto="PENDENTE"):
    return {"t": texto, "destaque": AMARELO} if v in (None, "") else v


def _corpo(d, doc, fl):
    import relatorio_word as RW
    word = bool(getattr(fl, "editavel", False))
    cfg, med = d["cfg"], d["medicao"]
    ct, ob, cn = cfg["contratada"], cfg["obra"], cfg["contratante"]
    n = med["numero"]
    nª = f"{n:02d}ª"
    tot = d["totais"]
    ini, fim = d["ini"], d["fim"]
    mes_nome = f"{MESES[_d(fim).month - 1].capitalize()}/{_d(fim).year}"
    valor = tot["total"]

    # 2 e 3 -------------------------------------------------------------------------------------------------------
    fl.titulo(1, "Apresentação", nova_pagina=True)
    fl.paragrafo(f"A {ct['razao_social']}., com sede na cidade de {ct['cidade_sede']}, na {ct['sede']}, para a execução "
                 f"completa e perfeita da {ob['nome_caixa_alta']}, em São Sebastião/DF – objeto do edital de licitação "
                 f"{ob['licitacao']} da {cn['orgao']}, apresenta o Relatório Mensal de Atividades {fl_rm(d)}, referente ao "
                 f"período de {dbr(ini)} a {dbr(fim)} ({nª} medição) do Contrato nº {d['contrato']}.")
    fl.titulo(1, "Identificação")
    linhas = [["CAMPO", "DADOS"]]
    blocos = [("EMPRESA", [("Razão social", ct["razao_social"]), ("CNPJ", ct["cnpj"]), ("CNAE", ct["cnae"]),
                           ("Atividade principal", ct["atividade"]), ("Endereço da sede", ct["sede"])]),
              ("CONTRATANTE", [("Órgão", cn["orgao"]), ("CNPJ", cn["cnpj"]), ("CNAE", cn["cnae"]),
                               ("Grau de risco", cn["grau_risco"]), ("Área gestora", cn["area_gestora"])]),
              ("OBRA", [("Obra", ob["nome"]), ("Objeto", f"{ob['objeto']} – {ob['licitacao']} – {ob['projeto']}"),
                        ("CNO", ob.get("cno")), ("CNAE / grau de risco", ob["cnae_grau"]), ("Canteiro de obras", ob["canteiro"]),
                        ("Horário de trabalho", ob["horario"])]),
              ("RESPONSÁVEIS", [(r, None) for r in cfg["responsaveis"]])]
    for bloco, campos in blocos:
        linhas.append([{"t": bloco, "span": 2, "fundo": "F2E6E5", "negrito": True, "cor": VINHO}])
        for c, v in campos:
            linhas.append([{"t": c, "negrito": True}, _celula_pend(v, "PENDENTE (nome, cargo e registro, do cadastro da obra)"
                                                                   if bloco == "RESPONSÁVEIS" else "PENDENTE")])
    fl.tabela([0.3, 0.7], linhas, tam=8)
    fl.paragrafo([("Telefones e e-mails dos responsáveis não constam deste relatório. Os dados em amarelo ainda não estão "
                   "no sistema.", {"italico": True, "cor": CINZA})], tam=8)

    # 4 -------------------------------------------------------------------------------------------------------------
    fl.titulo(1, "Do Empreendimento", nova_pagina=True)
    fl.titulo(2, "Características Gerais do Empreendimento")
    pd = d["por_de"]
    ext = sum(v["previsto"] for v in pd.values())
    ntr = sum(int(v["trechos"]) for v in pd.values())
    nmnd = sum(1 for t in d["trechos"].values() if str(t["metodologia"] or "").upper() == "MND")
    fl.paragrafo(f"O presente documento tem como objetivo apresentar os materiais e serviços a serem fornecidos para a "
                 f"{ob['nome_caixa_alta'].lower()}, localizada na {ob['localizacao']}, conforme o Projeto Básico "
                 f"{ob['projeto']}.")
    fl.paragrafo(f"Esta implantação de redes desenvolverá percurso de {br(ext)} m de extensão, em {ntr} trechos, nos "
                 f"diâmetros DE {', DE '.join(str(k) for k in pd if k)} mm em PEAD"
                 + (f", dos quais {nmnd} pelo método não destrutivo (MND)." if nmnd else "."))
    fl.paragrafo([("Mapa Geral do Morro da Cruz – Figura 01:", {"negrito": True})], alin="E", junto=True)
    camadas = []
    for de in sorted({int(t["de_mm"] or 0) for t in d["trechos"].values()}):
        camadas.append((CORES_DE.get(de, "666666"), 1.6 if de >= 225 else 0.7,
                        [t["seg"] for t in d["trechos"].values() if t["seg"] and int(t["de_mm"] or 0) == de]))

    def fig01(doc, p, x, y, w, h):
        _mapa(doc, p, x, y, w, h - 26, camadas, _rotulos_zona(d["trechos"]))
        _legenda(doc, p, x, y + h - 14, w, [(CORES_DE.get(de, "666666"), f"DE {de}") for de in sorted(CORES_DE)
                                           if any(int(t["de_mm"] or 0) == de for t in d["trechos"].values())], 6.5)
    fl.figura(fl.w, 470, fig01, "Figura 01 – Mapa geral das redes de distribuição do Morro da Cruz, por diâmetro (projeto "
                                "RED.SSB-D014).")

    # 5, 6, 7 ---------------------------------------------------------------------------------------------------------
    fl.titulo(1, "Dados Contratuais do Empreendimento", nova_pagina=True)
    os_, prazo = d["modelo"]["os"], d["modelo"]["prazo"]
    fl.tabela([0.35, 0.65], [
        ["CAMPO", "INFORMAÇÃO"],
        ["Objeto do contrato", ob["nome"]], ["Localização", ob["localizacao"]], ["Contratada", ct["razao_social"].title()],
        ["Número do contrato", f"{d['contrato']} – assinado em {ob['assinatura']} e publicado em {ob['publicacao']}"],
        ["Processo", ob["processo"]], ["Valor inicial do contrato", rs(d["valor_contrato"])],
        ["Contratante", f"{cn['sigla']} – {cn['orgao'].split(' – ')[0]}"],
        ["Data de início da execução", _celula_pend(os_ and f"{os_.strftime('%d/%m/%Y')} (Ordem de Serviço)")],
        ["Data de conclusão da execução", _celula_pend(d["termino"] and d["termino"].strftime("%d/%m/%Y"))],
        ["Prazo de execução", _celula_pend(prazo and f"{int(prazo)} dias consecutivos")],
        ["Prazo de vigência", _celula_pend(ob.get("vigencia_dias") and f"{ob['vigencia_dias']} dias consecutivos",
                                           "PENDENTE (conferir no contrato)")],
    ])
    fl.paragrafo([("Tabela 01 – Dados contratuais do empreendimento.", {"italico": True, "cor": CINZA})], tam=8, alin="C")
    fl.titulo(1, "Quadro Resumo Gerencial do Contrato")
    fl.tabela([0.62, 0.22, 0.16], [
        ["RESUMO", "VALOR", "%"],
        ["Valor inicial do contrato", rs(d["valor_contrato"]), "100,00%"],
        ["Valor do contrato – reprogramação 01", rs(0), "—"], ["Valor do contrato – reprogramação 02", rs(0), "—"],
        ["Valor dos acréscimos", rs(0), "0,00%"], ["Valor dos decréscimos", rs(0), "0,00%"],
        ["Valor aditivado", rs(0), "0,00%"],
        ["Valor do reajuste do contrato (pedido até esta medição)", rs(0), "0,00%"],
        ["Valor total do contrato aditivado e reajustado", rs(d["valor_contrato"]), "100,00%"],
    ], alin=["E", "D", "D"], total=True)
    aditivo = [i for i in d["itens"] if i["excede"]]
    fl.paragrafo([("Tabela 02 – Quadro resumo gerencial. Sem reprogramação nem aditivo registrado no sistema"
                   + (f"; {len(aditivo)} item(ns) com acumulado acima do contrato aguardam aditivo (capítulo 17)." if aditivo else "."),
                   {"italico": True, "cor": CINZA})], tam=8, alin="C")
    fl.titulo(1, "Dados Gerenciais Contratual do Empreendimento")
    acum = valor + sum(d["anteriores"].values())
    decorrido = (_d(fim) - d["modelo"]["os"]).days + 1 if d["modelo"]["os"] else None
    fl.tabela([0.66, 0.34], [
        ["INDICADOR", "VALOR"],
        [f"Valor faturado acumulado até a {nª} medição do contrato (P0)", rs(acum)],
        [f"Valor faturado reajustado acumulado até a {nª} medição do contrato", rs(0)],
        [f"Valor da {nª} medição do mês atual do contrato (P0, com BDI e coeficiente K)", rs(valor)],
        [f"Valor do reajuste da {nª} medição do mês atual do contrato", "R$ 0,00 (não pedido)"],
        ["Valor do saldo do contrato (P0)", rs(d["valor_contrato"] - acum)],
        ["Prazo de execução decorrido", _celula_pend(decorrido and f"{decorrido} dias consecutivos")],
        ["Prazo de execução restante", _celula_pend(decorrido and prazo and f"{int(prazo) - decorrido} dias consecutivos")],
        ["Prazo de vigência decorrido", _celula_pend(decorrido and f"{decorrido} dias consecutivos")],
        ["Prazo de vigência restante", _celula_pend(None, "PENDENTE (data limite da vigência no contrato)")],
    ], alin=["E", "D"])
    fl.paragrafo([("Tabela 03 – Dados gerenciais do contrato.", {"italico": True, "cor": CINZA})], tam=8, alin="C")

    # 8 a 10 ---------------------------------------------------------------------------------------------------------
    fl.titulo(1, "Desenvolvimento dos Trabalhos", nova_pagina=True)
    fl.paragrafo("Montagem do canteiro de obra e disponibilização de máquinas, equipamentos e pessoal para execução das "
                 "atividades, conforme descritos no relatório abaixo:")
    if word:
        RW.canteiro(d, fl)
    else:
        fl.paragrafo(_pend("croqui da área de instalação do canteiro (Imagem 01 – 1ª locação, Imagem 02 – localização e Imagem 03 – "
                           "layout atual). O layout do canteiro ainda não é guardado no sistema."))
        fl.titulo(2, "Composição do Canteiro de Obras")
        aps_canteiro = [a for s in d["semanas"] for a in s["apropriacoes"] if a["local_tipo"] == "CANTEIRO"]
        for a in aps_canteiro:
            fl.paragrafo(f"{a['o_que_foi_feito']} – {br(a['quantidade'])} {a['unidade']} ({dbr(a['data'])});", marcador=True,
                         depois=2)
        fl.paragrafo(_pend("instalações do canteiro (contêineres, almoxarifado, refeitório, vestiário, WC, baias e depósitos), com "
                           "as dimensões e as áreas, conforme o layout atualizado; área total e área construída."))
    fl.titulo(1, "Organograma da Obra – 1ª parte", nova_pagina=True)
    fl.figura(fl.w, 330, lambda doc_, p, x, y, w, h: _org1(doc_, p, x, y, w, h, cfg),
              "Imagem 04 – Organograma da obra: contratada e fiscalização da CAESB.")
    fl.titulo(1, "Organograma da Obra – 2ª parte")
    fl.figura(fl.w, 250, lambda doc_, p, x, y, w, h: _org2(doc_, p, x, y, w, h, d), "Imagem 05 – Frentes de serviço do "
              "cadastro de equipes do sistema e as terceirizadas.")

    # 11 ------------------------------------------------------------------------------------------------------------
    fl.titulo(1, "Principais Atividades Realizadas no Período:", nova_pagina=True)
    if word:
        RW.semanas(d, fl)
    else:
        for s in d["semanas"]:
            fl.titulo(2, f"Período de {dbr(s['ini'])} até {dbr(s['fim'])}:")
            nada = True
            for fr, et in s["execucao"].items():
                nada = False
                fl.paragrafo([(f"MORRO DA CRUZ – {_frente(fr)}:", {"negrito": True})], alin="E", depois=2, junto=True)
                trs = s["trechos"].get(fr, [])
                fl.paragrafo(f"Trechos: {', '.join(d['trechos'][t]['ponto'] for t in trs[:12] if t in d['trechos'])}"
                             + ("…" if len(trs) > 12 else "") + ".", tam=8.5, depois=2)
                for etapa, m in et.items():
                    fl.paragrafo(f"{_etapa(etapa)} – {br(m)} m;", marcador=True, depois=2)
            for fr, m in s["liberacao"].items():
                nada = False
                fl.paragrafo(f"Locação topográfica com NS – {_frente(fr)} – {br(m)} m;", marcador=True, depois=2)
            if s["apropriacoes"]:
                nada = False
                fl.paragrafo([("SERVIÇOS (apropriação direta):", {"negrito": True})], alin="E", depois=2, junto=True)
                for a in s["apropriacoes"]:
                    fl.paragrafo(f"{a['o_que_foi_feito']} – {br(a['quantidade'])} {a['unidade']}"
                                 + (f" – {a['local_texto']}" if a["local_texto"] else "") + f" ({dbr(a['data'])}, item {a['item']});",
                                 marcador=True, depois=2)
            for o in s["ocorrencias"]:
                nada = False
                fl.paragrafo(f"{o['tipo'].replace('_', ' ').title()} ({dbr(o['data'])}): {o['descricao'] or o['categoria'] or ''};",
                             marcador=True, depois=2)
            if nada:
                fl.paragrafo([("Sem serviço registrado no sistema nesta semana.", {"italico": True, "cor": CINZA})], depois=4)
            tr_sem = {t for v in s["trechos"].values() for t in v}
            if tr_sem:
                fl.paragrafo([("Croqui de locação da semana:", {"negrito": True})], alin="E", depois=2, junto=True)
                fl.figura(fl.w, 230, lambda doc_, p, x, y, w, h, tr_sem=tr_sem: _croqui(doc_, p, x, y, w, h, d, tr_sem),
                          "Vermelho: executado na semana · amarelo: executado antes · azul: não executado.")

    # 12 ------------------------------------------------------------------------------------------------------------
    fl.titulo(1, "Materiais e Equipamentos", nova_pagina=True)
    fl.titulo(2, "Dimensionamento das Equipes de Trabalho:")
    fl.paragrafo(f"Disposição de máquinas, ferramentas e acessórios das frentes de serviços para metodologia tipo \"VCA – vala "
                 f"a céu aberto\" ou tipo \"MND – método não destrutivo\", para andamento da execução dos serviços referentes à "
                 f"{ob['nome_caixa_alta']}, tais como apresentados na tabela abaixo:")
    if word:
        RW.equipes(d, fl)
    else:
        linhas = [["TIPOLOGIA", "ID EQUIPE", "DESCRIÇÃO", "FUNCIONÁRIOS (CADASTRO)", "MÁQUINAS (CADASTRO)", "DIAS COM CHECK-IN",
                   "SITUAÇÃO"]]
        for e in d["equipes"]:
            linhas.append(["ANKARA / EMPREITEIRA", e["id"], e["nome"], str(e["funcionarios"]), str(e["maquinas"]), str(e["dias"]),
                           "ATIVA NO PERÍODO" if e["dias"] else "SEM CHECK-IN NO PERÍODO"])
        for ide, desc in cfg["terceirizadas"]:
            linhas.append(["TERCEIRIZADA", ide, desc, "—", "—", "—", "REGISTRADA PELA ENGENHARIA"])
        fl.tabela([0.14, 0.1, 0.26, 0.12, 0.12, 0.11, 0.15], linhas, tam=7.5, alin=["C", "C", "E", "D", "D", "D", "C"])
        fl.paragrafo([("Tabela 04 – Resumo ID-equipes (cadastro de equipes, funcionários e máquinas do sistema e check-in do "
                       "período).", {"italico": True, "cor": CINZA})], tam=8, alin="C")
    fl.titulo(2, "Materiais:")
    fl.titulo(3, "Materiais de Consumo Diário (Fornecimento ANKARA ENGENHARIA), tais como:")
    if d["materiais"]["consumo"]:
        for m in d["materiais"]["consumo"]:
            fl.paragrafo(f"{m['descricao']} – {br(m['q'])} {m['unidade']};", marcador=True, depois=2)
    else:
        fl.paragrafo([("Sem saída de material da Ankara para as equipes registrada no período.", {"italico": True,
                                                                                               "cor": CINZA})])
    fl.titulo(3, "Status Entrega de Materiais (Fornecimento CAESB – Tubos PEAD):", paisagem=True if word else None)
    fl.paragrafo(f"Situação referente à entrega / execução dos materiais para a {ob['nome_caixa_alta']}, conforme tabela abaixo:")
    if word:
        RW.tubos(d, fl)
    else:
        linhas = [["MATERIAL", "UNID.", "LEVANT. DE PROJETO", "RECEBIDO (ROMANEIO)", "EMPRESTADO", "COM AS EQUIPES", "APLICADO",
                   "SALDO ALMOX.", "% EXECUTADO"]]
        for m in d["materiais"]["tubos"]:
            linhas.append([m["descricao"], m["unidade"], br(m["previsto"]), br(m["recebido"]), br(m["emprestado"]),
                           br(m["com_equipes"]), br(m["aplicado"]), br(m["saldo_almox"]),
                           pct(m["aplicado"] / m["previsto"]) if m["previsto"] else "—"])
        if len(linhas) == 1:
            linhas.append([{"t": "Sem tubo da CAESB no cadastro de materiais.", "span": 9}])
        fl.tabela([0.3, 0.06, 0.09, 0.1, 0.08, 0.09, 0.08, 0.09, 0.11], linhas, tam=7, alin=["E", "C"] + ["D"] * 7)
        fl.paragrafo([("Tabela 05 – Compatibilização de tubos (almoxarifado: romaneios da CAESB, saídas, aplicado e saldo). "
                       "% executado = aplicado ÷ levantamento de projeto.", {"italico": True, "cor": CINZA})], tam=8, alin="C")

    # 13 e 14 ---------------------------------------------------------------------------------------------------------
    fl.titulo(1, "Execução de Obras:")
    fl.titulo(2, "Redes de Água:")
    fl.titulo(3, "Locação Topográfica (C/ NS) de Redes do Morro da Cruz;", paisagem=True if word else None)
    t_prev = sum(v["previsto"] for v in pd.values())
    s_ = lambda k: sum(v[k] for v in pd.values())
    if word:
        RW.redes(d, fl)
    else:
        linhas = [["DESCRIÇÃO", "DE (mm)", "PREVISTO PROJETO (m)", "LOCADO NO MÊS (m)", "LOCADO ACUMULADO (m)",
                   "CADASTRO TÉCNICO (m)", "PENDENTE LOCAÇÃO (m)", "% CADASTRADO", "% LOCADO"]]
        for de, v in pd.items():
            linhas.append(["TUBO PEAD", str(de), br(v["previsto"]), br(v["locado_mes"]), br(v["locado"]), br(v["cadastro"]),
                           br(max(v["previsto"] - v["locado"], 0)), pct(v["cadastro"] / v["previsto"] if v["previsto"] else None),
                           pct(v["locado"] / v["previsto"] if v["previsto"] else None)])
        s_ = lambda k: sum(v[k] for v in pd.values())
        linhas.append(["TOTAL", "", br(t_prev), br(s_("locado_mes")), br(s_("locado")), br(s_("cadastro")),
                       br(max(t_prev - s_("locado"), 0)), pct(s_("cadastro") / t_prev if t_prev else None),
                       pct(s_("locado") / t_prev if t_prev else None)])
        fl.tabela([0.14, 0.07, 0.12, 0.11, 0.12, 0.12, 0.12, 0.1, 0.1], linhas, tam=7, alin=["E", "C"] + ["D"] * 7, total=True)
        fl.paragrafo([("Tabela 06 – Locação topográfica (liberações com NS registradas no sistema) e cadastro técnico aprovado.",
                       {"italico": True, "cor": CINZA})], tam=8, alin="C")
    fl.titulo(3, "Execução do Morro da Cruz, Rede Acumulada;", paisagem=True if word else None)
    if word:
        RW.redes(d, fl, execucao=True)
    else:
        linhas = [["DESCRIÇÃO", "DE (mm)", "LEVANT. DE PROJETO (m)", "EXECUTADO NO MÊS (m)", "EXECUTADO ACUMULADO (m)", "% PENDENTE",
                   "% EXECUTADO"]]
        for de, v in pd.items():
            p_ = v["acumulado"] / v["previsto"] if v["previsto"] else None
            linhas.append(["TUBO PEAD", str(de), br(v["previsto"]), br(v["mes"]), br(v["acumulado"]),
                           pct(1 - p_ if p_ is not None else None), pct(p_)])
        p_ = s_("acumulado") / t_prev if t_prev else None
        linhas.append(["TOTAL", "", br(t_prev), br(s_("mes")), br(s_("acumulado")), pct(1 - p_ if p_ is not None else None), pct(p_)])
        fl.tabela([0.16, 0.08, 0.16, 0.16, 0.16, 0.14, 0.14], linhas, tam=7, alin=["E", "C"] + ["D"] * 5, total=True)
        fl.paragrafo([("Tabela 07 – Execução das redes (assentado: intervalos efetivos do sistema).", {"italico": True,
                                                                                                    "cor": CINZA})], tam=8,
                     alin="C")
    fl.titulo(2, f"Serviços Medidos na {nª} Medição", paisagem=False if word else None)
    linhas = [["ITEM", "SERVIÇO", "UNID.", "QUANT.", "VALOR (SEM BDI)"]]
    for i in d["itens"]:
        linhas.append([i["item"], i["descricao"] + (" (acima do contrato: aditivo pendente)" if i["excede"] else ""),
                       i["unidade"], br(i["quantidade"], 8 if i["chave"] == PM.CHAVE_ADM else 2), rs(i["valor"])])
    sub = tot["material"] + tot["servico"]
    bdi = float(tot["bdi_material"]) + float(tot["bdi_servico"])
    fm, fs, fk = d["fatores"]
    linhas += [["", "SUBTOTAL (SEM BDI)", "", "", rs(sub)],
               ["", f"BDI MATERIAL ({pct(fm)}) + SERVIÇO ({pct(fs)})", "", "", rs(bdi)],
               ["", f"COEFICIENTE K ({pct(fk)})", "", "", rs(float(tot["k"]))],
               ["", f"TOTAL DA {nª} MEDIÇÃO (P0)", "", "", rs(valor)]]
    fl.tabela([0.1, 0.56, 0.07, 0.12, 0.15], linhas, tam=7.5, alin=["C", "E", "C", "D", "D"], total=True)
    fl.paragrafo([("Tabela 08 – Serviços medidos (lançamentos PROPOSTOS da medição, valores como a juntada do BM REV04, com a "
                   "administração local proporcional).", {"italico": True, "cor": CINZA})], tam=8, alin="C")
    fl.titulo(1, "Principais Atividades Previstas para o Próximo Mês")
    prox = _proximo(d) + (d.get("word_previstas", []) if word else [])
    for t in prox:
        fl.paragrafo(t, marcador=True, depois=2)
    if not prox:
        fl.paragrafo(_pend("atividades previstas para o próximo mês (programação e cronograma)."))

    # 15 e 16 (paisagem) -----------------------------------------------------------------------------------------------
    fl.titulo(1, "Cronograma e Gráficos", paisagem=True)
    prev = d["modelo"]["previsto"]
    nmes = 18
    real = [None] * nmes
    for k, vv in d["anteriores"].items():
        if k <= nmes:
            real[k - 1] = vv
    if n <= nmes:
        real[n - 1] = valor
    fl.titulo(2, "Cronograma Físico Financeiro;")
    contrato = d["p0_bm"] or d["valor_contrato"] or 1
    if prev:
        pac = [sum(prev[:i + 1]) for i in range(nmes)]
        rac = [sum(v for v in real[:i + 1] if v) if i < n else None for i in range(nmes)]
        cab = ["MÊS"] + [f"{i + 1:02d}" for i in range(nmes)]
        linhas = [cab,
                  ["PREVISTO (R$ mil)"] + [br(v / 1000, 1) for v in prev],
                  ["PREVISTO (%)"] + [pct(v / contrato) for v in prev],
                  ["PREVISTO ACUM. (%)"] + [pct(v / contrato) for v in pac],
                  ["REALIZADO (R$ mil)"] + [br(v / 1000, 1) if v is not None else "" for v in real],
                  ["REALIZADO (%)"] + [pct(v / contrato) if v is not None else "" for v in real],
                  ["REALIZADO ACUM. (%)"] + [pct(v / contrato) if v is not None else "" for v in rac]]
        fl.tabela([0.12] + [0.88 / nmes] * nmes, linhas, tam=6.5, alin=["E"] + ["D"] * nmes)
        fl.paragrafo([(f"Tabela 09 – Cronograma físico-financeiro (previsto da aba GRÁFICOS do BM; realizado das medições do "
                       f"sistema): previsto {rs(prev[n - 1])} e realizado {rs(valor)} no mês {n:02d}.",
                       {"italico": True, "cor": CINZA})], tam=8, alin="C")
    else:
        fl.paragrafo(_pend("cronograma físico-financeiro previsto (aba GRÁFICOS do BM oficial ausente)."))
        prev = [None] * nmes
        pac = [None] * nmes
        rac = [sum(v for v in real[:i + 1] if v) if i < n else None for i in range(nmes)]
    rot = [f"MÊS {i + 1:02d}" for i in range(nmes)]
    mil = lambda v: "R$ " + br(v / 1000, 2)
    gw, gh = fl.w, 300
    graficos = [
        ("Gráfico Físico Financeiro (R$) – Mensal;", lambda doc_, p, x, y, w, h: _grafico(
            doc_, p, x, y, w, h, rot, [("PREVISTO R$/1000", prev, AZUL), ("REALIZADO R$/1000", real, LARANJA)], [], mil,
            "GRÁFICO FINANCEIRO MENSAL – MORRO DA CRUZ", (1, n - 1)), "Gráfico 01 – Físico-financeiro mensal (R$/1000, P0)."),
        ("Gráfico Físico Financeiro (%) – Mensal;", lambda doc_, p, x, y, w, h: _grafico(
            doc_, p, x, y, w, h, rot, [("% - PREVISTO", [v / contrato if v is not None else None for v in prev], AZUL),
                                       ("% - REALIZADO", [v / contrato if v is not None else None for v in real], LARANJA)], [],
            pct, "GRÁFICO PERCENTUAL MENSAL – MORRO DA CRUZ", (1, n - 1)), "Gráfico 02 – Físico-financeiro mensal (% do contrato)."),
        ("Gráfico Físico Financeiro (R$) – Acumulado;", lambda doc_, p, x, y, w, h: _grafico(
            doc_, p, x, y, w, h, rot, [("PREVISTO R$/1000", prev, AZUL), ("REALIZADO R$/1000", real, LARANJA)],
            [("PREVISTO ACUM. R$/1000", pac, "1F3864"), ("REALIZADO ACUM. R$/1000", rac, "C00000")], mil,
            "GRÁFICO FINANCEIRO MENSAL / ACUMULADO – MORRO DA CRUZ", (1, n - 1)), "Gráfico 03 – Físico-financeiro mensal e "
                                                                                 "acumulado (R$/1000, P0)."),
        ("Gráfico Físico Percentual (%) – Acumulado;", lambda doc_, p, x, y, w, h: _grafico(
            doc_, p, x, y, w, h, rot, [("% - PREVISTO", [v / contrato if v is not None else None for v in prev], AZUL),
                                       ("% - REALIZADO", [v / contrato if v is not None else None for v in real], LARANJA)],
            [("% - PREVISTO ACUM.", [v / contrato if v is not None else None for v in pac], "1F3864"),
             ("% - REALIZADO ACUM.", [v / contrato if v is not None else None for v in rac], "C00000")], pct,
            "GRÁFICO PERCENTUAL MENSAL / ACUMULADO – MORRO DA CRUZ", (1, n - 1)), "Gráfico 04 – Físico percentual mensal e "
                                                                                 "acumulado (%)."),
    ]
    for indice_grafico, (titulo, fn, leg) in enumerate(graficos):
        fl.titulo(2, titulo, nova_pagina=True)
        altura_grafico = (180 if indice_grafico == 0 else 355) if word else gh
        fl.figura(gw, altura_grafico, fn, leg)
    fl.titulo(1, "Histograma Operacional:", nova_pagina=True)
    ef = d["efetivo"]
    fl.titulo(2, "Disposição das Equipes Operacionais / Administrativas;")
    linhas = [["EQUIPE", "COLABORADORES PRESENTES NO PERÍODO"]]
    for e, q in ef["por_equipe"].items():
        linhas.append([e, str(q)])
    linhas.append(["TOTAL GERAL", str(ef["total"])])
    if ef["total"] == 0:
        linhas = [linhas[0], [{"t": "Sem presença registrada no check-in do período.", "span": 2}]]
    fl.tabela([0.6, 0.4], linhas, tam=8, alin=["E", "D"], total=ef["total"] > 0)
    fl.paragrafo([(("Tabela 10 – Disposição das equipes (presenças do check-in). Empresa da equipe identifica direto e terceirizado." if word else "Tabela 10 – Disposição das equipes (presenças do check-in). A separação em direto e terceirizado ainda "
                   "não é guardada no cadastro de funcionários."), {"italico": True, "cor": CINZA})], tam=8, alin="C")
    fl.titulo(2, "Quadro Resumo de Funções Operacionais / Administrativas;")
    linhas = [["FUNÇÃO", "COLABORADORES"]] + [[f, str(q)] for f, q in ef["funcoes"].items()]
    if len(linhas) == 1:
        linhas.append([{"t": "Sem presença registrada no check-in do período.", "span": 2}])
    fl.tabela([0.6, 0.4], linhas, tam=8, alin=["E", "D"])
    fl.paragrafo([("Tabela 11 – Quadro resumo de funções (cadastro de funcionários presentes no período).",
                   {"italico": True, "cor": CINZA})], tam=8, alin="C")
    fl.titulo(2, "Quadro Resumo de Máquinas / Equipamentos / Veículos;")
    linhas = [["MÁQUINA / EQUIPAMENTO / VEÍCULO", "QUANTIDADE", "DIAS × MÁQUINA"]] + \
             [[k, str(v[0]), str(v[1])] for k, v in ef["maquinas"].items()]
    if len(linhas) == 1:
        linhas.append([{"t": "Sem máquina registrada no check-in do período.", "span": 3}])
    fl.tabela([0.6, 0.2, 0.2], linhas, tam=8, alin=["E", "D", "D"])
    fl.paragrafo([("Tabela 12 – Quadro resumo de máquinas, equipamentos e veículos (check-in).", {"italico": True,
                                                                                               "cor": CINZA})], tam=8,
                 alin="C")
    fl.titulo(2, f"Gráfico Detalhado Mensal do Histograma - Mão de Obra – Mês {mes_nome};", nova_pagina=True)
    if word:
        RW.colaboradores(d, fl)
    else:
        if ef["colaboradores"]:
            col = ef["colaboradores"][:40]
            fl.figura(fl.w, 240 if word else 300, lambda doc_, p, x, y, w, h: _grafico(
                doc_, p, x, y, w, h, [c for c, _ in col], [("DIAS PRESENTES", [q for _, q in col], AZUL)], [],
                lambda v: br(v, 0), f"DIAS PRESENTES POR COLABORADOR (INICIAIS-MATRÍCULA) – {mes_nome.upper()}"),
                "Gráfico 05 – Dias presentes por colaborador (check-in)." + (" Os 40 com mais dias." if len(ef["colaboradores"]) > 40
                                                                              else ""))
        else:
            fl.paragrafo(_pend("Gráfico 05 – sem presença registrada no check-in do período."))
    fl.titulo(2, f"Gráfico Mensal do Histograma - Mão de Obra – {mes_nome};")
    dias = [(_d(ini) + timedelta(days=i)).isoformat() for i in range((_d(fim) - _d(ini)).days + 1)]
    if word:
        RW.efetivo(d, fl, dias)
    else:
        if ef["por_dia"]:
            fl.figura(fl.w, 260, lambda doc_, p, x, y, w, h: _grafico(
                doc_, p, x, y, w, h, [dbr(x_)[:5] for x_ in dias], [("EFETIVO DO DIA", [ef["por_dia"].get(x_) for x_ in dias], AZUL)],
                [], lambda v: br(v, 0), f"EFETIVO DO DIA – {mes_nome.upper()}"), "Gráfico 06 – Efetivo do dia (check-in).")
        else:
            fl.paragrafo(_pend("Gráfico 06 – sem presença registrada no check-in do período."))
    fl.titulo(2, "Gráfico de Produção Acumulada – Histórico Assentamento de Rede por Tipo de Tubo;", nova_pagina=True)
    des = list(pd)
    fl.figura(fl.w, 355 if word else 300, lambda doc_, p, x, y, w, h: _grafico(
        doc_, p, x, y, w, h, [f"PEAD DE {k}" for k in des],
        [("PREVISTO (m)", [pd[k]["previsto"] for k in des], AZUL), ("REALIZADO NO MÊS (m)", [pd[k]["mes"] for k in des], LARANJA),
         ("REALIZADO ACUMULADO (m)", [pd[k]["acumulado"] for k in des], VERDE)], [], lambda v: br(v, 0),
        f"PRODUÇÃO DE REDES ACUMULADA – METROS (previsto {br(t_prev)} m; acumulado {br(s_('acumulado'))} m)"),
        "Gráfico 07 – Produção de redes acumulada por tipo de tubo.")
    fl.titulo(2, f"Gráfico do Indicador de Desempenho Ambiental (IDA) – Morro da Cruz – {mes_nome};", nova_pagina=True)
    meses_ida = [f"{MESES[(_d(d['modelo']['os'] or ini).month - 1 + i) % 12][:3]}/"
                 f"{str(_d(d['modelo']['os'] or ini).year + (_d(d['modelo']['os'] or ini).month - 1 + i) // 12)[2:]}" for i in range(nmes)]
    fl.figura(fl.w, 355 if word else 260, lambda doc_, p, x, y, w, h: _ida(doc_, p, x, y, w, h, meses_ida, n),
              "Gráfico 08 – IDA CAESB × meta (70%). A vistoria ambiental da CAESB ainda não é registrada no sistema.")
    fl.paragrafo("O Relatório de Supervisão Ambiental de Obras (SAOB) do período não está registrado no sistema. A CONTRATADA "
                 "mantém a atenção com o meio em que trabalha, para garantir a segurança dos trabalhadores e o atendimento às "
                 "normas regulamentadoras.")

    # 17 a 19 -------------------------------------------------------------------------------------------------------
    fl.titulo(1, "Observações Gerais, Reuniões e Fatos Relevantes", paisagem=False)
    fl.paragrafo(f"Fechamento da {nª} medição, referente ao período de {dbr(ini)} até {dbr(fim)}, no valor de {rs(valor)} "
                 f"(P0, com BDI e coeficiente K){' – medição ' + med['status'].lower() if med['status'] else ''};",
                 marcador=True, depois=2)
    fl.paragrafo("Reajuste de R$ 0,00 nesta medição: não pedido (D-140);", marcador=True, depois=2)
    for i in aditivo:
        fl.paragrafo(f"Item {i['item']} ({i['descricao'][:80]}): acumulado {br(i['acumulado'])} {i['unidade']}, acima dos "
                     f"{br(float(i['contrato']))} {i['unidade']} do contrato. A diferença depende de aditivo ou apostilamento;",
                     marcador=True, depois=2)
    if d["chuva"]:
        fl.paragrafo(f"Dias com paralisação por chuva no período: {d['chuva']};", marcador=True, depois=2)
    if d["ocorrencias_abertas"]:
        fl.paragrafo(f"Interferências, impedimentos e não conformidades em aberto: {d['ocorrencias_abertas']};", marcador=True,
                     depois=2)
    fl.paragrafo(f"A CONTRATADA informa que ainda não existe data definida para ser realizada a vistoria da equipe ambiental da "
                 f"CAESB para emissão do relatório de supervisão ambiental, referente ao período: {dbr(ini)} até {dbr(fim)}.",
                 marcador=True, depois=2)
    if d["teste"]:
        fl.paragrafo("Medição de TESTE: este relatório segue o modelo, mas não vale como medição oficial (D-56);", marcador=True,
                     depois=2)
    fl.paragrafo(_pend("diálogos diários de segurança (DDS), reuniões com a fiscalização, visitas e fatos relevantes do período."))
    fl.titulo(1, "Relatório Fotográfico", nova_pagina=True)
    fl.titulo(2, f"Fotos referente ao – Mês {mes_nome};")
    _fotos_paginas(doc, fl, d)
    fl.titulo(1, "Anexos", nova_pagina=True)
    fl.titulo(2, "Projeto do Canteiro de Obras - Atualizado;")
    fl.paragrafo(_pend("layout atualizado do canteiro de obras (documento da obra, fora do sistema)."))
    fl.titulo(2, "Relatório de Supervisão Ambiental de Obras;")
    fl.paragrafo([("NOTA: ", {"negrito": True}), ("Ainda não houve inspeção pela fiscalização da CAESB registrada no sistema.", {})])
    fl.titulo(2, "Mapa Iluminado – Morro da Cruz – Redes de Distribuição;", nova_pagina=True)
    fl.figura(fl.w, 480, lambda doc_, p, x, y, w, h: _iluminado(doc_, p, x, y, w, h, d),
              f"Anexo – Mapa iluminado da {nª} medição: rede executada no mês {br(s_('mes'))} m; acumulada {br(s_('acumulado'))} m.")
    fl.titulo(3, f"Caminhamento – Redes Referente à {nª} Medição – Período: {dbr(ini)} até {dbr(fim)};")
    if word:
        RW.caminhamento(d, fl)
    else:
        mes_tr = [(t, m) for t, m in d["assentado"]["mes"].items() if t in d["trechos"]]
        if mes_tr:
            linhas = [["TRECHO", "FRENTE", "DE (mm)", "MÉTODO", "ASSENTADO NO MÊS (m)"]]
            for t, m in sorted(mes_tr, key=lambda x: d["trechos"][x[0]]["ponto"]):
                tr = d["trechos"][t]
                linhas.append([tr["ponto"], _frente(tr["frente_id"]), str(int(tr["de_mm"] or 0)), tr["metodologia"] or "—", br(m)])
            fl.tabela([0.36, 0.2, 0.1, 0.12, 0.22], linhas, tam=7.5, alin=["E", "E", "C", "C", "D"])
        else:
            fl.paragrafo("Não houve rede executada no período; o caminhamento da medição não tem trechos.")


def fl_rm(d):
    return f"RM – {d['medicao']['numero']:02d}/{_d(d['fim']).year}"


def _frente(fr):
    if not fr or fr == "—":
        return "SEM FRENTE"
    return fr.replace("Zona", "ZONA ") if str(fr).startswith("Zona") else {"ADUTORA": "SUBADUTORA", "CH": "CAIXAS HIDRÁULICAS"}.get(fr, fr)


def _etapa(e):
    return {"ASSENTADO": "Assentamento de rede", "REATERRADO": "Reaterro de vala", "CADASTRO_CAMPO": "Cadastro de campo"}.get(e, e)


def _proximo(d):
    """A programação gravada para o mês seguinte (por equipe e serviço), como no modelo."""
    return [f"{_frente(eq)} – {serv.replace('_', ' ').lower()}: {q} programação(ões) de {dbr(a)} a {dbr(b)};"
            for (eq, serv), (q, a, b) in sorted(d["proximo"].items())]


def _org1(doc, p, x, y, w, h, cfg):
    _caixa(doc, p, x + w * 0.1, y, w * 0.8, 24, [f"CONTRATO – {cfg['obra']['nome'].upper()}"], fundo=VINHO, tam=8, negrito=True,
           cor_txt="FFFFFF")
    ca, cb = x + w * 0.04, x + w * 0.54
    bw = w * 0.42
    doc.linha(p, x + w / 2, y + 24, x + w / 2, y + 34, "555555", 0.8)
    doc.linha(p, ca + bw / 2, y + 34, cb + bw / 2, y + 34, "555555", 0.8)
    for xx, t, f in ((ca, "CONTRATADA – ANKARA ENGENHARIA LTDA", "F4B183"), (cb, "FISCALIZAÇÃO – CAESB", "BDD7EE")):
        doc.linha(p, xx + bw / 2, y + 34, xx + bw / 2, y + 42, "555555", 0.8)
        _caixa(doc, p, xx, y + 42, bw, 22, [t], fundo=f, tam=8, negrito=True)
    for i, papel in enumerate(cfg["responsaveis"]):
        yy = y + 76 + i * 34
        doc.linha(p, ca + 8, y + 64, ca + 8, yy + 13, "555555", 0.8)
        doc.linha(p, ca + 8, yy + 13, ca + 18, yy + 13, "555555", 0.8)
        _caixa(doc, p, ca + 18, yy, bw - 18, 26, [papel.upper(), "PENDENTE (cadastro da obra)"], fundo="FFF2A8", tam=7)
    for i, papel in enumerate(("GESTOR DO CONTRATO", "FISCAL DO CONTRATO", "FISCAL DO CONTRATO", "DE ACORDO – SUPERINTENDENTE")):
        yy = y + 76 + i * 40
        doc.linha(p, cb + bw / 2, yy - (12 if i == 0 else 14), cb + bw / 2, yy, "555555", 0.8)
        _caixa(doc, p, cb + bw * 0.1, yy, bw * 0.8, 26, [papel, "conforme a Ordem de Serviço (nome PENDENTE)"], fundo="FFF2A8",
               borda="1F4E9E", tam=7)


def _org2(doc, p, x, y, w, h, d):
    eqs = [(e["nome"], "ativa no período" if e["dias"] else "sem check-in no período") for e in d["equipes"]]
    eqs += [(f"{a} (terceirizada)", b.lower()) for a, b in d["cfg"]["terceirizadas"]]
    _caixa(doc, p, x + w * 0.2, y, w * 0.6, 22, ["FRENTES DE SERVIÇO E TERCEIRIZADAS – MORRO DA CRUZ"], fundo=VINHO, tam=8,
           negrito=True, cor_txt="FFFFFF")
    cols = 5
    bw, bh = (w - (cols - 1) * 6) / cols, 34
    doc.linha(p, x + w / 2, y + 22, x + w / 2, y + 30, "555555", 0.8)
    linhas_ = (len(eqs) + cols - 1) // cols
    for r in range(linhas_):
        yb = y + 30 + r * (bh + 14)
        doc.linha(p, x + bw / 2, yb, x + (cols - 1) * (bw + 6) + bw / 2, yb, "555555", 0.8)
        if r:
            doc.linha(p, x + 2, y + 30, x + 2, yb, "555555", 0.8)
            doc.linha(p, x + 2, yb, x + bw / 2, yb, "555555", 0.8)
        for c in range(cols):
            i = r * cols + c
            if i >= len(eqs):
                break
            xb = x + c * (bw + 6)
            doc.linha(p, xb + bw / 2, yb, xb + bw / 2, yb + 6, "555555", 0.8)
            ativa = "ativa" in eqs[i][1]
            _caixa(doc, p, xb, yb + 6, bw, bh, [eqs[i][0], eqs[i][1]], fundo="FFFFFF" if ativa else "F2F2F2", tam=6.8)


def _croqui(doc, p, x, y, w, h, d, tr_sem):
    base, ant, sem = [], [], []
    antes = d["assentado"]["antes"]
    for tid, t in d["trechos"].items():
        if not t["seg"]:
            continue
        (sem if tid in tr_sem else ant if antes.get(tid) else base).append(t["seg"])
    segs = [d["trechos"][t]["seg"] for t in tr_sem if d["trechos"].get(t, {}).get("seg")]
    janela = None
    if segs:                                             # aproxima nos trechos da semana (pelo menos 500 m de lado)
        es = [v for s_ in segs for v in (s_[0], s_[2])]
        ns = [v for s_ in segs for v in (s_[1], s_[3])]
        ce, cn_ = (min(es) + max(es)) / 2, (min(ns) + max(ns)) / 2
        lado = max(max(es) - min(es), max(ns) - min(ns), 500) * 1.35
        k = w / h
        janela = (ce - lado * k / 2, cn_ - lado / 2, ce + lado * k / 2, cn_ + lado / 2)
    _mapa(doc, p, x, y, w, h, [("9DC3E6", 0.6, base), ("F2C200", 1.6, ant), ("D00000", 2.6, sem)], _rotulos_zona(d["trechos"]),
          janela=janela)


def _iluminado(doc, p, x, y, w, h, d):
    mes, antes = d["assentado"]["mes"], d["assentado"]["antes"]
    base, ant, m = [], [], []
    for tid, t in d["trechos"].items():
        if t["seg"]:
            (m if mes.get(tid) else ant if antes.get(tid) else base).append(t["seg"])
    _mapa(doc, p, x, y, w, h - 22, [("1F4E9E", 0.6, base), ("F2C200", 1.4, ant), ("D00000", 2.0, m)], _rotulos_zona(d["trechos"]))
    _legenda(doc, p, x, y + h - 8, w, [("D00000", "EXECUTADO NO MÊS"), ("F2C200", "EXECUTADO ANTERIOR"),
                                       ("1F4E9E", "NÃO EXECUTADO")], 7.5)


def _ida(doc, p, x, y, w, h, meses, n):
    _grafico(doc, p, x, y, w, h, meses, [("IDA CAESB", [None] * len(meses), AZUL)], [("META (70%)", [0.7] * len(meses), "C00000")],
             lambda v: pct(v, 0), "INDICADOR DE DESEMPENHO AMBIENTAL (IDA) – MORRO DA CRUZ", eixo_unico=True, vmax=1.2)
    t = f"NÃO HOUVE VISTORIA DA CAESB – Nº {n:02d}"
    doc.ret(p, x + 70, y + 30, P.largura(t, 8, True) + 10, 14, fundo="FFF2CC", borda="999999", lw=0.5)
    doc.texto(p, x + 75, y + 40, t, 8, True)


def _fotos_paginas(doc, fl, d):
    if hasattr(fl,"fotos"):
        fl.fotos(d["fotos"],d["fotos_fora"])
        return
    fotos = d["fotos"]
    if not fotos:
        fl.paragrafo([("Sem foto registrada no período.", {"italico": True, "cor": CINZA})])
        return
    for k in range(0, len(fotos), FOTOS_POR_PAGINA):
        if k:
            fl.nova_pagina()
        bloco = fotos[k:k + FOTOS_POR_PAGINA]
        disp = fl.y1 - fl.y
        cw, ch = fl.w / 2, disp / 3
        for i, f in enumerate(bloco):
            cx = fl.x0 + (i % 2) * cw
            cy = fl.y + (i // 2) * ch
            doc.ret(fl.p, cx, cy, cw, ch, borda="C8D0D6", lw=0.4)
            leg = f"FOTO {k + i + 1:02d} – {f['legenda']};"
            ls = P.linhas_texto(leg, cw - 12, 7.5)
            hl = len(ls) * 9 + 6
            reg = doc.registrar_imagem(f["jpeg"], foto=True, max_px=900) if f["jpeg"] else None
            if reg:
                iid, pw, ph = reg
                kk = min((cw - 14) / pw, (ch - hl - 12) / ph)
                doc.imagem(fl.p, iid, cx + (cw - pw * kk) / 2, cy + 6, pw * kk, ph * kk)
            else:
                doc.texto(fl.p, cx + 10, cy + ch / 2, "(foto indisponível no servidor)", 8, False, True, CINZA)
            for j, t in enumerate(ls):
                doc.texto(fl.p, cx + (cw - P.largura(t, 7.5)) / 2, cy + ch - hl + 8 + j * 9, t, 7.5)
        fl.y = fl.y1
    if d["fotos_fora"]:
        fl.nova_pagina()
        fl.paragrafo([(f"Mais {d['fotos_fora']} foto(s) do período ficaram de fora (limite de {MAX_FOTOS} fotos no relatório).",
                       {"italico": True, "cor": CINZA})])
