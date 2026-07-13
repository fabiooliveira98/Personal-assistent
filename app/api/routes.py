from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import check_database_connection, get_session
from app.domain.schemas import (
    AgendaItemCreateRequest,
    AgendaItemResponse,
    BillingSummaryResponse,
    ConfirmationDecisionRequest,
    HealthResponse,
    normalize_whatsapp_webhook,
    OutboundMessageResponse,
    OperationalQueryRequest,
    OperationalQueryResponse,
    PendingInterpretationResponse,
    StudentCreateRequest,
    StudentResponse,
    WebhookVerificationResponse,
)
from app.domain.enums import InterpretationStatus
from app.domain.models import BillingPeriod, Interpretation, OutboundMessage
from app.services.bootstrap import BootstrapService
from app.services.confirmation import ConfirmationService
from app.services.ingestion import IngestionService
from app.services.query_service import QueryService

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    database_status = "connected" if check_database_connection() else "disconnected"
    status_label = "ok" if database_status == "connected" else "degraded"
    return HealthResponse(
        status=status_label,
        environment=settings.app_env,
        database=database_status,
    )


@router.get("/webhooks/whatsapp", response_model=WebhookVerificationResponse)
def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> WebhookVerificationResponse:
    if hub_mode != "subscribe" or hub_verify_token != settings.whatsapp_verify_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid WhatsApp verification request.",
        )
    return WebhookVerificationResponse(challenge=hub_challenge)


@router.post("/webhooks/whatsapp", status_code=status.HTTP_202_ACCEPTED)
def receive_whatsapp_webhook(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, object]:
    service = IngestionService(session)
    normalized_payload = normalize_whatsapp_webhook(payload)
    processed = service.ingest_webhook(normalized_payload)
    return {"accepted": True, "processed_messages": processed}


@router.post("/confirmations/{interpretation_id}")
def confirm_interpretation(
    interpretation_id: int,
    request: ConfirmationDecisionRequest,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    service = ConfirmationService(session)
    interpretation = service.apply_decision(interpretation_id, request)
    return {
        "interpretation_id": interpretation.id,
        "status": interpretation.status.value,
        "domain_fact_type": interpretation.domain_fact_type,
    }


@router.post("/queries", response_model=OperationalQueryResponse)
def operational_query(
    request: OperationalQueryRequest,
    session: Session = Depends(get_session),
) -> OperationalQueryResponse:
    service = QueryService(session)
    return service.answer(request)


@router.post("/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def create_student(
    request: StudentCreateRequest,
    session: Session = Depends(get_session),
) -> StudentResponse:
    service = BootstrapService(session)
    student = service.create_student(request)
    contact_id = next(
        (
            channel.external_contact_id
            for channel in student.contacts
            if channel.channel_type.value == "whatsapp"
        ),
        "",
    )
    return StudentResponse(
        id=student.id,
        full_name=student.full_name,
        whatsapp_contact_id=contact_id,
        default_lesson_price=float(student.default_lesson_price),
        active=student.active,
    )


@router.post("/agenda", response_model=AgendaItemResponse, status_code=status.HTTP_201_CREATED)
def create_agenda_item(
    request: AgendaItemCreateRequest,
    session: Session = Depends(get_session),
) -> AgendaItemResponse:
    service = BootstrapService(session)
    item = service.create_agenda_item(request)
    return AgendaItemResponse(
        id=item.id,
        student_id=item.student_id,
        title=item.title,
        scheduled_date=item.scheduled_date,
        scheduled_time=item.scheduled_time,
        duration_minutes=item.duration_minutes,
        status=item.status.value,
        lesson_price=float(item.lesson_price) if item.lesson_price is not None else None,
        notes=item.notes,
    )


@router.get("/interpretations/pending", response_model=list[PendingInterpretationResponse])
def list_pending_interpretations(session: Session = Depends(get_session)) -> list[PendingInterpretationResponse]:
    items = (
        session.query(Interpretation)
        .filter(Interpretation.status == InterpretationStatus.pending_confirmation)
        .order_by(Interpretation.created_at.desc())
        .all()
    )
    return [
        PendingInterpretationResponse(
            interpretation_id=item.id,
            intent=item.intent.value,
            confidence=float(item.confidence),
            status=item.status.value,
            student_name=item.extracted_entities.get("student_name"),
            raw_text=item.extracted_entities.get("raw_text"),
            suggested_reply=(
                f"CONFIRMAR #{item.id}"
                if item.status.value == "pending_confirmation"
                else None
            ),
        )
        for item in items
    ]


@router.get("/outbox", response_model=list[OutboundMessageResponse])
def list_outbound_messages(session: Session = Depends(get_session)) -> list[OutboundMessageResponse]:
    items = session.query(OutboundMessage).order_by(OutboundMessage.created_at.desc()).all()
    return [
        OutboundMessageResponse(
            id=item.id,
            recipient_contact_id=item.recipient_contact_id,
            recipient_role=item.recipient_role,
            body=item.body,
            status=item.status.value,
        )
        for item in items
    ]


@router.get("/billing-periods/{student_id}/latest", response_model=BillingSummaryResponse)
def latest_billing_summary(student_id: int, session: Session = Depends(get_session)) -> BillingSummaryResponse:
    billing_period = (
        session.query(BillingPeriod)
        .filter(BillingPeriod.student_id == student_id)
        .order_by(BillingPeriod.period_end.desc())
        .first()
    )
    if not billing_period:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Billing period not found.")
    return BillingSummaryResponse(
        student=billing_period.student.full_name,
        period_label=billing_period.label,
        lesson_count=billing_period.lesson_count,
        amount_due=float(billing_period.amount_due),
        amount_paid=float(billing_period.amount_paid),
        balance=float(billing_period.amount_due - billing_period.amount_paid),
    )
