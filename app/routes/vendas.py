from datetime import datetime
from functools import wraps
import unicodedata

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import extract, func

from app import db, socketio
from app.models.empreendimento import Empreendimento
from app.models.meta_venda import MetaVendaVarejo
from app.models.venda import SITUACAO_VENDA_OPCOES, Venda
from app.services.analytics_ai import analytics_ai_available, analytics_ai_enabled, ask_analytics_assistant


vendas_bp = Blueprint('vendas', __name__)

MESES_VENDAS = [
    ('abril', 'Abril', 4),
    ('maio', 'Maio', 5),
    ('junho', 'Junho', 6),
]
MESES_MAP = {slug: {'slug': slug, 'nome': nome, 'numero': numero} for slug, nome, numero in MESES_VENDAS}
RESUMO_TRIMESTRAL = ('resumo_trimestral', 'Resumo Trimestral', None)
EMPREENDIMENTO_IGNORADO = 'J J NEGOCIOS IMOBILIARIOS'
SITUACOES_FUNIL_AGRUPADAS = {
    'CANCELADA': 'Cancelada',
    'CONFECCAO DE CONTRATO': 'Confecção de Contrato',
    'CONTRATO ASSINADO': 'Contrato Assinado / Contrato Assinado Clientes',
    'CONTRATO ASSINADO CLIENTES': 'Contrato Assinado / Contrato Assinado Clientes',
    'NOVA RESERVA': 'Nova Reserva',
    'PENDENTE DE ASSINATURA': 'Pendente de Assinatura',
}


def requer_vendas(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.tipo not in ('admin', 'comercial'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _mes_slug_atual() -> str:
    mes = (request.args.get('mes') or request.form.get('mes') or '').strip().lower()
    if mes == RESUMO_TRIMESTRAL[0]:
        return mes
    return mes if mes in MESES_MAP else 'abril'


def montar_contexto_template_vendas(mes_slug: str, incluir_resumo: bool = False) -> dict:
    if mes_slug == RESUMO_TRIMESTRAL[0] and not incluir_resumo:
        mes_slug = 'abril'
    mes_info = {'nome': RESUMO_TRIMESTRAL[1]} if mes_slug == RESUMO_TRIMESTRAL[0] else MESES_MAP[mes_slug]
    empreendimentos = Empreendimento.query.filter_by(ativo=True).order_by(Empreendimento.nome).all()
    vendas = _consultar_vendas_periodo(mes_slug)
    meses = list(MESES_VENDAS)
    if incluir_resumo:
        meses.append(RESUMO_TRIMESTRAL)
    return {
        'meses': meses,
        'mes_atual': mes_slug,
        'mes_atual_nome': mes_info['nome'],
        'empreendimentos': empreendimentos,
        'situacoes': SITUACAO_VENDA_OPCOES,
        'financeiro': _calcular_financeiro(mes_slug),
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


def _consultar_vendas_por_mes(mes_numero: int):
    return (
        Venda.query
        .filter(extract('month', Venda.data_reserva) == mes_numero)
        .filter(func.upper(Venda.empreendimento) != EMPREENDIMENTO_IGNORADO)
        .order_by(Venda.data_reserva.desc(), Venda.id.desc())
        .all()
    )


def _consultar_vendas_periodo(mes_slug: str):
    if mes_slug == RESUMO_TRIMESTRAL[0]:
        return (
            Venda.query
            .filter(extract('month', Venda.data_reserva).in_([4, 5, 6]))
            .filter(func.upper(Venda.empreendimento) != EMPREENDIMENTO_IGNORADO)
            .order_by(Venda.data_reserva.desc(), Venda.id.desc())
            .all()
        )
    return _consultar_vendas_por_mes(MESES_MAP[mes_slug]['numero'])


def _obter_meta_mes(mes_slug: str) -> float:
    meta = MetaVendaVarejo.query.filter_by(mes=mes_slug).first()
    return int(meta.quantidade_meta) if meta else 0


def _obter_meta_trimestral() -> int:
    return sum(_obter_meta_mes(slug) for slug, _, _ in MESES_VENDAS)


def _montar_funil(vendas: list[Venda]) -> list[dict]:
    agrupado: dict[str, int] = {
        'Vendida': 0,
        'Cancelada': 0,
        'Confecção de Contrato': 0,
        'Contrato Assinado / Contrato Assinado Clientes': 0,
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


def _calcular_financeiro(mes_slug: str) -> dict:
    vendas = _consultar_vendas_periodo(mes_slug)
    meta_quantidade = _obter_meta_trimestral() if mes_slug == RESUMO_TRIMESTRAL[0] else _obter_meta_mes(mes_slug)
    valor_realizado = sum(
        float(venda.valor_presente or 0)
        for venda in vendas
        if _normalizar_situacao(venda.situacao) == 'VENDIDA'
    )
    total_vendidas = sum(1 for venda in vendas if _normalizar_situacao(venda.situacao) == 'VENDIDA')
    percentual = round((total_vendidas / meta_quantidade) * 100, 1) if meta_quantidade > 0 else 0.0
    return {
        'mes': mes_slug,
        'meta_quantidade': meta_quantidade,
        'valor_realizado': valor_realizado,
        'percentual_atingimento': percentual,
        'total_registros': len(vendas),
        'total_vendidas': total_vendidas,
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


def _validar_payload_venda(dados: dict) -> tuple[dict, str | None]:
    registro = {
        'reserva': _normalizar_texto(dados.get('reserva')),
        'data_reserva': _parse_data(dados.get('data')),
        'situacao': _normalizar_situacao(dados.get('situacao')),
        'empreendimento': _normalizar_texto(dados.get('empreendimento')),
        'bloco': _normalizar_texto(dados.get('bloco')),
        'unidade': _normalizar_texto(dados.get('unidade')),
        'cliente': _normalizar_texto(dados.get('cliente')),
        'corretor': _normalizar_texto(dados.get('corretor')),
        'imobiliaria': _normalizar_texto(dados.get('imobiliaria')),
        'valor_presente': _parse_decimal(dados.get('valor_presente')),
    }
    obrigatorios = ('reserva', 'data_reserva', 'situacao', 'empreendimento', 'cliente')
    for campo in obrigatorios:
        if not registro.get(campo):
            return registro, f'Campo obrigatório ausente: {campo}'
    if registro['empreendimento'] == EMPREENDIMENTO_IGNORADO:
        return registro, 'Empreendimento desconsiderado para o Grid de Vendas.'
    if registro['situacao'] not in SITUACAO_VENDA_OPCOES:
        return registro, 'Situação inválida.'
    mes_valido = any(registro['data_reserva'].month == info['numero'] for info in MESES_MAP.values())
    if not mes_valido:
        return registro, 'A data deve estar entre abril e junho.'
    return registro, None


@vendas_bp.route('/')
@login_required
@requer_vendas
def index():
    return render_template('vendas/index.html', **montar_contexto_template_vendas(_mes_slug_atual(), incluir_resumo=False))


@vendas_bp.route('/registros')
@login_required
@requer_vendas
def listar_registros():
    mes_slug = _mes_slug_atual()
    vendas = _consultar_vendas_periodo(mes_slug)
    return jsonify({
        'registros': [venda.to_dict() for venda in vendas],
        'financeiro': _calcular_financeiro(mes_slug),
    })


@vendas_bp.route('/ai-chat', methods=['POST'])
@login_required
@requer_vendas
def vendas_ai_chat():
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

    try:
        resposta = ask_analytics_assistant(pergunta, history, _montar_contexto_ia_vendas(mes_slug))
    except Exception:
        return jsonify({'erro': 'Nao foi possivel consultar a assistente analitica no momento.'}), 502

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
        criado_por=current_user.nome.upper(),
    )
    db.session.add(venda)
    db.session.commit()

    mes_slug = next(slug for slug, _, numero in MESES_VENDAS if numero == venda.data_reserva.month)
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
            criado_por=current_user.nome.upper(),
        )
        vendas.append(venda)
        meses_afetados.add(next(slug for slug, _, numero in MESES_VENDAS if numero == venda.data_reserva.month))

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

    mes_anterior = next(slug for slug, _, numero in MESES_VENDAS if numero == venda.data_reserva.month)
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
    db.session.commit()

    mes_atual = next(slug for slug, _, numero in MESES_VENDAS if numero == venda.data_reserva.month)
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
    mes_slug = next(slug for slug, _, numero in MESES_VENDAS if numero == venda.data_reserva.month)
    db.session.delete(venda)
    db.session.commit()
    _broadcast_update(mes_slug)
    return jsonify({'sucesso': True})
