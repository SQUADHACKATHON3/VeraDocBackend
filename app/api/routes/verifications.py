from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.verification import Verdict, Verification
from app.schemas.verification import (
    VerificationDetailOut,
    VerificationListItem,
    VerificationListOut,
    issuer_contact_hints_from_ai,
)

router = APIRouter(prefix="/api/verifications", tags=["verifications"])


@router.get("", response_model=VerificationListOut)
def list_verifications(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    verdict: str | None = None,
    search: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VerificationListOut:
    stmt = select(Verification).where(Verification.user_id == user.id)
    count_stmt = select(func.count()).select_from(Verification).where(Verification.user_id == user.id)

    if verdict:
        try:
            verdict_enum = Verdict(verdict)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid verdict filter")
        stmt = stmt.where(Verification.verdict == verdict_enum)
        count_stmt = count_stmt.where(Verification.verdict == verdict_enum)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Verification.document_name.ilike(like))
        count_stmt = count_stmt.where(Verification.document_name.ilike(like))

    total = db.scalar(count_stmt) or 0
    items = (
        db.scalars(
            stmt.order_by(Verification.created_at.desc()).offset((page - 1) * limit).limit(limit)
        ).all()
    )

    return VerificationListOut(
        data=[
            VerificationListItem(
                id=v.id,
                documentName=v.document_name,
                verdict=v.verdict.value if v.verdict else None,
                trustScore=v.trust_score,
                status=v.status.value,
                createdAt=v.created_at,
            )
            for v in items
        ],
        total=int(total),
        page=page,
        limit=limit,
    )


@router.get("/{verification_id}", response_model=VerificationDetailOut)
def get_verification(
    verification_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VerificationDetailOut:
    v: Verification | None = db.get(Verification, verification_id)
    if not v:
        raise HTTPException(status_code=404, detail="Verification not found")
    if v.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    ai = v.ai_output or {}
    flags = ai.get("flags")
    passed_checks = ai.get("passed_checks")

    return VerificationDetailOut(
        id=v.id,
        documentName=v.document_name,
        squadTransactionRef=v.squad_transaction_ref,
        paymentStatus=v.payment_status.value,
        status=v.status.value,
        verdict=v.verdict.value if v.verdict else None,
        trustScore=v.trust_score,
        flags=flags if isinstance(flags, list) else None,
        passedChecks=passed_checks if isinstance(passed_checks, list) else None,
        summary=v.summary,
        issuerContactHints=issuer_contact_hints_from_ai(ai, document_filename=v.document_name),
        createdAt=v.created_at,
        completedAt=v.completed_at,
    )

