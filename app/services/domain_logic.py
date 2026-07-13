from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import AgendaItemStatus, BillingPeriodStatus
from app.domain.models import AgendaItem, BillingPeriod, Payment, Student


class DomainLogicService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_billing_period(
        self,
        student: Student,
        period_start: date,
        period_end: date,
    ) -> BillingPeriod:
        billing_period = self.session.scalar(
            select(BillingPeriod).where(
                BillingPeriod.student_id == student.id,
                BillingPeriod.period_start == period_start,
                BillingPeriod.period_end == period_end,
            )
        )
        if billing_period:
            return billing_period

        billing_period = BillingPeriod(
            student_id=student.id,
            period_start=period_start,
            period_end=period_end,
            label=f"{period_start.isoformat()} a {period_end.isoformat()}",
        )
        self.session.add(billing_period)
        self.session.flush()
        return billing_period

    def infer_previous_month_period(self, reference_date: date | None = None) -> tuple[date, date]:
        reference_date = reference_date or date.today()
        first_day_current_month = reference_date.replace(day=1)
        previous_month_end = first_day_current_month - timedelta(days=1)
        previous_month_start = previous_month_end.replace(day=1)
        return previous_month_start, previous_month_end

    def recalculate_billing_period(self, billing_period: BillingPeriod) -> BillingPeriod:
        lesson_count = self.session.scalar(
            select(func.count(AgendaItem.id)).where(
                AgendaItem.student_id == billing_period.student_id,
                AgendaItem.billing_period_id == billing_period.id,
                AgendaItem.status.in_([AgendaItemStatus.completed, AgendaItemStatus.counted_as_completed]),
            )
        ) or 0

        replacement_lesson_count = self.session.scalar(
            select(func.count(AgendaItem.id)).where(
                AgendaItem.student_id == billing_period.student_id,
                AgendaItem.billing_period_id == billing_period.id,
                AgendaItem.notes.ilike("%reposicao%"),
            )
        ) or 0

        amount_due = self.session.scalar(
            select(func.coalesce(func.sum(AgendaItem.lesson_price), Decimal("0.00"))).where(
                AgendaItem.student_id == billing_period.student_id,
                AgendaItem.billing_period_id == billing_period.id,
                AgendaItem.status.in_([AgendaItemStatus.completed, AgendaItemStatus.counted_as_completed]),
            )
        ) or Decimal("0.00")

        amount_paid = self.session.scalar(
            select(func.coalesce(func.sum(Payment.amount), Decimal("0.00"))).where(
                Payment.billing_period_id == billing_period.id
            )
        ) or Decimal("0.00")

        billing_period.lesson_count = int(lesson_count)
        billing_period.replacement_lesson_count = int(replacement_lesson_count)
        billing_period.amount_due = Decimal(amount_due)
        billing_period.amount_paid = Decimal(amount_paid)
        if billing_period.amount_paid == Decimal("0.00"):
            billing_period.status = BillingPeriodStatus.awaiting_review
        elif billing_period.amount_paid < billing_period.amount_due:
            billing_period.status = BillingPeriodStatus.partially_paid
        else:
            billing_period.status = BillingPeriodStatus.paid
        return billing_period

    def evaluate_cancellation(
        self,
        lesson_date: date | None,
        lesson_time: time | None,
        cancelled_at: datetime,
    ) -> tuple[int | None, bool, bool]:
        if not lesson_date or not lesson_time:
            return None, False, False

        lesson_starts_at = datetime.combine(lesson_date, lesson_time)
        hours_before_start = int((lesson_starts_at - cancelled_at).total_seconds() // 3600)
        counts_as_completed = lesson_starts_at - cancelled_at < timedelta(hours=2)
        eligible_for_replacement = not counts_as_completed
        return hours_before_start, counts_as_completed, eligible_for_replacement

    def apply_counted_lesson_to_agenda(
        self,
        student: Student,
        lesson_date: date | None,
        lesson_time: time | None,
    ) -> AgendaItem | None:
        if not lesson_date or not lesson_time:
            return None
        agenda_item = self.session.scalar(
            select(AgendaItem).where(
                AgendaItem.student_id == student.id,
                AgendaItem.scheduled_date == lesson_date,
                AgendaItem.scheduled_time == lesson_time,
            )
        )
        if agenda_item:
            agenda_item.status = AgendaItemStatus.counted_as_completed
        return agenda_item
