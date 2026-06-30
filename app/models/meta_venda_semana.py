from app import db


class MetaVendaSemana(db.Model):
    __tablename__ = 'metas_venda_semana'

    id = db.Column(db.Integer, primary_key=True)
    semana = db.Column(db.Integer, nullable=False, default=1)
    trimestre = db.Column(db.String(2), nullable=False, default='q1')
    quantidade_meta = db.Column(db.Integer, nullable=False, default=0)
    acoes_planejadas = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint('semana', 'trimestre', name='uq_meta_venda_semana_trimestre'),)

    def to_dict(self) -> dict:
        return {
            'semana': self.semana,
            'trimestre': self.trimestre,
            'quantidade_meta': int(self.quantidade_meta or 0),
            'acoes_planejadas': int(self.acoes_planejadas or 0),
        }
