"""Necessidade de material por frente. Solicitar ou aprovar nunca bloqueia nota, entrega ou estoque."""
import base64
import json
import os
import re

import compras as C
import servicos as S
from recebimento import numero
from servicos import RegraViolada, _one, _rows, transacao

UNIDADES = {'M': 'metros', 'UN': 'unidades', 'PÇ': 'peças', 'PC': 'peças', 'KG': 'quilos', 'M2': 'metros quadrados', 'M3': 'metros cúbicos'}


def catalogo(conn):
    with open(os.path.join(S.BASE, 'config', 'materiais_pedido.json'), encoding='utf-8') as f:
        ajustes = json.load(f).get('materiais', {})
    out = []
    for m in _rows(conn.execute('SELECT id,descricao,unidade,propriedade FROM materiais ORDER BY descricao')):
        texto = ' '.join(C._palavras(m['descricao']))
        grupo = next((rot for palavra, rot in [('luva', 'Luva'), ('te', 'Tê'), ('curva', 'Curva'), ('reducao', 'Redução'),
                     ('flange', 'Flange'), ('tampao', 'Tampão'), ('tubo', 'Tubo')] if palavra in texto.split()), 'Outros')
        medida = re.search(r'(?:diametro(?: externo)?|de|dn)\s*[:=]?\s*(\d+(?:[.,]\d+)?(?:\s*[xX/]\s*\d+)*)', m['descricao'], re.I)
        # A busca normalizada também aceita descrições com acento.
        if not medida:
            medida = re.search(r'(?:diametro(?: externo)?|de|dn)\s+(\d+(?:\s+x\s+\d+)*)', texto)
        tamanho = medida.group(1).replace(' ', '') + ' mm' if medida else 'Outros tamanhos'
        metodo = ' eletrofusão' if 'eletrofusao' in texto else ' termofusão' if 'termofusao' in texto else ''
        nome = (grupo + metodo + (' ' + tamanho if medida else '')) if grupo != 'Outros' else m['descricao'].split('(')[0].strip().capitalize()
        # Pressão, resina e ângulo distinguem peças de mesma bitola.
        detalhes = []
        for padrao, prefixo in [(r'(?:pressao|pn)\s*(\d+(?:\s+\d+)?)', 'PN '), (r'pe\s*(\d+)', 'PE'), (r'(\d+)\s*graus', '')]:
            v = re.search(padrao, texto)
            if v:
                detalhes.append(prefixo + v.group(1) + ('°' if not prefixo else ''))
        if detalhes:
            nome += ' · ' + ' · '.join(detalhes)
        item = {'id': m['id'], 'nome': nome, 'tipo': grupo, 'tamanho': tamanho, 'descricao': m['descricao'],
                'unidade': m['unidade'], 'unidade_nome': UNIDADES.get(m['unidade'], m['unidade'].lower()),
                'caesb': m['propriedade'] == 'CAESB'}
        item.update({k: v for k, v in ajustes.get(m['id'], {}).items() if k in ('nome', 'tipo', 'tamanho')})
        out.append(item)
    return out


def abrir(conn, corpo, usuario):
    frente = corpo.get('frente_id')
    if not _one(conn, 'SELECT id FROM equipes WHERE id=?', frente):
        raise RegraViolada('Toque na zona ou frente de destino.')
    if usuario.get('restrito_a_equipe') and frente != usuario.get('equipe_id'):
        raise RegraViolada('O encarregado solicita para a frente da própria equipe.')
    itens = corpo.get('itens') or []
    if not itens or len(itens) > 50:
        raise RegraViolada('Escolha de 1 a 50 materiais.')
    obs = str(corpo.get('observacao') or '').strip()
    if len(obs) > 600:
        raise RegraViolada('A observação deve ter até 600 caracteres.')
    data = corpo.get('data') or S.RL.hoje().isoformat()
    S.exigir_data_ocorrida(data, 'Solicitação')
    with transacao(conn):
        sid = conn.execute('INSERT INTO solicitacoes_compra(data,solicitante,motivo,criada_em) VALUES (?,?,?,?)',
                           (data, usuario['login'], obs, S._agora())).lastrowid
        conn.execute('INSERT INTO solicitacao_detalhes VALUES (?,?)', (sid, frente))
        for it in itens:
            q = numero(it.get('quantidade'))
            if not q:
                raise RegraViolada('Informe quanto precisa.')
            if it.get('material_id'):
                if not _one(conn, 'SELECT id FROM materiais WHERE id=?', it['material_id']):
                    raise RegraViolada('Material não encontrado.')
                conn.execute('INSERT INTO solicitacao_itens(solicitacao_id,material_id,quantidade) VALUES (?,?,?)', (sid, it['material_id'], q))
            else:
                desc = str(it.get('descricao') or '').strip()
                foto = it.get('foto_b64')
                if (not desc and not foto) or len(desc) > 600:
                    raise RegraViolada('Escreva o que precisa ou tire uma foto (texto até 600 caracteres).')
                unidade = it.get('unidade') or 'UN'
                if unidade not in UNIDADES:
                    raise RegraViolada('Escolha a unidade.')
                doc = C.guardar_documento(conn, 'NF_IMAGEM', foto, 'material-solicitado.jpg', usuario['login'], C.documento_dir(conn)) if foto else None
                conn.execute('INSERT INTO solicitacao_avulsos(solicitacao_id,descricao,quantidade,unidade,documento_id) VALUES (?,?,?,?,?)',
                             (sid, desc or 'Material da foto', q, unidade, doc))
    return {'id': sid}


def decidir(conn, corpo, por):
    sid = int(corpo.get('solicitacao_id') or 0)
    aprovar = corpo.get('aprovar') is True
    with transacao(conn):
        if aprovar:
            escolhas = {int(x.get('id') or 0): x for x in corpo.get('avulsos') or []}
            for it in _rows(conn.execute('SELECT * FROM solicitacao_avulsos WHERE solicitacao_id=?', (sid,))):
                esc = escolhas.get(it['id'], {})
                mid = esc.get('material_id') or it['material_id']
                m = _one(conn, 'SELECT unidade FROM materiais WHERE id=?', mid)
                if not m:
                    raise RegraViolada('Identifique o material descrito ou fotografado antes de aprovar.')
                q = numero(esc.get('quantidade', it['quantidade']))
                if not q:
                    raise RegraViolada('Informe a quantidade na unidade do material.')
                if m['unidade'] != it['unidade'] and 'quantidade' not in esc:
                    raise RegraViolada('Confira a quantidade na unidade do material escolhido.')
                conn.execute('UPDATE solicitacao_avulsos SET material_id=?,unidade=?,quantidade=? WHERE id=?', (mid, m['unidade'], q, it['id']))
        C.decidir_solicitacao(conn, sid, aprovar, corpo.get('motivo'), por)
    return {'ok': True}


def listar(conn, usuario):
    aprova = 'compras_aprovar' in usuario['permissoes']
    sql = 'SELECT s.*,d.frente_id FROM solicitacoes_compra s LEFT JOIN solicitacao_detalhes d ON d.solicitacao_id=s.id'
    sql += '' if aprova else ' WHERE lower(s.solicitante)=lower(?)'
    rows = _rows(conn.execute(sql + ' ORDER BY s.id DESC LIMIT 200', () if aprova else (usuario['login'],)))
    nomes = {x['id']: x for x in catalogo(conn)}
    for s in rows:
        s['itens'] = _rows(conn.execute('SELECT material_id,quantidade FROM solicitacao_itens WHERE solicitacao_id=?', (s['id'],)))
        s['avulsos'] = _rows(conn.execute('SELECT * FROM solicitacao_avulsos WHERE solicitacao_id=?', (s['id'],)))
        for i in s['itens'] + s['avulsos']:
            m = nomes.get(i['material_id'], {})
            i['nome'] = m.get('nome') or i.get('descricao')
            i['unidade_nome'] = m.get('unidade_nome') or UNIDADES.get(i.get('unidade'), 'unidades')
        necessario = {}
        for i in s['itens'] + s['avulsos']:
            necessario[i['material_id']] = necessario.get(i['material_id'], 0) + i['quantidade']
        recebido = dict(conn.execute("""SELECT ni.material_id,SUM(i.aceito) FROM solicitacao_notas sn
            JOIN nf_itens ni ON ni.nf_id=sn.nf_id JOIN recebimento_itens ri ON ri.nf_item_id=ni.id
            JOIN inspecoes i ON i.recebimento_item_id=ri.id WHERE sn.solicitacao_id=? GROUP BY ni.material_id""", (s['id'],)))
        s['situacao'] = 'CHEGOU' if s['status'] == 'APROVADA' and necessario and all(mid and recebido.get(mid, 0) >= q - C.TOL for mid, q in necessario.items()) else s['status']
    return rows


def vincular(conn, corpo, por):
    nf, sid = int(corpo.get('nf_id') or 0), int(corpo.get('solicitacao_id') or 0)
    if not _one(conn, "SELECT 1 FROM notas_fiscais WHERE id=? AND status<>'CANCELADA'", nf):
        raise RegraViolada('Nota não encontrada.')
    if not _one(conn, "SELECT 1 FROM solicitacoes_compra WHERE id=? AND status='APROVADA'", sid):
        raise RegraViolada('Escolha uma solicitação aprovada.')
    atual = _one(conn, 'SELECT solicitacao_id FROM solicitacao_notas WHERE nf_id=?', nf)
    if atual and atual['solicitacao_id'] != sid:
        raise RegraViolada('Esta nota já está vinculada a outra solicitação.')
    conn.execute('INSERT OR IGNORE INTO solicitacao_notas VALUES (?,?,?,?)', (nf, sid, por, S._agora()))
    return {'ok': True}


def foto(conn, avulso_id, usuario):
    x = _one(conn, '''SELECT a.documento_id,s.solicitante FROM solicitacao_avulsos a
        JOIN solicitacoes_compra s ON s.id=a.solicitacao_id WHERE a.id=?''', avulso_id)
    if not x or not x['documento_id'] or (x['solicitante'] != usuario['login'] and 'compras_aprovar' not in usuario['permissoes']):
        raise RegraViolada('Foto não disponível para este usuário.')
    d = _one(conn, 'SELECT arquivo,mime FROM documentos WHERE id=?', x['documento_id'])
    with open(os.path.join(C.documento_dir(conn), d['arquivo']), 'rb') as f:
        return {'imagem': 'data:' + d['mime'] + ';base64,' + base64.b64encode(f.read()).decode('ascii')}
