"""
Deterministic checks on model output (hybrid layer).

Conservative: can downgrade AUTHENTIC when score contradicts policy bands,
add review flags, and never invent new forensic claims — only consistency /
calibration signals aligned with the system prompt score bands.
"""

from __future__ import annotations

from typing import Any


def apply_verdict_score_band_consistency(output: dict[str, Any]) -> dict[str, Any]:
    """
    Enforce alignment with declared bands:
    AUTHENTIC 75–100, NEEDS REVIEW 40–74, FAKE 0–39.

    Reduces false "AUTHENTIC" when trust_score is below the AUTHENTIC band.
    Surfaces contradictions for human review without silently upgrading FAKE → AUTHENTIC.
    """
    verdict = output.get("verdict")
    ts = output.get("trust_score")
    if verdict not in ("AUTHENTIC", "NEEDS REVIEW", "FAKE") or not isinstance(ts, int):
        return output

    flags = list(output.get("flags") or [])
    summary = output.get("summary")
    summary_s = summary if isinstance(summary, str) else ""
    out = dict(output)

    if verdict == "AUTHENTIC" and ts < 75:
        flags.append(
            "Hybrid consistency: score below AUTHENTIC band (75+); verdict adjusted to NEEDS REVIEW — please confirm with the issuing institution."
        )
        out["verdict"] = "NEEDS REVIEW"
        out["flags"] = flags
        if summary_s:
            out["summary"] = summary_s + " (Adjusted by consistency check — human review recommended.)"
        return out

    if verdict == "FAKE" and ts > 39:
        flags.append(
            "Hybrid consistency: FAKE verdict with trust_score above FAKE band — treat as high-risk; confirm manually."
        )
        out["flags"] = flags
        return out

    if verdict == "NEEDS REVIEW" and ts >= 75:
        flags.append(
            "Hybrid consistency: trust_score in AUTHENTIC range but verdict is Needs Review — institutional confirmation recommended."
        )
        out["flags"] = flags
        return out

    if verdict == "NEEDS REVIEW" and ts <= 39:
        flags.append(
            "Hybrid consistency: trust_score in FAKE range but verdict is Needs Review — escalate review if policy requires."
        )
        out["flags"] = flags
        return out

    return out
