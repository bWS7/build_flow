from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.models.login_throttle import LoginThrottle
from app.models.user import DOMINIO_PERMITIDO, TIPOS_LEGADOS_MAP, User

auth_bp = Blueprint('auth', __name__)

LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LOCK_SECONDS = 15 * 60

REDIRECT_MAP = {
    'admin': 'admin.dashboard',
    'admin_financeiro': 'admin.master_painel',
    'admin_engenharia': 'admin.master_painel',
    'admin_comercial': 'admin.master_painel',
    'admin_marketing': 'admin.master_painel',
    'admin_suprimentos': 'admin.master_painel',
    'admin_credito': 'admin.master_painel',
    'financeiro': 'financeiro.index',
    'engenharia': 'medicao.index',
    'comercial': 'vendas.index',
    'marketing': 'investidores.index',
    'suprimentos': 'fornecedores.index',
    'credito': 'relacionamento.index',
}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _get_login_throttle(email: str) -> LoginThrottle:
    ip_address = _client_ip()
    throttle_key = f'{ip_address}:{email}'
    throttle = LoginThrottle.query.filter_by(throttle_key=throttle_key).first()
    if throttle:
        return throttle

    now = _utcnow()
    throttle = LoginThrottle(
        throttle_key=throttle_key,
        email=email,
        ip_address=ip_address,
        attempt_count=0,
        window_started_at=now,
        last_attempt_at=now,
    )
    db.session.add(throttle)
    return throttle


def _prune_old_login_throttles() -> None:
    cutoff = _utcnow() - timedelta(days=7)
    LoginThrottle.query.filter(
        LoginThrottle.updated_at < cutoff,
        LoginThrottle.locked_until.is_(None),
    ).delete(synchronize_session=False)


def _remaining_lock_minutes(locked_until: datetime | None) -> int:
    if not locked_until:
        return 0
    remaining_seconds = max(0, int((locked_until - _utcnow()).total_seconds()))
    if remaining_seconds <= 0:
        return 0
    return max(1, remaining_seconds // 60)


def _reset_login_throttle(throttle: LoginThrottle) -> None:
    now = _utcnow()
    throttle.attempt_count = 0
    throttle.window_started_at = now
    throttle.last_attempt_at = now
    throttle.locked_until = None


def _register_failed_login(email: str) -> int:
    now = _utcnow()
    throttle = _get_login_throttle(email)

    if throttle.locked_until and throttle.locked_until <= now:
        throttle.locked_until = None
        throttle.attempt_count = 0
        throttle.window_started_at = now

    if (now - throttle.window_started_at).total_seconds() > LOGIN_WINDOW_SECONDS:
        throttle.attempt_count = 0
        throttle.window_started_at = now

    throttle.attempt_count += 1
    throttle.last_attempt_at = now

    if throttle.attempt_count >= LOGIN_MAX_ATTEMPTS:
        throttle.locked_until = now + timedelta(seconds=LOGIN_LOCK_SECONDS)
        throttle.attempt_count = 0

    _prune_old_login_throttles()
    db.session.commit()
    return _remaining_lock_minutes(throttle.locked_until)


@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # Se já tem trimestre na sessão, redireciona direto; senão vai para seleção
        if session.get('trimestre'):
            return _redirecionar(current_user.tipo)
        return redirect(url_for('auth.selecionar_trimestre'))

    erro = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        now = _utcnow()
        throttle = _get_login_throttle(email)

        if throttle.locked_until and throttle.locked_until > now:
            minutos = _remaining_lock_minutes(throttle.locked_until)
            erro = f'Muitas tentativas. Tente novamente em {minutos} minuto(s).'
            return render_template('auth/login.html', erro=erro)

        if not email.endswith(DOMINIO_PERMITIDO):
            erro = 'Acesso permitido apenas para e-mails @sousaaraujo.com.br.'
        else:
            user = User.query.filter_by(email=email, ativo=True).first()
            if user and user.check_password(senha):
                _reset_login_throttle(throttle)
                db.session.commit()
                login_user(user, remember=False)
                # Sempre pede seleção de trimestre após login
                session.pop('trimestre', None)
                return redirect(url_for('auth.selecionar_trimestre'))

            minutos = _register_failed_login(email)
            if minutos:
                erro = f'Muitas tentativas. Tente novamente em {minutos} minuto(s).'
            else:
                erro = 'E-mail ou senha invalidos.'

    return render_template('auth/login.html', erro=erro)


@auth_bp.route('/selecionar-trimestre', methods=['GET', 'POST'])
@login_required
def selecionar_trimestre():
    if request.method == 'POST':
        trimestre = request.form.get('trimestre', 'q1')
        if trimestre not in ('q1', 'q2', 'q3'):
            trimestre = 'q1'
        session['trimestre'] = trimestre
        return _redirecionar(current_user.tipo)

    return render_template('auth/selecionar_trimestre.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    session.pop('trimestre', None)
    logout_user()
    flash('Sessao encerrada com sucesso.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/em-construcao')
@login_required
def em_construcao():
    return render_template('auth/em_construcao.html')


def _redirecionar(tipo: str):
    from app.utils.trimestre_context import get_trimestre, get_primeiro_mes_slug
    tri = get_trimestre()
    primeiro_mes = get_primeiro_mes_slug()

    tipo_normalizado = TIPOS_LEGADOS_MAP.get(str(tipo or '').strip().lower(), str(tipo or '').strip().lower())
    destino = REDIRECT_MAP.get(tipo_normalizado, 'auth.login')
    if destino == 'financeiro.index':
        return redirect(url_for(destino, semana=2))
    if destino == 'medicao.index':
        return redirect(url_for(destino, semana=2))
    if destino == 'fornecedores.index':
        return redirect(url_for(destino, semana=2))
    if destino == 'giro.index':
        return redirect(url_for(destino, semana=2))
    if destino == 'relacionamento.index':
        return redirect(url_for(destino, semana=2))
    if destino == 'vendas.index':
        return redirect(url_for(destino, mes=primeiro_mes, semana=2))
    if destino == 'investidores.index':
        return redirect(url_for(destino, mes=primeiro_mes, semana=2))
    return redirect(url_for(destino))
