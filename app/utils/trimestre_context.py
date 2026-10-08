"""
Contexto de trimestre — fonte única da verdade para qual trimestre está ativo.

Q1: Abril, Maio, Junho      (semanas 1–12, meses 4, 5, 6)
Q2: Julho, Agosto, Set.     (semanas 1–12, meses 7, 8, 9)
Q3: Outubro, Nov., Dez.     (semanas 1–12, meses 10, 11, 12)
"""
from __future__ import annotations

from datetime import datetime
from flask import session


# ── Configurações de cada trimestre ───────────────────────────────────────────

Q1_MESES = [
    ('abril',   'Abril',   4, 1),
    ('maio',    'Maio',    5, 5),
    ('junho',   'Junho',   6, 9),
]

Q2_MESES = [
    ('julho',    'Julho',    7, 1),
    ('agosto',   'Agosto',   8, 5),
    ('setembro', 'Setembro', 9, 9),
]

Q1_MASTER_SEMANAS = [
    (1,  datetime(2026,  4,  1, 0, 0, 0), datetime(2026,  4,  7, 23, 59, 59)),
    (2,  datetime(2026,  4,  8, 0, 0, 0), datetime(2026,  4, 14, 23, 59, 59)),
    (3,  datetime(2026,  4, 15, 0, 0, 0), datetime(2026,  4, 21, 23, 59, 59)),
    (4,  datetime(2026,  4, 22, 0, 0, 0), datetime(2026,  4, 30, 23, 59, 59)),
    (5,  datetime(2026,  5,  1, 0, 0, 0), datetime(2026,  5,  7, 23, 59, 59)),
    (6,  datetime(2026,  5,  8, 0, 0, 0), datetime(2026,  5, 14, 23, 59, 59)),
    (7,  datetime(2026,  5, 15, 0, 0, 0), datetime(2026,  5, 21, 23, 59, 59)),
    (8,  datetime(2026,  5, 22, 0, 0, 0), datetime(2026,  5, 31, 23, 59, 59)),
    (9,  datetime(2026,  6,  1, 0, 0, 0), datetime(2026,  6,  7, 23, 59, 59)),
    (10, datetime(2026,  6,  8, 0, 0, 0), datetime(2026,  6, 14, 23, 59, 59)),
    (11, datetime(2026,  6, 15, 0, 0, 0), datetime(2026,  6, 21, 23, 59, 59)),
    (12, datetime(2026,  6, 22, 0, 0, 0), datetime(2026,  6, 30, 23, 59, 59)),
]

Q2_MASTER_SEMANAS = [
    (1,  datetime(2026,  7,  1, 0, 0, 0), datetime(2026,  7,  7, 23, 59, 59)),
    (2,  datetime(2026,  7,  8, 0, 0, 0), datetime(2026,  7, 14, 23, 59, 59)),
    (3,  datetime(2026,  7, 15, 0, 0, 0), datetime(2026,  7, 21, 23, 59, 59)),
    (4,  datetime(2026,  7, 22, 0, 0, 0), datetime(2026,  7, 31, 23, 59, 59)),
    (5,  datetime(2026,  8,  1, 0, 0, 0), datetime(2026,  8,  7, 23, 59, 59)),
    (6,  datetime(2026,  8,  8, 0, 0, 0), datetime(2026,  8, 14, 23, 59, 59)),
    (7,  datetime(2026,  8, 15, 0, 0, 0), datetime(2026,  8, 21, 23, 59, 59)),
    (8,  datetime(2026,  8, 22, 0, 0, 0), datetime(2026,  8, 31, 23, 59, 59)),
    (9,  datetime(2026,  9,  1, 0, 0, 0), datetime(2026,  9,  7, 23, 59, 59)),
    (10, datetime(2026,  9,  8, 0, 0, 0), datetime(2026,  9, 14, 23, 59, 59)),
    (11, datetime(2026,  9, 15, 0, 0, 0), datetime(2026,  9, 21, 23, 59, 59)),
    (12, datetime(2026,  9, 22, 0, 0, 0), datetime(2026,  9, 30, 23, 59, 59)),
]

Q3_MESES = [
    ('outubro',   'Outubro',   10, 1),
    ('novembro',  'Novembro',  11, 5),
    ('dezembro',  'Dezembro',  12, 9),
]

Q3_MASTER_SEMANAS = [
    (1,  datetime(2026, 10,  1, 0, 0, 0), datetime(2026, 10,  7, 23, 59, 59)),
    (2,  datetime(2026, 10,  8, 0, 0, 0), datetime(2026, 10, 14, 23, 59, 59)),
    (3,  datetime(2026, 10, 15, 0, 0, 0), datetime(2026, 10, 21, 23, 59, 59)),
    (4,  datetime(2026, 10, 22, 0, 0, 0), datetime(2026, 10, 31, 23, 59, 59)),
    (5,  datetime(2026, 11,  1, 0, 0, 0), datetime(2026, 11,  7, 23, 59, 59)),
    (6,  datetime(2026, 11,  8, 0, 0, 0), datetime(2026, 11, 14, 23, 59, 59)),
    (7,  datetime(2026, 11, 15, 0, 0, 0), datetime(2026, 11, 21, 23, 59, 59)),
    (8,  datetime(2026, 11, 22, 0, 0, 0), datetime(2026, 11, 30, 23, 59, 59)),
    (9,  datetime(2026, 12,  1, 0, 0, 0), datetime(2026, 12,  7, 23, 59, 59)),
    (10, datetime(2026, 12,  8, 0, 0, 0), datetime(2026, 12, 14, 23, 59, 59)),
    (11, datetime(2026, 12, 15, 0, 0, 0), datetime(2026, 12, 21, 23, 59, 59)),
    (12, datetime(2026, 12, 22, 0, 0, 0), datetime(2026, 12, 31, 23, 59, 59)),
]

# ── Lookups por trimestre ──────────────────────────────────────────────────────

_MESES_POR_TRIMESTRE = {'q1': Q1_MESES, 'q2': Q2_MESES, 'q3': Q3_MESES}
_MASTER_SEMANAS_POR_TRIMESTRE = {
    'q1': Q1_MASTER_SEMANAS,
    'q2': Q2_MASTER_SEMANAS,
    'q3': Q3_MASTER_SEMANAS,
}
_LABEL_POR_TRIMESTRE = {
    'q1': '2º Trimestre (Abril–Junho)',
    'q2': '3º Trimestre (Julho–Setembro)',
    'q3': '4º Trimestre (Outubro–Dezembro)',
}

# ── Helpers públicos ───────────────────────────────────────────────────────────

def get_trimestre() -> str:
    """Retorna 'q1', 'q2' ou 'q3' baseado na sessão do usuário."""
    return session.get('trimestre', 'q1')


def get_meses() -> list:
    """Retorna a lista de meses (slug, nome, numero, semana_inicio) do trimestre ativo."""
    return _MESES_POR_TRIMESTRE.get(get_trimestre(), Q1_MESES)


def get_meses_map() -> dict:
    """Retorna o dict slug→info do trimestre ativo."""
    return {
        slug: {'slug': slug, 'nome': nome, 'numero': numero, 'semana_inicio': semana_inicio}
        for slug, nome, numero, semana_inicio in get_meses()
    }


def get_meses_numeros() -> list[int]:
    """Retorna os números dos meses do trimestre ativo ([4,5,6] ou [7,8,9])."""
    return [numero for _, _, numero, _ in get_meses()]


def get_master_semanas() -> list:
    """Retorna os intervalos de data para cada semana (1–12) do trimestre ativo."""
    return _MASTER_SEMANAS_POR_TRIMESTRE.get(get_trimestre(), Q1_MASTER_SEMANAS)


def get_primeiro_mes_slug() -> str:
    """Retorna o slug do primeiro mês do trimestre ativo."""
    return get_meses()[0][0]


def get_periodo_label() -> str:
    """Label do trimestre ativo para exibição."""
    return _LABEL_POR_TRIMESTRE.get(get_trimestre(), _LABEL_POR_TRIMESTRE['q1'])


def semana_global_atual_trimestre(agora: datetime | None = None) -> int:
    """Retorna a semana global atual (1–12) dentro do trimestre ativo."""
    referencia = agora or datetime.now()
    semanas = get_master_semanas()
    for semana, inicio, fim in semanas:
        if inicio <= referencia <= fim:
            return semana
    if referencia < semanas[0][1]:
        return semanas[0][0]
    return semanas[-1][0]


def semana_editavel_trimestre(
    semana_global: int,
    can_override_past_lock: bool,
    is_admin: bool = False,
    agora: datetime | None = None,
) -> bool:
    """Verifica se uma semana é editável no contexto do trimestre ativo."""
    semana = int(semana_global or 0)
    primeira_semana = 1
    # A trava da semana 1 vale apenas para o 1º trimestre (semana inicial de abril).
    if semana == primeira_semana and not is_admin and get_trimestre() == 'q1':
        return False
    if can_override_past_lock:
        return True
    return semana >= semana_global_atual_trimestre(agora)
