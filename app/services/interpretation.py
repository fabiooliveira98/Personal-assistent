from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import IntentType
from app.domain.models import IncomingMessage


@dataclass(slots=True)
class InterpretationResult:
    intent: IntentType
    confidence: Decimal
    extracted_entities: dict
    reasoning: str
    requires_confirmation: bool
    domain_fact_type: str | None


class MessageInterpreter:
    """Heuristic interpreter used until an OpenAI adapter is connected."""

    def interpret(self, message: IncomingMessage) -> InterpretationResult:
        text = (message.text_content or "").strip()
        lowered = text.lower()

        if self._looks_like_confirmation_command(lowered):
            return InterpretationResult(
                intent=IntentType.confirmation_command,
                confidence=Decimal("0.99"),
                extracted_entities={"command_text": text},
                reasoning="Detected a confirmation command from WhatsApp.",
                requires_confirmation=False,
                domain_fact_type=None,
            )

        if self._looks_like_query(lowered):
            return InterpretationResult(
                intent=IntentType.operational_query,
                confidence=Decimal("0.90"),
                extracted_entities={"question": text},
                reasoning="Detected an operational question pattern.",
                requires_confirmation=False,
                domain_fact_type=None,
            )

        if any(token in lowered for token in ("pix", "comprovante")) or message.media_url:
            amount = self._extract_amount(text)
            return InterpretationResult(
                intent=IntentType.pix_receipt,
                confidence=Decimal("0.78"),
                extracted_entities={"amount": amount, "raw_text": text},
                reasoning="Detected PIX receipt indicators or media attachment.",
                requires_confirmation=True,
                domain_fact_type="pix_receipt",
            )

        if any(token in lowered for token in ("pagou", "pagamento", "paguei")):
            amount = self._extract_amount(text)
            student_name = self._extract_named_student(text)
            return InterpretationResult(
                intent=IntentType.payment_notice,
                confidence=Decimal("0.84"),
                extracted_entities={"student_name": student_name, "amount": amount, "raw_text": text},
                reasoning="Detected payment-related keywords.",
                requires_confirmation=True,
                domain_fact_type="payment",
            )

        if any(token in lowered for token in ("cancel", "nao vou", "faltar")):
            return InterpretationResult(
                intent=IntentType.cancellation_request,
                confidence=Decimal("0.80"),
                extracted_entities={"student_name": self._extract_named_student(text), "raw_text": text},
                reasoning="Detected cancellation request keywords.",
                requires_confirmation=True,
                domain_fact_type="lesson_cancellation",
            )

        if "reposi" in lowered:
            return InterpretationResult(
                intent=IntentType.replacement_request,
                confidence=Decimal("0.80"),
                extracted_entities={"student_name": self._extract_named_student(text), "raw_text": text},
                reasoning="Detected replacement request keywords.",
                requires_confirmation=True,
                domain_fact_type="replacement_credit",
            )

        if any(token in lowered for token in ("horario", "remarca", "trocar")):
            return InterpretationResult(
                intent=IntentType.schedule_change,
                confidence=Decimal("0.76"),
                extracted_entities={"student_name": self._extract_named_student(text), "raw_text": text},
                reasoning="Detected schedule change request keywords.",
                requires_confirmation=True,
                domain_fact_type="reschedule",
            )

        if text:
            return InterpretationResult(
                intent=IntentType.student_note,
                confidence=Decimal("0.55"),
                extracted_entities={"student_name": self._extract_named_student(text), "content": text},
                reasoning="Fallback to note when text is informative but non-transactional.",
                requires_confirmation=False,
                domain_fact_type="student_note",
            )

        return InterpretationResult(
            intent=IntentType.unknown,
            confidence=Decimal("0.10"),
            extracted_entities={},
            reasoning="Could not identify a supported intent.",
            requires_confirmation=False,
            domain_fact_type=None,
        )

    def _extract_amount(self, text: str) -> str | None:
        match = re.search(r"(\d+[.,]\d{2})", text)
        if not match:
            return None
        return match.group(1).replace(".", "").replace(",", ".")

    def _extract_named_student(self, text: str) -> str | None:
        match = re.search(r"\b([A-Z][a-z]+)\b", text)
        return match.group(1) if match else None

    def _looks_like_query(self, lowered: str) -> bool:
        return any(
            pattern in lowered
            for pattern in (
                "quem ainda nao pagou",
                "quanto entrou",
                "ja pagou",
                "quantas reposi",
                "quanto esse aluno deve",
                "o que tenho hoje",
            )
        )

    def _looks_like_confirmation_command(self, lowered: str) -> bool:
        return lowered.startswith("confirmar #") or lowered.startswith("rejeitar #") or lowered.startswith("corrigir #")
