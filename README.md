# Build Flow

Aplicacao web corporativa para acompanhamento operacional, comercial e gerencial, desenvolvida em Flask com arquitetura modular, interface server-rendered e atualizacao em tempo real via Socket.IO.

O sistema centraliza operacoes de relacionamento, vendas varejo, investidores e administracao interna em uma unica base, com paineis analiticos e controles de acesso por perfil de usuario.

## Visao Geral

- Backend em Flask com app factory e blueprints por dominio.
- Persistencia com SQLAlchemy sobre PostgreSQL.
- Autenticacao e controle de sessao com Flask-Login.
- Protecao de formularios e requisicoes com Flask-WTF e CSRF.
- Atualizacao em tempo real entre telas com Flask-SocketIO.
- Interface HTML/Jinja com ativos estaticos organizados por modulo.
- Recursos analiticos e assistente de apoio concentrados na camada de servicos.

## Estrutura do Projeto

```text
projeto-sousa/
|-- app/
|   |-- __init__.py
|   |-- models/
|   |   |-- __init__.py
|   |   |-- empreendimento.py
|   |   |-- investidor.py
|   |   |-- meta.py
|   |   |-- meta_investidor.py
|   |   |-- meta_venda.py
|   |   |-- relacionamento.py
|   |   |-- user.py
|   |   `-- venda.py
|   |-- routes/
|   |   |-- __init__.py
|   |   |-- admin.py
|   |   |-- auth.py
|   |   |-- investidores.py
|   |   |-- relacionamento.py
|   |   `-- vendas.py
|   |-- services/
|   |   `-- analytics_ai.py
|   |-- static/
|   |   |-- css/
|   |   |   |-- admin.css
|   |   |   |-- base.css
|   |   |   |-- master.css
|   |   |   |-- relacionamento.css
|   |   |   `-- vendas.css
|   |   |-- images/
|   |   |   |-- kamille.png
|   |   |   |-- logo.png
|   |   |   |-- logo.webp
|   |   |   `-- logo2.webp
|   |   `-- js/
|   |       |-- admin.js
|   |       |-- analytics_ai.js
|   |       |-- investidores.js
|   |       |-- master.js
|   |       |-- relacionamento.js
|   |       `-- vendas.js
|   `-- templates/
|       |-- base.html
|       |-- admin/
|       |   |-- dashboard.html
|       |   |-- master_painel.html
|       |   `-- relacionamento_painel.html
|       |-- auth/
|       |   |-- em_construcao.html
|       |   `-- login.html
|       |-- investidores/
|       |   `-- index.html
|       |-- partials/
|       |   `-- theme_control.html
|       |-- relacionamento/
|       |   `-- index.html
|       `-- vendas/
|           `-- index.html
|-- instance/
|-- requirements.txt
`-- run.py
```

## Organizacao por Camadas

### Aplicacao

`app/__init__.py` concentra a inicializacao da aplicacao, extensoes, filtros Jinja, configuracoes centrais, registro de blueprints e rotinas de bootstrap.

### Modelos

A pasta `app/models/` contem as entidades de negocio e suporte ao dominio:

- usuarios e perfis de acesso
- empreendimentos
- registros de relacionamento
- registros de vendas
- registros de investidores
- metas operacionais e comerciais

### Rotas

A pasta `app/routes/` organiza a aplicacao por contexto funcional:

- `auth.py`: autenticacao e fluxo de acesso
- `admin.py`: administracao, configuracoes e paineis gerenciais
- `relacionamento.py`: operacao de relacionamento e inadimplencia
- `vendas.py`: central e painel de vendas varejo
- `investidores.py`: central e painel de investidores

### Servicos

`app/services/analytics_ai.py` encapsula a camada de assistencia analitica, agregacao contextual e integracao com recursos de IA utilizados pelos paineis.

### Interface

As views estao em `app/templates/`, com base compartilhada e templates separados por modulo. Os ativos estaticos ficam em `app/static/`, com estilos e scripts distribuidos conforme cada frente funcional.

## Principais Dominios Funcionais

- Administracao de usuarios, empreendimentos e metas.
- Central de relacionamento com acompanhamento operacional.
- Central de vendas varejo com indicadores e grid de reservas.
- Central de investidores com acompanhamento consolidado.
- Painel master com visao executiva e consolidacao entre modulos.
- Paineis analiticos com sincronizacao em tempo real.

## Arquitetura Tecnica

- Framework web: Flask
- ORM: SQLAlchemy
- Migracoes: Flask-Migrate
- Autenticacao: Flask-Login
- Formularios e CSRF: Flask-WTF
- Tempo real: Flask-SocketIO
- Banco de dados: PostgreSQL
- Servidor WSGI/ASGI de execucao: Gunicorn/Eventlet

## Consideracoes de Engenharia

- Estrutura modular orientada por dominio.
- Separacao clara entre modelos, rotas, servicos, templates e ativos.
- Capacidade de atualizacao em tempo real entre clientes conectados.
- Base preparada para operacao em ambiente produtivo com persistencia relacional e controle de acesso.
