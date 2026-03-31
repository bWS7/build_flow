import json
import os
import re
import unicodedata
from datetime import datetime

DEFAULT_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
DEFAULT_STYLE = os.environ.get('GEMINI_ANALYTICS_STYLE', 'executivo')


def analytics_ai_enabled() -> bool:
    return bool(os.environ.get('GEMINI_API_KEY'))


def analytics_ai_available() -> bool:
    try:
        from google import genai  # noqa: F401
        return True
    except Exception:
        return False


def _sanitize_response(text: str) -> str:
    cleaned = (text or '').replace('*', '')
    replacements = {
        'valor_realizado': 'Valor Realizado',
        'valor_planejado': 'Valor Planejado',
        'acoes_realizadas': 'Acoes Realizadas',
        'acoes_planejadas': 'Acoes Planejadas',
        'pct_valor': 'Percentual de Valor Realizado',
        'pct_acoes': 'Percentual de Acoes Realizadas',
        'melhor_semana': 'melhor semana',
        'pior_semana': 'pior semana',
        'resumo_mensal': 'resumo do periodo',
        'responsavel': 'responsavel',
        'situacao': 'situacao',
        'empreendimento': 'empreendimento',
    }
    for raw, friendly in replacements.items():
        cleaned = re.sub(rf'\b{re.escape(raw)}\b', friendly, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    return cleaned.strip()


def _should_be_brief(question: str) -> bool:
    normalized = re.sub(r'\s+', ' ', (question or '').strip().lower())
    if not normalized:
        return False

    brief_starters = (
        'qual ',
        'quanto ',
        'quantos ',
        'quais ',
        'quando ',
        'quem ',
    )
    brief_terms = (
        'ticket medio',
        'ticket médio',
        'valor medio',
        'valor médio',
        'media',
        'média',
        'total',
        'quantidade',
        'percentual',
        'meta',
        'saldo',
        'faturamento',
        'vendas',
        'investidores',
    )
    complexity_terms = (
        'por que',
        'porque',
        'explique',
        'analise',
        'analisa',
        'compare',
        'comparar',
        'tendencia',
        'tendência',
        'gargalo',
        'gargalos',
        'oportunidade',
        'oportunidades',
        'plano de acao',
        'plano de ação',
        'detalhe',
        'detalhar',
        'resuma',
        'resumir',
    )

    if any(term in normalized for term in complexity_terms):
        return False

    word_count = len(normalized.split())
    starts_brief = normalized.startswith(brief_starters)
    has_brief_term = any(term in normalized for term in brief_terms)
    return word_count <= 10 and (starts_brief or has_brief_term)


def _normalizar_texto_analitico(value) -> str:
    return ' '.join(str(value or '').strip().upper().split())


def _normalizar_pergunta_analitica(text: str) -> str:
    normalized = unicodedata.normalize('NFD', str(text or '').strip().lower())
    normalized = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
    return re.sub(r'\s+', ' ', normalized)


def _agrupar_top_registros(registros, campo: str, *, valor_field: str | None = None) -> list[dict]:
    agrupado: dict[str, dict] = {}
    for item in registros:
        chave = _normalizar_texto_analitico(getattr(item, campo, '') or 'NAO INFORMADO')
        if not chave:
            chave = 'NAO INFORMADO'
        agrupado.setdefault(chave, {
            'nome': chave,
            'quantidade': 0,
            'valor_realizado': 0.0,
        })
        agrupado[chave]['quantidade'] += 1
        if valor_field:
            agrupado[chave]['valor_realizado'] += float(getattr(item, valor_field, 0) or 0)

    return sorted(
        agrupado.values(),
        key=lambda registro: (registro['quantidade'], registro['valor_realizado'], registro['nome']),
        reverse=True,
    )


def _primeiro_ranking_disponivel(*listas) -> dict | None:
    for lista in listas:
        if isinstance(lista, list) and lista:
            primeiro = lista[0]
            if isinstance(primeiro, dict) and primeiro.get('nome'):
                return primeiro
    return None


def _formatar_moeda_brl(valor: float) -> str:
    texto = f'{float(valor or 0):,.2f}'
    return 'R$ ' + texto.replace(',', 'X').replace('.', ',').replace('X', '.')


def _obter_valor_registro(registro: dict) -> float:
    if 'valor_presente' in registro:
        return float(registro.get('valor_presente') or 0)
    return float(registro.get('valor') or 0)


def _dataset_principal_pergunta(question: str, context: dict) -> str:
    pergunta = _normalizar_pergunta_analitica(question)
    pagina = str(context.get('pagina_atual') or '').strip().lower()
    if any(termo in pergunta for termo in ('inadimplencia', 'relacionamento', 'contas a receber', 'tipo de contato', 'responsavel', 'responsável')):
        return 'inadimplencia'
    if any(termo in pergunta for termo in ('master', 'objetivo geral', 'frente', 'cards do master')):
        return 'master'
    if any(termo in pergunta for termo in ('meta', 'metas', 'planejado', 'atingimento', 'prazo')):
        if pagina == 'painel_inadimplencia':
            return 'inadimplencia'
        if pagina == 'painel_master':
            return 'master'
    if (
        ('varejo' in pergunta and 'investidor' in pergunta)
        or 'contando vendas varejo e vendas investidor' in pergunta
        or 'somando vendas varejo e vendas investidor' in pergunta
    ):
        return 'consolidado'
    if 'investidor' in pergunta:
        return 'investidores'
    if 'vendas varejo' in pergunta or 'varejo' in pergunta or 'venda' in pergunta:
        return 'vendas'
    if pagina == 'painel_investidores':
        return 'investidores'
    if pagina == 'painel_vendas':
        return 'vendas'
    if pagina == 'painel_inadimplencia':
        return 'inadimplencia'
    if pagina == 'painel_master':
        return 'master'
    return 'vendas'


def _registros_contexto_consulta(question: str, context: dict) -> tuple[list[dict], str]:
    painel = context.get('contexto_painel') or {}
    dados = context.get('dados') or {}
    dataset = _dataset_principal_pergunta(question, context)

    if dataset == 'investidores':
        return list(painel.get('registros') or dados.get('investidores') or []), 'investidores'
    if dataset == 'inadimplencia':
        return list(painel.get('registros_detalhados_periodo') or dados.get('inadimplencia') or []), 'inadimplencia'
    if dataset == 'master':
        return list(dados.get('vendas') or []) + list(dados.get('investidores') or []) + list(dados.get('inadimplencia') or []), 'master'
    if dataset == 'consolidado':
        return list(dados.get('vendas') or []) + list(dados.get('investidores') or []), 'consolidado'
    return list(painel.get('registros') or dados.get('vendas') or []), 'vendas'


def _listar_status_contexto(registros: list[dict], context: dict) -> list[str]:
    candidatos = set()
    for registro in registros:
        situacao = str(registro.get('situacao') or '').strip()
        if situacao:
            candidatos.add(situacao)
    painel = context.get('contexto_painel') or {}
    for origem in (painel.get('situacoes'), painel.get('situacoes_funil')):
        if isinstance(origem, dict):
            candidatos.update(str(chave) for chave in origem.keys())
    return sorted(candidatos, key=lambda item: len(_normalizar_pergunta_analitica(item)), reverse=True)


def _extrair_status_registros(question: str, registros: list[dict], context: dict) -> str:
    pergunta = _normalizar_pergunta_analitica(question)
    for status in _listar_status_contexto(registros, context):
        status_normalizado = _normalizar_pergunta_analitica(status)
        if status_normalizado and status_normalizado in pergunta:
            return status
    return str(((context.get('contexto_painel') or {}).get('filtros_aplicados') or {}).get('situacao') or '').strip()


def _filtrar_registros_por_status(registros: list[dict], status: str) -> list[dict]:
    status_normalizado = _normalizar_texto_analitico(status)
    if not status_normalizado:
        return registros
    return [
        registro for registro in registros
        if _normalizar_texto_analitico(registro.get('situacao')) == status_normalizado
    ]


def _campos_dimensionais_contexto(registros: list[dict], context: dict) -> tuple[str, ...]:
    base = ['empreendimento', 'imobiliaria', 'corretor', 'cliente', 'unidade', 'reserva', 'situacao']
    pagina = str(context.get('pagina_atual') or '').strip().lower()
    if pagina in {'painel_vendas', 'painel_investidores', 'painel_master'}:
        base.extend(['tipo_venda', 'bloco', 'criado_por'])
    if pagina == 'painel_inadimplencia':
        base.extend(['responsavel', 'tipo_contato', 'semana', 'telefone', 'email_cliente'])
    campos_presentes = []
    for campo in base:
        if any(str(registro.get(campo) or '').strip() for registro in registros):
            campos_presentes.append(campo)
    return tuple(dict.fromkeys(campos_presentes))


def _agrupar_registros_dict(registros: list[dict], campo: str) -> list[dict]:
    agrupado: dict[str, dict] = {}
    for registro in registros:
        nome = _normalizar_texto_analitico(registro.get(campo) or 'NAO INFORMADO')
        agrupado.setdefault(nome, {'nome': nome, 'quantidade': 0, 'valor_realizado': 0.0})
        agrupado[nome]['quantidade'] += 1
        agrupado[nome]['valor_realizado'] += _obter_valor_registro(registro)
    return sorted(
        agrupado.values(),
        key=lambda item: (item['quantidade'], item['valor_realizado'], item['nome']),
        reverse=True,
    )


def _tokenizar_analitico(texto: str) -> list[str]:
    tokens = re.findall(r'[a-z0-9]+', _normalizar_pergunta_analitica(texto))
    stopwords = {
        'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'para', 'com', 'sem',
        'qual', 'quais', 'quem', 'mais', 'fez', 'fazer', 'vendeu', 'vendas', 'venda',
        'maior', 'numero', 'total', 'valor', 'contando', 'somando',
        'corretor', 'corretores', 'empreendimento', 'empreendimentos',
        'cliente', 'clientes', 'unidade', 'unidades', 'reserva', 'reservas',
        'situacao', 'situacoes', 'status', 'registro', 'registros',
        'imobiliaria', 'imobiliario', 'imobiliarios', 'imoveis', 'imovel',
        'negocios', 'negocio', 'consultoria', 'solucoes', 'solucao', 'ltda',
    }
    return [token for token in tokens if len(token) >= 4 and token not in stopwords]


def _extrair_valores_mencionados(question: str, registros: list[dict], campo: str, limite: int = 400) -> list[str]:
    pergunta = _normalizar_pergunta_analitica(question)
    tokens_pergunta = set(_tokenizar_analitico(question))
    candidatos = []
    vistos = set()
    for registro in registros[:limite]:
        valor = str(registro.get(campo) or '').strip()
        if not valor:
            continue
        normalizado = _normalizar_pergunta_analitica(valor)
        if len(normalizado) < 3 or normalizado in vistos:
            continue
        vistos.add(normalizado)
        candidatos.append((valor, normalizado))

    candidatos.sort(key=lambda item: len(item[1]), reverse=True)
    encontrados = [valor for valor, normalizado in candidatos if normalizado in pergunta]
    if encontrados:
        return encontrados

    exige_multiplos_tokens = campo in {'corretor', 'cliente', 'unidade', 'reserva'}
    if exige_multiplos_tokens and len(tokens_pergunta) < 2:
        return []

    correspondencias_parciais = []
    for valor, _ in candidatos:
        tokens_valor = set(_tokenizar_analitico(valor))
        if tokens_valor and tokens_pergunta and tokens_pergunta.issubset(tokens_valor):
            correspondencias_parciais.append(valor)
    return correspondencias_parciais


def _interpretar_pergunta_analitica(question: str, context: dict) -> dict:
    pergunta = _normalizar_pergunta_analitica(question)
    dataset = _dataset_principal_pergunta(question, context)
    fala_de_extremo_maior = any(termo in pergunta for termo in ('mais cara', 'mais caro', 'maior valor'))
    fala_de_extremo_menor = any(termo in pergunta for termo in ('mais barata', 'mais barato', 'menor valor'))

    metrica = 'quantidade'
    if any(termo in pergunta for termo in ('valor', 'faturamento', 'receita', 'soma', 'ticket')):
        metrica = 'valor'
    if any(termo in pergunta for termo in ('ticket medio', 'ticket médio', 'media', 'média')):
        metrica = 'media'
    if any(termo in pergunta for termo in ('percentual', 'participacao', 'participação', 'share')):
        metrica = 'percentual'

    intencao = 'analise'
    if any(termo in pergunta for termo in ('liste', 'listar', 'quais', 'me mande', 'mostre todas', 'mostre todos')):
        intencao = 'listagem'
    if any(termo in pergunta for termo in ('qual', 'quem', 'maior', 'mais', 'lider', 'lidera')):
        intencao = 'ranking'
    if any(termo in pergunta for termo in ('quanto', 'qual valor', 'valor total', 'total', 'soma', 'somando')):
        intencao = 'agregacao'
    if any(termo in pergunta for termo in ('compare', 'comparativo', 'comparar', 'diferenca', 'diferença')):
        intencao = 'comparacao'
    if any(termo in pergunta for termo in ('por que', 'porque', 'tendencia', 'tendência', 'gargalo', 'oportunidade')):
        intencao = 'analise'
    if fala_de_extremo_maior or fala_de_extremo_menor:
        intencao = 'extremo'

    dimensao = ''
    aliases_dimensao = (
        ('imobiliaria', ('imobiliaria', 'imobiliária')),
        ('corretor', ('corretor',)),
        ('empreendimento', ('empreendimento',)),
        ('situacao', ('situacao', 'situação', 'status')),
        ('cliente', ('cliente',)),
        ('unidade', ('unidade',)),
        ('reserva', ('reserva',)),
        ('responsavel', ('responsavel', 'responsável')),
        ('tipo_contato', ('tipo de contato', 'contato')),
        ('semana', ('semana',)),
        ('tipo_venda', ('tipo de venda',)),
    )
    for campo, termos in aliases_dimensao:
        if any(termo in pergunta for termo in termos):
            dimensao = campo
            break
    if not dimensao and intencao == 'ranking':
        dimensao = 'empreendimento'

    return {
        'dataset_alvo': dataset,
        'intencao_principal': intencao,
        'metrica_principal': metrica,
        'dimensao_principal': dimensao,
        'operacao_extrema': 'max' if fala_de_extremo_maior else 'min' if fala_de_extremo_menor else '',
        'fala_de_meta': any(termo in pergunta for termo in ('meta', 'metas', 'planejado', 'atingimento', 'prazo')),
        'fala_de_venda': any(
            termo in pergunta for termo in (
                'vendeu',
                'vendas',
                'fez mais vendas',
                'mais fez vendas',
                'qual imobiliaria fez mais vendas',
                'qual corretor fez mais vendas',
                'qual empreendimento mais vendeu',
            )
        ),
    }


def _detectar_status_implicito(question: str, interpretacao: dict) -> str:
    pergunta = _normalizar_pergunta_analitica(question)
    if interpretacao.get('fala_de_venda'):
        return 'VENDIDA'
    if 'cancelad' in pergunta:
        return 'CANCELADA'
    if 'pendente de assinatura' in pergunta:
        return 'PENDENTE DE ASSINATURA'
    if 'contrato assinado' in pergunta:
        return 'CONTRATO ASSINADO CLIENTES'
    return ''


def _filtrar_registros_pergunta(question: str, registros: list[dict], context: dict) -> tuple[list[dict], dict]:
    interpretacao = _interpretar_pergunta_analitica(question, context)
    campos_dimensionais = _campos_dimensionais_contexto(registros, context)
    filtros_detectados = {
        'situacao': _extrair_status_registros(question, registros, context),
    }
    for campo in campos_dimensionais:
        if campo == 'situacao':
            continue
        filtros_detectados[campo] = _extrair_valores_mencionados(question, registros, campo)

    filtrados = registros[:]
    status_implicito = _detectar_status_implicito(question, interpretacao)

    if filtros_detectados['situacao']:
        filtrados = _filtrar_registros_por_status(filtrados, filtros_detectados['situacao'])
    elif status_implicito:
        filtros_detectados['situacao'] = status_implicito
        filtrados = _filtrar_registros_por_status(filtrados, status_implicito)

    for campo in campos_dimensionais:
        if campo == 'situacao':
            continue
        valores = filtros_detectados[campo]
        if not valores:
            continue
        normalizados = {_normalizar_texto_analitico(valor) for valor in valores}
        filtrados = [
            registro for registro in filtrados
            if _normalizar_texto_analitico(registro.get(campo)) in normalizados
        ]

    return filtrados, filtros_detectados


def _calcular_metricas_consulta(registros: list[dict]) -> dict:
    total_valor = round(sum(_obter_valor_registro(registro) for registro in registros), 2)
    total_registros = len(registros)
    return {
        'total_registros': total_registros,
        'valor_total': total_valor,
        'ticket_medio': round((total_valor / total_registros), 2) if total_registros else 0.0,
    }


def _ranking_principal_por_dimensao(registros: list[dict], dimensao: str, metrica: str) -> dict:
    if not dimensao:
        return {}
    ranking = _agrupar_registros_dict(registros, dimensao)
    if not ranking:
        return {}
    return {
        'dimensao': dimensao,
        'ordenado_por': 'valor_realizado' if metrica in {'valor', 'media', 'percentual'} else 'quantidade',
        'lider': ranking[0],
        'top_10': ranking[:10],
    }


def _registro_extremo_por_valor(registros: list[dict], operacao: str) -> dict:
    if not registros or operacao not in {'max', 'min'}:
        return {}
    seletor = max if operacao == 'max' else min
    escolhido = seletor(registros, key=_obter_valor_registro)
    return {
        'operacao': operacao,
        'valor': round(_obter_valor_registro(escolhido), 2),
        'registro': escolhido,
    }


def _comparativos_sistema(context: dict) -> dict:
    resumos = context.get('resumos') or {}
    painel = context.get('contexto_painel') or {}
    master_cards = painel.get('cards_master') or []
    return {
        'vendas_varejo': {
            'total_vendidas': int((resumos.get('vendas') or {}).get('total_vendidas') or 0),
            'valor_realizado': float((resumos.get('vendas') or {}).get('valor_realizado') or 0),
        },
        'investidores': {
            'total_vendidas': int((resumos.get('investidores') or {}).get('total_vendidas') or 0),
            'valor_realizado': float((resumos.get('investidores') or {}).get('valor_realizado') or 0),
        },
        'inadimplencia': {
            'total_convertidos': int((resumos.get('inadimplencia') or {}).get('total_convertidos') or 0),
            'valor_realizado': float((resumos.get('inadimplencia') or {}).get('valor_realizado') or 0),
        },
        'master': [
            {
                'frente': card.get('frente') or card.get('nome'),
                'percentual': float(card.get('percentual') or 0),
                'realizado': float(card.get('realizado') or 0),
                'meta': float(card.get('meta') or 0),
            }
            for card in master_cards
        ],
    }


def _catalogar_perguntas_previsiveis(context: dict) -> dict:
    pagina = str(context.get('pagina_atual') or '').strip().lower()
    base = {
        'ranking': [
            'Qual imobiliaria mais vendeu?',
            'Qual corretor mais vendeu?',
            'Qual empreendimento teve maior volume?',
        ],
        'totais': [
            'Qual o valor total do recorte atual?',
            'Quantos registros existem no filtro atual?',
            'Qual o ticket medio?',
        ],
        'extremos': [
            'Qual a unidade mais cara vendida?',
            'Qual a unidade mais barata?',
            'Qual o maior valor encontrado?',
        ],
        'listagens': [
            'Quais unidades foram consideradas nesse calculo?',
            'Liste os registros com determinado status.',
        ],
        'comparacoes': [
            'Compare imobiliarias, corretores e empreendimentos.',
            'Qual modulo performou melhor?',
        ],
    }
    por_pagina = {
        'painel_vendas': [
            'Qual status tem mais registros?',
            'Qual tipo de venda performa melhor?',
            'Quem lidera vendas por imobiliaria, corretor e empreendimento?',
        ],
        'painel_investidores': [
            'Qual empreendimento lidera investidores vendidos?',
            'Qual imobiliaria tem maior valor em investidores?',
        ],
        'painel_inadimplencia': [
            'Qual responsavel converteu mais?',
            'Qual tipo de contato gera mais valor?',
            'Qual semana ficou mais distante da meta?',
        ],
        'painel_master': [
            'Qual frente esta mais avancada no trimestre?',
            'Qual frente esta mais atrasada?',
            'Qual area concentra mais valor realizado?',
        ],
    }
    return {
        'pagina_atual': pagina,
        'categorias_gerais': base,
        'perguntas_especificas_da_pagina': por_pagina.get(pagina, []),
    }


def _montar_consulta_orientada(question: str, context: dict) -> dict:
    interpretacao = _interpretar_pergunta_analitica(question, context)
    registros, dataset = _registros_contexto_consulta(question, context)
    registros = list(registros or [])
    filtrados, filtros_detectados = _filtrar_registros_pergunta(question, registros, context)
    tem_filtros_detectados = any(
        bool(valor) for valor in filtros_detectados.values()
    )
    base = filtrados if (filtrados or tem_filtros_detectados) else registros
    contexto_painel = context.get('contexto_painel') or {}
    metricas = _calcular_metricas_consulta(base)
    ranking_principal = _ranking_principal_por_dimensao(
        base,
        interpretacao.get('dimensao_principal') or 'empreendimento',
        interpretacao.get('metrica_principal') or 'quantidade',
    )
    registro_extremo = _registro_extremo_por_valor(base, interpretacao.get('operacao_extrema') or '')

    return {
        'dataset_consultado': dataset,
        'pagina_atual': context.get('pagina_atual'),
        'interpretacao': interpretacao,
        'filtros_ativos_da_pagina': contexto_painel.get('filtros_aplicados') or {},
        'filtros_detectados_na_pergunta': filtros_detectados,
        'resumo_base': {
            'total_registros_no_contexto': len(registros),
            'total_registros_correspondentes': metricas['total_registros'],
            'valor_total_correspondente': metricas['valor_total'],
            'ticket_medio_correspondente': metricas['ticket_medio'],
        },
        'comparativos_sistema': _comparativos_sistema(context),
        'ranking_principal': ranking_principal,
        'registro_extremo': registro_extremo,
        'top_situacoes_correspondentes': _agrupar_registros_dict(base, 'situacao')[:10],
        'top_empreendimentos_correspondentes': _agrupar_registros_dict(base, 'empreendimento')[:10],
        'top_imobiliarias_correspondentes': _agrupar_registros_dict(base, 'imobiliaria')[:10],
        'top_corretores_correspondentes': _agrupar_registros_dict(base, 'corretor')[:10],
        'top_responsaveis_correspondentes': _agrupar_registros_dict(base, 'responsavel')[:10] if any('responsavel' in registro for registro in base) else [],
        'top_tipos_contato_correspondentes': _agrupar_registros_dict(base, 'tipo_contato')[:10] if any('tipo_contato' in registro for registro in base) else [],
        'amostra_registros_correspondentes': base[:20],
        'registros_correspondentes': base[:50],
    }


def _extrair_status_mencionado(question: str, context: dict) -> str:
    registros, _ = _registros_contexto_consulta(question, context)
    return _extrair_status_registros(question, registros, context)


def _responder_consulta_banco_deterministica(question: str, context: dict) -> str | None:
    pergunta = _normalizar_pergunta_analitica(question)
    registros, dataset = _registros_contexto_consulta(question, context)
    if not registros:
        return None

    status_mencionado = _extrair_status_registros(question, registros, context)
    fala_de_valor_total = (
        'valor total' in pergunta
        or 'valor das vendas' in pergunta
        or 'total das vendas' in pergunta
        or 'valor dos investidores' in pergunta
        or 'valor das unidades' in pergunta
        or 'valor total das unidades' in pergunta
        or ('qual valor' in pergunta and 'situacao' in pergunta)
    )
    fala_de_lideranca = any(
        termo in pergunta for termo in (
            'mais vendeu',
            'maior numero',
            'maior numero de vendas',
            'mais fez vendas',
            'fez mais vendas',
            'mais vendas',
            'lider',
            'lidera',
        )
    )
    fala_de_listagem_unidades = (
        'todas as unidades' in pergunta
        or 'quais unidades' in pergunta
        or 'mande as unidades' in pergunta
        or 'me mande todas as unidades' in pergunta
        or 'liste as unidades' in pergunta
        or ('unidades' in pergunta and 'contabilizou' in pergunta)
    )
    campo = (
        'imobiliaria' if 'imobiliaria' in pergunta else
        'corretor' if 'corretor' in pergunta else
        'empreendimento' if 'empreendimento' in pergunta else
        ''
    )

    if fala_de_listagem_unidades:
        registros_base = _filtrar_registros_por_status(registros, status_mencionado) if status_mencionado else registros
        if not registros_base:
            return 'Nao encontrei unidades para os filtros informados.'
        linhas = []
        for registro in registros_base:
            unidade = registro.get('unidade') or 'NAO INFORMADA'
            empreendimento = registro.get('empreendimento') or 'NAO INFORMADO'
            valor = _formatar_moeda_brl(_obter_valor_registro(registro))
            linhas.append(f'empreendimento: {empreendimento}, unidade: {unidade}, valor: {valor}')
        cabecalho = (
            f'As unidades contabilizadas com a situacao {status_mencionado} sao: '
            if status_mencionado else
            'As unidades contabilizadas sao: '
        )
        return cabecalho + ' | '.join(linhas)

    if fala_de_valor_total:
        registros_base = _filtrar_registros_por_status(registros, status_mencionado) if status_mencionado else registros
        valor_total = sum(_obter_valor_registro(registro) for registro in registros_base)
        if dataset == 'investidores':
            if status_mencionado:
                return f'O valor total dos investidores com status {status_mencionado} e de {_formatar_moeda_brl(valor_total)}.'
            return f'O valor total dos investidores e de {_formatar_moeda_brl(valor_total)}.'
        if dataset == 'consolidado':
            if status_mencionado:
                return f'O valor total somando vendas varejo e investidores com status {status_mencionado} e de {_formatar_moeda_brl(valor_total)}.'
            return f'O valor total somando vendas varejo e investidores e de {_formatar_moeda_brl(valor_total)}.'
        if status_mencionado:
            return f'O valor total das vendas com status {status_mencionado} e de {_formatar_moeda_brl(valor_total)}.'
        return f'O valor total das vendas e de {_formatar_moeda_brl(valor_total)}.'

    if fala_de_lideranca and campo:
        registros_base = registros
        if status_mencionado:
            registros_base = _filtrar_registros_por_status(registros_base, status_mencionado)
        elif dataset in {'vendas', 'investidores', 'consolidado'}:
            registros_base = _filtrar_registros_por_status(registros_base, 'VENDIDA')
        top = _primeiro_ranking_disponivel(_agrupar_registros_dict(registros_base, campo))
        if not top:
            return None

        if campo == 'imobiliaria' and dataset == 'investidores':
            return f'A imobiliaria que mais vendeu em investidores foi {top["nome"]}, com {int(top["quantidade"])} investidores vendidos.'
        if campo == 'imobiliaria' and dataset == 'consolidado':
            return f'A imobiliaria que mais vendeu somando vendas varejo e investidores foi {top["nome"]}, com {int(top["quantidade"])} vendas.'
        if campo == 'imobiliaria':
            return f'A imobiliaria que mais vendeu no varejo foi {top["nome"]}, com {int(top["quantidade"])} vendas.'
        if campo == 'corretor' and dataset == 'investidores':
            return f'O corretor com maior numero de investidores vendidos foi {top["nome"]}, com {int(top["quantidade"])} investidores vendidos.'
        if campo == 'corretor':
            return f'O corretor com maior numero de vendas foi {top["nome"]}, com {int(top["quantidade"])} vendas.'
        if campo == 'empreendimento' and dataset == 'investidores':
            return f'O empreendimento com maior numero de investidores vendidos foi {top["nome"]}, com {int(top["quantidade"])} investidores vendidos.'
        return f'O empreendimento com maior numero de vendas foi {top["nome"]}, com {int(top["quantidade"])} vendas.'

    return None


def _responder_ranking_deterministico(question: str, context: dict) -> str | None:
    pergunta = _normalizar_pergunta_analitica(question)
    if not pergunta:
        return None

    termos_lideranca = (
        'mais vendeu',
        'maior numero',
        'maior numero de vendas',
        'mais fez vendas',
        'fez mais vendas',
        'mais vendas',
        'lider',
        'lidera',
    )
    if not any(termo in pergunta for termo in termos_lideranca):
        return None

    painel = context.get('contexto_painel') or {}
    resumos = context.get('resumos') or {}
    pagina = str(context.get('pagina_atual') or '').strip().lower()

    fala_de_imobiliaria = 'imobiliaria' in pergunta
    fala_de_empreendimento = 'empreendimento' in pergunta
    fala_de_corretor = 'corretor' in pergunta
    fala_de_investidor = 'investidor' in pergunta
    fala_de_varejo = 'varejo' in pergunta or 'vendas varejo' in pergunta
    fala_de_ambos = (
        ('varejo' in pergunta and 'investidor' in pergunta)
        or 'contando vendas varejo e vendas investidor' in pergunta
        or 'somando vendas varejo e vendas investidor' in pergunta
    )

    if fala_de_imobiliaria and fala_de_ambos:
        top = _primeiro_ranking_disponivel(
            (((resumos.get('consolidado_comercial') or {}).get('top_imobiliarias_vendidas'))),
        )
        if top:
            return f'A imobiliaria que mais vendeu somando vendas varejo e investidores foi {top["nome"]}, com {int(top["quantidade"])} vendas.'

    if fala_de_empreendimento:
        if fala_de_investidor or pagina == 'painel_investidores':
            top = _primeiro_ranking_disponivel(
                painel.get('top_empreendimentos_vendidos'),
                ((resumos.get('investidores') or {}).get('top_empreendimentos_vendidos')),
            )
            if top:
                return f'O empreendimento com maior numero de investidores vendidos foi {top["nome"]}, com {int(top["quantidade"])} investidores vendidos.'
        if fala_de_varejo or pagina == 'painel_vendas':
            top = _primeiro_ranking_disponivel(
                painel.get('top_empreendimentos_vendidos'),
                ((resumos.get('vendas') or {}).get('top_empreendimentos_vendidos')),
            )
            if top:
                return f'O empreendimento com maior numero de vendas no varejo foi {top["nome"]}, com {int(top["quantidade"])} vendas.'
        top = _primeiro_ranking_disponivel(
            painel.get('top_empreendimentos_vendidos'),
            ((resumos.get('consolidado_comercial') or {}).get('top_empreendimentos_vendidos')),
            ((resumos.get('vendas') or {}).get('top_empreendimentos_vendidos')),
            ((resumos.get('investidores') or {}).get('top_empreendimentos_vendidos')),
        )
        if top:
            return f'O empreendimento com maior numero de vendas foi {top["nome"]}, com {int(top["quantidade"])} vendas.'

    if fala_de_imobiliaria:
        if fala_de_investidor or pagina == 'painel_investidores':
            top = _primeiro_ranking_disponivel(
                painel.get('top_imobiliarias_vendidas'),
                ((resumos.get('investidores') or {}).get('top_imobiliarias_vendidas')),
            )
            if top:
                return f'A imobiliaria que mais vendeu em investidores foi {top["nome"]}, com {int(top["quantidade"])} investidores vendidos.'
        if fala_de_varejo or pagina == 'painel_vendas':
            top = _primeiro_ranking_disponivel(
                painel.get('top_imobiliarias_vendidas'),
                ((resumos.get('vendas') or {}).get('top_imobiliarias_vendidas')),
            )
            if top:
                return f'A imobiliaria que mais vendeu no varejo foi {top["nome"]}, com {int(top["quantidade"])} vendas.'

    if fala_de_corretor:
        if fala_de_investidor or pagina == 'painel_investidores':
            top = _primeiro_ranking_disponivel(
                painel.get('top_corretores_vendidos'),
                ((resumos.get('investidores') or {}).get('top_corretores_vendidos')),
            )
            if top:
                return f'O corretor com maior numero de investidores vendidos foi {top["nome"]}, com {int(top["quantidade"])} investidores vendidos.'
        if fala_de_varejo or pagina == 'painel_vendas':
            top = _primeiro_ranking_disponivel(
                painel.get('top_corretores_vendidos'),
                ((resumos.get('vendas') or {}).get('top_corretores_vendidos')),
            )
            if top:
                return f'O corretor com maior numero de vendas no varejo foi {top["nome"]}, com {int(top["quantidade"])} vendas.'

    return None


def _responder_total_deterministico(question: str, context: dict) -> str | None:
    pergunta = _normalizar_pergunta_analitica(question)
    if 'valor total' not in pergunta and 'valor das vendas' not in pergunta and 'total das vendas' not in pergunta:
        return None

    painel = context.get('contexto_painel') or {}
    pagina = str(context.get('pagina_atual') or '').strip().lower()
    status_mencionado = _extrair_status_mencionado(question, context)
    resumo_filtrado = painel.get('resumo_filtrado') or {}

    if pagina == 'painel_vendas' and status_mencionado:
        filtros = painel.get('filtros_aplicados') or {}
        if _normalizar_texto_analitico(filtros.get('situacao')) == _normalizar_texto_analitico(status_mencionado):
            valor = float(resumo_filtrado.get('valor_total_registros') or 0)
            return f'O valor total das vendas com status {status_mencionado} e de {_formatar_moeda_brl(valor)}.'

    if pagina == 'painel_investidores' and status_mencionado:
        filtros = painel.get('filtros_aplicados') or {}
        if _normalizar_texto_analitico(filtros.get('situacao')) == _normalizar_texto_analitico(status_mencionado):
            valor = float(resumo_filtrado.get('valor_total_registros') or 0)
            return f'O valor total dos investidores com status {status_mencionado} e de {_formatar_moeda_brl(valor)}.'

    return None


def _compact_context_for_prompt(context: dict) -> dict:
    contexto_painel = context.get('contexto_painel') or {}
    resumos = context.get('resumos') or {}
    dados = context.get('dados') or {}
    return {
        'pagina_atual': context.get('pagina_atual'),
        'gerado_em': context.get('gerado_em'),
        'usuario_atual': context.get('usuario_atual'),
        'sistema': context.get('sistema'),
        'resumos': resumos,
        'contexto_painel': {
            'filtros_aplicados': contexto_painel.get('filtros_aplicados') or {},
            'resumo_filtrado': contexto_painel.get('resumo_filtrado') or {},
            'totais_grid': {
                'registros': len(contexto_painel.get('registros') or []),
                'situacoes': len((contexto_painel.get('situacoes') or {})),
                'situacoes_funil': len((contexto_painel.get('situacoes_funil') or {})),
            },
        },
        'bases_disponiveis': {
            'usuarios': len(dados.get('usuarios') or []),
            'empreendimentos': len(dados.get('empreendimentos') or []),
            'metas_semana': len(dados.get('metas_semana') or []),
            'metas_venda_varejo': len(dados.get('metas_venda_varejo') or []),
            'metas_venda_investidor': len(dados.get('metas_venda_investidor') or []),
            'vendas': len(dados.get('vendas') or []),
            'investidores': len(dados.get('investidores') or []),
            'inadimplencia': len(dados.get('inadimplencia') or []),
        },
        'perguntas_previsiveis': _catalogar_perguntas_previsiveis(context),
    }


def _extrair_moedas_resposta(texto: str) -> list[float]:
    encontrados = re.findall(r'R\\$\\s*([\\d\\.\\,]+)', texto or '', flags=re.IGNORECASE)
    valores = []
    for bruto in encontrados:
        try:
            valores.append(float(bruto.replace('.', '').replace(',', '.')))
        except ValueError:
            continue
    return valores


def _resposta_canonica_da_consulta(question: str, consulta_orientada: dict) -> str | None:
    interpretacao = consulta_orientada.get('interpretacao') or {}
    resumo = consulta_orientada.get('resumo_base') or {}
    ranking_principal = consulta_orientada.get('ranking_principal') or {}
    registro_extremo = consulta_orientada.get('registro_extremo') or {}
    registros = consulta_orientada.get('registros_correspondentes') or []
    filtros = consulta_orientada.get('filtros_detectados_na_pergunta') or {}
    dataset = consulta_orientada.get('dataset_consultado') or 'vendas'
    pergunta = _normalizar_pergunta_analitica(question)

    if interpretacao.get('intencao_principal') == 'extremo' and registro_extremo.get('registro'):
        registro = registro_extremo['registro']
        valor = _formatar_moeda_brl(registro_extremo.get('valor') or 0)
        rotulo = 'mais cara' if interpretacao.get('operacao_extrema') == 'max' else 'mais barata'
        if 'unidade' in pergunta:
            complemento = ''
            if registro.get('empreendimento'):
                complemento += f' do empreendimento {registro["empreendimento"]}'
            if registro.get('unidade'):
                complemento += f', unidade {registro["unidade"]}'
            return f'O valor da unidade {rotulo}{complemento} foi de {valor}.'
        return f'O {"maior" if interpretacao.get("operacao_extrema") == "max" else "menor"} valor encontrado foi de {valor}.'

    if interpretacao.get('intencao_principal') == 'agregacao' and interpretacao.get('metrica_principal') == 'valor':
        status = filtros.get('situacao')
        sujeito = 'dos investidores' if dataset == 'investidores' else 'somando vendas varejo e investidores' if dataset == 'consolidado' else 'das vendas'
        if 'unidade' in pergunta:
            sujeito = 'das unidades'
        if status:
            return f'O valor total {sujeito} com status {status} e de {_formatar_moeda_brl(resumo.get("valor_total_correspondente") or 0)}.'
        return f'O valor total {sujeito} e de {_formatar_moeda_brl(resumo.get("valor_total_correspondente") or 0)}.'

    if interpretacao.get('intencao_principal') == 'ranking' and ranking_principal.get('lider'):
        lider = ranking_principal['lider']
        dimensao = ranking_principal.get('dimensao') or interpretacao.get('dimensao_principal') or 'empreendimento'
        quantidade = int(lider.get('quantidade') or 0)
        rotulo = {
            'imobiliaria': 'A imobiliaria que mais vendeu',
            'corretor': 'O corretor com maior numero de vendas',
            'empreendimento': 'O empreendimento com maior numero de vendas',
            'situacao': 'A situacao com maior volume',
            'responsavel': 'O responsavel com maior volume',
            'tipo_contato': 'O tipo de contato com maior volume',
            'tipo_venda': 'O tipo de venda com maior volume',
        }.get(dimensao, 'O lider do ranking')
        unidade = 'vendas' if filtros.get('situacao') == 'VENDIDA' or interpretacao.get('fala_de_venda') else 'registros'
        if dataset == 'inadimplencia' and dimensao in {'responsavel', 'tipo_contato', 'situacao', 'empreendimento'}:
            unidade = 'registros'
        return f'{rotulo} foi {lider.get("nome")}, com {quantidade} {unidade}.'

    if interpretacao.get('intencao_principal') == 'comparacao':
        comparativos = consulta_orientada.get('comparativos_sistema') or {}
        vendas = comparativos.get('vendas_varejo') or {}
        investidores = comparativos.get('investidores') or {}
        if vendas or investidores:
            return (
                f'No consolidado, vendas varejo somam {int(vendas.get("total_vendidas") or 0)} vendas e '
                f'{_formatar_moeda_brl(vendas.get("valor_realizado") or 0)}, enquanto investidores somam '
                f'{int(investidores.get("total_vendidas") or 0)} vendas e '
                f'{_formatar_moeda_brl(investidores.get("valor_realizado") or 0)}.'
            )

    if interpretacao.get('intencao_principal') == 'listagem' and registros:
        linhas = []
        for registro in registros:
            partes = []
            if registro.get('empreendimento'):
                partes.append(f'empreendimento: {registro["empreendimento"]}')
            if registro.get('unidade'):
                partes.append(f'unidade: {registro["unidade"]}')
            if registro.get('reserva'):
                partes.append(f'reserva: {registro["reserva"]}')
            partes.append(f'valor: {_formatar_moeda_brl(_obter_valor_registro(registro))}')
            linhas.append(', '.join(partes))
        return ' | '.join(linhas)

    return None


def _validar_resposta_analitica(question: str, resposta: str, consulta_orientada: dict) -> str:
    resposta_limpa = _sanitize_response(resposta or '')
    interpretacao = consulta_orientada.get('interpretacao') or {}
    resumo = consulta_orientada.get('resumo_base') or {}
    ranking_principal = consulta_orientada.get('ranking_principal') or {}
    registro_extremo = consulta_orientada.get('registro_extremo') or {}
    canonica = _resposta_canonica_da_consulta(question, consulta_orientada)

    if not resposta_limpa:
        return canonica or 'Nao foi possivel gerar uma resposta com base nos dados informados.'

    if interpretacao.get('intencao_principal') == 'extremo' and registro_extremo.get('registro'):
        valor_canonico = round(float(registro_extremo.get('valor') or 0), 2)
        valores_resposta = _extrair_moedas_resposta(resposta_limpa)
        if not valores_resposta or all(round(valor, 2) != valor_canonico for valor in valores_resposta):
            return canonica or resposta_limpa

    if interpretacao.get('intencao_principal') == 'agregacao' and interpretacao.get('metrica_principal') == 'valor':
        valor_canonico = round(float(resumo.get('valor_total_correspondente') or 0), 2)
        valores_resposta = _extrair_moedas_resposta(resposta_limpa)
        if not valores_resposta or all(round(valor, 2) != valor_canonico for valor in valores_resposta):
            return canonica or resposta_limpa

    if interpretacao.get('intencao_principal') == 'ranking' and ranking_principal.get('lider'):
        lider = ranking_principal['lider']
        nome_lider = str(lider.get('nome') or '').strip().upper()
        quantidade = int(lider.get('quantidade') or 0)
        resposta_maiuscula = resposta_limpa.upper()
        if nome_lider not in resposta_maiuscula or str(quantidade) not in resposta_maiuscula:
            return canonica or resposta_limpa

    if interpretacao.get('intencao_principal') == 'listagem' and '|' not in resposta_limpa and canonica:
        return canonica

    return resposta_limpa


def _fallback_resposta_analitica(question: str, context: dict, consulta_orientada: dict | None = None) -> str:
    consulta = consulta_orientada or _montar_consulta_orientada(question, context)
    resposta = _resposta_canonica_da_consulta(question, consulta)
    if resposta:
        return resposta

    resumo = consulta.get('resumo_base') or {}
    total = int(resumo.get('total_registros_correspondentes') or 0)
    valor = _formatar_moeda_brl(resumo.get('valor_total_correspondente') or 0)
    dataset = consulta.get('dataset_consultado') or 'dados'
    return f'Considerei {total} registros em {dataset}, com valor total de {valor}.'


def fallback_analytics_answer(question: str, context: dict) -> str:
    return _fallback_resposta_analitica(question, context)


def build_global_ai_context(*, page: str, actor=None, extra_context: dict | None = None) -> dict:
    from app.models.empreendimento import Empreendimento
    from app.models.investidor import Investidor
    from app.models.meta import MetaSemana
    from app.models.meta_investidor import MetaInvestidor
    from app.models.meta_venda import MetaVendaVarejo
    from app.models.relacionamento import Relacionamento
    from app.models.user import User
    from app.models.venda import Venda

    extra_context = extra_context or {}

    usuarios = User.query.order_by(User.nome.asc()).all()
    empreendimentos = Empreendimento.query.order_by(Empreendimento.nome.asc()).all()
    metas_semana = MetaSemana.query.order_by(MetaSemana.semana.asc()).all()
    metas_venda = MetaVendaVarejo.query.order_by(MetaVendaVarejo.mes.asc()).all()
    metas_investidor = MetaInvestidor.query.order_by(MetaInvestidor.mes.asc()).all()
    vendas = Venda.query.order_by(Venda.data_reserva.desc(), Venda.id.desc()).all()
    investidores = Investidor.query.order_by(Investidor.data_reserva.desc(), Investidor.id.desc()).all()
    relacionamentos = Relacionamento.query.order_by(Relacionamento.criado_em.desc(), Relacionamento.id.desc()).all()

    vendas_vendidas = [item for item in vendas if (item.situacao or '').upper() == 'VENDIDA']
    investidores_vendidos = [item for item in investidores if (item.situacao or '').upper() == 'VENDIDA']
    relacionamentos_convertidos = [item for item in relacionamentos if (item.situacao or '').upper() == 'SIM']

    return {
        'pagina_atual': page,
        'gerado_em': datetime.now().isoformat(),
        'usuario_atual': {
            'id': getattr(actor, 'id', None),
            'nome': getattr(actor, 'nome', ''),
            'email': getattr(actor, 'email', ''),
            'tipo': getattr(actor, 'tipo', ''),
        },
        'sistema': {
            'usuarios_totais': len(usuarios),
            'usuarios_ativos': sum(1 for item in usuarios if item.ativo),
            'empreendimentos_totais': len(empreendimentos),
            'empreendimentos_ativos': sum(1 for item in empreendimentos if item.ativo),
            'metas_semana_totais': len(metas_semana),
            'metas_venda_totais': len(metas_venda),
            'metas_investidor_totais': len(metas_investidor),
            'vendas_totais': len(vendas),
            'investidores_totais': len(investidores),
            'inadimplencia_total_registros': len(relacionamentos),
        },
        'resumos': {
            'vendas': {
                'total_registros': len(vendas),
                'total_vendidas': len(vendas_vendidas),
                'valor_realizado': round(sum(float(item.valor_presente or 0) for item in vendas_vendidas), 2),
                'top_empreendimentos_vendidos': _agrupar_top_registros(vendas_vendidas, 'empreendimento', valor_field='valor_presente')[:10],
                'top_corretores_vendidos': _agrupar_top_registros(vendas_vendidas, 'corretor', valor_field='valor_presente')[:10],
                'top_imobiliarias_vendidas': _agrupar_top_registros(vendas_vendidas, 'imobiliaria', valor_field='valor_presente')[:10],
            },
            'investidores': {
                'total_registros': len(investidores),
                'total_vendidas': len(investidores_vendidos),
                'valor_realizado': round(sum(float(item.valor_presente or 0) for item in investidores_vendidos), 2),
                'top_empreendimentos_vendidos': _agrupar_top_registros(investidores_vendidos, 'empreendimento', valor_field='valor_presente')[:10],
                'top_corretores_vendidos': _agrupar_top_registros(investidores_vendidos, 'corretor', valor_field='valor_presente')[:10],
                'top_imobiliarias_vendidas': _agrupar_top_registros(investidores_vendidos, 'imobiliaria', valor_field='valor_presente')[:10],
            },
            'inadimplencia': {
                'total_registros': len(relacionamentos),
                'total_convertidos': len(relacionamentos_convertidos),
                'valor_realizado': round(sum(float(item.valor or 0) for item in relacionamentos_convertidos), 2),
            },
            'consolidado_comercial': {
                'top_imobiliarias_vendidas': _agrupar_top_registros(
                    vendas_vendidas + investidores_vendidos,
                    'imobiliaria',
                    valor_field='valor_presente',
                )[:10],
                'top_corretores_vendidos': _agrupar_top_registros(
                    vendas_vendidas + investidores_vendidos,
                    'corretor',
                    valor_field='valor_presente',
                )[:10],
                'top_empreendimentos_vendidos': _agrupar_top_registros(
                    vendas_vendidas + investidores_vendidos,
                    'empreendimento',
                    valor_field='valor_presente',
                )[:10],
            },
        },
        'dados': {
            'usuarios': [
                {
                    'id': item.id,
                    'nome': item.nome,
                    'email': item.email,
                    'tipo': item.tipo,
                    'ativo': bool(item.ativo),
                }
                for item in usuarios
            ],
            'empreendimentos': [
                {
                    'id': item.id,
                    'nome': item.nome,
                    'ativo': bool(item.ativo),
                }
                for item in empreendimentos
            ],
            'metas_semana': [item.to_dict() for item in metas_semana],
            'metas_venda_varejo': [item.to_dict() for item in metas_venda],
            'metas_venda_investidor': [item.to_dict() for item in metas_investidor],
            'vendas': [item.to_dict() for item in vendas],
            'investidores': [item.to_dict() for item in investidores],
            'inadimplencia': [item.to_dict() for item in relacionamentos],
        },
        'contexto_painel': extra_context,
    }


def ask_analytics_assistant(question: str, history: list[dict], context: dict) -> str:
    from google import genai

    style = (os.environ.get('GEMINI_ANALYTICS_STYLE') or DEFAULT_STYLE).strip().lower()
    consulta_orientada = _montar_consulta_orientada(question, context)
    contexto_prompt = _compact_context_for_prompt(context)

    style_map = {
        'executivo': (
            'Priorize clareza, objetividade e decisao. '
            'Resuma achados principais em linguagem de gestao.'
        ),
        'analitico_comercial_financeiro': (
            'Priorize diagnostico analitico, leitura comercial e impacto financeiro ao mesmo tempo. '
            'Relacione conversao, volume, produtividade, valor realizado, gaps de meta, concentracao de resultado '
            'e oportunidades de acao por responsavel, empreendimento ou periodo.'
        ),
        'comercial': (
            'Priorize leitura de performance comercial, conversao, gargalos de funil, '
            'oportunidades por responsavel e por empreendimento.'
        ),
        'financeiro': (
            'Priorize impacto em valor realizado, gaps de meta, concentracao de resultados '
            'e riscos financeiros do periodo.'
        ),
    }
    style_instruction = style_map.get(style, style_map['executivo'])
    brief_mode = _should_be_brief(question)

    history_lines = []
    for item in history[-8:]:
        role = item.get('role')
        content = (item.get('content') or '').strip()
        if role in {'user', 'assistant'} and content:
            prefix = 'Usuario' if role == 'user' else 'Assistente'
            history_lines.append(f'{prefix}: {content}')

    prompt = (
        'Voce se chama Kamille e e a assistente analitica oficial do sistema Sousa Araujo.\n'
        'Voce e uma analista de dados senior.\n'
        'Responda em portugues do Brasil, de forma objetiva, clara e executiva.\n'
        'Responda como uma agente de IA direta e profissional.\n'
        'Nao use saudacoes, nao se apresente e nao use frases como '
        '"Kamille aqui esta o resumo", "segue a analise", "como assistente" ou equivalentes.\n'
        'Comece direto pelo conteudo da resposta.\n'
        'Nao use asteriscos, nao use Markdown e nao formate a resposta com bullets usando simbolos especiais.\n'
        'Nunca exponha nomes internos, nomes tecnicos de campos, chaves de dicionario ou labels de sistema '
        'como valor_realizado, valor_planejado, acoes_realizadas, acoes_planejadas, pct_valor, pct_acoes, '
        'melhor_semana, pior_semana ou nomes parecidos.\n'
        'Sempre traduza os dados para linguagem de negocio. Exemplos corretos: '
        '"Valor Realizado: R$ 0,00", "Valor Planejado: R$ 0,00", "Acoes Realizadas: 0", '
        '"Acoes Planejadas: 0", "Percentual de Valor Realizado: 0,0%".\n'
        'Quando citar dinheiro, use sempre o formato brasileiro com R$ e virgula decimal. '
        'Quando citar percentuais, use o simbolo % com formatacao natural para leitura humana.\n'
        'Considere obrigatoriamente a data atual e o prazo final das metas informados no contexto.\n'
        'Ao falar de prazo, atraso, urgencia, tempo restante ou ritmo necessario, use essas datas como base.\n'
        'Se a pergunta envolver momento atual, progresso esperado ou tempo ate a meta, cite as datas explicitamente.\n'
        'Considere tambem datas e horarios dos registros de clientes presentes no contexto.\n'
        'Quando a pergunta envolver cadencia, horario, sequencia temporal, ultimo registro, primeiro registro '
        'ou concentracao por periodo, use os timestamps dos registros.\n'
        'Voce pode usar qualquer dado presente no contexto consolidado do sistema, mas deve priorizar o contexto estruturado e auditavel em vez de inferencias livres.\n'
        'A secao CONSULTA_ORIENTADA foi gerada diretamente a partir dos dados vivos do banco e do contexto atual da pagina.\n'
        'Para qualquer pergunta factual, numerica, de contagem, soma, ranking, listagem ou comparacao, trate CONSULTA_ORIENTADA como a fonte primaria da verdade.\n'
        'Leia primeiro interpretacao, filtros_ativos_da_pagina, filtros_detectados_na_pergunta, resumo_base, ranking_principal e registros_correspondentes.\n'
        'Use tambem a secao perguntas_previsiveis do contexto compacto como guia de cobertura esperada para vendas, investidores, inadimplencia, metas, master e cruzamentos.\n'
        'Se CONSULTA_ORIENTADA trouxer resumo_base, ranking_principal, rankings auxiliares ou registros_correspondentes, '
        'nao contradiga esses numeros e nao invente valores fora dessa secao.\n'
        'Quando a pergunta envolver empreendimento, corretor, imobiliaria, unidade, cliente, reserva ou situacao, '
        'use primeiro os filtros_detectados_na_pergunta e os registros_correspondentes da CONSULTA_ORIENTADA.\n'
        'Se a resposta envolver lideranca ou maior volume, cite sempre nome e quantidade exata.\n'
        'Se a resposta envolver soma, cite sempre o valor exato com base em valor_total_correspondente quando essa secao estiver disponivel.\n'
        'Se a pergunta pedir listagem, liste apenas os registros_correspondentes da CONSULTA_ORIENTADA.\n'
        'Use apenas o contexto fornecido e os numeros do relatorio.\n'
        'Se algum dado nao estiver presente no contexto, diga isso com clareza.\n'
        'Ao responder, cite os numeros relevantes e destaque tendencias, gargalos, comparacoes '
        'e oportunidades praticas quando fizer sentido.\n'
        f'{style_instruction}\n'
        'Sempre que ajudar a leitura, estruture a resposta em resumo, evidencias e acao recomendada, '
        'mas em texto limpo, sem asteriscos.\n'
        'Se a pergunta for simples, direta e pedir apenas um numero, indicador ou fato objetivo, '
        'responda de forma curta em no maximo 1 frase e 20 palavras. '
        'Nesses casos, entregue primeiro a resposta final e nao explique o calculo, nao acrescente contexto '
        'e nao traga recomendacoes, a menos que o usuario peca isso explicitamente.\n'
        'Exemplo de pergunta simples: "qual o ticket medio dos investidores?". '
        'Exemplo de resposta esperada: "O ticket medio dos investidores e de R$ 228.257,40."\n'
        'Se a pergunta pedir analise, comparacao, causa, tendencia, risco, plano de acao ou detalhamento, '
        'voce pode responder com mais profundidade.\n'
        f'Modo de resposta para esta pergunta: {"curto e direto" if brief_mode else "analitico e detalhado quando necessario"}.\n\n'
        f'CONSULTA_ORIENTADA:\n{json.dumps(consulta_orientada, ensure_ascii=False)}\n\n'
        f'CONTEXTO_ANALITICO_COMPACTO:\n{json.dumps(contexto_prompt, ensure_ascii=False)}\n\n'
        f'Historico recente:\n' + ('\n'.join(history_lines) if history_lines else 'Sem historico anterior.') + '\n\n'
        f'Pergunta atual do usuario:\n{question.strip()}'
    )

    try:
        client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt,
        )
        return _validar_resposta_analitica(question, response.text or '', consulta_orientada)
    except Exception:
        return _fallback_resposta_analitica(question, context, consulta_orientada)
