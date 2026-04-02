from app import db


class MetaGiroSemana(db.Model):
    __tablename__ = 'metas_giro_semana'

    id = db.Column(db.Integer, primary_key=True)
    semana = db.Column(db.Integer, nullable=False, default=1)
    valor_meta = db.Column(db.Numeric(15, 2), nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint('semana', name='uq_meta_giro_semana'),)

    def to_dict(self):
        return {
            'semana': self.semana,
            'valor_meta': float(self.valor_meta or 0),
        }
