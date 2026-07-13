from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class HealthResponse(BaseModel):
    status: str
    environment: str
    database: str


class IncomingWhatsAppMessage(BaseModel):
    external_message_id: str = Field(min_length=1)
    external_contact_id: str = Field(min_length=1)
    sender_name: str | None = None
    message_type: str = "text"
    text: str | None = None
    media_url: str | None = None
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncomingWebhookEnvelope(BaseModel):
    object: str = "whatsapp_business_account"
    messages: list[IncomingWhatsAppMessage]


class MetaWebhookContactProfile(BaseModel):
    name: str | None = None


class MetaWebhookContact(BaseModel):
    profile: MetaWebhookContactProfile | None = None
    wa_id: str | None = None


class MetaWebhookMessageText(BaseModel):
    body: str | None = None


class MetaWebhookMessage(BaseModel):
    id: str = Field(min_length=1)
    from_: str = Field(alias="from", min_length=1)
    timestamp: str | None = None
    type: str = "text"
    text: MetaWebhookMessageText | None = None


class MetaWebhookValue(BaseModel):
    contacts: list[MetaWebhookContact] = Field(default_factory=list)
    messages: list[MetaWebhookMessage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetaWebhookChange(BaseModel):
    field: str | None = None
    value: MetaWebhookValue


class MetaWebhookEntry(BaseModel):
    changes: list[MetaWebhookChange] = Field(default_factory=list)


class MetaWebhookEnvelope(BaseModel):
    object: str = "whatsapp_business_account"
    entry: list[MetaWebhookEntry] = Field(default_factory=list)


def normalize_whatsapp_webhook(payload: dict[str, Any]) -> IncomingWebhookEnvelope:
    try:
        return IncomingWebhookEnvelope.model_validate(payload)
    except ValidationError:
        meta_payload = MetaWebhookEnvelope.model_validate(payload)

    normalized_messages: list[IncomingWhatsAppMessage] = []
    for entry in meta_payload.entry:
        for change in entry.changes:
            contacts_by_id = {
                contact.wa_id: contact
                for contact in change.value.contacts
                if contact.wa_id
            }
            for message in change.value.messages:
                contact = contacts_by_id.get(message.from_)
                normalized_messages.append(
                    IncomingWhatsAppMessage(
                        external_message_id=message.id,
                        external_contact_id=message.from_,
                        sender_name=(contact.profile.name if contact and contact.profile else None),
                        message_type=message.type,
                        text=(message.text.body if message.text else None),
                        media_url=None,
                        timestamp=_parse_meta_timestamp(message.timestamp),
                        metadata={
                            "meta_change_field": change.field,
                            "meta_metadata": change.value.metadata,
                            "meta_message": message.model_dump(mode="json", by_alias=True),
                        },
                    )
                )

    return IncomingWebhookEnvelope(
        object=meta_payload.object,
        messages=normalized_messages,
    )


def _parse_meta_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromtimestamp(int(value), tz=UTC).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


class WebhookVerificationResponse(BaseModel):
    challenge: str


class InterpretationSnapshot(BaseModel):
    id: int
    intent: str
    confidence: float
    status: str
    extracted_entities: dict[str, Any]


class ConfirmationDecisionRequest(BaseModel):
    decision: Literal["confirmed", "rejected", "corrected"]
    corrected_entities: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class OperationalQueryRequest(BaseModel):
    question: str = Field(min_length=3)
    reference_datetime: datetime | None = None


class OperationalQueryResponse(BaseModel):
    intent: str
    answer: str
    data: dict[str, Any] = Field(default_factory=dict)


class StudentCreateRequest(BaseModel):
    full_name: str = Field(min_length=2)
    whatsapp_contact_id: str = Field(min_length=1)
    default_lesson_price: float = Field(ge=0)
    active: bool = True


class StudentResponse(BaseModel):
    id: int
    full_name: str
    whatsapp_contact_id: str
    default_lesson_price: float
    active: bool


class AgendaItemCreateRequest(BaseModel):
    student_id: int
    title: str = Field(min_length=2)
    scheduled_date: date
    scheduled_time: time
    duration_minutes: int = Field(default=60, ge=15)
    lesson_price: float | None = Field(default=None, ge=0)
    notes: str | None = None


class AgendaItemResponse(BaseModel):
    id: int
    student_id: int | None
    title: str
    scheduled_date: date
    scheduled_time: time
    duration_minutes: int
    status: str
    lesson_price: float | None
    notes: str | None


class PendingInterpretationResponse(BaseModel):
    interpretation_id: int
    intent: str
    confidence: float
    status: str
    student_name: str | None = None
    raw_text: str | None = None
    suggested_reply: str | None = None


class OutboundMessageResponse(BaseModel):
    id: int
    recipient_contact_id: str
    recipient_role: str
    body: str
    status: str


class BillingSummaryResponse(BaseModel):
    student: str
    period_label: str
    lesson_count: int
    amount_due: float
    amount_paid: float
    balance: float
