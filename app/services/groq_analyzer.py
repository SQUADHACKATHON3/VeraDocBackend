import base64
import io
import json
from typing import Any

from groq import Groq
from pdf2image import convert_from_bytes
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings
from app.services.forensic_hybrid import apply_verdict_score_band_consistency
from app.services.issuer_contact_hints import build_issuer_contact_hints


_FORENSIC_PROMPT_BASE = """
You are VeraDoc, a forensic document verification AI specialized in detecting
fake or tampered academic certificates and transcripts.

Your ONLY job is to analyze the provided document image for signs of forgery,
tampering, or inauthenticity.

You MUST always return a JSON object in this exact format with no extra text,
no markdown, no preamble:

{
  "verdict": "AUTHENTIC" or "SUSPICIOUS" or "FAKE",
  "trust_score": integer between 0 and 100,
  "flags": ["list of specific forensic issues found"],
  "passed_checks": ["list of checks that passed"],
  "summary": "one sentence explanation of your verdict"
}

Analyze the following signals (multimodal: layout, typography, imagery, and text coherence):
- Font consistency across the entire document
- Seal and watermark presence, placement, and quality
- Formatting alignment and spacing regularity
- Text layer anomalies suggesting digital alteration
- Date format validity and logical consistency
- Institution name spelling and official formatting patterns
- Signature presence and placement
- Overall document structural integrity
- Consistency anomalies: contradictory dates, mismatched letterhead vs body fonts, implausible serial patterns

Treat inconsistent seals, misaligned typography layers, impossible chronology, and template drift as
consistency anomalies (similar in spirit to anomaly detection on document layout and metadata signals).

Verdict guidelines:
- AUTHENTIC (trust_score 75-100): All or most checks pass, no significant anomalies
- SUSPICIOUS (trust_score 40-74): Some anomalies present but not conclusive
- FAKE (trust_score 0-39): Multiple clear forensic indicators of forgery

Do NOT return anything outside the JSON structure.
Do NOT add markdown code fences.
Do NOT explain your reasoning outside the summary field.
""".strip()


_REGION_BLOCK_NG = """
Primary operational context: Nigeria — federal/state universities, polytechnics, colleges of education,
WAEC/NECO-style awards, NYSC discharge or exemption documents where applicable, and common Nigerian
registry / attestation wording. Prefer flags that cite specific Nigerian layout or naming cues when visible.

If the document clearly appears issued for another country with no Nigerian contextual cues, add a flag
such as "Regional context: issuer may be non-Nigeria" and lean SUSPICIOUS over AUTHENTIC unless forensic
evidence is very strong (this product is Nigeria-first; cross-border documents need clearer proof).
""".strip()


_REGION_BLOCK_GENERAL = """
Primary operational context: general international academic credentials (any country). Apply the same
forensic and consistency-anomaly signals. When issuer region or jurisdiction is unclear, prefer SUSPICIOUS
over AUTHENTIC without strong cross-field consistency.
""".strip()


def _forensic_system_prompt() -> str:
    code = (settings.verification_primary_region or "NG").strip().upper()
    region = _REGION_BLOCK_NG if code == "NG" else _REGION_BLOCK_GENERAL
    return f"{_FORENSIC_PROMPT_BASE}\n\n{region}"


def _entity_extraction_prompt() -> str:
    ng = (settings.verification_primary_region or "NG").strip().upper() == "NG"
    bias = (
        "When visible cues suggest Nigeria (e.g. Nigerian institution names, Naira-era dates, WAEC/NYSC wording), "
        "set country_or_region to Nigeria unless the document explicitly states otherwise."
        if ng
        else "Infer country_or_region from visible issuer address or language when reasonably clear; else null."
    )
    return f"""
You extract factual labels visible on an academic certificate or transcript image.
Return ONLY valid JSON with no markdown:

{{
  "institution_name": string or null,
  "document_title_or_type": string or null,
  "candidate_name": string or null,
  "dates_visible": string or null,
  "serial_or_registration": string or null,
  "country_or_region": string or null,
  "other_notable_text": string or null
}}

{bias}
Use null if unknown or illegible. Keep strings short (under 200 chars each).
""".strip()


def _merge_system_prompt() -> str:
    ng = (settings.verification_primary_region or "NG").strip().upper() == "NG"
    web_bias = (
        "For Nigerian issuers, weigh snippets from .edu.ng domains, federal ministry pages, and known Nigerian "
        "regulatory sources more heavily than random blogs; still never treat web text alone as proof of authenticity."
        if ng
        else "Prefer official registrar or .ac / .edu primary sources over forums; web text is never sole proof."
    )
    return f"""
You are VeraDoc. You combine (1) visual forensic analysis of a document with (2) optional web search snippets.
Web results may be incomplete, outdated, unrelated, or adversarial — treat them as hints with guardrails, not proof.

{web_bias}

Rules:
- If web sources strongly contradict claims on the document (e.g. institution does not exist, known diploma mill), increase suspicion or mark FAKE with clear flags citing "web corroboration".
- If web sources support that the institution/program exists and matches the document type, you may slightly increase confidence but do not upgrade to AUTHENTIC solely from web text without strong forensic support.
- Preserve forensic reasoning; adjust trust_score by at most ~15 points unless web evidence is decisive.
- Add brief flags like "Web: ..." when web search influenced the outcome.

Also produce suggested_outreach_message in the SAME JSON response (one model call — no follow-up):
- Plain text only, no markdown fences. Start with a line "Subject: ..." then a blank line, then the email body the end user can copy to send to the issuing institution.
- Ground the letter in extracted_entities (institution, document type, candidate name, serial/registration/certificate ID, dates, region) and the forensic + web context. Never invent a serial or ID not present in extracted_entities; if missing, say it was not legible on the scan.
- Tone: professional, neutral English (Nigerian context is fine when region is Nigeria). Ask the office to confirm authenticity and register match.
- End with placeholder lines exactly: [Your full name] then [Your email or phone] on separate lines.
- Length: roughly 120–450 words.

Output ONLY this JSON shape (no markdown):

{{
  "verdict": "AUTHENTIC" or "SUSPICIOUS" or "FAKE",
  "trust_score": 0-100,
  "flags": [],
  "passed_checks": [],
  "summary": "one sentence",
  "suggested_outreach_message": "Subject: ...\\n\\nDear ...\\n\\n...\\n\\n[Your full name]\\n[Your email or phone]"
}}
""".strip()


class GroqVerdict(BaseModel):
    verdict: str = Field(pattern=r"^(AUTHENTIC|SUSPICIOUS|FAKE)$")
    trust_score: int = Field(ge=0, le=100)
    flags: list[str]
    passed_checks: list[str]
    summary: str


class GroqMergeOutput(GroqVerdict):
    """Merge-step response: verdict fields plus AI outreach draft (same completion as merge)."""

    model_config = ConfigDict(extra="ignore")

    suggested_outreach_message: str = Field(min_length=40, max_length=12000)


class ExtractedEntities(BaseModel):
    model_config = ConfigDict(extra="ignore")

    institution_name: str | None = None
    document_title_or_type: str | None = None
    candidate_name: str | None = None
    dates_visible: str | None = None
    serial_or_registration: str | None = None
    country_or_region: str | None = None
    other_notable_text: str | None = None


def _maybe_apply_hybrid(data: dict[str, Any]) -> dict[str, Any]:
    if settings.hybrid_verdict_score_consistency:
        return apply_verdict_score_band_consistency(data)
    return data


def _bytes_to_base64_jpeg(image_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _pdf_first_page_to_base64_jpeg(pdf_bytes: bytes) -> str:
    pages = convert_from_bytes(pdf_bytes, first_page=1, last_page=1)
    if not pages:
        raise ValueError("PDF has no pages")
    img = pages[0].convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _image_base64_from_upload(*, filename: str, content_type: str, file_bytes: bytes) -> str:
    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return _pdf_first_page_to_base64_jpeg(file_bytes)
    return _bytes_to_base64_jpeg(file_bytes)


def _parse_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Groq did not return JSON")
        return json.loads(text[start : end + 1])


def _forensic_vision(client: Groq, *, base64_jpeg: str) -> dict[str, Any]:
    resp = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _forensic_system_prompt()},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_jpeg}"}},
                    {"type": "text", "text": "Analyze this academic document and return the JSON verdict."},
                ],
            },
        ],
        temperature=0.1,
        max_tokens=1000,
    )
    text = (resp.choices[0].message.content or "").strip()
    parsed = _parse_json_object(text)
    return _maybe_apply_hybrid(GroqVerdict.model_validate(parsed).model_dump())


def _extract_entities_vision(client: Groq, *, base64_jpeg: str) -> dict[str, Any]:
    resp = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _entity_extraction_prompt()},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_jpeg}"}},
                    {"type": "text", "text": "Extract visible fields as JSON only."},
                ],
            },
        ],
        temperature=0.1,
        max_tokens=600,
    )
    text = (resp.choices[0].message.content or "").strip()
    parsed = _parse_json_object(text)
    return ExtractedEntities.model_validate(parsed).model_dump()


def _build_search_queries(entities: dict[str, Any]) -> list[str]:
    qs: list[str] = []
    inst = (entities.get("institution_name") or "").strip()
    doc_type = (entities.get("document_title_or_type") or "").strip()
    region = (entities.get("country_or_region") or "").strip()
    serial = (entities.get("serial_or_registration") or "").strip()
    ng = (settings.verification_primary_region or "NG").strip().upper() == "NG"
    geo = "Nigeria" if ng else (region or "international")

    if inst:
        qs.append(f"{inst} official university college verification diploma certificate {geo}")
        qs.append(f"{inst} accreditation higher education {geo}")
    if doc_type and inst:
        qs.append(f"{inst} {doc_type} authentic sample {geo}")
    elif doc_type:
        qs.append(f"{doc_type} academic certificate verification {geo}")

    if serial and len(serial) > 3:
        reg_hint = "WAEC NECO university" if ng else "academic registry"
        qs.append(f"{serial} certificate verification {reg_hint} {geo}")

    if region and region.lower() not in ("nigeria", "ng"):
        qs.append(f"{inst or doc_type} {region} education certificate")

    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for q in qs:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out[:4]


def _merge_forensic_and_web(
    client: Groq,
    *,
    forensic: dict[str, Any],
    entities: dict[str, Any],
    web_blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    web_blob = json.dumps(web_blocks, ensure_ascii=False, indent=2)[:12000]
    user_text = f"""Forensic JSON (from image):
{json.dumps(forensic, ensure_ascii=False)}

Extracted entities (from image):
{json.dumps(entities, ensure_ascii=False)}

Web search snippets (may be incomplete):
{web_blob}

Produce the final merged JSON verdict."""
    resp = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _merge_system_prompt()},
            {"role": "user", "content": user_text},
        ],
        temperature=0.15,
        max_tokens=1600,
    )
    text = (resp.choices[0].message.content or "").strip()
    parsed = _parse_json_object(text)
    try:
        return _maybe_apply_hybrid(GroqMergeOutput.model_validate(parsed).model_dump())
    except ValidationError:
        base = _maybe_apply_hybrid(GroqVerdict.model_validate(parsed).model_dump())
        return {**base, "suggested_outreach_message": ""}


def analyze_document(*, filename: str, content_type: str, file_bytes: bytes) -> dict[str, Any]:
    """
    Full pipeline: forensic vision (multimodal) → optional Tavily from extracted entities → merged verdict.

    Region is controlled by ``verification_primary_region`` (default ``NG``). Optional Tavily step applies
    web corroboration with merge guardrails. A small deterministic hybrid layer can align verdict vs score bands.

    If ``TAVILY_API_KEY`` is unset or search fails, returns forensic-only result (same core shape as before).
    """
    base64_jpeg = _image_base64_from_upload(filename=filename, content_type=content_type, file_bytes=file_bytes)
    client = Groq(api_key=settings.groq_api_key)

    forensic = _forensic_vision(client, base64_jpeg=base64_jpeg)

    tavily_key = (settings.tavily_api_key or "").strip()
    if not tavily_key:
        return forensic

    blocks: list[dict[str, Any]] | None = None
    ai_outreach_for_hints: str | None = None
    try:
        from app.services.tavily_search import run_queries

        entities = _extract_entities_vision(client, base64_jpeg=base64_jpeg)
        queries = _build_search_queries(entities)
        if not queries:
            merged = forensic
            web_meta: dict[str, Any] = {"enabled": True, "skipped_reason": "no_queries_from_entities"}
            blocks = None
        else:
            used_queries, blocks = run_queries(queries)
            merged_full = _merge_forensic_and_web(client, forensic=forensic, entities=entities, web_blocks=blocks)
            raw_msg = merged_full.pop("suggested_outreach_message", None)
            merged = merged_full
            ai_outreach_for_hints = raw_msg.strip() if isinstance(raw_msg, str) and raw_msg.strip() else None
            web_meta = {
                "enabled": True,
                "queries": used_queries,
                "result_blocks": blocks,
            }
    except Exception as e:
        # Tavily or merge failed: keep forensic, record error
        return {
            **forensic,
            "web_search": {"enabled": True, "error": str(e)},
            "forensic_only": forensic,
        }

    out: dict[str, Any] = {
        **merged,
        "extracted_entities": entities,
        "forensic_only": forensic,
        "web_search": web_meta,
    }
    ts_raw = out.get("trust_score")
    try:
        ts_int = int(ts_raw) if ts_raw is not None else None
    except (TypeError, ValueError):
        ts_int = None
    vd_raw = out.get("verdict")
    verdict_str = vd_raw if isinstance(vd_raw, str) else None
    hints = build_issuer_contact_hints(
        verdict=verdict_str,
        trust_score=ts_int,
        web_blocks=blocks,
        extracted_entities=entities,
        document_filename=filename,
        screening_summary=out.get("summary") if isinstance(out.get("summary"), str) else None,
        ai_outreach_message=ai_outreach_for_hints,
    )
    if hints is not None:
        out["issuer_contact_hints"] = hints
    return out
