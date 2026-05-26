from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import db


SITUACAO_INVESTIDOR_OPCOES = (
    'VENDIDA',
    'CANCELADA',
    'CONFECCAO DE CONTRATO',
    'CONTRATO ASSINADO',
    'CONTRATO ASSINADO CLIENTES',
    'ENVIO UAU',
    'NOVA RESERVA',
    'PENDENTE DE ASSINATURA',
)

TIPO_VENDA_OPCOES = (
    'A VISTA / DIRETA',
    'DIRETA',
    'FINANCIADA',
    'INDIRETA',
    'PARCERIA',
    'REPASSE',
)

try:
    BRAZIL_TZ = ZoneInfo('America/Sao_Paulo')
except ZoneInfoNotFoundError:
    BRAZIL_TZ = timezone(timedelta(hours=-3), name='America/Sao_Paulo')


def agora_brasilia() -> datetime:
    return datetime.now(BRAZIL_TZ)


class Investidor(db.Model):
    __tablename__ = 'vendas_investidor'

    id = db.Column(db.Integer, primary_key=True)
    reserva = db.Column(db.String(80), nullable=False)
    data_reserva = db.Column(db.Date, nullable=False, default=date.today)
    situacao = db.Column(db.String(60), nullable=False, default='NOVA RESERVA')
    tipo_venda = db.Column(db.String(60), nullable=False, default='DIRETA')
    empreendimento = db.Column(db.String(120), nullable=False)
    bloco = db.Column(db.String(60), nullable=True)
    unidade = db.Column(db.String(60), nullable=True)
    cliente = db.Column(db.String(120), nullable=False)
    corretor = db.Column(db.String(120), nullable=True)
    imobiliaria = db.Column(db.String(120), nullable=True)
    valor_presente = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    valor_unitario = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    acao_realizada = db.Column(db.Text, nullable=True)
    criado_por = db.Column(db.String(120), nullable=False)
    criado_em = db.Column(
        db.DateTime(timezone=True),
        default=agora_brasilia,
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'reserva': self.reserva,
            'data': self.data_reserva.strftime('%d/%m/%Y') if self.data_reserva else '',
            'data_iso': self.data_reserva.isoformat() if self.data_reserva else '',
            'situacao': self.situacao,
            'tipo_venda': self.tipo_venda,
            'empreendimento': self.empreendimento,
            'bloco': self.bloco or '',
            'unidade': self.unidade or '',
            'cliente': self.cliente,
            'corretor': self.corretor or '',
            'imobiliaria': self.imobiliaria or '',
            'valor_presente': float(self.valor_presente or 0),
            'valor_unitario': float(self.valor_unitario or 0),
            'acao_realizada': self.acao_realizada or '',
            'criado_por': self.criado_por,
            'criado_em': self.criado_em.isoformat() if self.criado_em else '',
        }

    def __repr__(self):
        return f'<Investidor {self.reserva} - {self.situacao}>'
