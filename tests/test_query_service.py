from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.domain.enums import AgendaItemStatus
from app.domain.enums import BillingPeriodStatus
from app.domain.models import AgendaItem, BillingPeriod, Payment, ReplacementCredit, Student
from app.domain.schemas import OperationalQueryRequest
from app.services.query_service import QueryService


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, future=True)
    return session_factory()


def test_answers_how_much_entered() -> None:
    session = build_session()
    student = Student(full_name="Joao", default_lesson_price=Decimal("125.00"))
    billing_period = BillingPeriod(
        student=student,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        label="2026-06-01 a 2026-06-30",
        status=BillingPeriodStatus.partially_paid,
        lesson_count=2,
        amount_due=Decimal("250.00"),
    )
    payment = Payment(
        student=student,
        billing_period=billing_period,
        amount=Decimal("250.00"),
        paid_at=date(2026, 7, 10),
        payment_method="pix",
    )
    session.add_all([student, billing_period, payment])
    session.commit()

    service = QueryService(session)
    response = service.answer(
        OperationalQueryRequest(
            question="Quanto entrou esse mes?",
            reference_datetime=datetime(2026, 7, 13, 10, 0, 0),
        )
    )

    assert response.intent == "how_much_entered"
    assert response.data["total"] == 250.0


def test_answers_replacement_balance() -> None:
    session = build_session()
    student = Student(full_name="Maria", default_lesson_price=Decimal("90.00"))
    credit = ReplacementCredit(student=student, quantity=3, consumed_quantity=1)
    session.add_all([student, credit])
    session.commit()

    service = QueryService(session)
    response = service.answer(
        OperationalQueryRequest(question="Quantas reposicoes a Maria possui?")
    )

    assert response.intent == "replacement_balance"
    assert response.data["balance"] == 2


def test_answers_schedule_lookup() -> None:
    session = build_session()
    student = Student(full_name="Ana", default_lesson_price=Decimal("100.00"))
    agenda_item = AgendaItem(
        student=student,
        title="Aula com Ana",
        scheduled_date=date(2026, 7, 13),
        scheduled_time=time(17, 0),
        status=AgendaItemStatus.scheduled,
    )
    session.add_all([student, agenda_item])
    session.commit()

    service = QueryService(session)
    response = service.answer(
        OperationalQueryRequest(
            question="O que tenho hoje as 17:00?",
            reference_datetime=datetime(2026, 7, 13, 8, 0, 0),
        )
    )

    assert response.intent == "schedule_lookup"
    assert response.data["scheduled"] is True


def test_answers_student_balance() -> None:
    session = build_session()
    student = Student(full_name="Carlos", default_lesson_price=Decimal("80.00"))
    billing_period = BillingPeriod(
        student=student,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        label="2026-06-01 a 2026-06-30",
        status=BillingPeriodStatus.partially_paid,
        lesson_count=4,
        amount_due=Decimal("320.00"),
        amount_paid=Decimal("160.00"),
    )
    session.add_all([student, billing_period])
    session.commit()

    service = QueryService(session)
    response = service.answer(
        OperationalQueryRequest(
            question="Quanto esse aluno deve Carlos?",
            reference_datetime=datetime(2026, 7, 13, 8, 0, 0),
        )
    )

    assert response.intent == "student_balance"
    assert response.data["balance"] == 160.0
