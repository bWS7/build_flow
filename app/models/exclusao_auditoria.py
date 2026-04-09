import json
from datetime import date, datetime
from decimal import Decimal

from app import db


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


class ExclusaoAuditoria(db.Model):
    __tablename__ = 'exclusao_auditoria'

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(50), nullable=False, index=True)
    registro_tipo = db.Column(db.String(80), nullable=False, index=True)
    registro_id = db.Column(db.Integer, nullable=True, index=True)
    semana = db.Column(db.Integer, nullable=True, index=True)
    responsavel_registro = db.Column(db.String(120), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    payload_json = db.Column(db.Text, nullable=False, default='{}')
    criado_em = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), index=True)

    usuario = db.relationship('User', lazy='joined')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'scope': self.scope,
            'registro_tipo': self.registro_tipo,
            'registro_id': self.registro_id,
            'semana': self.semana,
            'responsavel_registro': self.responsavel_registro,
            'usuario_id': self.usuario_id,
            'usuario': getattr(self.usuario, 'nome', ''),
            'payload': json.loads(self.payload_json or '{}'),
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
        }


def _snapshot_model(instance) -> dict:
    if instance is None:
        return {}
    if hasattr(instance, 'to_dict'):
        try:
            data = instance.to_dict()
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    snapshot = {}
    for column in instance.__table__.columns:
        snapshot[column.name] = getattr(instance, column.name)
    return snapshot


def registrar_exclusao_auditoria(
    *,
    scope: str,
    instance,
    usuario_id: int,
    registro_tipo: str | None = None,
) -> ExclusaoAuditoria:
    snapshot = _snapshot_model(instance)
    auditoria = ExclusaoAuditoria(
        scope=scope,
        registro_tipo=registro_tipo or getattr(instance, '__tablename__', instance.__class__.__name__),
        registro_id=getattr(instance, 'id', None),
        semana=getattr(instance, 'semana', None),
        responsavel_registro=getattr(instance, 'responsavel', None),
        usuario_id=usuario_id,
        payload_json=json.dumps(snapshot, ensure_ascii=False, default=_json_default),
    )
    db.session.add(auditoria)
    return auditoria
