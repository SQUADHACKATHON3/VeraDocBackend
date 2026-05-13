import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class InitiateOut(BaseModel):
    verificationId: uuid.UUID
    creditsRemaining: int


class StatusOut(BaseModel):
    status: Literal["pending", "processing", "complete", "error"]
    verdict: str | None = None
    trustScore: int | None = None
    summary: str | None = None


class VerificationListItem(BaseModel):
    id: uuid.UUID
    documentName: str
    verdict: str | None
    trustScore: int | None
    status: str
    createdAt: datetime


class VerificationListOut(BaseModel):
    data: list[VerificationListItem]
    total: int
    page: int
    limit: int


class IssuerContactItemOut(BaseModel):
    type: Literal["email", "phone"]
    value: str
    sourceUrl: str | None = None
    sourceTitle: str | None = None


class IssuerContactHintsOut(BaseModel):
    """Web-derived issuer contacts; only populated for SUSPICIOUS + mid trust band when Tavily ran."""

    included: bool
    trigger: str
    unverified: bool = True
    disclaimer: str
    items: list[IssuerContactItemOut]
    suggestedOutreachMessage: str
    suggestedOutreachMessageNote: str = (
        "Auto-filled from the document scan; may contain errors. Replace bracketed placeholders before sending."
    )
    outreachMessageSource: Literal["ai_merge", "template_fallback"] | None = None
    note: str | None = None


class VerificationDetailOut(BaseModel):
    id: uuid.UUID
    documentName: str
    squadTransactionRef: str | None
    paymentStatus: str
    status: str
    verdict: str | None
    trustScore: int | None
    flags: list[str] | None = None
    passedChecks: list[str] | None = None
    summary: str | None
    issuerContactHints: IssuerContactHintsOut | None = None
    createdAt: datetime
    completedAt: datetime | None


def issuer_contact_hints_from_ai(
    ai: dict[str, Any],
    *,
    document_filename: str | None = None,
) -> IssuerContactHintsOut | None:
    raw = ai.get("issuer_contact_hints")
    if not isinstance(raw, dict) or not raw.get("included"):
        return None
    items_out: list[IssuerContactItemOut] = []
    for it in raw.get("items") or []:
        if not isinstance(it, dict):
            continue
        t = it.get("type")
        if t not in ("email", "phone"):
            continue
        val = it.get("value")
        if not val:
            continue
        items_out.append(
            IssuerContactItemOut(
                type=t,
                value=str(val),
                sourceUrl=it.get("source_url") if isinstance(it.get("source_url"), str) else None,
                sourceTitle=it.get("source_title") if isinstance(it.get("source_title"), str) else None,
            )
        )
    msg_raw = raw.get("suggested_outreach_message")
    msg = msg_raw if isinstance(msg_raw, str) and msg_raw.strip() else ""
    message_synthesized = False
    if not msg:
        from app.services.issuer_contact_hints import build_suggested_outreach_message

        ent = ai.get("extracted_entities") if isinstance(ai.get("extracted_entities"), dict) else None
        summ = ai.get("summary") if isinstance(ai.get("summary"), str) else None
        msg = build_suggested_outreach_message(
            ent,
            document_filename=document_filename,
            screening_summary=summ,
        )
        message_synthesized = True
    src_raw = raw.get("outreach_message_source")
    source: Literal["ai_merge", "template_fallback"] | None = (
        src_raw if src_raw in ("ai_merge", "template_fallback") else None
    )
    if source is None and message_synthesized:
        source = "template_fallback"

    msg_note_raw = raw.get("suggested_outreach_message_note")
    from app.services.issuer_contact_hints import outreach_message_note_for_source

    if isinstance(msg_note_raw, str) and msg_note_raw.strip():
        msg_note = msg_note_raw.strip()
    else:
        msg_note = outreach_message_note_for_source(source)
    return IssuerContactHintsOut(
        included=True,
        trigger=str(raw.get("trigger") or ""),
        unverified=bool(raw.get("unverified", True)),
        disclaimer=str(raw.get("disclaimer") or ""),
        items=items_out,
        suggestedOutreachMessage=msg,
        suggestedOutreachMessageNote=msg_note,
        outreachMessageSource=source,
        note=raw.get("note") if isinstance(raw.get("note"), str) else None,
    )

