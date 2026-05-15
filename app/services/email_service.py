"""Send transactional emails (OTP, password reset).

Drivers: 'smtp' (default) or 'resend'.
Set EMAIL_DRIVER + the relevant credentials in .env.
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.core.config import settings


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
            This code expires in <strong>{settings.otp_ttl_minutes} minutes</strong>.
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
        f"This code expires in {settings.otp_ttl_minutes} minutes.\n"
        "If you did not request this, ignore this email."
    )


def send_otp_email(*, to: str, code: str, otp_type: str) -> None:
    """Fire-and-forget OTP email. Call inside a BackgroundTask."""
    if otp_type == "email_verification":
        subject = "Your VeraDoc verification code"
        heading = "Please verify your email address."
    else:
        subject = "Reset your VeraDoc password"
        heading = "Use the code below to reset your password."

    driver = (settings.email_driver or "smtp").lower()
    if driver == "resend":
        _send_via_resend(to=to, subject=subject, code=code, heading=heading)
    else:
        _send_via_smtp(to=to, subject=subject, code=code, heading=heading)


def _send_via_smtp(*, to: str, subject: str, code: str, heading: str) -> None:
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is required when EMAIL_DRIVER=smtp")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.attach(MIMEText(_text_otp_email(code, subject), "plain"))
    msg.attach(MIMEText(_html_otp_email(code, subject, heading), "html"))

    if settings.smtp_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
            s.ehlo()
            s.starttls()
            if settings.smtp_user and settings.smtp_password:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as s:
            if settings.smtp_user and settings.smtp_password:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)


def _send_via_resend(*, to: str, subject: str, code: str, heading: str) -> None:
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is required when EMAIL_DRIVER=resend")

    payload = {
        "from": settings.resend_from,
        "to": [to],
        "subject": subject,
        "html": _html_otp_email(code, subject, heading),
        "text": _text_otp_email(code, subject),
    }
    resp = httpx.post(
        "https://api.resend.com/emails",
        json=payload,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    resp.raise_for_status()
