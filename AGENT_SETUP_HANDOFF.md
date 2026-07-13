# Handoff: Instalacao e Configuracao das Integracoes Faltantes

## Objetivo

Ajudar na instalacao e configuracao do que falta para o projeto funcionar em ambiente real.

Importante:

- o banco ja esta conectado;
- nao deve popular dados;
- nao deve testar a conexao com o banco;
- foco apenas em instalacao, configuracao e integracoes externas.

## Atualizacoes realizadas nesta conversa

- conexao com Supabase preparada no projeto com `psycopg`;
- `GET /health` passou a informar status do banco;
- `.env.example` e `README.md` foram atualizados com orientacoes de conexao do Supabase;
- webhook do WhatsApp foi adaptado para aceitar o payload real da Meta Cloud API e normalizar internamente para o formato usado pelo projeto;
- foi adicionado teste de normalizacao do webhook em `tests/test_whatsapp_webhook_schema.py`;
- foi criado `.gitignore` para evitar versionamento de `.env`, caches e artefatos locais;
- foi corrigida a linha local de `DATABASE_URL` no `.env` que estava com prefixo duplicado.

## Observacoes importantes para o proximo agente

- o usuario quer que toda mudanca relevante de rota, setup e integracao continue sendo registrada neste documento;
- o projeto ainda nao foi versionado/publicado no GitHub;
- antes de subir para GitHub foi feita uma revisao basica de segredos:
  - nao foi encontrada chave real no codigo-fonte;
  - existe segredo real apenas no `.env`, que nao deve ser commitado;
- existe uma pasta `.git`, mas ela nao esta inicializada como repositorio valido ainda;
- ainda nao foi feito deploy;
- a preferencia atual do usuario e usar `Render`, pois oferece opcao gratuita;
- a integracao com Meta/WhatsApp ainda depende de:
  - URL publica HTTPS do backend;
  - `WHATSAPP_ACCESS_TOKEN`;
  - `WHATSAPP_PHONE_NUMBER_ID`;
  - `WHATSAPP_VERIFY_TOKEN`;
  - `PERSONAL_WHATSAPP_CONTACT_ID`.

## O que falta configurar

### 1. Publicacao do backend

- publicar a API em `Render` (preferencia atual do usuario) ou `Railway` se houver mudanca de decisao;
- garantir URL publica com HTTPS;
- configurar variaveis de ambiente no deploy.

### 2. Variaveis de ambiente

Configurar no ambiente:

- `APP_ENV`
- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_API_VERSION`
- `WHATSAPP_SEND_ENABLED`
- `PERSONAL_WHATSAPP_CONTACT_ID`
- `PERSONAL_DISPLAY_NAME`

### 3. Integracao com WhatsApp Cloud API

- configurar app na Meta for Developers;
- configurar produto WhatsApp Cloud API;
- obter `WHATSAPP_ACCESS_TOKEN`;
- obter `WHATSAPP_PHONE_NUMBER_ID`;
- definir `WHATSAPP_VERIFY_TOKEN`;
- configurar webhook para:
  - `GET /webhooks/whatsapp`
  - `POST /webhooks/whatsapp`

### 4. Integracao com OpenAI

- obter `OPENAI_API_KEY`;
- definir `OPENAI_MODEL`;
- substituir a interpretacao heuristica atual por integracao real com OpenAI, se entrar no escopo desta etapa;
- se nao entrar, deixar apenas a chave e o ambiente prontos.

## Restrições

- nao mexer na modelagem do banco;
- nao popular alunos, agenda ou historico;
- nao testar conexao com o banco;
- nao alterar regras de negocio;
- nao implementar novas features fora de setup e configuracao.

## Entregaveis esperados

- backend publicado;
- variaveis de ambiente configuradas;
- webhook do WhatsApp configurado;
- credenciais externas conectadas no ambiente;
- documentacao curta do que foi configurado e do que ainda depende do dono do projeto.

## Contexto tecnico

O projeto ja possui:

- backend Python;
- endpoints de webhook;
- fluxo de confirmacao;
- estrutura inicial para WhatsApp;
- configuracoes base em `.env.example`.

Arquivos uteis:

- `README.md`
- `.gitignore`
- `.env.example`
- `AGENT_SETUP_HANDOFF.md`
- `app/api/routes.py`
- `app/core/config.py`
- `app/domain/schemas.py`
- `app/services/whatsapp.py`
- `app/services/whatsapp_flow.py`
- `tests/test_whatsapp_webhook_schema.py`

## Pedido para o outro agente

Por favor:

1. instale e configure o ambiente de deploy;
2. conecte as variaveis de ambiente necessarias;
3. configure a integracao do WhatsApp Cloud API;
4. deixe a integracao com OpenAI pronta ou claramente preparada;
5. documente de forma objetiva o que foi feito;
6. nao popule dados e nao teste a conexao com o banco.
