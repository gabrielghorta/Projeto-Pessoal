"""Validação de imagem antes de aceitar uma foto como evidência (achado F05 da auditoria do commit f035f5c).

O hash prova a identidade dos bytes, não que eles sejam uma foto. Aqui se confere se o arquivo é uma imagem íntegra:

* com Pillow instalado: decodificação completa dos pixels (``DECODIFICADA``);
* sem Pillow:
  - PNG: decodificação completa só com a biblioteca padrão (CRC de cada bloco, zlib, tamanho exato das linhas);
  - JPEG: verificação estrutural (marcadores com tamanhos válidos, tabelas de quantização e Huffman, quadro com
    largura/altura, varredura com dados e marcador final EOI). Pega arquivo truncado, cabeçalho falso e texto com
    assinatura JPEG, mas não pixel corrompido dentro de uma varredura bem formada (``ESTRUTURAL``);
* HEIC/outros: sem decodificador disponível → recusado (converter para JPEG).

Os bytes originais nunca são alterados: a validação só lê.
"""
import io
import struct
import zlib

try:                                                    # opcional: decodificação completa dos pixels
    from PIL import Image as _PIL
    from PIL import ImageOps as _OPS
except ImportError:                                     # pragma: no cover - depende do ambiente
    _PIL = _OPS = None


class ImagemInvalida(ValueError):
    pass


def tipo(dados):
    if dados[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if dados[4:8] == b"ftyp" and dados[8:12] in (b"heic", b"heix", b"mif1", b"heim", b"heis"):
        return "heic", "image/heic"
    return None, None


_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_estrutura(d):
    if d[:2] != b"\xff\xd8":
        raise ImagemInvalida("JPEG sem marcador inicial (SOI).")
    i, vistos, varreduras, n = 2, set(), 0, len(d)
    quadro = None
    while i < n:
        if d[i] != 0xFF:
            raise ImagemInvalida(f"JPEG corrompido: byte inesperado na posição {i}.")
        while i < n and d[i] == 0xFF:                  # marcadores podem ter FF de preenchimento
            i += 1
        if i >= n:
            break
        m = d[i]
        i += 1
        if m == 0xD9:                                  # EOI
            if not quadro:
                raise ImagemInvalida("JPEG sem quadro de imagem (SOF).")
            if not varreduras:
                raise ImagemInvalida("JPEG sem dados de imagem (SOS).")
            if 0xDB not in vistos:
                raise ImagemInvalida("JPEG sem tabela de quantização (DQT).")
            if quadro[0] in (0xC0, 0xC1, 0xC2, 0xC3) and 0xC4 not in vistos:
                raise ImagemInvalida("JPEG sem tabela de Huffman (DHT).")
            return quadro
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            continue
        if i + 2 > n:
            raise ImagemInvalida("JPEG truncado no cabeçalho de um segmento.")
        tam = struct.unpack(">H", d[i:i + 2])[0]
        if tam < 2 or i + tam > n:
            raise ImagemInvalida("JPEG truncado (segmento além do fim do arquivo).")
        seg = d[i + 2:i + tam]
        vistos.add(m)
        if m in _SOF:
            if len(seg) < 6:
                raise ImagemInvalida("JPEG com quadro (SOF) incompleto.")
            alt, larg, comp = struct.unpack(">HHB", seg[1:6])
            if alt == 0 or larg == 0 or comp not in (1, 3, 4) or len(seg) < 6 + 3 * comp:
                raise ImagemInvalida("JPEG com dimensões ou componentes inválidos.")
            quadro = (m, larg, alt)
        i += tam
        if m == 0xDA:                                  # SOS: dados entrópicos até o próximo marcador real
            if not quadro:
                raise ImagemInvalida("JPEG com varredura antes do quadro.")
            ini = i
            while i < n - 1:
                if d[i] == 0xFF and d[i + 1] != 0x00 and not (0xD0 <= d[i + 1] <= 0xD7):
                    break
                i += 1
            else:
                raise ImagemInvalida("JPEG truncado: dados de imagem sem marcador final (EOI).")
            if i == ini:
                raise ImagemInvalida("JPEG com varredura vazia.")
            varreduras += 1
    raise ImagemInvalida("JPEG truncado: sem marcador final (EOI).")


def _png_decodifica(d):
    i, ihdr, idat, fim = 8, None, [], False
    while i + 8 <= len(d):
        tam, tp = struct.unpack(">I4s", d[i:i + 8])
        if i + 12 + tam > len(d):
            raise ImagemInvalida("PNG truncado.")
        corpo = d[i + 8:i + 8 + tam]
        if struct.unpack(">I", d[i + 8 + tam:i + 12 + tam])[0] != zlib.crc32(tp + corpo) & 0xFFFFFFFF:
            raise ImagemInvalida(f"PNG corrompido (CRC do bloco {tp.decode('latin1')}).")
        if tp == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", corpo)
        elif tp == b"IDAT":
            idat.append(corpo)
        elif tp == b"IEND":
            fim = True
            break
        i += 12 + tam
    if not ihdr or not idat or not fim:
        raise ImagemInvalida("PNG incompleto (IHDR/IDAT/IEND).")
    larg, alt, prof, cor, _, _, entrel = ihdr
    canais = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(cor)
    if not larg or not alt or canais is None:
        raise ImagemInvalida("PNG com cabeçalho inválido.")
    try:
        bruto = zlib.decompress(b"".join(idat))
    except zlib.error:
        raise ImagemInvalida("PNG com dados de imagem corrompidos.") from None
    linha = lambda w: 1 + (w * canais * prof + 7) // 8
    if entrel:
        passos = [(8, 8, 0, 0), (8, 8, 4, 0), (4, 8, 0, 4), (4, 4, 2, 0), (2, 4, 0, 2), (2, 2, 1, 0), (1, 2, 0, 1)]
        esperado = 0
        for dx, dy, x0, y0 in passos:
            w, h = (larg - x0 + dx - 1) // dx, (alt - y0 + dy - 1) // dy
            if w and h:
                esperado += h * linha(w)
    else:
        esperado = alt * linha(larg)
    if len(bruto) != esperado:
        raise ImagemInvalida("PNG com quantidade de pixels incompatível com o cabeçalho.")
    return (larg, alt)


def miniatura(dados, lado=640, qualidade=70):
    """JPEG reduzido (lado maior até `lado` px, ~25 KB) para mostrar a foto quando o original fica só no Drive.
    Sem Pillow devolve None: aí o original continua no servidor."""
    if _PIL is None:
        return None
    try:
        with _PIL.open(io.BytesIO(dados)) as im:
            im = _OPS.exif_transpose(im).convert("RGB")   # foto de celular: a orientação vem no EXIF
            im.thumbnail((lado, lado))
            saida = io.BytesIO()
            im.save(saida, "JPEG", quality=qualidade, optimize=True)
            return saida.getvalue()
    except (OSError, ValueError):
        return None


def validar(dados):
    """Valida a imagem. Retorna (extensão, mime, método) ou lança ImagemInvalida com o motivo."""
    ext, mime = tipo(dados)
    if not ext:
        raise ImagemInvalida("Arquivo não é uma imagem JPEG ou PNG.")
    if ext == "heic":
        raise ImagemInvalida("HEIC não pode ser validado neste sistema: envie a foto em JPEG.")
    if ext == "jpg":
        _jpeg_estrutura(dados)
    else:
        _png_decodifica(dados)
    if _PIL is not None:
        try:
            with _PIL.open(io.BytesIO(dados)) as im:
                im.load()
        except Exception as e:                          # noqa: BLE001 — qualquer falha de decodificação recusa
            raise ImagemInvalida(f"Imagem não decodifica ({type(e).__name__}).") from None
        return ext, mime, "DECODIFICADA (Pillow)"
    return ext, mime, ("DECODIFICADA (PNG)" if ext == "png" else "ESTRUTURAL (JPEG, sem Pillow)")
