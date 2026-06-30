from __future__ import annotations

from datetime import date, datetime

# ── Importamos o contexto de trimestre ────────────────────────────────────────
# Usamos importação lazy para evitar circular imports durante inicialização.


def _get_trimestre_ctx():
    from app.utils.trimestre_context import (
        get_master_semanas,
        get_meses_map,
        semana_global_atual_trimestre,
        semana_editavel_trimestre,
    )
    return get_master_semanas, get_meses_map, semana_global_atual_trimestre, semana_editavel_trimestre


# Constante de semana padrão de preenchimento
SEMANA_PADRAO_PREENCHIMENTO = 2


def semana_global_atual(agora: datetime | None = None) -> int:
    """Retorna a semana atual (1–12) no trimestre ativo."""
    _, _, semana_global_atual_trimestre, _ = _get_trimestre_ctx()
    return semana_global_atual_trimestre(agora)


def semana_global_para_local(semana_global: int) -> tuple[str, int]:
    """Converte semana global para (mes_slug, semana_local) no trimestre ativo."""
    _, get_meses_map, _, _ = _get_trimestre_ctx()
    meses_map = get_meses_map()
    for mes_slug, info in meses_map.items():
        inicio = info['semana_inicio']
        fim = inicio + 3
        if inicio <= semana_global <= fim:
            return mes_slug, (semana_global - inicio) + 1
    primeiro = list(meses_map.keys())[0]
    return primeiro, 1


def semana_local_atual(mes_slug: str, agora: datetime | None = None) -> int:
    _, get_meses_map, _, _ = _get_trimestre_ctx()
    meses_map = get_meses_map()
    mes_normalizado = mes_slug if mes_slug in meses_map else list(meses_map.keys())[0]
    mes_atual, semana_local = semana_global_para_local(semana_global_atual(agora))
    if mes_atual != mes_normalizado:
        return 1
    return semana_local


def semana_padrao_preenchimento() -> int:
    return SEMANA_PADRAO_PREENCHIMENTO


def semana_global_por_mes_local(mes_slug: str, semana_local: int) -> int:
    _, get_meses_map, _, _ = _get_trimestre_ctx()
    meses_map = get_meses_map()
    primeiro = list(meses_map.keys())[0]
    info = meses_map.get(mes_slug, meses_map[primeiro])
    semana_normalizada = min(max(int(semana_local or 1), 1), 4)
    return info['semana_inicio'] + semana_normalizada - 1


def semana_global_por_data(data_referencia: date | None, fallback_mes: str | None = None) -> int | None:
    _, get_meses_map, _, _ = _get_trimestre_ctx()
    meses_map = get_meses_map()
    if data_referencia is None:
        return None
    for mes_slug, info in meses_map.items():
        if data_referencia.month == info['numero']:
            return semana_global_por_mes_local(mes_slug, ((data_referencia.day - 1) // 7) + 1)
    if fallback_mes and fallback_mes in meses_map:
        return semana_global_por_mes_local(fallback_mes, ((data_referencia.day - 1) // 7) + 1)
    return None


def semana_editavel(
    semana_global: int,
    can_override_past_lock: bool,
    is_admin: bool = False,
    agora: datetime | None = None,
) -> bool:
    _, _, _, semana_editavel_trimestre = _get_trimestre_ctx()
    return semana_editavel_trimestre(semana_global, can_override_past_lock, is_admin, agora)
