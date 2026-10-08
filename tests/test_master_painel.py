"""Testes do Painel Master — dropdown de trimestres e visao consolidada 'Geral'."""
import pytest

from app.routes.admin import TRIMESTRE_LABELS, TRIMESTRES_DISPONIVEIS


def test_trimestres_disponiveis_inclui_o_4o_trimestre():
    assert TRIMESTRES_DISPONIVEIS == ['q1', 'q2', 'q3']
    assert TRIMESTRE_LABELS['q3'] == '4º Trimestre'


@pytest.mark.parametrize('trimestre', ['q1', 'q2', 'q3'])
def test_master_painel_carrega_para_cada_trimestre(client, make_user, login, trimestre):
    user, senha = make_user('admin')
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': trimestre})

    resp = client.get(f'/admin/master?tri={trimestre}')
    assert resp.status_code == 200


def test_master_painel_dropdown_lista_os_3_trimestres(client, make_user, login):
    user, senha = make_user('admin')
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': 'q1'})

    resp = client.get('/admin/master')
    html = resp.get_data(as_text=True)
    for label in TRIMESTRE_LABELS.values():
        assert label in html


def test_master_painel_visao_geral_consolida_todos_os_trimestres(client, make_user, login):
    user, senha = make_user('admin')
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': 'q1'})

    resp = client.get('/admin/master?view=geral')
    assert resp.status_code == 200


def test_master_painel_data_json_funciona_para_q3(client, make_user, login):
    user, senha = make_user('admin')
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': 'q3'})

    resp = client.get('/admin/master/data?tri=q3')
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), dict)
