# Arquitetura Inicial

## Visao geral

O sistema foi desenhado para centralizar a operacao de uma unica personal usando o WhatsApp como principal canal. A arquitetura separa claramente:

- entrada de mensagens;
- interpretacao assistida;
- regras de negocio deterministicas;
- trilha de auditoria;
- consultas operacionais.

## Fluxo principal

1. O WhatsApp envia uma mensagem para o webhook.
2. A mensagem e persistida como `IncomingMessage`.
3. O sistema gera um `RawEvent` com o payload normalizado.
4. Um interpretador produz uma `Interpretation` com:
   - intencao;
   - entidades extraidas;
   - nivel de confianca;
   - justificativa.
5. Se a intencao for critica, a interpretacao fica `pending_confirmation`.
6. A confirmacao aprovada cria fatos de negocio:
   - `Payment`
   - `LessonCancellation`
   - `Reschedule`
   - `ReplacementCredit`
   - `StudentNote`
7. Consultas em linguagem natural sempre leem dados estruturados do banco.

## Fronteiras de responsabilidade

### Integracao
- recebe e valida webhooks;
- normaliza payloads;
- garante idempotencia por mensagem externa.

### Interpretacao
- classifica a intencao;
- extrai entidades;
- nunca persiste fatos finais sozinha.

### Dominio
- aplica regras de negocio;
- decide se um evento gera pagamento, credito, cancelamento ou nota;
- protege a consistencia transacional.

### Consultas
- traduz perguntas operacionais em consultas controladas;
- nao executa SQL gerado por modelo;
- responde apenas com intents conhecidas no MVP.

## Decisoes arquiteturais

- FastAPI foi escolhida pela simplicidade da borda HTTP e boa ergonomia com Pydantic.
- SQLAlchemy permite usar SQLite localmente e PostgreSQL/Supabase em producao sem reescrever o dominio.
- O interpretador foi encapsulado em uma interface para evoluir de heuristica para OpenAI sem acoplamento.
- Confirmacao humana fica no centro do MVP para reduzir erros operacionais.

## Escalabilidade

O desenho atual e modular e pode evoluir para processamento assincrono com fila sem reestruturar o dominio:

- webhook grava evento;
- worker interpreta;
- worker de aplicacao executa fatos confirmados;
- canal de resposta envia retorno ao WhatsApp.
