from __future__ import annotations

from datetime import datetime
from urllib import error, request
import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import OutboundMessageStatus
from app.domain.models import OutboundMessage


class WhatsAppMessagingService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def queue_message(
        self,
        recipient_contact_id: str,
        recipient_role: str,
        body: str,
        interpretation_id: int | None = None,
    ) -> OutboundMessage:
        message = OutboundMessage(
            recipient_contact_id=recipient_contact_id,
            recipient_role=recipient_role,
            body=body,
            interpretation_id=interpretation_id,
        )
        self.session.add(message)
        self.session.flush()

        if settings.whatsapp_send_enabled and recipient_contact_id:
            self._send_message(message)

        return message

    def _send_message(self, message: OutboundMessage) -> None:
        if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
            message.status = OutboundMessageStatus.failed
            message.error_message = "WhatsApp credentials are not configured."
            return

        endpoint = (
            f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
            f"{settings.whatsapp_phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": message.recipient_contact_id,
            "type": "text",
            "text": {"preview_url": False, "body": message.body},
        }
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {settings.whatsapp_access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=10) as response:
                body = json.loads(response.read().decode("utf-8"))
            provider_message_id = (
                body.get("messages", [{}])[0].get("id")
                if isinstance(body, dict)
                else None
            )
            message.status = OutboundMessageStatus.sent
            message.provider_message_id = provider_message_id
            message.sent_at = datetime.utcnow()
        except error.URLError as exc:
            message.status = OutboundMessageStatus.failed
            message.error_message = str(exc)
