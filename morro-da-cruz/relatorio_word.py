"""Conteúdo complementar do RM Word (D-218). O gerador PDF e seus dados permanecem iguais.

Somente registros do período originam checklists. Os roteiros são configuração; não criam
execução, verificação ou aceite. Ausência de data impede atribuir ligações a uma semana.
"""
import json
import os
import re
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

import memoria_calculo as MC
import servicos as S
import regras as R
import relatorio_mensal as RM


def estaca(metros):
    cm = int((Decimal(str(metros))*100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    n, resto = divmod(cm, 2000)
    return f"{n}+{resto/100:05.2f}".replace(".", ",")


def complementar(conn, d):
    ini, fim = d["ini"], d["fim"]
    d["word_registros"] = S._rows(conn.execute(f"""SELECT trecho_id,etapa,ini_m,fim_m,data FROM intervalos_execucao
        WHERE {S.EFETIVO} AND data<=? UNION ALL SELECT trecho_id,
        CASE etapa WHEN 'LIBERACAO_TOPOGRAFICA' THEN 'TOPOGRAFIA' ELSE etapa END,ini_m,fim_m,data
        FROM etapas_complementares WHERE anulado_em IS NULL AND data<=? ORDER BY data,trecho_id""", (fim, fim)))
    d["word_soldas"] = S._rows(conn.execute("SELECT alvo_id,tipo,data,quantidade,resultado FROM soldas "
                                           "WHERE alvo_tipo='TRECHO' AND data BETWEEN ? AND ?", (ini, fim)))
    d["word_canteiro"] = S._rows(conn.execute("""SELECT a.*,b.subgrupo_nome,b.descricao bm_descricao FROM apropriacoes a LEFT JOIN bm_itens b ON b.id=a.bm_item_id
        WHERE a.estornado_em IS NULL AND a.data<=? AND (a.local_tipo='CANTEIRO' OR UPPER(b.subgrupo_nome) LIKE '%CANTEIRO%')
        ORDER BY a.data,a.id""", (fim,)))
    d["word_equipes"] = {e["id"]: e for e in S._rows(conn.execute("SELECT id,empresa,ativa,nome FROM equipes"))}
    # Tubos: retrato até o fim do período. Retirada líquida = custódia menos sobra devolvida.
    mov = defaultdict(lambda: defaultdict(float))
    for mid, tipo, q in conn.execute(f"""SELECT material_id,tipo,SUM(quantidade) FROM movimentos WHERE {S.VALIDO}
        AND substr(data,1,10)<=? AND COALESCE(status,'ACEITO')='ACEITO' GROUP BY material_id,tipo""", (fim,)):
        mov[mid][tipo] += q
    tubos = []
    for m in d["materiais"]["tubos"]:
        v = mov[m["material_id"]]
        de = re.search(r"\bDE\s*(\d+)", m["descricao"], re.I)
        cadastrado = d["por_de"].get(int(de[1]), {}).get("cadastro", 0) if de else None
        tubos.append(dict(m, recebido=v["ROMANEIO_CAESB"], emprestado=v["EMPRESTIMO_OUTRA_OBRA"],
            retirado=v["CUSTODIA"]-v["SOBRA"], aplicado=v["APLICADO"], cadastro=cadastrado,
            virtual=v["ROMANEIO_CAESB"]-v["EMPRESTIMO_OUTRA_OBRA"]-v["CUSTODIA"]+v["SOBRA"]))
    d["word_tubos"] = tubos
    por_de = {de:dict(v,locado=0,locado_mes=0,mes=0,acumulado=0) for de,v in d["por_de"].items()}
    for l in conn.execute("""SELECT t.de_mm,l.servico,l.quantidade,m.id mid,m.periodo_fim FROM medicao_lancamentos l
        JOIN medicoes m ON m.id=l.medicao_id JOIN trechos t ON l.alvo_tipo='TRECHO' AND t.id=l.alvo_id
        WHERE l.status='PROPOSTO' AND m.tipo=? AND m.numero<=? AND l.unidade='M'
        AND l.servico IN ('ASSENTAMENTO','LOCAÇÃO C/ NOTA')""", (d["medicao"]["tipo"], d["medicao"]["numero"])):
        v = por_de.get(int(l["de_mm"] or 0))
        if v is not None:
            atual = l["mid"] == d["medicao"]["id"]
            chave = "locado" if l["servico"] == "LOCAÇÃO C/ NOTA" else "acumulado"
            v[chave] += l["quantidade"]
            if atual:
                v["locado_mes" if chave == "locado" else "mes"] += l["quantidade"]
    d["word_por_de"] = por_de
    diario = defaultdict(lambda: {k:set() for k in ("DIRETO", "TERCEIRIZADO", "NAO_INFORMADO")})
    for data, fid, empresa in conn.execute("""SELECT c.data,p.recurso_id,e.empresa FROM checkin_presencas p
        JOIN checkins c ON c.id=p.checkin_id JOIN equipes e ON e.id=c.equipe_id
        WHERE p.recurso_tipo='FUNCIONARIO' AND c.data BETWEEN ? AND ?""", (ini, fim)):
        grupo = "DIRETO" if empresa == "ANKARA" else "TERCEIRIZADO" if empresa in ("E1", "E2") else "NAO_INFORMADO"
        diario[data][grupo].add(fid)
    d["word_efetivo"] = {dt:{k:len(v) for k,v in grupos.items()} for dt,grupos in diario.items()}
    with open(os.path.join(S.BASE,"config","rm_checklists.json"),encoding="utf-8") as arq:
        d["word_checklists"] = json.load(arq)
    import cronograma as CR
    from datetime import timedelta, date
    proximo = date.fromisoformat(fim)+timedelta(days=1)
    ultimo = date(proximo.year+proximo.month//12,proximo.month%12+1,1)-timedelta(days=1)
    d["word_previstas"] = [f"Cronograma: {t['nome']} – {RM.dbr(t['inicio'])} a {RM.dbr(t['fim'])};"
        for t in CR.consultar(conn).get("tarefas",[]) if not t["resumo"] and t.get("inicio") and t.get("fim")
        and t["inicio"][:10]<=ultimo.isoformat() and t["fim"][:10]>=proximo.isoformat()]


def canteiro(d, fl):
    with open(os.path.join(S.BASE,"config","mapa_contexto.json"),encoding="utf-8") as arq:
        pts = json.load(arq)["canteiro"]["vertices_utm"]
    centro = [sum(p[k] for p in pts)/len(pts) for k in (0,1)]
    segs = [tuple(a+b) for a,b in zip(pts,pts[1:]+pts[:1])]
    def mapa(dr,p,x,y,w,h):
        RM._mapa(dr,p,x,y,w,h,[("AABBC8",.8,[t["seg"] for t in d["trechos"].values() if t["seg"]]),("C00000",2.5,segs)],
            [(centro[0],centro[1],"CANTEIRO")],janela=(centro[0]-180,centro[1]-120,centro[0]+180,centro[1]+120))
    fl.figura(fl.w,225,mapa,"Imagem 01 – Localização e polígono do canteiro (mapa_contexto; coordenadas do projeto).")
    fl.titulo(2,"Composição do Canteiro de Obras")
    for a in d["word_canteiro"]:
        calc = MC.ler(a["calculo_json"])
        if calc:
            dim=MC.DIMENSOES[calc["unidade"]]
            for p in calc["parcelas"]:
                medidas=f"perímetro {RM.br(p['comprimento_m'])} m"
                if dim>1:medidas+=f" × {'altura' if dim==2 else 'largura'} {RM.br(float(MC.medida(p['largura'])[0]))} m"
                if dim>2:medidas+=f" × espessura {RM.br(float(MC.medida(p['profundidade'])[0]))} m"
                if p["repeticoes"]!=1:medidas+=f" × {p['repeticoes']} vezes"
                fl.paragrafo(f"{a['o_que_foi_feito']}{' – '+p['descricao'] if p['descricao'] else ''}: {medidas} – {RM.br(p['quantidade'])} {a['unidade']};",marcador=True,depois=3)
        else:
            fl.paragrafo(f"{a['o_que_foi_feito']} – {RM.br(a['quantidade'])} {a['unidade']}; "+(a["memoria_calculo"] or "dimensões PENDENTES"),marcador=True,depois=3)
    if not d["word_canteiro"]:fl.paragrafo("PENDENTE: instalações do canteiro sem apropriação registrada.")
    area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(pts,pts[1:]+pts[:1])))/2
    fl.paragrafo(f"Área total do polígono do canteiro: {RM.br(area)} m² (mapa_contexto).")
    fl.paragrafo("Área construída e fechamento das instalações: PENDENTE do layout atualizado. As medidas acima são as apropriações registradas; não se somam áreas de tapume à área do terreno.")


def _segmento(t, a, b):
    if not t.get("seg") or not t["extensao_m"]:return None
    e,n,f,o=t["seg"];ext=t["extensao_m"]
    return e+(f-e)*a/ext,n+(o-n)*a/ext,e+(f-e)*b/ext,n+(o-n)*b/ext


def croqui_semana(dr,p,x,y,w,h,d,g,ini,fim):
    ids=g["trechos"]
    base=[t["seg"] for t in d["trechos"].values() if t.get("seg")]
    anteriores=[];atuais=[]
    for r in d["word_registros"]:
        seg=_segmento(d["trechos"][r["trecho_id"]],r["ini_m"],r["fim_m"])
        if seg:
            if r["data"]<ini and r["etapa"]=="ASSENTADO":anteriores.append(seg)
            elif r["trecho_id"] in ids and ini<=r["data"]<=fim:atuais.append(seg)
    segs=[d["trechos"][tid]["seg"] for tid in ids if d["trechos"][tid].get("seg")]
    janela=None
    if segs:
        es=[v for s in segs for v in (s[0],s[2])];ns=[v for s in segs for v in (s[1],s[3])]
        ce,cn=(min(es)+max(es))/2,(min(ns)+max(ns))/2
        lado=max(max(es)-min(es),max(ns)-min(ns),200)*1.2
        janela=(ce-lado*w/h/2,cn-lado/2,ce+lado*w/h/2,cn+lado/2)
    RM._mapa(dr,p,x,y,w,h,[("1F4E9E",.6,base),("F2C200",1.7,anteriores),("D00000",2.5,atuais)],janela=janela)


def grupos_semana(d, ini, fim):
    grupos = {}
    def grupo(tid):
        t=d["trechos"].get(tid)
        if not t:return None
        pb=(re.search(r"\b(PB\d+)\b",t["ponto"].replace("_"," ")) or [None,"PENDENTE"])[1]
        k=t["frente_id"],pb,int(t["de_mm"] or 0),t["metodologia"]
        return grupos.setdefault(k,{"frente":k[0],"pb":pb,"dn":k[2],"metodo":k[3],"servicos":set(),"intervalos":[],"trechos":set()})
    for r in d["word_registros"]:
        if ini<=r["data"]<=fim:
            g=grupo(r["trecho_id"])
            if g is not None:
                g["servicos"].add("MND" if g["metodo"]=="MND" and r["etapa"]=="ASSENTADO" else r["etapa"])
                g["trechos"].add(r["trecho_id"]);g["intervalos"].append(r)
    for r in d["word_soldas"]:
        if ini<=r["data"]<=fim:
            g=grupo(r["alvo_id"])
            if g is not None:g["servicos"].add("SOLDA_"+r["tipo"]);g["trechos"].add(r["alvo_id"])
    return [grupos[k] for k in sorted(grupos,key=lambda k:tuple(str(x or "") for x in k))]


def checklist(d, fl, chave, dn, trecho):
    cfg=d["word_checklists"].get(chave)
    if not cfg:return
    fl.paragrafo([(cfg["titulo"]+(' – roteiro a revisar pela engenharia' if cfg.get("revisar") else ''),{"negrito":True})],alin="E",depois=3,junto=True)
    for linha in cfg["itens"]:fl.paragrafo(linha.format(DN=dn,trecho=trecho),marcador=True,depois=2)


def semanas(d,fl):
    for semana in d["semanas"]:
        a,b=semana["ini"],semana["fim"]
        fl.titulo(2,f"Período de {RM.dbr(a)} até {RM.dbr(b)}")
        grupos=grupos_semana(d,a,b)
        for g in grupos:
            fl.paragrafo([(f"{RM._frente(g['frente'])} – {g['pb']} – REDE PEAD DN {g['dn']} MM",{"negrito":True})],alin="E",junto=True)
            fl.paragrafo(f"Croqui de Locação – PRANCHA {g['pb']}",alin="E",junto=True)
            trs=g["trechos"]
            # Recorte por frente, com legenda fora da rede e trechos executados nesta semana.
            fl.figura(fl.w,205,lambda dr,p,x,y,w,h,g=g,a=a,b=b:croqui_semana(dr,p,x,y,w,h,d,g,a,b),
                      "Figura 01 – EXECUTADO (vermelho) · ANTERIOR (amarelo) · NÃO EXECUTADO (azul).")
            rows=[["ZONA / PRANCHA / DN","TRECHO E SERVIÇO","ESTACAS E COMPRIMENTO"]]
            for r in g["intervalos"]:
                t=d["trechos"][r["trecho_id"]]
                rows.append([f"{RM._frente(g['frente'])} · {g['pb']} · DN {g['dn']}",t["ponto"].split('_')[-1]+" · "+RM._etapa(r["etapa"]),
                             f"EST. {estaca(r['ini_m'])} ATÉ EST. {estaca(r['fim_m'])} – {RM.br(r['fim_m']-r['ini_m'])} M"])
            if len(rows)==1:rows.append([{"t":"Solda registrada; não há intervalo de rede lançado nesta semana.","span":3}])
            fl.tabela([.27,.27,.46],rows)
            fl.paragrafo("SERVIÇOS:",junto=True)
            for chave in sorted(g["servicos"]):
                tids={r["trecho_id"] for r in g["intervalos"] if r["etapa"]==chave or chave=="MND" and r["etapa"]=="ASSENTADO"}
                if chave.startswith("SOLDA_"):tids={r["alvo_id"] for r in d["word_soldas"] if a<=r["data"]<=b and "SOLDA_"+r["tipo"]==chave and r["alvo_id"] in g["trechos"]}
                trechos=", ".join(d["trechos"][tid]["ponto"].split('_')[-1] for tid in sorted(tids))
                checklist(d,fl,chave,g["dn"],trechos)
        for ap in semana["apropriacoes"]:
            fl.paragrafo(f"{ap['o_que_foi_feito']} – {RM.br(ap['quantidade'])} {ap['unidade']} ({RM.dbr(ap['data'])}, item {ap['item']});",marcador=True)
            # O roteiro do tapume só entra para apropriação de tapume; não para qualquer gasto no canteiro.
            fonte = next((x for x in d["word_canteiro"] if x["id"] == ap["id"]), {})
            if "tapume" in (fonte.get("bm_descricao") or ap["o_que_foi_feito"]).lower():
                checklist(d,fl,"CANTEIRO","—","canteiro")
        for o in semana["ocorrencias"]:fl.paragrafo(f"{RM.dbr(o['data'])}: {o['descricao'] or o['categoria']};",marcador=True)
        if not grupos and not semana["apropriacoes"] and not semana["ocorrencias"]:fl.paragrafo("Sem serviço registrado nesta semana.")


def equipes(d,fl):
    fl.paragrafo("RESUMO ID-EQUIPES",junto=True)
    rows=[["TIPOLOGIA","EMPRESA","CATEGORIA","ID EQUIPE","DESCRIÇÃO","SITUAÇÃO","TOTAL INTEGRANTES"]]
    for e in d["equipes"]:
        cad=d["word_equipes"].get(e["id"],{})
        empresa={"ANKARA":"Ankara","E1":"Empreiteiro 1","E2":"Empreiteiro 2"}.get(cad.get("empresa"),"PENDENTE")
        rows.append(["PRÓPRIA" if empresa=="Ankara" else "SUBCONTRATADA" if empresa!="PENDENTE" else "PENDENTE",
                     empresa,"PENDENTE",e["id"],e["nome"],"COM CHECK-IN" if e["dias"] else "SEM CHECK-IN NO PERÍODO",str(e["funcionarios"])])
    if len(rows)==1:rows.append([{"t":"Sem equipe ativa ou com check-in no período.","span":7}])
    fl.tabela([.12,.13,.11,.09,.23,.17,.15],rows)
    fl.paragrafo([("Tabela 01 – Resumo ID-equipes. Categoria técnica não informada no cadastro permanece PENDENTE.",{"italico":True,"cor":"595959"})],tam=9,alin="C")


def tubos(d,fl):
    if not fl.paisagem:fl.nova_pagina(True)
    fl.paragrafo("COMPATIBILIZAÇÃO DE TUBOS – FORNECIMENTO CAESB",junto=True)
    cab=["MATERIAL","UN.","PROJETO","ESTOQUE CAESB (ROMANEIO)","EMPRESTADO","RETIRADO ANKARA","APLICADO","CADASTRO TÉCNICO","ESTOQUE VIRTUAL","% EXECUTADO"]
    rows=[cab];total=defaultdict(float)
    for m in d["word_tubos"]:
        rows.append([m["descricao"],m["unidade"]]+[RM.br(m[k]) for k in ("previsto","recebido","emprestado","retirado","aplicado","cadastro","virtual")]+[RM.pct(m["aplicado"]/m["previsto"]) if m["previsto"] else "—"])
        for k in ("previsto","recebido","emprestado","retirado","aplicado","cadastro","virtual"):total[k]+=m[k] or 0
    values=[RM.br(total[k]) for k in ("previsto","recebido","emprestado","retirado","aplicado","cadastro","virtual")]+[RM.pct(total["aplicado"]/total["previsto"]) if total["previsto"] else "—"]
    rows.extend([["SUBTOTAL PEAD","M"]+values,["TOTAL GERAL","M"]+values])
    fl.tabela([.23,.04,.08,.1,.08,.09,.08,.1,.1,.1],rows,total=True)
    fl.paragrafo([("Tabela 01 – Tubos até o fim do período. Estoque virtual = romaneio − emprestado − retirado; retirada líquida = custódia − sobra devolvida. % executado = aplicado ÷ projeto.",{"italico":True,"cor":"595959"})],tam=9,alin="C")


def redes(d,fl,execucao=False):
    if not fl.paisagem:fl.nova_pagina(True)
    rows=[["TUBO / DN","PREVISTO (M)","LOCADO MEDIDO (M)","CADASTRO (M)","PENDENTE LOCAÇÃO (M)","% LOCADO","EXEC. MÊS MEDIDO (M)","EXEC. ACUM. MEDIDO (M)","% EXECUTADO"]]
    total=defaultdict(float)
    for de,v in d["word_por_de"].items():
        rows.append([f"PEAD DN {de}",RM.br(v["previsto"]),RM.br(v["locado"]),RM.br(v["cadastro"]),RM.br(max(0,v["previsto"]-v["locado"])),RM.pct(v["locado"]/v["previsto"]) if v["previsto"] else "—",RM.br(v["mes"]),RM.br(v["acumulado"]),RM.pct(v["acumulado"]/v["previsto"]) if v["previsto"] else "—"])
        for k in ("previsto","locado","cadastro","mes","acumulado"):total[k]+=v[k]
    t=total;den=t["previsto"]
    rows.append(["TOTAL",RM.br(den),RM.br(t["locado"]),RM.br(t["cadastro"]),RM.br(max(0,den-t["locado"])),RM.pct(t["locado"]/den) if den else "—",RM.br(t["mes"]),RM.br(t["acumulado"]),RM.pct(t["acumulado"]/den) if den else "—"])
    fl.tabela([.12]+[.11]*8,rows,total=True)
    fl.paragrafo([("Tabela 01 – "+("Execução acumulada" if execucao else "Locação topográfica com NS")+": locado e executado medidos conciliados com os lançamentos PROPOSTO do BM. As semanas mostram a produção física registrada, inclusive o que ainda não foi medido.",{"italico":True,"cor":"595959"})],tam=9,alin="C")
    if not execucao:fl.nova_pagina()  # a próxima tabela larga fica inteira na página em paisagem


def efetivo(d,fl,dias):
    if not d["word_efetivo"]:
        fl.paragrafo("PENDENTE: efetivo do dia sem presença registrada no check-in.")
        return
    fl.figura(fl.w,355,lambda dr,p,x,y,w,h:RM._grafico(dr,p,x,y,w,h,[RM.dbr(dt)[:5] for dt in dias],
        [("DIRETO",[d["word_efetivo"].get(dt,{}).get("DIRETO",0) for dt in dias],RM.AZUL),
         ("TERCEIRIZADO",[d["word_efetivo"].get(dt,{}).get("TERCEIRIZADO",0) for dt in dias],RM.LARANJA),
         ("EMPRESA PENDENTE",[d["word_efetivo"].get(dt,{}).get("NAO_INFORMADO",0) for dt in dias],"888888")],[],lambda v:RM.br(v,0),"EFETIVO DO DIA – CHECK-IN"),
        "Gráfico 01 – Efetivo direto e terceirizado por dia, pela empresa da equipe no check-in.")
    fl.paragrafo("PENDENTE: falta, atestado e abono não são registrados no check-in; ausência de presença não comprova falta.")


def colaboradores(d, fl):
    col = d["efetivo"]["colaboradores"]
    if not col:
        fl.paragrafo("PENDENTE: gráfico por colaborador sem presença registrada no check-in do período.")
    for inicio in range(0, len(col), 40):
        parte = col[inicio:inicio+40]
        fl.figura(fl.w, 160 if inicio == 0 else 355,
            lambda dr,p,x,y,w,h,parte=parte: RM._grafico(dr,p,x,y,w,h,[c for c,_ in parte],
                [("DIAS PRESENTES",[q for _,q in parte],RM.AZUL)],[],lambda v:RM.br(v,0),
                "DIAS PRESENTES POR COLABORADOR (INICIAIS-MATRÍCULA)"),
            f"Gráfico 01 – Dias presentes por colaborador (check-in). Parte {inicio//40+1}.")


def caminhamento(d,fl):
    rows=[["TRECHO / FRENTE / PRANCHA / DN","CAMINHAMENTO EM ESTACAS","REDE EXECUTADA (M)"]]
    for r in d["word_registros"]:
        if r["etapa"]!="ASSENTADO" or not d["ini"]<=r["data"]<=d["fim"]:continue
        t=d["trechos"].get(r["trecho_id"])
        if t:rows.append([t["ponto"],f"EST. {estaca(r['ini_m'])} ATÉ EST. {estaca(r['fim_m'])}",RM.br(r["fim_m"]-r["ini_m"])])
    if len(rows)==1:fl.paragrafo("Não houve rede executada no período.")
    else:fl.tabela([.42,.4,.18],rows)
    mes=sum(v["mes"] for v in d["por_de"].values());ac=sum(v["acumulado"] for v in d["por_de"].values())
    fl.paragrafo(f"REDE EXEC. MÊS: {RM.br(mes)} M / REDE EXEC. ACUMUL.: {RM.br(ac)} M",alin="C")
