import os
import secrets
from flask import Flask, flash, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from sqlalchemy import inspect, text
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from dotenv import load_dotenv

load_dotenv()


def _format_brl(value):
    """Formata número no padrão brasileiro: 1.234.567,89"""
    try:
        v = float(value)
        parts = f"{v:,.2f}".split(".")
        return parts[0].replace(",", ".") + "," + parts[1]
    except Exception:
        return "0,00"


def _format_brl_int(value):
    """Formata inteiro no padrão brasileiro sem decimais: 1.234.567"""
    try:
        return f"{int(float(value)):,}".replace(",", ".")
    except Exception:
        return "0"


def _format_user_type(value):
    labels = {
        'admin': 'ADMIN',
        'comercial': 'COMERCIAL',
        'financeiro': 'FINANCEIRO',
        'relacionamento': 'CONTAS A RECEBER',
        'contas_a_receber': 'CONTAS A RECEBER',
        'obra': 'OBRA',
    }
    return labels.get(str(value or '').strip().lower(), str(value or '').upper())


db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
socketio = SocketIO()
csrf = CSRFProtect()


def _resolve_database_url():
    database_url = (os.environ.get('DATABASE_URL') or '').strip()
    if not database_url:
        raise RuntimeError('DATABASE_URL do Railway nao configurada. A aplicacao nao usa banco local.')
    database_url = database_url.replace('postgres://', 'postgresql://')
    if not database_url.startswith('postgresql://'):
        raise RuntimeError('DATABASE_URL invalida. A aplicacao aceita apenas PostgreSQL do Railway.')
    if database_url.startswith('postgresql://') and 'sslmode=' not in database_url:
        separator = '&' if '?' in database_url else '?'
        database_url = f'{database_url}{separator}sslmode=require'
    return database_url


def _resolve_secret_key():
    return os.environ.get('SECRET_KEY') or secrets.token_urlsafe(32)


def _resolve_socketio_cors():
    allowed_origins = (os.environ.get('ALLOWED_ORIGINS') or '').strip()
    if not allowed_origins:
        return None
    return [origin.strip() for origin in allowed_origins.split(',') if origin.strip()]


def create_app():
    app = Flask(__name__)

    # ── Filtros Jinja ──────────────────────────────────────────────────────────
    app.jinja_env.filters['brl'] = _format_brl
    app.jinja_env.filters['brl_int'] = _format_brl_int
    app.jinja_env.filters['user_type_label'] = _format_user_type

    # ── Configurações ──────────────────────────────────────────────────────────
    app.config['SECRET_KEY'] = _resolve_secret_key()
    app.config['SQLALCHEMY_DATABASE_URI'] = _resolve_database_url()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = 7200
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'

    # Cookies seguros em produção
    if os.environ.get('FLASK_ENV') == 'production':
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['REMEMBER_COOKIE_SECURE'] = True

    # ── Extensões ──────────────────────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins=_resolve_socketio_cors(), async_mode='threading')

    # ── Blueprints ─────────────────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.relacionamento import relacionamento_bp
    from app.routes.admin import admin_bp
    from app.routes.investidores import investidores_bp
    from app.routes.vendas import vendas_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(relacionamento_bp, url_prefix='/relacionamento')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(investidores_bp, url_prefix='/investidores')
    app.register_blueprint(vendas_bp, url_prefix='/vendas')

    # ── Seed inicial ───────────────────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        _ensure_database_columns()
        _seed_initial_data()

    @app.after_request
    def _apply_security_headers(response):
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.errorhandler(CSRFError)
    def _handle_csrf_error(error):
        mensagem = 'Requisição bloqueada por validação de segurança. Atualize a página e tente novamente.'
        wants_json = request.path.startswith('/admin/') or request.path.startswith('/relacionamento/') or request.is_json
        if wants_json:
            return {'erro': mensagem, 'detalhe': error.description}, 400
        flash(mensagem, 'error')
        return redirect(url_for('auth.login'))

    return app


def _seed_initial_data():
    """Cria usuário admin e empreendimentos padrão se não existirem."""
    from app.models.user import User
    from app.models.empreendimento import Empreendimento

    seed_admin_email = (os.environ.get('SEED_ADMIN_EMAIL') or '').strip().lower()
    seed_admin_password = os.environ.get('SEED_ADMIN_PASSWORD') or ''
    seed_admin_name = (os.environ.get('SEED_ADMIN_NAME') or 'ADMIN').strip().upper()

    # Admin inicial controlado por variÃ¡veis de ambiente
    if seed_admin_email and seed_admin_password and not User.query.filter_by(email=seed_admin_email).first():
        admin = User(
            nome=seed_admin_name,
            email=seed_admin_email,
            tipo='admin',
        )
        admin.set_password(seed_admin_password)
        db.session.add(admin)

    # Remove placeholders de empreendimento caso existam
    placeholders = ['EMPREENDIMENTO A', 'EMPREENDIMENTO B', 'EMPREENDIMENTO C']
    Empreendimento.query.filter(Empreendimento.nome.in_(placeholders)).delete(synchronize_session=False)

    # Seed de empreendimentos reais
    _EMPREENDIMENTOS = [
        'AMETISTA', 'GRAN PORTINARI', 'MONET I', 'MONET II', 'PORTAL DO LAGO',
        'SAFIRA I', 'SAFIRA II', 'SIENA', 'SOU PLENO HOME I', 'SOU PLENO HOME II',
        'SOU PLENO JACAREÍ', 'SOU PLENO LIFE I', 'SOU PLENO LIFE II',
        'SOU PLENO PAISAGE I', 'SOU PLENO PAISAGE II', 'SOU PLENO VISAGE',
        'SOU SPECIAL MOMENT', 'SOU VIVER NOVA ODESSA', 'SOU VIVER POÁ',
        'SOU VIVER TAUBATÉ I', 'SOU VIVER TAUBATÉ II', 'TANGARÁ II',
        'SOU VIVER VICENZA', 'VIDÁLA', 'BOSQUE DAS CEREJEIRAS I',
        'BOSQUE DAS CEREJEIRAS II', 'SOU VIVER JACAREÍ DAVILINO',
        'SOU VIVER FLORENÇA', 'SOU MAIS GUAIANASES', 'SOU VIVER DIADEMA I',
        'SOU VIVER DIADEMA II', 'SOU MAIS DIADEMA', 'SOU VIVER VERONA',
        'SOU VIVER PAVENNA', 'SOU VIVER RAVENNIA II', 'SOU MAIS SUZANO',
        'SOU PLENO COTIA', 'SOU SPECIAL PLACE', 'DUMONT', 'DA VINCI',
        'SOU MAIS URBAN', 'SOU VIVER ITATIBA I', 'SOU VIVER ITATIBA II',
        'SOU VIVER ROMA', 'SOU VIVER ALTOS DE SÃO JOSÉ', 'SOU VIVER UP',
        'SOU VIVER SOROCABA',
    ]
    for nome in _EMPREENDIMENTOS:
        if not Empreendimento.query.filter_by(nome=nome).first():
            db.session.add(Empreendimento(nome=nome))

    db.session.commit()


def _ensure_database_columns():
    inspector = inspect(db.engine)
    tabelas = {
        'vendas': {
            'tipo_venda': "ALTER TABLE vendas ADD COLUMN tipo_venda VARCHAR(60) NOT NULL DEFAULT 'DIRETA'",
        },
    }

    for tabela, colunas in tabelas.items():
        existentes = {coluna['name'] for coluna in inspector.get_columns(tabela)}
        for coluna, ddl in colunas.items():
            if coluna in existentes:
                continue
            db.session.execute(text(ddl))
            db.session.commit()
