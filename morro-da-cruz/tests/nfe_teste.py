"""NF-e de TESTE (estrutura do leiaute 4.00, sem assinatura real): chave com dígito verificador válido."""
import base64

import nfe

CNPJ_FORNECEDOR = "11222333000181"           # CNPJ fictício com dígitos verificadores válidos


def chave(numero, cnpj=CNPJ_FORNECEDOR, serie=1, modelo=55):
    base = f"53" f"2610" f"{cnpj}" f"{modelo:02d}" f"{serie:03d}" f"{int(numero):09d}" f"1" f"{int(numero):08d}"
    return base + str(nfe.dv_chave(base))


def xml(numero, itens, cnpj=CNPJ_FORNECEDOR, modelo=55, emissao="2026-10-14T09:00:00-03:00", protocolo=True, chave_nfe=None, extra=""):
    """itens: [(codigo, descricao, unidade, quantidade, valor_unitario)]"""
    ch = chave_nfe or chave(numero, cnpj, modelo=modelo)
    dets = "".join(
        f"""<det nItem="{k}"><prod><cProd>{c}</cProd><xProd>{d}</xProd><NCM>39172300</NCM><CFOP>5102</CFOP><uCom>{u}</uCom>
            <qCom>{q:.4f}</qCom><vUnCom>{v:.10f}</vUnCom><vProd>{q * v:.2f}</vProd></prod></det>"""
        for k, (c, d, u, q, v) in enumerate(itens, 1))
    total = sum(round(q * v, 2) for _, _, _, q, v in itens)
    prot = (f'<protNFe versao="4.00"><infProt><chNFe>{ch}</chNFe><cStat>100</cStat><nProt>153260000000001</nProt></infProt></protNFe>'
            if protocolo else "")
    return f"""<?xml version="1.0" encoding="UTF-8"?>{extra}
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe{ch}" versao="4.00">
<ide><cUF>53</cUF><mod>{modelo}</mod><serie>1</serie><nNF>{numero}</nNF><dhEmi>{emissao}</dhEmi></ide>
<emit><CNPJ>{cnpj}</CNPJ><xNome>Fornecedor de Teste Ltda</xNome></emit><dest><CNPJ>00000000000191</CNPJ></dest>
{dets}<total><ICMSTot><vProd>{total:.2f}</vProd><vNF>{total:.2f}</vNF></ICMSTot></total></infNFe></NFe>{prot}</nfeProc>""".encode()


def b64(dados):
    return base64.b64encode(dados).decode()
