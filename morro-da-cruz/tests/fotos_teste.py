"""JPEGs mínimos e únicos para os testes (cada evidência precisa de uma foto própria), com EXIF opcional."""
import base64
import itertools
import struct

_seq = itertools.count(1)


def _exif(data_hora=None, lat=None, lon=None):
    """APP1 Exif (TIFF little-endian) com DateTimeOriginal e GPS opcionais."""
    ents0 = []
    base = 8                                                   # IFD0 começa no byte 8 do TIFF
    n0 = (1 if data_hora else 0) + (1 if lat is not None else 0)
    pos = base + 2 + 12 * n0 + 4                               # depois do IFD0
    corpo = b""
    if data_hora:
        exif_ifd = pos
        dt = data_hora.replace("-", ":").replace("T", " ")[:19].encode() + b"\x00"
        val = exif_ifd + 2 + 12 + 4
        corpo += struct.pack("<H", 1) + struct.pack("<HHII", 0x9003, 2, len(dt), val) + struct.pack("<I", 0) + dt
        ents0.append(struct.pack("<HHII", 0x8769, 4, 1, exif_ifd))
        pos = base + 2 + 12 * n0 + 4 + len(corpo)
    if lat is not None:
        gps_ifd = pos
        rac = lambda v: [(int(abs(v)), 1), (int(abs(v) * 60) % 60, 1), (round((abs(v) * 3600) % 60 * 1000), 1000)]
        dados_rac = gps_ifd + 2 + 12 * 4 + 4
        ent = struct.pack("<H", 4)
        ent += struct.pack("<HHI", 1, 2, 2) + (b"S" if lat < 0 else b"N") + b"\x00\x00\x00"
        ent += struct.pack("<HHII", 2, 5, 3, dados_rac)
        ent += struct.pack("<HHI", 3, 2, 2) + (b"W" if lon < 0 else b"E") + b"\x00\x00\x00"
        ent += struct.pack("<HHII", 4, 5, 3, dados_rac + 24) + struct.pack("<I", 0)
        for v in (lat, lon):
            for a, b in rac(v):
                ent += struct.pack("<II", a, b)
        corpo += ent
        ents0.append(struct.pack("<HHII", 0x8825, 4, 1, gps_ifd))
    tiff = b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", len(ents0)) + b"".join(ents0) + struct.pack("<I", 0) + corpo
    app1 = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1


def jpeg(data_hora=None, lat=None, lon=None):
    """base64 de um JPEG mínimo e único; com data_hora/lat/lon grava EXIF."""
    exif = _exif(data_hora, lat, lon) if (data_hora or lat is not None) else b""
    unico = f"foto-teste-{next(_seq)}".encode()
    com = b"\xff\xfe" + struct.pack(">H", len(unico) + 2) + unico
    return base64.b64encode(b"\xff\xd8" + exif + com + b"\xff\xda\x00\x02\xff\xd9").decode()
