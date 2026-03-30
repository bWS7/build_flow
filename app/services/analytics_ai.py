import json
import os
import re
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
            },
            'investidores': {
                'total_registros': len(investidores),
                'total_vendidas': len(investidores_vendidos),
                'valor_realizado': round(sum(float(item.valor_presente or 0) for item in investidores_vendidos), 2),
            },
            'inadimplencia': {
                'total_registros': len(relacionamentos),
                'total_convertidos': len(relacionamentos_convertidos),
                'valor_realizado': round(sum(float(item.valor or 0) for item in relacionamentos_convertidos), 2),
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

    client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
    style = (os.environ.get('GEMINI_ANALYTICS_STYLE') or DEFAULT_STYLE).strip().lower()

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
        'Voce pode usar qualquer dado presente no contexto consolidado de todo o sistema, de todas as tabelas e de todos os registros enviados, '
        'mas sempre com foco em analise gerencial, comercial e financeira.\n'
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
        f'Contexto analitico do relatorio:\n{json.dumps(context, ensure_ascii=False)}\n\n'
        f'Historico recente:\n' + ('\n'.join(history_lines) if history_lines else 'Sem historico anterior.') + '\n\n'
        f'Pergunta atual do usuario:\n{question.strip()}'
    )

    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=prompt,
    )
    return _sanitize_response(response.text or '')
