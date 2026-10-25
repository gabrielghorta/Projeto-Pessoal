"""Relógio da obra: a data e a hora de Brasília, em todo o servidor.

O PythonAnywhere roda em UTC. Antes, das 21h à meia-noite de Brasília o servidor já estava no dia seguinte: o mapa
procurava o check-in do "dia" errado e o pino e o laranja da equipe sumiam, e a data padrão de cada registro virava a de
amanhã. Tudo que pergunta "que dia é hoje" ou carimba um registro passa por aqui. Os carimbos gravados antes desta troca
(23/10/2026) estão em UTC e não são reescritos (docs/NUVEM.md).
"""
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:       # sem a base de fusos no sistema: UTC−3 fixo (o Brasil não tem horário de verão desde 2019)
    FUSO = timezone(timedelta(hours=-3))

_FIXO = None            # só para teste: fixar(datetime em UTC) congela o relógio


def agora():
    """Data e hora de Brasília, sem fuso no objeto (o mesmo formato que o banco sempre guardou)."""
    base = _FIXO if _FIXO is not None else datetime.now(timezone.utc)
    return base.astimezone(FUSO).replace(tzinfo=None)


def hoje():
    return agora().date()


def fixar(utc=None):
    """Teste: congela o relógio num instante em UTC (datetime sem fuso = UTC); fixar() volta ao relógio de verdade."""
    global _FIXO
    _FIXO = utc.replace(tzinfo=timezone.utc) if utc is not None and utc.tzinfo is None else utc
