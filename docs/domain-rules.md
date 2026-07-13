# Regras de Dominio do MVP

## Intencoes suportadas

- `payment_notice`
- `pix_receipt`
- `cancellation_request`
- `replacement_request`
- `schedule_change`
- `student_note`
- `operational_query`
- `unknown`

## Politica de confirmacao

Exigem confirmacao:

- pagamentos;
- comprovantes PIX;
- cancelamentos;
- reposicoes;
- alteracoes de horario.

Nao exigem confirmacao obrigatoria no estado atual:

- observacoes simples;
- consultas operacionais.

## Regras iniciais

### Pagamentos
- Um pagamento confirmado deve ser associado a um aluno.
- O `external_message_id` protege contra dupla ingestao da mesma mensagem.
- Ainda nao existe conciliacao automatica com conta bancaria.

### Cancelamentos
- Cancelamento gera historico mesmo antes da regra final de reposicao.
- O direito a reposicao depende de regra futura mais detalhada da personal.

### Reposicoes
- No MVP, um credito pode ser criado manualmente a partir da confirmacao.
- Consumo de credito sera sempre vinculado a uma sessao.

### Agenda
- A agenda e baseada em `AgendaItem`.
- Alteracoes futuras devem preservar historico por `Reschedule`.

### Observacoes
- Observacoes sao vinculadas ao aluno e a mensagem de origem.

## Perguntas suportadas no MVP

- Quem ainda nao pagou?
- Quanto entrou este mes?
- O aluno X ja pagou?
- Quantas reposicoes o aluno X possui?
- O que tenho hoje as HH:mm?
