from app import db


class MetaVendaVarejo(db.Model):
    __tablename__ = 'metas_venda_varejo'

    id = db.Column(db.Integer, primary_key=True)
    mes = db.Column(db.String(20), nullable=False, unique=True)
    valor_meta = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    quantidade_meta = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self) -> dict:
        return {
            'mes': self.mes,
            'quantidade_meta': int(self.quantidade_meta or 0),
        }
