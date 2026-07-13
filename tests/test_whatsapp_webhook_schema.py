from datetime import datetime

from app.domain.schemas import normalize_whatsapp_webhook


def test_normalizes_meta_cloud_api_payload() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "1234567890",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Ana"},
                                    "wa_id": "5511999999999",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "5511999999999",
                                    "id": "wamid.TEST123",
                                    "timestamp": "1783936800",
                                    "type": "text",
                                    "text": {"body": "Oi, consegui pagar"},
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }

    normalized = normalize_whatsapp_webhook(payload)

    assert normalized.object == "whatsapp_business_account"
    assert len(normalized.messages) == 1
    assert normalized.messages[0].external_message_id == "wamid.TEST123"
    assert normalized.messages[0].external_contact_id == "5511999999999"
    assert normalized.messages[0].sender_name == "Ana"
    assert normalized.messages[0].text == "Oi, consegui pagar"
    assert normalized.messages[0].timestamp == datetime(2026, 7, 13, 10, 0, 0)
