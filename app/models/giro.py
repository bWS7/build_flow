from datetime import datetime

from app import db
from app.models.relacionamento import agora_brasilia, para_brasilia


ORIGENS_GIRO = (
    'BANCO DO BRASIL',
    'CAIXA ECONOMICA FEDERAL',
    'ITAU UNIBANCO',
    'BRADESCO',
    'SANTANDER',
    'NUBANK',
    'BANCO INTER',
    'BTG PACTUAL',
    'SAFRA',
    'SICREDI',
    'SICOOB',
    'BANCO PAN',
    'C6 BANK',
    'XP',
    'FIDC',
    'SECURITIZADORA',
    'FUNDO DE INVESTIMENTO',
    'HOLDING',
    'INVESTIDOR PRIVADO',
    'EMPRESA PARCEIRA',
    'FACTORING',
    'CORRESPONDENTE BANCARIO',
    'OUTRA EMPRESA',
)

NEGOCIACAO_GIRO_OPCOES = (
    'INTEGRAL',
    'PARCIAL',
)


class GiroCaptacao(db.Model):
    __tablename__ = 'giro_captacoes'

    id = db.Column(db.Integer, primary_key=True)
    origem = db.Column(db.String(120), nullable=False)
    negociacao = db.Column(db.String(20), nullable=False, default='PARCIAL')
    valor_captado = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    tipo_negociacao = db.Column(db.String(120), nullable=False)
    observacao = db.Column(db.Text, nullable=True)
    acao_realizada = db.Column(db.Text, nullable=True)
    referencia = db.Column(db.String(120), nullable=True)
    responsavel = db.Column(db.String(120), nullable=False)
    semana = db.Column(db.Integer, nullable=False, default=1)
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
            'origem': self.origem,
            'negociacao': self.negociacao,
            'valor_captado': float(self.valor_captado or 0),
            'tipo_negociacao': self.tipo_negociacao,
            'observacao': self.observacao or '',
            'acao_realizada': self.acao_realizada or '',
            'referencia': self.referencia or '',
            'responsavel': self.responsavel,
            'semana': self.semana,
            'criado_em': self.formatar_criado_em(),
            'criado_em_iso': criado_em.isoformat() if criado_em else '',
        }

    def __repr__(self):
        return f'<GiroCaptacao {self.origem} - {self.tipo_negociacao}>'
