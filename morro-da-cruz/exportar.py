"""Exportação da medição para .xlsx: BM Vertical, BM Juntada, REAJUSTE, gavetas e memórias de cálculo."""
import io
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import servicos as S

LARANJA = "E85D22"
GRAFITE = "17202B"
CAB = PatternFill("solid", fgColor=GRAFITE)
SUB = PatternFill("solid", fgColor="FBE3D6")
FINO = Side(style="thin", color="E2E5EA")
BORDA = Border(left=FINO, right=FINO, top=FINO, bottom=FINO)
MOEDA = 'R$ #,##0.00'
QTD = '#,##0.000'


def _cabecalho(ws, titulo, sub, colunas, larguras):
    ws.append([titulo])
    ws["A1"].font = Font(bold=True, size=13, color=LARANJA)
    ws.append([sub])
    ws["A2"].font = Font(italic=True, color="555555")
    ws.append([])
    ws.append(colunas)
    for i, w in enumerate(larguras, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
        c = ws.cell(row=4, column=i)
        c.font, c.fill, c.alignment, c.border = Font(bold=True, color="FFFFFF"), CAB, Alignment(wrap_text=True, vertical="center"), BORDA
    ws.freeze_panes = "A5"


def _fmt(ws, linha, formatos):
    for col, f in formatos.items():
        ws.cell(row=linha, column=col).number_format = f
    for c in ws[linha]:
        c.border = BORDA


def planilha_medicao(conn, medicao_id):
    r = S.resumo_medicao(conn, medicao_id)
    med = r["medicao"]
    contrato = S.contrato(conn)
    sub = f"{contrato} · {med['numero']}ª medição · {med['periodo_ini']} a {med['periodo_fim']} · status {med['status']}"
    wb = Workbook()

    # ---- resumo das gavetas
    ws = wb.active
    ws.title = "RESUMO"
    _cabecalho(ws, "Medição — resumo das 4 gavetas", sub, ["Gaveta", "Descrição", "Lançamentos", "Valor P0 (c/ BDI − K)"], [10, 52, 14, 22])
    for g, d in r["gavetas"].items():
        ws.append([g, d["nome"], len(d["lancamentos"]), d["valor"]])
        _fmt(ws, ws.max_row, {4: MOEDA})
    for rot, val in (("Subtotal P0", r["valor_pi"]), ("(−) Excedente sobre teto de subgrupo", -r["excedente_teto"]),
                     ("Valor P0 limitado ao teto", r["valor_pi_limitado"]),
                     ("Índice de reajuste", r["indice_reajuste"] if r["indice_reajuste"] is not None else "PENDENTE"),
                     ("Reajuste", r["valor_reajuste"] if r["valor_reajuste"] is not None else "PENDENTE"),
                     ("TOTAL DA MEDIÇÃO", r["valor_total"] if r["valor_total"] is not None else "PENDENTE")):
        ws.append(["", rot, "", val])
        ws.cell(row=ws.max_row, column=2).font = Font(bold=True)
        _fmt(ws, ws.max_row, {4: "0.00%" if rot.startswith("Índice") else MOEDA})
    if r["aviso_reajuste"]:
        ws.append(["", r["aviso_reajuste"]])
    if r["sem_vinculo_bm"]:
        ws.append(["", f"{r['sem_vinculo_bm']} lançamento(s) SEM ITEM BM VINCULADO — valor zero até a confirmação (ver MC)."])
        ws.cell(row=ws.max_row, column=2).font = Font(bold=True, color="C92A2A")

    # ---- quantidades medidas por item (esta e anteriores)
    atual, anterior = defaultdict(lambda: [0.0, 0.0]), defaultdict(lambda: [0.0, 0.0])
    for l in conn.execute(
            """SELECT l.bm_item_id, l.quantidade, l.valor, m.numero FROM medicao_lancamentos l JOIN medicoes m ON m.id=l.medicao_id
               WHERE l.bm_item_id IS NOT NULL AND m.numero <= ?""", (med["numero"],)):
        alvo = atual if l["numero"] == med["numero"] else anterior
        alvo[l["bm_item_id"]][0] += l["quantidade"]
        alvo[l["bm_item_id"]][1] += l["valor"]

    # ---- BM Vertical
    ws = wb.create_sheet("BM VERTICAL")
    _cabecalho(ws, "BM — Planilha de Medição — Vertical", sub,
               ["Subgrupo", "Item", "Descrição", "Classif.", "Unid.", "Quant. contrato", "Preço unit. (s/ BDI)",
                "Quant. anterior", "Quant. nesta medição", "Quant. acumulada", "Saldo", "Valor nesta medição (P0)"],
               [10, 13, 60, 11, 8, 15, 16, 15, 15, 15, 15, 20])
    teto = {t["subgrupo"]: t for t in r["tetos"]}
    sg_atual = None
    for b in conn.execute("SELECT * FROM bm_itens WHERE planilha='VERTICAL' ORDER BY linha_origem"):
        if b["subgrupo"] != sg_atual:
            sg_atual = b["subgrupo"]
            t = teto.get(sg_atual)
            info = f" — teto {t['teto']:,.2f} · excedente {t['excedente']:,.2f}" if t else ""
            ws.append([sg_atual, "", (b["subgrupo_nome"] or "") + info])
            for c in ws[ws.max_row]:
                c.fill, c.font = SUB, Font(bold=True)
        qa, qm = anterior[b["id"]][0], atual[b["id"]][0]
        ws.append([b["subgrupo"], b["item"], b["descricao"], b["classificacao"], b["unidade"], b["quantidade"], b["preco_unitario"],
                   qa, qm, qa + qm, (b["quantidade"] or 0) - qa - qm, atual[b["id"]][1]])
        _fmt(ws, ws.max_row, {6: QTD, 7: MOEDA, 8: QTD, 9: QTD, 10: QTD, 11: QTD, 12: MOEDA})

    # ---- BM Juntada (soma dos itens verticais por item do BM)
    ws = wb.create_sheet("BM JUNTADA")
    _cabecalho(ws, "BM — Planilha de Medição — Juntada", sub,
               ["Item BM", "Descrição", "Unid.", "Quant. contrato", "Quant. nesta medição", "Quant. acumulada", "Valor nesta medição (P0)"],
               [12, 60, 8, 15, 15, 15, 20])
    por_item = defaultdict(lambda: [0.0, 0.0, 0.0])
    for b in conn.execute("SELECT id, item_bm FROM bm_itens WHERE planilha='VERTICAL'"):
        por_item[b["item_bm"]][0] += atual[b["id"]][0]
        por_item[b["item_bm"]][1] += atual[b["id"]][0] + anterior[b["id"]][0]
        por_item[b["item_bm"]][2] += atual[b["id"]][1]
    for b in conn.execute("SELECT * FROM bm_itens WHERE planilha='JUNTADA' ORDER BY linha_origem"):
        qm, qac, vm = por_item.get(b["item"], (0, 0, 0))
        ws.append([b["item"], b["descricao"], b["unidade"], b["quantidade"], qm, qac, vm])
        _fmt(ws, ws.max_row, {4: QTD, 5: QTD, 6: QTD, 7: MOEDA})

    # ---- Reajuste
    ws = wb.create_sheet("REAJUSTE")
    _cabecalho(ws, "Reajuste — CT 10239/2026", sub, ["Parâmetro", "Valor"], [55, 30])
    for k in ("reajuste_data_base", "reajuste_aniversario", "reajuste_indice", "reajuste_inicio_os"):
        ws.append([k.replace("reajuste_", "").replace("_", " ").capitalize(), S.parametro(conn, k)])
    for i in S.indices_reajuste(conn):
        ws.append([f"Vigência {i['vigencia_ini']} a {i['vigencia_fim']}", f"{i['indice']:.2%} — {i['descricao']}"])
    ws.append(["Índice aplicado nesta medição", r["indice_reajuste"] if r["indice_reajuste"] is not None else r["aviso_reajuste"]])
    ws.append(["Valor P0 limitado", r["valor_pi_limitado"]])
    ws.append(["Reajuste", r["valor_reajuste"]])
    ws.append(["Total", r["valor_total"]])

    # ---- Memórias de cálculo
    for nome, filtro in (("MC REDE", lambda l: l["alvo_tipo"] == "TRECHO"),
                         ("MC CANTEIRO", lambda l: l["alvo_tipo"] != "TRECHO")):
        ws = wb.create_sheet(nome)
        _cabecalho(ws, f"Memória de cálculo — {nome[3:].lower()}", sub,
                   ["Gaveta", "Trecho / conjunto / NF", "Serviço", "Unid.", "Quantidade", "Item BM", "Descrição BM", "Valor P0", "Observação"],
                   [8, 34, 34, 8, 14, 13, 50, 16, 40])
        for g, d in r["gavetas"].items():
            for l in d["lancamentos"]:
                if not filtro(l):
                    continue
                ref = l["alvo_id"] or (f"NF {l['nf_id']}" if l["nf_id"] else "")
                ws.append([g, ref, l["servico"], l["unidade"], l["quantidade"], l["item"] or "—", l["bm_descricao"] or "",
                           l["valor"], l["observacao"] or ""])
                _fmt(ws, ws.max_row, {5: QTD, 8: MOEDA})
                if l["bm_item_id"] is None:
                    ws.cell(row=ws.max_row, column=6).font = Font(bold=True, color="C92A2A")

    buf = io.BytesIO()
    wb.save(buf)
    return f"MEDICAO_{med['numero']:02d}_MORRO_DA_CRUZ.xlsx", buf.getvalue()
