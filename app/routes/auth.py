import time
from collections import defaultdict, deque

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.models.user import DOMINIO_PERMITIDO, User

auth_bp = Blueprint('auth', __name__)

LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LOCK_SECONDS = 15 * 60
_login_attempts = defaultdict(deque)
_login_locks = {}

REDIRECT_MAP = {
    'admin': 'admin.dashboard',
    'relacionamento': 'relacionamento.index',
    'comercial': 'auth.em_construcao',
    'financeiro': 'auth.em_construcao',
    'obra': 'auth.em_construcao',
}


def _client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _throttle_key(email: str) -> str:
    return f'{_client_ip()}:{email}'


@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _redirecionar(current_user.tipo)

    erro = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        throttle_key = _throttle_key(email)
        now = time.time()
        lock_until = _login_locks.get(throttle_key, 0)

        if lock_until > now:
            restante = int(lock_until - now)
            minutos = max(1, restante // 60)
            erro = f'Muitas tentativas. Tente novamente em {minutos} minuto(s).'
            return render_template('auth/login.html', erro=erro)

        if not email.endswith(DOMINIO_PERMITIDO):
            erro = 'Acesso permitido apenas para e-mails @sousaaraujo.com.br.'
        else:
            user = User.query.filter_by(email=email, ativo=True).first()
            if user and user.check_password(senha):
                _login_attempts.pop(throttle_key, None)
                _login_locks.pop(throttle_key, None)
                login_user(user, remember=False)
                return _redirecionar(user.tipo)

            tentativas = _login_attempts[throttle_key]
            while tentativas and now - tentativas[0] > LOGIN_WINDOW_SECONDS:
                tentativas.popleft()
            tentativas.append(now)
            if len(tentativas) >= LOGIN_MAX_ATTEMPTS:
                _login_locks[throttle_key] = now + LOGIN_LOCK_SECONDS
                tentativas.clear()
            erro = 'E-mail ou senha inválidos.'

    return render_template('auth/login.html', erro=erro)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Sessão encerrada com sucesso.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/em-construcao')
@login_required
def em_construcao():
    return render_template('auth/em_construcao.html')


def _redirecionar(tipo: str):
    destino = REDIRECT_MAP.get(tipo, 'auth.login')
    return redirect(url_for(destino))
