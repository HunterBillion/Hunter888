"""Exam & Certificate models."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    level = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="in_progress")  # in_progress | passed | failed
    total_questions = Column(Integer, nullable=False, default=0)
    correct_answers = Column(Integer, nullable=False, default=0)
    score = Column(Float, nullable=True)
    pass_threshold = Column(Float, nullable=False, default=70.0)
    questions_data = Column(JSONB, nullable=True)
    answers_data = Column(JSONB, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    certificate_id = Column(UUID(as_uuid=True), ForeignKey("certificates.id"), nullable=True)

    certificate = relationship("Certificate", back_populates="exam_attempt", foreign_keys=[certificate_id])


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    exam_attempt_id = Column(UUID(as_uuid=True), nullable=True)
    level = Column(Integer, nullable=False)
    level_name = Column(String(100), nullable=False, default="")
    score = Column(Float, nullable=False)
    pdf_path = Column(Text, nullable=True)
    serial_number = Column(String(50), unique=True, nullable=False)
    issued_at = Column(DateTime, default=datetime.utcnow)

    exam_attempt = relationship("ExamAttempt", back_populates="certificate", foreign_keys=[ExamAttempt.certificate_id])
