from flask import Blueprint, render_template, request, jsonify, abort, flash, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps
from datetime import date, datetime, time
from sqlalchemy import func
from app import db
from app.models.user import User, DOMINIO_PERMITIDO, TIPOS_VALIDOS
from app.models.empreendimento import Empreendimento
from app.models.investidor import Investidor
from app.models.meta import MetaSemana
from app.models.meta_financeiro import MetaFinanceiroSemana
from app.models.indicador_acao import contar_acoes
from app.models.meta_fornecedor import MetaFornecedorSemana
from app.models.meta_giro import MetaGiroSemana
from app.models.meta_medicao import MetaMedicaoSemana
from app.models.meta_investidor_semana import MetaInvestidorSemana
from app.models.meta_venda_semana import MetaVendaSemana
from app.models.meta_liberacao import MetaLiberacaoSemana
from app.models.meta_configuracao import MetaConfiguracaoIndicador
from app.models.meta_auditoria import MetaAlteracaoAuditoria
from app.models.relacionamento import Relacionamento
from app.models.financeiro import BANCOS_BRASIL, FinanceiroBanco
from app.models.fornecedor import FornecedorRegistro, SITUACAO_FORNECEDOR_OPCOES
from app.models.giro import ORIGENS_GIRO, GiroCaptacao
from app.models.medicao import MedicaoRegistro
from app.routes.fornecedores import resumir_fornecedores_trimestre
from app.routes.financeiro import resumir_financeiro_bancos_trimestre
from app.routes.giro import resumir_giro_trimestre
from app.routes.medicao import resumir_medicao_trimestre
from app.routes.investidores import PERIODO_INVESTIDORES, MESES_INVESTIDORES, montar_contexto_template_investidores
from app.routes.vendas import MESES_VENDAS, montar_contexto_template_vendas
from app.services.analytics_ai import analytics_ai_available, analytics_ai_enabled, ask_analytics_assistant, build_global_ai_context, fallback_analytics_answer

MESES_RELATORIO = [
    ('abril', 'Abril', 1),
    ('maio', 'Maio', 5),
    ('junho', 'Junho', 9),
]
PERIODO_TRIMESTRAL = ('resumo_trimestral', 'Resumo Trimestral', 1)
META_FINAL_MONTH = 11
META_FINAL_DAY = 30
MIN_PASSWORD_LENGTH = 10
MASTER_START_DATE = datetime(2026, 4, 1, 0, 0, 0)
MASTER_END_DATE = datetime(2026, 6, 30, 23, 59, 59)
MASTER_METRICAS_FICTICIAS = (
    ('fornecedores', 'Fornecedores', 12.0, 100.0, 'Status provisório enquanto o painel não recebe inputs reais.'),
)


MASTER_MESES = [
    ('abril', 'Abril', range(1, 5), datetime(2026, 4, 1, 0, 0, 0), datetime(2026, 4, 30, 23, 59, 59)),
    ('maio', 'Maio', range(5, 9), datetime(2026, 5, 1, 0, 0, 0), datetime(2026, 5, 31, 23, 59, 59)),
    ('junho', 'Junho', range(9, 13), datetime(2026, 6, 1, 0, 0, 0), datetime(2026, 6, 30, 23, 59, 59)),
]
MASTER_SEMANAS = [
    ('s1', 'Abril - Semana 1', 1, datetime(2026, 4, 1, 0, 0, 0), datetime(2026, 4, 7, 23, 59, 59)),
    ('s2', 'Abril - Semana 2', 2, datetime(2026, 4, 8, 0, 0, 0), datetime(2026, 4, 14, 23, 59, 59)),
    ('s3', 'Abril - Semana 3', 3, datetime(2026, 4, 15, 0, 0, 0), datetime(2026, 4, 21, 23, 59, 59)),
    ('s4', 'Abril - Semana 4', 4, datetime(2026, 4, 28, 0, 0, 0), datetime(2026, 4, 30, 23, 59, 59)),
    ('s5', 'Maio - Semana 1', 5, datetime(2026, 5, 1, 0, 0, 0), datetime(2026, 5, 7, 23, 59, 59)),
    ('s6', 'Maio - Semana 2', 6, datetime(2026, 5, 8, 0, 0, 0), datetime(2026, 5, 14, 23, 59, 59)),
    ('s7', 'Maio - Semana 3', 7, datetime(2026, 5, 15, 0, 0, 0), datetime(2026, 5, 21, 23, 59, 59)),
    ('s8', 'Maio - Semana 4', 8, datetime(2026, 5, 28, 0, 0, 0), datetime(2026, 5, 31, 23, 59, 59)),
    ('s9', 'Junho - Semana 1', 9, datetime(2026, 6, 1, 0, 0, 0), datetime(2026, 6, 7, 23, 59, 59)),
    ('s10', 'Junho - Semana 2', 10, datetime(2026, 6, 8, 0, 0, 0), datetime(2026, 6, 14, 23, 59, 59)),
    ('s11', 'Junho - Semana 3', 11, datetime(2026, 6, 15, 0, 0, 0), datetime(2026, 6, 21, 23, 59, 59)),
    ('s12', 'Junho - Semana 4', 12, datetime(2026, 6, 28, 0, 0, 0), datetime(2026, 6, 30, 23, 59, 59)),
]


def _safe_pct(realizado: float, planejado: float) -> float:
    if planejado <= 0:
        return 0.0
    return min(round((realizado / planejado) * 100, 1), 999.9)


def _obter_meta_base_total(scope: str) -> float:
    config = MetaConfiguracaoIndicador.query.filter_by(scope=scope).first()
    return float(config.meta_base_total or 0) if config else 0.0


def _mapa_meta_base_total() -> dict[str, float]:
    return {
        item.scope: float(item.meta_base_total or 0)
        for item in MetaConfiguracaoIndicador.query.order_by(MetaConfiguracaoIndicador.scope.asc()).all()
    }


def _registrar_auditoria_meta(scope: str, campo: str, valor_anterior, valor_novo, periodo: str | None = None) -> None:
    anterior = '' if valor_anterior is None else str(valor_anterior)
    novo = '' if valor_novo is None else str(valor_novo)
    if anterior == novo:
        return
    db.session.add(
        MetaAlteracaoAuditoria(
            scope=scope,
            periodo=periodo,
            campo=campo,
            valor_anterior=anterior,
            valor_novo=novo,
            usuario_id=current_user.id,
        )
    )


def _salvar_meta_base_total(scope: str, valor: float) -> float:
    valor_normalizado = max(float(valor or 0), 0.0)
    config = MetaConfiguracaoIndicador.query.filter_by(scope=scope).first()
    anterior = float(config.meta_base_total or 0) if config else 0.0
    if config is None:
        config = MetaConfiguracaoIndicador(scope=scope, meta_base_total=valor_normalizado)
        db.session.add(config)
    else:
        config.meta_base_total = valor_normalizado
    _registrar_auditoria_meta(scope, 'meta_base_total', anterior, valor_normalizado, 'total')
    return valor_normalizado


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


def _situacao_conta_como_sim(situacao: str | None) -> bool:
    situacao_normalizada = (situacao or '').upper().strip()
    return situacao_normalizada in {'SIM', 'SIM (INTEGRAL)', 'SIM (PARCIAL)'}


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
    valor_realizado = sum(float(r.valor) for r in registros if _situacao_conta_como_sim(r.situacao) and float(r.valor) > 0)
    acoes_realizadas = contar_acoes('relacionamento', semana)
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
        valor_convertido = valor if _situacao_conta_como_sim(situacao) and valor > 0 else 0.0

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
        'registros_investidores_totais': Investidor.query.count(),
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


def _normalizar_filtros_financeiro(args) -> dict:
    return {
        'banco': (args.get('banco') or '').strip().upper(),
        'responsavel': (args.get('responsavel') or '').strip().upper(),
        'tipo_negociacao': (args.get('tipo_negociacao') or '').strip().upper(),
        'referencia': (args.get('referencia') or '').strip().upper(),
    }


def _consultar_registros_financeiro_semana(semana: int, filtros: dict):
    query = FinanceiroBanco.query.filter_by(semana=semana)
    if filtros.get('banco'):
        query = query.filter(func.upper(FinanceiroBanco.banco) == filtros['banco'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(FinanceiroBanco.responsavel) == filtros['responsavel'])
    if filtros.get('tipo_negociacao'):
        query = query.filter(func.upper(FinanceiroBanco.tipo_negociacao) == filtros['tipo_negociacao'])
    if filtros.get('referencia'):
        query = query.filter(func.upper(FinanceiroBanco.referencia) == filtros['referencia'])
    return query.order_by(FinanceiroBanco.criado_em.desc()).all()


def _coletar_semana_financeiro(semana: int, filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    meta = MetaFinanceiroSemana.query.filter_by(semana=semana).first()
    registros = _consultar_registros_financeiro_semana(semana, filtros)
    valor_planejado = float(meta.valor_meta) if meta else 0.0
    valor_realizado = sum(float(r.valor_arrecadado or 0) for r in registros)
    total_negociacoes = len(registros)
    total_bancos = len({(r.banco or '').strip() for r in registros if (r.banco or '').strip()})
    pct_bancos = _safe_pct(total_bancos, len(BANCOS_BRASIL))
    return {
        'semana': semana,
        'valor_planejado': valor_planejado,
        'valor_realizado': valor_realizado,
        'negociacoes_realizadas': total_negociacoes,
        'bancos_acionados': total_bancos,
        'pct_valor': _safe_pct(valor_realizado, valor_planejado),
        'pct_bancos': pct_bancos,
        'total_registros': len(registros),
    }


def _listar_registros_financeiro_contexto_ia(filtros: dict | None = None, limite: int = 500) -> list[dict]:
    filtros = filtros or {}
    query = FinanceiroBanco.query.filter(FinanceiroBanco.semana.in_(range(1, 13)))
    if filtros.get('banco'):
        query = query.filter(func.upper(FinanceiroBanco.banco) == filtros['banco'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(FinanceiroBanco.responsavel) == filtros['responsavel'])
    if filtros.get('tipo_negociacao'):
        query = query.filter(func.upper(FinanceiroBanco.tipo_negociacao) == filtros['tipo_negociacao'])
    if filtros.get('referencia'):
        query = query.filter(func.upper(FinanceiroBanco.referencia) == filtros['referencia'])

    registros = query.order_by(FinanceiroBanco.criado_em.desc()).limit(limite).all()
    return [registro.to_dict() for registro in registros]


def _montar_contexto_ia_financeiro(mes_slug: str, filtros: dict | None = None) -> dict:
    dados = _montar_relatorio_financeiro(mes_slug, filtros)
    return {
        'mes_atual': dados['mes_atual'],
        'filtros': dados['filtros'],
        'resumo_mensal': dados['resumo_mensal'],
        'destaques': dados['destaques'],
        'semanas': dados['semanas_mes'],
        'evolucao': dados['evolucao'],
        'total_bancos_base': len(BANCOS_BRASIL),
        'bancos_disponiveis': list(BANCOS_BRASIL),
        'registros_detalhados_periodo': _listar_registros_financeiro_contexto_ia(filtros),
        'resumo_sistema': _resumo_sistema_contexto_ia(),
    }


def _montar_relatorio_financeiro(mes_slug: str, filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    meses_map = {slug: {'slug': slug, 'nome': nome, 'inicio': inicio} for slug, nome, inicio in MESES_RELATORIO}
    meses_map[PERIODO_TRIMESTRAL[0]] = {'slug': PERIODO_TRIMESTRAL[0], 'nome': PERIODO_TRIMESTRAL[1], 'inicio': PERIODO_TRIMESTRAL[2]}
    mes_selecionado = meses_map.get(mes_slug, meses_map['abril'])
    semanas_mes = []
    evolucao = []
    acumulado_valor_planejado = 0.0
    acumulado_valor_realizado = 0.0
    acumulado_negociacoes = 0
    acumulado_bancos = 0

    for slug, nome, inicio in MESES_RELATORIO:
        for offset in range(4):
            semana = inicio + offset
            linha = _coletar_semana_financeiro(semana, filtros)
            linha.update({
                'mes_slug': slug,
                'mes_nome': nome,
                'semana_label': offset + 1,
            })
            acumulado_valor_planejado += linha['valor_planejado']
            acumulado_valor_realizado += linha['valor_realizado']
            acumulado_negociacoes += linha['negociacoes_realizadas']
            acumulado_bancos += linha['bancos_acionados']
            linha['acumulado_valor_planejado'] = acumulado_valor_planejado
            linha['acumulado_valor_realizado'] = acumulado_valor_realizado
            linha['acumulado_negociacoes'] = acumulado_negociacoes
            linha['acumulado_bancos'] = acumulado_bancos
            linha['pct_valor_acumulado'] = _safe_pct(acumulado_valor_realizado, acumulado_valor_planejado)
            linha['pct_bancos_acumulado'] = _safe_pct(acumulado_bancos, len(BANCOS_BRASIL) * max(len(evolucao) + 1, 1))
            evolucao.append(linha)
            if mes_selecionado['slug'] == PERIODO_TRIMESTRAL[0] or slug == mes_selecionado['slug']:
                semanas_mes.append(linha)

    resumo_mensal = {
        'valor_planejado': sum(item['valor_planejado'] for item in semanas_mes),
        'valor_realizado': sum(item['valor_realizado'] for item in semanas_mes),
        'negociacoes_realizadas': sum(item['negociacoes_realizadas'] for item in semanas_mes),
        'bancos_acionados': sum(item['bancos_acionados'] for item in semanas_mes),
    }
    resumo_mensal['pct_valor'] = _safe_pct(resumo_mensal['valor_realizado'], resumo_mensal['valor_planejado'])
    resumo_mensal['pct_bancos'] = _safe_pct(resumo_mensal['bancos_acionados'], len(BANCOS_BRASIL) * max(len(semanas_mes), 1))

    melhor_semana = max(semanas_mes, key=lambda item: (item['pct_valor'] + item['pct_bancos'])) if semanas_mes else None
    pior_semana = min(semanas_mes, key=lambda item: (item['pct_valor'] + item['pct_bancos'])) if semanas_mes else None
    destaques = {
        'melhor_semana': melhor_semana,
        'pior_semana': pior_semana,
        'gap_valor': max(resumo_mensal['valor_planejado'] - resumo_mensal['valor_realizado'], 0),
        'gap_bancos': max((len(BANCOS_BRASIL) * max(len(semanas_mes), 1)) - resumo_mensal['bancos_acionados'], 0),
    }

    chart_width = 720
    chart_height = 220
    left_pad = 20
    usable_width = chart_width - (left_pad * 2)
    usable_height = chart_height - 40
    total_points = max(len(semanas_mes) - 1, 1)

    valor_points = []
    bancos_points = []
    valor_markers = []
    bancos_markers = []
    chart_labels = []
    for idx, item in enumerate(semanas_mes):
        x = left_pad + (usable_width * idx / total_points)
        y_valor = 20 + (usable_height * (1 - min(item['pct_valor'], 100) / 100))
        y_bancos = 20 + (usable_height * (1 - min(item['pct_bancos'], 100) / 100))
        valor_points.append(f"{round(x, 1)},{round(y_valor, 1)}")
        bancos_points.append(f"{round(x, 1)},{round(y_bancos, 1)}")
        valor_markers.append({'x': round(x, 1), 'y': round(y_valor, 1)})
        bancos_markers.append({'x': round(x, 1), 'y': round(y_bancos, 1)})
        chart_labels.append({
            'x': round(x, 1),
            'label': f"{item['mes_nome']} S{item['semana_label']}" if mes_selecionado['slug'] == PERIODO_TRIMESTRAL[0] else f"S{item['semana_label']}",
        })

    chart = {
        'width': chart_width,
        'height': chart_height,
        'valor_points': " ".join(valor_points),
        'acoes_points': " ".join(bancos_points),
        'valor_area_points': f"20,180 {' '.join(valor_points)} {chart_width - 20},180",
        'acoes_area_points': f"20,180 {' '.join(bancos_points)} {chart_width - 20},180",
        'valor_markers': valor_markers,
        'acoes_markers': bancos_markers,
        'labels': chart_labels,
    }

    filtros_aplicados = {chave: valor for chave, valor in filtros.items() if valor}
    opcoes_filtro = {
        'bancos': _listar_opcoes_filtro(FinanceiroBanco.banco),
        'responsaveis': _listar_opcoes_filtro(FinanceiroBanco.responsavel),
        'tipos_negociacao': _listar_opcoes_filtro(FinanceiroBanco.tipo_negociacao),
        'referencias': _listar_opcoes_filtro(FinanceiroBanco.referencia),
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
        'total_bancos_base': len(BANCOS_BRASIL),
    }


def _normalizar_filtros_giro(args) -> dict:
    return {
        'origem': (args.get('origem') or '').strip().upper(),
        'responsavel': (args.get('responsavel') or '').strip().upper(),
        'tipo_negociacao': (args.get('tipo_negociacao') or '').strip().upper(),
        'referencia': (args.get('referencia') or '').strip().upper(),
    }


def _consultar_registros_giro_semana(semana: int, filtros: dict):
    query = GiroCaptacao.query.filter_by(semana=semana)
    if filtros.get('origem'):
        query = query.filter(func.upper(GiroCaptacao.origem) == filtros['origem'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(GiroCaptacao.responsavel) == filtros['responsavel'])
    if filtros.get('tipo_negociacao'):
        query = query.filter(func.upper(GiroCaptacao.tipo_negociacao) == filtros['tipo_negociacao'])
    if filtros.get('referencia'):
        query = query.filter(func.upper(GiroCaptacao.referencia) == filtros['referencia'])
    return query.order_by(GiroCaptacao.criado_em.desc()).all()


def _coletar_semana_giro(semana: int, filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    meta = MetaGiroSemana.query.filter_by(semana=semana).first()
    registros = _consultar_registros_giro_semana(semana, filtros)
    valor_planejado = float(meta.valor_meta) if meta else 0.0
    valor_realizado = sum(float(r.valor_captado or 0) for r in registros)
    total_captacoes = len(registros)
    total_origens = len({(r.origem or '').strip() for r in registros if (r.origem or '').strip()})
    pct_origens = _safe_pct(total_origens, len(ORIGENS_GIRO))
    return {
        'semana': semana,
        'valor_planejado': valor_planejado,
        'valor_realizado': valor_realizado,
        'captacoes_realizadas': total_captacoes,
        'origens_acionadas': total_origens,
        'pct_valor': _safe_pct(valor_realizado, valor_planejado),
        'pct_origens': pct_origens,
        'total_registros': len(registros),
    }


def _listar_registros_giro_contexto_ia(filtros: dict | None = None, limite: int = 500) -> list[dict]:
    filtros = filtros or {}
    query = GiroCaptacao.query.filter(GiroCaptacao.semana.in_(range(1, 13)))
    if filtros.get('origem'):
        query = query.filter(func.upper(GiroCaptacao.origem) == filtros['origem'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(GiroCaptacao.responsavel) == filtros['responsavel'])
    if filtros.get('tipo_negociacao'):
        query = query.filter(func.upper(GiroCaptacao.tipo_negociacao) == filtros['tipo_negociacao'])
    if filtros.get('referencia'):
        query = query.filter(func.upper(GiroCaptacao.referencia) == filtros['referencia'])

    registros = query.order_by(GiroCaptacao.criado_em.desc()).limit(limite).all()
    return [registro.to_dict() for registro in registros]


def _montar_contexto_ia_giro(mes_slug: str, filtros: dict | None = None) -> dict:
    dados = _montar_relatorio_giro(mes_slug, filtros)
    return {
        'mes_atual': dados['mes_atual'],
        'filtros': dados['filtros'],
        'resumo_mensal': dados['resumo_mensal'],
        'destaques': dados['destaques'],
        'semanas': dados['semanas_mes'],
        'evolucao': dados['evolucao'],
        'total_origens_base': len(ORIGENS_GIRO),
        'origens_disponiveis': list(ORIGENS_GIRO),
        'registros_detalhados_periodo': _listar_registros_giro_contexto_ia(filtros),
        'resumo_sistema': _resumo_sistema_contexto_ia(),
    }


def _montar_relatorio_giro(mes_slug: str, filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    meses_map = {slug: {'slug': slug, 'nome': nome, 'inicio': inicio} for slug, nome, inicio in MESES_RELATORIO}
    meses_map[PERIODO_TRIMESTRAL[0]] = {'slug': PERIODO_TRIMESTRAL[0], 'nome': PERIODO_TRIMESTRAL[1], 'inicio': PERIODO_TRIMESTRAL[2]}
    mes_selecionado = meses_map.get(mes_slug, meses_map['abril'])
    semanas_mes = []
    evolucao = []
    acumulado_valor_planejado = 0.0
    acumulado_valor_realizado = 0.0
    acumulado_captacoes = 0
    acumulado_origens = 0

    for slug, nome, inicio in MESES_RELATORIO:
        for offset in range(4):
            semana = inicio + offset
            linha = _coletar_semana_giro(semana, filtros)
            linha.update({
                'mes_slug': slug,
                'mes_nome': nome,
                'semana_label': offset + 1,
            })
            acumulado_valor_planejado += linha['valor_planejado']
            acumulado_valor_realizado += linha['valor_realizado']
            acumulado_captacoes += linha['captacoes_realizadas']
            acumulado_origens += linha['origens_acionadas']
            linha['acumulado_valor_planejado'] = acumulado_valor_planejado
            linha['acumulado_valor_realizado'] = acumulado_valor_realizado
            linha['acumulado_captacoes'] = acumulado_captacoes
            linha['acumulado_origens'] = acumulado_origens
            linha['pct_valor_acumulado'] = _safe_pct(acumulado_valor_realizado, acumulado_valor_planejado)
            linha['pct_origens_acumulado'] = _safe_pct(acumulado_origens, len(ORIGENS_GIRO) * max(len(evolucao) + 1, 1))
            evolucao.append(linha)
            if mes_selecionado['slug'] == PERIODO_TRIMESTRAL[0] or slug == mes_selecionado['slug']:
                semanas_mes.append(linha)

    resumo_mensal = {
        'valor_planejado': sum(item['valor_planejado'] for item in semanas_mes),
        'valor_realizado': sum(item['valor_realizado'] for item in semanas_mes),
        'captacoes_realizadas': sum(item['captacoes_realizadas'] for item in semanas_mes),
        'origens_acionadas': sum(item['origens_acionadas'] for item in semanas_mes),
    }
    resumo_mensal['pct_valor'] = _safe_pct(resumo_mensal['valor_realizado'], resumo_mensal['valor_planejado'])
    resumo_mensal['pct_origens'] = _safe_pct(resumo_mensal['origens_acionadas'], len(ORIGENS_GIRO) * max(len(semanas_mes), 1))

    melhor_semana = max(semanas_mes, key=lambda item: (item['pct_valor'] + item['pct_origens'])) if semanas_mes else None
    pior_semana = min(semanas_mes, key=lambda item: (item['pct_valor'] + item['pct_origens'])) if semanas_mes else None
    destaques = {
        'melhor_semana': melhor_semana,
        'pior_semana': pior_semana,
        'gap_valor': max(resumo_mensal['valor_planejado'] - resumo_mensal['valor_realizado'], 0),
        'gap_origens': max((len(ORIGENS_GIRO) * max(len(semanas_mes), 1)) - resumo_mensal['origens_acionadas'], 0),
    }

    chart_width = 720
    chart_height = 220
    left_pad = 20
    usable_width = chart_width - (left_pad * 2)
    usable_height = chart_height - 40
    total_points = max(len(semanas_mes) - 1, 1)

    valor_points = []
    origens_points = []
    valor_markers = []
    origens_markers = []
    chart_labels = []
    for idx, item in enumerate(semanas_mes):
        x = left_pad + (usable_width * idx / total_points)
        y_valor = 20 + (usable_height * (1 - min(item['pct_valor'], 100) / 100))
        y_origens = 20 + (usable_height * (1 - min(item['pct_origens'], 100) / 100))
        valor_points.append(f"{round(x, 1)},{round(y_valor, 1)}")
        origens_points.append(f"{round(x, 1)},{round(y_origens, 1)}")
        valor_markers.append({'x': round(x, 1), 'y': round(y_valor, 1)})
        origens_markers.append({'x': round(x, 1), 'y': round(y_origens, 1)})
        chart_labels.append({
            'x': round(x, 1),
            'label': f"{item['mes_nome']} S{item['semana_label']}" if mes_selecionado['slug'] == PERIODO_TRIMESTRAL[0] else f"S{item['semana_label']}",
        })

    chart = {
        'width': chart_width,
        'height': chart_height,
        'valor_points': " ".join(valor_points),
        'acoes_points': " ".join(origens_points),
        'valor_area_points': f"20,180 {' '.join(valor_points)} {chart_width - 20},180",
        'acoes_area_points': f"20,180 {' '.join(origens_points)} {chart_width - 20},180",
        'valor_markers': valor_markers,
        'acoes_markers': origens_markers,
        'labels': chart_labels,
    }

    filtros_aplicados = {chave: valor for chave, valor in filtros.items() if valor}
    opcoes_filtro = {
        'origens': _listar_opcoes_filtro(GiroCaptacao.origem),
        'responsaveis': _listar_opcoes_filtro(GiroCaptacao.responsavel),
        'tipos_negociacao': _listar_opcoes_filtro(GiroCaptacao.tipo_negociacao),
        'referencias': _listar_opcoes_filtro(GiroCaptacao.referencia),
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
        'total_origens_base': len(ORIGENS_GIRO),
    }


def _normalizar_filtros_medicao(args) -> dict:
    return {
        'empreendimento': (args.get('empreendimento') or '').strip().upper(),
        'responsavel': (args.get('responsavel') or '').strip().upper(),
    }


def _consultar_registros_medicao_semana(semana: int, filtros: dict):
    query = MedicaoRegistro.query.filter_by(semana=semana)
    if filtros.get('empreendimento'):
        query = query.filter(func.upper(MedicaoRegistro.empreendimento) == filtros['empreendimento'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(MedicaoRegistro.responsavel) == filtros['responsavel'])
    return query.order_by(MedicaoRegistro.criado_em.desc()).all()


def _coletar_semana_medicao(semana: int, filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    meta = MetaMedicaoSemana.query.filter_by(semana=semana).first()
    registros = _consultar_registros_medicao_semana(semana, filtros)
    valor_planejado = float(meta.valor_meta) if meta else 0.0
    valor_realizado = sum(float(r.valor_medicao or 0) for r in registros)
    total_medicoes = len(registros)
    total_empreendimentos = len({(r.empreendimento or '').strip() for r in registros if (r.empreendimento or '').strip()})
    total_base = Empreendimento.query.filter_by(ativo=True).count()
    return {
        'semana': semana,
        'valor_planejado': valor_planejado,
        'valor_realizado': valor_realizado,
        'medicoes_realizadas': total_medicoes,
        'empreendimentos_lancados': total_empreendimentos,
        'pct_valor': _safe_pct(valor_realizado, valor_planejado),
        'pct_empreendimentos': _safe_pct(total_empreendimentos, total_base),
        'total_registros': len(registros),
    }


def _listar_registros_medicao_contexto_ia(filtros: dict | None = None, limite: int = 500) -> list[dict]:
    filtros = filtros or {}
    query = MedicaoRegistro.query.filter(MedicaoRegistro.semana.in_(range(1, 13)))
    if filtros.get('empreendimento'):
        query = query.filter(func.upper(MedicaoRegistro.empreendimento) == filtros['empreendimento'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(MedicaoRegistro.responsavel) == filtros['responsavel'])

    registros = query.order_by(MedicaoRegistro.criado_em.desc()).limit(limite).all()
    return [registro.to_dict() for registro in registros]


def _montar_contexto_ia_medicao(mes_slug: str, filtros: dict | None = None) -> dict:
    dados = _montar_relatorio_medicao(mes_slug, filtros)
    return {
        'mes_atual': dados['mes_atual'],
        'filtros': dados['filtros'],
        'resumo_mensal': dados['resumo_mensal'],
        'destaques': dados['destaques'],
        'semanas': dados['semanas_mes'],
        'evolucao': dados['evolucao'],
        'total_empreendimentos_base': dados['total_empreendimentos_base'],
        'empreendimentos_disponiveis': [item.nome for item in Empreendimento.query.filter_by(ativo=True).order_by(Empreendimento.nome).all()],
        'registros_detalhados_periodo': _listar_registros_medicao_contexto_ia(filtros),
        'resumo_sistema': _resumo_sistema_contexto_ia(),
    }


def _montar_relatorio_medicao(mes_slug: str, filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    meses_map = {slug: {'slug': slug, 'nome': nome, 'inicio': inicio} for slug, nome, inicio in MESES_RELATORIO}
    meses_map[PERIODO_TRIMESTRAL[0]] = {'slug': PERIODO_TRIMESTRAL[0], 'nome': PERIODO_TRIMESTRAL[1], 'inicio': PERIODO_TRIMESTRAL[2]}
    mes_selecionado = meses_map.get(mes_slug, meses_map['abril'])
    semanas_mes = []
    evolucao = []
    acumulado_valor_planejado = 0.0
    acumulado_valor_realizado = 0.0
    acumulado_medicoes = 0
    acumulado_empreendimentos = 0
    total_empreendimentos_base = Empreendimento.query.filter_by(ativo=True).count()

    for slug, nome, inicio in MESES_RELATORIO:
        for offset in range(4):
            semana = inicio + offset
            linha = _coletar_semana_medicao(semana, filtros)
            linha.update({
                'mes_slug': slug,
                'mes_nome': nome,
                'semana_label': offset + 1,
            })
            acumulado_valor_planejado += linha['valor_planejado']
            acumulado_valor_realizado += linha['valor_realizado']
            acumulado_medicoes += linha['medicoes_realizadas']
            acumulado_empreendimentos += linha['empreendimentos_lancados']
            linha['acumulado_valor_planejado'] = acumulado_valor_planejado
            linha['acumulado_valor_realizado'] = acumulado_valor_realizado
            linha['acumulado_medicoes'] = acumulado_medicoes
            linha['acumulado_empreendimentos'] = acumulado_empreendimentos
            linha['pct_valor_acumulado'] = _safe_pct(acumulado_valor_realizado, acumulado_valor_planejado)
            linha['pct_empreendimentos_acumulado'] = _safe_pct(
                acumulado_empreendimentos,
                total_empreendimentos_base * max(len(evolucao) + 1, 1),
            )
            evolucao.append(linha)
            if mes_selecionado['slug'] == PERIODO_TRIMESTRAL[0] or slug == mes_selecionado['slug']:
                semanas_mes.append(linha)

    resumo_mensal = {
        'valor_planejado': sum(item['valor_planejado'] for item in semanas_mes),
        'valor_realizado': sum(item['valor_realizado'] for item in semanas_mes),
        'medicoes_realizadas': sum(item['medicoes_realizadas'] for item in semanas_mes),
        'empreendimentos_lancados': sum(item['empreendimentos_lancados'] for item in semanas_mes),
    }
    resumo_mensal['pct_valor'] = _safe_pct(resumo_mensal['valor_realizado'], resumo_mensal['valor_planejado'])
    resumo_mensal['pct_empreendimentos'] = _safe_pct(
        resumo_mensal['empreendimentos_lancados'],
        total_empreendimentos_base * max(len(semanas_mes), 1),
    )

    melhor_semana = max(semanas_mes, key=lambda item: (item['pct_valor'] + item['pct_empreendimentos'])) if semanas_mes else None
    pior_semana = min(semanas_mes, key=lambda item: (item['pct_valor'] + item['pct_empreendimentos'])) if semanas_mes else None
    destaques = {
        'melhor_semana': melhor_semana,
        'pior_semana': pior_semana,
        'gap_valor': max(resumo_mensal['valor_planejado'] - resumo_mensal['valor_realizado'], 0),
        'gap_empreendimentos': max((total_empreendimentos_base * max(len(semanas_mes), 1)) - resumo_mensal['empreendimentos_lancados'], 0),
    }

    chart_width = 720
    chart_height = 220
    left_pad = 20
    usable_width = chart_width - (left_pad * 2)
    usable_height = chart_height - 40
    total_points = max(len(semanas_mes) - 1, 1)

    valor_points = []
    empreendimentos_points = []
    valor_markers = []
    empreendimentos_markers = []
    chart_labels = []
    for idx, item in enumerate(semanas_mes):
        x = left_pad + (usable_width * idx / total_points)
        y_valor = 20 + (usable_height * (1 - min(item['pct_valor'], 100) / 100))
        y_empreendimentos = 20 + (usable_height * (1 - min(item['pct_empreendimentos'], 100) / 100))
        valor_points.append(f"{round(x, 1)},{round(y_valor, 1)}")
        empreendimentos_points.append(f"{round(x, 1)},{round(y_empreendimentos, 1)}")
        valor_markers.append({'x': round(x, 1), 'y': round(y_valor, 1)})
        empreendimentos_markers.append({'x': round(x, 1), 'y': round(y_empreendimentos, 1)})
        chart_labels.append({
            'x': round(x, 1),
            'label': f"{item['mes_nome']} S{item['semana_label']}" if mes_selecionado['slug'] == PERIODO_TRIMESTRAL[0] else f"S{item['semana_label']}",
        })

    chart = {
        'width': chart_width,
        'height': chart_height,
        'valor_points': " ".join(valor_points),
        'acoes_points': " ".join(empreendimentos_points),
        'valor_area_points': f"20,180 {' '.join(valor_points)} {chart_width - 20},180",
        'acoes_area_points': f"20,180 {' '.join(empreendimentos_points)} {chart_width - 20},180",
        'valor_markers': valor_markers,
        'acoes_markers': empreendimentos_markers,
        'labels': chart_labels,
    }

    filtros_aplicados = {chave: valor for chave, valor in filtros.items() if valor}
    opcoes_filtro = {
        'empreendimentos': _listar_opcoes_filtro(MedicaoRegistro.empreendimento),
        'responsaveis': _listar_opcoes_filtro(MedicaoRegistro.responsavel),
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
        'total_empreendimentos_base': total_empreendimentos_base,
    }


def _situacao_fornecedor_conta_como_sim(situacao: str | None) -> bool:
    return (situacao or '').upper().strip() in {'SIM (INTEGRAL)', 'SIM (PARCIAL)'}


def _normalizar_filtros_fornecedores(args) -> dict:
    return {
        'empreendimento': (args.get('empreendimento') or '').strip().upper(),
        'fornecedor': (args.get('fornecedor') or '').strip().upper(),
        'servico_prestado': (args.get('servico_prestado') or '').strip().upper(),
        'situacao': (args.get('situacao') or '').strip().upper(),
        'responsavel': (args.get('responsavel') or '').strip().upper(),
    }


def _consultar_registros_fornecedores_semana(semana: int, filtros: dict):
    query = FornecedorRegistro.query.filter_by(semana=semana)
    if filtros.get('empreendimento'):
        query = query.filter(func.upper(FornecedorRegistro.empreendimento) == filtros['empreendimento'])
    if filtros.get('fornecedor'):
        query = query.filter(func.upper(FornecedorRegistro.nome_fornecedor) == filtros['fornecedor'])
    if filtros.get('servico_prestado'):
        query = query.filter(func.upper(FornecedorRegistro.servico_prestado) == filtros['servico_prestado'])
    if filtros.get('situacao'):
        query = query.filter(func.upper(FornecedorRegistro.situacao) == filtros['situacao'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(FornecedorRegistro.responsavel) == filtros['responsavel'])
    return query.order_by(FornecedorRegistro.criado_em.desc()).all()


def _coletar_semana_fornecedores(semana: int, filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    meta = MetaFornecedorSemana.query.filter_by(semana=semana).first()
    registros = _consultar_registros_fornecedores_semana(semana, filtros)
    valor_planejado = float(meta.valor_meta) if meta else 0.0
    valor_realizado = sum(float(r.valor_negociado or 0) for r in registros if _situacao_fornecedor_conta_como_sim(r.situacao))
    total_negociacoes = sum(1 for r in registros if _situacao_fornecedor_conta_como_sim(r.situacao))
    total_fornecedores = len({(r.nome_fornecedor or '').strip() for r in registros if (r.nome_fornecedor or '').strip()})
    total_empreendimentos = len({(r.empreendimento or '').strip() for r in registros if (r.empreendimento or '').strip()})
    total_empreendimentos_base = Empreendimento.query.filter_by(ativo=True).count()
    return {
        'semana': semana,
        'valor_planejado': valor_planejado,
        'valor_realizado': valor_realizado,
        'negociacoes_realizadas': total_negociacoes,
        'fornecedores_acionados': total_fornecedores,
        'empreendimentos_acionados': total_empreendimentos,
        'pct_valor': _safe_pct(valor_realizado, valor_planejado),
        'pct_empreendimentos': _safe_pct(total_empreendimentos, total_empreendimentos_base),
        'total_registros': len(registros),
    }


def _listar_registros_fornecedores_contexto_ia(filtros: dict | None = None, limite: int = 500) -> list[dict]:
    filtros = filtros or {}
    query = FornecedorRegistro.query.filter(FornecedorRegistro.semana.in_(range(1, 13)))
    if filtros.get('empreendimento'):
        query = query.filter(func.upper(FornecedorRegistro.empreendimento) == filtros['empreendimento'])
    if filtros.get('fornecedor'):
        query = query.filter(func.upper(FornecedorRegistro.nome_fornecedor) == filtros['fornecedor'])
    if filtros.get('servico_prestado'):
        query = query.filter(func.upper(FornecedorRegistro.servico_prestado) == filtros['servico_prestado'])
    if filtros.get('situacao'):
        query = query.filter(func.upper(FornecedorRegistro.situacao) == filtros['situacao'])
    if filtros.get('responsavel'):
        query = query.filter(func.upper(FornecedorRegistro.responsavel) == filtros['responsavel'])

    registros = query.order_by(FornecedorRegistro.criado_em.desc()).limit(limite).all()
    return [registro.to_dict() for registro in registros]


def _montar_contexto_ia_fornecedores(mes_slug: str, filtros: dict | None = None) -> dict:
    dados = _montar_relatorio_fornecedores(mes_slug, filtros)
    return {
        'mes_atual': dados['mes_atual'],
        'filtros': dados['filtros'],
        'resumo_mensal': dados['resumo_mensal'],
        'destaques': dados['destaques'],
        'semanas': dados['semanas_mes'],
        'evolucao': dados['evolucao'],
        'total_empreendimentos_base': dados['total_empreendimentos_base'],
        'situacoes_disponiveis': list(SITUACAO_FORNECEDOR_OPCOES),
        'registros_detalhados_periodo': _listar_registros_fornecedores_contexto_ia(filtros),
        'resumo_sistema': _resumo_sistema_contexto_ia(),
    }


def _montar_relatorio_fornecedores(mes_slug: str, filtros: dict | None = None) -> dict:
    filtros = filtros or {}
    meses_map = {slug: {'slug': slug, 'nome': nome, 'inicio': inicio} for slug, nome, inicio in MESES_RELATORIO}
    meses_map[PERIODO_TRIMESTRAL[0]] = {'slug': PERIODO_TRIMESTRAL[0], 'nome': PERIODO_TRIMESTRAL[1], 'inicio': PERIODO_TRIMESTRAL[2]}
    mes_selecionado = meses_map.get(mes_slug, meses_map['abril'])
    semanas_mes = []
    evolucao = []
    acumulado_valor_planejado = 0.0
    acumulado_valor_realizado = 0.0
    acumulado_negociacoes = 0
    acumulado_empreendimentos = 0
    total_empreendimentos_base = Empreendimento.query.filter_by(ativo=True).count()

    for slug, nome, inicio in MESES_RELATORIO:
        for offset in range(4):
            semana = inicio + offset
            linha = _coletar_semana_fornecedores(semana, filtros)
            linha.update({'mes_slug': slug, 'mes_nome': nome, 'semana_label': offset + 1})
            acumulado_valor_planejado += linha['valor_planejado']
            acumulado_valor_realizado += linha['valor_realizado']
            acumulado_negociacoes += linha['negociacoes_realizadas']
            acumulado_empreendimentos += linha['empreendimentos_acionados']
            linha['acumulado_valor_planejado'] = acumulado_valor_planejado
            linha['acumulado_valor_realizado'] = acumulado_valor_realizado
            linha['acumulado_negociacoes'] = acumulado_negociacoes
            linha['acumulado_empreendimentos'] = acumulado_empreendimentos
            linha['pct_valor_acumulado'] = _safe_pct(acumulado_valor_realizado, acumulado_valor_planejado)
            linha['pct_empreendimentos_acumulado'] = _safe_pct(acumulado_empreendimentos, total_empreendimentos_base * max(len(evolucao) + 1, 1))
            evolucao.append(linha)
            if mes_selecionado['slug'] == PERIODO_TRIMESTRAL[0] or slug == mes_selecionado['slug']:
                semanas_mes.append(linha)

    resumo_mensal = {
        'valor_planejado': sum(item['valor_planejado'] for item in semanas_mes),
        'valor_realizado': sum(item['valor_realizado'] for item in semanas_mes),
        'negociacoes_realizadas': sum(item['negociacoes_realizadas'] for item in semanas_mes),
        'fornecedores_acionados': sum(item['fornecedores_acionados'] for item in semanas_mes),
        'empreendimentos_acionados': sum(item['empreendimentos_acionados'] for item in semanas_mes),
    }
    resumo_mensal['pct_valor'] = _safe_pct(resumo_mensal['valor_realizado'], resumo_mensal['valor_planejado'])
    resumo_mensal['pct_empreendimentos'] = _safe_pct(resumo_mensal['empreendimentos_acionados'], total_empreendimentos_base * max(len(semanas_mes), 1))

    melhor_semana = max(semanas_mes, key=lambda item: (item['pct_valor'] + item['pct_empreendimentos'])) if semanas_mes else None
    pior_semana = min(semanas_mes, key=lambda item: (item['pct_valor'] + item['pct_empreendimentos'])) if semanas_mes else None
    destaques = {
        'melhor_semana': melhor_semana,
        'pior_semana': pior_semana,
        'gap_valor': max(resumo_mensal['valor_planejado'] - resumo_mensal['valor_realizado'], 0),
        'gap_empreendimentos': max((total_empreendimentos_base * max(len(semanas_mes), 1)) - resumo_mensal['empreendimentos_acionados'], 0),
    }

    chart_width = 720
    chart_height = 220
    left_pad = 20
    usable_width = chart_width - (left_pad * 2)
    usable_height = chart_height - 40
    total_points = max(len(semanas_mes) - 1, 1)
    valor_points = []
    empreendimentos_points = []
    valor_markers = []
    empreendimentos_markers = []
    chart_labels = []
    for idx, item in enumerate(semanas_mes):
        x = left_pad + (usable_width * idx / total_points)
        y_valor = 20 + (usable_height * (1 - min(item['pct_valor'], 100) / 100))
        y_empreendimentos = 20 + (usable_height * (1 - min(item['pct_empreendimentos'], 100) / 100))
        valor_points.append(f"{round(x, 1)},{round(y_valor, 1)}")
        empreendimentos_points.append(f"{round(x, 1)},{round(y_empreendimentos, 1)}")
        valor_markers.append({'x': round(x, 1), 'y': round(y_valor, 1)})
        empreendimentos_markers.append({'x': round(x, 1), 'y': round(y_empreendimentos, 1)})
        chart_labels.append({'x': round(x, 1), 'label': f"{item['mes_nome']} S{item['semana_label']}" if mes_selecionado['slug'] == PERIODO_TRIMESTRAL[0] else f"S{item['semana_label']}"})

    chart = {
        'width': chart_width,
        'height': chart_height,
        'valor_points': " ".join(valor_points),
        'acoes_points': " ".join(empreendimentos_points),
        'valor_area_points': f"20,180 {' '.join(valor_points)} {chart_width - 20},180",
        'acoes_area_points': f"20,180 {' '.join(empreendimentos_points)} {chart_width - 20},180",
        'valor_markers': valor_markers,
        'acoes_markers': empreendimentos_markers,
        'labels': chart_labels,
    }

    filtros_aplicados = {chave: valor for chave, valor in filtros.items() if valor}
    opcoes_filtro = {
        'empreendimentos': _listar_opcoes_filtro(FornecedorRegistro.empreendimento),
        'fornecedores': _listar_opcoes_filtro(FornecedorRegistro.nome_fornecedor),
        'servicos': _listar_opcoes_filtro(FornecedorRegistro.servico_prestado),
        'situacoes': _listar_opcoes_filtro(FornecedorRegistro.situacao),
        'responsaveis': _listar_opcoes_filtro(FornecedorRegistro.responsavel),
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
        'total_empreendimentos_base': total_empreendimentos_base,
    }


def _formatar_tempo_restante(total_segundos: int) -> str:
    if total_segundos <= 0:
        return 'Prazo encerrado'
    dias, resto = divmod(total_segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos, _ = divmod(resto, 60)
    return f'{dias}d {horas:02d}h {minutos:02d}min'


def _montar_master_painel() -> dict:
    resumo_inadimplencia = _montar_relatorio_relacionamento('resumo_trimestral')
    resumo_vendas = montar_contexto_template_vendas('resumo_trimestral', incluir_resumo=True)
    resumo_investidores = montar_contexto_template_investidores('resumo_trimestral', incluir_resumo=True)
    resumo_bancos = resumir_financeiro_bancos_trimestre()
    resumo_giro = resumir_giro_trimestre()
    resumo_fornecedores = resumir_fornecedores_trimestre()
    resumo_medicao = resumir_medicao_trimestre()

    cards = [
        {
            'slug': 'venda_varejo',
            'nome': 'Venda Varejo',
            'realizado': float(resumo_vendas['financeiro']['total_vendidas']),
            'meta': float(resumo_vendas['financeiro']['meta_quantidade']),
            'percentual': float(resumo_vendas['financeiro']['percentual_atingimento']),
            'descricao': 'Total vendido frente ? meta trimestral cadastrada no admin.',
            'comparativo_label': 'vendas realizadas x vendas planejadas',
            'ficticio': False,
            'monetario': False,
        },
        {
            'slug': 'giro',
            'nome': 'Capital de giro',
            'realizado': float(resumo_giro['valor_realizado']),
            'meta': float(resumo_giro['valor_meta']),
            'percentual': float(resumo_giro['percentual_atingimento']),
            'descricao': 'Valor captado para reforco de caixa frente a meta semanal cadastrada no admin.',
            'comparativo_label': 'valor captado x meta de capital de giro',
            'ficticio': False,
            'monetario': True,
        },
        {
            'slug': 'medicao',
            'nome': 'Medição de obras',
            'realizado': float(resumo_medicao['valor_realizado']),
            'meta': float(resumo_medicao['valor_meta']),
            'percentual': float(resumo_medicao['percentual_atingimento']),
            'descricao': 'Valor de medicao lancado frente a meta semanal cadastrada no admin.',
            'comparativo_label': 'valor de medição x meta de medição de obras',
            'ficticio': False,
            'monetario': True,
        },
        {
            'slug': 'fornecedores',
            'nome': 'Renegociação Fornecedores',
            'realizado': float(resumo_fornecedores['valor_realizado']),
            'meta': float(resumo_fornecedores['valor_meta']),
            'percentual': float(resumo_fornecedores['percentual_atingimento']),
            'descricao': 'Valor negociado com fornecedores frente a meta semanal cadastrada no admin.',
            'comparativo_label': 'valor negociado x meta de renegociação de fornecedores',
            'ficticio': False,
            'monetario': True,
        },
        {
            'slug': 'investidor',
            'nome': 'Investidor',
            'realizado': float(resumo_investidores['financeiro']['valor_realizado']),
            'meta': float(resumo_investidores['financeiro']['meta_valor']),
            'percentual': float(resumo_investidores['financeiro']['percentual_atingimento']),
            'descricao': 'Valor realizado de investidores frente ? meta de valor cadastrada no admin.',
            'comparativo_label': 'valor realizado x meta de investidores',
            'ficticio': False,
            'monetario': True,
        },
    ]

    cards.extend([
        {
            'slug': slug,
            'nome': nome,
            'realizado': realizado,
            'meta': meta,
            'percentual': _safe_pct(realizado, meta),
            'descricao': descricao,
            'comparativo_label': 'realizado x planejado',
            'ficticio': True,
            'monetario': False,
        }
        for slug, nome, realizado, meta, descricao in MASTER_METRICAS_FICTICIAS
        if slug != 'fornecedores'
    ])

    cards.append({
        'slug': 'bancos',
        'nome': 'Renegociação Bancária',
        'realizado': float(resumo_bancos['valor_realizado']),
        'meta': float(resumo_bancos['valor_meta']),
        'percentual': float(resumo_bancos['percentual_atingimento']),
        'descricao': 'Valor arrecadado em renegociações bancárias frente a meta semanal cadastrada no admin.',
        'comparativo_label': 'valor arrecadado x meta de renegociação bancária',
        'ficticio': False,
        'monetario': True,
    })

    cards.append({
        'slug': 'inadimplencia',
        'nome': 'Inadimplencia',
        'realizado': float(resumo_inadimplencia['resumo_mensal']['valor_realizado']),
        'meta': float(resumo_inadimplencia['resumo_mensal']['valor_planejado']),
        'percentual': float(resumo_inadimplencia['resumo_mensal']['pct_valor']),
        'descricao': 'Valor realizado frente ao valor planejado do trimestre.',
        'comparativo_label': 'valor realizado x valor planejado',
        'ficticio': False,
        'monetario': True,
    })

    cards_acoes = [
        {'slug': 'venda_varejo', 'nome': 'Ações Venda Varejo', 'realizado': float(resumo_vendas['financeiro'].get('acoes_realizadas', 0)), 'meta': float(resumo_vendas['financeiro'].get('meta_acoes', 0)), 'percentual': float(resumo_vendas['financeiro'].get('percentual_acoes', 0)), 'descricao': 'Ações comerciais executadas frente à meta de ações do trimestre.', 'comparativo_label': 'ações realizadas x meta de ações', 'ficticio': False, 'monetario': False},
        {'slug': 'giro', 'nome': 'Ações Capital de giro', 'realizado': float(resumo_giro.get('acoes_realizadas', 0)), 'meta': float(resumo_giro.get('acoes_planejadas', 0)), 'percentual': float(resumo_giro.get('percentual_acoes', 0)), 'descricao': 'Ações de capital de giro executadas frente à meta do trimestre.', 'comparativo_label': 'ações realizadas x meta de ações', 'ficticio': False, 'monetario': False},
        {'slug': 'inadimplencia', 'nome': 'Ações Inadimplencia', 'realizado': float(resumo_inadimplencia['resumo_mensal'].get('acoes_realizadas', 0)), 'meta': float(resumo_inadimplencia['resumo_mensal'].get('acoes_planejadas', 0)), 'percentual': float(resumo_inadimplencia['resumo_mensal'].get('pct_acoes', 0)), 'descricao': 'Ações de inadimplência executadas frente à meta do trimestre.', 'comparativo_label': 'ações realizadas x meta de ações', 'ficticio': False, 'monetario': False},
        {'slug': 'medicao', 'nome': 'Ações Medição de obras', 'realizado': float(resumo_medicao.get('acoes_realizadas', 0)), 'meta': float(resumo_medicao.get('acoes_planejadas', 0)), 'percentual': float(resumo_medicao.get('percentual_acoes', 0)), 'descricao': 'Ações de medição executadas frente à meta do trimestre.', 'comparativo_label': 'ações realizadas x meta de ações', 'ficticio': False, 'monetario': False},
        {'slug': 'investidor', 'nome': 'Ações Investidores', 'realizado': float(resumo_investidores['financeiro'].get('acoes_realizadas', 0)), 'meta': float(resumo_investidores['financeiro'].get('meta_acoes', 0)), 'percentual': float(resumo_investidores['financeiro'].get('percentual_acoes', 0)), 'descricao': 'Ações de investidores executadas frente à meta do trimestre.', 'comparativo_label': 'ações realizadas x meta de ações', 'ficticio': False, 'monetario': False},
        {'slug': 'fornecedores', 'nome': 'Ações Renegociação Fornecedores', 'realizado': float(resumo_fornecedores.get('acoes_realizadas', 0)), 'meta': float(resumo_fornecedores.get('acoes_planejadas', 0)), 'percentual': float(resumo_fornecedores.get('percentual_acoes', 0)), 'descricao': 'Ações com fornecedores executadas frente à meta do trimestre.', 'comparativo_label': 'ações realizadas x meta de ações', 'ficticio': False, 'monetario': False},
        {'slug': 'bancos', 'nome': 'Ações Renegociação Bancária', 'realizado': float(resumo_bancos.get('acoes_realizadas', 0)), 'meta': float(resumo_bancos.get('acoes_planejadas', 0)), 'percentual': float(resumo_bancos.get('percentual_acoes', 0)), 'descricao': 'Ações bancárias executadas frente à meta do trimestre.', 'comparativo_label': 'ações realizadas x meta de ações', 'ficticio': False, 'monetario': False},
    ]

    cards_ordenados = sorted(cards, key=lambda item: (
        ['venda_varejo', 'giro', 'inadimplencia', 'medicao', 'investidor', 'fornecedores', 'bancos'].index(item['slug'])
    ))
    cards_acoes_ordenados = sorted(cards_acoes, key=lambda item: (
        ['venda_varejo', 'giro', 'inadimplencia', 'medicao', 'investidor', 'fornecedores', 'bancos'].index(item['slug'])
    ))
    for card in cards_ordenados:
        percentual = float(card.get('percentual', 0))
        card['desempenho_status'] = 'positivo' if percentual >= 100 else ('negativo' if percentual < 60 else 'neutro')
    for card in cards_acoes_ordenados:
        percentual = float(card.get('percentual', 0))
        card['desempenho_status'] = 'positivo' if percentual >= 100 else ('negativo' if percentual < 60 else 'neutro')

    total_realizado = sum(min(float(item['percentual']), 100.0) for item in cards_ordenados)
    total_meta = float(len(cards_ordenados) * 100)
    objetivo_geral = _safe_pct(total_realizado, total_meta)

    agora = datetime.now().replace(microsecond=0)
    inicio_contagem = MASTER_START_DATE
    fim_trimestre = MASTER_END_DATE
    duracao_total = max(int((fim_trimestre - inicio_contagem).total_seconds()), 1)
    tempo_decorrido = int((agora - inicio_contagem).total_seconds())
    tempo_decorrido = min(max(tempo_decorrido, 0), duracao_total)
    tempo_pct = round((tempo_decorrido / duracao_total) * 100, 1)

    destaque_principal = max(cards_ordenados, key=lambda item: item['percentual']) if cards_ordenados else None
    alerta_principal = min(cards_ordenados, key=lambda item: item['percentual']) if cards_ordenados else None

    return {
        'cards_master': cards_ordenados,
        'objetivo_geral': objetivo_geral,
        'objetivo_realizado_total': total_realizado,
        'objetivo_meta_total': total_meta,
        'tempo_pct': tempo_pct,
        'tempo_restante_label': _formatar_tempo_restante(tempo_decorrido),
        'data_limite_label': f'{inicio_contagem.strftime("%d/%m/%Y")} a {fim_trimestre.strftime("%d/%m/%Y")}',
        'timer_started_at_iso': inicio_contagem.isoformat(),
        'timer_deadline_at_iso': fim_trimestre.isoformat(),
        'destaque_principal': destaque_principal,
        'alerta_principal': alerta_principal,
        'analytics_ai_enabled': analytics_ai_enabled() and analytics_ai_available(),
    }


def _serializar_master_painel() -> dict:
    painel = _montar_master_painel()
    return {
        'cards_master': painel['cards_master'],
        'cards_master_acoes': painel['cards_master_acoes'],
        'objetivo_geral': painel['objetivo_geral'],
        'objetivo_realizado_total': painel['objetivo_realizado_total'],
        'objetivo_meta_total': painel['objetivo_meta_total'],
        'tempo_pct': painel['tempo_pct'],
        'tempo_restante_label': painel['tempo_restante_label'],
        'data_limite_label': painel['data_limite_label'],
        'timer_started_at_iso': painel['timer_started_at_iso'],
        'timer_deadline_at_iso': painel['timer_deadline_at_iso'],
        'destaque_principal': painel['destaque_principal'],
        'alerta_principal': painel['alerta_principal'],
    }


def _montar_contexto_ia_master() -> dict:
    painel = _montar_master_painel()
    return {
        'objetivo_geral': painel['objetivo_geral'],
        'tempo_pct': painel['tempo_pct'],
        'tempo_restante_label': painel['tempo_restante_label'],
        'data_limite_label': painel['data_limite_label'],
        'cards_master': [
            {
                'frente': card['nome'],
                'realizado': card['realizado'],
                'meta': card['meta'],
                'percentual': card['percentual'],
                'descricao': card['descricao'],
                'comparativo_label': card['comparativo_label'],
                'ficticio': card['ficticio'],
                'monetario': card['monetario'],
            }
            for card in painel['cards_master']
        ],
        'cards_master_acoes': [
            {
                'frente': card['nome'],
                'realizado': card['realizado'],
                'meta': card['meta'],
                'percentual': card['percentual'],
                'descricao': card['descricao'],
                'comparativo_label': card['comparativo_label'],
                'ficticio': card['ficticio'],
                'monetario': card['monetario'],
            }
            for card in painel['cards_master_acoes']
        ],
        'destaque_principal': painel['destaque_principal'],
        'alerta_principal': painel['alerta_principal'],
    }


def _resolver_master_periodo_v2(view: str | None = None, period: str | None = None) -> dict:
    view_normalizada = (view or 'trimestral').strip().lower()
    if view_normalizada not in {'semanal', 'mensal', 'trimestral'}:
        view_normalizada = 'trimestral'

    semanas_map = {item[0]: item for item in MASTER_SEMANAS}
    meses_map = {item[0]: item for item in MASTER_MESES}
    view_options = [
        {'slug': 'semanal', 'label': 'Semanas'},
        {'slug': 'mensal', 'label': 'Meses'},
        {'slug': 'trimestral', 'label': 'Trimestre'},
    ]

    if view_normalizada == 'semanal':
        selecionado = semanas_map.get((period or 's1').strip().lower(), MASTER_SEMANAS[0])
        return {
            'view': 'semanal',
            'period': selecionado[0],
            'label': selecionado[1],
            'semanas': [selecionado[2]],
            'started_at': selecionado[3],
            'deadline_at': selecionado[4],
            'view_options': view_options,
            'period_options': [{'slug': item[0], 'label': item[1]} for item in MASTER_SEMANAS],
        }

    if view_normalizada == 'mensal':
        selecionado = meses_map.get((period or 'abril').strip().lower(), MASTER_MESES[0])
        return {
            'view': 'mensal',
            'period': selecionado[0],
            'label': selecionado[1],
            'semanas': list(selecionado[2]),
            'started_at': selecionado[3],
            'deadline_at': selecionado[4],
            'view_options': view_options,
            'period_options': [{'slug': item[0], 'label': item[1]} for item in MASTER_MESES],
        }

    return {
        'view': 'trimestral',
        'period': 'resumo_trimestral',
        'label': 'Resumo Trimestral',
        'semanas': list(range(1, 13)),
        'started_at': MASTER_START_DATE,
        'deadline_at': MASTER_END_DATE,
        'view_options': view_options,
        'period_options': [{'slug': 'resumo_trimestral', 'label': 'Abril a Junho'}],
    }


def _master_mes_e_semana_local_v2(semana_global: int) -> tuple[str, int]:
    for slug, _nome, _numero, semana_inicio in MESES_VENDAS:
        if semana_inicio <= semana_global <= semana_inicio + 3:
            return slug, (semana_global - semana_inicio) + 1
    return 'abril', 1


def _resolver_periodo_painel(view: str | None, period: str | None, meses_base: list[tuple[str, str, int, int]]) -> dict:
    view_normalizada = (view or 'trimestral').strip().lower()
    if view_normalizada not in {'semanal', 'mensal', 'trimestral'}:
        view_normalizada = 'trimestral'

    view_options = [
        {'slug': 'trimestral', 'label': 'Trimestre'},
        {'slug': 'mensal', 'label': 'Meses'},
        {'slug': 'semanal', 'label': 'Semanas'},
    ]
    meses_map = {slug: {'slug': slug, 'label': nome, 'numero': numero, 'semana_inicio': semana_inicio} for slug, nome, numero, semana_inicio in meses_base}
    semanas_map = {}
    week_groups = []
    for slug, nome, _numero, semana_inicio in meses_base:
        semanas = []
        for offset in range(4):
            semana_global = semana_inicio + offset
            semana_slug = f's{semana_global}'
            semana = {
                'slug': semana_slug,
                'label': f'{nome} - Semana {offset + 1}',
                'short_label': f'S{offset + 1}',
                'mes_slug': slug,
                'semana_local': offset + 1,
            }
            semanas_map[semana_slug] = semana
            semanas.append(semana)
        week_groups.append({'slug': slug, 'label': nome, 'weeks': semanas})

    if view_normalizada == 'semanal':
        selecionado = semanas_map.get((period or 's1').strip().lower(), next(iter(semanas_map.values())))
        return {
            'view': 'semanal',
            'period': selecionado['slug'],
            'label': selecionado['label'],
            'mes_slug': selecionado['mes_slug'],
            'semana_local': selecionado['semana_local'],
            'view_options': view_options,
            'month_options': list(meses_map.values()),
            'week_groups': week_groups,
        }

    if view_normalizada == 'mensal':
        selecionado = meses_map.get((period or 'abril').strip().lower(), next(iter(meses_map.values())))
        return {
            'view': 'mensal',
            'period': selecionado['slug'],
            'label': selecionado['label'],
            'mes_slug': selecionado['slug'],
            'semana_local': None,
            'view_options': view_options,
            'month_options': list(meses_map.values()),
            'week_groups': week_groups,
        }

    return {
        'view': 'trimestral',
        'period': PERIODO_TRIMESTRAL[0],
        'label': PERIODO_TRIMESTRAL[1],
        'mes_slug': PERIODO_TRIMESTRAL[0],
        'semana_local': None,
        'view_options': view_options,
        'month_options': list(meses_map.values()),
        'week_groups': week_groups,
    }


def _sumario_valor_por_semanas_v2(modelo_meta, modelo_registro, campo_meta: str, campo_valor: str, semanas: list[int], filtro_valor=None) -> tuple[float, float]:
    metas = modelo_meta.query.filter(modelo_meta.semana.in_(semanas)).all()
    registros = modelo_registro.query.filter(modelo_registro.semana.in_(semanas)).all()
    meta = sum(float(getattr(item, campo_meta, 0) or 0) for item in metas)
    realizado = 0.0
    for item in registros:
        if filtro_valor and not filtro_valor(item):
            continue
        realizado += float(getattr(item, campo_valor, 0) or 0)
    return realizado, meta


def _sumario_acoes_por_semanas_v2(modelo_meta, scope: str, semanas: list[int]) -> dict:
    metas = modelo_meta.query.filter(modelo_meta.semana.in_(semanas)).all()
    meta = sum(int(getattr(item, 'acoes_planejadas', 0) or 0) for item in metas)
    realizado = contar_acoes(scope, semanas)
    return {
        'acoes_planejadas': float(meta),
        'acoes_realizadas': float(realizado),
        'percentual_acoes': float(_safe_pct(realizado, meta)),
    }


def _resumir_vendas_master_v2(periodo: dict) -> dict:
    if periodo['view'] == 'trimestral':
        financeiro = montar_contexto_template_vendas('resumo_trimestral', incluir_resumo=True)['financeiro']
        return {
            'realizado': float(financeiro['total_vendidas']),
            'meta': float(financeiro['meta_quantidade']),
            'percentual': float(financeiro['percentual_atingimento']),
            'acoes_realizadas': float(financeiro['acoes_realizadas']),
            'meta_acoes': float(financeiro['meta_acoes']),
            'percentual_acoes': float(financeiro['percentual_acoes']),
        }
    total_realizado = 0.0
    total_meta = 0.0
    total_acoes_realizadas = 0.0
    total_meta_acoes = 0.0
    for semana_global in periodo['semanas']:
        mes_slug, semana_local = _master_mes_e_semana_local_v2(semana_global)
        financeiro = montar_contexto_template_vendas(mes_slug, semana_local=semana_local)['financeiro']
        total_realizado += float(financeiro['total_vendidas'])
        total_meta += float(financeiro['meta_quantidade'])
        total_acoes_realizadas += float(financeiro['acoes_realizadas'])
        total_meta_acoes += float(financeiro['meta_acoes'])
    return {
        'realizado': total_realizado,
        'meta': total_meta,
        'percentual': _safe_pct(total_realizado, total_meta),
        'acoes_realizadas': total_acoes_realizadas,
        'meta_acoes': total_meta_acoes,
        'percentual_acoes': _safe_pct(total_acoes_realizadas, total_meta_acoes),
    }


def _resumir_investidores_master_v2(periodo: dict) -> dict:
    if periodo['view'] == 'trimestral':
        financeiro = montar_contexto_template_investidores('resumo_trimestral', incluir_resumo=True)['financeiro']
        return {
            'realizado': float(financeiro['valor_realizado']),
            'meta': float(financeiro['meta_valor']),
            'percentual': float(financeiro['percentual_atingimento']),
            'acoes_realizadas': float(financeiro['acoes_realizadas']),
            'meta_acoes': float(financeiro['meta_acoes']),
            'percentual_acoes': float(financeiro['percentual_acoes']),
        }
    total_realizado = 0.0
    total_meta = 0.0
    total_acoes_realizadas = 0.0
    total_meta_acoes = 0.0
    for semana_global in periodo['semanas']:
        mes_slug, semana_local = _master_mes_e_semana_local_v2(semana_global)
        financeiro = montar_contexto_template_investidores(mes_slug, semana_local=semana_local)['financeiro']
        total_realizado += float(financeiro['valor_realizado'])
        total_meta += float(financeiro['meta_valor'])
        total_acoes_realizadas += float(financeiro['acoes_realizadas'])
        total_meta_acoes += float(financeiro['meta_acoes'])
    return {
        'realizado': total_realizado,
        'meta': total_meta,
        'percentual': _safe_pct(total_realizado, total_meta),
        'acoes_realizadas': total_acoes_realizadas,
        'meta_acoes': total_meta_acoes,
        'percentual_acoes': _safe_pct(total_acoes_realizadas, total_meta_acoes),
    }


def _resumir_inadimplencia_master_v2(semanas: list[int]) -> dict:
    metas = MetaSemana.query.filter(MetaSemana.semana.in_(semanas)).all()
    registros = Relacionamento.query.filter(Relacionamento.semana.in_(semanas)).all()
    valor_meta = sum(float(item.valor_meta or 0) for item in metas)
    acoes_planejadas = sum(int(item.acoes_planejadas or 0) for item in metas)
    valor_realizado = sum(
        float(item.valor or 0)
        for item in registros
        if _situacao_conta_como_sim(item.situacao) and float(item.valor or 0) > 0
    )
    acoes_realizadas = contar_acoes('relacionamento', semanas)
    return {
        'realizado': valor_realizado,
        'meta': valor_meta,
        'percentual': _safe_pct(valor_realizado, valor_meta),
        'acoes_realizadas': acoes_realizadas,
        'acoes_planejadas': acoes_planejadas,
        'percentual_acoes': _safe_pct(acoes_realizadas, acoes_planejadas),
    }


def _montar_master_painel_periodizado(view: str | None = None, period: str | None = None) -> dict:
    periodo = _resolver_master_periodo_v2(view, period)
    semanas = periodo['semanas']
    meta_base_por_scope = _mapa_meta_base_total()
    resumo_vendas = _resumir_vendas_master_v2(periodo)
    resumo_investidores = _resumir_investidores_master_v2(periodo)
    resumo_inadimplencia = _resumir_inadimplencia_master_v2(semanas)
    bancos_realizado, bancos_meta = _sumario_valor_por_semanas_v2(MetaFinanceiroSemana, FinanceiroBanco, 'valor_meta', 'valor_arrecadado', semanas)
    giro_realizado, giro_meta = _sumario_valor_por_semanas_v2(MetaGiroSemana, GiroCaptacao, 'valor_meta', 'valor_captado', semanas)
    medicao_realizado, medicao_meta = _sumario_valor_por_semanas_v2(MetaMedicaoSemana, MedicaoRegistro, 'valor_meta', 'valor_medicao', semanas)
    fornecedores_realizado, fornecedores_meta = _sumario_valor_por_semanas_v2(
        MetaFornecedorSemana,
        FornecedorRegistro,
        'valor_meta',
        'valor_negociado',
        semanas,
        filtro_valor=lambda item: (item.situacao or '').upper().strip() in {'SIM (INTEGRAL)', 'SIM (PARCIAL)'},
    )
    resumo_bancos = _sumario_acoes_por_semanas_v2(MetaFinanceiroSemana, 'financeiro', semanas)
    resumo_giro = _sumario_acoes_por_semanas_v2(MetaGiroSemana, 'giro', semanas)
    resumo_medicao = _sumario_acoes_por_semanas_v2(MetaMedicaoSemana, 'medicao', semanas)
    resumo_fornecedores = _sumario_acoes_por_semanas_v2(MetaFornecedorSemana, 'fornecedores', semanas)

    agora = datetime.now().replace(microsecond=0)
    inicio_contagem = periodo['started_at']
    fim_periodo = periodo['deadline_at']
    duracao_total = max(int((fim_periodo - inicio_contagem).total_seconds()), 1)
    tempo_decorrido = int((agora - inicio_contagem).total_seconds())
    tempo_decorrido = min(max(tempo_decorrido, 0), duracao_total)
    tempo_pct = round((tempo_decorrido / duracao_total) * 100, 1)

    cards = [
        {'slug': 'venda_varejo', 'scope': 'vendas', 'nome': 'Venda Varejo', 'realizado': float(resumo_vendas['realizado']), 'meta': float(resumo_vendas['meta']), 'percentual': float(resumo_vendas['percentual']), 'descricao': f"Total vendido no período selecionado: {periodo['label']}.", 'comparativo_label': 'vendas realizadas x vendas planejadas', 'ficticio': False, 'monetario': False},
        {'slug': 'giro', 'scope': 'giro', 'nome': 'Capital de giro', 'realizado': giro_realizado, 'meta': giro_meta, 'percentual': _safe_pct(giro_realizado, giro_meta), 'descricao': f"Valor captado frente à meta do período {periodo['label']}.", 'comparativo_label': 'valor captado x meta de capital de giro', 'ficticio': False, 'monetario': True},
        {'slug': 'inadimplencia', 'scope': 'relacionamento', 'nome': 'Inadimplencia', 'realizado': float(resumo_inadimplencia['realizado']), 'meta': float(resumo_inadimplencia['meta']), 'percentual': float(resumo_inadimplencia['percentual']), 'descricao': f"Valor realizado frente ao planejado no período {periodo['label']}.", 'comparativo_label': 'valor realizado x valor planejado', 'ficticio': False, 'monetario': True},
        {'slug': 'medicao', 'scope': 'medicao', 'nome': 'Medição de obras', 'realizado': medicao_realizado, 'meta': medicao_meta, 'percentual': _safe_pct(medicao_realizado, medicao_meta), 'descricao': f"Valor de medição acumulado no período {periodo['label']}.", 'comparativo_label': 'valor de medição x meta de medição de obras', 'ficticio': False, 'monetario': True},
        {'slug': 'investidor', 'scope': 'investidores', 'nome': 'Investidor', 'realizado': float(resumo_investidores['realizado']), 'meta': float(resumo_investidores['meta']), 'percentual': float(resumo_investidores['percentual']), 'descricao': f"Valor realizado de investidores no período {periodo['label']}.", 'comparativo_label': 'valor realizado x meta de investidores', 'ficticio': False, 'monetario': True},
        {'slug': 'fornecedores', 'scope': 'fornecedores', 'nome': 'Renegociação Fornecedores', 'realizado': fornecedores_realizado, 'meta': fornecedores_meta, 'percentual': _safe_pct(fornecedores_realizado, fornecedores_meta), 'descricao': f"Valor negociado com fornecedores no período {periodo['label']}.", 'comparativo_label': 'valor negociado x meta de renegociação de fornecedores', 'ficticio': False, 'monetario': True},
        {'slug': 'bancos', 'scope': 'financeiro', 'nome': 'Renegociação Bancária', 'realizado': bancos_realizado, 'meta': bancos_meta, 'percentual': _safe_pct(bancos_realizado, bancos_meta), 'descricao': f"Valor arrecadado com bancos no período {periodo['label']}.", 'comparativo_label': 'valor arrecadado x meta de renegociação bancária', 'ficticio': False, 'monetario': True},
    ]
    cards_acoes = [
        {'slug': 'venda_varejo', 'nome': 'Acoes Venda Varejo', 'realizado': float(resumo_vendas['acoes_realizadas']), 'meta': float(resumo_vendas['meta_acoes']), 'percentual': float(resumo_vendas['percentual_acoes']), 'descricao': f"Acoes de venda varejo no periodo {periodo['label']}.", 'comparativo_label': 'acoes realizadas x meta de acoes', 'ficticio': False, 'monetario': False},
        {'slug': 'giro', 'nome': 'Acoes Capital de giro', 'realizado': float(resumo_giro['acoes_realizadas']), 'meta': float(resumo_giro['acoes_planejadas']), 'percentual': float(resumo_giro['percentual_acoes']), 'descricao': f"Acoes de capital de giro no periodo {periodo['label']}.", 'comparativo_label': 'acoes realizadas x meta de acoes', 'ficticio': False, 'monetario': False},
        {'slug': 'inadimplencia', 'nome': 'Acoes Inadimplencia', 'realizado': float(resumo_inadimplencia['acoes_realizadas']), 'meta': float(resumo_inadimplencia['acoes_planejadas']), 'percentual': float(resumo_inadimplencia['percentual_acoes']), 'descricao': f"Acoes de inadimplencia no periodo {periodo['label']}.", 'comparativo_label': 'acoes realizadas x meta de acoes', 'ficticio': False, 'monetario': False},
        {'slug': 'medicao', 'nome': 'Acoes Medicao de obras', 'realizado': float(resumo_medicao['acoes_realizadas']), 'meta': float(resumo_medicao['acoes_planejadas']), 'percentual': float(resumo_medicao['percentual_acoes']), 'descricao': f"Acoes de medicao no periodo {periodo['label']}.", 'comparativo_label': 'acoes realizadas x meta de acoes', 'ficticio': False, 'monetario': False},
        {'slug': 'investidor', 'nome': 'Acoes Investidor', 'realizado': float(resumo_investidores['acoes_realizadas']), 'meta': float(resumo_investidores['meta_acoes']), 'percentual': float(resumo_investidores['percentual_acoes']), 'descricao': f"Acoes de investidores no periodo {periodo['label']}.", 'comparativo_label': 'acoes realizadas x meta de acoes', 'ficticio': False, 'monetario': False},
        {'slug': 'fornecedores', 'nome': 'Acoes Renegociacao Fornecedores', 'realizado': float(resumo_fornecedores['acoes_realizadas']), 'meta': float(resumo_fornecedores['acoes_planejadas']), 'percentual': float(resumo_fornecedores['percentual_acoes']), 'descricao': f"Acoes de fornecedores no periodo {periodo['label']}.", 'comparativo_label': 'acoes realizadas x meta de acoes', 'ficticio': False, 'monetario': False},
        {'slug': 'bancos', 'nome': 'Acoes Renegociacao Bancaria', 'realizado': float(resumo_bancos['acoes_realizadas']), 'meta': float(resumo_bancos['acoes_planejadas']), 'percentual': float(resumo_bancos['percentual_acoes']), 'descricao': f"Acoes bancarias no periodo {periodo['label']}.", 'comparativo_label': 'acoes realizadas x meta de acoes', 'ficticio': False, 'monetario': False},
    ]
    ordem = ['venda_varejo', 'giro', 'inadimplencia', 'medicao', 'investidor', 'fornecedores', 'bancos']
    cards_ordenados = sorted(cards, key=lambda item: ordem.index(item['slug']))
    if periodo['view'] == 'trimestral':
        for card in cards_ordenados:
            meta_base_total = float(meta_base_por_scope.get(card['scope'], 0) or 0)
            card['meta'] = meta_base_total
            card['percentual'] = _safe_pct(float(card['realizado']), meta_base_total)
    for card in cards_ordenados:
        if card['percentual'] > tempo_pct + 0.1:
            card['desempenho_status'] = 'positivo'
        elif card['percentual'] < tempo_pct - 0.1:
            card['desempenho_status'] = 'negativo'
        else:
            card['desempenho_status'] = 'neutro'
    cards_acoes_ordenados = sorted(cards_acoes, key=lambda item: ordem.index(item['slug']))
    for card in cards_acoes_ordenados:
        if card['percentual'] > tempo_pct + 0.1:
            card['desempenho_status'] = 'positivo'
        elif card['percentual'] < tempo_pct - 0.1:
            card['desempenho_status'] = 'negativo'
        else:
            card['desempenho_status'] = 'neutro'

    total_realizado = sum(min(float(item['percentual']), 100.0) for item in cards_ordenados)
    total_meta = float(len(cards_ordenados) * 100)
    objetivo_geral = _safe_pct(total_realizado, total_meta)
    total_acoes_realizadas = sum(float(item['realizado']) for item in cards_acoes_ordenados)
    total_acoes_meta = sum(float(item['meta']) for item in cards_acoes_ordenados)
    percentual_acoes_master = _safe_pct(total_acoes_realizadas, total_acoes_meta)
    destaque_principal = max(cards_ordenados, key=lambda item: item['percentual']) if cards_ordenados else None
    alerta_principal = min(cards_ordenados, key=lambda item: item['percentual']) if cards_ordenados else None

    return {
        'cards_master': cards_ordenados,
        'cards_master_acoes': cards_acoes_ordenados,
        'objetivo_geral': objetivo_geral,
        'objetivo_realizado_total': total_realizado,
        'objetivo_meta_total': total_meta,
        'acoes_realizadas_master': total_acoes_realizadas,
        'acoes_meta_master': total_acoes_meta,
        'acoes_percentual_master': percentual_acoes_master,
        'tempo_pct': tempo_pct,
        'tempo_restante_label': _formatar_tempo_restante(tempo_decorrido),
        'data_limite_label': f'{inicio_contagem.strftime("%d/%m/%Y")} a {fim_periodo.strftime("%d/%m/%Y")}',
        'timer_started_at_iso': inicio_contagem.isoformat(),
        'timer_deadline_at_iso': fim_periodo.isoformat(),
        'destaque_principal': destaque_principal,
        'alerta_principal': alerta_principal,
        'analytics_ai_enabled': analytics_ai_enabled() and analytics_ai_available(),
        'master_view': periodo['view'],
        'master_period': periodo['period'],
        'master_period_label': periodo['label'],
        'master_view_options': periodo['view_options'],
        'master_period_options': periodo['period_options'],
    }


def _serializar_master_painel_periodizado(view: str | None = None, period: str | None = None) -> dict:
    painel = _montar_master_painel_periodizado(view, period)
    return {
        'cards_master': painel['cards_master'],
        'cards_master_acoes': painel['cards_master_acoes'],
        'objetivo_geral': painel['objetivo_geral'],
        'objetivo_realizado_total': painel['objetivo_realizado_total'],
        'objetivo_meta_total': painel['objetivo_meta_total'],
        'acoes_realizadas_master': painel['acoes_realizadas_master'],
        'acoes_meta_master': painel['acoes_meta_master'],
        'acoes_percentual_master': painel['acoes_percentual_master'],
        'tempo_pct': painel['tempo_pct'],
        'tempo_restante_label': painel['tempo_restante_label'],
        'data_limite_label': painel['data_limite_label'],
        'timer_started_at_iso': painel['timer_started_at_iso'],
        'timer_deadline_at_iso': painel['timer_deadline_at_iso'],
        'destaque_principal': painel['destaque_principal'],
        'alerta_principal': painel['alerta_principal'],
        'master_view': painel['master_view'],
        'master_period': painel['master_period'],
        'master_period_label': painel['master_period_label'],
    }


def _montar_contexto_ia_master_periodizado(view: str | None = None, period: str | None = None) -> dict:
    painel = _montar_master_painel_periodizado(view, period)
    return {
        'objetivo_geral': painel['objetivo_geral'],
        'tempo_pct': painel['tempo_pct'],
        'tempo_restante_label': painel['tempo_restante_label'],
        'data_limite_label': painel['data_limite_label'],
        'periodo': painel['master_period_label'],
        'cards_master': [
            {
                'frente': card['nome'],
                'realizado': card['realizado'],
                'meta': card['meta'],
                'percentual': card['percentual'],
                'descricao': card['descricao'],
                'comparativo_label': card['comparativo_label'],
                'ficticio': card['ficticio'],
                'monetario': card['monetario'],
                'desempenho_status': card['desempenho_status'],
            }
            for card in painel['cards_master']
        ],
        'cards_master_acoes': painel['cards_master_acoes'],
        'destaque_principal': painel['destaque_principal'],
        'alerta_principal': painel['alerta_principal'],
    }

admin_bp = Blueprint('admin', __name__)


def requer_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_manage_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated


def requer_dashboard_metas(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_access_metas_dashboard():
            abort(403)
        return f(*args, **kwargs)
    return decorated


def requer_painel(scope: str):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.can_access_panel(scope):
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def _garantir_permissao_meta(scope: str):
    if not current_user.is_authenticated or not current_user.can_access_meta_scope(scope):
        abort(403)


def _meta_esta_liberada(scope: str, semana: int) -> bool:
    return (
        MetaLiberacaoSemana.query
        .filter_by(scope=scope, semana=semana, liberada=True)
        .first()
        is not None
    )


def _garantir_meta_liberada(scope: str, semana: int) -> bool:
    if current_user.can_access_meta_scope(scope):
        return True
    return _meta_esta_liberada(scope, semana)


def _pode_editar_meta_existente(scope: str) -> bool:
    return current_user.can_access_meta_scope(scope)


def _meta_relacionamento_preenchida(meta: MetaSemana | None) -> bool:
    if meta is None:
        return False
    return (int(meta.acoes_planejadas or 0) > 0) or (float(meta.valor_meta or 0) > 0)


def _meta_valor_preenchida(meta) -> bool:
    if meta is None:
        return False
    return (
        float(getattr(meta, 'valor_meta', 0) or 0) > 0
        or int(getattr(meta, 'acoes_planejadas', 0) or 0) > 0
    )


def _meta_venda_preenchida(meta: MetaVendaSemana | None) -> bool:
    if meta is None:
        return False
    return int(meta.quantidade_meta or 0) > 0 or int(meta.acoes_planejadas or 0) > 0


def _mapa_metas_liberadas() -> dict[str, set[int]]:
    mapa: dict[str, set[int]] = {}
    liberacoes = (
        MetaLiberacaoSemana.query
        .filter_by(liberada=True)
        .order_by(MetaLiberacaoSemana.scope.asc(), MetaLiberacaoSemana.semana.asc())
        .all()
    )
    for liberacao in liberacoes:
        mapa.setdefault(liberacao.scope, set()).add(int(liberacao.semana))
    return mapa


def _contexto_dashboard_metas(show_admin_cards: bool, show_meta_cards: bool) -> dict:
    return {
        'usuarios': User.query.order_by(User.nome).all() if show_admin_cards and current_user.can_manage_admin() else [],
        'empreendimentos': Empreendimento.query.order_by(Empreendimento.nome).all() if show_admin_cards and current_user.can_manage_admin() else [],
        'metas': MetaSemana.query.order_by(MetaSemana.semana).all(),
        'metas_vendas': {meta.semana: meta for meta in MetaVendaSemana.query.order_by(MetaVendaSemana.semana).all()},
        'metas_investidores': {meta.semana: meta for meta in MetaInvestidorSemana.query.order_by(MetaInvestidorSemana.semana).all()},
        'metas_financeiro': {meta.semana: meta for meta in MetaFinanceiroSemana.query.order_by(MetaFinanceiroSemana.semana).all()},
        'metas_fornecedores': {meta.semana: meta for meta in MetaFornecedorSemana.query.order_by(MetaFornecedorSemana.semana).all()},
        'metas_giro': {meta.semana: meta for meta in MetaGiroSemana.query.order_by(MetaGiroSemana.semana).all()},
        'metas_medicao': {meta.semana: meta for meta in MetaMedicaoSemana.query.order_by(MetaMedicaoSemana.semana).all()},
        'metas_base_total': _mapa_meta_base_total(),
        'metas_liberadas': _mapa_metas_liberadas(),
        'meses_vendas': MESES_VENDAS,
        'periodo_investidores': PERIODO_INVESTIDORES,
        'tipos': TIPOS_VALIDOS,
        'is_admin_dashboard': current_user.can_manage_admin(),
        'meta_scopes': current_user.meta_scopes() if show_meta_cards else set(),
        'show_admin_cards': show_admin_cards,
        'show_meta_cards': show_meta_cards,
    }


@admin_bp.route('/')
@login_required
@requer_dashboard_metas
def dashboard():
    if current_user.can_manage_admin():
        contexto = _contexto_dashboard_metas(show_admin_cards=True, show_meta_cards=False)
    else:
        contexto = _contexto_dashboard_metas(show_admin_cards=False, show_meta_cards=True)
    return render_template('admin/dashboard.html', **contexto)


@admin_bp.route('/metas')
@login_required
@requer_dashboard_metas
def metas_dashboard():
    return render_template('admin/dashboard.html', **_contexto_dashboard_metas(show_admin_cards=False, show_meta_cards=True))


@admin_bp.route('/relacionamento')
@login_required
@requer_painel('relacionamento')
def relacionamento_painel():
    filtros = _normalizar_filtros(request.args)
    dados = _montar_relatorio_relacionamento(request.args.get('mes', 'abril'), filtros)
    dados['analytics_ai_enabled'] = analytics_ai_enabled() and analytics_ai_available()
    return render_template('admin/relacionamento_painel.html', **dados)


@admin_bp.route('/vendas')
@login_required
@requer_painel('vendas')
def vendas_painel():
    periodo = _resolver_periodo_painel(request.args.get('view'), request.args.get('period'), MESES_VENDAS)
    dados = montar_contexto_template_vendas(periodo['mes_slug'], incluir_resumo=True, semana_local=periodo['semana_local'])
    dados['painel_admin_vendas'] = True
    dados['analytics_view'] = periodo['view']
    dados['analytics_period'] = periodo['period']
    dados['analytics_period_label'] = periodo['label']
    dados['analytics_view_options'] = periodo['view_options']
    dados['analytics_month_options'] = periodo['month_options']
    dados['analytics_week_groups'] = periodo['week_groups']
    return render_template('vendas/index.html', **dados)


@admin_bp.route('/investidores')
@login_required
@requer_painel('investidores')
def investidores_painel():
    periodo = _resolver_periodo_painel(request.args.get('view'), request.args.get('period'), MESES_INVESTIDORES)
    dados = montar_contexto_template_investidores(periodo['mes_slug'], incluir_resumo=True, semana_local=periodo['semana_local'])
    dados['painel_admin_investidores'] = True
    dados['analytics_view'] = periodo['view']
    dados['analytics_period'] = periodo['period']
    dados['analytics_period_label'] = periodo['label']
    dados['analytics_view_options'] = periodo['view_options']
    dados['analytics_month_options'] = periodo['month_options']
    dados['analytics_week_groups'] = periodo['week_groups']
    return render_template('investidores/index.html', **dados)


@admin_bp.route('/financeiro')
@login_required
@requer_painel('financeiro')
def financeiro_painel():
    filtros = _normalizar_filtros_financeiro(request.args)
    dados = _montar_relatorio_financeiro(request.args.get('mes', 'abril'), filtros)
    dados['analytics_ai_enabled'] = analytics_ai_enabled() and analytics_ai_available()
    return render_template('admin/financeiro_painel.html', **dados)


@admin_bp.route('/giro')
@login_required
@requer_painel('giro')
def giro_painel():
    filtros = _normalizar_filtros_giro(request.args)
    dados = _montar_relatorio_giro(request.args.get('mes', 'abril'), filtros)
    dados['analytics_ai_enabled'] = analytics_ai_enabled() and analytics_ai_available()
    return render_template('admin/giro_painel.html', **dados)


@admin_bp.route('/fornecedores')
@login_required
@requer_painel('fornecedores')
def fornecedores_painel():
    filtros = _normalizar_filtros_fornecedores(request.args)
    dados = _montar_relatorio_fornecedores(request.args.get('mes', 'abril'), filtros)
    dados['analytics_ai_enabled'] = analytics_ai_enabled() and analytics_ai_available()
    return render_template('admin/fornecedores_painel.html', **dados)


@admin_bp.route('/medicao')
@login_required
@requer_painel('medicao')
def medicao_painel():
    filtros = _normalizar_filtros_medicao(request.args)
    dados = _montar_relatorio_medicao(request.args.get('mes', 'abril'), filtros)
    dados['analytics_ai_enabled'] = analytics_ai_enabled() and analytics_ai_available()
    return render_template('admin/medicao_painel.html', **dados)


@admin_bp.route('/master')
@login_required
@requer_painel('master')
def master_painel():
    view = request.args.get('view', 'trimestral')
    period = request.args.get('period')
    return render_template('admin/master_painel.html', **_montar_master_painel_periodizado(view, period))


@admin_bp.route('/master/data')
@login_required
@requer_painel('master')
def master_painel_data():
    view = request.args.get('view', 'trimestral')
    period = request.args.get('period')
    return jsonify(_serializar_master_painel_periodizado(view, period))


@admin_bp.route('/master/ai-chat', methods=['POST'])
@login_required
@requer_painel('master')
def master_ai_chat():
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

    history = dados.get('history') or []
    contexto = build_global_ai_context(
        page='painel_master',
        actor=current_user,
        extra_context=_montar_contexto_ia_master_periodizado(dados.get('view'), dados.get('period')),
    )

    try:
        resposta = ask_analytics_assistant(pergunta, history, contexto)
    except Exception:
        resposta = fallback_analytics_answer(pergunta, contexto)

    return jsonify({'answer': resposta})


@admin_bp.route('/relacionamento/ai-chat', methods=['POST'])
@login_required
@requer_painel('relacionamento')
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
    contexto = build_global_ai_context(
        page='painel_inadimplencia',
        actor=current_user,
        extra_context=_montar_contexto_ia_relacionamento(mes_slug, filtros),
    )

    try:
        resposta = ask_analytics_assistant(pergunta, history, contexto)
    except Exception:
        resposta = fallback_analytics_answer(pergunta, contexto)

    return jsonify({'answer': resposta})


@admin_bp.route('/financeiro/ai-chat', methods=['POST'])
@login_required
@requer_painel('financeiro')
def financeiro_ai_chat():
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

    filtros = _normalizar_filtros_financeiro(dados)
    mes_slug = dados.get('mes') or 'resumo_trimestral'
    history = dados.get('history') or []
    contexto = build_global_ai_context(
        page='painel_financeiro',
        actor=current_user,
        extra_context=_montar_contexto_ia_financeiro(mes_slug, filtros),
    )

    try:
        resposta = ask_analytics_assistant(pergunta, history, contexto)
    except Exception:
        resposta = fallback_analytics_answer(pergunta, contexto)

    return jsonify({'answer': resposta})


@admin_bp.route('/giro/ai-chat', methods=['POST'])
@login_required
@requer_painel('giro')
def giro_ai_chat():
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

    filtros = _normalizar_filtros_giro(dados)
    mes_slug = dados.get('mes') or 'resumo_trimestral'
    history = dados.get('history') or []
    contexto = build_global_ai_context(
        page='painel_giro',
        actor=current_user,
        extra_context=_montar_contexto_ia_giro(mes_slug, filtros),
    )

    try:
        resposta = ask_analytics_assistant(pergunta, history, contexto)
    except Exception:
        resposta = fallback_analytics_answer(pergunta, contexto)

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

@admin_bp.route('/meta/disponibilizar', methods=['POST'])
@login_required
@requer_admin
def disponibilizar_meta():
    dados = request.get_json(silent=True) or request.form.to_dict()
    scope = (dados.get('scope') or '').strip().lower()
    try:
        semana = int(dados.get('semana', 0))
    except (TypeError, ValueError):
        return jsonify({'erro': 'Semana invalida.'}), 400

    if scope not in {'relacionamento', 'vendas', 'investidores', 'financeiro', 'giro', 'fornecedores', 'medicao'}:
        return jsonify({'erro': 'Escopo de meta invalido.'}), 400
    if semana not in range(1, 13):
        return jsonify({'erro': 'Semana invalida.'}), 400

    liberacao = MetaLiberacaoSemana.query.filter_by(scope=scope, semana=semana).first()
    if not liberacao:
        liberacao = MetaLiberacaoSemana(scope=scope, semana=semana)
        db.session.add(liberacao)

    liberacao.liberada = True
    liberacao.liberada_por = current_user.nome
    liberacao.liberada_em = datetime.now()
    db.session.commit()
    return jsonify({'sucesso': True, 'scope': scope, 'semana': semana, 'liberada': True})


@admin_bp.route('/meta-base/salvar', methods=['POST'])
@login_required
@requer_admin
def salvar_meta_base():
    dados = request.get_json(silent=True) or request.form.to_dict()
    scope = (dados.get('scope') or '').strip().lower()
    tipo = (dados.get('tipo') or 'monetario').strip().lower()
    if scope not in {'relacionamento', 'vendas', 'investidores', 'financeiro', 'giro', 'fornecedores', 'medicao'}:
        return jsonify({'erro': 'Escopo de meta invalido.'}), 400

    try:
        valor = float(dados.get('valor', 0) or 0)
    except (TypeError, ValueError):
        return jsonify({'erro': 'Valor invalido.'}), 400

    valor_normalizado = max(round(valor, 2), 0.0)
    if tipo == 'inteiro':
        valor_normalizado = int(valor_normalizado)

    _salvar_meta_base_total(scope, valor_normalizado)
    db.session.commit()
    return jsonify({'sucesso': True, 'scope': scope, 'valor': valor_normalizado})


@admin_bp.route('/meta/salvar', methods=['POST'])
@login_required
def salvar_meta():
    _garantir_permissao_meta('relacionamento')
    dados = request.get_json(silent=True) or request.form.to_dict()
    semana = int(dados.get('semana', 1))
    if not _garantir_meta_liberada('relacionamento', semana):
        return jsonify({'erro': 'Meta ainda nao foi disponibilizada pelo administrador.'}), 403
    try:
        acoes = int(dados.get('acoes_planejadas', 0))
        valor = float(dados.get('valor_meta', 0))
        meta_base_total = float(dados.get('meta_base_total', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valores inválidos.'}), 400

    meta = MetaSemana.query.filter_by(semana=semana).first()
    if meta:
        if _meta_relacionamento_preenchida(meta) and not _pode_editar_meta_existente('relacionamento'):
            return jsonify({'erro': 'Meta ja preenchida e bloqueada para edicao.'}), 403
        _registrar_auditoria_meta('relacionamento', 'acoes_planejadas', int(meta.acoes_planejadas or 0), acoes, f's{semana}')
        _registrar_auditoria_meta('relacionamento', 'valor_meta', float(meta.valor_meta or 0), valor, f's{semana}')
        meta.acoes_planejadas = acoes
        meta.valor_meta = valor
    else:
        meta = MetaSemana(semana=semana, acoes_planejadas=acoes, valor_meta=valor)
        db.session.add(meta)
        _registrar_auditoria_meta('relacionamento', 'acoes_planejadas', 0, acoes, f's{semana}')
        _registrar_auditoria_meta('relacionamento', 'valor_meta', 0, valor, f's{semana}')
    if current_user.can_manage_admin():
        _salvar_meta_base_total('relacionamento', meta_base_total)
    db.session.commit()
    return jsonify({'sucesso': True})


@admin_bp.route('/meta-investidor/salvar', methods=['POST'])
@login_required
def salvar_meta_investidor():
    _garantir_permissao_meta('investidores')
    dados = request.get_json(silent=True) or request.form.to_dict()
    try:
        semana = int(dados.get('semana', 1))
        valor = float(dados.get('valor_meta', 0) or 0)
        acoes = int(dados.get('acoes_planejadas', 0) or 0)
        meta_base_total = float(dados.get('meta_base_total', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valor invalido.'}), 400
    if not _garantir_meta_liberada('investidores', semana):
        return jsonify({'erro': 'Meta ainda nao foi disponibilizada pelo administrador.'}), 403

    meta = MetaInvestidorSemana.query.filter_by(semana=semana).first()
    if meta:
        if _meta_valor_preenchida(meta) and not _pode_editar_meta_existente('investidores'):
            return jsonify({'erro': 'Meta ja preenchida e bloqueada para edicao.'}), 403
        _registrar_auditoria_meta('investidores', 'valor_meta', float(meta.valor_meta or 0), max(valor, 0), f's{semana}')
        _registrar_auditoria_meta('investidores', 'acoes_planejadas', int(meta.acoes_planejadas or 0), max(acoes, 0), f's{semana}')
        meta.valor_meta = max(valor, 0)
        meta.acoes_planejadas = max(acoes, 0)
    else:
        meta = MetaInvestidorSemana(semana=semana, valor_meta=max(valor, 0), acoes_planejadas=max(acoes, 0))
        db.session.add(meta)
        _registrar_auditoria_meta('investidores', 'valor_meta', 0, max(valor, 0), f's{semana}')
        _registrar_auditoria_meta('investidores', 'acoes_planejadas', 0, max(acoes, 0), f's{semana}')
    if current_user.can_manage_admin():
        _salvar_meta_base_total('investidores', meta_base_total)
    db.session.commit()
    return jsonify({'sucesso': True})


@admin_bp.route('/meta-financeiro/salvar', methods=['POST'])
@login_required
def salvar_meta_financeiro():
    _garantir_permissao_meta('financeiro')
    dados = request.get_json(silent=True) or request.form.to_dict()
    try:
        semana = int(dados.get('semana', 1))
        valor = float(dados.get('valor_meta', 0) or 0)
        acoes = int(dados.get('acoes_planejadas', 0) or 0)
        meta_base_total = float(dados.get('meta_base_total', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valores invalidos.'}), 400
    if not _garantir_meta_liberada('financeiro', semana):
        return jsonify({'erro': 'Meta ainda nao foi disponibilizada pelo administrador.'}), 403

    meta = MetaFinanceiroSemana.query.filter_by(semana=semana).first()
    if meta:
        if _meta_valor_preenchida(meta) and not _pode_editar_meta_existente('financeiro'):
            return jsonify({'erro': 'Meta ja preenchida e bloqueada para edicao.'}), 403
        _registrar_auditoria_meta('financeiro', 'valor_meta', float(meta.valor_meta or 0), max(valor, 0), f's{semana}')
        _registrar_auditoria_meta('financeiro', 'acoes_planejadas', int(meta.acoes_planejadas or 0), max(acoes, 0), f's{semana}')
        meta.valor_meta = max(valor, 0)
        meta.acoes_planejadas = max(acoes, 0)
    else:
        meta = MetaFinanceiroSemana(semana=semana, valor_meta=max(valor, 0), acoes_planejadas=max(acoes, 0))
        db.session.add(meta)
        _registrar_auditoria_meta('financeiro', 'valor_meta', 0, max(valor, 0), f's{semana}')
        _registrar_auditoria_meta('financeiro', 'acoes_planejadas', 0, max(acoes, 0), f's{semana}')
    if current_user.can_manage_admin():
        _salvar_meta_base_total('financeiro', meta_base_total)
    db.session.commit()
    return jsonify({'sucesso': True})


@admin_bp.route('/meta-giro/salvar', methods=['POST'])
@login_required
def salvar_meta_giro():
    _garantir_permissao_meta('giro')
    dados = request.get_json(silent=True) or request.form.to_dict()
    try:
        semana = int(dados.get('semana', 1))
        valor = float(dados.get('valor_meta', 0) or 0)
        acoes = int(dados.get('acoes_planejadas', 0) or 0)
        meta_base_total = float(dados.get('meta_base_total', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valores invalidos.'}), 400
    if not _garantir_meta_liberada('giro', semana):
        return jsonify({'erro': 'Meta ainda nao foi disponibilizada pelo administrador.'}), 403

    meta = MetaGiroSemana.query.filter_by(semana=semana).first()
    if meta:
        if _meta_valor_preenchida(meta) and not _pode_editar_meta_existente('giro'):
            return jsonify({'erro': 'Meta ja preenchida e bloqueada para edicao.'}), 403
        _registrar_auditoria_meta('giro', 'valor_meta', float(meta.valor_meta or 0), max(valor, 0), f's{semana}')
        _registrar_auditoria_meta('giro', 'acoes_planejadas', int(meta.acoes_planejadas or 0), max(acoes, 0), f's{semana}')
        meta.valor_meta = max(valor, 0)
        meta.acoes_planejadas = max(acoes, 0)
    else:
        meta = MetaGiroSemana(semana=semana, valor_meta=max(valor, 0), acoes_planejadas=max(acoes, 0))
        db.session.add(meta)
        _registrar_auditoria_meta('giro', 'valor_meta', 0, max(valor, 0), f's{semana}')
        _registrar_auditoria_meta('giro', 'acoes_planejadas', 0, max(acoes, 0), f's{semana}')
    if current_user.can_manage_admin():
        _salvar_meta_base_total('giro', meta_base_total)
    db.session.commit()
    return jsonify({'sucesso': True})


@admin_bp.route('/meta-fornecedor/salvar', methods=['POST'])
@login_required
def salvar_meta_fornecedor():
    _garantir_permissao_meta('fornecedores')
    dados = request.get_json(silent=True) or request.form.to_dict()
    try:
        semana = int(dados.get('semana', 1))
        valor = float(dados.get('valor_meta', 0) or 0)
        acoes = int(dados.get('acoes_planejadas', 0) or 0)
        meta_base_total = float(dados.get('meta_base_total', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valores invalidos.'}), 400
    if not _garantir_meta_liberada('fornecedores', semana):
        return jsonify({'erro': 'Meta ainda nao foi disponibilizada pelo administrador.'}), 403

    meta = MetaFornecedorSemana.query.filter_by(semana=semana).first()
    if meta:
        if _meta_valor_preenchida(meta) and not _pode_editar_meta_existente('fornecedores'):
            return jsonify({'erro': 'Meta ja preenchida e bloqueada para edicao.'}), 403
        _registrar_auditoria_meta('fornecedores', 'valor_meta', float(meta.valor_meta or 0), max(valor, 0), f's{semana}')
        _registrar_auditoria_meta('fornecedores', 'acoes_planejadas', int(meta.acoes_planejadas or 0), max(acoes, 0), f's{semana}')
        meta.valor_meta = max(valor, 0)
        meta.acoes_planejadas = max(acoes, 0)
    else:
        meta = MetaFornecedorSemana(semana=semana, valor_meta=max(valor, 0), acoes_planejadas=max(acoes, 0))
        db.session.add(meta)
        _registrar_auditoria_meta('fornecedores', 'valor_meta', 0, max(valor, 0), f's{semana}')
        _registrar_auditoria_meta('fornecedores', 'acoes_planejadas', 0, max(acoes, 0), f's{semana}')
    if current_user.can_manage_admin():
        _salvar_meta_base_total('fornecedores', meta_base_total)
    db.session.commit()
    return jsonify({'sucesso': True})


@admin_bp.route('/meta-medicao/salvar', methods=['POST'])
@login_required
def salvar_meta_medicao():
    _garantir_permissao_meta('medicao')
    dados = request.get_json(silent=True) or request.form.to_dict()
    try:
        semana = int(dados.get('semana', 1))
        valor = float(dados.get('valor_meta', 0) or 0)
        acoes = int(dados.get('acoes_planejadas', 0) or 0)
        meta_base_total = float(dados.get('meta_base_total', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Valores invalidos.'}), 400
    if not _garantir_meta_liberada('medicao', semana):
        return jsonify({'erro': 'Meta ainda nao foi disponibilizada pelo administrador.'}), 403

    meta = MetaMedicaoSemana.query.filter_by(semana=semana).first()
    if meta:
        if _meta_valor_preenchida(meta) and not _pode_editar_meta_existente('medicao'):
            return jsonify({'erro': 'Meta ja preenchida e bloqueada para edicao.'}), 403
        _registrar_auditoria_meta('medicao', 'valor_meta', float(meta.valor_meta or 0), max(valor, 0), f's{semana}')
        _registrar_auditoria_meta('medicao', 'acoes_planejadas', int(meta.acoes_planejadas or 0), max(acoes, 0), f's{semana}')
        meta.valor_meta = max(valor, 0)
        meta.acoes_planejadas = max(acoes, 0)
    else:
        meta = MetaMedicaoSemana(semana=semana, valor_meta=max(valor, 0), acoes_planejadas=max(acoes, 0))
        db.session.add(meta)
        _registrar_auditoria_meta('medicao', 'valor_meta', 0, max(valor, 0), f's{semana}')
        _registrar_auditoria_meta('medicao', 'acoes_planejadas', 0, max(acoes, 0), f's{semana}')
    if current_user.can_manage_admin():
        _salvar_meta_base_total('medicao', meta_base_total)
    db.session.commit()
    return jsonify({'sucesso': True})


@admin_bp.route('/meta-venda/salvar', methods=['POST'])
@login_required
def salvar_meta_venda():
    _garantir_permissao_meta('vendas')
    dados = request.get_json(silent=True) or request.form.to_dict()
    try:
        semana = int(dados.get('semana', 1))
        quantidade = int(dados.get('quantidade_meta', 0) or 0)
        acoes = int(dados.get('acoes_planejadas', 0) or 0)
        meta_base_total = float(dados.get('meta_base_total', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'erro': 'Quantidade inválida.'}), 400

    if not _garantir_meta_liberada('vendas', semana):
        return jsonify({'erro': 'Meta ainda nao foi disponibilizada pelo administrador.'}), 403
    meta = MetaVendaSemana.query.filter_by(semana=semana).first()
    if meta:
        if _meta_venda_preenchida(meta) and not _pode_editar_meta_existente('vendas'):
            return jsonify({'erro': 'Meta ja preenchida e bloqueada para edicao.'}), 403
        _registrar_auditoria_meta('vendas', 'quantidade_meta', int(meta.quantidade_meta or 0), max(quantidade, 0), f's{semana}')
        _registrar_auditoria_meta('vendas', 'acoes_planejadas', int(meta.acoes_planejadas or 0), max(acoes, 0), f's{semana}')
        meta.quantidade_meta = max(quantidade, 0)
        meta.acoes_planejadas = max(acoes, 0)
    else:
        meta = MetaVendaSemana(semana=semana, quantidade_meta=max(quantidade, 0), acoes_planejadas=max(acoes, 0))
        db.session.add(meta)
        _registrar_auditoria_meta('vendas', 'quantidade_meta', 0, max(quantidade, 0), f's{semana}')
        _registrar_auditoria_meta('vendas', 'acoes_planejadas', 0, max(acoes, 0), f's{semana}')
    if current_user.can_manage_admin():
        _salvar_meta_base_total('vendas', meta_base_total)
    db.session.commit()
    return jsonify({'sucesso': True})


@admin_bp.route('/medicao/ai-chat', methods=['POST'])
@login_required
@requer_painel('medicao')
def medicao_ai_chat():
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

    filtros = _normalizar_filtros_medicao(dados)
    mes_slug = dados.get('mes') or 'resumo_trimestral'
    history = dados.get('history') or []
    contexto = build_global_ai_context(
        page='painel_medicao',
        actor=current_user,
        extra_context=_montar_contexto_ia_medicao(mes_slug, filtros),
    )

    try:
        resposta = ask_analytics_assistant(pergunta, history, contexto)
    except Exception:
        resposta = fallback_analytics_answer(pergunta, contexto)

    return jsonify({'answer': resposta})


@admin_bp.route('/fornecedores/ai-chat', methods=['POST'])
@login_required
@requer_painel('fornecedores')
def fornecedores_ai_chat():
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

    filtros = _normalizar_filtros_fornecedores(dados)
    mes_slug = dados.get('mes') or 'resumo_trimestral'
    history = dados.get('history') or []
    contexto = build_global_ai_context(
        page='painel_fornecedores',
        actor=current_user,
        extra_context=_montar_contexto_ia_fornecedores(mes_slug, filtros),
    )

    try:
        resposta = ask_analytics_assistant(pergunta, history, contexto)
    except Exception:
        resposta = fallback_analytics_answer(pergunta, contexto)

    return jsonify({'answer': resposta})
