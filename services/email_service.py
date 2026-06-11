"""Send transactional emails (OTP, password reset) via Resend.

Set RESEND_API_KEY and RESEND_FROM in .env. Optional EMAIL_DRIVER=smtp for local fallback.

Resend sandbox: `onboarding@resend.dev` only delivers to the email on your Resend account.
Verify a domain at resend.com/domains for production recipients.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import resend

from django.conf import settings

logger = logging.getLogger(__name__)


def _html_otp_email(code: str, subject: str, heading: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="font-family:Arial,sans-serif;background:#f6f6f6;margin:0;padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 0;">
      <table width="520" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:8px;padding:40px;box-shadow:0 2px 8px rgba(0,0,0,.06);">
        <tr><td>
          <h1 style="color:#8B0035;margin:0 0 8px;">VeraDoc</h1>
          <p style="color:#555;margin:0 0 24px;">{heading}</p>
          <div style="background:#f9f0f4;border-radius:6px;padding:24px;text-align:center;margin-bottom:24px;">
            <span style="font-size:40px;font-weight:bold;letter-spacing:10px;color:#8B0035;">{code}</span>
          </div>
          <p style="color:#888;font-size:13px;margin:0;">
            This code expires in <strong>{settings.OTP_TTL_MINUTES} minutes</strong>.
            If you did not request this, you can ignore this email.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _text_otp_email(code: str, subject: str) -> str:
    return (
        f"VeraDoc — {subject}\n\n"
        f"Your code: {code}\n\n"
        f"This code expires in {settings.OTP_TTL_MINUTES} minutes.\n"
        "If you did not request this, ignore this email."
    )


def should_log_otp_codes() -> bool:
    return settings.OTP_LOG_CODES or settings.ENV.lower() == "local"


def log_otp_code(*, to: str, code: str, otp_type: str) -> None:
    """Log OTP for local debugging (Render logs / terminal). Never expose in API in production."""
    if should_log_otp_codes():
        logger.warning(
            "OTP code for %s (type=%s): %s — expires in %s min",
            to,
            otp_type,
            code,
            settings.OTP_TTL_MINUTES,
        )


def send_otp_email(*, to: str, code: str, otp_type: str) -> None:
    """Send OTP email. Raises on failure."""
    if otp_type == "email_verification":
        subject = "Your VeraDoc verification code"
        heading = "Please verify your email address."
    else:
        subject = "Reset your VeraDoc password"
        heading = "Use the code below to reset your password."

    driver = (settings.EMAIL_DRIVER or "resend").lower()
    if driver == "smtp":
        _send_via_smtp(to=to, subject=subject, code=code, heading=heading)
    else:
        _send_via_resend(to=to, subject=subject, code=code, heading=heading)


def send_otp_email_task(*, to: str, code: str, otp_type: str) -> None:
    """Background-task entrypoint: send email and log failures (and OTP in local/dev)."""
    log_otp_code(to=to, code=code, otp_type=otp_type)
    try:
        send_otp_email(to=to, code=code, otp_type=otp_type)
        logger.info("OTP email sent to %s (type=%s)", to, otp_type)
    except Exception:
        logger.exception(
            "Failed to send OTP email to %s (type=%s). "
            "If using Resend onboarding@resend.dev, only your Resend account email can receive mail "
            "until you verify a domain.",
            to,
            otp_type,
        )


def _send_via_resend(*, to: str, subject: str, code: str, heading: str) -> None:
    if not settings.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is required when EMAIL_DRIVER=resend")

    resend.api_key = settings.RESEND_API_KEY
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM,
        "to": [to],
        "subject": subject,
        "html": _html_otp_email(code, subject, heading),
        "text": _text_otp_email(code, subject),
    }
    resend.Emails.send(params)


def _send_via_smtp(*, to: str, subject: str, code: str, heading: str) -> None:
    if not settings.SMTP_HOST:
        raise RuntimeError("SMTP_HOST is required when EMAIL_DRIVER=smtp")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg.attach(MIMEText(_text_otp_email(code, subject), "plain"))
    msg.attach(MIMEText(_html_otp_email(code, subject, heading), "html"))

    if settings.SMTP_TLS:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
            s.ehlo()
            s.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as s:
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)
