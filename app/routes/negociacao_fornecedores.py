from functools import wraps

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from app import db, socketio
from app.models.exclusao_auditoria import registrar_exclusao_auditoria
from app.models.fornecedor_cadastro import FornecedorCadastro
from app.models.indicador_acao import IndicadorAcao, consultar_acoes, contar_acoes, sincronizar_acao_registro
from app.models.meta_configuracao import MetaConfiguracaoIndicador
from app.models.meta_negociacao_fornecedor import MetaNegociacaoFornecedorSemana
from app.models.negociacao_fornecedor import NEGOCIACAO_FORNECEDOR_OPCOES, NegociacaoFornecedor
from app.utils.progress import calcular_percentual_meta, calcular_percentual_planejado_realizado
from app.utils.quarter import semana_editavel, semana_padrao_preenchimento
from app.utils.trimestre_context import get_trimestre

negociacao_fornecedores_bp = Blueprint('negociacao_fornecedores', __name__)

SCOPE = 'negociacao_fornecedores'
SEMANAS_VALIDAS = set(range(1, 13))


def requer_negociacao_fornecedores_ou_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.can_access_page(SCOPE):
            abort(403)
        if request.method != 'GET' and not current_user.can_edit_page(SCOPE):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _parse_semana(valor) -> int | None:
    try:
        semana = int(valor)
    except (TypeError, ValueError):
        return None
    return semana if semana in SEMANAS_VALIDAS else None


def _fornecedores_ativos() -> list[str]:
    return [item.nome for item in FornecedorCadastro.query.filter_by(ativo=True).order_by(FornecedorCadastro.nome).all()]


def _calcular_indicadores(semana: int, registros: list[NegociacaoFornecedor] | None = None) -> dict:
    tri = get_trimestre()
    meta = MetaNegociacaoFornecedorSemana.query.filter_by(semana=semana, trimestre=tri).first()
    valor_meta = float(meta.valor_meta) if meta else 0.0
    acoes_planejadas = int(meta.acoes_planejadas or 0) if meta else 0
    todos = registros if registros is not None else NegociacaoFornecedor.query.filter_by(semana=semana, trimestre=tri).all()
    valor_arrecadado = sum(float(item.valor_arrecadado or 0) for item in todos)
    volume_fornecimento = sum(float(item.volume_fornecimento or 0) for item in todos)
    total_negociacoes = len(todos)
    total_fornecedores = len({(item.fornecedor or '').strip() for item in todos if (item.fornecedor or '').strip()})
    acoes_realizadas = contar_acoes(SCOPE, semana)
    percentual = calcular_percentual_meta(valor_arrecadado, valor_meta)
    percentual_acoes = calcular_percentual_meta(acoes_realizadas, acoes_planejadas)
    percentual_planejado_realizado = calcular_percentual_planejado_realizado(
        valor_arrecadado,
        valor_meta,
        acoes_realizadas,
        acoes_planejadas,
    )
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope=SCOPE, trimestre=tri).first()

    return {
        'semana': semana,
        'valor_meta': valor_meta,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'valor_arrecadado': valor_arrecadado,
        'volume_fornecimento': volume_fornecimento,
        'total_negociacoes': total_negociacoes,
        'total_fornecedores': total_fornecedores,
        'acoes_planejadas': acoes_planejadas,
        'acoes_realizadas': acoes_realizadas,
        'pct_acoes': min(round(percentual_acoes, 1), 100),
        'pct_valor': min(round(percentual, 1), 100),
        'pct_planejado_realizado': percentual_planejado_realizado,
    }


def _broadcast_update(semana: int):
    tri = get_trimestre()
    registros = (
        NegociacaoFornecedor.query.filter_by(semana=semana, trimestre=tri)
        .order_by(NegociacaoFornecedor.criado_em.desc())
        .all()
    )
    socketio.emit('negociacao_fornecedores_atualizado', {
        'indicadores': _calcular_indicadores(semana, registros),
        'registros': [item.to_dict() for item in registros],
        'acoes': [item.to_dict() for item in consultar_acoes(SCOPE, semana)],
    })


def _pode_gerenciar_registro(registro: NegociacaoFornecedor) -> bool:
    return current_user.can_manage_admin() or registro.responsavel == current_user.nome.upper()


def _garantir_semana_editavel(semana: int):
    if not current_user.can_edit_page(SCOPE):
        return jsonify({'erro': 'Seu perfil possui apenas visualizacao nesta area.'}), 403
    if not semana_editavel(semana, current_user.can_override_week_lock(), current_user.can_manage_admin()):
        return jsonify({'erro': 'Esta semana esta bloqueada para edicao. Apenas perfis admin podem alterar semanas anteriores.'}), 403
    return None


def _criar_registro_acao_direta(semana: int, acao_realizada: str) -> NegociacaoFornecedor:
    tri = get_trimestre()
    fornecedores = _fornecedores_ativos()
    registro = NegociacaoFornecedor(
        fornecedor=fornecedores[0] if fornecedores else 'ACAO DIRETA',
        negociacao='PARCIAL',
        valor_arrecadado=0.0,
        volume_fornecimento=0.0,
        tipo_negociacao='ACAO DIRETA',
        observacao='REGISTRO TECNICO GERADO PARA ACAO DIRETA',
        acao_realizada=acao_realizada,
        referencia='ACAO DIRETA',
        responsavel=current_user.nome.upper(),
        semana=semana,
        trimestre=tri,
    )
    db.session.add(registro)
    return registro


@negociacao_fornecedores_bp.route('/')
@login_required
@requer_negociacao_fornecedores_ou_admin
def index():
    semana = _parse_semana(request.args.get('semana', semana_padrao_preenchimento())) or semana_padrao_preenchimento()
    tri = get_trimestre()
    registros = (
        NegociacaoFornecedor.query.filter_by(semana=semana, trimestre=tri)
        .order_by(NegociacaoFornecedor.criado_em.desc())
        .all()
    )
    return render_template(
        'negociacao_fornecedores/index.html',
        fornecedores=_fornecedores_ativos(),
        negociacoes=NEGOCIACAO_FORNECEDOR_OPCOES,
        indicadores=_calcular_indicadores(semana, registros),
        registros=registros,
        registros_json=[item.to_dict() for item in registros],
        acoes_json=[item.to_dict() for item in consultar_acoes(SCOPE, semana)],
        semana_atual=semana,
        permite_edicao=current_user.can_edit_page(SCOPE) and semana_editavel(semana, current_user.can_override_week_lock(), current_user.can_manage_admin()),
    )


@negociacao_fornecedores_bp.route('/cadastrar', methods=['POST'])
@login_required
@requer_negociacao_fornecedores_ou_admin
def cadastrar():
    dados = request.get_json(silent=True) or request.form.to_dict()
    campos_obrigatorios = ['fornecedor', 'negociacao', 'valor_arrecadado', 'tipo_negociacao', 'referencia']
    for campo in campos_obrigatorios:
        if not str(dados.get(campo) or '').strip():
            return jsonify({'erro': f'Campo obrigatorio ausente: {campo}'}), 400

    fornecedor = (dados.get('fornecedor') or '').upper().strip()
    if fornecedor not in _fornecedores_ativos():
        return jsonify({'erro': 'Fornecedor invalido.'}), 400
    negociacao = (dados.get('negociacao') or '').upper().strip()
    if negociacao not in NEGOCIACAO_FORNECEDOR_OPCOES:
        return jsonify({'erro': 'Negociacao invalida.'}), 400

    try:
        valor_arrecadado = float(dados.get('valor_arrecadado', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valor arrecadado invalido.'}), 400
    if valor_arrecadado < 0:
        valor_arrecadado = 0.0

    try:
        volume_fornecimento = float(dados.get('volume_fornecimento', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Volume de fornecimento invalido.'}), 400
    if volume_fornecimento < 0:
        volume_fornecimento = 0.0

    semana = _parse_semana(dados.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400
    bloqueio = _garantir_semana_editavel(semana)
    if bloqueio:
        return bloqueio

    tri = get_trimestre()
    novo = NegociacaoFornecedor(
        fornecedor=fornecedor,
        negociacao=negociacao,
        valor_arrecadado=valor_arrecadado,
        volume_fornecimento=volume_fornecimento,
        tipo_negociacao=(dados.get('tipo_negociacao') or '').upper().strip(),
        observacao=(dados.get('observacao') or '').upper().strip() or None,
        acao_realizada=(dados.get('acao_realizada') or '').upper().strip() or None,
        referencia=(dados.get('referencia') or '').upper().strip() or None,
        responsavel=current_user.nome.upper(),
        semana=semana,
        trimestre=tri,
    )
    db.session.add(novo)
    db.session.flush()
    sincronizar_acao_registro(
        SCOPE,
        semana,
        novo.acao_realizada,
        current_user.nome.upper(),
        novo.id,
        'negociacao_fornecedor_registro',
    )
    db.session.commit()

    _broadcast_update(semana)
    return jsonify({'sucesso': True, 'id': novo.id}), 201


@negociacao_fornecedores_bp.route('/acao', methods=['POST'])
@login_required
@requer_negociacao_fornecedores_ou_admin
def registrar_acao():
    dados = request.get_json(silent=True) or request.form.to_dict()
    reg_id = dados.get('id')
    semana = _parse_semana(dados.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400
    bloqueio = _garantir_semana_editavel(semana)
    if bloqueio:
        return bloqueio

    acao_realizada = (dados.get('acao_realizada') or '').upper().strip()
    if not acao_realizada:
        return jsonify({'erro': 'Informe a acao realizada.'}), 400

    reg = None
    if reg_id:
        reg = db.session.get(NegociacaoFornecedor, int(reg_id))
    if reg and not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode editar registros criados por voce.'}), 403

    if reg is None:
        reg = _criar_registro_acao_direta(semana, acao_realizada)
        db.session.flush()
        sincronizar_acao_registro(
            SCOPE,
            semana,
            acao_realizada,
            current_user.nome.upper(),
            reg.id,
            'negociacao_fornecedor_registro',
        )
    else:
        tri = get_trimestre()
        nova_acao = IndicadorAcao(
            scope=SCOPE,
            semana=semana,
            trimestre=tri,
            descricao=acao_realizada,
            responsavel=current_user.nome.upper(),
            registro_id=reg.id,
            registro_tipo='negociacao_fornecedor',
        )
        db.session.add(nova_acao)
    db.session.commit()
    _broadcast_update(semana)
    return jsonify({'sucesso': True})


@negociacao_fornecedores_bp.route('/registros')
@login_required
@requer_negociacao_fornecedores_ou_admin
def listar_registros():
    semana = _parse_semana(request.args.get('semana', semana_padrao_preenchimento()))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400
    tri = get_trimestre()
    registros = (
        NegociacaoFornecedor.query.filter_by(semana=semana, trimestre=tri)
        .order_by(NegociacaoFornecedor.criado_em.desc())
        .all()
    )
    return jsonify({
        'registros': [item.to_dict() for item in registros],
        'indicadores': _calcular_indicadores(semana, registros),
        'acoes': [item.to_dict() for item in consultar_acoes(SCOPE, semana)],
    })


@negociacao_fornecedores_bp.route('/acao/<int:acao_id>', methods=['DELETE'])
@login_required
@requer_negociacao_fornecedores_ou_admin
def deletar_acao(acao_id):
    acao = db.session.get(IndicadorAcao, acao_id)
    if not acao or acao.scope != SCOPE:
        return jsonify({'erro': 'Acao nao encontrada.'}), 404
    bloqueio = _garantir_semana_editavel(acao.semana)
    if bloqueio:
        return bloqueio
    if not (current_user.can_manage_admin() or acao.responsavel == current_user.nome.upper()):
        return jsonify({'erro': 'Voce so pode excluir acoes registradas por voce.'}), 403
    semana = acao.semana
    registrar_exclusao_auditoria(scope=SCOPE, instance=acao, usuario_id=current_user.id, registro_tipo='negociacao_fornecedor_acao')
    db.session.delete(acao)
    db.session.commit()
    _broadcast_update(semana)
    return jsonify({'sucesso': True})


@negociacao_fornecedores_bp.route('/registro/<int:reg_id>', methods=['PUT'])
@login_required
@requer_negociacao_fornecedores_ou_admin
def editar_registro(reg_id):
    reg = db.session.get(NegociacaoFornecedor, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode editar registros criados por voce.'}), 403
    bloqueio = _garantir_semana_editavel(reg.semana)
    if bloqueio:
        return bloqueio

    dados = request.get_json(silent=True) or request.form.to_dict()
    campos_obrigatorios = ['fornecedor', 'negociacao', 'valor_arrecadado', 'tipo_negociacao', 'referencia']
    for campo in campos_obrigatorios:
        if not str(dados.get(campo) or '').strip():
            return jsonify({'erro': f'Campo obrigatorio ausente: {campo}'}), 400

    fornecedor = (dados.get('fornecedor') or '').upper().strip()
    if fornecedor not in _fornecedores_ativos():
        return jsonify({'erro': 'Fornecedor invalido.'}), 400
    negociacao = (dados.get('negociacao') or '').upper().strip()
    if negociacao not in NEGOCIACAO_FORNECEDOR_OPCOES:
        return jsonify({'erro': 'Negociacao invalida.'}), 400

    try:
        valor_arrecadado = float(dados.get('valor_arrecadado', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valor arrecadado invalido.'}), 400
    if valor_arrecadado < 0:
        valor_arrecadado = 0.0

    try:
        volume_fornecimento = float(dados.get('volume_fornecimento', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Volume de fornecimento invalido.'}), 400
    if volume_fornecimento < 0:
        volume_fornecimento = 0.0

    reg.fornecedor = fornecedor
    reg.negociacao = negociacao
    reg.valor_arrecadado = valor_arrecadado
    reg.volume_fornecimento = volume_fornecimento
    reg.tipo_negociacao = (dados.get('tipo_negociacao') or '').upper().strip()
    reg.observacao = (dados.get('observacao') or '').upper().strip() or None
    reg.acao_realizada = (dados.get('acao_realizada') or '').upper().strip() or None
    reg.referencia = (dados.get('referencia') or '').upper().strip() or None
    sincronizar_acao_registro(
        SCOPE,
        reg.semana,
        reg.acao_realizada,
        current_user.nome.upper(),
        reg.id,
        'negociacao_fornecedor_registro',
    )

    db.session.commit()
    _broadcast_update(reg.semana)
    return jsonify({'sucesso': True, 'registro': reg.to_dict()})


@negociacao_fornecedores_bp.route('/registro/<int:reg_id>', methods=['DELETE'])
@login_required
@requer_negociacao_fornecedores_ou_admin
def deletar_registro(reg_id):
    reg = db.session.get(NegociacaoFornecedor, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode excluir registros criados por voce.'}), 403
    bloqueio = _garantir_semana_editavel(reg.semana)
    if bloqueio:
        return bloqueio

    semana = reg.semana
    registrar_exclusao_auditoria(scope=SCOPE, instance=reg, usuario_id=current_user.id, registro_tipo='negociacao_fornecedor_registro')
    db.session.delete(reg)
    db.session.commit()
    _broadcast_update(semana)
    return jsonify({'sucesso': True})
