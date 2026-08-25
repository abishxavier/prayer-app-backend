"""
Email OTP service using Gmail SMTP with IPv4 enforcement.

Configuration (in .env or Render environment):
  SMTP_EMAIL=your_gmail@gmail.com
  SMTP_PASSWORD=your_gmail_app_password   # 16-character App Password (no spaces)

Gmail App Password setup:
  1. Enable 2-Step Verification on your Google account.
  2. Go to myaccount.google.com -> Security -> App passwords.
  3. Create an app password for "Mail" and paste it in SMTP_PASSWORD.
"""

import os
import smtplib
import ssl
import socket
import random
import string
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── In-memory OTP store ──────────────────────────────────────────────────────
_otp_store: dict[str, dict] = {}
OTP_TTL_SECONDS = 600  # 10 minutes


# ── IPv4-Forced SMTP Clients (Bypasses IPv6 unreachable error on Render) ────

class IPv4SMTP(smtplib.SMTP):
    """SMTP client that forces IPv4 resolution to prevent [Errno 101] Network unreachable."""
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
    """SMTP_SSL client that forces IPv4 resolution to prevent [Errno 101] Network unreachable."""
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
    smtp_email = (os.getenv("SMTP_EMAIL", "") or "").strip()
    smtp_password = (os.getenv("SMTP_PASSWORD", "") or "").replace(" ", "").strip()
    return smtp_email, smtp_password


def send_otp_email(to_email: str, otp_code: str, purpose: str = "verification") -> None:
    """
    Send a 6-digit OTP to `to_email` via Gmail SMTP using IPv4.
    Tries Port 587 (STARTTLS) first, then falls back to Port 465 (SSL).
    """
    smtp_email, smtp_password = _get_smtp_credentials()

    if not smtp_email or not smtp_password:
        raise RuntimeError(
            "Email service is not configured. "
            "Please set SMTP_EMAIL and SMTP_PASSWORD in the Render environment variables."
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
    <body style="font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 24px;">
      <div style="max-width: 500px; margin: auto; background: #1e293b; border-radius: 16px; padding: 32px; border: 1px solid #334155;">
        <div style="text-align: center; margin-bottom: 24px;">
          <h2 style="color: #60a5fa; margin: 0; font-size: 22px;">✝️ JIPF Prayer App</h2>
          <p style="color: #94a3b8; margin-top: 6px; font-size: 14px;">{greeting}</p>
        </div>
        <p style="color: #cbd5e1; font-size: 15px; line-height: 1.6;">
          You are {action_text} <strong>JIPF Prayer App</strong>. 
          Use the verification code below to complete your registration:
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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"JIPF Prayer App <{smtp_email}>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    errors = []

    # Attempt 1: Port 587 with STARTTLS (Preferred on cloud platforms)
    try:
        server = IPv4SMTP("smtp.gmail.com", 587, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_email, smtp_password)
        server.sendmail(smtp_email, to_email, msg.as_string())
        server.quit()
        return
    except Exception as e:
        errors.append(f"Port 587: {e}")

    # Attempt 2: Port 465 with SSL
    try:
        server_ssl = IPv4SMTP_SSL("smtp.gmail.com", 465, timeout=15)
        server_ssl.ehlo()
        server_ssl.login(smtp_email, smtp_password)
        server_ssl.sendmail(smtp_email, to_email, msg.as_string())
        server_ssl.quit()
        return
    except Exception as e:
        errors.append(f"Port 465: {e}")

    # If both failed
    err_str = " | ".join(errors)
    if "AuthenticationError" in err_str or "Username and Password not accepted" in err_str:
        raise RuntimeError(
            "Gmail authentication failed. Please check SMTP_EMAIL and SMTP_PASSWORD in Render. "
            "Make sure you are using a 16-character Gmail App Password."
        )
    raise RuntimeError(f"Failed to send OTP email: {err_str}")
