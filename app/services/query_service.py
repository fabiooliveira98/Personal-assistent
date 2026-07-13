from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.domain.enums import AgendaItemStatus, BillingPeriodStatus
from app.domain.models import AgendaItem, BillingPeriod, Payment, ReplacementCredit, Student
from app.domain.schemas import OperationalQueryRequest, OperationalQueryResponse


class QueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def answer(self, request: OperationalQueryRequest) -> OperationalQueryResponse:
        return self._answer_internal(request.question, request.reference_datetime or datetime.now())

    def answer_from_whatsapp(self, question: str) -> OperationalQueryResponse:
        return self._answer_internal(question, datetime.now())

    def _answer_internal(self, question: str, reference: datetime) -> OperationalQueryResponse:
        question = question.strip()
        lowered = question.lower()

        if "quem ainda nao pagou" in lowered:
            return self._who_has_not_paid(reference)
        if "quanto entrou" in lowered:
            return self._how_much_entered(reference)
        if "ja pagou" in lowered:
            return self._student_paid(question, reference)
        if "quanto esse aluno deve" in lowered or "quanto o " in lowered and " deve" in lowered:
            return self._student_balance(question, reference)
        if "quantas reposi" in lowered:
            return self._replacement_balance(question)
        if "o que tenho hoje" in lowered:
            return self._schedule_for_time(question, reference)

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question not supported yet.",
        )

    def _who_has_not_paid(self, reference: datetime) -> OperationalQueryResponse:
        open_period_subquery = select(BillingPeriod.student_id).where(
            BillingPeriod.status != BillingPeriodStatus.paid
        )
        students = self.session.scalars(
            select(Student).where(Student.active.is_(True), Student.id.in_(open_period_subquery))
        ).all()
        names = [student.full_name for student in students]
        answer = "Todos os alunos com fechamento registrado estao pagos." if not names else ", ".join(names)
        return OperationalQueryResponse(
            intent="who_has_not_paid",
            answer=answer,
            data={"students": names, "reference_month": reference.month, "reference_year": reference.year},
        )

    def _how_much_entered(self, reference: datetime) -> OperationalQueryResponse:
        total = self.session.scalar(
            select(func.coalesce(func.sum(Payment.amount), Decimal("0.00"))).where(
                extract("month", Payment.paid_at) == reference.month,
                extract("year", Payment.paid_at) == reference.year,
            )
        )
        total_value = float(total or 0)
        return OperationalQueryResponse(
            intent="how_much_entered",
            answer=f"Entrou R$ {total_value:.2f} no mes.",
            data={"total": total_value, "reference_month": reference.month, "reference_year": reference.year},
        )

    def _student_paid(self, question: str, reference: datetime) -> OperationalQueryResponse:
        student_name = self._extract_student_name(question)
        student = self._find_student(student_name)
        billing_period = self.session.scalar(
            select(BillingPeriod)
            .where(BillingPeriod.student_id == student.id)
            .order_by(BillingPeriod.period_end.desc())
        )
        paid = billing_period is not None and billing_period.status == BillingPeriodStatus.paid
        return OperationalQueryResponse(
            intent="student_paid",
            answer=f"{student.full_name} {'ja pagou' if paid else 'ainda nao pagou'} o ultimo fechamento.",
            data={"student": student.full_name, "paid": paid},
        )

    def _student_balance(self, question: str, reference: datetime) -> OperationalQueryResponse:
        student_name = self._extract_student_name(question)
        student = self._find_student(student_name)
        billing_period = self.session.scalar(
            select(BillingPeriod)
            .where(BillingPeriod.student_id == student.id)
            .order_by(BillingPeriod.period_end.desc())
        )
        if not billing_period:
            return OperationalQueryResponse(
                intent="student_balance",
                answer=f"Nao ha fechamento registrado para {student.full_name}.",
                data={"student": student.full_name, "balance": 0.0},
            )
        balance = float(billing_period.amount_due - billing_period.amount_paid)
        return OperationalQueryResponse(
            intent="student_balance",
            answer=f"{student.full_name} deve R$ {balance:.2f} no fechamento {billing_period.label}.",
            data={
                "student": student.full_name,
                "period_label": billing_period.label,
                "amount_due": float(billing_period.amount_due),
                "amount_paid": float(billing_period.amount_paid),
                "balance": balance,
            },
        )

    def _replacement_balance(self, question: str) -> OperationalQueryResponse:
        student_name = self._extract_student_name(question)
        student = self._find_student(student_name)
        balance = self.session.scalar(
            select(
                func.coalesce(
                    func.sum(ReplacementCredit.quantity - ReplacementCredit.consumed_quantity),
                    0,
                )
            ).where(ReplacementCredit.student_id == student.id)
        )
        balance_value = int(balance or 0)
        return OperationalQueryResponse(
            intent="replacement_balance",
            answer=f"{student.full_name} possui {balance_value} reposicao(oes) disponivel(is).",
            data={"student": student.full_name, "balance": balance_value},
        )

    def _schedule_for_time(self, question: str, reference: datetime) -> OperationalQueryResponse:
        match = re.search(r"(\d{1,2})[:h](\d{2})", question.lower())
        if not match:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Question must include a time, for example 17:00.",
            )
        hour = int(match.group(1))
        minute = int(match.group(2))
        agenda_item = self.session.scalar(
            select(AgendaItem).where(
                AgendaItem.scheduled_date == reference.date(),
                AgendaItem.status == AgendaItemStatus.scheduled,
                extract("hour", AgendaItem.scheduled_time) == hour,
                extract("minute", AgendaItem.scheduled_time) == minute,
            )
        )
        if not agenda_item:
            return OperationalQueryResponse(
                intent="schedule_lookup",
                answer=f"Nao ha compromisso agendado hoje as {hour:02d}:{minute:02d}.",
                data={"scheduled": False},
            )
        return OperationalQueryResponse(
            intent="schedule_lookup",
            answer=f"Hoje as {hour:02d}:{minute:02d}: {agenda_item.title}.",
            data={
                "scheduled": True,
                "title": agenda_item.title,
                "student_id": agenda_item.student_id,
            },
        )

    def _extract_student_name(self, question: str) -> str:
        matches = re.findall(r"\b([A-Z][a-z]+)\b", question)
        if not matches:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not infer student name from question.",
            )
        ignored_tokens = {"Quanto", "Quantas", "Quem", "O", "Hoje"}
        filtered = [match for match in matches if match not in ignored_tokens]
        if filtered:
            return filtered[-1]
        return matches[-1]

    def _find_student(self, student_name: str) -> Student:
        student = self.session.scalar(select(Student).where(Student.full_name.ilike(f"{student_name}%")))
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student '{student_name}' not found.",
            )
        return student
