from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User, DOMINIO_PERMITIDO

auth_bp = Blueprint('auth', __name__)

REDIRECT_MAP = {
    'admin': 'admin.dashboard',
    'relacionamento': 'relacionamento.index',
    'comercial': 'auth.em_construcao',
    'financeiro': 'auth.em_construcao',
    'obra': 'auth.em_construcao',
}


@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _redirecionar(current_user.tipo)

    erro = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')

        # Valida domínio antes de consultar o banco
        if not email.endswith(DOMINIO_PERMITIDO):
            erro = 'Acesso permitido apenas para e-mails @sousaaraujo.com.br.'
        else:
            user = User.query.filter_by(email=email, ativo=True).first()
            if user and user.check_password(senha):
                login_user(user, remember=False)
                return _redirecionar(user.tipo)
            else:
                erro = 'E-mail ou senha inválidos.'

    return render_template('auth/login.html', erro=erro)


@auth_bp.route('/logout')
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
