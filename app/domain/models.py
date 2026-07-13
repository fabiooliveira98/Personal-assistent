from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import (
    AgendaItemStatus,
    BillingPeriodStatus,
    ChannelType,
    EventType,
    InterpretationStatus,
    IntentType,
    MessageDirection,
    OutboundMessageStatus,
)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), index=True)
    default_lesson_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    contacts: Mapped[list[ContactChannel]] = relationship(back_populates="student")
    notes: Mapped[list[StudentNote]] = relationship(back_populates="student")
    payments: Mapped[list[Payment]] = relationship(back_populates="student")
    replacement_credits: Mapped[list[ReplacementCredit]] = relationship(back_populates="student")
    agenda_items: Mapped[list[AgendaItem]] = relationship(back_populates="student")
    billing_periods: Mapped[list[BillingPeriod]] = relationship(back_populates="student")


class ContactChannel(Base):
    __tablename__ = "contact_channels"
    __table_args__ = (UniqueConstraint("channel_type", "external_contact_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    channel_type: Mapped[ChannelType] = mapped_column(Enum(ChannelType), nullable=False)
    external_contact_id: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    student: Mapped[Student | None] = relationship(back_populates="contacts")
    messages: Mapped[list[IncomingMessage]] = relationship(back_populates="contact_channel")


class IncomingMessage(Base):
    __tablename__ = "incoming_messages"
    __table_args__ = (UniqueConstraint("external_message_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_message_id: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_channel_id: Mapped[int | None] = mapped_column(ForeignKey("contact_channels.id"), nullable=True)
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection),
        default=MessageDirection.inbound,
        nullable=False,
    )
    message_type: Mapped[str] = mapped_column(String(40), default="text", nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    contact_channel: Mapped[ContactChannel | None] = relationship(back_populates="messages")
    raw_events: Mapped[list[RawEvent]] = relationship(back_populates="message")


class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("incoming_messages.id"), nullable=False)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    normalized_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    message: Mapped[IncomingMessage] = relationship(back_populates="raw_events")
    interpretations: Mapped[list[Interpretation]] = relationship(back_populates="raw_event")


class Interpretation(Base):
    __tablename__ = "interpretations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_event_id: Mapped[int] = mapped_column(ForeignKey("raw_events.id"), nullable=False)
    intent: Mapped[IntentType] = mapped_column(Enum(IntentType), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    extracted_entities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[InterpretationStatus] = mapped_column(
        Enum(InterpretationStatus),
        default=InterpretationStatus.pending_confirmation,
        nullable=False,
    )
    domain_fact_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    raw_event: Mapped[RawEvent] = relationship(back_populates="interpretations")
    confirmations: Mapped[list[Confirmation]] = relationship(back_populates="interpretation")
    outbound_messages: Mapped[list[OutboundMessage]] = relationship(back_populates="interpretation")


class Confirmation(Base):
    __tablename__ = "confirmations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interpretation_id: Mapped[int] = mapped_column(ForeignKey("interpretations.id"), nullable=False)
    decision: Mapped[InterpretationStatus] = mapped_column(Enum(InterpretationStatus), nullable=False)
    corrected_entities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    interpretation: Mapped[Interpretation] = relationship(back_populates="confirmations")


class BillingPeriod(Base):
    __tablename__ = "billing_periods"
    __table_args__ = (UniqueConstraint("student_id", "period_start", "period_end"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[BillingPeriodStatus] = mapped_column(
        Enum(BillingPeriodStatus),
        default=BillingPeriodStatus.awaiting_review,
        nullable=False,
    )
    lesson_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    replacement_lesson_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    student: Mapped[Student] = relationship(back_populates="billing_periods")
    payments: Mapped[list[Payment]] = relationship(back_populates="billing_period")
    agenda_items: Mapped[list[AgendaItem]] = relationship(back_populates="billing_period")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    billing_period_id: Mapped[int | None] = mapped_column(ForeignKey("billing_periods.id"), nullable=True)
    interpretation_id: Mapped[int | None] = mapped_column(ForeignKey("interpretations.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    paid_at: Mapped[date] = mapped_column(Date, default=date.today)
    payment_method: Mapped[str] = mapped_column(String(40), default="pix", nullable=False)
    source_message_id: Mapped[int | None] = mapped_column(ForeignKey("incoming_messages.id"), nullable=True)

    student: Mapped[Student] = relationship(back_populates="payments")
    billing_period: Mapped[BillingPeriod | None] = relationship(back_populates="payments")


class PixReceipt(Base):
    __tablename__ = "pix_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("incoming_messages.id"), nullable=False)
    extracted_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    extracted_payer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgendaItem(Base):
    __tablename__ = "agenda_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    billing_period_id: Mapped[int | None] = mapped_column(ForeignKey("billing_periods.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    lesson_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[AgendaItemStatus] = mapped_column(
        Enum(AgendaItemStatus),
        default=AgendaItemStatus.scheduled,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    student: Mapped[Student | None] = relationship(back_populates="agenda_items")
    billing_period: Mapped[BillingPeriod | None] = relationship(back_populates="agenda_items")


class LessonCancellation(Base):
    __tablename__ = "lesson_cancellations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    agenda_item_id: Mapped[int | None] = mapped_column(ForeignKey("agenda_items.id"), nullable=True)
    interpretation_id: Mapped[int | None] = mapped_column(ForeignKey("interpretations.id"), nullable=True)
    lesson_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lesson_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    hours_before_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counts_as_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    eligible_for_replacement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancelled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReplacementCredit(Base):
    __tablename__ = "replacement_credits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    source_cancellation_id: Mapped[int | None] = mapped_column(ForeignKey("lesson_cancellations.id"), nullable=True)
    interpretation_id: Mapped[int | None] = mapped_column(ForeignKey("interpretations.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    consumed_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    decided_by_personal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    student: Mapped[Student] = relationship(back_populates="replacement_credits")


class Reschedule(Base):
    __tablename__ = "reschedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    old_agenda_item_id: Mapped[int | None] = mapped_column(ForeignKey("agenda_items.id"), nullable=True)
    new_agenda_item_id: Mapped[int | None] = mapped_column(ForeignKey("agenda_items.id"), nullable=True)
    interpretation_id: Mapped[int | None] = mapped_column(ForeignKey("interpretations.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StudentNote(Base):
    __tablename__ = "student_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    interpretation_id: Mapped[int | None] = mapped_column(ForeignKey("interpretations.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    student: Mapped[Student] = relationship(back_populates="notes")


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interpretation_id: Mapped[int | None] = mapped_column(ForeignKey("interpretations.id"), nullable=True)
    recipient_contact_id: Mapped[str] = mapped_column(String(120), nullable=False)
    recipient_role: Mapped[str] = mapped_column(String(40), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OutboundMessageStatus] = mapped_column(
        Enum(OutboundMessageStatus),
        default=OutboundMessageStatus.pending,
        nullable=False,
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    interpretation: Mapped[Interpretation | None] = relationship(back_populates="outbound_messages")
