from app import db


class MetaVendaSemana(db.Model):
    __tablename__ = 'metas_venda_semana'

    id = db.Column(db.Integer, primary_key=True)
    semana = db.Column(db.Integer, nullable=False, default=1)
    quantidade_meta = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint('semana', name='uq_meta_venda_semana'),)

    def to_dict(self) -> dict:
        return {
            'semana': self.semana,
            'quantidade_meta': int(self.quantidade_meta or 0),
        }
