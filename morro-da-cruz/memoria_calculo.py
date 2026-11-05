"""Memória dimensional da apropriação: números e somas, sem executar expressões."""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import regras as R

DIMENSOES = {"M": 1, "M2": 2, "M3": 3}
ROTULOS = {"M": "m", "M2": "m²", "M3": "m³"}


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


def calcular(unidade, parcelas, quantidade=None):
    u = R.normalizar_unidade(unidade).replace("²", "2").replace("³", "3")
    dim = DIMENSOES.get(u, 0)
    if not dim:
        return None
    if not parcelas and dim == 1 and quantidade is not None:
        parcelas = [{"comprimento": quantidade}]
    if not isinstance(parcelas, list) or not 1 <= len(parcelas) <= 30:
        raise R.RegraViolada("Informe as medidas da memória de cálculo: comprimento" +
                            (", largura/altura" if dim > 1 else "") + (" e profundidade." if dim > 2 else "."))
    total, saida, memorias = Decimal(0), [], []
    chaves = ("comprimento", "largura", "profundidade")[:dim]
    for i, p in enumerate(parcelas, 1):
        if not isinstance(p, dict):
            raise R.RegraViolada("Parcela da memória de cálculo inválida.")
        valores, textos = [], []
        for chave in chaves:
            n, texto = medida(p.get(chave))
            valores.append(n); textos.append(texto)
        rep = str(p.get("repeticoes") or "1")
        if not re.fullmatch(r"[1-9]\d{0,4}", rep):
            raise R.RegraViolada("Repetições devem ser um inteiro entre 1 e 99999.")
        q = Decimal(rep)
        for n in valores:
            q *= n
        if q > Decimal("1000000000000000"):
            raise R.RegraViolada("Resultado da memória de cálculo fora do limite.")
        desc = str(p.get("descricao") or "").strip()[:150]
        conta = " × ".join(("(" + t + ")" if "+" in t else t) for t in textos)
        if rep != "1":
            conta = rep + " × " + conta
        memoria = (desc + ": " if desc else "") + conta + " = " + R.fmt_num(q, 4) + " " + ROTULOS[u]
        if dim > 1:
            memoria = (desc + ": " if desc else "") + "L = " + textos[0] + " m; " + ("H/largura" if dim == 2 else "largura") + " = " + textos[1] + " m; " + ("profundidade = " + textos[2] + " m; " if dim == 3 else "") + "Q = " + conta + " = " + R.fmt_num(q, 4) + " " + ROTULOS[u]
        saida.append({"descricao": desc, **dict(zip(chaves, textos)), "repeticoes": int(rep), "quantidade": float(q)})
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
    return {"versao": 1, "unidade": u, "parcelas": saida, "quantidade": float(arred), "memoria": "\n".join(memorias)}
