from app import db, login_manager
from flask_login import UserMixin
import bcrypt


ADMIN = 'admin'
GESTOR_FINANCEIRO = 'gestor_financeiro'
GESTOR_ENGENHARIA = 'gestor_engenharia'
GESTOR_COMERCIAL = 'gestor_comercial'
GESTOR_MARKETING = 'gestor_marketing'
GESTOR_SUPRIMENTOS = 'gestor_suprimentos'
GESTOR_CREDITO = 'gestor_credito'
USUARIO_FINANCEIRO = 'usuario_financeiro'
USUARIO_ENGENHARIA = 'usuario_engenharia'
USUARIO_COMERCIAL = 'usuario_comercial'
USUARIO_SUPRIMENTOS = 'usuario_suprimentos'
USUARIO_CREDITO = 'usuario_credito'

TIPOS_LEGADOS_MAP = {
    'financeiro': USUARIO_FINANCEIRO,
    'obra': USUARIO_ENGENHARIA,
    'comercial': USUARIO_COMERCIAL,
    'contas_a_receber': USUARIO_CREDITO,
}

TIPOS_VALIDOS = (
    ADMIN,
    GESTOR_FINANCEIRO,
    GESTOR_ENGENHARIA,
    GESTOR_COMERCIAL,
    GESTOR_MARKETING,
    GESTOR_SUPRIMENTOS,
    GESTOR_CREDITO,
    USUARIO_FINANCEIRO,
    USUARIO_ENGENHARIA,
    USUARIO_COMERCIAL,
    USUARIO_SUPRIMENTOS,
    USUARIO_CREDITO,
)
DOMINIO_PERMITIDO = '@sousaaraujo.com.br'

GESTORES = {
    GESTOR_FINANCEIRO,
    GESTOR_ENGENHARIA,
    GESTOR_COMERCIAL,
    GESTOR_MARKETING,
    GESTOR_SUPRIMENTOS,
    GESTOR_CREDITO,
}

PERMISSOES_PAGINAS = {
    'financeiro': {ADMIN, GESTOR_FINANCEIRO, USUARIO_FINANCEIRO},
    'giro': {ADMIN, GESTOR_FINANCEIRO, USUARIO_FINANCEIRO},
    'medicao': {ADMIN, GESTOR_ENGENHARIA, USUARIO_ENGENHARIA},
    'vendas': {ADMIN, GESTOR_COMERCIAL, USUARIO_COMERCIAL},
    'investidores': {ADMIN, GESTOR_MARKETING},
    'fornecedores': {ADMIN, GESTOR_SUPRIMENTOS, USUARIO_SUPRIMENTOS},
    'relacionamento': {ADMIN, GESTOR_CREDITO, USUARIO_CREDITO},
}

PERMISSOES_PAINEIS = {
    'financeiro': {ADMIN, GESTOR_FINANCEIRO},
    'giro': {ADMIN, GESTOR_FINANCEIRO},
    'medicao': {ADMIN, GESTOR_ENGENHARIA},
    'vendas': {ADMIN, GESTOR_COMERCIAL},
    'investidores': {ADMIN, GESTOR_MARKETING},
    'fornecedores': {ADMIN, GESTOR_SUPRIMENTOS},
    'relacionamento': {ADMIN, GESTOR_CREDITO},
    'master': {ADMIN},
}

PERMISSOES_METAS = {
    'financeiro': {ADMIN, GESTOR_FINANCEIRO},
    'giro': {ADMIN, GESTOR_FINANCEIRO},
    'medicao': {ADMIN, GESTOR_ENGENHARIA},
    'vendas': {ADMIN, GESTOR_COMERCIAL},
    'investidores': {ADMIN, GESTOR_MARKETING},
    'fornecedores': {ADMIN, GESTOR_SUPRIMENTOS},
    'relacionamento': {ADMIN, GESTOR_CREDITO},
}


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(256), nullable=False)
    tipo = db.Column(db.String(30), nullable=False, default=USUARIO_CREDITO)
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

    def is_admin(self) -> bool:
        return self.tipo_normalizado() == ADMIN

    def is_gestor(self) -> bool:
        return self.tipo_normalizado() in GESTORES

    def tipo_normalizado(self) -> str:
        return TIPOS_LEGADOS_MAP.get(str(self.tipo or '').strip().lower(), str(self.tipo or '').strip().lower())

    def can_access_page(self, pagina: str) -> bool:
        return self.tipo_normalizado() in PERMISSOES_PAGINAS.get(pagina, set())

    def can_access_panel(self, painel: str) -> bool:
        return self.tipo_normalizado() in PERMISSOES_PAINEIS.get(painel, set())

    def can_access_metas_dashboard(self) -> bool:
        return self.is_admin() or self.is_gestor()

    def can_manage_admin(self) -> bool:
        return self.is_admin()

    def can_access_meta_scope(self, scope: str) -> bool:
        return self.tipo_normalizado() in PERMISSOES_METAS.get(scope, set())

    def meta_scopes(self) -> set[str]:
        if self.is_admin():
            return set(PERMISSOES_METAS.keys())
        tipo = self.tipo_normalizado()
        return {scope for scope, perfis in PERMISSOES_METAS.items() if tipo in perfis}

    def __repr__(self):
        return f'<User {self.email} [{self.tipo}]>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
