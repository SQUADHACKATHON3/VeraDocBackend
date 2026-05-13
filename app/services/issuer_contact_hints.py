"""Derive optional issuer contact hints from Tavily snippets when verdict + trust band match."""

from __future__ import annotations

import re
from typing import Any, Literal

# Only surface web-parsed contacts when the model is uncertain enough to warrant issuer follow-up.
ISSUER_HINTS_VERDICT = "SUSPICIOUS"
ISSUER_HINTS_MIN_TRUST = 45
ISSUER_HINTS_MAX_TRUST = 70

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
# Nigeria: +234 with up to 10 following digits (separators allowed), or local 0[789][01]…
PHONE_INTL = re.compile(r"\+?\s*234(?:[\s\-]*\d){10}\b")
PHONE_LOCAL = re.compile(r"\b0[789][01](?:[\s\-]*\d){8}\b")

MAX_ITEMS = 8
_SUMMARY_MAX = 280


def _field(ent: dict[str, Any], key: str, *, fallback: str = "Not stated on our scan") -> str:
    v = ent.get(key)
    if v is None:
        return fallback
    s = str(v).strip()
    return s if s else fallback


def build_suggested_outreach_message(
    entities: dict[str, Any] | None,
    *,
    document_filename: str | None = None,
    screening_summary: str | None = None,
) -> str:
    """
    Copy-ready email-style text for the end user to send to the issuer.
    Uses vision-extracted fields (including serial/registration when present).
    """
    ent = entities if isinstance(entities, dict) else {}
    inst = _field(ent, "institution_name", fallback="the issuing institution")
    doc_type = _field(ent, "document_title_or_type", fallback="Academic certificate or transcript")
    candidate = _field(ent, "candidate_name", fallback="Not extracted from our scan")
    serial = _field(ent, "serial_or_registration", fallback="Not visible on our scan")
    dates = _field(ent, "dates_visible", fallback="Not extracted from our scan")
    region = _field(ent, "country_or_region", fallback="Not extracted from our scan")
    other = (ent.get("other_notable_text") or "").strip()
    other_line = f"\n- Other reference text (as read from the document): {other}" if other else ""

    fname = (document_filename or "").strip()
    file_line = f"\n- Uploaded file name: {fname}" if fname else ""

    summary_line = ""
    if screening_summary and str(screening_summary).strip():
        sm = str(screening_summary).strip().replace("\n", " ")
        if len(sm) > _SUMMARY_MAX:
            sm = sm[: _SUMMARY_MAX - 1] + "…"
        summary_line = (
            f"\n\nNote for your records (unofficial automated screening only, not a legal finding):\n{sm}"
        )

    return f"""Subject: Request to verify an academic / award document

Dear Records / Admissions / Examinations Office,

I am writing to ask you to verify whether the following document was genuinely issued by your institution. I used VeraDoc as a preliminary self-check; the result was inconclusive, and I am seeking confirmation directly from you.

Details as read from the document:
- Institution: {inst}
- Document type: {doc_type}
- Name as printed on the document: {candidate}
- Registration / serial / certificate or transcript ID (as printed): {serial}
- Dates visible on the document: {dates}
- Country or region (if shown): {region}{other_line}{file_line}{summary_line}

Please let me know:
1) Whether this document is authentic and was issued by your office, and
2) Whether your records match the candidate name and reference/serial above.

I can provide a copy of the document and my identification through your preferred secure channel.

Thank you for your assistance.

Kind regards,
[Your full name]
[Your email or phone]
""".strip()


def _normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 13 and digits.startswith("234"):
        return "+" + digits
    if len(digits) == 11 and digits.startswith("0") and digits[1] in "789":
        return "+234" + digits[1:]
    if len(digits) == 10 and digits[0] in "789" and digits[1] in "01":
        return "+234" + digits
    return None


def _dedupe_key(kind: Literal["email", "phone"], value: str) -> str:
    return f"{kind}:{value.lower()}"


def extract_from_web_blocks(web_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for block in web_blocks:
        snippets = block.get("snippets") or []
        if not isinstance(snippets, list):
            continue
        for sn in snippets:
            if not isinstance(sn, dict):
                continue
            title = (sn.get("title") or "").strip()
            url = (sn.get("url") or "").strip()
            text = f"{title}\n{sn.get('snippet') or ''}"
            for m in EMAIL_RE.finditer(text):
                val = m.group(0).strip()
                key = _dedupe_key("email", val)
                if key in seen or len(items) >= MAX_ITEMS:
                    continue
                seen.add(key)
                items.append({"type": "email", "value": val, "source_url": url or None, "source_title": title or None})
            for pat in (PHONE_INTL, PHONE_LOCAL):
                for m in pat.finditer(text):
                    raw = m.group(0)
                    norm = _normalize_phone(raw)
                    if not norm:
                        continue
                    key = _dedupe_key("phone", norm)
                    if key in seen or len(items) >= MAX_ITEMS:
                        continue
                    seen.add(key)
                    items.append(
                        {"type": "phone", "value": norm, "source_url": url or None, "source_title": title or None}
                    )
    return items


_NOTE_TEMPLATE = (
    "Template fallback: filled from extracted fields only. Proofread; replace bracketed placeholders before sending."
)
_NOTE_AI = (
    "Draft produced in the same AI step as the merged verdict (forensic + entities + web snippets). "
    "Review for accuracy; replace bracketed placeholders before sending."
)


def outreach_message_note_for_source(source: str | None) -> str:
    if source == "ai_merge":
        return _NOTE_AI
    if source == "template_fallback":
        return _NOTE_TEMPLATE
    return (
        "Auto-filled from the document scan; may contain errors. Replace bracketed placeholders before sending."
    )


def build_issuer_contact_hints(
    *,
    verdict: str | None,
    trust_score: int | None,
    web_blocks: list[dict[str, Any]] | None,
    extracted_entities: dict[str, Any] | None = None,
    document_filename: str | None = None,
    screening_summary: str | None = None,
    ai_outreach_message: str | None = None,
) -> dict[str, Any] | None:
    if verdict != ISSUER_HINTS_VERDICT or trust_score is None:
        return None
    if not (ISSUER_HINTS_MIN_TRUST <= trust_score <= ISSUER_HINTS_MAX_TRUST):
        return None
    if not web_blocks:
        return None

    items = extract_from_web_blocks(web_blocks)
    ai_m = (ai_outreach_message or "").strip()
    if ai_m:
        message = ai_m
        source = "ai_merge"
        msg_note = _NOTE_AI
    else:
        message = build_suggested_outreach_message(
            extracted_entities,
            document_filename=document_filename,
            screening_summary=screening_summary,
        )
        source = "template_fallback"
        msg_note = _NOTE_TEMPLATE

    out: dict[str, Any] = {
        "included": True,
        "trigger": f"{ISSUER_HINTS_VERDICT.lower()}_{ISSUER_HINTS_MIN_TRUST}_{ISSUER_HINTS_MAX_TRUST}_trust",
        "unverified": True,
        "disclaimer": (
            "These contacts were parsed from web search snippets. They are not verified by VeraDoc. "
            "Confirm any phone or email on the institution's official website before sharing sensitive information."
        ),
        "items": items,
        "suggested_outreach_message": message,
        "suggested_outreach_message_note": msg_note,
        "outreach_message_source": source,
    }
    if not items:
        out["note"] = "no_contacts_found_in_snippets"
    return out
