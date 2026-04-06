from datetime import datetime

from app import db
from app.models.relacionamento import agora_brasilia, para_brasilia


class MedicaoRegistro(db.Model):
    __tablename__ = 'medicoes'

    id = db.Column(db.Integer, primary_key=True)
    empreendimento = db.Column(db.String(120), nullable=False)
    valor_medicao = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    observacao = db.Column(db.Text, nullable=True)
    acao_realizada = db.Column(db.Text, nullable=True)
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
            'empreendimento': self.empreendimento,
            'valor_medicao': float(self.valor_medicao or 0),
            'observacao': self.observacao or '',
            'acao_realizada': self.acao_realizada or '',
            'responsavel': self.responsavel,
            'semana': self.semana,
            'criado_em': self.formatar_criado_em(),
            'criado_em_iso': criado_em.isoformat() if criado_em else '',
        }

    def __repr__(self):
        return f'<MedicaoRegistro {self.empreendimento} - {self.valor_medicao}>'
