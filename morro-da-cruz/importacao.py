"""Importação idempotente das planilhas oficiais para o esquema v2.

Princípios (etapa 1):
  * nada é apagado: registro que sai de uma revisão fica com vigente = 0;
  * identidade estável própria (TR-/EL-/AT-/IP-), casada por chave natural, nunca pelo nº da linha;
  * toda linha importada guarda proveniência (arquivo + SHA-256 + aba + linha + células);
  * reimportar os mesmos arquivos não altera nada (status SEM_ALTERACOES);
  * quantidade/unidade sem fonte ficam NULL (pendentes) — sem regra de descrição, sem equivalência UN↔PÇ;
  * avisos AA/AB/AW entram como texto de origem; decisões posteriores ficam em `decisoes` e não são tocadas;
  * ambiguidades vão para `pendencias_importacao`, nunca são resolvidas em silêncio.
"""
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime

import openpyxl
from openpyxl.utils import column_index_from_string as col
from openpyxl.utils import get_column_letter

import regras as R
import servicos as S
from backup import sha256

BASE = os.path.dirname(os.path.abspath(__file__))
DIR_PLANILHAS = os.path.join(BASE, "planilhas")

COLUNAS_SERVICO = ["AL", "AM", "AN", "AO", "AP", "AQ", "AR", "AS", "AT", "AU", "AV", "AW", "AX", "AY", "AZ",
                   "BA", "BB", "BC", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BK"]

# Cabeçalhos da aba CONEXÕES (06.2) localizados pelo nome; a letra encontrada vai para o relatório.
CAB_CONEXOES = {
    "descricao": "DESCRIÇÃO", "pressao": "PRESSÃO", "resina": "RESINA", "tipo_conexao": "TIPO_CONEXÃO",
    "solda": "SOLDA", "diametro": "DIÂMETRO", "material": "MATERIAL", "grupo": "GRUPO", "quantidade": "QUANT.",
    "nomenclatura": "NOMENCLATURA (OBRA)", "local": "LOCAL", "codigo_bm": "CÓDIGO BM",
    "consideracao": "CONSIDERAÇÃO", "sugestao": "SUGESTÃO DE CORREÇÃO", "equipe": "EQUIPE",
    "tipo_entroncamento": "TIPO ENTRONCAMENTO", "status_conexao": "STATUS CONEXÃO", "handle": "HANDLE CAD",
    "utm_e": "COORD. E (UTM)", "utm_n": "COORD. N (UTM)", "lat": "LATITUDE", "lon": "LONGITUDE",
    "prioridade": "PRIORIDADE DO ERRO", "enquadramento": "ENQUADRAMENTO BM", "obs_enquadramento": "OBS. ENQUADRAMENTO BM",
    "trechos": "TRECHO (06.1)",
}


def carregar_config():
    with open(os.path.join(BASE, "config", "fontes.json"), encoding="utf-8") as f:
        return json.load(f)


def caminho(cfg, chave, pasta=DIR_PLANILHAS):
    nome = cfg["arquivos"].get(chave)
    p = os.path.join(pasta, nome) if nome else None
    return p if p and os.path.exists(p) else None


def revisao_do_nome(nome):
    m = re.findall(r"REV\d+", nome.upper())
    return m[0] if m else None


def num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def txt(x):
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date().isoformat()
    s = str(x).strip()
    return s or None


def bruto(x):
    """Valor de célula serializável para a proveniência."""
    if isinstance(x, (datetime, date)):
        return x.isoformat()
    return x


def _hash_texto(t):
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


def numero_projeto(nomenclatura):
    """Zona01_PB01_CH_DF-33 -> DF-33."""
    return nomenclatura.split("_")[-1]


def tipo_elemento(numero):
    return "NÓ" if numero.upper().startswith(("NÓ", "NO")) else numero.split("-")[0].upper()


class Importador:
    def __init__(self, conn, cfg, importacao_id, pasta=DIR_PLANILHAS):
        self.c = conn
        self.cfg = cfg
        self.imp = importacao_id
        self.pasta = pasta
        self.stats = defaultdict(Counter)       # entidade -> {novos, alterados, iguais, retirados}
        self.fontes = {}
        self.colunas_06_2 = {}
        self.conferencias = {}

    # -------------------------------------------------------------- utilitários
    def fonte(self, chave, p):
        h = sha256(p)
        nome = os.path.basename(p)
        r = self.c.execute("SELECT id FROM fontes_arquivo WHERE chave=? AND sha256=?", (chave, h)).fetchone()
        if r:
            fid = r[0]
        else:
            fid = self.c.execute(
                "INSERT INTO fontes_arquivo(chave,nome,revisao,sha256,bytes,primeira_importacao_id) VALUES (?,?,?,?,?,?)",
                (chave, nome, revisao_do_nome(nome), h, os.path.getsize(p), self.imp)).lastrowid
        self.fontes[chave] = {"id": fid, "nome": nome, "sha256": h, "revisao": revisao_do_nome(nome)}
        return fid

    def prov(self, entidade, eid, fid, aba, linha, celulas):
        self.c.execute("INSERT OR REPLACE INTO proveniencia VALUES (?,?,?,?,?,?)",
                       (entidade, eid, fid, aba, linha, json.dumps(celulas, ensure_ascii=False, default=str)))

    def pendencia(self, tipo, ref, detalhe):
        self.c.execute("INSERT INTO pendencias_importacao(importacao_id,tipo,referencia,detalhe) VALUES (?,?,?,?)",
                       (self.imp, tipo, ref, detalhe))

    def nome_hist(self, entidade, eid, nome, fid):
        self.c.execute("INSERT OR IGNORE INTO nomes_historico VALUES (?,?,?,?,?)", (entidade, eid, nome, fid, S._agora()))

    def upsert(self, tabela, entidade, chave_where, campos):
        """Insere ou atualiza registrando cada campo alterado. chave_where: dict de colunas-chave."""
        where = " AND ".join(f"{k}=?" for k in chave_where)
        atual = self.c.execute(f"SELECT * FROM {tabela} WHERE {where}", tuple(chave_where.values())).fetchone()
        ident = str(next(iter(chave_where.values()))) if len(chave_where) == 1 else json.dumps(chave_where, ensure_ascii=False)
        if atual is None:
            dados = {**chave_where, **campos}
            self.c.execute(f"INSERT INTO {tabela}({','.join(dados)}) VALUES ({','.join('?' * len(dados))})",
                           tuple(dados.values()))
            self.c.execute("INSERT INTO alteracoes(importacao_id,entidade,entidade_id,campo,antes,depois) VALUES (?,?,?,?,?,?)",
                           (self.imp, entidade, ident, "(novo)", None, None))
            self.stats[entidade]["novos"] += 1
            return "novo"
        dif = {k: v for k, v in campos.items() if atual[k] != v}
        if not dif:
            self.stats[entidade]["iguais"] += 1
            return "igual"
        self.c.execute(f"UPDATE {tabela} SET {', '.join(f'{k}=?' for k in dif)} WHERE {where}",
                       (*dif.values(), *chave_where.values()))
        for k, v in dif.items():
            self.c.execute("INSERT INTO alteracoes(importacao_id,entidade,entidade_id,campo,antes,depois) VALUES (?,?,?,?,?,?)",
                           (self.imp, entidade, ident, k, None if atual[k] is None else str(atual[k]),
                            None if v is None else str(v)))
        self.stats[entidade]["alterados"] += 1
        return "alterado"

    def retirar_nao_vistos(self, tabela, entidade, vistos, filtro="1=1", args=()):
        for (eid,) in self.c.execute(f"SELECT id FROM {tabela} WHERE vigente=1 AND {filtro}", args).fetchall():
            if eid not in vistos:
                self.c.execute(f"UPDATE {tabela} SET vigente=0 WHERE id=?", (eid,))
                self.c.execute("INSERT INTO alteracoes(importacao_id,entidade,entidade_id,campo,antes,depois) VALUES (?,?,?,?,?,?)",
                               (self.imp, entidade, str(eid), "vigente", "1", "0"))
                self.stats[entidade]["retirados"] += 1

    def novo_id(self, prefixo, tabela, largura):
        r = self.c.execute(f"SELECT MAX(CAST(SUBSTR(id, {len(prefixo) + 1}) AS INTEGER)) FROM {tabela} WHERE id LIKE ?",
                           (prefixo + "%",)).fetchone()[0]
        return f"{prefixo}{(r or 0) + 1:0{largura}d}"

    def parametro(self, chave, valor, fonte, sobrescrever=True):
        sql = "INSERT OR REPLACE" if sobrescrever else "INSERT OR IGNORE"
        atual = S.parametro(self.c, chave)
        self.c.execute(f"{sql} INTO parametros(chave,valor,fonte) VALUES (?,?,?)", (chave, str(valor), fonte))
        if sobrescrever and atual is not None and atual != str(valor):
            self.c.execute("INSERT INTO alteracoes(importacao_id,entidade,entidade_id,campo,antes,depois) VALUES (?,?,?,?,?,?)",
                           (self.imp, "parametro", chave, "valor", atual, str(valor)))

    # -------------------------------------------------------------- cargas
    def equipes(self):
        nomes = {f"Zona{n:02d}": f"EQUIPE ZONA {n:02d}" for n in range(1, 12)}
        nomes.update({"ADUTORA": "EQUIPE ADUTORA", "CH": "EQUIPE CH — CAIXAS HIDRÁULICAS"})
        for eid in R.FRENTES:
            self.c.execute("INSERT OR IGNORE INTO equipes(id, nome) VALUES (?,?)", (eid, nomes[eid]))

    def bm(self, p):
        fid = self.fonte("bm", p)
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        nomes_atr = ["descricao_resumida", "pressao", "resina", "tipo_conexao", "solda", "diametro", "material", "grupo",
                     "grupo_orcamento_ankara"]
        for planilha, aba, ini_atr in (("JUNTADA", "BM MORRO DA CRUZ", 1), ("VERTICAL", "BM MORRO DA CRUZ - VERTICAL", 5)):
            vistos = set()
            for k, row in enumerate(wb[aba].iter_rows(min_row=6, values_only=True), 6):
                if planilha == "JUNTADA":
                    if not (row[0] and row[1]):
                        continue
                    item = str(row[0])
                    campos = dict(item_bm=item, subgrupo=None, subgrupo_nome=None, codigo_caesb=txt(row[10]),
                                  classificacao=txt(row[11]), descricao=row[12], unidade=txt(row[13]),
                                  quantidade=num(row[14]), preco_unitario=num(row[15]), valor_total=num(row[16]))
                else:
                    if not row[3]:
                        continue
                    item = str(row[3])
                    campos = dict(item_bm=str(row[4]), subgrupo=txt(row[1]), subgrupo_nome=txt(row[2]),
                                  codigo_caesb=txt(row[14]), classificacao=txt(row[15]), descricao=row[16],
                                  unidade=txt(row[17]), quantidade=num(row[18]), preco_unitario=num(row[19]),
                                  valor_total=num(row[20]))
                campos["atributos"] = json.dumps(dict(zip(nomes_atr, row[ini_atr:ini_atr + 9])), ensure_ascii=False, default=str)
                campos["linha_origem"] = k
                campos["vigente"] = 1
                self.upsert("bm_itens", "bm_item", {"planilha": planilha, "item": item}, campos)
                bid = self.c.execute("SELECT id FROM bm_itens WHERE planilha=? AND item=?", (planilha, item)).fetchone()[0]
                vistos.add(bid)
                self.prov("bm_item", str(bid), fid, aba, k, {"item": item, "quantidade": bruto(campos["quantidade"]),
                                                             "preco": bruto(campos["preco_unitario"])})
            self.retirar_nao_vistos("bm_itens", "bm_item", vistos, "planilha=?", (planilha,))
        # rodapé da Vertical: BDI, K, totais por classe e P0
        rod, no_rodape = {}, False
        for row in wb["BM MORRO DA CRUZ - VERTICAL"].iter_rows(min_row=6, values_only=True):
            no_rodape = no_rodape or any(str(x).strip() == "RESUMO PRINCIPAL" for x in row if x is not None)
            if not no_rodape:
                continue
            cel = [x for x in row if x not in (None, "")]
            rots = [i for i, x in enumerate(cel) if isinstance(x, str)]
            if not rots:
                continue
            rot = str(cel[rots[-1]]).strip()
            vals = [x for x in cel[rots[-1] + 1:] if isinstance(x, (int, float))]
            if not vals:
                continue
            chave = {"MATERIAL": "bm_total_material", "SERVIÇO": "bm_total_servico", "BDI MATERIAL =>": "bdi_material",
                     "BDI SERVIÇO =>": "bdi_servico", "COEF. - K =>": "coef_k", "TOTAL 01 + 02 + BDI -K": "p0_bm"}.get(rot)
            if chave and chave not in rod:
                rod[chave] = vals[0]
        fonte_rod = f"{os.path.basename(p)} · BM VERTICAL, rodapé"
        for k, v in rod.items():
            self.parametro(k, v, fonte_rod)
        return rod

    def reajuste(self, p):
        self.fonte("reajuste", p)
        ws = openpyxl.load_workbook(p, read_only=True, data_only=True)["REAJUSTE"]
        achados = {}
        for row in ws.iter_rows(values_only=True):
            rot = str(row[0] or "")
            vals = [x for x in row[1:] if x is not None]
            if not vals:
                continue
            if rot.startswith("Data-base do reajuste"):
                achados["data_base"] = vals[0]
            elif rot.startswith("Percentual do 1º reajuste"):
                achados["indice"] = vals[0]
            elif rot.startswith("1º aniversário"):
                achados["aniversario"] = vals[0]
            elif rot.startswith("Início da execução"):
                achados["inicio_os"] = vals[0]
        for k in ("data_base", "indice", "aniversario"):
            if k not in achados:
                raise RuntimeError(f"REAJUSTE: '{k}' não encontrado na aba.")
        aniv = achados["aniversario"].date() if isinstance(achados["aniversario"], datetime) else achados["aniversario"]
        fim = date.fromordinal(date(aniv.year + 1, aniv.month, aniv.day).toordinal() - 1)
        self.c.execute("INSERT OR REPLACE INTO reajuste_indices VALUES (?,?,?,?)",
                       (aniv.isoformat(), fim.isoformat(), float(achados["indice"]),
                        "1º reajuste — Despacho 322/2026-CEFR; frações elegíveis e pedido da contratada pendentes"))
        for k, v in achados.items():
            self.parametro(f"reajuste_{k}", v.date().isoformat() if isinstance(v, datetime) else v,
                           f"{os.path.basename(p)} · aba REAJUSTE")
        return achados

    def trechos(self, p):
        fid = self.fonte("redes", p)
        ws = openpyxl.load_workbook(p, read_only=True, data_only=True)["REDE"]
        existentes = [dict(r) for r in self.c.execute("SELECT id, ponto, handle, utm_ini, utm_fim FROM trechos")]
        por_ponto = {r["ponto"]: r["id"] for r in existentes}
        por_geom = defaultdict(list)
        for r in existentes:
            por_geom[(r["handle"], r["utm_ini"], r["utm_fim"])].append(r["id"])
        vistos, pontos_vistos = set(), set()
        v = lambda row, l: row[col(l) - 1] if col(l) - 1 < len(row) else None
        for k, row in enumerate(ws.iter_rows(min_row=6, values_only=True), 6):
            ponto = txt(v(row, "R"))
            if not ponto:
                continue
            if ponto in pontos_vistos:
                self.pendencia("TRECHO_DUPLICADO", ponto, f"PONTO repetido na linha {k} da aba REDE — linha ignorada")
                continue
            pontos_vistos.add(ponto)
            e1, n1, e2, n2 = (num(v(row, c)) for c in ("BS", "BT", "BU", "BV"))
            utm_ini = json.dumps([e1, n1]) if e1 else None
            utm_fim = json.dumps([e2, n2]) if e2 else None
            handle = txt(v(row, "BR"))
            tid = por_ponto.get(ponto)
            if tid is None:
                cands = por_geom.get((handle, utm_ini, utm_fim), [])
                if len(cands) == 1 and cands[0] not in vistos:
                    tid = cands[0]       # mesmo trecho com outro nome nesta revisão
                elif len(cands) > 1:
                    self.pendencia("TRECHO_AMBIGUO", ponto, f"geometria igual a {cands}; criado novo ID")
            if tid is None:
                tid = self.novo_id("TR-", "trechos", 5)
            pend = R.PERFIL_PENDENTE if any(str(v(row, c) or "").strip().upper() == R.PERFIL_PENDENTE
                                             for c in ("AE", "AF", "AG", "AH")) else None
            campos = dict(
                ponto=ponto, vigente=1, item=v(row, "A"), frente_id=txt(v(row, "K")), equipe=txt(v(row, "BM")),
                tipo=txt(v(row, "BN")), pb=txt(v(row, "BO")), prancha=txt(v(row, "U")), area=txt(v(row, "X")),
                de_mm=num(v(row, "H")), material=txt(v(row, "I")), solda=txt(v(row, "G")), metodologia=txt(v(row, "N")),
                classe=txt(v(row, "S")), extensao_m=num(v(row, "M")), codigo_bm=txt(v(row, "AC")),
                recobrimento_m=num(v(row, "AE")), profundidade_m=num(v(row, "AF")), largura_m=num(v(row, "AG")),
                lastro_m=num(v(row, "AH")), perfil_status=pend,
                quantidades=json.dumps({c: num(v(row, c)) for c in COLUNAS_SERVICO if num(v(row, c)) is not None}),
                no_ini=txt(v(row, "BP")), no_fim=txt(v(row, "BQ")), handle=handle, utm_ini=utm_ini, utm_fim=utm_fim,
                lat=num(v(row, "BW")), lon=num(v(row, "BX")), observacao=txt(v(row, "AB")))
            self.upsert("trechos", "trecho", {"id": tid}, campos)
            self.nome_hist("trecho", tid, ponto, fid)
            self.prov("trecho", tid, fid, "REDE", k, {c: bruto(v(row, c)) for c in
                                                      ("R", "K", "H", "M", "N", "AC", "AE", "AF", "AG", "AH", "BR", "BP", "BQ")})
            vistos.add(tid)
        self.retirar_nao_vistos("trechos", "trecho", vistos)

    def conexoes(self, p, evidencias=None):
        fid = self.fonte("conexoes", p)
        ws = openpyxl.load_workbook(p, read_only=True, data_only=True)["CONEXÕES"]
        cab_linha, idx = None, {}
        for i, row in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), 1):
            nomes = [str(c or "").strip().upper() for c in row]
            if CAB_CONEXOES["nomenclatura"] in nomes:
                cab_linha = i
                for campo, rotulo in CAB_CONEXOES.items():
                    if rotulo in nomes:
                        idx[campo] = nomes.index(rotulo)
                break
        faltando = [CAB_CONEXOES[c] for c in CAB_CONEXOES if c not in idx]
        if cab_linha is None or faltando:
            raise RuntimeError(f"06.2: cabeçalhos não encontrados: {faltando or 'linha de cabeçalho'}")
        self.colunas_06_2 = {c: get_column_letter(j + 1) for c, j in idx.items()}
        juntada = {r[0]: r[1] for r in self.c.execute("SELECT item, unidade FROM bm_itens WHERE planilha='JUNTADA' AND vigente=1")}

        linhas = []
        for k, row in enumerate(ws.iter_rows(min_row=cab_linha + 1, values_only=True), cab_linha + 1):
            g = lambda campo: row[idx[campo]] if idx[campo] < len(row) else None
            if txt(g("nomenclatura")):
                linhas.append((k, {c: g(c) for c in idx}))

        # elemento físico: handle CAD; sem handle, o número do projeto
        grupos = defaultdict(list)
        for k, r in linhas:
            nom = txt(r["nomenclatura"])
            chave = f"H:{txt(r['handle'])}" if txt(r["handle"]) else f"N:{numero_projeto(nom)}"
            grupos[chave].append((k, r))
        nom_chave = defaultdict(set)
        for chave, rs in grupos.items():
            for _, r in rs:
                nom_chave[txt(r["nomenclatura"])].add(chave)
        for nom, ch in nom_chave.items():
            if len(ch) > 1:
                self.pendencia("NOMENCLATURA_EM_MAIS_DE_UM_ELEMENTO", nom, f"chaves {sorted(ch)}")

        ev = self._evidencias(evidencias) if evidencias else {}
        if ev:
            meus = {frozenset(txt(r["nomenclatura"]) for _, r in rs) for rs in grupos.values()}
            iguais = sum(1 for g_ in ev if g_ in meus)
            self.conferencias["agrupamento_vs_evidencias"] = {"evidencias": len(ev), "iguais": iguais}
            for g_ in ev:
                if g_ not in meus:
                    self.pendencia("AGRUPAMENTO_DIVERGE_EVIDENCIAS", " | ".join(sorted(g_)), "grupo das EVIDÊNCIAS sem par na 06.2")

        el_existentes = {r[0]: r[1] for r in self.c.execute("SELECT chave_natural, id FROM elementos")}
        at_existentes = {(r[0], r[1]): r[2] for r in self.c.execute("SELECT elemento_id, tipo_frente, id FROM atividades")}
        ip_existentes = {(r[0], r[1]): r[2] for r in self.c.execute("SELECT atividade_id, chave_ocorrencia, id FROM itens_projeto")}
        el_vistos, at_vistos, ip_vistos, av_vistos = set(), set(), set(), set()

        for chave, rs in grupos.items():
            noms = sorted({txt(r["nomenclatura"]) for _, r in rs})
            numero = numero_projeto(noms[0])
            coords = {(num(r["utm_e"]), num(r["utm_n"]), num(r["lat"]), num(r["lon"])) for _, r in rs}
            if len(coords) > 1:
                self.pendencia("COORDENADAS_DIVERGENTES", numero, f"{len(coords)} coordenadas distintas no mesmo elemento")
            ue, un, la, lo = sorted(coords, key=lambda x: tuple(v is None for v in x))[0]
            info_ev = ev.get(frozenset(noms), {})
            eid = el_existentes.get(chave) or self.novo_id("EL-", "elementos", 4)
            el_existentes[chave] = eid
            self.upsert("elementos", "elemento", {"id": eid}, dict(
                chave_natural=chave, numero=numero, tipo=tipo_elemento(numero), vigente=1,
                handle=txt(rs[0][1]["handle"]), pb=noms[0].split("_")[1] if noms[0].count("_") >= 3 else None,
                zona=info_ev.get("zona"), utm_e=ue, utm_n=un, lat=la, lon=lo,
                status_posicao=info_ev.get("status"), id_auditoria=info_ev.get("id")))
            self.prov("elemento", eid, fid, "CONEXÕES", rs[0][0], {"handle": txt(rs[0][1]["handle"]), "nomenclaturas": noms})
            el_vistos.add(eid)

            por_frente = defaultdict(list)
            for k, r in rs:
                nom = txt(r["nomenclatura"])
                por_frente[nom.split("_")[2] if nom.count("_") >= 3 else "?"].append((k, r))
            for tipo_frente, linhas_at in por_frente.items():
                noms_at = sorted({txt(r["nomenclatura"]) for _, r in linhas_at})
                if len(noms_at) > 1:
                    self.pendencia("ATIVIDADE_COM_VARIAS_NOMENCLATURAS", numero, " | ".join(noms_at))
                nom = noms_at[0]
                aid = at_existentes.get((eid, tipo_frente)) or self.novo_id("AT-", "atividades", 4)
                at_existentes[(eid, tipo_frente)] = aid
                k0, r0 = linhas_at[0]
                self.upsert("atividades", "atividade", {"id": aid}, dict(
                    elemento_id=eid, tipo_frente=tipo_frente, nomenclatura=nom, frente_id=txt(r0["local"]),
                    equipe=txt(r0["equipe"]), vigente=1))
                self.nome_hist("atividade", aid, nom, fid)
                self.prov("atividade", aid, fid, "CONEXÕES", k0, {"nomenclatura": nom, "local": txt(r0["local"])})
                at_vistos.add(aid)

                ocorr = Counter()
                for k, r in linhas_at:
                    descr = txt(r["descricao"]) or "(sem descrição)"
                    diam, pressao = txt(r["diametro"]), txt(r["pressao"])
                    ocorr[(descr, diam, pressao)] += 1
                    chave_oc = f"{descr}|{diam}|{pressao}|{ocorr[(descr, diam, pressao)]}"
                    iid = ip_existentes.get((aid, chave_oc)) or self.novo_id("IP-", "itens_projeto", 6)
                    ip_existentes[(aid, chave_oc)] = iid
                    codigo = txt(r["codigo_bm"])
                    if codigo in juntada and juntada[codigo]:
                        unidade, fonte_un = R.normalizar_unidade(juntada[codigo]), f"BM Juntada {codigo}"
                    else:
                        unidade, fonte_un = None, f"PENDENTE: código '{codigo}' sem item/unidade na Juntada"
                    self.upsert("itens_projeto", "item_projeto", {"id": iid}, dict(
                        atividade_id=aid, chave_ocorrencia=chave_oc, vigente=1, descricao=descr, pressao=pressao,
                        resina=txt(r["resina"]), tipo_conexao=txt(r["tipo_conexao"]), solda=txt(r["solda"]), diametro=diam,
                        material=txt(r["material"]), grupo=txt(r["grupo"]), quantidade=num(r["quantidade"]),
                        unidade=unidade, unidade_fonte=fonte_un, codigo_bm=codigo,
                        enquadramento_bm=txt(r["enquadramento"]), obs_enquadramento_bm=txt(r["obs_enquadramento"]),
                        trechos=txt(r["trechos"]), tipo_entroncamento=txt(r["tipo_entroncamento"]),
                        status_conexao=txt(r["status_conexao"])))
                    self.prov("item_projeto", iid, fid, "CONEXÕES", k,
                              {self.colunas_06_2[c]: bruto(v) for c, v in r.items()})
                    ip_vistos.add(iid)
                    for tipo, campo in (("PROBLEMA", "consideracao"), ("SUGESTAO", "sugestao")):
                        for texto in [t.strip() for t in str(r[campo] or "").split(" | ") if t.strip()]:
                            h = _hash_texto(texto)
                            res = self.upsert("avisos_origem", "aviso", {"item_id": iid, "tipo": tipo, "texto_hash": h},
                                              dict(prioridade=txt(r["prioridade"]), texto=texto, vigente=1))
                            avid = self.c.execute("SELECT id FROM avisos_origem WHERE item_id=? AND tipo=? AND texto_hash=?",
                                                  (iid, tipo, h)).fetchone()[0]
                            av_vistos.add(avid)
                            if res == "novo":
                                self.prov("aviso", str(avid), fid, "CONEXÕES", k, {self.colunas_06_2[campo]: texto})

        self.retirar_nao_vistos("itens_projeto", "item_projeto", ip_vistos)
        self.retirar_nao_vistos("atividades", "atividade", at_vistos)
        self.retirar_nao_vistos("elementos", "elemento", el_vistos)
        self.retirar_nao_vistos("avisos_origem", "aviso", av_vistos)

    def _evidencias(self, p):
        """EVIDÊNCIAS REV08 (aba ELEMENTOS_ZONA): conferência do agrupamento + zona, status e ID da auditoria."""
        self.fonte("evidencias", p)
        out = {}
        ws = openpyxl.load_workbook(p, read_only=True, data_only=True)["ELEMENTOS_ZONA"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0]:
                g_ = frozenset(s.strip() for s in str(row[1]).split("|") if s.strip())
                out[g_] = {"id": txt(row[0]), "zona": txt(row[5]), "status": txt(row[8])}
        return out

    def materiais(self):
        """Tubos PEAD da rede (fornecimento Caesb, SL0327 §6) por DE; itens MATERIAL do BM (aquisição Ankara);
        consumo diário. Nunca apaga material (há movimentos ligados)."""
        for r in self.c.execute("SELECT de_mm, SUM(extensao_m) ext FROM trechos WHERE vigente=1 GROUP BY de_mm ORDER BY de_mm").fetchall():
            de = int(r["de_mm"])
            self.upsert("materiais", "material", {"id": f"CAESB-PEAD-DE{de}"}, dict(
                descricao=f"TUBO PEAD DE{de} PN10 — fornecimento Caesb", unidade="M", propriedade="CAESB",
                preco_unitario=0, qtd_projeto=round(r["ext"], 2)))
        for b in self.c.execute("SELECT * FROM bm_itens WHERE planilha='VERTICAL' AND classificacao='MATERIAL' AND vigente=1").fetchall():
            self.upsert("materiais", "material", {"id": b["item"]}, dict(
                descricao=b["descricao"], unidade=b["unidade"] or "UN", propriedade="ANKARA",
                preco_unitario=b["preco_unitario"] or 0, bm_item_id=b["id"], qtd_projeto=b["quantidade"]))
        for m in self.cfg["materiais_consumo"]:
            self.c.execute("INSERT OR IGNORE INTO materiais(id,descricao,unidade,propriedade) VALUES (?,?,?,'CONSUMO')",
                           (m["id"], m["descricao"], m["unidade"]))

    def decisoes(self):
        p = os.path.join(BASE, "config", "decisoes.json")
        if not os.path.exists(p):
            return 0
        with open(p, encoding="utf-8") as f:
            lista = json.load(f)["decisoes"]
        n = 0
        for d in lista:   # INSERT OR IGNORE: a importação nunca altera uma decisão já registrada
            n += self.c.execute(
                """INSERT OR IGNORE INTO decisoes(id,assunto,objeto_tipo,objeto_ref,status,decisao,responsavel,evidencia,data,
                     padrao_aviso,registrada_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (d["id"], d["assunto"], d.get("objeto_tipo"), d.get("objeto_ref"), d["status"], d["decisao"],
                 d.get("responsavel"), d["evidencia"], d.get("data"), d.get("padrao_aviso"), S._agora())).rowcount
        return n

    # -------------------------------------------------------------- execução
    def executar(self):
        cfg = self.cfg
        obrig = {k: caminho(cfg, k, self.pasta) for k in ("redes", "conexoes", "bm", "reajuste")}
        faltam = [cfg["arquivos"][k] for k, v in obrig.items() if not v]
        if faltam:
            raise RuntimeError("Faltam planilhas obrigatórias em planilhas/: " + ", ".join(faltam))
        self.parametro("contrato", cfg["contrato"], "config/fontes.json")
        vc = cfg["valor_contrato"]
        self.parametro("valor_contrato", vc["valor"], vc["fonte"])
        self.parametro("medicao_oficial_liberada", "NAO", "trava das etapas 0/1 (alterar só após validação)", sobrescrever=False)
        self.equipes()
        self.bm(obrig["bm"])
        self.reajuste(obrig["reajuste"])
        self.trechos(obrig["redes"])
        self.conexoes(obrig["conexoes"], caminho(cfg, "evidencias", self.pasta))
        self.materiais()
        self.decisoes_novas = self.decisoes()


# ------------------------------------------------------------------ migração do esquema v1 (MVP) para v2
TABELAS_V1_RENOMEAR = ["trechos", "elementos", "conjuntos", "pecas", "medicoes", "medicao_lancamentos", "parametros"]


def preparar_v1(conn):
    """Renomeia as tabelas v1 de estrutura incompatível para v1_* (preservadas para auditoria) e cria o esquema v2.

    Deve rodar com foreign_keys=OFF e legacy_alter_table=ON (as referências das tabelas operacionais
    continuam apontando para os nomes trechos/medicoes, que passam a ser as tabelas v2).
    """
    for t in TABELAS_V1_RENOMEAR:
        conn.execute(f'ALTER TABLE "{t}" RENAME TO "v1_{t}"')
    for ix in ("ix_pecas_conj", "ix_conj_elem", "ix_lanc_med"):
        conn.execute(f"DROP INDEX IF EXISTS {ix}")
    cols_bm = {r[1] for r in conn.execute("PRAGMA table_info(bm_itens)")}
    if "vigente" not in cols_bm:
        conn.execute("ALTER TABLE bm_itens ADD COLUMN vigente INTEGER NOT NULL DEFAULT 1")
    S.aplicar_esquema(conn)
    conn.execute("INSERT OR IGNORE INTO parametros(chave,valor,fonte) SELECT chave, valor, 'migrado do esquema v1' "
                 "FROM v1_parametros WHERE chave NOT IN ('p0')")
    conn.execute("INSERT INTO medicoes(id,numero,tipo,periodo_ini,periodo_fim,status) "
                 "SELECT id, numero, 'TESTE', periodo_ini, periodo_fim, status FROM v1_medicoes")
    conn.execute(
        """INSERT INTO medicao_lancamentos(id,medicao_id,gaveta,servico,bm_item_id,alvo_tipo,alvo_id,nf_id,material_id,
             unidade,quantidade,status,motivo,observacao)
           SELECT id, medicao_id, gaveta, servico, bm_item_id, alvo_tipo, alvo_id, nf_id, material_id, unidade, quantidade,
             CASE WHEN servico LIKE 'MATERIAL%' OR bm_item_id IS NULL THEN 'PENDENTE' ELSE 'PROPOSTO' END,
             CASE WHEN servico LIKE 'MATERIAL%' THEN 'regime de faturamento pendente (matriz de regimes não aprovada)'
                  WHEN bm_item_id IS NULL THEN 'sem item de BM com fonte' END,
             observacao
           FROM v1_medicao_lancamentos""")


REFS_ALVO = ["movimentos", "checkins", "apontamentos", "fotos", "execucao", "medicao_lancamentos"]
REFS_TRECHO = [("cadastro", "trecho_id"), ("cadastro_historico", "trecho_id"), ("ligacoes_prediais", "trecho_id")]


def remapear_v1(conn, imp):
    """Troca as referências antigas (PONTO / nomenclatura) pelas identidades estáveis. Nada é apagado;
    referência sem correspondência fica com o valor antigo e vira pendência."""
    agora = S._agora()
    tr = {r[0]: r[1] for r in conn.execute("SELECT ponto, id FROM trechos")}
    at = {r[0]: r[1] for r in conn.execute("SELECT nomenclatura, id FROM atividades")}
    resumo = Counter()
    for tabela in REFS_ALVO:
        for tipo, antigo in conn.execute(f"SELECT DISTINCT alvo_tipo, alvo_id FROM {tabela} WHERE alvo_id IS NOT NULL").fetchall():
            if tipo == "TRECHO":
                novo_tipo, novo = "TRECHO", tr.get(antigo)
            elif tipo in ("CONJUNTO", "ELEMENTO"):
                novo_tipo, novo = "ATIVIDADE", at.get(antigo)
            else:
                continue
            conn.execute("INSERT OR REPLACE INTO migracao_mapa VALUES (?,?,?,?,?)",
                         (tabela, "alvo", f"{tipo}:{antigo}", f"{novo_tipo}:{novo}" if novo else None, agora))
            if novo:
                conn.execute(f"UPDATE {tabela} SET alvo_tipo=?, alvo_id=? WHERE alvo_tipo=? AND alvo_id=?",
                             (novo_tipo, novo, tipo, antigo))
                resumo[f"{tabela}:mapeados"] += 1
            else:
                conn.execute("INSERT INTO pendencias_importacao(importacao_id,tipo,referencia,detalhe) VALUES (?,?,?,?)",
                             (imp, "REFERENCIA_V1_SEM_PAR", f"{tabela}:{tipo}:{antigo}", "valor antigo preservado"))
                resumo[f"{tabela}:sem_par"] += 1
    for tabela, coluna in REFS_TRECHO:
        for (antigo,) in conn.execute(f"SELECT DISTINCT {coluna} FROM {tabela}").fetchall():
            novo = tr.get(antigo)
            conn.execute("INSERT OR REPLACE INTO migracao_mapa VALUES (?,?,?,?,?)", (tabela, coluna, antigo, novo, agora))
            if novo:
                conn.execute(f"UPDATE {tabela} SET {coluna}=? WHERE {coluna}=?", (novo, antigo))
                resumo[f"{tabela}:mapeados"] += 1
            else:
                conn.execute("INSERT INTO pendencias_importacao(importacao_id,tipo,referencia,detalhe) VALUES (?,?,?,?)",
                             (imp, "REFERENCIA_V1_SEM_PAR", f"{tabela}.{coluna}:{antigo}", "valor antigo preservado"))
                resumo[f"{tabela}:sem_par"] += 1
    return dict(resumo)


# ------------------------------------------------------------------ auditoria pós-carga
def auditar(conn, cfg, imp):
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    esperado = cfg["auditoria"]
    obtido = {
        "trechos": q("SELECT COUNT(*) FROM trechos WHERE vigente=1"),
        "extensao_m": round(q("SELECT SUM(extensao_m) FROM trechos WHERE vigente=1") or 0, 2),
        "elementos": q("SELECT COUNT(*) FROM elementos WHERE vigente=1"),
        "nos": q("SELECT COUNT(*) FROM elementos WHERE vigente=1 AND tipo='NÓ'"),
        "caixas": q("SELECT COUNT(*) FROM elementos WHERE vigente=1 AND tipo<>'NÓ'"),
        "conjuntos": q("SELECT COUNT(*) FROM atividades WHERE vigente=1"),
        "pecas": q("SELECT COUNT(*) FROM itens_projeto WHERE vigente=1"),
        "bm_vertical": q("SELECT COUNT(*) FROM bm_itens WHERE planilha='VERTICAL' AND vigente=1"),
        "bm_juntada": q("SELECT COUNT(*) FROM bm_itens WHERE planilha='JUNTADA' AND vigente=1"),
        "sem_posicao": sorted(r[0] for r in conn.execute("SELECT numero FROM elementos WHERE vigente=1 AND lat IS NULL")),
    }
    contagens = {k: {"esperado": v, "obtido": obtido[k], "ok": obtido[k] == v} for k, v in esperado.items() if k in obtido}

    # BM: a totalização do sistema reproduz o rodapé da Vertical (mesma ordem de arredondamento)?
    bdi_m, bdi_s, k = (float(S.parametro(conn, x, 0)) for x in ("bdi_material", "bdi_servico", "coef_k"))
    itens = [(r[0], r[1] or 0, r[2] or 0) for r in conn.execute(
        "SELECT classificacao, quantidade, preco_unitario FROM bm_itens WHERE planilha='VERTICAL' AND vigente=1")]
    tot = R.totalizar_bm(itens, bdi_m, bdi_s, k, modo="contrato")
    ref = {x: float(S.parametro(conn, x, "nan")) for x in ("bm_total_material", "bm_total_servico", "p0_bm")}
    bm_ok = (abs(tot["material"] - ref["bm_total_material"]) < 0.005 and abs(tot["servico"] - ref["bm_total_servico"]) < 0.005
             and abs(tot["total_exato"] - ref["p0_bm"]) < 1e-4)
    totalizacao = {"sistema": {"material": tot["material"], "servico": tot["servico"], "p0": tot["total_exato"]},
                   "celulas_bm": ref, "ok": bm_ok}

    vc = float(S.parametro(conn, "valor_contrato"))
    p0 = ref["p0_bm"]
    total_contratual = {"contrato_3_1": vc, "fonte_contrato": cfg["valor_contrato"]["fonte"], "bm_p0": p0,
                        "diferenca": round(p0 - vc, 7),
                        "situacao": "DIVERGÊNCIA REGISTRADA — conciliar (não ajustado)" if abs(p0 - vc) > 0.004 else "IGUAL"}

    unidades = {r[0] or "PENDENTE": {"linhas": r[1], "quantidade": round(r[2] or 0, 4)} for r in conn.execute(
        "SELECT unidade, COUNT(*), SUM(quantidade) FROM itens_projeto WHERE vigente=1 GROUP BY unidade ORDER BY unidade")}
    pend_q = q("SELECT COUNT(*) FROM itens_projeto WHERE vigente=1 AND quantidade IS NULL")
    enquad = {r[0] or "(vazio)": r[1] for r in conn.execute(
        "SELECT enquadramento_bm, COUNT(*) FROM itens_projeto WHERE vigente=1 GROUP BY 1 ORDER BY 2 DESC")}
    avisos = {f"{r[0]}/{r[1] or 'sem prioridade'}": r[2] for r in conn.execute(
        "SELECT tipo, prioridade, COUNT(*) FROM avisos_origem WHERE vigente=1 GROUP BY 1,2 ORDER BY 1,2")}
    servs = json.load(open(os.path.join(BASE, "config", "servicos_rede.json"), encoding="utf-8"))["gaveta1"]
    pendencias = {r[0]: r[1] for r in conn.execute(
        "SELECT tipo, COUNT(*) FROM pendencias_importacao WHERE importacao_id=? GROUP BY 1", (imp,))}
    return {
        "contagens": contagens,
        "contagens_ok": all(c["ok"] for c in contagens.values()),
        "totalizacao_bm": totalizacao,
        "total_contratual": total_contratual,
        "unidades_06_2": unidades,
        "itens_sem_quantidade": pend_q,
        "enquadramento_bm_BA": enquad,
        "avisos_AA_AB_AW": avisos,
        "decisoes_registradas": q("SELECT COUNT(*) FROM decisoes"),
        "servicos_06_1_sem_item_confirmado": [s["servico"] for s in servs if s["status"] != "CONFIRMADO"],
        "trechos_mnd": [r[0] for r in conn.execute("SELECT ponto FROM trechos WHERE vigente=1 AND metodologia='MND' ORDER BY 1")],
        "pendencias_importacao": pendencias,
    }
