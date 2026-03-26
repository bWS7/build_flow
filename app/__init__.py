import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
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


db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
socketio = SocketIO()


def _resolve_database_url():
    database_url = (
        os.environ.get('DATABASE_URL')
        or os.environ.get('DATABASE_PUBLIC_URL')
        or 'sqlite:///local_dev.db'
    )
    database_url = database_url.replace('postgres://', 'postgresql://')
    if database_url.startswith('postgresql://') and 'sslmode=' not in database_url:
        separator = '&' if '?' in database_url else '?'
        database_url = f'{database_url}{separator}sslmode=require'
    return database_url


def create_app():
    app = Flask(__name__)

    # ── Filtros Jinja ──────────────────────────────────────────────────────────
    app.jinja_env.filters['brl'] = _format_brl
    app.jinja_env.filters['brl_int'] = _format_brl_int

    # ── Configurações ──────────────────────────────────────────────────────────
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
    app.config['SQLALCHEMY_DATABASE_URI'] = _resolve_database_url()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = True

    # Cookies seguros em produção
    if os.environ.get('FLASK_ENV') == 'production':
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # ── Extensões ──────────────────────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    # ── Blueprints ─────────────────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.relacionamento import relacionamento_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(relacionamento_bp, url_prefix='/relacionamento')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # ── Seed inicial ───────────────────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        _seed_initial_data()

    return app


def _seed_initial_data():
    """Cria usuário admin e empreendimentos padrão se não existirem."""
    from app.models.user import User
    from app.models.empreendimento import Empreendimento

    # Admin inicial
    if not User.query.filter_by(email='bruno.alves@sousaaraujo.com.br').first():
        admin = User(
            nome='BRUNO ALVES',
            email='bruno.alves@sousaaraujo.com.br',
            tipo='admin',
        )
        admin.set_password('Sousa@1234')
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
