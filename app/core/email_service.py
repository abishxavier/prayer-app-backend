"""
Multi-provider Email OTP Service with HTTPS API + IPv4 SMTP fallback.

Supported providers (set ANY of these in Render / .env):
  Option A (Recommended for Render - 100% reliable HTTPS):
    RESEND_API_KEY=re_xxxxxxxxx        (from resend.com - 3000 free emails/mo)
  Option B (HTTPS):
    BREVO_API_KEY=xkeysib-xxxxxxxxx    (from brevo.com - 300 free emails/day)
  Option C (Standard SMTP - for VPS / non-firewalled hosts):
    SMTP_EMAIL=your_gmail@gmail.com
    SMTP_PASSWORD=your_gmail_app_password
"""

import os
import smtplib
import ssl
import socket
import random
import string
import time
import json
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── In-memory OTP store ──────────────────────────────────────────────────────
_otp_store: dict[str, dict] = {}
OTP_TTL_SECONDS = 600  # 10 minutes


# ── IPv4-Forced SMTP Clients (for hosts that allow outbound SMTP) ───────────

class IPv4SMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        last_err = None
        for res in infos:
            af, socktype, proto, _, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                if timeout is not None:
                    sock.settimeout(timeout)
                sock.connect(sa)
                return sock
            except OSError as err:
                last_err = err
                if sock is not None:
                    sock.close()
        if last_err:
            raise last_err
        raise OSError("Could not resolve host to IPv4")


class IPv4SMTP_SSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        last_err = None
        for res in infos:
            af, socktype, proto, _, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                if timeout is not None:
                    sock.settimeout(timeout)
                sock.connect(sa)
                context = self.context if self.context else ssl.create_default_context()
                new_sock = context.wrap_socket(sock, server_hostname=host)
                return new_sock
            except OSError as err:
                last_err = err
                if sock is not None:
                    sock.close()
        if last_err:
            raise last_err
        raise OSError("Could not resolve host to IPv4")


# ── OTP Generation & Verification ───────────────────────────────────────────

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


# ── Email Templates ─────────────────────────────────────────────────────────

def _get_email_content(otp_code: str, purpose: str):
    subject = "Your JIPF Prayer App Verification Code"
    if purpose == "login":
        action_text = "signing in to"
        greeting = "Welcome back!"
    else:
        action_text = "registering with"
        greeting = "Welcome to JIPF Prayer App!"

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 24px;">
      <div style="max-width: 500px; margin: auto; background: #1e293b; border-radius: 16px; padding: 32px; border: 1px solid #334155;">
        <div style="text-align: center; margin-bottom: 24px;">
          <h2 style="color: #60a5fa; margin: 0; font-size: 22px;">✝️ JIPF Prayer App</h2>
          <p style="color: #94a3b8; margin-top: 6px; font-size: 14px;">{greeting}</p>
        </div>
        <p style="color: #cbd5e1; font-size: 15px; line-height: 1.6;">
          You are {action_text} <strong>JIPF Prayer App</strong>. 
          Use the verification code below to complete your authentication:
        </p>
        <div style="text-align: center; margin: 28px 0;">
          <div style="display: inline-block; background: #0f172a; border: 2px solid #3b82f6; border-radius: 12px; padding: 16px 36px;">
            <span style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #60a5fa; font-family: monospace;">{otp_code}</span>
          </div>
        </div>
        <p style="color: #94a3b8; font-size: 13px; text-align: center;">
          ⏱️ This code expires in <strong>10 minutes</strong>.
        </p>
        <p style="color: #64748b; font-size: 12px; text-align: center;">
          If you did not request this code, please ignore this email.
        </p>
        <hr style="border: none; border-top: 1px solid #334155; margin: 24px 0;" />
        <p style="color: #64748b; font-size: 11px; text-align: center;">
          Jesus Intercessory Prayer Family · Automated System
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

    return subject, html_body, text_body


# ── Sender Implementations ──────────────────────────────────────────────────

def _send_via_resend(api_key: str, to_email: str, subject: str, html_body: str, text_body: str):
    """Send via Resend HTTPS REST API (Port 443 - never blocked)."""
    payload = {
        "from": "JIPF Prayer App <onboarding@resend.dev>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "PrayerApp/1.0",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        if res.status in (200, 201):
            return True
        raise RuntimeError(f"Resend returned status {res.status}")


def _send_via_brevo(api_key: str, to_email: str, subject: str, html_body: str, text_body: str):
    """Send via Brevo (Sendinblue) HTTPS REST API (Port 443 - never blocked)."""
    payload = {
        "sender": {"name": "JIPF Prayer App", "email": "jipfprayerapp@gmail.com"},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": api_key.strip(),
            "Content-Type": "application/json",
            "User-Agent": "PrayerApp/1.0",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        if res.status in (200, 201, 202):
            return True
        raise RuntimeError(f"Brevo returned status {res.status}")


def _send_via_smtp(smtp_email: str, smtp_password: str, to_email: str, subject: str, html_body: str, text_body: str):
    """Send via Gmail SMTP using IPv4-forced client."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"JIPF Prayer App <{smtp_email}>"
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    errors = []
    # 1. Try port 587 (STARTTLS)
    try:
        server = IPv4SMTP("smtp.gmail.com", 587, timeout=10)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_email, smtp_password)
        server.sendmail(smtp_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        errors.append(f"Port 587: {e}")

    # 2. Try port 465 (SSL)
    try:
        server_ssl = IPv4SMTP_SSL("smtp.gmail.com", 465, timeout=10)
        server_ssl.ehlo()
        server_ssl.login(smtp_email, smtp_password)
        server_ssl.sendmail(smtp_email, to_email, msg.as_string())
        server_ssl.quit()
        return True
    except Exception as e:
        errors.append(f"Port 465: {e}")

    raise RuntimeError(f"SMTP failed: {' | '.join(errors)}")


# ── Main Dispatcher ─────────────────────────────────────────────────────────

def send_otp_email(to_email: str, otp_code: str, purpose: str = "verification") -> None:
    """
    Dispatches OTP email via the best available provider.
    Priority:
      1. Resend HTTPS API (if RESEND_API_KEY is set)
      2. Brevo HTTPS API (if BREVO_API_KEY is set)
      3. Gmail SMTP IPv4 (if SMTP_EMAIL & SMTP_PASSWORD are set)
    """
    subject, html_body, text_body = _get_email_content(otp_code, purpose)

    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    brevo_key = os.getenv("BREVO_API_KEY", "").strip()
    smtp_email = os.getenv("SMTP_EMAIL", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "").strip()

    errors = []

    # 1. Resend (HTTPS)
    if resend_key:
        try:
            _send_via_resend(resend_key, to_email, subject, html_body, text_body)
            print(f"[Email] Sent OTP to {to_email} via Resend")
            return
        except Exception as e:
            errors.append(f"Resend error: {e}")

    # 2. Brevo (HTTPS)
    if brevo_key:
        try:
            _send_via_brevo(brevo_key, to_email, subject, html_body, text_body)
            print(f"[Email] Sent OTP to {to_email} via Brevo")
            return
        except Exception as e:
            errors.append(f"Brevo error: {e}")

    # 3. SMTP (IPv4)
    if smtp_email and smtp_password:
        try:
            _send_via_smtp(smtp_email, smtp_password, to_email, subject, html_body, text_body)
            print(f"[Email] Sent OTP to {to_email} via Gmail SMTP")
            return
        except Exception as e:
            errors.append(f"SMTP error: {e}")

    # If no provider worked or configured
    if not resend_key and not brevo_key and not (smtp_email and smtp_password):
        raise RuntimeError(
            "No email service configured. Please set RESEND_API_KEY (recommended for Render) "
            "or SMTP_EMAIL/SMTP_PASSWORD in Render environment variables."
        )

    # Cloud hosting firewall explanation
    if any("timed out" in err or "unreachable" in err for err in errors):
        raise RuntimeError(
            "Render blocks outbound SMTP ports (587/465). "
            "Please add RESEND_API_KEY (free from resend.com) to your Render environment variables for instant HTTPS email delivery."
        )

    raise RuntimeError(f"Failed to send OTP email: {' | '.join(errors)}")
