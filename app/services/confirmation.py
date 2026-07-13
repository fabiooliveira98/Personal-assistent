from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import AgendaItemStatus, InterpretationStatus, IntentType
from app.domain.models import AgendaItem, Confirmation, IncomingMessage, Interpretation, LessonCancellation, Payment, ReplacementCredit, Student, StudentNote
from app.domain.schemas import ConfirmationDecisionRequest
from app.services.domain_logic import DomainLogicService
from app.services.whatsapp import WhatsAppMessagingService


class ConfirmationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.domain_logic = DomainLogicService(session)
        self.messaging = WhatsAppMessagingService(session)

    def apply_decision(
        self,
        interpretation_id: int,
        request: ConfirmationDecisionRequest,
    ) -> Interpretation:
        interpretation = self.session.get(Interpretation, interpretation_id)
        if not interpretation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interpretation not found.")

        status_map = {
            "confirmed": InterpretationStatus.confirmed,
            "rejected": InterpretationStatus.rejected,
            "corrected": InterpretationStatus.corrected,
        }
        new_status = status_map[request.decision]
        final_entities = dict(interpretation.extracted_entities)
        final_entities.update(request.corrected_entities)

        confirmation = Confirmation(
            interpretation=interpretation,
            decision=new_status,
            corrected_entities=request.corrected_entities,
            notes=request.notes,
        )
        interpretation.status = new_status
        interpretation.extracted_entities = final_entities
        self.session.add(confirmation)

        if new_status in {InterpretationStatus.confirmed, InterpretationStatus.corrected}:
            self._apply_domain_fact(interpretation, final_entities)

        self._queue_confirmation_result(interpretation, final_entities)

        self.session.commit()
        self.session.refresh(interpretation)
        return interpretation

    def _apply_domain_fact(self, interpretation: Interpretation, entities: dict) -> None:
        message = interpretation.raw_event.message
        if interpretation.intent == IntentType.payment_notice:
            self._create_payment(interpretation, message, entities)
            return
        if interpretation.intent == IntentType.pix_receipt:
            self._create_payment(interpretation, message, entities)
            return
        if interpretation.intent == IntentType.cancellation_request:
            self._create_cancellation(interpretation, entities)
            return
        if interpretation.intent == IntentType.replacement_request:
            self._create_replacement_credit(interpretation, entities)
            return
        if interpretation.intent == IntentType.schedule_change:
            self._reschedule_agenda_item(interpretation, entities)
            return
        if interpretation.intent == IntentType.student_note:
            self._create_student_note(interpretation, entities)

    def _create_payment(self, interpretation: Interpretation, message: IncomingMessage, entities: dict) -> None:
        student = self._resolve_student(entities.get("student_name"))
        amount = Decimal(str(entities.get("amount") or "0.00"))
        period_start, period_end = self._resolve_billing_period_dates(entities)
        billing_period = self.domain_logic.get_or_create_billing_period(student, period_start, period_end)

        payment = Payment(
            student_id=student.id,
            billing_period_id=billing_period.id,
            interpretation_id=interpretation.id,
            amount=amount,
            paid_at=self._resolve_paid_at(entities),
            payment_method="pix",
            source_message_id=message.id,
        )
        self.session.add(payment)
        self.session.flush()
        self.domain_logic.recalculate_billing_period(billing_period)

    def _create_cancellation(self, interpretation: Interpretation, entities: dict) -> None:
        student = self._resolve_student(entities.get("student_name"))
        lesson_date = self._parse_date(entities.get("lesson_date"))
        lesson_time = self._parse_time(entities.get("lesson_time"))
        cancelled_at = self._resolve_cancelled_at(entities)
        hours_before_start, counts_as_completed, eligible_for_replacement = self.domain_logic.evaluate_cancellation(
            lesson_date,
            lesson_time,
            cancelled_at,
        )
        agenda_item = self.domain_logic.apply_counted_lesson_to_agenda(student, lesson_date, lesson_time)
        cancellation = LessonCancellation(
            student_id=student.id,
            agenda_item_id=agenda_item.id if agenda_item else None,
            interpretation_id=interpretation.id,
            lesson_date=lesson_date,
            lesson_time=lesson_time,
            hours_before_start=hours_before_start,
            counts_as_completed=counts_as_completed,
            eligible_for_replacement=eligible_for_replacement,
            cancelled_at=cancelled_at,
            reason=entities.get("raw_text"),
        )
        self.session.add(cancellation)
        self.session.flush()
        if eligible_for_replacement and entities.get("grant_replacement") is True:
            self._create_replacement_credit(
                interpretation,
                {
                    **entities,
                    "student_name": student.full_name,
                    "source_cancellation_id": cancellation.id,
                },
            )
        elif counts_as_completed:
            period_start, period_end = self._resolve_billing_period_dates(entities)
            billing_period = self.domain_logic.get_or_create_billing_period(student, period_start, period_end)
            if agenda_item:
                agenda_item.billing_period_id = billing_period.id
                agenda_item.status = AgendaItemStatus.counted_as_completed
            self.domain_logic.recalculate_billing_period(billing_period)

    def _create_replacement_credit(self, interpretation: Interpretation, entities: dict) -> None:
        student = self._resolve_student(entities.get("student_name"))
        credit = ReplacementCredit(
            student_id=student.id,
            source_cancellation_id=entities.get("source_cancellation_id"),
            interpretation_id=interpretation.id,
            quantity=int(entities.get("quantity") or 1),
            expires_on=self._parse_date(entities.get("replacement_expires_on")),
            decided_by_personal=True,
        )
        self.session.add(credit)

    def _create_student_note(self, interpretation: Interpretation, entities: dict) -> None:
        student = self._resolve_student(entities.get("student_name"))
        note = StudentNote(
            student_id=student.id,
            interpretation_id=interpretation.id,
            content=entities.get("content") or entities.get("raw_text") or "",
        )
        self.session.add(note)

    def _resolve_student(self, student_name: str | None) -> Student:
        if not student_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Student resolution failed. Confirmation must include student_name.",
            )

        student = self.session.scalar(select(Student).where(Student.full_name.ilike(f"{student_name}%")))
        if student:
            return student

        student = Student(full_name=student_name)
        self.session.add(student)
        self.session.flush()
        return student

    def _reschedule_agenda_item(self, interpretation: Interpretation, entities: dict) -> None:
        student = self._resolve_student(entities.get("student_name"))
        lesson_date = self._parse_date(entities.get("lesson_date"))
        lesson_time = self._parse_time(entities.get("lesson_time"))
        new_date = self._parse_date(entities.get("new_lesson_date"))
        new_time = self._parse_time(entities.get("new_lesson_time"))
        if not lesson_date or not lesson_time or not new_date or not new_time:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Reschedule confirmation requires old and new lesson date/time.",
            )

        agenda_item = self.session.scalar(
            select(AgendaItem).where(
                AgendaItem.student_id == student.id,
                AgendaItem.scheduled_date == lesson_date,
                AgendaItem.scheduled_time == lesson_time,
            )
        )
        if not agenda_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agenda item not found.")

        agenda_item.status = AgendaItemStatus.rescheduled
        new_item = AgendaItem(
            student_id=student.id,
            title=agenda_item.title,
            scheduled_date=new_date,
            scheduled_time=new_time,
            duration_minutes=agenda_item.duration_minutes,
            lesson_price=agenda_item.lesson_price,
            notes=(agenda_item.notes or "") + " Remarcada.",
        )
        self.session.add(new_item)

    def _resolve_billing_period_dates(self, entities: dict) -> tuple[date, date]:
        period_start = self._parse_date(entities.get("billing_period_start"))
        period_end = self._parse_date(entities.get("billing_period_end"))
        if period_start and period_end:
            return period_start, period_end
        return self.domain_logic.infer_previous_month_period()

    def _resolve_paid_at(self, entities: dict) -> date:
        return self._parse_date(entities.get("paid_at")) or date.today()

    def _resolve_cancelled_at(self, entities: dict) -> datetime:
        raw = entities.get("cancelled_at")
        if not raw:
            return datetime.utcnow()
        return datetime.fromisoformat(str(raw))

    def _parse_date(self, raw_value: object) -> date | None:
        if not raw_value:
            return None
        if isinstance(raw_value, date):
            return raw_value
        return date.fromisoformat(str(raw_value))

    def _parse_time(self, raw_value: object) -> datetime.time | None:
        if not raw_value:
            return None
        if isinstance(raw_value, datetime):
            return raw_value.time()
        return datetime.strptime(str(raw_value), "%H:%M").time()

    def _queue_confirmation_result(self, interpretation: Interpretation, entities: dict) -> None:
        personal_contact_id = (
            interpretation.raw_event.message.metadata_json.get("personal_contact_id")
            or interpretation.raw_event.normalized_payload.get("personal_contact_id")
            or settings.personal_whatsapp_contact_id
        )
        if not personal_contact_id:
            return
        self.messaging.queue_message(
            recipient_contact_id=personal_contact_id,
            recipient_role="personal",
            body=self._build_confirmation_result_text(interpretation, entities),
            interpretation_id=interpretation.id,
        )

    def _build_confirmation_result_text(self, interpretation: Interpretation, entities: dict) -> str:
        if interpretation.status == InterpretationStatus.rejected:
            return f"Interpretacao #{interpretation.id} rejeitada."
        student_name = entities.get("student_name", "aluno")
        if interpretation.intent in {IntentType.payment_notice, IntentType.pix_receipt}:
            return f"Pagamento confirmado para {student_name}."
        if interpretation.intent == IntentType.cancellation_request:
            return f"Cancelamento registrado para {student_name}."
        if interpretation.intent == IntentType.replacement_request:
            return f"Reposicao registrada para {student_name}."
        if interpretation.intent == IntentType.schedule_change:
            return f"Remarcacao registrada para {student_name}."
        return f"Interpretacao #{interpretation.id} confirmada."
