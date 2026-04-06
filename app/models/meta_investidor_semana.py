from app import db


class MetaInvestidorSemana(db.Model):
    __tablename__ = 'metas_investidor_semana'

    id = db.Column(db.Integer, primary_key=True)
    semana = db.Column(db.Integer, nullable=False, default=1)
    valor_meta = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    acoes_planejadas = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint('semana', name='uq_meta_investidor_semana'),)

    def to_dict(self) -> dict:
        return {
            'semana': self.semana,
            'valor_meta': float(self.valor_meta or 0),
            'acoes_planejadas': int(self.acoes_planejadas or 0),
        }
