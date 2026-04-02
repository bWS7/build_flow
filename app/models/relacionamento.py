from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import db


SITUACAO_OPCOES = ('SIM (INTEGRAL)', 'SIM (PARCIAL)', 'NÃO', 'CONTATO REJEITADO', 'LIGAR EM OUTRO MOMENTO')

try:
    BRAZIL_TZ = ZoneInfo('America/Sao_Paulo')
except ZoneInfoNotFoundError:
    # Fallback for Windows/dev environments without tzdata installed.
    BRAZIL_TZ = timezone(timedelta(hours=-3), name='America/Sao_Paulo')


def agora_brasilia() -> datetime:
    return datetime.now(BRAZIL_TZ)


def para_brasilia(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).astimezone(BRAZIL_TZ)
    return dt.astimezone(BRAZIL_TZ)


class Relacionamento(db.Model):
    __tablename__ = 'relacionamentos'

    id = db.Column(db.Integer, primary_key=True)
    empreendimento = db.Column(db.String(120), nullable=False)
    cliente = db.Column(db.String(120), nullable=False)
    telefone = db.Column(db.String(30), nullable=False)
    email_cliente = db.Column(db.String(120), nullable=True)
    tipo_contato = db.Column(db.String(60), nullable=False)
    situacao = db.Column(db.String(30), nullable=False, default='NÃO')
    observacao = db.Column(db.Text, nullable=True)
    valor = db.Column(db.Numeric(15, 2), nullable=False, default=0)
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
        situacao = 'SIM (INTEGRAL)' if self.situacao == 'SIM' else self.situacao
        return {
            'id': self.id,
            'empreendimento': self.empreendimento,
            'cliente': self.cliente,
            'telefone': self.telefone,
            'email_cliente': self.email_cliente or '',
            'tipo_contato': self.tipo_contato,
            'situacao': situacao,
            'observacao': self.observacao or '',
            'valor': float(self.valor),
            'responsavel': self.responsavel,
            'semana': self.semana,
            'criado_em': self.formatar_criado_em(),
            'criado_em_iso': criado_em.isoformat() if criado_em else '',
        }

    def __repr__(self):
        return f'<Relacionamento {self.cliente} - {self.situacao}>'
