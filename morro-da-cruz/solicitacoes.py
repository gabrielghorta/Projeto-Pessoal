"""Necessidade de material por frente. Solicitar ou aprovar nunca bloqueia nota, entrega ou estoque."""
import base64
import json
import os
import re
import unicodedata

import compras as C
import servicos as S
from recebimento import numero
from servicos import RegraViolada, _one, _rows, transacao

UNIDADES = {'M': 'metros', 'UN': 'unidades', 'PÇ': 'peças', 'PC': 'peças', 'KG': 'quilos', 'M2': 'metros quadrados',
            'M3': 'metros cúbicos', 'SC': 'sacos'}

# Pedir material (D-173): o tipo vem do começo da descrição; a ordem importa ("TE DE SERVICO" é ligação de água, não tê)
_TIPOS = [("Ligação de água", r"(HIDROMETRO|KIT CAVALETE|CAIXA DE PROTECAO|ABRIGO|ADAPTADOR|TE DE SERVICO|UNIAO)"),
          ("Tubo", r"TUBO"), ("Luva", r"LUVA"), ("Tê", r"TE\b"), ("Curva", r"CURVA"), ("Redução", r"REDUCAO"),
          ("Flange", r"(FLANGE|COLARINHO|ACESSORIOS? PARA FLANGE)"), ("Toco", r"(TOCO|EXTREMIDADE)"),
          ("Válvula", r"(VALVULA|VENTOSA|HIDRANTE)"), ("Tampa", r"TAMPA"),
          ("Obra", r"(AREIA|BRITA|CIMENTO|MADEIRA|TERRA|CONCRETO|CONE|TELA|TENDA|PLACA|PILAR|ESCADA|ANEL|FOSSA)")]
_CONEXOES = {"Tubo", "Luva", "Tê", "Curva", "Redução", "Flange", "Toco"}
_NAO_E_MATERIAL = r"(SERVICO|LOCACAO|TAXA|INFRAESTRUTURA|RECURSOS)"      # serviço e administração local não se pedem
_SEM_BITOLA = ("ABRIGO", "CAIXA")                    # o "diâmetro de 50 mm" do abrigo é o do tubo que passa nele
_ACENTOS = {"Te": "Tê", "servico": "serviço", "Uniao": "União", "Tampao": "Tampão", "sinalizacao": "sinalização",
            "septica": "séptica", "autoadensavel": "autoadensável", "bombeavel": "bombeável", "nao": "não", "pvc": "PVC"}
# tamanho: duas bitolas (redução, tê de redução, tê de sela) antes de uma; polegada antes de milímetro
_DUAS = [r"DIAMETRO (?:MAIOR|DE ENTRADA)\s*:\s*(\d+)\s*MM\s*/\s*DIAMETRO (?:MENOR|DE SAIDA)\s*:\s*(\d+)",
         r"\bDN[\s-]*(\d+)\s*X\s*(\d+)\s*MM", r"DIAMETRO EXTERNO DE\s*(\d+)\s*MM.*?DA SAIDA\s*:\s*(\d+)"]
_POLEGADA = [r"DIAMETRO[^:/(]*:\s*(\d+ \d/\d|\d/\d|\d+)\s*\"", r"\b(\d/\d)\""]
_UMA = [r"DIAMETRO[^:/(]*:\s*(\d+)\s*MM", r"DIAMETRO EXTERNO DE\s*(\d+)\s*MM", r"\bDN\s*[=:]?\s*(\d+)",
        r"\bDE\s*[=:]?\s*(\d+)\s*MM", r"\bDE(\d+)\b", r"\b(\d+)\s*X\s*(\d+)\s*MM", r"\bTAMPA (\d+)\s*MM", r",\s*(\d+)\s*MM\b"]
# o que separa dois materiais de mesmo nome (o primeiro que difere entre eles entra no nome)
_DETALHES = [(r"(SEM|COM) ALMA", lambda m: m.group(1).lower() + " alma"),
             (r"COMPRIMENTO\s*:\s*([\d,]+)\s*(MM|M)\b", lambda m: f"{m.group(1)} {m.group(2).lower()} de comprimento"),
             (r"CLASSE DE PRESSAO\s*:\s*([\d/]+)", lambda m: "PN " + m.group(1)),
             (r"\bPN[\s-]*(\d+)", lambda m: "PN " + m.group(1)), (r"AUTO OPERADA", lambda m: "auto operada")]


def _maiusculo(texto):
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().upper()


def _tamanho(t):
    for padrao in _DUAS:
        m = re.search(padrao, t)
        if m:
            return f"{m.group(1)}×{m.group(2)} mm"
    for padrao in _POLEGADA:
        m = re.search(padrao, t)
        if m:
            return m.group(1) + '"'
    for padrao in _UMA:
        m = re.search(padrao, t)
        if m:
            return "×".join(g for g in m.groups() if g) + " mm"
    return ""


def _nome_curto(descricao):
    """O começo da descrição: até a vírgula, o parêntese ou o primeiro "com/em/para/de/do/da" depois de duas palavras."""
    texto = re.split(r"\s*[(:;]|, | - |\. ", descricao.replace("*", ""))[0].strip()
    palavras = texto.split()
    for i in range(2, len(palavras)):
        if _maiusculo(palavras[i]) in ("COM", "EM", "PARA", "DE", "DO", "DA", "SEM", "TIPO") and i < len(palavras) - 1:
            palavras = palavras[:i]
            break
    nome = " ".join(palavras[:8]).capitalize().split()
    return " ".join(_ACENTOS.get(p, p) for p in nome)


def _nome_conexao(tipo, t):
    """Tubo e conexões: o nome como se fala na obra ("Luva eletrofusão", "Redução ferro", "Tê de sela")."""
    metodo = "eletrofusão" if "ELETROFUSAO" in t else "termofusão" if "TERMOFUSAO" in t else ""
    material = "ferro" if "FERRO FUNDIDO" in t else "PEAD" if ("POLIETILENO" in t or "PEAD" in t) else ""
    if tipo == "Flange":
        if "PARAFUSO" in t:                          # o parafuso vem "com porca e duas arruelas"
            return "Parafuso sextavado"
        if "ARRUELA" in t:
            return "Arruela de borracha"
        return "Colarinho PEAD" if t.startswith("COLARINHO") else "Flange solto" if "SOLTO" in t else "Flange"
    if tipo == "Toco":
        base = "Extremidade flange e ponta" if t.startswith("EXTREMIDADE") else "Toco com aba" if "ABA DE VEDACAO" in t else "Toco"
        return base + (" ferro" if material == "ferro" and base == "Toco" else "")
    nome = {"Curva": "Curva 90°" if "90" in t[:12] else "Curva", "Tê": "Tê de sela" if "SELA" in t else "Tê de redução"
            if "DE REDUCAO" in t else "Tê", "Redução": "Redução excêntrica" if "EXCENTRICA" in t else "Redução",
            "Luva": "Luva de correr" if "DE CORRER" in t else "Luva"}.get(tipo, tipo)
    if tipo == "Tubo" and material == "ferro":
        return "Tubo ferro " + ("flange e ponta" if "FLANGE E PONTA" in t else "com flanges")
    return " ".join(x for x in (nome, metodo or material) if x)


def catalogo(conn):
    """Os materiais da tela Pedir material (D-173), sem código: tipo, tamanho e um nome curto tirados da descrição.
    config/materiais_pedido.json corrige o nome, o tipo ou o tamanho de um material, pelo id."""
    with open(os.path.join(S.BASE, 'config', 'materiais_pedido.json'), encoding='utf-8') as f:
        ajustes = json.load(f).get('materiais', {})
    out = []
    for m in _rows(conn.execute('SELECT id,descricao,unidade,propriedade FROM materiais ORDER BY descricao')):
        t = _maiusculo(m['descricao'])
        if re.match(_NAO_E_MATERIAL, t) and m['id'] not in ajustes:
            continue
        tipo = next((rot for rot, padrao in _TIPOS if re.match(padrao, t)), 'Outros')
        tamanho = _tamanho(t) if tipo != 'Obra' and not t.startswith(_SEM_BITOLA) else ''
        nome = _nome_conexao(tipo, t) if tipo in _CONEXOES else _nome_curto(m['descricao'])
        if tamanho and tamanho.replace(' mm', '') not in nome.split():
            nome += ' ' + tamanho
        out.append({'id': m['id'], 'nome': nome, 'tipo': tipo, 'tamanho': tamanho, 'descricao': m['descricao'],
                    'unidade': m['unidade'], 'unidade_nome': UNIDADES.get(m['unidade'].upper(), m['unidade'].lower()),
                    'caesb': m['propriedade'] == 'CAESB', '_t': t})
    # mesmo nome, descrições diferentes, do mesmo dono: entra o primeiro detalhe que os separa
    grupos = {}
    for item in out:
        grupos.setdefault((item['nome'], item['caesb']), []).append(item)
    for itens in grupos.values():
        if len({i['descricao'] for i in itens}) < 2:
            continue
        for padrao, rotulo in _DETALHES:
            achados = [re.search(padrao, i['_t']) for i in itens]
            valores = [rotulo(a) if a else '' for a in achados]
            if len(set(valores)) > 1:
                for i, v in zip(itens, valores):
                    if v:
                        i['nome'] += ' · ' + v
                break
    for item in out:
        del item['_t']
        item.update({k: v for k, v in ajustes.get(item['id'], {}).items() if k in ('nome', 'tipo', 'tamanho')})
    # os botões de tipo saem nesta ordem; dentro do tipo, da bitola menor para a maior
    ordem = [rot for rot, _ in _TIPOS] + ['Outros']
    bitola = lambda i: int(re.match(r'\d*', i['tamanho']).group() or 0)
    return sorted(out, key=lambda i: (ordem.index(i['tipo']) if i['tipo'] in ordem else len(ordem), bitola(i), i['nome']))


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
    # quem aprova e quem abre Compras e notas (os requerimentos, D-187) vê os pedidos da obra; os outros, só os seus
    todos = 'compras_aprovar' in usuario['permissoes'] or 'compras' in usuario.get('telas', ())
    sql = 'SELECT s.*,d.frente_id FROM solicitacoes_compra s LEFT JOIN solicitacao_detalhes d ON d.solicitacao_id=s.id'
    sql += '' if todos else ' WHERE lower(s.solicitante)=lower(?)'
    rows = _rows(conn.execute(sql + ' ORDER BY s.id DESC LIMIT 200', () if todos else (usuario['login'],)))
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
        # Compras e notas (D-187): as notas ligadas e, do aprovado, o que ainda falta chegar (a lista "A comprar")
        s['notas'] = [r[0] for r in conn.execute('''SELECT n.numero FROM solicitacao_notas sn JOIN notas_fiscais n ON n.id=sn.nf_id
            WHERE sn.solicitacao_id=? ORDER BY n.id''', (s['id'],))]
        s['falta'] = [{'material_id': mid, 'nome': nomes.get(mid, {}).get('nome') or mid,
                       'unidade_nome': nomes.get(mid, {}).get('unidade_nome') or 'unidades',
                       'quantidade': round(q - recebido.get(mid, 0), 6)}
                      for mid, q in necessario.items() if mid and q - recebido.get(mid, 0) > C.TOL] if s['situacao'] == 'APROVADA' else []
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
