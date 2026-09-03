"""
email_service.py — OTP email delivery for AI Database Automator.

Sends a professional OTP email with proper From display name so recipients
see 'AI Database Automator' (or configured MAIL_FROM_NAME) as the sender.

Never exposes SMTP credentials, stack traces, or technical details to callers.
On failure, raises EmailDeliveryError so the route layer can show a safe message.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when email cannot be delivered. Never propagate to frontend."""
    pass


def _build_otp_email(to_email: str, username: str, otp: str) -> MIMEMultipart:
    """Build the MIME message for OTP email with HTML + plain-text fallback."""
    app_name = settings.APP_NAME
    expiry_minutes = settings.OTP_EXPIRY_SECONDS // 60

    subject = f"Password Reset OTP - {app_name}"

    # ── Plain-text fallback ───────────────────────────────────────────────────
    plain_text = f"""Hello {username},

We received a request to reset your password for {app_name}.

Your verification code is: {otp}

This code will expire in {expiry_minutes} minute(s).

For your security:
- Do not share this OTP with anyone.
- If you did not request a password reset, you can safely ignore this email.

Regards,
{app_name} Team
"""

    # ── HTML body ─────────────────────────────────────────────────────────────
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Password Reset OTP</title>
</head>
<body style="margin:0;padding:0;background-color:#0f172a;font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f172a;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0"
               style="background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);
                      border-radius:16px;border:1px solid #334155;
                      box-shadow:0 20px 60px rgba(0,0,0,0.5);">

          <!-- Header -->
          <tr>
            <td style="padding:32px 40px 24px;text-align:center;
                       border-bottom:1px solid #334155;">
              <table cellpadding="0" cellspacing="0" style="display:inline-block;">
                <tr>
                  <td style="background:#2563eb;border-radius:12px;
                             padding:10px 14px;margin-right:12px;">
                    <span style="font-size:24px;">🎓</span>
                  </td>
                  <td style="padding-left:14px;vertical-align:middle;">
                    <span style="font-size:20px;font-weight:700;color:#f8fafc;
                                 letter-spacing:-0.3px;">{app_name}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;">
              <p style="margin:0 0 8px;font-size:15px;color:#94a3b8;font-weight:500;">
                Hello <strong style="color:#e2e8f0;">{username}</strong>,
              </p>
              <p style="margin:0 0 28px;font-size:15px;color:#94a3b8;line-height:1.6;">
                We received a request to reset your password for
                <strong style="color:#e2e8f0;">{app_name}</strong>.
                Use the verification code below to continue.
              </p>

              <!-- OTP Box -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="margin:0 0 28px;">
                <tr>
                  <td align="center">
                    <div style="background:linear-gradient(135deg,#1d4ed8,#2563eb);
                                border-radius:12px;padding:24px 40px;
                                display:inline-block;
                                box-shadow:0 8px 24px rgba(37,99,235,0.35);">
                      <p style="margin:0 0 6px;font-size:12px;color:#bfdbfe;
                                font-weight:600;letter-spacing:3px;
                                text-transform:uppercase;">
                        Verification Code
                      </p>
                      <p style="margin:0;font-size:42px;font-weight:800;
                                color:#ffffff;letter-spacing:12px;
                                font-family:'Courier New',Courier,monospace;">
                        {otp}
                      </p>
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Expiry notice -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#422006;border:1px solid #854d0e;
                            border-radius:8px;margin-bottom:28px;">
                <tr>
                  <td style="padding:12px 16px;">
                    <p style="margin:0;font-size:13px;color:#fef3c7;">
                      ⏱&nbsp; This code expires in
                      <strong>{expiry_minutes} minute(s)</strong>.
                      Do not share it with anyone.
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:0;font-size:13px;color:#64748b;line-height:1.6;">
                If you did not request a password reset, you can safely ignore
                this email. Your password will not be changed.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 40px 28px;text-align:center;
                       border-top:1px solid #1e293b;">
              <p style="margin:0;font-size:12px;color:#475569;">
                Regards,&nbsp;<strong style="color:#64748b;">{app_name} Team</strong>
              </p>
              <p style="margin:8px 0 0;font-size:11px;color:#334155;">
                This is an automated security email. Please do not reply.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    # ── Assemble MIME message ─────────────────────────────────────────────────
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject

    # Proper From header: "Display Name <email@domain.com>"
    sender_addr = settings.MAIL_FROM or settings.MAIL_USERNAME or "noreply@example.com"
    msg["From"] = formataddr((settings.MAIL_FROM_NAME, sender_addr))
    msg["To"] = to_email

    # plain part first (lowest preference), then HTML
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    return msg


def send_otp_email(to_email: str, username: str, otp: str) -> None:
    """
    Send a password-reset OTP email.

    Raises:
        EmailDeliveryError: if SMTP delivery fails. Callers must catch this
            and return a safe generic message to the user.
    """
    # Always log to server console for ops visibility (never log OTP value in production)
    logger.info("[EMAIL] Sending OTP email to %s for user %s", to_email, username)
    
    # Debug: Check what we received
    mail_user = settings.MAIL_USERNAME or ""
    mail_pass = settings.MAIL_PASSWORD or ""
    
    # Dev mode if either is empty/whitespace
    if not mail_user.strip() or not mail_pass.strip():
        # Dev-mode fallback: print to console only
        logger.warning(
            "[EMAIL] SMTP credentials not configured. OTP for %s printed to server log only.",
            to_email
        )
        # Force flush to ensure immediate console output
        import sys
        print(f"\n{'='*60}", flush=True)
        print(f"[DEV MODE — PASSWORD RESET OTP]", flush=True)
        print(f"To:  {to_email}", flush=True)
        print(f"User: {username}", flush=True)
        print(f"OTP:  {otp}  (expires in {settings.OTP_EXPIRY_SECONDS}s)", flush=True)
        print(f"{'='*60}\n", flush=True)
        sys.stdout.flush()
        return  # Dev mode: treat as delivered

    msg = _build_otp_email(to_email, username, otp)
    sender_addr = settings.MAIL_FROM or settings.MAIL_USERNAME

    try:
        with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT, timeout=15) as server:
            server.ehlo()
            if settings.MAIL_USE_TLS:
                server.starttls()
                server.ehlo()
            server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
            server.sendmail(sender_addr, [to_email], msg.as_string())

        logger.info("[EMAIL] OTP email delivered successfully to %s", to_email)

    except smtplib.SMTPAuthenticationError as exc:
        logger.error("[EMAIL] SMTP authentication failed: %s", exc)
        raise EmailDeliveryError(
            "SMTP authentication failed. Check MAIL_USERNAME / MAIL_PASSWORD in .env. "
            "For Gmail, use a 16-character App Password, not your account password."
        ) from exc
    except smtplib.SMTPException as exc:
        logger.error("[EMAIL] SMTP error sending to %s: %s", to_email, exc)
        raise EmailDeliveryError(f"SMTP delivery failed: {exc}") from exc
    except OSError as exc:
        logger.error("[EMAIL] Network error sending to %s: %s", to_email, exc)
        raise EmailDeliveryError(f"Network error: {exc}") from exc


# ── Legacy shim — kept so existing imports in routes_auth.py don't break ─────
# This is replaced by the new OTP flow; preserved only for safety during migration.
def send_reset_password_email(to_email: str, reset_link: str) -> bool:
    """Deprecated: link-based reset. Kept for backward compatibility only."""
    logger.warning("[EMAIL] send_reset_password_email called (deprecated link-based reset)")
    print(f"[DEPRECATED RESET LINK] To: {to_email} | Link: {reset_link}")
    return True
