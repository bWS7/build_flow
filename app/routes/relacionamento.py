from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user
from functools import wraps
from app import db, socketio
from app.models.exclusao_auditoria import registrar_exclusao_auditoria
from app.models.indicador_acao import IndicadorAcao, consultar_acoes, contar_acoes, sincronizar_acao_registro
from app.models.relacionamento import Relacionamento, SITUACAO_OPCOES
from app.models.empreendimento import Empreendimento
from app.models.meta import MetaSemana
from app.models.meta_configuracao import MetaConfiguracaoIndicador
from sqlalchemy import func
from app.utils.progress import calcular_percentual_meta, calcular_percentual_planejado_realizado
from app.utils.quarter import semana_editavel, semana_padrao_preenchimento

relacionamento_bp = Blueprint('relacionamento', __name__)

TIPOS_CONTATO = ['LIGAÇÃO', 'VISITA', 'WHATSAPP', 'E-MAIL', 'REUNIÃO']
SEMANAS_VALIDAS = set(range(1, 13))
TIPO_CONTATO_PADRAO = 'WHATSAPP'
TELEFONE_PADRAO = 'NAO INFORMADO'


def _situacao_conta_como_sim(situacao: str | None) -> bool:
    situacao_normalizada = (situacao or '').upper().strip()
    return situacao_normalizada in {'SIM', 'SIM (INTEGRAL)', 'SIM (PARCIAL)'}


def _normalizar_situacao(situacao: str | None) -> str:
    situacao_normalizada = (situacao or '').upper().strip()
    return 'SIM (INTEGRAL)' if situacao_normalizada == 'SIM' else situacao_normalizada


def requer_relacionamento_ou_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.can_access_page('relacionamento'):
            abort(403)
        if request.method != 'GET' and not current_user.can_edit_page('relacionamento'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Helpers ────────────────────────────────────────────────────────────────────

def _calcular_indicadores(semana: int, registros: list[Relacionamento] | None = None) -> dict:
    meta = MetaSemana.query.filter_by(semana=semana).first()
    acoes_planejadas = meta.acoes_planejadas if meta else 0
    valor_meta = float(meta.valor_meta) if meta else 0.0
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope='relacionamento').first()

    todos = registros if registros is not None else Relacionamento.query.filter_by(semana=semana).all()
    acoes_realizadas = contar_acoes('relacionamento', semana)
    registros_sim = [r for r in todos if _situacao_conta_como_sim(r.situacao)]
    soma_valores = sum(float(r.valor) for r in registros_sim if r.valor > 0)

    pct_acoes = calcular_percentual_meta(acoes_realizadas, acoes_planejadas)
    pct_valor = calcular_percentual_meta(soma_valores, valor_meta)
    pct_planejado_realizado = calcular_percentual_planejado_realizado(
        soma_valores,
        valor_meta,
        acoes_realizadas,
        acoes_planejadas,
    )

    return {
        'semana': semana,
        'acoes_planejadas': acoes_planejadas,
        'acoes_realizadas': acoes_realizadas,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'valor_meta': valor_meta,
        'soma_valores': soma_valores,
        'pct_acoes': min(round(pct_acoes, 1), 100),
        'pct_valor': min(round(pct_valor, 1), 100),
        'pct_planejado_realizado': pct_planejado_realizado,
    }


def _broadcast_update(semana: int):
    """Emite atualização via WebSocket para todos os clientes."""
    registros = Relacionamento.query.filter_by(semana=semana)\
        .order_by(Relacionamento.criado_em.desc()).all()
    indicadores = _calcular_indicadores(semana, registros)
    socketio.emit('dados_atualizados', {
        'indicadores': indicadores,
        'registros': [r.to_dict() for r in registros],
        'acoes': [item.to_dict() for item in consultar_acoes('relacionamento', semana)],
    })


def _pode_gerenciar_registro(registro: Relacionamento) -> bool:
    return current_user.can_manage_admin() or registro.responsavel == current_user.nome.upper()


def _garantir_semana_editavel(semana: int):
    if not current_user.can_edit_page('relacionamento'):
        return jsonify({'erro': 'Seu perfil possui apenas visualizacao nesta area.'}), 403
    if not semana_editavel(semana, current_user.can_override_week_lock(), current_user.can_manage_admin()):
        return jsonify({'erro': 'Esta semana esta bloqueada para edicao. Apenas perfis admin podem alterar semanas anteriores.'}), 403
    return None


def _empreendimento_padrao() -> str:
    empreendimento = Empreendimento.query.filter_by(ativo=True).order_by(Empreendimento.nome).first()
    return empreendimento.nome if empreendimento else 'NAO INFORMADO'


def _parse_semana(valor) -> int | None:
    try:
        semana = int(valor)
    except (TypeError, ValueError):
        return None
    return semana if semana in SEMANAS_VALIDAS else None


# ── Rotas ──────────────────────────────────────────────────────────────────────

@relacionamento_bp.route('/')
@login_required
@requer_relacionamento_ou_admin
def index():
    semana = _parse_semana(request.args.get('semana', semana_padrao_preenchimento())) or semana_padrao_preenchimento()
    empreendimentos = Empreendimento.query.filter_by(ativo=True).order_by(Empreendimento.nome).all()
    registros = Relacionamento.query.filter_by(semana=semana)\
        .order_by(Relacionamento.criado_em.desc()).all()
    indicadores = _calcular_indicadores(semana, registros)

    return render_template(
        'relacionamento/index.html',
        empreendimentos=empreendimentos,
        situacoes=SITUACAO_OPCOES,
        tipos_contato=TIPOS_CONTATO,
        indicadores=indicadores,
        registros=registros,
        registros_json=[r.to_dict() for r in registros],
        acoes_json=[item.to_dict() for item in consultar_acoes('relacionamento', semana)],
        semana_atual=semana,
        permite_edicao=current_user.can_edit_page('relacionamento') and semana_editavel(semana, current_user.can_override_week_lock(), current_user.can_manage_admin()),
    )


@relacionamento_bp.route('/cadastrar', methods=['POST'])
@login_required
@requer_relacionamento_ou_admin
def cadastrar():
    dados = request.get_json(silent=True) or request.form.to_dict()

    campos_obrigatorios = ['empreendimento', 'cliente', 'situacao']
    for campo in campos_obrigatorios:
        if not dados.get(campo):
            return jsonify({'erro': f'Campo obrigatório ausente: {campo}'}), 400

    situacao = _normalizar_situacao(dados.get('situacao'))
    tipo_contato = (dados.get('tipo_contato') or TIPO_CONTATO_PADRAO).upper().strip()
    if situacao not in SITUACAO_OPCOES:
        return jsonify({'erro': 'Situação inválida.'}), 400
    if tipo_contato not in TIPOS_CONTATO:
        return jsonify({'erro': 'Tipo de contato inválido.'}), 400

    try:
        valor = float(dados.get('valor', 0) or 0)
        if valor < 0:
            valor = 0.0
    except (ValueError, TypeError):
        valor = 0.0

    semana = _parse_semana(dados.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana inválida.'}), 400

    bloqueio = _garantir_semana_editavel(semana)
    if bloqueio:
        return bloqueio

    novo = Relacionamento(
        empreendimento=dados['empreendimento'].upper().strip(),
        cliente=dados['cliente'].upper().strip(),
        telefone=(dados.get('telefone') or TELEFONE_PADRAO).upper().strip(),
        email_cliente=(dados.get('email_cliente') or '').upper().strip() or None,
        tipo_contato=tipo_contato,
        situacao=situacao,
        observacao=(dados.get('observacao') or '').upper().strip() or None,
        valor=valor,
        responsavel=current_user.nome.upper(),
        semana=semana,
    )
    db.session.add(novo)
    db.session.flush()
    sincronizar_acao_registro(
        'relacionamento',
        semana,
        (dados.get('acao_realizada') or '').upper().strip(),
        current_user.nome.upper(),
        novo.id,
        'relacionamento_registro',
    )
    db.session.commit()

    _broadcast_update(semana)
    return jsonify({'sucesso': True, 'id': novo.id}), 201


@relacionamento_bp.route('/bulk-cadastrar', methods=['POST'])
@login_required
@requer_relacionamento_ou_admin
def bulk_cadastrar():
    dados = request.get_json(silent=True) or {}
    linhas = dados.get('linhas') or []
    if not isinstance(linhas, list) or not linhas:
        return jsonify({'erro': 'Nenhuma linha valida foi informada para importacao.'}), 400

    registros_criados = []
    semanas_processadas = set()

    for indice, linha in enumerate(linhas, start=1):
        if not isinstance(linha, dict):
            return jsonify({'erro': f'Linha {indice} invalida.'}), 400

        empreendimento = (linha.get('empreendimento') or '').upper().strip()
        cliente = (linha.get('cliente') or '').upper().strip()
        situacao = _normalizar_situacao(linha.get('situacao'))
        semana = _parse_semana(linha.get('semana', 1))

        if not empreendimento or not cliente or not situacao:
            return jsonify({'erro': f'Linha {indice}: preencha empreendimento, cliente e situacao.'}), 400
        if situacao not in SITUACAO_OPCOES:
            return jsonify({'erro': f'Linha {indice}: situacao invalida.'}), 400
        if semana is None:
            return jsonify({'erro': f'Linha {indice}: semana invalida.'}), 400

        bloqueio = _garantir_semana_editavel(semana)
        if bloqueio:
            return bloqueio

        try:
            valor = float(linha.get('valor', 0) or 0)
        except (TypeError, ValueError):
            return jsonify({'erro': f'Linha {indice}: valor invalido.'}), 400
        if valor < 0:
            valor = 0.0

        novo = Relacionamento(
            empreendimento=empreendimento,
            cliente=cliente,
            telefone=TELEFONE_PADRAO,
            email_cliente=None,
            tipo_contato=TIPO_CONTATO_PADRAO,
            situacao=situacao,
            observacao=None,
            valor=valor,
            responsavel=current_user.nome.upper(),
            semana=semana,
        )
        db.session.add(novo)
        registros_criados.append(novo)
        semanas_processadas.add(semana)

    db.session.commit()

    for semana in semanas_processadas:
        _broadcast_update(semana)

    return jsonify({'sucesso': True, 'total': len(registros_criados)}), 201


@relacionamento_bp.route('/registro/<int:reg_id>', methods=['PUT'])
@login_required
@requer_relacionamento_ou_admin
def editar_registro(reg_id):
    reg = db.session.get(Relacionamento, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro não encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Você só pode editar registros criados por você.'}), 403

    dados = request.get_json(silent=True) or request.form.to_dict()
    campos_obrigatorios = ['empreendimento', 'cliente', 'telefone', 'tipo_contato', 'situacao']
    for campo in campos_obrigatorios:
        if not dados.get(campo):
            return jsonify({'erro': f'Campo obrigatório ausente: {campo}'}), 400

    situacao = _normalizar_situacao(dados.get('situacao'))
    tipo_contato = (dados.get('tipo_contato') or '').upper().strip()
    if situacao not in SITUACAO_OPCOES:
        return jsonify({'erro': 'Situação inválida.'}), 400
    if tipo_contato not in TIPOS_CONTATO:
        return jsonify({'erro': 'Tipo de contato inválido.'}), 400

    try:
        valor = float(dados.get('valor', 0) or 0)
        if valor < 0:
            valor = 0.0
    except (ValueError, TypeError):
        valor = 0.0

    reg.empreendimento = (dados.get('empreendimento') or '').upper().strip()
    reg.cliente = (dados.get('cliente') or '').upper().strip()
    reg.telefone = (dados.get('telefone') or '').upper().strip()
    reg.email_cliente = (dados.get('email_cliente') or '').upper().strip() or None
    reg.tipo_contato = tipo_contato
    reg.situacao = situacao
    reg.observacao = (dados.get('observacao') or '').upper().strip() or None
    reg.valor = valor
    reg.acao_realizada = (dados.get('acao_realizada') or '').upper().strip() or None
    sincronizar_acao_registro(
        'relacionamento',
        reg.semana,
        reg.acao_realizada,
        current_user.nome.upper(),
        reg.id,
        'relacionamento_registro',
    )

    db.session.commit()
    _broadcast_update(reg.semana)
    return jsonify({'sucesso': True, 'registro': reg.to_dict()})


@relacionamento_bp.route('/acao', methods=['POST'])
@login_required
@requer_relacionamento_ou_admin
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

    reg = db.session.get(Relacionamento, int(reg_id)) if reg_id else None
    if reg and not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode editar registros criados por voce.'}), 403
    nova_acao = IndicadorAcao(
        scope='relacionamento',
        semana=semana,
        descricao=acao_realizada,
        responsavel=current_user.nome.upper(),
        registro_id=reg.id if reg else None,
        registro_tipo='relacionamento' if reg else None,
    )
    db.session.add(nova_acao)
    db.session.commit()
    _broadcast_update(semana)
    return jsonify({'sucesso': True, 'acao': nova_acao.to_dict()})


@relacionamento_bp.route('/registros')
@login_required
@requer_relacionamento_ou_admin
def listar_registros():
    semana = _parse_semana(request.args.get('semana', semana_padrao_preenchimento()))
    if semana is None:
        return jsonify({'erro': 'Semana inválida.'}), 400
    registros = Relacionamento.query.filter_by(semana=semana)\
        .order_by(Relacionamento.criado_em.desc()).all()
    indicadores = _calcular_indicadores(semana)
    return jsonify({
        'registros': [r.to_dict() for r in registros],
        'indicadores': indicadores,
        'acoes': [item.to_dict() for item in consultar_acoes('relacionamento', semana)],
    })


@relacionamento_bp.route('/acao/<int:acao_id>', methods=['DELETE'])
@login_required
@requer_relacionamento_ou_admin
def deletar_acao(acao_id):
    acao = db.session.get(IndicadorAcao, acao_id)
    if not acao or acao.scope != 'relacionamento':
        return jsonify({'erro': 'Acao nao encontrada.'}), 404
    bloqueio = _garantir_semana_editavel(acao.semana)
    if bloqueio:
        return bloqueio
    if not (current_user.can_manage_admin() or acao.responsavel == current_user.nome.upper()):
        return jsonify({'erro': 'Voce so pode excluir acoes registradas por voce.'}), 403
    semana = acao.semana
    registrar_exclusao_auditoria(scope='relacionamento', instance=acao, usuario_id=current_user.id, registro_tipo='relacionamento_acao')
    db.session.delete(acao)
    db.session.commit()
    _broadcast_update(semana)
    return jsonify({'sucesso': True})


@relacionamento_bp.route('/registro/<int:reg_id>', methods=['DELETE'])
@login_required
@requer_relacionamento_ou_admin
def deletar_registro(reg_id):
    reg = db.session.get(Relacionamento, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro não encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Você só pode excluir registros criados por você.'}), 403
    bloqueio = _garantir_semana_editavel(reg.semana)
    if bloqueio:
        return bloqueio
    semana = reg.semana
    registrar_exclusao_auditoria(scope='relacionamento', instance=reg, usuario_id=current_user.id, registro_tipo='relacionamento_registro')
    db.session.delete(reg)
    db.session.commit()
    _broadcast_update(semana)
    return jsonify({'sucesso': True})


@relacionamento_bp.route('/registros', methods=['DELETE'])
@login_required
@requer_relacionamento_ou_admin
def deletar_registros_semana():
    if not request.args.get('semana'):
        return jsonify({'erro': 'Informe a semana para excluir registros.'}), 400
    semana = _parse_semana(request.args.get('semana', semana_padrao_preenchimento()))
    if semana is None:
        return jsonify({'erro': 'Semana invalida.'}), 400
    bloqueio = _garantir_semana_editavel(semana)
    if bloqueio:
        return bloqueio

    registros = Relacionamento.query.filter_by(semana=semana).all()
    registros_permitidos = [reg for reg in registros if _pode_gerenciar_registro(reg)]
    if registros and len(registros_permitidos) != len(registros) and not current_user.can_manage_admin():
        return jsonify({'erro': 'Voce so pode excluir em massa registros criados por voce.'}), 403
    if not registros_permitidos:
        return jsonify({'sucesso': True, 'quantidade': 0})

    for reg in registros_permitidos:
        registrar_exclusao_auditoria(scope='relacionamento', instance=reg, usuario_id=current_user.id, registro_tipo='relacionamento_registro')
        db.session.delete(reg)
    db.session.commit()
    _broadcast_update(semana)
    return jsonify({'sucesso': True, 'quantidade': len(registros_permitidos)})
