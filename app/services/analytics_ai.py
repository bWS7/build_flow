import json
import os
import re

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
        'Voce pode usar qualquer dado presente no contexto consolidado do sistema e dos registros, '
        'mas sempre com foco em analise gerencial, comercial e financeira.\n'
        'Use apenas o contexto fornecido e os numeros do relatorio.\n'
        'Se algum dado nao estiver presente no contexto, diga isso com clareza.\n'
        'Ao responder, cite os numeros relevantes e destaque tendencias, gargalos, comparacoes '
        'e oportunidades praticas quando fizer sentido.\n'
        f'{style_instruction}\n'
        'Sempre que ajudar a leitura, estruture a resposta em resumo, evidencias e acao recomendada, '
        'mas em texto limpo, sem asteriscos.\n\n'
        f'Contexto analitico do relatorio:\n{json.dumps(context, ensure_ascii=False)}\n\n'
        f'Historico recente:\n' + ('\n'.join(history_lines) if history_lines else 'Sem historico anterior.') + '\n\n'
        f'Pergunta atual do usuario:\n{question.strip()}'
    )

    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=prompt,
    )
    return _sanitize_response(response.text or '')
