from app import db


class MetaSemana(db.Model):
    """Ações planejadas pelo ADMIN para cada semana."""
    __tablename__ = 'metas_semana'

    id = db.Column(db.Integer, primary_key=True)
    semana = db.Column(db.Integer, nullable=False, default=1)
    trimestre = db.Column(db.String(2), nullable=False, default='q1')
    acoes_planejadas = db.Column(db.Integer, nullable=False, default=0)
    valor_meta = db.Column(db.Numeric(15, 2), nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint('semana', 'trimestre', name='uq_meta_semana_trimestre'),)

    def to_dict(self):
        return {
            'semana': self.semana,
            'trimestre': self.trimestre,
            'acoes_planejadas': self.acoes_planejadas,
            'valor_meta': float(self.valor_meta),
        }
