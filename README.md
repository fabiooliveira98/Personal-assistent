# Assistente Operacional para Personal

Base inicial do backend para centralizar pagamentos, cancelamentos, reposicoes, agenda e consultas operacionais via WhatsApp.

## Objetivo

Esta primeira base implementa:

- modelo de dominio inicial;
- persistencia transacional com trilha de auditoria;
- ingestao de mensagens no formato de webhook;
- pipeline de interpretacao com confirmacao humana;
- fila de mensagens de saida para a personal;
- confirmacao operacional no proprio WhatsApp;
- cadastro manual inicial de alunos e agenda;
- fechamento financeiro por periodo com base em aulas realizadas;
- consultas operacionais essenciais via API;
- documentacao da arquitetura e das regras do MVP.

## Stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0
- PostgreSQL/Supabase em producao
- SQLite para desenvolvimento local

## Estrutura

```text
app/
  api/               rotas HTTP
  core/              configuracao e banco
  domain/            enums, modelos e contratos
  services/          ingestao, interpretacao, confirmacao e consultas
docs/                arquitetura, dominio e roadmap
tests/               testes iniciais
```

## Principios implementados

- Event-first: toda mensagem relevante e salva antes de gerar qualquer efeito de negocio.
- Human-in-the-loop: eventos criticos passam por confirmacao.
- Idempotencia: o sistema usa `external_message_id` para evitar duplicidades.
- Regras no backend: a interpretacao apenas propõe fatos; a persistencia final acontece por regras deterministicas.

## Endpoints iniciais

- `GET /health`
- `GET /webhooks/whatsapp`
- `POST /webhooks/whatsapp`
- `POST /confirmations/{interpretation_id}`
- `POST /queries`
- `POST /students`
- `POST /agenda`
- `GET /interpretations/pending`
- `GET /outbox`
- `GET /billing-periods/{student_id}/latest`

## Configuracao

Copie `.env.example` para `.env` e ajuste:

```env
APP_ENV=development
DATABASE_URL=sqlite:///./personal_assistant.db
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_API_VERSION=v21.0
WHATSAPP_SEND_ENABLED=false
PERSONAL_WHATSAPP_CONTACT_ID=
PERSONAL_DISPLAY_NAME=Personal
```

### Conectando ao Supabase

Este projeto nao precisa do SDK do Supabase para funcionar com o banco. Como ele ja usa SQLAlchemy, a integracao mais simples e correta aqui e conectar direto no PostgreSQL do Supabase.

1. No painel do Supabase, abra o projeto certo.
2. Va em `Connect` ou `Project Settings > Database`.
3. Copie a string de conexao de `Transaction pooler`.
4. Troque o comeco `postgres://` por `postgresql+psycopg://` se necessario.
5. Garanta que a URL termine com `?sslmode=require`.
6. Cole essa URL no `.env` em `DATABASE_URL`.

Exemplo:

```env
DATABASE_URL=postgresql+psycopg://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require
```

Depois disso:

1. Instale as dependencias do projeto, incluindo o driver `psycopg` adicionado nesta base.
2. Suba a API.
3. Abra `GET /health`.
4. Se estiver tudo certo, a resposta deve trazer `database: "connected"`.

Observacoes importantes:

- Use a senha do banco do Supabase, nao a senha da sua conta.
- O projeto cria as tabelas automaticamente ao iniciar pela chamada `Base.metadata.create_all(...)` em [app/main.py](C:/Users/Fabio/Documents/Personal%20assistent/app/main.py:12).
- Se voce quiser usar Auth, Storage ou Realtime do Supabase depois, ai sim vale adicionar o client do Supabase em uma etapa separada.

### Integracao com OpenAI

O projeto agora aceita `OPENAI_API_KEY` e `OPENAI_MODEL` para interpretar mensagens com OpenAI.

- quando `OPENAI_API_KEY` estiver configurada, o backend tenta usar OpenAI para classificar mensagens livres;
- comandos de confirmacao e consultas operacionais continuam com tratamento deterministico;
- se a chamada da OpenAI falhar ou retornar algo invalido, o backend volta automaticamente para a heuristica local.

## Proximos passos recomendados

1. Conectar o projeto a um Supabase real.
2. Adicionar migracoes com Alembic.
3. Configurar o numero da personal para receber confirmacoes reais.
4. Trocar a interpretacao heuristica por um adaptador com OpenAI.
5. Evoluir o fechamento financeiro para suportar regras especiais por aluno.
