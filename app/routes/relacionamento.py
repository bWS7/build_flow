from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user
from functools import wraps
from app import db, socketio
from app.models.relacionamento import Relacionamento, SITUACAO_OPCOES
from app.models.empreendimento import Empreendimento
from app.models.meta import MetaSemana
from app.models.meta_configuracao import MetaConfiguracaoIndicador
from sqlalchemy import func

relacionamento_bp = Blueprint('relacionamento', __name__)

TIPOS_CONTATO = ['LIGAÇÃO', 'VISITA', 'WHATSAPP', 'E-MAIL', 'REUNIÃO']
SEMANAS_VALIDAS = set(range(1, 13))


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
        return f(*args, **kwargs)
    return decorated


# ── Helpers ────────────────────────────────────────────────────────────────────

def _calcular_indicadores(semana: int, registros: list[Relacionamento] | None = None) -> dict:
    meta = MetaSemana.query.filter_by(semana=semana).first()
    acoes_planejadas = meta.acoes_planejadas if meta else 0
    valor_meta = float(meta.valor_meta) if meta else 0.0
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope='relacionamento').first()

    todos = registros if registros is not None else Relacionamento.query.filter_by(semana=semana).all()
    acoes_realizadas = sum(1 for item in todos if (item.acao_realizada or '').strip())
    registros_sim = [r for r in todos if _situacao_conta_como_sim(r.situacao)]
    soma_valores = sum(float(r.valor) for r in registros_sim if r.valor > 0)

    pct_acoes = (acoes_realizadas / acoes_planejadas * 100) if acoes_planejadas > 0 else 0
    pct_valor = (soma_valores / valor_meta * 100) if valor_meta > 0 else 0

    return {
        'semana': semana,
        'acoes_planejadas': acoes_planejadas,
        'acoes_realizadas': acoes_realizadas,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'valor_meta': valor_meta,
        'soma_valores': soma_valores,
        'pct_acoes': min(round(pct_acoes, 1), 100),
        'pct_valor': min(round(pct_valor, 1), 100),
    }


def _broadcast_update(semana: int):
    """Emite atualização via WebSocket para todos os clientes."""
    registros = Relacionamento.query.filter_by(semana=semana)\
        .order_by(Relacionamento.criado_em.desc()).all()
    indicadores = _calcular_indicadores(semana, registros)
    socketio.emit('dados_atualizados', {
        'indicadores': indicadores,
        'registros': [r.to_dict() for r in registros],
    })


def _pode_gerenciar_registro(registro: Relacionamento) -> bool:
    return current_user.can_manage_admin() or registro.responsavel == current_user.nome.upper()


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
    semana = _parse_semana(request.args.get('semana', 1)) or 1
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
        semana_atual=semana,
    )


@relacionamento_bp.route('/cadastrar', methods=['POST'])
@login_required
@requer_relacionamento_ou_admin
def cadastrar():
    dados = request.get_json(silent=True) or request.form.to_dict()

    campos_obrigatorios = ['empreendimento', 'cliente', 'telefone', 'tipo_contato', 'situacao']
    for campo in campos_obrigatorios:
        if not dados.get(campo):
            return jsonify({'erro': f'Campo obrigatório ausente: {campo}'}), 400

    situacao = _normalizar_situacao(dados.get('situacao'))
    tipo_contato = dados['tipo_contato'].upper().strip()
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

    novo = Relacionamento(
        empreendimento=dados['empreendimento'].upper().strip(),
        cliente=dados['cliente'].upper().strip(),
        telefone=dados['telefone'].upper().strip(),
        email_cliente=(dados.get('email_cliente') or '').upper().strip() or None,
        tipo_contato=tipo_contato,
        situacao=situacao,
        observacao=(dados.get('observacao') or '').upper().strip() or None,
        acao_realizada=(dados.get('acao_realizada') or '').upper().strip() or None,
        valor=valor,
        responsavel=current_user.nome.upper(),
        semana=semana,
    )
    db.session.add(novo)
    db.session.commit()

    _broadcast_update(semana)
    return jsonify({'sucesso': True, 'id': novo.id}), 201


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
    reg.acao_realizada = (dados.get('acao_realizada') or '').upper().strip() or None
    reg.valor = valor

    db.session.commit()
    _broadcast_update(reg.semana)
    return jsonify({'sucesso': True, 'registro': reg.to_dict()})


@relacionamento_bp.route('/acao', methods=['POST'])
@login_required
@requer_relacionamento_ou_admin
def registrar_acao():
    dados = request.get_json(silent=True) or request.form.to_dict()
    reg_id = dados.get('id')
    if not reg_id:
        return jsonify({'erro': 'Cliente nao informado.'}), 400

    reg = db.session.get(Relacionamento, int(reg_id))
    if not reg:
        return jsonify({'erro': 'Cliente nao encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Voce so pode editar registros criados por voce.'}), 403

    acao_realizada = (dados.get('acao_realizada') or '').upper().strip()
    if not acao_realizada:
        return jsonify({'erro': 'Informe a acao realizada.'}), 400

    reg.acao_realizada = acao_realizada
    db.session.commit()
    _broadcast_update(reg.semana)
    return jsonify({'sucesso': True, 'registro': reg.to_dict()})


@relacionamento_bp.route('/registros')
@login_required
@requer_relacionamento_ou_admin
def listar_registros():
    semana = _parse_semana(request.args.get('semana', 1))
    if semana is None:
        return jsonify({'erro': 'Semana inválida.'}), 400
    registros = Relacionamento.query.filter_by(semana=semana)\
        .order_by(Relacionamento.criado_em.desc()).all()
    indicadores = _calcular_indicadores(semana)
    return jsonify({
        'registros': [r.to_dict() for r in registros],
        'indicadores': indicadores,
    })


@relacionamento_bp.route('/registro/<int:reg_id>', methods=['DELETE'])
@login_required
@requer_relacionamento_ou_admin
def deletar_registro(reg_id):
    reg = db.session.get(Relacionamento, reg_id)
    if not reg:
        return jsonify({'erro': 'Registro não encontrado.'}), 404
    if not _pode_gerenciar_registro(reg):
        return jsonify({'erro': 'Você só pode excluir registros criados por você.'}), 403
    semana = reg.semana
    db.session.delete(reg)
    db.session.commit()
    _broadcast_update(semana)
    return jsonify({'sucesso': True})
