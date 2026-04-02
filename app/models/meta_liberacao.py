from app import db


class MetaLiberacaoSemana(db.Model):
    __tablename__ = 'meta_liberacoes_semana'
    __table_args__ = (
        db.UniqueConstraint('scope', 'semana', name='uq_meta_liberacao_scope_semana'),
    )

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(40), nullable=False, index=True)
    semana = db.Column(db.Integer, nullable=False, index=True)
    liberada = db.Column(db.Boolean, nullable=False, default=False)
    liberada_por = db.Column(db.String(120), nullable=True)
    liberada_em = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<MetaLiberacaoSemana {self.scope}:{self.semana} liberada={self.liberada}>'
