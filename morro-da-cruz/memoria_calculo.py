"""Memória dimensional da apropriação: números e somas, sem executar expressões."""
import re
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import regras as R

DIMENSOES = {"M": 1, "M2": 2, "M3": 3}
ROTULOS = {"M": "m", "M2": "m²", "M3": "m³"}
MAX_PARTES = 30
MAX_LADOS = 30


def medida(valor):
    texto = str(valor if valor is not None else "").strip()
    partes = texto.split("+")
    if not texto or len(texto) > 400 or len(partes) > 30:
        raise R.RegraViolada("Informe a medida em metros; para somar lados, use 80 + 50 + 40.")
    numeros = []
    for parte in partes:
        p = parte.strip()
        if not re.fullmatch(r"(?:\d+(?:[.,]\d+)?|\d{1,3}(?:\.\d{3})+,\d+)", p):
            raise R.RegraViolada("Medida inválida. Use números positivos e apenas + para somar lados.")
        try:
            n = Decimal(p.replace(".", "").replace(",", ".") if "," in p else p)
        except InvalidOperation:
            raise R.RegraViolada("Medida inválida.") from None
        if not n.is_finite() or not 0 < n <= Decimal("1000000000"):
            raise R.RegraViolada("Cada medida deve ser maior que zero e até um bilhão de metros.")
        numeros.append(n)
    return sum(numeros), " + ".join(R.fmt_num(n, 6) for n in numeros)


def _comprimento(parte):
    lados = parte.get("lados") or []
    soma = str(parte.get("soma") or parte.get("comprimento") or "").strip()
    if lados and soma:
        raise R.RegraViolada("Escolha os lados ou a soma na mesma parte. Não preencha os dois.")
    if not isinstance(lados, list) or len(lados) > MAX_LADOS:
        raise R.RegraViolada(f"Use no máximo {MAX_LADOS} lados por parte.")
    if not lados:
        valor, expressao = medida(soma)
        return valor, expressao, [], expressao
    saida, total = [], Decimal(0)
    for lado in lados:
        if not isinstance(lado, dict) or "+" in str(lado.get("comprimento")):
            raise R.RegraViolada("Cada lado precisa de um comprimento positivo. Use o campo da soma para somar.")
        valor, texto = medida(lado.get("comprimento"))
        nome = str(lado.get("nome") or "").strip()
        if len(nome) > 40:
            raise R.RegraViolada("Nome do lado: no máximo 40 caracteres.")
        saida.append({"nome": nome, "comprimento": texto})
        total += valor
    return total, " + ".join(l["comprimento"] for l in saida), saida, None


def calcular(unidade, parcelas, quantidade=None):
    u = R.normalizar_unidade(unidade).replace("²", "2").replace("³", "3")
    dim = DIMENSOES.get(u, 0)
    if not dim:
        return None
    if not parcelas and dim == 1 and quantidade is not None:
        parcelas = [{"comprimento": quantidade}]
    if not isinstance(parcelas, list) or not 1 <= len(parcelas) <= MAX_PARTES:
        raise R.RegraViolada("Informe as medidas da memória de cálculo: comprimento" +
                            (", largura/altura" if dim > 1 else "") + (" e profundidade." if dim > 2 else "."))
    total, saida, memorias = Decimal(0), [], []
    chaves = ("comprimento", "largura", "profundidade")[:dim]
    for i, p in enumerate(parcelas, 1):
        if not isinstance(p, dict):
            raise R.RegraViolada("Parcela da memória de cálculo inválida.")
        comp, exp, lados, soma = _comprimento(p)
        valores, textos = [comp], [exp]
        for chave in chaves[1:]:
            n, texto = medida(p.get(chave))
            valores.append(n); textos.append(texto)
        rep = str(p.get("repeticoes") if p.get("repeticoes") not in (None, "") else "1")
        if not re.fullmatch(r"[1-9]\d{0,4}", rep):
            raise R.RegraViolada("Repetições devem ser um inteiro entre 1 e 99999.")
        q = Decimal(rep)
        for n in valores:
            q *= n
        if q > Decimal("1000000000000000"):
            raise R.RegraViolada("Resultado da memória de cálculo fora do limite.")
        desc = str(p.get("descricao") or p.get("identificacao") or "").strip()[:150]
        conta = " × ".join(("(" + t + ")" if "+" in t else t) for t in textos)
        if rep != "1":
            conta = rep + " × " + conta
        memoria = (desc + ": " if desc else "") + conta + " = " + R.fmt_num(q, 4) + " " + ROTULOS[u]
        if dim > 1:
            memoria = (desc + ": " if desc else "") + "L = " + textos[0] + " m; " + ("H/largura" if dim == 2 else "largura") + " = " + textos[1] + " m; " + ("profundidade = " + textos[2] + " m; " if dim == 3 else "") + "Q = " + conta + " = " + R.fmt_num(q, 4) + " " + ROTULOS[u]
        saida.append({"descricao": desc, **dict(zip(chaves, textos)), "lados": lados, "soma": soma,
                      "comprimento_m": float(comp), "repeticoes": int(rep), "quantidade": float(q)})
        memorias.append(memoria); total += q
    arred = total.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if arred <= 0:
        raise R.RegraViolada("A quantidade calculada deve ser maior que zero.")
    if quantidade not in (None, ""):
        try:
            informada = Decimal(str(quantidade).replace(",", "."))
        except InvalidOperation:
            raise R.RegraViolada("Quantidade inválida.") from None
        if not informada.is_finite() or abs(informada - arred) > Decimal("0.00005"):
            raise R.RegraViolada("A quantidade não confere com as medidas. Confira a memória de cálculo.")
    if len(saida) > 1:
        memorias.append("Total = " + R.fmt_num(arred, 4) + " " + ROTULOS[u])
    return {"versao": 2, "unidade": u, "parcelas": saida, "quantidade": float(arred), "memoria": "\n".join(memorias)}


def ler(calculo):
    """Lê o retrato v1/v2 sem alterar o banco e sem deduzir lados a partir de um total antigo."""
    if isinstance(calculo, str):
        calculo = json.loads(calculo or "null")
    if not calculo:
        return None
    if calculo.get("versao") not in (1, 2):
        raise R.RegraViolada("Versão da memória dimensional não reconhecida.")
    parcelas = []
    for parte in calculo["parcelas"]:
        p = dict(parte)
        if p.get("lados") or p.get("soma"):
            p.pop("comprimento", None)  # v2 também guarda o comprimento normalizado para leitura humana
        parcelas.append(p)
    return calcular(calculo["unidade"], parcelas, calculo["quantidade"])


def referencia(parte, apropriacao_id=None, limite=64):
    """Abrevia a identificação antes de abreviar a origem. Nunca corta uma expressão no meio."""
    lados = parte.get("lados") or []
    origem = ("LADOS " + " + ".join((l["nome"] + " " if l["nome"] else "") + l["comprimento"] for l in lados)
              if lados else "PERÍMETRO (" + parte["comprimento"] + ")")
    if len(origem) > limite:
        origem = f"PERÍMETRO ({len(lados) or len(parte['comprimento'].split('+'))} LADOS; VER APROPRIAÇÃO Nº {apropriacao_id})"
    desc = parte.get("descricao", "").upper()
    disponivel = limite - len(origem) - 3
    return (desc[:disponivel] + " – " if desc and disponivel > 3 else "") + origem


def resumo_parte(parte, unidade):
    """Resumo com as dimensões numéricas para a justificativa e a composição do canteiro."""
    u = R.normalizar_unidade(unidade).replace("²", "2").replace("³", "3")
    dim = DIMENSOES[u]
    fmt = lambda v: f"{float(v):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    t = (parte.get("descricao", "") + ": " if parte.get("descricao") else "")
    t += ("PERÍMETRO " if dim > 1 else "COMPRIMENTO ") + fmt(parte["comprimento_m"]) + " M"
    if dim > 1:
        t += " × " + ("ALTURA/LARGURA " if dim == 2 else "LARGURA ") + fmt(medida(parte["largura"])[0]) + " M"
    if dim > 2:
        t += " × ESPESSURA " + fmt(medida(parte["profundidade"])[0]) + " M"
    if parte["repeticoes"] != 1:
        t += f" × {parte['repeticoes']} VEZES"
    return t + " = " + fmt(parte["quantidade"]) + " " + ROTULOS[u].upper() + "."
