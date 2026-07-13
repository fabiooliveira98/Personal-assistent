from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ChannelType, EventType, InterpretationStatus, MessageDirection
from app.domain.models import ContactChannel, IncomingMessage, Interpretation, RawEvent
from app.domain.schemas import IncomingWebhookEnvelope
from app.services.interpretation import MessageInterpreter
from app.services.whatsapp_flow import WhatsAppFlowService


class IngestionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.interpreter = MessageInterpreter()
        self.whatsapp_flow = WhatsAppFlowService(session)

    def ingest_webhook(self, payload: IncomingWebhookEnvelope) -> int:
        processed = 0
        for item in payload.messages:
            existing = self.session.scalar(
                select(IncomingMessage).where(
                    IncomingMessage.external_message_id == item.external_message_id
                )
            )
            if existing:
                continue

            channel = self._get_or_create_channel(item.external_contact_id, item.sender_name)
            message = IncomingMessage(
                external_message_id=item.external_message_id,
                contact_channel=channel,
                direction=MessageDirection.inbound,
                message_type=item.message_type,
                text_content=item.text,
                media_url=item.media_url,
                metadata_json=item.metadata,
                received_at=item.timestamp,
            )
            self.session.add(message)
            self.session.flush()

            raw_event = RawEvent(
                message=message,
                event_type=EventType.incoming_message,
                normalized_payload=item.model_dump(mode="json"),
            )
            self.session.add(raw_event)
            self.session.flush()

            result = self.interpreter.interpret(message)
            interpretation = Interpretation(
                raw_event=raw_event,
                intent=result.intent,
                confidence=result.confidence,
                extracted_entities=result.extracted_entities,
                reasoning=result.reasoning,
                status=(
                    InterpretationStatus.pending_confirmation
                    if result.requires_confirmation
                    else InterpretationStatus.auto_applied
                ),
                domain_fact_type=result.domain_fact_type,
            )
            self.session.add(interpretation)
            self.session.flush()
            self.whatsapp_flow.handle_interpretation(interpretation)
            processed += 1

        self.session.commit()
        return processed

    def _get_or_create_channel(self, external_contact_id: str, sender_name: str | None) -> ContactChannel:
        channel = self.session.scalar(
            select(ContactChannel).where(
                ContactChannel.channel_type == ChannelType.whatsapp,
                ContactChannel.external_contact_id == external_contact_id,
            )
        )
        if channel:
            return channel

        channel = ContactChannel(
            channel_type=ChannelType.whatsapp,
            external_contact_id=external_contact_id,
            label=sender_name,
        )
        self.session.add(channel)
        self.session.flush()
        return channel
