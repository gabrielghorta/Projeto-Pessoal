"""Leitor mínimo do .xls (Excel 97-2003, BIFF8), só com a biblioteca padrão: a planilha da NS ainda chega nesse formato.

Lê o arquivo composto do Office (OLE2), o fluxo Workbook e as células com valor: texto, número, data, booleano, erro e
o resultado guardado das fórmulas. Do estilo, só o formato do número; nada é recalculado. Devolve as abas como o
openpyxl (linhas desde a A1, células vazias como None), para o mesmo leitor da NS servir aos dois formatos.
"""
import re
import struct
from datetime import datetime, timedelta

ASSINATURA = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
FIM_CADEIA = 0xFFFFFFFE
ESPECIAL = 0xFFFFFFFA                # daqui para cima: fim de cadeia, setor livre, setor da tabela
LIMITE_CELULAS = 200_000             # uma NS tem algumas centenas; mais que isso é arquivo estranho
ERROS = {0x00: '#NULL!', 0x07: '#DIV/0!', 0x0F: '#VALUE!', 0x17: '#REF!', 0x1D: '#NAME?', 0x24: '#NUM!', 0x2A: '#N/A'}
# formatos internos do Excel (os que o arquivo não escreve), com os nomes do openpyxl
INTERNOS = {0: 'General', 1: '0', 2: '0.00', 3: '#,##0', 4: '#,##0.00', 5: '"$"#,##0_);("$"#,##0)',
            6: '"$"#,##0_);[Red]("$"#,##0)', 7: '"$"#,##0.00_);("$"#,##0.00)', 8: '"$"#,##0.00_);[Red]("$"#,##0.00)',
            9: '0%', 10: '0.00%', 11: '0.00E+00', 12: '# ?/?', 13: '# ??/??', 14: 'mm-dd-yy', 15: 'd-mmm-yy',
            16: 'd-mmm', 17: 'mmm-yy', 18: 'h:mm AM/PM', 19: 'h:mm:ss AM/PM', 20: 'h:mm', 21: 'h:mm:ss',
            22: 'm/d/yy h:mm', 37: '#,##0_);(#,##0)', 38: '#,##0_);[Red](#,##0)', 39: '#,##0.00_);(#,##0.00)',
            40: '#,##0.00_);[Red](#,##0.00)', 45: 'mm:ss', 46: '[h]:mm:ss', 47: 'mmss.0', 48: '##0.0E+0', 49: '@'}
DATAS_INTERNAS = set(range(14, 23)) | set(range(27, 37)) | {45, 46, 47} | set(range(50, 59))
CONTINUE, EOF, BOF = 0x003C, 0x000A, 0x0809


class XlsInvalido(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ arquivo composto
def _fluxo(dados, nome):
    """Bytes do fluxo `nome` do arquivo composto (None se não houver)."""
    if len(dados) < 512 or dados[:8] != ASSINATURA:
        raise XlsInvalido('não é um arquivo do Excel 97-2003')
    ss = 1 << struct.unpack_from('<H', dados, 30)[0]
    if ss not in (512, 4096) or struct.unpack_from('<H', dados, 32)[0] != 6:
        raise XlsInvalido('cabeçalho do arquivo composto inválido')
    _, dir1, corte, minifat1, _, difat1, n_difat = struct.unpack_from('<II4xIIIII', dados, 44)
    n_setores = -(-(len(dados) - ss) // ss)

    def setor(i):
        if i >= n_setores:
            raise XlsInvalido('setor fora do arquivo')
        return dados[(i + 1) * ss:(i + 2) * ss].ljust(ss, b'\0')

    def cadeia(ini, tabela):
        visto = set()
        while ini != FIM_CADEIA:
            if ini >= len(tabela) or ini in visto:
                raise XlsInvalido('cadeia de setores quebrada')
            visto.add(ini)
            yield ini
            ini = tabela[ini]

    setores_fat = [x for x in struct.unpack_from('<109I', dados, 76) if x < ESPECIAL]
    d, visto = difat1, set()
    while d < ESPECIAL and len(visto) < n_difat:
        if d in visto:
            raise XlsInvalido('cadeia de setores quebrada')
        visto.add(d)
        s = setor(d)
        setores_fat += [x for x in struct.unpack_from(f'<{ss // 4 - 1}I', s) if x < ESPECIAL]
        d = struct.unpack_from('<I', s, ss - 4)[0]
    if not setores_fat or len(setores_fat) > n_setores:
        raise XlsInvalido('tabela de setores inválida')
    fat = [x for i in setores_fat for x in struct.unpack(f'<{ss // 4}I', setor(i))]

    def ler(ini, tam, tabela, ler_setor):
        partes = b''.join(ler_setor(i) for i in cadeia(ini, tabela))
        if len(partes) < tam:
            raise XlsInvalido('fluxo menor que o tamanho declarado')
        return partes[:tam]

    diretorio = b''.join(setor(i) for i in cadeia(dir1, fat))
    entradas = []                      # (nome, tipo: 2 fluxo / 5 raiz, primeiro setor, tamanho)
    for o in range(0, len(diretorio) - 127, 128):
        e = diretorio[o:o + 128]
        n = min(struct.unpack_from('<H', e, 64)[0], 64)
        tam = struct.unpack_from('<Q', e, 120)[0] if ss == 4096 else struct.unpack_from('<I', e, 120)[0]
        entradas.append((e[:max(n - 2, 0)].decode('utf-16-le', 'replace'), e[66], struct.unpack_from('<I', e, 116)[0], tam))
    if not entradas or entradas[0][1] != 5:
        raise XlsInvalido('arquivo composto sem a raiz')
    alvo = next((e for e in entradas if e[1] == 2 and e[0].lower() == nome.lower()), None)
    if alvo is None:
        return None
    if alvo[3] > len(dados):
        raise XlsInvalido('fluxo maior que o arquivo')
    if alvo[3] >= corte:
        return ler(alvo[2], alvo[3], fat, setor)
    raiz = entradas[0]                 # fluxo pequeno: mora no mini fluxo da raiz, em blocos de 64 bytes
    mini = ler(raiz[2], raiz[3], fat, setor) if raiz[3] else b''
    mf = b''.join(setor(i) for i in cadeia(minifat1, fat)) if minifat1 < ESPECIAL else b''
    minifat = struct.unpack(f'<{len(mf) // 4}I', mf[:len(mf) // 4 * 4])
    return ler(alvo[2], alvo[3], minifat, lambda i: mini[i * 64:(i + 1) * 64])


def eh_xls(dados):
    """Arquivo composto do Office com o fluxo Workbook (o .doc e o .ppt também são compostos, mas sem esse fluxo)."""
    try:
        return dados[:8] == ASSINATURA and _fluxo(dados, 'Workbook') is not None
    except (XlsInvalido, struct.error):
        return False


# ------------------------------------------------------------------------------------------------ registros BIFF8
class _Pedacos:
    """Um registro com as continuações (CONTINUE): o texto partido entre dois registros recomeça com um byte que diz se
    os caracteres seguintes têm 1 ou 2 bytes; o resto (cabeçalho do texto, formatação) atravessa a divisa direto."""

    def __init__(self, pedacos):
        self.p, self.i, self.o = pedacos, 0, 0

    def bytes(self, n):
        out = []
        while n > 0:
            while self.i < len(self.p) and self.o >= len(self.p[self.i]):
                self.i, self.o = self.i + 1, 0
            if self.i >= len(self.p):
                raise XlsInvalido('registro truncado')
            c = self.p[self.i][self.o:self.o + n]
            out.append(c)
            self.o, n = self.o + len(c), n - len(c)
        return b''.join(out)

    def num(self, fmt):
        return struct.unpack(fmt, self.bytes(struct.calcsize(fmt)))[0]

    def _caracteres(self, cch, largo):
        out = []
        while cch > 0:
            if self.i >= len(self.p):
                raise XlsInvalido('texto truncado')
            if self.o >= len(self.p[self.i]):              # continua no registro seguinte, com novo byte de largura
                self.i, self.o = self.i + 1, 1
                if self.i >= len(self.p) or not self.p[self.i]:
                    raise XlsInvalido('texto truncado')
                largo = self.p[self.i][0] & 1
                continue
            larg = 2 if largo else 1
            k = min(cch, (len(self.p[self.i]) - self.o) // larg)
            if k == 0:
                raise XlsInvalido('texto partido no meio de um caractere')
            out.append(self.p[self.i][self.o:self.o + k * larg].decode('utf-16-le' if largo else 'latin-1'))
            self.o, cch = self.o + k * larg, cch - k
        return ''.join(out)

    def texto(self, cch_curto=False, rico=False):
        """XLUnicodeString (rico: XLUnicodeRichExtendedString, da tabela de textos; a formatação é pulada)."""
        cch = self.num('<B' if cch_curto else '<H')
        op = self.num('<B')
        runs = self.num('<H') if rico and op & 0x08 else 0
        ext = self.num('<I') if rico and op & 0x04 else 0
        s = self._caracteres(cch, op & 0x01)
        if runs or ext:
            self.bytes(4 * runs + ext)
        return s


class _Registros:
    """Os registros do fluxo a partir de uma posição, com o próximo à mão (para juntar as continuações)."""

    def __init__(self, fluxo, pos):
        self.f, self.p, self.guardado = fluxo, pos, None

    def proximo(self):
        if self.guardado:
            r, self.guardado = self.guardado, None
            return r
        if self.p + 4 > len(self.f):
            return None
        tipo, n = struct.unpack_from('<HH', self.f, self.p)
        r = (tipo, self.f[self.p + 4:self.p + 4 + n])
        self.p += 4 + n
        return r

    def com_continuacoes(self, primeiro):
        pedacos = [primeiro]
        while True:
            r = self.proximo()
            if r is None or r[0] != CONTINUE:
                self.guardado = r
                return _Pedacos(pedacos)
            pedacos.append(r[1])


def _rk(v):
    """Número compactado do Excel: inteiro de 30 bits ou os 30 bits altos de um double; o bit 0 divide por 100."""
    x = float(struct.unpack('<i', struct.pack('<I', v))[0] >> 2) if v & 2 else \
        struct.unpack('<d', struct.pack('<Q', (v & 0xFFFFFFFC) << 32))[0]
    return x / 100 if v & 1 else x


def eh_formato_data(fmt):
    s = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]|_.|\*.', '', (fmt or '').split(';')[0])
    return bool(re.search(r'[dmyhs]', s, re.I))


def _valor(x, fmt, f1904):
    if eh_formato_data(fmt):
        try:
            return (datetime(1904, 1, 1) if f1904 else datetime(1899, 12, 30)) + timedelta(days=x)
        except (OverflowError, ValueError):
            return x
    return int(x) if x.is_integer() and abs(x) < 1e15 else x          # como o openpyxl: o número inteiro vem int


def abas(dados):
    """[(nome, linhas)] das planilhas do livro; cada linha é uma lista de (valor, formato) desde a coluna A."""
    try:
        fluxo = _fluxo(dados, 'Workbook')
        if fluxo is None:
            raise XlsInvalido('sem o fluxo Workbook (Excel 5/95 ou não é planilha): salve como .xlsx')
        return _livro(fluxo)
    except struct.error:
        raise XlsInvalido('arquivo truncado') from None


def _livro(fluxo):
    regs = _Registros(fluxo, 0)
    tipo, bof = regs.proximo() or (None, b'')
    if tipo != BOF or len(bof) < 4 or struct.unpack_from('<H', bof)[0] != 0x0600:
        raise XlsInvalido('não é BIFF8 (Excel 97-2003)')
    formatos, xf_fmt, folhas, sst, f1904 = {}, [], [], [], False
    while (r := regs.proximo()) and r[0] != EOF:
        tipo, d = r
        if tipo == 0x002F:
            raise XlsInvalido('planilha protegida por senha')
        if tipo == 0x0022 and len(d) >= 2:                      # DATEMODE
            f1904 = struct.unpack_from('<H', d)[0] == 1
        elif tipo == 0x041E and len(d) >= 5:                    # FORMAT
            formatos[struct.unpack_from('<H', d)[0]] = _Pedacos([d[2:]]).texto()
        elif tipo == 0x00E0 and len(d) >= 4:                    # XF
            xf_fmt.append(struct.unpack_from('<H', d, 2)[0])
        elif tipo == 0x0085 and len(d) >= 8:                    # BOUNDSHEET: só planilha (não gráfico nem macro)
            pos, _, dt = struct.unpack_from('<IBB', d)
            if dt == 0:
                folhas.append((_Pedacos([d[6:]]).texto(cch_curto=True), pos))
        elif tipo == 0x00FC and len(d) >= 8:                    # SST: a tabela de textos
            p = regs.com_continuacoes(d)
            p.bytes(4)
            sst = [p.texto(rico=True) for _ in range(min(p.num('<I'), LIMITE_CELULAS))]

    def nome_fmt(i):
        if i == 0:
            return 'General'
        return formatos.get(i) or INTERNOS.get(i) or ('dd/mm/yyyy' if i in DATAS_INTERNAS else 'General')
    return [(nome, _folha(fluxo, pos, sst, [nome_fmt(i) for i in xf_fmt], f1904)) for nome, pos in folhas]


def _folha(fluxo, pos, sst, fmt, f1904):
    celulas = {}

    def por(rw, col, valor, ixfe):
        if len(celulas) >= LIMITE_CELULAS:
            raise XlsInvalido('planilha grande demais para uma NS')
        f = fmt[ixfe] if ixfe < len(fmt) else 'General'
        celulas[(rw, col)] = (_valor(valor, f, f1904) if isinstance(valor, float) else valor, f)

    regs = _Registros(fluxo, pos)
    if (regs.proximo() or (None,))[0] != BOF:
        raise XlsInvalido('aba sem o registro de início')
    pend = None                        # fórmula de texto: o valor vem no registro STRING seguinte
    while (r := regs.proximo()) and r[0] != EOF:
        tipo, d = r
        if tipo == 0x00BD and len(d) >= 12:                     # MULRK: vários números seguidos na linha
            rw, col = struct.unpack_from('<HH', d)
            for k in range((len(d) - 6) // 6):
                ixfe, v = struct.unpack_from('<HI', d, 4 + 6 * k)
                por(rw, col + k, _rk(v), ixfe)
            continue
        if tipo == 0x0207 and pend:                             # STRING: o texto da fórmula anterior
            por(pend[0], pend[1], regs.com_continuacoes(d).texto(), pend[2])
            pend = None
            continue
        if len(d) < 8 or tipo not in (0x0203, 0x027E, 0x00FD, 0x0204, 0x00D6, 0x0205, 0x0006):
            continue
        rw, col, ixfe = struct.unpack_from('<HHH', d)
        if tipo == 0x0203 and len(d) >= 14:                     # NUMBER
            por(rw, col, struct.unpack_from('<d', d, 6)[0], ixfe)
        elif tipo == 0x027E and len(d) >= 10:                   # RK
            por(rw, col, _rk(struct.unpack_from('<I', d, 6)[0]), ixfe)
        elif tipo == 0x00FD and len(d) >= 10:                   # LABELSST
            i = struct.unpack_from('<I', d, 6)[0]
            por(rw, col, sst[i] if i < len(sst) else '', ixfe)
        elif tipo in (0x0204, 0x00D6):                          # LABEL, RSTRING
            por(rw, col, regs.com_continuacoes(d[6:]).texto(), ixfe)
        elif tipo == 0x0205:                                    # BOOLERR
            por(rw, col, bool(d[6]) if d[7] == 0 else ERROS.get(d[6], '#ERRO'), ixfe)
        elif tipo == 0x0006 and len(d) >= 14:                   # FORMULA: o resultado guardado
            v = d[6:14]
            if v[6:8] != b'\xff\xff':
                por(rw, col, struct.unpack('<d', v)[0], ixfe)
            elif v[0] == 0:
                pend = (rw, col, ixfe)
            elif v[0] in (1, 2, 3):
                por(rw, col, bool(v[2]) if v[0] == 1 else ERROS.get(v[2], '#ERRO') if v[0] == 2 else '', ixfe)
    if not celulas:
        return []
    n_lin, n_col = max(r for r, _ in celulas) + 1, max(c for _, c in celulas) + 1
    if n_lin * n_col > 5 * LIMITE_CELULAS:
        raise XlsInvalido('planilha grande demais para uma NS')
    return [[celulas.get((r, c), (None, '')) for c in range(n_col)] for r in range(n_lin)]
