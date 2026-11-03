"""Coordenadas da obra: UTM (SIRGAS 2000, fuso 23 Sul, as da 06.1 e da 06.2) → latitude e longitude.

As fichas do trecho e do nó mostram as coordenadas reais, como o HTML do projeto (E e N, com o link para abrir no mapa).
A 06.2 traz latitude e longitude dos nós; a 06.1 traz só a UTM das pontas do trecho, então a latitude e a longitude de
cada ponta saem daqui. Série de Krüger (Karney, 2011) no elipsoide GRS80: erro abaixo de 1 mm na faixa do fuso. Conferido
contra as 2.872 pontas do HTML do projeto (tests/test_coordenadas.py).
"""
import math

A = 6378137.0                       # GRS80 (SIRGAS 2000)
F = 1 / 298.257222101
K0 = 0.9996
FALSO_E, FALSO_N_SUL = 500000.0, 10000000.0
FUSO_OBRA = 23                      # meridiano central −45°: São Sebastião/DF

_N = F / (2 - F)
_A = A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_BETA = (_N / 2 - 2 * _N ** 2 / 3 + 37 * _N ** 3 / 96, _N ** 2 / 48 + _N ** 3 / 15, 17 * _N ** 3 / 480)
_DELTA = (2 * _N - 2 * _N ** 2 / 3 - 2 * _N ** 3, 7 * _N ** 2 / 3 - 8 * _N ** 3 / 5, 56 * _N ** 3 / 15)


def utm_para_geo(e, n, fuso=FUSO_OBRA, sul=True):
    """(E, N) em metros → (latitude, longitude) em graus decimais, com 7 casas (cerca de 1 cm)."""
    xi = (n - (FALSO_N_SUL if sul else 0.0)) / (K0 * _A)
    eta = (e - FALSO_E) / (K0 * _A)
    xi_ = xi - sum(b * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    eta_ = eta - sum(b * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    chi = math.asin(math.sin(xi_) / math.cosh(eta_))
    lat = chi + sum(d * math.sin(2 * j * chi) for j, d in enumerate(_DELTA, 1))
    lon = math.radians(fuso * 6 - 183) + math.atan2(math.sinh(eta_), math.cos(xi_))
    return round(math.degrees(lat), 7), round(math.degrees(lon), 7)


def do_trecho(utm_ini, utm_fim, no_ini=None, no_fim=None):
    """As duas pontas do trecho (as UTM das colunas BS..BV da 06.1, guardadas como texto JSON [E, N])."""
    import json
    lido = lambda u: json.loads(u) if isinstance(u, str) and u.strip() else u
    a, b = lido(utm_ini), lido(utm_fim)
    return {"inicio": ponto(*a, no=no_ini) if a else None, "fim": ponto(*b, no=no_fim) if b else None}


def ponto(e, n, lat=None, lon=None, no=None):
    """A coordenada como a ficha mostra: E e N (3 casas, as da planilha), latitude e longitude (as da planilha, se houver;
    senão, convertidas da UTM) e o nó da ponta. None sem UTM."""
    if e is None or n is None:
        return None
    if lat is None or lon is None:
        lat, lon = utm_para_geo(float(e), float(n))
    return {"e": round(float(e), 3), "n": round(float(n), 3), "lat": lat, "lon": lon, "no": no}
