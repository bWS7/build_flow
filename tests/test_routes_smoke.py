"""
Smoke tests: cada pagina principal precisa carregar (200, sem 500) para o
perfil de usuario correto, nos 3 trimestres existentes (q1, q2 e o novo q3).
Tambem confere que o controle de acesso por perfil continua bloqueando quem
nao deveria entrar.
"""
import pytest

TRIMESTRES = ['q1', 'q2', 'q3']

PAGINAS_POR_PERFIL = [
    ('/vendas/', 'comercial'),
    ('/investidores/', 'marketing'),
    ('/financeiro/', 'financeiro'),
    ('/giro/', 'financeiro'),
    ('/fornecedores/', 'suprimentos'),
    ('/negociacao-fornecedores/', 'suprimentos'),
    ('/medicao/', 'engenharia'),
    ('/relacionamento/', 'credito'),
]


@pytest.mark.parametrize('trimestre', TRIMESTRES)
@pytest.mark.parametrize('url,tipo', PAGINAS_POR_PERFIL)
def test_pagina_do_perfil_carrega_em_todos_os_trimestres(client, make_user, login, url, tipo, trimestre):
    user, senha = make_user(tipo)
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': trimestre})

    resp = client.get(url)
    assert resp.status_code == 200, f'{url} (perfil {tipo}) falhou no trimestre {trimestre}: {resp.status_code}'


@pytest.mark.parametrize('trimestre', TRIMESTRES)
def test_dashboard_admin_carrega_em_todos_os_trimestres(client, make_user, login, trimestre):
    user, senha = make_user('admin')
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': trimestre})

    resp = client.get('/admin/')
    assert resp.status_code == 200


def test_perfil_sem_permissao_e_bloqueado(client, make_user, login):
    user, senha = make_user('comercial')
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': 'q3'})

    resp = client.get('/financeiro/')  # comercial nao tem acesso a financeiro
    assert resp.status_code == 403


def test_pagina_requer_login(client):
    resp = client.get('/vendas/')
    assert resp.status_code in (302, 401)
