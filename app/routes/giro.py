from functools import wraps

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from app import db, socketio
from app.models.giro import NEGOCIACAO_GIRO_OPCOES, ORIGENS_GIRO, GiroCaptacao
from app.models.meta_giro import MetaGiroSemana
from app.models.meta_configuracao import MetaConfiguracaoIndicador


giro_bp = Blueprint('giro', __name__)

SEMANAS_VALIDAS = set(range(1, 13))


def requer_giro_ou_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.can_access_page('giro'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _parse_semana(valor) -> int | None:
    try:
        semana = int(valor)
    except (TypeError, ValueError):
        return None
    return semana if semana in SEMANAS_VALIDAS else None


def _calcular_indicadores_giro(semana: int, registros: list[GiroCaptacao] | None = None) -> dict:
    meta = MetaGiroSemana.query.filter_by(semana=semana).first()
    valor_meta = float(meta.valor_meta) if meta else 0.0
    acoes_planejadas = int(meta.acoes_planejadas or 0) if meta else 0
    todos = registros if registros is not None else GiroCaptacao.query.filter_by(semana=semana).all()
    valor_captado = sum(float(item.valor_captado or 0) for item in todos)
    total_captacoes = len(todos)
    total_origens = len({(item.origem or '').strip() for item in todos if (item.origem or '').strip()})
    acoes_realizadas = sum(1 for item in todos if (item.acao_realizada or '').strip())
    percentual = (valor_captado / valor_meta * 100) if valor_meta > 0 else 0
    percentual_acoes = (acoes_realizadas / acoes_planejadas * 100) if acoes_planejadas > 0 else 0
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope='giro').first()

    return {
        'semana': semana,
        'valor_meta': valor_meta,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'valor_captado': valor_captado,
        'total_captacoes': total_captacoes,
        'total_origens': total_origens,
        'acoes_planejadas': acoes_planejadas,
        'acoes_realizadas': acoes_realizadas,
        'pct_acoes': min(round(percentual_acoes, 1), 100),
        'pct_valor': min(round(percentual, 1), 100),
    }


def resumir_giro_trimestre() -> dict:
    registros = GiroCaptacao.query.filter(GiroCaptacao.semana.in_(range(1, 13))).all()
    metas = MetaGiroSemana.query.filter(MetaGiroSemana.semana.in_(range(1, 13))).all()
    valor_realizado = sum(float(item.valor_captado or 0) for item in registros)
    valor_meta = sum(float(item.valor_meta or 0) for item in metas)
    acoes_planejadas = sum(int(item.acoes_planejadas or 0) for item in metas)
    acoes_realizadas = sum(1 for item in registros if (item.acao_realizada or '').strip())
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope='giro').first()
    return {
        'valor_realizado': valor_realizado,
        'valor_meta': valor_meta,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'percentual_atingimento': round((valor_realizado / valor_meta) * 100, 1) if valor_meta > 0 else 0.0,
        'total_captacoes': len(registros),
        'total_origens': len({(item.origem or '').strip() for item in registros if (item.origem or '').strip()}),
        'acoes_planejadas': acoes_planejadas,
        'acoes_realizadas': acoes_realizadas,
        'percentual_acoes': round((acoes_realizadas / acoes_planejadas) * 100, 1) if acoes_planejadas > 0 else 0.0,
    }


def _broadcast_update_giro(semana: int):
    registros = (
        GiroCaptacao.query.filter_by(semana=semana)
        .order_by(GiroCaptacao.criado_em.desc())
        .all()
    )
    socketio.emit('giro_atualizado', {
        'indicadores': _calcular_indicadores_giro(semana, registros),
        'registros': [item.to_dict() for item in registros],
    })


def _pode_gerenciar_registro(registro: GiroCaptacao) -> bool:
    return current_user.can_manage_admin() or registro.responsavel == current_user.nome.upper()


@giro_bp.route('/')
@login_required
@requer_giro_ou_admin
def index():
    semana = _parse_semana(request.args.get('semana', 1)) or 1
    registros = (
        GiroCaptacao.query.filter_by(semana=semana)
        .order_by(GiroCaptacao.criado_em.desc())
        .all()
    )
    return render_template(
        'giro/index.html',
        origens=ORIGENS_GIRO,
        negociacoes=NEGOCIACAO_GIRO_OPCOES,
        indicadores=_calcular_indicadores_giro(semana, registros),
        registros=registros,
        registros_json=[item.to_dict() for item in registros],
        semana_atual=semana,
    )


@giro_bp.route('/cadastrar', methods=['POST'])
@login_required
@requer_giro_ou_admin
def cadastrar():
    dados = request.get_json(silent=True) or request.form.to_dict()
    campos_obrigatorios = ['origem', 'negociacao', 'valor_captado', 'tipo_negociacao', 'referencia']
    for campo in campos_obrigatorios:
        if not str(dados.get(campo) or '').strip():
            return jsonify({'erro': f'Campo obrigatorio ausente: {campo}'}), 400

    origem = (dados.get('origem') or '').upper().strip()
    if origem not in ORIGENS_GIRO:
        return jsonify({'erro': 'Origem invalida.'}), 400
    negociacao = (dados.get('negociacao') or '').upper().strip()
    if negociacao not in NEGOCIACAO_GIRO_OPCOES:
        return jsonify({'erro': 'Negociacao invalida.'}), 400

    try:
        valor_captado = float(dados.get('valor_captado', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valor captado invalido.'}), 400
    if valor_captado < 0:
        valor_captado = 0.0

    semana = _parse_semana(dados.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400

    novo = GiroCaptacao(
        origem=origem,
        negociacao=negociacao,
        valor_captado=valor_captado,
        tipo_negociacao=(dados.get('tipo_negociacao') or '').upper().strip(),
        observacao=(dados.get('observacao') or '').upper().strip() or None,
        acao_realizada=(dados.get('acao_realizada') or '').upper().strip() or None,
        referencia=(dados.get('referencia') or '').upper().strip() or None,
        responsavel=current_user.nome.upper(),
        semana=semana,
    )
    db.session.add(novo)
    db.session.commit()

    _broadcast_update_giro(semana)
    return jsonify({'sucesso': True, 'id': novo.id}), 201


@giro_bp.route('/acao', methods=['POST'])
@login_required
@requer_giro_ou_admin
def registrar_acao():
    dados = request.get_json(silent=True) or request.form.to_dict()
    reg_id = dados.get('id')
    semana = _parse_semana(dados.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400

    reg = None
    if reg_id:
        reg = db.session.get(GiroCaptacao, int(reg_id))
    else:
        query = GiroCaptacao.query.filter_by(semana=semana)
        if current_user.tipo != 'admin':
            query = query.filter_by(responsavel=current_user.nome.upper())
        reg = query.order_by(GiroCaptacao.criado_em.desc()).first()

    if not reg:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode editar registros criados por voce.'}), 403

    acao_realizada = (dados.get('acao_realizada') or '').upper().strip()
    if not acao_realizada:
        return jsonify({'erro': 'Informe a acao realizada.'}), 400

    reg.acao_realizada = acao_realizada
    db.session.commit()
    _broadcast_update_giro(reg.semana)
    return jsonify({'sucesso': True, 'registro': reg.to_dict()})


@giro_bp.route('/registros')
@login_required
@requer_giro_ou_admin
def listar_registros():
    semana = _parse_semana(request.args.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400
    registros = (
        GiroCaptacao.query.filter_by(semana=semana)
        .order_by(GiroCaptacao.criado_em.desc())
        .all()
    )
    return jsonify({
        'registros': [item.to_dict() for item in registros],
        'indicadores': _calcular_indicadores_giro(semana, registros),
    })


@giro_bp.route('/registro/<int:reg_id>', methods=['PUT'])
@login_required
@requer_giro_ou_admin
def editar_registro(reg_id):
    reg = db.session.get(GiroCaptacao, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode editar registros criados por voce.'}), 403

    dados = request.get_json(silent=True) or request.form.to_dict()
    campos_obrigatorios = ['origem', 'negociacao', 'valor_captado', 'tipo_negociacao', 'referencia']
    for campo in campos_obrigatorios:
        if not str(dados.get(campo) or '').strip():
            return jsonify({'erro': f'Campo obrigatorio ausente: {campo}'}), 400

    origem = (dados.get('origem') or '').upper().strip()
    if origem not in ORIGENS_GIRO:
        return jsonify({'erro': 'Origem invalida.'}), 400
    negociacao = (dados.get('negociacao') or '').upper().strip()
    if negociacao not in NEGOCIACAO_GIRO_OPCOES:
        return jsonify({'erro': 'Negociacao invalida.'}), 400

    try:
        valor_captado = float(dados.get('valor_captado', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valor captado invalido.'}), 400
    if valor_captado < 0:
        valor_captado = 0.0

    reg.origem = origem
    reg.negociacao = negociacao
    reg.valor_captado = valor_captado
    reg.tipo_negociacao = (dados.get('tipo_negociacao') or '').upper().strip()
    reg.observacao = (dados.get('observacao') or '').upper().strip() or None
    reg.acao_realizada = (dados.get('acao_realizada') or '').upper().strip() or None
    reg.referencia = (dados.get('referencia') or '').upper().strip() or None

    db.session.commit()
    _broadcast_update_giro(reg.semana)
    return jsonify({'sucesso': True, 'registro': reg.to_dict()})


@giro_bp.route('/registro/<int:reg_id>', methods=['DELETE'])
@login_required
@requer_giro_ou_admin
def deletar_registro(reg_id):
    reg = db.session.get(GiroCaptacao, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode excluir registros criados por voce.'}), 403

    semana = reg.semana
    db.session.delete(reg)
    db.session.commit()
    _broadcast_update_giro(semana)
    return jsonify({'sucesso': True})
