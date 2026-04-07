from datetime import datetime
from functools import wraps
import unicodedata

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import extract, func

from app import db, socketio
from app.models.empreendimento import Empreendimento
from app.models.meta_configuracao import MetaConfiguracaoIndicador
from app.models.meta_venda_semana import MetaVendaSemana
from app.models.venda import SITUACAO_VENDA_OPCOES, TIPO_VENDA_OPCOES, Venda
from app.services.analytics_ai import analytics_ai_available, analytics_ai_enabled, ask_analytics_assistant, build_global_ai_context, fallback_analytics_answer


vendas_bp = Blueprint('vendas', __name__)

MESES_VENDAS = [
    ('abril', 'Abril', 4, 1),
    ('maio', 'Maio', 5, 5),
    ('junho', 'Junho', 6, 9),
]
MESES_MAP = {slug: {'slug': slug, 'nome': nome, 'numero': numero, 'semana_inicio': semana_inicio} for slug, nome, numero, semana_inicio in MESES_VENDAS}
RESUMO_TRIMESTRAL = ('resumo_trimestral', 'Resumo Trimestral', None)
EMPREENDIMENTO_IGNORADO = 'J J NEGOCIOS IMOBILIARIOS'
SITUACOES_FUNIL_AGRUPADAS = {
    'CANCELADA': 'Cancelada',
    'CONFECCAO DE CONTRATO': 'Confecção de Contrato',
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
    'FINANCIADA': 'FINANCIADA',
    'FINANCIADO': 'FINANCIADA',
    'FINANCIAMENTO': 'FINANCIADA',
    'INDIRETA': 'INDIRETA',
    'PARCERIA': 'PARCERIA',
    'REPASSE': 'REPASSE',
}


def requer_vendas(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.can_access_page('vendas'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _mes_slug_atual() -> str:
    mes = (request.args.get('mes') or request.form.get('mes') or '').strip().lower()
    if mes == RESUMO_TRIMESTRAL[0]:
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
    if mes_slug and mes_slug in MESES_MAP:
        mes_numero = MESES_MAP[mes_slug]['numero']
    for slug, info in MESES_MAP.items():
        if info['numero'] == mes_numero:
            semana_local = min(((data_reserva.day - 1) // 7) + 1, 4)
            return info['semana_inicio'] + semana_local - 1
    return None


def montar_contexto_template_vendas(mes_slug: str, incluir_resumo: bool = False, semana_local: int | None = None) -> dict:
    if mes_slug == RESUMO_TRIMESTRAL[0] and not incluir_resumo:
        mes_slug = 'abril'
    semana_local_normalizada = semana_local if semana_local in {1, 2, 3, 4} else None
    mes_info = {'nome': RESUMO_TRIMESTRAL[1]} if mes_slug == RESUMO_TRIMESTRAL[0] else MESES_MAP[mes_slug]
    empreendimentos = Empreendimento.query.filter_by(ativo=True).order_by(Empreendimento.nome).all()
    vendas = _consultar_vendas_periodo(mes_slug, semana_local=semana_local_normalizada)
    meses = [(slug, nome, numero) for slug, nome, numero, _ in MESES_VENDAS]
    if incluir_resumo:
        meses.append(RESUMO_TRIMESTRAL)
    semana_global = None
    if mes_slug != RESUMO_TRIMESTRAL[0] and semana_local_normalizada is not None:
        semana_global = MESES_MAP[mes_slug]['semana_inicio'] + semana_local_normalizada - 1
    return {
        'meses': meses,
        'mes_atual': mes_slug,
        'semana_atual': semana_local_normalizada,
        'semana_global_atual': semana_global,
        'mes_atual_nome': mes_info['nome'],
        'empreendimentos': empreendimentos,
        'situacoes': SITUACAO_VENDA_OPCOES,
        'tipos_venda': TIPO_VENDA_OPCOES,
        'financeiro': _calcular_financeiro(mes_slug, vendas=vendas, semana_local=semana_local_normalizada),
        'registros': vendas,
        'registros_json': [venda.to_dict() for venda in vendas],
        'resumo_trimestral': mes_slug == RESUMO_TRIMESTRAL[0],
        'analytics_ai_enabled': analytics_ai_enabled() and analytics_ai_available(),
        'incluir_resumo_tabs': incluir_resumo,
        'painel_admin_vendas': False,
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


def _consultar_vendas_por_mes(mes_numero: int):
    return (
        Venda.query
        .filter(extract('month', Venda.data_reserva) == mes_numero)
        .filter(func.upper(Venda.empreendimento) != EMPREENDIMENTO_IGNORADO)
        .order_by(Venda.data_reserva.desc(), Venda.id.desc())
        .all()
    )


def _mes_slug_por_numero(mes_numero: int) -> str:
    return next(slug for slug, _, numero, _ in MESES_VENDAS if numero == mes_numero)


def _consultar_vendas_periodo(mes_slug: str, semana_local: int | None = None):
    if mes_slug == RESUMO_TRIMESTRAL[0]:
        return (
            Venda.query
            .filter(extract('month', Venda.data_reserva).in_([4, 5, 6]))
            .filter(func.upper(Venda.empreendimento) != EMPREENDIMENTO_IGNORADO)
            .order_by(Venda.data_reserva.desc(), Venda.id.desc())
            .all()
        )
    vendas = _consultar_vendas_por_mes(MESES_MAP[mes_slug]['numero'])
    if semana_local is None:
        return vendas
    semana_global = MESES_MAP[mes_slug]['semana_inicio'] + semana_local - 1
    return [venda for venda in vendas if _semana_global_por_data(venda.data_reserva, mes_slug) == semana_global]


def _obter_meta_semana(semana_global: int | None) -> int:
    if not semana_global:
        return 0
    meta = MetaVendaSemana.query.filter_by(semana=semana_global).first()
    return int(meta.quantidade_meta) if meta else 0


def _obter_meta_acoes_semana(semana_global: int | None) -> int:
    if not semana_global:
        return 0
    meta = MetaVendaSemana.query.filter_by(semana=semana_global).first()
    return int(meta.acoes_planejadas or 0) if meta else 0


def _obter_meta_mes(mes_slug: str) -> int:
    inicio = MESES_MAP[mes_slug]['semana_inicio']
    return sum(_obter_meta_semana(inicio + offset) for offset in range(4))


def _obter_meta_trimestral() -> int:
    return sum(_obter_meta_mes(slug) for slug, _, _, _ in MESES_VENDAS)


def _obter_meta_acoes_mes(mes_slug: str) -> int:
    inicio = MESES_MAP[mes_slug]['semana_inicio']
    return sum(_obter_meta_acoes_semana(inicio + offset) for offset in range(4))


def _obter_meta_acoes_trimestral() -> int:
    return sum(_obter_meta_acoes_mes(slug) for slug, _, _, _ in MESES_VENDAS)


def _montar_funil(vendas: list[Venda]) -> list[dict]:
    agrupado: dict[str, int] = {
        'Vendida': 0,
        'Cancelada': 0,
        'Confecção de Contrato': 0,
        'Contrato Assinado / Contrato Assinado Clientes': 0,
        'Envio UAU': 0,
        'Nova Reserva': 0,
        'Pendente de Assinatura': 0,
    }
    total = 0
    for venda in vendas:
        situacao = _normalizar_situacao(venda.situacao)
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
        'Confecção de Contrato': '#C27D2C',
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


def _calcular_financeiro(mes_slug: str, vendas: list[Venda] | None = None, semana_local: int | None = None) -> dict:
    vendas = vendas if vendas is not None else _consultar_vendas_periodo(mes_slug, semana_local=semana_local)
    if mes_slug == RESUMO_TRIMESTRAL[0]:
        meta_quantidade = _obter_meta_trimestral()
        meta_acoes = _obter_meta_acoes_trimestral()
    elif semana_local:
        semana_global = MESES_MAP[mes_slug]['semana_inicio'] + semana_local - 1
        meta_quantidade = _obter_meta_semana(semana_global)
        meta_acoes = _obter_meta_acoes_semana(semana_global)
    else:
        meta_quantidade = _obter_meta_mes(mes_slug)
        meta_acoes = _obter_meta_acoes_mes(mes_slug)
    valor_realizado = sum(
        float(venda.valor_presente or 0)
        for venda in vendas
        if _normalizar_situacao(venda.situacao) == 'VENDIDA'
    )
    total_vendidas = sum(1 for venda in vendas if _normalizar_situacao(venda.situacao) == 'VENDIDA')
    acoes_realizadas = sum(1 for venda in vendas if (venda.acao_realizada or '').strip())
    percentual = round((total_vendidas / meta_quantidade) * 100, 1) if meta_quantidade > 0 else 0.0
    percentual_acoes = round((acoes_realizadas / meta_acoes) * 100, 1) if meta_acoes > 0 else 0.0
    meta_base = MetaConfiguracaoIndicador.query.filter_by(scope='vendas').first()
    return {
        'mes': mes_slug,
        'semana_local': semana_local,
        'meta_quantidade': meta_quantidade,
        'meta_base_total': float(meta_base.meta_base_total or 0) if meta_base else 0.0,
        'meta_acoes': meta_acoes,
        'valor_realizado': valor_realizado,
        'percentual_atingimento': percentual,
        'total_registros': len(vendas),
        'total_vendidas': total_vendidas,
        'acoes_realizadas': acoes_realizadas,
        'percentual_acoes': percentual_acoes,
        'funil': _montar_funil(vendas),
    }


def _listar_opcoes_filtro_vendas(coluna) -> list[str]:
    valores = (
        db.session.query(coluna)
        .filter(coluna.isnot(None))
        .filter(func.upper(Venda.empreendimento) != EMPREENDIMENTO_IGNORADO)
        .distinct()
        .order_by(coluna.asc())
        .all()
    )
    return [valor[0] for valor in valores if valor[0]]


def _montar_contexto_ia_vendas(mes_slug: str) -> dict:
    vendas = _consultar_vendas_periodo(mes_slug)
    financeiro = _calcular_financeiro(mes_slug)
    return {
        'periodo': 'Resumo Trimestral' if mes_slug == RESUMO_TRIMESTRAL[0] else MESES_MAP[mes_slug]['nome'],
        'resumo_financeiro': financeiro,
        'registros': [venda.to_dict() for venda in vendas[:500]],
        'situacoes': {item['label']: item['quantidade'] for item in financeiro['funil']},
        'tipos_venda': _listar_opcoes_filtro_vendas(Venda.tipo_venda),
        'empreendimentos': _listar_opcoes_filtro_vendas(Venda.empreendimento),
        'corretores': _listar_opcoes_filtro_vendas(Venda.corretor),
        'imobiliarias': _listar_opcoes_filtro_vendas(Venda.imobiliaria),
    }


def _broadcast_update(mes_slug: str):
    mes_info = MESES_MAP[mes_slug]
    vendas = _consultar_vendas_por_mes(mes_info['numero'])
    socketio.emit('vendas_atualizadas', {
        'mes': mes_slug,
        'financeiro': _calcular_financeiro(mes_slug),
        'registros': [venda.to_dict() for venda in vendas],
    })


@vendas_bp.route('/acao', methods=['POST'])
@login_required
@requer_vendas
def registrar_acao():
    dados = request.get_json(silent=True) or request.form.to_dict()
    try:
        venda_id = int(dados.get('venda_id', 0) or 0)
    except (TypeError, ValueError):
        venda_id = 0
    if venda_id <= 0:
        return jsonify({'erro': 'Selecione uma venda para registrar a ação.'}), 400

    acao_realizada = _normalizar_texto(dados.get('acao_realizada'))
    if not acao_realizada:
        return jsonify({'erro': 'Descreva a ação realizada.'}), 400

    venda = db.session.get(Venda, venda_id)
    if not venda:
        return jsonify({'erro': 'Venda não encontrada.'}), 404

    venda.acao_realizada = acao_realizada
    db.session.commit()

    mes_slug = _mes_slug_por_numero(venda.data_reserva.month)
    _broadcast_update(mes_slug)
    return jsonify({'sucesso': True, 'registro': venda.to_dict()})


def _validar_payload_venda(dados: dict) -> tuple[dict, str | None]:
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
        'acao_realizada': _normalizar_texto(dados.get('acao_realizada')),
    }
    obrigatorios = ('reserva', 'data_reserva', 'situacao', 'tipo_venda', 'empreendimento', 'cliente')
    for campo in obrigatorios:
        if not registro.get(campo):
            return registro, f'Campo obrigatório ausente: {campo}'
    if registro['empreendimento'] == EMPREENDIMENTO_IGNORADO:
        return registro, 'Empreendimento desconsiderado para o Grid de Vendas.'
    if registro['situacao'] not in SITUACAO_VENDA_OPCOES:
        return registro, 'Situação inválida.'
    if registro['tipo_venda'] not in TIPO_VENDA_OPCOES:
        return registro, 'Tipo de venda inválido.'
    mes_valido = any(registro['data_reserva'].month == info['numero'] for info in MESES_MAP.values())
    if not mes_valido:
        return registro, 'A data deve estar entre abril e junho.'
    return registro, None


@vendas_bp.route('/')
@login_required
@requer_vendas
def index():
    return render_template('vendas/index.html', **montar_contexto_template_vendas(_mes_slug_atual(), incluir_resumo=False, semana_local=_semana_do_mes_atual()))


@vendas_bp.route('/registros')
@login_required
@requer_vendas
def listar_registros():
    mes_slug = _mes_slug_atual()
    semana_local = _semana_do_mes_atual()
    vendas = _consultar_vendas_periodo(mes_slug, semana_local=semana_local)
    return jsonify({
        'registros': [venda.to_dict() for venda in vendas],
        'financeiro': _calcular_financeiro(mes_slug, vendas=vendas, semana_local=semana_local),
    })


@vendas_bp.route('/ai-chat', methods=['POST'])
@login_required
@requer_vendas
def vendas_ai_chat():
    if current_user.tipo != 'admin':
        abort(403)
    if not analytics_ai_enabled():
        return jsonify({'erro': 'A assistente analitica nao esta configurada.'}), 503
    if not analytics_ai_available():
        return jsonify({'erro': 'Dependencia da assistente nao instalada.'}), 503

    dados = request.get_json(silent=True) or {}
    pergunta = (dados.get('message') or '').strip()
    if not pergunta:
        return jsonify({'erro': 'Pergunta obrigatoria.'}), 400

    mes_slug = (dados.get('mes') or RESUMO_TRIMESTRAL[0]).strip().lower()
    if mes_slug != RESUMO_TRIMESTRAL[0] and mes_slug not in MESES_MAP:
        mes_slug = RESUMO_TRIMESTRAL[0]
    history = dados.get('history') or []
    financeiro = _calcular_financeiro(mes_slug)
    contexto = build_global_ai_context(
        page='painel_vendas',
        actor=current_user,
        extra_context={
            'mes_atual': mes_slug,
            'periodo': 'Resumo Trimestral' if mes_slug == RESUMO_TRIMESTRAL[0] else MESES_MAP[mes_slug]['nome'],
            'resumo_painel': financeiro,
            'situacoes_funil': {item['label']: item['quantidade'] for item in financeiro['funil']},
        },
    )

    try:
        resposta = ask_analytics_assistant(pergunta, history, contexto)
    except Exception:
        resposta = fallback_analytics_answer(pergunta, contexto)

    return jsonify({'answer': resposta})


@vendas_bp.route('/cadastrar', methods=['POST'])
@login_required
@requer_vendas
def cadastrar():
    dados = request.get_json(silent=True) or request.form.to_dict()
    registro, erro = _validar_payload_venda(dados)
    if erro:
        status = 202 if 'desconsiderado' in erro.lower() else 400
        return jsonify({'sucesso': status == 202, 'ignorado': status == 202, 'erro': erro}), status

    venda = Venda(
        reserva=registro['reserva'],
        data_reserva=registro['data_reserva'],
        situacao=registro['situacao'],
        empreendimento=registro['empreendimento'],
        bloco=registro['bloco'] or None,
        unidade=registro['unidade'] or None,
        cliente=registro['cliente'],
        corretor=registro['corretor'] or None,
        imobiliaria=registro['imobiliaria'] or None,
        valor_presente=registro['valor_presente'],
        tipo_venda=registro['tipo_venda'],
        acao_realizada=registro['acao_realizada'] or None,
        criado_por=current_user.nome.upper(),
    )
    db.session.add(venda)
    db.session.commit()

    mes_slug = _mes_slug_por_numero(venda.data_reserva.month)
    _broadcast_update(mes_slug)
    return jsonify({'sucesso': True, 'id': venda.id}), 201


@vendas_bp.route('/bulk-cadastrar', methods=['POST'])
@login_required
@requer_vendas
def bulk_cadastrar():
    dados = request.get_json(silent=True) or {}
    linhas = dados.get('linhas') or []
    if not isinstance(linhas, list) or not linhas:
        return jsonify({'erro': 'Nenhuma linha informada para importação.'}), 400

    vendas: list[Venda] = []
    meses_afetados: set[str] = set()
    ignoradas = 0
    for indice, linha in enumerate(linhas, start=1):
        registro, erro = _validar_payload_venda(linha or {})
        if erro:
            if 'desconsiderado' in erro.lower():
                ignoradas += 1
                continue
            return jsonify({'erro': f'Linha {indice}: {erro}'}), 400
        venda = Venda(
            reserva=registro['reserva'],
            data_reserva=registro['data_reserva'],
            situacao=registro['situacao'],
            empreendimento=registro['empreendimento'],
            bloco=registro['bloco'] or None,
            unidade=registro['unidade'] or None,
            cliente=registro['cliente'],
            corretor=registro['corretor'] or None,
            imobiliaria=registro['imobiliaria'] or None,
            valor_presente=registro['valor_presente'],
            tipo_venda=registro['tipo_venda'],
            acao_realizada=registro['acao_realizada'] or None,
            criado_por=current_user.nome.upper(),
        )
        vendas.append(venda)
        meses_afetados.add(_mes_slug_por_numero(venda.data_reserva.month))

    if vendas:
        db.session.add_all(vendas)
        db.session.commit()
        for mes_slug in meses_afetados:
            _broadcast_update(mes_slug)

    return jsonify({'sucesso': True, 'quantidade': len(vendas), 'ignoradas': ignoradas}), 201


@vendas_bp.route('/registro/<int:reg_id>', methods=['PUT'])
@login_required
@requer_vendas
def editar_registro(reg_id):
    venda = db.session.get(Venda, reg_id)
    if not venda:
        return jsonify({'erro': 'Registro não encontrado.'}), 404

    dados = request.get_json(silent=True) or request.form.to_dict()
    registro, erro = _validar_payload_venda(dados)
    if erro:
        return jsonify({'erro': erro}), 400

    mes_anterior = _mes_slug_por_numero(venda.data_reserva.month)
    venda.reserva = registro['reserva']
    venda.data_reserva = registro['data_reserva']
    venda.situacao = registro['situacao']
    venda.empreendimento = registro['empreendimento']
    venda.bloco = registro['bloco'] or None
    venda.unidade = registro['unidade'] or None
    venda.cliente = registro['cliente']
    venda.corretor = registro['corretor'] or None
    venda.imobiliaria = registro['imobiliaria'] or None
    venda.valor_presente = registro['valor_presente']
    venda.tipo_venda = registro['tipo_venda']
    venda.acao_realizada = registro['acao_realizada'] or None
    db.session.commit()

    mes_atual = _mes_slug_por_numero(venda.data_reserva.month)
    _broadcast_update(mes_atual)
    if mes_atual != mes_anterior:
        _broadcast_update(mes_anterior)
    return jsonify({'sucesso': True, 'registro': venda.to_dict()})


@vendas_bp.route('/registro/<int:reg_id>', methods=['DELETE'])
@login_required
@requer_vendas
def deletar_registro(reg_id):
    venda = db.session.get(Venda, reg_id)
    if not venda:
        return jsonify({'erro': 'Registro não encontrado.'}), 404
    mes_slug = _mes_slug_por_numero(venda.data_reserva.month)
    db.session.delete(venda)
    db.session.commit()
    _broadcast_update(mes_slug)
    return jsonify({'sucesso': True})


@vendas_bp.route('/registros', methods=['DELETE'])
@login_required
@requer_vendas
def deletar_todos_registros():
    vendas = Venda.query.all()
    if not vendas:
        return jsonify({'sucesso': True, 'quantidade': 0})

    meses_afetados = {
        slug
        for venda in vendas
        for slug, _, numero, _ in MESES_VENDAS
        if venda.data_reserva and venda.data_reserva.month == numero
    }

    for venda in vendas:
        db.session.delete(venda)
    db.session.commit()

    for mes_slug in meses_afetados:
        _broadcast_update(mes_slug)

    return jsonify({'sucesso': True, 'quantidade': len(vendas)})
