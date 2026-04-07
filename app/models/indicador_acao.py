from sqlalchemy import or_
from collections.abc import Iterable

from app import db
from app.models.relacionamento import agora_brasilia, para_brasilia


class IndicadorAcao(db.Model):
    __tablename__ = 'indicador_acoes'

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(50), nullable=False, index=True)
    semana = db.Column(db.Integer, nullable=False, index=True)
    descricao = db.Column(db.Text, nullable=False)
    responsavel = db.Column(db.String(120), nullable=False)
    registro_id = db.Column(db.Integer, nullable=True)
    registro_tipo = db.Column(db.String(50), nullable=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=agora_brasilia, nullable=False)

    def to_dict(self) -> dict:
        data = para_brasilia(self.criado_em)
        return {
            'id': self.id,
            'scope': self.scope,
            'semana': self.semana,
            'descricao': self.descricao or '',
            'responsavel': self.responsavel or '',
            'registro_id': self.registro_id,
            'registro_tipo': self.registro_tipo or '',
            'criado_em': data.strftime('%d/%m/%Y %H:%M') if data else '',
            'data': data.strftime('%d/%m/%Y') if data else '',
        }


def consultar_acoes(scope: str, semanas) -> list[IndicadorAcao]:
    query = IndicadorAcao.query.filter_by(scope=scope)
    if isinstance(semanas, Iterable) and not isinstance(semanas, (str, bytes)):
        semanas_lista = [int(item) for item in semanas if item is not None]
        if not semanas_lista:
            return []
        query = query.filter(IndicadorAcao.semana.in_(semanas_lista))
    else:
        if semanas is None:
            return []
        query = query.filter_by(semana=int(semanas))
    return query.order_by(IndicadorAcao.criado_em.desc(), IndicadorAcao.id.desc()).all()


def contar_acoes(scope: str, semanas) -> int:
    query = db.session.query(db.func.count(IndicadorAcao.id)).filter_by(scope=scope)
    if isinstance(semanas, Iterable) and not isinstance(semanas, (str, bytes)):
        semanas_lista = [int(item) for item in semanas if item is not None]
        if not semanas_lista:
            return 0
        query = query.filter(IndicadorAcao.semana.in_(semanas_lista))
    else:
        if semanas is None:
            return 0
        query = query.filter_by(semana=int(semanas))
    return int(query.scalar() or 0)
