from app import db, login_manager
from flask_login import UserMixin
import bcrypt


ADMIN = 'admin'
ADMIN_FINANCEIRO = 'admin_financeiro'
ADMIN_ENGENHARIA = 'admin_engenharia'
ADMIN_COMERCIAL = 'admin_comercial'
ADMIN_MARKETING = 'admin_marketing'
ADMIN_SUPRIMENTOS = 'admin_suprimentos'
ADMIN_CREDITO = 'admin_credito'
FINANCEIRO = 'financeiro'
ENGENHARIA = 'engenharia'
COMERCIAL = 'comercial'
MARKETING = 'marketing'
SUPRIMENTOS = 'suprimentos'
CREDITO = 'credito'

TIPOS_LEGADOS_MAP = {
    'financeiro': FINANCEIRO,
    'obra': ENGENHARIA,
    'contas_a_receber': CREDITO,
    'gestor_financeiro': ADMIN_FINANCEIRO,
    'gestor_engenharia': ADMIN_ENGENHARIA,
    'gestor_comercial': ADMIN_COMERCIAL,
    'gestor_marketing': ADMIN_MARKETING,
    'gestor_suprimentos': ADMIN_SUPRIMENTOS,
    'gestor_credito': ADMIN_CREDITO,
    'usuario_financeiro': FINANCEIRO,
    'usuario_engenharia': ENGENHARIA,
    'usuario_comercial': COMERCIAL,
    'usuario_suprimentos': SUPRIMENTOS,
    'usuario_credito': CREDITO,
}

TIPOS_VALIDOS = (
    ADMIN,
    ADMIN_FINANCEIRO,
    ADMIN_ENGENHARIA,
    ADMIN_COMERCIAL,
    ADMIN_MARKETING,
    ADMIN_SUPRIMENTOS,
    ADMIN_CREDITO,
    FINANCEIRO,
    ENGENHARIA,
    COMERCIAL,
    MARKETING,
    SUPRIMENTOS,
    CREDITO,
)
DOMINIO_PERMITIDO = '@sousaaraujo.com.br'

ADMINS_SEGMENTADOS = {
    ADMIN_FINANCEIRO,
    ADMIN_ENGENHARIA,
    ADMIN_COMERCIAL,
    ADMIN_MARKETING,
    ADMIN_SUPRIMENTOS,
    ADMIN_CREDITO,
}

PERMISSOES_PAGINAS = {
    'financeiro': {ADMIN, ADMIN_FINANCEIRO, FINANCEIRO},
    'giro': {ADMIN, ADMIN_FINANCEIRO, FINANCEIRO},
    'medicao': {ADMIN, ADMIN_ENGENHARIA, ENGENHARIA},
    'vendas': {ADMIN, ADMIN_COMERCIAL, COMERCIAL},
    'investidores': {ADMIN, ADMIN_MARKETING, MARKETING},
    'fornecedores': {ADMIN, ADMIN_SUPRIMENTOS, SUPRIMENTOS},
    'relacionamento': {ADMIN, ADMIN_CREDITO, CREDITO},
}

PERMISSOES_PAINEIS = {
    'financeiro': {ADMIN, ADMIN_FINANCEIRO, FINANCEIRO},
    'giro': {ADMIN, ADMIN_FINANCEIRO, FINANCEIRO},
    'medicao': {ADMIN, ADMIN_ENGENHARIA, ENGENHARIA},
    'vendas': {ADMIN, ADMIN_COMERCIAL, COMERCIAL},
    'investidores': {ADMIN, ADMIN_MARKETING, MARKETING},
    'fornecedores': {ADMIN, ADMIN_SUPRIMENTOS, SUPRIMENTOS},
    'relacionamento': {ADMIN, ADMIN_CREDITO, CREDITO},
    'master': {ADMIN, *ADMINS_SEGMENTADOS},
}

PERMISSOES_METAS = {
    'financeiro': {ADMIN, ADMIN_FINANCEIRO},
    'giro': {ADMIN, ADMIN_FINANCEIRO},
    'medicao': {ADMIN, ADMIN_ENGENHARIA},
    'vendas': {ADMIN, ADMIN_COMERCIAL},
    'investidores': {ADMIN, ADMIN_MARKETING},
    'fornecedores': {ADMIN, ADMIN_SUPRIMENTOS},
    'relacionamento': {ADMIN, ADMIN_CREDITO},
}

PERMISSOES_EDICAO_PAGINAS = {
    'financeiro': {ADMIN, ADMIN_FINANCEIRO, FINANCEIRO},
    'giro': {ADMIN, ADMIN_FINANCEIRO, FINANCEIRO},
    'medicao': {ADMIN, ADMIN_ENGENHARIA, ENGENHARIA},
    'vendas': {ADMIN, ADMIN_COMERCIAL, COMERCIAL},
    'investidores': {ADMIN, ADMIN_MARKETING, MARKETING},
    'fornecedores': {ADMIN, ADMIN_SUPRIMENTOS, SUPRIMENTOS},
    'relacionamento': {ADMIN, ADMIN_CREDITO, CREDITO},
}


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(256), nullable=False)
    tipo = db.Column(db.String(30), nullable=False, default=CREDITO)
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

    def tipo_normalizado(self) -> str:
        return TIPOS_LEGADOS_MAP.get(str(self.tipo or '').strip().lower(), str(self.tipo or '').strip().lower())

    def is_admin(self) -> bool:
        return self.tipo_normalizado() == ADMIN

    def is_segmented_admin(self) -> bool:
        return self.tipo_normalizado() in ADMINS_SEGMENTADOS

    def can_access_page(self, pagina: str) -> bool:
        tipo = self.tipo_normalizado()
        if self.is_segmented_admin():
            return pagina in PERMISSOES_PAGINAS
        return tipo in PERMISSOES_PAGINAS.get(pagina, set())

    def can_edit_page(self, pagina: str) -> bool:
        return self.tipo_normalizado() in PERMISSOES_EDICAO_PAGINAS.get(pagina, set())

    def can_access_panel(self, painel: str) -> bool:
        tipo = self.tipo_normalizado()
        if self.is_segmented_admin():
            return painel in PERMISSOES_PAINEIS
        return tipo in PERMISSOES_PAINEIS.get(painel, set())

    def can_access_metas_dashboard(self) -> bool:
        return self.is_admin() or self.is_segmented_admin()

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
