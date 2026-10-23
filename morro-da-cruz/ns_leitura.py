"""Leitura da NOTA DE SERVIÇO (NS) da Caesb em PDF: cabeçalho, grupos, linhas, segmentos, RESUMO e assinaturas, com as
contas que precisam fechar. Só lê: não grava nada (quem grava é notas_servico.py).

O PDF vem do Excel (modelo Caesb "NOTA DE SERVIÇO"): cabeçalho (NS nº, CONTRATO, FOLHA x de y, DATA, LOCALIZAÇÃO), linha
de título, bloco (TOPOGRAFIA…), tabela de estacas por grupo (rede, adutora), linhas de segmento "A ----> B = x metros"
entre as linhas de dados, NOTAS, RESUMO, TOTAL GERAL e assinaturas.
* Texto: pypdf no modo layout (a página girada, /Rotate 90, tem de ir para o conteúdo antes, senão sai vazio). Se o
  pdftotext existir, o PDF é lido de novo com ele e as duas leituras são comparadas pela impressão dos dados.
* Planilha da NS (opcional), .xlsx ou o .xls do Excel 97-2003 (planilha_xls.py): as células viram o mesmo texto em
  colunas e passam pelo mesmo leitor; a leitura da planilha confere a do PDF (dados diferentes = falha de leitura).
* Croqui em PDF com texto (opcional): o número da NS, o contrato e a data escritos nele são conferidos com os da nota.
* Colunas: a posição de uma célula VAZIA é decidida por âncoras. No pypdf a linha inteira desliza conforme o texto do
  elemento, então as âncoras são RELATIVAS ao método (V.C.A/MND) ou ao material (PEAD-160) da própria linha, aprendidas
  nas linhas completas. No pdftotext (e na planilha) as posições são fiéis e os rótulos do cabeçalho servem de âncora.
Protótipo e pesquisa: ferramentas/ns/ e docs/ns/04_leitor_da_ns_prototipo.md.
"""
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from datetime import date, datetime
from itertools import combinations
from statistics import median

import planilha_xls
import relogio as RL

VERSAO = "ns_leitura 1"
TOL = 0.011            # m: valores impressos com 2 casas
ESTACA_M = 20.0        # estaca Caesb = 20 m
LIMITE_PDF = 5 * 1024 * 1024
LIMITE_PLANILHA = 2 * 1024 * 1024
LIMITE_PAGINAS = 20

DEC = r'[-−]?(?:\d{1,3}(?:\.\d{3})+|\d+),\d+'
RX_DEC = re.compile(rf'^{DEC}$')
RX_NUMS = re.compile(rf'^{DEC}(?: {DEC})+$')                 # "2,07 1,40": colunas coladas por 1 espaço
RX_INT = re.compile(r'^\d+$')
RX_MET = re.compile(r'^(?:V\.?\s?C\.?\s?A\.?|M\.?\s?N\.?\s?D\.?)$', re.I)
MATERIAIS = r'PEAD|PVC(?:\s?DEFOFO|\s?PBA)?|DEFOFO|PRFV|FOFO|F[ºO°]\s?F[ºO°]|A[ÇC]O|PE|PP|RPVC|CONCRETO|MANILHA'
RX_MAT = re.compile(rf'^(?P<mat>{MATERIAIS})\s*[-/]?\s*(?:DN|DE|Ø|⌀|D=)?\s*(?P<dn>\d{{2,4}})(?:\s*mm)?$', re.I)
RX_MAT_DESC = re.compile(rf'(?P<mat>{MATERIAIS})\s*[-/]?\s*(?:DN|DE|Ø|⌀)?\s*(?P<dn>\d{{2,4}})\s*mm', re.I)
RX_ESTACA = re.compile(r'^\s*(?P<int>\d{1,4})\s*\+\s*(?P<fra>\d{1,2}(?:,\d+)?)(?=\s|$)')
RX_SETA = re.compile(r'-{2,}\s*>|[—–]+\s*>|=>|→')
RX_SEG = re.compile(rf'^\s*(?P<de>\S.*?)\s*(?:-+\s*>|[—–]+\s*>|=+>|→)\s*(?P<para>\S.*?)\s*=\s*(?P<m>{DEC}|\d+)'
                    r'\s*(?:m|metros?)?\.?\s*$', re.I)
RX_TOTAL = re.compile(rf'TOTAL\s+GERAL\s*[=:]?\s*(?P<v>{DEC})', re.I)
RX_UNID = re.compile(r'^(?:metros?|m|un|und|unid\.?|p[çc]s?\.?|pe[çc]as?)$', re.I)
RX_SUBCAB = re.compile(r'\bInteira\b|\bFra[çc][ãa]o\b|ACUMULADA', re.I)
RX_CAB_TAB = re.compile(r'\bESTACA\b|^\s*C\s?O\s?T\s?A\s?S\s*$')
RX_ROT_CAB = re.compile(r'N\.?\s?S\.?\s*n\s*[º°o]|CONTRATO\s*:|CONTRATADA\s*:|FOLHA\s*:|DATA\s*:|LOCALIZA[ÇC][ÃA]O\s*:', re.I)
VAZIOS = {'-', '–', '—', '--', 'N/A', 'NA', 'S/N', '*'}
NUMERICOS = ('dec', 'vazio', 'int')

CAMPOS_PRE = ('cota_terreno', 'cota_gi', 'profundidade')
CAMPOS_POS = ('dist_parcial', 'dist_acumulada', 'esc_boca', 'esc_fundo', 'visor', 'cruzeta')
ROTULOS_CAB = {'cota_terreno': r'TERRENO', 'cota_gi': r'INFERIOR DO|"GI"', 'profundidade': r'PROFUNDIDADE',
               'met': r'EXECUTIVO|M[ÉE]TODO', 'mat': r'"D" \(mm\)|MATERIAL', 'dist_parcial': r'PARCIAL',
               'dist_acumulada': r'ACUMULADA', 'esc_boca': r'BOCA', 'esc_fundo': r'FUNDO', 'visor': r'VISOR',
               'cruzeta': r'CRUZETA'}
MESES = {'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'set': 9, 'out': 10,
         'nov': 11, 'dez': 12}
# elementos da rede de água (06.1/06.2) e os nomes por extenso que a NS pode usar
ELEMENTOS = (('NO', r'N(?:O|\.)?', True), ('VRP', r'VRP', False), ('VM', r'VM|REGISTRO', True),
             ('MV', r'MV|MACROMEDIDOR', False), ('DF', r'DF|DESCARGA', False), ('VTF', r'VTF|VENTOSA', False),
             ('HID', r'HID|HIDRANTE', False), ('RG', r'RG', False))


class LeituraRecusada(ValueError):
    """Arquivo que não dá para ler como NS (não é PDF, sem camada de texto, protegido, grande demais)."""


# ------------------------------------------------------------------------------------------------ utilidades
def sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def norm_txt(s):
    return re.sub(r'[^A-Z0-9]+', ' ', sem_acento(s or '').upper()).strip()


def num_br(s):
    """'1.089,550' -> 1089.55 ; '17,32' -> 17.32 ; '0' -> 0.0 ; vazio/'-' -> None."""
    if s is None:
        return None
    s = s.strip().replace('−', '-')
    if not s or s in VAZIOS:
        return None
    if not re.fullmatch(DEC + r'|-?\d+', s):
        raise ValueError(f'número inválido: {s!r}')
    return float(s.replace('.', '').replace(',', '.'))


def data_iso(s):
    """'27-out-25' / '27/10/2025' / '27 de outubro de 2025' -> '2025-10-27' (None se não for data válida)."""
    if not s:
        return None
    t = sem_acento(s).lower().strip()
    m = (re.fullmatch(r'(\d{1,2})\s*[-/. ]\s*([a-z]{3,9}|\d{1,2})\.?\s*[-/. ]\s*(\d{4}|\d{2})', t)
         or re.fullmatch(r'(\d{1,2}) de ([a-z]+) de (\d{4})', t))
    if not m:
        return None
    d, mes, a = m.groups()
    mes = int(mes) if mes.isdigit() else MESES.get(mes[:3])
    a = int(a) + (2000 if len(a) == 2 else 0)
    try:
        return date(a, mes, int(d)).isoformat()
    except (TypeError, ValueError):
        return None


def norm_contrato(s):
    """'CT 10239/2026 Caesb × Ankara' -> '10239/2026' ; '9702/24' -> '9702/2024' (só número e ano)."""
    m = re.search(r'(\d{1,6})\s*/\s*(\d{4}|\d{2})\b', s or '')
    if not m:
        return None
    ano = m.group(2) if len(m.group(2)) == 4 else '20' + m.group(2)
    return f'{int(m.group(1))}/{ano}'


def _r(x, n=3):
    return None if x is None else round(x + 0.0, n)


def chave_elemento(texto):
    """Chave curta para casar o elemento da NS com o nó da 06.1, a mesma dos dois lados: 'Zona03_PB08_Rede_NÓ9.1',
    'NÓ 9.1', 'N 9-1' e 'Nó-09.1' -> 'NO9.1'; 'Zona03_PB08_CH_VRP-15', 'VRP 15' e 'VRP-015' -> 'VRP-15'; 'REGISTRO 5.4'
    -> 'VM-5.4'; 'VENTOSA 22' -> 'VTF-22'; 'DESCARGA 6' -> 'DF-6'. Vale a sigla que aparece primeiro no texto
    ('NÓ 9.1 (TÊ - DERIV. P/ VRP-15)' -> 'NO9.1'). Sem sigla conhecida: o texto antes de ' - ' ou '(' normalizado."""
    if not texto:
        return None
    s = sem_acento(texto).upper()
    achados = []
    for sigla, rx, ponto in ELEMENTOS:
        num = r'(\d+)\s*[.\-]\s*(\d+)(?![\d])' if ponto and sigla == 'NO' else r'(\d+)(?:\s*[.\-]\s*(\d+))?(?![\d])' \
            if ponto else r'0*(\d+)(?![\d.])'
        for m in re.finditer(rf'(?<![A-Z])(?:{rx})\s*[-.]?\s*{num}', s):
            a = int(m.group(1))
            b = m.group(2) if m.lastindex and m.lastindex >= 2 else None
            v = f'{a}.{int(b)}' if b is not None else f'{a}'
            achados.append((m.start(), -len(m.group(0)), f'NO{v}' if sigla == 'NO' else f'{sigla}-{v}'))
    if achados:
        return min(achados)[2]
    base = re.split(r'\s+-\s+|\(', s)[0]
    return norm_txt(base) or None


def contexto_zona_pb(*textos):
    """Zona/PB citados no texto (na 06.1 o nome do nó só é único dentro de zona + PB + rede)."""
    t = sem_acento(' '.join(x for x in textos if x)).upper()
    z = re.search(r'\bZONA\s*[-_ ]?\s*0*(\d{1,2})\b', t)
    pb = re.search(r'\bPB\s*[-_ ]?\s*0*(\d{1,2})\b', t)
    zona = f'Zona{int(z.group(1)):02d}' if z else 'ADUTORA' if re.search(r'\bADUTORA\b', t) else None
    return {'zona': zona, 'pb': f'PB{int(pb.group(1)):02d}' if pb else None}


# ------------------------------------------------------------------------------------------------ tokens
class Tok:
    __slots__ = ('a', 'b', 's', 'tipo')

    def __init__(self, a, b, s):
        self.a, self.b, self.s = a, b, s
        self.tipo = ('dec' if RX_DEC.match(s) else 'vazio' if s in VAZIOS else 'met' if RX_MET.match(s)
                     else 'mat' if RX_MAT.match(s) else 'int' if RX_INT.match(s) else 'txt')

    @property
    def c(self):
        return (self.a + self.b) / 2

    def __repr__(self):
        return f'{self.s}@{self.a}'


def tokens(linha, ini=0):
    """Células = trechos separados por 2+ espaços (posição em caracteres preservada). Também separa números
    colados por 1 espaço ("2,07 1,40") e método colado ao material ("V.C.A PEAD-160")."""
    out = []
    for m in re.finditer(r'\S+(?: \S+)*', linha[ini:]):
        a, s = m.start() + ini, m.group()
        mm = re.match(r'^(V\.?C\.?A\.?|MND|M\.N\.D\.?) (\S.*)$', s, re.I)
        if RX_NUMS.match(s):
            out += [Tok(a + p.start(), a + p.end(), p.group()) for p in re.finditer(r'\S+', s)]
        elif mm and RX_MAT.match(mm.group(2)):
            out += [Tok(a, a + mm.end(1), mm.group(1)), Tok(a + mm.start(2), a + mm.end(2), mm.group(2))]
        else:
            out.append(Tok(a, a + len(s), s))
    return out


# ------------------------------------------------------------------------------------------------ extração
def _pypdf():
    try:
        import pypdf
    except ImportError:
        raise LeituraRecusada('A leitura do PDF precisa da biblioteca pypdf (pip install "pypdf>=6,<7").') from None
    logging.getLogger('pypdf').setLevel(logging.ERROR)
    return pypdf


def _abrir_pdf(dados):
    if not dados or dados[:5] != b'%PDF-':
        raise LeituraRecusada('O arquivo não é um PDF.')
    if len(dados) > LIMITE_PDF:
        raise LeituraRecusada(f'PDF da NS maior que {LIMITE_PDF // 2 ** 20} MB: envie o PDF gerado do Excel, sem imagens grandes.')
    pypdf = _pypdf()
    try:
        r = pypdf.PdfReader(io.BytesIO(dados))
        if r.is_encrypted and not r.decrypt(''):
            raise LeituraRecusada('PDF protegido por senha: envie o PDF sem proteção.')
        n = len(r.pages)
    except LeituraRecusada:
        raise
    except Exception as e:  # noqa: BLE001 — PDF quebrado: recusa com a mensagem, sem derrubar o servidor
        raise LeituraRecusada(f'PDF ilegível ({type(e).__name__}).') from None
    if n > LIMITE_PAGINAS:
        raise LeituraRecusada(f'PDF com {n} páginas: a NS tem no máximo {LIMITE_PAGINAS} folhas.')
    return pypdf, r


def extrair_paginas(dados, extrator='auto'):
    """Texto de cada página do PDF (bytes) e de onde veio. 'auto' = pypdf; sem texto, pdftotext (se existir)."""
    meta = {'sha256': hashlib.sha256(dados).hexdigest(), 'bytes': len(dados)}
    pypdf, r = _abrir_pdf(dados)
    if extrator in ('auto', 'pypdf'):
        paginas, imagens, folhas = [], [], r.pages
        if any(pg.get('/Rotate') for pg in folhas):
            folhas = pypdf.PdfWriter(clone_from=r).pages   # girar o conteúdo exige a página num writer (pypdf 6+)
        for pg in folhas:
            if pg.get('/Rotate'):
                pg.transfer_rotation_to_content()      # sem isso o modo layout devolve vazio (NS assinada: /Rotate 90)
            paginas.append(pg.extract_text(extraction_mode='layout') or '')
            try:
                imagens.append(len(pg.images))
            except Exception:  # noqa: BLE001 — imagem que o pypdf não decodifica
                imagens.append(None)
        md = r.metadata or {}
        meta.update(extrator=f'pypdf {pypdf.__version__} layout', posicoes_fieis=False, paginas=len(r.pages),
                    produtor=md.get('/Producer'), titulo_pdf=md.get('/Title'), imagens_por_pagina=imagens)
        if any(p.strip() for p in paginas):
            return paginas, meta
        meta['aviso_extrator'] = 'pypdf não achou texto'
    if extrator in ('auto', 'pdftotext') and shutil.which('pdftotext'):
        with tempfile.TemporaryDirectory(prefix='ns_') as tmp:
            caminho = os.path.join(tmp, 'ns.pdf')
            with open(caminho, 'wb') as f:
                f.write(dados)
            out = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', caminho, '-'], capture_output=True,
                                 text=True, timeout=60).stdout
        paginas = out.split('\f')
        if paginas and not paginas[-1].strip():
            paginas.pop()
        meta.update(extrator='pdftotext -layout', posicoes_fieis=True, paginas=len(r.pages))
        if any(p.strip() for p in paginas):
            return paginas, meta
    raise LeituraRecusada('PDF sem camada de texto (digitalizado ou impresso como imagem): envie o PDF gerado do '
                          'Excel, não a foto ou a digitalização da NS.')


def _texto_celula(v, formato):
    if v is None:
        return ''
    if isinstance(v, (datetime, date)):
        return v.strftime('%d/%m/%Y')
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        casas = len(formato.split('.', 1)[1].split(';')[0].rstrip('_)%" ')) if '.' in (formato or '') else None
        if isinstance(v, int) and not casas:
            return str(v)
        if casas is None:                              # formato Geral: as casas que o Excel mostraria
            casas = max(2, len(f'{v:.6f}'.rstrip('0').split('.')[1]))
        txt = f'{v:,.{min(max(casas, 1), 6)}f}'
        return txt.replace(',', '§').replace('.', ',').replace('§', '.')
    return re.sub(r'\s+', ' ', str(v)).strip()


def tipo_planilha(dados):
    """'.xlsx', '.xls' ou None."""
    if dados[:4] == b'PK\x03\x04':
        return '.xlsx'
    return '.xls' if dados[:8] == planilha_xls.ASSINATURA else None


def _abas_xlsx(dados):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(dados), data_only=True, read_only=True)
    except Exception as e:  # noqa: BLE001
        raise LeituraRecusada(f'Planilha ilegível ({type(e).__name__}).') from None
    try:
        return [[[(c.value, getattr(c, 'number_format', '')) for c in row] for row in ws.iter_rows()] for ws in wb.worksheets]
    finally:
        wb.close()


def ler_planilha(dados):
    """Páginas de texto da planilha da NS, .xlsx ou .xls (uma por aba com conteúdo de NS), com as células em colunas
    fixas, como o pdftotext: passam pelo mesmo leitor do PDF."""
    tipo = tipo_planilha(dados or b'')
    if not tipo:
        raise LeituraRecusada('A planilha da NS precisa ser a do Excel (.xlsx ou .xls).')
    if len(dados) > LIMITE_PLANILHA:
        raise LeituraRecusada(f'Planilha da NS maior que {LIMITE_PLANILHA // 2 ** 20} MB.')
    if tipo == '.xlsx':
        abas = _abas_xlsx(dados)
    else:
        try:
            abas = [linhas for _, linhas in planilha_xls.abas(dados)]
        except planilha_xls.XlsInvalido as e:
            raise LeituraRecusada(f'Planilha .xls ilegível: {e}.') from None
    paginas = []
    for aba in abas:
        linhas = [[_texto_celula(v, f or '') for v, f in row] for row in aba]
        linhas = [l for l in linhas if any(l)]
        if not any(re.search(r'N\.?\s?S\.?\s*n\s*[º°o]|NOTA\s+DE\s+SERVI', ' '.join(l), re.I) for l in linhas):
            continue
        n = max(len(l) for l in linhas)
        sozinha = lambda l: sum(1 for c in l if c) == 1      # título, segmento, rótulo: uma célula só na linha
        larg = [max((len(l[j]) for l in linhas if j < len(l) and not sozinha(l)), default=0) for j in range(n)]
        # na planilha a célula do elemento nunca vem quebrada em 2 linhas (isso é coisa da impressão): a linha de uma
        # célula só começa na coluna 0, para não ser tomada como continuação do elemento da linha de baixo
        paginas.append('\n'.join(next(c for c in l if c) if sozinha(l) else
                                 ''.join(c.ljust(larg[j] + 3) if j + 1 < len(l) else c for j, c in enumerate(l)
                                         if larg[j] or c).rstrip() for l in linhas))
    if not paginas:
        raise LeituraRecusada('A planilha não tem nenhuma aba com a NS (cabeçalho "NS nº").')
    return paginas


# ------------------------------------------------------------------------------------------------ cabeçalho
def _campo(linhas, rot, val):
    """Valor do rótulo na mesma linha, depois ('FOLHA:  01 de 01') ou antes ('01 de 01FOLHA:', NS assinada/pypdf)."""
    for ln in linhas:
        m = re.search(rf'{rot}[ \t]*:?[ \t]*(?P<v>{val})', ln, re.I)
        if m:
            return m.group('v').strip()
        m = re.search(rf'(?P<v>{val})[ \t]*{rot}', ln, re.I)
        if m:
            return m.group('v').strip()
    return None


def _cabecalho(linhas):
    cab = {'numero': _campo(linhas, r'(?:N\.?\s?S\.?|NOTA\s+DE\s+SERVI[ÇC]O)\s*N\s*[º°o]?\s*\.?\s*:', r'\d{1,5}[A-Z]?'),
           'contrato': _campo(linhas, r'CONTRATO\s*:', r'(?:CT\s*)?\d{1,6}\s*/\s*\d{2,4}')}
    folha = _campo(linhas, r'FOLHA\s*:', r'\d{1,3}\s*de\s*\d{1,3}')
    if folha:
        a, b = re.findall(r'\d+', folha)
        cab['folha'], cab['total_folhas'] = int(a), int(b)
    cab['data_texto'] = _campo(linhas, r'DATA\s*:', r'\d{1,2}\s*[-/.]\s*(?:[A-Za-zÇç]{3,9}|\d{1,2})\.?\s*[-/.]\s*\d{2,4}')
    for ln in linhas:
        m = re.search(r'CONTRATADA\s*:\s*(?P<v>\S.*?)(?:\s{2,}|$)', ln)
        if m and 'contratada' not in cab:
            cab['contratada'] = m.group('v')
        m = re.search(r'LOCALIZA[ÇC][ÃA]O\s*:\s*(?P<v>\S.*?)(?:\s{2,}|$)', ln, re.I)
        if m and 'localizacao' not in cab:
            cab['localizacao'] = m.group('v')
        if 'orgao' not in cab and re.search(r'\bCaesb\b', ln):
            cab['orgao'] = 'Caesb'
    return cab


# ------------------------------------------------------------------------------------------------ leitura
class _Bruta:
    """Linha de dados lida, antes de decidir em que coluna cai cada número."""

    def __init__(self, pagina, n, linha, m_est):
        self.pagina, self.n, self.texto = pagina, n, linha
        self.est_int = int(m_est.group('int')) if m_est else None
        self.est_fra = num_br(m_est.group('fra')) if m_est else None
        self.fim_estaca = m_est.end() if m_est else 0
        toks = tokens(linha, self.fim_estaca)
        i = 0
        while i < len(toks) and toks[i].tipo in ('txt', 'int'):
            i += 1
        self.elem, resto = toks[:i], toks[i:]
        self.met = next((t for t in resto if t.tipo == 'met'), None)
        self.mat = next((t for t in resto if t.tipo == 'mat' and (self.met is None or t.a > self.met.a)), None)
        ref_pre, ref_pos = self.met or self.mat, self.mat or self.met
        self.pre, self.pos, self.obs, self.estranhos, self.semref = [], [], [], [], []
        for t in resto:
            if t is self.met or t is self.mat:
                continue
            if t.tipo in NUMERICOS and not self.obs:
                if ref_pre is None:
                    self.semref.append(t)
                elif t.a < ref_pre.a:
                    self.pre.append(t)
                elif t.a > ref_pos.a:
                    self.pos.append(t)
                else:
                    self.estranhos.append(t)
            elif (ref_pos is not None and t.a > ref_pos.a) or (ref_pos is None and self.semref):
                self.obs.append(t)                   # texto depois dos números = observação
            else:
                self.estranhos.append(t)
        self.elem_antes, self.elem_depois = [], []   # célula do elemento quebrada em 2+ linhas
        nums = self.pre + self.pos + self.semref + [x for x in (self.met, self.mat) if x]
        self.prim_num = min((t.a for t in nums), default=len(linha))

    def completa(self):
        return len(self.pre) == 3 and len(self.pos) == 6 and self.met and self.mat and not self.estranhos

    def aceita_continuacao(self, tk):
        """Texto de 1 célula, dentro da coluna do elemento (depois da estaca, antes do 1º número). O elemento da
        linha pode estar vazio: no pdftotext a 1ª parte da célula quebrada sai ACIMA da linha dos números."""
        return len(tk) == 1 and tk[0].a >= self.fim_estaca and tk[0].b < self.prim_num


def _alinhar(toks, campos, anc, ref):
    """Distribui k tokens em n campos (k <= n), preservando a ordem, pela menor distância às âncoras."""
    k, n = len(toks), len(campos)
    if k == n:
        return dict(zip(campos, toks)), None
    if k > n:
        return dict(zip(campos, toks[:n])), 'sobra'
    if anc and ref is not None and all(anc.get(c) is not None for c in campos):
        rel = [t.c - ref.c for t in toks]
        custos = sorted((sum(abs(rel[i] - anc[campos[s]]) for i, s in enumerate(comb)), comb)
                        for comb in combinations(range(n), k))
        melhor = custos[0][1]
        ambiguo = len(custos) > 1 and custos[1][0] - custos[0][0] < 2.0
        return {campos[s]: toks[i] for i, s in enumerate(melhor)}, 'ambiguo' if ambiguo else 'ancora'
    return dict(zip(campos, toks)), 'ordem'


def _alinhar_livre(toks, campos, anc):
    """Sem token de referência (sem método nem material): procura o deslocamento da linha junto com a
    distribuição; anc = deslocamentos de todos os campos no mesmo referencial (relativos ao método)."""
    k, n = len(toks), len(campos)
    if k > n or not anc or any(anc.get(c) is None for c in campos):
        return None, None
    custos = []
    for comb in combinations(range(n), k):
        d = [toks[i].c - anc[campos[s]] for i, s in enumerate(comb)]
        s0 = median(d)
        custos.append((sum(abs(x - s0) for x in d), comb))
    custos.sort()
    melhor = custos[0][1]
    ambiguo = len(custos) > 1 and custos[1][0] - custos[0][0] < 2.0
    return {campos[s]: toks[i] for i, s in enumerate(melhor)}, 'ambiguo' if ambiguo else 'ancora'


def _ancoras(brutas, linhas_cab_tabela, posicoes_fieis):
    """Âncoras relativas {'pre@met': {campo: deslocamento}, 'pos@mat': {...}, ...} e de onde vieram."""
    comp = [b for b in brutas if b.completa()]
    anc = {}
    if comp:
        for chave, campos, lista in (('pre', CAMPOS_PRE, lambda b: b.pre), ('pos', CAMPOS_POS, lambda b: b.pos)):
            for refn in ('met', 'mat'):
                anc[f'{chave}@{refn}'] = {c: median(lista(b)[i].c - getattr(b, refn).c for b in comp)
                                          for i, c in enumerate(campos)}
        return anc, f'linhas completas ({len(comp)})'
    if posicoes_fieis and linhas_cab_tabela:
        pos = {}
        for ln in linhas_cab_tabela:
            for campo, rx in ROTULOS_CAB.items():
                m = re.search(rx, ln)
                if m and campo not in pos:
                    pos[campo] = (m.start() + m.end()) / 2
        if 'met' in pos and 'mat' in pos:
            for chave, campos in (('pre', CAMPOS_PRE), ('pos', CAMPOS_POS)):
                for refn in ('met', 'mat'):
                    anc[f'{chave}@{refn}'] = {c: (pos[c] - pos[refn]) if c in pos else None for c in campos}
            return anc, 'rótulos do cabeçalho'
    return {}, 'nenhuma (ordem da esquerda para a direita)'


def _eh_papeis(s, seguintes=()):
    """Linha dos papéis das assinaturas ("TOPOGRAFIA:  CONSTRUTORA ANKARA  Fiscalização: CONCREMAT ...").
    Não confundir com o cabeçalho "CONTRATADA: CONSTRUTORA ANKARA ENGENHARIA LTDA"."""
    if re.search(r'Fiscaliza', s, re.I) or re.match(r'^(TOPOGRAFIA|CADASTRO|TOPÓGRAFO|ENCARREGADO|SUPERVISOR)\s*:', s, re.I):
        return True
    prox = [x.strip() for x in seguintes if x.strip()][:2]
    return len(prox) == 2 and bool(re.match(r'^Eng', prox[0], re.I)) and bool(re.match(r'^CREA', prox[1], re.I))


def parse_texto(paginas, meta=None):
    """Texto das folhas -> NS (dicionário) com as falhas de leitura e os avisos; as contas ficam em verificar()."""
    meta = dict(meta or {})
    avisos = []      # leitura que merece conferência, sem perda de dado
    falhas = []      # leitura com possível perda/troca de dado (vira ERRO E06)
    cabs, grupos, notas, resumo, total = [], [], [], [], None
    assin_linhas, cab_tabela_linhas = [], []
    titulo = bloco = None
    for p, texto in enumerate(paginas, 1):
        linhas = texto.splitlines()
        i_cab = next((i for i, l in enumerate(linhas) if RX_CAB_TAB.search(l)), None)
        i_row1 = next((i for i, l in enumerate(linhas) if RX_ESTACA.match(l) and (i_cab is None or i > i_cab)), None)
        lim = i_row1 if i_row1 is not None else len(linhas)
        i_sub = max((i for i in range(lim) if RX_SUBCAB.search(linhas[i])), default=None)
        i_rot = max((i for i in range(lim) if RX_ROT_CAB.search(linhas[i])), default=-1)
        cab = _cabecalho(linhas[: i_cab if i_cab is not None else lim])
        cab['pagina'] = p
        cabs.append(cab)
        if i_cab is not None:
            fim_cab = i_sub if i_sub is not None else i_cab
            cab_tabela_linhas += linhas[i_cab: fim_cab + 1]
            if p == 1:   # título e bloco: linhas entre LOCALIZAÇÃO/DATA e o cabeçalho da tabela
                livres = [l.strip() for l in linhas[i_rot + 1: i_cab] if l.strip()]
                livres = [l for l in livres if not re.fullmatch(r'C\s?O\s?T\s?A\s?S', l)]
                if livres:
                    titulo = livres[0]
                    if len(livres) > 1 and len(livres[-1]) <= 40 and not re.search(r'\d', livres[-1]):
                        bloco = livres[-1]
        else:
            fim_cab = i_rot           # folha sem cabeçalho de tabela: começa depois dos rótulos (NS nº, DATA...)
        repetidos = {norm_txt(titulo), norm_txt(bloco)} - {''}
        estado = 'tabela' if (i_cab is not None or i_row1 is not None) else 'fora'
        grupo_atual = grupos[-1] if grupos else None
        pend = None                   # (nº da linha, texto) de título de grupo ainda não confirmado
        j = fim_cab + 1
        while j < len(linhas):
            ln, j = linhas[j], j + 1  # j passa a ser o nº (1-based) desta linha
            s = ln.strip()
            if not s:
                continue
            novo = None
            if estado != 'assinaturas' and _eh_papeis(s, linhas[j:j + 6]):
                novo = 'assinaturas'
            elif re.match(r'^NOTAS\b', s, re.I):
                novo = 'notas'
            elif re.match(r'^RESUMO\b', s, re.I):
                novo = 'resumo'
            mt = RX_TOTAL.search(s)
            if mt:
                novo = 'pos_total'
            if novo:
                if pend is not None:
                    avisos.append(f'p{p} l{pend[0]}: texto solto na tabela, sem linhas de dados: {pend[1][:80]!r}')
                    pend = None
                estado = novo
                if mt:
                    total = num_br(mt.group('v'))
                if novo in ('notas', 'resumo', 'pos_total'):
                    continue
            if estado == 'assinaturas':
                assin_linhas.append(ln)
                continue
            if estado == 'notas':
                tk = tokens(ln)
                if len(tk) >= 2:
                    txt = ' '.join(t.s for t in tk[1:])
                    q = re.search(r'"([^"]+)"', txt)
                    notas.append({'elemento': tk[0].s, 'chave': chave_elemento(tk[0].s),
                                  'tipo': q.group(1) if q else txt, 'texto': txt, 'pagina': p})
                else:
                    notas.append({'elemento': None, 'chave': None, 'tipo': None, 'texto': s, 'pagina': p})
                continue
            if estado == 'resumo':
                resumo.append(_linha_resumo(ln, p, avisos))
                continue
            if estado != 'tabela':
                avisos.append(f'p{p} l{j}: linha fora de bloco ignorada: {s[:80]!r}')
                continue
            if norm_txt(s) in repetidos and i_cab is None:
                continue                                       # título repetido em folha sem cabeçalho de tabela
            # ---------------- tabela: linha de dados
            m_est = RX_ESTACA.match(ln)
            if m_est or sum(1 for t in tokens(ln) if t.tipo == 'dec') >= 3:
                b = _Bruta(p, j, ln, m_est)
                if not m_est:
                    falhas.append(f'p{p} l{j}: linha de dados sem estaca: {s[:80]!r}')
                if b.estranhos:
                    falhas.append(f'p{p} l{j}: células não esperadas {[t.s for t in b.estranhos]} em {s[:60]!r}')
                if pend is not None:
                    tk = tokens(linhas[pend[0] - 1])
                    if pend[0] == j - 1 and b.aceita_continuacao(tk):
                        b.elem_antes.append(pend[1])
                        avisos.append(f'p{p} l{j}: elemento em 2 linhas juntado: {pend[1]!r} + ...')
                    else:
                        grupo_atual = _novo_grupo(grupos, pend[1], p, avisos)
                    pend = None
                if grupo_atual is None:
                    grupo_atual = _novo_grupo(grupos, None, p, avisos)
                    avisos.append(f'p{p} l{j}: linhas de dados antes de qualquer título de grupo')
                elif grupo_atual['pagina_fim'] < p:
                    avisos.append(f'p{p}: grupo {grupo_atual["titulo"]!r} continua da folha anterior')
                grupo_atual['pagina_fim'] = p
                grupo_atual['itens'].append(('linha', b))
                continue
            # ---------------- segmento "A ----> B = x metros"
            m_seg = RX_SEG.match(ln)
            if m_seg:
                if pend is not None:
                    grupo_atual = _novo_grupo(grupos, pend[1], p, avisos)
                    pend = None
                if grupo_atual is None:
                    grupo_atual = _novo_grupo(grupos, None, p, avisos)
                n_lin = sum(1 for k, _ in grupo_atual['itens'] if k == 'linha')
                grupo_atual['itens'].append(('seg', {'de': m_seg.group('de').strip(), 'para': m_seg.group('para').strip(),
                                                     'metros': num_br(m_seg.group('m')), 'apos': n_lin - 1,
                                                     'pagina': p, 'linha_txt': j}))
                continue
            if RX_SETA.search(ln):
                falhas.append(f'p{p} l{j}: segmento sem "= x metros": {s[:80]!r}')
                continue
            # ---------------- texto: continuação do elemento da linha de cima, ou título de grupo
            ult = grupo_atual['itens'][-1] if grupo_atual and grupo_atual['itens'] else None
            tk = tokens(ln)
            if ult and ult[0] == 'linha' and ult[1].pagina == p and ult[1].n == j - 1 and ult[1].aceita_continuacao(tk):
                ult[1].elem_depois.append(s)
                avisos.append(f'p{p} l{j}: elemento em 2 linhas juntado: ... + {s!r}')
                continue
            if pend is not None and pend[0] >= j - 2:
                pend = (j, pend[1] + ' ' + s)                  # título em 2 linhas
            else:
                if pend is not None:
                    avisos.append(f'p{p} l{pend[0]}: texto solto na tabela, sem linhas de dados: {pend[1][:80]!r}')
                pend = (j, s)
        if pend is not None:
            avisos.append(f'p{p} l{pend[0]}: texto solto no fim da folha: {pend[1][:80]!r}')

    brutas = [b for g in grupos for k, b in g['itens'] if k == 'linha']
    anc, origem_anc = _ancoras(brutas, cab_tabela_linhas, bool(meta.get('posicoes_fieis')))
    out_grupos = []
    for g in grupos:
        linhas_g = [_montar_linha(it, anc, avisos, falhas) for k, it in g['itens'] if k == 'linha']
        segs = [it for k, it in g['itens'] if k == 'seg']
        if not linhas_g:
            avisos.append(f'grupo {g["titulo"]!r} sem linhas de dados: descartado')
            continue
        out_grupos.append({'titulo': g['titulo'], 'pagina': g['pagina'], 'linhas': linhas_g, 'segmentos': segs})
    for g in out_grupos:
        _completar_grupo(g, out_grupos, avisos)
    cab = dict(cabs[0]) if cabs else {}
    cab.pop('pagina', None)
    cab['data'] = data_iso(cab.get('data_texto'))
    cab['numero_int'] = int(re.sub(r'\D', '', cab['numero'])) if cab.get('numero') else None
    if cab.get('numero') is None and meta.get('titulo_pdf'):
        m = re.search(r'N\.?\s*S\.?\s*0*(\d+)', meta['titulo_pdf'])
        if m:
            cab['numero'], cab['numero_int'] = m.group(1).zfill(3), int(m.group(1))
            avisos.append('número da NS lido do título do arquivo PDF (não achado no cabeçalho)')
    cab['titulo'], cab['bloco'] = titulo, bloco
    for r in resumo:
        r['grupo'] = _grupo_do_resumo(r, out_grupos)
    ns = {'cabecalho': cab, 'folhas': cabs, 'grupos': out_grupos, 'notas': notas, 'resumo': resumo,
          'total_geral': total, 'assinaturas': _assinaturas(assin_linhas, avisos), 'avisos': avisos,
          'falhas_leitura': falhas, 'colunas': {'ancoras': origem_anc}, 'fonte': meta, 'leitor': VERSAO}
    ns['impressao_dados'] = impressao_dados(ns)
    return ns


def _novo_grupo(grupos, titulo, p, avisos):
    if titulo is not None and grupos:
        ult = grupos[-1]
        base = re.sub(r'\(?\s*CONT(?:INUA[ÇC][ÃA]O|\.)\s*\)?', '', titulo, flags=re.I).strip()
        if ult['titulo'] and norm_txt(base) == norm_txt(ult['titulo']) and ult['pagina_fim'] < p:
            avisos.append(f'p{p}: título {titulo!r} repete o grupo da folha anterior: mesma lista')
            return ult
    g = {'titulo': titulo, 'pagina': p, 'pagina_fim': p, 'itens': []}
    grupos.append(g)
    return g


def _montar_linha(b, anc, avisos, falhas):
    incerto = []
    if b.semref:
        campos = CAMPOS_PRE + CAMPOS_POS
        anc_met = {**(anc.get('pre@met') or {}), **(anc.get('pos@met') or {})}
        m, modo = _alinhar_livre(b.semref, campos, anc_met)
        if m is None:
            m, modo = _alinhar(b.semref, campos, None, None)
        pre, pos = {c: m.get(c) for c in CAMPOS_PRE}, {c: m.get(c) for c in CAMPOS_POS}
        incerto += [c for c in campos if m.get(c) is not None] if modo != 'ancora' else []
        avisos.append(f'p{b.pagina} l{b.n}: linha sem método nem material: números por {modo} (conferir no PDF)')
    else:
        pre, modo1 = _alinhar(b.pre, CAMPOS_PRE, anc.get('pre@met' if b.met else 'pre@mat'), b.met or b.mat)
        pos, modo2 = _alinhar(b.pos, CAMPOS_POS, anc.get('pos@mat' if b.mat else 'pos@met'), b.mat or b.met)
        for modo, toks, campos, mapa in ((modo1, b.pre, CAMPOS_PRE, pre), (modo2, b.pos, CAMPOS_POS, pos)):
            if modo in ('ordem', 'ambiguo', 'sobra'):
                incerto += [c for c in campos if c in mapa]
                (falhas if modo == 'sobra' else avisos).append(
                    f'p{b.pagina} l{b.n}: {len(toks)} número(s) para {len(campos)} colunas {"/".join(campos)}: '
                    f'posição por {modo} (conferir no PDF)')
    mat = RX_MAT.match(b.mat.s) if b.mat else None
    elem = ' '.join(b.elem_antes + [t.s for t in b.elem] + b.elem_depois) or None

    def val(d, c):
        try:
            return num_br(d[c].s) if d.get(c) is not None else None
        except ValueError:
            falhas.append(f'p{b.pagina} l{b.n}: {c} ilegível: {d[c].s!r}')
            return None

    d = {'pagina': b.pagina, 'linha_txt': b.n,
         'estaca_inteira': b.est_int, 'estaca_fracao': _r(b.est_fra),
         'estaca_m': _r(b.est_int * ESTACA_M + b.est_fra) if b.est_int is not None else None,
         'elemento': elem, 'chave': chave_elemento(elem)}
    d.update({c: _r(val(pre, c)) for c in CAMPOS_PRE})
    d['metodo'] = ('MND' if 'N' in b.met.s.upper() else 'VCA') if b.met else None
    d['material'] = re.sub(r'\s+', ' ', mat.group('mat').upper()) if mat else None
    d['dn_mm'] = int(mat.group('dn')) if mat else None
    d['material_texto'] = b.mat.s if b.mat else None
    d.update({c: _r(val(pos, c)) for c in CAMPOS_POS})
    d['obs'] = ' '.join(t.s for t in b.obs) or None
    if incerto:
        d['incerto'] = incerto
    return d


def _linha_resumo(ln, p, avisos):
    desc = qtd = unid = None
    textos = []
    for t in tokens(ln):
        if desc is None and t.tipo == 'txt' and re.match(
                r'^(TUBO|TUBULA|REDE|ADUTORA|RAMAL|PEAD|PVC|CONEX|REGISTRO|PE[ÇC]A)', t.s, re.I):
            desc = t.s
        elif t.tipo == 'dec' and qtd is None:
            qtd = num_br(t.s)
        elif RX_UNID.match(t.s):
            unid = t.s
        elif qtd is None and (m := re.match(rf'^(?P<v>{DEC})\s*(?P<u>metros?|m)$', t.s, re.I)):
            qtd, unid = num_br(m.group('v')), m.group('u')
        elif qtd is None and (m := re.match(rf'^(?P<t>.*?[^\d.,\s])\s*(?P<v>{DEC})$', t.s)):
            textos.append(m.group('t'))                      # NS assinada/pypdf: "...(NÓ6.1 - NÓ9.1)573,97"
            qtd = num_br(m.group('v'))
            avisos.append(f'p{p}: RESUMO com valor colado ao texto: {t.s[-40:]!r}')
        else:
            textos.append(t.s)
    if desc is None and textos:
        desc = textos.pop(0)
    md = RX_MAT_DESC.search(desc or '')
    u = (unid or '').lower()
    return {'descricao': desc, 'material': md.group('mat').upper() if md else None,
            'dn_mm': int(md.group('dn')) if md else None, 'quantidade': qtd, 'unidade': unid,
            'metros': qtd if u.startswith('m') or not u else None, 'coletor': ' '.join(textos) or None, 'pagina': p}


def _grupo_do_resumo(r, grupos):
    alvo = norm_txt(r.get('coletor'))
    if alvo:
        exatos = [i for i, g in enumerate(grupos) if norm_txt(g['titulo']) == alvo]
        if len(exatos) == 1:
            return exatos[0]
        cont = [i for i, g in enumerate(grupos) if norm_txt(g['titulo']) and
                (f' {norm_txt(g["titulo"])} ' in f' {alvo} ' or f' {alvo} ' in f' {norm_txt(g["titulo"])} ')]
        if len(cont) == 1:
            return cont[0]
    cand = [i for i, g in enumerate(grupos) if r.get('dn_mm') and g.get('dn_mm') == r['dn_mm']
            and g.get('material') == r.get('material')]
    return cand[0] if len(cand) == 1 else None


def _completar_grupo(g, grupos, avisos):
    ls = g['linhas']
    mats = {(l['material'], l['dn_mm']) for l in ls if l['material']}
    g['material'], g['dn_mm'] = (next(iter(mats)) if len(mats) == 1 else (None, None))
    if len(mats) > 1:
        avisos.append(f'grupo {g["titulo"]!r}: mais de um material/DN: {sorted(map(str, mats))}')
    g['soma_parcial'] = _r(sum(l['dist_parcial'] or 0 for l in ls))
    g['extensao'] = None
    if ls[0]['dist_acumulada'] is not None and ls[-1]['dist_acumulada'] is not None:
        g['acumulada_ini'], g['acumulada_fim'] = ls[0]['dist_acumulada'], ls[-1]['dist_acumulada']
        g['extensao'] = _r(ls[-1]['dist_acumulada'] - ls[0]['dist_acumulada'])
    g['continua_de'] = None
    if (ls[0]['dist_acumulada'] or 0) > TOL:
        for gi, outro in enumerate(grupos):
            if outro is g:
                break
            for li, l in enumerate(outro['linhas']):
                if l['chave'] == ls[0]['chave'] and l['dist_acumulada'] is not None \
                        and abs(l['dist_acumulada'] - ls[0]['dist_acumulada']) <= TOL:
                    g['continua_de'] = {'grupo': gi, 'linha': li, 'elemento': l['elemento'],
                                        'acumulada': l['dist_acumulada']}
    for s in g['segmentos']:
        s['chave_de'], s['chave_para'] = chave_elemento(s['de']), chave_elemento(s['para'])
        a, b = s['apos'], s['apos'] + 1
        s['entre'] = [a, b] if 0 <= a and b < len(ls) else None
        s['sentido'] = None
        if s['entre']:
            ka, kb = ls[a]['chave'], ls[b]['chave']
            if (s['chave_de'], s['chave_para']) == (kb, ka):
                s['sentido'] = 'contra_estaqueamento'      # da estaca maior para a menor
            elif (s['chave_de'], s['chave_para']) == (ka, kb):
                s['sentido'] = 'a_favor'


def _assinaturas(linhas, avisos):
    papeis = nomes = creas = None
    for k, ln in enumerate(linhas):
        s = ln.strip()
        if papeis is None and _eh_papeis(s, linhas[k + 1:k + 7]):
            papeis = tokens(ln)
        elif papeis is not None and nomes is None and re.match(r'^Eng', s, re.I):
            nomes = tokens(ln)
        elif papeis is not None and creas is None and re.match(r'^CREA', s, re.I):
            creas = tokens(ln)
    if not papeis:
        return []

    def casar(lista):
        if lista is None:
            return [None] * len(papeis)
        if len(lista) == len(papeis):
            return lista
        avisos.append('assinaturas: número de colunas diferente do de papéis; casadas pela posição (conferir)')
        out = [None] * len(papeis)
        for t in lista:
            out[min(range(len(papeis)), key=lambda i: abs(papeis[i].a - t.a))] = t
        return out

    res = []
    for pp, nm, cr in zip(papeis, casar(nomes), casar(creas)):
        rot = pp.s
        u = sem_acento(rot).upper()
        papel = ('FISCALIZACAO' if 'FISCALIZA' in u else 'TOPOGRAFIA' if 'TOPOGRAFIA' in u else 'CADASTRO'
                 if 'CADASTRO' in u else 'CONTRATADA' if re.search(r'CONSTRUTORA|CONTRATADA', u) else norm_txt(rot))
        empresa = rot.split(':', 1)[1].strip() if ':' in rot else (rot if papel == 'CONTRATADA' else None)
        nome = re.sub(r'^Eng\S*\s*', '', nm.s).strip() if nm else ''
        crea = re.sub(r'^CREA\s*:?\s*', '', cr.s).strip() if cr else ''
        res.append({'papel': papel, 'rotulo': rot, 'empresa': empresa or None, 'nome': nome or None,
                    'crea': crea or None})
    return res


def impressao_dados(ns):
    """SHA-256 do conteúdo (sem posições, folhas, avisos, fonte): mesma NS em PDFs diferentes = mesma impressão."""
    tirar = {'pagina', 'linha_txt', 'incerto', 'apos', 'confirmado_2a_leitura'}
    # cabeçalho pelo conteúdo, não pela grafia (a planilha guarda a data e o nº como número)
    cab = {k: v for k, v in ns['cabecalho'].items() if k not in ('folha', 'total_folhas', 'data_texto', 'numero', 'contrato')}
    cab['contrato'] = norm_contrato(ns['cabecalho'].get('contrato'))

    def limpo(d):
        return {k: v for k, v in d.items() if k not in tirar}

    dados = {'cabecalho': cab,
             'grupos': [{'titulo': g['titulo'], 'linhas': [limpo(l) for l in g['linhas']],
                         'segmentos': [limpo(s) for s in g['segmentos']]} for g in ns['grupos']],
             'notas': [limpo(n) for n in ns['notas']], 'resumo': [limpo(r) for r in ns['resumo']],
             'total_geral': ns['total_geral'], 'assinaturas': ns['assinaturas']}
    return hashlib.sha256(json.dumps(dados, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def impressao_tecnica(ns):
    """SHA-256 só do que conta para a obra (cabeçalho, estacas, elementos, números, segmentos, RESUMO e total), sem a
    grafia dos textos: compara duas leituras independentes da mesma NS (pypdf × pdftotext, PDF × planilha)."""
    c = ns['cabecalho']
    campos = ('estaca_m', 'chave') + CAMPOS_PRE + ('metodo', 'material', 'dn_mm') + CAMPOS_POS
    dados = {'cab': [c.get('numero_int'), norm_contrato(c.get('contrato')), c.get('data')],
             'grupos': [[[l.get(k) for k in campos] + [norm_txt(l.get('elemento')), norm_txt(l.get('obs'))] for l in g['linhas']]
                        + [[s.get('chave_de'), s.get('chave_para'), s.get('metros')] for s in g['segmentos']] for g in ns['grupos']],
             'resumo': [r.get('metros') for r in ns['resumo']], 'total': ns['total_geral']}
    return hashlib.sha256(json.dumps(dados, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


# ------------------------------------------------------------------------------------------------ conferências
def verificar(ns, contrato_obra=None, hoje=None, inicio_contrato=None, contratada_obra='ANKARA'):
    v = []

    def add(id_, nivel, ok, msg, **onde):
        onde = {k: x for k, x in onde.items() if x}
        v.append({'id': id_, 'nivel': nivel, 'ok': bool(ok), 'msg': msg, **({'onde': onde} if onde else {})})

    def igual(a, b):
        return a is not None and b is not None and abs(a - b) <= TOL

    cab = ns['cabecalho']
    falta = [k for k in ('numero', 'contrato', 'data', 'folha', 'total_folhas') if cab.get(k) in (None, '')]
    add('E01', 'ERRO', not falta, 'cabeçalho completo (NS nº, contrato, data válida, folha)' + (f': falta {falta}' if falta else ''))
    folhas = ns.get('folhas', [])
    npag = (ns.get('fonte') or {}).get('paginas') or len(folhas)
    seq = [f.get('folha') for f in folhas]
    tot = {f.get('total_folhas') for f in folhas}
    iguais = {(f.get('numero'), norm_contrato(f.get('contrato')), f.get('data_texto')) for f in folhas}
    ok_f = seq == list(range(1, len(folhas) + 1)) and tot == {len(folhas)} and len(iguais) == 1 and npag == len(folhas)
    add('E02', 'ERRO', ok_f, f'folhas {seq} "de" {sorted(t for t in tot if t)}; páginas no arquivo {npag}; '
        f'mesmo nº/contrato/data em todas: {len(iguais) == 1}')
    linhas = [(gi, li, l) for gi, g in enumerate(ns['grupos']) for li, l in enumerate(g['linhas'])]
    add('E03', 'ERRO', linhas, f'{len(ns["grupos"])} grupo(s), {len(linhas)} linha(s) de dados')
    obrig = [(gi, li) for gi, li, l in linhas if None in (l['estaca_m'], l['dist_parcial'], l['dist_acumulada'])]
    add('E04', 'ERRO', not obrig, 'estaca, parcial e acumulada em todas as linhas', linhas=obrig)
    sem_el = [(gi, li) for gi, li, l in linhas if not l['elemento']]
    add('E07', 'AVISO', not sem_el, 'elemento escrito em todas as linhas', linhas=sem_el)
    inc = [(gi, li, l['incerto']) for gi, li, l in linhas if l.get('incerto')]
    add('E05', 'ERRO', not inc, 'nenhuma célula com posição incerta: célula vazia posta pela ordem e não confirmada '
        'por âncora nem pela 2ª leitura; bloqueia até a confirmação na tela de revisão', linhas=inc)
    add('E06', 'ERRO', not ns.get('falhas_leitura'), 'nenhuma linha mal lida', detalhes=ns.get('falhas_leitura'))

    for gi, g in enumerate(ns['grupos']):
        ls = g['linhas']
        tg = f'[{gi}] ' + (g['titulo'] or 'sem título')[:50]
        e = [li for li, l in enumerate(ls) if None not in (l['cota_terreno'], l['cota_gi'], l['profundidade'])
             and not igual(l['cota_terreno'] - l['cota_gi'], l['profundidade'])]
        add('A01', 'ERRO', not e, f'{tg}: profundidade = terreno - GI', linhas=e)
        e = [li for li, l in enumerate(ls) if None not in (l['visor'], l['cruzeta'], l['profundidade'])
             and not igual(l['visor'] + l['profundidade'], l['cruzeta'])]
        add('A02', 'AVISO', not e, f'{tg}: cruzeta = visor + profundidade', linhas=e)
        e = [li for li, l in enumerate(ls) if None not in (l['esc_boca'], l['esc_fundo'])
             and l['esc_boca'] + TOL < l['esc_fundo']]
        add('A03', 'AVISO', not e, f'{tg}: escavação boca >= fundo', linhas=e)
        e = [li for li in range(1, len(ls)) if None not in (ls[li]['dist_acumulada'], ls[li - 1]['dist_acumulada'],
                                                            ls[li]['dist_parcial'])
             and not igual(ls[li - 1]['dist_acumulada'] + ls[li]['dist_parcial'], ls[li]['dist_acumulada'])]
        add('A04', 'ERRO', not e, f'{tg}: acumulada = acumulada anterior + parcial', linhas=e)
        e = [li for li, l in enumerate(ls) if None not in (l['estaca_m'], l['dist_acumulada'])
             and not igual(l['estaca_m'], l['dist_acumulada'])]
        add('A05', 'AVISO', not e, f'{tg}: estaca (inteira x 20 + fração) = acumulada', linhas=e)
        e = [li for li, l in enumerate(ls) if l['estaca_fracao'] is not None and l['estaca_fracao'] >= ESTACA_M]
        e += [li for li in range(1, len(ls)) if None not in (ls[li]['estaca_m'], ls[li - 1]['estaca_m'])
              and ls[li]['estaca_m'] < ls[li - 1]['estaca_m'] - TOL]
        add('A06', 'ERRO', not e, f'{tg}: estacas crescentes e fração < 20 m', linhas=e)
        l0 = ls[0]
        ok = (l0['dist_parcial'] or 0) <= TOL and ((l0['dist_acumulada'] or 0) <= TOL or g.get('continua_de'))
        cont = g.get('continua_de')
        add('A07', 'AVISO', ok, f'{tg}: começa com parcial 0 e acumulada 0, ou num ponto de grupo anterior'
            + (f' (continua de {cont["elemento"]!r} em {cont["acumulada"]} m do grupo {cont["grupo"]})' if cont else ''))
        bad_m, bad_n = [], []
        for s in g['segmentos']:
            if not s['entre']:
                bad_n.append((s['de'], s['para'], 'fora de um par de linhas'))
                continue
            a, b = (ls[k] for k in s['entre'])
            delta = None if None in (a['dist_acumulada'], b['dist_acumulada']) else b['dist_acumulada'] - a['dist_acumulada']
            if not (igual(s['metros'], b['dist_parcial']) and (delta is None or igual(s['metros'], delta))):
                bad_m.append((s['de'], s['para'], s['metros'], b['dist_parcial'], _r(delta)))
            if s['sentido'] is None:
                bad_n.append((s['de'], s['para'], a['chave'], b['chave']))
        add('A08', 'ERRO', not bad_m, f'{tg}: metros do segmento = parcial = diferença das acumuladas', detalhes=bad_m)
        add('A09', 'AVISO', not bad_n, f'{tg}: cada segmento liga as duas linhas vizinhas (nomes)', detalhes=bad_n)
        com = {s['apos'] for s in g['segmentos'] if s['entre']}
        faltam = [(ls[k]['chave'], ls[k + 1]['chave']) for k in range(len(ls) - 1) if k not in com]
        add('A10', 'AVISO', not faltam, f'{tg}: um segmento entre cada par de linhas', detalhes=faltam)
        rs = [r for r in ns['resumo'] if r.get('grupo') == gi]
        ext = g['extensao'] if g['extensao'] is not None else g['soma_parcial']
        ok = len(rs) == 1 and igual(rs[0]['metros'], g['soma_parcial']) and igual(ext, g['soma_parcial'])
        add('A11', 'ERRO', ok, f'{tg}: soma das parciais ({g["soma_parcial"]}) = extensão pelas acumuladas ({ext}) '
            f'= RESUMO ({[r["metros"] for r in rs]})')
        if rs:
            ok = rs[0]['dn_mm'] in (None, g['dn_mm']) and (rs[0]['material'] or '') in ('', g['material'] or '')
            add('A12', 'ERRO', ok, f'{tg}: material/DN do grupo ({g["material"]} {g["dn_mm"]}) = RESUMO '
                f'({rs[0]["material"]} {rs[0]["dn_mm"]})')
    soma_res = _r(sum(r['metros'] or 0 for r in ns['resumo']))
    add('A13', 'ERRO', igual(soma_res, ns['total_geral']), f'soma do RESUMO ({soma_res}) = TOTAL GERAL ({ns["total_geral"]})')
    sem_g = [r['descricao'] for r in ns['resumo'] if r.get('grupo') is None and r.get('metros') is not None]
    add('A14', 'ERRO', ns['resumo'] and not sem_g, 'há RESUMO e cada linha em metros corresponde a um grupo', detalhes=sem_g)
    chaves = {l['chave'] for _, _, l in linhas}
    orf = [n['elemento'] for n in ns['notas'] if n['chave'] and n['chave'] not in chaves]
    add('A15', 'AVISO', not orf, 'NOTAS citam elementos da tabela', detalhes=orf)

    # ---- regras da obra
    c_ns, c_obra = norm_contrato(cab.get('contrato')), norm_contrato(contrato_obra)
    if contrato_obra:
        add('V01', 'ERRO', c_ns == c_obra, f'contrato da NS ({c_ns}) = contrato da obra ({c_obra})')
    else:
        add('V01', 'INFO', True, 'contrato da obra não informado: conferência não feita')
    hoje = hoje or RL.hoje().isoformat()
    d = cab.get('data')
    add('V02', 'ERRO', d is not None and d <= hoje, f'data da NS ({d}) válida e não futura (hoje {hoje})')
    if inicio_contrato:
        add('V03', 'AVISO', d is not None and d >= inicio_contrato, f'data da NS ({d}) >= início do contrato ({inicio_contrato})')
    add('V04', 'AVISO', contratada_obra.upper() in (cab.get('contratada') or '').upper(),
        f'contratada contém {contratada_obra!r} ({cab.get("contratada")})')
    ass = ns['assinaturas']
    tec = [a for a in ass if a['papel'] in ('TOPOGRAFIA', 'CADASTRO', 'CONTRATADA')]
    add('V05', 'AVISO', tec and all(a['nome'] and a['crea'] for a in tec),
        f'responsáveis técnicos com nome e CREA ({sum(1 for a in tec if a["nome"] and a["crea"])} de {len(tec)})')
    fis = [a for a in ass if a['papel'] == 'FISCALIZACAO']
    add('V06', 'AVISO', fis and all(a['nome'] for a in fis),
        'fiscalização com nome no campo de assinatura: ' + ', '.join(f'{a["empresa"]}: {"sim" if a["nome"] else "não"}' for a in fis))
    imgs = [n for n in ((ns.get('fonte') or {}).get('imagens_por_pagina') or []) if n is not None]
    if imgs:
        add('V07', 'INFO', True, f'imagens por página: {imgs} (o modelo tem 1, o logotipo; mais que 1 sugere assinatura '
            'ou carimbo escaneado; a conferência visual continua obrigatória)')
    erros = [x for x in v if x['nivel'] == 'ERRO' and not x['ok']]
    avs = [x for x in v if x['nivel'] == 'AVISO' and not x['ok']]
    return {'verificacoes': v, 'resultado': {'erros': len(erros), 'avisos': len(avs), 'aceita': not erros,
                                             'motivos': [f'{x["id"]}: {x["msg"]}' for x in erros]}}


def _diferencas(a, b, maximo=8):
    """Campos que mudam entre duas leituras da mesma NS (para mostrar quando os extratores divergem)."""
    out = []
    for k in ('numero', 'contrato', 'data', 'total_folhas'):
        if a['cabecalho'].get(k) != b['cabecalho'].get(k):
            out.append(('cabecalho', k, a['cabecalho'].get(k), b['cabecalho'].get(k)))
    if len(a['grupos']) != len(b['grupos']):
        out.append(('grupos', 'quantidade', len(a['grupos']), len(b['grupos'])))
    for gi, (ga, gb) in enumerate(zip(a['grupos'], b['grupos'])):
        if len(ga['linhas']) != len(gb['linhas']):
            out.append((f'grupo {gi}', 'linhas', len(ga['linhas']), len(gb['linhas'])))
        for li, (la, lb) in enumerate(zip(ga['linhas'], gb['linhas'])):
            for c in ('estaca_m', 'chave') + CAMPOS_PRE + ('metodo', 'material', 'dn_mm') + CAMPOS_POS:
                if la.get(c) != lb.get(c):
                    out.append((f'grupo {gi} linha {li}', c, la.get(c), lb.get(c)))
            for c in ('elemento', 'obs'):
                if norm_txt(la.get(c)) != norm_txt(lb.get(c)):
                    out.append((f'grupo {gi} linha {li}', c, la.get(c), lb.get(c)))
        sa = [(s.get('chave_de'), s.get('chave_para'), s.get('metros')) for s in ga['segmentos']]
        sb = [(s.get('chave_de'), s.get('chave_para'), s.get('metros')) for s in gb['segmentos']]
        if sa != sb:
            out.append((f'grupo {gi}', 'segmentos', sa, sb))
    if [r['metros'] for r in a['resumo']] != [r['metros'] for r in b['resumo']] or a['total_geral'] != b['total_geral']:
        out.append(('resumo', 'metros/total', [r['metros'] for r in a['resumo']], [r['metros'] for r in b['resumo']]))
    return out[:maximo]


def _conferir(ns, outra, origem):
    """Compara a leitura principal com outra leitura independente (pdftotext ou planilha) pela impressão técnica."""
    igual = impressao_tecnica(outra) == impressao_tecnica(ns)
    ns['fonte']['conferido_com'] = {'extrator': origem, 'mesma_impressao': igual}
    if igual:
        for g in ns['grupos']:
            for l in g['linhas']:
                if l.pop('incerto', None):
                    l['confirmado_2a_leitura'] = True
    else:
        ns['falhas_leitura'].append(f'{ns["fonte"].get("extrator")} e {origem} leram dados diferentes: {_diferencas(ns, outra)}')


def conferir_texto_croqui(texto, cab):
    """Avisos quando o texto do croqui diz outra NS: o número, o contrato ou a data escritos nele não batem com os da
    nota. O croqui não é obrigado a trazer esses dados; só o que ele traz é conferido."""
    t = sem_acento(texto or '').upper()
    numeros = {int(m.group(1)) for m in re.finditer(
        r'(?<![A-Z0-9])(?:N\s*\.?\s*S|NOTA\s+DE\s+SERVICO)\s*\.?\s*(?:N\s*[O.]\s*)?[-_:.]?\s*(\d{1,4})(?![\d/])', t)}
    contratos = {norm_contrato(f'{a}/{b}') for a, b in    # só o número escrito depois de 'contrato' (ou 'CT')
                 re.findall(r'(?:CONTRAT\w*|(?<![A-Z])CT)[^0-9]{0,40}?(?<![\d/])(\d{3,6})\s*/\s*((?:19|20)\d\d)(?![\d/])', t)}
    datas = {d for d in (data_iso(m.group(0)) for m in re.finditer(
        r'(?<![\d/])\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})(?![\d/])|(?<!\d)\d{1,2}-[A-Z]{3}-\d{2,4}(?!\d)', t)) if d}
    avisos = []
    if numeros and cab.get('numero_int') is not None and cab['numero_int'] not in numeros:
        avisos.append(f'o croqui é da NS {", ".join(f"{n:03d}" for n in sorted(numeros))}, e a nota é a {cab.get("numero")}')
    contrato = norm_contrato(cab.get('contrato'))
    if contratos and contrato and contrato not in contratos:
        avisos.append(f'o croqui cita o contrato {", ".join(sorted(contratos))}, e a nota é do {contrato}')
    if datas and cab.get('data') and cab['data'] not in datas:
        br = lambda d: date.fromisoformat(d).strftime('%d/%m/%Y')
        avisos.append(f'a data do croqui ({", ".join(br(d) for d in sorted(datas))}) não é a da nota ({br(cab["data"])})')
    return avisos


def conferir_croqui(dados, ns):
    """conferir_texto_croqui com o texto do croqui em PDF. Foto, PDF sem texto ou ilegível: nada a conferir ([])."""
    if not dados or dados[:5] != b'%PDF-':
        return []
    try:
        r = _pypdf().PdfReader(io.BytesIO(dados))
        if r.is_encrypted and not r.decrypt(''):
            return []
        texto = '\n'.join(p.extract_text() or '' for p in list(r.pages)[:LIMITE_PAGINAS])
    except Exception:  # noqa: BLE001 — o croqui é guardado como vier; a conferência é só reforço
        return []
    return conferir_texto_croqui(texto, ns.get('cabecalho') or {})


def ler(dados, contrato_obra=None, hoje=None, inicio_contrato=None, planilha=None, comparar=True):
    """Lê o PDF da NS (bytes) e faz as conferências. Com a planilha .xlsx ou .xls (bytes), ela confere a leitura do PDF;
    sem ela, se o pdftotext existir, o PDF é relido com ele. Leituras iguais confirmam as células incertas; diferentes
    viram falha de leitura (ERRO E06), com as diferenças. Arquivo que não dá para ler: LeituraRecusada."""
    paginas, meta = extrair_paginas(dados, 'auto')
    ns = parse_texto(paginas, meta)
    if planilha:
        origem = f'planilha {tipo_planilha(planilha) or ""}'.strip()
        ns_p = parse_texto(ler_planilha(planilha), {'extrator': origem, 'posicoes_fieis': True,
                                                     'paginas': meta.get('paginas')})
        _conferir(ns, ns_p, origem)
    elif comparar and str(meta.get('extrator', '')).startswith('pypdf') and shutil.which('pdftotext'):
        try:
            pag2, meta2 = extrair_paginas(dados, 'pdftotext')
            _conferir(ns, parse_texto(pag2, meta2), meta2['extrator'])
        except Exception as e:  # noqa: BLE001 — a comparação é reforço; sem ela vale a leitura principal
            ns['fonte']['conferido_com'] = {'erro': f'{type(e).__name__}: {e}'}
    ns.update(verificar(ns, contrato_obra=contrato_obra, hoje=hoje, inicio_contrato=inicio_contrato))
    return ns


if __name__ == '__main__':      # conferência manual: python ns_leitura.py NS.pdf [contrato da obra]
    import sys
    with open(sys.argv[1], 'rb') as f:
        r = ler(f.read(), sys.argv[2] if len(sys.argv) > 2 else None)
    c = r['cabecalho']
    print(f'NS {c.get("numero")} contrato {c.get("contrato")} data {c.get("data")}: {len(r["grupos"])} grupos, '
          f'{sum(len(g["linhas"]) for g in r["grupos"])} linhas, total {r["total_geral"]} | '
          f'erros {r["resultado"]["erros"]} avisos {r["resultado"]["avisos"]} | {r["fonte"].get("extrator")} | '
          f'impressão {r["impressao_dados"][:12]}')
    for m in r['resultado']['motivos']:
        print('  ERRO', m)
