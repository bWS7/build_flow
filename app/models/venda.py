from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import db


SITUACAO_VENDA_OPCOES = (
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

SITUACOES_FUNIL = (
    'CANCELADA',
    'CONFECCAO DE CONTRATO',
    'CONTRATO ASSINADO',
    'CONTRATO ASSINADO CLIENTES',
    'ENVIO UAU',
    'NOVA RESERVA',
    'PENDENTE DE ASSINATURA',
)

try:
    BRAZIL_TZ = ZoneInfo('America/Sao_Paulo')
except ZoneInfoNotFoundError:
    BRAZIL_TZ = timezone(timedelta(hours=-3), name='America/Sao_Paulo')


def agora_brasilia() -> datetime:
    return datetime.now(BRAZIL_TZ)


class Venda(db.Model):
    __tablename__ = 'vendas'

    id = db.Column(db.Integer, primary_key=True)
    reserva = db.Column(db.String(80), nullable=False)
    data_reserva = db.Column(db.Date, nullable=False, default=date.today)
    situacao = db.Column(db.String(60), nullable=False, default='NOVA RESERVA')
    empreendimento = db.Column(db.String(120), nullable=False)
    bloco = db.Column(db.String(60), nullable=True)
    unidade = db.Column(db.String(60), nullable=True)
    cliente = db.Column(db.String(120), nullable=False)
    corretor = db.Column(db.String(120), nullable=True)
    imobiliaria = db.Column(db.String(120), nullable=True)
    valor_presente = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    tipo_venda = db.Column(db.String(60), nullable=False, default='DIRETA')
    acao_realizada = db.Column(db.Text, nullable=True)
    criado_por = db.Column(db.String(120), nullable=False)
    criado_em = db.Column(
        db.DateTime(timezone=True),
        default=agora_brasilia,
        nullable=False,
    )

    @property
    def mes_referencia(self) -> int:
        return self.data_reserva.month if self.data_reserva else 4

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'reserva': self.reserva,
            'data': self.data_reserva.strftime('%d/%m/%Y') if self.data_reserva else '',
            'data_iso': self.data_reserva.isoformat() if self.data_reserva else '',
            'situacao': self.situacao,
            'empreendimento': self.empreendimento,
            'bloco': self.bloco or '',
            'unidade': self.unidade or '',
            'cliente': self.cliente,
            'corretor': self.corretor or '',
            'imobiliaria': self.imobiliaria or '',
            'valor_presente': float(self.valor_presente or 0),
            'tipo_venda': self.tipo_venda,
            'acao_realizada': self.acao_realizada or '',
            'criado_por': self.criado_por,
            'criado_em': self.criado_em.isoformat() if self.criado_em else '',
        }

    def __repr__(self):
        return f'<Venda {self.reserva} - {self.situacao}>'
