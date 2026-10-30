"""Arquivo XML do MS Project (MSPDI) com o mesmo plano da planilha: o Project abre direto e salva como .mpp."""
import datetime as dt
from xml.sax.saxutils import escape

import motor
from motor import CAL, DIA, FERIADOS, NOME, OS, PRAZO, REAJUSTE

ISO = '%Y-%m-%dT%H:%M:%S'
TIPO = {'FS': 1, 'SS': 3, 'FF': 0}
CAMPOS = [('Text1', 188743731, 'Equipe'), ('Text2', 188743734, 'Zona / frente'), ('Text3', 188743737, 'Fase'),
          ('Number1', 188743767, 'Extensão (m)'), ('Number2', 188743768, 'DE (mm)'),
          ('Number3', 188743769, 'Ligações (est.)')]


def dur(minutos):
    h, m = divmod(int(round(minutos)), 60)
    return f'PT{h}H{m}M0S'


class Projeto:
    def __init__(self):
        self.tarefas = []          # dicts
        self.uid = 0

    def add(self, nome, nivel, ini=None, fim=None, resumo=False, marco=False, snet=None, links=(), recurso=None,
            campos=None, notas=None, prazo=None, pct=0):
        self.uid += 1
        t = {'uid': self.uid, 'nome': nome, 'nivel': nivel, 'ini': ini, 'fim': fim, 'resumo': resumo, 'marco': marco,
             'snet': snet, 'links': list(links), 'recurso': recurso, 'campos': campos or {}, 'notas': notas,
             'prazo': prazo, 'pct': pct}
        self.tarefas.append(t)
        return t


def montar(plano, cen):
    T, E = plano['T'], plano['E']
    tr = plano['trechos']
    P = Projeto()
    uid_tr = {}

    def tarefa_trecho(i, nivel, link_ant, snet=None):
        t, x = T[i], tr[i]
        tk = P.add(f"{t['R']} - DE {t['de']} - {t['L']:.2f} m", nivel, x['ini'], x['fim'], snet=snet,
                   links=[('FS', link_ant, 0)] if link_ant else [], recurso=x['eq'],
                   campos={'Text1': NOME[x['eq']], 'Text2': 'Subadutora' if t['sub'] else t['loc'],
                           'Text3': x['fase'], 'Number1': t['L'], 'Number2': t['de'], 'Number3': round(t['lig'], 1)})
        uid_tr[i] = tk['uid']
        return tk['uid']

    raiz = P.add(f"CT 10.239/2026 - MORRO DA CRUZ - REV00 - {cen['titulo']}", 1, resumo=True)
    m_os = P.add('INÍCIO DA OBRA - EMISSÃO DA O.S.', 2, 0, 0, marco=True, snet=0)
    P.add('CANTEIRO', 2, resumo=True)
    P.add('DEMARCAÇÃO, ALAMBRADO METÁLICO, PORTÃO E 2 CONTÊINERES (EXECUTADO EM OUT/2026)', 3, *plano['canteiro'],
          snet=plano['canteiro'][0], links=[('FS', m_os['uid'], 0)], pct=100)
    P.add('DEMAIS INSTALAÇÕES DO CANTEIRO E MAIS 4 CONTÊINERES', 3, *plano['canteiro_inst'], snet=plano['canteiro_inst'][0])
    for d, n, quem in [(motor.CONTEINERES[2][0], 6, 'EMPREITEIRO 1'), (motor.CONTEINERES[3][0], 6, 'EMPREITEIRO 2')]:
        w = CAL.w(d)
        P.add(f'CHEGADA DE {n} CONTÊINERES - {quem}', 3, w, w, marco=True, snet=w)
    w_reaj = CAL.w(REAJUSTE)
    P.add('ANIVERSÁRIO DO CONTRATO - REAJUSTE (o que começa a partir de 01/02/2027)', 2, w_reaj, w_reaj, marco=True,
          snet=w_reaj)
    ultimo_da_equipe = {}
    ultimo_de_bloco = {}               # (zona) -> [uid do último trecho de cada bloco]
    primeiro_de_zona = {}
    lig_tarefas = []

    def bloco_tarefas(b, nivel, eq):
        """Resumo do bloco, os trechos em fila e a tarefa de ligações (5 dias úteis atrás da rede)."""
        nome = f"{b['zona'].replace('Zona', 'ZONA ')} · {b['pb']}"
        P.add(nome, nivel, resumo=True)
        ant = ultimo_da_equipe.get(eq)
        snet = None if ant else CAL.w([e[3] for e in motor.EQUIPES if e[0] == eq][0])
        primeiro = None
        for i in b['trechos']:
            u = tarefa_trecho(i, nivel + 1, ant, snet)
            snet = None
            primeiro = primeiro or u
            ant = u
        ultimo_da_equipe[eq] = ant
        ultimo_de_bloco.setdefault(b['zona'], []).append(ant)
        primeiro_de_zona.setdefault(b['zona'], []).append(primeiro)
        if b['lig'] > 0.5:
            a, z = b['ini'] + motor.LIG_ATRASO, b['fim'] + motor.LIG_ATRASO
            lt = P.add(f"LIGAÇÕES PREDIAIS - {round(b['lig'])} un (5 dias úteis atrás da rede)", nivel + 1, a, z,
                       links=[('SS', primeiro, motor.LIG_ATRASO), ('FF', ant, motor.LIG_ATRASO)],
                       campos={'Text1': NOME[eq], 'Text2': b['zona'], 'Text3': 'Ligações prediais',
                               'Number3': round(b['lig'], 1)})
            lig_tarefas.append(lt['uid'])

    # Equipe Adutora
    P.add(NOME['ANK1'].upper(), 2, resumo=True)
    P.add('REDES DE 160 mm - PÉ ALTO ATÉ O REAJUSTE', 3, resumo=True)
    for b in [b for b in plano['blocos'] if b.get('pe_alto')]:
        bloco_tarefas(b, 4, 'ANK1')
    P.add('SUBADUTORA (ADUTORA + REDES DE DE 225 E 250)', 3, resumo=True)
    sub = [i for i in plano['fila']['ANK1'] if tr[i]['fase'] == 'Subadutora']
    ant = ultimo_da_equipe['ANK1']
    for n, i in enumerate(sub):
        ant = tarefa_trecho(i, 4, ant, w_reaj if n == 0 else None)
    ultimo_da_equipe['ANK1'] = ant
    ult_sub = ant
    blocos_ank1 = [b for b in plano['blocos'] if b['eq'] == 'ANK1' and not b.get('pe_alto')]
    if blocos_ank1:
        P.add('REDES DAS ZONAS (DEPOIS DA SUBADUTORA)', 3, resumo=True)
        for b in sorted(blocos_ank1, key=lambda b: b['ini']):
            bloco_tarefas(b, 4, 'ANK1')
    for eq in ['E1A', 'E1B', 'E2C', 'E2D']:
        P.add(NOME[eq].upper(), 2, resumo=True)
        for b in sorted((b for b in plano['blocos'] if b['eq'] == eq), key=lambda b: b['ini']):
            bloco_tarefas(b, 3, eq)
    # caixas e hidromecânico
    cx = plano['caixas']
    P.add(NOME['ANK2'].upper(), 2, resumo=True)
    P.add('CAIXAS HIDRÁULICAS - OBRA CIVIL', 3, resumo=True)
    uid_civ, uid_hid = {}, {}
    ant = None
    for n, j in enumerate(plano['ordem_civil']):
        e = E[j]
        links = [('FS', uid_tr[i], 0) for i in e['tr'] if i in uid_tr]
        if not links:                     # caixa sem trecho desenhado: espera a rede da zona dela
            z = next((nm[:6] for nm in e['noms'] if nm.startswith('Zona')), None)
            trs_z = [i for i in uid_tr if T[i]['loc'] == z and not T[i]['sub']]
            if trs_z:
                links = [('FS', uid_tr[max(trs_z, key=lambda i: tr[i]['fim'])], 0)]
        if ant:
            links.append(('FS', ant, 0))
        tk = P.add(f"CX {e['tp']} - {e['noms'][0] if e['noms'] else e['id']}", 4, cx[j]['civ_ini'], cx[j]['civ_fim'],
                   snet=CAL.w(motor.EQUIPES[5][3]) if n == 0 else None, links=links, recurso='ANK2',
                   campos={'Text1': NOME['ANK2'], 'Text2': e.get('zona') or '', 'Text3': 'Caixa - obra civil'})
        uid_civ[j] = ant = tk['uid']
    P.add('HIDROMECÂNICO - MONTAGEM (peças de SP e do exterior)', 3, resumo=True)
    ant = None
    for n, j in enumerate(plano['ordem_hidro']):
        e = E[j]
        links = [('FS', uid_civ[j], 0)] + ([('FS', ant, 0)] if ant else [])
        tk = P.add(f"MONTAGEM {e['tp']} - {e['noms'][0] if e['noms'] else e['id']}", 4, cx[j]['hid_ini'],
                   cx[j]['hid_fim'], snet=CAL.w(motor.INICIO_HIDRO) if n == 0 else None, links=links,
                   recurso='ANK2H', campos={'Text1': NOME['ANK2'] + ' - montagem', 'Text2': e.get('zona') or '',
                                            'Text3': 'Hidromecânico'})
        uid_hid[j] = ant = tk['uid']
    # topografia: as notas de serviço 2 semanas antes de cada bloco (sem vínculo; data marcada)
    P.add('TOPOGRAFIA - NOTAS DE SERVIÇO (2 SEMANAS ANTES DE CADA FRENTE)', 2, resumo=True)
    w_topo = CAL.w(motor.TOPO_INICIO)
    for b in sorted(plano['blocos'], key=lambda b: b['ini']):
        a = max(w_topo, b['ini'] - motor.TOPO_ANTES)
        z = max(a + DIA, b['fim'] - motor.TOPO_ANTES)
        P.add(f"NS - {b['zona'].replace('Zona', 'ZONA ')} · {b['pb']}", 3, a, z, snet=a,
              campos={'Text1': 'Topografia', 'Text2': b['zona'], 'Text3': 'Locação com NS'})
    sub_trs = [i for i in plano['fila']['ANK1'] if tr[i]['fase'] == 'Subadutora']
    a = max(w_topo, tr[sub_trs[0]]['ini'] - motor.TOPO_ANTES)
    P.add('NS - SUBADUTORA', 3, a, tr[sub_trs[-1]]['fim'] - motor.TOPO_ANTES, snet=a,
          campos={'Text1': 'Topografia', 'Text2': 'Subadutora', 'Text3': 'Locação com NS'})
    # testes, interligações e cadastro
    P.add('TESTES, INTERLIGAÇÕES E CADASTRO TÉCNICO', 2, resumo=True)
    fe = plano['fechamento']
    zc = plano['zona_cx']
    fim_uids = list(lig_tarefas)
    P.add('SUBADUTORA', 3, resumo=True)
    ts = P.add('TESTE HIDROSTÁTICO E DESINFECÇÃO - SUBADUTORA', 4, *fe['SUB']['teste'], links=[('FS', ult_sub, 0)])
    isub = P.add('INTERLIGAÇÃO - SUBADUTORA', 4, *fe['SUB']['interlig'],
                 links=[('FS', ts['uid'], 0)] + [('FS', uid_hid[j], 0) for j in zc.get('SUB', [])])
    prim_sub = min(sub_trs, key=lambda i: tr[i]['fim'])
    csub = P.add('CADASTRO TÉCNICO - SUBADUTORA', 4, *fe['SUB']['cadastro'],
                 links=[('FS', uid_tr[prim_sub], motor.CADASTRO_DEPOIS), ('FF', ult_sub, motor.CADASTRO_DEPOIS)])
    fim_uids += [isub['uid'], csub['uid']]
    for z in plano['zonas']:
        f = fe[z]
        P.add(z.replace('Zona', 'ZONA '), 3, resumo=True)
        tz = P.add(f"TESTE HIDROSTÁTICO E DESINFECÇÃO - {z.replace('Zona', 'ZONA ')}", 4, *f['teste'],
                   links=[('FS', u, 0) for u in ultimo_de_bloco[z]])
        iz = P.add(f"INTERLIGAÇÃO E ENTRADA EM CARGA - {z.replace('Zona', 'ZONA ')}", 4, *f['interlig'],
                   links=[('FS', tz['uid'], 0), ('FS', ts['uid'], 0)] + [('FS', uid_hid[j], 0) for j in zc.get(z, [])])
        trs_z = [i for i, x in tr.items() if T[i]['loc'] == z and not T[i]['sub']]
        prim = min(trs_z, key=lambda i: tr[i]['fim'])
        ult = max(trs_z, key=lambda i: tr[i]['fim'])
        cz = P.add(f"CADASTRO TÉCNICO - {z.replace('Zona', 'ZONA ')}", 4, *f['cadastro'],
                   links=[('FS', uid_tr[prim], motor.CADASTRO_DEPOIS), ('FF', uid_tr[ult], motor.CADASTRO_DEPOIS)])
        fim_uids += [iz['uid'], cz['uid']]
    ult_hid = uid_hid[plano['ordem_hidro'][-1]]
    des = P.add('DESMOBILIZAÇÃO DO CANTEIRO', 2, *plano['desmob'],
                links=[('FS', u, 0) for u in fim_uids + [ult_hid]])
    P.add('FINAL DA OBRA', 2, plano['fim'], plano['fim'], marco=True, links=[('FS', des['uid'], 0)],
          prazo=CAL.w(PRAZO + dt.timedelta(days=1)))
    return P


def xml(P, plano, cen, caminho):
    tarefas = P.tarefas
    # datas dos resumos: do primeiro filho ao último
    for k, t in enumerate(tarefas):
        if t['resumo']:
            filhos = []
            for u in tarefas[k + 1:]:
                if u['nivel'] <= t['nivel']:
                    break
                if not u['resumo']:
                    filhos.append(u)
            t['ini'] = min(u['ini'] for u in filhos)
            t['fim'] = max(u['fim'] for u in filhos)
    # números de EDT
    cont = [0] * 12
    for t in tarefas:
        n = t['nivel']
        cont[n] += 1
        for j in range(n + 1, 12):
            cont[j] = 0
        t['edt'] = '.'.join(str(cont[j]) for j in range(1, n + 1))
    fim_proj = max(t['fim'] for t in tarefas)
    o = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
         '<Project xmlns="http://schemas.microsoft.com/project">',
         '<SaveVersion>14</SaveVersion>',
         f"<Name>{escape(cen['arquivo'])}.xml</Name>",
         f"<Title>{escape('CT 10.239/2026 - Morro da Cruz - Cronograma físico executivo base - ' + cen['titulo'])}</Title>",
         '<Company>Ankara Engenharia</Company>',
         f'<CreationDate>{dt.datetime(2026, 10, 29, 12, 0):{ISO}}</CreationDate>',
         '<ScheduleFromStart>1</ScheduleFromStart>',
         f'<StartDate>{CAL.inicio(0):{ISO}}</StartDate>',
         f'<FinishDate>{CAL.fim(fim_proj):{ISO}}</FinishDate>',
         '<CurrencySymbol>R$</CurrencySymbol><CurrencyCode>BRL</CurrencyCode>',
         '<CalendarUID>1</CalendarUID>',
         '<DefaultStartTime>07:00:00</DefaultStartTime><DefaultFinishTime>17:00:00</DefaultFinishTime>',
         '<MinutesPerDay>540</MinutesPerDay><MinutesPerWeek>2700</MinutesPerWeek><DaysPerMonth>20</DaysPerMonth>',
         '<DefaultTaskType>1</DefaultTaskType>',
         '<DurationFormat>7</DurationFormat><WorkFormat>2</WorkFormat>',
         '<HonorConstraints>0</HonorConstraints>',
         '<WeekStartDay>1</WeekStartDay>',
         f'<StatusDate>{CAL.inicio(0):{ISO}}</StatusDate>',
         '<NewTasksAreManual>0</NewTasksAreManual>',
         '<ExtendedAttributes>']
    for nome, fid, alias in CAMPOS:
        o.append(f'<ExtendedAttribute><FieldID>{fid}</FieldID><FieldName>{nome}</FieldName>'
                 f'<Alias>{escape(alias)}</Alias></ExtendedAttribute>')
    o.append('</ExtendedAttributes>')
    # calendário
    o += ['<Calendars><Calendar><UID>1</UID><Name>Morro da Cruz - seg a sex 7h-17h</Name><IsBaseCalendar>1</IsBaseCalendar>',
          '<BaseCalendarUID>-1</BaseCalendarUID><WeekDays>']
    for d in range(1, 8):
        if d in (1, 7):
            o.append(f'<WeekDay><DayType>{d}</DayType><DayWorking>0</DayWorking></WeekDay>')
        else:
            o.append(f'<WeekDay><DayType>{d}</DayType><DayWorking>1</DayWorking><WorkingTimes>'
                     '<WorkingTime><FromTime>07:00:00</FromTime><ToTime>12:00:00</ToTime></WorkingTime>'
                     '<WorkingTime><FromTime>13:00:00</FromTime><ToTime>17:00:00</ToTime></WorkingTime>'
                     '</WorkingTimes></WeekDay>')
    o.append('</WeekDays><Exceptions>')
    for d, nome in sorted(FERIADOS.items()):
        if OS <= d <= dt.date(2029, 12, 31) and d.weekday() < 5:
            o.append(f'<Exception><EnteredByOccurrences>0</EnteredByOccurrences><TimePeriod>'
                     f'<FromDate>{d:%Y-%m-%d}T00:00:00</FromDate><ToDate>{d:%Y-%m-%d}T23:59:00</ToDate></TimePeriod>'
                     f'<Occurrences>1</Occurrences><Name>{escape(nome)}</Name><Type>1</Type>'
                     f'<DayWorking>0</DayWorking></Exception>')
    o.append('</Exceptions></Calendar></Calendars>')
    # tarefas
    o.append('<Tasks>')
    o.append(f"<Task><UID>0</UID><ID>0</ID><Name>{escape(cen['arquivo'])}</Name><Type>1</Type><IsNull>0</IsNull>"
             f"<WBS>0</WBS><OutlineNumber>0</OutlineNumber><OutlineLevel>0</OutlineLevel>"
             f"<Start>{CAL.inicio(0):{ISO}}</Start><Finish>{CAL.fim(fim_proj):{ISO}}</Finish>"
             f"<Duration>{dur(fim_proj)}</Duration><DurationFormat>7</DurationFormat><Milestone>0</Milestone>"
             f"<Summary>1</Summary><ConstraintType>0</ConstraintType><CalendarUID>-1</CalendarUID>"
             f"<Active>1</Active><Manual>0</Manual></Task>")
    for n, t in enumerate(tarefas, 1):
        ini, fim = t['ini'], t['fim']
        d = 0 if t['marco'] else max(0, fim - ini)
        s_ini = CAL.inicio(ini)
        s_fim = CAL.fim(fim)
        if t['marco']:
            s_ini = s_fim = CAL.inicio(t['snet']) if t['snet'] is not None else CAL.fim(fim)
        x = [f'<Task><UID>{t["uid"]}</UID><ID>{n}</ID><Name>{escape(t["nome"])}</Name><Type>1</Type>',
             f'<IsNull>0</IsNull><WBS>{t["edt"]}</WBS><OutlineNumber>{t["edt"]}</OutlineNumber>',
             f'<OutlineLevel>{t["nivel"]}</OutlineLevel><Priority>500</Priority>',
             f'<Start>{s_ini:{ISO}}</Start><Finish>{s_fim:{ISO}}</Finish>',
             f'<Duration>{dur(d)}</Duration><DurationFormat>7</DurationFormat>',
             f'<Milestone>{int(t["marco"])}</Milestone><Summary>{int(t["resumo"])}</Summary>',
             f'<PercentComplete>{t["pct"]}</PercentComplete>']
        if t['snet'] is not None and not t['resumo']:
            x.append(f'<ConstraintType>4</ConstraintType><CalendarUID>-1</CalendarUID>'
                     f'<ConstraintDate>{CAL.inicio(t["snet"]):{ISO}}</ConstraintDate>')
        else:
            x.append('<ConstraintType>0</ConstraintType><CalendarUID>-1</CalendarUID>')
        if t['prazo'] is not None:
            x.append(f'<Deadline>{CAL.fim(t["prazo"]):{ISO}}</Deadline>')
        if t['notas']:
            x.append(f'<Notes>{escape(t["notas"])}</Notes>')
        for tipo, pred, lag in t['links']:
            x.append(f'<PredecessorLink><PredecessorUID>{pred}</PredecessorUID><Type>{TIPO[tipo]}</Type>'
                     f'<CrossProject>0</CrossProject><LinkLag>{int(lag * 10)}</LinkLag><LagFormat>7</LagFormat>'
                     f'</PredecessorLink>')
        for nome, fid, _ in CAMPOS:
            v = t['campos'].get(nome)
            if v not in (None, ''):
                x.append(f'<ExtendedAttribute><FieldID>{fid}</FieldID><Value>{escape(str(v))}</Value></ExtendedAttribute>')
        if not t['resumo']:
            x.append(f'<Baseline><Number>0</Number><Start>{s_ini:{ISO}}</Start><Finish>{s_fim:{ISO}}</Finish>'
                     f'<Duration>{dur(d)}</Duration><DurationFormat>7</DurationFormat>'
                     f'<EstimatedDuration>0</EstimatedDuration></Baseline>')
        x.append('<Active>1</Active><Manual>0</Manual></Task>')
        o.append(''.join(x))
    o.append('</Tasks>')
    # recursos e atribuições
    recursos = [('ANK1', NOME['ANK1']), ('E1A', NOME['E1A']), ('E1B', NOME['E1B']), ('E2C', NOME['E2C']),
                ('E2D', NOME['E2D']), ('ANK2', NOME['ANK2'] + ' - obra civil'), ('ANK2H', NOME['ANK2'] + ' - montagem')]
    ruid = {k: n for n, (k, _) in enumerate(recursos, 1)}
    o.append('<Resources>')
    for k, nome in recursos:
        o.append(f'<Resource><UID>{ruid[k]}</UID><ID>{ruid[k]}</ID><Name>{escape(nome)}</Name><Type>1</Type>'
                 f'<IsNull>0</IsNull><Initials>{k}</Initials><Group>{"Ankara" if k.startswith("ANK") else "Empreiteiro"}</Group>'
                 f'<MaxUnits>1.00</MaxUnits></Resource>')
    o.append('</Resources><Assignments>')
    au = 0
    for t in tarefas:
        if t['recurso'] and not t['resumo']:
            au += 1
            d = max(0, t['fim'] - t['ini'])
            o.append(f'<Assignment><UID>{au}</UID><TaskUID>{t["uid"]}</TaskUID><ResourceUID>{ruid[t["recurso"]]}</ResourceUID>'
                     f'<Finish>{CAL.fim(t["fim"]):{ISO}}</Finish><Start>{CAL.inicio(t["ini"]):{ISO}}</Start>'
                     f'<Units>1</Units><Work>{dur(d)}</Work></Assignment>')
    o.append('</Assignments></Project>')
    open(caminho, 'w', encoding='utf-8').write('\n'.join(o))
    return len(tarefas)
