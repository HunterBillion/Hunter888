"""Exam API — level-gate exams with certificate generation."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.exam import Certificate, ExamAttempt
from app.models.user import User
from app.services.exam_service import EXAM_LEVELS, create_exam, get_exam_status, submit_exam

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/exams", tags=["exams"])


class ExamStartRequest(BaseModel):
    level: int


class ExamSubmitRequest(BaseModel):
    attempt_id: str
    answers: list[dict]


@router.get("/levels")
async def get_exam_levels():
    return {"exam_levels": sorted(EXAM_LEVELS)}


@router.get("/status")
async def exam_status(
    level: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if level not in EXAM_LEVELS:
        raise HTTPException(status_code=400, detail=f"Уровень {level} не требует экзамена")
    return await get_exam_status(user.id, level, db)


@router.post("/start")
async def start_exam(
    body: ExamStartRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.level not in EXAM_LEVELS:
        raise HTTPException(status_code=400, detail=f"Уровень {body.level} не требует экзамена")

    current = await get_exam_status(user.id, body.level, db)
    if current["status"] == "in_progress":
        attempt = await db.get(ExamAttempt, uuid.UUID(current["attempt_id"]))
        if attempt:
            questions = (attempt.questions_data or {}).get("questions", [])
            safe_questions = [{"question": q["question"], "options": q["options"], "index": i} for i, q in enumerate(questions)]
            return {"attempt_id": str(attempt.id), "questions": safe_questions, "time_limit": (attempt.questions_data or {}).get("time_limit", 900), "total": len(safe_questions), "resumed": True}

    if current["status"] == "passed":
        raise HTTPException(status_code=400, detail="Экзамен уже сдан")

    attempt = await create_exam(user.id, body.level, db)
    await db.commit()
    questions = (attempt.questions_data or {}).get("questions", [])
    safe_questions = [{"question": q["question"], "options": q["options"], "index": i} for i, q in enumerate(questions)]
    return {"attempt_id": str(attempt.id), "questions": safe_questions, "time_limit": (attempt.questions_data or {}).get("time_limit", 900), "total": len(safe_questions), "resumed": False}


@router.post("/submit")
async def submit_exam_answers(
    body: ExamSubmitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    attempt = await db.get(ExamAttempt, uuid.UUID(body.attempt_id))
    if not attempt:
        raise HTTPException(status_code=404, detail="Экзамен не найден")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    result = await submit_exam(uuid.UUID(body.attempt_id), body.answers, db)
    await db.commit()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/certificate/{cert_id}")
async def download_certificate(
    cert_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cert = await db.get(Certificate, uuid.UUID(cert_id))
    if not cert:
        raise HTTPException(status_code=404, detail="Сертификат не найден")
    if cert.user_id != user.id:
        raise HTTPException(status_code=403)
    if not cert.pdf_path:
        raise HTTPException(status_code=404, detail="PDF не найден")
    import os
    if not os.path.exists(cert.pdf_path):
        from app.services.exam_service import generate_certificate_pdf
        cert.pdf_path = await generate_certificate_pdf(cert)
        await db.commit()
    return FileResponse(cert.pdf_path, media_type="application/pdf", filename=f"certificate_{cert.serial_number}.pdf")


@router.get("/my-certificates")
async def my_certificates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Certificate).where(Certificate.user_id == user.id).order_by(Certificate.level))
    certs = result.scalars().all()
    return {"certificates": [{"id": str(c.id), "level": c.level, "level_name": c.level_name, "score": c.score, "serial_number": c.serial_number, "issued_at": c.issued_at.isoformat() if c.issued_at else None, "has_pdf": bool(c.pdf_path)} for c in certs]}
