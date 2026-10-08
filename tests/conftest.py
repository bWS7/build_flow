"""
Infraestrutura comum da suite de testes.

A aplicacao so aceita PostgreSQL (ver app/__init__.py:_resolve_database_url),
entao os testes precisam de uma instancia Postgres descartavel. Para rodar
localmente:

    docker run -d --name buildflow_test_pg -e POSTGRES_PASSWORD=test \
        -e POSTGRES_DB=buildflow_test -p 55432:5432 postgres:16-alpine

    pytest

Para apontar para outro host/porta, defina TEST_DATABASE_URL antes de rodar
o pytest.
"""
import os

import pytest
from sqlalchemy import text

TEST_DATABASE_URL = os.environ.get(
    'TEST_DATABASE_URL',
    'postgresql://postgres:test@localhost:55432/buildflow_test?sslmode=disable',
)

# Precisa ser definido ANTES de importar app/__init__.py, que le estas
# variaveis de ambiente no momento de create_app().
os.environ['DATABASE_URL'] = TEST_DATABASE_URL
os.environ.setdefault('SECRET_KEY', 'test-secret-key-nao-usar-em-producao')
os.environ.pop('SEED_ADMIN_EMAIL', None)
os.environ.pop('SEED_ADMIN_PASSWORD', None)
os.environ.setdefault('SOCKETIO_ASYNC_MODE', 'threading')
os.environ.pop('FLASK_ENV', None)  # garante que nao caia no modo "production" (cookies secure exigiriam https)
os.environ.pop('GEMINI_API_KEY', None)

from app import create_app  # noqa: E402
from app import db as _db  # noqa: E402
from app.models.user import User  # noqa: E402

# Tabelas de referencia/catalogo que nao sao limpas entre testes.
TABELAS_PRESERVADAS = {'empreendimentos'}


@pytest.fixture(scope='session')
def app():
    """Cria a aplicacao uma unica vez para toda a sessao de testes."""
    flask_app = create_app()
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield flask_app


@pytest.fixture(autouse=True)
def clean_db(app):
    """Isola cada teste truncando as tabelas de dados antes de executar."""
    with app.app_context():
        tabelas = [
            t.name for t in _db.metadata.sorted_tables
            if t.name not in TABELAS_PRESERVADAS
        ]
        if tabelas:
            nomes = ', '.join(f'"{nome}"' for nome in tabelas)
            with _db.engine.begin() as conn:
                conn.execute(text(f'TRUNCATE TABLE {nomes} RESTART IDENTITY CASCADE'))
    yield


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    """Factory para criar usuarios de teste com senha conhecida."""
    def _factory(tipo: str, email: str | None = None, senha: str = 'Senha@123', ativo: bool = True, nome: str | None = None):
        with app.app_context():
            email_final = email or f'{tipo}.teste@sousaaraujo.com.br'
            user = User(nome=nome or f'Teste {tipo}', email=email_final, tipo=tipo, ativo=ativo)
            user.set_password(senha)
            _db.session.add(user)
            _db.session.commit()
            _db.session.refresh(user)
            _db.session.expunge(user)
        return user, senha
    return _factory


@pytest.fixture
def login(client):
    """Faz login via POST /login e retorna a resposta (sem seguir redirect)."""
    def _login(email: str, senha: str):
        return client.post('/login', data={'email': email, 'senha': senha})
    return _login


@pytest.fixture
def auth_client(client, make_user, login):
    """Cria um usuario, loga e opcionalmente seleciona o trimestre ativo."""
    def _factory(tipo: str, trimestre: str | None = None, **user_kwargs):
        user, senha = make_user(tipo, **user_kwargs)
        login(user.email, senha)
        if trimestre:
            client.post('/selecionar-trimestre', data={'trimestre': trimestre})
        return client, user
    return _factory
