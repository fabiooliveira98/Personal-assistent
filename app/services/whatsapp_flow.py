from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import InterpretationStatus, IntentType
from app.domain.models import Interpretation
from app.domain.schemas import ConfirmationDecisionRequest
from app.services.confirmation import ConfirmationService
from app.services.query_service import QueryService
from app.services.whatsapp import WhatsAppMessagingService


class WhatsAppFlowService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.confirmation_service = ConfirmationService(session)
        self.query_service = QueryService(session)
        self.messaging = WhatsAppMessagingService(session)

    def is_personal_contact(self, external_contact_id: str) -> bool:
        return bool(settings.personal_whatsapp_contact_id) and external_contact_id == settings.personal_whatsapp_contact_id

    def handle_interpretation(self, interpretation: Interpretation) -> None:
        message = interpretation.raw_event.message
        external_contact_id = message.contact_channel.external_contact_id if message.contact_channel else ""

        if interpretation.intent == IntentType.confirmation_command and self.is_personal_contact(external_contact_id):
            self._handle_confirmation_command(interpretation)
            return

        if interpretation.intent == IntentType.operational_query and self.is_personal_contact(external_contact_id):
            self._handle_operational_query(interpretation)
            return

        if interpretation.status == InterpretationStatus.pending_confirmation:
            self._queue_confirmation_prompt(interpretation)

    def _handle_confirmation_command(self, interpretation: Interpretation) -> None:
        command_text = str(interpretation.extracted_entities.get("command_text") or "")
        parsed = self._parse_confirmation_command(command_text)
        result = self.confirmation_service.apply_decision(
            parsed["interpretation_id"],
            ConfirmationDecisionRequest(
                decision=parsed["decision"],
                corrected_entities=parsed["corrected_entities"],
                notes=parsed["notes"],
            ),
        )
        self.messaging.queue_message(
            recipient_contact_id=settings.personal_whatsapp_contact_id,
            recipient_role="personal",
            body=f"Confirmacao aplicada na interpretacao #{result.id}.",
            interpretation_id=result.id,
        )
        self.session.commit()

    def _handle_operational_query(self, interpretation: Interpretation) -> None:
        question = str(interpretation.extracted_entities.get("question") or interpretation.raw_event.message.text_content or "")
        response = self.query_service.answer_from_whatsapp(question)
        self.messaging.queue_message(
            recipient_contact_id=settings.personal_whatsapp_contact_id,
            recipient_role="personal",
            body=response.answer,
            interpretation_id=interpretation.id,
        )
        self.session.commit()

    def _queue_confirmation_prompt(self, interpretation: Interpretation) -> None:
        if not settings.personal_whatsapp_contact_id:
            return
        entities = interpretation.extracted_entities
        student_name = entities.get("student_name") or "aluno nao identificado"
        raw_text = entities.get("raw_text") or interpretation.raw_event.message.text_content or ""
        prompt = (
            f"Interpretacao #{interpretation.id}: {interpretation.intent.value} para {student_name}.\n"
            f"Mensagem: {raw_text}\n"
            "Responda com:\n"
            f"CONFIRMAR #{interpretation.id}\n"
            f"REJEITAR #{interpretation.id}\n"
            f"CORRIGIR #{interpretation.id} aluno=Nome; valor=0.00; billing_period_start=AAAA-MM-DD; "
            "billing_period_end=AAAA-MM-DD; lesson_date=AAAA-MM-DD; lesson_time=HH:MM; "
            "grant_replacement=true; replacement_expires_on=AAAA-MM-DD"
        )
        self.messaging.queue_message(
            recipient_contact_id=settings.personal_whatsapp_contact_id,
            recipient_role="personal",
            body=prompt,
            interpretation_id=interpretation.id,
        )

    def _parse_confirmation_command(self, command_text: str) -> dict[str, Any]:
        match = re.match(r"^(confirmar|rejeitar|corrigir)\s+#(\d+)\s*(.*)$", command_text.strip(), re.IGNORECASE)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid confirmation command format.",
            )
        action, interpretation_id, remainder = match.groups()
        decision_map = {"confirmar": "confirmed", "rejeitar": "rejected", "corrigir": "corrected"}
        corrected_entities: dict[str, Any] = {}
        if remainder:
            for chunk in [part.strip() for part in remainder.split(";") if part.strip()]:
                if "=" not in chunk:
                    continue
                key, value = chunk.split("=", 1)
                corrected_entities[key.strip()] = self._coerce_value(value.strip())
        return {
            "decision": decision_map[action.lower()],
            "interpretation_id": int(interpretation_id),
            "corrected_entities": corrected_entities,
            "notes": remainder or None,
        }

    def _coerce_value(self, raw_value: str) -> Any:
        lowered = raw_value.lower()
        if lowered in {"true", "sim"}:
            return True
        if lowered in {"false", "nao"}:
            return False
        return raw_value
