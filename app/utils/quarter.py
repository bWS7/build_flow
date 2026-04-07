from __future__ import annotations

from datetime import date, datetime

MASTER_SEMANAS = [
    (1, datetime(2026, 4, 1, 0, 0, 0), datetime(2026, 4, 7, 23, 59, 59)),
    (2, datetime(2026, 4, 8, 0, 0, 0), datetime(2026, 4, 14, 23, 59, 59)),
    (3, datetime(2026, 4, 15, 0, 0, 0), datetime(2026, 4, 21, 23, 59, 59)),
    (4, datetime(2026, 4, 22, 0, 0, 0), datetime(2026, 4, 30, 23, 59, 59)),
    (5, datetime(2026, 5, 1, 0, 0, 0), datetime(2026, 5, 7, 23, 59, 59)),
    (6, datetime(2026, 5, 8, 0, 0, 0), datetime(2026, 5, 14, 23, 59, 59)),
    (7, datetime(2026, 5, 15, 0, 0, 0), datetime(2026, 5, 21, 23, 59, 59)),
    (8, datetime(2026, 5, 22, 0, 0, 0), datetime(2026, 5, 31, 23, 59, 59)),
    (9, datetime(2026, 6, 1, 0, 0, 0), datetime(2026, 6, 7, 23, 59, 59)),
    (10, datetime(2026, 6, 8, 0, 0, 0), datetime(2026, 6, 14, 23, 59, 59)),
    (11, datetime(2026, 6, 15, 0, 0, 0), datetime(2026, 6, 21, 23, 59, 59)),
    (12, datetime(2026, 6, 22, 0, 0, 0), datetime(2026, 6, 30, 23, 59, 59)),
]

MESES_MAP = {
    "abril": {"numero": 4, "semana_inicio": 1},
    "maio": {"numero": 5, "semana_inicio": 5},
    "junho": {"numero": 6, "semana_inicio": 9},
}


def semana_global_atual(agora: datetime | None = None) -> int:
    referencia = agora or datetime.now()
    for semana, inicio, fim in MASTER_SEMANAS:
        if inicio <= referencia <= fim:
            return semana
    if referencia < MASTER_SEMANAS[0][1]:
        return MASTER_SEMANAS[0][0]
    return MASTER_SEMANAS[-1][0]


def semana_global_para_local(semana_global: int) -> tuple[str, int]:
    for mes_slug, info in MESES_MAP.items():
        inicio = info["semana_inicio"]
        fim = inicio + 3
        if inicio <= semana_global <= fim:
            return mes_slug, (semana_global - inicio) + 1
    return "abril", 1


def semana_local_atual(mes_slug: str, agora: datetime | None = None) -> int:
    mes_normalizado = mes_slug if mes_slug in MESES_MAP else "abril"
    mes_atual, semana_local = semana_global_para_local(semana_global_atual(agora))
    if mes_atual != mes_normalizado:
        return 1
    return semana_local


def semana_global_por_mes_local(mes_slug: str, semana_local: int) -> int:
    info = MESES_MAP.get(mes_slug, MESES_MAP["abril"])
    semana_normalizada = min(max(int(semana_local or 1), 1), 4)
    return info["semana_inicio"] + semana_normalizada - 1


def semana_global_por_data(data_referencia: date | None, fallback_mes: str = "abril") -> int | None:
    if data_referencia is None:
        return None
    for mes_slug, info in MESES_MAP.items():
        if data_referencia.month == info["numero"]:
            return semana_global_por_mes_local(mes_slug, ((data_referencia.day - 1) // 7) + 1)
    if fallback_mes in MESES_MAP:
        return semana_global_por_mes_local(fallback_mes, ((data_referencia.day - 1) // 7) + 1)
    return None


def semana_editavel(semana_global: int, is_admin: bool, agora: datetime | None = None) -> bool:
    if is_admin:
        return True
    return int(semana_global or 0) >= semana_global_atual(agora)
