from flask import Blueprint, render_template, request, jsonify, abort, flash, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps
from datetime import date
from sqlalchemy import func
from app import db
from app.models.user import User, DOMINIO_PERMITIDO, TIPOS_VALIDOS
from app.models.empreendimento import Empreendimento
from app.models.meta import MetaSemana
from app.models.relacionamento import Relacionamento
from app.services.analytics_ai import analytics_ai_available, analytics_ai_enabled, ask_analytics_assistant

MESES_RELATORIO = [
    ('abril', 'Abril', 1),
    ('maio', 'Maio', 5),
    ('junho', 'Junho', 9),
]
PERIODO_TRIMESTRAL = ('resumo_trimestral', 'Resumo Trimestral', 1)
META_FINAL_MONTH = 11
META_FINAL_DAY = 30
MIN_PASSWORD_LENGTH = 10


def _safe_pct(realizado: float, planejado: float) -> float:
    if planejado <= 0:
        return 0.0
    return min(round((realizado / planejado) * 100, 1), 999.9)


def _senha_forte(senha: str) -> bool:
    if len(senha or '') < MIN_PASSWORD_LENGTH:
        return False
    return any(char.isalpha() for char in senha) and any(char.isdigit() for char in senha)


def _normalizar_filtros(args) -> dict:
    return {
        'empreendimento': (args.get('empreendimento') or '').strip().upper(),
        'responsavel': (args.get('responsavel') or '').strip().upper(),
        'tipo_contato': (args.get('tipo_contato') or '').strip().upper(),
        'situacao': (args.get('situacao') or '').strip().upper(),
    }


def _consultar_registros_semana(semana: int, filtros: dict):
    query = Relacionamento.query.filter_by(semana=semana)
    if filtros.get('empreendimento'):
        query = query.filter(func.upper(Relacionamento.empreendimento) == filtros['empreendimento'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(Relacionamento.responsavel) == filtros['responsavel'])
    if filtros.get('tipo_contato'):
        query = query.filter(func.upper(Relacionamento.tipo_contato) == filtros['tipo_contato'])
    if filtros.get('situacao'):
        query = query.filter(func.upper(Relacionamento.situacao) == filtros['situacao'])
    return query.order_by(Relacionamento.criado_em.desc()).all()


def _listar_opcoes_filtro(coluna) -> list[str]:
    valores = (
        db.session.query(coluna)
        .filter(coluna.isnot(None))
        .distinct()
        .order_by(coluna.asc())
        .all()
    )
    return [valor[0] for valor in valores if valor[0]]


def _coletar_semana(semana: int, filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    meta = MetaSemana.query.filter_by(semana=semana).first()
    registros = _consultar_registros_semana(semana, filtros)
    valor_planejado = float(meta.valor_meta) if meta else 0.0
    acoes_planejadas = int(meta.acoes_planejadas) if meta else 0
    valor_realizado = sum(float(r.valor) for r in registros if r.situacao == 'SIM' and float(r.valor) > 0)
    acoes_realizadas = len(registros)
    return {
        'semana': semana,
        'valor_planejado': valor_planejado,
        'valor_realizado': valor_realizado,
        'acoes_planejadas': acoes_planejadas,
        'acoes_realizadas': acoes_realizadas,
        'pct_valor': _safe_pct(valor_realizado, valor_planejado),
        'pct_acoes': _safe_pct(acoes_realizadas, acoes_planejadas),
        'total_registros': len(registros),
    }


def _resumir_entidades_trimestre(filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    semanas = list(range(1, 13))
    query = Relacionamento.query.filter(Relacionamento.semana.in_(semanas))
    if filtros.get('empreendimento'):
        query = query.filter(func.upper(Relacionamento.empreendimento) == filtros['empreendimento'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(Relacionamento.responsavel) == filtros['responsavel'])
    if filtros.get('tipo_contato'):
        query = query.filter(func.upper(Relacionamento.tipo_contato) == filtros['tipo_contato'])
    if filtros.get('situacao'):
        query = query.filter(func.upper(Relacionamento.situacao) == filtros['situacao'])

    registros = query.all()
    top_empreendimentos: dict[str, dict] = {}
    top_responsaveis: dict[str, dict] = {}
    situacoes: dict[str, int] = {}

    for registro in registros:
        emp = registro.empreendimento or 'NAO INFORMADO'
        resp = registro.responsavel or 'NAO INFORMADO'
        situacao = registro.situacao or 'NAO INFORMADA'
        valor = float(registro.valor or 0)
        valor_convertido = valor if situacao == 'SIM' and valor > 0 else 0.0

        top_empreendimentos.setdefault(emp, {'empreendimento': emp, 'registros': 0, 'valor': 0.0})
        top_empreendimentos[emp]['registros'] += 1
        top_empreendimentos[emp]['valor'] += valor_convertido

        top_responsaveis.setdefault(resp, {'responsavel': resp, 'registros': 0, 'valor': 0.0})
        top_responsaveis[resp]['registros'] += 1
        top_responsaveis[resp]['valor'] += valor_convertido

        situacoes[situacao] = situacoes.get(situacao, 0) + 1

    top_empreendimentos_lista = sorted(
        top_empreendimentos.values(),
        key=lambda item: (item['valor'], item['registros']),
        reverse=True,
    )[:5]
    top_responsaveis_lista = sorted(
        top_responsaveis.values(),
        key=lambda item: (item['valor'], item['registros']),
        reverse=True,
    )[:5]

    return {
        'top_empreendimentos': top_empreendimentos_lista,
        'top_responsaveis': top_responsaveis_lista,
        'situacoes': situacoes,
        'total_registros_filtrados': len(registros),
    }


def _listar_registros_contexto_ia(filtros: dict | None = None, limite: int = 500) -> list[dict]:
    filtros = filtros or {}
    semanas = list(range(1, 13))
    query = Relacionamento.query.filter(Relacionamento.semana.in_(semanas))
    if filtros.get('empreendimento'):
        query = query.filter(func.upper(Relacionamento.empreendimento) == filtros['empreendimento'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(Relacionamento.responsavel) == filtros['responsavel'])
    if filtros.get('tipo_contato'):
        query = query.filter(func.upper(Relacionamento.tipo_contato) == filtros['tipo_contato'])
    if filtros.get('situacao'):
        query = query.filter(func.upper(Relacionamento.situacao) == filtros['situacao'])

    registros = (
        query.order_by(Relacionamento.criado_em.desc())
        .limit(limite)
        .all()
    )

    return [
        {
            'id': registro.id,
            'semana': registro.semana,
            'empreendimento': registro.empreendimento,
            'cliente': registro.cliente,
            'telefone': registro.telefone,
            'email_cliente': registro.email_cliente or '',
            'tipo_contato': registro.tipo_contato,
            'situacao': registro.situacao,
            'valor': float(registro.valor or 0),
            'responsavel': registro.responsavel,
            'observacao': registro.observacao or '',
            'criado_em': registro.formatar_criado_em(),
            'criado_em_iso': registro.criado_em_brasilia.isoformat() if registro.criado_em_brasilia else '',
        }
        for registro in registros
    ]


def _resumo_sistema_contexto_ia() -> dict:
    return {
        'usuarios_ativos': User.query.filter_by(ativo=True).count(),
        'usuarios_totais': User.query.count(),
        'empreendimentos_ativos': Empreendimento.query.filter_by(ativo=True).count(),
        'empreendimentos_totais': Empreendimento.query.count(),
        'metas_cadastradas': MetaSemana.query.count(),
        'registros_relacionamento_totais': Relacionamento.query.count(),
    }


def _montar_contexto_ia_relacionamento(mes_slug: str, filtros: dict | None = None) -> dict:
    dados = _montar_relatorio_relacionamento(mes_slug, filtros)
    extras = _resumir_entidades_trimestre(filtros)
    registros_contexto = _listar_registros_contexto_ia(filtros)
    hoje = date.today()
    prazo_final = date(hoje.year, META_FINAL_MONTH, META_FINAL_DAY)
    dias_restantes = (prazo_final - hoje).days

    if dias_restantes > 0:
        status_prazo = 'em_andamento'
    elif dias_restantes == 0:
        status_prazo = 'ultimo_dia'
    else:
        status_prazo = 'encerrado'

    return {
        'calendario': {
            'data_atual_iso': hoje.isoformat(),
            'data_atual': hoje.strftime('%d/%m/%Y'),
            'prazo_final_metas_iso': prazo_final.isoformat(),
            'prazo_final_metas': prazo_final.strftime('%d/%m/%Y'),
            'dias_restantes_para_o_prazo_final': dias_restantes,
            'status_do_prazo': status_prazo,
        },
        'mes_atual': dados['mes_atual'],
        'filtros': dados['filtros'],
        'resumo_mensal': dados['resumo_mensal'],
        'destaques': dados['destaques'],
        'semanas': dados['semanas_mes'],
        'evolucao': dados['evolucao'],
        'top_empreendimentos': extras['top_empreendimentos'],
        'top_responsaveis': extras['top_responsaveis'],
        'situacoes': extras['situacoes'],
        'total_registros_filtrados': extras['total_registros_filtrados'],
        'registros_detalhados_periodo': registros_contexto,
        'resumo_sistema': _resumo_sistema_contexto_ia(),
    }


def _montar_relatorio_relacionamento(mes_slug: str, filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    meses_map = {slug: {'slug': slug, 'nome': nome, 'inicio': inicio} for slug, nome, inicio in MESES_RELATORIO}
    meses_map[PERIODO_TRIMESTRAL[0]] = {'slug': PERIODO_TRIMESTRAL[0], 'nome': PERIODO_TRIMESTRAL[1], 'inicio': PERIODO_TRIMESTRAL[2]}
    mes_selecionado = meses_map.get(mes_slug, meses_map['abril'])
    semanas_mes = []
    evolucao = []
    acumulado_valor_planejado = 0.0
    acumulado_valor_realizado = 0.0
    acumulado_acoes_planejadas = 0
    acumulado_acoes_realizadas = 0

    for slug, nome, inicio in MESES_RELATORIO:
        for offset in range(4):
            semana = inicio + offset
            linha = _coletar_semana(semana, filtros)
            linha.update({
                'mes_slug': slug,
                'mes_nome': nome,
                'semana_label': offset + 1,
            })
            acumulado_valor_planejado += linha['valor_planejado']
            acumulado_valor_realizado += linha['valor_realizado']
            acumulado_acoes_planejadas += linha['acoes_planejadas']
            acumulado_acoes_realizadas += linha['acoes_realizadas']
            linha['acumulado_valor_planejado'] = acumulado_valor_planejado
            linha['acumulado_valor_realizado'] = acumulado_valor_realizado
            linha['acumulado_acoes_planejadas'] = acumulado_acoes_planejadas
            linha['acumulado_acoes_realizadas'] = acumulado_acoes_realizadas
            linha['pct_valor_acumulado'] = _safe_pct(acumulado_valor_realizado, acumulado_valor_planejado)
            linha['pct_acoes_acumulado'] = _safe_pct(acumulado_acoes_realizadas, acumulado_acoes_planejadas)
            evolucao.append(linha)
            if mes_selecionado['slug'] == PERIODO_TRIMESTRAL[0] or slug == mes_selecionado['slug']:
                semanas_mes.append(linha)

    resumo_mensal = {
        'valor_planejado': sum(item['valor_planejado'] for item in semanas_mes),
        'valor_realizado': sum(item['valor_realizado'] for item in semanas_mes),
        'acoes_planejadas': sum(item['acoes_planejadas'] for item in semanas_mes),
        'acoes_realizadas': sum(item['acoes_realizadas'] for item in semanas_mes),
    }
    resumo_mensal['pct_valor'] = _safe_pct(resumo_mensal['valor_realizado'], resumo_mensal['valor_planejado'])
    resumo_mensal['pct_acoes'] = _safe_pct(resumo_mensal['acoes_realizadas'], resumo_mensal['acoes_planejadas'])

    melhor_semana = max(semanas_mes, key=lambda item: (item['pct_valor'] + item['pct_acoes'])) if semanas_mes else None
    pior_semana = min(semanas_mes, key=lambda item: (item['pct_valor'] + item['pct_acoes'])) if semanas_mes else None
    destaques = {
        'melhor_semana': melhor_semana,
        'pior_semana': pior_semana,
        'gap_valor': max(resumo_mensal['valor_planejado'] - resumo_mensal['valor_realizado'], 0),
        'gap_acoes': max(resumo_mensal['acoes_planejadas'] - resumo_mensal['acoes_realizadas'], 0),
    }

    chart_width = 720
    chart_height = 220
    left_pad = 20
    usable_width = chart_width - (left_pad * 2)
    usable_height = chart_height - 40
    total_points = max(len(semanas_mes) - 1, 1)

    valor_points = []
    acoes_points = []
    valor_markers = []
    acoes_markers = []
    chart_labels = []
    for idx, item in enumerate(semanas_mes):
        x = left_pad + (usable_width * idx / total_points)
        y_valor = 20 + (usable_height * (1 - min(item['pct_valor'], 100) / 100))
        y_acoes = 20 + (usable_height * (1 - min(item['pct_acoes'], 100) / 100))
        valor_points.append(f"{round(x, 1)},{round(y_valor, 1)}")
        acoes_points.append(f"{round(x, 1)},{round(y_acoes, 1)}")
        valor_markers.append({'x': round(x, 1), 'y': round(y_valor, 1)})
        acoes_markers.append({'x': round(x, 1), 'y': round(y_acoes, 1)})
        chart_labels.append({
            'x': round(x, 1),
            'label': f"{item['mes_nome']} S{item['semana_label']}" if mes_selecionado['slug'] == PERIODO_TRIMESTRAL[0] else f"S{item['semana_label']}",
        })

    valor_area_points = f"20,180 {' '.join(valor_points)} {chart_width - 20},180"
    acoes_area_points = f"20,180 {' '.join(acoes_points)} {chart_width - 20},180"
    chart = {
        'width': chart_width,
        'height': chart_height,
        'valor_points': " ".join(valor_points),
        'acoes_points': " ".join(acoes_points),
        'valor_area_points': valor_area_points,
        'acoes_area_points': acoes_area_points,
        'valor_markers': valor_markers,
        'acoes_markers': acoes_markers,
        'labels': chart_labels,
    }

    filtros_aplicados = {chave: valor for chave, valor in filtros.items() if valor}
    opcoes_filtro = {
        'empreendimentos': _listar_opcoes_filtro(Relacionamento.empreendimento),
        'responsaveis': _listar_opcoes_filtro(Relacionamento.responsavel),
        'tipos_contato': _listar_opcoes_filtro(Relacionamento.tipo_contato),
        'situacoes': _listar_opcoes_filtro(Relacionamento.situacao),
    }

    return {
        'meses': [meses_map[slug] for slug, _, _ in MESES_RELATORIO] + [meses_map[PERIODO_TRIMESTRAL[0]]],
        'mes_atual': mes_selecionado,
        'semanas_mes': semanas_mes,
        'resumo_mensal': resumo_mensal,
        'destaques': destaques,
        'evolucao': evolucao,
        'chart': chart,
        'filtros': filtros,
        'filtros_aplicados': filtros_aplicados,
        'opcoes_filtro': opcoes_filtro,
    }

admin_bp = Blueprint('admin', __name__)


def requer_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.tipo != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/')
@login_required
@requer_admin
def dashboard():
    usuarios = User.query.order_by(User.nome).all()
    empreendimentos = Empreendimento.query.order_by(Empreendimento.nome).all()
    metas = MetaSemana.query.order_by(MetaSemana.semana).all()
    return render_template('admin/dashboard.html',
                           usuarios=usuarios,
                           empreendimentos=empreendimentos,
                           metas=metas,
                           tipos=TIPOS_VALIDOS)


@admin_bp.route('/relacionamento')
@login_required
@requer_admin
def relacionamento_painel():
    filtros = _normalizar_filtros(request.args)
    dados = _montar_relatorio_relacionamento(request.args.get('mes', 'abril'), filtros)
    dados['analytics_ai_enabled'] = analytics_ai_enabled() and analytics_ai_available()
    return render_template('admin/relacionamento_painel.html', **dados)


@admin_bp.route('/relacionamento/ai-chat', methods=['POST'])
@login_required
@requer_admin
def relacionamento_ai_chat():
    if not analytics_ai_enabled():
        return jsonify({
            'erro': 'A assistente analitica nao esta configurada. Defina GEMINI_API_KEY para habilitar.',
        }), 503
    if not analytics_ai_available():
        return jsonify({
            'erro': 'Dependencia do Gemini nao instalada no ambiente.',
        }), 503

    dados = request.get_json(silent=True) or {}
    pergunta = (dados.get('message') or '').strip()
    if not pergunta:
        return jsonify({'erro': 'Pergunta obrigatoria.'}), 400

    filtros = _normalizar_filtros(dados)
    mes_slug = dados.get('mes') or 'resumo_trimestral'
    history = dados.get('history') or []
    contexto = _montar_contexto_ia_relacionamento(mes_slug, filtros)

    try:
        resposta = ask_analytics_assistant(pergunta, history, contexto)
    except Exception:
        return jsonify({
            'erro': 'Nao foi possivel consultar a assistente analitica no momento.',
        }), 502

    return jsonify({'answer': resposta})


# ── Usuários ───────────────────────────────────────────────────────────────────

@admin_bp.route('/usuario/criar', methods=['POST'])
@login_required
@requer_admin
def criar_usuario():
    dados = request.get_json(silent=True) or request.form.to_dict()
    nome = (dados.get('nome') or '').strip().upper()
    email = (dados.get('email') or '').strip().lower()
    senha = dados.get('senha') or ''
    tipo = (dados.get('tipo') or '').strip().lower()

    if not all([nome, email, senha, tipo]):
        return jsonify({'erro': 'Todos os campos são obrigatórios.'}), 400
    if not email.endswith(DOMINIO_PERMITIDO):
        return jsonify({'erro': f'E-mail deve ser do domínio {DOMINIO_PERMITIDO}'}), 400
    if not _senha_forte(senha):
        return jsonify({'erro': f'Senha deve ter ao menos {MIN_PASSWORD_LENGTH} caracteres, com letras e números.'}), 400
    if tipo not in TIPOS_VALIDOS:
        return jsonify({'erro': 'Tipo de usuário inválido.'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'erro': 'E-mail já cadastrado.'}), 409

    user = User(nome=nome, email=email, tipo=tipo)
    user.set_password(senha)
    db.session.add(user)
    db.session.commit()
    return jsonify({'sucesso': True, 'id': user.id}), 201


@admin_bp.route('/usuario/<int:uid>/toggle', methods=['POST'])
@login_required
@requer_admin
def toggle_usuario(uid):
    user = db.session.get(User, uid)
    if not user:
        return jsonify({'erro': 'Usuário não encontrado.'}), 404
    if user.id == current_user.id:
        return jsonify({'erro': 'Não é possível desativar seu próprio usuário.'}), 400
    user.ativo = not user.ativo
    db.session.commit()
    return jsonify({'sucesso': True, 'ativo': user.ativo})


@admin_bp.route('/usuario/<int:uid>/editar', methods=['POST'])
@login_required
@requer_admin
def editar_usuario(uid):
    user = db.session.get(User, uid)
    if not user:
        return jsonify({'erro': 'Usuário não encontrado.'}), 404

    dados = request.get_json(silent=True) or request.form.to_dict()
    nome = (dados.get('nome') or '').strip().upper()
    email = (dados.get('email') or '').strip().lower()
    tipo = (dados.get('tipo') or '').strip().lower()
    senha = (dados.get('senha') or '').strip()

    if not all([nome, email, tipo]):
        return jsonify({'erro': 'Nome, e-mail e tipo são obrigatórios.'}), 400
    if not email.endswith(DOMINIO_PERMITIDO):
        return jsonify({'erro': f'E-mail deve ser do domínio {DOMINIO_PERMITIDO}'}), 400
    if tipo not in TIPOS_VALIDOS:
        return jsonify({'erro': 'Tipo de usuário inválido.'}), 400
    if senha and not _senha_forte(senha):
        return jsonify({'erro': f'Senha deve ter ao menos {MIN_PASSWORD_LENGTH} caracteres, com letras e números.'}), 400

    email_existente = User.query.filter(User.email == email, User.id != uid).first()
    if email_existente:
        return jsonify({'erro': 'E-mail já cadastrado para outro usuário.'}), 409

    user.nome = nome
    user.email = email
    user.tipo = tipo
    if senha:
        user.set_password(senha)

    db.session.commit()
    return jsonify({
        'sucesso': True,
        'usuario': {
            'id': user.id,
            'nome': user.nome,
            'email': user.email,
            'tipo': user.tipo,
            'ativo': user.ativo,
        }
    })


# ── Empreendimentos ────────────────────────────────────────────────────────────

@admin_bp.route('/empreendimento/criar', methods=['POST'])
@login_required
@requer_admin
def criar_empreendimento():
    dados = request.get_json(silent=True) or request.form.to_dict()
    nome = (dados.get('nome') or '').strip().upper()
    if not nome:
        return jsonify({'erro': 'Nome obrigatório.'}), 400
    if Empreendimento.query.filter_by(nome=nome).first():
        return jsonify({'erro': 'Empreendimento já cadastrado.'}), 409
    emp = Empreendimento(nome=nome)
    db.session.add(emp)
    db.session.commit()
    return jsonify({'sucesso': True, 'id': emp.id, 'nome': emp.nome}), 201


@admin_bp.route('/empreendimento/<int:eid>/toggle', methods=['POST'])
@login_required
@requer_admin
def toggle_empreendimento(eid):
    emp = db.session.get(Empreendimento, eid)
    if not emp:
        return jsonify({'erro': 'Empreendimento não encontrado.'}), 404
    emp.ativo = not emp.ativo
    db.session.commit()
    return jsonify({'sucesso': True, 'ativo': emp.ativo})


# ── Metas ──────────────────────────────────────────────────────────────────────

@admin_bp.route('/meta/salvar', methods=['POST'])
@login_required
@requer_admin
def salvar_meta():
    dados = request.get_json(silent=True) or request.form.to_dict()
    semana = int(dados.get('semana', 1))
    try:
        acoes = int(dados.get('acoes_planejadas', 0))
        valor = float(dados.get('valor_meta', 0))
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valores inválidos.'}), 400

    meta = MetaSemana.query.filter_by(semana=semana).first()
    if meta:
        meta.acoes_planejadas = acoes
        meta.valor_meta = valor
    else:
        meta = MetaSemana(semana=semana, acoes_planejadas=acoes, valor_meta=valor)
        db.session.add(meta)
    db.session.commit()
    return jsonify({'sucesso': True})
