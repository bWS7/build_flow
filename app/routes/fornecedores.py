from functools import wraps

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from app import db, socketio
from app.models.empreendimento import Empreendimento
from app.models.fornecedor import FornecedorRegistro, SITUACAO_FORNECEDOR_OPCOES
from app.models.meta_fornecedor import MetaFornecedorSemana
from app.models.meta_configuracao import MetaConfiguracaoIndicador


fornecedores_bp = Blueprint('fornecedores', __name__)

SEMANAS_VALIDAS = set(range(1, 13))


def requer_fornecedores_ou_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.can_access_page('fornecedores'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _parse_semana(valor) -> int | None:
    try:
        semana = int(valor)
    except (TypeError, ValueError):
        return None
    return semana if semana in SEMANAS_VALIDAS else None


def _situacao_conta_como_negociado(situacao: str | None) -> bool:
    return (situacao or '').upper().strip() in {'SIM (INTEGRAL)', 'SIM (PARCIAL)'}


def _calcular_indicadores_fornecedores(semana: int, registros: list[FornecedorRegistro] | None = None) -> dict:
    meta = MetaFornecedorSemana.query.filter_by(semana=semana).first()
    valor_meta = float(meta.valor_meta) if meta else 0.0
    acoes_planejadas = int(meta.acoes_planejadas or 0) if meta else 0
    todos = registros if registros is not None else FornecedorRegistro.query.filter_by(semana=semana).all()
    valor_negociado = sum(
        float(item.valor_negociado or 0)
        for item in todos
        if _situacao_conta_como_negociado(item.situacao)
    )
    total_negociacoes = sum(1 for item in todos if _situacao_conta_como_negociado(item.situacao))
    total_fornecedores = len({(item.nome_fornecedor or '').strip() for item in todos if (item.nome_fornecedor or '').strip()})
    total_empreendimentos = len({(item.empreendimento or '').strip() for item in todos if (item.empreendimento or '').strip()})
    acoes_realizadas = sum(1 for item in todos if (item.acao_realizada or '').strip())
    percentual = (valor_negociado / valor_meta * 100) if valor_meta > 0 else 0
    percentual_acoes = (acoes_realizadas / acoes_planejadas * 100) if acoes_planejadas > 0 else 0
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope='fornecedores').first()

    return {
        'semana': semana,
        'valor_meta': valor_meta,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'valor_negociado': valor_negociado,
        'total_negociacoes': total_negociacoes,
        'total_fornecedores': total_fornecedores,
        'total_empreendimentos': total_empreendimentos,
        'acoes_planejadas': acoes_planejadas,
        'acoes_realizadas': acoes_realizadas,
        'pct_acoes': min(round(percentual_acoes, 1), 100),
        'pct_valor': min(round(percentual, 1), 100),
    }


def resumir_fornecedores_trimestre() -> dict:
    registros = FornecedorRegistro.query.filter(FornecedorRegistro.semana.in_(range(1, 13))).all()
    metas = MetaFornecedorSemana.query.filter(MetaFornecedorSemana.semana.in_(range(1, 13))).all()
    valor_realizado = sum(
        float(item.valor_negociado or 0)
        for item in registros
        if _situacao_conta_como_negociado(item.situacao)
    )
    valor_meta = sum(float(item.valor_meta or 0) for item in metas)
    acoes_planejadas = sum(int(item.acoes_planejadas or 0) for item in metas)
    acoes_realizadas = sum(1 for item in registros if (item.acao_realizada or '').strip())
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope='fornecedores').first()
    return {
        'valor_realizado': valor_realizado,
        'valor_meta': valor_meta,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'percentual_atingimento': round((valor_realizado / valor_meta) * 100, 1) if valor_meta > 0 else 0.0,
        'total_negociacoes': sum(1 for item in registros if _situacao_conta_como_negociado(item.situacao)),
        'total_fornecedores': len({(item.nome_fornecedor or '').strip() for item in registros if (item.nome_fornecedor or '').strip()}),
        'total_empreendimentos': len({(item.empreendimento or '').strip() for item in registros if (item.empreendimento or '').strip()}),
        'acoes_planejadas': acoes_planejadas,
        'acoes_realizadas': acoes_realizadas,
        'percentual_acoes': round((acoes_realizadas / acoes_planejadas) * 100, 1) if acoes_planejadas > 0 else 0.0,
    }


def _broadcast_update_fornecedores(semana: int):
    registros = (
        FornecedorRegistro.query.filter_by(semana=semana)
        .order_by(FornecedorRegistro.criado_em.desc())
        .all()
    )
    socketio.emit('fornecedores_atualizado', {
        'indicadores': _calcular_indicadores_fornecedores(semana, registros),
        'registros': [item.to_dict() for item in registros],
    })


def _pode_gerenciar_registro(registro: FornecedorRegistro) -> bool:
    return current_user.can_manage_admin() or registro.responsavel == current_user.nome.upper()


@fornecedores_bp.route('/')
@login_required
@requer_fornecedores_ou_admin
def index():
    semana = _parse_semana(request.args.get('semana', 1)) or 1
    empreendimentos = Empreendimento.query.filter_by(ativo=True).order_by(Empreendimento.nome).all()
    registros = (
        FornecedorRegistro.query.filter_by(semana=semana)
        .order_by(FornecedorRegistro.criado_em.desc())
        .all()
    )
    return render_template(
        'fornecedores/index.html',
        empreendimentos=empreendimentos,
        situacoes=SITUACAO_FORNECEDOR_OPCOES,
        indicadores=_calcular_indicadores_fornecedores(semana, registros),
        registros=registros,
        registros_json=[item.to_dict() for item in registros],
        semana_atual=semana,
    )


@fornecedores_bp.route('/cadastrar', methods=['POST'])
@login_required
@requer_fornecedores_ou_admin
def cadastrar():
    dados = request.get_json(silent=True) or request.form.to_dict()
    campos_obrigatorios = [
        'empreendimento', 'nome_fornecedor', 'servico_prestado',
        'email', 'telefone', 'situacao', 'valor_negociado',
    ]
    for campo in campos_obrigatorios:
        if not str(dados.get(campo) or '').strip():
            return jsonify({'erro': f'Campo obrigatorio ausente: {campo}'}), 400

    empreendimento = (dados.get('empreendimento') or '').upper().strip()
    if not Empreendimento.query.filter_by(nome=empreendimento, ativo=True).first():
        return jsonify({'erro': 'Empreendimento invalido.'}), 400

    situacao = (dados.get('situacao') or '').upper().strip()
    if situacao not in SITUACAO_FORNECEDOR_OPCOES:
        return jsonify({'erro': 'Situacao invalida.'}), 400

    try:
        valor_negociado = float(dados.get('valor_negociado', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valor negociado invalido.'}), 400
    if valor_negociado < 0:
        valor_negociado = 0.0

    semana = _parse_semana(dados.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400

    novo = FornecedorRegistro(
        empreendimento=empreendimento,
        nome_fornecedor=(dados.get('nome_fornecedor') or '').upper().strip(),
        servico_prestado=(dados.get('servico_prestado') or '').upper().strip(),
        email=(dados.get('email') or '').strip(),
        telefone=(dados.get('telefone') or '').strip(),
        situacao=situacao,
        valor_negociado=valor_negociado,
        observacao=(dados.get('observacao') or '').upper().strip() or None,
        acao_realizada=(dados.get('acao_realizada') or '').upper().strip() or None,
        responsavel=current_user.nome.upper(),
        semana=semana,
    )
    db.session.add(novo)
    db.session.commit()

    _broadcast_update_fornecedores(semana)
    return jsonify({'sucesso': True, 'id': novo.id}), 201


@fornecedores_bp.route('/acao', methods=['POST'])
@login_required
@requer_fornecedores_ou_admin
def registrar_acao():
    dados = request.get_json(silent=True) or request.form.to_dict()
    reg_id = dados.get('id')
    semana = _parse_semana(dados.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400

    reg = None
    if reg_id:
        reg = db.session.get(FornecedorRegistro, int(reg_id))
    else:
        query = FornecedorRegistro.query.filter_by(semana=semana)
        if current_user.tipo != 'admin':
            query = query.filter_by(responsavel=current_user.nome.upper())
        reg = query.order_by(FornecedorRegistro.criado_em.desc()).first()

    if not reg:
        return jsonify({'erro': 'Fornecedor nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode editar registros criados por voce.'}), 403

    acao_realizada = (dados.get('acao_realizada') or '').upper().strip()
    if not acao_realizada:
        return jsonify({'erro': 'Informe a acao realizada.'}), 400

    reg.acao_realizada = acao_realizada
    db.session.commit()
    _broadcast_update_fornecedores(reg.semana)
    return jsonify({'sucesso': True, 'registro': reg.to_dict()})


@fornecedores_bp.route('/registros')
@login_required
@requer_fornecedores_ou_admin
def listar_registros():
    semana = _parse_semana(request.args.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400
    registros = (
        FornecedorRegistro.query.filter_by(semana=semana)
        .order_by(FornecedorRegistro.criado_em.desc())
        .all()
    )
    return jsonify({
        'registros': [item.to_dict() for item in registros],
        'indicadores': _calcular_indicadores_fornecedores(semana, registros),
    })


@fornecedores_bp.route('/registro/<int:reg_id>', methods=['PUT'])
@login_required
@requer_fornecedores_ou_admin
def editar_registro(reg_id):
    reg = db.session.get(FornecedorRegistro, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode editar registros criados por voce.'}), 403

    dados = request.get_json(silent=True) or request.form.to_dict()
    campos_obrigatorios = [
        'empreendimento', 'nome_fornecedor', 'servico_prestado',
        'email', 'telefone', 'situacao', 'valor_negociado',
    ]
    for campo in campos_obrigatorios:
        if not str(dados.get(campo) or '').strip():
            return jsonify({'erro': f'Campo obrigatorio ausente: {campo}'}), 400

    empreendimento = (dados.get('empreendimento') or '').upper().strip()
    if not Empreendimento.query.filter_by(nome=empreendimento, ativo=True).first():
        return jsonify({'erro': 'Empreendimento invalido.'}), 400

    situacao = (dados.get('situacao') or '').upper().strip()
    if situacao not in SITUACAO_FORNECEDOR_OPCOES:
        return jsonify({'erro': 'Situacao invalida.'}), 400

    try:
        valor_negociado = float(dados.get('valor_negociado', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valor negociado invalido.'}), 400
    if valor_negociado < 0:
        valor_negociado = 0.0

    reg.empreendimento = empreendimento
    reg.nome_fornecedor = (dados.get('nome_fornecedor') or '').upper().strip()
    reg.servico_prestado = (dados.get('servico_prestado') or '').upper().strip()
    reg.email = (dados.get('email') or '').strip()
    reg.telefone = (dados.get('telefone') or '').strip()
    reg.situacao = situacao
    reg.valor_negociado = valor_negociado
    reg.observacao = (dados.get('observacao') or '').upper().strip() or None
    reg.acao_realizada = (dados.get('acao_realizada') or '').upper().strip() or None

    db.session.commit()
    _broadcast_update_fornecedores(reg.semana)
    return jsonify({'sucesso': True, 'registro': reg.to_dict()})


@fornecedores_bp.route('/registro/<int:reg_id>', methods=['DELETE'])
@login_required
@requer_fornecedores_ou_admin
def deletar_registro(reg_id):
    reg = db.session.get(FornecedorRegistro, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode excluir registros criados por voce.'}), 403

    semana = reg.semana
    db.session.delete(reg)
    db.session.commit()
    _broadcast_update_fornecedores(semana)
    return jsonify({'sucesso': True})
