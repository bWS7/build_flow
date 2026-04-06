from app import db


class MetaAlteracaoAuditoria(db.Model):
    __tablename__ = 'meta_alteracao_auditoria'

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(40), nullable=False, index=True)
    periodo = db.Column(db.String(20), nullable=True, index=True)
    campo = db.Column(db.String(40), nullable=False)
    valor_anterior = db.Column(db.String(120), nullable=False, default='')
    valor_novo = db.Column(db.String(120), nullable=False, default='')
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    criado_em = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    usuario = db.relationship('User', lazy='joined')

    def to_dict(self) -> dict:
        return {
            'scope': self.scope,
            'periodo': self.periodo,
            'campo': self.campo,
            'valor_anterior': self.valor_anterior,
            'valor_novo': self.valor_novo,
            'usuario': getattr(self.usuario, 'nome', ''),
            'usuario_id': self.usuario_id,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
        }
