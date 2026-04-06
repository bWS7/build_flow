from app import db


class MetaConfiguracaoIndicador(db.Model):
    __tablename__ = 'meta_configuracao_indicador'

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(40), nullable=False, unique=True, index=True)
    meta_base_total = db.Column(db.Numeric(15, 2), nullable=False, default=0)

    def to_dict(self) -> dict:
        return {
            'scope': self.scope,
            'meta_base_total': float(self.meta_base_total or 0),
        }
