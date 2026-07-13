from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import AgendaItemStatus, ChannelType
from app.domain.models import AgendaItem, ContactChannel, Student
from app.domain.schemas import AgendaItemCreateRequest, StudentCreateRequest


class BootstrapService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_student(self, request: StudentCreateRequest) -> Student:
        existing_channel = self.session.scalar(
            select(ContactChannel).where(
                ContactChannel.channel_type == ChannelType.whatsapp,
                ContactChannel.external_contact_id == request.whatsapp_contact_id,
            )
        )
        if existing_channel:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="WhatsApp contact is already linked to another student.",
            )

        student = Student(
            full_name=request.full_name,
            default_lesson_price=Decimal(str(request.default_lesson_price)),
            active=request.active,
        )
        self.session.add(student)
        self.session.flush()

        channel = ContactChannel(
            student_id=student.id,
            channel_type=ChannelType.whatsapp,
            external_contact_id=request.whatsapp_contact_id,
            label=request.full_name,
        )
        self.session.add(channel)
        self.session.commit()
        self.session.refresh(student)
        return student

    def create_agenda_item(self, request: AgendaItemCreateRequest) -> AgendaItem:
        student = self.session.get(Student, request.student_id)
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

        agenda_item = AgendaItem(
            student_id=student.id,
            title=request.title,
            scheduled_date=request.scheduled_date,
            scheduled_time=request.scheduled_time,
            duration_minutes=request.duration_minutes,
            lesson_price=(
                Decimal(str(request.lesson_price))
                if request.lesson_price is not None
                else student.default_lesson_price
            ),
            status=AgendaItemStatus.scheduled,
            notes=request.notes,
        )
        self.session.add(agenda_item)
        self.session.commit()
        self.session.refresh(agenda_item)
        return agenda_item
