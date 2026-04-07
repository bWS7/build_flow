from functools import wraps

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from app import db, socketio
from app.models.financeiro import BANCOS_BRASIL, NEGOCIACAO_OPCOES, FinanceiroBanco
from app.models.indicador_acao import IndicadorAcao, consultar_acoes, contar_acoes
from app.models.meta_financeiro import MetaFinanceiroSemana
from app.models.meta_configuracao import MetaConfiguracaoIndicador
from app.utils.progress import calcular_percentual_planejado_realizado
from app.utils.quarter import semana_editavel


financeiro_bp = Blueprint('financeiro', __name__)

SEMANAS_VALIDAS = set(range(1, 13))


def requer_financeiro_ou_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.can_access_page('financeiro'):
            abort(403)
        if request.method != 'GET' and not current_user.can_edit_page('financeiro'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _parse_semana(valor) -> int | None:
    try:
        semana = int(valor)
    except (TypeError, ValueError):
        return None
    return semana if semana in SEMANAS_VALIDAS else None


def _calcular_indicadores_financeiro(semana: int, registros: list[FinanceiroBanco] | None = None) -> dict:
    meta = MetaFinanceiroSemana.query.filter_by(semana=semana).first()
    valor_meta = float(meta.valor_meta) if meta else 0.0
    acoes_planejadas = int(meta.acoes_planejadas or 0) if meta else 0
    todos = registros if registros is not None else FinanceiroBanco.query.filter_by(semana=semana).all()
    valor_arrecadado = sum(float(item.valor_arrecadado or 0) for item in todos)
    total_negociacoes = len(todos)
    total_bancos = len({(item.banco or '').strip() for item in todos if (item.banco or '').strip()})
    acoes_realizadas = contar_acoes('financeiro', semana)
    percentual = (valor_arrecadado / valor_meta * 100) if valor_meta > 0 else 0
    percentual_acoes = (acoes_realizadas / acoes_planejadas * 100) if acoes_planejadas > 0 else 0
    percentual_planejado_realizado = calcular_percentual_planejado_realizado(
        valor_arrecadado,
        valor_meta,
        acoes_realizadas,
        acoes_planejadas,
    )
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope='financeiro').first()

    return {
        'semana': semana,
        'valor_meta': valor_meta,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'valor_arrecadado': valor_arrecadado,
        'total_negociacoes': total_negociacoes,
        'total_bancos': total_bancos,
        'acoes_planejadas': acoes_planejadas,
        'acoes_realizadas': acoes_realizadas,
        'pct_acoes': min(round(percentual_acoes, 1), 100),
        'pct_valor': min(round(percentual, 1), 100),
        'pct_planejado_realizado': percentual_planejado_realizado,
    }


def resumir_financeiro_bancos_trimestre() -> dict:
    registros = FinanceiroBanco.query.filter(FinanceiroBanco.semana.in_(range(1, 13))).all()
    metas = MetaFinanceiroSemana.query.filter(MetaFinanceiroSemana.semana.in_(range(1, 13))).all()
    valor_realizado = sum(float(item.valor_arrecadado or 0) for item in registros)
    valor_meta = sum(float(item.valor_meta or 0) for item in metas)
    acoes_planejadas = sum(int(item.acoes_planejadas or 0) for item in metas)
    acoes_realizadas = contar_acoes('financeiro', range(1, 13))
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope='financeiro').first()
    percentual_planejado_realizado = calcular_percentual_planejado_realizado(
        valor_realizado,
        valor_meta,
        acoes_realizadas,
        acoes_planejadas,
    )
    return {
        'valor_realizado': valor_realizado,
        'valor_meta': valor_meta,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'percentual_atingimento': round((valor_realizado / valor_meta) * 100, 1) if valor_meta > 0 else 0.0,
        'total_negociacoes': len(registros),
        'total_bancos': len({(item.banco or '').strip() for item in registros if (item.banco or '').strip()}),
        'acoes_planejadas': acoes_planejadas,
        'acoes_realizadas': acoes_realizadas,
        'percentual_acoes': round((acoes_realizadas / acoes_planejadas) * 100, 1) if acoes_planejadas > 0 else 0.0,
        'percentual_planejado_realizado': percentual_planejado_realizado,
    }


def _broadcast_update_financeiro(semana: int):
    registros = (
        FinanceiroBanco.query.filter_by(semana=semana)
        .order_by(FinanceiroBanco.criado_em.desc())
        .all()
    )
    socketio.emit('financeiro_atualizado', {
        'indicadores': _calcular_indicadores_financeiro(semana, registros),
        'registros': [item.to_dict() for item in registros],
        'acoes': [item.to_dict() for item in consultar_acoes('financeiro', semana)],
    })


def _pode_gerenciar_registro(registro: FinanceiroBanco) -> bool:
    return current_user.can_manage_admin() or registro.responsavel == current_user.nome.upper()


def _garantir_semana_editavel(semana: int):
    if not current_user.can_edit_page('financeiro'):
        return jsonify({'erro': 'Seu perfil possui apenas visualizacao nesta area.'}), 403
    if not semana_editavel(semana, current_user.can_manage_admin()):
        return jsonify({'erro': 'Esta semana esta bloqueada para edicao. Apenas o admin pode alterar semanas anteriores.'}), 403
    return None


def _criar_registro_acao_direta(semana: int, acao_realizada: str) -> FinanceiroBanco:
    registro = FinanceiroBanco(
        banco='BANCO DO BRASIL',
        negociacao='PARCIAL',
        valor_arrecadado=0.0,
        tipo_negociacao='ACAO DIRETA',
        observacao='REGISTRO TECNICO GERADO PARA ACAO DIRETA',
        acao_realizada=acao_realizada,
        referencia='ACAO DIRETA',
        responsavel=current_user.nome.upper(),
        semana=semana,
    )
    db.session.add(registro)
    return registro


@financeiro_bp.route('/')
@login_required
@requer_financeiro_ou_admin
def index():
    semana = _parse_semana(request.args.get('semana', 1)) or 1
    registros = (
        FinanceiroBanco.query.filter_by(semana=semana)
        .order_by(FinanceiroBanco.criado_em.desc())
        .all()
    )
    return render_template(
        'financeiro/index.html',
        bancos=BANCOS_BRASIL,
        negociacoes=NEGOCIACAO_OPCOES,
        indicadores=_calcular_indicadores_financeiro(semana, registros),
        registros=registros,
        registros_json=[item.to_dict() for item in registros],
        acoes_json=[item.to_dict() for item in consultar_acoes('financeiro', semana)],
        semana_atual=semana,
        permite_edicao=current_user.can_edit_page('financeiro') and semana_editavel(semana, current_user.can_manage_admin()),
    )


@financeiro_bp.route('/cadastrar', methods=['POST'])
@login_required
@requer_financeiro_ou_admin
def cadastrar():
    dados = request.get_json(silent=True) or request.form.to_dict()
    campos_obrigatorios = ['banco', 'negociacao', 'valor_arrecadado', 'tipo_negociacao', 'referencia']
    for campo in campos_obrigatorios:
        if not str(dados.get(campo) or '').strip():
            return jsonify({'erro': f'Campo obrigatorio ausente: {campo}'}), 400

    banco = (dados.get('banco') or '').upper().strip()
    if banco not in BANCOS_BRASIL:
        return jsonify({'erro': 'Banco invalido.'}), 400
    negociacao = (dados.get('negociacao') or '').upper().strip()
    if negociacao not in NEGOCIACAO_OPCOES:
        return jsonify({'erro': 'Negociacao invalida.'}), 400

    try:
        valor_arrecadado = float(dados.get('valor_arrecadado', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valor arrecadado invalido.'}), 400
    if valor_arrecadado < 0:
        valor_arrecadado = 0.0

    semana = _parse_semana(dados.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400
    bloqueio = _garantir_semana_editavel(semana)
    if bloqueio:
        return bloqueio

    novo = FinanceiroBanco(
        banco=banco,
        negociacao=negociacao,
        valor_arrecadado=valor_arrecadado,
        tipo_negociacao=(dados.get('tipo_negociacao') or '').upper().strip(),
        observacao=(dados.get('observacao') or '').upper().strip() or None,
        acao_realizada=(dados.get('acao_realizada') or '').upper().strip() or None,
        referencia=(dados.get('referencia') or '').upper().strip() or None,
        responsavel=current_user.nome.upper(),
        semana=semana,
    )
    db.session.add(novo)
    db.session.commit()

    _broadcast_update_financeiro(semana)
    return jsonify({'sucesso': True, 'id': novo.id}), 201


@financeiro_bp.route('/acao', methods=['POST'])
@login_required
@requer_financeiro_ou_admin
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
        reg = db.session.get(FinanceiroBanco, int(reg_id))
    if reg and not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode editar registros criados por voce.'}), 403
    nova_acao = IndicadorAcao(
        scope='financeiro',
        semana=semana,
        descricao=acao_realizada,
        responsavel=current_user.nome.upper(),
        registro_id=reg.id if reg else None,
        registro_tipo='financeiro' if reg else None,
    )
    db.session.add(nova_acao)
    db.session.commit()
    _broadcast_update_financeiro(semana)
    return jsonify({'sucesso': True, 'acao': nova_acao.to_dict()})


@financeiro_bp.route('/registros')
@login_required
@requer_financeiro_ou_admin
def listar_registros():
    semana = _parse_semana(request.args.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400
    registros = (
        FinanceiroBanco.query.filter_by(semana=semana)
        .order_by(FinanceiroBanco.criado_em.desc())
        .all()
    )
    return jsonify({
        'registros': [item.to_dict() for item in registros],
        'indicadores': _calcular_indicadores_financeiro(semana, registros),
        'acoes': [item.to_dict() for item in consultar_acoes('financeiro', semana)],
    })


@financeiro_bp.route('/acao/<int:acao_id>', methods=['DELETE'])
@login_required
@requer_financeiro_ou_admin
def deletar_acao(acao_id):
    acao = db.session.get(IndicadorAcao, acao_id)
    if not acao or acao.scope != 'financeiro':
        return jsonify({'erro': 'Acao nao encontrada.'}), 404
    bloqueio = _garantir_semana_editavel(acao.semana)
    if bloqueio:
        return bloqueio
    if not (current_user.can_manage_admin() or acao.responsavel == current_user.nome.upper()):
        return jsonify({'erro': 'Voce so pode excluir acoes registradas por voce.'}), 403
    semana = acao.semana
    db.session.delete(acao)
    db.session.commit()
    _broadcast_update_financeiro(semana)
    return jsonify({'sucesso': True})


@financeiro_bp.route('/registro/<int:reg_id>', methods=['PUT'])
@login_required
@requer_financeiro_ou_admin
def editar_registro(reg_id):
    reg = db.session.get(FinanceiroBanco, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode editar registros criados por voce.'}), 403
    bloqueio = _garantir_semana_editavel(reg.semana)
    if bloqueio:
        return bloqueio

    dados = request.get_json(silent=True) or request.form.to_dict()
    campos_obrigatorios = ['banco', 'negociacao', 'valor_arrecadado', 'tipo_negociacao', 'referencia']
    for campo in campos_obrigatorios:
        if not str(dados.get(campo) or '').strip():
            return jsonify({'erro': f'Campo obrigatorio ausente: {campo}'}), 400

    banco = (dados.get('banco') or '').upper().strip()
    if banco not in BANCOS_BRASIL:
        return jsonify({'erro': 'Banco invalido.'}), 400
    negociacao = (dados.get('negociacao') or '').upper().strip()
    if negociacao not in NEGOCIACAO_OPCOES:
        return jsonify({'erro': 'Negociacao invalida.'}), 400

    try:
        valor_arrecadado = float(dados.get('valor_arrecadado', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valor arrecadado invalido.'}), 400
    if valor_arrecadado < 0:
        valor_arrecadado = 0.0

    reg.banco = banco
    reg.negociacao = negociacao
    reg.valor_arrecadado = valor_arrecadado
    reg.tipo_negociacao = (dados.get('tipo_negociacao') or '').upper().strip()
    reg.observacao = (dados.get('observacao') or '').upper().strip() or None
    reg.acao_realizada = (dados.get('acao_realizada') or '').upper().strip() or None
    reg.referencia = (dados.get('referencia') or '').upper().strip() or None

    db.session.commit()
    _broadcast_update_financeiro(reg.semana)
    return jsonify({'sucesso': True, 'registro': reg.to_dict()})


@financeiro_bp.route('/registro/<int:reg_id>', methods=['DELETE'])
@login_required
@requer_financeiro_ou_admin
def deletar_registro(reg_id):
    reg = db.session.get(FinanceiroBanco, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode excluir registros criados por voce.'}), 403
    bloqueio = _garantir_semana_editavel(reg.semana)
    if bloqueio:
        return bloqueio

    semana = reg.semana
    db.session.delete(reg)
    db.session.commit()
    _broadcast_update_financeiro(semana)
    return jsonify({'sucesso': True})
