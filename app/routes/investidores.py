from datetime import date, datetime
from functools import wraps
import unicodedata

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import extract, func

from app import db, socketio
from app.models.empreendimento import Empreendimento
from app.models.indicador_acao import IndicadorAcao, consultar_acoes, contar_acoes, sincronizar_acao_registro
from app.models.meta_configuracao import MetaConfiguracaoIndicador
from app.models.investidor import Investidor, SITUACAO_INVESTIDOR_OPCOES, TIPO_VENDA_OPCOES
from app.models.meta_investidor_semana import MetaInvestidorSemana
from app.services.analytics_ai import analytics_ai_available, analytics_ai_enabled, ask_analytics_assistant, build_global_ai_context, fallback_analytics_answer
from app.utils.progress import calcular_percentual_planejado_realizado
from app.utils.quarter import semana_editavel


investidores_bp = Blueprint('investidores', __name__)

PERIODO_INVESTIDORES = ('resumo_trimestral', 'Resumo Trimestral', None)
MESES_INVESTIDORES = [
    ('abril', 'Abril', 4, 1),
    ('maio', 'Maio', 5, 5),
    ('junho', 'Junho', 6, 9),
]
MESES_MAP = {slug: {'slug': slug, 'nome': nome, 'numero': numero, 'semana_inicio': semana_inicio} for slug, nome, numero, semana_inicio in MESES_INVESTIDORES}
EMPREENDIMENTO_IGNORADO = 'J J NEGOCIOS IMOBILIARIOS'
SITUACOES_FUNIL_AGRUPADAS = {
    'CANCELADA': 'Cancelada',
    'CONFECCAO DE CONTRATO': 'Confeccao de Contrato',
    'CONTRATO ASSINADO': 'Contrato Assinado / Contrato Assinado Clientes',
    'CONTRATO ASSINADO CLIENTES': 'Contrato Assinado / Contrato Assinado Clientes',
    'ENVIO UAU': 'Envio UAU',
    'NOVA RESERVA': 'Nova Reserva',
    'PENDENTE DE ASSINATURA': 'Pendente de Assinatura',
}

TIPO_VENDA_ALIAS = {
    'A VISTA / DIRETA': 'A VISTA / DIRETA',
    'A VISTA DIRETA': 'A VISTA / DIRETA',
    'AVISTA / DIRETA': 'A VISTA / DIRETA',
    'AVISTA DIRETA': 'A VISTA / DIRETA',
    'DIRETA': 'DIRETA',
    'INDIRETA': 'INDIRETA',
    'PARCERIA': 'PARCERIA',
    'REPASSE': 'REPASSE',
}


def requer_investidores(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.can_access_page('investidores'):
            abort(403)
        if request.method != 'GET' and not current_user.can_edit_page('investidores'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _usuario_admin_total() -> bool:
    return bool(getattr(current_user, 'is_authenticated', False) and current_user.can_override_week_lock())


def _usuario_pode_editar_investidores() -> bool:
    return bool(getattr(current_user, 'is_authenticated', False) and current_user.can_edit_page('investidores'))


def _mes_slug_atual() -> str:
    mes = (request.args.get('mes') or request.form.get('mes') or 'abril').strip().lower()
    if mes == PERIODO_INVESTIDORES[0]:
        return mes
    return mes if mes in MESES_MAP else 'abril'


def _semana_do_mes_atual() -> int:
    try:
        semana = int((request.args.get('semana') or request.form.get('semana') or '1').strip())
    except (TypeError, ValueError, AttributeError):
        semana = 1
    return semana if semana in {1, 2, 3, 4} else 1


def _semana_global_por_data(data_reserva, mes_slug: str | None = None) -> int | None:
    if not data_reserva:
        return None
    mes_numero = data_reserva.month
    for slug, _, numero, semana_inicio in MESES_INVESTIDORES:
        if numero == mes_numero:
            semana_local = min(((data_reserva.day - 1) // 7) + 1, 4)
            return semana_inicio + semana_local - 1
    return None


def _data_referencia_da_semana(mes_slug: str, semana_local: int) -> date:
    mes_info = MESES_MAP.get(mes_slug, MESES_MAP['abril'])
    dia_inicial = {1: 1, 2: 8, 3: 15, 4: 22}.get(semana_local, 1)
    return date(datetime.now().year, mes_info['numero'], dia_inicial)


def _garantir_semana_editavel_por_data(data_referencia):
    if not _usuario_pode_editar_investidores():
        return jsonify({'erro': 'Seu perfil possui apenas visualizacao nesta area.'}), 403
    semana_global = _semana_global_por_data(data_referencia)
    if semana_global is None:
        return jsonify({'erro': 'Nao foi possivel identificar a semana do registro.'}), 400
    if not semana_editavel(semana_global, _usuario_admin_total()):
        return jsonify({'erro': 'Esta semana esta bloqueada para edicao. Apenas o admin pode alterar semanas anteriores.'}), 403
    return None


def _garantir_semana_editavel_global(semana_global: int | None):
    if not _usuario_pode_editar_investidores():
        return jsonify({'erro': 'Seu perfil possui apenas visualizacao nesta area.'}), 403
    if semana_global is None:
        return jsonify({'erro': 'Nao foi possivel identificar a semana do registro.'}), 400
    if not semana_editavel(semana_global, _usuario_admin_total()):
        return jsonify({'erro': 'Esta semana esta bloqueada para edicao. Apenas o admin pode alterar semanas anteriores.'}), 403
    return None


def montar_contexto_template_investidores(mes_slug: str, incluir_resumo: bool = False, semana_local: int | None = None) -> dict:
    if mes_slug == PERIODO_INVESTIDORES[0] and not incluir_resumo:
        mes_slug = 'abril'
    semana_local_normalizada = semana_local if semana_local in {1, 2, 3, 4} else None
    mes_info = {'nome': PERIODO_INVESTIDORES[1]} if mes_slug == PERIODO_INVESTIDORES[0] else MESES_MAP[mes_slug]
    empreendimentos = Empreendimento.query.filter_by(ativo=True).order_by(Empreendimento.nome).all()
    investidores = _consultar_investidores_periodo(mes_slug, semana_local=semana_local_normalizada)
    semana_global = None
    if mes_slug != PERIODO_INVESTIDORES[0] and semana_local_normalizada is not None:
        semana_inicio = next(semana_inicio for slug, _, _, semana_inicio in MESES_INVESTIDORES if slug == mes_slug)
        semana_global = semana_inicio + semana_local_normalizada - 1
    if mes_slug == PERIODO_INVESTIDORES[0]:
        permite_edicao = _usuario_pode_editar_investidores()
    else:
        permite_edicao = _usuario_pode_editar_investidores() and semana_editavel(semana_global, _usuario_admin_total())
    return {
        'meses': [(slug, nome, numero) for slug, nome, numero, _ in MESES_INVESTIDORES] + ([PERIODO_INVESTIDORES] if incluir_resumo else []),
        'mes_atual': mes_slug,
        'semana_atual': semana_local_normalizada,
        'mes_atual_nome': mes_info['nome'],
        'empreendimentos': empreendimentos,
        'situacoes': SITUACAO_INVESTIDOR_OPCOES,
        'tipos_venda': TIPO_VENDA_OPCOES,
        'financeiro': _calcular_financeiro(mes_slug, investidores=investidores, semana_local=semana_local_normalizada),
        'registros': investidores,
        'registros_json': [investidor.to_dict() for investidor in investidores],
        'acoes_json': [item.to_dict() for item in consultar_acoes('investidores', _semanas_periodo_investidores(mes_slug, semana_local_normalizada))],
        'resumo_trimestral': mes_slug == PERIODO_INVESTIDORES[0],
        'permite_edicao': permite_edicao,
        'analytics_ai_enabled': analytics_ai_enabled() and analytics_ai_available(),
        'incluir_resumo_tabs': incluir_resumo,
        'painel_admin_investidores': False,
    }


def _parse_decimal(valor) -> float:
    texto = str(valor or '').strip()
    if not texto:
        return 0.0
    texto = texto.replace('R$', '').replace(' ', '')
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        numero = float(texto)
    except (TypeError, ValueError):
        return 0.0
    return max(numero, 0.0)


def _parse_data(valor: str | None):
    texto = (valor or '').strip()
    if not texto:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def _normalizar_situacao(valor: str | None) -> str:
    texto = (valor or '').strip().upper()
    texto = ' '.join(texto.split())
    return ''.join(
        char for char in unicodedata.normalize('NFD', texto)
        if unicodedata.category(char) != 'Mn'
    )


def _normalizar_texto(valor: str | None, fallback: str = '') -> str:
    return ' '.join((valor or fallback).strip().upper().split())


def _normalizar_tipo_venda(valor: str | None, fallback: str = 'DIRETA') -> str:
    texto = _normalizar_situacao(valor or fallback)
    return TIPO_VENDA_ALIAS.get(texto, texto)


def _consultar_investidores_periodo(mes_slug: str, semana_local: int | None = None):
    query = (
        Investidor.query
        .filter(func.upper(Investidor.empreendimento) != EMPREENDIMENTO_IGNORADO)
    )
    if mes_slug != PERIODO_INVESTIDORES[0]:
        query = query.filter(extract('month', Investidor.data_reserva) == MESES_MAP[mes_slug]['numero'])
    else:
        query = query.filter(extract('month', Investidor.data_reserva).in_([4, 5, 6]))
    investidores = query.order_by(Investidor.data_reserva.desc(), Investidor.id.desc()).all()
    if mes_slug != PERIODO_INVESTIDORES[0] and semana_local is not None:
        semana_global = next(semana_inicio for slug, _, _, semana_inicio in MESES_INVESTIDORES if slug == mes_slug) + semana_local - 1
        investidores = [item for item in investidores if _semana_global_por_data(item.data_reserva, mes_slug) == semana_global]
    return investidores


def _obter_meta_semana(semana_global: int | None) -> float:
    if not semana_global:
        return 0.0
    meta = MetaInvestidorSemana.query.filter_by(semana=semana_global).first()
    return float(meta.valor_meta or 0) if meta else 0.0


def _obter_meta_acoes_semana(semana_global: int | None) -> int:
    if not semana_global:
        return 0
    meta = MetaInvestidorSemana.query.filter_by(semana=semana_global).first()
    return int(meta.acoes_planejadas or 0) if meta else 0


def _obter_meta_mes(mes_slug: str) -> float:
    semana_inicio = next(semana_inicio for slug, _, _, semana_inicio in MESES_INVESTIDORES if slug == mes_slug)
    return sum(_obter_meta_semana(semana_inicio + offset) for offset in range(4))


def _obter_meta_geral() -> float:
    return sum(_obter_meta_mes(slug) for slug, _, _, _ in MESES_INVESTIDORES)


def _obter_meta_acoes_mes(mes_slug: str) -> int:
    semana_inicio = next(semana_inicio for slug, _, _, semana_inicio in MESES_INVESTIDORES if slug == mes_slug)
    return sum(_obter_meta_acoes_semana(semana_inicio + offset) for offset in range(4))


def _obter_meta_acoes_geral() -> int:
    return sum(_obter_meta_acoes_mes(slug) for slug, _, _, _ in MESES_INVESTIDORES)


def _semanas_periodo_investidores(mes_slug: str, semana_local: int | None = None):
    if mes_slug == PERIODO_INVESTIDORES[0]:
        return range(1, 13)
    inicio = MESES_MAP[mes_slug]['semana_inicio']
    if semana_local:
        return [inicio + semana_local - 1]
    return [inicio + offset for offset in range(4)]


def _montar_funil(investidores: list[Investidor]) -> list[dict]:
    agrupado: dict[str, int] = {
        'Vendida': 0,
        'Cancelada': 0,
        'Confeccao de Contrato': 0,
        'Contrato Assinado / Contrato Assinado Clientes': 0,
        'Envio UAU': 0,
        'Nova Reserva': 0,
        'Pendente de Assinatura': 0,
    }
    total = 0
    for investidor in investidores:
        situacao = _normalizar_situacao(investidor.situacao)
        if situacao == 'VENDIDA':
            agrupado['Vendida'] += 1
            total += 1
            continue
        label = SITUACOES_FUNIL_AGRUPADAS.get(situacao)
        if not label:
            continue
        agrupado[label] += 1
        total += 1

    cores = {
        'Vendida': '#2A8A64',
        'Cancelada': '#B14D4D',
        'Confeccao de Contrato': '#C27D2C',
        'Contrato Assinado / Contrato Assinado Clientes': '#6B1A2A',
        'Envio UAU': '#4A6FA5',
        'Nova Reserva': '#B89A57',
        'Pendente de Assinatura': '#8A6E67',
    }
    funil = []
    for label, quantidade in agrupado.items():
        percentual = round((quantidade / total) * 100, 1) if total else 0.0
        funil.append({
            'label': label,
            'quantidade': quantidade,
            'percentual': percentual,
            'cor': cores[label],
        })
    return funil


def _calcular_financeiro(mes_slug: str, investidores: list[Investidor] | None = None, semana_local: int | None = None) -> dict:
    investidores = investidores if investidores is not None else _consultar_investidores_periodo(mes_slug, semana_local=semana_local)
    if mes_slug == PERIODO_INVESTIDORES[0]:
        meta_valor = _obter_meta_geral()
        meta_acoes = _obter_meta_acoes_geral()
    elif semana_local:
        semana_inicio = next(semana_inicio for slug, _, _, semana_inicio in MESES_INVESTIDORES if slug == mes_slug)
        semana_global = semana_inicio + semana_local - 1
        meta_valor = _obter_meta_semana(semana_global)
        meta_acoes = _obter_meta_acoes_semana(semana_global)
    else:
        meta_valor = _obter_meta_mes(mes_slug)
        meta_acoes = _obter_meta_acoes_mes(mes_slug)
    valor_realizado = sum(
        float(investidor.valor_presente or 0)
        for investidor in investidores
        if _normalizar_situacao(investidor.situacao) == 'VENDIDA'
    )
    total_vendidas = sum(1 for investidor in investidores if _normalizar_situacao(investidor.situacao) == 'VENDIDA')
    acoes_realizadas = contar_acoes('investidores', _semanas_periodo_investidores(mes_slug, semana_local))
    percentual = round((valor_realizado / meta_valor) * 100, 1) if meta_valor > 0 else 0.0
    percentual_acoes = round((acoes_realizadas / meta_acoes) * 100, 1) if meta_acoes > 0 else 0.0
    percentual_planejado_realizado = calcular_percentual_planejado_realizado(
        valor_realizado,
        meta_valor,
        acoes_realizadas,
        meta_acoes,
    )
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope='investidores').first()
    return {
        'mes': mes_slug,
        'meta_valor': meta_valor,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'meta_acoes': meta_acoes,
        'valor_realizado': valor_realizado,
        'percentual_atingimento': percentual,
        'total_registros': len(investidores),
        'total_vendidas': total_vendidas,
        'acoes_realizadas': acoes_realizadas,
        'percentual_acoes': percentual_acoes,
        'percentual_planejado_realizado': percentual_planejado_realizado,
        'funil': _montar_funil(investidores),
    }


def _listar_opcoes_filtro(coluna) -> list[str]:
    valores = (
        db.session.query(coluna)
        .filter(coluna.isnot(None))
        .filter(func.upper(Investidor.empreendimento) != EMPREENDIMENTO_IGNORADO)
        .distinct()
        .order_by(coluna.asc())
        .all()
    )
    return [valor[0] for valor in valores if valor[0]]


def _montar_contexto_ia_investidores(mes_slug: str) -> dict:
    investidores = _consultar_investidores_periodo(mes_slug)
    financeiro = _calcular_financeiro(mes_slug, investidores=investidores)
    return {
        'periodo': MESES_MAP[PERIODO_INVESTIDORES[0]]['nome'],
        'resumo_financeiro': financeiro,
        'registros': [investidor.to_dict() for investidor in investidores[:500]],
        'situacoes': {item['label']: item['quantidade'] for item in financeiro['funil']},
        'tipos_venda': _listar_opcoes_filtro(Investidor.tipo_venda),
        'empreendimentos': _listar_opcoes_filtro(Investidor.empreendimento),
        'corretores': _listar_opcoes_filtro(Investidor.corretor),
        'imobiliarias': _listar_opcoes_filtro(Investidor.imobiliaria),
    }


def _broadcast_update(mes_slug: str):
    investidores = _consultar_investidores_periodo(PERIODO_INVESTIDORES[0])
    socketio.emit('investidores_atualizados', {
        'mes': PERIODO_INVESTIDORES[0],
        'financeiro': _calcular_financeiro(PERIODO_INVESTIDORES[0], investidores=investidores),
        'registros': [investidor.to_dict() for investidor in investidores],
        'acoes': [item.to_dict() for item in consultar_acoes('investidores', _semanas_periodo_investidores(PERIODO_INVESTIDORES[0]))],
    })


@investidores_bp.route('/acao', methods=['POST'])
@login_required
@requer_investidores
def registrar_acao():
    dados = request.get_json(silent=True) or request.form.to_dict()
    try:
        investidor_id = int(dados.get('investidor_id', 0) or 0)
    except (TypeError, ValueError):
        investidor_id = 0

    acao_realizada = _normalizar_texto(dados.get('acao_realizada'))
    if not acao_realizada:
        return jsonify({'erro': 'Descreva a acao realizada.'}), 400

    if investidor_id <= 0:
        mes_slug = (dados.get('mes') or '').strip().lower()
        try:
            semana_local = int(dados.get('semana', 1) or 1)
        except (TypeError, ValueError):
            semana_local = 0
        if mes_slug not in MESES_MAP:
            return jsonify({'erro': 'Mes invalido para registrar a acao.'}), 400
        if semana_local not in {1, 2, 3, 4}:
            return jsonify({'erro': 'Semana invalida para registrar a acao.'}), 400
        semana_global = MESES_MAP[mes_slug]['semana_inicio'] + semana_local - 1
        bloqueio = _garantir_semana_editavel_global(semana_global)
        if bloqueio:
            return bloqueio
        nova_acao = IndicadorAcao(
            scope='investidores',
            semana=semana_global,
            descricao=acao_realizada,
            responsavel=current_user.nome.upper(),
        )
        db.session.add(nova_acao)
        db.session.commit()
        _broadcast_update(PERIODO_INVESTIDORES[0])
        return jsonify({'sucesso': True, 'acao': nova_acao.to_dict(), 'acao_direta': True}), 201

    investidor = db.session.get(Investidor, investidor_id)
    if not investidor:
        return jsonify({'erro': 'Investidor nao encontrado.'}), 404

    semana_global = _semana_global_por_data(investidor.data_reserva)
    bloqueio = _garantir_semana_editavel_global(semana_global)
    if bloqueio:
        return bloqueio

    nova_acao = IndicadorAcao(
        scope='investidores',
        semana=semana_global,
        descricao=acao_realizada,
        responsavel=current_user.nome.upper(),
        registro_id=investidor.id,
        registro_tipo='investidores',
    )
    db.session.add(nova_acao)
    db.session.commit()

    _broadcast_update(PERIODO_INVESTIDORES[0])
    return jsonify({'sucesso': True, 'acao': nova_acao.to_dict()})


def _validar_payload_investidor(dados: dict) -> tuple[dict, str | None]:
    registro = {
        'reserva': _normalizar_texto(dados.get('reserva')),
        'data_reserva': _parse_data(dados.get('data')),
        'situacao': _normalizar_situacao(dados.get('situacao')),
        'tipo_venda': _normalizar_tipo_venda(dados.get('tipo_venda'), 'DIRETA'),
        'empreendimento': _normalizar_texto(dados.get('empreendimento')),
        'bloco': _normalizar_texto(dados.get('bloco')),
        'unidade': _normalizar_texto(dados.get('unidade')),
        'cliente': _normalizar_texto(dados.get('cliente')),
        'corretor': _normalizar_texto(dados.get('corretor')),
        'imobiliaria': _normalizar_texto(dados.get('imobiliaria')),
        'valor_presente': _parse_decimal(dados.get('valor_presente')),
    }
    obrigatorios = ('reserva', 'data_reserva', 'situacao', 'tipo_venda', 'empreendimento', 'cliente')
    for campo in obrigatorios:
        if not registro.get(campo):
            return registro, f'Campo obrigatorio ausente: {campo}'
    if registro['empreendimento'] == EMPREENDIMENTO_IGNORADO:
        return registro, 'Empreendimento desconsiderado para o Grid de Investidores.'
    if registro['situacao'] not in SITUACAO_INVESTIDOR_OPCOES:
        return registro, 'Situacao invalida.'
    if registro['tipo_venda'] not in TIPO_VENDA_OPCOES:
        return registro, 'Tipo de venda invalido.'
    return registro, None


@investidores_bp.route('/')
@login_required
@requer_investidores
def index():
    mes_slug = _mes_slug_atual()
    semana_local = None if mes_slug == PERIODO_INVESTIDORES[0] else _semana_do_mes_atual()
    return render_template(
        'investidores/index.html',
        **montar_contexto_template_investidores(mes_slug, incluir_resumo=False, semana_local=semana_local),
    )


@investidores_bp.route('/registros')
@login_required
@requer_investidores
def listar_registros():
    mes_slug = _mes_slug_atual()
    semana_local = None if mes_slug == PERIODO_INVESTIDORES[0] else _semana_do_mes_atual()
    investidores = _consultar_investidores_periodo(mes_slug, semana_local=semana_local)
    return jsonify({
        'registros': [investidor.to_dict() for investidor in investidores],
        'financeiro': _calcular_financeiro(mes_slug, investidores=investidores, semana_local=semana_local),
        'acoes': [item.to_dict() for item in consultar_acoes('investidores', _semanas_periodo_investidores(mes_slug, semana_local))],
    })


@investidores_bp.route('/acao/<int:acao_id>', methods=['DELETE'])
@login_required
@requer_investidores
def deletar_acao(acao_id):
    acao = db.session.get(IndicadorAcao, acao_id)
    if not acao or acao.scope != 'investidores':
        return jsonify({'erro': 'Acao nao encontrada.'}), 404
    bloqueio = _garantir_semana_editavel_global(acao.semana)
    if bloqueio:
        return bloqueio
    if not (current_user.can_manage_admin() or acao.responsavel == current_user.nome.upper()):
        return jsonify({'erro': 'Voce so pode excluir acoes registradas por voce.'}), 403

    db.session.delete(acao)
    db.session.commit()
    _broadcast_update(PERIODO_INVESTIDORES[0])
    return jsonify({'sucesso': True})


@investidores_bp.route('/ai-chat', methods=['POST'])
@login_required
@requer_investidores
def investidores_ai_chat():
    if not current_user.can_manage_admin():
        abort(403)
    if not analytics_ai_enabled():
        return jsonify({'erro': 'A assistente analitica nao esta configurada.'}), 503
    if not analytics_ai_available():
        return jsonify({'erro': 'Dependencia da assistente nao instalada.'}), 503

    dados = request.get_json(silent=True) or {}
    pergunta = (dados.get('message') or '').strip()
    if not pergunta:
        return jsonify({'erro': 'Pergunta obrigatoria.'}), 400

    mes_slug = (dados.get('mes') or PERIODO_INVESTIDORES[0]).strip().lower()
    if mes_slug != PERIODO_INVESTIDORES[0] and mes_slug not in MESES_MAP:
        mes_slug = PERIODO_INVESTIDORES[0]
    history = dados.get('history') or []
    investidores = _consultar_investidores_periodo(mes_slug)
    financeiro = _calcular_financeiro(mes_slug, investidores=investidores)
    contexto = build_global_ai_context(
        page='painel_investidores',
        actor=current_user,
        extra_context={
            'mes_atual': mes_slug,
            'periodo': 'Resumo Trimestral' if mes_slug == PERIODO_INVESTIDORES[0] else MESES_MAP[mes_slug]['nome'],
            'resumo_painel': financeiro,
            'situacoes_funil': {item['label']: item['quantidade'] for item in financeiro['funil']},
        },
    )

    try:
        resposta = ask_analytics_assistant(pergunta, history, contexto)
    except Exception:
        resposta = fallback_analytics_answer(pergunta, contexto)

    return jsonify({'answer': resposta})


@investidores_bp.route('/cadastrar', methods=['POST'])
@login_required
@requer_investidores
def cadastrar():
    dados = request.get_json(silent=True) or request.form.to_dict()
    registro, erro = _validar_payload_investidor(dados)
    if erro:
        status = 202 if 'desconsiderado' in erro.lower() else 400
        return jsonify({'sucesso': status == 202, 'ignorado': status == 202, 'erro': erro}), status

    bloqueio = _garantir_semana_editavel_por_data(registro['data_reserva'])
    if bloqueio:
        return bloqueio

    investidor = Investidor(
        reserva=registro['reserva'],
        data_reserva=registro['data_reserva'],
        situacao=registro['situacao'],
        tipo_venda=registro['tipo_venda'],
        empreendimento=registro['empreendimento'],
        bloco=registro['bloco'] or None,
        unidade=registro['unidade'] or None,
        cliente=registro['cliente'],
        corretor=registro['corretor'] or None,
        imobiliaria=registro['imobiliaria'] or None,
        valor_presente=registro['valor_presente'],
        acao_realizada=_normalizar_texto(dados.get('acao_realizada')) or None,
        criado_por=current_user.nome.upper(),
    )
    db.session.add(investidor)
    db.session.flush()
    sincronizar_acao_registro(
        'investidores',
        _semana_global_por_data(investidor.data_reserva),
        investidor.acao_realizada,
        current_user.nome.upper(),
        investidor.id,
        'investidores_registro',
    )
    db.session.commit()

    _broadcast_update(PERIODO_INVESTIDORES[0])
    return jsonify({'sucesso': True, 'id': investidor.id}), 201


@investidores_bp.route('/bulk-cadastrar', methods=['POST'])
@login_required
@requer_investidores
def bulk_cadastrar():
    dados = request.get_json(silent=True) or {}
    linhas = dados.get('linhas') or []
    if not isinstance(linhas, list) or not linhas:
        return jsonify({'erro': 'Nenhuma linha informada para importacao.'}), 400

    investidores: list[Investidor] = []
    meses_afetados: set[str] = set()
    ignoradas = 0
    for indice, linha in enumerate(linhas, start=1):
        registro, erro = _validar_payload_investidor(linha or {})
        if erro:
            if 'desconsiderado' in erro.lower():
                ignoradas += 1
                continue
            return jsonify({'erro': f'Linha {indice}: {erro}'}), 400
        bloqueio = _garantir_semana_editavel_por_data(registro['data_reserva'])
        if bloqueio:
            return bloqueio

        investidor = Investidor(
            reserva=registro['reserva'],
            data_reserva=registro['data_reserva'],
            situacao=registro['situacao'],
            tipo_venda=registro['tipo_venda'],
            empreendimento=registro['empreendimento'],
            bloco=registro['bloco'] or None,
            unidade=registro['unidade'] or None,
            cliente=registro['cliente'],
            corretor=registro['corretor'] or None,
            imobiliaria=registro['imobiliaria'] or None,
            valor_presente=registro['valor_presente'],
            criado_por=current_user.nome.upper(),
        )
        investidores.append(investidor)
        meses_afetados.add(PERIODO_INVESTIDORES[0])

    if investidores:
        db.session.add_all(investidores)
        db.session.commit()
        for mes_slug in meses_afetados:
            _broadcast_update(mes_slug)

    return jsonify({'sucesso': True, 'quantidade': len(investidores), 'ignoradas': ignoradas}), 201


@investidores_bp.route('/registro/<int:reg_id>', methods=['PUT'])
@login_required
@requer_investidores
def editar_registro(reg_id):
    investidor = db.session.get(Investidor, reg_id)
    if not investidor:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404

    bloqueio = _garantir_semana_editavel_por_data(investidor.data_reserva)
    if bloqueio:
        return bloqueio

    dados = request.get_json(silent=True) or request.form.to_dict()
    registro, erro = _validar_payload_investidor(dados)
    if erro:
        return jsonify({'erro': erro}), 400

    bloqueio = _garantir_semana_editavel_por_data(registro['data_reserva'])
    if bloqueio:
        return bloqueio

    mes_anterior = PERIODO_INVESTIDORES[0]
    investidor.reserva = registro['reserva']
    investidor.data_reserva = registro['data_reserva']
    investidor.situacao = registro['situacao']
    investidor.tipo_venda = registro['tipo_venda']
    investidor.empreendimento = registro['empreendimento']
    investidor.bloco = registro['bloco'] or None
    investidor.unidade = registro['unidade'] or None
    investidor.cliente = registro['cliente']
    investidor.corretor = registro['corretor'] or None
    investidor.imobiliaria = registro['imobiliaria'] or None
    investidor.valor_presente = registro['valor_presente']
    investidor.acao_realizada = _normalizar_texto(dados.get('acao_realizada')) or None
    sincronizar_acao_registro(
        'investidores',
        _semana_global_por_data(investidor.data_reserva),
        investidor.acao_realizada,
        current_user.nome.upper(),
        investidor.id,
        'investidores_registro',
    )
    db.session.commit()

    mes_atual = PERIODO_INVESTIDORES[0]
    _broadcast_update(mes_atual)
    if mes_atual != mes_anterior:
        _broadcast_update(mes_anterior)
    return jsonify({'sucesso': True, 'registro': investidor.to_dict()})


@investidores_bp.route('/registro/<int:reg_id>', methods=['DELETE'])
@login_required
@requer_investidores
def deletar_registro(reg_id):
    investidor = db.session.get(Investidor, reg_id)
    if not investidor:
        return jsonify({'erro': 'Registro nao encontrado.'}), 404
    bloqueio = _garantir_semana_editavel_por_data(investidor.data_reserva)
    if bloqueio:
        return bloqueio

    db.session.delete(investidor)
    db.session.commit()
    _broadcast_update(PERIODO_INVESTIDORES[0])
    return jsonify({'sucesso': True})


@investidores_bp.route('/registros', methods=['DELETE'])
@login_required
@requer_investidores
def deletar_todos_registros():
    investidores = Investidor.query.all()
    if not investidores:
        return jsonify({'sucesso': True, 'quantidade': 0})
    for investidor in investidores:
        bloqueio = _garantir_semana_editavel_por_data(investidor.data_reserva)
        if bloqueio:
            return bloqueio

    for investidor in investidores:
        db.session.delete(investidor)
    db.session.commit()
    _broadcast_update(PERIODO_INVESTIDORES[0])
    return jsonify({'sucesso': True, 'quantidade': len(investidores)})
