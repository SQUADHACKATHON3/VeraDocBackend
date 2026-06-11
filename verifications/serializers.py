from datetime import datetime
from typing import Any, Literal

from rest_framework import serializers

from services.issuer_contact_hints import (
    build_suggested_outreach_message,
    outreach_message_note_for_source,
)


class InitiateOutSerializer(serializers.Serializer):
    verificationId = serializers.UUIDField()
    creditsRemaining = serializers.IntegerField()


class StatusOutSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["pending", "processing", "complete", "error"])
    verdict = serializers.CharField(allow_null=True, required=False)
    trustScore = serializers.IntegerField(allow_null=True, required=False)
    summary = serializers.CharField(allow_null=True, required=False)
    error = serializers.CharField(allow_null=True, required=False)
    errorDetail = serializers.CharField(allow_null=True, required=False)


class VerificationListItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    documentName = serializers.CharField()
    verdict = serializers.CharField(allow_null=True)
    trustScore = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()
    createdAt = serializers.DateTimeField()


class VerificationListSerializer(serializers.Serializer):
    data = VerificationListItemSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    limit = serializers.IntegerField()


class IssuerContactItemSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["email", "phone"])
    value = serializers.CharField()
    sourceUrl = serializers.CharField(allow_null=True, required=False)
    sourceTitle = serializers.CharField(allow_null=True, required=False)


class IssuerContactHintsSerializer(serializers.Serializer):
    included = serializers.BooleanField()
    trigger = serializers.CharField()
    unverified = serializers.BooleanField(default=True)
    disclaimer = serializers.CharField()
    items = IssuerContactItemSerializer(many=True)
    suggestedOutreachMessage = serializers.CharField()
    suggestedOutreachMessageNote = serializers.CharField()
    outreachMessageSource = serializers.ChoiceField(
        choices=["ai_merge", "template_fallback"], allow_null=True, required=False
    )
    note = serializers.CharField(allow_null=True, required=False)


class VerificationDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    documentName = serializers.CharField()
    squadTransactionRef = serializers.CharField(allow_null=True)
    paymentStatus = serializers.CharField()
    status = serializers.CharField()
    verdict = serializers.CharField(allow_null=True)
    trustScore = serializers.IntegerField(allow_null=True)
    flags = serializers.ListField(child=serializers.CharField(), allow_null=True, required=False)
    passedChecks = serializers.ListField(child=serializers.CharField(), allow_null=True, required=False)
    summary = serializers.CharField(allow_null=True)
    issuerContactHints = IssuerContactHintsSerializer(allow_null=True, required=False)
    createdAt = serializers.DateTimeField()
    completedAt = serializers.DateTimeField(allow_null=True)


def issuer_contact_hints_from_ai(
    ai: dict[str, Any],
    *,
    document_filename: str | None = None,
) -> dict[str, Any] | None:
    raw = ai.get("issuer_contact_hints")
    if not isinstance(raw, dict) or not raw.get("included"):
        return None
    items_out: list[dict[str, Any]] = []
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
            {
                "type": t,
                "value": str(val),
                "sourceUrl": it.get("source_url") if isinstance(it.get("source_url"), str) else None,
                "sourceTitle": it.get("source_title") if isinstance(it.get("source_title"), str) else None,
            }
        )
    msg_raw = raw.get("suggested_outreach_message")
    msg = msg_raw if isinstance(msg_raw, str) and msg_raw.strip() else ""
    message_synthesized = False
    if not msg:
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
    if isinstance(msg_note_raw, str) and msg_note_raw.strip():
        msg_note = msg_note_raw.strip()
    else:
        msg_note = outreach_message_note_for_source(source)
    return {
        "included": True,
        "trigger": str(raw.get("trigger") or ""),
        "unverified": bool(raw.get("unverified", True)),
        "disclaimer": str(raw.get("disclaimer") or ""),
        "items": items_out,
        "suggestedOutreachMessage": msg,
        "suggestedOutreachMessageNote": msg_note,
        "outreachMessageSource": source,
        "note": raw.get("note") if isinstance(raw.get("note"), str) else None,
    }
