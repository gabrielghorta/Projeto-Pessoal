"""Leitura do XML da NF-e (modelo 55) só com a biblioteca padrão.

O que é conferido:
* XML bem formado, sem DOCTYPE/entidades (bloqueia ataques de expansão e entidades externas), até 5 MB;
* namespace oficial da NF-e e modelo 55;
* chave de acesso com 44 dígitos e dígito verificador (módulo 11);
* campos obrigatórios (número, emissão, emitente, itens) e números válidos;
* cada item: quantidade × valor unitário ≈ valor do item; soma dos itens ≈ total de produtos (ICMSTot/vProd).

O que NÃO é conferido (limitação registrada): a assinatura digital (XMLDSig) e a situação da nota na SEFAZ. O
protocolo de autorização, quando presente no XML (nfeProc/protNFe), é só lido. Por isso a nota importada fica
"A CONFERIR" e não gera movimento até a conferência por uma pessoa.
"""
import xml.etree.ElementTree as ET
from datetime import datetime

import regras as R

NS = "http://www.portalfiscal.inf.br/nfe"
LIMITE = 5 * 1024 * 1024


def _t(el, caminho):
    x = el.find(caminho.replace("n:", f"{{{NS}}}")) if el is not None else None
    return x.text.strip() if x is not None and x.text else None


def dv_chave(chave43):
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(chave43)))
    dv = 11 - soma % 11
    return 0 if dv >= 10 else dv


def chave_valida(chave):
    return isinstance(chave, str) and len(chave) == 44 and chave.isdigit() and dv_chave(chave[:43]) == int(chave[43])


def _num(v, campo, item=None):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise R.RegraViolada(f"NF-e: {campo}{f' do item {item}' if item else ''} ausente ou inválido.") from None
    return x


def ler(dados):
    """Dicionário com cabeçalho e itens da NF-e, ou RegraViolada com o motivo."""
    if not dados or len(dados) > LIMITE:
        raise R.RegraViolada("XML vazio ou maior que 5 MB.")
    if b"<!DOCTYPE" in dados.upper() or b"<!ENTITY" in dados.upper():
        raise R.RegraViolada("XML com DOCTYPE/ENTITY não é aceito (NF-e não usa).")
    try:
        raiz = ET.fromstring(dados)
    except ET.ParseError as e:
        raise R.RegraViolada(f"XML inválido: {e}") from None
    inf = raiz.find(f".//{{{NS}}}infNFe")
    if inf is None:
        raise R.RegraViolada("O arquivo não é uma NF-e (sem infNFe no namespace da NF-e).")
    chave = (inf.get("Id") or "")[3:]
    if not chave_valida(chave):
        raise R.RegraViolada("Chave de acesso inválida (44 dígitos com dígito verificador).")
    ide = inf.find(f"{{{NS}}}ide")
    if _t(ide, "n:mod") != "55":
        raise R.RegraViolada("Só NF-e modelo 55 é aceita.")
    emissao = _t(ide, "n:dhEmi") or _t(ide, "n:dEmi")
    numero = _t(ide, "n:nNF")
    if not numero or not emissao:
        raise R.RegraViolada("NF-e sem número ou data de emissão.")
    try:
        data_emissao = datetime.fromisoformat(emissao[:10]).date().isoformat()
    except ValueError:
        raise R.RegraViolada("Data de emissão inválida.") from None
    emit = inf.find(f"{{{NS}}}emit")
    cnpj = _t(emit, "n:CNPJ")
    if not cnpj or not _t(emit, "n:xNome"):
        raise R.RegraViolada("NF-e sem CNPJ ou nome do emitente.")
    itens = []
    for det in inf.findall(f"{{{NS}}}det"):
        n = det.get("nItem")
        prod = det.find(f"{{{NS}}}prod")
        q, vu, vp = (_num(_t(prod, f"n:{c}"), nome, n) for c, nome in (("qCom", "quantidade"), ("vUnCom", "valor unitário"),
                                                                         ("vProd", "valor")))
        if q <= 0:
            raise R.RegraViolada(f"NF-e: quantidade do item {n} deve ser maior que zero.")
        if abs(q * vu - vp) > max(0.05, abs(vp) * 1e-6):
            raise R.RegraViolada(f"NF-e: item {n} com quantidade × valor unitário ({q * vu:.2f}) diferente do valor ({vp:.2f}).")
        if not _t(prod, "n:xProd") or not _t(prod, "n:uCom"):
            raise R.RegraViolada(f"NF-e: item {n} sem descrição ou unidade.")
        itens.append({"n_item": int(n), "codigo": _t(prod, "n:cProd"), "descricao": _t(prod, "n:xProd"), "ncm": _t(prod, "n:NCM"),
                      "cfop": _t(prod, "n:CFOP"), "unidade": _t(prod, "n:uCom"), "quantidade": q, "valor_unitario": vu,
                      "valor_total": vp})
    if not itens:
        raise R.RegraViolada("NF-e sem itens.")
    tot = inf.find(f"{{{NS}}}total/{{{NS}}}ICMSTot")
    v_prod = _num(_t(tot, "n:vProd"), "total de produtos")
    if abs(sum(i["valor_total"] for i in itens) - v_prod) > 0.05:
        raise R.RegraViolada("NF-e: soma dos itens diferente do total de produtos.")
    prot = raiz.find(f".//{{{NS}}}protNFe/{{{NS}}}infProt")
    return {"chave": chave, "numero": numero, "serie": _t(ide, "n:serie"), "data_emissao": data_emissao,
            "emitente_cnpj": cnpj, "emitente_nome": _t(emit, "n:xNome"),
            "destinatario_cnpj": _t(inf.find(f"{{{NS}}}dest"), "n:CNPJ"),
            "valor_produtos": v_prod, "valor_total": _num(_t(tot, "n:vNF"), "valor da nota"), "itens": itens,
            "autorizacao": ({"cStat": _t(prot, "n:cStat"), "nProt": _t(prot, "n:nProt")} if prot is not None else None)}
