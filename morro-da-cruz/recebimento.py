"""Entrega por linha: identificar pode vir depois de receber, mas sempre antes de virar estoque."""
import math

import compras as C
import regras as R
import servicos as S
from servicos import RegraViolada, _one, _rows, transacao, _agora


def numero(v):
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        raise RegraViolada("Quantidade inválida.") from None
    if not math.isfinite(n) or n < 0:
        raise RegraViolada("Quantidade deve ser um número positivo ou zero.")
    return n


def entregue(conn, linha):
    """Unidade da NF. Entregas antigas e novas sem contar duas vezes a materialização."""
    nova = conn.execute("SELECT COALESCE(SUM(aceito+recusado),0) FROM nf_entregas_linhas WHERE linha_id=?", (linha['id'],)).fetchone()[0]
    antiga = conn.execute("""SELECT COALESCE(SUM(ri.quantidade),0) FROM recebimento_itens ri
        JOIN nf_itens ni ON ni.id=ri.nf_item_id WHERE ni.linha_id=?
        AND ri.id NOT IN (SELECT recebimento_item_id FROM nf_entregas_linhas WHERE recebimento_item_id IS NOT NULL)""", (linha['id'],)).fetchone()[0]
    return round(nova + antiga / (linha['fator'] or 1), 6)


def linhas(conn, nf_id):
    out = _rows(conn.execute("SELECT * FROM nf_linhas WHERE nf_id=? ORDER BY n_item", (nf_id,)))
    for li in out:
        li['entregue'] = entregue(conn, li)
        li['aguardando_identificacao'] = conn.execute("""SELECT COALESCE(SUM(aceito),0) FROM nf_entregas_linhas
            WHERE linha_id=? AND resolvida_em IS NULL""", (li['id'],)).fetchone()[0]
    return out


def corrigir(conn, nf_id, linha_id, por):
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", nf_id)
    li = _one(conn, "SELECT * FROM nf_linhas WHERE id=? AND nf_id=?", linha_id, nf_id)
    if not nf or nf['status'] == 'CANCELADA' or not li:
        raise RegraViolada("Linha ou nota não encontrada.")
    if _one(conn, "SELECT id FROM nf_itens WHERE linha_id=?", linha_id):
        raise RegraViolada("A linha já foi conferida para o estoque. Corrija por devolução/estorno, preservando o histórico.")
    conn.execute("""INSERT INTO nf_confirmacoes(linha_id,solicitada_por,solicitada_em) VALUES (?,?,?)
        ON CONFLICT(linha_id) DO UPDATE SET pendente=1,solicitada_por=excluded.solicitada_por,
        solicitada_em=excluded.solicitada_em,confirmada_por=NULL,confirmada_em=NULL""", (linha_id, por, _agora()))
    conn.execute("UPDATE nf_linhas SET fora_do_estoque=0 WHERE id=?", (linha_id,))   # volta a ser material a confirmar
    return {'ok': True}


def _item(conn, li):
    ni = _one(conn, "SELECT * FROM nf_itens WHERE linha_id=?", li['id'])
    if ni:
        return ni
    m = _one(conn, "SELECT * FROM materiais WHERE id=?", li['material_id'])
    if not m or not li['fator'] or li['fator'] <= 0:
        raise RegraViolada("Confirme o material e a conversão da linha.")
    conn.execute("UPDATE nf_linhas SET romaneio_caesb=? WHERE id=?", (int(m['propriedade'] == 'CAESB'), li['id']))
    ident = conn.execute("""INSERT INTO nf_itens(nf_id,material_id,quantidade,valor_unitario,linha_id)
        VALUES (?,?,?,?,?)""", (li['nf_id'], li['material_id'], round(li['quantidade'] * li['fator'], 6),
                               li['valor_unitario'] / li['fator'], li['id'])).lastrowid
    return _one(conn, "SELECT * FROM nf_itens WHERE id=?", ident)


def materializar(conn, entrega_id):
    """Uma entrega física gera estoque só uma vez, com o recebedor original e a confirmação identificada."""
    e = _one(conn, "SELECT * FROM nf_entregas_linhas WHERE id=?", entrega_id)
    if e['resolvida_em']:
        return
    li = _one(conn, "SELECT * FROM nf_linhas WHERE id=?", e['linha_id'])
    if li['fora_do_estoque'] or (not li['material_id'] and not e['aceito']):
        conn.execute("UPDATE nf_entregas_linhas SET resolvida_em=? WHERE id=?", (_agora(), entrega_id))
        return
    if not li['material_id'] or _one(conn, "SELECT 1 FROM nf_confirmacoes WHERE linha_id=? AND pendente=1", li['id']):
        return
    ni = _item(conn, li)
    r = _one(conn, "SELECT * FROM recebimentos WHERE id=?", e['recebimento_id'])
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", li['nf_id'])
    a, rec = round(e['aceito'] * li['fator'], 6), round(e['recusado'] * li['fator'], 6)
    caesb = _one(conn, "SELECT propriedade FROM materiais WHERE id=?", ni['material_id'])['propriedade'] == 'CAESB'
    mid = conn.execute("""INSERT INTO movimentos(data,material_id,tipo,quantidade,documento,status,nf_id,responsavel,ref_tipo,ref_id)
        VALUES (?,?,?,?,?,?,?,?, 'RECEBIMENTO',?)""", (r['data'], ni['material_id'], 'ROMANEIO_CAESB' if caesb else 'ENTRADA_NF',
        a if caesb else a + rec, (f"NF {nf['numero']} (remessa Caesb)" + (f"; {rec:g} recusado, fora do romaneio" if rec else '')) if caesb else f"NF {nf['numero']}", 'ACEITO' if caesb else 'QUARENTENA', nf['id'], r['recebido_por'], r['id'])).lastrowid
    ri = conn.execute("INSERT INTO recebimento_itens(recebimento_id,nf_item_id,quantidade,movimento_id) VALUES (?,?,?,?)",
                      (r['id'], ni['id'], round(a + rec, 6), mid)).lastrowid
    conn.execute("UPDATE nf_entregas_linhas SET recebimento_item_id=?,resolvida_em=? WHERE id=?", (ri, _agora(), entrega_id))
    if caesb:
        conn.execute("""INSERT INTO inspecoes(recebimento_item_id,aceito,recusado,laudo,motivo_recusa,inspecionado_por,
            inspecionado_em,movimento_aceito_id) VALUES (?,?,?,?,?,?,?,?)""",
            (ri, a, rec, e['motivo'] or 'Conferido na entrega', e['motivo'], r['recebido_por'], _agora(), mid))
    else:
        C.inspecionar(conn, ri, a, rec, e['motivo'], r['recebido_por'], r['data'], e['motivo'])


def encerrar(conn, nf_id):
    nf = _one(conn, "SELECT status FROM notas_fiscais WHERE id=?", nf_id)
    if not nf or nf['status'] == 'CANCELADA':
        return
    ls = linhas(conn, nf_id)
    falta = any(not l['fora_do_estoque'] and (l['quantidade'] - l['entregue'] > C.TOL or l['aguardando_identificacao'] > C.TOL) for l in ls)
    quarentena = _one(conn, """SELECT 1 FROM recebimento_itens ri JOIN nf_itens ni ON ni.id=ri.nf_item_id
        WHERE ni.nf_id=? AND ri.id NOT IN (SELECT recebimento_item_id FROM inspecoes) AND """ + C._SEM_ROMANEIO, nf_id)
    if falta or quarentena:
        if nf['status'] != 'A_CONFERIR':
            conn.execute("UPDATE notas_fiscais SET status='CONFERIDA' WHERE id=?", (nf_id,))
    else:
        conn.execute("UPDATE notas_fiscais SET status='ENCERRADA' WHERE id=?", (nf_id,))


def confirmar(conn, nf_id, conf, por):
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", nf_id)
    if not nf or nf['status'] == 'CANCELADA':
        raise RegraViolada("Nota não encontrada ou cancelada.")
    if nf['origem'] == 'DIGITADA' and str(nf['registrada_por']).lower() == str(por).lower():
        raise RegraViolada("Quem digitou os dados da nota não pode conferi-los.")
    if not conf:
        raise RegraViolada("Escolha a linha a confirmar.")
    with transacao(conn):
        for c in conf:
            li = _one(conn, "SELECT * FROM nf_linhas WHERE id=? AND nf_id=?", int(c.get('linha_id') or 0), nf_id)
            if not li:
                raise RegraViolada("Linha fora desta nota.")
            if _one(conn, "SELECT 1 FROM nf_itens WHERE linha_id=?", li['id']):
                raise RegraViolada("Linha já conferida para o estoque: preserve o histórico por devolução/estorno.")
            mid, fat = None, None
            if not c.get('fora_do_estoque'):
                m = _one(conn, "SELECT * FROM materiais WHERE id=?", c.get('material_id'))
                if not m:
                    raise RegraViolada("Escolha o material.")
                mid = m['id']
                fat = 1 if R.normalizar_unidade(m['unidade']) == R.normalizar_unidade(li['unidade']) else numero(c.get('fator'))
                if not fat:
                    raise RegraViolada(f"Linha {li['n_item']}: diga quantos {m['unidade']} vem em cada {li['unidade']}.")
            conn.execute("UPDATE nf_linhas SET material_id=?,fator=?,fora_do_estoque=? WHERE id=?", (mid, fat, int(not mid), li['id']))
            conn.execute("""INSERT INTO nf_confirmacoes(linha_id,pendente,solicitada_por,solicitada_em,confirmada_por,confirmada_em)
                VALUES (?,0,?,?,?,?) ON CONFLICT(linha_id) DO UPDATE SET pendente=0,
                confirmada_por=excluded.confirmada_por,confirmada_em=excluded.confirmada_em""", (li['id'], por, _agora(), por, _agora()))
            for (eid,) in conn.execute("SELECT id FROM nf_entregas_linhas WHERE linha_id=? AND resolvida_em IS NULL", (li['id'],)).fetchall():
                materializar(conn, eid)
        if nf['status'] != 'A_CONFERIR':
            encerrar(conn, nf_id)
    faltam = sum(not x['material_id'] and not x['fora_do_estoque'] for x in C.sugerir_materiais(conn, nf_id))
    return {'confirmadas': len(conf), 'faltam': faltam, 'por': por}


def receber(conn, nf_id, por, data, problema=None, recusa=None):
    S.exigir_data_ocorrida(data, 'Recebimento')
    nf = _one(conn, "SELECT * FROM notas_fiscais WHERE id=?", nf_id)
    if not nf or nf['status'] not in ('A_CONFERIR', 'CONFERIDA'):
        raise RegraViolada("Só nota a conferir ou conferida pode receber entrega.")
    if not data or (nf['data_emissao'] and data < nf['data_emissao']):
        raise RegraViolada("Data da entrega ausente ou anterior à emissão da nota.")
    if nf['origem'] == 'DIGITADA' and str(nf['registrada_por']).lower() == str(por).lower():
        raise RegraViolada("Quem digitou os dados da nota não pode conferi-los.")
    obs = str(recusa if recusa is not None else (problema or {}).get('observacao') or (problema or {}).get('motivo') or '').strip()
    if (recusa is not None or problema is not None) and not obs:
        raise RegraViolada("Diga por que a entrega foi recusada." if recusa is not None else "Diga o porquê da avaria ou falta.")
    sug = {x['linha_id']: x for x in C.sugerir_materiais(conn, nf_id)}
    pedidos = (problema or {}).get('linhas') or {}
    plano = []
    for li in linhas(conn, nf_id):
        s = sug[li['id']]
        resta = round(li['quantidade'] - li['entregue'], 6)
        if resta <= C.TOL or s['fora_do_estoque']:
            continue
        p = pedidos.get(str(li['id']), pedidos.get(li['id'], {}))
        if recusa is not None:
            a, r = 0, resta
        elif 'aceito' in p or 'recusado' in p:
            a, r = numero(p.get('aceito')), numero(p.get('recusado'))
        elif problema is not None:
            chegou = numero(p.get('chegou', 0 if pedidos else resta))
            r = numero(p.get('avariado'))
            a = chegou - r
        else:
            a, r = resta, 0
        if a < 0 or a + r > resta + C.TOL:
            raise RegraViolada(f"Linha {li['n_item']}: no máximo {resta:g} no total; o avariado não passa do que chegou.")
        if a + r > C.TOL:
            plano.append((li, s, a, r))
    with transacao(conn):
        for s in sug.values():
            if s['fora_do_estoque']:
                conn.execute("UPDATE nf_linhas SET fora_do_estoque=1 WHERE id=?", (s['linha_id'],))
        if not plano:
            if all(s['fora_do_estoque'] for s in sug.values()):
                conn.execute("UPDATE notas_fiscais SET status='ENCERRADA',conferida_por=?,conferida_em=? WHERE id=?", (por, _agora(), nf_id))
                return {'encerrada': True, 'itens': 0, 'recebimento_id': None, 'aguarda_aprovacao': False, 'cancelada': False}
            raise RegraViolada("Nada a receber: informe o que foi aceito ou recusado.")
        conn.execute("UPDATE notas_fiscais SET status='CONFERIDA',conferida_por=COALESCE(conferida_por,?),conferida_em=COALESCE(conferida_em,?) WHERE id=?", (por, _agora(), nf_id))
        rid = conn.execute("INSERT INTO recebimentos(nf_id,data,documento,recebido_por,registrado_em) VALUES (?,?,?,?,?)", (nf_id, data, ('recusa: ' if recusa is not None else 'obs.: ') + obs if obs else None, por, _agora())).lastrowid
        for li, s, a, r in plano:
            if s['material_id']:
                conn.execute("UPDATE nf_linhas SET material_id=?,fator=? WHERE id=?", (s['material_id'], s['fator'], li['id']))
            elif a:
                corrigir(conn, nf_id, li['id'], por)
            eid = conn.execute("INSERT INTO nf_entregas_linhas(recebimento_id,linha_id,aceito,recusado,motivo) VALUES (?,?,?,?,?)", (rid, li['id'], a, r, obs or None)).lastrowid
            materializar(conn, eid)
        encerrar(conn, nf_id)
    return {'recebimento_id': rid, 'itens': len(plano), 'recusado': sum(x[3] for x in plano),
            'encerrada': _one(conn, "SELECT status FROM notas_fiscais WHERE id=?", nf_id)['status'] == 'ENCERRADA',
            'aguarda_aprovacao': False, 'aguardando_identificacao': sum(x['aguardando_identificacao'] for x in linhas(conn, nf_id))}
