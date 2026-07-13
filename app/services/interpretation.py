from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.core.config import settings

from app.domain.enums import IntentType
from app.domain.models import IncomingMessage

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - local environments may not have deps installed yet.
    OpenAI = None


@dataclass(slots=True)
class InterpretationResult:
    intent: IntentType
    confidence: Decimal
    extracted_entities: dict
    reasoning: str
    requires_confirmation: bool
    domain_fact_type: str | None


class MessageInterpreter:
    def __init__(self) -> None:
        self._client = (
            OpenAI(api_key=settings.openai_api_key)
            if settings.openai_api_key and OpenAI is not None
            else None
        )

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

        if self._client is not None and text:
            ai_result = self._interpret_with_openai(message)
            if ai_result is not None:
                return ai_result

        return self._interpret_with_heuristics(message)

    def _interpret_with_openai(self, message: IncomingMessage) -> InterpretationResult | None:
        user_prompt = json.dumps(
            {
                "text": message.text_content or "",
                "message_type": message.message_type,
                "sender_name": message.contact_channel.label if message.contact_channel else None,
                "external_contact_id": (
                    message.contact_channel.external_contact_id
                    if message.contact_channel
                    else None
                ),
                "has_media": bool(message.media_url),
                "media_url": message.media_url,
            },
            ensure_ascii=True,
        )
        try:
            response = self._client.responses.create(
                model=settings.openai_model,
                input=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception:
            return None

        payload = self._parse_json_object(getattr(response, "output_text", ""))
        if payload is None:
            return None

        intent = self._coerce_intent(payload.get("intent"))
        entities = self._normalize_entities(payload.get("extracted_entities"), message)
        reasoning = str(payload.get("reasoning") or "Interpreted by OpenAI.")
        requires_confirmation = bool(payload.get("requires_confirmation", True))
        domain_fact_type = payload.get("domain_fact_type") or self._default_domain_fact_type(intent)
        confidence = self._coerce_confidence(payload.get("confidence"))

        return InterpretationResult(
            intent=intent,
            confidence=confidence,
            extracted_entities=entities,
            reasoning=reasoning,
            requires_confirmation=requires_confirmation,
            domain_fact_type=domain_fact_type,
        )

    def _interpret_with_heuristics(self, message: IncomingMessage) -> InterpretationResult:
        text = (message.text_content or "").strip()
        lowered = text.lower()

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

    def _system_prompt(self) -> str:
        return (
            "You are classifying incoming WhatsApp messages for a personal trainer operations backend. "
            "Return only valid JSON with the fields: intent, confidence, requires_confirmation, "
            "domain_fact_type, reasoning, extracted_entities. "
            "Supported intents: payment_notice, pix_receipt, cancellation_request, "
            "replacement_request, schedule_change, student_note, unknown. "
            "Use payment_notice when the text says someone paid; use pix_receipt when it looks like a "
            "PIX receipt or proof of payment; use cancellation_request for missed/cancelled lesson requests; "
            "use replacement_request for replacement credit requests; use schedule_change for rescheduling. "
            "Set requires_confirmation=true for payment_notice, pix_receipt, cancellation_request, "
            "replacement_request, and schedule_change. "
            "Set requires_confirmation=false for student_note and unknown. "
            "In extracted_entities, include only relevant keys from this set when they are present or can be "
            "safely inferred: student_name, amount, raw_text, content, lesson_date, lesson_time, "
            "new_lesson_date, new_lesson_time, billing_period_start, billing_period_end, paid_at, "
            "grant_replacement, replacement_expires_on. "
            "If student_name or amount are unknown, omit them. Keep confidence between 0 and 1."
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

    def _parse_json_object(self, content: str) -> dict[str, Any] | None:
        if not content:
            return None
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _coerce_intent(self, raw_intent: object) -> IntentType:
        try:
            return IntentType(str(raw_intent or IntentType.unknown.value))
        except ValueError:
            return IntentType.unknown

    def _coerce_confidence(self, raw_confidence: object) -> Decimal:
        try:
            value = Decimal(str(raw_confidence))
        except Exception:
            return Decimal("0.50")
        if value < 0:
            return Decimal("0.00")
        if value > 1:
            return Decimal("1.00")
        return value.quantize(Decimal("0.01"))

    def _normalize_entities(self, raw_entities: object, message: IncomingMessage) -> dict[str, Any]:
        entities = raw_entities if isinstance(raw_entities, dict) else {}
        normalized = {key: value for key, value in entities.items() if value not in (None, "", [])}
        if message.text_content and "raw_text" not in normalized:
            normalized["raw_text"] = message.text_content
        if "amount" in normalized and isinstance(normalized["amount"], str):
            normalized["amount"] = self._normalize_amount_string(normalized["amount"])
        return normalized

    def _default_domain_fact_type(self, intent: IntentType) -> str | None:
        mapping = {
            IntentType.payment_notice: "payment",
            IntentType.pix_receipt: "pix_receipt",
            IntentType.cancellation_request: "lesson_cancellation",
            IntentType.replacement_request: "replacement_credit",
            IntentType.schedule_change: "reschedule",
            IntentType.student_note: "student_note",
        }
        return mapping.get(intent)

    def _normalize_amount_string(self, raw_amount: str) -> str:
        cleaned = raw_amount.strip()
        if "," in cleaned and "." in cleaned:
            return cleaned.replace(".", "").replace(",", ".")
        if "," in cleaned:
            return cleaned.replace(",", ".")
        return cleaned
