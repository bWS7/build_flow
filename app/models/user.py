from app import db, login_manager
from flask_login import UserMixin
import bcrypt


TIPOS_VALIDOS = ('admin', 'comercial', 'financeiro', 'contas_a_receber', 'obra')
DOMINIO_PERMITIDO = '@sousaaraujo.com.br'


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(256), nullable=False)
    tipo = db.Column(db.String(30), nullable=False, default='contas_a_receber')
    ativo = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, senha: str):
        self.senha_hash = bcrypt.hashpw(
            senha.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')

    def check_password(self, senha: str) -> bool:
        return bcrypt.checkpw(senha.encode('utf-8'), self.senha_hash.encode('utf-8'))

    @staticmethod
    def validar_email(email: str) -> bool:
        return email.lower().endswith(DOMINIO_PERMITIDO)

    def __repr__(self):
        return f'<User {self.email} [{self.tipo}]>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
