"""
Email OTP service using Gmail SMTP.

Configuration (add to .env):
  SMTP_EMAIL=your_gmail@gmail.com
  SMTP_PASSWORD=your_gmail_app_password   # NOT your regular password – use an App Password

Gmail App Password setup:
  1. Enable 2-Step Verification on your Google account.
  2. Go to myaccount.google.com → Security → App passwords.
  3. Create an app password for "Mail" and paste it in SMTP_PASSWORD.
"""

import os
import smtplib
import random
import string
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── In-memory OTP store ──────────────────────────────────────────────────────
# Structure: { key: {"code": "123456", "expires": <unix ts>} }
# key = email address (for email-OTP) or phone (for phone-OTP)
_otp_store: dict[str, dict] = {}
OTP_TTL_SECONDS = 600  # 10 minutes


# ── OTP generation & storage ─────────────────────────────────────────────────

def generate_otp(key: str) -> str:
    """Generate a 6-digit OTP and store it keyed by `key` (email or phone)."""
    code = "".join(random.choices(string.digits, k=6))
    _otp_store[key.lower().strip()] = {
        "code": code,
        "expires": time.time() + OTP_TTL_SECONDS,
    }
    return code


def verify_otp(key: str, code: str) -> bool:
    """Return True if OTP is valid and not expired, and remove it from store."""
    k = key.lower().strip()
    entry = _otp_store.get(k)
    if not entry:
        return False
    if time.time() > entry["expires"]:
        _otp_store.pop(k, None)
        return False
    if entry["code"] != code.strip():
        return False
    _otp_store.pop(k, None)
    return True


def invalidate_otp(key: str) -> None:
    """Remove any pending OTP for this key."""
    _otp_store.pop(key.lower().strip(), None)


# ── Gmail SMTP sender ────────────────────────────────────────────────────────

def _get_smtp_credentials():
    smtp_email = os.getenv("SMTP_EMAIL", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    return smtp_email, smtp_password


def send_otp_email(to_email: str, otp_code: str, purpose: str = "verification") -> None:
    """
    Send a 6-digit OTP to `to_email` via Gmail SMTP.

    Raises RuntimeError if SMTP credentials are not configured or sending fails.
    """
    smtp_email, smtp_password = _get_smtp_credentials()

    if not smtp_email or not smtp_password:
        raise RuntimeError(
            "Email service is not configured. "
            "Please set SMTP_EMAIL and SMTP_PASSWORD in the server environment."
        )

    subject = "Your JIPF Prayer App Verification Code"

    if purpose == "login":
        action_text = "signing in to"
        greeting = "Welcome back!"
    else:
        action_text = "registering with"
        greeting = "Welcome to JIPF Prayer App!"

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
      <div style="max-width: 500px; margin: auto; background: white; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <div style="text-align: center; margin-bottom: 24px;">
          <h2 style="color: #1a237e; margin: 0;">✝️ JIPF Prayer App</h2>
          <p style="color: #666; margin-top: 8px;">{greeting}</p>
        </div>
        <p style="color: #333; font-size: 15px;">
          You are {action_text} <strong>JIPF Prayer App</strong>. 
          Use the verification code below to complete the process:
        </p>
        <div style="text-align: center; margin: 28px 0;">
          <div style="display: inline-block; background: #f0f4ff; border: 2px solid #3949ab; border-radius: 12px; padding: 16px 40px;">
            <span style="font-size: 36px; font-weight: bold; letter-spacing: 10px; color: #1a237e;">{otp_code}</span>
          </div>
        </div>
        <p style="color: #666; font-size: 13px; text-align: center;">
          This code expires in <strong>10 minutes</strong>.
        </p>
        <p style="color: #666; font-size: 13px; text-align: center;">
          If you did not request this code, please ignore this email.
        </p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
        <p style="color: #bbb; font-size: 11px; text-align: center;">
          JIPF Prayer Community · Sent automatically, do not reply.
        </p>
      </div>
    </body>
    </html>
    """

    text_body = (
        f"Your JIPF Prayer App verification code is: {otp_code}\n\n"
        f"This code expires in 10 minutes.\n\n"
        f"If you did not request this, please ignore this email."
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"JIPF Prayer App <{smtp_email}>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Gmail authentication failed. "
            "Please check SMTP_EMAIL and SMTP_PASSWORD (use a Gmail App Password, not your regular password)."
        )
    except Exception as e:
        raise RuntimeError(f"Failed to send OTP email: {e}")
