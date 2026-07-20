from app import db


class FornecedorCadastro(db.Model):
    __tablename__ = 'fornecedores_cadastro'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    ativo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<FornecedorCadastro {self.nome}>'
