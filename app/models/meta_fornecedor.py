from app import db


class MetaFornecedorSemana(db.Model):
    __tablename__ = 'meta_fornecedor_semana'

    id = db.Column(db.Integer, primary_key=True)
    semana = db.Column(db.Integer, unique=True, nullable=False)
    valor_meta = db.Column(db.Numeric(15, 2), nullable=False, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'semana': self.semana,
            'valor_meta': float(self.valor_meta or 0),
        }

    def __repr__(self):
        return f'<MetaFornecedorSemana semana={self.semana} valor_meta={self.valor_meta}>'
