"""
Testes de unidade para app/utils/trimestre_context.py — a fonte unica da
verdade sobre qual trimestre esta ativo. Cobre especificamente o 4o Trimestre
(q3, Outubro-Dezembro) adicionado ao sistema, alem de q1/q2 ja existentes.
"""
import calendar
from datetime import datetime, timedelta

import pytest
from flask import session

from app.utils import trimestre_context as tc

TRIMESTRES = ['q1', 'q2', 'q3']


@pytest.mark.parametrize('trimestre,meses_esperados', [
    ('q1', [4, 5, 6]),
    ('q2', [7, 8, 9]),
    ('q3', [10, 11, 12]),
])
def test_meses_do_trimestre(trimestre, meses_esperados):
    meses = tc._MESES_POR_TRIMESTRE[trimestre]
    assert [numero for _, _, numero, _ in meses] == meses_esperados
    assert len(meses) == 3


@pytest.mark.parametrize('trimestre', TRIMESTRES)
def test_master_semanas_cobrem_o_trimestre_sem_buraco_nem_sobreposicao(trimestre):
    semanas = tc._MASTER_SEMANAS_POR_TRIMESTRE[trimestre]
    assert len(semanas) == 12
    assert [s[0] for s in semanas] == list(range(1, 13))

    numeros_meses = [numero for _, _, numero, _ in tc._MESES_POR_TRIMESTRE[trimestre]]
    ano = semanas[0][1].year

    # A 1a semana comeca no dia 1, 00:00:00, do primeiro mes do trimestre.
    assert semanas[0][1] == datetime(ano, numeros_meses[0], 1, 0, 0, 0)

    # A ultima semana termina no ultimo dia do ultimo mes do trimestre, 23:59:59.
    ultimo_mes = numeros_meses[-1]
    ultimo_dia_do_mes = calendar.monthrange(ano, ultimo_mes)[1]
    assert semanas[-1][2] == datetime(ano, ultimo_mes, ultimo_dia_do_mes, 23, 59, 59)

    # Semanas consecutivas: fim de uma = inicio da proxima menos 1 segundo.
    for (_, _, fim_atual), (_, inicio_proxima, _) in zip(semanas, semanas[1:]):
        assert inicio_proxima == fim_atual + timedelta(seconds=1)


@pytest.mark.parametrize('trimestre,label_esperado', [
    ('q1', '2º Trimestre (Abril–Junho)'),
    ('q2', '3º Trimestre (Julho–Setembro)'),
    ('q3', '4º Trimestre (Outubro–Dezembro)'),
])
def test_get_periodo_label(app, trimestre, label_esperado):
    with app.test_request_context():
        session['trimestre'] = trimestre
        assert tc.get_periodo_label() == label_esperado


def test_get_trimestre_default_eh_q1_quando_sessao_vazia(app):
    with app.test_request_context():
        assert tc.get_trimestre() == 'q1'
        assert tc.get_meses() == tc.Q1_MESES
        assert tc.get_master_semanas() == tc.Q1_MASTER_SEMANAS


@pytest.mark.parametrize('trimestre', TRIMESTRES)
def test_get_primeiro_mes_slug(app, trimestre):
    with app.test_request_context():
        session['trimestre'] = trimestre
        slug_esperado = tc._MESES_POR_TRIMESTRE[trimestre][0][0]
        assert tc.get_primeiro_mes_slug() == slug_esperado


@pytest.mark.parametrize('trimestre,data_referencia,semana_esperada', [
    ('q3', datetime(2026, 10, 1, 0, 0, 0), 1),
    ('q3', datetime(2026, 10, 7, 23, 59, 59), 1),
    ('q3', datetime(2026, 10, 8, 0, 0, 0), 2),
    ('q3', datetime(2026, 11, 25, 12, 0, 0), 8),
    ('q3', datetime(2026, 12, 31, 23, 59, 59), 12),
    ('q1', datetime(2026, 4, 1, 0, 0, 0), 1),
    ('q2', datetime(2026, 9, 30, 23, 59, 59), 12),
])
def test_semana_global_atual_trimestre(app, trimestre, data_referencia, semana_esperada):
    with app.test_request_context():
        session['trimestre'] = trimestre
        assert tc.semana_global_atual_trimestre(data_referencia) == semana_esperada


def test_semana_1_do_q1_e_travada_para_nao_admin(app):
    with app.test_request_context():
        session['trimestre'] = 'q1'
        assert tc.semana_editavel_trimestre(
            1, can_override_past_lock=False, is_admin=False, agora=datetime(2026, 4, 1),
        ) is False


def test_semana_1_do_q1_e_liberada_para_admin(app):
    with app.test_request_context():
        session['trimestre'] = 'q1'
        assert tc.semana_editavel_trimestre(
            1, can_override_past_lock=False, is_admin=True, agora=datetime(2026, 4, 1),
        ) is True


@pytest.mark.parametrize('trimestre', ['q2', 'q3'])
def test_semana_1_nao_e_travada_fora_do_q1(app, trimestre):
    with app.test_request_context():
        session['trimestre'] = trimestre
        inicio_do_trimestre = tc._MASTER_SEMANAS_POR_TRIMESTRE[trimestre][0][1]
        assert tc.semana_editavel_trimestre(
            1, can_override_past_lock=False, is_admin=False, agora=inicio_do_trimestre,
        ) is True
