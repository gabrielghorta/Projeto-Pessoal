"""Regras de negócio puras (sem banco) do sistema Morro da Cruz.

Tudo aqui é determinístico e testável isoladamente; `servicos.py` aplica
estas regras sobre o banco.
"""
import math
import re
from collections import OrderedDict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# ------------------------------------------------------------------ constantes
FRENTES = [f"Zona{n:02d}" for n in range(1, 12)] + ["ADUTORA", "CH"]
CONTINGENCIAS = ["Confecção de Bloquetes", "Execução de Calçadas/Asfalto"]
PERFIL_PENDENTE = "A CONFIRMAR"
CONDICOES_CLIMA = OrderedDict([
    ("SOL", "Sol"),
    ("CHUVA_FRACA_TENDA", "Chuva Fraca c/ Tenda 3x3m"),
    ("PARALISADO_CHUVA", "Paralisado por Chuva"),
    ("VALA_ALAGADA_BOMBA", "Vala Alagada / Bomba"),
])


class RegraViolada(Exception):
    """Operação bloqueada por regra de negócio (mensagem vai para o usuário)."""


class PerfilPendente(RegraViolada):
    pass


# ------------------------------------------------------------------ N02 — unidades
def normalizar_unidade(u):
    """Só padroniza a grafia (maiúsculas, sem ponto). Não cria equivalências: UN e PÇ continuam
    distintos até haver decisão documentada."""
    return (u or "").strip().upper().replace(".", "")


def somar_por_unidade(itens):
    """Soma quantidades separadas por unidade. Nunca devolve um total único.

    itens: iterável de (unidade, quantidade). Retorna OrderedDict unidade -> total.
    """
    tot = OrderedDict()
    for unidade, qtd in itens:
        u = normalizar_unidade(unidade)
        if not u:
            raise RegraViolada("Item sem unidade não pode ser contabilizado (auditoria N02).")
        tot[u] = round(tot.get(u, 0.0) + float(qtd or 0), 6)
    return tot


def nome_completo(nome):
    """Nome do trecho ou nó para quem lê: Zona03_PB06_Rede_TR014 → "Zona 03 · PB06 · TR014". A numeração TR recomeça a
    cada PB (o TR001 existe em dezenas de PBs): o número sozinho não identifica o trecho."""
    m = re.match(r"^(?:Zona(\d+)|(ADUTORA))_(PB\d+)_(?:Rede_)?(.+)$", str(nome or ""))
    if not m:
        return str(nome or "")
    return f"{'Zona ' + m.group(1) if m.group(1) else 'Adutora'} · {m.group(3)} · {m.group(4)}"


def fmt_num(v, casas=2):
    s = f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if casas and "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def formatar_por_unidade(totais):
    """{'UN': 17, 'M': 0.71} -> '17 UN · 0,71 m'."""
    return " · ".join(f"{fmt_num(q)} {'m' if u == 'M' else u}" for u, q in totais.items())


# ------------------------------------------------------------------ E06 — perfil de vala
def perfil_pendente(trecho):
    """Motivo do bloqueio, ou None se o perfil de vala está definido."""
    if str(trecho.get("perfil_status") or "").upper() == PERFIL_PENDENTE:
        return "Perfil de vala A CONFIRMAR"
    for campo in ("profundidade_m", "largura_m", "lastro_m"):
        v = trecho.get(campo)
        invalido = not isinstance(v, (int, float)) or v < 0 or (v == 0 and campo != "lastro_m")
        if invalido:
            return f"Perfil de vala incompleto ({campo} = {v!r})"
    return None


def bloqueio_perfil(trecho):
    """Única regra de perfil para cálculo E detalhe: vala só existe em VCA; MND não exige perfil."""
    if trecho.get("metodologia") == "MND":
        return None
    return perfil_pendente(trecho)


def exigir_perfil(trecho):
    motivo = perfil_pendente(trecho)
    if motivo:
        raise PerfilPendente(f"{trecho['id']}: {motivo} — cálculo bloqueado até a definição (auditoria E06).")


# ------------------------------------------------------------------ quantidades previstas
def qtd_soldas(metros, barra_m=6.0):
    return int(math.ceil(metros / barra_m - 1e-9)) if metros > 0 else 0


def quantidades_previstas_trecho(trecho, quantidades_totais, metros, mapa):
    """Quantidades previstas para L metros de um trecho.

    As quantidades vêm da própria 06.1 (colunas AL:BK do trecho), rateadas por
    L / extensão. Volumes negativos indicam dado inconsistente e bloqueiam
    (nunca IFERROR -> 0).
    """
    L = float(metros)
    if L <= 0:
        return []
    mnd = trecho.get("metodologia") == "MND"
    motivo = bloqueio_perfil(trecho)    # perfil de vala só se aplica a vala a céu aberto (VCA)
    if motivo:
        raise PerfilPendente(f"{trecho['id']}: {motivo} — cálculo bloqueado até a definição (auditoria E06).")
    ext = float(trecho["extensao_m"])
    frac = min(L / ext, 1.0) if ext > 0 else 0.0
    out = []
    for s in mapa["gaveta1"]:
        if mnd and s["coluna"] != "M":
            continue                    # MND: sem serviços de vala; só o comprimento executado
        if s["coluna"] == "M":
            q = L
        else:
            total = quantidades_totais.get(s["coluna"])
            if total is None:
                continue
            q = float(total) * frac
        if q < -1e-9:
            raise PerfilPendente(f"{trecho['id']}: {s['servico']} negativo ({q:.3f}) — revisar perfil de vala.")
        if abs(q) < 1e-9:
            continue
        out.append({"servico": s["servico"], "unidade": s["unidade"], "previsto": round(q, 3)})
    if str(trecho.get("material") or "").upper() == "PEAD" and trecho.get("metodologia") != "MND":
        sol = mapa["solda"]
        # ⌈L/6⌉ é só ESTIMATIVA de referência: nunca vira quantidade confirmada (soldas têm controle próprio)
        out.append({"servico": sol["servico"], "unidade": "UN", "previsto": qtd_soldas(L, sol["comprimento_barra_m"]),
                    "estimativa": True})
    return out


def quantidades_previstas_elemento(pecas):
    """Peças do nó/caixa agrupadas por descrição+diâmetro+unidade (sem misturar unidades)."""
    agrup = OrderedDict()
    for p in pecas:
        u = normalizar_unidade(p["unidade"])
        nome = p["descricao"] + (f" DE{p['diametro']}" if p.get("diametro") not in (None, "", "N/A") else "")
        agrup[(nome, u)] = agrup.get((nome, u), 0.0) + float(p["quantidade"])
    return [{"servico": d, "unidade": u, "previsto": round(q, 3)} for (d, u), q in agrup.items()]


def ratear(qtd, itens_quantidades):
    """Rateia qtd entre itens proporcionalmente às quantidades contratuais."""
    tot = sum(q for _, q in itens_quantidades)
    if tot <= 0:
        n = len(itens_quantidades)
        return [(i, qtd / n) for i, _ in itens_quantidades]
    return [(i, qtd * q / tot) for i, q in itens_quantidades]


# ------------------------------------------------------------------ fotos
FOTOS_TRECHO = ("SINALIZACAO", "EXECUCAO", "CONCLUIDO")
NOMES_FOTO = {"SINALIZACAO": "sinalização", "EXECUCAO": "execução", "CONCLUIDO": "concluído"}
FOTOS_ELEMENTO = ("EXECUCAO", "CONCLUIDO")


def fotos_pendentes(alvo_tipo, categorias_existentes, sinalizacao_herdada):
    """Categorias de foto que ainda faltam.

    Trecho: 3 fotos (sinalização, executando, concluído).
    Nó/caixa: 2 fotos; herda a sinalização se algum trecho ligado (mesma
    área/rua) já tem foto de sinalização — senão a área é nova e exige as 3.
    """
    exigidas = list(FOTOS_TRECHO if alvo_tipo == "TRECHO" else FOTOS_ELEMENTO)
    if alvo_tipo != "TRECHO" and not sinalizacao_herdada:
        exigidas.insert(0, "SINALIZACAO")
    tem = set(categorias_existentes)
    return [c for c in exigidas if c not in tem]


def carimbo(contrato, alvo_id, data_hora, lat=None, lon=None):
    gps = f"{lat:.6f}, {lon:.6f}" if lat is not None and lon is not None else "GPS indisponível"
    return f"{contrato} | {alvo_id} | {data_hora} | {gps}"


# ------------------------------------------------------------------ OK Fiscalização / mapa iluminado
def validar_ok_fiscal(execucao, fotos_faltando):
    if not execucao or not execucao.get("concluido"):
        raise RegraViolada("OK Fiscalização exige o trecho/nó 100 % executado e reaterrado.")
    if fotos_faltando:
        raise RegraViolada("OK Fiscalização exige as fotos obrigatórias. Faltando: " + ", ".join(fotos_faltando))
    if execucao.get("ok_fiscal_em"):
        raise RegraViolada("Trecho/nó já marcado com OK Fiscalização.")


# Etapa do trecho no mapa, da mais atrasada à mais adiantada. "Verificado" e "OK interno" são conferência interna da
# Ankara; só "cadastrado" (memorando ESET registrado) é decisão da Caesb.
ETAPAS_MAPA = ("nao", "liberado", "execucao", "executado", "verificado", "campo", "pronto", "ok", "cad_andamento",
               "cadastrado")


def etapa_trecho(liberado=False, equipe_hoje=False, informado_hoje=False, executado=False, concluido=False,
                 verificado=False, fotos_ok=False, campo=False, ok=False, esteira=None):
    """A etapa que acende no mapa, só pelo que foi gravado. A equipe liberada hoje deixa o trecho "em execução" até a NS
    do dia (ou o apontamento) chegar; com ela, o trecho passa a "executado, aguardando verificação"."""
    if esteira == "6_APROVADO":
        return "cadastrado"
    if esteira and esteira != "1_PRONTO":
        return "cad_andamento"
    if ok:
        return "ok"
    if equipe_hoje and not concluido and not informado_hoje:
        return "execucao"
    if concluido and verificado and fotos_ok:
        return "pronto"
    if campo:
        return "campo"
    if executado:
        return "verificado" if verificado else "executado"
    return "execucao" if equipe_hoje else "liberado" if liberado else "nao"


def distancia_m(lat1, lon1, lat2, lon2):
    """Distância em metros entre dois pontos (graus), pela esfera: basta para pôr o mais perto primeiro."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


def status_mapa(execucao, fotos_faltando, medicao_atual_id):
    """Classe de cor do Modo Mapa Iluminado."""
    if not execucao:
        return "NAO_EXECUTADO"          # cinza pontilhado (nenhum apontamento)
    if execucao.get("ok_fiscal_em"):
        if execucao.get("medicao_id") and medicao_atual_id and execucao["medicao_id"] != medicao_atual_id:
            return "MEDIDO_ANTERIOR"    # amarelo sólido
        return "OK_FISCAL"              # verde esmeralda
    if execucao["concluido"] and not fotos_faltando:
        return "CONCLUIDO_MES"          # vermelho/ciano — aguardando validação
    return "EM_EXECUCAO"                # laranja tracejado


# ------------------------------------------------------------------ esteira de cadastro (GDOC)
ETAPAS = OrderedDict([
    ("1_PRONTO", "1. Pronto p/ Cadastro"),
    ("2_ENVIADO", "2. Dados Enviados p/ Empresa de Cadastro"),
    ("3_RECEBIDO", "3. Cadastros Recebidos da Terceirizada"),
    ("4_GDOC_ANALISE", "4. Catalogado no GDOC Caesb — Em Análise"),
    ("5A_NEGADO", "5A. Cadastro Negado no GDOC"),
    ("6_APROVADO", "6. Aprovado no GDOC"),
])

# etapa_atual -> {etapa_destino: campos obrigatórios}
TRANSICOES = {
    "1_PRONTO": {"2_ENVIADO": ("empresa", "data_envio")},
    "2_ENVIADO": {"3_RECEBIDO": ("arquivos",)},
    # 3 → 2: devolver à empresa depois de conferência interna NÃO CONFORME (nova revisão)
    "3_RECEBIDO": {"4_GDOC_ANALISE": ("protocolo_gdoc",), "2_ENVIADO": ()},
    "4_GDOC_ANALISE": {"6_APROVADO": ("memorando_eset",), "5A_NEGADO": ("motivo_negativa",)},
    "5A_NEGADO": {"2_ENVIADO": ()},   # [Reenviar p/ Empresa Ajustar] -> Em Produção (Rev. N)
    "6_APROVADO": {},
}


# Conferência interna Ankara do cadastro recebido da empresa, antes do protocolo no GDOC. Roteiro PROPOSTO para
# achar divergência com o executado e com o levantamento de campo; não é critério nem aprovação da Caesb.
CHECKLIST_CONFERENCIA_CADASTRO = OrderedDict([
    ("EXTENSAO", "Extensão desenhada confere com o assentado registrado (intervalos)"),
    ("TRACADO", "Traçado e posição conferem com o levantamento de campo"),
    ("PROFUNDIDADE", "Profundidade e cotas conferem com o levantamento de campo"),
    ("MATERIAL_DE", "Material e diâmetro conferem com o executado"),
    ("PECAS_NOS", "Peças, conexões e nós conferem com o executado"),
    ("ARQUIVOS", "Arquivos completos (DWG/PDF) e nomenclatura do trecho conforme"),
])


# Conferência interna da medição de TESTE pela engenharia, antes do fechamento (PROVISÓRIO, D-59). Confere a proposta
# contra os registros e as evidências; não é aprovação da Caesb nem libera medição oficial.
CHECKLIST_CONFERENCIA_MEDICAO = OrderedDict([
    ("EXECUTADO", "Lançamentos conferidos com o executado e verificado nos registros de campo"),
    ("EVIDENCIAS", "Evidências conferidas (fotos válidas, soldas, memorando ESET do cadastro)"),
    ("PENDENTES", "Lançamentos PENDENTES identificados e mantidos fora do valor"),
    ("DUPLICIDADE", "Sem parcela já medida em medição anterior"),
    ("HIPOTESES", "Hipóteses e regras bloqueadas da simulação revisadas"),
])


def validar_conferencia(resultado, checklist, revisor, obs, roteiro=None,
                        exige_obs="Descreva a divergência encontrada (vai para a empresa de cadastro)."):
    """CONFORME exige todos os itens conferidos; NAO_CONFORME exige a descrição da divergência."""
    roteiro = roteiro or CHECKLIST_CONFERENCIA_CADASTRO
    if resultado not in ("CONFORME", "NAO_CONFORME"):
        raise RegraViolada("Resultado da conferência: CONFORME ou NAO_CONFORME.")
    if not str(revisor or "").strip():
        raise RegraViolada("Informe quem conferiu.")
    itens = {k: bool((checklist or {}).get(k)) for k in roteiro}
    if set(checklist or {}) - set(itens):
        raise RegraViolada("Item de conferência desconhecido: " + ", ".join(sorted(set(checklist) - set(itens))))
    if resultado == "CONFORME" and not all(itens.values()):
        raise RegraViolada("CONFORME exige todos os itens conferidos. Pendentes: "
                           + ", ".join(roteiro[k] for k, v in itens.items() if not v))
    if resultado == "NAO_CONFORME" and not str(obs or "").strip():
        raise RegraViolada(exige_obs)
    return itens


def validar_transicao(etapa_atual, destino, dados):
    permitidas = TRANSICOES.get(etapa_atual, {})
    if destino not in permitidas:
        raise RegraViolada(f"Transição inválida: {ETAPAS.get(etapa_atual)} → {ETAPAS.get(destino, destino)}.")
    faltando = [c for c in permitidas[destino] if not str(dados.get(c) or "").strip()]
    if faltando:
        raise RegraViolada("Campos obrigatórios: " + ", ".join(faltando))


def rotulo_etapa(etapa, revisao):
    if etapa == "2_ENVIADO" and revisao > 0:
        return f"2. Em Produção (Rev. {revisao})"
    return ETAPAS[etapa]


# ------------------------------------------------------------------ medição / BDI / reajuste
def _dec(x):
    """Decimal com 15 algarismos significativos — a precisão com que o Excel exibe e arredonda doubles."""
    return Decimal(format(float(x or 0), ".15g"))


def excel_round(valor, casas=2):
    """ROUND do Excel (meio para longe do zero) sobre o valor com 15 algarismos significativos.

    Ex.: 6.026,69 × 47,50 = 286.267,775 → Excel 286.267,78 (o float do Python daria ...,77).
    """
    return _dec(valor).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)


def produto_excel(q, p):
    return (_dec(q) * _dec(p)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def totalizar_bm(itens, bdi_material, bdi_servico, coef_k, modo="medicao"):
    """Totaliza como o BM Vertical (fórmulas conferidas nas células, REV03/REV04).

    modo="medicao" (colunas de medição V/W…):  W = ROUND(quantidade × preço; 2) por item;
                                                V548/V549 = SUMIFS(W) por classe.
    modo="contrato" (coluna T, P0):            T548/T549 = ROUND(SUMPRODUCT(quant.; preço) por classe; 2).
    Depois, igual nos dois modos (sem arredondar):
      BDI: ΣMAT × BDI_mat + ΣSERV × BDI_serv;  K: (Σ + BDI) × K, com K = −1 + (1 − 14,04 %);
      total = (Σ + BDI) × (1 + K).
    itens: iterável de (classificacao, quantidade, preco_unitario) — uma entrada por item do BM.
    Contrato 5.2: custos unitários sem BDI × coeficientes “K x BDI” × quantitativos.
    """
    mat = srv = Decimal(0)
    for classe, q, p in itens:
        base = produto_excel(q, p) if modo == "medicao" else _dec(q) * _dec(p)
        if str(classe).upper().startswith("MATERIAL"):
            mat += base
        else:
            srv += base
    if modo == "contrato":
        mat, srv = mat.quantize(Decimal("0.01"), ROUND_HALF_UP), srv.quantize(Decimal("0.01"), ROUND_HALF_UP)
    bdi_m = float(mat) * bdi_material
    bdi_s = float(srv) * bdi_servico
    sub01 = float(mat) + float(srv)
    total01_02 = sub01 + bdi_m + bdi_s
    total = total01_02 + total01_02 * coef_k
    return {"modo": modo, "material": float(mat), "servico": float(srv), "bdi_material": bdi_m, "bdi_servico": bdi_s,
            "subtotal_01": sub01, "total_01_02": total01_02, "k": total01_02 * coef_k, "total": round(total, 2),
            "total_exato": total}


def indice_reajuste(periodo_ini, periodo_fim, indices):
    """Índice aplicável ao período da medição.

    indices: lista de dicts {vigencia_ini, vigencia_fim, indice} (ISO).
    Período inteiro antes do 1º aniversário → 0. Período que cruza um
    aniversário ou passa da última vigência cadastrada → bloqueia (rateio e
    índice do próximo aniversário pendentes; não repetir 3,29 % automaticamente).
    """
    di = periodo_ini if isinstance(periodo_ini, date) else date.fromisoformat(periodo_ini)
    df = periodo_fim if isinstance(periodo_fim, date) else date.fromisoformat(periodo_fim)
    ordenados = sorted(indices, key=lambda i: i["vigencia_ini"])
    if not ordenados or df < date.fromisoformat(ordenados[0]["vigencia_ini"]):
        return 0.0
    for i in ordenados:
        if date.fromisoformat(i["vigencia_ini"]) <= di and df <= date.fromisoformat(i["vigencia_fim"]):
            return float(i["indice"])
    raise RegraViolada(
        f"Medição {di.isoformat()} a {df.isoformat()} sem índice de reajuste definido "
        "(cruza aniversário ou após a última vigência) — cadastrar o novo índice e o rateio na aba REAJUSTE.")


# ------------------------------------------------------------------ base de custo: situação do item
ORIGEM_CODIGO = OrderedDict([("BASE_CAESB", "base Caesb"), ("SINAPI", "base Caesb (composição SINAPI)"),
                             ("SICRO", "base Caesb (composição SICRO)"), ("PROVISORIO", "código provisório"),
                             ("NOVO", "item novo")])


def origem_codigo(codigo):
    """De onde vem o código do item do BM: base Caesb (só números), base Caesb com composição SINAPI ('SI' no código, como
    8000508010SI98459) ou SICRO ('SC'), ou provisório (com 'X', como 1514603060XX11, até a Caesb dar o código oficial).
    Os códigos com SI e SC são oficiais da base de custos da Caesb e vieram no orçamento da licitação (P0): são
    contratuais. Código vazio ou fora desses formatos também é provisório."""
    c = str(codigo or "").strip().upper()
    if not c or "X" in c:
        return "PROVISORIO"
    if "SI" in c:
        return "SINAPI"
    if "SC" in c:
        return "SICRO"
    return "BASE_CAESB" if c.isdigit() else "PROVISORIO"


def composicao_referencia(codigo):
    """'8000508010SI98459' → 'SINAPI 98459'; '2202019100SCE9779' → 'SICRO E9779'; código sem SI/SC → None."""
    m = re.search(r"(SI|SC)([A-Z0-9]+)$", str(codigo or "").strip().upper())
    return f"{'SINAPI' if m.group(1) == 'SI' else 'SICRO'} {m.group(2)}" if m else None


def aplicar_teto(valor_pedido, ja_medido, teto):
    """Limita ao teto do subgrupo (BM Vertical). Retorna (valor_aceito, excedente)."""
    if teto is None:
        return round(valor_pedido, 2), 0.0
    disponivel = max(0.0, teto - ja_medido)
    aceito = min(valor_pedido, disponivel)
    return round(aceito, 2), round(valor_pedido - aceito, 2)


# ------------------------------------------------------------------ intervalos de execução por etapa (etapa 4)
ETAPAS_INTERVALO = ("ASSENTADO", "CADASTRO_CAMPO", "REATERRADO")
TOL_M = 1e-3


def unir_intervalos(intervalos):
    """[(ini, fim)] → lista ordenada e unida (intervalos que se tocam viram um só)."""
    out = []
    for a, b in sorted((float(a), float(b)) for a, b in intervalos):
        if out and a <= out[-1][1] + TOL_M:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [tuple(x) for x in out]


def comprimento(intervalos):
    return round(sum(b - a for a, b in unir_intervalos(intervalos)), 6)


def sobreposicao(intervalo, intervalos):
    """Trecho comum (> 1 mm) entre `intervalo` e algum dos `intervalos`, ou None."""
    a, b = intervalo
    for c, d in intervalos:
        ini, fim = max(a, c), min(b, d)
        if fim - ini > TOL_M:
            return (ini, fim)
    return None


def fora_da_cobertura(intervalo, cobertura):
    """Partes de `intervalo` não cobertas pela `cobertura` (lista unida)."""
    a, b = intervalo
    faltas, pos = [], a
    for c, d in unir_intervalos(cobertura):
        if d <= pos + TOL_M:
            continue
        if c > b - TOL_M:
            break
        if c > pos + TOL_M:
            faltas.append((pos, min(c, b)))
        pos = max(pos, d)
    if pos < b - TOL_M:
        faltas.append((pos, b))
    return faltas


def lacunas(cobertura, extensao):
    return fora_da_cobertura((0.0, float(extensao)), cobertura)
