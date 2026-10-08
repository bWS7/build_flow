"""
Testes de regressao para o isolamento de metas por trimestre.

O historico do projeto ja teve um bug (corrigido no commit 2801f38) em que a
unicidade antiga de algumas tabelas de meta considerava so a semana, fazendo
uma meta de um trimestre sobrescrever a de outro. Estes testes garantem que
isso nao volta a acontecer, cobrindo tambem o novo q3 (4o Trimestre).
"""
import pytest

from app.models.meta_investidor_semana import MetaInvestidorSemana
from app.models.meta_venda_semana import MetaVendaSemana

ENDPOINTS_DE_META = [
    ('/admin/meta-venda/salvar', MetaVendaSemana, 'quantidade_meta', {'acoes_planejadas': 1}),
    ('/admin/meta-investidor/salvar', MetaInvestidorSemana, 'valor_meta', {'acoes_planejadas': 1}),
]


@pytest.mark.parametrize('endpoint,model,campo_valor,payload_extra', ENDPOINTS_DE_META)
def test_metas_sao_isoladas_por_trimestre(app, client, make_user, login, endpoint, model, campo_valor, payload_extra):
    user, senha = make_user('admin')
    login(user.email, senha)

    valores_por_trimestre = {'q1': 100, 'q2': 200, 'q3': 300}
    for trimestre, valor in valores_por_trimestre.items():
        client.post('/selecionar-trimestre', data={'trimestre': trimestre})
        payload = dict(payload_extra, semana=3, **{campo_valor: valor})
        resp = client.post(endpoint, json=payload)
        assert resp.status_code == 200, resp.get_json()

    with app.app_context():
        for trimestre, valor_esperado in valores_por_trimestre.items():
            registro = model.query.filter_by(semana=3, trimestre=trimestre).first()
            assert registro is not None, f'meta nao foi salva para {trimestre}'
            assert float(getattr(registro, campo_valor)) == valor_esperado, (
                f'trimestre {trimestre} deveria ter {campo_valor}={valor_esperado}, '
                f'mas tem {getattr(registro, campo_valor)} (possivel colisao entre trimestres)'
            )


@pytest.mark.parametrize('trimestre,deve_permitir', [('q1', False), ('q2', True), ('q3', True)])
def test_meta_negociacao_fornecedores_so_conta_a_partir_do_2o_trimestre_do_sistema(
    client, make_user, login, trimestre, deve_permitir,
):
    """Regra de negocio: Negociacao de Fornecedores so vale a partir do 3o
    Trimestre exibido (q2 no codigo). O 4o Trimestre (q3) tambem deve permitir,
    pois cai no 'else' do `if get_trimestre() == 'q1'`."""
    user, senha = make_user('admin')
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': trimestre})

    resp = client.post('/admin/meta-negociacao-fornecedores/salvar', json={
        'semana': 1, 'valor_meta': 500, 'acoes_planejadas': 2,
    })
    if deve_permitir:
        assert resp.status_code == 200
    else:
        assert resp.status_code == 400


@pytest.mark.parametrize('trimestre,semana1_bloqueada', [('q1', True), ('q2', False), ('q3', False)])
def test_semana_1_de_meta_vendas_so_e_travada_no_q1_para_nao_admin(
    client, make_user, login, trimestre, semana1_bloqueada,
):
    """A trava da semana 1 (primeira semana de Abril) vale so para o 1o
    trimestre do sistema (q1); q2 e o novo q3 nao devem travar a semana 1."""
    user, senha = make_user('admin_comercial')
    login(user.email, senha)
    client.post('/selecionar-trimestre', data={'trimestre': trimestre})

    resp = client.post('/admin/meta-venda/salvar', json={
        'semana': 1, 'quantidade_meta': 10, 'acoes_planejadas': 1,
    })
    if semana1_bloqueada:
        assert resp.status_code == 403
    else:
        assert resp.status_code == 200
