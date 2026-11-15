"""Importação da planilha de locação e seus croquis como NS de topografia."""
import hashlib
import io
import json
import re
from itertools import groupby

import compras as C
import notas_servico as NS
import ns_leitura as L
import regras as R
import servicos as S
import topologia as TP
from servicos import RegraViolada, _agora, _one, transacao

A_CONFERIR = ("CONFIRMAR", "SEM_CORRESPONDENCIA", "ERRO")


def _nome(nome):
    nome = re.split(r"[/\\]", str(nome or ""))[-1].strip()
    if not nome or len(nome) > 255 or any(ord(c) < 32 for c in nome):
        raise RegraViolada("Informe o nome original do arquivo.")
    return nome


def _croquis(anexos):
    if not isinstance(anexos, list) or not 1 <= len(anexos) <= 19:
        raise RegraViolada("Envie de 1 a 19 croquis junto da planilha.")
    arquivos = {}
    for a in anexos:
        if not isinstance(a, dict):
            raise RegraViolada("Croqui inválido.")
        dados = NS._bytes(a.get("croqui_b64"), "o croqui", NS.LIMITE_CROQUI)
        if C._tipo_arquivo(dados)[0] not in ("pdf", "jpg", "png"):
            raise RegraViolada("O croqui precisa ser PDF, JPG ou PNG.")
        arquivos.setdefault(hashlib.sha256(dados).hexdigest(), (_nome(a.get("nome")), dados))
    return list(arquivos.values())


def _avisos_croquis(croquis, contrato):
    avisos, pranchas = [], {}
    for nome, dados in croquis:
        if not dados.startswith(b"%PDF-"):
            continue
        try:
            pdf = L._pypdf().PdfReader(io.BytesIO(dados))
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages[:L.LIMITE_PAGINAS])
        except Exception:  # a conferência do carimbo é só um aviso
            continue
        texto = L.sem_acento(texto).upper()
        for valor in re.findall(r'DO CONTRATO\s*:\s*(\d[\d.]*\s*/\s*\d{2,4})', texto):
            if L.norm_contrato(valor) != contrato:
                avisos.append(f'{nome}: o carimbo traz contrato {valor}. A obra é {contrato}.')
        # A posição do texto do AutoCAD pode variar. Só compara o carimbo quando há um número de prancha inequívoco.
        if 'DA PRANCHA' in texto:
            nums = set(re.findall(r'(?<![\d/])\d{1,2}/\d{1,2}(?![\d/])', texto))
            if len(nums) == 1:
                prancha = nums.pop()
                if prancha in pranchas:
                    avisos.append(f'{nome} e {pranchas[prancha]} trazem o mesmo número de prancha ({prancha}).')
                pranchas[prancha] = nome
    return avisos


def _estaca(m):
    i, f = divmod(m, L.ESTACA_M)
    return f"{int(i)}+{f:.3f}".rstrip("0").rstrip(".").replace(".", ",")


def _marcos(grupo, ind):
    pontos = []
    for m, rows in groupby(grupo["linhas"], key=lambda p: p["dist_acumulada"]):
        linhas = list(rows)
        chaves = {chave: p for p in linhas if (chave := NS.chave_rede(p["elemento"]))}
        if not chaves:
            # O nó sem sufixo só pode ser usado quando essa chave exata existe no cadastro da obra.
            for p in linhas:
                chave = (L.chave_elemento(p["elemento"]) or "").replace(" ", "")
                if re.fullmatch(r"NO\d+", chave) and chave in ind["chaves"]:
                    chaves[chave] = p
        chave = next(iter(chaves)) if len(chaves) == 1 else None
        linha = chaves.get(chave) or next((p for p in linhas if p["elemento"]), linhas[0])
        pontos.append(dict(linha, chave=chave, rotulo=f"{linha['elemento']} · {_estaca(m)}" if linha["elemento"] else _estaca(m)))
    return [p for i, p in enumerate(pontos) if i in (0, len(pontos) - 1) or p["chave"]]


def _casar(conn, ns, ctx):
    grupo = ns["grupos"][0]
    material = grupo["material"]
    ind = NS.indice(conn)
    marcos = _marcos(grupo, ind)
    segs = []
    for i, (a, b) in enumerate(zip(marcos, marcos[1:])):
        cands = [c for c in NS._vaos(ind, a["chave"], b["chave"], ctx)
                 if L.norm_txt(c["F"]["material"]) == L.norm_txt(material)]
        seg = NS._avaliar({"grupo": 0, "i": i, "j": i + 1, "ka": a["chave"], "kb": b["chave"],
                           "ctx": ctx, "cands": cands, "avisos": []}, marcos, ns)
        seg.update(ordem=i + 1, de=a["rotulo"], para=b["rotulo"])
        if not cands:
            seg["motivo"] = "Vincule esta faixa de estacas ao trecho da 06.1 usando o croqui."
        segs.append(seg)
    # Mesmo trecho físico repetido em faixas diferentes: deixe em conferência quando as faixas se sobrepõem.
    autos = [s for s in segs if s["situacao"] == "AUTOMATICO"]
    for i, s in enumerate(autos):
        c = s["escolhido"]
        for outro in autos[i + 1:]:
            d = outro["escolhido"]
            if c["fisico_id"] == d["fisico_id"] and R.sobreposicao((c["ini_m"], c["fim_m"]), [(d["ini_m"], d["fim_m"])]):
                for seg in (s, outro):
                    seg.update(situacao="CONFIRMAR", motivo="Mais de uma faixa da planilha coincide neste trecho físico.")
    return segs


def _gravar(conn, ns, sid, por):
    seg = _one(conn, "SELECT * FROM ns_segmentos WHERE id=?", sid)
    gravado, pendente, motivos = NS._aplicar_segmento(conn, ns, seg, por)
    NS._marcar(conn, sid, {"pendente_m": pendente, "pendencias": motivos})
    return gravado, pendente


def enviar(conn, planilha_b64, nome, croquis, por, zona=None, pb=None, hoje=None):
    nome = _nome(nome)
    dados = NS._bytes(planilha_b64, "a planilha de locação", L.LIMITE_PLANILHA)
    anexos = _croquis(croquis)
    try:
        ns = L.ler_locacao(dados, L.norm_contrato(S.contrato(conn)), hoje)
    except L.LeituraRecusada as e:
        raise RegraViolada(str(e)) from None
    ns["arquivo_locacao"] = nome
    z, p = NS._norm_zona_pb(zona, pb)
    ctx = {"zona": z, "pb": p}
    with transacao(conn):
        anterior = _one(conn, """SELECT * FROM notas_servico WHERE contrato=? AND tipo='TOPOGRAFIA'
                                 AND numero=? AND status='REGISTRADA'""", ns["cabecalho"]["contrato"], ns["cabecalho"]["numero"])
        if anterior:
            return {"id": anterior["id"], "referencia": anterior["arquivo_locacao"], "repetida": True}
        segs = _casar(conn, ns, ctx)
        ns["avisos_croqui"] = _avisos_croquis(anexos, ns["cabecalho"]["contrato"])
        planilha_id = NS._guardar(conn, "NS_PLANILHA", dados, nome, por)
        ns_id = NS._inserir_ns(conn, "TOPOGRAFIA", ns, ctx, None, None, planilha_id, por)
        for i, (arq, bytes_) in enumerate(anexos, 1):
            doc_id = NS._guardar(conn, "NS_CROQUI", bytes_, arq, por)
            conn.execute("INSERT INTO ns_locacao_croquis VALUES (?,?,?)", (ns_id, i, doc_id))
        nota = NS._ns(conn, ns_id)
        gravado, pendente, conferir = 0.0, 0.0, 0
        for s in segs:
            if s["situacao"] != "AUTOMATICO":
                conferir += 1
                s.update(pendente_m=s["metros_ns"], escolhido=None)
                pendente += s["metros_ns"]
            sid = NS._inserir_segmento(conn, ns_id, s, por)
            if s["situacao"] == "AUTOMATICO":
                g, p = _gravar(conn, nota, sid, por)
                gravado += g
                pendente += p
    return {"id": ns_id, "referencia": nome, "gravado_m": round(gravado, 3), "pendente_m": round(pendente, 3),
            "conferir": conferir, "total_m": ns["total_geral"], "avisos": ns["avisos"] + ns["avisos_croqui"]}


def opcoes(conn, nota):
    grupo = nota["leitura"]["grupos"][0]
    material = grupo["material"]
    return [{"id": f["id"], "extensao_m": f["extensao_m"], "linhas": [m["ponto"] for m in f["membros"]]}
            for f in TP.trechos_fisicos(conn)
            if f["de_mm"] == grupo["dn_mm"] and L.norm_txt(f["material"]) == L.norm_txt(material)]


def _vinculos(conn, nota, seg, selecao):
    if not isinstance(selecao, list) or not 1 <= len(selecao) <= 50:
        raise RegraViolada("Escolha ao menos um trecho físico e informe os intervalos.")
    fisicos = {f["id"]: f for f in TP.trechos_fisicos(conn)}
    material = json.loads(nota["leitura"])["grupos"][0]["material"]
    intervalos = {}
    for s in S._rows(conn.execute(f"""SELECT fisico_id,ini_fisico_m,fim_fisico_m FROM ns_segmentos
                                     WHERE ns_id=? AND situacao IN {NS.APLICADAS}""", (nota["id"],))):
        intervalos.setdefault(s["fisico_id"], []).append((s["ini_fisico_m"], s["fim_fisico_m"]))
    out = []
    for v in selecao:
        f = fisicos.get(str(v.get("fisico_id"))) if isinstance(v, dict) else None
        if not f or f["de_mm"] != seg["de_mm"] or L.norm_txt(f["material"]) != L.norm_txt(material):
            raise RegraViolada("Escolha um trecho vigente com diâmetro e material iguais aos da locação.")
        a, b = (L._numero_locacao(v.get(k)) for k in ("ini_m", "fim_m"))
        if a is None or b is None or a < 0 or b > f["extensao_m"] or b - a <= R.TOL_M:
            raise RegraViolada(f"Informe um intervalo válido de 0 a {NS._m(f['extensao_m'])} m em {f['id']}.")
        a, b = round(a, 3), round(b, 3)
        faixas = intervalos.setdefault(f["id"], [])
        if R.sobreposicao((a, b), faixas):
            raise RegraViolada(f"A faixa em {f['id']} coincide com outra já escolhida nesta planilha.")
        faixas.append((a, b))
        out.append((f, a, b))
    total = sum(b - a for _, a, b in out)
    if NS._nivel_diferenca(seg["metros_ns"], total) == "ERRO":
        raise RegraViolada(f"As faixas somam {NS._m(total)} m na 06.1 para {NS._m(seg['metros_ns'])} m na planilha. "
                           "Confira os trechos e as posições. A diferença máxima é de 5%.")
    return out


def vincular(conn, ns_id, segmento_id, selecao, por):
    """Resolve a identificação de uma faixa já enviada. A escolha e as liberações entram na mesma transação."""
    with transacao(conn):
        nota = NS._ns(conn, ns_id)
        seg = _one(conn, "SELECT * FROM ns_segmentos WHERE id=? AND ns_id=?", segmento_id, ns_id)
        if not nota["arquivo_locacao"] or nota["status"] != "REGISTRADA" or not seg:
            raise RegraViolada("Faixa de locação indisponível para vincular.")
        if seg["situacao"] not in A_CONFERIR:
            return {"id": ns_id, "gravado_m": 0, "pendente_m": seg["pendente_m"], "repetida": True}
        vinculos = _vinculos(conn, nota, seg, selecao)
        f, a, b = vinculos[0]
        conn.execute("""UPDATE ns_segmentos SET fisico_id=?,membros=?,sentido=1,extensao_fisico_m=?,ini_fisico_m=?,fim_fisico_m=?,
                        origem_sentido='ENGENHARIA',situacao='CONFIRMADO',motivo=NULL,confirmado_por=?,confirmado_em=?,
                        pendente_m=0,pendente=NULL WHERE id=?""",
                     (f["id"], json.dumps(f["membros"], ensure_ascii=False), f["extensao_m"], a, b, por, _agora(), seg["id"]))
        ids = [seg["id"]]
        if len(vinculos) > 1:
            ordem = conn.execute("SELECT MAX(ordem) FROM ns_segmentos WHERE ns_id=?", (ns_id,)).fetchone()[0]
            for i, (f, a, b) in enumerate(vinculos[1:], ordem + 1):
                parte = dict(ordem=i, grupo=seg["grupo"], de=seg["de"], para=seg["para"], de_mm=seg["de_mm"],
                             escolhido={"fisico_id": f["id"], "sentido": 1, "ini_m": a, "fim_m": b},
                             situacao="CONFIRMADO", origem_sentido="ENGENHARIA", confirmado_por=por,
                             motivo=f"Faixa complementar do segmento {seg['ordem']}.")
                ids.append(NS._inserir_segmento(conn, ns_id, parte, por))
        valores = [_gravar(conn, nota, sid, por) for sid in ids]
    return {"id": ns_id, "gravado_m": round(sum(g for g, _ in valores), 3), "pendente_m": round(sum(p for _, p in valores), 3)}
