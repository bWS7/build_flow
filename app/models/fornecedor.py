from datetime import datetime

from app import db
from app.models.relacionamento import agora_brasilia, para_brasilia


SITUACAO_FORNECEDOR_OPCOES = (
    'SIM (INTEGRAL)',
    'SIM (PARCIAL)',
    'NAO',
)


class FornecedorRegistro(db.Model):
    __tablename__ = 'fornecedores_registros'

    id = db.Column(db.Integer, primary_key=True)
    empreendimento = db.Column(db.String(120), nullable=False)
    nome_fornecedor = db.Column(db.String(160), nullable=False)
    servico_prestado = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(160), nullable=False)
    telefone = db.Column(db.String(40), nullable=False)
    situacao = db.Column(db.String(30), nullable=False, default='NAO')
    valor_negociado = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    observacao = db.Column(db.Text, nullable=True)
    acao_realizada = db.Column(db.Text, nullable=True)
    responsavel = db.Column(db.String(120), nullable=False)
    semana = db.Column(db.Integer, nullable=False, default=1)
    trimestre = db.Column(db.String(2), nullable=False, default='q1')
    criado_em = db.Column(
        db.DateTime(timezone=True),
        default=agora_brasilia,
        nullable=False,
    )

    @property
    def criado_em_brasilia(self) -> datetime | None:
        return para_brasilia(self.criado_em)

    def formatar_criado_em(self, fmt: str = '%d/%m/%Y %H:%M') -> str:
        criado_em = self.criado_em_brasilia
        return criado_em.strftime(fmt) if criado_em else ''

    def to_dict(self):
        criado_em = self.criado_em_brasilia
        return {
            'id': self.id,
            'empreendimento': self.empreendimento,
            'nome_fornecedor': self.nome_fornecedor,
            'servico_prestado': self.servico_prestado,
            'email': self.email,
            'telefone': self.telefone,
            'situacao': self.situacao,
            'valor_negociado': float(self.valor_negociado or 0),
            'observacao': self.observacao or '',
            'acao_realizada': self.acao_realizada or '',
            'responsavel': self.responsavel,
            'semana': self.semana,
            'trimestre': self.trimestre,
            'criado_em': self.formatar_criado_em(),
            'criado_em_iso': criado_em.isoformat() if criado_em else '',
        }

    def __repr__(self):
        return f'<FornecedorRegistro {self.nome_fornecedor} - {self.empreendimento}>'
