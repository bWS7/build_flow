"""Testes de login, throttle de tentativas e selecao de trimestre."""
import pytest

from app.routes.auth import LOGIN_MAX_ATTEMPTS


def test_login_rejeita_dominio_nao_permitido(client):
    resp = client.post('/login', data={'email': 'pessoa@gmail.com', 'senha': 'qualquer'})
    assert resp.status_code == 200
    assert '@sousaaraujo.com.br' in resp.get_data(as_text=True)


def test_login_rejeita_senha_errada(client, make_user):
    user, _senha = make_user('comercial')
    resp = client.post('/login', data={'email': user.email, 'senha': 'senha-errada'})
    assert resp.status_code == 200
    assert 'invalidos' in resp.get_data(as_text=True).lower()


def test_login_rejeita_usuario_inativo(client, make_user):
    user, senha = make_user('comercial', ativo=False)
    resp = client.post('/login', data={'email': user.email, 'senha': senha})
    assert resp.status_code == 200
    assert 'invalidos' in resp.get_data(as_text=True).lower()


def test_login_sucesso_redireciona_para_selecionar_trimestre(client, make_user):
    user, senha = make_user('comercial')
    resp = client.post('/login', data={'email': user.email, 'senha': senha})
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/selecionar-trimestre')
    with client.session_transaction() as sess:
        assert 'trimestre' not in sess


def test_login_bloqueia_apos_muitas_tentativas(client, make_user):
    user, senha = make_user('comercial')
    for _ in range(LOGIN_MAX_ATTEMPTS):
        client.post('/login', data={'email': user.email, 'senha': 'errada'})
    resp = client.post('/login', data={'email': user.email, 'senha': senha})
    assert resp.status_code == 200
    assert 'muitas tentativas' in resp.get_data(as_text=True).lower()


def test_selecionar_trimestre_requer_login(client):
    resp = client.get('/selecionar-trimestre')
    assert resp.status_code in (302, 401)


def test_tela_selecionar_trimestre_mostra_o_4o_trimestre(client, make_user, login):
    user, senha = make_user('comercial')
    login(user.email, senha)
    resp = client.get('/selecionar-trimestre')
    html = resp.get_data(as_text=True)
    assert '4º Trimestre' in html
    assert 'Outubro a Dezembro' in html


@pytest.mark.parametrize('trimestre_enviado,trimestre_esperado', [
    ('q1', 'q1'),
    ('q2', 'q2'),
    ('q3', 'q3'),
    ('q9', 'q1'),
    ('', 'q1'),
])
def test_selecionar_trimestre_valida_valor(client, make_user, login, trimestre_enviado, trimestre_esperado):
    user, senha = make_user('comercial')
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': trimestre_enviado})
    with client.session_transaction() as sess:
        assert sess.get('trimestre') == trimestre_esperado


def test_logout_limpa_trimestre_da_sessao(client, make_user, login):
    user, senha = make_user('comercial')
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': 'q3'})
    client.post('/logout')
    with client.session_transaction() as sess:
        assert 'trimestre' not in sess
