# 🏢 Sousa Araujo — Sistema Web

Sistema de gerenciamento de relacionamento com clientes, desenvolvido em **Flask + PostgreSQL**, com deploy configurado para **Railway**.

---

## 🗂️ Estrutura do Projeto

```
projeto-sousa/
├── app/
│   ├── __init__.py           # App factory + extensões
│   ├── models/
│   │   ├── user.py           # Modelo de usuário (bcrypt)
│   │   ├── relacionamento.py # Registros de contato
│   │   ├── empreendimento.py # Empreendimentos (select)
│   │   └── meta.py           # Metas por semana (admin)
│   ├── routes/
│   │   ├── auth.py           # Login / Logout
│   │   ├── relacionamento.py # CRUD + WebSocket broadcast
│   │   └── admin.py          # Gestão de usuários, empreendimentos, metas
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/             # login.html, em_construcao.html
│   │   ├── relacionamento/   # index.html
│   │   └── admin/            # dashboard.html
│   └── static/
│       ├── css/              # base.css, relacionamento.css, admin.css
│       └── js/               # relacionamento.js, admin.js
├── run.py                    # Entry point
├── Procfile                  # Gunicorn (Railway)
├── railway.toml              # Config Railway
├── requirements.txt
└── .env.example
```

---

## 🚀 Deploy no Railway

### 1. Pré-requisitos
- Conta no [Railway](https://railway.app)
- Git instalado
- Python 3.11+

### 2. Configuração local

```bash
# Clone / entre na pasta
cd projeto-sousa

# Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# Instale dependências
pip install -r requirements.txt

# Configure variáveis de ambiente
cp .env.example .env
# Edite .env com suas configurações locais (SQLite funciona para dev)
```

### 3. Inicializar banco de dados local

```bash
flask db init
flask db migrate -m "initial"
flask db upgrade
```

> O seed do usuário admin e empreendimentos padrão é automático na primeira inicialização.

### 4. Rodar localmente

```bash
python run.py
# Acesse: http://localhost:5000
```

### 5. Deploy no Railway

```bash
# Inicie um repositório Git
git init
git add .
git commit -m "feat: sistema sousa araujo v1"

# No Railway:
# 1. New Project → Deploy from GitHub repo
# 2. Adicione um serviço PostgreSQL ao projeto
# 3. Configure as variáveis de ambiente:

SECRET_KEY=<chave-aleatória-longa>
FLASK_ENV=production

# O Railway injeta DATABASE_URL automaticamente ao vincular o PostgreSQL.
```

### 6. Variáveis de ambiente no Railway

| Variável | Valor |
|---|---|
| `SECRET_KEY` | String aleatória longa (ex: `openssl rand -hex 32`) |
| `FLASK_ENV` | `production` |
| `DATABASE_URL` | Injetado automaticamente pelo Railway PostgreSQL |

---

## 👤 Usuário inicial

| Campo | Valor |
|---|---|
| E-mail | `bruno.alves@sousaaraujo.com.br` |
| Senha | `Sousa@1234` |
| Tipo | `ADMIN` |

> ⚠️ Troque a senha após o primeiro login (funcionalidade a implementar no próximo sprint).

---

## 🔐 Segurança

- Apenas e-mails `@sousaaraujo.com.br` são aceitos
- Senhas armazenadas com **bcrypt**
- Sessões HTTP-only e Secure em produção
- Controle de acesso por tipo de usuário em todas as rotas
- Validação de dados no frontend **e** backend

---

## 🧩 Tipos de Usuário

| Tipo | Acesso atual |
|---|---|
| `admin` | Dashboard admin + Relacionamento |
| `relacionamento` | Página de Relacionamento |
| `comercial` | Em construção |
| `financeiro` | Em construção |
| `obra` | Em construção |

---

## ⚡ Funcionalidades em Tempo Real

O sistema usa **Flask-SocketIO + Eventlet** para broadcast de atualizações.  
Ao cadastrar ou deletar um registro, **todos os usuários conectados** recebem a atualização instantânea sem necessidade de recarregar a página.

---

## IA no Relatório Trimestral

O painel de relacionamento possui uma assistente analítica no canto inferior direito da tela de **Resumo Trimestral**.

Ela responde perguntas com base em:
- dados agregados do trimestre
- evolução semanal
- metas planejadas x realizadas
- filtros aplicados no painel
- dados do banco relacionados a responsáveis, empreendimentos e situações

### Variáveis necessárias

```env
GEMINI_API_KEY=sua-chave-gemini
GEMINI_MODEL=gemini-2.5-flash
GEMINI_ANALYTICS_STYLE=analitico_comercial_financeiro
```

### Estilos disponíveis

- `executivo`: respostas mais diretas para gestão
- `analitico_comercial_financeiro`: mistura análise profunda, leitura comercial e impacto financeiro
- `comercial`: foco em performance, conversão e oportunidades
- `financeiro`: foco em valor realizado, gaps e impacto financeiro

---

## 📋 Regras de Negócio

- Dados salvos em **CAIXA ALTA** no banco
- **Ações realizadas** = registros com `SITUAÇÃO = SIM`
- **Barra de progresso** proporcional a ações realizadas / planejadas
- **Soma de valores** = soma dos campos `valor` onde `SITUAÇÃO = SIM` e `valor > 0`
- Campo `RESPONSÁVEL` preenchido automaticamente com o usuário logado
- Campo `EMPREENDIMENTO` é um select gerenciado pelo ADMIN

---

## 🛠️ Próximos módulos

- [ ] Comercial
- [ ] Financeiro
- [ ] Obra
- [ ] Troca de senha pelo próprio usuário
- [ ] Relatórios exportáveis (PDF/Excel)
