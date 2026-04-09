import os
import secrets
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from sqlalchemy import inspect, text
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

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
    from app.models.user import TIPOS_LEGADOS_MAP
    normalized = TIPOS_LEGADOS_MAP.get(str(value or '').strip().lower(), str(value or '').strip().lower())
    labels = {
        'admin': 'ADMIN',
        'admin_financeiro': 'ADMIN FINANCEIRO',
        'admin_engenharia': 'ADMIN ENGENHARIA',
        'admin_comercial': 'ADMIN COMERCIAL',
        'admin_marketing': 'ADMIN MARKETING',
        'admin_suprimentos': 'ADMIN SUPRIMENTOS',
        'admin_credito': 'ADMIN CREDITO',
        'financeiro': 'FINANCEIRO',
        'engenharia': 'ENGENHARIA',
        'comercial': 'COMERCIAL',
        'marketing': 'MARKETING',
        'suprimentos': 'SUPRIMENTOS',
        'credito': 'CREDITO',
    }
    return labels.get(normalized, str(value or '').upper())


db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
socketio = SocketIO()
csrf = CSRFProtect()


def _resolve_database_url():
    database_url = (os.environ.get('DATABASE_URL') or '').strip()
    if not database_url:
        raise RuntimeError('DATABASE_URL nao configurada. A aplicacao requer um banco PostgreSQL externo.')
    database_url = database_url.replace('postgres://', 'postgresql://')
    if not database_url.startswith('postgresql://'):
        raise RuntimeError('DATABASE_URL invalida. A aplicacao aceita apenas conexoes PostgreSQL.')
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


def _resolve_socketio_async_mode():
    async_mode = (os.environ.get('SOCKETIO_ASYNC_MODE') or '').strip().lower()
    if async_mode in {'eventlet', 'threading'}:
        return async_mode
    return 'eventlet' if os.environ.get('FLASK_ENV') == 'production' else 'threading'


def _build_csp_header():
    directives = {
        'default-src': ["'self'"],
        'base-uri': ["'self'"],
        'form-action': ["'self'"],
        'frame-ancestors': ["'self'"],
        'object-src': ["'none'"],
        'script-src': [
            "'self'",
            "'unsafe-inline'",
            'https://cdnjs.cloudflare.com',
            'https://cdn.socket.io',
        ],
        'style-src': [
            "'self'",
            "'unsafe-inline'",
            'https://fonts.googleapis.com',
        ],
        'font-src': [
            "'self'",
            'https://fonts.gstatic.com',
            'data:',
        ],
        'img-src': [
            "'self'",
            'data:',
            'https:',
        ],
        'connect-src': [
            "'self'",
            'https:',
            'wss:',
        ],
        'frame-src': ["'none'"],
        'manifest-src': ["'self'"],
        'worker-src': ["'self'", 'blob:'],
        'upgrade-insecure-requests': [],
    }
    return '; '.join(
        f"{directive} {' '.join(values)}".rstrip()
        for directive, values in directives.items()
    )


def create_app():
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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
    app.config['PREFERRED_URL_SCHEME'] = 'https'

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
    socketio.init_app(
        app,
        cors_allowed_origins=_resolve_socketio_cors(),
        async_mode=_resolve_socketio_async_mode(),
    )

    # ── Blueprints ─────────────────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.relacionamento import relacionamento_bp
    from app.routes.admin import admin_bp
    from app.routes.investidores import investidores_bp
    from app.routes.vendas import vendas_bp
    from app.routes.financeiro import financeiro_bp
    from app.routes.giro import giro_bp
    from app.routes.medicao import medicao_bp
    from app.routes.fornecedores import fornecedores_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(relacionamento_bp, url_prefix='/relacionamento')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(investidores_bp, url_prefix='/investidores')
    app.register_blueprint(vendas_bp, url_prefix='/vendas')
    app.register_blueprint(financeiro_bp, url_prefix='/financeiro')
    app.register_blueprint(giro_bp, url_prefix='/giro')
    app.register_blueprint(fornecedores_bp, url_prefix='/fornecedores')
    app.register_blueprint(medicao_bp, url_prefix='/medicao')

    # ── Seed inicial ───────────────────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        _ensure_database_columns()
        _seed_initial_data()

    @app.after_request
    def _apply_security_headers(response):
        response.headers['Content-Security-Policy'] = _build_csp_header()
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        if request.endpoint == 'auth.login':
            response.headers['Cache-Control'] = 'no-store'
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.errorhandler(CSRFError)
    def _handle_csrf_error(error):
        mensagem = 'Requisição bloqueada por validação de segurança. Atualize a página e tente novamente.'
        wants_json = (
            request.path.startswith('/admin/')
            or request.path.startswith('/relacionamento/')
            or request.path.startswith('/financeiro/')
            or request.path.startswith('/giro/')
            or request.path.startswith('/fornecedores/')
            or request.path.startswith('/medicao/')
            or request.is_json
        )
        if wants_json:
            return {'erro': mensagem, 'detalhe': error.description}, 400
        flash(mensagem, 'error')
        return redirect(url_for('auth.login'))

    @app.get('/health')
    def healthcheck():
        return {'status': 'ok'}, 200

    @app.errorhandler(404)
    def _handle_not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(405)
    def _handle_method_not_allowed(error):
        return render_template('errors/405.html'), 405

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
            'acao_realizada': "ALTER TABLE vendas ADD COLUMN acao_realizada TEXT",
        },
        'vendas_investidor': {
            'acao_realizada': "ALTER TABLE vendas_investidor ADD COLUMN acao_realizada TEXT",
        },
        'financeiro_bancos': {
            'negociacao': "ALTER TABLE financeiro_bancos ADD COLUMN negociacao VARCHAR(20) NOT NULL DEFAULT 'PARCIAL'",
            'acao_realizada': "ALTER TABLE financeiro_bancos ADD COLUMN acao_realizada TEXT",
        },
        'giro_captacoes': {
            'acao_realizada': "ALTER TABLE giro_captacoes ADD COLUMN acao_realizada TEXT",
        },
        'fornecedores_registros': {
            'acao_realizada': "ALTER TABLE fornecedores_registros ADD COLUMN acao_realizada TEXT",
        },
        'medicoes': {
            'acao_realizada': "ALTER TABLE medicoes ADD COLUMN acao_realizada TEXT",
        },
        'relacionamentos': {
            'acao_realizada': "ALTER TABLE relacionamentos ADD COLUMN acao_realizada TEXT",
        },
        'metas_venda_semana': {
            'acoes_planejadas': "ALTER TABLE metas_venda_semana ADD COLUMN acoes_planejadas INTEGER NOT NULL DEFAULT 0",
        },
        'metas_investidor_semana': {
            'acoes_planejadas': "ALTER TABLE metas_investidor_semana ADD COLUMN acoes_planejadas INTEGER NOT NULL DEFAULT 0",
        },
        'metas_financeiro_semana': {
            'acoes_planejadas': "ALTER TABLE metas_financeiro_semana ADD COLUMN acoes_planejadas INTEGER NOT NULL DEFAULT 0",
        },
        'metas_giro_semana': {
            'acoes_planejadas': "ALTER TABLE metas_giro_semana ADD COLUMN acoes_planejadas INTEGER NOT NULL DEFAULT 0",
        },
        'meta_fornecedor_semana': {
            'acoes_planejadas': "ALTER TABLE meta_fornecedor_semana ADD COLUMN acoes_planejadas INTEGER NOT NULL DEFAULT 0",
        },
        'metas_medicao_semana': {
            'acoes_planejadas': "ALTER TABLE metas_medicao_semana ADD COLUMN acoes_planejadas INTEGER NOT NULL DEFAULT 0",
        },
        'exclusao_auditoria': {
            'usuario_nome': "ALTER TABLE exclusao_auditoria ADD COLUMN usuario_nome VARCHAR(120) NOT NULL DEFAULT ''",
            'usuario_email': "ALTER TABLE exclusao_auditoria ADD COLUMN usuario_email VARCHAR(120) NOT NULL DEFAULT ''",
        },
    }

    for tabela, colunas in tabelas.items():
        if not inspector.has_table(tabela):
            continue
        existentes = {coluna['name'] for coluna in inspector.get_columns(tabela)}
        for coluna, ddl in colunas.items():
            if coluna in existentes:
                continue
            db.session.execute(text(ddl))
            db.session.commit()
