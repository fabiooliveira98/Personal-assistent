from enum import Enum


class ChannelType(str, Enum):
    whatsapp = "whatsapp"


class MessageDirection(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class EventType(str, Enum):
    incoming_message = "incoming_message"


class IntentType(str, Enum):
    payment_notice = "payment_notice"
    pix_receipt = "pix_receipt"
    cancellation_request = "cancellation_request"
    replacement_request = "replacement_request"
    schedule_change = "schedule_change"
    student_note = "student_note"
    operational_query = "operational_query"
    confirmation_command = "confirmation_command"
    unknown = "unknown"


class InterpretationStatus(str, Enum):
    pending_confirmation = "pending_confirmation"
    confirmed = "confirmed"
    rejected = "rejected"
    corrected = "corrected"
    auto_applied = "auto_applied"


class AgendaItemStatus(str, Enum):
    scheduled = "scheduled"
    cancelled = "cancelled"
    completed = "completed"
    rescheduled = "rescheduled"
    counted_as_completed = "counted_as_completed"


class BillingPeriodStatus(str, Enum):
    open = "open"
    awaiting_review = "awaiting_review"
    closed = "closed"
    partially_paid = "partially_paid"
    paid = "paid"


class OutboundMessageStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
